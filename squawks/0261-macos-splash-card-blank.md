# Squawk 0261: on macOS the splash card shows blank for about 1.5 s

**Status**: deferred
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
Mission 32 Flight 4, leg 2 phase 2b: a policy flag, `BootPolicy.splash_hidden_until_loaded` (True on macOS only). With it set the splash is created `hidden=True` and ordered in only after its own `loaded` plus a 0.15 s settle (`SPLASH_SETTLE`), or after a 2.0 s bound (`SPLASH_LOADED_BOUND`) if `loaded` never arrives, whichever comes first, once. The show is guarded by `_splash_closed`, `_main_shown`, `_splash_blocked()` and `quit_was_requested()`, with a try/except, so it is inert after a destroy, a quit or a stopped loop. Linux, Windows and Other are unchanged (decision-table test).

## Verification
- A hosted `lifecycle` run's L1 +1 s screenshot shows the splash's logo and text (or the painted app), never an empty card; L1 still passes.

Plan:
1. Unit tests now (`tests/test_macos_dock_shell.py`, `tests/test_boot_policy.py`): hidden creation, show only on `loaded`, the bound firing without `loaded`, no show after destroy or quit, no change on the other policies. Done.
2. The hosted L1 screenshot at the Flight Director's AC13 dispatch. A blank card matching Flight 3's known-blank data-URL result on the runner (DD11) is inconclusive, not a pass.
Known edge: if the darwin boot errors before the splash's `loaded` (inside the roughly 2 s window), the splash is never shown; the app terminates anyway, so nothing is lost.
3. If L1 is inconclusive, the contributors' check on real Macs (DD10) before this is marked completed.

## Sign-Off
*(written at completion)*

## Disposition
- **Deferred** at Mission 32 Flight 4's landing (2026-10-26, operator: "Land now, carry it"). The fix shipped in `v0.12.0`/`v0.12.1`; the hosted L1 screenshot was inconclusive (leg 5). **Revisit trigger:** a contributor's real-Mac `macos-app-install` report (step 3, the splash at launch), which completes this squawk or reopens it.
- **Logged** at Mission 32 Flight 3's debrief, on the operator's decision. The P1 fix (Flight 3's HAT) removed the larger symptom, an empty framed main window in front of the splash; this is what is left.
- **Escalate if** the fix needs a change to the shared boot sequence beyond the darwin splash path. Verifying it needs a hosted macOS run.
- **Still deferred** (2026-10-31, operator): a contributor ran the real-Mac `macos-app-install` check and reported it passed, but the splash at first launch was not watched, so this squawk is neither completed nor reopened. The check's expiring `.dmg` no longer matters: any release `.dmg` will do. **Revised revisit trigger:** the next real-Mac launch where someone records step 3's splash observation (logo and text painted, no splash, or an empty card).
- **2026-11-02 triage (Flight Director, Mission 34 squawk turnaround):** stays deferred; the recorded trigger stands (the next real-Mac launch with the splash observed). Nothing can be done on this host.
