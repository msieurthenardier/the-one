# Leg: closing-quiet-gate

**Status**: completed
**Flight**: [Unit-tier runtime III](../flight.md)

## Objective
Take one quiet-host `make gate` on the flight's final code, then re-budget the browser lanes and restate the gate targets from it.

## Context
- Flight criteria T1 (unit under 400 s) and T2 (every lane budget from a measured quiet reading).
- **Leg 2's AC6 is deferred here.** Its stability runs were loaded at 7-23 by another project; clean readings were 180-212 s.
- **The quiet-host rule** (CLAUDE.md, squawk 0259): a budget reading counts only from a `--parallel 3` run that starts with a 1-minute load below about 1.0 and no other test process on the host.
- **The re-budget rule** (`the_one/agents.md`, "Budget history", restated at M36 F4 L8 and F5):
  - Compare each lane's wall time against its last recorded quiet reading (the "measured" figure in its `scripts/run-tests.sh` comment), or against its budget where no reading exists.
  - If it moved more than 15%, or is over budget, the new budget is wall × 1.25, rounded up to 30 s.
- **Six lanes have no measurement note:** `knowledge`, `mcp-connection`, `settings-tools`, `providers`, `contracts-widget` and `chats-widgets`. The last two are still provisional.

## Inputs
- The flight branch at `a5dcdc58` (Legs 1-2 committed).
- The Flight Director starts this leg only after the host has been quiet: a 1-minute load below 1.0 on consecutive checks.

## Outputs
- A gate reading in the flight log.
- Updated budgets and "measured" comments in `scripts/run-tests.sh`.
- A new "Budget history" entry and restated targets in `the_one/agents.md`.

## Acceptance Criteria
- [ ] **AC1, quiet start.** Record `uptime` and `ps -ef | grep -E "pytest|run-tests"` immediately before the run. The 1-minute load must be below about 1.0, with no other test process.
  - If the load rises above about 2 during the run, the run is reference only. Record it, then wait and re-run once.
  - If a second quiet window does not come, report that and do not re-budget.
- [ ] **AC2, the gate.**
  - Command: `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python make gate`. The unit tier runs at N=4 from Leg 2, then the browser tier runs at `--parallel 3`.
  - Run it in the background and wait for its completion notification.
  - Record in the flight log: the unit summary line and time, `PARALLEL_RESULT`, every lane's wall time and budget, the total gate time, and the load at start and end.
- [ ] **AC3, unit target.** The unit tier is under 400 s on this run. If it is not, record the reading honestly. The flight is not landed on a false claim.
- [ ] **AC4, re-budget.** Apply the rule above to every lane, including the six with no note. Each changed budget and its "measured" comment are updated in `scripts/run-tests.sh`. `tests/test_run_tests_lanes.py` passes.
- [ ] **AC5, targets restated.** In `the_one/agents.md`:
  - a "Budget history" entry for this gate, in the existing format;
  - the full-gate target restated as measured plus 25%;
  - the unit tier's reading noted against its 500 s standing target, in the "Host policy" bullet.

  CLAUDE.md is not changed, unless it states a number that is now wrong.
- [ ] **AC6, failures.** A gate failure is triaged per the crew rules: re-run in isolation; accept a known squawk flake that passes in isolation, with the result recorded; treat anything else as a regression to fix before landing.

## Verification Steps
- **AC1, AC2, AC3:** read the flight log's "Leg 3" entry.
- **AC4:** check the `scripts/run-tests.sh` diff and the lane-test result.
- **AC5:** check the `the_one/agents.md` diff.

## Implementation Guidance
1. Check that the host is quiet (AC1). If it is not, report back without running anything. The Flight Director waits for quiet before spawning this leg, but conditions can change.
2. Run the gate (AC2). Read `scripts/run-tests.sh --help` for where `PARALLEL_RESULT` and the per-lane walls are printed.
3. Apply the re-budget rule (AC4). Write each lane's comparison in the flight log as a small table: lane, wall, last reading, change, old budget, new budget.
4. Update the docs (AC5).
5. Run `tests/test_run_tests_lanes.py`, then `ruff check` on `scripts/` if a Python file changed.
6. Write the "Leg 3" entry in the flight log. Then `[LAND:leg]`.

## Edge Cases
- **The host is loaded partway through:** record it, and do not re-budget from a loaded run.
- **A lane is far over budget** (more than 1.3 × its budget) on a quiet run: re-budget it per the rule, and note in the log that it is a split candidate.

## Files Affected
- `scripts/run-tests.sh`: the budget table and its "measured" comments.
- `the_one/agents.md`: "Budget history" and "Host policy".
- The flight log.

## Citation Audit
- `the_one/agents.md` "Budget history" and "Host policy": the bullets near line 3058-3060 (the M36 F5 entry and the rule). Verified 2026-11-24, and edited by Leg 2 (the Host policy sentence), so re-check them at the leg.
- `scripts/run-tests.sh`: the budget table (`[mcp]=450 # M36 F4 L8 ...`, line 79). Verified.
- `Makefile` `gate`: unit, then browser, never concurrent. Leg 2 added `-n $(UNIT_WORKERS)` to `test-unit`. Verified in the Leg 2 review.
