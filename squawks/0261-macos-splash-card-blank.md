# Squawk 0261: on macOS the splash card shows blank for about 1.5 s

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-25
**Completed**: —

## Report
On macOS, the frameless 400×300 splash ("GleepGlorp AI — starting") appears at launch with its dark card drawn, but its logo and text have not painted. About 1.6 s later the main window replaces it (Mission 32 Flight 3's P1 fix shows the main window only after its page loads). The user sees an empty branded card instead of the logo and "starting" text. The splash CSS has no fade-in or delay on the logo or text, so the late paint is most likely the splash's own WKWebView starting up.

## Evidence
- The hosted lifecycle run `40228973240` (`macos-packages.yml`), `lifecycle/L1/first-paint-+1s.png`: the splash card with no content; `app.log`: `macos: main window shown after page load (1.6s)`.
- `the_one/interfaces/desktop/shell.py::_splash_html` (the logo as a data URI, the text, a `slide` animation only on the progress bar) and the splash's `webview.create_window(..., html=_splash_html(launch_theme), frameless=True, ...)`.

## Corrective Action
*(written at completion)*. Candidates, to measure first:
- show the splash only after its own `loaded` (as the main window now does), with a short bound;
- or make the splash's first paint cheaper (a smaller inline logo, or a native-drawn first frame).

## Verification
- A hosted `lifecycle` run's L1 +1 s screenshot shows the splash's logo and text (or the painted app), never an empty card; L1 still passes.

## Sign-Off
*(written at completion)*

## Disposition
- **Logged** at Mission 32 Flight 3's debrief, on the operator's decision. The P1 fix (Flight 3's HAT) removed the larger symptom, an empty framed main window in front of the splash; this is what is left.
- **Escalate if** the fix needs a change to the shared boot sequence beyond the darwin splash path. Verifying it needs a hosted macOS run.
