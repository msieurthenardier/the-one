# Flight Log: Connector UX Cleanup

**Flight**: [Connector UX Cleanup](flight.md)

## Summary

Planning phase. Recon complete (all 10 enumerated items walked against current code; 8 confirmed-live + 2 process-level). Design decisions documented in `flight.md`. Awaiting `/agentic-workflow` execution.

---

## Reconnaissance Report

n=2 application of the F4-codified `cross-flight-ux-debt-reconciliation` discipline. Source artifact: interactive operator enumeration session (2026-05-23), captured during the F5 planning conversation. The operator walked the live Discord connector editor + Cave Man Bot Connectors tab through the agent's Chrome MCP and enumerated 10 UX items, using the Design Language page (`#admin/design-language`) + MCP editor (`#studio/mcp-sources/{id}`) as the canonical-primitive references.

Walk of every cited item against current code state (2026-05-23, post-F4 ship at commits `4973384` + `216a2ad` + `e345947`).

| # | Item | Classification | Evidence | Recommendation |
|---|---|---|---|---|
| R1 | Re-style General-tab form controls (Intents/Guilds/Presence/Advanced) | confirmed-live | `connector-form-discord.js:163-238` `renderConnectionFields` uses raw `<input type="checkbox">`, raw `<input type="text">`, raw `<select>`, raw `<fieldset>/<legend>`, raw `<details>/<summary>` — no `.field-input`/`.field-select`/`.checkbox-primary`/`.field-info-icon` classes | F5 L1 — re-class to canonical primitives per Design Language `fields-section.js:7-44` |
| R2 | Move Config (Intents/Guilds/Presence/Advanced) from General → Access and Routing | confirmed-live | `connector-account-editor.js:512-522` General-tab block emits `connectionHtml + credentialsHtml + pairingHtml + directiveHtml + attachedAgentsHtml + testConnectionHtml + inviteHtml + dangerZoneHtml`; `connectionHtml` includes the Discord typed-form's Intents/Guilds/Presence/Advanced; `lifecycleHtml + allowlistHtml + routingHtml` go to Access-and-Routing tab | F5 L3 — split `renderConnectionFields` into Connection (empty for Discord) + Runtime Config (mounted on Access-and-Routing tab between Lifecycle and Allowlist) |
| R3 | Labels + verbose help-text + missing info icons | confirmed-live | `<small class="form-hint">` sites at `connector-form-discord.js:189-191, 201, 221-222` (Intents help text, Guilds help text, Presence help text); similar pattern in `connector-account-editor.js` for Auto-relay, Lifecycle, etc.; no `field-info-icon` usage in connector editor (MCP editor uses it at `mcp-server-editor.js:792`) | F5 L3 — replace verbose `<small>` with `.field-info-icon` tooltips per Design Language `fields-section.js:18-24`; rewrite labels for human-friendliness |
| R4 | New-connector Type dropdown placeholder mis-styled + re-selectable | confirmed-live | `connector-account-editor.js:622-623` `<option value="" disabled>Select a connector type</option>` always renders in the dropdown list; browser default styling for `option:disabled` is muted (correctly per `components.css:219`), but the placeholder is re-selectable in the open list after a real type is picked | F5 L1 — suppress placeholder option from the rendered list when a real type is selected (omit emission OR add `hidden` attribute) |
| R5 | New connector page: Auto-relay raw checkbox + verbosity + missing info icons | confirmed-live | `connector-account-editor.js:382-388` `<input type="checkbox" id="cf-auto-relay">` with no canonical class; `connector-account-editor.js:389-392` 2-sentence `<small>` help-text with technical jargon (`send_to_platform_channel`) | F5 L1 — Auto-relay → `tool-enable-switch` (iOS toggle) per MCP editor's `Allow network access` at `mcp-server-editor.js:531-540`; F5 L3 — shorten/relabel + info-icon tooltip |
| R6 | Cave Man Bot Peers expansion fills full tile width with no containment | confirmed-live | `connectors-tab.js:_buildAxisRow` renders `.connector-acl-axis` with a `body` child (`hidden` toggled on expand) that takes parent (tile) width; no visual container scoping the per-axis editor; chip-mode body mounts the `discoverable-dropdown` which is a full-width `<div class="discoverable-dropdown">` | F5 L4 — add CSS containment for `.connector-acl-axis-body` (border-left/padding/background tint) so the expanded body visually self-contains as "this is the Peers editor for this account" |
| R7 | Empty "Selected entries" blank box | confirmed-live | `discoverable-dropdown.js:103-105` always emits `<div class="chip-list-editor discoverable-dropdown-chips" role="group" aria-label="Selected entries">`; `_renderChips` (line 122-168) empties + repopulates but never hides the container when `state.currentValues.length === 0`; container's `.chip-list-editor` minimum-height styling makes the empty container visually present | F5 L4 — toggle `hidden` attribute on `.discoverable-dropdown-chips` in `_renderChips` based on `state.currentValues.length` |
| R8 | Move // TEST CONNECTION + // INVITE up under // CONNECTION (mirror MCP) | confirmed-live | `connector-account-editor.js:512-521` current General-tab order puts Test Connection + Invite after 5 other sections; MCP editor at `mcp-server-editor.js:441-502` mounts Refresh-connection button + LED + last-updated INSIDE the `<div class="editor-section">Connection</div>` as a footer-row (`mcp-test-row`) | F5 L2 — fold Test Connection button + LED + Invite URL block into Connection section as footer-row; remove standalone `// TEST CONNECTION` and `// INVITE` editor-section blocks |
| R9 | Full UX sweep leg | n/a (process) | Process-level item; runs last among code-level legs to walk the post-L1-L4 state | F5 L5 — element-by-element coverage map; output `sweep-coverage.md` artifact at flight directory root |
| R10 | Interactive HAT (operator-driven) | n/a (process) | Process-level; final leg | F5 L6 — operator-driven HAT walks cumulative result; agent guides verification steps |

