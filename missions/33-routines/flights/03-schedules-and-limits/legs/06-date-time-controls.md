# Leg: date-time-controls

**Status**: completed
**Flight**: [Schedules and Limits](../flight.md)

## Objective

Add the three library controls leg 7's recurrence form needs (flight DD7):
`App.ui.datePicker` (a typed date with a calendar popover), `App.ui.timeField`
(a typed time shown in 12-hour form) and circular S M T W T F S day toggles.
Each control follows the control-library rules: a factory in `js/ui/`, a
catalogue row in `docs/ui-control-inventory.md`, owned CSS classes, and
engine-parametrized contract tests (Chromium and WebKit). Nothing in the app
uses them yet.

## Context

- **Independent of legs 2-5.** This leg touches only `static/js/ui/`,
  `static/css/components.css`, `static/index.html` (script tags, if a new
  file is added), `docs/ui-control-inventory.md` and new
  `tests/browser/test_ui_*` files. Other Developers are editing backend and
  `areas/studio/` files in the same tree at the same time; do not touch
  those.
- **Library rules** (CLAUDE.md "Control library (`App.ui`)"): ES5, native
  elements, no HTML-string sinks, a caller-supplied `testid`; every factory
  needs an inventory row and a `tests/browser/test_ui_*.py` that calls
  `App.ui.<name>(`; `tests/test_ui_control_inventory.py`,
  `tests/test_ui_ownership.py`, `tests/test_ui_emitted_classes.py` and
  `tests/test_ui_guards.py` enforce them. Disabled states use the opaque
  `--btn-disabled-*` tokens, never `opacity`. Colours come from
  `tokens.css`; any new token pair goes through
  `tests/test_design_tokens_a11y.py`. No `document` listeners from a factory
  (the shell owns the one Ctrl K listener) — an outside-click close must be
  scoped (listen while open, on the owner document, and remove on close and
  on destroy; check how `App.ui.menu` does it and follow that pattern, since
  `test_ui_listener_cleanup.py` checks cleanup).
- **"Today" and the zone.** Library factories may not read `App.time` (the
  library-globals guard allows only `App.ui` and `App.icons`), so "today" is
  supplied by the caller: a `today` option, a function returning the
  operator-zone date as "YYYY-MM-DD" (leg 7 builds one on `App.time`).
  Without it there is no today mark, and a year-less typed date takes its
  year from the value, else `min`, else is unreadable. Never the `Date`
  getters (only `time.js` may call them, a guarded rule). (Spec corrected
  after the library-globals guard failed on the first draft.)
- **Inside a modal.** Leg 7 puts a date picker in the "Custom recurrence"
  `App.ui.modal`. The modal handles Escape on keydown on the `<dialog>` with
  `preventDefault` and `stopPropagation` (`js/ui/modal.js`). The picker's
  open calendar must take Escape first (its own keydown handler with
  `stopPropagation`), close the calendar and return focus to its button,
  leaving the modal open. A second Escape closes the modal.

### `App.ui.datePicker(opts)`

- Options (suggested): `label` (visible, or `ariaLabel`), `value`
  ("YYYY-MM-DD" or null), `min`, `max` (ISO dates), `onChange(iso)`,
  `testid`, `disabled`, `describedBy`.
