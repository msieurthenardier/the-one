# Flight Debrief: Studio Alignment

**Date**: 2026-04-28
**Flight**: [Studio Alignment](flight.md)
**Status**: landed
**Duration**: 2026-04-27 (in-flight) → 2026-04-28 (landed)
**Legs Completed**: 5 of 5

## Outcome Assessment

### Objectives Achieved

F5 brought the Studio area to the established design-language quality bar across all four planned axes:

- **Three-section sidebar nav** (Agents / Knowledge / Tools) with hash-routable sub-section state and stub destinations for the unbuilt sections.
- **Agent tile grid** as the canonical agents view (CSS-grid, responsive, ARIA `role="listbox"` + `option`).
- **Tabbed agent editor** with the codebase's first tab idiom (`App.tabs` — W3C ARIA manual activation, roving tabindex, hash-encoded active tab).
- **Save / Cancel / Back action cluster** with `disabled` as single source of truth, plus an `App.confirmDialog` modal for unsaved-changes blocking decisions across four navigation routes (Back, section-nav, hash-route-to-other-agent, beforeunload).

Two design-system helpers shipped that earn cross-area reuse: `App.confirmDelete` (two-step in-place confirm) and `App.confirmDialog` (focus-trapped modal). The canonical-vocabulary CSS discipline held: `components.css` gained ~309 LOC of shared primitives; `studio.css` net +8 LOC despite gaining tile grid, tablist, modal, page headers (slightly over the ≤60 target — 77 LOC final, justified area-specific layout).

Final test counts: **407 unit + 172 browser** passing. The browser delta is +49 net new tests (legs added 47; HAT removed 4 for the deleted tile X-button suite and inverted/rewrote 2 for the tab and tile dirty-gate behavior changes).

The HAT surfaced seven inline design refinements that materially altered the shipped surface vs. the original spec — captured in detail in `flight-log.md` under `### 05-hat-and-comprehensive-review`. None required a one-shot Developer review per the F4 lessons-learned threshold; all were CSS/JS layout/wiring with no new algorithms or cross-cutting state.

### Mission Criteria Advanced

| Mission criterion | F5 contribution |
|---|---|
| Each functional area reflects the design language and meets a quality bar suitable for showing externally | Studio brought to the bar; mirror of F4 chat-component shape applied to studio sub-modules |
| Common interaction patterns behave consistently across areas | `App.confirmDelete` extracted (chat consumes, queued for editor migration); `App.confirmDialog` shipped; `App.tabs` shipped; `disabled` SSoT for primary actions |
| Critical user flows progress without dead-ends | Agent CRUD lifecycle reworked end-to-end including dirty-gate confirmations and `Test` button on the General tab |
| Navigation state reflected in the URL and survives refresh | Hash routing extended to `#studio/{section}[/{name}/{tab}]`; refresh on every URL returns to that exact state |
| Automated browser tests cover critical flows | +49 net browser tests across tab idiom, dirty-state modal, tile grid, hash routing |

## What Went Well

- **Hash-routing free-redirect path** (`#studio` → `#studio/agents` → `…/{name}/general`) was predictable from the F3-router contract and worked without new redirect logic. The Architect first-pass review explicitly called this out before implementation.
- **Two-pass design review caught spec ambiguities** before implementation in every leg. Leg 02 testid clash (tile X vs editor Delete), leg 03 editor-Delete migration assumption, leg 04 Save SSoT internal contradiction — each found in review, fixed in spec, never reached the codebase.
- **`beforeunload` lifecycle correction** during leg 04 second-pass review (do NOT remove on `deactivate()`) was load-bearing — without it, chat → studio → chat round-trip would have silently broken tab-close protection.
- **Closure-locals → `this.*` migration** (leg 01) fixed a latent `serializeState` bug that pre-dated F5. Net architectural win.
- **Race-condition fixes during leg 03** (hydrate-before-loadAll URL clobber; same-agent re-select tab reset; `data-tab-id` short-id resolution) were absorbed inline cleanly because each was small and structural, not a new feature.
- **Accessibility review at flight end** caught one BLOCKING WCAG 1.3.1 issue (orphan `<label>` elements in general-tab.js) before commit; the fix landed in the same bundle.
- **Test coverage scaled with surface area**: 21 new tests in `test_flow_dirty_confirm.py` alone meaningfully validate behavior (focus-trap actually checked, ARIA contract verified including resolved id targets, `beforeunload` via synthetic-event + `defaultPrevented`).
- **Single-`replaceSub` discipline** preserved from F4. `grep -n 'App.router.replaceSub' studio.js` returns exactly one site.
- **`window.confirm` removed entirely** from studio.js (leg 04) — verified via grep.

