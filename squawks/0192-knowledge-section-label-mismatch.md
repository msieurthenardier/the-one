# Squawk 0192: router names the knowledge section "Knowledge" while the group is "Knowledge bases"

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-12
**Completed**: —

## Report
The router's Library labels announce and title the knowledge section as "Knowledge", while the Library list group, the start-page card and the breadcrumb say "Knowledge bases". This predates sortie 02. Confirm whether the short form is intended; if not, align the router label (and its announcer tests).

## Evidence
- `the_one/interfaces/web/static/js/router.js` ~l.446 (`LIBRARY_LABELS` knowledge entry).
- `the_one/interfaces/web/static/js/areas/studio.js` `LIBRARY_GROUPS` (`label: 'Knowledge bases'`).
- `tests/browser/test_router_announce.py` (pins the announced text).
- Sortie 02 debrief (Architect).

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