- A text input that shows the value as "Thu, Oct 29, 2026" and accepts what
  people type: ISO "2026-10-29", "10/29/2026", "10/29" (this year), "Oct 29,
  2026", "Oct 29", and the displayed form. Parsed on blur and on Enter;
  re-shown in the display form. An unreadable or out-of-range entry keeps the
  text, sets `aria-invalid="true"` and shows one sentence ("Enter a date
  like Oct 29, 2026." / "Choose a date on or after Oct 29, 2026."),
  linked by `aria-describedby`; `value()` returns null until fixed.
- A button beside it ("Choose date", icon only with an accessible name;
  `aria-haspopup="dialog"`, `aria-expanded`) opens a calendar popover: a
  non-modal `role="dialog"` with a label naming the month, previous and next
  month buttons, and a month grid (`role="grid"`, column headers Su Mo Tu We
  Th Fr Sa with full-name abbreviations, Sunday first) of day buttons with
  `aria-selected` on the value, `aria-current="date"` on today, and
  disabled days outside `min`/`max`.
- Keyboard in the grid: arrows move a day or a week; Page Up/Down a month;
  Shift+Page Up/Down a year; Home/End the start/end of the week; Enter or
  Space picks; Escape closes and returns focus to the button. Opening moves
  focus to the selected day (or today, or `min`); roving `tabindex`.
- Picking sets the input, fires `onChange`, closes the popover and returns
  focus to the button. A click outside closes it.
- Handle: `{el, input, value(), setValue(iso), setMin(iso), setMax(iso),
  setDisabled(bool), focus(), destroy()}`; `setValue` is silent (no
  `onChange`), like the other controls.

### `App.ui.timeField(opts)`

- Options: `label`/`ariaLabel`, `value` ("HH:MM" 24-hour or null),
  `onChange(hhmm)`, `testid`, `disabled`, `describedBy`.
- A text input that shows "9:30 AM" and accepts "9:30 AM", "9:30am",
  "9:30 a", "9:30p", "21:30", "0930", "930pm", "9 am", "9pm", "12 pm"
  (noon) and "12 am" (midnight). Parsed on blur and Enter; re-shown as
  12-hour (M25 DD14). An unreadable entry: `aria-invalid`, "Enter a time
  like 9:30 AM.", `value()` null.
- Handle: `{el, input, value(), setValue(hhmm), setDisabled(bool), focus(),
  destroy()}`.

### Day toggles

- Seven circular toggles S M T W T F S in a fieldset whose legend is the
  caller's ("Repeat on"), **native checkboxes**: each has an accessible name
  of the full day ("Sunday") while showing the letter (the letter
  `aria-hidden`, the full name visually hidden). Checked state is visible
  without colour alone (fill plus a contrast change), with a visible focus
  ring.
- Preferred: an `App.ui.checkboxGroup` option (for example `variant:
  'days'` or `layout: 'circles'`) that changes only layout and styling, so
  `value()`/`setValue` keep their contract; a new factory only if the
  variant does not fit, recorded in the flight log.
- The caller supplies the options and values. The app's day values are
  0 = Monday … 6 = Sunday, shown Sunday first; leg 7 passes them in that
  order, so the control itself knows nothing about weekday numbering.

## Inputs

- Flight spec DD7 (controls).
- `static/js/ui/` (`choice.js` for `checkboxGroup`, `menu.js` for the
  outside-click and listener-cleanup pattern, `field.js` for labels and
  error text, `modal.js` for Escape), `static/js/time.js`,
  `static/css/components.css`, `static/css/tokens.css`,
  `docs/ui-control-inventory.md`, existing contract tests
  (`tests/browser/test_ui_checkbox_group_contract.py`,
  `test_ui_menu_contract.py`, `_ui_engines.py`).

## Outputs

- The two new factories (in a new `js/ui/` file or files, with script tags
  in `index.html` in library order) and the checkbox-group variant; CSS in
  `components.css`; inventory rows (owned classes, options, the caller-supplied
  testid scheme for inner parts, e.g. `{testid}-input`, `{testid}-button`,
  `{testid}-calendar`, `{testid}-day`).
- `tests/browser/test_ui_date_picker_contract.py`,
  `test_ui_time_field_contract.py`, and day-toggle cases added to
  `test_ui_checkbox_group_contract.py`, each engine-parametrized.
- Flight log entry.

## Acceptance Criteria

- [ ] AC1. `App.ui.datePicker`: typed input parses every listed form and
      shows the display form; invalid and out-of-range input is flagged
      with `aria-invalid` and its sentence and `value()` is null; the
      calendar opens from the button, shows the right month with today
      (from the caller's `today` option) and the selected day marked, disables days outside
      `min`/`max`, and every listed key works; picking updates the input,
      fires `onChange` once, closes and returns focus; outside click closes;
      `setValue` is silent; `destroy()` removes every listener.
- [ ] AC2. Inside an `App.ui.modal`, Escape with the calendar open closes
      only the calendar (the modal stays open, focus on the picker's
      button); the next Escape closes the modal.
- [ ] AC3. "Today" is supplied by the caller (`today` option, built on
      `App.time` by the caller) and follows the operator zone: with a zone
      whose date differs from the host's, the calendar's today mark and
      start day use that date; without `today` there is no mark and a
      year-less entry needs a year from the value or `min`.
- [ ] AC4. `App.ui.timeField` parses every listed form, shows 12-hour
      text, flags invalid input, `value()` returns "HH:MM" or null,
      `setValue` is silent.
- [ ] AC5. Day toggles: seven native checkboxes in a fieldset with the
      caller's legend, each named by its full day, showing its letter;
      `value()`/`setValue` unchanged; checked state visible in both themes
      without relying on colour alone; focus ring visible.
- [ ] AC6. Inventory rows exist for both new factories and the variant;
      `tests/test_ui_control_inventory.py`, `test_ui_ownership.py`,
      `test_ui_emitted_classes.py`, `test_ui_guards.py`,
      `test_token_definitions.py` and `test_design_tokens_a11y.py` pass.
- [ ] AC7. The contract tests pass in both engines:
      `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane contracts-controls`
      (and `contracts-overlay` if a new test file lands there by glob).
- [ ] AC8. No file outside `static/js/ui/`, `static/css/components.css`
      (and `tokens.css` only if a token is needed), `static/index.html`,
      `docs/ui-control-inventory.md`, the new or extended
      `tests/browser/test_ui_*` files and the flight log is modified.

## Verification Steps

- AC1-AC5: the contract tests, both engines.
- AC6: the unit-tier guards (`PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_ui_control_inventory.py tests/test_ui_ownership.py tests/test_ui_emitted_classes.py tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py -x --timeout 60`).
- AC7: the lane command (alone, never beside the unit suite or another
  lane).
- AC8: `git status` over the leg's paths.

## Edge Cases

- A `min` later than the current value (an edit of a past start, leg 7):
  the picker shows the value, marks it invalid only if the caller asks
  (`min` is the caller's choice, see the flight's DD7 `min` rule).
- Month navigation across year boundaries and February in leap years.
- Two pickers on one page (the form's start and the modal's "ends on"):
  ids unique, popovers independent.
- WebKit focus quirks with buttons inside a popover (prior flights hit
  WebKit focus-after flakes: squawk 0276). Prefer explicit `focus()` after
  render.

## Files Affected

- New `static/js/ui/date-time.js` (suggested name) or two files;
  `static/js/ui/choice.js` (variant); `static/css/components.css`;
  `static/index.html`; `docs/ui-control-inventory.md`;
  new `tests/browser/test_ui_date_picker_contract.py`,
  `test_ui_time_field_contract.py`; `test_ui_checkbox_group_contract.py`.

## Citation Audit

Checked at `49a5051a`:
- `js/ui/choice.js` `App.ui.checkboxGroup` (legend required, options
  `{value, label, disabled, testid}`); inventory row for the checkbox group
  — verified.
- `js/ui/modal.js`: native `<dialog>`, Escape handled on keydown on the
  dialog with `preventDefault` and `stopPropagation`, `cancel` prevented —
  verified.
- `js/time.js` `parts(d)`, `formatDate` — verified.
- CSS files `components.css`, `tokens.css` — verified.
