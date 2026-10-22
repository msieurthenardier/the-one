# Leg: mcps-tab

**Status**: completed
**Flight**: [Agents on the library](../flight.md)

## Objective
Rebuild the agent editor's MCPs tab from library controls:
- one `App.ui.groupTile` per source, whose master is the **attach** switch;
- a lazily loaded body of `App.ui.toolRow` rows;
- the small Refresh button.

Fix DD9-1 (collapsing an expanded source throws), test first. Mount the tab once and patch it with `setAgent`. `mcps-tab.js` ends with zero sinks and zero allowance rows.

## Context
- **Flight decisions:** DD4 (the switch; Refresh becomes the small button), DD6, DD7, DD9-1, DD10.
- **The leg-07 design review** (2026-10-21) split the old leg 07 and set the decisions below.
- **Legs 01-05, 06a, 06b and 07a have landed.** Read the flight log and the actual `groupTile`/`toolRow` API in `js/ui/tile.js`.
- **Today** (re-locate by symbol; `mcps-tab.js`):
  - The master is the **attach** checkbox `[data-mcp-source-toggle][data-mcp-source-id]` (checked means the id is in `mcp_source_ids`). It is **independent of tool selection**. The self-config source's master is locked checked and disabled, with a hint.
  - Per-tool checkboxes `[data-mcp-tool-toggle][data-mcp-source]` sit inside a `[data-mcp-tool-group][data-mcp-tool-mode]` wrapper. The mode (allowlist or denylist) comes from `agent.mcp_overrides` at render.
  - The count chip "N / M enabled" comes from the cache (`_enabledFromCache`) until the body renders, then from the checked boxes on each change. `_wireToolCheckboxesAndRecount` adds a duplicate listener on every load.
  - Refresh opens the body, then `loadTools(true)` calls `fetchMcpSourceTools({forceRefresh})` (`App.store.invalidate('mcp-sources')` on success) and replaces the body: rows, an `AuthRequired` notice, or `buildMcpError` (a headline plus Technical details).
  - `pendingSourceId`/`onSelectedSourceChange` handle URL focus.
  - **DD9-1:** `_setExpanded(false)` calls the undefined `_parseSourceIdFromHash` (`:364`). The collapse throws a `pageerror` and `onSelectedSourceChange(null)` never fires, so the route keeps `/{source-id}`.
  - `_populateDetailsBody` is dead code.
  - `agent-form-data.js` reads the masters' and tool rows' `.checked`, `data-*` and `closest('[data-mcp-tool-group]')` (about `:176`, `:199`, `:201`; re-locate).

