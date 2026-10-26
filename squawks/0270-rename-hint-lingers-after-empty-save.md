# Squawk 0270: The rename hint stays after saving an empty value under a renamed key

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-26
**Completed**: —

## Report
In the MCP editor, rename the key of a stored sensitive header, which clears the value and shows "Type the value again for the new name.". Then Save without typing a value.

After the save the form is clean and the server stores `""` for the new key. Yet the row still shows "Type the value again for the new name." and a visible Show button, as if something were pending. After a save, the row should read as an ordinary empty value, with no rename prompt.

Found in the `mcp-sensitive-headers-round-trip` behavior test (Mission 31 Flight 5, step 7). The operator approved logging it at the Flight 5 debrief.

## Evidence
- `the_one/interfaces/web/static/js/ui/key-value-table.js:checkRename` sets `ctl.setHint(RENAME_HINT)`.
- There appears to be no path that clears the hint when the row is re-baselined after a successful Save with the value still empty.
- Run log: `tests/behavior/mcp-sensitive-headers-round-trip/runs/2026-10-26-15-13-47.md`, checkpoint 7.

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
