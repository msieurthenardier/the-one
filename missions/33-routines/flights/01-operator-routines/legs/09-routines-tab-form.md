# Leg: routines-tab-form

**Status**: completed
**Flight**: [Operator Routines, End to End](../flight.md)

## Objective

The operator creates and edits routines on the Routines tab. One inline form
covers the name, the prompt, all five schedule kinds and the three target
kinds, and lets the operator choose an existing chat from a searchable list of
the agent's chats. One-off "At" times are entered in the operator's zone and
converted on the server. Weekday selection uses a new
`App.ui.checkboxGroup` control.

## Context

- Flight DD12 (second half), DD2 and DD9. This is part 8b of the original
  leg 8, split at design review.
- **Leg 8 hands this leg a form hook.**
  - The `routines-new-btn` and `routine-edit` buttons call
    `callbacks.openRoutineForm({mode, routine, opener})` once
    `App.studio.routinesForm` exists.
  - `routines-describe.js` is shared.
- **One-off "At" (design decision, design review).** The client has no
  zone-local-to-UTC converter, and `time.js` is the only module that may call
  `Date` getters. The server already owns the operator zone and the DST
  rules, so the server accepts a local date and time for `once`:
  - **Request.** `{"kind": "once", "on": {"date": "YYYY-MM-DD", "time": "HH:MM"}}`
    is a third input form beside `at` and `in`.
  - **Conversion.** The server converts with leg 1's wall-clock resolver (a
    gap gives the gap's end, a repeated time gives its first occurrence) in
    the effective zone, then stores `at`. The same past and one-year bounds
    apply.
  - **Where it lives.** This is a small server change in
    `the_one/routines/schedule.py` or `api.py`, made in this leg.
- **The chooser shows all of the agent's chats** *(autonomous judgement
  call)*, including routine run chats and connector chats.
- **Unsaved form text.** It is held locally and discarded on Cancel or on
  leaving the tab *(autonomous judgement call, as for Rules)*.

## Inputs

All paths are under `the_one/interfaces/web/static/js/` unless they start
with `the_one/`.

**Library controls (`ui/`):**
- `ui/choice.js`:
  - `App.ui.radioGroup(opts)`: `legend` is required, and `name` should be
    passed explicitly when groups nest. `optionEl(value)` returns that
    option's `.ui-radio-slot`, an empty slot for revealed fields.
  - `App.ui.checkbox`.
- `ui/field.js`: `App.ui.select` (`:87`), `App.ui.textInput` (with
  `type: 'number'`) and `App.ui.field`.
- `App.ui.modal({layout: 'chooser'})` and `App.ui.searchList`, as used by
  `areas/chat/agent-picker.js`. The pick runs from the modal's `onClose`,
  after focus returns.

**Shared helpers:**
- `App.api.fetchJson`, `App.api.fieldErrors`.
- `App.store.get('sessions')`. It is only WebSocket-primed while Chats is
  open, so call `get` when the chooser opens. Rows are
  `{id, agent_name, title, created_at, updated_at, platform, busy, turn_seq}`.
- `App.chat.chatsList.platformName`.
- `App.time`: `parts`, `formatDate`, `formatClock`, `zone`.

**Server code:**
- `the_one/routines/schedule.py`: the wall-clock resolver and `validate`.
- `the_one/interfaces/web/api.py`: the routine create/update parsing of
  `once` (`at` | `in`).

**Library rules** (`docs/ui-control-inventory.md` header; enforced by
`tests/test_ui_control_inventory.py`, `test_ui_ownership.py` and
`test_ui_emitted_classes.py`): a new factory needs:
- an inventory row with its owned classes;
- an engine-parametrized contract test, `tests/browser/test_ui_*.py`, that
  calls `App.ui.<name>(`.

## Outputs

- **`ui/choice.js` (or a new `ui/checkbox-group.js`):**
  - `App.ui.checkboxGroup({legend, name, options:[{value,label}], value:[], onChange, testid})`
    returns `{el, value(), setValue(arr), setDisabled(bool), destroy()}`;
  - a native `<fieldset>` with `<legend>`;
  - owned classes `ui-checkbox-group*`;
  - CSS in `components.css`.
- **The new control's docs and tests:**
  - an inventory row;
  - `tests/browser/test_ui_checkbox_group.py`, a contract test in
    `contracts-controls`, run on both engines.
- **`areas/studio/routines-form-model.js` (new, pure):**
  - `formToBody(state, {mode, initial})`;
  - `bodyToFormState(row, zoneParts)`;
  - `dayOptions(todayParts, extraDate)`, which lists the next 60 days plus
    the routine's own date when editing;
  - `hourMinuteOptions(extraMinute)`;
  - all on `App.studio.routinesFormModel`.
