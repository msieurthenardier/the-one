# Leg: move-runtime-config-and-relabel

**Status**: completed
**Flight**: [Connector UX Cleanup](../flight.md)

## Objective

Move the Discord typed-form's runtime-config block (Intents + Guilds + Presence + Advanced-kv) from the General tab's Connection section to the Access-and-Routing tab, between Lifecycle and Allowlist. Add a new OPTIONAL registry hook `renderRuntimeConfigFields(account)` that the substrate calls when building the Access-and-Routing tab. Discord's existing `renderConnectionFields` becomes empty (return `''`) — Discord has no typed Connection-level fields anymore; Connection holds Name + Type + Test Connection + Invite (substrate-managed via L2). Rewrite verbose labels + help-text across the touched surfaces for human-friendliness, using `.field-info-icon` tooltips per Design Language `fields-section.js:18-24` to replace `<small class="form-hint">` blocks where the help text fits in a tooltip. Tab semantics become coherent: **General = WHAT the bot is** (Name / Type / Bot Token / Pairing / Directive / Attached Agents / Test Connection + Invite) vs **Access and Routing = HOW it behaves at runtime** (Lifecycle / Runtime Config / Allowlist / Routing Rules). Chrome MCP visual verification + persistence-round-trip via browser tests.

## Context

- F5 L3 is the section-shape change per the flight's "primitives-first then section-shape" sequencing. L1 + L2 landed (form-controls re-styled; Test Connection + Invite folded into Connection section). L3 moves runtime-config across tabs and rewrites copy.
- F5 flight Design Decision "Move runtime-config from General → Access and Routing; tab order" pins: new Access-and-Routing tab order is **Lifecycle → Runtime Config → Allowlist → Routing Rules**. Lifecycle stays at top (connection mechanics); Runtime Config sits next (event types received + servers scoped); then access surfaces.
- F5 flight Design Decision "Labels + info-icon tooltips — match MCP-editor pattern" pins: most `<small class="form-hint">` verbose help-text → `.field-info-icon` tooltips; labels rewrite for human-friendliness; help-text that genuinely needs multi-line operator guidance stays as `<small>` but is shortened.
- The registry contract pattern is established (`renderConnectionFields` required; `renderInviteSection` / `renderDirectiveSection` / `renderDiscoverableDropdown` optional). L3 adds `renderRuntimeConfigFields` as the 4th optional hook, following the same shape (typed-form returns HTML string; substrate decides where to mount it).
- L2 just added `renderTestConnectionRow()` to `connector-account-editor.js` at file-scope inside the IIFE. L3 follows the same placement convention for any new helpers.
- F4 L4 fold-in (`connector-account-pool-warmed` event) is unaffected — the event listener lives on `document`, not on any runtime-config DOM ancestor. The Test Connection click on General tab still fires the event; mounted dropdowns on Access-and-Routing tab still re-fetch.
- Touched-surface UX-debt folding: no outstanding UX-debt against `connector-form-discord.js:renderConnectionFields` or `connector-account-editor.js:renderConnectorAccountEditor` beyond items in F5 scope. The L2 file-header comment was just updated; L3 may need to update it again to reflect the new Access-and-Routing tab structure.

## Inputs

