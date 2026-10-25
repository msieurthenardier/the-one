# Leg: kv-secret-column

**Status**: completed
**Flight**: [The MCP server editor on the library](../flight.md)

## Objective
Grow `App.ui.keyValueTable` with two column types, a `secret` value cell and a per-row `toggle` cell, and the row-level behaviour the MCP environment variables and headers need, built and contract-tested in Chromium and WebKit before the editor uses them (leg 07):
- masking driven by the row's switch;
- the stored-secret mode (B5);
- clear on unmask;
- clear on a key rename;
- a focus-keeping row patch;
- per-row names.

The connector channel map, today's only consumer, does not change. Nothing in the MCP editor changes in this leg.

## Context
- **Flight decisions:**
  - DD5 (secrets: `.value` only, `autocomplete="new-password"`, the eye with `aria-pressed` and a per-row name, B5's stored-value hint and select-on-focus, clear on unmask, the key-rename rule, re-mask through a focus-keeping `setRow`);
  - DD9 (defects 11 part, 14, 15);
  - DD10 (what the old control gave for free; derived-relationship and degenerate-input criteria; no consumer CSS on library internals);
  - DD11 (new `ui-kv-*` marker classes; the allowance only shrinks).
- **The control today** (`js/ui/key-value-table.js`, 304 lines):
  - `CELL_TYPES = { text: true }` (`:6`); an unknown type throws (`:39`);
  - one delegated `input` listener (`:93-103`, `:123`) and one `click` listener (Add and remove);
  - `buildCell` (`:152-169`, "Flight 5 adds 'sensitive' here") builds a `textInput` with the class `ui-kv-input`;
  - non-column keys on a row round-trip through `values()`/`setValues` (`:13-14`);
  - inputs are named `"{column label}, row {n}"` and re-numbered by `renumber()` (`:200-210`);
  - `removeLabel(n, row)` names the remove button;
  - `setValues` rebuilds every row and moves focus to row 1 if focus was inside (`:242-258`). There is no single-row patch.
- **`App.ui.secretInput`** (`js/ui/field.js`, about `:460-507`):
  - a `textInput` with `type=password` and `autocomplete` defaulting to `new-password`;
  - an icon-only `button.api-key-eye` with `aria-pressed`, named "Show password" or "Hide password";
  - the value only through `.value`;
  - `setValue` hides it again. It has no destroy and no option for the button's names.
  - Its catalogue row (`docs/ui-control-inventory.md:58`) owns `api-key-wrap` and `api-key-eye`.
- **`App.ui.toggle`** (`js/ui/choice.js:117`): `{label, labelHidden, checked, onChange(checked), testid on the input}`, returning `{el, control, setChecked, setDisabled}`; `role=switch`.
- **What the MCP editor's table does today** (`mcp-env-headers.js`; leg 07 moves it onto this control). The old control gives these for free, and the new cells must keep them:
  - **Masking:** a sensitive row's value is a password input with an eye; a plain row's is a text input with no eye. Unticking Sensitive on a row whose value still equals its stored mask clears the value (`SENSITIVE_HINT`).
  - **What the old control does wrong** (fixed here): the masked tail sits in `value=` and `data-original-masked=` attributes; the inputs have no `autocomplete`; the switch's `aria-label` is identical on every row; every row's remove is "Remove row"; the eye has no `aria-pressed`.
- **The server's mask shape** (`api.py` `_MASK_SHAPE_RE`, `_looks_masked`): GET returns `***...abcd` (or `***`). The stored-secret mode keys on the row's stored mask (a non-column row key), never on the shape alone.

## Inputs
- Batch B1 is committed (`ebf3ef6`). Leg 03 may be in progress in the same tree. This leg touches only `js/ui/`, `css/components.css`, the catalogue and contract tests, so there is no file overlap.

## Outputs
- **`js/ui/field.js` `secretInput`:** two new options, additive and default-off, so the provider and tool editors are unchanged:
  - `showLabel` and `hideLabel`, which name the eye button (they default to "Show password" and "Hide password", as today), plus `setLabels(show, hide)` on the controller for re-numbering;
  - **`stored` mode**, through `opts.stored` (a non-empty string, the stored mask) and `setStored(mask|null)`. An empty string means no stored mode. While the input's value equals the stored mask:
    - the eye is hidden;
    - a hint ("Stored. Type a new value to replace it.") is linked through `aria-describedby`;
    - **every edit replaces the mask** (defect 14; cycle 1 H2, refined at cycle 2):
      - **The guarantee is a `beforeinput` handler** that selects all of the value first while the value still equals the mask. That covers typing, Backspace and Delete, cut, drop, paste (`insertFromPaste`, so there is no separate paste handler) and `insertReplacementText`, in both engines. It skips `insertCompositionText` and the `history*` types.
      - **An `input`-event fallback covers IME and anything else.** When the previous value was the mask and the new value contains the mask and is longer, the mask is stripped and the rest kept. So an IME composition also replaces the mask; there is no documented gap.
      - **Select-on-focus is only a convenience.** WebKit collapses a click-focus selection on mouseup, which is why `beforeinput` is the real guarantee;
    - once the value differs, the eye appears and the hint is hidden.
  - **The hint element** (cycle 1 H3):
    - it is created only when stored mode is used, so the default DOM is byte-identical to today;
    - it is exposed as `controller.hintEl` (`div.ui-secret-hint`, id from `util.uid`) for the caller to place: the table puts it after `secret.el` in the cell. Stored mode is for table cells only: `App.ui.field` rewrites `aria-describedby` wholesale in `wire()`, so a stored `secretInput` placed in a `field` is unsupported, and the option's doc says so;
    - `secret.el` stays the `.api-key-wrap` row;
    - the class is owned by the secret input's catalogue row, the control that emits it.
  - **`aria-describedby` is a token list** (cycle 1 H4). The hint adds and removes only its own id, never the whole attribute. The table's `setError` is changed the same way, through two small helpers, `App.ui.util.addDescribedBy` and `removeDescribedBy`, added in `js/ui/core.js`, where `App.ui.util` lives. A test covers an error and the stored mode together.
- **`js/ui/key-value-table.js`:**
  - `CELL_TYPES` gains `secret` and `toggle`.
  - **A `secret` column** `{key, type: 'secret', maskedBy: '<toggle column key>', storedKey: '<row key holding the stored mask>', clearOnUnmask: true}`:
    - while `row[maskedBy]` is true, the cell is a `secretInput` (`autocomplete="new-password"`, the eye named "Show value, row n" and "Hide value, row n", re-numbered, and `stored: row[storedKey]` when set);
    - while it is false, the cell is a plain text input with no eye;
    - **switching rebuilds only that cell** (cycle 1 M5):
      - `row.inputs[key]` is repointed to the new `<input>` (never the `.api-key-wrap`), because `onInput` finds its row through it;
      - the error state (`aria-invalid`, `is-invalid`, the error line and its `aria-describedby` token) is re-applied;
      - `inputTestid`, the `ui-kv-input` class (and `ui-kv-input--mono` when the column is mono) and the row-numbered name are re-applied to both variants. `secretInput` builds its own `textInput`, so `buildCell` adds them after construction;
      - the reveal state resets to hidden;
      - focus is restored to the value input if it had focus; a click on the row's toggle keeps focus on the toggle;
    - the value is never written to an attribute.
  - **A `toggle` column** `{key, type: 'toggle', label, ariaLabel, inputTestid}`: an `App.ui.toggle` with `labelHidden`, named "{ariaLabel or the string label}, row n" and re-numbered. When the header label is a Node (for example with an info button), `ariaLabel` is required, so the button's text never leaks into the name. The row's value is a boolean.
    - A new delegated `change` listener handles only the toggle inputs, matched by identity as `onInput` matches. Text inputs also fire `change` on blur, and a test proves a text blur fires no `{type: 'toggle'}`. `onInput` ignores toggle targets (a checkbox also fires `input`).
    - It writes the value and fires `onChange(values, {type: 'toggle'})`.
  - **`clearOnUnmask`:** unticking a row whose value still equals its stored mask clears the value (today's rule) **and clears `row[storedKey]`**, so stored mode ends and re-ticking does not bring it back. The change fires.
  - **Key rename** (cycle 1 M6):
    - a `keyColumn` option, defaulting to `columns[0].key`, names the key column;
    - **the baseline:** the row's trimmed key is captured whenever `row[storedKey]` becomes non-empty, in `setValues` and in `setRow` (leg 07's re-mask after Save re-captures it);
    - **the rule:** when the trimmed key differs from that baseline, on a row whose value still equals its stored mask, the value clears, `row[storedKey]` clears, and the cell's hint (`hintEl`, polite, not an alert and not `aria-invalid`) reads "Type the value again for the new name." (defect 15). The combined clear fires **one** `onChange`;
    - **the hint's life:** it clears when the operator types in the value, and an unrelated `setRow` does not wipe it;
    - **a value edited away from the mask keeps `row[storedKey]`** until the next load. Typing the mask back exactly re-enters stored mode, and leg 07 then sends `__MASKED__`, which keeps the stored secret. That is accepted;
    - it fires at most once per loaded mask. A one-character typo fix also clears the secret: that is accepted, and the hint says why;
    - typing the old key back does not restore it;
    - a trailing space is not a rename;
    - a test also proves that a hand-typed value equal to the old mask, after a rename, is no longer stored-masked (so leg 07 never sends `__MASKED__` under the new key).
  - **`setRow(i, patch)`** (cycle 1 M7):
    - it **merges** the given keys (column and non-column, including `storedKey` and the toggle) into row `i`. All keys are applied to the row's data before any cell re-renders, so a cell never renders a new mask against a stale `storedKey`;
    - it re-renders only the cells whose value or masking changed, without moving focus. A value patch on the focused input sets `.value` directly and restores the selection range;
    - a cell whose value the patch changes loses its error; other errors stay.
    - **Leg 07's plan, decided here:** after Save it maps the server's rows to the UI rows **by key** (the server reorders: plaintext first, then secrets; and it drops empty-key rows, which the UI keeps), then calls `setRow` on each matched sensitive row whose value still equals what was submitted. No keyed reconcile is needed.
    - `setValues` keeps its documented behaviour.
  - **`removeLabel(n, row)`** already exists. The documented example in the catalogue becomes "Remove {KEY}".
  - **A secret column without a toggle column** (`maskedBy` omitted) is always masked.
  - **Marker classes** `ui-kv-secret` and `ui-kv-toggle` on the cells, and `ui-kv-table--fixed` on a table that has a secret or toggle column. All are owned by the table's catalogue row (DD11). No consumer CSS.
- **`css/components.css`** (cycle 1 H1): the new cells' layout in the `.ui-kv*` block. Owned rules only, and no `!important`.
  - The secret cell holds the `api-key-wrap` at the column's width, and the toggle cell is narrow and centred.
  - **`.ui-kv-table--fixed`** sets `width: 100%; table-layout: fixed`, so A12's 4 px overflow cannot recur. Fixed layout does nothing on a `width: auto` table.
    - The toggle and remove columns are sized through a `<colgroup>` the table emits for a fixed table, never only on `th`: the head is hidden when the table is empty, and fixed layout reads widths from the first row.
  - The base `.ui-kv-table` rule is untouched, so the channel map (no secret or toggle column, so no modifier) keeps `width: auto` and its look.
- **`docs/ui-control-inventory.md`:**
  - **row 58, the secret input:** the new options; `ui-secret-hint` added to its owned classes; its "used by" column. The `kv-eye-btn` note stays until leg 07;
  - **row 111, the key-value table:** remove "`type` ... anything else throws", the "Flight 5 adds" text and the `.mcp-kv-*` note. Add the column types, `keyColumn`, `setRow`, and `ui-kv-secret`, `ui-kv-toggle` and `ui-kv-table--fixed` as owned classes;
  - no `EMITTED_EXEMPT` entry is needed.
- **Tests**, engine-parametrized in Chromium and WebKit:
  - `tests/browser/test_ui_key_value_table_contract.py`: new cases for each behaviour above, plus degenerate inputs:
    - an empty table, then Add;
    - a 200-character value;
    - a row whose key is empty;
    - two rows with the same key;
    - a stored mask of `***` (no tail), and a stored mask of `''` (no stored mode);
    - in stored mode: typing, Backspace and `page.keyboard.insert_text` (a real `beforeinput`; it stands in for paste, which needs a clipboard grant in WebKit, and paste takes the same `insertFromPaste` path), with the caret at the start, middle and end (placed by click and by Home/End), each yielding exactly the typed text, with a click-focus in WebKit as well as a Tab-focus. No synthetic `beforeinput` dispatch, which would not edit the field;
    - a value equal to the mask typed by hand on a plain (unticked) row;
    - the toggle and remove names after removing a middle row;
    - a value equal to the mask typed by hand;
    - a toggle flipped twice;
    - remove while the eye is revealed;
    - Escape and Tab order within a row;
    - `setRow` while focus is inside another row (focus stays), and on the focused row (focus stays on the same control);
  - derived relationships: each row's input, eye, toggle and remove names carry the same row number (and the remove names the key when `removeLabel` does); the eye's `aria-pressed` matches the input's `type`; the hint's id is in the input's `aria-describedby` exactly while the stored mode is on;
  - "no attribute holds the secret": after rendering a stored mask and after typing a new value, no attribute anywhere in the table's subtree contains the mask's tail or the typed value;
  - `tests/browser/test_ui_secret_input_contract.py`: the new options; that the defaults are unchanged (the provider's "Show password" names); `stored` mode;
  - **The channel map is unchanged:** the existing table contract tests (14 functions, 28 runs across the two engines, counted at cycle 2; 7 in the secret input file) and the connector editor tests (`tests/browser/test_studio_connector_editor.py`, lane `library`) pass with no edit, and a computed-style check proves a text-only table's cells keep their widths and spacing. The `connector-edit` capture surface matches the before set.

## Acceptance Criteria
- [ ] Every new behaviour in Outputs has a contract test that passes in Chromium and WebKit, run with `THE_ONE_REQUIRE_WEBKIT=1` in the `contracts-controls` lane.
- [ ] **No attribute holds the secret:** the stored mask's tail and a typed secret never appear in any attribute of the table's subtree (tested).
- [ ] **Stored mode (B5):** no eye and the hint while the value equals the stored mask; the eye returns once the value changes; typing, Backspace and `insert_text` with the caret at the start, middle and end each yield exactly the typed text (tested in both engines).
- [ ] **Clear on unmask and the key rename** clear the value as specified, and each fires `onChange` (tested).
- [ ] **`setRow` keeps focus** (tested both ways).
- [ ] **Names:** every control in a row names its row number, and they re-number on remove; the eye has `aria-pressed` (tested).
- [ ] **Nothing else moves:**
  - the defaults of `secretInput` and of a text-only `keyValueTable` are unchanged;
  - the existing contract tests, `test_studio_connector_editor.py` and the provider editor tests (lane `providers`) pass unedited;
  - the `connector-edit` and `provider-edit-*` captures match the before set (`ImageChops`).
- [ ] **Guards:** the catalogue and ownership guards (`test_ui_control_inventory.py`, `test_ui_ownership.py`, `test_ui_emitted_classes.py`) pass with the new classes owned; no new allowance row; the static JS/CSS guards and `make test-unit` pass.

## Verification Steps
- `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser tests/browser/test_ui_key_value_table_contract.py tests/browser/test_ui_secret_input_contract.py -x --timeout 60`.
- `--lane library` and `--lane providers`, each with `THE_ONE_TEST_NETNS=1`. Run at most 3 at a time.
- The captures: `connector-edit` and the `provider-edit-*` surfaces into a scratch set, compared with the before sets. For the provider and connector surfaces, use the newest pre-flight set in `~/.cache/the-one-ui-capture/` (Flight 4's after set, `m31-f4-after`), or retake them on `main` if absent.
- `.venv/bin/python -m pytest tests/test_ui_control_inventory.py tests/test_ui_ownership.py tests/test_ui_emitted_classes.py tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py -q -x --timeout 120`, then `make test-unit`.

## Implementation Guidance
1. **Write the contract tests first** for the `secretInput` options and the two cell types, using the existing harness in each contract file.
2. **`secretInput`:** the labels, then `stored` mode, with the defaults untouched.
3. **The table:** the cell types, the `change` listener, `clearOnUnmask`, the key-rename rule, `setRow`, the names and re-numbering, then the CSS.
4. **The catalogue rows.** Then the guards, the lanes and the captures.

## Edge Cases
- **Key rename:**
  - typing the same key back after a rename does not restore the cleared value (the server never sends it);
  - a key edit on a row with **no** stored mask does nothing special.
- **A row added in the UI** has no stored mask, so it gets no stored mode.
- **Revealing a stored mask** cannot happen, because the eye is hidden in stored mode.
- **`setValues` while an eye is revealed** rebuilds the row hidden, as `setValue` does today.
- **IME:** covered by the stored-mode `input` fallback above. Outside stored mode, behave as `textInput` does (no composition handling).
- **The existing contract counts** (cycle 2): the table file has 14 test functions (28 runs) and the secret input file 7. Re-count at the start if either changed.
- **WebKit:** focus on a button does not happen on click in WebKit/macOS semantics. The tests click with `focus()` first where they assert focus, as the existing contract tests do.

## Files Affected
- `the_one/interfaces/web/static/js/ui/key-value-table.js`, `js/ui/field.js`, `js/ui/core.js` (the `aria-describedby` helpers), `css/components.css`.
- `docs/ui-control-inventory.md`.
- `tests/browser/test_ui_key_value_table_contract.py`, `tests/browser/test_ui_secret_input_contract.py`.
- The flight log; the ledger rows 26, 32 and 35 (the library half; leg 07 shows them in the MCP editor).

## Citation Audit
- `key-value-table.js:6, :39, :93-103, :123, :152-169, :200-210, :242-258`. FD read at `ebf3ef6`.
- `field.js` `secretInput` (the block read by the FD; line numbers move). `choice.js:117` `App.ui.toggle`. `docs/ui-control-inventory.md:58` and `:111`. By grep.
- `connector-editor.js:493`: the only `keyValueTable` consumer. By grep.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.

## Design Review
- **Developer design review, cycle 1 (2026-10-25): approve with changes**, applied in place:
  - the table layout as a `--fixed` modifier, since `table-layout: fixed` needs a width (H1);
  - every edit in stored mode replaces the mask, through `beforeinput` and paste (H2);
  - the hint is owned by the secret input, created only in stored mode, and placed by the caller (H3);
  - `aria-describedby` handled as a token list (H4);
  - the state a cell rebuild carries over (M5);
  - `keyColumn`, trimmed keys, and clearing the stored mask on a rename and on unmask (M6);
  - `setRow` merge semantics, and leg 07's plan to re-mask by key (M7);
  - the toggle-only `change` filter (M8);
  - the toggle column's `ariaLabel` and `inputTestid` (M9);
  - the extra tests (L).

  Substantive, so a second cycle follows.
- **Developer design review, cycle 2 (2026-10-25): approve with changes**, applied in place:
  - the helpers live in `core.js`, and stored mode is for table cells only;
  - `beforeinput` is the guarantee, with no separate paste path and the `input` fallback covering IME;
  - the rename baseline's capture point, its hint mechanism and a single `onChange`; `storedKey` kept after an edit away from the mask;
  - the real test counts;
  - `setRow`'s merge order and caret;
  - `<colgroup>` widths;
  - the `ui-kv-input` class on the secret cell;
  - the exact catalogue rows;
  - `insert_text` in place of paste in the tests.

  This was the last of two cycles. Status `ready`.