- **`areas/studio/routines-form.js` (new):**
  - `App.studio.routinesForm.open({panelHost, mode, routine, agent, callbacks, opener})`;
  - the inline form;
  - the chat chooser.
- **Callbacks:** `createRoutine` and `updateRoutine` in `agent-data.js` and
  the controller.
- **Leg 8's hidden-buttons check is removed**, so the buttons always show for
  a named agent.
- **Server:**
  - the `once` → `on` input form in the routine POST/PUT parsing;
  - unit tests in `tests/test_routines_api.py` and
    `tests/test_routines_schedule.py` covering a gap time, a repeated time,
    past, more than a year ahead, and a bad date.
- **Tests:** `tests/browser/test_flow_agent_routines_form.py` (new, in the
  agent-tabs lane).
- **Docs and tooling:**
  - the registry;
  - `the_one/agents.md` (the Routines tab subsection: form, chooser, `on`
    input);
  - CLAUDE.md (the Routines paragraph mentions the tab);
  - `scripts/ui_capture.py` gets `agent-routines` and
    `agent-routines-form` surfaces, seeded through REST at the pinned
    clock, with the next-run text masked;
  - the agent-tabs lane is re-measured.

## Acceptance Criteria

- [ ] AC1. **`App.ui.checkboxGroup`** renders a `<fieldset>` and `<legend>`
      with one `App.ui.checkbox` per option.
      - `value()` returns the checked values in option order.
      - `setValue` and `setDisabled` work.
      - Keyboard: Tab moves to each box, and Space toggles it.
      - The group is named by its legend.
      - A missing legend throws.

      The contract test passes in Chromium and WebKit
      (`THE_ONE_REQUIRE_WEBKIT=1`). The inventory row lists the option set and
      the owned classes.
- [ ] AC2. **The server's `on` input.**
      - `{"kind":"once","on":{"date":"2026-11-02","time":"09:00"}}` is stored
        as the UTC `at` of 09:00 in the effective zone.
      - A spring-forward gap time stores the gap's end.
      - A fall-back repeated time stores the first occurrence.
      - Errors:
        - a past time → 422 "That time has already passed.";
        - more than a year ahead → "That time is more than a year away.";
        - a malformed date or time → a list-shaped 422 on `loc ["schedule"]`.
      - The response's `schedule` is the stored `{kind, at}`.