## What Could Be Improved

### Process

- **Layout-as-implicit-assumption.** The flight spec never explicitly committed to "tile grid in sidebar"; it inherited that placement from the pre-flight studio shape. Leg 01 wrote `sectionContentEl` into the sidebar by default because the prior agent list lived there. The HAT walkthrough was the **first time the question was asked aloud** — and the user's answer was "main panel, not sidebar." Restructuring init() and inventing `updateContentVisibility()` was avoidable rework. **Future area-alignment flights should treat "what lives in sidebar vs main panel?" as an explicit Open Question, not an inherited shape.**
- **Multi-affordance destruction without justification.** The flight resolved "tile X-button + editor Delete" as separate affordances without articulating why both existed. The HAT removed the tile X — meaning leg 02's wrap-with-siblings DOM, keydown-bubble fix, three dedicated tests, and ~30 LOC of CSS was wasted work. **The design template should ask: "Does this flight introduce multiple destructive entry points for the same entity? If so, justify each."**
- **Per-tab dirty gate misread the data model.** Leg 04 specified "tab-change-when-dirty triggers `App.confirmDialog`" for all four routes (Back, section-nav, tile, tab). The HAT inverted the tab path because tabs share the same form's data — switching never discards. The leg spec didn't articulate the "do tabs share state?" question; the answer was implicitly "yes" (W3C tab idiom = alternative facets of the same entity), so the gate shouldn't have been specified at all. **Add a one-line rule to the tab-idiom doc: "gate tab-change only when the new panel discards rather than hides form state."**
- **Pre-existing init code wasn't audited against new contracts.** The studio's end-of-init `selectAgent(self._agents[0])` upgraded bare `#studio/agents` to `#studio/agents/{first}/general`, conflicting with leg 02's tile-grid-as-default-view contract. Leg 01 changed the URL contract; leg 02 changed the visual default; neither audited the legacy auto-select. **Add to area-alignment leg 01 templates: "scan area init() bottom block for legacy auto-selects against new URL contracts."**

### Technical

- **`updateContentVisibility()` is a manual visibility-state machine.** Wired into 7 call sites (`setActiveSection`, `doSelect`, `doEnterCreateMode`, `doHandleBack`, `handleDeleteEditor` empty branch, init bottom block, `cancelEdit` indirectly). It's the kind of imperative toggle that begs for a single derived render path. F6 admin will likely want the same shape — consider extracting `App.areaLayout(sidebar, content, {sections, render})` if a third consumer appears.
- **Editor Delete still uses inline two-step** (`studio.js:515-542`, capital-D label). With the tile X removed, `App.confirmDelete` has only one consumer (chat session items). Either migrate the editor Delete to `App.confirmDelete` (pass `confirmLabel: 'Confirm Delete?'` per call) so the helper has ≥2 consumers, or accept the divergence and document the rule (in-place destructive = `App.confirmDelete`; in-form Danger Zone = inline). Don't drift — F6 admin will likely add a third destructive surface (delete provider) and inherit whichever pattern is canonical.
- **Dead `escapeHtml` / `escapeAttr` shadow declarations** in `studio.js:928-929` and `agent-editor.js:52-53` (latter never used inside that module). Minor cleanup.
- **`.section-nav-item` role choice** — leg 01 chose `role="group"` over `role="tablist"` deliberately (sections have side-effects, not facet-of-same-entity). Worth documenting in `agents.md` as the canonical choice for "side-effecting nav lists."
- **`data-confirm-title` attribute hook on the tile name span** was removed correctly during HAT (no longer needed without tile-level confirm flow). Chat session items continue to use it — no debt.
- **Heading hierarchy** (`<h2>`/`<h3>` refinement to align editor title and section-title with proper semantic order) was deferred from leg 04 a11y review. Still deferred — flag for routine maintenance.

### Documentation

