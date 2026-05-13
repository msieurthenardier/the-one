# Flight: Studio Polish

**Status**: landed
**Mission**: [GleepGlorp AI Rebrand & UX Polish](../../mission.md)

## Contributing to Criteria

- [ ] Each functional area (Chat, Studio, Administration) has been reviewed page-by-page and every screen meets a professional polish bar *(this flight covers the Studio leg)*
- [ ] A coherent visual identity anchored to the new logo and a purple-led palette is present and consistent across all three areas *(Studio inherits the polished shell from Flight 3.5; per-page polish brings Studio to parity with Admin)*
- [ ] Per-area routing and navigation behaves correctly across every page within an area *(Studio routing sweep covers Agents grid / Agent editor / MCP Sources grid + editor)*
- [ ] Color contrast meets WCAG AA across the rebranded palette *(re-verified; Flight 3.5 audit gap on `--shell-chrome-bg` closed in this flight's prep leg)*
- [ ] All existing functionality (M01–M07 capabilities) continues working *(no behavioral change in polish work; structural infrastructure parity adds confirmLeave + stale-then guard to Studio matching Admin)*
- [ ] Automated browser tests pass; visual-snapshot baselines regenerate cleanly *(closing leg regenerates baselines; cross-area Playwright regression test for the B2 dirty-gate adds explicit coverage)*

---

## Pre-Flight

### Objective

Page-by-page polish pass across the Studio area (Agents grid + Agent editor tabs + MCP Sources grid + editor), inheriting the alien-dashboard shell housing from Flight 3.5, with the design-language vocabulary applied to Studio's interior surfaces. **Plus** roll in carry-forward debt from Flight 3 and Flight 3.5 debriefs:

1. **Prep leg** closes Flight 3.5 debrief technical-debt items (reduced-transparency block extension for shell tokens; WCAG audit gap close; `--bg-gradient` rename + `--shell-chrome-bg` comment; agents.md cross-flight convention lifts) BEFORE Studio polish begins so polish work composes on a coherent base.

2. **Custom dropdown component** (mission Known Issue → Flight 3 deferred → Flight 4) — Studio has 4 native `<select>` sites (provider selector, model selector, MCP type, MCP command-runtime); building the dropdown here amortizes the cost.

3. **Cross-area dirty-gate parity** — implement `confirmLeave(proceed, abort)` hook on the studio area descriptor (matching the admin pattern from Flight 3 Leg 06) so Studio editor dirty state gates cross-area navigation uniformly. Add stale-then guard preemptively to Studio's `area.activate()` async fetches (avoid the chat→admin race we hit in Flight 3 Leg 06). Plus the Playwright B2 regression test (Flight 3 debrief Action Item #1, deferred to here) covering both admin and studio cross-area dirty paths in one test pass.

### Open Questions

- [x] **Flight 4 scope shaving** (per Flight 3.5 debrief recommendation #8) → Shell housing inheritance means per-page polish operates on `.content-panel` interior only — no chrome retreatment per area. Confirmed: 2 vibe page-polish legs (one for Agents, one for MCP Sources) plus 1 leg for the Knowledge stub if needed. Knowledge tab is currently a 21-line stub (`stub-knowledge.js`); cosmetic polish on a stub is premature. Recorded in Design Decisions. Polish scope: Agents grid + Agent editor (4 tabs: General / Knowledge / Tools / MCPs) + MCP Sources grid + MCP Server editor. The MCPs tab inside Agent editor is cosmetic-only per mission spec (no structural change to M07 UI).
- [x] **Reduced-transparency posture extension** (Flight 3.5 debrief recommendation #1) → Land in Leg 01 prep leg. Specifically: under `@media (prefers-reduced-transparency: reduce)`, override `--shell-chrome-bg` to its solid base color (no grain), suppress the topbar sheen (via new `--shell-topbar-sheen` token = transparent under reduced-transparency), suppress `--shell-frame-glow`. Recorded in Design Decisions.
- [x] **WCAG audit gap close** (Flight 3.5 debrief recommendation #2) → Land in Leg 01 prep leg. Add `(dark, fg, shell_chrome_bg, 4.5)` + `(light, fg, shell_chrome_bg, 4.5)` parametrizations + the muted variants. Mirror values into `tests/browser/design_tokens.py`. Recorded in Design Decisions.
- [x] **`--bg-gradient` rename** (Flight 3.5 debrief recommendation #6) → Rename to `--shell-bg` in Leg 01 prep. Provides backward-compat alias `--bg-gradient: var(--shell-bg)` for one flight cycle so external consumers (none today, but defensive). Recorded in Design Decisions.
- [x] **agents.md docs updates** (Flight 3.5 debrief recommendations #3, #4, #5, #7) → All four fold into Leg 01 prep's agents.md touch-ups: lift theme-generalization-via-tokenization convention to F2 subsection; lift "land dark, port light" cadence to a new flight-design-conventions subsection; cross-reference Flight 3 carry-forward docs items under F3 subsection pointing at F3.5 placement; add cascade-override caveat comment to `--shell-chrome-bg` token definition. Recorded in Design Decisions.
- [x] **Custom dropdown component shape** → `<button>` + popover dropdown helper (~50-80 LOC + ARIA keyboard nav per the mission Known Issue spec). Compose the design-language vocabulary (glass-substrate popover, V3b-styled trigger button, accent-translucent active option, mini-glass active-row treatment). Markup migration at the 4 Studio sites + 2-3 Admin sites that still use native `<select>` (provider type editor's type dropdown, tools editor selects). Live as `App.dropdown(triggerEl, options, callbacks)` helper. Recorded in Design Decisions.
- [x] **Studio confirmLeave + stale-then guard scope** → Implement `confirmLeave(proceed, abort)` on the studio area descriptor following admin's `_confirmLeaveImpl` pattern (closure over local `dirty` flag inside `init()`). Studio has dirty-state in: agent-editor's General/Knowledge/Tools/MCPs tab forms, mcp-server-editor's form. Both need the same `dirty && inEditor` gate. Apply stale-then guard to Studio's `area.activate()` async fetches (fetchAgents, fetchAgent, fetchMCPServers, fetchMCPServer detail). Same pattern Admin's `populateProviderGrid` + `selectTool.then` use. Recorded in Design Decisions.
- [x] **Playwright B2 regression test scope** → One test file covering both areas' cross-area dirty-gate. Sequence: open editor → dirty → click topbar cross-area → confirm dialog appears → cancel → still on dirty editor + URL rolled back; then dirty → topbar → confirm → land on target area + return → assert no stale editor (the Flight 3 stale-then race). Covers admin + studio in one test. Recorded in Design Decisions.
- [ ] **Page-polish iteration order** — operator drives in vibe legs (per Flight 3.5 lesson: "axes to cover" not "sequence to execute"). Suggested starting point: Agents grid → Agent editor tabs → MCP Sources grid → MCP Server editor. Operator-resolved in Leg 02 + Leg 03 kickoff.
- [ ] **LED wire-up sites on MCP source connection state** (Flight 2 debrief Action Item, Flight 3 carry-forward) — identify the source-connection-status surfaces in MCP grid + editor; wire to `.indicator-led--success` (connected) / `--warning` (auth-required) / `--danger` (error) / `--idle` (disconnected). Resolved at Leg 03 implementation.

### Design Decisions

**Flight 4 scope shaving — shell inheritance**: Per Flight 3.5 debrief recommendation #8, per-page polish in Studio operates on `.content-panel` interior only. No chrome retreatment per area — `#main-content` already has the L-bracket framing the studio interior. No body-bg work. No topbar/sidebar work. Polish surfaces: Agents tile grid, Agent editor tabs (General / Knowledge / Tools / MCPs), MCP Sources grid, MCP Server editor.
- Rationale: Flight 3.5 made the shell universal. Per-area polish in Flights 3 + 4 + 6 (Chat) operate on the interior. Avoids re-litigating chrome decisions per area.
- Trade-off: None — this is a scope-clarification, not a scope-cut.

**Knowledge tab is a stub — polish-deferred**: `stub-knowledge.js` is 21 lines (placeholder). Cosmetic polish on a stub is premature; the Knowledge tab will be polished when the underlying feature lands. Mission Known Issue noted.
- Rationale: Polishing a placeholder produces decorated emptiness, not professional polish. The Knowledge feature itself needs design before polish.
- Trade-off: Leaves the Knowledge tab visually inconsistent with the rest of Studio. Acceptable; documented as Known Issue.

**Prep leg runs FIRST — closes Flight 3.5 debrief tech debt before polish**: Leg 01 is autonomous, mechanical, closes 7 Flight 3.5 debrief items (reduced-transparency block, WCAG audit, `--bg-gradient` rename, `--shell-chrome-bg` comment, agents.md cross-flight convention lifts).
- Rationale: Mirrors Flight 3 Leg 01 pattern. Subsequent polish legs operate on a clean substrate; reduced-transparency posture is coherent when Studio composes on top.
- Trade-off: 5+ items in one leg is wide scope. Acceptable — all autonomous, all mechanical, all interlock.

**Custom dropdown component lands in its own leg** (Leg 04, with explicit migration checkpoint): The native `<select>` popup chrome design-language gap is a mission Known Issue. Studio has 4 native sites + Admin has 2-3 + **Chat has 1 (`#chat-agent-select` at `chat.js:55`)** — total 7-8 migration sites.
- Implementation: `<button>` trigger + `<div role="listbox">` popover. ARIA keyboard nav (Arrow keys + Home/End + Enter/Space + Escape). Compose design-language vocabulary: V3b trigger button + glass popover + accent-translucent active option + mini-glass active-row treatment.
- Component lives as `App.dropdown(triggerEl, options, callbacks)` helper in `static/js/dropdown.js` (mirror existing `App.tabs`, `App.confirmDialog`, `App.confirmDelete` pattern). Closure-based init-once, returns imperative handle.
- **Migration scope includes `#chat-agent-select`** (Chat area's agent selector — high-traffic, on-shell, frequently-used). Per Architect design review: leaving it native while migrating Studio's lower-traffic selectors creates a visible inconsistency post-flight that Flight 6 would have to revisit. Migrate opportunistically in this leg.
- **Explicit migration checkpoint** (per Architect design review — Leg 04 conflates 3 work shapes: helper-build / popover-vibe / migration; risk of open-ended vibe eating migration time): Before vibe-close, ALL 7-8 migration sites must be swapped to `App.dropdown` + smoke-verified (no behavioral regression). Acceptance criterion: `grep -E '<select.*field-input|<select.*field-select' the_one/interfaces/web/static/js/areas/` returns no matches in the migrated areas.
- Rationale: Closes a long-running mission Known Issue. Centralizes dropdown UX so future consumers compose rather than re-derive.
- Trade-off: 50-80 LOC of new helper code + ARIA testing + 7-8 site migration. Scope-bounded by the migration checkpoint.

**Cross-area dirty-gate parity for Studio** (scope: smaller than initial framing per Architect design review — Studio already has inline gate logic; the work is EXTRACTION + EXPOSURE, not from-scratch implementation):
- **Inline dirty+inEditor gate already exists** at `studio.js:301-303` in the sidebar `setActiveSection` flow — uses `App.confirmDialog` with the same shape as admin's pre-Flight-3-Leg-06 pattern.
- **Work**: extract the existing inline predicate into `self._confirmLeaveImpl` closure (over the existing local `dirty` flag) + expose `confirmLeave` on the area descriptor. Pattern-match to admin's `_confirmLeaveImpl` (`admin.js:628`).
- **`inEditor` predicate** must cover both editor mount contexts: `(activeSection === 'agents' && _selectedAgent)` AND `(activeSection === 'mcp-sources' && mcpSourceFormMode)` — exact mirror of the existing inline gate.
- **Stale-then guard scope** (corrected per Architect design review): Studio already guards `fetchMcpSources_()` (lines 470, 475, 484) + `fetchMcpSourceTypes()` (line 355 continuation). `fetchAgent` per-agent-detail does NOT exist — agents load only via `loadAll()` at init (lines 758-773), already guarded. **Actual remaining gap**: re-audit `loadAll()` continuations + agent-editor mount-path Promise resolutions for any un-guarded `.then` blocks. Leg 05 reframes as "verify + gap-fill," not infrastructure-from-scratch.
- Rationale: Flight 3 Leg 06 surfaced both bugs in admin. Studio inherited some guards from prior flight work; remainder is identification + closure.
- Trade-off: Smaller than initial estimate. ~20 LOC, mostly extraction.

**Playwright B2 regression test covers BOTH admin and studio**: One Playwright test file. Two parametrized tests, one per area: (a) open editor → dirty → topbar cross-area click → confirm dialog appears → cancel → URL rolled back, editor still mounted; (b) dirty → confirm → navigate → return → assert no stale editor (verifies stale-then guard).
- Rationale: Flight 3 deferred this to Flight 4 to amortize across both areas. Building it once for both areas with parametrization is cheaper than building twice.
- Trade-off: Test file growth (~80 LOC). Closes a high-value regression risk.

**Reduced-transparency block extension** (Flight 3.5 debrief recommendation #1): Under `@media (prefers-reduced-transparency: reduce)`, the shell tokens override to suppression mode:
- `--shell-chrome-bg`: override to the solid base color (no grain layer). Dark = `#20202a`, light = `#d4d8df`.
- New `--shell-topbar-sheen` token (extracted from the inlined gradient at `#app-topbar`): rgba sheen at rest, transparent under reduced-transparency.
- `--shell-frame-glow`: override to transparent under reduced-transparency (no inner halo).
- Rationale: Flight 2 established the token-layer fallback pattern; Flight 3.5 introduced shell tokens but missed updating the reduced-transparency block. Closing the gap now keeps reduced-transparency posture coherent.
- Trade-off: One new token (`--shell-topbar-sheen`) so reduced-transparency can suppress it. Acceptable — extracts a one-site literal into a token to enable the fallback.

**`--bg-gradient` → `--shell-bg` HARD rename** (no alias — per Architect design review): Repurposed in Flight 3.5 from a "page backdrop gradient" to a "chrome continuation surface." Token names are semantic API; misleading names invite regressions.
- Audit-verified consumer count: 1 (`base.css:10` `body { background: var(--bg-gradient); }`). No external consumers. Backward-compat alias is over-engineering for zero benefit.
- Hard-rename in Leg 01 prep. Update the one consumer; delete the old token.
- Rationale: Token API hygiene. Saves cognitive overhead for future readers.
- Trade-off: None — single internal consumer.

**agents.md cross-flight convention lifts**: Three patterns get promoted from per-flight subsections to canonical cross-flight guidance:
- **Theme generalization via tokenization** (Flight 3 + 3.5 confirmed): when a treatment differs only by value across themes, parametrize through tokens and drop `[data-theme="..."]` selector prefix. Promote to F2 subsection as a canonical composition rule (it underpins F3, F3.5, and future flights).
- **"Land dark, port light" vibe cadence** (Flight 3.5 originated): for vibe legs translating symmetrically across themes, land dark first as the aesthetic anchor; port light at leg close as a value-swap exercise. Avoids 2× decision load during operator-bandwidth bottleneck. Promote to a new **"vibe-leg conventions"** subsection (per Architect design review — narrower and more accurate than "flight-design conventions" since it documents how vibe legs run, not flight-design constraints generally).
- **Flight 3 carry-forward docs cross-reference**: add a one-line pointer under F3 affordance vocabulary that the topbar `<img>` CLS contract + legacy class-as-JS-handle pattern live in F3.5. So F3 searchers find them.

**Snapshot regen at flight close** (mirrors Flights 1/2/3/3.5): vibe legs do NOT regenerate baselines mid-flight. Final regen in Leg 07 alignment leg.

### Prerequisites

- [x] Mission 08 active; Flights 1 + 2 + 3 + 3.5 completed and merged to main (`c0a716c` on main as of flight design)
- [x] Flight 3.5 shell housing in place (`#main-content` L-bracket, unified metallic chrome on topbar + sidebar)
- [x] Flight 3.5 shell tokens defined (`--shell-chamfer`, `--shell-frame-fill`, `--shell-content-fill`, `--shell-frame-glow`, `--shell-chrome-bg`, `--bg-gradient`)
- [x] `--accent-glow` defined (used by both inner-glow + new dropdown's hover-state per design language)
- [x] `App.tabs()` primitive available (Studio's Agent editor uses tabs)
- [x] `App.confirmDialog()` available (for `confirmLeave` hook reuse)
- [x] `wireChipListEditor` shared code path operational (`tools-form-helpers.js` from Flight 3 Leg 05 — Studio's tools-tab.js consumes it)
- [x] Reduced-transparency `@media` block exists in `tokens.css` (Flight 2 origin, extensible)
- [x] WCAG audit + Python mirror in place (`tests/test_design_tokens_a11y.py`, `tests/browser/design_tokens.py`)
- [x] `confirmLeave` hook contract defined on area descriptor (Flight 3 Leg 06; admin implements; Studio will follow same pattern)
- [x] Stale-then guard pattern canonical (admin's `populateProviderGrid` + `selectTool.then`; Studio will mirror)
- [x] `.indicator-led` primitive available with `--success` / `--warning` / `--danger` / `--idle` modifiers
- [ ] Narrow-test-gate fallback (broad pytest hangs per SQLite WAL anomaly; same gate works)
- [ ] Operator available for Legs 02 + 03 + 06 vibes + Leg 07 HAT

### Pre-Flight Checklist

- [x] All open questions resolved with working assumptions / Design Decisions
- [x] Design decisions documented
- [x] Prerequisites verified
- [x] Validation approach defined
- [ ] Legs defined (7 legs, see below)

---

## In-Flight

### Technical Approach

**Seven legs**: 1 autonomous prep + 2 interactive vibe (Agents + MCP Sources polish) + 1 mixed-autonomous-and-vibe (custom dropdown — component design + vibe-driven popover treatment) + 1 autonomous (Studio dirty-gate parity + B2 regression test) + 1 mixed (routing sweep) + 1 closing alignment.

**Prep (Leg 01)**:

*Leg 01 — Prep + Flight 3.5 debrief debt close*. Autonomous, mechanical. 7 items:

1. **Reduced-transparency `@media` block extension** in `tokens.css`: override `--shell-chrome-bg` to its solid base (no grain layer) per theme; introduce `--shell-topbar-sheen` token (extract the inlined gradient from `#app-topbar` rule) so reduced-transparency can suppress it via the token; override `--shell-frame-glow: transparent` under reduced-transparency.
2. **WCAG audit gap close**: add parametrizations `(dark, fg, shell_chrome_bg, 4.5)` + `(light, fg, shell_chrome_bg, 4.5)` + the muted variants in `tests/test_design_tokens_a11y.py`. Mirror values into `tests/browser/design_tokens.py`. Audit must remain green.
3. **`--bg-gradient` → `--shell-bg` HARD rename** (no alias per Architect design review — only 1 consumer): rename the token in `tokens.css` (both themes). Delete `--bg-gradient`. Update the one consumer (`base.css:10` body bg).
4. **`--shell-chrome-bg` cascade-override comment**: add a one-line comment at the token's definition site noting "to strip grain, edit token definition, not via cascade override" so future agents don't search-miss.
5. **agents.md**: lift "theme generalization via tokenization" convention from F3.5 prose to F2 design-language-foundation subsection as a canonical composition rule. Add to F2's composition-rules list.
6. **agents.md**: add new "Vibe-leg conventions" subsection (per Architect design review — narrower than "flight-design conventions"; documents how vibe legs run, not flight-design constraints generally) at the top of the Design system section, documenting "land dark, port light" vibe cadence + the gallery-as-iteration-substrate pattern.
7. **agents.md**: add cross-reference under F3 affordance vocabulary pointing to F3.5 for the topbar `<img>` CLS contract + legacy class-as-JS-handle pattern.

Verification gate: narrow gate green + WCAG audit green (with 4+ new parametrizations passing) + visual scan that body bg still reads as chrome (no regression from rename).

**Page-polish (Legs 02-03)** — interactive vibe legs:

*Leg 02 — Agents page polish* (vibe). Operator drives.
- **Agents tile grid** (`renderAgentsGrid` if it exists; otherwise the rendering path in `studio.js`): `.entity-tile` already inherits Flight 2 glass+bezel. Polish: tile spacing, badge positioning (if agents have badges), hover/focus alignment with the rest of the chrome.
- **Agent editor tabs** (General / Knowledge / Tools / MCPs — canonical `App.tabs()` tablist + per-tab content):
  - **General tab** (`general-tab.js` — 165 lines): persona text, provider selector (native `<select>` — will be replaced in Leg 04), model selector (native `<select>` — Leg 04), advanced field rows. Polish: field-row spacing, label alignment, info-icon positioning.
  - **Knowledge tab** (`knowledge-tab.js` — 21 lines stub + `stub-knowledge.js`): polish-deferred per Design Decisions. Verify the placeholder reads on-brand (no broken styling) but no design effort.
  - **Tools tab** (`tools-tab.js` — 250 lines): per-agent tool override editor. Composes `wireChipListEditor` shared code path (chip-list UX from Flight 3 Leg 05 ships automatically). Polish: override panel layout, locked-chip styling consistency.
  - **MCPs tab** (`mcps-tab.js` — 382 lines): per-mission spec, COSMETIC-ONLY — no structural change to M07 UI. Polish: list spacing, source-status presentation (LED wire-up candidate, see Leg 03 scope below).
- Iterate until operator confirms Agents page reads on-brand. Apply "land dark, port light" cadence (operator drives dark first, port to light at leg close).

*Leg 03 — MCP Sources polish* (vibe). Operator drives.
- **Pre-leg audit** (per Architect design review — pre-scope the LED wire-up): before Leg 03 kickoff, audit `mcp-server-editor.js` + `mcp-servers-grid.js` for the connection-status surface(s) where the LED primitive lands. Pin the exact consumer sites in the leg artifact (file:line) so the LED wire-up is a known-finite-scope sub-task, isolated from the open-ended polish vibe. Expected outputs: connection-status display in MCP grid tiles (per-server), connection-status indicator in the editor (single LED on the editor header), possibly connection-status during OAuth flow stages.
- **MCP Servers grid** (`mcp-servers-grid.js` — 117 lines): tile grid for MCP source list. Polish: tile spacing, status indicators.
- **MCP Server editor** (`mcp-server-editor.js` — 1654 lines): per-source detail form + connection test + (per-source) OAuth flow. Polish: form layout, section grouping, status display (LED wire-up consumer per pre-leg audit).
- **LED wire-up on MCP source connection state** (Flight 2 debrief Action Item, carried-forward): wire `<span class="indicator-led indicator-led--{success|warning|danger|idle}">` at the pre-scoped consumer sites. Mirrors Flight 3 Leg 04 Ollama wire-up.
- Iterate until operator confirms MCP Sources reads on-brand.

**Custom dropdown component (Leg 04)**:

*Leg 04 — Custom dropdown component + migration* (mixed autonomous + interactive). Build the `App.dropdown(triggerEl, options, callbacks)` helper in `static/js/dropdown.js`. Markup:
- `<button class="dropdown-trigger app-picker-button">` (compose V3b styling) with current value display + chevron icon.
- `<div role="listbox" class="dropdown-popover">` (compose glass treatment) populated with `<button role="option">` items.
- Active option: `aria-selected="true"` + accent-translucent + mini-glass styling.
- ARIA keyboard nav: Arrow keys (Up/Down navigate, Home/End jump), Enter/Space activate, Escape close.
- Closure-based state (similar to `App.tabs`).

Vibe portion: operator iterates on popover treatment (rounded corners, padding, hover state, max-height/overflow behavior). Compose existing design-language tokens.

Migration: 4 Studio sites (general-tab.js:52 + :77; mcp-server-editor.js:506 + :533) + 2-3 Admin sites (provider-editor.js type-select, tools-editor.js any `<select>`). Verify each site post-migration reads identically to before (no behavioral regression).

**Studio dirty-gate parity + B2 regression test (Leg 05)**:

*Leg 05 — Studio confirmLeave + stale-then guard + Playwright B2 regression test* (autonomous).
- **`confirmLeave(proceed, abort)` hook on studio descriptor** (mirrors admin's pattern). `self._confirmLeaveImpl` wired inside `init()` over closure-local `dirty` flag. Same condition as admin's sidebar gate: `dirty && inEditor` (where `inEditor` covers agent-editor and mcp-server-editor mounted contexts).
- **Stale-then guard** added to Studio's `area.activate()` async fetches: `fetchAgents`, `fetchAgent` detail, `fetchMCPServers`, `fetchMCPServer` detail. Pattern: `if (currentSection !== 'agents') return;` (or equivalent per section).
- **Playwright B2 regression test** in `tests/browser/test_flow_cross_area_dirty_gate.py` (new file). Two parametrized tests, one per area (admin, studio):
  - (a) `dirty_editor_topbar_cancel_keeps_state`: open editor → dirty → click cross-area topbar button → confirm dialog appears → cancel → URL rolls back, dirty editor still mounted.
  - (b) `dirty_editor_topbar_confirm_navigates_cleanly`: open editor → dirty → topbar → confirm → land on target area → return to source area → assert non-stale UI (verifies stale-then guard).

**Routing sweep (Leg 06)**:

*Leg 06 — Studio routing sweep + opportunistic fixes* (mixed autonomous + interactive HAT). Two-pass cadence (catalog first, fix second, per Flight 3 Leg 06 lesson).
- **Routing catalog**: walk through Studio sub-routes — `#studio` bare (defaults to agents), `#studio/agents`, `#studio/agents/new`, `#studio/agents/{id}`, `#studio/knowledge`, `#studio/mcp-sources`, `#studio/mcp-sources/new`, `#studio/mcp-sources/{id}` — × 3 transitions (deep-link / refresh / back-button) ≈ 24 checks.
- **Beforeunload / cross-area dirty-gate check**: agent-editor dirty → topbar Chat/System (confirm dialog fires); mcp-editor dirty → same.
- **Fix inline** scope-light routing bugs.
- **Log Known Issues** for non-trivial gaps (Flight 7 catch-all per mission spec).

**Close (Leg 07)**:

*Leg 07 — Alignment + snapshot regen* (10-step ordered close per Flight 2/3/3.5 template). Pre-close grep + WCAG audit + rebuild + playwright + snapshot regen + HAT × 2 themes × 8 pages + agents.md F4 subsection + stability rerun + final narrow gate + status + commit.

### Checkpoints

- [ ] **Leg 01 done**: Reduced-transparency block extended; WCAG audit gap closed (4+ new parametrizations); `--bg-gradient` renamed to `--shell-bg` with backward-compat alias; agents.md F2 / flight-design-conventions / F3 cross-references all landed.
- [ ] **Leg 02 done**: Agents tile grid + Agent editor (General / Knowledge / Tools / MCPs tabs) read on-brand in both themes; operator confirms.
- [ ] **Leg 03 done**: MCP Servers grid + MCP Server editor read on-brand; LED wire-up on source connection state complete (`.indicator-led--{state}` at consumer sites).
- [~] **Leg 04 skipped** (operator decision, 2026-05-13): native `<select>` accepted as-is; Known Issue carries forward to a future flight.
- [x] **Leg 05 done**: Studio `confirmLeave` hook implemented; Studio stale-then guards added; Playwright B2 regression test covering both areas passes.
- [x] **Leg 06 done**: Studio routing catalog complete; scope-light fixes applied; non-trivial issues logged.
- [x] **Leg 07 done**: WCAG audit green; 10/12 snapshot baselines regenerated cleanly; agents.md F4 subsection added; HAT walkthrough operator-confirmed both themes × all 8 pages; narrow gate stable.

### Adaptation Criteria

**Divert if**:
- Custom dropdown ARIA keyboard nav can't be implemented within the leg's budget — escalate; either drop ARIA nav as a Known Issue (less-than-ideal but better than blocking the leg) or extend Leg 04 scope.
- MCP Server editor (1654 lines) polish surfaces a structural change need — pause, decide whether to expand or defer to a future flight.
- Studio's existing routing has a deep architectural gap that exceeds scope-light fix budget — log as Flight 7 territory.

**Acceptable variations**:
- Per-leg vibe ordering (Agents first vs MCP Sources first within Leg 02 / Leg 03) — operator-driven.
- Whether dropdown migration covers all 6-7 sites in this flight or defers some to a future maintenance pass. **Resolved 2026-05-13**: operator declined the full Leg 04 — native `<select>` accepted; Known Issue carries forward.
- Whether the Playwright test in Leg 05 uses one test file or two (admin + studio split).

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `01-prep-and-debrief-debt-close` — Autonomous. 7 mechanical items: reduced-transparency block extension; WCAG audit gap close on `--shell-chrome-bg`; `--bg-gradient` → `--shell-bg` rename; `--shell-chrome-bg` cascade-override comment; agents.md theme-generalization-via-tokenization convention lift; agents.md "land dark, port light" cadence + flight-design conventions subsection; agents.md F3 cross-reference for carry-forward docs items.
- [x] `02-agents-polish` *(vibe)* — Interactive. Agents tile grid + Agent editor (General / Knowledge / Tools / MCPs tabs). Knowledge tab stub-polish-deferred. Chip-list UX from Flight 3 ships via shared code path automatically.
- [x] `03-mcp-sources-polish` *(vibe)* — Interactive. **Pre-leg audit** to pin the LED wire-up consumer sites in `mcp-server-editor.js` + `mcp-servers-grid.js` (per Architect design review — isolates the LED sub-task from the 1654-line-editor polish vibe). MCP Servers grid + MCP Server editor polish. LED wire-up on source connection state at pre-scoped sites (Flight 2 debrief Action Item carried-forward).
- [~] `04-custom-dropdown-component` *(autonomous + vibe)* — **SKIPPED** (operator decision, 2026-05-13): native `<select>` works fine in current usage; the polish wasn't worth the helper-build + ARIA-nav + 8-site migration cost. The mission Known Issue stays open and carries forward to a future flight if/when a dropdown surface surfaces a real need. Original scope retained below for reference: `App.dropdown(triggerEl, options, callbacks)` helper in `static/js/dropdown.js`. ARIA keyboard nav. Compose design-language vocabulary. Migrate **8 sites**: 4 Studio (`general-tab.js:52, :77`; `mcp-server-editor.js:506, :533`) + 1 Chat (`chat.js:55` agent-select — Architect-flagged, opportunistic) + 2-3 Admin (provider-editor type-select, tools-editor selects).
- [x] `05-studio-dirty-gate-parity-and-b2-regression-test` — Autonomous. **EXTRACT** Studio's existing inline `dirty + inEditor` gate at `studio.js:301-303` into `self._confirmLeaveImpl` closure + expose `confirmLeave` on descriptor (pattern-match admin's `_confirmLeaveImpl` at `admin.js:628`). Verify + gap-fill Studio's stale-then guards (Studio already has SOME; audit `loadAll()` continuations + agent-editor mount-path Promise resolutions for un-guarded `.then` blocks per Architect design review). Playwright B2 regression test covering both admin + studio (2 parametrized tests in new `tests/browser/test_flow_cross_area_dirty_gate.py`).
- [x] `06-studio-routing-sweep` — Mixed autonomous + HAT. Studio routing catalog (8 sub-routes × 3 transitions ≈ 24 checks + beforeunload dirty-gate scenarios). Scope-light fixes inline.
- [x] `07-alignment-and-snapshot-regen` — 10-step ordered close per Flight 2/3/3.5 template. Pre-close grep + WCAG audit + rebuild + playwright + snapshot regen + HAT × 2 themes × all 8 pages + agents.md F4 subsection + stability rerun + final narrow gate + status + commit.

---

## Post-Flight

### Completion Checklist

- [ ] All 7 legs completed
- [ ] Leg 01 prep deliverables: reduced-transparency block extended; WCAG audit gap closed; `--bg-gradient` renamed; `--shell-chrome-bg` comment added; agents.md F2/flight-conventions/F3-cross-reference landed
- [ ] Studio Agents grid + Agent editor (4 tabs) read on-brand both themes
- [ ] Studio MCP Sources grid + Server editor read on-brand both themes
- [ ] LED wire-up on MCP source connection state
- [~] ~~Custom dropdown component shipped + 6-7 sites migrated~~ — SKIPPED per operator decision; native `<select>` accepted, Known Issue carries forward
- [ ] Studio `confirmLeave` hook + stale-then guards implemented
- [ ] Playwright B2 regression test covers both admin + studio cross-area dirty paths
- [ ] Studio routing catalog produced; scope-light fixes applied; non-trivial issues logged
- [ ] WCAG audit green (with new shell-chrome-bg parametrizations)
- [ ] Visual-snapshot baselines regenerated; 10/12 pass on rerun without UPDATE_SNAPSHOTS=1 (the 2 `chat_with_messages` blockers remain Flight 5 territory)
- [ ] `agents.md` F4 subsection added; cross-flight convention lifts landed (theme-generalization, land-dark-port-light)
- [ ] HAT walkthrough complete in both themes × all 8 pages
- [ ] Code merged; flight status updated to `landed`

### Verification

- **Studio aesthetic check**: Load each Studio sub-route × 2 themes; every screen reads on-brand consistent with Admin's polish.
- **WCAG check**: `docker exec the-one pytest tests/test_design_tokens_a11y.py -v` — 49+ parametrizations (45 existing + 4+ new shell-chrome-bg) all pass.
- **Snapshot stability check**: After regen in Leg 07, re-run without `UPDATE_SNAPSHOTS=1`; 10/12 stable.
- **Reduced-transparency check**: Emulate `prefers-reduced-transparency: reduce`; verify shell loses grain + sheen + glow (degrades to solid chrome).
- **`agents.md` check**: F2 has theme-generalization convention; new "flight-design conventions" subsection has land-dark-port-light cadence; F3 has cross-reference to F3.5 docs items; new F4 subsection has Studio polish + dropdown component + cross-area-dirty-gate-parity entries.
- **Dropdown ARIA check**: Tab to a migrated dropdown trigger; press Enter; navigate options via Arrow keys; Enter to select; Escape to close. Screen reader announces options correctly.
- **B2 regression check**: `pytest tests/browser/test_flow_cross_area_dirty_gate.py` passes; both admin and studio paths covered.
- **Narrow gate stable**: 56/56.
