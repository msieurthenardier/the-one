# Leg: 05a-pty-session-protocol-and-unix-implementation

**Status**: landed
**Flight**: [Execution Expansion & Constraints](../flight.md)

## Objective

Add `the_one/platform/pty.py` with the `PtySession` ABC and a Unix `pty`-based concrete implementation (`UnixPtySession`). Enforce the `_build_subprocess_env()` allowlist via fork-then-execv (Decision 10). Resolve the two leg-design-time Open Questions: protocol shape and PTY readiness signal after `start()`.

## Context

- **L1a + L1b + L2 + L3 + L4 landed** (uncommitted). Execution tools are migrated. `_build_subprocess_env()` exists in `the_one/tools/execution.py`.
- **F4 Decision 10 (env-allowlist invariant for pty)**: `pty.spawn(shell)` would inherit the parent's full environment. To enforce the allowlist, the implementation must `pty.fork()`, then in the child clear `os.environ` and `os.execvp(shell, [shell])`. The exec replaces the child process image with the shell, which now sees only the allowlisted env.
- **F4 Decision 4 (`PtySession` protocol)**: ABC method signatures `start()`, `send(input, timeout) -> bytes`, `close()`, `is_alive: bool`, `last_activity: float`. Resolved at L5a leg-design time.
- **F4 Open Question (PTY readiness signal after `start`)**: recommendation was block-until-prompt. **Resolution for this leg**: `start()` blocks until the shell signals readiness via a short `select`-based read with timeout. Detect readiness as "the master_fd has at least one byte AND no new bytes for ~100ms" (idle-mark) OR a hard 2-second cap, whichever comes first. This avoids regex-matching prompts (which vary by shell/RC) and still gives a clean post-`start()` state for the agent's first `send`.
- **L5b (next leg)** ships the registry + reaper + lifespan integration. **L5a is the protocol + Unix implementation only** — no registry, no reaper, no agent_name. Tests instantiate `UnixPtySession` directly.
- **Asyncio integration**: `send` is `async def` returning `bytes`. Internally uses `loop.run_in_executor(None, blocking_io)` to wrap the synchronous `os.write` + `select.select` + `os.read` loop. Stdlib-only, no async-pty libraries (per mission constraint "no frameworks beyond M01-M04 baseline").
- **Stdlib `pty` module quirks**:
  - `pty.fork()` returns `(pid, master_fd)`. In child, returns `(0, master_fd)` — but the `master_fd` in child is unusable; the child's stdin/stdout/stderr are already wired to the slave PTY.
  - The child process sees stdin/stdout/stderr as the slave PTY → all subsequent writes go through the master_fd in the parent.
  - Calling `os.execvp` in the child REPLACES the process image. Before exec, the child's environment is whatever the parent had; we clear and replace.
- **Threat model note**: Decision 11 says per-call denylist enforcement on `send` lives in the SESSION TOOL (L6), not in `PtySession`. L5a is the platform primitive — no policy logic.

## Inputs

