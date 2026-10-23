# Squawk 0192: router names the knowledge section "Knowledge" while the group is "Knowledge bases"

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-12
**Completed**: 2026-10-23

## Report
The router's Library labels announce and title the knowledge section as "Knowledge", while the Library list group, the start-page card and the breadcrumb say "Knowledge bases". This predates sortie 02. Confirm whether the short form is intended; if not, align the router label (and its announcer tests).

## Evidence
- `the_one/interfaces/web/static/js/router.js` ~l.446 (`LIBRARY_LABELS` knowledge entry).
- `the_one/interfaces/web/static/js/areas/studio.js` `LIBRARY_GROUPS` (`label: 'Knowledge bases'`).
- `tests/browser/test_router_announce.py` (pins the announced text).
- Sortie 02 debrief (Architect).

## Corrective Action
`router.js` `LIBRARY_LABELS.knowledge` is now "Knowledge bases" (Library knowledge group only; the agent editor's Knowledge tab is unchanged). The announcer pins in `test_router_announce.py` and `test_flow_studio_library_list.py` were updated.

## Verification
routing and mcp lanes pass with the new text; no behaviour spec pins the old text (flight 03 leg 08).

## Sign-Off
**Reviewer**: Sonnet, the Mission 31 Flight 3 flight review (code and accessibility reviewers, then a scoped re-review of the fix pass)
**Verdict**: confirmed
**Commit**: `flight/3: Knowledge and connectors on the library (Mission 31)` on branch `flight/03-knowledge-and-connectors-on-the-library`
