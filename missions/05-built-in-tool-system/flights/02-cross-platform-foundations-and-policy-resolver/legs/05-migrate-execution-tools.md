# Leg: 05-migrate-execution-tools

**Status**: completed
**Flight**: [Cross-Platform Foundations & Policy Resolver](../flight.md)

## Objective

Route `ShellTool` through `the_one.platform.shell.run_shell` and `PythonExecTool` through `the_one.platform.interpreter.run_python`. The tools' return-string formatting (`[stderr]`, `[exit code: N]`, `[error] ...`, `(no output)`) is preserved byte-for-byte; only the subprocess plumbing moves into the platform layer. Adds direct execute-path regression tests for both tools.

## Context

Second of three tool-migration legs (L4 filesystem ✓, L5 execution, L6 web). Per Decision 5, `Tool.Config = _EmptyConfig` empty default still applies — no per-tool Config classes for F2. F4 will harden these tools with output caps, timeout caps, and command/path denylists.

**Real platform-fix payoff in L5**: today's `PythonExecTool` hardcodes `"python3"` — broken on Windows. The L5 migration to `run_python()` (which calls `resolve_python()` returning `sys.executable`) is the concrete cross-platform improvement. `ShellTool` was already calling `create_subprocess_shell` which delegates shell selection to the OS, so its migration is mostly mechanical.

**Behavioral equivalence**: today's tools call `proc.kill()` on timeout then return an error string. After migration, `run_shell` / `run_python` do the kill+reap internally (using `start_new_session=True` + `killpg(SIGKILL)` per L1's anomaly fix) and re-raise `asyncio.TimeoutError`; the tool's `except` clause returns the same error string. Net behavior is byte-for-byte equivalent on the happy path **and strictly more robust on the timeout path** (no leaked grandchildren — see L1 anomaly entry "proc.kill() alone does not unblock proc.communicate() for shell-spawned subtrees").

### v8 baseline (verified at L5 design time, post-L4)

- `the_one/tools/shell.py:32-50` — `ShellTool.execute(command, timeout=120, **kwargs)`:
  - calls `asyncio.create_subprocess_shell(command, stdout=PIPE, stderr=PIPE)`
  - `await asyncio.wait_for(proc.communicate(), timeout=timeout)`
  - decodes stdout/stderr with `errors="replace"`; appends `\n[stderr]\n{stderr}` if non-empty stderr; appends `\n[exit code: {rc}]` if rc != 0
  - returns `output.strip() or "(no output)"`
  - on `TimeoutError`: `proc.kill()` then `return f"[error] Command timed out after {timeout}s"`
  - on other `Exception`: `return f"[error] {e}"`
- `the_one/tools/python_exec.py:25-41` — `PythonExecTool.execute(code, timeout=60, **kwargs)`:
  - calls `asyncio.create_subprocess_exec("python3", "-c", code, stdout=PIPE, stderr=PIPE)`
  - `await asyncio.wait_for(proc.communicate(), timeout=timeout)`
  - decodes stdout/stderr with `errors="replace"`; appends `\n[stderr]\n{stderr}` if non-empty stderr
  - **does NOT append `[exit code: N]`** (different from ShellTool)
  - returns `output.strip() or "(no output)"`
  - on `TimeoutError`: `proc.kill()` then `return f"[error] Timed out after {timeout}s"` (note: NOT "Command timed out" like ShellTool)
  - on other `Exception`: `return f"[error] {e}"`
