# Leg: 01a-async-exit-stack-and-cross-task-safety

**Status**: completed
**Flight**: [Idle-TTL Lifecycle](../flight.md)

## Objective

Refactor `MCPClient` from manual `__aenter__` / `__aexit__` calls on its transport CM to a single `contextlib.AsyncExitStack` owned by the client, while preserving the existing cross-task safety-net swallow at `the_one/mcp/client.py::disconnect` as the documented contract for cross-task accidents — and add a stake-test probe (committed as regression tests) that mechanically locks the same-task / cross-task / worker-task contract before any pool work begins.

> **Scope-reduction deviation (Flight Director runtime decision, 2026-05-07)**: this leg originally also rewrote `connect_stdio` / `connect_streamable_http` from `@asynccontextmanager` to non-CM `(session, stack)` returns. That change was abandoned at implementation time because 9 prior tests directly consume those helpers as async-CMs (8 in `tests/test_mcp_stdio_sandbox.py` + 1 in `tests/test_mcp_client.py`), violating AC #8's "all prior tests pass UNMODIFIED" invariant. F4 L3's worker-task pattern wraps `MCPClient.connect/disconnect` (NOT the transport helpers), so transport API shape is opaque to L3 — the original refactor was design-elegance, not load-bearing. See flight log §"L1a runtime deviation — transport-API scope reduced (2026-05-07)" for full rationale. **The transport modules (`stdio.py`, `streamable_http.py`) and the `_transport_connect` dispatcher are UNCHANGED in this leg.**

## Context

### Flight design decisions

- **§5 (AsyncExitStack refactor)**: the `connect_stdio` and `connect_streamable_http` helpers switch from nested `@asynccontextmanager` + `async with` to non-CM functions returning `(session, AsyncExitStack)`. `MCPClient.connect()` stores `self._transport_stack`; `MCPClient.disconnect()` calls `await self._transport_stack.aclose()`. The same-task usage (`async with MCPClient(source) as c:`) is fully clean.
- **§2-detail (why a worker task per entry, not just AsyncExitStack)**: `mcp.client.stdio.stdio_client` and `mcp.shared.session.BaseSession.__aenter__` both wrap their bodies in `anyio.create_task_group()`. anyio's `CancelScope.__aexit__` raises `RuntimeError("Attempted to exit cancel scope in a different task than it was entered in")` on cross-task exit. **AsyncExitStack alone does NOT solve cross-task** — `stack.aclose()` still invokes registered exit functions on the calling task. F4's pool (L3) uses a worker-task-per-entry pattern; L1a's stake-test probe verifies that pattern runs cross-task evict WITHOUT triggering the safety net.
- **§5 (safety net disposition)**: `client.py::disconnect`'s `except Exception: logger.warning("MCPClient transport close failed", exc_info=True)` swallow STAYS — the comment is renamed from "F2 noise" to "cross-task safety net (real fix is the F4 pool's worker-task pattern, not AsyncExitStack)". L1a regression tests lock the contract: same-task disconnect does NOT trigger it; cross-task disconnect DOES trigger it (and logs); the worker-task pattern from L3 does NOT trigger it (because the worker runs disconnect on its own task).

### Carries forward from prior flights

- F2 debrief Recommendation #1 (deferred to F4 per disposition): AsyncExitStack refactor.
- F3 had no related anomalies on this path. The `_transport_cm` field that L1a renames to `_transport_stack` was introduced in F2 L2 (`MCPClient.__init__`).
- F2 L2's existing test `tests/test_mcp_client.py::test_disconnect_swallows_close_errors` (lines 388-407) already exercises the swallow via a `monkeypatch.setattr(client_mod, "_transport_connect", ...)` path. **The L1a refactor preserves `_transport_connect`'s outward shape (still `@asynccontextmanager` yielding a session)** so this test passes unmodified — `_transport_connect`'s internals change to call the new non-CM transport helpers via an `AsyncExitStack`, but its public surface is preserved.

### Why this leg lands first (before L1b, L2, L3, L4)

