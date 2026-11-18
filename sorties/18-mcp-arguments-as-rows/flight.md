# Sortie: MCP arguments as rows

**Status**: in-flight

## Charter

### Outcome
In the MCP server editor, a local-command server's arguments are entered one per row with an "Add row" button, like Environment variables, and are saved exactly as entered.

### Why Now
The operator finds the chip field confusing (2026-11-17). Reading the code for that report showed the chip field also loses data: it drops a repeated argument (`--flag a --flag a` keeps one `a`) and splits a typed or pasted value at every comma (`--allow=a,b` cannot be entered).

### Success Criteria
- [ ] Arguments shows one row per argument, with Add row and a remove button per row, matching the look of Environment variables.
- [ ] An existing server's arguments load one per row in stored order (the hidden `-y` of `npx -y` and `run` of `pipx run` stay hidden, as today).
- [ ] Save keeps order and repeats; blank rows are dropped.
- [ ] Unsaved-changes, Cancel and Test with unsaved changes work as they do today.

### Constraints
- No change to how arguments are stored (`config.args`, a list of strings) or to the API.
- Other chip fields (allowlists, writable paths, allowed tools) stay as they are.

---

## Pre-Flight

### Objective
Replace the Arguments chip list in the Library MCP server editor (local-command servers only) with a one-column row table built on `App.ui.keyValueTable`, placed where the chips are now. Each row is one argument with Move up, Move down and Remove buttons; "+ Add row" sits under the rows. The control library gains what that needs, each addition inert unless asked for: on the table control, row moves, a full-width layout, a hidden column header and a `focus()` method; on the field control, a group mode. The editor's value model stops removing repeats and never splits a value.

### Open Questions
- [x] Where do the rows sit? → In Connection, where the chips are (operator, 2026-11-17), see Mockup and DD1.
- [x] How is a row moved? → Move up and Move down buttons on every row (operator, 2026-11-17), see DD3.
- [x] Several arguments typed or pasted into one row? → Kept as one argument; nothing is split (operator, 2026-11-17), see DD5.
- [x] A closing HAT? → Yes, a short one (operator, 2026-11-17).
- [x] Is a group mode on `App.ui.field` the right way to label a block of rows? → Yes (Architect, 2026-11-17): no field-level recipe exists for a block with no single control, and a section title would be the uppercase eyebrow, which the mockup does not show. See DD2.
- [x] Does a new local-command server start with no argument rows or one blank row? → No rows, like Environment variables (DD1). A HAT item: the operator may prefer one blank row.

### Design Decisions

**DD1. Arguments is a one-column `App.ui.keyValueTable` in the Connection section**
- Choice: the block stays in `mcp-connection-fields.js`, in the chips' place (after Working directory, local-command servers only). It is one `App.ui.keyValueTable` with a single text column (`key: 'value'`, label "Argument", `mono: true`) and the options `movable` (DD3), `fill` (DD10) and `headHidden` (DD4). `addLabel` is the default "+ Add row". Buttons are named by position, never by value (a value can be 90 characters): "Remove argument {n}", "Move argument {n} up", "Move argument {n} down". The table is wrapped in a group-mode field (DD2) whose caption is "Arguments" and whose hint, "One argument per row, in order.", sits between the caption and the rows as in the mockup. The table's own `label` option is not passed, so the name is not announced twice. A server with no arguments shows no rows, only Add row.
- Rationale: the operator asked for the Environment variables model; that table is this control, and it accepts one column. No new control.
- Trade-off: a table element for what is a list. Accepted for one look and one behaviour across the editor.

