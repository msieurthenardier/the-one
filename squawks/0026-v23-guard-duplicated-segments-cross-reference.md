# Squawk 0026: Duplicated v23 guard segments lack cross-reference comments

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-08-31
**Completed**: 2026-09-01

## Report

The Mission 23 Flight 1 fix to v23's re-entry guard (needed once v38 retires `pending_approvals`
and the agent connector columns asymmetrically) near-duplicates the segment-2 (`pending_approvals`
row-rewrite re-check) and segment-4 (`agents` column-rename re-check) logic across the
`if post_v23_target_exists:` and historical `elif` branches of `ensure_schema`. Extracting a
shared helper was correctly avoided (minimizing edits to frozen migration logic), but the two
copies carry no pointer to each other — a future migration author could fix one and miss the
other. Add a one-line cross-reference comment at each copy.

## Evidence

- `the_one/db/schema.py:1064-1119` — the `if post_v23_target_exists:` branch (Flight 1 fix)
- `the_one/db/schema.py` v23 historical `elif` branch — the original copies
- Raised by the Flight 1 debrief (2026-08-31), Developer interview, Implementation Quality

## Corrective Action

Added a one-line cross-reference comment at each of the four duplicated-logic
sites in `ensure_schema` (`the_one/db/schema.py`), pointing each copy at its
counterpart so a future author touching one segment is prompted to check the
other:

- `if post_v23_target_exists:` branch, segment-2 (`pending_approvals`
  row-rewrite) — comment added just above the table-presence check, pointing
  at the `elif` branch's Segment 2 below.
- `if post_v23_target_exists:` branch, segment-4 (`agents` column rename) —
  comment added just above the `PRAGMA table_info(agents)` call, pointing at
  the `elif` branch's Segment 4 below.
- `elif pre_v23_source_exists:` branch, Segment 2 (`pending_approvals`
  row-rewrite) — comment added above the `if "pending_approvals" in
  v23_present:` guard, pointing back at the `if post_v23_target_exists:`
  branch above.
- `elif pre_v23_source_exists:` branch, Segment 4 (`agents` column rename) —
  comment added above the `if "agents" in v23_present:` guard, pointing back
  at the `if post_v23_target_exists:` branch above.

No behavior change — comments only. The frozen migration logic (DDL,
row-rewrite scripts, guard conditions) is untouched.

## Verification

- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_db_migration.py -x --timeout 60`
  — 84 passed.
- `ruff check the_one/db/schema.py` — all checks passed.
- `git diff -- the_one/db/schema.py` reviewed: all four hunks are added
  comment lines only; no code line was modified, added, or removed.

## Sign-Off
**Reviewer**: independent batch Reviewer (Sonnet), squawk/turnaround-2026-09-01
**Verdict**: confirmed
**Commit**: squawk/turnaround-2026-09-01 batch commit (PR follows)
