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

### L1: SDK pin and skeleton

**Status**: landed
**Started**: 2026-05-06
**Completed**: 2026-05-06

**Changes made:**
- `pyproject.toml` — added `"mcp==1.27.0"` to `dependencies` (positioned after `"cryptography>=43.0"` per spec).
- `the_one/mcp/__init__.py` (NEW) — public surface: `_PINNED_PROTOCOL_VERSION = "2025-11-25"`, `MCP_DEFAULT_TIMEOUT_SECONDS = 30`, `MCP_DEFAULT_CALL_TIMEOUT_SECONDS = 60`, plus re-exports of `MCPClient`, the 7-class error hierarchy, `MCPTool`, `MCPToolResult`. Constants intentionally precede the re-exports (annotated `# noqa: E402` per F2 contract).
- `the_one/mcp/errors.py` (NEW) — full 6-subclass hierarchy under `MCPClientError`. `MCPVersionMismatch` and `MCPCapabilityMissing` carry `# noqa: N818` because the names are mandated by F2 contract (subclass of `MCPClientError`, not direct `Exception`).
- `the_one/mcp/types.py` (NEW) — `MCPTool` and `MCPToolResult` frozen dataclasses per flight §4 / §5b.
- `the_one/mcp/client.py` (NEW) — placeholder `class MCPClient: """L2 implements lifecycle."""` shell with no SDK imports.
- `the_one/mcp/transports/__init__.py` (NEW) — package marker docstring.
- `the_one/mcp/transports/stdio.py` (NEW) — placeholder docstring citing flight §11; no logic.
- `the_one/mcp/transports/streamable_http.py` (NEW) — placeholder docstring; no logic.
- `the_one/interfaces/web/api.py::_validate_mcp_source_config` — extended stdio branch with `config.env` validation block (mirrors the existing `headers` validation pattern verbatim except for the field name); docstring updated with the matching one-clause append.
- `tests/test_mcp_client.py` (NEW) — `TestModuleSetup` class with 3 tests: `test_pinned_protocol_version_matches_sdk` (SDK-version tripwire), `test_timeout_constants_present`, `test_dataclasses_frozen`.
- `tests/test_db_api.py::TestMCPSourceAPI` — added `test_validation_rejects_stdio_config_env_non_string_value` and `test_validation_rejects_stdio_config_env_non_dict` after `test_validation_rejects_unknown_transport_type`.
- `CLAUDE.md` — added new `## F2 (MCP Client Foundation) Contracts (authoritative for F3-F8)` section with 6 enumerated contracts, inserted directly after the existing "Encryption rotation invariant" paragraph.
- `the_one/agents.md` — added 6 concise F2 bullets (one per CLAUDE.md contract) immediately after the `oauth_client_secret` paragraph in the MCPSourceRepository section.

