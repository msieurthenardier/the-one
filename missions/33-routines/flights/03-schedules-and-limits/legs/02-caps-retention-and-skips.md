# Leg: caps-retention-and-skips

**Status**: completed
**Flight**: [Schedules and Limits](../flight.md)

## Objective

Land the limit and retention decisions the operator made in planning, none
of which depends on the new schedule shape: one active-routine cap and one
open-routine backstop for every write (DD3), retention for Done routines and
resolved proposals (DD4), and stable skip reason codes with the "still
running" collapse (DD11). Schema v47 adds the two run columns.

## Context

- **Leg 1 has landed** (uncommitted, Batch A): the routine routes now live in
  `the_one/interfaces/web/routines_api.py`, included into `api.router`;
  helpers are looked up through the `api` module at call time. Read the leg 1
  flight-log entry before starting. Purge now (`DELETE /api/agents/{name}/chat/sessions`)
  and the purge-sweep test seam (`POST /api/_test/purge-sweep`) stay in `api.py`.
- **Today's caps** (`the_one/routines/limits.py`):
  - `ROUTINES_PER_AGENT_MAX = 50` — a total over **every** row (disabled and
    Done included), checked in `AgentRoutineRepository.create` with
    `SELECT COUNT(*) … WHERE agent_name = ?`, for operator and agent alike.
  - `AGENT_ACTIVE_ROUTINES_MAX = 10` and `AGENT_RUNS_PER_DAY_MAX = 48` with
    `runs_per_day` and `_measures`, checked by `check_agent_caps(before, after, now)`
    (raise-only) only when `agent_caps=True`: in the repository's
    `create`/`update`/`delete` through `_caps_after`, and at proposal time in
    `service.agent_change` (`insert_pending(caps_check=…)`).
  - `AGENT_PROPOSALS_KEPT = 500`, enforced by `proposals._prune`, called from
    `insert_applied`, `resolve` and `insert_pending`.
