# Flight Log: MCP Client Foundation — stdio + Streamable HTTP

**Flight**: [MCP Client Foundation](flight.md)

## Summary

Pre-execution. Phase 1b reconnaissance complete; design decisions §§1–12 locked; legs L1–L6b sketched (L7 optional HAT, total 7 autonomous + 1 optional). Architect design review (Phase 5b) passed after one rework cycle. Ready for execution.

## Architect Design Review (Phase 5b)

**Cycle 1 — overall assessment**: needs rework (3 high, 9 medium, 8 low issues; 8 asks already correctly addressed)

**High-severity issues addressed:**
- Switched all references from deprecated `streamablehttp_client` to current `streamable_http_client` (the new SDK function accepts a pre-built `httpx.AsyncClient`, enabling in-process ASGI integration tests for streamable-http)
- Documented the SDK-vs-F2 strict-version divergence explicitly: SDK accepts `SUPPORTED_PROTOCOL_VERSIONS = ["2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"]`; F2 is *narrower* (exact match to `_PINNED_PROTOCOL_VERSION`). The SDK's own `RuntimeError` from `session.initialize()` on truly-unsupported versions is caught and re-raised as `MCPVersionMismatch` so the operator sees one consistent error type
- Reused canonical `_ENV_ALLOWLIST` from `the_one/platform/env.py` instead of re-declaring; `build_stdio_environ` accepts `allowlist_env` as a parameter for testability while production callers pass `_build_subprocess_env()`

**Medium-severity issues addressed:**
- Renamed F4-pool properties to `is_alive`/`last_activity` matching `PtySession`'s contract (the_one/platform/pty.py:114-128) so F4 can build one reaper code path via structural typing
- Added `MCPTool` dataclass shape definition (§5b) — was referenced but never defined
- Pre-split L6 into L6a (list_tools/call_tool happy path + dataclass) and L6b (input validation + error paths + non-text content blocks) per F1 debrief sizing recommendation
- Enumerated the 6 doc-update contracts in L1's verification step
- Swapped L4↔L5: streamable-http first (in-process ASGI is structurally simpler than stdio subprocess management)
- Added `MCP_DEFAULT_CALL_TIMEOUT_SECONDS = 60` separate from the 30s handshake/list-tools timeout
- Added §12 covering F1's missing `config.env` shape validation; L1 picks up the API patch
- Clarified L2 `last_activity`-update tests use mocked `ClientSession` (real list_tools is L6a)

**Low-severity issues addressed:**
- Added wheel-inspection reproduction recipe to flight-log.md Part C (below)
- Added CVE divert criterion to Adaptation Criteria
- Added F1↔F5 OAuth slot non-dependency reconciliation row (below)
- Added `UrlElicitationRequiredError` propagation note in §3
- L7 HAT structured as 5-step binary go/no-go list with optional bonus step
- Justified `tests/fixtures/mcp/hello_server.py` location (runnable-script convention) in §7
- Tightened `is_alive` semantic during `connect()` ("false until connect() returns successfully") in §9
- Promoted `__repr__` from acceptable variation to default in §2 (small-model error ergonomics)

**Per-leg conventions adopted:**
- Anchor-by-symbol-name for leg artifact citations (F1 debrief recommendation)
- `make lint` clean (or "no NEW ruff errors") in each leg's post-completion checklist before `[HANDOFF:review-needed]`

**Asks already correctly addressed (no changes):** module placement (§1), error hierarchy base class (§3), frozen dataclass for MCPToolResult (§4), `jsonschema` dependency (§5 — verified direct dep of mcp 1.27.0 via wheel METADATA), FastMCP API stability (§6), `build_stdio_environ` parameter form (§11), Python 3.11 compatibility for mcp 1.27.0 (universal `py3-none-any` wheel), mission criteria coverage (Contributing to Criteria section).

