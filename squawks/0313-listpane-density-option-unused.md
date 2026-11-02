# Squawk 0313: `App.ui.listPane`'s `density: 'compact'` option has no caller

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-02
**Completed**: —

## Report
`App.ui.listPane` documents a `density` option (`regular | compact`) and `components.css` styles `.ui-list-pane-compact`, but no call site passes `density: 'compact'`. Mission 34 Flight 3 kept the CSS because the factory can produce the class (`'ui-list-pane-' + density`). The option is unused library surface. Remove the `compact` value (the option, the CSS rule, the catalogue mention and any contract-test case for it), keeping `regular` as the only rendering, unless a grep finds a planned caller (a leg or flight that names it), in which case record that and close as kept. `App.ui.modelList` has its own `density` and is out of scope.

## Evidence
- `the_one/interfaces/web/static/js/ui/list-pane.js:89` (doc comment, `density (regular | compact)`), `:197` (`var density = opts.density === 'compact' ? 'compact' : 'regular';`), `:211` (`'ui-list-pane ui-list-pane-' + density`).
- `the_one/interfaces/web/static/css/components.css:706` — `.ui-list-pane-compact .ui-list-pane-row { … }`.
- `docs/ui-control-inventory.md` listPane row: "`density`" in its options.
- Mission 34 Flight 3 flight log, Leg 1 (CSS variants kept); debrief Action Items.

## Corrective Action
*(written at completion)*

## Verification
- No `density: 'compact'` caller exists (grep recorded); the option value, the `.ui-list-pane-compact` rule and the catalogue mention are gone, or the squawk records the planned caller and closes as kept.
- `tests/test_ui_ownership.py`, `tests/test_ui_emitted_classes.py`, `tests/test_ui_control_inventory.py`, the static guards and `THE_ONE_REQUIRE_WEBKIT=1 … --lane contracts` pass.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
