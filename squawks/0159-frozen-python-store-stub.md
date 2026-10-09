# Squawk 0159: Packaged app resolves the Microsoft Store `python.exe` stub as a real interpreter

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-08
**Completed**: 2026-10-08

## Report
From GitHub issue #245, the "Related, lower priority" section. On a Windows host with no real Python installed, `python_exec` returns the Microsoft Store stub's message ("Python was not found; run without arguments to install from the Microsoft Store…", exit 9009) in both host and boxed modes. The app already has a clear, actionable "no Python found" error (`FrozenInterpreterError`), but it never fires here.

## Evidence
- `the_one/platform/interpreter.py:_resolve_frozen_python` returns the first `shutil.which("python3"/"python", path=…)` hit. On Windows, the App Execution Alias stubs under `%LOCALAPPDATA%\Microsoft\WindowsApps\` (`python.exe`, `python3.exe`) are on PATH by default and match, so the stub is returned as the interpreter.
- The stub's exit code 9009 and message come from the alias itself, not from the app.

## Corrective Action
`_resolve_frozen_python` now skips a bare-name (`python3`/`python`) PATH hit whose parent directory is `Microsoft\WindowsApps` (case-insensitive, string-based via `PureWindowsPath`, checked on the path `which` returned before `resolve()`), and continues the search. If nothing real remains, the existing `FrozenInterpreterError` fires, naming the Store alias when one was skipped. Aliases of a real Store-installed Python in that directory are skipped too; `THE_ONE_PYTHON` is the escape hatch and is never filtered. Non-frozen behavior unchanged. No new search location.

## Verification
Three new tests in `tests/test_platform_interpreter.py` (stub only raises; stub then real `python` returns the real one; `THE_ONE_PYTHON` on a WindowsApps path returned unfiltered). `scripts/run-tests.sh tests/test_platform_interpreter.py -x --timeout 30`: 11 passed. `ruff check` / `ruff format --check`: clean. The Reviewer's batch run of the three touched test files gave 25 passed.

## Sign-Off
**Reviewer**: independent Reviewer (Sonnet tier, batched with 0157). It confirmed the stub check runs on `which`'s raw result before `resolve()`, the `THE_ONE_PYTHON` override is never filtered, non-frozen behavior is unchanged, and the error names the Store alias only when one was skipped.
**Verdict**: confirmed (`[HANDOFF:confirmed]`)
**Commit**: `squawk: turnaround 2026-10-08 (3)` on branch `squawk/turnaround-2026-10-08-3`
