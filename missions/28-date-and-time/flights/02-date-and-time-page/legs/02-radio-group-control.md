# Leg: radio-group-control

**Status**: completed
**Flight**: [The Date and Time Page](../flight.md)

## Objective

Add `App.ui.radioGroup`, a native-radio group factory in the control library,
with its Design language demo, its inventory row and engine-parametrized
contract tests. The Date and time page (leg 3) uses it for its "system /
choose a zone" choice.

## Context

- Read [flight.md](../flight.md) **DD3** (shape, structure, placement, guard
  rules).
- CLAUDE.md "Control library (`App.ui`)" requires three things of every new
  factory: a demo on the dev-mode `#settings/design-language` page, a row in
  `docs/ui-control-inventory.md`, and contract tests in Chromium and WebKit.
  `tests/test_ui_control_inventory.py` enforces the first two.
- **Reference implementation:** `static/js/ui/choice.js::build()` (~9-44).
  It shows:
  - the label wraps the input plus text;
  - the hint is a **sibling**, wired by `aria-describedby`;
  - `data-ui-own-label`;
  - the test id goes on the native input;
  - `util.el` / `util.uid`.
- It is independent of leg 1 and touches none of its files.
- **Host rule:** browser runs use `THE_ONE_TEST_NETNS=1`, plus
  `THE_ONE_REQUIRE_WEBKIT=1` for the contracts lane.

## Inputs

- Branch `flight/02-date-and-time-page`, after leg 1 (uncommitted).
- `static/js/ui/choice.js`, `static/js/areas/admin/design-language/ui-choices-section.js`.
- `docs/ui-control-inventory.md` (~52-60, "Choices and toggles").
- `tests/browser/test_ui_choice_contract.py`, the pattern (`load_harness`,
  `_mount`, `_throws`, `assert_controls_labelled_and_described`).

## Outputs

- `static/js/ui/choice.js`: `App.ui.radioGroup`.
- `static/css/components.css`: `.ui-radio-group` / `.ui-radio-option` rules,
  plus a forced-colors rule if the neighbours have one.
- `ui-choices-section.js`: a radio-group demo (two options with descriptions;
  one with a slot child).
- `docs/ui-control-inventory.md`: a new 5-cell row, `Radio group (native,
  App.ui.radioGroup)`.
  - Its status cell is exactly `library: App.ui.radioGroup`.
  - It goes after "Toggle, library" and before the legacy toggle rows.
  - All columns are filled, with no stray `|`. The existing "Radio group (theme …)" row keeps
  its `not yet defined` status, with a note "theme toggle migrates to
  App.ui.radioGroup later".
- `tests/browser/test_ui_radio_group_contract.py` (new, contracts lane).
- `the_one/agents.md`: one line in "Control library (`App.ui`)" listing the
  factory.
- The flight log: the leg entry.

## Acceptance Criteria

- [ ] **AC1. Signature.** `App.ui.radioGroup(opts)` takes
      `{legend (required), legendHidden, name, value, options: [{value
      (required), label (required), description, testid, disabled}], onChange,
      testid}`.
  - It throws `'App.ui.radioGroup: legend is required'` without a legend.
  - It throws when `options` is empty, or an option lacks `value`/`label`.
  - It returns `{el, value(), setValue(v), setDescription(value, text),
    optionEl(value), input(value), focus(), destroy()}`.
    - `input(value)` returns that option's native input, or `null`.
    - `focus()` focuses the checked input, or the first enabled input.
  - Duplicate option values throw `'App.ui.radioGroup: duplicate value'`.
  - An explicit shared `name` across two groups is the caller's problem; the
    factory comment says so.
- [ ] **AC2. Structure** (DOM APIs only, no HTML-sink tokens anywhere in the
      file, comments included):
  - `el` is `fieldset.ui-radio-group`, carrying `data-testid` from
    `opts.testid` when given;
  - then `legend` (class `visually-hidden` when `legendHidden`);
  - then, per option, `div.ui-radio-option` holding three siblings:
    1. `label.ui-radio-label` wrapping `input[type=radio].ui-radio-input`
       (`name` = `opts.name || util.uid('radio')`, `value`, `id` from
       `util.uid`, `data-ui-own-label`, and the option's `testid` **on the
       input**) and `span.ui-radio-text` (the label);
    2. `div.field-hint.ui-radio-description`, only when `description` is
       given, with an `id`, and the input's `aria-describedby` pointing at it;
    3. `div.ui-radio-slot`, empty.
  - The option wrapper gains `.is-checked` when its input is checked, and
    `.is-disabled` when the option is disabled.
    - `.is-checked` is a fallback for `:has()`.
    - On **every** change, and on every `setValue`, **all** options are
      re-synced: native radios fire `change` only on the newly checked input,
      so syncing one wrapper would leave a stale class.
  - **One delegated `change` listener** sits on the fieldset (no per-input
    listeners). `destroy()` removes it and does not remove `el`, which the
    caller owns.
