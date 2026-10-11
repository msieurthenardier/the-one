# Squawk 0178: Add a global `[hidden] { display: none !important }` reset

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-11
**Completed**: —

## Report
An author `display` rule that defeats the `hidden` attribute has now needed a local fix four times: `#app-sidebar`, `#chat-drawer`, `.chat-chrome`, and `.date-time-page [hidden]` (M28 F2).

## Evidence
`static/css/base.css` (base layer). The fix: one reset rule in the base layer. Remove the page-local copies once the browser lanes stay green.

Logged from the Mission 28 flight debriefs.

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
