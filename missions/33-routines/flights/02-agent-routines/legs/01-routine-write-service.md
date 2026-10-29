# Leg: routine-write-service

**Status**: completed
**Flight**: [Agents Schedule Their Own Routines](../flight.md)

## Objective

Move the routine write rules out of `the_one/interfaces/web/api.py` into a
new `the_one/routines/service.py`. The REST routes then become thin adapters
over the service, and their behaviour does not change at all.

## Context

- **Flight DD3.** The agent's routine tools (leg 3) and proposal approval
  (leg 2) must enforce exactly the operator's rules, so those rules need one
  home.
- **The pattern is Flight 1's leg 2** (`connector-delivery-split`): a pure
  extraction, held by an existing test file that must pass unedited.
- **This leg changes no behaviour.** It adds no agent, proposal, flag or cap
  logic; those come in legs 2 and 3. The service's surface is shaped so they
  can extend it.

## Inputs

`main` at `6ed89395` (Flight 1 merged), on branch
`flight/02-agent-routines`. The code it extracts lives in
`the_one/interfaces/web/api.py` (verified at leg design):

**Small helpers:**
- `_routine_422` (`:1602`);
- `_routines_limits` (`:1609`);
- `_poke_scheduler` (`:1619`), which uses `_get_routine_scheduler`, imported
  at `:120`;
- `_routines_agent_or_404` (`:1627`);
- `_routines_repos` (`:1633`);
- `_routine_body` (`:1638`).

**The write rules:**
- `_routine_prompt(value)` (`:1648`);
- `_ROUTINE_DATE_RE`;
- `_routine_schedule(raw, now, zone)` (`:1664`);
- `async _routine_target(raw, agent_name)` (`:1725`), which uses `_chat_repo()`
  (`:445`);
- `async _routine_view(routine, run_repo, chat_repo)` (`:1762`).

**The routes:**
- `create_agent_routine` (`:1822`): the `default` refusal, `_checked_name`,
  the prompt, the zone, the schedule, the target, `enabled`, the anchor, the
  next run, `repo.create`, the `RoutineNameTaken` → 409 and
  `RoutineLimitError` → 422 mappings, and the poke;
- `update_agent_routine` (`:1874`): the whole update state machine (the
  schedule-change, re-enable and finished rules);
- `delete_agent_routine` (`:1938`).

**Name checks:** `_checked_name` (`:190`) wraps
`the_one.naming.check_name`, whose `NameRuleError` becomes a 422 through
`name_rule_detail`. `_name_conflict_detail` is at `:198`.

**The tests:**
- `tests/test_routines_api.py` (749 lines) patches
  `the_one.interfaces.web.api.get_connection` and `api.get_encryptor`
  (`:34-35`). The service therefore must not call `get_connection()` itself.
- `tests/test_routines_scheduler.py:368-373`
  (`test_poke_scheduler_tolerates_none`) calls `api._poke_scheduler()`
  directly.

## Outputs

**New: `the_one/routines/service.py`.** It never calls `get_connection()`,
`get_encryptor()` or `HTTPException`. It holds:

**Errors:**
- `RoutineFieldError(field: str, message: str)`, a `ValueError` subclass, in
  `routines/limits.py` beside the other routine errors.
- It also raises the existing `RoutineScheduleError`, `RoutineLimitError`,
  `RoutineNameTaken` and `the_one.naming.NameRuleError`, unchanged.

**Validators**, pure where the originals were pure:
- `validate_prompt(value) -> str`;
- `validate_schedule(raw, now, zone) -> dict`;
- `async resolve_target(raw, agent_name, chat_repo) -> dict`;
- `validate_enabled(value) -> bool`.

Each raises `RoutineFieldError(field, msg)` with exactly today's message
strings.

**The writes**, each taking its repositories and zone from the caller. They
return the stored `Routine`, and `delete_routine` returns `None`:
- `async create_routine(repo, chat_repo, agent_name, data, *, now, zone)`;
- `async update_routine(repo, chat_repo, agent_name, current, data, *, now, zone)`.
  It takes the loaded `current` routine and applies today's state machine
  verbatim: the schedule-change precedence, the `finished_at` clear, "Set a
  new time to run it again.", the interval re-anchor on re-enable, and a
  past one-off on re-enable marked Done.
- `async delete_routine(repo, agent_name, routine_id)`.

`create_routine` and `update_routine` take the raw request `data`. The name
goes through `check_name`, so a `NameRuleError` propagates.

**Other functions:**
- `async routine_view(routine, run_repo, chat_repo) -> dict`, moved verbatim.
- `poke_scheduler()`, moved from `api._poke_scheduler`. It is called by the
  three writes on success, and it uses `routines.scheduler.get_scheduler`.
- `limits_view() -> dict`, moved from `_routines_limits`.

**`the_one/interfaces/web/api.py`:**
- The three write routes call the service and map its errors:
  - `RoutineFieldError` → `_routine_422(field, msg)`;
  - `NameRuleError` → 422 `name_rule_detail` (the `_checked_name` shape);
  - `RoutineNameTaken` → 409 `_name_conflict_detail`;
  - `RoutineLimitError` → 422 `e.detail`;
  - `KeyError` → 404.
- The `default` refusal (422 "Routines need a named agent." on create) and
  the 404 checks stay in the routes, in today's order. The order matters:
  create refuses `default` before reading the body, and the others 404 first.
