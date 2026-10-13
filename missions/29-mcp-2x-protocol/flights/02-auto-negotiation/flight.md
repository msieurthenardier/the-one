# Flight: Automatic negotiation of protocol 2026-07-28

**Status**: ready
**Mission**: [MCP servers connect on the newest protocol](../../mission.md)

## Contributing to Criteria
- [ ] A server that supports 2026-07-28 connects on it: its MCP editor shows "protocol 2026-07-28", and its tools list and run from an agent's chat (the operator's Sonos server).
- [ ] A server that supports only an older revision still connects on its revision over stdio and streamable HTTP, with every older revision proven on a real server. After its first successful connection it connects with no added delay the operator would notice. This flight owns the latency half and the per-revision proof; Flight 1 proved parity.
- [ ] Signing in to a remote MCP server that requires OAuth still works end to end, and the server's tools run afterwards: a re-run of the Cloudflare sign-in under negotiation, with a live tool run.
- [ ] An agent's self-configuration tools still work, and their refusals still read as a one-line reason. The loopback server negotiates 2026-07-28 after this flight.
- [ ] When a server shares no protocol revision with the-one, or a tool asks for input the-one cannot provide, the operator sees a plain one-line error. The oversized-event case was done in Flight 1.
- [ ] The Windows packaged build still builds and `the-one doctor` passes in it, now proving the full HTTP closure (`httpcore2`).
- [ ] The unit suite and the full browser suite pass, and every changed test expectation is listed with its reason.

---

## Pre-Flight

### Objective
Make the-one's MCP client negotiate the newest protocol automatically. It tries `server/discover` at 2026-07-28 and falls back to the initialize handshake, so a server that speaks 2026-07-28 connects on it and the editor says so. That covers the operator's Sonos server and the-one's own self-configuration loopback. Every older server keeps connecting on its own revision, with no added delay after its first successful connection.

The flight also closes the Flight 1 debrief's carry-forward items. They touch the same code (`MCPClient.connect`, the DD1 failure translation, the doctor gate and the Test-connection route), so they land here rather than as separate work.

### Open Questions
- [x] Re-implement the SDK's auto policy, or call the private `negotiate_auto`? → re-implement on the public `ClientSession` API (operator, 2026-10-12). See DD1.
- [x] How is the negotiated era remembered? → **in memory only**. The operator revised this after the design review found that every pre-existing saved `protocol_version` was written by a handshake-only client. See DD2.
- [x] What to do about the stale-token behaviour when a timeout follows a 401 (Flight 1)? → clear the stale OAuth secrets before offering a fresh sign-in (operator). Pre-Flight-1 parity: all four OAuth-managed keys. See DD7.
- [x] How to fix the RFC 8707 `resource` inconsistency between the SDK path and the-one's two flow drivers? → align the drivers (operator), using a version header rather than a discover body (design review). See DD10.
- [x] Squawk 0199 (stale MCP docs)? → folded into this flight (operator). See DD12.
- [x] How does a server that speaks only 2026-07-28 pass the auth-posture probe? → see DD9.
- [x] What does the operator see when a tool asks for input? → see DD8.
- [x] How is a real outer cancellation told apart from the SDK's internal cancel-scope fallout? → by task identity, not `cancelling()`. The design review's probe disproved the original premise. See DD6.

### Design Decisions

**DD1: Negotiation re-implemented on the public `ClientSession` API, behind one seam.**

`the_one/mcp/_negotiate.py::negotiate(session, *, remembered) -> str` replaces the `session.initialize()` call in `MCPClient.connect` (`the_one/mcp/client.py:411`). It follows mcp 2.3.0's private `mcp/client/_probe.py::negotiate_auto`:
- It calls `send_discover(LATEST_MODERN_VERSION)`, at most twice. The SDK's `LATEST_MODERN_VERSION` is read at call time, so the-one keeps no copy of the modern offer.
- **On -32022 (`UNSUPPORTED_PROTOCOL_VERSION`)**, it parses `UnsupportedProtocolVersionErrorData`.
  - On the first attempt, if there is a mutual modern version, it re-probes at that version.
  - If `supported` parses and lists no handshake version, it raises: a modern-only server with no shared version (see DD5).
  - If the data doesn't parse, it falls back to `initialize()` (`_probe.py:78`).
- **Any other `MCPError` falls back to `session.initialize()`.** That includes -32601, -32602, -32600, -32001 timeout, and the transport's synthesized errors for HTTP 4xx and 202. If that `initialize()` itself answers -32022, it re-probes discover once at a mutual version.
- **Exceptions that are not `MCPError` propagate**: transport errors, anyio errors and cancellation. They are never an era verdict.
- **A successful discover** is validated as `mcp.types.DiscoverResult`. A `ValidationError`, or no modern version in `supported_versions`, falls back to `initialize()`. Otherwise it calls `session.adopt(result)`.
- **The DD2 shortcut**: if `remembered` is a handshake revision, it calls `initialize()` directly. If that fails with an `MCPError` and the sign-in record shows no 401 since the shortcut began, it runs the full policy above in the same call.
  - "No 401" is checked by calling `_signin_record.auth_record_for(session)` and comparing against the sequence number taken just before the shortcut's `initialize()`. Within `connect` that baseline is 0.
  - A record of `None` means "no 401". That covers stdio, and every mock session.
  - So a shortcut `initialize()` answered 401 still raises `MCPAuthRequired` through matrix row 1 (DD5), instead of triggering the full policy.
