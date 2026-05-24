# Leg: discord-dropdown-routing-and-overlay

**Status**: completed
**Flight**: [Live-Data Discoverable Dropdowns](../flight.md)

## Objective

Apply L6a's registry-dispatch pattern to TWO additional consumer surfaces:
1. The routing-rules editor's match-value cell (`connector-account-editor.js:_wireRoutingMatchChiplist` at L2177). Per-row dispatch keyed off the row's `data-routing-scope` value (which determines the axis the match values target).
2. The per-agent overlay editor (`connectors-tab.js:_renderAccountTile`'s chip-mode-axis subset). For Discord-attached accounts in chip-mode (account-scope is non-empty), the per-axis chip-list swaps to the discoverable dropdown. Checkbox-mode (account-scope is empty/wildcard) stays unchanged — no axis to filter.

Both surfaces fall back to the existing chip-list/free-form text editor for stub-type accounts. Existing F6 + F7 + F8 browser tests pass UNMODIFIED for stub-type accounts (the regression contract).

## Context

- L6a landed the dispatch pattern (`_mountAllowlistAxisEditor`) + the `_allowlistValues` getter convention + the storage-`guilds` → API-`groups` axis mapping. L6b reuses these.
- **Design Decision — routing-rules scope → API axis mapping** (this leg's resolution): each routing-rules row has a scope `select` (channel/thread/dm/peer per F7 vocab). The match values target the corresponding API axis. Mapping:
  - scope `'channel'` → API axis `'channels'`
  - scope `'thread'` → API axis `'channels'` (threads are platform-side narrowings of channels; the bot's discoverable view exposes the channel; the operator can pick a channel and the routing engine handles the thread-narrowing at runtime per F7 logic)
  - scope `'dm'` → API axis `'peers'`
  - scope `'peer'` → API axis `'peers'`
  - The dispatch helper accepts `scope` and translates internally.
- **Design Decision — per-row dropdown teardown on scope change**: when the operator changes a row's scope select, the match-value editor MUST re-mount to reflect the new axis. The existing wiring listens for scope changes (L2327); L6b's refactor hooks into that listener to tear down the dropdown and re-mount with the new scope. Avoids stale-dropdown bugs.
- **Design Decision — per-agent overlay scope** (this leg's narrowing): `connectors-tab.js:_renderAccountTile` has two display modes per axis:
  - **Checkbox mode**: when `accountScope.{axis}` is non-empty (operator restricted the account-level allowlist), the per-agent overlay shows one checkbox per scoped entry — the operator can opt the agent INTO a subset of the account-scope. NO chip-list; nothing to convert; OUT of L6b scope.
  - **Chip-mode**: when `accountScope.{axis}` is empty AND the per-agent overlay carries a per-axis override list, the chip-list editor allows free entry. THIS is L6b's target — swap to discoverable dropdown for Discord.

  **Actual codebase shape**: re-walking `connectors-tab.js:60-140` shows the chip-mode path uses a chip-list editor for per-axis overrides only when `accountScope` is empty AND the operator has selected per-agent restrictions. The current code's chip-list mount site is the L6b refactor target. **Mid-leg verification**: the developer confirms the chip-mode path's mount site at implementation time — if the surface turns out to be checkbox-only (no chip-list path in `connectors-tab.js`), the per-agent overlay refactor is a NO-OP for L6b and the leg ships routing-rules only. This is acceptable per the flight Adaptation Criteria's "L6a/L6b may merge ONLY if … the merged leg stays clearly atomic" — even if per-agent overlay turns out to be a no-op, L6b still ships the routing-rules refactor + the test coverage.
- **Codebase recon** (verified at design):
  - `connector-account-editor.js:2154` `wireRoutingRulesEvents(container, account, checkDirty)`.
  - `connector-account-editor.js:2177-2185` `_wireRoutingMatchChiplist(rowEl)` wires `adminFormHelpers.wireChipListEditor(chiplist, { onChange: checkDirty })` per row. This is the per-row mount site L6b refactors.
  - `connector-account-editor.js:2007` row HTML has `data-routing-scope` attribute on a `<select>` element.
  - `connector-account-editor.js:2327` scope-change listener already exists — wraps re-render of the match cell.
  - `connector-account-editor.js:2017` the match-cell HTML has `<div class="chip-list-editor connector-routing-match-chiplist" ...>` — same slot pattern as the allowlist's per-axis slots.
  - `connectors-tab.js:60+` `renderConnectorsTab` + `_renderAccountTile` for the per-agent overlay.
  - Routing-rules collect path: `getFormSnapshot` or a dedicated routing-collect helper reads match values from `.connector-routing-match-chiplist` text-nodes — same DOM-walk vulnerability as the allowlist's pre-L6a state. L6b applies the `_routingMatchValues` getter pattern (mirrors L6a's `_allowlistValues`).

## Inputs

- L6a has landed: `_mountAllowlistAxisEditor` pattern + `_allowlistValues` getter convention; updated `collectAllowlistFromContainer`.
- F6/F7 chip-list tests at `tests/browser/test_flow_studio_connector_account_editor.py` pass currently for both stub and Discord allowlist axes.
- L5's component + L4's API are callable.

## Outputs

- `connector-account-editor.js` modified:
  - NEW helper `_mountRoutingMatchEditor(rowEl, account, scope, currentValues, vocab, checkDirty)` mirroring `_mountAllowlistAxisEditor` shape:
    - Maps scope → API axis: channel→channels, thread→channels, dm→peers, peer→peers.
    - Consults `App.studio.connectorFormRegistry.get(account.type).renderDiscoverableDropdown` for Discord.
    - Calls dropdown with the mapped axis; installs `slotEl._routingMatchValues = () => state.values.slice()` on the chip-list slot for the collect path.
    - Fallback to existing `adminFormHelpers.wireChipListEditor` on stub-type.
  - Refactor `_wireRoutingMatchChiplist(rowEl)` (L2177-2185) to call `_mountRoutingMatchEditor`. The function now takes the row's current `data-routing-scope` value from the row's scope `<select>` and the current match values from the existing chip-list (or row state).
  - Refactor the scope-change listener (L2327 region) to: read the row's new scope value → call `_mountRoutingMatchEditor` to re-mount the match-cell editor with the new axis. Tear-down the previous mount (the `_routingMatchValues` getter and the dropdown DOM are wholesale-replaced).
  - Refactor the routing-collect helper (search for the routing-rules collect path — likely in `collectRoutingRulesFromContainer` or inside `getFormSnapshot`) to consult `slot._routingMatchValues` first; fall back to text-node walk when absent.
- `connectors-tab.js` modified — **conditionally** based on the actual chip-mode-axis path:
  - If a chip-list mount site exists in `_renderAccountTile`'s axis-per-axis rendering: refactor the same dispatch pattern via the registry hook. Install `_overlayChipValues` getter for the collect path; checkbox-mode untouched.
  - If no chip-list mount site exists (the per-agent overlay is purely checkbox-mode by the F6/F7/F8 contract): document this finding in the flight-log and skip the `connectors-tab.js` refactor entirely. L6b ships routing-rules only.
- New tests in `tests/browser/test_flow_studio_connector_routing_dropdown.py` (NEW file):
  - `test_routing_match_renders_dropdown_for_discord_channel_scope` — open Discord account routing-rules, add row with scope='channel', verify the match cell mounts a dropdown with `data-axis="channels"`.
  - `test_routing_match_renders_dropdown_for_discord_peer_scope` — same but scope='peer', verify `data-axis="peers"`.
  - `test_routing_match_thread_scope_uses_channels_axis` — scope='thread', verify the dropdown's `data-axis="channels"` (the thread-→-channels mapping).
  - `test_routing_match_renders_chiplist_for_stub_account` — stub-type, verify existing chip-list per row.
  - `test_routing_scope_change_re_mounts_dropdown_with_new_axis` — Discord account; row scope changes from 'channel' to 'peer'; verify the dropdown re-mounts with `data-axis="peers"` AND previous match values are cleared (or preserved if the leg picks preservation — the simpler choice is cleared, since the axis changed and the ids are no longer valid).
  - `test_routing_match_onChange_persists_via_save_round_trip` — Discord account; select an item; save; reload; verify the match value persists.
- New tests in `tests/browser/test_flow_studio_per_agent_overlay_dropdown.py` (NEW file) — only if `connectors-tab.js` chip-mode path is refactored:
  - `test_per_agent_overlay_chip_mode_renders_dropdown_for_discord` (or stub fallback).
  - `test_per_agent_overlay_checkbox_mode_unchanged` (regression contract).
- Existing F6/F7 routing-rules tests at `tests/browser/test_flow_studio_connector_account_editor.py` MUST pass UNMODIFIED for stub-type accounts (regression contract).

## Acceptance Criteria

- [x] `connector-account-editor.js` has a NEW helper `_mountRoutingMatchEditor(rowEl, account, scope, currentValues, vocab, checkDirty)` that mirrors `_mountAllowlistAxisEditor`'s shape but for per-row match cells.
- [x] Inside `_mountRoutingMatchEditor`, scope translates to API axis per the mapping (channel→channels, thread→channels, dm→peers, peer→peers).
- [x] When taking the dropdown path, `_mountRoutingMatchEditor` installs `slotEl._routingMatchValues = () => state.values.slice()` on the chip-list slot.
- [x] `_wireRoutingMatchChiplist(rowEl)` refactored to call `_mountRoutingMatchEditor`.
- [x] Scope-change listener (L2327 region) refactored to re-mount the match-cell editor with the new scope. Previous match values cleared on scope change (the simpler semantics — the dropdown's ids belong to the previous axis).
- [x] Routing-rules collect path refactored to consult `_routingMatchValues` first; falls back to chip text-node walk when absent.
- [x] For Discord accounts:
  - All routing-rules rows with scope `channel`/`thread` show a dropdown with `data-axis="channels"` in the match cell.
  - Rows with scope `dm`/`peer` show a dropdown with `data-axis="peers"`.
- [x] For stub-type accounts, all routing-rules rows show the existing chip-list editor — DOM byte-identical to pre-L6b state.
- [x] If `connectors-tab.js` has a chip-mode-axis path: same refactor applied; per-agent overlay tests added. If not: documented as a no-op finding in flight-log; L6b ships routing-rules only.
- [x] 6 new browser tests for routing-rules; 2 new tests for per-agent overlay if applicable.
- [x] Existing F6/F7/F8 chip-list tests pass byte-identically for stub-type accounts.
- [x] No changes to L5's component file, L4's API, L3's substrate, or L6a's allowlist refactor.
- [x] `git diff --stat` shows changes only in: `connector-account-editor.js`, optionally `connectors-tab.js`, the new test file(s), plus F3 sibling artifacts.

## Verification Steps

- `grep -n "_mountRoutingMatchEditor\|_routingMatchValues" the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — both names appear.
- `docker exec the-one pytest tests/browser/test_flow_studio_connector_routing_dropdown.py -x --timeout 60 -q -m browser` — 6 new tests pass.
- `docker exec the-one pytest tests/browser/test_flow_studio_connector_account_editor.py -x --timeout 60 -q -m browser` — existing routing tests pass byte-identically.
- L6a regression: `docker exec the-one pytest tests/browser/test_flow_studio_connector_allowlist_dropdown.py -x --timeout 60 -q -m browser` — 6 L6a tests still pass.

## Implementation Guidance

1. Read the actual current state of `_wireRoutingMatchChiplist` (L2177-2185), `wireRoutingRulesEvents` (L2154), the scope-change listener (L2327 region), and the routing-rules collect path.

2. Implement `_mountRoutingMatchEditor(rowEl, account, scope, currentValues, vocab, checkDirty)` mirroring L6a's `_mountAllowlistAxisEditor` shape. Find the chip-list slot inside the row (`rowEl.querySelector('.connector-routing-match-chiplist')`); install the `_routingMatchValues` getter on the slot.

3. Refactor `_wireRoutingMatchChiplist` to call the new helper. Pass the row's current scope (read from `rowEl.querySelector('[data-routing-scope]').value`).

4. Refactor the scope-change listener: on scope change, call `_mountRoutingMatchEditor` to re-mount the match cell with the new scope. Clear previous match values (the dropdown's ids belong to the previous axis).

5. Refactor the routing-rules collect path to consult `slot._routingMatchValues` first.

6. **Investigate `connectors-tab.js`** during implementation: walk `_renderAccountTile` to confirm whether a chip-list mount site exists for per-axis overrides in chip-mode. If yes: apply the same dispatch refactor + install `_overlayChipValues` getter. If no: document in flight-log + L6b ships routing-rules only.

7. Write the new browser tests. Use the existing seeder pattern for Discord and stub accounts.

8. Run tests:
   - L6b target: `docker exec the-one pytest tests/browser/test_flow_studio_connector_routing_dropdown.py -x --timeout 60 -q -m browser` (plus the per-agent overlay test file if applicable).
   - L6a regression: `docker exec the-one pytest tests/browser/test_flow_studio_connector_allowlist_dropdown.py -x --timeout 60 -q -m browser`.
   - Full editor: `docker exec the-one pytest tests/browser/test_flow_studio_connector_account_editor.py -x --timeout 60 -q -m browser` (the pre-existing `test_edit_session_continuation_round_trip` failure is carried forward — unrelated to L6b).

9. Sibling artifact bookkeeping: check off L6b in flight.md + flight-log; update leg status to `landed`.

## Edge Cases

- **Scope change preserves vs clears match values**: the leg picks CLEAR (simpler). If the operator notices the friction at HAT, F8 followup considers preservation logic (e.g., keep the ids if the new axis structurally contains them — peers and channels don't overlap, so this is rarely useful).
- **Per-agent overlay no-op finding**: the developer's `connectors-tab.js` walk may surface that the chip-mode path doesn't actually mount a chip-list (it may render checkbox-mode only when account-scope is restrictive, and fall back to "inherit account-scope" otherwise — no chip-list anywhere). This is a legitimate finding; L6b ships routing-rules only in that case.
- **Routing-rules table is empty in create mode**: similar to L6a's allowlist, `renderRoutingRulesSection` is gated on `!isCreate` (per L410 — `var routingHtml = isCreate ? '' : renderRoutingRulesSection(account);`). No create-mode AC needed.
- **Pre-existing test failure carry-forward**: `test_edit_session_continuation_round_trip` failure from L5/L6a remains unrelated; carry forward.

## Files Affected

- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — `_mountRoutingMatchEditor` + refactored `_wireRoutingMatchChiplist` + scope-change listener + routing collect path.
- `the_one/interfaces/web/static/js/areas/studio/connectors-tab.js` — CONDITIONALLY refactored based on developer's walk.
- `tests/browser/test_flow_studio_connector_routing_dropdown.py` — NEW; 6 tests.
- `tests/browser/test_flow_studio_per_agent_overlay_dropdown.py` — NEW if applicable; 2 tests.
- F3 sibling artifacts.

---

## Post-Completion Checklist

- [x] All ACs verified
- [x] All browser tests pass
- [x] If per-agent overlay was investigated and turned out a no-op, the finding is documented in flight-log under L6b's entry
- [x] Update flight-log.md
- [x] Set leg status to `landed`
- [x] Check off L6b in flight.md
- [x] Do NOT commit
