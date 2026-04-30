# Leg: 05b-session-registry-reaper-and-lifespan

**Status**: landed
**Flight**: [Execution Expansion & Constraints](../flight.md)

## Objective

Add `the_one/tools/_session_registry.py`: a module-level `(agent_name, session_id) → PtySession` registry with helpers for register/get/close/list/count. Add an idle-reaper `asyncio.Task` that periodically reaps sessions whose `last_activity` exceeds the agent's resolved `pty_session_idle_ttl_seconds`. Register the reaper with FastAPI's `lifespan` context so shutdown awaits and cancels it cleanly. No tool wiring in this leg — L6 wires the four PTY session tools to this registry.

## Context

- **L1a-L5a landed** (uncommitted). `UnixPtySession` ships in `the_one/platform/pty.py`. `_build_subprocess_env()` is in `the_one/platform/env.py`.
- **F4 Decision 5**: 5-minute idle TTL + 5 max concurrent + process-lifetime persistence + FastAPI-lifespan-registered reaper.
  - Reaper is a single `asyncio.Task` spawned **lazily on first session registration** AND registered with FastAPI's lifespan so shutdown awaits and cancels it cleanly.
  - On `make rebuild` / container shutdown: lifespan teardown calls `task.cancel()`; reaper catches `CancelledError`, drains its registry by calling `close()` on each session, exits.
  - Reaper wakes every 30s, checks `last_activity` per session, calls `close()` on expired ones.
