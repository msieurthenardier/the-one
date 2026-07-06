# Flight Debrief: Studio Re-skin

**Date**: 2026-07-05
**Flight**: [Studio Re-skin](flight.md)
**Status**: completed
**Legs Completed**: 6 of 6

## Outcome Assessment

### Objectives Achieved

The entire Agent Studio — agent/connector/MCP/knowledge grids and their editors (agent-editor's tabs, connector-editor, connectors-tab, discord-form, mcp-server-editor) — renders the v3 quiet vocabulary in both themes with zero alien remnants. 32 real form fields migrated `.field-row`→`.field-group` with full label-association; the `.area-studio .field-error` gutter exception retired; the discoverable-dropdown restyled at **zero JS diff** (WAI-listbox a11y preserved); the save→delete race fixed + regression-tested; M07 F10 lazy-discovery copy added; per-area browser lanes introduced. **Both studio behavior gates green**: studio-agent-crud (SC7) passed both themes, connector-editor-keyboard-a11y (SC5) re-passed 7/7 (M12 F4 keyboard a11y survived the re-skin). This was the mission's largest flight (6 legs).

### Mission Criteria Advanced

SC1 (studio surfaces to vocabulary, 0 alien remnants), SC3 (studio consumes the vocabulary, ~32 fields to `.field-group`, gutter exception retired), SC5 (keyboard a11y preserved AND re-verified — connector-a11y 7/7 + dropdown live-driven), SC7 (studio-agent-crud green both themes — the studio down-payment on the mission-end sweep) — F5 shares delivered; mission-end verification pending at F7.

## What Went Well

- **The `.field-group` migration + label-association guards — the strongest DD of the flight, and the SC3/SC5 substrate.** ~32 hand-wired label/control/error triads converted to one stacked primitive, then *frozen* by two probe-tested static-source guards (`find_label_for_without_control`, `find_invalid_describedby_without_field_error`). The migration REDUCED CSS surface (dropped redundant `admin-pf-*` composition once the vocabulary primitives proved self-sufficient) rather than adding per-area rules. A new shared `.field-group-label` primitive (label + info-icon as siblings — never nesting interactive content in `<label>`) was reused across 3 editors. Grids needed ZERO changes — the F3 vocabulary substrate holds.
- **Documented label-left exceptions are principled, not escape hatches**: the 3-column ACL editor (cohesive mount), chrome rows (LED/button layout, not form fields), and the env kv-table (its own tabular structure, never a `.field-row`). Each correctly reasoned.
- **Discoverable-dropdown restyle-not-rewrite (zero JS diff)** — the model for a11y-sensitive widgets: quiet the one alien typography rule in CSS, leave the WAI-listbox machinery untouched, gate the one wash it touched. Split into its own leg to isolate from bulk connector churn.
- **Per-area browser lanes as a complement design** — `shared` = complement of the three area globs, making "no file orphaned" a STRUCTURAL guarantee (569=569 verified, survives future test additions by construction). A genuine improvement over the DD's literal enumeration (which would have orphaned ~14 files). Realizes the F4-debrief decision; studio-only verification ~7:38 vs full ~12:33.
- **Both behavior gates run synchronously and passed** — studio-agent-crud (SC7, light 9/9 + dark 4/4, API-corroborated, the two-step Danger-Zone delete's armed state a judged a11y checkpoint) and connector-editor-keyboard-a11y (SC5, 7/7, chrome-devtools for real `:focus`, M12 F4 routing-reorder + live-region survived). The F4 "author + RUN synchronously" lesson realized.
- **Two independent review passes** (general + accessibility) both `[HANDOFF:confirmed]`; the a11y reviewer live-drove the dropdown keyboard flow, recomputed every composite ratio, and found two real fixes (info-icon `:focus-visible`, a pre-existing studio.css:934 double-paren typo).

## What Could Be Improved

- **The `.field-row` grep-inflation pattern recurred every single leg** (~1.4×): general-tab 7→6, connector 22→17, discord 8→4, mcp 12→11; nominal 54 → ~32 real. Source: grep-line counts fold in querySelectors, comments, `[data-field-row]` matches. **Firm lesson: a leg AC must grep to real render sites first, or express the target qualitatively ("migrate all genuine form-field render sites") — never pin a raw grep count that then reads as a miss.**
- **The chip-list `label[for]` runtime-dangle** — `mf-args`/`mf-sandbox-writable-paths` carry `<label for>` targets that `mountChipListEditors` strips at mount, so the runtime `for` resolves to nothing. Pre-existing, cross-editor, NOT an F5 regression (source byte-identical; the static guard scans source where the id is present → stays green). **This is the guard's coverage ceiling made concrete: static-source association ≠ runtime association.** → F7 systemic chip-list pass + a RUNTIME DOM assertion companion.
- **Behavior-gate crews are slow** — connector-a11y ran ~71 min and completed AFTER the flight commit `50b25ff`, landing as a follow-up (`e367c99`) rather than inside the committed flight. Green, but the gate should be run well before the commit boundary. (This also caused a transient FD misread — see the honesty-catch below.)

## Deviations and Lessons Learned

| Item | Disposition | Standardize? |
|------|-------------|--------------|
| Composited soft-fill contrast: VRAM warning `#a16207→#8f5606` | Fix-then-gate — the THIRD instance (F3 danger, F3 soft-fill, F5 warning) of a 600-family status color failing as text-on-its-own-`-bg-soft` | **Yes — PROMOTE to a token-design invariant**: any status color used as body text on its own `-bg-soft` wash is gated at token-definition time, both themes, over bg/surface/elevated — not rediscovered per surface |
| Static label-association guard blind to runtime dangle | Chip-list mount strips the id | Yes — pair every static association guard with a runtime DOM assertion where a mount step can alter the tree |
| Info-icon `:focus-visible` gap amplified by migration | Fixed at close | Lesson: promoting an element to a shared primitive amplifies any latent state-styling gap it had (1 icon → 4-editor problem) |
| Grep-inflation ~1.4× on `.field-row` counts | Re-derived per leg | Yes — grep to render sites, or qualitative ACs |
| Apparatus: goldfinch can't observe `:focus`; wedges on CRUD-seeding; no `ignoreCache` reload | Used chrome-devtools for the focus/keyboard + seed+drive flows | Yes — chrome-devtools default for focus/keyboard AND multi-step seed+drive (it has `ignoreCache` reload — the `?v=` JS-cache footgun workaround); focus flows run in ONE continuous Executor session (a re-spawn drops focus); printToPDF/computed-style/readAxTree as the default evidence path, screenshots opt-in |

## Key Learnings

1. **Verify on-disk evidence before recording a disposition** (the flight's headline process win): the commit-Developer refused to write a "deferred/FD-pending" narrative that contradicted the on-disk studio-agent-crud PASS run log, and surfaced the conflict rather than transcribing an earlier planning-state assumption. A disposition in an artifact must match the on-disk evidence at commit time. This caught a stale-narrative drift between when the leg landed and when the flight committed.
2. A complement-based test-lane partition converts "no test orphaned" from a maintenance promise into a structural guarantee.
3. Restyle-don't-rewrite (zero JS diff) is the correct posture for a11y-sensitive widgets already on-vocabulary.
4. Migrations surface latent debt (the info-icon focus gap) and expose guard coverage ceilings (the chip-list runtime dangle).

## Recommendations

1. **(F6 — next, directly parallel)** Retire the `.area-admin .field-error` gutter exception (admin.css:445 — the System-side twin of the studio one F5 deleted); migrate provider/tool editors + admin forms to `.field-group`; rename surviving `.section-title`/`// SECTION` per-area markers; apply the **promoted token rule** (gate status-text-on-soft-fill at definition). Grep field-row counts to render sites first (~1.4× inflation).
2. **(F6/F7)** Fix the chip-list `label[for]` runtime-dangle systemically (retain/re-point the id at mount) + add a runtime DOM guard (the class the static guard can't catch).
3. **(F7 behavior gates)** Prefer chrome-devtools for focus/keyboard AND seed+drive flows; run the sync crews well before the flight-commit boundary (budget ~60-90 min). SC7 mission-end sweep now owes: chat-roundtrip DARK (light passed F4) + system-provider-config (F6) — studio is green both themes, SC5 connector-a11y is done (7/7).
4. **(standing)** Keep the combined review+implement protocol + the independent a11y review pass — both proved out over 6 legs; F7's SC6 monolith is now decomposable via the lanes.

## Test Metrics (F1 → F5)

| Metric | F1 | F2 | F3 | F4 | F5 |
|---|---|---|---|---|---|
| Unit passed | 3681 | 3721 | 3749 | 3759 | 3779 |
| Unit wall | 5:33 | 5:35 | 5:31 | 5:34 | 5:30 |
| Browser pass | 532 | 533 | 533/1fl | 562/1fl | 562/1fl |
| Browser wall (full) | ~12.5m | 12:33 | ~12.5m | 13:08 | 12:33 |
| Studio lane | — | — | — | — | 252p / 7:38 |

Unit flat-to-linear (+20 = composite gates + label-assoc guards). Browser wall came back down to 12:33 (F5 net-added no browser tests — class-swaps + lane refactor). 1 flake = documented load-timing class (passes in the studio lane + 8/8 isolated). Perf (SC8) not re-measured — CSS/markup-led; F1 baseline stands; SC8 is an F7 gate. Both studio behavior gates green (SC7 both themes / SC5 7/7).
