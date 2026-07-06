# Flight Debrief: Shell and Shared Components

**Date**: 2026-07-04
**Flight**: [Shell and Shared Components](flight.md)
**Status**: completed
**Duration**: 2026-07-04 (single day, 6 legs)
**Legs Completed**: 6 of 6

## Outcome Assessment

### Objectives Achieved

One shared component vocabulary now spans all surfaces on the v3 tokens: four intent-named button variants (`.btn-filled-primary`/`-outlined-primary`/`-ghost`/`-muted-destructive`), a `.field-select`/`.field-group` field system, tabs (chamfer L-bracket retired → 2px accent bottom-border), tiles/tables, restyled modal/toast/empty-states. The pixel-font banner is replaced by a set-type wordmark (SC1's last branding remnant). The entity-grid create CTA is unified to one always-visible labeled button — retiring **both** mission Known Issues (the state-split icon-only CTA and the dead `connector-test-status` selector). Badge contrast is fixed with per-badge ink and gated (+22 tests). The design gallery is re-authored as the living SC3 reference; agents.md carries the vocabulary conventions + the completed apparatus doctrine. Behavior gate `shell-navigation-smoke` passed 6/6 on the redesigned shell.

### Mission Criteria Advanced

SC1 (pixel-font branding + last chamfer gone), SC3 (one vocabulary built), SC5 (vocabulary keyboard-complete, focus-visible on every interactive selector), SC9 (gallery + apparatus doctrine) — F3 shares delivered; mission-end verification pending.

## What Went Well

- **Per-badge ink over lightness-tuning** (architect-corrected pre-flight): the worst pairs (white on ollama at 2.10:1) needed ~2.1× improvement un-buyable by darkening without destroying brand hue. Ink chosen by fill luminance and kept **theme-stable** (one ink clears AA in both themes) fixed 10 of 11 pairs; one fill tuned. Reusable heuristic: pick the ink, not the fill; keep the ink theme-stable.
- **Vocabulary-first leg ordering** held as the dependency spine — every later leg consumed Leg 1's primitives; no back-tracking forced.
- **Combined review+implement protocol** (F3 process adaptation): the `[BLOCKED:design-flaw]` stop-gate never needed to fire across 6 legs, while the per-leg review hat still caught load-bearing corrections (strict-mode double-testid hazard; `--nav-bg`/`--sidebar-bg` both-alias-surface invisible-hover; mirror-sync-is-mirror-driven) and absorbed intra-flight line-number drift via content-anchored citations. Saved ~30-48 min vs separate review spawns while preserving the safety net.
- **Additive-not-migrating discipline**: `.field-group` (label-above) shipped alongside the load-bearing `.field-row` (label-left, 100px gutter anchors 3-col layouts) rather than flipping it — correctly avoiding pulling F4-6 area re-skins forward past the flight's own divert criteria.
- **Delegated behavior-test orchestration**: the gate ran as a sub-orchestrator (spawning its own Executor+Validator, writing the run log, reporting only the verdict), conserving Flight-Director context — a pattern to keep for the remaining flights.
- **Guard ratchet reached its healthiest end state**: all three named guard allowances now empty (`CLIP_PATH_POLYGON_ALLOWANCE={}`, `KNOWN_DEAD_SELECTORS=set()`, banner sink re-pinned) — the banned-vocabulary net tolerates zero retired constructs; it can only tighten.

## What Could Be Improved

- **The soft-fill-fg contrast blind spot** (the headline finding): the flight-close accessibility review caught a BLOCKING WCAG 1.4.3 failure — `.btn-muted-destructive` put `--status-danger` body text on the low-alpha `--status-danger-bg-soft` wash; composited over the surface ladder it measured 4.41/4.23/4.02 (light), failing on real Danger-Zone/delete buttons across five editors. The per-leg badge gate modeled solid fill×ink pairs, not a low-alpha rgba wash over a ladder of base surfaces — a whole token genre (`--*-bg-soft`) the suite didn't model. Fixed (light danger red-600→red-700 `#b91c1c`, soft base kept matched) and gated with a new `_alpha_composite`-reconstruction test (mutation-verified: fails on old value, passes on new). **Lesson for F4-6**: any composited/alpha fill carrying body text gets a reconstruct-and-gate test AT LEG TIME, not at flight-close review — make it a per-leg a11y acceptance criterion.
- **JS-references-dead-CSS-var blind spot**: a Leg-1 miss (`status-section.js` referencing the deleted `--panel-radius-sm` alias) slipped past both the combined review and `test_token_definitions.py` (which scans CSS, not JS gallery `innerHTML` strings). Caught only by Leg 4's review. Cheap tripwire candidate: grep JS strings for `var(--token)` refs absent from tokens.css (same genre as F1's backtick tripwire).
- **`DYNAMIC_SINK_BASELINE` carries 3 stale entries** (live 92/27 vs frozen 95/30 — three Leg-1 gallery createElement conversions; removals never fail the ratchet so left un-pruned). Benign, but F4 should re-baseline to 92 before adding the markdown sink so the ratchet is honest.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| `.field-row`→label-above became ADDITIVE (`.field-group`), not a flip | Flipping the load-bearing gutter would pull F4-6 forward past divert criteria | Yes — additive vocabulary primitives; migrate per-area during re-skins |
| Destructive-button contrast fixed post-flight (a11y review catch) | Soft-fill body-text pair wasn't in the measured worklist | Yes — audit every fg-on-soft-fill pair at leg-authoring time |
| Combined review+implement (one spawn, stop-gate) | Twice-Opus-reviewed flight DDs front-load the rigor; separate review spawns are ~5-8min each | Yes — keep for flights with twice-reviewed specs |
| Behavior gate delegated to a sub-orchestrator | Conserve Flight-Director context on a long mission | Yes — for remaining flights |

