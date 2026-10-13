# Leg: sdk-port

**Status**: completed
**Flight**: [Port to the mcp 2.x SDK at parity](../flight.md)

## Objective
Move the-one from `mcp==1.28.1` to `mcp==2.3.0` in one atomic change: the MCP client, its OAuth sign-in, the self-configuration loopback server, the MCP test fixtures, and the docs for DD1-DD10 and DD12. Every server still connects on the initialize handshake exactly as today, apart from the four deliberate changes in the flight's DD8 and DD12. DD11 (packaging and the doctor gate) is the next leg, `packaging-and-doctor`.

## Context
- **The flight spec's DD1-DD12 are the design.** Read `../flight.md` in full before starting. This leg implements every DD except DD11, which is leg 02. Where this file and the flight spec disagree, the flight spec wins; report the disagreement in the flight log.
- **The port is atomic.** `mcp` 1.x and 2.x share a distribution name. 2.x's `mcp.server.fastmcp` is a stub that raises `ModuleNotFoundError`, so `the_one/interfaces/web/app.py`'s import of `the_one/self_configuration/surface.py` fails the moment the pin flips. Nothing is green again until the servers are ported.
- **The soak is waived** by the operator (flight log, Flight Director Notes; DD10 as rewritten). Pin `mcp==2.3.0` now. Add no soak caps.
- **Automatic negotiation of 2026-07-28 is Flight 2's work, not this leg's.** `MCPClient.connect` keeps calling `session.initialize()`. Do not call `discover()` or `negotiate_auto`.
- **Where the evidence is:**
  - The flight log's "Code Interrogation" and "Design Review" sections hold the evidence behind each DD.
  - Extracted 2.3.0 sources sit under `/tmp/claude-1000/-home-cprch-projects-the-one/875c2e63-eac8-4b6b-9502-e3cecc18639d/scratchpad/` (`mcpwheel-2.3.0/x/mcp`, `mcptypes/x/mcp_types`) for reading.
  - Once the pin is installed, read the installed package in `.venv` instead.
- **Out of scope, do not touch:** `the_one/llm/` (including `anthropic_oauth.py`, which is LLM-provider OAuth, not MCP), web fetch, and the rest of the app's `httpx` use.

## Inputs
- Worktree `/home/cprch/projects/the-one-sortie-03`, branch `flight/01-port-to-mcp-2x`, with a `.venv` synced from `uv.lock` (`mcp` 1.28.1).
  - **Always install from the lock**, never with a fresh resolve. `uv pip install -e` alone resolves fresh; it drifted `openai` to 3.29.0 and failed 5 baseline tests (flight log).
- Baseline: `make test-unit` in plain mode (no `THE_ONE_TEST_NETNS`) on the unchanged, lock-synced tree. Result: 6019 passed, 12 skipped, 0 failed (flight log, Flight Director Notes).

## Outputs
- Code and tests ported. `pyproject.toml` and `uv.lock` updated.
- Docs updated:
  - `the_one/agents.md`: the MCP F2 Client Foundation, MCP error translation and MCP source secrets storage sections, plus any OAuth contract text that names the `(code, state)` tuple.
  - `the_one/mcp/README.md`.
  - `SECURITY-MODEL.md`: DD9 trust store, plus the DD12 issuer and redirect notes.
  - `CLAUDE.md`: any operator-facing fact that changed. The doctor gate list belongs to leg 02.
- The flight log's `sdk-port` entry lists every test whose expected value changed and every cache key that changed (DD5), each with a reason. It also records each internal checkpoint as it goes green.

## Acceptance Criteria
- [x] AC1: `pyproject.toml` pins `mcp==2.3.0` with a comment recording the operator's soak waiver, replacing the stale "1.28.1 closes PYSEC-…" comment, plus an explicit `httpx2>=2.10.0`.
  - `uv.lock` is regenerated, and its diff moves nothing unrelated to the `mcp` bump.
  - The worktree `.venv`, synced from the lock, has `mcp` 2.3.0 and `mcp-types` 2.3.0.
  - `pip-audit` reports no known vulnerability in `mcp`, `mcp-types`, `httpx2`, `httpcore2`, `truststore` or `opentelemetry-api`.
