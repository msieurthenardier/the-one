# Flight: Administration Polish

**Status**: in-flight
**Mission**: [GleepGlorp AI Rebrand & UX Polish](../../mission.md)

## Contributing to Criteria

- [ ] Each functional area (Chat, Studio, Administration) has been reviewed page-by-page and every screen meets a professional polish bar — empty states, loading states, error states, and primary-task flows all feel intentional *(this flight covers the Administration leg)*
- [ ] A coherent visual identity anchored to the new logo and a purple-led palette is present and consistent across all three areas, in both light and dark themes *(Admin pages take the Flight 2 design language vocabulary onto every screen)*
- [ ] Per-area routing and navigation behaves correctly across every page within an area: deep links resolve, page refresh restores the visible state, browser back/forward moves through history sensibly, and there are no dead routes, broken back targets, or routes that bounce the user somewhere unexpected *(catalogued and addressed for Admin pages in this flight)*
- [ ] Color contrast meets WCAG AA across the rebranded palette *(re-verified after any aesthetic adjustments)*
- [ ] All existing functionality (M01–M07 capabilities) continues working after the rebrand and polish passes *(no behavioral change; cosmetic + opportunistic-fix only)*
- [ ] Automated browser tests pass; visual-snapshot baselines regenerate cleanly *(closing leg regenerates baselines for the post-polish state)*

---

## Pre-Flight

### Objective

Take the Administration area page-by-page and bring every screen to a professional polish bar using the Flight 2 design language vocabulary (glass + bezel + V3b buttons + LED indicators + motion). Apply the aesthetic to the four Admin pages: **System** (Appearance / Encryption / Base Prompt), **LLM Providers** (grid + editor + Ollama lifecycle), **Built-in Tools** (tabbed grid + per-tool editor), and the dev-mode **Design Language** gallery (cosmetic refinement only — no structural change to the gallery itself). Close debrief debt from Flight 2 (4 token-hygiene items) up front so the polish legs operate on clean tokens. Wire the `.indicator-led` primitive to the Ollama lifecycle panel's loaded/unloaded model dots — the natural in-Admin LED-status consumer surfaced by Flight 2's debrief. Catalog and fix Admin-area routing/navigation issues that surface during HAT. Close with a snapshot regeneration + alignment HAT across both themes covering all four pages.

### Open Questions

- [x] **Custom dropdown for native `<select>`** → Defer to Flight 4 (Studio Polish). Studio has materially more select consumers (provider type per provider, model per agent, source type per MCP, etc.) than Admin; building the custom dropdown there amortizes the cost across more sites. Admin's selects continue to use native `<select>` with Flight 2's max-coverage option styling. Mission Known Issue stays open against Flight 4. Recorded in Design Decisions.
- [x] **LED wire-up sites in Admin** → The Ollama lifecycle panel's `.admin-pf-model-dot.loaded` (admin.css:90-91, an 8px circle with `box-shadow: 0 0 6px var(--status-success-glow)` when loaded) is the primary natural LED consumer. The Provider editor's "Test connection" surfaces auto-retrofit via the `.test-result-*::before` rule landed in Flight 2 — no extra work. No other in-Admin OAuth-status surface exists (OAuth is MCP-only and lives in Studio + Chat). Recorded in Design Decisions.
- [x] **Polish cadence — vibe vs autonomous** → Page-polish legs are interactive (the operator drives aesthetic-judgment calls about which surfaces want glass-substrate, which want bezel-inset, which form rows want tighter spacing). Token-hygiene and routing-sweep legs are autonomous. Final alignment leg is the HAT. Recorded in Design Decisions.
- [x] **Order — token hygiene first vs page polish first** → Token hygiene first. The four debrief items (radius bug, dead `--panel-shadow-glow`, duplicate `--panel-radius-sm`, V3b gradient duplication) are small fixes but each is a cleanup the page-polish legs would otherwise have to navigate around. Doing them up front gives every polish leg a clean substrate. Recorded in Design Decisions.
- [x] **Theme-toggle aesthetic** → Theme toggle is the *only* segmented-control affordance in Admin currently. Worth a vibe pass during Leg 02 (System polish) — could compose `.tab` from Flight 1's tab primitive, OR remain a bespoke `.admin-theme-toggle` styled with the bezel/glass vocabulary. Operator decides during Leg 02. Working assumption: stay bespoke (segmented-control affordance is distinct from tab-navigation affordance) and apply bezel-mini + accent-translucent active state. Recorded in Design Decisions.
- [ ] **Ollama model-dot LED retrofit detail** — current dot is an 8px round in `admin.css:90-91` (`border-radius: 50%`, `box-shadow: 0 0 6px var(--status-success-glow)` when `.loaded`); `.indicator-led` is a 10px round with reflective-crescent radial-gradient + `0 0 4px` outer glow. Two paths: (a) keep the current `.admin-pf-model-dot` class with a CSS rule that composes `.indicator-led` styles onto it; (b) **working assumption — path (b)** change the markup in `provider-models.js` to emit `<span class="indicator-led indicator-led--success">` (or `--idle` for unloaded) directly **at both render sites (`provider-models.js:346` for the loaded list + `:375` for the unloaded list)** and retire `.admin-pf-model-dot` (the rule pair in `admin.css:90-91`) as dead-selector cleanup. Path (a) is the fallback if the JS edit surfaces unexpected coupling. → Resolved in Leg 03 (operator + Developer agent pick during implementation; default path (b)).
- [ ] **Beforeunload + dirty-state behavior on cross-Admin navigation** — `admin.js:197-203` registers a beforeunload listener gated on the `dirty` closure flag, mirrored to the provider/tools editor sub-modules. **Leg 05 includes an explicit beforeunload checklist row** as part of the routing catalog, covering: (a) provider-editor dirty → section-nav-to-tools (confirm dialog fires), (b) tools-editor dirty → section-nav-to-providers (confirm dialog fires), (c) any-editor dirty → area-picker-pill switch to Studio/Chat (confirm dialog fires), (d) any-editor dirty → browser refresh / window-close (native beforeunload prompt fires). Any gap surfaced → fix inline if scope-light, else log as Known Issue for Flight 7. → Resolved in Leg 05.
- [ ] **Routing issues catalog** — direct-link to every Admin sub-route (`#admin`, `#admin/system`, `#admin/providers`, `#admin/providers/new`, `#admin/providers/{id}`, `#admin/tools`, `#admin/tools/{name}`, `#admin/design-language`) plus tool-tab persistence across refresh, plus back-button traversal through editor → grid → home. Catalog populated in Leg 05 HAT walkthrough; fixes applied inline where scope-light; non-trivial issues logged as Known Issues for Flight 7 (UI Performance Audit). → Resolved in Leg 05.
- [ ] **`agents.md` affordance-patterns updates** — Flight 2 added a Mission 08 F2 Design Language Layer subsection. This flight will surface (a) Ollama-dot → indicator-led wire-up pattern, (b) potentially the segmented-control vs tablist distinction (if Leg 02 codifies it). Decide at Leg 06 close whether new patterns warrant `agents.md` entries. → Resolved in Leg 06.

