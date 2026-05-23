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

### L1 — re-style-connector-form-controls (2026-05-23)

- Status: `completed` (batched F5 commit at flight end per agentic-workflow protocol).
- Changes:
  - `the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js` — Intent `<input type="checkbox">` markup now carries `class="checkbox-primary"` (fieldset shape preserved). Guilds input + Presence name input gained `class="field-input"`. Presence type select gained `class="field-input field-select"`. Advanced (kv-table) `<details>/<summary>` unchanged (already matches MCP single-class-on-`<details>` precedent).
  - `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — Auto-relay row rewritten to MCP sibling-label pattern: outer `<label for="cf-auto-relay">` + inner `<label class="tool-enable-switch">` are SIBLINGS inside `<div class="field-row admin-pf-row cf-auto-relay-row">`. Inner toggle-label wraps `<input type="checkbox" class="field-input" aria-label="Auto-relay peer replies to platform">` + `<span class="tool-enable-switch-track" aria-hidden="true">`. Type-dropdown placeholder option suppressed from rendered list when `createType !== ''` (emit only when `createType === ''`). Explicit Auto-relay change-handler at lines 943-945 + its M10-F8-L11-Fix-#4 comment removed — now redundant with `attachStaticListeners` once the input carries `.field-input`.
  - `the_one/interfaces/web/static/css/admin.css` — added one ~3 LOC `.area-studio .field-row.cf-auto-relay-row .tool-enable-switch { position: relative; bottom: auto; right: auto; }` rule next to the `tools-editor-enabled-row` + `mf-sandbox-network-row` precedents at lines 278-281.
- Verification:
  - Grep checks pass: `checkbox-primary` emitted in Intent loop (3 runtime hits per 1 source line); 3 `field-input` hits in connector-form-discord.js; 1 `field-select` hit; 2 `tool-enable-switch` hits in connector-account-editor.js; placeholder emission shows the new guard form.
  - Chrome MCP visual verification (hard-reload to bust cache):
    - `#studio/connectors/{discord}` General tab: Intent checkboxes have `class="checkbox-primary"`; Guilds + Presence inputs have `class="field-input"`; Presence type select has `class="field-input field-select"`. Form renders with dark-theme styling.
    - `#studio/connectors/new`: Auto-relay row renders as iOS toggle inline next to label (NOT pinned to bottom-right of nearest positioned ancestor); single click flips `checked` state from `true` → `false` (defensive AC met — sibling-label markup avoids the nested-label cancel bug). Type dropdown initially shows "Select a connector type" placeholder; after picking `discord`, dropdown options list contains ONLY Discord (placeholder suppressed).
  - Browser tests: `docker exec the-one pytest tests/browser/test_flow_studio_connector_account_editor.py tests/browser/test_flow_studio_connector_account_create_and_test.py tests/browser/test_flow_studio_connector_discord_form.py tests/browser/test_flow_studio_connector_discord_vocabulary.py -m browser -x --timeout 60 -v` → 39 passed in 58.59s.
- Adaptation notes: none — cycle-1 design review revisions (sibling-label markup, fieldset preservation, CSS unpin override, explicit-handler removal) all applied at the leg-design tightening; implementation matched the spec one-shot with no in-flight rework.

### L2 — mirror-mcp-test-connection-placement (2026-05-23)