- `the_one/platform/__init__.py` — current public API; will gain `PtySession` re-export (NEW, optional — re-export depends on L5b's needs).
- `the_one/platform/shell.py` — `select_shell()` returns `(shell_executable, args_prefix)`. Use `select_shell()[0]` (just the executable, no `-c` args) for the interactive shell.
- `the_one/tools/execution.py` — `_build_subprocess_env()`. **Subtle**: this helper is currently in `the_one/tools/execution.py` because L2 placed it there. L5a needs to call it from `the_one/platform/pty.py`. Two options:
  1. Import from `the_one.tools.execution` (creates a `platform → tools` import direction, which is BACKWARDS — `platform/` is supposed to be the lower layer with no `tools/` deps).
  2. Move `_build_subprocess_env()` and `_ENV_ALLOWLIST` to `the_one/platform/pty.py` (or a new `the_one/platform/env.py`) and re-export from `the_one/tools/execution.py` for backward-compat.
  - **Choice for this leg**: option 2. Move the env-allowlist machinery into `the_one/platform/env.py` (NEW module) so `platform/pty.py` and `tools/execution.py` both import from there. Re-export from `tools/execution.py` for L3/L4 backward-compat (existing tests reference these names from `the_one.tools.execution`).
- `the_one/platform/paths.py`, `the_one/platform/shell.py`, `the_one/platform/interpreter.py` — pattern reference (cross-platform contract; `os.name == "nt"` early branch with `NotImplementedError`).

## Outputs

- `the_one/platform/env.py` (NEW):
  - `_ENV_ALLOWLIST: tuple[str, ...]` (moved from `the_one/tools/execution.py`).
  - `_build_subprocess_env() -> dict[str, str]` (moved).
  - Module docstring documenting Decision 10 and the platform-layer placement.
- `the_one/tools/execution.py`:
  - REMOVE local `_ENV_ALLOWLIST` and `_build_subprocess_env` definitions.
  - ADD `from the_one.platform.env import _ENV_ALLOWLIST, _build_subprocess_env  # noqa: F401  (re-export for L3/L4)`. Same `# noqa: F401` pattern as L1a's `ConstraintError` re-export.
- `the_one/platform/__init__.py`:
  - Add `from the_one.platform.env import _build_subprocess_env` (for L5b/L6 to call from session tools without reaching into `platform.env` directly — actually keep the underscore-private name; only re-export the platform-public surface).
  - Add `from the_one.platform.pty import PtySession, UnixPtySession, create_pty_session` to `__all__` once L5a is live.
- `the_one/platform/pty.py` (NEW):
  - Module docstring: cross-platform PTY contract; Unix-only for F4; Windows ConPTY explicitly deferred.
  - **Top-of-file Windows guard**:
    ```python
    if os.name == "nt":
        raise NotImplementedError(
            "Windows ConPTY support deferred to a future mission"
        )
    ```
    (Place AFTER imports; raises at IMPORT TIME on Windows.)
  - `class PtySession(ABC)`:
    ```python
    class PtySession(ABC):
        @abstractmethod
        async def start(self) -> None:
            """Spawn the shell subprocess and block until ready for input.

            Implementations:
              - fork-then-execvp with the hardcoded env allowlist
              - block until the shell signals readiness (idle-mark or
                hard 2s cap, whichever comes first)
            """

        @abstractmethod
        async def send(self, input: str, timeout: float = 30.0) -> bytes:
            """Write `input` (newline-terminated if not already) to the shell;
            read response until idle (no new bytes for ~100ms) OR the timeout
            elapses. Returns raw bytes. Updates ``self.last_activity``.

            Raises ``asyncio.TimeoutError`` if the shell produces no output
            for the entire ``timeout`` window.
            """

        @abstractmethod
        async def close(self) -> None:
            """Send SIGTERM, wait 1s, SIGKILL if still alive, close master_fd.
            Idempotent — safe to call multiple times."""

        @property
        @abstractmethod
        def is_alive(self) -> bool:
            """True if the subprocess is still running.

            Non-blocking ``os.waitpid(pid, os.WNOHANG)`` check; returns
            ``False`` once the child has exited (or after ``close()``).
            """

        @property
        @abstractmethod
        def last_activity(self) -> float:
            """``time.monotonic()`` timestamp of the most recent ``send``
            return. Used by the idle reaper (L5b) to decide when to call
            ``close()``."""
    ```
  - `class UnixPtySession(PtySession)`:
    - `__init__(self, cwd: Path | None = None, shell: str | None = None)` — store cwd and optional explicit shell override (used in tests; defaults to `select_shell()[0]`).
    - `start()` implementation:
      1. Verify `os.name == "posix"` (defensive).
      2. `shell = self._shell_override or select_shell()[0]`. **`-i` flag handling**: only pass `-i` when the resolved shell basename is `bash` or `zsh` (`os.path.basename(shell) in {"bash", "zsh"}`). For `dash`/`sh`/other, spawn non-interactive (`[shell]` only) — `dash -i` emits "can't access tty" warning bytes in some configurations and the F4 use case doesn't strictly need an interactive prompt (idle-mark detects the prompt regardless). The dev container's `$SHELL` is `/bin/bash`, so `-i` applies; `/bin/sh` (dash symlink) does not get `-i`.
      3. `pid, master_fd = pty.fork()`.
      4. If `pid == 0` (child):
         - **chdir BEFORE env mutation** (chdir failure is the more common operator error; fail fast):
           - If `cwd is not None`: `try: os.chdir(str(cwd)); except OSError: os._exit(127)` — child process can't propagate exceptions; `os._exit` avoids running atexit handlers / pytest cleanup.
         - `os.environ.clear()`.
         - `os.environ.update(_build_subprocess_env())`.
         - Build argv: `argv = [shell, "-i"] if os.path.basename(shell) in {"bash", "zsh"} else [shell]`.
         - `os.execvp(shell, argv)`. On success, exec replaces the process image — does not return.
      5. Parent: store `pid`, `master_fd`. Set `master_fd` to non-blocking via `fcntl.fcntl(master_fd, fcntl.F_SETFL, os.O_NONBLOCK)`.
      6. Block-until-ready: call `await self._read_until_idle(timeout=2.0, idle_window=0.1)` to drain the prompt. Discard the result.
      7. Update `self._last_activity = time.monotonic()`.
    - `send(input, timeout)` implementation:
      1. If `self._closed` or not `is_alive`: raise `RuntimeError("session not active")`.
      2. Append `\n` to input if not already terminated.
      3. Run blocking I/O in executor: `await asyncio.get_running_loop().run_in_executor(None, self._send_blocking, input.encode(), timeout)`.
      4. `_send_blocking`: `os.write(master_fd, payload)`; then `_read_until_idle_blocking(timeout=timeout, idle_window=0.1)`.
      5. Update `self._last_activity = time.monotonic()`.
      6. Return raw bytes.
    - `_read_until_idle(timeout, idle_window) → bytes` async wrapper around `_read_until_idle_blocking`.
    - `_read_until_idle_blocking(timeout, idle_window) → bytes`:
      - Track `start_time = time.monotonic()` and `last_byte_time = start_time`.
      - Loop:
        - `select_timeout = max(0.0, min(idle_window, timeout - (time.monotonic() - start_time)))` — **clamp non-negative** to avoid `select.select` raising `ValueError` once the budget is exhausted.
        - `ready, _, _ = select.select([master_fd], [], [], select_timeout)`.
        - If ready: read up to 65536 bytes via `os.read(master_fd, 65536)`. Append to buffer. Update `last_byte_time = time.monotonic()`.
        - If not ready (idle): if `time.monotonic() - last_byte_time >= idle_window` AND buffer is non-empty: return buffer.
        - If `time.monotonic() - start_time >= timeout`: raise `asyncio.TimeoutError` if buffer is empty; else return buffer (partial read on timeout).
      - On `OSError(EIO)` (PTY closed): return current buffer.
      - On `BlockingIOError` / `OSError(EAGAIN)` from `os.read`: treat as no-data this iteration, continue loop.
    - `close()`:
      1. If already closed (e.g. `self._closed`): return.
      2. Set `self._closed = True`.
      3. `os.kill(pid, signal.SIGTERM)`.
      4. Wait up to 1s for `os.waitpid(pid, os.WNOHANG)` to reap. Loop with `time.sleep(0.05)`.
      5. If still alive: `os.kill(pid, signal.SIGKILL)`; `os.waitpid(pid, 0)` (blocking).
      6. `os.close(master_fd)`.
      7. Catch and log `ProcessLookupError` (child already exited) at every step.
      8. Async wrapper: `await loop.run_in_executor(None, self._close_blocking)`.
    - `is_alive` property:
      ```python
      @property
      def is_alive(self) -> bool:
          if self._closed:
              return False
          try:
              done, _ = os.waitpid(self._pid, os.WNOHANG)
          except ChildProcessError:
              # Kernel removed the entry between calls; treat as dead.
              self._closed = True
              return False
          if done == 0:
              return True
          # `done == self._pid` means it has exited; mark closed.
          self._closed = True
          return False
      ```
    - `last_activity` property: returns `self._last_activity` (set in `start` and `send`).
  - `def create_pty_session(cwd: Path | None = None, shell: str | None = None) -> PtySession`:
    - On `os.name == "posix"`: returns `UnixPtySession(cwd=cwd, shell=shell)`.
    - On other platforms: would have been blocked at module import. (Belt-and-suspenders.)
- `tests/test_pty_session.py` (NEW):
  - `TestUnixPtySession` (skip on non-Posix via `pytest.skip` at module level if `os.name != "posix"`):
    - `test_start_creates_alive_session`: `s = UnixPtySession(); await s.start(); assert s.is_alive; await s.close()`.
    - `test_send_echoes_input`: `await s.send("echo hello")` → bytes containing `b"hello"`.
    - `test_send_round_trip_pwd`: `await s.start(cwd=tmp_path); await s.send("pwd")` → bytes containing `tmp_path`.
    - `test_send_after_close_raises`: close, then `await s.send("x")` raises `RuntimeError`.
    - `test_close_is_idempotent`: `await s.close(); await s.close()` — no error.
    - `test_close_kills_subprocess`: start, get pid, close, then `os.kill(pid, 0)` raises `ProcessLookupError`.
    - `test_send_timeout_raises_when_no_output`: spawn an interactive subprocess that hangs on input; pass a tight timeout; `send` raises `asyncio.TimeoutError`. (Tricky to engineer; can use a Python REPL with `input()` blocking, but that requires sending input that doesn't trigger a response. Alternative: stub the platform call with monkeypatching — keep it simple.)
    - `test_env_allowlist_invariant`: `monkeypatch.setenv("THE_ONE_TEST_LEAK", "secret")`. Start session, send `env`, parse output. Assert `THE_ONE_TEST_LEAK` not in keys. Allow superset of allowlist + shell-injected (`PWD`, `_`, `SHLVL`, `PS1`, etc — interactive shell sets these).
    - `test_last_activity_updated`: capture `t0 = s.last_activity`; await `send("echo")`; assert `s.last_activity > t0`.
    - `test_is_alive_false_after_subprocess_exits`: send `exit` to the shell; wait briefly; `assert not s.is_alive`.
  - **`TestWindowsGuard`** (skipped on Posix): pin the import-time `NotImplementedError` on Windows.

## Acceptance Criteria

- [x] `the_one/platform/env.py` exists; `_ENV_ALLOWLIST` and `_build_subprocess_env` live there.
- [x] `the_one/tools/execution.py` re-exports both names with `# noqa: F401`; existing L2 tests pass unchanged.
- [x] `the_one/platform/pty.py` exists.
- [x] `pty.py` raises `NotImplementedError` at IMPORT time when `os.name == "nt"`.
- [x] `PtySession` ABC defines `start()`, `send(input, timeout)`, `close()`, `is_alive` property, `last_activity` property.
- [x] `UnixPtySession.start()` uses `pty.fork()` + child-side `os.environ.clear()` + `os.environ.update(_build_subprocess_env())` + `os.execvp(shell, [shell, "-i"])`.
- [x] `start()` blocks until idle-mark (no new bytes for `idle_window`) or hard cap (`2s` default), whichever first.
- [x] `start()` accepts optional `cwd: Path | None` and `os.chdir`s in the child before exec.
- [x] `send(input, timeout)` returns raw bytes from the shell, updates `last_activity`, supports `asyncio.TimeoutError` on no-output windows.
- [x] `close()` is idempotent (multiple calls do not error).
- [x] `close()` kills the subprocess (verified by `os.kill(pid, 0)` raising `ProcessLookupError` post-close).
- [x] `is_alive` returns `True` while subprocess is running, `False` after exit or close.
- [x] **Env allowlist invariant verified**: `THE_ONE_TEST_LEAK` set in parent process is NOT visible to the shell spawned by `UnixPtySession`.
- [x] All new tests pass.
- [x] No existing tests regress: `docker exec the-one pytest -x -q` is green (modulo CSS-token red).
- [x] `ruff check` clean on touched files.
- [x] `the_one/platform/__init__.py` exposes `PtySession`, `UnixPtySession`, `create_pty_session` in its public surface (added to `__all__`).

## Verification Steps

```bash
# Module imports cleanly (Linux)
docker exec the-one python -c "
from the_one.platform.pty import PtySession, UnixPtySession, create_pty_session
from the_one.platform.env import _ENV_ALLOWLIST, _build_subprocess_env
from the_one.tools.execution import _ENV_ALLOWLIST as A, _build_subprocess_env as B
from the_one.platform.env import _ENV_ALLOWLIST as C, _build_subprocess_env as D
assert A is C and B is D, 're-export identity broken'
print('OK imports')
"

# Round-trip smoke
docker exec the-one python -c "
import asyncio
from pathlib import Path
from the_one.platform.pty import UnixPtySession
async def main():
    s = UnixPtySession(cwd=Path('/tmp'))
    await s.start()
    assert s.is_alive
    out = await s.send('echo hello-pty')
    assert b'hello-pty' in out, out
    out2 = await s.send('pwd')
    assert b'/tmp' in out2, out2
    await s.close()
    assert not s.is_alive
    print('OK round-trip')
asyncio.run(main())
"

# Env allowlist invariant
docker exec the-one python -c "
import asyncio, os
os.environ['THE_ONE_TEST_LEAK'] = 'secret-pty'
from the_one.platform.pty import UnixPtySession
async def main():
    s = UnixPtySession()
    await s.start()
    out = await s.send('env | grep THE_ONE_TEST_LEAK || echo NOT_FOUND')
    await s.close()
    assert b'NOT_FOUND' in out, out
    assert b'secret-pty' not in out, out
    print('OK env allowlist')
asyncio.run(main())
"

# Tests
docker exec the-one pytest tests/test_pty_session.py tests/test_execution_helpers.py tests/test_execution_config.py -x -q
docker exec the-one pytest -x -q

# Lint
docker exec the-one ruff check the_one/platform/pty.py the_one/platform/env.py the_one/tools/execution.py tests/test_pty_session.py
```

## Implementation Guidance

1. **Move env helpers to `the_one/platform/env.py` first**:
   - Cut `_ENV_ALLOWLIST` constant and `_build_subprocess_env` function from `the_one/tools/execution.py`.
   - Paste into a new `the_one/platform/env.py` with appropriate module docstring.
   - In `execution.py`: replace with `from the_one.platform.env import _ENV_ALLOWLIST, _build_subprocess_env  # noqa: F401`.
   - Run the L2 helper test suite (`pytest tests/test_execution_helpers.py -x -q`) — should still pass via re-export. If any import path breaks, fix.

2. **Build `the_one/platform/pty.py`**:
   - Imports: `asyncio`, `fcntl`, `os`, `pty`, `select`, `signal`, `time`, `from abc import ABC, abstractmethod`, `from pathlib import Path`, `from the_one.platform.env import _build_subprocess_env`, `from the_one.platform.shell import select_shell`.
   - Top-of-module Windows guard.
   - Define `PtySession` ABC.
   - Define `UnixPtySession(PtySession)`.
   - Define `create_pty_session(cwd=None)` factory.

3. **Implement `UnixPtySession` carefully** — fork+exec is fragile:
   - `pty.fork()` may fail (resource limits) — catch `OSError` and re-raise with context.
   - Set non-blocking on master_fd via `fcntl` BEFORE the first `select` call.
   - Use `os.read(master_fd, 65536)` and handle `BlockingIOError` / `OSError(EAGAIN)` by treating as "no data this iteration".
   - On `OSError(EIO)` (slave PTY closed when shell exited): return what's accumulated so far.
   - In `_read_until_idle_blocking`, track time via `time.monotonic()` for monotonic budget.
   - **Cleanup on test failures**: tests should `try/finally: await s.close()` to avoid leaking child processes between tests.

4. **Test fixtures**:
   - `pytest-asyncio` is installed with `asyncio_mode = "auto"` in `pyproject.toml` — `async def test_*` is auto-detected; do NOT add `@pytest.mark.asyncio` decorators.
   - Skip the entire test module on `os.name != "posix"` (use `pytestmark = pytest.mark.skipif(...)`).
   - For `test_send_timeout_raises_when_no_output`: send `read x` (bash builtin that blocks for input) with `timeout=0.5`; assert TimeoutError.
   - For `test_env_allowlist_invariant`: pin in test docstring that `monkeypatch.setenv("THE_ONE_TEST_LEAK", ...)` runs BEFORE `UnixPtySession()` instantiation — `_build_subprocess_env()` reads `os.environ` at call time, so the monkeypatch order matters.
   - **Use the `shell` override** for the env-allowlist test: `UnixPtySession(shell="/bin/bash")` to get consistent `env` output formatting regardless of container `$SHELL`.

5. **Run the suite** — particularly verify NO test leaks a child process. Add a session-scoped `autouse` fixture that asserts no leftover children at session teardown if you want to be safe.

## Edge Cases

- **`pty.fork()` resource exhaustion**: returns `OSError`. Tests don't exercise this; document.
- **Interactive shell prompt drift**: different shells produce different prompts. The idle-mark approach (no new bytes for 100ms) avoids prompt-regex matching entirely. If the agent's first `send` returns extra prompt-like bytes, that's accepted noise — agents tolerate this.
- **`bash -i` may try to read `~/.bashrc`** which could leak environment back via `export` statements. Test pinning that `THE_ONE_TEST_LEAK` is not visible verifies the allowlist holds even after rc-file sourcing.
- **`run_in_executor` with default executor**: the default `ThreadPoolExecutor` has a small worker count. If many tests run in parallel, executor saturation could cause delays. Tests should be serial; document.
- **`os.execvp` PATH lookup**: searches `PATH` for the shell binary. The allowlisted env contains `PATH`, so `bash` / `sh` / `/bin/sh` resolves correctly.
- **PTY bytes: control characters, ANSI escape sequences**: shells inject prompt-formatting escapes. Tests assert via `in` substring search, not equality. Accepted.
- **`os.waitpid(pid, os.WNOHANG)` after `close()`**: once we've reaped via `WNOHANG` or blocking `waitpid`, subsequent `WNOHANG` calls return `(0, 0)` if the child is gone — but the kernel may have removed the entry. `os.waitpid` will raise `ChildProcessError`. `is_alive` should catch this and return `False`.
- **`asyncio.run_in_executor` with synchronous I/O**: blocking I/O inside the executor means each `send` ties up a thread for the duration. Acceptable for F4 — execution tools are not high-concurrency.
- **`SIGTERM → SIGKILL` race**: in the 1s window after SIGTERM, the child may have started cleanup that holds the master_fd. Acceptable; SIGKILL forces.
- **`os.chdir` failure in child**: e.g., cwd does not exist. The child writes an error to the slave PTY (which the parent can read after exec doesn't happen). To avoid the parent hanging waiting for the prompt, the child should `os._exit(127)` on chdir failure. Parent's `start()` then sees a quick EOF and `is_alive` returns False. Document.

## Files Affected

- `the_one/platform/env.py` — NEW; hosts `_ENV_ALLOWLIST` + `_build_subprocess_env`.
- `the_one/platform/pty.py` — NEW; `PtySession` ABC + `UnixPtySession` + `create_pty_session`.
- `the_one/platform/__init__.py` — re-export pty surface.
- `the_one/tools/execution.py` — replace local env constants with re-export from `platform.env`.
- `tests/test_pty_session.py` — NEW; `TestUnixPtySession` + Windows-guard test.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed` (in this file's header)
- [ ] (Flight Director will check off in flight.md — do NOT modify flight.md)
- [ ] (NOT final leg — do NOT update flight.md status, do NOT commit)
