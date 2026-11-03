# Squawk 0313: `App.ui.listPane`'s `density: 'compact'` option has no caller

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-02
**Completed**: 2026-11-02

## Report
`App.ui.listPane` documents a `density` option (`regular | compact`) and `components.css` styles `.ui-list-pane-compact`, but no call site passes `density: 'compact'`. Mission 34 Flight 3 kept the CSS because the factory can produce the class (`'ui-list-pane-' + density`). The option is unused library surface. Remove the `compact` value (the option, the CSS rule, the catalogue mention and any contract-test case for it), keeping `regular` as the only rendering, unless a grep finds a planned caller (a leg or flight that names it), in which case record that and close as kept. `App.ui.modelList` has its own `density` and is out of scope.

## Evidence
- `the_one/interfaces/web/static/js/ui/list-pane.js:89` (doc comment, `density (regular | compact)`), `:197` (`var density = opts.density === 'compact' ? 'compact' : 'regular';`), `:211` (`'ui-list-pane ui-list-pane-' + density`).
- `the_one/interfaces/web/static/css/components.css:706` — `.ui-list-pane-compact .ui-list-pane-row { … }`.
- `docs/ui-control-inventory.md` listPane row: "`density`" in its options.
- Mission 34 Flight 3 flight log, Leg 1 (CSS variants kept); debrief Action Items.

## Corrective Action
Removed `density` from `App.ui.listPane`: the doc-comment mention and the `density` variable in `js/ui/list-pane.js`, the `.ui-list-pane-compact` rule (and the comment referring to it) in `static/css/components.css`, and `density` from the listPane catalogue row in `docs/ui-control-inventory.md`. The root class is now plain `ui-list-pane`: the `ui-list-pane-regular` class was styled and pinned nowhere (CSS, tests, catalogue), and keeping it as a literal made `tests/test_ui_emitted_classes.py` flag it as unowned, so it was dropped rather than exempted. Tests: deleted `test_list_pane_row_style_wins_over_compact_density` (`test_ui_library_contract.py`), dropped the compact half of the density test (now `test_list_pane_regular_density_computed`) and the `density` parameter of `_pane`/`MOUNT_PANE_JS` (`test_ui_choice_contract.py`). `App.ui.modelList`'s own `density` is untouched.
After review, the stale `the_one/agents.md` mentions were fixed too: `density` in the `listPane` signature, the "`rowStyle` padding wins over `density: 'compact'`" clause, and the `'ui-list-pane-' + density` example in the `removing-dead-code` convention (now `'ui-menu-align-' + align`).

## Verification
- Callers: `grep -rnE "density|ui-list-pane-(compact|regular)"` over the repo (excluding `.claude`, `.git`, `.venv`, `missions`, `sorties`, `maintenance`, `squawks`) found no `listPane` caller passing `density` (only `provider-models.js:137`, which is `modelList`). A separate grep of `missions/`, `sorties/`, `maintenance/`, `squawks/` found only the Flight 3 leg/debrief notes that prompted this squawk and an M25 leg 06 test-plan row; no planned caller.
- `tests/test_ui_ownership.py`, `test_ui_emitted_classes.py`, `test_ui_control_inventory.py`, `test_ui_guards.py`, `test_token_definitions.py`, `test_design_tokens_a11y.py`: 370 passed.
- `THE_ONE_TEST_NETNS=1 make test-unit`: 8618 passed, 15 skipped.
- `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 ... --lane contracts-overlay`: 548 passed, 1 skipped. `--lane contracts-controls` (holds the `test_ui_list_pane*` choice/library/activity files): 1172 passed, 4 skipped. `contracts-chat` holds no listPane file and was not run.
- Superseded original criteria below, kept for reference:
- No `density: 'compact'` caller exists (grep recorded); the option value, the `.ui-list-pane-compact` rule and the catalogue mention are gone, or the squawk records the planned caller and closes as kept.
- `tests/test_ui_ownership.py`, `tests/test_ui_emitted_classes.py`, `tests/test_ui_control_inventory.py`, the static guards and `THE_ONE_REQUIRE_WEBKIT=1 … --lane contracts` pass.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches `tests/test_encryption.py` key-path guards and logging setup), batch review of the 2026-11-02 squawk turnaround, scoped to the diff, `[HANDOFF:confirmed]` with no blocking issues; the Reviewer's own `THE_ONE_TEST_NETNS=1 make test-unit`: 8618 passed, 15 skipped; `ruff check`/`format --check` clean. Fix pass after review: the stale listPane `density` mentions in `the_one/agents.md` (signature, rowStyle note, and the `removing-dead-code` example) were corrected, then re-reviewed by a Haiku Reviewer (docs-only), `[HANDOFF:confirmed]`. The root class change (`ui-list-pane ui-list-pane-regular` to `ui-list-pane`) is deliberate: nothing styled or pinned the class.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02` commit on `squawk/turnaround-2026-11-02`.
