# Flight: OAuth simplification + Test connection button

**Status**: in-flight
**Mission**: [MCP Integration](../../mission.md)

## Contributing to Criteria

- [ ] **#3** — remote OAuth servers usable end-to-end without manual bearer-token paste (post-F6.5 the canonical surface is RFC 7591 DCR + RFC 9728 PRM + RFC 8414 OASM, no GitHub-legacy manual-entry fallback)
- [ ] **#7** — agent attaches MCP sources; tools become callable (closes the auth-on-`tools/list` operator-blocking gap shipped open in F6 — Cloudflare API MCP and similar production OAuth MCPs build with real tools instead of zero)
- [ ] **#9** — credentials never appear in plaintext outside the encryption boundary (the `oauth_client_secret` field that this flight removes is the F1 dead-letter UI surface that F5 doesn't read; deleting it shrinks the credential-handling perimeter)
- [ ] **#10** — graceful failure isolation (extends MCPToolProvider's except list to include MCPAuthRequired so 401-at-build degrades cleanly; combined with the Test button as the operator-facing resolution path)

---

## Pre-Flight

### Objective

Strip the GitHub-legacy OAuth manual-entry fallback that F5 added for one non-RFC-7591-compliant vendor, leaving F5's spec-compliant DCR happy path as the canonical (and only) OAuth surface. Add a Test connection button to the Studio MCP Servers source-edit page that drives the OAuth flow at source-creation time so subsequent agent builds register real tools instead of graceful-degrade-skipping. Extend `MCPClient.list_tools` (and `MCPToolProvider.get_tools_for_agent`) with the `MCPAuthRequired` translation that F5 only landed on `call_tool`, closing the auth-on-`tools/list` common-posture gap that F6 shipped open (Cloudflare API MCP, most production OAuth MCPs).

### Open Questions

- [x] Should `MCPToolProvider` register a placeholder `mcp__{source}__authenticate_to_use_this_source` tool on `MCPAuthRequired`, or graceful-degrade-skip? → **graceful-degrade-skip**, see Design Decisions §1
- [x] How does the consent URL flow back to the source-edit page (no chat session in scope)? → **two-call dance with popup-callback**, see Design Decisions §2
- [x] Does this flight also widen `MCPClient.connect`'s OAuth error surface (F6 A5 lossy-diagnostic case)? → **defer to F7 inspector**, see Design Decisions §3
- [x] Tier-2 HAT against live Cloudflare API MCP — optional or binding? → **binding L4, required for sign-off**, see Design Decisions §4
- [x] `secrets["dcr_credentials"]` field name — keep or rename now that the `registration_method` discriminator is gone? → **keep**, see Design Decisions §5
- [x] How is the consent_url surfaced to the test endpoint without involving the chat WebSocket? → **extend `make_oauth_handlers` AND `build_oauth_provider_for_source` with optional `consent_url_future` parameter**, see Design Decisions §6
- [x] What happens to the `registration_method` discriminator writer (`storage.py:151-156`) and its test assertion now that the only branch reading it is being deleted? → **strip the writer + delete the test assertion**, see Design Decisions §7
- [x] Backend `_validate_mcp_source_config` validator gates `config.oauth.{issuer_url, client_id, redirect_uri, scopes}` at `api.py:680-699` — keep as 422-defensive or delete? → **delete**, see Design Decisions §8

### Design Decisions

**§1. `MCPToolProvider.get_tools_for_agent` graceful-degrade-skips on `MCPAuthRequired`**: extend the existing `(MCPSandboxError, MCPConnectionError, MCPVersionMismatch)` except list at `_tool_provider.py` to include `MCPAuthRequired`. The source's tools are dropped from the agent's registry; a WARNING log records the skip; the agent builds with the remaining sources' tools.

