# Squawk 0270: The rename hint stays after saving an empty value under a renamed key

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-26
**Completed**: 2026-10-28 (signed off at the Mission 31 Flight 6 landing)

## Report
In the MCP editor, rename the key of a stored sensitive header, which clears the value and shows "Type the value again for the new name.". Then Save without typing a value.

After the save the form is clean and the server stores `""` for the new key. Yet the row still shows "Type the value again for the new name." and a visible Show button, as if something were pending. After a save, the row should read as an ordinary empty value, with no rename prompt.

Found in the `mcp-sensitive-headers-round-trip` behavior test (Mission 31 Flight 5, step 7). The operator approved logging it at the Flight 5 debrief.

## Evidence
- `the_one/interfaces/web/static/js/ui/key-value-table.js:checkRename` sets `ctl.setHint(RENAME_HINT)`.
- There appears to be no path that clears the hint when the row is re-baselined after a successful Save with the value still empty.
- Run log: `tests/behavior/mcp-sensitive-headers-round-trip/runs/2026-10-26-15-13-47.md`, checkpoint 7.

## Corrective Action
M31 F6 L03c: `key-value-table.js` `setRow` now calls `setHint(null)` on a secret column's control whenever the patch carries that column's `storedKey` (a re-baseline), so the one-off rename hint no longer survives a Save. A plain value or unrelated patch leaves the hint (existing test `test_unrelated_set_row_does_not_wipe_the_rename_hint` still passes). Note: the leg's "no Show button" expectation does not hold: an empty sensitive row is an ordinary new secret cell and keeps its normal eye; only the stale hint was the defect. Status left in-progress for the flight-end sign-off.

## Verification
Failing first: `test_set_row_rebaseline_clears_the_rename_hint` (both engines) failed with the fix reverted and passes with it. The MCP editor test `test_kv_rename_hint_and_eye_clear_after_save_with_empty_value` (rename a stored header, save with empty value, no stale hint) passes with the fix; its first run on reverted code failed only on the Show-button assertion that was then dropped as wrong, so its hint assertion was not seen failing in the editor.

## Sign-Off
