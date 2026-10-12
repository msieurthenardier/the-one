# Flight: Port to the mcp 2.x SDK at parity

**Status**: in-flight
**Mission**: [MCP servers connect on the newest protocol](../../mission.md)

## Contributing to Criteria
- [ ] A server that supports only an older revision still connects on its revision, and its tools list and run, over stdio and streamable HTTP (parity half; the post-first-connect latency bound is Flight 2's)
- [ ] Signing in to a remote MCP server that requires OAuth still works end to end, including the RFC 9207 issuer
- [ ] An agent's self-configuration tools still work, and their refusals still read as a one-line reason
- [ ] The Windows packaged build still builds and `the-one doctor` passes in it
- [ ] The unit suite and the MCP-touching browser lanes pass; every changed test expectation is listed with its reason

> Re-homed 2026-10-12 from sortie planning (`sorties/03-mcp-2026-07-28-protocol`, never committed); the sortie's charter now lives in the mission. See the flight log's "Escalation" section.

---
## Pre-Flight

### Objective
Move the-one's MCP client, its OAuth sign-in, the self-configuration loopback server and the MCP test fixtures from `mcp==1.28.1` to `mcp==2.3.0` with no behaviour change an operator would notice — every server still connects on the initialize handshake, exactly as today — except the four deliberate changes the operator accepted (DD8's 1 MiB event cap and DD12's three), each failing with a plain error. The SDK upgrade is atomic: `mcp` 1.x and 2.x share a distribution name, and 2.x's `mcp.server.fastmcp` stub raises `ModuleNotFoundError`, which takes down `the_one/interfaces/web/app.py`'s import of the self-configuration surface. So the whole port lands as one leg. Flight 2 builds automatic negotiation of 2026-07-28 on top.

### Open Questions
- [x] How does the-one detect "this server wants sign-in" now that 2.x no longer surfaces HTTP 401? → DD1
- [x] How does the RFC 9207 issuer reach the SDK? → DD2
- [x] How do self-configuration refusals keep their one-line reason on the new server API without changing tests? → DD3
- [x] Which code moves to `httpx2`, and how is a silent `httpx` catch prevented? → DD4
- [x] How do snake_case wire types stay invisible to the editor and the agent? → DD5
- [x] Where do the negotiated revision and server metadata come from? → DD6
- [x] Which live sign-in target? → Cloudflare's MCP server only (operator decision, 2026-10-12) — DD11
- [x] Does Python accept `class X(ToolError, PermissionError)` and `class Y(ToolError, ValueError)`? → yes (Architect, stand-in classes on Python 3.12): MRO `X → ToolError → MCPServerError → PermissionError → OSError → Exception`, `str(X("msg")) == "msg"`, `except PermissionError` catches it. Raise with ONE argument (two args format as `[Errno …]`). See DD3.
- [x] Which behaviour changes does 2.x force beyond the 1 MiB cap, and are they accepted? → DD12 (operator: accept all three, 2026-10-12)

### Design Decisions

**DD1 — Sign-in detection by a scoped, sequenced 401 record on the transport-owned HTTP client.**
The streamable-http transport attaches an async, headers-only `httpx2` response hook (it never reads the body) to the client it hands the SDK, on **all three** client branches in **both** entry points — `connect_streamable_http` and `_open_streamable_http_transport_stack` (`the_one/mcp/transports/streamable_http.py:337-399`, the path `MCPClient._transport_connect` actually uses): the production client it builds; a pre-built client from `_test_http_client_override` (appended to `client.event_hooks["response"]` and removed on exit, because the seam client is shared across connections in a test); and the factory branch.
- **Scope**: the hook records every response to an **MCP POST** — `response.request.method == "POST"`, the request URL has the same origin as the endpoint (compared as `httpx2.URL(source.config["url"])`, whose scheme, host and default port are normalised), and its `accept` header contains `text/event-stream` (the SDK's MCP POSTs carry `accept: application/json, text/event-stream`, `mcp/client/streamable_http.py::StreamableHTTPTransport._prepare_headers`). The origin rule, not an exact-URL match, keeps a 401 behind a same-origin redirect (DD12.1, e.g. `/mcp` → `/mcp/`) in scope. The auth flow's own requests are excluded by the header rule: token and refresh POSTs are form-encoded (`oauth2.py` ~477, ~531), DCR sends only `Content-Type: application/json` (`auth/utils.py` ~294), discovery is GET. GET-stream responses are not recorded. For each MCP-POST response the record keeps its status and, for a 401, the `resource_metadata` field of `WWW-Authenticate`.
- **Lifetime — last-status rule**: each recorded response gets a per-connection monotonically increasing sequence number. `MCPClient` captures the current sequence when an operation (`connect`, `list_tools`, `call_tool`) starts, and treats a failure as auth-required **only if the most recent MCP-POST response after that baseline was a 401**. So a sign-in that succeeds mid-operation (401, OAuth flow, retried POST answers 200 with an ordinary JSON-RPC error) does not misfire; a flow that dies after the 401 (mismatched issuer, token endpoint 400, or a 2.3.0 `CancelledError` instead of `OAuthFlowError`) leaves 401 as the last status; a concurrent GET can't interfere; a stale 401 from an earlier operation sits before the baseline. `connect`'s baseline is 0 on the fresh per-connection record (the session, and so its record, doesn't exist when `connect` starts). `call_tool`'s lazy `list_tools()` captures its own baseline. A pool rebuild after `_mark_dead` gives a new client, session and record, so nothing carries over. One helper (`_auth_required_since(baseline) -> MCPAuthRequired | None`) holds the window logic for all three methods.
- **Plumbing**: a module-level `weakref.WeakKeyDictionary` in the transport module maps the yielded `ClientSession` to its record, read through one accessor, `auth_record_for(session: ClientSession) -> AuthRecord | None` (2.3.0's `ClientSession` defines no `__eq__` or `__slots__`, so it is hashable and weakly referenceable; `MCPClient._session` keeps it alive for the connection's life, whichever task owns the stack). `_transport_connect` keeps yielding only a session, so `patch_transport`-style tests are untouched (a patched transport simply has no record).
- **Translation**: on **every** failure after a request is sent in `connect`, `list_tools` and `call_tool` (errors raised before sending — `MCPToolNotFoundError`, `MCPArgumentError` — never consult the record; `asyncio.TimeoutError` does) — `MCPError` (any code: a 401 with a JSON-RPC body surfaces the server's own code and message, not `INTERNAL_ERROR` — `mcp/client/streamable_http.py:398-415`), `BaseExceptionGroup`, `CancelledError` from the transport's task group, and generic `Exception` — `MCPClient` consults the record first — in `connect`, before the `CancelledError` and `_safe_cleanup` branches set `self._session = None` (`client.py` ~442-460) — and raises the existing `MCPAuthRequired(resource_metadata_url=…)`, replacing the three `httpx.HTTPStatusError` walks (`client.py` ~463, ~656, ~797). Never gate on the error code or message text.
- **Provider-attached failure**: kept as today's `OAuthFlowError`/`OAuthTokenError` → `MCPAuthRequired` translation (parity: a failed sign-in flow reads as sign-in required, as in 1.x), backed by the last-status rule, and **proven end to end** through `MCPClient.connect` against a real fixture (a mismatched issuer, and a token endpoint answering 400), because in 2.3.0 an auth-flow exception raised inside the transport's `post_writer` task group may surface as `CancelledError`, not a matchable group; today's A8/A9 tests inject the exception directly.
- **Stale-token recovery**: the Test-connection route's `looks_like_token_failure` (`the_one/interfaces/web/api.py` ~3703-3740) matches `MCPConnectionError` text ("did not respond", "cancelled during initialize"). Its inputs are reshaped by this DD and DD7, so it is re-pinned by a test where a refresh-token failure runs against a real fixture, and the clear-stale-tokens-then-Phase-B recovery is observed.
- **Fixture**: `tests/fixtures/oauth/__init__.py::_OAuthASHandler` already serves a real 401 with `WWW-Authenticate` over loopback; tests use it (and the ASGI fixture) rather than an injected `HTTPStatusError`.
- Rationale: covers every request on the connection (including a mid-session token expiry on `call_tool`), keeps the `MCPAuthRequired` contract consumed by `the_one/agent/core.py` unchanged, and needs no extra round trip. The bare-`httpx` probe (`_probe_auth_posture`) only runs on Test connection, so it can't cover the agent path.
- Trade-off: the-one depends on the SDK sending through the client it was given (`mcp/shared/_httpx_utils.py:131` sends via `client.send`, which fires hooks) — pinned by the real-401 tests above.

**DD2 — RFC 9207 issuer carried from the callback route to the SDK.**
`GET /api/oauth/callback` (`the_one/interfaces/web/api.py`, route at ~4413) reads the optional `iss` query parameter; `the_one/mcp/oauth/_state.py::resolve(state, code, returned_state)` gains `iss` and its `code_future` carries it; `the_one/mcp/oauth/handlers.py::callback_handler` returns the SDK's `AuthorizationCodeResult(code, state, iss)` instead of a `(code, state)` tuple. The in-repo OAuth test server gains a mode that advertises `authorization_response_iss_parameter_supported` and returns `iss`; tests cover a matching issuer (sign-in succeeds), a mismatched issuer, and a missing one when advertised (sign-in fails with the existing plain sign-in error). Stored client registrations from 1.x have no `issuer` and stay valid (2.x treats them as unbound).
- Rationale: 2.x fails every sign-in against an authorization server that advertises the parameter unless `iss` is forwarded (`mcp/client/auth/utils.py::validate_authorization_response_iss`).
- Trade-off: none beyond touching a security-sensitive route; the change is additive (a new optional query parameter).

**DD3 — Self-configuration refusals as dual-typed `ToolError`s.**
`the_one/self_configuration/surface.py` moves from `FastMCP` to `mcp.server.mcpserver.MCPServer` (transport options move to `streamable_http_app(stateless_http=True, streamable_http_path="/")` at its mount in `the_one/interfaces/web/app.py`; `session_manager.run()` stays in the lifespan). Its refusals raise two module-level classes, one subclassing `ToolError` and `PermissionError` (today's `PermissionError` raises at `surface.py:78-116`), one subclassing `ToolError` and `ValueError` (`surface.py:197-202`). 2.x keeps "Error executing tool <name>: <msg>" only for `ToolError` and reduces anything else to "Error executing tool <name>" (`mcp/server/mcpserver/tools/base.py`), so this keeps the one-line reason byte-identical to 1.x, and `tests/test_self_configuration_write.py` (expects `ValueError`) and `tests/test_self_configuration_surface.py` (matches "disabled") pass unchanged.
- Premise verified at planning (see Open Questions): both combinations work; raise with ONE argument. **Fallback** kept for the record: raise `ToolError` and update the three `ValueError` assertions (`test_self_configuration_write.py:207, 220, 242`), listed in the flight log.
- One surface app factory (a function in `surface.py`) builds the mounted app with `stateless_http=True, streamable_http_path="/"`; `app.py` (~600) and the test mount (`tests/test_self_configuration_surface.py` ~136) both call it, so the options can't drift.
- `tests/fixtures/mcp/hello_server.py` moves to `MCPServer` the same way; `transport_security=` moves to `streamable_http_app(...)` at every call site (`tests/conftest.py::mcp_fixture_http_client` ~297); its test-only escape tools keep their strerror text by raising `ToolError(str(exc))`, so the bwrap-lane assertions in `tests/test_mcp_sandbox_integration.py` hold.

**DD4 — Everything under `the_one/mcp/` on `httpx2`; a guard test bans `httpx` there.**
The transport, the OAuth provider factory (`the_one/mcp/oauth/provider_factory.py` returns an `httpx2.Auth`), `MCPClient`'s exception handling (`client.py:692`, `:851` catch `(httpx.HTTPError, anyio.ClosedResourceError)`), and the auth-posture probe all move to `httpx2`, as do the two OAuth flow drivers in `api.py` (~3781, ~4641, which build `httpx.AsyncClient(auth=provider)`) and the test seam `tests/conftest.py::mcp_fixture_http_client` (`httpx2.ASGITransport`). A unit test fails on any `import httpx` / `from httpx` under `the_one/mcp/`. The rest of the app (LLM SDKs, web fetch, Starlette `TestClient`) stays on `httpx`; `httpx2.alias_httpx()` is not used (it aliases process-wide).
- Rationale: `httpx` stays importable, so a leftover `except httpx.HTTPError` fails silently rather than loudly; one rule for the whole package is easy to enforce mechanically.
- Trade-off: the probe moves libraries without strictly needing to.

**DD5 — Wire types dump by alias at every boundary; tests use real SDK models.**
2.x models are snake_case with camelCase aliases and dump snake_case by default. Every `model_dump(mode="json")` in `the_one/mcp/client.py` (capabilities ~227, server info ~242, `_meta` ~525, tool annotations ~703, raw result blocks ~864) — and any further dump or attribute site the port finds in `api.py`, `the_one/mcp/_tool.py` and `_tool_provider.py` — gains `by_alias=True`, so the MCP cache, the API responses, the editor (`mcp-server-editor.js` reads `info.websiteUrl` at ~325) and the content blocks an agent receives keep today's camelCase keys with no JavaScript change. Two known key differences are accepted and listed in the flight log: raw content blocks dump `"_meta"` where 1.x dumped `"meta"`, and the capabilities dump gains `"extensions": null` (the editor reads a fixed `SPEC_CAPABILITY_KEYS` list, ~286, so it is unaffected). `the_one/mcp/oauth/storage.py` is unaffected (auth models are snake_case with no alias generator). Attribute reads move to snake_case (`input_schema`, `structured_content`, `is_error`, …). Tests in `tests/test_mcp_client.py` that build camelCase `MagicMock` results (~125-255) move to real `mcp.types` model instances, so a missed rename fails loudly instead of returning a Mock.

**DD6 — Negotiated revision and server metadata read from the session, era-agnostically.**
`MCPClient` reads `session.protocol_version`, `session.server_capabilities`, `session.server_info` and `session.instructions` (2.x `ClientSession` properties) instead of fields of the `InitializeResult`. Flight 1 still calls `session.initialize()`, so values are unchanged; Flight 2 then only swaps the call. The post-connect version gate (`client.py:497-501`) is rebuilt on `mcp.types.version.HANDSHAKE_PROTOCOL_VERSIONS` (`mcp.shared.version` is gone). `_PINNED_PROTOCOL_VERSION` (`the_one/mcp/__init__.py:12`) stays "2025-11-25", and the tripwire test (`tests/test_mcp_client.py:44-55`) is re-pinned to `mcp.types.version.LATEST_HANDSHAKE_VERSION` — 2.x's `LATEST_PROTOCOL_VERSION` is now "2026-07-28", which Flight 2 adopts.

**DD7 — Errors renamed, not reshaped.**
`McpError(ErrorData)` → `MCPError(code, message, data)` throughout (`client.py` and tests); `_is_session_terminated` keeps working through `.error`. The handshake still raises `RuntimeError("Unsupported protocol version from the server: …")`, so `client.py::_UNSUPPORTED_VERSION_RE` and `MCPVersionMismatch` are unchanged. `streamable_http_client` now yields `(read, write)`; the six three-value unpacks in `transports/streamable_http.py` become two-value. The session-terminated tripwire (`tests/test_mcp_client.py` ~1700-1724) calls `StreamableHTTPTransport._send_session_terminated_error`, which 2.x removed; it is rewritten to drive a real 404 with a session id set (2.x builds `INVALID_REQUEST "Session terminated"` inline), keeps its pin, and is listed in the flight log.

**DD8 — The 1 MiB SSE event cap is accepted, passed explicitly, with a plain error.**
The transport passes `max_sse_event_size` from a the-one constant equal to the SDK default (1 MiB), so a future SDK default change shows up in a diff. An oversized event raises `httpx2.SSEError("Server-sent event exceeded the 1048576 byte limit.")` inside the SDK (`httpx2/_sse.py:124`), which the SDK turns into `MCPError(CONNECTION_CLOSED=-32000, "SSE stream failed: …")` for the abandoned request (`mcp/client/streamable_http.py` ~503-522). `MCPClient` matches code -32000 **and** a message starting with "SSE stream failed:" and containing "byte limit" (so other -32000 errors, e.g. "SSE stream ended without a response", stay unmatched); the check sits after DD1's record check and before `call_tool`'s generic `MCPCallError`, and translates it to a plain one-line message naming the limit: `MCPCallError` from `call_tool` (it reaches the chat's tool result), `MCPConnectionError` from `list_tools`/`connect` (it reaches the MCP editor's Test result). The connection is **not** marked dead — the session survives one oversized response. An oversized event on the GET stream is logged and retried by the SDK (lines ~262-264) and is out of the-one's hands; noted in `the_one/agents.md`. A unit test drives an oversized event through the ASGI fixture for both `call_tool` and `list_tools`.

**DD9 — OS trust store on the SDK path, documented.**
`httpx2` verifies TLS against the operating system's trust store (via `truststore`) unless `SSL_CERT_FILE`/`SSL_CERT_DIR` is set; `httpx` (the rest of the app) uses certifi. Accepted by the operator (2026-10-12); `SECURITY-MODEL.md` gains a short entry naming the split and the override.

**DD10 — Exact pins (soak waived by the operator, 2026-10-12).**
> Original framing (planning): every new package capped at its newest release uploaded ≥14 days before the leg, `mcp` 2.3.0 not before 2026-10-16 22:06 UTC, `opentelemetry-api<1.45.1`. Superseded by the operator's soak waiver at flight start (flight log, Flight Director Notes).

`pyproject.toml`: `mcp==2.3.0` (pulls `mcp-types==2.3.0`) and an explicit `httpx2>=2.10.0` floor (mcp 2.3.0's own requirement, made visible beside the other floors). No soak caps on `httpx2`, `httpcore2`, `truststore` or `opentelemetry-api`; the `mcp` pin's comment records the waiver. `uv.lock` regenerated; `pip-audit` clean on the new packages.

**DD11 — Packaging and the live checks.**
`packaging/windows/the-one.spec` collects `mcp_types`, `httpx2`, `httpcore2`, `truststore` and `opentelemetry` beside `mcp`, filters `mcp.server.fastmcp` out of the `mcp` submodule walk (its stub raises on import, like the existing `mcp.cli` filter at ~75), adds `copy_metadata("httpx2")` and `copy_metadata("httpcore2")` (both call `importlib.metadata.version()` at import time), and corrects its stale "pinned 1.27.0" comment. `the-one doctor` gains a twelfth gate, appended after `time zones`, printing `mcp sdk: OK`: it imports `mcp`, imports `the_one.self_configuration.surface`, and builds a `truststore` SSL context. It runs on every host (so `make test-unit`'s doctor tests import the surface). The fixed `gates` list in `the_one/diagnostics.py::run_doctor` (~1032) and its "eleven" docstring, `tests/test_doctor.py::test_gates_list_has_eleven_names_ending_with_time_zones` (renamed for twelve ending with `mcp sdk`; logged as a changed expectation), `CLAUDE.md`'s gate list, and the needle lists of both Windows lanes — `ci/tasks/windows-installer-build.yml` (~117; it already runs the frozen doctor as a build gate, ~97-119) and the break-glass `.github/workflows/windows-installer.yml` (~107-135) — all gain it, so an import failure only a frozen build shows can't pass silently. The live sign-in check follows `tests/HAT.md` Tier 2 against `https://mcp.cloudflare.com/mcp` on a dedicated dev instance; the OAuth redirect URI follows that instance's port (`the_one/mcp/oauth/provider_factory.py:121`), so dynamic client registration works there without touching 8484.

**DD12 — Behaviour changes 2.x forces, accepted (operator, 2026-10-12).**
Beyond the 1 MiB cap (DD8), three changes are taken as deliberate, each surfacing as a plain error rather than worked around:
1. **Redirects**: the MCP path follows only same-origin, method-preserving redirects (`mcp/shared/_httpx_utils.py::stream_within_origin`, ~111-145); a cross-origin redirect fails with the SDK's `MCPError(INVALID_REQUEST, "Redirect to … not followed")`, translated per the existing contract (`MCPConnectionError` from `connect`/`list_tools`, where it normally first hits at `initialize`; `MCPCallError` from `call_tool`). The now-inert `follow_redirects: True` kwarg in `_build_production_httpx_kwargs` is dropped.
2. **Authorization-server issuer**: 2.x checks that the authorization server's metadata names the expected issuer (`oauth2.py` `validate_metadata_issuer`) and drops stored credentials recorded for a different issuer (`credentials_match_issuer`); a mismatch fails sign-in with the existing plain sign-in error (covered by DD1's end-to-end provider-failure test).
3. **404 with no `Mcp-Session-Id` issued** — which for a stateless server is its whole connection lifetime — reads `METHOD_NOT_FOUND "Not Found"` instead of "Session terminated" (`mcp/client/streamable_http.py` ~417-424). In 1.x every 404 read "Session terminated", so `call_tool` marked the client dead and the pool reconnected; in 2.x a stateless server's mid-use 404 becomes an `MCPCallError` with no self-heal. Accepted (a reconnect can't fix a wrong path); noted in the flight log.
The mission's Constraints list all four; `the_one/agents.md` records them.

### Citation Audit

Verified against the worktree at `8193d5f` and the extracted `mcp` 2.3.0 / `mcp-types` 2.3.0 / `httpx2` 2.13.1 sources:

| Citation | Status |
|---|---|
| `the_one/mcp/client.py` connect `except` — walks `BaseExceptionGroup.subgroup(httpx.HTTPStatusError)` for 401 → `MCPAuthRequired` (~463-476) | verified |
| `the_one/mcp/client.py::list_tools` — `except* httpx.HTTPStatusError` no-provider 401 path (~656-679) | verified |
| `mcp/client/streamable_http.py` (2.3.0) — POST status ≥ 400 becomes `ErrorData(INTERNAL_ERROR, "Server returned an error response")`, headers dropped (~398-430); **caveat**: a JSON-RPC error body is passed through with the server's own code | verified (Architects, mission validation + flight review) |
| `the_one/mcp/transports/streamable_http.py::_open_streamable_http_transport_stack` (~337-399) — the path `MCPClient._transport_connect` uses | verified (flight review) |
| `httpx2/_client.py::_send_handling_redirects` (~1868-1884) — response hooks fire for every response, including `Auth`-flow requests (`_send_handling_auth`, ~1834-1866) | verified (flight review) |
| `httpx2/_sse.py:124` `SSEError` → `mcp/client/streamable_http.py` ~503-522 `MCPError(-32000, "SSE stream failed: …")` | verified (flight review) |
| `the_one/interfaces/web/api.py::looks_like_token_failure` (~3703-3740) matches `MCPConnectionError` text | verified (flight review) |
| `tests/fixtures/oauth/__init__.py::_OAuthASHandler` serves a real 401 with `WWW-Authenticate` | verified (flight review) |
| `httpx2` `AsyncClient(event_hooks=…)`, `Auth`, `ASGITransport`, `HTTPError` exist (2.13.1) | verified (Architect, from the wheel) |
| `mcp/shared/_httpx_utils.py` (2.3.0) — requests go through `client.send` (hooks fire) | verified (Architect) |
| `the_one/mcp/transports/streamable_http.py::_build_production_httpx_kwargs` — transport builds the client's kwargs (headers, timeout, `auth`) | verified |
| `the_one/mcp/oauth/_state.py::resolve(state, code, returned_state)`; `code_future: Future[tuple[str, str \| None]]` (:56, :106) | verified |
| `the_one/mcp/oauth/handlers.py::callback_handler -> tuple[str, str \| None]` (:142) | verified |
| `mcp/shared/auth.py::AuthorizationCodeResult(code, state=None, iss=None)`; `oauth2.py` `callback_handler: Callable[[], Awaitable[AuthorizationCodeResult]]` | verified |
| `the_one/interfaces/web/api.py` `@router.get("/oauth/callback")` (:4413) | verified |
| `the_one/self_configuration/surface.py` — `PermissionError` raises (:78-116), `ValueError` raises (:197-202), `from mcp.server.fastmcp import Context, FastMCP` (:26) | verified |
| `tests/test_self_configuration_write.py` — `pytest.raises(ValueError)` around `surface.update_my_system_prompt` (~207) | verified |
| `mcp/server/mcpserver/exceptions.py` — `class ToolError(MCPServerError)`, `class MCPServerError(Exception)` | verified |
| `mcp/server/mcpserver/tools/base.py` — non-`ToolError` exceptions reduced to "Error executing tool <name>" | verified (Architect) |
| `the_one/mcp/client.py` `model_dump(mode="json")` at ~227, ~242, ~525, ~703, ~864 | verified |
| `mcp-server-editor.js` reads `info.websiteUrl` (~325) | verified |
| `tests/conftest.py::mcp_fixture_http_client` uses `httpx.ASGITransport` (~297) | verified |
| `tests/test_mcp_client.py` tripwire asserts `_PINNED_PROTOCOL_VERSION == mcp.types.LATEST_PROTOCOL_VERSION` (~53) | verified |
| `the_one/mcp/oauth/provider_factory.py:121` — `redirect_uris=[f"http://127.0.0.1:{settings.port}/api/oauth/callback"]` | verified |
| `packaging/windows/the-one.spec:75` — `collect_submodules("mcp", filter=… not mcp.cli)` | verified |
| `ci/tasks/windows-installer-build.yml` — runs the frozen `the-one doctor` as a build gate (~97-119) | verified |
| Python accepts `class X(ToolError, PermissionError)` / `class Y(ToolError, ValueError)` | verified (flight review, stand-in classes, Python 3.12) |

### Prerequisites
- [x] ~~`mcp` 2.3.0 and `mcp-types` 2.3.0 clear the 14-day soak at 2026-10-16 22:06 UTC~~ — soak waived by the operator, 2026-10-12 (DD10).
- [x] Worktree `../the-one-sortie-03` on branch `mission/29-mcp-2x-protocol`, based on `8193d5f`; rebased onto main before execution if main moves.
- [ ] A Cloudflare account for the operator (free tier) — for the `hat` leg. **Re-verified at the start of `hat`**, together with network access to `mcp.cloudflare.com` and the Windows `platform: windows` Concourse worker being up.
- [x] The Windows installer-build CI lane exists and runs the frozen doctor (`ci/tasks/windows-installer-build.yml`).

### Pre-Flight Checklist
- [x] All open questions resolved
- [x] Design decisions documented
- [x] Citation Audit complete — every code-asserting design decision verified
- [ ] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach
One implementation leg carries the atomic port, ordered so the suite returns to green as early as possible:
1. Bump pins and caps (DD10); regenerate the lock.
2. Port the servers (`surface.py`, `hello_server.py`, the app mount and the test mounts) to `MCPServer` (DD3) — this restores app import.
3. Port the client: `httpx2` (DD4), two-value unpacks and `MCPError` (DD7), session-property reads and the version gate (DD6), `by_alias` dumps and snake_case reads (DD5), the SSE-cap error (DD8).
4. Sign-in: the response hook and its translation (DD1), the issuer path (DD2), with a real-401 fixture and an issuer-advertising OAuth fixture.
5. Tests to real SDK models; the `httpx` guard; packaging (DD11); docs (`the_one/agents.md` MCP sections — including the stale "exact match" note in "MCP F2" item 5 — `SECURITY-MODEL.md` for DD9, `CLAUDE.md` only if an operator-facing fact changes).
6. Re-run the pool/teardown tests and the `requires_bwrap` set (Mission 07's anyio cancel-scope fragility; 2.x rewrote the session's task group).
7. Tests of DD9 clear `SSL_CERT_FILE`/`SSL_CERT_DIR` explicitly, since httpx2's trust-store choice depends on them (`httpx2/_config.py` ~32-41); `OTEL_PROPAGATORS` is unset in test runs (an unknown name raises at `import mcp`). The WSL run does not prove the Windows trust store — the Windows lane's doctor gate (DD11) does.
8. The `httpx` guard (DD4) is AST-based, so `import httpx2` is not flagged.

### Checkpoints
- [x] App imports and `make test-unit` is green on `mcp==2.3.0`
- [x] A real 401 fixture yields `MCPAuthRequired` with the `resource_metadata` URL on connect, `list_tools` and `call_tool`; a stale 401 from an earlier operation does not misfire
- [x] Provider-attached sign-in failure (mismatched issuer; token endpoint 400) surfaces as `MCPAuthRequired` end to end through `MCPClient.connect`; a sign-in that succeeds mid-operation followed by an ordinary JSON-RPC error does NOT yield `MCPAuthRequired`; stale-token recovery on Test connection observed
- [x] Issuer-advertising OAuth fixture: matching `iss` signs in; mismatched or missing `iss` fails plainly
- [x] Full browser suite (`make test-browser`: all lanes, including `shared` — the OAuth modal and callback tests — and `chats`) green; `requires_bwrap` set green
- [ ] Windows installer-build lane green (frozen doctor passes)
- [ ] Live Cloudflare sign-in passes on a dev instance

### Adaptation Criteria

**Divert if**:
- The SDK does not route requests through the provided client's hooks (DD1's premise fails) — re-plan sign-in detection (fallback candidate: run the bare probe before a no-provider connect).
- The 2.x session's teardown reintroduces the cross-task cancel-scope deadlock in a way the existing `_safe_cleanup` mitigations don't contain.

**Acceptable variations**:
- DD3's fallback (plain `ToolError` and three updated `ValueError` assertions), logged.
- Test expectations that change only for SDK shapes, each listed in the flight log with its reason.
- Additional `by_alias` or snake_case sites found during the port.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `sdk-port` - The atomic port to `mcp==2.3.0` at parity: DD1-DD10 and DD12's code, tests and docs; `make test-unit`, the full browser suite (`make test-browser`) and the `requires_bwrap` set green. (Soak waived, DD10.)
- [x] `packaging-and-doctor` - DD11: Windows packaging spec collection and metadata, the twelfth doctor gate `mcp sdk`, both Windows workflow needle lists, `tests/test_doctor.py`, `CLAUDE.md`'s gate list. *(Split out of `sdk-port` at leg design, 2026-10-12 — see flight log.)*
- [ ] `hat` - Live checks with the operator on a dedicated dev instance (prerequisites re-verified first): the Cloudflare sign-in (`tests/HAT.md` Tier 2), a legacy stdio server connecting and running a tool, and the Windows installer-build lane with the new doctor gate; fixes as needed.

---

## Post-Flight

### Completion Checklist
- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing
- [ ] Documentation updated

### Verification
- `make test-unit` green, with the expected skip count; `make test-browser` (all lanes) green under `THE_ONE_TEST_NETNS=1`; `pytest -m requires_bwrap` green.
- `pip-audit` clean; `uv.lock` resolves `mcp==2.3.0` and its new dependencies.
- Windows installer-build lane green, its doctor output including the new MCP gate line.
- `hat` leg: the Cloudflare sign-in completes end to end and its tools run; an MCP editor Test on a handshake-era server shows the same protocol, server details and tools as before the port.
- Flight log lists every test whose expected value changed, and every cache key that changed (DD5), with its reason.