**Items classification summary**: 8 confirmed-live (R1-R8), 2 process-level (R9-R10). No drifted, no already-satisfied, no needs-human-recheck.

**Items DEFERRED out of F5 scope per F4-debrief Action Items** (per operator decision: "F4 debrief Action Items include several routine-maintenance carryovers — don't bundle them here; leave for /routine-maintenance"):
- C3 AIAT 4-test cluster (fixture issue; 5 flights deep) — routine-maintenance candidate.
- C5a/b chronic UI tests (`test_tablist_renders_with_three_tabs`, `test_studio_section_round_trip_preserves_agent_selection`) — routine-maintenance candidate.
- `_xxxValues` getter pattern unification (F3 debrief carryover) — routine-maintenance candidate.
- Axis vocabulary constant lift to `App.studio.connectorAxes` (F3 carryover) — routine-maintenance candidate.
- `_RegistryEntry.account_type=""` backwards-compat default removal (F3 carryover) — routine-maintenance candidate.
- Plugin-author guide for connectors (F3 + F4 debrief carryover) — documentation; out of F5 scope (UX cleanup, not docs).
- F4 debrief criterion-coverage row #2 vocabulary gap — methodology; not a UX surface, sits outside F5.

**Crew interview outcomes** (2026-05-23):
- Source-of-style references: Design Language page (catalog) + MCP editor (working reference). NO new UI components built in F5.
- Leg ordering: L1 primitives → L2 Test-Connection fold → L3 Move Config + Labels → L4 Connectors-tab cleanup → L5 sweep → L6 operator-HAT.
- Chrome MCP for in-flight visual verification throughout L1-L5; L6 operator-driven (operator clicks).
- Intents → `.checkbox-primary` multi-select (set semantics); Auto-relay → `tool-enable-switch` (single boolean).
- Type-placeholder fix: suppress from rendered list post-selection.
- Move Config: new Access-and-Routing tab order is Lifecycle → Runtime Config → Allowlist → Routing Rules. General becomes WHAT (name/type/token/pairing/directive/attached).
- Test Connection + Invite fold into Connection section footer-row, mirroring MCP `mcp-test-row`.
- Sweep output: `missions/11-discord-connector-depth/flights/05-connector-ux-cleanup/sweep-coverage.md`.

---

## Leg Progress

*(empty — to be populated as legs are planned + executed)*

---

## Decisions

Runtime decisions not in original plan.

*(empty — to be populated during execution)*

---

## Deviations

Departures from planned approach.

*(empty)*

---

## Anomalies

Unexpected issues encountered.

*(empty)*

---

## Session Notes

### 2026-05-23 — Planning Session

- F4 just completed (PR #72 open; flight artifact status `completed`; debrief at `flight-debrief.md`).
- Interactive operator enumeration session compiled 10 UX items; operator explicitly directed "do not re-litigate scope" at /flight invocation.
- Phase 1b recon walked all 8 code-level items against current code: 8/8 confirmed-live, no drift, no surprises.
- Phase 4 crew interview resolved 6 design decisions documented in `flight.md`.
- Chrome MCP for in-flight verification is the methodology improvement over F4's HAT-only Chrome MCP usage.
- F5 status: `planning` → `ready` upon operator approval; awaiting `/agentic-workflow` execution.

### 2026-05-23 — F5 mission-flight-list update

- F5 = Connector UX Cleanup (this flight) — inserted ahead of the originally-planned peer-name attribution flight, which shifts to F6.
- Operator was explicit at planning: "im not concerned about numbering, do it however you wish." F5 numbering is the natural extension of the F4 precedent (F4 was inserted ahead of the originally-planned peer-name flight to consume F3-debrief UX hotfixes; F5 continues the pattern with a broader cleanup).
- Mission.md flight-list update: mark `Flight 5: Peer-name attribution` as Flight 6, shift subsequent flights by +1; insert F5 = Connector UX Cleanup. (Pending update — to be done as part of `/agentic-workflow` kickoff.)