- [ ] **AC3. Behaviour.**
  - `value()` returns the checked option's value, or `null`.
  - `setValue(v)` checks that option (or clears all for `null`), syncs
    `.is-checked` and **does not** call `onChange`.
  - A user change (click, Space, or an arrow key, the browser's native radio
    behaviour) calls `onChange(value)` exactly once per change.
  - `setDescription(value, text)` sets that option's description text,
    creating and wiring the element if it was absent.
  - `optionEl(value)` returns the option's slot div, or `null` for an unknown
    value.
  - `destroy()` removes the delegated listener. It is verified behaviourally:
    after `destroy()`, a click or arrow key no longer calls `onChange`.
    (`test_ui_listener_cleanup.py` only instruments document, window and
    body, and is unaffected.)
  - **`setValue` with an unknown value** is a no-op. With `null` it clears.
    Targeting a disabled option leaves the group unchanged.
  - **`setDescription(value, text)`:**
    - an unknown value returns silently;
    - an empty `text` removes the description element and the input's
      `aria-describedby`;
    - a non-empty text creates the element if needed, with a `util.uid` id,
      and wires it.
- [ ] **AC4. Styling** (`components.css`, using tokens only, which
      `tests/test_token_definitions.py` checks):
  - the fieldset reset: `border: 0; padding: 0; margin: 0; min-inline-size: 0`.
    It gets **no `display: flex`** (WebKit fieldset layout risk); option
    spacing is `.ui-radio-option + .ui-radio-option { margin-block-start:
    var(--space-2) }`.
  - **The legend:** the hidden case uses the global `.visually-hidden`
    (`components.css:~33`). The visible case gets `padding: 0`, a
    `margin-block-end`, `--font-size-body` and `--font-weight-medium`.
  - each option is a card: `1px solid var(--border)`, `var(--radius-md)`,
    padding about `12px 14px`, background `var(--surface)`;
  - the checked card (`.ui-radio-option:has(.ui-radio-input:checked)`, plus
    `.is-checked`) has border `var(--accent)` and background
    `var(--accent-translucent)`;
  - the input has `accent-color: var(--accent-fill)` and an explicit
    `:focus-visible` outline of `2px solid var(--accent)` with
    `outline-offset: 2px`;
  - the description is `--font-size-caption`, colour `--fg-muted`, **unless**
    the new a11y pair below fails, in which case it uses `--fg-secondary`. The
    flight log records which.
  - a disabled option is dimmed, with `cursor: not-allowed`;
  - **A mandatory `@media (forced-colors: active)` rule**, modelled on the
    toggle's (`components.css:~1997-2001`): the checked card gets
    `border-color: Highlight` and a 2px border (or an outline), and a disabled
    option `GrayText`.

  **The a11y token gate** (`tests/test_design_tokens_a11y.py`) gains firm
  pairs, in the style of its translucent composite tests (~371-397), for both
  themes at 4.5:1:
  - the description colour on `--accent-translucent` composited over
    `--surface` (the checked card);
  - `--fg` on the same composite;
  - the description colour on `--surface` (the unchecked card).
- [ ] **AC5. The demo.** `ui-choices-section.js` gains exactly **one**
      `d.demo(host, 'radioGroup', function (pane) { … })` call, whose id is the
      factory name. `test_ui_control_inventory.py::test_every_factory_is_demonstrated_in_source`
      and `test_ui_reference_page.py::test_every_factory_has_exactly_one_demo_root`
      require this.
  - The demo has two options with descriptions, the second holding a small
    slot child (a text line).
  - It passes **no `testid` and no `name`**: `ui-demo.js` builds dark and light
    panes, and the two groups rely on `util.uid` names.
  - The section's header comment gains the radio group. `tests/browser/test_ui_reference_page.py`
      or any Design language guard still passes.
      `tests/test_ui_control_inventory.py` passes, with the section count
      unchanged at 9 because no new section file is added.
