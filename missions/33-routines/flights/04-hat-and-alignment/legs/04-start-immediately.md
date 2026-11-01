# Leg: start-immediately

**Status**: completed
**Flight**: [HAT and Alignment](../flight.md)

## Objective

Give the routine form's start a three-way choice, the operator's chosen
mockup **S1** (https://claude.ai/artifact/ADMrdaR59SSTHgWdV6CbVe, artboard
"S1. Radio group"): **On** {date} {time} (exists), **In** {amount} {unit}
(exists as a quick fill), and **Immediately** (new): the first run starts when
the routine is saved. A repeating routine then repeats from that moment; a
one-off runs once, right away.

## Context

- **Operator request at the HAT** (flight log, after C4): "a radio button
  with 3 options start date/time (exists), starts in (exits), or
  immediately (new)"; S1 chosen over S2 (segmented) and S3 (dropdown).
- **Today's form** (`static/js/areas/studio/routines-form.js`): a start
  `App.ui.datePicker` + `App.ui.timeField`, and an "In {amount} {unit}"
  quick start (`routine-form-in-amount`, `routine-form-in-unit`, `applyIn`
  ~:236) that fills the date and time fields from now; the form always sends
  the canonical `{start: {date, time}, repeat, ends}` (F3 DD7).
- **Today's backend** (`the_one/routines/recurrence.py::normalize` ~:283):
  the start is `{date, time}` or the relative `{"in": {amount, unit}}`
  (rounded up to the minute). An operator write has no minimum lead
  (`service._min_ahead(False)` is None); an agent write needs a one-off at
  least a minute away (`MSG_ONCE_TOO_SOON`). A schedule with no future
  occurrence is refused ("This schedule has no runs left.", 422,
  `_require_future`). The start is inclusive when it matches the rule, and
  "next run" is the first occurrence at or after now, so a start at the
  current minute (already seconds past) does not run now; this is why
  "Immediately" needs a backend change, not just a form fill.
- Builds on legs 02 and 03 and fix pass 1 (all uncommitted in this tree).

### Design decisions (leg-level)

**L4-DD1. The form (S1).**
- A "Starts" `fieldset` with an `App.ui.radioGroup` (or the library's radio
  control the form already uses) of three options, each on one line:
  1. **On** with the date picker and time field (the stored start when
     editing);
  2. **In** with the amount and unit (kept testids), and beside them the
     resulting date and time as muted text ("Today at 9:52 PM"), updating as
     the amount changes;
  3. **Immediately**, with the muted hint "The first run starts when you
     save".
- The inputs of the unselected options are disabled (library disabled
  tokens), never hidden, so the three choices stay comparable (as drawn).
- Defaults: a new routine starts with **On** selected and today's next whole
  hour (unchanged); an edited routine opens with **On** and its stored start.
  "In" and "Immediately" are ways to set the start, not stored modes.
- The preview line follows the choice; for Immediately it reads e.g. "Every
  day at the time you save · First run: when you save" (server-worded where
  the preview route can word it; see L4-DD2).
