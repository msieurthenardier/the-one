# Squawk 0148: A walk that finishes after its folder is deleted leaves an orphan kv row

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-08
**Completed**: 2026-10-08

## Report
After a folder walk, the indexer writes the walk's skip counters to `app_metadata` unconditionally. The delete paths clean that key once, at delete time. If a folder is deleted while its walk is finishing, the write lands after the cleanup and the row is orphaned for good (`app_metadata` sits outside the `kb_items` FK cascade). Separately, the knowledge-base delete cleanup wraps its whole per-folder loop in one `try`, so one failed delete skips the rest. Found by routine maintenance 2026-10-08 (finding #24).

## Evidence
- `the_one/knowledge/manager.py` ~452-458 — unconditional `meta_repo.set(walk_skip_counters_key(folder.id), …)`
- `the_one/interfaces/web/api.py` ~1627-1632 (KB delete, single try around the loop) and ~1830-1836 (item delete)

## Corrective Action
- `the_one/knowledge/manager.py::_walk_one_folder`: before the walk-skip-counter `meta_repo.set`, re-reads the folder item (`item_repo.get`, which raises `KeyError` when gone) and skips the write if it has been deleted. Residual window: the check and the write are two awaits on the walk's connection, and a delete committed from another connection (the API's) between them can still orphan one row; closing that would need a cross-table transaction or a new repository method, out of squawk scope. The check closes the realistic case, a delete landing during the walk and reconcile.
- `the_one/interfaces/web/api.py` (knowledge-base delete): the cleanup loop now has a per-folder `try` (same `logger.exception` level), so one failed key delete no longer skips the rest. The single-item delete cleanup is one key, not a loop, so it is unchanged.

## Verification
- New `tests/test_kb_manager.py::TestPass::test_walk_skips_counter_write_when_folder_deleted_mid_walk` (deletes the folder item right after the `indexed` transition, then asserts no kv row) and `tests/test_db_api.py::...::test_delete_knowledge_base_cleanup_continues_past_a_failing_key` (first key delete raises; the other two are removed). Each was falsified (guard removed / loop under one `try`), failed, and was restored.
- `tests/test_kb_manager.py` + `tests/test_db_api.py`: 217 passed. `ruff check` and `ruff format --check` clean.

## Sign-Off

**Reviewer**: independent batch Reviewer (Sonnet tier: the batch touches the credential-gated test seams and secret echo in 422 bodies), plus a Haiku re-review of the one fix-loop change (`tests/test_store_static.py`, a static guard that pinned the pre-0145 fetch literal); unit suite 5647 passed, 1 failed before the guard fix (the guard, re-run green after), 16 skipped (10 Windows-only, 2 root-only under `THE_ONE_TEST_NETNS=1`, 4 `requires_bwrap` sandbox skips included by the run's marker set); agents lane 154 passed, 2 skipped; shared lane 465 passed; ruff clean
**Verdict**: confirmed (`[HANDOFF:confirmed]`)
**Commit**: `squawk: turnaround 2026-10-08` on branch `squawk/turnaround-2026-10-08`
