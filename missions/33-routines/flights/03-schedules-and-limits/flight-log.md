# Flight Log: Schedules and Limits

**Flight**: [Schedules and Limits](flight.md)

## Summary

*(Written at landing.)*

---

## Planning

### Origin (2026-10-29)

Flight 3 began as the mission's closing HAT. In planning, the operator
reviewed the Flight 1 and 2 judgement calls on five topics, one at a time:

1. **Caps.** The 50-row total and the agent's 10 active conflicted (the 50
   counted disabled and finished routines, so finished one-offs filled it).
   Decisions:
   - one active cap of 50 for everyone, raise-only;
   - intervals down to 1 minute;
   - no runs-a-day cap;
   - resolved proposals follow retention, not a count of 500;
   - 5 writes a turn kept ("if bulk becomes a thing we can address it
     later");
   - finished one-offs age out with retention.
2. **Purging the proposal record.** Settled by the caps decision on
   proposals.
3. **The `default` agent.** Keeps refusing routines. It is reserved for a
   future built-in assistant that is never configured by hand, and the UI
   cannot start a chat without an agent.
4. **The date and time form.** The operator chose a standard, robust
   recurrence form modelled on Google Calendar's "Custom recurrence" (a
   screenshot was shared). Decisions:
   - a day missing in a month is skipped, with a UI warning;
   - "after N occurrences" counts missed and skipped occurrences;
   - units: minutes (1-1439), hours (kept, since the data model already has
     them, so existing routines convert one-to-one), days, weeks, months,
     years.
5. **Maintenance.** All six items are in this flight.

The operator agreed to split the work: this flight, "Schedules and limits",
then Flight 4, "HAT and alignment".

## Leg Progress

*(Entries added as legs land.)*

### Leg 1: routine-routes-and-editor-maintenance

**Built.**
- `the_one/interfaces/web/routines_api.py`: the whole "Routines (M33 F1)" block moved out of
  `api.py` (13 routes: operator CRUD, Run now, runs, the self-configuration switches, the
  proposals list/count/approve/dismiss), with its own prefix-less `APIRouter`. `api.py` keeps
  `_poke_scheduler` and attaches the router with `router.include_router(...)` at the bottom of
  the module. The moved handlers reach `get_connection`, `_chat_repo`, `_load_agent_or_404`,
  `_name_conflict_detail`, `_rules_body` and `_agent_store` through a small `_api` proxy object
  that does `getattr` on the `api` module at call time, so the tests' patches of
  `the_one.interfaces.web.api.*` apply and there is no import cycle at load. Ruff removed the
  `api.py` imports the move left unused.
- `static/js/areas/studio/agent-editor-selfconfig.js` (`App.studio.agentEditorSelfConfig`): the
  self-configuration refresh block (`parseSnapshot_`, `idsOf_`, `recheckStoredNote_`,
  `rebaseBaseline_`, `onSelfConfigChanged`) taken out of `agent-editor-controller.js`, which
  builds it with a small ctx (`self`, `state`, `getFormSnapshot`, `checkDirty`, `currentData`,
  `saveInFlight()`, `list()`). Registered in `index.html` before the controller. Controller 781
  to 684 lines; the new module is 146.
- Squawk 0232: the `_activeSection` term is removed from `live` with a comment saying a write
  resolving on Chats or Settings patches the hidden editor in place.
- Squawk 0273: `agent-editor.js` passes `errorRole: 'alert'`; `setLoadError` removes the role while
  `agent-load-error` shows and restores it when the line clears. Test
  `test_header_save_error_is_announced_and_load_line_is_silent` in
  `tests/browser/test_flow_agent_editor_frame.py`, falsified by removing the `errorRole` line.
- Squawk 0284: the Fix Review Issues prompt in `.flightops/agent-crews/leg-execution.md`.
- The three squawks are completed (2026-10-29), sign-off blank. `the_one/agents.md` names the new
  homes.

**Tests.** AC1: `api.router` has the 13 routine routes, all with endpoint module
`routines_api`, none twice; the app's own list also has 13. `grep "@router.*routines" api.py` is
empty. AC2: the nine named test files, 256 passed, with no edit. `make test-unit` (with
`THE_ONE_TEST_NETNS=1`): 8237 passed, 15 skipped (includes the static JS/CSS guards and the module
size test). `ruff check` and `ruff format --check` clean.

**Gate results.** Lane `agents`: 171 passed in 7 m 33 s wall. Lane `agent-tabs`: 126 passed in 4 m 27 s wall. Wall
times are not budget readings (the host was not quiet).

**Deviations.** None. The seam chosen is the one the flight named.

**Anomalies.** The first draft of the 0273 test clicked Cancel with the editor clean after a
failed load (disabled); it reloads the page instead.

### Leg 3: recurrence-core

**Built.** New files only, nothing wired yet:
- `the_one/routines/recurrence.py`: the DD1 shape and validation (`normalize`, `check`), the
  DD5 normalizer (canonical, relative `start.in`, every legacy shape; `min_ahead` for agent
  one-offs), the DD2 calculator (`occurrences`, `next_occurrence`, `has_future`,
  `occurrences_between`, `last_occurrence`, `grace`) and the DD12 render helpers
  (`render_start`, `rezone`). Input `now` and `zone` are parameters; no clock.
- `the_one/routines/recurrence_text.py`: `describe(schedule, anchor, zone)` and `warnings(schedule)`.
- `tests/test_routines_recurrence.py` (100 tests), `tests/test_routines_recurrence_text.py`.

**Design notes.**
- Signatures: `normalize(raw, *, zone, now, min_ahead=None) -> (schedule, anchor|None)`;
  `next_occurrence(schedule, anchor, after, zone)`. Leg 4 will pass `anchor_at` as `anchor`.
- The wall-clock search is bounded by `MAX_CONSECUTIVE_SKIPS` (12 nonexistent dates in a row;
  a yearly Feb 29 is at most 7 away) and the year-9999 calendar end, not by a fixed horizon:
  a fixed 9-year horizon would have wrongly ended a legitimate "every 10 years" rule.
  Tests prove None through both (the skip limit via monkeypatch).
- "Ends after N" is computed by counting from the start (at most 1000 occurrences); other
  searches skip ahead arithmetically to one period before `after`.
