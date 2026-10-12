# Flight Log: Port to the mcp 2.x SDK at parity

**Flight**: [Port to the mcp 2.x SDK at parity](flight.md)

## Summary
Mission 29 Flight 1, **ready** (approved 2026-10-12). Began as sortie planning (charter agreed 2026-10-11), escalated to Mission 29 on 2026-10-12 and re-homed here. Origin: a squawk attempt (not logged) that failed the squawk gate — the newer protocol needs the `mcp` 2.x SDK, a breaking upgrade with design decisions.

---

## Leg Progress

## Code Interrogation (2026-10-11)

Read-only survey of the `mcp` 2.x upgrade surface (SDK sources read as text from extracted wheels; nothing executed). Key findings:

**Soak rule.** `mcp` 2.3.0 / `mcp-types` 2.3.0 were uploaded 2026-10-02 (under the project's 14-day soak until 2026-10-16). `mcp` 2.2.0 (2026-09-07) clears it, speaks 2026-07-28 (`mcp_types.version.MODERN_PROTOCOL_VERSIONS == ("2026-07-28",)`), and its `mcp/client/_probe.py` is byte-identical to 2.3.0's. 2.3.0 adds an SSE max-event-size limit and minor auth/server changes. `httpx2` 2.13.1 (2026-09-23) clears the soak; `mcp` 2.2.0 needs `httpx2>=2.5.0`.

**Auto mode.** Implemented by the private `mcp.client._probe.negotiate_auto(session)`: `send_discover(LATEST_MODERN_VERSION)` → `adopt(DiscoverResult)`, else fall back to `session.initialize()`. Every `MCPError` except -32022 falls back; non-MCPError exceptions propagate; discover timeout 10 s (`session.py DISCOVER_TIMEOUT_SECONDS`). The-one can keep its structure (transports yield an entered `ClientSession`; `MCPClient.connect` swaps `initialize()` for negotiation). The high-level `mcp.client.Client` is not needed. Modern sessions stamp `_meta` + `MCP-Protocol-Version`/`Mcp-Method`/`Mcp-Name` headers internally; `list_tools`/`call_tool` unchanged in use; no `Mcp-Session-Id` in the modern era.

**Breaking changes beyond renames** (all must land together — `surface.py` importing `mcp.server.fastmcp` raises `ModuleNotFoundError` and takes down `app.py`):
1. `httpx` → `httpx2` for everything handed to the SDK (`streamable_http_client(http_client=httpx2.AsyncClient)`, `OAuthClientProvider` is an `httpx2.Auth`); the rest of the app stays on `httpx` → dual HTTP stack.
2. Wire types are snake_case (`protocol_version`, `server_info`, `input_schema`, `structured_content`, `is_error`, …); `model_dump(mode="json")` emits snake_case unless `by_alias=True` → the editor's `info.websiteUrl` etc. silently lost. MagicMock-based tests set camelCase and would silently pass.
3. **No-provider HTTP 401 is no longer raised**: 2.x turns a POST 401 into `MCPError(INTERNAL_ERROR, "Server returned an error response")` and drops `WWW-Authenticate` → the-one's "three 401 sources" contract and `MCPAuthRequired(resource_metadata_url=…)` (consumed by `agent/core.py`) break. Needs a redesign (e.g. an httpx2 response hook). Existing A9 test injects a synthetic `HTTPStatusError` and would keep passing.
4. OAuth `callback_handler` must return `AuthorizationCodeResult(code, state, iss)` (RFC 9207); `oauth/_state.py`, `oauth/handlers.py` and the `api.py` callback route carry `(code, state)` and drop `iss` → sign-in fails against servers advertising `authorization_response_iss_parameter_supported`.
5. `McpError(ErrorData)` → `MCPError(code, message, data)`; `mcp.shared.version` → `mcp.types.version`; `streamable_http_client` yields a 2-tuple (the-one unpacks 3 at six sites).
6. `mcp.server.fastmcp.FastMCP` → `mcp.server.mcpserver.MCPServer`; `stateless_http`/`streamable_http_path`/`transport_security` move to `streamable_http_app(...)`; non-`ToolError` exceptions in a tool lose their message ("Error executing tool <name>") → `surface.py` refusals must raise `ToolError`; `hello_server` escape tools' strerror assertions (bwrap lane) change.
7. `_probe_auth_posture` (`transports/streamable_http.py`) hand-posts `initialize` with the pinned version; must send `LATEST_HANDSHAKE_VERSION` and tolerate modern-only servers. `api.py` OAuth flow drivers must use `httpx2.AsyncClient`.
8. Modern-era metadata: read `session.protocol_version` / `server_capabilities` / `server_info` (from `DiscoverResult._meta["io.modelcontextprotocol/serverInfo"]`) / `instructions`; de-dup the serverInfo stamp from `_meta`.
9. Unsupported version: handshake era still raises `RuntimeError("Unsupported protocol version from the server: X")`; modern era raises `MCPError(-32022)` → needs explicit mapping to `MCPVersionMismatch`.
10. Packaging: `packaging/windows/the-one.spec` collects only `mcp`; `mcp_types`, `httpx2`, `httpcore2`, `truststore`, `opentelemetry` need checking in the frozen build.

**Test breakage**: `test_mcp_client.py` (heaviest), `test_mcp_integration.py`, `test_mcp_oauth_integration.py`, `test_mcp_transport_timeouts.py`, OAuth tuple-shape tests, `test_self_configuration_surface.py` (whose real loopback becomes a ready-made modern-era proof). `hello_server` will serve both eras after the port; proving fallback needs a legacy-only fixture (stdio `serve_loop`; HTTP wrapper rejecting the modern header).

**Prior debriefs**: anyio cross-task cancel-scope fragility of SDK teardown (Mission 07 F06/F08) is unresolved and the 2.x session rewrite changes that surface; HAT against a real OAuth MCP server caught issues six flights running.

**Gate re-check**: the 401-detection / RFC 9207 / dual-HTTP-stack work is a second cluster of design decisions in a security-sensitive domain, separate from the auto-negotiation cluster — raised with the operator before flight design continues.

## Escalation (2026-10-12)

**Escalated to a mission** by operator decision. Failed sortie criterion 2 (one cluster of design decisions): the SDK port at parity carries its own security-sensitive cluster — HTTP 401 detection now that 2.x swallows it, RFC 9207 `iss` through the OAuth callback, the httpx/httpx2 dual stack, the `MCPServer` port — separate from the auto-negotiation cluster. Planned shape: Flight 1 port to `mcp` 2.x at parity; Flight 2 auto negotiation + 2026-07-28 + HAT.

**SDK pin**: operator chose `mcp==2.3.0` (over the soak-clearing 2.2.0); 2.3.0 clears the 14-day soak on 2026-10-16.

**Rebase note**: main moved to `8193d5f` (v0.11.4) during planning; sortie number 03 was taken by `sorties/03-claude-plan-token`. No MCP code changed in between (only the MCP editor's breadcrumb, `mcp-server-editor.js`), so the interrogation above still holds. Worktree branch renamed `mission/29-mcp-2x-protocol`.

## Design Review (2026-10-12)

Two Architect cycles (the maximum).
- **Cycle 1 — approve with changes**: DD1 rescoped (record scope, lifetime, plumbing, every failure path, provider-attached failure proven end to end, `looks_like_token_failure` re-pinned); DD8 corrected (the SDK surfaces `MCPError(-32000, "SSE stream failed: …")`, not an httpx2 error); three further SDK-forced changes surfaced → operator accepted all three (DD12, mission Constraint); `shared`/`chats` lanes added (full `make test-browser`); DD10 concrete versions (exact soak time, `opentelemetry-api<1.45.1`); DD3 premise verified; packaging metadata + doctor gate.
- **Cycle 2 — approve with changes**, applied without a third cycle: DD1 last-status rule (a 401 counts only if it is the most recent MCP-POST response since the operation's baseline — fixes a misfire after a successful mid-operation sign-in); MCP-POST discriminator by method + same origin + `accept: text/event-stream` (survives DD12's same-origin redirects, excludes token/DCR POSTs); baseline and read-before-cleanup points; doctor gate named (`mcp sdk`, twelfth) with every pinned list it touches; stale Objective/approach/leg/checkpoint text aligned; DD12 error classes per the existing contract and the stateless-404 self-heal note; truststore cap rule.
- **Decided by the Flight Director**: a provider-attached sign-in failure (e.g. mismatched issuer) keeps 1.x parity and reads as `MCPAuthRequired`, not the OAuth error text. Revisit if the HAT shows a sign-in loop.
