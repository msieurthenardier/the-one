# Leg: control-row-moves

**Status**: completed
**Flight**: [MCP arguments as rows](../flight.md)

## Objective
Give `App.ui.keyValueTable` row moves, a full-width layout, a visually hidden column header and a `focus()` method, and give `App.ui.field` a group mode, each inert unless asked for and each pinned by contract tests in Chromium and WebKit.

## Context
- Flight decisions this leg implements: DD2 (field group mode), DD3 (row moves), DD4 (hidden header), DD10 (`fill`, `focus()`). Read them in `../flight.md` first; this leg adds mechanics, not decisions.
- No consumer changes in this leg. The MCP editor starts using the options in leg 2 (`arguments-rows`). The four existing consumers of the table (`connector-editor.js`, `mcp-env-headers.js`, `mcp-agent-credentials.js`, `secret-editor.js`) pass none of the new options and must behave exactly as before.
- The Architect's review (flight log, 2026-11-17) set the mechanics below: move the neighbour's row so the pressed row never leaves the document, call `focus()` explicitly, guard clicks on disabled buttons, recompute edge state in `renumber()`, build the hidden header from per-cell spans.
- First leg of the flight: there are no prior-leg outcomes to carry.

## Inputs
- Branch `sortie/18-mcp-arguments-as-rows`, cut from `main` at `f635e039`.
- `the_one/interfaces/web/static/js/ui/key-value-table.js`, `ui/field.js`, `css/components.css`, `js/icons.js` (`chevron-up`, `chevron-down` exist).
- Contract files `tests/browser/test_ui_key_value_table_contract.py` (table) and `tests/browser/test_ui_library_contract.py` (field), both in the `contracts-controls` lane.
- Catalogue `docs/ui-control-inventory.md` (rows "Key-value table" and the field row).

## Outputs
- The two controls with the new options, their header-comment contracts updated.
- New CSS for the owned classes `ui-kv-move`, `ui-kv-live`, `ui-kv-table--head-hidden`, `field-group-caption`.
- New contract tests; the existing ones pass unmodified.
- The two catalogue rows updated (options, owned classes).

## Acceptance Criteria