- Save's label stays "Save" (S2's "Save and run" was not chosen).
- In edit mode, choosing Immediately counts as a change (Save enables).
- **Form mechanics (review):** use `App.ui.radioGroup` (`js/ui/choice.js`
  ~:281; `optionEl(value)` gives each option's content slot, `slotIndent:
  'label'`); it replaces the current Starts role=group div. Disable the
  unselected options' inputs: `App.ui.datePicker.setDisabled`, the time
  field's (verify `App.ui.timeField` has `setDisabled`; add it with a
  contract test if missing), `.disabled` on the text input and select. The
  model gains `startMode: 'on' | 'in' | 'now'` (`defaultState`,
  `bodyToFormState` → 'on'); `scheduleBody` sends `start: {now: true}` for
  'now'. While 'now' is selected, `fs.startDate` / `fs.startTime` stay at the
  client's current date and time in the operator zone (`App.time`), so the
  presets and the Custom dialog still work; only `scheduleBody` sends the
  now-start. "In" keeps filling the date/time (`applyIn` ~:235), and its
  resulting-time text (new testid) updates on amount and unit changes and is
  empty for a blank amount. Because `formToBody` diffs `scheduleBody`,
  Immediately counts as a change and flipping back to On is clean again
  (test both). The preview re-runs on every change while Immediately is
  selected.

**L4-DD2. The backend: a service-level now-start (design review's
mechanism; no `recurrence.py` change).** A change inside
`recurrence.normalize` cannot express "due now" (occurrences are strictly
after `now`, and `normalize` returns only `(schedule, anchor)`), and a
service-side Run now would double-run one-offs and label the run "Run now".
So:
1. **Wire shape** `{"start": {"now": true}, "repeat": …, "ends": …}`,
   operator routes only.
2. **A helper in `routines/service.py`**, e.g.
   `resolve_now_start(raw, now, zone) -> (raw', is_now)`: fires only when
   `raw["start"] == {"now": True}` (exact dict equality) and rewrites the
   start to the canonical `{date, time}` of the **floor** minute of `now` in
   the operator zone (`recurrence.render_start(now.replace(second=0,
   microsecond=0), zone)`). Everything else goes through `normalize`
   unchanged (instant-anchored units anchor at that minute; wall-clock units
   take that wall start), so the grid is "save minute + k periods".
3. **`create_routine` and `update_routine`** call it only when
   `not agent_caps and schedule_pair is None`, with `min_ahead=None`. For a
   now-start, instead of `_require_future`: refuse "This schedule has no runs
   left." when `next_occurrence(sched, anchor, floor_minute - 1µs, tz)` is
   None (an `ends` already past), else set `next_run_at = now.isoformat()`
   (the **exact save instant**, not the floor minute: an every-minute routine
   has 30 s of grace and a floor-minute `next_run_at` could be recorded
   Missed). Spell out the order in `update_routine`: the now-start's
   `next_run_at` is set in the `schedule_changed` branch and must not be
   overwritten by the later `_require_future(...)` (~:287); it is persisted
   only if the routine ends up enabled and not finished (a disabled routine
   is re-anchored only and does not run; `enabled` is unchanged). A
   now-start on an update clears `finished_at` like any schedule change, so
   **a Done routine can be re-run with Save + Immediately**.
4. **Scheduler: no change.** The scheduler's `late = now - due` is a few
   seconds (< `ON_TIME_SECONDS`, `scheduler.py` ~:33), so `_handle` (~:213)
   records trigger "schedule" (history "Scheduled"), never catch-up or
   missed; `advance_if_due` claims the row (no double run) and computes the
   next occurrence after its own now (None for a one-off: Done; the next grid
   point one period after the save minute for a repeat). `poke_scheduler()`
   already runs after each write, so it runs within seconds.
5. **Agent path: no code change.** `agent_change` and the tools use
   `validate_schedule` → `normalize` with `_min_ahead(True)`, which refuses a
   start that is not `{date, time}` or `{in}` ("The schedule needs a start
   with a date and a time."). A test pins that refusal; the tool schemas and
   text are untouched (no eval run; confirm with a diff of the tool files).
6. **Preview** (`routines_api.py` ~:105, `schedule_preview` ~:90): call the
   same helper; check "has a future" with `after = floor - ε`; prepend `now`
   as `next_runs[0]` with 2 further occurrences after `now` (3 in all); return
   `immediate: true`. The **client composes** the preview line for it: the
   server's sentence, then "First run: when you save" (the server sentence is
   not changed).
- **FD calls on the review's questions:** the immediate run is labelled
  "Scheduled" in history (it is the schedule's first occurrence); a
  now-start saved on a routine whose run is still going gets the existing
  "still running" skip (accepted, no new refusal; recorded); a one-off keeps
  the save minute as its stored date and time ("Once, on …" afterwards).

## Acceptance Criteria

- [ ] AC1. The form shows the three-option "Starts" group per L4-DD1; the
      unselected options' inputs are disabled; "In" shows its resulting
      time; edit mode opens on "On" with the stored start.
- [ ] AC2. Saving a new **repeating** routine with Immediately runs it
      within seconds (a new chat, history "Ran", trigger Scheduled), and its
      next run is one period after the save minute.
- [ ] AC3. Saving a **one-off** with Immediately runs it once within seconds
      and it shows Done.
- [ ] AC4. Editing an enabled routine with Immediately re-anchors it to the
      save minute and runs it within seconds; a Done routine saved with
      Immediately runs again; a disabled routine is re-anchored and does not
      run.
- [ ] AC5. The preview route returns `immediate: true` and `next_runs[0]` =
      now (then two grid occurrences) for a now-start; the form's preview
      line reads the sentence then "First run: when you save".
- [ ] AC6. `agent_change` / the agent tools refuse a now-start ("The
      schedule needs a start with a date and a time."), the proposals queue
      is unaffected, and the tool schemas and text are unchanged.
- [ ] AC7. A now-start is never recorded as Missed or as a catch-up: a unit
      test with `frozen_clock` sets `next_run_at` = now and runs scheduler
      passes at +2 s and +59 s (trigger "schedule").
- [ ] AC7b. Two saves with Immediately give two runs; the 50-active cap
      still refuses; an `ends` already past refuses "This schedule has no
      runs left.".
- [ ] AC8. New testids registered (the radio options; the "In" resulting
      time); `tests/test_nav_helper.py`, the static guards and
      `tests/test_area_module_size.py` pass; `the_one/agents.md` "Routines
      (M33)" and CLAUDE.md's Routines paragraph mention the now-start.
- [ ] AC9. `THE_ONE_TEST_NETNS=1 make test-unit` (15 skipped) and the
      `agent-routines` lane pass.

## Verification Steps

- AC2-AC5, AC7: unit tests (`tests/test_routines_service.py`,
  `test_routines_api.py`, `test_routines_scheduler.py`, the recurrence
  tests) and browser tests in `tests/browser/test_flow_agent_routines_form.py`.
- AC1, AC8: browser tests and the guards.

## Edge Cases

- Immediately while the agent already has 50 active routines: the cap
  refusal as for any create.
- Immediately on a routine that is off: it is turned on? The edit form does
  not change `enabled`; a now-start on a disabled routine just re-anchors
  (it does not run). Record the behaviour.
- Saving Immediately twice in a row: two runs (each save is a request).
- The browser's minute rolls over between choosing and saving: the server
  takes its own now, not the client's (a midnight rollover only makes the
  first run off-grid).
- `ends: after N` with a now-start counts the save minute as occurrence 1
  only when that minute is on the grid; a weekly rule whose days exclude
  today makes the immediate run an extra off-grid run that does not count
  (the preview shows it truthfully).
- An every-minute routine the scheduler picks up more than 30 s late (a
  stalled host) is recorded Missed: accepted.
- The app closed right after a save: a one-off (24 h grace) or an hourly or
  longer repeat catches up on restart; a very short repeat may record one
  Missed: consistent with existing behaviour.
- A DST fall-back hour: the floor minute's wall time may resolve to the
  first of the two hours; the run happens immediately anyway (accepted).

## Files Affected

- `the_one/routines/service.py` (no `recurrence.py` or `scheduler.py`
  change); `static/js/ui/date-time.js` only if `timeField` lacks
  `setDisabled` (with its contract test);
  `the_one/interfaces/web/routines_api.py` (preview);
  `static/js/areas/studio/routines-form.js`, `routines-form-model.js`,
  `static/css/studio.css`; `docs/ui-testid-registry.md`;
  the tests above; `the_one/agents.md`, CLAUDE.md.

## Citation Audit

`recurrence.normalize` (~:283) with the `{"in": …}` start (~:309-320) and
`MSG_ONCE_TOO_SOON` (~:49, ~:277); `service._min_ahead` (~:165) and the
`validate_schedule` callers (~:200, ~:263, ~:431); `routines-form.js`
`inAmount` (~:124-136) and `applyIn` (~:236). Verified at planning against
the working tree.
