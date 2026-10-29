# Leg: routines-store-and-schedule

**Status**: completed
**Flight**: [Operator Routines, End to End](../flight.md)

## Objective

Persist named per-agent routines and their run history (schema v45). Compute
their next run in the operator's time zone with a pure, DST-correct calculator.
Expose operator CRUD over REST, and put run history under the agent's
retention policy. Nothing runs yet.

## Context

- Flight DD1 (store, retention), DD2 (schedule kinds and calculator), DD3
  (DST), DD4 (grace window and one-off finishing), DD9 (REST surface, minus
  Run now).
- This is the first leg. The later legs build on it:
  - `connector-delivery-split` (leg 2) is independent of it.
  - `routine-run-path` (leg 3) adds the runner, Run now, and the row's live
    `running` flag.
  - `routine-scheduler` (leg 4) adds the loop, `scheduler.poke()`, the
    `routines_zone` comparison, and the catch-up pass that uses this leg's
    `grace` and `occurrences_between` helpers.
- Nothing calls `scheduler.poke()` yet. Leg 4 adds the poke calls to every
  routine write route.

## Inputs

- Schema at v44 (`the_one/db/schema.py:14`).
- The `agent_rules`/`agent_notes` patterns:
  - DDL with `REFERENCES agents(name) ON DELETE CASCADE ON UPDATE CASCADE`;
  - `AgentRuleRepository` (`the_one/db/repositories.py`, class
    `AgentRuleRepository`), with one `write_transaction` per mutator and
    `KeyError` for a missing row;
  - the hand-parsed bodies in `api.py` (`_rules_body`, `_load_agent_or_404`).
- `the_one/time_zones.py`: `utcnow()` (the clock seam) and
  `load_effective_zone(conn) -> EffectiveZone(key, tzinfo)`.
- `the_one/retention.py` `run_purge_sweep` and
  `SQLiteAgentStore.list_retention_windows()`.
- `DELETE /api/agents/{name}/chat/sessions` (`api.py`,
  `delete_agent_chat_sessions`): the editor's Purge now.

## Outputs

- New package `the_one/routines/`:
  - `__init__.py`;
  - `schedule.py` (pure calculator);
  - `limits.py` (constants and error types);
  - `repository.py` (`AgentRoutineRepository`, `RoutineRunRepository`);
  - `models.py` (pydantic `Routine`, `RoutineRun`).
- `the_one/db/schema.py`: the v45 migration, and `CURRENT_VERSION = 45`.
- `the_one/interfaces/web/api.py`: routine routes, and Purge now also clears
  run history.
- `the_one/retention.py`: the sweep deletes old finished runs and returns
  `runs_deleted`.
- Tests:
  - `tests/test_routines_schedule.py`, `tests/test_routines_api.py`,
    `tests/test_routines_repository.py`;
  - `tests/test_db_migration.py`: `TestSchemaV45` and the version pins;
  - `tests/test_api_name_rule.py`: classification;
  - `tests/test_retention.py` (or `test_chat_history_purge.py`): run
    retention;
  - `tests/test_name_repair.py`: `agent_routines` added to the follow-the-rename
    table loop.
- `the_one/agents.md`: a new "Routines (M33)" section covering the store,
  schedule and REST parts.

## Acceptance Criteria

**Schema**

- [ ] AC1. `CURRENT_VERSION == 45`. A fresh database and a v44 database both
      migrate to 45 and create `agent_routines` and `agent_routine_runs` with
      exactly the flight DD1 columns, in DD1 order:
      - `agent_routines`: `id`, `agent_name`, `name`, `prompt`, `schedule`,
        `enabled`, `finished_at`, `target_kind`, `target_session_id`,
        `target_platform`, `target_connector_id`, `target_channel_id`,
        `target_thread_id`, `target_peer_id`, `next_run_at`, `anchor_at`,
        `created_by`, `created_at`, `updated_at`;
      - `agent_routine_runs`: `id`, `routine_id`, `trigger_kind`, `outcome`,
        `reason`, `due_at`, `started_at`, `finished_at`, `session_id`,
        `new_chat`.
- [ ] AC2. `agent_routines.agent_name`'s FK has `on_update`/`on_delete` =
      CASCADE. `agent_routine_runs.routine_id`'s has `on_delete` = CASCADE.
      `UNIQUE (agent_name, name COLLATE NOCASE)` is enforced: inserting "Daily"
      and "daily" for one agent fails, and the same name on two agents
      succeeds. The CHECKs on `target_kind`, `created_by`, `trigger_kind` and
      `outcome` reject other values.