**Table: row moves (`movable: true`)**
- [x] AC1. Each row's actions cell holds, in this order, a Move up button, a Move down button and the Remove button. The move buttons are icon-only ghost `App.ui.button`s with class `ui-kv-move` and icons `chevron-up` and `chevron-down`; `moveUpTestid` and `moveDownTestid`, when given, are their testids.
- [x] AC2. Their accessible names are "Move row {n} up" and "Move row {n} down" by default, or the return value of `moveLabel(n, row, direction)` (`direction` is `'up'` or `'down'`, `row` a copy of the row's data). Names are correct after add, remove, `setValues`, `setRow` and a move, and are refreshed when the key column is typed in (as the remove name is), so a `moveLabel` that reads the row never goes stale.
- [x] AC3. The first row's Move up and the last row's Move down are natively `disabled` and keep their names; with one row both are disabled. This holds after add, remove, `setValues` and a move.
- [x] AC4. A move up or down changes `values()` to the new order and fires `onChange` exactly once with `{type: 'move'}`. The moved row's `<input>` is the same DOM node as before, keeps its value, and an error set with `setError` before the move is still shown on that row after it; `setError(i, …)` after the move addresses rows in the new order.
- [x] AC5. A click on a disabled move button, or on the icon inside it, changes nothing and fires no `onChange`, in both engines.
- [x] AC6. After a move by mouse click or by keyboard (Enter or Space on the focused button), `document.activeElement` is the pressed button; when that button has become disabled, it is the same row's other move button. Holds in WebKit.
- [x] AC7. With `movable` (and not `readOnly`), the control's root holds one visually hidden `role="status"` node with class `ui-kv-live`, after the Add row button. After a move its text is "Moved to row {n} of {total}." Two moves in a row that produce the same text each write it again (the node is emptied, then written a tick later). Without `movable` there is no such node. After `destroy()`, a pending announcement writes nothing.
- [x] AC8. `readOnly` with `movable` builds no move buttons and no status node. `movable` together with `lockBy`, `removableBy` or `markerBy` throws at construction with a message that names the option, whether or not `readOnly` is also set.

**Table: layout and header**
- [x] AC9. `fill: true` on a table with no secret or toggle column gives it the fixed layout (`ui-kv-table--fixed`, a `colgroup`): the table is as wide as the control's root, and a text input fills its column. On a table that is already fixed, `fill` changes nothing. An empty `fill` table (its `thead` hidden) keeps its width and its Add row button.
- [x] AC10. In a fixed-layout table with `movable`, the actions column holds the three buttons on one line with no overflow and no wrap (measured in both engines). Without `movable` the actions `col` is still 48px.
- [x] AC11. `headHidden: true`: every column label (a string or a Node) sits inside a `span.visually-hidden` in its `th`, the table has class `ui-kv-table--head-hidden`, and with rows present the head row takes no visible height: the `thead` measures at most 1px and the first body row's top is within 1px of the table's top. The `th[scope="col"]` cells are all still there with their text. `emptyHidesHead` still hides the `thead` of an empty table.

**Table: `focus()` and inertness**
- [x] AC12. The controller has `focus()`: it focuses the first row's first input, or the Add row button when there are no rows; on a `readOnly` table with no rows it does nothing and does not throw.
- [x] AC13. A table built with none of `movable`, `fill`, `headHidden` has no `.ui-kv-move`, no `.ui-kv-live` and no `ui-kv-table--head-hidden`, and every existing test in `tests/browser/test_ui_key_value_table_contract.py` passes without modification.

**Field: group mode**
- [x] AC14. `App.ui.field({label, group: <element>})` returns the usual controller. The wrapper is `div.field-group` with `role="group"` and `aria-labelledby` equal to the id of a `div.field-group-caption` whose text is the label. The wrapper's children, in order: the caption, the hint (when there is one), the group element, the error line (when there is one).
- [x] AC15. The hint id and the error id are tokens of the wrapper's `aria-describedby`, hint first; each is removed when its element is. `setError(msg)` shows the error line and `setError(null)` removes it; neither the wrapper nor the group element ever gets `aria-invalid` or the `is-invalid` class. `setHint` and `setLabel` work (the caption text changes). `hintTestid`, `errorTestid` and `testid` behave as in normal mode.
- [x] AC16. `controller.control` is the element passed as `group`.
- [x] AC17. These throw: `group` that is not an element; `control` and `group` together; `group` with `info`; `group` with `labelHidden`. Normal mode is unchanged: `control` is still required when `group` is absent, and every existing field test passes without modification.
- [x] AC18. The caption's computed font size, weight and colour equal those of a normal field's `label` rendered beside it, in the light and the dark theme.

**Styles, catalogue, gates**
- [x] AC19. A disabled move button uses the opaque `--btn-disabled-fg` and `cursor: not-allowed`, never `opacity`. An enabled one looks like the table's remove button at rest and takes `--fg` on hover (it is not a destructive action, so no danger colour).
- [x] AC20. `docs/ui-control-inventory.md`: the Key-value table row lists `movable`, `moveUpTestid`, `moveDownTestid`, `moveLabel`, `fill`, `headHidden`, the `focus()` method, the `'move'` change type and the owned classes `ui-kv-move`, `ui-kv-live`, `ui-kv-table--head-hidden`; the field row lists group mode and `field-group-caption`. The header comments of `key-value-table.js` and `field.js` state the same contracts.
- [x] AC21. Green: `tests/test_ui_control_inventory.py`, `tests/test_ui_ownership.py`, `tests/test_ui_emitted_classes.py`, `tests/test_ui_guards.py`, `tests/test_token_definitions.py`, `tests/test_design_tokens_a11y.py`; all contract lanes with WebKit required; and the lanes of the table's existing consumers: `mcp`, `library`, `agent-tabs`.

## Verification Steps
- AC1 to AC13: new tests in `tests/browser/test_ui_key_value_table_contract.py`, engine-parametrized through `engine_page` and `load_harness`, no fixed sleeps. AC13's second half is the unmodified existing tests passing.
- AC14 to AC18: new tests in `tests/browser/test_ui_library_contract.py`, beside the existing field tests.
- AC5's test must reach the guard: Playwright's `locator.click()` waits for a disabled button to become enabled and times out, so dispatch a bubbling `click` MouseEvent on the `svg` inside the disabled button from `page.evaluate` (or use `click(force=True)`), then assert `values()` and the change log are unchanged.
- AC6's mouse test clicks the enabled button with `locator.click()`; its keyboard test focuses the button, then presses Enter, and separately Space. Cover both cases in both engines: the pressed button stays enabled (focus stays on it), and the pressed button becomes disabled (focus goes to the row's other move button).
- AC7's test installs a `MutationObserver` on the status node that logs its `textContent` after every mutation. With rows A, B, C: move A down ("Moved to row 2 of 3."), wait on the log's length, then move C up (the same text), wait again, and assert the log holds an empty string between the two identical texts. No fixed sleeps.
- AC19: a contract test reads the computed `color`, `opacity` and `cursor` of a disabled and an enabled move button in both themes.
- AC20: read the two catalogue rows and the two header comments.
- AC21, in this order (browser runs need `THE_ONE_TEST_NETNS=1` on this host):
  - `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_ui_control_inventory.py tests/test_ui_ownership.py tests/test_ui_emitted_classes.py tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py -x --timeout 60`
  - `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane contracts -x --timeout 60`
  - `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane mcp -x --timeout 60`, then `--lane library`, then `--lane agent-tabs` (one at a time, never with another test run on the host).
