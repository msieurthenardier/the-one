# Squawk 0373: "Forget tools list" stays hidden after a Test on the operator's servers

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-17
**Completed**: —

## Report
In the Library MCP server editor, the operator pressed "Forget tools list" on several HTTP servers, then pressed Test. The tools loaded again, but the button did not return, and it has stayed gone on those servers since.

Expected: once a Test has reloaded the tools list of an HTTP server with no sign-in, "Forget tools list" is shown again.

Not reproduced. Squawk 0371's Developer ran Test, Forget, Test in a real browser against the rich fixture server (no sign-in, no headers) on the working tree: the button came back (armed, which 0371 fixed). So the cause depends on something the operator's servers or app have that the fixture did not.

First step: with the operator's consent, read one affected server's record from their instance (`GET /api/mcp-sources/{id}`, read-only) and note `type`, `oauth_active`, `has_access_token` and the keys of `config._cache`; also note which app version the operator runs (a packaged release may differ from the working tree). The button's rule is in the first Evidence line, so the record says directly which condition is false.

Untested variants worth trying if the record does not settle it: a server with a static header or token; a server with a blank "Set per agent" header; a server whose connection probe answers `oauth` or an unexpected status, so the Test goes on to register a client and stores sign-in keys (`oauth_active` then stays true and the editor shows Reset connection in place of Forget).

## Evidence
- `the_one/interfaces/web/static/js/areas/studio/mcp-connection-status.js::updateButtons` — Forget is shown only for `type === 'streamable-http'`, `oauth_active !== true` and a `_cache` with `auth_posture` or `tools`.
- `the_one/interfaces/web/api.py` (the MCP source response builder) — `oauth_active` is true when any sign-in-managed secret key is stored, including `dcr_credentials` alone.
- `the_one/interfaces/web/api.py::_test_mcp_connection_inner` — after a Forget the cached posture is gone, so the next Test probes again and may take a different path from the one that first filled the cache.
- `squawks/0371-forget-tools-list-returns-armed.md` — the reproduction that did not show this symptom, and the test it added (`test_forget_then_test_brings_the_button_back_at_rest`).

- **Operator, 2026-11-17, on v0.16.5** (which carries squawk 0371's fix): the button is still absent on the server named `mcp-everything`.
- **Second reproduction attempt, 2026-11-17, still not reproduced** (scratch instance on port 8485, this tree at `bc497ab2`, the public `@modelcontextprotocol/server-everything` over HTTP, API calls only; the button's rule was computed from each `GET /api/mcp-sources/{id}`):
  - Version 1.0.0: Test, Forget, Test, Test. After every Test the record is `type=streamable-http`, `oauth_active=false`, `auth_posture=no_auth`, 13 tools: the rule is true. After the Forget the cache is empty and the rule is false, as designed.
  - The server's process replaced by 2.3.0 under the same saved record, then Test, Forget, Test: the rule is true after every Test (22 tools, protocol `2026-07-28`).
  - A local-command server never satisfies the rule, whatever its cache holds: `type` is `stdio`.
- Code read of the Test route and the editor (`api.py::_test_mcp_connection_inner`, `::_build_and_test_no_auth_mcp`; `mcp-connection-status.js::syncFromServer`): for an HTTP server every successful Test writes `tools` and the editor re-reads the record afterwards. So with a successful Test the button can be absent only when the server's type is not HTTP, or when `oauth_active` is true (then Reset connection is shown in its place).
- Still needed from the operator's `mcp-everything` page: the Type field's value; whether a "Reset connection" button is shown; whether the status line reads Connected with tools listed after a Test.

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
