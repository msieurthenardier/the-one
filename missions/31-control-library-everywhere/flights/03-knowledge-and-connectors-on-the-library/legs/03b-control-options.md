# Leg: control-options

**Status**: completed
**Flight**: [Knowledge and connectors on the library](../flight.md)

## Objective
Add the library options and the one new factory that the knowledge-base and connector editors need, each with a catalogue entry and engine-parametrized contract tests, before any consumer migrates:
- `chip` `dataset` and `tone: 'warning'`;
- `App.ui.clearableInput`;
- the `more` icon;
- `editorShell` `save.enabledWhenClean` and an error `role`;
- `status` `ledTestid`;
- `copyField` `buttonLabel`;
- any `App.ui.menu` gap the knowledge-base item menu needs.

## Context
- **Flight DD4** lists each item. **DD6** says where each is consumed. **DD11** holds the standing rules. **DD10** carries Flight 2 DD11's size and role-structure assertions for new size-bearing or composite controls.
- No consumer migrates in this leg. Legs 05a-07b consume these options. The chip cascade fix is leg 03c.
- The current code:
  - **`App.ui.chip`** (`js/ui/feedback.js` about `:192-215`): `label`, `tone` `neutral|danger` (it throws on others), `size` `sm`, `title` and `testid`. There is no `dataset`. The classes are `chip`, `chip--danger` and `chip--sm`.
    - **Consumer need:** the knowledge-base status counts carry `data-status` (testid `kb-status-count`, `knowledge-section.js` about `:1309`).
    - `.kb-item-standalone-badge` recolours a chip in `studio.css` (about `:903`), and the warning tone replaces it.
  - **`App.ui.status`** (`feedback.js` about `:145-191`): `state`, `text`, `ledLabel`, `live`, `role` and `led:false` already exist. The testid goes on the `p.ui-status` root. With text, the LED is `aria-hidden`.
    - **The need:** `ledTestid`, a caller testid on the LED span, so the connector header's line can keep `connector-status-led` on the LED and `connector-status-label` on the root (flight DD4 and DD6).
  - **`App.ui.editorShell`** (`js/ui/editor.js` about `:42-175`): `actions.cancel.enabledWhenClean` exists, and Save is disabled until `setDirty(true)`, which also shows the "Unsaved changes" caption. The error span is `span.editor-error` (about `:101`) with no role.
    - **The need:** `actions.save.enabledWhenClean`, so Save is enabled on a clean form *without* the caption (knowledge-base Create), and an option that gives the error span `role="alert"`.
    - Watch the interaction with `setBusy` (about `:62-63`): `setBusy(false)` restores "the dirty-derived state", which must now include `enabledWhenClean` for Save.
  - **`App.ui.copyField`** (`js/ui/copy.js` about `:84-…`): `label` names the input. `copyButton`'s visible text and accessible name are "Copy", then "Copied".
    - **The need:** `buttonLabel`, the button's resting visible text and name ("Copy pairing code"). The "Copied"/failure feedback still swaps the visible text, and the name follows the text as today, with no stale `aria-label`.
  - **`App.ui.menu`** (`js/ui/menu.js`): a WAI-ARIA menu button. Its trigger is `App.ui.button` options (`iconOnly` + `ariaLabel` allowed), and items take `{label, onSelect, icon, danger, disabled, testid}`. The popup takes the testid. Document listeners exist only while it is open. `activate` calls `close(true)` (focus back to the trigger), then `item.onSelect(item)`, so an `onSelect` can move focus afterwards.
    - **Compare with `buildItemMenu`** (`knowledge-section.js` about `:679-762`): the trigger testid is `kb-item-menu-btn` with the label "Item actions"; the popup is `kb-item-menu`; the items are `kb-item-chunks-btn` ("View chunks") and `kb-item-source-btn` ("View source").
    - **The expected gap is only the trigger icon.** It is the text "⋯" today and becomes the `more` icon. List any other gap you find in the flight log, and add it here only if it is a real need; otherwise record "none".
  - **`icons.js`** holds an SVG string table: 36 icons, lucide style, with `aria-hidden` and `focusable=false` and 24×24 stroke paths. There is no `more`/ellipsis icon. Add lucide's `ellipsis` (horizontal) as `more`.
  - **A new `App.ui.clearableInput(opts)`** (flight DD4, squawk 0100; the operator chose an explicit × on 2026-10-22). It is a separate factory, because `copyField` and `secretInput` call `textInput` internally and `textInput` must keep returning a bare `HTMLInputElement`.
    - It returns `{el, input, clear(), setValue(v), destroy}`, used as `field({control: c.input, host: c.el})`, the `secretInput` host precedent (read `js/ui/field.js`).
    - The × is a small icon-only library button inside the field's end. It is shown only while there is text, and named "Clear" plus the field's label (or `clearLabel`).
    - Pressing it, or Escape while there is text, clears the value, fires an `input` event and `onClear`, and keeps focus in the input.
    - Escape on an empty input does not stop propagation.
    - `setValue` updates the × visibility, and so does typing.
    - It never uses `type=search`.
    - It needs an `x` icon (there is likely one already; grep `icons.js`).

