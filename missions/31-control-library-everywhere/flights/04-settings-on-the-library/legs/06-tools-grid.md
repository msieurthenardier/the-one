# Leg: tools-grid

**Status**: landed
**Flight**: [Settings on the library](../flight.md)

## Objective
Rebuild the Built-in tools list (category tabs and tool tiles) on the library:
- `App.ui.tabs`, `toolTile` and `toolTile.grid`, mounted once and reconciled by tool name, with no HTML strings and no hand-made focus restore;
- the tile switch as a named `role=switch` (DD8-1);
- a load failure shown, not stuck on "Loading tools…" (DD8-2);
- a non-404 detail failure no longer stranded (DD8-3);
- the per-tool summary on each tile (B1), and no category badge (A6);
- legacy `App.tabs` and `js/tabs.js` retired.

`toolTile` takes ownership of its legacy classes (DD12).

## Context
- **Flight decisions:** DD6 (the grid), DD8 1-3, DD12 (the `toolTile` handover here), DD7 (ledger rows 6, 25 and 40), DD10, DD11.
- **Today** (`static/js/areas/admin/tools-grid.js`, 274 lines):
  - `renderToolsGrid(container, toolConfigs, callbacks)` rebuilds the whole list with `innerHTML` (3 sinks: loading `:130`, empty `:135`, the list `:201`), twice per toggle (optimistic, then settle), with hand-made focus restore (`focusKey`/`focusTarget`/`deferredFocus`);
  - the hand-built `role=tablist` is wired by legacy `App.tabs` (`:212`);
  - the tile is a string with an `a.tool-tile-link`, an `.admin-tool-badge--{cat}` badge, the description and the legacy corner switch (`aria-label="Enable {name}"`, which hides the "for all agents" state text);
  - `setToolsSelection(container, name)` marks the open tool in place.
