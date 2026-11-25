# Squawk 0408: The tools page's one-shot `keepFocus` stays set if a fill's navigation throws

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-24
**Completed**: —

## Report

Mission 36 Flight 5 (Leg 4b) added `App.admin.toolsPage.keepFocus`. The `tool_config` kind's
`beforeNavigate` sets it, so the editor's title does not take focus from the drawer composer
during a fill, and `afterNavigate` clears it. If anything between the two throws or returns early,
the flag stays `true`. Every later real navigation to a tool's editor then skips the title focus,
until a fill completes. The flag has no test. Found by the Flight 5 debrief (Developer).

## Evidence
- `static/js/areas/admin/tool-config-kinds.js:43-44`:
  `beforeNavigate: function () { App.admin.toolsPage.keepFocus = true; }` and the matching
  `afterNavigate`.
- `static/js/areas/admin/tools-page.js:20` `keepFocus: false`, and `:150-156`, where
  `revealItem` reads it.

## Corrective Action
*(written at completion)*

## Verification
The flag is cleared on every exit of the fill's navigation (a `finally` in the caller, or the flag
passed as an argument rather than held as module state). A test fails a fill's navigation midway
and shows that the next ordinary open of a tool's editor focuses its title.