- [ ] AC3. Re-running `ensure_schema` after rewinding `schema_version` below 45
      is idempotent.
- [ ] AC4. `SQLiteAgentStore.rename` carries an agent's routines, and their run
      rows stay attached. `SQLiteAgentStore.delete` removes both. An agent PUT
      (the `ON CONFLICT(name) DO UPDATE` upsert) leaves routines untouched.

**Calculator**

- [ ] AC5. `schedule.validate` accepts exactly the five DD2 kinds and refuses
      anything else with a `RoutineScheduleError` carrying a one-sentence
      `.detail`. That covers: an unknown kind, a bad `HH:MM`, an empty or
      out-of-range `days`, `hours` outside 1–168, extra keys, and a non-UTC or
      unparsable `at`.
- [ ] AC6. `schedule.next_run(schedule, after=, zone=, anchor=)` returns the
      first occurrence strictly after `after`, as an aware UTC datetime.
      Covered cases:
      - daily;
      - weekdays (a Friday evening goes to Monday);
      - weekly with several days;
      - interval anchored, with and without a DST change in between (elapsed
        time is unchanged);
      - once in the future (`at`) and once in the past (`None`).
- [ ] AC7. DST, pinned in America/Los_Angeles and Europe/London:
      - a nonexistent wall time runs once at the gap's end (LA 2026-03-08
        02:30 → 03:00 PDT, **not** zoneinfo's 03:30);
      - a repeated wall time runs once, on its first occurrence (LA 2026-11-01
        01:30 → 01:30 PDT, `fold=0`). The next day's run is the next
        occurrence, never a second 01:30 PST.

      Asia/Kolkata (+05:30, no DST) gives the exact wall time.
      Australia/Lord_Howe (a 30-minute gap) resolves a gap time to the gap's
      end on a whole minute. Every expected value in step 2's table is
      asserted.
- [ ] AC8. `schedule.grace(schedule, due, zone, anchor)`:
      - a one-off returns 24 h;
      - a repeating kind returns min(half the gap from `due` to the next
        occurrence after it, 2 h). Daily gives 2 h, interval 2 gives 1 h,
        interval 1 gives 30 min.

      `schedule.occurrences_between(schedule, start, end, zone, anchor, cap=1001)`
      counts occurrences in `(start, end]`, stopping at `cap`.
- [ ] AC9. The calculator never calls `datetime.now`. The scheduler and API code
      use `time_zones.utcnow()`. A grep guard test asserts that
      `the_one/routines/schedule.py` contains no `datetime.now(`.

**REST**

- [ ] AC10. `POST /api/agents/{name}/routines` creates a routine and returns
      201 with the row shape below.
      - **The `default` agent.** A literal `name == "default"` check runs
        **before** the 404 load: POST gives 422 "Routines need a named
        agent." even when a stored `default` row exists. GET, PUT, DELETE and
        `/runs` for `default` are 404 ("Agent not found: default"), since no
        routine can exist. The codebase compares the name literally
        (`factory.py:616`) and has no shared constant.
      - **An unknown agent** gives 404.

      The body is
      `{name, prompt, schedule, target, enabled?}`:
      - `target` is one of:
        - `{"kind": "chat", "session_id": "…"}`;
        - `{"kind": "new"}`;
        - `{"kind": "own"}`.
      - `schedule` is a DD2 kind. `once` may instead be given as
        `{"kind": "once", "in": {"amount": N, "unit": "minutes|hours|days"}}`,
        which the server converts to an absolute `at`.
- [ ] AC11. Row shape: `{id, agent_name, name, prompt, schedule, enabled,
      finished_at, next_run_at, created_by, created_at, updated_at, target,
      last_run, running}`.
      - `target` = `{kind, session_id, title, platform, missing}`. For `chat`,
        `title`/`platform` come from the live `chat_sessions` row, and
        `missing` is true when that row is gone. For `own`, `session_id` is
        null until the first run.
      - `last_run` = `{outcome, reason, trigger_kind, finished_at, session_id}`
        of the newest run, or `null`.
      - `running` is `false` in this leg (leg 3 wires it).
