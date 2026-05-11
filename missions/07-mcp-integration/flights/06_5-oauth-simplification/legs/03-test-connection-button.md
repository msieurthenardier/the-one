# Leg: 03-test-connection-button

**Status**: landed
**Flight**: [OAuth simplification + Test connection button](../flight.md)

## Objective

Add a Test connection button to the Studio MCP source-edit page that drives a connect + list_tools probe end-to-end, kicking the OAuth flow at source-creation time when needed via a popup-callback dance — so subsequent agent builds register real tools instead of graceful-degrade-skipping on `MCPAuthRequired`.

## Context

L0 + L1 ripped out the manual-OAuth surface; L2 closed the auth-on-`tools/list` gap by translating 401 to `MCPAuthRequired` and making `MCPToolProvider.get_tools_for_agent` graceful-skip on it. The combined posture: an OAuth-protected source attached to an agent with no tokens skips cleanly at agent build, surfacing a WARNING log line. But the operator has no UI path to authenticate — they'd have to invoke an agent, hit the 401, run the chat-path lazy-OAuth, then the agent rebuild, etc. Friction.

L3 closes the gap with a Test connection button on each source's edit page. The button POSTs to a new endpoint `POST /api/mcp-sources/{id}/test/connect`, which:
- **Phase 1** — if `secrets["dcr_credentials"]` and tokens present, try `MCPClient.connect()` + `list_tools()` and return `{status: "ok", tools: [...]}` (or `{status: "error"}`). If creds absent OR connection raises `MCPAuthRequired`, build an OAuth provider with a *test-mode* `redirect_handler` that resolves a `consent_url_future` instead of broadcasting via WebSocket; kick `_drive_flow` as a background task; await the future with a 15-second timeout; return `{status: "auth_required", consent_url: "..."}`.
- **Phase 2** — UI opens `consent_url` in a popup window. User completes consent; popup hits `/api/oauth/callback` (existing endpoint, no changes); SDK's `callback_handler` resolves; `_drive_flow` exchanges code for tokens via `MCPSourceTokenStorage.set_tokens` (existing F5 path). Popup renders "Login successful" HTML.
- **Phase 3** — UI listens for popup-closed event; on close, re-POSTs `/test/connect`. Backend now has tokens → connect + list_tools succeeds → returns `{status: "ok", tools: [...]}`.

Per flight Design Decision §6, this requires extending BOTH `make_oauth_handlers` (`handlers.py:39`) AND `build_oauth_provider_for_source` (`provider_factory.py:58`) with an optional keyword-only `consent_url_future: asyncio.Future[str] | None = None` parameter that threads through. When present, the redirect_handler resolves the future after registering the state token (and before the existing chat-WS broadcast, which is a no-op for the synthetic chat_session_id `f"test:{source_id}"` because the broadcast is already guarded by `if session is not None`).

L4 (Tier-2 HAT against live Cloudflare API MCP) verifies this end-to-end. L3 ships the autonomous code; L4 is the human verification leg.

Key learnings from prior legs (flight log + L0/L1/L2):

- **`make_oauth_handlers` async-context constraint**: per `handlers.py:19-25`, the factory calls `asyncio.get_running_loop().create_future()` synchronously, which raises `RuntimeError` outside an async context. The Test endpoint is an `async def` route handler — the test harness must construct the future inside an async-test body.
- **Synthetic `chat_session_id = f"test:{source_id}"` is safe**: the existing chat-WS broadcast at `handlers.py:91-102` does `_sessions.get(chat_session_id)` and guards on `if session is not None:`. A synthetic csid like `"test:abc123"` returns None (real csids are 12-char uuid4-hex per `api.py:1156`) so the broadcast is a no-op. The synthetic csid also flows through `_state.register` and `/api/oauth/callback`'s `entry.chat_session_id` lookup, which also no-ops on lookup-miss.
- **Pool eviction is required**: per `oauth_start`'s pattern at `api.py:1007`, `await _evict_all_for_source(source_id)` runs after token persistence so subsequent `acquire` calls reconstruct `MCPClient` with the freshly-populated `dcr_credentials`. The Test endpoint must do the same to honor the F4 cache invariant.
- **`/api/oauth/callback` requires no changes**: the synthetic-csid flows through `entry.chat_session_id` lookup (returns None), the `_send_to_session` call is guarded, and `_state.resolve(state, code, state)` works identically. The endpoint is at `api.py:820-935` (per the existing source).
- **L2's `MCPAuthRequired` translation is the trigger**: when `MCPClient.list_tools()` 401s, L2 raises `MCPAuthRequired` instead of `MCPConnectionError`. The Test endpoint catches `MCPAuthRequired` to fall through to Phase 1's OAuth-flow path. Without L2, the Phase 1 fall-through wouldn't fire on auth-on-tools/list servers.
- **Test button is edit-mode only**: a brand-new (create-mode) source has no `id` yet. The Test endpoint takes `{id}` in its path, so the button must hide in create-mode and appear only after the source is saved. Per flight Adaptation Criteria, the button placement default is "below the save button, in its own section."

## Inputs

What exists before this leg runs:

