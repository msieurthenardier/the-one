# Leg: recurrence-switch

**Status**: ready
**Flight**: [Schedules and Limits](../flight.md)

## Objective

Switch routines to the calendar recurrence: migration v48 rewrites every
stored schedule and proposal to the DD1 shape (DD6); the service, REST
routes, scheduler, zone-change path (DD12), agent tools and proposals use
leg 3's `recurrence` and `recurrence_text` modules; a preview route and
server-rendered sentences replace the browser's schedule wording (DD7); the
legacy five-kind calculator and wording are deleted; and a minimal JS
adapter keeps the old Routines form, the approval queue and the
`agent-routines` lane working until leg 7 rebuilds the form.

## Context

- **Prior legs (uncommitted until Batch A/B commits):**
  - Leg 1 moved the routine routes into `the_one/interfaces/web/routines_api.py`
    (included into `api.router`; `api` helpers looked up at call time
    through `_ApiModule`); `_poke_scheduler` stays in `api.py`.
  - Leg 2: the two caps, retention, v47 (`repeats`, `reason_code`), skip
    reason codes and the collapse. `CURRENT_VERSION = 47`.
  - Leg 3: `the_one/routines/recurrence.py` (`normalize(raw, *, zone, now,
    min_ahead=None) -> (schedule, anchor)`, `check(schedule, anchor)`,
    `occurrences`, `next_occurrence`, `has_future`, `occurrences_between`,
    `last_occurrence`, `grace`, `render_start`, `rezone`, `is_anchored`,
    `ceil_minute`, `MSG_NO_RUNS_LEFT`, `MSG_ONCE_TOO_SOON`, `MSG_TOO_FAR`)
    and `recurrence_text.py` (`describe(schedule, anchor, zone)`,
    `warnings(schedule)`). It imports `resolve_wall_time` etc. from
    `schedule.py` as `legacy`. Read the leg 1-3 flight-log entries first.
- **The contract is the flight spec**: DD1 (two kinds of start; refusal of a
  save with no runs left), DD2 (re-enable continues the grid), DD5 (aliases;
  proposals fix their start when made), DD6 (v48), DD7 (preview, sentences,
  the JS adapter list), DD8 (the harness mapping — moved into this leg, see
  below), DD12 (zone changes). Read them in full.
- **Anchor storage.** `agent_routines.anchor_at` holds the exact instant for
  instant-anchored schedules (one-offs, minute and hour units) and is null
  for wall-clock units. Every calculation passes it to `recurrence`.