- Status: `completed` (batched F5 commit at flight end per agentic-workflow protocol).
- Changes:
  - `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — new file-scope helper `renderTestConnectionRow()` returns the Test Connection field-row + status banner + details-wrap as WRAPPER-LESS content (no `<div class="editor-section">`, no `<div class="section-title">`), placed alongside the existing `renderPairingSection`/`renderAllowlistSection`/`renderRoutingRulesSection`/`renderAttachedAgentsSection` helpers. Connection section's `<div class="editor-section">` (now also carrying `data-testid="connector-connection-section"` for future ancestry asserts) was extended so that in edit-mode it emits `renderConnectionFields` + `renderTestConnectionRow()` + the registry-mediated invite content INSIDE the same section. Standalone `var testConnectionHtml = '';` block (formerly at the post-attached-agents site) and standalone `var inviteHtml = '';` block REMOVED — replaced with one-line breadcrumb comments pointing at the new home inside the Connection section. General-tab mount sequence shed `testConnectionHtml + inviteHtml` lines; new sequence: `connectionHtml + credentialsHtml + pairingHtml + directiveHtml + attachedAgentsHtml + dangerZoneHtml`. File-header doc-comment at lines 5-11 updated to reflect the new shape (Connection section hosts Test Connection footer-row + Invite block in edit mode; standalone Test Connection section dropped from the section catalogue).
  - `the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js:renderInviteSection` — rewritten to return wrapper-less content: `<div class="connector-invite-block" data-testid="connector-invite-section">...</div>`. Removed the outer `<section class="editor-section connector-invite-section">` wrapper and the `<div class="section-title">Invite</div>`. All inner data-testids preserved byte-identical (`connector-invite-hint`, `connector-invite-url-wrap`, `connector-invite-url`, `connector-invite-copy-btn`, `connector-invite-recompute-btn`); the `connector-invite-section` testid moved from the dropped `<section>` onto the new `<div class="connector-invite-block">` so DOM-by-testid lookups (used at `connector-form-discord.js:701` and in the browser test suite) keep resolving.
  - `the_one/interfaces/web/static/css/studio.css:126` — added `.connector-test-row` to the existing `.area-studio .mcp-test-row` selector list (resulting rule: `.area-studio .mcp-test-row, .area-studio .connector-test-row { margin-top: 8px; }`) so the connector editor's Test Connection footer-row shares MCP's `mcp-test-row` margin. One-line MCP-parity comment added above the rule.
  - `the_one/interfaces/web/static/js/areas/studio/connector-form-registry.js` — docstrings updated at two sites (`renderInviteSection` enumeration in the Optional Hooks header and the M11 F1 L5 paragraph inside `_validateEntry`) to reflect the new wrapper-less embed semantics. Registry contract code unchanged (the hook still returns an HTML string; only the returned HTML shape changes).
  - `the_one/agents.md` — Connector subsystem section `optional-registry-entry-hook` citation for `renderInviteSection` updated to describe the wrapper-less embed inside the Connection section per F5 L2's MCP-parity refactor.
- Verification:
  - Grep checks pass: `field-row admin-pf-row connector-test-row` returns 1 hit in `connector-account-editor.js` (the new helper); `editor-section connector-test-section` returns 0 hits; `editor-section connector-invite-section` returns 0 hits in `connector-form-discord.js`; `connector-invite-block` returns 1 hit in `connector-form-discord.js` (plus the explanatory comment); `data-testid="connector-test-connection-btn"` + `data-testid="connector-invite-section"` testids preserved across both files; `.connector-test-row` + `.mcp-test-row` co-occur in the same CSS selector at `studio.css:130-131`.
  - Chrome MCP visual verification (hard-reload to bust cache):
    - `#studio/connectors/58f1fe5a833f` (Discord Constellation) General tab: CONNECTION section now contains Name + Type + Intents + Guilds + Presence + Advanced disclosure + Test connection button + LED ("Not tested") + invite hint ("Run Test Connection first..."). CREDENTIALS, PAIRING, SYSTEM PROMPT DIRECTIVE, ATTACHED AGENTS, DANGER ZONE follow as separate sections. No standalone "// TEST CONNECTION" or "// INVITE" section headers.
    - Click on Test connection button: LED transitions Not tested → OK; status banner "Discord probe ok" appears; invite URL `https://discord.com/oauth2/authorize?client_id=...&permissions=2147552256&scope=bot+applications.commands` populates inside the Connection section with Copy + Recompute buttons. All click wiring + application-id cache push contracts preserved.
  - Browser tests: `docker exec the-one pytest tests/browser/test_flow_studio_connector_account_editor.py tests/browser/test_connector_test_connection_button.py tests/browser/test_flow_studio_connector_invite_section.py tests/browser/test_flow_studio_connector_account_create_and_test.py -m browser -x --timeout 60 -v` → 34 passed in 51.77s. Includes the test-connection button, invite section pre/post-probe behavior, stub-type no-invite path, copy-button clipboard, and create-and-test combined-action flows.
- Adaptation notes: none — cycle-1 design review tightening (line-citation drift repairs; registry + agents.md doc-comment additions; file-header comment update; helper placement pinned; CSS file pinned; optional ancestry-testid suggestion absorbed) was sufficient; implementation matched the spec one-shot with no in-flight rework.

### L3 — move-runtime-config-and-relabel (2026-05-23)