### Design Decisions

**Defer custom-dropdown component to Flight 4 (Studio Polish)**: Building the `<button>` + popover dropdown helper (~50-80 LOC + ARIA keyboard nav + markup migration at consumer sites) lands in Studio. Admin's native `<select>` consumers (provider type, tool config selects) continue using native popups with Flight 2's max-coverage option styling.
- Rationale: Studio has materially more dropdown consumers than Admin (provider type, model-per-agent, source type, agent-MCP toggles). Building the custom component in Studio amortizes the cost across more sites; Admin gets the benefit when the component is later threaded back through shared primitives. Per the mission Known Issue: "Suggested follow-up: Flight 4 (Studio Polish) or Flight 3 (Administration Polish), whichever first surfaces a need for a polished dropdown." Flight 4 surfaces more need.
- Trade-off: Admin keeps the unstyleable native popup chrome for one more flight cycle. Acceptable — Flight 2 already maxed out native styling on selected option + option list within native CSS limits.
- Alternatives rejected: (a) Build dropdown in Flight 3 — pays the cost in a flight that has 1-2 consumer sites; (b) Defer indefinitely — but Studio's selector density is large enough that one of those flights must build it.

**Token-hygiene leg runs FIRST**: Fix `tokens-section.js:30-32` undefined `--panel-radius-md`/`-lg` references, decide on `--panel-shadow-glow` (rip — currently dead per components.css:613 substitution rule), decide on `--panel-radius-sm` (retune from 6px → 4px for actual hierarchy with `--panel-radius: 6px`, since the slot exists and the gallery samples both), and extract V3b button-gradient to `--btn-v3-gradient` token (currently duplicated literally at components.css:59, :387, :426, :459).
- Rationale: All four are debrief carry-overs from Flight 2. Page-polish legs would otherwise have to navigate around them (e.g., V3b retune would touch 4 sites instead of 1; gallery radius samples would render as 0-radius squares). Land the cleanup up front so polish legs touch only their target surfaces.
- Trade-off: The token decisions (rip vs reserve) are one-time choices that constrain future polish flights. Mitigated by carrying the rationale into agents.md and the leg artifact so future maintenance reads cleanly. Specifically: `--panel-shadow-glow` is ripped (not reserved) — the Flight 2 composition rule of "glass replaces glow on chrome surfaces" already covers the active-state affordance need; if a future polish flight needs an accent-tinted glow for non-chrome consumers, it can define a new specific token at that time.

**Page polish is interactive vibe, token hygiene + routing sweep + alignment are mixed**: Legs 02/03/04 are interactive (operator drives aesthetic-judgment calls); Legs 01/05/06 are autonomous (Developer agent) where the work is mechanical, with operator HAT interleaved during Leg 05 routing-sweep and Leg 06 alignment.
- Rationale: Polish is the kind of "does this feel right" judgment that needs operator at the wheel — exactly what Flight 2's vibe-leg cadence proved out. Token hygiene is mechanical; routing-sweep is HAT-style walkthrough with autonomous fixes when scope-light.
- Trade-off: 4 interactive legs is a lot of operator time. Mitigated by per-leg pre-flight design that lets the operator see the scope before committing to the leg.

