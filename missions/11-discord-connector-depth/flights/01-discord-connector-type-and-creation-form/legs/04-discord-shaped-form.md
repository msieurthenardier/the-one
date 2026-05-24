# Leg: discord-shaped-form

**Status**: landed
**Flight**: [Discord Connector-Type Registration + Discord-Shaped Creation Form](../flight.md)

## Objective

Register the Discord entry in L3's `App.studio.connectorFormRegistry` with typed form-fields — BOT_TOKEN (masked-edit secret), three intent checkboxes (all defaulted on), a guilds list editor, a presence dict editor, and an Advanced kv-table disclosure wrapping the generic kv-table — closing the Discord-shaped-creation-form half of the flight by producing UI that posts the typed shapes L2's API validator accepts.

## Context

- **Why now**: F1 contributing-to-criteria item #1 names "typed BOT_TOKEN field, intents selector with safe defaults, optional guild scoping, presence editor" as the Discord-shaped form deliverable. L1 codified `atomic-leg-pattern` (registry entry + dirty-tracker extension + collect-hook contract land together). L2 shipped the API-layer validator that gates these shapes; L3 shipped the registry substrate plus the byte-identical-fallback wrapper contract. L4 is the first registry consumer.
- **L4 ships everything Discord-specific in one atomic registry entry**: the entry's `renderConnectionFields` produces the three typed sections (Intents / Guilds / Presence) plus the Advanced kv-table disclosure; `renderCredentialsFields` produces the typed BOT_TOKEN field with masked-edit; `collect` reads back the typed-input DOM and emits the structured `{config: {intents, guilds, presence}, secrets: {BOT_TOKEN}}` payload; `reservedConfigKeys: ['intents', 'guilds', 'presence']` hides the typed keys from the Advanced kv-table per L3's effective-reserved-keys composition.
- **`getFormSnapshot` MUST be extended** (deferred by L3 to L4): the new typed inputs need to participate in the dirty-tracker so the operator's first edit re-enables the Save button. Failure to extend the snapshot makes Save stuck-disabled when the operator changes only typed fields.
- **Prerequisite from L2/L3**: L2's validator accepts `intents` / `guilds` / `presence` shapes the L4 form emits; L3's wrapper contract guarantees the substrate's `.connector-account-config` `data-testid` and `.connector-account-secrets` wrappers stay in place, so existing Playwright selectors continue to resolve when running against `'stub'` (no entry → fallback) — L4 must not break that.
- **Backward compatibility**: an existing Discord account whose `config` lacks `intents` / `guilds` / `presence` renders with the typed inputs at their defaults (intents all True, guilds empty, presence empty/default). Saving without typed-input edits MUST NOT introduce keys that weren't present — emit `intents` only when at least one checkbox state has changed, similarly for guilds and presence. Otherwise edits to other fields would silently materialize default-shaped intents into the persisted config, deviating from the M10 F8 byte-identical-fallback baseline.

### Design Decisions (L4-internal)