- It uses only public names: `send_discover`, `initialize` and `adopt`; `mcp.types.DiscoverResult`, `UnsupportedProtocolVersionErrorData` and `UNSUPPORTED_PROTOCOL_VERSION`; and `mcp.types.version`. It returns `session.protocol_version`.

The SDK's fallback cases are ported as unit tests of `negotiate()` against an in-memory session.

The seam doubles as the test hook. `tests/test_mcp_client.py` uses `patch_transport` 111 times with a bare `MagicMock` session (`:176-182`). On that mock, `send_discover` returns something that isn't awaitable, so calling it raises `TypeError`. Those fixtures therefore gain `send_discover=AsyncMock(side_effect=MCPError(METHOD_NOT_FOUND, …))` and `adopt`, and existing tests keep exercising the handshake path. `test_mcp_wire_shapes.py::_fake_session` (`:135-150`) gets the same change.

- Rationale: the operator chose this. It keeps the error mapping in the-one's code, makes DD2's shortcut a natural branch, and depends on no private SDK module.
- Trade-off: the-one owns about 50 lines that must track the SDK's policy. A test pins the parity cases, and `the_one/agents.md` names the SDK function it mirrors.

**DD2: Era memory lives only in memory, per source.**

The operator decided this on 2026-10-12, after the design review.

- **Owner.** A new leaf module, `the_one/mcp/_era.py`, holds a process-wide `dict[source_id, str]`. Its functions are `era_for(source_id) -> str | None`, `remember_era(source_id, version)` and `forget_era(source_id)`, plus `_clear_for_test()` for an autouse fixture. That fixture is needed because about 110 `patch_transport` tests share fixed source ids.
- **Who reads and writes it.** The module is created in leg 1 (`client-hardening`), so leg 1 can implement DD5's `forget_era` cells. Leg 2 wires the reads and writes.
  - `MCPClient.connect` reads `era_for(self.source.id)` itself, so no caller has to pass an era in, and hands the value to `negotiate()`.
  - After a successful connect, it calls `remember_era(source.id, session.protocol_version)`. The one exception is a Test connection that used a body-override config: it records nothing, because the era belongs to an unsaved URL, not to `source.id`.
  - `MCPClient(..., fresh_negotiation=True)` ignores the map. The three Test-connection sites (`api.py:3321, 3416, 3644`) pass it, so a Test always re-discovers.
  - The pool (`_pool.py:228`) and the self-configuration path use the default.
- **The shortcut.**
  - A remembered handshake revision means `initialize()` directly, with no discover probe.
  - A remembered modern revision, or no entry, means the full policy.
  - A shortcut `initialize()` that fails runs the full policy (DD1). So a server that has since gone modern-only is re-discovered, not stuck.
- **Clearing.** `forget_era` runs on:
  - any failed connect;
  - Reset connection (`api.py:3279-3284`);
  - a source update (`update_mcp_source`, ~`api.py:3082`, which today keeps `_cache` even when the URL or command changes);
  - delete;
  - any mid-session -32022 (DD5, row 3).
- **Not used:** `source.config._cache.protocol_version`. Every source Tested before this flight holds "2025-11-25", written by a client that could only speak the handshake, so the value says nothing about the server's era. It remains a display value written by Test connection.
- Rationale: this meets "no noticeable added delay after the first successful connection" within a process, with no new persistence and no way to get stuck on a stale hint.
- Trade-off, accepted by the operator:
  - Each server pays one discover probe per app run. For real servers that takes milliseconds: a 1.x Python server answers discover at once, with HTTP 400 or stdio -32602. A server that silently ignores discover costs up to the 10 s timeout, once per run.
  - A server that adds 2026-07-28 while the app is running stays on the handshake until a restart, Reset connection, a source edit or a Test.

**DD3: Session metadata becomes fully era-agnostic, with the serverInfo de-dup.**

`MCPClient.connect` already reads `protocol_version`, `server_capabilities`, `server_info` and `instructions` from the session (`client.py:558-577`). The `_meta` read at `client.py:581` (`getattr(result, "meta", None)`) changes to `(session.initialize_result or session.discover_result).meta`, dumped by alias.

In the modern era, `_meta` carries the SDK's serverInfo stamp under `mcp.types.SERVER_INFO_META_KEY`. That key is dropped before caching, because the editor already shows the server info. If nothing remains after dropping it, `None` is stored rather than `{}`.

