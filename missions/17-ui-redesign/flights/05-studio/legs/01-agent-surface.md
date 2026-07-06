# Leg: agent-surface

**Status**: completed
**Flight**: [Studio Re-skin](../flight.md)

## Objective

Re-skin the agent-editor (tab strip + General/Knowledge-stub/MCPs/Built-in Tools panels) and the agent tile grid to the v3 vocabulary; migrate general-tab's 7 `.field-row`→`.field-group` with label-association; add the M07 F10 lazy-discovery copy; fix the save→delete race (unit test); land the VRAM-warning + tool-switch composite-a11y gates + the label-association guards.

## Scope (flight DDs authoritative)

- Agent-editor tab strip (agent-editor.js) + agent grid (studio.js loadAll ~:1182) + the 5 tab modules' CHROME to the vocabulary (consume F3 tiles/buttons/tabs — no per-area variants). The shared tab-strip chrome is done ONCE here; the connector-editor/mcp legs only touch their panel content.
- general-tab.js: 7 `.field-row`→`.field-group` (unique id, `label.for`, invalid→`aria-describedby`→`.field-error` id). studio.js: its 3 `.field-row` too if agent-side.
- M07 F10: author "Built-in Tools" tab intro/subtitle copy ("tools the agent CAN load" vs "has loaded"; tone ref: MCPs tab "Expand to load tools…"); review the "N / M enabled" count word (tools-tab.js:132,315) for lazy-accuracy.
- Save-race fix: add the null-`found` fallback to studio.js save re-select (~2485-2503), matching handleDeleteEditor (~1636)/`_refresh` (~2661). UNIT test the fallback branch (or a route-stub forcing DELETE-during-PUT) — NOT a browser race.
- Composite-a11y gates (both themes): VRAM/model warning (`--status-warning` on `--status-warning-bg-soft`, studio.css:83), indeterminate tool-switch (`--accent-translucent`, :66). `_alpha_composite` rgba-over-one-known-surface in test_design_tokens_a11y.py; add fg+alpha+base to design_tokens.py mirror.
- Label-association guards (firm AC): a guard asserting every `.field-group label[for]` resolves to a control id AND every `.is-invalid` control's `aria-describedby` resolves to a `.field-error` id (land in test_ui_guards.py). Consider extracting `App.ui.fieldGroup` helper.

## Acceptance Criteria

- [x] Agent-editor + grid + tab strip render the vocabulary, both themes (visual pass on 8485, CDP focus); Knowledge tab is a stub (no re-skin work beyond chrome) — verified via CDP computed-style + focus in BOTH themes: field-group stacked, 2px accent focus-visible outline, label/input tokens correct
- [x] general-tab (+ studio.js agent-side) .field-row→.field-group with label-association; gutter exception NOT removed here — VERIFIED general-tab is NOT the sole consumer of `.area-studio .field-row .field-error` (studio.css:896-900): connector-editor (22), mcp-server-editor (12), discord-form (8), connectors-tab (2) still render `.field-row`, so the gutter exception stays for the connector-editor-core leg. studio.js had NO agent-side `.field-row` creation site (only wrapper skip-logic) — nothing to migrate there. general-tab migrated 6 field-rows (flight said 7; actual count is 6 — system_prompt uses a bare textarea + visually-hidden label, not a field-row)
- [x] M07 F10 lazy copy in the Built-in Tools tab (createElement `<p class="section-description tools-tab-intro">`, no new innerHTML sink); "N / M enabled" count word reviewed and kept (accurate for CAN-load semantics)
- [x] Save-race null-found fallback added; deterministic browser test green (route-stubbed loadAll → falls to first/empty, not stale editor) — JS has no unit harness, so the sanctioned route-stub form was used
- [x] VRAM-warning + tool-switch composite gates green both themes; label-association guards green + probe-tested. Light `--status-warning` deepened #a16207→#8f5606 (fix-then-gate; #a16207 text failed body AA ≈4.0–4.4:1 on the composited soft fill)
- [x] test_markdown.py + chat suites unaffected; studio browser slice green via run-tests.sh; make test-unit green (3812 passed); ruff clean; sink baseline UNCHANGED (general-tab kept innerHTML; tools intro via createElement); registry: no new testids (field ids are `id=`, not `data-testid`)

## Post-Completion Checklist

- [x] Criteria verified; flight-log entry; leg `landed`; checked off in flight.md