## Decisions (binding)
- **The master is attach only.** It uses `groupTile` with a **non-tristate** master (add `master.tristate: false` to `groupTile` if it has no such option), so it renders with `role=switch`. It is never mixed, and its change toggles attachment and marks dirty. Tool rows never change it, and the "mixed master" edge case does not apply.
- **The library gains input datasets** (with contract cases in this leg): `groupTile` `master.dataset` (applied to the master's input) and `toolRow` `inputDataset` (applied to the checkbox input). This keeps `agent-form-data.js`'s DOM reads, and its payload, unchanged.
- **The tool-group wrapper** (`div[data-mcp-tool-group][data-mcp-tool-mode]`) is built inside `groupTile.body`, around the rows.
- **Refresh:**
  - On success, rows are patched **keyed by tool name**. A tool that is still present keeps the operator's unsaved checked state; a new tool takes the stored default for the current mode; a removed tool's row is removed.
  - On error, the existing rows stay and `buildMcpError`'s node shows above them, replacing any previous error. `buildMcpError` stays: tests about `:575-600` expect its headline and details.
  - One delegated change handler on the group replaces the per-load listeners, so the count no longer double-binds.
- **Refresh button:** `App.ui.button({size:'sm', icon:'refresh-cw'})` keeps today's visible "Refresh" text if the canvas-approved small button has a label (DD4 item 3: 24px, 10px text, 14px icon). Its `aria-label` names the source. It keeps the `mcp-refresh-tools-btn-{id}` testid.

## Acceptance Criteria
- [ ] **DD9-1, test first:** expand then collapse a source, and assert:
  - no `pageerror`;
  - the expand button has `aria-expanded="false"`;
  - the body (`mcp-source-details-body-{id}`) is hidden;
  - **the route drops the source segment.**

  It fails today and passes after. Under `groupTile`, the collapse path calls `onSelectedSourceChange(null)` from `onExpand(false)`; the tab never parses the URL. `_populateDetailsBody` is removed.
- [ ] **The tiles:**
  - `groupTile` per source: the name, the count chip (`setCount`; hidden while unknown), the protocol chip, Refresh in the actions, the subtitle (server name and version; `has-instructions` title), and the expand label "**N** tools" or "Tools" (`setToolCount`);
  - the self-config source: master locked on and disabled, the hint shown in the tile;
  - today's testids kept: `mcp-source-row-{id}` on the tile root, `mcp-source-toggle-{id}` on the master input, `mcp-source-expand-{id}`, `mcp-source-details-body-{id}`, the hint testid.
- [ ] **The rows:** `toolRow` without a disclosure, with `inputDataset: {mcpToolToggle: name, mcpSource: id}` inside the group wrapper. The auth-required notice is an `App.ui.status` line, and the empty state is an `App.ui.emptyState`.
- [ ] **URL focus:** `pendingSourceId` expands on mount. A later deep-link change calls `setExpanded(true)` plus the selected-source callback explicitly (`setExpanded` does not fire `onExpand`). An already-loaded body does not refetch.
- [ ] **Patch-only:** the tab exposes `{setAgent(agent), destroy}`. `setAgent`:
  - resets the masters from `mcp_source_ids`;
  - recomputes each group's `data-mcp-tool-mode` from `agent.mcp_overrides`;
  - re-derives each tool's checked state;
  - recounts the chips.

  It does not rebuild, and the tab is removed from 06a's interim list. A test: change a source's tool selection, Save, and assert the group's mode and the checked states match the server response, with the same tile node and the expanded state kept.
- [ ] **Form data:** for the same UI state, `mcp_source_ids` and the tool allow/deny lists sent on Save are identical to today's. A round-trip test pins it.
- [ ] **Tests:**
  - `test_studio_mcps_tab.py`: the `aria-expanded` assertions on `mcp-source-row-{id}` (about `:102`, `:287`, `:366`) move to `mcp-source-expand-{id}`; the master is located by role `switch`.
  - `test_studio_self_configuration_tab.py:80-85` (disabled, checked master; hint) passes.
  - The MCP error test (about `:575-600`) passes.
  - The grep of `data-mcp-*` and `.mcp-source-tile` across `tests/` is listed.
- [ ] **CSS:** delete only `.mcp-source-tile`, `-row1`, `-name`, `-protocol`, `-expand-btn`, `-tool-count`, `-chevron`, `-tools`, `.mcp-refresh-tools-btn`, `.mcp-tools-checkbox-group` and `.mcp-tool-toggle-label`/`-hint`, after confirming with grep that `tools-tab.js` uses none of them.
  - **Keep, for leg 08:** `.tool-toggle`, `.tool-switch`, `.mcp-source-tile-toggle` and `.mcp-tool-toggle-name` (`tools-tab.js` and `test_flow_studio_tools_overrides.py` use them; `test_design_tokens_a11y.py:643-680` pins `.tool-switch`).
  - **Keep, for later:** `.mcp-source-tile-subtitle` (`admin.css`).
  - **Do not touch:** the legacy comparison rules that `test_ui_tile_contract.py` (about `:202`, `:420-455`) compares against. If that test needs the legacy `.mcp-source-tile` rules, keep them in a test-only fixture stylesheet, or keep the rules until the contract test is rewritten to inline its legacy CSS. Decide and record it.
- [ ] **Zero:** `mcps-tab.js` has no sinks and no allowance rows.
- [ ] **Captures:** `agent-mcps` to `…/m31-f2-after-07b/`. The differences are DD4 items 1 (the switch) and 3 (Refresh) only.
- [ ] **Gates:** `make test-unit`; the static guards and ownership checks; the contracts lane (WebKit required: `tile.js` options added); the `agents` lane under netns.

## Files Affected
- `the_one/interfaces/web/static/js/areas/studio/{mcps-tab,agent-editor-controller}.js`, `js/ui/tile.js` (input datasets; non-tristate master), `css/studio.css`.
- `tests/browser/test_studio_mcps_tab.py`, `test_ui_tile_contract.py` (new options), new DD9-1 and round-trip tests; `tests/_ui_ownership_allowance.py`, `tests/test_ui_guards.py`.
- `docs/ui-control-inventory.md`, `the_one/agents.md`.

## Citation Audit
From the leg 07 design review (2026-10-21, post-split tree). Re-locate by symbol.

## Design Review Addenda, cycle 2 (2026-10-21)
- **Dirty tracking (binding).** `wireEditorEvents` only listens to `.field-input`, `.field-textarea`, `.field-select` and `.tool-toggle`, so the new library inputs would not mark the form dirty. Each control's own `onChange` (`toggle`, `toolRow`, `groupTile` `master.onChange`) calls the editor's dirty callback directly, passed in through the tab's ctx. A test checks that clicking a switch or checkbox enables Save and shows `.editor-unsaved`. It uses a real click, not an `evaluate` flip.
- **Legacy CSS (decided):** `test_ui_tile_contract.py` (about `:202`, `:420-455`) gets the legacy `.mcp-source-tile`/`.mcp-tool-toggle-label` rules **inlined as a fixture string**; it already builds the legacy markup. Then the rules are deleted from `studio.css`. The test is in Files Affected.
- **The Refresh label (decided):** `App.ui.button` supports an icon and a text label together at `size:'sm'` (as Flight 1's Test button does), so Refresh keeps its visible "Refresh" text at the small size: 24px, 10px text, a 14px icon. Its accessible name is "Refresh tools for {name}", and a test checks it.
- **The master:**
  - `setAgent` sets each master to `locked || attached` (the self-config source stays checked and disabled);
  - `groupTile` gains `master.tristate: false` with a `role=switch` contract case;
  - `master.dataset` goes on the input: `{mcpSourceToggle: '', mcpSourceId: id}`.
- **Refresh and mode rules:**
  - a Refresh never recomputes `data-mcp-tool-mode`; only `setAgent` does;
  - a new tool's default follows the group's current mode, with a test per mode;
  - a successful Refresh removes any previous error node.
- **The selected-source callback:** the `pendingSourceId` expand on mount calls `onSelectedSourceChange(id)` explicitly, as today's `startsExpanded` branch does. So does a Refresh on a collapsed tile. A loaded-once guard prevents a double fetch.
- **The source list refreshes only on remount**, the same as 07a. This is recorded. One exception follows.

## Design Review Addenda, from the leg 10a review (2026-10-21; binding)
Enabling self-configuration creates a new source row server-side, and disabling deletes it. The server never re-adds the loopback id on a PUT (`api.py` `update_agent` does not preserve `mcp_source_ids`). With a mount-fixed source list, the next Save after an enable would therefore drop the surface. Two self-configuration tests also depend on the tile appearing and disappearing: `test_studio_self_configuration_tab.py` `test_enable_shows_locked_row_on_mcps_tab` and `test_disable_removes_row_from_mcps_tab` (which expects `mcp-empty-state`).
- **The handle gains `setSources(sources, agentName)`**, so it is `{setAgent, setSources, destroy}`. `setSources` reconciles tiles by source id:
  - it adds a tile for a new source (the agent's own surface, locked checked and disabled);
  - it removes the tile of a deleted source;
  - it switches between the empty state and the list;
  - it leaves every other tile untouched: the same node, its expanded state, and its unsaved choices.
- **`patch` calls `mcps.setSources(self._allMcpSources, name)` before `mcps.setAgent(agent)`.** Until leg 10a lands, the self-configuration refresh still reaches `patch`, so the two tests above stay green in this leg.
- **Tests:**
  - the two self-configuration tests above pass unchanged;
  - after an enable, Save, and the stored `mcp_source_ids` contains the surface id;
  - after a disable, Save, and the stored `mcp_source_ids` does not contain the deleted id;
  - `setSources` keeps an expanded, unsaved tile's node and state.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
