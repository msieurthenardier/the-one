# Leg: close-the-counts

**Status**: completed
**Flight**: [Chats, and closing every count to zero](../flight.md)

*Rewritten after design review cycle 2 (2026-10-27), so the body reads as one current plan. The review history is kept at the end; where it differs, this body is current.*

## Objective
Bring every mission count to zero in code and docs (DD14):
- **the retired-API aliases** deleted, with their guard line set and test call sites. The ownership allowance tables are already empty since legs 05b and 07, so this leg confirms them and clears `START_ROWS`;
- **the catalogue:** no "not yet defined" row, a unit test that keeps it so, and the "Data table" row moved to a Retired table (D5);
- **the seven orphaned badge kinds** deleted (D6), with their test-only producers retargeted;
- **every product-dead CSS family** deleted, and the unused-selector report made trustworthy and clean;
- **the docs** in their final state, including squawk 0272.

## Context
- **Flight decisions:** DD14, D5, D6, DD13 and DD15.
- **State at HEAD `942c9b5`** (verified at design review cycles 1-2):
  - `OWNERSHIP_ALLOWANCE = {}`, `TOTAL_USES = {}`, `MOVES = []` (a comment only), `HTML_SINK_ALLOWANCE = {}`, `SINK_TOTAL = 0`;
  - `START_ROWS` still lists 23 stale keys;
  - `RETIRED_APIS` (`tests/test_ui_ownership.py:52-59`) scans code with comments stripped.
- **The aliases still defined:**
  - `window.App.confirmDelete = App.ui.confirm;` (`ui/confirm.js:195`);
  - `window.App.consentLink = App.ui.consentLink;` (`ui/consent-link.js:118`);
  - `app.js`: `escapeHtml` / `escapeAttr` (`:240-250`), `showFlash` (`:287`), exports `:303-307`;
  - `icons.js:82-90`: `Object.assign(window.App, {icons, icon})`; `icon` and its warning string go, `icons` stays (the rail and `ui/core.js` read it).

  The dead `icon:` fields of the three `registerArea` descriptors are at `chat.js:4`, `studio.js:15` and `admin.js:4`; nothing reads `descriptor.icon`. **No product code calls any alias.**
  - **Test callers:** `test_ui_confirm_contract.py` (`:54-273`), `test_ui_list_pane_chats_contract.py` (`:242`, `:449`, `:493`, `:508`, `:527`, `:549`) and `test_ui_copy_contract.py` (`:148-158`, `:243-245`).
  - `_ALIAS_LINES` is at `tests/test_ui_library_source.py:31`, with its `continue` at `:56`.
- **D6.** A producer grep over `the_one/` and `tests/` finds **no product producer** for `approved`, `connectors`, `dismissed`, `execution`, `filesystem`, `time` or `web` (`badge--` is built only by `ui/feedback.js` from caller-supplied kinds). Their only producers and mirrors are in tests and fixtures:
  - `tests/browser/test_ui_tile_contract.py` (`~:598`, `:628`, `:677-700`, `:682`);
  - `tests/browser/_legacy_tool_css.py:339-346` (a frozen fixture);
  - `tests/browser/test_ui_list_pane_chats_contract.py:96`;
  - `tests/browser/_probe_mount_ui.js:60`, `:74`;
  - `tests/browser/test_ui_choice_contract.py:340-348` (`"kinds": 18`, a throws check with `web`);
  - both theme dicts in `tests/browser/design_tokens.py` (`~:116-142`, `~:212-233`);
  - `tests/test_design_tokens_a11y.py` (`_TOKEN_BADGE_KINDS` `~:1170-1190`, `_BADGE_INK_PAIRS` `~:1348-1354`, `test_badge_semantic_kinds_sit_on_the_gated_ladder` `~:1163`);
  - `tests/test_ui_badge_kinds.py` (18).

  The product side is `BADGE_KINDS` (`ui/feedback.js:8-27`), `components.css:1963-1985` and `tokens.css:175-207`, `:338-368` (both themes). `.msg-pending-approval-badge--approved/--dismissed` (`chat.css:396`, `:400`) are separate classes in the dead `.msg-pending-approval*` family.
