# Squawk 0060: Benchmark tests assert only the `| OK |` cell

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-15
**Completed**: —

## Report

`tests/test_bench_vector_store.py`'s end-to-end tests check that a row exists and ends in `| OK |`, never that the numeric cells are well-formed and in range (non-negative latencies, p50 ≤ p95 ≤ max, recall in [0, 1], bytes > 0, `peak_rss_MB` numeric). A regression that prints `nan` or swaps two columns still passes. Add a row parser and range assertions to the existing tests; no new fixtures.

Logged from the Mission 24 Flight 2 debrief (2026-09-15).

## Evidence

- `tests/test_bench_vector_store.py:173` — `assert "| OK |" in captured.out or " OK |" in captured.out`; `:211` — `endswith("| OK |")`.
- Flight 2 flight log, "flight-end review, cycle 1": squawk candidate.

## Corrective Action
*(written at completion)*

## Verification
The tightened tests pass on the tree; a deliberately corrupted row (e.g. `p95` set to `nan`) fails them; `make test-unit` green.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
