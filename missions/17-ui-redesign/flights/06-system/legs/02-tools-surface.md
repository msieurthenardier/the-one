# Leg: tools-surface

**Status**: completed
**Flight**: [System / Admin Re-skin](../flight.md)

## Objective

Re-skin the Built-in Tools surface — tools-grid + tools-editor (admin-only rows) — to the v3 vocabulary; migrate the tools-editor enabled-row to `.field-group`; quiet the tool badge eyebrow. (The tools-editor SCHEMA field rows come from the shared renderField — migrated in Leg 3; mid-flight the editor carries mixed `.field-group` + `.field-row` rows, which is EXPECTED, not a defect.)

## Scope (flight DDs authoritative)

- tools-grid.js (227, category tablist + `.tool-tile` tiles + inline `.tool-enable-switch--corner` toggle) + tools-editor.js (678, admin-only rows — NOT the shared renderField schema fields) → vocabulary (consume F3 tiles/tabs/buttons/fields).
- Migrate the tools-editor enabled-row (tools-editor.js:216 `.tools-editor-enabled-row`) to `.field-group` (or keep as a documented label-left toggle exception like the provider thinking-toggle — the enabled-row is a single toggle; default to the label-left exception if stacking reads worse, marker preserved). GREP to real render sites first.
- **Quiet the `.admin-tool-badge` eyebrow** (admin.css:168 — drop mono/uppercase/letter-spacing via OVERRIDE if a shared base reasserts it, per the Leg-1 badge lesson; keep the per-type `--badge-ink-*` color). Also `.editor-subtitle-meta` (:296) if on this surface.
- **Composite gate**: `.editor-error-banner` (admin.css:589) — CONFIRM it consumes the ALREADY-GATED `--status-danger`/`--status-danger-bg-soft` pair (test_design_tokens_a11y.py); NO new `_alpha_composite` math (per the flight DD). Optionally a source-grep guard pinning the usage.
- Guard bookkeeping: label-association guards green; DYNAMIC_SINK_BASELINE updated if a tools-grid/tools-editor innerHTML markup site changed; registry for any new field ids.
- DO NOT touch the shared tools-form-helpers.js renderField (Leg 3) or the studio tools-tab. Admin-only surface here.

## Acceptance Criteria

- [x] tools-grid + tools-editor (admin rows) render the vocabulary, both themes (CDP visual + focus); tool badge eyebrow quieted; category tablist + toggle to vocabulary
- [x] enabled-row migrated to `.field-group` OR documented label-left toggle exception (marker preserved); label-association green
- [x] `.editor-error-banner` confirmed consuming the already-gated danger pair (no new gate); optional source-grep guard added
- [x] tools-editor's mixed field-group/field-row mid-flight state noted (schema rows land Leg 3) — not misread as a defect
- [x] `test_flow_admin_tools_editor.py` + `test_flow_admin_tools_grid.py` + `test_flow_admin_openrouter.py` + system lane green via run-tests.sh --lane system (PYTHON=.venv/bin/python); make test-unit green; ruff clean; sink baseline honest

## Post-Completion Checklist

- [x] Criteria verified; flight-log entry; leg `landed`; checked off in flight.md