- **Product-dead CSS**, classified by hand (`scripts/unused_selectors.py` today counts behavior run logs and `data-testid` values as users, which masks some):
  - `.test-result*` (`components.css:1376-1450`; `data-testid="test-result"` in `tools-editor.js:264` is a testid, not the class), plus the `scripts/ui_capture.py:746-748` fallback selector and the comments naming it (`studio.css:992`, `components.css:1394`, `:1430`);
  - `.msg-pending-approval*` with its `-badge--approved/--dismissed` and the dead base `.msg` rule (`chat.css:327-~410`), plus the contrast row `test_design_tokens_a11y.py:620-624`;
  - `.stub-content`, `.stub-sidebar` and children (`base.css`);
  - `.u-flex`, `.u-block` (`components.css` utilities; keep `.is-hidden`);
  - `.back-btn`, `.refresh-btn` (with its `_DISABLED_BUTTON_SELECTORS` row at `test_design_tokens_a11y.py:1635`), and `.field-row` and children (`components.css:123-129`, `~:225-255`). Their only test users are `to_have_count(0)` negatives, which keep passing, and comments.

  **Dynamic, not dead:** `.banner-error/info/warning` (`'banner banner-' + tone`, `ui/page.js:96`), `ui-disclosure--plain` (`disclosure.js:40`), and the prefix-matched `badge--` (kept kinds), `indicator-led--`, `ui-list-pane-` and `ui-menu-align-`.
- **The catalogue** (`docs/ui-control-inventory.md`):
  - `control_table_rows` reads only tables whose header starts `| Control |`;
  - the only "not yet defined" row is "Data table" (`:104`);
  - `test_inventory_rows_are_classified` accepts "not yet defined" (`:72-84`);
  - the header prose describing statuses is at `:4` and `:23-34`;
  - the "Owned by controls built later" table holds only `test-result`, and `test_ui_ownership.py` `owned_classes()` (`~:222`) reads it.
- **The line guard:** the remaining `tests/test_area_module_size.py` entry is `studio/provider-editor.js: 896`; the file has 895 lines. Mission criterion 8 holds: `studio.js` 753, `chat.js` 538, `admin.js` 385.
- **Squawk 0272:** item 1 (the lane-time sentence) was already updated by earlier legs; 09b refines the numbers. Item 2 is the four `agents.md` patterns.

## Inputs
- Batch B4 committed (HEAD `942c9b5`).

## Outputs
1. **The aliases:**
   - delete the two `window.App.*` lines, `App.showFlash`, `App.escapeHtml`, `App.escapeAttr`, `App.icon` (and its warning string) and the three `icon:` descriptor fields;
   - remove `_ALIAS_LINES`, its comment and the `continue`;
   - move the test callers to `App.ui.confirm` / `App.ui.consentLink`, and **delete** the two identity assertions (`test_ui_copy_contract.py:151`, `test_ui_confirm_contract.py:273`);
   - add `escapeHtml` and `escapeAttr` patterns to `RETIRED_APIS`, which stays as the regression guard;
   - confirm `App.icons` is still defined (`tests/browser/test_shell_rail.py:521` passes).