- Rationale: the mission entry frames Test button as the operator-facing path — "operators authenticate at source-creation time rather than chat time, so subsequent agent builds see fresh tokens in `secrets["dcr_credentials"]` and register real tools." Once Test button works, the placeholder-tool path is unnecessary friction; once Test button is the contract, agent-build-time 401 is operator error (didn't auth before building) and graceful-skip is the right posture. Closes a layer-leakage too: chat-context auth flow stays out of agent-factory scope.
- Trade-off: mid-session token-revocation surfaces as "tool disappears on next agent rebuild" rather than as a chat-UI Login-required button. Acceptable: revocation is rare; the F5 chat-path lazy-OAuth on `call_tool` (where MCPAuthRequired translation already exists) still works inside an active session — F6.5 doesn't strip that.

**§2. Test button uses two-call dance + popup-callback (no WebSocket)**: 

Phase 1 — UI POSTs `/api/mcp-sources/{id}/test/connect`. Backend reads source. If `secrets["dcr_credentials"]` and tokens (`access_token` / `refresh_token`) present: try `MCPClient.connect()` + `list_tools()` and return `{status: "ok", tools: [...]}` (or `{status: "error", error}`). If creds absent OR connection raises `MCPAuthRequired`: backend builds an OAuth provider with a *test-mode* `redirect_handler` that resolves a `consent_url_future` instead of broadcasting via WebSocket, kicks `_drive_flow` as a background task, awaits the future with a 15-second timeout, returns `{status: "auth_required", consent_url: "..."}`. The `_drive_flow` task continues running (waits for `callback_handler` to receive code from `/api/oauth/callback`).

Phase 2 — UI opens `consent_url` in a popup window. User completes consent. Popup hits `/api/oauth/callback` (existing endpoint, no modification needed); SDK's `callback_handler` resolves; `_drive_flow` exchanges code for tokens via `MCPSourceTokenStorage.set_tokens` (existing F5 path). Popup renders "Login successful" HTML and is closed by the user (or auto-closes on a follow-up — see L3 implementation).

Phase 3 — UI listens for popup-closed event (via `window.open()` ref + `window.setInterval` on `popupRef.closed`, or `window.addEventListener('message', ...)` if popup uses `postMessage`). On popup-close, UI re-POSTs `/test/connect`. Backend now has tokens → connect + list_tools succeeds → returns `{status: "ok", tools: [...]}`.

- Rationale: source-edit page is not a chat session; introducing per-source-edit WebSocket subscription would add a third dispatch surface and complicate the chat lazy-OAuth flow. Two-call popup + reuse-existing-callback is the smallest delta. The `_drive_flow` task pattern is identical to F5's `/api/oauth/start` — only the redirect_handler dispatch differs.
- Trade-off: 15-second timeout on Phase 1 is a hard ceiling; if the SDK's PRM/OASM/DCR discovery takes longer (slow network, multi-hop redirects), Phase 1 returns `{status: "error", error: "consent_url_timeout"}` and the operator retries. Acceptable: real-world DCR-supporting servers respond in <2s. Cloudflare verified at F6 close in 0.4s.

**§3. `MCPClient.connect` OAuth error surface widening deferred to F7**: F6 A5's "cancelled during initialize" lossy diagnostic stays as-is. F6.5's Test button surfaces 401 via `list_tools` (not `connect`), so the F7 inspector is the right boundary for `connect()` translation.

- Rationale: scope tightness. F6 A5's fix is acceptable for graceful-degrade behavior; the lossy diagnostic only matters when the operator needs to distinguish "401 unauthorized" from "transport error" at connection time, which only F7's inspector trace pane needs to surface visibly.
- Trade-off: operators who Test against a source where `connect` itself 401s (rather than `list_tools`) see "cancelled during initialize" in the result panel. Mitigation: F6.5's Test button always calls `list_tools` after `connect`; the connect path that surfaces 401-as-cancelled is the *no-provider-and-server-401s-on-init* edge case, which the Test button explicitly handles by switching to OAuth-flow mode. The lossy diagnostic is unreachable through the Test button.

**§4. Tier-2 HAT against live Cloudflare API MCP is a required leg**: per F6 debrief recommendation #5 — "real-target HAT is binding go/no-go for spec-compliance claims." `tests/HAT.md` Tier-2 procedure replaced with end-to-end against `https://mcp.cloudflare.com/mcp` (which is OAuth-protected via Cloudflare's DCR-supporting AS at `https://oauth.mcp.cloudflare.com`). 

- Rationale: F6 A5 + A6 + the F1↔F5 storage-shape mismatch all only surfaced under live DCR-supporting AS targets. F6.5 is fundamentally an OAuth-path change; in-repo-fixture HAT (F5's auto-consent fixture) is insufficient.
- Trade-off: requires the operator to have a Cloudflare account at HAT time. Acceptable: Cloudflare offers free-tier accounts; the test scope (Test button → consent → re-Test → tools-list → agent build → chat tool call) takes ~5 minutes once the account is provisioned. The HAT explicitly notes "skip if account unavailable; flight cannot ship without this leg."

**§5. `secrets["dcr_credentials"]` field name kept verbatim**: even though the `registration_method` discriminator is gone, the storage key stays `dcr_credentials` to avoid a schema migration + repository update. Future readers see it as the canonical "OAuth client registration record" surface.

- Rationale: scope tightness. The field name is internal — it never surfaces in operator-facing UI after F6.5 (the dead-letter `mcp-oauth-section` block is being deleted). Renaming would force `MCPSourceTokenStorage` updates, a `secrets["dcr_credentials"]` → `secrets["oauth_credentials"]` migration in `db/schema.py`, and updates across F5's plumbing — net zero operator-facing benefit.
- Trade-off: the field name no longer reflects exclusive DCR use (since DCR is now the only path). Mitigated by docstring update at `provider_factory.py` and `storage.py` to clarify "DCR-registered OAuth client credentials" is now redundant phrasing.

**§6. `make_oauth_handlers` AND `build_oauth_provider_for_source` extended with optional `consent_url_future` parameter**: BOTH factory signatures gain a new keyword-only parameter `consent_url_future: asyncio.Future[str] | None = None`. The provider factory at `the_one/mcp/oauth/provider_factory.py:58-65` threads the future through to `make_oauth_handlers` at `the_one/mcp/oauth/handlers.py:39`. When supplied, the redirect_handler resolves the future with the consent URL after registering the state token (and before the existing chat-WS broadcast, which is a no-op for synthetic chat_session_ids).

```python
# the_one/mcp/oauth/handlers.py
def make_oauth_handlers(
    chat_session_id: str,
    source_id: str,
    tool_call_id: str | None,
    resource_metadata_url: str | None,
    *,
    consent_url_future: asyncio.Future[str] | None = None,
) -> tuple[...]:
    ...
    async def redirect_handler(authorization_url: str) -> None:
        # ... existing state-register + state_box.set_result ...
        if consent_url_future is not None and not consent_url_future.done():
            consent_url_future.set_result(authorization_url)
        # ... existing chat-WS broadcast (no-op when synthetic csid) ...

# the_one/mcp/oauth/provider_factory.py
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
    ...
    redirect_handler, callback_handler = make_oauth_handlers(
        chat_session_id=chat_session_id,
        source_id=sid,
        tool_call_id=tool_call_id,
        resource_metadata_url=resource_metadata_url,
        consent_url_future=consent_url_future,
    )
```

The Test endpoint passes a synthetic `chat_session_id = f"test:{source_id}"` (not registered in `_sessions`, so the broadcast is a guarded no-op) plus a `consent_url_future` to `build_oauth_provider_for_source`. The factory threads the future through to `make_oauth_handlers`. The endpoint awaits the future to capture consent_url.

- Rationale: keep one handler factory; reuse all the existing closure-capture invariants (5 concurrent flows, state-register-before-resolve, code_future via `_state.peek`). The new parameter is optional and defaults to None — backward-compatible signature; existing F5 chat path unchanged. Threading through `build_oauth_provider_for_source` lets both production callers (chat-path `oauth_start` + test-path `test/connect`) use the same factory without divergence.
- Trade-off: synthetic `chat_session_id` means the existing handler does a `_sessions.get("test:{source_id}")` that always returns None. The broadcast clause is already guarded (`if session is not None`), so this is a no-op — but the synthetic-csid string flows through `_state.register` and `_state.peek` and into the `/oauth/callback` endpoint's `entry.chat_session_id` lookup (which also no-ops on lookup-miss). No structural risk; real chat session IDs are 12-char uuid4-hex (`api.py:1156`) so the `test:` prefix cannot collide. The test path coexists cleanly with chat path.

**§7. `registration_method` discriminator writer is stripped post-F6.5**: the writer at `the_one/mcp/oauth/storage.py:151-156` (currently writes `registration_method="dcr"` by default and preserves `"manual"` from prior payloads) becomes vestigial once the `provider_factory.py:115` branch reading it is deleted by L0. Stripping the writer keeps the codebase clean of dead discriminator state; the test assertion at `tests/test_oauth_storage.py:152` (`assert ...["registration_method"] == "dcr"`) is deleted alongside.

- Rationale: a vestigial discriminator field with no reader is exactly the kind of dead-letter state F6 debrief addendum 2 §3 calls out. F6.5 ships it gone, not retained-for-future; future non-DCR auth shapes (e.g. mTLS, DPoP) get their own dedicated fields when added, not a recycled enum.
- Trade-off: any operator-facing tooling that inspected `secrets["dcr_credentials"]["registration_method"]` (none known per recon) would no longer find the field. Acceptable — the field was an internal discriminator, never operator-visible.

**§8. Backend `config.oauth.*` validator at `api.py:680-699` is deleted alongside the F1 UI block**: the `_validate_mcp_source_config` function rejects requests whose `config.oauth.{issuer_url, client_id, redirect_uri, scopes}` is malformed. Once L1 deletes the JS writer producing this field, no caller can populate it; retaining the validator means accepting a public-API attack surface for a stale schema. L0 deletes the validator block + the docstring lines at `api.py:576-578` that reference it.

- Rationale: dead validation paths are themselves a maintenance liability. The field never persists into runtime (F5 reads `secrets["dcr_credentials"]`, not `config.oauth.*`). Deleting both the producer (L1) and the validator (L0) shrinks the attack surface in lockstep.
- Trade-off: a hypothetical legacy API client still POSTing `config.oauth.*` fields would silently have them stored as opaque `config` dict entries (since `config` is a free-form JSON blob post-strip) rather than 422-rejected. Acceptable: the only known API client is this project's own UI, which L1 is updating in lockstep; the field has no runtime effect, so silent storage is harmless.

### Prerequisites

- [x] F6 landed and merged (per `mission.md::Flights[6]` `[x]`); branch `flight/6_5-oauth-simplification` already created from F6 tip
- [x] `MCPAuthRequired` canonical at `the_one/mcp/errors.py` (F6 L0)
- [x] `MCPSourceTokenStorage` set_tokens/get_tokens path (F5 L2) — used by `_drive_flow` after callback resolves
- [x] `/api/oauth/callback` endpoint exists and broadcasts via `_state.resolve` (F5 L4) — no modification needed for test path; the synthetic-csid no-op on `_sessions.get(entry.chat_session_id)` keeps it inert
- [x] F4 pool eviction primitive `_evict_all_for_source` (F5 carry-forward) — used by Phase-1 of `/test/connect` to bust any cached `MCPClient` instance after fresh tokens land
- [ ] Cloudflare account (free-tier acceptable) for L4 Tier-2 HAT — operator-side prerequisite, called out in `tests/HAT.md`

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Prerequisites verified (5 of 6 — Cloudflare account is operator-side, surfaced in HAT)
- [x] Validation approach defined (unit + browser tests in L0-L3; binding Tier-2 HAT in L4)
- [x] Legs defined

---

## In-Flight

### Technical Approach

The flight is two parallel deletions (L0 backend strip, L1 frontend strip) plus two coupled additions (L2 `list_tools` translation, L3 Test button + endpoint), then a binding human verification (L4 Tier-2 HAT).

**L0 + L1 (strip-out)**: GitHub's pre-2014 OAuth shape required pre-registered apps with operator-pasted `client_id` + `client_secret` because GitHub doesn't implement RFC 7591 DCR. F5 added `ManualOAuthClientProvider` + a chat-UI manual-entry modal + F1's editor section for `config.oauth.*` to support it. Cloudflare and other modern OAuth MCPs implement DCR, so this surface is dead-letter for the spec-compliant happy path. We delete it everywhere and lock F5's DCR path as canonical:

- Backend: delete `manual_metadata.py`, simplify `provider_factory.py` (drop the `registration_method == "manual"` branch at line 115), strip the `registration_method` writer at `storage.py:151-156` (per Design Decision §7), delete the `config.oauth.*` validator block at `api.py:680-699` and the related docstring lines at `api.py:576-578` (per Design Decision §8), delete `/api/oauth/manual-register` endpoint, drop `oauth/__init__.py` re-exports of `ManualOAuth*`, delete the `oauth_client_secret` field from `secrets` payload handling. Update docstrings (`storage.py`, `streamable_http.py:83,102,177`, `client.py:139`) that reference manual flow.
- Frontend: delete the `mcp-oauth-section` block in `mcp-server-editor.js` (~200 LOC: HTML at :122, form-population read at :269-271, form-population write at :692-772, save-mode payload at :891-938), delete the manual-entry form + `manual_registration_required` switch in `oauth-modal.js`, delete the `oauth_manual_registration_required` chat handler in `chat.js:670`.
- Tests: delete `test_oauth_manual_register_endpoint.py` and `test_oauth_manual_metadata.py`; remove manual-branch tests from `test_oauth_provider_factory.py` (the manual-branch test cases at lines 82-100); REWRITE `test_oauth_secrets_api.py` to use `secrets["dcr_credentials"]` (or `secrets["access_token"]`) as the masking sample instead of `oauth_client_secret` — the file's masking-contract tests are F1 production semantics that survive F6.5; only the field name changes; do NOT delete the file wholesale (it's not a manual-branch test file). Remove manual setup from `test_oauth_start_endpoint.py:100`. Delete `test_oauth_storage.py:152` (`registration_method` assertion per Design Decision §7). Delete `tests/browser/test_oauth_modal_flow.py` (manual-entry flow + `manual_registration_required` event). Update `tests/browser/test_flow_studio_mcp_editor.py:120` to drop `oauth_client_secret` field assertion.
- Update `the_one/agents.md:52,56` to drop `oauth_client_secret` references and clarify F1↔F5 storage model post-strip (F1 OAuth-config-editor block is gone; only `secrets["dcr_credentials"]` and `secrets["access_token"]`/`secrets["refresh_token"]` exist).

**L2 (`list_tools` translation)**: mirror call_tool's pattern at `client.py:540-617`. The first L2 implementation step probes whether `list_tools` 401 surfaces wrapped in `BaseExceptionGroup` (as `call_tool` does per F5 L4 A8/A9 stake-test) or bare; the `except*` pattern handles both cases safely so we keep it regardless, but the probe documents the surface for future readers. The graceful-degrade-skip log line at `MCPToolProvider` gains a discriminator distinguishing AUTH-skipped from CONNECT-skipped (per architect Q3) so the F7 inspector can render the right operator message later. Wrap `await self._session.list_tools()` in:

```python
try:
    async with asyncio.timeout(self.timeout_seconds):
        try:
            result = await self._session.list_tools()
        except* (OAuthFlowError, OAuthTokenError):
            raise MCPAuthRequired(
                source_id=self.source.id,
                resource_metadata_url=None,
                consent_url=None,
            ) from None
        except* httpx.HTTPStatusError as eg:
            auth_error: httpx.HTTPStatusError | None = None
            for sub in eg.exceptions:
                if isinstance(sub, httpx.HTTPStatusError) and sub.response.status_code == 401:
                    auth_error = sub
                    break
            if auth_error is not None:
                rmd = extract_field_from_www_auth(auth_error.response, "resource_metadata")
                raise MCPAuthRequired(
                    source_id=self.source.id,
                    resource_metadata_url=rmd,
                    consent_url=None,
                ) from None
            raise eg.exceptions[0] from None
except asyncio.TimeoutError:
    ...  # existing
except MCPAuthRequired:
    raise
except UrlElicitationRequiredError:
    raise  # existing
except McpError as e:
    ...  # existing
except (httpx.HTTPError, anyio.ClosedResourceError) as e:
    ...  # existing
```

Then extend `MCPToolProvider.get_tools_for_agent`'s except list at `_tool_provider.py:~150` from `(MCPSandboxError, MCPConnectionError, MCPVersionMismatch)` to `(MCPSandboxError, MCPConnectionError, MCPVersionMismatch, MCPAuthRequired)`. Log line gains a `auth_required` discriminator for ops visibility.

**L3 (Test button + `/test/connect` endpoint)**: 

Backend at `the_one/interfaces/web/api.py`:

```python
@router.post("/mcp-sources/{source_id}/test/connect")
async def test_mcp_connection(source_id: str) -> dict[str, Any]:
    repo = await _mcp_repo()
    source = await repo.get(source_id)  # 404 on KeyError
    
    # Phase 2 path: tokens present → try connect + list_tools
    if source.secrets.get("dcr_credentials") and source.secrets.get("access_token"):
        try:
            client = MCPClient(source=source, ...)  # via existing factory
            await client.connect()
            tools = await client.list_tools()
            await client.disconnect()
            return {"status": "ok", "tools": [t.model_dump() for t in tools]}
        except MCPAuthRequired:
            pass  # fall through to Phase 1 (token expired, re-auth)
        except (MCPConnectionError, MCPVersionMismatch) as e:
            return {"status": "error", "error": f"{type(e).__name__}: {e}"}
    
    # Phase 1 path: no creds OR re-auth needed → kick OAuth flow
    if source.type != "streamable-http":
        return {"status": "error", "error": "OAuth flow only applies to streamable-http sources"}
    
    consent_url_future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
    test_csid = f"test:{source_id}"
    
    provider = build_oauth_provider_for_source(
        source, repo, test_csid,
        source_id=source_id,
        tool_call_id=None,
        resource_metadata_url=None,
        consent_url_future=consent_url_future,  # NEW
    )
    if provider is None:
        # No dcr_credentials yet — server doesn't support DCR or operator hit
        # an unsupported AS shape; surface as error
        return {"status": "error", "error": "OAuth provider construction failed (server may not support DCR)"}
    
    await _evict_all_for_source(source_id)
    
    async def _drive_flow_test() -> None:
        try:
            async with httpx.AsyncClient(auth=provider, timeout=30.0) as client:
                await client.post(
                    source.config["url"],
                    json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {...}},
                )
        except Exception:
            if not consent_url_future.done():
                consent_url_future.set_exception(RuntimeError("auth flow failed before consent_url surfaced"))
    
    task = asyncio.create_task(_drive_flow_test())
    _inflight_resume_tasks.add(task)
    task.add_done_callback(_inflight_resume_tasks.discard)
    
    try:
        consent_url = await asyncio.wait_for(consent_url_future, timeout=15.0)
    except asyncio.TimeoutError:
        return {"status": "error", "error": "consent_url_timeout"}
    except Exception as e:
        return {"status": "error", "error": f"auth_flow_error: {e}"}
    
    return {"status": "auth_required", "consent_url": consent_url}
```

Handler factory extension at `the_one/mcp/oauth/handlers.py:39` and provider factory at `the_one/mcp/oauth/provider_factory.py:58` add the optional `consent_url_future` keyword-only parameter that threads through to the redirect_handler closure.

Frontend at `mcp-server-editor.js`:

```javascript
// Test button visible only in edit-mode (not create-mode)
function renderTestConnectionButton(source) {
  if (!source || !source.id) return '';  // create-mode
  return '<div class="editor-section mcp-test-section">' +
    '<button data-testid="mcp-test-connection" class="btn btn-secondary">Test connection</button>' +
    '<div class="mcp-test-result" data-testid="mcp-test-result"></div>' +
    '</div>';
}

async function handleTestConnection(sourceId) {
  const result = await fetch(`/api/mcp-sources/${sourceId}/test/connect`, { method: 'POST' })
    .then(r => r.json());
  if (result.status === 'ok') {
    renderToolList(result.tools);
  } else if (result.status === 'auth_required') {
    const popup = window.open(result.consent_url, 'mcp-oauth-consent', 'width=600,height=700');
    const interval = setInterval(() => {
      if (popup.closed) {
        clearInterval(interval);
        handleTestConnection(sourceId);  // Phase 2 re-POST
      }
    }, 500);
  } else {
    renderError(result.error);
  }
}
```

**L4 (Tier-2 HAT)**: replace the existing `tests/HAT.md` Tier-2 procedure (which still references the deleted GitHub manual-entry path) with a Cloudflare API MCP procedure:

1. Operator creates a fresh Cloudflare account (or uses existing).
2. Operator registers a new MCP source in Studio: name=`cloudflare_api`, type=`streamable-http`, url=`https://mcp.cloudflare.com/mcp`. Save (no auth fields needed; the source has no `dcr_credentials` yet).
3. Operator clicks Test connection. UI receives `{status: "auth_required", consent_url: "..."}` and opens popup.
4. Operator completes Cloudflare consent in popup. Popup shows "Login successful. You may close this tab." Operator closes popup.
5. UI auto re-POSTs Test. UI receives `{status: "ok", tools: [...]}` rendering N tools (verify: at least `mcp__cloudflare_api__accounts_list` or similar — exact list depends on Cloudflare's MCP server scope).
6. Operator creates a new agent `hat_cloudflare_api` attached to `cloudflare_api` source.
7. Operator opens chat with `hat_cloudflare_api`, asks "list my Cloudflare accounts using your MCP tool." Verify: agent calls `mcp__cloudflare_api__accounts_list` (or equivalent); result lands in chat.
8. Operator deletes test source + agent (cleanup — automated step in `tests/HAT.md`: documented `curl` commands for source DELETE and agent DELETE so the operator doesn't have to remember the cleanup; per architect Q4).

Pass criteria: all 7 + cleanup steps succeed; caplog `MCPClient.disconnect` warning count remains 0 (carry-forward from F6 Tier-1 HAT).

### Checkpoints

- [ ] **L0 landing**: `grep -rn "ManualOAuthClientProvider\|ManualOAuthMetadata\|/oauth/manual-register" the_one/ tests/` returns 0 hits; pytest passes for retained suites; `the_one/agents.md` updated
- [ ] **L1 landing**: `grep -rn "oauth_client_secret\|mcp-oauth-section\|manual_registration_required" the_one/interfaces/web/static/` returns 0 hits; manual chat browser tests deleted
- [x] **L2 landing**: 4 new unit tests pass against `MCPClient.list_tools` 401 surfaces (no-provider 401 wrapped in BaseExceptionGroup, OAuthFlowError surface, OAuthTokenError surface, MCPToolProvider graceful-degrade-skip on `MCPAuthRequired`); existing tests untouched
- [ ] **L3 landing**: `/test/connect` endpoint returns `{status: "ok", tools}` against Cloudflare Docs MCP (no-auth) in <2s; Test button browser test verifies popup-flow happy path against in-repo OAuth fixture
- [ ] **L4 binding go/no-go**: human verifier completes all 7 steps against live Cloudflare API MCP; flight cannot transition to `landed` without L4 PASS

### Adaptation Criteria

**Divert if**:
- Cloudflare API MCP's DCR endpoint or AS metadata returns a non-spec shape that breaks F5's path → escalate; F6.5 cannot ship without a real DCR-supporting target. Fall-back: any DCR-supporting MCP server with a non-localhost AS that the operator can reach (the operator confirms reachability before L4 starts). If no DCR target reachable within 1 hour of L4 kickoff, abort flight; F6.5 is OAuth-spec-compliance and needs live verification.
- L2's `list_tools` translation surfaces a third exception class not covered by F5's `call_tool` pattern (e.g. `OAuth2Error`, `BaseHTTPError`) → widen the except* groups in lockstep; flag as cycle-2 architect concern.
- The `consent_url_future` resolve-and-await pattern races the SDK's redirect_handler invocation in a way the F5 chat path doesn't (e.g. SDK invokes redirect_handler from a different task than the request handler) → measure with a probe; possibly switch to a contextvar-bound future propagation.

**Acceptable variations**:
- L1's exact line ranges for `mcp-oauth-section` deletion may shift as the JS module is touched; keep all `oauth_client_secret` and `config.oauth.*` references gone.
- L3's Test button placement (above the save button vs in a sidebar) is operator-feedback-driven; default to "below the save button, in its own section."
- L4's specific tool name verified in chat (step 7) varies with whatever Cloudflare's MCP server exposes; verify "any MCP tool returns a non-empty result" rather than a specific tool name.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `00-oauth-backend-strip` — Delete `manual_metadata.py`, simplify `provider_factory.py` (drop manual branch at :115; scrub manual-flow docstring at :8,73) + `storage.py:151-156` (strip `registration_method` writer; scrub `registration_method` docstring references at :10,113,123,137) + `streamable_http.py:83,102,177` + `client.py:139` docstrings, delete `/api/oauth/manual-register` endpoint, delete `_validate_mcp_source_config`'s `config.oauth.*` validator block at `api.py:680-699` + docstring lines :576-578, drop `ManualOAuth*` re-exports from `oauth/__init__.py`, REWRITE `test_oauth_secrets_api.py` to use `dcr_credentials`/`access_token` as masking sample (do NOT delete), delete `test_oauth_manual_register_endpoint.py` + `test_oauth_manual_metadata.py` + `test_oauth_storage.py:152` assertion, prune manual-branch tests from `test_oauth_provider_factory.py:82-100` (and update fixtures at lines :64-68, :115 which reference `registration_method` outside the deleted range — surgical edit, not delete) + `test_oauth_start_endpoint.py:100`, update `agents.md:52,56`
- [x] `01-oauth-frontend-strip` — Delete `mcp-oauth-section` block in `mcp-server-editor.js` (4 regions: :122 HTML, :269-271 + :692-772 form-population, :891-938 save-mode payload), delete manual-entry form + `manual_registration_required` switch in `oauth-modal.js`, delete `oauth_manual_registration_required` chat handler in `chat.js:670`, delete `tests/browser/test_oauth_modal_flow.py` (manual-entry flow), update `tests/browser/test_flow_studio_mcp_editor.py:120` to drop `oauth_client_secret` field assertion
- [x] `02-list-tools-401-translation` — Add `try / except* (OAuthFlowError, OAuthTokenError)` and `except* httpx.HTTPStatusError` around `MCPClient.list_tools`'s `session.list_tools()` call, mirroring `call_tool`'s F5 L4 pattern; extend `MCPToolProvider.get_tools_for_agent`'s except list to include `MCPAuthRequired`; new unit tests cover 4 surfaces
- [x] `03-test-connection-button` — Add `consent_url_future` parameter to `make_oauth_handlers` + `build_oauth_provider_for_source`; new endpoint `POST /api/mcp-sources/{id}/test/connect` (two-call dance); UI button + result-panel rendering in `mcp-server-editor.js`; unit tests for endpoint phase-1 and phase-2; browser test for popup-flow against in-repo OAuth fixture
- [ ] `04-tier2-hat-cloudflare` — Replace `tests/HAT.md` Tier-2 GitHub procedure with Cloudflare API MCP procedure (7 steps + automated teardown step deleting test source + agent); binding human verification; flight cannot land without PASS

---

## Post-Flight

### Completion Checklist

- [ ] All legs completed (L0–L4 binding; no optional legs)
- [ ] Code merged
- [ ] Tests passing inside `docker compose exec the-one pytest` (full suite, per F6 lesson #5)
- [ ] `tests/HAT.md` Tier-2 PASS recorded with date + caplog count
- [ ] `agents.md` updated to reflect post-strip storage model
- [ ] F1↔F5 storage-shape mismatch (F6 debrief addendum 2 §3) closed: zero references to `config.oauth.*` in production code AND zero references to `oauth_client_secret` outside the deleted test fixtures
- [ ] Mission known-issue at `mission.md:104` already retired (F6 close); no new mission-level known issues introduced

### Verification

- **Strip-out completeness**: `grep -rn "ManualOAuth\|oauth_client_secret\|config\.oauth\|manual.register\|manual_registration_required\|registration_method" the_one/ tests/ --include="*.py" --include="*.js"` returns 0 hits (excluding deletion-PR commit messages and CHANGELOG entries).
- **`list_tools` translation**: against an OAuth-protected MCP source with no creds, `MCPClient.list_tools()` raises `MCPAuthRequired` (not `MCPConnectionError`); `MCPToolProvider.get_tools_for_agent` graceful-degrade-skips with WARNING log "MCP source X requires authorization; skipping tools" and the agent builds with the remaining sources.
- **Test button**: against Cloudflare Docs MCP (no-auth) the button returns `{status: "ok", tools: [...]}` in <2s without a popup. Against Cloudflare API MCP, the button opens a popup; after consent, the same button (re-clicked) returns `{status: "ok", tools: [...]}`.
- **L4 Tier-2 HAT PASS**: human verifier completes all 7 steps with no anomalies; flight log captures the date + caplog count.
