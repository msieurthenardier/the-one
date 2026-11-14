# Leg: 02-oauth-sdk-adapter

**Status**: landed
**Flight**: [Lazy OAuth 2.1 + PKCE for Remote MCP Servers](../flight.md)

## Objective

Land the OAuth-side adapter layer that the SDK's `OAuthClientProvider` consumes — `TokenStorage` impl backed by `MCPSourceRepository`, paired redirect/callback handlers wired to the WebSocket-broadcast surface, an in-memory pending-flow registry, a `ManualOAuthClientProvider` subclass that overrides `async_auth_flow` to skip discovery for non-DCR providers, the `/api/oauth/callback` FastAPI route, and strict GET/PUT protection for the four OAuth-managed `secrets` keys.

## Context

**Flight design references** — read first, all citations against current code:

- §§5 (token storage shape + GET/PUT protection), §9 (loopback callback route), §11 (module placement) in `flight.md` define the surface this leg lands. §1 (flow shape) and §2 (DCR-first / manual fallback) define the construction-time wiring this leg's `handlers.py` and `manual_metadata.py` must satisfy.
- §7 declared that PKCE / discovery / DCR / RFC 8707 audience binding / pre-emptive refresh are SDK-internal. This leg implements ONLY the adapters — no PKCE, discovery, DCR, or audience-validation code.
- L0 already shipped the package skeleton: `the_one/mcp/oauth/__init__.py` (empty `__all__`) and `the_one/mcp/oauth/errors.py` (4-class hierarchy).
- L1 landed the dispatcher-owned `_open_*_transport_stack` helpers and scoped the F2-known-issue retirement to F4-pool-routed flows. L2 does NOT touch transport code; the OAuth wiring on `connect_streamable_http` is L4's scope.
- L3 introduces the `ToolResult.metadata` field and the agent-loop pause/resume primitive that consumes `auth_required` events. L2's redirect handler broadcasts the WebSocket event but does NOT depend on L3's loop changes — the event shape is fixed by §4 and the chat UI (L5) renders it; backend tests in L2 assert only the broadcast happened.

**Critical SDK contract — verified at design time against `mcp==1.27.0`**:

`OAuthClientProvider.__init__` signature:

```
(self, server_url: str, client_metadata: OAuthClientMetadata,
 storage: TokenStorage,
 redirect_handler: Callable[[str], Awaitable[None]] | None = None,
 callback_handler: Callable[[], Awaitable[tuple[str, str | None]]] | None = None,
 timeout: float = 300.0,
 client_metadata_url: str | None = None)
```

`TokenStorage` Protocol exposes 4 async methods: `get_tokens() -> OAuthToken | None`, `set_tokens(tokens: OAuthToken) -> None`, `get_client_info() -> OAuthClientInformationFull | None`, `set_client_info(client_info: OAuthClientInformationFull) -> None`.

`OAuthToken` field set (verified): `access_token: str`, `token_type: str = "Bearer"`, `expires_in: int | None`, `scope: str | None`, `refresh_token: str | None`. **`expires_in` is a relative duration in seconds at issuance** — not a Unix epoch. The storage layer translates between the SDK's relative duration and our persisted Unix epoch (see Implementation Guidance step 2).

The SDK error hierarchy this leg's tests assert against is rooted at `mcp.client.auth.oauth2.OAuthFlowError` with subclasses `OAuthRegistrationError` and `OAuthTokenError`.

**Manual-entry override target — pre-pinned, NOT discovered at implementation time** (cycle-1 H1, cycle-2 NEW-H1 expansion):

The recon-time SDK probe (verified against `mcp/client/auth/oauth2.py` at the installed `mcp==1.27.0`) confirms that **discovery is inlined into `OAuthClientProvider.async_auth_flow`** as raw `for url in [...]: yield request` loops, and the discovery requests are issued via `yield` regardless of context state — pre-populating `self.context.oauth_metadata` from a custom `_initialize` does NOT skip the discovery loops; the loops always run inside the 401 branch.

This leg therefore commits upfront to **overriding `async_auth_flow` itself** in `ManualOAuthClientProvider`. The override is a **near-verbatim copy of the parent body** (~140 LOC in `mcp==1.27.0`) with three elisions: Step 1 (PRM discovery loop) replaced by `self.context.protected_resource_metadata = None`; Step 2 (OASM discovery loop) replaced by `self.context.oauth_metadata = <synthesized_oauth_metadata>`; Step 4's DCR branch skipped (the `if not self.context.client_info:` guard is short-circuited because the override pre-sets `self.context.client_info` from the manual-entry fields before entering the 401 handler).

The override **MUST mirror the FULL outer structure** of the parent (cycle-2 NEW-H1 finding):

1. `async with self.context.lock:` — outer lock (preserved verbatim)
2. `if not self._initialized: await self._initialize()` — initialize bookkeeping (preserved verbatim)
3. `self.context.protocol_version = request.headers.get(MCP_PROTOCOL_VERSION)` — protocol version capture (preserved verbatim)
4. Refresh-token retry path (`if not self.context.is_token_valid() and self.context.can_refresh_token():`) — preserved verbatim
5. `if self.context.is_token_valid(): self._add_auth_header(request)` — preserved
6. Initial `response = yield request` — preserved
7. `if response.status_code == 401:` — **THIS IS WHERE THE ELISIONS HAPPEN**:
   - **Skip Step 1** (PRM discovery loop): `self.context.protected_resource_metadata = None`
   - **Skip Step 2** (OASM discovery loop): `self.context.oauth_metadata = self._synthesized_oauth_metadata`
   - **Step 3** (scope selection): preserved verbatim; with `protected_resource_metadata=None`, scope falls back to `extract_scope_from_www_auth(response)` only — sufficient for manual-entry providers that don't advertise scopes via PRM.
   - **Skip Step 4 DCR branch**: the `if not self.context.client_info:` guard is short-circuited because the override has already set `self.context.client_info = self._synthesized_client_info` before entering the 401 handler. (Set in `_initialize` override; see Implementation Guidance step 4.)
   - **Step 5** (`token_response = yield await self._perform_authorization()` + `await self._handle_token_response(token_response)`): preserved verbatim
   - Final `self._add_auth_header(request); yield request`: preserved verbatim
8. `elif response.status_code == 403:` step-up scope reauth: **preserved verbatim** (no discovery in this branch; no override needed)

**Helpers the override must import** (from `mcp.client.auth.utils` — verified in cycle-2 review):

```python
from mcp.client.auth.utils import (
    extract_scope_from_www_auth,
    extract_field_from_www_auth,
    get_client_metadata_scopes,
)
from mcp.shared.version import MCP_PROTOCOL_VERSION
```

The override does NOT import the discovery-only helpers (`build_protected_resource_metadata_discovery_urls`, `build_oauth_authorization_server_metadata_discovery_urls`, `create_oauth_metadata_request`, `handle_protected_resource_response`, `handle_auth_metadata_response`, `should_use_client_metadata_url`, `create_client_info_from_metadata_url`, `create_client_registration_request`, `handle_registration_response`) — those are exactly the helpers used by the elided sections.

**SDK-version compatibility risk**: any `mcp` package bump that changes `async_auth_flow`'s body invalidates the override. AC A12b body-shape stake test pins the parent's structure so a future SDK bump fails our test loudly rather than silently producing wrong behavior. **Honest LOC estimate** (cycle-2 NEW-H1): the `manual_metadata.py` module is ~80 LOC of override body + ~30 LOC of `_synthesized_oauth_metadata` / `_synthesized_client_info` construction + imports = ~110 LOC, not the ~50 LOC implied by the cycle-1 draft.

**Paired-handler factory pattern** (cycle-1 H3):

`make_callback_handler(state)` cannot work as a stand-alone factory because the `state` token is generated *inside* `_perform_authorization_code_grant` (SDK internal) and only surfaces to user code via the `authorization_url` passed to `redirect_handler`. So the redirect_handler runs FIRST, parses state from the URL, registers it; the callback_handler runs SECOND with no args, must somehow find that same state. The leg therefore uses a paired-factory shape: `make_oauth_handlers(...) -> tuple[redirect, callback]` that share a `state_box: asyncio.Future[str]` (the state token itself, NOT the auth-code future). Redirect resolves the state-box; callback awaits it, then awaits the per-state code future from `_state`.

