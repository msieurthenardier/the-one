# Squawk 0202: OAuth flow drivers send no `Accept` header, so a server answers 406 after sign-in

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-13
**Completed**: —

## Report
The-one has two hand-built OAuth flow drivers: `_drive_flow_test` (Test connection) and `_drive_flow` (the agent's consent flow). Each POSTs to the MCP server URL through the SDK's `OAuthClientProvider`, sending a JSON body and an `MCP-Protocol-Version` header but no `Accept: application/json, text/event-stream`.

A streamable-HTTP server that enforces content negotiation answers the driver's post-token retry with **406 Not Acceptable**. This was seen live with Cloudflare's MCP server in Mission 29 Flight 2's HAT, on 2026-10-13. The driver throws the response away and sign-in completes, so the only effect is a misleading 406 in the log. The fix is to send the same `Accept` header the SDK's transport sends.

## Evidence
- The dev-instance log right after `POST https://mcp.cloudflare.com/token "200 OK"`: `POST https://mcp.cloudflare.com/mcp "HTTP/1.1 406 Not Acceptable"`, then the next Test's POSTs return 200.
- `the_one/interfaces/web/api.py::_drive_flow_test` — `await client.post(server_url, json=body, headers={"MCP-Protocol-Version": version})`.
- `the_one/interfaces/web/api.py::_drive_flow` — the same `client.post(..., headers={"MCP-Protocol-Version": version})`.
- Related: the Flight 2 debrief, Recommendation 3, suggests a shared request builder for the raw MCP HTTP requests. That is out of scope here; this squawk only adds the header.

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*

## Disposition