- `connector-form-discord.js:renderConnectionFields` (line 163) currently returns Intents + Guilds + Presence + Advanced. After L1 + L2, the Intent inputs have `.checkbox-primary`, the Guilds/Presence-name inputs have `.field-input`, the Presence-type select has `.field-input.field-select`. The verbose `<small class="form-hint">` blocks at lines ~189-191, ~201, ~221-222 remain (L1 explicitly deferred to L3).
- `connector-form-discord.js:renderInviteSection` (line 385) and `:renderDirectiveSection` (line 438) are unchanged from L2 — L3 does not touch these.
- `connector-form-discord.js`'s registry export object at lines 720-726 lists the hooks. L3 adds `renderRuntimeConfigFields: renderRuntimeConfigFields` to that object.
- `connector-form-registry.js` `optionalFns` array at lines 138-144 enumerates the optional hooks. L3 adds `'renderRuntimeConfigFields'` to that array. The registry validation walks the array; no other registry changes needed.
- `connector-form-registry.js` `validateEntry` comment block at lines 112-137 documents each optional hook. L3 adds a documentation paragraph for `renderRuntimeConfigFields` matching the established prose pattern.
- `connector-account-editor.js` Access-and-Routing tab block at lines ~527-531 (verify line; was at 526-531 pre-L2) emits `lifecycleHtml + allowlistHtml + routingHtml`. L3 inserts `runtimeConfigHtml` between `lifecycleHtml` and `allowlistHtml`.
- `connector-account-editor.js` builds `lifecycleHtml` at lines ~340-396 (pre-L2 line range; verify post-L2). Auto-relay row is inside `lifecycleHtml` after L1.
- The `attachStaticListeners` selector at `connector-account-editor.js:932-933` is `.editor-section .field-input:not(.config-key-input):not(.config-value-input):not(.secret-key-input):not(.secret-value-input), .editor-section .field-select`. The L3-moved Runtime Config block lands inside a new `<div class="editor-section">` on the Access-and-Routing tab, so its `.field-input` / `.field-select` inputs ARE picked up — verified-by-construction.
- The Discord `wireEvents` function in `connector-form-discord.js` (search lines 540+ for the wireup) listens for change events on `[data-field^="intent-"]`, `[data-field="guilds-list"]`, `[data-field="presence-name"]`, `[data-field="presence-type"]`. These listeners attach in the editor's wireup phase regardless of which tab the inputs live on — verified by data-field-based lookup.
- **`field-info-icon` PRODUCTION pattern** (cycle-1 reviewer pinned via grep — supersedes the `fields-section.js:18-24` inline-SVG sample which is a VISUAL exemplar, not a usage exemplar):
  ```html
  <button type="button" class="field-info-icon" title="{escapeAttr(text)}" aria-describedby="{descId}">{App.icon('info')}</button>
  <span id="{descId}" class="visually-hidden">{escapeHtml(text)}</span>
  ```
  - `App.icon('info')` returns the lucide info-icon SVG (defined in `the_one/interfaces/web/static/js/icons.js`).
  - The `title=` attribute provides the browser-native tooltip; `aria-describedby` + `visually-hidden` sibling provides the screen-reader-accessible description (no duplicate announcement).
  - References: `mcp-server-editor.js:790-795`, `tools-form-helpers.js:107-119`, `tools-editor.js:180`.
- Chrome MCP available; `the-one` container at `http://localhost:8484/`.

## Outputs

- **`connector-form-discord.js`**:
  - `renderConnectionFields(account, isCreate)` returns the runtime-config block when `isCreate === true` (create-mode flat layout has no tabs; the typed-form fields must render somewhere visible during creation so the operator can set Intents/Guilds/Presence before clicking Create & Test). Returns `''` when `isCreate === false` (edit-mode has tabs; runtime-config moves to A&R via the new hook). Add a one-line comment explaining this conditional. **Critical**: in CREATE mode, the same runtime-config markup is shared between `renderConnectionFields` (create-time) and `renderRuntimeConfigFields` (edit-time) — factor out a shared internal helper `_renderRuntimeConfigBody(account)` so the markup is single-source-of-truth.
  - Add `renderRuntimeConfigFields(account)` returning the runtime-config block (Intents + Guilds + Presence + Advanced) by delegating to `_renderRuntimeConfigBody(account)`. Same markup as the (factored-out) helper. The relabel rewrites + info-icon tooltips live in the shared helper.
  - Registry export object at lines 720-726 grows `renderRuntimeConfigFields: renderRuntimeConfigFields,`.
- **`connector-form-registry.js`**:
  - `optionalFns` array at lines 138-144 grows `'renderRuntimeConfigFields'`.
  - Add a documentation paragraph in the validation comment block (around line 137) explaining the new hook: when present, the substrate mounts the returned HTML on the Access-and-Routing tab between Lifecycle and Allowlist; absent means the typed-form has no runtime-config block (`'stub'` and any future-type-with-no-runtime-config).
- **`connector-account-editor.js`**:
  - Add `runtimeConfigHtml` variable construction between the existing `lifecycleHtml` and `allowlistHtml` builds. Pattern:
    ```javascript
    // Runtime Config section — registry-mediated (Discord today; future
    // typed connectors with runtime config blocks plug in here). The
    // hook returns wrapper-less content; substrate wraps in an
    // editor-section with a section-title.
    var runtimeConfigHtml = '';
    if (!isCreate) {
      var runtimeRegistry = (window.App && window.App.studio && window.App.studio.connectorFormRegistry) || null;
      var runtimeEntry = (runtimeRegistry && account && account.type) ? runtimeRegistry.get(account.type) : undefined;
      if (runtimeEntry && typeof runtimeEntry.renderRuntimeConfigFields === 'function') {
        var inner = runtimeEntry.renderRuntimeConfigFields(account);
        if (inner) {
          runtimeConfigHtml += '<div class="editor-section">';
          runtimeConfigHtml += '<div class="section-title">Runtime Config</div>';
          runtimeConfigHtml += inner;
          runtimeConfigHtml += '</div>';
        }
      }
    }
    ```
    Section title "Runtime Config" matches the F5 flight Design Decision; verify with Chrome MCP that the existing section-title typography reads cleanly.
  - Access-and-Routing tab block at lines ~527-531 inserts `runtimeConfigHtml` between `lifecycleHtml` and `allowlistHtml`: new sequence `lifecycleHtml + runtimeConfigHtml + allowlistHtml + routingHtml`.
  - File-header doc-comment at lines 5-11 (just updated in L2) gets another small update: Access-and-Routing tab now lists `Lifecycle / Runtime Config — registry-mediated (Discord today) / Allowlist / Routing Rules` (matches the symmetric phrasing the L2 update introduced for the registry-mediated Invite block).
