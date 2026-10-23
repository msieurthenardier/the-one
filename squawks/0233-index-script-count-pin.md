# Squawk 0233: the cache-busting test pins the exact script count, so every module split edits a magic number

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-22
**Completed**: 2026-10-23

## Report
`tests/test_index_asset_cache_busting.py` asserts `len(refs) == 93` (about `:99`). Every split that adds a module to `index.html` must bump the number: it was bumped again and again in Mission 31 Flight 2 alone (83, 86, 87, 91, 93), and Flight 3 will split more. The pin adds no protection that an existence and order check would not give. Recommended in the Mission 31 Flight 2 debrief.

## Evidence
- `tests/test_index_asset_cache_busting.py:99` — `assert len(refs) == 93`.

## Corrective Action
`tests/test_index_asset_cache_busting.py` no longer pins `len(refs)`. A shared `check_static_refs(body)` asserts: every `/static/*.js|css` ref exists on disk under `static/`; each carries exactly one `?v={__version__}`; no ref is duplicated; and the relative load order of the `.js` refs (`js/ui/core.js` before every other `js/ui/*.js`; every `js/ui/*.js` before any `js/areas/**`; every `js/areas/studio/*.js` before `js/areas/studio.js`, and `js/areas/chat/*.js` before `js/areas/chat.js`). The history comment collapsed to a pointer to the git log. Three negative tests mutate the served body (missing script, an area script above `ui/core.js`, a duplicate ref) and prove the check fails. Landed in Mission 31 Flight 3 Leg 01.

## Verification
- Done: `tests/test_index_asset_cache_busting.py` (7 tests) passes; the three negative tests fail the check as intended. A module added or split needs no test edit.
- The count pin is replaced by checks that every `/static` reference in `index.html` exists on disk and carries the version query, and that the dependency order the app relies on holds: `ui/` before areas, `settings-pages.js` before `router.js`, as already pinned elsewhere. A module added or split needs no test edit.

## Sign-Off
**Reviewer**: Sonnet, the Mission 31 Flight 3 flight review (code and accessibility reviewers, then a scoped re-review of the fix pass)
**Verdict**: confirmed
**Commit**: `flight/3: Knowledge and connectors on the library (Mission 31)` on branch `flight/03-knowledge-and-connectors-on-the-library`