- [x] AC2: `python -c "import the_one.interfaces.web.app"` succeeds. No Python **code** under `the_one/` or `tests/` imports `mcp.server.fastmcp` or `mcp.shared.version`, or uses `McpError`. Code means imports and names, checked by AST or a code-only grep, not prose.
  - Comments that name `McpError` or `FastMCP` are updated to the 2.x names, for example `transports/stdio.py` ~497/578/597, `client.py` ~620-632/766-768 and `tests/test_mcp_stdio_error_translation.py:113`.
- [x] AC3 (DD3): the self-configuration surface and `tests/fixtures/mcp/hello_server.py` run on `mcp.server.mcpserver.MCPServer`.
  - **Factory:** a single surface app factory in `surface.py` builds the mounted app with `stateless_http=True, streamable_http_path="/"`. Both `app.py` and the test mount in `tests/test_self_configuration_surface.py` call it.
  - **Session-manager lifecycle:**
    - `mcp` stays a module attribute;
    - the factory is called exactly once per module instance;
    - the lifespan reads `session_manager` only after the factory has run.

    `app.py`'s lifespan guard and the surface test's `importlib.reload` pattern keep working.
  - **Refusal classes:** refusals raise two module-level classes, one subclassing `(ToolError, PermissionError)` and one `(ToolError, ValueError)`, each always called with one argument.
  - **Refusal-parity audit:** under 2.x, any non-`ToolError` exception that escapes a tool is reduced to "Error executing tool <name>" with no text.
    - Audit every tool body, and what each calls in `manage`, `pending`, `revisions`, the agent store and the projection builders. The tools are `get_my_configuration`, `describe_my_capabilities`, `update_my_description` and `update_my_system_prompt`.
    - Find exceptions that reached the client with a user-meaningful reason under 1.x. Convert each to the matching refusal class with the same text, or record in the flight log that none was meant to reach the client.
  - **Request context:** `ctx.request_context.request` is still the Starlette `Request` with `.scope` under `stateless_http=True`; `surface.py` ~76 depends on it. Verify this at checkpoint 1.
  - **Tests:** `tests/test_self_configuration_write.py` and `tests/test_self_configuration_surface.py` pass with no change to their refusal assertions. A refusal reaching a real client reads `Error executing tool <name>: self-configuration: …`, with the same text as before.
- [x] AC4 (DD4): every file under `the_one/mcp/` uses `httpx2`, not `httpx`; that includes `_probe_auth_posture`. The two OAuth flow drivers in `the_one/interfaces/web/api.py` use `httpx2.AsyncClient`, while `api.py` keeps `httpx` for its non-MCP uses (~5416-5631). `tests/conftest.py::mcp_fixture_http_client` uses `httpx2.ASGITransport`.
  - A new AST-based unit test fails on any `import httpx` / `from httpx …` under `the_one/mcp/`, and does not flag `httpx2`.
  - `the_one/llm/` and the rest of the app are unchanged.
- [x] AC5 (DD5): every `model_dump` on an SDK model in `the_one/mcp/` uses `by_alias=True`, and attribute reads are snake_case. `api.py` forwards the client's cache and does no dump of its own.
  - A test asserts that the cached `server_info` and capabilities and an agent-facing tool result keep camelCase keys (`websiteUrl`, `mimeType`, `structuredContent`/`isError` where present).
  - The `MagicMock` result fixtures in `tests/test_mcp_client.py` that set camelCase attributes are replaced by real `mcp.types` model instances.
- [x] AC6 (DD6, DD7):
  - `MCPClient` reads the protocol version, capabilities, server info and instructions from `session.protocol_version` / `server_capabilities` / `server_info` / `instructions`.
  - The post-connect version gate uses `mcp.types.version.HANDSHAKE_PROTOCOL_VERSIONS`.
  - `_PINNED_PROTOCOL_VERSION` stays `"2025-11-25"`, and the tripwire test is re-pinned to `mcp.types.version.LATEST_HANDSHAKE_VERSION`.
  - A real connection to `hello_server`, over stdio and over the ASGI fixture, reports `negotiated_protocol_version == "2025-11-25"`. The 2.x server serves both eras, so this proves the client's `initialize()` still lands on the handshake era.
  - The session-terminated tripwire drives a real 404 with a session id set.
