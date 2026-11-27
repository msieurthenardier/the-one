# Squawk 0438: the browser fixtures' app-spawn ready wait (15 s) times out under load

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-27
**Completed**: —

## Report

In the squawk 0428 verification run (full browser gate, `--parallel 3`, load 8 to 20), 14 of 15 setup errors were `TimeoutError: App at http://127.0.0.1:<port> not ready within 15.0s`. That means the test's uvicorn subprocess did not answer `/api/live` within 15 s of spawn. This is before any `_nav` call, so it is not the 0428 class. All 14 passed when re-run in isolation at load 8. Under load, each one costs a whole test (setup error) and turns its lane red.

## Evidence
- `tests/browser/conftest.py::_wait_for_ready`: `timeout: float = 15.0` default. The spawn site (`tests/browser/conftest.py:283`) passes `timeout=15.0` explicitly. The function already fails fast if the subprocess exits, so a longer timeout only costs time when the app is genuinely slow to start, not on crashes.
- 0428 run record: `squawks/0428-nav-goto-has-no-boot-ready-wait.md`, Verification ("14 of the errors were `App subprocess ... not ready within 15.0s`").

## Corrective Action
*(written at completion)* Suggested direction: raise the spawn-ready timeout at `conftest.py:283`, for example to 45 s, perhaps with an env override. Since `_wait_for_ready` already raises immediately when the process dies, the larger value costs nothing on a fast or crashing start. Check other `_wait_for_ready` callers (grep `tests/`) for the same 15 s.

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