**Architect questions resolved:**
- Property naming divergence: aligned to PtySession (`is_alive`/`last_activity`)
- `MCPTool` shape: defined in §5b
- Tools without `inputSchema`: skip validation (matches SDK permissiveness)
- Streamable-http fixture pattern: in-process via `streamable_http_client(http_client=httpx.AsyncClient(transport=ASGITransport))`
- Timeout governance: separate handshake (30s) and call_tool (60s) timeouts
- Strict-equality intent: yes, intentional pre-release narrowing; revisit at 1.0
- `_ENV_ALLOWLIST` reuse: yes (was missed in cycle 1; corrected)
- L4-vs-L5 ordering: streamable-http first (in-process ASGI simpler)
- L7 binary go/no-go: 5 steps must pass (bonus step #6 informational)

**Cycle 2**: not required — all high and medium issues addressed in cycle 1 rework; low issues addressed defensively in the same pass; no substantive new issues introduced (just text edits).

---

## Phase 1b Reconnaissance Report

Verified F1 debrief F2-targeted citations + mapped current codebase landscape.

### Part A: F1 debrief F2-targeted citations

| # | Item | Location | Status | Evidence / Notes |
|---|---|---|---|---|
| 1 | `MCPSource.merged_config()` body | `the_one/db/models.py:61-71` | confirmed-live | `return {**self.config, **self.secrets}` — flat merge. F1 debrief warning correct: NOT directly usable for stdio env-var assembly because `config.env` is a nested dict. F2's `build_stdio_environ` reads `config.env` directly per Design Decision §11 |
| 2 | `MCPSource` model | `the_one/db/models.py:50-59` | confirmed-live | Fields: id/name/type/config/secrets/created_at/updated_at; `type: Literal["stdio", "streamable-http"]` |
| 3 | `MCPSourceRepository` helpers | `the_one/db/repositories.py:247-281` | confirmed-live | Encryptor stored as reference (line 252), `_secrets_to_ciphertext` and `_ciphertext_to_secrets` with InvalidToken-swallow + JSONDecodeError-propagate |
| 4 | API helpers | `the_one/interfaces/web/api.py:509-826` | confirmed-live | `_validate_mcp_source_config:539-628`, `_mask_secrets:509-517`, `_mcp_source_response:520-536`, `_MASKED_API_KEY_SENTINEL:826` |
| 5 | `/api/mcp-sources*` endpoints | `the_one/interfaces/web/api.py:631-736` | confirmed-live | 6 endpoints: list, types (registered before `/{source_id}` per route-ordering invariant), get, create, update, delete |
| 6 | agents.md MCP storage contract | `the_one/agents.md:52-56`; `CLAUDE.md:298-304` | confirmed-live | Field-segregated encryption, per-key __MASKED__, oauth_client_secret routing, all-in-memory rotation invariant — all documented and accurate |

### Part B: F2 integration landscape

| # | Item | Location | Status | Notes |
|---|---|---|---|---|
| 7 | `ToolProvider` protocol | `the_one/tools/provider.py:8-51` | confirmed-live | `@runtime_checkable`; F2 does NOT implement (F6 does — wraps MCPClient → MCPToolProvider) |
| 8 | Agent step loop | `the_one/agent/core.py:50-142` | confirmed-live | Name-based tool dispatch; F2 doesn't wire (F6 wires MCP tools into the registry) |
| 9 | FastAPI lifespan | `the_one/interfaces/web/app.py:47-75` | confirmed-live | F2 keeps MCPClient per-call; no lifespan extension. F4 will integrate the warm-pool drain here |
| 10 | PTY session registry | `the_one/tools/_session_registry.py:1-313` | confirmed-live | F4 will mirror this shape for MCP warm-pool. F2 ignores |
| 11 | Test fixtures (async repo + API) | `tests/test_db_repositories.py:18-74`; `tests/test_db_api.py:197+` | confirmed-live | F2 extends with `tests/test_mcp_client.py` and `tests/test_mcp_integration.py` |
| 12 | Dependencies | `pyproject.toml:6-30` | confirmed-live | Python 3.11+; `mcp` SDK NOT yet pinned. F2's L1 adds `mcp==1.27.0` |
| 13 | Existing MCP server fixture | (search) | not-found | F2's L3 authors `tests/fixtures/mcp/hello_server.py` |
| 14 | CI Dockerfile | `Dockerfile:1-25` | confirmed-live | Python 3.11-slim base; pip install handles SDK addition. No bubblewrap (F3) |
| 15 | CLAUDE.md MCP sections | `CLAUDE.md:74,76-78,298-304` | confirmed-live | All F1 contracts captured; F2 will append entries for `_PINNED_PROTOCOL_VERSION` location, fail-hard version policy, F4-compat invariants |
| 16 | `the_one/` package structure | (directory listing) | confirmed-live | Recommend `the_one/mcp/` as MCPClient home; matches `the_one/llm/` precedent |

### Part C: Cross-cutting verification

- **Mission constraint #45 ("degrade rather than crash") deviation rationale**: F2 deviates with fail-hard at handshake during pre-release. Rationale documented in flight.md Design Decision §10. Mission constraint stays as-is (long-term north star); F2 captures the pre-release stance and revisit-at-1.0 follow-up
- **`mcp==1.27.0` PyPI verification**: `pip index versions mcp` confirmed 1.27.0 as latest stable at flight-design time
- **`mcp==1.27.0` wheel inspection — reproducible recipe**:
  ```bash
  pip download mcp==1.27.0 --no-deps -d /tmp/mcp-wheel
  unzip -p /tmp/mcp-wheel/mcp-1.27.0-py3-none-any.whl mcp/types.py | grep -E "(LATEST_PROTOCOL_VERSION|DEFAULT_NEGOTIATED_VERSION)\s*="
  unzip -p /tmp/mcp-wheel/mcp-1.27.0-py3-none-any.whl mcp/shared/version.py
  unzip -p /tmp/mcp-wheel/mcp-1.27.0-py3-none-any.whl mcp/client/streamable_http.py | grep -nE "^def (streamable_http_client|streamablehttp_client)"
  unzip -p /tmp/mcp-wheel/mcp-1.27.0-py3-none-any.whl mcp-1.27.0.dist-info/METADATA | grep -E "^(Requires-Python|Requires-Dist)"
  ```
- **`mcp==1.27.0` protocol version**: wheel inspection confirmed `LATEST_PROTOCOL_VERSION = "2025-11-25"`, `DEFAULT_NEGOTIATED_VERSION = "2025-03-26"`, and `SUPPORTED_PROTOCOL_VERSIONS = ["2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"]`. Mission's cited revision (`2025-11-25`) matches the SDK's `LATEST_PROTOCOL_VERSION` exactly. F2's strict-equality version check is *narrower* than the SDK's `SUPPORTED_PROTOCOL_VERSIONS` whitelist (intentional per §10)
- **`mcp==1.27.0` current vs deprecated streamable-http API**: `streamable_http_client(url, *, http_client=None, ...)` is the current function (mcp/client/streamable_http.py:601); `streamablehttp_client` is `@deprecated`. F2 uses ONLY the current name; the `http_client` parameter enables in-process ASGI integration testing
- **`mcp==1.27.0` transport exports**: wheel inspection confirmed `mcp.client.stdio` (with `stdio_client` and `StdioServerParameters`) and `mcp.client.streamable_http` (with `streamable_http_client`) both present. `mcp.server.fastmcp` confirmed bundled with `FastMCP`, `streamable_http_app() -> Starlette` for ASGI embedding — no separate `fastmcp` PyPI dependency needed
- **`mcp==1.27.0` direct dependencies**: METADATA inspection confirmed `Requires-Dist: jsonschema>=4.20.0` is a direct dependency, NOT transitive — F2 does NOT need to add jsonschema to `pyproject.toml` separately. Other direct deps: `httpx`, `httpx-sse`, `pydantic`, `pydantic-settings`, `python-multipart`, `sse-starlette`, `starlette`, `uvicorn`, `anyio`. All already in the-one's transitive closure
- **Python compatibility**: `Requires-Python: >=3.10`; wheel is `py3-none-any` (universal). Compatible with the-one's `requires-python = ">=3.11"` (`pyproject.toml:5`)

### Reconciliation: F1 debrief action items addressed in F2 design

| F1 debrief action item | F2 resolution |
|---|---|
| F2 must consume `merged_config()` AND clarify env-var assembly shape | Design Decision §11 — F2 does NOT consume `merged_config()`; uses `build_stdio_environ(source, allowlist)` reading `config.env` and `secrets` separately. F1 debrief recommendation explicitly contradicted with rationale (nested-dict structure) |
| F2 must clarify env-var assembly shape (do NOT blindly consume `merged_config()`) | Design Decision §11 — explicit 2-layer flat merge documented |
| The "leg lands red, next leg lands green" pattern recurs in this flight? | No — F2 has no schema migration leg (no migration in this flight). Pattern doesn't apply |
| Anchor-by-symbol-name convention for leg artifact citations | F2 leg artifacts will follow this convention (anchor by `MCPClient.connect`, `build_stdio_environ`, etc., not by line number) — captured as a leg-design instruction |
| Per-leg lint gate | F2 enforces `make lint` clean per-leg before `[HANDOFF:review-needed]` — captured in leg artifact post-completion checklists |
| `_MASKED_API_KEY_SENTINEL` rename to `_MASKED_SENTINEL` | Out of scope for F2 (deferred to routine maintenance per F1 debrief recommendation; F2 doesn't add a 5th call site) |
| Runtime OAuth token slots NOT pre-landed (F1 debrief Key Learning #6) | F2 doesn't read them — F2's static-bearer support emerges from the operator typing `Authorization: Bearer xxx` as a row of the headers kv table. F5 introduces `secrets["access_token"]`, `["refresh_token"]`, `["token_expires_at"]` slots when implementing the live OAuth flow |
| Mission Open Q "Reference server choice for tests and HAT" | Closed at F2 design — in-repo FastMCP "hello world" fixture, no `mcp-server-everything` dependency. F2 debrief will confirm closure so the mission's Open Question table can mark it resolved |
| Mission Open Q "MCP source identity for the resolver" (resolved in Flight 2 or 4 design) | Deferred to F4 — F2 stops at the runtime client and does not touch the resolver. Mission Open Q stays carried |

---

## Leg Progress

> Populated as legs land.

---

## Decisions

> Runtime decisions not in the original plan. Populated during execution.

---

## Anomalies

> Populated as encountered during execution.

---

## Flight Director Notes

> Populated by the orchestrator (mission-control) during agentic-workflow execution.