## Inputs
- `js/ui/{feedback,editor,copy,menu,field,button,core}.js`, `js/icons.js` and `css/components.css` (`@layer components`; owner banner sections).
- `docs/ui-control-inventory.md`: the rows for chip, status, editorShell, copyField and menu, and a new row for `clearableInput`.
- The contract files: `tests/browser/test_ui_feedback_contract.py` (chip and status), `test_ui_editor_contract.py`, `test_ui_copy_contract.py`, `test_ui_menu_contract.py`, `test_ui_icon_contract.py` and a new `test_ui_clearable_input_contract.py`. Confirm the real names with `ls tests/browser/test_ui_*`. They sit in `contracts-controls` or `contracts-overlay` (menu) after leg 01's split.
- `tests/test_design_tokens_a11y.py`, the contrast gate. A new tone's text and background pair must be audited there.

## Outputs
- **`chip`:**
  - `dataset` (object → `data-*`);
  - `tone: 'warning'`, adding `chip--warning`, which **mirrors `.chip--danger` exactly**: the soft warning fill `--status-warning-bg-soft`, a warning border, and `--status-warning` text, without `cursor: help`. This is the Flight Director's call, the canonical form.
    - Today's `.kb-item-standalone-badge` is warning text on the plain chip's `--accent-translucent` fill, a pair the contrast gate does not cover.
    - The gated pair is `--status-warning` on `--status-warning-bg-soft` (`test_warning_text_on_soft_fill_passes_body_aa`, about `:526`).
    - Add a source-grep guard modelled on `test_chip_danger_consumes_the_gated_danger_pair` (about `:436`).
    - The consumer leg (05b or 06a) records the small visible change in the ledger for the HAT.
  - `dataset` uses `App.ui.util.applyDataset` (camelCase keys become `data-*`).