**Ollama model-dot → indicator-led wire-up**: The `.admin-pf-model-dot.loaded` rule (admin.css:90-91) is the natural in-Admin LED-status consumer. Wire-up happens during Leg 03 (Providers polish), as part of the Ollama-lifecycle-panel polish pass. The Provider-editor "Test connection" surface already auto-retrofits via the `.test-result-*::before` rule landed in Flight 2 — no new work there.
- Rationale: Closes a Flight 2 debrief recommendation (LED wire-up to status surfaces) in the right page-polish leg. Picks up the deferred "LED applications to status surfaces" loose end.
- Trade-off: Two viable wire-up paths (compose `.indicator-led` styles onto `.admin-pf-model-dot`, OR change provider-models.js markup to emit `.indicator-led` directly). Resolved at implementation time per the related Open Question.

**Theme toggle stays as a bespoke `.admin-theme-toggle` segmented control with bezel-mini + accent-translucent active state**: Working assumption (operator can override during Leg 02). The segmented-control affordance is semantically distinct from `.tab`/`.tablist` navigation, so composition onto the tab primitive would conflate two different affordances.
- Rationale: Three-option segmented control (Light / Auto / Dark) is a control-input affordance for a setting, not a navigation tablist. Keeping it bespoke keeps the affordance vocabulary cleanly distinct.
- Trade-off: Bespoke styling continues to live in admin.css:44-48 rather than composing a shared primitive. If a second segmented-control affordance surfaces in Studio or Chat polish flights, that flight is the right time to extract.
- **Implementation note (per design-review feedback)**: The current active-option rule at `admin.css:47` carries `box-shadow: 0 0 8px var(--accent-glow)` — when adding accent-translucent + bezel-mini, **rip the existing accent-glow** so we don't end up with two glows on one element (reads as muddy). The new treatment is `background: var(--accent-translucent)` + `box-shadow: var(--bezel-shadow-mini)` + the existing accent-fg color.

**Snapshot regen at flight close, mirroring Flight 1 and Flight 2**: Polish iterations don't regenerate baselines mid-flight. Final regen runs once in Leg 06 via `UPDATE_SNAPSHOTS=1 pytest -m pixel`. Baselines remain gitignored (local regression artifact only).
- Rationale: Polish iterations produce many small visual changes; mid-stream baselines rot fast. Single regen at close captures final state. Same trade-off applied successfully in Flight 1 + Flight 2.
- Trade-off: If a polish leg accidentally breaks an unrelated screen, we don't catch it until the closing leg. Mitigated by operator HAT being part of the close + the narrow-test-gate fallback running on each autonomous leg.

**Page-polish HAT folds into Leg 06 alignment, NOT into each page-polish leg**: Each page-polish leg ends when the operator confirms the page reads as on-brand — but HAT covering both themes × all four pages × all sub-routes is folded into the closing alignment leg. Avoids HAT fatigue mid-flight.
- Rationale: Per-leg HAT would duplicate work (operator already saw the live result during the vibe iteration); single-pass HAT at close is what verifies the full integration. Flight 2's Leg 06 HAT pattern worked.
- Trade-off: A page-polish-only regression that breaks an adjacent unrelated screen isn't caught until close. Mitigated by polish legs only touching their target surfaces (no shared-primitive edits) and the narrow gate catching JS regressions.

**Carry-forward from Flight 1 + Flight 2: opportunistic adjacent fixes at design-review-caught moments**: Continue the pattern. If a Developer agent surfaces an adjacent bug during a design-review pass (e.g., wrong API signature in a Test-connection callback, mis-cited line in a HAT verification step), fix in scope.
- Rationale: Both prior flights credited this pattern with meaningful debt close. Citation Audit + design-review-spawned Developer remains the highest-ROI control.
- Trade-off: Slight scope expansion. Acceptable — quick wins at the right moment cost less than a separate maintenance pass.

**`agents.md` updates folded into Leg 06**: Any new affordance patterns surfaced by this flight (Ollama-dot LED wire-up, theme-toggle segmented-control distinction) get added to the existing Mission 08 F2 Design Language Layer subsection during Leg 06's close steps, not in a separate documentation leg.
- Rationale: Mirrors Flight 2's pattern. Keeps the aesthetic-final-state commit coherent with the docs commit.
- Trade-off: Leg 06 grows in scope slightly. Acceptable; doc-only addition is low-risk.

### Prerequisites

