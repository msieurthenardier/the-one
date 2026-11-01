# Leg: recurrence-form

**Status**: completed
**Flight**: [Schedules and Limits](../flight.md)

## Objective

Rebuild the Routines tab's create/edit form on the calendar recurrence, in
the Google Calendar pattern (flight DD7): a start date and time, a "Repeat"
preset select computed from the start date, a "Custom recurrence" dialog,
a server preview line with warnings, and a canonical-shape save. It replaces
leg 4b's read-only stopgap, so every recurrence the backend stores can be
created and edited from the form.

## Context

- **Prior legs:** leg 4 (4a and 4b) switched the backend to the DD1 shape,
  added `POST /api/agents/{name}/routines/preview` (`{schedule}` →
  `{schedule, anchor_at, text, next_runs, last_occurrence, warnings}`, the
  create route's 422 on refusal), `schedule_text` on routine views, and a
  minimal adapter in `routines-form-model.js::bodyToFormState` that opens
  shapes the old form cannot express as read-only. Leg 6 added
  `App.ui.datePicker` (with a caller-supplied `today` option),
  `App.ui.timeField` and `App.ui.checkboxGroup({variant: 'days'})`. Read
  the flight log entries for legs 4 and 6 first.
- **The form today** (`static/js/areas/studio/routines-form.js`, 419 lines,
  and `routines-form-model.js`): a five-kind Schedule `radioGroup`, a
  shared hour/minute/AM-PM select row, a weekly `checkboxGroup`, a nested
  Once "In"/"At" group with a 60-day day select, an interval hours input,
  then the target group. Save sends only changed fields (`formToBody`
  diffs). `areas/studio/routines-describe.js` keeps target and time
  formatting.
- **The new form** (DD7):
  - **Name**, **Prompt** unchanged.
  - **Starts:** `App.ui.datePicker` (testid `routine-form-start-date`) and
    `App.ui.timeField` (`routine-form-start-time`), defaulting to the next
    whole hour in the operator zone. The picker's `today` option returns the
    operator-zone date from `App.time`; its `min` is today for a new routine
    and the earlier of today and the stored start when editing. A quick
    "In … minutes/hours/days" (amount + unit, `routine-form-in-amount`,
    `routine-form-in-unit`, kept testids) sets the start fields from now
    plus the amount (rounded up to the minute) — or, if simpler, is sent as
    the relative start `{"in": …}`; the leg designer's preference is to fill
    the fields, so what is saved is what is shown.
  - **Repeat:** an `App.ui.select` (`routine-form-repeat`) of presets
    computed from the start date: "Does not repeat"; "Every day"; "Every
    weekday (Monday to Friday)"; "Weekly on {weekday}"; "Monthly on day
    {d}"; "Monthly on the {first|second|third|fourth} {weekday}" when the
    date's nth is 1-4; "Monthly on the last {weekday}" when the date is in
    the month's last 7 days; "Annually on {Month} {d}"; "Custom…". The
    presets recompute when the start date changes; a selected preset keeps
    its meaning (e.g. "Weekly on Thursday" follows to the new weekday, as
    Google does). An edited routine whose recurrence matches no preset shows
    its server sentence as an extra selected option above "Custom…".
  - **Custom…** opens `App.ui.modal` titled "Custom recurrence"
    (`routine-custom`): "Repeat every" (`routine-custom-every`, a number,
    and `routine-custom-unit`, a select: minutes, hours, days, weeks,
    months, years — singular/plural labels follow the number); "Repeat on"
    (`routine-custom-days`, the `days` variant, weeks only, the start's
    weekday preselected; values 0 = Monday … 6 = Sunday, passed Sunday
    first); a month choice (`routine-custom-month-by`, a radio group: "On
    day {d}" / "On the {nth} {weekday}" / "On the last {weekday}" when it
    applies; months only); "Ends" (`routine-custom-ends`, a radio group:
    Never / On {`App.ui.datePicker`, `routine-custom-ends-date`} / After
    {number, `routine-custom-ends-count`} occurrences); Cancel and Done
    (`routine-custom-cancel`, `routine-custom-done`). Done validates the
    numbers against the DD1 ranges (field errors in the dialog), applies to
    the form and closes; Cancel discards; Escape with the ends calendar open
    closes only the calendar (leg 6 contract). Focus returns to the Repeat
    select.
  - **Preview line** (`routine-form-preview`) under Repeat: the server's
    `text`, the next run, and the last occurrence when the series ends
    ("Next: Fri, Oct 30 at 9:00 AM · Last: Jan 28, 2027"), fetched through
    the preview route, debounced (about 300 ms) on any schedule change, with
    `App.ui.util.latest()` so only the latest response applies; a 422 shows
    its sentence as the schedule field's error (`routine-form-schedule-error`,
    kept). It is a polite status, not an alert, and does not move focus.
  - **Warnings** (`routine-form-schedule-hint`): the preview's `warnings`
    shown as a field hint linked to the Repeat select by `aria-describedby`.
  - **Target** unchanged.
  - **Save** sends the canonical schedule (start `{date, time}`, `repeat`,
    `ends`) when the schedule changed (the diff rule stays), never a legacy
    shape. A 422 maps to fields through `App.api.fieldErrors` as today.
