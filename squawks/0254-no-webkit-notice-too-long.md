# Squawk 0254: the no-WebKit notification is too long for GNOME's banner

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-24
**Completed**: 2026-11-03

## Report
When the Linux desktop app falls back to the browser because WebKitGTK is missing (DD14), it sends a one-string notification of about 120 characters. GNOME's banner cuts single strings this long off. Mission 32 Flight 2 hit this twice: the no-tray notice (leg 11) and the tray notice (the HAT). Both were fixed by splitting them into a short title and a body of at most 60 characters. This third notice was not changed.

## Evidence
- `the_one/interfaces/desktop/shell.py::_NO_WEBVIEW_BODIES["webkit"]` — "GleepGlorp AI opened in your browser because WebKitGTK isn't installed. Install gir1.2-webkit2-4.1 for its own window."
- `["gtk"]` (about 87 characters) and `["gi"]` (about 77) are also over 60.
- The pattern to follow: `_TRAY_NOTICE_TITLE`/`_TRAY_NOTICE_BODY` and `_NO_TRAY_NOTICE_SUMMARY`. The bound is pinned in `tests/test_desktop_tray.py` (tray) and `test_none_mode_close_hides_and_notices_once` (no-tray).
- Flight 2 debrief, recommendation 3.

## Corrective Action
`the_one/interfaces/desktop/shell.py`: added `_NO_WEBVIEW_TITLE` ("GleepGlorp AI opened in your browser", 36 chars) and shortened `_NO_WEBVIEW_BODIES` to 52/43/31 chars (webkit: "WebKitGTK is missing. Install gir1.2-webkit2-4.1."); the browser-fallback notification now sends the title and body separately. `docs/linux-install.md` only describes the notice generally, so it needed no change. Tests: `test_fallback_notifies_before_opening_browser` updated (title, needle, body <= 60); new `test_every_desktop_notice_fits_a_gnome_banner` in `tests/test_desktop_shell.py` bounds every `*NOTICE*`/`*NO_WEBVIEW*` string constant in `shell.py` and `window_control.py` at 60.

## Verification
- Result: `run-tests.sh tests/test_desktop_{shell,tray,session_state,split_guard}.py` 187 passed; ruff check/format clean; full unit tier see report. Falsified (yes): lengthening the "gi" body made the bound test and the fallback test fail; reverted by edit.
- Every no-WebKit body has a short title (e.g. "GleepGlorp AI opened in your browser") and a body of at most 60 characters that still names what to install.
- One unit test asserts the 60-character bound over every desktop notice constant, so a new notice cannot regress it.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches the shell-write hook, `App.safeUrl`, the encryption status count and the credential docs), batch review of the 2026-11-02-2 squawk turnaround, scoped to the diff. Its one blocking finding (0135's Dockerfile `uv venv` line) and the non-blocking items were fixed in a fix pass, which a Haiku Reviewer re-checked: `[HANDOFF:confirmed]`. An Accessibility Reviewer (Sonnet) confirmed the UI changes (0239, 0289, 0290, 0291, 0254). The final gate on the batch tree: `THE_ONE_TEST_NETNS=1 make test-unit` 8738 passed, 15 skipped (219 s, start load 0.48); browser `--parallel 3` `PARALLEL_RESULT rc=1 total=1774s lanes=17 failed=chats-transcript` (start load 0.72). The one failure is new squawk 0315, which passed 3 of 3 isolated runs.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02-2` commit on `squawk/turnaround-2026-11-02-2`.

## Disposition
- **Logged** at Mission 32 Flight 2's debrief, on the operator's decision.