- **`agents.md` lines 263-264 are stale.** Both the "Agent tile" and "Confirm-delete" entries still describe the wrap-with-siblings + per-tile X-button + adjacent-sibling combinator design that HAT removed. Misleading — F6 admin alignment explicitly inherits this vocabulary. **Critical fix.**
- **The new section-content + editor swap layout pattern** (`updateContentVisibility()` and `.studio-section-content + .studio-editor` siblings with `.is-hidden` toggle) is undocumented. F6's admin needs this for the provider list-vs-editor swap.
- **Cancel button pairing with Save** (both flip `disabled` together via `checkDirty`; mode-aware behavior in `cancelEdit()`) is a useful idiom for any future entity editor — undocumented.
- **The hydrate-vs-fetch race pattern** (any area that deep-links into a list-item where the list is async-fetched must let `serializeState()` consider pending-hydrate state, not just committed state) needs a project-level note. F6 admin has the same shape and shouldn't rediscover it.
- **`beforeunload`-once-at-init lifecycle rule** (closure flag is the gate; do NOT remove on `deactivate()`) deserves a project-level area-lifecycle note.
- **The "tabs gate iff data discards" rule** codifies HAT refinement #6's lesson and prevents the same misread in F6.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| Section-content moved sidebar → main panel (HAT) | Implicit "tile grid lives in sidebar" inherited from pre-flight shape; user expectation was main panel | Yes — make "what lives in sidebar vs main panel?" an explicit Open Question for every area-alignment flight |
| Tile X-button removed entirely (HAT) | Centralizing destruction in editor Danger Zone is more discoverable + harder to misclick | Yes for **configuration entities** (agents, providers); chat sessions are ephemeral and may keep per-row X — decide explicitly per area |
| Cancel button added to action cluster (HAT) | Recovery affordance was missing; Save alone doesn't undo edits | Yes — `[Back] [Cancel] [Save]` is the canonical entity-editor cluster going forward |
| Tab-change dirty-gate inverted (HAT) | Tabs share the same form state; switching never discards data | Yes — codify "gate tab-change only when the new panel discards form state" as the tab-idiom rule |
| Auto-select-first-agent removed (HAT) | Legacy code conflicted with new tile-grid-as-default-view contract | Yes — audit area-init bottom blocks for legacy auto-selects in any future area-alignment flight |
| App-picker hover contrast fixed (`var(--nav-fg-hover)` → `var(--fg)`) in light theme | Token misuse: `nav-*` tokens are for the dark nav rail, not light surfaces | Yes — add a token-domain rule: `nav-*` tokens are scoped to the dark nav rail; popovers on body surfaces use `--fg` family |
| Page titles + "New Agent" button refresh (HAT) | Section views needed visible page identity; bare `+` icon was unclear | Yes — `.studio-page-header` + page-title h1 + right-aligned primary action is the canonical "page heading + primary action" pattern |
| `serializeState` pending-name fallback (leg 03) | Hydrate-before-loadAll race would clobber `#studio/agents/{name}/{tab}` to `#studio/agents` before `tryConsumePendingSelect` could run | Yes — document as the "hydrate-vs-fetch race" pattern; any area with deep-link + async list fetch needs this |
| Same-agent re-select tab preservation (leg 03) | `_refresh()` re-runs `selectAgent(found)` on every cross-area entry; resetting `_activeTab` would clobber the user's tab | Yes — selectAgent in any tabbed editor should preserve `_activeTab` when re-selecting the same agent |
| `data-tab-id` short-id resolution in `App.tabs` (leg 03) | Spec used `aria-controls` (full panel id) as tab id; consumers want logical short ids (`'general'`) | Yes — keep `data-tab-id` as the canonical tab-id source in the helper API |
| `beforeunload` NOT removed on `deactivate()` (leg 04 second-pass) | Removing on every cross-area exit would silently break tab-close protection after first round-trip | Yes — codify as a project-level area-lifecycle rule for singleton listeners |
| Editor Delete kept inline two-step (vs `App.confirmDelete`) | Test stability (`test_flow_agent_crud.py:73` asserts capital-D "Confirm Delete?"); migration deferred | Defer — revisit after F6 either justifies ≥2-consumer migration or accepts divergence permanently |

## Key Learnings

1. **Implicit shape inheritance is the highest-impact source of wasted work.** Layout, default-view selection, and per-action affordances inherited from pre-flight code without explicit re-evaluation produced the largest HAT-time corrections (section-content placement, auto-select, tile X-button). Make "audit pre-existing area shape against new contracts" a leg-1 acceptance criterion for area-alignment flights.