- **Retired:** the Schedule radio group, the shared time selects, the Once
  "In"/"At" group, the 60-day select, the interval input and leg 4b's
  read-only note. Their testids (`routine-form-schedule`, `-hour`,
  `-minute`, `-ampm`, `-at-day`, `-at-hour`, `-at-minute`, `-at-ampm`,
  `-once-mode`, `-interval`, `-days`, `routine-form-day-*`) move to the
  registry's "Retired testids" table and `RETIRED_SELECTORS`
  (`tests/test_nav_helper.py`); new testids are registered in
  `docs/ui-testid-registry.md`. Keep a testid only where the element keeps
  its meaning.
- **Module size:** `routines-form.js` will outgrow its limit with the Custom
  dialog; put the dialog in its own module (suggested
  `areas/studio/routines-custom-recurrence.js`, script tag in `index.html`)
  and the preset computation in `routines-form-model.js` (pure, testable).
  `tests/test_area_module_size.py` must pass.
- **Dates without the `Date` getters:** weekday, nth and "last week of the
  month" come from `App.time` parts or pure arithmetic on "YYYY-MM-DD";
  only `time.js` may call the `Date` getters (`tests/test_time_getters_static.py`).
  If a helper is needed (days in a month, weekday of an ISO date), add it to
  `App.time` with a unit or contract test.
- **Lane:** the form's browser tests are in `agent-routines`
  (`test_flow_agent_routines*`). The lane's budget is 240 s (measured 171 s);
  if the rewritten form tests push it over 1.3x, record it for leg 8's
  re-budget rather than trimming coverage.

## Inputs

- Flight spec DD1, DD2 (the nth/last rule), DD7; legs 4 and 6 in the flight
  log; the leg 6 inventory rows.
- `static/js/areas/studio/routines-form.js`, `routines-form-model.js`,
  `routines-describe.js`, `routines-tab.js`, `static/js/ui/` (the new
  controls, `modal`, `select`, `radioGroup`, `field`),
  `static/js/time.js`, `static/index.html`.
- `tests/browser/test_flow_agent_routines_form.py`,
  `test_flow_agent_routines.py`, `docs/ui-testid-registry.md`,
  `tests/test_nav_helper.py`.

## Outputs

- The rebuilt form, the Custom dialog module, the preset model; updated and
  new browser tests; registry and retired-selector updates; a short
  `the_one/agents.md` note on the form (replacing the five-kind form's
  description in "Routines (M33)") and the CLAUDE.md Routines paragraph's
  form wording if it names the old fields.
- Flight log entry.

## Acceptance Criteria

- [ ] AC1. Creating a routine with each preset from a chosen start date
      (Does not repeat, Every day, Every weekday, Weekly on {weekday},
      Monthly on day {d}, Monthly on the {nth} {weekday}, Monthly on the
      last {weekday}, Annually) saves the canonical schedule the preset
      means; the routine row shows the server sentence and next run.
