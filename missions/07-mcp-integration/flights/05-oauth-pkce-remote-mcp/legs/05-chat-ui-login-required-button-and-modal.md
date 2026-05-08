# Leg: 05-chat-ui-login-required-button-and-modal

**Status**: landed
**Flight**: [Lazy OAuth 2.1 + PKCE for Remote MCP Servers](../flight.md)

## Objective

Land the end-to-end OAuth UX: WebSocket event handlers in `chat.js` (`auth_required`, `auth_resolved`, `auth_failed`); inline Login-required button in chat history; new `oauth-modal.js` component (Connect button + manual-entry form); two new API endpoints — `/api/oauth/manual-register` (persists manual-entry dcr_credentials) and `/api/oauth/start` (constructs provider + drives SDK flow to broadcast `auth_required` with a real `consent_url`); a factory `build_oauth_provider_for_source(source, repo, chat_session_id, source_id, tool_call_id, resource_metadata_url) -> httpx.Auth | None` in `the_one.mcp.oauth`; F4 pool extension to attach a provider when dcr_credentials are present; browser tests via Playwright; accessibility review.

## Context

**Flight design references**: §1 (auth-code with loopback redirect), §2 (DCR-first / manual fallback), §4 (lazy-path consent_url=None seam), §10 (HAT 5-step verification), §11 (`/api/oauth/manual-register` route + chat UI). L0-L4 landed (uncommitted). L4 deferred provider construction; user **picked Option A for L5**: pull provider construction + lazy-path trigger into L5 alongside UI work.

**Critical invariants**:

1. **Factory function in `the_one.mcp.oauth.provider_factory`** (NEW module) — reads `source.secrets["dcr_credentials"]`. If absent, returns None. If `registration_method == "manual"`, constructs `ManualOAuthClientProvider`. Else `OAuthClientProvider`. Both bound to handlers from `make_oauth_handlers(chat_session_id, source_id, tool_call_id, resource_metadata_url)` and `MCPSourceTokenStorage(repo, source_id)`. `OAuthClientMetadata` is built per L4-design `client_name="the-one"`, `redirect_uris=[f"http://127.0.0.1:{settings.port}/api/oauth/callback"]`, `grant_types=["authorization_code", "refresh_token"]`, `response_types=["code"]`, `token_endpoint_auth_method="none"`.

2. **F4 pool integration (cycle-ahead-of-L6)** — `_entry_worker` calls the factory to build a provider; `MCPClient(source, auth_provider=provider)` gets the provider attached at construction. Pool keys on `(agent_name, source_id)`. Since L5 doesn't have agent-side `chat_session_id` plumbing yet (F6 scope), the pool constructs a "session-broadcast" handler factory that resolves `chat_session_id` via a contextvar (`current_chat_session_id: ContextVar[str | None]`) set by the agent loop on each tool dispatch. **If contextvar is unset**, the redirect_handler broadcasts to the most-recently-active session in `_sessions` (best-effort fallback for HAT testing).

3. **`/api/oauth/start` endpoint** — POST with `{source_id, chat_session_id, tool_call_id?, resource_metadata_url?}`. Looks up source. If `dcr_credentials` is present, constructs provider via factory and runs `async_auth_flow` against the source URL in a background task — the SDK's redirect_handler broadcasts `auth_required` with the real consent_url + the loopback callback awaits → tokens persist → `auth_resolved` broadcast → agent resumes. Returns 202 immediately. If `dcr_credentials` absent, returns 400 with "manual-register first or DCR-supporting AS required".

4. **`/api/oauth/manual-register` endpoint** — POST with `{source_id, client_id, auth_endpoint, token_endpoint}`. Persists `secrets["dcr_credentials"] = {client_id, auth_endpoint, token_endpoint, registration_method: "manual", registered_at: <iso>}`. Returns 200. The chat UI then triggers `/api/oauth/start` to begin the flow.