- **F4 Decision 4 (per-explicit-handle session addressing)**: registry keyed on `(agent_name, session_id)`. `session_id` formatted as `f"pty-{uuid4().hex}"`.
- **Reaper TTL is per-Config** (`ExecutionConfig.pty_session_idle_ttl_seconds`). The reaper has no Config of its own — it queries the registry's stored sessions for their TTL. **But wait** — the registry stores sessions, not Configs. Two approaches:
  1. Registry stores `(session, ttl_seconds)` tuples; the tool that registers the session passes the ttl from its resolved Config.
  2. Reaper has its own ttl that defaults to 300s (matching `ExecutionConfig.pty_session_idle_ttl_seconds=300`). Per-agent narrowing is enforced at session-START time (the tool checks the count cap and idle-ttl from the resolved Config, but the reaper itself doesn't re-read narrowed values per session).
  - **Choice for this leg**: option 1. The registry is a pure data structure; the L6 session tool passes the resolved `pty_session_idle_ttl_seconds` at register time. The registry stores `(session, ttl_seconds, agent_name)` tuples. The reaper iterates and applies each session's stored TTL. This honors per-agent narrowing.
- **No new asyncio loop magic**: the registry uses simple dict access with module-level `asyncio.Lock` for concurrent register/close. Avoid global mutable state surprises.
- **L6 dependency**: L6's session tools call:
  - `_session_registry.register(agent_name, session_id, session, ttl_seconds)` from `shell_session_start`.
  - `_session_registry.get(agent_name, session_id)` from `shell_session_send`.
  - `_session_registry.close(agent_name, session_id)` from `shell_session_close`.
  - `_session_registry.list_for_agent(agent_name)` from `shell_session_list`.
  - `_session_registry.count_for_agent(agent_name)` from `shell_session_start` (max-concurrent check).
- **`PtySession` ABC** is the abstraction the registry stores; the registry doesn't care if it's `UnixPtySession` or some future `WinPtySession`.

## Inputs

- `the_one/platform/pty.py` — `PtySession` ABC.
- `the_one/interfaces/web/app.py` — `lifespan` context manager (line 44). The reaper's lifespan hook plugs in here.
- `the_one/tools/execution.py` — `ExecutionConfig.pty_session_idle_ttl_seconds` (default 300s).
- `tests/test_pty_session.py` — provides patterns for spawning real PTY sessions in tests.

## Outputs

- `the_one/tools/_session_registry.py` (NEW):
  - Module-level state:
    ```python
    _sessions: dict[tuple[str, str], _RegistryEntry] = {}
    _lock = asyncio.Lock()
    _reaper_task: asyncio.Task | None = None
    _REAPER_INTERVAL_SECONDS = 30.0
    ```
  - `class _RegistryEntry`:
    ```python
    @dataclass
    class _RegistryEntry:
        session: PtySession
        ttl_seconds: int
        # NOTE: agent_name is the dict key — do NOT duplicate here (drift risk).
    ```
  - `def new_session_id() -> str`: returns `f"pty-{uuid4().hex}"`.
  - `async def register(agent_name: str, session_id: str, session: PtySession, ttl_seconds: int) -> None`:
    - If `_shutting_down`: raise `RuntimeError("session registry is shutting down")` — fail loudly rather than silently orphan.
    - Acquire lock.
    - Set `_sessions[(agent_name, session_id)] = _RegistryEntry(session, ttl_seconds)`.
    - Spawn the reaper task lazily (`_ensure_reaper_running()`).
  - `async def get(agent_name: str, session_id: str) -> PtySession | None`:
    - Acquire lock.
    - Return `_sessions.get((agent_name, session_id), _RegistryEntry(...)).session` or `None` if not found.
    - **Cross-agent leakage prevention**: `(agent_name, session_id)` keying naturally rejects cross-agent access — agent B looking up agent A's session_id gets `None` because `(B, sid_a)` isn't in the dict.
  - `async def close(agent_name: str, session_id: str) -> bool`:
    - **Two-phase to avoid lock-and-await deadlock**:
      1. Under lock: pop entry from `_sessions` if present (capture session reference).
      2. Release lock.
      3. If captured: `await entry.session.close()`; return `True`.
      4. Else: return `False`.
    - Rationale: holding `_lock` across `await session.close()` (which can take ~1s under SIGTERM→SIGKILL) would block all other registry operations. Snapshot-under-lock + close-after-release is the standard pattern.
  - `async def list_for_agent(agent_name: str) -> list[str]`:
    - Acquire lock.
    - Return `[sid for (an, sid) in _sessions if an == agent_name]`.
  - `async def count_for_agent(agent_name: str) -> int`:
    - Acquire lock.
    - Return count.
  - `async def _ensure_reaper_running() -> None`:
    - Module-level singleton: if `_reaper_task is None or _reaper_task.done()`, spawn `asyncio.create_task(_reap_loop())` and store.
  - `async def _reap_once() -> list[PtySession]` — extracted body for deterministic tests:
    - Two-phase snapshot+close (same pattern as `close()`):
      1. Under lock: build `expired = [(key, entry.session) for (key, entry) in _sessions.items() if (time.monotonic() - entry.session.last_activity) > entry.ttl_seconds]`. Pop each expired key from `_sessions`.
      2. Release lock.
      3. For each captured session: `await session.close()` (in `try/except` — log + continue if a close raises so one bad session doesn't block reaping the rest).
      4. Return the list of closed sessions (for test purchase).
  - `async def _reap_loop() -> None`:
    - While True:
      - `await asyncio.sleep(_REAPER_INTERVAL_SECONDS)`.
      - `await _reap_once()`.
    - On `asyncio.CancelledError`: drain ALL remaining registry entries (using the same snapshot+close pattern), then re-raise.
  - `async def shutdown_drain() -> None`:
    - Set module-level `_shutting_down = True` so further `register()` calls raise.
    - If `_reaper_task is not None and not _reaper_task.done()`:
      - `_reaper_task.cancel()`.
      - `with contextlib.suppress(asyncio.CancelledError): await _reaper_task` — suppress the CancelledError that the awaiter receives when a cancelled task is awaited; the reap-loop's own CancelledError handler does the registry drain.
    - **Belt-and-suspenders drain** (in case the reaper was never spawned, e.g., `shutdown_drain` called with no sessions ever registered): snapshot+close any remaining `_sessions` entries directly.
    - Reset `_reaper_task = None`.
  - `async def _clear_for_test() -> None` (test seam):
    - Cancel `_reaper_task` if alive; `with contextlib.suppress(asyncio.CancelledError): await _reaper_task`.
    - Reset `_reaper_task = None`, `_shutting_down = False`.
    - Snapshot+close any remaining `_sessions` entries; `_sessions.clear()`.
    - **Tests must call this in an `autouse=True` async fixture** AFTER each test, otherwise the next test inherits a stale `_reaper_task` reference (bound to a torn-down event loop).
- `the_one/interfaces/web/app.py`:
  - In `lifespan`, after the `yield` and before `await close_connection()`: `await shutdown_drain()` (imported from `the_one.tools._session_registry`). Wraps in `try/except` to log but not fail shutdown.
- `tests/test_session_registry.py` (NEW):
  - Tests use a `MockPtySession` that implements `PtySession` minimally (in-memory, no real fork). Avoids spawning real subprocesses for unit tests.
  - **`PtySession` ABC declares `is_alive` and `last_activity` as `@property @abstractmethod`** — mocks MUST use `@property` accessors, NOT class-level attribute defaults. Pattern:
    ```python
    class MockPtySession(PtySession):
        def __init__(self):
            self._alive = True
            self._last_activity = time.monotonic()
            self.close_count = 0
        async def start(self): pass
        async def send(self, input, timeout=30.0): return b""
        async def close(self):
            self.close_count += 1
            self._alive = False
        @property
        def is_alive(self): return self._alive
        @property
        def last_activity(self): return self._last_activity
    ```
    Class-level `is_alive = True` would NOT satisfy the abstract property and `MockPtySession()` would raise `TypeError`.
  - `test_register_and_get`: register a mock; `await get(...)` returns the same instance.
  - `test_get_returns_none_for_unknown_session`.
  - `test_get_returns_none_for_cross_agent`: register under agent A; `await get("B", session_id)` returns None.
  - `test_close_removes_entry_and_calls_session_close`.
  - `test_close_returns_false_for_unknown`.
  - `test_list_for_agent_filters_by_owner`.
  - `test_count_for_agent_filters_by_owner`.
  - `test_reaper_closes_idle_sessions`: register a mock with `last_activity` set to `time.monotonic() - 600` and `ttl_seconds=300`; **call `await _reap_once()` directly** (deterministic — eliminates time-based flakiness from `await asyncio.sleep`); assert session was closed and removed. This is the primary pattern; reserve sleep-based tests for integration (`test_reaper_loop_actually_runs`).
  - `test_reaper_lazy_spawn`: register one session; `_reaper_task` is now non-None.
  - `test_shutdown_drain_cancels_reaper_and_closes_sessions`: register multiple sessions; await `shutdown_drain()`; assert all sessions closed.
  - `test_reaper_does_not_close_active_sessions`: register a mock with fresh `last_activity`; trigger reap; assert still in registry.
  - **Cleanup fixture**: `autouse=True` async fixture that calls `await _clear_for_test()` after each test.
- `tests/test_lifespan.py` (NEW):
  - **Pattern**: use the FastAPI `lifespan` context manager directly — `async with lifespan(app): ...`. **Do NOT use `TestClient`** (sync, doesn't expose lifespan teardown well). The codebase's async-test pattern is `httpx.AsyncClient + ASGITransport` (see `tests/test_db_api.py:10` and `tests/test_provider_api.py:14`); reference for any test that needs HTTP routing.
  - `init_db` + `migrate_json_to_sqlite` run inside the lifespan; tests must point `THE_ONE_DATA_DIR` to a temp directory via `monkeypatch.setenv` BEFORE entering the context.
  - Pattern:
    ```python
    async def test_lifespan_drains_session_registry(monkeypatch, tmp_path):
        monkeypatch.setenv("THE_ONE_DATA_DIR", str(tmp_path))
        from the_one.interfaces.web.app import app, lifespan
        from the_one.tools._session_registry import register, count_for_agent, new_session_id
        async with lifespan(app):
            sid = new_session_id()
            await register("test-agent", sid, MockPtySession(), ttl_seconds=300)
            assert await count_for_agent("test-agent") == 1
        # After lifespan exit, registry is drained.
        assert await count_for_agent("test-agent") == 0
    ```

## Acceptance Criteria

- [x] `the_one/tools/_session_registry.py` exists with the documented public API.
- [x] `new_session_id()` returns `f"pty-{uuid4().hex}"` (36-char `pty-` prefix).
- [x] `register(agent_name, session_id, session, ttl_seconds)` adds to registry.
- [x] `get(agent_name, session_id)` returns the `PtySession` instance or `None`.
- [x] Cross-agent isolation: `get("B", session_id_owned_by_A)` returns `None`.
- [x] `close(agent_name, session_id)` calls `session.close()` and removes the entry; returns `True`/`False`.
- [x] `list_for_agent(agent_name)` filters by owner.
- [x] `count_for_agent(agent_name)` filters by owner.
- [x] Reaper task is lazily spawned on first `register` call (not at module import).
- [x] Reaper closes sessions whose `last_activity` is older than their `ttl_seconds`.
- [x] Reaper does NOT close active sessions.
- [x] `shutdown_drain()` cancels the reaper task (using `contextlib.suppress(asyncio.CancelledError)`) and closes all remaining sessions.
- [x] `register()` after `shutdown_drain()` raises `RuntimeError("session registry is shutting down")` — fails loudly rather than silently orphaning sessions.
- [x] Real-PTY drain integration is verified by L8 (this leg uses `MockPtySession` for unit tests).
- [x] FastAPI `lifespan` in `the_one/interfaces/web/app.py` calls `await shutdown_drain()` on shutdown (logged-but-not-failing).
- [x] Module-level lock serializes concurrent register/close — no race on `_sessions` mutation.
- [x] All new tests pass.
- [x] Full unit suite green (modulo CSS-token red).
- [x] `ruff check` clean.

## Verification Steps

```bash
# Module imports cleanly
docker exec the-one python -c "
from the_one.tools._session_registry import (
    register, get, close, list_for_agent, count_for_agent,
    new_session_id, shutdown_drain,
)
sid = new_session_id()
assert sid.startswith('pty-') and len(sid) == 36 + len('pty-')
print('OK imports')
"

# Cross-agent isolation
docker exec the-one python -c "
import asyncio
from the_one.tools import _session_registry as reg
class MockSession:
    is_alive = True
    last_activity = 0.0
    async def close(self): pass
    async def send(self, *a, **k): return b''
    async def start(self): pass
async def main():
    sid = reg.new_session_id()
    await reg.register('agent-a', sid, MockSession(), ttl_seconds=300)
    assert await reg.get('agent-a', sid) is not None
    assert await reg.get('agent-b', sid) is None
    await reg._clear_for_test()
    print('OK isolation')
asyncio.run(main())
"

# Tests
docker exec the-one pytest tests/test_session_registry.py tests/test_lifespan.py tests/test_pty_session.py -x -q
docker exec the-one pytest -x -q

# Lint
docker exec the-one ruff check the_one/tools/_session_registry.py the_one/interfaces/web/app.py tests/test_session_registry.py tests/test_lifespan.py
```

## Implementation Guidance

1. **Build `the_one/tools/_session_registry.py`**:
   - Module docstring with F4 Decision 4 + 5 references.
   - Use `from __future__ import annotations` and `from dataclasses import dataclass`.
   - Imports: `asyncio`, `time`, `uuid.uuid4`, `from typing import Any`, `from the_one.platform.pty import PtySession`.
   - Define `_REAPER_INTERVAL_SECONDS = 30.0` as a module constant.
   - Define `_RegistryEntry` dataclass.
   - Define module-level `_sessions: dict[...] = {}`, `_lock = asyncio.Lock()`, `_reaper_task: asyncio.Task | None = None`.
   - Define helpers in this order: `new_session_id`, `register`, `get`, `close`, `list_for_agent`, `count_for_agent`, `_ensure_reaper_running`, `_reap_loop`, `shutdown_drain`, `_clear_for_test`.

2. **Reaper lifecycle subtlety**:
   - The reaper task is created lazily inside `register()` to avoid creating it at module-import time (which would fail if no event loop is running).
   - Use `asyncio.get_running_loop()` to ensure we have a loop. If not, raise `RuntimeError` (shouldn't happen — `register` is async and can only be called from an async context).
   - Reaper checks `_reaper_task` via `_lock`-guarded `_ensure_reaper_running` to avoid spawning twice.
   - On `CancelledError` inside `_reap_loop`: drain the registry by closing each session, then re-raise to let the cancel propagate cleanly.

3. **Wire FastAPI lifespan** in `the_one/interfaces/web/app.py`:
   - Import: `from the_one.tools._session_registry import shutdown_drain`.
   - In the `lifespan` async context manager, after `yield`:
     ```python
     try:
         await shutdown_drain()
     except Exception:
         logger.exception("session registry shutdown failed")
     await close_connection()
     ```

4. **Build `tests/test_session_registry.py`**:
   - Use `pytest-asyncio` auto mode (no decorators).
   - Define `MockPtySession(PtySession)` with `start`, `send`, `close`, `is_alive`, `last_activity` (instance vars overridable).
   - Use `autouse=True` async fixture for `_clear_for_test`.
   - For reaper tests, monkeypatch `_REAPER_INTERVAL_SECONDS` to 0.05 and `await asyncio.sleep(0.15)` to trigger.

5. **Build `tests/test_lifespan.py`**:
   - Test the FastAPI lifespan integration. Pattern:
     ```python
     async def test_lifespan_drains_session_registry():
         from the_one.interfaces.web.app import app, lifespan
         async with lifespan(app):
             # Register a session inside the context
             ...
         # After exit, registry should be drained
         assert await count_for_agent("test") == 0
     ```
   - This may require initialising the DB layer; use `tmp_path` for `THE_ONE_DATA_DIR` if necessary.

## Edge Cases

- **Reaper spawned multiple times**: guard with `_lock`. `_ensure_reaper_running` is the only spawn site.
- **`session.close()` raises during reap**: log and continue; remove from registry regardless. Don't let one bad session block reaping others.
- **`register` after `shutdown_drain`**: technically possible if a request races with shutdown. The reap loop has already exited; new sessions are orphaned (no reaper). Acceptable for F4 — process is shutting down; sessions die with the process.
- **`_lock` held across `await session.close()` in reap**: this serializes session shutdowns. Long-running close() blocks other reap operations. Acceptable; sessions close in milliseconds (SIGTERM → wait 1s → SIGKILL → close fd).
- **Cross-agent session_id collision**: `(agent_name, session_id)` keying makes this impossible by construction; even if two agents got the same `uuid4().hex` (probability ~ 0), they're keyed separately.
- **Test flakiness from real time**: prefer explicit `last_activity` values + a small `_REAPER_INTERVAL_SECONDS` over `await asyncio.sleep`. Tests should drive time, not measure it.
- **Module import order**: `_session_registry.py` imports `PtySession` from `the_one.platform.pty`. On Windows, that import raises `NotImplementedError` (per L5a). The registry module would also fail import on Windows — acceptable, since the entire pty session feature is Unix-only for F4. Document.
- **`shutdown_drain` called without registered sessions**: should be a no-op. Verify `_reaper_task is None` path doesn't error.
- **Reaper task crash**: if `_reap_loop` hits an unexpected exception, the task ends. `_ensure_reaper_running` checks `_reaper_task.done()` to respawn on next register. Defensive.

## Files Affected

- `the_one/tools/_session_registry.py` — NEW.
- `the_one/interfaces/web/app.py` — wire `shutdown_drain` into lifespan.
- `tests/test_session_registry.py` — NEW.
- `tests/test_lifespan.py` — NEW (or extend existing app integration tests).

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed` (in this file's header)
- [ ] (Flight Director will check off in flight.md — do NOT modify flight.md)
- [ ] (NOT final leg — do NOT update flight.md status, do NOT commit)
