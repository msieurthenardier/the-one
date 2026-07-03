# Flight: Shell and Shared Components

**Status**: ready
**Mission**: [UI Redesign — Clean, Professional, Consistent](../../mission.md)

## Contributing to Criteria

- [ ] SC1 — visual-language replacement (pixel-font branding retired here; last chamfer removed here)
- [ ] SC3 — one component vocabulary (this flight builds it)
- [ ] SC5 — keyboard/AT operability (vocabulary components ship keyboard-complete)
- [ ] SC9 — documentation (gallery rebuilt as the living reference; apparatus doctrine completed)

---

## Pre-Flight

### Objective

Rebuild the shared visual vocabulary on the v3 token system: a clean set-type wordmark (retiring the pixel-font banner and fixing the light-rail contrast requirement), restyled shell navigation, and one component vocabulary — buttons, fields, dropdowns, tiles/tables, tabs (without the last chamfer), modals, toasts, empty states, badges (contrast-fixed AND gated) — used identically everywhere, with the F1/F2 deferred ledger (CTA unification, dead-selector cleanup, panel-radius migration, section-title semantics) executed as first-class scope and the design gallery rebuilt as the living reference.

### Open Questions

- [x] Dropdown: custom widget vs styled native `<select>`? → Design Decisions
- [x] Wordmark: text vs image? Mascot's role? → Design Decisions
- [x] CTA unification shape? → Design Decisions

### Design Decisions

