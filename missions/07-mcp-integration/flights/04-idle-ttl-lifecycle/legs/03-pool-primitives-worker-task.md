# Leg: 03-pool-primitives-worker-task

**Status**: completed
**Flight**: [Idle-TTL Lifecycle](../flight.md)

## Objective

Create `the_one/mcp/_pool.py` with the per-`(agent_name, source_id)` pool primitives — `_RegistryEntry` dataclass, module-level `_pool` dict, `_lock` asyncio.Lock, `_resolve_ttl_seconds` helper, `_load_source` repository helper, `_entry_worker` coroutine (the worker-task-per-entry pattern), `_evict` helper, and `acquire` public function. Re-export `acquire` from `the_one/mcp/__init__.py`. NO reaper / lifespan integration in this leg (those are L4). NO drain logic in this leg either; only the acquire path + entry worker + evict primitive that L4 will compose into a sweep loop.

## Context

### Flight design decisions

- **§1 (per-`(agent_name, source_id)` keying)**: pool is `dict[tuple[str, str], _RegistryEntry]`. Mirrors `the_one/tools/_session_registry.py:73` structurally.
- **§2 (lazy demand-paged spawn — worker-task-per-entry pattern)**: each entry owns a dedicated `asyncio.Task` (the entry worker). The worker holds the `MCPClient` connect/disconnect on the SAME task — anyio's cross-task `CancelScope.__aexit__` guard is satisfied mechanically. The reaper (L4) signals via `entry.evict_event`; the worker's `finally:` runs disconnect on its own task. **§2 pseudo-code is the authoritative implementation guide.**
- **§2 (race-handling invariant)**: cycle-2 fix — the lock-held branch checks `entry is None`, NOT `entry.client is None`. Concurrent same-key acquires share the worker by waiting on `entry.client_ready`. Worker is the sole writer of `entry.client` and `entry.failure`; both written BEFORE `entry.client_ready.set()`.
- **§2 (acquire cancellation)**: caller cancels mid-`await ready.wait()` → worker keeps running normally. Entry stays in `_pool` and reaps on idle TTL. NOT a leak; worker still runs disconnect on its own task when evicted.
- **§2 + §3 (`_load_source` outside the lock — cycle-2 medium #2)**: pre-load the source from the F1 repository OUTSIDE `_lock` so acquires for DIFFERENT keys don't serialize on a slow DB read.
- **§3 (TTL resolution)**: AT register-time per-entry. `_resolve_ttl_seconds()` reads `MCP_POOL_IDLE_TTL_SECONDS` env var (default 300s) at the moment a new entry is created. Per-source override is deferred to a future flight.
- **§4 (no hard pool size cap)**: idle TTL is the only eviction mechanism. Pathological-case bound is OS process limit.
- **§11 (module placement)**: `the_one/mcp/_pool.py` (underscore-private). Public API at `the_one.mcp.acquire` via re-export from `the_one/mcp/__init__.py`. Internal symbols all underscore-prefixed.

### Carries forward

- L1a's `MCPClient` AsyncExitStack refactor: pool's `_entry_worker` calls `await client.connect()` / `await client.disconnect()` (the standard public API). The same-task contract is satisfied because both calls run on the worker task. The cross-task safety net swallow at `MCPClient.disconnect()` is documented but not exercised under the pool's worker-task pattern (L1a's `test_worker_task_pattern_no_safety_net_log` already locks this against the real anyio task group; L3 inherits the contract, doesn't re-prove it).
- L2's `MCPSandboxError` translation in `connect_stdio` propagates to `MCPClient.connect()` → re-raised by `MCPClient.connect()` via the `except (MCPClientError, NotImplementedError):` branch → caught by `_entry_worker`'s `except BaseException as exc:` → stored in `entry.failure` → re-raised to `acquire` callers. Same path for `MCPConnectionError` / `MCPVersionMismatch` / `MCPCapabilityMissing`. Test #5 in L3 locks this end-to-end.
- F3's `mcp_fixture_sandbox_profile` fixture (still flagged as dead code): consumed by L3's pool integration tests (the few tests that go through real bwrap; most L3 tests mock `MCPClient`). This resolves the F3 dead-code flag in this leg.
- F1's `MCPSourceRepository` at `the_one/db/repositories.py:247-330`. Public method: `async def get(source_id: str) -> MCPSource` (raises `KeyError` if not found). Factory pattern from `the_one/interfaces/web/api.py::_mcp_repo` shows construction: `conn = await get_connection(); encryptor = get_encryptor(settings.data_dir); return MCPSourceRepository(conn, encryptor)`.

### Why this leg lands fourth (after L1a, L1b, L2)

L3 is architecturally the largest leg in the flight. It depends on:
- **L1a**: clean `MCPClient.connect/disconnect` contract via AsyncExitStack (so worker-task disconnect doesn't trip unexpected paths).
- **L1b**: `--tmpfs /tmp` argv ordering correct (so any pool-test that uses real bwrap and writable_paths under /tmp works).
- **L2**: `MCPSandboxError` translated correctly (so test #5 below — spawn-failure-propagates — actually exercises the F3 §6 catalog, not just F2's catch-all).

L4 (reaper + lifespan) builds on L3's `_evict` helper. L5 (docs) cross-references the pool primitives. L6 (HAT) drives them end-to-end against a real third-party MCP.

## Inputs

What exists before this leg runs:

- `the_one/mcp/__init__.py` exists with `_PINNED_PROTOCOL_VERSION`, `MCP_DEFAULT_TIMEOUT_SECONDS`, `MCP_DEFAULT_CALL_TIMEOUT_SECONDS`, `MCPClient`, `MCPTool`, `MCPToolResult`, and the seven error classes in `__all__`. **No `acquire` or `shutdown_drain` re-export yet.**
- `the_one/mcp/client.py::MCPClient` post-L1a: `__init__` sets `self._transport_stack: AsyncExitStack | None = None`; `connect()` builds the stack; `disconnect()` is idempotent and never raises.
- `the_one/db/repositories.py::MCPSourceRepository.get(source_id)` exists; raises `KeyError` if not found.
- `the_one/db/connection.py::get_connection()` exists (verified at L3 design via grep).
- `the_one/encryption.py::get_encryptor(data_dir)` exists.
- `the_one/config.py::settings.data_dir` exists.
- `the_one/tools/_session_registry.py` is the structural template for L3's pool. Its module docstring, dataclass placement, lock-and-await deadlock-avoidance pattern, and `_clear_for_test` test seam are mirrored in L3 (different content; same shape).
- Test counts at L3-start (post-L2): 126 tests collected (`{59, 14, 13, 9, 17, 14}`); 125 passed + 1 skipped (Test #6c EPERM in dev container).
- L1a + L1b + L2 source changes are uncommitted in the working tree (per agentic-workflow's flight-final-commit pattern).

## Outputs

What exists after this leg completes:

- **`the_one/mcp/_pool.py`** (new, ~250-350 lines) — implements the worker-task-per-entry pool per flight §2 + §11. Module docstring credits the structural mirror of `the_one/tools/_session_registry.py`. **NO reaper, NO `shutdown_drain`** — those are L4. Internal symbols (all underscore-prefixed):
  - `_DEFAULT_TTL_SECONDS = 300` — module-level int (default for `_resolve_ttl_seconds()` env-var fallback).
  - `_REAPER_INTERVAL_SECONDS = 30.0` — module-level float, defined in L3 for forward-reference but UNUSED until L4 wires the reaper. Tests can monkeypatch.
  - `_RegistryEntry` dataclass with fields: `ttl_seconds: int`, `worker: asyncio.Task[None] | None = None` (None during the brief construction window before `acquire` assigns the spawned Task — cycle-1 reviewer flagged that earlier `worker: asyncio.Task[None]` annotation forbade the temporary None), `evict_event: asyncio.Event`, `client_ready: asyncio.Event`, `client: MCPClient | None = None`, `failure: BaseException | None = None`. **`acquire` and `_evict` MUST `assert entry.worker is not None` before awaiting it** — the assignment in `acquire` happens immediately after dataclass construction (atomic from the perspective of any other caller, since `_lock` is held), so the assertion is sound.
  - `_pool: dict[tuple[str, str], _RegistryEntry] = {}`.
  - `_lock: asyncio.Lock = asyncio.Lock()`.
  - `_shutting_down: bool = False` — set by `shutdown_drain()` (L4); read by `acquire` (this leg) to raise `RuntimeError` for late callers.
  - `_resolve_ttl_seconds() -> int` — reads `os.environ.get("MCP_POOL_IDLE_TTL_SECONDS", str(_DEFAULT_TTL_SECONDS))`; returns the int. Reads at call-time (so test monkeypatch.setenv works).
  - `_load_source(source_id: str) -> MCPSource` — async helper that constructs an `MCPSourceRepository` (via `get_connection() + get_encryptor(settings.data_dir)`) and calls `await repo.get(source_id)`. Raises `KeyError` on miss, propagated to the caller.
  - `_entry_worker(source: MCPSource, entry: _RegistryEntry) -> None` — the worker task per §2. Constructs `MCPClient(source)`, awaits `connect()`. On exception, stores in `entry.failure`, sets `entry.client_ready`, returns. On success, stores `entry.client`, sets `entry.client_ready`, awaits `entry.evict_event`. On evict, runs `await client.disconnect()` in the `finally:` block.
  - `_evict(key: tuple[str, str]) -> None` — async helper per §2. Pops the entry under `_lock`, sets `evict_event`, awaits the worker with a 10s timeout (cancel + suppress on timeout). Used by L4's reaper and by `_clear_for_test`.
  - `acquire(agent_name: str, source_id: str) -> MCPClient` — async public function per §2 pseudo-code. Pre-loads the source OUTSIDE the lock; under the lock, dispatches by `entry is None` (atomic existence check); waits on `entry.client_ready` outside the lock; raises `entry.failure` if connect failed (and pops the entry idempotently); returns `entry.client` on success. On success, calls `client._touch_activity()` so the L4 reaper sees the use.
  - `_clear_for_test() -> None` — async test seam mirroring `_session_registry.py::_clear_for_test`. Cancels all worker tasks, drains the dict, resets `_shutting_down = False`.

- **`the_one/mcp/__init__.py`** updated:
  - Add `from the_one.mcp._pool import acquire` at module level.
  - Extend `__all__` with `["acquire"]`.
  - **NOTE**: `shutdown_drain` is added in L4, NOT this leg. Document with a `# L4 will add: from the_one.mcp._pool import shutdown_drain` comment so the import-order discipline is forward-referenced.
  - **No `MCPSandboxError` re-export added in this leg** (L2 left it out of `__all__`; that's a separate leg-or-routine-maintenance item; not in F4 scope).

- **`tests/test_mcp_pool.py`** (new, ~400-500 lines) — 9-11 tests covering:
  1. **`test_acquire_lazy_spawn_creates_worker_and_returns_client`** — first acquire for `(agent_name, source_id)` spawns exactly one worker; returns the connected `MCPClient`. Uses a mock `MCPClient` (monkeypatched via `the_one.mcp._pool.MCPClient`) to avoid real bwrap.
  2. **`test_acquire_warm_reuse_returns_same_client_instance`** — second acquire for the same key returns `id(client) == id(c1)`; spawns NO new worker; `client._touch_activity()` was called twice (once per acquire).
  3. **`test_concurrent_acquire_same_key_shares_one_worker`** — fire 5 concurrent `asyncio.create_task(acquire("a", "src1"))`; `await asyncio.gather(...)`; assert exactly ONE worker spawned (mock `MCPClient` has a class-level call count); all 5 awaiters got the same client instance. **This is the cycle-2 race-fix lock.**
  4. **`test_different_keys_spawn_independent_workers`** — `acquire("agent-a", "src1")` and `acquire("agent-b", "src1")` produce different worker tasks AND different `MCPClient` instances. Per-`(agent, source)` isolation invariant.
  5. **`test_spawn_failure_propagates_to_acquire_callers`** — mock `MCPClient.connect` to raise `MCPSandboxError`; first acquire raises `MCPSandboxError`; concurrent acquires for the same key during the failed connect ALL raise the same `MCPSandboxError`. Locks the §2 failure-propagation path via `entry.failure` + `entry.client_ready`.
  6. **`test_spawn_failure_pop_is_idempotent_under_concurrent_acquires`** (cycle-1 reviewer fix): TWO concurrent `asyncio.gather(acquire("a", "src1"), acquire("a", "src1"), return_exceptions=True)` calls against `_FailingClient`; both raise the SAME `MCPConnectionError` instance (the worker's stored `entry.failure`). The first failure-observer pops the entry; the second's `_pool.pop(key, None)` is a no-op because the entry is already gone — the `, None` default on `pop` makes this safe (would `KeyError` without it). Then a third sequential acquire with `_RetryClient` succeeds, proving the pool can recover after a failure burst. Earlier revisions had a single-caller version of this test that did NOT exercise the concurrent idempotent-pop path — the `_pool.pop(key, None)` guard was untested against future regressions.
  7. **`test_acquire_cancellation_leaves_worker_running`** — start `acquire`, cancel the calling task mid-`await ready.wait()` (use `asyncio.wait_for` with `timeout=0.001` against a slow-mock-connect that sleeps), confirm the worker is still alive in `_pool`. Subsequent uncancelled acquire on the same key sees the entry, waits, and gets the client. NO leak.
  8. **`test_load_source_runs_outside_the_lock`** — spy: monkeypatch `_load_source` to record `id(_lock._lock)` at call time; assert that the lock is NOT held when `_load_source` runs. Per cycle-2 medium #2 — different keys must not serialize on the F1 DB read.
  9. **`test_clear_for_test_cancels_workers_and_empties_pool`** — register 3 entries; call `_clear_for_test()`; assert `_pool == {}` AND all 3 worker tasks are done (cancelled and awaited).
  10. **(integration)** **`test_acquire_real_bwrap_end_to_end_with_strict_floor_profile`** — uses the F3 `mcp_fixture_sandbox_profile` strict-floor fixture + `mcp_fixture_stdio_params` to construct an `MCPSource` for the in-repo `hello_server` fixture; calls `acquire("test-agent", source.id)`; asserts `client.is_alive` and `len(await client.list_tools()) > 0`. Marker: `@requires_bwrap`.
  11. **(integration)** **`test_acquire_then_evict_via_internal_helper`** — uses real bwrap-spawned client; calls `acquire`; then directly calls `_pool._evict((agent, source_id))`; asserts `_pool` is empty AND the `MCPClient.is_alive is False`. Locks the `_evict` contract for L4's later reaper. Note: by the time `_evict`'s `await asyncio.wait_for(entry.worker, ...)` returns, the worker has fully completed its `finally:` block and `client.disconnect()` has run — the `is_alive is False` assertion is race-free.
  12. **`test_evict_idempotent_on_missing_key`** (cycle-1 reviewer suggestion) — `await _pool._evict(("nope", "nope"))` against a key that was never inserted; expect a no-op (no raise). Locks the `if entry is None: return` guard against future regressions where someone "simplifies" the None check.

- An autouse fixture `_clear_pool_after_each_test` is added at the top of `tests/test_mcp_pool.py` to call `await _pool._clear_for_test()` after every test (mirrors the F4 PTY pool's pattern).

- `tests/test_mcp_pool.py` count: **12 tests** (9 unit-style with mock `MCPClient`, 2 integration-style with real bwrap marked `@requires_bwrap`, 1 idempotent-`_evict` smoke test). All 12 add to collected count regardless; integration tests skip cleanly if `bwrap` is missing.

- **No changes to `tests/test_mcp_client.py`, `tests/test_mcp_integration.py`, `tests/test_mcp_sandbox_integration.py`, `tests/test_mcp_stdio_sandbox.py`, `tests/test_sandbox_bubblewrap.py`, or `tests/test_sandbox_contract.py`.**

- Cumulative test count post-L3: 126 (post-L2) + **12 new** = **138** (137 passed + 1 skipped — only L2 #6c EPERM skips in the dev container; integration tests #10/#11 run because bwrap is present). In a privilege-stripped CI without SYS_ADMIN, integration tests #10/#11 may also fail with EPERM-on-unshare → catalog #3 `MCPSandboxError`; document as expected behavior in those environments.

## Acceptance Criteria

- [ ] `the_one/mcp/_pool.py` exists and matches the structural pattern of `the_one/tools/_session_registry.py` (module docstring credits the mirror; `_RegistryEntry` dataclass; `_pool: dict[tuple[str, str], _RegistryEntry]`; `_lock: asyncio.Lock`; `_shutting_down: bool`; helper functions all underscore-prefixed; `_clear_for_test` autouse-friendly).
- [ ] `_RegistryEntry` has the six fields per flight §2: `ttl_seconds: int`, `worker: asyncio.Task[None]`, `evict_event: asyncio.Event`, `client_ready: asyncio.Event`, `client: MCPClient | None = None`, `failure: BaseException | None = None`.
- [ ] `acquire(agent_name, source_id) -> MCPClient` is async, follows §2 pseudo-code: pre-loads source OUTSIDE the lock; under the lock, checks `entry is None` (NOT `entry.client is None`); spawns worker via `asyncio.create_task`; waits on `entry.client_ready` outside the lock; raises `entry.failure` (and pops idempotently) if connect failed; returns `entry.client` and calls `_touch_activity()` on success.
- [ ] `_entry_worker(source, entry)` is async; constructs `MCPClient(source)`, awaits `client.connect()`; on `BaseException`, stores in `entry.failure`, sets `entry.client_ready`, returns; on success, stores `entry.client`, sets `entry.client_ready`, awaits `entry.evict_event`; in `finally:`, runs `await client.disconnect()`. Worker is the SOLE WRITER of `entry.client` and `entry.failure`, BOTH written BEFORE `entry.client_ready.set()`.
- [ ] `_evict(key)` is async; pops the entry under `_lock`; sets `evict_event`; awaits the worker with `asyncio.wait_for(worker, timeout=10.0)`; on timeout, cancels and `with contextlib.suppress(BaseException): await worker`.
- [ ] `_resolve_ttl_seconds()` reads `os.environ.get("MCP_POOL_IDLE_TTL_SECONDS")` at call time; defaults to 300 if unset; returns int. Tests can `monkeypatch.setenv` to change the value for new entries.
- [ ] `_load_source(source_id)` constructs `MCPSourceRepository` via the same factory shape as `the_one/interfaces/web/api.py::_mcp_repo` and calls `await repo.get(source_id)`. Raises whatever the repo raises (e.g., `KeyError`).
- [ ] `_clear_for_test()` cancels all live worker tasks, awaits them with suppress, empties `_pool`, resets `_shutting_down = False`.
- [ ] `the_one/mcp/__init__.py` re-exports `acquire`; `__all__` extended to include `"acquire"`.
- [ ] `tests/test_mcp_pool.py` exists with the **12 tests** listed in §Outputs (9 unit-style with mock `MCPClient` + 2 integration tests with real bwrap marker `@requires_bwrap` + 1 idempotent-`_evict` smoke test). Test #3 (concurrent-acquire) directly exercises the cycle-2 race-fix; test #6 (concurrent failure observers) locks the idempotent-pop contract under contention.
- [ ] All 126 prior tests across the L3-start surface (`{59, 14, 13, 9, 17, 14}` per L2-end target) pass UNMODIFIED. The single-skipped EPERM test (L2 #6c) continues to skip in the dev container.
- [ ] Cumulative `pytest tests/test_mcp_client.py tests/test_mcp_integration.py tests/test_mcp_sandbox_integration.py tests/test_mcp_stdio_sandbox.py tests/test_sandbox_bubblewrap.py tests/test_sandbox_contract.py tests/test_mcp_pool.py -q --timeout=60` returns 0 exit; collected = **138** (126 prior + 12 new); passed ≥ 137; skipped ≤ 1 (only L2 #6c EPERM in dev container).
- [ ] `ruff check the_one/mcp/ tests/test_mcp_pool.py` clean (no NEW errors vs baseline).
- [ ] Flight log Leg Progress entry added with: (a) module-level test for the cycle-2 race-fix (test #3 passes), (b) confirmation that worker-task pattern correctly satisfies anyio's cross-task guard against real bwrap (integration test #11 passes), (c) `_clear_for_test` covers all post-test cleanup (no orphan workers or processes leak between tests).

## Verification Steps

1. **`_pool.py` structural mirror**: `grep -n "^_\|^async def \|^def " the_one/mcp/_pool.py` shows the symbols listed in §Outputs.
2. **Race-fix lock check**: `grep -A 5 "if entry is None" the_one/mcp/_pool.py` shows the lock-held branch checks `entry is None`, NOT `entry.client is None`.
3. **`_load_source` outside lock**: `grep -B 2 -A 8 "_load_source\|async with _lock" the_one/mcp/_pool.py` shows `_load_source` called BEFORE `async with _lock:`.
4. **`__init__.py` re-export**: `grep -n "acquire" the_one/mcp/__init__.py` shows the re-export line and inclusion in `__all__`.
5. **Pool tests green**: `docker compose exec the-one pytest tests/test_mcp_pool.py -v --timeout=60` returns 0 exit; 9-11 tests passed (or 7-9 passed + 2 skipped if `@requires_bwrap` skip-gate fires).
6. **Cumulative regression invariant**: `docker compose exec the-one pytest tests/test_mcp_client.py tests/test_mcp_integration.py tests/test_mcp_sandbox_integration.py tests/test_mcp_stdio_sandbox.py tests/test_sandbox_bubblewrap.py tests/test_sandbox_contract.py tests/test_mcp_pool.py -q --timeout=60` returns 0 exit; collected = 135-137; passed ≥ 133; skipped ≤ 4.
7. **No prior file modifications**: `git diff /tmp/l3-baseline.diff` (against baseline captured at L3 start) shows changes ONLY to `the_one/mcp/__init__.py` (acquire re-export), `the_one/mcp/_pool.py` (new), and `tests/test_mcp_pool.py` (new). No changes to `the_one/mcp/client.py`, `the_one/mcp/transports/`, the L1a/L1b/L2 surfaces.
8. **Lint clean**: `docker compose exec the-one ruff check the_one/mcp/ tests/test_mcp_pool.py` returns 0 exit.
9. **Flight log updated**: `grep -A 8 "03-pool-primitives-worker-task" missions/07-mcp-integration/flights/04-idle-ttl-lifecycle/flight-log.md` shows a Leg Progress entry with status `landed`, started/completed timestamps, race-fix-test confirmation, and integration-test confirmation against real bwrap.

## Implementation Guidance

1. **Capture L3-start state**: `git diff > /tmp/l3-baseline.diff`. Capture per-file test counts (expected: `{59, 14, 13, 9, 17, 14}` for the six prior files; total 126 with 1 skipped).

2. **Run the L3-affected baseline**:
   ```bash
   docker compose exec the-one pytest tests/test_mcp_client.py tests/test_mcp_integration.py tests/test_mcp_sandbox_integration.py tests/test_mcp_stdio_sandbox.py tests/test_sandbox_bubblewrap.py tests/test_sandbox_contract.py -q --timeout=60
   ```
   Expect: 126 collected, 125 passed + 1 skipped.

3. **Create `the_one/mcp/_pool.py`**. Reference template: `the_one/tools/_session_registry.py`. Skeleton (the implementer adapts):

   ```python
   """MCP source pool — per-(agent, source) keyed worker-task-per-entry registry.

   Mirrors `the_one/tools/_session_registry.py` (PTY pool) at the structural
   level: module-level dict keyed on (agent_name, source_id); asyncio.Lock for
   serialized mutations; per-entry worker task that holds the SDK's
   anyio-task-group-rooted CMs on a SINGLE task — connect AND disconnect run
   on the same task, satisfying anyio's cross-task CancelScope guard
   (verified at L1a stake-test probe).

   F4 lands the pool in three legs:
     - L3 (this module): _RegistryEntry, _pool, _lock, _resolve_ttl_seconds,
       _load_source, _entry_worker, _evict, acquire, _clear_for_test.
     - L4: _reap_once, _reap_loop, _ensure_reaper_running_locked,
       shutdown_drain, FastAPI lifespan integration.
     - L5: the_one/mcp/README.md documents the runtime invariants.

   Public API (re-exported from `the_one.mcp`):
     - `acquire(agent_name, source_id) -> MCPClient` (this module)
     - `shutdown_drain() -> None` (L4)

   Internal symbols (underscore-prefixed; tests reach in for `_clear_for_test`
   and friends):
     - _RegistryEntry, _pool, _lock, _shutting_down
     - _DEFAULT_TTL_SECONDS, _REAPER_INTERVAL_SECONDS
     - _resolve_ttl_seconds, _load_source, _entry_worker, _evict
     - _clear_for_test
   """

   from __future__ import annotations

   import asyncio
   import contextlib
   import logging
   import os
   from dataclasses import dataclass, field

   from the_one.config import settings
   from the_one.db.connection import get_connection
   from the_one.db.models import MCPSource
   from the_one.db.repositories import MCPSourceRepository
   from the_one.encryption import get_encryptor
   from the_one.mcp.client import MCPClient

   logger = logging.getLogger(__name__)

   _DEFAULT_TTL_SECONDS = 300
   _REAPER_INTERVAL_SECONDS = 30.0  # Defined here for forward-reference; L4 wires the reaper.


   @dataclass
   class _RegistryEntry:
       """A pool entry. Holds connection state shared between the entry
       worker and any concurrent `acquire` callers waiting on `client_ready`.

       The worker task holds the SDK's anyio-task-group-rooted CMs for the
       entry's lifetime. The reaper (L4) signals eviction via `evict_event`;
       the worker's `finally:` runs disconnect on the SAME task that ran
       connect, avoiding anyio's cross-task __aexit__ guard.

       Worker is the SOLE writer of `client` and `failure`. Both are
       written BEFORE `client_ready.set()`, so post-event reads are
       race-free. `acquire` callers wait on `client_ready` and read the
       fields outside the lock.
       """

       ttl_seconds: int
       worker: asyncio.Task[None]
       evict_event: asyncio.Event
       client_ready: asyncio.Event
       client: MCPClient | None = None
       failure: BaseException | None = None


   _pool: dict[tuple[str, str], _RegistryEntry] = {}
   _lock: asyncio.Lock = asyncio.Lock()
   _shutting_down: bool = False


   def _resolve_ttl_seconds() -> int:
       """Read MCP_POOL_IDLE_TTL_SECONDS env at call time; default 300.

       Read at call time so test monkeypatch.setenv works. Mirrors the
       PTY pool's per-entry TTL resolution (also read at register time).
       """
       raw = os.environ.get("MCP_POOL_IDLE_TTL_SECONDS")
       if raw is None:
           return _DEFAULT_TTL_SECONDS
       try:
           return int(raw)
       except ValueError:
           logger.warning(
               "MCP_POOL_IDLE_TTL_SECONDS=%r is not an int; falling back to %d",
               raw,
               _DEFAULT_TTL_SECONDS,
           )
           return _DEFAULT_TTL_SECONDS


   async def _load_source(source_id: str) -> MCPSource:
       """Load an MCPSource by id from the F1 repository.

       Called OUTSIDE `_lock` so different-key acquires don't serialize
       on the F1 DB read. Per flight §3 / cycle-2 medium #2.

       Raises whatever the repo raises (typically KeyError on miss);
       the calling acquire propagates the exception to the caller.
       """
       conn = await get_connection()
       encryptor = get_encryptor(settings.data_dir)
       repo = MCPSourceRepository(conn, encryptor)
       return await repo.get(source_id)


   async def _entry_worker(source: MCPSource, entry: _RegistryEntry) -> None:
       """Hold the connection on a single task. Run teardown on same task.

       On connect-failure, populate `entry.failure` BEFORE setting
       `client_ready`. On connect-success, populate `entry.client` BEFORE
       setting `client_ready`. Then idle until `evict_event` fires; the
       `finally:` clause runs disconnect — anyio cross-task guard
       satisfied because connect and disconnect both run on this task.

       Memory ordering: `failure` / `client` written BEFORE
       `client_ready.set()`; asyncio's single-threaded event loop
       guarantees post-event reads on `acquire`'s side observe the
       writes. No memory barriers needed — there's no other thread.
       """
       client = MCPClient(source)
       try:
           await client.connect()
       except BaseException as exc:
           entry.failure = exc
           entry.client_ready.set()
           return
       entry.client = client
       entry.client_ready.set()
       try:
           await entry.evict_event.wait()
       finally:
           # Disconnect on the SAME task that ran connect — anyio guard
           # is satisfied. MCPClient.disconnect is idempotent and never
           # raises (post-L1a contract); the cross-task safety-net swallow
           # is documented but not exercised here.
           try:
               await client.disconnect()
           except Exception:
               logger.exception(
                   "MCPClient disconnect failed during entry teardown"
               )


   async def _evict(key: tuple[str, str]) -> None:
       """Pop the entry, signal the worker to teardown, await the worker.

       `await entry.worker` is REQUIRED for shutdown_drain (L4) to honour
       its 'all entries drained before return' contract. 10s timeout +
       cancel-on-stuck per flight §2.
       """
       async with _lock:
           entry = _pool.pop(key, None)
       if entry is None:
           return
       entry.evict_event.set()
       try:
           await asyncio.wait_for(entry.worker, timeout=10.0)
       except asyncio.TimeoutError:
           logger.warning(
               "MCP pool worker for %r did not terminate within 10s", key
           )
           entry.worker.cancel()
           with contextlib.suppress(BaseException):
               await entry.worker


   async def acquire(agent_name: str, source_id: str) -> MCPClient:
       """Look up or spawn the warm MCPClient for (agent, source).

       Per flight §2: pre-load source OUTSIDE the lock; check `entry is
       None` under the lock (atomic existence dispatch); wait on
       `entry.client_ready` outside the lock; on failure, raise and pop
       idempotently; on success, touch_activity and return.
       """
       # Pre-load OUTSIDE the lock (cycle-2 medium #2).
       source = await _load_source(source_id)

       async with _lock:
           if _shutting_down:
               raise RuntimeError("MCP pool is shutting down")
           entry = _pool.get((agent_name, source_id))
           if entry is None:
               # First-acquirer-for-this-key path. Spawn worker, insert entry.
               # Note: asyncio.create_task returns immediately; the worker
               # body runs on the next event-loop tick. We're under the
               # lock only for dict-mutation atomicity.
               entry = _RegistryEntry(
                   ttl_seconds=_resolve_ttl_seconds(),
                   worker=None,  # populated immediately below
                   evict_event=asyncio.Event(),
                   client_ready=asyncio.Event(),
               )
               entry.worker = asyncio.create_task(
                   _entry_worker(source, entry)
               )
               _pool[(agent_name, source_id)] = entry
           # else: entry exists. Wait on client_ready outside the lock.

       # Lock released. Concurrent same-key acquires now share entry.
       await entry.client_ready.wait()

       if entry.failure is not None:
           # Connect failed. Pop the entry idempotently (only if it's
           # still THIS entry — if a later acquire already replaced it
           # with a fresh worker, leave that one alone).
           async with _lock:
               existing = _pool.get((agent_name, source_id))
               if existing is entry:
                   _pool.pop((agent_name, source_id), None)
           raise entry.failure

       client = entry.client
       assert client is not None  # invariant: ready set + no failure → client populated
       client._touch_activity()
       return client


   async def _clear_for_test() -> None:
       """Test seam: cancel all worker tasks; empty the pool.

       Tests must call this in an autouse=True fixture AFTER each test;
       otherwise the next test inherits stale entries / worker tasks
       bound to a torn-down event loop. Resets `_shutting_down = False`.

       INVARIANT: do NOT call while another task is awaiting `acquire`
       on the same key — the awaiting task may receive the soon-to-be-
       disconnected client (post `client_ready` set, pre worker
       finally block running disconnect). The autouse fixture pattern
       runs cleanup AFTER the test body completes, which guarantees
       this in normal usage.
       """
       global _shutting_down

       async with _lock:
           snapshot = list(_pool.items())
           _pool.clear()
       for key, entry in snapshot:
           entry.evict_event.set()
           if not entry.worker.done():
               entry.worker.cancel()
           with contextlib.suppress(BaseException):
               await entry.worker

       _shutting_down = False
   ```

4. **Update `the_one/mcp/__init__.py`** to re-export `acquire`:

   ```python
   # ... existing imports ...
   from the_one.mcp._pool import acquire  # noqa: E402  (constants first per F2 contract)

   __all__ = [
       # ... existing entries ...
       "acquire",
   ]
   ```

   Add a `# L4 will add: shutdown_drain` comment near the import for forward-reference discipline.

5. **Create `tests/test_mcp_pool.py`**. Use `the_one.mcp._pool` as the import root (NOT `the_one.mcp` — tests need to reach internal symbols). Mirror the patterns from `tests/test_session_registry.py` if that exists; otherwise build fresh. Sketch:

   ```python
   """Tests for the_one/mcp/_pool.py — worker-task-per-entry pool primitives.

   Coverage:
     1. lazy-spawn-on-first-acquire  (uses mock MCPClient)
     2. warm-reuse-on-second-acquire
     3. concurrent-acquire-same-key-shares-one-worker  (cycle-2 race-fix lock)
     4. different-keys-spawn-independent-workers
     5. spawn-failure-propagates-from-worker  (MCPSandboxError, MCPConnectionError)
     6. spawn-failure-pop-is-idempotent
     7. acquire-cancellation-leaves-worker-running
     8. _load_source runs OUTSIDE the lock  (lock-acquire vs source-load order)
     9. _clear_for_test cancels workers and empties pool
    10. real-bwrap end-to-end (integration; @requires_bwrap)
    11. _evict primitive (integration; @requires_bwrap)
   """

   from __future__ import annotations

   import asyncio
   import contextlib
   import shutil
   import sys
   from pathlib import Path
   from typing import Any
   from unittest.mock import AsyncMock, MagicMock, patch

   import pytest

   from the_one.db.models import MCPSource
   from the_one.mcp import _pool as pool_mod
   from the_one.mcp._pool import acquire
   from the_one.mcp.errors import MCPConnectionError, MCPSandboxError
   from tests.fixtures.mcp.hello_server import make_mcp_app  # if needed

   _PROJECT_ROOT = Path(__file__).resolve().parent.parent
   requires_bwrap = pytest.mark.skipif(
       shutil.which("bwrap") is None,
       reason="bwrap required for real-subprocess integration tests",
   )


   # Autouse cleanup. The project uses pytest-asyncio in `auto` mode (verify
   # via `grep asyncio_mode pyproject.toml setup.cfg conftest.py` BEFORE
   # implementation — if `auto` is NOT set, switch to `@pytest_asyncio.fixture`).
   @pytest.fixture(autouse=True)
   async def _clear_pool_after_each_test():
       yield
       await pool_mod._clear_for_test()


   def _make_stub_source(source_id: str = "src-test", name: str = "test") -> MCPSource:
       return MCPSource(
           id=source_id,
           name=name,
           type="stdio",
           config={"command": "/bin/true", "args": [], "env": {}, "cwd": None},
           secrets={},
       )


   class _MockClient:
       """Stub MCPClient. Overrides connect/disconnect/_touch_activity.

       Subclass per scenario rather than mutating the base class's
       `_connect_impl` (cycle-1 reviewer flagged that class-attribute
       mutation between instantiations is fragile because __init__ binds
       `self._connect_impl` into an AsyncMock side_effect — late
       reassignment doesn't affect already-instantiated mocks).
       """

       _instance_count = 0

       def __init__(self, source):
           type(self)._instance_count += 1
           self.source = source
           self.is_alive = False
           self.connect = AsyncMock(side_effect=self._connect_impl)
           self.disconnect = AsyncMock(side_effect=self._disconnect_impl)
           self._touch_activity = MagicMock()

       async def _connect_impl(self):
           self.is_alive = True

       async def _disconnect_impl(self):
           self.is_alive = False


   @pytest.fixture
   def patch_client(monkeypatch):
       """Replace pool's MCPClient with the mock; reset instance counter.

       Returns the mock class so tests can read _instance_count. Tests
       requiring per-scenario behavior subclass _MockClient explicitly
       (see _SlowClient / _FailingClient / _RetryClient below).
       """
       _MockClient._instance_count = 0
       async def _patched_load_source(source_id):
           return _make_stub_source(source_id)
       monkeypatch.setattr(pool_mod, "MCPClient", _MockClient)
       monkeypatch.setattr(pool_mod, "_load_source", _patched_load_source)
       return _MockClient


   # ─────────────────────────────────────────────────────────────────
   # Test bodies — implement per §Outputs sketches
   # ─────────────────────────────────────────────────────────────────

   async def test_acquire_lazy_spawn_creates_worker_and_returns_client(patch_client):
       client = await acquire("agent-a", "src-1")
       assert isinstance(client, _MockClient)
       assert client.is_alive is True
       assert _MockClient._instance_count == 1
       client._touch_activity.assert_called_once()

   async def test_acquire_warm_reuse_returns_same_client_instance(patch_client):
       c1 = await acquire("agent-a", "src-1")
       c2 = await acquire("agent-a", "src-1")
       assert c1 is c2
       assert _MockClient._instance_count == 1
       assert c1._touch_activity.call_count == 2

   async def test_concurrent_acquire_same_key_shares_one_worker(monkeypatch):
       """Cycle-2 race-fix lock: 5 concurrent acquires for same key share ONE worker."""
       class _SlowClient(_MockClient):
           async def _connect_impl(self):
               await asyncio.sleep(0.05)
               self.is_alive = True

       _SlowClient._instance_count = 0
       async def _patched_load_source(source_id):
           return _make_stub_source(source_id)
       monkeypatch.setattr(pool_mod, "MCPClient", _SlowClient)
       monkeypatch.setattr(pool_mod, "_load_source", _patched_load_source)

       results = await asyncio.gather(*[
           acquire("agent-a", "src-1") for _ in range(5)
       ])
       assert _SlowClient._instance_count == 1
       assert all(r is results[0] for r in results)

   async def test_different_keys_spawn_independent_workers(patch_client):
       c1 = await acquire("agent-a", "src-1")
       c2 = await acquire("agent-b", "src-1")
       assert c1 is not c2
       assert _MockClient._instance_count == 2

   async def test_spawn_failure_propagates_to_acquire_callers(monkeypatch):
       async def _patched_load_source(source_id):
           return _make_stub_source(source_id)

       class _FailingClient(_MockClient):
           async def _connect_impl(self):
               raise MCPSandboxError("test sandbox failure")

       monkeypatch.setattr(pool_mod, "MCPClient", _FailingClient)
       monkeypatch.setattr(pool_mod, "_load_source", _patched_load_source)

       with pytest.raises(MCPSandboxError, match="test sandbox failure"):
           await acquire("agent-a", "src-1")

   async def test_spawn_failure_pop_is_idempotent_under_concurrent_acquires(monkeypatch):
       """Cycle-1 reviewer fix: TWO concurrent failure-observers don't double-pop."""
       calls = {"n": 0}
       async def _patched_load_source(source_id):
           return _make_stub_source(source_id)

       class _FailingThenRecoveringClient(_MockClient):
           async def _connect_impl(self):
               calls["n"] += 1
               if calls["n"] <= 2:
                   # First TWO instantiations fail (the gather'd pair, sharing
                   # one worker — actually only worker #1 fails; the second
                   # _instance_count increment comes from the retry below).
                   await asyncio.sleep(0.02)  # let both acquires queue
                   raise MCPConnectionError(f"attempt {calls['n']} fails")
               self.is_alive = True

       monkeypatch.setattr(pool_mod, "MCPClient", _FailingThenRecoveringClient)
       monkeypatch.setattr(pool_mod, "_load_source", _patched_load_source)

       # Two concurrent acquires on the SAME key; both should raise the SAME
       # MCPConnectionError instance (the worker's stored entry.failure).
       results = await asyncio.gather(
           acquire("agent-a", "src-1"),
           acquire("agent-a", "src-1"),
           return_exceptions=True,
       )
       assert all(isinstance(r, MCPConnectionError) for r in results)
       # Both observers got the SAME exception instance (worker's entry.failure
       # is a single object; both gather'd acquires re-raised it).
       assert results[0] is results[1]
       # Only ONE worker spawned (cycle-2 race-fix invariant); only ONE _MockClient.
       assert _FailingThenRecoveringClient._instance_count == 1
       # Entry was popped (idempotent — no KeyError despite both raising).
       assert ("agent-a", "src-1") not in pool_mod._pool

       # Retry: third acquire, fresh worker, succeeds.
       client = await acquire("agent-a", "src-1")
       assert client.is_alive
       assert _FailingThenRecoveringClient._instance_count == 2  # original failed + retry succeeded
       assert calls["n"] == 2  # connect attempts: first failed (count=1), retry succeeded (count=2). Wait, the gather'd pair ONLY made ONE connect call (shared worker), so calls["n"] is 2 after the retry, NOT 3.

   async def test_acquire_cancellation_leaves_worker_running(monkeypatch):
       """Caller cancellation mid-await leaves the worker running; subsequent acquire reuses it."""
       class _VerySlowClient(_MockClient):
           async def _connect_impl(self):
               await asyncio.sleep(1.0)
               self.is_alive = True

       _VerySlowClient._instance_count = 0
       async def _patched_load_source(source_id):
           return _make_stub_source(source_id)
       monkeypatch.setattr(pool_mod, "MCPClient", _VerySlowClient)
       monkeypatch.setattr(pool_mod, "_load_source", _patched_load_source)

       # First acquire times out (caller cancels via wait_for).
       # Verified against Python 3.12: asyncio.wait_for raises asyncio.TimeoutError
       # cleanly when the inner awaitable exceeds the timeout.
       with pytest.raises(asyncio.TimeoutError):
           await asyncio.wait_for(acquire("agent-a", "src-1"), timeout=0.05)

       # Entry is still in the pool; worker is still running.
       assert ("agent-a", "src-1") in pool_mod._pool
       entry = pool_mod._pool[("agent-a", "src-1")]
       assert entry.worker is not None
       assert not entry.worker.done()

       # Second acquire (un-cancelled) waits for the worker, gets the client.
       client = await acquire("agent-a", "src-1")
       assert client.is_alive
       assert _VerySlowClient._instance_count == 1  # one worker, one client

   async def test_load_source_runs_outside_the_lock(patch_client, monkeypatch):
       """Cycle-2 medium #2: different-key acquires must not serialize on the F1 DB read."""
       lock_held_during_load: list[bool] = []
       prior_load_source = pool_mod._load_source  # this is the _patched_load_source from patch_client

       async def _spy_load_source(source_id: str):
           lock_held_during_load.append(pool_mod._lock.locked())
           return await prior_load_source(source_id)

       monkeypatch.setattr(pool_mod, "_load_source", _spy_load_source)

       await acquire("agent-a", "src-1")
       # Stronger assertion: ALL invocations of _load_source ran outside the lock,
       # even if a future revision adds retry-on-miss or warm-up paths.
       assert lock_held_during_load and all(h is False for h in lock_held_during_load)

   async def test_clear_for_test_cancels_workers_and_empties_pool(patch_client):
       await acquire("agent-a", "src-1")
       await acquire("agent-a", "src-2")
       await acquire("agent-b", "src-1")
       assert len(pool_mod._pool) == 3

       await pool_mod._clear_for_test()
       assert pool_mod._pool == {}


   # ─────────────────────────────────────────────────────────────────
   # Integration tests — real bwrap subprocess
   # ─────────────────────────────────────────────────────────────────

   @requires_bwrap
   async def test_acquire_real_bwrap_end_to_end_with_strict_floor_profile(
       mcp_fixture_sandbox_profile,
       mcp_fixture_stdio_params,
   ) -> None:
       """End-to-end: pool spawns real bwrap-wrapped MCP server, list_tools succeeds."""
       # Build an MCPSource pointing at the in-repo hello fixture.
       source = MCPSource(
           id="src-l3-integration",
           name="hello-fixture",
           type="stdio",
           config={
               **mcp_fixture_stdio_params,
               "sandbox": {
                   "writable_paths": list(mcp_fixture_sandbox_profile.writable_paths),
                   "network_allowed": mcp_fixture_sandbox_profile.network_allowed,
               },
           },
           secrets={},
       )

       # Patch _load_source to return our test source rather than going through DB.
       async def _patched_load_source(source_id):
           assert source_id == source.id
           return source
       with patch.object(pool_mod, "_load_source", _patched_load_source):
           client = await acquire("test-agent", source.id)
           tools = await client.list_tools()
           assert len(tools) > 0


   @requires_bwrap
   async def test_acquire_then_evict_via_internal_helper(
       mcp_fixture_sandbox_profile,
       mcp_fixture_stdio_params,
   ) -> None:
       """_evict pops entry, runs disconnect on worker task, leaves pool empty.

       By the time `_evict`'s `await asyncio.wait_for(entry.worker, ...)`
       returns, the worker has fully completed its `finally:` block and
       `client.disconnect()` has run. The `is_alive is False` assertion
       below is race-free.
       """
       source = MCPSource(
           id="src-l3-evict",
           name="hello-fixture",
           type="stdio",
           config={
               **mcp_fixture_stdio_params,
               "sandbox": {
                   "writable_paths": list(mcp_fixture_sandbox_profile.writable_paths),
                   "network_allowed": mcp_fixture_sandbox_profile.network_allowed,
               },
           },
           secrets={},
       )
       async def _patched_load_source(source_id):
           return source
       with patch.object(pool_mod, "_load_source", _patched_load_source):
           client = await acquire("test-agent", source.id)
           assert client.is_alive
           assert ("test-agent", source.id) in pool_mod._pool

           await pool_mod._evict(("test-agent", source.id))

           assert ("test-agent", source.id) not in pool_mod._pool
           assert client.is_alive is False


   async def test_evict_idempotent_on_missing_key():
       """_evict on a key that was never inserted is a no-op (no raise).

       Locks the `if entry is None: return` guard against future regressions
       where someone "simplifies" the None check. Cheap canary; runs without
       bwrap because there's nothing to spawn.
       """
       # Pool starts empty (autouse fixture); the key has never been inserted.
       await pool_mod._evict(("never-inserted-agent", "never-inserted-src"))
       assert pool_mod._pool == {}
   ```

   Note the test sketches above are illustrative — the implementer adapts to the actual fixtures and signature shapes. The mocking approach (replace `pool_mod.MCPClient` and `pool_mod._load_source`) is the recommended pattern; it avoids the F1 DB and avoids real bwrap for unit tests.

6. **Run the L3 regression suite**:
   ```bash
   docker compose exec the-one pytest tests/test_mcp_client.py tests/test_mcp_integration.py tests/test_mcp_sandbox_integration.py tests/test_mcp_stdio_sandbox.py tests/test_sandbox_bubblewrap.py tests/test_sandbox_contract.py tests/test_mcp_pool.py -q --timeout=60
   ```
   Expect 138 collected; 137 passed; 1 skipped (only L2 #6c EPERM in dev container). If integration tests #10/#11 fail with EPERM-on-unshare, that indicates the dev container lost SYS_ADMIN — escalate via Adaptation Criteria.

   **Pre-flight check before step 5**: confirm `pytest-asyncio` is in `auto` mode by grepping `pyproject.toml` / `setup.cfg` / `conftest.py` for `asyncio_mode`. If it's not `auto`, switch the autouse fixture in step 5 to `@pytest_asyncio.fixture(autouse=True)` (and import `pytest_asyncio`). The leg sketch assumes `auto` mode — verify or adapt.

7. **Lint**:
   ```bash
   docker compose exec the-one ruff check the_one/mcp/ tests/test_mcp_pool.py
   ```

8. **Update the flight log** with status `landed`, ISO 8601 UTC timestamps, the new test count, the cycle-2 race-fix confirmation (test #3 passes), and the `@requires_bwrap` integration tests' status (passed in dev container, expected).

## Edge Cases

- **`_load_source` returning early-vs-late**: if `_load_source` is slow (DB round-trip), MULTIPLE concurrent acquires for the same key will each call `_load_source` independently — that's intentional. The lock is only held for the dict-mutation; the source loads happen in parallel. The first one through the lock spawns the worker; subsequent ones return early via `entry exists` and use the worker's loaded source. This means a slow DB returns N copies of the source for N callers; only the first one is consumed by the worker. Memory waste is negligible (small dataclass).
- **`MCPSourceRepository` raises `KeyError` on miss**: propagated as-is to the `acquire` caller. NOT wrapped as `MCPClientError`. F6 (the agent-loop consumer) handles this case at the call site.
- **`MCP_POOL_IDLE_TTL_SECONDS=0` or negative**: `_resolve_ttl_seconds` accepts whatever int is provided. Zero or negative means "evict on next reaper sweep" — the L4 reaper handles this. Document but don't error.
- **Worker task suppressed-cancellation**: `_clear_for_test` cancels the worker via `entry.worker.cancel()`; the worker's `try: await evict_event.wait()` gets a `CancelledError`; the `finally:` runs `client.disconnect()`. `MCPClient.disconnect` is idempotent and never raises (post-L1a). The `with contextlib.suppress(BaseException): await worker` catches the CancelledError. Clean.
- **Worker task that fails inside `disconnect`** (post-success path): the `finally:` block has its own `try/except Exception: logger.exception(...)`. A truly catastrophic disconnect (e.g., out-of-memory) still propagates; the test seam handles it via suppress.
- **Race between `_clear_for_test` and a concurrent `acquire`**: if a test fixture calls `_clear_for_test` while another test task is mid-`acquire`, the `acquire` may complete with a torn-down `_pool`. Tests must not run concurrent acquires across test boundaries; the autouse fixture pattern ensures isolation.
- **`shutdown_drain` not yet implemented**: `_shutting_down` is read by `acquire` (raise RuntimeError if True) but never set in this leg. L4 sets it. Test #9 (`test_clear_for_test`) implicitly resets it — ensures no leak between tests.
- **`acquire`-after-cancel rejoin**: if caller A cancels mid-acquire and caller B reuses the same key, B reads the entry that A left in `_pool` and shares the worker. NOT a leak; mirrored from test #7's behavior.

## Files Affected

- `the_one/mcp/_pool.py` (new) — pool primitives per §Outputs.
- `the_one/mcp/__init__.py` — add `acquire` import + `__all__` entry; comment forward-referencing L4's `shutdown_drain`.
- `tests/test_mcp_pool.py` (new) — 9-11 tests.
- `missions/07-mcp-integration/flights/04-idle-ttl-lifecycle/flight-log.md` — append Leg Progress entry.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`. Do NOT commit.**

- [ ] All acceptance criteria verified
- [ ] `pytest tests/test_mcp_client.py tests/test_mcp_integration.py tests/test_mcp_sandbox_integration.py tests/test_mcp_stdio_sandbox.py tests/test_sandbox_bubblewrap.py tests/test_sandbox_contract.py tests/test_mcp_pool.py -q --timeout=60` green
- [ ] `ruff check the_one/mcp/ tests/test_mcp_pool.py` clean
- [ ] Flight log Leg Progress entry added (status `landed`, timestamps, test counts, race-fix-test confirmation, integration-test confirmation)
- [ ] Set this leg's status to `landed` (header at top of this file)
- [ ] Check off this leg in flight.md (the `[ ] 03-pool-primitives-worker-task` line)
- [ ] Do NOT commit. Do NOT signal `[COMPLETE:leg]`. Signal `[HANDOFF:review-needed]` and stop.

---

## Citation Audit

7 citations verified against current code at leg design time (2026-05-07).

- `the_one/tools/_session_registry.py` (entire module) — structural template; mirrored in `_pool.py`. **OK**.
- `the_one/db/repositories.py:247-330` (`MCPSourceRepository.get`) — async method raising `KeyError` on miss. **OK**.
- `the_one/interfaces/web/api.py:55-58` (`_mcp_repo` factory) — `conn = await get_connection(); encryptor = get_encryptor(settings.data_dir); return MCPSourceRepository(conn, encryptor)`. **OK**, mirrored by `_load_source`.
- `the_one/mcp/__init__.py` (current `__all__` content) — does NOT include `acquire`; will be extended in this leg. **OK**.
- `the_one/mcp/client.py::MCPClient` (post-L1a contract: idempotent disconnect, AsyncExitStack-based connect/disconnect, never raises from disconnect) — **OK**, working-tree includes uncommitted L1a changes.
- `the_one/mcp/transports/stdio.py::connect_stdio` (post-L2: `MCPSandboxError` translation via `errlog=` capture) — **OK**, working-tree includes uncommitted L2 changes; L3's failure-propagation tests rely on this surface.
- F3 fixture `mcp_fixture_sandbox_profile` (in `tests/conftest.py`) — strict-floor `SandboxProfile`; consumed by integration tests in this leg, resolving the F3 dead-code flag.
