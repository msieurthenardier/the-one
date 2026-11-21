# Squawk 0379: The Key-value table's catalogue row names two of its five users

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-17
**Completed**: 2026-11-21

## Report
The Key-value table row in `docs/ui-control-inventory.md` says where the control is used: "the connector editor's channel map is its first consumer (M31 F3 L07b) and the MCP editor's environment variables and headers table is its second (M31 F5 L07)". The control now has five users. The agent credentials tile (sortie 09), the secret editor (sortie 10) and the MCP editor's Arguments rows (sortie 18) are missing from that sentence. Found in the sortie 18 debrief.

Needed: list all five in the row, so a reader changing the control knows which lanes to run. Why now: sortie 18 added six options to this control on the claim "inert for existing consumers", and the catalogue is where that list of consumers should be read from.

## Evidence
- `docs/ui-control-inventory.md` — the row that starts "Key-value table (`App.ui.keyValueTable`", location column.
- Callers of `keyValueTable(` under `the_one/interfaces/web/static/js/areas/`: `studio/connector-editor.js`, `studio/mcp-env-headers.js`, `studio/mcp-agent-credentials.js`, `studio/secret-editor.js`, `studio/mcp-connection-fields.js`.

## Corrective Action
The Key-value table row's location column in `docs/ui-control-inventory.md` now lists all five consumers (grep-confirmed) with their files and browser lanes: connector editor channel map, MCP env/headers table, MCP Arguments rows, agent Tools tab credentials tile, secret editor. Doc-only.

## Verification
Grepped `keyValueTable(` callers outside `js/ui/`: the five files above. Ran `scripts/run-tests.sh tests/test_ui_control_inventory.py tests/test_ui_ownership.py tests/test_ui_emitted_classes.py -x --timeout 60`: 32 passed. (Lane names are from the lane descriptions, not each verified with `--list`.)

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet; the security tier, since the batch changed the shell-write hook and CLAUDE.md's safety rules), batch review of squawks 0368, 0379, 0384, 0385, 0391-0397
**Verdict**: confirmed
**Commit**: `squawk: turnaround 2026-11-21` on squawk/turnaround-2026-11-21
