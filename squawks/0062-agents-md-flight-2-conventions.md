# Squawk 0062: Name four Flight 2 conventions in `the_one/agents.md`

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-15
**Completed**: 2026-09-15

## Report

Four patterns the flight instantiated live only in code comments and the flight log. Add them to `the_one/agents.md` "Project Conventions": *empty-transaction re-entry guard* (an in-memory-until-flush store opens and closes an empty `write_transaction` so DD-13's no-nesting rule holds uniformly — cite `UsearchStore.upsert`); *atomic sidecar save* (write `<path>.tmp` in the same directory, `os.replace`, then the registry row; a crash between the two reads as stale and is recoverable, never silent — cite `_save_atomically`); *migration tests replay the real chain* (fixtures must not stamp `schema_version` past tables they never created; until they comply, a block touching an always-present table carries a presence guard — cite v40 `kb_items` and v41 `app_metadata`); *store-owned-until-decided* (a schema element whose owner is an open planning question is created by the owner until the decision, then moved into a migration — cite `kb_vector_index`). Also add one sentence to "Knowledge storage": synthetic-corpus recall is index recall on a clustered generator; DD-4's 0.95 floor applies to real-corpus recall only.

Logged from the Mission 24 Flight 2 debrief (2026-09-15).

## Evidence

- `the_one/agents.md:82` `## Project Conventions`; the Knowledge storage section (~line 1128).
- `the_one/vectors/usearch_store.py` module docstring and `_save_atomically` docstring; `the_one/db/schema.py` v40/v41 guard comments.
- Flight 2 debrief, Recommendation 3.

## Corrective Action

Added four new entries to `the_one/agents.md`'s "Project Conventions" → "Project-wide" section, inserted immediately after `db-writes-hold-the-write-lock` (before the "Mission-specific (M16)" subheading), matching the section's existing heading/bold-name + Rationale/Citation prose shape:

- **`empty-transaction re-entry guard`** — cites `the_one/vectors/usearch_store.py::UsearchStore.upsert` (line 255) / `.delete` (line 285), each opening an empty `async with write_transaction(self.conn): pass` before its in-memory-only mutation. Notes the cost (app-wide write lock + a real empty commit per call) and that Flight 3's bulk-indexing leg is expected to measure it under volume, per the flight debrief's Recommendation 1/technical note.
- **`atomic sidecar save`** — cites `UsearchStore._save_atomically` (write to a same-directory `.tmp` path via `_tmp_path_for`, then `os.replace`) and `_ensure_loaded` (the read-side count/dtype/dim mismatch checks that report a crash-between-steps as `VectorStoreStaleError` rather than silently accepting a stale sidecar), with `rebuild_from` as the recovery path.
- **`migration tests replay the real chain`** — cites the v40 `kb_items_present` guard (`the_one/db/schema.py` ~2447-2451) and the v41 `app_metadata_exists` guard (~schema.py:2603-2611), plus `tests/test_db_migration.py::TestSchemaV41::test_v41_app_metadata_absent_guard` (added by squawk 0058 in this tree), which pins the v41 guard directly against a fixture stamped 1..31 with no `app_metadata` table.
- **`store-owned-until-decided`** — cites `kb_vector_index`: created inside `UsearchStore.open()` (`CREATE TABLE IF NOT EXISTS`) through Legs 4-5 while the vector-store backend choice was open (DD-3), then moved byte-for-byte into the v41 migration block in `the_one/db/schema.py` once the operator chose `usearch` at the DD-9 checkpoint; `open()` issues no DDL today.

Also added one sentence to the "Knowledge storage" section (after the flush/benchmark bullet, before the "store acquires the write lock" bullet, ~line 1157-1158): synthetic-corpus recall@10 (0.04–0.43 across the benchmark's 20k–3M runs) is index recall against a pathologically clustered generator, a known HNSW failure mode, not a retrieval-quality regression — DD-4's 0.95 floor applies only to the real-corpus recall column, where f16 measured 0.98. (Verified the actual flight-log numbers — 0.43 at 20k, 0.07 at 1M, 0.04 at 3M — rather than reusing the "0.04–0.43 at 1M–3M" figure as literally phrased in the squawk report, which doesn't match the recorded per-N values; the sentence instead spans the full 20k–3M range the benchmark covers.)

No code files touched; only `the_one/agents.md` and this squawk file.

## Verification
Doc-only; `tests/test_token_definitions.py`-style checks unaffected; a reviewer confirms each convention cites a real symbol.

Verified:
- Every cited path/symbol resolves in the current tree (`grep -n` against `the_one/vectors/usearch_store.py`, `the_one/db/schema.py`, `tests/test_db_migration.py`): `UsearchStore.upsert`/`.delete`/`._save_atomically`/`._tmp_path_for`/`._ensure_loaded`, the v40 `kb_items_present` guard, the v41 `app_metadata_exists` guard, `kb_vector_index`'s `CREATE TABLE IF NOT EXISTS` in both `open()`'s docstring/comment and the v41 migration block, and `TestSchemaV41::test_v41_app_metadata_absent_guard`.
- CLAUDE.md's "Named project-wide patterns" sentence is explicitly illustrative (ends in "…") and does not claim completeness — left unchanged per the task's scope gate.
- No summary/index list of convention names exists elsewhere in `agents.md`'s Project Conventions section to keep in sync — the section is a flat sequence of `### `name`` entries.
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_token_definitions.py -x --timeout 60 -q` → 1 passed.
- `ruff check the_one/ tests/ scripts/` → All checks passed (tree unchanged Python-wise; `agents.md` itself isn't linted).
- `git diff --stat the_one/agents.md` → 28 insertions, 0 deletions (purely additive); `git status --short` confirms only `the_one/agents.md` and this squawk file changed beyond the pre-existing uncommitted squawks 0054-0061 tree.

## Sign-Off
*(written at completion)*
**Reviewer**: Sonnet, batch review of squawk/turnaround-2026-09-15
**Verdict**: confirmed
**Commit**: _(recorded in the follow-up commit)_
