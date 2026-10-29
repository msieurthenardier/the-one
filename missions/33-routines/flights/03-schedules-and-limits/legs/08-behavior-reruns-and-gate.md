# Leg: behavior-reruns-and-gate

**Status**: completed
**Flight**: [Schedules and Limits](../flight.md)

## Objective

Prove the flight end to end (DD13): re-author the two routine behavior
specs' assertions on the stored schedule shape, re-run both live on a
dedicated dev instance, run the full quiet-host gate on one commit, and set
lane budgets from it, giving the `routing` and `agents` lanes headroom
(DD9).

## Context

- **Legs 1-7 are committed** (Batch A `54d87b8a`, Batch B — legs 4, 5, 7 —
  at its review commit). Read the flight log.
- **Spec re-authoring** (a deliberate spec change, recorded in each spec's
  header note; the FD does it, it is artifact text):
  - `tests/behavior/agent-schedules-follow-up.md`:
    - step 3 "schedule kind `once`" becomes "a one-off (`schedule.repeat`
      null)";
    - step 5 "a `once` (or `daily`) schedule" becomes "a one-off or a daily
      recurrence (`repeat` null, or `repeat.every` 1 with `unit` `day`)";
    - any other `kind` mention is updated, and the header note records the
      DD1 shape and that the model is taught only the canonical shape
      (leg 5).
  - `tests/behavior/routine-connector-delivery.md`: its REST requests keep
    the legacy shapes (step 3 `{"kind":"daily","time":"09:00"}`, step 6
    `{"kind":"once","at":…}`), which proves the DD5 aliases live. Step 6's
    one-off `at` is now rounded up to the minute (DD5), so "1 minute from
    now" lands 1-2 minutes out: widen its poll window to 180 s. Any
    assertion on the stored schedule shape moves to DD1.
- **The runs** are FD-driven through `/mission-control:behavior-test
  <slug>` (no Developer), one at a time:
  - a dev instance per run: port 8490 or higher, scratch data dir
    `$HOME/the-one-behavior-test-scratch/data` wiped fresh, scratch cwd
    `$HOME/the-one-behavior-test-scratch/cwd`, `THE_ONE_DEV_MODE=true
    THE_ONE_STUB_TEST_ENDPOINT=1`, PID recorded and the instance stopped by
    that PID; `/proc/<pid>/environ` and `/proc/<pid>/cwd` read before the
    first step;
  - `gpt-oss:20b` for `agent-schedules-follow-up` (the spec allows
    `qwen3:30b` after two failed tries at step 3); `curl -s
    127.0.0.1:11434/api/tags` re-checked first;
  - run logs committed at `tests/behavior/<slug>/runs/<ts>.md`, evidence
    only under `/tmp/behavior-tests/…`; each spec's `Last Run` updated.
- **The gate** (on one commit, after the behavior runs, nothing else on
  the host — check `uptime` below about 1.0 and `ps` for other test
  processes):
  1. `THE_ONE_TEST_NETNS=1 make test-unit` (15 skipped expected);
  2. `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python
     TEST_TIMEOUT=3600 bash scripts/run-tests.sh --parallel 3`.
  A flake is re-run in isolation (the triage rule); a known flake that
  passes alone is recorded. `test_chat_history_purge.py::test_purge_loop_catch_up_sweeps_due_db`
  failed once under load in leg 4b: if it fails on a quiet host too, it is
  a defect to fix or squawk, not a flake.
- **Lane budgets** (CLAUDE.md "Quiet-host rule"): from the gate's
  `PARALLEL_RESULT` run only, measured plus 25%, rounded up to 30 s;
  re-budget only lanes that moved more than 15% from their table reading,
  plus `routing` and `agents` (DD9: three flights at 90%+). For those two,
  a split is preferred if a coherent file group exists (a Developer edits
  `scripts/run-tests.sh` lane globs and `tests/test_run_tests_lanes.py`);
  otherwise a re-budget. Any budget change goes into the
  `scripts/run-tests.sh` table and the CLAUDE.md lane table and history
  paragraph; a split also updates the lane list in CLAUDE.md. A lane change
  after the gate means a second gate run of the affected lanes is not
  needed for budgets (the change is file movement only), but
  `tests/test_run_tests_lanes.py` must pass.

## Inputs

- Flight spec DD9, DD13; both specs and their prior run logs
  (`tests/behavior/agent-schedules-follow-up/runs/2026-10-29-10-44-39.md`,
  `tests/behavior/routine-connector-delivery/runs/2026-10-29-03-31-37.md`);
  CLAUDE.md "Behavior-test credential convention" and its SAFETY RULE;
  `scripts/run-tests.sh`, CLAUDE.md's lane table.

## Outputs

- Re-authored specs, two committed run logs, updated `Last Run` lines.
- The gate's `PARALLEL_RESULT` line, per-lane times and unit counts in the
  flight log.
- Lane budget changes (and a split, if chosen) in `scripts/run-tests.sh`
  and CLAUDE.md.

## Acceptance Criteria

- [ ] AC1. `agent-schedules-follow-up` passes every checkpoint live (or a
      recorded failure is accepted by the operator as a known issue).
- [ ] AC2. `routine-connector-delivery` passes every checkpoint live,
      using the legacy request shapes.
- [ ] AC3. Neither instance touched port 8484, 8485 or the default data
      directory (read, not guessed); each ran from the scratch cwd and was
      stopped by its PID.
- [ ] AC4. The unit tier and a quiet-host `--parallel 3` run pass on one
      commit; the flight log records the commit, start load, the
      `PARALLEL_RESULT` line and per-lane times.
- [ ] AC5. `routing` and `agents` each sit at or below about 80% of their
      budget after this leg (split or re-budget), and every lane that moved
      more than 15% is re-budgeted; `tests/test_run_tests_lanes.py` passes.
- [ ] AC6. Run logs committed; no evidence under the repo.

## Verification Steps

- AC1-AC3, AC6: the run logs, `/proc` reads, `git status`.
- AC4-AC5: the gate output and the budget table diff.

## Edge Cases

- A behavior checkpoint fails on a real defect: fix it through a Developer
  in a new commit, re-run the gate's affected lanes and the spec.
- The gate fails on a lane the flight did not touch: triage per the rule;
  a reproducible failure in untouched code is a squawk, not a flight fix.

## Files Affected

- `tests/behavior/agent-schedules-follow-up.md`,
  `tests/behavior/routine-connector-delivery.md`, their new run logs
- `scripts/run-tests.sh`, `tests/test_run_tests_lanes.py` (if split),
  CLAUDE.md, the flight log

## Citation Audit

Checked at `54d87b8a` plus the Batch B tree:
- `agent-schedules-follow-up.md` steps 3 and 5 name `kind` `once`/`daily` —
  verified; `routine-connector-delivery.md` steps 3 and 6 send legacy
  shapes, step 6 polls 150 s — verified.
- `scripts/run-tests.sh` budget table and CLAUDE.md lane table (`routing`
  600/569, `agents` 540/500) — verified.
