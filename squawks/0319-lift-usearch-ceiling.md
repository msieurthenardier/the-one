# Squawk 0319: Lift the `usearch<2.26.5` ceiling once a release passes the recall test

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-03
**Completed**: —

## Report
Squawk 0241 capped `usearch` below 2.26.5. Versions 2.26.5 and 2.26.6 intermittently fail `tests/test_vector_store.py::TestSharedProtocolSuite::test_query_returns_self_first_for_every_vector[usearch-f16]`, in 4 to 5 runs out of 25. Version 2.26.4 fails 0 of 25. When a newer release ships, test it and lift the ceiling if it passes repeatedly.

## Evidence
- The usearch ceiling comment in `pyproject.toml`.
- `squawks/0241-unit-tests-fail-under-fresh-dependencies.md`.

## Corrective Action
*(written at completion)*

## Verification
- A release at least 14 days old passes that test 25 of 25 times in a scratch venv.
- The ceiling is removed, the lock is redone, and `make test-unit` passes.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