- **The caller** is the tools-page module (leg 02a's `tools-page.js`): `fetchToolConfigs` with no `r.ok` check (DD8-2), `handleToolToggle` (an optimistic toggle with `toolsInFlight`), and `selectTool`'s non-404 failure path (DD8-3).
- **The switch's name (DD8-1):** "Enable {name} for all agents". The role `switch` gives the state ("on"/"off"), the name keeps the "Enable {name}" prefix the existing tests and `_lists.tool_toggle` use, and the scope is now part of the name. The visible label stays hidden on the tile (`labelHidden`), as today.
- **B1:** the tile shows `summary` (served since leg 05a), falling back to `description` only if `summary` is missing. Drop the two-line clamp if the summary fits; keep it as a backstop.
- **A6:** no category badge on tiles. `.admin-tool-badge--*` is deleted.

## Inputs
- Legs 02a (`tools-page.js`), 04d (`tabs` `panelPadding`), 04e (`toolTile`, `toolTile.grid`) and 05a (`summary`) landed.

## Outputs
- `tools-grid.js` rewritten: `App.admin.toolsGrid.create(listEl, {onToggle, onOpen?})` returns `{render(toolConfigs, {selectedName, inFlight}), setSelection(name), setLoading(), setError(text), destroy()}`. Or keep the two exported function names as thin wrappers, if `tools-page.js` and the tests are simpler that way; pick one.
  - The tabs are `App.ui.tabs` (testids `tab-{cid}` and ids kept as the tests read them), with `panelPadding: 'none'`.
  - Each panel is a `toolTile.grid`.
  - A toggle patches its tile (`setChecked`/`setDisabled`); the list is never rebuilt.
  - Loading and empty states use `App.ui.status`/`App.ui.emptyState` (`variant: 'flush'`).
  - A load failure shows "Couldn't load the built-in tools." with the server detail, through `App.ui.status` `danger` (or a banner), plus a Retry button.
- `tools-page.js`: `fetchToolConfigs` through `App.api.fetchJson` (DD3); `handleToolToggle` failure through `App.ui.flash` with the server detail (no more "Failed to update {name}."); the DD8-3 fix (a non-404 detail failure clears `pendingToolName`, syncs the route to `tools` and keeps the list usable).
- `js/tabs.js` and its `index.html` tag deleted. `test_ui_tabs_contract.py`'s legacy parity test (`:152-215`, which loads `js/tabs.js`) is deleted, with its reason recorded: the legacy helper no longer exists, and the library tabs' own keyboard contract stays. `tests/test_ui_ownership.py`'s `App.tabs(` pattern stays (harmless).
- `admin.css`: the grid, tile, badge, legacy-switch `.area-admin` tile rules, `.settings-list .tablist/.tabpanel/.empty-state`, and the dead `.settings-intro` removed (the `.area-admin` switch rules stay for leg 10's Knowledge indexing until it moves).
  - The `test_design_tokens_a11y.py` tile pins (`:985-998`) are moved to the library tile.
- `toolTile`'s catalogue row lists its legacy classes as owned. The `OWNERSHIP_ALLOWANCE` rows for `tools-grid.js` (5 rows, 10 uses) are removed, and `admin.css`'s tile rows shrink.
- `HTML_SINK_ALLOWANCE`: the `tools-grid.js` row is removed (3 sinks to 0).
- `docs/ui-testid-registry.md`: the `tab-` row and the Tabs inventory row are fixed (both stale per the survey).

## Acceptance Criteria
1. **DD8-1:** the tile toggle is `role=switch` with the accessible name "Enable {name} for all agents", and its state is announced. The test fails on today's code.
2. **DD8-2:** a routed 500 on `GET /api/tools/configs` shows the load error and a Retry; Retry after the route is fixed shows the list. The test fails on today's code (stuck on "Loading tools…").
3. **DD8-3:** a routed 500 on the detail for `#settings/tools/read_file` leaves the URL at `#settings/tools`, no tile selected and the list usable, with an error shown. The test fails on today's code.
4. **No rebuild on toggle:** a `MutationObserver` on the list during a toggle (optimistic and settled) records no removal or re-insertion of tiles. A focused toggle keeps focus through the whole toggle, with no `deferredFocus` code left.
5. **Tabs:** `App.ui.tabs`. The keyboard behaviour (arrows, Home/End and activation, per the library contract) and the persisted active category hold. Opening a tool switches to its category once (today's `revealedName` rule). The `settings` lane's grid tests pass, retargeted only for removed classes (`.entity-tile` → the `tool-card` testid, `.admin-tool-badge` gone).
6. **B1 and A6:** each tile shows its summary and no badge (ledger rows 25 and 6). The capture compare against the before set shows only the ledgered differences (rows 6, 25 and 40).
7. **Counts:** `tools-grid.js` has no sink row and no ownership row. `git grep -n "App.tabs\b" the_one/` finds no caller. `js/tabs.js` does not exist.
8. The unit tier, the static guards, the emitted-class guard (the `toolTile` legacy names now owned) and the `settings`, `routing`, `shared` and `contracts-controls` lanes pass.

## Verification Steps
- `.venv/bin/python -m pytest tests/test_ui_guards.py tests/test_ui_ownership.py tests/test_ui_control_inventory.py tests/test_ui_emitted_classes.py tests/test_design_tokens_a11y.py tests/test_tools_admin_grid_assets.py tests/test_index_asset_cache_busting.py -q -x --timeout 120`.
- The lanes under `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1`.
- The capture compare.
- `make test-unit` once.

## Implementation Guidance
1. The three DD8 tests first, failing.
2. Build the grid controller on `tabs` and `toolTile.grid`, then switch `tools-page.js` to it.
3. Move the fetch to `fetchJson`, and fix DD8-2/3 and the toggle flash.
4. Delete `js/tabs.js` and its tag and parity test, plus the `admin.css` rules.
5. Hand over `toolTile`'s ownership; update the allowances, registry and catalogue.

## Edge Cases
- **A toggle while a list refetch is in flight** (`_refresh`): the in-flight map keeps the tile disabled. The refetch reconciles without un-disabling it.
- **A tool removed from the list while its toggle has focus:** focus moves to the next tile's toggle, or the tab. Say which, and test it.
- **The search-free grid at 1024 width:** the capture checks it.

## Files Affected
- `static/js/areas/admin/tools-grid.js`, `static/js/areas/admin/tools-page.js`, `static/js/tabs.js` (deleted), `static/index.html`, `static/css/admin.css`.
- `tests/browser/test_flow_admin_tools_grid.py`, `test_flow_settings_items.py`, `test_flow_settings_visible_fixes.py`, `test_ui_tabs_contract.py`, `tests/browser/_lists.py` (if a helper reads a removed class), `tests/test_tools_admin_grid_assets.py`, `tests/test_design_tokens_a11y.py`, `tests/test_ui_guards.py`, `tests/_ui_ownership_allowance.py`.
- `docs/ui-control-inventory.md`, `docs/ui-testid-registry.md`, `the_one/agents.md`, the flight log.

## Citation Audit
- `tools-grid.js:130`, `:135`, `:201` sinks; `:212` `App.tabs`; `setToolsSelection`: verified (FD read).
- `admin.js` `fetchToolConfigs` (`:447-466`, no `r.ok`) and `selectTool`'s `:443` failure flash: from the survey. Both move to `tools-page.js` in 02a, so re-locate them.
- `test_ui_tabs_contract.py:152-215`: from the survey.

## Design Review Amendments (cycle 1, 2026-10-23)
These override the body where they conflict.
- **`App.ui.tabs({idPrefix: 'tools', items: [{id: cid, label, testid: 'tab-' + cid}]})`** gives the ids the tests read (`tools-tab-{cid}`, `tools-panel-{cid}`) and keeps `data-tab-id`. The toggle's `dataset` and `testid` land on the input (the choice factory does this).
- **The name prefix:** no test asserts the exact name "Enable {name}" (`_lists.tool_toggle` selects by testid and `data-name`). The new name "Enable {name} for all agents" stands on its own merits.
- **Badge tests:** delete the badge assertion in `test_flow_admin_tools_grid.py` (about `:120-130`, A6). Rewrite `test_tool_tile_name_never_overlaps_badge` (`test_flow_settings_visible_fixes.py` about `:40-60`) as "the name never overlaps the toggle". The library tile's link keeps the `tool-tile-link` class (legacy-emitted, owned after this leg), so focus code and the test still find it.
- **`selectTool` moves to `fetchJson` too:** 03a's errors carry `err.status`, so the 404 "gone" path uses `err.status === 404`. AC3's test also asserts that the 404 healing still works.
- **`activeCategory` and `revealedName` stay module-level** in `tools-grid.js` (outside `create`), so the active tab survives a re-render and re-entering Settings › Tools. `tabs.select(id)` calls `onChange`; the reveal path sets the module state first, so there is no loop. Add a leave-and-re-enter test.
- **The toggle mechanism:**
  - `render(configs, {inFlight})` calls `setDisabled(true)` for in-flight names;
  - a failed PUT calls `setChecked(previous)` on the tile with no rebuild, and shows a flash with the server detail;
  - AC4 also covers a routed 500 on the PUT.
- **An empty category** panel uses `App.ui.emptyState({title: 'No tools.', variant: 'flush'})`, tested with a mocked list.
- **Focus when the focused tool disappears:** the next tile's toggle in the same panel, else the previous tile's, else the panel's tab. Tested with a routed list that drops the tool.
- **The exports:** `App.admin.toolsGrid.create`; `renderToolsGrid` and `setToolsSelection` are deleted, and `tests/test_tools_admin_grid_assets.py` is retargeted (keep the file name `tools-grid.js`).
- **The legacy parity test removal** also removes its helpers (`LEGACY_BUILD` and the constants about `:140-215`). `git grep` `js/tabs.js` and `App.tabs` across `tests/`, `scripts/`, `docs/` and `tests/behavior/`.
- **The load error** is `App.ui.status` (`danger`) plus a Retry `App.ui.button` (`testid: 'tools-load-retry'`).
- **B1's fallback** (`summary` missing → `description`) has an assertion.
- **The `.area-admin` corner-switch rules stay** for Knowledge indexing until leg 10, which removes them.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