- **Label rewrites + info-icon tooltips** (the relabel half of L3) — apply to:
  - `connector-form-discord.js` runtime-config block (now in `renderRuntimeConfigFields`):
    - **Intents fieldset legend**: keep `<legend>Intents</legend>`. The verbose `<small class="form-hint">` ("Discord gateway intents — controls which event types the bot receives. All on is the safe default; disable individual intents only if you understand the consequences.") REPLACED with a `<button class="field-info-icon" title="...">` adjacent to the legend. Tooltip text shortened to: "Discord event types the bot receives. All on is the safe default."
    - **Guilds label**: rewrite from "Guilds" to "Servers (optional)" so the operator vocabulary matches Discord-native terms (already established in M11 F1's vocabulary substitution). The `<small class="form-hint">` ("Comma-separated Discord guild IDs (digit-only).") REPLACED with a `<button class="field-info-icon" title="...">` next to the label. Tooltip text: "Comma-separated server IDs. Leave blank to allow all servers the bot is in."
    - **Presence label**: keep "Presence". The `<small class="form-hint">` ("Activity name + type for the bot's status. Leave both blank to use the default presence.") REPLACED with a `<button class="field-info-icon" title="...">` next to the label. Tooltip text: "What the bot shows as its activity status. Blank for default."
    - **Advanced disclosure summary**: keep "Advanced (kv-table)".
  - `connector-account-editor.js` Auto-relay row (just re-styled in L1):
    - **Auto-relay label**: rewrite from "Auto-relay peer replies to platform" to "Auto-reply to platform messages". Shorter, friendlier, removes technical "peer" jargon.
    - **`<small class="form-hint">`** at lines ~388-394: REPLACED with a `<button class="field-info-icon" title="...">` next to the label. Tooltip text: "When on, the agent's replies post back to Discord automatically. Off requires the agent to explicitly invoke send_to_platform_channel."
  - `connector-account-editor.js` Lifecycle section:
    - **Pool idle timeout `<small>` hint** ("Reap warm connection after inactivity."): REPLACED with `field-info-icon` tooltip. Same text or slightly shorter.
    - **Chat-session continuation `<small>` hint** ("Inbound continues the same chat session within this window."): REPLACED with `field-info-icon` tooltip. Same text.
  - `connector-account-editor.js` Account-scope allowlist section:
    - **Empty-list hints** ("Empty list = no user restriction." / "Empty list = no channel restriction." etc.): these are inline-help text that conveys real meaning when the list is empty; KEEP as `<small>` for L3 (operator may want them more visible than a tooltip). L5 sweep may reconsider.
  - Other `<small class="form-hint">` sites: GREP `connector-account-editor.js` and `connector-form-discord.js` for `class="form-hint"`. For each one, judge whether it fits in a tooltip (label-adjacent help → tooltip) or is multi-line operator guidance below the input (keep as `<small>`, optionally shortened).
- **`the_one/agents.md`**:
  - Connector subsystem doc gets a new paragraph about `renderRuntimeConfigFields` hook mirroring the existing `renderInviteSection` documentation shape.
- No data-testid changes. No id changes. No data-field changes. All form-data collection paths continue to round-trip.
- CSS: NONE expected. `.field-info-icon` already exists at `components.css:226`. If the info-icon's visual placement next to a label needs a small spacing rule, it lands as one targeted addition; otherwise skip.
- Sibling artifact bookkeeping: F5 `flight.md`'s L3 Checkpoints + L3 Legs item checked off; F5 `flight-log.md`'s Leg Progress section grows an L3 entry; this leg artifact's Status header progresses through its lifecycle.

## Acceptance Criteria

- [x] `connector-form-discord.js:renderConnectionFields(account, isCreate)` returns the runtime-config block when `isCreate === true` (delegates to shared helper `_renderRuntimeConfigBody`); returns `''` when `isCreate === false` (runtime-config has moved to A&R via the new hook).
- [x] `connector-form-discord.js` exports a new function `renderRuntimeConfigFields(account)` that returns the runtime-config HTML block by delegating to `_renderRuntimeConfigBody(account)` (single-source-of-truth between create-mode and edit-mode rendering).
- [x] `connector-form-discord.js` defines an internal helper `_renderRuntimeConfigBody(account)` holding the Intents fieldset + Guilds row + Presence row + Advanced kv-table disclosure markup — with the rewritten labels + info-icon tooltips applied here once.
- [x] `connector-form-discord.js` registry export object grows `renderRuntimeConfigFields: renderRuntimeConfigFields,` (position in the export object is not significant — placement next to other render hooks is conventional).
- [x] `connector-form-registry.js` `optionalFns` array grows `'renderRuntimeConfigFields'`. The validation walks the new entry without error.
- [x] `connector-form-registry.js` validation comment block documents the new hook semantics matching the established prose pattern for `renderInviteSection` / `renderDirectiveSection`.
- [x] `connector-account-editor.js` builds `runtimeConfigHtml` via registry hook lookup; mounts inside `<div class="editor-section"><div class="section-title">Runtime Config</div>...</div>` on the Access-and-Routing tab between Lifecycle and Allowlist.
- [x] `connector-account-editor.js` Access-and-Routing tab mount sequence: `lifecycleHtml + runtimeConfigHtml + allowlistHtml + routingHtml`. Runtime Config slots between Lifecycle and Allowlist as specified.
- [x] `connector-account-editor.js` file-header doc-comment at lines 5-11 updated to reflect the new tab structure (Access-and-Routing now lists Lifecycle / Runtime Config / Allowlist / Routing Rules).
- [x] Discord runtime-config block on Access-and-Routing tab renders the Intents fieldset, Guilds row, Presence row, and Advanced kv-table disclosure (same content as pre-L3, just moved tabs).
- [x] Verbose `<small class="form-hint">` blocks REPLACED with `.field-info-icon` tooltips in the runtime-config block:
  - Intents fieldset's verbose explanation → tooltip on a `.field-info-icon` next to the legend. Text: "Discord event types the bot receives. All on is the safe default."
  - Guilds row's `<small>` ("Comma-separated Discord guild IDs (digit-only).") → tooltip next to the label. Text: "Comma-separated server IDs. Leave blank to allow all servers the bot is in."
  - Presence row's `<small>` → tooltip next to the label. Text: "What the bot shows as its activity status. Blank for default."
- [x] **Guilds label** rewritten to "Servers" matching Discord-native vocabulary (Discord calls them servers; Guild is the API term). NO "(optional)" parenthetical — matches the surrounding lexicon (allowlist labels are "Servers"/"Users"/"Channels"/"Roles" plain); optionality is conveyed in the tooltip text ("Leave blank to allow all servers the bot is in").
- [x] `connector-account-editor.js` Auto-relay row:
  - Visible label rewritten from "Auto-relay peer replies to platform" to "Auto-reply to platform messages".
  - **`aria-label` on the auto-relay checkbox input** (currently `aria-label="Auto-relay peer replies to platform"` from L1) also rewritten to "Auto-reply to platform messages" so screen-reader users hear the same wording as sighted users.
  - `<small class="form-hint">` REPLACED with `.field-info-icon` tooltip. Text: "When on, the agent's replies post back to Discord automatically. Off requires the agent to explicitly invoke send_to_platform_channel."
- [x] `connector-account-editor.js` Lifecycle section:
  - Pool idle timeout `<small>` REPLACED with `.field-info-icon` tooltip.
  - Chat-session continuation `<small>` REPLACED with `.field-info-icon` tooltip.
- [x] `connector-account-editor.js` Allowlist empty-list hints stay as `<small>` (inline-meaning text; preserved).
- [x] `the_one/agents.md` Connector subsystem doc grows a paragraph about the `renderRuntimeConfigFields` hook contract.
- [x] No changes to data-testids, ids, or data-field attributes on any input/label/select.
- [x] No CSS changes unless absolutely required for `.field-info-icon` spacing next to labels (verify visually; if needed, ~3 LOC in `studio.css` or `components.css`).
- [x] Form-data round-trip preserved: edit a Discord account, change an Intent + Guild + Presence + Auto-relay, Save, reload editor, verify all changes persist. Chrome MCP verifies.
- [x] In-flight Chrome MCP verification:
  - Navigate to `http://localhost:8484/#studio/connectors/58f1fe5a833f`; General tab — confirm NO Intents/Guilds/Presence/Advanced content (only Name/Type/Test Connection/Invite + the existing Credentials/Pairing/Directive/AttachedAgents sections).
  - Click Access and Routing tab — confirm tab now shows Lifecycle → Runtime Config (Intents/Guilds/Presence/Advanced) → Allowlist → Routing Rules in that order.
  - Hover the new info-icons; verify tooltips render with the rewritten text.
  - Click Auto-relay toggle — single click flips state (L1 contract preserved).
- [x] Browser test suite: `docker exec the-one pytest tests/browser/test_flow_studio_connector_account_editor.py tests/browser/test_flow_studio_connector_discord_form.py tests/browser/test_flow_studio_connector_discord_vocabulary.py tests/browser/test_flow_studio_connector_account_create_and_test.py tests/browser/test_flow_studio_connector_directive_section.py -m browser -x --timeout 60 -v` passes. Tests asserting tab-relative ordering or General-tab section count may need updates — that's expected and part of L3 scope.
- [x] Source files modified: `connector-form-discord.js`, `connector-form-registry.js`, `connector-account-editor.js`, `the_one/agents.md`. Optionally `studio.css` IF info-icon spacing needs a CSS tweak.

## Verification Steps

- `grep -n "renderRuntimeConfigFields" the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js the_one/interfaces/web/static/js/areas/studio/connector-form-registry.js the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` returns at least 4 hits (function def + export + registry validation + editor call).
- `grep -n "field-info-icon" the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` returns at least 5 hits (3 in runtime-config block + Auto-relay + 2 in Lifecycle).
- `grep -nE "class=\"form-hint\"" the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js` returns 0 hits (all moved to tooltips).
- `grep -nE "Auto-relay peer replies to platform" the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` returns 0 hits (label rewritten).
- `grep -nE "Auto-reply to platform messages" the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` returns at least 1 hit (new label).
- `grep -n "section-title.*Runtime Config" the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` returns exactly 1 hit (new Runtime Config section-title).
- Visual (Chrome MCP):
  - General tab — Connection section contains Name + Type + Test Connection + Invite ONLY. No Intents/Guilds/Presence/Advanced anywhere on General tab.
  - Access and Routing tab — Runtime Config section appears between Lifecycle and Allowlist with the moved content.
  - Hover info-icons — tooltips render with rewritten text.
  - Click Auto-relay — single click flips state.
- Persistence round-trip (Chrome MCP):
  - Edit Discord Constellation, change an Intent (e.g., un-check Servers), change Presence name to "test-presence-l3", change Auto-relay state, Save.
  - Reload page; reopen editor; verify all 3 changes persisted.
- Browser test suite: `docker exec the-one pytest tests/browser/test_flow_studio_connector_account_editor.py tests/browser/test_flow_studio_connector_discord_form.py tests/browser/test_flow_studio_connector_discord_vocabulary.py tests/browser/test_flow_studio_connector_account_create_and_test.py tests/browser/test_flow_studio_connector_directive_section.py -m browser -x --timeout 60 -v` passes.
- `git diff --stat` shows changes in: `connector-form-discord.js`, `connector-form-registry.js`, `connector-account-editor.js`, `the_one/agents.md`, optionally `studio.css`, + F5 sibling artifacts.

## Implementation Guidance

1. **Read target file sections** before editing:
   - `connector-form-discord.js:163-238` — current `renderConnectionFields` body (post-L1 with `.checkbox-primary` etc.)
   - `connector-form-discord.js:720-728` — registry export object
   - `connector-form-registry.js:88-153` — validation logic + comment block
   - `connector-account-editor.js:316-330` — Connection section block (post-L2)
   - `connector-account-editor.js:340-396` — Lifecycle section build (with Auto-relay)
   - `connector-account-editor.js:518-525` — General-tab mount sequence (post-L2)
   - `connector-account-editor.js:526-531` — Access-and-Routing tab mount sequence
   - `connector-account-editor.js:5-11` — file-header doc-comment (post-L2)
   - `mcp-server-editor.js:792` (GREP first to confirm line) — MCP `field-info-icon` usage for tooltip-text pattern reference.

2. **Decide tooltip-text mechanism for `.field-info-icon`**:
   - GREP `mcp-server-editor.js` for `field-info-icon` to see how MCP attaches tooltip text. If MCP uses `title="..."` attribute (browser-native tooltip), use that. If MCP uses `aria-describedby` + a sibling tooltip element, use that.
   - Document the chosen mechanism in Implementation Guidance for consistency across L3's ~5 new info-icons.

3. **Refactor `connector-form-discord.js`** for shared markup + cross-tab placement:
   - Define internal helper `_renderRuntimeConfigBody(account)` (file-scope inside IIFE, near `renderConnectionFields`). Body holds the existing Intents fieldset + Guilds row + Presence row + Advanced kv-table disclosure markup with the relabel rewrites applied:
     - **Intents fieldset**: keep `<fieldset class="discord-intents-fieldset"><legend>Intents</legend>`; ADD a sibling `<button type="button" class="field-info-icon" title="Discord event types the bot receives. All on is the safe default." aria-describedby="discord-intents-help-text">{App.icon('info')}</button><span id="discord-intents-help-text" class="visually-hidden">Discord event types the bot receives. All on is the safe default.</span>` next to the legend. REMOVE the verbose `<small class="form-hint">` block at the old lines 189-191.
     - **Guilds row**: rewrite `<label for="cf-discord-guilds">Guilds</label>` to `<label for="cf-discord-guilds">Servers</label>`; ADD info-icon: `<button type="button" class="field-info-icon" title="Comma-separated server IDs. Leave blank to allow all servers the bot is in." aria-describedby="discord-guilds-help-text">{App.icon('info')}</button><span id="discord-guilds-help-text" class="visually-hidden">...</span>`. REMOVE the verbose `<small>` block.
     - **Presence row**: keep `<label>Presence</label>`; ADD info-icon: `<button ... title="What the bot shows as its activity status. Blank for default." ...>`. REMOVE the verbose `<small>` block.
     - Advanced kv-table disclosure unchanged.
   - Modify `renderConnectionFields(account, isCreate)`:
     ```javascript
     function renderConnectionFields(account, isCreate) {
       // L3: in create-mode (flat layout, no tabs), runtime-config renders
       // here so the operator can configure Intents/Guilds/Presence before
       // clicking Create & Test. In edit-mode (tabbed), runtime-config
       // moves to the Access-and-Routing tab via renderRuntimeConfigFields.
       if (isCreate) {
         return _renderRuntimeConfigBody(account);
       }
       return '';
     }
     ```
   - Add `renderRuntimeConfigFields(account)` that delegates to the shared helper:
     ```javascript
     function renderRuntimeConfigFields(account) {
       return _renderRuntimeConfigBody(account);
     }
     ```

4. **Register the new hook**:
   - `connector-form-discord.js` registry export at lines 720-726: add `renderRuntimeConfigFields: renderRuntimeConfigFields,`.
   - `connector-form-registry.js:138-144` `optionalFns` array: add `'renderRuntimeConfigFields'`.
   - `connector-form-registry.js` validation comment block: add a documentation paragraph matching the `renderInviteSection` precedent (~5-10 LOC of prose).

5. **Mount the new section in `connector-account-editor.js`**:
   - Build `runtimeConfigHtml` between the existing `lifecycleHtml` and `allowlistHtml` builds (around line ~400).
   - Update the Access-and-Routing tab mount sequence to include `runtimeConfigHtml` between `lifecycleHtml` and `allowlistHtml`.
   - Update file-header doc-comment at lines 5-11 to reflect Runtime Config on Access-and-Routing.

6. **Relabel + info-icon tooltips in `connector-account-editor.js`**:
   - Auto-relay row: rewrite label + replace `<small>` with `.field-info-icon` tooltip.
   - Lifecycle section's Pool-idle-timeout + Chat-session-continuation `<small>` blocks: replace with `.field-info-icon` tooltips next to their labels.
   - Allowlist empty-list hints: KEEP as `<small>` for L3 (operator may want them more visible; L5 sweep reconsiders).

7. **Update `the_one/agents.md`** Connector subsystem doc:
   - Add a paragraph about `renderRuntimeConfigFields` hook contract (mounted between Lifecycle and Allowlist on Access-and-Routing tab; absent → no runtime-config section renders).

8. **Run Chrome MCP visual verification** after edits:
   - Hard-reload `http://localhost:8484/#studio/connectors/58f1fe5a833f` (Discord Constellation).
   - General tab: confirm Connection section shows ONLY Name + Type + Test Connection + Invite. Confirm Credentials/Pairing/Directive/AttachedAgents/DangerZone sections remain.
   - Access and Routing tab: confirm Runtime Config section appears between Lifecycle and Allowlist with the Intents/Guilds/Presence/Advanced content.
   - Hover the new info-icons; verify tooltips render the rewritten text.
   - Click Auto-relay toggle; single click flips state.
   - Test persistence round-trip: change an Intent + Guild + Presence + Auto-relay, Save, reload, verify all changes persisted.

9. **Update edit-mode browser tests** (cycle-1 reviewer enumerated):
   - Edit `tests/browser/test_flow_studio_connector_discord_form.py` to insert a tab-click before EACH edit-mode test that interacts with `discord-intent-*`/`discord-guilds-list`/`discord-presence-*` testids. Affected tests (~6): `test_edit_mode_renders_typed_fields_with_persisted_intents`, `test_intent_toggle_re_enables_save`, `test_intent_toggle_save_emits_typed_payload`, `test_guilds_add_saves`, `test_presence_name_and_type_save`, `test_advanced_disclosure_hides_reserved_keys`.
   - Pattern (copy from `test_flow_studio_connector_account_editor.py:89` `_activate_access_and_routing_tab` helper, OR inline the same logic):
     ```python
     def _activate_access_and_routing_tab(page: Page) -> None:
         tab = page.locator('[data-testid="tab-access-and-routing"]')
         tab.click()
         expect(page.locator('[data-testid="connector-account-discord-runtime-config-section"]')).to_be_visible(timeout=4000)
     ```
     (Adjust the wait-for-visible selector to whatever runtime-config-section testid you choose during implementation.)

10. **Run targeted browser tests**:
   - `docker exec the-one pytest tests/browser/test_flow_studio_connector_account_editor.py tests/browser/test_flow_studio_connector_discord_form.py tests/browser/test_flow_studio_connector_discord_vocabulary.py tests/browser/test_flow_studio_connector_account_create_and_test.py tests/browser/test_flow_studio_connector_directive_section.py -m browser -x --timeout 60 -v`
   - Create-mode tests (`test_create_mode_pick_discord_renders_typed_form`, `directive_section.py:452`) stay passing because the leg preserves create-mode rendering via the shared helper.
   - Edit-mode tests should pass after the tab-click insertions in step 9.

11. **Update F5 `flight.md`** — check off L3 in Checkpoints + Legs sections.

12. **Append L3 leg-progress entry** to F5 `flight-log.md`.

13. **Update this leg artifact's Status header** progressively: `planning` → `ready` → `in-flight` → `landed`.

14. **Source files modified** (final list per cycle-1 scope-sync):
    - `connector-form-discord.js` (renderConnectionFields conditional, new helpers, relabels + info-icons)
    - `connector-form-registry.js` (optionalFns + comment block)
    - `connector-account-editor.js` (runtimeConfigHtml mount, Auto-relay label + aria-label + info-icon, Lifecycle info-icons, file-header)
    - `the_one/agents.md` (Connector subsystem doc)
    - `tests/browser/test_flow_studio_connector_discord_form.py` (tab-click insertions; ~6 tests)
    - Optionally `studio.css` (info-icon spacing if needed)

## Edge Cases

- **Create-mode preservation**: per cycle-1 architect HIGH catch, `renderConnectionFields` MUST return the runtime-config block when `isCreate === true` (no tabs in create-mode; the typed fields need to render in the Connection section so the operator can configure before clicking Create & Test). `test_create_mode_pick_discord_renders_typed_form` (`account_create_and_test.py:220-234`) and `directive_section.py:452` both assert `discord-intents-fieldset` is visible in create mode — they stay PASSING because L3 preserves the create-mode rendering via the `_renderRuntimeConfigBody` shared helper.
- **Edit-mode tests need tab-click before interacting with runtime-config elements** (cycle-1 reviewer enumerated): the following tests in `tests/browser/test_flow_studio_connector_discord_form.py` need an `_activate_access_and_routing_tab` click inserted BEFORE the first interaction with `discord-intent-*`/`discord-guilds-list`/`discord-presence-*` testids:
  - `test_edit_mode_renders_typed_fields_with_persisted_intents` (~line 86)
  - `test_intent_toggle_re_enables_save` (~line 106)
  - `test_intent_toggle_save_emits_typed_payload` (~line 185)
  - `test_guilds_add_saves` (~line 207)
  - `test_presence_name_and_type_save` (~line 225)
  - `test_advanced_disclosure_hides_reserved_keys` (~line 256)
  The helper `_activate_access_and_routing_tab(page)` already exists at `test_flow_studio_connector_account_editor.py:89` — either import it OR copy the implementation inline (the helper does `page.locator('[data-testid="tab-access-and-routing"]').click()` and waits for the panel to be visible). The leg implements inline copy for minimum disruption; future flight may lift to a shared `tests/browser/helpers.py`.
- **Persistence wiring**: the typed-form's `wireEvents` (`connector-form-discord.js`) and `collect` (in the registry hook) read fields by `data-field=` selectors. These selectors are tab-agnostic — `document.querySelector('[data-field="intent-message_content"]')` finds the input regardless of tab. Verified by-construction.
- **`renderConnectionFields` returning `''`**: the substrate's call site is `connectionHtml += renderConnectionFields(account, types, isCreate);` (in connector-account-editor.js). Appending `''` is a no-op. No null-check needed.
- **Other connector types (Stub)**: Stub's `renderConnectionFields` continues to return its Stub-specific config-kv content. Stub does NOT register `renderRuntimeConfigFields` (it's optional); so its Access-and-Routing tab has no Runtime Config section. Verify by-construction: the new `runtimeConfigHtml` build path checks `runtimeEntry && typeof runtimeEntry.renderRuntimeConfigFields === 'function'` — Stub fails the typeof check; `runtimeConfigHtml` stays `''`.
- **F4 L4 pool-warmed event**: unchanged. The Test Connection click on General tab still fires `connector-account-pool-warmed`; the discoverable-dropdown listeners on the (now-moved) runtime-config or on the existing allowlist editor still re-fetch.
- **Existing data-testids on `<small>` hints being removed**: GREP `grep -rn "connector-account-auto-relay-hint\|connector-account-idle-hint\|connector-account-continuation-hint" tests/` before removing these `<small>` elements. If any test asserts visibility/text of these testids, the test needs updating OR the testid should migrate to the new `.field-info-icon` button so existing tests continue passing. Document inline for each affected test.
- **`.field-info-icon` tooltip text in `title=` attribute**: browser-default tooltip rendering varies (delay before display, no styling). MCP-editor precedent uses `title=` (cycle-1 reviewer confirmed via grep at `mcp-server-editor.js:790-795`); L3 mirrors this. The L5 sweep can flag tooltip-styling as a future-UX-mission item if browser-default styling reads as low-polish.
- **The L2 file-header doc-comment** was just updated. L3 updates it again — careful not to lose the L2 update (re-read the post-L2 state first).
- **The Runtime Config section-title "Runtime Config"**: if visual rhythm reads cleaner as just "Configuration" or "Discord configuration" or no section title at all (since type-context is clear from the parent editor), L5 sweep may suggest a change. L3 uses "Runtime Config" per flight Design Decision; L5 sweep reconsiders if needed.