- [x] AC7 (DD1), each proven by a test against a real HTTP server (the extended OAuth fixture or the ASGI 401 wrapper, step 4), never an injected `HTTPStatusError`:
  - (a) A no-provider 401 with `WWW-Authenticate: Bearer resource_metadata="…"` yields `MCPAuthRequired(resource_metadata_url=…)` from `connect`, `list_tools` and `call_tool`.
  - (b) A 401 recorded during an earlier operation does not turn a later unrelated failure into `MCPAuthRequired`.
  - (c) With a provider attached, a sign-in that succeeds mid-operation followed by an ordinary JSON-RPC error does not yield `MCPAuthRequired`.
  - (d) With a provider attached, a sign-in flow that fails (a mismatched issuer, and a token endpoint answering 400) yields `MCPAuthRequired` end to end through `MCPClient.connect`.
  - (e) A 401 on an auth-flow request (token or DCR POST) or on the GET stream is not recorded.
  - (f) The hook is present on the production, override-seam and factory client branches, in both `connect_streamable_http` and `_open_streamable_http_transport_stack`, and the seam client's hook is removed on exit.
- [x] AC8 (DD1, stale tokens): a test drives Test connection's stale-token recovery (`api.py::looks_like_token_failure` → clear stale tokens → Phase B) through a refresh-token failure against a real fixture, and observes the recovery.
- [x] AC9 (DD2):
  - `GET /api/oauth/callback` forwards an optional `iss`; `oauth/_state.py::resolve` carries it; `oauth/handlers.py::callback_handler` returns `AuthorizationCodeResult(code, state, iss)`.
  - With an authorization server advertising `authorization_response_iss_parameter_supported`: a matching `iss` signs in, while a mismatched or missing `iss` fails.
  - A registration stored by 1.x (no `issuer`) still loads.
- [x] AC10 (DD8):
  - The transport passes `max_sse_event_size` from a named the-one constant equal to 1 MiB.
  - An oversized event on a tool call yields `MCPCallError` with a one-line message naming the limit, and the client is not marked dead. Test it with `echo` and a string over 1 MiB.
  - The same event during `list_tools` yields `MCPConnectionError` with that message. Produce it with a test-only `hello_server` switch that registers a tool whose description exceeds 1 MiB.
  - The match is code -32000 with a message that starts "SSE stream failed:" and contains "byte limit". A different -32000 error is not matched, and a test proves it.
- [x] AC11 (DD12):
  - The inert `follow_redirects: True` is dropped from `_build_production_httpx_kwargs`.
  - A cross-origin redirect on the MCP path fails with a plain `MCPConnectionError` (test).
  - `the_one/agents.md` records all four accepted behaviour changes, including the stateless-404 self-heal note.
- [x] AC12 (DD9): `SECURITY-MODEL.md` documents the OS trust store on the SDK path and the `SSL_CERT_FILE`/`SSL_CERT_DIR` override. Tests that touch TLS or trust settings clear those variables explicitly.
- [x] AC13: the following all pass:
  - `make test-unit`, plain mode, the same as the baseline. The skip count matches the baseline's 12, or each difference is explained in the flight log. Iterate with `-x`.
  - `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python TEST_TIMEOUT=3600 bash scripts/run-tests.sh --parallel 3 --tb=short` (all browser lanes).
  - `.venv/bin/python -m pytest -m requires_bwrap -x --timeout 120` (12 tests).
  - `ruff check` and `ruff format --check` on `the_one/ tests/ scripts/`.
- [x] AC14: the flight log's `sdk-port` entry lists every test whose expected value changed and every cache key that changed, each with its reason. The leg status is `landed`.

## Verification Steps
- AC1: `grep -n 'mcp==\|httpx2' pyproject.toml`; `git diff uv.lock`, reviewed for unrelated moves; `.venv/bin/python -c "from importlib.metadata import version as v; print(v('mcp'), v('mcp-types'), v('httpx2'), v('openai'))"` (openai stays 2.32.0); `uvx pip-audit` against the venv.
- AC2: the import command, plus an AST or code-only check for the three names.
- AC3-AC11: the named tests pass. Each new test is named in the flight log.
- AC12: read the docs diff.
- AC13: the four commands, with exit codes recorded in the flight log. Also review `grep -rn "api\.httpx\." tests/` for patch-target drift.