2. **The comment scrub (product only):** every comment in `the_one/` that names an alias moves to the `App.ui.*` name, including `components.css` `:541`, `:865`, `:1154`, `:1475`; `dialog.js:7`; `agent-editor.js:35`; `ui/confirm.js:6`, `:13`, `:82`; `ui/core.js:216`; `ui/list-pane.js:137`, `:166`, `:556`; and any other the code-only grep surfaces. Test docstrings and `RETIRED_APIS` strings may keep historical mentions.
3. **The allowances:** confirm the empty tables; set `START_ROWS = frozenset()`; update `_ui_ownership_allowance.py`'s docstring and comments to the closed state.
4. **D6:** delete the seven kinds from `BADGE_KINDS`, `components.css` and both themes in `tokens.css`. Retarget every test producer and mirror listed in Context to a kept kind (`ollama` or `local`), **including a deliberate edit of the frozen `_legacy_tool_css.py`**, with the reason in the flight log. `test_ui_choice_contract.py`'s count and `test_ui_badge_kinds.py` become 11, and the `design_tokens.py` dicts and `test_design_tokens_a11y.py` tables are trimmed. Record the producer grep (command and result) in the flight log.
5. **Dead CSS:** delete every family under "Product-dead CSS", with its contrast rows, the `ui_capture.py` fallback selector and the scrubbed comments.
6. **The unused-selector script:** it adds the `banner-` and `ui-disclosure--` dynamic prefixes, and skips `tests/behavior/**/runs/` and `data-testid` string values. Its report on every `css/*.css` then lists no unused selector. Prefix-matched dynamic users may still appear under "check by hand" and are documented in the flight log (after D6, `badge--` lists only kept kinds).
7. **The catalogue:**
   - move "Data table" to a new **Retired** table with a `| Retired control |` header, whose prose cites no `App.ui.<x>` that is not a factory;
   - delete the "Owned by controls built later" table, and guard `owned_classes()` against its absence if `test_catalogue_declares_owned_classes` needs it;
   - rewrite the header prose (`:4`, `:23-34`) for the final statuses;
   - update the rows that name aliases or dead CSS (`:47`, `:74` Badge, `:76`, `:77`, `:91`, `:114`, `:124`);
   - in `tests/test_ui_control_inventory.py`, delete the `"not yet defined"` branch (`:72-84`) and add `test_no_control_row_is_not_yet_defined`.
8. **The line guard:** tighten `studio/provider-editor.js` to 895.
9. **Docs:**
   - `docs/ui-testid-registry.md` `:106`, `:138`, `:269`, `:329`, `:432`;
   - `the_one/agents.md` `:28`, `:925`, `:1438`/`:1442`, `:1813` (check its kinds count), `:1935`, `:1970`, `:2124`, `:2134`, `:2142` ("KINDS (14)"), `:2160-2172` (including "not yet defined"), `:2218`; `:941` is history and may stay;
   - CLAUDE.md `:99` (`App.confirmDelete`, "13 `App.confirmDelete` call sites") and the totals paragraph (`~:293`), ending at 0 rows / 0 uses / 0 sinks;
   - squawk 0272: verify and record item 1; add the four patterns to `agents.md`; record its corrective action and verification (status `in-progress` until the flight commit);
   - `mission.md`'s "Alias shims" Known Issue: closing counts (all zero), checked off.

## Acceptance Criteria
- [ ] **No alias use in code:** a JS-code-only grep over `the_one/` with comments stripped finds no `App.confirmDelete`, `App.consentLink`, `App.showFlash`, `App.escapeHtml`, `App.escapeAttr` or `App.icon(`. `tests/test_ui_ownership.py`'s retired-API scan passes. A plain grep of `the_one/` comments finds none of these names either.
- [ ] `OWNERSHIP_ALLOWANCE`, `TOTAL_USES`, `MOVES` and `HTML_SINK_ALLOWANCE` are empty, and `START_ROWS` is `frozenset()`. `tests/test_ui_ownership.py`, `tests/test_ui_guards.py` and `tests/test_ui_library_source.py` pass.
- [ ] **The inventory:** `test_no_control_row_is_not_yet_defined` passes, and fails when a "not yet defined" control row is added (checked once, then reverted). The Retired table holds "Data table", and `test_catalogue_declares_owned_classes` passes.
- [ ] **D6:** `tests/test_ui_badge_kinds.py` pins 11 kinds. `test_ui_tile_contract.py`, `test_ui_choice_contract.py`, `test_ui_list_pane_chats_contract.py`, `test_design_tokens_a11y.py` and `test_token_definitions.py` pass.
- [ ] **The improved `scripts/unused_selectors.py`** on every `css/*.css` lists nothing unused. Its "check by hand" items are all documented dynamic users. Its output is in the flight log.
- [ ] **No sentence states a current total other than 0** in CLAUDE.md, `the_one/agents.md` or the catalogue; history phrasings may stay. Squawk 0272's four patterns are in `agents.md`.
- [ ] `tests/test_area_module_size.py` passes with 895.
- [ ] **Lanes:** `contracts-controls`, `contracts-overlay`, `contracts-chat` (`THE_ONE_REQUIRE_WEBKIT=1`), `chats`, `chats-transcript`, `shared`, `settings`, `settings-tools`, `library` and `providers`, at most three at a time. Then `make test-unit` (netns: 15 skipped expected), and `ruff` is clean.

