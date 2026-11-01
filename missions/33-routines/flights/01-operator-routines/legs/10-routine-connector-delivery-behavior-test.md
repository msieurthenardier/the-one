# Leg: routine-connector-delivery-behavior-test

**Status**: completed
**Flight**: [Operator Routines, End to End](../flight.md)

## Objective

Prove on a live dev instance that operator routines deliver through a
connector, using `tests/behavior/routine-connector-delivery.md`:
- the reply is posted to the channel and the prompt never is;
- the run's message is stored as the routine's;
- a scheduled one-off fires on its own;
- after `/new`, a run lands in the channel's new chat;
- the peer's reply continues that chat.

## Context

- Flight DD13, and mission criterion 3 ("The reply lands in the target",
  behavior-test-backed).
- The spec was drafted at flight planning, before the routes landed. This
  leg first re-checks every step against the landed shapes, then runs the
  test.
- The Flight Director runs it with `/mission-control:behavior-test`, not as a
  Developer spawn. A failing run is an unmet acceptance criterion: fix in a
  new commit and re-run, or the operator accepts it as a known issue.

## Inputs

- Batches A and B committed: the routes, the runner, the scheduler, the tab.
- `tests/behavior/routine-connector-delivery.md` (draft).
- CLAUDE.md "Behavior-test credential convention" and the "SAFETY RULE".
- Squawk 0278: `serve` does not create the credential, so run
  `the-one rotate-api-credential` against the scratch data dir first.

## Outputs

- **The spec**, `tests/behavior/routine-connector-delivery.md`, finalized:
  `Status: active`, and every step's route, field name and value matches the
  code (`next_run_at`, `finished_at`, `target.session_id`, the
  `/_test/stub/outbound` record fields `connector_id`/`channel_id`/`peer_id`,
  `routine_name`, `session_metadata.routine`).
- **A run log** at `tests/behavior/routine-connector-delivery/runs/{ts}.md`
  (committed), with evidence outside the repo.
- **A flight-log entry** that references the run log.

## Acceptance Criteria

- [x] AC1. **The spec matches the landed code.** It reads the stub outbound
      shape, the run row fields and the routine row fields as they really
      are, and its preconditions name a dev port of 8490 or higher, a
      scratch data dir under `$HOME`, a scratch cwd, the two gate env vars
      and the credential rotation.
- [x] AC2. `/mission-control:behavior-test routine-connector-delivery`
      passes every step, and the run log is committed.
- [x] AC3. **The instance is stopped by its recorded PID**, and the scratch
      data dir is removed. Ports 8484 and 8485 and the operator's default data
      directory were never touched: check that dir with
      `python -c "from the_one.config import settings; print(settings.data_dir)"`
      before and after.

## Verification Steps

- AC1: read the spec against `the_one/interfaces/web/api.py` (the routine
  routes and `/_test/stub/outbound`) and `the_one/routines/models.py`.
- AC2: the run log's verdict.
- AC3: the run log's teardown section.

## Implementation Guidance

1. Re-check each step of the spec against the code, and edit the wording
   where a field or route differs.
2. Pick a free port of 8490 or higher. Check `ss -ltn` first.
3. Run `/mission-control:behavior-test routine-connector-delivery`.
4. If a step fails, diagnose it. A product defect is fixed by a Developer
   spawn and committed, then the test is re-run. A spec defect is
   re-authored, and the edit is recorded in the flight log.

## Edge Cases

- **Step 6 waits on real time** (about 1 to 2.5 minutes). The poll bound in
  the spec is 150 seconds.
- **The stub DM's `channel_id=""`.** Step 7 compares the targets of two
  routine sends, and both carry the same `""` channel, so the check holds
  but is weak (flight-design cycle 2 note).

## Files Affected

- `tests/behavior/routine-connector-delivery.md`
- `tests/behavior/routine-connector-delivery/runs/{ts}.md` (new)
- `missions/33-routines/flights/01-operator-routines/flight-log.md`
