# Squawk 0375: Every MCP server tile in an agent's Tools tab has an Add button named only "+ Add row"

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-17
**Completed**: —

## Report
Found in sortie 18's HAT. In an agent's Tools tab, each expanded MCP server tile that is in override mode has its own "+ Add row" button, and every one has the same accessible name. A voice-control user saying "click Add row" gets several targets, and a screen-reader user hears identical buttons with only the surrounding tile for context.

Sortie 18 gave the two tables of the Library MCP server editor distinct names ("Add row to Arguments", "Add row to Environment variables" or "Add row to Headers") through the table control's new `addAriaLabel` option, with the visible label unchanged. The Tools tab was left out because it is another page.

Expected: each tile's Add button has an accessible name that says which table and which server it belongs to (the tile's other buttons already do, for example "Override headers for {server}"), with the visible "+ Add row" unchanged.

## Evidence
- `the_one/interfaces/web/static/js/areas/studio/mcp-agent-credentials.js` — builds one `App.ui.keyValueTable` per tile with an `addTestid` of the form `mcp-agent-cred-add-{id}` and no accessible name for the Add button; the tile's Override, Cancel, Save and Test buttons carry "… for {source}" names.
- `the_one/interfaces/web/static/js/ui/key-value-table.js` — `addAriaLabel` (sortie 18) sets the Add button's `aria-label` and is inert when not passed.
- `sorties/18-mcp-arguments-as-rows/flight-log.md`, `### hat-and-alignment` — the design review that named this page and the decision to leave it out.

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
