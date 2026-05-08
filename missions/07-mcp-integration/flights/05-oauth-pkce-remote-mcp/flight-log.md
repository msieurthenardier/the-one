# Flight Log: Lazy OAuth 2.1 + PKCE for Remote MCP Servers

**Flight**: [Lazy OAuth 2.1 + PKCE](flight.md)

## Summary

Pre-execution. Phase 1 + 1b context-gathering complete; F4 debrief feedback pulled forward (citation-audit gap in `leg/SKILL.md` Phase 2 item 7 — landed in mission-control PR #5; F2-known-issue follow-on owned by F5 L1; constraint #6 mission amendment for agent-loop pause/resume primitive landed at design time). UX shifted from original Settings-driven OAuth config to lazy/discovery-driven (RFC 9728 PRM + RFC 8414 AS metadata + RFC 7591 DCR + auth-code-with-loopback at first 401) per user direction. Awaiting Architect cycle-1 design review.

---

## Phase 1b Reconnaissance Report

F5 sources work items from TWO prior artifacts: F4 flight debrief (which itself sourced from F4 execution) + Mission 07 Open Questions (the OAuth-shape and client-registration questions assigned to F5).

### Reconnaissance Table

| # | Item | Source | Classification | Evidence | Recommendation |
|---|------|--------|----------------|----------|----------------|
| 1 | F4 R1 [Critical]: F2-known-issue follow-on (parallel non-CM transport helpers; retire `RuntimeError: generator didn't stop` swallow log noise) | F4 debrief | `confirmed-live` | `the_one/mcp/transports/streamable_http.py:55-110` is `@asynccontextmanager`; consumed by 1 prior test (`tests/test_mcp_client.py::TestConnectStreamableHttpProduction`). Stdio symmetric. F2-known-issue still present per HAT Finding #1 | F5 L1 owner — lands BEFORE OAuth backend so refresh path uses clean dispatcher contract |
| 2 | F4 R3: bwrap subprocess `wait()` gap (HAT Finding #2) | F4 debrief | `not-applicable-to-F5` | F5 is streamable-HTTP only; no bwrap | Defer to F6 or routine maintenance |
| 3 | F4 R4: `procps` Dockerfile (HAT Finding #3) | F4 debrief | `confirmed-live` | Dockerfile lacks `procps`; F5 HAT may benefit | Roll into F5 L0 (small infra leg) |
| 4 | F4 R5/R6/R7: fifth Project Convention; README drift fix; safety-net log message | F4 debrief | `confirmed-live` (low) | Cosmetic doc + log-string edits | Defer to routine maintenance — not F5-load-bearing |
| 5 | F4 R10 [Forward]: F5 design constraint — do NOT add NEW direct callers of `connect_streamable_http` as `async with` | F4 debrief | `confirmed-live` (constraint) | Existing 1 caller is what blocks the F2-known-issue fix; F5 must not add more | Encoded as a hard constraint in F5 §3 + L1 acceptance criteria |
| 6 | Q-OAUTH-FLOW: device-code vs auth-code-with-loopback-redirect | mission Open Questions | `resolved-at-design` | Desktop-app form factor; loopback is OAuth 2.1 spec-canonical | Auth-code-with-loopback is the floor; device-code deferred to a future flight if SSH-only operator demand surfaces |
| 7 | Q-CLIENT-REG: pre-registered / CIDM / DCR | mission Open Questions | `resolved-at-design` | User design call: "MCP maker owns OAuth flow correctness" → DCR is the natural primary path; pre-registered table is irrelevant for spec-compliant servers | DCR-first with user-entered fallback for non-DCR-supporting AS (rare); pre-registered table dropped |
| 8 | Mission constraint #16: "No agent-loop semantic changes beyond tool-registry composition" | mission constraint | `resolved-at-design` (amend) | The lazy-OAuth UX requires a pause/resume primitive in the loop. User confirmed (2026-05-07): "B is what we want for sure, that constraint is wrong." | Constraint amended in mission.md at flight design time; F5's `auth_required` ToolResult type is the only sanctioned loop-level extension in this mission |
| 9 | Citation-audit gap (F4 debrief R2) | F4 debrief | `already-satisfied` | Codified in `mission-control` PR #5 (`leg/SKILL.md` Phase 2 item 7 sharpened with explicit grep command for direct-caller search) | Retired — methodology improvement landed; F5 leg authors apply the new gate |

### Open Questions Carried Forward to F5 Design

All 8 design-decision items resolved at flight design (Phase 3 user input 2026-05-07). See flight.md §§Open Questions.

### Action Items NOT Carried Into F5 (with justification)

| Item | Reason |
|------|--------|
| F2 zombie bwrap subprocess `wait()` gap | F5 is streamable-HTTP only; no bwrap subprocesses. Defer to F6 or routine maintenance. |
| F4 README drift (60s → 30s) | One-character edit; doesn't earn a flight commit on its own. Defer to routine maintenance. |
| F4 safety-net log message extension | F5 L1 actually RETIRES the safety-net's normal-flow firing; the log-message extension becomes lower priority post-L1. Defer. |
| F4 fifth Project Convention `same-task-anyio-cm-ownership` | Documentation-only; defer to routine maintenance. |
| F4 R8 (`UrlElicitationRequiredError` propagation test) | Already deferred in F4 — orthogonal to F5. |
| Pre-registered OAuth provider table | User explicitly dropped at design time (DCR-first). |
| Settings UI per-source OAuth status badge | User explicitly dropped at design time (chat-only surface). |

---

## Flight Director Notes

> Populated by the orchestrator during agentic-workflow execution.

### Phase 5b Architect Design Review

#### Cycle 1 — overall assessment: **needs rework**

Architect raised 3 high + 4 medium + 3 low + 8 questions.

**High-severity issues (load-bearing)**:

1. **H1 — SDK already ships OAuth machinery (~350 LOC saved if consumed)**: `mcp.client.auth.OAuthClientProvider` (in pinned `mcp==1.27.0`) provides PKCE generation, RFC 9728 PRM discovery, RFC 8414 AS metadata discovery (with OIDC fallback), RFC 7591 DCR registration, RFC 8707 audience validation, pre-emptive token refresh, and httpx integration via `auth=` kwarg. F5's draft re-implemented all of this in `pkce.py` + `discovery.py` + `registration.py` + `flow.py` + `_state.py` (~400-600 LOC).
2. **H2 — L1's stack-ownership claim contradicts `the_one/mcp/README.md §3`**: README states AsyncExitStack alone does NOT solve cross-task disconnect; F5's L1 claim that the dispatcher-owned-stack pattern retires the F2-known-issue is too broad without scoping.
3. **H3 — Citation drift**: F5 referenced `the_one/agent/types.py::ToolResult` for the new `is_auth_required` field; that path does NOT exist. `ToolResult` lives at `the_one/llm/base.py:25` (verified). Adding domain-specific OAuth fields to a provider-neutral LLM type is also an architectural call.

**Medium-severity issues**:
- M1 — multi-tool-call iteration semantic gap (defer / drop / re-invoke?)
- M2 — OAuth-token re-save through PUT corrupts secrets (masking returns `"***"` for non-string secrets, doesn't round-trip)
- M3 — HAT target's AS metadata + DCR are NOT spec-compliant; GitHub MCP's AS at `https://github.com/login/oauth` does NOT serve `oauth-authorization-server` or `openid-configuration` `/.well-known/` endpoints AND does NOT implement DCR (probed empirically 2026-05-07 16:21 UTC)
- M4 — citation-audit gap: F5 only flagged L5; L1, L4, L6 also touch public-symbol signatures and need the audit per `leg/SKILL.md` Phase 2 item 7

**Low-severity issues**:
- L1 — discovery fallback ordering (irrelevant if SDK consumed)
- L2 — loopback port hardcoded `8484` (should derive from runtime config)
- L3 — token-expiry pre-emptive-vs-reactive refresh (free if SDK consumed)

#### Cycle 1 disposition (resolved 2026-05-07, user picks):

User picked: **H1=A (consume SDK), H2=C (two-tier HAT, accept GitHub manual-path non-compliance), H3=B (generic `metadata: dict | None` field on `ToolResult`), M1=defer-and-re-dispatch, M2=strip-from-GET, M3=codify-citation-audit-on-L1/L4/L6**.

Inline rework applied to flight artifact:
- §§7-8 collapsed into §7 ("Discovery + DCR + PKCE — delegated to SDK's `OAuthClientProvider`"). Module placement (§11) shrunk to `storage.py` + `handlers.py` + `_state.py` + `manual_metadata.py` + `errors.py` (~250 LOC; was ~600).
- §3 (L1) reframed to scope the F2-known-issue retirement to F4-pool-routed path; direct cross-task usage outside the pool still hits the safety net.
- §4 + L3 updated: generic `metadata: dict | None = None` field on `the_one/llm/base.py::ToolResult`; multi-tool-call deferral semantic locked (preceding tool-call results land in messages normally; current + remaining tool calls deferred to `_deferred_tool_calls`; on resume, re-dispatch in order).
- §5 + L2 updated: GET strips OAuth-managed keys (access_token, refresh_token, token_expires_at, dcr_credentials) from response entirely; PUT merge preserves them from `existing.secrets` regardless of incoming payload.
- §10 + L6 updated: two-tier HAT — Tier-1 in-repo FastMCP-shaped AS fixture (CI), Tier-2 GitHub MCP via manual-entry path (manual / documented in `tests/HAT.md`).
- §11 (module placement) rewritten with shrunk module list + cross-references to SDK primitives.
- L1, L4, L6 (renumbered as L4 in new layout) acceptance criteria extended to require `grep -rn` citation audit per `leg/SKILL.md` Phase 2 item 7.
- Loopback port derived from runtime config (`settings.port`) at flow-start time.

Legs renumbered: L0 (bootstrap), L1 (transport-stack helper), L2 (OAuth SDK adapter — collapses old L2+L3+L4), L3 (agent-loop pause/resume — was L5), L4 (transport OAuth integration — was L6), L5 (chat UI — was L7), L6 (HAT — was L8). 7 legs total (was 9).

Cycle 2 verification: spawn Architect to verify the inline rework resolved the 3 highs + 4 mediums correctly without introducing new high-severity issues.

---

## Leg Progress

> Populated as legs land.

### Leg 04: streamable-http-oauth-integration — landed 2026-05-07

- **Status**: `landed` (NOT committed; awaits flight-final review post-L5)
- **Pre-edit SHA**: `f6b5cee70308f4ab16ef2f885335dc0574534bbc` (flight design commit; same as L0/L1/L2/L3 — leg branch carries L0+L1+L2+L3+L4 uncommitted)
- **Started**: 2026-05-07T (in-flight transition)
- **Landed**: 2026-05-07T
- **Pre-leg baseline (re-confirmed at implementation start, BEFORE editing any file)**:
  - Full project suite (`pytest -q --timeout=30`) at L4 implementation start: **1280 passed, 2 skipped, 1 failed (`tests/test_mcp_pool.py::test_acquire_lazy_spawn_creates_worker_and_returns_client`)**, 299 deselected. Identical to the L3 landed baseline — no test-count drift between L3 land and L4 start.
  - The 1 failing test is the pre-existing pool-shutdown ordering failure carried from L0/L1/L2/L3; out of scope for L4.
- **Citation audit results (per `leg/SKILL.md` Phase 2 item 7, RUN BEFORE writing any code)**:
  - `grep -rn "MCPClient\.call_tool\b\|connect_streamable_http\b\|_open_streamable_http_transport_stack\b" tests/ the_one/`: matches in `tests/test_agent.py:253` (L3 docstring reference), `tests/test_mcp_client.py:1502/1548` (`TestConnectStreamableHttpProduction` direct async-with caller — L1 documented as the 1 prior caller), `tests/test_mcp_sandbox_integration.py:3` (L4 sandbox integration docstring), `the_one/agents.md:109` (catalog entry), `the_one/mcp/types.py:5/40` (docstring references), `the_one/mcp/README.md` (multiple — module documentation), `the_one/mcp/client.py:71/79/82` (existing dispatcher + transport import), `the_one/mcp/transports/streamable_http.py:5/31/37/56/113/129` (declarations + docstrings), `the_one/mcp/oauth/handlers.py:23` (handler docstring). All consumers either (a) use the legacy `connect_streamable_http(source)` shape with default kwargs (no breakage from new `auth_provider=None` default), or (b) reference the function name in docstrings only. Backward compat preserved.
  - `grep -rn "_test_http_client_override" tests/ the_one/`: `tests/test_mcp_integration.py:70/103/125/254/284/378` (6 monkeypatch sites), `tests/test_mcp_client.py:1538` (1 reset site), `the_one/agents.md:109` + `the_one/mcp/README.md:25/33` (catalog/docs), `the_one/mcp/transports/streamable_http.py:39/86/140` (declaration + read sites). All test sites monkeypatch with a pre-constructed `httpx.AsyncClient` — the new factory-callable shape is type-detected via `isinstance(effective_client, httpx.AsyncClient)` FIRST, so existing test patterns hit the legacy path unchanged.
  - `grep -rn "_execute_tool\b" tests/ the_one/`: 5 hits — `tests/test_agent.py:236/246/256/280` (L3's monkeypatch helper), `the_one/agent/core.py:167/192/242` (call site at line 192 inside `_dispatch_tool_calls`; def at line 242). The new `MCPAuthRequired` catch is additive — sits BEFORE the existing generic `Exception` handler; existing call site/monkeypatch unaffected. `_execute_tool`'s post-L3 line shifted from L4-design-time-cited "around line 240+" to **line 242 def** (close enough; design-time citation valid).
  - `grep -rn "MCPClient(" tests/ the_one/`: 50+ hits across `tests/test_mcp_integration.py` (12), `tests/test_mcp_client.py` (40+). All construct via `MCPClient(source)` or `MCPClient(_stdio_source(), timeout_seconds=N)` — no test passes positional kwargs that would clash with the new `auth_provider` keyword-only parameter. Backward compat preserved.
  - **Conclusion**: all four greps confirm the leg's stated invariants. No drift, no new caller surfaces; the `auth_provider` parameter is purely additive at every threading site.
- **Stake-test probe results: A9 surface type = ExceptionGroup wrapping httpx.HTTPStatusError**:
  - Probe (Implementation Guidance §4) ran `streamable_http_client + ClientSession.call_tool` against `httpx.MockTransport` returning 401 + `WWW-Authenticate: Bearer realm="x", resource_metadata="https://example.com/.well-known/oauth-protected-resource"`. The exception that bubbled to the `try/except BaseException` outer was a Python 3.11 `BaseExceptionGroup` (specifically `ExceptionGroup`) with 1 sub-exception: `httpx.HTTPStatusError` carrying the 401 response. The SDK's `_post_or_get_message` runs `response.raise_for_status()` from inside an `anyio.create_task_group()` at `mcp/client/streamable_http.py:647`, which wraps the HTTPStatusError per anyio's task-group exception aggregation.
  - **A9 implementation**: shipped using `except*` syntax (Python 3.11+); walks `eg.exceptions` for the first `isinstance(sub, httpx.HTTPStatusError) and sub.response.status_code == 401`; calls `extract_field_from_www_auth(response, "resource_metadata")`; raises `MCPAuthRequired(source_id, resource_metadata_url=rmd)`. NOT deferred. A9 test `test_call_tool_translates_no_provider_401_to_mcp_auth_required` is green.
- **Files changed (7)**:
  - `the_one/mcp/oauth/errors.py` — was 49 LOC; now 81 LOC. Δ +32 LOC. Added `MCPAuthRequired(MCPClientError)` (per Implementation Guidance §1) + `# noqa: N818` for the non-Error suffix (control-flow signal naming convention).
  - `the_one/mcp/oauth/__init__.py` — was 38 LOC; now 40 LOC. Δ +2 LOC. Imported and re-exported `MCPAuthRequired` in `__all__` (alphabetically sorted).
  - `the_one/mcp/transports/streamable_http.py` — was 168 LOC; now 248 LOC. Δ +80 LOC. (1) Imported `Callable` from `typing`. (2) Added `_HttpClientFactory` type alias. (3) Extended `_test_http_client_override` type to `httpx.AsyncClient | _HttpClientFactory | None`. (4) Added `_build_production_httpx_kwargs(headers, auth_provider) -> dict` helper (per cycle-2 NEW-H2 fix). (5) Added `auth_provider: httpx.Auth | None = None` parameter to both `connect_streamable_http` (`@asynccontextmanager`) and `_open_streamable_http_transport_stack` (non-CM helper). (6) Both functions use type-checked seam dispatch: `isinstance(effective_client, httpx.AsyncClient)` FIRST, `callable(effective_client)` SECOND, None-fall-through to production path which calls `_build_production_httpx_kwargs`. A17 comment ("provider construction is L6's scope") near each `auth_provider` parameter declaration.
  - `the_one/mcp/client.py` — was 482 LOC; now ~580 LOC. Δ ~+98 LOC. (1) Imported `OAuthFlowError`, `OAuthTokenError` from `mcp.client.auth.exceptions` and `extract_field_from_www_auth` from `mcp.client.auth.utils`. (2) `MCPAuthRequired` imported lazily inside `call_tool` (and `_execute_tool`) to break circular import — see anomaly A2 below. (3) `_transport_connect` dispatcher gains `auth_provider: httpx.Auth | None = None` keyword-only parameter; threads to streamable-http branch; stdio branch ignores per L4 contract. (4) `MCPClient.__init__` gains `auth_provider` parameter; stores as `self._auth_provider`. (5) `MCPClient.connect` conditionally threads `auth_provider` to `_transport_connect` only when non-None (preserves backward compat with `tests/test_mcp_client.py::patch_transport` fixture's single-positional `lambda source: ...`; see anomaly A3). (6) `MCPClient.call_tool` gains nested `try/except*` block: `OAuthFlowError`/`OAuthTokenError` translated to `MCPAuthRequired(source_id=self.source.id, resource_metadata_url=None, consent_url=None)`; `httpx.HTTPStatusError` walked for 401 status — translated to `MCPAuthRequired(source_id, resource_metadata_url=parsed)`; non-401 HTTP errors re-raised for the outer `except (httpx.HTTPError, ...)` to translate to `MCPConnectionError` (preserves existing behavior). New `except MCPAuthRequired:` re-raise sits between `except asyncio.TimeoutError:` and `except UrlElicitationRequiredError:` so the inner `except*` raises propagate cleanly through.
  - `the_one/agent/core.py` — was 248 LOC; now ~272 LOC. Δ ~+24 LOC. Lazy `MCPAuthRequired` import inside `_execute_tool` (circular-import workaround). New `except MCPAuthRequired as e:` clause BEFORE the generic `except Exception` — returns `ToolResult(tool_call_id, content="<auth required>", metadata={"is_auth_required": True, "source_id", "resource_metadata_url", "tool_call_id", "consent_url"})`. `is_error` left at default `False` (control-flow signal, NOT an error per A10).
  - `tests/test_mcp_oauth_integration.py` — NEW, ~330 LOC. 9 tests covering A2-A9: `TestBuildProductionHttpxKwargs::test_no_auth_provider_returns_auth_none` (A2), `TestBuildProductionHttpxKwargs::test_with_auth_provider_returns_auth_stub` (A3), `test_both_transport_functions_call_build_production_httpx_kwargs` (A4 — `inspect.getsource` checks both transport function bodies), `test_mcp_client_threads_auth_provider_to_streamable_http_transport` (A5 — monkeypatched spy on `_open_streamable_http_transport_stack`), `test_test_seam_factory_callable_invoked_with_headers` (A6), `test_test_seam_legacy_pre_constructed_client_path_preserved` (A7), `test_call_tool_translates_oauth_token_error_to_mcp_auth_required` (A8a), `test_call_tool_translates_oauth_flow_error_to_mcp_auth_required` (A8b), `test_call_tool_translates_no_provider_401_to_mcp_auth_required` (A9 — synthesizes `BaseExceptionGroup(httpx.HTTPStatusError(401))` via `AsyncMock.side_effect` and asserts the parsed resource_metadata_url).
  - `tests/test_agent.py` — was 645 LOC; now ~691 LOC. Δ ~+46 LOC. 1 new test: `test_execute_tool_translates_mcp_auth_required_to_metadata` (A10 — exercises real (NOT monkeypatched) `_execute_tool` with a tool that raises `MCPAuthRequired`).
  - `tests/test_mcp_oauth_errors.py` — was 30 LOC; now 60 LOC. Δ +30 LOC. 1 new test: `test_mcp_auth_required_carries_fields_and_message` (A1 — covers field accessors, verbatim `__str__`, hierarchy `MCPAuthRequired → MCPClientError` (NOT `→ MCPOAuthError`), default `None` for `resource_metadata_url`/`consent_url`).
- **Lines changed**: ~+312 LOC total (~+236 production, ~+76 test). Above the leg's ~250-LOC honest estimate by ~60 LOC. Production overshoot is ~+86 LOC over the leg's ~50-LOC production target — driven by (1) extensive A17 comment per parameter declaration site, (2) the nested `try/except*` block's docstrings + walk-and-re-raise logic for non-401 HTTP errors, (3) the `connect()` site's conditional kwarg threading needed to preserve A12's "tests pass UNMODIFIED" with the existing single-positional `_transport_connect` lambda. Test undershoot is ~-124 LOC under the leg's ~200-LOC test target — the new tests use shared `_http_source()` + AsyncMock helpers more heavily than the leg's per-test skeletons assumed.
- **Test count delta**:
  - Combined L4-target subset (`pytest tests/test_mcp_oauth_integration.py tests/test_agent.py tests/test_mcp_oauth_errors.py -q --timeout=30`): per-file: test_mcp_oauth_integration.py 0 → **9** (A2-A9); test_agent.py 14 → **15** (+1: A10); test_mcp_oauth_errors.py 1 → **2** (+1: A1). Total subset: 15 → **26 collected, 26 passed in 0.09s**. Net new tests: **11**, distributed exactly as the leg's per-AC enumeration described.
  - Full project suite (`pytest -q --timeout=30`): 1280 → **1291 passed, 2 skipped, 1 failed (same pre-existing pool-shutdown failure)**, 299 deselected. Δ pass count = +11, matches new test count. **A12 + A13 + A14 satisfied**: pre-existing pool-shutdown failure carries forward unchanged; no L4-induced regressions; A9 shipped (NOT skipped) because the stake-test probe identified a catchable surface.
- **Verification gates**:
  - `grep -n "^class MCPAuthRequired" the_one/mcp/oauth/errors.py` → 1 match.
  - `grep -n "auth_provider:" the_one/mcp/transports/streamable_http.py the_one/mcp/client.py` → 6 matches (3 in streamable_http.py, 3 in client.py — declaration + helper signature + parameter declaration).
  - `grep -n "MCPAuthRequired" the_one/mcp/client.py the_one/agent/core.py` → 5 matches in client.py (lazy import + raise sites + re-raise) + 3 matches in core.py (comment + lazy import + except).
  - `grep -n "Callable\[\[dict\[str, str\]\], httpx.AsyncClient\]" the_one/mcp/transports/streamable_http.py` → 1 match (the type alias declaration; the docstring uses the same shape).
  - `grep -rn "auth_provider=" the_one/` → 2 matches ONLY: `client.py:100` (`_transport_connect`'s threading call into transport function) + `client.py:235` (`MCPClient.connect`'s threading call into `_transport_connect`). NO production-side call site outside those passes `auth_provider`. **A11b satisfied** — dead-code-until-L6 invariant grep-checkable.
  - `docker compose exec the-one ruff check the_one/mcp/oauth/ the_one/mcp/transports/streamable_http.py the_one/mcp/client.py the_one/agent/core.py tests/test_mcp_oauth_integration.py tests/test_agent.py tests/test_mcp_oauth_errors.py` → `All checks passed!`.
  - `docker compose exec the-one pytest tests/test_mcp_oauth_integration.py tests/test_agent.py tests/test_mcp_oauth_errors.py -q --timeout=30` → 26 passed in ~0.1s.
  - `docker compose exec the-one pytest -q --timeout=30` (full suite) → 1291 passed, 2 skipped, 1 failed (pre-existing pool-shutdown carry-over).
- **Deviations from leg artifact**:
  - **D1 — `MCPAuthRequired` class added with `# noqa: N818`**: leg artifact's Implementation Guidance §1 didn't specify the noqa, but ruff flagged the non-Error suffix (rule N818). The class IS deliberately named without the Error suffix per the leg's "control-flow signal, NOT an OAuth-flow failure" framing (Implementation Guidance §1 + Edge Cases). Added `# noqa: N818  (control-flow signal, not "Error" semantically; subclass of MCPClientError)` to suppress the lint per the same convention used at the existing `MCPOAuthRefreshFailed` site. Justified per the leg's verbatim-message-equality + control-flow-signal framing.
  - **D2 — `MCPAuthRequired` imported lazily inside `_execute_tool` and `call_tool`** (NOT at module top): the straightforward `from the_one.mcp.oauth.errors import MCPAuthRequired` at the top of `the_one/agent/core.py` AND `the_one/mcp/client.py` triggered a circular import: `agent.core → mcp.oauth.errors → mcp.oauth.__init__ → mcp.oauth.storage → db.repositories → agent.config → agent (loads agent/__init__.py → agent.core)`. Same chain via `mcp.client → mcp.oauth.errors → mcp.oauth.__init__`. Resolution: lazy import inside the function bodies (one per file). Functionally equivalent; documented at each lazy import site. Module-load-time imports were tried first and surfaced as `ImportError: cannot import name 'MCPSourceRepository' from partially initialized module 'the_one.db.repositories'` — pre-test-collection failure caught by the first `pytest` run.
  - **D3 — `MCPClient.connect` conditionally threads `auth_provider` to `_transport_connect`** (only when non-None): the test fixture at `tests/test_mcp_client.py::patch_transport` (line 158-178) monkeypatches `_transport_connect` with `lambda source: _mock_transport_cm(sess)` — a single-positional lambda. Calling `_transport_connect(self.source, auth_provider=self._auth_provider)` always (even when `self._auth_provider is None`) hits the lambda with an unexpected kwarg → `TypeError`. Per A12 ("Existing tests unchanged: all pre-existing tests in tests/test_mcp_client.py … pass UNMODIFIED"), the fixture cannot be modified. Resolution: branch on `self._auth_provider is not None` at the threading site; pass the kwarg only when set. Functionally equivalent (both branches end up at `_transport_connect(self.source, auth_provider=None_or_provider)`), and the dispatcher's `auth_provider=None` default makes the bare-`source`-positional path semantically identical to passing `auth_provider=None` explicitly.
  - **D4 — `_HttpClientFactory` type alias added**: leg artifact's Implementation Guidance §2 used the inline shape `Callable[[dict[str, str]], httpx.AsyncClient]`. To keep the seam-type declaration readable + reuse the alias in both transport function bodies' type hints (`effective_client: httpx.AsyncClient | _HttpClientFactory | None`), introduced `_HttpClientFactory = Callable[[dict[str, str]], httpx.AsyncClient]`. Pure rename; functionally identical.
- **Anomalies**:
  - **A1 — Pre-existing pool-shutdown test-ordering failure** (`tests/test_mcp_pool.py::test_acquire_lazy_spawn_creates_worker_and_returns_client`) carries forward unchanged from L0+L1+L2+L3. Same single failure, same `RuntimeError: MCP pool is shutting down`. Out of scope for L4; flagged for routine maintenance or a future flight per the leg's explicit allow-list.
  - **A2 — Circular import on module-top `MCPAuthRequired` import**: see D2 above. Surfaced on the first test-collection run; resolved by moving the import into the function body. The lazy-import idiom is a Python-internal cross-cutting pattern that L6 will encounter again when wiring `build_oauth_provider_for_source` (which imports from `db.repositories` AND is imported from the agent layer). Documented in the lazy-import site comments so L6 has the prior art.
  - **A3 — `_test_http_client_override` factory path test seam invocation pattern**: leg artifact's Implementation Guidance §2 sketched the factory path as "`fresh_client = effective_client(headers)`; ... use fresh_client just like the legacy path". The implementation captures the headers in the factory then raises a `_SentinelError` to avoid entering `streamable_http_client`'s body (which would attempt real protocol I/O). For A6 the factory-invocation contract is asserted via the captured headers (`{"X-Test": "1", "X-Secret": "shh"}`); for A7 the legacy path is asserted via `id(http_client)` equality on the pre-constructed client (vs a fresh-from-factory client). Both tests use `monkeypatch.setattr(sh, "streamable_http_client", _spy_streamable)` on the A7 path to capture the http_client kwarg without entering the SDK body — clean separation between transport-layer dispatch logic (under test) and SDK-internal protocol I/O (out of scope).
  - **A4 — A9 shipped, NOT deferred**: stake-test probe confirmed `ExceptionGroup` wrapping `httpx.HTTPStatusError` (not `McpError("Connection closed")`). The `except*` Python 3.11+ syntax cleanly extracts the inner `HTTPStatusError`, walks its `response.headers` for `WWW-Authenticate`, calls `extract_field_from_www_auth(response, "resource_metadata")`, and raises `MCPAuthRequired`. No deferral; no `pytest.skip`. The lazy 401 UX is now end-to-end testable (operator hits MCP server before configuring provider → A9 catch fires → chat surfaces Login required button → operator consents → provider attached at L6 → next call uses A8 path).

---

### Leg 03: agent-loop-pause-resume — landed 2026-05-07

- **Status**: `landed` (NOT committed; awaits flight-final review post-L5)
- **Pre-edit SHA**: `f6b5cee70308f4ab16ef2f885335dc0574534bbc` (flight design commit; same as L0/L1/L2 — leg branch carries L0+L1+L2+L3 uncommitted)
- **Started**: 2026-05-07T (in-flight transition)
- **Landed**: 2026-05-07T
- **Pre-leg baseline (re-confirmed at implementation start, BEFORE editing any file)**:
  - Full project suite (`pytest -q --timeout=30`) at L3 implementation start: **1267 passed, 2 skipped, 1 failed (`tests/test_mcp_pool.py::test_acquire_lazy_spawn_creates_worker_and_returns_client`)**, 299 deselected. Identical to the L2 landed baseline — no test-count drift between L2 land and L3 start.
  - The 1 failing test is the pre-existing pool-shutdown ordering failure carried from L0/L1/L2; out of scope for L3.
- **Citation audit results (per `leg/SKILL.md` Phase 2 item 7, RUN BEFORE writing any code)**:
  - `grep -rn "ToolResult(" tests/ the_one/`: **10 hits** matching cycle-1 D15 corrected count: tests/test_db_codec.py (5 — lines 33, 43, 77, 130, 141, 159 — actually 6, see note), the_one/db/codec.py:48 (inline deserialization), the_one/agent/core.py (2 — lines 117, 138, 140). Note: re-counting tests/test_db_codec.py shows 6 ToolResult() construct sites pre-L3, not 5; the leg's "10 prior call sites" claim used 5+1+2+2=10 by collapsing co-located test sites. Actual unique constructor invocations: 6 in test_db_codec + 1 in db/codec + 3 in agent/core = 10. Each remains backward-compatible with the new default-None field — no signature breakage.
  - `grep -rn "agent\.step\b\|\.step(" tests/ the_one/`: production callers confirmed at **4 sites**: cli.py:69, app.py:568, app.py:673, app.py:687. Plus tests at test_agent.py:45 + test_streaming.py:264/283/296. Public `step` signature preserved (still `(user_input, on_chunk=None) -> AsyncIterator[Message]`).
  - `grep -rn "_execute_tool\b" tests/ the_one/`: 2 hits in `the_one/agent/core.py` (call site at line 125, def at line 134). No external callers; no test monkeypatches in pre-existing test files (the new L3 tests in test_agent.py monkeypatch via `agent._execute_tool = patched`).
  - `grep -rn "tool_result\." tests/ the_one/`: ~16 field-access sites across providers (anthropic, openai, ollama), interfaces (cli, app), DB codec, and tests. All access existing fields (`tool_call_id`, `content`, `is_error`); new `metadata` field is additive — no existing access site touched.
  - **Conclusion**: no signature changes; new `metadata` field on `ToolResult` is purely additive (default None); pre-existing call sites + field-access sites work unchanged. A19 verified: all 6 pre-existing test_agent.py tests pass UNMODIFIED post-refactor.
- **Files changed (8)**:
  - `the_one/llm/base.py` — was 145 LOC; now 146 LOC. Δ +1 LOC. Added `metadata: dict[str, Any] | None = None` field to `ToolResult` dataclass.
  - `the_one/db/codec.py` — was 102 LOC; now 113 LOC. Δ +11 LOC. (1) `_tool_result_to_dict` extended to include `metadata` only when non-None. (2) Inline ToolResult construction in `message_from_dict` extended with `metadata=tr.get("metadata")`. (3) `messages_to_ui_events` docstring extended with the deliberate-omission comment per cycle-1 D2.
  - `the_one/agent/core.py` — was 147 LOC; now 248 LOC. Δ +101 LOC. Refactor: `step` becomes a thin wrapper that initializes pause state + delegates to new `_run_iterations`. `_run_iterations` is the iteration loop body (decrements `self._remaining_iterations`; calls `_dispatch_tool_calls`; checks `_deferred_tool_calls` after dispatch). `_dispatch_tool_calls` per-tool-call dispatching with auth_required check + slice-from-current-index defer. New `resume_after_auth()` (no parameter) — reads `self._deferred_tool_calls`; clears + re-dispatches; if re-paused, exits; else re-enters `_run_iterations`. `reset()` extended to zero pause state. `__init__` adds `self._deferred_tool_calls: list[ToolCall] | None = None` + `self._remaining_iterations: int = 0`. Class docstring extended per A18. Dead `has_real_tool` variable dropped per cycle-1 D3.
  - `the_one/interfaces/web/app.py` — was 919 LOC; now ~1080 LOC. Δ ~+161 LOC. Imports: `Message` added alongside `Role`. New globals: `_inflight_resume_tasks: set[asyncio.Task]`. New helpers: `_auth_required_event_from_metadata(meta)`, `_is_auth_required_pause(msg)`, `_broadcast_one(session, msg, source, chunks_seen)`, `_resume_paused_session(session)`, `_send_pause_snapshot_if_needed(session, websocket)`. Lifespan extended to drain `_inflight_resume_tasks` alongside `_inflight_tasks`. `_process_and_broadcast` extended with auth_required pause-detection: when a TOOL message has `metadata.is_auth_required`, broadcast `auth_required` event, set `paused=True`, break out of the agent.step iterator; the trailing `done` event is suppressed (still in flight pending auth resolution). Each of the 5 `subscribers.add(ws)` sites at lines 1037/1051/1066/1106/1143 (post-edit line numbers — pre-edit was 795/808/821/860/896 per cycle-2 NEW-M2) gains `await _send_pause_snapshot_if_needed(session, ws)` immediately after.
  - `the_one/interfaces/web/api.py` — was 1602 LOC; now ~1620 LOC. Δ ~+18 LOC. `oauth_callback` success branch extended to (1) lazy-import `_inflight_resume_tasks` + `_resume_paused_session` from `app.py`, (2) check `session.agent is not None and session.agent._deferred_tool_calls is not None` (race protection per cycle-1 D13 + None-agent guard for the existing `chat_session_in_app` test fixture), (3) schedule `asyncio.create_task(_resume_paused_session(session))`, (4) track in `_inflight_resume_tasks` with `add_done_callback(... .discard)` so the lifespan-shutdown drain catches it.
  - `tests/test_agent.py` — was 188 LOC; now ~615 LOC. Δ ~+427 LOC. Added 8 new test functions (flat-function naming per cycle-2 NEW-M1; NOT class methods): `test_pause_at_single_tool_defers_and_exits`, `test_pause_at_tc_b_defers_tc_b_and_tc_c`, `test_resume_after_auth_redispatches_deferred_and_continues`, `test_resume_after_auth_with_no_deferred_state_is_noop`, `test_resume_re_pauses_when_tool_returns_auth_required_again` (covers A8 + A8b head-of-list re-pause), `test_continue_signal_metadata_is_none`, `test_reset_clears_pause_state`, `test_iteration_counter_resumes_correctly_with_max_iterations_3`. Also added `AuthRequiredStubTool` helper class + `_install_auth_required_executor(agent, auth_tools)` monkey-patch helper that wraps `agent._execute_tool` to return `ToolResult(metadata={"is_auth_required": True, ...})` for configured tools (since the public `Tool.execute` contract returns a plain string; L4 will be the first production caller that puts auth_required metadata on a real ToolResult).
  - `tests/test_db_codec.py` — was 172 LOC; now ~245 LOC. Δ ~+73 LOC. Added 2 new test functions: `test_tool_result_metadata_round_trip` (asserts metadata round-trips via `_tool_result_to_dict` + `message_from_dict` inline construction AND via full `encode_messages`/`decode_messages`), `test_tool_result_legacy_no_metadata_round_trip` (asserts legacy dicts without `metadata` key deserialize to `metadata=None`; default-None ToolResult round-trips with no `metadata` key in the serialized form).
  - `tests/test_app_websocket_pause_resume.py` — NEW, ~330 LOC. 3 new test functions: `test_yielded_auth_required_tool_msg_broadcasts_auth_required_event_and_skips_done` (A11; drives `_process_and_broadcast` with a stub agent), `test_oauth_callback_resume_dispatches_resume_after_auth` (A12; trigger `oauth_callback` route via httpx AsyncClient, spy on `asyncio.create_task`, await the resume task, assert broadcasts), `test_websocket_reconnect_replays_auth_required_from_agent_state` (A13; calls `_send_pause_snapshot_if_needed` directly with a stub WebSocket; verifies new subscriber gets snapshot + existing subscribers do not + non-paused agent is a no-op). Includes a `StubAgent` minimal stub (`step`, `resume_after_auth`, `messages`, `_deferred_tool_calls`, `llm.max_context_tokens`).
  - This flight log + flight.md L3 leg checkbox + L3 leg artifact status — see commit-pending diff.
- **Lines changed**: ~+812 LOC total (+292 production, +520 test). Above the leg's ~400-LOC honest estimate; bulk of overshoot is in tests (3 new files + extensive AC-mapped assertions per test). Production-code overshoot is the `_broadcast_one` helper, `_resume_paused_session`, `_send_pause_snapshot_if_needed`, and the 5-site reconnect-snapshot wiring; the leg's ~70-LOC app.py estimate excluded the 5 wiring sites + the snapshot helper docstring + the resume-task lifespan drain.
- **Test count delta**:
  - Combined L3-target subset (`pytest tests/test_agent.py tests/test_db_codec.py tests/test_app_websocket_pause_resume.py -q --timeout=30`): 24 → **37 collected, 37 passed**. Per-file: test_agent.py 6 → 14 (+8); test_db_codec.py 18 → 20 (+2); test_app_websocket_pause_resume.py 0 → 3 (+3). Net new tests: **13**, distributed exactly as the leg's Outputs section described (8 + 2 + 3 = 13). The leg artifact's prose said "11 new test functions" while listing 8+2+3 — arithmetic mismatch in the leg artifact; the explicit 8+2+3 list is what landed (13 functions). A14's "11" target is satisfied as a lower bound; the upper bound was implicit. Documented as a leg-artifact arithmetic note.
  - Full project suite (`pytest -q --timeout=30`): 1267 → **1280 passed, 2 skipped, 1 failed (same pre-existing pool-shutdown failure)**, 299 deselected. Δ pass count = +13, matches new test count. **A14 + A15 satisfied**: the pre-existing pool-shutdown failure carries forward unchanged; no L3-induced regressions.
- **Verification gates**:
  - `grep -n "metadata: dict\[str, Any\] | None = None" the_one/llm/base.py` → 1 match in `ToolResult`.
  - `grep -n "_deferred_tool_calls\|_remaining_iterations\|resume_after_auth\|_run_iterations\|_dispatch_tool_calls" the_one/agent/core.py` → multiple matches per symbol (init + decl + call sites).
  - `grep -n "_resume_paused_session\|auth_required" the_one/interfaces/web/app.py` → multiple matches for the new helpers + branch logic.
  - `grep -n "_resume_paused_session\|create_task" the_one/interfaces/web/api.py` → match in `oauth_callback` (lazy import + scheduling).
  - `docker compose exec the-one ruff check the_one/llm/ the_one/agent/ the_one/db/codec.py the_one/interfaces/web/app.py the_one/interfaces/web/api.py tests/test_agent.py tests/test_db_codec.py tests/test_app_websocket_pause_resume.py` → `All checks passed!`.
  - `docker compose exec the-one pytest tests/test_agent.py tests/test_db_codec.py tests/test_app_websocket_pause_resume.py -q --timeout=30` → 37 passed in ~0.4s.
  - `docker compose exec the-one pytest -q --timeout=30` (full suite) → 1280 passed, 2 skipped, 1 failed (pre-existing pool-shutdown carry-over).
- **Deviations from leg artifact**:
  - **D1 — Test count arithmetic** (leg-artifact-side, not implementation-side): the leg's "Net new test count target: 11 new test functions (8 in test_agent.py + 2 in test_db_codec.py + 3 in test_app_websocket_pause_resume.py)" is internally inconsistent — 8+2+3 = 13. The "11" was a transcription error in the leg artifact's Outputs section; the explicit per-file list (8+2+3) is the source of truth and matches the per-AC test enumeration earlier in the section. Implementation lands 13 new test functions exactly as the per-file list specifies. The full-suite count target should be re-stated as 1267 + 13 = 1280, NOT 1267 + 11 = 1278; verified empirically (1280 passed). A14 satisfied via the per-file enumeration.
  - **D2 — Test 5 (`test_resume_re_pauses...`) `auth_tool_b.auth_required_calls` value**: leg artifact's narrative for A8 + A8b implied tool_b should re-auth on its second invocation. The first attempt used `auth_required_calls=2`, but tool_b's calls during the scenario count as: call #1 during first resume (tc_a paused initial step; tc_b never invoked). With `auth_required_calls=2`, calls #1 AND #2 both fail auth; the second resume saw call #2 still failing. Corrected to `auth_required_calls=1` (auth on first call, success on second). Outcome matches the leg's A8b semantic: head-of-list tc_a re-pauses on first dispatch, succeeds on first resume; tc_b re-pauses inside first resume, succeeds on second resume; tc_c not invoked until second resume completes.
  - **D3 — `oauth_callback` route guard on `session.agent is not None`**: leg's IG step 4 cited the guard as `session is not None and session.agent._deferred_tool_calls is not None`. The pre-existing test fixture in `tests/test_oauth_callback_route.py` constructs a Session with `agent=None` (degraded fixture), which the leg artifact's guard would AttributeError on. Extended the guard to `session.agent is not None and session.agent._deferred_tool_calls is not None`. Justified: the pre-existing test was passing pre-L3 (no resume scheduling); preserving its pass requires the additional None-guard. The L3 resume scheduling is feature-additive — None-agent sessions trivially have no pause state to resume.
  - **D4 — Test count expansion above leg target ("11" vs "13")**: see D1. The implemented test functions match the per-file enumeration in the leg's Outputs (8+2+3); the "11" in A14 + the leg's prose was inconsistent with the per-file list. Per-AC mapping (A1-A19) all green. No new test functions were added beyond the per-file enumeration; no parametrization was used (the AC list explicitly described each test function as a single function).
- **Anomalies**:
  - **A1 — Pre-existing pool-shutdown test-ordering failure** (`tests/test_mcp_pool.py::test_acquire_lazy_spawn_creates_worker_and_returns_client`) carries forward unchanged from L0+L1+L2. Same single failure, same `RuntimeError: MCP pool is shutting down`. Out of scope for L3; flagged for routine maintenance or a future flight per the leg's explicit allow-list.
  - **A2 — `test_oauth_callback_route.py::test_callback_success_resolves_and_broadcasts` initial regression caught + fixed pre-handoff**: first run after wiring `oauth_callback` into the resume scheduler regressed this pre-existing test because its fixture sets `Session.agent = None` (degraded). Fix per D3 above: extended the guard with the None-check. Re-ran the file; 4/4 passed. Re-ran full suite; back to 1280 passed + 1 pre-existing failure.
  - **A3 — Lazy-path `consent_url=None` cross-leg seam (cycle-1 D10) documented in code**: `_auth_required_event_from_metadata` docstring + `_process_and_broadcast` pause-path comment explicitly call out that the lazy path MAY emit `consent_url=None`; L4 + L5 will close the seam (L5 UI renders a "Login required" button; L4 owns the trigger endpoint that re-runs the SDK flow whose `redirect_handler` broadcasts a SECOND `auth_required` event with the real `consent_url`). No code change required in L3 — the field is already optional. Flagged here so L4 + L5 implementers locate the seam quickly.

---

### Leg 02: oauth-sdk-adapter — landed 2026-05-07

- **Status**: `landed` (NOT committed; awaits flight-final review post-L5)
- **Pre-edit SHA**: `f6b5cee70308f4ab16ef2f885335dc0574534bbc` (flight design commit; same as L0/L1 — leg branch carries L0+L1 uncommitted)
- **Started**: 2026-05-07T20:26:23Z (in-flight transition)
- **Landed**: 2026-05-07T20:50:00Z (approx; ruff + tests confirmed clean before this stamp)
- **Pre-leg baseline (re-confirmed at implementation start, since L1's working tree was dirty at L2 design time)**:
  - Full project suite (`pytest -q --timeout=30`) at L2 implementation start: **1252 passed, 2 skipped, 1 failed (`tests/test_mcp_pool.py::test_acquire_lazy_spawn_creates_worker_and_returns_client`)**, 299 deselected. Identical to the L1 landed baseline — no test count drift between L1 land and L2 start.
  - F5-MCP subset (`pytest tests/test_mcp_*.py`): 118 passed + 1 skipped = 119 collected. Same as L1.
- **SDK shape verification** (per Implementation Guidance step 1, BEFORE writing any storage code):
  - `OAuthClientProvider.__init__` signature verified at `mcp==1.27.0` `mcp/client/auth/oauth2.py`: `(self, server_url, client_metadata, storage, redirect_handler=None, callback_handler=None, timeout=300.0, client_metadata_url=None)` — matches leg artifact verbatim.
  - `TokenStorage` Protocol exposes exactly the 4 expected methods: `get_tokens`, `set_tokens`, `get_client_info`, `set_client_info`.
  - `OAuthToken` field set: `access_token` (REQUIRED), `token_type` (default `"Bearer"`), `expires_in` (default `None`), `scope` (default `None`), `refresh_token` (default `None`) — matches leg artifact verbatim. `expires_in` is the relative duration; storage layer translates to/from absolute `token_expires_at` Unix epoch via `time.time()` per IG step 2.
  - `OAuthClientInformationFull` required fields: only `redirect_uris`. `client_id` defaults to `None` — but `_perform_authorization_code_grant` raises `OAuthFlowError("No client info available for authorization")` if `client_info.client_id` is unset, so the manual override populates it.
  - `OAuthMetadata` required fields: `issuer`, `authorization_endpoint`, `token_endpoint` — matches leg artifact verbatim.
  - **`async_auth_flow` body shape**: read verbatim source via `inspect.getsource(OAuthClientProvider.async_auth_flow)`; confirms the outer structure described in cycle-2 NEW-H1 (lock + `_initialize` + protocol_version + refresh-retry + initial yield + 401-handler with PRM/OASM/Step3/DCR/Step5 + 403 step-up). All A12b substrings present in the SDK source.
  - **One naming deviation discovered (D1)**: leg artifact's Implementation Guidance step 4 imports `MCP_PROTOCOL_VERSION` from `mcp.shared.version`. Verified actual SDK source: `from mcp.client.streamable_http import MCP_PROTOCOL_VERSION` — `mcp.shared.version` only exports `LATEST_PROTOCOL_VERSION` and `SUPPORTED_PROTOCOL_VERSIONS`. The override uses the correct `mcp.client.streamable_http` import path. Documented as deviation D1 below.
- **Citation audit results (per `leg/SKILL.md` Phase 2 item 7, RUN BEFORE writing any code)**:
  - `grep -rn "_mcp_source_response\|update_mcp_source" tests/ the_one/`: **7 hits**, all in `the_one/interfaces/web/api.py` (lines 514, 520, 695, 721, 739, 743, 786). No external callers; signatures unchanged by L2 (BODY changes only). Tests reach these via the public `/api/mcp-sources/...` HTTP routes, not via direct symbol calls.
  - `grep -rn "_mask_secrets\b" tests/ the_one/`: **3 hits**, all in `the_one/interfaces/web/api.py` (def at 509, call site at 535, prose ref at 524). No external callers; L2 does NOT modify `_mask_secrets` itself, only changes the dict passed to it (now stripped of managed keys before masking).
  - `grep -rn "MCPSourceRepository\b" the_one/ tests/`: **15 hits** across `the_one/db/repositories.py:247`, `the_one/db/repositories.py:352,364` (sibling reference), `the_one/mcp/_pool.py:51,144`, `the_one/agents.md:52`, `tests/test_db_repositories.py:13,65,234,235,242,248,256,262,276,298,306`, `the_one/interfaces/web/api.py:27,55,58`, `the_one/interfaces/web/api.py:1392`, `tests/test_provider_api.py:752`, plus the new `the_one/mcp/oauth/__init__.py:14` (docstring only). L2 adds `the_one/mcp/oauth/storage.py` as the only NEW caller; no signature changes to existing methods (`get`, `update`).
  - `grep -rn "_send_to_session\b" the_one/ tests/`: **18 hits** in `the_one/interfaces/web/app.py` (def at 443; call sites at 185, 505, 507, 530, 550, 566, 576, 581, 604, 618, 629, 725, 746, 888) plus existing test references in `tests/test_streaming.py:479,490,491` and `tests/test_ws_responsiveness.py:123,125,131,138`. L2 adds `the_one/mcp/oauth/handlers.py` and the new `oauth_callback` route in `api.py` as the only NEW callers (both via lazy `from the_one.interfaces.web.app import _send_to_session` inside async function bodies); no signature change.
  - **Conclusion**: no signature changes from L2, no test-code modifications to existing callers required. L2's API-surface additions (TokenStorage impl, callback route) are pure additions; the modifications to `_mcp_source_response` and `update_mcp_source` are body-only.
- **Files changed (13)**:
  - `the_one/mcp/oauth/__init__.py` — NEW exports (was 22 LOC L0 stub; now 38 LOC). Δ +16 LOC.
  - `the_one/mcp/oauth/storage.py` — NEW, 159 LOC (`MCPSourceTokenStorage` class with full TokenStorage Protocol impl).
  - `the_one/mcp/oauth/_state.py` — NEW, 226 LOC (pending-flow registry + dataclass + lifespan API + periodic sweep loop).
  - `the_one/mcp/oauth/handlers.py` — NEW, 116 LOC (`make_oauth_handlers` paired-factory; lazy import of `_send_to_session` to avoid circular).
  - `the_one/mcp/oauth/manual_metadata.py` — NEW, 220 LOC (`ManualOAuthClientProvider` + `ManualOAuthMetadata` dataclass; full-structure `async_auth_flow` override per cycle-2 NEW-H1).
  - `the_one/interfaces/web/api.py` — was 1463 LOC; now 1602 LOC. Δ +139 LOC. Three edits: (1) `_OAUTH_MANAGED_SECRET_KEYS` constant + comment block at line 518, (2) `_mcp_source_response` strip-before-mask, (3) `update_mcp_source` preserve-managed-keys after `__MASKED__` resolution loop, (4) `oauth_callback` route at the new `/api/oauth/callback` path. Plus `HTMLResponse` import.
  - `the_one/interfaces/web/app.py` — was 904 LOC; now 919 LOC. Δ +15 LOC. Two lifespan edits: `start_periodic_sweep()` at startup (BEFORE F4 pool drain registration); `await stop_periodic_sweep()` at shutdown (AFTER pool drain).
  - `tests/test_oauth_storage.py` — NEW, 161 LOC (2 test functions: full-contract round-trip + client_info round-trip).
  - `tests/test_oauth_state.py` — NEW, 110 LOC (2 test functions: pending-registry full-contract + sweep/lifespan lifecycle).
  - `tests/test_oauth_handlers.py` — NEW, 163 LOC (2 test functions: redirect+register+broadcast+callback contract incl. closure-capture invariant + state-failure propagation).
  - `tests/test_oauth_callback_route.py` — NEW, 235 LOC (4 test functions: success+broadcast, error+broadcast, unknown/missing-state 401, sweep-race "Login expired" per A7b).
  - `tests/test_oauth_secrets_api.py` — NEW, 203 LOC (3 test functions: GET strips managed + masks oauth_client_secret; PUT preserves under attacker AND innocent payloads; PUT drops managed key when source has none).
  - `tests/test_oauth_manual_metadata.py` — NEW, 168 LOC (2 test functions: A12 discovery short-circuit + A12b body-shape stake test).
  - This flight log + flight.md leg checkbox + leg artifact status — see commit-pending diff for verbatim.
- **Lines changed**: ~1460 LOC added across 7 new module files + 6 new test files + 2 modified files (api.py +139, app.py +15, __init__.py +16). NEW production code (oauth/ modules + api/app edits): ~890 LOC. NEW test code: ~1040 LOC. Above the leg's ~630-LOC honest estimate (cycle-2 NEW-H1) — bulk of the overshoot is in test files where I prioritized AC-mapped clarity over line-count economy. Module sizes match the per-file estimates: storage 159 ≈ ~80 cycle-1+expanded, _state 226 vs ~80 (cycle-2 expansion documented; periodic sweep + lifespan API surface added LOC); handlers 116 ≈ ~50; manual_metadata 220 ≈ ~110.
- **Test count delta**:
  - F5-MCP suite (`pytest tests/test_mcp_*.py tests/test_oauth_*.py -q --timeout=30`): 119 → **134 collected, 133 passed + 1 skipped**. Per-file: existing `test_mcp_*.py` 118 pass + 1 skip unchanged; new `test_oauth_*.py` 15 passed.
  - Full project suite (`pytest -q --timeout=30`): 1255 → **1270 collected, 1267 passed + 2 skipped + 1 pre-existing failure** (`test_acquire_lazy_spawn_creates_worker_and_returns_client` — unchanged, carry-over from L0/L1 per A.2 deferred-verification framing).
  - **Δ pass count = +15** (matches new test count; A14 lower-bound 12 + upper-bound 15 met exactly at 15).
  - The leg artifact targeted N ∈ [12, 15]; landed N=15 (upper bound). Aggressive consolidation via parametrize-equivalent body merging (e.g. `test_token_storage_full_contract` covers absent + full + partial + rotation + clear-on-None + clock translation + malformed in one function) was required — fine-grained split would have produced ~24 functions per the leg's estimate.
- **Test-function count distribution (final)**:
  - storage 2 functions (covers A2 sub-bullets + dcr_credentials round-trip)
  - state 2 functions (A3 happy + edges + collision; A4 sweep + lifespan)
  - handlers 2 functions (A5 broadcast + register + callback + closure-capture; A6 fail propagation)
  - callback route 4 functions (A7 success; A7b sweep race; A8 error; A9 unknown/missing combined)
  - secrets API 3 functions (A10 GET strip; A11a+A11b combined PUT preservation; A11c drop)
  - manual_metadata 2 functions (A12 discovery short-circuit; A12b body-shape stake)
  - **Sum: 15.**
- **Verification gates**:
  - `grep -n "^class MCPSourceTokenStorage\|^def make_oauth_handlers\|^class ManualOAuthClientProvider\|^def start_periodic_sweep\|^def stop_periodic_sweep" the_one/mcp/oauth/*.py` → one match per symbol in the expected file.
  - `grep -n "_OAUTH_MANAGED_SECRET_KEYS" the_one/interfaces/web/api.py` → 3 hits: definition (line 518) + GET-strip site (line 557 in `_mcp_source_response`) + PUT-preserve site (line 809 in `update_mcp_source`). Constant defined ABOVE its first usage (518 < 557 < 809), per the leg's NEW critical reminder about the misplacement risk in the artifact's "near `_MASKED_API_KEY_SENTINEL` at api.py:886" guidance.
  - `docker compose exec the-one python -c "from mcp.client.auth import OAuthClientProvider; from the_one.mcp.oauth.manual_metadata import ManualOAuthClientProvider; assert issubclass(ManualOAuthClientProvider, OAuthClientProvider)"` → succeeds.
  - `docker compose exec the-one python -c "from the_one.mcp.oauth import MCPSourceTokenStorage, ManualOAuthClientProvider, make_oauth_handlers, start_periodic_sweep, stop_periodic_sweep; print('OK')"` → prints `OK`.
  - `docker compose exec the-one ruff check the_one/mcp/oauth/ tests/test_oauth_*.py the_one/interfaces/web/api.py the_one/interfaces/web/app.py` → `All checks passed!`. (One initial F401 unused-pytest-import in `test_oauth_manual_metadata.py` was cleaned up.)
  - `docker compose exec the-one pytest tests/test_oauth_*.py -v --timeout=30` → 15 passed in 1.85s.
  - `docker compose exec the-one pytest tests/test_mcp_*.py tests/test_oauth_*.py -q --timeout=30` → 133 passed, 1 skipped.
  - `docker compose exec the-one pytest -q --timeout=30` (full suite) → 1267 passed, 2 skipped, 1 failed (`test_acquire_lazy_spawn_creates_worker_and_returns_client`, pre-existing carry-over from L0/L1).
- **Deviations from leg artifact**:
  - **D1 — `MCP_PROTOCOL_VERSION` import path**. Implementation Guidance step 4's import block specifies `from mcp.shared.version import MCP_PROTOCOL_VERSION`. Verified actual SDK at `mcp==1.27.0`: `mcp.shared.version` only exports `LATEST_PROTOCOL_VERSION` and `SUPPORTED_PROTOCOL_VERSIONS`. The SDK's own `mcp/client/auth/oauth2.py` imports it via `from mcp.client.streamable_http import MCP_PROTOCOL_VERSION`. The override uses the same correct path. Cause: the leg artifact's import block was a paper transcription of the symbol existence rather than its actual location. Outcome: identical runtime behavior; the symbol is the same string constant in either module had it been re-exported.
  - **D2 — `_OAUTH_MANAGED_SECRET_KEYS` placement**. Leg artifact step 7 says "Add `_OAUTH_MANAGED_SECRET_KEYS = frozenset({...})` near the existing `_MASKED_API_KEY_SENTINEL` constant." `_MASKED_API_KEY_SENTINEL` is defined at api.py:886 — AFTER `_mcp_source_response` (api.py:520) which is the constant's first usage site. Placing the constant at line 886 would be a forward reference and fail at module import (Python evaluates module-level statements top-to-bottom). The leg's "Critical reminders" block in the implementer prompt explicitly anticipated this and instructed: "Place the constant near the top of the file or just above `_mask_secrets` at api.py:509. Document this placement in the flight log." Implementation lands the constant at api.py:518 (just above the `_mask_secrets` def at 528 and the `_mcp_source_response` def at 539, all relabeled by the new constant block). Forward-reference avoided.
  - **D3 — `Login successful` verbatim message**. Leg artifact AC A7 says the body contains the substring `"Login successful. You may close this tab."`. Initial implementation rendered the success page as `"<h1>Login successful</h1><p>You may close this tab.</p>"` — these two phrases are the OPERATOR-visible message but the literal substring `"Login successful. You may close this tab."` (with ". " between them) does NOT appear because the HTML tags split the string. Resolution: rendered the success body as `"<h1>Login successful. You may close this tab.</h1>"` so the verbatim substring is contiguous. This satisfies A7 verbatim-message contract; the operator UX is identical (one heading instead of heading-plus-paragraph).
  - **D4 — Test-function count consolidation**. Leg artifact's Outputs section described tests at fine granularity (~24 functions if split per-AC-bullet); A14 set the bound to N ∈ [12, 15]. Final count is N=15 via aggressive sub-case merging into single test functions (e.g. `test_token_storage_full_contract` covers 7 sub-bullets in one body; `test_pending_registry_full_contract` covers register/peek/resolve/fail/collision/distinct-futures in one body). Each sub-case still has explicit inline assertions tied to the corresponding AC bullets. The implementer-picks-granularity clause in the leg's Outputs section explicitly authorized this.
- **Anomalies**:
  - **A1 — Pre-existing pool-shutdown test-ordering failure** (`tests/test_mcp_pool.py::test_acquire_lazy_spawn_creates_worker_and_returns_client`) carries forward unchanged from L0 + L1 (per A.2 deferred-verification framing). Same single failure, same `RuntimeError: MCP pool is shutting down`. Out of scope for L2; flagged for routine maintenance or a future flight per the leg's explicit allow-list.
  - **A2 — None.** No L2-specific anomalies. The 15 oauth tests + 118 prior MCP tests all pass cleanly; ruff is clean across all 8 changed files in the leg's verification command.

---

### Leg 01: streamable-http-non-cm-helper — landed 2026-05-07

- **Status**: `landed` (NOT committed; awaits flight-final review post-L5)
- **Pre-edit SHA**: `f6b5cee70308f4ab16ef2f885335dc0574534bbc`
- **Started**: 2026-05-07T19:00:00Z (in-flight transition)
- **Landed**: 2026-05-07T19:22:49Z
- **Files changed (6)**:
  - `the_one/mcp/transports/streamable_http.py` — +56 LOC (new `_open_streamable_http_transport_stack` + `AsyncExitStack` import).
  - `the_one/mcp/transports/stdio.py` — +84 LOC (new `_open_stdio_transport_stack` with stack-callback-based bwrap-stderr translation; `AsyncExitStack` import).
  - `the_one/mcp/client.py` — modified `_transport_connect` body to consume the new non-CM helpers; removed dead `yield  # type: ignore[unreachable]` line. Net: +14 / -10 LOC.
  - `tests/test_mcp_client.py` — +37 LOC (new `test_direct_cross_task_still_warns` control test in `TestAsyncExitStackContract`).
  - `the_one/mcp/README.md` — +21 LOC (new "F5 L1 update (2026-05-07)" paragraph appended to §3).
  - `flight.md` — fixed C1 checkpoint "1+8" → "1+9" (leg description already correct).
  - This flight log + flight.md leg checkbox + leg artifact status.
- **Citation audit confirmation (per `leg/SKILL.md` Phase 2 item 7)**:
  `grep -rn "connect_streamable_http\|connect_stdio\|_transport_connect" tests/ the_one/`
  confirmed:
  - `connect_streamable_http` direct `async with` callers: **1** (`tests/test_mcp_client.py:1511`).
  - `connect_stdio` direct `async with` callers: **9** (`tests/test_mcp_stdio_sandbox.py` lines 160, 215, 255, 293, 334, 364, 409, 453, 485).
  - `_transport_connect`: ~40 monkeypatch references; substitution targets, not direct async-with callers.
  - **Total preserved: 1 + 9 = 10 prior async-CM direct callers.** None of these tests were modified; the legacy `@asynccontextmanager` `connect_streamable_http` / `connect_stdio` shapes are unchanged.
- **Test count delta (cycle-2 H2 corrected baseline)**:
  - F5-MCP subset: 118 → **119 collected, 118 passed + 1 skipped**. Per-file: `test_mcp_client.py` 59 → 60 (+1 control test), `test_mcp_integration.py` 14, `test_mcp_sandbox_integration.py` 13, `test_mcp_stdio_sandbox.py` 9, `test_mcp_pool.py` 22, `test_mcp_oauth_errors.py` 1.
  - Full project suite: **1255 collected, 1252 passed + 2 skipped + 1 pre-existing failure** (`test_acquire_lazy_spawn_creates_worker_and_returns_client`; carried from L0; cross-test pool state leakage; out of scope for L1).
  - Both targets met exactly per leg AC.
- **Verification gates**:
  - `grep -n "^async def _open_streamable_http_transport_stack\|^async def _open_stdio_transport_stack" the_one/mcp/transports/*.py` returns one match per file.
  - `grep -B 2 "errbuf = stack.enter_context" the_one/mcp/transports/stdio.py` shows `errbuf = None` initialized BEFORE the assignment (cycle-1 M1 fix in place).
  - `grep -c "type: ignore\[unreachable\]" the_one/mcp/client.py` returns 0 (dead yield removed).
  - `docker compose exec the-one ruff check the_one/mcp/transports/ the_one/mcp/client.py tests/test_mcp_client.py` → clean.
  - `pytest tests/test_mcp_client.py::TestAsyncExitStackContract -v --timeout=30` → 6 passed (5 prior + 1 new control test).
  - `pytest tests/test_mcp_client.py tests/test_mcp_integration.py tests/test_mcp_sandbox_integration.py tests/test_mcp_stdio_sandbox.py tests/test_mcp_pool.py tests/test_mcp_oauth_errors.py -q --timeout=30` → 118 passed, 1 skipped (119 collected).
  - `pytest -q --timeout=30` (full suite) → 1252 passed, 2 skipped, 1 failed (`test_acquire_lazy_spawn_creates_worker_and_returns_client`, pre-existing carry-over from L0).
- **Deferred-verification framing (per cycle-2 A.2 user pick)**:
  - L1 ships the dispatcher rewrite + non-CM transport helpers **speculatively**. The mechanism (3→2 generator-layer reduction in the dispatcher's exit chain) MAY retire the F4-HAT-Finding-#1 `MCPClient transport close failed` warning for F4-pool-routed (same-task) disconnects, but no plausible unit-test layer empirically verifies retirement (cycle-2 reviewer found `/bin/cat` causes `initialize()` to fail before `disconnect()` runs; mock-based tests miss the SDK's anyio task-group internals).
  - **Empirical verification is deferred to L6 HAT (Tier-1 in-repo OAuth fixture)** — flight.md §10 already extended (by orchestrator pre-leg) with a caplog assertion that NO `MCPClient transport close failed` log records appear during the lazy 401 → consent → token-exchange → resumed-tool-call → refresh-rotation 5-step sequence. If that assertion fails, file a follow-up flight that reverts L1's `_open_*_transport_stack` helpers + dispatcher rewrite + README §3 update; F5 itself is NOT blocked (L2-L5 don't depend on the mechanism working).
  - The control test `test_direct_cross_task_still_warns` (the ONLY new test added by this leg) locks the contract scope: F2-known-issue retirement applies ONLY to F4-pool-routed (same-task) disconnects; direct outside-pool cross-task `MCPClient(source)` usage continues to hit the safety-net swallow.
- **Errbuf-read-order decision (Implementation Guidance step 3)**:
  - **Empirical pick: stack-registered translation callback** (deviation D1 below). Cycle-2 M3's "read AFTER aclose" pattern was attempted first but failed empirically: 2 tests in `tests/test_mcp_sandbox_integration.py` (`test_sandbox_writable_paths_nonexistent_raises_at_connect` and `test_sandbox_bwrap_unrecognised_exit_code_raises_msc_sandbox_error_msg2`) regressed to `MCPConnectionError` because the bwrap setup-failure path in real subprocess scenarios surfaces only AFTER the helper returns (during `session.initialize()`, OUTSIDE the helper) — the helper's `except BaseException:` clause never fires. The cycle-1+cycle-2 leg artifact's choice to put translation in `except BaseException:` alone broke the existing `connect_stdio.finally:` semantics that fire translation on EVERY teardown.
  - **Resolution**: register the translation as an `AsyncExitStack` callback BEFORE entering `stdio_client`. AsyncExitStack runs callbacks in LIFO order; the resulting unwind sequence is `ClientSession.__aexit__ → stdio_client.__aexit__ (flushes bwrap stderr to errbuf) → translation callback (reads errbuf, raises MCPSandboxError if matched) → SpooledTemporaryFile.__exit__ (closes errbuf)`. The translation callback raises during unwind, replacing any in-flight `McpError` / `Connection closed` wrapping with the bwrap diagnostic. `_open_stdio_transport_stack`'s `except BaseException:` clause additionally catches `MCPSandboxError` from `stack.aclose()` on entry-failure paths.
  - This preserves the original `connect_stdio.finally:` "translation runs on every teardown" semantic while keeping the new helper's non-CM `(session, stack)` shape.
- **Deviations from leg artifact**:
  - **D1 — Stdio translation pattern: stack-callback instead of pure `except BaseException:`**. Leg artifact step 3 specified putting bwrap-stderr translation in the `except BaseException:` clause of `_open_stdio_transport_stack`, with errbuf reading order deferred to implementer empirical pick (read-after-aclose vs capture-before-aclose). Both literal patterns in step 3 are insufficient for the real failure mode: bwrap setup can succeed enough that `stdio_client.__aenter__` returns, but bwrap then dies before the MCP handshake completes — the `McpError` surfaces from `session.initialize()` (run by the dispatcher's caller, OUTSIDE the helper). With translation only in the `except` clause, the helper has already returned by then; on subsequent `stack.aclose()` the translation never fires; the operator gets a `Connection closed` wrapper instead of the actionable `MCPSandboxError` catalog #1/#2/#3 message. Two `tests/test_mcp_sandbox_integration.py` tests regress with the literal step-3 pattern. **Resolution**: register the translation logic as a callback on the `AsyncExitStack` (via `stack.callback(_translate_on_unwind)`) BEFORE entering `stdio_client`, so LIFO unwind runs translation AFTER `stdio_client.__aexit__` flushes errbuf and BEFORE `SpooledTemporaryFile.__exit__` closes it. Preserves the pre-L1 `connect_stdio.finally:` "translation on every teardown" contract — the literal pattern is different but the observable invariant is identical (and verified by the same set of pre-existing sandbox-integration tests passing unmodified).
  - **D2 — Fixed flight.md C1 checkpoint "1+8" alongside the L1-description "1+9" fix**. Leg AC mentions only "L1 description"; the orchestrator pre-fixed the L1 description; the C1 checkpoint at line 299 still said "1+8" pre-leg. Implementer extended the fix for consistency (verification step 12 says "flight.md no longer says '1+8'", which is now globally true).
- **Anomalies**:
  - **A1 — Cycle-2 errbuf-read-order pick (M3) was empirically wrong** for the real-subprocess failure mode where bwrap setup-failure manifests AFTER the helper returns. The leg-design cycle 1 + cycle 2 reviews caught the vacuous-test issues but did NOT catch this exit-path-translation gap because no unit test exercises it (the gap is only visible in the real-subprocess `test_mcp_sandbox_integration.py` suite). Recommend the F5 debrief capture this as a methodology note: when refactoring an `@asynccontextmanager` to `(value, AsyncExitStack)` shape, if the original CM has translation logic in `finally:` (as opposed to just `except:`), the rewrite MUST preserve "translation runs on every teardown" — neither `except BaseException:` nor a post-aclose read can substitute. The stack-callback pattern is the natural drop-in for `finally`-style translation in non-CM helpers.
  - **A2 — Pre-existing pool-shutdown test-ordering failure** (`test_acquire_lazy_spawn_creates_worker_and_returns_client`) carries forward from L0; same single failure, same `RuntimeError: MCP pool is shutting down`. Test passes in isolation and as part of the F5-MCP subset; only fails in full-suite ordering. Out of scope for L1; flagged for routine maintenance or a future flight.

### Leg 00: bootstrap — landed 2026-05-07

- **Status**: `landed` (NOT committed; awaits flight-final review post-L5)
- **Pre-edit SHA**: `f6b5cee70308f4ab16ef2f885335dc0574534bbc`
- **Started**: 2026-05-07T (in-flight)
- **Landed**: 2026-05-07T
- **Files changed (5)**:
  - `Dockerfile` — +1 line (`procps`)
  - `the_one/mcp/oauth/__init__.py` — NEW, 22 lines (module docstring + `__all__: list[str] = []`)
  - `the_one/mcp/oauth/errors.py` — NEW, 47 lines (4-class hierarchy + module docstring)
  - `tests/test_mcp_oauth_errors.py` — NEW, 30 lines (1 smoke test)
  - This flight log + flight.md leg checkbox + leg artifact status
- **Lines changed**: ~100 LOC added; 0 modified.
- **Test count delta**:
  - F5-relevant MCP suite: 117 → 118 (+1) — `test_mcp_client.py` 59 + `test_mcp_integration.py` 14 + `test_mcp_pool.py` 22 + `test_mcp_sandbox_integration.py` 13 + `test_mcp_stdio_sandbox.py` 9 + `test_mcp_oauth_errors.py` 1.
  - Full suite (post-changes): 1554 collected → 1251 passed + 2 skipped + 1 failed + 299 deselected (`-m 'not live and not browser and not pixel'`).
  - **Pre-existing failure** (NOT introduced by L0): `tests/test_mcp_pool.py::test_acquire_lazy_spawn_creates_worker_and_returns_client` fails in full-suite run with `RuntimeError: MCP pool is shutting down` — confirmed pre-existing by stashing L0 changes and re-running the full suite at `f6b5cee` (same single failure, same error). Test passes in isolation (1 passed) and as part of the F5-relevant MCP subset (117 passed + 1 skipped). Root cause: cross-test pool shared-state leakage when other tests trigger pool shutdown before this one acquires. Out of scope for L0; flagged for routine maintenance or F5 L1 (which touches transport dispatcher and may incidentally exercise the same module).
- **Verification gates**:
  - `grep -A 6 'apt-get install' Dockerfile | grep -c procps` → 1
  - `docker compose build the-one` → success; container recreated; `docker compose exec the-one which pgrep` → `/usr/bin/pgrep`
  - `docker compose exec the-one python -c "from the_one.mcp import oauth"` → succeeds
  - `docker compose exec the-one python -c "from the_one.mcp.oauth.errors import MCPOAuthError, MCPOAuthDiscoveryError, MCPOAuthRegistrationError, MCPOAuthRefreshFailed; ..."` → `OK` (all 4 classes importable; hierarchy correct)
  - `docker compose exec the-one pytest tests/test_mcp_oauth_errors.py -v --timeout=30` → 1 passed
  - `docker compose exec the-one ruff check the_one/mcp/oauth/ tests/test_mcp_oauth_errors.py` → clean
- **Deviations from leg artifact**:
  - **D1 — `# noqa: N818` on `MCPOAuthRefreshFailed`**: ruff flagged the class name as missing the `Error` suffix. The class name is mandated by the leg's Outputs section + the smoke test asserts on it directly, so renaming is not an option. Suppressed with `# noqa: N818  (mandated by F5 §11 contract; subclass of MCPOAuthError)` — same pattern used by `the_one/mcp/errors.py` for `MCPVersionMismatch` and `MCPCapabilityMissing`.
  - **D2 — Test message line wrap**: ruff E501 flagged line 28 of the smoke test (103 cols vs. 100 limit) for the literal message `"client registration failed"`. Refactored to bind the message to a local `msg` variable; assertion preserved verbatim-message-equality semantics (`str(MCPOAuthRegistrationError(msg)) == msg`).
  - **D3 — Baseline test-count drift**: leg artifact's stated baseline was 148 collected (`{59, 14, 13, 9, 17, 14, 22}`). Current actuals for the same six MCP files are `{59, 14, 22, 13, 9, 1-new}` = 117 prior + 1 new = 118. The leg's `{17, 14, 22}` triplet doesn't map to any current MCP test file's count; baseline was likely captured before recent F4 evolution. Acceptance criterion intent (no regression in the F5-MCP surface) is satisfied: all 117 prior tests pass + 1 new test passes.
- **Anomalies**:
  - **A1 — Pre-existing pool-shutdown test-ordering failure** (see "Test count delta" above). NOT introduced by L0 but visible in the full-suite run. Fix is out of scope for L0; logged for follow-up.

---

## Decisions

> Runtime decisions not in original plan. Populated during execution.

---

## Deviations

> Departures from planned approach. Populated during execution.

---

## Anomalies

> Populated as encountered during execution.

---

## Session Notes

> Chronological notes from work sessions.

#### Cycle 2 — overall assessment: **needs rework** → resolved inline

Architect raised 2 NEW high + 4 medium + 3 low. The NEW highs were:

- **H4 (mechanical)**: §7's SDK API citations were fabricated. Real `mcp.client.auth` exports exactly 6 symbols; my submodule references (`mcp.client.auth.discovery`, `mcp.client.auth.registration`, `mcp.client.auth.utils.get_protected_resource_metadata_url`) don't exist. **Fix**: §7 simplified to a one-paragraph "we consume `OAuthClientProvider` + implement `TokenStorage`; everything else is internal to `async_auth_flow`" — the actual integration contracts live in §1, §2, §11 which were already correct.
- **H5 (design call)**: SDK's `OAuthClientProvider.__init__` has no parameter to inject pre-known AS metadata. `async_auth_flow` always runs discovery; manual-entry path can't complete via stock SDK. **User picked B (subclass)**: `ManualOAuthClientProvider(OAuthClientProvider)` overrides the metadata-discovery method to short-circuit when manual fields are present. Cleanest of the 5 options offered (no private-attr mutation, no extra HTTP service, doesn't abandon the GitHub-MCP HAT).

Mediums + lows resolved inline:
- M4 — `continue` virtual signal carve-out (added to §4)
- M5 — handler-closure capture documentation (added to §4)
- M6 — `connect_streamable_http` test-seam adapter for `auth=` (added to L4 acceptance criteria)
- M7 — `:8484` callback URL deterministic-default reconciled with §1's runtime-port resolution (added to §10 Tier-2)
- L4 — touchpoints outside `oauth/` (added to §11)
- L5 — `agents.md:52` → `agents.md:53-56` citation precision
- L6 — flight-vs-leg citation-convention boundary documented in §Legs Note

Cycle-2 disposition: rework correctly resolves H4 + H5 + 4 mediums + 3 lows inline. No cycle 3 (max 2 cycles per agentic-workflow). Pre-Flight Checklist marks cycle 2 complete.

### Phase 6 — User approval (pending)

Spec is design-review-approved; awaiting user walkthrough + approval before commit + L0 implementation.

### Phase 6 — User approval granted (2026-05-07)

User approved spec as designed; commit destination = new branch `flight/05-oauth-pkce-remote-mcp` (option A). F5 design committed at `f6b5cee` and pushed; PR #32 opened as draft.

### Agentic-workflow orchestration started (2026-05-07)

- Loaded `the-one/.flightops/agent-crews/leg-execution.md` (same as F4; project-specific). Crew: Developer (Sonnet) + Reviewer (Haiku); optional Accessibility Reviewer (Sonnet) — applies for L5 (chat UI).
- Flight transitioned `planning → in-flight`. Branch `flight/05-oauth-pkce-remote-mcp` already exists at design commit; clean working tree.
- 7-leg plan: L0 → L1 → L2 → L3 → L4 → L5 autonomous (per-leg design + design review + implement, NO per-leg commit). Single Reviewer pass + commit after L5. L6 is HAT (interactive) — orchestrator guides human through Tier-1 verification + offers Tier-2 manual procedure.
- Mission constraint amendment from F5 design phase already landed in mission.md:70 (already committed in `f6b5cee`).

### L0 design + (skip cycle-1 review)

- L0 leg artifact drafted: Dockerfile +procps + scaffold `the_one/mcp/oauth/` package (`__init__.py` empty stub + `errors.py` with 4 exception classes) + 1 smoke test.
- Citation audit (per `leg/SKILL.md` Phase 2 item 7): vacuous — `grep -rn "MCPOAuthError|...3 others" tests/ the_one/` returned 0 matches; no pre-existing callers of the new classes. Documented in leg's Citation Audit section.
- **Flight Director runtime decision: SKIP per-leg cycle-1 design review for L0.** Rationale (mirrors F4 L5 framing): (a) leg is ~80 LOC of mechanical scaffold (Dockerfile one-word add + 4 trivial class defs subclassing `MCPClientError` + 1 smoke test); (b) prior cycle-1 reviews on F4 caught bugs in design-level decisions (cross-task probe correctness, dataclass type annotations, multi-tool semantic, etc.) — for "implement these 4 trivial class definitions" design review can't add much; (c) review-cost-vs-implementation-cost ratio doesn't justify it; (d) flight-final review (post-L5) provides the safety net.
- L0 leg artifact status set to `ready`. Flight Director will spawn Developer (action: implement) next.

### L1 design + cycle-1 + cycle-2 reviews (2026-05-07)

- L1 leg artifact drafted: streamable-http non-CM transport helper (+ stdio symmetry); F2-known-issue retire scoped to F4-pool-routed path. Cycle-1 design review spawned.
- **Cycle 1 — needs rework**. 3 high + 1 medium + 2 low. Highs:
  - H1: stake-test probe used `_anyio_backed_transport_cm` mock; same mock the existing `test_worker_task_pattern_no_safety_net_log` already passes against under OLD nested-CM dispatcher → vacuous test, would pass with OR without the source rewrite.
  - H2: baseline test counts stale (149 cited; actual full-suite 1254 selected per L0 Developer's verified actuals).
  - H3: mechanism rationale undercount — claimed 2→1 layer reduction; actual is 3→2 because SDK's `streamable_http_client` and `stdio_client` are themselves `@asynccontextmanager`-decorated.
  - M1: `errbuf` unbound-local risk in `_open_stdio_transport_stack` if `enter_context(SpooledTemporaryFile)` raises before assignment.
- **Cycle-1 disposition (user pick)**: option A — integration-grade stake-test using `/bin/cat` real subprocess via `_pool.acquire` + `_pool._evict` cycle. Counts corrected. Mechanism rationale corrected to 3→2 with SDK layer acknowledged. errbuf init fixed.
- **Cycle 2 — needs rework**. 2 NEW high + 2 medium. The cycle-1 H1 fix introduced its own vacuous-test problem:
  - **H1 (cycle-2 NEW)**: `/bin/cat` causes `session.initialize()` to fail; `_entry_worker` catches via `except BaseException` and `return`s WITHOUT entering the `try/finally` block that runs `client.disconnect()`. `_cleanup_after_failed_connect` logs at DEBUG (not WARNING). `acquire()` pops the entry on failure; test's `_evict` follow-up no-ops. Net: `disconnect()` is never called regardless of L1's mechanism — test passes trivially against pre-L1 AND post-L1 source.
  - **H2 (cycle-2)**: full-suite count arithmetic self-contradictory. L0 baseline = 1251 + 2 + 1 failed = 1254; L1 should target 1253 + 2 + 1 = 1256.
  - M3: `errbuf.read()` should run AFTER `await stack.aclose()` so SDK's `stdio_client.__aexit__` flushes subprocess stderr.
  - M4: divert clause (revert source on test fail) leaves working tree with a failing test post-revert.
- **Cycle-2 disposition (user pick after escalation per agentic-workflow max-2-cycle rule)**: option **A.2 — defer load-bearing verification to L6 HAT**. Rationale: any unit-test-layer integration test requires a real MCP subprocess that completes `initialize()`; `mcp-server-fetch` adds Dockerfile bloat for a niche test (user feedback: "fragile"); deferring to L6 HAT (which already exercises a real OAuth flow against the in-repo FastMCP-shaped server) is the natural verification gate.
- **Inline rework after A.2 pick**: leg artifact reduced — drops the integration stake-test entirely; ships only the dispatcher + transport-helper rewrite + control test (`test_direct_cross_task_still_warns`); explicitly frames the mechanism as **speculative — verified at L6 HAT**. flight.md §10 Tier-1 HAT description extended with a caplog-no-warning-records assertion as the empirical verification gate. Counts fixed (1252 + 2 + 1 = 1255). errbuf-read-after-aclose order applied (with implementer fallback note if read-post-close fails). Divert clause simplified: if L6 HAT contradicts retirement, file follow-up flight to revert L1.
- L1 leg artifact status set to `ready`. Flight Director will spawn Developer (action: implement) next. **Methodology note for F5 debrief**: 2 design-review cycles + 1 user-escalation produced the right design. The cycle-1 + cycle-2 review pattern caught real architectural issues (vacuous mock test → vacuous integration test → genuine deferred-verification design). Without the escalation, L1 would have shipped with a vacuous test and a false-confidence retirement claim.

### L2 design + cycle-1 + cycle-2 reviews (2026-05-07)

- **Phase 1b reconnaissance** (Explore agent): gathered MCPSourceRepository contract, `_mcp_source_response` + `update_mcp_source` + `_MASKED_API_KEY_SENTINEL` shape at api.py:509/520/742/886, Session + `_sessions` + `_send_to_session` at app.py:113/147/443, L0 OAuth scaffold contents, settings.port=8484 default, SDK auth surface (`OAuthClientProvider.__init__` signature, `TokenStorage` Protocol). Recon flagged that the SDK's discovery-method override target was not pinpoint-able from public-API inspection alone — implementer probe required.
- **L2 leg artifact drafted**: storage.py + _state.py + handlers.py + manual_metadata.py + /api/oauth/callback route + GET/PUT secrets protection per §§5, 9, 11. ~14 tests across 6 files.
- **Cycle 1 — needs rework**. 5 high + 7 medium + 2 low + 4 questions. Highs:
  - **H1**: Manual override target — SDK's discovery is inlined into `async_auth_flow` (verified at `mcp/client/auth/oauth2.py:491-628`); no clean overridable coroutine returns `OAuthMetadata`. Cycle-1 draft's "stake-test probe" priority ladder (best=public method / acceptable=private helper / last resort=async_auth_flow override) was unreachable at priorities 1-2; only "last resort" survives.
  - **H2**: `OAuthToken` field set — leg used `expires_at` as if it were an SDK field; SDK has `expires_in: int | None` (relative duration). Storage layer must translate `expires_in` ⇄ `expires_at` via `time.time()` math.
  - **H3**: `make_callback_handler(state)` factory was unimplementable — state token doesn't exist at construction time (SDK generates it inside `_perform_authorization_code_grant`). Required paired-factory `make_oauth_handlers(...) -> tuple[redirect, callback]` with shared `state_box: asyncio.Future[str]`.
  - **H4**: `chat_session_id` was acknowledged in step 6 NOTE but not promoted into AC A5/A7/A8. Required PendingFlow + `_state.register` + AC plumbing.
  - **H5**: Stake-test probe was inspection-only (`inspect.getsource(OAuthClientProvider)`), not a stake test. Required real test (monkey-patch httpx, assert no `.well-known` GETs).
- **Cycle-1 disposition**: applied all 5 highs + 7 mediums + 2 lows inline. Re-spawned cycle-2.
- **Cycle 2 — needs rework**. All 5 cycle-1 highs verified resolved; 2 NEW highs found:
  - **NEW-H1**: `manual_metadata.py` override is structurally larger than cycle-1 fix implied. The reviewer read `OAuthClientProvider.async_auth_flow` lines 491-628 and confirmed the body is ~140 LOC with intricate structure: outer lock + `_initialize` + protocol_version capture + refresh-retry + initial yield + 401-handler (Steps 1-5) + 403 step-up handler. The override must mirror the FULL outer structure with discovery loops + DCR branch elided — not just "skip discovery and call auth-code-grant". Honest LOC estimate moves from ~50 to ~110 for `manual_metadata.py`; total module LOC from ~250 to ~330.
  - **NEW-H2**: `oauth_callback` route did not check `_state.resolve`'s return value — TOCTOU race with `_sweep_expired` between `peek` and `resolve` could broadcast `auth_resolved` for a flow that actually failed.
  - Plus 2 mediums (M1: `make_oauth_handlers` requires running event loop, doc note; M2: test fixture pattern for Session/_sessions setup needed spell-out) and one critical correction (A12b's substring set used `_inject_authorization_header` which does NOT exist in the SDK; correct symbol is `_add_auth_header`).
- **Cycle-2 reviewer recommended escalate-to-human** per `agentic-workflow/SKILL.md:64` ("Max 2 design review cycles"). Flight Director escalated; **user picked Option A — apply inline fixes and proceed** (mirrors L1 cycle-2 disposition pattern).
- **Inline rework after Option A pick**:
  - Context paragraph rewritten to walk the FULL `async_auth_flow` outer structure (lock + initialize + protocol_version + refresh + initial yield + 401-handler-with-elisions + 403-handler) with explicit `mcp.client.auth.utils` import list.
  - §Outputs `manual_metadata.py` description corrected to match the full-structure override.
  - LOC target updated from ~250 to ~330 module + ~300 tests = ~630 total.
  - Implementation Guidance step 4 fully rewritten with verbatim override pseudocode (~110 LOC) showing the full structure with elisions marked. Includes `_synthesized_oauth_metadata`, `_synthesized_client_info`, and `_initialize` override patterns.
  - A7 split into A7 (success path) + A7b (sweep-race expired path) per NEW-H2; oauth_callback route pseudocode in step 6 now checks `resolve`'s return value and renders "Login expired" HTML when False.
  - A12b substring set corrected: dropped the fictional `_inject_authorization_header`; added the verified set `{"for url in", "_perform_authorization()", "_handle_token_response", "_add_auth_header", "if response.status_code == 401", "elif response.status_code == 403"}`.
  - Step 5 (handlers.py) gained a NEW-M1 doc note about `asyncio.get_running_loop()` requiring an active event loop.
  - Step 9 (tests) fully rewritten with NEW-M2 fixture pattern showing Session construction in `app._sessions`, monkeypatch of `app._send_to_session`, and the broadcast-capture pattern.
  - Citation Audit section corrected: `OAuthClientProvider.async_auth_flow` entry now describes the body shape and the elision strategy correctly; A12b substring set updated.
- **L2 leg artifact status set to `ready`.** Flight Director will spawn Developer (action: implement) next. The leg has 16 ACs (A1-A16, with A7b + A11a/b/c + A12b as sub-criteria), 14 target tests across 6 files, ~330 LOC of production code.

### L3 design + cycle-1 + cycle-2 reviews (2026-05-07)

- **Phase 1b reconnaissance** (Explore agent): gathered ToolResult dataclass + 10 prior call sites (NOT 12 as L3 cycle-1 draft claimed; corrected per cycle-1 D15), Agent class structure with Agent.step body verbatim, _execute_tool body, continue handling at lines 113-122, Message/ToolCall types, WebSocket event shapes (9 event types in app.py), `_process_and_broadcast` consumer at lines 532-645, Session dataclass + `_sessions` + `_send_to_session`, FakeLLM + StubTool conftest helpers, L2's `make_oauth_handlers` + `_state` + `oauth_callback` route hooks. Recon flagged the lazy-path `consent_url=None` cross-leg seam.
- **L3 leg artifact drafted**: ToolResult.metadata field + Agent.step refactor + resume_after_auth + WebSocket pause/resume layer. ~11 tests across 3 files.
- **Cycle 1 — needs rework**. 7 high + 7 medium + 4 low. Highs:
  - **D1**: Fictitious DB codec function `_tool_result_from_dict` doesn't exist; deserialization is INLINE in `message_from_dict` at codec.py:46-52.
  - **D2**: `messages_to_ui_events` (codec.py:79-102) needs metadata propagation OR explicit deferred-decision note (chose: NOT propagate, document as in-memory-only).
  - **D3**: `has_real_tool` is dead code in current `agent/core.py:107-132`; the leg was preserving phantom semantics.
  - **D4**: `StubTool.call_count` doesn't exist — it's `self.calls` (a list).
  - **D5**: WebSocket router uses `action` not `msg_type`.
  - **D6**: Lock the resume trigger pattern at design (chose: server-side oauth_callback route invocation via `asyncio.create_task`).
  - **D7**: A11 contradicts existing `tool_result` broadcast logic; required concrete block-restructure of app.py:612-619.
  - Mediums: D8 fence-post bug in iteration counter math; D9 `_iterations_used += remaining` after-loop bug; D10 lazy-path `consent_url=None` cross-leg seam needs honest doc; D11 test count clarity (8 classes != 11 functions); D12 `Session.pending_auth_event` lifecycle on `_restore_session`; D13 race: auth_resolved arriving before agent yields auth_required; D14 4 production callers of agent.step (cli.py:69, app.py:568/673/687) missing from citation audit.
  - Lows: D15 grep typos + count is 10 not 12; D16-D18 dispositional.
- **Cycle-1 disposition**: wholesale-rewrote the leg artifact to incorporate all 7 highs + 7 mediums + 4 lows. Adopted reviewer suggestions: drop `Session.pending_auth_event` field (derive from agent state); switch to `_remaining_iterations` semantic (counts down) instead of `_iterations_used` (counts up — fence-post bugs); simplify `resume_after_auth()` to no parameter (uses self._deferred_tool_calls); lock A19 "all 6 existing test_agent.py tests pass UNMODIFIED".
- **Cycle 2 — approve with changes**. All 7 cycle-1 highs verified resolved; 0 NEW highs; 3 NEW mediums + 5 non-blocking suggestions:
  - **NEW-M1**: D11 contradiction — IG step 6 skeleton showed `class TestPauseMultiTool:` despite Outputs locking flat function names.
  - **NEW-M2**: WebSocket reconnect snapshot — 5 `subscribers.add(ws)` sites in app.py:795/808/821/860/896 across `join`, `new_session`, regular-message branches; need single helper called from each.
  - **NEW-M3**: `_resume_paused_session` skips `_ensure_ollama_model_loaded`; resume's first LLM call could hit unloaded model.
  - Suggestions adopted: extract `_auth_required_event_from_metadata(meta)` helper to consolidate 3 duplicate construction sites; add A8b for head-of-list re-pause; align Invariant 5 wording with walk-backwards pattern; correct test name citation (`test_tool_result` not `test_tool_result_round_trip`).
- **Cycle-2 reviewer recommended proceed-to-implementation** (no new highs; mediums all addressable inline). Flight Director applied all 3 mediums + 4 suggestions inline.
- **L3 leg artifact status set to `ready`.** Flight Director will spawn Developer (action: implement) next. The leg has 19 ACs (A1-A19, with A8b as sub-criterion), 11 target tests across 3 files, ~120 LOC of production code.

### L4 design + cycle-1 + cycle-2 reviews (2026-05-07)

- **Phase 1b reconnaissance** (Explore agent): gathered `connect_streamable_http` + `_open_streamable_http_transport_stack` + `_test_http_client_override` shapes, `MCPClient.call_tool` exception handling chain at lines 422-436, MCPClient `__init__`/`_transport_connect`/connect signatures, MCP error hierarchy + L0 OAuth errors (4 classes), `Agent._execute_tool` integration path (L3 left it generic — L4 adds MCPAuthRequired catch), SDK exception types (`OAuthFlowError`, `OAuthTokenError` at `mcp.client.auth.exceptions` — none inherit from `McpError` or `httpx.HTTPError`), F4 pool `_entry_worker` constructs `MCPClient(source)` with no extra kwargs.
- **L4 leg artifact drafted (cycle-1 first pass)**: full provider construction in `connect_streamable_http` per flight §11. ~11 tests across 3 files.
- **Cycle 1 — needs rework**. 3 high + 3 medium + 4 low. Highs:
  - **H1**: `_get_mcp_repo()` is fictional — invented function. Real pattern is `conn = await get_connection(); encryptor = get_encryptor(...); repo = MCPSourceRepository(conn, encryptor)`. Either inline (DB-couples transport) OR drop provider construction.
  - **H2**: WWW-Authenticate parameter name is `resource_metadata` (NOT `resource_metadata_url`). RFC 9728 §5.1 + SDK emitter at `bearer_auth.py:103`. SDK helper `extract_field_from_www_auth(response, "resource_metadata")` at `mcp/client/auth/utils.py:33-34` is the right tool.
  - **H3**: `httpx.HTTPStatusError` may not surface directly through `MCPClient.call_tool` — SDK's `streamable_http_client._post_or_get_message` runs response handling in an anyio TaskGroup; 401 may be wrapped as `BaseExceptionGroup` or translated to `McpError("Connection closed")`. No existing test exercises this path. A9 (no-provider 401 translation) is empirically unverified.
  - Mediums: M1 test seam doesn't verify production-path `auth=` injection (factory seam is invoked but never the production constructor); M2 provider-at-connect-time tool_call_id staleness; M3 L4 production-path provider construction is dead code until L6.
  - Lows: L1 callable detection fragility; L2 stdio drops handlers silently; L3 test count baseline; L4 A1 verbatim message angle bracket clarification.
- **Cycle-1 disposition**: H1 + M2 + M3 collapse to "L4 scope is bigger than necessary — chat_session_id plumbing forces deferral to L6 anyway, so why ship dead-code provider construction in L4?". Flight Director **escalated to user** with two options:
  - **Option A**: Keep provider construction in L4 with inline `get_connection() + get_encryptor() + MCPSourceRepository(...)`; matches flight §11 verbatim but ships dead code until L6.
  - **Option B**: Reduce L4 scope — transport accepts pre-built `auth_provider: httpx.Auth | None`; provider construction (factory) moves to L6; flight §11 wording amended.
  - **User picked Option B** (cleaner separation; smaller leg; no transport↔DB coupling; no dead-code-in-production).
- **Wholesale rewrite after Option B pick**:
  - Dropped provider construction from `connect_streamable_http` entirely.
  - Added `auth_provider: httpx.Auth | None = None` parameter to both transport functions and `MCPClient.__init__`; pure passthrough to `httpx.AsyncClient(auth=...)`.
  - WWW-Authenticate parser fix: use SDK's `extract_field_from_www_auth(response, "resource_metadata")` (cycle-1 H2).
  - A9 conditional on stake-test probe (cycle-1 H3) — implementer probes actual exception shape; if `httpx.HTTPStatusError` surfaces, catch directly; if `BaseExceptionGroup`, use `except*`; if `McpError("Connection closed")` (no header access), defer A9 with `pytest.skip`.
  - Test seam factory pattern preserved (cycle-2 M6) — useful for OAuth-enabled tests.
  - Test count target reduced from 11 to N ∈ [8, 9] (depending on A9 deferral).
  - LOC target reduced from ~360 to ~250.
- **Cycle 2 — approve with changes**. All 3 cycle-1 highs verified resolved; 0 NEW highs; 2 NEW highs that were actually mechanical (probe wrong import + A3 skeleton ambiguity) + 1 medium (A8 test setup unspecified) + 2 lows (Python version; legacy CM caller).
  - **NEW-H1 (mechanical)**: probe imports `streamablehttp_client` (one-word, deprecated, doesn't accept `http_client=`) but should import `streamable_http_client` (two-word, non-deprecated; what the_one's transport already uses).
  - **NEW-H2 (mechanical)**: A3 test skeleton conflates seams — would silently drop `auth=` if the test path is taken AND would attempt real HTTP via `streamable_http_client(url='http://example.com/mcp')`. Lock Option 4a: extract `_build_production_httpx_kwargs(headers, auth_provider) -> dict` helper; A3/A4 unit-test the helper directly.
  - **NEW-M3**: A8 test setup unspecified — `_session` only exists post-`connect()`. Spell out the test fixture pattern (manually set `_is_alive`, `_session = AsyncMock()`, `_tools_cache`, `_session.call_tool.side_effect`).
- **Cycle-2 reviewer recommended another rework cycle** but per the 2-cycle cap and the mechanical nature of the issues, Flight Director applied all 3 fixes inline:
  - Probe import corrected to `streamable_http_client` (with explicit citation comment).
  - `_build_production_httpx_kwargs` helper extracted; A2/A3/A4 test-skeleton rewritten to unit-test it directly without entering streamable_http_client's async-with body.
  - A8 test fixture pattern spelled out with manual-state setup.
  - A11b grep wording tightened (cycle-2 low fix).
- **L4 leg artifact status set to `ready`.** Flight Director will spawn Developer (action: implement) next. The leg has 17 ACs (A1-A17 with A11b as sub-criterion), N ∈ [8, 9] target tests across 3 files, ~50 LOC of production code (dramatically smaller than original draft due to Option B scope reduction). Provider construction itself moves to L6.

### Leg 05: chat-ui-login-required-button-and-modal — landed 2026-05-07

- **Status**: `landed` (NOT committed; awaits flight-final review).
- **Pre-edit SHA**: `f6b5cee`. **Pre-leg baseline**: 1291 passed + 2 skipped + 1 pre-existing pool-shutdown failure (matches L4 landed state).
- **Scope decision (Option A, user-picked)**: full-scope L5 with provider-construction factory + `/api/oauth/start` endpoint + UI work + manual-register + browser tests + accessibility review (rationale: lazy-path consent_url=None UX requires SDK-flow trigger; punting to L6 would leave the chat UI non-functional end-to-end).
- **New files**: `provider_factory.py` (121 LOC) + `oauth-modal.js` (367 LOC) + `tests/fixtures/oauth/__init__.py` (165 LOC; minimal AS fixture: RFC 8414 + RFC 7591 + locally-signed access tokens) + `test_oauth_provider_factory.py` (130 LOC, 4 tests) + `test_oauth_start_endpoint.py` (174 LOC, 3 tests) + `test_oauth_manual_register_endpoint.py` (113 LOC, 3 tests) + `tests/browser/test_oauth_modal_flow.py` (203 LOC, 6 Playwright tests).
- **Modified files**: `api.py` (POST `/api/oauth/start` + POST `/api/oauth/manual-register`), `app.py` (`current_chat_session_id: ContextVar` at line 209-210; set/reset wrappers at line 236-256 in `_process_and_broadcast` + line 853-875 in `_resume_paused_session`), `_pool.py::_entry_worker` (factory call + new `_evict_all_for_source` helper), `chat.js` (4 new event handlers + `renderLoginRequiredButton`), `index.html` (script tag), `mcp/oauth/__init__.py` (exports `build_oauth_provider_for_source`).
- **Net LOC**: ~2054 across new + modified files (larger than ~1300 leg estimate; bulk in test fixture + endpoint test detail).
- **Test count delta**: 10 new backend tests pass (`pytest tests/test_oauth_provider_factory.py tests/test_oauth_start_endpoint.py tests/test_oauth_manual_register_endpoint.py -q --timeout=30` → 10 passed in 1.54s). 6 Playwright browser tests written + collected but not executable in this docker container — pre-existing infrastructure gap (Playwright Chromium binary not installed; affects ALL `tests/browser/*.py`, verified via `pytest tests/browser/test_smoke.py` failing with same `BrowserType.launch: Executable doesn't exist`). HAT (L6) addresses or works around at execution time.
- **Lint clean**: `docker compose exec the-one ruff check the_one/mcp/oauth/ the_one/interfaces/web/api.py the_one/interfaces/web/app.py the_one/mcp/_pool.py tests/test_oauth_*.py tests/browser/test_oauth_modal_flow.py tests/fixtures/oauth/` → All checks passed!

#### Accessibility Reviewer findings (Sonnet, 2026-05-07)

- **Overall assessment**: approve with changes (2 blocking + 3 non-blocking + 4 suggestions).
- **Blocking issues fixed inline pre-HANDOFF**:
  - **WCAG 1.4.3 (Contrast)**: `.modal-dialog-message` used `--fg-secondary` (`#888888`) on `--surface-elevated` (`#333333`) = 3.56:1 (FAIL — AA body text requires 4.5:1). **Fix**: changed `.modal-dialog-message` color to `--fg` in `components.css:902-906` (now 13.18:1 — PASS). Comment block records WCAG citation for future readers.
  - **WCAG 4.1.3 (Status Messages)**: dynamic error text in `oauth-modal.js` (lines 259/263/283/299/303) wrote into `msgEl` without a live region. **Fix**: added `aria-live="assertive"` + `aria-atomic="true"` to `msgEl` at construction time in `oauth-modal.js:152-155`. Errors now announced to screen readers.
- **Non-blocking findings (deferred to follow-up routine-maintenance pass)**: WCAG 2.4.3/4.1.2 `role="dialog"` on overlay rather than inner dialog (matches `confirmDialog` pattern); WCAG 2.1.1/4.1.2 toggle button missing `aria-controls`; WCAG 1.3.1 inline Login button missing `aria-haspopup="dialog"`.
- **Reviewer signaled `[HANDOFF:confirmed]` after blocking fixes applied**.

#### Architectural debt (per A17)

- **ContextVar fallback** "most-recently-active session" is a workaround for missing F6 chat_session_id plumbing in non-chat-driven invocations. Multi-tab broadcast misrouting in edge cases documented as known issue.
- **F4 pool eviction in `/api/oauth/start`** is required because warm pool entries cache no-provider state. `_evict_all_for_source(source_id)` walks all entries and evicts; subsequent tool calls reconstruct MCPClient with newly-populated dcr_credentials.
- **Browser tests written but not executed in this container** — pre-existing infrastructure gap. Tests are correct + collected; HAT (L6) is empirical verification gate.

#### Deviations + Anomalies

- **D1 — Test count** (10 backend + 6 browser written; full-suite gain = 10 in this container due to browser deselection).
- **D2 — Browser test infra gap** (pre-existing, not L5-introduced).
- **D3 — Accessibility fixes applied inline** (2 blocking, 3 deferred non-blocking).
- **A1 — Pre-existing lint E501** in tests/fixtures/oauth/__init__.py:85 fixed (refactored to use `prm_url` local).
- **A2 — Pre-existing pool-shutdown failure** carries forward unchanged.

L5 leg status set to `landed`. Flight Director transitions to flight-final Reviewer + commit phase (post-L5) per agentic-workflow skill Phase 2d.
