# Squawk 0060: Benchmark tests assert only the `| OK |` cell

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-15
**Completed**: 2026-09-15

## Report

`tests/test_bench_vector_store.py`'s end-to-end tests check that a row exists and ends in `| OK |`, never that the numeric cells are well-formed and in range (non-negative latencies, p50 ≤ p95 ≤ max, recall in [0, 1], bytes > 0, `peak_rss_MB` numeric). A regression that prints `nan` or swaps two columns still passes. Add a row parser and range assertions to the existing tests; no new fixtures.

Logged from the Mission 24 Flight 2 debrief (2026-09-15).

## Evidence

- `tests/test_bench_vector_store.py:173` — `assert "| OK |" in captured.out or " OK |" in captured.out`; `:211` — `endswith("| OK |")`.
- Flight 2 flight log, "flight-end review, cycle 1": squawk candidate.

## Corrective Action

Added a row parser and range-checking helper to `tests/test_bench_vector_store.py`
(no changes to `scripts/bench_vector_store.py`):

- `_parse_bench_row(line)` splits a rendered markdown row on `|` and maps
  cells to column names from the script's own `bench_vector_store._TABLE_HEADERS`
  (imported, not duplicated — a column reorder in the script changes the
  dict keys the test asserts against, rather than silently misaligning).
- `_assert_non_negative_float_cell(row, key)` — a cell is either `"-"`
  (legitimately not applicable) or a finite, non-negative float.
- `_assert_row_sane(row)` asserts: `status == "OK"`; `build_s`,
  `p50_ms`/`p95_ms`/`max_ms`, `save_ms`, `restore_ms` are present
  (not `"-"` — all render unconditionally for an OK row) and non-negative;
  `p50 <= p95 <= max`; `recall@k` is a non-NaN float in `[0, 1]`;
  `disk_MB` is a positive float; `peak_rss_MB` is a positive float (never
  `"-"` on this host — `resource.getrusage` always succeeds on Linux).

Applied `_assert_row_sane` (via `_parse_bench_row`) in the three existing
end-to-end tests instead of adding new fixtures:

- `test_end_to_end_synthetic_usearch_f16` (single-cell synthetic run)
- `test_child_mode_emits_exactly_one_row_on_stdout` (`--child` single-row test)
- `test_multi_cell_run_dispatches_one_subprocess_per_cell_with_two_rows`
  (real two-cell run) — this also replaced the test's own hand-rolled
  `_peak_rss` column extractor with the shared parser.

Added three small unit tests of the helper itself, using hand-written row
strings (no benchmark run needed):

- `test_assert_row_sane_accepts_a_well_formed_row` — baseline: a good row
  does not raise.
- `test_assert_row_sane_rejects_nan_cell` — `p95_ms` corrupted to `nan`
  raises `AssertionError`.
- `test_assert_row_sane_rejects_p50_greater_than_p95` — `p50_ms`/`p95_ms`
  swapped so `p50 > p95` raises `AssertionError`.

## Verification

- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_bench_vector_store.py -x --timeout 120 -q`
  → `16 passed`.
- The two new negative unit tests (`test_assert_row_sane_rejects_nan_cell`,
  `test_assert_row_sane_rejects_p50_greater_than_p95`) prove the tightening
  has teeth: a hand-written row with `p95` set to `nan`, and one with
  `p50`/`p95` swapped, both fail `_assert_row_sane` as expected.
- `ruff check the_one/ tests/ scripts/` → all checks passed.
- `ruff format the_one/ tests/ scripts/` → no changes (already formatted).
- Only `tests/test_bench_vector_store.py` was touched — `scripts/bench_vector_store.py`
  is unchanged (confirmed via `git status`).

## Sign-Off
*(written at completion)*
**Reviewer**: Sonnet, batch review of squawk/turnaround-2026-09-15
**Verdict**: confirmed
**Commit**: ba46d62
