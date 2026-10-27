# Squawk 0185: Jump to's active row can move under the user when cold data lands

**Status**: in-progress
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
Mission 31 Flight 6 leg 03b. The operator chose option (a) on 2026-10-26: keep the highlighted row **by identity** across refreshes, whether or not the user moved, rather than "the first row follows the data" (M25 DD10, now superseded).
- `js/ui/search-list.js`: `refresh()` with an unchanged query keeps the active option by `(group index, id)` while it still exists, scrolls it into view with `nearest`, and falls back to the first option when it is gone; an input event (a changed query) still activates the first match. The inline variant's `keepScroll` is unified with it (it now only means "restore the offset, do not scroll"); there is one keep rule.
- `js/jump-to.js`: `lastFirstId` and the "keep only when the user moved off the first row" logic are removed; `refresh(entry)` just calls `list.refresh()`.
- The change reaches every `searchList`: the agent picker, Jump to and the Date and time zone list.

## Verification
- Contract tests, Chromium and WebKit (`test_ui_search_list_contract.py`, written and seen failing before the fix): an arrowed-to row stays active and in view when a row is added above it; a cold refresh with no move keeps the highlighted row; with the same id in two groups the active row stays in its own group; a vanished active option falls back to the first; a query change (and an input event with the same value) activates the first match.
- `test_flow_jump_to.py::test_cold_data_landing_never_moves_the_highlighted_row` holds the palette's chats request, opens it ("New chat…" is first), releases the request, and asserts that newer chat rows appear above while "New chat…" is still the one active row. The pinned DD10 tests were rewritten deliberately (see the flight log), and `_jump`'s wait for the chats to load, the workaround for squawk 0168's flake, is removed.
- `tests/behavior/jump-to-palette.md` step 2 re-authored (the highlighted row does not move when data lands).

## Sign-Off
*(written at completion)*