## Key Learnings

1. Solid-fill contrast gates don't cover alpha-wash-over-ladder pairs — the `--*-bg-soft` genre needs composite-reconstruction tests.
2. "Pick the ink by fill luminance, keep it theme-stable" beats darkening fills for brand-colored badges.
3. Element-scope font rules when a class serves two roles (heading + label).
4. Delegating behavior-test runs preserves orchestrator context without weakening the Witnessed independence (Executor/Validator are still separate agents).

## Recommendations

1. **(F4)** Vendored markdown pipeline: the `App.markdown` facade is the chokepoint; land the vendor manifest + two-source hash verification + CI integrity test + XSS regression suite IN THE SAME LEG as the swap. Re-baseline the sink freeze to 92 first, then add the sanitizer's `innerHTML` write as an explicit annotated `DYNAMIC_SINK_BASELINE` entry justified by the XSS suite. State expected net direction (consolidation down as chat sites route through the sanitizer).
2. **(F4-6, per-leg a11y AC)** Every new composited/alpha fill carrying body text gets an `_alpha_composite` reconstruct-and-gate test — F4's chat surfaces (turn backgrounds, tool-trace disclosures, code blocks) are the next soft-fill genre.
3. **(F4-6 field contract)** Instantiate `.field-group` with the full label-association wiring (unique id, `label.for`, invalid→`aria-describedby`→error id) per the gallery `fieldGroup()` reference — not bare labels. Consider a guard asserting `.field-group label[for]` always resolves.
4. **(F4-6)** Consume the button vocabulary directly (no per-area variants — SC3); the chat stop button adopts a vocabulary variant during the re-skin.
5. **(F4)** Add the JS-references-dead-CSS-var tripwire; prune the 3 stale sink entries; spec per-area browser test lanes (browser suite parked at ~12.5 min for three flights, F4 grows it).
6. **(F5)** Owes: `discoverable-dropdown.js` combobox restyle, the M12 F4 connector-editor a11y preservation (re-verify via `connector-editor-keyboard-a11y`), the deferred `.field-row`→`.field-group` migration + retiring the `.area-admin .field-error` gutter exception, and the 4s dirty-back expect-timeout bump (that module lives there).
7. **(Mission debrief)** Still-open cross-flight items: aiosqlite `TestSchemaV17` loop-closed warning (F1 action item, 1 location); M16's undebriefed `active` status. (The theme-unset cross-tab bug was resolved in F2.)

## Test Metrics (F1 → F2 → F3)

| Metric | F1 | F2 | F3 |
|---|---|---|---|
| Unit passed | 3681 | 3721 | 3749 |
| Unit wall | 5:33 | 5:35 | 5:31 |
| Browser | 532/0 | 533/0 | 533 pass / 1 logged flake |
| Guard/a11y/token slice | bootstrapped | 93 | 121 |
| Sinks (live/baseline) | 95/30 | 95/95 | 92/27 vs 95/30 |

Unit flat-to-faster despite +28 tests (all badge/danger a11y gates); browser consolidated (not net-added) — CTA migration dropped `-empty` assertions. Perf not re-measured (CSS/markup/docs only); F1 baseline stands. Watch: dirty-back confirm-dialog flake (→F5); browser-suite lane cost (→F4).