5. **Chat UI flow**:
   - First `auth_required` event (`consent_url=None`, lazy-path): chat surface renders an inline "Login required for `<source_id>`" button replacing the would-be tool_result. Click → opens `oauth-modal`. Modal shows "Connect" button (DCR auto-attempted) and a collapsed "Use manual entry instead" disclosure.
   - Connect click: POST `/api/oauth/start` with `{source_id, chat_session_id, tool_call_id, resource_metadata_url}`. SDK runs DCR + auth flow → SECOND `auth_required` event with real `consent_url` → modal opens it via `window.open(consent_url, "_blank")`.
   - If DCR fails (server returns `auth_failed` with `error="dcr_not_supported"` or `oauth_required` event with `manual_registration_required: true` flag): modal expands manual-entry form (3 fields). Submit → POST `/api/oauth/manual-register` → on success, retries `/api/oauth/start`.
   - On `auth_resolved`: modal auto-closes; inline button clears (replaced by a "Re-running…" spinner that resolves when the resumed tool_result arrives).

6. **`auth_failed` UI**: chat surface shows an error notice ("OAuth failed: <description>"). Modal closes if open.

7. **Reconnect snapshot from L3**: WebSocket reconnect re-emits the cached `auth_required` event from `agent.messages[-1].tool_result.metadata`. UI's auth_required handler is idempotent — re-rendering the button is a no-op.

8. **Manual-register sub-event protocol**: when `/api/oauth/start` detects DCR failure (no `registration_endpoint` in AS metadata), it broadcasts a NEW WebSocket event `oauth_manual_registration_required` `{type, source_id, auth_endpoint?, token_endpoint?, error}`. Modal listens and pops the manual-entry form pre-filled (when endpoints could be discovered) or empty.

9. **Accessibility**: modal must trap focus, support Escape-to-close, have ARIA labels on form fields, maintain WCAG 2.1 AA contrast (4.5:1 text), keyboard-navigable button + form. Existing `dialog.js`'s `App.confirmDialog` pattern provides the focus-trap + Escape baseline; reuse it. Manual-entry form labels: `<label for="oauth-client-id">Client ID</label>` etc.

10. **No new CSS**: reuse `.modal-overlay`, `.modal-dialog`, `.modal-dialog-title`, `.modal-dialog-message`, `.btn-filled-cyan`, `.btn-outlined-cyan` classes from `components.css` 855-912. Form fields use existing `<input>` styling.

**Known architectural debt** (cycle-1 reviewer will flag — accept and document):

- The contextvar fallback (Invariant 2) is a workaround for missing F6 plumbing. When F6 lands, the agent loop sets `current_chat_session_id` cleanly per tool dispatch and the fallback dies.
- The "most-recently-active session" fallback is best-effort and may misroute broadcasts in multi-tab scenarios. Documented as a known issue carried to F6.
- F4 pool warm-cache means the FIRST tool call after dcr_credentials persistence still uses the cached MCPClient (which has no provider). To work around: `/api/oauth/start` evicts the pool entry for `(agent_name, source_id)` (using the existing pool API) so the next call_tool reconstructs MCPClient with the now-populated dcr_credentials → factory builds provider → success. The eviction is a one-line addition to the start endpoint.

**Test seam considerations**:

- Browser tests use the existing `tests/browser/conftest.py` fixtures (`page`, `app_clean`, `app_with_provider`).
- The `/api/oauth/start` endpoint uses an in-process FastMCP-shaped OAuth fixture for testing (the same fixture L6 HAT will use). For L5's browser tests, a minimal stub fixture in `tests/fixtures/oauth/` is sufficient; L6 builds the full RFC-compliant fixture.

## Inputs

- L0-L4 landed (uncommitted; flight branch `flight/05-oauth-pkce-remote-mcp`).
- L2's `make_oauth_handlers`, `MCPSourceTokenStorage`, `ManualOAuthClientProvider`, `ManualOAuthMetadata` from `the_one.mcp.oauth.__init__`.
- L2's `/api/oauth/callback` route + `_state` registry.
- L3's `auth_required`/`auth_resolved`/`auth_failed` events broadcast from `_send_to_session` in `app.py:548-572`/`920-928`/`894-902`.
- L4's `MCPAuthRequired` exception + `auth_provider` parameter on `connect_streamable_http` + `MCPClient.__init__`.
- F4 pool at `the_one/mcp/_pool.py`. The `_entry_worker` function constructs `MCPClient(source)`. `acquire(agent_name, source_id)` and `_evict(agent_name, source_id)` are the pool's public API.
- Existing chat UI: `static/js/areas/chat.js` (`ws.onmessage` at lines 456-594; vanilla JS + `App.registerArea`); `static/js/dialog.js` (modal helper); `static/css/components.css` (modal classes).
- Browser test fixtures: `tests/browser/conftest.py` (`page`, `app_clean`, `app_with_provider`).
- `the_one.config.settings.port` (default 8484).
- `MCPSourceRepository`, `Encryptor`, `get_connection`, `get_encryptor` for repo construction (used by the new factory + endpoints).

