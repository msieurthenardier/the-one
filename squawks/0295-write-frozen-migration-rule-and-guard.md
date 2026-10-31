# Squawk 0295: Write the frozen-migration rule and guard it with a test

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-30
**Completed**: —

## Report
The Mission 33 debrief asks for a convention that a migration never imports live domain code. It is not in `the_one/agents.md` Project Conventions (only the narrower `frozen-migration-converter-with-guarded-failure-row` exists), and nothing enforces it. Today `schema.py` reaches the live `time_zones` module from the v48/v49 converters, so a later change to the `time_zone` setting format could change what a past migration does on a fresh install. From maintenance report 2026-10-30, finding #8.

## Evidence
- `the_one/db/schema.py:222`, `:229`, `:391`: `from the_one import time_zones` (function-local, used by `load_effective_zone`/`utcnow` in the routine converters).
- `the_one/db/schema.py:14`: `from the_one.db._provider_types import PROVIDER_TYPES` (frozen data, acceptable).
- `the_one/db/migration.py:7`: `from the_one.agent.store import FilesystemConfigStore` (legacy import path).

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

`agents.md` Project Conventions names the rule. A unit test AST-scans `the_one/db/schema.py` for `the_one.` imports and fails on any outside an explicit allow-list (`_provider_types`, and `time_zones` only if it stays, with the reason recorded beside the entry).

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
