# Leg: providers-surface

**Status**: completed
**Flight**: [System / Admin Re-skin](../flight.md)

## Objective

Re-skin the LLM Providers surface — providers-grid + provider-editor + provider-models (Ollama panel) — to the v3 vocabulary; migrate the 6 provider-editor `.admin-pf-row` sites to `.field-group` (preserving the type-driven show/hide); quiet the provider badge eyebrow.

## Scope (flight DDs authoritative)

- providers-grid.js (tile grid + New Provider CTA) + provider-editor.js (610) + provider-models.js (480, Ollama VRAM/models panel) → vocabulary (consume F3 `.entity-tile`/`.btn-*`/fields; reuse the shared `.field-group-label` for info-icon fields).
- Migrate the 6 `.admin-pf-row` sites (provider-editor.js:126-208: Name/Type/Base URL/API Key/num_ctx/thinking) to stacked `.field-group` with full label-association (unique id, `label.for`→control id, invalid→`aria-describedby`→`.field-error` id). **GREP to real render sites first** (~1.4× inflation).
- **AC INVARIANT — preserve the `.admin-pf-{base-url,api-key,num-ctx,thinking-enabled}` row-marker classes** on the migrated `.field-group` rows (or migrate the `wireEditorEvents` selectors in lockstep, provider-editor.js:278-289): those classes drive the type-change `is-hidden` show/hide — dropping them breaks it. Verify by exercising a provider-type switch in both themes.
- The `thinking_enabled` toggle (js:200-208, a `.tool-enable-switch`) + `num_ctx` stay as a **documented label-left toggle exception** if stacking reads worse; default to stacking the text fields, keep the toggle label-left. The API-key masked input + `.api-key-eye` reveal preserved.
- **Quiet the `.admin-provider-badge` eyebrow** (admin.css:82 — drop mono/uppercase/letter-spacing; keep the per-type ink color, already `--badge-ink-*`-gated). Also `.editor-subtitle-meta` (:296) if it's on this surface.
- **Composite gates**: `.cap-chip-no-tools` (admin.css:138) — CONFIRM it consumes the ALREADY-GATED `--status-danger`/`--status-danger-bg-soft` pair (test_design_tokens_a11y.py:265); NO new `_alpha_composite` math (per the flight DD). Optionally a source-grep guard pinning the usage. Provider LEDs (`.indicator-led--success/--idle`) + `.test-result-*` are LED/UI, fg-ladder-covered.
- Guard bookkeeping: label-association guards stay green; update DYNAMIC_SINK_BASELINE for any new/changed innerHTML markup site in provider-editor/provider-models; registry for any new field ids.

## Acceptance Criteria

- [x] providers-grid + provider-editor + provider-models render the vocabulary, both themes (CDP visual + focus); no per-area variants; no alien remnants; provider badge eyebrow quieted
- [x] 6 `.admin-pf-row`→`.field-group` with label-association (guards green); `.admin-pf-*` marker classes preserved AND the type-driven show/hide verified working (switch provider type, confirm fields toggle) both themes; thinking toggle label-left exception documented
- [x] `.cap-chip-no-tools` confirmed consuming the already-gated danger pair (no new gate); optional source-grep guard added
- [x] `test_flow_provider_editor.py` + `test_flow_provider_grid.py` + `test_flow_provider_setup.py` + provider slice green via run-tests.sh --lane system (PYTHON=.venv/bin/python); make test-unit green; ruff clean; label-association guards green; sink baseline honest (update DYNAMIC_SINK_BASELINE if markup sites changed)

## Post-Completion Checklist

- [x] Criteria verified; flight-log entry; leg `landed`; checked off in flight.md
