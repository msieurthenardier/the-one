# Leg: arguments-rows

**Status**: completed
**Flight**: [MCP arguments as rows](../flight.md)

## Objective
Replace the Arguments chip list of the Library MCP server editor with a one-column row table (Add row, Move up, Move down, Remove) built on the controls leg 1 delivered, with a value model that keeps order and repeats and never splits a value.

## Context
- Flight decisions this leg implements: DD1 (the block), DD5 (one row is one argument, ends trimmed, blanks dropped), DD6 (the dirty check compares the collected list), DD7 (stored shape untouched; its limit), DD8 (DOM contract and testids), DD9 (tests). The approved mockup in `../flight.md` is the look: no column header, the hint between the caption and the rows, full-width inputs, three icon buttons per row.
- Leg 1 landed (flight log, `### control-row-moves`). What it delivered, as built:
  - `App.ui.keyValueTable`: `movable`, `moveUpTestid`, `moveDownTestid`, `moveLabel(n, row, 'up'|'down')`, `fill`, `headHidden`, the method `focus()` (first row's first input, else Add row), the change type `'move'`. Existing options this leg also uses: `columns[].inputTestid`, `columns[].mono`, `rowTestid`, `removeTestid`, `removeLabel(n, row)`, `addTestid`, `testid`, `onChange`.
  - `App.ui.field({label, group, hint, hintTestid, errorTestid, testid})`: the wrapper is `div.field-group[role="group"]` named by a `div.field-group-caption`; children in order caption, hint, group element, error; `setError` shows the error line only.
  - `movable` cannot be combined with `lockBy`, `removableBy` or `markerBy` (it throws). This leg uses none of them.
- This leg changes one area module and its tests. It must not change `js/ui/*`: if the controls turn out to lack something, stop and report it (see the last paragraph of the Developer brief), do not patch the library here.

## Inputs
- Branch `sortie/18-mcp-arguments-as-rows` with leg 1's uncommitted changes in the tree (`js/ui/key-value-table.js`, `js/ui/field.js`, `css/components.css`, the two contract files, the catalogue).
- `the_one/interfaces/web/static/js/areas/studio/mcp-connection-fields.js` (the Arguments chip list), `mcp-server-editor.js` (collect, dirty check, Cancel, Save, field errors), `mcp-editor-shared.js` (`deriveStdioRuntimeSelection`, `uniqueStrings`).
- Tests that pin the chips: `tests/browser/test_flow_studio_mcp_editor_fields.py`, `tests/browser/test_flow_studio_mcp_editor_kv_chips.py`, `tests/browser/test_flow_chiplist_label_resolver.py`; tests that must stay green: `tests/browser/test_flow_studio_mcp_editor_controller.py`.

## Outputs
- The Arguments block as a table in a group-mode field; the module's value model per DD5 and DD6.
- Rewritten and new flow tests; a row helper in `tests/browser/_mcp_editor.py`.
- Docs: `docs/ui-testid-registry.md`, the chip list's header comment and catalogue row, `tests/_ui_guard_helpers.py`'s comment, `the_one/agents.md`.

## Acceptance Criteria

**The block**
- [x] AC1. For a local-command server the Connection section shows, after Working directory, a block `[data-testid="mcp-args-field"]` carrying `data-field="args"`, with `role="group"` and the accessible name "Arguments". Inside it, in order: the caption "Arguments", the hint `[data-testid="mcp-args-hint"]` reading "One argument per row, in order.", the table `[data-testid="mcp-args-table"]`, and the button `[data-testid="mcp-args-add-row-btn"]` labelled "+ Add row".
- [x] AC2. The table has one row (`mcp-args-row`) per stored display argument, in stored order. Each row has a monospace text input (`mcp-args-input`) named "Argument, row {n}", then buttons named "Move argument {n} up" (`mcp-args-move-up`), "Move argument {n} down" (`mcp-args-move-down`) and "Remove argument {n}" (`mcp-args-remove`). No column header is visible. The inputs fill the block: an argument input is at least 70% as wide as the Working directory input above it.
- [x] AC3. The block is hidden for an HTTP server and shown for a local-command one, and follows the Type select in create mode; rows typed before a switch to HTTP and back are still there.
- [x] AC4. A server stored as `command: "npx", args: ["-y", "pkg", "--flag"]` shows Command "npx -y" and two rows (`pkg`, `--flag`); one stored as `command: "pipx", args: ["run", "pkg"]` shows "pipx run" and one row. A server with no arguments, and the create form, show no rows.
- [x] AC5. Inside `[data-field="args"]` there is no `.chip-list-editor`, and no element has the id `mf-args`. The writable-paths chip list is unchanged.

**Saving**
- [x] AC6. Save stores `config.args` as the implicit runtime argument (when the Command needs one) followed by the rows in order, each with leading and trailing whitespace trimmed and rows that are then empty left out. Repeats are kept: rows `--flag`, `a`, `--flag`, `a` store four arguments. A row `--allow=a,b` and a row `/home/me/My Documents` are each stored as one argument, unchanged. After a reload the rows equal what was stored.
- [x] AC7. With no rows, or only blank rows, Save stores no `args` key (as today for an empty list).
- [x] AC8. After a successful Save the form is clean and the rows show the stored display arguments: blank rows are gone and trimmed values are shown trimmed.

**Unsaved changes, Cancel, Test**
- [x] AC9. "Unsaved changes" (`editor-unsaved`) does not appear when a blank row is added, when a row is added and removed again, or when a value is typed and then restored. It appears when a value changes, a non-blank row is added or removed, or a row is moved, and disappears when the move is undone.
- [x] AC10. A server stored with a repeat (`["a", "a", "b"]`) opens clean with three rows. `tests/browser/test_flow_studio_mcp_editor_controller.py`'s baseline-parity and clean-mount tests pass with their seeds unchanged.
- [x] AC11. Cancel in edit mode puts back the saved rows in the saved order, in place (the editor is not remounted), and the form is clean.
- [x] AC12. Test with unsaved rows sends them: the `/test/connect` request body's `config.args` is the implicit argument plus the collected rows, and the result note reads "Tested with your unsaved changes."
- [x] AC13. A Save refused with a field error for `args` shows the message on the block's error line and moves focus into the table (the first row's input, or Add row when there are no rows). Editing, adding, removing or moving a row clears the message.

