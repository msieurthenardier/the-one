# Squawk 0186: A valid but non-object JSON body still returns 500 on many API routes

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-11
**Completed**: 2026-10-13

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
Enumerated all 24 `_read_json` callers in `the_one/interfaces/web/api.py`; every one
reads the body as an object (`.get`, `["key"]`, `data["id"] = ...`,
`model_validate(data)`); none takes a list (the ordering routes do not use it). So no
opt-in argument was added: `_read_json` itself now raises
`HTTPException(422, "Request body must be a JSON object.")` for any non-dict, keeping
0184's malformed-JSON sentence. The body is never echoed. One change in the shared
reader rather than per-route guards. Existing in-route `isinstance(data, dict)` checks
(knowledge-settings, provider oauth code) are now unreachable for non-dicts but harmless.

Routes parsing JSON without `_read_json` (not changed): `api.py` ~1372 and ~2488
(direct `await request.json()`), `app.py` 2820 and 2862 (`/api/window/*` payloads).
Not-yet-reviewed whether those guard non-dicts.

## Verification
- `ruff check` and `ruff format` on `the_one/interfaces/web/api.py`, `tests/test_api_invalid_json.py`: clean.
- Added `test_non_object_json_is_422` (bodies `[]`, `5`, `"x"`, `null` x 6 routes: PUT knowledge-settings, POST agents/providers/knowledge-bases/mcp-sources/connectors), asserting 422 and the exact detail.
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_api_invalid_json.py tests/test_oauth_start_endpoint.py tests/test_db_api.py tests/test_provider_api.py tests/test_time_settings_api.py -x --timeout 60`: 474 passed.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet; the batch includes the OAuth sign-in path, 0202), batch review of the 2026-10-13 squawk turnaround
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-10-13` commit on `squawk/turnaround-2026-10-13`. The final gate passed: unit 6287 passed and 14 skipped (the expected count under `THE_ONE_TEST_NETNS=1`); `PARALLEL_RESULT rc=0 total=998s lanes=9 failed=-`, every lane within budget. The Reviewer falsified the new tests (removing only the `isinstance(data, dict)` check makes `tests/test_api_invalid_json.py` fail) and restored `api.py` byte-identically.