- Falsification: for the tests of AC5 (the disabled-click guard), AC6 (focus after a move) and AC3 (edge state after a move), show each fails with its mechanism edited out and passes with it back, and report yes or no for each, naming the engine. Chromium focuses a clicked button and may not deliver a click on a disabled button's child, so the AC5 test and the stays-enabled case of AC6 are expected to fail without their mechanism in WebKit only; the became-disabled case of AC6 must fail in both.

## Implementation Guidance

1. **Options and validation (`key-value-table.js`, top of the factory).**
   - Read `movable`, `fill`, `headHidden` as strict booleans (`=== true`), beside `readOnly`.
   - Throw when `movable` is set with `lockBy`, `removableBy` or `markerBy`.
   - `fixed` becomes true when `opts.fill === true` as well as for a secret or toggle column.

2. **Actions column width.** In the existing `colgroup` branch, the actions `col` stays `48px` unless `movable` is set; then size it for three buttons. Derive the number from the button box in the CSS (`.ui-kv .ui-kv-remove` is a 16px icon with 4px padding, so 24px a button) plus the two gaps and the cell's 8px side padding; AC10's measurement is the check, not a guessed constant. `.ui-kv-center` is a flex row with no gap today: give the actions cell's row a gap and `flex-wrap: nowrap`.

3. **Hidden header.** Where the head cells are built: when `headHidden`, put the label (text or Node) inside a `span.visually-hidden` in the `th`, as the actions cell already does, and add `ui-kv-table--head-hidden` to the table. Keep `labelText` (the input names use it). Do not hide the `thead` or its row with a class: `syncHead()` keeps owning `thead.hidden`.

4. **Move buttons in `newRow`.** When `movable` and not `readOnly`, build `row.up` and `row.down` with `App.ui.button({variant: 'ghost', iconOnly: true, icon: …, ariaLabel: …, className: 'ui-kv-move', testid: …})` and put them before `row.remove` inside the existing `div.ui-kv-center` of the actions cell. Mark the direction on each button with a data attribute so the click handler can read it.

5. **`renumber()` owns names and edge state.** After the remove name, set each move button's `aria-label` (through `moveLabel` when given, with a copy of the row data) and its `disabled` (`up` on index 0, `down` on the last index). `renumber()` already runs after add, remove, `setValues`, `setRow` and the toggle handler; call it after a move too. Do not put this in `applyRowState`, which returns early when no lock option is set.

