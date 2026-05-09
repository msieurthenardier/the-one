# Flight: Lazy OAuth 2.1 + PKCE for Remote MCP Servers

**Status**: completed
**Mission**: [MCP Integration](../../mission.md)

## Contributing to Criteria

- [ ] Remote MCP servers requiring OAuth are usable end-to-end from the chat UI without manual bearer-token paste: the operator initiates the flow lazily at first 401, completes consent through the IDP, and the resulting access and refresh tokens are stored encrypted and used on all subsequent calls — covering the spec's mandatory protections (PKCE, RFC 8707 Resource Indicators on auth and token requests, audience-bound tokens, refresh-token rotation, no token-passthrough to upstream services)
- [ ] Credentials never appear in plaintext outside the encryption boundary — not in API responses, not in logs, not in the chat surface — and the existing edit-form sentinel pattern is preserved so an operator can re-save an MCP source without retyping its secrets *(F5 contributes the OAuth-token surface; F1 already lands the sentinel pattern for static secrets)*
- [ ] Each layer of the integration has automated coverage proving its contract — **OAuth flow** *(F5 contributes)*; client-side connection lifecycle for both transports *(F2)*; idle-TTL reaper *(F4)*; sandbox spawn path *(F3)*

---

## Pre-Flight

### Objective

Land lazy, discovery-driven OAuth 2.1 + PKCE for remote MCP servers. The operator never enters OAuth fields in Settings — they enter only the MCP URL. When an attached agent makes a tool call that returns 401 with `WWW-Authenticate: Bearer realm=..., resource_metadata=<RFC 9728 PRM URL>`, the chat surface renders a "Login required" button. Clicking it opens a modal; the modal opens IDP consent in a new browser tab; the operator consents at the IDP; the loopback redirect resolves at `/api/oauth/callback`; tokens persist encrypted; the agent loop resumes the original tool call.

**Mission constraint amendment**: F5 introduces ONE new tool-result envelope (a generic `metadata` field on `ToolResult` carrying `{"is_auth_required": True, ...}` for the MCP path) that the agent loop recognizes and treats as "yield to human, pause execution, await `auth_resolved` event, then re-dispatch the deferred tool calls with the original arguments." This is the only sanctioned loop-level extension in this mission. The mission `Constraints` section was updated accordingly at F5 design time (2026-05-07). The iteration cap, continue-tool signal, capability-gate fallback, and dispatch-by-tool-name are all unchanged.

**Spec-strict posture**: per the user's design call — the MCP server author owns their OAuth-flow correctness end-to-end. F5 follows the spec verbatim and does NOT add adapters for non-compliant servers. Malformed AS metadata, missing `registration_endpoint`, broken refresh rotation, etc. surface as clear errors with operator-facing diagnostics; no in-the-one workarounds.

**SDK consumption decision (Architect cycle-1, H1)**: the official `mcp==1.27.0` SDK ships `mcp.client.auth.OAuthClientProvider(httpx.Auth)` which handles PKCE generation, RFC 9728 PRM discovery, RFC 8414 AS metadata discovery (with OIDC fallback), RFC 7591 DCR registration, RFC 8707 audience validation, pre-emptive token refresh, and httpx integration via `auth=` kwarg. F5 consumes this primitive and provides only: (a) a `TokenStorage` impl backed by `MCPSourceRepository`, (b) a `redirect_handler` that surfaces auth_required to the WebSocket, (c) a `callback_handler` that awaits the FastAPI route's resolution, (d) the `/api/oauth/callback` route, (e) an error-translation layer, (f) the agent-loop pause/resume primitive, (g) the chat-UI modal. This drops ~350 LOC of in-house OAuth code we would otherwise write and aligns with the user's "follow the spec, don't reinvent" framing.

### Open Questions

All resolved at flight design (Phase 3 user input + Architect cycle-1):

