# Squawk 0347: windows_test_copy.py launch drops dev mode and refuses a relaunch

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-11
**Completed**: 2026-11-13

## Report
Two snags in `scripts/windows_test_copy.py launch`, both met in Mission 35 Flight 2 leg 8 Part B:
1. The launched test copy does not receive `THE_ONE_DEV_MODE`, so the mock provider is refused ("Mock provider type requires THE_ONE_DEV_MODE=true") and a session must seed an unused real provider instead.
2. After the test copy quits (tray Quit, `the-one quit`, `POST /api/window/quit`), its watchdog stays alive, and `launch` refuses with "a recorded tree 'main' is still live: run `stop` first", so every quit-and-relaunch cycle needs a `stop` in between.

## Evidence
- `scripts/windows_test_copy.py`: no `THE_ONE_DEV_MODE` in the launch environment (grep finds none); `:1869` `raise HelperError(f"a recorded tree {tid!r} is still live: run `stop` first")`.
- Flight log, "Part B done" (apparatus snags).

## Corrective Action
1. `scrub_env` gained a `dev_mode` parameter and `launch` an explicit `--dev-mode` flag; only then is `THE_ONE_DEV_MODE=true` put in the child environment (an inherited value is still scrubbed, so the allowlist model is unchanged).
2. `op_launch` now treats a recorded tree whose identity-confirmed live members are only its watchdog (`_only_watchdog_live`) as stale: it calls the existing `op_stop` for that tree (which kills the watchdog through `_kill_one`'s identity check, audits it, and removes the record), re-checks liveness, and otherwise still refuses. A tree with any live app or WebView2 member still refuses with "run `stop` first". `the_one/agents.md` "Windows test copy" lists the flag and behaviour.

## Verification
Unit tests in `tests/test_windows_test_copy.py` (`test_scrub_env_dev_mode_is_explicit_opt_in`, `test_launch_stops_a_watchdog_left_after_the_app_exited`, `test_launch_still_refuses_a_tree_whose_app_is_live`): 163 passed. Each fix falsified by editing it out (2 failures: the env test and the watchdog test) and restored. Not run end to end on Windows.

Original plan: A unit test in `tests/test_windows_test_copy.py` pins that `launch --dev-mode` (or an explicit opt-in) puts `THE_ONE_DEV_MODE=true` in the child environment, and that `launch` treats a tree whose app process has exited and only its watchdog remains as relaunchable (stopping the stale watchdog by its recorded identity).

## Sign-Off
**Reviewer**: batch Reviewer (Haiku), independent of the implementers.
- `--dev-mode` is opt-in, and `scrub_env` still removes every inherited `THE_ONE_*`.
- The watchdog-only path uses the existing `op_stop`, which goes through `_kill_one`'s identity check.
- No kill by name was added, and the live-app refusal is unchanged.

Non-blocking notes from the Reviewer, not logged:
- The two new launch tests fake `op_stop`.
- `op_stop` reports complete even when a kill is refused, so that edge gives the generic "still live" message.

Not run on the real Windows host.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-13` commit on `squawk/turnaround-2026-11-13`