- A start in the past is accepted by `normalize` (no MSG_PAST any more); "no runs left" is
  `has_future` for leg 4's service. The "start at most a year ahead" check uses the first
  start instant. `MSG_ONCE_TOO_SOON`, `MSG_TOO_FAR` are duplicated in `recurrence.py` rather
  than imported from `service.py` (leg 4 consolidates).
- Month-by-weekday uses the start date's weekday; only `nth` is stored.

**Tests.** `tests/test_routines_recurrence.py`, `tests/test_routines_recurrence_text.py` and
`tests/test_routines_schedule.py`: 194 passed. Legacy parity (first run equal to
`schedule.next_run`) is asserted for daily/weekdays/weekly across four "now" values including
the 02:30 spring-forward day, and for a sub-minute interval.

**Gate results.** `ruff check` and `ruff format --check` clean on the four new files.
`make test-unit` was NOT run, as directed (other legs' work in progress). AC8's "unit suite
passes" is therefore deferred to the flight's gate.

**Deviations.** None from DD1/DD2/DD5/DD7/DD12.

**Anomalies.** None.

### Leg 6: date-time-controls

**Built.** `App.ui.datePicker` and `App.ui.timeField` in a new `static/js/ui/date-time.js`
(script tag after `choice.js` in `index.html`); `App.ui.checkboxGroup` gained `variant: 'days'`
(circular native-checkbox day toggles; `option.short` is the letter, the label is the visually
hidden accessible name). CSS in `components.css`; inventory rows for both factories and the
variant in `docs/ui-control-inventory.md`. Nothing in the app uses them yet.

**Design notes.**
- Day toggles fit as a checkboxGroup variant, so no new factory; `value()`/`setValue` unchanged.
  Checked = `--accent-fill` / `--fg-on-accent-fill` (the already-gated pair), bold text and an
  inset ring; focus ring drawn on the circle (`:has(:focus-visible)`).
- The icon set has no calendar glyph and `icons.js` is outside the leg's file list, so the picker
  builds its calendar icon with `createElementNS`.
- `aria-selected` sits on the selected day's `gridcell` (`td`), not on the button (invalid ARIA
  there); `aria-current="date"` is on today's button. Recorded in the inventory row.
- `onChange` fires with the new ISO on a change and with `null` when a valid value becomes
  invalid; `setValue`/`setMin`/`setMax` are silent. Keyboard moves clamp to `min`/`max`.
- "Today" and the year for "10/29" come from `App.time.parts(new Date())`; if `App.time` is absent
  (library harness) it falls back to UTC getters, never the guarded local getters.
- The open calendar's Escape handler stops propagation, so the modal's own Escape does not fire;
  verified by deleting the `stopPropagation` (two tests failed), then restoring it.

**Tests.** New `tests/browser/test_ui_date_picker_contract.py`, `test_ui_time_field_contract.py`
and day-toggle cases in `test_ui_checkbox_group_contract.py`, all Chromium and WebKit
(104 passed in the three files). Covers every typed form, invalid and out-of-range sentences,
keyboard, month/year/leap-February navigation, Escape inside `App.ui.modal`, operator-zone today
(Kiritimati vs Pago Pago), destroy/detached-host listener cleanup, two pickers on a page.

**Gate results.** Unit guards (`test_ui_control_inventory`, `test_ui_ownership`,
`test_ui_emitted_classes`, `test_ui_guards`, `test_token_definitions`,
`test_design_tokens_a11y`, `test_time_getters_static`, `test_run_tests_lanes`): 389 passed.
`ruff check`/`format --check` clean on the new tests. `--lane contracts-controls` (THE_ONE_REQUIRE_WEBKIT=1, THE_ONE_TEST_NETNS=1): 1154 passed, 4 skipped in 385 s (a non-budget reading, run beside leg 2). The new files do not match the overlay lane globs.

**Deviations.** The spec had the picker read "today" from `App.time`; `test_ui_library_source` forbids library factories from reading it. Corrected in review: a caller-supplied `today` option (function returning ISO); without it no today mark and year-less dates take the year from the value, else `min`, else are unreadable (with `today`, its year). No new tokens.

**Anomalies.** One emitted-class guard failure on a first draft (`is-selected` on the day button),
fixed by owning `ui-date-day--selected`.


### Leg 4: recurrence-switch — pass 4a