- [x] Mission 08 active; Flights 1 + 2 completed and merged to main (`2f3b51c` on main as of flight design)
- [x] Flight 2 design vocabulary (glass + bezel + V3b + LED + motion tokens) committed and consumed across `tokens.css` + `components.css`
- [x] `.indicator-led` primitive exists in `components.css:922-935` with `--success`/`--warning`/`--danger`/`--idle` modifiers
- [x] V3b button gradient currently duplicated at `components.css:59, :387, :426, :459` (verified in recon — confirmed-live)
- [x] `--panel-shadow-glow` defined at `tokens.css:135` (light) + `:271` (dark) with zero CSS consumers — only a comment-reference at `components.css:613` (verified in recon — confirmed-live, safe to rip)
- [x] `--panel-radius-sm` defined at `tokens.css:132` + `:268` as `6px`, equal to `--panel-radius` (verified in recon — confirmed-live)
- [x] `tokens-section.js:30-32` references `--panel-radius-sm`/`-md`/`-lg`, only first is defined (verified in recon — confirmed-live)
- [x] Dev-mode-only Design Language gallery exists at `#admin/design-language` (Flight 2 Leg 01)
- [x] `tests/test_design_tokens_a11y.py` audit + `tests/browser/design_tokens.py` mirror in place (Flight 2 added 0 new parametrizations; glass tokens aren't text-on-color slots)
- [ ] Narrow-test-gate fallback in use for legs 1 + 5 + 6 (broad pytest hangs against live uvicorn DB per Flight 1 SQLite WAL anomaly; same gate works — `docker exec the-one pytest tests/test_design_tokens_a11y.py tests/test_token_definitions.py tests/test_oauth_provider_factory.py tests/test_platform_tempdirs.py -x -q --timeout 10`)
- [ ] Operator available for interactive vibe legs (02, 03, 04) and Leg 06 HAT — no batchable surrogate

### Pre-Flight Checklist
- [x] All open questions for pre-flight scope resolved (concrete polish specifics deferred to in-leg resolution and NOT pre-flight blockers)
- [x] Design decisions documented
- [x] Prerequisites verified
- [x] Validation approach defined
- [ ] Legs defined (six legs, see below)

---

## In-Flight

### Technical Approach

The flight is structured as **one autonomous prep leg → three interactive page-polish vibe legs → one mixed routing-sweep leg → one closing alignment leg**. Prep clears debrief debt from Flight 2; polish legs apply the design vocabulary page-by-page with operator at the wheel; routing-sweep catalogs deep-link / refresh / back-button behavior; alignment runs the 10-step ordered close.

**Prep (Leg 01)**:

*Leg 01 — Token hygiene + V3b gradient extraction*. Autonomous Developer-agent leg.
- **Fix `tokens-section.js:30-32`** — replace `['--panel-radius', '--panel-radius-sm', '--panel-radius-md', '--panel-radius-lg']` with `['--panel-radius', '--panel-radius-sm']` (the actual defined tokens). The gallery's radius swatches will now render correctly instead of as 0-radius squares with blank hex labels.
- **Rip `--panel-shadow-glow`** — token defined at `tokens.css:135` (light, `0 0 12px var(--accent-glow)`) and `:271` (dark, layered shadow). Zero CSS consumers (substituted out at all 4 sites during Flight 2 Leg 03; only `components.css:613` retains a comment-reference noting the intentional drop). Remove all FOUR references: (1) the light-theme declaration at `tokens.css:135`, (2) the dark-theme declaration at `tokens.css:271`, (3) the stale comment-reference inside the `--glass-bg` comment block at `tokens.css:60` (rewrite to describe the composition rule without naming the removed token), (4) the comment-reference at `components.css:613` (rewrite to past tense — "glass surfaces replaced the prior accent-glow treatment" — without naming the removed token). Also remove the historical-context line in `agents.md` if present.
- **Retune `--panel-radius-sm` from `6px` → `4px`** in both themes. Provides actual hierarchy between `--panel-radius: 6px` (large panels) and `--panel-radius-sm: 4px` (small chips/swatches). Verify gallery + any current consumers visually pre/post (admin.css:31, :44 use the small radius; Flight 2 added it to a few primitives).
- **Extract V3b gradient to `--btn-v3-gradient` token** — define in `tokens.css` `@layer tokens` as a single token holding the gradient image; substitute at all 4 sites (`components.css:59 .app-picker-button`, `:387 .btn-outlined-primary`, `:426 .btn-filled-primary`, `:459 .btn-muted-destructive`). Token name follows Flight 2's `--bezel-shadow` / `--glass-bg` precedent. **Safety note (per design-review verification)**: `grep -rn "linear-gradient(to bottom" the_one/interfaces/web/static/css/` confirms only 4 matches and all are in `components.css` at the four V3b sites — no false positives in `admin.css`, `studio.css`, `chat.css`, `base.css`. Safe to extract.
- **Mirror radius changes into `tests/browser/design_tokens.py`** if it tracks `--panel-radius-sm` (verified during design review: it currently does NOT track radius tokens, so this step is a no-op; left in the leg in case a future audit row adds the token).
- **Verification gate**: narrow test gate green + WCAG audit green + visual scan of the gallery (radius swatches now render correctly + button-family appearance unchanged) + `grep -c "linear-gradient(to bottom" the_one/interfaces/web/static/css/components.css` returns 0 (V3b extraction sentinel — currently returns 4 across the four sites) + `grep -rn "panel-shadow-glow" the_one/interfaces/web/static/` returns nothing (rip sentinel).

**Page-polish (Legs 02–04)** — interactive vibe legs. The Flight Director walks the operator through micro-iterations per page: presents current state, presents 2-4 polish options, applies, operator reloads, iterates. The end of each leg has the operator confirm "this page is on-brand."

*Leg 02 — System page polish*. Vibe.
- **Page header**: Currently `.page-header` + `.page-title` (canonical). Verify alignment.
- **Appearance section**: theme-toggle bespoke segmented control (`.admin-theme-toggle` + `.admin-theme-option`) — apply `--bezel-shadow-mini` to the container, `var(--accent-translucent)` to the active option, possibly a small LED-dot indicator in the active option. Working assumption per Design Decisions; operator confirms.
- **Encryption section**: Warning callout (`.admin-system-warning`) — currently flat `--status-warning-bg-soft-2` + `--status-warning-border`. **Working assumption**: keep `var(--status-warning-bg-soft-2)` as the background (it's an audited WCAG pair with `--status-warning` text) and add `--bezel-shadow-inset` for recessed feel. **If the operator wants a glass-tinted surface variant**, re-run `docker exec the-one pytest tests/test_design_tokens_a11y.py -v` mid-leg before continuing — replacing the background with a low-alpha glass over `var(--bg)` is NOT an audited pair and could regress AA contrast. Iterate.
- **Rotate Encryption Key button**: Already `.btn-muted-destructive` (canonical) — should look correct from Flight 2's V3b treatment. Verify.
- **Base Prompt block**: `.admin-base-prompt` is a `<pre>` with `var(--surface)` background — apply `--bezel-shadow-inset` for "recessed code well" feel matching `.field-input` family. Iterate.
- **Flash feedback**: `.admin-system-flash` (success/error) — verify on-brand.
- **Iterate until operator confirms System reads as on-brand.**

*Leg 03 — LLM Providers grid + editor polish (includes Ollama-dot LED wire-up)*. Vibe.
- **Grid view (`renderProvidersGrid`)**: `.entity-tile-grid` of `.entity-tile`s, each with a `.admin-provider-badge--{type}` color-coded provider-type badge top-right + `.entity-tile-name` + `.entity-tile-description`. Tiles inherit Flight 2 glass+bezel. Polish: badge spacing/positioning, tile spacing, hover/focus alignment with the rest of the chrome.
- **Editor view (`renderProviderEditor`)**: editor-header (canonical) + `.editor-section` blocks. Form fields use `.field-input` (gets `--bezel-shadow-inset` from Flight 2). API-key wrap (`.api-key-wrap` + `.api-key-eye`) — verify on-brand. Test-connection button (`.btn-outlined-primary.test-provider-btn`) — verify V3b. Test-result display (`.test-result` + spans) — already gets LED auto-retrofit from Flight 2 (`.test-result-*::before` rule).
- **Models list (`.admin-pf-models-list`)**: Flat-bordered list of `.admin-pf-model-item` rows. Consider bezel-inset or `.list-item` composition.
- **Ollama lifecycle panel**: `.admin-pf-model-row` rows with `.admin-pf-model-dot` (8px circle, gets `box-shadow: 0 0 6px var(--status-success-glow)` when `.loaded`) + name + size + per-row action buttons. **LED wire-up**: replace `.admin-pf-model-dot.loaded` with `.indicator-led.indicator-led--success`; idle state with `.indicator-led.indicator-led--idle`. Two paths discussed in Open Questions; **default path (b)** — JS markup edit at BOTH `provider-models.js:346` (loaded list emission) AND `:375` (unloaded list emission); after the markup change, also retire the `.admin-pf-model-dot{,.loaded}` rule pair in `admin.css:90-91` as dead-selector cleanup. Path (a) (CSS compose onto `.admin-pf-model-dot`) is the fallback if the JS edit surfaces unexpected coupling.
- **Pull UI**: progress bar (`.admin-pf-pull-progress` + `.admin-pf-pull-fill` + `.admin-pf-pull-text`) — already accent-tinted; verify on-brand with new aesthetic.
- **Cap chips (`.cap-chip` + `.cap-chip-no-tools`)**: already use canonical `.chip` from Flight 2; verify the `--no-tools` variant uses danger palette correctly.
- **Action cluster**: editor-bottom Save/Cancel/Back/Delete — canonical from Flight 2; verify.
- **Action-blocked-message**: hidden by default; surfaced when delete is blocked. Verify on-brand.
- **Iterate until operator confirms Providers grid + editor + Ollama panel read as on-brand.**

*Leg 04 — Built-in Tools grid + editor polish*. Vibe. **Pre-flight expectation (per design-review verification)**: `tools-form-helpers.js` already composes canonical primitives (`.chip`, `.chip-remove`, `.field-error` — all from Flight 2). Expect this to be the **lightest of the three polish legs**; the operator should not over-search for polish targets in the form-helpers area.
- **Grid view (`renderToolsGrid`)**: page-header + `.tablist` (Filesystem / Execution / Web tabs, canonical from Flight 2's tab primitive) + `.tabpanel`s each containing `.entity-tile-grid` of `.entity-tile.tool-tile`s. Tiles already inherit Flight 2 glass+bezel; per-tile iOS-toggle (`.tool-enable-switch` + `.tool-enable-switch-track`) is the only non-design-language primitive (Mission Known Issue: deferred extraction). Polish: tile spacing, iOS-toggle aesthetic alignment with the rest of the chrome (kept in admin.css per Flight 2 design decision; do NOT extract here).
- **Tool tile badge (`.entity-tile-badge.admin-tool-badge--{category}`)**: color-coded by tool category (filesystem/execution/web). Verify on-brand.
- **Editor view (`renderToolsEditor`)**: editor-header + form fields + per-tool config UI from `tools-form-helpers.js` (527 lines — complex). The form-helper primitives are shared infrastructure; only cosmetic alignment here, no structural changes.
- **Iterate until operator confirms Tools grid + editor read as on-brand.**

**Routing + sweep (Leg 05)** — mixed autonomous + interactive.

*Leg 05 — Admin routing sweep + Design Language page cosmetic*. Mixed: interactive HAT for routing catalog (two-pass — catalog first, fix second, to avoid operator context-switching mid-walkthrough); autonomous Developer agent for scope-light fixes; in-leg cosmetic pass on the gallery page.
- **Routing catalog (pass 1, catalog-only)**: Walk through every Admin deep-link / refresh / back-button scenario with operator. Catalog any unexpected behavior. Coverage: 8 sub-routes (`#admin`, `#admin/system`, `#admin/providers`, `#admin/providers/new`, `#admin/providers/{id}`, `#admin/tools`, `#admin/tools/{name}`, `#admin/design-language`) × 3 transitions (deep-link / refresh / back-button) ≈ 24 checks.
- **Beforeunload checklist (extends catalog)**: (a) provider-editor dirty → section-nav-to-tools (confirm dialog fires), (b) tools-editor dirty → section-nav-to-providers (confirm dialog fires), (c) any-editor dirty → area-picker-pill switch to Studio/Chat (confirm dialog fires), (d) any-editor dirty → browser refresh / window-close (native beforeunload prompt fires).
- **Routing fixes (pass 2)**: Scope-light routing bugs (e.g., URL not updating on internal nav, refresh losing pending state) get fixed during the leg via Developer agent spawn.
- **Log Known Issue**: Non-trivial routing gaps (e.g., a missing area-state restoration that needs a registered-categories registry refactor) get logged in mission Known Issues for Flight 7 (UI Performance Audit) which the mission already designates as the catch-all for cross-area routing issues.
- **Design Language page cosmetic**: After Leg 01 ripped the dead radius references, the gallery page-header + section-eyebrow spacing + section gap rhythm get a polish pass. **Out of scope**: the gallery's swatch grids and per-section sample primitives themselves (those are the canonical aesthetic spec already locked by Flight 2). Cosmetic-only — no structural change to gallery sections (per mission Flight 3 scope: "the new dev-mode Design Language category from Flight 2 (cosmetic-only — no structural change to the gallery itself)").

**Close (Leg 06)** — 10-step ordered alignment.

*Leg 06 — WCAG + snapshots + HAT + agents.md + stability*. Mixed autonomous + interactive (same 10-step pattern as Flight 2 Leg 06). Each step's output is the next step's input:

1. **Pre-close grep sweep** — `grep -E '#[0-9a-f]{3,6}' the_one/interfaces/web/static/css/*.css | grep -v '/\\*'` to confirm no hardcoded hex slipped past page polish; `grep -rn 'admin-pf-model-dot' the_one/interfaces/web/static/` to confirm the Leg 03 LED wire-up removed all old references if path (b) was taken; `grep -c "linear-gradient(to bottom" the_one/interfaces/web/static/css/components.css` returns 0 (V3b extraction sentinel from Leg 01); `grep -rn "panel-shadow-glow" the_one/interfaces/web/static/` returns nothing (rip sentinel from Leg 01).
2. **Run WCAG audit** — `docker exec the-one pytest tests/test_design_tokens_a11y.py -v`. Audit must be green BEFORE snapshot regen.
3. **`make rebuild`** — bake final CSS / Python mirror state into running container.
4. **`make _ensure-playwright`** — re-install playwright deps (named volume survives rebuild but deps go missing, per Flight 1 debrief Action Item #4 documented in Flight 2's standing playbook).
5. **`UPDATE_SNAPSHOTS=1 pytest -m pixel tests/browser/test_visual_snapshots.py`** — regenerate baselines (expected: 10/12 pass; the 2 `chat_with_messages` × dark + light remain blocked by Flight 1 Known Issue — `app_with_agent` seeder, Flight 5 territory).
6. **Walk operator through HAT** in light + dark themes, covering all four Admin pages (System / Providers grid + editor + Ollama panel / Tools grid + editor / Design Language gallery) + sub-routes. Tactical fixes inline; structural issues logged.
7. **Codify any new affordance patterns in `agents.md`** — append to the existing Mission 08 F2 Design Language Layer subsection. Candidates: Ollama-dot LED wire-up pattern (a worked example of `.indicator-led` retrofit), theme-toggle segmented-control distinction (if Leg 02 codified the segmented-vs-tablist boundary).
8. **Snapshot stability re-run** without `UPDATE_SNAPSHOTS=1` to confirm new baselines stable on rerun (10/12 pass).
9. **Final narrow-test-gate** — `docker exec the-one pytest tests/test_design_tokens_a11y.py tests/test_token_definitions.py tests/test_oauth_provider_factory.py tests/test_platform_tempdirs.py -x -q --timeout 10` — confirm narrow gate stable.
10. **Update flight status** `in-flight` → `landed`; check off flight in mission.md; commit all artifacts.

**Narrow-test-gate fallback** (carried from Flight 1 + Flight 2): autonomous legs use the 4-module narrow gate above. Broad pytest may be attempted in Leg 06 once but is expected to hang on the SQLite WAL anomaly until a future maintenance pass.

### Checkpoints

- [x] **Leg 1 done**: `tokens-section.js` radius bug fixed; `--panel-shadow-glow` ripped from 6 sites (including the api.py consumer surfaced during design review); `--panel-radius-sm` retuned to `4px`; `--btn-v3-gradient` extracted and consumed at 4 sites; narrow gate 56/56 + WCAG 45/45 green.
- [x] **Leg 2 done**: Topbar restructured — app-picker chevron+popover retired entirely; three flat area buttons (Chat / Agent Studio / System) replace it; brand banner replaces the wordmark+icon. Area labels renamed (`'Agent Chat'` → `'Chat'`, `'Settings'` → `'System'`). Operator-requested scope expansion (replaced original System page polish, which moved to Leg 03). Operator visual-confirmed.
- [x] **Leg 3 done**: System page polish (Appearance / Base Prompt / Encryption — reordered) + cross-page absorbed items (Tools editor prompt header/body, chip-list-editor, Providers test result, Design Language gallery cleanup) + two new shared primitives (`.banner` + `.code-block`) + body-level scrollbar bug fix. Operator visual-confirmed.
- [x] **Leg 4 done**: Ollama model-dot LED wire-up complete (`.indicator-led--success` for loaded, `--idle` for unloaded); test-result LED + label spacing fixed; remaining Providers items deemed on-brand by operator. Leg closed early.
- [x] **Leg 5 done**: Chip-list-editor UX polished (Tab commit, click-to-insert-before, × button visibility, Backspace position-awareness); boolean tool config fields composed onto `.checkbox-primary`. Operator confirms.
- [ ] **Leg 6 done**: Admin routing catalog complete; scope-light fixes applied; non-trivial issues logged as Known Issues for Flight 7; Design Language gallery page cosmetic pass complete.
- [ ] **Leg 7 done**: WCAG audit green; 10/12 visual-snapshot baselines regenerated cleanly (2 by Flight 1 Known Issue); `agents.md` updates folded in if applicable; HAT walkthrough operator-confirmed across both themes × all four pages; narrow gate stable on rerun.

### Adaptation Criteria

**Divert if**:
- A page polish discovers a structural change is needed (not cosmetic) — pause, surface, decide whether to expand flight scope, defer to a follow-up flight, or abandon the change.
- The Ollama-dot LED wire-up surfaces a deeper rendering issue (e.g., the existing `.admin-pf-model-dot.loaded` glow is consumed by other state machines in provider-models.js JS) — log and decide path (a) compose vs path (b) markup replace.
- WCAG audit cannot be passed after page polish within two iterations — escalate; may require a token shift or accepting non-AA-passing edge case as a debt entry.
- Routing-sweep catalogs >5 non-trivial issues — pause, decide whether Flight 7 absorbs all of them or this flight's scope expands.
- A `tools-form-helpers.js` cosmetic pass surfaces structural form-helper bugs — log as Known Issue, do not absorb into this flight.

**Acceptable variations**:
- Per-leg ordering within Legs 02-04 (System vs Providers vs Tools order) — independent.
- Whether Leg 03's LED wire-up uses path (a) compose or path (b) markup-replace — implementation-time call.
- Whether Leg 05 surfaces the gallery cosmetic pass as a sub-step or a separate mini-leg — leg-time call; both work.
- Theme-toggle styling working assumption (bespoke segmented control with bezel-mini + accent-translucent) is overridable by the operator during Leg 02.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `01-token-hygiene-and-v3b-extract` — Autonomous Developer-agent leg. Fixed `tokens-section.js:30-32` undefined radius references; ripped `--panel-shadow-glow` from 6 sites (Leg 01 design review surfaced the api.py consumer Flight 2 debrief recon missed — methodology lesson: grep whole package not just `static/`); retuned `--panel-radius-sm` `6px → 4px`; extracted V3b button gradient to `--btn-v3-gradient` token at 4 consumer sites. 18 mechanical edits across 5 source files + 1 docs file. All 7 grep sentinels green; narrow gate 56/56; WCAG 45/45.
- [x] `02-topbar-restructure-and-area-renames` — Operator-requested scope expansion at Leg 02 kickoff (replaces the originally-planned System page polish, which shifts to Leg 03). Retired the app-picker chevron+popover entirely; replaced with three flat area buttons (Chat / Agent Studio / System) in the topbar actions. Replaced the `<h1>` wordmark + icon with the brand banner image (`gleepglorp_banner.png`). Renames: chat `'Agent Chat'` → `'Chat'`; admin `'Settings'` → `'System'` (+ sidebarLabel + ariaLabel). `.app-picker-button[aria-current="page"]` CSS rule provides the "you are here" state. ~100 LOC of popover state machine removed. Operator visual-confirmed. Narrow gate 56/56; WCAG 45/45.
- [x] `03-system-page-polish` *(vibe)* — Scope expanded mid-HAT from System-only to System + cross-page polish (Tools editor prompt + chip-list, Providers test result, Design Language gallery) + 2 new shared primitives extracted (`.banner` with error/warning/info variants, `.code-block` chat-style terminal aesthetic) + body-level scrollbar bug fix (`body { overflow: hidden }` + flex-column `min-height: 0` chain). Theme toggle final: V3b family + solid-filled active option. 4 iteration rounds.
- [x] `04-providers-and-ollama-polish` *(vibe)* — Wired the canonical `.indicator-led` primitive into the Ollama lifecycle panel (loaded → `--success`, available → `--idle`); retired the `.admin-pf-model-dot` rule pair as dead-selector cleanup. Fixed test-result LED + label touching (added `margin-right: 6px` + `vertical-align: middle` to the `.test-result-*::before` shared rule). Operator deemed remaining Providers items on-brand; leg closed early.
- [x] `05-tools-polish` *(vibe)* — Chip-list-editor UX polish: Tab key commits chip (joining Enter/comma); click on chip body re-positions the input before that chip for insert-before flow; Backspace-on-empty walks `previousElementSibling` so re-positioned input deletes the right chip; × button color updated to `--accent` (rest) → `--status-danger` (hover) for better visibility. Boolean tool config fields gain `.checkbox-primary` class (canonical Flight 2 primitive). Operator deemed tabbed grid + iOS toggles already on-brand; leg scoped to chip-list + checkbox polish only.
- [ ] `06-routing-sweep-and-design-language-cosmetic` — Mixed autonomous + interactive. Admin routing catalog (deep-link / refresh / back-button across `#admin/*` sub-routes); scope-light fixes inline; non-trivial issues logged as Known Issues for Flight 7. Design Language gallery page cosmetic pass (cosmetic-only per mission scope).
- [ ] `07-alignment-and-snapshot-regen` — 10-step ordered close: pre-close grep, WCAG audit, rebuild, playwright, snapshot regen, HAT × 2 themes × 4 pages, agents.md updates if applicable, stability rerun, final narrow gate, status update + commit.

---

## Post-Flight

### Completion Checklist

- [ ] All 6 legs completed
- [ ] Token hygiene: `tokens-section.js` radius bug fixed; `--panel-shadow-glow` ripped; `--panel-radius-sm` retuned to `4px`; `--btn-v3-gradient` extracted and consumed at 4 sites; tokens still align with `tests/browser/design_tokens.py` mirror
- [ ] System page reads as on-brand (Appearance theme toggle + Encryption rotate flow + Base Prompt block)
- [ ] Providers grid reads as on-brand; Provider editor reads as on-brand; Ollama lifecycle panel reads as on-brand; Ollama model-dot LED wire-up complete
- [ ] Built-in Tools grid (tabbed) reads as on-brand; Per-tool editor reads as on-brand
- [ ] Design Language gallery cosmetic pass complete (no structural change)
- [ ] Admin routing/navigation catalog produced; scope-light issues fixed; non-trivial issues logged for Flight 7
- [ ] WCAG audit green
- [ ] Visual-snapshot baselines regenerated locally; 10/12 pass on rerun without `UPDATE_SNAPSHOTS=1` (the 2 `chat_with_messages` × dark + light remain Flight 1 Known Issue scope)
- [ ] `prefers-reduced-motion` and `prefers-reduced-transparency` posture still works (token-layer fallbacks from Flight 2 carry forward; no new motion / glass added in this flight)
- [ ] `agents.md` updates folded in if new affordance patterns surfaced
- [ ] HAT walkthrough complete in both themes × all four Admin pages + sub-routes
- [ ] Code merged; flight status updated to `landed`

### Verification

- **Token hygiene check**: `grep -n "panel-radius-md\|panel-radius-lg" the_one/interfaces/web/static/js/areas/admin/design-language/tokens-section.js` returns nothing; `grep -rn "panel-shadow-glow" the_one/interfaces/web/static/css/` returns nothing; `grep -n "btn-v3-gradient" the_one/interfaces/web/static/css/tokens.css` shows the new declaration; `grep -c "linear-gradient(to bottom" the_one/interfaces/web/static/css/components.css` returns 0 in the V3b-consumer rules (only inside the new token definition).
- **Page polish check**: Load each Admin page in both themes; chrome (page-header / editor-header / section-nav) carries Flight 2 glass+bezel; form fields carry bezel-inset; buttons carry V3b; LED indicators visible on Ollama loaded models.
- **Routing check**: Direct-load every sub-route + verify state restoration on refresh + verify back-button traversal. Tool-tab persistence on `#admin/tools` refresh confirmed (currently module-level, not URL-encoded — behavioral expectation documented in this flight's catalog).
- **WCAG check**: `docker exec the-one pytest tests/test_design_tokens_a11y.py -v` — all parametrizations pass.
- **Snapshot stability check**: After regen in Leg 6, re-run `pytest -m pixel tests/browser/test_visual_snapshots.py` without `UPDATE_SNAPSHOTS=1`; passes cleanly modulo the 2 Flight 1 Known Issue blockers.
- **Narrow gate stable**: 56/56 (same as Flight 1 + Flight 2 baseline).
- **`agents.md` check**: Existing Mission 08 F2 Design Language Layer subsection extended with any new patterns from this flight; structure stays coherent.