- [ ] AC2a. **Exact parsing of the `on` form** (design review cycle 2).
      - **Signature.** `_routine_schedule(raw, now)` (`api.py`) gains a
        `zone` parameter. Both the POST and PUT routes load
        `time_zones.load_effective_zone(conn)` **before** calling it.
      - **Shape.** Mirroring the `in` branch:
        - `set(raw) == {"kind", "on"}`, so `at`, `in` and `on` can never
          appear together;
        - `on` is a dict with exactly the keys `{date, time}`.
      - **Values.**
        - `date` must match a strict `^\d{4}-\d{2}-\d{2}$` before
          `date.fromisoformat`, which also accepts `20261102`;
        - `time` goes through `_parse_hhmm`.
      - **Conversion.** Call `routine_schedule.resolve_wall_time(day, h, m, zone)`
        (leg 1's resolver), then the existing past and one-year checks.
      - **Errors** go through `_routine_422("schedule", …)`.
      - **Unit tests:**
        - the gap end;
        - a repeated hour;
        - past;
        - more than a year ahead;
        - `2026-13-40`;
        - `20261102`;
        - a bad time;
        - extra keys;
        - `on` together with `at`;
        - a PUT with `on` on a Done one-off, which clears `finished_at`.
- [ ] AC2b. **Nested radio card styling** (design review cycle 2).
      - **The defect.** `components.css` `.ui-radio-option:has(.ui-radio-input:checked)`
        (`~:2343`) and its forced-colors twin (`~:2378`) match descendants,
        so the outer "Once" card would show as selected whenever its nested
        "When" group has a checked radio.
      - **The fix.** Change both rules to a direct-child form, or drop `:has`
        and use the existing per-row `.is-checked`.
      - **Contract test.** `tests/browser/test_ui_radio*.py` gains a nested
        group case: the outer card is styled checked only when its own radio
        is checked.
      - **Change events.** Nested radios and inner select changes never fire
        the outer group's `onChange`. One test line covers this.
- [ ] AC2c. **Library rules for `checkboxGroup`.**
      - **The inventory row** lists every emitted class explicitly. The cell
        regex in `tests/test_ui_control_inventory.py:80` rejects wildcards.
        Use `ui-checkbox-group`, `ui-checkbox-group-legend` and
        `ui-checkbox-group-options`, plus any others.
      - **No variable class names.** Class names are not built from
        variables.
      - **No collisions.** None of them collides with
        `mcp-tools-checkbox-group`, and no `ui-radio-*` class is reused.
      - **Status cell:** `library: App.ui.checkboxGroup`.
      - **The contract test** contains the literal `App.ui.checkboxGroup(`.
- [ ] AC3. **The form** (`routine-form`) opens inline above the list, from New
      routine (create) and from Edit (edit, pre-filled). The fields are:
      - **Name** (`routine-form-name`, `textInput`, limit 64) and **Prompt**
        (`routine-form-prompt`, `textarea`, limit from `limits.prompt_chars`).
      - **Schedule:** an `App.ui.radioGroup` with legend "Schedule", name
        `routine-schedule-kind` and testid `routine-form-schedule`. Its
        options are Once, Daily, Weekdays, Weekly and Every N hours. Each
        option's fields are mounted in its `optionEl(value)` slot and shown
        only while it is selected.
        - **Time of day:** hour 1-12, minute (five-minute steps, plus the
          routine's own minute when editing) and AM/PM
          (`routine-form-hour`, `-minute`, `-ampm`), sent as 24-hour `HH:MM`.
          The Once "At" mode has its own set (`routine-form-at-hour`,
          `-at-minute`, `-at-ampm`). Hidden slots stay in the DOM, so the
          testids must be unique.
        - **Weekly:** `App.ui.checkboxGroup` with legend "Days"
          (`routine-form-days`), Mon to Sun, sent as 0-6 with Monday = 0.
        - **Once:** a nested `radioGroup` with legend "When" and name
          `routine-once-mode`.
          - "In" (`routine-form-in-amount`, number; `routine-form-in-unit`,
            minutes/hours/days) is sent as `{in: {amount, unit}}`.
          - "At" (`routine-form-at-day`, from `dayOptions`, plus the time
            selects) is sent as `{on: {date, time}}`.
        - **Every N hours:** `routine-form-interval`, a number from 1 to 168.
      - **Target:** an `App.ui.radioGroup` with legend "Run in", name
        `routine-target-kind` and testid `routine-form-target`. Its options
        are "A chat", "A new chat each run" and "Its own chat". "A chat"
        shows the chosen chat's description (`routine-form-chat`) and
        Choose chat (`routine-target-picker`).
      - **Save** (`routine-form-save`) and **Cancel** (`routine-form-cancel`).
- [ ] AC4a. **Edit-mode omissions.**
      - **Unchanged `name` and `prompt`** are omitted from the PUT, just like
        an untouched schedule and target.
      - **A touched-but-unchanged once** is still sent as a valid
        `{on: {date, time}}`.
      - **The "At" day list** is built in the operator zone from
        `App.time.parts(now)`, never from `Date` getters, and includes the
        routine's own date.
      - **A test** proves the form's weekly day numbering (Mon = 0) matches
        the server's.
- [ ] AC4. **The body rules** (`formToBody`, unit-tested through
      `page.evaluate`).
      - Changing the schedule kind sends only that kind's keys, never stale
        fields from another kind.
      - **Edit mode compares the serialized form state to the initial
        state.** An untouched schedule sends no `schedule` key, so a past
        one-off awaiting catch-up is not re-validated. A changed-then-reverted
        field is treated as untouched. An untouched target sends no `target`
        key.
      - `bodyToFormState` round-trips every kind: once becomes "At" with the
        routine's date added to the day options even when it is past or more
        than 60 days away.
- [ ] AC5. **Errors.**
      - A 422 list maps through `App.api.fieldErrors`:
        - `name` and `prompt` errors show on their fields;
        - a `schedule` error shows on the Schedule group's status line
          (`routine-form-schedule-error`);
        - a `target` error shows on the Run in group's status line
          (`routine-form-target-error`).
      - A 409 shows on Name.
      - The client pre-checks an "At" time that is already past ("That time
        has already passed.") and a Weekly schedule with no days selected
        before sending.
      - **Save** closes the form, refetches the list and focuses the saved
        row's Edit.
      - **Cancel** closes it and returns focus to the opener.
- [ ] AC6. **The chat chooser** (`routine-chat-chooser`) is an `App.ui.modal`
      chooser with an `App.ui.searchList`.
      - **Data:** `App.store.get('sessions')` is called on open. Rows are
        filtered to this agent's chats and sorted newest first.
      - **Each row** (`routine-chat-option`, `data-session-id`) shows:
        - the title;
        - the platform as a neutral badge (`platformName`) for connector
          chats;
        - the day, through `App.time`.
      - **Search** matches the title and the platform name.
      - **Keys and focus:** Enter picks, Escape closes, and focus returns to
        Choose chat. The pick applies from `onClose`, as in the agent
        picker.
      - **Empty and error lines:** an agent with no chats shows "This agent
        has no chats yet."; a load failure shows "Couldn't load chats."
- [ ] AC7. **End to end in the browser** (each schedule kind and each target
      kind). Create through the form, the row appears with the right sentence
      and target, edit it, and the change shows. A test covers each kind;
      the form-model unit cases cover the rest.
- [ ] AC8. **Docs and tooling.**
      - The registry lists every new testid.
      - The capture surfaces render in light and dark mode, and
        `tests/test_ui_capture_safety.py` passes.
      - The `agent-tabs` lane has been re-measured on a quiet-host
        `--parallel 3` run, or the reason it was not is recorded. It is
        re-budgeted if it moved by more than 15%.
- [ ] AC9. **Gates.**
      - **Lanes** (`THE_ONE_TEST_NETNS=1`): `agent-tabs`, `agents` and
        `contracts-controls` (`THE_ONE_REQUIRE_WEBKIT=1`).
      - **Static guards:** `tests/test_ui_guards.py`,
        `tests/test_token_definitions.py`, `tests/test_design_tokens_a11y.py`,
        `tests/test_ui_control_inventory.py`, `tests/test_ui_ownership.py` and
        `tests/test_ui_emitted_classes.py`.
      - **Also:** `make test-unit` and `make lint`.

## Verification Steps

- AC1: `tests/browser/test_ui_checkbox_group.py`.
- AC2: `tests/test_routines_api.py` and `tests/test_routines_schedule.py`,
  with `frozen_clock`.
- AC3-AC7: `tests/browser/test_flow_agent_routines_form.py`.
- AC8 and AC9: the commands, plus `scripts/ui_capture.py --list` and a
  capture run to a scratch directory outside the repo.

## Implementation Guidance

1. `App.ui.checkboxGroup`, with its inventory row, contract test and CSS.
2. The server's `on` input form and its unit tests.
3. `routines-form-model.js`, the pure model, with its `page.evaluate` tests.
4. `routines-form.js`: the form, then the chooser.
5. Wire `openRoutineForm`, remove leg 8's check, and add the create and
   update callbacks.
6. Registry, docs, capture surfaces and lane re-measure.

## Edge Cases

- **The zone changes while the form is open.** The day list is recomputed on
  the next open, and "At" values are sent as local date and time, so the
  server applies the zone in effect when it receives them.
- **A Weekly edit that unchecks every day.** The client pre-check blocks the
  save, and the server rejects it too.
- **A name that differs only in case from another routine's** gets a 409 on
  Name.
- **The chosen chat is deleted before saving** gives a 422 on the target
  ("That chat doesn't exist."). It shows on the Run in group.
- **A long prompt** keeps its full text in the textarea. Prompt text is set
  with `.value` or `textContent` only.

## Files Affected

All `static/` paths are under `the_one/interfaces/web/`.

- `static/js/ui/choice.js` (or a new `ui/checkbox-group.js`),
  `static/css/components.css`, `docs/ui-control-inventory.md`
- `static/js/areas/studio/routines-form-model.js`, `routines-form.js` (new);
  `routines-tab.js`, `agent-data.js`, `agent-editor-controller.js`;
  `static/index.html`
- `the_one/routines/schedule.py` and/or `the_one/interfaces/web/api.py`
  (the `on` input)
- Tests:
  - `tests/test_routines_api.py`, `tests/test_routines_schedule.py`;
  - `tests/browser/test_ui_checkbox_group.py`,
    `tests/browser/test_flow_agent_routines_form.py` (new)
- `docs/ui-testid-registry.md`, `scripts/ui_capture.py`,
  `scripts/run-tests.sh` (if re-budgeted), `the_one/agents.md`, `CLAUDE.md`

## Citation Audit

Checked on the working tree:
- `ui/choice.js:145-170` (`radioGroup`, `legend` required, `optionEl` slot);
- `ui/field.js:87` (`select`);
- `agent-picker.js:165-185`, `:241` (chooser and pick-from-`onClose`);
- `chats-list.js:102-132` (`platformName`);
- `time.js` exports (no local-to-UTC converter);
- leg 1 `parse_utc` (only UTC `at`, plus `in`).

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off the
leg in the parent flight, and the commit) are Flight Control protocol, driven
by the execution workflow, and are not repeated here.
