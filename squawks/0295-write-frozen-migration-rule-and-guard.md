# Squawk 0295: Write the frozen-migration rule and guard it with a test

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-30
**Completed**: 2026-11-01

## Report
The Mission 33 debrief asks for a convention that a migration never imports live domain code. It is not in `the_one/agents.md` Project Conventions (only the narrower `frozen-migration-converter-with-guarded-failure-row` exists), and nothing enforces it. Today `schema.py` reaches the live `time_zones` module from the v48/v49 converters, so a later change to the `time_zone` setting format could change what a past migration does on a fresh install. From maintenance report 2026-10-30, finding #8.

## Evidence
- `the_one/db/schema.py:222`, `:229`, `:391`: `from the_one import time_zones` (function-local, used by `load_effective_zone`/`utcnow` in the routine converters).
- `the_one/db/schema.py:14`: `from the_one.db._provider_types import PROVIDER_TYPES` (frozen data, acceptable).
- `the_one/db/migration.py:7`: `from the_one.agent.store import FilesystemConfigStore` (legacy import path).

## Corrective Action
Added the `frozen-migration-imports` convention to `the_one/agents.md` beside `frozen-migration-converter-with-guarded-failure-row`, and `tests/test_schema_frozen_imports.py`, which AST-scans `the_one/db/schema.py` (function-local imports included) and fails on any `the_one.*` import outside an `ALLOWED` table. Allowed: `the_one.db._provider_types` (frozen data) and `the_one.time_zones` (v48/v49 converters). `time_zones` stays: freezing it means copying the `time_zone` setting format and system-zone detection, a design call, so the reason is recorded in the table and the convention. `migration.py` is not scanned: it is the one-off file-store import and exists to call live code. No migration behaviour changed.

## Verification
*(planned)* `agents.md` Project Conventions names the rule. A unit test AST-scans `the_one/db/schema.py` for `the_one.` imports and fails on any outside an explicit allow-list (`_provider_types`, and `time_zones` only if it stays, with the reason recorded beside the entry).

Run: adding `from the_one.naming import check_name` to `schema.py` made the test fail; removed, it passes. `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_schema_frozen_imports.py tests/test_db_migration.py tests/test_schema.py tests/test_schema_template.py -x --timeout 60`: 177 passed. `ruff check` and `ruff format --check` on the new test: clean.

`agents.md` Project Conventions names the rule. A unit test AST-scans `the_one/db/schema.py` for `the_one.` imports and fails on any outside an explicit allow-list (`_provider_types`, and `time_zones` only if it stays, with the reason recorded beside the entry).

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet; the batch states security-model residual risks, 0298 and 0299), batch review of the 2026-11-01 squawk turnaround, scoped to the diff, `[HANDOFF:confirmed]`. Falsified: yes (a forbidden import added to `schema.py` failed the test, then was removed).
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-01` commit on `squawk/turnaround-2026-11-01`. Unit tier under `THE_ONE_TEST_NETNS=1`: 8560 passed, 23 skipped, 3 failed (the known `tests/test_desktop_host.py` baseline, unchanged from main).
