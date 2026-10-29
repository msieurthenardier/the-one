# Flight: Schedules and Limits

**Status**: in-flight
**Mission**: [Routines](../../mission.md)

## Contributing to Criteria

- [ ] **The operator manages an agent's routines** — the schedule becomes a
      calendar-style recurrence (start, repeat every N units, ends), set
      through a Google Calendar-style form with presets and a Custom panel.
- [ ] **Routines run on time, unattended** — the new recurrence runs in the
      operator zone across daylight-saving changes and ends when told to.
- [ ] **Unattended runs are honest** — runs skipped because the previous run
      is still going collapse into one history row with a count.
- [ ] **An agent schedules its own routines when allowed** — the agent's
      tools take the same recurrence; the shapes it uses today still work.
- [ ] **Injected content cannot plant a routine unnoticed, and routines are
      bounded** — one active-routine cap and one routine-count backstop for
      everyone; no separate runs-a-day cap (operator decision, trade-off
      recorded in DD3).
- [ ] **Routines follow their agent** — finished routines and resolved
      proposals age out with the agent's retention policy; the v48 migration
      upgrades every existing routine with its next run unchanged.

This flight is not in the mission's original plan. It came out of Flight 3
planning (2026-10-29), when the operator reviewed the Flight 1 and 2
judgement calls on caps, retention, the `default` agent and the schedule
form, and chose to replace the five fixed schedule kinds with a calendar
recurrence. The mission's HAT moves to Flight 4.

---

## Pre-Flight

### Objective

Replace the five fixed schedule kinds (once, daily, weekdays, weekly, every N
hours) with one calendar recurrence — a start date and time; repeat never, or
every N minutes, hours, days, weeks (on chosen days), months (on a day or an
nth weekday) or years; ending never, on a date or after N occurrences — set
through a Google Calendar-style form, and taken by the agent's tools in the
same shape. Rework the limits the operator reviewed: one active-routine cap
and one count backstop for everyone, a 1-minute floor, no runs-a-day cap, and
retention for finished routines and resolved proposals. Carry the
maintenance that shares these surfaces: move the routine routes out of
`api.py`, split the agent editor's controller, squawks 0232, 0273 and 0284,
and headroom for the `routing` and `agents` lanes. Flight 4 (the HAT) walks
the result.

### Open Questions

Resolved with the operator in planning on 2026-10-29 unless marked *(FD)*.
*(FD)* marks a planning-level detail the Flight Director chose. The operator
approved the cycle-0 *(FD)* calls; the cycle-1 review changed two of them
with the operator's answer (DD1 one-offs, DD2 counting) and added the rest,
which are listed in the flight log for Flight 4's walk.

- [x] Total vs active cap → DD3 (one active cap of 50, plus a 200 backstop
      on routines that are not Done)
- [x] Interval floor → DD1/DD3 (1 minute)
- [x] Runs-a-day cap → DD3 (dropped)
- [x] Per-turn write cap → DD3 (stays 5)
- [x] Proposals kept → DD4 (agent retention, not a count)
- [x] Finished one-offs → DD4 (age out with retention)
- [x] The `default` agent → DD10 (keeps refusing; reserved)
- [x] The schedule form → DD1, DD7 (calendar recurrence, Google-style)
- [x] Month day missing in a month → DD2 (skip, with a form warning)
- [x] What "after N occurrences" counts → DD2 (the Nth occurrence counted
      from the start; missed, skipped and turned-off occurrences count)
- [x] Units → DD1 (minutes 1-1439, hours 1-168, days, weeks, months, years)
- [x] A one-off across a zone change → DD12 (keeps its instant)
- [x] The flight split → this flight, then Flight 4 HAT
- [x] Maintenance in scope → DD9 (all six items; the turn-host move dropped
      on review, see DD9)
- [x] Legacy schedule shapes on input → DD5 *(FD)*
- [x] A start that does not match its own rule → DD2 *(FD)*
- [x] Turning a minute/hour routine back on → DD2 *(FD)*
- [x] Week start for "every N weeks" → DD2 *(FD)*
- [x] Custom panel inline or modal → DD7 *(FD)*
- [x] Purge now and proposals → DD4 *(FD)*
- [x] Where sentences and previews are computed → DD7 *(FD)*
- [x] A save that leaves no future occurrence → DD1 (refused) *(FD, cycle 2)*
- [x] One sentence wording for UI and tools → DD7 *(FD, cycle 2)*
- [x] Pending proposals across a zone change → DD12 (rebased) *(FD, cycle 2)*
- [x] Legacy proposals' start → DD5/DD6 (fixed at proposal time) *(FD, cycle 2)*

### Design Decisions

#### DD1. The recurrence (one stored shape)

The stored `agent_routines.schedule` JSON becomes one shape for every
routine, operator or agent:

```json
{
  "start":  {"date": "YYYY-MM-DD", "time": "HH:MM"},
  "repeat": null | {
    "every": N,
    "unit": "minute" | "hour" | "day" | "week" | "month" | "year",
    "days":  [0-6],                                   // week only; 0 is Monday
    "month_by": {"by": "day"} | {"by": "weekday", "nth": 1|2|3|4|-1}  // month only
  },
  "ends": {"kind": "never"} | {"kind": "on", "date": "YYYY-MM-DD"}
        | {"kind": "after", "count": N}
}
```