L3's `_entry_worker` (the §2 worker-task pattern) depends on a `disconnect()` that does NOT raise spurious `RuntimeError: generator didn't stop` from cross-task `__aexit__`. The existing F2 swallow already absorbs that, but the pool will exercise the path constantly under reaper-driven evictions. L1a's stake-test probe verifies experimentally that the worker-task-per-entry shape (not AsyncExitStack alone) is the actual cross-task-safe pattern, BEFORE L3 commits to it. If the probe fails (Adaptation Criteria divert path), L3 design must escalate to user before proceeding.

## Inputs

What exists before this leg runs:

- `the_one/mcp/client.py` exists with `MCPClient.__init__` setting `self._transport_cm: Any = None` (line 134); `connect()` calling `self._transport_cm = _transport_connect(self.source); session = await self._transport_cm.__aenter__()` (lines 187-188); `_cleanup_after_failed_connect()` calling `await self._transport_cm.__aexit__(None, None, None)` (line 235); `disconnect()` calling `await self._transport_cm.__aexit__(None, None, None)` with `except Exception: logger.warning("MCPClient transport close failed", exc_info=True)` swallow (lines 254-257).
- `the_one/mcp/transports/stdio.py::connect_stdio` is `@asynccontextmanager` using nested `async with stdio_client(params) as (read, write): async with ClientSession(read, write) as session: yield session` (lines 166-190).
- `the_one/mcp/transports/streamable_http.py::connect_streamable_http` is `@asynccontextmanager` using triply-nested `async with httpx.AsyncClient(...) as owned_client: async with streamable_http_client(...) as (read, write, _): async with ClientSession(read, write) as session: yield session` for the production path, and a similar two-level shape for the test-injected-client path (lines 55-110).
- `the_one/mcp/client.py::_transport_connect` dispatcher (`@asynccontextmanager`, lines 57-88) selects on `source.type` and yields a session.
- F2 + F3 tests pass at the L1a-start baseline. Live counts as of 2026-05-07 (re-baselined twice — first per design-review cycle 1, then per Developer's actual measurement at implementation start; the second correction caught two new tests that had landed on `tests/test_sandbox_bubblewrap.py` between F3 design and L1a start):
  - `tests/test_mcp_client.py`: 54 tests
  - `tests/test_mcp_integration.py`: 14 tests
  - `tests/test_mcp_sandbox_integration.py`: 10 tests
  - `tests/test_mcp_stdio_sandbox.py`: 9 tests
  - `tests/test_sandbox_bubblewrap.py`: **16 tests** (was cited as 14 in pre-implementation revisions; corrected at implementation-time measurement)
  - `tests/test_sandbox_contract.py`: 14 tests
  - **Total prior tests in scope: 117.** Post-L1a target: 117 + 5 required new (+ up to 1 optional) = 122-123. F4 net-new estimate (across L1a-L4) re-anchors on this baseline.
- `tests/test_mcp_client.py::test_disconnect_swallows_close_errors` (lines 388-407) patches `client_mod._transport_connect` to a custom `@asynccontextmanager` that raises on `__aexit__`. This test must continue to pass unmodified.
- 9 prior tests consume `connect_stdio` / `connect_streamable_http` directly as async-CMs (8 in `tests/test_mcp_stdio_sandbox.py` calling `async with connect_stdio(source) as session:`; 1 in `tests/test_mcp_client.py::TestConnectStreamableHttpProduction` calling `async with sh.connect_streamable_http(source):`). **L1a's scope-reduction (Objective deviation note) preserves the CM shape of these helpers so all 9 callers remain unmodified.**

## Outputs

What exists after this leg completes:

- `the_one/mcp/client.py`:
  - Field rename: `self._transport_cm: Any = None` → `self._transport_stack: AsyncExitStack | None = None`. Import line on `client.py:18` extended from `from contextlib import asynccontextmanager` to `from contextlib import AsyncExitStack, asynccontextmanager`.
  - `connect()` builds the stack via `self._transport_stack = await AsyncExitStack().__aenter__(); session = await self._transport_stack.enter_async_context(_transport_connect(self.source))`. The `_transport_connect` dispatcher is **unchanged** — it remains an `@asynccontextmanager` consuming the existing CM-shaped transport helpers, exactly as in F2.
  - `disconnect()` and `_cleanup_after_failed_connect()` switch from `await self._transport_cm.__aexit__(None, None, None)` to `await self._transport_stack.aclose()`. The `except Exception: logger.warning("MCPClient transport close failed", exc_info=True)` swallow STAYS with renamed comment: `# Cross-task safety net (the real fix for cross-task disconnect is the F4 pool's worker-task pattern, not AsyncExitStack — see flight 04 design §2-detail).`
  - The dead `yield  # type: ignore[unreachable]` line at the bottom of `_transport_connect` (lines 86-88) — kept in F2 only as a workaround for `@asynccontextmanager`'s yield requirement — is preserved unchanged. (The original L1a design proposed deleting it as part of the dispatcher rewrite; the scope-reduction makes the dispatcher rewrite unnecessary, so the dead yield stays.)
- `the_one/mcp/transports/stdio.py` — **UNCHANGED in this leg** (scope-reduction deviation per Objective). The leg originally rewrote `connect_stdio` to a non-CM helper; that change is reverted to preserve the 8 prior tests in `tests/test_mcp_stdio_sandbox.py` that consume it as `async with connect_stdio(source) as session:`. F4 L3's worker-task pattern wraps `MCPClient.connect/disconnect` (not transport helpers), so transport API shape is opaque to L3.
- `the_one/mcp/transports/streamable_http.py` — **UNCHANGED in this leg** (scope-reduction deviation per Objective). The leg originally rewrote `connect_streamable_http` to a non-CM helper; that change is reverted to preserve the 1 prior test in `tests/test_mcp_client.py::TestConnectStreamableHttpProduction` that consumes it as `async with sh.connect_streamable_http(source):`.
- `the_one/mcp/client.py::_transport_connect` — **UNCHANGED in this leg**. The F2 dispatcher already uses `async with connect_stdio(source) as session:` / `async with connect_streamable_http(source) as session:` and yields the session; this composes correctly with `MCPClient`'s new outer `AsyncExitStack` (the dispatcher is the single CM that the outer stack owns).
- `tests/test_mcp_client.py` gains 5-6 new tests in a new `TestAsyncExitStackContract` class. To make the cross-task and worker-task tests genuinely exercise anyio's cancel-scope guard (not just simulate its error message), the class introduces a small `_anyio_task_group_cm` helper context-manager that wraps its body in a real `anyio.create_task_group()`; mocks for these tests use this helper as the transport CM body so `__aexit__` actually invokes anyio's `CancelScope.__aexit__` and triggers the real `RuntimeError` on cross-task exit.
  - `test_same_task_disconnect_no_safety_net_log`: real-anyio mock; same-task `async with MCPClient(source) as c:` produces NO `WARNING` log.
  - `test_cross_task_disconnect_logs_via_safety_net`: real-anyio mock; `MCPClient.connect()` runs on task A; `MCPClient.disconnect()` runs on task B (via `asyncio.create_task` + handoff). Anyio's actual cross-task guard fires inside `stack.aclose()`; the cross-task safety net swallow catches it. `caplog` asserts exactly one `WARNING` record matches `"MCPClient transport close failed"`.
  - `test_worker_task_pattern_no_safety_net_log`: real-anyio mock; reproduces the L3 worker-task shape (a single `asyncio.Task` runs `await client.connect(); await evict_event.wait()` then `finally: await client.disconnect()`; main task signals `evict_event.set()` and awaits the worker). Because connect AND disconnect run on the same task, anyio's guard is satisfied; the swallow is NOT triggered. This is the experimental verification that L3's worker-task-per-entry pattern actually circumvents the guard against a real anyio task group — not just a mocked error string.
  - `test_connect_failure_runs_stack_aclose`: a connect-failure path (e.g., `session.initialize` raises) calls `await self._transport_stack.aclose()` exactly once via `_cleanup_after_failed_connect`; the stack is reset to None. Spy mechanism: `unittest.mock.patch.object(contextlib.AsyncExitStack, "aclose", autospec=True)` scoped to a single test via context-manager `with` form (NOT module-level monkeypatch — prevents leakage between tests).
  - `test_disconnect_idempotent_with_stack`: parallel to existing `test_disconnect_idempotent`, but covers FOUR scenarios: (a) never-connected disconnect is a no-op; (b) connect → disconnect → disconnect is a no-op on the second; (c) connect → disconnect → connect → disconnect succeeds and the second `_transport_stack` is a fresh `AsyncExitStack` instance (`id(stack_first) != id(stack_second)`); (d) post-`_cleanup_after_failed_connect`, `c.is_alive is False` AND `c._transport_stack is None` AND `c._session is None`.
  - (optional) `test_subprocess_cleanup_via_proc_inspection`: integration test using `mcp_fixture_stdio_params` — confirms after `MCPClient.disconnect()` the spawned subprocess is gone (`/proc/{pid}` raises `FileNotFoundError`). Marker: `@pytest.mark.skipif(not Path("/proc").is_dir(), reason="Linux-only /proc inspection")`. Drop the previously-listed optional `test_streamable_http_owned_client_closed_on_disconnect` test — the test-path can't exercise the production branch and the rephrased "spy on stack aclose" duplicates `test_connect_failure_runs_stack_aclose`.
