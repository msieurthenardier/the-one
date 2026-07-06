# Leg: shared-helpers-and-chiplist

**Status**: completed
**Flight**: [System / Admin Re-skin](../flight.md)

## Objective

Migrate the SHARED `tools-form-helpers.js` renderField emitter `.field-row`→`.field-group` (cross-area: admin tools-editor + studio tools-tab), and fix the chip-list `label[for]` runtime-dangle systemically (admin + ALL studio chip-list consumers) with a RUNTIME DOM guard. This is the flight's highest-coupling leg — re-verify BOTH the studio and system lanes.

## Scope (flight DDs authoritative)

- **renderField `.field-row`→`.field-group`** (tools-form-helpers.js:298): the emitter feeds exactly TWO call sites — admin `tools-editor.js:153` + studio `tools-tab.js:415`. Migrate to `.field-group` with label-association. **AC INVARIANT — KEEP `.tools-editor-field` + `data-field-name`** on the migrated emitter: `renderFieldErrors`' selector is `.tools-editor-field[data-field-name=…], .field-row[data-field-name=…]` (tools-form-helpers.js:552), used by BOTH lanes — dropping the marker breaks 422-error rendering in both. Keep the markers on the `.field-group` rows.
- **Chip-list `label[for]` systemic fix**: add an `options.controlId` param to the shared `renderChipListEditor` → land it as `id` on the real focusable `.chip-list-input` (a `<div>` is NOT labelable, so the `label[for]` must target the input, not the wrapper). Wiring per convention:
  - `renderField` passes `idAttr` (the `tef-{name}` it already computes for its `<label for>`).
  - **`mcp-server-editor.js` — the TRUE mount-time strip site**: it wires `for="mf-{name}"` on a PLACEHOLDER `<div id="mf-{name}">` that `mountChipListEditors` replaces via `outerHTML=` (stripping the id). Repoint: pass `controlId="mf-{name}"` to `renderChipListEditor`, DROP the placeholder-div id (its post-mount selectors key on `[data-field="args"].chip-list-editor`, verified js:857/873 — dropping the div id is safe). Enumerate every mcp-server-editor chip-list site touched.
  - Check the other direct `renderChipListEditor` consumers (studio connector-editor, connectors-tab, tools-tab) — pass `controlId` where a `<label for>` targets the widget; leave alone where there's no label coupling.
- **RUNTIME DOM guard** in `tests/browser/` (NOT test_ui_guards.py — the static guard provably can't catch a mount-time strip): a Playwright flow (pattern precedent `test_flow_studio_per_agent_overlay_label_resolver.py`) that mounts a chip-list-bearing editor and asserts via `page.evaluate` that each `label[for=X]` resolves to a real element in the mounted tree. Cover admin tools-editor + mcp-server-editor.
- Guard bookkeeping: static label-association guards stay green; DYNAMIC_SINK_BASELINE updated for any changed markup site; registry unchanged.

## Acceptance Criteria

- [x] renderField emits `.field-group` (keeping `.tools-editor-field` + `data-field-name`); admin tools-editor AND studio tools-tab schema fields render stacked with label-association, both themes (CDP visual)
- [x] 422-error rendering still works in BOTH lanes (renderFieldErrors selector intact) — verify a validation error surfaces on a schema field in admin tools-editor
- [x] chip-list `label[for]` resolves at runtime (options.controlId on .chip-list-input); mcp-server-editor placeholder-div repoint done + enumerated; the F5 runtime-dangle CLOSED
- [x] RUNTIME DOM guard in tests/browser/ added + green (asserts label[for] resolves in the mounted tree for admin tools + mcp-server-editor chip-lists)
- [x] BOTH `--lane studio` AND `--lane system` green via run-tests.sh (PYTHON=.venv/bin/python) — the cross-area change didn't regress either; make test-unit green; ruff clean; static label-association guards green; sink baseline honest

## Post-Completion Checklist

- [x] Criteria verified; flight-log entry; leg `landed`; checked off in flight.md