- **Service** (`the_one/routines/service.py`):
  - `validate_schedule` becomes a thin wrapper over `recurrence.normalize`
    (mapping `RoutineScheduleError` to `RoutineFieldError("schedule", …)`),
    returning `(schedule, anchor)`; its legacy `on`/`in` parsing goes.
  - `create_routine` / `update_routine` store the schedule and `anchor_at`
    from it, compute `next_run_at` with `recurrence.next_occurrence(…,
    after=now)`, and refuse a save with no future occurrence
    (`MSG_NO_RUNS_LEFT`, 422 on `loc ["schedule"]`). A schedule save reopens
    a Done routine (today's rule).
  - **Re-enable continues the grid** (DD2): drop the `anchor = now`
    re-anchor on re-enable; the next run is the next occurrence after now.
    Enabling a routine with no future occurrence is refused with the same
    sentence (on `loc ["enabled"]`).
  - **Proposals:** an agent change's payload stores the normalized schedule
    and, for an instant-anchored schedule, `anchor_at`, fixed at proposal
    time (DD5). Approval applies that schedule and anchor **verbatim**
    (no re-normalization against approval time) and refuses with
    `MSG_NO_RUNS_LEFT` when no occurrence is left (422 at the approve route;
    the proposal stays pending).
  - **Stale check:** `_BASE_KEYS` gains `anchor_at`, and
    `_PAYLOAD_TO_BASE["schedule"]` touches `("schedule", "anchor_at",
    "finished_at")`. v48 writes `anchor_at` into every proposal base it
    rewrites.
  - `routine_view` gains `schedule_text`; the proposals list items gain
    `payload_schedule_text`, `base_schedule_text` and
    `current_schedule_text` where a schedule is present (null otherwise);
    the approve route's stale 409 body gains `current_schedule_text`,
    `base_schedule_text` and `proposed_schedule_text` beside the existing
    values (null where the schedule is not among the touched keys).
  - `limits_view` keeps its keys (the old form reads `interval_hours_max`;
    hours 1-168 is still the hour range).
- **Preview route** (`routines_api.py`): `POST /api/agents/{name}/routines/preview`
  with `{schedule}` (any DD5 input; agent-only `min_ahead` never applies:
  this is the operator's form) returns `{schedule, anchor_at, text,
  next_runs (up to three ISO instants), last_occurrence (ISO or null),
  warnings}`; a refusal is the create route's 422 shape on `loc
  ["schedule"]`, including `MSG_NO_RUNS_LEFT`. It writes nothing; 404 for
  an unknown agent and for `default`, like the other routine routes. It
  joins `EXEMPT` in `tests/test_api_name_rule.py` ("previews a schedule;
  writes nothing").
- **Scheduler** (`scheduler.py`):
  - `_handle`: grace, next run and the missed count from `recurrence` with
    the routine's anchor; a routine is finished (`finished_at = now`,
    `next_run_at` null) whenever there is no next occurrence — a one-off
    after its run, or the last occurrence of an ended series. The missed
    count (`occurrences_between`) runs before the advance only if the code
    needs it for the next run; keep today's compare-and-set-then-spawn order.
  - `_check_zone` per DD12: every routine that is not Done, on or off;
    instant-anchored → rewrite `start` from `anchor_at` in the new zone
    (`recurrence.rezone`), `next_run_at` untouched; wall-clock → recompute
    `next_run_at` for an on routine (Done when none). Compare-and-set on
    `schedule` and `anchor_at` (and `next_run_at` where it changes). In
    the same transaction, rebase pending proposals whose `base.schedule`
    equals the routine's pre-rewrite schedule. `list_active_wall_clock` and
    `recompute_next_run` are replaced by repository methods that select by
    the new shape (never `kind`).
- **Agent tools** (`tools.py`): `coerce_schedule` output goes through the
  service (so aliases and the canonical shape both work); every
  `describe_schedule` call becomes `recurrence_text.describe(schedule,
  anchor, zone)`, with the anchor from the routine or the payload. The tool
  **descriptions** (`_SCHEDULE_SHAPES`, the schema text) are leg 5's; this
  leg leaves them unchanged.
- **Evals harness** (moved from leg 5 so the unit tier stays green):
  `evals/harness.py::_collect_routines` maps the stored shape back to the
  `kind` the checks read: `repeat` null → `once`; every 1 day → `daily`;
  every 1 week on exactly 0-4 → `weekdays`; every 1 week → `weekly`;
  every N hours → `interval`; anything else → the unit name.
  `tests/test_evals_routines.py` passes unchanged in its checks.
  `tests/test_evals_freeze.py` pins digests of `evals/harness.py`; update
  the digest in this leg (Flight 2 leg 4 did the same).
- **v48** (`schema.py`) per DD6: a frozen converter inside the v48 block
  (its own legacy parsing; the fallback zone through a lazy
  `the_one.time_zones.load_effective_zone`); daily/weekdays/weekly take
  `start.date` from `next_run_at`'s local date (or `created_at`'s when off
  or Done) and `start.time` from the legacy `time`; interval `anchor_at =
  next_run_at` exactly when set, else `anchor_at + hours`; once `anchor_at =
  at` exactly; `start` rendered from the anchor; `next_run_at` untouched.
  Proposals: `base` takes the routine's migrated schedule and `anchor_at`
  verbatim when `base.schedule` equals the routine's pre-migration schedule,
  else is converted alone; `payload` is converted like an off routine using
  the proposal's `created_at`, with `anchor_at` for an instant-anchored
  result. Unreadable schedules: left, routine turned off, one guarded run
  row (`trigger_kind` `schedule`, `outcome` `failed`, `reason_code`
  `upgrade_failed`, `started_at`/`finished_at` = migration time, DD6's
  sentence). `CURRENT_VERSION = 48`.
- **Deleting the legacy code:** `schedule.py` keeps only what `recurrence`
  needs (`resolve_wall_time`, `parse_utc`, `_parse_hhmm`) — or those move
  into `recurrence.py` and `schedule.py` is deleted; the Developer chooses
  and records it. `KINDS`, `validate`, `next_run`, `grace`,
  `occurrences_between` and `describe.describe_schedule` go;
  `describe_next` and `describe_target` stay. `MSG_ONCE_TOO_SOON` /
  `MSG_TOO_FAR` exist once. `tests/test_routines_schedule.py` keeps the
  `resolve_wall_time` cases (moved if the function moves) and drops the
  rest, which `tests/test_routines_recurrence.py` replaces.
- **The minimal JS adapter** (DD7, cycle 2), under
  `static/js/areas/studio/`:
  - `routines-tab.js`: the list row's schedule sentence is
    `routine.schedule_text`;
  - `self-config-routines-queue.js`: payload/base/current sentences from the
    proposal's `*_schedule_text`, and the stale 409 view from the body's
    `*_schedule_text`;
  - `routines-describe.js`: the schedule sentence function is retired;
    target and time formatting stay;
  - `routines-form-model.js::bodyToFormState`: canonical → the old form's
    five kinds where expressible (`repeat` null → once with `start` as the
    at-day and time, no zone conversion; every 1 day → daily; every 1 week
    on exactly 0-4 → weekdays; every 1 week → weekly; every N hours →
    interval); any other shape opens with the schedule fields read-only and
    the note "Edit this schedule after the form update."; legacy-shaped
    input still accepted. `formToBody` already sends only changed fields,
    so an untouched schedule is never re-sent;
  - the old form keeps sending legacy shapes, which the service accepts;
  - the drawer needs nothing (`agent-drawer-parts.js::routineMeta` reads
    only `finished_at`, `enabled`, `next_run_at`).
- **Browser tests to edit** (wording and shape pins): `tests/browser/test_flow_agent_routines.py`
  (about `:170-188`, `:216`), `test_flow_agent_routines_form.py` (about
  `:99`, `:154`, `:168`, `:335`, `:460`), `test_flow_agent_routines_self_config.py`
  (about `:230`, `:308`, `:528`, `:539`), and `tests/browser/seeders.py`
  (`seed_routine`'s stored default `{"kind": "daily", …}` becomes canonical).
  Grep the lanes for `describeSchedule`, `"kind": "daily"` and the old
  sentences ("Daily at", "every day at").
- **Unit tests** with legacy shapes in requests keep working through the
  aliases; assertions on stored or returned schedules, on sentences and on
  inserted rows move to the canonical shape (about 150 sites across
  `test_routines_api.py`, `_service.py`, `_proposals.py`, `_scheduler.py`,
  `_runner.py`, `_self_config_api.py`, `test_routine_tools.py`,
  `_taint.py`, `_repository.py`).

## Inputs

- Flight spec DD1, DD2, DD5, DD6, DD7, DD8 (harness), DD12; legs 1-3 and
  their flight-log entries.
- The files named in Context; `tests/test_db_migration.py`;
  `tests/test_api_name_rule.py`; the behavior specs only to read (leg 8
  re-authors them).

## Outputs

- v48, the switched backend, the preview route, the view sentences, the
  deleted legacy code, the harness mapping, the JS adapter, updated tests.
- Docs: `the_one/agents.md` "Routines (M33)" rewritten for the calendar
  recurrence (shape, two kinds of start, occurrence rules, refusals, the
  preview route, v48, zone changes, re-enable); `SECURITY-MODEL.md`
  "Routines" if it names schedule kinds; CLAUDE.md's Routines paragraph
  ("a once, daily, weekdays, weekly or interval schedule") updated to the
  recurrence and the preview route.
- Flight log entry.

## Acceptance Criteria

- [ ] AC1. v48: every legacy kind, on and off, converts as DD6 says and its
      `next_run_at` is unchanged; a 02:30 LA daily whose `next_run_at` falls
      on the spring-forward day keeps `start.time` "02:30"; an interval
      keeps its exact anchor (microseconds); a one-off keeps its instant;
      pending and resolved proposals are rewritten (bases verbatim when
      they matched, with `anchor_at`); an unreadable schedule turns the
      routine off with one guarded run row; rewind is idempotent; with and
      without `routines_zone`. `TestSchemaV48`; version pins and column
      lists move.
- [ ] AC2. After v48, every scheduler, service and tool path reads the new
      shape: a routine of each unit runs at its next occurrence; an "after
      N" series finishes (Done) after its Nth occurrence; an "ends on"
      series finishes after its last; missed and catch-up behaviour and the
      missed count match the legacy rules.
- [ ] AC3. REST create, update and the agent tools accept the canonical
      shape, the relative start and every legacy shape; stored and returned
      schedules are canonical; `anchor_at` follows DD1.
- [ ] AC4. A create, schedule update, enable or approval that leaves no
      future occurrence is refused with "This schedule has no runs left."
      (422; the proposal stays pending at approval).
- [ ] AC5. Re-enabling a minute or hour routine continues its grid from
      `anchor_at`.
- [ ] AC6. The preview route returns the normalized schedule, anchor, text,
      up to three next runs, the last occurrence and warnings; refuses like
      create; writes nothing; is `EXEMPT` in the name-rule test.
- [ ] AC7. Zone change (DD12): an off and an on one-off keep their instants
      with `start` re-rendered; a minute/hour routine keeps its anchor; a
      daily keeps 9:00 AM local with `next_run_at` recomputed; an operator
      edit made between read and write wins (compare-and-set); a pending
      proposal whose base matched is rebased and approves without a stale
      409.
- [ ] AC8. Approval applies a proposal's stored schedule and anchor
      verbatim; the stale check includes `anchor_at`; the stale 409 body,
      the proposals list and the routine view carry the schedule sentences.
- [ ] AC9. The legacy calculator and `describe_schedule` are gone (no
      references under `the_one/` or `tests/`); `MSG_ONCE_TOO_SOON` and
      `MSG_TOO_FAR` are defined once.
- [ ] AC10. `evals/harness.py::_collect_routines` maps the new shape back
      to `kind`; `tests/test_evals_routines.py` passes.
- [ ] AC11. The JS adapter: the Routines tab lists `schedule_text`; the
      queue and its stale view show the server sentences; editing a
      daily/weekdays/weekly/interval/once routine in the old form still
      works and saves; a routine whose shape the old form cannot express
      opens with read-only schedule fields and the note; the
      `agent-routines` lane passes.
- [ ] AC12. `THE_ONE_TEST_NETNS=1 make test-unit` passes (15 skipped);
      ruff clean; the static guards pass; the `agent-routines`, `agents`
      and `chats` lanes pass (the drawer and the transcript read routines).

## Verification Steps

- AC1-AC10: unit tests (named in the flight log), `grep -rn` for AC9.
- AC11-AC12: the lanes through `scripts/run-tests.sh --lane …` with
  `THE_ONE_TEST_NETNS=1`, one at a time, never beside the unit suite.

## Implementation Guidance

1. v48 with its tests first (the frozen converter is self-contained).
2. Service and repository: normalize, store, next run, refusals, re-enable,
   proposals (payload anchor, verbatim approval, base keys), views and
   sentences; then the preview route.
3. Scheduler `_handle`, then `_check_zone` with its repository methods and
   the proposal rebase.
4. Tools' describe calls; the harness mapping.
5. Delete the legacy code; fix every test pin (grep for `"kind"`,
   `describe_schedule`, `next_run(`, the old sentences).
6. The JS adapter and the browser test edits; run the lanes.
7. Docs, flight log.

## Edge Cases

- A legacy `once` whose `at` passed while the app was closed: v48 keeps
  its anchor and `next_run_at`; the scheduler's catch-up handles it.
- A routine with `next_run_at` set but `enabled` 0 (should not exist):
  treat as off.
- A pending proposal whose routine was deleted (`routine_id` null): v48
  converts its payload alone; approval refuses `gone` as today.
- A wall-clock routine whose rule produces nothing in the new zone after a
  zone change (impossible today, possible with "ends on"): Done.
- Two zone changes before a pass: each rewrite is computed from the stored
  anchor or `start`, never from the previous rendering of an anchor.

## Files Affected

- `the_one/db/schema.py`; `the_one/routines/{service,repository,scheduler,tools,proposals,schedule,describe,recurrence}.py`;
  `the_one/interfaces/web/routines_api.py`; `evals/harness.py`
- `static/js/areas/studio/{routines-tab,routines-describe,routines-form-model,self-config-routines-queue}.js`
- tests listed in Context; `tests/test_api_name_rule.py`; `tests/test_db_migration.py`
- `the_one/agents.md`, `SECURITY-MODEL.md`, CLAUDE.md, the flight log

## Citation Audit

Checked at `49a5051a` plus legs 1-3 in the working tree:
- `service.py`: `validate_schedule` (`once` `on`/`in`), `create_routine`
  `anchor = now if kind == "interval"`, `update_routine`'s re-anchor on
  re-enable, `_BASE_KEYS` (no `anchor_at`), `_PAYLOAD_TO_BASE`,
  `_stale_precheck`, `approve_proposal` — verified.
- `scheduler.py::_handle` (`once = kind == "once"`, `next_run`, `grace`,
  `occurrences_between`) and `_check_zone` → `repository.list_active_wall_clock`
  (`json_extract(schedule, '$.kind') IN (…)`), `recompute_next_run` —
  verified.
- `tools.py`: `describe_schedule` at `list_my_routines` and in two result
  builders; `coerce_schedule` — verified.
- `routines_api.py` approve route: `ProposalStaleError` → 409
  `{error, current_value, proposed_value, base_value}` — verified (leg 1's
  module).
- `evals/harness.py::_collect_routines` reads `r.schedule.get("kind")` —
  verified.
- `tests/browser/seeders.py` `seed_routine` default schedule
  `{"kind": "daily", "time": "09:00"}` — verified.
- `recurrence.py` / `recurrence_text.py` public functions — verified (leg 3).

## Design review cycle 1 (Sonnet Developer): approve with changes, applied

These rules override anything above that contradicts them.

### Two passes: 4a (backend and unit tier), then 4b (JS adapter, browser, docs)

The leg is too large for one Developer pass and cannot be green halfway, so
it runs as two Developer passes in one working tree, landed together:
- **4a:** v48 and `TestSchemaV48`; service, repository and routes (preview,
  `*_schedule_text`); scheduler `_handle` and `_check_zone`; tools; the
  harness mapping and the `tests/test_evals_freeze.py` digest; deleting the
  legacy code; converting the unit tests. Exit gate: `THE_ONE_TEST_NETNS=1
  make test-unit` green (15 skipped), ruff clean. It lists, in the flight
  log, the browser test files that will stay red until 4b (the
  `agent-routines` files and `test_flow_chat_routine_marker.py`).
- **4b:** the JS adapter, the browser test edits (including
  `tests/browser/test_flow_chat_routine_marker.py`, `seeders.seed_routine`
  and every `seed_routine_proposal` caller, which must pass canonical
  `payload`/`base` with `anchor_at`), and the docs. Exit gate: the
  `agent-routines`, `agents` and `chats` lanes, one at a time.
- Within 4a, v48 first (its converter is self-contained), then the service
  and scheduler together.

### Verbatim schedules for proposals and immediate agent writes (high)

- `create_routine` / `update_routine` gain a keyword (suggested
  `schedule_pair=(schedule, anchor)`) that skips normalization: it runs
  `recurrence.check(schedule, anchor)`, does **not** apply `min_ahead` or
  the one-year start limit, and still applies the no-runs-left refusal.
- `agent_change` normalizes **once** (with `min_ahead`), stores the result
  in the payload as `schedule` plus `anchor_at` (ISO or null), and passes
  the pair to `create_routine`/`update_routine` on the immediate path, so
  the proposal row and the stored routine are identical.
  `approve_proposal` passes the payload's pair the same way.
- **At approval, `start` is re-rendered** with
  `recurrence.rezone(schedule, anchor, current_zone)` (the anchor stays
  verbatim), so a zone change while a proposal is pending leaves no stale
  `start`. The payload itself is not rebased by DD12. AC8 gains this test.
- `_hypothetical` and `_touched_base_keys` tolerate the `anchor_at` payload
  key.
- A unit test pins that `normalize` followed by a verbatim `check`
  round-trips for each legacy alias.

### Refusals and their order

- **Approval with no runs left is 422** (the flight's DD1 is amended); the
  approve route already maps `RoutineFieldError` to 422 and the queue shows
  a 422 sentence in the item. The has-future check runs **before** the
  repository transaction, so it wins over a stale 409 when both apply.
- **No runs left applies whatever `enabled` is** (FD): a create or schedule
  edit to a schedule with no future occurrence is refused even when the
  routine is or stays off.
- **Re-enabling a routine with no future occurrence** (for example a
  one-off whose time passed while it was off) is refused with the same
  sentence on `loc ["enabled"]`. Today it is marked Done silently
  (`service.update_routine`); the pin in `tests/test_routines_service.py`
  is inverted and renamed.

### Views, sentences and unreadable schedules

- `routine_view` gains a `zone` parameter; its four callers in
  `routines_api.py` (list, get, create, update) await
  `time_zones.load_effective_zone`.
- `list_routine_proposals` adds `payload_schedule_text`,
  `base_schedule_text` and `current_schedule_text`; `current` comes from one
  `list_for_agent` per request (never a query per row); a proposal whose
  routine is gone gets null.
- The stale-409 body builds its three texts from `e.current`, `e.proposed`
  and `e.base` (which carry `anchor_at` once `_PAYLOAD_TO_BASE["schedule"]`
  includes it). One `routines_api.py` helper builds sentence, next runs and
  last occurrence for the preview and the 409 body.
- **Unreadable schedules never 500.** `recurrence_text.describe` raises on a
  legacy-shaped schedule left by v48's `upgrade_failed` path; the routine
  view, the proposals list and the tools (`list_my_routines`, results)
  catch it and use null / "an unreadable schedule". Tests cover each,
  including `list_my_routines` on an `upgrade_failed` routine.

### The JS adapter's mapping (medium)

`bodyToFormState` maps to the old five kinds only when `ends.kind` is
`never` **and** `start.date` is not in the future (the old form has no end
and no start date, and its save would drop both); everything else opens
read-only with the note. The evals harness mapping ignores `ends`
(documented in the function).

### v48 details

- `routines_zone` is a zone **key**: build it with `zoneinfo.ZoneInfo(key)`;
  a missing or invalid key falls back to the effective zone (the scheduler
  never writes the key for an unnamed system zone).
- Every non-null proposal `base` gains `anchor_at` (the migrated routine's
  when the base matched, else its own converted anchor or null), including
  delete proposals' bases.
- **Unreadable** is decided on the raw column text (bad JSON, or JSON that
  is not a recognizable legacy shape); the repository's `{}` for bad JSON
  must not be relied on.
- The `upgrade_failed` run row's guard: skip it when a run with
  `reason_code = 'upgrade_failed'` already exists for that routine.

### DD12 repository work

- New repository methods: list every not-Done routine (on or off) across
  agents; a compare-and-set on the **raw stored text** of `schedule` (and
  `anchor_at`) that writes `schedule`, `anchor_at` and, where it changes,
  `next_run_at`, and rebases matching pending proposals' `base` through raw
  SQL, all in one `write_transaction`.
- A test that `_check_zone` leaves Done routines alone.

### Legacy cleanup specifics

- `MSG_ONCE_TOO_SOON` exists in `service.py` and `recurrence.py`;
  `MSG_TOO_FAR` in `limits.py` and `recurrence.py`. Keep one of each (in
  `recurrence.py`); `MSG_PAST` and `ONCE_MAX_AHEAD_DAYS` go if dead.
- `describe.py` (`describe_next`) and `recurrence.py` still use
  `schedule.parse_utc`, `_parse_hhmm` and `resolve_wall_time`: keep
  `schedule.py` as a three-function module, or move them into
  `recurrence.py` and update the importers.
- **Argument order changed** from the legacy functions:
  `recurrence.grace(schedule, anchor, due, zone)` and
  `occurrences_between(schedule, anchor, start, end, zone, cap)`; every
  scheduler call site changes.

### Test-conversion inventory (from the review)

- Direct inserts of legacy schedules to convert: `tests/test_routines_scheduler.py`
  (`_mk` and about eight literals; the `'not json'` hot-loop test stays),
  `test_routines_repository.py`, `test_routines_proposals.py` (`DAILY`, raw
  proposal inserts), `test_retention.py`, `test_routines_runner.py`,
  `test_routine_tools_taint.py`, `tests/_routine_app.py`,
  `tests/_routine_tools_env.py`, `test_api_name_rule.py`, and the v45 raw
  insert in `test_db_migration.py`.
- REST requests keep working through the aliases; their stored/returned
  shape and sentence assertions move: `test_routines_api.py`,
  `test_routines_service.py`, `test_routines_self_config_api.py`,
  `test_routine_tools.py`.
- `test_routines_schedule.py` keeps only the `resolve_wall_time` cases.
- Evals: `tests/test_evals_routines.py`, the `test_evals_freeze.py` digest.
- Browser (4b): `test_flow_agent_routines.py`, `_form.py`,
  `_self_config.py`, `test_flow_chat_routine_marker.py`, `seeders.py`.
- Behavior: `tests/behavior/agent-schedules-follow-up.md` asserts "schedule
  kind `once`" / `daily`; leg 8 re-authors it.
