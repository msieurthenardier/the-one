# Flight: Connector UX Cleanup

**Status**: landed
**Mission**: [Discord Connector Depth & Robustness](../../mission.md)

## Contributing to Criteria

- [x] Mission criterion #1 (Discord-shaped form): re-styled to sdcon design language + MCP-editor reference shape. Substrate's six-layer contract unchanged.
- [x] Mission criterion #2 (Discord-shaped vocabulary): verbose technical labels replaced with human-friendly copy + info-icon tooltips throughout.
- [x] Mission criterion #18 (fresh operator under fifteen minutes): cumulative UX polish reduces visual friction (HAT-iterated through 8 rounds).
- [x] Mission criterion #19 (full working-day daily-driver): operational consistency between MCP editor and connector editor reduces mode-switching cognitive cost.
- [ ] Mission criterion #14 (operator-editable directive) — **PARTIALLY REVERTED in F5 L6 HAT round-8** per operator decision. Defaults visible in styled codeblock; per-account operator override removed. Re-evaluation candidate for F5 debrief or future UX maturity mission.

## Source artifacts driving this flight

- **F4 mission-flight-debrief** (`missions/11-discord-connector-depth/flights/04-ux-hotfixes-from-f3-debrief/flight-debrief.md`) — F4 closed F3-debrief's near-term hotfixes and codified the `cross-flight-ux-debt-reconciliation` + `touched-surface-ux-debt-folding` disciplines that gate this flight's recon. F4 also explicitly DEFERRED several routine-maintenance candidates (C3 AIAT cluster; chronic UI tests; `_xxxValues` getter unification; etc.) — those stay deferred, NOT bundled here.
- **Interactive operator enumeration session** (2026-05-23 — captured in this flight's planning conversation) — 10 UX items enumerated through guided discussion with the operator, using the Discord Connector editor + Cave Man Bot Connectors tab as the live reference and the Design Language page + MCP editor as the canonical-primitive references. Items below are verbatim from that enumeration; no scope expansion at planning.
- **Design Language page** (`the_one/interfaces/web/static/js/areas/admin/design-language/fields-section.js`) — canonical primitive catalog: `.field-input` / `.field-select` / `.checkbox-primary` / `.field-info-icon`.
- **MCP editor** (`the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js`) — already-styled reference for the same problem shape: per-type form rendering, test/refresh-connection placement, info-icon hint pattern, tool-enable-switch (iOS toggle) for booleans.

---

## Pre-Flight

### Objective

Re-style the connector editor (both new-connector and edit-connector flows) + agent-Connectors-tab to consume the existing sdcon design-language primitives, mirroring the MCP editor's pattern. Move runtime-config (Intents/Guilds/Presence/Advanced) from the General tab to the Access-and-Routing tab so tab semantics become coherent (General = WHAT the bot is; Access and Routing = HOW it behaves). Fold `// TEST CONNECTION` + `// INVITE` into the Connection section as footer rows, mirroring MCP editor's Refresh-connection placement. Replace verbose technical help-text with info-icon tooltips and human-friendly copy. Close two specific Cave Man Bot Connectors-tab visual bugs: Peers dropdown body fills the full tile width with no scoping container, and the empty "Selected entries" area renders as a confusing blank box when no chips are selected. Conclude with an explicit element-by-element sweep of the touched surfaces verifying every visible element maps to either a design-language primitive or an MCP-editor pattern, with a deferral list noting any element whose visual treatment needs a future UX-mission scope. Final HAT is operator-driven (operator clicks; agent guides verification steps). **NO new UI components built in this flight.** ~350-500 LOC across `connector-form-discord.js`, `connector-account-editor.js`, `connectors-tab.js`, `discoverable-dropdown.js`, plus minor CSS additions and one new sweep-coverage report artifact.

The flight is explicitly framed as the operator-requested cleanup of cumulative connector-editor UX debt before F6 (peer-name attribution; M10 Bug C; CRITICAL most-deferred). The same Adaptation Criteria discipline F4 used applies here: if new UX issues surface during implementation OR during the sweep leg, fold in OR escalate as Known UX Gap with a near-term path — NOT defer to F8/F10 or a hypothetical-future UX mission.

### Open Questions

*All resolved at planning per crew interview (2026-05-23). Resolutions promoted to Design Decisions below.*

### Design Decisions

**Source-of-style references — Design Language page (catalog) + MCP editor (working reference)** *(operator decision)*:
- The Design Language page (`#admin/design-language`, source under `the_one/interfaces/web/static/js/areas/admin/design-language/`) is the canonical primitive catalog. The `fields-section.js` enumerates the four primitives this flight reuses: `.field-input` (text + textarea + select), `.field-select` (paired with `.field-input` for selects), `.checkbox-primary` (single + multi-select), `.field-info-icon` (SVG-circle-i tooltip trigger).
- The MCP editor (`mcp-server-editor.js`) is the working reference for the same problem shape — per-type form rendering, test-connection placement, info-icon hints, iOS-toggle-for-boolean. Where two interpretations of "design-language-compliant" diverge, the MCP editor's choice wins.
- **NO new UI components built in this flight.** The sweep leg's deferral list captures any element whose visual treatment needs a new primitive; those become a future-UX-mission scope rather than F5 work.

**Leg ordering — primitives-first then section-shape, sweep last** *(operator: "leg ordering is flexible")*:
- L1 lands the form-control re-styling (items 1 + 4 + 5) BEFORE the section-shape changes. Re-styling the controls first means L2's Test-Connection-fold and L3's Move-Config-and-Relabel can rely on the new classes being in place. Mirrors the F1-F4 codification-first precedent in spirit (apply contract before consumers).
- L2 lands the Test-Connection + Invite fold (item 8) before L3's Move-Config because L3 is the bigger section-shape change and may need to settle in isolation.
- L3 lands Move-Config + Labels together (items 2 + 3). Both touch the same surface (the typed Discord form's `renderConnectionFields`); splitting would force two diff windows on the same code.
- L4 lands Connectors-tab axis cleanup (items 6 + 7) — touches `connectors-tab.js` + `discoverable-dropdown.js`; independent of L1-L3.
- L5 is the element-by-element sweep (item 9) — runs LAST among code-level legs so the sweep walks the post-L1-L4 state, not the pre-flight state.
- L6 is the operator-driven HAT (item 10) — operator clicks; agent guides verification steps; no Chrome MCP automation on this leg per operator decision ("for the last hat, I will do the clicking around myself").

**Chrome MCP for in-flight verification throughout L1-L5** *(operator decision)*:
- Each implementing leg uses Chrome MCP to verify changes visually after edits, not just `pytest`-style assertion runs. The agent navigates to the affected surface, takes a snapshot (a11y tree) and/or screenshot, and compares against the design-language page / MCP editor. This catches CSS-side rendering issues that pytest-only verification misses (font sizes, spacing, alignment).
- Chrome MCP usage replaces the L4-only HAT pattern from F4. The substrate cost is `make restart` per JS edit if hot-reload is not in place; the operator's local container handles this fine.
- The final L6 HAT is operator-driven (operator clicks) — agent guides verification steps but does not drive the browser.

**Intents → `.checkbox-primary` (multi-select set), NOT iOS toggle** *(operator-accepted recommendation)*:
- The 3 intent axes (Message Content / Server Members / Servers) are conceptually a "set of capabilities enabled" rather than 3 independent on/off switches. The Design Language page's `fields-section.js:30-43` Multi-select example is the precedent; reuse it directly. iOS-toggle `tool-enable-switch` is reserved for single-boolean cases (Auto-relay below).

**Auto-relay → `tool-enable-switch` (iOS toggle)** *(operator-accepted recommendation)*:
- Single boolean: on/off. The MCP editor's `Allow network access` at `mcp-server-editor.js:531-540` is the exact analog (iOS toggle inside a 2-column field-row, label left, toggle right). Reuse the same shape.

**Type-dropdown placeholder fix — hide post-selection** *(operator-accepted recommendation)*:
- The `<option value="" disabled>Select a connector type</option>` at `connector-account-editor.js:623` currently always renders inside the dropdown list, browser-default-muted. Fix: when a real type is selected, omit the placeholder option from the rendered list entirely. The closed-state combobox keeps "Select…" as initial placeholder text via a different mechanism (use `aria-placeholder` on the combobox OR continue with disabled-selected pattern but flag `hidden` so the option doesn't appear when re-opened).
- Operator gets a crisp dropdown showing only real types after selection. Browser-default-muted placeholder stays in the closed-state display until first selection, but never appears as a re-selectable option in the open list.

**Move runtime-config from General → Access and Routing; tab order** *(operator decision)*:
- New tab semantics: **General = WHAT the bot is** (Name / Type / Bot Token / Pairing / System Prompt Directive / Attached Agents) vs **Access and Routing = HOW it behaves at runtime** (Lifecycle / Intents / Guilds / Presence / Advanced kv-table / Allowlist / Routing Rules).
- New Access-and-Routing tab order: **Lifecycle → Runtime Config (Intents/Guilds/Presence/Advanced) → Allowlist → Routing Rules**. Lifecycle stays at top (governs connection mechanics — pool TTL, continuation window, auto-relay); Runtime Config sits next (what events the bot receives + which servers it scopes to); then access surfaces (allowlist + routing rules).
- Bot Token stays on General (it's "this is the bot" — identity + credential). Intents/Guilds are access concerns (what the bot RECEIVES and which servers it CAN SEE).

**MCP-mirror placement of Test Connection + Invite — fold into Connection section as footer-row** *(operator decision)*:
- MCP editor places `Refresh connection` button + LED + last-updated text INSIDE the `<div class="editor-section">Connection</div>` as a footer-row (`mcp-server-editor.js:472-501`). Connector editor currently has Test Connection + Invite as separate `editor-section` blocks 5+ sections later.
- Fix: move Test Connection button + LED + Invite section content into the Connection section as a footer-row, matching `mcp-test-row` + `mcp-connection-actions` pattern. Removes the separate `// TEST CONNECTION` and `// INVITE` section headers; the test result LED + invite URL hug the Connection-defining fields above them.
- Trade-off: Invite is no longer a standalone-section navigation target. Acceptable per operator decision (the MCP editor has no standalone "Connection result" section either; the LED + last-updated text IS the result presentation).

**Labels + info-icon tooltips — match MCP-editor pattern** *(operator decision)*:
- Most `<small class="form-hint">` verbose help-text in the connector form (Discord intents fieldset, Guilds row, Presence row, Auto-relay section) replaces with `.field-info-icon` tooltips next to the label.
- Label text rewrites for human-friendliness: drop technical jargon ("Discord gateway intents", "Comma-separated Discord guild IDs (digit-only)", "send_to_platform_channel", etc.). Operator-friendly versions land in L3 with the moved sections.
- Where help-text genuinely belongs below a control (multi-line operator guidance that doesn't fit a tooltip), keep `<small class="form-hint">` but shorten significantly and use human-friendly copy.

**Cave Man Bot Peers axis containment + empty-chips hide** *(operator decision)*:
- Item 6 (no visual scoping for per-axis body): add styling so the per-axis body visually self-contains. Likely a CSS-only fix — border-left or padding-left + background tint on `.connector-acl-axis-body` so the expanded body reads as "this is the Peers editor for this account" rather than "free-floating dropdown spans the tile."
- Item 7 (empty Selected entries blank box): in `discoverable-dropdown.js:_renderChips`, toggle the `hidden` attribute on `.discoverable-dropdown-chips` based on `state.currentValues.length`. Hide when empty; show when ≥1 chip. Preserves test-id surface; no behavioral change.

**Sweep leg output — new artifact at flight directory root** *(operator decision)*:
- Path: `missions/11-discord-connector-depth/flights/05-connector-ux-cleanup/sweep-coverage.md`.
- Shape: element-by-element table mapping each visible element on connector editor + agent-Connectors-tab to its canonical primitive (design-language page OR MCP editor), with a deferral list at the bottom for elements whose visual treatment needs a primitive that does NOT yet exist.
- At F5 debrief, deferrals roll into a future-UX-mission scope proposal. NOT a substitute for the F5 debrief itself; the sweep is a coverage map, not a retrospective.

**Touched-surface UX-debt folding discipline** *(F4-L1-codified convention)*:
- The L1-codified `touched-surface-ux-debt-folding` convention (agents.md Project-wide) applies: any prior-debrief UX-debt item against the same source file the F5 leg touches gets folded in, OR explicitly left with reason. F4 debrief's "Routine-maintenance candidates" list (C3 AIAT, chronic UI tests, `_xxxValues` getter unification, axis-vocabulary lift, `_RegistryEntry.account_type=""` removal) is explicitly OUT of scope per operator decision — these are routine-maintenance candidates, NOT UX-debt against the surfaces F5 touches.
- Sweep leg L5 produces the n=2 application of `cross-flight-ux-debt-reconciliation` discipline (F4 was n=1).

### Prerequisites

- [ ] F4 is `completed` (verified: status updated 2026-05-23; commits `4973384` + `216a2ad` + `e345947`; PR #72 open).
- [ ] Canonical CSS classes exist:
  - `.field-input` at `the_one/interfaces/web/static/css/components.css:142`
  - `.field-select` at `components.css:184`
  - `.field-info-icon` at `components.css:226`
  - `.checkbox-primary` at `components.css:252`
  - `.tool-enable-switch` at `admin.css:197`
- [ ] MCP editor source (`the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js`) is the reference; no expected changes to it during this flight.
- [ ] Design Language page modules (`the_one/interfaces/web/static/js/areas/admin/design-language/fields-section.js` etc.) are the primitive catalog; no expected changes to them during this flight.
- [ ] Chrome MCP available throughout the flight for in-flight visual verification.
- [ ] Local `the-one` container running at `http://localhost:8484/` (operator's existing setup; verified post-F4 HAT).

### Pre-Flight Checklist

- [ ] All open questions resolved (recon: 8 items confirmed-live; interview: 6 design decisions locked at Phase 4 — locked above)
- [ ] Design decisions documented (above)
- [ ] Prerequisites verified
- [ ] Validation approach defined (per-leg ACs + in-flight Chrome MCP visual verification + L6 operator-driven HAT)
- [ ] Legs defined (below; planned one-at-a-time per Flight Control convention but scoped here)

---

## In-Flight

### Technical Approach

**Primitives-first then section-shape, with Chrome MCP verification throughout.** L1 re-classes the existing markup to use canonical primitives (`.field-input`, `.field-select`, `.checkbox-primary`, `.field-info-icon`, `tool-enable-switch`) across the typed Discord form + the new-connector page's Auto-relay + Type-dropdown placeholder fix. L2 folds Test Connection + Invite into the Connection section as a footer-row mirroring MCP editor. L3 splits `renderConnectionFields` into a CONNECTION renderer (Name/Type/Token) + a RUNTIME-CONFIG renderer (Intents/Guilds/Presence/Advanced) and re-mounts the runtime-config block on the Access-and-Routing tab; concurrent with the move, the labels + help-text get rewritten for human-friendliness with info-icon tooltips replacing most `<small class="form-hint">` text. L4 cleans up the Cave Man Bot Connectors tab — adds visual containment for the per-axis body and hides the empty Selected-entries container in the dropdown. L5 sweeps the touched surfaces element-by-element and produces the coverage report. L6 operator-driven HAT.

**Sequence rationale**: L1 (primitives) → L2 (section move within General) → L3 (cross-tab section move + labels) → L4 (independent Connectors-tab fixes) → L5 (sweep) → L6 (HAT). L4 could parallelize with L1-L3 (different files) but sequential preserves clean per-leg verification.

**Per-leg LOC budget**: L1 ~80-120 LOC; L2 ~40-60 LOC; L3 ~150-200 LOC; L4 ~50-80 LOC + minor CSS; L5 ~30 LOC source + coverage report artifact; L6 0 LOC. Total source delta ~350-500 LOC across `connector-form-discord.js`, `connector-account-editor.js`, `connectors-tab.js`, `discoverable-dropdown.js`, plus minor CSS additions to `studio.css`.

### Checkpoints

- [x] L1 — `connector-form-discord.js` renders Intents as `.checkbox-primary` multi-select; Guilds as `.field-input`; Presence type as `.field-input.field-select`; Advanced disclosure preserves shape but visually matches MCP's disclosure pattern. `connector-account-editor.js` Auto-relay checkbox becomes `tool-enable-switch`. Type-dropdown placeholder option is suppressed from the list when a real type is selected. Chrome MCP visual verification confirms each.
- [x] L2 — `connector-account-editor.js` section ordering: Connection section grows a footer-row containing Test Connection button + LED + Invite URL block, mirroring MCP's `mcp-test-row`. Separate `// TEST CONNECTION` and `// INVITE` section headers are removed from the General-tab mount sequence. Chrome MCP confirms placement.
- [x] L3 — `renderConnectionFields` in `connector-form-discord.js` is split into two: Connection (Name/Type/Token — actually these are in `connector-account-editor.js`; the typed-form's contribution to Connection becomes empty in the Discord case since Intents/Guilds/Presence move out) + Runtime Config (Intents/Guilds/Presence/Advanced). `connector-account-editor.js` Access-and-Routing tab mounts the Runtime Config block between Lifecycle and Allowlist. Labels rewritten for human-friendliness; verbose `<small class="form-hint">` text replaced with `.field-info-icon` tooltips. Chrome MCP confirms tab semantics + label rendering.
- [x] L4 — `connectors-tab.js` per-axis body gets a CSS class for visual containment (border-left/padding/background tint); `discoverable-dropdown.js:_renderChips` toggles `hidden` on `.discoverable-dropdown-chips` based on `currentValues.length`. Chrome MCP confirms both visual contracts.
- [x] L5 — `missions/11-discord-connector-depth/flights/05-connector-ux-cleanup/sweep-coverage.md` exists with element-by-element table covering connector editor (both new and edit modes) + agent-Connectors-tab; deferral list at the bottom enumerates any element whose visual treatment needs a future-UX-mission primitive. Any small inline-style cleanups discovered during the sweep land in this leg's commit.
- [x] L6 — operator-driven HAT iterated through 8 rounds; substantial inline fixes folded (Type-placeholder, Lifecycle relabel/reorder, runtime-config repositioning, intent label rewrites, allowlist 3-column refactor, tab section reorg + descriptions, banner Refresh + copy, invite section 3-column + icon-only buttons, directive simplification with reactive codeblock). Operator-confirmed pass.

### Adaptation Criteria

**Divert if**:
- L1 re-styling reveals that the canonical CSS classes don't render correctly inside the connector editor's existing `.editor-section` / `.field-row` container shapes (e.g., the `.checkbox-primary` styling assumes a parent shape the typed Discord form doesn't provide). Pause; reconcile with MCP-editor patterns; if a CSS change is needed, it lands inline in the leg rather than punting to a follow-up.
- L3's section move breaks routing/persistence — e.g., the typed-form's `attachStaticListeners` wiring at `connector-account-editor.js:932-933` expects the typed-form fields to be on the same tab as the connection editor; the cross-tab move requires adapting the listener attachment. Pause; rework listener wiring; do NOT skip the move.
- L4's CSS containment fix produces an undesired visual rhythm (too heavy a border, awkward padding). Iterate inline with Chrome MCP until visual rhythm reads cleanly.
- L5 sweep surfaces NEW UX issues during element-by-element review. **Fold into F5 OR escalate as Known UX Gap in F5 flight-debrief with a near-term path — NOT defer to a hypothetical-future UX mission.** Same discipline F4 established.

**Acceptable variations**:
- L1 may shard into two legs (one for connector-form-discord typed form, one for connector-account-editor Auto-relay + Type placeholder) if the touched surface diverges significantly.
- L3 may shard into two legs (one for the section move, one for labels + info icons) if the leg's LOC budget exceeds ~250 or if the section move surfaces unexpected listener-wiring complexity.
- L5 sweep may surface an element that warrants a small inline fix — fold into the L5 commit rather than deferring; document inline.
- L6 HAT may add small-tweak fixes that lead to commits — that's the leg's expected operating mode.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses.
>
> **Dependency ordering**: L1 lands before L2-L3 (they reference the new canonical classes). L2 + L3 are independent of each other (both touch `connector-account-editor.js` but different sections); L2 first because it's smaller and de-risks the section-shape work in L3. L4 is independent of L1-L3 (different files). L5 runs after L1-L4 to sweep the post-cleanup state. L6 runs last.

- [x] `re-style-connector-form-controls` — Apply canonical primitives across the typed Discord form (`connector-form-discord.js:renderConnectionFields`) and the connector-account editor's Auto-relay + Type-dropdown placeholder. Intents → `.checkbox-primary` multi-select per Design Language fields-section pattern; Guilds → `.field-input`; Presence name → `.field-input`; Presence type → `.field-input.field-select`; Advanced (kv-table) `<details>/<summary>` disclosure → match MCP editor's disclosure shape if one exists OR style accurately and note in L5 sweep. Auto-relay checkbox → `tool-enable-switch` (iOS toggle) per MCP editor's "Allow network access" pattern. Type-dropdown placeholder option → suppress from the rendered list once a real type is selected. Chrome MCP visual verification after each substantive change. ~80-120 LOC across `connector-form-discord.js` + `connector-account-editor.js`.

- [x] `mirror-mcp-test-connection-placement` — Fold `// TEST CONNECTION` button + LED + status message + `// INVITE` URL block INSIDE the `// CONNECTION` section as a footer-row, mirroring MCP editor's `mcp-test-row` at `mcp-server-editor.js:472-501`. Remove the standalone `// TEST CONNECTION` and `// INVITE` `editor-section` blocks. Preserve all data-testids and click-handler wiring. Chrome MCP verifies placement matches MCP editor's. ~40-60 LOC in `connector-account-editor.js`.

- [x] `move-runtime-config-and-relabel` — Bundle items 2 + 3. Split the typed-form rendering so Intents/Guilds/Presence/Advanced (the "runtime config" block) renders on the Access-and-Routing tab between Lifecycle and Allowlist; Connection section on the General tab keeps Name/Type/Bot Token only. Rewrite labels for human-friendliness; replace verbose `<small class="form-hint">` text with `.field-info-icon` tooltips. Adapt the `attachStaticListeners` wiring at `connector-account-editor.js:932-933` to accommodate the cross-tab field location. Chrome MCP verifies tab semantics + label rendering + that form-data collection round-trips correctly post-move. ~150-200 LOC across `connector-form-discord.js` + `connector-account-editor.js`.

- [x] `connectors-tab-axis-cleanup` — Bundle items 6 + 7. Add visual containment for the per-axis body in `connectors-tab.js:_buildAxisRow` — likely a new CSS class on `.connector-acl-axis-body` with border-left/padding/background tint so the expanded body reads as "this is the Peers editor for this account." In `discoverable-dropdown.js:_renderChips`, toggle the `hidden` attribute on `.discoverable-dropdown-chips` based on `state.currentValues.length` (hide when empty). Chrome MCP verifies both visual contracts on Cave Man Bot Connectors tab. ~50-80 LOC across `connectors-tab.js` + `discoverable-dropdown.js` + `studio.css`.

- [x] `connector-ux-sweep` — Element-by-element sweep of the touched surfaces: full connector editor (new + edit modes, both tabs) + agent-Connectors-tab. For every visible element, confirm it maps to a Design Language primitive (`field-input`, `field-select`, `checkbox-primary`, `field-info-icon`, `tool-enable-switch`, `chip`, `indicator-led`, etc.) OR an MCP-editor pattern. Reuse existing primitives where they exist; style-accurately where they don't AND note as future-UX-mission scope in the deferral list. Output: `missions/11-discord-connector-depth/flights/05-connector-ux-cleanup/sweep-coverage.md` with element→primitive table + deferral list. Any small inline-style cleanups discovered during the sweep land in this leg's commit. **NO new UI components built.** Chrome MCP drives the element enumeration. ~30 LOC source + coverage report artifact.

- [x] `uat-and-alignment` *(required HAT — operator-driven)* — Operator walked the cumulative result manually across 8 HAT rounds; agent guided verification steps. Substantial inline fixes folded across rounds 1-8 (Type-placeholder polish; Lifecycle relabel+reorder; runtime-config repositioning; intent label rewrites; allowlist 3-column refactor; tab section reorg + descriptions; banner Refresh visibility + copy; invite section 3-column + icon-only buttons; directive simplification with reactive codeblock). Mission criterion #14 partially reverted (operator-editable directive override removed per operator decision; defaults still visible in styled codeblock).

---

## Post-Flight

### Completion Checklist

- [ ] All 6 legs (L1-L6) completed
- [ ] L6 HAT walk completed with operator-confirmed pass
- [ ] Code merged on `main` (or stacked behind F4 PR #72)
- [ ] Tests passing at or above F4's 2899 baseline + F5 additions
- [ ] `sweep-coverage.md` exists with element→primitive table + deferral list
- [ ] All visible elements on touched surfaces map to a Design Language primitive OR an MCP-editor pattern (per L5 sweep verification)
- [ ] No new UI components introduced (per operator constraint)
- [ ] F5 debrief Action Items capture any future-UX-mission scope from the deferral list

### Verification

**Mechanical verification** (CI / scripted):
- Existing browser test suites continue passing (especially `test_flow_studio_connector_account_editor.py`, `test_flow_studio_connector_account_create_and_test.py`, `test_flow_studio_per_agent_overlay_dropdown.py`, `test_flow_studio_per_agent_overlay_label_resolver.py`, `test_flow_studio_connector_discoverable_dropdown.py`).
- Existing data-testid selectors continue resolving (form-control re-classing preserves IDs).
- Full suite at or above F4's 2899-pass baseline.

**Operational verification** (in-flight Chrome MCP):
- Each leg's Developer verifies visual rendering via Chrome MCP snapshot + screenshot after substantive changes.
- Verification compares against Design Language page (`#admin/design-language`) and MCP editor (`#studio/mcp-sources/{id}`).

**Operational verification** (L6 operator HAT):
- Operator walks the connector editor (new + edit modes), the agent-Connectors-tab, and any related surfaces; confirms the cumulative cleanup matches expectations.

**Methodology verification**:
- `cross-flight-ux-debt-reconciliation` discipline applied at recon (n=2 since F4 was n=1) — Recon Report classifies all 10 enumerated items.
- `touched-surface-ux-debt-folding` discipline applied during legs — any prior-debrief UX-debt against touched files gets folded OR explicitly left with reason.
- L5 sweep is the n=1 application of the element-by-element coverage discipline; may codify as a new convention at F5 debrief if a second instance materializes in F6+.
