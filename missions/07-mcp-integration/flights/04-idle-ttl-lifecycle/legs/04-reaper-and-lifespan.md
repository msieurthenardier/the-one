# Leg: 04-reaper-and-lifespan

**Status**: completed
**Flight**: [Idle-TTL Lifecycle](../flight.md)

## Objective

Add the idle-TTL reaper task and `shutdown_drain` to `the_one/mcp/_pool.py`; integrate `acquire`'s entry-insertion path with `_ensure_reaper_running_locked`; wire `shutdown_drain` into `the_one/interfaces/web/app.py::lifespan` AFTER `_session_registry_shutdown_drain` and BEFORE `close_connection`. Re-export `shutdown_drain` from `the_one/mcp/__init__.py`. Tests cover reap-after-idle, reap-active-skipped, reap-error-isolation (one bad worker doesn't kill the loop), respawn-after-reap, parallel-warm-multiple-entries, lifespan-drain-cancels-reaper, lifespan-drain-awaits-all-workers, register-after-drain-raises, lifespan-order-spy, drain-timeout-handles-stuck-worker.

## Context

### Flight design decisions

- **§2 (`_evict` already in L3)**: L3's `_evict(key)` helper pops the entry under `_lock`, sets `evict_event`, awaits the worker with 10s timeout, cancel-on-stuck. L4 composes `_evict` into the reaper sweep and the drain.
- **§3 (TTL resolution)**: per-entry TTL stored at register time. `_reap_once` uses `entry.ttl_seconds` to decide expiry (`now - client.last_activity > ttl_seconds`). The L3 entry's `ttl_seconds` field is already populated; L4 reads it.
- **§12 (FastAPI lifespan ordering)**: shutdown sequence is (1) cancel in-flight per-message tasks, (2) `_session_registry_shutdown_drain` (PTY pool), (3) **NEW**: `mcp_pool_shutdown_drain` (this leg), (4) `close_connection` (DB). MCP pool drains AFTER PTY because PTY may have shell-tool-spawned MCP-aware code in flight; let it complete before MCP processes go away. Drains BEFORE DB close because drain may need source config from DB (precautionary; current design loads at register-time so this is forward-looking).
- **§4 (no hard pool size cap)**: idle TTL is the ONLY eviction mechanism. The reaper is what makes idle TTL real.

### Carries forward

- L3's `_evict(key)` primitive — verified by L3 test #11 against real bwrap and test #12 for idempotent missing-key behavior. L4 uses `_evict` exclusively for entry teardown; does NOT duplicate the cancel+await pattern.
- L3's `_shutting_down: bool` module-level flag — L4 sets it to True at the top of `shutdown_drain`; `acquire` reads it and raises `RuntimeError`.
- L3's `_REAPER_INTERVAL_SECONDS = 30.0` constant — L3 defined it for forward-reference; L4 wires the actual reaper.
- L1a's `MCPClient.last_activity` invariant — `last_activity` starts at `0.0` and is updated by `_touch_activity()` on each successful operation. `acquire` calls `_touch_activity()` on warm reuse; `_reap_once` reads `last_activity` to decide expiry.
- **`_MockClient` extension required (cycle-1 reviewer fix)**: L3's `_MockClient` class does NOT expose `last_activity` as a property — it has a `_touch_activity = MagicMock()` line that replaces the method, but no underlying `_last_activity` attribute or `last_activity` getter. L4 tests need to age the mock client by setting `client.last_activity = 0.0` to trigger expiry. **L4 extends `_MockClient` to expose `last_activity` as a settable instance attribute** (initialised to `0.0` in `__init__`; tests set it to `0.0` before reaping; production code would never set it directly because the real `MCPClient` has a property+`_touch_activity` mechanism). The mock's `_touch_activity` MagicMock then no longer needs to touch `last_activity` for L4 tests because the tests set it directly.
- L2's `_sandbox_disabled_for_tests()` bypass — irrelevant for L4 (the reaper doesn't go through `connect_stdio`).
- L1b's argv reorder — irrelevant for L4 (no bwrap operations beyond what L3 already exercises).

### Why this leg lands fifth (after L1a, L1b, L2, L3)

- L4 depends on L3's `_evict` primitive and `_RegistryEntry.ttl_seconds` field. Both are landed.
- L4 modifies `the_one/interfaces/web/app.py::lifespan` (the only L4 source change OUTSIDE `_pool.py`). Modification: insert `await mcp_pool_shutdown_drain()` between PTY drain and DB close. Single-line addition + import.
- L4 lands BEFORE L5 (docs) so `the_one/mcp/README.md` can document the live reaper + drain semantics.

## Inputs

What exists before this leg runs:

