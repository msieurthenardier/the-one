# Squawk 0233: the cache-busting test pins the exact script count, so every module split edits a magic number

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-22
**Completed**: —

## Report
`tests/test_index_asset_cache_busting.py` asserts `len(refs) == 93` (about `:99`). Every split that adds a module to `index.html` must bump the number: it was bumped again and again in Mission 31 Flight 2 alone (83, 86, 87, 91, 93), and Flight 3 will split more. The pin adds no protection that an existence and order check would not give. Recommended in the Mission 31 Flight 2 debrief.

## Evidence
- `tests/test_index_asset_cache_busting.py:99` — `assert len(refs) == 93`.

## Corrective Action
*(written at completion)*

## Verification
- The count pin is replaced by checks that every `/static` reference in `index.html` exists on disk and carries the version query, and that the dependency order the app relies on holds: `ui/` before areas, `settings-pages.js` before `router.js`, as already pinned elsewhere. A module added or split needs no test edit.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