6. **The move.** In `onClick`, after the add branch and beside the remove branch: `closest('.ui-kv-move')`; return when it is `disabled` (WebKit can deliver a click on a disabled button's child); find the row with `rowOfNode`; move it.
   - Swap the two entries of `rows`.
   - Move the neighbour's `tr`, not the pressed row's: for a move up, insert the neighbour after the pressed row; for a move down, insert the neighbour before it. The pressed row's nodes then never leave the document.
   - `renumber()`.
   - Focus explicitly: the pressed button, or the row's other move button when the pressed one is now disabled.
   - Write the status text (step 7).
   - `fire('move')`.

7. **Status node.** Only with `movable` (and not `readOnly`): a `div` with classes `ui-kv-live visually-hidden` and `role="status"`, appended to the root after the Add button. `setValues` leaves a pending announcement alone (it describes a move that happened). To announce: empty it, then write the text in a zero-delay timeout; keep the timer handle, cancel a pending one before starting the next, and cancel it in `destroy`.

8. **`focus()`.** Add it to the returned object: first row's first input through `focusInput`; else, when not `readOnly`, the Add button; else nothing. Guard on `readOnly`, not on the button: `addBtn` exists as an unattached node in a `readOnly` table.

9. **Field group mode (`field.js`).** Branch at the top of `App.ui.field` on `opts.group`:
   - Validate (AC17) before anything is built. In group mode skip the two control-only steps: the "checkbox/toggle carry their own label" check (a table may hold toggle columns) and the generated-id assignment (nothing points a `for` at the group element).
   - Build the caption (`div.field-group-caption`, generated id), the wrapper (`div.field-group`, `role="group"`, `aria-labelledby`), and place the group element.
   - Keep one code path for what the two modes share by introducing two targets: a describedby target (the wrapper in group mode, the control otherwise) and an invalid target (none in group mode, the control otherwise). The existing `wire()` stays the single writer of `aria-describedby`: it reads the foreign tokens from the describedby target and removes the attribute when there are no ids, which gives the "no attribute at all" edge case for free. `setError` writes `is-invalid` and `aria-invalid` only when there is an invalid target.
   - Insertion points need an explicit branch. Today `setHint` inserts the hint before the error element, which with no error appends it after everything. In group mode the hint goes directly after the caption and the error is appended after the group element.

10. **CSS (`components.css`).**
    - Add `.field-group > .field-group-caption` to the selector list of the existing label rule so the two cannot drift.
    - `.ui-kv .ui-kv-move`: the same box as `.ui-kv .ui-kv-remove`, by joining its selector lists: the box rule with its `:hover` twin (`width: auto; height: auto; background: transparent; border: 0; padding: 4px; line-height: 0`) and the 16px `svg` rule further down, or the buttons render at the default icon-button size; resting colour `--fg-secondary`, hover `--fg`; `:disabled` and `:disabled:hover` with `--btn-disabled-fg` and `cursor: not-allowed`, placed so they win on specificity (see the existing comment above the remove button's disabled rule). A small gap between the three buttons.
    - `.ui-kv-table--head-hidden .ui-kv-head th`: zero padding and border, and `height: 0` with `line-height: 0`. The table uses `border-collapse: collapse`, so check the head's bottom border does not survive as the first body row's top edge (AC11 measures it).
    - Tokens only; no new colour values.

11. **Catalogue and comments.** Update the two rows of `docs/ui-control-inventory.md` and the two header comments. Grep `tests/`, `scripts/`, `docs/` and `tests/behavior/` for pins of the changed shapes (the controller's key list, the owned-class lists) and update them in this leg.

## Edge Cases
- **One row**: both move buttons disabled; no focus target problem because no move can happen.
- **Move the first row down / the last row up**: the pressed button stays enabled, focus stays on it.
- **Move the second row up / the second-to-last row down**: the pressed button becomes disabled; focus goes to the row's other move button.
- **Move while an input of that row has focus**: focus goes to the pressed button, as for any click.
- **`setValues` after moves**: rows are rebuilt; names and edge state come from `renumber()`.
- **`destroy` with a pending announcement**: the timer is cancelled; nothing writes to a destroyed control.
- **`headHidden` with a Node label**: the Node goes inside the span; the input names still use its text.
- **`fill` with a column `width`**: the width now applies (the table is fixed); `fill` without widths shares the space evenly.
- **`headHidden` on an empty table**: the `thead` is `hidden` by `emptyHidesHead`, as today.
- **Group mode with no hint and no error**: the wrapper has no `aria-describedby` attribute at all.
- **Group element holding a toggle column**: group mode does not throw the own-label error.
- **`readOnly` with `movable` and a lock option**: still throws (AC8).

## Files Affected
- `the_one/interfaces/web/static/js/ui/key-value-table.js` - the options, move buttons, the move, the status node, `focus()`, the header comment
- `the_one/interfaces/web/static/js/ui/field.js` - group mode, the header comment
- `the_one/interfaces/web/static/css/components.css` - the four new owned classes
- `tests/browser/test_ui_key_value_table_contract.py` - new contract tests
- `tests/browser/test_ui_library_contract.py` - new field group-mode tests
- `docs/ui-control-inventory.md` - the two catalogue rows
- `sorties/18-mcp-arguments-as-rows/flight-log.md` - the leg's progress entry

## Citation Audit

Checked against the working tree at `f635e039`.

- `the_one/interfaces/web/static/js/ui/key-value-table.js` (constructor) - `fixed` is set only for a `secret` or `toggle` column; the `colgroup` is built only when `fixed`, and its actions `col` is `48px` unless `readOnly` - verified
- `key-value-table.js` (head) - each column gets a `th[scope="col"]`; `labelText` collects the label text; the actions `th` holds a `span.visually-hidden` "Actions" - verified
- `key-value-table.js::newRow` - the remove button is `App.ui.button({variant: 'ghost', iconOnly: true, icon: 'trash', className: 'ui-kv-remove'})` inside `div.ui-kv-center` in a `td.ui-kv-cell`, built only when not `readOnly` - verified
- `key-value-table.js::renumber` - sets `data-row-idx`, the cell names and the remove name for every row - verified
- `key-value-table.js::applyRowState` - returns at once unless `readOnly`, `lockBy`, `markerBy` or `removableBy` is set - verified
- `key-value-table.js::onClick` - one delegated listener on the root; the remove branch uses `closest('.ui-kv-remove')`, returns when the button is `disabled`, then `removeByKey(owner.key)` - verified
- `key-value-table.js::removeByKey` / `::setValues` - both call `renumber()` and `syncHead()`; `syncHead` sets `thead.hidden` from `emptyHidesHead` and the row count - verified
- `key-value-table.js` (return) - `{el, values, setValues, setRow, setError, focusRow, destroy}`; `destroy` removes the three listeners - verified
- `the_one/interfaces/web/static/js/ui/field.js::App.ui.field` - throws without a `control` element; builds `label` with `htmlFor`; and for a control holding `[data-ui-own-label="true"]`; assigns the control an id when it has none; wrapper `div.field-group`; `setHint` builds `div.field-hint` with a generated id and inserts it before the error element; `wire()` rewrites the control's whole `aria-describedby` from the foreign tokens plus the hint and error ids; `setError` adds `is-invalid` and `aria-invalid` to the control - verified (the insertion point and `wire()` by the leg's design reviewer, 2026-11-17)
- `the_one/interfaces/web/static/css/components.css` - `.field-group > label` sets `--font-size-body-sm`, medium weight, `--fg-secondary`; `.ui-kv-center` is a flex row; `.ui-kv .ui-kv-remove` has 4px padding, no border; its `:disabled` rule uses `--btn-disabled-fg` - verified
- `the_one/interfaces/web/static/js/icons.js` - `chevron-up`, `chevron-down` - verified
- `tests/browser/test_ui_key_value_table_contract.py` - mounts through `load_harness` and `engine_page`; `tests/browser/test_ui_library_contract.py` - holds the field tests (`test_field_wiring_label_hint_error_order` and others) - verified

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