- [ ] AC12. `GET …/routines` returns `{routines: [...], limits: {...}}` with the
      routines in name order (case-insensitive). `limits` is exactly
      `{"prompt_chars": 4000, "routines_per_agent": 50, "interval_hours_min": 1,
      "interval_hours_max": 168, "once_max_days": 365}`, and a test asserts the
      exact dict. `GET …/routines/{id}` returns
      one row. `DELETE …/routines/{id}` returns `{"status": "ok"}`. Another
      agent's routine id is a 404 on every route.
- [ ] AC13. `PUT …/routines/{id}` is a partial update of `name`, `prompt`,
      `schedule`, `target` and `enabled`:
      - **A schedule change** recomputes `next_run_at` from now, and for
        `interval` resets `anchor_at`.
      - **A once whose `at` moves** to a future time clears `finished_at` and
        re-arms it.
      - **`enabled: false`** nulls `next_run_at`.
      - **`enabled: true`** (from false) recomputes `next_run_at` from now,
        with no catch-up, and for `interval` resets `anchor_at`.
      - **`enabled: true` on a finished one-off** without a new future `at`
        is a 422: "Set a new time to run it again."
      - **A target change** re-snapshots the connector identity.
      - **Precedence** (design review):
        1. Any `schedule` key in the body counts as a schedule change, even
           one identical to the stored schedule. It is validated (a `once` in
           the past is refused only here), stored, and resets `anchor_at` for
           `interval`.
        2. A body without `schedule` never re-validates the stored one. An
           unfinished once whose time has passed and that is awaiting
           catch-up stays as it is.
        3. A schedule change on a finished one-off to a future `once` or to
           any repeating kind clears `finished_at`.
        4. After the fields are applied, `next_run_at` is computed: null if
           the resulting `enabled` is false or the routine is finished,
           otherwise `next_run(after=now)` when the schedule changed or
           `enabled` went false → true. Otherwise it is unchanged.
           `enabled: true` on an already enabled routine is a no-op.
        5. A target left out of the body is not re-validated, so a `missing`
           chat target can stay until it is re-pointed.
      - **Errors.** `in` and `at` share one message per bound: "That time has
        already passed." and "That time is more than a year away."
- [ ] AC14. Validation:
      - **Name** goes through `check_name`: a 422 list on `loc ["name"]`.
      - **Duplicate name** (case-insensitive, same agent): a 409 with a
        list-shaped detail on `loc ["name"]`, like the agent 409.
      - **Prompt** is trimmed, and must be 1–4000 characters (422).
      - **Routine count:** more than 50 per agent is a 422.
      - **A `once`** that is in the past ("That time has already passed.") or
        more than 365 days ahead ("That time is more than a year away.") is a
        422.
      - **A `chat` target** whose session does not exist, or belongs to
        another agent, is a 422 ("That chat belongs to another agent." / "That
        chat doesn't exist.").
      - **Bodies** are parsed by hand; no 422 echoes submitted input.
- [ ] AC15. A `chat` target on a connector session snapshots `target_platform`,
      `target_connector_id`, `target_channel_id`, `target_thread_id` and
      `target_peer_id` from that row. A web chat leaves them null.
- [ ] AC16. `next_run_at` is computed with `load_effective_zone(conn).tzinfo`
      and `time_zones.utcnow()`, so it moves under `frozen_clock`. It is stored
      as UTC ISO.
- [ ] AC17. `GET …/routines/{id}/runs?limit=&before=` returns runs newest first
      (`started_at DESC`, ties by id). `limit` defaults to 50, max 200
      (otherwise 422), and `before` is a `started_at` cursor. Leg 1 seeds runs
      only through the repository in tests.
- [ ] AC18. `tests/test_api_name_rule.py`: `POST …/routines` and
      `PUT …/routines/{routine_id}` are in `CHECKED`, with tests in the file's
      style proving a rule-breaking name is refused. The suite's
      every-route classification passes.

**Retention**

- [ ] AC19. `run_purge_sweep` deletes, per agent, every run row whose routine
      belongs to that agent, whose `outcome != 'running'`, and whose
      `finished_at` is older than the agent's `chat_history_retention_days`.
      It returns `runs_deleted`. Newer runs and other agents' runs remain.
      `POST /api/_test/purge-sweep` (existing seam) surfaces `runs_deleted`.
- [ ] AC20. `DELETE /api/agents/{name}/chat/sessions` (Purge now) also deletes
      that agent's **finished** run rows (`outcome != 'running'`, like the
      sweep), and returns `runs_deleted`. The routines remain.
      `RoutineRunRepository.finish` on a missing row is a no-op, never a
      raise, which matters for leg 3 when a routine is deleted while its run
      is going.
