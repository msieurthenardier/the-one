# Leg: settings-close

**Status**: ready
**Flight**: [Settings on the library](../flight.md)

## Objective
Close the flight's counts, styles, captures, lanes and docs:
- `admin.css` becomes Settings-only, with the Flight 5 rules moved to `studio.css` as a recorded row move;
- every Settings file is at zero sinks and zero allowance rows, apart from the Flight 5 chip-list path;
- the unused-selector report and the single-consumer option recheck are reviewed;
- the after captures are taken and the ledger is complete;
- lanes are re-budgeted (a possible `settings` split);
- the catalogue, registry, CLAUDE.md and `agents.md` are final;
- the behavior specs are checked.

## Context
- **Flight decisions:** DD2 (the line guard), DD10 (lanes and specs), DD11, DD12 (the owned-list check), the mission criteria (the counts), and the Flight 3 debrief recommendation 5 (close checks).
- **The Flight 5 rules in `admin.css`:** the `.area-studio` halves of the legacy `.tool-enable-switch*` rules and of the chip-list block (`.chip-list-editor:not(.ui-chip-list)…`, `.chip-list-input:not(.ui-chip-list-input)`, `.chip`). They move to `studio.css`, with their `OWNERSHIP_ALLOWANCE` rows moving from `css/admin.css` to `css/studio.css`, unchanged in count. Record it in the flight log as a move, not new debt. Their `test_design_tokens_a11y.py` pins are repointed to `studio.css`.
- **The single-consumer options** (the Flight 3 debrief list, plus this flight's new options): for each, record whether a Settings consumer now uses it, or that it stays single.
- **"Declared not controls":** `p.admin-system-text` (if any remains), the Settings nav host `div.admin-settings-nav`, `.admin-content` and `platform-section`. Add a short note to the catalogue.
- **`components.css:1245`**, the header-action rule, is dead after 04a's page variant (it was not reused). Confirm with the unused-selector report and delete it.

## Inputs
- Every earlier leg landed.

## Outputs
- `admin.css` holds Settings rules only. `studio.css` gains the moved Flight 5 rules.
- **Counts verified and pasted into the flight log:**
  - `HTML_SINK_ALLOWANCE` has no row for `tools-editor.js`, `tools-grid.js`, `admin.js`, `knowledge-settings-page.js` or `theme.js`;
  - `OWNERSHIP_ALLOWANCE` has no row for the Settings page files, `admin.js`, `tools-page.js`, `tools-grid.js`, `tools-editor.js`, `tabs.js` or `admin.css`;
  - `tools-form-helpers.js` keeps only chip-list rows; `studio.css` holds the moved rows;
  - the whole-app totals from Flight 3's close (135 rows / 315 uses / 37 sinks) to now.
- **The line guard:** every allowance entry still at or below its ceiling (`knowledge-folders.js`' entry gone).
- **`scripts/unused_selectors.py`** over `admin.css`, `studio.css` and `components.css`, with each remaining hit justified or removed.
- **The after captures** at `$HOME/.cache/the-one-ui-capture/m31-f4-after/`, the same surfaces as the before set. A compare script lists every differing surface, and each difference maps to a ledger row; the result goes in the flight log.
- **A full `make gate`** (netns, WebKit required) with per-lane times. Re-budget by the 15% and 1.3x rules, and split `settings` if it is over 1.3x. Update `scripts/run-tests.sh` and CLAUDE.md's lane table.
- **Docs:**
  - CLAUDE.md: the Settings paragraphs ("Settings nav and pages", "Settings item pages", "Date and time page", the control library paragraph with the new controls, the "Flight 6 alignment notes" if a rule changed), and the testing section if lanes changed;
  - `the_one/agents.md`: Settings, the control library, errors and late responses, tool config fields;
  - `docs/ui-control-inventory.md`: every new control and option, the owned lists, the declared-not-controls note, the alias counts in the mission's Known Issues;
  - `docs/ui-testid-registry.md`: new testids, and retired ones in the retired table plus `RETIRED_SELECTORS`.
- **The mission's Known Issues** alias counts updated (Settings' `confirmDelete`, `showFlash`, `icon`, `tabs` uses are gone).
- **The behavior specs:** each spec that walks Settings (`jump-to-palette`, `list-and-detail`, `workbench-navigation`, `shell-navigation-smoke`, `start-a-chat`, `windows-window-chrome`, `windows-native-frame-splash`, `agent-governance-and-search`, `stub-connector-round-trip`) is read against the landed UI, and amended where a step's selector or wording changed.

## Acceptance Criteria
1. The counts above hold (pasted from the tests' printed tables).
2. `admin.css` has no rule for a non-Settings surface, and the `studio.css` move matches the removed rows exactly.
3. The unused-selector report is reviewed, and every remaining hit is justified.
4. The after captures are taken, and every difference maps to a ledger row.
5. `make gate` is green, the budgets are re-measured and updated, and any `settings` split is done with its lane test (`tests/test_run_tests_lanes.py`) updated.
6. The docs are updated (each named file has a diff, or a recorded "no change needed").
7. The behavior specs are checked, and amendments made.
8. The line guard passes, and no area module grew past 800 lines.

## Verification Steps
- `.venv/bin/python -m pytest tests/test_ui_guards.py tests/test_ui_ownership.py tests/test_ui_control_inventory.py tests/test_ui_emitted_classes.py tests/test_design_tokens_a11y.py tests/test_token_definitions.py tests/test_area_module_size.py tests/test_run_tests_lanes.py tests/test_nav_helper.py -q -x --timeout 120`.
- `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 TEST_TIMEOUT=3600 make gate`, run alone.
- The capture run and compare.

## Files Affected
- `static/css/admin.css`, `studio.css`, `components.css`; `scripts/run-tests.sh`; the allowance and pin tests.
- CLAUDE.md, `the_one/agents.md`, `docs/ui-control-inventory.md`, `docs/ui-testid-registry.md`, `tests/test_nav_helper.py` (`RETIRED_SELECTORS`), `missions/31-control-library-everywhere/mission.md` (Known Issues), `tests/behavior/*` (as needed), the flight log.

## Citation Audit
- The Flight 3 close totals, 135 / 315 / 37: verified (CLAUDE.md and the FD tally at planning).

## Amendment from leg 04a (2026-10-23)
- **Remove the `!important` in the flush modifiers.** Leg 04a's `editor-header--flush` and `editor-section--flush` use `!important` to beat area rules (`.area-admin .page-header`, `.area-studio .editor-section`) in the later `areas` layer. Once legs 06-10 have deleted the `.area-admin` rules, drop the `!important` wherever no area rule competes any more. Keep it only against a remaining `.area-studio` rule, with a comment naming that rule and Flight 5. A computed-style test proves the flush still applies.

Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