## Outputs

**New files**:

- `the_one/mcp/oauth/provider_factory.py` — `build_oauth_provider_for_source(source, repo, chat_session_id, source_id, tool_call_id=None, resource_metadata_url=None) -> httpx.Auth | None` factory. ~70 LOC.
- `the_one/interfaces/web/static/js/oauth-modal.js` — `App.oauthModal.open({source_id, chat_session_id, tool_call_id, resource_metadata_url, consent_url, manual_registration_required})`, `App.oauthModal.close()`. Renders modal with Connect button, manual-entry disclosure, manual-entry form (3 fields). Submits to `/api/oauth/start` or `/api/oauth/manual-register`. ~150 LOC.
- `tests/fixtures/oauth/__init__.py` — stub OAuth AS fixture (FastMCP-shaped). Implements minimal RFC 8414 AS metadata + RFC 7591 DCR + locally-signed access tokens. ~80 LOC. (L6 HAT extends with full RFC 9728 PRM.)
- `tests/test_oauth_provider_factory.py` (NEW) — factory unit tests (4 tests).
- `tests/test_oauth_start_endpoint.py` (NEW) — `/api/oauth/start` route tests (3 tests).
- `tests/test_oauth_manual_register_endpoint.py` (NEW) — `/api/oauth/manual-register` route tests (3 tests).
- `tests/browser/test_oauth_modal_flow.py` (NEW) — Playwright tests (6 tests).

**Modified files**:

