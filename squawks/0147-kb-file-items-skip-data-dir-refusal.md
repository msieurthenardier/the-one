# Squawk 0147: Knowledge-base file items skip the data-directory refusal

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-08
**Completed**: 2026-10-08

## Report
Registering a `folder` item canonicalizes the path and refuses one that equals, contains or lies inside the application data directory (M24 F4, DD-6). A `file` item gets neither check: any `path_or_url` is stored, and `GET .../items/{id}/source` reads it back through the extractor. Only the credential-holding operator can do this, but it makes DD-6 a folder-only rule in practice. Found by routine maintenance 2026-10-08 (finding #22).

## Evidence
- `the_one/interfaces/web/api.py` item create (~1668-1707): the data-dir check runs only when `item.type == "folder"`
- Source read-back ~1978-2030

## Corrective Action
`create_kb_item` now runs `canonicalize` + `is_within(canonical, settings.data_dir)` (the folder branch's helpers) for `type: "file"` items: a file equal to or inside the data directory is refused 422 ("file lies inside the application data directory ..."), and the canonical path is stored, mirroring folders. Folder-only checks (existence, filesystem root, overlap) stay folder-only; walk-inserted children are untouched. CLAUDE.md's Knowledge bases sentence now says the refusal covers file items.

## Verification
`tests/test_db_api.py::TestKnowledgeBaseFileItemDataDirRefusal` (inside -> 422, via `..` -> 422, outside -> 201 with canonical path). Falsified: disabling the check fails the two 422 tests; restored. `tests/test_db_api.py` 188 passed; ruff check and format clean.

## Sign-Off

**Reviewer**: independent batch Reviewer (Sonnet tier: the batch touches the credential-gated test seams and secret echo in 422 bodies), plus a Haiku re-review of the one fix-loop change (`tests/test_store_static.py`, a static guard that pinned the pre-0145 fetch literal); unit suite 5647 passed, 1 failed before the guard fix (the guard, re-run green after), 16 skipped (10 Windows-only, 2 root-only under `THE_ONE_TEST_NETNS=1`, 4 `requires_bwrap` sandbox skips included by the run's marker set); agents lane 154 passed, 2 skipped; shared lane 465 passed; ruff clean
**Verdict**: confirmed (`[HANDOFF:confirmed]`)
**Commit**: `squawk: turnaround 2026-10-08` on branch `squawk/turnaround-2026-10-08`