## Files Affected

- `the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js` — `renderConnectionFields` emptied; new `renderRuntimeConfigFields` added; registry export grows the new hook; verbose `<small class="form-hint">` blocks in runtime-config replaced with `.field-info-icon` tooltips; Guilds label rewritten to "Servers (optional)".
- `the_one/interfaces/web/static/js/areas/studio/connector-form-registry.js` — `optionalFns` array grows `'renderRuntimeConfigFields'`; validation comment block documents the new hook.
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — `runtimeConfigHtml` build path added; Access-and-Routing tab mount sequence includes new section between Lifecycle and Allowlist; file-header doc-comment updated; Auto-relay label rewritten + tooltip; Lifecycle `<small>` blocks replaced with tooltips.
- `the_one/agents.md` — Connector subsystem doc grows a paragraph about `renderRuntimeConfigFields`.
- `tests/browser/test_flow_studio_connector_discord_form.py` — ~6 tests get a tab-click inserted before runtime-config interactions (cycle-1 enumerated; see Edge Cases).
- Optionally `the_one/interfaces/web/static/css/studio.css` IF `.field-info-icon` spacing next to labels needs ~3 LOC.
- `missions/11-discord-connector-depth/flights/05-connector-ux-cleanup/flight.md` — L3 checkpoint + L3 leg checklist item checked off.
- `missions/11-discord-connector-depth/flights/05-connector-ux-cleanup/flight-log.md` — L3 leg-progress entry appended.
- `missions/11-discord-connector-depth/flights/05-connector-ux-cleanup/legs/03-move-runtime-config-and-relabel.md` — this artifact's status header updated through the lifecycle.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified (grep checks pass; Chrome MCP visual verification confirms; persistence round-trip works; browser tests pass)
- [x] `docker exec the-one pytest tests/browser/test_flow_studio_connector_account_editor.py tests/browser/test_flow_studio_connector_discord_form.py tests/browser/test_flow_studio_connector_discord_vocabulary.py tests/browser/test_flow_studio_connector_account_create_and_test.py tests/browser/test_flow_studio_connector_directive_section.py -m browser -x --timeout 60` passes
- [x] Update `flight-log.md` with L3 leg-progress entry
- [x] Set this leg's status to `landed`
- [x] Check off L3 in `flight.md` (Checkpoints + Legs sections)
- [x] Do NOT commit (F5 batches review + commit at flight end per the agentic-workflow protocol)

