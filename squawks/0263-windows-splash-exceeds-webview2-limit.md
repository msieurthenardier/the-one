# Squawk 0263: the Windows launch splash never renders, because its HTML exceeds WebView2's NavigateToString limit

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-26
**Completed**: —

## Report
On Windows, every desktop launch logs `[pywebview] WebView2 initialization failed with exception: Value does not fall within the expected range. at … ICoreWebView2.NavigateToString(String htmlContent)`.

The splash HTML from `shell.py::_splash_html` embeds the brand logo as a base64 data URI and comes to 2,328,661 characters, which is over WebView2's documented `NavigateToString` limit of about 2 MB. The splash window opens, but its content is never navigated: the user sees an empty splash frame until the main window appears.

This is not a regression from Mission 32. The splash HTML has embedded the logo since the rebrand (M15 F7/M20).

## Evidence
- The release dry run `40263206440`, `windows-packages-logs/lifecycle/the-one-app.log`: the line appears on every launch (75 lines across the run). The green lifecycle run `40260950171` has it too (12 lines).
- `the_one/interfaces/desktop/shell.py::_splash_html`: "embedding the brand logo as a base64 data URI".
- Found by the Developer fixing the quit-during-boot hang (Mission 32 Flight 4, leg 5). It is unrelated to that hang.

## Corrective Action
*(written at completion)*. Candidates:
- embed a small logo for the splash only, such as a 128 px PNG (a few KB) or an SVG;
- or load the splash from a file URL instead of `html=`.

Check WebKitGTK and WKWebView, which take the same HTML, for any size effect. Related to squawk 0261 (the macOS blank splash card).

## Verification
- A unit test pins the splash HTML well under 2 MB.
- A Windows run (the lifecycle or `windows_test_copy.py`) shows no `NavigateToString` failure in `the-one-app.log`, and a capture shows the splash's logo and text.

## Sign-Off
*(written at completion)*

## Disposition
- **Logged** by the Flight Director at Mission 32 Flight 4, leg 5. Its inclusion in v0.12.0 is the operator's call. It is open as routine because the main window still opens normally.
