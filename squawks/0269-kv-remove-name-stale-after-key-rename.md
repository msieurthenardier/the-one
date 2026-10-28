# Squawk 0269: The key-value row's remove button keeps the saved key's name after an unsaved rename

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-26
**Completed**: 2026-10-28 (signed off at the Mission 31 Flight 6 landing)

## Report
In the MCP editor's Headers or Environment variables table, change a row's key without saving, for example `Authorization` to `X-Auth`. The row's remove button is still announced "Remove Authorization", although the key now reads `X-Auth`. It reads "Remove X-Auth" only after a Save, which re-renders the row.

Found by the Validator of the `mcp-sensitive-headers-round-trip` behavior test (Mission 31 Flight 5, step 6). The operator approved logging it at the Flight 5 debrief.

## Evidence
- `the_one/interfaces/web/static/js/areas/studio/mcp-env-headers.js:removeLabel`: `return key ? 'Remove ' + key : 'Remove row ' + n;`
- `the_one/interfaces/web/static/js/ui/key-value-table.js:removeName`: called when a row is built, and apparently not re-run when the key input changes.
- Run log: `tests/behavior/mcp-sensitive-headers-round-trip/runs/2026-10-26-15-13-47.md`, checkpoint 6, Validator notes.

## Corrective Action
M31 F6 L03c: `key-value-table.js` `onInput` on the key column now refreshes `row.remove`'s `aria-label` from `removeName(row, idx + 1)`, so the name follows the typed key (an empty key keeps "Remove row n"). Status left in-progress for the flight-end sign-off.

## Verification
Failing first (reverted fix seen failing): `test_ui_key_value_table_contract.py::test_remove_name_follows_a_typed_key` (Chromium and WebKit) and `test_flow_studio_mcp_editor_kv_chips.py::test_kv_remove_name_follows_a_typed_key`. Passing with the fix.

## Sign-Off