- All 117 prior tests across the F2/F3 surface (per the §Inputs re-baseline) pass UNMODIFIED. The existing `test_disconnect_swallows_close_errors` continues to work because `_transport_connect` is unchanged. The 9 prior tests that consume `connect_stdio` / `connect_streamable_http` directly as async-CMs continue to work because both helpers are unchanged.
- A stake-test probe script committed as a comment block at the top of the new `TestAsyncExitStackContract` class in `tests/test_mcp_client.py`, per F2 debrief KL #1: "flight-design Phase 1b reconnaissance should run a 10-line 'does this actually work' probe when integration tests stake on a specific SDK pattern". The comment block names the four observable invariants (1) same-task no-warn, (2) cross-task warns via safety net, (3) worker-task pattern no-warn, (4) `aclose()` is idempotent under double-call — and points to the test methods that lock each.
- `pytest tests/test_mcp_*.py -v` is green; `ruff check the_one/mcp/ tests/test_mcp_*.py` is clean (no NEW errors vs baseline).

## Acceptance Criteria

- [ ] `the_one/mcp/client.py::MCPClient` no longer has a `_transport_cm` attribute; instead has `self._transport_stack: AsyncExitStack | None = None` initialized in `__init__`. Import on `client.py:18` extended to include `AsyncExitStack`.
- [ ] `MCPClient.connect()` enters the stack via `self._transport_stack = await AsyncExitStack().__aenter__()` then calls `await self._transport_stack.enter_async_context(_transport_connect(self.source))` to obtain the session.
- [ ] `MCPClient.disconnect()` calls `await self._transport_stack.aclose()` instead of `await self._transport_cm.__aexit__(None, None, None)`. The `except Exception: logger.warning("MCPClient transport close failed", exc_info=True)` swallow remains, with the comment renamed to call out its cross-task-safety-net role and reference flight 04 §2-detail.
- [ ] `MCPClient._cleanup_after_failed_connect()` calls `await self._transport_stack.aclose()` (best-effort, with `try: ... except Exception: logger.debug(..., exc_info=True)` matching the existing pattern at lines 233-237).
- [ ] **`the_one/mcp/transports/stdio.py` is unchanged** (scope-reduction deviation per Objective). `connect_stdio` remains an `@asynccontextmanager`.
- [ ] **`the_one/mcp/transports/streamable_http.py` is unchanged** (scope-reduction deviation per Objective). `connect_streamable_http` remains an `@asynccontextmanager`.
- [ ] **`the_one/mcp/client.py::_transport_connect` (the dispatcher) is unchanged.** Its `@asynccontextmanager` outward shape AND its internal nested `async with` over the transport helpers are both preserved; `tests/test_mcp_client.py::test_disconnect_swallows_close_errors` continues to pass unmodified.
- [ ] All 117 prior F2 + F3 tests pass UNMODIFIED. Specifically, `pytest tests/test_mcp_client.py tests/test_mcp_integration.py tests/test_mcp_sandbox_integration.py tests/test_mcp_stdio_sandbox.py tests/test_sandbox_bubblewrap.py tests/test_sandbox_contract.py -q` returns per-file counts {54, 14, 10, 9, 16, 14} for the prior tests (new tests on `tests/test_mcp_client.py` add 5-6 on top, for a post-L1a total of 122-123).
- [ ] At least 5 new tests exist in `tests/test_mcp_client.py::TestAsyncExitStackContract` covering: (a) same-task no-warn, (b) cross-task DOES warn via safety net **with anyio's REAL cross-task `CancelScope.__aexit__` guard firing** (not a string-equal mocked RuntimeError), (c) worker-task pattern no-warn against a real `anyio.create_task_group()`, (d) connect-failure runs `aclose` (spy records `>= 1` invocation against the outer `_transport_stack`; the load-bearing observation is the post-cleanup state — `_transport_stack is None`, `_session is None`, `_is_alive is False`), (e) `disconnect()` is idempotent with the new stack field across the four scenarios in §Outputs (never-connected, double-disconnect, reconnect-after-disconnect with FRESH live-ref identity check `c._transport_stack is not stack_first` — NOT id-comparison, since CPython recycles ids of GC'd objects, post-cleanup-after-failed-connect state). One additional optional test may exist (subprocess `/proc` inspection; Linux-only marker).
- [ ] After `_cleanup_after_failed_connect` runs, `c.is_alive is False` AND `c._transport_stack is None` AND `c._session is None` — locked by `test_disconnect_idempotent_with_stack` scenario (d).
- [ ] A stake-test probe comment block is committed at the top of `TestAsyncExitStackContract` documenting the four invariants and naming each test method that locks them (per F2 debrief KL #1).
- [ ] `ruff check the_one/mcp/ tests/test_mcp_*.py` produces no NEW errors versus baseline.
- [ ] Flight log Leg Progress entry added with: (a) net new test count, (b) confirmation of zero regressions in F2/F3 prior tests, (c) confirmation that the cross-task probe behavior matches the documented contract, (d) any deviations or anomalies encountered.

## Verification Steps

How to confirm each criterion is met:

1. **Field rename**: `grep -n "_transport_cm" the_one/mcp/client.py` returns NO matches; `grep -n "_transport_stack" the_one/mcp/client.py` returns matches in `__init__`, `connect`, `disconnect`, and `_cleanup_after_failed_connect`.
2. **Stack-based connect**: `grep -n "enter_async_context\|AsyncExitStack" the_one/mcp/client.py` shows the stack construction and `enter_async_context` call.
3. **Safety-net comment renamed**: `grep -B1 -A1 "MCPClient transport close failed" the_one/mcp/client.py` shows a comment containing `cross-task safety net` and a reference to flight 04 §2-detail.
4. **Transport modules unchanged**: `git diff <l1a-start-sha> -- the_one/mcp/transports/stdio.py the_one/mcp/transports/streamable_http.py` shows no output (zero diff). Both `connect_stdio` and `connect_streamable_http` remain `@asynccontextmanager`-decorated.
5. **Dispatcher unchanged**: `git diff <l1a-start-sha> -- the_one/mcp/client.py | grep -A 30 "_transport_connect"` shows no functional changes inside `_transport_connect` (only changes are to `MCPClient` methods elsewhere in `client.py`).
6. **Regression tests unmodified**: against the L1a-start commit (capture via `git rev-parse HEAD` BEFORE the first L1a edit; do NOT use `main` — the flight branch already diverged), `git diff <l1a-start-sha> -- tests/test_mcp_client.py tests/test_mcp_integration.py tests/test_mcp_sandbox_integration.py tests/test_mcp_stdio_sandbox.py tests/test_sandbox_bubblewrap.py tests/test_sandbox_contract.py | grep -E '^-[^-]' | wc -l` shows changes only to ADD the new `TestAsyncExitStackContract` class (and the `_anyio_backed_transport_cm` helper near `_mock_transport_cm`) — no deletions or modifications of existing test methods.
7. **All tests green**: `cd ~/projects/the-one && docker compose exec the-one pytest tests/test_mcp_client.py tests/test_mcp_integration.py tests/test_mcp_sandbox_integration.py tests/test_mcp_stdio_sandbox.py tests/test_sandbox_bubblewrap.py tests/test_sandbox_contract.py -q --timeout=30` returns 0 exit; counts: 117 prior + 5 required new (+1 optional `/proc` test if included) = 122-123 passed.
8. **Cross-task warning observed**: `pytest tests/test_mcp_client.py::TestAsyncExitStackContract::test_cross_task_disconnect_logs_via_safety_net -v --log-cli-level=WARNING` shows `WARNING ... MCPClient transport close failed` in captured logs.
9. **Worker-task pattern silent**: `pytest tests/test_mcp_client.py::TestAsyncExitStackContract::test_worker_task_pattern_no_safety_net_log -v --log-cli-level=WARNING` shows NO `WARNING` log for the swallow message.
10. **Lint clean**: `cd ~/projects/the-one && docker compose exec the-one ruff check the_one/mcp/ tests/test_mcp_client.py` returns 0 exit with no new findings vs `git stash; ruff check ...; git stash pop` baseline.
11. **Flight log updated**: `grep -A 8 "L1a-async-exit-stack\|01a-async-exit-stack" missions/07-mcp-integration/flights/04-idle-ttl-lifecycle/flight-log.md` shows a Leg Progress entry with status `landed` (NOT `completed` — the flight-final commit transitions it later), started/completed timestamps, summary of changes, the test-count reconciliation, and the per-test-method invariant mapping (which test locks each of the four observable invariants).

## Implementation Guidance

Work in this order. Each step has a concrete output you can inspect before moving on.

1. **Run the F2/F3 baseline test suite to capture pre-refactor counts.**
   ```bash
   cd ~/projects/the-one
   docker compose exec the-one pytest tests/test_mcp_client.py tests/test_mcp_integration.py \
       tests/test_mcp_sandbox_integration.py tests/test_mcp_stdio_sandbox.py \
       tests/test_sandbox_bubblewrap.py tests/test_sandbox_contract.py -q --timeout=30 \
       2>&1 | tee /tmp/l1a_baseline.txt
   ```
   Note the count per file (expected: 54 + 14 + 10 + 9 + 16 + 14 = 117). These are the regression-invariants for AC #6 and #7. (Use `tests/test_sandbox_contract.py` — `tests/test_sandbox_runtime.py` does NOT exist in this repo. `tests/test_sandbox_bubblewrap.py` is 16 tests, not the 14 cited in earlier revisions of this artifact.)

2-4. **(Steps 2-4 from earlier leg revisions are dropped per the scope-reduction deviation in §Objective.)** Transport modules `the_one/mcp/transports/stdio.py` and `the_one/mcp/transports/streamable_http.py` are NOT modified. The `_transport_connect` dispatcher in `the_one/mcp/client.py` is NOT modified. Skip directly to step 5 (the only structural source-code change in this leg). The historical reasoning for those steps is preserved in the §"L1a runtime deviation" entry of the flight log.

5. **Rewrite `MCPClient.__init__`, `connect`, `_cleanup_after_failed_connect`, `disconnect`** to use an `AsyncExitStack`. This is the ONLY source-code change in this leg.

   Extend the existing import on line 18 from `from contextlib import asynccontextmanager` to `from contextlib import AsyncExitStack, asynccontextmanager` (matches the style L1a proposes for the transport modules; avoids mixed `contextlib.X` vs `from contextlib import X` styles). Then:

   ```python
   # In __init__:
   self._transport_stack: AsyncExitStack | None = None
   # (Replaces self._transport_cm: Any = None at line 134.)

   # In connect():
   try:
       async with asyncio.timeout(self.timeout_seconds):
           # Single-line construction-and-enter to make the "stack is always
           # entered when assigned" invariant locally obvious. AsyncExitStack
           # objects survive __aenter__ — it returns self — so this is the
           # canonical idiom.
           self._transport_stack = await AsyncExitStack().__aenter__()
           session = await self._transport_stack.enter_async_context(
               _transport_connect(self.source)
           )
           self._session = session
           try:
               result = await session.initialize()
           except RuntimeError as e:
               # ... existing translation unchanged
   ```

   ```python
   async def _cleanup_after_failed_connect(self) -> None:
       """Best-effort teardown of partial state from a failed connect()."""
       try:
           if self._transport_stack is not None:
               await self._transport_stack.aclose()
       except Exception:
           logger.debug("transport cleanup raised; suppressing", exc_info=True)
       self._transport_stack = None
       self._session = None
   ```

   ```python
   async def disconnect(self) -> None:
       """Idempotent teardown. Never raises — F4-pool contract.

       (existing F4-pool concurrency note unchanged)
       """
       if not self._is_alive and self._transport_stack is None:
           return
       self._is_alive = False
       try:
           if self._transport_stack is not None:
               await self._transport_stack.aclose()
       except Exception:
           # Cross-task safety net — the real fix for cross-task disconnect
           # is the F4 pool's worker-task pattern, NOT AsyncExitStack
           # (anyio's cancel-scope guard fires on cross-task __aexit__
           # regardless of how the CM is wrapped). See flight 04 design
           # §2-detail. This swallow remains intentionally; pool callers
           # use _pool._entry_worker (F4 L3) which runs disconnect on the
           # same task that ran connect, never tripping this branch.
           logger.warning("MCPClient transport close failed", exc_info=True)
       finally:
           self._transport_stack = None
           self._session = None
           self._tools_cache = None
   ```

   The state-preservation comment (`Preserve _capabilities, _protocol_version, _last_activity for the F4 pool — once disconnected they're stale but not invalid.`) at the bottom of `disconnect`'s `finally` block stays.

6. **Add the new `TestAsyncExitStackContract` test class** to `tests/test_mcp_client.py`. Place it AFTER the existing `TestMCPClientLifecycle` class (line 270 in the current file — verified at design 2026-05-06; do NOT use `TestMCPClientConnect`, which does not exist in this repo).

   **Critical**: the cross-task and worker-task tests must exercise a REAL `anyio.create_task_group()` so anyio's `CancelScope.__aexit__` guard fires for real on cross-task exit. A mock that simulates the RuntimeError string would only test the swallow's `except Exception:` branch — proving nothing about the SDK-level invariant L3's worker-task pattern depends on. Build this `_AnyioTaskGroupMockSession` helper at module scope (placed near the existing `mock_session` fixture):

   ```python
   import anyio
   from contextlib import asynccontextmanager

   @asynccontextmanager
   async def _anyio_backed_transport_cm(session_double):
       """Transport CM whose body holds a real anyio task group.

       Used by L1a stake-test probes to ensure cross-task __aexit__
       trips anyio's CancelScope guard for real (vs simulating it via
       a string-equal RuntimeError). The session_double argument is
       the existing mock_session — the body just yields it; the
       anyio task group is what makes the guard fire when __aexit__
       runs on a different task than __aenter__.
       """
       async with anyio.create_task_group():
           yield session_double
   ```

   Then in tests, monkeypatch `client_mod._transport_connect` to a `lambda source: _anyio_backed_transport_cm(mock_session)`. This means `MCPClient.connect()` enters this CM via the stack; `MCPClient.disconnect()`'s `stack.aclose()` exits it. If the exit happens on a different task than the entry, anyio's guard raises `RuntimeError("Attempted to exit cancel scope in a different task...")` for real — caught by the safety-net swallow.

   Include the stake-test probe comment block at the top of the class:

   ```python
   class TestAsyncExitStackContract:
       """Stake-test probe + regression suite for the L1a AsyncExitStack
       refactor.

       Locks the four observable invariants of the disconnect contract:

       1. Same-task disconnect (the canonical ``async with MCPClient(s) as c:``
          pattern) produces NO ``WARNING`` log line — anyio guard not
          triggered, swallow not invoked. Lock: ``test_same_task_disconnect_no_safety_net_log``.

       2. Cross-task disconnect (``MCPClient`` constructed on task A,
          ``disconnect()`` awaited on task B) DOES log via the cross-task
          safety net — anyio guard fires from inside ``stack.aclose()``,
          swallow catches the ``RuntimeError``. Lock: ``test_cross_task_disconnect_logs_via_safety_net``.

       3. Worker-task-per-entry pattern (the F4 L3 pool shape: a worker
          task holds connect, awaits an evict_event, then runs disconnect
          in its ``finally`` — connect AND disconnect on the same task)
          produces NO ``WARNING`` log. This is the experimental verification
          that L3's chosen pattern actually circumvents the anyio guard.
          Lock: ``test_worker_task_pattern_no_safety_net_log``.

       4. Stack ``aclose()`` is idempotent under double-call and after
          connect failure. Locks: ``test_connect_failure_runs_stack_aclose``,
          ``test_disconnect_idempotent_with_stack``.

       Per F2 debrief KL #1: when integration tests stake on a specific
       SDK pattern, commit a stake-test probe as a regression test so
       future maintainers can mechanically re-verify the contract.
       """

       async def test_same_task_disconnect_no_safety_net_log(
           self, patch_transport, mock_session, caplog
       ) -> None:
           # ... implementation
           ...
   ```

   Test bodies (sketch):

   - **`test_same_task_disconnect_no_safety_net_log`**: monkeypatch `client_mod._transport_connect` to `lambda source: _anyio_backed_transport_cm(mock_session)` so the body actually holds a real anyio task group. `caplog.set_level(logging.WARNING, logger="the_one.mcp.client")`. `async with MCPClient(_stdio_source()) as c: pass` — connect and disconnect on the same task. Assert no record in `caplog.records` matches `"MCPClient transport close failed"`. **This is meaningful BECAUSE the mock holds a real task group**: the test proves anyio's guard does NOT fire on same-task exit. (A simpler "no warning on success" test would pass even with a guard-less mock — useless.)

   - **`test_cross_task_disconnect_logs_via_safety_net`**: monkeypatch `client_mod._transport_connect` to `lambda source: _anyio_backed_transport_cm(mock_session)`. Construct the `MCPClient` and call `await c.connect()` synchronously on the test task — this means anyio's `_host_task` for the cancel scope IS the test task. Then explicitly schedule `disconnect()` on a separate worker task: `disconnect_task = asyncio.create_task(c.disconnect()); await disconnect_task`. The disconnect runs on the worker task, calls `stack.aclose()`, which invokes the dispatcher's `__aexit__`, which exits the anyio task group. anyio's `CancelScope.__exit__` checks `current_task() is self._host_task` (verified at `.venv/lib/python3.12/site-packages/anyio/_backends/_asyncio.py:444-458`) — the test task is the host but the worker is current, so the guard raises the REAL `RuntimeError("Attempted to exit cancel scope in a different task...")`; the safety-net swallow at `client.py::disconnect`'s `except Exception:` clause catches it. `caplog.set_level(logging.WARNING, logger="the_one.mcp.client")`; assert exactly one record matches `"MCPClient transport close failed"`. Assert `c.is_alive is False` and `disconnect_task` did not raise (the swallow absorbed). **This locks the cross-task contract for real — the host-task / current-task asymmetry is the actual mechanism, not just an error-message simulation.**

   - **`test_worker_task_pattern_no_safety_net_log`**: monkeypatch `_transport_connect` to `lambda source: _anyio_backed_transport_cm(mock_session)`. Build a worker fixture that mirrors the L3 §2 pattern:
     ```python
     async def _worker(client: MCPClient, ready: asyncio.Event, evict: asyncio.Event) -> None:
         await client.connect()
         ready.set()
         try:
             await evict.wait()
         finally:
             await client.disconnect()
     ```
     From the test task: `ready = asyncio.Event(); evict = asyncio.Event(); client = MCPClient(_stdio_source()); worker = asyncio.create_task(_worker(client, ready, evict)); await ready.wait(); evict.set(); await worker`. `caplog.set_level(logging.WARNING, logger="the_one.mcp.client")`; assert no `"MCPClient transport close failed"` record. **Because connect AND disconnect run on the worker task, anyio's guard is satisfied — this proves the L3 worker-task-per-entry pattern actually works against a real anyio task group**, which is the load-bearing assumption L3's design rests on. Use `ready: asyncio.Event` not `asyncio.sleep` for deterministic synchronization.

   - **`test_connect_failure_runs_stack_aclose`**: monkeypatch `_transport_connect` to a working `_anyio_backed_transport_cm(mock_session)` (or the simpler `@asynccontextmanager` from `patch_transport`) AND set `mock_session.initialize` to raise `RuntimeError("init failed")`. Spy via `unittest.mock.patch.object(AsyncExitStack, "aclose", autospec=True, wraps=AsyncExitStack.aclose)` scoped narrowly with a `with patch.object(...)` block — NOT a fixture-level monkeypatch (prevents leakage to other tests in the same session). The `wraps=` argument preserves real behavior so cleanup actually runs while the spy records calls. Confirm: (a) `connect()` raises `MCPConnectionError`; (b) `c._transport_stack is None` post-failure (set by `_cleanup_after_failed_connect`'s `finally`); (c) `c._session is None`; (d) `c.is_alive is False`; (e) the spy recorded `>= 1` `aclose` call. **Do NOT assert "exactly one"** — the two-layer AsyncExitStack architecture (per the §Edge Cases bullet) means one call from `_cleanup_after_failed_connect` on the outer stack PLUS the dispatcher's inner `stack.aclose()` triggered transitively in its `finally:`, so the autospec-class-level spy will record `>= 2` calls in practice. The load-bearing observation is the post-cleanup state (b/c/d), not the call count; the `>= 1` assertion is just a smoke check that the spy fired at all.

   - **`test_disconnect_idempotent_with_stack`**: monkeypatch `_transport_connect` to `_anyio_backed_transport_cm(mock_session)`. Cover four scenarios in one test (or split into 2-3 sub-tests if cleaner):
     - **(a) never-connected**: `c = MCPClient(_stdio_source()); await c.disconnect()`. No raise; `c._transport_stack is None`; `c.is_alive is False`.
     - **(b) double-disconnect**: `c = MCPClient(...); await c.connect(); stack_first = c._transport_stack; await c.disconnect(); await c.disconnect()`. Second disconnect short-circuits via the `_is_alive False AND _transport_stack None` early return; no raise; no second `aclose` (verify via spy or by asserting `caplog` has no records after the first disconnect's clean close). Hold a live ref to `stack_first` so the object survives across (c).
     - **(c) reconnect-after-disconnect produces a fresh stack**: continuing from (b), `await c.connect(); assert c._transport_stack is not stack_first; await c.disconnect()`. Use `is not` against the live `stack_first` reference rather than `id()` comparison — CPython id-recycling of GC'd objects could spuriously match if the original stack were collected.
     - **(d) post-`_cleanup_after_failed_connect` state**: separate `MCPClient` instance; force `mock_session.initialize` to raise; `with pytest.raises(MCPConnectionError): await c.connect()`; assert `c.is_alive is False AND c._transport_stack is None AND c._session is None`.

   - (optional) **`test_subprocess_cleanup_via_proc_inspection`**: marker `@pytest.mark.skipif(not Path("/proc").is_dir(), reason="Linux-only /proc inspection")`. Use `mcp_fixture_stdio_params` to build a real `MCPSource(type="stdio", config={"command": ..., "args": ..., "env": ...}, ...)`. After `await c.connect()`, capture the bwrap subprocess PID (read from `c._session._read_stream._fd` lineage if reachable; otherwise enumerate `Path("/proc")` children before/after connect to find the new PID). After `await c.disconnect()`, poll `Path(f"/proc/{pid}").exists()` for up to 2 seconds (e.g., `for _ in range(20): if not Path(f"/proc/{pid}").exists(): break; await asyncio.sleep(0.1); else: pytest.fail(...)`).

7. **Run the new tests + the regression suite together.**

   ```bash
   docker compose exec the-one pytest tests/test_mcp_client.py -v --timeout=30
   docker compose exec the-one pytest tests/test_mcp_client.py tests/test_mcp_integration.py tests/test_mcp_sandbox_integration.py tests/test_mcp_stdio_sandbox.py tests/test_sandbox_bubblewrap.py tests/test_sandbox_contract.py -q --timeout=30
   ```

   Confirm: count on `tests/test_mcp_client.py` goes from 54 → 59-60 (5 required new + 1 optional); `tests/test_mcp_integration.py` (14), `tests/test_mcp_sandbox_integration.py` (10), `tests/test_mcp_stdio_sandbox.py` (9), `tests/test_sandbox_bubblewrap.py` (16), `tests/test_sandbox_contract.py` (14) UNCHANGED.

8. **Lint check.**

   ```bash
   docker compose exec the-one ruff check the_one/mcp/ tests/test_mcp_client.py
   ```

   Resolve any new findings. (`ruff format the_one/mcp/ tests/test_mcp_client.py` is acceptable if the new test class triggers formatter drift — pre-existing formatting in the file is the floor.)

9. **Update the flight log.** Append a Leg Progress entry under `## Leg Progress` with: status `landed` (NOT `completed` — flight-final commit will transition it), started/completed timestamps (ISO 8601, UTC), `### Changes Made` summary, `### Notes` covering: (a) observed cross-task behavior in the probe (anyio's actual error message captured during the cross-task test, for L2's later regex-baseline reference); (b) confirmation that the L2 stderr-capture seam (the SDK's `errlog=` parameter on `mcp.client.stdio.stdio_client`) is still reachable from the unchanged `connect_stdio` — pass `errlog=tempfile.SpooledTemporaryFile(...)` into `stdio_client(...)` from inside the existing `@asynccontextmanager` body (NOTE: with the scope-reduction deviation, this is trivially still reachable since the function is unchanged); (c) which test methods lock each of the four observable invariants from the stake-test probe (per AC #11).

## Edge Cases

- **Existing `test_disconnect_swallows_close_errors` mock contract**: the test patches `client_mod._transport_connect` to an `@asynccontextmanager`. Because the scope-reduction deviation leaves `_transport_connect` entirely unchanged, this test passes unmodified. **Do NOT modify this test.**

- **Single AsyncExitStack architecture (post-deviation)**: `MCPClient`'s outer `_transport_stack` registers ONE async-CM exit callback (the dispatcher's `__aexit__`). The dispatcher itself uses nested `async with` over the unchanged transport CMs — no inner AsyncExitStack. Call chain on disconnect: `MCPClient._transport_stack.aclose()` → dispatcher.`__aexit__` → SDK transport CMs' `__aexit__` (in LIFO order via `@asynccontextmanager`'s generator-finally). The two-layer architecture description from earlier revisions of this leg no longer applies — the scope-reduction collapsed the dispatcher's internal stack back to F2's nested-`async with` shape. AC #(d) (`test_connect_failure_runs_stack_aclose`) consequently observes EXACTLY one outer-stack `aclose` call (not `>= 2`); the spy assertion can be tightened to `== 1` if the implementer prefers, OR kept at `>= 1` for forgiveness — choice at implementer's discretion since both states satisfy the load-bearing post-cleanup-state observation.

- **SDK version pin**: cross-task `RuntimeError` behavior was empirically verified at flight design 2026-05-06 against `mcp==1.27.0` and `anyio==4.x` (the F2-pinned versions). If the SDK is upgraded, re-run the L1a stake-test probe to re-verify that anyio's `CancelScope.__aexit__` still raises on cross-task exit — anyio's contract is documented but a minor-version change could surface a different error class or a non-raising fallback.

- **`@asynccontextmanager` dead-yield preservation**: lines 86-88 of `client.py` (the `yield  # type: ignore[unreachable]` with `# noqa: F821`) exist as a workaround for `@asynccontextmanager`'s "must contain a yield" requirement. **Earlier revisions of this leg proposed deleting it as part of the dispatcher rewrite; the scope-reduction deviation reverts that — the dispatcher is unchanged and the dead yield STAYS.** Confirm via `grep "type: ignore\[unreachable\]" the_one/mcp/client.py` returning the original line still present.

- **`AsyncExitStack` re-entry safety**: never enter a single `AsyncExitStack` instance twice. Each `MCPClient.connect` builds a fresh stack; each `MCPClient.disconnect` consumes (`aclose`) it then sets `self._transport_stack = None`. Reconnecting after disconnect builds a new stack — verified by `test_disconnect_idempotent_with_stack`.

- **`asyncio.timeout` interaction with `enter_async_context`**: the existing `connect()` wraps everything in `async with asyncio.timeout(self.timeout_seconds):`. If the timeout fires while `enter_async_context(_transport_connect(...))` is mid-entry, the stack is partially populated. The exception path in `connect()` calls `_cleanup_after_failed_connect()` which calls `await self._transport_stack.aclose()` — this correctly closes any partial entries (`AsyncExitStack` documents `aclose` is safe even if no contexts were entered or if entry was incomplete). No additional handling required.

- **Cross-task safety net under empty-stack double-aclose**: if disconnect is called twice, the second call sees `self._transport_stack is None` (set by `finally:` on first call) and returns early via the guard at the top of `disconnect`. No extra `aclose` runs. Locked by `test_disconnect_idempotent_with_stack`.

- **Streamable-HTTP transport unchanged**: with the scope-reduction deviation, `connect_streamable_http` is unchanged. Test-path / production-path branching, owned-vs-injected httpx client lifecycle, etc. are exactly as they were in F2.

- **Subprocess cleanup observability**: anchored on Linux `/proc/{pid}` inspection. The optional integration test in step 6 has `@pytest.mark.skipif(not Path("/proc").is_dir(), ...)` so the test is portable but only meaningfully runs on the dev container (which is Linux-only per F3's bubblewrap dependency). The acceptance-criteria checks do not REQUIRE this test — it's documented as optional in §Outputs.

## Files Affected

- `the_one/mcp/client.py` — `MCPClient.__init__`, `connect`, `_cleanup_after_failed_connect`, `disconnect` (the AsyncExitStack refactor). The import on line 18 extends from `from contextlib import asynccontextmanager` to `from contextlib import AsyncExitStack, asynccontextmanager`. The `_transport_connect` dispatcher and the dead `yield` line are UNCHANGED.
- `the_one/mcp/transports/stdio.py` — **NOT MODIFIED** (scope-reduction deviation; see §Objective).
- `the_one/mcp/transports/streamable_http.py` — **NOT MODIFIED** (scope-reduction deviation; see §Objective).
- `tests/test_mcp_client.py` — new module-scope helper `_anyio_backed_transport_cm` (placed near the existing `_mock_transport_cm` at line 121) and new `TestAsyncExitStackContract` class with stake-test probe comment block + 5 required + up to 1 optional new tests.
- `missions/07-mcp-integration/flights/04-idle-ttl-lifecycle/flight-log.md` — append Leg Progress entry.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`. Do NOT commit.**

- [ ] All acceptance criteria verified
- [ ] `pytest tests/test_mcp_client.py tests/test_mcp_integration.py tests/test_mcp_sandbox_integration.py tests/test_mcp_stdio_sandbox.py tests/test_sandbox_bubblewrap.py tests/test_sandbox_contract.py -q --timeout=30` green; per-file counts: prior tests UNCHANGED; `tests/test_mcp_client.py` count grew by 5 required (+1 optional)
- [ ] `ruff check the_one/mcp/ tests/test_mcp_client.py` clean (no NEW findings vs baseline)
- [ ] Flight log Leg Progress entry added (status `landed`, timestamps, changes summary, observed cross-task probe behavior, per-test invariant mapping)
- [ ] Set this leg's status to `landed` (header at top of this file). Do NOT set to `completed` — the flight-level commit transitions it.
- [ ] Check off this leg in flight.md (the `[ ] 01a-async-exit-stack-and-cross-task-safety` line)
- [ ] Do NOT commit. Do NOT signal `[COMPLETE:leg]`. Signal `[HANDOFF:review-needed]` and stop.

---

## Citation Audit

8 citations verified against current code at leg design time (2026-05-06). Implementation-time gap caught by Developer (2026-05-07): the citation audit verified the cited locations but did NOT walk the test files for direct callers of `connect_stdio` / `connect_streamable_http` — which is what surfaced the AC #6/#8 conflict. The scope-reduction deviation resolves the conflict by leaving both transport modules unchanged. Methodology note for flight debrief: design-review citation audit must include "find direct callers of any public symbol whose signature changes" as an explicit step.

- `the_one/mcp/client.py:134` (in `MCPClient.__init__`) — `self._transport_cm: Any = None  # holds the _transport_connect cm` — **OK** (verified via Read 2026-05-06). **Will be modified in this leg.**
- `the_one/mcp/client.py:187-188` (in `connect`) — `self._transport_cm = _transport_connect(self.source); session = await self._transport_cm.__aenter__()` — **OK**. **Will be modified in this leg.**
- `the_one/mcp/client.py:235` (in `_cleanup_after_failed_connect`) — `await self._transport_cm.__aexit__(None, None, None)` — **OK**. **Will be modified in this leg.**
- `the_one/mcp/client.py:254-257` (in `disconnect`) — `await self._transport_cm.__aexit__(None, None, None)` followed by `except Exception: logger.warning("MCPClient transport close failed", exc_info=True)` — **OK**. **Will be modified in this leg** (the `__aexit__` call) and the comment renamed.
- `the_one/mcp/client.py:57-88` (`_transport_connect` dispatcher with the dead `yield  # type: ignore[unreachable]` at line 88) — **OK**. **NOT modified in this leg** (post-deviation).
- `the_one/mcp/transports/stdio.py:166-190` (`connect_stdio` `@asynccontextmanager` with nested `async with stdio_client(params) as (read, write): async with ClientSession(read, write) as session: yield session`) — **OK**. **NOT modified in this leg** (post-deviation).
- `the_one/mcp/transports/streamable_http.py:55-110` (`connect_streamable_http` `@asynccontextmanager` with test-path / production-path branching) — **OK**. **NOT modified in this leg** (post-deviation).
- `tests/test_mcp_client.py:388-407` (`test_disconnect_swallows_close_errors` patching `client_mod._transport_connect`) — **OK**. Continues to pass unmodified post-deviation.