- [x] **OAuth flow shape** → **auth-code with loopback redirect**, implemented via SDK's `OAuthClientProvider` + redirect/callback handlers we provide. Device-code is NOT shipped — the-one is a desktop-app form factor; loopback is the spec-canonical desktop OAuth flow. SSH-only operators are NOT supported in F5. See §1.
- [x] **Client registration path** → **DCR-first via SDK**, user-entered fallback when AS doesn't advertise `registration_endpoint`. The SDK's `OAuthClientProvider` handles RFC 7591 DCR natively when supported. For non-DCR-supporting AS (notably GitHub at `https://github.com/login/oauth` per Architect cycle-1 H2 probe), the modal pops a manual-entry form with three fields (`client_id`, `auth_endpoint`, `token_endpoint`); the-one wraps them in a **`ManualOAuthClientProvider(OAuthClientProvider)` subclass** that overrides the metadata-discovery method to short-circuit when manual fields are present (Architect cycle-2 H5 resolution). Pre-registered provider table is dropped. See §2.
- [x] **Settings UI status badge** → **NO**. Per-source OAuth state surfaces ONLY in the chat UI (login-required button + modal). Settings stays minimal. See §6.
- [x] **Loop pause/resume primitive shape** → **generic `metadata: dict | None` field on `ToolResult`** (NOT a domain-specific flag). MCP path populates `metadata = {"is_auth_required": True, "resource_metadata_url": "...", "source_id": "...", "tool_call_id": "..."}`. Agent loop checks for `metadata.get("is_auth_required")` AFTER `_execute_tool` returns; on first match, defers ALL remaining tool calls in the same iteration to a pending list (preceding tool calls land in messages normally), broadcasts `auth_required` WebSocket event, exits the step. On `auth_resolved`, `Agent.resume_after_auth(deferred_tool_calls)` re-dispatches the deferred list in order. The generic `metadata` field is reusable for any future cross-provider payload (token-usage reporting, MCP elicitation events, etc.) — not coupled to OAuth specifically. See §4.
- [x] **F2-known-issue follow-on inclusion** → **YES, F5 owns it (scoped per Architect cycle-1 H2 reframe)**. Lands as L1 (BEFORE OAuth backend work). The retirement is specifically for the F4-pool-routed path: with L1's dispatcher-owned-stack pattern AND the F4 worker-task-per-entry pattern, cross-task `__aexit__` is structurally impossible because the F4 pool's `_entry_worker` always runs disconnect on the same task that ran connect. Direct `MCPClient(source)` usage outside the pool (the rare cross-task case) STILL hits the cross-task safety net swallow — that contract is preserved. F5's OAuth refresh path always routes through the F4 pool (via `acquire`), so the SDK's `OAuthClientProvider`-driven reconnect on token refresh inherits the clean dispatcher contract for free. See §3.
- [x] **HAT target** → **two-tier (Architect cycle-1 H2)**: Tier 1 (always-runs CI) is an in-repo FastMCP-shaped AS fixture with full DCR + AS metadata compliance, exercising all 5 steps of the lazy-auth lifecycle deterministically. Tier 2 (manual / quarterly) is GitHub MCP via the manual-entry path (Architect probed GitHub's AS at `https://github.com/login/oauth` and confirmed it does NOT serve `oauth-authorization-server` or `openid-configuration` `/.well-known/` endpoints AND does NOT implement DCR — so DCR-first cannot complete the chain end-to-end against the live GitHub target). The HAT plan accepts this real-world non-compliance and exercises the manual-entry fallback as the GitHub-MCP exercise. See §10.
- [x] **`procps` Dockerfile roll-in** → **YES**. Trivial; included in L0.
- [x] **Token storage shape + GET/PUT protection** → extend `secrets` JSON blob (per F1's locked schema; agents.md:53-56) with new top-level keys: `secrets["access_token"]`, `secrets["refresh_token"]`, `secrets["token_expires_at"]`, `secrets["dcr_credentials"]` (a sub-dict). Architect cycle-1 M2 fix: **GET `/api/mcp-sources/{id}` strips OAuth-managed keys from the response entirely** (NOT masked — stripped, since they're owned by the OAuth flow not the form); **PUT merge preserves OAuth-managed keys from `existing.secrets` regardless of incoming payload** (so a Settings-form save can never corrupt or null the OAuth state). The four OAuth-managed keys are owned exclusively by the `/api/oauth/callback` handler. See §5.
- [x] **Pause/resume persistence across server restart** → NOT implemented in F5. In-memory only. Documented as known limitation; consistent with the M01-M06 in-memory posture for in-flight loop state. UI behavior on browser refresh during pause: WebSocket reconnect re-emits the `auth_required` event from the agent's pending state if the FastAPI process is still alive; if the FastAPI process restarted, the pending state is lost and the operator must re-trigger the original tool call. See §4 trade-off.

### Design Decisions

**§1. OAuth flow shape — auth-code with loopback redirect, SDK-driven**

The SDK's `OAuthClientProvider` orchestrates the full flow. We provide three callbacks:

```python
# the_one/mcp/oauth/handlers.py (new in this flight)

async def redirect_handler(authorization_url: str) -> None:
    """Surface the consent URL to the operator's browser via WebSocket.

    Called by OAuthClientProvider when it has constructed the authorize URL.
    We broadcast an `auth_required` WebSocket event to the originating chat
    session with the URL; the chat UI's modal opens it in a new browser tab
    on the operator's Connect-button click.
    """

async def callback_handler() -> tuple[str, str | None]:
    """Block until the FastAPI /api/oauth/callback route resolves.

    Returns (code, state). Called by OAuthClientProvider after the redirect
    handler returns; awaits the future that the callback route resolves.
    """
```

The actual loopback URL is derived at flow-start time from the FastAPI app's bound port (NOT hardcoded `8484` — Architect cycle-1 L2): `http://127.0.0.1:{settings.port}/api/oauth/callback`. The redirect URI is registered with the AS via DCR or the manual-entry form, so the URL must be stable across the flow's lifetime.

Trade-off: requires a working browser on the operator's machine. SSH-only operators are NOT supported in F5. Device-code is a future flight if demand surfaces.

**§2. Client registration — DCR-first via SDK, user-entered fallback**

The SDK's `OAuthClientProvider` handles RFC 7591 DCR automatically when the AS advertises `registration_endpoint`. We provide:

1. **DCR happy path**: zero operator interaction. SDK calls `/register`, receives `client_id`, persists via our `TokenStorage` impl as `secrets["dcr_credentials"] = {"client_id": "...", "registration_method": "dcr", ...}`.
2. **Manual-entry fallback**: when AS does not advertise `registration_endpoint` (verified non-compliance: GitHub MCP), the modal surfaces three fields: `client_id`, `auth_endpoint`, `token_endpoint`. Operator pre-registers an OAuth app at the IDP's UI; pastes those three values; the-one constructs a `ManualOAuthClientProvider(OAuthClientProvider)` subclass that overrides the metadata-discovery method (per Architect cycle-2 H5 resolution — the SDK's `__init__` has no parameter to inject pre-known AS metadata; subclass + method-override is the cleanest extension point that doesn't depend on private-attribute mutation or hosting an extra HTTP service). Persisted as `secrets["dcr_credentials"] = {"client_id": "...", "auth_endpoint": "...", "token_endpoint": "...", "registration_method": "manual", ...}`.

The `client_secret` field stays at `secrets["oauth_client_secret"]` (per agents.md:56 lock) for confidential-client flows; PKCE-only public clients omit it.

Trade-off: GitHub MCP (the live HAT target) requires the manual path. The Tier-1 CI HAT exercises DCR; Tier-2 manual HAT exercises the manual fallback. Both paths are tested.

**§3. F2-known-issue retirement — scoped to F4-pool-routed path**

Per Architect cycle-1 H2: the README at `the_one/mcp/README.md §3` states *"AsyncExitStack alone does NOT solve cross-task disconnect. AsyncExitStack.aclose() invokes registered exit functions on the calling task — if that task differs from the one that ran the original `__aenter__`, anyio's guard fires regardless of the AsyncExitStack wrapping."* The L1 retirement claim is therefore SCOPED:

- **Retired for F4-pool-routed path**: the F4 pool's `_entry_worker` already holds connect AND disconnect on the same task. With L1's `_open_streamable_http_transport_stack` returning `(session, AsyncExitStack)`, the dispatcher inside `_transport_connect` consumes the non-CM helper and owns the stack within its own `@asynccontextmanager` body. The dispatcher's `__aexit__` runs on the same task as the dispatcher's `__aenter__` (both inside `_entry_worker`). Cross-task `__aexit__` is structurally impossible.
- **NOT retired for direct cross-task usage**: a caller that constructs `MCPClient(source)` directly (outside the F4 pool) and disconnects from a different task STILL hits the cross-task safety net swallow at `client.py::disconnect`. That contract is preserved unchanged.

The F5 refresh path always routes through the F4 pool (token refresh triggers a reconnect via `pool.acquire` re-entry; the SDK's `OAuthClientProvider` is wired into the httpx client used by `connect_streamable_http` which the dispatcher invokes from `_entry_worker`). So cross-task is structurally impossible for F5's flows.

L1 also lands `_open_stdio_transport_stack` for symmetry — same shape, same dispatcher consumption. Stdio doesn't have an OAuth path in F5, but the cross-task contract is identical.

The 9 prior callers of `connect_stdio` and the 1 prior caller of `connect_streamable_http` continue to use the existing `@asynccontextmanager` shape unchanged. **L1 includes the citation-audit grep step (per `leg/SKILL.md` Phase 2 item 7) for both transport functions and `_transport_connect` to confirm signature compatibility before implementation.**

**§4. Agent-loop pause/resume primitive — generic `metadata` field on `ToolResult`**

Per Architect cycle-1 H3: `ToolResult` lives at `the_one/llm/base.py:25`, NOT `the_one/agent/types.py` (which doesn't exist). Adding domain-specific OAuth fields would couple the LLM-base namespace to MCP. Instead, add a generic field:

```python
# the_one/llm/base.py:25 (existing dataclass extended)
@dataclass
class ToolResult:
    tool_call_id: str
    content: str
    is_error: bool = False
    metadata: dict[str, Any] | None = None  # NEW (F5): generic cross-provider payload
```

MCP populates `metadata = {"is_auth_required": True, "resource_metadata_url": "...", "source_id": "...", "tool_call_id": "..."}` when `MCPClient.call_tool` raises `MCPAuthRequired`. The `Agent` loop checks `result.metadata and result.metadata.get("is_auth_required")` AFTER `_execute_tool` returns.

**Multi-tool-call iteration semantic** (Architect cycle-1 M1; cycle-2 M4 carve-out):

```
For an iteration where response.tool_calls = [tc_A, tc_B, tc_C]:

1. Execute tc_A → ToolResult(no auth_required) → append to messages, yield
2. Execute tc_B → ToolResult(metadata.is_auth_required=True)
   → defer tc_B AND tc_C to self._deferred_tool_calls = [tc_B, tc_C]
   → yield Message.tool(result_B) so chat history reflects the auth_required surface
   → broadcast `auth_required` WebSocket event with result_B.metadata payload
   → return (exit step early; iteration counter NOT incremented further)
3. On `auth_resolved` event: Agent.resume_after_auth(self._deferred_tool_calls):
   → Re-dispatch tc_B (now with valid token) → ToolResult → append, yield
   → Re-dispatch tc_C → ToolResult → append, yield
   → Continue the iteration normally; iteration counter resumes from where it paused.
   → Clear self._deferred_tool_calls
```

**`continue` virtual signal carve-out** (cycle-2 M4): the auth_required check applies ONLY to results from `_execute_tool` (real tool calls). The synthetic `continue` tool is handled inline at `agent/core.py:113-122` without going through `_execute_tool`; its synthesized `ToolResult.metadata` is `None` by construction, so the check naturally short-circuits. No special-casing needed; documented here so future maintainers know `continue` is unaffected by the pause path.

**Handler closure capture** (cycle-2 M5): the SDK's `redirect_handler` callable signature is `Callable[[str], Awaitable[None]]` — receives only the auth URL. To broadcast `auth_required` with the `(session, source_id, tool_call_id)` payload required by §4's WebSocket protocol, the handler must close over those values at construction time. F5's per-tool-call provider construction in `connect_streamable_http` (or in the lazy 401 surface in `MCPClient.call_tool`) captures `(session, source_id, tool_call_id)` in the handler closure so the broadcast targets the originating chat session.

Rationale: preceding tool calls' results were ALREADY appended/yielded; rolling them back would corrupt history. Following tool calls were NOT executed; deferring them preserves the model's intended sequence and lets them succeed post-auth without re-prompting the model. Iteration counter NOT reset (resume continues the paused step).

`Agent.resume_after_auth(deferred: list[ToolCall]) -> AsyncIterator[Message]` is the new entry point.

**WebSocket protocol additions** (in `the_one/interfaces/web/app.py`):
- Outbound `auth_required` event: `{"type": "auth_required", "source_id": "...", "resource_metadata_url": "...", "tool_call_id": "...", "consent_url": "..."}`. UI renders the Login-required button + modal.
- Internal trigger from `/api/oauth/callback`: calls `agent.resume_after_auth(session._deferred_tool_calls)` on the originating session.

**Persistence**: pending pause-event lives in `Agent` instance memory only. Server restart loses the pause; documented as known limitation. Browser refresh during pause: WebSocket reconnect re-broadcasts the pending `auth_required` event from the live `Agent.session._deferred_tool_calls` state.

**§5. Token storage — extend F1 secrets JSON blob, with strict GET/PUT protection**

Architect cycle-1 M2 fix: OAuth-managed keys are NEVER in Settings-form scope. The four managed keys are:
- `secrets["access_token"]` (str)
- `secrets["refresh_token"]` (str)
- `secrets["token_expires_at"]` (float, Unix epoch seconds)
- `secrets["dcr_credentials"]` (dict — sub-fields `client_id`, optional `registration_access_token`, optional `registration_client_uri`, `registration_method` ∈ {"dcr", "manual"}, `registered_at`, plus `auth_endpoint` + `token_endpoint` for manual-entry path)

**API protections**:
1. **GET `/api/mcp-sources/{id}`**: `_mcp_source_response` STRIPS the four managed keys from the secrets payload BEFORE constructing the response. The form never sees them; the operator never sees them in the UI.
2. **PUT `/api/mcp-sources/{id}`**: the merge logic preserves the four managed keys from `existing.secrets` regardless of incoming payload. The form CANNOT corrupt or null them; only the OAuth flow can write them.
3. **`secrets["oauth_client_secret"]`** (the F1-defined confidential-client secret) continues to use the existing `__MASKED__` sentinel pattern — it's a form-managed secret, not an OAuth-flow-managed one.

**Refresh-token rotation** (handled by SDK's `OAuthClientProvider` per RFC 6749 §6 + RFC 8693): every successful refresh produces a NEW `access_token` AND a NEW `refresh_token`. Our `TokenStorage` impl persists both via `MCPSourceRepository.update`; the old `refresh_token` is overwritten. If refresh fails (401, invalid_grant), the SDK raises a typed exception we translate to `MCPOAuthRefreshFailed`; the next tool call surfaces a fresh `auth_required` event.

**Audience-binding** (handled by SDK's `OAuthClientProvider` per RFC 8707): every authorization request and token request includes a `resource=<canonical_mcp_url>` parameter. Audience validation on token receipt is delegated to the SDK; we trust the SDK's compliance. Never-passthrough is structurally guaranteed by `connect_streamable_http` reading the token from secrets and injecting it into the streamable-http transport's Authorization header only — it never goes anywhere else.

**§6. Settings UI: minimal — no OAuth status badge**

Per the user's design call: F5 does NOT add a per-source OAuth status badge in Settings. The chat surface is the only place OAuth state appears. Settings continues to show the F1 transport-aware form for `streamable-http`: `url` + `headers`. The legacy `oauth` config block (with `issuer_url`, `client_id`, `scopes`, `redirect_uri`) remains in F1's validator but becomes **operator-optional / advanced override only** — pre-populated read-only when the manual-entry path completes; otherwise empty. Operators don't fill it in for routine cases.

**§7. Discovery + DCR + PKCE — delegated to SDK's `OAuthClientProvider`**

Architect cycle-1 H1: do NOT write `pkce.py`, `discovery.py`, `registration.py`, or `flow.py`. The SDK's public auth surface (verified in cycle-2 against `mcp==1.27.0`) is exactly six exports: `OAuthClientProvider`, `PKCEParameters`, `TokenStorage`, `OAuthFlowError`, `OAuthRegistrationError`, `OAuthTokenError`. F5 only consumes `OAuthClientProvider` + implements `TokenStorage` + provides redirect/callback handlers — see §1, §2, §11 for the actual integration contracts. Discovery, PKCE, DCR, RFC 8707 audience binding, and pre-emptive token refresh are all internal to `OAuthClientProvider.async_auth_flow` and run automatically when we plug it into httpx via `auth=`.

We test our adapters (`TokenStorage` + handlers + `/api/oauth/callback` route + `ManualOAuthClientProvider` subclass) against the SDK's behavior. We do NOT test the SDK's own discovery/PKCE/DCR — that's the SDK author's responsibility.

**§8. (deleted — folded into §7)**

**§9. Loopback redirect handler — `/api/oauth/callback`**

New FastAPI route in `the_one/interfaces/web/api.py`:

```python
@router.get("/oauth/callback")
async def oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> HTMLResponse:
    """Loopback redirect handler for OAuth auth-code flow.

    Resolves the future awaited by `oauth.handlers.callback_handler`.
    Returns small HTML for operator-facing UX:
    "Login successful. You may close this tab." or error text.
    """
```

Behavior:
1. Looks up the pending-flow record by `state` (CSRF check; 401 if mismatched or expired/missing)
2. If `error` is set, resolves the awaited future with an error; broadcasts `auth_failed` WebSocket event; renders error HTML
3. Else resolves the awaited future with `(code, state)`; SDK's `OAuthClientProvider` exchanges code → tokens; our `TokenStorage` persists; we broadcast `auth_resolved`; render success HTML

The pending-flow registry lives in `the_one/mcp/oauth/_state.py` — keyed by state token, 10-minute TTL cleanup, in-memory.

**§10. HAT — two-tier (Tier 1 CI / Tier 2 manual)**

**Tier 1 (always-runs in CI)**: in-repo FastMCP-shaped AS fixture in `tests/fixtures/oauth/`. Implements:
- RFC 9728 PRM document
- RFC 8414 AS metadata document at `/.well-known/oauth-authorization-server`
- RFC 7591 DCR endpoint
- Local-key-signed access tokens with `aud` claim
- 5-minute token lifetime so refresh can be tested deterministically

5-step verification driven by Playwright:
1. **Pre-state**: configure fixture URL as streamable-http MCP source (no OAuth fields in form)
2. **Lazy 401 + button surfaces**: agent sends a tool-triggering message; chat surface shows Login-required button; agent step paused; WebSocket `auth_required` emitted
3. **Modal + consent**: click Login-required → modal opens → click Connect → consent URL opens → simulated consent (test-mode auto-approve) → callback resolves → `auth_resolved` emitted
4. **Resumed tool call**: modal closes; button clears; agent loop resumes; tool call returns successfully
5. **Refresh rotation**: artificially advance time to expire access_token; trigger another tool call; refresh runs transparently (no UI affordance); new tokens persist; tool call succeeds

**(F5 L1 verification, deferred from L1 unit-test layer)**: throughout the 5-step sequence, capture pytest caplog records at WARNING level for `the_one.mcp.client`. Assert that NO record matches `MCPClient transport close failed`. This is the empirical verification gate for L1's F2-known-issue retirement claim — L1 ships speculatively (the dispatcher rewrite MAY help; could not be verified at unit-test layer because real MCP subprocess required to make `initialize()` succeed and disconnect actually run). If the assertion fails, file a follow-up flight that reverts L1's `_open_*_transport_stack` helpers + dispatcher rewrite + README §3 update, and re-add F2-known-issue to mission Known Issues with a real diagnosis plan. F5 itself is NOT blocked by an L1 revert (L2-L5 don't depend on L1's mechanism working — they depend on the dispatcher and transports being functional, which they remain post-revert).

**Tier 2 (manual / quarterly)**: GitHub MCP at `https://api.githubcopilot.com/mcp/` via the manual-entry fallback path. Operator pre-registers a GitHub OAuth app at github.com/settings/developers with `callback URL = http://127.0.0.1:8484/api/oauth/callback` (the desktop form-factor default per `settings.port = 8484`; per cycle-2 M7, §1's runtime-port resolution selects this default value unless explicitly overridden by env var; pre-registration assumes the default); pastes `client_id`, `auth_endpoint = https://github.com/login/oauth/authorize`, `token_endpoint = https://github.com/login/oauth/access_token` into the modal's manual-entry form; consents at github.com; verifies a real tool call (e.g., list repos) succeeds. Documented as a manual procedure in `tests/HAT.md` or equivalent; not run in CI. **Note**: operators running the-one on a non-default port must update both their pre-registration AND the `settings.port` to match.

**Bonus (per Architect cycle-1 if approved)**: revoke + re-auth — delete the GitHub OAuth app's grant via github.com UI; trigger another tool call; verify the next 401 surfaces a fresh `auth_required` event.

Binary go/no-go: Tier 1 all 5 steps PASS = ✓ flight close. Tier 2 is an out-of-band validation; failures are filed as upstream non-compliance issues, not flight blockers.

**§11. Module placement — slim adapter layer over SDK**

```
the_one/mcp/oauth/
├── __init__.py        # public API: get_oauth_provider_for_source, oauth_callback handler
├── _state.py          # in-memory pending-flow registry (state token → asyncio.Future[(code, state)]); 10-min TTL
├── storage.py         # TokenStorage Protocol impl backed by MCPSourceRepository (~50 LOC)
├── handlers.py        # redirect_handler + callback_handler (broadcast `auth_required`; await callback) (~60 LOC)
├── manual_metadata.py # ManualOAuthClientProvider subclass that overrides metadata-discovery for non-DCR providers (cycle-2 H5 resolution) (~50 LOC)
└── errors.py          # MCPOAuthError hierarchy: translates SDK exceptions to the_one-side types
```

**Touchpoints OUTSIDE `oauth/`** (cycle-2 L4 — important for readers of §11 alone):
- `the_one/llm/base.py:25` — `ToolResult` gains `metadata: dict[str, Any] | None = None` field (L3)
- `the_one/agent/core.py::Agent.step` — auth_required check + deferral logic (L3)
- `the_one/agent/core.py::Agent.resume_after_auth` — new entry point (L3)
- `the_one/mcp/transports/streamable_http.py::connect_streamable_http` — provider construction with auth= injection (L4)
- `the_one/mcp/client.py::MCPClient.call_tool` — `MCPAuthRequired` exception path (L4)
- `the_one/interfaces/web/api.py` — `/api/oauth/callback` + `/api/oauth/manual-register` routes (L2/L5)
- `the_one/interfaces/web/app.py` — `auth_required` / `auth_resolved` WebSocket event broadcast (L3)
- `the_one/interfaces/web/static/js/chat.js` — event handlers + UI render (L5)
- `the_one/interfaces/web/static/js/oauth-modal.js` — new modal component (L5)

Public consumers:
- `connect_streamable_http` constructs an `OAuthClientProvider` (or `ManualOAuthClientProvider`) from `secrets["dcr_credentials"]` and our `TokenStorage`/`redirect_handler`/`callback_handler`; passes it as `auth=` to httpx.AsyncClient.
- The `/api/oauth/callback` route in `api.py` calls into `handlers.resolve_callback(state, code, error)`.
- Agent loop's `_execute_tool` catches `MCPAuthRequired` (raised by `MCPClient.call_tool` when SDK-level auth fails despite the `OAuthClientProvider` integration — e.g., refresh failed silently and no auth provider available).

Total new LOC: ~270 (down from ~600 in pre-cycle-1 design; +20 LOC vs cycle-1 estimate due to `ManualOAuthClientProvider` subclass for cycle-2 H5).

**§12. Cross-task safety with refresh — automatic via F4 pool routing**

Token refresh runs inside the SDK's `OAuthClientProvider` `auth_flow` generator. The httpx client invokes the refresh hook before each request; the SDK persists new tokens via our `TokenStorage` impl. A successful refresh does NOT require reconnecting the MCPClient — the new access_token is used on the next outgoing request via the `auth=` kwarg.

If the SDK detects token corruption or unrecoverable refresh failure, it raises an exception we translate to `MCPOAuthRefreshFailed`. The pool's `_entry_worker` sees the exception, evicts the entry, and re-acquire spawns a fresh `MCPClient` (and triggers the `auth_required` flow at the next 401).

**No cross-task disconnect** in the refresh path: the entire refresh happens within the active `_entry_worker` task. F4's worker-task-per-entry pattern + L1's dispatcher-owned-stack guarantee this.

### Prerequisites

- [x] F1, F2, F3, F4 `completed`
- [x] FastAPI app + WebSocket route at `/ws` exists; `_send_to_session` event broadcast pattern is in place (verified at `the_one/interfaces/web/app.py:454, 528-569`)
- [x] `Agent.step` loop dispatch path verified at `the_one/agent/core.py:50-148`
- [x] `ToolResult` dataclass at `the_one/llm/base.py:25` (corrected from earlier draft per Architect cycle-1 H3)
- [x] `Encryptor` rotation reuses single-key path (mission constraint)
- [x] Browser available on operator's machine (mission constraint — desktop-app form factor)
- [x] SDK's `mcp.client.auth.OAuthClientProvider` available in pinned `mcp==1.27.0`; verified at design time
- [x] In-repo OAuth fixture viable (FastMCP supports custom routes; can implement RFC 9728 + RFC 8414 + RFC 7591 endpoints)

### Pre-Flight Checklist

- [x] All 8 open questions resolved (above)
- [x] Design decisions documented (§§1-7, §9-12; §8 folded into §7)
- [x] Prerequisites verified
- [x] Validation approach defined (test strategy in legs L1-L5 + L6 HAT)
- [x] Legs defined (see In-Flight § Legs)
- [x] Architect design review cycle 1 — resolved 2026-05-07 (3 highs + 4 mediums + 3 lows addressed)
- [x] Architect design review cycle 2 — resolved 2026-05-07 (2 new highs H4 mechanical + H5 user-decided B subclass; 4 mediums + 3 lows addressed inline)
- [x] User approval (Phase 6) — granted 2026-05-07; flight transitioned planning → in-flight; agentic-workflow orchestration started

---

## In-Flight

### Technical Approach

Three layers:

1. **OAuth adapter layer** (`the_one/mcp/oauth/`): ~250 LOC of glue that consumes SDK's `OAuthClientProvider` and adapts it to the-one's `MCPSourceRepository`-backed token storage + WebSocket-based UI. We do NOT reimplement PKCE, discovery, DCR, audience binding, or refresh — those come from the SDK.
2. **Transport + agent-loop integration**: `connect_streamable_http` constructs an `OAuthClientProvider` from secrets and passes it to httpx. `MCPClient.call_tool` raises `MCPAuthRequired` on unrecoverable 401. Agent loop catches via the new `metadata.is_auth_required` flag on `ToolResult`. Multi-tool-call deferral semantic per §4.
3. **Chat UI**: WebSocket event handler in `chat.js` for `auth_required` / `auth_resolved`; modal component (`oauth-modal.js`) with Connect button + DCR/manual switching + status spinner.

**L1 lands FIRST** (F2-known-issue retirement scoped to F4-pool-routed path). **L0** is bootstrap (procps + scaffold).

### Checkpoints

- [ ] **C0** — `procps` in Dockerfile; `the_one/mcp/oauth/` package scaffolded with `__init__.py` + `errors.py` (with `MCPOAuthError` base + 3 subclasses: `MCPOAuthDiscoveryError`, `MCPOAuthRegistrationError`, `MCPOAuthRefreshFailed`) (L0)
- [ ] **C1** — `_open_streamable_http_transport_stack` (and stdio symmetry) lands; dispatcher consumes the non-CM helpers; F2-known-issue retired for F4-pool-routed path (verified by extending an L1a-style stake-test). Citation audit confirms 1+9 prior callers continue to work. (L1)
- [x] **C2** — OAuth SDK adapter: `storage.py` (TokenStorage backed by MCPSourceRepository), `handlers.py` (redirect_handler + callback_handler), `_state.py` (pending-flow registry), `manual_metadata.py` (synthetic OAuthMetadata for non-DCR), `/api/oauth/callback` route, `errors.py`. Tests use the in-repo OAuth fixture from L6 (lifted forward) for end-to-end validation. (L2)
- [ ] **C3** — Agent-loop pause/resume primitive: `metadata: dict | None = None` field on `ToolResult` (`the_one/llm/base.py:25`); `Agent.step` deferral logic + multi-tool semantic per §4; `Agent.resume_after_auth(deferred_tool_calls)` entry point; WebSocket protocol additions. Citation audit confirms `Agent.step` callers still work. (L3)
- [x] **C4** — Streamable-http transport OAuth integration: `connect_streamable_http` constructs `OAuthClientProvider` from secrets when present; `MCPClient.call_tool` raises `MCPAuthRequired` on auth failure; `Agent._execute_tool` catches and populates `metadata`. Citation audit confirms `MCPClient.call_tool` error-translation tests don't shadow the new branch. (L4) *(landed 2026-05-07; provider construction itself deferred to L6 per cycle-1 H1+H4 disposition — L4 ships only the `auth_provider` passthrough seam)*
- [x] **C5** — Chat UI: Login-required button + modal + WebSocket event handlers in `chat.js` and new `oauth-modal.js`; manual-entry form when DCR fails. Browser tests pass. Optional Accessibility Reviewer for this leg. (L5) *(landed 2026-05-07; full-scope per user-picked Option A — provider-construction factory + `/api/oauth/start` + `/api/oauth/manual-register` + UI + minimal AS fixture; 10 backend tests pass + 6 Playwright tests written but require Chromium install to execute; A11y Reviewer fixed 2 WCAG blocking issues inline)*
- [ ] **C6** — Tier-1 HAT 5-step verification against in-repo OAuth fixture: PASS in CI. Tier-2 HAT documented in `tests/HAT.md` for manual run against GitHub MCP. (L6)

### Adaptation Criteria

**Divert if**:

- L1 stake-test reveals dispatcher-owned-stack pattern fails to retire the F2-known-issue under F4-pool routing. Fall back to: keep the safety-net swallow firing on every disconnect; document the residual log noise; proceed with F5 OAuth without the cleanup. Escalate to user.
- SDK's `OAuthClientProvider` API surface differs materially from the cycle-1 verification (e.g., kwargs renamed, callback shape changed). Pin SDK harder; if upgrade required, do it as L0 sub-leg with explicit version bump.
- Per-source state machine for "DCR-supported" vs "manual-entry" needs more states than the modal can clearly surface. Revisit §2 + L5.
- Tier-1 HAT fixture's signed-token implementation conflicts with the SDK's audience-validation mechanism (e.g., SDK rejects locally-signed tokens). Fall back to: accept-any-signature mode in fixture; document as test-only invariant; proceed.
- Loopback port determination at flow-start time conflicts with multi-instance test runs (e.g., two pytest workers binding different ports). Add per-test port resolution; document.

**Acceptable variations**:

- L2 splitting into L2a (TokenStorage + state) + L2b (handlers + callback route) if combined LOC exceeds ~300.
- L4 reusing L2b's pending-flow state machine for the call_tool 401 path rather than constructing a separate flow trigger.
- L5 modal styling/copy details — refine inline at implementation per existing chat-UI design language.
- L6 Tier-2 HAT may be deferred to a follow-up validation pass after merge; not flight-blocking.

### Legs

> **Note**: tentative suggestions; refined per leg as work progresses.
>
> **Conventions for all legs**: leg artifacts use anchor-by-symbol-name (NOT `file.py:LINE`); each leg's post-completion checklist includes lint clean before `[HANDOFF:review-needed]`; leg artifacts include "stake-test probe" scripts when integration tests stake on a specific OS/SDK pattern; test-count reconciliation across Objective / Outputs / Acceptance Criteria sections; **citation audit MUST include "find direct callers of any public symbol whose signature changes" via grep against test files** (per F4 debrief R2 — codified in `mission-control` PR #5).
>
> **Citation convention boundary** (cycle-2 L6): the FLIGHT artifact (this document) uses `file.py:LINE` citations freely — it's a human-readable spec read top-to-bottom by reviewers. LEG artifacts use anchor-by-symbol-name to insulate against line-drift between leg-design time and leg-execution time (per F1 debrief recommendation). Both conventions are correct in their respective contexts.

- [x] `00-bootstrap` *(landed 2026-05-07)* — Dockerfile: add `procps` (alongside existing `bubblewrap` apt install). Scaffold `the_one/mcp/oauth/` package with empty `__init__.py` + `errors.py` defining `MCPOAuthError`, `MCPOAuthDiscoveryError`, `MCPOAuthRegistrationError`, `MCPOAuthRefreshFailed` (all subclass `MCPClientError`). Tests: 1 smoke test asserting all 4 error classes import and form a coherent hierarchy. ~1-2 new tests; ~30 LOC. Smallest leg in the flight.

- [x] `01-streamable-http-non-cm-helper` *(landed 2026-05-07)* — Land `_open_streamable_http_transport_stack` and `_open_stdio_transport_stack` (symmetric) per §3. Update `_transport_connect` dispatcher in `the_one/mcp/client.py` to consume the new non-CM helpers internally. Existing `@asynccontextmanager connect_streamable_http` and `connect_stdio` STAY UNCHANGED — preserve back-compat with their **1 + 9 = 10 prior async-CM callers** respectively (citation-audit-verified). **Citation audit (per `leg/SKILL.md` Phase 2 item 7)**: `grep -rn 'connect_streamable_http\|connect_stdio\|_transport_connect' tests/ the_one/` BEFORE implementation; confirm only the documented prior callers exist. Stake-test probe extending L1a's `TestAsyncExitStackContract`: dispatcher-owned-stack disconnect under F4 pool routing produces NO `WARNING MCPClient transport close failed` against real bwrap; direct `async with MCPClient(source)` continues to behave correctly. Update `the_one/mcp/README.md §3` to scope the retirement claim to F4-pool-routed path. ~5-7 new tests; F2/F3/F4 prior tests UNMODIFIED.

- [x] `02-oauth-sdk-adapter` *(landed 2026-05-07)* — Implement `the_one/mcp/oauth/storage.py` (TokenStorage Protocol impl reading/writing the four managed secret keys via `MCPSourceRepository`); `handlers.py` (`redirect_handler` broadcasts `auth_required` WebSocket event; `callback_handler` awaits the future from `_state`); `_state.py` (in-memory `dict[str, asyncio.Future[tuple[code, state] | OAuthError]]` keyed by state token; 10-min TTL cleanup task at app startup); `manual_metadata.py` (synthetic `OAuthMetadata` constructor from the manual-entry fields); `/api/oauth/callback` route in `the_one/interfaces/web/api.py` per §9. **GET/PUT secrets protection** (M2 fix): extend `_mcp_source_response` to strip the 4 OAuth-managed keys from secrets; extend the PUT merge to preserve them from `existing.secrets`. Tests use a stub OAuthClientProvider (or the actual SDK with HTTP responses stubbed via `httpx.MockTransport`) for end-to-end validation: storage round-trip, callback resolution, error path, GET strips managed keys, PUT preserves managed keys. ~12-15 new tests.

- [x] `03-agent-loop-pause-resume` *(landed 2026-05-07)* — Add `metadata: dict[str, Any] | None = None` to `the_one/llm/base.py::ToolResult`. Modify `Agent.step` per §4: check `result.metadata and result.metadata.get("is_auth_required")` after `_execute_tool`; defer the current and remaining tool calls in the iteration to `self._deferred_tool_calls`; yield the tool message; broadcast `auth_required`; exit step. Add `Agent.resume_after_auth(deferred: list[ToolCall]) -> AsyncIterator[Message]`: re-dispatches in order; clears deferred state; resumes iteration. WebSocket protocol additions. **Citation audit**: `grep -rn 'Agent\.step\|ToolResult' tests/ the_one/` BEFORE implementation; confirm: ToolResult new field is backward-compatible (default None); Agent.step caller signature unchanged. Tests: pause/defer multi-tool-call iteration (preceding result lands; following deferred); resume re-dispatches deferred in order; resume with empty deferred no-ops cleanly; pause-state-not-persisted-across-restart documented; browser-refresh-during-pause re-broadcasts. ~10-12 new tests.

- [x] `04-streamable-http-oauth-integration` *(landed 2026-05-07)* — Modify `connect_streamable_http` (the existing `@asynccontextmanager` AND the L1 non-CM helper) to: when `secrets["dcr_credentials"]` is present, construct `OAuthClientProvider` (or `ManualOAuthClientProvider` if `registration_method == "manual"`) with the storage/handlers/manual-metadata adapters, pass `auth=provider` to httpx.AsyncClient; otherwise no Authorization injection (lets the 401 surface naturally to trigger the lazy flow). Modify `MCPClient.call_tool` to detect `MCPAuthRequired` exceptions raised by the SDK's underlying httpx response handling; the SDK should raise its own auth exception we translate. Modify `Agent._execute_tool` to catch `MCPAuthRequired`, return `ToolResult(content="<auth required>", metadata={"is_auth_required": True, "resource_metadata_url": ..., "source_id": ..., "tool_call_id": tc.id})`. **Citation audit**: `grep -rn 'MCPClient\.call_tool\|connect_streamable_http' tests/`; confirm error-translation tests don't shadow the new `MCPAuthRequired` branch. Stake-test probe: validate that the SDK's `streamable_http_client` + `OAuthClientProvider` actually surfaces a typed exception (vs. an httpx 401) on auth failure; pin behavior. **Test seam adapter** (cycle-2 M6): the existing `_test_http_client_override` test path mutates an injected `httpx.AsyncClient`'s headers post-construction, but `auth=` must be set at httpx-client construction time. Extend the test seam to accept either a client OR a factory `Callable[[], httpx.AsyncClient]` so OAuth-enabled tests can produce fresh per-call clients with `auth=` attached; preserve the legacy mutate-headers path for non-OAuth tests. Tests: provider construction happy path; absent-secrets → no auth; refresh-success → next call uses new token; refresh-fail → `MCPAuthRequired` propagates; `ManualOAuthClientProvider` short-circuits discovery for manual-entry sources. ~8-10 new tests.

- [x] `05-chat-ui-login-required-button-and-modal` *(landed 2026-05-07)* — Add WebSocket event handlers for `auth_required` and `auth_resolved` in `the_one/interfaces/web/static/js/chat.js`. New component `oauth-modal.js`: renders the modal with "Login required for <source-name>" + Connect button. On Connect click: opens consent URL in new tab. Includes a manual-entry form that pops when the modal receives a `manual_registration_required` sub-event (DCR not supported); operator pastes `client_id` + `auth_endpoint` + `token_endpoint`; modal POSTs to a new `/api/oauth/manual-register` endpoint; the-one then reissues the consent flow with the synthetic metadata. Auto-closes on `auth_resolved`. Render Login-required button inline in the chat surface where the failed tool-call result would normally render. Browser tests via Playwright: button-renders-on-event, modal-opens-on-click, manual-entry-form-toggle, modal-closes-on-auth-resolved, button-clears-on-resumed-tool-call. ~6-8 browser tests. Spawn the optional Accessibility Reviewer for this leg.

- [ ] `06-hat-two-tier` — **Tier 1 (CI, required)**: build in-repo OAuth fixture in `tests/fixtures/oauth/` (FastMCP-shaped server implementing RFC 9728 PRM, RFC 8414 AS metadata, RFC 7591 DCR, locally-signed access tokens with 5-min lifetime). Run all 5 verification steps via Playwright: pre-state, lazy 401, modal+consent, resumed tool call, refresh rotation. **Tier 2 (manual, documented in `tests/HAT.md`)**: GitHub MCP via manual-entry path. Operator follows documented procedure: pre-register OAuth app at github.com; paste client_id + endpoints into manual-entry modal; consent at github.com; verify a real tool call. Bonus: revoke + re-auth.

---

## Post-Flight

### Completion Checklist

- [ ] All required legs (L0, L1, L2, L3, L4, L5) completed; L6 HAT planned per §10
- [ ] All checkpoints (C0-C5) met; C6 contingent on L6 outcome
- [ ] `pytest --tb=no -q` green; new test count documented in flight-debrief; F1/F2/F3/F4 regression unaffected
- [ ] `ruff check the_one/ tests/` clean (per-leg gate)
- [ ] F2-known-issue mission-known-issues entry retired (post-L1, scoped per §3)
- [ ] Mission constraint amendment captured in mission.md (already landed at design time)
- [ ] FastAPI route inventory updated: `/api/oauth/callback`, `/api/oauth/manual-register` documented in CLAUDE.md or agents.md
- [ ] `the_one/mcp/README.md` extended with §11 (or §12 — placement TBD): OAuth adapter layer, error hierarchy, token persistence shape, refresh rotation invariants, GET/PUT secrets-protection invariant
- [ ] F6 design has F5 prerequisites met
- [ ] L5 accessibility review passed

### Verification

1. **F2-known-issue retired (scoped)**: F4-pool-routed path produces no `WARNING MCPClient transport close failed` log lines under shutdown_drain; direct cross-task `MCPClient.disconnect` STILL hits the safety net (contract preserved).
2. **OAuth adapter unit tests pass**: `pytest tests/test_oauth_adapter.py -v` green.
3. **End-to-end against in-repo fixture**: `pytest tests/test_oauth_e2e.py -v` green.
4. **Agent-loop pause/resume tests pass**: `pytest tests/test_agent_pause_resume.py -v` green.
5. **Streamable-http transport OAuth integration tests pass**: `pytest tests/test_streamable_http_oauth.py -v` green.
6. **Browser tests for Login-required button + modal pass**: `pytest tests/browser/test_chat_oauth_modal.py -v` green.
7. **HAT Tier-1 smoke**: 5-step in-repo-fixture flow PASS.
8. **HAT Tier-2 (documented, manual)**: GitHub MCP via manual-entry path PASS in operator's local run.
9. **Lint + existing-suite regression**: lint clean; F1/F2/F3/F4 prior tests grow by F5's net new tests (estimated +45-60 across L0-L5 — down from pre-cycle-1 estimate of +50-70 due to SDK consumption), no regressions.
10. **GET/PUT secrets protection (M2 invariant)**: integration test asserts `GET /api/mcp-sources/{id}` response has no `access_token`/`refresh_token`/`token_expires_at`/`dcr_credentials` keys; PUT with arbitrary secrets payload preserves the four managed keys from existing state.

The flight delivers the OAuth foundation that F6 (agent integration) and F7 (inspector) consume. F5 closes mission criterion #3 ("Remote MCP servers requiring OAuth are usable end-to-end") and contributes to criteria #9 (credentials-never-plaintext) and #11 (per-layer automated coverage).