**State persistence and TTL**:

§9 sets `_state.py` as keyed by state token, 10-minute TTL, in-memory only. This leg's `_state.py` matches that exactly — no DB persistence; pending flows are lost on FastAPI restart (consistent with §4 / §10's pause/resume not-persisted-across-restart trade-off; documented in module docstring).

**`chat_session_id` is load-bearing** (cycle-1 H4):

The `oauth_callback` route needs to broadcast `auth_resolved` / `auth_failed` to the originating chat session, NOT to anything keyed by MCP source id. The handler factory therefore takes `chat_session_id: str` (i.e. `Session.id`), the `PendingFlow` dataclass carries it, and `_state.register(state, source_id, tool_call_id, chat_session_id)` is the canonical signature. The route's broadcast lookup is `_sessions.get(entry.chat_session_id)`. This is wired into AC A5/A7/A8 directly — not deferred to "mental update".

## Inputs

What exists before this leg runs:

- L0 + L1 landed (uncommitted; flight branch `flight/05-oauth-pkce-remote-mcp` from design commit `f6b5cee`).
- `the_one/mcp/oauth/__init__.py` exists with `__all__: list[str] = []`. L2 appends `__all__` exports.
- `the_one/mcp/oauth/errors.py` defines `MCPOAuthError`, `MCPOAuthDiscoveryError`, `MCPOAuthRegistrationError`, `MCPOAuthRefreshFailed` (all subclassing `MCPClientError`). L2 imports these for tests; the SDK→our-error translation is L4's scope.
- `MCPSourceRepository` (`the_one/db/repositories.py::MCPSourceRepository`) provides async `get(id)` returning `MCPSource` and `update(MCPSource)`; `secrets` is `dict[str, Any]` decrypted via `_ciphertext_to_secrets`, encrypted via `_secrets_to_ciphertext` (whole-blob Fernet).
- `MCPSource` model (`the_one/db/models.py::MCPSource`) has `secrets: dict[str, Any]`, `type: Literal["stdio", "streamable-http"]`, `config: dict[str, Any]`.
- API router (`the_one/interfaces/web/api.py::router`) is `APIRouter(prefix="/api")`; included in app at `the_one/interfaces/web/app.py`. The `_mask_secrets` helper is at api.py:509; `_mcp_source_response` at api.py:520; `update_mcp_source` PUT handler at api.py:742; `_MASKED_API_KEY_SENTINEL = "__MASKED__"` at api.py:886.
- WebSocket broadcast: `the_one/interfaces/web/app.py::_send_to_session(session, payload, exclude=None)` at app.py:443 broadcasts an arbitrary JSON payload to all subscribers of a `Session`. The `Session` dataclass at app.py:113 has `id: str` and `subscribers: set[WebSocket]`. The global `_sessions: dict[str, Session]` is at app.py:147. There is an EXISTING `_state: dict[str, Any]` dict at app.py:103 — the leg's new `the_one.mcp.oauth._state` module MUST be imported under an alias to avoid shadowing.
- The pinned SDK `mcp==1.27.0` provides `mcp.client.auth.OAuthClientProvider`, `mcp.client.auth.TokenStorage` Protocol, `mcp.client.auth.oauth2.OAuthFlowError` / `OAuthRegistrationError` / `OAuthTokenError`. `mcp.shared.auth` provides `OAuthToken`, `OAuthClientInformationFull`, `OAuthClientMetadata`, `OAuthMetadata`.
- Test infrastructure: `tests/test_db_api.py:18-44` shows the FastAPI TestClient + isolated DB + `Encryptor` patch fixture pattern; `tests/test_mcp_integration.py:70` shows the `_test_http_client_override` httpx-seam pattern; `tests/test_mcp_oauth_errors.py` is the L0 smoke test. `tests/CONVENTIONS.md` documents 4 test patterns (no naming convention codified — leg follows the existing `test_*` convention used elsewhere in the suite without claiming a project-wide rule).
- Settings: `the_one/config.py::Settings` exposes `port: int = 8484` (env override `THE_ONE_PORT`).
- Existing FastAPI `lifespan` is at `the_one/interfaces/web/app.py:48` — it already drains the F4 pool on shutdown. L2 extends this same lifespan (NOT a parallel one).

## Outputs

What exists after this leg completes:

**New files**:

- `the_one/mcp/oauth/storage.py` — `MCPSourceTokenStorage` class implementing `mcp.client.auth.TokenStorage` Protocol; constructed with `(repo: MCPSourceRepository, source_id: str)`; reads/writes `OAuthToken` and `OAuthClientInformationFull` to the four managed `secrets` keys (`access_token`, `refresh_token`, `token_expires_at`, `dcr_credentials`). **Persisted `token_expires_at` is a Unix epoch float**; the SDK's `expires_in` (relative duration) is translated via `time.time()` on read and `time.time() + expires_in` on write. `get_tokens()` returns `None` only when `access_token` is absent; partial state (e.g. token without refresh_token) returns a valid `OAuthToken` with `refresh_token=None`. Persists via `repo.update(source)` on every `set_*`. Race contract: last-writer-wins is accepted; concurrent `set_tokens` calls from parallel tool invocations may briefly serialize behind the DB UPDATE, both writes typically write the same new token (same refresh leads to same response), so the race is observable only as wasted writes, not corruption.
- `the_one/mcp/oauth/_state.py` — In-memory pending-flow registry: `_pending: dict[str, PendingFlow]` keyed by `state` token. `PendingFlow` is a small dataclass: `code_future: asyncio.Future[tuple[str, str | None]]`, `created_at: float`, `source_id: str`, `tool_call_id: str | None`, `chat_session_id: str`. Module exposes:
  - `register(state, source_id, tool_call_id, chat_session_id) -> asyncio.Future[tuple[str, str | None]]`
  - `peek(state) -> PendingFlow | None` (does NOT pop — used by `oauth_callback` route to look up `chat_session_id` for broadcast)
  - `resolve(state, code, returned_state) -> bool` (pops + sets future result; returns False if state is unknown / already resolved)
  - `fail(state, error: Exception) -> bool` (pops + sets future exception; returns False if unknown)
  - `_sweep_expired() -> int` (called from periodic task at lifespan startup; returns count removed)
  - `_periodic_sweep_loop()` (the lifespan-managed task body)
  - `_pending` dict is NOT public; tests reset it via a fixture-scoped `_pending.clear()` to ensure isolation.
  - Module-private `_TTL_SECONDS = 600`. Module docstring documents non-persistence-across-restart trade-off.
- `the_one/mcp/oauth/handlers.py` — Single paired-factory function (cycle-1 H3 resolution):
  - `make_oauth_handlers(chat_session_id: str, source_id: str, tool_call_id: str | None, resource_metadata_url: str | None) -> tuple[redirect_handler, callback_handler]`. Both handlers share a `state_box: asyncio.Future[str]` constructed inside the factory:
    - `redirect_handler(authorization_url)`: parses `state` from URL; registers via `_state.register(state, source_id, tool_call_id, chat_session_id)`; resolves `state_box` with the parsed `state`; broadcasts `auth_required` to the chat session looked up from `_sessions[chat_session_id]`.
    - `callback_handler()`: awaits `state_box` to learn the state token; awaits `_state.peek(state).code_future`; returns `(code, returned_state)`. Errors propagate (e.g. `_state.fail` resolves the code_future with an exception, which is re-raised here).
  - Both handlers close over `(chat_session_id, source_id, tool_call_id, resource_metadata_url, state_box)` — closure capture pinned per cycle-2 M5.