**Tests and docs**
- [x] AC14. No browser test or helper reaches the Arguments field through `.chip-list-editor`, `.chip` or `label[for="mf-args"]`. The tests that did are rewritten against the rows (not deleted): in `test_flow_studio_mcp_editor_fields.py`, in `test_flow_studio_mcp_editor_kv_chips.py` (`_add_chip(page, "args", …)` becomes a row helper; `test_chip_edit_after_cancel_is_tracked_as_dirty` keeps its writable-paths case and gets a rows counterpart), and in `test_flow_chiplist_label_resolver.py` (its `mf-args` half goes; the writable-paths half stays). A helper for adding and reading argument rows lives in `tests/browser/_mcp_editor.py`.
- [x] AC15. New flow tests cover AC2 to AC13 in `test_flow_studio_mcp_editor_fields.py` or `test_flow_studio_mcp_editor_kv_chips.py` (both are in the `mcp` lane; a new file would need a lane entry in `scripts/run-tests.sh`, so do not add one).
- [x] AC16. Docs: `docs/ui-testid-registry.md` lists the nine new testids (and does not add `mf-args` to its "Retired testids" table: it is an id, not a testid); the chip list's header comment and its catalogue row no longer name the MCP editor's arguments as a user; the comment in `tests/_ui_guard_helpers.py` that names `mf-args` is corrected; `the_one/agents.md` describes the Arguments block and its value rule in its MCP editor notes and records leg 1's control options in its "Control library (`App.ui`)" history; `mcp-connection-fields.js`'s header comment describes the new field and `values().args`.
- [x] AC17. Green: the six static guard files of leg 1's AC21; `THE_ONE_TEST_NETNS=1 make test-unit`; the lanes `mcp`, `mcp-connection` and `shared`. `js/ui/*` is not modified by this leg.
- [x] AC18. `scripts/ui_capture.py`'s `mcp-edit-stdio` surface is captured in light and dark to a directory outside the repo and looked at: the rows are full width, there is no header row, the hint sits between the caption and the rows, and the three buttons sit on one line. What was seen is reported (the PNGs are not committed).

## Verification Steps
- AC1 to AC13: Playwright flow tests in the `mcp` lane. Stored values are read through the authenticated `GET /api/mcp-sources/{id}` helper the files already use (`config.args`). AC12 captures the `/test/connect` request the way the existing unsaved-changes Test tests do. AC13: find how an existing test produces a field error for another connection field (for example a refused URL or name) and mirror it for `args`; if no server response can name `args`, stub the Save response with a 422 whose `loc` is the one `App.api.fieldErrors` maps to `args` for `SERVER_FIELDS`, and say so in the report.
- AC14: `grep -rn 'mf-args' tests/ scripts/ docs/ tests/behavior/` and a grep for `data-field="args"` beside `chip` return nothing but intended hits.
- AC17, in this order (browser runs need `THE_ONE_TEST_NETNS=1`; one run at a time, never with another test run on the host):
  - `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_ui_control_inventory.py tests/test_ui_ownership.py tests/test_ui_emitted_classes.py tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py tests/test_nav_helper.py tests/test_run_tests_lanes.py -x --timeout 60`
  - `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane mcp -x --timeout 60`, then `--lane mcp-connection`, then `--lane shared`
  - `THE_ONE_TEST_NETNS=1 make test-unit`
