# Squawk 0191: studio's Library section lists duplicate LIBRARY_GROUPS by hand

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-12
**Completed**: —

## Report
`studio.js` keeps two hand-maintained lists of Library sections that duplicate `LIBRARY_GROUPS`: `hydrateState`'s root/bare-section list and `isLibrarySection`. A fifth Library group would need both edited, and missing one silently misroutes. Derive both from `LIBRARY_GROUPS`, or pin them to it with a static test.

## Evidence
- `the_one/interfaces/web/static/js/areas/studio.js` ~l.187 (`hydrateState` section list) and ~l.628 (`isLibrarySection`); `LIBRARY_GROUPS` (the source of truth).
- Sortie 02 debrief (Architect, Q4).

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
