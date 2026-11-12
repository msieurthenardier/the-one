# Squawk 0347: windows_test_copy.py launch drops dev mode and refuses a relaunch

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-11
**Completed**: —

## Report
Two snags in `scripts/windows_test_copy.py launch`, both met in Mission 35 Flight 2 leg 8 Part B:
1. The launched test copy does not receive `THE_ONE_DEV_MODE`, so the mock provider is refused ("Mock provider type requires THE_ONE_DEV_MODE=true") and a session must seed an unused real provider instead.
2. After the test copy quits (tray Quit, `the-one quit`, `POST /api/window/quit`), its watchdog stays alive, and `launch` refuses with "a recorded tree 'main' is still live: run `stop` first", so every quit-and-relaunch cycle needs a `stop` in between.

## Evidence
- `scripts/windows_test_copy.py`: no `THE_ONE_DEV_MODE` in the launch environment (grep finds none); `:1869` `raise HelperError(f"a recorded tree {tid!r} is still live: run `stop` first")`.
- Flight log, "Part B done" (apparatus snags).

## Corrective Action
*(written at completion)*

## Verification
A unit test in `tests/test_windows_test_copy.py` pins that `launch --dev-mode` (or an explicit opt-in) puts `THE_ONE_DEV_MODE=true` in the child environment, and that `launch` treats a tree whose app process has exited and only its watchdog remains as relaunchable (stopping the stale watchdog by its recorded identity).

## Sign-Off
*(written at completion)*
