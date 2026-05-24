# Leg: discord-dropdown-allowlist

**Status**: completed
**Flight**: [Live-Data Discoverable Dropdowns](../flight.md)

## Objective

Refactor `connector-account-editor.js:renderAllowlistSection` (the 4-axis account-scope allowlist editor) to consult the L5-shipped registry-entry hook `renderDiscoverableDropdown(account, axis, currentValues, vocab, onChange)`. For Discord accounts, the editor now renders dropdown components per axis (peers/channels/guilds/roles) instead of chip-list editors. For stub-type accounts (and any type without the registry hook), the existing chip-list editor renders UNMODIFIED — that is the regression contract. Bundle in the deferred F2 debrief item: consolidate the `connector-form-registry.js` top-comment optional-hook table.

## Context

- L5 landed: `App.studio.discoverableDropdown` component callable; `connector-form-registry.js:optionalFns` at n=5; Discord per-type entry exposes `renderDiscoverableDropdown` delegating to the component.
- **Design Decision — registry-mediated dispatch for allowlist UI** (flight.md L6a scope): `renderAllowlistSection` consults `connector-form-registry.get(account.type)` per axis. If the entry exists AND exposes `renderDiscoverableDropdown`, the section mounts the dropdown component on that axis. Otherwise, the section falls back to the existing `_buildAllowlistChipList(kind, items)` chip-list editor — byte-identical render for stub-type accounts (the regression contract).
- **Design Decision — onChange wiring + collect-path via per-slot getter** (this leg's resolution to cycle-1 HIGH #1): there is NO internal-state store in the editor today — `collectAllowlistFromContainer` (`connector-account-editor.js:2657-2674`) reads chip values by walking the DOM chip `.chip` text nodes. The dropdown's `.chip` shape is structurally different (label in a `<span class="discoverable-dropdown-chip-label">` child + canonical id in `data-id`), so direct DOM reading breaks. **Resolution**: `_mountAllowlistAxisEditor` installs a getter on the slot element: `slotEl._allowlistValues = () => state.currentValues.slice()`. `collectAllowlistFromContainer` is refactored to check for this getter first; if present, uses it; if absent (chip-list path), falls back to the existing text-node walk. Same change for `getFormSnapshot`'s allowlist branch (L858 area) — the dirty-tracker must observe dropdown changes for `checkDirty` to fire. The dropdown's `onChange(newValues)` callback (1) updates the component's internal state (already done by the component), (2) calls `checkDirty()` to trigger the dirty-tracker. No separate "internal state" data store needed; the getter wraps the dropdown's own state.
- **Design Decision — storage-axis vs API-axis name mapping** (this leg's resolution to cycle-1 HIGH #2): storage uses axis `'guilds'` (per `account.config.allowlist.guilds` at L2618-2622 + slot key at L1823); the L4 API + L5 dropdown use axis `'groups'` (per the L3 `DiscoverableEntities` dataclass shape). `_mountAllowlistAxisEditor` translates: when invoking the dropdown, maps storage `'guilds'` → API `'groups'`; the dropdown's `onChange(newIds)` returns ids that are written back to storage under `'guilds'`. The translation is bidirectional, centralized in the mount helper. Other 3 axes (`peers`, `channels`, `roles`) are name-identical across storage and API.
- **Design Decision — create-mode AC NOT applicable** (this leg's resolution to cycle-1 HIGH #3): `renderAllowlistSection` is structurally edit-mode-only (gated at `connector-account-editor.js:405` on `!isCreate`; `wireAllowlistEvents` gated on `isEdit` at L1210). Per the `registry-dispatch-create-mode-AC` convention itself: "Does NOT apply when the dispatch key is structurally guaranteed at mount." Allowlist UI does not render in create mode → no dispatch-key-absent transition exists for this surface. The create-mode-after-type-pick AC for L6a is therefore NOT applicable; the previous spec's `test_create_mode_after_picking_discord_renders_dropdown` test is dropped. The leg covers the convention's spirit by ensuring no crash + no fetch fires in create mode for Discord (a defensive sibling test below).
- **Design Decision — registry-dispatch-create-mode-AC compliance** (F1 L1 codified): the refactor MUST verify BOTH create-mode-after-type-pick (operator picks Discord in create form → typed dropdown renders) AND edit-mode-with-type-set (open existing Discord account → typed dropdown renders) paths. Both ACs in the test suite below.
- **Design Decision — F2 debrief item bundle** (flight.md L6a scope): consolidate the `connector-form-registry.js` top-comment optional-hook table. The current top-comment (lines 1-40) describes the entry shape but doesn't carry a single reference table listing all 5 optional hooks with their signatures. L6a adds that table.
- **Codebase recon** (verified at design):
  - `connector-account-editor.js:1774` `renderAllowlistSection(account)` — returns HTML string. Iterates 4 axes (`peers`, `channels`, `guilds`, `roles`) emitting per-axis sections with `<div data-allowlist-chiplist-slot="{axis}"></div>` slots (lines 1805-1833).
  - The chip-list editors are mounted into those slots in `wireAllowlistEvents(container, account, checkDirty)` at `connector-account-editor.js:2609-2642`. Internal closure `_mountChipList(slot, kind, init)` at L2629-2637 does the per-axis chip-list mount + `adminFormHelpers.wireChipListEditor(chiplist, { onChange: checkDirty })` wiring at L2634-2636. L6a refactors `_mountChipList` to consult `_mountAllowlistAxisEditor` (the new dispatch helper) for the dropdown-path; falls back to chip-list when the registry has no `renderDiscoverableDropdown` for the account type.
  - `collectAllowlistFromContainer` at L2657-2674 reads chip values via text-node walk on `.chip` elements — INCOMPATIBLE with the dropdown's chip shape. L6a refactors to check for the `_allowlistValues` getter on the slot first (set by `_mountAllowlistAxisEditor` for the dropdown path); falls back to text-node walk when absent (chip-list path).
  - `getFormSnapshot` (around L858) also walks the allowlist DOM for dirty-tracker comparison — same refactor pattern needed for symmetry. (Verify the snapshot helper's allowlist branch at implementation time.)
  - Dirty-tracker integration: `checkDirty` closure (defined at L909-919), threaded through `wireAllowlistEvents`'s parameter. The dropdown path's `onChange(newValues)` callback invokes `checkDirty()` directly (matches the chip-list's `wireChipListEditor` `onChange: checkDirty` pattern).
  - `connector-account-editor.js:_buildAllowlistChipList(kind, items)` at L1856 returns a DOM element. Continues to render unchanged for stub-type fallback.
  - F6 chip-list browser tests live at `tests/browser/test_flow_studio_connector_account_editor.py`. They MUST continue to pass byte-identically for stub-type accounts.
- L1's `flight-spec-dom-order-audit` convention: verify the slot DOM structure at the actual current state of the file before claiming line numbers.

## Inputs

- L5 has landed: `App.studio.discoverableDropdown`, `connector-form-registry.optionalFns` at n=5, Discord entry's `renderDiscoverableDropdown` bridge.
- `connector-account-editor.js` exists with `renderAllowlistSection` at ~L1774 and `_buildAllowlistChipList` at ~L1856.
- F6 + F8 chip-list tests at `tests/browser/test_flow_studio_connector_account_editor.py` pass currently.
- Discord per-type entry registered in the registry (verified by L5 test).

## Outputs

- `connector-account-editor.js` modified:
  - **NEW helper `_mountAllowlistAxisEditor(slotEl, account, storageAxis, currentValues, vocab, checkDirty)`** — the dispatch primitive. Signature note: the function receives the STORAGE axis name (`'peers'`/`'channels'`/`'guilds'`/`'roles'`) and translates internally:
    - Looks up `entry = App.studio.connectorFormRegistry.get(account.type)`.
    - If `entry && typeof entry.renderDiscoverableDropdown === 'function'`:
      - Maps `apiAxis = storageAxis === 'guilds' ? 'groups' : storageAxis`.
      - Defines `onChange(newValues) { state.values = newValues; checkDirty(); }` where `state` is the helper's closure.
      - Calls `entry.renderDiscoverableDropdown(account, apiAxis, currentValues, vocab, onChange)`.
      - Mounts the returned element; installs `slotEl._allowlistValues = () => state.values.slice()` for the collect path.
      - Initialize `state.values = currentValues.slice()`.
    - Otherwise (chip-list fallback path):
      - Builds the chip-list via `_buildAllowlistChipList(storageAxis, currentValues)`.
      - Appends to slot.
      - Wires `helpers.wireChipListEditor(chiplist, { onChange: checkDirty })` per the precedent at `connector-account-editor.js:2634-2636`.
      - Does NOT install `slotEl._allowlistValues` — the collect path's fallback (text-node walk) handles chip-list reads.
  - **`renderAllowlistSection(account)` itself unchanged** in its HTML shape (still emits the per-axis slot divs). The dispatch is at MOUNT time, not RENDER time — preserves the existing render-then-wire pattern.
  - **Refactor `wireAllowlistEvents`** at L2609-2642: replace the inline `_mountChipList(slot, kind, init)` closure with a call to `_mountAllowlistAxisEditor(slotEl, account, kind, init, vocab, checkDirty)` per axis. `vocab` is the existing `_vocabForAccount(account)` result already available in the editor scope.
  - **Refactor `collectAllowlistFromContainer`** at L2657-2674: for each axis, check `slotEl._allowlistValues` first; if a function, call it; otherwise fall back to the existing text-node-walk per axis. Returns the same shape `{peers, channels, guilds, roles}` for `account.config.allowlist`.
  - **Refactor the `getFormSnapshot` allowlist branch** (around L858): symmetric to `collectAllowlistFromContainer` — uses `_allowlistValues` when present, falls back to DOM walk. This is what `checkDirty` compares against.

- `connector-form-registry.js` modified — top-comment optional-hook table (the deferred F2 debrief bundle):
  - The top-comment block (lines 1-40) gets a new dedicated section "## Optional Hooks (each function-if-present)" listing all 5 optional hooks with their signatures and one-line descriptions:
    ```
    ## Optional Hooks (each function-if-present per `_validateEntry`)
    - snapshot(container) → object: per-type typed-state snapshot for the dirty-tracker (F1 L4)
    - wireEvents(container, checkDirty, account) → void: per-type listener wiring outside the substrate's delegation (F1 L4)
    - renderInviteSection(account) → string: per-type detail-page HTML section (F1 L5)
    - renderDirectiveSection(account, params) → HTMLElement: per-type per-account directive surface (F2 L4)
    - renderDiscoverableDropdown(account, axis, currentValues, vocab, onChange) → HTMLElement | null: per-type axis-specific live-data dropdown (F3 L5)
    ```
  - No other changes to the file; the array literal at L98 and the validator code path stay byte-identical.

- New tests in `tests/browser/test_flow_studio_connector_account_editor.py` (or a sibling file `tests/browser/test_flow_studio_connector_allowlist_dropdown.py`):
  - `test_allowlist_axis_renders_dropdown_for_discord_account` — open an existing Discord account; assert each of the 4 axes has a `[data-testid^="discoverable-dropdown-"]` element (NOT the chip-list).
  - `test_allowlist_axis_renders_chiplist_for_stub_account` — open an existing stub-type account; assert each axis has the EXISTING chip-list testid `[data-testid="connector-allowlist-{axis}-chiplist"]` (per `connector-account-editor.js:1860` — testid prefix is `connector-allowlist-`, NOT `connector-allowlist-chiplist-`).
  - `test_allowlist_dropdown_onChange_updates_account_config_allowlist` — open Discord account; select an item from the channels dropdown; save; reload; assert `account.config.allowlist.channels` includes the selected id. (Tests the full collect-path through the `_allowlistValues` getter.)
  - `test_allowlist_dropdown_chip_remove_updates_account_config_allowlist` — open Discord account with pre-selected channels; click a chip's × button; save; reload; assert the removed id is gone from `account.config.allowlist.channels`.
  - `test_allowlist_storage_axis_guilds_maps_to_api_groups` — open Discord account; verify the guilds-axis slot mounts a dropdown whose component-internal axis is `'groups'` (verifiable via the dropdown's outermost `data-axis="groups"` attribute on the mounted element). Pin the storage↔API axis translation.
  - `test_create_mode_discord_does_not_render_allowlist` (defensive coverage of the `registry-dispatch-create-mode-AC` "structurally guaranteed" exclusion): open create-account form; pick Discord; assert no `[data-testid^="connector-allowlist-"]` elements exist AND no GET to `/api/connector-accounts/*/discoverable-entities` fires.

- Existing F6/F8 chip-list tests at `tests/browser/test_flow_studio_connector_account_editor.py` MUST pass UNMODIFIED for stub-type accounts (the regression contract).

## Acceptance Criteria

- [x] `connector-account-editor.js` has a NEW helper `_mountAllowlistAxisEditor(slotEl, account, storageAxis, currentValues, vocab, checkDirty)` that dispatches to either the registry's `renderDiscoverableDropdown` (when present) or the existing chip-list mount + `wireChipListEditor` (when absent).
- [x] Inside `_mountAllowlistAxisEditor`, storage axis `'guilds'` translates to API axis `'groups'` before passing to the dropdown; other axes pass through unchanged.
- [x] When taking the dropdown path, `_mountAllowlistAxisEditor` installs `slotEl._allowlistValues = () => state.values.slice()` for the collect path.
- [x] `wireAllowlistEvents` at L2609-2642 refactored to call `_mountAllowlistAxisEditor` per axis (replacing the inline `_mountChipList` closure).
- [x] `collectAllowlistFromContainer` at L2657-2674 refactored to consult `slotEl._allowlistValues` first; falls back to existing text-node walk when absent. Returns `{peers, channels, guilds, roles}` shape unchanged.
- [x] `getFormSnapshot` allowlist branch (around L858) similarly refactored — uses `_allowlistValues` when present, falls back to DOM walk. Symmetric to `collectAllowlistFromContainer`.
- [x] For Discord accounts, all 4 axes (peers, channels, guilds, roles) render `discoverable-dropdown` components.
- [x] For stub-type accounts, all 4 axes render the existing chip-list editors — DOM byte-identical to pre-L6a state.
- [x] `renderAllowlistSection`'s returned HTML shape is unchanged (per-axis slot divs preserved).
- [x] Selecting an item in the dropdown writes the new id array to the editor's internal allowlist state for that axis AND triggers the dirty-tracker.
- [x] Removing a chip via × button does the same.
- [x] Save round-trip persists the selected ids in `account.config.allowlist.{axis}`; reload shows them.
- [x] `connector-form-registry.js` top-comment has a new "## Optional Hooks" section listing all 5 hooks with signatures.
- [x] The 5 new browser tests are added and pass.
- [x] Existing chip-list tests at `tests/browser/test_flow_studio_connector_account_editor.py` continue passing byte-identically for stub-type accounts.
- [x] No changes to L5's component file (`discoverable-dropdown.js`), to the L4 API endpoints, or to the L3 substrate. L6a is purely consumer-integration.
- [x] `git diff --stat` shows changes only in: `connector-account-editor.js`, `connector-form-registry.js`, `tests/browser/test_flow_studio_connector_account_editor.py` (or sibling), plus F3 sibling artifacts.

## Verification Steps

- `grep -n "_mountAllowlistAxisEditor\|renderDiscoverableDropdown" the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — the new helper appears; the registry consultation appears in the helper body.
- `grep -n "## Optional Hooks" the_one/interfaces/web/static/js/areas/studio/connector-form-registry.js` — top-comment table present.
- `docker exec the-one pytest tests/browser/test_flow_studio_connector_account_editor.py -x --timeout 60 -q -m browser` — existing tests pass; new tests pass.
- `docker exec the-one pytest tests/browser/test_flow_studio_connector_discoverable_dropdown.py tests/browser/test_connector_form_registry.py -x --timeout 60 -q -m browser` — L5 tests still pass.

## Implementation Guidance

1. Read the current state of `connector-account-editor.js` around `renderAllowlistSection` (~L1774) AND the wiring site that calls `_buildAllowlistChipList` for each axis (search for `_buildAllowlistChipList` references). Confirm the actual current line numbers and the wire-up flow per `flight-spec-dom-order-audit` (L1 codified).

2. Implement `_mountAllowlistAxisEditor(slotEl, account, storageAxis, currentValues, vocab, checkDirty)`:
   ```javascript
   function _mountAllowlistAxisEditor(slotEl, account, storageAxis, currentValues, vocab, checkDirty) {
     var state = { values: currentValues.slice() };
     var entry = App.studio.connectorFormRegistry.get(account.type);
     if (entry && typeof entry.renderDiscoverableDropdown === 'function') {
       var apiAxis = (storageAxis === 'guilds') ? 'groups' : storageAxis;
       var dropdownEl = entry.renderDiscoverableDropdown(
         account, apiAxis, state.values, vocab,
         function onChange(newValues) {
           state.values = newValues.slice();
           checkDirty();
         }
       );
       if (dropdownEl) {
         slotEl.innerHTML = '';
         slotEl.appendChild(dropdownEl);
         slotEl._allowlistValues = function() { return state.values.slice(); };
         return;
       }
     }
     // Fallback: chip-list (preserves stub-type behavior).
     var chipListEl = _buildAllowlistChipList(storageAxis, currentValues);
     slotEl.innerHTML = '';
     slotEl.appendChild(chipListEl);
     helpers.wireChipListEditor(chipListEl, { onChange: checkDirty });
     // No _allowlistValues getter installed — chip-list path falls back to text-node walk.
   }
   ```

3. Refactor `wireAllowlistEvents` (L2609-2642) — replace the inline `_mountChipList(slot, kind, init)` closure body with a single call to `_mountAllowlistAxisEditor(slot, account, kind, init, _vocabForAccount(account), checkDirty)`.

4. Refactor `collectAllowlistFromContainer` (L2657-2674) — for each axis slot, check `if (typeof slot._allowlistValues === 'function') return slot._allowlistValues();`; otherwise fall back to the existing chip text-node walk. Output shape unchanged.

5. Refactor `getFormSnapshot` allowlist branch (around L858) — symmetric to step 4. Required for `checkDirty` to detect dropdown changes.

5. Update `connector-form-registry.js` top-comment with the "## Optional Hooks" section.

6. Write the 5 new browser tests. Use `seed_connector_account(app_clean, type='discord', ...)` for Discord; `type='stub'` for stub fallback. The create-mode test uses the goto-create-form flow.

7. Run tests:
   - `docker exec the-one pytest tests/browser/test_flow_studio_connector_account_editor.py -x --timeout 60 -q -m browser`
   - L5 regression: `docker exec the-one pytest tests/browser/test_flow_studio_connector_discoverable_dropdown.py tests/browser/test_connector_form_registry.py -x --timeout 60 -q -m browser`

8. Sibling artifact bookkeeping: check off L6a in flight.md + flight-log; update leg status to landed.

## Edge Cases

- **Pre-existing F6 chip-list onChange**: the chip-list's onChange flow uses `wireChipListEditor`-installed listeners. The dropdown's onChange is a callback param. Both paths write to the same editor-internal state; verify the dirty-tracker fires the same signal in both paths.
- **Empty currentValues**: when an account has no allowlist for an axis, the dropdown mounts with empty chips. Operator can still add via the dropdown. No regression.
- **Discord account with no warm pool entry yet**: the dropdown's first-call inline refresh (L4) handles this. The operator sees "Loading…" briefly then either the entities OR the cold-pre-probe-hint OR empty axes (fail-open).
- **Operator switches connector type in create-mode**: the editor re-renders the allowlist section; the dispatch hits the new type's entry. Per `registry-dispatch-create-mode-AC` convention (F1 L1 codified).

## Files Affected

- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — `_mountAllowlistAxisEditor` helper + wire-up refactor.
- `the_one/interfaces/web/static/js/areas/studio/connector-form-registry.js` — top-comment "## Optional Hooks" section.
- `tests/browser/test_flow_studio_connector_account_editor.py` — 5 new tests.
- F3 sibling artifacts (flight.md, flight-log.md, this leg).

---

## Post-Completion Checklist

- [x] All ACs verified
- [x] All browser tests pass (new + existing chip-list)
- [x] Update flight-log.md with L6a entry
- [x] Set leg status to `landed`
- [x] Check off L6a in flight.md
- [x] Do NOT commit
