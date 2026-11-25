# Squawk 0419: The drawer keeps a dead `MediaQueryList.addListener` fallback

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-24
**Completed**: 2026-11-25

## Report

The GleepGlorp drawer shell falls back to the deprecated `mq.addListener` when `addEventListener` is missing on a `MediaQueryList`. Every engine the app supports has `addEventListener` there: Chromium, WebKit, WebKitGTK, WebView2 and WKWebView. So the branch is dead code (the project's `removing-dead-code` convention). Found by the 2026-11-24 routine maintenance (JS Inspector).

## Evidence
- `static/js/gleepglorp-drawer/shell.js` (about line 261): `else if (typeof mq.addListener === 'function') mq.addListener(applyMode);`.

## Corrective Action
Removed the `mq.addListener` fallback in `static/js/gleepglorp-drawer/shell.js`; the width listener is now `if (mq) mq.addEventListener('change', applyMode);`.

## Verification
The fallback branch is removed. The `gleepglorp-chat` lane, the drawer contract tests and `tests/test_ui_guards.py` pass.

Result: `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane gleepglorp-chat -x`: 84 passed. `tests/test_ui_guards.py`, `test_token_definitions.py`, `test_design_tokens_a11y.py`: 396 passed.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet), batch review of squawks 0411-0419; Accessibility Reviewer: no accessibility effect
**Verdict**: confirmed
**Commit**: `squawk: turnaround 2026-11-25` on squawk/turnaround-2026-11-25