## Implementation Guidance

Work through five internal checkpoints, and record each in the flight log as it goes green.

1. **Pins** (DD10):
   - Set `mcp==2.3.0` and `httpx2>=2.10.0`, then run `uv lock`. Check the lock diff for unrelated upgrades.
   - Sync `.venv` from the lock: `uv export --frozen --extra all-llms --extra dev --no-hashes --no-emit-project -o <tmp>/req.txt && VIRTUAL_ENV=$PWD/.venv uv pip sync <tmp>/req.txt && VIRTUAL_ENV=$PWD/.venv uv pip install --no-deps -e .`.
   - Confirm the installed versions.
2. **Servers first** (DD3). **Checkpoint 1: the app imports and `tests/test_self_configuration_*` is green.**
   - Port `surface.py`: the factory, the refusal classes, the refusal-parity audit and the session-manager lifecycle.
   - Port its mount in `app.py`, the test mount, and `hello_server.py`. Move `transport_security` to `streamable_http_app(...)` at every call site, and add the test-only switches from step 4 and AC10.
   - Check that `tests/test_mcp_sandbox_integration.py::test_register_naughty_tools_in_process` (~717, unit tier) still holds. It reads `app._tool_manager.list_tools()`, which exists on `MCPServer`.
3. **Client** (DD4, DD7, DD6, DD5, DD8). **Checkpoint 2: the unit suite is green apart from the sign-in tests.**
   - httpx2 throughout `the_one/mcp/`, including `_probe_auth_posture`.
   - `api.py` gains `import httpx2` for the two OAuth flow drivers (~3782, ~4642).
   - Two-value unpacks.
   - `MCPError`.
   - Session-property reads and the handshake version gate.
   - `by_alias` dumps and snake_case reads.
   - The explicit SSE cap constant and its translation.
4. **Sign-in** (DD1, DD2). **Checkpoint 3: AC7-AC9 are green.**
   - The hook, the sequenced record and the side table (`auth_record_for(session)`, `_auth_required_since(baseline)`).
   - Translation on every failure that happens after a request is sent, reading the record before `connect` clears `self._session`.
   - The issuer path through the route, the state and the handler.

   **The existing fixtures don't cover this.** `_OAuthASHandler` serves its 401 only on `GET /mcp`, has no `POST /mcp`, and answers 404 on `/.well-known/oauth-protected-resource`. No test uses `OAuthASStub` today. The ASGI `hello_server` fixture has no 401 path. Build:
   - **OAuth fixture modes** in `tests/fixtures/oauth/__init__.py`:
     - `POST /mcp` answering 401 with `WWW-Authenticate: Bearer resource_metadata="…"`;
     - protected-resource metadata;
     - authorization-server metadata that advertises `authorization_response_iss_parameter_supported`, and returns, omits or mismatches `iss`;
     - a token endpoint that answers 400;
     - a stateful mode for AC7c: 401 first, then after sign-in a 200 carrying an ordinary JSON-RPC error;
     - an in-process way to complete the redirect and callback, through `the_one.mcp.oauth._state.resolve`, so `MCPClient.connect` finishes.
   - **An ASGI wrapper** (or middleware) around the `hello_server` app. It accepts `initialize`, then answers a chosen later MCP POST with 401 and `WWW-Authenticate`. This serves AC7(a) on `list_tools`/`call_tool`, and AC7(b).
5. **Remaining tests.** **Checkpoint 4: the full unit suite is green.**
   - Real `mcp.types` models in `test_mcp_client.py`, and the AST httpx guard.
   - Work through this breakage checklist, adding each item to the flight log's changed-expectations list:
     - `tests/test_mcp_connection_reset.py:452` and `tests/test_oauth_test_connection_endpoint.py:288`, `:491` patch `the_one.interfaces.web.api.httpx.AsyncClient` (`_StubHttpxClient`). Retarget them to `...api.httpx2.AsyncClient`; otherwise they silently stop intercepting.
     - `tests/test_mcp_transport_timeouts.py`: `isinstance(timeout, httpx.Timeout)` and `httpx.BasicAuth` move to httpx2.
     - `tests/test_auth_posture_probe.py` patches `transport_mod.httpx.AsyncClient` with a MockTransport factory; it moves to httpx2 types.
     - `tests/test_mcp_integration.py`: its own `streamable_http_client` three-value unpacks (~12-14) and `init_result.protocolVersion`.
     - `tests/test_mcp_oauth_integration.py`: httpx types, and the synthetic `HTTPStatusError` (A9) replaced by the real-fixture tests.
     - The OAuth tuple-shape tests: `tests/test_oauth_handlers.py`, `tests/test_oauth_state.py`, `tests/test_oauth_callback_route.py`.
     - `tests/test_mcp_stdio_test_connect.py` and `tests/test_mcp_sandbox_integration.py`: FastMCP prose, and the escape tools' strerror text (DD3).