- `the_one/mcp/oauth/manual_metadata.py` — `ManualOAuthClientProvider(OAuthClientProvider)` subclass that **overrides `async_auth_flow`** with a near-verbatim copy of the parent body, eliding only the PRM/OASM discovery loops and the DCR branch (per Context cycle-2 NEW-H1). Constructor takes `manual_metadata: ManualOAuthMetadata` (a small dataclass with `client_id`, `auth_endpoint`, `token_endpoint`) plus all standard `OAuthClientProvider.__init__` args. The subclass also overrides `_initialize` to additionally pre-set `self.context.client_info` from the synthesized `OAuthClientInformationFull` so the 401-handler's DCR guard short-circuits. The override mirrors the FULL outer structure (lock + initialize + protocol_version + refresh + initial yield + 401-handler-with-elisions + 403-handler), NOT just the post-discovery body. Module docstring cites SDK file:symbol for re-verification on SDK upgrades. Module size: ~110 LOC (cycle-2 NEW-H1 honest estimate, up from ~50 LOC in cycle-1 draft).
- `tests/test_oauth_storage.py` — TokenStorage round-trip tests: get-when-absent → None; set-then-get round-trip with all fields; refresh-token rotation overwrites old token; partial-state get (no refresh_token) returns valid OAuthToken with `refresh_token=None`; `expires_in` ⇄ `expires_at` translation correctness (set with `expires_in=300`; advance time by 100 seconds; get returns `expires_in≈200`); `OAuthClientInformationFull` round-trip via `set/get_client_info` writes/reads `secrets["dcr_credentials"]`.
- `tests/test_oauth_state.py` — `_state` registry tests: register-resolve happy path; resolve-with-error path via `fail`; resolve-unknown-state returns False; sweep-expired removes entries older than TTL and resolves their futures with a timeout error (`OAuthFlowError`); concurrent-register returns distinct futures; collision-on-same-state raises `RuntimeError`; `peek` does NOT pop.
- `tests/test_oauth_callback_route.py` — `/api/oauth/callback` route tests (using the FastAPI TestClient pattern from `tests/test_db_api.py:18-44`):
  - Success: GET with valid `state` + `code` → resolves the future + returns 200 HTML containing `"Login successful"` + broadcasts `auth_resolved` to the chat session keyed by `entry.chat_session_id`.
  - Error: GET with `error=...` + valid `state` → calls `_state.fail` + returns 200 HTML containing `"Login failed"` + broadcasts `auth_failed`.
  - Unknown state: GET with `state` not in `_state` → returns 401 + does NOT broadcast.
  - Missing state param: GET with no `state` → returns 401 + does NOT broadcast.
  - HTML body contents (verbatim-message contract per `agents.md` Project Conventions): success body contains `"Login successful. You may close this tab."`; error body contains the `error_description` (HTML-escaped).
- `tests/test_oauth_secrets_api.py` — GET/PUT secrets protection tests:
  - GET strips: seed all 4 managed keys + `oauth_client_secret` via `repo.update`; assert `await client.get(...)` JSON has the 4 managed keys ABSENT from `secrets` and `oauth_client_secret` MASKED.
  - PUT preserves: seed managed keys; PUT with attacker payload `{"access_token": "evil"}`; assert via `repo.get` (NOT API GET, which strips) that stored `access_token` unchanged. Comment in test cites the deliberate API-bypass.
  - PUT preserves with innocent payload: seed managed keys; PUT with `{"oauth_client_secret": "__MASKED__"}`; assert via `repo.get` that all 4 managed keys still present unchanged.
  - PUT no-managed-keys-leak: seed source WITHOUT managed keys; PUT with `{"access_token": "evil"}`; assert via `repo.get` that `access_token` NOT written (drop-on-no-existing semantic).
- `tests/test_oauth_handlers.py` — handler tests with stubbed `_send_to_session`:
  - `make_oauth_handlers` returns paired callables; redirect resolves state-box and registers in `_state`; callback awaits both futures; the broadcast payload shape matches §4's contract.
  - Closure-capture invariant: 5 distinct calls to `make_oauth_handlers` with different args produce 5 distinct (redirect, callback) pairs whose closures are independent.
- `tests/test_oauth_manual_metadata.py` — `ManualOAuthClientProvider` override stake test (cycle-1 H1 + H5):
  - **Discovery short-circuit (A12)**: monkey-patch `httpx.AsyncClient` to fail any GET whose URL path contains `.well-known`; construct `ManualOAuthClientProvider(...)`; drive the auth flow up to the redirect_handler call; assert no `.well-known` request was attempted.
  - **SDK body-shape stake test (A12b)**: assert `inspect.getsource(OAuthClientProvider.async_auth_flow)` contains the substrings the override depends on (`for url in`, `_perform_authorization_code_grant`, `_inject_authorization_header`). If a future SDK bump removes any of these, the test fails loudly, signaling the override may need re-verification.

**Modified files**:

- `the_one/mcp/oauth/__init__.py` — `__all__` populated with public names: `MCPSourceTokenStorage`, `ManualOAuthClientProvider`, `make_oauth_handlers`, `start_periodic_sweep`, `stop_periodic_sweep` (the `_state` module's lifespan hooks exposed as a public lifespan API to avoid shadowing app.py's `_state` dict — see Implementation Guidance step 8).
- `the_one/interfaces/web/api.py` — Three changes:
  1. Add `_OAUTH_MANAGED_SECRET_KEYS = frozenset({"access_token", "refresh_token", "token_expires_at", "dcr_credentials"})` near the existing `_MASKED_API_KEY_SENTINEL` constant.
  2. `_mcp_source_response` extended to STRIP the four OAuth-managed keys from the secrets payload BEFORE `_mask_secrets` runs.
  3. `update_mcp_source` (PUT) extended to preserve the four OAuth-managed keys from `existing.secrets` UNCONDITIONALLY (after the existing per-key `__MASKED__` resolution loop) — incoming payload entries for those keys are dropped silently.
  4. New route `GET /api/oauth/callback` per §9; uses lazy import of `_sessions` and `_send_to_session` from `the_one.interfaces.web.app` inside the handler body to avoid a circular import (cycle-1 M2 fix).
- `the_one/interfaces/web/app.py` — Lifespan registers the periodic sweep task at startup and cancels it at shutdown. The existing F4 pool drain in the same lifespan is preserved unchanged.

**Net new test count target**: 14 new tests across 6 test files (final count locked at implementation; flight log records actual). Distribution: storage 5, state 6, callback route 5, secrets API 4, handlers 2, manual_metadata 2 = ~24 if test functions are split fine-grained; the artifact targets `12-15` distinct test functions (some sub-cases may be parametrized into single functions). The implementer picks the granularity; A14 sets the lower/upper bound.

**Net LOC target** (cycle-2 NEW-H1 honest re-sizing): ~330 LOC of new module code + ~300 LOC of tests = ~630 LOC total. Breakdown: storage.py ~80 LOC, _state.py ~80 LOC, handlers.py ~50 LOC, manual_metadata.py ~110 LOC, api.py changes ~100 LOC (route + strip/preserve + constant), app.py changes ~10 LOC (lifespan).

## Acceptance Criteria

- [x] **A1 — Module skeletons land**: `the_one/mcp/oauth/storage.py`, `_state.py`, `handlers.py`, `manual_metadata.py` all exist and import cleanly. `the_one/mcp/oauth/__init__.py::__all__` lists the public names (`MCPSourceTokenStorage`, `ManualOAuthClientProvider`, `make_oauth_handlers`, `start_periodic_sweep`, `stop_periodic_sweep`).
- [x] **A2 — TokenStorage round-trip with `expires_in` ⇄ `expires_at` translation**: `MCPSourceTokenStorage` round-trips `OAuthToken` and `OAuthClientInformationFull` through `MCPSourceRepository.update`. Stored values land in the four named secrets keys. Specifically:
  - `set_tokens(OAuthToken(access_token="a", refresh_token="r", expires_in=300, ...))` writes `secrets["token_expires_at"] = time.time() + 300` (plus or minus 1 second tolerance) and also writes the access_token + refresh_token + scope + token_type as appropriate.
  - `get_tokens()` reads `secrets["token_expires_at"]` and returns `OAuthToken(..., expires_in=max(0, expires_at - time.time()))`.
  - `set_tokens` with `OAuthToken(expires_in=None)` does NOT write `secrets["token_expires_at"]` (or clears it if previously set).
  - Refresh-token rotation: a second `set_tokens` call with a NEW token overwrites the OLD `access_token` AND `refresh_token` in one repo.update call. Verified by load-then-load-after-rotation assertion.
  - Partial state (e.g. `OAuthToken(access_token="x", refresh_token=None)`) round-trips with `refresh_token=None` returned by `get_tokens`.