**Wordmark: set type, not an image** (retires SC1's "pixel-font branding"): the topbar banner PNG (`gleepglorp_banner.png`, injected at app.js:66) is replaced by a text wordmark — "GleepGlorp AI" set in Geist (semibold, `--font-size-h3`-tier, `--fg` color — theme-aware, AA on both rails by construction). The small robot mark (`topbar-icon-24.png`) may sit beside it at 20-24px as the compact brand mark (mascot equity retained; the chat-welcome mascot and favicons unchanged — not a rebrand). Light/dark verified AA; the F2 wordmark-contrast requirement closes here.

**Dropdown: vocabulary styling for BOTH surfaces, no forced migration** (mission Open Question closed; architect review corrected the premise — `discoverable-dropdown.js` is a connector-coupled multi-select typeahead combobox, not an extractable select): (a) the native single-select `.field-select` elements (admin provider/tools editors, studio general-tab/mcp/connector forms) get vocabulary styling as a shared class (quiet surface + hairline + pinned focus form) — this flight, inside `vocabulary-core`. **Chat agent-select seam (2nd-pass corrected)**: `#chat-agent-select` uses its own `.agent-select` class + bespoke chat.css rules (chat.css:29-31) — it does NOT inherit. Decision: `vocabulary-core` makes the minimal chat touch — add `field-select` to its class list (chat.js:138) and delete the now-redundant bespoke `.area-chat .agent-select` styling rules — so SC3's one-vocabulary claim holds at F3 close; chat-area layout work otherwise stays F4. Guard note: this is a justified chat.js/chat.css diff. (b) `discoverable-dropdown.js` keeps its behavior and gets surface/border/shadow restyling in **Flight 5** (studio re-skin), where its connector context lives. No unified custom widget is built; native selects with vocabulary styling ARE the vocabulary dropdown for static single-select.

**CTA unification** (mission KI, F1/F2 carry-forward): one always-visible header create button per entity grid — visible text label at rest (icon + label, no hover-reveal `components.css:633`, no `display:none` state-split `components.css:672` — both rules deleted; line refs corrected post-F2 sweep). Empty states keep their inviting canvas copy but the canvas CTA becomes the SAME component instance class; the four `-empty` testids retire (`new-agent/connector/mcp-source/provider-btn-empty`) with their registry rows pruned (`docs/ui-testid-registry.md:164-171`). **Test sweep covers ALL SIX consumer files** (architect enumeration): the F1 state-split trio (`test_flow_agent_crud`, `test_flow_provider_setup`, `test_flow_provider_grid` — re-simplified to the unified contract they deliberately pinned as flawed) PLUS three incidental-entry-path users (`test_flow_studio_openrouter_picker` — ~8 clicks, `test_flow_studio_connector_navigation`, `test_flow_studio_mcp_navigation`) migrated to the unified testid. Product fix + all tests + registry in the same leg.

**Tabs without the L-bracket**: selected-tab treatment becomes a quiet underline/edge (2px accent bottom-border family) — the `clip-path` chamfer at `components.css:~764` is deleted WITH its guard allowance (`CLIP_PATH_POLYGON_ALLOWANCE` entry — the guard fail-stales and demands it).

**Badges: fix THEN gate — per-badge ink is the PRIMARY strategy** (architect-corrected: the worst pairs, e.g. white on ollama `#2ecc71` at 2.10, need ~2.1× improvement — un-darkenable without losing the hue): introduce a per-badge ink token so light-toned fills take dark text; lightness-tune only where cheap. Every badge×ink pair clears body AA in both themes (F2's measured table at flight-02 flight-log Decisions is the worklist), THEN the pairs enter the a11y suite parametrization. Brand hue preserved; legibility wins conflicts.

**Component vocabulary conventions** (from the mission design brief; documented in agents.md + gallery): buttons (primary accent fill / secondary surface+border / ghost / danger; 32px, radius-sm; one primary per region), fields (label-above, inline validation color+message, pinned focus form; `.field-select` vocabulary styling per the dropdown DD), tiles/cards (surface + hairline + radius-md; elevation = surface-elevated, no shadows at rest), tables/lists (40-44px rows, hairline separators only, hover surface shift), modals (**restyle the existing `dialog.js` overlay** — it already has role=dialog/aria-modal/focus-trap/Escape/restore-focus; native `<dialog>` migration dropped as scope-creep; radius-lg + shadow-modal), toasts (surface + border + shadow-popover), empty states (one-line statement + one primary action). All consume `--space-*`/`--radius-*`; the `--panel-radius*` compat aliases are migrated (**35 consumer refs**: components 14, chat 7, admin 7, studio 7; plus 4 alias definitions deleted from tokens.css).

**Section-title semantics + admin labels**: `.section-title` remains the class (rename deferred — churn without payoff); real headings get an **element-scoped** bump (`h2.section-title { font-size: var(--font-size-h3) }` — NOT a bare class rule: a live non-h2 consumer exists at chat.js:136 `<label class="section-title">` which must not inflate); the admin `-pf-models-title`/`-pf-section-label` mono-uppercase treatments are quieted to the vocabulary label style.

**Gallery rebuilt per-section as the living reference** (mission Open Question part 2): each design-language section module is updated to showcase the NEW vocabulary (buttons/fields/surfaces/status/tabs/modal sections re-authored; tokens section already v3). The gallery is the acceptance surface for SC3's "one vocabulary."

**Apparatus doctrine completed** (F2 debrief debt): agents.md gains (a) UnknownVizError escalation note, (b) PDF fill-palette cross-check technique, (c) goldfinch-cannot-observe-focus → CDP-driven page for `:focus-visible` evidence. Lands with this flight's docs leg.

**Guard bookkeeping at markup intensity** (F2 debrief rec): every leg states expected registry/sink diff direction (registry: prune `-empty` rows, possible new vocabulary testids; sinks: expected ≤95, shrinkage justified); exact-diff guard output is the worklist; JS diffs justified in the flight log. **Three named guard-entry deltas, each fail-staling on exactly its leg's change**: (1) the banner-injection innerHTML string pinned at `test_ui_guards.py:89` updates when the wordmark replaces it (wordmark leg); (2) `CLIP_PATH_POLYGON_ALLOWANCE["components.css"]` deletes with the tab L-bracket (vocabulary-core leg); (3) `KNOWN_DEAD_SELECTORS` entry deletes with the dead queries (cta-unification leg).

**Studio cleanup bundle**: dead `connector-test-status` queries (`connector-editor.js:1775,1828`) + `KNOWN_DEAD_SELECTORS` entry removed together (the guard demands the allowlist cleanup).

### Prerequisites

- [x] Flight 2 completed (v3 tokens live; banned-token guard active; 8485 dev instance; apparatus doctrine partial)
- [x] F2 measured badge table available (flight-log Decisions)
- [x] F1 testid registry + sink baseline current

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

Component work proceeds vocabulary-first (buttons/fields/tabs/tiles in components.css + gallery), then the shell (wordmark/nav), then the cross-cutting product fixes (CTA unification with test re-simplification; badges fix+gate), then semantics/migration/docs, then verification. All legs: both themes, per-leg a11y criteria, guard bookkeeping, port 8485, `make restart` + hard-reload discipline, focus evidence via CDP page per doctrine.

### Checkpoints

- [ ] Vocabulary components render in gallery + all areas, both themes; zero clip-path polygons (allowance deleted)
- [ ] Wordmark AA both themes; banner PNG unreferenced
- [ ] CTA unified; F1 state-split tests re-simplified; registry pruned
- [ ] Badges AA-gated in suite (all pairs green)
- [ ] panel-radius aliases gone; section-title heading fix in
- [ ] Suites green; behavior gate passes; a11y review confirms

### Adaptation Criteria

**Divert if**: a vocabulary component rebuild breaks area-specific flows beyond test-fixable scope (that's F4-6 work pulled forward — stop and re-scope the boundary).

**Acceptable variations**: exact component CSS details within the vocabulary conventions; leg order swaps where dependencies allow.

### Legs

> **Note:** Tentative; created one at a time as the flight progresses.

- [ ] `vocabulary-core` - Buttons/fields (incl. `.field-select` styling)/tabs (L-bracket + allowance deleted)/tiles/tables; panel-radius migration (35 refs + 4 defs); gallery sections for these
- [ ] `wordmark-and-shell` - Text wordmark + compact mark (banner sink guard entry updated); topbar/sidebar nav restyle; light/dark AA evidence
- [ ] `cta-unification` - Product fix (state-split `:672` + hover-reveal `:633` deleted); ALL SIX test consumers migrated; 4 registry rows pruned; dead-selector cleanup bundle
- [ ] `badges-and-overlays` - Badges per-badge-ink fix + suite gating; dialog.js/toast/empty-state restyling; their gallery sections
- [ ] `semantics-docs` - Section-title heading fix + admin label quieting; agents.md vocabulary conventions + apparatus doctrine completion
- [ ] `flight-verification` - Suites; dual-theme visual pass (focus via CDP); behavior gate; sink/registry ledger

---

## Post-Flight

### Completion Checklist

- [ ] All legs completed
- [ ] Tests passing
- [ ] Flight log updated
- [ ] Documentation updated

### Verification

Gallery + three areas render the one vocabulary in both themes; `grep clip-path static/css` zero (allowance gone); banner PNG unreferenced in JS; unified CTA contract tested; badge pairs gated green; `--panel-radius` zero refs; suites green; `shell-navigation-smoke` passes at close.
