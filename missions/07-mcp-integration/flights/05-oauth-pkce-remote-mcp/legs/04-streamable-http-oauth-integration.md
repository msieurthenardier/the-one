# Leg: 04-streamable-http-oauth-integration

**Status**: landed
**Flight**: [Lazy OAuth 2.1 + PKCE for Remote MCP Servers](../flight.md)

## Objective

Build the foundational auth-passthrough seam: add `MCPAuthRequired` exception type, modify `connect_streamable_http` (CM and non-CM helper) to accept an optional pre-built `auth_provider: httpx.Auth | None` and pass it as `auth=` to httpx.AsyncClient at construction time, extend `MCPClient.__init__` to accept and thread the same `auth_provider` through `_transport_connect` to the transport, modify `MCPClient.call_tool` to detect SDK auth failures (`OAuthFlowError`, `OAuthTokenError`) and translate to `MCPAuthRequired` carrying `(source_id, resource_metadata_url)`, modify `Agent._execute_tool` to catch `MCPAuthRequired` and populate `ToolResult.metadata.is_auth_required=True`, and extend the `_test_http_client_override` test seam to accept a factory `Callable[[dict[str, str]], httpx.AsyncClient]` so OAuth-enabled tests can produce fresh httpx clients with `auth=` attached at construction. **Provider construction itself (factory function that reads `secrets["dcr_credentials"]` and instantiates `OAuthClientProvider`/`ManualOAuthClientProvider`) is OUT OF SCOPE for L4 — it is L6's responsibility (when `chat_session_id` plumbing from the agent layer is available).**

## Context

**Flight design references**:

- §1 (auth-code with loopback redirect, SDK-driven), §2 (DCR-first / manual fallback), §11 (module placement), §12 (cross-task safety with refresh) define the OAuth wiring strategy. The provider IS attached at httpx-client construction time per §12 ("`auth=` kwarg on `httpx.AsyncClient`; token refresh runs inside the SDK's `OAuthClientProvider.async_auth_flow` generator").
- §11 Touchpoints OUTSIDE `oauth/` lists L4's two production-side targets: `connect_streamable_http` and `MCPClient.call_tool`. The flight artifact's §11 wording "provider construction with auth= injection (L4)" is **amended at design time per cycle-1 review**: L4 ships ONLY `auth=` passthrough; provider construction (factory function) is L6's scope. Rationale below.
- §11 Test seam adapter (cycle-2 M6): "the existing `_test_http_client_override` test path mutates an injected `httpx.AsyncClient`'s headers post-construction, but `auth=` must be set at httpx-client construction time. Extend the test seam to accept either a client OR a factory `Callable[[], httpx.AsyncClient]`." L4 ships this extension so OAuth-enabled tests can attach `auth=` at httpx-client construction time.
- L0 + L1 + L2 + L3 landed (uncommitted). L2 shipped `make_oauth_handlers`, `MCPSourceTokenStorage`, `ManualOAuthClientProvider`. L3 shipped `ToolResult.metadata` + `Agent.step` pause/resume primitive.

**Why provider construction is L6's scope (cycle-1 H1 + H4 disposition, user-approved 2026-05-07)**:

L2's `make_oauth_handlers(chat_session_id, source_id, tool_call_id, resource_metadata_url)` REQUIRES `chat_session_id` at construction time. `connect_streamable_http` is module-level transport code with no agent-layer context — it does NOT know `chat_session_id`. The F4 pool's `_entry_worker` constructs `MCPClient(source)` with no agent-side identifiers and reuses the warm connection across many tool calls.

Three options were considered:
- **Option A**: inline `get_connection() + get_encryptor() + MCPSourceRepository(...)` inside the transport, plus a way to thread `chat_session_id` from agent layer to transport. Adds DB-import coupling AND requires plumbing that L6 will redo. Dead code until L6.
- **Option B (chosen)**: L4 builds the seam (`auth_provider` parameter); L6 builds the factory (`build_oauth_provider_for_source(source, repo, handlers)`) and the agent-layer wiring that calls it. Cleaner separation; no dead code; smaller L4.
- **Option C**: Skip OAuth entirely until L6. Rejected — L4's seam plumbing is non-trivial and benefits from being landed independently for review.

**Critical SDK contract verified at design time** (recon + cycle-1 review 2026-05-07):

- `OAuthClientProvider.__init__(server_url, client_metadata, storage, redirect_handler, callback_handler, timeout, client_metadata_url)` — verified at `mcp/client/auth/oauth2.py:225-234`.
- `OAuthClientProvider` is an `httpx.Auth` subclass; passed via `auth=` to `httpx.AsyncClient(...)`.
- SDK exception hierarchy at `mcp/client/auth/exceptions.py`: `OAuthFlowError(Exception)` (base) > `OAuthTokenError(OAuthFlowError)` (refresh failure) > `OAuthRegistrationError(OAuthFlowError)` (DCR failure). **None inherit from `mcp.shared.exceptions.McpError` or `httpx.HTTPError`** (cycle-1 verification) — they propagate independently.
- WWW-Authenticate header parameter name is `resource_metadata` (NOT `resource_metadata_url`). Per RFC 9728 §5.1 + SDK emitter at `mcp/server/auth/middleware/bearer_auth.py:103`. SDK provides `extract_field_from_www_auth(response, "resource_metadata")` at `mcp/client/auth/utils.py:33-34` — L4 uses this helper instead of writing a regex.

**Stake-test for the no-provider 401 path** (cycle-1 H3):

When no `auth_provider` is attached and the MCP server returns 401 with WWW-Authenticate, the SDK's `streamable_http_client._post_or_get_message` runs `response.raise_for_status()` from inside an async-with `ctx.client.stream(...)` block on a separate anyio task within the SDK's TaskGroup. anyio task-group exception aggregation MAY wrap the resulting `httpx.HTTPStatusError` as a `BaseExceptionGroup`, OR convert it to `McpError("Connection closed")` via `ClientSession`'s read-stream consumer. **No existing test in the repo exercises this path** (`grep -rn "401" tests/test_mcp_*.py` → 0 hits at design time).