- [ ] AC2. The preset list follows the start date (weekday, day, nth, the
      "last" option only in the month's final 7 days); changing the date
      keeps the chosen preset's meaning.
- [ ] AC3. The Custom dialog round trip: every N minutes/hours/days/weeks
      (with days)/months (by day and by weekday)/years, and each Ends choice,
      applies to the form on Done, is discarded on Cancel, validates its
      ranges with field errors, and returns focus to the Repeat select;
      Escape with the ends calendar open closes only the calendar.
- [ ] AC4. The preview line shows the server's sentence, next run and last
      occurrence, updates after a schedule change (latest response wins),
      shows a refusal ("This schedule has no runs left.") as the schedule
      error, and shows the month-day warning as a hint described-by the
      Repeat select.
- [ ] AC5. Editing an existing routine of every unit (including one that
      leg 4b opened read-only) shows its start, its preset or its sentence as
      an extra option, and saves only changed fields; an untouched schedule
      is not re-sent.
- [ ] AC6. The "In …" quick start sets the start date and time from now
      plus the amount in the operator zone; the picker's "today" follows the
      operator's time-zone setting (a test with an operator zone whose date
      differs from the host's).
- [ ] AC7. Retired testids are in the registry's retired table and
      `RETIRED_SELECTORS`; new testids are registered; `tests/test_nav_helper.py`,
      `tests/test_ui_testid_registry*.py` (whatever pins the registry) and
      `tests/test_area_module_size.py` pass.
- [ ] AC8. Static guards pass (`test_ui_guards.py`,
      `test_token_definitions.py`, `test_design_tokens_a11y.py`,
      `test_time_getters_static.py`, `test_ui_ownership.py`);
      `THE_ONE_TEST_NETNS=1 make test-unit` passes (15 skipped); the
      `agent-routines` lane passes, with its wall time reported (not a
      budget reading).

## Verification Steps

- AC1-AC6: browser tests in `tests/browser/test_flow_agent_routines_form.py`
  (and a new file if it grows past the lane's grouping, still matching
  `test_flow_agent_routines*`).
- AC7-AC8: the named unit tests and the lane:
  `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane agent-routines`.

## Edge Cases

- A start date of the 29th-31st and "Monthly on day {d}": the warning
  appears; February's preview skips.
- A start time in the spring-forward gap: the preview's next run is at the
  end of the gap; the form keeps the typed time.
- Switching from a weekly Custom recurrence back to a preset, and back to
  Custom: the dialog reopens with the current recurrence, not defaults.
- A one-off whose start is in the past (editing an old routine): the
  preview refuses it; Save shows the refusal on the schedule.
- Two date pickers on the page (start, ends-on): independent.

## Files Affected

- `static/js/areas/studio/routines-form.js`, `routines-form-model.js`, new
  `routines-custom-recurrence.js`, possibly `routines-describe.js`,
  `routines-tab.js`; `static/index.html`; possibly `static/js/time.js`
- `tests/browser/test_flow_agent_routines_form.py` (and any new form test
  file), `test_flow_agent_routines.py` if it opens the form
- `docs/ui-testid-registry.md`, `tests/test_nav_helper.py`
- `the_one/agents.md`, CLAUDE.md, the flight log

## Citation Audit

Checked at `54d87b8a` (Batch A); leg 4 changes these files and the leg's
Developer re-reads them:
- `routines-form.js`: `KIND_OPTIONS`, `TARGET_OPTIONS`, `timeRow`,
  `App.ui.checkboxGroup` for days, the 60-day "At" select — verified.
- `routines-form-model.js`: `defaultState`, `scheduleBody`, `formToBody`
  (diff), `bodyToFormState`, `dayOptions`, `precheck` — verified.
- `docs/ui-testid-registry.md` `routine-form-*` rows — verified.
- Leg 6's `App.ui.datePicker` `today` option and `checkboxGroup`
  `variant: 'days'` — verified (flight log, Batch A commit).