## Verification Steps
1. **The code-only grep:** a small script in the session scratchpad that strips `//` and `/* */` comments from `the_one/interfaces/web/static/js/**/*.js` and greps the alias names. Also a plain `git grep` of `the_one/` for the names (comments included).
2. `.venv/bin/python -m pytest tests/test_ui_ownership.py tests/test_ui_guards.py tests/test_ui_control_inventory.py tests/test_ui_library_source.py tests/test_ui_badge_kinds.py tests/test_design_tokens_a11y.py tests/test_token_definitions.py tests/test_css_layers.py tests/test_area_module_size.py -q -x --timeout 120`.
3. `.venv/bin/python scripts/unused_selectors.py the_one/interfaces/web/static/css/*.css` (after the script change).
4. The lanes; then `make test-unit`; `ruff check`; `ruff format --check`.

## Implementation Guidance
1. **The aliases and their tests** (Outputs 1-3), then the guards.
2. **D6** (Output 4), then `contracts-controls` and the tile contract file at once.
3. **Dead CSS** (Output 5).
4. **The unused-selector script** (Output 6), then the report.
5. **The catalogue** (Output 7), the line guard (8) and docs (9).
6. **The lanes** and `make test-unit`.

## Edge Cases
- **A product producer** for a D6 kind surfacing mid-leg: stop, keep that kind, record why (none was found at review).
- **`owned_classes()` with the "built later" table gone:** guard the parse, and keep the test's other assertions.
- **The frozen legacy-tile fixture:** edit only the kind, not the comparison logic. Note it in the fixture's header.

## Files Affected
- **Product:** `the_one/interfaces/web/static/js/{app,icons,dialog}.js`, `js/ui/{confirm,consent-link,core,feedback,list-pane,page}.js`, `js/areas/{chat,studio,admin}.js`, `js/areas/studio/agent-editor.js`, `css/{components,chat,studio,base,tokens}.css`.
- **Tests:** `tests/test_ui_library_source.py`, `tests/test_ui_ownership.py`, `tests/_ui_ownership_allowance.py`, `tests/test_ui_guards.py`, `tests/test_ui_control_inventory.py`, `tests/test_ui_badge_kinds.py`, `tests/test_design_tokens_a11y.py`, `tests/test_area_module_size.py`, `tests/browser/{test_ui_confirm_contract,test_ui_list_pane_chats_contract,test_ui_copy_contract,test_ui_tile_contract,_legacy_tool_css,design_tokens,test_ui_choice_contract,test_shell_rail}.py`, `tests/browser/_probe_mount_ui.js`.
- **Scripts:** `scripts/unused_selectors.py`, `scripts/ui_capture.py`.
- **Docs:** `docs/ui-control-inventory.md`, `docs/ui-testid-registry.md`, `the_one/agents.md`, CLAUDE.md, `missions/31-control-library-everywhere/mission.md`, `squawks/0272-…`, the flight log.

## Citation Audit
- **Verified at design review cycles 1-2** (Sonnet, read-only, HEAD `942c9b5`): every line reference in Context, including the D6 producer grep and the unused-selector re-run.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.