- `the_one/mcp/_pool.py` (post-L3) has: `_RegistryEntry` (with `ttl_seconds`, `worker`, `evict_event`, `client_ready`, `client`, `failure`); `_pool: dict`; `_lock`; `_shutting_down: bool = False`; `_DEFAULT_TTL_SECONDS = 300`; `_REAPER_INTERVAL_SECONDS = 30.0` (defined for L4); `_resolve_ttl_seconds`; `_load_source`; `_entry_worker`; `_evict`; `acquire`; `_clear_for_test`. **No `_reap_once`, `_reap_loop`, `_ensure_reaper_running_locked`, `shutdown_drain`, `_reaper_task` yet** — those are L4.
- `the_one/mcp/__init__.py` re-exports `acquire` (post-L3); `__all__` includes `"acquire"`. **No `shutdown_drain` re-export yet.** A forward-reference comment exists per L3 design.
- `the_one/interfaces/web/app.py:37` imports `from the_one.tools._session_registry import shutdown_drain as _session_registry_shutdown_drain`.
- `the_one/interfaces/web/app.py::lifespan` (lines 47-74) has the shutdown order: cancel in-flight tasks → `_session_registry_shutdown_drain` → `close_connection`. **No MCP pool drain yet.**
- `the_one/tools/_session_registry.py::shutdown_drain` is the structural template for L4's `shutdown_drain`.
- L3-end test counts: 138 collected (`{59, 14, 13, 9, 17, 14, 12}`); 137 passed + 1 skipped (Test L2 #6c EPERM). All L1a + L1b + L2 + L3 source changes uncommitted in working tree.

## Outputs

What exists after this leg completes:

- **`the_one/mcp/_pool.py`** gains:
  - `_reaper_task: asyncio.Task[None] | None = None` — module-level task ref (mirrors PTY pool).
  - `_ensure_reaper_running_locked() -> None` — async helper (must be called UNDER `_lock` to avoid double-spawn race). Spawns the reaper Task if not already running.
  - `_reap_once() -> list[tuple[str, str]]` — async helper: snapshot expired keys under `_lock`; `await _evict(key)` for each (sequentially, NOT gather'd, so each `_evict`'s 10s timeout is independent); returns the list of evicted keys for test purchase.
  - `_reap_loop() -> None` — async background loop: sleep `_REAPER_INTERVAL_SECONDS`, then `_reap_once`, repeat. On `CancelledError`: drain the registry via `await _evict(key)` for every remaining key (concurrently via `asyncio.gather(..., return_exceptions=True)`), then re-raise. On any other exception in `_reap_once`: log and continue (one bad eviction must not kill the loop).
  - `shutdown_drain() -> None` — async public function. Order: (1) set `_shutting_down = True`; (2) cancel `_reaper_task` if running, suppress its `CancelledError` (the reaper's own handler runs the registry drain); (3) belt-and-suspenders: snapshot all remaining keys and `_evict` them concurrently via `asyncio.gather(..., return_exceptions=True)` with the 10s per-key timeout already inside `_evict` (total drain bounded at ~10s regardless of pool size); (4) reset `_reaper_task = None` so a future test's `_clear_for_test` sees a clean slate.
  - `_clear_for_test` extended to ALSO cancel `_reaper_task` and reset `_shutting_down = False` (the L3 sketch already resets `_shutting_down`; L4 adds the reaper-cancel block).
  - `acquire()` modified to call `await _ensure_reaper_running_locked()` UNDER `_lock` immediately after inserting a new entry (the lock-held branch where `entry is None`). The PTY pool's `register` does this; L4 mirrors.

- **`the_one/mcp/__init__.py`** updated:
  - Add `from the_one.mcp._pool import shutdown_drain` (re-export AS-IS to mirror PTY pool's API name). The L3 forward-reference comment is REMOVED.
  - Extend `__all__` with `"shutdown_drain"`.
  - Consumers in `app.py` use the qualified import form `from the_one.mcp import shutdown_drain as _mcp_pool_shutdown_drain` to disambiguate from the PTY pool's `shutdown_drain`.

- **`the_one/interfaces/web/app.py`** modified:
  - Add import `from the_one.mcp import shutdown_drain as _mcp_pool_shutdown_drain` near line 37 (alongside the PTY-pool import).
  - In `lifespan`'s shutdown branch, after `_session_registry_shutdown_drain()` (line 71) and BEFORE `close_connection()` (line 74), add:
    ```python
    try:
        await _mcp_pool_shutdown_drain()
    except Exception:
        logger.exception("MCP pool shutdown failed")
    ```
  - Same `try/except Exception` shape as the PTY pool's call (NOT `BaseException`; CancelledError must propagate).

- **`tests/test_mcp_pool.py`** gains 9-10 new tests in a `TestReaperAndLifespan` class (or similar grouping):
  1. **`test_reap_after_idle_evicts_entry_and_disconnects_client`** — register entry with `ttl_seconds=1`; sleep 2s OR call `_reap_once()` after manually setting `client._last_activity = time.monotonic() - 5`; confirm key gone from `_pool` AND `client.disconnect` was awaited (mocked).
  2. **`test_reap_active_entry_skipped`** — entry with `ttl_seconds=300`, fresh `last_activity`; call `_reap_once()`; confirm key STILL in `_pool`, `client.disconnect` NOT called.
  3. **`test_reap_error_isolation_one_bad_evict_does_not_kill_loop`** — register two entries; mock `_evict` to raise on the first; confirm `_reap_once` returns successfully and the second entry is processed (or, if simpler, mock one `client.disconnect` to raise and confirm both entries get evicted from the pool dict). Locks "one bad close logs and continues."
  4. **`test_respawn_after_reap_creates_fresh_entry`** — `acquire` → fast-forward TTL → `_reap_once` → `acquire` again; confirm second acquire spawned a NEW worker and NEW client (different instance from the reaped one).
  5. **`test_parallel_warm_multiple_entries`** — register 3 entries with different keys; sleep < TTL; `_reap_once`; all 3 still warm. Then fast-forward TTL on entries 1 and 3 only; `_reap_once`; entry 2 is the only survivor.
  6. **`test_shutdown_drain_cancels_reaper_and_evicts_all_entries`** — register 3 entries; `await shutdown_drain()`; confirm `_pool == {}`, `_reaper_task is None`, `_shutting_down is True`, all 3 clients had `disconnect` awaited.
  7. **`test_acquire_after_shutdown_drain_raises_runtime_error`** — `await shutdown_drain()`; `with pytest.raises(RuntimeError, match="shutting down"): await acquire("a", "src")`. Locks the post-drain register-fail invariant.
  8. **`test_lifespan_order_pty_drain_before_mcp_drain_before_db_close`** — spy: monkeypatch `_session_registry_shutdown_drain`, `_mcp_pool_shutdown_drain`, `close_connection` to append themselves to a shared list when called; trigger `lifespan` shutdown; assert the list is `["pty", "mcp", "db"]`. Locks the §12 ordering against future regression.
  9. **`test_drain_timeout_handles_stuck_worker`** — register an entry whose mock client.disconnect sleeps for 30s (longer than `_evict`'s 10s timeout); call `shutdown_drain()`; assert `shutdown_drain` returns within ~10s (not 30s); the stuck worker is cancelled. Use `asyncio.wait_for(shutdown_drain(), timeout=15.0)` to bound the test.
  10. **`test_reap_loop_drains_on_cancellation`** — start `_reap_loop` via `asyncio.create_task`; register 2 entries; cancel the task; confirm both entries are evicted before the task's `CancelledError` propagates. Locks the reaper's CancelledError handler shape.
  11. **(integration, optional)** **`test_real_bwrap_reap_then_respawn`** — spawn real bwrap-wrapped client; monkeypatch `MCP_POOL_IDLE_TTL_SECONDS=1`; `await asyncio.sleep(2)`; `await _reap_once()`; assert pool empty AND original `client.is_alive is False`; second `acquire` spawns a fresh subprocess. Marker: `@requires_bwrap`.

- `tests/test_mcp_pool.py` count: 12 (post-L3) + 9-11 new = 21-23.
- Cumulative test count post-L4: 138 (post-L3) + 9-11 new = 147-149 (146-148 passed + 1 skipped).
- All other tests pass UNMODIFIED.

## Acceptance Criteria

- [ ] `the_one/mcp/_pool.py` adds `_reaper_task` module-level ref, `_ensure_reaper_running_locked`, `_reap_once`, `_reap_loop`, `shutdown_drain` per §Outputs.
- [ ] `_reap_once` snapshots expired keys under `_lock` (using `now - entry.client.last_activity > entry.ttl_seconds` as the expiry test); for each expired key, calls `await _evict(key)` (the L3 helper). Returns the list of evicted keys.
- [ ] `_reap_loop` runs the sleep+reap cycle. On CancelledError, drains the entire registry via `_evict` for every remaining key (concurrently via `asyncio.gather(..., return_exceptions=True)`), then re-raises CancelledError. On any other exception in `_reap_once`, logs and continues.
- [ ] `shutdown_drain` sets `_shutting_down = True` FIRST; cancels the reaper; suppresses CancelledError; runs a belt-and-suspenders snapshot+`_evict` for any remaining keys (the reaper's own drain handles the common case; this catches edge cases where the reaper was never spawned). Resets `_reaper_task = None` at the end.
- [ ] `acquire` calls `await _ensure_reaper_running_locked()` UNDER `_lock` immediately after `_pool[(agent, source)] = entry` for new entries. NOT called for warm-reuse paths.
- [ ] `_ensure_reaper_running_locked` is idempotent — multiple calls do not spawn multiple reapers.
- [ ] `the_one/mcp/__init__.py` re-exports `shutdown_drain`; `__all__` extended with `"shutdown_drain"`.
- [ ] `the_one/interfaces/web/app.py::lifespan` shutdown branch calls `_mcp_pool_shutdown_drain()` AFTER `_session_registry_shutdown_drain()` and BEFORE `close_connection()`, with the same `try/except Exception: logger.exception(...)` shape as the PTY drain.
- [ ] `tests/test_mcp_pool.py` gains 9-11 new tests covering reaper, drain, lifespan ordering, drain-timeout, and (optional) real-bwrap integration. Test #8 (`test_lifespan_order_pty_drain_before_mcp_drain_before_db_close`) directly locks §12.
- [ ] `_clear_for_test` cancels `_reaper_task` (in addition to the L3-defined entry-cancel + `_shutting_down=False` reset).
- [ ] All 138 prior tests across the L4-start surface pass UNMODIFIED.
- [ ] Cumulative `pytest tests/test_mcp_client.py tests/test_mcp_integration.py tests/test_mcp_sandbox_integration.py tests/test_mcp_stdio_sandbox.py tests/test_sandbox_bubblewrap.py tests/test_sandbox_contract.py tests/test_mcp_pool.py -q --timeout=60` returns 0 exit; collected 147-149; passed ≥ 146; skipped ≤ 2.
- [ ] `ruff check the_one/mcp/ the_one/interfaces/web/app.py tests/test_mcp_pool.py` clean.
- [ ] Flight log Leg Progress entry added with: (a) reaper-loop CancelledError-handler test confirmation, (b) drain-timeout test confirmation (10s bound observed empirically), (c) lifespan-order spy test confirmation, (d) confirmation of zero regressions in L1a/L1b/L2/L3 surface.

## Verification Steps

1. **`_reap_once` shape**: `grep -B 2 -A 15 "async def _reap_once" the_one/mcp/_pool.py` shows snapshot-under-lock + `await _evict(key)` per expired key.
2. **`_reap_loop` cancellation handler**: `grep -A 20 "async def _reap_loop" the_one/mcp/_pool.py` shows `try: ... except asyncio.CancelledError:` with the registry-drain block and re-raise.
3. **`shutdown_drain` order**: `grep -A 25 "async def shutdown_drain" the_one/mcp/_pool.py` shows `_shutting_down = True` FIRST, then reaper-cancel, then belt-and-suspenders drain.
4. **`acquire` reaper hookup**: `grep -B 2 -A 5 "_ensure_reaper_running_locked" the_one/mcp/_pool.py` shows the call inside the `if entry is None:` branch (under `_lock`).
5. **Lifespan integration**: `grep -B 2 -A 5 "_mcp_pool_shutdown_drain\|mcp.*shutdown_drain" the_one/interfaces/web/app.py` shows the import and the call inside `lifespan`'s shutdown branch, between PTY drain and DB close.
6. **Pool tests green**: `docker compose exec the-one pytest tests/test_mcp_pool.py -v --timeout=60` returns 0 exit; 21-23 tests passed.
7. **Cumulative regression invariant**: `docker compose exec the-one pytest tests/test_mcp_client.py tests/test_mcp_integration.py tests/test_mcp_sandbox_integration.py tests/test_mcp_stdio_sandbox.py tests/test_sandbox_bubblewrap.py tests/test_sandbox_contract.py tests/test_mcp_pool.py -q --timeout=60` returns 0 exit; collected 147-149.
8. **Lint clean**: `docker compose exec the-one ruff check the_one/mcp/ the_one/interfaces/web/app.py tests/test_mcp_pool.py` returns 0 exit.
9. **Flight log updated**: `grep -A 8 "04-reaper-and-lifespan" missions/07-mcp-integration/flights/04-idle-ttl-lifecycle/flight-log.md` shows a Leg Progress entry with status `landed`, timestamps, and the four test confirmations from AC #14.

## Implementation Guidance

1. **Capture L4-start state**: `git diff > /tmp/l4-baseline.diff`. Capture per-file test counts (expected: `{59, 14, 13, 9, 17, 14, 12}` = 138 collected, 137 passed + 1 skipped).

2. **Run the L4-affected baseline**:
   ```bash
   docker compose exec the-one pytest tests/test_mcp_pool.py -v --timeout=60
   ```
   Expect: 12 collected, 11 passed + 1 conditional-skipped or all-passed.

3. **Add reaper helpers to `the_one/mcp/_pool.py`** (between `_evict` and `acquire`, structurally mirroring `_session_registry.py:213-280`):

   ```python
   _reaper_task: asyncio.Task[None] | None = None


   async def _ensure_reaper_running_locked() -> None:
       """Spawn the reaper Task if not already running.

       MUST be called under `_lock` — avoids a double-spawn race when two
       concurrent `acquire`s for different keys both try to start the
       reaper in parallel.
       """
       global _reaper_task
       if _reaper_task is None or _reaper_task.done():
           _reaper_task = asyncio.create_task(_reap_loop())


   async def _reap_once() -> list[tuple[str, str]]:
       """Run a single reap pass: evict every entry whose
       `client.last_activity` is older than its `ttl_seconds`.

       Returns the list of evicted keys for test purchase. Per-entry
       eviction goes through `_evict`, which has its own 10s timeout.

       Eviction parallelism (cycle-1 reviewer Q1): per-key `_evict`
       calls run CONCURRENTLY via `asyncio.gather(..., return_exceptions=True)`.
       Rationale: if N entries are stuck (each blocking `_evict` for the
       full 10s timeout), sequential awaits would block the reap pass for
       10s × N (during which the loop cannot honor cancellation). Parallel
       gather bounds the worst-case reap-pass duration at ~10s regardless
       of pool size, matching `shutdown_drain`'s parallelism. The PTY pool
       template uses sequential close because subprocess SIGTERM-to-SIGKILL
       ladders are CPU-cheap (~1s each); MCP `_evict`'s 10s wait is much
       larger, justifying the divergence from the structural template.
       """
       now = time.monotonic()
       async with _lock:
           expired = [
               key
               for key, entry in _pool.items()
               if entry.client is not None
               and (now - entry.client.last_activity) > entry.ttl_seconds
           ]
       # _evict each expired key OUTSIDE the lock, IN PARALLEL. _evict
       # re-acquires the lock for its own pop — fair-FIFO ordering means
       # parallel evicts serialize on the lock briefly but the actual
       # worker awaits run concurrently.
       if expired:
           results = await asyncio.gather(
               *(_evict(key) for key in expired),
               return_exceptions=True,
           )
           for key, result in zip(expired, results):
               if isinstance(result, Exception):
                   logger.exception(
                       "MCP pool _evict raised during reap pass: key=%r exc=%r",
                       key,
                       result,
                   )
       return expired


   async def _reap_loop() -> None:
       """Background loop: sleep, reap, repeat.

       On CancelledError: drain the entire registry concurrently via
       `_evict` then re-raise. One bad `_reap_once` doesn't kill the loop
       (try/except Exception around the call).
       """
       try:
           while True:
               await asyncio.sleep(_REAPER_INTERVAL_SECONDS)
               try:
                   await _reap_once()
               except Exception:
                   logger.exception("MCP pool reap pass raised; continuing")
       except asyncio.CancelledError:
           # Drain the registry on cancellation. Concurrent _evict for
           # parallelism; gather with return_exceptions so one bad evict
           # doesn't block the others.
           async with _lock:
               keys = list(_pool.keys())
           if keys:
               await asyncio.gather(
                   *(_evict(key) for key in keys),
                   return_exceptions=True,
               )
           raise


   async def shutdown_drain() -> None:
       """Cancel the reaper task; evict every remaining entry.

       Wired into the FastAPI lifespan shutdown branch (between PTY pool
       drain and DB close per flight §12). After this runs, `acquire`
       raises `RuntimeError` for any late-arriving caller.

       Order:
         1. Set `_shutting_down = True` FIRST so any concurrent `acquire`
            sees the flag at the next lock acquisition.
         2. Cancel `_reaper_task`; suppress CancelledError on its await
            (the reaper's own CancelledError handler runs the drain).
         3. Belt-and-suspenders: snapshot any remaining keys (rare —
            the reaper's drain already ran). Concurrent `_evict` via
            gather with return_exceptions.
         4. Reset `_reaper_task = None` so the next test's
            `_clear_for_test` sees a clean slate.

       Total drain time is bounded at ~10s regardless of pool size
       because each `_evict` has a 10s per-entry timeout AND the
       gather'd evicts run in parallel.
       """
       global _reaper_task, _shutting_down
       _shutting_down = True

       task = _reaper_task
       if task is not None and not task.done():
           task.cancel()
           with contextlib.suppress(asyncio.CancelledError):
               await task

       # Belt-and-suspenders drain. Snapshot under lock; gather _evict.
       async with _lock:
           keys = list(_pool.keys())
       if keys:
           await asyncio.gather(
               *(_evict(key) for key in keys),
               return_exceptions=True,
           )

       _reaper_task = None
   ```

4. **Modify `acquire`** to call `_ensure_reaper_running_locked()` after inserting a new entry. Find the `if entry is None:` branch in L3's `acquire`; immediately after `_pool[(agent_name, source_id)] = entry`, insert `await _ensure_reaper_running_locked()` (still under the lock).

5. **Verify L3's `_clear_for_test` body**: before extending, `grep -B 1 -A 25 "async def _clear_for_test" the_one/mcp/_pool.py`. Confirm L3's body resets `_shutting_down = False`. If absent (L3 implementer deviation), L4 adds it alongside the reaper-cancel block. **Extend `_clear_for_test`** to cancel `_reaper_task` (in addition to L3's entry-cancel + `_shutting_down` reset). Mirror `_session_registry.py::_clear_for_test`'s pattern:

   ```python
   async def _clear_for_test() -> None:
       """Test seam: cancel reaper + workers; empty pool.

       Tests must call this in an autouse=True fixture AFTER each test;
       otherwise the next test inherits stale state.
       """
       global _reaper_task, _shutting_down

       # Cancel the reaper FIRST so it doesn't race the worker-cancel
       # below.
       task = _reaper_task
       if task is not None and not task.done():
           task.cancel()
           with contextlib.suppress(asyncio.CancelledError):
               await task
       _reaper_task = None

       # ... existing entry-cancel block from L3 ...

       _shutting_down = False
   ```

6. **Update `the_one/mcp/__init__.py`** to re-export `shutdown_drain`:

   ```python
   from the_one.mcp._pool import acquire, shutdown_drain  # noqa: E402

   __all__ = [
       # ... existing entries ...
       "acquire",
       "shutdown_drain",
   ]
   ```

   The L3 forward-reference comment is removed.

7. **Update `the_one/interfaces/web/app.py`**:
   - Add import near line 37: `from the_one.mcp import shutdown_drain as _mcp_pool_shutdown_drain`.
   - In `lifespan`'s shutdown branch (after the existing `try: await _session_registry_shutdown_drain() except Exception:` block at lines 70-73, BEFORE `await close_connection()` at line 74):
     ```python
     try:
         await _mcp_pool_shutdown_drain()
     except Exception:
         logger.exception("MCP pool shutdown failed")
     ```

8. **Extend `_MockClient`** in `tests/test_mcp_pool.py` to expose `last_activity` as a settable instance attribute. Cycle-1 reviewer caught that L3's `_MockClient` doesn't have this attribute — `_reap_once` reads `entry.client.last_activity` and would `AttributeError` against the mock. Add to `_MockClient.__init__`:

   ```python
   def __init__(self, source):
       type(self)._instance_count += 1
       self.source = source
       self.is_alive = False
       self.last_activity = 0.0  # ← L4 addition: settable mock attr
       self.connect = AsyncMock(side_effect=self._connect_impl)
       self.disconnect = AsyncMock(side_effect=self._disconnect_impl)
       self._touch_activity = MagicMock()
   ```

   Tests then set `client.last_activity = 0.0` directly (the L3 `_touch_activity` MagicMock continues to no-op the production touch path, but L4 tests bypass it).

9. **Add the new tests to `tests/test_mcp_pool.py`**. Place them in a `TestReaperAndLifespan` class or sibling section AFTER the existing L3 tests. Sketch:

   ```python
   # ─────────────────────────────────────────────────────────────────
   # L4 — Reaper, drain, lifespan
   # ─────────────────────────────────────────────────────────────────


   async def test_reap_after_idle_evicts_entry_and_disconnects_client(
       monkeypatch, patch_client
   ):
       monkeypatch.setenv("MCP_POOL_IDLE_TTL_SECONDS", "1")
       client = await acquire("agent-a", "src-1")
       # Manually age the entry by overriding last_activity.
       client.last_activity = 0.0  # ancient (mock attr added in step 8)

       evicted = await pool_mod._reap_once()
       assert ("agent-a", "src-1") in evicted
       assert ("agent-a", "src-1") not in pool_mod._pool
       client.disconnect.assert_awaited_once()


   async def test_reap_active_entry_skipped(patch_client):
       client = await acquire("agent-a", "src-1")
       # Fresh last_activity; default TTL=300s.
       evicted = await pool_mod._reap_once()
       assert evicted == []
       assert ("agent-a", "src-1") in pool_mod._pool
       client.disconnect.assert_not_awaited()


   async def test_reap_error_isolation_one_bad_evict_does_not_kill_loop(
       monkeypatch
   ):
       """One bad `client.disconnect` raises but reap pass completes for the rest."""

       class _PartialFailingClient(_MockClient):
           async def _disconnect_impl(self):
               if self.source.id == "src-bad":
                   raise RuntimeError("disconnect failed")
               self.is_alive = False

       _PartialFailingClient._instance_count = 0
       async def _patched_load_source(source_id):
           return _make_stub_source(source_id, name=source_id)
       monkeypatch.setattr(pool_mod, "MCPClient", _PartialFailingClient)
       monkeypatch.setattr(pool_mod, "_load_source", _patched_load_source)
       monkeypatch.setenv("MCP_POOL_IDLE_TTL_SECONDS", "1")

       c_good = await acquire("agent-a", "src-good")
       c_bad = await acquire("agent-a", "src-bad")
       c_good.last_activity = 0.0
       c_bad.last_activity = 0.0

       evicted = await pool_mod._reap_once()
       # Both keys reaped (one threw inside disconnect, but the entry
       # was still popped).
       assert set(evicted) == {("agent-a", "src-good"), ("agent-a", "src-bad")}
       assert pool_mod._pool == {}


   async def test_respawn_after_reap_creates_fresh_entry(patch_client, monkeypatch):
       monkeypatch.setenv("MCP_POOL_IDLE_TTL_SECONDS", "1")
       c1 = await acquire("agent-a", "src-1")
       c1.last_activity = 0.0
       await pool_mod._reap_once()
       assert pool_mod._pool == {}

       c2 = await acquire("agent-a", "src-1")
       assert c1 is not c2
       assert _MockClient._instance_count == 2


   async def test_parallel_warm_multiple_entries(patch_client, monkeypatch):
       monkeypatch.setenv("MCP_POOL_IDLE_TTL_SECONDS", "300")
       c1 = await acquire("agent-a", "src-1")
       c2 = await acquire("agent-a", "src-2")
       c3 = await acquire("agent-b", "src-1")
       assert len(pool_mod._pool) == 3

       evicted = await pool_mod._reap_once()
       assert evicted == []  # all fresh
       assert len(pool_mod._pool) == 3

       # Age entries 1 and 3.
       c1.last_activity = 0.0
       c3.last_activity = 0.0
       evicted = await pool_mod._reap_once()
       assert set(evicted) == {("agent-a", "src-1"), ("agent-b", "src-1")}
       assert len(pool_mod._pool) == 1
       assert ("agent-a", "src-2") in pool_mod._pool


   async def test_shutdown_drain_cancels_reaper_and_evicts_all_entries(
       patch_client,
   ):
       c1 = await acquire("agent-a", "src-1")
       c2 = await acquire("agent-a", "src-2")
       assert pool_mod._reaper_task is not None

       await pool_mod.shutdown_drain()
       assert pool_mod._pool == {}
       assert pool_mod._reaper_task is None
       assert pool_mod._shutting_down is True
       c1.disconnect.assert_awaited_once()
       c2.disconnect.assert_awaited_once()


   async def test_acquire_after_shutdown_drain_raises_runtime_error(
       patch_client,
   ):
       await pool_mod.shutdown_drain()
       with pytest.raises(RuntimeError, match="shutting down"):
           await acquire("agent-a", "src-1")


   async def test_lifespan_order_pty_drain_before_mcp_drain_before_db_close(
       monkeypatch,
   ):
       """Locks flight §12 ordering: PTY drain → MCP drain → DB close.

       Mocks the four startup calls (init_db, get_connection,
       migrate_json_to_sqlite, SQLiteAgentStore) so lifespan's startup
       doesn't try to talk to a real DB. Then mocks the three shutdown
       targets and asserts call order. Per cycle-1 reviewer fix — earlier
       drafts only mocked the shutdown targets, leaving startup to crash.
       """
       from the_one.interfaces.web import app as app_mod

       calls: list[str] = []

       # Startup mocks — minimal no-ops so lifespan reaches `yield`.
       async def _fake_init_db():
           pass

       _fake_conn = MagicMock()  # not awaited; just a sentinel
       async def _fake_get_connection():
           return _fake_conn

       async def _fake_migrate_json_to_sqlite(store):
           pass

       monkeypatch.setattr(app_mod, "init_db", _fake_init_db)
       monkeypatch.setattr(app_mod, "get_connection", _fake_get_connection)
       monkeypatch.setattr(
           app_mod, "migrate_json_to_sqlite", _fake_migrate_json_to_sqlite
       )
       monkeypatch.setattr(app_mod, "SQLiteAgentStore", MagicMock())
       monkeypatch.setattr(app_mod, "AgentFactory", MagicMock())

       # Shutdown spies.
       async def _fake_pty_drain():
           calls.append("pty")

       async def _fake_mcp_drain():
           calls.append("mcp")

       async def _fake_close_conn():
           calls.append("db")

       monkeypatch.setattr(
           app_mod, "_session_registry_shutdown_drain", _fake_pty_drain
       )
       monkeypatch.setattr(
           app_mod, "_mcp_pool_shutdown_drain", _fake_mcp_drain
       )
       monkeypatch.setattr(app_mod, "close_connection", _fake_close_conn)

       # Drive lifespan: enter (runs startup), exit (runs shutdown).
       from fastapi import FastAPI
       fake_app = FastAPI()
       async with app_mod.lifespan(fake_app):
           pass

       # Filter to the three drain steps; assert order.
       drain_steps = [c for c in calls if c in ("pty", "mcp", "db")]
       assert drain_steps == ["pty", "mcp", "db"]


   async def test_drain_timeout_handles_stuck_worker(monkeypatch):
       """A worker stuck in disconnect for 30s gets cancelled at the 10s timeout."""

       class _StuckClient(_MockClient):
           async def _disconnect_impl(self):
               await asyncio.sleep(30)  # never returns within the test budget
               self.is_alive = False

       _StuckClient._instance_count = 0
       async def _patched_load_source(source_id):
           return _make_stub_source(source_id)
       monkeypatch.setattr(pool_mod, "MCPClient", _StuckClient)
       monkeypatch.setattr(pool_mod, "_load_source", _patched_load_source)

       await acquire("agent-a", "src-1")

       # shutdown_drain must return within ~10s (per-entry _evict timeout)
       # plus a small overhead for the reaper-cancel. Bound at 15s.
       await asyncio.wait_for(pool_mod.shutdown_drain(), timeout=15.0)

       assert pool_mod._pool == {}


   async def test_reap_loop_drains_on_cancellation(patch_client, monkeypatch):
       """The reaper's CancelledError handler drains the registry."""
       # Speed up the loop's sleep so the test doesn't wait the full 30s.
       monkeypatch.setattr(pool_mod, "_REAPER_INTERVAL_SECONDS", 0.05)

       c1 = await acquire("agent-a", "src-1")
       c2 = await acquire("agent-a", "src-2")
       reaper = pool_mod._reaper_task
       assert reaper is not None and not reaper.done()

       reaper.cancel()
       with contextlib.suppress(asyncio.CancelledError):
           await reaper

       # Cancellation handler ran the drain.
       assert pool_mod._pool == {}
       c1.disconnect.assert_awaited_once()
       c2.disconnect.assert_awaited_once()
   ```

10. **Run the L4 regression suite**:
    ```bash
    docker compose exec the-one pytest tests/test_mcp_client.py tests/test_mcp_integration.py tests/test_mcp_sandbox_integration.py tests/test_mcp_stdio_sandbox.py tests/test_sandbox_bubblewrap.py tests/test_sandbox_contract.py tests/test_mcp_pool.py -q --timeout=60
    ```
    Expect 147-149 collected; ≥146 passed; ≤2 skipped.

11. **Lint**:
    ```bash
    docker compose exec the-one ruff check the_one/mcp/ the_one/interfaces/web/app.py tests/test_mcp_pool.py
    ```

12. **Update the flight log** with status `landed`, ISO 8601 UTC timestamps, the four test confirmations from AC #14, and a note that the reaper's CancelledError-handler test (#10) verified the registry drains correctly when the reaper task is cancelled mid-loop (locks the F4 §12 contract from the cancellation side).

## Edge Cases

- **`_reap_once` reads `entry.client.last_activity` — but `entry.client` may be `None`** if the worker is mid-connect. Guard: `if entry.client is not None and (now - entry.client.last_activity) > entry.ttl_seconds`. An entry with `client is None` is NEVER expired by the reaper; it stays until either the worker connects (then becomes reapable) or the worker fails (`_clear_for_test` or future maintenance reaps it).
- **`_evict` race with concurrent `acquire`**: if `_reap_once` snapshots key K, then a concurrent `acquire` for key K reads the still-present entry (lock-fair), sees a connected client, returns it; THEN `_evict(K)` runs, pops K, evicts the worker. The acquired client then receives a `disconnect` from the worker's finally block while the caller still holds the reference. The caller's next `client.list_tools()` raises `MCPConnectionError("not connected")`. **This is a known race**, mitigated by the L4 design's "touch_activity on acquire" — fresh activity makes K not-expired on the next `_reap_once` pass. Document in §Edge Cases of `the_one/mcp/README.md` (L5).
- **`shutdown_drain` re-entrancy**: if called twice, the second call sees `_shutting_down = True`, no reaper task to cancel, empty pool to drain (or near-empty); idempotent. Test #7 implicitly covers this (a second `acquire` after drain raises; a second `shutdown_drain` would also be safe).
- **Reaper-cancel vs. belt-and-suspenders double-evict**: when `shutdown_drain` cancels the reaper, the reaper's CancelledError handler runs ITS own drain (via `asyncio.gather(*(_evict(key) for key in keys), return_exceptions=True)`); after `await task` returns, `_pool` is empty. `shutdown_drain`'s subsequent belt-and-suspenders snapshot+gather then sees an empty pool and is a no-op. **No double-evict** in normal flow. If any inner `_evict` timed out and left the entry partially evicted (popped but worker still cancelling), `shutdown_drain`'s second snapshot still sees an empty pool because `_evict` pops under `_lock` BEFORE awaiting the worker. The `_evict` idempotent-on-missing-key contract (L3 test #12) is the safety net.
- **Reaper task in test environment**: tests' autouse `_clear_for_test` fixture cancels the reaper between tests. If a test forgets the fixture, the reaper bound to a torn-down event loop produces "RuntimeError: Event loop is closed" warnings. The `_clear_for_test` extension in step 5 prevents this.
- **`_REAPER_INTERVAL_SECONDS` test override**: `monkeypatch.setattr(pool_mod, "_REAPER_INTERVAL_SECONDS", 0.05)` works because `_reap_loop` reads the constant at call time (`await asyncio.sleep(_REAPER_INTERVAL_SECONDS)` is a `LOAD_GLOBAL` against the module dict). Confirmed.
- **Lifespan ordering test #8 race**: if the test runs BEFORE the autouse `_clear_for_test` fixture for some reason, stale `_reaper_task` from a prior test could interfere. Mitigated by the autouse fixture; document the dependency.

## Files Affected

- `the_one/mcp/_pool.py` — add `_reaper_task`, `_ensure_reaper_running_locked`, `_reap_once`, `_reap_loop`, `shutdown_drain`; modify `acquire` (add `_ensure_reaper_running_locked()` call); extend `_clear_for_test` (cancel reaper).
- `the_one/mcp/__init__.py` — re-export `shutdown_drain`; extend `__all__`; remove L3 forward-reference comment.
- `the_one/interfaces/web/app.py` — add import; add `_mcp_pool_shutdown_drain()` call in `lifespan` shutdown branch.
- `tests/test_mcp_pool.py` — 9-11 new tests for reaper, drain, lifespan ordering, drain-timeout, cancellation-handler.
- `missions/07-mcp-integration/flights/04-idle-ttl-lifecycle/flight-log.md` — append Leg Progress entry.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`. Do NOT commit.**

- [ ] All acceptance criteria verified
- [ ] `pytest tests/test_mcp_client.py tests/test_mcp_integration.py tests/test_mcp_sandbox_integration.py tests/test_mcp_stdio_sandbox.py tests/test_sandbox_bubblewrap.py tests/test_sandbox_contract.py tests/test_mcp_pool.py -q --timeout=60` green; collected 147-149
- [ ] `ruff check the_one/mcp/ the_one/interfaces/web/app.py tests/test_mcp_pool.py` clean
- [ ] Flight log Leg Progress entry added
- [ ] Set this leg's status to `landed`
- [ ] Check off this leg in flight.md (the `[ ] 04-reaper-and-lifespan` line)
- [ ] Do NOT commit. Do NOT signal `[COMPLETE:leg]`. Signal `[HANDOFF:review-needed]` and stop.

---

## Citation Audit

5 citations verified against current code at leg design time (2026-05-07).

- `the_one/tools/_session_registry.py` (entire module) — structural template; mirror confirmed at L3 design and re-confirmed at L4 design. Specifically lines 213-280 (`_ensure_reaper_running_locked`, `_reap_once`, `_reap_loop`) — **OK**.
- `the_one/interfaces/web/app.py:37` (PTY-pool import: `from the_one.tools._session_registry import shutdown_drain as _session_registry_shutdown_drain`) — **OK**.
- `the_one/interfaces/web/app.py:47-74` (`lifespan` async-CM with shutdown branch: cancel in-flight tasks → PTY drain → `close_connection`) — **OK**.
- `the_one/mcp/_pool.py` (post-L3: has `_RegistryEntry`, `_pool`, `_lock`, `_shutting_down`, `_DEFAULT_TTL_SECONDS`, `_REAPER_INTERVAL_SECONDS`, `_resolve_ttl_seconds`, `_load_source`, `_entry_worker`, `_evict`, `acquire`, `_clear_for_test`. NO reaper helpers yet — those land in this leg.) — **OK**.
- `the_one/mcp/__init__.py` (post-L3: re-exports `acquire`; no `shutdown_drain` yet) — **OK**.
