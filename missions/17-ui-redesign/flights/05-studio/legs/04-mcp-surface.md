# Leg: mcp-surface

**Status**: completed
**Flight**: [Studio Re-skin](../flight.md)

## Objective

Re-skin mcp-server-editor.js + mcps-tab.js + mcp-servers-grid.js to the vocabulary; migrate their `.field-row`→`.field-group` (nominally 12 — expect grep-inflation, real count likely lower per Legs 1-3) with label-association. Completes the studio editor re-skin.

## Scope (flight DDs authoritative)

- mcp-server-editor.js (MCP source editor: name/type/command/env kv-table) + mcps-tab.js (agent-editor MCPs tab: chip-list attach + per-source tool discovery) + mcp-servers-grid.js → vocabulary (consume F3 buttons/tiles/tabs/fields; reuse Leg 2's shared `.field-group-label` for info-icon fields).
- `.field-row`→`.field-group` with full label-association (unique id, `label.for`, invalid→`aria-describedby`→`.field-error` id). Count is nominally 12; verify real render sites (Legs 1-3 all found grep-inflation: 7→6, 22→17, 8→4). The env kv-table rows may be a legit dense/tabular exception — keep label-left there if migrating breaks the table, documented.
- The `.area-studio .field-error` gutter exception is ALREADY DELETED (Leg 2 removed it as the last consumer) — just verify no regression; nothing to delete here.
- Any washed mcp surface carrying text gets a composite-a11y gate (the mcp-auth-required-notice at studio.css:695 is SOLID `--surface-elevated` → NOT composite-gated, fg-ladder covers it; check for any actual alpha wash).

## Acceptance Criteria

- [x] mcp-server-editor + mcps-tab + mcp-servers-grid render the vocabulary, both themes (CDP visual + focus) — mcps-tab + grid already pure vocabulary (zero changes); editor migrated. Light + dark verified on fresh CDP page (ignoreCache), 2px accent focus-visible (light #6d28d9 / dark #a78bfa)
- [x] `.field-row`→`.field-group` migrated with label-association (guards green); dense kv-table exception documented if kept — 9 real form-field render sites migrated (grep "12"→11 real, of which 9 form fields + 2 chrome); the env kv-table is NOT a `.field-row` (its own `renderKvTable` tabular structure) so no exception needed
- [x] `test_flow_studio_mcp_editor.py` (47) + `test_studio_mcps_tab.py` (8) + mcp browser slice (nav + test-connection, 12/1skip) green via run-tests.sh with PYTHON=.venv/bin/python
- [x] make test-unit green (3779 passed / 10 skipped); ruff clean; label-association guards green (14); sink baseline honest (single innerHTML sink unchanged); no new composite gate needed (class-swap only, no new alpha wash carrying text; auth-notice is solid surface)
- [x] MCPs-tab lazy tool-discovery a11y unaffected (aria-expanded on tile+expandBtn via `_setExpanded`) — mcps-tab.js not touched

## Post-Completion Checklist

- [x] Criteria verified; flight-log entry; leg `landed`; checked off in flight.md