- [x] **A3 — Pending-flow registry contract**: `register` returns a fresh `asyncio.Future`; `register` for an already-registered state raises `RuntimeError`; `resolve(state, code, returned_state)` resolves the future to `(code, returned_state)` and returns True; `resolve` on unknown/already-popped state returns False; `fail(state, error)` resolves the future with the given exception and returns True; `peek(state)` returns the entry without popping; `_sweep_expired` removes entries older than TTL and resolves their futures with `OAuthFlowError("OAuth flow timed out (10-minute TTL)")`. Sweeping is idempotent — calling twice in a row removes nothing the second call. Race protection: `_sweep_expired` guards `set_exception` with `if not future.done()`.
- [x] **A4 — Lifespan integration**: At FastAPI startup, `start_periodic_sweep()` is called; at shutdown, `stop_periodic_sweep()` is called. Verified by a test that uses `LifespanManager` (or manual lifespan invocation) and asserts the sweep task is in `asyncio.all_tasks()` mid-lifespan and absent post-shutdown. The existing F4 pool-drain in the lifespan continues to run unchanged.
- [x] **A5 — Paired handler factory + WebSocket broadcast**: `make_oauth_handlers(chat_session_id="abc123", source_id="src1", tool_call_id="tc1", resource_metadata_url="https://example/.well-known/oauth-protected-resource")` returns `(redirect_handler, callback_handler)` pair. Calling `redirect_handler("https://idp/authorize?state=S1&...")` (a) registers state `"S1"` via `_state.register` with `source_id="src1"`, `tool_call_id="tc1"`, `chat_session_id="abc123"`; (b) calls `_send_to_session(session_with_id_abc123, {"type": "auth_required", "source_id": "src1", "resource_metadata_url": ..., "tool_call_id": "tc1", "consent_url": "https://idp/authorize?state=S1&..."})`. Calling `callback_handler()` after another task calls `_state.resolve("S1", "code123", "S1")` returns `("code123", "S1")`. Test stubs `_send_to_session` via `monkeypatch.setattr` and asserts call args.
- [x] **A6 — Callback handler error propagation**: When `_state.fail("S1", OAuthFlowError("operator denied"))` is called by another task, `await callback_handler()` raises `mcp.client.auth.oauth2.OAuthFlowError` with message `"operator denied"`. The exception type is the SDK's actual `OAuthFlowError`, not a translated wrapper.
- [x] **A7 — `/api/oauth/callback` success path**: GET with valid `state` + `code` query params → calls `_state.resolve` + returns `HTMLResponse` (200 status) whose body contains the substring `"Login successful. You may close this tab."` + broadcasts `{"type": "auth_resolved", "source_id": entry.source_id, "tool_call_id": entry.tool_call_id}` to the chat session at `_sessions[entry.chat_session_id]`. End-to-end verification with FastAPI TestClient.
  - **A7b (sweep race, cycle-2 NEW-H2)**: GET with valid `state` after `_sweep_expired` has popped the entry (simulated by manually invoking the sweep mid-test) → `_state.resolve` returns False; route returns 200 HTML containing `"Login expired"` (NOT `"Login successful"`) AND does NOT broadcast `auth_resolved`. The chat UI never sees a successful login event for a failed flow.
- [x] **A8 — `/api/oauth/callback` error path**: GET with `error=access_denied` + `error_description=user denied` + valid `state` → calls `_state.fail` with an `OAuthFlowError("user denied")` + returns 200 HTML containing the substring `"Login failed"` AND the HTML-escaped `error_description` + broadcasts `{"type": "auth_failed", "source_id": ..., "error": "access_denied", "description": "user denied"}` to the chat session at `_sessions[entry.chat_session_id]`.
- [x] **A9 — `/api/oauth/callback` unknown / missing state**: GET with `state` not in `_state` returns 401; GET with no `state` query param returns 401. Neither broadcasts anything.
- [x] **A10 — GET `/api/mcp-sources/{id}` strips managed keys**: When the underlying source has all 4 managed keys + an `oauth_client_secret` in its stored `secrets`, the GET response payload's `secrets` dict does NOT contain any of `access_token`, `refresh_token`, `token_expires_at`, `dcr_credentials`, even as masked values. `oauth_client_secret` continues to be masked per the existing `_mask_secrets` pattern. Verified by writing all 5 keys directly via `repo.update`, then asserting `response_json["secrets"]` keys ⊂ {"oauth_client_secret"}.
- [x] **A11 — PUT `/api/mcp-sources/{id}` preserves managed keys (3 sub-cases)**:
  - **A11a (attacker payload)**: Seed managed keys via `repo.update`. PUT with `{"access_token": "attacker_value", "refresh_token": "evil"}`. Verify via `repo.get` (deliberate API bypass since GET strips) that stored `access_token` and `refresh_token` are unchanged from seeded values.
  - **A11b (innocent payload)**: Seed managed keys + `oauth_client_secret`. PUT with `{"oauth_client_secret": "__MASKED__"}` (sentinel preserves). Verify via `repo.get` that all 4 managed keys still present unchanged AND `oauth_client_secret` preserved.
  - **A11c (no-managed-keys-leak)**: Seed source WITHOUT managed keys. PUT with `{"access_token": "evil"}`. Verify via `repo.get` that `access_token` is NOT in stored `secrets`.
