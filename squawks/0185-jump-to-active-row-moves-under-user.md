# Squawk 0185: Jump to's active row can move under the user when cold data lands

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-11
**Completed**: —

## Report
When the Jump to palette opens cold, it force-fetches `sessions` (and other
collections) after it is shown. When the data lands, `refresh()` moves the
active row to the new first row unless the user had already moved off it. So
a user who types a query, arrow-keys to a row and presses Enter just before
the cold data lands can pick a different row from the one they saw
highlighted. This is the root cause of squawk 0168's test flake: a seeded
chat titled "New chat" was inserted above "New chat…" and became active.

## Evidence
- Found during the 2026-10-11 turnaround's investigation of squawk 0168.
  Failing runs never called `openPicker`; Enter joined the inserted chat row.
- `static/js/jump-to.js`: `open()` force-gets the store collections, then
  re-renders. `static/js/ui/search-list.js` `refresh()` re-activates the
  first option.
- The fix direction: keep the active option by **id** across a source
  refresh. If the previously active id is still present, keep it active.
  Otherwise fall back to the first option. This may be a small `searchList`
  contract change: re-check the contract tests in both engines.

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
