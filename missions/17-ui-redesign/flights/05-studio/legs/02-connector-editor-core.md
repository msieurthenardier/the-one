# Leg: connector-editor-core

**Status**: completed
**Flight**: [Studio Re-skin](../flight.md)

## Objective

Re-skin connector-editor.js (4956 LOC) + connectors-tab.js (the agent-editor Connectors panel) + connectors-grid.js to the vocabulary; migrate their 24 `.field-row`→`.field-group` with label-association; retire the `.area-studio .field-error` gutter exception; add composite-a11y gates for connector washes. The M12 F4 keyboard routing-reorder + live-region a11y is PRESERVED verbatim (re-verified in Leg 6).

## Scope (flight DDs authoritative)

- connector-editor.js tabs (Connection/Credentials/Session/Discord-summary/Access+Routing "Advanced") + routing-rule reorder table + allowlist editors → vocabulary (consume F3 buttons/tiles/tabs/fields; discord-form itself is Leg 3). connectors-tab.js (per-account attach toggles + ACL/admit-dms editor) + connectors-grid.js → vocabulary.
- 24 `.field-row`→`.field-group` (connector-editor 22 + connectors-tab 2) with full label-association (unique id, `label.for`, invalid→`aria-describedby`→`.field-error` id). NOTE: 2 connector for-targets come through the `renderLifecycleSelect` concatenation helper — already allowlisted in `FIELD_FOR_ID_HELPER_INDIRECTED` (Leg 1); keep them resolvable.
- **Retire the `.area-studio .field-error` gutter exception** (studio.css:896-900) — now that connector-editor's rows migrate to `.field-group`, verify NO remaining `.field-row .field-error` consumer (mcp-server-editor + discord-form migrate in Legs 3/4 — if they still render `.field-row` at THIS leg's end, the exception stays until Leg 4; delete it only when the last consumer is gone. Coordinate: this leg does connector-editor+connectors-tab; discord-form=Leg3, mcp=Leg4. So the gutter exception likely survives to Leg 4 — state which leg actually deletes it).
- **PRESERVE verbatim** the M12 F4 keyboard a11y: routing-rule drag-handle `[data-routing-drag-handle]` (tabindex=0, ArrowUp/Down reorder, focus retained, live-region announcement), the `[data-routing-live-region]` (aria-live polite), the `connector-live-status`/`-error-wrap` (aria-live/role=alert). The re-skin touches CSS/chrome, NOT this behavior. The `<h2 class="section-title">Routing</h2>` etc. already quiet (F2).
- Composite-a11y gates (both themes) for connector washes carrying text: the connector-empty-types-banner soft wash (studio.css:926), any field-error-highlight text-on-wash. `_alpha_composite` rgba-over-one-known-surface; mirror in lockstep.

## Acceptance Criteria

- [x] connector-editor + connectors-tab + connectors-grid render the vocabulary, both themes (CDP visual + focus); no per-area variants; no alien remnants — connectors-grid already pure vocabulary (0 changes); connector-editor/connectors-tab dropped redundant `admin-pf-*`; CDP focus-visible (2px accent) + `.is-invalid` danger verified both themes
- [x] 24 `.field-row`→`.field-group` with label-association — TRUE count: 17 connector-editor render sites (not 22 grep-lines), 13 migrated total (11 connector-editor form fields + 2 connectors-tab; 3 ACL rows kept label-left as documented exception; 5 chrome rows not form fields). Both label-association guards return empty (pass); helper-indirected allowlist refreshed; field-id churn recorded in flight-log
- [x] Gutter exception disposition stated — **DELETED in this leg** (connector-editor name/type proven sole + last consumer; discord-form/mcp render `.field-row` with zero `.field-error`). Not deferred to Leg 4
- [x] M12 F4 keyboard routing-reorder + live-region a11y UNCHANGED — `data-routing-drag-handle` / `data-routing-live-region` / `connector-live-status-error-wrap` grep-confirmed intact at leg end; routing table untouched (Leg 6 runs the behavior spec)
- [x] Connector composite gates green both themes; mirror updated — added `test_connector_empty_types_banner_prose_passes_body_aa` (`--fg` on soft-warning wash, both themes × 3 surfaces); `<strong>` reuses Leg 01's warning gate; `design_tokens.py` mirror already carried the tokens (no value change)
- [x] `test_flow_studio_connector_editor.py` + connector browser slice green via run-tests.sh; make test-unit green; ruff clean; sink baseline honest — editor(23)+slice(74+31 more)=128 connector/connectors-tab browser tests green; unit lane 3818 passed/0 failed; ruff+format clean; **sink baseline UNCHANGED** (no innerHTML→createElement migration — kept string-concat)

## Post-Completion Checklist

- [x] Criteria verified; flight-log entry; leg `landed`; checked off in flight.md