- [x] **A12 — Manual-entry subclass skips discovery (the actual stake test, cycle-1 H5)**: `tests/test_oauth_manual_metadata.py::test_manual_provider_skips_discovery_endpoints`: monkey-patches `httpx.AsyncClient` to fail any GET whose path contains `/.well-known/`; constructs `ManualOAuthClientProvider(server_url="https://api.example.com", client_metadata=..., storage=stub_storage, redirect_handler=stub_redirect, callback_handler=stub_callback, manual_metadata=ManualOAuthMetadata(client_id="cid", auth_endpoint="https://idp/authorize", token_endpoint="https://idp/token"))`; drives the auth flow up to the redirect_handler call; asserts no `.well-known` request was attempted. The stub redirect writes a known state, the stub callback returns a known code, the test verifies the override delegated correctly to the parent's auth-code-grant logic.
- [x] **A12b — SDK body-shape stake test (cycle-2 corrected substring set)**: `tests/test_oauth_manual_metadata.py::test_async_auth_flow_body_shape_pinned`: asserts `inspect.getsource(OAuthClientProvider.async_auth_flow)` contains all of `"for url in"`, `"_perform_authorization()"`, `"_handle_token_response"`, `"_add_auth_header"`, `"if response.status_code == 401"`, `"elif response.status_code == 403"`. Failure means the SDK has been bumped and the override may need re-verification. Substring set verified against `mcp==1.27.0` (`mcp/client/auth/oauth2.py` lines 491-628).
- [x] **A13 — Lint clean**: `docker compose exec the-one ruff check the_one/mcp/oauth/ tests/test_oauth_*.py the_one/interfaces/web/api.py the_one/interfaces/web/app.py` exits 0 BEFORE `[HANDOFF:review-needed]`.
- [x] **A14 — F5-MCP suite expansion**: `pytest tests/test_mcp_*.py tests/test_oauth_*.py -q --timeout=30` is green; F5-MCP test count is 119 + N where N ∈ [12, 15]. Pre-existing pool-shutdown failure (`tests/test_mcp_pool.py::test_acquire_lazy_spawn_creates_worker_and_returns_client`, carried from L0/L1) is NOT a regression and remains the only failure; flight-log entry records exact pre-leg baseline (re-confirmed at implementation start, since L1's working tree was dirty at design time).
- [x] **A15 — Full-suite regression neutral**: `pytest -q --timeout=30` shows the same 1 pre-existing failure carried from L0/L1; passed count grows by exactly N (the new L2 tests). No prior tests modified.
- [x] **A16 — Citation audit (per `leg/SKILL.md` Phase 2 item 7)**: BEFORE implementation begins,
  - `grep -rn "_mcp_source_response\|update_mcp_source\|_mask_secrets" tests/ the_one/` → record direct callers; confirm none break under L2's signature changes (none expected — L2 changes the BODY of `_mcp_source_response` and `update_mcp_source`, not their signatures; `_mask_secrets` is unchanged).
  - `grep -rn "MCPSourceRepository\b" the_one/ tests/` → confirm L2's `storage.py` is the only NEW caller; no signature change to existing methods.
  - `grep -rn "_send_to_session\b" the_one/ tests/` → confirm L2's `handlers.py` is the only NEW caller; no signature change.
  - Citation audit results (counts + list) recorded in this leg's flight-log entry.

## Verification Steps

- `grep -n "^class MCPSourceTokenStorage\|^def make_oauth_handlers\|^class ManualOAuthClientProvider\|^def start_periodic_sweep\|^def stop_periodic_sweep" the_one/mcp/oauth/*.py` → one match per symbol in the expected file.
- `grep -n "_OAUTH_MANAGED_SECRET_KEYS" the_one/interfaces/web/api.py` → confirm the strip-list is defined as a single named constant used in BOTH the GET-strip and PUT-preserve paths.
- `docker compose exec the-one python -c "from mcp.client.auth import OAuthClientProvider; from the_one.mcp.oauth.manual_metadata import ManualOAuthClientProvider; assert issubclass(ManualOAuthClientProvider, OAuthClientProvider)"` → succeeds.
- `docker compose exec the-one python -c "from the_one.mcp.oauth import MCPSourceTokenStorage, ManualOAuthClientProvider, make_oauth_handlers, start_periodic_sweep, stop_periodic_sweep; print('OK')"` → prints `OK`.
- `docker compose exec the-one ruff check the_one/mcp/oauth/ tests/test_oauth_*.py the_one/interfaces/web/api.py the_one/interfaces/web/app.py` → clean.
- `docker compose exec the-one pytest tests/test_oauth_storage.py tests/test_oauth_state.py tests/test_oauth_handlers.py tests/test_oauth_callback_route.py tests/test_oauth_secrets_api.py tests/test_oauth_manual_metadata.py -v --timeout=30` → all green; total test functions in [12, 15].
- `docker compose exec the-one pytest tests/test_mcp_*.py tests/test_oauth_*.py -q --timeout=30` → green at 119 + N.
- `docker compose exec the-one pytest -q --timeout=30` → 1252 + N passed, 2 skipped, 1 pre-existing failure (`test_acquire_lazy_spawn_creates_worker_and_returns_client`).

## Implementation Guidance

1. **Re-verify SDK contract against installed `mcp==1.27.0`** before drafting any module:
   - `docker compose exec the-one python -c "import inspect, mcp.client.auth.oauth2; print(inspect.getfile(mcp.client.auth.oauth2))"` → resolves the SDK install path.
   - Read `OAuthClientProvider.__init__`, `async_auth_flow`, `_perform_authorization_code_grant`, `_perform_dcr`, `_inject_authorization_header`, `OAuthContext` dataclass. Read `TokenStorage` Protocol verbatim. Read the `mcp.shared.auth` types.
   - Confirm the public exception types: `mcp.client.auth.oauth2.OAuthFlowError`, `OAuthRegistrationError`, `OAuthTokenError`. These are L2's translation targets.
   - **Lock the `OAuthToken` field set**: `access_token`, `token_type`, `expires_in`, `scope`, `refresh_token`. If the actual SDK shape differs, divert per Adaptation Criteria.

2. **Implement `the_one/mcp/oauth/storage.py`**:
   - `class MCPSourceTokenStorage(TokenStorage)`: `__init__(self, repo: MCPSourceRepository, source_id: str) -> None`.
   - `async def get_tokens(self) -> OAuthToken | None`:
     ```
     source = await self._repo.get(self._source_id)
     access = source.secrets.get("access_token")
     if not access:
         return None
     expires_at = source.secrets.get("token_expires_at")
     expires_in = None
     if isinstance(expires_at, (int, float)):
         expires_in = max(0, int(expires_at - time.time()))
     return OAuthToken(
         access_token=access,
         token_type=source.secrets.get("token_type", "Bearer"),
         expires_in=expires_in,
         refresh_token=source.secrets.get("refresh_token"),
         scope=source.secrets.get("scope"),
     )
     ```
   - `async def set_tokens(self, tokens: OAuthToken) -> None`:
     ```
     source = await self._repo.get(self._source_id)
     source.secrets["access_token"] = tokens.access_token
     source.secrets["token_type"] = tokens.token_type
     if tokens.refresh_token is not None:
         source.secrets["refresh_token"] = tokens.refresh_token
     if tokens.scope is not None:
         source.secrets["scope"] = tokens.scope
     if tokens.expires_in is not None:
         source.secrets["token_expires_at"] = time.time() + tokens.expires_in
     elif "token_expires_at" in source.secrets:
         del source.secrets["token_expires_at"]
     await self._repo.update(source)
     ```
   - `get_client_info()` / `set_client_info()`: store/load under `secrets["dcr_credentials"]` (a sub-dict). Add a `registration_method` field discriminator (`"dcr"` or `"manual"`) so L4's `connect_streamable_http` can pick the right provider class.
   - **Edge case**: malformed `token_expires_at` (string, None, etc.) — the type-guard at read time returns `expires_in=None` rather than crashing. This forces a refresh-on-next-call but keeps the connection alive.

3. **Implement `the_one/mcp/oauth/_state.py`**:
   - Module-level `_pending: dict[str, PendingFlow] = {}`.
   - `@dataclass class PendingFlow: code_future: asyncio.Future[tuple[str, str | None]]; created_at: float; source_id: str; tool_call_id: str | None; chat_session_id: str`.
   - `def register(state: str, *, source_id: str, tool_call_id: str | None, chat_session_id: str) -> asyncio.Future[tuple[str, str | None]]`: creates the future via `asyncio.get_running_loop().create_future()`; raises `RuntimeError` on collision.
   - `def peek(state: str) -> PendingFlow | None`: returns entry without popping.
   - `def resolve(state: str, code: str, returned_state: str | None) -> bool`: pops + sets future result; returns False if unknown.
   - `def fail(state: str, error: Exception) -> bool`: pops + future.set_exception; returns False if unknown.
   - `async def _sweep_expired() -> int`: walks `_pending`, removes entries older than `_TTL_SECONDS`, resolves their futures with `OAuthFlowError("OAuth flow timed out (10-minute TTL)")` (guard with `if not future.done()`).
   - `async def _periodic_sweep_loop()`: `while True: await asyncio.sleep(_TTL_SECONDS); await _sweep_expired()`. Catches `asyncio.CancelledError` to exit cleanly on lifespan shutdown.
   - `def start_periodic_sweep() -> asyncio.Task`: launches the loop, stores task in module-private `_sweep_task`. Idempotent: if already running, returns existing task.
   - `def stop_periodic_sweep() -> Awaitable[None]`: returns a coroutine that cancels the task and awaits its termination.

4. **Implement `the_one/mcp/oauth/manual_metadata.py` (cycle-2 NEW-H1: full-structure rewrite)**:

   The override mirrors the FULL outer structure of `OAuthClientProvider.async_auth_flow` (~140 LOC body in `mcp==1.27.0` at `mcp/client/auth/oauth2.py:async_auth_flow`). Read that source verbatim before writing. The override copy preserves: outer lock, `_initialize` call, `protocol_version` capture, refresh-retry path, initial `yield request`, the 401-handler outer try/except, Step 3 (scope selection), Step 5 (`_perform_authorization` + `_handle_token_response`), final `_add_auth_header + yield request`, and the entire 403 step-up branch. Three sections are elided/replaced: Step 1 (PRM discovery loop), Step 2 (OASM discovery loop), Step 4 DCR sub-branch.

   **Module structure**:

   ```python
   # the_one/mcp/oauth/manual_metadata.py
   from __future__ import annotations

   from dataclasses import dataclass
   from typing import AsyncGenerator

   import httpx
   from mcp.client.auth.oauth2 import OAuthClientProvider, logger
   from mcp.client.auth.utils import (
       extract_field_from_www_auth,
       extract_scope_from_www_auth,
       get_client_metadata_scopes,
   )
   from mcp.shared.auth import (
       OAuthClientInformationFull,
       OAuthClientMetadata,
       OAuthMetadata,
       OAuthToken,
   )
   from mcp.shared.version import MCP_PROTOCOL_VERSION


   @dataclass(frozen=True)
   class ManualOAuthMetadata:
       """Operator-supplied OAuth endpoints for non-DCR-supporting AS."""
       client_id: str
       auth_endpoint: str
       token_endpoint: str


   class ManualOAuthClientProvider(OAuthClientProvider):
       """OAuthClientProvider variant that skips discovery + DCR.

       Used for AS that don't implement RFC 7591 DCR (e.g. GitHub at
       https://github.com/login/oauth) — operator pre-registers an OAuth
       app at the IDP UI and pastes the resulting client_id + endpoints
       into the chat-UI manual-entry form.

       SDK anchor: mcp/client/auth/oauth2.py::OAuthClientProvider.async_auth_flow
       (body verified against mcp==1.27.0 at design time; see A12b body-shape
       stake test). On every mcp package upgrade, re-run A12 + A12b before
       trusting this override.
       """

       def __init__(
           self,
           *args,
           manual_metadata: ManualOAuthMetadata,
           **kwargs,
       ) -> None:
           super().__init__(*args, **kwargs)
           self._manual_metadata = manual_metadata

       def _synthesized_oauth_metadata(self) -> OAuthMetadata:
           """Build the synthesized OAuthMetadata from manual-entry fields.

           OAuthMetadata required-field set verified at design time:
           issuer, authorization_endpoint, token_endpoint. Other fields
           default per SDK. response_types_supported defaults to
           ["code"] which matches our auth-code+PKCE flow.
           """
           # Issuer best-effort: rsplit the auth endpoint at the last '/'.
           # For typical auth_endpoints (e.g. github's /login/oauth/authorize),
           # this gives a sensible issuer URL.
           issuer = self._manual_metadata.auth_endpoint.rsplit("/", 1)[0]
           return OAuthMetadata(
               issuer=issuer,
               authorization_endpoint=self._manual_metadata.auth_endpoint,
               token_endpoint=self._manual_metadata.token_endpoint,
           )

       def _synthesized_client_info(self) -> OAuthClientInformationFull:
           """Build the synthesized client info from the manual client_id."""
           return OAuthClientInformationFull(
               client_id=self._manual_metadata.client_id,
               redirect_uris=self.context.client_metadata.redirect_uris,
           )

       async def _initialize(self) -> None:
           """Initialize bookkeeping + pre-set client_info from manual entry.

           Calls super()._initialize() first to load any persisted tokens,
           then injects the manual client_info if not already present so
           the 401-handler's DCR branch short-circuits.
           """
           await super()._initialize()
           if not self.context.client_info:
               synthesized = self._synthesized_client_info()
               self.context.client_info = synthesized
               await self.context.storage.set_client_info(synthesized)

       async def async_auth_flow(
           self, request: httpx.Request
       ) -> AsyncGenerator[httpx.Request, httpx.Response]:
           """Override of OAuthClientProvider.async_auth_flow.

           Mirrors the parent body verbatim with three elisions in the 401
           handler: PRM discovery loop, OASM discovery loop, DCR sub-branch.
           See class docstring for SDK-version risk notes.
           """
           async with self.context.lock:
               if not self._initialized:
                   await self._initialize()

               # Capture protocol version from request headers
               self.context.protocol_version = request.headers.get(MCP_PROTOCOL_VERSION)

               if not self.context.is_token_valid() and self.context.can_refresh_token():
                   refresh_request = await self._refresh_token()
                   refresh_response = yield refresh_request

                   if not await self._handle_refresh_response(refresh_response):
                       self._initialized = False

               if self.context.is_token_valid():
                   self._add_auth_header(request)

               response = yield request

               if response.status_code == 401:
                   try:
                       # ELIDED — Step 1 (PRM discovery): manual path bypasses RFC 9728
                       self.context.protected_resource_metadata = None

                       # ELIDED — Step 2 (OASM discovery): manual entry supplies metadata
                       self.context.oauth_metadata = self._synthesized_oauth_metadata()

                       # Step 3 (scope selection) — preserved verbatim; with PRM=None,
                       # scope falls back to www-auth header + manual oauth_metadata
                       self.context.client_metadata.scope = get_client_metadata_scopes(
                           extract_scope_from_www_auth(response),
                           self.context.protected_resource_metadata,
                           self.context.oauth_metadata,
                       )

                       # ELIDED — Step 4 DCR branch: client_info already set in _initialize

                       # Step 5 (auth + token exchange) — preserved verbatim
                       token_response = yield await self._perform_authorization()
                       await self._handle_token_response(token_response)
                   except Exception:
                       logger.exception("OAuth flow error")
                       raise

                   # Retry with new tokens
                   self._add_auth_header(request)
                   yield request
               elif response.status_code == 403:
                   # 403 step-up scope reauth — preserved verbatim from parent
                   error = extract_field_from_www_auth(response, "error")

                   if error == "insufficient_scope":
                       try:
                           self.context.client_metadata.scope = get_client_metadata_scopes(
                               extract_scope_from_www_auth(response),
                               self.context.protected_resource_metadata,
                           )
                           token_response = yield await self._perform_authorization()
                           await self._handle_token_response(token_response)
                       except Exception:
                           logger.exception("OAuth flow error")
                           raise

                   self._add_auth_header(request)
                   yield request
   ```

   - **Verify against the SDK source first**: `docker compose exec the-one python -c "import inspect, mcp.client.auth.oauth2 as m; print(inspect.getsource(m.OAuthClientProvider.async_auth_flow))"` — diff the body against the override's preserved sections. If the SDK body has drifted (new step inserted, refactored helper names), the override must be updated to match before tests will pass.
   - **Required `OAuthMetadata` fields** verified at design time: only `issuer`, `authorization_endpoint`, `token_endpoint` are required (cycle-2 review confirmed against `mcp.shared.auth:108-135`). Other fields are optional and default per SDK.
   - **Required `OAuthClientInformationFull` fields**: `client_id` is required; `redirect_uris` should be passed through from `self.context.client_metadata.redirect_uris` so the AS issues the redirect to our loopback callback URL.
   - **Edge case (issuer derivation)**: for non-standard auth-endpoint URL shapes, the rsplit-at-last-slash issuer may be wrong but is non-fatal (issuer is informational; the actual `authorization_endpoint` and `token_endpoint` are the load-bearing fields). Future flight could add `issuer` as an explicit ManualOAuthMetadata field if operators report broken behavior.
   - **Edge case (super()._initialize raises)**: if the parent's `_initialize` raises, `client_info` is not pre-set, but the lock has not been entered yet so the next call retries cleanly.

5. **Implement `the_one/mcp/oauth/handlers.py`**:
   ```
   from mcp.client.auth.oauth2 import OAuthFlowError
   from urllib.parse import parse_qs, urlsplit

   def make_oauth_handlers(
       chat_session_id: str,
       source_id: str,
       tool_call_id: str | None,
       resource_metadata_url: str | None,
   ) -> tuple[
       Callable[[str], Awaitable[None]],
       Callable[[], Awaitable[tuple[str, str | None]]],
   ]:
       state_box: asyncio.Future[str] = asyncio.get_running_loop().create_future()

       async def redirect_handler(authorization_url: str) -> None:
           qs = parse_qs(urlsplit(authorization_url).query)
           state = qs.get("state", [None])[0]
           if state is None:
               raise OAuthFlowError("Authorization URL missing state parameter")
           _state.register(
               state,
               source_id=source_id,
               tool_call_id=tool_call_id,
               chat_session_id=chat_session_id,
           )
           if not state_box.done():
               state_box.set_result(state)
           # Lazy-import to avoid app.py ↔ api.py circular at module level
           from the_one.interfaces.web.app import _sessions, _send_to_session
           session = _sessions.get(chat_session_id)
           if session is not None:
               await _send_to_session(session, {
                   "type": "auth_required",
                   "source_id": source_id,
                   "resource_metadata_url": resource_metadata_url,
                   "tool_call_id": tool_call_id,
                   "consent_url": authorization_url,
               })

       async def callback_handler() -> tuple[str, str | None]:
           state = await state_box
           entry = _state.peek(state)
           if entry is None:
               raise OAuthFlowError("Pending flow not registered")
           return await entry.code_future

       return redirect_handler, callback_handler
   ```

   **Important** (cycle-2 NEW-M1): `make_oauth_handlers` calls `asyncio.get_running_loop().create_future()` synchronously, which raises `RuntimeError: no running event loop` if called outside an async context. Production usage is fine (L4 calls this from inside `connect_streamable_http`, which runs in an async context). Tests MUST construct handlers inside `async def test_...` bodies — synchronous fixtures cannot construct them. Document this constraint in the module docstring.

6. **Implement `/api/oauth/callback` route in `the_one/interfaces/web/api.py`**:
   ```
   from fastapi.responses import HTMLResponse
   import html as _html

   @router.get("/oauth/callback")
   async def oauth_callback(
       code: str | None = None,
       state: str | None = None,
       error: str | None = None,
       error_description: str | None = None,
   ) -> HTMLResponse:
       from the_one.mcp.oauth import _state as oauth_state
       from the_one.interfaces.web.app import _sessions, _send_to_session
       from mcp.client.auth.oauth2 import OAuthFlowError

       if state is None:
           raise HTTPException(status_code=401, detail="Missing state parameter")
       entry = oauth_state.peek(state)
       if entry is None:
           raise HTTPException(status_code=401, detail="Unknown or expired state")

       if error is not None:
           oauth_state.fail(state, OAuthFlowError(error_description or error))
           session = _sessions.get(entry.chat_session_id)
           if session is not None:
               await _send_to_session(session, {
                   "type": "auth_failed",
                   "source_id": entry.source_id,
                   "error": error,
                   "description": error_description,
               })
           safe_desc = _html.escape(error_description or error)
           return HTMLResponse(
               f"<h1>Login failed</h1><p>{safe_desc}</p>",
               status_code=200,
           )

       # cycle-2 NEW-H2: check resolve's return value to handle the
       # peek-then-resolve race with _sweep_expired
       resolved = oauth_state.resolve(state, code or "", state)
       if not resolved:
           # Sweep raced between our peek and resolve; the future was
           # already failed with a timeout. Don't broadcast auth_resolved
           # — the chat UI must not see a successful login event for a
           # flow that actually failed.
           return HTMLResponse(
               "<h1>Login expired</h1><p>The login window has closed. "
               "Please re-trigger the original action to retry.</p>",
               status_code=200,
           )
       session = _sessions.get(entry.chat_session_id)
       if session is not None:
           await _send_to_session(session, {
               "type": "auth_resolved",
               "source_id": entry.source_id,
               "tool_call_id": entry.tool_call_id,
           })
       return HTMLResponse(
           "<h1>Login successful</h1><p>You may close this tab.</p>",
           status_code=200,
       )
   ```

   Lazy imports (`from the_one.interfaces.web.app import ...` inside handler body) avoid the api.py ↔ app.py circular at module load time. `the_one.mcp.oauth._state` is also lazily imported to keep the module-load order consistent.

7. **GET response strip + PUT preserve in `the_one/interfaces/web/api.py`**:
   - Add `_OAUTH_MANAGED_SECRET_KEYS = frozenset({"access_token", "refresh_token", "token_expires_at", "dcr_credentials"})` near the existing `_MASKED_API_KEY_SENTINEL` constant.
   - In `_mcp_source_response`: build a stripped copy `visible = {k: v for k, v in source.secrets.items() if k not in _OAUTH_MANAGED_SECRET_KEYS}`. Pass `visible` to `_mask_secrets` instead of `source.secrets`. The unmodified source dict remains in memory; only the response payload is stripped.
   - In `update_mcp_source`: AFTER the existing `__MASKED__` per-key resolution loop, but BEFORE `existing.model_copy(update=data)`, overlay the four managed keys from `existing.secrets`:
     ```
     for key in _OAUTH_MANAGED_SECRET_KEYS:
         if key in existing.secrets:
             resolved_secrets[key] = existing.secrets[key]
         elif key in resolved_secrets:
             # Incoming payload tried to set a managed key on a source
             # that doesn't have one yet; drop it. Only the OAuth flow
             # writes these keys.
             del resolved_secrets[key]
     data["secrets"] = resolved_secrets
     ```
   - The existing per-key `__MASKED__` sentinel logic continues unchanged for all OTHER secret keys (e.g. `oauth_client_secret`, `GITHUB_TOKEN`).

8. **Lifespan integration in `the_one/interfaces/web/app.py`**:
   - Locate the existing `@asynccontextmanager async def lifespan(...)` (drains the F4 pool on shutdown).
   - At startup, BEFORE the existing pool drain code: `from the_one.mcp.oauth import start_periodic_sweep; start_periodic_sweep()`.
   - At shutdown, AFTER the existing pool drain code: `from the_one.mcp.oauth import stop_periodic_sweep; await stop_periodic_sweep()`.
   - The `_state` module is imported via the public `start_periodic_sweep` / `stop_periodic_sweep` API, NOT directly — this avoids shadowing the existing `_state: dict[str, Any]` dict at app.py:103.

9. **Tests** (~12-15 across 6 files):

   - **Pending-flow registry isolation**: every test file that touches `_state` includes a fixture-scoped clear:
     ```python
     @pytest.fixture(autouse=True)
     def _reset_oauth_state():
         from the_one.mcp.oauth import _state as oauth_state
         oauth_state._pending.clear()
         yield
         oauth_state._pending.clear()
     ```
     The periodic sweep task is NOT started in unit tests (only the lifespan integration test starts it explicitly), so this reset cannot race with a sweep iteration.

   - **Route + secrets-API tests**: reuse the `tests/test_db_api.py:18-44` fixture pattern (isolated DB + `Encryptor` patch + ASGITransport TestClient).

   - **Callback-route test fixture for Session/_sessions broadcast** (cycle-2 NEW-M2): the lazy `from the_one.interfaces.web.app import _sessions, _send_to_session` inside `oauth_callback` resolves to the real `app.py` module's globals — NOT to the test_app's. So A7/A8 tests must construct a stub Session in `app._sessions[chat_session_id]` AND patch `app._send_to_session` to capture broadcast calls:
     ```python
     # tests/test_oauth_callback_route.py (sketch)
     import pytest
     from unittest.mock import AsyncMock
     from the_one.interfaces.web import app as web_app

     @pytest.fixture
     async def chat_session_in_app(monkeypatch):
         """Place a stub Session in app._sessions and capture broadcasts."""
         broadcast_calls: list[tuple] = []
         async def capture(session, payload, exclude=None):
             broadcast_calls.append((session.id, payload))
         monkeypatch.setattr(web_app, "_send_to_session", capture)

         # Construct a minimal Session — Agent can be a Mock since the
         # callback route never touches it
         from the_one.interfaces.web.app import Session
         from datetime import datetime, timezone
         session = Session(
             id="test-chat-1",
             agent=AsyncMock(),
             created=datetime.now(timezone.utc).isoformat(),
         )
         web_app._sessions["test-chat-1"] = session
         try:
             yield session, broadcast_calls
         finally:
             web_app._sessions.pop("test-chat-1", None)
     ```
     The fixture is autouse-scoped per test file as needed; A7's success-path test asserts `broadcast_calls == [("test-chat-1", {"type": "auth_resolved", ...})]`.

   - **Handler unit tests**: monkeypatch path for `_send_to_session` is `the_one.interfaces.web.app._send_to_session` (NOT `the_one.mcp.oauth.handlers._send_to_session`) because the handler does a `from ... import` lookup against the source module on EACH call. Verified: `monkeypatch.setattr(web_app, "_send_to_session", capture)` is picked up by subsequent lazy imports.

   - **`_state` and `storage` unit tests**: use plain `pytest.mark.asyncio` + `MCPSourceRepository` constructed against an in-memory aiosqlite. No FastAPI needed.

   - **`ManualOAuthClientProvider` test**: use `httpx.MockTransport` (per `tests/CONVENTIONS.md`) to fail any `.well-known` URL — assert no GET request to `.well-known` is made.

10. **Pre-implementation citation audit** (per `leg/SKILL.md` Phase 2 item 7) — RUN BEFORE writing any code:
    - `cd ~/projects/the-one && grep -rn "_mcp_source_response\|update_mcp_source" tests/ the_one/`
    - `cd ~/projects/the-one && grep -rn "_mask_secrets\b" tests/ the_one/`
    - `cd ~/projects/the-one && grep -rn "MCPSourceRepository\b" the_one/ tests/`
    - `cd ~/projects/the-one && grep -rn "_send_to_session\b" the_one/ tests/`
    - Record results (counts + brief list) in this leg's flight-log entry under "Citation audit results".

11. **Lint + post-completion checklist** (per leg-execution phase file):
    - Run `docker compose exec the-one ruff check ...` on every changed file BEFORE `[HANDOFF:review-needed]`.
    - Update flight-log.md with: pre-edit SHA, files changed (LOC delta), test count delta (re-confirmed pre-leg baseline first), citation audit results, any deviations from this artifact, the SDK shape verification result (item 1 above).
    - Update flight.md L2 checkbox + leg artifact status to `landed` ONLY (NOT `completed` — flight-final review post-L5 commits).
    - **Do NOT commit.** Do NOT signal `[COMPLETE:leg]`. Signal `[HANDOFF:review-needed]` instead so the orchestrator can spawn the next-leg cycle.

## Edge Cases

- **State token collision in `_state.register`**: SDK generates URL-safe random states; collision probability is negligible. Treat collision as a programming error → raise `RuntimeError`. Test asserts the raise (A3).
- **Future already done when `_sweep_expired` runs**: race between successful callback resolution and TTL sweep. Guard with `if not future.done()` (A3).
- **Server restart mid-flow**: `_pending` is in-memory only. Operator's IDP redirect lands at `/api/oauth/callback` post-restart; route returns 401 unknown-state; UI shows the operator a "Re-trigger the failed tool call to retry login" message (UI text is L5's; L2 only ensures the 401 is correct). Documented in `_state.py`'s module docstring.
- **OAuth-managed key set in `secrets` via direct DB write before any flow**: `_mcp_source_response` strips them anyway; PUT preserves them anyway. Operator-via-SQL writes are not a supported path — they go through `repo.update`.
- **Concurrent OAuth flows for the same MCP source**: each `register` call uses its own random `state` token; `_pending` keys are state-scoped. No conflict. Race protection: `set_tokens` from two parallel flows is last-writer-wins; both writes typically commit the same fresh token from the same refresh, so observable corruption is unlikely. Documented in `storage.py`'s docstring.
- **MCP source DELETED while a flow is pending in `_state`**: the future remains pending; eventually `_sweep_expired` resolves it with timeout error. The callback_handler raises that error. The chat UI surfaces "OAuth flow timed out". Operator-visible behavior is graceful. No special-case code needed.
- **`set_tokens` racing with operator's PUT on `/api/mcp-sources/{id}`**: PUT preserves managed keys from `existing.secrets` (A11). If `set_tokens` writes new tokens between `existing = await repo.get(...)` and `repo.update(...)` in the PUT handler, the PUT's `existing.secrets` snapshot is stale and the write loses the new tokens. Mitigation: this is a known F1 race; not in L2 scope to fix with row-level locking. Documented in flight-log; consistent with the M5 last-writer-wins disposition.
- **`HTMLResponse` vs `JSONResponse` for the callback route**: per §9, HTML is correct — the operator's browser tab is the renderer. Don't return JSON.
- **Closure leak in `make_oauth_handlers`**: the closure holds a reference to `chat_session_id` (a str — fine) plus the `state_box` Future (resolves once). Once both handlers are done, the GC collects normally. No leak.
- **`Session` lookup race**: `_sessions.get(entry.chat_session_id)` could return None if the operator closes the chat tab between flow start and callback. The route handles None gracefully (no broadcast, but still resolves the future and returns success HTML).