- [ ] **AC6. Contract tests** (`tests/browser/test_ui_radio_group_contract.py`):
  - **Engines:** Chromium and WebKit, through `engine_page` and
    `load_harness`.
  - **Structure:** the fieldset, the legend's accessible name, each radio's
    accessible name equal to its label text only (not the description or the
    slot), the description wired by `aria-describedby`, and
    `assert_controls_labelled_and_described`.
  - **Keyboard,** on a 3-option group with an initial `value` set:
    - Tab from a start button (the positive-control pattern of
      `test_ui_choice_contract.py:~498-523`) leaves the button and lands on the
      checked radio. If an engine's Tab skips radios, use `group.focus()` as a
      fallback and note it in the test.
    - ArrowDown and ArrowUp move the selection, with `onChange` once per move.
    - Space on a focused unchecked radio checks it.
    - The Tab target of an unchecked group is not asserted (engine-specific).
    - Locate with `getByRole('group', {name: legend})` and
      `getByRole('radio', {name: label})`.
  - **`.is-checked`:** after each arrow move, exactly one wrapper has
    `.is-checked`.
  - **Forced colors:** a test modelled on
    `test_forced_colors_keep_state_distinguishable` (~652) proves the checked
    card stays distinguishable.
  - **API semantics:** `setValue` is silent; `value()` is correct;
    `setDescription` works; `optionEl` returns the slot, and putting a button
    into the slot leaves the radio's accessible name unchanged.
  - **Two groups** mounted without a `name` don't interfere.
  - **Focus ring:** outline of 2px or more on keyboard focus.
  - **Destroy:** listeners are removed and `onChange` no longer fires.
  - **Validation:** the throws from AC1, including duplicate values.
  - **The file:** `# ruff: noqa: E501`, `pytestmark = pytest.mark.browser`, and
    the `test_ui_*` name (contracts lane; no `run-tests.sh` change).
- [ ] **AC7.** The static guards pass:
  - **`tests/test_ui_guards.py`, with its strict rules for `ui/*.js`:**
    - no sink token anywhere, comments included;
    - any `testid:` or `<x>Testid:` token, comments included, must be an
      identifier chain ending `.testid`. Forward an option's id through a local
      (`var o = opts.options[i]; … o.testid`), never `opts.options[i].testid`,
      and never write `testid:` in a doc comment;
    - use `setAttribute('data-testid', o.testid)`;
  - the rest: `tests/test_token_definitions.py`,
      `tests/test_design_tokens_a11y.py`, `tests/test_ui_control_inventory.py`.
      `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python TEST_TIMEOUT=1200 bash scripts/run-tests.sh --lane contracts`
      is green, and the flight log records its wall time against the 270 s
      budget.
- [ ] **AC8.** `agents.md` lists `App.ui.radioGroup` in the control library
      section, with its contract in one or two sentences.

## Verification Steps

- **AC1-AC3, AC6:** `… bash scripts/run-tests.sh tests/browser/test_ui_radio_group_contract.py -x` (with the netns and WebKit env).
- **AC4, AC5, AC7:** the guard commands and the contracts lane.
- **AC8:** read the diff.

## Implementation Guidance

1. Add the factory below `App.ui.toggle` in `choice.js`, reusing `util.el` and
   `util.uid`. Do not refactor `build()`; the radio's structure differs (a
   wrapper card holding three siblings).
2. Track listeners in an array so `destroy()` can remove them.
3. Add the CSS next to the existing `.ui-checkbox` / `.ui-toggle` rules.
4. Add the demo, the inventory row and the tests, then run the contracts lane.

## Edge Cases

- **`value` not among the options** at construction: none is checked, and
  `value()` returns `null`.
- **A disabled option** cannot be checked by `setValue`; return it unchanged
  and log nothing.
- **Arrow keys skip a disabled radio**: native behaviour, which the tests
  note but don't fight.

## Files Affected

- `static/js/ui/choice.js`, `static/css/components.css`.
- `static/js/areas/admin/design-language/ui-choices-section.js`.
- `docs/ui-control-inventory.md`, `the_one/agents.md`.
- `tests/browser/test_ui_radio_group_contract.py` (new), and possibly
  `tests/browser/test_ui_listener_cleanup.py`.
- The flight log.

## Citation Audit

Checked at `a9c8da5`:

- `choice.js:9-44`, `build()` (label wraps the input; hint sibling with
  `aria-describedby`; testid on the input).
- `docs/ui-control-inventory.md:52-60`.
- The `test_ui_choice_contract.py` helper pattern.

Section count 9 and the status-cell regex: per the Architect's second pass
(`test_ui_control_inventory.py:~55-64, ~96`).

---

## Post-Completion

Completion steps are Flight Control protocol, driven by the execution
workflow. They are not repeated here.
