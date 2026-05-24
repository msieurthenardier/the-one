# Leg: directive-studio-surface

**Status**: landed
**Flight**: [Pool-Keying Refactor + Per-Account System-Prompt Directive Surface](../flight.md)

## Objective

Land the Studio UI half of the per-account system-prompt directive surface: register a NEW optional `renderDirectiveSection(account)` hook on the connector-form-registry, mount the section on the Discord connector's General tab (edit-mode only, between Pairing and Test Connection), render a textarea + three read-only `<details>` disclosures showing the verbatim hardcoded defaults from `agent/config.py`, wire dirty-tracking via the existing `wireEvents` + `snapshot` + `collect` hooks, declare `system_prompt_directive` in the entry's `reservedConfigKeys` so it doesn't appear in the Advanced kv-table, AND bundle two F1-debrief polish items that share this Studio surface: lift `MASKED_SENTINEL` to a shared `window.App.studio.MASKED_SENTINEL` constant and replace `_resolveAccountFromContainer` hash-parse with a `data-account-id` attribute on the editor's mount node.

## Context

- **Why now**: F2 flight spec Design Decisions §3 specifies the Studio surface shape end-to-end (Path B registry-mediated; General tab between Pairing and Test Connection; textarea + 3 read-only disclosures; "(this account's current)" annotation reacts to auto-relay checkbox; dirty-tracker via the existing entry hooks). L3 shipped the substrate; L4 connects it to the operator.
- **Bundled polish** (per F1 debrief Action Items + F2 flight Design Decisions §6): `MASKED_SENTINEL` is duplicated across `connector-account-editor.js` and `connector-form-discord.js`; `_resolveAccountFromContainer` parses `window.location.hash` because the editor's mount node has no `data-account-id`. L4 lifts the constant + removes the hash-parse — these touch the same Studio surface L4 already opens.
- **Conventions applied**:
  - `optional-registry-entry-hook` (L1-codified F2): `renderDirectiveSection` is the 4th optional entry hook; extends the registry's `optionalFns` array additively.
  - `registry-dispatch-create-mode-AC` (L1-codified F2): the directive section is edit-mode-only; the AC verifies that F1 L7's type-pick re-mount path (create mode → operator picks Discord → re-mount with stub account) traverses the new directive render code WITHOUT crashing. In create mode, the consult returns no section; no exception.
  - `mechanical-fallback-prompt-truth-pairing` (L1-codified F1): the textarea is APPEND-mode only (substrate enforced by L3 — operator cannot replace the default); the UI shows the operator exactly which default fires + what their text composes with via the three read-only disclosures.

### Design Decisions (L4-internal)

- **Section placement on General tab**: immediately after Pairing, before Attached Agents. The F2 flight Design Decisions §3 wording "between Pairing and Test Connection" predates this leg's audit; the current DOM order is Connection → Credentials → Pairing → Attached Agents → Test Connection → Invite → Danger Zone, and the directive section lands between the operator-config sections (Pairing) and the read-only/diagnostic sections (Attached Agents / Test Connection / Invite). Post-L4: Connection → Credentials → Pairing → **Directive** → Attached Agents → Test Connection → Invite → Danger Zone.

- **Textarea shape**: single `<textarea>` element; rows="6" (~150-200px tall — enough to compose 2-3 sentences without dominating the editor); fills the section width. `data-field="system-prompt-directive"`, `data-testid="connector-account-system-prompt-directive"`, `placeholder="(leave empty for no override)"`. Help text below: `"Your text is appended to whichever default fires for this account's current state. Empty = no override."`

- **Three `<details>` disclosures**: one per `(connector_attached, send_tool_enabled, auto_relay)` state-triple's default constant. Order: auto-relay-ON (the daily-driver default) → auto-relay-OFF-tool-enabled → tool-disabled. Each disclosure's `<summary>` carries a state label, and the disclosure for the account's CURRENTLY-ACTIVE state (per `auto_relay_platform_replies` value; default True) gets an annotation `"(this account's current)"`.
  - Summary labels (verbatim, must match for byte-stable test selectors):
    - `"When auto-relay is ON"` (auto-relay default; account's `auto_relay_platform_replies` is True or absent)
    - `"When auto-relay is OFF and platform-send tool is enabled"` (the F8-L11-Fix-4 opt-out path)
    - `"When the platform-send tool is disabled"` (tool disabled for this agent)
  - The CURRENT-state summary appends `" (this account's current)"`.
  - The defaults are rendered inside each disclosure as a `<pre><code>` block carrying the VERBATIM text of `agent/config.py:_CONNECTOR_AUTO_RELAY_DIRECTIVE / _CONNECTOR_TOOL_ENABLED_DIRECTIVE / _CONNECTOR_TOOL_DISABLED_DIRECTIVE` respectively. **Implementation reads these constants over the wire** via a new readonly API endpoint (see Design Decision §3 below) OR inlines them as constants in `connector-form-discord.js` IF the values are stable enough to duplicate. **Choice**: inline as JS module-level constants. Rationale: (a) the strings are stable — operator never edits them; (b) round-trip API call to fetch them adds startup latency for zero functional benefit; (c) a future flight that changes the hardcoded defaults can update both Python and JS in the same diff (atomic-leg-pattern enforces this). The verbatim equality is pinned by a new browser test that grep-asserts the JS constants match the Python constants.
  - All three disclosures start CLOSED. Operator clicks to expand.

- **Tool-disabled state — UI only reflects, never controls**: the third disclosure label ("When the platform-send tool is disabled") describes an AGENT-level setting (the per-agent `disabled_tools` list), NOT a connector-account setting. The connector-account editor doesn't control this. The disclosure is shown for completeness — the operator authoring the directive needs to know the disabled-state default exists so their appended text composes sensibly with it. The "(this account's current)" annotation can NEVER land on this disclosure from the account editor (the editor has no agent context). Operators wanting to test the tool-disabled state preview do so by attaching the account to an agent + toggling the agent's tool config. Acceptable — L4 is intentionally connector-account-scoped.

