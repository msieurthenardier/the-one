# Leg: retire-design-language-page

**Status**: completed
**Flight**: [Library completion and a stateful pilot](../flight.md)

## Objective
Delete the dev-mode Design language page and the dev-only Settings page mechanism that only it used. Move its token and type reference into the control catalogue, and leave every test, pin, registry row, behavior spec and doc consistent with an app that has no such page.

## Context
- This leg implements flight DD7. The operator decided (2026-10-14) that the whole page goes. The library's contract tests run from the disk harness (`tests/browser/_ui_engines.py::load_harness`), not from this page, so no library coverage is lost.
- **The dependency map** (Flight Director survey at `59992fd`) is reproduced below as the work list. Paths under `static/` are relative to `the_one/interfaces/web/static/`.
- **The demo rule changes shape.** "Every factory has a demo section on the page" becomes: "every factory has a catalogue row, and at least one `tests/browser/test_ui_*.py` file calls `App.ui.<name>(`". Leg 02 later adds an Owned classes column (6 cells). This leg keeps 5 cells, but scopes the row parser to the control tables, so the new Tokens and type section's tables are not read as control rows.
- `#settings/design-language` becomes an unknown route: dropped by the router's unknown-hash rules (boot goes to `#chats`; after boot the current route is restored). No redirect.
- **Carried lesson** (sortie 03): when retiring JS, grep the Makefile, `scripts/` and the testid registry for the old paths, and move retired testids to the registry's Retired table in the same edit.

## Inputs
- Branch `flight/01-library-completion-and-pilot` at `59992fd` plus the uncommitted flight artifacts.
- The page: `static/js/areas/admin/design-language-page.js` and 16 files under `static/js/areas/admin/design-language/`.

## Outputs
- The page, its scripts, its CSS and its browser test are deleted. The `devOnly`/`dev` page mechanism is deleted.
- `docs/ui-control-inventory.md` has a "Tokens and type" section (names and roles; no values).
- The rewritten tests, pins, registry, behavior specs and docs.

## Acceptance Criteria
- [ ] `static/js/areas/admin/design-language-page.js` and the `static/js/areas/admin/design-language/` directory are gone. `index.html` has no script tag for them. `tests/test_index_asset_cache_busting.py` pins the new `/static` ref count of 71.
- [ ] No runtime code mentions the page. `grep -rn "design-language\|designLanguage\|renderDesignLanguagePage" the_one/` returns nothing.
- [ ] The `devOnly`/`dev` mechanism is gone, and the Developer nav group can no longer exist:
  - `settings-pages.js` has no `devOnly` field or docs;
  - `router.js` has no `dev` row flag, `devMode()` or `row.dev` branch;
  - `admin.js` has no dev-mode `validIds` addition, no `devOnly` nav filter and no `design-language` dispatch;
  - `jump-to.js` has no `devOnly` skip or dev-only check used only for it.

  Dev mode itself (the mock provider and test seams) is untouched.
- [ ] CSS used only by the page is deleted:
  - `admin.css` `.design-language-*` (about `:631-676`);
  - `.telemetry-strip`/`.telemetry-value` (about `:678-697`);
  - `.admin-provider-badge` and its `--{type}` modifiers (about `:167-181`), with the `components.css` comments that cite them (about `:1173,1185`) reworded;
  - `components.css` `.list-item`, `.list-item-delete` (about `:127-166`) and `.list-item.confirm-delete` (about `:1204-1206`).

  Before deleting a rule, grep `static/` for each class to confirm that nothing outside the deleted page uses it. Classes the map lists as still used stay: `.admin-tool-badge--*`, `.entity-tile*`, `.indicator-led--*`, `.empty-canvas*`, `.test-result-*`, `.chip-remove`, `.banner-*`.
