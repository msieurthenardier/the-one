# Squawk 0191: studio's Library section lists duplicate LIBRARY_GROUPS by hand

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-12
**Completed**: 2026-10-23

## Report
`studio.js` keeps two hand-maintained lists of Library sections that duplicate `LIBRARY_GROUPS`: `hydrateState`'s root/bare-section list and `isLibrarySection`. A fifth Library group would need both edited, and missing one silently misroutes. Derive both from `LIBRARY_GROUPS`, or pin them to it with a static test.

## Evidence
- `the_one/interfaces/web/static/js/areas/studio.js` ~l.187 (`hydrateState` section list) and ~l.628 (`isLibrarySection`); `LIBRARY_GROUPS` (the source of truth).
- Sortie 02 debrief (Architect, Q4).

## Corrective Action
`LIBRARY_GROUPS` is hoisted to `library-pane.js`'s IIFE scope and exposed as `App.studio.libraryGroups()`. `isLibrarySection` and `studio-route.js`'s bare-section list now derive from it (read at call time, since `studio-route.js` loads first). `tests/test_library_groups_static.py` pins that neither site hand-lists a section.

## Verification
Static test passes and fails when a literal section is re-added (tried once, reverted); library, mcp, routing, shared lanes and `make test-unit` green (flight 03 leg 08).

## Sign-Off
**Reviewer**: Sonnet, the Mission 31 Flight 3 flight review (code and accessibility reviewers, then a scoped re-review of the fix pass)
**Verdict**: confirmed
**Commit**: `flight/3: Knowledge and connectors on the library (Mission 31)` on branch `flight/03-knowledge-and-connectors-on-the-library`