2. **The two-pass design review cap is correctly tuned.** Every autonomous leg landed within two passes; second passes routinely caught real issues (lifecycle correction, internal contradictions, save SSoT). The 2-pass-then-escalate rule prevented thrash.

3. **Helpers earn standardization at ≥2 consumers.** `App.confirmDelete` shipped with two consumers (chat sessions, tile X) but HAT removed the tile X consumer — leaving one. The standardization bar (≥2 consumers) is the right test for "is this a real primitive or a one-off?" and should drive the editor-Delete migration decision in F6.

4. **Race conditions cluster around async-list-fetch + deep-link-on-mount.** Three race fixes in leg 03 (URL clobber, tab reset, tab-id resolution) all stem from the same shape. F6 admin has the same shape; document the pattern so it's a one-line application, not a re-discovery.

5. **HAT scope discipline mostly held but one refinement was architectural.** Six of the seven HAT refinements were CSS/JS wiring and correctly handled inline. **Refinement #2 (layout flip) was architectural** — moving section-content from sidebar to main panel changed the visual hierarchy of the entire studio area and required 7 new call sites. For F6, treat any HAT refinement that changes layout topology as a divert candidate, not an inline fix.

6. **`disabled` as single source of truth scales.** Leg 04 made it the rule for Save; HAT extended it to Cancel without friction. The pattern (drop `.clean`/`.dirty` class machinery; opacity hooks key off `[disabled]`) is the canonical "primary action enables on dirty" idiom going forward.

## Recommendations

1. **(Critical) Update `agents.md`** to reflect post-HAT studio reality: fix lines 263-264's stale tile-X description; add an "Editor + section-content swap" layout entry; add a "Cancel/Save SSoT" idiom entry; add the "tabs gate iff data discards" rule to the tab-idiom entry; add the "hydrate-vs-fetch race" gotcha; add the "`beforeunload`-once-at-init" area-lifecycle rule; add the "`nav-*` tokens are scoped to the dark rail" token-domain rule.

2. **(Critical) Make "what lives in sidebar vs main panel?" an explicit Open Question in every area-alignment flight design** going forward. F6 admin's flight spec must answer this before leg 01.

3. **(Important) Add to the flight design template**: "Does this flight introduce multiple destructive entry points for the same entity? Justify each, or pick one canonical entry point." Would have caught the tile X / editor Delete redundancy pre-implementation.

4. **(Important) Add to area-alignment leg-01 acceptance criteria**: "Audit area `init()` bottom block for legacy behavior (auto-select, default-view assumptions) against the new URL contract." Would have caught the studio auto-select pre-HAT.

5. **(Important) Migrate the editor Delete to `App.confirmDelete`** (or document the divergence as canonical) before F6 adds a third destructive surface. Bring the helper to ≥2 consumers permanently or accept the inline pattern as the canonical "in-form Danger Zone" idiom.

## Action Items

- [ ] Update `the_one/agents.md` (stale tile content lines 263-264; new layout pattern; Cancel/Save SSoT; tab-idiom dirty-gate rule; hydrate-vs-fetch race; beforeunload lifecycle; nav-token domain). **Owner**: F5 follow-up or routine-maintenance.
- [ ] Add `cancelEdit` browser tests (3 cases: create-mode → tile grid; edit-mode → form revert; Cancel disabled-when-clean). **Owner**: routine-maintenance or F6.
- [ ] Add a "switch to General tab → select Ollama provider → see VRAM warning" browser test (currently no test exercises this after the tab restructure). **Owner**: routine-maintenance.
- [ ] Migrate editor Delete to `App.confirmDelete` OR document the divergence as canonical. **Owner**: F6 design-time decision.
- [ ] Address heading hierarchy a11y refinement deferred from leg 04 (`<h2>`/`<h3>` for editor title and section-title; `.section-nav-header` as `<h2>`). **Owner**: routine-maintenance.
- [ ] Remove dead `escapeHtml`/`escapeAttr` shadow declarations in `studio.js:928-929` and `agent-editor.js:52-53`. **Owner**: routine-maintenance.
- [ ] Decide chat session-delete consistency at mission debrief: follow studio (move to detail/edit view) or keep per-row X as deliberate ephemeral-vs-config asymmetry. **Owner**: M04 mission debrief.
- [ ] Consider extracting `App.areaLayout(sidebar, content, {sections, render})` if F6 admin makes a third consumer of the section-nav-in-sidebar + content-in-main-panel pattern. **Owner**: F6 design-time decision.