L4 ships the no-provider 401 translation (A9) **conditionally on a stake-test probe**. Implementation Guidance step 4 below describes the probe: drive a tool call against an httpx.MockTransport that returns 401+WWW-Authenticate, observe the actual exception type that surfaces from `MCPClient.call_tool`. The catch is shaped against the empirical answer:
- If raw `httpx.HTTPStatusError` surfaces → catch directly.
- If `BaseExceptionGroup` wraps it → catch with `except*` (Python 3.11+) OR walk `e.exceptions` manually.
- If translated to `McpError("Connection closed")` (no body access) → cannot translate to `MCPAuthRequired`; A9 defers to a follow-up flight; the no-provider 401 path surfaces as `MCPConnectionError` (existing behavior).

The leg explicitly accepts that A9 may defer — it's not blocking for the rest of L4. The provider-attached path (A8) handles all OAuth-enabled tool calls; A9 is a courtesy translation for the rare no-provider-yet operator.

**`MCPAuthRequired` design**:

- Lives at `the_one/mcp/oauth/errors.py` (sibling to the 4 existing OAuth errors).
- Carries fields: `source_id: str`, `resource_metadata_url: str | None = None`, `consent_url: str | None = None`.
- Inherits from `MCPClientError` (NOT `MCPOAuthError` — it's a control-flow signal, not a "the OAuth flow itself failed" error).
- `__str__` returns `f"Authorization required for MCP source {source_id}"` (verbatim — operator-facing; per `agents.md` Project Convention `verbatim-message-equality`).

**`Agent._execute_tool` minimal additive change**:

L3's `Agent._execute_tool` (post-L3 location: read at implementation start) catches all exceptions generically. L4 inserts a `except MCPAuthRequired as e:` clause BEFORE the generic `Exception` clause, returning `ToolResult(content="<auth required>", metadata={"is_auth_required": True, "source_id": e.source_id, "resource_metadata_url": e.resource_metadata_url, "tool_call_id": tool_call.id, "consent_url": e.consent_url})`. The L3 step loop's auth_required check then fires.

**Test seam factory pattern** (cycle-2 M6):

The current `_test_http_client_override: httpx.AsyncClient | None` is mutated post-construction (`effective_client.headers.update(headers)`). For OAuth-enabled tests, `auth=` MUST be passed at `httpx.AsyncClient(...)` construction time — post-construction mutation can't add it. L4 extends the seam type to `httpx.AsyncClient | Callable[[dict[str, str]], httpx.AsyncClient] | None`. The transport detects the type:
- If pre-constructed `httpx.AsyncClient`: legacy path, mutate headers post-construction (existing behavior preserved).
- If callable: factory path, invoke with `headers` to get a fresh client; the callable owns construction (including `auth=` if needed).
- If None: production path, transport constructs its own httpx.AsyncClient.

## Inputs

What exists before this leg runs:

- L0 + L1 + L2 + L3 landed (uncommitted; flight branch `flight/05-oauth-pkce-remote-mcp`).
- `the_one/mcp/transports/streamable_http.py::connect_streamable_http` (lines 55-110, recon-confirmed) — production path constructs `httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=httpx.Timeout(30.0))`. L4 adds `auth=auth_provider` at this construction.
- `the_one/mcp/transports/streamable_http.py::_open_streamable_http_transport_stack` (lines 113-168) — same pattern, same `auth=` insertion point.
- `_test_http_client_override: httpx.AsyncClient | None = None` at lines 34-39. Used by `tests/test_mcp_integration.py` (verified — pre-constructed client + monkeypatch + header mutation).
- `the_one/mcp/client.py::MCPClient.call_tool` (lines 369-481) — current exception handling at lines 422-436. L4 inserts a new catch BEFORE the existing `McpError` catch.
- `the_one/mcp/client.py::MCPClient.__init__` (lines 114-147) — L4 adds `auth_provider: httpx.Auth | None = None` parameter (additive, default None preserves backward compat).
- `the_one/mcp/client.py::_transport_connect` (the dispatcher in client.py) — L4 threads `auth_provider` to streamable-http path; stdio path ignores.
- `the_one/mcp/oauth/errors.py` — 4 existing OAuth errors (L0-defined). L4 adds 5th: `MCPAuthRequired`.
- `the_one/mcp/errors.py` — 8 existing classes; `MCPClientError` is the base for the new `MCPAuthRequired`.
- `the_one/mcp/oauth/__init__.py::__all__` — extended with `MCPAuthRequired`.
- `the_one/agent/core.py::Agent._execute_tool` (post-L3 line range — read at implementation start; L3 refactored core.py extensively but `_execute_tool` body is structurally similar, around line 240+) — L4 adds `except MCPAuthRequired:` before the generic `Exception` catch.
- F4 pool at `the_one/mcp/_pool.py::_entry_worker` (lines 148-193, recon-confirmed) — constructs `MCPClient(source)` with no extra kwargs. **L4 does NOT modify the pool**; the pool continues to construct `MCPClient(source)` with default `auth_provider=None`. L6 will extend the pool's caller (or `MCPClient` construction site upstream of the pool) to pass a provider.
- SDK exception types: `OAuthFlowError`, `OAuthTokenError` at `mcp.client.auth.exceptions`. SDK helper `extract_field_from_www_auth(response, "resource_metadata")` at `mcp.client.auth.utils`.

## Outputs

What exists after this leg completes:

**Modified files**:

- `the_one/mcp/oauth/errors.py` — add `MCPAuthRequired(MCPClientError)` class.
- `the_one/mcp/oauth/__init__.py` — extend `__all__` with `MCPAuthRequired`.
- `the_one/mcp/transports/streamable_http.py`:
  - Extend `_test_http_client_override` type to `httpx.AsyncClient | Callable[[dict[str, str]], httpx.AsyncClient] | None`.
  - Add `auth_provider: httpx.Auth | None = None` parameter to `connect_streamable_http` (production path passes to httpx.AsyncClient).
  - Add same parameter to `_open_streamable_http_transport_stack` (non-CM helper, same usage pattern).
  - Detect callable seam vs pre-constructed seam vs None; invoke factory when callable.
- `the_one/mcp/client.py`:
  - `MCPClient.__init__` gains `auth_provider: httpx.Auth | None = None` parameter; stored as `self._auth_provider`.
  - `_transport_connect` (dispatcher) threads `self._auth_provider` to `connect_streamable_http` / `_open_streamable_http_transport_stack` on the streamable-http branch. Stdio branch ignores (no auth applicable).
  - `MCPClient.call_tool` adds catch for `(OAuthFlowError, OAuthTokenError)` BEFORE the existing `McpError` catch — translates to `MCPAuthRequired(source_id=self.source.id)` (URL fields None — SDK exception doesn't carry them).
  - `MCPClient.call_tool` adds A9-conditional catch for the no-provider 401 path (shape determined at implementation per stake-test probe in IG step 4).
- `the_one/agent/core.py::Agent._execute_tool` — add `except MCPAuthRequired as e:` clause; returns `ToolResult` with `metadata.is_auth_required=True` populated.

**New tests**:

- `tests/test_mcp_oauth_integration.py` (NEW) — 7 tests covering A2-A9:
  - `test_connect_streamable_http_no_auth_provider_no_auth_attached` (A2) — `auth_provider=None` → constructed httpx client has `auth is None`.
  - `test_connect_streamable_http_with_auth_provider_attaches_auth` (A3) — `auth_provider=stub_auth` → constructed httpx client has `auth=stub_auth`. Verified by direct unit test on the transport (using `monkeypatch.setattr(httpx, "AsyncClient", capturing_factory)` to intercept the construction).
  - `test_open_streamable_http_transport_stack_with_auth_provider_attaches_auth` (A4) — same for the non-CM helper.
  - `test_test_seam_factory_callable_invoked_with_headers_and_returns_client` (A6) — monkey-patch `_test_http_client_override` to a factory; assert factory invoked with headers; assert returned client used.
  - `test_test_seam_legacy_pre_constructed_client_path_preserved` (A7) — pre-constructed httpx.AsyncClient as seam → headers mutated post-construction (mirrors existing pattern in `tests/test_mcp_integration.py`).
  - `test_call_tool_translates_oauth_token_error_to_mcp_auth_required` (A8a) — stub `session.call_tool` raises `OAuthTokenError("expired refresh")` → MCPClient.call_tool raises `MCPAuthRequired` with `source_id=source.id`.
  - `test_call_tool_translates_oauth_flow_error_to_mcp_auth_required` (A8b) — stub `session.call_tool` raises `OAuthFlowError("discovery failed")` → MCPClient.call_tool raises `MCPAuthRequired` with `source_id=source.id`.
  - `test_call_tool_no_provider_401_translation` (A9, conditional) — stake-test probe drives a 401 through MockTransport; if exception shape is catchable, assert MCPAuthRequired with `resource_metadata_url` populated. If shape is `BaseExceptionGroup` or `McpError`, document deferral and replace with a `pytest.skip("A9 deferred — see flight log")`.
- `tests/test_agent.py` extension (1 test):
  - `test_execute_tool_translates_mcp_auth_required_to_metadata` (A10) — register a stub tool whose `.execute()` raises `MCPAuthRequired(source_id="s1", resource_metadata_url="https://x")`; assert `Agent._execute_tool(tc)` returns `ToolResult(metadata={"is_auth_required": True, "source_id": "s1", ..., "tool_call_id": tc.id})`.
- `tests/test_mcp_oauth_errors.py` extension (1 test):
  - `test_mcp_auth_required_carries_fields_and_message` (A1) — construct `MCPAuthRequired(source_id="s1", resource_metadata_url="https://x", consent_url="https://idp/auth")`; assert all 3 fields accessible; assert `str(e) == "Authorization required for MCP source s1"`.

**Net new test count target**: 9 new tests (7 in test_mcp_oauth_integration.py + 1 in test_agent.py + 1 in test_mcp_oauth_errors.py). A14 sets the bound at 9 (+1 if A9 is feasible to test, -1 if A9 is `pytest.skip`'d). The implementer records the exact final count in the flight log.

**Net LOC target**: ~50 LOC of production code (~10 in oauth/errors.py + ~15 in streamable_http.py + ~20 in client.py + ~5 in agent/core.py + ~2 in oauth/__init__.py) + ~200 LOC of tests = ~250 LOC total.

## Acceptance Criteria

- [ ] **A1 — `MCPAuthRequired` exception class added**: `the_one/mcp/oauth/errors.py` defines `class MCPAuthRequired(MCPClientError)` with constructor `(source_id: str, *, resource_metadata_url: str | None = None, consent_url: str | None = None)`. `__str__` returns `f"Authorization required for MCP source {source_id}"` (literal interpolation — `source_id`'s actual value substitutes; no angle brackets in runtime message). `MCPAuthRequired` is exported from `the_one.mcp.oauth.__init__.__all__`. Verified via `tests/test_mcp_oauth_errors.py::test_mcp_auth_required_carries_fields_and_message`.

- [ ] **A2 — `_build_production_httpx_kwargs` returns `auth=None` when `auth_provider=None`**: direct unit test on the extracted helper — `_build_production_httpx_kwargs(headers={}, auth_provider=None)["auth"] is None`. (Tests the helper directly to avoid entering streamable_http_client's async-with body which would attempt real HTTP — cycle-2 NEW-H2 Option 4a fix.)

- [ ] **A3 — `_build_production_httpx_kwargs` returns `auth=stub_auth` when provided**: direct unit test — `_build_production_httpx_kwargs(headers={}, auth_provider=stub_auth)["auth"] is stub_auth`. Stub auth is a minimal `httpx.Auth` subclass with no behavior. AC also asserts `headers`, `follow_redirects=True`, and `timeout=httpx.Timeout(30.0)` are preserved.

- [ ] **A4 — Both `connect_streamable_http` and `_open_streamable_http_transport_stack` call `_build_production_httpx_kwargs` on the production path**: verified by `grep -n "_build_production_httpx_kwargs" the_one/mcp/transports/streamable_http.py` returning matches in both functions' bodies. Single source of truth for production-path kwargs.

- [ ] **A5 — `MCPClient.__init__` accepts and threads `auth_provider`**: `MCPClient(source, auth_provider=stub_auth).connect()` results in the streamable-http transport receiving `stub_auth`. Verified by spying on `_transport_connect`'s call into `connect_streamable_http` (or `_open_streamable_http_transport_stack`).

- [ ] **A6 — Test seam factory pattern**: monkey-patch `_test_http_client_override` to a callable `def factory(headers): return httpx.AsyncClient(headers=headers, auth=my_auth)`. The transport invokes the factory with the source's `headers` dict; the returned client is used as the effective client. Headers are NOT mutated post-construction (factory owns headers).

- [ ] **A7 — Test seam legacy pre-constructed-client pattern preserved**: monkey-patch `_test_http_client_override` to a pre-constructed `httpx.AsyncClient`. Transport detects type (NOT callable) and uses the legacy path: `effective_client.headers.update(headers)`. Existing `tests/test_mcp_integration.py` patterns continue to work UNMODIFIED.

- [ ] **A8 — `MCPClient.call_tool` translates SDK auth exceptions to `MCPAuthRequired`** (TWO sub-cases):
  - **A8a (OAuthTokenError)**: stub `self._session.call_tool` raises `OAuthTokenError("refresh failed")` → `MCPClient.call_tool` raises `MCPAuthRequired(source_id=self.source.id, resource_metadata_url=None, consent_url=None)`.
  - **A8b (OAuthFlowError)**: stub raises `OAuthFlowError("discovery failed")` → same MCPAuthRequired translation.
  - The new catch sits BEFORE the existing `except McpError:` clause. SDK exceptions don't inherit from McpError, so order is technically optional; the explicit ordering documents intent.

- [ ] **A9 — `MCPClient.call_tool` translates no-provider 401 to `MCPAuthRequired` (CONDITIONAL on stake-test)**: if the stake-test probe (Implementation Guidance step 4) reveals that a 401 + WWW-Authenticate header surfaces as a catchable exception (raw `httpx.HTTPStatusError` or `BaseExceptionGroup` containing one), `MCPClient.call_tool` parses the WWW-Authenticate header via `extract_field_from_www_auth(response, "resource_metadata")` from `mcp.client.auth.utils` and raises `MCPAuthRequired(source_id=self.source.id, resource_metadata_url=parsed_url)`. If the probe reveals the exception is wrapped as `McpError("Connection closed")` (no header access), A9 is **deferred**: the test is `pytest.skip("A9 deferred per cycle-1 H3 — exception shape obscures header access; see flight log")`, the no-provider 401 path continues to surface as `MCPConnectionError` (existing behavior). Defer documented in flight log.

- [ ] **A10 — `Agent._execute_tool` catches `MCPAuthRequired` and populates `ToolResult.metadata`**: when a tool's `.execute()` raises `MCPAuthRequired(source_id="s1", resource_metadata_url="https://x")`, `Agent._execute_tool(tc)` returns `ToolResult(tool_call_id=tc.id, content="<auth required>", metadata={"is_auth_required": True, "source_id": "s1", "resource_metadata_url": "https://x", "tool_call_id": tc.id, "consent_url": None})`. The L3 step loop's auth_required check then fires (verified end-to-end by L3's existing pause/defer tests when combined with this catch).

- [ ] **A11 — F4 pool unchanged**: `the_one/mcp/_pool.py` is NOT modified by L4. Existing pool tests continue to pass UNMODIFIED. The pool's `_entry_worker` continues to construct `MCPClient(source)` with default `auth_provider=None`.

- [ ] **A11b — Production-path provider construction NOT shipped (cycle-2 low fix)**: `grep -rn "auth_provider=" the_one/` shows matches ONLY in production declarations + threading sites (`streamable_http.py` parameter declarations + `client.py` parameter declaration + `_transport_connect`'s threading call); NO production-side call site outside those passes `auth_provider`. (Test files in `tests/` may pass `auth_provider=` in the new L4 tests — they're not in the `the_one/` grep scope.) This makes the dead-code-until-L6 invariant grep-checkable.

- [ ] **A12 — Existing tests unchanged**: all pre-existing tests in `tests/test_mcp_client.py`, `tests/test_mcp_integration.py`, `tests/test_mcp_pool.py`, `tests/test_mcp_sandbox_integration.py`, `tests/test_mcp_stdio_sandbox.py`, `tests/test_oauth_*.py` (from L2), `tests/test_agent.py` (from L3), `tests/test_db_codec.py` (from L3), `tests/test_app_websocket_pause_resume.py` (from L3) pass UNMODIFIED. The pre-existing pool-shutdown failure carries forward as the only failure.

- [ ] **A13 — Test count expansion**: `pytest tests/test_mcp_oauth_integration.py tests/test_agent.py tests/test_mcp_oauth_errors.py -q --timeout=30` is green; new test count N ∈ [8, 9] (A9 may be skipped if stake-test reveals it's not feasible). `tests/test_agent.py` count = 14 (L3) + 1 (L4) = 15. `tests/test_mcp_oauth_errors.py` = 1 (L0) + 1 (L4) = 2.

- [ ] **A14 — Full-suite regression neutral**: `pytest -q --timeout=30` shows `<L3 baseline = 1280> + N` passed (with N ∈ [8, 9]), 2 skipped (+ 1 if A9 skipped = up to 3 skipped), 1 pre-existing failure (unchanged).

- [ ] **A15 — Lint clean**: `docker compose exec the-one ruff check the_one/mcp/oauth/ the_one/mcp/transports/streamable_http.py the_one/mcp/client.py the_one/agent/core.py tests/test_mcp_oauth_integration.py tests/test_agent.py tests/test_mcp_oauth_errors.py` exits 0 BEFORE `[HANDOFF:review-needed]`.

- [ ] **A16 — Citation audit (per `leg/SKILL.md` Phase 2 item 7)**: BEFORE implementation begins,
  - `grep -rn "MCPClient\.call_tool\b\|connect_streamable_http\b\|_open_streamable_http_transport_stack\b" tests/ the_one/` → identify all callers; verify the new optional `auth_provider` parameter is backward-compatible (default None preserves all existing call shapes).
  - `grep -rn "_test_http_client_override" tests/ the_one/` → identify all uses; verify the new factory-callable shape is backward-compatible with the existing client-instance shape.
  - `grep -rn "_execute_tool\b" tests/ the_one/` → confirm only the agent's internal call site exists; the new `MCPAuthRequired` catch is additive.
  - `grep -rn "MCPClient(" tests/ the_one/` → identify all MCPClient construction sites; verify the new `auth_provider` kwarg is backward-compatible.
  - Citation audit results recorded in this leg's flight-log entry.

- [ ] **A17 — Provider construction deferred to L6 documented**: `the_one/mcp/transports/streamable_http.py` has a comment near the `auth_provider` parameter declaration: `# F5 L4: auth_provider is provided pre-built by the caller; provider construction (factory function that reads secrets["dcr_credentials"] and instantiates OAuthClientProvider/ManualOAuthClientProvider with handlers) is L6's scope. L6 builds the factory and the agent-layer wiring that calls it.`

## Verification Steps

- `grep -n "^class MCPAuthRequired" the_one/mcp/oauth/errors.py` → 1 match.
- `grep -n "auth_provider:" the_one/mcp/transports/streamable_http.py the_one/mcp/client.py` → matches in both (parameter declarations).
- `grep -n "MCPAuthRequired" the_one/mcp/client.py the_one/agent/core.py` → matches in both.
- `grep -n "Callable\[\[dict\[str, str\]\], httpx.AsyncClient\]" the_one/mcp/transports/streamable_http.py` → match for the new seam type.
- `grep -rn "auth_provider=" the_one/` → matches ONLY in `streamable_http.py` (declaration) and `client.py` (declaration + threading); NO production call site (A11b).
- `docker compose exec the-one ruff check the_one/mcp/oauth/ the_one/mcp/transports/streamable_http.py the_one/mcp/client.py the_one/agent/core.py tests/test_mcp_oauth_integration.py tests/test_agent.py tests/test_mcp_oauth_errors.py` → clean.
- `docker compose exec the-one pytest tests/test_mcp_oauth_integration.py tests/test_agent.py tests/test_mcp_oauth_errors.py -v --timeout=30` → all green; N ∈ [8, 9] new tests pass.
- `docker compose exec the-one pytest -q --timeout=30` → `<L3 baseline = 1280> + N` passed, `2 + (1 if A9 skipped else 0)` skipped, 1 pre-existing failure.

## Implementation Guidance

1. **Add `MCPAuthRequired` to `the_one/mcp/oauth/errors.py`**:

   ```python
   class MCPAuthRequired(MCPClientError):
       """Raised when an MCP tool call requires user re-authentication.

       Control-flow signal (NOT an OAuth-flow failure — see MCPOAuthError
       for those). The agent loop catches it via Agent._execute_tool and
       returns a ToolResult with metadata.is_auth_required=True so the
       L3 pause/resume primitive fires. Chat UI surfaces a Login-required
       button; user consents at the IDP; tokens persist; agent loop
       resumes.

       Carries source_id (always), resource_metadata_url (when parsed
       from a 401 WWW-Authenticate header), consent_url (when the SDK
       exposes it; usually None on the lazy path).
       """

       def __init__(
           self,
           source_id: str,
           *,
           resource_metadata_url: str | None = None,
           consent_url: str | None = None,
       ) -> None:
           super().__init__(f"Authorization required for MCP source {source_id}")
           self.source_id = source_id
           self.resource_metadata_url = resource_metadata_url
           self.consent_url = consent_url
   ```

   Inherits from `MCPClientError` (NOT `MCPOAuthError`). Add to `the_one/mcp/oauth/__init__.__all__`.

2. **Extend the test seam in `the_one/mcp/transports/streamable_http.py`**:

   ```python
   from typing import Callable

   _HttpClientFactory = Callable[[dict[str, str]], httpx.AsyncClient]
   _test_http_client_override: httpx.AsyncClient | _HttpClientFactory | None = None
   ```

   Update the seam-resolution logic in BOTH `connect_streamable_http` and `_open_streamable_http_transport_stack`. Use explicit type checks (cycle-1 low: `httpx.AsyncClient` is callable too via `__call__`; type check first).

   **Extract a private helper for production-path kwargs** (cycle-2 NEW-H2 fix — Option 4a):
   ```python
   def _build_production_httpx_kwargs(
       headers: dict[str, str], auth_provider: httpx.Auth | None
   ) -> dict[str, Any]:
       """Build the kwargs dict used to construct the production-path httpx.AsyncClient.

       Extracted as a unit-testable helper (F5 L4: AC A3/A4 unit-test
       this helper directly without entering streamable_http_client's
       async-with body, which would attempt real HTTP).
       """
       return {
           "headers": headers,
           "follow_redirects": True,
           "timeout": httpx.Timeout(30.0),
           "auth": auth_provider,  # None when no provider is supplied
       }
   ```

   Both transport functions then construct via:
   ```python
   effective_client = http_client
   if effective_client is None:
       effective_client = _test_http_client_override

   if isinstance(effective_client, httpx.AsyncClient):
       # Legacy: mutate headers on pre-constructed client
       effective_client.headers.update(headers)
       # ... existing path: yield session via streamable_http_client(url, http_client=effective_client)
   elif callable(effective_client):
       # Factory: invoke with headers; factory owns construction (incl. auth=)
       fresh_client = effective_client(headers)
       # ... use fresh_client just like the legacy path; no header mutation needed
   else:
       # effective_client is None: production path
       kwargs = _build_production_httpx_kwargs(headers, auth_provider)
       async with httpx.AsyncClient(**kwargs) as owned_client:
           # ... existing path
   ```

   The `auth=` kwarg is `None` when no provider is provided — `httpx.AsyncClient` accepts `auth=None` cleanly (verified at `.venv/.../httpx/_client.py:445-455`: `_build_auth(None) → None`, no auth attached).

3. **Thread `auth_provider` through `MCPClient`**:

   ```python
   # the_one/mcp/client.py::MCPClient.__init__ — add parameter
   def __init__(
       self,
       source: MCPSource,
       *,
       timeout_seconds: ... = _DEFAULT,
       call_timeout_seconds: ... = _DEFAULT,
       auth_provider: httpx.Auth | None = None,  # NEW (F5 L4)
   ) -> None:
       # ... existing init
       self._auth_provider = auth_provider
   ```

   And in `_transport_connect`:
   ```python
   if source.type == "streamable-http":
       session, stack = await _open_streamable_http_transport_stack(
           source,
           http_client=http_client,
           auth_provider=self._auth_provider,  # NEW
       )
   elif source.type == "stdio":
       # auth_provider not applicable; ignore silently
       session, stack = await _open_stdio_transport_stack(source)
   ```

   Same `auth_provider=` plumbing for the `@asynccontextmanager` `connect_streamable_http` if it's invoked directly via `_transport_connect`'s alternate path.

4. **Stake-test probe for A9** (no-provider 401 surface) — RUN BEFORE writing the call_tool catch:

   ```python
   # Inside docker container, ad-hoc probe in pytest:
   import httpx
   from mcp.client.session import ClientSession
   # NOTE (cycle-2 NEW-H1 fix): the function is `streamable_http_client`
   # (two-word, non-deprecated, accepts http_client kwarg), NOT
   # `streamablehttp_client` (one-word, deprecated, different signature).
   # Verified at .venv/.../mcp/client/streamable_http.py:601 — same import
   # path the_one's transport already uses at streamable_http.py:27.
   from mcp.client.streamable_http import streamable_http_client

   def _probe_handler(request: httpx.Request) -> httpx.Response:
       return httpx.Response(
           status_code=401,
           headers={
               "WWW-Authenticate": (
                   'Bearer realm="x", '
                   'resource_metadata="https://example.com/.well-known/oauth-protected-resource"'
               ),
           },
           json={"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": "unauthorized"}},
       )

   async def probe():
       transport = httpx.MockTransport(_probe_handler)
       async with httpx.AsyncClient(transport=transport) as client:
           try:
               async with streamable_http_client(
                   "https://example.com/mcp", http_client=client
               ) as (read, write, _get_id):
                   async with ClientSession(read, write) as session:
                       await session.initialize()
                       await session.call_tool("any", {})
           # probe-only — BaseException intentional to capture cancel-style
           # exits if they surface (cycle-2 suggestion)
           except BaseException as e:
               print(f"Surface type: {type(e).__name__}; chain: {repr(e)}")

   # Run probe inside docker:
   # docker compose exec the-one python -c "import asyncio; from <probe_file> import probe; asyncio.run(probe())"
   ```

   The probe identifies the exception type that bubbles. Three branches:
   - **httpx.HTTPStatusError** → catch directly:
     ```python
     except httpx.HTTPStatusError as e:
         if e.response.status_code == 401:
             from mcp.client.auth.utils import extract_field_from_www_auth
             rmd = extract_field_from_www_auth(e.response, "resource_metadata")
             raise MCPAuthRequired(
                 source_id=self.source.id,
                 resource_metadata_url=rmd,
             ) from None
         raise MCPConnectionError(...) from None
     ```
   - **BaseExceptionGroup wrapping httpx.HTTPStatusError** (Python 3.11+) → use `except*`:
     ```python
     try:
         async with asyncio.timeout(...):
             result = await self._session.call_tool(name, arguments)
     except* httpx.HTTPStatusError as eg:
         e = eg.exceptions[0]  # or walk the group
         if e.response.status_code == 401:
             # ... same translation
     ```
   - **McpError("Connection closed")** with no body access → A9 deferred:
     ```python
     # No catch added; A9 test is pytest.skip("A9 deferred — cycle-1 H3"); document in flight log.
     ```

   Implementer records the probe result in flight log under "Stake-test results: A9 surface type = <X>".

5. **`MCPClient.call_tool` — translate SDK auth exceptions** (always-shipped — A8):

   ```python
   from mcp.client.auth.exceptions import OAuthFlowError, OAuthTokenError
   from the_one.mcp.oauth.errors import MCPAuthRequired

   # Inside MCPClient.call_tool, BEFORE the existing `except McpError`:
   try:
       async with asyncio.timeout(self.call_timeout_seconds):
           result = await self._session.call_tool(name, arguments)
   except asyncio.TimeoutError:
       raise MCPConnectionError(...) from None
   except UrlElicitationRequiredError:
       raise
   except (OAuthFlowError, OAuthTokenError):
       # F5 L4 (A8): SDK auth-flow failed. Provider attached but couldn't
       # complete (refresh failed / discovery failed / DCR failed). Tell the
       # agent loop to pause and surface auth_required to chat UI.
       raise MCPAuthRequired(
           source_id=self.source.id,
           resource_metadata_url=None,  # SDK exception doesn't carry it
           consent_url=None,
       ) from None
   # ... A9 conditional catch goes here, shape determined by step 4 probe ...
   except McpError as e:
       raise MCPCallError(tool_name=name, server_message=str(e)) from None
   except (httpx.HTTPError, anyio.ClosedResourceError) as e:
       raise MCPConnectionError(...) from None
   ```

6. **Agent._execute_tool — translate MCPAuthRequired** (A10):

   Read the post-L3 shape of `Agent._execute_tool` (line numbers shifted by L3's refactor — likely around line 240+). Add the new catch BEFORE the generic `Exception`:

   ```python
   from the_one.mcp.oauth.errors import MCPAuthRequired

   async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
       try:
           tool = self.tools.get(tool_call.name)
           output = await tool.execute(**tool_call.arguments)
           return ToolResult(tool_call_id=tool_call.id, content=output)
       except MCPAuthRequired as e:
           return ToolResult(
               tool_call_id=tool_call.id,
               content="<auth required>",
               metadata={
                   "is_auth_required": True,
                   "source_id": e.source_id,
                   "resource_metadata_url": e.resource_metadata_url,
                   "tool_call_id": tool_call.id,
                   "consent_url": e.consent_url,
               },
           )
       except Exception as e:
           return ToolResult(
               tool_call_id=tool_call.id,
               content=f"[error] Tool execution failed: {e}",
               is_error=True,
           )
   ```

7. **Pre-implementation citation audit** (per `leg/SKILL.md` Phase 2 item 7) — RUN BEFORE writing code:
   - `cd /home/cprch/projects/the-one && grep -rn "MCPClient\.call_tool\b\|connect_streamable_http\b\|_open_streamable_http_transport_stack\b" tests/ the_one/`
   - `cd /home/cprch/projects/the-one && grep -rn "_test_http_client_override" tests/ the_one/`
   - `cd /home/cprch/projects/the-one && grep -rn "_execute_tool\b" tests/ the_one/`
   - `cd /home/cprch/projects/the-one && grep -rn "MCPClient(" tests/ the_one/`
   - Record results in flight log.

8. **Tests** (~9 functions across 3 files):

   - **`tests/test_mcp_oauth_integration.py` (NEW)** — covers A2-A9. Use `monkeypatch.setattr(httpx, "AsyncClient", capturing_factory)` to intercept the production-path constructor and capture `auth=` kwargs. For A6/A7, use the `_test_http_client_override` seam directly.

     Skeleton for A2/A3 (cycle-2 NEW-H2 Option 4a — direct unit test on the extracted helper):
     ```python
     def test_build_production_httpx_kwargs_no_auth_provider() -> None:
         from the_one.mcp.transports.streamable_http import _build_production_httpx_kwargs
         kwargs = _build_production_httpx_kwargs(headers={"X-Foo": "bar"}, auth_provider=None)
         assert kwargs["auth"] is None
         assert kwargs["headers"] == {"X-Foo": "bar"}
         assert kwargs["follow_redirects"] is True
         assert kwargs["timeout"] == httpx.Timeout(30.0)

     def test_build_production_httpx_kwargs_with_auth_provider() -> None:
         from the_one.mcp.transports.streamable_http import _build_production_httpx_kwargs

         class StubAuth(httpx.Auth):
             def auth_flow(self, request):
                 yield request

         stub = StubAuth()
         kwargs = _build_production_httpx_kwargs(headers={}, auth_provider=stub)
         assert kwargs["auth"] is stub
     ```

     Skeleton for A4 (verify both transport functions invoke the helper):
     ```python
     def test_both_transport_functions_call_build_production_httpx_kwargs() -> None:
         """Single source of truth for production-path kwargs."""
         import inspect
         from the_one.mcp.transports import streamable_http as mod
         cm_src = inspect.getsource(mod.connect_streamable_http)
         stack_src = inspect.getsource(mod._open_streamable_http_transport_stack)
         assert "_build_production_httpx_kwargs" in cm_src
         assert "_build_production_httpx_kwargs" in stack_src
     ```

     Skeleton for A8a/A8b (cycle-2 NEW-M3 fix — explicit test fixture pattern):
     ```python
     async def test_call_tool_translates_oauth_token_error_to_mcp_auth_required() -> None:
         from unittest.mock import AsyncMock
         from mcp.client.auth.exceptions import OAuthTokenError
         from the_one.mcp.client import MCPClient
         from the_one.mcp.oauth.errors import MCPAuthRequired

         source = MCPSource(
             id="src-1", name="x", type="streamable-http",
             config={"url": "http://example.com/mcp", "headers": {}},
             secrets={},
         )
         client = MCPClient(source)
         # Manually plug in connected state — skip real connect() to keep
         # the test hermetic and avoid live SDK/network dependencies.
         client._is_alive = True
         client._session = AsyncMock()
         client._session.call_tool.side_effect = OAuthTokenError("refresh failed")
         # Pre-populate _tools_cache so call_tool's lazy list_tools() doesn't fire
         from the_one.mcp.client import MCPTool  # or wherever the model is
         client._tools_cache = [MCPTool(name="t", description="x", input_schema={"type": "object", "properties": {}})]

         with pytest.raises(MCPAuthRequired) as exc_info:
             await client.call_tool("t", {})
         assert exc_info.value.source_id == "src-1"
         assert exc_info.value.resource_metadata_url is None
         assert exc_info.value.consent_url is None
     ```

     A8b uses the same skeleton with `OAuthFlowError("discovery failed")` instead of `OAuthTokenError`. The implementer reads `the_one/mcp/client.py::MCPClient` to confirm the exact internal-state field names (`_is_alive`, `_session`, `_tools_cache`, the MCPTool model name) before writing the test; if names differ, adjust accordingly. Document any name differences in the flight log.

   - **`tests/test_agent.py` extension** — 1 test for A10:
     ```python
     async def test_execute_tool_translates_mcp_auth_required_to_metadata() -> None:
         from the_one.mcp.oauth.errors import MCPAuthRequired

         class AuthRequiredTool(Tool):
             name = "auth_tool"
             description = "raises auth required"
             input_schema = {"type": "object", "properties": {}}
             async def execute(self, **kwargs) -> str:
                 raise MCPAuthRequired(
                     source_id="s1",
                     resource_metadata_url="https://x/.well-known/oauth-protected-resource",
                 )

         tools = ToolRegistry()
         tools.register(AuthRequiredTool())
         agent = Agent(llm=FakeLLM([]), tools=tools, system_prompt="...")
         tc = ToolCall(id="tc1", name="auth_tool", arguments={})
         result = await agent._execute_tool(tc)
         assert result.metadata == {
             "is_auth_required": True,
             "source_id": "s1",
             "resource_metadata_url": "https://x/.well-known/oauth-protected-resource",
             "tool_call_id": "tc1",
             "consent_url": None,
         }
         assert result.tool_call_id == "tc1"
     ```

   - **`tests/test_mcp_oauth_errors.py` extension** — 1 test for A1:
     ```python
     def test_mcp_auth_required_carries_fields_and_message() -> None:
         from the_one.mcp.oauth.errors import MCPAuthRequired
         e = MCPAuthRequired(
             source_id="s1",
             resource_metadata_url="https://x",
             consent_url="https://idp/auth",
         )
         assert e.source_id == "s1"
         assert e.resource_metadata_url == "https://x"
         assert e.consent_url == "https://idp/auth"
         assert str(e) == "Authorization required for MCP source s1"
     ```

9. **Lint + post-completion checklist**:
   - Run `docker compose exec the-one ruff check ...` on every changed file.
   - Update flight-log.md with: pre-edit SHA, files changed (LOC delta), test count delta (re-confirmed pre-leg baseline first), citation audit results, stake-test probe results (step 4), deviations.
   - Update flight.md L4 checkbox + leg artifact status to `landed` ONLY (NOT `completed`). Mark C4 checkpoint `[x]`.
   - **Do NOT commit.** Signal `[HANDOFF:review-needed]`.

## Edge Cases

- **Source has dcr_credentials but caller passes auth_provider=None**: transport doesn't construct a provider (L4 punted that to L6); httpx.AsyncClient gets `auth=None`. The 401 surfaces (A9 path if probed-feasible). Operator sees Login required event. L6 will wire the provider so this path just-works.
- **`_test_http_client_override` is an `httpx.AsyncClient` AND `Callable`**: legacy path takes precedence (`isinstance(effective_client, httpx.AsyncClient)` catches it first). Cycle-1 low fix verified.
- **Stdio source with `auth_provider` passed**: `_transport_connect`'s stdio branch ignores `self._auth_provider` silently. No assertion or warning — auth_provider is just transport-irrelevant for stdio. Document in code comment near the stdio branch.
- **`MCPClient.call_tool`'s catch order (A8 BEFORE McpError)**: SDK exceptions don't inherit from McpError; the order is technically optional. Explicit `(OAuthFlowError, OAuthTokenError)` BEFORE `McpError` documents intent and protects against future SDK-side hierarchy changes.
- **Stake-test probe surfaces `BaseExceptionGroup`** (cycle-1 H3): A9 catch uses `except*`. Test verifies the catch fires correctly. If Python 3.11+ syntax causes ruff/mypy issues, the implementer either upgrades the linter config or falls back to manual `e.exceptions` walking inside a regular `except BaseExceptionGroup`.
- **Stake-test probe surfaces `McpError("Connection closed")`** (response body lost before the exception bubbles): A9 is deferred; the test is `pytest.skip(...)`; documented in flight log. The lazy 401 UX still works via the agent layer's L6 wiring (which always attaches a provider when an MCP source is configured); this corner case is "operator hits a server before configuring the provider" and is acceptable to surface as a generic connection error.
- **`MCPClient.call_tool`'s `from None` propagation**: the existing pattern uses `from None` to suppress the SDK exception chain in operator-facing messages. L4 follows the same convention for `MCPAuthRequired` (no `from e` — SDK exception's traceback would leak into operator UI; cleaner to drop).

## Files Affected

- `the_one/mcp/oauth/errors.py` — add `MCPAuthRequired` class.
- `the_one/mcp/oauth/__init__.py` — extend `__all__` with `MCPAuthRequired`.
- `the_one/mcp/transports/streamable_http.py` — extend `_test_http_client_override` type; add `auth_provider` parameter to both transport functions; pass `auth=` to httpx clients in production path.
- `the_one/mcp/client.py::MCPClient` — add `auth_provider` parameter to `__init__`; thread through `_transport_connect`; add SDK-auth-exception catch in `call_tool`; conditionally add 401-translation catch (per stake-test probe).
- `the_one/agent/core.py::Agent._execute_tool` — add `except MCPAuthRequired` clause.
- `tests/test_mcp_oauth_integration.py` — NEW; 7 tests.
- `tests/test_agent.py` — +1 test.
- `tests/test_mcp_oauth_errors.py` — +1 test.
- Flight log + flight checkbox + leg artifact status — flight-final updates.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria A1-A17 verified (A9 may be deferred per stake-test)
- [ ] `docker compose exec the-one ruff check the_one/mcp/oauth/ the_one/mcp/transports/streamable_http.py the_one/mcp/client.py the_one/agent/core.py tests/test_mcp_oauth_integration.py tests/test_agent.py tests/test_mcp_oauth_errors.py` clean
- [ ] `docker compose exec the-one pytest tests/test_mcp_oauth_integration.py tests/test_agent.py tests/test_mcp_oauth_errors.py -q --timeout=30` green at +N tests where N ∈ [8, 9]
- [ ] `docker compose exec the-one pytest -q --timeout=30` shows 1280+N passed, 2+(1 if A9 skipped else 0) skipped, 1 pre-existing failure (unchanged) — re-confirmed pre-leg baseline at implementation start
- [ ] Stake-test probe results recorded in flight log (A9 surface type)
- [ ] Citation audit grep results recorded in flight log
- [ ] Update flight-log.md with the L4 progress entry
- [ ] Set leg status to `landed` in this file's header
- [ ] Check off leg L4 in `flight.md`
- [ ] Mark C4 checkpoint `[x]` in `flight.md`
- [ ] Do NOT commit; do NOT update flight status to landed (final autonomous leg of flight is L5 → triggers flight-final review + commit)
- [ ] Signal `[HANDOFF:review-needed]` (NOT `[COMPLETE:leg]`)

## Citation Audit

11 citations verified against current code at leg design time (recon + cycle-1 review 2026-05-07):

- `connect_streamable_http` body — `the_one/mcp/transports/streamable_http.py:55-110` — OK; auth injection point at the production-path `httpx.AsyncClient(...)` constructor.
- `_open_streamable_http_transport_stack` body — `the_one/mcp/transports/streamable_http.py:113-168` — OK; same injection pattern.
- `_test_http_client_override` declaration — `the_one/mcp/transports/streamable_http.py:34-39` — OK.
- `MCPClient.call_tool` body + exception handling — `the_one/mcp/client.py:369-481`, especially the catch chain at 422-436 — OK.
- `MCPClient.__init__` signature — `the_one/mcp/client.py:114-147` — OK; new `auth_provider` parameter is additive.
- `the_one/mcp/oauth/errors.py` — 4 existing classes; L4 adds 5th (`MCPAuthRequired`).
- `the_one/mcp/errors.py` — 8 classes; `MCPClientError` is the base for the new `MCPAuthRequired`.
- L2 exports verified at `the_one/mcp/oauth/__init__.py:31-38`: `MCPSourceTokenStorage`, `ManualOAuthClientProvider`, `ManualOAuthMetadata`, `make_oauth_handlers`, `start_periodic_sweep`, `stop_periodic_sweep`. L4 adds `MCPAuthRequired` to `__all__`.
- F4 pool — `the_one/mcp/_pool.py::_entry_worker` at lines 148-193 constructs `MCPClient(source)` with no extra kwargs. L4 does NOT modify the pool.
- SDK exception types — `mcp.client.auth.exceptions.OAuthFlowError` and `OAuthTokenError` — verified to NOT inherit from `McpError` or `httpx.HTTPError`; propagate independently.
- WWW-Authenticate parameter name `resource_metadata` (NOT `resource_metadata_url`) — verified per RFC 9728 §5.1 + SDK emitter at `mcp/server/auth/middleware/bearer_auth.py:103`. SDK helper `extract_field_from_www_auth(response, "resource_metadata")` at `mcp/client/auth/utils.py:33-34` is used by the A9 catch path (cycle-1 H2 fix).

No drift; no `gone` citations. The single load-bearing unknown — the SDK's exception shape on a no-provider 401 (A9) — is captured by the stake-test probe in Implementation Guidance step 4.