## Design Review Amendments (cycle 1, 2026-10-27, needs rework; these take precedence)
- **The allowances are already empty.** This leg sets `START_ROWS = frozenset()` (it still lists 23 stale keys) and tidies `_ui_ownership_allowance.py`'s docstring and comments. `OWNERSHIP_ALLOWANCE`, `TOTAL_USES` and `MOVES` are only confirmed. `RETIRED_APIS` in `test_ui_ownership.py`, with its fixtures, **stays** as the regression guard against a re-introduced call; `escapeHtml` and `escapeAttr` patterns are added to it. The `OwnershipMove` machinery tests stay (they use their own fixtures).
- **`_ALIAS_LINES` is removed, not emptied:** the set, its comment and the `continue` at `test_ui_library_source.py:56`.
- **Alias callers and assertions:**
  - `test_ui_confirm_contract.py` (`:54-273`), `test_ui_list_pane_chats_contract.py` (`:242`, `:449`, `:493`, `:508`, `:527`, `:549`) and **`test_ui_copy_contract.py`** (`:148-158`, `:243-245`) move to `App.ui.*`;
  - the identity assertions `App.consentLink === App.ui.consentLink` (`test_ui_copy_contract.py:151`) and `App.confirmDelete === App.ui.confirm` (`test_ui_confirm_contract.py:273`) are **deleted**;
  - `icons.js` keeps `App.icons` and drops `icon` and its warning string;
  - the header comments in `core.js:216` and `ui/confirm.js` move off the alias names;
  - a check that `App.icons` is still defined (the rail needs it) is added or confirmed, and `tests/browser/test_shell_rail.py:521` passes.
- **The acceptance grep is redefined.** It is the `test_ui_ownership.py` retired-API scan plus a JS-code-only grep with comments stripped over `the_one/`. **Product comments and CSS comments that name an alias are scrubbed:** `components.css` `:541`, `:865`, `:1154`, `:1475`; `dialog.js:7`; `agent-editor.js:35`; others the grep finds. Test docstrings and the guard strings may keep historical mentions.
- **D6: all seven kinds are deleted** (the operator approved D6). The producer grep finds **no product producer**; every producer is in tests or fixtures, and this is recorded in the flight log. These change with the deletion:
  - `tests/browser/test_ui_tile_contract.py` (`~:598`, `:628`, `:677-700`): retargeted to a kept kind (`ollama` or `local`);
  - the frozen `tests/browser/_legacy_tool_css.py` (`:339-346`): edited **deliberately** to a kept kind, with the reason in the log;
  - `test_ui_list_pane_chats_contract.py:96`, `_probe_mount_ui.js:60`, `:74`, and `test_ui_choice_contract.py:340-348` (its `"kinds": 18` becomes 11, and its throws check uses a deleted kind);
  - both theme dicts in `tests/browser/design_tokens.py` (`~:116-142`, `~:212-233`);
  - `tests/test_design_tokens_a11y.py` (`_TOKEN_BADGE_KINDS` `~:1170-1190`, `_BADGE_INK_PAIRS` `~:1348-1354`, `test_badge_semantic_kinds_sit_on_the_gated_ladder` `~:1163`);
  - `components.css:1963-1985`, `tokens.css:175-207` and `:338-368` (both themes);
  - `tests/test_ui_badge_kinds.py` (18 becomes 11);
  - `agents.md:1970` and `:2142` ("KINDS (14)").

  D6 runs **before** the dead-CSS deletions, then `contracts-controls` and the tile contract file.