- Branch `flight/6_5-oauth-simplification` with L0 + L1 + L2 landed (uncommitted)
- `the_one/mcp/oauth/handlers.py:39-116` — `make_oauth_handlers` factory; current signature has 4 positional/keyword args (`chat_session_id`, `source_id`, `tool_call_id`, `resource_metadata_url`)
- `the_one/mcp/oauth/provider_factory.py:58-135` — `build_oauth_provider_for_source` factory; current signature has 4 positional + 4 keyword args (`source`, `repo`, `chat_session_id` are positional + `source_id`, `tool_call_id`, `resource_metadata_url` are keyword); calls `make_oauth_handlers` at line 99
- `the_one/interfaces/web/api.py:937-1053` — existing `/oauth/start` endpoint (the production caller of `build_oauth_provider_for_source` for non-test paths); the Test endpoint reuses much of this pattern with two key differences: synthetic csid + `consent_url_future` instead of WebSocket broadcast wait
- `the_one/interfaces/web/api.py:820-935` — `/api/oauth/callback` (no changes; synthetic-csid path no-ops cleanly)
- `the_one/interfaces/web/api.py:715-830` — existing `/api/mcp-sources` CRUD (GET/POST/PUT/DELETE); the new `/test/connect` POST goes here, alongside the CRUD endpoints
- `the_one/mcp/_pool.py:248` — `_evict_all_for_source(source_id)` async function (the same one `oauth_start` calls)
- `the_one/mcp/client.py::MCPClient` — F6.5 L2-extended `list_tools` raises `MCPAuthRequired` on 401; the Test endpoint depends on this translation
- `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js` — has Save/Back buttons in the editor's button row (~line 59-61); has Danger Zone block in edit-mode (line 117-121); has `wireEditorEvents` (line 126) that wires button click handlers
- `tests/test_oauth_start_endpoint.py` — existing test pattern for endpoints that call `build_oauth_provider_for_source`; new endpoint tests follow this file's conventions (or join it)
- `tests/test_oauth_handlers.py` — existing test pattern for `make_oauth_handlers`; new test for the `consent_url_future` parameter joins this file
- `tests/test_oauth_provider_factory.py` — existing test pattern for `build_oauth_provider_for_source`; new test for the threaded `consent_url_future` joins this file
- `tests/browser/test_oauth_modal_flow.py` (post-L1, 4 standard-flow tests remain) — pattern for browser tests against the in-repo OAuth fixture; new browser test for popup-flow joins this file (or a new `test_mcp_test_connection_button.py`)

## Outputs

What exists after this leg completes:

- `make_oauth_handlers` accepts an optional keyword-only `consent_url_future: asyncio.Future[str] | None = None`; when supplied, the redirect_handler resolves the future with the `authorization_url` after registering the state token. Default `None` preserves the existing chat-flow behavior.
- `build_oauth_provider_for_source` accepts the same optional `consent_url_future` parameter, threads it to `make_oauth_handlers`. Default `None` preserves the existing call shape; existing callers (`oauth_start`, `_pool._entry_worker`) unchanged.
- New endpoint `POST /api/mcp-sources/{id}/test/connect` registered at `api.py` (placement: contiguous to the `/api/mcp-sources` CRUD block, around line ~830, BEFORE the `/oauth/callback` endpoint). Behavior matches the flight Technical Approach §L3 spec.
- `mcp-server-editor.js` renders a Test connection button + result panel in the editor's edit-mode (NOT create-mode); `handleTestConnection` async function POSTs to `/test/connect`, handles `ok` / `auth_required` / `error` responses, opens consent popup with `window.open`, listens for popup close, re-POSTs.
- 6 new unit tests:
  1. `make_oauth_handlers` with `consent_url_future`: redirect_handler resolves the future with the authorization_url
  2. `build_oauth_provider_for_source` with `consent_url_future`: factory threads the kwarg through to `make_oauth_handlers`
  3. `/test/connect` 404 when source missing
  4. `/test/connect` Phase A (creds + tokens present): returns `{status: "ok", tools: [...]}` against an in-repo OAuth fixture; verify Phase A threads `auth_provider` through to `MCPClient`
  5. `/test/connect` Phase B (no creds): returns `{status: "auth_required", consent_url}` after the SDK kicks the flow
  6. `/test/connect` consent_url_timeout: monkeypatch `_TEST_CONNECT_TIMEOUT` to a short value (e.g. 0.5s); SDK never calls redirect_handler; endpoint returns `{status: "error", error: "consent_url_timeout"}`
- 1 new browser test: end-to-end popup-flow against the in-repo OAuth fixture (which auto-consents). The test seeds an MCP source via API, opens the editor, clicks Test, verifies the popup opens, verifies the button is disabled while the popup is open, simulates the auto-consent + popup close, verifies the second POST returns tools, verifies the result panel renders the tool list and the button is re-enabled.
- All retained pytest suites pass under `docker exec the-one pytest --ignore=tests/test_mcp_pool.py` (modulo pre-existing failures L0/L1/L2 documented).

## Acceptance Criteria

