# Squawk 0149: Window-chrome failures are swallowed without a log line

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-08
**Completed**: 2026-10-08

## Report
Two `except Exception: pass` blocks in the desktop chrome module hide OS-theme detection and DWM apply failures, and theme detection falls back to "dark" without a trace. The `GET /api/window/chrome` HRESULT read-back does not cover these paths, so a tinting failure on a user's machine leaves nothing in the log. Found by routine maintenance 2026-10-08 (finding #25).

## Evidence
- `the_one/interfaces/desktop/chrome.py` ~148-151 and ~337-338

## Corrective Action
In `the_one/interfaces/desktop/chrome.py`, three silent sites now emit `log.debug(..., exc_info=True)` through the module logger: the OS-theme detection fallback to "dark" in `os_theme()`, the `winreg.CloseKey` swallow beside it, and the `_record` swallow inside `_ui_apply`'s error handler. Return values and fallbacks are unchanged.

## Verification
Two new tests in `tests/test_window_chrome.py` force `winreg` to raise and assert the unchanged result ("dark" / "light") plus one DEBUG record with `exc_info` from the chrome logger. Falsified by restoring `pass` at the two `os_theme` sites: the detection test failed, then passed again with the fix restored. `tests/test_window_chrome.py` passes (51), and `ruff check` and `ruff format --check` are clean. The `_record` site is not separately pinned.

## Sign-Off

**Reviewer**: independent batch Reviewer (Sonnet tier: the batch touches the credential-gated test seams and secret echo in 422 bodies), plus a Haiku re-review of the one fix-loop change (`tests/test_store_static.py`, a static guard that pinned the pre-0145 fetch literal); unit suite 5647 passed, 1 failed before the guard fix (the guard, re-run green after), 16 skipped (10 Windows-only, 2 root-only under `THE_ONE_TEST_NETNS=1`, 4 `requires_bwrap` sandbox skips included by the run's marker set); agents lane 154 passed, 2 skipped; shared lane 465 passed; ruff clean
**Verdict**: confirmed (`[HANDOFF:confirmed]`)
**Commit**: `squawk: turnaround 2026-10-08` on branch `squawk/turnaround-2026-10-08`
