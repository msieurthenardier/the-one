# Leg: 04-providers-and-ollama-polish

**Status**: completed
**Flight**: [Administration Polish](../flight.md)

## Objective

Wire the canonical `.indicator-led` primitive into the Ollama lifecycle panel's loaded/unloaded model markers and fix the test-result LED + label spacing on the Provider editor. Leg scope was originally broader (Providers grid + editor + Ollama lifecycle full polish per the flight design), but the operator deemed the page on-brand after the two targeted changes — closed the leg early.

## Context

- **Flight 2 debrief carry-over (the in-Admin LED wire-up)**: The `.indicator-led` primitive (canonical 10px reflective-crescent dot) shipped in Flight 2 Leg 05 with `--success / --warning / --danger / --idle` variants and a `.test-result-*::before` retrofit for the Provider editor test-connection display. The Ollama lifecycle panel's model dots (`.admin-pf-model-dot.loaded` for running, `.admin-pf-model-dot` for available) were the deferred in-Admin LED consumer. Path (b) — JS markup replacement at both render sites + dead-selector cleanup — was the working assumption per the flight design.
- **Operator-surfaced test-result spacing bug**: After clicking Test on a provider, the LED dot (from `.test-result-*::before` retrofit) and the status label text were visually touching. Root cause: the `.test-result` parent has `gap: 6px`, but the LED `::before` is a pseudo-element INSIDE the span (not a sibling flex item), so the gap doesn't apply. Fix: `margin-right: 6px` on the shared `::before` rule.
- **Leg scope decision**: Operator deemed the remaining Providers polish items (tile grid, API-key wrap, pull progress UI, cap chips, per-row Load/Unload/Delete buttons) on-brand without changes. Closed leg early. Carries forward to debrief: most of the Providers page already inherits Flight 2 vocabulary via canonical primitives (entity-tile glass+bezel, V3b buttons, .test-result with LED retrofit, banner-error for delete-blocked from Leg 03).

## Inputs (pre-leg state)

- `static/js/areas/admin/provider-models.js:347` — `<span class="admin-pf-model-dot loaded"></span>` emitted for running models (loaded list).
- `static/js/areas/admin/provider-models.js:376` — `<span class="admin-pf-model-dot"></span>` emitted for available models (unloaded list).
- `static/css/admin.css:128-129` — `.admin-pf-model-dot` rule pair: 8px round, `--fg-muted` bg; `.loaded` variant adds `--status-success` bg + 6px outer glow.
- `static/css/components.css:857-869` — `.test-result-*::before` shared rule: 10px round with reflective-crescent radial-gradients, no `margin-right` (LED touches text content).

## Outputs (post-leg state)

- `provider-models.js:347` — emits `<span class="indicator-led indicator-led--success"></span>` (canonical primitive consumer).
- `provider-models.js:376` — emits `<span class="indicator-led indicator-led--idle"></span>` (canonical primitive consumer).
- `admin.css:128-129` — `.admin-pf-model-dot` rule pair retired; only a comment marker remains documenting the Flight 3 Leg 04 retrofit.
- `components.css :860 .test-result-*::before` shared rule — `margin-right: 6px` + `vertical-align: middle` added so the LED + status label have proper spacing and baseline alignment.

## Acceptance Criteria

- [x] **Ollama loaded models** render `<span class="indicator-led indicator-led--success">` (10px reflective-crescent + success-color outer glow)
- [x] **Ollama available models** render `<span class="indicator-led indicator-led--idle">` (10px reflective-crescent + idle/muted bg, no glow)
- [x] **`.admin-pf-model-dot` rule pair retired** from admin.css; no grep hits remain in static
- [x] **Test-result LED spacing fixed** — `::before` LED has 6px right margin + baseline-aligned to text middle
- [x] Narrow test gate green: 56/56 (no behavioral regressions)
- [x] WCAG audit green: 45/45 (no contrast pair changes)
- [x] Operator visual verification confirmed across both fixes ("looks good")
- [x] Operator deemed remaining Providers items on-brand; leg closed early

## Files Modified

- `the_one/interfaces/web/static/js/areas/admin/provider-models.js` — LED markup swap at lines `:347` (loaded) and `:376` (available)
- `the_one/interfaces/web/static/css/admin.css` — `.admin-pf-model-dot` rule pair retired at `:128-129` (replaced with a one-line comment marker)
- `the_one/interfaces/web/static/css/components.css` — `.test-result-*::before` shared rule gains `margin-right: 6px` + `vertical-align: middle` at `:860`

## Citation Audit

5 citations verified against current code at leg close:

- `provider-models.js:347` — verified: emits `<span class="indicator-led indicator-led--success">`.
- `provider-models.js:376` — verified: emits `<span class="indicator-led indicator-led--idle">`.
- `admin.css:128-129` — verified: rule pair retired, comment marker present.
- `components.css :860` — verified: `margin-right: 6px` + `vertical-align: middle` present on shared `::before` rule.
- `grep -rn "admin-pf-model-dot" the_one/interfaces/web/static/` — returns only the comment marker in admin.css. No live consumers.

All citations clean. No mirror updates needed.