---

## Citation Audit

All code-location citations in this leg artifact verified against current code at leg design time (2026-05-23, post-L2):

- `connector-form-discord.js:163` — `renderConnectionFields(account, isCreate)` confirmed.
- `connector-form-discord.js:385` — `renderInviteSection` confirmed (post-L2 returns wrapper-less content).
- `connector-form-discord.js:438` — `renderDirectiveSection` confirmed.
- `connector-form-discord.js:720-728` — registry export object confirmed.
- `connector-form-registry.js:88-153` — validation logic + optionalFns array + comment block confirmed.
- `connector-form-registry.js:138-144` — `optionalFns = ['snapshot', 'wireEvents', 'renderInviteSection', 'renderDirectiveSection', 'renderDiscoverableDropdown']` confirmed.
- `connector-account-editor.js:316-330` — Connection section (post-L2: hosts Test Connection + Invite footer-rows) confirmed.
- `connector-account-editor.js:5-11` — file-header doc-comment (post-L2 update) confirmed.
- `fields-section.js:18-24` — `field-info-icon` SVG markup confirmed (the canonical primitive shape).
- `components.css:226` — `.field-info-icon` rule confirmed.
- `mcp-server-editor.js:792` — citation deferred to implementation-time grep (just need confirmation of the title-attribute-vs-aria-describedby mechanism).
- Access-and-Routing tab mount sequence + lifecycle build line ranges — implementation-time grep for current post-L2 lines (legacy citations were pre-L2; safe to grep at L3 implementation time).

11 confirmed sites + 2 implementation-time grep targets. No drift repaired since L1 + L2 commits already settled the post-L2 state; L3 citations are post-L2 and current.