- **The decisions (flight DD3, DD4, DD11):**
  - `ROUTINES_ACTIVE_MAX = 50` (enabled and not Done) and
    `ROUTINES_OPEN_MAX = 200` (not Done, on or off), both raise-only, for
    **every** write — operator REST and agent tools — in the repository's
    write transaction (precheck, caps, write, proposal), at proposal time,
    and at approval. Run now never counts. The scheduler's own advances
    (`advance_if_due`, finishing a one-off) never raise either count and are
    not checked.
  - Refusals: "This agent already has 50 active routines, the most allowed.
    Turn one off or delete one first." and "This agent already has 200
    routines that are not done, the most allowed. Delete some first." (422 on
    REST with the existing error mapping; the tool's one-sentence refusal for
    the agent).
  - Removed: `ROUTINES_PER_AGENT_MAX`, `AGENT_ACTIVE_ROUTINES_MAX`,
    `AGENT_RUNS_PER_DAY_MAX`, `runs_per_day`, `AGENT_PROPOSALS_KEPT`,
    `_prune` and its three calls.
  - Unchanged: `AGENT_ROUTINE_WRITES_PER_TURN` 5,
    `AGENT_ONCE_MIN_AHEAD_MINUTES` 1 (agent only, `service._min_ahead`),
    `AGENT_PENDING_PROPOSALS_MAX` 20, the prompt limit, the one-year limit,
    and the interval hours range (the 1-minute floor arrives with the new
    shape in leg 3/4).
  - **Retention** (`retention.run_purge_sweep`, per agent, the same cutoff
    as chats and runs):
    - delete the agent's routines with `finished_at` older than the cutoff,
      first superseding their pending proposals (status `superseded`,
      `resolved_at` now), as `AgentRoutineRepository.delete` does; their
      run rows cascade;
    - delete the agent's proposals with `status != 'pending'` and
      `resolved_at` older than the cutoff;
    - the result gains `routines_deleted` and `proposals_deleted`; the
      test seam `POST /api/_test/purge-sweep` returns them; the lifespan
      wrapper `_run_purge_sweep_and_evict` passes them through.
  - **Purge now** also deletes the agent's resolved proposals (never
    pending ones, never routines); its response gains `proposals_deleted`.
    If the agent editor shows any description of what Purge now clears,
    it says "and the agent's resolved routine changes"; the button's
    `confirmLabel` stays.
  - **Skip reason codes:** every run row written as `skipped` gets a
    `reason_code`: `still_running` (scheduler: "The previous run was still
    going."), `chat_busy` (`runner.classify`: "The chat stayed busy for …"),
    `waiting_sign_in` (runner: "The chat is waiting for a sign-in."). Other
    outcomes leave it null.
  - **The collapse:** when the scheduler skips a run as `still_running` and
    the routine's newest run row (by `started_at`) is a `still_running`
    skip, it increments that row's `repeats`, sets its `finished_at` and
    `due_at` to the latest values, and rewrites its reason to "Skipped {n}
    times while the previous run was still going." — read-then-update in
    one repository transaction. Otherwise it inserts a row as today
    (`repeats` 1, today's sentence).
- **Schema v47** (`the_one/db/schema.py`, idempotent, guarded `ALTER`s in the
  v46 style): `agent_routine_runs.repeats INTEGER NOT NULL DEFAULT 1` and
  `agent_routine_runs.reason_code TEXT`. `CURRENT_VERSION = 47`. `RoutineRun`
  gains `repeats: int = 1` and `reason_code: str | None = None`; the runs
  repository reads and writes both; the runs route (`model_dump`) returns
  them.
- **Tool text:** `routines/tools.py::_LIMITS_SENTENCE` becomes "At most 50
  active routines and 5 changes a turn. Your operator may need to approve."
  This is platform prompt text (Mission 30 convention); the flight's leg 5
  eval run covers this change together with the schedule text, so this leg
  records the change in the flight log for leg 5 and runs no evals.
- **`limits_view()`** (`GET …/routines` `limits`): drop
  `routines_per_agent`; add `active_max` (50) and `open_max` (200). The
  browser reads only `prompt_chars`, `interval_hours_max` and
  `run_timeout_seconds` today; `tests/test_routines_api.py` pins the dict.

## Inputs

- Flight spec DD3, DD4, DD11.
- `the_one/routines/{limits,repository,service,proposals,scheduler,runner,tools,models}.py`,
  `the_one/retention.py`, `the_one/db/schema.py`, `the_one/interfaces/web/api.py`
  (Purge now, the purge-sweep seam), `the_one/interfaces/web/app.py`
  (`_run_purge_sweep_and_evict`), `the_one/interfaces/web/static/js/areas/studio/general-tab.js`.
- Tests: `tests/test_routines_proposals.py`, `tests/test_routines_repository.py`
  (imports `ROUTINES_PER_AGENT_MAX`, about `:14`, `:77`),
  `tests/test_routines_api.py` (the `limits` dict, about `:112`),
  `tests/test_routines_service.py` (`limits_view()["routines_per_agent"]`,
  about `:200`, `:298`), `tests/test_routine_tools.py` (asserts "10 active",
  "48 runs" in the description, about `:595`),
  `tests/test_routines_self_config_api.py`, `tests/test_retention.py`
  (the exact sweep-result dict, about `:186`, and the "leaves proposals"
  test), `tests/test_routines_scheduler.py`, `tests/test_routines_runner.py`,
  `tests/test_routines_classify.py`, `tests/test_db_migration.py`,
  `tests/test_seam_routes_403_sweep.py` and `tests/test_chat_history_purge.py`
  (check for sweep and Purge now response pins).
- `tests/behavior/agent-history-auto-purge.md`: if it documents the sweep
  result or the Purge now response, add the new keys.

## Outputs

- The two caps and their refusals; the removed constants gone.
- Retention and Purge now as above.
- v47, the run model fields, reason codes and the collapse.
- Tests (below); docs: `the_one/agents.md` "Routines (M33)" (caps, retention,
  v47, reason codes), `SECURITY-MODEL.md` "Routines" (the caps paragraph and
  the "proposals record is never purged" bullet near `:617` rewritten, the
  no-runs-a-day trade-off stated as in DD3), CLAUDE.md's Routines paragraph
  if it names a removed cap. Grep `the_one/agents.md` (around L2798-2816)
  for "10 active", "48", "500" and "never touch".
- Flight log entry, including a note for leg 5 that `_LIMITS_SENTENCE` changed.

## Acceptance Criteria

- [ ] AC1. A create (enabled), an enable, or a reopen that would make the
      agent's active routines exceed 50 is refused with the DD3 sentence, on
      the operator REST routes and through the agent tools; a write that
      does not raise the active count passes even when the agent is over 50
      (a rename, a prompt edit, a turn-off, a delete).
- [ ] AC2. A write that would make the agent's not-Done routines exceed 200
      is refused with its sentence, raise-only in the same way; Done
      routines do not count toward either cap.
- [ ] AC3. Both caps apply at proposal time (a pending create that would
      exceed a cap is refused) and again at approval: approving a pending
      create after the agent filled up is refused with **422** and the DD3
      sentence (the approve route's existing `except RoutineLimitError`
      mapping), and the proposal is still `pending` (the transaction rolls
      back before `ProposalOp.resolve`). Approving a pending update that
      only renames passes while the agent is over the cap (raise-only).
      Approval already re-runs caps through `create_routine`/`update_routine`
      with `agent_caps=True`; what is new is that the caps no longer depend
      on that flag.
- [ ] AC4. `ROUTINES_PER_AGENT_MAX`, `AGENT_ACTIVE_ROUTINES_MAX`,
      `AGENT_RUNS_PER_DAY_MAX`, `runs_per_day`, `AGENT_PROPOSALS_KEPT` and
      `_prune` no longer exist (`grep -rn` over `the_one/` and `tests/` finds
      none); tests that pinned them are rewritten for the new caps (renamed,
      so the intent shift reads in `git blame`).
- [ ] AC5. The sweep deletes, per agent, Done routines older than the cutoff
      (with their runs) and resolved proposals older than the cutoff;
      it leaves enabled or off routines that are not Done, pending
      proposals, and anything newer than the cutoff. A pending proposal for
      a swept routine is superseded, never left pointing at a null
      `routine_id`. The sweep result and the test seam carry
      `routines_deleted` and `proposals_deleted`.
      `test_run_purge_sweep_leaves_routine_proposals` is inverted and renamed.
- [ ] AC6. Purge now deletes resolved proposals and keeps pending ones and
      every routine; its response carries `proposals_deleted`.
- [ ] AC7. v47 adds `repeats` (default 1) and `reason_code` to
      `agent_routine_runs`; a `TestSchemaV47` class covers fresh replay,
      columns and defaults on existing rows, and rewind idempotency; every
      `== 46` version pin and the runs column list move.
- [ ] AC8. Every skipped run row carries its `reason_code`
      (`still_running`, `chat_busy`, `waiting_sign_in`), and the runs route
      returns `repeats` and `reason_code`.
- [ ] AC9. Three consecutive "still running" skips leave one row with
      `repeats` 3 and the reason "Skipped 3 times while the previous run was
      still going."; the row keeps its first `trigger_kind` and its
      `started_at` (only `finished_at`, `due_at`, `repeats` and the reason
      move, so `before=started_at` paging stays stable). A skip after a
      different row (an `ok` run, a `chat_busy` skip), after a pre-v47
      `still_running`-text row with a null `reason_code`, or on another
      routine inserts a new row. Existing rows are not backfilled.
- [ ] AC10. `limits_view()` returns `active_max` and `open_max` and no
      `routines_per_agent`; `_LIMITS_SENTENCE` reads as in Context.
- [ ] AC11. `THE_ONE_TEST_NETNS=1 make test-unit` passes (15 skipped);
      ruff clean; the `agent-routines` lane passes (the Routines tab reads
      `limits` and the run history).

## Verification Steps

- AC1-AC3, AC5-AC6, AC8-AC10: unit tests, named in the flight log.
- AC4: the grep.
- AC7: the migration tests.
- AC11: the commands, and
  `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane agent-routines`.

## Implementation Guidance

1. v47 and the model fields first (guarded `ALTER`s with `PRAGMA
   table_info`, and the fresh-schema `CREATE TABLE agent_routine_runs` too,
   so a fresh replay and an upgrade match); move the version pins
   (`tests/test_db_migration.py` has `== 46` pins near L5019, 5375, 5521,
   5662, 5668, 5799, 5893, 5948, 5953 and `_RUN_COLS` near L5748).
2. Caps: replace `check_agent_caps`'s measures with the two counts and run
   the check **always** on create and update in the repository, as a
   separate always-on step (a delete never raises a count, so it may skip
   the read). **Keep the `agent_caps` parameter**, now meaning only the
   agent-only minimum lead time (`service._min_ahead`), so `service.py`'s
   call sites barely change. Keep the raise-only semantics and the
   in-transaction order (precheck, caps, write, proposal). In
   `insert_pending`, `caps_check` runs after the "supersede earlier pending
   for the same routine" UPDATE and must stay there: it has to see the
   post-supersede state, and its refusal rolls the supersede back.
3. Retention in `run_purge_sweep` (a repository method per deletion, in
   the style of `RoutineRunRepository.delete_finished_older_than`), the
   wrapper and the test seam; Purge now (`delete_agent_chat_sessions` in
   `api.py`) through a new proposals-repository method that deletes
   resolved rows only. The agent editor shows no description of Purge now
   (`general-tab.js` has only the button and "Confirm purge?"), so there is
   no UI change.
4. Reason codes at the three skip sites:
   - the scheduler's skip is an INSERT through `_record`: pass
     `still_running`;
   - both runner skips end through `end()` → `_finish_row` →
     `RoutineRunRepository.finish(run_id, outcome, reason, session_id, new_chat)`,
     an UPDATE: `finish` gains a `reason_code` parameter. `chat_busy` is
     set where the timed-out, never-started "skipped" path is taken, never
     by matching the reason text. Leave `classify` a 2-tuple (pinned by
     `tests/test_routines_classify.py`) and compute the code beside its
     call, or change its return and update that test — say which in the
     flight log. The sign-in skip passes `waiting_sign_in` directly.
     `_fail_early` writes only `failed` rows and needs no change;
   - one test per path.

   The collapse: a repository method doing read-then-update in one
   `write_transaction`; new columns go last in `RoutineRunRepository._COLS`
   and `_row`, and `insert`'s placeholder count grows.
5. `limits_view`, `_LIMITS_SENTENCE`, tests, docs, flight log.

## Edge Cases

- An agent already over 50 active (possible after this leg, because the
  operator's old limit was 50 total): every lowering write still passes.
- **A Done routine with a `running` run.** Every executing one-off is
  Done while it runs: `scheduler._handle` calls `advance_if_due(...,
  finished=now)` before `_spawn`, and the runner inserts the `running` row
  after. A stuck row can outlive the cutoff if the process died before the
  startup `mark_running_interrupted`. The sweep's delete carries
  `AND NOT EXISTS (SELECT 1 FROM agent_routine_runs WHERE routine_id =
  agent_routines.id AND outcome = 'running')`, with a test. (Deleting a
  routine mid-run is otherwise tolerated: `finish()` is a no-op on a
  missing row.)
- Retention windows: `chat_history_retention_days` is 1-365
  (`ge=1, le=365`), so there is no "keep forever" value; the minimum
  cutoff is one day.
- The collapse must not merge across a `manual` run or across routines.

## Files Affected

- `the_one/routines/{limits,repository,service,proposals,scheduler,runner,tools,models}.py`
- `the_one/retention.py`, `the_one/db/schema.py`
- `the_one/interfaces/web/api.py` (Purge now, test seam), `app.py` (sweep wrapper)
- possibly `static/js/areas/studio/general-tab.js` (Purge now description)
- the tests listed in Inputs
- `the_one/agents.md`, `SECURITY-MODEL.md`, CLAUDE.md, the flight log

## Citation Audit

Checked at `49a5051a` (leg 1 does not touch these):
- `limits.py` constants and `check_agent_caps`; `repository.py` `_caps_after`,
  `create`'s `COUNT(*)`, `update`/`delete` `agent_caps` paths;
  `proposals.py::_prune` and its three callers; `service.agent_change`'s
  `caps_check`; `service.limits_view`; `tools.py::_LIMITS_SENTENCE` — verified.
- `retention.run_purge_sweep`; `api.py` Purge now returning `runs_deleted`
  and `trigger_purge_sweep`; `app.py::_run_purge_sweep_and_evict` — verified.
- `runner.classify` "The chat stayed busy for …" and the sign-in skip;
  `scheduler._handle`'s "The previous run was still going." — verified.
- `tests/test_retention.py::test_run_purge_sweep_leaves_routine_proposals`;
  `tests/test_routines_api.py` `limits` dict pin — verified.

Design review cycle 1 (Sonnet Developer, approve with changes) applied:
AC3 made 422 and pending-preserving, with a rename-over-cap case; the
runner's reason codes go through `finish()` (an UPDATE), never by text
matching; the sweep's `running` guard is specified; pinned tests and
docs added to Inputs; the collapse's trigger, `started_at` and pre-v47
rules stated; "keep forever" corrected (1-365 days); Purge now needs a new
repository method and no UI change; the `insert_pending` ordering stated;
`agent_caps` kept for the lead time only. No backfill of old skip rows.