**DD2. `App.ui.field` gains a group mode for a block with no single control**
- Choice: `App.ui.field({label, group: <element>, hint, hintTestid, error, errorTestid, testid})` returns the same controller shape. In group mode:
  - The wrapper is the usual `div.field-group`, with `role="group"` and `aria-labelledby` pointing at the caption. The role is on the wrapper, not on the element passed as `group`, so the hint and the Add row button are inside the named group.
  - The caption is a `div.field-group-caption` with a generated id (a new owned class, styled exactly as `.field-group > label`). It is not a `label`, so there is no orphan `label` with no `for`.
  - Child order is caption, hint, the `group` element, error. The hint directly follows the caption (the mockup's order; normal mode keeps its order of label, control, hint, error).
  - The hint and error ids are joined into the wrapper's `aria-describedby`. `setError` shows or clears the error line and that id only: it sets no `aria-invalid` (not allowed on `role="group"`) and no `is-invalid` class (it has CSS only on inputs).
  - `controller.control` is the element passed as `group`.
  - `info` and `labelHidden` are not supported with `group` and throw, as does passing both `control` and `group`. Normal mode is unchanged and still requires `control`.
- Rationale: `App.ui.field` requires one control to point its `label[for]` at, and a table of rows has none while it is empty. The label's classes are owned by the field control, so the area module cannot hand-build the caption (`tests/test_ui_ownership.py`). The existing group recipes in the library (`search-list.js`, `nav-groups.js`) are a caption plus `role="group"` with `aria-labelledby`; a `div` keeps the `.field-group` layout without `legend` rendering quirks.
- Trade-off: a second control-library change in this sortie, and a mode that supports fewer options than the normal one.

**DD3. Row moves are a `keyValueTable` option, inert unless passed**
- Choice: a construct-time option `movable: true` adds two icon-only ghost buttons to each row's actions cell, before Remove: Move up (`chevron-up`) and Move down (`chevron-down`), class `ui-kv-move` (new, owned; styled like `.ui-kv .ui-kv-remove`, with `--btn-disabled-fg` when disabled, never opacity), with `moveUpTestid` and `moveDownTestid`. Names come from `moveLabel(n, row, direction)`; the default is "Move row {n} up" and "Move row {n} down".
  - **Edges.** The first row's Move up and the last row's Move down are natively disabled and keep their names. The disabled state and the names are recomputed in `renumber()`, which already runs after every add, remove, `setValues` and `setRow`; they do not live in `applyRowState`, which returns early when no lock option is set.
  - **The move.** A move swaps two entries of the keyed row model and moves the neighbour's `tr` across the pressed row, so the pressed row's nodes never leave the document. Everything a row owns (input values, selection, error text, stored masks and rename baselines) is on the row object and travels with it. Then `renumber()`, then `onChange(values, {type: 'move'})`.
  - **Focus.** After the move the control calls `focus()` explicitly on the pressed button (WebKit does not focus a clicked button); when that button has just become disabled, focus goes to the row's other move button. The Rules tab's `move()` is the precedent.
  - **Click guard.** The click handler returns early for a disabled button, as the remove path does (WebKit can deliver a click on a disabled button's child).
  - **Announcement.** One visually hidden `role="status"` node, class `ui-kv-live` (new, owned), created only when `movable` is set, says "Moved to row {n} of {total}." It is cleared and written a tick later, so two moves with the same text are both announced.
  - **Width.** In a fixed-layout table the actions column is sized for three buttons when `movable` is set (it is 48px today, enough for one).
  - **Combinations.** `readOnly` builds no move buttons. `movable` together with `lockBy`, `removableBy` or `markerBy` throws at construction: no consumer needs it, and a move across a locked row has no agreed meaning.
  - Without `movable`, the DOM and behaviour are unchanged for the four existing consumers.
- Rationale: the operator chose buttons over no reordering. The sortie 09 row options set the precedent of options that are inert when not passed.
- Trade-off: three buttons per row is busier than Environment variables' one.

**DD4. The column header can be hidden visually**
- Choice: a construct-time option `headHidden: true` wraps each column label in a `span.visually-hidden` (the recipe the actions column's header cell already uses) and adds a modifier class `ui-kv-table--head-hidden` (new, owned) that zeroes the head cells' padding, border and height. The `thead` keeps its table display, so table semantics hold in both engines; `emptyHidesHead` still applies. Inputs keep their names, "Argument, row {n}".
- Rationale: the approved mockup shows no column header: with one column under a caption that already says "Arguments", a header row repeats the caption. Putting `.visually-hidden` on the `thead` itself would make it `position: absolute`, which turns a table section into a block and can drop table semantics in WebKit.
- Trade-off: one more option on the table control.

**DD5. One row is one argument, taken whole**
- Choice: nothing splits a value: not a comma, not a space, not a paste. At collect time each row's value has leading and trailing whitespace trimmed; inner whitespace is kept; a row that is empty after the trim is dropped. Order is the row order. Repeats are kept.
- Rationale: the operator chose "keep as one argument". Trimming the ends guards against an invisible trailing space from a paste, which would break a path or flag with no visible cause.
- Trade-off: an argument that must begin or end with a space, and an empty-string argument, cannot be entered. Judged not to occur in practice; listed for the HAT.

**DD6. The value model compares the collected list, so a blank row is not a change**
- Choice: `connectionFields.values().args` returns the collected list of DD5 (trimmed, blanks dropped). `baselineFrom(source)` returns the stored display arguments mapped through the same rule, and no longer through `shared.uniqueStrings` (the writable-paths chip list keeps using it). The editor's dirty check is the existing JSON snapshot of `values()`, so adding an empty row, or typing and deleting a value, leaves the form clean, and a move is a change.
- Rationale: keeps the editor's rule that typing a change and reverting it is clean, and keeps Cancel and Test with unsaved changes on their existing paths with no new plumbing.
- Trade-off: differs from Environment variables, where an added empty row counts as a change (its dirty check compares row identities). Accepted: an empty argument row is dropped on Save, so reporting it as unsaved work would be wrong.

**DD7. Stored shape and the implicit runtime arguments are untouched**
- Choice: `config.args` stays a list of strings. The controller keeps prepending `-y` for `npx -y` and `run` for `pipx run` at Save, and `deriveStdioRuntimeSelection` keeps stripping them on load. Changing the Command select does not touch the rows. A stored list that already holds repeats, or a value with a comma, now loads and saves unchanged.
- Limit: a stored argument with leading or trailing whitespace, or an empty-string argument (possible only through the API), loads as stored and compares clean, but the next Save of any field trims or drops it (DD5). The stored shape does not change, so the charter's constraint holds; listed for the HAT.
- Rationale: the charter's first constraint.
- Trade-off: the limit above.

**DD8. DOM contract**
- Choice: `data-field="args"` moves to the group-mode field's wrapper (today it is on the chip list's root). `data-field-type="array"` goes away with the chips: no MCP editor code reads either attribute (errors and focus go through the field module's own name map), so `data-field` is kept only as the tests' anchor, and the editor leg greps for any reader of `data-field-type` on this field before dropping it. The element id `mf-args` goes away; it is an id, not a testid, so it is not added to the testid registry's "Retired testids" table. New testids: `mcp-args-field` (the wrapper), `mcp-args-table`, `mcp-args-row`, `mcp-args-input`, `mcp-args-move-up`, `mcp-args-move-down`, `mcp-args-remove`, `mcp-args-add-row-btn` and `mcp-args-hint`. A field error for `args` (a refused Save) shows on the block through the field's error line; focusing the field on error calls the table's `focus()` (DD10).
- Rationale: the tests address the field by `data-field`; the Environment variables table set the testid pattern.
- Trade-off: every test that reaches the chips by `[data-field="args"].chip-list-editor` or `label[for="mf-args"]` is rewritten in the same leg (see Prerequisites for the list).

**DD9. Verification apparatus**
- Choice: Playwright browser tests, no behavior test. Control changes are pinned in the engine-parametrized contract files in Chromium and WebKit: `tests/browser/test_ui_key_value_table_contract.py` for the table and `tests/browser/test_ui_library_contract.py` for the field (there is no separate field contract file). The editor change is pinned in `tests/browser/test_flow_studio_mcp_editor_fields.py` and `test_flow_studio_mcp_editor_kv_chips.py` (the `mcp` lane), with `test_flow_studio_mcp_editor_controller.py` (`mcp-connection`) and `test_flow_chiplist_label_resolver.py` (`shared`) kept green. Act path: Playwright types into `mcp-args-input`, clicks the move, remove and add buttons, and clicks Save. Observe path: the DOM (row order, values, names, `editor-unsaved`), and the stored record through the authenticated `GET /api/mcp-sources/{id}` the existing tests already use (`config.args`).
- Rationale: every criterion is a deterministic DOM or stored-record fact; two live agents would add cost and no coverage.
- Trade-off: none.

**DD10. Two more table additions the editor needs: `fill` and `focus()`**
- Choice: a construct-time option `fill: true` turns on the control's existing fixed layout (table width 100%, `table-layout: fixed`, a `colgroup`) for a table with no secret or toggle column; Arguments passes it. The control also returns a new method `focus()`: it focuses the first row's first input, or the Add row button when there are no rows.
- Rationale: without `fill` a one-column table renders each input at its intrinsic width (about 20 characters), unlike the mockup and unlike Working directory above it; the area module cannot widen it with CSS because the `ui-kv*` classes are owned. Without `focus()` the editor cannot reach Add row for its focus-on-error path without querying an owned class.
- Trade-off: two more additions to the table control, both inert for the four existing consumers.

### Mockup (operator-approved, 2026-11-17)

The operator chose "In Connection" over "Its own section" (a titled Arguments section between Connection and Environment variables). `^`, `v` and `x` stand for the icon-only Move up, Move down and Remove buttons.

```
CONNECTION ----------------------------------------
 Name               [ filesystem               ]
 Type               [ Local command          v ]
 Command            [ npx -y                 v ]
   Runs a Node package from npm, downloaded on
   first use. Put the package name in Arguments.
 Working directory  [ (optional)               ]
 Arguments
   One argument per row, in order.
   [ @modelcontextprotocol/server-fs ]  ^  v  x
   [ --root                          ]  ^  v  x
   [ /home/me/My Documents           ]  ^  v  x
   [ + Add row ]

 [ Test ]   * Connected - checked 3:42 PM

ENVIRONMENT VARIABLES -----------------------------
 Key          Value            Sensitive
 [ API_KEY ]  [ ********  ]    (on)       x
 [ + Add row ]
```

Decided with no board (operator, same day): Move up and Move down buttons on each row; a row holding several words stays one argument.

A clickable board of the same layout, in the app's dark theme, was shown to the operator and approved with the spec on 2026-11-17 (https://claude.ai/artifact/PQArFLy1wvHK4LMsaoLYVF, private to the operator). It shows what the legs build: no column header, the hint between the caption and the rows, full-width argument boxes, three icon buttons per row with the edge moves disabled, and "Unsaved changes" appearing on an edit or a move but not on a blank added row. It is a reference for the look, not a pixel contract; the control library's own classes decide spacing.

### Citation Audit

Verified against the working tree at `ac1e2925`.

| Citation | Status |
|---|---|
| `the_one/interfaces/web/static/js/areas/studio/mcp-connection-fields.js::create` — Arguments is `ui.chipList({inputId: 'mf-args', dataset: {field: 'args', fieldType: 'array'}})` wrapped in `ui.field({label: 'Arguments', control: argsChips.input, host: argsChips.el})` with class `mcp-stdio-only` | verified |
| `mcp-connection-fields.js::values` / `::baselineFrom` — `values()` reads `argsChips.values()`; `baselineFrom` passes `sel.displayArgs` through `shared.uniqueStrings` | verified |
| `the_one/interfaces/web/static/js/areas/studio/mcp-editor-shared.js::uniqueStrings` — drops a repeated string, first-seen order; its other caller is `mcp-sandbox-fields.js` (writable paths) | verified |
| `the_one/interfaces/web/static/js/ui/chip-list.js` (header contract) — "duplicates are ignored"; Enter, comma and Tab commit; a paste containing a comma splits | verified |
| `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js` (collect) — `argsList = prependArgs.concat(fv.args)`; `config.args` is set only when the list is non-empty; `-y` and `run` are the prepended values | verified |
| `mcp-server-editor.js::isDirty` — compares `JSON.stringify({connection: connection.values(), sandbox: sandbox.values()})` to a baseline snapshot, plus `envHeaders.isDirty()` | verified |
| `the_one/interfaces/web/static/js/ui/key-value-table.js` (header contract and constructor) — `columns` needs at least one entry; `onChange(values, {type})`; the row model is keyed and a remove keeps surviving rows' DOM nodes; `renumber()` rewrites names in place; the remove button is an icon-only ghost `App.ui.button` in a `td.ui-kv-cell`; the return value has no focus method for the Add button | verified |
| `key-value-table.js` — no move option exists; the `thead` is always built and is hidden only while the table has no rows (`emptyHidesHead`); the actions column's header cell holds a `span.visually-hidden` | verified |
| `key-value-table.js` (constructor) — `fixed` is set only by a `secret` or `toggle` column; only then is the table `ui-kv-table--fixed` with a `colgroup`, whose actions `col` is 48px | verified |
| `key-value-table.js::applyRowState` — returns at once unless `readOnly`, `lockBy`, `markerBy` or `removableBy` is set | verified |
| `the_one/interfaces/web/static/js/ui/field.js::App.ui.field` — throws without a `control` element; the label is a `label` with `htmlFor = control.id`; `host` only places a wrapper in the control's slot; `setError` sets `is-invalid` and `aria-invalid` on the control; the hint is built as `div.field-hint` after the control slot | verified |
| `the_one/interfaces/web/static/js/icons.js` — `chevron-up` and `chevron-down` exist in `App.icons` | verified |
| `the_one/interfaces/web/static/js/areas/studio/rules-notes-tab.js` — Move up and Move down are hand-built `App.ui.button`s on the rule list, not a library option | verified |
| `tests/browser/test_flow_studio_mcp_editor_fields.py`, `tests/browser/test_flow_chiplist_label_resolver.py` — reach the field through `[data-field="args"].chip-list-editor` and `label[for="mf-args"]` | verified |
| `tests/browser/test_flow_studio_mcp_editor_kv_chips.py::_add_chip` — called with `"args"`; `tests/browser/test_flow_studio_mcp_editor_controller.py::_BASELINE_SEEDS` — holds `("dup-arg", {"command": "uvx", "args": ["a", "a", "b"]})` and a legacy-type seed with `["q", "q"]` | verified |

### Prerequisites
- [x] No open sortie or active mission covers the MCP editor's connection fields (sortie 12 is unrelated).
- [x] Squawk 0371 (the editor's Forget button, PR #375) touches `mcp-connection-status.js` and its status test file only; no overlap with this flight's files. PR #375 merged on 2026-11-17 (`f635e039`); the flight branch is cut from that `main`.
- [x] `scripts/ui_capture.py` has no selector on the args chips (Architect, 2026-11-17). Its `mcp-edit-stdio` surface seeds a long argument, so the editor leg re-captures that surface as a visual check.
- [x] Identified (their rewrite is the editor leg's work): tests that pin the chip markup for Arguments: `tests/browser/test_flow_studio_mcp_editor_fields.py` (nine sites); `tests/browser/test_flow_studio_mcp_editor_kv_chips.py` (`_add_chip` with `"args"` at five call sites, and `test_chip_edit_after_cancel_is_tracked_as_dirty`'s `"args"` parameter); `tests/browser/test_flow_chiplist_label_resolver.py` (the `mf-args` half; the writable-paths half stays). The leg greps `tests/`, `scripts/`, `docs/` and `tests/behavior/` again for `mf-args` and `data-field="args"` before it starts.
- [x] Identified (kept green by the editor leg): must stay green unchanged in meaning: `tests/browser/test_flow_studio_mcp_editor_controller.py`'s baseline parity and clean-mount tests over `_BASELINE_SEEDS` (the `dup-arg` seed and the legacy-type seed prove DD6: a stored repeat mounts clean).

### Pre-Flight Checklist
- [x] All open questions resolved
- [x] Design decisions documented
- [x] Citation Audit complete — every code-asserting design decision verified
- [x] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined
- [x] Operator-approved mockup recorded

---

## In-Flight

### Technical Approach
1. **Control library first.** Add to `App.ui.keyValueTable`: `movable` with `moveUpTestid`, `moveDownTestid` and `moveLabel` (DD3), `headHidden` (DD4), `fill` and `focus()` (DD10). Add the group mode to `App.ui.field` (DD2). Each is inert when not passed. Pin them in the contract files in both engines, including: a move keeps the moved input's node, value and error; edge buttons are disabled and keep their names after add, remove, `setValues` and a move; focus after a move, at the edges too; the status text, twice in a row; `readOnly` builds no move buttons; the throwing combinations; `fill` and the actions column's width with three buttons; the hidden header keeps the table's row and column semantics; group mode's order, names, describedby and `setError`; an existing table or field with none of the options is unchanged. Update the catalogue rows in `docs/ui-control-inventory.md` (options, the new owned classes `ui-kv-move`, `ui-kv-live`, `ui-kv-table--head-hidden`, `field-group-caption`; the chip list row's "used by" text) so `tests/test_ui_control_inventory.py`, `tests/test_ui_ownership.py` and `tests/test_ui_emitted_classes.py` pass.
2. **Then the editor.** In `mcp-connection-fields.js`, replace the chip list with the table inside a group-mode field; implement the collect rule of DD5 in one function used by both `values()` and `baselineFrom()`; keep `setValues`, `clearErrors`, `setError('args', …)`, the focus-on-error path (through the table's `focus()`) and `destroy` working; hide the block for HTTP servers as today (`mcp-stdio-only`). `mcp-server-editor.js` should need no change beyond what the new handle requires. Rewrite the pinned tests and add: repeats survive a Save and a reload; a value with a comma and one with inner spaces survive; blank rows are dropped and do not make the form dirty; a move makes it dirty and Cancel restores the saved order; Test with unsaved rows sends them; the `npx -y` and `pipx run` cases still hide their implicit argument. Update `docs/ui-testid-registry.md` (the new ids only), the chip list's header comment (it names "the MCP editor's arguments"), the comment in `tests/_ui_guard_helpers.py` that names `mf-args`, and `the_one/agents.md`'s MCP editor notes.
3. **HAT** on a scratch dev instance (never port 8484 or the default data directory), then the flight review with the Reviewer and the Accessibility Reviewer in parallel. For the Accessibility Reviewer: the editor now has two "+ Add row" buttons (Arguments and Environment variables); the group gives a screen reader the context, and a name such as "Add row to Arguments" would also separate them for voice control while keeping the visible label in the name.

### Checkpoints
- [x] All contract lanes green in both engines with the new options (`THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1`, `--lane contracts`)
- [x] `mcp`, `mcp-connection` and `shared` lanes green with Arguments as rows (`THE_ONE_TEST_NETNS=1`); unit tier green
- [ ] HAT walked with the operator

### Adaptation Criteria

**Divert if**:
- The stored shape or the API would have to change to keep repeats or order.
- Row moves cannot be added to `App.ui.keyValueTable` without changing the behaviour of its existing consumers (the connector channel map, the MCP environment variables and headers table, the agent credentials tile, the secret editor).
- A second, independent set of decisions appears (for example reworking the writable-paths chip list, or the Command select). That is a new sortie.

**Acceptable variations**:
- A visible column header if the hidden header of DD4 still misbehaves in an engine.
- A native `fieldset` and `legend` for group mode, if the Accessibility Reviewer asks for it.
- The exact wording of the buttons' names and the status text, within the patterns of DD1 and DD3.
- One blank row on a server with no arguments, if the operator asks for it at the HAT.

### HAT list
- A new local-command server starts with no rows (DD1).
- Trimmed ends, and no empty-string argument (DD5, DD7's limit).
- The hint's place, the hidden column header and the row width against the mockup.
- Two "+ Add row" buttons in one editor.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `control-row-moves` - `App.ui.keyValueTable` row moves, full-width layout, hidden header and `focus()`; `App.ui.field` group mode; contract tests; catalogue rows
- [x] `arguments-rows` - the MCP editor's Arguments block on the table, the value model, the rewritten and new flow tests, docs
- [ ] `hat-and-alignment` *(optional)* - Guided HAT session with iterative fixes

---

## Post-Flight

### Completion Checklist
- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing
- [ ] Documentation updated

### Verification
- With `THE_ONE_TEST_NETNS=1` on the WSL host: `THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane contracts`, and `--lane mcp`, `--lane mcp-connection` and `--lane shared`, all green, plus every lane a grep for `mf-args`, `data-field="args"` and the table control's pins turns up.
- `make test-unit` green (the control inventory, ownership, emitted-classes and UI guards among it).
- The `mcp` lane measured 292 s against a 330 s budget before this flight. Its time is read from the closing `--parallel 3` gate on a quiet host, and it is re-budgeted there if it is over, never from a solo run.
- On a scratch dev instance: an existing local-command server shows its arguments one per row in stored order; entering `--flag`, `a`, `--flag`, `a` and `--allow=a,b`, saving and reloading shows the same five rows; the stored `config.args` matches.
