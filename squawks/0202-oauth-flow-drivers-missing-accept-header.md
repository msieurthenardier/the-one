# Squawk 0202: OAuth flow drivers send no `Accept` header, so a server answers 406 after sign-in

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-13
**Completed**: 2026-10-13

## Report
The-one has two hand-built OAuth flow drivers: `_drive_flow_test` (Test connection) and `_drive_flow` (the agent's consent flow). Each POSTs to the MCP server URL through the SDK's `OAuthClientProvider`, sending a JSON body and an `MCP-Protocol-Version` header but no `Accept: application/json, text/event-stream`.

A streamable-HTTP server that enforces content negotiation answers the driver's post-token retry with **406 Not Acceptable**. This was seen live with Cloudflare's MCP server in Mission 29 Flight 2's HAT, on 2026-10-13. The driver throws the response away and sign-in completes, so the only effect is a misleading 406 in the log. The fix is to send the same `Accept` header the SDK's transport sends.

## Evidence
- The dev-instance log right after `POST https://mcp.cloudflare.com/token "200 OK"`: `POST https://mcp.cloudflare.com/mcp "HTTP/1.1 406 Not Acceptable"`, then the next Test's POSTs return 200.
- `the_one/interfaces/web/api.py::_drive_flow_test` — `await client.post(server_url, json=body, headers={"MCP-Protocol-Version": version})`.
- `the_one/interfaces/web/api.py::_drive_flow` — the same `client.post(..., headers={"MCP-Protocol-Version": version})`.
- Related: the Flight 2 debrief, Recommendation 3, suggests a shared request builder for the raw MCP HTTP requests. That is out of scope here; this squawk only adds the header.

## Corrective Action
Added a module constant `_MCP_POST_ACCEPT` ("application/json, text/event-stream", the value the SDK transport and the auth probe already send) and a helper `_oauth_driver_headers(version)` in `the_one/interfaces/web/api.py`; both `_drive_flow_test` and `_drive_flow` now pass its result as the POST headers. Header only: no token, credential or control-flow change. A shared helper (rather than two literals) keeps the drivers from drifting apart; the broader shared request builder from the debrief is left out of scope.

## Verification
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_oauth_test_connection_endpoint.py tests/test_oauth_start_endpoint.py tests/test_mcp_httpx_guard.py -x --timeout 30` (plus tests/test_mcp_test_connection_negotiation.py) -> 28 passed.
- New: Test-connection driver captured-header assertion, `_drive_flow` header equality updated, and `test_oauth_driver_headers_satisfy_content_negotiating_server` (MockTransport that 406s without Accept).
- `ruff check` / `ruff format --check` clean on changed files.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet; the batch includes the OAuth sign-in path, 0202), batch review of the 2026-10-13 squawk turnaround
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-10-13` commit on `squawk/turnaround-2026-10-13`. The final gate passed: unit 6287 passed and 14 skipped (the expected count under `THE_ONE_TEST_NETNS=1`); `PARALLEL_RESULT rc=0 total=998s lanes=9 failed=-`, every lane within budget.

## Disposition
