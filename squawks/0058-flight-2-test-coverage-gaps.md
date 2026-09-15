# Squawk 0058: Fill the Flight 2 test gaps: v41 migration, usearch staleness, cosine value, `delete_kb` unlink

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-15
**Completed**: —

## Report

Four coverage gaps named at the Flight 2 debrief, all on code the flight added: (a) `TestSchemaV41` lacks the double-`ensure_schema` idempotency test and the full `>= 7` rewind test its v40 sibling has, and its `app_metadata`-absent guard is proven only incidentally by a `TestSchemaV32` fixture; (b) `UsearchStore._ensure_loaded`'s registry dtype/dim-mismatch branch (raises `VectorStoreStaleError`) has no test; (c) `query()`'s distances are asserted non-decreasing but never against an independently computed cosine distance; (d) `delete_kb` unlinks with `if path.exists(): path.unlink()` where its sibling uses `unlink(missing_ok=True)` — make them consistent. One servicing item: tests only plus the one-token unlink change.

Logged from the Mission 24 Flight 2 debrief (2026-09-15).

## Evidence

- `tests/test_db_migration.py::TestSchemaV41` vs `TestSchemaV40` (idempotent double-run, `>= 7` rewind-rerun present only in V40).
- `the_one/db/schema.py:2603-2611` — v41 `app_metadata` guard.
- `the_one/vectors/usearch_store.py` `_ensure_loaded`, the `row["dtype"] != self.dtype or row["dim"] != self.dim` branch; `tests/test_vector_store.py::TestUsearchStaleness` covers count and missing-file only.
- `tests/test_vector_store.py::TestSharedProtocolSuite::test_query_k10_returns_10_nondecreasing_distances`.
- `the_one/vectors/usearch_store.py:304` — `path.unlink()`.

## Corrective Action
*(written at completion)*

## Verification
The new tests pass and each fails when its guard/branch is removed (state this in the corrective action); `make test-unit` green.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
