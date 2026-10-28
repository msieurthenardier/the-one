# Leg: close-the-counts

**Status**: planning
**Flight**: [Chats, and closing every count to zero](../flight.md)

## Objective
Bring every mission count to zero in code and docs (DD14):
- the retired-API aliases deleted, with their guard lines and test call sites;
- `OWNERSHIP_ALLOWANCE`, `TOTAL_USES` and `MOVES` empty (the guard machinery stays);
- the catalogue: no "not yet defined" row, a unit assertion that keeps it so, and the "Data table" row moved to a new Retired table (D5);
- the orphaned badge kinds deleted (D6);
- the dead CSS deleted, and the unused-selector report reviewed;
- `the_one/agents.md`, CLAUDE.md and the catalogue in their final state, including squawk 0272.

## Context
- **Flight decisions:** DD14 (the whole list), D5, D6, DD13 and DD15.
- **This leg is designed against the tree after batch B4** (legs 06-08). The Citation Audit below is re-run when B4 lands, and the leg goes `ready` only then.
- **The aliases at design time** (2026-10-27):
  - `window.App.confirmDelete = App.ui.confirm;` (`ui/confirm.js:195`);
  - `window.App.consentLink = App.ui.consentLink;` (`ui/consent-link.js:118`);
  - `App.showFlash` (`app.js:287`, exported `:307`);
  - `App.escapeHtml` and `App.escapeAttr` (`app.js:240-250`, exported `:303-304`; dead);
  - `App.icon` (`icons.js:84`).
  - `App.iconNode` and `App.noteFlag` were already deleted in leg 03a.
  - `_ALIAS_LINES` (`tests/test_ui_library_source.py:31-34`) pins the two `window.App.*` lines.
  - The dead `icon: App.icons.*` fields of the three `registerArea` descriptors are at `chat.js:4`, `studio.js:15` and `admin.js:4`; `registerArea` never reads `icon`.
  - **The expected callers after B4:** none in app code (05b removes `App.confirmDelete` and `App.consentLink.`; leg 07 removes markdown's `App.icon` and `App.showFlash`). Tests still call the aliases (`test_ui_confirm_contract.py`, `test_ui_list_pane_chats_contract.py`, `test_ui_copy_contract.py`); they move to the `App.ui.*` names.
- **The catalogue** (`docs/ui-control-inventory.md`):
  - at design time the "not yet defined" rows were the Provider model picker (leg 08 closes it) and "Data table" (`:104`);
  - its header prose (`:4`, `:23-34`) describes the two statuses;
  - `tests/test_ui_control_inventory.py` accepts "not yet defined" today (`:72-84`).
- **Badge kinds** (`ui/feedback.js:8-27`). D6 deletes `approved`, `connectors`, `dismissed`, `execution`, `filesystem`, `time` and `web` after a grep confirms no producer: no JS builds `badge--{kind}` for them, and no `App.ui.badge({kind})` passes them. Their tokens (`css/tokens.css` `--badge-*`), the contrast rows (`tests/test_design_tokens_a11y.py`), `design_tokens.py` if it lists them, and the `tests/test_ui_badge_kinds.py` pin (18 → 11) move together.
- **Dead CSS (code survey §9):**
  - `.test-result*` (`components.css` about `:1330-1347`, `:1390-1400`);
  - `.msg-pending-approval*` (`chat.css` about `:684-769`), with its contrast row (`test_design_tokens_a11y.py` about `:624-628`);
  - `.stub-content`, `.stub-sidebar` and their children (`base.css` about `:112-115`);
  - `.u-flex`, `.u-block` (`components.css` utilities; keep `.is-hidden`).

  The catalogue's "Owned by controls built later" table lists `test-result`. `scripts/unused_selectors.py` needs `ui-disclosure--` (and any other factory-built prefix) in `DYNAMIC_PREFIXES`.
- **Docs:**
  - `the_one/agents.md`: "Control library (`App.ui`)" (the totals, the flight's controls, the closed counts), the chat module map, the composer/transcript/telemetry contracts and the `rescueFlashes` remnant if any is left;
  - CLAUDE.md: the control-library totals paragraph ("Current whole-app totals …"), the "Chat composer", "Chats pane" and agent-drawer passages, the lane table (budgets are leg 09b's) and squawk 0272's stale lane-time sentence;
  - squawk 0272's four `agents.md` patterns: flash to the page when the action closes the item; the `.ui-kv-center` strut; the overlay/bubble typography reset; a new badge kind bumps the `test_ui_badge_kinds.py` pin.

## Inputs
- Batch B4 (legs 06-08) landed and committed.

## Outputs
- **The aliases deleted:**
  - the two `window.App.*` alias lines, `App.showFlash`, `App.escapeHtml`, `App.escapeAttr`, `App.icon` and the three `icon:` descriptor fields;
  - `_ALIAS_LINES` emptied (or removed with its check, if the test then has nothing to pin);
  - every test call site moved to `App.ui.confirm` / `App.ui.consentLink`;
  - `App.icons`, the table that `ui/core.js` reads, stays.
- **The allowances:** `OWNERSHIP_ALLOWANCE = {}`, `TOTAL_USES = {}`, `MOVES = []`. `HTML_SINK_ALLOWANCE = {}` and `SINK_TOTAL = 0` (since leg 01). Any `START_ROWS` entry left is pruned if the guard allows, or documented. `test_chat_area_has_no_baselined_sink`'s docstring is current.
- **The catalogue:**
  - no row reads "not yet defined";
  - the "Data table" row moves to a new **Retired** table, with its history text;
  - the "Owned by controls built later" table loses `test-result`, and is deleted if then empty;
  - the header prose describes the final statuses;
  - `tests/test_ui_control_inventory.py` gains a test that fails on any control row whose status is "not yet defined".
- **D6:** the seven badge kinds and their tokens, contrast rows and pins are deleted; the catalogue's Badge row is updated.
- **Dead CSS:** the families above are deleted, with their contrast row. `scripts/unused_selectors.py` learns the dynamic prefixes. The report, run on every stylesheet, is clean apart from documented dynamic users, and its output is recorded in the flight log.
- **Docs to their final state:** the passages listed above. Squawk 0272's corrective action and verification are recorded (status `in-progress` until the flight commit). The totals read zero.
- **The mission artifact:** `mission.md`'s "Alias shims" Known Issue gets its closing counts (all zero) and is checked off.

## Acceptance Criteria
- [ ] `git grep -nE "App\.(confirmDelete|consentLink|showFlash|escapeHtml|escapeAttr|icon)\b" -- the_one/ tests/ scripts/` finds no code use. History documents (flight logs, debriefs, squawks, release notes) are excluded by path.
- [ ] `OWNERSHIP_ALLOWANCE`, `TOTAL_USES`, `MOVES` and `HTML_SINK_ALLOWANCE` are empty, and `tests/test_ui_ownership.py` and `tests/test_ui_guards.py` pass.
- [ ] The new inventory test passes, and fails when a "not yet defined" row is added (checked once, then reverted). The Retired table holds "Data table".
- [ ] **D6:** `tests/test_ui_badge_kinds.py` pins 11 kinds, and the contrast and token tests pass.
- [ ] `scripts/unused_selectors.py` on every `css/*.css` lists nothing unused apart from documented dynamic users. The output is in the flight log.
- [ ] CLAUDE.md's totals read 0 rows / 0 uses and 0 sinks, squawk 0272's sentence is fixed, and `the_one/agents.md` has the four patterns. A grep for the old totals ("25 ownership rows", "5 HTML-string sinks") finds no live text.
- [ ] **Lanes:** `contracts-controls`, `contracts-overlay`, `contracts-chat` (`THE_ONE_REQUIRE_WEBKIT=1`), `chats`, `chats-transcript`, `shared` and `settings` (badge kinds in tool categories, if any). `make test-unit` passes, and `ruff` is clean.

## Verification Steps
1. The greps in the criteria.
2. `.venv/bin/python -m pytest tests/test_ui_ownership.py tests/test_ui_guards.py tests/test_ui_control_inventory.py tests/test_ui_library_source.py tests/test_ui_badge_kinds.py tests/test_design_tokens_a11y.py tests/test_token_definitions.py tests/test_css_layers.py -q -x --timeout 120`.
3. `.venv/bin/python scripts/unused_selectors.py the_one/interfaces/web/static/css/*.css`.
4. The lanes, at most three at a time; then `make test-unit`.

## Implementation Guidance
1. **The aliases**, then their test call sites; `_ALIAS_LINES`.
2. **The allowances** to empty; prune `START_ROWS`.
3. **The catalogue:** Retired table, header prose, the new inventory test.
4. **D6**, after the producer grep.
5. **Dead CSS** and the unused-selector report.
6. **Docs** and squawk 0272; the mission's Known Issue.
7. **The lanes** and `make test-unit`.

## Edge Cases
- **An alias with a remaining caller** found by the grep (for example a comment-only use is fine; a code use is not). Move the caller, don't keep the alias.
- **A badge kind that still has a producer** (the grep finds one): keep that kind and record why.
- **The unused-selector script counts `tests/` as a user:** a selector used only by a test is dead product CSS. Check each hit by hand.

## Files Affected
- `the_one/interfaces/web/static/js/{app,icons}.js`, `js/ui/{confirm,consent-link,feedback}.js`, the three area entry modules, `css/{components,chat,base,tokens}.css`.
- `tests/test_ui_library_source.py`, `tests/_ui_ownership_allowance.py`, `tests/test_ui_guards.py`, `tests/test_ui_control_inventory.py`, `tests/test_ui_badge_kinds.py`, `tests/test_design_tokens_a11y.py`, the alias-calling contract tests, `scripts/unused_selectors.py`.
- `docs/ui-control-inventory.md`, `the_one/agents.md`, CLAUDE.md, `missions/31-control-library-everywhere/mission.md`, `squawks/0272-…`, the flight log.

## Citation Audit
- `ui/confirm.js:195`, `ui/consent-link.js:118`, `app.js:240-250`, `:287`, `:303-307`, `icons.js:84`, `tests/test_ui_library_source.py:25-35`, `chat.js:4`, `studio.js:15`, `admin.js:4`, `ui/feedback.js:8-27`, `docs/ui-control-inventory.md:4`, `:23-34`, `:60`, `:104`. FD grep (2026-10-27, after leg 05a).
- **Re-run after batch B4 landed** (FD grep, 2026-10-27, B4 uncommitted):
  - `OWNERSHIP_ALLOWANCE`, `TOTAL_USES` and `MOVES` are **already empty** (legs 05b and 07 retired the last rows; `MOVES` holds only a comment), so this leg confirms them and tidies the comments rather than emptying them;
  - the aliases are still defined: `ui/confirm.js:195`, `ui/consent-link.js:118`, and `app.js` `escapeHtml` / `escapeAttr` `:240-250`, `showFlash` `:287`, exports `:303-307`; `App.icon` is at `icons.js:84` (its only reference left is its own warning string);
  - no app code calls any alias. Tests still do: `test_ui_confirm_contract.py` (12), `test_ui_list_pane_chats_contract.py` (6), and the guard tests' fixtures (`test_ui_ownership.py`, `_ui_ownership_allowance.py` comments);
  - the only "not yet defined" control row left is "Data table" (`:104`); the header prose is at `:4`, `:23-34`.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