**Notes:**
- `pip install` happened via container rebuild (`docker compose build the-one`). Pre-existing image had no `mcp` package installed (the recon-noted "1.18.0 pre-existing" was on the host's system Python; PEP 668 blocks host-side editable installs anyway). Inside the freshly built container, `mcp.types.LATEST_PROTOCOL_VERSION == "2025-11-25"`, matching `_PINNED_PROTOCOL_VERSION` exactly.
- Lint required four `# noqa` annotations: two `N818` (mandated exception class names), one `E402` block (constants-first ordering per F2 contract), and the `mcp.types`/`the_one` import ordering in the test file split into two import groups (stdlib `import mcp.types` is first-party-adjacent here; ruff's `I001` accepted it once a blank line separated the groups).
- The long docstring line in `the_one/mcp/__init__.py` (the example python -c command in the upgrade procedure) was wrapped using a backslash continuation inside the docstring text to satisfy E501 without losing the example's clarity.

**Test count:**
- Before: 1099 passing + 1 skipped (288 deselected) — recon baseline.
- After:  1104 passing + 1 skipped (288 deselected). Delta: +5 (3 module-setup + 2 API-validation), as planned.

**Lint:** clean (0 errors, 0 warnings). No new ruff errors introduced.

---

### L2: Client lifecycle and handshake

**Status**: landed
**Started**: 2026-05-06
**Completed**: 2026-05-06

**Changes made:**
- `the_one/mcp/client.py` — replaced L1's placeholder shell with full `MCPClient` lifecycle:
  - **Lazy-SDK-import pattern**: SDK names (`ClientSession`, `ServerCapabilities`) appear only under `if TYPE_CHECKING`. The `from the_one import mcp as the_one_mcp` lookup that reads `_PINNED_PROTOCOL_VERSION` lives inside `connect()` (not at module top) so test monkeypatches propagate. Verified `mcp.client.session` is NOT in `sys.modules` after `import the_one.mcp.client`.
  - **`_transport_connect` dispatch helper at top-level of `client.py`** (not a method): decorated `@asynccontextmanager`, dispatches on `source.type`, raises `NotImplementedError("L4/L5 lands it")` for now. Top-level placement lets tests do `monkeypatch.setattr(client_mod, "_transport_connect", ...)`. The `else` branch raises `MCPClientError` for defensive exhaustiveness even though the `MCPSource.type` Pydantic Literal makes it unreachable.
  - **`_cleanup_after_failed_connect` helper**: best-effort teardown of partial transport state on every failure path inside `connect()` (timeout, version mismatch, capability missing, generic exception). Logs at DEBUG and swallows. Keeps `connect()` linear-readable.
  - **`is_alive` ordering invariant**: `disconnect()` flips `_is_alive = False` BEFORE awaiting the transport `__aexit__` (so a concurrent F4 reaper observing `is_alive` sees the disconnect-in-progress state); `connect()` sets `_is_alive = True` only AFTER all version + capability + state-commit work succeeds. Documented inline.
  - **F2 strict-equality version check** (narrower than SDK's `SUPPORTED_PROTOCOL_VERSIONS`) runs OUTSIDE the `asyncio.timeout` block — important because timeout > version mismatch > capability missing precedence is enforced via try/except ordering.
  - `__aexit__` returns `None` (no explicit re-raise): Python's `async with` auto-propagates exceptions when `__aexit__` returns falsy. Confirmed by `test_aenter_aexit`'s `raise ValueError("boom")` body that propagates correctly.
  - `last_activity` initialized to **exactly `0.0`** (not `None`); `_touch_activity()` writes `time.monotonic()`. List_tools/call_tool stubs call `_touch_activity()` BEFORE raising `NotImplementedError("L6a implements")` so the activity contract is locked in at L2.
  - `__init__` uses a `_DEFAULT = object()` sentinel (not `...` Ellipsis) for `timeout_seconds`/`call_timeout_seconds` defaults so explicit `None`/`0` aren't silently overwritten.
- `tests/test_mcp_client.py` — added `TestMCPClientLifecycle` class with **13 tests** matching the spec's exact list (1: init_state through 13: last_activity_updates_via_list_tools), plus three module-level helpers and two pytest fixtures:
  - `_stdio_source(...)` — builds `MCPSource(id="src-1", name="test", type="stdio", config={"command": "echo", "args": []}, secrets={})`. Critical: `MCPSource` requires `id: str` per Pydantic model; every fixture passes it.
  - `_make_init_result(*, protocol_version, tools_present, capabilities_dump)` — builds a `MagicMock` `InitializeResult` with `protocolVersion`, `capabilities.tools`, and `capabilities.model_dump(mode="json")` configured.
  - `_mock_transport_cm(session)` — `@asynccontextmanager` async-CM that yields the supplied session.
  - `mock_session` fixture — `MagicMock` with `initialize`/`list_tools`/`call_tool` as `AsyncMock`s (default `initialize` returns `_make_init_result()`).
  - `patch_transport(session=None)` fixture — installs `lambda source: _mock_transport_cm(sess)` via `monkeypatch.setattr` on `client_mod._transport_connect`. **Critical**: the lambda creates a fresh CM per call (asynccontextmanager-produced CMs are single-use; without the lambda, a connect→disconnect→connect sequence would re-enter an already-exited CM).

**Notes:**
- **No deviations from spec.** All 13 tests landed exactly as numbered in the leg AC.
- **No new ruff suppressions added.** The `_transport_connect` body has a trailing `yield  # type: ignore[unreachable]  # noqa: F821` that's unreachable at runtime (both branches raise) but required by `@asynccontextmanager` for static-analysis cleanliness — not a F-code suppression, just a type hint. Lint passed without modification of the global `pyproject.toml` ruff config.
- **SDK shape surprise (none)**: `mcp==1.27.0`'s `ClientSession.initialize` raises `RuntimeError("Unsupported protocol version from the server: <version>")` exactly as the leg-design citation 1 documented. The `_UNSUPPORTED_VERSION_RE = re.compile(r"Unsupported protocol version from the server: (.+)")` regex matches verbatim.
- **F2 strict-check vs SDK SUPPORTED_PROTOCOL_VERSIONS**: confirmed at runtime — `SUPPORTED = ['2024-11-05', '2025-03-26', '2025-06-18', '2025-11-25']`. F2's strict check on `_PINNED_PROTOCOL_VERSION = "2025-11-25"` is narrower (rejects the 3 older versions). `test_connect_version_mismatch_strict` uses `2025-06-18` (in SDK whitelist, NOT pinned) to prove the F2 gate fires.
- **`disconnect()` no-op idempotency** has a subtle gate: the early-return uses `if not self._is_alive and self._transport_cm is None` (both conditions). This is correct for the case where `_cleanup_after_failed_connect` already ran (sets `_transport_cm=None`); a fresh-uninitialized client also satisfies both conditions. `test_disconnect_idempotent` exercises both paths.
- **F841 watch**: `disconnect()` does NOT assign `was_alive` (per the leg's review-cycle note); it just early-returns or proceeds with the flag flip. No unused locals introduced.
- **`asyncio.timeout` raises `TimeoutError` (not `asyncio.TimeoutError` since 3.11)**: the codebase targets `>=3.11` so `asyncio.TimeoutError` is an alias for `TimeoutError`. The `except asyncio.TimeoutError` clause works and reads consistent with the rest of the project. The `from None` chain-suppression keeps the operator-facing message clean.

**Test count:**
- Before: 1104 passing + 1 skipped (288 deselected) — L1 baseline.
- After:  1117 passing + 1 skipped (288 deselected). Delta: +13 (all `TestMCPClientLifecycle` tests), exactly as planned.

**Lint:** clean (0 errors, 0 warnings). No new ruff errors introduced.

---

### L3: FastMCP hello fixture

**Status**: landed
**Started**: 2026-05-06
**Completed**: 2026-05-06

**Changes made:**
- `pyproject.toml` — added `"asgi-lifespan>=2.0"` to `[project.optional-dependencies] dev` after `"pixelmatch>=0.3"`. Required to drive Starlette lifespan startup under `httpx.ASGITransport` (which does not auto-fire lifespan events). Installed inside the running container with `pip install 'asgi-lifespan>=2.0'`; resolved cleanly to `asgi-lifespan-2.1.0` against the existing image — no `docker compose build` required because the host filesystem is bind-mounted via `pip install -e ".[dev]"` (the image has the editable install) and the new dep was a pure Python add.
- `tests/fixtures/__init__.py` (NEW; `"""Pytest fixture packages."""`) — empty package marker so `--import-mode=importlib` resolves `tests.fixtures` cleanly across pytest versions.
- `tests/fixtures/mcp/__init__.py` (NEW; `"""MCP test-fixture servers."""`) — same rationale.
- `tests/fixtures/mcp/hello_server.py` (NEW; **89 LOC**, under the relaxed <100 budget) — runnable FastMCP server. Three non-obvious shapes are baked in:
  1. **Factory pattern**: `make_mcp_app() -> FastMCP` constructs a fresh instance with `transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False)` and registers `echo(message: str) -> str` and `add(a: int, b: int) -> int` via the `@app.tool()` (parens-form required) decorator. Module-level `mcp_app: FastMCP = make_mcp_app()` exists ONLY for the stdio subprocess path — the HTTP fixture must call the factory per-test because `StreamableHTTPSessionManager.run()` enforces once-per-instance.
  2. **DNS-rebinding protection disabled at construction**: FastMCP's default `host="127.0.0.1"` auto-enables protection that would 421 the in-process ASGI fixture's `Host: localhost` header. We disable it at the `FastMCP` level for defense-in-depth (the fixture also sends a Host header that matches the default allowlist `["localhost:*", ...]`).
  3. **`__main__` dispatch**: `--stdio` (default) calls `mcp_app.run("stdio")`; `--http` prints a usage hint pointing at the in-process pytest fixture; unknown modes exit 2.
- `tests/conftest.py` — extended with TWO new fixtures plus supporting imports (`os`, `sys`, `Path`) and a `_PROJECT_ROOT` constant:
  - `mcp_fixture_stdio_params` (function-scoped) — returns a `dict[str, Any]` shaped like `StdioServerParameters` kwargs: `{"command": sys.executable, "args": ["-m", "tests.fixtures.mcp.hello_server", "--stdio"], "env": {"PATH": ..., "PYTHONPATH": <project root>}, "cwd": None}`. The `PYTHONPATH` line is critical so the spawned subprocess can resolve `tests.fixtures.mcp.hello_server` via `python -m`.
  - `mcp_fixture_http_client` (async function-scoped) — calls `make_mcp_app()` per-test, drives Starlette lifespan via `asgi_lifespan.LifespanManager(app)`, yields `(client: httpx.AsyncClient with ASGITransport, url: "http://localhost/mcp")`, and tears down the lifespan + client on exit. `import httpx`, `from asgi_lifespan import LifespanManager`, and `from tests.fixtures.mcp.hello_server import make_mcp_app` are kept inside the fixture body to keep import-time cost zero for tests that don't touch MCP.
- `tests/test_mcp_integration.py` (NEW; **56 LOC**) — `TestL3IntegrationSmoke` class with 2 tests, both using the bare SDK (no `MCPClient`):
  - `test_stdio_smoke_via_raw_sdk`: builds `StdioServerParameters(**fixture_dict)`, opens `stdio_client` + `ClientSession`, calls `initialize()` (asserts `protocolVersion == "2025-11-25"`, `capabilities.tools is not None`), `list_tools()` (asserts `{"echo", "add"}`), `call_tool("echo", {"message": "hi"})` (asserts `isError is False`, `content[0].text == "hi"`).
  - `test_streamable_http_smoke_via_raw_sdk`: unpacks `(client, url)` from the fixture, opens `streamable_http_client(url, http_client=client)` + `ClientSession`, same assertion set.

**Notes:**
- **No deviations from spec.** Both tests passed on first run; no flakiness observed across multiple invocations.
- **`asgi-lifespan` install path**: pure pip install inside the running container worked (no `docker compose build` needed). The image already had `pip install -e ".[dev]"` baked in pointing at the host-mounted source tree, so the freshly-listed dep in `pyproject.toml` was satisfied by an in-container `pip install 'asgi-lifespan>=2.0'`. If a future container rebuild happens, the `pyproject.toml` entry will pick it up automatically.
- **Test runtime**: combined runtime for the two L3 smoke tests was **0.67s** (well under the <5s budget). The streamable-http in-process ASGI test ran in ~0.05s; the stdio subprocess test ran in ~0.6s (Python cold-start + FastMCP init dominated). No CI variance concern at this point.
- **ASGI shape (no surprises)**: `make_mcp_app().streamable_http_app()` returns a `Starlette` instance as documented; `LifespanManager` properly fires startup events; `httpx.ASGITransport(app=app)` routes by scope without DNS lookup; the `Host: localhost` synthetic header passes both the FastMCP allowlist (default) and the explicitly-disabled DNS-rebinding middleware.
- **SDK version assertion**: `init_result.protocolVersion == "2025-11-25"` matches the F2 pinned version (`_PINNED_PROTOCOL_VERSION`) — the assertion is a tripwire for SDK protocol drift in either transport. Both transports negotiated the same version, confirming our pin is the SDK's `LATEST_PROTOCOL_VERSION` for both stdio and streamable-http.
- **L4/L5 readiness**: the two `mcp_fixture_*` fixtures are stable and reusable. L4 will pass `mcp_fixture_http_client`'s tuple into `streamable_http_client(url, http_client=client)` to drive `MCPClient` round-trips; L5 will build `StdioServerParameters(**mcp_fixture_stdio_params)` for the `MCPClient` stdio path. Both call sites are in the smoke tests above as a working reference.

**Test count:**
- Before: 1117 passing + 1 skipped (288 deselected) — L2 baseline.
- After:  1119 passing + 1 skipped (288 deselected). Delta: +2 (`TestL3IntegrationSmoke::test_stdio_smoke_via_raw_sdk`, `TestL3IntegrationSmoke::test_streamable_http_smoke_via_raw_sdk`), exactly as planned.

**Lint:** clean (0 errors, 0 warnings) via `make lint` (in-container `ruff check the_one/ tests/`). No new ruff errors introduced.

---

### L4: Streamable-HTTP transport

**Status**: landed
**Started**: 2026-05-06
**Completed**: 2026-05-06

**Changes made:**
- `the_one/mcp/transports/streamable_http.py` — replaced the L1 placeholder docstring with the full implementation:
  - `__all__ = ["build_request_headers", "connect_streamable_http"]` declared at module top so the `_test_http_client_override` seam is excluded from `from … import *` (defense-in-depth on top of the underscore prefix; documented in module docstring).
  - `_test_http_client_override: httpx.AsyncClient | None = None` — module-level TEST-ONLY seam, only ever read inside `connect_streamable_http` and only when caller-supplied `http_client is None`. Documented "TEST-ONLY" tag in the surrounding comment so future maintainers don't promote it.
  - `build_request_headers(source: MCPSource) -> dict[str, str]` — pure function returning `{**source.config.get("headers", {}) or {}, **source.secrets}`. Defensive `or {}` against a future schema drift that allows `headers: None`. Trusts F1's API validator for the shape — does not re-validate.
  - `connect_streamable_http(source, *, http_client=None)` — `@asynccontextmanager` yielding an entered `ClientSession`. Reads the seam ONLY when `http_client is None`. **Production path** (`effective_client is None`): builds its OWN `httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=httpx.Timeout(30.0))` so headers are applied at construction (the SDK's `streamable_http_client` does NOT accept a `headers=` kwarg — confirmed by design-review's in-container probe; Case B in the leg's "Implementation Guidance" is the only path). **Test path** (`effective_client is not None`): mutates `effective_client.headers.update(headers)` before yielding to the SDK; safe because L3's `mcp_fixture_http_client` is per-test fresh, so cross-test pollution is prevented by fixture lifetime.
- `the_one/mcp/client.py::_transport_connect` — streamable-http branch replaced the L2 `NotImplementedError` with a local `from the_one.mcp.transports.streamable_http import connect_streamable_http` + `async with connect_streamable_http(source) as session: yield session`. No `return` after `yield` — `if/elif/else` already handles dispatch isolation. The stdio branch's `NotImplementedError` is unchanged (L5 lands it).
- `tests/test_mcp_client.py` — added top-level import `from the_one.mcp.transports.streamable_http import build_request_headers` (alphabetized with the existing `the_one.mcp.errors` import). Appended:
  - `_http_source(...)` test helper (small `MCPSource` factory for the streamable-http shape).
  - `TestBuildRequestHeaders` (4 unit tests: `test_empty`, `test_sensitive_only`, `test_plaintext_only`, `test_mixed_secrets_win`) — pure-Python, no SDK / network / fixture involvement.
  - `TestConnectStreamableHttpProduction::test_production_path_constructs_client_with_assembled_headers` (1 unit test, **Option C** pattern) — monkeypatches `streamable_http_client`, `ClientSession`, AND `_test_http_client_override = None` to force the production path; asserts `captured["http_client"].headers["authorization"] == "Bearer test-token"` (httpx normalizes header keys to lowercase). Closes the gap that the integration test #2 cannot assert (the test-seam path uses a `dict.update()` mutation, not a constructor).
- `tests/test_mcp_integration.py` — added imports at the top of the file (alphabetized with the existing `from mcp…` block): `import pytest`, `from the_one.db.models import MCPSource`, `from the_one.mcp.client import MCPClient`, `from the_one.mcp.errors import MCPConnectionError`. Appended `TestL4StreamableHttp` with 3 integration tests:
  1. `test_connect_via_mcpclient_against_asgi_fixture` — full MCPClient connect against the L3 ASGI fixture; asserts `is_alive`, `negotiated_protocol_version == "2025-11-25"`, AND the tighter capability shape `isinstance(caps["tools"], dict) and "listChanged" in caps["tools"]` (defends against future SDK regressions); cleanly disconnects.
  2. `test_connect_with_secrets_does_not_break_connection` — same setup with `secrets={"Authorization": "Bearer test-token"}`; explicit comment notes that header-injection verification is in `TestConnectStreamableHttpProduction` (Option C unit test). Proves the test-seam path's `effective_client.headers.update(headers)` mutation doesn't break the in-process ASGI transport.
  3. `test_connect_already_connected_via_real_transport` — same as L2's mocked `already-connected` test but against the real ASGI transport; confirms the L2 contract holds end-to-end.

**Notes:**
- **SDK shape confirmed at design review's in-container probe.** `streamable_http_client(url, *, http_client=None, terminate_on_close=True)` does NOT accept a `headers=` kwarg — Case B in the leg's "Implementation Guidance" §1 is the only path. The production-path defaults `follow_redirects=True, timeout=httpx.Timeout(30.0)` mirror `mcp.shared._httpx_utils.create_mcp_http_client` without depending on the private `_httpx_utils` module.
- **No deviations from spec.** All 8 new tests passed on first run; no flakiness across two full-suite runs.
- The `_test_http_client_override` seam is auto-reverted by `monkeypatch.setattr` on test teardown, so cross-test pollution is impossible. The Option C unit test additionally `monkeypatch.setattr(sh, "_test_http_client_override", None)` defensively to document intent — production-path execution is asserted by the captured `http_client.headers` lookup, not by the absence of the seam.
- **F4 warm-pool compatibility**: the helper is stateless (only reads its arguments + the test seam). Per-MCPClient lifecycle is owned by `MCPClient._transport_cm`. F4-pool-safe; no state changes needed when F4 lands.

**Test count:**
- Before: 1119 passing + 1 skipped — L3 baseline.
- After:  **1127 passing + 1 skipped**. Delta: +8 — exactly as planned (4 `TestBuildRequestHeaders` + 1 `TestConnectStreamableHttpProduction` + 3 `TestL4StreamableHttp`).

**Lint:** clean (0 errors) via `make lint` (in-container `ruff check the_one/ tests/`). No new ruff errors introduced.

---

### L5: Stdio transport

**Status**: landed
**Started**: 2026-05-06
**Completed**: 2026-05-06

**Changes made:**
- `the_one/mcp/transports/stdio.py` — replaced the L1 placeholder docstring with the full implementation:
  - `__all__ = ["build_stdio_environ", "connect_stdio"]` declared at module top (mirrors L4's symmetry).
  - SDK imports at module top (NOT lazy): `from mcp import ClientSession` and `from mcp.client.stdio import StdioServerParameters, stdio_client`. Helper imports also at module top: `from the_one.db.models import MCPSource` and `from the_one.platform.env import _build_subprocess_env`. Reuses the canonical `_ENV_ALLOWLIST` + `_build_subprocess_env()` from `the_one/platform/env.py` per the L4 architect-review fix; **no re-declaration**. Module docstring notes `_build_subprocess_env` is "private by underscore convention" but is the canonical helper — promoted-by-use-not-by-rename.
  - `build_stdio_environ(source, allowlist_env)` — pure 2-layer flat-merge: `{**allowlist_env, **source.config.get("env", {}) or {}, **source.secrets}`. Defensive `or {}` against future schema drift letting `env: None` slip through. Trusts F1's API validator for shape; does not re-validate. Module docstring explicitly forbids switching to `merged_config()` (would inject command/args/cwd-shaped keys).
  - `connect_stdio(source)` — `@asynccontextmanager` yielding an entered `ClientSession`. Reads `command` (required), `args` (default `[]` defensively even though SDK has `default_factory=list`), `cwd` (default `None`); calls `_build_subprocess_env()` itself and passes the result into `build_stdio_environ`. Nests `async with stdio_client(params) as (read, write):` then `async with ClientSession(read, write) as session: yield session`. SDK's `errlog=sys.stderr` default is preserved.
- `the_one/mcp/client.py::_transport_connect` — stdio branch replaced the L2 `NotImplementedError` with a local `from the_one.mcp.transports.stdio import connect_stdio` + `async with connect_stdio(source) as session: yield session`. Streamable-http branch unchanged (L4); else-branch and the trailing `yield  # type: ignore[unreachable]` (asynccontextmanager protocol) both unchanged.
- `tests/test_mcp_client.py` — added top-level import `from the_one.mcp.transports.stdio import build_stdio_environ` (alphabetized with the L4 streamable-http import). Appended:
  - `_stdio_source_for_env_test(*, env=None, secrets=None)` — test helper that omits `config["env"]` entirely when `env=None` so the helper's `.get("env", {}) or {}` defensive default is exercised.
  - `TestBuildStdioEnviron` — **6 unit tests** covering the full precedence matrix per leg AC: `test_allowlist_only`, `test_config_env_only`, `test_secrets_only`, `test_mixed_no_collision`, `test_secrets_win_over_config_env`, `test_secrets_win_over_allowlist` (the secrets-trump-allowlist test locks in the documented operator-can-override-anything behavior).
- `tests/test_mcp_integration.py` — appended `TestL5Stdio` with **3 integration tests**, each wrapped in `@pytest.mark.timeout(15)` so a hung subprocess fails fast:
  1. `test_connect_via_mcpclient_against_stdio_fixture` — full MCPClient connect against the L3 stdio subprocess fixture; asserts `is_alive`, `negotiated_protocol_version == "2025-11-25"`, and the tighter `caps["tools"]` shape (`isinstance(...) and "listChanged" in ...`).
  2. `test_connect_with_extra_env_passes_through` — extends fixture's `config.env` with `MY_PLAIN: hello` AND adds `secrets={"MY_SECRET": "shh"}`; asserts `is_alive` (round-trip proves the merged env materializes without breaking subprocess spawn).
  3. `test_connect_already_connected_via_stdio_transport` — second `connect()` raises `MCPConnectionError("…already connected.")`; mirrors L4's `test_connect_already_connected_via_real_transport` naming pattern (no "raises" suffix).
- `pyproject.toml` — added `"pytest-timeout>=2.4"` to `[project.optional-dependencies] dev` (between `pytest-asyncio` and `ruff`). The leg-design notes claimed pytest-timeout 2.4.0 was already installed in the container, but `pip show pytest-timeout` returned not-found. Adding the dep and `pip install pytest-timeout==2.4.0` inside the running container registered the `timeout` marker (no more `PytestUnknownMarkWarning`).

**Notes:**
- **Container had no pytest-timeout** despite the leg's design assumption. Resolved by adding `pytest-timeout>=2.4` to `[dev]` and running `pip install pytest-timeout==2.4.0` against the running container — same pattern L3 used for `asgi-lifespan`. Tests pass either way (the unknown-mark warning is non-fatal), but registering the plugin makes `@pytest.mark.timeout(15)` actually enforce the 15s deadline.
- **SDK env-merge floor confirmed at runtime.** The SDK's `get_default_environment()` is applied UNDER our env inside `stdio_client`, providing defense-in-depth defaults for HOME/LANG/etc. We never see this floor (it's inside the SDK's spawn path); our `build_stdio_environ` produces the operator-side ceiling. Documented in module docstring.
- **Secrets-wins-over-allowlist documented.** Test #6 (`test_secrets_win_over_allowlist`) locks the contract: an operator-marked-sensitive `PATH` value beats the host-inherited allowlist `PATH`. The kv table is the operator's authority surface; secrets is the encryption-at-rest sub-layer of that surface. Module docstring spells this out.
- **Subprocess startup runtimes** for the 3 integration tests: combined wall-clock **1.38s** (per `pytest -k TestL5Stdio` isolated run). Average ~0.46s per test — under the L3-measured ~0.5–0.8s upper band. No CI variance concern at this point. Full suite delta is ~1.5s additive (1099→1136 baseline shifted ~60s flat; the +9 tests don't perceptibly change the suite duration).
- **`args` default-factory caught no edge cases.** All three integration tests pass an explicit `params_dict["args"]` from the L3 fixture (always non-empty: `["-m", "tests.fixtures.mcp.hello_server", "--stdio"]`). The defensive `.get("args", [])` in `connect_stdio` was not exercised by integration tests but is covered by code review intent — F1 validator drift would surface it.
- **No deviations from spec.** All 9 new tests passed on first full-suite run; no flakiness observed.
- **F4 warm-pool compatibility**: `connect_stdio` is stateless (only reads its arguments + module-global SDK + the platform-layer helper). Per-MCPClient lifecycle is owned by `MCPClient._transport_cm`. F4-pool-safe.

**Test count:**
- Before: 1127 passing + 1 skipped — L4 baseline.
- After:  **1136 passing + 1 skipped**. Delta: +9 — exactly as planned (6 `TestBuildStdioEnviron` unit + 3 `TestL5Stdio` integration).

**Lint:** clean (0 errors) via `make lint` (in-container `ruff check the_one/ tests/`). No new ruff errors introduced.

---

### L6a: list_tools and call_tool happy path

**Status**: landed
**Started**: 2026-05-06
**Completed**: 2026-05-06

**Changes made:**
- `the_one/mcp/client.py` — replaced L2's `NotImplementedError` stubs for `list_tools` and `call_tool` with full implementations:
  - `list_tools()` — refetches from server every call (no client-side cache invalidation), wraps `self._session.list_tools()` in `asyncio.timeout(self.timeout_seconds)` (30s handshake/list-tools budget), maps each `Tool` to a frozen `MCPTool` (defaults `description` to `""` and `input_schema` to `{}` if SDK returns None; `annotations` projected via `tool.annotations.model_dump(mode="json")` when present, else `None`). Caches the resulting list on `self._tools_cache` for `call_tool`'s unknown-tool guard.
  - `call_tool(name, arguments)` — guards on `self._is_alive`/`self._session is None` (raises `MCPConnectionError`); lazy-populates `self._tools_cache` via `list_tools()` if `None` (runs OUTSIDE the call_timeout_seconds budget); raises `MCPToolNotFoundError` BEFORE wire call when name not in cache; wraps `self._session.call_tool(name, arguments)` in `asyncio.timeout(self.call_timeout_seconds)` (60s tool-call budget); flattens text-type content blocks into `joined_text` (non-text blocks land in L6b — they currently dump-only into `raw` without joining); passes through `structuredContent` and `isError`; raises `MCPCallError(tool_name=name, server_message=joined_text)` when `is_error` is true; otherwise returns `MCPToolResult(text, raw, structured, is_error=False)`.
  - Added `self._tools_cache: list[MCPTool] | None = None` attribute in `__init__` (lazily populated; cleared by `disconnect()` so re-connect rebuilds fresh per session).
- `tests/test_mcp_client.py` — appended `TestListToolsAndCallTool` (11 unit tests) covering: list_tools-not-connected raises, list_tools maps 2 tools and populates cache, list_tools handles `None` description / `None` inputSchema / `None` annotations defensively, call_tool-not-connected raises, call_tool-unknown raises `MCPToolNotFoundError` BEFORE wire call, call_tool happy text-only path with structuredContent, call_tool isError raises `MCPCallError` with server message in payload, call_tool lazy-populates cache when call_tool fires before list_tools, call_tool refreshes cache via `list_tools()` (re-fetch contract). Helpers `_make_tool`, `_make_call_tool_result`, `_make_text_content`, `_make_list_tools_result` mirror SDK shape with the minimum fields needed.
- `tests/test_mcp_client.py::test_last_activity_updates_via_list_tools` — REWORKED in place to drop the `pytest.raises(NotImplementedError)` wrapper from L2 (now that L6a's `list_tools` is real). Asserts `t1 > t0` after a real `await client.list_tools()` call; the mocked `ClientSession.list_tools` returns an empty `ListToolsResult` to keep the test `_touch_activity()`-focused.
- `tests/test_mcp_integration.py` — appended `TestL6aHappyPath` with **4 integration tests** (mirrors L4/L5 transport-test naming pattern):
  1. `test_list_tools_streamable_http` (`src-4`) — connects via streamable-http ASGI fixture; asserts `len(tools) == 2`, `{echo, add}` set match, each `MCPTool.input_schema` is a non-empty dict.
  2. `test_call_tool_echo_streamable_http` (`src-4`) — calls `echo({"message": "hello"})` against ASGI fixture; asserts `result.is_error is False`, `result.text == "hello"`, `len(result.raw) == 1` (one text content block dumped).
  3. `test_list_tools_stdio` (`src-stdio-4`, `@pytest.mark.timeout(15)`) — same shape assertions as #1 but over real subprocess transport.
  4. `test_call_tool_add_stdio` (`src-stdio-5`, `@pytest.mark.timeout(15)`) — calls `add({"a": 2, "b": 3})`; asserts `result.is_error is False`, `result.structured == {"result": 5}`, `result.text == "5"` (no trailing newline — confirmed by in-container probe; see Notes).

**Notes:**
- **`add` tool's `.text` shape confirmed `"5"`** (no trailing newline) via in-container probe before writing the assertion. FastMCP's `@mcp.tool` returns the int `5`; SDK projects to `structuredContent={"result": 5}` and a single text content block with `.text == "5"` (`str(5)`, no decoration). The L4 design-time projection was correct; the L6a implementation comment in `the_one/mcp/types.py` already documents this `text` flatten contract.
- **No deviations from spec.** All 11 unit tests + 4 integration tests passed on first run after the predecessor agent's partial state was completed; no flakiness across two full-suite runs.
- **Integration test runtimes**: `pytest -k TestL6aHappyPath -v` reports the 4 new tests in **1.82s** wall-clock combined (2 ASGI ~instant + 2 stdio subprocess each ~0.5–0.8s — within the L3-measured stdio cold-start band). Full suite went from ~58s (L5) to **59.26s** — the +4 tests are essentially free against the existing 1147 baseline.
- **Lazy-cache contract is single-population, not per-call.** `call_tool` only triggers `list_tools()` when `self._tools_cache is None`; subsequent calls reuse the cached set. `list_tools()` itself always re-fetches and overwrites. Disconnect clears the cache so the next session starts fresh — no cross-session leakage.
- **`_touch_activity()` placement.** Both `list_tools` and `call_tool` call `_touch_activity()` BEFORE the wire call (not after). This is consistent with L2's intent: any successful entry into the method body — regardless of whether the wire call eventually times out or errors — counts as activity for F4's idle-reaper purposes. Documented in the L2 reworked test (`test_last_activity_updates_via_list_tools`).
- **F4 warm-pool compatibility**: `list_tools` and `call_tool` are stateful only on `self._tools_cache` (cleared by `disconnect()`). No cross-MCPClient state. F4-pool-safe.

**Test count:**
- Before: 1136 passing + 1 skipped — L5 baseline.
- After:  **1151 passing + 1 skipped**. Delta: +15 — exactly as planned (11 `TestListToolsAndCallTool` unit + 4 `TestL6aHappyPath` integration; the L2-reworked `test_last_activity_updates_via_list_tools` is in-place rework, not net-new).

**Lint:** clean (0 errors) via in-container `ruff check the_one/ tests/`. No new ruff errors introduced.

---

### L6b: input validation, content rendering, error paths

**Status**: landed
**Started**: 2026-05-06
**Completed**: 2026-05-06

**Changes made:**
- `the_one/mcp/client.py` — extended L6a's `list_tools` and `call_tool` bodies and added third-party imports (`anyio`, `httpx`, `from jsonschema import ValidationError` / `validate as jsonschema_validate`, `from mcp.shared.exceptions import McpError, UrlElicitationRequiredError`) plus `MCPArgumentError` from the_one.mcp.errors. Imports placed in a third-party block AFTER stdlib (re/time/asyncio/contextlib/typing) and BEFORE the_one imports — ruff isort enforces this grouping. `from jsonschema import` split into two lines (ruff isort splits the combined form).
- `call_tool` — three new responsibilities layered on top of L6a's body:
  1. **Input validation step** (after the unknown-tool guard, BEFORE the `asyncio.timeout(...)` block): looks up `tool_meta = next(t for t in self._tools_cache if t.name == name)`; if `tool_meta.input_schema` is truthy (non-empty dict), wraps `jsonschema_validate(arguments, tool_meta.input_schema)` in `try/except ValidationError`, raising `MCPArgumentError(tool_name=name, validation_message=str(e)) from None` on mismatch. Tools with empty schema skip validation (matches SDK permissiveness per flight §5). Validation runs OUTSIDE the timeout window — jsonschema is fast pure-Python (~µs for trivial schemas), no point timing it.
  2. **SDK error translation** wrapped around `async with asyncio.timeout(self.call_timeout_seconds)`: `asyncio.TimeoutError` → `MCPConnectionError("MCP tool call exceeded N seconds")`; `UrlElicitationRequiredError` → `raise` (passes through); `McpError` → `MCPCallError(tool_name=name, server_message=str(e))`; `(httpx.HTTPError, anyio.ClosedResourceError)` → `MCPConnectionError("MCP transport error during call_tool: <type>: <e>")`. All wrapper raises use `from None` for clean small-model-friendly tracebacks (mission constraint #61).
  3. **Non-text content rendering** in the existing `for block in result.content` loop: `image` → `f"[image: {len(block.data)} bytes, mime={block.mimeType}]"`; `audio` → same shape; `resource_link` → `f"[resource_link: {block.uri}]"`; `resource` → `f"[resource: {block.resource.uri}]"` (EmbeddedResource's `.resource` carries the inner uri). Unknown block types silently dropped (forward-compat with future SDK content-block types). The `raw_blocks` accumulator unchanged — every block still dumps via `model_dump(mode="json")`.
- `list_tools` — parallel SDK error translation around the existing timeout block: `asyncio.TimeoutError` → `MCPConnectionError("MCP list_tools exceeded N seconds")`; `UrlElicitationRequiredError` → `raise`; `McpError` → `MCPConnectionError(f"MCP list_tools failed: {e}")` (NOT `MCPCallError` — list_tools isn't a tool *call*); `(httpx.HTTPError, anyio.ClosedResourceError)` → `MCPConnectionError("MCP transport error during list_tools: <type>: <e>")`.
- **Critical subclass-ordering invariant**: `UrlElicitationRequiredError` IS a subclass of `McpError` (verified in-container at L6b implementation: `issubclass(UrlElicitationRequiredError, McpError) == True`). The explicit `except UrlElicitationRequiredError: raise` clause MUST be ordered BEFORE `except McpError` in BOTH `list_tools` and `call_tool` — without it, F3+'s URL elicitation prompts would be silently swallowed into `MCPCallError` / `MCPConnectionError`. Test #6 in `TestCallToolErrorTranslation` (`test_url_elicitation_propagates_through_call_tool_wrapper`) is the mechanical guard against accidental regression.
- `call_tool` docstring updated to enumerate the new raise contracts (MCPArgumentError, transport-error MCPConnectionError, UrlElicitationRequiredError pass-through).
- `tests/test_mcp_client.py` — added 4 mock-content helpers near the existing L6a helpers: `_make_image_content`, `_make_audio_content`, `_make_resource_link_content`, `_make_embedded_resource_content` (each MagicMock with `.type`, the relevant fields, and a `model_dump` returning the JSON-serialized shape). Added 3 new test classes:
  - `TestCallToolInputValidation` (×5): `test_valid_args_pass_validation`, `test_type_mismatch_raises_argument_error`, `test_missing_required_field_raises_argument_error`, `test_extra_unknown_field_passes_validation` (jsonschema's default — additional properties ARE allowed unless `additionalProperties: false`), `test_no_schema_skips_validation`. Tests assert `mock.assert_not_called()` on the wire-call spy when validation fails.
  - `TestCallToolContentBlockRendering` (×5): `test_image_block_placeholder`, `test_audio_block_placeholder`, `test_resource_link_block_placeholder`, `test_embedded_resource_block_placeholder`, `test_mixed_text_and_image_concatenation` — last test asserts `result.text == "first [image: 3 bytes, mime=image/png] last"` for the order-preservation contract (`[text("first "), image, text(" last")]`).
  - `TestCallToolErrorTranslation` (×6): `test_call_tool_timeout_raises_connection_error`, `test_list_tools_timeout_raises_connection_error`, `test_call_tool_mcp_error_raises_mcp_call_error` (uses `McpError(ErrorData(code=-32600, message="boom"))`; asserts `server_message == "boom"`), `test_call_tool_httpx_error_raises_connection_error`, `test_call_tool_closed_resource_raises_connection_error`, `test_url_elicitation_propagates_through_call_tool_wrapper` — last test uses `UrlElicitationRequiredError([])` (empty `list[ElicitRequestURLParams]`) and asserts `pytest.raises(UrlElicitationRequiredError)` (NOT `MCPCallError`!).
  - Test imports extended: `import anyio`, `import httpx`, `from mcp.shared.exceptions import McpError, UrlElicitationRequiredError`, `from mcp.types import ErrorData`, `from the_one.mcp.errors import MCPArgumentError`.
- `tests/test_mcp_integration.py` — extended `from the_one.mcp.errors import MCPConnectionError` to also import `MCPArgumentError`. Added `TestL6bInputValidationIntegration` class with 2 tests:
  1. `test_call_tool_invalid_args_via_streamable_http` (`src-6`) — `call_tool("echo", {})` (missing required `message`) raises `MCPArgumentError` against the FastMCP fixture via streamable-http.
  2. `test_call_tool_invalid_args_via_stdio` (`src-stdio-6`, `@pytest.mark.timeout(15)`) — same shape via the real stdio subprocess transport.

**Notes:**
- **`UrlElicitationRequiredError` constructor signature**: probed in-container — `UrlElicitationRequiredError(elicitations: list[ElicitRequestURLParams], message: str | None = None)`. The leg's working note about "`url: str`" (per the name) was off; the actual signature takes a list of `ElicitRequestURLParams`. Empty list `UrlElicitationRequiredError([])` constructs cleanly and yields `repr(e) == UrlElicitationRequiredError('URL elicitation required')` — sufficient for the side_effect test, which only cares that the exception propagates type-unchanged.
- **`McpError(ErrorData(code=-32600, message="boom"))`** constructed cleanly per the design-review prediction; `str(e) == "boom"` (the SDK's `__str__` flattens to the inner ErrorData's `message`). No mock spec wrapper needed.
- **`anyio.ClosedResourceError()`** zero-arg construction works fine.
- **Integration test runtimes**: `pytest -k TestL6bInputValidationIntegration --durations=0` reports 0.40s for the stdio subprocess test (within the L3-measured 0.5–0.8s cold-start band) and ~0.01s for the streamable-http ASGI test (in-process, essentially instant). Combined wall-clock 1.49s including pytest startup. Full suite went from 1151 (61.84s) to 1169 (62.39s) — the +18 tests are essentially free.
- **No deviations from spec.** Helpers added exactly as guidance step 5; class/test names and counts match leg AC. The `next(t for t in self._tools_cache if t.name == name)` lookup uses the cache directly (defensive `or []` was acceptable per leg note but unnecessary — the unknown-tool guard already guarantees `name` is in the cache).
- **Forward-compat**: unknown content-block types fall through silently (no `else: raise`), so a future SDK adding e.g. `video` content blocks won't break L6b. The `raw_blocks` accumulator still captures the full dump regardless.

**Test count:**
- Before: 1151 passing + 1 skipped — L6a baseline.
- After:  **1169 passing + 1 skipped**. Delta: +18 — exactly as planned (5 input-val + 5 content-rendering incl. mixed-order + 6 error-translation incl. URL elicitation propagation + 2 integration).

**Lint:** clean (0 errors) via in-container `ruff check the_one/ tests/`. No new ruff errors introduced.

---

## Decisions

> Runtime decisions not in the original plan. Populated during execution.

---

## Anomalies

> Populated as encountered during execution.

---

## Flight Director Notes

> Populated by the orchestrator (mission-control) during agentic-workflow execution.