- Status: `completed` (batched F5 commit at flight end per agentic-workflow protocol).
- Changes:
  - `the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js` — old `renderConnectionFields` body extracted into a new internal helper `_renderRuntimeConfigBody(account)` that holds the Intents fieldset + Servers (was: Guilds) row + Presence row + Advanced kv-table disclosure. `renderConnectionFields(account, isCreate)` rewritten as a conditional: returns `_renderRuntimeConfigBody(account)` when `isCreate === true` (create-mode flat layout — runtime-config renders in Connection section) and `''` when `isCreate === false` (edit-mode tabbed layout — runtime-config moves to Access-and-Routing tab via the new hook). New top-level `renderRuntimeConfigFields(account)` delegates to the shared helper; registered as the 6th optional hook in the registry-entry export object. Verbose `<small class="form-hint">` blocks for Intents/Guilds/Presence REMOVED; each label gains a `<button type="button" class="field-info-icon" title="..." aria-describedby="...">` info-icon + visually-hidden help-text sibling per `mcp-server-editor.js:790-795` production pattern. Guilds label rewritten "Guilds" → "Servers" per Discord-native vocabulary (the existing M11 F1 substitution surface). All `data-testid`s, `data-field`s, and ids preserved byte-identical so the typed-form wireup + collect/snapshot paths continue resolving across tabs.
  - `the_one/interfaces/web/static/js/areas/studio/connector-form-registry.js` — `optionalFns` array grows `'renderRuntimeConfigFields'` (6th entry). Validation comment block + the top-of-file Optional Hooks header doc-comment both document the new hook's contract: wrapper-less HTML mounted on the Access-and-Routing tab between Lifecycle and Allowlist, substrate owns the section wrapper + section-title "Runtime Config".
  - `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — file-header doc-comment rewritten to enumerate both tabs by section (General = WHAT the bot is: Connection/Credentials/Pairing/Directive/AttachedAgents/DangerZone; Access and Routing = HOW it behaves at runtime: Lifecycle/RuntimeConfig/Allowlist/RoutingRules), with note on create-mode flat layout and how the runtime-config block renders inside Connection in create-mode via the shared helper. New `runtimeConfigHtml` build between `lifecycleHtml` and `allowlistHtml` invokes `registry.get(type).renderRuntimeConfigFields(account)` and wraps the returned content in `<div class="editor-section" data-testid="connector-account-runtime-config-section"><div class="section-title">Runtime Config</div>...</div>`. Access-and-Routing tab mount sequence becomes `lifecycleHtml + runtimeConfigHtml + allowlistHtml + routingHtml`. Lifecycle section's three `<small class="form-hint">` blocks (Pool idle timeout, Chat-session continuation, Auto-relay) REPLACED with `.field-info-icon` button + visually-hidden sibling using the same production pattern; the existing testids (`connector-account-{idle,continuation,auto-relay}-hint`) migrated from the dropped `<small>` elements onto the new info-icon buttons so existing tests resolve against the new affordance (tooltip text now lives in the button's `title=` attribute). Auto-relay row's visible label + `aria-label` both rewritten "Auto-relay peer replies to platform" → "Auto-reply to platform messages" per the F5 L3 friendliness pass; persisted `config.auto_relay_platform_replies` key intentionally unchanged.
  - `the_one/agents.md` — Connector subsystem `optional-registry-entry-hook` citation list extended with the F5 L3 entry for `renderRuntimeConfigFields` (matches the F1 L5 `renderInviteSection` precedent: WRAPPER-LESS HTML, substrate owns the section wrapper + section-title; new for L3 — single-source-of-truth via `_renderRuntimeConfigBody` shared with `renderConnectionFields(account, isCreate=true)` for create-mode flat layout). `optionalFns` array enumeration updated to include the new hook name.
  - `tests/browser/test_flow_studio_connector_discord_form.py` — new local helper `_activate_access_and_routing_tab(page)` mirroring `account_editor.py:89` (clicks the tab + waits for `connector-account-runtime-config-section` to be visible). Six edit-mode tests (`test_edit_mode_renders_typed_fields_with_persisted_intents`, `test_intent_toggle_re_enables_save`, `test_intent_toggle_save_emits_typed_payload`, `test_guilds_add_saves`, `test_presence_name_and_type_save`, `test_advanced_disclosure_hides_reserved_keys`) gain a tab-click before their first interaction with `discord-intent-*`/`discord-guilds-list`/`discord-presence-*`/`discord-advanced-kv-disclosure` testids. `test_edit_mode_renders_typed_fields_with_persisted_intents` also clicks back to the General tab to verify the Bot Token input still lives in the Credentials section there.
  - `tests/browser/test_flow_studio_connector_account_editor.py` — `test_edit_session_continuation_round_trip` updated: the `connector-account-continuation-hint` testid no longer resolves to a `<small>` carrying the text content but to a `<button class="field-info-icon">` whose `title=` attribute holds the text. The assertion was rewritten from `to_contain_text(...)` to `to_have_attribute("title", ...)` so the test exercises the migrated tooltip-text affordance.
- Verification:
  - Grep checks pass: `renderRuntimeConfigFields` → 11 hits (def + registry export + registry validation + editor consume + agents.md + docstrings); `<button class="field-info-icon">` → 6 hits in connector-form-discord.js + connector-account-editor.js (3 runtime-config + 3 lifecycle/auto-relay); `class="form-hint"` in connector-form-discord.js runtime-config block → 0 hits (the 3 remaining hits are the deferred Bot Token credentials hint + the directive section hint + a comment reference, all outside L3 scope); `Auto-relay peer replies to platform` → 0 hits (old label fully removed including from comments); `Auto-reply to platform messages` → 3 hits (visible label + aria-label + comment); `section-title.*Runtime Config` → 2 hits (the actual section-title line + the doc-comment reference). All match the leg's Verification Steps grep contracts.
  - Chrome MCP visual verification (hard-reload to bust cache):
    - `#studio/connectors/58f1fe5a833f` (Discord Constellation) General tab: Connection section shows Name + Type + Test connection + Invite hint ONLY. No Intents/Servers/Presence/Advanced anywhere on the General tab. Credentials/Pairing/SystemPromptDirective/AttachedAgents/DangerZone follow as separate sections (unchanged from L2 baseline). Access and Routing tab: shows the new section order Lifecycle → Runtime Config → Account-Scope Allowlist → Routing Rules. The Runtime Config section renders Intents (with info-icon "Discord event types the bot receives. All on is the safe default."), Servers row (label = "Servers", info-icon "Comma-separated server IDs. Leave blank to allow all servers the bot is in."), Presence row (info-icon "What the bot shows as its activity status. Blank for default."), Advanced (kv-table) disclosure. Lifecycle section also shows info-icons for Pool idle timeout / Chat-session continuation / Auto-reply. Auto-reply label reads "Auto-reply to platform messages" with iOS toggle (L1 contract preserved).
    - `#studio/connectors/new` create-mode after picking Discord type: Connection section renders Intents/Servers/Presence/Advanced inline (create-mode flat-layout preservation per the conditional `renderConnectionFields(account, isCreate=true)` path).
    - Persistence round-trip (programmatic via fetch API on the live page): toggled Message Content intent off, set Presence name to "test-presence-l3", toggled Auto-reply off; PUT through Save; re-fetched account state → `config.intents.message_content === false`, `config.presence.name === "test-presence-l3"`, `config.auto_relay_platform_replies === false`. Reload → re-mount → Access and Routing tab → confirmed all three values restored (intent unchecked, presence name populated, auto-reply toggle off). Original state restored via API PUT before exit.
  - Browser tests: `docker exec the-one pytest tests/browser/test_flow_studio_connector_account_editor.py tests/browser/test_flow_studio_connector_discord_form.py tests/browser/test_flow_studio_connector_discord_vocabulary.py tests/browser/test_flow_studio_connector_account_create_and_test.py tests/browser/test_flow_studio_connector_directive_section.py -m browser -x --timeout 60 -v` → 52 passed in 76.67s.
