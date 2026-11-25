# Squawk 0419: The drawer keeps a dead `MediaQueryList.addListener` fallback

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-24
**Completed**: —

## Report

The GleepGlorp drawer shell falls back to the deprecated `mq.addListener` when `addEventListener` is missing on a `MediaQueryList`. Every engine the app supports has `addEventListener` there: Chromium, WebKit, WebKitGTK, WebView2 and WKWebView. So the branch is dead code (the project's `removing-dead-code` convention). Found by the 2026-11-24 routine maintenance (JS Inspector).

## Evidence
- `static/js/gleepglorp-drawer/shell.js` (about line 261): `else if (typeof mq.addListener === 'function') mq.addListener(applyMode);`.

## Corrective Action
*(written at completion)*

## Verification
The fallback branch is removed. The `gleepglorp-chat` lane, the drawer contract tests and `tests/test_ui_guards.py` pass.