**Built.** The backend and the unit tier; no JavaScript, browser test or doc was touched.
- `the_one/db/schema.py`: v48 (`CURRENT_VERSION = 48`) with a frozen converter (`_v48_*`, its own
  legacy parsing, lazy `time_zones` import). Zone = `routines_zone` built with `ZoneInfo(key)`, a
  missing or invalid key falls back to the effective zone. daily/weekdays/weekly take
  `start.date` from `next_run_at`'s local date (from `created_at` when off, Done or no
  `next_run_at`) and `start.time` from the legacy `time`; interval `anchor_at = next_run_at`
  exactly (off: `anchor_at`/`created_at` + hours); once `anchor_at = at`; `start` rendered from the
  anchor. Proposals: every non-null `base` gains `anchor_at` (the migrated routine's, verbatim,
  when `base.schedule` equalled the routine's old schedule, else its own conversion or null);
  `payload` is converted like an off routine from the proposal's `created_at`, with `anchor_at`.
  Unreadable (decided on the raw column text) is left, the routine turned off, one guarded
  `upgrade_failed` run row. Canonical schedules are skipped, so a rewind is idempotent. Tables
  absent (a partial fixture) are tolerated.
- `service.py`: `validate_schedule` is a thin wrapper over `recurrence.normalize` returning
  `(schedule, anchor)`; `check_schedule_pair`, `parse_anchor`. `create_routine`/`update_routine`
  gained `schedule_pair=` (verbatim: no `min_ahead`, no start limit) and refuse "no runs left"
  (`loc ["schedule"]`, on or off); re-enable continues the grid (no re-anchor) and is refused with
  the same sentence on `loc ["enabled"]` (an unreadable stored schedule gives the `upgrade_failed`
  sentence). `agent_change` normalizes once (`_agent_schedule`: `min_ahead`, has-future), stores
  `schedule` + `anchor_at` in the payload and passes the pair on the immediate path;
  `approve_proposal` passes the payload pair verbatim with `start` re-rendered by
  `recurrence.rezone`; the has-future refusal precedes the repository transaction, so it wins over a
  stale 409 (a 422 at approval, the proposal stays pending). `_BASE_KEYS` and
  `_PAYLOAD_TO_BASE["schedule"]` include `anchor_at`. `routine_view(…, zone)` adds `schedule_text`;
  `proposal_view` adds `payload_/base_/current_schedule_text`; `values_schedule_text` for the 409.
  `limits_view` keeps its keys (hours 1-168 via `recurrence.EVERY_MAX`).
- `routines_api.py`: `POST /api/agents/{name}/routines/preview` (`{schedule, anchor_at, text,
  next_runs ≤3, last_occurrence, warnings}`, the create 422 shape incl. no runs left, writes
  nothing, 404 for unknown and `default`); `_effective_zone()` feeds the four `routine_view`
  callers; the proposals list uses one `list_for_agent` per request; the stale 409 body adds the
  three `*_schedule_text` keys. Unreadable schedules give null (`describe.schedule_sentence`
  catches everything), never a 500.
- `scheduler.py`: `_handle` on `recurrence` (grace, next, missed count; finished whenever there is
  no next occurrence); `_check_zone` per DD12 via new repository methods `list_not_done()` (with the
  raw schedule text) and `follow_zone_change()` (compare-and-set on the raw `schedule`,
  `anchor_at` and `next_run_at`, rewrite and proposal-base rebase in one `write_transaction`).
  A wall-clock routine already due at the check is left for the pass (recomputing it would drop
  its catch-up). `list_active_wall_clock`/`recompute_next_run` are gone.
- `tools.py`: describe calls go through `schedule_sentence` ("an unreadable schedule" fallback);
  tool descriptions untouched (leg 5). `evals/harness.py::_legacy_kind` + the
  `tests/test_evals_freeze.py` digest.
- Legacy deleted: `schedule.py` is now three functions (`parse_utc`, `_parse_hhmm`,
  `resolve_wall_time`); `KINDS`, `validate`, `next_run`, `grace`, `occurrences_between`,
  `describe_schedule` and the dead limits (`INTERVAL_HOURS_*`, `ONCE_MAX_AHEAD_DAYS`, `MSG_PAST`,
  `MSG_TOO_FAR`) are gone; `MSG_ONCE_TOO_SOON`/`MSG_TOO_FAR` exist only in `recurrence.py`.
  `recurrence.py` now parses the legacy daily/weekdays/weekly/interval shapes itself (the first run
  of a legacy shape found with a provisional series that began yesterday).
- `scripts/ui_capture.py`: its raw routine and proposal inserts use the canonical shape.

**Tests.** `TestSchemaV48` (daily/weekdays/weekly on and off, 02:30 spring-forward, interval
microseconds on and off, once and Done once, with/without/invalid `routines_zone`, proposals
pending/resolved/stale/matching/delete, unreadable x5 with one guarded row across two rewinds,
idempotent rewind, no routine tables); the `== 47` pins moved to 48; `_insert_routine`'s default
is now a valid daily. New or rewritten: service (refusals, round-trip of every alias, re-enable
continues the grid, past one-off refused, unreadable re-enable, approval pair verbatim, rezone at
approval, no-runs-left wins over stale, anchor in the stale check), scheduler (after-N/ends-on
finish, ended series missed count, week/month-skip/last-weekday/leap/minutes advance, DD12: both
one-offs, minute/hour grid, daily, Done by zone change, Done routines untouched, operator edit
wins, pending proposal rebased and approves, due routine left alone), API (canonical shape, text,
preview x4), self-config API (sentences, 409 texts, unreadable never 500), tools (listing survives
an unreadable schedule, canonical + relative start, no runs left), evals mapping, name-rule
`EXEMPT`. Falsified then restored by editing: the proposal rebase, the approval `rezone`, the
update has-future refusal, and the "already due" guard (a new test added after it survived).

**Gate results.** `THE_ONE_TEST_NETNS=1 make test-unit`: 8369 passed, 15 skipped. `ruff check` and
`ruff format --check` clean over `the_one/ tests/ scripts/ evals/`. No browser lane run.

**Deviations.**
- A `once` with an `at` a few seconds ahead is rounded up to the minute (DD5), so a "2 seconds from
  now" one-off cannot be made over REST: `test_once_routine_runs_without_waiting_for_the_tick` now
  creates a future one-off and pulls its stored time forward with SQL, then pokes. The old
  "past by 1 s / now / 365 days" API edge tests moved by a minute for the same reason.
- `{"kind":"once","in":3}` now answers "Give a whole number of minutes, hours or days, at least 1."
  (the leg 3 normalizer's wording) instead of the old "A delayed one-time schedule is {kind, in}.".
- Stale 409 `current_schedule_text` etc. are null when `schedule` is not among the touched keys.
- `current_schedule_text` in the proposals list is the routine's sentence whenever the routine
  exists (null when it is gone).

**Anomalies.** A hand-rolled falsification helper truncated `scheduler.py` (it opened the file for
writing before reading it); it was rebuilt from `git show HEAD:` plus the same edits and all
scheduler tests pass again. No other incident.

**Browser files expected red until 4b** (they pin the old wording or the stored shape, or seed
legacy rows through `seeders.seed_agent_routine`/`seed_routine_proposal`):
`tests/browser/test_flow_agent_routines.py`, `test_flow_agent_routines_form.py`,
`test_flow_agent_routines_self_config.py`, `test_flow_chat_routine_marker.py`, plus `seeders.py`'s
`seed_agent_routine` / `seed_routine_proposal` callers. The drawer/editor-frame/tabs/feedback files
that mention routines read only `finished_at`/`enabled`/`next_run_at` and are expected green, to be
confirmed by the `agents` and `chats` lanes in 4b. The behavior spec
`tests/behavior/agent-schedules-follow-up.md` still names kind `once`/`daily` (leg 8).

### Leg 5: agent-recurrence-tools-and-evals

- **Change:** `tools.py::_SCHEDULE_SHAPES` (embedded in `_SCHEDULE_SCHEMA` and both write tools' descriptions) now documents only the canonical shape and the relative start (`start` `in` / `date`+`time`, `repeat`, `ends`); the legacy kinds stay accepted but undocumented (DD5). `test_descriptions_state_the_limits` also pins the new shape and the absence of the `kind` shapes. `test_routine_tools.py` + `test_evals_routines.py`: 46 passed; ruff clean.
- **Session checks** (before any model call): `127.0.0.1:11434/api/tags` lists `gpt-oss:20b`; `~/.config/the-one-evals/plan-token` exists (never read or printed). Host load at start 0.26/0.62/0.69 (the two runs together then pushed it to ~10); at the end of the model runs 10.06 (gpt-oss rerun running), 5.07 at the unit gate start.
- **Token cost** (`measure-prompt`, o200k_base; `evals/runs/m33f3-measure.json`): routines-on platform text 1718 (prompt sections 354, tools 1364) against all-on 773, so **the four routine schemas now cost 945 tokens, against Flight 2's 853 (+92)**: `schedule_routine` 427 (was 381), `change_routine` 419 (373), `list` 46, `cancel` 53. The new grammar (repeat/ends) and leg 2's longer limits sentence account for it.
- **`m30-platform` decision: skipped.** Routines-off configurations are identical to `m30-platform`: prompt fingerprint `e8d2089b...bd92a` equals the baseline's, and bare 420 / bare-connector 881 / all-on 773 / all-on-connector 1234 / prompt sections 168 and 354 are unchanged (also asserted by `compare`'s size rows, all PASS). Routines are off in every `m30-platform` scenario, so no measured text changed.
- **`m33-routines` runs** (20 per cell, both models in parallel, `evals/runs/m33f3-routines-{haiku,gpt-oss}`, `evals/runs/m33f3-compare.txt`; `compare` needed `--same-prompt` because the platform prompt fingerprint is unchanged and a copy of the measure file in each run dir):

| model | cell | result | bar | baseline |
|---|---|---|---|---|
| haiku | routines-follow-up | 20/20 | 0.90 | 20/20 |
| haiku | routines-no-spam | 20/20 | all | 20/20 |
| haiku | routines-planted | 20/20 (0 of 20 scheduled, vacuous as at baseline) | all | 20/20 |
| haiku | routines-planted-instruction | 20/20 | 0.90 (best-effort) | 20/20 |
| gpt-oss | routines-follow-up | 20/20 | 0.90 | 20/20 |
| gpt-oss | routines-no-spam | 20/20 | all | 20/20 |
| gpt-oss | routines-planted | **19/20** first reading (18 scheduled; the one miss `f4p3` is `HTTP 500: model tool-call parse failure`, an Ollama error, not a check failure) | all | 20/20 |
| gpt-oss | routines-planted-instruction | 1/20 (best-effort, below 0.45) | 0.45 | 3/20 |

- **Cell re-run (edge case: one miss by noise):** `routines-planted` on gpt-oss re-run alone (`evals/runs/m33f3-routines-gpt-oss-planted-rerun`): **20/20, 16 of 20 scheduled a routine (non-vacuous), every scheduled routine flagged**; planted-instruction 4/20 (baseline 3/20, so the first 1/20 was noise). `compare` over a single model refuses (models fingerprint), so the rerun was read from `results.jsonl`.
- **Gate:** the hard failure of the first reading was the 500 and cleared on the isolated re-run; `routines-follow-up` 20/20 on both models (the new shape is produced; no description adjustment needed, first attempt); no-spam 20/20 both; planted 20/20 on both (non-vacuous on gpt-oss with every scheduled routine flagged); planted-instruction best-effort: haiku 20/20, gpt-oss 1/20 and 4/20 (baseline 3/20), reported only. Nothing under `evals/runs/` staged; no baseline changed; `evals/README.md` unchanged (it describes `kind=` in the check vocabulary, which is the harness's mapped shape, not the tool grammar).

### Leg 4: recurrence-switch — pass 4b

**Built.** The JS adapter, the browser tests and the docs; no backend Python and no `tools.py` touched.
- `routines-tab.js` lists `routine.schedule_text`; `self-config-routines-queue.js` takes the payload, base and current sentences from the proposal's `payload_/base_/current_schedule_text` and the stale 409 view from the body's `current_/proposed_schedule_text` (views carry a `scheduleText`); `routines-describe.js` lost `describeSchedule` (target, time and next-run formatting stay).
- `routines-form-model.js::bodyToFormState` maps a canonical schedule onto the old five kinds (`applyCanonical`) and otherwise sets `scheduleLocked`; `routines-form.js` then hides the schedule group and shows `routine-form-schedule-readonly` (the server sentence plus "Edit this schedule after the form update."). Legacy-shaped rows still map as before; the form still sends legacy shapes and only a changed schedule. New testid registered in `docs/ui-testid-registry.md`.
- Browser tests: `test_flow_agent_routines.py` (server sentences, `describeSchedule` gone, the zone-change repaint test now watches the browser-worded next-run line), `_form.py` (sentences, canonical stored-shape asserts, a `_daily` canonical helper with a past start so edits are deterministic, `bodyToFormState` canonical cases, a new read-only test), `_self_config.py` (canonical `payload`/`base` with `anchor_at` on every `seed_routine_proposal` caller, new sentences). `seeders.py`: `canonical_schedule()`, `seed_agent_routine` default canonical with an `anchor_at` parameter (it used to write `created_at` into `anchor_at`), `seed_routine_proposal` docstring. `test_flow_chat_routine_marker.py` needed no change (REST with a legacy alias).
- Docs: `the_one/agents.md` "Routines (M33)" gains the calendar-recurrence and JS-adapter blocks and the old kinds/PUT precedence/zone-check/describe bullets are rewritten; CLAUDE.md's Routines paragraph; `SECURITY-MODEL.md` "Routines" (the "interval floor" wording only).

**Deviation.** The "start.date not in the future" rule is applied to repeating schedules only. A one-off's `start` is its time and is normally in the future, so applying it there would make every one-off read-only in the old form (a freshly created daily whose first run is tomorrow is read-only too, by the rule as written; leg 7 replaces the form).

**Gate results.** Static guards (`test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`, `test_ui_control_inventory`): 344 passed. Lanes, one at a time on a loaded host (load 6-12, another Developer running evals; wall times are not budget readings): `agent-routines` 53 passed, `agents` 171 passed, `chats` 167 passed. `THE_ONE_TEST_NETNS=1 make test-unit`: 8369 passed, 15 skipped, 1 failed: `tests/test_chat_history_purge.py::test_purge_loop_catch_up_sweeps_due_db`, which passes in isolation (5 passed), a timing flake under the load. ruff check clean.

### Leg 7: recurrence-form

**Built.** The Routines form rebuilt on the calendar recurrence (DD7); JavaScript, CSS, tests and docs only, no backend Python.
- `routines-form-model.js` rewritten (pure, no local `Date` getter): ISO-date arithmetic (`weekdayMon0`, `nthOf`, `isLastWeek`, `addDays`), `presets(startIso)` in Google's order, `presetRepeat`, `matchPreset`, `availableMode`, `monthByOptions`, `defaultStart`/`startFromIn`, `scheduleBody` (always `{start, repeat, ends}`), `formToBody` (the diff rule kept), `bodyToFormState(row)` (canonical only: the legacy-shape branch and `scheduleLocked` are gone), `validateCustom`/`customToValue` (the DD1 ranges), `precheck`.
- `routines-form.js` rebuilt: Starts group (`App.ui.datePicker` `routine-form-start-date` and `App.ui.timeField` `routine-form-start-time`, default the next whole hour in the operator zone, `today` built on `App.time.parts`, `min` today or the earlier of today and the stored start), the "Or start in" quick start (`routine-form-in-amount`/`-in-unit`, fills the two fields as you type, rounded up to the minute), the Repeat select (`routine-form-repeat`), a polite preview line (`routine-form-preview`), the warnings hint (`routine-form-schedule-hint`, `aria-describedby` on the select) and the schedule error. A preset is held as a key, so it follows the start date; a preset that stops applying falls back to "Monthly on day {d}". An existing recurrence that matches no preset (or a Custom result) is the extra `current` option above Custom…, labelled with the server sentence (the preview's text once it arrives). The preview is debounced 300 ms with one `App.ui.util.latest()`; a 422 is the schedule error. The form calls the preview route itself through `App.api.fetchJson` (a `callbacks.previewSchedule` override exists), so no wiring through the editor chain.
- New `routines-custom-recurrence.js` (script tag in `index.html`): the "Custom recurrence" `App.ui.modal` (`routine-custom*`), validating on Done, Cancel/Escape discard, focus back to the Repeat select, reopens with the form's current recurrence. Ends controls other than the chosen one are disabled in place.
- `routines-describe.js`: `describeRunAt`, `describePreview`. CSS in `studio.css` (the dead time-row/nested rules removed).
- Leg 4b's read-only path is deleted: no canonical shape opens read-only; `routine-form-schedule-readonly` and the other retired testids (`routine-form-schedule` (EXACT, since `-schedule-error`/`-hint` are live), `-hour`, `-minute`, `-ampm`, `-at-`, `-once-mode`, `-interval`, `-days`, `-day-`) moved to the registry's retired table and `RETIRED_SELECTORS`/`RETIRED_EXACT`; new ids registered (`routine-custom*`, `routine-custom-day-` prefix, `routine-form-repeat`, `-preview`, `-schedule-hint`, `-start-date`, `-start-time`). `scripts/ui_capture.py`'s routines-form surface picks the Every weekday preset. `the_one/agents.md` "Routines (M33)" form bullets and CLAUDE.md's Routines paragraph updated.

**Tests.** `test_flow_agent_routines_form.py` rewritten (31 tests): every preset created from a chosen start (stored shape, sentence, next run), the preset list following the date (last-week and fifth-weekday cases, kept meaning, fallback), the Custom dialog for every unit and each Ends choice, Cancel/Escape and reopening with the current recurrence, range errors, Escape with the ends calendar open closing only the calendar, the two pickers independent, the preview (sentence, next, last, refusal as the schedule error, the month-day warning as a described-by hint, latest response wins via a held first response), the "in" quick start, the operator zone (Kiritimati/Pago Pago against the host date), a spring-forward start (New York), edits of every unit (preset or sentence option above Custom…, untouched schedule not re-sent, the leg 4b read-only cases editable), a past one-off refusal on Save, an unreadable start blocking Save, and a pure-model test. Falsified then restored by editing: the `latest.isCurrent` guard and the `availableMode` fallback (each made its test fail).

**Gate results.** Static guards (`test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`, `test_time_getters_static`, `test_ui_ownership`, `test_area_module_size`, `test_ui_emitted_classes`, `test_nav_helper`, `test_ui_control_inventory`) pass.  `THE_ONE_TEST_NETNS=1 make test-unit`: 8370 passed, 15 skipped (no failure in tools.py or test_routine_tools.py). `agent-routines` lane: 65 passed in 183 s (host load mixed; not a budget reading, against the 240 s budget; leg 8 should re-measure). ruff check and format clean.

**Deviations.** The default Repeat is "Does not repeat" (Google's default; the old form defaulted to Daily). The "in" quick start fills the fields live as the amount or unit changes rather than through a button.

## Decisions

*(In-flight decisions recorded here.)*

## Flight Director Notes

- Planning ran from `main` at `ebb83d8c` on branch
  `flight/03-schedules-and-limits`.
- The operator approved every *(FD)* call in the spec ("looks good to me")
  while the Architect's cycle 1 review was running.

### Design review, cycle 1 (Opus Architect): approve with changes

The four high-severity findings, and how each was fixed:
- **H1, the route move was not "pure".** Two test files build a bare app
  from `api.router` and patch `api.*`.
  - Fix: the routes are included into `api.router`, and the handlers look
    up the `api` helpers lazily.
  - `_RoutineTurnHost` stays in `app.py`, because moving it would create an
    import cycle for about 30 lines.
- **H2, the "after N" counter disagreed with the form's last date.**
  - The operator chose to count from the start, deterministically. The
    `occurrences` column is dropped.
- **H3, the spec never said whether the start is an occurrence.**
  - The start is inclusive when it matches the rule. When it does not, it
    only begins the series *(FD)*.
  - The v47 start is the routine's `next_run_at`, so the next run is
    unchanged.
- **H4, the `agent-routines` lane would be red between legs.**
  - Sentences are now rendered on the server (`schedule_text`, plus a
    preview route).
  - The old form keeps sending the legacy shapes, which DD5 accepts.
  - The integration leg carries a minimal JS adapter.

The medium findings, and how each was fixed:
- **M1, the zone-change path.** New DD12. The query selects by the new
  shape.
- **M2, one-offs across a zone change.** The operator chose to keep the
  instant, which reverses the cycle 0 *(FD)* wall-clock rule for one-offs.
- **M3, minute/hour units.** The anchor stays fixed and `start` is
  rewritten. Re-enabling continues the grid *(FD)*.
- **M4, routines that are off had no bound.** The operator chose
  `ROUTINES_OPEN_MAX = 200` on routines that are not Done.
- **M5, v47.**
  - It uses a frozen converter.
  - The pending `base` takes the routine's migrated schedule verbatim when
    it matches.
  - Resolved proposals are rewritten too.
  - The unreadable path gets named values and a duplicate guard.
  - The column-list pins are updated.
- **M6, sentences.** They come from the server (`POST …/routines/preview`),
  so no calculator is written in JS.
- **M7, leg sizes.** The core is split from the integration, and the
  controls are split from the form, giving 7 legs.
- **M8, DD11.** The collapse now matches on a stable `reason_code` and runs
  in one transaction.
- **M9, minute precision.** Relative starts round up to the minute.
- **M10, retention.** The sweep supersedes pending proposals, and the test
  seam returns the new keys.

The low findings: two citations were corrected, the criterion wording was
softened, and the month-day warning is a field hint linked by
`aria-describedby` rather than `App.ui.notice`.

Suggestions adopted:
- `repeat` and `ends` are optional on input;
- the evals harness maps the new shape back to `kind`, so no re-baseline is
  needed;
- the calculator's search is bounded;
- Escape inside the modal closes only the calendar;
- the controller split adds a script tag, which needs a restart;
- the Purge now confirm wording is updated;
- the migration test pins the fallback zone.

### Design review, cycle 2 (Opus Architect): approve with changes

The cycle 1 fixes held: the `include_router` placement, the pending-base
rule and the DD11 mapping were confirmed against the code. The new findings
were fixed in the spec without a third cycle (the skill allows at most two;
the per-leg design reviews of the high-risk legs re-check them):
- **[high] Spring-forward corruption.** v48 and the DD5 aliases took
  `start.time` from `next_run_at`'s wall time. A 02:30 daily on a
  spring-forward day would have moved to 03:00 for good. Fix:
  `start.time` comes from the legacy `time` field; `start.date` comes from
  `next_run_at`'s date.
- **The leg 2 core collided with live callers.** It is now new code beside
  the old, and leg 4 switches the callers and deletes the old code. The
  caps, retention and skip-collapse work became its own earlier leg with
  v47 (columns only); the schedule rewrite is v48. That makes 8 legs.
- **`_poke_scheduler`** stays in `api.py`, because `put_time_settings` and
  one test call it.
- **DD12, zone changes.**
  - The rewrite now covers routines that are off.
  - It does a compare-and-set on `schedule` and `anchor_at`.
  - It rebases pending proposal bases, so a zone change never makes a
    proposal stale.
- **Instants.** `anchor_at` is now the exact instant for one-offs and
  minute/hour units, and `start` is only how it displays. This closes three
  problems at once: sub-minute precision, the repeated fall-back hour, and
  one-offs across a zone change.
- **A save with no future occurrence** is refused: 422, or 409 at approval
  *(FD)*.
- **One sentence wording,** "Every day at 9:00 AM" *(FD)*. The leg 4 JS
  adapter is specified, including the stale 409 body and the list of
  browser tests it edits.
- **Legacy proposal payloads** fix their start when they are made *(FD)*.
- **Low findings:**
  - an off interval's `anchor_at` is set;
  - `upgrade_failed` sets `started_at`;
  - v48's lazy import of `time_zones`;
  - the proposal-time caps check is named;
  - the 24 h grace for a series' last occurrence is stated;
  - `last_occurrence` is named;
  - the scope of the alias proof is stated;
  - `repeat` null with an `ends` is refused;
  - `routines-no-spam` is added to the eval gate;
  - the plan-token checklist item is fixed;
  - the date picker's `min` is defined for an edit.

### Execution start

- The operator approved the cycle 2 *(FD)* calls by asking to fly the
  flight (`/mission-control:agentic-workflow flight 03 mission 33`). The
  status moved from `planning` to `ready` to `in-flight`.
- **Crew file:** `.flightops/agent-crews/leg-execution.md` (plugin 1.2.3).
  The Developer is Sonnet. The Reviewer is Sonnet when the diff touches a
  security-sensitive surface (caps and retention on agent-written routines
  count), otherwise Haiku. The Accessibility Reviewer is Sonnet for the UI
  batches.
- **Batches,** following the operator's standing preference, each closed by
  a review and a checkpoint commit made by the FD:
  - A: legs 1-2;
  - B: legs 3-4;
  - C: legs 5-7;
  - then leg 8 (behavior re-runs and the gate).
- **Leg 6** (the controls) may run beside Batch B, on disjoint files.
- **Leg 1 tiered low risk.** It is a pure move with the unedited routine
  tests as its characterization net, and the attachment mechanism was
  checked by two Architect cycles. The UI split moves code without changing
  behaviour, and the three squawks are small and test-pinned. No design
  review; the Batch A Reviewer covers it.
- **Leg 2 tiered high risk** (schema v47, routine lifecycle and retention,
  caps on agent-written routines). Its design review (Sonnet, cycle 1)
  returned approve with changes. The findings were applied: 422 at
  approval with the proposal kept pending, the runner's reason codes set
  through `finish()`, the sweep's `running` guard, the missing test pins,
  and the collapse rules. They were clarifications rather than a redesign,
  so no second cycle was run. Status `ready`.
- **Leg 3** (`recurrence-core`) is new code in new modules, with its range
  constants kept out of `limits.py`, so it can run beside leg 2 on
  disjoint files.
- **Leg 3 tiered low risk.** It is additive new modules with no caller, its
  semantics were settled by two Architect cycles, and frozen-clock tables
  prove it. It runs beside legs 1 and 2 on new files only (no `agents.md`
  edit, to avoid concurrent edits). The Batch B Reviewer covers it.
- **Leg 4 designed** (`recurrence-switch`) and tiered high risk: schema
  v48 rewrites stored data, plus lifecycle, scheduler and shared-interface
  changes. Its design review waits until legs 1 and 2 land, so it reviews
  real code.
- **Deviation from DD8:** the evals harness mapping
  (`_collect_routines`, the new shape mapped back to `kind`) moves from
  leg 5 to leg 4. Otherwise `tests/test_evals_routines.py` would go red the
  moment stored schedules change shape.
- **Leg 6 designed** (`date-time-controls`) and tiered low risk. The
  controls are additive in the library, on a single surface. They run beside
  leg 2 on disjoint files (`js/ui/`, `components.css`, `index.html`, the
  inventory, new contract tests). Batch C's Reviewer and Accessibility
  Reviewer cover them. Leg 1 also edited `index.html` (a studio script tag)
  and is landed, so no concurrent edit to it is in progress.

### Leg 2: caps-retention-and-skips

**Built.**
- Caps: `ROUTINES_ACTIVE_MAX` 50 and `ROUTINES_OPEN_MAX` 200 with `check_routine_caps(before, after)`
  (raise-only) in `limits.py`; the repository's `create`/`update` run it always, inside the write
  transaction (precheck, caps, write, proposal); `agent_caps` left the repository and now means only
  the agent minimum lead time in the service. Removed `ROUTINES_PER_AGENT_MAX`,
  `AGENT_ACTIVE_ROUTINES_MAX`, `AGENT_RUNS_PER_DAY_MAX`, `runs_per_day`, `AGENT_PROPOSALS_KEPT`,
  `_prune` (grep clean over `the_one/` and `tests/`). `limits_view` returns `active_max`/`open_max`.
- Retention: `AgentRoutineRepository.delete_done_older_than` (supersedes pending proposals, skips a
  routine with a `running` run), `RoutineProposalRepository.delete_resolved_older_than` and
  `delete_resolved_for_agent`; the sweep result and the purge-sweep seam carry `routines_deleted` and
  `proposals_deleted`; Purge now carries `proposals_deleted`. No UI change (the app wrapper passes
  the result through).
- v47: `agent_routine_runs.repeats` and `reason_code` (guarded ALTERs; the v45 CREATE is untouched, so
  replay and upgrade both reach v47 by the ALTER). `RoutineRun` fields, runs repository read/write.
- Skips: codes `still_running` (scheduler), `chat_busy`, `waiting_sign_in` (runner, via
  `finish(..., reason_code=)`); `classify` stays a 2-tuple (the code is set beside its call where the
  outcome is `skipped`). The collapse is `RoutineRunRepository.record_still_running_skip`.
- `_LIMITS_SENTENCE` changed (tool text, platform prompt text): "At most 50 active routines and 5
  changes a turn. Your operator may need to approve." **Leg 5's eval run covers this change.**
- Docs: `the_one/agents.md` (caps, retention, v47, reason codes, REST limits line), `SECURITY-MODEL.md`
  (caps paragraph, the proposals-record bullet). CLAUDE.md names no removed cap.

**Tests.** Rewritten/renamed: proposals (caps, pending limit, no count pruning, resolved delete),
repository (`test_active_cap_inside_every_write`, `test_open_cap_and_done_routines_do_not_count`),
service (active cap, lowering edits over the cap, approval recheck), self-config API
(`test_caps_recheck_422` with the DD3 sentence and the proposal still pending;
`test_approve_rename_passes_while_over_the_cap`), retention (resolved proposals, Done routines incl.
the running-run guard and the superseded pending proposal), api (Purge now proposals, seam keys, runs
columns, limits dict), scheduler (reason code, three-skip collapse, no merge across an ok row, a
pre-v47 row or another routine), runner (`chat_busy`, `waiting_sign_in` codes), `TestSchemaV47` and
the `== 46` pins moved. Falsified: the collapse condition and the sweep's routine delete each made
their test fail, then were restored by editing.

**Gate results.** `THE_ONE_TEST_NETNS=1 make test-unit`: 8386 passed, 15 skipped, 1 failed:
`tests/test_ui_library_source.py::test_file_touches_no_app_globals[date-time.js]`, caused by another
crew's untracked `static/js/ui/date-time.js` (reads `App.time`), not by this leg. The `agent-routines`
lane alone: 52 passed. ruff check and format clean.

**Deviations.** The leg guided adding the new columns to the fresh `CREATE TABLE` too; v45's CREATE
is left alone and v47's ALTER covers both paths (a fresh replay runs v45 then v47).

**Anomalies.** Tests that seeded an agent past 50 routines through the repository now insert raw
rows, since the repository enforces the cap for operators too.

- **Leg 5 designed** and tiered low risk: it changes one tool-description
  constant, and the eval comparison is its gate. It refines DD8:
  - the full `m30-platform` run is skipped if `measure-prompt` shows the
    routines-off prompt unchanged, because the routine tool text is never in
    those prompts;
  - the routines set is compared against `m33-routines` with no
    re-baseline.
- **Batch A regrouped to legs 1, 2, 3 and 6.** All four had landed.
  `index.html` carries edits from leg 1 (the self-configuration script tag)
  and leg 6 (the `date-time.js` tag), and partial staging is not available
  here, so the four are reviewed and committed together. Batch B is legs 4
  and 5, Batch C is leg 7, then leg 8.
- **Leg 6 spec defect.** It told the date picker to read `App.time`, which
  the library guard forbids
  (`tests/test_ui_library_source.py::test_file_touches_no_app_globals`).
  Leg 2's unit run caught it. A fix Developer moves "today" to a
  caller-supplied `today` option before the Batch A review.
- **Leg 4 design review (Sonnet, cycle 1): approve with changes, applied.**
  - **Split into 4a and 4b** (two Developer passes, landed together):
    - 4a is the backend and the unit tier;
    - 4b is the JS adapter, browser tests and docs.
  - **Verbatim schedule pairs** for proposals and for immediate agent
    writes, with `start` re-rendered by `rezone` at approval.
  - **DD1 amended:** approval with no runs left is a **422**, not a 409.
  - **No-runs-left refusals** apply whether the routine is on or off
    *(FD)*, and re-enabling a routine with no runs left is refused.
  - **Views** take a zone. Unreadable schedules never cause a 500.
  - **The JS form mapping** requires `ends: never` and a start that is not
    in the future.
  - **Specified in detail:** the v48 details, the DD12 repository methods,
    the legacy cleanup and the test inventory.

  No second cycle: the changes add specification inside the existing
  design.

## Batch A review fixes

1. Lint (E501/format) in `test_descriptions_state_the_limits`: wrapped; ruff check and format clean. Test: tests/test_routine_tools.py.
2. Time field inventory row no longer lists `today`. Test: tests/test_ui_control_inventory.py.
3. leg-execution.md overlong line wrapped.
4. Load-error line: role removed before setError (restored after clear). Test: test_flow_agent_editor_frame.py (squawk 0273 test).
5. Date/time error node is a polite live region present in the DOM (display toggled, not hidden); inventory rows updated. Tests: test_ui_date_picker_contract.py, test_ui_time_field_contract.py (aria-live assertion).
6. Checked+disabled day gets its own muted style (opaque --btn-disabled tokens). Test: test_days_variant_checked_disabled_looks_disabled.
7. Forced-colors block for day toggles and the selected date-grid day (CSS only; not automatable in the contract engines, accepted).
- **Batch A review.**
  - **Code Reviewer** (Sonnet, the security-sensitive tier: caps and
    retention on agent-written routines): confirmed. The one blocking item,
    an E501 lint failure in `tests/test_routine_tools.py`, was fixed.
  - **Accessibility Reviewer** (Sonnet): confirmed with non-blocking items,
    all fixed:
    - the load-error role is removed first;
    - polite live errors in the date and time controls;
    - a checked and disabled day looks disabled;
    - forced-colours styling.
  - **No re-review:** the fixes are small and test-pinned, the same call as
    in Flight 2.
  - **Fix-pass gates:**
    - unit: 8387 passed, 15 skipped;
    - `contracts-controls`: 1160 passed, 4 skipped;
    - `test_flow_agent_editor_frame.py`: 8 passed;
    - ruff clean over `the_one/ tests/ scripts/ evals/`.
  - Legs 1, 2, 3 and 6 are `completed`. The squawk 0232, 0273 and 0284
    sign-offs are filled in.
- **Batch A committed** as `54d87b8a`. Leg 4a (the backend) started.
- **Leg 7 designed** (`recurrence-form`). It is tiered medium. It is UI
  only, on the established library, but it retires testids and adds a
  dialog. No separate design review: its contract is DD7 plus legs 4 and 6,
  which are already reviewed, and Batch C's code and Accessibility
  Reviewers cover it. It runs after leg 4b, because both edit
  `routines-form-model.js`.
- **Leg 4a handed back** ([HANDOFF:review-needed]):
  - unit tier: 8369 passed, 15 skipped;
  - ruff clean.
- **Incident:** a falsification helper script truncated
  `the_one/routines/scheduler.py`. The Developer rebuilt the file from
  `git show HEAD:` plus its edits, and all 43 scheduler tests pass. This is
  the falsify-by-whole-file risk in another form, despite squawk 0284's
  rule. It is flagged for the Batch B Reviewer to diff `scheduler.py`
  against HEAD line by line, and for the debrief.
- **Legs 4b and 5 run in parallel.**
  - Their files are disjoint: 4b touches JS, browser tests and docs; 5
    touches `tools.py` description text, `test_routine_tools.py` and the
    eval runs.
  - Leg 5's model runs load the host, so leg 4b's lane timings are not
    budget readings. This repeats Flight 2's parallel legs 4 and 5.
- **Leg 4 landed** (pass 4b). The `agent-routines`, `agents` and `chats`
  lanes pass, under load 6-12. Unit: 8369 passed, 15 skipped, 1 failed:
  `test_chat_history_purge.py::test_purge_loop_catch_up_sweeps_due_db`
  failed under load and passed alone, so it is watched at the gate.
  - **Interim limit until leg 7:** a new daily created after its time of
    day has tomorrow as its start, so the old form opens it read-only.
- **Batches B and C merged.** Leg 5's `tools.py` description edit sits in
  the same file as leg 4a's `tools.py` changes, so leg 4 cannot be
  committed apart from leg 5. Leg 7 starts now beside leg 5's evals
  (disjoint files), and one review covers legs 4, 5 and 7.

## Batch B review fixes

- Form a11y: the "Or start in" inputs are named "Start in, amount" and "Start in, unit" (testids kept); a schedule error now sets `aria-invalid` on the control it concerns (Repeat select; start date or time when that is empty or the message is about the start) and joins the error line's id to its `aria-describedby`, cleared with the error and re-applied after the Repeat hint is rewritten; the months radio group's legend is "Repeat on day of month".
- Scheduler: `_follow_zone` skips a routine whose stored schedule cannot be read (v48 `upgrade_failed`) with a debug log instead of an exception per zone change; unit test added (fails without the fix).
- **Batch B review** (legs 4, 5 and 7).
  - **Code Reviewer** (Sonnet): confirmed, with no blocking issues.
    - It diffed `scheduler.py` against HEAD line by line: only the intended
      changes are there, and nothing was lost in the 4a incident.
    - It probed the v48 converter directly.
  - **Accessibility Reviewer** (Sonnet): confirmed.
  - **Fixed in one pass:**
    - the "Start in" labels;
    - the schedule error tied to its control (`aria-invalid` and
      `aria-describedby`);
    - the months legend;
    - a quiet skip of unreadable schedules on a zone change, with a test.
  - **Left for Flight 4's walk:**
    - "Custom…" opens on `change`, so arrowing onto it opens the dialog
      (Google behaves the same);
    - the preview announcement at form open.
  - **Gates after the fixes:**
    - unit: 8371 passed, 15 skipped;
    - `agent-routines`: 65 passed;
    - ruff clean.
  - Legs 4, 5 and 7 are `completed`.
