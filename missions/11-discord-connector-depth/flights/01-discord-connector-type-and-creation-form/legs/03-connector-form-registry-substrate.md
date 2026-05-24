# Leg: connector-form-registry-substrate

**Status**: landed
**Flight**: [Discord Connector-Type Registration + Discord-Shaped Creation Form](../flight.md)

## Objective

Introduce a frontend per-type form registry (`App.studio.connectorFormRegistry`) so the connector-account editor can dispatch typed form-field rendering and form-data collection per connector type, with a generic-kv-table fallback when no entry is registered; ship the substrate ONLY (no Discord entry yet — that's L4) so the existing `'stub'`-type flow and any future-type-without-UI flow continue to render unchanged via the fallback path.

## Context

- **Why now**: F1 flight Design Decision "Form abstraction — substrate-level per-type form registry (frontend)" (`flight.md` Design Decisions §3) commits to a `connector-form-registry` substrate that the second connector (in M12 or later) inherits without forcing a refactor. M11 mission constraint forbids closing design space for the second connector; a hardcoded `if (type === 'discord')` would repeat the M10 F1 pool-keying methodology failure (mirror without premise re-validation surfaced at F8 HAT seven flights later). L3 ships the substrate; L4 ships Discord as the first registry consumer; the fallback path (no entry → generic kv-table) is the test seam that keeps `'stub'` and future-type-no-UI flows working.
- **Prerequisite from L2**: API-layer config validation is in place for the three Discord keys (`intents`, `guilds`, `presence`). The frontend can now post these typed shapes without the backend rejecting unrecognized config — the validator gates them at the API write boundary.
- **Atomic-leg-pattern application**: per L1's codified convention, the registry substrate ships with its consumer-side integration into `connector-account-editor.js` (consult sites in `renderConnectionFields`, `renderSecretsKvTable`, `collectConfigRows`, `collectFormData`, `getFormSnapshot`) AND its regression-coverage test seam (browser tests against the `'stub'` type confirm the fallback path renders byte-identical generic kv-tables) all in this leg. No Discord entry — that's L4's atomic-leg pattern landing.
- **What's NOT in scope**: any Discord-shaped form fields, any vocabulary substitution (that's L6's own substrate), any registry entry. L3 ships an empty registry plus the fallback path; the only test surface is "with zero entries registered, the editor renders exactly what it renders today."
- **State-machine reachability**: this leg introduces no new server-side state, no DB changes, no API changes. The registry is a client-side object with two methods (`register`, `get`); reload restores it to "empty" on every page load (no persistence). The fallback when `get(type)` returns `undefined` is the established generic kv-table path. Cache freshness: per-page-load only, no TTL; the registry is per-tab in-memory state.
- **Test-update surface**: The current Studio Playwright tests (`tests/browser/test_flow_studio_connector_account_editor.py`, `test_flow_studio_connector_account_create_and_test.py`, `test_flow_studio_connector_account_navigation.py`) all test against the `'stub'` connector type (registered via `THE_ONE_REGISTER_STUB_CONNECTOR=1` per the test file's docstring). After L3 lands, every one of these tests MUST continue to pass UNMODIFIED — the fallback path renders the same DOM the current generic-kv-table code produces. This is the regression contract.

### Design Decisions (L3-internal)

- **Registry shape**: `App.studio.connectorFormRegistry` exposes exactly two public methods: `register(type, entry)` and `get(type) → entry | undefined`. Internal storage is a plain object keyed on `type`. No `unregister` (registry entries are program-lifetime; tests reset via page reload). No `list()` (consumers know the types they care about). Calling `register(type, entry)` twice on the same type overwrites the prior entry (last-writer-wins) with a `console.warn` — supports hot-reload during dev, surfaces accidental double-registration.
- **Entry shape**: `{ type: string, renderConnectionFields: function(account, isCreate) → string, renderCredentialsFields: function(account) → string, collect: function(container, account, isEdit) → {config, secrets}, reservedConfigKeys: string[] }`. All five fields are REQUIRED — the registry validates the shape at `register()` time and throws `TypeError` with a descriptive message if any field is missing or wrong type. The `type` field is redundant with the dict key but kept for self-description (logging, debugging). `reservedConfigKeys` declares which top-level `account.config` keys the typed form OWNS — `collectConfigRows` hides them from the Advanced kv-table; `collectFormData` lets the registry's `collect` hook write them via `config`.
- **Consult-site shape (the load-bearing decision)**: per `flight.md` Design Decisions §3 trade-off paragraph, the registry's `collect` hook returns `{config: {...}, secrets: {...}}` and the substrate STITCHES the result into the canonical payload alongside allowlist / routing / pairing data. This is the cleaner of the two integration options surfaced at design review. Rationale: the alternative (emit the same DOM selectors as the generic tables so existing scanning works unchanged) couples the registry entry's DOM to the substrate's selector strings, which is a worse separation.
- **Fallback path is the test seam**: when `App.studio.connectorFormRegistry.get(account.type)` returns `undefined`, `renderConnectionFields` calls the existing generic-kv-table renderer UNCHANGED. Same for `renderSecretsKvTable`. `collectFormData` falls through to the existing DOM-scan path. `collectConfigRows` uses the static `RESERVED_CONFIG_KEYS` substrate baseline (`{pairing, allowlist, routing}`) when no entry exists; merges with `entry.reservedConfigKeys` when present. Browser tests against the `'stub'` type (which has no registry entry in L3 or L4) are the regression gate.
- **Wrapper-contract for byte-identical fallback**: the substrate's `renderConnectionFields` always emits the outer `<div class="field-row admin-pf-row connector-account-config-wrap"><label>Config</label><div class="connector-account-config" data-testid="connector-account-config">...</div></div>` wrapper. ONLY the inner content varies — `renderConfigKvTable(account)` when no entry exists; `entry.renderConnectionFields(account, isCreate)` (returning HTML for typed fields) when an entry exists. This wrapper contract guarantees: (a) the `'stub'`-type Playwright tests that select `[data-testid="connector-account-config"]` continue to resolve; (b) L4's Discord-shaped form has a stable mount point inside `.connector-account-config`; (c) the fallback DOM is byte-identical to the pre-L3 baseline at the wrapper level. Same wrapper-contract applies analogously to `renderSecretsKvTable` (which already emits its own wrapper at `connector-account-editor.js:618-622` — its `.connector-account-secrets` wrapper stays in place; only the inner table HTML varies per entry).
- **`auto_relay_platform_replies` is OUT OF L3 SCOPE — explicit deferral**: this top-level `account.config` key (`config["auto_relay_platform_replies"]`, M10 F8 L11 Fix #4) currently appears as a row in the Advanced kv-table when an account has it set, because it's NOT in `RESERVED_CONFIG_KEYS`. This is a pre-existing substrate bug: the key is rendered both by the dedicated Lifecycle-section checkbox (line 1207-1220) AND by the generic kv-table iterator. L3 does NOT touch this — adding the key to `RESERVED_CONFIG_KEYS` would change the existing fallback DOM, violating the byte-identical contract. Recorded as a deferred-item for a later flight to fix without entanglement to the registry substrate.
- **Entries MUST NOT return reserved config keys**: when `entry.collect()` returns `{config, secrets}`, the returned `config` MUST NOT contain any key in `RESERVED_CONFIG_KEYS` (`pairing`, `allowlist`, `routing`, plus `auto_relay_platform_replies` which is substrate-known even if not in the constant — see deferral above). If an entry violates this, the substrate-merge code overlays the substrate's value at the end of `collectFormData`; the entry's collision is silently overwritten. L4 (when registering Discord) is the first consumer to obey this contract.
- **Entry `renderConnectionFields(account, isCreate)` signature**: deliberately does NOT receive `types` — the type-select dropdown is the substrate's connector-agnostic responsibility (rendered before the registry consult); typed entries only render the post-type-pick section. This pins the entry's scope to its own typed fields, not the type-picker.
- **Reserved-key composition**: substrate keeps `RESERVED_CONFIG_KEYS = { pairing, allowlist, routing }` as the connector-agnostic baseline. The effective reserved set for a typed account is `RESERVED_CONFIG_KEYS ∪ entry.reservedConfigKeys` — computed at `collectConfigRows` and `renderConfigKvTable` time, not statically. Per `flight.md` Design Decision: "The substrate's `RESERVED_CONFIG_KEYS` stays as the connector-agnostic generic baseline; the Discord registry entry adds `{ intents, guilds, presence }` to its own per-type set" — confirming L3 leaves the substrate baseline at `{pairing, allowlist, routing}` and the Discord-specific additions land in L4.
- **No `getFormSnapshot` integration in L3**: the dirty-tracker reads its own DOM selectors directly (lines 650-712). When L4 ships the Discord registry entry with typed inputs, those inputs MUST be added to the dirty-tracker's scan paths. L3 leaves `getFormSnapshot` UNCHANGED — its current selectors cover the generic kv-table rows; nothing the registry's substrate touches changes that. L4 owns the dirty-tracker extension.
- **Script-load order**: `connector-form-registry.js` MUST load BEFORE `connector-account-editor.js` because the editor consults the registry at first-render time. Insert the new `<script>` tag in `index.html` at line 56 (before `connector-account-editor.js` at line 57; immediately after `connector-accounts-grid.js` at line 56). The script attaches `App.studio.connectorFormRegistry` to the global namespace via the established `window.App.studio = window.App.studio || {};` pattern.

## Inputs

Files that must exist:
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` (existing 2421-line module — target for the integration; key sites at `renderConnectionFields:477`, `renderSecretsKvTable:616`, `collectConfigRows:555`, `collectFormData:1092`, `RESERVED_CONFIG_KEYS:553`)
- `the_one/interfaces/web/static/index.html` (script-load-order file — new `<script>` tag added at line 56)
- `tests/browser/test_flow_studio_connector_account_editor.py` (regression gate — must pass UNMODIFIED post-L3)
- `tests/browser/test_flow_studio_connector_account_create_and_test.py` (regression gate)
- `tests/browser/test_flow_studio_connector_account_navigation.py` (regression gate)
- `tests/browser/seeders.py` (test seeders for connector accounts — read for context; NO edit in L3)
- `tests/browser/conftest.py` (Playwright fixtures + `THE_ONE_REGISTER_STUB_CONNECTOR=1` wiring — read; NO edit)

State that must be true:
- L1 and L2 are `landed`
- Flight branch `flight/01-discord-connector-type-and-creation-form` is checked out
- All M10 F8 tests pass (2421 baseline post-L2)
- The connector-form-registry.js file does NOT yet exist in `the_one/interfaces/web/static/js/areas/studio/`

## Outputs

State changes after this leg:
- **New file** `the_one/interfaces/web/static/js/areas/studio/connector-form-registry.js` (~80-120 lines): defines `App.studio.connectorFormRegistry` with `register(type, entry)`, `get(type)`, plus internal storage + shape validation + double-register warning.
- **Modified** `the_one/interfaces/web/static/index.html`: new `<script src="/static/js/areas/studio/connector-form-registry.js"></script>` line inserted at line 56 (before `connector-account-editor.js`).
- **Modified** `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js`:
  - `renderConnectionFields` (line 477+) consults `App.studio.connectorFormRegistry.get(account.type || typeValue)` at the head; if entry exists and `entry.renderConnectionFields` is present, calls it AFTER rendering the Name + Type field-rows but INSTEAD OF rendering the Config kv-table block (the Config kv-table goes into an "Advanced" disclosure that L4 will introduce; in L3 the conditional just chooses between "typed render path" vs "generic kv-table render path"). When no entry → existing behavior (renders the generic kv-table). The Name + Type field-rows always render (they're connector-agnostic).
  - `renderSecretsKvTable` (line 616+) consults the registry analogously; if entry has `renderCredentialsFields`, calls it INSTEAD of the generic secrets kv-table. When no entry → existing behavior.
  - `collectConfigRows` (line 555+) composes the effective reserved set as `RESERVED_CONFIG_KEYS ∪ (entry?.reservedConfigKeys || [])` at call time, then proceeds with the existing iteration.
  - `collectFormData` (line 1092+) consults the registry's `collect` hook FIRST when an entry exists; the hook returns `{config, secrets}` which the substrate then STITCHES with the existing pairing/allowlist/routing merging. When no entry → existing config-from-DOM + secrets-from-DOM scan path unchanged.
  - All consult sites guard against the registry being undefined (e.g., during early module-load races) — fallback to generic path.
- **NO changes** to `getFormSnapshot` (L4 will extend it when typed inputs land), to `wireEditorEvents`, to allowlist / routing / pairing handlers, to backend API, to tests.
- **Test outcome**: existing browser test count holds; no new tests added in L3 (the existing `'stub'`-type Playwright tests ARE the regression seam — they pass UNMODIFIED, proving the fallback path renders byte-identically).

## Acceptance Criteria

- [ ] `the_one/interfaces/web/static/js/areas/studio/connector-form-registry.js` EXISTS and defines `App.studio.connectorFormRegistry` with exactly two public methods: `register(type, entry)` and `get(type)`. Internal storage is a plain object; no other public methods exposed.
- [ ] `register(type, entry)` validates the entry's shape at call time: `entry.type === type` (string), `typeof entry.renderConnectionFields === 'function'`, `typeof entry.renderCredentialsFields === 'function'`, `typeof entry.collect === 'function'`, `Array.isArray(entry.reservedConfigKeys)`. Missing or wrong-type fields raise `TypeError` with a message naming the specific field. Test: a malformed `entry` (missing `collect`) throws.
- [ ] `register(type, entry)` called twice on the same `type` overwrites the prior entry and emits `console.warn('App.studio.connectorFormRegistry: re-registering type ' + type)`. The second registration's entry is what `get(type)` returns thereafter.
- [ ] `get(type)` returns the registered entry, or `undefined` if no entry exists for `type`. No exception thrown for missing types.
- [ ] `connector-form-registry.js` is loaded by `index.html` IMMEDIATELY BEFORE `connector-account-editor.js` (ordering criterion, not literal-line-number — verify the new `<script>` tag and the `connector-account-editor.js` `<script>` tag are adjacent with the registry first).
- [ ] `connector-account-editor.js:renderConnectionFields` consults `App.studio.connectorFormRegistry.get(account.type || ...)` at the head of the function (after the Name + Type field-rows render); the substrate ALWAYS emits the outer `<div class="field-row admin-pf-row connector-account-config-wrap"><label>Config</label><div class="connector-account-config" data-testid="connector-account-config">...</div></div>` wrapper. The inner content is either `entry.renderConnectionFields(account, isCreate)` (when an entry exists with that method) or `renderConfigKvTable(account)` (fallback). Wrapper byte-identical between paths.
- [ ] `connector-account-editor.js:renderSecretsKvTable` consults the registry; the substrate ALWAYS emits its existing outer wrappers (around line 618-622, `.connector-account-secrets` block); only the inner table HTML varies — `entry.renderCredentialsFields(account)` (when entry has it) or the existing generic secrets kv-table (fallback). For create mode (`account` is `{}` or has no `type`), `registry.get('')` returns `undefined` → fallback path; this matches pre-L3 behavior.
- [ ] `connector-account-editor.js:collectConfigRows` composes the effective reserved set as union of `RESERVED_CONFIG_KEYS` (existing static `{pairing, allowlist, routing}`) and `(registry.get(account.type)?.reservedConfigKeys || [])`. Substrate baseline `RESERVED_CONFIG_KEYS` constant is UNCHANGED.
- [ ] `connector-account-editor.js:collectFormData` consults the registry's `collect(container, account, isEdit) → {config, secrets}` hook when an entry exists; the returned `config` and `secrets` are then merged with allowlist / routing / pairing per the existing code path (the registry's `config` keys are written first, then the substrate-known reserved keys overlay). When NO entry → existing config-from-DOM + secrets-from-DOM scan path unchanged.
- [ ] All consult sites guard with `var registry = window.App && window.App.studio && window.App.studio.connectorFormRegistry; var entry = registry && registry.get(typeValue);` — three layered checks so an early-load race never throws.
- [ ] **New test**: `tests/browser/test_connector_form_registry.py` (or a small `TestConnectorFormRegistry` class inside the existing `test_flow_studio_connector_account_editor.py`) covers the registry's own contract via `page.evaluate`:
  - `App.studio.connectorFormRegistry.register('test-type', {complete-valid-entry})` succeeds; `get('test-type')` returns the entry.
  - `register('test-type', ...)` called twice — `console.warn` fires; the second entry is what `get` returns. Use `page.on("console", lambda m: ...)` to capture the warn.
  - `register('bad-type', {missing renderConnectionFields})` raises `TypeError` with a message naming the missing field.
  - `register('mismatch-type', {type: 'other'})` raises `TypeError` for the type-mismatch case.
  - `get('unregistered-type')` returns `undefined`.
  ~30-50 lines; uses an existing Playwright fixture to load the Studio page and `page.evaluate` to drive the registry directly.
- [ ] `tests/browser/test_flow_studio_connector_account_editor.py` PASSES UNMODIFIED — every test in that file continues to pass.
- [ ] `tests/browser/test_flow_studio_connector_account_create_and_test.py` PASSES UNMODIFIED.
- [ ] `tests/browser/test_flow_studio_connector_account_navigation.py` PASSES UNMODIFIED.
- [ ] No backend changes, no API changes, no DB changes. `git diff --name-only` shows only the new registry file, `index.html`, and `connector-account-editor.js` plus the leg/flight-log artifacts.
- [ ] Full suite `docker exec the-one pytest -x --timeout 30 -q -m "not pixel"` stays at or above the L2 baseline (2421 passed).

## Verification Steps

- `grep -n "connectorFormRegistry" the_one/interfaces/web/static/js/areas/studio/connector-form-registry.js` — confirms the namespace attach.
- `grep -n "connector-form-registry.js" the_one/interfaces/web/static/index.html` — confirms script load.
- `grep -c "connectorFormRegistry" the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — should return >= 4 (consults at `renderConnectionFields`, `renderSecretsKvTable`, `collectConfigRows`, `collectFormData`).
- `docker exec the-one pytest -x --timeout 60 -m browser tests/browser/test_flow_studio_connector_account_editor.py` — all tests pass.
- `docker exec the-one pytest -x --timeout 60 -m browser tests/browser/test_flow_studio_connector_account_create_and_test.py` — all pass.
- `docker exec the-one pytest -x --timeout 60 -m browser tests/browser/test_flow_studio_connector_account_navigation.py` — all pass.
- `docker exec the-one pytest -x --timeout 30 -q -m "not pixel"` — full non-pixel suite at or above 2421-passed baseline.
- Manual DOM check (optional, sanity): open Studio in a browser at the dev container, navigate to Connector Accounts, click an existing stub-type account; the form renders identically to the pre-L3 baseline (Name + Type + generic Config kv-table + generic Secrets kv-table + Allowlist + Routing). Open browser console — `App.studio.connectorFormRegistry.get('stub')` returns `undefined`.

## Implementation Guidance

1. **Read the existing module pattern**: `the_one/interfaces/web/static/js/areas/studio/agent-editor.js` is a good model — IIFE-wrapped, attaches to `window.App.studio`, exposes a small public surface. Mirror the file shape. The studio modules use vanilla ES5-style JS — `var` (not `const`/`let`), no arrow functions, no template literals — confirmed by inspecting `agent-editor.js`. `connector-form-registry.js` MUST use the same ES5 style for consistency.

2. **Create `the_one/interfaces/web/static/js/areas/studio/connector-form-registry.js`**:
   ```javascript
   // App.studio.connectorFormRegistry — per-type form-field registry (M11 F1 L3).
   //
   // A substrate-level abstraction so connector-account-editor.js can
   // dispatch typed form rendering and form-data collection per connector
   // type without hardcoded `if (type === 'discord')` branches. Each
   // connector type that wants a typed form registers an entry here at
   // module load time. The connector-account editor consults the registry
   // at render and collect time; unregistered types fall back to the
   // generic kv-table render path (the `'stub'` test-only carve-out and
   // any future-type-with-no-UI path remain on the fallback).
   //
   // M11 mission constraint: the registry shape must not close design
   // space for the second connector. Single-method-per-section render
   // hooks + a structured `{config, secrets}` return from `collect` keep
   // DOM coupling local to each entry and stitching local to the
   // substrate.

   (function () {
     'use strict';

     window.App = window.App || {};
     window.App.studio = window.App.studio || {};

     var _entries = {};

     function _validateEntry(type, entry) {
       if (!entry || typeof entry !== 'object') {
         throw new TypeError(
           'connectorFormRegistry.register: entry must be an object; got ' + (entry === null ? 'null' : typeof entry)
         );
       }
       if (entry.type !== type) {
         throw new TypeError(
           "connectorFormRegistry.register: entry.type must equal the registered key '" + type + "'; got " + JSON.stringify(entry.type)
         );
       }
       var requiredFns = ['renderConnectionFields', 'renderCredentialsFields', 'collect'];
       for (var i = 0; i < requiredFns.length; i++) {
         if (typeof entry[requiredFns[i]] !== 'function') {
           throw new TypeError(
             "connectorFormRegistry.register: entry." + requiredFns[i] + " must be a function for type '" + type + "'"
           );
         }
       }
       if (!Array.isArray(entry.reservedConfigKeys)) {
         throw new TypeError(
           "connectorFormRegistry.register: entry.reservedConfigKeys must be an array for type '" + type + "'"
         );
       }
     }

     function register(type, entry) {
       if (typeof type !== 'string' || !type) {
         throw new TypeError('connectorFormRegistry.register: type must be a non-empty string');
       }
       _validateEntry(type, entry);
       if (_entries[type] !== undefined) {
         // Last-writer-wins; surface accidental double-registration via warn.
         try {
           console.warn('App.studio.connectorFormRegistry: re-registering type ' + type);
         } catch (e) { /* console may be missing in some test envs */ }
       }
       _entries[type] = entry;
     }

     function get(type) {
       return _entries[type];
     }

     window.App.studio.connectorFormRegistry = {
       register: register,
       get: get
     };
   })();
   ```

3. **Add the script tag to `index.html` at line 56** (immediately before `connector-account-editor.js` at the current line 57; line numbers shift by one after the insert):
   ```html
   <script src="/static/js/areas/studio/connector-form-registry.js"></script>
   <script src="/static/js/areas/studio/connector-account-editor.js"></script>
   ```

4. **Refactor `connector-account-editor.js:renderConnectionFields`** (line 477+):
   - At the position where the existing Config kv-editor block lives (lines 534-540 — opens `<div class="field-row admin-pf-row connector-account-config-wrap">`, closes with the corresponding `</div>`), wrap the INNER `renderConfigKvTable(account)` call with a registry consult. The outer wrapper stays unconditional so the fallback DOM is byte-identical to pre-L3:
     ```javascript
     // M11 F1 L3: per-type form registry consult. The substrate emits
     // the outer field-row wrapper unconditionally so the
     // ``[data-testid="connector-account-config"]`` selector keeps
     // resolving for tests; only the inner content varies between the
     // typed (entry.renderConnectionFields) and generic
     // (renderConfigKvTable) render paths.
     var registry = (window.App && window.App.studio && window.App.studio.connectorFormRegistry) || null;
     var activeType = isCreate ? '' : (account && account.type) || '';
     var entry = (registry && activeType) ? registry.get(activeType) : undefined;

     html += '<div class="field-row admin-pf-row connector-account-config-wrap">';
     html += '<label>Config</label>';
     html += '<div class="connector-account-config" data-testid="connector-account-config">';
     if (entry && typeof entry.renderConnectionFields === 'function') {
       html += entry.renderConnectionFields(account, isCreate);
     } else {
       html += renderConfigKvTable(account);
     }
     html += '</div>';
     html += '</div>';
     ```
   - Important: the create-mode path (where the operator hasn't picked a type yet, so `account.type` is empty) always falls through to the generic kv-table. The create-mode typed-form rendering becomes a L4 concern (when Discord-shaped form lands, it'll re-render the Config section in response to the type-select dropdown). For L3, create mode stays on the generic kv-table — and this matches the existing behavior in `tests/browser/test_flow_studio_connector_account_editor.py` (create form is always generic-kv-table today).

5. **Refactor `connector-account-editor.js:renderSecretsKvTable`** (line 616+) analogously:
   - Read the existing function to identify the outer wrapper(s) emitted in the secrets render. Preserve them unconditionally so the fallback DOM is byte-identical. Only the inner content (the secrets kv-table HTML body) is replaced when `entry.renderCredentialsFields` exists.
   - At the head of the function, do the registry consult with the triple-guard; when an entry exists with a `renderCredentialsFields` method, substitute its return for the inner table HTML. Fall through to the existing implementation when no entry.
   - Important: this function is called from `renderConnectorAccountEditor` around line 272 with `account` as the parameter. In create mode `account` is an empty object (or has no `type` set) — `registry.get('')` or `registry.get(undefined)` returns `undefined` → falls through to the generic path. Matches pre-L3 behavior.

6. **Refactor `connector-account-editor.js:collectConfigRows`** (line 555+):
   - Compose effective reserved-keys at the top:
     ```javascript
     function collectConfigRows(account) {
       var rows = [];
       if (!account || !account.config) return rows;

       // M11 F1 L3: union the substrate baseline with per-type
       // reserved keys (registry entry, if any).
       var registry = (window.App && window.App.studio && window.App.studio.connectorFormRegistry) || null;
       var entry = (registry && account.type) ? registry.get(account.type) : undefined;
       var perTypeReserved = (entry && entry.reservedConfigKeys) || [];
       var effectiveReserved = Object.assign({}, RESERVED_CONFIG_KEYS);
       for (var pi = 0; pi < perTypeReserved.length; pi++) {
         effectiveReserved[perTypeReserved[pi]] = true;
       }

       for (var k in account.config) {
         if (Object.prototype.hasOwnProperty.call(account.config, k)) {
           if (effectiveReserved[k]) continue;
           // ... rest unchanged
         }
       }
       return rows;
     }
     ```

7. **Refactor `connector-account-editor.js:collectFormData`** (line 1092+):
   - At the position where the existing function collects config from DOM (around line 1119) and secrets from DOM (around line 1131), insert a registry consult:
     ```javascript
     var config = {};
     var secrets = {};

     // M11 F1 L3: per-type registry's collect hook runs FIRST when
     // an entry exists; its returned config/secrets are then merged
     // with the substrate's pairing/allowlist/routing post-fill below.
     // When no entry exists, fall through to the generic DOM-scan path.
     var registry = (window.App && window.App.studio && window.App.studio.connectorFormRegistry) || null;
     var collectEntry = (registry && typeValue) ? registry.get(typeValue) : undefined;
     var collected = (collectEntry && typeof collectEntry.collect === 'function')
       ? collectEntry.collect(container, account, isEdit)
       : null;

     if (collected) {
       if (collected.config) {
         for (var ck in collected.config) {
           if (Object.prototype.hasOwnProperty.call(collected.config, ck)) {
             config[ck] = collected.config[ck];
           }
         }
       }
       if (collected.secrets) {
         for (var sk in collected.secrets) {
           if (Object.prototype.hasOwnProperty.call(collected.secrets, sk)) {
             secrets[sk] = collected.secrets[sk];
           }
         }
       }
     } else {
       // Existing generic DOM-scan path — UNCHANGED.
       var configRows = container.querySelectorAll(/* ... */);
       // ... existing code unchanged
     }
     ```
   - Be careful: the substrate's pairing / allowlist / routing / `auto_relay_platform_replies` merge code (lines 1157-1205+) MUST still run after the registry's `collect` returns. The registry's `config` keys do NOT include `pairing`, `allowlist`, `routing`, `auto_relay_platform_replies` — those are substrate-known and stitched in by the substrate code. The registry contract is "the registry writes the per-type config keys; the substrate writes the connector-agnostic config keys; they coexist in the final payload."

8. **Do NOT modify `getFormSnapshot`** (line 650+). The L3 spec leaves it alone — its current selectors scan the generic kv-table rows. With no typed inputs landed yet, no extension is needed. L4 will own the snapshot extension when typed inputs ship.

9. **Run the regression tests**:
   ```bash
   docker exec the-one pytest -x --timeout 60 -m browser tests/browser/test_flow_studio_connector_account_editor.py
   docker exec the-one pytest -x --timeout 60 -m browser tests/browser/test_flow_studio_connector_account_create_and_test.py
   docker exec the-one pytest -x --timeout 60 -m browser tests/browser/test_flow_studio_connector_account_navigation.py
   ```
   ALL must pass UNMODIFIED. If any fails, the fallback path has drifted — diagnose; do NOT modify the test to match the new behavior. The L3 contract is byte-identical generic-path rendering for `'stub'`.

10. **Final full-suite check**:
    ```bash
    docker exec the-one pytest -x --timeout 30 -q -m "not pixel"
    ```
    Should stay at or above the L2 baseline of 2421 passed. No new tests added by L3 (the regression coverage IS the existing `'stub'`-path tests).

## Edge Cases

- **`account.type === '' or undefined` (create mode pre-type-pick)**: `registry.get('')` returns `undefined`; falls through to generic kv-table. Matches existing create-mode behavior.
- **Registry not loaded (script-load race)**: every consult site uses the `(window.App && window.App.studio && window.App.studio.connectorFormRegistry) || null` triple-guard. If somehow `connector-form-registry.js` fails to load (e.g. 404), all consult sites return `undefined` from the lookup and fall through to the generic path. Worst case: typed forms don't appear — operator sees the pre-L3 UI. No exceptions.
- **`entry.collect` returns malformed `{config, secrets}` shape**: L3 substrate doesn't strictly validate the return — the substrate's loop iterates `collected.config` keys, treating it as an object; non-string keys cause undefined behavior. L4 contracts its own collect-return shape; L3 trusts it (the substrate-vs-entry boundary is at registration-time shape validation, not call-time return validation). If L4 needs return validation, it owns the contract.
- **Double-register on the same type**: emits `console.warn`; last-writer-wins. Important during dev hot-reload but unlikely in production.
- **Existing `RESERVED_CONFIG_KEYS` substrate constant**: stays at `{pairing, allowlist, routing}`. NOT modified. The composition happens at call time, not at constant definition. Per Design Decisions §3 (`auto_relay_platform_replies` deferral): the implementing agent does NOT extend `RESERVED_CONFIG_KEYS` to include this key — doing so would change the existing fallback DOM and violate the byte-identical contract. The status-quo bug (the key appearing as a kv-row when set) is preserved untouched.
- **`registry.get(type)` mid-render race**: the registry is populated at script-load time (no async). Once `connector-form-registry.js` has loaded, the registry is stable. The script-load-order in `index.html` ensures the registry exists by the time any editor code runs.
- **Future test-update implication**: L4 will register Discord and the existing `'stub'`-path tests still need to pass (they hit the fallback). L3's no-Discord-entry shape is the cleanest substrate to land that contract.

## Files Affected

- `the_one/interfaces/web/static/js/areas/studio/connector-form-registry.js` — NEW FILE; ~80-120 lines.
- `the_one/interfaces/web/static/index.html` — one new `<script>` tag inserted before `connector-account-editor.js`.
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — modifications to `renderConnectionFields`, `renderSecretsKvTable`, `collectConfigRows`, `collectFormData`; static `RESERVED_CONFIG_KEYS` constant UNCHANGED; no edits to `getFormSnapshot`, `wireEditorEvents`, allowlist / routing / pairing / dirty-tracker paths.
- `missions/11-discord-connector-depth/flights/01-discord-connector-type-and-creation-form/flight-log.md` — Leg Progress entry appended.
- `missions/11-discord-connector-depth/flights/01-discord-connector-type-and-creation-form/legs/03-connector-form-registry-substrate.md` — status header transitions (planning → ready → in-flight → landed).

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Existing browser tests pass UNMODIFIED — the regression contract for the fallback path
- [ ] Full suite at or above L2 baseline (2421 passed) on `-m "not pixel"` invocation
- [ ] No backend, API, DB, or Pydantic changes
- [ ] Each consult site uses the triple-guard against missing registry
- [ ] Update flight-log.md with Leg Progress entry
- [ ] Set this leg's status to `landed` in this file's header
- [ ] Do NOT check off the leg in flight.md
- [ ] Do NOT commit

## Citation Audit

Citations verified at leg design time (2026-05-21, post-L2):

- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js:renderConnectionFields` — verified at line 477; ~65-line function. The Config kv-editor block is at lines 534-540 (`<div class="field-row admin-pf-row connector-account-config-wrap">` through `</div>`).
- `connector-account-editor.js:renderSecretsKvTable` — verified at line 616.
- `connector-account-editor.js:collectConfigRows` — verified at line 555; iterates `account.config` keys with `RESERVED_CONFIG_KEYS[k]` skip-guard at line 560.
- `connector-account-editor.js:RESERVED_CONFIG_KEYS` — verified at line 553; current shape `{ pairing: true, allowlist: true, routing: true }`.
- `connector-account-editor.js:collectFormData` — verified at line 1092; ~360-line function (collects config from DOM at 1119-1129, secrets at 1131-1148, then merges pairing / allowlist / routing / auto_relay).
- `connector-account-editor.js:getFormSnapshot` — verified at line 650; ~63-line function with `static`/`config`/`secrets`/`allowlist`/`routing` snapshot keys.
- `the_one/interfaces/web/static/index.html` — verified: `connector-accounts-grid.js` at line 56, `connector-account-editor.js` at line 57, `studio.js` at line 58. Insertion point at line 56 (before connector-account-editor.js, after connector-accounts-grid.js).
- `tests/browser/test_flow_studio_connector_account_editor.py`, `_create_and_test.py`, `_navigation.py` — verified to exist; use `'stub'` connector type via `THE_ONE_REGISTER_STUB_CONNECTOR=1` per file docstrings; `data-testid` selectors throughout.
- `the_one/interfaces/web/static/js/areas/studio/agent-editor.js` — verified at lines 1-200; IIFE-wrapped module attaching to `window.App.studio`; suitable model for `connector-form-registry.js` shape.

Nine citation clusters verified live. No drift.