The mock-session helpers (`tests/test_mcp_client.py::_set_init` ~134-144 and `tests/test_mcp_wire_shapes.py::_fake_session` ~135-150) set `initialize_result` and `discover_result` explicitly. An unset attribute on a `MagicMock` is truthy, so it would otherwise be read as the result. Tests cover both eras.

**DD4: The version gate, the renamed constant and the tripwires.**

- **Version gate.** The post-connect gate (`client.py:553-561`) accepts `HANDSHAKE_PROTOCOL_VERSIONS + MODERN_PROTOCOL_VERSIONS`.
- **Constant.** `_PINNED_PROTOCOL_VERSION` (`the_one/mcp/__init__.py:12, 65`, used at `client.py:370/433/561` and `transports/streamable_http.py:260`) is renamed `_HANDSHAKE_OFFER_VERSION = "2025-11-25"`, read at call time. It feeds the auth-posture probe's `initialize` payload, and the two flow drivers' `initialize` payload and header (DD10). The modern offer comes only from the SDK (DD1). `tests/test_mcp_client.py:718-737`, which monkeypatches the old name, is updated.
- **Tripwires.** `tests/test_mcp_client.py:56` and `tests/test_mcp_wire_shapes.py:102-106` now pin `_HANDSHAKE_OFFER_VERSION == LATEST_HANDSHAKE_VERSION == "2025-11-25"` and `LATEST_MODERN_VERSION == "2026-07-28"`. The `LATEST_PROTOCOL_VERSION != _PINNED…` assertion is deleted.
- **Expected values that move to "2026-07-28".** Against the dual-era `hello_server`: `tests/test_mcp_integration.py:79, 170` and `tests/test_mcp_wire_shapes.py:78, 88`, each listed in the flight log. The raw-SDK `session.initialize()` assertions (`test_mcp_integration.py:27, 47`) stay as they are.

**DD5: Failure translation gets one shared classifier, keeps cleanup at the call sites, and follows a written matrix.**

- **What is shared.** `MCPClient._classify_failure(exc, *, op, baseline) -> Exception | None` builds the typed exception for the shared cases. Each method keeps its own `try`/`except`/`except*` structure and its own cleanup:
  - connect's 3-second `_safe_cleanup`;
  - abandoning the stack on `CancelledError`;
  - reading the sign-in record before cleanup (`client.py:434-473, 535-543`).

  The three `except* (OAuthFlowError, OAuthTokenError)` blocks (`:412, 701, 837`) can't move into a helper; only the construction of their `MCPAuthRequired` is shared.
- **The matrix.** First match wins. Today the arm order differs between `list_tools` and `call_tool`; the matrix fixes one order.

  | Order | Failure | `connect` | `list_tools` | `call_tool` |
  |---|---|---|---|---|
  | 1 | `UrlElicitationRequiredError` | pass through (**intended change**: today the generic arm wraps it, logged) | pass through (as today) | pass through (as today) |
  | 2 | The sign-in record shows a 401 since the baseline. Applies to `MCPError`, `BaseExceptionGroup`, `asyncio.TimeoutError`, `httpx2.HTTPError` / `anyio.ClosedResourceError` (which consult the record first today, `client.py:736, 882`), generic exceptions, and `CancelledError` (per DD6). | `MCPAuthRequired` | `MCPAuthRequired` | `MCPAuthRequired` |
  | 3 | Protocol-version rejection: any `MCPError(-32022)`, or `initialize()`'s `RuntimeError("Unsupported protocol version …")` | `MCPVersionMismatch` if no shared version; otherwise the policy re-probes (DD1) | mark dead; `forget_era`; `MCPVersionMismatch` if no shared version, otherwise `MCPConnectionError` ("the server changed protocol revision; reconnecting on the next call") | same as `list_tools` |
  | 4 | SSE cap: `MCPError(-32000)` whose message starts "SSE stream failed:" and contains "byte limit" | `MCPConnectionError` (cap text) | `MCPConnectionError` (cap text); not marked dead | `MCPCallError` (cap text); not marked dead |
  | 5 | Session terminated (existing `_is_session_terminated`) | — | `MCPConnectionError`; mark dead | `MCPConnectionError`; mark dead |
  | 6 | Input required (DD8). A result branch, not an exception: it is checked before the content is flattened, because `InputRequiredResult` has no `content`. | — | — | `MCPCallError` (plain line) |
  | 7 | Any other `MCPError` | `MCPConnectionError("MCP connect failed: …")` | `MCPConnectionError("MCP list_tools failed: …")` | `MCPCallError` |
  | 8 | `asyncio.TimeoutError` | `MCPConnectionError("MCP server did not respond within …")` | today's type and text | today's type and text |
  | 9 | `httpx2.HTTPError`, `anyio.ClosedResourceError` | `MCPConnectionError` | `MCPConnectionError`; mark dead | `MCPConnectionError`; mark dead |
  | 10 | Other exceptions and `BaseExceptionGroup` | `MCPConnectionError` (wraps, as today) | propagate unchanged | propagate unchanged |

  Rows 1-4 and 6 are the target behaviour. For every other cell, today's behaviour wins, and the leg logs any disagreement. Row 1 comes before row 2, as it already does in `list_tools` and `call_tool`.