- The routes keep resolving `conn` through `api.get_connection` and the zone
  through `time_zones.load_effective_zone(conn)`, then pass `zone` (as
  `.tzinfo`) and `now = time_zones.utcnow()`.
  - **The zone is loaded only where it is today.** Create always loads it.
    Update loads it only on a schedule change or a re-enable.
  - So `update_routine` takes a zone *loader*: an async callable it awaits
    only when needed. A test that counts connection use, or freezes the zone,
    cannot tell the difference.
- `_routine_view`, `_routines_limits` and `_poke_scheduler` either stay as
  one-line delegates or are removed where nothing references them.
  `api._poke_scheduler` must remain importable as a delegate
  (`test_routines_scheduler.py:373`).
- The list, get, run and runs routes are unchanged apart from calling the
  moved `routine_view` and `limits_view`.

**Tests:**
- `tests/test_routines_service.py` (new) tests the service directly, against
  a template database (`connect_template_db`). It covers:
  - each validator's refusals and their exact messages;
  - create with each target kind, and the anchor and next run for an
    interval;
  - the update state machine's branches (schedule change clears Done,
    re-enable of a Done one-off refused, interval re-anchor on re-enable, a
    past one-off on re-enable marked Done);
  - the name refusal (`NameRuleError`), the duplicate (`RoutineNameTaken`)
    and the cap (`RoutineLimitError`);
  - that the poke is called once per successful write and not on a refused
    one. Use a stub scheduler through `routines.scheduler.set_scheduler`.
- **`tests/test_routines_api.py` passes unedited.**

**Docs:**
- `the_one/agents.md` "Routines (M33)": one paragraph naming
  `routines/service.py` as the single home of the routine write rules, and
  the conn-from-caller rule.
- Flight log: the leg 1 entry.

## Acceptance Criteria

- [ ] AC1. `git diff --stat main -- tests/test_routines_api.py` is empty, and
      the file passes: the same pass count before and after. Record both
      counts in the flight log.

      If the file cannot pass unedited, stop, revert this leg's changes to
      `api.py` and the service, and signal
      `[BLOCKED:routine-service-not-contained]`. That is the flight's divert
      condition. Do not edit the test.
- [ ] AC2. `the_one/routines/service.py` exists with the functions in
      Outputs. `grep -n "get_connection\|get_encryptor\|HTTPException\|fastapi"`
      on it finds nothing.
- [ ] AC3. The three write routes in `api.py` contain no schedule, target,
      prompt or update-state-machine logic. They parse the body, check
      `default` and 404, call the service and map its errors.
      `_routine_schedule`, `_routine_target` and `_routine_prompt` no longer
      exist in `api.py`.
- [ ] AC4. `tests/test_routines_service.py` covers each item listed in
      Outputs and passes.
- [ ] AC5. `tests/test_routines_scheduler.py`, `tests/test_routines_runner.py`,
      `tests/test_api_name_rule.py` and `tests/test_routines_repository.py`
      pass unedited.
- [ ] AC6. `THE_ONE_TEST_NETNS=1 make test-unit` is green with the expected
      15 skipped. `ruff check` and `ruff format --check` are clean on
      `the_one/ tests/ scripts/ evals/`.
- [ ] AC7. `the_one/agents.md` names the service.

## Verification Steps

- AC1: before any edit, run
  `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_routines_api.py -x --timeout 30`
  and note the count. Run it again at the end, then
  `git diff --stat main -- tests/test_routines_api.py`.
- AC2/AC3: grep as stated. Read the three routes.
- AC4/AC5/AC6: the named runs and `make test-unit`.

## Implementation Guidance

1. Record AC1's "before" count first.
2. Create `service.py` by moving the code, not rewriting it. Keep every
   message string byte-identical. The API tests assert on them.
3. Convert `_routine_422(field, msg)` raises into `RoutineFieldError(field, msg)`.
   Convert `_chat_repo()` calls into the passed `chat_repo`.
4. Rewire the routes. Keep their check order (body parse, `default`, 404,
   name, prompt, schedule, target, enabled) so that a body with several bad
   fields gets the same first error as today.
5. Write `tests/test_routines_service.py`.
6. Run the gates, then update `agents.md` and the flight log.

## Edge Cases

- **Error order:** today `create_agent_routine` checks the name before the
  prompt, then the schedule and the target. `create_routine` must check in
  the same order, because the API tests send multi-error bodies.
- **The two zone loads** are deliberate (DD3 of Flight 1 leg 1). Keep loading
  lazy in update, so a name-only PUT does not touch time settings.
- **`RoutineFieldError` is a `ValueError`.** Make sure no route's broad
  `except ValueError` already exists to swallow it. There is none in these
  three routes today; keep it that way.

## Files Affected

- `the_one/routines/service.py` (new)
- `the_one/routines/limits.py` (`RoutineFieldError`)
- `the_one/interfaces/web/api.py`
- `tests/test_routines_service.py` (new)
- `the_one/agents.md`
- `missions/33-routines/flights/02-agent-routines/flight-log.md`

## Citation Audit

Verified at leg design against the working tree at `5b607af3`:
- the `api.py` helpers and routes at the cited lines;
- the `test_routines_api.py:34-35` patches;
- `test_routines_scheduler.py:373`'s call to `api._poke_scheduler`.

No citation drifted.