6. **Docs, then full verification.** **Checkpoint 5: AC13 passes.**
   - Docs: `the_one/agents.md`, `the_one/mcp/README.md`, `SECURITY-MODEL.md` (DD9, DD12), and `CLAUDE.md` where an operator-facing fact changed.
   - Re-run the pool and teardown tests and the `requires_bwrap` set. 2.x rewrote the session's task group, and Mission 07's cross-task cancel-scope issue lives there.

## Edge Cases
- **The seam client is shared across connections in one test.** Add the hook on entry and remove exactly that hook on exit, never by clearing the list.
- **A 401 whose body is a JSON-RPC error** comes through as the server's own `MCPError` code. DD1 must not gate on `INTERNAL_ERROR`.
- **`connect`'s `CancelledError` / `_safe_cleanup` branches** set `self._session = None`. Read the auth record first.
- **`OTEL_PROPAGATORS`** in the environment can make `import mcp` raise. Keep it unset in tests, and don't add a dependency on it.
- **`ClientSession` must stay hashable and weakly referenceable.** If 2.3.0 breaks that, a WeakKeyDictionary is the wrong structure: stop and report `[BLOCKED:dd1-side-table]`.
- **If DD1's premise fails**, meaning the SDK doesn't send through the provided client's hooks, stop and report `[BLOCKED:dd1-hook-premise]`. That is a flight divert condition.
- **If 2.x teardown reintroduces the cross-task cancel-scope deadlock** and the existing `_safe_cleanup` mitigations don't contain it, stop and report `[BLOCKED:teardown]`.

## Files Affected
- `pyproject.toml`, `uv.lock`
- `the_one/mcp/__init__.py`, `client.py`, `errors.py` (only if needed), `_pool.py` (only if needed), `_tool.py`, `_tool_provider.py`, `transports/streamable_http.py`, `transports/stdio.py` (comments), `oauth/provider_factory.py`, `oauth/handlers.py`, `oauth/_state.py`, `README.md`
- `the_one/self_configuration/surface.py`
- `the_one/interfaces/web/app.py` (the surface mount)
- `the_one/interfaces/web/api.py` (the OAuth callback route and the OAuth flow drivers)
- Test fixtures: `tests/conftest.py`, `tests/fixtures/mcp/hello_server.py` (test-only switches), `tests/fixtures/oauth/__init__.py` (new modes), and a new ASGI 401 wrapper
- Test files: the MCP, OAuth and self-configuration tests (step 5 checklist), plus new ones for the httpx guard, the DD1 and DD2 real-fixture tests, and the DD8 cap tests
- `the_one/agents.md`, `SECURITY-MODEL.md`, `CLAUDE.md`
- The flight log

## Citation Audit
- **Flight design:** every DD citation was verified against `8193d5f` (the flight spec's Citation Audit, two Architect cycles). The flight branch is `86c93dc`, which adds planning artifacts only and changes no code.
- **Design review:** re-checked, then corrected by the leg's Developer design review (approve with changes, applied).
  - The `the_one/mcp/` modules that import `httpx` are `client.py`, `oauth/provider_factory.py` and `transports/streamable_http.py`. `oauth/storage.py` mentions httpx only in a comment (~42), and `transports/stdio.py` has none.
  - The three `api.httpx.AsyncClient` patch sites are confirmed.
  - `_OAuthASHandler`'s routes are confirmed: `GET /mcp` 401 only, no `POST /mcp`, protected-resource metadata 404.
  - `tests/test_anthropic_oauth.py` uses `httpx` for LLM-provider OAuth and is out of scope.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