- **Token-failure strings are a contract.** Test connection's `looks_like_token_failure` (`api.py:3720-3722`) string-matches "did not respond" and "cancelled during initialize" (`client.py:440, 470`; pinned at `tests/test_mcp_client.py:487, 518`). Both phrases stay byte-for-byte, pinned by a test that names them. That includes "during initialize", even though negotiation may now cancel during discover.
- **The no-shared-revision message.** `MCPVersionMismatch`'s message (`errors.py:19-22`) becomes "the-one supports 2024-11-05 through 2026-07-28", built from `mcp.types.version`. `observed` comes from the error's `supported` list when present. `.pinned` stays, holding `_HANDSHAKE_OFFER_VERSION`; `tests/test_mcp_client.py:451` pins it. The frontend keys only on the class name (`static/js/mcp-error.js:21-22`).

**DD6: Cancellation is translated only on the task that owns the transport.**

This replaces the original plan after the design review disproved its premise.

- **The premise that failed.** The planned `asyncio.current_task().cancelling() == 0` gate doesn't work.
  - anyio 4.15.1 delivers its own cancel-scope cancellation by calling `task.cancel()` on the host task (`anyio/_backends/_asyncio.py::_deliver_cancellation`).
  - So the SDK's internal fallout after a failed sign-in arrives as `CancelledError('Cancelled via cancel scope …')` with `cancelling() == 1`, which looks exactly like a real outer cancellation.
  - In the pool shape, where connect runs on a worker task and calls come from another task, the caller gets `MCPError(-32000, "Connection closed")` and no `CancelledError` at all.
  - Evidence: the probes `scratchpad/archprobe/cancelling2.py` and `crosstask.py`.
- **The rule.** `connect` records the task that entered the transport stack (`self._owner_task`). It is reset on every `connect` and cleared in `disconnect`, so a reconnected client never compares against a stale task.
  - A `CancelledError` caught on any other task can't be the transport's internal fallout, so it re-raises. That covers every pool tool call, and an agent turn cancelled while a sign-in is pending.
  - On the owner task, today's translation stays: a 401 in the record gives `MCPAuthRequired`; otherwise connect's existing F6 A5 handling applies.
- **Tests.** The existing `tests/test_mcp_signin_detection.py::test_failed_signin_flow_yields_auth_required_end_to_end` keeps passing. A new test cancels a `call_tool` issued from a different task than `connect`, with a 401 as the last response, and asserts `CancelledError` propagates.

**DD7: Test connection clears stale OAuth secrets before a fresh sign-in, as before Flight 1.**

- **The change.** In Test connection's Phase A, the `except MCPAuthRequired` branch (`api.py:3698`) also clears the four OAuth-managed secrets before falling through to Phase B: `dcr_credentials`, `access_token`, `refresh_token` and `token_expires_at` (`the_one/agents.md:763`). That is the same set `looks_like_token_failure`'s strip clears (`api.py:3720-3734`), so it restores pre-Flight-1 behaviour, including a fresh client registration on the next sign-in. The operator chose this ("clear them").
- **How it writes.** It re-reads the stored row, strips only those keys, and writes that row back. Separately, it strips the same four keys from the in-memory `source`'s `secrets` with `source.model_copy(update={"secrets": ...})`. It does **not** swap `source` for the stored row, because Phase B reads `source.config["url"]` and builds the provider from `source` (~`api.py:3755-3778`), so the sign-in must target the URL the operator is testing. It never writes from the request-body override, which can carry the operator's unsaved form values. The existing strip has exactly that flaw (`repo.update(source.model_copy(...))`, `api.py:3723-3734`), and this flight corrects it to the same re-read pattern.
- **Tests.** `tests/test_mcp_test_connection_stale_tokens.py` asserts the secrets are cleared; that changed expectation is logged. A new test sends a body override with an unsaved URL. It asserts that the stored row's non-secret config is unchanged after the clear, and that Phase B's consent flow targets the override URL.
- **Scope.** Only Test connection changes. The agent's pool path keeps raising `MCPAuthRequired` without touching the stored row, because the agent loop's consent flow overwrites the tokens on success.

**DD8: A tool asking for input gives a plain error.**

`MCPClient.call_tool` calls `session.call_tool(..., allow_input_required=True)`. When the result is an `mcp.types.InputRequiredResult`, it raises `MCPCallError` with `server_message` exactly "the server asked for extra input, which the-one can't provide yet". `MCPCallError` already prefixes "MCP tool '<name>' returned an error:", so the tool is named only once.