## Files Affected

- `the_one/mcp/oauth/__init__.py` — populate `__all__` with L2 exports.
- `the_one/mcp/oauth/storage.py` — NEW.
- `the_one/mcp/oauth/_state.py` — NEW.
- `the_one/mcp/oauth/handlers.py` — NEW.
- `the_one/mcp/oauth/manual_metadata.py` — NEW.
- `the_one/interfaces/web/api.py` — add `_OAUTH_MANAGED_SECRET_KEYS` constant; modify `_mcp_source_response` (strip); modify `update_mcp_source` (preserve); add `oauth_callback` route.
- `the_one/interfaces/web/app.py` — lifespan integration for `start_periodic_sweep` / `stop_periodic_sweep`.
- `tests/test_oauth_storage.py` — NEW.
- `tests/test_oauth_state.py` — NEW.
- `tests/test_oauth_handlers.py` — NEW.
- `tests/test_oauth_callback_route.py` — NEW.
- `tests/test_oauth_secrets_api.py` — NEW.
- `tests/test_oauth_manual_metadata.py` — NEW.
- Flight log + flight checkbox + leg artifact status — flight-final updates per the post-completion checklist.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria A1-A16 verified
- [x] `docker compose exec the-one ruff check the_one/mcp/oauth/ tests/test_oauth_*.py the_one/interfaces/web/api.py the_one/interfaces/web/app.py` clean
- [x] `docker compose exec the-one pytest tests/test_oauth_*.py tests/test_mcp_*.py -q --timeout=30` green at 119 + N
- [x] `docker compose exec the-one pytest -q --timeout=30` shows 1252 + N passed, 2 skipped, 1 pre-existing failure (unchanged) — re-confirmed pre-leg baseline at implementation start
- [x] SDK shape verification result recorded in flight log (item 1 above — locked the `OAuthToken` field set + `async_auth_flow` body anchor)
- [x] Citation audit grep results recorded in flight log
- [x] Update flight-log.md with the L2 progress entry (pre-edit SHA, files, LOC delta, test counts, deviations)
- [x] Set leg status to `landed` in this file's header
- [x] Check off leg L2 in `flight.md`
- [ ] Do NOT commit; do NOT update flight status to landed (final autonomous leg of flight is L5 → triggers flight-final review + commit)
- [ ] Signal `[HANDOFF:review-needed]` (NOT `[COMPLETE:leg]`)

