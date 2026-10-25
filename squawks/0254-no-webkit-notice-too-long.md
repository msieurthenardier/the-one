# Squawk 0254: the no-WebKit notification is too long for GNOME's banner

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-24
**Completed**: —

## Report
When the Linux desktop app falls back to the browser because WebKitGTK is missing (DD14), it sends a one-string notification of about 120 characters. GNOME's banner cuts single strings this long off. Mission 32 Flight 2 hit this twice: the no-tray notice (leg 11) and the tray notice (the HAT). Both were fixed by splitting them into a short title and a body of at most 60 characters. This third notice was not changed.

## Evidence
- `the_one/interfaces/desktop/shell.py::_NO_WEBVIEW_BODIES["webkit"]` — "GleepGlorp AI opened in your browser because WebKitGTK isn't installed. Install gir1.2-webkit2-4.1 for its own window."
- `["gtk"]` (about 87 characters) and `["gi"]` (about 77) are also over 60.
- The pattern to follow: `_TRAY_NOTICE_TITLE`/`_TRAY_NOTICE_BODY` and `_NO_TRAY_NOTICE_SUMMARY`. The bound is pinned in `tests/test_desktop_tray.py` (tray) and `test_none_mode_close_hides_and_notices_once` (no-tray).
- Flight 2 debrief, recommendation 3.

## Corrective Action
*(written at completion)*

## Verification
- Every no-WebKit body has a short title (e.g. "GleepGlorp AI opened in your browser") and a body of at most 60 characters that still names what to install.
- One unit test asserts the 60-character bound over every desktop notice constant, so a new notice cannot regress it.

## Sign-Off
*(written at completion)*

## Disposition
- **Logged** at Mission 32 Flight 2's debrief, on the operator's decision.