- [ ] `make_oauth_handlers` signature includes `*, consent_url_future: asyncio.Future[str] | None = None` as keyword-only with default None; existing 4 args unchanged
- [ ] `build_oauth_provider_for_source` signature includes the same kwarg; threads it to `make_oauth_handlers` at `provider_factory.py:99`
- [ ] When `consent_url_future` is None (existing call sites), behavior is byte-identical to pre-L3 — `oauth_start`'s and `_pool._entry_worker`'s production paths unchanged
- [ ] When `consent_url_future` is supplied AND not done, the redirect_handler calls `consent_url_future.set_result(authorization_url)` AFTER `_state.register` (per flight Design Decision §6 ordering — register BEFORE resolve so the callback handler can `_state.peek` immediately)
- [ ] When `consent_url_future` is supplied AND already done (e.g. resolved by a prior call), the redirect_handler does NOT raise — it MUST guard with `if not consent_url_future.done():` (defensive against double-resolve from SDK retries)
- [ ] New endpoint `POST /api/mcp-sources/{source_id}/test/connect` returns:
  - `404 {"detail": "MCP source not found"}` if `source_id` does not exist
  - `{status: "ok", tools: [...]}` if `secrets["dcr_credentials"]` AND `secrets["access_token"]` present and `MCPClient.connect()` + `list_tools()` succeed (Phase A path; Phase A builds an OAuth provider with `consent_url_future=None` and threads it as `auth_provider` to `MCPClient` so cached tokens are actually applied)
  - `{status: "auth_required", consent_url}` if creds absent OR `list_tools()` raises `MCPAuthRequired` (per L2's translation) AND the SDK's PRM/OASM/DCR discovery succeeds within `_TEST_CONNECT_TIMEOUT` seconds (15s default, monkeypatchable via the module-level constant for tests)
  - `{status: "error", error: "..."}` for other failures: `MCPConnectionError` (including connect-time 401 per Design Decision §3 deferring to F7), `MCPVersionMismatch`, non-streamable-http source, OAuth-flow failure during discovery, `consent_url_timeout`
  - On the `auth_required` path: a background `asyncio.Task` is registered into `_inflight_resume_tasks` and runs the SDK auth flow until it either resolves (popup callback delivers code) or fails. The task is dispatched but not awaited — the endpoint returns after the future resolves with the consent_url.
- [ ] On `auth_required`, the endpoint calls `await _evict_all_for_source(source_id)` BEFORE the future completes — so the F4 pool cache is busted at the same time the OAuth flow surfaces the consent URL. (Mirror the timing of `oauth_start`'s eviction at line 1007.) AND on the Phase A → Phase B fallthrough (i.e. expired token in `MCPAuthRequired`), eviction runs immediately after the `except MCPAuthRequired:` clause (BEFORE Phase B builds the new provider) so the pool can't hand out a cached client carrying the expired auth provider.
- [ ] Endpoint timeout: a module-level constant `_TEST_CONNECT_TIMEOUT: float = 15.0` is defined in `api.py` (placement: near other module-level constants). The await on `consent_url_future` uses `asyncio.wait_for(..., timeout=_TEST_CONNECT_TIMEOUT)`; on timeout returns `{status: "error", error: "consent_url_timeout"}`. The 15-second ceiling is from Design Decision §2; tests monkeypatch the constant via `monkeypatch.setattr(api_mod, "_TEST_CONNECT_TIMEOUT", 0.5)` to drive the timeout path quickly.
- [ ] **Concurrent-Test guard**: the UI MUST disable the Test connection button while a test is in flight (i.e. between the click and either the `{status: "ok"}` / `{status: "error"}` final response, OR the popup-close re-Test settling). Re-clicking before the in-flight POST resolves would create a second `consent_url_future` and a second `_drive_flow_test` task, with the second `_state.register` shadowing the first; the first popup's callback would resolve the wrong flow. Implementation: set `testBtn.disabled = true` at click; restore via `testBtn.disabled = false` only after the final state lands (success / error / popup-flow-completed). NOT after the auth_required first response — the popup-flow chain MUST keep the button disabled until the second POST completes.
- [ ] Test button visibility: rendered only when `source.id` is truthy (edit-mode); create-mode shows nothing. Test selector: `[data-testid="mcp-test-connection"]` for the button; `[data-testid="mcp-test-result"]` for the result panel.
- [ ] Frontend `handleTestConnection(sourceId)` async function:
  - POSTs to `/api/mcp-sources/${sourceId}/test/connect`, parses JSON
  - On `status: "ok"`: renders the tools list in the result panel (one row per tool, format implementer's choice — minimum: tool name and description)
  - On `status: "auth_required"`: opens a popup with `window.open(consent_url, 'mcp-oauth-consent', 'width=600,height=700')`, sets up `setInterval(() => { if (popup.closed) { clearInterval(...); handleTestConnection(sourceId); } }, 500)` for popup-close detection, re-POSTs
  - On `status: "error"`: renders the error message in the result panel
- [ ] Browser test verifies the end-to-end popup-flow against the in-repo OAuth fixture (NOT live Cloudflare — that's L4): auto-consent fixture lands tokens; second POST returns tools; result panel renders. The fixture should be the same one F5 uses (`tests/browser/test_oauth_modal_flow.py` references it; identify by reading that file's setup).
- [ ] No existing endpoint or test broken — `oauth_start`, `oauth_callback`, `oauth_modal` standard-flow tests all still pass.
- [ ] Test runs:
  ```
  docker exec the-one pytest tests/test_oauth_handlers.py tests/test_oauth_provider_factory.py tests/test_oauth_start_endpoint.py tests/test_oauth_test_connection_endpoint.py -v --tb=short
  docker exec the-one pytest -m 'not browser and not live and not pixel' --ignore=tests/test_mcp_pool.py --tb=short -q
  docker exec the-one pytest -m browser tests/browser/test_oauth_modal_flow.py tests/browser/test_flow_studio_mcp_editor.py tests/browser/test_mcp_test_connection_button.py -v --tb=short
  ```
  All exit 0 (modulo pre-existing failures).

## Verification Steps

How to confirm each criterion is met:

- **Signature checks**:
  ```bash
  grep -A 10 "def make_oauth_handlers" the_one/mcp/oauth/handlers.py
  grep -A 12 "def build_oauth_provider_for_source" the_one/mcp/oauth/provider_factory.py
  ```
  Both should show the new kwarg with `*` keyword-only marker and `= None` default.

- **Endpoint registration**:
  ```bash
  grep -n "/test/connect" the_one/interfaces/web/api.py
  ```
  Should show the new `@router.post("/mcp-sources/{source_id}/test/connect")` decorator.

- **Endpoint smoke (post-`make rebuild`)**:
  ```bash
  # 404 path
  curl -X POST http://localhost:8484/api/mcp-sources/nonexistent/test/connect
  # → 404
  
  # Seed a source with no creds, then test:
  curl -X POST http://localhost:8484/api/mcp-sources -H 'Content-Type: application/json' \
    -d '{"name":"test-mcp","type":"streamable-http","config":{"url":"https://invalid.example.com/mcp"}}'
  # → 201 with id
  curl -X POST http://localhost:8484/api/mcp-sources/<id>/test/connect
  # → {"status": "error", "error": "..."} OR {"status": "auth_required", consent_url} depending on the URL's behavior
  ```

- **UI smoke**: open `http://localhost:8484/#studio/mcp-sources/new`; confirm no Test button visible. Save a streamable-http source; confirm Test button appears in edit-mode. Click; confirm result panel renders something (either an error message or the tools list).

- **Test runs**: see Acceptance Criteria.

- **No regression in standard OAuth flow**: `docker exec the-one pytest tests/test_oauth_start_endpoint.py tests/test_oauth_callback_route.py tests/test_oauth_handlers.py -v` exits 0.

## Implementation Guidance

The leg has 4 logical pieces. Order matters — the factory extension comes first because the endpoint depends on the kwarg threading.

### Step 1: Extend `make_oauth_handlers` with `consent_url_future`

Open `the_one/mcp/oauth/handlers.py`. Update the function signature:

```python
def make_oauth_handlers(
    chat_session_id: str,
    source_id: str,
    tool_call_id: str | None,
    resource_metadata_url: str | None,
    *,
    consent_url_future: asyncio.Future[str] | None = None,
) -> tuple[
    Callable[[str], Awaitable[None]],
    Callable[[], Awaitable[tuple[str, str | None]]],
]:
```

Update the docstring at lines 48-67 to document the new parameter (~3 sentences):

```
When ``consent_url_future`` is supplied, the redirect_handler resolves it
with the authorization_url AFTER registering the state token (preserving
the register-BEFORE-resolve invariant from the existing closure-capture
contract). The Test connection endpoint (F6.5 L3) supplies this future
and awaits it to surface the consent_url to the source-edit UI without
requiring a chat WebSocket subscription.
```

Inside the `redirect_handler` body (around lines 71-102), add the `consent_url_future` resolution AFTER `_state.register` and BEFORE the chat-WS broadcast:

```python
async def redirect_handler(authorization_url: str) -> None:
    """SDK-provided callback. Parse state, register, broadcast."""
    qs = parse_qs(urlsplit(authorization_url).query)
    states = qs.get("state", [])
    state = states[0] if states else None
    if not state:
        raise OAuthFlowError("Authorization URL missing state parameter")
    # Register BEFORE resolving state_box so the callback handler
    # can _state.peek immediately upon awaiting.
    _state.register(
        state,
        source_id=source_id,
        tool_call_id=tool_call_id,
        chat_session_id=chat_session_id,
    )
    if not state_box.done():
        state_box.set_result(state)
    # F6.5 L3: surface authorization_url to the test-connection endpoint
    # if the caller supplied a future (test path); production chat path
    # passes None and falls through to the WebSocket broadcast below.
    # Guard `done()` defensively — SDK retries could call redirect twice.
    if consent_url_future is not None and not consent_url_future.done():
        consent_url_future.set_result(authorization_url)
    # Lazy import — see module docstring.
    from the_one.interfaces.web.app import _send_to_session, _sessions
    
    session = _sessions.get(chat_session_id)
    if session is not None:
        await _send_to_session(...)
```

The order is: `_state.register` → `state_box.set_result` → `consent_url_future.set_result` → WebSocket broadcast. The first three must complete before the broadcast in case the chat-WS recipient is the same process that submitted the test request — preserving the `_state.peek`-before-broadcast invariant from the existing pattern.

### Step 2: Extend `build_oauth_provider_for_source`

Open `the_one/mcp/oauth/provider_factory.py`. Update the function signature:

```python
def build_oauth_provider_for_source(
    source: MCPSource,
    repo: MCPSourceRepository,
    chat_session_id: str | None,
    source_id: str | None = None,
    tool_call_id: str | None = None,
    resource_metadata_url: str | None = None,
    *,
    consent_url_future: asyncio.Future[str] | None = None,
) -> httpx.Auth | None:
```

Note: per L0's strip, the function body has only ONE auth-shape branch (the standard `OAuthClientProvider`). Thread `consent_url_future` to `make_oauth_handlers` at line ~99:

```python
redirect_handler, callback_handler = make_oauth_handlers(
    chat_session_id=chat_session_id,
    source_id=sid,
    tool_call_id=tool_call_id,
    resource_metadata_url=resource_metadata_url,
    consent_url_future=consent_url_future,  # NEW
)
```

Update the docstring at lines 66-82 to document the new kwarg (~2 sentences):

```
``consent_url_future`` is forwarded to ``make_oauth_handlers``; when
supplied, the redirect_handler resolves it with the authorization_url.
The F6.5 L3 Test endpoint uses this; production chat paths pass None.
```

### Step 3: New endpoint `POST /api/mcp-sources/{source_id}/test/connect`

Open `the_one/interfaces/web/api.py`. Find the `/api/mcp-sources` CRUD block (around lines 715-830). Add the new endpoint AFTER the DELETE handler. The endpoint structure mirrors `oauth_start`'s pattern at lines 937-1053:

```python
@router.post("/mcp-sources/{source_id}/test/connect")
async def test_mcp_connection(source_id: str) -> dict[str, Any]:
    """Connect + list_tools probe; kicks OAuth flow if needed via popup-callback dance.
    
    Behavior:
      - 404 if source not found
      - {status: "ok", tools: [...]} if connect + list_tools succeed
      - {status: "auth_required", consent_url} if creds absent or
        MCPAuthRequired raised; SDK's auth flow runs as a background
        task waiting for /oauth/callback to deliver the code
      - {status: "error", error} for other failures (transport, version
        mismatch, non-streamable-http source, consent_url_timeout)
    
    Two-call dance: UI POSTs once; on auth_required opens a popup, waits
    for popup close, re-POSTs. The second POST hits the {status: "ok"}
    path because tokens have landed via the SDK's callback_handler.
    
    F6.5 L3 — see flight artifact Design Decision §2 for the protocol.
    """
    from the_one.interfaces.web.app import _inflight_resume_tasks
    from the_one.mcp._pool import _evict_all_for_source
    from the_one.mcp.client import MCPClient
    from the_one.mcp.errors import MCPAuthRequired, MCPConnectionError, MCPVersionMismatch
    from the_one.mcp.oauth import build_oauth_provider_for_source
    
    repo = await _mcp_repo()
    try:
        source = await repo.get(source_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"MCP source not found: {source_id}")
    
    if source.type != "streamable-http":
        return {"status": "error", "error": f"Test only supports streamable-http; got {source.type!r}"}
    
    # Phase A: tokens present → build provider WITH consent_url_future=None
    # (test path doesn't kick the OAuth flow yet) and try connect + list_tools.
    # MUST thread auth_provider through MCPClient or the SDK has no way to
    # apply the cached tokens — bare MCPClient sends Bearer-less requests
    # and always 401s, defeating the "tokens present" fast path.
    if (
        source.secrets.get("dcr_credentials")
        and source.secrets.get("access_token")
    ):
        provider_a = build_oauth_provider_for_source(
            source,
            repo,
            f"test:{source_id}",
            source_id=source_id,
            tool_call_id=None,
            resource_metadata_url=None,
            consent_url_future=None,  # Phase A doesn't kick a flow
        )
        try:
            async with MCPClient(source=source, auth_provider=provider_a) as client:
                tools = await client.list_tools()
            return {
                "status": "ok",
                "tools": [
                    {
                        "name": t.name,
                        "description": t.description,
                        "input_schema": t.input_schema,
                    }
                    for t in tools
                ],
            }
        except MCPAuthRequired:
            # Token expired/revoked. Bust pool cache BEFORE Phase B builds
            # a fresh provider — otherwise the F4 cache may hand out an
            # MCPClient with the stale auth_provider and the SDK gets
            # confused mid-refresh. Mirrors oauth_start's eviction timing.
            await _evict_all_for_source(source_id)
            # fall through to Phase B
        except (MCPConnectionError, MCPVersionMismatch) as e:
            # Per Design Decision §3, F6.5 defers connect-time 401
            # translation to F7. So a `connect()` 401 surfaces here as
            # MCPConnectionError ("cancelled during initialize") and
            # the operator sees a generic error. The Test button is
            # functional for list_tools-401 servers (Cloudflare API MCP,
            # most production OAuth MCPs); connect-401 servers will need
            # F7's typed-diagnostic widening for clean Test-button UX.
            return {"status": "error", "error": f"{type(e).__name__}: {e}"}
    
    # Phase B: kick OAuth flow with consent_url_future
    consent_url_future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
    test_csid = f"test:{source_id}"
    
    provider = build_oauth_provider_for_source(
        source,
        repo,
        test_csid,
        source_id=source_id,
        tool_call_id=None,
        resource_metadata_url=None,
        consent_url_future=consent_url_future,
    )
    if provider is None:
        # No dcr_credentials yet AND chat_session_id was None per
        # provider_factory's short-circuit. With test_csid supplied,
        # the only way provider is None is dcr_credentials absent —
        # which means the SDK will run DCR on the upcoming POST. So
        # this branch is unreachable when test_csid is supplied.
        # Defensive return:
        return {"status": "error", "error": "OAuth provider construction failed"}
    
    await _evict_all_for_source(source_id)
    
    server_url = source.config.get("url", "")
    
    async def _drive_flow_test() -> None:
        """Hit the source URL with the provider attached; SDK runs auth flow."""
        try:
            async with httpx.AsyncClient(auth=provider, timeout=30.0) as client:
                await client.post(
                    server_url,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-11-25",
                            "clientInfo": {"name": "the-one", "version": "0.1"},
                            "capabilities": {},
                        },
                    },
                )
        except Exception:
            if not consent_url_future.done():
                consent_url_future.set_exception(
                    RuntimeError("auth flow failed before consent_url surfaced")
                )
    
    task = asyncio.create_task(_drive_flow_test())
    _inflight_resume_tasks.add(task)
    task.add_done_callback(_inflight_resume_tasks.discard)
    
    try:
        consent_url = await asyncio.wait_for(
            consent_url_future, timeout=_TEST_CONNECT_TIMEOUT
        )
    except asyncio.TimeoutError:
        return {"status": "error", "error": "consent_url_timeout"}
    except Exception as e:
        return {"status": "error", "error": f"auth_flow_error: {e}"}
    
    return {"status": "auth_required", "consent_url": consent_url}
```

Add a module-level constant at the top of `api.py` (placement: with other module-level constants near the top of the file, after imports). This constant is monkeypatchable from tests:

```python
# F6.5 L3: Test connection endpoint timeout (seconds). Bounds the await
# on consent_url_future so a slow / hanging SDK auth flow doesn't pin
# the request indefinitely. 15s is the Design Decision §2 ceiling;
# tests monkeypatch this to drive the timeout path quickly.
_TEST_CONNECT_TIMEOUT: float = 15.0
```

Confirm the import of `httpx` exists at top of `api.py` (it should, per `oauth_start` already using it). If not, add it.

### Step 4: UI — Test connection button + result panel

Open `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js`. Find the Danger Zone block (around lines 115-121). Add a Test connection block ABOVE the Danger Zone, also gated on edit-mode (`!isCreate`), but REQUIRING `streamable-http` type:

```javascript
// ── Test Connection (edit only, streamable-http only) ─────────────
if (!isCreate && (source && source.type === 'streamable-http')) {
  html += '<div class="editor-section mcp-test-section">';
  html += '<div class="section-title">Test Connection</div>';
  html += '<button type="button" class="btn-outlined-cyan" data-testid="mcp-test-connection">Test connection</button>';
  html += '<div class="mcp-test-result" data-testid="mcp-test-result" hidden></div>';
  html += '</div>';
}
```

Inside `wireEditorEvents` (~line 126; find the function body and locate where Save/Back/Delete are wired), add the Test button click handler:

```javascript
var testBtn = container.querySelector('[data-testid="mcp-test-connection"]');
if (testBtn) {
  testBtn.addEventListener('click', function () {
    handleTestConnection(source.id, container);
  });
}
```

Define `handleTestConnection` (a new function inside the same IIFE module scope, near the other helper functions). **MUST use `Promise.then()` chains, NOT `async/await`** — the entire `mcp-server-editor.js` module uses Promise-chain style; introducing `async function` would diverge from the file's convention and possibly break under any future transpilation pipeline. Use the local `escapeHtml` alias convention from line 132.

```javascript
function handleTestConnection(sourceId, container, testBtn) {
  var escapeHtml = window.App.escapeHtml;
  var resultEl = container.querySelector('[data-testid="mcp-test-result"]');
  resultEl.hidden = false;
  resultEl.textContent = 'Testing connection...';
  testBtn.disabled = true;  // concurrent-Test guard
  
  function settle() {
    testBtn.disabled = false;  // re-enable on final state
  }
  
  fetch('/api/mcp-sources/' + encodeURIComponent(sourceId) + '/test/connect', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  })
    .then(function (resp) { return resp.json(); })
    .then(function (data) {
      if (data.status === 'ok') {
        var html = '<div class="test-success">Connected. Tools (' + data.tools.length + '):</div>';
        html += '<ul class="test-tools-list">';
        for (var i = 0; i < data.tools.length; i++) {
          var t = data.tools[i];
          html += '<li><strong>' + escapeHtml(t.name) + '</strong>';
          if (t.description) {
            html += ': ' + escapeHtml(t.description);
          }
          html += '</li>';
        }
        html += '</ul>';
        resultEl.innerHTML = html;
        settle();
      } else if (data.status === 'auth_required') {
        // Keep button disabled across popup-flow; re-enabled only when
        // the Phase 2 re-POST settles (in this same function).
        resultEl.textContent = 'Opening consent popup...';
        var popup = window.open(
          data.consent_url, 'mcp-oauth-consent', 'width=600,height=700'
        );
        if (!popup) {
          resultEl.textContent = 'Popup blocked — please allow popups and retry.';
          settle();
          return;
        }
        var interval = setInterval(function () {
          if (popup.closed) {
            clearInterval(interval);
            // Phase 2 re-POST. Recursive call handles its own settle().
            handleTestConnection(sourceId, container, testBtn);
          }
        }, 500);
      } else {
        resultEl.textContent = 'Error: ' + (data.error || 'unknown');
        settle();
      }
    })
    .catch(function (err) {
      resultEl.textContent = 'Network error: ' + err.message;
      settle();
    });
}
```

The `settle()` closure helper exists so every terminal branch (ok, error, popup-blocked, network error, OR popup-close → recursive Phase 2) re-enables the button exactly once. The auth_required branch does NOT call settle() directly — the recursive re-POST inherits the guard and settles on its own terminal state.

Notes on the JS:
- **`Promise.then()` chains, NOT `async/await`**: enforced by file convention (the existing module has zero `async function` or `await` keywords; all I/O uses `.then().catch()`). Diverging would create a stylistic outlier and may not transpile if the build pipeline targets ES5.
- `window.App.escapeHtml` is the canonical XSS-safe text rendering helper. Bind to a local `escapeHtml` alias at function entry to match line 132's pattern.
- The popup-poll loop checks every 500ms — same as the flight Technical Approach §L3 spec. Don't increase the interval; popup-close detection latency is operator-facing.

The button-click wiring inside `wireEditorEvents` passes `testBtn` so the handler can manage its disabled state:

```javascript
var testBtn = container.querySelector('[data-testid="mcp-test-connection"]');
if (testBtn) {
  testBtn.addEventListener('click', function () {
    handleTestConnection(source.id, container, testBtn);
  });
}
```

### Step 5: Tests

**Unit Test 1: `test_make_oauth_handlers_resolves_consent_url_future`**

Joins `tests/test_oauth_handlers.py`. Read 30 lines of context to find the file's existing pattern; the new test follows the same `pytest.mark.asyncio` + handler-construction-in-async-body convention.

```python
@pytest.mark.asyncio
async def test_make_oauth_handlers_resolves_consent_url_future():
    consent_url_future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
    redirect_handler, _ = make_oauth_handlers(
        chat_session_id="test-csid",
        source_id="src-1",
        tool_call_id=None,
        resource_metadata_url=None,
        consent_url_future=consent_url_future,
    )
    
    auth_url = "https://example.com/auth?state=abc123&client_id=x"
    await redirect_handler(auth_url)
    
    assert consent_url_future.done()
    assert consent_url_future.result() == auth_url
```

**Unit Test 2: `test_build_oauth_provider_for_source_threads_consent_url_future`**

Joins `tests/test_oauth_provider_factory.py`. Tests that the factory threads the kwarg through to `make_oauth_handlers`; use a monkeypatched `make_oauth_handlers` that captures the kwargs, OR construct a real provider and invoke its redirect_handler with an auth URL and confirm the future resolves.

**Unit Tests 3, 4, 5, 6: `/test/connect` endpoint**

Create `tests/test_oauth_test_connection_endpoint.py` (mirrors `test_oauth_start_endpoint.py`'s structure — read it for fixture conventions). Tests:

3. `test_test_connect_404_when_source_missing`: POST to `/test/connect/nonexistent` returns 404
4. `test_test_connect_returns_ok_when_tokens_present`: seed source with `dcr_credentials` + `access_token`; mock `MCPClient` to return tools (assert that the test verifies `auth_provider` was threaded through — not a bare `MCPClient(source=...)`); POST returns `{status: "ok", tools: [...]}`
5. `test_test_connect_returns_auth_required_when_no_creds`: seed source with empty secrets; mock the SDK's auth flow (or use the existing in-repo OAuth fixture) to call redirect_handler with a synthetic URL; POST returns `{status: "auth_required", consent_url}` matching the synthetic URL
6. `test_test_connect_consent_url_timeout`: monkeypatch `_TEST_CONNECT_TIMEOUT` to a short value (e.g. `monkeypatch.setattr(api_mod, "_TEST_CONNECT_TIMEOUT", 0.5)`); mock the SDK's auth flow to never call redirect_handler; POST returns `{status: "error", error: "consent_url_timeout"}` within ~0.5s + epsilon

**Browser Test: `tests/browser/test_mcp_test_connection_button.py`**

Pattern: mirror `tests/browser/test_oauth_modal_flow.py`'s in-repo OAuth fixture setup. The test:

1. Seeds a streamable-http MCP source via API (`POST /api/mcp-sources`) pointing at the in-repo OAuth fixture's mock server URL
2. Opens `#studio/mcp-sources/{id}/edit`
3. Clicks the Test connection button
4. Verifies the result panel renders "Testing connection..." then a popup opens
5. Simulates auto-consent by hitting `/api/oauth/callback` with the fixture's pre-known state + code
6. Closes the popup (simulate via `popup.close()` or close-event)
7. Verifies the result panel renders the tools list (from the in-repo fixture's tools)

Implementer: read `tests/browser/test_oauth_modal_flow.py` for the in-repo OAuth-fixture setup pattern; adapt to the new test-button surface. If the auto-consent fixture isn't easy to drive from a Playwright test, simplify the browser test to: (a) verify the button renders and clicks, (b) verify the result panel updates to show some response (mocked or real). Document any test-shape compromises in the flight log Anomalies section.

### Step 6: Run tests

```bash
docker exec the-one pytest tests/test_oauth_handlers.py tests/test_oauth_provider_factory.py tests/test_oauth_start_endpoint.py tests/test_oauth_test_connection_endpoint.py -v --tb=short
docker exec the-one pytest -m 'not browser and not live and not pixel' --ignore=tests/test_mcp_pool.py --tb=short -q
docker exec the-one pytest -m browser tests/browser/test_oauth_modal_flow.py tests/browser/test_flow_studio_mcp_editor.py tests/browser/test_mcp_test_connection_button.py -v --tb=short
```

If a test fails, debug in place — common modes:
- `MCPClient(source=source)` constructor — verify the actual constructor signature matches (read `the_one/mcp/client.py:60+`); the `MCPClient` may need `connect()` called explicitly (not via context manager).
- The `async with MCPClient(...)` context-manager form may not exist; if it doesn't, use the explicit `await client.connect()` / `await client.disconnect()` pattern.
- The synthetic csid `f"test:{source_id}"` flowing through `_state.register` may collide with state-cleanup invariants; if a test fails on state-registry shape, investigate `_state.register`'s expectations.
- `_evict_all_for_source` is async; missing `await` is the most common bug.

## Edge Cases

- **Source has `dcr_credentials` but no `access_token`** (e.g. DCR completed but auth flow was interrupted before tokens landed): Phase A skips (tokens absent); Phase B kicks. The SDK's auth flow re-uses the existing DCR registration and proceeds to the auth-code grant. Behavior is correct.
- **`access_token` present but expired**: Phase A's `MCPClient.connect()` + `list_tools()` raises `MCPAuthRequired` (per L2 translation when the SDK's refresh fails). Phase A's `except MCPAuthRequired: pass` falls through to Phase B; the SDK's auth flow either refreshes (if refresh_token still valid) or runs full re-auth.
- **Popup blocker prevents `window.open`**: `popup` is `null` (or has `popup.closed === true` immediately). The JS detects this and shows a message asking the operator to allow popups. The button is re-clickable — no re-Test required.
- **`consent_url` future resolved twice**: SDK retries could potentially call redirect_handler twice. The `if not consent_url_future.done()` guard at handler.py prevents `InvalidStateError`. Behavior is correct: first resolution wins; subsequent calls no-op.
- **`/api/oauth/callback` race with periodic state-sweep**: per the existing `oauth_callback` doc at lines 848-853, the cycle-2 NEW-H2 race exists where the TTL sweep pops the entry before `resolve` can fire. The Test endpoint's `_drive_flow_test` task catches the resulting exception and sets the consent_url_future's exception (line 1247 in the leg's sample code). The endpoint then returns `{status: "error", error: "auth_flow_error: ..."}`. Behavior is correct but operator-facing; document in the result-panel UI.
- **Source URL is unreachable** (network error in `_drive_flow_test`): the `except Exception` clause sets the future's exception; endpoint returns `{status: "error", error: "auth_flow_error: ..."}`. Correct.
- **`MCPClient` async context-manager form**: verify by reading `the_one/mcp/client.py:60-100` — there's likely an `@asynccontextmanager` decorated factory function `connect_mcp_client`. If `MCPClient(source=...)` is not directly usable as a context manager, refactor the Phase A code to `client = MCPClient(source=source); await client.connect(); try: ... finally: await client.disconnect()`.
- **`consent_url_timeout` should NOT cancel the background task**: the task continues running and may eventually resolve (if the SDK is slow). The task is in `_inflight_resume_tasks`; the FastAPI lifespan drains them on shutdown. Test: after a `consent_url_timeout` response, the task is still in `_inflight_resume_tasks`; if the SDK eventually resolves, tokens land and a SUBSEQUENT Test press hits Phase A's `{status: "ok"}` path. Correct.
- **Test button rendering on stdio sources**: the AC requires hiding on stdio (Test only applies to streamable-http per the `if (source.type !== "streamable-http")` guard at the endpoint). The UI's render guard `(source && source.type === 'streamable-http')` aligns. Confirm both layers reject stdio.

## Files Affected

- `the_one/mcp/oauth/handlers.py` — extend `make_oauth_handlers` signature with `consent_url_future` keyword-only kwarg; add resolution inside `redirect_handler`; update docstring (~6 lines added)
- `the_one/mcp/oauth/provider_factory.py` — extend `build_oauth_provider_for_source` signature with same kwarg; thread to `make_oauth_handlers`; update docstring (~3 lines added)
- `the_one/interfaces/web/api.py` — add new `@router.post("/mcp-sources/{source_id}/test/connect")` handler; ~80 lines
- `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js` — add Test connection HTML block (edit-mode + streamable-http only), wire button event, add `handleTestConnection` async function (~50 lines)
- `tests/test_oauth_handlers.py` — add 1 new test for `consent_url_future`
- `tests/test_oauth_provider_factory.py` — add 1 new test for kwarg threading
- `tests/test_oauth_test_connection_endpoint.py` — NEW FILE — 4 tests for the endpoint
- `tests/browser/test_mcp_test_connection_button.py` — NEW FILE — 1 browser test for popup-flow against in-repo fixture

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (full unit + targeted browser)
- [ ] Update flight-log.md with leg progress entry under `## Leg Progress` → `### L3`
- [ ] Set this leg's status to `landed` in this file's header
- [ ] Check off this leg in flight.md
- [ ] Update CLAUDE.md or `agents.md` if the new endpoint or UI surface needs documenting (the endpoint is a peer of `/api/oauth/start`; mention it in any prose listing OAuth endpoints)
- [ ] **DO NOT commit** — flight 6.5's flight-level Reviewer + commit run AFTER L3 lands. L3 is the last autonomous leg.

## Citation Audit

15 citation regions verified against current code on branch `flight/6_5-oauth-simplification` post-L0+L1+L2 at leg design time (2026-05-08):

- `handlers.py:39-116` — full file body; `make_oauth_handlers` signature + body verified
- `provider_factory.py:58-135` — function signature + threading point at line 99 verified (post-L0 simplified body)
- `api.py:715-830` — `/api/mcp-sources` CRUD block (placement reference for new endpoint)
- `api.py:820-935` — `/api/oauth/callback` (no changes; synthetic-csid path no-ops)
- `api.py:937-1053` — `/api/oauth/start` (pattern reference)
- `_pool.py:248` — `_evict_all_for_source` async function
- `client.py::MCPClient` — F6.5 L2-extended `list_tools` (pattern dependency)
- `mcp-server-editor.js:59-61, 117-121, 126` — Save/Back/Danger Zone/wireEditorEvents (placement reference)
- `tests/test_oauth_handlers.py` — pattern reference for handler tests
- `tests/test_oauth_provider_factory.py` — pattern reference for factory tests
- `tests/test_oauth_start_endpoint.py` — pattern reference for endpoint tests
- `tests/browser/test_oauth_modal_flow.py` — pattern reference for in-repo OAuth fixture
- `_state.register` / `_state.peek` semantics (per handlers.py:78-85) — register-BEFORE-resolve invariant verified
- `_inflight_resume_tasks` set (per `app.py`) — task-tracking pattern verified via `oauth_start` usage
- `MCPAuthRequired` constructor (post-L2) — keyword-only fields after `source_id`

L3 is structurally larger than L0/L1/L2 (new endpoint + new UI + new tests) but the source-of-truth patterns are all in the codebase already. The factory extensions are textbook keyword-only-with-default. The endpoint mirrors `oauth_start` with two key deltas (synthetic csid + future-await). The UI is a small editor extension. The browser test is the highest-risk piece because in-repo OAuth fixture handling is finicky — be prepared to compromise on browser-test scope if the fixture proves hard to drive.

**Design review cycle 1 (2026-05-08)**: Reviewer flagged 3 high + 3 medium issues, all from reading the actual code. All incorporated:
1. HIGH — `mcp-server-editor.js` uses Promise-chain style exclusively (zero `async function`/`await`). Rewrote `handleTestConnection` as a Promise-then chain to match file convention.
2. HIGH — Phase A's `MCPClient(source=source)` was bare, no `auth_provider` threaded — would always 401 even with cached tokens, defeating the fast-path. Phase A now builds an OAuth provider with `consent_url_future=None` and threads it via `MCPClient(source=source, auth_provider=provider_a)`.
3. HIGH — Concurrent-Test race (re-clicking before in-flight POST settles creates a second `consent_url_future` and second task with state shadowing). Added explicit AC: UI MUST disable the Test button between click and final-state settle (NOT just first response — popup-flow keeps button disabled until Phase 2 re-POST settles). Updated the JS sample with `testBtn.disabled = true` + a `settle()` closure helper.
4. MEDIUM — Pool eviction was Phase B-only, but Phase A → Phase B fallthrough (expired token) leaves stale pool entries. Added `await _evict_all_for_source(source_id)` immediately inside the `except MCPAuthRequired:` clause before fall-through.
5. MEDIUM — Connect-time 401 surfaces as `MCPConnectionError` per Design Decision §3 deferring to F7. The original AC said `auth_required` fires "if connection raises MCPAuthRequired" but only `list_tools` 401 surfaces that way. AC corrected to "list_tools raises MCPAuthRequired"; added explanatory comment in the endpoint sample noting the F7 deferral implication.
6. MEDIUM — Timeout monkeypatching was unspecified. Extracted the magic 15.0 to a module-level constant `_TEST_CONNECT_TIMEOUT: float = 15.0` near top of `api.py`; Test 6 monkeypatches via `monkeypatch.setattr(api_mod, "_TEST_CONNECT_TIMEOUT", 0.5)` per file convention.

Reviewer also corrected the test count (5 → 6 unit + 1 browser; reconciled Outputs section) and confirmed the redirect_handler resolution ordering in `handlers.py` is correct.