- [ ] AC20a. Timestamps are consistent. Every routine and run timestamp
      (`created_at`, `updated_at`, `next_run_at`, `anchor_at`, `finished_at`,
      `started_at`) is written through one helper in
      `the_one/routines/repository.py`, `_now_iso()`, which returns
      `time_zones.utcnow().isoformat()`. It is called through the module
      namespace (`time_zones.utcnow()`, never `from … import utcnow`) so
      `frozen_clock` bites. A repository test writes runs at chosen instants,
      including one with zero microseconds, and proves the retention cutoff
      compare and the `before=` cursor order them correctly.

**Gate**

- [ ] AC21. `make test-unit` (with `THE_ONE_TEST_NETNS=1`) is green, with the
      expected skip count. `ruff check` and `ruff format --check` are clean.

## Verification Steps

- AC1-AC4: `tests/test_db_migration.py::TestSchemaV45` (fresh replay columns
  via `PRAGMA table_info`, `_fk_rows`, unique and CHECK behaviour, rewind twice,
  rename, delete and upsert cascade).
- AC5-AC9: `tests/test_routines_schedule.py` with `frozen_clock` and explicit
  `after`/`zone`, plus a grep test for `datetime.now(` in `schedule.py`.
- AC10-AC17, AC20: `tests/test_routines_api.py` through the app's test client
  with `auth_headers()`, on a schema-template database.
- AC18: `python -m pytest tests/test_api_name_rule.py -x`.
- AC19: the retention tests with seeded run rows at chosen `finished_at`.
- AC21: `THE_ONE_TEST_NETNS=1 make test-unit`, then `make lint`.

## Implementation Guidance

1. **`the_one/routines/limits.py`**: the constants
   - `ROUTINE_PROMPT_MAX_CHARS = 4000`;
   - `ROUTINES_PER_AGENT_MAX = 50`;
   - `INTERVAL_HOURS_MIN = 1`, `INTERVAL_HOURS_MAX = 168`;
   - `ONCE_MAX_AHEAD_DAYS = 365`;
   - `RUNS_PAGE_DEFAULT = 50`, `RUNS_PAGE_MAX = 200`;
   - `REPEATING_GRACE_CAP = timedelta(hours=2)`, `ONCE_GRACE = timedelta(hours=24)`.

   It also defines `RoutineScheduleError(ValueError)` and
   `RoutineLimitError(ValueError)`, each carrying `.detail`, as in
   `db/_rules.py`. Keep this module a leaf, importing stdlib only.

2. **`the_one/routines/schedule.py`**: pure functions over a frozen dataclass,
   or a pydantic model, per kind.
   - **Wall-clock resolution** (design review: an exact algorithm). For a
     local date and an `HH:MM`:
     1. Build `dt = datetime(y, m, d, H, M, tzinfo=zone)` with `fold=0`.
     2. **The time exists** if `dt.astimezone(UTC).astimezone(zone)` has the
        same wall time. Use `dt.astimezone(UTC)`. `fold=0` is the first
        occurrence of a repeated time, which is AC7's fall-back rule:
        LA 2026-11-01 01:30 → 08:30Z.
     3. **Otherwise it is a gap.**
        - Let `lo = dt.replace(fold=1).astimezone(UTC)`, the new offset and
          the earlier instant.
        - Let `hi = dt.astimezone(UTC)`, the old offset.
        - Let `target_offset = hi.astimezone(zone).utcoffset()`.
        - Return the first instant in `[lo, hi]`, stepping **whole minutes**
          (at most about 120 iterations), whose `astimezone(zone).utcoffset()`
          equals `target_offset`. That instant is the gap's end.
        - Never bisect on timedelta halves: that produced 02:30:37.5 for
          Lord Howe.

     Expected values, verified with zoneinfo:

     | Input | Result |
     |---|---|
     | LA 2026-03-08 02:30 | 10:00Z (03:00 PDT; zoneinfo alone gives 03:30) |
     | LA 02:00 | 10:00Z |
     | London 2026-03-29 01:30 | 01:00Z (02:00 BST) |
     | London 2026-10-25 01:30 | 00:30Z |
     | Kolkata 09:00 | 03:30Z |
   - **Iteration.** Iterate candidate local dates starting from
     `after.astimezone(zone).date()`, for at most 8 days for
     daily/weekdays/weekly.
   - **`interval`.** `anchor + k*hours`, with `k = floor((after - anchor)/h) + 1`
     and `k >= 1`. With `after < anchor` this gives `anchor + h`, not
     `anchor`. That is intended, since the anchor is "now" at creation; state
     it in the docstring and test it.
   - **`once`.** `at` if `at > after`, else `None`.
   - **`grace(schedule, due, zone, anchor)`.** Repeating:
     `min((next_run(after=due) - due) / 2, REPEATING_GRACE_CAP)`. Once:
     `ONCE_GRACE`.
   - **`occurrences_between`.** Walk `next_run` from `start` until past `end`
     or `cap`.
   - **`describe(schedule)`.** Optional. A plain-English sentence is useful to
     the UI later, but the client may build its own; skip it if it isn't
     needed.

