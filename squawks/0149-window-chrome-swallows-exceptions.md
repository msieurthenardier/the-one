# Squawk 0149: Window-chrome failures are swallowed without a log line

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-08
**Completed**: —

## Report
Two `except Exception: pass` blocks in the desktop chrome module hide OS-theme detection and DWM apply failures, and theme detection falls back to "dark" without a trace. The `GET /api/window/chrome` HRESULT read-back does not cover these paths, so a tinting failure on a user's machine leaves nothing in the log. Found by routine maintenance 2026-10-08 (finding #25).

## Evidence
- `the_one/interfaces/desktop/chrome.py` ~148-151 and ~337-338

## Corrective Action
*(written at completion)* Expected: replace each `pass` with `log.debug(..., exc_info=True)`, behavior otherwise unchanged.

## Verification
A unit test that forces the detection path to raise and asserts the debug record via `caplog` and the unchanged fallback.

## Sign-Off
*(written at completion)*
