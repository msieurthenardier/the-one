# Leg: retire-settings-providers

**Status**: completed
**Flight**: [Model providers in Library](../flight.md)

## Objective
Remove providers from Settings entirely: the Models group, the `#settings/providers…` route (old links drop, with no redirect), every admin-area provider branch, the Settings tile list and the provider editor's interim `'settings'` host. Migrate every remaining provider test to the Library routes, then retire and fence the dead testids. The full gate is green.

## Context
- **Flight design decisions:** DD8 (Settings loses providers; old links drop; retired ids fenced), DD10's leg-2 half, and the leg-2 parts of DD4 (admin strip), DD6 (Jump to's Settings special case), DD7 (CSS deletion, `.cap-chip*` move) and DD9 (file renames, `settings` re-budget). Read them in [flight.md](../flight.md).
- **Leg 1 outcome** (flight log, "library-and-providers"):
  - Providers work fully in Library (`providers-section.js`, the first group, Add menu, start-page card, Jump to rows `data-kind="provider"`, 13 tests in `tests/browser/test_flow_provider_library.py`, `_providers.py` with `block_claude_ai` and `studio_dirty`).
  - `provider-editor.js` and `provider-models.js` live in `areas/studio/` under `App.studio.*`. `callbacks.host` defaults to `'settings'`, and admin passes nothing.
  - The only `App.admin.renderProvider*` left is `renderProvidersList` (`areas/admin/providers-list.js`).
  - `LISTS["settings/providers"]` is scoped by `a.provider-tile-link[data-testid="provider-card"]`.
  - `_nav.legacy_hash` and `_from_legacy` have a providers branch.
  - Lane walls: settings 305/540, providers 185/240, agents 474/510 (tight).
  - The asset count is 88.
- **The operator's decision:** old `#settings/providers` links are **dropped**, not redirected.
- **Squawks:** 0166 and 0187 (and 0168, 0171) are known gate flakes; triage them by isolated re-run.

## Inputs
- The uncommitted leg-1 working tree on `sortie/02-model-providers-in-library` (both parts), landed and accepted.

## Outputs
- No provider surface in Settings, and no `settings/providers` route in code or tests.
- `areas/admin/providers-list.js` is deleted, and `admin.js` has no provider code.
- The provider editor has a single host (Library).
- Provider tests live in the `providers` lane and use Library routes.
- Retired testids are fenced.
- Docs are current.

## Acceptance Criteria
- [x] **AC1 — Settings nav and pages.**
  - `settings-pages.js` has no `providers` row, and the Settings nav shows General, Defaults for agents and Developer (dev mode), with no "Models" group.
  - `tests/test_settings_pages_static.py` pins the seven-row table (and its `ROUTE_SECTION` literal).
  - The router's Settings rows equal the table.
