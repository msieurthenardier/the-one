# Squawk 0159: agents.md lacks the test template-DB rule and the parallel runner contract

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-09
**Completed**: —

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
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
