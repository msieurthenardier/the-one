# Squawk 0159: agents.md lacks the test template-DB rule and the parallel runner contract

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-09
**Completed**: 2026-10-09

## Report
Mission 26 F01 introduced two conventions that live only in code, CLAUDE.md's Testing section, and the flight log:
1. New tests build their database through `tests/_schema_template.py` (`connect_template_db` / `copy_template` / `connect_template_memory`), and call `ensure_schema` or `init_db` directly only in allow-listed migration tests.
2. `scripts/run-tests.sh --parallel`'s lifecycle contract:
   - TERM-first cleanup, `.pgids` files, the parent-death guard and the USR1 timeout;
   - the exit-code rules and the `PARALLEL_RESULT` line;
   - how lane budgets are re-measured and updated.

`the_one/agents.md` (the canonical deep reference, "Project Conventions") has neither, so the next leg author has to rediscover them.

## Evidence
- `tests/test_schema_template.py` `ALLOWED_DIRECT_CALLERS`; `tests/_schema_template.py` module docstring.
- `scripts/run-tests.sh` `--help` and the parallel block; the leg 4 spec (`missions/26-maintenance/flights/01-test-suite-runtime/legs/04-local-lane-parallelism.md`, AC2/AC3).
- Debrief recommendation 4 (`missions/26-maintenance/flights/01-test-suite-runtime/flight-debrief.md`).

## Corrective Action
Added two sections to `the_one/agents.md` (under "Testing patterns", after "Browser test isolation"): "Test databases come from the session template" and "Parallel test runner contract (`scripts/run-tests.sh --parallel N`)". Added a one-paragraph pointer to both from CLAUDE.md's Testing section (it had none). Documentation only; no code changed.

## Verification
Every claim was checked against the code, not the flight artifacts:
- `tests/_schema_template.py`: the four helpers and their behaviour (once-per-process build, `journal_mode=DELETE`, `copy_template` refuses an existing dest and chmods 0o600, `connect_template_memory` uses the backup API, never-open-the-template note).
- `tests/test_schema_template.py`: `ALLOWED_DIRECT_CALLERS`, the `ast` guard (`ensure_schema`/`init_db` calls under `tests/`), the stale-entry test, and `test_template_matches_fresh_replay` (what it compares).
- `tests/browser/conftest.py::_spawn_app`: `seed_db=True` default, copy before `Popen`, `seed_db=False` for first-boot/migration tests.
- `scripts/run-tests.sh`: `--parallel`/`--lane` exclusivity, child invocation under `setsid`, log/xml/pgids files, `BUDGET` ordering, TERM-then-5 s-then-KILL cleanup, `.pgids` contents and removal, USR1 watchdog and 15 s escalation, `RUN_TESTS_PARENT_PID` guard and `.parent-died` marker, exit-code rules (137/143, missing/empty junit, first failing lane in schedule order), `PARALLEL_RESULT` format (including the aborted-run form), `TEST_TIMEOUT` defaults 1200/2400.
- `tests/test_run_tests_lanes.py`: the plan test pins shape (every lane once, numeric, descending), timeout defaults and exit-2 errors, not the budget values. The agents.md text says so (the brief said the test "pins" the budget; it does not pin values).
- Markdown only; ruff not applicable.

## Sign-Off

**Reviewer**: independent batch Reviewer (Sonnet tier: the batch touches the self-configuration credential-isolation tests and a CI install script). Spot-checked the documented claims against `tests/_schema_template.py`, `tests/test_schema_template.py`, `scripts/run-tests.sh` and `tests/browser/conftest.py::_spawn_app`. All match.
**Verdict**: confirmed (`[HANDOFF:confirmed]`)
**Commit**: `squawk: turnaround 2026-10-09` on branch `squawk/turnaround-2026-10-09`