- `the_one/interfaces/web/api.py` — add `/api/oauth/start` POST route; add `/api/oauth/manual-register` POST route. Both use lazy imports from `app.py` for `_sessions` + `_send_to_session`. ~80 LOC additions.
- `the_one/interfaces/web/app.py` — add `current_chat_session_id: ContextVar[str | None]` module-level. Add a new event type emit helper for `oauth_manual_registration_required`. Modify the agent-tool dispatch site (in L3's `_dispatch_tool_calls` or `_resume_paused_session` path) to set the contextvar before invoking tool calls. ~30 LOC.
- `the_one/mcp/_pool.py::_entry_worker` — call `build_oauth_provider_for_source(source, repo, chat_session_id=None, source_id=source.id)` and pass result as `auth_provider=` to `MCPClient(source, ...)`. The chat_session_id is None at pool-construction time (resolved via contextvar at handler-fire time). ~10 LOC.
- `the_one/interfaces/web/static/js/areas/chat.js` — extend `ws.onmessage` with cases for `auth_required`, `auth_resolved`, `auth_failed`, `oauth_manual_registration_required`. Add `renderLoginRequiredButton(event)` helper. ~80 LOC.
- `the_one/interfaces/web/static/index.html` — add `<script src="/static/js/oauth-modal.js"></script>` (after dialog.js). ~1 LOC.
- `the_one/mcp/oauth/__init__.py` — extend `__all__` with `build_oauth_provider_for_source`.

**Net new test count target**: 16 new tests (4 factory + 3 start endpoint + 3 manual-register + 6 browser). A14 sets bound at 16.

**Net LOC target**: ~600 production + ~700 tests = ~1300 LOC total. (Larger than prior legs due to UI + endpoints + factory + tests.)

## Acceptance Criteria

- [ ] **A1 — Factory function**: `build_oauth_provider_for_source(source, repo, chat_session_id, source_id, tool_call_id=None, resource_metadata_url=None)` returns:
  - `None` when `source.secrets.get("dcr_credentials")` is absent or empty.
  - `OAuthClientProvider` instance when `dcr_credentials.get("registration_method") != "manual"`.
  - `ManualOAuthClientProvider` instance when `dcr_credentials.get("registration_method") == "manual"`.
  Constructed with handlers from `make_oauth_handlers(chat_session_id, source_id, tool_call_id, resource_metadata_url)`, storage from `MCPSourceTokenStorage(repo, source_id)`, and `OAuthClientMetadata(client_name="the-one", redirect_uris=[f"http://127.0.0.1:{settings.port}/api/oauth/callback"], grant_types=["authorization_code", "refresh_token"], response_types=["code"], token_endpoint_auth_method="none")`. Verified by 4 unit tests.

- [ ] **A2 — `/api/oauth/manual-register` endpoint**: POST `{source_id, client_id, auth_endpoint, token_endpoint}` persists `secrets["dcr_credentials"]` correctly. Verified: source has dcr_credentials with all 4 fields + `registration_method="manual"` + `registered_at`. 400 on missing fields; 404 on unknown source_id.

- [ ] **A3 — `/api/oauth/start` endpoint**: POST `{source_id, chat_session_id, tool_call_id?, resource_metadata_url?}`:
  - 400 if `secrets["dcr_credentials"]` is absent (with message "Configure manual registration or use a DCR-supporting AS").
  - When dcr_credentials present: schedules background task to drive SDK flow; evicts the F4 pool entry for `(any_agent, source_id)` so next call_tool reconstructs MCPClient; returns 202 with `{status: "started"}`.
  - The background task uses an httpx.AsyncClient with `auth=provider` to make a request to `source.config["url"]`; the 401 surfaces; SDK runs auth flow; redirect_handler broadcasts `auth_required` with real `consent_url`; callback awaits.

- [ ] **A4 — F4 pool integration**: `_entry_worker` constructs `MCPClient(source, auth_provider=build_oauth_provider_for_source(...))`. Verified: when source has `dcr_credentials`, the pool's MCPClient instance has a non-None `_auth_provider`; when absent, `_auth_provider is None`. Existing pool tests pass UNMODIFIED.

- [ ] **A5 — `current_chat_session_id` contextvar**: declared at module level in `app.py`; set by `_dispatch_tool_calls` (or `_resume_paused_session`) wrapper before each tool dispatch; read by `make_oauth_handlers`'s factory site so the redirect_handler broadcasts to the right session. Best-effort fallback: when contextvar is unset, broadcast to "most-recently-active" session — implemented as `_sessions[next(iter(_sessions))]` if the dict is non-empty, else no broadcast.

- [ ] **A6 — chat.js handlers**: `ws.onmessage` switches on type:
  - `"auth_required"`: render Login-required button inline at the chat history's tail (replacing the would-be `tool_result`). Cache event payload on the button via `data-*` attributes.
  - `"auth_resolved"`: clear the inline Login-required button; close modal if open; show "Resuming…" spinner until the resumed `tool_result` arrives.
  - `"auth_failed"`: show error notice with `error_description`. Close modal if open.
  - `"oauth_manual_registration_required"`: open modal in manual-entry-form mode (if not already open). Pre-fill `auth_endpoint` and `token_endpoint` if event carries them.

- [ ] **A7 — `oauth-modal.js` component**: `App.oauthModal.open({...})`:
  - Renders modal with title "Login required for `<source_id>`", Connect button, "Use manual entry" disclosure (collapsed by default).
  - Connect click: if `consent_url` is in event payload, `window.open(consent_url, "_blank")`. Otherwise POST `/api/oauth/start` with `{source_id, chat_session_id, tool_call_id, resource_metadata_url}` and wait for the SDK flow to broadcast a SECOND `auth_required` (which the chat.js handler reroutes to the modal — modal handler intercepts when modal is open AND `consent_url` is now present → opens window).
  - Manual-entry form: 3 fields (`client_id`, `auth_endpoint`, `token_endpoint`), Submit button. POST to `/api/oauth/manual-register`. On 200, immediately POST `/api/oauth/start` to drive the consent flow.
  - Auto-close on `auth_resolved`. ESC-key + clicking overlay outside dialog also closes (matches `App.confirmDialog` pattern).

- [ ] **A8 — Inline Login-required button**: rendered in `.messages` flow; styled via `.btn-filled-cyan`; click triggers `App.oauthModal.open(event_payload)`. Button text: `"Login required for <source_id>"`. Replaced by a "Resuming…" placeholder on `auth_resolved`.

- [ ] **A9 — `auth_failed` rendering**: error notice div appended to chat with class `.system-error` (existing class). Text: `f"OAuth failed: {description or error}"`.

- [ ] **A10 — Reconnect snapshot UI**: when WebSocket reconnects and the session has `pending_auth` state (per L3's `_send_pause_snapshot_if_needed`), the auth_required event payload arrives — the UI's handler is idempotent (re-rendering the button is a no-op; no duplicate buttons).

- [ ] **A11 — Browser tests pass** (Playwright, `tests/browser/test_oauth_modal_flow.py`):
  - `test_login_button_renders_on_auth_required_event` — emit fake `auth_required` via test helper; assert `.login-required-btn` visible with correct text.
  - `test_modal_opens_on_button_click` — click button; assert `.modal-overlay` visible + dialog title contains `source_id`.
  - `test_manual_entry_disclosure_toggles` — click "Use manual entry"; assert form fields visible.
  - `test_manual_register_submission_persists_dcr_credentials` — fill form; submit; assert API was called + dcr_credentials updated.
  - `test_modal_closes_on_auth_resolved_event` — open modal; emit `auth_resolved`; assert `.modal-overlay` gone.
  - `test_button_clears_on_resumed_tool_result` — full flow: button → modal → auth_resolved → tool_result arrives → button replaced by tool_result.

- [ ] **A12 — Accessibility audit**: spawn the **Accessibility Reviewer** crew agent (Sonnet, per `.flightops/agent-crews/leg-execution.md:23-30`). Reviewer evaluates against WCAG 2.1 AA; any blocking issues fixed inline; reviewer signals `[HANDOFF:confirmed]`. Specific checks:
  - Modal has focus-trap (`role="dialog"`, `aria-modal="true"`, `aria-labelledby` pointing to title).
  - All form fields have `<label for="...">`.
  - Connect button + Submit button keyboard-reachable in tab order.
  - Color contrast: cyan on dark surface ≥ 4.5:1 for text (verified via existing tokens).
  - Escape key closes modal (matches `dialog.js` pattern).
  - Screen-reader-friendly text: button uses descriptive text not ARIA hacks.

- [ ] **A13 — F4 pool tests pass UNMODIFIED**: existing `tests/test_mcp_pool.py` tests pass without any changes (the pool extension is additive — when source has no dcr_credentials, factory returns None, pool behavior identical to today).

- [ ] **A14 — All prior tests pass UNMODIFIED**: all L0-L4 tests + pre-existing tests pass at 1291 (L4 baseline) + 16 (new) = 1307 passed. The 1 pre-existing pool-shutdown failure carries forward unchanged.

- [ ] **A15 — Lint clean**: `docker compose exec the-one ruff check the_one/mcp/oauth/ the_one/interfaces/web/api.py the_one/interfaces/web/app.py the_one/mcp/_pool.py tests/test_oauth_provider_factory.py tests/test_oauth_start_endpoint.py tests/test_oauth_manual_register_endpoint.py tests/browser/test_oauth_modal_flow.py tests/fixtures/oauth/` exits 0.

- [ ] **A16 — Citation audit**: BEFORE implementation,
  - `grep -rn "MCPClient(" tests/ the_one/` → identify call sites; verify backward compat with new `auth_provider=` plumbing.
  - `grep -rn "ws\.onmessage\|onmessage" the_one/interfaces/web/static/js/` → identify the message handler site.
  - `grep -rn "_entry_worker\|MCPClient(source)" the_one/mcp/_pool.py` → identify the pool's MCPClient construction site.
  - Citation audit results recorded in flight log.

- [ ] **A17 — Architectural debt documented**: flight log L5 entry documents (a) contextvar fallback to "most-recently-active session" is a workaround for F6's missing chat_session_id plumbing; (b) the start endpoint's pool eviction is required because warm pool entries cache the no-provider state; (c) F6 will replace these workarounds with proper agent-layer plumbing.

## Verification Steps

- `grep -n "build_oauth_provider_for_source" the_one/mcp/oauth/provider_factory.py the_one/mcp/_pool.py` → matches in both.
- `grep -n "/oauth/start\|/oauth/manual-register" the_one/interfaces/web/api.py` → 2 matches.
- `grep -n "current_chat_session_id" the_one/interfaces/web/app.py` → multiple matches.
- `grep -n "auth_required\|auth_resolved\|auth_failed\|oauth_manual_registration_required" the_one/interfaces/web/static/js/areas/chat.js` → matches for all 4 event types.
- `docker compose exec the-one ruff check ...` → clean.
- `docker compose exec the-one pytest tests/test_oauth_provider_factory.py tests/test_oauth_start_endpoint.py tests/test_oauth_manual_register_endpoint.py -q --timeout=30` → green.
- `docker compose exec the-one pytest tests/browser/test_oauth_modal_flow.py -q --timeout=60` → green (browser tests have higher timeout).
- `docker compose exec the-one pytest -q --timeout=30` → 1307 passed, 2 skipped, 1 pre-existing failure.

## Implementation Guidance

1. **Factory function** at `the_one/mcp/oauth/provider_factory.py`:
   ```python
   from typing import Any
   import httpx
   from mcp.client.auth import OAuthClientProvider
   from mcp.shared.auth import OAuthClientMetadata
   from the_one.config import settings
   from the_one.db.models import MCPSource
   from the_one.db.repositories import MCPSourceRepository
   from .handlers import make_oauth_handlers
   from .manual_metadata import ManualOAuthClientProvider, ManualOAuthMetadata
   from .storage import MCPSourceTokenStorage

   def build_oauth_provider_for_source(
       source: MCPSource,
       repo: MCPSourceRepository,
       chat_session_id: str,
       source_id: str | None = None,
       tool_call_id: str | None = None,
       resource_metadata_url: str | None = None,
   ) -> httpx.Auth | None:
       dcr = source.secrets.get("dcr_credentials")
       if not dcr or not dcr.get("client_id"):
           return None

       redirect_handler, callback_handler = make_oauth_handlers(
           chat_session_id=chat_session_id,
           source_id=source_id or source.id,
           tool_call_id=tool_call_id,
           resource_metadata_url=resource_metadata_url,
       )
       storage = MCPSourceTokenStorage(repo, source.id)
       client_metadata = OAuthClientMetadata(
           client_name="the-one",
           redirect_uris=[f"http://127.0.0.1:{settings.port}/api/oauth/callback"],
           grant_types=["authorization_code", "refresh_token"],
           response_types=["code"],
           token_endpoint_auth_method="none",
       )
       if dcr.get("registration_method") == "manual":
           manual = ManualOAuthMetadata(
               client_id=dcr["client_id"],
               auth_endpoint=dcr["auth_endpoint"],
               token_endpoint=dcr["token_endpoint"],
           )
           return ManualOAuthClientProvider(
               server_url=source.config["url"],
               client_metadata=client_metadata,
               storage=storage,
               redirect_handler=redirect_handler,
               callback_handler=callback_handler,
               manual_metadata=manual,
           )
       return OAuthClientProvider(
           server_url=source.config["url"],
           client_metadata=client_metadata,
           storage=storage,
           redirect_handler=redirect_handler,
           callback_handler=callback_handler,
       )
   ```

2. **`/api/oauth/manual-register`** in `api.py`:
   ```python
   @router.post("/oauth/manual-register")
   async def oauth_manual_register(request: Request) -> dict[str, Any]:
       data = await request.json()
       source_id = data.get("source_id")
       client_id = data.get("client_id")
       auth_endpoint = data.get("auth_endpoint")
       token_endpoint = data.get("token_endpoint")
       if not all([source_id, client_id, auth_endpoint, token_endpoint]):
           raise HTTPException(status_code=400, detail="Missing fields")
       repo = await _mcp_repo()
       try:
           source = await repo.get(source_id)
       except KeyError:
           raise HTTPException(status_code=404, detail=f"Source not found: {source_id}")
       source.secrets["dcr_credentials"] = {
           "client_id": client_id,
           "auth_endpoint": auth_endpoint,
           "token_endpoint": token_endpoint,
           "registration_method": "manual",
           "registered_at": datetime.now(timezone.utc).isoformat(),
       }
       await repo.update(source)
       return {"status": "registered"}
   ```

3. **`/api/oauth/start`** in `api.py`:
   ```python
   @router.post("/oauth/start")
   async def oauth_start(request: Request) -> dict[str, Any]:
       from the_one.interfaces.web.app import _inflight_resume_tasks
       from the_one.mcp.oauth import build_oauth_provider_for_source
       from the_one.mcp._pool import _evict_all_for_source  # add this helper to the pool

       data = await request.json()
       source_id = data["source_id"]
       chat_session_id = data["chat_session_id"]
       tool_call_id = data.get("tool_call_id")
       resource_metadata_url = data.get("resource_metadata_url")

       repo = await _mcp_repo()
       try:
           source = await repo.get(source_id)
       except KeyError:
           raise HTTPException(status_code=404, detail=f"Source not found: {source_id}")
       if not source.secrets.get("dcr_credentials"):
           raise HTTPException(
               status_code=400,
               detail="Configure manual registration or use a DCR-supporting AS",
           )

       provider = build_oauth_provider_for_source(
           source, repo, chat_session_id,
           source_id=source_id,
           tool_call_id=tool_call_id,
           resource_metadata_url=resource_metadata_url,
       )

       # Evict any cached pool entries for this source so subsequent
       # tool calls reconstruct MCPClient with the new provider
       await _evict_all_for_source(source_id)

       async def _drive_flow() -> None:
           try:
               async with httpx.AsyncClient(auth=provider, timeout=30.0) as client:
                   # Hit the source URL; 401 triggers SDK auth flow
                   await client.post(source.config["url"], json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
           except Exception as e:
               logger.exception("OAuth start flow failed")
               # Best-effort: broadcast auth_failed
               from the_one.interfaces.web.app import _sessions, _send_to_session
               sess = _sessions.get(chat_session_id)
               if sess is not None:
                   await _send_to_session(sess, {
                       "type": "auth_failed",
                       "source_id": source_id,
                       "error": "start_failed",
                       "description": str(e),
                   })

       task = asyncio.create_task(_drive_flow())
       _inflight_resume_tasks.add(task)
       task.add_done_callback(_inflight_resume_tasks.discard)
       return {"status": "started"}
   ```

   Add `_evict_all_for_source(source_id: str)` helper to `the_one/mcp/_pool.py`. Walks all entries, evicts those matching source_id (across all agent_names).

4. **F4 pool extension** in `_pool.py::_entry_worker`:
   ```python
   # Inside _entry_worker(source, entry):
   from the_one.mcp.oauth import build_oauth_provider_for_source
   from the_one.interfaces.web.app import current_chat_session_id  # contextvar

   # Resolve chat_session_id from contextvar (may be None — fallback handled in make_oauth_handlers)
   csid = current_chat_session_id.get(None) or "_pool_default"
   conn = await get_connection()
   encryptor = get_encryptor(settings.data_dir)
   repo = MCPSourceRepository(conn, encryptor)
   provider = build_oauth_provider_for_source(source, repo, csid, source_id=source.id)
   client = MCPClient(source, auth_provider=provider)
   ```

5. **Contextvar in `app.py`**:
   ```python
   from contextvars import ContextVar
   current_chat_session_id: ContextVar[str | None] = ContextVar("current_chat_session_id", default=None)
   ```
   Set in `_process_and_broadcast` before invoking `agent.step` and in `_resume_paused_session` before invoking `resume_after_auth`:
   ```python
   token = current_chat_session_id.set(session.id)
   try:
       # ... existing agent step / resume ...
   finally:
       current_chat_session_id.reset(token)
   ```

6. **chat.js extension**: in `ws.onmessage`'s switch (around line 470+), add:
   ```javascript
   } else if (data.type === "auth_required") {
       renderLoginRequiredButton(data);
   } else if (data.type === "auth_resolved") {
       clearLoginRequiredButton(data);
       App.oauthModal && App.oauthModal.close();
       renderResumingPlaceholder(data);
   } else if (data.type === "auth_failed") {
       App.oauthModal && App.oauthModal.close();
       renderErrorNotice(`OAuth failed: ${data.description || data.error}`);
   } else if (data.type === "oauth_manual_registration_required") {
       App.oauthModal && App.oauthModal.openManual(data);
   }
   ```

   `renderLoginRequiredButton(data)`:
   ```javascript
   function renderLoginRequiredButton(data) {
       const btn = document.createElement("button");
       btn.className = "btn-filled-cyan login-required-btn";
       btn.dataset.sourceId = data.source_id;
       btn.dataset.chatSessionId = currentSessionId;
       btn.dataset.toolCallId = data.tool_call_id || "";
       btn.dataset.resourceMetadataUrl = data.resource_metadata_url || "";
       if (data.consent_url) btn.dataset.consentUrl = data.consent_url;
       btn.textContent = `Login required for ${data.source_id}`;
       btn.addEventListener("click", () => {
           App.oauthModal.open({
               source_id: data.source_id,
               chat_session_id: currentSessionId,
               tool_call_id: data.tool_call_id,
               resource_metadata_url: data.resource_metadata_url,
               consent_url: data.consent_url,
           });
       });
       const messages = document.querySelector(".messages");
       messages.appendChild(btn);
   }
   ```

7. **`oauth-modal.js`** — vanilla JS following the `App.confirmDialog` pattern in `dialog.js`. Implements `open({source_id, ...})`, `openManual(data)`, `close()`. Uses `.modal-overlay`, `.modal-dialog`, `.modal-dialog-title`, `.modal-actions`, `.btn-filled-cyan`, `.btn-outlined-cyan` classes. Manual-entry form has 3 `<input>` fields + submit button. Focus-trap + ESC handling mirrors `App.confirmDialog`.

8. **OAuth fixture** at `tests/fixtures/oauth/__init__.py`: minimal FastMCP-shaped server implementing `/.well-known/oauth-authorization-server` (RFC 8414) + `/register` (RFC 7591) + `/authorize` + `/token`. Local-key-signed access tokens with 5-min lifetime. Used by browser tests + `/api/oauth/start` integration tests. L6 HAT extends with full RFC 9728 PRM.

9. **Browser tests** at `tests/browser/test_oauth_modal_flow.py`: use `app_with_provider` fixture (extended with an MCP source pre-configured to point at the local OAuth fixture). Each test drives a UI scenario via `page.click()` / `page.fill()` / `expect(page.locator(...)).to_be_visible()`.

10. **Citation audit + lint + post-completion checklist** per usual.

## Edge Cases

- **Modal opened with both `consent_url` AND `manual_registration_required: true`**: prefer manual-entry mode (DCR didn't work; no point opening a stale URL).
- **`/api/oauth/start` called when SDK flow already in progress for same source**: pool eviction handles re-entry; the new flow supersedes the old. No locking needed for L5 scope.
- **Modal closed by user before flow completes**: pending OAuth state continues server-side (10-min TTL via L2's sweep). User can re-open by clicking a future auth_required event or re-triggering the original action.
- **Multi-tab scenario with contextvar fallback**: "most-recently-active" session may misroute. Documented as known issue carried to F6.
- **Browser snapshot tests are out of scope for L5**: only structural Playwright assertions; pixel snapshots are deferred.
- **Network failure during `/api/oauth/start` background task**: caught by the `_drive_flow` try/except; broadcasts `auth_failed`. UI handles.

## Files Affected

- `the_one/mcp/oauth/provider_factory.py` (NEW)
- `the_one/mcp/oauth/__init__.py` (extend `__all__`)
- `the_one/interfaces/web/api.py` (2 new routes)
- `the_one/interfaces/web/app.py` (contextvar + setter wrappers)
- `the_one/mcp/_pool.py` (_entry_worker + new `_evict_all_for_source` helper)
- `the_one/interfaces/web/static/js/areas/chat.js` (4 new event handlers)
- `the_one/interfaces/web/static/js/oauth-modal.js` (NEW)
- `the_one/interfaces/web/static/index.html` (script tag)
- `tests/fixtures/oauth/__init__.py` (NEW; minimal AS fixture)
- `tests/test_oauth_provider_factory.py` (NEW)
- `tests/test_oauth_start_endpoint.py` (NEW)
- `tests/test_oauth_manual_register_endpoint.py` (NEW)
- `tests/browser/test_oauth_modal_flow.py` (NEW)
- Flight log + flight checkbox + leg artifact status

---

## Post-Completion Checklist

- [ ] All A1-A17 verified
- [ ] Lint clean across all changed files
- [ ] `pytest tests/test_oauth_*.py tests/browser/test_oauth_modal_flow.py -q --timeout=60` green
- [ ] `pytest -q --timeout=30` shows 1307 passed, 2 skipped, 1 pre-existing failure
- [ ] **Accessibility Reviewer spawned and signaled `[HANDOFF:confirmed]`** (per leg-execution phase file)
- [ ] Citation audit + architectural debt notes recorded in flight log
- [ ] Update flight-log.md with L5 progress entry
- [ ] Set leg status to `landed`
- [ ] Check off L5 in flight.md; mark C5 `[x]`
- [ ] Do NOT commit; do NOT update flight status to `landed` yet
- [ ] Signal `[HANDOFF:review-needed]` (NOT `[COMPLETE:leg]` — flight-final review post-L5 commits)

## Citation Audit

To be completed at implementation start. Expected anchor verifications:
- `_pool.py::_entry_worker` location.
- Existing `chat.js` `ws.onmessage` switch shape.
- Existing modal CSS classes in `components.css`.
- L2/L3/L4 hooks confirmed present.
- L4-baseline test count (1291) re-confirmed.
