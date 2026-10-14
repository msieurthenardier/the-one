# Squawk 0205: Chat links open inside the desktop window

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-13
**Completed**: 2026-10-13

## Report
GitHub issue #231. In the Windows desktop app (pywebview + WebView2), clicking an external link in an agent's response, such as `[text](https://...)`, loads the page inside the app window instead of the system browser. The window has no Back button, so the user is stuck on the external page until they restart the app. To reproduce: run `the-one app`, get a reply that contains a link, and click it.

## Evidence
- `the_one/interfaces/web/static/js/markdown.js` renderer, `case NodeType.LINK`: sets `href` and `rel="noopener noreferrer"` but no `target`, so a click navigates the current frame. `tests/browser/test_markdown.py` (~L623-651) pins this exact output.
- pywebview 5.4 `webview/platforms/edgechromium.py::on_new_window_request` already handles `NewWindowRequested`: when `OPEN_EXTERNAL_LINKS_IN_BROWSER` is set (the default is `True`, and the-one never overrides it), it calls `webbrowser.open(uri)`. The gtk, qt and cocoa backends behave the same way.
- Precedent: `areas/studio/mcp-server-editor.js` already renders its `websiteUrl` link with `target="_blank" rel="noopener noreferrer"`, so that link is not affected.
- So no new `/api/window/open-external` endpoint is needed (the issue comment's proposal). A `target="_blank"` on absolute http(s) links lets pywebview do the routing. In a plain browser the link opens in a new tab.

## Corrective Action
`markdown.js` `case NodeType.LINK` now sets `target="_blank"` when the (already safeHref-sanitized) href matches `/^https?:/i`; `rel="noopener noreferrer"` is kept. Fragment (`#...`), root-relative, `mailto:`, `tel:` and the `#` fallback get no target. `safeHref` is unchanged. This lets pywebview's existing new-window routing (`webbrowser.open`) open the system browser, with no new endpoint; in a plain browser it opens a new tab. `tests/browser/test_markdown.py` link expectations updated for the two http(s) cases (the non-http cases already pin the absence of a target).

Grep of `static/js` for other `<a>` construction: only `mcp-server-editor.js:385` builds an external link (already has `target="_blank"`); all others are in-app hash links or breadcrumbs. No other chat-rendering path builds external anchors.

## Verification
- `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python TEST_TIMEOUT=900 bash scripts/run-tests.sh tests/browser/test_markdown.py -m browser -x --timeout 60`: 120 passed.
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py -x --timeout 30`: 273 passed.
- `ruff check` / `ruff format` on test_markdown.py: clean.
- Not verifiable here: the actual click in Windows/WebView2 handing off to the system browser (Linux host); relies on pywebview's documented `OPEN_EXTERNAL_LINKS_IN_BROWSER` default.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet; the batch includes the OAuth sign-in path, 0202), batch review of the 2026-10-13 squawk turnaround
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-10-13` commit on `squawk/turnaround-2026-10-13`. The final gate passed: unit 6287 passed and 14 skipped (the expected count under `THE_ONE_TEST_NETNS=1`); `PARALLEL_RESULT rc=0 total=998s lanes=9 failed=-`, every lane within budget. Not verified on this host: the actual Windows/WebView2 click handing off to the system browser; confirm on the desktop app.

## Disposition