- [ ] `#settings/design-language` behaves as an unknown route, both at boot and after boot, with dev mode on.
- [ ] `docs/ui-control-inventory.md`:
  - **Header:** no longer calls the page the living reference. It names the catalogue plus each factory's contract tests as the reference.
  - **"The guard" section:** describes the new rule.
  - **Rows that cite the page:** the badge row's "only the Design language status demo" and the chat-history row's `.list-item` note are corrected.
  - **New "Tokens and type" section**, which lists:
    - every colour token the page showed (18: `--bg`, `--surface`, `--surface-elevated`, `--border`, `--border-hover`, `--border-strong`, `--fg`, `--fg-secondary`, `--fg-muted`, `--accent`, `--accent-fill`, `--accent-fill-hover`, `--fg-on-accent-fill`, `--control-border`, `--accent-api`, `--status-success`, `--status-warning`, `--status-danger`), each with its role in one line;
    - spacing `--space-1…8`, radius `--radius-sm/md/lg`, shadows `--shadow-popover`/`--shadow-modal`;
    - the type ladder (`--font-size-display`, `h1`, `h2`, `h3`, `body-lg`, `body`, `body-sm`, `caption`, `tiny`) and the mono family;
    - the `.section-title` eyebrow recipe and its `.section-title--plain` opt-out.

    Values are not copied; the section says they live in `css/tokens.css` and `css/fonts.css`.
- [ ] `tests/test_ui_control_inventory.py`:
  - drops `SECTIONS_DIR`, `LIBRARY_SECTIONS`, the 9-file pin and the section-content tests;
  - adds `test_every_factory_has_a_contract_test`: every factory name is called as `App.ui.<name>(` in at least one `tests/browser/test_ui_*.py`;
  - scopes `test_inventory_rows_are_classified` to the control tables, for example by stopping at the "Tokens and type" heading, so that section's tables are not parsed as control rows;
  - updates the module docstring.
- [ ] Every dependent test is rewritten and passes:
  - `tests/test_settings_pages_static.py`: the table is 6 rows. The `devOnly` assertions are removed along with the mechanism, and the docstring is updated.
  - `tests/test_nav_helper.py:59`: the `settings/design-language` DD2 row is removed, together with `_nav.py:41,221-222`'s legacy branch if it exists only for that row.
  - `tests/test_nav_guard_static.py:28-34`: the `confirmDialog` caller subset is narrowed to the remaining real callers, and the docstring is updated.
  - `tests/test_makefile_verify_serving.py:25`: samples another `admin/` file.
  - `tests/test_ui_guards.py`: `DYNAMIC_SINK_BASELINE`'s two design-language keys are removed. The testid registry sync passes after the registry edit below.
  - `tests/browser/test_ui_reference_page.py`: deleted.
  - `tests/browser/test_router_core.py`: drop the `design-language` round-trip spec (about `:112`). The two dev-route tests (about `:490-513`) become one or two unknown-route tests for `#settings/design-language`: at boot it lands on `#chats`; after boot the current route is restored.
  - `tests/browser/test_flow_admin_settings_nav.py`:
    - `GROUPS` loses Developer;
    - the dev-off "no Developer group" test (about `:135-150`) is deleted or folded into a "no Developer group, ever" assertion;
    - `test_design_language_page_has_no_section_nav_sample` (about `:343-356`) is deleted.
  - `tests/browser/test_flow_keyboard.py:208`: `_SETTINGS_NAV_ORDER` loses the page, and the link count follows.
  - `tests/browser/test_flow_jump_to.py`:
    - `SETTINGS_PAGES` loses the row;
    - the "settings" query count and the empty-install count follow (7 → 6 pages; New chat plus pages);
    - the dev-mode and dev-off candidate tests (about `:718-745`) are deleted;
    - the "a" query cap (about `:696`) is re-checked.
  - `tests/browser/_lists.py:251`: `SETTINGS_PAGE_TITLES` loses the entry, and the docstring follows.
  - `tests/browser/test_ui_nav_groups_contract.py`: uses "design-language" only as harness fixture data. Change the fixture label to a neutral one so the grep criterion holds. No behaviour change.
- [ ] `docs/ui-testid-registry.md`: the page-only rows (`ui-demo-chooser`, `-close`, `-row`, `-search`, `ui-demo-modal`, `ui-demo-drawer-`, `ui-demo-drawer-toggle-`) are moved to the Retired table. The `settings-nav-` row's prose no longer mentions `-design-language`. The registry sync test passes.
- [ ] Behavior specs amended so no step depends on the page or the Developer group:
  - `tests/behavior/list-and-detail.md` step 18;
  - `tests/behavior/workbench-navigation.md` step 5;
  - `tests/behavior/shell-navigation-smoke.md` step 6;
  - `tests/behavior/jump-to-palette.md`, Out of Scope bullet.

  Past run logs are left as history.