3. **Migration v45** in `ensure_schema`, after the v44 block. Write it in the
   v43 style: `CREATE TABLE IF NOT EXISTS` for both tables, with the DD1
   columns and CHECKs and `UNIQUE (agent_name, name COLLATE NOCASE)` as a table
   constraint, then the indexes `idx_agent_routines_due (enabled, next_run_at)`
   and `idx_agent_routine_runs_routine (routine_id, started_at DESC)`. Insert
   schema_version 45, commit, and set `version = 45`. Also:
   - set `CURRENT_VERSION = 45`;
   - add the comment "Any future agent-keyed table must declare ON UPDATE
     CASCADE too";
   - update every `== 44` pin in `tests/test_db_migration.py`, renaming
     `test_current_version_is_44` to `…_is_45` (rename, not delete and re-add).

4. **`the_one/routines/models.py`**:
   - `Routine` mirrors the columns; `schedule` is parsed to a dict.
   - `RoutineRun` mirrors the run columns.

5. **`the_one/routines/repository.py`**, in the `AgentRuleRepository` style:
   - Every method is scoped by `agent_name`.
   - `KeyError` for a missing or other-agent row.
   - One `write_transaction` per mutator.
   - `sqlite3.IntegrityError` on the unique constraint becomes
     `RoutineNameTaken`.
   - The count check (`ROUTINES_PER_AGENT_MAX`) runs inside the create
     transaction.

   **`AgentRoutineRepository`:**
   - `list_for_agent(name)`
   - `get(name, id)`
   - `create(name, fields)`
   - `update(name, id, fields)`
   - `delete(name, id)`
   - `list_due(now_iso)`, for leg 4: enabled, `finished_at IS NULL`,
     `next_run_at <= ?`.
   - `set_next_run(id, next_run_at, *, finished_at=…)`, for legs 3 and 4.

   **`RoutineRunRepository`:**
   - `insert(run)`
   - `finish(run_id, outcome, reason, session_id, new_chat)`
   - `latest(routine_id)`
   - `list(routine_id, limit, before)`
   - `mark_running_interrupted(reason) -> int`
   - `delete_finished_older_than(agent_name, cutoff) -> int` (join through
     `agent_routines`)
   - `delete_all_for_agent(agent_name) -> int`

   **Timestamps** all go through `_now_iso()`, which is
   `time_zones.utcnow().isoformat()` (AC20a), not `now_iso()`.

   **Repository tests** also cover `list_due`. It excludes disabled rows,
   finished rows, rows with a null `next_run_at`, and rows due in the future.

   This leg never sets `finished_at`; legs 3 and 4 do. It only reads and
   clears it.

