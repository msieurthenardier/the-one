# Squawk 0263: the Windows launch splash never renders, because its HTML exceeds WebView2's NavigateToString limit

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-26
**Completed**: 2026-10-26

## Report
On Windows, every desktop launch logs `[pywebview] WebView2 initialization failed with exception: Value does not fall within the expected range. at … ICoreWebView2.NavigateToString(String htmlContent)`.

The splash HTML from `shell.py::_splash_html` embeds the brand logo as a base64 data URI and comes to 2,328,661 characters, which is over WebView2's documented `NavigateToString` limit of about 2 MB. The splash window opens, but its content is never navigated: the user sees an empty splash frame until the main window appears.

This is not a regression from Mission 32. The splash HTML has embedded the logo since the rebrand (M15 F7/M20).

## Evidence
- The release dry run `40263206440`, `windows-packages-logs/lifecycle/the-one-app.log`: the line appears on every launch (75 lines across the run). The green lifecycle run `40260950171` has it too (12 lines).
- `the_one/interfaces/desktop/shell.py::_splash_html`: "embedding the brand logo as a base64 data URI".
- Found by the Developer fixing the quit-during-boot hang (Mission 32 Flight 4, leg 5). It is unrelated to that hang.

## Corrective Action
The splash now embeds `static/brand/gleepglorp_splash.png`, a 320 px (1.33x the 240 px it is shown at), 125 KB resize of the brand logo, instead of the 1024 px 1.7 MB `gleepglorp_med.png`. `_splash_html` output: 2,328,661 characters before, 168,825 after (both themes), on every platform; the look is unchanged apart from image resolution. The asset was generated with Pillow (`Image.open("gleepglorp_med.png").resize((320, 320), Image.LANCZOS).save("gleepglorp_splash.png", optimize=True)`; the command is in the comment above the splash code in `shell.py`) and is collected by the three specs' `interfaces/web/static/**/*` glob, read through the same `STATIC_DIR` path as before. Also applied the review nit: `_destroy_splash` now claims the teardown under a lock so two threads cannot both call `splash.destroy()`. Candidates considered:
- embed a small logo for the splash only, such as a 128 px PNG (a few KB) or an SVG;
- or load the splash from a file URL instead of `html=`.

Check WebKitGTK and WKWebView, which take the same HTML, for any size effect. Related to squawk 0261 (the macOS blank splash card).

## Verification
- Done: `tests/test_desktop_shell.py` pins `len(_splash_html(theme))` under 256 KB for both themes with the data URI present, and a concurrent-teardown test shows one `destroy()`.
- Done (Flight Director): Windows run `40265814405` (head `f185cb2`): the six launches of the new builds logged zero `NavigateToString` failures. The only three matching lines are one trace from pid 1624, the old v0.11.8 app that L1 installs first.
- A unit test pins the splash HTML well under 2 MB.
- A Windows run (the lifecycle or `windows_test_copy.py`) shows no `NavigateToString` failure in `the-one-app.log`, and a capture shows the splash's logo and text.

## Sign-Off
- **Reviewer:** Haiku, `[HANDOFF:confirmed]` (Mission 32 Flight 4, leg 5).
- **Commit:** `f185cb2`.
- **Field check:** Windows run `40265814405`.

## Disposition
- **Logged** by the Flight Director at Mission 32 Flight 4, leg 5. Its inclusion in v0.12.0 is the operator's call. It is open as routine because the main window still opens normally.