- **Field anchor IDs and `data-testid`s**: every typed input carries both `data-field` (consumed by the dirty-tracker scan) AND `data-testid` (consumed by browser tests). Naming: `intent-message-content`, `intent-members`, `intent-guilds`, `guilds-list`, `presence-name`, `presence-type`, `bot-token`. Plus per-element `data-testid` strings — `discord-intent-message-content`, etc. — namespaced with the `discord-` prefix to disambiguate from any future entry's intent UI.
- **Intents shape on emit**: emit `config.intents = {message_content: bool, members: bool, guilds: bool}` ONLY when at least one of the three checkbox states is NOT True (the M10 F8 hardcoded default). If all three are True AND the existing `account.config` does NOT carry `intents`, omit the key entirely — preserves byte-identical round-trip for accounts that never opted in. If the existing `account.config` already carries `intents` (operator previously set it), ALWAYS emit (round-trip the operator's prior choice exactly, even if all three are True). The collect hook receives `account` so this read is straightforward.
- **Guilds shape on emit**: the typed input is a comma-separated text input or a chip-list (implementer's choice — chip-list mirrors the F6 allowlist pattern but adds complexity; comma-separated string with frontend split-on-comma is simpler and matches the existing kv-editor's feel). Recommend comma-separated `<input>` with the help-text "Comma-separated Discord guild IDs (digit-only)". The collect hook splits, trims, drops empties; if result is empty list AND existing config has no `guilds`, omit. Otherwise emit as `config.guilds = [...]`. L2's validator catches non-digit entries at 422.
- **Presence shape on emit**: the typed input is two fields — a `name` text input and a `type` dropdown with the five values from L2's validator (`playing`, `streaming`, `listening`, `watching`, `competing`). The dropdown's empty option means "no presence override" → omit `config.presence`. When the operator sets a non-empty name or non-default type, emit `config.presence = {name?, type?}` (only the keys the operator set; L2's validator accepts missing keys). Defaults: name input shows the live `account.config.presence.name` (or empty placeholder); type dropdown shows the live value (or the empty "Use default" option).
  **Cleared-when-pre-existing**: if `account.config.presence` was set before AND the operator now cleared BOTH name + type, emit `config.presence = {}` so the empty operator-intent round-trips (L2's validator accepts empty-dict per Edge Cases section of L2). The plugin's `_build_activity` defensive guards fall back to the default presence when both name and type are absent, preserving runtime behavior.
- **BOT_TOKEN field**: single secret input with masked-edit per the existing `secrets-value-input` pattern (`MASKED_SENTINEL` handling at lines 1142-1147 in `collectFormData`). Reused conventions: `data-original-masked` attribute carries the original `***...{tail4}` value; show/hide eye-icon toggles type=password/text. The collect hook returns `{secrets: {BOT_TOKEN: ...}}` — if the input value equals the `_originalMasked` string, emit `MASKED_SENTINEL`. The substrate's `secrets`-merge at lines 1131-1148 in the generic path would normally do this; the L4 collect hook reimplements it for the typed BOT_TOKEN field.
- **Advanced kv-table disclosure**: render a `<details>` element (HTML native) labeled "Advanced (kv-table)". Inside, mount `renderConfigKvTable(account)` — the EXISTING generic kv-table render, unmodified. L3's effective-reserved-keys composition (with the entry's `reservedConfigKeys: ['intents', 'guilds', 'presence']`) ensures the typed keys do not appear as rows in the kv-table. The `<details>` is closed by default. `data-testid="discord-advanced-kv-disclosure"`.
- **Dirty-tracker integration via TWO optional entry hooks** (load-bearing — design-review-2 finding): the existing dirty-tracker at `attachStaticListeners` (lines 796-813) only delegates to elements carrying `.field-input` or `.field-select` AND living inside an `.editor-section`. Bare checkboxes, raw `<input>`, and `<select>` outside that pattern do NOT trigger `checkDirty`. Two coordinated extensions resolve this:
  1. **`getFormSnapshot` extension** (line 650+): substrate calls `entry.snapshot?.(container)` if defined; the returned JSON-serializable object lands under a new top-level `typedFields` key. When `entry.snapshot` is absent (the `'stub'`/unregistered path), the snapshot object MUST NOT contain a `typedFields` key at all — no `typedFields: undefined`, no key-reordering — so the snapshot remains byte-identical for unregistered types (preserves L3's `'stub'`-test stability).
  2. **`wireEvents(container, checkDirty)` entry hook** (NEW — registry-entry-shape extension): the substrate's `wireEditorEvents` calls `entry.wireEvents?.(container, checkDirty)` once after the existing `attachStaticListeners` runs. The entry attaches its own `input`/`change` listeners to the typed inputs that don't carry `.field-input` / `.field-select` (the intent checkboxes, the presence `<select>`, the BOT_TOKEN show/hide toggle). Each listener calls `checkDirty` so the dirty-tracker re-snapshots. **Why an entry hook over class-on-input**: class-on-input is fragile to future styling drift (the dirty-tracker scope-selector could change); the entry hook keeps DOM coupling local to the entry and matches the `snapshot` extension's shape (both are optional registry-entry methods).
- **Entry-shape extension is additive**: the registry's `_validateEntry` accepts `snapshot` and `wireEvents` as OPTIONAL; if present, both MUST be functions; if absent, no error. The 4 required fields (`type`, `renderConnectionFields`, `renderCredentialsFields`, `collect`) plus `reservedConfigKeys` array stay REQUIRED.
- **`renderConfigKvTable` namespace exposure**: REQUIRED for L4 — the entry's Advanced disclosure must mount the existing generic kv-table. Expose as `window.App.studio.renderConfigKvTable` at the end of the `connector-account-editor.js` IIFE (alongside the existing `window.App.studio.renderConnectorAccountEditor` export). The function body is UNCHANGED — only its accessibility extends.
- **Vocabulary substitution NOT in scope for L4**: L4 still uses generic "Peers / Channels" labels in the Allowlist section. L6 swaps them to Discord vocabulary. L4 only typed-shapes the Connection + Credentials sections. Banner / badge polish DROPPED from L4 entirely (defer to L6 if pursued).

## Inputs

Files that must exist:
- `the_one/interfaces/web/static/js/areas/studio/connector-form-registry.js` (L3 substrate — extension here: `snapshot` field added to entry-validator as OPTIONAL)
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` (existing 2530+ lines — `getFormSnapshot:650`, `MASKED_SENTINEL` constant, secret-row rendering at lines 633-643)
- `the_one/interfaces/web/static/index.html` (new `<script>` for the Discord entry file, AFTER connector-form-registry.js, BEFORE connector-account-editor.js)
- `tests/browser/test_flow_studio_connector_account_editor.py` and friends (regression gates — L4's `'discord'` entry MUST NOT affect `'stub'`-type flows)
- `tests/browser/seeders.py` (read for existing seed pattern, possibly extend for Discord seed if not present)
- L2 validator + L3 registry are already landed.

## Outputs

State changes after this leg:
- **NEW FILE** `the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js` (~250-350 LOC): IIFE-wrapped ES5 module that, at load time, calls `App.studio.connectorFormRegistry.register('discord', {discord-entry})`. The entry implements `renderConnectionFields`, `renderCredentialsFields`, `collect`, optional `snapshot`, and declares `reservedConfigKeys: ['intents', 'guilds', 'presence']`.
- **Modified** `index.html`: new `<script src="/static/js/areas/studio/connector-form-discord.js"></script>` line inserted AFTER `connector-form-registry.js` and BEFORE `connector-account-editor.js`. Three adjacent script tags.
- **Modified** `connector-form-registry.js`: the entry-shape validator accepts `snapshot` as OPTIONAL — if present, must be a function; if absent, no error. The entry's other 5 fields stay REQUIRED.
- **Modified** `connector-account-editor.js:getFormSnapshot` (line 650+): add a registry-consult that captures the typed-field snapshot when `entry.snapshot` is defined; serialize under a new `typedFields` top-level key in the JSON snapshot.
- **NEW TEST FILE** `tests/browser/test_flow_studio_connector_discord_form.py` (~150-250 LOC): browser tests exercising the Discord-shaped form end-to-end — create-mode renders typed fields after type-select; edit-mode renders typed fields with persisted values; intent checkbox toggles dirty-tracker; saving with intents change posts the typed config payload; saving without changes round-trips byte-identical config; Advanced kv-table disclosure renders with reserved keys hidden; BOT_TOKEN masked-edit round-trips through `MASKED_SENTINEL`.
- **Modified** `tests/browser/seeders.py`: extend `seed_connector_account` to accept a `type='discord'` shape with optional `config={intents/guilds/presence}` IF the existing seeder doesn't already support it. Read first; extend additively.

## Acceptance Criteria

- [ ] `the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js` exists; IIFE-wrapped ES5; calls `App.studio.connectorFormRegistry.register('discord', {entry})` at module load.
- [ ] The entry's `renderConnectionFields(account, isCreate)` returns HTML mounting four sections (in order): Intents (three checkboxes labelled "Message Content", "Server Members", "Servers"; each checked by default OR per account.config.intents); Guilds (single comma-separated input, help-text "Comma-separated Discord guild IDs (digit-only)"); Presence (name input + type dropdown with the 5 L2-pinned values + empty default option); Advanced disclosure (`<details>` wrapping `renderConfigKvTable(account)`).
- [ ] The entry's `renderCredentialsFields(account)` returns HTML mounting one typed BOT_TOKEN secret input with masked-edit (reuses `MASKED_SENTINEL` + `data-original-masked` attributes); show/hide eye toggle present.
- [ ] The entry's `collect(container, account, isEdit) → {config, secrets}` reads typed-input values and produces a structured payload:
  - `intents` emitted ONLY IF (any checkbox != True) OR (account.config.intents was already present). Three-key dict.
  - `guilds` emitted as `string[]` (split on comma, trimmed, empties dropped) ONLY IF non-empty OR account.config.guilds was already present.
  - `presence` emitted ONLY IF (name input non-empty) OR (type dropdown non-default) OR (account.config.presence was already present). Dict carries only the populated keys.
  - `BOT_TOKEN` emitted under `secrets` — `MASKED_SENTINEL` when input value equals `_originalMasked`, else the new value.
- [ ] The entry declares `reservedConfigKeys: ['intents', 'guilds', 'presence']`. L3's `collectConfigRows` effective-reserved composition hides these from the Advanced kv-table.
- [ ] The entry optionally declares `snapshot: (container) → object` that returns a JSON-serializable object of the typed-input state: `{intents: {message_content, members, guilds}, guildsList: <str>, presenceName: <str>, presenceType: <str>, botTokenValue: <str>}` — note `botTokenValue` is the RAW input value (not a derived "changed" flag) for symmetry with the secrets-row snapshot pattern. Used by the dirty-tracker.
- [ ] The entry optionally declares `wireEvents: (container, checkDirty) → void` that attaches `input` / `change` listeners to the typed inputs that don't carry `.field-input` / `.field-select` classes (intent checkboxes, presence-type `<select>`, BOT_TOKEN field, show/hide eye toggle). Each listener invokes `checkDirty` so the dirty-tracker re-snapshots after every operator edit.
- [ ] `connector-form-registry.js:register` accepts BOTH optional fields (`snapshot`, `wireEvents`) — must be functions if present; throws `TypeError` if defined but not a function; throws no error if absent. The 4 required entry functions + `reservedConfigKeys` array stay required.
- [ ] `connector-account-editor.js:getFormSnapshot` consults the registry for `entry.snapshot`; when present, the returned object is serialized into the JSON snapshot under a new `typedFields` key. **Byte-stability**: when `entry.snapshot` is ABSENT (registry has no entry for the active type, e.g. `'stub'`), the snapshot object MUST NOT carry a `typedFields` key — no `typedFields: undefined` placeholder, no key-reordering of the existing snapshot shape. Verified by an assertion in the new browser test that the `'stub'`-type snapshot is byte-identical to today's baseline.
- [ ] `connector-account-editor.js:wireEditorEvents` calls `entry.wireEvents?.(container, checkDirty)` once after `attachStaticListeners` runs. When `entry.wireEvents` is absent → no-op; existing behavior preserved for unregistered types.
- [ ] `window.App.studio.renderConfigKvTable` is exposed at the end of `connector-account-editor.js`'s IIFE — REQUIRED for L4's Advanced disclosure to mount the existing generic kv-table. The function body is UNCHANGED.
- [ ] An existing `'discord'` account with no `config.intents` / `config.guilds` / `config.presence` keys, opened in edit mode and saved with NO changes (operator clicks Save without editing anything), round-trips the API payload byte-identically — none of the three keys are added to `config`.
- [ ] An existing `'discord'` account with `config.intents = {message_content: True, members: True, guilds: True}` round-trips that exact shape on no-change save (the operator's prior explicit choice is preserved even though all three are True).
- [ ] Toggling any intent checkbox makes the form dirty (Save enables); saving emits `config.intents` with the toggled shape.
- [ ] Adding a guild ID via the comma-separated input makes the form dirty; saving emits `config.guilds: ["<id>"]`.
- [ ] The Advanced `<details>` disclosure renders with `intents`, `guilds`, `presence` keys NOT appearing as kv-table rows (L3 reserved-keys composition).
- [ ] BOT_TOKEN masked-edit: a no-change save round-trips `BOT_TOKEN: "__MASKED__"`; a value-edit save sends the new plaintext.
- [ ] L2's validator accepts the typed-shape payloads at create + update API endpoints — confirmed by the new browser tests' successful save round-trips.
- [ ] Existing browser tests against `'stub'` connector type pass UNMODIFIED (L3's wrapper contract is preserved; the `'discord'` entry's existence doesn't affect `'stub'`-type rendering).
- [ ] New browser test file `test_flow_studio_connector_discord_form.py` exercises: create-mode-types-discord-renders-typed-fields, edit-mode-renders-persisted-intents, intent-toggle-dirty, guilds-add-saves, presence-set-saves, advanced-disclosure-hides-reserved-keys, bot-token-masked-roundtrip.
- [ ] Full suite `docker exec the-one pytest -x --timeout 60 -q -m "not pixel"` at or above the L3 baseline (with the L3 additions; failures pre-existing).

## Implementation Guidance

1. **Read L3's `connector-form-registry.js` + the L3 consult sites in `connector-account-editor.js`** to confirm the contract before writing the entry.
2. **Read existing secret-row rendering** at `connector-account-editor.js:633-643` and `MASKED_SENTINEL` handling at `collectFormData:1142-1147` — mirror the masked-edit pattern in the typed BOT_TOKEN field.
3. **Create `connector-form-discord.js`** as IIFE ES5 (mirror `connector-form-registry.js` shape). At the bottom, call `App.studio.connectorFormRegistry.register('discord', {entry})`. Define the entry inline — its 5 (or 6 with snapshot) functions live in the module scope.
4. **Add the script tag** to `index.html` AFTER `connector-form-registry.js` and BEFORE `connector-account-editor.js`. Three adjacent script tags total.
5. **Extend `connector-form-registry.js:_validateEntry`** to accept TWO OPTIONAL fields: `if (entry.snapshot !== undefined && typeof entry.snapshot !== 'function') throw new TypeError(...)` and the same shape for `wireEvents`. The required-fields loop is unchanged.
6. **Extend `connector-account-editor.js:getFormSnapshot`** (line 650+): after the existing `static`/`config`/`secrets`/`allowlist`/`routing` snapshot construction (line 705), do a registry consult; if `entry.snapshot` is a function, call it with `container` and add the result under a new `typedFields` key in the snapshot object before `JSON.stringify`. **Critical**: only add the `typedFields` key when `entry.snapshot` is actually defined and returns a non-undefined value. Use a guard `if (entry && typeof entry.snapshot === 'function') { var typed = entry.snapshot(container); if (typed !== undefined) snapshotObj.typedFields = typed; }` so unregistered types continue to produce byte-identical snapshots.
6b. **Extend `connector-account-editor.js:wireEditorEvents`** (line 716+): at a position AFTER `attachStaticListeners(container, checkDirty)` runs, consult the registry; if `entry.wireEvents` is a function, call it with `(container, checkDirty)`. Use the triple-guard for registry access. The entry's `wireEvents` is responsible for ALL typed-input dirty-tracking wiring; the substrate does no per-input-type dispatch.
6c. **Expose `renderConfigKvTable`**: at the end of `connector-account-editor.js`'s IIFE (where existing `window.App.studio.renderConnectorAccountEditor = renderConnectorAccountEditor;` exists, ~line 2416), add `window.App.studio.renderConfigKvTable = renderConfigKvTable;`. The function body is untouched.
7. **Render the BOT_TOKEN field** with `data-field="bot-token"`, `data-testid="discord-bot-token"`, masked value initially shown with `_originalMasked` attribute; eye-icon toggle changes `type` between `password` and `text`. Use the existing `App.icon('eye')` / `App.icon('eye-off')` calls if present.
8. **Render the three intent checkboxes** in a `<fieldset>` labelled "Intents" with help text "Discord gateway intents — controls which event types the bot receives. All on is the safe default; disable individual intents only if you understand the consequences." Each `<input type="checkbox" data-field="intent-<axis>" data-testid="discord-intent-<axis>">`.
9. **Render the guilds input** as a single text input `<input type="text" data-field="guilds-list" data-testid="discord-guilds-list">`, help-text below. The value is comma-joined; the collect hook splits.
10. **Render the presence editor** as two inputs side-by-side: `<input data-field="presence-name" data-testid="discord-presence-name">` for name, `<select data-field="presence-type" data-testid="discord-presence-type">` with the 5 options + empty default.
11. **Render the Advanced disclosure**: `<details class="discord-advanced-kv-disclosure" data-testid="discord-advanced-kv-disclosure"><summary>Advanced (kv-table)</summary>` then call `renderConfigKvTable(account)` (the existing global; expose it from `connector-account-editor.js` via the `window.App.studio` namespace if not already exposed — read first). Closing `</details>`.
12. **The collect hook** reads each typed input by `data-field` (use `container.querySelector(...)`); applies the "emit only on change or pre-existing" logic from Design Decisions §§ 2-4; returns `{config: {...}, secrets: {BOT_TOKEN: ...}}`.
13. **The snapshot hook** returns `{intents: {message_content, members, guilds}, guildsList: <str>, presenceName: <str>, presenceType: <str>, botTokenValue: <str>}` — JSON-serializable; `botTokenValue` is the RAW input value (matches the secrets-row snapshot pattern; a derived "changed" flag is rejected per cycle-1 review). The substrate's `JSON.stringify` covers the rest.
14. **Wire change-events via the entry's `wireEvents` hook** — the existing dirty-tracker's `attachStaticListeners` (lines 796-813) only delegates to `.field-input` / `.field-select` elements inside `.editor-section`. L4's typed inputs (intent checkboxes, presence-type `<select>`, BOT_TOKEN, show/hide eye) live OUTSIDE that delegation. The entry's `wireEvents(container, checkDirty)` hook MUST attach explicit `input` and `change` listeners to each typed input that calls `checkDirty`. Implementation shape: for each typed input, `container.querySelector('[data-field="..."]').addEventListener('change', checkDirty);` plus `addEventListener('input', checkDirty)` for the text-type inputs (BOT_TOKEN, presence-name, guilds-list). The substrate's `wireEditorEvents` invokes the hook AFTER `attachStaticListeners` so the entry's wiring is additive.
15. **Create browser tests** in `tests/browser/test_flow_studio_connector_discord_form.py` — mirror the shape of `test_flow_studio_connector_account_editor.py`. Use `seed_connector_account(type='discord', config={...}, secrets={'BOT_TOKEN': 'plaintext'})` — extend the seeder if needed.
16. **Run regression suite** after implementation: existing `'stub'`-type tests + L3 registry-contract tests + the new Discord-form tests + full suite.

## Edge Cases

- **Operator creates a new Discord account** (no existing config): all three intent checkboxes default to checked; saving without toggling emits no `config.intents` key (matches L4 Design Decisions §2). The API validator accepts the absence; the plugin's L2 fallback reads `account.config.get("intents", {})` and defaults to all True. Round-trip with no L4-introduced surprise key.
- **Operator opens an existing M10 F8 account** (config has no intents/guilds/presence): typed fields render at their defaults; saving without changes makes Save stay disabled (no dirty); the operator must explicitly edit something to enable Save. Matches existing dirty-tracker behavior.
- **Operator types a non-digit guild ID** ("foo"): the input accepts it (no inline JS validation); on save, L2's validator returns 422 with the verbatim detail string. The operator sees the field-level error (the substrate's existing `setFieldError` path renders the 422 detail near the field; verify the substrate's existing 422-error path is generic enough to surface the validator's detail string — if not, this is a future polish task, not L4 scope).
- **Operator opens edit mode with `config.intents = {message_content: False, members: True, guilds: True}`** (operator previously disabled message_content): the three checkboxes show False/True/True; saving without change emits `config.intents` unchanged (preserves operator's prior choice).
- **Race: `connector-form-discord.js` loads BEFORE `connector-form-registry.js`**: would throw because `App.studio.connectorFormRegistry.register` is undefined. The `<script>` ordering in `index.html` MUST ensure registry loads first. Verify before signaling complete.
- **`'stub'`-type account in edit mode**: registry lookup returns undefined; L3's wrapper contract emits the generic kv-table; `'stub'` flows are unaffected by L4. Confirmed by existing browser tests passing UNMODIFIED.
- **Empty guilds string after operator deletes all entries**: collect hook returns empty list. If `account.config.guilds` was previously non-empty, emit empty list to honor the operator's intent (they cleared it); if it was absent, omit the key.

## Files Affected

- `the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js` — NEW FILE; ~250-350 LOC.
- `the_one/interfaces/web/static/js/areas/studio/connector-form-registry.js` — additive `snapshot` validation in `_validateEntry`.
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — `getFormSnapshot` extended with `typedFields` key via registry consult. Possibly expose `renderConfigKvTable` on `window.App.studio` if not already.
- `the_one/interfaces/web/static/index.html` — one new `<script>` tag.
- `tests/browser/test_flow_studio_connector_discord_form.py` — NEW FILE; ~150-250 LOC.
- `tests/browser/seeders.py` — possibly extend `seed_connector_account` for Discord seed (read first).
- `missions/.../flight-log.md` — Leg Progress entry.
- `missions/.../legs/04-discord-shaped-form.md` — status transitions.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Existing browser tests pass UNMODIFIED — `'stub'`-type flows unaffected
- [ ] New Discord-form tests pass
- [ ] Full suite at or above L3 baseline; new tests add to the count
- [ ] No backend / API / DB changes (the API surface is L2; the substrate is L3; L4 is frontend-only + one optional validator extension)
- [ ] Update flight-log.md with Leg Progress entry
- [ ] Set this leg's status to `landed`
- [ ] Do NOT check off the leg in flight.md
- [ ] Do NOT commit

## Citation Audit

Citations verified at leg design time (2026-05-21, post-L3):

- `connector-account-editor.js:getFormSnapshot` — verified at line 650; serializes `{static, config, secrets, allowlist, routing}` via `JSON.stringify`; insertion point for `typedFields` key is line 705.
- `connector-account-editor.js:renderConfigKvTable` — verified at line 622; not currently exposed on `window.App.studio` namespace (function is IIFE-local); needs additive exposure for the L4 entry to call it.
- `connector-account-editor.js:MASKED_SENTINEL` — verified the existing constant + use pattern at lines 1142-1147 (secrets-merge); typed BOT_TOKEN field reuses.
- `connector-account-editor.js:wireEditorEvents` — verified at line 716+; calls `attachStaticListeners(container, checkDirty)` at lines 796-813 which delegates ONLY to `.field-input` / `.field-select` elements inside `.editor-section`. Bare typed inputs (checkboxes, raw `<input>`, `<select>` without those classes) are NOT covered by the delegation. L4's typed inputs deliberately live OUTSIDE that pattern; the new `entry.wireEvents(container, checkDirty)` hook (called once from `wireEditorEvents` after `attachStaticListeners` runs) is the explicit wiring path for the typed inputs.
- L3's `connector-form-registry.js` — landed; `_validateEntry` shape covered in L3 leg artifact §2.
- L2's `_validate_connector_account_config` — landed; accepts the typed shapes L4 emits.
- `the_one/interfaces/web/static/css/tokens.css:158` — verified `--badge-discord: #5865F2`; available for the optional banner polish.
- `tests/browser/seeders.py:seed_connector_account` — exists; signature needs reading to confirm Discord-shape support before extension.

Eight citation clusters verified live.