- [ ] Docs:
  - `CLAUDE.md`: the route list, the Settings nav groups, the "every factory needs a demo on the dev-mode page" convention (becomes "a catalogue row and engine-parametrized contract tests"), and the contracts-lane description.
  - `the_one/agents.md`: about `:167`, `:169`, `:1570`, `:1947`, `:2053-2054` (the "Adding a factory" steps), `:2131`, `:2323`, `:2351`.
  - `.env.example:27`.
  - The `scripts/webkitgtk_probe.py:9-11` docstring example (use another page, for example `#settings/appearance`).
  - The Makefile's stale "18 static-asset paths" comment, if the leg confirms it is stale.
- [ ] Gates pass:
  - `make test-unit` (the documented skip count);
  - `ruff check`/`ruff format --check` on `the_one/ tests/ scripts/ evals/`;
  - the browser lanes that hold the changed files, run through `scripts/run-tests.sh`: `routing`, `settings`, `shared` and `contracts`, with `THE_ONE_TEST_NETNS=1`, and `THE_ONE_REQUIRE_WEBKIT=1` for `contracts`.
- [ ] `grep -rn "design-language\|devOnly" the_one/ tests/ scripts/ docs/ CLAUDE.md .env.example Makefile` returns only history: `tests/behavior/*/runs/*.md`.

## Verification Steps
- `git status` / `ls` confirm the deletions; `grep -c 'src="/static' the_one/interfaces/web/static/index.html` plus the css links equals 71.
- The grep criteria above.
- `make test-unit`.
- `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python TEST_TIMEOUT=1500 bash scripts/run-tests.sh --lane routing -x`; then the same for `settings` and `shared`; then `THE_ONE_REQUIRE_WEBKIT=1` with `--lane contracts`.
- `.venv/bin/ruff check the_one/ tests/ scripts/ evals/ && .venv/bin/ruff format --check the_one/ tests/ scripts/ evals/`.
- Read the amended behavior-spec steps against the app's Settings nav: six pages in two groups.

## Implementation Guidance

1. **Delete the page and its scripts.** Remove the 17 `<script>` tags at `index.html:94-110` (about). Update the script-count pin to 71, keeping its comment history style: add a dated line.
2. **Remove the dev-only mechanism**, following the citations in Acceptance Criteria 3: `settings-pages.js:32` (the only `devOnly:true` row) and `:10,19-20`; `router.js:20,101,220-221,363`; `admin.js:72-75,146-154,246-247`; `jump-to.js:89,162`. Keep `App.config.dev_mode` and everything else that reads it.
3. **Delete the page-only CSS**, grepping each class first.
4. **Catalogue.** Rewrite the inventory doc's header and guard section, fix the two rows, and add the Tokens and type section at the end of the document, after every control table. Read the token roles from the comments in `css/tokens.css`. Do not invent roles: if a token has no comment, describe it from its use.
5. **Inventory test.** Implement the new rule and scope the row parser.
6. **Rewrite the remaining tests**, following the list. Grep `tests/` for `design-language`, `Developer`, `devOnly` and `ui-demo` to catch anything the list misses, and record any extra file in the flight log.
7. **Registry, behavior specs, docs.**
8. **Run the gates.** Record the browser lanes' wall times in the flight log, since lane budgets are tracked.

## Edge Cases
- **Dev mode on in browser lanes.** The browser-lane app runs with `THE_ONE_DEV_MODE=true`, so the unknown-route test must prove the route is unknown even with dev mode on.
- **`jump-to.js`'s dev check** may guard more than `devOnly` rows. Remove only what exists solely for `devOnly`. If anything else uses it, keep it and say so in the flight log.
- **`DYNAMIC_SINK_BASELINE` removals never fail.** Remove the two keys anyway; leg 02 replaces the counting.
- **Comment-only mentions** of the page in surviving files (for example `components.css:252`, where "design-language" is a phrase) are reworded so the grep criterion holds.