- **The stored dict is fully normalized**: `days` sorted and unique, no
  absent-vs-null or extra keys, `repeat: null` with `ends` `{"kind":"never"}`.
  The stale check compares dicts, so one value has one form. An input with
  `repeat: null` and an `ends` other than never is refused (422, "A routine
  that does not repeat has no end to set.").
- **Two kinds of start (cycle 2):**
  - **Instant-anchored: one-offs and minute/hour units.** The exact first
    instant is stored in `anchor_at` (UTC, at the precision the input named:
    `at`, `in`, or a migrated `next_run_at` with its microseconds). Every
    calculation uses `anchor_at`; `start` is only its wall-clock rendering in
    the current zone, for display and the form. This keeps an instant in
    the repeated fall-back hour exact (a `{date, time}` with fold 0 cannot
    name it) and makes a zone change a display rewrite (DD12). "Every 90
    minutes" stays 90 minutes across a daylight-saving change.
  - **Wall-clock: day, week, month and year units.** `start` is
    authoritative and `anchor_at` is null. Occurrences fall at `start.time`
    in the operator zone, with today's daylight-saving rules
    (`resolve_wall_time`: a time in the spring-forward gap runs once at the
    end of the gap; a repeated time runs once, on its first occurrence).
  - A `start` typed in the form for an instant-anchored schedule resolves
    once, at save, through `resolve_wall_time` in the effective zone, and
    that instant becomes `anchor_at`.
- **`repeat: null`** is "Does not repeat", today's one-off.
- **A save that leaves no future occurrence is refused** *(FD, cycle 2)*:
  create, a schedule edit and approval of a pending create or schedule change
  fail with "This schedule has no runs left." (422 on REST and the preview, the
  tool's refusal for the agent, and a 409 at approval that leaves the proposal
  pending for the operator to dismiss). Today's `MSG_PAST` for a one-off in
  the past becomes this case. The preview says so before Save.
- **Ranges:**

  | Field | Range |
  |---|---|
  | `every` with `minute` | 1-1439 |
  | `every` with `hour` | 1-168 (today's range) |
  | `every` with `day` | 1-365 |
  | `every` with `week` | 1-52 |
  | `every` with `month` | 1-12 |
  | `every` with `year` | 1-10 |
  | `days` | at least one, each 0-6, required for `week` only |
  | `ends.count` | 1-1000 |
  | `ends.date` | on or after `start.date` |
  | `start` | at most a year ahead (today's one-off rule) |

- **Rationale**: one shape for operator and agent, the calendar model people
  already know, and every existing kind maps onto it exactly (DD6). Still
  hand-rolled, with no date library (the project has no `dateutil`; the
  existing calculator already carries the daylight-saving rules).
- **Trade-off**: a bigger calculator, a data migration and a new form,
  against five kinds that already worked.

#### DD2. Occurrence rules

- **The start is the first occurrence when it matches the rule** (every
  unit). When it does not — a weekly start on a Wednesday that repeats on
  Mondays, an API-supplied month-by-weekday whose nth differs from the
  start date's — the start only begins the series, and the first occurrence
  is the first one matching the rule at or after the start instant *(FD)*.
- **Week:** the chosen `days`, in weeks counted from the week (Sunday to
  Saturday) holding `start.date` *(FD: Sunday-first, as the form shows
  S M T W T F S)*; every N weeks takes every Nth such week.
- **Month, by day:** day-of-month of `start.date`. A month without that day
  is **skipped** (operator decision). Every N months counts calendar months
  from the start month.
- **Month, by weekday:** the nth weekday of the month, with `nth` 1-4 or -1
  for the last. The form offers the start date's nth (1-4), and "last" when
  the start date is in the month's final 7 days, as Google does.
- **Year:** month and day of `start.date`; February 29 occurs only in leap
  years (skipped otherwise, with the form warning).
- **Ends on a date:** the last occurrence is the last one on or before that
  date, inclusive, in the operator zone.
- **Ends after N** (operator decision): the Nth occurrence **counted from
  the start**, deterministically. Every occurrence the rule produces counts,
  whether it ran, was missed, was skipped, fell before the routine was saved
  or fell while the routine was turned off. Run now does not count. There is
  no stored counter: `next_run` returns None after the Nth occurrence, so the
  form's "last on" date is always exact, and raising "after 10" to "after 12"
  adds exactly two.
- **The form's default start** is the next whole hour after now, so a new
  routine loses no occurrence to a start in the past.
- **Turning a minute or hour routine back on** continues its grid from
  `anchor_at` (the next grid point after now) *(FD)*. This replaces today's
  re-anchor to now on re-enable (`service.update_routine`), so an "after N"
  count and the summary stay true.
- **Done:** a routine whose recurrence has no next occurrence (a one-off
  that ran, an ended recurrence) gets `finished_at` and `next_run_at` null,
  as a one-off does today, and shows "Done". Saving a schedule with a future
  occurrence reopens it.
- **The calculator's search is bounded explicitly**: February 29 can be
  eight years away (2096 to 2104), and month-day skips span months. Past the
  bound, or past `ends`, it returns None, and a test proves that None makes
  the routine Done.
- **Grace and catch-up** keep today's formula (24 h for a one-off,
  otherwise min(half the gap to the next occurrence, 2 h)). The last
  occurrence of an ended series has no next occurrence, so it gets the
  one-off's 24 h, as `grace()` does today when `next_run` is None
  (intended: it is the series' last chance, like a one-off).

#### DD3. Caps (operator decisions)

- **`ROUTINES_ACTIVE_MAX = 50`, one active-routine cap for every write**,
  the operator's REST routes and the agent's tools alike. Active means
  enabled and not Done. Raise-only: a write is refused only when it raises
  the active count and leaves it over 50 (create enabled, enable, reopen a
  Done routine). A rename, a prompt edit or a change that lowers the count
  always passes. Run now never counts. Refusal: "This agent already has 50
  active routines, the most allowed. Turn one off or delete one first."
- **`ROUTINES_OPEN_MAX = 200`, a backstop on routines that are not Done**
  (on or off), for every write, raise-only in the same way (operator
  decision). It bounds routines turned off and kept, which never age out;
  Done routines age out with retention (DD4). Refusal: "This agent already
  has 200 routines that are not done, the most allowed. Delete some first."
- Both caps are checked in the repository's write transaction, at the
  position today's agent caps hold (DD4 of Flight 2: precheck, caps, write,
  proposal), at proposal time (`agent_change` → `insert_pending(caps_check=…)`,
  today's `check_agent_caps`) and again at approval.
- **Removed:** `ROUTINES_PER_AGENT_MAX` (the 50-row total, which counted
  finished routines), `AGENT_ACTIVE_ROUTINES_MAX` (10),
  `AGENT_RUNS_PER_DAY_MAX` (48) and `runs_per_day`.
- **The trade-off the operator accepted:** with no runs-a-day cap,
  frequency is bounded only by the active cap times the 1-minute floor (50
  x 1,440 = 72,000 turns a day in the worst case). What holds an injected
  high-frequency routine is its "Check this" flag and approval, which is on
  by default. A 1-minute routine still writes a run row (and, with a
  new-chat-each-run target, a chat) every minute; retention bounds them.
  `SECURITY-MODEL.md` "Routines" records this.
- **Unchanged:** 5 routine writes per turn (operator decision: "if bulk
  becomes a thing we can address it later"), a one-off at least 1 minute
  ahead for the agent, 20 pending proposals, a 4000-character prompt, a
  start at most a year ahead.
- `limits_view()` (the `limits` key of `GET …/routines`) and the agent
  tools' limits sentence follow.

#### DD4. Retention (operator decisions, except as marked)

- **Finished routines age out.** The daily purge sweep
  (`retention.run_purge_sweep`) also deletes each agent's routines whose
  `finished_at` is older than that agent's retention cutoff, of either
  origin; their run rows cascade. Before deleting, it supersedes the
  routine's pending proposals, as `AgentRoutineRepository.delete` does, so
  the `routine_id ON DELETE SET NULL` never turns one into a "gone" 409.
  The sweep result gains `routines_deleted`.
- **Resolved proposals age out.** The sweep deletes each agent's proposals
  with a status other than `pending` whose `resolved_at` is older than the
  cutoff. Pending rows are never purged by age (the 20-pending cap bounds
  them). The `AGENT_PROPOSALS_KEPT` prune (`proposals.py` `_prune`, called
  from `insert_applied`, `resolve` and `insert_pending`) is removed. The
  sweep result gains `proposals_deleted`.
- **`POST /api/_test/purge-sweep`** returns the two new keys.
- **Purge now** (`DELETE /api/agents/{name}/chat/sessions`) clears the
  agent's chats and run history today; it now also clears resolved
  proposals *(FD: they are history like runs)*, never routines or pending
  proposals. Its confirm wording says so.
- This reverses Flight 2's DD10 ("proposals are never purged");
  `the_one/agents.md` and `SECURITY-MODEL.md` say so.

#### DD5. Input shapes: canonical, plus legacy aliases *(FD)*

- **REST, the preview route and the agent tools accept the DD1 shape**,
  with `repeat` optional (absent means null) and `ends` optional (absent
  means never), so "check back in 2 hours" stays short.
- **A relative start** is accepted inside the new shape,
  `"start": {"in": {"amount": N, "unit": "minutes|hours|days"}}`, resolved
  at save to now plus the amount **rounded up to the next whole minute**,
  then checked against the agent's 1-minute minimum.
- **Today's shapes are accepted and normalized on input:**
  - `{"kind":"once","at":<UTC>}` and `{"kind":"once","on":{date,time}}` →
    that instant, `repeat` null (`at` rounded up to the minute);
  - `{"kind":"once","in":{amount, unit}}` → as the relative start above;
  - `{"kind":"daily","time"}` → every 1 day; `weekdays` → every 1 week on
    0-4; `weekly` → every 1 week on `days`. `start.date` is the local date
    of the next occurrence of that rule at or after now, and `start.time` is
    the legacy `time` field, never the resolved instant's wall time (a
    spring-forward gap would otherwise store the post-gap time for good).
    Today's first run is unchanged;
  - `{"kind":"interval","hours":N}` → every N hours with `anchor_at` at now
    plus N hours, exactly (today's first run at anchor + N hours).
- **Proposals fix their start when they are made.** A legacy-shaped agent
  change is normalized at proposal time, so an approved interval runs on a
  grid anchored at proposal time, not approval time as today; a daily or
  weekly one starts on the proposal's date. A late approval that leaves no
  run is refused (DD1).
- **Only the canonical shape is stored and returned.**
- **Rationale**: the two behavior specs, the eval scenarios and any model
  that learned today's shapes keep working, and the old form keeps
  working against the new backend from leg 4 until leg 7 replaces it.
- **Trade-off**: two input vocabularies to test. The tool descriptions
  document only the canonical shape and the `in` start (DD8), so the
  aliases cost no tokens.

#### DD6. Migrations v47 and v48

Two versions in `the_one/db/schema.py`, idempotent, in the v42-v46 style,
landed by different legs (cycle 2 split):

**v47 (leg 2), columns only:**
- `agent_routine_runs.repeats INTEGER NOT NULL DEFAULT 1` (DD11);
- `agent_routine_runs.reason_code TEXT` (DD11; null on existing rows).

**v48 (leg 4), the schedule rewrite:**
- **A frozen converter.** v48 rewrites schedules with a converter defined
  inside the v48 block, including its own parsing of the legacy shapes, not
  the live DD5 normalizer or `schedule.validate`, so a later change to either
  never changes what v48 did (`schema.py`'s frozen-literal convention). Its
  fallback zone comes from `the_one.time_zones.load_effective_zone`
  (tzlocal), a new import for `schema.py`, imported lazily inside the block.
- **Every stored routine schedule is rewritten** to the DD1 shape. The zone
  is the one the stored `next_run_at` values were computed in
  (`app_metadata` `routines_zone`), falling back to the effective zone.
  - **daily, weekdays, weekly:** `start.date` is the local date of
    `next_run_at` (or, when off or Done, of `created_at`), and `start.time`
    is the legacy `time` field, never `next_run_at`'s wall time (cycle 2: a
    02:30 daily on a spring-forward day has a `next_run_at` whose wall time
    is 03:00). `anchor_at` stays null.
  - **interval:** `anchor_at` becomes `next_run_at` exactly (microseconds
    kept) when set; when off, `anchor_at + hours`, so the grid is identical
    either way. `start` is its rendering.
  - **once:** `anchor_at` becomes `at` exactly; `start` is its rendering.
  - `next_run_at` is not recomputed.
- **Proposals:** the schedules in `payload` and `base` of every proposal are
  rewritten, pending and resolved (so the history queue renders one shape).
  - `base`: if `base.schedule` equals the routine's pre-migration schedule,
    it takes the routine's migrated schedule (and `anchor_at`) verbatim;
    otherwise it is converted on its own (it is stale either way).
  - `payload`: converted like an off routine, using the proposal's
    `created_at` (DD5's "proposals fix their start when they are made").
- **A schedule that cannot be read** (hand-edited, corrupt) is left as is,
  the routine is turned off, and one run row is written with `trigger_kind`
  `schedule`, `outcome` `failed`, `reason_code` `upgrade_failed`,
  `started_at` and `finished_at` set to the migration time (so
  `RoutineRunRepository.latest` shows it), and "This schedule could not be
  upgraded. Edit it to turn the routine back on.", guarded so a rewind
  re-run inserts no duplicate. The migration never fails startup over one
  routine.
- **Tests:** `TestSchemaV47` (columns, rewind) and `TestSchemaV48` in
  `tests/test_db_migration.py` — each legacy kind converted, enabled and
  off, with its next run unchanged under a frozen clock, including a 02:30
  daily across a spring-forward `next_run_at` and an interval with
  microseconds; with and without `routines_zone` (the fallback zone pinned
  through `frozen_clock`); pending and resolved proposal rewrites, including
  a stale base; idempotent rewind; the unreadable path. Every `== 46` pin and
  the `_ROUTINE_COLS`/`_RUN_COLS` column lists move.

#### DD7. The form (Google Calendar pattern) and where sentences come from

- **Sentences and previews come from the server** *(FD)*. The one Python
  calculator and `routines/describe.py` produce every schedule sentence:
  - the routine view gains `schedule_text`; each proposal view gains the
    sentence for its payload, base and current schedule;
  - a new `POST /api/agents/{name}/routines/preview` takes `{schedule}`
    (any DD5 input) and returns `{schedule (normalized), text, next_runs
    (the next three instants), last_occurrence (null for "never"),
    warnings}`, or the create route's 422 (including "This schedule has no
    runs left."). It writes nothing and joins `EXEMPT` in
    `tests/test_api_name_rule.py`.

  The browser's `routines-describe.js` keeps only target and time
  formatting; its schedule sentence is retired. No calculator is
  duplicated in JavaScript.
- **One wording** *(FD, cycle 2)*: sentence case, starting "Every …":
  "Every day at 9:00 AM", "Every weekday at 9:00 AM", "Every week on Tue,
  Thu at 9:00 AM", "Every 90 minutes", "Once, on Thu, Oct 29, 2026 at
  3:00 PM", with ", until {date}" or ", {n} times" appended. The UI shows
  it as is; the tool results embed the same text (Python today writes
  "every day at 9:00 AM" mid-sentence, so tool-result phrasing around it is
  adjusted). The change reaches the agent's tool results, so leg 5's eval
  runs include it.
- **Leg 4's minimal JS adapter** keeps the old form and the `agent-routines`
  lane working on the new shape until leg 7:
  - the Routines tab list renders `schedule_text`;
  - the approval queue renders the proposal sentences for payload, base and
    current, **including the stale 409 body** (`current_value`/`base_value`/
    `proposed_value` from the approve route, rendered through `columnsView`):
    the route adds a sentence for each;
  - `bodyToFormState` maps a canonical schedule onto the old form's five
    kinds where it can (`repeat` null → once, with `start` as the at-day
    and time, no zone conversion; every 1 day → daily; every 1 week on 0-4
    → weekdays; every 1 week → weekly; every N hours → interval), still
    accepts legacy-shaped rows, and opens any other shape with the schedule
    fields read-only and a note "Edit this schedule after the form update.";
    because `formToBody` sends only changed fields, an untouched schedule is
    never re-sent, which is the intended safeguard;
  - the old form keeps sending the legacy shapes, which DD5 accepts;
  - the drawer needs nothing (`agent-drawer-parts.js::routineMeta` reads
    only `finished_at`, `enabled` and `next_run_at`);
  - the browser tests that assert the old wording or call
    `describeSchedule` directly are updated in leg 4:
    `test_flow_agent_routines.py` (about `:170-188`, `:216`),
    `test_flow_agent_routines_form.py` (about `:99`, `:154`, `:168`,
    `:335`, `:460`), `test_flow_agent_routines_self_config.py` (about
    `:230`, `:308`, `:528`, `:539`).
- **The form** (`routines-form.js`, `routines-form-model.js`; expect
  `routines-form.js`, at 419 lines, to split for the Custom panel):
  - **Starts:** a date (the new date picker) and a time (the new time
    field), defaulting to the next whole hour. The picker's `min` is today
    for a new routine; editing a routine whose start is already past keeps
    that date selectable (`min` is the earlier of today and the stored
    start). "In … minutes/hours/days"
    stays as a quick way to set the start.
  - **Repeat:** an `App.ui.select` of presets computed from the start date,
    in Google's order: "Does not repeat"; "Every day"; "Every weekday
    (Monday to Friday)"; "Weekly on {weekday}"; "Monthly on day {d}" or
    "Monthly on the {nth} {weekday}"; "Annually on {Month} {d}"; "Custom…".
    An edited routine whose recurrence matches no preset shows its sentence
    as a selected extra option above "Custom…".
  - **Custom…** opens an `App.ui.modal` titled "Custom recurrence" *(FD:
    mirrors the operator's reference screenshot)*: "Repeat every" (a number
    and a unit select: minutes, hours, days, weeks, months, years); "Repeat
    on" (the day toggles, weeks only); a month choice (day vs nth weekday,
    months only); "Ends" (Never / On {date picker} / After {number}
    occurrences); Cancel and Done. Done applies to the form; Save saves.
  - **The preview line** under the repeat choice shows the server's `text`,
    next run and last occurrence, debounced on change (latest request wins,
    `App.ui.util.latest`).
  - **Warnings** from the preview ("Some months have fewer than {d} days.
    Those months are skipped.", and the February 29 equivalent) show as a
    field hint linked by `aria-describedby` (not `App.ui.notice`, which is
    the transcript line control).
- **Library controls** (new, `js/ui/`, each with a
  `docs/ui-control-inventory.md` row and engine-parametrized contract tests
  in Chromium and WebKit):
  - **`App.ui.datePicker`**: a typed date input showing "Thu, Oct 29,
    2026", with a calendar popover (a button opens a month grid; arrow keys,
    Page Up/Down, Home/End, Enter, Escape; `min`/`max`; "today" from
    `App.time`, never the host zone). Escape inside a modal closes only the
    calendar.
  - **`App.ui.timeField`**: a typed time ("9:30 AM", "21:30", "9:30p"),
    validated on blur, shown back as 12-hour (M25 DD14).
  - **Day toggles**: seven circular checkboxes S M T W T F S in a fieldset
    named "Repeat on", an `App.ui.checkboxGroup` variant if that fits, a new
    factory otherwise (native checkbox semantics either way).
- **Testids** go in `docs/ui-testid-registry.md`; the old time selects'
  testids move to its retired table and `RETIRED_SELECTORS`.

#### DD8. Agent tools and evals

- `schedule_routine` and `change_routine` take the DD1 shape (with the DD5
  `in` start and optional `repeat`/`ends`). `_SCHEDULE_SHAPES` and
  `_LIMITS_SENTENCE` in `routines/tools.py` are rewritten;
  `list_my_routines` and the tool results carry the DD7 sentences.
- **Evals** (Mission 30 convention; tool descriptions are platform prompt
  text): `measure-prompt` for the token cost, then `compare` against
  `m30-platform` (routines off, so its size must be unchanged) and against
  `m33-routines` (routines on).
  - `evals/harness.py::_collect_routines` maps the stored shape back to the
    `kind` the checks read (`repeat` null is "once"), so the scenario TOML
    and `checks.py` keep their vocabulary. The fingerprint covers scenario
    TOML, fixtures and judge only, so no re-baseline is needed.
- **The gate:** no hard failure in either comparison; `routines-follow-up`,
  `routines-no-spam` and `routines-planted` within their bars on both
  models.

#### DD9. Maintenance carried in (operator decision: all six)

- **Move the routine routes** (the "Routines" block of `api.py`: operator
  routes, self-configuration routines routes, proposals, Run now, runs)
  into `the_one/interfaces/web/routines_api.py`, whose router is attached
  with `router.include_router(routines_router)` at the bottom of `api.py`.
  - The routes stay in `api.router.routes`, so every test app built on
    `api.router` gets them and `tests/test_api_name_rule.py` keeps
    classifying them.
  - The moved handlers reach `get_connection`, `get_encryptor`,
    `_chat_repo`, `_load_agent_or_404` and the other `api.py` helpers
    through the `api` module at call time (a lazy
    `from the_one.interfaces.web import api`), so the tests' patches of
    `the_one.interfaces.web.api.*` still apply.
  - The routes move to the end of the router; there are no `:path` routes
    under `/agents/{name}` to shadow them.
  - **`_poke_scheduler` stays in `api.py`** (cycle 2): `put_time_settings`
    calls it and `tests/test_routines_scheduler.py::test_poke_scheduler_tolerates_none`
    calls `api._poke_scheduler()`. The moved handlers reach it lazily or
    call `routine_service.poke_scheduler`.
  - A pure move: the routines API, self-configuration, scheduler, runner and
    name-rule tests pass unedited.
- **`_RoutineTurnHost` stays in `app.py`** (changed on review): it is about
  30 lines that forward to `app.py` privates, and a separate module would
  import `app` back.
- **Split `agent-editor-controller.js`** (781 of the 800-line limit,
  `tests/test_area_module_size.py`): the self-configuration refresh block
  (`parseSnapshot_` through `onSelfConfigChanged`) moves to its own module
  reached through `ctx`. Its `<script>` tag goes in `index.html`, which is
  read once per process (a restart for manual checks).
- **Squawk 0232**: make the `_activeSection` term in `onSelfConfigChanged`
  falsifiable or remove it, per the squawk.
- **Squawk 0273**: announce header save errors in the agent editor
  (`errorRole`), keeping the load-failure line silent.
- **Squawk 0284**: the crew file's "Fix Review Issues" prompt (and
  "Implement", if it asks for falsification) in
  `.flightops/agent-crews/leg-execution.md` says a falsification removes
  the fix by editing and puts it back by editing, never by restoring a whole
  file. Crew files are project-owned scaffolding.
- **Lane headroom**: at the flight's quiet-host gate, `routing` and `agents`
  get headroom — a split if a coherent file group exists, else a re-budget
  from the measured time plus 25%.

#### DD10. The `default` agent (operator decision)

Unchanged: routines are refused for `default`. The operator's intent for it
is a future built-in assistant that is never configured by hand and has no
use for routines; there is no way in the UI to start a chat without an
agent. Recorded so Flight 4 does not reopen it.

#### DD11. "Still running" skips collapse *(FD)*

- Every skip row the scheduler and runner write gains a stable
  `reason_code`: `still_running` (the scheduler's "previous run was still
  going"), `chat_busy` (`runner.py`, the chat stayed busy) and
  `waiting_sign_in` (`runner.py`, the chat is waiting for a sign-in).
- When a run is skipped as `still_running` and the routine's newest run row
  is a `still_running` skip, the scheduler increments that row's `repeats`
  and moves its `finished_at`, in one repository transaction, instead of
  inserting a row. Its reason becomes "Skipped {n} times while the previous
  run was still going." (`repeats` 1 keeps today's sentence).
- The run-history UI shows the count; the runs route returns `repeats` and
  `reason_code`.

#### DD12. Time-zone changes

`scheduler._check_zone` (today: `list_active_wall_clock`, which selects
enabled, unfinished routines with a `next_run_at` and filters on the old
`kind` values, so it would match nothing after v48) is rewritten for the
DD1 shape:

- **It covers every routine that is not Done, on or off** (cycle 2), so an
  off routine re-enabled after a zone change behaves like an on one.
- **Instant-anchored (one-offs, minute and hour units):** the instant does
  not move (operator decision for one-offs). `anchor_at` and `next_run_at`
  are untouched; `start` is rewritten to `anchor_at`'s wall time in the new
  zone, purely for display.
- **Wall-clock (day, week, month, year):** they keep their wall time
  ("9:00 AM stays 9:00 AM"). `next_run_at` is recomputed in the new zone for
  an on routine, as today; if that leaves no next occurrence, the routine
  becomes Done.
- **Compare-and-set on the stored `schedule` and `anchor_at`** (not only
  `next_run_at`, which is null when a routine is off and unchanged for an
  instant-anchored one), so an operator edit made mid-pass still wins.
- **Pending proposals stay approvable.** In the same transaction, a pending
  proposal whose `base.schedule` equals the routine's schedule before the
  rewrite gets the rewritten schedule as its new base (v48's rule), so a
  zone change never makes it a stale 409.
- The repository query selects routines by the new shape, never by `kind`.

#### DD13. Verification

- **Unit tier, `frozen_clock`:** the calculator's table of cases for every
  unit, both month modes, month-end and leap-year skips, the inclusive and
  non-matching start, ends on a date and after N (including occurrences
  before the save and while off), the search bound and Done, the
  daylight-saving gap and repeat for each wall-clock unit, minute/hour units
  across a daylight-saving change, every DD12 zone-change case, re-enable on
  the grid; the normalizer for every legacy and relative shape (with the
  minute round-up); the two caps; retention; the skip collapse; the preview
  route.
- **Browser:** the form (presets from a start date, the Custom panel round
  trip, the preview line and warning, editing an existing routine, 422
  mapping) in the `agent-routines` lane; the new controls' contract tests in
  `contracts-controls` (or a split lane, if its budget needs it).
- **Behavior tests re-run** (no new spec): `agent-schedules-follow-up` and
  `routine-connector-delivery`, live, on a dev instance (port 8490 or
  higher, scratch data dir and cwd). Their assertions on the stored schedule
  shape ("schedule kind `once`") are re-authored to the DD1 shape before the
  run. `routine-connector-delivery`'s REST requests keep the legacy shapes
  (steps 3 and 6), which proves the aliases live; in
  `agent-schedules-follow-up` the model writes the schedule, and after leg 5
  it is taught only the canonical shape.
- **The gate:** `THE_ONE_TEST_NETNS=1 make test-unit`, then a quiet-host
  `--parallel 3` browser run on one commit, with `THE_ONE_REQUIRE_WEBKIT=1`.

### Citation Audit

Verified against the working tree at `ebb83d8c`; corrected after the cycle 1
review:

| Citation | Status |
|---|---|
| `the_one/routines/schedule.py::validate` — five kinds, `interval` in whole hours 1-168, `once.at` UTC | verified |
| `the_one/routines/schedule.py::next_run` — `interval` is `anchor + k*hours` with `k >= 1` (the anchor itself excluded); wall-clock kinds via `resolve_wall_time`; no `dateutil` import | verified |
| `the_one/routines/schedule.py::resolve_wall_time` — gap runs at end of gap, repeat on `fold=0` | verified |
| `the_one/routines/schedule.py::grace` — 24 h one-off, else min(half gap, 2 h) | verified |
| `the_one/routines/scheduler.py::_handle` — compare-and-set `advance_if_due` before spawn; missed counted with `occurrences_between` after the advance; "still going" skip inserts one row each time | verified |
| `the_one/routines/scheduler.py::_check_zone` — `list_active_wall_clock` filters on `kind IN ('daily','weekdays','weekly')`; `next_run` called with no anchor | verified (cycle 1) |
| `the_one/routines/runner.py` — two more skip reasons: chat busy (about `:179`), waiting for a sign-in (about `:391`) | verified (cycle 1) |
| `the_one/routines/limits.py` — `ROUTINES_PER_AGENT_MAX = 50`, `AGENT_ACTIVE_ROUTINES_MAX = 10`, `AGENT_RUNS_PER_DAY_MAX = 48`, `AGENT_PROPOSALS_KEPT = 500`, `AGENT_ROUTINE_WRITES_PER_TURN = 5`; `check_agent_caps` raise-only | verified |
| `the_one/routines/repository.py::AgentRoutineRepository.create` — `SELECT COUNT(*) … WHERE agent_name = ?` counts every row against 50 | verified |
| `the_one/routines/proposals.py::_prune` — keeps the newest 500 resolved rows; called from `insert_applied`, `resolve` and `insert_pending`; `base` is the raw stored fields for the stale check; `resolved_at` set on every resolution | verified (corrected cycle 1) |
| `the_one/routines/service.py::validate_schedule` — accepts `once` `on`/`in` input forms | verified |
| `the_one/routines/service.py::create_routine`/`update_routine` — `anchor = now` for `interval` on create and schedule change, and re-anchored to now on re-enable | verified (corrected cycle 1) |
| `the_one/routines/tools.py::_SCHEDULE_SHAPES`, `_LIMITS_SENTENCE` — the agent's schedule shapes and limits text | verified |
| `the_one/retention.py::run_purge_sweep` — per-agent cutoff from `list_retention_windows`; deletes chats and finished runs | verified |
| `the_one/db/schema.py` — `CURRENT_VERSION = 46` | verified |
| `the_one/interfaces/web/api.py` — routine routes from the "Routines" block (`_DEFAULT_AGENT`) through `GET …/routines/{id}/runs`; `router` is the module's `APIRouter` (prefix `/api`); `_poke_scheduler` in the block is also called by `put_time_settings` | verified (cycle 2) |
| `tests/test_routines_api.py`, `tests/test_routines_self_config_api.py` — bare `FastAPI()` with only `api.router`; patch `the_one.interfaces.web.api.get_connection`/`get_encryptor` | verified (cycle 1) |
| `tests/test_api_name_rule.py` — walks `api.router.routes` | verified (cycle 1) |
| `evals/harness.py::_collect_routines` and `evals/fingerprint.py` — the checks read `kind`; the fingerprint covers scenario TOML, fixtures and judge | verified (cycle 1) |
| `static/js/areas/studio/agent-editor-controller.js` — 781 lines; `onSelfConfigChanged` in the self-configuration refresh block | verified |
| `static/js/areas/studio/routines-form.js` — hour/minute/AM-PM `App.ui.select`s, day `checkboxGroup`, 60-day "At" select; `routines-describe.js`, `routines-form-model.js::bodyToFormState`, `self-config-routines-queue.js` read `kind` | verified (cycle 1) |

### Prerequisites

- [x] `main` at `ebb83d8c`; branch `flight/03-schedules-and-limits` created.
- [x] Ollama serves `gpt-oss:20b` and `qwen3:30b` (checked at planning);
      re-checked before leg 5's evals and leg 8's behavior runs.
- [ ] The plan token at `~/.config/the-one-evals/plan-token` works
      (an external session: verified before leg 5's evals; never printed).
- [x] Ports 8485-8499 free at planning; re-checked before each dev instance.
- [x] `THE_ONE_REQUIRE_WEBKIT=1` contract lanes ran green at Flight 2's gate.

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Citation Audit complete
- [x] Prerequisites verified, except the plan token, an external session
      verified at leg 5
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

1. **Move first.** The routine routes move out of `api.py` unchanged, with
   the existing tests as the characterization net; the agent editor's
   controller is split and the three squawks are closed. Nothing
   user-visible changes except the announced header error (0273).
2. **Caps, retention and the skip collapse** (independent of the schedule
   shape; cycle 2 split): v47's two run columns; the two caps replacing the
   old ones (tools' limits sentence included); retention for Done routines
   and resolved proposals; Purge now; the `reason_code` on every skip and
   the collapse.
3. **The recurrence core, alongside the old code.** New pure code (new
   module or new names) for the DD1 shape, the DD5 normalizer, the
   calculator and the sentences, proven by frozen-clock tables. The live
   `schedule.py` and `describe.py` keep serving the legacy data, so the unit
   tier stays green.
4. **The switch.** v48 rewrites the data; the scheduler, service, REST,
   preview route, views and zone changes (DD12) move to the new code; the
   legacy calculator and kinds are deleted; the minimal JS adapter keeps the
   old form and the `agent-routines` lane working.
5. **The agent's side.** Tool shapes and descriptions, the harness mapping,
   the eval runs and comparisons.
6. **The controls.** `datePicker`, `timeField` and the day toggles, with
   contract tests in both engines. Independent of legs 2-5, so it may run
   beside them on disjoint files.
7. **The form.** Presets, the Custom panel and the preview line on the new
   controls.
8. **Proof.** Both behavior specs re-run live; the quiet-host gate; lane
   budgets and headroom.

### Checkpoints

- [ ] Leg 1: routine routes in `routines_api.py`, all existing routine tests
      green unedited; the controller under the line limit; 0232, 0273 and
      0284 completed.
- [ ] Leg 2: one active cap and the 200 backstop; retention deletes Done
      routines and resolved proposals only; skips carry `reason_code` and
      collapse.
- [ ] Leg 3: the new calculator and normalizer pass their frozen-clock
      tables; the old code untouched.
- [ ] Leg 4: every legacy kind's next run unchanged across v48; the old form
      still works; the `agent-routines` lane green.
- [ ] Leg 5: the eval comparisons pass the gate; the token cost recorded.
- [ ] Leg 6: the three controls pass their contracts in both engines.
- [ ] Leg 7: the form builds every preset and the Custom panel round trip.
- [ ] Leg 8: both behavior specs pass live; the quiet-host gate is green.

### Adaptation Criteria

**Divert if**:
- The v48 schedule rewrite cannot preserve every legacy kind's next run
  exactly (stop and re-plan the mapping with the operator).
- The eval comparison shows a hard failure the tool text cannot fix
  without a broader prompt change (raise to the operator).
- The preview route's latency makes the form feel slow (re-plan with the
  operator before duplicating the calculator in JavaScript).

**Acceptable variations**:
- The day toggles as a `checkboxGroup` variant or a new factory.
- `routing`/`agents` headroom by split or by re-budget.
- The route module's name; the controller split's module name.
- Legs 6 and 7 merged if the controls are small.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [ ] `routine-routes-and-editor-maintenance` - Move the routine routes into
      `routines_api.py` (included into `api.router`, a pure move); split the
      agent editor's controller; squawks 0232, 0273, 0284 (DD9)
- [ ] `caps-retention-and-skips` - DD3, DD4, DD11, v47: the two caps,
      retention for Done routines and resolved proposals, Purge now, skip
      reason codes and the collapse
- [ ] `recurrence-core` - DD1, DD2, DD5: the shape, the normalizer, the
      calculator and the sentences as new code beside the old, with
      frozen-clock tables
- [ ] `recurrence-switch` - DD6 (v48), DD7 (server side and the JS
      adapter), DD12: the data rewrite, callers moved to the new code, the
      preview route, server sentences, zone changes, legacy code deleted,
      docs
- [ ] `agent-recurrence-tools-and-evals` - DD8: tool shapes and
      descriptions, the harness mapping, comparisons against both baselines
- [ ] `date-time-controls` - DD7: `App.ui.datePicker`, `App.ui.timeField`,
      the day toggles, with contract tests in both engines (may run beside
      legs 2-5)
- [ ] `recurrence-form` - DD7: the rebuilt Routines form with presets, the
      Custom panel and the preview line
- [ ] `behavior-reruns-and-gate` - DD13: re-author the specs' stored-shape
      assertions, re-run both specs live, the quiet-host gate, lane budgets
      and `routing`/`agents` headroom (DD9)

---

## Post-Flight

### Completion Checklist

- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing
- [ ] Documentation updated (CLAUDE.md, `the_one/agents.md` "Routines (M33)",
      `SECURITY-MODEL.md` "Routines", `docs/ui-control-inventory.md`,
      `docs/ui-testid-registry.md`)

### Verification

- The unit and browser tiers pass at the quiet-host gate.
- Both behavior specs pass live.
- On a dev instance, a routine created with each preset and with a Custom
  recurrence shows the right next run, last run and sentence; a Flight 1
  routine upgraded by v48 keeps its next run.
- Flight 4's HAT walks the form, the caps and retention with the operator.