6. **REST** in `api.py`, next to the rules routes, with a comment banner
   "Routines (M33 F1)". Reuse `_rules_body`-style hand parsing (generalize the
   helper's name if you like, keeping the rules call sites working),
   `_load_agent_or_404` and `_checked_name`.
   - **The target view** resolves `chat_sessions` by `target_session_id` with
     the chat repository; `missing` is true on `KeyError`.
   - **Write order:**
     1. validate the schedule;
     2. compute `next_run_at` with `schedule.next_run(after=utcnow(),
        zone=(await load_effective_zone(conn)).tzinfo, anchor=…)`;
     3. persist.

     For `interval`, `anchor_at` = now on create.
   - **No `poke`** (leg 4).

7. **Retention**:
   - In `run_purge_sweep`, after each agent's chat deletion, call
     `RoutineRunRepository(conn).delete_finished_older_than(name, cutoff)`.
     Sum the counts into `runs_deleted`.
   - `_run_purge_sweep_and_evict` and the seam pass the field through.
   - In `delete_agent_chat_sessions`, call `delete_all_for_agent(name)` and
     add `runs_deleted` to the response.
   - **The seam's response.** `POST /api/_test/purge-sweep` builds its
     response by hand (`api.py`, `trigger_purge_sweep`: `{"deleted": …,
     "last_purge_at": …}`), so add `runs_deleted` to it explicitly.
   - **These exact-dict pins break and are updated in this leg:**
     - `tests/test_db_api.py:3719` and `:3730`
       (`resp.json() == {"status": "ok", "deleted": N}`) gain
       `"runs_deleted": 0`;
     - `tests/test_retention.py:182-186` (the exact sweep result dict) gains
       `runs_deleted`.

     The behavior specs `agent-purge-now-clears-history.md` and
     `agent-history-auto-purge.md` assert only `deleted` and need no change.
     Grep once more for `"deleted":` in `tests/` to catch any other exact pin.

8. **Name-rule test**:
   - add the two routes to `CHECKED`;
   - add a test per route asserting that `"a/b"` and `""` are refused on
     `loc ["name"]`;
   - add `agent_routines` to `test_name_repair.py`'s table loop, seeding one
     routine for the renamed agent in `_seed`.

9. **Docs.** In `the_one/agents.md`, add a "Routines (M33)" section covering:
   - the tables;
   - the schedule kinds and the DST rule (name the zoneinfo 03:30 trap);
   - grace;
   - the REST routes;
   - retention;
   - the `default` refusal;
   - the `chat` target snapshot, taken at write time and not refreshed if the
     session later changes.

   Leg 3 and leg 4 extend this section.

## Edge Cases

- **`frozen_clock` default zone** is America/Los_Angeles. Tests that need
  another zone pass `zone=` explicitly to the pure functions, or parametrize
  `frozen_clock`.
- **Weekly `days`:** deduplicate and sort.
- **`HH:MM`:** zero-padded, 00:00–23:59.
- **Time-setting mode `system`:** the effective zone comes from the host, and
  `frozen_clock` patches `detect_system_zone`.
- **`once` given as `in`:** `amount` must be a positive integer, and the
  computed `at` must still pass the 365-day bound.
- **A PUT that changes only `name` or `prompt`** leaves `next_run_at` alone.
- **Renaming a routine to its own name with different case** succeeds for the
  same row. The unique index allows updating a row to "daily" from "Daily",
  since it is the same row.
- **The `default` agent:** compare the name literally, as other code does.
  Read how `default` is special-cased elsewhere and match it.

## Files Affected

- `the_one/routines/__init__.py`, `limits.py`, `schedule.py`, `models.py`,
  `repository.py`: new.
- `the_one/db/schema.py`: v45.
- `the_one/interfaces/web/api.py`: routine routes; Purge now; sweep
  pass-through.
- `the_one/retention.py`: run retention.
- `the_one/interfaces/web/app.py`: `_run_purge_sweep_and_evict` passes
  `runs_deleted` through, if it shapes the result.
- Tests:
  - `tests/test_db_migration.py`, `tests/test_api_name_rule.py`,
    `tests/test_name_repair.py`, `tests/test_retention.py`: updated;
  - `tests/test_routines_schedule.py`, `tests/test_routines_repository.py`,
    `tests/test_routines_api.py`: new.
- `the_one/agents.md`: the new section.

## Citation Audit

Checked at `c2366221` on branch `flight/01-operator-routines`:
- `the_one/db/schema.py:14` `CURRENT_VERSION = 44`, and the v43 block style.
- `AgentRuleRepository` (`repositories.py`): `write_transaction` per mutator,
  `uuid4().hex`, `now_iso()`.
- `api.py`: `_rules_body`, `_load_agent_or_404`, `_checked_name` (`:184`), and
  `delete_agent_chat_sessions` (`DELETE /agents/{name}/chat/sessions`).
- `retention.py` `run_purge_sweep` (loop over `list_retention_windows`).
- `time_zones.py`: `load_effective_zone(conn=None)`.
- `tests/test_api_name_rule.py`: `CHECKED`/`EXEMPT`.
- `tests/test_db_migration.py:5019,5375,5521,5661-5668`: the 44 pins.
- `tests/test_name_repair.py:154`: the table loop.
- The agent upsert is `ON CONFLICT(name) DO UPDATE` (`repositories.py:265`),
  so it cannot cascade-delete routines.

All verified.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off the
leg in the parent flight, and the commit) are Flight Control protocol, driven
by the execution workflow, and are not repeated here.