- **`status`:** `ledTestid` puts a testid on the LED span. With `led:false` it is **ignored**, so callers can toggle `led` freely. `set()` rewrites only the LED's `className` and aria attributes, so the testid persists.
- **`editorShell`:**
  - `actions.save.enabledWhenClean`: with it, `setDirty(false)` leaves Save enabled and the caption hidden, and `setBusy(false)` restores Save to enabled;
  - a top-level `errorRole: 'alert'` option (the only allowed value; anything else throws, as `status`'s `role` validation does) puts `role="alert"` on `span.editor-error`. The span is always present and empty, so it announces on change.
  - **Implementation:** in `apply()` (about `:133`), `saveButton.disabled = busy || !(dirty || cleanSave)`, mirroring the existing `cleanCancel`. The caption stays driven by `dirty` alone, and busy and dirty stay independent flags (`setBusy` about `:170`).
- **`copyField`:** `buttonLabel`, passed as `copyButton`'s `label`. `copyButton` already shows "Copied" or "Copy failed" for about 2 s and restores with `show(label)`. `doneText`/`failText` change only the announcement (`copy.js` about `:59-63`).
- **`icons.js`:** `more` (lucide `ellipsis`, the same SVG header as the others). `x` already exists (`icons.js:24`).
- **`App.ui.clearableInput`** in `js/ui/field.js` (406 lines today).
  - **Options:** it mirrors `textInput` (`value`, `id`, `placeholder`, `autocomplete`, `dataset`, `testid`, `onInput`, `disabled`), plus:
    - `label`, the input's aria-name when there is no visible label, as `secretInput` does;
    - `clearLabel`, default "Clear" plus the label;
    - `clearTestid`;
    - `onClear`.
  - **The input** keeps the `field-input` class.
  - **The ×** is `App.ui.button({variant: 'ghost', size: 'sm', iconOnly: true, icon: 'x', ariaLabel: clearLabel})`. It is `hidden` while the input is empty, which also takes it out of the tab order.
  - **The layout is new:** `secretInput` is a flex row with a sibling button, and only its `host`/`control` pattern transfers. The `.ui-clearable` wrapper is `position: relative`. The × is absolutely placed at the inline end, and the input reserves `padding-inline-end` at least the ×'s width.
  - **Clearing** (click or Escape) sets the value to empty, calls `input.focus()` **before** hiding the ×, and dispatches `new Event('input', {bubbles: true})` once. It then calls `onClear`.
  - **Escape with text** clears and calls `preventDefault()` and `stopPropagation()`. Escape on an empty input, or during IME composition (`isComposing` or `keyCode === 229`), does nothing and passes through.
  - **`setValue(v)`** sets the value and the × visibility without firing `input`.
  - **CSS** goes in `components.css` with the owned classes `ui-clearable`, `ui-clearable-input` and `ui-clearable-clear`.
- **Menu: no behaviour gap.** Compared with `buildItemMenu` and its keyboard test (`test_flow_studio_knowledge_inventory.py` about `:1109-1139`), `App.ui.menu` covers:
  - ArrowDown-open with focus on the first item;
  - arrow navigation with wrap;
  - Escape returning focus to the trigger;
  - outside-press close;
  - the trigger, popup and item testids;
  - an icon-only trigger.

  **The differences** are recorded in the flight log for leg 06b:
  - it closes on `pointerdown`, not on a capture `click`;
  - the `kb-item-menu*` classes and their `studio.css` rules go;
  - `onSelect` runs after focus has returned to the trigger, so the consumer must move focus to the opened panel itself;
  - it has no portal and no edge flipping, so a popup inside the scrolling "Other items" panel may clip (06b checks this);
  - the catalogue row ("KB item menu", about `:118`) flips in 06b, not here.

  No menu change is made in this leg.
- **The catalogue:** every changed row is updated, and the new row is added.

## Amendment from the leg 06a review (binding)
- **`App.ui.field` gains `errorTestid`,** placed on the error node `setError` creates, symmetric with `hintTestid`.
- **`App.ui.section` gains `descriptionTestid`,** on its `p.section-description`.
- Each gets a contract test.

## Amendment from the leg 05b review (binding)
- **`App.ui.status` gains `textTone: true`.** For the states `danger` and `warning`, the text node takes `--status-danger`/`--status-warning`, through an owned modifier class on the root (for example `ui-status--tone`) and a `[data-state]` rule. Without the option nothing changes.
  - **Contrast:** add source-grep guards in `tests/test_design_tokens_a11y.py` showing that the pair used is a gated text-on-surface pair (find the existing `--status-danger`/`--status-warning` text-on-surface audits; add one if missing).
  - **Contract test:** with `led:false`, `textTone:true` and `state:'danger'`, the text's computed colour is the danger token, and without `textTone` it is unchanged.

## Acceptance Criteria
- [ ] **`chip`:**
  - `App.ui.chip({label, dataset: {status: 'indexed'}})` renders `data-status="indexed"`;
  - `tone: 'warning'` renders `chip--warning`, and an unknown tone still throws;
  - the warning pair passes the contrast gate in light and dark.
- [ ] **`status`:**
  - `App.ui.status({text: 'Not connected', state: 'danger', testid: 'a', ledTestid: 'b'})` puts `a` on the `p`, `b` on the LED, `data-state="danger"` on the root, and `aria-hidden="true"` on the LED;
  - existing status tests pass unchanged.
- [ ] **`editorShell`:**
  - with `save.enabledWhenClean`, a fresh shell has Save enabled and no caption;
  - `setDirty(true)` shows the caption;
  - `setDirty(false)` hides it and leaves Save enabled;
  - `setBusy(true)` disables Save, and `setBusy(false)` re-enables it;
  - without the option, the behaviour is unchanged (existing tests pass);
  - with the error-role option, the error span has `role="alert"`.
- [ ] **`copyField`:**
  - with `buttonLabel: 'Copy pairing code'`, the button's resting accessible name and text are "Copy pairing code";
  - after a successful copy the visible text is "Copied" for about 2 s, and the accessible name follows it (no stale `aria-label`);
  - it then returns to "Copy pairing code".
- [ ] **`clearableInput`, in Chromium and WebKit:**
  - the × is hidden when empty and visible after typing;
  - its accessible name is "Clear" plus the label;
  - a real pointer click on it (in both engines) empties the input, fires `input` once, calls `onClear`, and leaves focus in the input;
  - Escape with text does the same and does not reach a bubble-phase `document` `keydown` listener;
  - Escape when empty does reach it;
  - Escape during composition does not clear;
  - `setValue('x')` shows the ×;
  - the × does not overlap a long value (computed padding-end ≥ the button's width);
  - Tab order is input, then ×;
  - `field({control: c.input, host: c.el, label})` labels the input;
  - it adds no `document`, `window` or `body` listeners, as `test_ui_listener_cleanup.py` instruments, and after `destroy` typing no longer toggles the ×.
- [ ] **`App.icon`/`App.ui.icon('more')`** returns an SVG with `aria-hidden`.
- [ ] **A size assertion:** the clearable input's height equals a plain `textInput`'s in the same field (DD10).
- [ ] **The menu difference list** above is recorded in the flight log for 06b.
- [ ] **The warning chip** has the soft fill, border and text of the gated pair, and its source-grep guard in `test_design_tokens_a11y.py` passes.
- [ ] **The catalogue rows** are updated and added. `tests/test_ui_control_inventory.py`, `tests/test_ui_ownership.py`, `tests/test_ui_guards.py`, `tests/test_token_definitions.py` and `tests/test_design_tokens_a11y.py` pass. The sink and ownership allowances do not grow.
- [ ] **Both contracts lanes** pass with `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1`. So do `providers` (editorShell's first consumer, the provider editor), `agent-tabs` (copyField in self-configuration) and `make test-unit`.
- [ ] **The ledger** has a row: no visible change, since no consumer changes yet.

## Verification Steps
- The contract files individually: `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser tests/browser/test_ui_<x>_contract.py -x --timeout 60`.
- `--lane contracts-controls`, `--lane contracts-overlay`, `--lane providers` and `--lane agent-tabs`.
- `make test-unit`.

## Implementation Guidance
1. **Log a start line.** Read each factory and its contract file first, and match the option-validation style: throw on unknown enum values.
2. **Write the tests first** for each option, in the existing contract file of that control, then implement.
3. **`clearableInput`:** read `secretInput` in `field.js` for the `host`/`control` pattern only. The in-field overlay layout is new (above).
4. **Contrast:** add the warning chip's source-grep guard, modelled on the danger one.
5. **Catalogue rows, the guards, the lanes. Flight log:** the entry, the ledger row, the menu gap list, and in-progress lines.

## Edge Cases
- **`enabledWhenClean` on Save plus `setBusy`:** `setBusy(true)` must win while busy. Test the order `setBusy(true)`, `setDirty(false)`, `setBusy(false)`: the end state is Save enabled.
- **`clearableInput` with IME composition:** Escape during composition (`isComposing`) must not clear.
- **A clearable input inside a modal:** confirm that `modal.js`'s Escape handler (about `:249`) is on the dialog, in the bubble phase, so the first Escape clears the field and only a second closes the modal. If it is a document capture listener, record that and test the actual order.

## Files Affected
- `js/ui/feedback.js`, `js/ui/editor.js`, `js/ui/copy.js`, `js/ui/field.js` (or the new `js/ui/clearable-input.js`), `js/ui/menu.js` (only if a gap), `js/icons.js`
- `css/components.css`
- `index.html` (only if a new file)
- `tests/browser/test_ui_*_contract.py` (several), new `tests/browser/test_ui_clearable_input_contract.py`, `tests/test_design_tokens_a11y.py`
- `docs/ui-control-inventory.md`
- The flight log

## Citation Audit
Checked at `332496d` on 2026-10-22 (FD read), corrected at the design review (Sonnet Developer, cycle 1: approve with changes): the copy feedback text; the warning chip mirrors danger, with its gated pair; the clearable layout is new; the menu has no gap; the `editor.js` lines (`apply` about `:133`, `setBusy` about `:170`). The FD read covered:
- `feedback.js:145-215`: status options include `led`/`live`/`role`/`ledLabel`; chip has no `dataset` and the tones neutral and danger only;
- `editor.js:42-63,69,101,133,160-169`;
- `copy.js:84-100`;
- `menu.js:11-35,104-108`;
- `knowledge-section.js:679-762`;
- `icons.js`: 36 icons, no ellipsis.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
