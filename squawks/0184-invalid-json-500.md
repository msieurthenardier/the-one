# Squawk 0184: Invalid JSON request bodies return 500 on most API routes

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-11
**Completed**: 2026-10-11

## Report
Mission 28 made `PUT /api/time-settings` return 422 for malformed JSON. `the_one/interfaces/web/api.py` still has about 26 bare `await request.json()` calls with no `JSONDecodeError` handling, so knowledge-settings and others return an unhandled 500 for a malformed body.

## Evidence
`grep -n "await request.json()" the_one/interfaces/web/api.py`. The fix: a shared `read_json_object(request, allowed_keys=None)` helper, or a global exception handler that maps `JSONDecodeError` to a plain-sentence 422. Add tests for two or three representative routes.

Logged from the Mission 28 mission debrief (mission Architect).

## Corrective Action
Added a private `_read_json(request)` helper in `the_one/interfaces/web/api.py` (right after `router`) that catches `ValueError` from `request.json()` and raises `HTTPException(422, "Request body is not valid JSON.")` (never echoes the body). Replaced all 24 bare `data/body = await request.json()` calls with it. A global `JSONDecodeError` handler was rejected: `api.py` also calls `json.loads` on stored DB values (skip counts, secrets, session messages), and a global handler would turn those genuine server faults into a misleading 422. The helper needs no middleware change, so the credential gate order is untouched. The two calls already wrapped in try/except (rules body, `PUT /api/time-settings`) keep their own messages.

## Verification
New `tests/test_api_invalid_json.py` (5 tests): malformed JSON to PUT /api/knowledge-settings, POST /api/agents and POST /api/providers gives 422 with the plain detail and no echo; PUT /api/time-settings keeps its own sentence; an unauthenticated malformed request through the real app stays 401. Targeted run: 37 passed. `make test-unit`: 5948 passed, 12 skipped. ruff check and format clean.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet), batch review of the 2026-10-11 squawk turnaround
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-10-11` commit on `squawk/turnaround-2026-10-11`. The final gate passed: unit 5946 passed and 14 skipped; `PARALLEL_RESULT rc=0 total=977s lanes=8 failed=-`, every lane within budget.
