# Squawk 0348: the isolated-Chromium widget test can skip silently

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-11
**Completed**: —

## Report
`tests/browser/test_flow_chat_widgets_isolated.py` is the only guard for the Mission 35 Flight 2 HAT defect where a sandboxed widget frame has 0 width at script start under Chromium site isolation (DD2 amendment). It skips when an isolating Chromium cannot launch or when its probe does not show the early 0 width, so on a host or CI image without that Chromium it becomes a silent no-op and the regression net disappears unnoticed.

## Evidence
- `tests/browser/test_flow_chat_widgets_isolated.py:56` `pytest.skip(f"cannot launch an isolating Chromium: {exc}")`, `:65` `pytest.skip(f"this Chromium does not isolate sandboxed frames (early width {early})")`.
- Precedent: `THE_ONE_REQUIRE_WEBKIT=1` turns a WebKit launch failure into a failure (`tests/browser/_ui_engines.py`).

## Corrective Action
*(written at completion)*

## Verification
With the require flag set (the existing `THE_ONE_REQUIRE_WEBKIT=1` or a new `THE_ONE_REQUIRE_ISOLATED_CHROMIUM=1`), a launch failure or a non-isolating probe fails the test; without it the test still skips. CLAUDE.md's `chats-widgets` lane note names the flag.

## Sign-Off
*(written at completion)*
