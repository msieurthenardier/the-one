# Squawk 0186: A valid but non-object JSON body still returns 500 on many API routes

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-11
**Completed**: —

## Report
Squawk 0184 made malformed JSON return a plain 422 through
`api.py::_read_json`. A body that is valid JSON but not an object (`[]`, `5`,
`"x"`) still reaches `.get(...)` or `["key"]` in many of the 24 routes, and
those routes return an unhandled 500.

## Evidence
- Found by the 2026-10-11 squawk-turnaround Reviewer, outside 0184's scope.
- The fix direction: `_read_json(request, require_object=True)`, or a
  separate `_read_json_object`, raising `HTTPException(422, "Request body must
  be a JSON object.")` for non-dict bodies on routes that expect an object.
  Keep any route that legitimately takes a list (check each). Add tests for
  two or three representative routes.

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