- **Dead CSS, classified by hand** (the script's report was masked: it counts behavior run logs and `data-testid` values as users). Delete:
  - `.test-result*` (`components.css:1376-1450`), plus the `ui_capture.py:746-748` fallback selector;
  - `.msg-pending-approval*` and the dead base `.msg` rule (`chat.css:327-~410`), with the contrast row at `test_design_tokens_a11y.py:620-624`;
  - `.stub-*` (`base.css`);
  - `.u-flex`, `.u-block`;
  - **added at review:** `.back-btn`, `.refresh-btn` (with its `_DISABLED_BUTTON_SELECTORS` row at `test_design_tokens_a11y.py:1635`) and `.field-row` and children (`components.css:123-129`, `~:225-255`). These are product-dead; their only test users are `to_have_count(0)` negatives (which keep passing) and comments. The mission criterion requires removing unused style rules (FD answer).

  **Not dead:** `.banner-error/info/warning` (emitted as `'banner banner-' + tone`). `scripts/unused_selectors.py` adds the `banner-` and `ui-disclosure--` prefixes, and **skips `tests/behavior/**/runs/` and `data-testid` string values**, so a "clean" report means something. The acceptance line applies to that improved report.
- **Catalogue mechanics:**
  - the Retired table uses a header other than `| Control |` (for example `| Retired control |`), so `control_table_rows` ignores it;
  - the `"not yet defined"` branch in `test_inventory_rows_are_classified` (`:72-84`) is deleted, and `test_no_control_row_is_not_yet_defined` is added;
  - the Retired table's prose cites no `App.ui.<x>` that is not a factory (`inventory_citations` scans the whole file);
  - the "Owned by controls built later" table (only `test-result`) is deleted whole, and `test_ui_ownership::test_catalogue_declares_owned_classes` is re-run;
  - the header prose at `:4` and `:23-34` is rewritten, without the "migrate to status" paragraph or the "next mission" wording;
  - rows that name aliases or dead CSS are updated: `:47` (consentLink), `:74` (Badge: the kinds, "per-area badge classes migrate"), `:76`, `:77` (`App.icon`, `showFlash`), `:91`, `:114` (the `.msg-pending-approval*` note), `:124`.
- **Docs, the full list:**
  - `docs/ui-testid-registry.md` `:106`, `:138`, `:269`, `:329`, `:432`;
  - `the_one/agents.md` `:28`, `:925`, `:1438`/`:1442`, `:1935`, `:1970`, `:2124`, `:2134`, `:2142`, `:2160-2172` (including "not yet defined" at `:2164`, `:2167`), `:2218` (`escapeHtml`/`escapeAttr`);
  - CLAUDE.md `:99` (`App.confirmDelete`; "13 `App.confirmDelete` call sites" in the confirm-lapse section) and the totals paragraph (`~:293`), which ends at 0 rows / 0 uses / 0 sinks. History phrasings ("from 66 / 167", "from 5 at the close of Flight 5") may stay, so the "no live text" check means "no sentence stating a current total other than 0".
- **Squawk 0272:** item 1 (the lane-time sentence) was already updated by earlier legs; this leg verifies it and records that. The four `agents.md` patterns are added.
- **The line guard:** `tests/test_area_module_size.py`'s remaining entry `studio/provider-editor.js` is tightened from 896 to its actual 895 (shrink-only). Mission criterion 8 holds (`studio.js` 753, `chat.js` 538, `admin.js` 385), recorded for the mission close-out.
- **The citations are corrected** to the review's verified line numbers above.

## Design Review
- **Developer design review, cycle 1** (Sonnet, 2026-10-27, after B4): **needs rework.** Applied as the amendments above. FD answers:
  - full D6, with deliberate test and fixture retargets;
  - the three newly found dead families are deleted;
  - `_ALIAS_LINES` is removed;
  - the grep is redefined, and product comments are scrubbed.
- **A second cycle follows** (needs rework).
- **Developer design review, cycle 2** (Sonnet, 2026-10-27): approve with changes. Every cycle-1 finding was resolved against the code. Its remaining points (contradictions between the original body and the amendments, the under-listed Files Affected, an incomplete comment-scrub list, the `agents.md` `:941`/`:1813` lines, and the dynamic-user note) are folded into the **rewritten body above**. FD answers: the `.test-result` comments are scrubbed; `owned_classes()` is guarded if the table's absence breaks it. This was the final cycle.
