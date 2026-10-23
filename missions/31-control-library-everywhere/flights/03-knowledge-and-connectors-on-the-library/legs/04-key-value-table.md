# Leg: key-value-table

**Status**: completed
**Flight**: [Knowledge and connectors on the library](../flight.md)

## Objective
Add `App.ui.keyValueTable`, the core of the key-value table control:
- a column-defined table of text inputs with a keyed row model, accessible names, an "Add row" button and an icon-only remove per row;
- the MCP editor's table look as the canonical look;
- a catalogue row and engine-parametrized contract tests.

Its first consumer, the connector channel map, migrates in leg 07b. Flight 5 adds the sensitive (masked) column for the MCP editor.

## Context
- **Flight DD4** ("`App.ui.keyValueTable(opts)`"), **DD7** item 8 (the channel map gains this look), **DD8-1** (the data-loss class this control's model removes), **DD8-8** (accessible names), **DD10** (size and role assertions), **DD11**.
- **The canonical look is the MCP editor's key-value table.** `css/studio.css` (`@layer areas`):
  - `.area-studio .mcp-kv-table` (`:408`): width auto, collapsed borders, margin-bottom 8px;
  - `.mcp-kv-thead.is-hidden` (`:409`): the head is hidden with no rows;
  - `.mcp-kv-thead th` (`:410-420`): left, padding 4px 8px, mono, `--font-size-tiny`, bold, uppercase, 1px letter-spacing, `--fg-secondary`, bottom hairline;
  - `tbody td` (`:429`): padding 4px 8px, middle;
  - `.kv-remove-row-btn` (`:433-446`): transparent, padding 4px, `--fg-secondary` turning `--status-danger` on hover, a 16px svg.
- **The markup:** `mcp-server-editor.js` `renderKvRow` (about `:922-952`) uses `field-input` text inputs and a trash-icon remove button named "Remove row". The Add button is `btn-outlined-primary kv-add-row-btn` "+ Add row" (about `:916`).
- **The MCP editor is not migrated here.** Its `.mcp-kv-*` and `.kv-*` rules stay until Flight 5, as recorded intentional duplicates of the new owned rules.
- **The connector channel map today** (`connector-editor.js` about `:452-498`):
  - `div.connector-channel-map-rows` holds rows `div.connector-channel-map-row` (testid `connector-channel-map-row`, `data-row-idx`);
  - each row has two `field-input` inputs (`channel-map-channel` "channel id", `channel-map-agent` "agent name") and a "✕" `channel-map-remove-btn` (testid `connector-channel-map-remove-btn`, aria-label "Remove row");
  - the Add button is `btn-outlined-primary channel-map-add-btn` (testid `connector-channel-map-add-btn`, "+ Add row").
- **What leg 07b needs to keep its testids:** the control must let the caller set the row testid, the per-column input testids, the remove testid and the add testid, and a `data-row-idx` on each row. Today's tests read `data-row-idx`; check `test_flow_studio_library_list.py` about `:1384-1402` and `test_studio_connector_editor.py`.

## Inputs
- **Requires leg 01 to have landed** (lanes, script order).
- `js/ui/{core,button,field}.js` (`util.el`, `util.uid`, `App.ui.button` with `iconOnly`, `App.ui.textInput`) and `js/icons.js` (`trash`).
- `css/components.css`, `docs/ui-control-inventory.md` (the "Key-value table" row about `:110`, "not yet defined"), `tests/test_ui_control_inventory.py`, `tests/browser/_ui_engines.py`.

## Outputs
- **`App.ui.keyValueTable(opts)`** in a new `js/ui/key-value-table.js`, loaded after `ui/button.js` and `ui/field.js`.
  - **Options:**
    - `columns: [{key, label, placeholder, inputTestid, mono, type}]` (at least 1; the keys are unique):
      - `label` is a string or a Node; Flight 5 needs an info button in a header;
      - `type` defaults to `'text'` and is the only type now. Any other value throws. Flight 5 adds `'sensitive'` (a masked value with an eye, plus a per-row switch) through the same per-type internal cell builder, so build cells through one internal `buildCell(column, row)` switch, not inline;
    - `rows: [{<colKey>: value, …}]`. **Keys that are not columns are preserved** on the row model and round-trip through `values()`/`setValues`, for Flight 5's `_originalMasked`;
    - `rowDataset(row) → object` (optional; extra `data-*` on each `<tr>`);
    - `addLabel` (default "+ Add row") and `addTestid`;
    - `rowTestid`, `removeTestid`, `removeLabel(rowNumber, row) → string` (default `"Remove row " + n`);
    - `onChange(values, {type: 'input'|'add'|'remove'})`;
    - `testid` on the table;
    - `label` (the table's accessible name, through `aria-label` on the `<table>`; not a `<caption>`);
    - `emptyHidesHead` (default `true`).
  - **Returns** `{el, values(), setValues(rows), setError(rowIndex, colKey, text|null), focusRow(i, colKey?), destroy}`.
    - `values()` returns the raw rows in display order, including empty ones, as fresh objects. The caller normalises.
    - `setValues` replaces the model and rebuilds the rows.
- **The model** is an array of row objects, each with a stable internal key. Input writes go straight into the model. Add appends a row and focuses its first input. Remove splices by key (never by a stale index), then moves focus to the next row's first input, the previous row's, or the Add button. Rows other than the one removed keep their DOM nodes and values.
- **DOM and names:**
  - a `<table>` with a `<thead>` of column labels (hidden when empty) and a `<tbody>`; each row is a `<tr>` with `data-row-idx` (its current display index, re-numbered on remove), one `<td>` per column with a library text input, and a `<td>` with the remove button;
  - each input is named "{column label}, row {n}" through `setAttribute('aria-label', …)` after `App.ui.textInput` (which has no such option), updated on re-number. A Node label uses its `textContent` for the name;
  - the remove column's `<th>` holds a visually hidden "Actions", as the MCP table has today;
  - the remove button is `App.ui.button({variant: 'ghost', iconOnly: true, icon: 'trash', ariaLabel, testid})` plus the owned `ui-kv-remove` class. It is named by `removeLabel`;
    - **`iconOnly` adds `btn-icon`** (32×32 with a variant background), but the legacy `.kv-remove-row-btn` is transparent, 4px padding and a 16px svg, about 24px. So the `ui-kv-remove` rules set width, height, padding, border and background explicitly, with enough selector weight to beat `.btn-icon` and the variant inside `@layer components`, for example `.ui-kv .ui-kv-remove`;
    - the computed size is pinned in the parity test;
  - the Add button is a library outlined button after the table, inside `el`, which is a wrapper `div` holding the table and the Add button;
  - `setError(rowIndex, colKey, text)` resolves `rowIndex` to the row's internal key at call time, so the error follows that row through later re-numbering. It renders a small error line inside the cell under the input, with an id, linked by `aria-describedby` and `aria-invalid="true"`, without widening the `width: auto` table beyond its column. `null` clears it.
- **`destroy`** removes the listeners and leaves the DOM in place; the caller removes `el`.
- **Owned classes, a new `ui-kv-*` family:** for example `ui-kv`, `ui-kv-table`, `ui-kv-head`, `ui-kv-row`, `ui-kv-cell`, `ui-kv-input`, `ui-kv-remove`, `ui-kv-add`, `ui-kv-error`. Declarations are copied exactly from the `.mcp-kv-*`/`.kv-remove-row-btn` sources, including the remove button's hover and its svg size.
- **The catalogue row** replaces "Key-value table: not yet defined". It records options, returns, owned classes, and that Flight 5 adds a `sensitive` column type (and that the MCP editor's `.mcp-kv-*` rules are intentional duplicates until then).
- **Contract tests:** `tests/browser/test_ui_key_value_table_contract.py`, in the `contracts-controls` lane.

## Acceptance Criteria
- [ ] **`App.ui.keyValueTable` exists** with the options and returns above. It throws on missing or duplicate column keys.
- [ ] **Validation:** an unknown column `type` throws. A Node `label` renders in the header, and the input's name uses its text.
- [ ] **Extra row keys** (for example `{channel: 'a', agent: 'b', _x: 1}`) survive `setValues` → `values()`.
- [ ] **Keyed model, in both engines:**
  - type into row 1 and row 2, add a row, and both keep their typed values;
  - remove row 1, and row 2's typed value survives and is now row 1 (`data-row-idx="0"`), with its input renamed "…, row 1";
  - `setValues` then `values()` round-trips;
  - `values()` includes empty rows;
  - `onChange` fires on input, add and remove.
- [ ] **Focus:** Add focuses the new row's first input. Remove moves focus to the next row, else the previous, else Add.
- [ ] **Names and roles:**
  - every input has an accessible name "{label}, row {n}";
  - every remove button is a `button` named by `removeLabel`;
  - the table has the caption's name when given;
  - `thead th` cells are column headers;
  - with no rows the head is hidden (`emptyHidesHead`).
- [ ] **The svg click:** a click on the remove button's svg removes the row.
- [ ] **Look parity** under an `area-studio` ancestor: the header cell's font family, size, weight, transform, letter-spacing, colour and bottom border, the body cell padding, the remove button's padding and colour (at rest and hovered), and the svg size all match a legacy `<table class="mcp-kv-table">` fixture rendered beside it (the real `studio.css` applies in the harness). Checked in light and dark.
- [ ] **Size:** a row's height equals a legacy MCP kv row's height in the same host (DD10).
- [ ] **`setError(0, colKey, 'Required')`** sets `aria-invalid="true"` and `aria-describedby` on that input and shows the text. After the first row is removed above it, the error stays on the same row. `null` clears both.
- [ ] **`destroy`** removes the listeners: the listener-cleanup contract, or an assertion that later input does not call `onChange`.
- [ ] The catalogue row, `tests/test_ui_control_inventory.py`, `tests/test_ui_ownership.py`, `tests/test_ui_guards.py`, `tests/test_token_definitions.py` and `tests/test_design_tokens_a11y.py` pass. No allowance grows.
- [ ] Both contracts lanes pass with `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1`, and `make test-unit` passes.
- [ ] Ledger row: no visible change (no consumer yet).

## Verification Steps
- `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser tests/browser/test_ui_key_value_table_contract.py -x --timeout 60`
- `--lane contracts-controls`, `--lane contracts-overlay`, `make test-unit`.

## Implementation Guidance
1. **Log a start line.** Read `chip-list.js` (a keyed list with add and remove) and `tile.js` for the factory idioms: validation errors, `util.el`, `applyDataset`, `destroy`.
2. **Write the contract tests first,** then the factory and its CSS section (banner-commented, owned by `App.ui.keyValueTable`).
3. **Re-numbering on remove** updates `data-row-idx` and the input names in place. It must not rebuild the surviving rows.
4. **Catalogue row, guards, lanes. Flight log:** the entry, the ledger row, in-progress lines.

## Consumer selectors (leg 07b)
The control sets no consumer classes. `test_flow_studio_library_list.py` (about `:1384-1402`) reads the classes `.channel-map-channel` and `.channel-map-agent`. Leg 07b moves those tests onto the new per-column input testids, which are new, since the map inputs have neither testids nor `data-field` today, and keeps the `connector-channel-map-row`/`-add-btn`/`-remove-btn` testids. Do not add an `inputClass` option.

## Edge Cases
- **Duplicate keys in `rows`** (two rows with the same channel id) are allowed. The model is keyed internally, not by the column values.
- **`setValues` while an input has focus:** focus moves to the table's first input, or Add if there are no rows. Document it.
- **IME:** input events during composition update the model as usual; nothing is cleared.
- **A long value:** the inputs keep the `field-input` width the MCP table uses. Check that the table stays `width: auto` and does not overflow the editor at 1024px.

## Files Affected
- New: `js/ui/key-value-table.js`, `tests/browser/test_ui_key_value_table_contract.py`
- `css/components.css`, `index.html` (the script tag right after `ui/field.js` and `ui/button.js`; `chip-list.js` is at about `:49`)
- `tests/test_ui_ownership.py`/allowance only if a row changes (none expected); recheck the `contracts-controls` budget after the new file
- `docs/ui-control-inventory.md`
- The flight log

## Citation Audit
Checked at `332496d` on 2026-10-22 (FD read). The design review (Sonnet Developer, cycle 1: approve with changes) added:
- the Flight 5 extension points (`type`, Node labels, preserved extra keys, `rowDataset`, the internal cell builder);
- the remove-button override of `btn-icon`;
- the `setError` markup, keyed by row;
- an `aria-label` rather than a `<caption>`;
- `onChange` with a change type;
- consumer selectors moving to testids in 07b.

The FD read covered:
- `studio.css:400-447`;
- `mcp-server-editor.js:916,922-952,1127-1189`;
- `connector-editor.js:452-498`;
- the inventory row (about `:110`), from the cross-cutting survey.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
