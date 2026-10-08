# Squawk 0148: A walk that finishes after its folder is deleted leaves an orphan kv row

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-08
**Completed**: —

## Report
After a folder walk, the indexer writes the walk's skip counters to `app_metadata` unconditionally. The delete paths clean that key once, at delete time. If a folder is deleted while its walk is finishing, the write lands after the cleanup and the row is orphaned for good (`app_metadata` sits outside the `kb_items` FK cascade). Separately, the knowledge-base delete cleanup wraps its whole per-folder loop in one `try`, so one failed delete skips the rest. Found by routine maintenance 2026-10-08 (finding #24).

## Evidence
- `the_one/knowledge/manager.py` ~452-458 — unconditional `meta_repo.set(walk_skip_counters_key(folder.id), …)`
- `the_one/interfaces/web/api.py` ~1627-1632 (KB delete, single try around the loop) and ~1830-1836 (item delete)

## Corrective Action
*(written at completion)* Expected: re-check that the folder item still exists before the write (skip if gone), and give the KB-delete cleanup a per-folder `try`.

## Verification
A unit test that deletes the folder item between the walk and the counter write and asserts no kv row remains.

## Sign-Off
*(written at completion)*