- [x] **AC2 — routes drop.**
  - `router.js` has no Settings `providers` SECTIONS row and no `settings/providers` entry anywhere (`ITEM_COLLECTIONS`, the header comment table). The "Model providers" label comment no longer contrasts it with a Settings page.
  - `resolve('#settings/providers')`, `resolve('#settings/providers/~new')`, `resolve('#settings/providers/<id>')`, `resolve('#admin/providers')`, `resolve('#admin/providers/new')` and `resolve('#admin/providers/<id>')` all return `{kind:'unknown'}`. Behaviour:
    - A cold boot lands on `#chats` (the boot sends a non-route hash to `resolve('chats')`).
    - `go()` resolves `false` for any non-route target (verified at leg design: `router.js` `go()`, first line).
    - A typed hash after boot restores the current route (`handleArrival`).

    Routing tests pin all three.
  - The routing-lane tests that pinned the old redirect (`test_router_core.py`'s `#admin/providers` rows, and others found by grep) are re-pinned to unknown. Rename such tests over delete-and-re-add where the intent shifts.
  - `#studio/providers[/…]` still maps to `library/providers` (accepted, DD8). A parity row pins it.
- [x] **AC3 — admin strip (DD4).** **Keep (shared with tools or other live UI):**
  - the scaffold (`mountScaffold`, `scaffoldFor`, `itemEl`/`listEl`), used by the tools editor;
  - `openItemLink`'s `a.tool-tile-link` branch;
  - any pending-state field the tools path also uses (check `_pendingFormMode` before removing);
  - the tools editor's `App.nav` dirty source. Confirm the registration is per category, so removing the provider path cannot unregister it.

  **Remove:**
  - the providers category (and `providers` from the `GENERAL_SUBS.concat([...])` list in `hydrateState`), the scaffold's provider half and `new-provider-btn`, the `providers` and `agents` store subscriptions and `agentsForTable` (verified at leg design: they serve only the provider "Used by" column; confirm no other admin consumer), `openItemLink`'s provider case, `fetchProvidersNow`, the `PROVIDER_TYPES`/`fetchProviderTypes`/`TYPE_DEFAULTS` copies, `revealItem`'s provider use, the provider pending state and focus helpers (`focusAddProvider`, `focusProviderRowNear`), and `serializeState`/`hydrateState`'s provider branches.
  - `areas/admin/providers-list.js` is deleted, with its `index.html` tag removed. The asset-count pin goes back to 87, with a history entry.
  - `grep -n -i "provider" the_one/interfaces/web/static/js/areas/admin.js` returns only lines unrelated to the provider surface (e.g. reasoning-effort or tool copy, if any), each justified in the leg's flight-log entry.
- [x] **AC4 — single editor host.**
  - `provider-editor.js`'s `callbacks.host` option and its `'settings'` path are removed: the `h2` title, the "Settings / Providers" breadcrumb, the Settings-only flash and any admin-only hook.
  - The editor always renders the Library chrome.
  - `providers-section.js` stops passing `host`.
- [x] **AC5 — Jump to.**
  - The `settingsWhere` providers special case (`jump-to.js`) is removed, and there is no Settings "Providers" candidate.
  - A "provider" query lists only the Library provider rows (and any non-provider matches).
  - `test_flow_jump_to.py` is updated.
- [x] **AC6 — CSS (DD7).**
  - **Delete** only provider-only rules in `admin.css`: the `.provider-tile*` selectors and the editor, model-list and plan sign-in duplicates now in `studio.css`. In a shared selector list (e.g. `.tool-tile-link, .provider-tile-link` near `admin.css` ~l.137-166), **trim the provider selector, never the rule**.
  - **Keep:**
    - the Built-in tools tile rules: `.area-admin .tile-title-row`, `.tile-title-row .entity-tile-name`, `.tile-title-row .admin-tool-badge`, `.tool-tile-link`, `.entity-tile*` (used by `areas/admin/tools-grid.js`);
    - `.admin-provider-badge` and `.admin-provider-badge--{type}` (used by the dev-mode Design language page, `areas/admin/design-language/status-section.js`, and read by the badge-ink a11y pins).
  - `.cap-chip*` moves to an unscoped shared location (e.g. `components.css`), and the agent editor's capability chips still render.
  - `test_design_tokens_a11y.py`'s `.cap-chip-no-tools` pin (~l.411-437, which reads admin.css by path and message) follows the move.
  - `test_providers_tile_rules_consume_the_gated_pairs` (~l.963-990) is **split, not retired**. Its shared assertions (`.tile-title-row`, `.tile-title-row .entity-tile-name`, `.entity-tile.active`) are kept and retargeted at the tools tile rule, in a test renamed to say so. Only the `provider-tile-*` assertions are deleted. The tile contrast-pairs test just above it gets the same review.
  - `tests/test_token_definitions.py` and `tests/test_ui_guards.py` pass.
- [x] **AC7 — tests migrated.** Every browser test that reached providers through Settings now reaches them through `library/providers[/~new|/{id}]` via `_nav`, and rows through `_lists` (`LISTS["library/providers"]`, `expect_selected(page, "library/providers", name)`, `library_add(page, "providers")`).
  - Tile-specific assertions (`test_flow_provider_grid.py`'s grid layout, the tile title row, the badge corner) are retired where the behaviour no longer exists. Where behaviour survives as a Library row (badge, "used by", selection, ordering), they are rewritten against the row; the file is renamed if its subject changes.
  - The provider half of `test_flow_settings_items.py` moves to a new `test_flow_provider_items.py` (providers lane), and the tools half stays.
  - `test_flow_admin_openrouter.py` is renamed to `test_flow_provider_openrouter.py` and migrated.
  - `test_flow_admin_settings_nav.py`, `test_flow_settings_visible_fixes.py`, `test_flow_settings_focus_after.py`, `test_flow_settings_section_labels.py` and `test_flow_admin_knowledge_settings.py` stay in settings. Their provider references are migrated or removed; assertions about the Models group are inverted to assert its absence.
  - The routing and shared files (`test_router_*`, `test_nav_guard.py`, `test_store.py`, `test_flow_hash_routing.py`, `test_flow_keyboard.py`, `test_shell_rail.py`, `test_flow_cross_area_dirty_gate.py`, `test_lists_helper.py`) are migrated.
  - `test_visual_snapshots.py` (pixel, no lane) is migrated, not exempted.
  - `test_flow_provider_plan_signin.py` switches to `_providers.block_claude_ai`, and its own copy is removed.
  - Where a Library-route test already covers a migrated scenario in `test_flow_provider_library.py`, the duplicate is removed, never kept twice. Known duplicates:
    - `test_flow_provider_setup.py`'s row link and selection checks;
    - `test_flow_provider_grid.py`'s badge and "used by" checks (covered by `test_model_providers_is_the_first_group_with_badge_and_used_by`). Its tile-layout tests retire. If any survivor stays, the file keeps the `test_flow_provider_` prefix so it stays in the providers lane; otherwise it is deleted;
    - `test_store.py`'s cold-boot providers test.
  - **Host-specific text:** `test_flow_provider_editor.py`, `test_flow_admin_openrouter.py` and others assert Settings-host chrome (the "Settings / Providers" breadcrumb, the "New Provider" `.editor-title`, the `h2`). Re-audit every migrated provider test for host-specific text, and assert the Library chrome instead.
  - **Fetch counts:** `test_store.py`'s provider fetch-count tests (e.g. "Settings -> Providers: one /api/providers") are re-derived for the Library route. Library also force-gets agents, knowledge bases, MCP sources and connectors. Count from the code, not by editing numbers until green.
  - `test_flow_admin_navigation.py` uses `settings/providers` as a generic Settings page. Retarget it to `settings/tools` (or `appearance`), not to Library.
  - Completeness check: `grep -rn "settings/providers" tests/ the_one/` returns nothing, except the new guard's own pattern and a test proving the route is unknown.
- [x] **AC8 — helpers.**
  - `_lists.py`: `LISTS["settings/providers"]`, `providers_list`, `SETTINGS_PAGE_TITLES["providers"]` and the `SETTINGS_PAGES` providers entry are removed, along with `settings_item`'s provider use (it stays for tools).
  - `tests/test_nav_helper.py`'s `settings/providers` mapping pins (~l.53-55, 74, 141, 152, 174-177, 190) are migrated to Library routes, or re-pinned as unknown.
  - `_nav.py`: the docstring examples (`"settings/providers/~new"`) use a Library route, and the `legacy_hash` and `_from_legacy` providers branches map to Library or are removed if unused.
  - The registry's `provider-card` row is "studio" only.
- [x] **AC9 — retired ids fenced (DD8).**
  - `new-provider-btn` and `providers-empty` are in `RETIRED_SELECTORS` and the registry's Retired table. `providers-empty` covers `providers-empty-add`. **In the same edit**, their live registry rows (`new-provider-btn`, `providers-empty`, `providers-empty-add`) are removed, because the coverage pin fails if a retired id (or prefix) is still registered as live.
  - `settings-nav-providers` is in `RETIRED_SELECTORS` only, not the Retired table, because `settings-nav-` stays live.
  - `provider-tile` (a class only in `providers-list.js`, admin.js and CSS) is fenced in `RETIRED_SELECTORS`. `providers-list` is not fenced (it would catch future `providers-list-*` ids, and nothing reaches it).
  - The `'a.provider-tile-link[...]'` literal in `_lists.py` is removed in the same step as the fence (AC8 before AC9).
  - The registry's `entity-tile` row stops citing `providers-list.js`.
  - `test_retired_selectors_cover_the_registry_retired_table` passes.
  - A new `tests/test_nav_helper.py` guard fails on any `settings/providers` route literal in `tests/browser/` (docstrings and comments exempt, as with the existing guards), with a self-test.
- [x] **AC10 — the `settings` lane and pins.**
  - `scripts/run-tests.sh`'s `settings` BUDGET is re-measured from this leg's gate (plus about 25%, rounded up to 30 s). The `providers` budget is re-measured too, since files move in.
  - `tests/test_run_tests_lanes.py` passes.
  - `CLAUDE.md`'s lane table and file globs are current.
  - The `test_store_static.py` pin of a provider-save `sync` refers only to the section module (DD10). Confirm it after the admin strip.
- [x] **AC11 — docs.**
  - `the_one/agents.md`: "Settings nav and pages" (no Models), "Settings item pages" (Built-in tools only), "Providers section" (interim note removed; single host), Hash routing (no `settings/providers`; `#admin/providers` unknown), Jump-to.
  - `CLAUDE.md`: the route scheme (`#settings/{appearance|date-and-time|prompts|encryption|tools|knowledge-indexing|design-language}`; no providers items), the Settings nav paragraph, the Settings item pages paragraph and the `_nav` example. Invariants only.
  - `docs/ui-testid-registry.md` and `docs/ui-control-inventory.md` are current.
  - Behavior specs naming `#settings/providers`, `#admin/providers`, the Settings Models group or provider tiles are re-authored. Grep `tests/behavior/*.md`, excluding `runs/`: `shell-navigation-smoke` steps 8-9, `anthropic-plan-signin`, `system-provider-config`, `anthropic-plan-chat-parity`, `extended-thinking-tool-turn`, `save-preserves-config`, `studio-agent-crud`, `workbench-navigation`, `list-and-detail` and any others found.
- [x] **AC12 — the gate.**
  - `make test-unit` is green.
  - `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python TEST_TIMEOUT=3600 bash scripts/run-tests.sh --parallel 3 --tb=short` gives `PARALLEL_RESULT rc=0` across nine lanes. A failure is accepted only under the gate-flake triage rule (an isolated re-run passes, and it is a known squawk, or a new squawk is logged), and that is recorded.
  - The static guards and ruff are clean.
  - Lane walls are recorded in the flight log.

## Verification Steps
- AC1, AC10: `make test-unit` (`test_settings_pages_static.py`, `test_run_tests_lanes.py`, `test_store_static.py`).
- AC2: the routing lane; `grep -rn "settings/providers" the_one/` returns nothing.
- AC3: `test -e the_one/interfaces/web/static/js/areas/admin/providers-list.js` fails; the `grep -n -i provider` on `admin.js` is justified in the flight log; `test_index_asset_cache_busting.py` is at 87.
- AC4: `grep -n "host" the_one/interfaces/web/static/js/areas/studio/provider-editor.js` shows no host option; the providers lane passes.
- AC5: `test_flow_jump_to.py` (shared lane).
- AC6: `test_design_tokens_a11y.py`, `test_token_definitions.py`, and the agents lane (capability chips).
- AC7-AC9: the completeness grep, the `test_nav_helper.py` guards, and every lane.
- AC11: reviewer reading, plus `grep -rn "settings/providers\|admin/providers" CLAUDE.md the_one/agents.md docs/ tests/behavior/*.md`, which returns only deliberate "unknown route" mentions.
- AC12: the commands in AC12.

## Implementation Guidance
1. **Re-check citations** against the working tree (leg 1 moved many lines), using symbols.
2. **Strip Settings:**
   - `settings-pages.js` and `router.js` (the row and comments);
   - `admin.js`'s provider branches, then delete `providers-list.js` and its `index.html` tag;
   - `jump-to.js`'s special case;
   - the editor's `'settings'` host path.
   - Run `make test-unit` and the static guards, and expect the browser lanes to fail until step 4.
3. **CSS:** delete the admin provider rules and move `.cap-chip*`.
4. **Helpers first, then tests:** `_lists.py`, `_nav.py`, `_providers.py`, then migrate the browser files lane by lane: providers, settings, routing, shared, chats and the pixel file. Remove duplicates of `test_flow_provider_library.py` scenarios. Split and rename per AC7.
5. **Fence:** the retired ids, the new `settings/providers` guard and the coverage pin.
6. **Docs and behavior specs.**
7. **Gate.** Re-measure the `settings` and `providers` budgets, and record the walls.

## Edge Cases
- **A bookmarked `#settings/providers/<id>`:** unknown route. The boot falls to `#chats` (the router's unknown handling), and in-app it is refused. No redirect, by the operator's decision. A routing test pins it.
- **`App.nav` dirty sources:** removing admin's provider dirty source must leave the Settings tools editor's guard intact (the `test_flow_cross_area_dirty_gate.py` and `test_nav_guard*` scenarios).
- **The admin area's `providers` store subscription** may also feed non-provider UI (e.g. a usage readout). Remove only what serves the provider surface, and keep anything else, justified.
- **`renderCapabilityChips` and `.cap-chip*`:** the agent editor depends on them, so they move rather than being deleted.
- **A Settings test that asserted the Models group exists:** invert it to assert absence (rename it so the intent shift shows in git blame).

## Files Affected
- `the_one/interfaces/web/static/js/settings-pages.js`, `router.js`, `jump-to.js`, `areas/admin.js`, `areas/admin/providers-list.js` (deleted), `areas/studio/provider-editor.js`, `areas/studio/providers-section.js`, `static/index.html`
- `the_one/interfaces/web/static/css/admin.css`, `components.css` (or another shared file for `.cap-chip*`)
- `scripts/run-tests.sh` (budgets)
- `tests/browser/_lists.py`, `_nav.py`, `_providers.py`, and the 28 browser files currently referencing `settings/providers` (see the leg-2 design grep in the flight log), plus `test_visual_snapshots.py`; new `test_flow_provider_items.py`; renamed `test_flow_provider_openrouter.py`
- `tests/test_settings_pages_static.py`, `tests/test_nav_helper.py`, `tests/test_index_asset_cache_busting.py`, `tests/test_design_tokens_a11y.py`, `tests/test_store_static.py`, `tests/test_run_tests_lanes.py`
- `tests/behavior/*.md` (re-authored specs)
- `the_one/agents.md`, `CLAUDE.md`, `docs/ui-testid-registry.md`, `docs/ui-control-inventory.md`

## Execution Note
The Flight Director runs this leg with two Developer spawns:
- **Part 1 — code and tests:** Implementation Guidance steps 1-5 (AC1-AC10). It ends with the providers, settings, routing, shared and chats lanes green, recorded in the flight log, and does not land the leg.
- **Part 2 — docs, behavior specs and the gate:** steps 6-7 (AC11-AC12), which land the leg.

Inside step 2, edit `router.js` and `settings-pages.js` last, after admin.js no longer branches on providers.

## Citation Audit
Every cited mechanism comes from the flight's DDs, verified at `30195e6`, and from leg 1's landed outcome (flight log). Leg 1 rewrote `studio.js`, `router.js`, `jump-to.js` and the editor, so line numbers are not cited here. The Developer locates by symbol: `settingsWhere`, `renderProvidersList`, `fetchProvidersNow`, `openItemLink`, `revealItem`, `callbacks.host`, `RETIRED_SELECTORS`, `test_retired_selectors_cover_the_registry_retired_table`. Verified now: 28 browser files and helpers reference `settings/providers` (grep at leg design).

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