- **Annotation reactivity to auto-relay toggle**: the auto-relay checkbox lives in the Lifecycle section (`data-field="auto_relay_platform_replies"`). Toggling it (a) flips the account's per-config value (on save), (b) MUST trigger a live repaint of the "(this account's current)" annotation. Wire via the entry's `wireEvents(container, checkDirty, account)` 3-arg hook (F1 L5 extension): attach a `change` listener on the auto-relay checkbox that calls a private `_updateDirectiveAnnotation(container)` helper. Pure DOM mutation; no save needed for the annotation to repaint.

- **Reserved-key declaration**: the Discord entry's `reservedConfigKeys` currently contains `['intents', 'guilds', 'presence']` (per F1 L4). L4 adds `'system_prompt_directive'` → `['intents', 'guilds', 'presence', 'system_prompt_directive']`. The substrate's `collectConfigRows` and `renderConfigKvTable` composition hides this key from the Advanced kv-table on Discord accounts (per F1 L3's effective-reserved-keys composition).

- **`collect` extension** (emit-on-non-empty, omit-on-empty):
  - Read the textarea's value via `container.querySelector('[data-field="system-prompt-directive"]')`.
  - Trim leading/trailing whitespace per UI convention (operator-typed text shouldn't carry incidental whitespace into the persisted config).
  - If trimmed value is non-empty → `config.system_prompt_directive = <trimmed>`.
  - If trimmed value is empty → OMIT the key entirely. (L3's API validator rejects empty strings; emit-and-reject would be a UX bug. Omit avoids the trip.)
  - On save, the substrate's `collectFormData` stitches `config` from the entry's collect hook with the substrate's pairing/allowlist/routing/auto_relay_platform_replies merge — the directive key flows through cleanly.

- **`snapshot` extension**:
  - Add `systemPromptDirective: <textarea.value>` to the returned object. Raw value (not trimmed) for snapshot symmetry with the secrets-row pattern. The dirty-tracker JSON-stringifies the snapshot; any non-trivial change to the textarea fires `checkDirty`.

- **`MASKED_SENTINEL` lift** (bundled): currently declared in TWO places (`connector-account-editor.js:MASKED_SENTINEL` + `connector-form-discord.js:MASKED_SENTINEL`). L4 lifts to `window.App.studio.MASKED_SENTINEL = '__MASKED__'` set in `connector-form-registry.js` (earliest-loading studio module that survives across all editor lifecycles). Both editor + form-discord modules read from the shared constant. Deletes the two duplicate `var MASKED_SENTINEL = '__MASKED__'` declarations.

- **`data-account-id` attribute** (bundled): the editor's mount node currently has no account ID exposed in the DOM. `connector-form-discord.js:_resolveAccountFromContainer` parses `window.location.hash` to recover it. L4: set `data-account-id="<account.id>"` on the `.connector-account-editor` mount node at render time (only in edit mode — create mode has no account.id). Replace `_resolveAccountFromContainer` body with `return container.closest('.connector-account-editor')?.getAttribute('data-account-id') || null` (or `container.querySelector('[data-account-id]')?.getAttribute('data-account-id')` depending on the container shape). The hash-parse logic is deleted entirely (the helper's existing function name is preserved for L5 callers that already use it; only the body changes).

- **Render `account.config.system_prompt_directive` value into the textarea on edit-mode mount**: the textarea's `value` attribute is set from `account.config.system_prompt_directive` (default empty string if absent). Edit-mode round-trip works: save → reload editor → see the persisted directive in the textarea.

## Inputs

Files that must exist:

**Production source**:
- `the_one/interfaces/web/static/js/areas/studio/connector-form-registry.js` (L4 extends the `optionalFns` array at line 92 with `'renderDirectiveSection'`; also adds the `MASKED_SENTINEL` lift constant at module-load time)
- `the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js` (extends entry with `renderDirectiveSection` function + extends `collect`, `snapshot`, `wireEvents` + extends `reservedConfigKeys`; replaces `_resolveAccountFromContainer` body; reads `MASKED_SENTINEL` from `window.App.studio` instead of declaring locally)
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` (adds the directive section mount between Pairing and Test Connection in the General tab assembly; adds `data-account-id` attribute on the `.connector-account-editor` mount node in edit mode; reads `MASKED_SENTINEL` from `window.App.studio` instead of declaring locally)

**Tests**:
- `tests/browser/test_flow_studio_connector_directive_section.py` (NEW file — directive UI tests)
- Existing browser tests must pass UNMODIFIED:
  - `tests/browser/test_flow_studio_connector_account_editor.py`
  - `tests/browser/test_flow_studio_connector_account_create_and_test.py`
  - `tests/browser/test_flow_studio_connector_account_navigation.py`
  - `tests/browser/test_flow_studio_connector_discord_form.py`
  - `tests/browser/test_flow_studio_connector_invite_section.py`
  - `tests/browser/test_flow_studio_connector_discord_vocabulary.py`
  - `tests/browser/test_connector_form_registry.py`

State that must be true:
- F2 L1, L2, L3 are `landed`
- F2 baseline (2814 from L3 ship) passes
- L3's `system_prompt_directive` config field is accepted by the API validator

## Outputs

State changes after this leg:

- **`connector-form-registry.js`**:
  - `optionalFns` array at line 92 extended: `['snapshot', 'wireEvents', 'renderInviteSection', 'renderDirectiveSection']`. Updated docstring comment block (lines 78-91) describes the new hook.
  - NEW: `window.App.studio.MASKED_SENTINEL = '__MASKED__'` set at module-load time (after the IIFE's existing namespace setup).

- **`connector-form-discord.js`** (~+120 LOC):
  - Module-level constants for the three hardcoded directive texts (verbatim copies of `agent/config.py:_CONNECTOR_AUTO_RELAY_DIRECTIVE`, `:_CONNECTOR_TOOL_ENABLED_DIRECTIVE`, `:_CONNECTOR_TOOL_DISABLED_DIRECTIVE`). New constants: `_DIRECTIVE_AUTO_RELAY_DEFAULT`, `_DIRECTIVE_TOOL_ENABLED_DEFAULT`, `_DIRECTIVE_TOOL_DISABLED_DEFAULT`. Each carries a code-comment naming the Python constant it mirrors so a future Python edit can grep-find the JS twin.
  - NEW function `renderDirectiveSection(account)`: returns the HTML for the section per Design Decisions §3 above. Edit-mode-only (caller guards with `!isCreate`; the function itself doesn't need a guard since it's only called from an edit-mode mount path).
  - NEW helper `_updateDirectiveAnnotation(container)`: pure DOM mutation; reads the auto-relay checkbox's checked state; finds the three disclosure `<summary>` elements by `data-testid="directive-default-<state>"` and updates each one's annotation text.
  - `collect` extended: reads the textarea by `[data-field="system-prompt-directive"]`; trims; emits `config.system_prompt_directive` when non-empty; omits when empty.
  - `snapshot` extended: adds `systemPromptDirective: <textarea.value>` to the returned object.
  - `wireEvents` extended: attaches `input` listener on the directive textarea (calls `checkDirty`); attaches `change` listener on the auto-relay checkbox (calls `_updateDirectiveAnnotation` then `checkDirty`).
  - `reservedConfigKeys` extended: `['intents', 'guilds', 'presence', 'system_prompt_directive']`.
  - `_resolveAccountFromContainer` body replaced: reads `container.closest('.connector-account-editor')?.getAttribute('data-account-id')` instead of parsing `window.location.hash`. Function name preserved.
  - Local `var MASKED_SENTINEL = '__MASKED__'` declaration DELETED; code references `window.App.studio.MASKED_SENTINEL` instead.
  - Register call extended: `renderDirectiveSection: renderDirectiveSection` added to the entry-shape object.

- **`connector-account-editor.js`**:
  - Edit-mode mount adds `data-account-id="<account.id>"` attribute to the root `.connector-account-editor` element. Create mode adds no attribute (no account.id yet).
  - General tab HTML assembly (lines 478-487) adds a new `directiveHtml` block parallel to `inviteHtml`. Placement: BETWEEN `pairingHtml` and `attachedAgentsHtml` per Design Decisions §1. Registry-mediated mount: `var directiveEntry = inviteRegistry.get(account.type); if (directiveEntry && typeof directiveEntry.renderDirectiveSection === 'function') { directiveHtml = directiveEntry.renderDirectiveSection(account); }`.
  - Local `var MASKED_SENTINEL = '__MASKED__'` declaration DELETED; code references `window.App.studio.MASKED_SENTINEL` instead.

- **NEW: `tests/browser/test_flow_studio_connector_directive_section.py`** (~150 LOC):
  - `test_directive_section_renders_on_discord_general_tab` — section visible in DOM, between Pairing and Attached Agents (selector ordering check).
  - `test_directive_textarea_renders_with_persisted_value` — seed account with `config.system_prompt_directive = "Sign replies with a coffee emoji."` → editor renders textarea pre-filled.
  - `test_three_default_disclosures_render_verbatim_python_text` — assert each disclosure's `<pre><code>` content matches the verbatim Python constant from `agent/config.py` (fetched via HTTP GET to a known-stable endpoint or inlined as Python-side fixture; SEE NOTE BELOW).
  - `test_current_state_annotation_on_auto_relay_on_disclosure` — default account (auto_relay_platform_replies absent → True) shows "(this account's current)" on the auto-relay-ON summary.
  - `test_current_state_annotation_moves_on_auto_relay_toggle` — uncheck auto-relay checkbox in the editor; annotation moves to the auto-relay-OFF disclosure live (no save needed).
  - `test_directive_save_round_trip_emits_config_key` — type "Reply formally." → save → GET account → confirm `config.system_prompt_directive == "Reply formally."`.
  - `test_directive_save_omits_key_when_empty` — leave textarea empty → save → GET account → confirm `config.system_prompt_directive` is NOT in config (no empty-string noise).
  - `test_directive_section_absent_on_stub_account` — stub-type account has no directive section in DOM (`[data-testid="connector-account-directive-section"]` count is 0).
  - `test_directive_key_hidden_from_advanced_kv_table` — Discord account with `config.system_prompt_directive = "X"` does NOT show this key as a kv-table row.
  - `test_data_account_id_attribute_set_in_edit_mode` — `.connector-account-editor` mount node has `data-account-id="<account.id>"` matching the seeded account.id.
  - `test_data_account_id_attribute_absent_in_create_mode` — create form's `.connector-account-editor` has no `data-account-id` attribute.
  - `test_masked_sentinel_global_constant` — `page.evaluate("window.App.studio.MASKED_SENTINEL")` returns `'__MASKED__'`.
  - `test_create_mode_type_pick_does_not_crash_with_directive` — create form → pick Discord → form re-mounts → no exception (registry-dispatch-create-mode-AC application).

  **NOTE on `test_three_default_disclosures_render_verbatim_python_text`**: the test needs to compare JS-side constants to Python-side constants. Two approaches: (a) use `page.evaluate` to read the JS constants, then read the Python constants from `agent/config.py` directly in the test fixture, byte-compare; (b) expose the Python constants via a read-only API endpoint and have the test fetch both. Approach (a) is simpler — the test imports the Python constants and asserts equality against `page.evaluate` output. Use (a).

## Acceptance Criteria

- [ ] `connector-form-registry.js` `optionalFns` extended with `'renderDirectiveSection'`; entry-shape validation accepts the new hook as optional (function-if-present).
- [ ] `connector-form-registry.js` sets `window.App.studio.MASKED_SENTINEL = '__MASKED__'` at module-load time.
- [ ] `connector-form-discord.js` defines `_DIRECTIVE_AUTO_RELAY_DEFAULT`, `_DIRECTIVE_TOOL_ENABLED_DEFAULT`, `_DIRECTIVE_TOOL_DISABLED_DEFAULT` constants whose string values are byte-identical to the verbatim Python constants at `agent/config.py:_CONNECTOR_AUTO_RELAY_DIRECTIVE`, `:_CONNECTOR_TOOL_ENABLED_DIRECTIVE`, `:_CONNECTOR_TOOL_DISABLED_DIRECTIVE`. Each carries a code-comment naming the Python twin.
- [ ] `renderDirectiveSection(account)` exists on the Discord entry, returns an HTML `<div class="editor-section connector-directive-section">` with: section title; textarea with the persisted value pre-filled + help text; three `<details>` disclosures with verbatim default text inside `<pre><code>` blocks.
- [ ] Disclosure summaries use the verbatim labels from Design Decisions §3; current-state annotation `" (this account's current)"` appears on the auto-relay-ON summary by default (account's `auto_relay_platform_replies` is True or absent).
- [ ] Toggling the auto-relay checkbox repaints the annotation live onto the auto-relay-OFF summary; toggling back moves it back. No save required.
- [ ] `collect` emits `config.system_prompt_directive = <trimmed-textarea>` when non-empty; OMITS the key when empty. Round-trip verified: type → save → GET → confirm persisted shape.
- [ ] `snapshot` adds `systemPromptDirective` to the returned object; dirty-tracker fires on any textarea edit.
- [ ] `wireEvents` attaches: (a) `input` listener on the directive textarea → `checkDirty`; (b) `change` listener on the auto-relay checkbox → `_updateDirectiveAnnotation` + `checkDirty`. The auto-relay listener does NOT conflict with the substrate's existing `change` listener on the same element — both fire independently.
- [ ] `reservedConfigKeys` includes `'system_prompt_directive'`; the key does NOT appear as a row in the Advanced kv-table on Discord accounts.
- [ ] `connector-account-editor.js` General tab assembly mounts the directive section BETWEEN `pairingHtml` and `attachedAgentsHtml`; create mode renders no directive section.
- [ ] `.connector-account-editor` root element has `data-account-id="<account.id>"` attribute in edit mode; no attribute in create mode.
- [ ] `_resolveAccountFromContainer` body replaced with `data-account-id` read; the function returns the same account.id strings it returned pre-L4 (verified by L5's invite section still working post-L4).
- [ ] Both `var MASKED_SENTINEL = '__MASKED__'` declarations DELETED; code reads `window.App.studio.MASKED_SENTINEL` instead.
- [ ] Existing browser tests pass UNMODIFIED — 7 test files listed in Inputs all green.
- [ ] New `test_flow_studio_connector_directive_section.py` adds ~13 test cases; all pass.
- [ ] Full suite at or above F2 L3's 2814 baseline + new tests.
- [ ] `registry-dispatch-create-mode-AC` (L1-codified F2) applied: create-mode-pick-Discord re-mount does NOT crash when traversing the new directive render code (consult returns no section since create mode renders no directive surface).

## Verification Steps

- `grep -n "renderDirectiveSection" the_one/interfaces/web/static/js/areas/studio/connector-form-registry.js the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — ≥4 hits (optionalFns entry + function definition + register-call entry + editor mount lookup).
- `grep -n "system_prompt_directive\|systemPromptDirective" the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js` — ≥5 hits (reservedConfigKeys + collect + snapshot + textarea data-field + helper references).
- `grep -n "window.App.studio.MASKED_SENTINEL" the_one/interfaces/web/static/js/areas/studio/connector-form-registry.js the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — ≥3 hits.
- `grep -n "var MASKED_SENTINEL" the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — ZERO hits (the local declarations are deleted).
- `grep -n "data-account-id" the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — ≥1 hit (the mount node attribute).
- `grep -n "window.location.hash" the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js` — ZERO hits (the hash-parse is deleted from `_resolveAccountFromContainer`).
- `docker exec the-one pytest -x --timeout 60 -m browser tests/browser/test_flow_studio_connector_account_editor.py tests/browser/test_flow_studio_connector_account_create_and_test.py tests/browser/test_flow_studio_connector_account_navigation.py tests/browser/test_flow_studio_connector_discord_form.py tests/browser/test_flow_studio_connector_invite_section.py tests/browser/test_flow_studio_connector_discord_vocabulary.py tests/browser/test_connector_form_registry.py tests/browser/test_flow_studio_connector_directive_section.py` — all 8 files pass.
- `docker exec the-one pytest -x --timeout 30 -q -m "not pixel"` — full suite at or above F2 L3's 2814 baseline + ~13 new tests.

## Implementation Guidance

1. **Read the surface end-to-end**:
   - `connector-form-registry.js:_validateEntry` + `optionalFns` array (line 92) — pattern for adding the 4th optional hook
   - `connector-form-discord.js` — current entry shape; pay attention to `collect`, `snapshot`, `wireEvents`, `renderInviteSection`, `_resolveAccountFromContainer`, `MASKED_SENTINEL` declaration
   - `connector-account-editor.js:renderConnectorAccountEditor` General tab assembly (lines 478-487) — pattern the L4 directive mount mirrors; pay attention to where `MASKED_SENTINEL` is currently declared (line 47) + the `.connector-account-editor` mount class
   - `agent/config.py:_CONNECTOR_AUTO_RELAY_DIRECTIVE` / `:_CONNECTOR_TOOL_ENABLED_DIRECTIVE` / `:_CONNECTOR_TOOL_DISABLED_DIRECTIVE` — copy the verbatim text into JS module-level constants

2. **Extend the registry's `optionalFns`**: add `'renderDirectiveSection'` to the array at `connector-form-registry.js:92`. Update the docstring comment block (lines 78-91) to describe the new hook briefly.

3. **Add the `MASKED_SENTINEL` lift to `connector-form-registry.js`**: at the bottom of the IIFE (after the existing `window.App.studio.connectorFormRegistry = { register, get };` line), add `window.App.studio.MASKED_SENTINEL = '__MASKED__';`. This module is the earliest-loading studio module that defines `App.studio`; the constant survives across all editor lifecycles.

4. **Implement `renderDirectiveSection(account)` in `connector-form-discord.js`**:
   - Add the three module-level constants `_DIRECTIVE_AUTO_RELAY_DEFAULT`, `_DIRECTIVE_TOOL_ENABLED_DEFAULT`, `_DIRECTIVE_TOOL_DISABLED_DEFAULT` (verbatim Python text copies). Each preceded by a comment block naming the Python twin and the agent/config.py symbol.
   - Implement `renderDirectiveSection(account)`. Skeleton — note: uses `<section>` (matches `renderInviteSection`'s precedent) and `textContent`-equivalent escaping discipline (summary text gets the apostrophe via post-render mutation OR initial render — both use the same shape so initial-render vs post-toggle text matches byte-for-byte):
     ```javascript
     function renderDirectiveSection(account) {
       var escapeHtml = window.App.escapeHtml;
       var escapeAttr = window.App.escapeAttr;
       var existingDirective = (account && account.config && account.config.system_prompt_directive) || '';
       var autoRelay = !(account && account.config && account.config.auto_relay_platform_replies === false);
       
       var html = '<section class="editor-section connector-directive-section" data-testid="connector-account-directive-section">';
       html += '<div class="section-title">SYSTEM PROMPT DIRECTIVE</div>';
       
       html += '<textarea data-field="system-prompt-directive" data-testid="connector-account-system-prompt-directive" rows="6" placeholder="(leave empty for no override)">' +
               escapeHtml(existingDirective) + '</textarea>';
       html += '<small class="form-hint">Your text is appended to whichever default fires for this account\'s current state. Empty = no override.</small>';
       
       // Three disclosures. Summaries are rendered with EMPTY content here;
       // _updateDirectiveAnnotation is called once at mount-time to set the
       // initial textContent, guaranteeing byte-identical text between
       // initial render and post-auto-relay-toggle re-render (single code
       // path — no escapeHtml-vs-textContent asymmetry).
       html += _renderDirectiveDisclosure('auto-relay-on', _DIRECTIVE_AUTO_RELAY_DEFAULT);
       html += _renderDirectiveDisclosure('auto-relay-off', _DIRECTIVE_TOOL_ENABLED_DEFAULT);
       html += _renderDirectiveDisclosure('tool-disabled', _DIRECTIVE_TOOL_DISABLED_DEFAULT);
       
       html += '</section>';
       return html;
     }
     
     function _renderDirectiveDisclosure(stateKey, defaultText) {
       var escapeHtml = window.App.escapeHtml;
       var html = '<details class="connector-directive-disclosure" data-state-key="' + stateKey + '">';
       // Summary text intentionally empty here — initialized by
       // _updateDirectiveAnnotation post-mount via textContent.
       html += '<summary data-testid="directive-default-' + stateKey + '-summary"></summary>';
       html += '<pre><code data-testid="directive-default-' + stateKey + '-text">' +
               escapeHtml(defaultText) + '</code></pre>';
       html += '</details>';
       return html;
     }
     ```
   - Call `_updateDirectiveAnnotation(container)` once at the entry's `wireEvents` invocation so summaries are populated on mount before any user interaction (the summary `textContent` is the same code path used on subsequent auto-relay toggles).

5. **Implement `_updateDirectiveAnnotation(container)`** — this is the SOLE writer of disclosure-summary textContent (initial mount + every auto-relay toggle). Pure DOM mutation using `textContent` for byte-stable summary text:
   ```javascript
   function _updateDirectiveAnnotation(container) {
     var autoRelayEl = container.querySelector('[data-field="auto_relay_platform_replies"]');
     // Default to autoRelay=true when checkbox isn't found (matches
     // account.config.auto_relay_platform_replies absent → True).
     var autoRelay = autoRelayEl ? !!autoRelayEl.checked : true;
     
     var onSummary = container.querySelector('[data-testid="directive-default-auto-relay-on-summary"]');
     var offSummary = container.querySelector('[data-testid="directive-default-auto-relay-off-summary"]');
     var disabledSummary = container.querySelector('[data-testid="directive-default-tool-disabled-summary"]');
     
     if (onSummary) onSummary.textContent = autoRelay
       ? 'When auto-relay is ON (this account\'s current)'
       : 'When auto-relay is ON';
     if (offSummary) offSummary.textContent = autoRelay
       ? 'When auto-relay is OFF and platform-send tool is enabled'
       : 'When auto-relay is OFF and platform-send tool is enabled (this account\'s current)';
     // tool-disabled never current from the account editor
     if (disabledSummary) disabledSummary.textContent = 'When the platform-send tool is disabled';
   }
   ```

6. **Extend `collect`**:
   ```javascript
   // In the existing collect() function, add after the presence handling:
   var directiveEl = container.querySelector('[data-field="system-prompt-directive"]');
   if (directiveEl) {
     var directiveValue = (directiveEl.value || '').trim();
     if (directiveValue) {
       config.system_prompt_directive = directiveValue;
     }
     // Empty → omit the key entirely (L3 validator rejects empty strings).
   }
   ```

7. **Extend `snapshot`**:
   ```javascript
   // In the existing snapshot() function, add to the returned object:
   var directiveEl = container.querySelector('[data-field="system-prompt-directive"]');
   var systemPromptDirective = directiveEl ? directiveEl.value : '';
   return {
     // ... existing snapshot fields ...
     systemPromptDirective: systemPromptDirective
   };
   ```

8. **Extend `wireEvents`**:
   ```javascript
   // In the existing wireEvents(container, checkDirty, account) function, add:
   // (a) initial population of disclosure summaries (one call at mount time;
   //     same code path as the auto-relay change handler — byte-stable text):
   _updateDirectiveAnnotation(container);
   
   // (b) directive textarea input → dirty tracker
   var directiveEl = container.querySelector('[data-field="system-prompt-directive"]');
   if (directiveEl) {
     directiveEl.addEventListener('input', checkDirty);
   }
   
   // (c) auto-relay change → repaint annotation + dirty tracker. The
   //     substrate's existing change listener at attachStaticListeners
   //     also fires (calls checkDirty); both are additive — no conflict.
   var autoRelayEl = container.querySelector('[data-field="auto_relay_platform_replies"]');
   if (autoRelayEl) {
     autoRelayEl.addEventListener('change', function () {
       _updateDirectiveAnnotation(container);
       // checkDirty fires from substrate's listener too; idempotent.
     });
   }
   ```

9. **Extend `reservedConfigKeys`** in the `register` call:
   ```javascript
   reservedConfigKeys: ['intents', 'guilds', 'presence', 'system_prompt_directive'],
   ```

10. **Extend the entry's `register` call** with `renderDirectiveSection`:
    ```javascript
    window.App.studio.connectorFormRegistry.register('discord', {
      // ... existing fields ...
      renderDirectiveSection: renderDirectiveSection
    });
    ```

11. **Replace `_resolveAccountFromContainer` body**:
    ```javascript
    function _resolveAccountFromContainer(container) {
      // M11 F2 L4: read the data-account-id attribute set by the editor's
      // mount path instead of parsing window.location.hash. The mount node
      // is the .connector-account-editor element (or container itself if
      // container IS that element).
      var mountEl = container.closest('.connector-account-editor');
      if (!mountEl) mountEl = container;  // fallback: container may itself be the mount
      var accountId = mountEl.getAttribute('data-account-id');
      return accountId;
    }
    ```

12. **Delete the local `MASKED_SENTINEL` declarations**: in both `connector-form-discord.js` and `connector-account-editor.js`, delete the `var MASKED_SENTINEL = '__MASKED__';` line. Replace every use site of `MASKED_SENTINEL` with `window.App.studio.MASKED_SENTINEL`.

13. **Set `data-account-id` on the editor mount node**: in `connector-account-editor.js:renderConnectorAccountEditor`, find the `<div class="connector-account-editor">` opening tag and add `data-account-id="<escapeAttr(account.id || '')>"` to it in edit mode only. Create mode adds NO attribute (account.id doesn't exist yet).

14. **Mount the directive section in the General tab**: in `connector-account-editor.js`, add a `directiveHtml` variable parallel to `inviteHtml` (around line 425-432). Insert into the General tab assembly between `pairingHtml` and `attachedAgentsHtml`:
    ```javascript
    var directiveHtml = '';
    if (!isCreate) {
      var directiveRegistry = (window.App && window.App.studio && window.App.studio.connectorFormRegistry) || null;
      var directiveEntry = (directiveRegistry && account && account.type) ? directiveRegistry.get(account.type) : undefined;
      if (directiveEntry && typeof directiveEntry.renderDirectiveSection === 'function') {
        directiveHtml = directiveEntry.renderDirectiveSection(account);
      }
    }
    
    // ... in the General tab assembly:
    html += connectionHtml;
    html += credentialsHtml;
    html += pairingHtml;
    html += directiveHtml;  // NEW — between Pairing and Attached Agents
    html += attachedAgentsHtml;
    html += testConnectionHtml;
    html += inviteHtml;
    html += dangerZoneHtml;
    ```

15. **Write the browser tests** in `tests/browser/test_flow_studio_connector_directive_section.py`. Use the existing `tests/browser/test_flow_studio_connector_invite_section.py` as a template (similar registry-mediated section + Playwright probe pattern). For the verbatim-text-comparison test, import the Python constants:
    ```python
    from the_one.agent.config import (
        _CONNECTOR_AUTO_RELAY_DIRECTIVE,
        _CONNECTOR_TOOL_ENABLED_DIRECTIVE,
        _CONNECTOR_TOOL_DISABLED_DIRECTIVE,
    )
    
    def test_three_default_disclosures_render_verbatim_python_text(page, dev_app, seeded_discord_account):
        page.goto(f"{dev_app.url}/#studio/connectors/{seeded_discord_account.id}")
        # Read the JS-side disclosure text via the data-testid selectors
        on_text = page.locator('[data-testid="directive-default-auto-relay-on-text"]').text_content()
        off_text = page.locator('[data-testid="directive-default-auto-relay-off-text"]').text_content()
        disabled_text = page.locator('[data-testid="directive-default-tool-disabled-text"]').text_content()
        assert on_text == _CONNECTOR_AUTO_RELAY_DIRECTIVE
        assert off_text == _CONNECTOR_TOOL_ENABLED_DIRECTIVE
        assert disabled_text == _CONNECTOR_TOOL_DISABLED_DIRECTIVE
    ```

16. **Run tests in order**:
    - `docker exec the-one pytest -x --timeout 60 -m browser tests/browser/test_flow_studio_connector_directive_section.py` — new tests first
    - `docker exec the-one pytest -x --timeout 60 -m browser tests/browser/` — all browser tests (any existing test that touched MASKED_SENTINEL or `_resolveAccountFromContainer` indirectly should still pass; especially L5's invite tests which call `_resolveAccountFromContainer`)
    - `docker exec the-one pytest -x --timeout 30 -q -m "not pixel"` — full suite final check

## Edge Cases

- **Verbatim text drift between JS constants and Python constants**: a future flight could edit `agent/config.py:_CONNECTOR_AUTO_RELAY_DIRECTIVE` without updating the JS twin. The test `test_three_default_disclosures_render_verbatim_python_text` catches this — the JS textContent must match the Python string verbatim. If the test fails post-Python-edit, the implementer of that edit MUST also update the JS constants.
- **Create mode + auto-relay toggle interaction**: in create mode, the directive section doesn't render. The auto-relay checkbox change still fires (the listener at `_updateDirectiveAnnotation` runs), but the disclosure summaries don't exist → `querySelector` returns null → the helper's `if (onSummary)` / `if (offSummary)` guards make it a no-op. No exception.
- **Stub account in edit mode**: registry lookup returns `undefined` → `directiveHtml = ''`. No directive section in DOM. Matches `'stub'`-type fallback contract (registry-mediated mount on a non-Discord type produces no section).
- **Account with `system_prompt_directive` already set, operator clears the textarea**: `collect` omits the key when empty. PUT payload's config DOES NOT include `system_prompt_directive`. Backend semantics: a missing key in the config-merge path means the existing key is OVERWRITTEN to absent. (Verify at impl time — check the PUT handler's config-merge shape. If the merge layer treats `config` as a complete replacement, this works. If it treats omitted keys as "preserve existing," the operator's clear is silently ignored and the directive lingers — that'd be a bug requiring a different `collect` shape.)
- **`data-account-id` and the F1 L7 re-mount path**: when picking Discord in create mode triggers re-mount, the re-mount happens with a stub `{name, type, config:{}, secrets:{}}` — no `id`. The `data-account-id` attribute is NOT added (still in create mode logically; F1 L7 fix kept `isCreate=true` for the re-mount). After the operator saves, the editor re-mounts in edit mode with `account.id` populated → `data-account-id` appears. Test `test_data_account_id_attribute_absent_in_create_mode` covers this.

## Files Affected

**Production source**:
- `the_one/interfaces/web/static/js/areas/studio/connector-form-registry.js` — `optionalFns` extended + `MASKED_SENTINEL` lift constant
- `the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js` — 3 directive-default constants + `renderDirectiveSection` + `_updateDirectiveAnnotation` + collect/snapshot/wireEvents/reservedConfigKeys extensions + `_resolveAccountFromContainer` body replacement + local MASKED_SENTINEL deletion + register-call entry
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — directive section mount in General tab + `data-account-id` attribute on mount node + local MASKED_SENTINEL deletion

**Tests**:
- `tests/browser/test_flow_studio_connector_directive_section.py` — NEW (~150 LOC, ~13 test cases)

**Flight artifacts**:
- `missions/11-discord-connector-depth/flights/02-pool-keying-and-directive-surface/flight-log.md` — Leg Progress entry
- `missions/11-discord-connector-depth/flights/02-pool-keying-and-directive-surface/legs/04-directive-studio-surface.md` — status transitions

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] All 7 existing browser test files pass UNMODIFIED
- [ ] New `test_flow_studio_connector_directive_section.py` passes (~13 tests)
- [ ] Full suite at or above F2 L3's 2814 baseline + new tests
- [ ] `grep "var MASKED_SENTINEL" the_one/interfaces/web/static/js/` returns ZERO hits
- [ ] `grep "window.location.hash" the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js` returns ZERO hits
- [ ] `_resolveAccountFromContainer` returns the same values pre/post-L4 (L5 invite tests still pass)
- [ ] Update flight-log.md with Leg Progress entry
- [ ] Set this leg's status to `landed`
- [ ] Do NOT check off the leg in flight.md
- [ ] Do NOT commit

## Citation Audit

Citations verified at leg design time (2026-05-21, post-L3):

- `connector-form-registry.js:_validateEntry` + `optionalFns` array — verified at line 92; current shape `['snapshot', 'wireEvents', 'renderInviteSection']`. L4 extends to add `'renderDirectiveSection'`.
- `connector-form-registry.js` IIFE export — verified at lines 110-115 (approximate); namespace setup at the top. L4 adds `window.App.studio.MASKED_SENTINEL` set at the bottom.
- `connector-form-discord.js:_DISCORD_INVITE_PERMISSIONS` constant + `renderInviteSection` + `wireEvents(container, checkDirty, account)` 3-arg + `_resolveAccountFromContainer` + `register` call — verified at L4 design time; line numbers will drift but symbolic anchors stable.
- `connector-form-discord.js:MASKED_SENTINEL` local declaration — verified at line 38 (`var MASKED_SENTINEL = '__MASKED__'`).
- `connector-account-editor.js:MASKED_SENTINEL` local declaration — verified at line 47.
- `connector-account-editor.js:renderConnectorAccountEditor` General tab assembly — verified at lines 478-487 in current shape; `pairingHtml`, `inviteHtml`, `attachedAgentsHtml`, `testConnectionHtml`, `dangerZoneHtml` all named.
- `connector-account-editor.js` `.connector-account-editor` mount class — verified as the root element class used by `_resolveAccountFromContainer`'s `container.closest()` pattern (per F1 L4 design).
- `agent/config.py:_CONNECTOR_AUTO_RELAY_DIRECTIVE` + `:_CONNECTOR_TOOL_ENABLED_DIRECTIVE` + `:_CONNECTOR_TOOL_DISABLED_DIRECTIVE` — verified at lines 54-95 (three module-level string constants).

Eight citation clusters verified live against the post-L3 tree.