## Files Affected
- **Deleted:** `static/js/areas/admin/design-language-page.js`, `static/js/areas/admin/design-language/*.js` (16), `tests/browser/test_ui_reference_page.py`.
- **Modified (runtime):** `static/index.html`, `static/js/settings-pages.js`, `static/js/router.js`, `static/js/areas/admin.js`, `static/js/jump-to.js`, `static/css/admin.css`, `static/css/components.css`.
- **Modified (tests):** `tests/test_ui_control_inventory.py`, `test_settings_pages_static.py`, `test_nav_helper.py`, `test_nav_guard_static.py`, `test_index_asset_cache_busting.py`, `test_makefile_verify_serving.py`, `test_ui_guards.py`, `tests/browser/test_router_core.py`, `test_flow_admin_settings_nav.py`, `test_flow_keyboard.py`, `test_flow_jump_to.py`, `test_ui_nav_groups_contract.py`, `_lists.py`, `_nav.py`.
- **Modified (docs and specs):** `docs/ui-control-inventory.md`, `docs/ui-testid-registry.md`, `tests/behavior/{list-and-detail,workbench-navigation,shell-navigation-smoke,jump-to-palette}.md`, `CLAUDE.md`, `the_one/agents.md`, `.env.example`, `scripts/webkitgtk_probe.py`, `Makefile` (comment only).

## Citation Audit
Line numbers are from the Flight Director's dependency survey at `59992fd`, re-checked 2026-10-15 for:
- `tests/test_ui_control_inventory.py:19,87,96` (SECTIONS_DIR, glob, 9-file pin);
- `tests/test_settings_pages_static.py:47-56` (7-row table with `design-language … True`);
- `tests/browser/test_router_core.py:112,490-513`;
- `tests/test_index_asset_cache_busting.py:87` (`== 88`).

The rest are cited "about": the Developer re-locates them by grep before editing.

## Design Review Addenda (2026-10-15)
These are binding additions to the criteria above:
- **`tests/test_settings_pages_static.py` is rewritten, not trimmed.** Its row regexes (`:23`, `:27`) hard-require `devOnly: (true|false)` and an optional `, dev: true`, and `:82-83` cross-checks dev routes between the router and the page table. Rewrite the regexes, `table()`'s return shape (drop the dev flag) and remove the dev-route cross-check, keeping a router-versus-table consistency check for the remaining pages.
- **`tests/test_makefile_verify_serving.py:25`**: the replacement sample must be a surviving file (for example `admin/system-page.js`), because `:28` checks that every derived file exists.
- **`tests/browser/test_flow_jump_to.py`**:
  - delete `:718-745`, including the `[data-ui-demo]` wait at `:727`;
  - `:687` and `:745` follow `len(SETTINGS_PAGES)`;
  - verify the empty-install count by reading it, not assuming.
- **The unknown-route test asserts `App.config.dev_mode === true` as a precondition**, then shows that `#settings/design-language` is unknown. It also covers `#admin/design-language`, which reaches the same page through the `admin` alias today. Both must land as unknown routes (boot → `#chats`; after boot the current route is restored).
- **`.list-item`:**
  - before deleting, confirm that no `.list-item …` descendant selector survives anywhere in `static/css/`;
  - reword the comments citing `.list-item.confirm-delete` in `chat.css:569` and `studio.css:1324-1326`;
  - guard fixtures in `tests/test_nav_helper.py` (`:385-424`, `:535`) stay as they are.
- **Doc-only mentions to fix:**
  - `tests/browser/test_flow_admin_navigation.py:42` docstring;
  - `test_flow_admin_settings_nav.py:42,136,187` comments (the "last link" comment at `:187` becomes stale);
  - `tests/browser/_lists.py:60` docstring;
  - all three `_nav.py` spots (`:41`, `:221-222` and the docstring map);
  - the count-pin comment's stale "All 80 /static refs" (fix it with the new dated line).

  Leave `test_index_asset_cache_busting.py:58`'s history comment.
- **`tests/test_nav_guard_static.py`**: rename the test along with the narrowed caller set `{"rules-notes-tab.js"}`.
- **Run the criteria greps before and after the edit**, with `ui-demo` added to the post-grep. After the edit, `ui-demo` may remain only in the registry's Retired table, that history comment and run logs.
- The Makefile's `:123` "18 static-asset paths" and "19 curl" comments are stale; fix both (comments only).
- `tests/behavior/.env.hat*` matches "Developer" only through the Discord Developer Portal. Ignore it.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