Today, the modern-era SDK `RuntimeError` ("Server returned InputRequiredResult; pass allow_input_required=True …", `session.py:1105-1106`) reaches the LLM verbatim through `agent/core.py:630-635`. The handshake-era cases ("Handler returned an invalid result", "Elicitation not supported") already read as `MCPCallError` and don't change.

A `hello_server` test tool returning `InputRequiredResult(request_state="x")` drives the modern case. `tests/test_mcp_client.py:1383` (`assert_awaited_once_with("t", {"x": 42})`) changes to include `allow_input_required=True`, and that change is logged.

**DD9: The auth-posture probe tolerates a server that speaks only 2026-07-28.**

This was revised after the design review.

- **Today.** `transports/streamable_http.py::_probe_auth_posture` (`:255-288`) posts a bare `initialize`. It returns `"error"` for anything except 200 or 401, including transport errors and timeouts (`:272-281`). Test connection's Phase 0 (`api.py:3606-3612`) then reports "connection probe failed" without trying the SDK. So a server that speaks only 2026-07-28, and rejects `initialize` with 400, can never be tested.
- **The change.**
  - The probe gains a fourth verdict, `"unexpected_status"`, for an HTTP response other than 200 or 401.
  - `"error"` stays for transport errors and timeouts, which keep failing fast, in about 5 s.
  - On `"unexpected_status"`, Phase 0 falls through to the no-auth SDK path. That path's "probe said no_auth … race" branch (~`api.py:3387`) turns `MCPAuthRequired` into `{"status":"error"}` today. When entered from this fall-through, it instead persists `auth_posture: "oauth"` and continues into Phase B's sign-in.
  - 401 → `"oauth"` and 200 → `"no_auth"` are unchanged.
- **Docs.** The probe's docstring is corrected once, in leg 3.

**DD10: The two OAuth flow drivers send the handshake version header.**

This keeps the RFC 8707 `resource` parameter consistent, and was revised after the design review.

- **The inconsistency.** The SDK's `OAuthClientProvider` records each request's `MCP-Protocol-Version` (`mcp/client/auth/oauth2.py:610-611`). `should_include_resource_param` (`:218-233`) sends `resource=<server URL>` to an authorization server without protected-resource metadata when that version is 2025-06-18 or later. With negotiation, the SDK path's first request, discover, carries 2026-07-28. But the-one's two flow drivers (`api.py:3780-3796` `_drive_flow_test`, `:4642-4663` `_drive_flow`) post a header-less `initialize` with a hard-coded "2025-11-25", so their sign-ins would omit `resource`.
- **The change.** Both drivers keep their `initialize` body, so a server of either era answers it with 401 before routing. They add `MCP-Protocol-Version: <_HANDSHAKE_OFFER_VERSION>`, and their payload reads the constant instead of the literal. Every sign-in the-one starts itself now includes `resource` for such servers (operator decision).
- **Rejected alternative.** A `server/discover` body from the drivers was rejected. Unlike the SDK path, the drivers have no fallback, so a server or gateway that rejects an unknown method with 400 before checking auth would never start sign-in.
- **Known remaining difference.** On DD2's handshake shortcut, the SDK sends `initialize` with no version header (`mcp/client/streamable_http.py:641-644`), so a 401 there still omits `resource`. This is accepted and documented.
- **Tests.** Both drivers' first request carries the header, and its payload uses the constant.
- **Trade-off.** An old authorization server that rejects an unknown `resource` would now fail on these paths too. No real one is known.

**DD11: The doctor gate proves the full HTTP closure.**

`the_one/diagnostics.py::_probe_mcp_sdk` (`:583-612`) also constructs and closes a synchronous `httpx2.Client()`, with no network. The probe is synchronous, and the async client's `aclose()` is a coroutine, so the sync client is the right choice. Constructing it forces the lazy `httpcore2` import, which the gate's current imports never load.

The detail line becomes `mcp 2.3.0, handshake 2025-11-25, modern 2026-07-28, httpcore2 <ver>`, with the version from `importlib.metadata.version("httpcore2")`. The Windows lanes' needle (`mcp sdk: OK`) is unchanged.

**DD12: Docs updated and squawk 0199 closed.**

- **Squawk 0199's remaining items:**
  - the `the_one/mcp/__init__.py:3` docstring, which still says "mcp==1.27.0";
  - the probe docstring (leg 3, DD9);
  - `CLAUDE.md:305`, which says the `requires_bwrap` set is 12 tests; it is now 41 passed and 3 skipped.

  The squawk's fourth item is already satisfied at `the_one/agents.md:1060`. The squawk is closed in this flight's commit.