- AC18: `python scripts/ui_capture.py --list` to confirm the surface name, then capture it with `--out` pointing outside the repo (the tool refuses a path inside it and starts its own scratch instance on port 8490 or higher).
- Falsification: show that the repeats test (AC6) fails when the collect rule removes repeats, and that the blank-row test (AC9) fails when blank rows are kept in `values().args`; report yes or no for each.

## Implementation Guidance

1. **Read first.** `mcp-connection-fields.js` in full, the `args` paths of `mcp-server-editor.js` (collect, `valuesSnapshot`, `baselineSnapshot`, `applySaved`, `performCancel`, the Save's `fieldErrors` mapping and `connection.focus(firstBad)`, the Test body), and `mcp-env-headers.js` as the neighbouring consumer of the table.

2. **One collect function.** In `mcp-connection-fields.js`, a module-level function that takes a list, maps each entry to a string, trims it and drops the empty ones, keeping order and repeats. `values().args` is that function over the table's row values; `baselineFrom(source)` is the same function over `deriveStdioRuntimeSelection(...).displayArgs`. Remove the `shared.uniqueStrings` call from `baselineFrom` only; `uniqueStrings` itself stays (the writable-paths field uses it).

3. **The table.** Replace `argsChips` with `ui.keyValueTable({columns: [{key: 'value', label: 'Argument', mono: true, inputTestid: 'mcp-args-input'}], movable: true, fill: true, headHidden: true, testid: 'mcp-args-table', rowTestid: 'mcp-args-row', removeTestid: 'mcp-args-remove', moveUpTestid: 'mcp-args-move-up', moveDownTestid: 'mcp-args-move-down', addTestid: 'mcp-args-add-row-btn', removeLabel: …, moveLabel: …, onChange: function () { changed('args'); }})`. The two label functions use the position only ("Remove argument {n}", "Move argument {n} up"). Do not pass the table's `label` option: the group names it.

4. **The field.** `ui.field({label: 'Arguments', group: table.el, hint: 'One argument per row, in order.', hintTestid: 'mcp-args-hint', testid: 'mcp-args-field'})`. Set `data-field="args"` on the field's wrapper and keep the `mcp-stdio-only` marker class on it. `data-field-type="array"` is not carried over; grep the tests and `js/` for a reader of it on this field first, and report what you find.

5. **The module's other paths.**
   - `setValues(source)`: `table.setValues` with one `{value}` row per stored display argument, as stored (not collected), so a stored value is shown as it is (DD7's limit). It must not fire `onChange` (the table's `setValues` does not).
   - `focus('args')`: `table.focus()` when the block is not hidden.
   - `setError('args', msg)` and `clearErrors()` keep working through the field's `setError`; `changed('args')` already clears the message on any table change.
   - `setType`: the block hides and shows as the chip field did.
   - `destroy`: `table.destroy()`.
   - Update the module's header comment (the field list, `values()`, `baselineFrom`, and the sentence that says `onChange` fires for "every chip change, a Cancel's re-set chips included": a Cancel no longer fires it for arguments, and the controller already recomputes dirty after `applySaved`).

6. **The controller.** `mcp-server-editor.js` should need no change: it concatenates `fv.args` after the implicit argument and compares JSON snapshots of `values()`. Confirm by reading; change it only if a test proves a path broken, and record why in the flight log.

7. **Tests.** Add the row helper to `tests/browser/_mcp_editor.py` first (add a row and type into it; read the rows' values; click a row's move or remove button by position). Rewrite the pinned tests on it, then add the new ones. Keep test names that still describe the behaviour; rename the ones that say "chip" for arguments.

8. **Docs and comments** per AC16. Grep `tests/`, `scripts/`, `docs/` and `tests/behavior/` for `mf-args`, `data-field="args"` and "chip" beside "arg" before finishing.

## Edge Cases
- **A stored argument with outer whitespace or an empty string** (only through the API): shown as stored; the form is clean; the next Save trims or drops it (DD7's limit). One test pins the clean mount.
- **Only blank rows**: clean form; Save stores no `args`.
- **Save while a blank row has focus**: after the Save the rows are re-set from the stored value; focus must not be lost to the page body (the table moves it to the first input or Add row; the editor's own focus-after rule may then move it to the title, which is the existing behaviour for a Save).
- **Type switched to HTTP with rows present**: the rows stay in the hidden block and are not sent for an HTTP server.
- **Command changed between `npx -y`, `pipx run` and a plain runtime**: the rows do not change; only the implicit argument at Save does.
- **A very long argument** (the capture surface seeds one of about 90 characters): the input scrolls its text; the row does not grow wider than the block.
- **Cancel with a move pending**: the saved order returns.

## Files Affected
- `the_one/interfaces/web/static/js/areas/studio/mcp-connection-fields.js` - the Arguments block, the collect rule, the header comment
- `the_one/interfaces/web/static/js/ui/chip-list.js` - header comment only (the list of users)
- `tests/browser/_mcp_editor.py` - the row helper
- `tests/browser/test_flow_studio_mcp_editor_fields.py`, `tests/browser/test_flow_studio_mcp_editor_kv_chips.py`, `tests/browser/test_flow_chiplist_label_resolver.py` - rewritten and new tests
- `tests/_ui_guard_helpers.py` - a comment
- `docs/ui-testid-registry.md`, `docs/ui-control-inventory.md` (the chip list row's users), `the_one/agents.md` - docs
- `sorties/18-mcp-arguments-as-rows/flight-log.md` - the leg's progress entry

## Citation Audit

Checked against the working tree on `sortie/18-mcp-arguments-as-rows` after leg 1 landed (base `f635e039` plus leg 1's uncommitted changes).

- `the_one/interfaces/web/static/js/areas/studio/mcp-connection-fields.js::create` - `argsChips = ui.chipList({inputId: 'mf-args', dataset: {field: 'args', fieldType: 'array'}, onChange → changed('args')})`; `argsField = ui.field({label: 'Arguments', control: argsChips.input, host: argsChips.el})` with class `mcp-stdio-only`; `byName.args = argsField` - verified
- `mcp-connection-fields.js::changed` - clears the named field's error, then calls `opts.onChange` - verified
- `mcp-connection-fields.js::setValues` / `::values` / `::baselineFrom` - `argsChips.setValues(sel.displayArgs || [])`; `values()` passes `argsChips.values()` to `shape`; `baselineFrom` passes `shared.uniqueStrings(sel.displayArgs || [])` - verified
- `mcp-connection-fields.js` (return) - `focus(field)` uses `argsChips.input` for the args field and skips a hidden field; `destroy` calls `argsChips.destroy()`; `setType` sets `argsField.el.hidden = !stdio` - verified
- `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js` - `argsList = prependArgs.concat(fv.args)` and `config.args` only when non-empty; `valuesSnapshot()` is the JSON of `connection.values()` and `sandbox.values()`; `performCancel` calls `applySaved(current)` then re-baselines; after a Save, `applySaved(updated)` runs when the values are unchanged since the click; field errors come from `App.api.fieldErrors(err, SERVER_FIELDS)` with `'args'` among `SERVER_FIELDS`, then `connection.focus(firstBad)` - verified
- `the_one/interfaces/web/static/js/ui/key-value-table.js` (as built by leg 1) - the header comment documents `movable`, `moveUpTestid`, `moveDownTestid`, `moveLabel(n, rowCopy, 'up'|'down')`, `fill`, `headHidden`, `focus()`; `movable` with `lockBy`, `removableBy` or `markerBy` throws; `setValues` fires no `onChange` and, when focus was inside the table, moves it to the first input or the Add button - verified
- `the_one/interfaces/web/static/js/ui/field.js` (as built by leg 1) - group mode documented in the header comment: `group` in place of `control`, caption, hint, group, error order - verified
- `tests/browser/test_flow_studio_mcp_editor_kv_chips.py::_add_chip` - fills `[data-field="{field}"].chip-list-editor .chip-list-input` and presses Enter; called with `"args"`; `test_chip_edit_after_cancel_is_tracked_as_dirty` is parametrized over `"args"` and `"sandbox-writable-paths"` - verified
- `tests/browser/test_flow_chiplist_label_resolver.py` - asserts `label[for="mf-args"]` and a chip input under `[data-field="args"]` - verified
- `tests/browser/test_flow_studio_mcp_editor_controller.py::_BASELINE_SEEDS` - includes `("dup-arg", {"command": "uvx", "args": ["a", "a", "b"]})` - verified
- `scripts/ui_capture.py` - has a surface named `mcp-edit-stdio` - verified

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
