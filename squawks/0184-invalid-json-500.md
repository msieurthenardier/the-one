# Squawk 0184: Invalid JSON request bodies return 500 on most API routes

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-11
**Completed**: —

## Report
Mission 28 made `PUT /api/time-settings` return 422 for malformed JSON. `the_one/interfaces/web/api.py` still has about 26 bare `await request.json()` calls with no `JSONDecodeError` handling, so knowledge-settings and others return an unhandled 500 for a malformed body.

## Evidence
`grep -n "await request.json()" the_one/interfaces/web/api.py`. The fix: a shared `read_json_object(request, allowed_keys=None)` helper, or a global exception handler that maps `JSONDecodeError` to a plain-sentence 422. Add tests for two or three representative routes.

Logged from the Mission 28 mission debrief (mission Architect).

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