- **References stale after DD4's rename:** `the_one/mcp/README.md` §5 (`:224-242`) and `:49`, and `the_one/agents.md:1050, 1057`.
- **`the_one/agents.md` gains:**
  - the negotiation policy and era memory (DD1, DD2);
  - modern connections have no session id, so their 404s read "Not Found" and never self-heal (Flight 1's DD12.3 now covers every modern connection);
  - the failure matrix (DD5);
  - the owner-task cancellation rule (DD6);
  - the stale-token clear (DD7);
  - the input-required error (DD8);
  - the probe verdicts (DD9);
  - the drivers' version header (DD10).
- **`CLAUDE.md`'s Mission 29 paragraph** gains the operator-facing facts: servers on 2026-07-28 show it, and older servers fall back automatically.

**DD13: Test servers that speak only older revisions prove every revision, and latency is proven structurally.**

`tests/fixtures/mcp/hello_server.py` serves both eras (stdio `serve_dual_era_loop`, HTTP header routing), so it can't prove fallback. These fixtures can:
- **stdio, fast error.** `hello_server.py --legacy-only[=<revision>]` drives 2.3.0's handshake-only `mcp.server.runner.serve_loop`, which answers discover with -32601 and falls back in milliseconds (verified in memory). The revision parameter sets what its `initialize` answers: 2024-11-05, 2025-03-26, 2025-06-18 or 2025-11-25.
  - **How.** 2.3.0's handshake server answers the client's requested version whenever that version is in its handshake set (`mcp/server/runner.py::_negotiate_initialize`, ~421-426). The client always requests 2025-11-25. So the fixture process patches the module globals `mcp.server.runner.HANDSHAKE_PROTOCOL_VERSIONS = (rev,)` and `LATEST_HANDSHAKE_VERSION = rev`. The design-review probe (`archprobe/oldrev.py`) connected, listed tools and called `echo` on 2024-11-05, 2025-03-26 and 2025-06-18.
  - **Limit, stated honestly.** This proves the client accepts each revision from a real 2.3.0 server labelled with it, not 1.x wire behaviour. Flight 1 proved the older revisions only with mocks. HAT step H4 covers real 1.x behaviour, on one revision.
- **stdio, silent drop.** A server middleware never answers `server/discover`. Tests patch `mcp.client.session.DISCOVER_TIMEOUT_SECONDS` low, since it is read at call time.
- **stdio, pipe close on discover.** The connect fails plainly as `MCPConnectionError`. This is accepted and documented: the policy can't respawn a process.
- **HTTP.** An ASGI wrapper modelled on `tests/fixtures/mcp/asgi_401.py::Auth401Wrapper` has three modes: a fast 400 carrying a 1.x-style JSON-RPC error body, a bare 404, and a silent drop. 2025-11-25 is proven on both transports.
- **Latency, checked structurally.** Each fallback test asserts that the second connect to the same source sends no `server/discover`, using a spy or a fixture counter. It also allows a generous bound on the second connect's time, relative to a plain handshake connect. An absolute stopwatch would flake on a loaded WSL host.
- **Existing tests that change.** `tests/test_mcp_signin_detection.py:64` adds `server/discover` to `fail_methods`. The OAuth stub's 202 reply to an authorized discover (`tests/fixtures/oauth/__init__.py:139-143`) makes it a fast-fallback legacy server, so its tests are checked.

**DD14: The HAT and how it is observed.**

- **Who acts, and where.** The operator, in their browser, on the dev instance already running from the worktree: port 8492, scratch data dir `…/scratchpad/hat-data`, holding their Cloudflare and Sonos sources. It is restarted on the flight's code first.
- **What is observed.**
  - The MCP editor's server-details line ("protocol …", from `GET /api/mcp-sources/{id}` → `config._cache.protocol_version`).
  - Test connection results.
  - Chat tool runs. The operator configures a provider on the dev instance for these.
- **The steps.**
  - **H1, Sonos.** Test shows "protocol 2026-07-28". A tool runs from chat, which goes through the pool and exercises DD2's in-memory map.
  - **H2, Cloudflare.** Sign-in under negotiation completes, and a tool runs from chat.
  - **H3, stale tokens.** This is Flight 1's V3, now run live. With Cloudflare's tokens revoked by the operator, Test clears the stored sign-in (DD7) and offers a fresh consent URL. Signing in recovers.
  - **H4, a real 1.x server.** An stdio server running `mcp==1.28.1`, an `uvx`-launched fixture the leg provides, connects on its handshake revision and a tool runs. This is the one live check of the "1.x answers discover fast" premise, which was read from source but never run.
  - **H5, Windows.** The installer-build lane re-run shows `mcp sdk: OK — …, modern 2026-07-28, httpcore2 …`.
- **What the automated suite proves instead.**
  - The latency criterion, structurally, including the silent-drop worst case (DD13).
  - Every older revision on a real server (DD13).
  - The self-configuration loopback resolving its caller in the modern era. The existing real-client tests in `tests/test_self_configuration_surface.py` cover this, and they now negotiate 2026-07-28.

### Citation Audit

Verified against the worktree at `307ad22` and the installed `mcp` 2.3.0 sources (reconnaissance and design review; see the flight log):

| Citation | Status |
|---|---|
| `the_one/mcp/client.py:411` `session.initialize()`; `:581` `meta_val = getattr(result, "meta", None)` | verified |
| `client.py:553-561` version gate on `HANDSHAKE_PROTOCOL_VERSIONS` | verified |
| `client.py`: 11 `_auth_required_since` call sites, 3 SSE-cap arms, 2 session-terminated arms, 3 `except*` OAuth blocks; arm order differs between `list_tools` and `call_tool` | verified |
| `client.py:743-750, 889-895` translate `CancelledError` | verified |
| `client.py:440, 470` texts string-matched by `api.py:3720-3722`, pinned at `tests/test_mcp_client.py:487, 518` | verified (design review) |
| DD6 premise: anyio 4.15.1 delivers cancel-scope cancellation via `task.cancel()` on the host task (`cancelling() == 1`); cross-task callers see `MCPError(-32000)` | verified (design-review probes `archprobe/cancelling2.py`, `crosstask.py`) |
| `mcp/client/_probe.py::negotiate_auto` policy, including `:78`'s fallback on unparseable -32022 data | verified (installed 2.3.0) |
| `ClientSession.send_discover(version) -> dict`, `initialize()`, `adopt(result)`, `initialize_result`/`discover_result`/`protocol_version` are public | verified |
| `mcp.client.session.DISCOVER_TIMEOUT_SECONDS = 10.0`, read at call time | verified (monkeypatch probe) |
| 1.28.1 answers a pre-init discover with HTTP 400 + JSON-RPC body (stateful and stateless) and stdio -32602 | verified by reading the 1.28.1 source; not run. H4 runs it live |
| 2.3.0 `serve_loop` (handshake-only) answers discover with -32601 | verified (in-memory probe) |
| Modern HTTP: every request is a POST with `accept: …text/event-stream`; no GET stream, no `Mcp-Session-Id`; the DD1 hook records discover and modern POSTs | verified (probe against the-one's transport) |
| `mcp/client/streamable_http.py:641-644` clears the version header on `initialize` | verified (design review) |
| `api.py:3321, 3416, 3644` Test-connection `MCPClient` sites; `_pool.py:228` pool site | verified |
| `api.py:3698` (`except MCPAuthRequired`) runs before `:3704-3735` (`looks_like_token_failure` strip, which writes from the possibly-overridden `source`) | verified |
| OAuth-managed MCP secrets: `dcr_credentials`, `access_token`, `refresh_token`, `token_expires_at` (`the_one/agents.md:763`) | verified |
| `transports/streamable_http.py:255-288` probe; `"error"` covers transport errors and timeouts (`:272-281`); `api.py:3606-3612` Phase 0 short-circuit; ~`api.py:3387` no-auth path turns `MCPAuthRequired` into an error | verified (design review) |
| `mcp/client/auth/oauth2.py:610-611` header capture; `:218-233` `should_include_resource_param` | verified |
| `api.py:3780-3796`, `:4642-4663` flow drivers post a header-less `initialize` with "2025-11-25" (`:3791`, `:4658`) | verified |
| `diagnostics.py:583-612`; `httpcore2` loads only once a client is built; `httpx2.Client().close()` also loads it | verified (probes) |
| `session.call_tool` raises `RuntimeError("Server returned InputRequiredResult …")` unless `allow_input_required=True` | verified (probe) |
| `tests/test_mcp_client.py:176-182` bare `MagicMock` session; `patch_transport` 111 uses | verified |
| `tests/test_mcp_signin_detection.py:64` `Auth401Wrapper(fail_methods={"initialize"})` | verified |
| DD13 older-revision fixture: patching `mcp.server.runner.HANDSHAKE_PROTOCOL_VERSIONS`/`LATEST_HANDSHAKE_VERSION` in the fixture process makes 2.3.0's handshake server answer that revision (`runner.py::_negotiate_initialize` ~421-426) | verified (design-review probe `archprobe/oldrev.py`: 2024-11-05, 2025-03-26, 2025-06-18) |
| DD6 pool shape: `_pool.py::_entry_worker` only runs `connect()`; `list_tools` runs on the agent-build task (`_tool_provider.py` ~312), `call_tool` on the agent's task (`_tool.py::execute` ~163) | verified (design review, cycle 2) |
| Self-configuration modern-era caller stamp: `_streamable_http_modern.py` passes `ServerMessageMetadata(request_context=request)` → `runner.py::_make_context` | verified by source; runtime proof by the existing real-client tests |

### Prerequisites
- [x] Flight 1 merged (`06e1e39`) and debriefed (`307ad22`). The worktree is on `flight/02-auto-negotiation`, cut from merged main.
- [x] The worktree `.venv` is synced from `uv.lock` (`mcp` 2.3.0). No dependency change is planned.
- [x] The dev instance on 8492 is running with the operator's Cloudflare and Sonos sources. It is restarted on the flight's code before the HAT, since Python changes need a restart.
- [ ] **Re-verified at the start of `hat`:**
  - the operator has a model provider to configure on the dev instance;
  - Cloudflare and the Sonos server are reachable;
  - `uvx` can fetch `mcp==1.28.1` for H4;
  - `fly -t the-one` login and the Windows worker are available for H5.

### Pre-Flight Checklist
- [x] All open questions resolved
- [x] Design decisions documented
- [x] Citation Audit complete: every code-asserting design decision verified
- [ ] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach
Three code legs and a HAT.

1. **`client-hardening`.** Lands the carry-forwards on the handshake era, so the suite stays green throughout.
   - DD5: the classifier, the matrix, the contract pin and the mismatch wording. The -32022 and mid-session rows are tested through mock sessions.
   - DD6: the owner-task rule.
   - DD7: the stale-token clear with the override-safe re-read, including the fix to the existing strip.
   - DD8: the input-required error. The modern-era case is tested through a mock session.
   - DD11: the doctor gate.
   - DD12: squawk 0199's items, except the probe docstring.

   - `the_one/mcp/_era.py` (DD2) is created here, so the `forget_era` cells of DD5 row 3 exist. Nothing reads it until leg 2.

   `connect` still calls `initialize()`. Suites green.
   - Interim state, logged in the flight log: `.pinned` still holds `_PINNED_PROTOCOL_VERSION` until leg 2's rename, and the mismatch message names 2026-07-28 before the client offers it.
2. **`auto-negotiation-core`.** Switches the client to negotiation.
   - DD1: `_negotiate.py`.
   - DD2: reads and writes of `_era.py`, `fresh_negotiation`, and clearing in the client.
   - DD3.
   - DD4: the rename, the tripwires, the expected values that move to 2026-07-28, and the mock fixtures.
   - DD8's real modern-era fixture.
   - DD13: the fixtures, every revision, and the structural latency checks.

   Suites green, and the self-configuration loopback on 2026-07-28.
3. **`auto-negotiation-api`.** Adapts the web routes.
   - DD9: the fourth probe verdict and the fall-through into Phase B.
   - DD10: the drivers' version header.
   - DD2's clearing on update, delete and Reset in `api.py`.
   - The probe docstring.
   - DD12's negotiation docs: `the_one/agents.md`, `the_one/mcp/README.md` and `CLAUDE.md`.

   Full browser suite and `requires_bwrap` green. The bwrap rejection path now meets discover first, so this leg confirms it still holds.
4. **`hat`.** H1-H5 with the operator (DD14).

### Checkpoints
- [ ] Shared failure classifier and matrix; owner-task cancellation rule; override-safe stale-token clear; input-required plain error; doctor proves `httpcore2`; unit suite green
- [ ] Negotiation lands; `hello_server` and the self-configuration loopback report 2026-07-28; every older revision proven on a real fixture; every legacy-only fixture falls back; the second connect sends no discover
- [ ] Probe fall-through into sign-in; drivers' version header; full browser suite and `requires_bwrap` green
- [ ] HAT H1-H5

### Adaptation Criteria

**Divert if**:
- A real server the operator uses (Sonos, Cloudflare, an stdio server) fails under negotiation in a way the policy can't fall back from. One example is a server that closes its HTTP connection on discover. Re-plan, possibly adding a per-source "handshake only" setting, which would be a new operator-facing control.
- Translating cancellation only on the owner task (DD6) leaves a real sign-in failure undetected in some pool shape the tests don't cover.

**Acceptable variations**:
- Passing a smaller per-call discover timeout instead of the SDK default, if a test shows the 10 s worst case matters.
- More expected values moving to 2026-07-28 than DD4 lists, or matrix cells that differ from today's code (DD5), each logged.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [ ] `client-hardening` - Flight 1 carry-forwards on the handshake era: the shared failure classifier and matrix, the owner-task cancellation rule, the override-safe stale-token clear, the input-required plain error, the doctor gate proving `httpcore2`, and squawk 0199's docs.
- [ ] `auto-negotiation-core` - The negotiation policy behind one seam; in-memory era memory; era-agnostic metadata with the serverInfo de-dup; the version gate; the constant rename and re-pinned tripwires; fixtures for every older revision; the structural latency tests.
- [ ] `auto-negotiation-api` - Web routes: the probe's fourth verdict and fall-through into sign-in, the flow drivers' version header, era clearing on update, delete and reset, and the negotiation docs; full browser and bwrap suites.
- [ ] `hat` - With the operator on the 8492 dev instance: H1 Sonos on 2026-07-28 with a chat tool run, H2 Cloudflare sign-in plus a tool run, H3 live stale-token clear, H4 a real 1.x server, H5 Windows lane re-run.

---

## Post-Flight

### Completion Checklist
- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing
- [ ] Documentation updated

### Verification
- `make test-unit` green in plain mode, with the skip count explained.
- `make test-browser` green across all lanes, under `THE_ONE_TEST_NETNS=1`.
- `pytest -m requires_bwrap` green, and ruff clean.
- New and changed tests named in the flight log, including every expected value that moved to 2026-07-28 and why.
- `hat` H1-H5 as DD14 lists them.