- Adaptation notes: none — cycle-1 design review tightening (HIGH: create-mode preservation via shared helper + conditional; MED: 6 edit-mode tests enumerated with tab-click insertions; MED: info-icon body convention pinned to production pattern with `App.icon('info')` + visually-hidden sibling; MED: Auto-relay aria-label rewrite added) was sufficient; implementation matched the spec one-shot with no in-flight rework. Additional touched-test discovered at implementation time: `test_edit_session_continuation_round_trip` asserts `to_contain_text` against the `connector-account-continuation-hint` testid; the testid migrated to the info-icon button so the assertion was updated to `to_have_attribute("title", ...)`. This is a touched-test-update consistent with the leg's "existing data-testids on `<small>` hints being removed" Edge Case — testid migrated to preserve test resolvability without renaming.

### L4 — connectors-tab-axis-cleanup (2026-05-23)

- Status: `completed` (batched F5 commit at flight end per agentic-workflow protocol).
- Changes:
  - `the_one/interfaces/web/static/js/areas/studio/discoverable-dropdown.js` — `_renderChips(state)` extended with a hidden-when-empty toggle (item 7): after the existing `chipsEl.innerHTML = ''` clear, when `state.currentValues` is empty/missing the chips container gets `setAttribute('hidden', '')` and the function returns early; otherwise `removeAttribute('hidden')` is called before the chip-rendering loop. Inline multi-line comment cites M11 F5 L4 item 7 and explicitly documents the cycle-1 specificity catch (the JS `hidden` attribute alone is insufficient because `.area-studio .chip-list-editor`'s `display: flex` at 0,0,2,0 overrides the user-agent `[hidden]` rule at 0,0,1,0 — the companion CSS override in studio.css at 0,0,3,0 is REQUIRED). Existing chip-rendering loop, status-div behavior, data-testids, ARIA labels, and the `_findEntityById` unknown-id fallback are byte-identical preserved.
  - `the_one/interfaces/web/static/css/studio.css` — TWO targeted edits per the leg spec:
    - EXTENDED the existing `.area-studio .connector-acl-axis-body` rule at line 1104 (was `margin-top: 8px;` only) with containment properties (item 6): `border-left: 2px solid var(--border); padding: 8px 0 8px 12px; background: var(--surface-elevated); border-radius: var(--panel-radius-sm);`. Preserved the existing `margin-top: 8px` (operator-deliberate spacing). Multi-line comment above the rule cites F5 L4 item 6 and explains the `--surface-elevated` choice (tonal step-up from the tile's `--surface`).
    - ADDED a new `.area-studio .discoverable-dropdown-chips[hidden] { display: none; }` override rule near the existing `.discoverable-dropdown-chips` rule (around line 1306). Multi-line comment cites F5 L4 item 7 and the specificity-override rationale (0,0,3,0 outranks `.area-studio .chip-list-editor`'s 0,0,2,0). Both rules use Design Language tokens (`--border`, `--surface-elevated`, `--panel-radius-sm`).
  - `connectors-tab.js` — no source change (item 6 is CSS-only; the `<div class="connector-acl-axis-body">` already exists at `_buildAxisRow` line 295).
- Verification:
  - Grep checks pass: `currentValues.length|hidden.*chipsEl|chipsEl.*hidden` in discoverable-dropdown.js → 5 hits (the new length check + setAttribute + removeAttribute + the existing currentValues iteration in `_renderChips` + the iteration in `_renderMenu`); `.connector-acl-axis-body` in studio.css → 1 hit (the existing rule at line 1110, now extended in-place — NOT a duplicate); `discoverable-dropdown-chips\[hidden\]` in studio.css → 1 hit (the new override rule at line 1328).
  - Chrome MCP visual verification (hard-reload to bust cache, `#studio/agents/Cave%20Man%20Bot/connectors`):
    - Discord Constellation Peers axis expanded (chip-mode, empty allowlist): contained body renders with `--surface-elevated` background, 2px solid `--border` left border, 8px/12px padding, and `--panel-radius-sm` corner — the body reads as the Peers editor for this account rather than as a free-floating dropdown. The "Add entry…" input + Refresh button + status text ("Run Test Connection first to populate the bot's discoverable view.") sit inside the contained body. The Selected entries chip container is correctly hidden — no blank box.
    - Discord Constellation Channels axis expanded (checkbox-mode, one persisted chip `1506831630923333722`): same containment applies uniformly. The checkbox row is visible inside the contained body. Did NOT mutate the chip — operator's downstream HAT dependency preserved.
    - Cycle-1 computed-style proof via `mcp__chrome-devtools__evaluate_script`:
      - Empty Peers chip container: `getComputedStyle(...).display === "none"` AND `hasAttribute('hidden') === true` AND `childCount === 0`.
      - After programmatically removing the `hidden` attribute (simulating the post-add-chip render): `display === "flex"` (chip-list-editor's flex layout restored).
      - After re-adding `hidden` (simulating the post-remove-last-chip render): `display === "none"` (override re-engaged).
    - This proves the CSS specificity override actually defeats `.area-studio .chip-list-editor`'s `display: flex` and the hide/show is dynamic, not a snapshot artifact. Stub HAT Account expansion confirmed both Peers and Channels axes are in checkbox-mode (no chip-mode dropdown surface available there for an interactive add/remove round-trip), so the dynamic toggle was verified via the JS-driven attribute-toggle proof above instead of operator click.
    - Containment computed-style readback: `borderLeftWidth === "2px"`, `borderLeftColor === "rgb(42, 42, 42)"`, `padding === "8px 0px 8px 12px"`, `backgroundColor === "rgb(51, 51, 51)"`, `borderRadius === "4px"`, `marginTop === "8px"` — every property landed exactly as specified, margin-top preserved.
  - Browser tests: `docker exec the-one pytest tests/browser/test_flow_studio_per_agent_overlay_dropdown.py tests/browser/test_flow_studio_per_agent_overlay_label_resolver.py tests/browser/test_flow_studio_connector_allowlist_dropdown.py tests/browser/test_flow_studio_connector_routing_dropdown.py tests/browser/test_flow_studio_connector_discoverable_dropdown.py -m browser -x --timeout 60 -v` → 25 passed in 36.63s. No regressions on the dropdown surfaces; no test asserted `to_be_visible()` on an empty chips container so the hide-when-empty contract does not break any existing test.
- Adaptation notes: none — the leg's cycle-1 design tightening (HIGH: companion CSS override required to defeat `.area-studio .chip-list-editor` `display: flex` specificity; HIGH: extend existing `.connector-acl-axis-body` rule at line 1104 rather than add a duplicate; MED: `--surface-elevated` over `--surface` for tonal differentiation; MED: do NOT mutate Discord Constellation chip state; MED: Stub HAT Account as add/remove playground; MED: computed-style check via `evaluate_script` is the cycle-1 verification gate) was sufficient. Implementation matched the spec one-shot with no in-flight rework. Operator-safety note: the Stub HAT Account paths turned out to be checkbox-mode (no chip-list dropdown UI), so the add/remove interactive round-trip was satisfied via JS-driven attribute toggle on the Discord Peers container instead — the cycle-1 dynamic-toggle proof is equivalent (CSS specificity is global, the attribute-driven hide/show works the same regardless of which axis triggers `_renderChips`). The positive side-effect noted in the leg's Edge Cases (cold-pool empty state in the pre-probe-404 path + ok path no longer renders the blank box) is in effect — `_renderChips` is the single chokepoint and all callers now flow through the hide-when-empty branch. Worth surfacing to L5 sweep as a "side effect to verify reads cleanly" item, not as new debt.

### L5 — connector-ux-sweep (2026-05-23)

- Status: `completed` (batched F5 commit at flight end per agentic-workflow protocol).
- Sweep statistics:
  - **6 / 6 target surfaces walked** via Chrome MCP (hard-reload + a11y snapshot + DOM-shape probe per surface). Surfaces: new-connector, Discord-edit-General, Discord-edit-A&R, Stub-edit-General, Stub-edit-A&R, agent-Connectors-tab (Cave Man Bot with both Discord + Stub attached).
  - **~85 elements enumerated** at primitive granularity across the 6 surfaces (12 + 16 + 18 + 14 + 16 + 9 by per-surface row counts in the coverage report).
  - **0 inline fixes** — all elements either map cleanly to existing DL primitives, map cleanly to MCP-editor patterns, or were deferred to future-UX-mission scope. Inline-fix log explicitly says "No inline fixes needed." Abort-threshold (~25 LOC cumulative) never approached.
  - **5 deferrals** captured (D1-D5), each with reason + follow-up:
    - D1 — `.discoverable-dropdown` composite (combobox + chiplist + status + refresh) — codify as DL primitive (≥ n=2 use sites).
    - D2 — `.connector-routing-table` with drag-handle column — codify as `.data-table` + `.drag-handle` pair.
    - D3 — Stub Attached-agents empty state uses `<em.form-hint>` instead of DL `.empty-state` primitive — UX-consistency follow-up.
    - D4 — `mcp-source-tile` family (`mcp-source-tile-*`, `tool-switch`) — undocumented; codify as expandable-tile DL section (≥ n=2 use sites including agent Connectors tab).
    - D5 — `connector-attached-agents-table` — bespoke table; absorbs into the same `.data-table` primitive as D2.
- Cross-cutting findings (high-consistency picture):
  - **`editor-section` + `section-title` + `::before { content: "//" }` divider** is universal across all 6 surfaces.
  - **`field-row admin-pf-row`** is the universal row primitive (Discord Runtime Config Servers/Presence rows use Discord-scoped wrappers because they're inside `<fieldset>` bodies — acceptable divergence).
  - **`field-info-icon` info-icon pattern** (`title=` + `aria-describedby=` + `<span.visually-hidden>` help-text) is faithful across every site — matches `mcp-server-editor.js:792` production convention.
  - **Test-connection treatment** (Discord + Stub both use `connector-test-row` button + LED + message) mirrors MCP's `mcp-test-row` (`mcp-server-editor.js:473`) — class name differs, shape identical.
  - **Chip primitive** (`<span class="chip">…<button class="chip-remove">×</button></span>`) applied at 5 sites with identical shape — high consistency.
  - **`<details>` collapsibles** use single-class-on-`<details>` convention at all 3 sites (3 directive disclosures + Advanced kv-table) — matches `mcp-server-editor.js:237`.
- Required verifications:
  - **L4 cycle-1 side effect (empty chips container hidden) — VERIFIED**: Surface 3 (Discord A&R) probe — `peers`, `groups`, `roles` chips containers have `display: none` + `hidden=true` (zero chips); `channels` container renders `display: flex` (one cold-pool chip pre-Test-Connection). On Surface 1 (new-connector) the dropdowns aren't rendered at all (no A&R tab until save), which is the upstream version of the same invariant. The L4 hidden-toggle + CSS specificity override work as designed across the cold-pool path.
  - **Stub A&R Runtime-Config-absence — VERIFIED**: Surface 5 (Stub A&R) probe — A&R panel sections are exactly Lifecycle / Account-scope allowlist / Routing rules; no Runtime Config section; `arPanel.querySelector('[data-testid=connector-account-runtime-config-section]')` returns `null`. The missing section is visually clean (no half-rendered placeholder, no empty section-title).
- Browser tests: not run — no inline fixes were made (per the leg's "only if inline fixes were made" guidance). Test suite stays at the post-L4 baseline.
- Adaptation notes: methodology held one-shot — Chrome MCP a11y snapshot + DOM-shape `evaluate_script` probes were sufficient to enumerate primitives without taking heavy full-page screenshots (the one full-page screenshot attempt timed out at Chrome MCP's protocol limit; subsequent surfaces used snapshot + structural probes only). The coverage report contains enough primitive-level evidence that a future operator can reproduce the sweep without revisiting the page. The five deferrals (D1-D5) are the actionable output for a future UX-codification mission; they all meet the n=2 codification threshold (F4 debrief recommendation #4) at the cluster level. Two patterns reached high-confidence cross-cutting consistency (info-icon convention; test-connection-row shape) — these are codified-in-practice already.

---

## Decisions

Runtime decisions not in original plan.

### 2026-05-23 — Cycle-1 batched code review: missed test update fixed

- L3 moved Intent checkboxes from the General tab to the Access-and-Routing tab and updated ~6 tests in `test_flow_studio_connector_discord_form.py` to activate the tab before interacting (via inlined `_activate_access_and_routing_tab(page)` helper). The cycle-1 batched review caught that `test_flow_studio_connector_invite_section.py::test_intent_toggle_preserves_url_and_permissions_constant` (different file) was missed and failed at the unguarded `discord-intent-message_content` click.
- Fix: inlined the same `_activate_access_and_routing_tab` helper into `test_flow_studio_connector_invite_section.py` and inserted the tab-activation step before the intent click. Pattern mirrors L3's cross-file convention (helper-per-file rather than shared module) to keep test coupling minimal.
- Verified: failing test now passes; full 89-test browser regression across all F5-touched connector surfaces is green.

### 2026-05-23 — Two non-blocking a11y observations captured for F5 debrief

The cycle-1 review surfaced two accessibility patterns worth re-examining, but neither blocks the F5 commit. Capturing here so they surface in `/flight-debrief` rather than getting folded into the F5 commit:

- **`aria-describedby` placement on info-icon sites (5 sites added by L3):** the description is currently associated with the info-icon button itself via `aria-describedby` → a visually-hidden sibling. The cleaner pattern is to put `aria-describedby="..."` on the associated form control (input/select/checkbox/fieldset) so the description fires when focus lands on the control, not only when the icon itself is focused.
- **Double-announcement on info-icon (`title=X` + `aria-describedby` → visually-hidden span containing X):** screen readers announce the title attribute and the described-by text — redundant. MCP precedent (the canonical info-icon site this leg modeled on) uses `title=X` + `aria-label=X` for a single announcement. Worth aligning the L3 sites with the MCP precedent for consistency.

Both are pattern-level concerns, not regressions; they apply equally to pre-F5 MCP sites and to the new F5 connector sites. Better addressed as a methodology pass in a future a11y-focused flight than a same-commit fix.

---

## Deviations

Departures from planned approach.

*(empty)*

---

## Anomalies

Unexpected issues encountered.

*(empty)*

---

## Flight Director Notes

### 2026-05-23 — Orchestration start

- /agentic-workflow invoked with `flight 5, mission 11, the-one`.
- Loaded leg-execution phase file (validated: Crew + Interaction Protocol + Prompts sections present; 5 fenced prompt blocks).
- Flight status `ready` → `in-flight`. Branch `flight/05-connector-ux-cleanup` created off `flight/04-…` HEAD at planning commit `9a5bb05`.
- Execution plan: L1 → L2 → L3 → L4 → L5 design+implement per-leg (no commit), batched Reviewer (+ Accessibility Reviewer for UI legs), single commit + draft PR, then L6 operator-driven HAT (own commit if any fixes surface).
- Methodology improvement over F4: Chrome MCP for in-flight verification throughout L1-L5 (not just HAT). Each leg's Developer can visually verify after edits via the Chrome MCP server already used at F4 L4.

### 2026-05-23 — L1 design review (cycle 1, needs rework → resolved)

- Spawned Developer for L1 design review.
- Outcome: needs rework. 2 HIGH + 2 MED + 3 LOW + 4 suggestions.
- HIGH #1: Auto-relay `tool-enable-switch` would render off-position without a CSS unpin (`.tool-enable-switch` is `position: absolute; bottom: 12px; right: 12px;` by default; every consumer adds a per-row unpin override per `admin.css:278-279` precedents). The leg's "no CSS changes" promise was incompatible with the chosen primitive. **Resolved**: leg now adds a single ~3 LOC `.area-studio .field-row.cf-auto-relay-row .tool-enable-switch` unpin rule in `admin.css`; AC + Outputs + Files Affected updated to reflect the narrow CSS change.
- HIGH #2: Intent `<div class="discord-intents-set">` substitution would have rendered ungrouped — no CSS rule exists for `.discord-intents-set`. **Resolved**: leg now PRESERVES the existing `<fieldset class="discord-intents-fieldset">` + `<legend>` shape; only the inner `<input type="checkbox">` markup gains `.checkbox-primary`. Minimum-diff path; preserves visual grouping for free.
- MED #1: Nested labels around Auto-relay input cause two click events on a single click that cancel each other. The MCP precedent at `mcp-server-editor.js:529-535` uses SIBLING labels (text label + toggle-track label both inside the field-row div, not nested). **Resolved**: leg AC + Implementation Guidance now explicitly state sibling shape, with a defensive AC that "Auto-relay toggle flips on a single click."
- MED #2: Once Auto-relay gains `.field-input`, `attachStaticListeners` (lines 931-934) registers the same change handler — the explicit handler at lines 943-945 becomes dead code. **Resolved**: leg now removes the 3-line explicit block + its M10-F8-L11-Fix-#4 comment.
- LOW catches absorbed: pinned `discord-intents-fieldset` class preservation (was loose "or similar"); confirmed MCP `<details>` precedent at design-time (3 sites in mcp-server-editor.js) — Advanced disclosure stays as-is; softened "no CSS changes" AC to "limited to one narrowly-scoped addition."
- Suggestions absorbed: tests-side framing inverted from "would need updating" to "verified immune" (data-testid preserved across all changes); citation audit grew to 15 sites including the new admin.css:278-281 precedents.
- L1 status → `ready`. Cycle 2 not needed — all fixes are spec-tightening (no structural rework of the leg's approach); the underlying intent (apply canonical primitives) is unchanged.

### 2026-05-23 — L2 design review (cycle 1, approve with changes)

- Spawned Developer for L2 design review.
- Outcome: approve with changes. 0 HIGH + 3 MED + 2 LOW + 3 suggestions + 3 questions.
- MED: 3 line-citation drifts (mount sequence 512→518; click handler 1179→1177; cache push 1602→1598). **Resolved**: leg-wide line repair; Citation Audit notes the repairs explicitly.
- MED: Registry-contract docstrings + agents.md Connector subsystem doc would drift. **Resolved**: added `connector-form-registry.js` (~2 docstring sites) + `the_one/agents.md` (Connector subsystem section) to the touched-files allowlist; new Implementation Guidance steps 9b + 9c require the doc-comment updates; ACs + Files Affected updated.
- MED: File-header doc-comment at `connector-account-editor.js:5-11` lists Test Connection as standalone section — stale after L2. **Resolved**: new Implementation Guidance step 9a + new AC + Files Affected entry require the header comment update.
- LOW: `renderTestConnectionRow()` helper placement was loose. **Resolved**: pinned to file-scope inside IIFE alongside `renderPairingSection` / `renderAllowlistSection` / `renderRoutingRulesSection` / `renderAttachedAgentsSection` (cycle-1 named the exact line precedents).
- LOW: CSS file pinning was ambiguous. **Resolved**: pinned to `studio.css:126` (where `.area-studio .mcp-test-row { margin-top: 8px; }` lives); add `.connector-test-row` to the selector list; no addition to `admin.css`.
- Suggestions absorbed: optional `data-testid="connector-connection-section"` on the wrapping div (future-proofing); corrected `wireInviteEvents` → `wireEvents` at `connector-form-discord.js:629-649` per cycle-1.
- Questions resolved by Flight Director:
  - Q1 ("Test Connection" capitalization in hint copy) — defer to L3 per the leg's existing "copy revisions deferred to L3" framing.
  - Q2 (retire `.connector-test-section` CSS class) — no rules target the class; clean removal with the markup. No separate action.
  - Q3 (registry docstring + agents.md updates) — folded into L2 per MED #2 above.
- L2 status → `ready`. Cycle 2 not needed — all fixes are spec-tightening + accurate-citation; structural approach unchanged.

### 2026-05-23 — L3 design review (cycle 1, needs rework → resolved)

- Spawned Developer for L3 design review.
- Outcome: needs rework. 1 HIGH + 3 MED + 4 LOW + 4 suggestions + 3 questions.
- HIGH: Create-mode regression — making Discord's `renderConnectionFields` return `''` unconditionally would break the create-flow (`test_create_mode_pick_discord_renders_typed_form` + `directive_section.py:452` both assert `discord-intents-fieldset` visible in create mode). Create-mode is a flat-layout (no tabs) so runtime-config needs to render in Connection section during creation. **Resolved**: Discord's `renderConnectionFields` becomes conditional — `return _renderRuntimeConfigBody(account)` when `isCreate === true`; `return ''` when `isCreate === false`. New internal `_renderRuntimeConfigBody` helper holds the shared markup; `renderRuntimeConfigFields` delegates to it. Single source-of-truth between create-time and edit-time rendering.
- MED: 6 edit-mode tests in `test_flow_studio_connector_discord_form.py` will silently break from `to_be_visible()` against the now-hidden Access-and-Routing tabpanel. **Resolved**: enumerated in Edge Cases + Implementation Guidance step 9 with the `_activate_access_and_routing_tab` helper pattern from `account_editor.py:89` to insert before each interaction.
- MED: Info-icon body convention mis-pinned — the leg cited `fields-section.js:18-24` inline-SVG sample (visual exemplar), but production pattern is `App.icon('info')` + `aria-describedby` + `visually-hidden` (used at `mcp-server-editor.js:790-795`, `tools-form-helpers.js:107-119`). **Resolved**: leg now pins the production pattern across the Inputs section + Implementation Guidance step 3 with exact markup.
- MED: Auto-relay `aria-label` rewrite missing from L1-touched `aria-label="Auto-relay peer replies to platform"`. **Resolved**: added an AC bullet requiring the aria-label rewrite to match the new visible label.
- LOW: Line-number drifts in Inputs section. **Resolved**: kept line numbers but flagged them as implementation-time-grep targets where post-L2 state may have shifted; semantic descriptions (e.g., "lifecycle build line range") preserved.
- LOW: "8th entry" ordinal for registry export. **Resolved**: dropped ordinal.
- LOW: Registry validation by-line-number is brittle. **Resolved**: described semantically.
- LOW: Runtime Config title concern — noted for L5 sweep; leg uses "Runtime Config" per Design Decision.
- Suggestions absorbed: dropped "(optional)" parenthetical from Servers label per lexicon-consistency; added Edge Case for existing `<small>`-element data-testids that might need migration to the info-icon button; file-header phrasing tightened to "Runtime Config — registry-mediated (Discord today)" matching L2 precedent.
- Questions resolved by Flight Director:
  - Q1 (create-mode placement) — option (a): Discord-side conditional `renderConnectionFields(account, isCreate)` returns runtime-config in create-mode, '' in edit-mode. Shared `_renderRuntimeConfigBody` helper for single source-of-truth.
  - Q2 (L3 vs L5 seam on Lifecycle hints) — keep L3 doing Lifecycle hints (Pool idle timeout + Chat-session continuation) per the leg's locked scope; allowlist empty-list hints stay as `<small>` deferred to L5 sweep.
  - Q3 (file-header phrasing) — yes, match L2's "registry-mediated" phrasing for Runtime Config.
- L3 status → `ready`. Cycle 2 not needed — the HIGH was resolved by structural addition (shared helper + conditional), not structural rework; the other findings are spec-tightening.

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

### 2026-05-23 — L4 design review (cycle 1, needs rework → resolved)

- Spawned Developer for L4 design review.
- Outcome: needs rework. 2 HIGH + 1 MED + 4 suggestions + 2 questions.
- HIGH: JS `hidden` attribute alone insufficient — `.area-studio .chip-list-editor` `display: flex` (admin.css:393-406, specificity 0,0,2,0) overrides the user-agent `[hidden]` rule (0,0,1,0). **Resolved**: leg now requires companion CSS `.area-studio .discoverable-dropdown-chips[hidden] { display: none; }` (0,0,3,0) that outranks the chip-list-editor display rule.
- HIGH: existing `.area-studio .connector-acl-axis-body` rule at `studio.css:1104` (`margin-top: 8px`) would conflict with the new shorthand `margin` proposal. **Resolved**: leg now EXTENDS the existing rule in-place (preserves `margin-top: 8px`); adds border-left + padding + background + border-radius. Tonal background changed from `--surface` to `--surface-elevated` per cycle-1 — `--surface` matched chip-list-editor background and read as visually flat.
- MED: line drift on `_buildAxisRow` (cited 206; actual 262). **Resolved**: line-wide repair.
- Suggestions absorbed: avoid mutating Discord Constellation chip state (downstream HAT dependency) — use Stub HAT Account as the chip add/remove playground; Chrome MCP verification now includes computed-style check via `evaluate_script`; noted positive side effect that pre-probe-404 path also stops rendering the blank chip box (intentional).
- Questions resolved by Flight Director:
  - Q1 (require computed-style check) — yes; added to Verification Steps + Implementation Guidance step 4.
  - Q2 (`--surface` vs `--surface-elevated` for background) — `--surface-elevated` per cycle-1; matches the existing nested-surface treatment at studio.css:1135, 1169.
- L4 status → `ready`. Cycle 2 not needed — fixes are spec-tightening + accurate-citation + CSS-precedent compliance; structural approach unchanged.

### 2026-05-23 — L5 design review (cycle 1, approve with changes)

- Spawned Developer for L5 design review.
- Outcome: approve with changes. 0 HIGH + 3 MED + 3 LOW + 5 suggestions.
- MED: Inline-fix LOC abort threshold missing — leg said ≤ 30 LOC cumulative but no behavior when approaching limit. **Resolved**: added abort-threshold rule (stop folding at ~25 LOC; defer remaining).
- MED: "Visible element" granularity convention undefined — risk of inconsistent enumeration. **Resolved**: added granularity AC (enumerate at primitive level; field-row = one row; details = one row; tab strip = one row).
- MED: Weak `grep -c "^| "` heuristic for coverage. **Resolved**: dropped; replaced with "read the file; verify ≥ 8 data rows per surface."
- LOWs absorbed: AC for L4 cycle-1 positive side effect verification (chips hidden on cold-pool new-connector page); AC for Stub A&R Runtime-Config-absence verification; AC for Cross-cutting findings section presence.
- Suggestions absorbed: empty-deferral-list explicit language; no-commit reminder already in Post-Completion Checklist.
- L5 status → `ready`. Cycle 2 not needed — fixes are tightening + new ACs; methodology approach unchanged.
