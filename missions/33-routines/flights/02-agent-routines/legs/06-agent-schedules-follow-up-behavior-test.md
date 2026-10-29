# Leg: agent-schedules-follow-up-behavior-test

**Status**: completed
**Flight**: [Agents Schedule Their Own Routines](../flight.md)

## Objective

Run the live behavior test `agent-schedules-follow-up` (flight DD13) against
a dedicated dev instance with a real local model. It proves that an agent
schedules its own follow-up when the operator allows it, that the follow-up
runs unattended, and that approval mode and cancel work end to end.

## Context

- **Legs 1-5 are committed** (`446b7388`, `ee4e8c5b`). The spec was finalized
  against `ee4e8c5b` by the FD (see the spec's header note); no route or
  field in it is a guess.
- **This leg changes no code.** It runs the spec through
  `/mission-control:behavior-test`, which the Flight Director invokes
  directly; there is no Developer spawn. A failure is an unmet acceptance
  criterion: diagnose it, fix it in a new commit through a Developer, and
  re-run.
- **The apparatus is shell-only** (curl through the shell, with the bearer
  credential) plus the stub connector seams (`THE_ONE_STUB_TEST_ENDPOINT=1`).
  The act path is `POST /api/_test/stub/inbound`. The read paths are
  `GET /api/_test/stub/outbound`, the routine, run and proposal routes, and
  the chat's stored messages.
- **Low risk.** It is a read-and-drive leg with no source change, so it gets
  no design review.

## Inputs

- `tests/behavior/agent-schedules-follow-up.md` (status `ready`).
- Flight 1's run log `tests/behavior/routine-connector-delivery/runs/2026-10-29-03-31-37.md`,
  the reference for the stub connector setup calls.
- CLAUDE.md "Behavior-test credential convention" and its SAFETY RULE.

## Outputs

- **Re-checked external sessions,** recorded in the flight log before the
  run: `curl -s 127.0.0.1:11434/api/tags` lists `gpt-oss:20b`.
- **A dev instance:**
  - port 8490 or higher;
  - scratch data dir `$HOME/the-one-behavior-test-scratch/data`, wiped fresh;
  - scratch cwd `$HOME/the-one-behavior-test-scratch/cwd`;
  - `THE_ONE_DEV_MODE=true THE_ONE_STUB_TEST_ENDPOINT=1`;
  - its PID recorded, and stopped by that PID afterwards.
- **A run log** at `tests/behavior/agent-schedules-follow-up/runs/<ts>.md`
  (committed). Evidence lives under `/tmp/behavior-tests/…` and is never
  committed.
- **The spec's `Last Run`** updated.
- **A flight log entry:** the run log path, the verdicts, any model switch
  (the spec allows `qwen3:30b` after two failed tries at step 3), and the
  wall time.

## Acceptance Criteria

- [ ] AC1. `/mission-control:behavior-test agent-schedules-follow-up` passes
      every checkpoint, or the operator accepts a recorded failure as a known
      issue.
- [ ] AC2. The instance never touched port 8484 or 8485, or the default data
      directory (`settings.data_dir`, read rather than guessed). It ran from
      the scratch cwd and was stopped by its recorded PID.
- [ ] AC3. The run log is committed. No evidence file is under the repo.

## Verification Steps

- AC1: the run log's checkpoint verdicts.
- AC2: the instance's `/proc/<pid>/environ` (`THE_ONE_PORT`, `THE_ONE_DATA_DIR`)
  and `/proc/<pid>/cwd`, read before the first step.
- AC3: `git status` after the run.

## Edge Cases

- **The model does not call `schedule_routine`** in step 3. Retry once. Then
  switch to `qwen3:30b` and record the switch.
- **A real-time wait.** Step 4 waits for the routine to fire. In
  re-spawn-per-checkpoint mode the Orchestrator waits, not an agent: one spawn
  reads `next_run_at`, the Orchestrator waits past it, and a second spawn
  polls the runs.
- **The 1-minute minimum.** An agent's one-off must be at least 1 minute
  ahead (`AGENT_ONCE_MIN_AHEAD_MINUTES`), so "in 2 minutes" is within the
  rules.

## Citation Audit

Checked against `ee4e8c5b`:
- the routes `GET`/`PUT /agents/{name}/self-configuration/routines`, the
  `.../proposals` routes (list, `pending-count` `{count}`, approve, dismiss),
  and `.../routines/{id}/runs`, in `the_one/interfaces/web/api.py`;
- the routine view's fields (`routines/service.py::routine_view`);
- `RoutineProposal` (`routines/proposals.py`);
- `TriggerKind` (`routines/models.py`);
- the `peer:{name}` source label (`agent/taint.py`).