## Citation Audit

11 citations verified against current code at leg design time (recon + cycle-1 review 2026-05-07):

- `MCPSourceRepository.get` / `update` / `_secrets_to_ciphertext` / `_ciphertext_to_secrets` — at `the_one/db/repositories.py:247-343` — OK.
- `MCPSource.secrets: dict[str, Any]` — at `the_one/db/models.py:50-72` — OK.
- `_mask_secrets` — at `the_one/interfaces/web/api.py:509` — OK (drift repaired from prior draft's "509-518 inside _mcp_source_response cluster").
- `_mcp_source_response` — at `the_one/interfaces/web/api.py:520-537` — OK.
- `update_mcp_source` PUT handler — at `the_one/interfaces/web/api.py:742-786` — OK.
- `_MASKED_API_KEY_SENTINEL` — at `the_one/interfaces/web/api.py:886` — OK.
- `_send_to_session` — at `the_one/interfaces/web/app.py:443-458` — OK.
- `Session` dataclass + `_sessions` dict — at `the_one/interfaces/web/app.py:113-147` — OK.
- Existing `_state: dict[str, Any]` — at `the_one/interfaces/web/app.py:103` — flagged for namespace-collision avoidance via the public `start_periodic_sweep` / `stop_periodic_sweep` API.
- `lifespan` (existing, F4 pool drain) — at `the_one/interfaces/web/app.py:48` — OK.
- L0 OAuth scaffold (`__init__.py:1-22`, `errors.py:1-50`) — OK (verified verbatim).
- `OAuthClientProvider.__init__` and `TokenStorage` Protocol — `mcp==1.27.0` SDK at `mcp/client/auth/oauth2.py` (containerized install path) — full signature verified including the `client_metadata_url` kwarg.
- `OAuthClientProvider.async_auth_flow` (cycle-1 verified, cycle-2 expanded) — body lives at `mcp/client/auth/oauth2.py:491-628` in `mcp==1.27.0`; ~140 LOC structured as: outer lock + `_initialize` + protocol_version capture + refresh-retry + initial yield + 401-handler (Steps 1-5: PRM discovery / OASM discovery / scope selection / DCR-or-CIMD / `_perform_authorization` + `_handle_token_response`) + 403 step-up handler. Discovery requests are issued via `yield` inside the 401 branch regardless of context state, so pre-populating context does NOT skip them. The override is a near-verbatim copy with PRM discovery, OASM discovery, and the DCR sub-branch elided; client_info is pre-set in `_initialize` so the DCR guard short-circuits. Body-shape stake test (A12b) pins the parent's structure with substrings `"for url in"`, `"_perform_authorization()"`, `"_handle_token_response"`, `"_add_auth_header"`, `"if response.status_code == 401"`, `"elif response.status_code == 403"`.
- `OAuthToken` field set — `access_token`, `token_type`, `expires_in` (relative), `scope`, `refresh_token` — verified; storage layer translates `expires_in` ⇄ `expires_at` per Implementation Guidance step 2.

No drift unrepaired; no `gone` citations. The single load-bearing risk — that the SDK's `async_auth_flow` body shifts in a future SDK upgrade — is captured by the A12b body-shape stake test.