- `the_one/platform/shell.py::run_shell(command, *, timeout, env=None) -> tuple[bytes, bytes, int]` — kills+reaps on TimeoutError, re-raises
- `the_one/platform/interpreter.py::run_python(code, *, timeout, env=None) -> tuple[bytes, bytes, int]` — same shape
- **No dedicated unit tests for `ShellTool.execute` / `PythonExecTool.execute` exist today.** L5 adds them as regression coverage (paralleling L4's filesystem-tools test addition).

## Inputs

What exists before this leg runs:

- L1, L2, L3, L4 landed: platform package, schema v8, resolver + Tool ABC + per-agent instantiation, filesystem tools migrated
- `the_one.platform.run_shell` and `the_one.platform.run_python` are available (verified: re-exported via `the_one/platform/__init__.py`)
- Branch: `flight/02-cross-platform-foundations` (continuing from L4)

## Outputs

What exists after this leg completes:

- `the_one/tools/shell.py` — `ShellTool.execute` calls `run_shell(...)`; subprocess plumbing removed
- `the_one/tools/python_exec.py` — `PythonExecTool.execute` calls `run_python(...)`; subprocess plumbing + hardcoded `"python3"` removed
- `tests/test_execution_tools.py` (new) — direct execute-path tests for both tools
- All previously passing tests continue passing (regression invariant)
- Flight log + leg + flight artifact updated

## Acceptance Criteria

- [ ] `the_one/tools/shell.py` migrated:
  - Adds `from the_one.platform import run_shell`
  - Removes `import asyncio` if no longer needed AFTER the migration (asyncio is still imported because `asyncio.TimeoutError` is caught in the `except` clause — keep the import)
  - `ShellTool.execute` body becomes:
    ```python
    try:
        stdout, stderr, returncode = await run_shell(command, timeout=timeout)
        output = stdout.decode(errors="replace")
        if stderr:
            output += f"\n[stderr]\n{stderr.decode(errors='replace')}"
        if returncode != 0:
            output += f"\n[exit code: {returncode}]"
        return output.strip() or "(no output)"
    except asyncio.TimeoutError:
        return f"[error] Command timed out after {timeout}s"
    except Exception as e:
        return f"[error] {e}"
    ```
  - The error-string formatting MUST be byte-for-byte identical: `"[error] Command timed out after Ns"` (NOT "Timed out") for ShellTool; preserve the leading `\n` before `[stderr]` and `[exit code:`; preserve `(no output)` for empty results
  - **`proc.kill()` line removed** — `run_shell` does the kill+reap internally
- [ ] `the_one/tools/python_exec.py` migrated:
  - Adds `from the_one.platform import run_python`
  - Keep `import asyncio` (still needed for `asyncio.TimeoutError`)
  - `PythonExecTool.execute` body becomes:
    ```python
    try:
        stdout, stderr, _ = await run_python(code, timeout=timeout)
        output = stdout.decode(errors="replace")
        if stderr:
            output += f"\n[stderr]\n{stderr.decode(errors='replace')}"
        return output.strip() or "(no output)"
    except asyncio.TimeoutError:
        return f"[error] Timed out after {timeout}s"
    except Exception as e:
        return f"[error] {e}"
    ```
  - Hardcoded `"python3"` is removed (replaced via `run_python` → `resolve_python` → `sys.executable`)
  - **`proc.kill()` line removed** — `run_python` does the kill+reap internally (parallel to ShellTool migration)
  - The error-string `"[error] Timed out after Ns"` (NOT "Command timed out" like ShellTool) is preserved exactly
  - `[exit code: N]` is NOT appended (this is a deliberate divergence from ShellTool — preserve it)
  - The returncode is intentionally discarded (`_`) since it's not used in the output formatting; explicit unused-variable assignment documents the choice
- [ ] No other changes to `the_one/tools/shell.py` or `the_one/tools/python_exec.py` — verify by `git diff` showing only the import + execute-body changes
- [ ] **Test: `tests/test_execution_tools.py` (NEW)** — direct unit tests:
  - `TestShellTool`:
    - Happy path: `ShellTool().execute(command="echo hi")` returns `"hi"` (stripped of trailing newline; no stderr; rc=0 so no `[exit code]`)
    - Stderr is appended: `ShellTool().execute(command="echo err >&2")` returns output containing `"[stderr]"` and `"err"`
    - Non-zero exit: `ShellTool().execute(command="exit 7")` returns output containing `"[exit code: 7]"`
    - Empty output: `ShellTool().execute(command="true")` returns `"(no output)"`
    - Timeout: `ShellTool().execute(command="sleep 5", timeout=0.5)` returns `"[error] Command timed out after 0.5s"` AND the call returns within **3s wall-clock** (proves kill+reap propagation; budget loosened from L1's 1s platform-layer budget to absorb the tool→platform asyncio overhead and tolerate slow CI scheduler latency without false positives — a broken kill+reap blocks for the full 5s sleep, well over the 3s sentinel)
    - Generic exception: not directly testable without mocking; covered indirectly by the timeout test exercising the `except` chain. Skip explicit test.
  - `TestPythonExecTool`:
    - Happy path: `PythonExecTool().execute(code="print(2+2)")` returns `"4"`
    - Stderr is appended: `PythonExecTool().execute(code="import sys; print('err', file=sys.stderr)")` returns output containing `"[stderr]"` and `"err"`
    - Non-zero exit does NOT append `[exit code]`: `PythonExecTool().execute(code="import sys; sys.exit(3)")` returns `"(no output)"` (no exit-code suffix, unlike ShellTool — preserves divergence)
    - Empty output: `PythonExecTool().execute(code="pass")` returns `"(no output)"`
    - Timeout: `PythonExecTool().execute(code="import time; time.sleep(5)", timeout=0.5)` returns `"[error] Timed out after 0.5s"` (note: "Timed out", NOT "Command timed out") AND returns within **3s wall-clock** (same budget rationale as ShellTool above)
    - Cross-platform interpreter: `PythonExecTool` no longer hardcodes `"python3"`; verifiable via the happy path running on any host where `sys.executable` resolves
- [ ] **Tool ABC instantiation regression test** (extend `test_execution_tools.py`): each execution tool can be instantiated with `cls()` (no args) AND `cls(_EmptyConfig())`; both work and produce a tool whose `_config` is an `_EmptyConfig` instance
- [ ] All 7 existing tools' tests pass unchanged (no regressions). Notably:
  - `tests/test_builtins.py` — all 9 tests still pass
  - `tests/test_factory.py` — unchanged behavior
  - `tests/test_filesystem_tools.py` — unchanged behavior (L4)
  - `tests/test_platform_shell.py`, `tests/test_platform_interpreter.py` — unchanged (L1's platform tests already exercise `run_shell` / `run_python` directly)
- [ ] Pre-existing test suite still green (modulo pre-existing CSS-token red): `make test-unit` returns the L4-tip pass/fail set plus the new L5 tests
- [ ] No source code modified outside `the_one/tools/shell.py`, `the_one/tools/python_exec.py`, and `tests/`
- [ ] AIAT live smoke (best-effort, like L4): try `pytest -m live tests/test_aiat.py`; if the pre-existing fixture ScopeMismatch (documented in the F2 flight-log.md Session Notes, L4 entry) still blocks, document the skip and rely on the unit suite. F2 verification leg L7 owns the full live smoke.

## Verification Steps

```bash
# Precondition: platform helpers are importable from the package surface
docker exec the-one python -c "from the_one.platform import run_shell, run_python; print('OK')"

# Diff inspection: confirm minimal scope (host)
git diff -- the_one/tools/shell.py the_one/tools/python_exec.py
# Expected: import line(s) added; execute body replaced; no other deltas

# Build container with new files
make rebuild

# Targeted tests
docker exec the-one pytest tests/test_execution_tools.py -v
docker exec the-one pytest tests/test_builtins.py tests/test_factory.py \
    tests/test_filesystem_tools.py tests/test_platform_shell.py \
    tests/test_platform_interpreter.py -v

# Full unit suite (pre-existing CSS red expected)
make test-unit

# Smoke: shell + python_exec roundtrip
docker exec the-one python -c "
import asyncio
from the_one.tools.shell import ShellTool
from the_one.tools.python_exec import PythonExecTool

async def main():
    r1 = await ShellTool().execute(command='echo shell-ok')
    assert r1 == 'shell-ok', r1
    r2 = await PythonExecTool().execute(code='print(2+2)')
    assert r2 == '4', r2
    # exit-code suffix divergence
    r3 = await ShellTool().execute(command='exit 7')
    assert '[exit code: 7]' in r3, r3
    r4 = await PythonExecTool().execute(code='import sys; sys.exit(3)')
    assert '[exit code' not in r4, r4
    print('OK')

asyncio.run(main())
"

# Smoke: timeout returns promptly (kill+reap propagation)
docker exec the-one python -c "
import asyncio, time
from the_one.tools.shell import ShellTool

async def main():
    t0 = time.monotonic()
    r = await ShellTool().execute(command='sleep 5', timeout=0.3)
    elapsed = time.monotonic() - t0
    assert '[error] Command timed out after 0.3s' in r, r
    assert elapsed < 2.0, f'kill+reap blocked: {elapsed}s'
    print(f'OK ({elapsed:.2f}s)')

asyncio.run(main())
"

# AIAT live smoke (best-effort)
docker exec the-one pytest -m live tests/test_aiat.py -v || echo "AIAT skipped"
```

## Implementation Guidance

1. **Update `the_one/tools/shell.py`**

   ```python
   from __future__ import annotations

   import asyncio
   from typing import Any

   from the_one.platform import run_shell
   from the_one.tools.base import Tool


   class ShellTool(Tool):
       name = "shell"
       description = (
           "Execute a shell command and return its output. "
           "Use for system commands, scripts, git, "
           "package managers, etc."
       )
       parameters = {
           "type": "object",
           "properties": {
               "command": {
                   "type": "string",
                   "description": "The shell command to execute.",
               },
               "timeout": {
                   "type": "integer",
                   "description": "Timeout in seconds (default 120).",
                   "default": 120,
               },
           },
           "required": ["command"],
       }

       async def execute(self, command: str, timeout: int = 120, **kwargs: Any) -> str:
           try:
               stdout, stderr, returncode = await run_shell(command, timeout=timeout)
               output = stdout.decode(errors="replace")
               if stderr:
                   output += f"\n[stderr]\n{stderr.decode(errors='replace')}"
               if returncode != 0:
                   output += f"\n[exit code: {returncode}]"
               return output.strip() or "(no output)"
           except asyncio.TimeoutError:
               return f"[error] Command timed out after {timeout}s"
           except Exception as e:
               return f"[error] {e}"
   ```

2. **Update `the_one/tools/python_exec.py`**

   ```python
   from __future__ import annotations

   import asyncio
   from typing import Any

   from the_one.platform import run_python
   from the_one.tools.base import Tool


   class PythonExecTool(Tool):
       name = "python_exec"
       description = "Execute Python code and return the output. Runs in a subprocess."
       parameters = {
           "type": "object",
           "properties": {
               "code": {"type": "string", "description": "Python code to execute."},
               "timeout": {
                   "type": "integer",
                   "description": "Timeout in seconds (default 60).",
                   "default": 60,
               },
           },
           "required": ["code"],
       }

       async def execute(self, code: str, timeout: int = 60, **kwargs: Any) -> str:
           try:
               stdout, stderr, _ = await run_python(code, timeout=timeout)
               output = stdout.decode(errors="replace")
               if stderr:
                   output += f"\n[stderr]\n{stderr.decode(errors='replace')}"
               return output.strip() or "(no output)"
           except asyncio.TimeoutError:
               return f"[error] Timed out after {timeout}s"
           except Exception as e:
               return f"[error] {e}"
   ```

3. **Write `tests/test_execution_tools.py`**

   ```python
   from __future__ import annotations

   import time

   import pytest

   from the_one.tools.python_exec import PythonExecTool
   from the_one.tools.resolver import _EmptyConfig
   from the_one.tools.shell import ShellTool


   class TestShellTool:
       async def test_happy_path(self) -> None:
           result = await ShellTool().execute(command="echo hi")
           assert result == "hi"

       async def test_stderr_appended(self) -> None:
           result = await ShellTool().execute(command="echo err >&2")
           assert "[stderr]" in result and "err" in result

       async def test_nonzero_exit_code_appended(self) -> None:
           result = await ShellTool().execute(command="exit 7")
           assert "[exit code: 7]" in result

       async def test_empty_output(self) -> None:
           result = await ShellTool().execute(command="true")
           assert result == "(no output)"

       async def test_timeout_returns_promptly(self) -> None:
           # Budget: 3s absorbs tool→platform asyncio overhead and slow-CI
           # scheduler latency. Broken kill+reap blocks for the full 5s sleep,
           # well over this sentinel (regression net, not a tightness target).
           t0 = time.monotonic()
           result = await ShellTool().execute(command="sleep 5", timeout=0.5)
           elapsed = time.monotonic() - t0
           assert result == "[error] Command timed out after 0.5s"
           assert elapsed < 3.0, f"kill+reap blocked: {elapsed}s"


   class TestPythonExecTool:
       async def test_happy_path(self) -> None:
           result = await PythonExecTool().execute(code="print(2+2)")
           assert result == "4"

       async def test_stderr_appended(self) -> None:
           result = await PythonExecTool().execute(
               code="import sys; print('err', file=sys.stderr)"
           )
           assert "[stderr]" in result and "err" in result

       async def test_nonzero_exit_no_exit_code_suffix(self) -> None:
           # Deliberate divergence from ShellTool: PythonExecTool does NOT
           # append [exit code: N]. Preserve this behavior.
           result = await PythonExecTool().execute(
               code="import sys; sys.exit(3)"
           )
           assert "[exit code" not in result
           assert result == "(no output)"

       async def test_empty_output(self) -> None:
           result = await PythonExecTool().execute(code="pass")
           assert result == "(no output)"

       async def test_timeout_returns_promptly(self) -> None:
           # See TestShellTool.test_timeout_returns_promptly for budget rationale.
           t0 = time.monotonic()
           result = await PythonExecTool().execute(
               code="import time; time.sleep(5)", timeout=0.5
           )
           elapsed = time.monotonic() - t0
           assert result == "[error] Timed out after 0.5s"
           assert elapsed < 3.0, f"kill+reap blocked: {elapsed}s"


   class TestExecutionToolInstantiation:
       def test_each_tool_has_empty_config(self) -> None:
           for cls in (ShellTool, PythonExecTool):
               t1 = cls()
               t2 = cls(_EmptyConfig())
               assert isinstance(t1._config, _EmptyConfig)
               assert isinstance(t2._config, _EmptyConfig)
   ```

4. **Run targeted tests, then full suite**:
   ```bash
   make rebuild
   docker exec the-one pytest tests/test_execution_tools.py -v
   make test-unit
   ```

5. **AIAT smoke** (best-effort): `docker exec the-one pytest -m live tests/test_aiat.py -v`. If the L4-documented ScopeMismatch is still in place, document the continued skip in the flight log.

## Edge Cases

- **`asyncio.TimeoutError` propagation**: `run_shell` / `run_python` re-raise `asyncio.TimeoutError` AFTER kill+reap. The tool's `except asyncio.TimeoutError:` clause catches it and returns the formatted error string. Net behavior: caller sees the same error string today and after migration.
- **`asyncio.TimeoutError` is `TimeoutError` in Python 3.11+**: `asyncio.TimeoutError = TimeoutError` since 3.11. The `except asyncio.TimeoutError:` clause works either way; no compatibility concern.
- **Timeout test runtime budget**: each timeout test fires a 5-second `sleep` with `timeout=0.5`; the kill+reap should complete within ~3s wall-clock. The 3s sentinel absorbs tool→platform asyncio overhead and tolerates slow-CI scheduler latency. A broken kill+reap blocks for the full 5s sleep, well over the sentinel — clear regression signal, low false-positive risk.
- **`sys.executable` in the Docker container**: verified during L1 — `sys.executable` returns `/bin/python3` inside the container, byte-for-byte equivalent to the previous hardcoded `"python3"` for the running test environment. The migration is observably no-op on Linux/WSL but unblocks Windows/macOS.
- **Cache freshness contract** (per `/leg` skill section 6): no caches in execution tools. Each `execute()` call invokes the platform helper fresh.
- **State-machine reachability** (per `/leg` skill section 5): no states added or modified by L5. The migration is internal; tool inputs/outputs and error-string formats are unchanged.
- **Generic exception path**: today's tools catch a broad `Exception` and return `[error] {e}`. The migrated form preserves this. Not separately tested (no straightforward way to trigger non-timeout errors without mocking the helpers).
- **L1 anomaly forward-reference**: L1's flight log documents that `run_shell` adds `start_new_session=True` + `killpg(SIGKILL)`. The L5 migration inherits this strictly-better behavior. If a future change to `run_shell` regresses kill+reap, the L5 test_timeout_returns_promptly test catches it (assertion `elapsed < 2.0`).

## Files Affected

- `the_one/tools/shell.py` — execute body migrated; 1-line import added
- `the_one/tools/python_exec.py` — execute body migrated; 1-line import added; hardcoded `"python3"` removed
- `tests/test_execution_tools.py` — created
- `missions/.../flight-log.md` — append L5 progress entry
- `missions/.../flight.md` — check off L5 in Legs section + check off "Execution tools migrated" checkpoint
- `missions/.../legs/05-migrate-execution-tools.md` — set status `landed`

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`** (per agentic-workflow batched-review pattern, Developer does NOT commit; review and commit happen once at flight end):

- [x] All acceptance criteria verified
- [x] New `test_execution_tools.py` tests passing
- [x] Pre-existing unit suite still green (modulo pre-existing CSS-token red)
- [x] AIAT smoke green or skip-with-explanation in flight log
- [x] Update flight-log.md with L5 progress entry
- [x] Set this leg's status to `landed`
- [x] Check off L5 in flight.md (legs section AND "Execution tools migrated" checkpoint)
- [x] Do NOT commit — final commit happens once after L7
