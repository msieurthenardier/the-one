# Squawk 0379: The Key-value table's catalogue row names two of its five users

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-17
**Completed**: —

## Report
The Key-value table row in `docs/ui-control-inventory.md` says where the control is used: "the connector editor's channel map is its first consumer (M31 F3 L07b) and the MCP editor's environment variables and headers table is its second (M31 F5 L07)". The control now has five users. The agent credentials tile (sortie 09), the secret editor (sortie 10) and the MCP editor's Arguments rows (sortie 18) are missing from that sentence. Found in the sortie 18 debrief.

Needed: list all five in the row, so a reader changing the control knows which lanes to run. Why now: sortie 18 added six options to this control on the claim "inert for existing consumers", and the catalogue is where that list of consumers should be read from.

## Evidence
- `docs/ui-control-inventory.md` — the row that starts "Key-value table (`App.ui.keyValueTable`", location column.
- Callers of `keyValueTable(` under `the_one/interfaces/web/static/js/areas/`: `studio/connector-editor.js`, `studio/mcp-env-headers.js`, `studio/mcp-agent-credentials.js`, `studio/secret-editor.js`, `studio/mcp-connection-fields.js`.

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
