# Flight: MCP Client Foundation — stdio + Streamable HTTP

**Status**: landed
**Mission**: [MCP Integration](../../mission.md)

## Contributing to Criteria

- [ ] Both transports defined in the current MCP specification are supported by the runtime — process-spawned stdio servers and remote streaming-HTTP servers — with capability negotiation handled per the spec's lifecycle requirements (initialize handshake, version negotiation, post-init protocol-version header for HTTP) *(F2 lands the client-side wrapper; runtime composition into agents is F6)*
- [ ] Each layer of the integration has automated coverage proving its contract — the encrypted persistence layer, the client-side connection lifecycle for both transports, the sandbox spawn path, the idle-TTL reaper, the resolver's substitution behavior on MCP-shaped overrides, the tool-name-spacing logic, and the inspector's tool-list / tool-call round-trip *(F2 contributes the client-side connection lifecycle for both transports)*
- [ ] An MCP-protocol version is pinned in code with an explicit upgrade path documented; the integration capability-gates spec features so that running against a server announcing an older or differently-capabled handshake degrades cleanly rather than crashing *(F2 lands the SDK pin and the `_PINNED_PROTOCOL_VERSION` constant; F2's pre-release stance is **fail-hard at handshake**, narrower than the SDK's `SUPPORTED_PROTOCOL_VERSIONS` whitelist — see Design Decisions §10 for rationale and the post-1.0 evolution path)*

---

## Pre-Flight

### Objective

Land a thin async `MCPClient` wrapper around the official Python `mcp==1.27.0` SDK that surfaces a small, opinionated surface area for the rest of the mission to consume: connect, list-tools, call-tool, disconnect — for both transports defined in the current MCP specification (stdio and streamable-http). The MCP spec revision targeted by the pinned SDK (`2025-11-25`) is captured in a `_PINNED_PROTOCOL_VERSION` module constant; mismatches at the `initialize` handshake fail hard with `MCPVersionMismatch` (pre-release stance, narrower than the SDK's own `SUPPORTED_PROTOCOL_VERSIONS` whitelist — see §10). Stdio servers spawn as ordinary subprocesses with an `env=` argument materialized from a 2-layer flat-merge of (1) the existing canonical 8-key host allowlist (imported from `the_one/platform/env.py`) and (2) the operator-configured kv table (sensitive-flagged values decrypted from `secrets`, non-sensitive read directly from `config.env`). No sandbox in this flight — F3 lands the `MCPSandbox` adapter contract and bubblewrap backend. Streamable-http servers connect with operator-configured headers from the same kv-table shape (sensitive headers decrypted from `secrets`, non-sensitive from `config.headers`), with optional static bearer support emergent from the kv table itself (operator types `Authorization | Bearer xxx | sensitive=true` as one row). No live OAuth flow in this flight — F5 lands the full RFC 8707 / PKCE flow on top of the streamable-http transport. An in-repo FastMCP "hello world" fixture (`tests/fixtures/mcp/hello_server.py`) is authored to back integration tests for both transports without depending on external npm packages; the streamable-http fixture wires in-process via the SDK's `streamable_http_client(http_client=httpx.AsyncClient(transport=ASGITransport(app=fastmcp.streamable_http_app())))` pattern (no real socket).

The flight is **runtime-foundation only**: no UI changes, no agent integration, no warm-pool, no sandbox, no OAuth. The `MCPClient` is designed compatible with F4's per-source warm-pool (idempotent `disconnect()`, no thread-locals or module-globals, `is_alive` and `last_activity` properties exposed — naming aligned with `PtySession`'s contract) and with F6's `ToolProvider` integration (returned `MCPToolResult` carries both a flat `.text` for agent consumption and the raw content blocks for F7's inspector) but does not itself wire either.

### Open Questions

All resolved during F2 design — see Design Decisions for rationale on each.

- [x] **Module placement**: `the_one/mcp/` (peer of `the_one/llm/`) — see §1
- [x] **MCPClient API surface shape**: async context manager wrapping explicit `connect()`/`disconnect()` lifecycle methods — see §2
- [x] **Error hierarchy** + capability-missing handling: single `MCPClientError(Exception)` base; fail-hard if server doesn't announce `tools` capability; other missing capabilities are non-fatal — see §3
- [x] **Tool-call result rendering**: hybrid `MCPToolResult(text, raw, structured, is_error)` dataclass — see §4
- [x] **Tool input validation**: validate at MCPClient boundary against the tool's input JSON Schema; raise `MCPArgumentError` on mismatch; tools without an `inputSchema` skip validation — see §5
- [x] **MCPTool dataclass shape** — see §5b
- [x] **SDK pin**: `mcp==1.27.0` (PyPI latest at flight-design time), `_PINNED_PROTOCOL_VERSION = "2025-11-25"` matching the SDK's `LATEST_PROTOCOL_VERSION` — see §6
- [x] **Test strategy**: 3-layer (unit with mocked `ClientSession`, integration via in-repo FastMCP fixture, no browser); fixture at `tests/fixtures/mcp/hello_server.py` (runnable-script convention rather than `tests/_mcp_fixtures.py`); streamable-http integration tests run in-process via ASGI transport — see §7
- [x] **Timeout**: separate constants for handshake/list-tools (`MCP_DEFAULT_TIMEOUT_SECONDS = 30`) and tool-call (`MCP_DEFAULT_CALL_TIMEOUT_SECONDS = 60`) — see §8
- [x] **F4-pool compatibility invariants**: locked at F2 — picklable-free, idempotent `disconnect()`, `is_alive: bool` and `last_activity: float` properties exposed (matching `PtySession` naming) — see §9
- [x] **Reference server choice for tests** (mission Open Q): in-repo FastMCP "hello world" fixture, no external `mcp-server-everything` dependency — see §7
- [x] **Version-mismatch policy** (mission Constraint #45 deviation): fail-hard at handshake during pre-release; degrade-and-capgate is the post-1.0 evolution. Note that the SDK's own `SUPPORTED_PROTOCOL_VERSIONS` accepts `["2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"]`; F2 is *narrower* — see §10
- [x] **Env-var assembly shape** (carried from F1 debrief action item): 2-layer flat merge of canonical host allowlist (from `the_one/platform/env._ENV_ALLOWLIST`) + operator-configured kv table (`config.env ∪ secrets`); secrets win on collision; allowlist is the floor — see §11

### Design Decisions

**§1. Module placement: `the_one/mcp/` peer of `the_one/llm/`**

`MCPClient` is a service abstraction (like `LLMProvider`), not a `Tool`. F6 will wrap MCP servers' tools into `Tool` instances via a `MCPToolProvider` that satisfies the existing `ToolProvider` protocol (`the_one/tools/provider.py:8-51`) — but that wrapping lives at the `tools/` layer; the underlying client lives at the service layer. Placing `the_one/mcp/` peer of `the_one/llm/` keeps the mental model consistent with how LLMs are organized.

- Rationale: matches `the_one/llm/` precedent (verified — `the_one/llm/__init__.py:1-12` re-exports a small surface); avoids the false "MCP is just a tool thing" mental model; gives F4's pool, F5's OAuth flow, F6's tool integration, and F7's inspector all a clear shared dependency to import from
- Trade-off: one more top-level package; single-purpose, narrow API surface

**Sub-structure**:
- `the_one/mcp/__init__.py` — re-exports + `_PINNED_PROTOCOL_VERSION`, `MCP_DEFAULT_TIMEOUT_SECONDS`, `MCP_DEFAULT_CALL_TIMEOUT_SECONDS` constants
- `the_one/mcp/client.py` — `MCPClient` class
- `the_one/mcp/errors.py` — `MCPClientError` hierarchy
- `the_one/mcp/types.py` — `MCPTool`, `MCPToolResult` dataclasses
- `the_one/mcp/transports/__init__.py`
- `the_one/mcp/transports/stdio.py` — `build_stdio_environ()` helper + stdio connection plumbing
- `the_one/mcp/transports/streamable_http.py` — headers-assembly helper + streamable-http connection plumbing

**§2. MCPClient API surface: async context manager wrapping explicit lifecycle**

```python
class MCPClient:
    def __init__(
        self,
        source: MCPSource,
        *,
        timeout_seconds: int = MCP_DEFAULT_TIMEOUT_SECONDS,
        call_timeout_seconds: int = MCP_DEFAULT_CALL_TIMEOUT_SECONDS,
    ) -> None: ...

    async def connect(self) -> None: ...           # explicit lifecycle
    async def disconnect(self) -> None: ...        # idempotent, never raises
    async def list_tools(self) -> list[MCPTool]: ...
    async def call_tool(self, name: str, arguments: dict[str, Any]) -> MCPToolResult: ...

    async def __aenter__(self) -> "MCPClient":
        await self.connect()
        return self
    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.disconnect()

    def __repr__(self) -> str:
        # Format: MCPClient(source='gh-mcp', type='stdio', is_alive=True, last_activity=12345.67)
        # Reaches the LLM context when an exception propagates into tool_results;
        # mission constraint #61 (small-model-friendly) makes this a default not a nice-to-have.
        ...

    @property
    def is_alive(self) -> bool:
        # False until connect() returns successfully; true thereafter; false from the
        # moment disconnect() begins. PtySession-aligned naming (the_one/platform/pty.py:114-128).
        ...

    @property
    def last_activity(self) -> float:
        # time.monotonic() updated on every list_tools() and call_tool() call. Initialized
        # to time.monotonic() at the moment connect() returns successfully. PtySession-aligned.
        ...

    @property
    def negotiated_protocol_version(self) -> str: ...  # post-handshake; raises if not connected
    @property
    def server_capabilities(self) -> dict[str, Any]: ...  # post-handshake; raises if not connected
```

- Rationale: F2's per-call usage reads naturally as `async with MCPClient(source) as client: tools = await client.list_tools()`. F4's pool calls `client.connect()` once on insertion and `client.disconnect()` on eviction without using `async with`. The hybrid pattern costs nothing
- **Property naming aligned with `PtySession`** (`is_alive`/`last_activity` rather than `is_connected`/`last_used_at`) so F4's per-source registry can be a single code path across PTY-and-MCP via a shared structural protocol if F4 chooses
- Trade-off: small API surface duplication (`__aenter__` and `connect()` both exist); accepted

**§3. Error hierarchy**

```python
class MCPClientError(Exception):
    """Base for all MCPClient-raised errors. Subclasses format clean strings for small-model consumption."""

class MCPVersionMismatch(MCPClientError):
    def __init__(self, pinned: str, observed: str) -> None: ...

class MCPCapabilityMissing(MCPClientError):
    def __init__(self, capability: str) -> None: ...

class MCPConnectionError(MCPClientError):
    """Spawn failed, stream closed, network unreachable, transport-level error."""

class MCPToolNotFoundError(MCPClientError):
    def __init__(self, tool_name: str) -> None: ...

class MCPArgumentError(MCPClientError):
    """call_tool arguments don't conform to the tool's input JSON Schema."""

class MCPCallError(MCPClientError):
    """Server returned a tool-call error (isError=true on the result)."""
    def __init__(self, tool_name: str, server_message: str) -> None: ...
```

- Each subclass formats a single clear sentence in `__str__`. No nested causes, no rich tracebacks visible in tool-result strings
- **Capability-missing policy**: fail-hard on `tools` capability missing (F2 needs it; without it the server is unusable). Other capabilities (`resources`, `prompts`, `sampling`, `experimental`) are non-fatal — they're deferred from this mission anyway
- **`mcp.shared.exceptions.UrlElicitationRequiredError` propagates as-is** (NOT wrapped). F2 doesn't claim elicitation capability so well-behaved servers won't trigger it; if a non-conforming server triggers it, the operator sees the SDK's own error type with its full context
- **SDK error translation**: `mcp.shared.exceptions.McpError` → `MCPCallError` (when raised from call_tool) or `MCPConnectionError` (when raised from session lifecycle); `RuntimeError` from `session.initialize()` (the SDK raises this on `protocolVersion not in SUPPORTED_PROTOCOL_VERSIONS`) → `MCPVersionMismatch`; `httpx.HTTPError` and `anyio.ClosedResourceError` etc. → `MCPConnectionError`; `asyncio.TimeoutError` → `MCPConnectionError` (handshake/list-tools) or `MCPConnectionError` with "tool call exceeded N seconds" message (call_tool — `asyncio.TimeoutError` is also re-raised as-is so callers expecting it still work; design goal: surfaceable to small models, debuggable in inspector)
- Rationale: mission constraint #61 (small-model friendly, no clever exception types). One word, one sentence, cleanly formatted
- Trade-off: less granular than catching specific SDK errors; the wrapper translates eagerly

**§4. Tool-call result rendering: hybrid `MCPToolResult` dataclass**

```python
@dataclass(frozen=True)
class MCPToolResult:
    text: str                              # flattened text for agent consumption
    raw: list[dict[str, Any]]              # original content blocks for inspector (F7)
    structured: dict[str, Any] | None      # MCP `structuredContent` typed-object form
    is_error: bool                         # mirrors the server's isError flag
```

`text` is built by concatenating all text-type content blocks in order, with non-text blocks rendered as small placeholder strings (`"[image: 1234 bytes, mime=image/png]"`, `"[audio: 5678 bytes]"`, `"[resource_link: file:///x.txt]"`, `"[resource: <uri>]"`). `raw` is the unmodified list-of-dicts the SDK returns. `structured` is populated when the server emits `structuredContent`. `is_error` mirrors the server's `isError` flag — if true, MCPClient.call_tool() raises `MCPCallError`; the dataclass field exists for inspector trace pane visibility (F7) where the operator wants to see a server-side error result rendered without an exception interrupting the trace.

- **Asymmetry note**: F2 validates tool *input* arguments (the SDK doesn't); the SDK validates *output* against `outputSchema` (`mcp/client/session.py:399-422`) and raises `RuntimeError` on mismatch — F2 propagates that as-is (or could translate to a future `MCPOutputError`; deferred — current SDK behavior is fine for F2's small-model constraint)
- Rationale: F2 doesn't know what F6 (agent integration) and F7 (inspector) will need; the dataclass gives both a clean read path. Mission constraint #56 (agent loop dispatches by tool name; tool results render to string format) is satisfied by `.text`
- Trade-off: slightly more memory per result than text-only; negligible

**§5. Tool input validation at MCPClient boundary**

`call_tool(name, arguments)` validates `arguments` against the tool's `inputSchema` (JSON Schema) before sending the JSON-RPC request. Validation uses the `jsonschema` library — verified at flight-design time as a *direct* requirement of `mcp==1.27.0` (`Requires-Dist: jsonschema>=4.20.0` in the wheel METADATA), NOT transitive — so no separate pin needed.

- Schema-mismatch → `MCPArgumentError(tool_name, validation_error_message)`
- Tools whose `inputSchema` is missing or `null` (the spec is permissive) **skip validation** — `call_tool` passes arguments through. This matches the SDK's own permissiveness; tightening would punish well-behaved servers that omit a schema for trivial tools

- Rationale: small LLMs (mission constraint #61) sometimes hallucinate argument shapes; catching this at the client boundary returns a clean error to the agent step loop with a navigable message, rather than a server-side cryptic JSON-RPC error
- Trade-off: small per-call validation cost; accepted. Validation is "strict" (no coerce, no drop-unknown) — the agent's error-recovery loop can re-call with corrected arguments

**§5b. `MCPTool` dataclass shape**

```python
@dataclass(frozen=True)
class MCPTool:
    name: str                                  # globally unique within a server's tool list
    description: str                           # human-readable summary; passed to the LLM
    input_schema: dict[str, Any]               # JSON Schema; may be {} for schema-less tools
    output_schema: dict[str, Any] | None       # JSON Schema for structuredContent; None if not declared
    annotations: dict[str, Any] | None         # MCP "annotations" (read-only hints, etc.)
```

- F6 will translate `MCPTool` into `Tool` instances (the project's existing tool abstraction at `the_one/tools/base.py`); F2 stops at the dataclass — no Tool conversion in this flight
- F7 (inspector) reads `input_schema` to render form-driven invocation
- `_meta`, `title`, and other SDK fields are deliberately not surfaced in F2 — they can be added later without breaking callers (frozen dataclass with new optional fields = backward compatible)

**§6. SDK pin and protocol version constant**

```python
# the_one/mcp/__init__.py
_PINNED_PROTOCOL_VERSION = "2025-11-25"  # matches mcp==1.27.0's LATEST_PROTOCOL_VERSION
MCP_DEFAULT_TIMEOUT_SECONDS = 30          # handshake + list_tools
MCP_DEFAULT_CALL_TIMEOUT_SECONDS = 60     # call_tool (longer for legitimate tool work)
```

`pyproject.toml` adds `"mcp==1.27.0"` to the base dependencies (NOT compatible-release `~=`, NOT minimum `>=`, NOT optional). The constant docstring documents the upgrade procedure.

- **Verified at flight-design time** via `pip download mcp==1.27.0 --no-deps -d /tmp/mcp-wheel && unzip -l /tmp/mcp-wheel/mcp-*.whl` and reading `mcp/types.py:27`. Reproducible recipe in flight-log.md Part C
- **L2 implementation note**: `_PINNED_PROTOCOL_VERSION` MUST be read at call time (`from the_one import mcp; mcp._PINNED_PROTOCOL_VERSION`), NOT imported by name (`from the_one.mcp import _PINNED_PROTOCOL_VERSION`). The latter binds at module-load and breaks `monkeypatch.setattr` in tests
- Rationale: mission constraint #45 mandates exact pinning; the constant gives test code and the inspector a single source of truth
- Trade-off: pinned versions need manual upgrade; intentional per mission

**§7. Test strategy + FastMCP fixture location**

Three test layers:

1. **Unit tests** (~15–20 tests in `tests/test_mcp_client.py`): mock `mcp.ClientSession` directly via `unittest.mock`. Cover MCPClient lifecycle (connect/disconnect/double-close idempotency), version handshake (match/mismatch), capability negotiation (tools-present / tools-missing / other-missing), error translation (SDK errors → our hierarchy), result rendering (each content block type), input validation (valid args / schema-mismatch / unknown tool / no-schema-tool-skipped), F4-compat properties (`is_alive`, `last_activity`), `build_stdio_environ` precedence (3 layers minus allowlist-source = 2 layers + secrets-wins-on-collision)
2. **Integration tests** (~5–7 tests in `tests/test_mcp_integration.py`): real wire round-trips via the FastMCP fixture
   - **Stdio mode**: spawn `python tests/fixtures/mcp/hello_server.py --stdio` as a subprocess; SDK's `stdio_client(StdioServerParameters(...))` wires the pipes
   - **Streamable-http mode**: in-process — instantiate `FastMCP(...)` in pytest fixture, get its `streamable_http_app() -> Starlette`, wrap in `httpx.AsyncClient(transport=ASGITransport(app=...))`, pass to `streamable_http_client(http_client=...)`. **NO real socket, NO ephemeral port**, NO uvicorn worker thread. The new SDK function `streamable_http_client(url, *, http_client=None, ...)` (`mcp/client/streamable_http.py:601`) accepts a pre-built `httpx.AsyncClient` precisely for this kind of in-process testing. (The deprecated `streamablehttp_client` does NOT accept `http_client=` and would force a real socket — F2 uses ONLY the current `streamable_http_client` name)
3. **Browser tests**: none for F2 (no UI changes)

**FastMCP fixture** lives at `tests/fixtures/mcp/hello_server.py` — single file, two trivial tools:
- `echo(message: str) -> str` — returns `message` verbatim (text-only result path)
- `add(a: int, b: int) -> int` — returns `a + b` (structured-content path; integer result)

Imports `FastMCP` from `mcp.server.fastmcp` (verified bundled in `mcp==1.27.0`; no separate `fastmcp` PyPI dep). The fixture is a runnable script (with `if __name__ == "__main__": ...` and a CLI flag `--stdio`/`--http`) — that's why it lives in `tests/fixtures/mcp/` rather than the `tests/_mcp_fixtures.py` underscore-helper convention. The convention split: helper modules go in `tests/_*.py`; runnable scripts go in `tests/fixtures/{slug}/`.

- Rationale: in-repo Python fixture avoids npm dependency, runs fast in CI without network, and gives a pinned-shape server we control. Mission Open Q "Reference server choice for tests" closes here. The in-process ASGI path makes the streamable-http leg structurally simpler than stdio (no subprocess, no broken-pipe handling, no port-binding races)
- Trade-off: doesn't exercise diversity of real-world MCP servers (slow Node startup, weird stderr logging); F7's HAT or a future integration matrix would address that. F2's optional L7 covers a single end-to-end real-server smoke

**§8. Timeout — separate handshake and call timeouts**

```python
MCP_DEFAULT_TIMEOUT_SECONDS = 30      # handshake (initialize) + list_tools — should be fast
MCP_DEFAULT_CALL_TIMEOUT_SECONDS = 60 # call_tool — legitimate tools may run longer (e.g. static analyzer)
```

Both overridable via `MCPClient(__init__, timeout_seconds=..., call_timeout_seconds=...)`. The MCPClient must always respect asyncio cancellation cleanly regardless of timeout value (mission constraint #56). On timeout, `MCPConnectionError` raises with a small-model-friendly message ("MCP server did not respond within N seconds during {operation}").

- Codebase consistency: 30s matches `the_one/llm/ollama_api.py` status-call defaults; 60s gives tool calls headroom while staying tight enough to surface hung servers. Per-source operator override is a future flight if anyone asks
- Trade-off: two constants instead of one; clarity gain >> extra surface

**§9. F4-pool compatibility invariants** (locked at F2)

- (i) **Picklable-free**: MCPClient instances hold no thread-locals, no `threading.Lock` (asyncio locks only), no module-globals as attribute references. F4 can store them in a dict-keyed registry without issue
- (ii) **Idempotent `disconnect()`**: calling `disconnect()` on an already-disconnected client is a no-op (no exception, no log line at WARN level — DEBUG only). F4's reaper races with operator-initiated disconnect; both must be safe
- (iii) **Public properties for the reaper**: `is_alive: bool` (false until `connect()` returns successfully; true thereafter; false from the moment `disconnect()` begins) and `last_activity: float` (`time.monotonic()` updated on every `list_tools()` and `call_tool()` call; initialized at successful `connect()`). F4's reaper reads these to evict idle clients
- **Naming alignment**: properties match `PtySession` (`the_one/platform/pty.py:114-128`) so F4 can build one reaper code path that handles both PtySession and MCPClient via structural typing. **This is intentional and load-bearing.**

These three are exercised by F2's unit tests (double-disconnect test, last_activity-update test, is_alive-state-machine test). F4 will not need to extend MCPClient to implement its pool.

**§10. Version-mismatch policy: fail-hard at handshake (pre-release deviation, narrower than SDK)**

The mission constraint at `mission.md:45` mandates "capability-gate spec features so an interaction with a server announcing a different revision degrades rather than crashes." F2 deviates: pre-release, MCPClient raises `MCPVersionMismatch(pinned, observed)` from `connect()` if `server.protocolVersion != _PINNED_PROTOCOL_VERSION` (exact string match). The connection never reaches `list_tools` or `call_tool`. The error message format is small-model friendly: `"MCP server announced protocol version {observed}, the-one supports {pinned}. Server upgrade or the-one downgrade required."`

**Important: F2's strict check is *narrower* than the SDK's own validation.** The SDK at `mcp/client/session.py:190-191` validates against `SUPPORTED_PROTOCOL_VERSIONS = ["2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"]` and raises `RuntimeError("Unsupported protocol version from the server: ...")` on truly-unsupported versions. F2 catches that `RuntimeError` and re-raises as `MCPVersionMismatch` (so the operator sees one consistent error type). For versions in `SUPPORTED_PROTOCOL_VERSIONS` but not equal to `_PINNED_PROTOCOL_VERSION` (e.g., a server announcing `"2025-06-18"`), the SDK is happy but **F2 still rejects**. This is intentional: pre-release we want exact-revision-match against what we tested.

- Rationale: pre-release we want strict known-good-state guarantees. Fail-hard surfaces drift at the earliest possible point — the operator sees a clean error in the inspector (F7) rather than a partially-working tool list with subtle semantic drift. Easier to soften later (relax to "in `SUPPORTED_PROTOCOL_VERSIONS`" + capgate) than to harden later
- Trade-off: operators with slightly-stale-but-SDK-supported servers can't connect. **Acceptable pre-release; this decision is revisited at 1.0** with the explicit alternative being "trust the SDK's whitelist and capability-gate per spec section." Captured as a forward action item in this flight's debrief
- **Mission-level note**: mission constraint §45 stays as-is (long-term north star); F2's flight-level deviation is documented here with rationale

**§11. Env-var assembly shape — 2-layer flat merge**

```python
# the_one/mcp/transports/stdio.py
from the_one.platform.env import _ENV_ALLOWLIST  # (canonical 8-key allowlist; do NOT redeclare)

def build_stdio_environ(source: MCPSource, allowlist_env: dict[str, str]) -> dict[str, str]:
    """Materialize the spawned-child environ for a stdio MCP source.

    Two layers, in precedence order:
      1. allowlist_env — host environment filtered to _ENV_ALLOWLIST (mission constraint #50 / #57).
                         Caller (typically MCPClient.connect()) builds this via
                         the_one.platform.env._build_subprocess_env().
      2. operator-configured kv table — config["env"] (plaintext-at-rest) ∪ secrets (encrypted-at-rest),
         flat-merged with secrets winning on collision.

    Layer 2 is one logical concept (the operator's kv table from the L6 editor); the at-rest
    config/secrets split is purely the F1 encryption-at-rest implementation detail and dissolves
    here.

    NOTE: do NOT call source.merged_config() — that produces {**config, **secrets} which would
    inject command/args/etc. as env-var-shaped keys. The kv table for stdio sources lives at
    config["env"], not at config top-level.
    """
    operator_env: dict[str, str] = {**source.config.get("env", {}), **source.secrets}
    return {**allowlist_env, **operator_env}
```

- **Reuses the canonical allowlist** at `the_one/platform/env.py:_ENV_ALLOWLIST` rather than re-declaring. Future hardening (e.g., adding `XDG_RUNTIME_DIR`) propagates automatically
- **Function signature accepts `allowlist_env` as parameter** (rather than calling `_build_subprocess_env()` internally) for testability — tests inject a known-shape allowlist via fixture, no `monkeypatch.setenv` pollution. Production callers pass `_build_subprocess_env()`
- Rationale: closes F1 debrief action item ("F2 leg design must confirm env-var assembly shape; do NOT blindly consume `merged_config()` for stdio env vars")
- Trade-off: `merged_config()` exists on the model but isn't used by F2 (and probably shouldn't be used by F4 either); future routine-maintenance candidate to deprecate or document narrow applicability

**§12. F1 config.env shape validation — picked up in F2's L1**

F1's `_validate_mcp_source_config` (`the_one/interfaces/web/api.py:539-628`) validates `config.command` (non-empty str) and `config.args` (list[str]) for stdio sources, but does NOT validate `config.env`. An operator who PUTs `config.env = {"FOO": 42}` (number, not string) would land an unsafe config that `build_stdio_environ` would put into a dict that the SDK's `StdioServerParameters(env: dict[str, str])` would reject at connect time with a Pydantic validation error.

F2's L1 picks up this gap: extends `_validate_mcp_source_config`'s stdio branch to validate `config.env: dict[str, str]` (mirroring the existing `config.headers: dict[str, str]` validation at api.py:587-593 for streamable-http). This is a forward-looking F1↔F2 contract reaffirmation: the API rejects bad shape; the runtime trusts the model.

- Rationale: defensive consistency with F1's existing patterns (`else: raise` exhaustiveness; `headers` shape validation). Catching at the API boundary returns a 422 with a clean message instead of a runtime crash later
- Trade-off: small backfill into F1 territory; lives in F2's L1 because L1 is where we touch the API anyway for the `/types` endpoint contract reaffirmation, and the test for `config.env` validation is co-located with F2's stdio testing concern. NOT a separate routine-maintenance pass

### Prerequisites

- [x] F1 landed and `completed`. Schema v10 in place; `MCPSource` model with `Literal["stdio", "streamable-http"]`; `MCPSourceRepository` returning fully-decrypted `MCPSource` instances; `/api/mcp-sources` CRUD with masked GET/PUT — see Phase 1b reconnaissance report in flight-log.md for line-anchored confirmations
- [x] **F1↔F5 OAuth runtime token slots NOT pre-landed** (per F1 debrief Key Learning #6): F2 does NOT depend on `secrets["access_token"]`, `["refresh_token"]`, `["token_expires_at"]` — F2's static-bearer support emerges from the operator typing `Authorization: Bearer xxx` as a row of the headers kv table. F5 introduces those slots
- [x] `mcp==1.27.0` available on PyPI (verified at design time via `pip index versions mcp`; reproduction recipe in flight-log.md Part C)
- [x] `mcp==1.27.0` is `py3-none-any` (universal Python 3, Python 3.10+ `Requires-Python`); compatible with the-one's `requires-python = ">=3.11"` (`pyproject.toml:5`)
- [x] `mcp==1.27.0` direct dependency `jsonschema>=4.20.0` (verified via wheel METADATA inspection); F2 does NOT need to add jsonschema to `pyproject.toml`
- [x] `mcp==1.27.0` exports `mcp.client.stdio.stdio_client` + `mcp.client.streamable_http.streamable_http_client` (current API; the deprecated `streamablehttp_client` is NOT used by F2)
- [x] `mcp.server.fastmcp.FastMCP` is bundled in `mcp==1.27.0` (no separate `fastmcp` PyPI dependency)
- [x] `mcp.server.fastmcp.FastMCP.streamable_http_app() -> Starlette` available for in-process ASGI integration testing (verified in `mcp/server/fastmcp/server.py:950`)
- [x] No port conflicts: F2's streamable-http integration tests use in-process ASGI transport (zero socket binding); stdio integration tests use pipes (zero socket binding)
- [x] CI Dockerfile already includes Python 3.11; no apt additions needed for F2 (bubblewrap is F3)
- [x] `the_one/platform/env._ENV_ALLOWLIST` is the canonical env-var allowlist (8 keys); F2 imports rather than re-declares

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented (§§1–12 above)
- [x] Prerequisites verified
- [x] Validation approach defined (test strategy in §7)
- [x] Legs defined (see In-Flight § Legs)
- [x] Architect design review passed (per Phase 5b — see flight-log.md)

---

## In-Flight

### Technical Approach

Thin wrapper over an opinionated-but-stable SDK pin. The `mcp==1.27.0` SDK exposes:

- `mcp.ClientSession` — the JSON-RPC envelope handler; `session.initialize()` runs the handshake (and itself enforces `SUPPORTED_PROTOCOL_VERSIONS`)
- `mcp.client.stdio.stdio_client(StdioServerParameters)` — async context manager yielding `(read_stream, write_stream)` for `ClientSession`. Constructor takes `command`, `args`, `env`, `cwd`
- `mcp.client.streamable_http.streamable_http_client(url, *, http_client=None, terminate_on_close=True, ...)` — current (non-deprecated) async context manager yielding `(read_stream, write_stream, get_session_id)` for `ClientSession`. Accepts pre-built `httpx.AsyncClient` for in-process ASGI testing
- `mcp.shared.exceptions.McpError` — the SDK's own error class (translated to our hierarchy)

`MCPClient.connect()` dispatches on `source.type`:
- For stdio: `connect_stdio(source)` builds `StdioServerParameters(command=..., args=..., env=build_stdio_environ(source, _build_subprocess_env()), cwd=source.config.get("cwd"))`, opens the `stdio_client` context, instantiates `ClientSession`
- For streamable-http: `connect_streamable_http(source)` builds the URL and headers (`build_request_headers(source)` — analogous to `build_stdio_environ` but for HTTP headers), opens the `streamable_http_client` context, instantiates `ClientSession`. In tests, the `http_client` parameter passes an in-process ASGI-transport `httpx.AsyncClient`

After session creation, `MCPClient`:
1. Calls `session.initialize()` inside an `asyncio.timeout(timeout_seconds)`
2. Catches `RuntimeError` from `initialize()` (SDK-level version rejection) → re-raises as `MCPVersionMismatch`
3. Validates `result.protocolVersion == _PINNED_PROTOCOL_VERSION` exactly → raises `MCPVersionMismatch` if not (narrower than SDK; intentional per §10)
4. Validates `result.capabilities.tools is not None` → raises `MCPCapabilityMissing("tools")` if absent
5. Stores `session`, `result.capabilities`, `result.protocolVersion`; sets `is_alive = True`, `last_activity = time.monotonic()`

`disconnect()` cancels the active call (if any), exits the session and transport context managers, sets `is_alive = False`. Idempotent: a second call no-ops.

`list_tools()` calls `session.list_tools()` inside `asyncio.timeout(timeout_seconds)`, converts each tool to `MCPTool`, updates `last_activity`, returns the list.

`call_tool(name, args)` looks up the tool's `inputSchema` from the cached tools (refreshing if stale), validates `args` via `jsonschema.validate(args, schema)` if a schema exists, calls `session.call_tool(name, args)` inside `asyncio.timeout(call_timeout_seconds)`, converts the result to `MCPToolResult`, raises `MCPCallError` if `result.isError`, updates `last_activity`, returns. On unknown tool name, raises `MCPToolNotFoundError` BEFORE any wire call.

The two transport modules own connection details (translate `MCPSource` → SDK params dict) and pre-spawn assembly helpers (`build_stdio_environ` / `build_request_headers`). `MCPClient` itself is transport-agnostic — it dispatches once at `connect()` and otherwise treats the resulting `ClientSession` uniformly.

The FastMCP fixture is the single point of integration-test coverage:
- **Stdio mode**: `python tests/fixtures/mcp/hello_server.py --stdio` is spawned by tests as a subprocess; pipes wired by `stdio_client`
- **Streamable-http mode**: pytest fixture instantiates `FastMCP(...)`, gets `app = fastmcp.streamable_http_app()`, builds `httpx.AsyncClient(transport=ASGITransport(app=app))`, passes to `streamable_http_client(url="http://test/mcp", http_client=client)`. Tests run entirely in-process

### Checkpoints

- [ ] **C1** — `mcp==1.27.0` installed; `_PINNED_PROTOCOL_VERSION` matches the SDK's `LATEST_PROTOCOL_VERSION` (asserted in test); `MCPClientError` hierarchy in place; `MCPTool`/`MCPToolResult` dataclasses defined; module skeleton imports cleanly; F1 API `config.env` validation extension lands (L1)
- [ ] **C2** — MCPClient lifecycle (connect/disconnect/idempotency), version handshake (match + mismatch + SDK-RuntimeError translation), capability negotiation (tools-present + tools-missing) all unit-tested with mocked `ClientSession`; F4-compat properties (`is_alive`, `last_activity`) exercised via mocked-call tests (L2)
- [ ] **C3** — In-repo FastMCP fixture authored at `tests/fixtures/mcp/hello_server.py`; pytest fixtures wire it for both stdio (subprocess) and streamable-http (in-process ASGI) modes (L3)
- [ ] **C4** — Streamable-http transport happy-path: connect → list-tools → call-tool (`echo`, `add`) → disconnect via in-process ASGI; headers-assembly unit-tested (L4)
- [ ] **C5** — Stdio transport happy-path: same shape against the fixture's stdio mode; `build_stdio_environ()` 2-layer precedence unit-tested (importing canonical allowlist) (L5)
- [ ] **C6a** — `list_tools()` + `call_tool()` happy-path with `MCPToolResult` text+structured rendering; agent-readable text-block flattening (L6a)
- [ ] **C6b** — Tool-call result rendering covers all non-text content block types (image, audio, resource_link, resource); input validation (`MCPArgumentError`) including no-schema-tool-skipped; full error-path translation (server-side isError, malformed handshake, stream closed mid-call, timeout) (L6b)

### Adaptation Criteria

**Divert if**:
- `mcp==1.27.0` is unexpectedly broken in our Python 3.11 environment (e.g., import fails, transport context managers raise on import) — pivot to a different stable version (1.26.0 or earlier) and update `_PINNED_PROTOCOL_VERSION` accordingly
- `mcp==1.27.0` is found to have a known security advisory (CVE) between flight-design and L1 install — pivot to the latest non-affected version; verify the new version's `LATEST_PROTOCOL_VERSION` matches before pinning
- The in-process ASGI streamable-http test pattern fails (e.g., `streamable_http_client` rejects an `httpx.AsyncClient` built with `ASGITransport`, contrary to flight-design assumption) — fall back to spawning the streamable-http fixture as a real subprocess on an ephemeral port. Document why in flight log
- The mission's "small-model friendly" constraint conflicts with a specific error message that needs structured detail — surface the conflict in the flight log; resolve in favor of "small-model first" by trimming the error message's structure, not adding it
- `the_one/platform/env._ENV_ALLOWLIST` turns out to NOT be the right helper to import (e.g., it's coupled to PTY in a way that breaks for MCP) — extract a transport-neutral constant and update both call sites; document in flight log

**Acceptable variations**:
- Bundling the FastMCP fixture authoring (L3) into L4 if the fixture turns out to be <100 LOC and authoring it standalone feels artificial
- Adding a small smoke test against a real third-party MCP server at the end of L6b if the in-repo fixture coverage feels insufficient — opt-in / skipped in CI by default to avoid network dependency
- Re-merging L6a/L6b into a single L6 if the leg-design LOC estimate (computed at leg-design time) lands ≤500 for both combined and the architectural review feels it splits artificially
- Adding small ergonomic helpers (e.g. a context-manager `MCPClient.connected_to(source)` factory) if the test code ergonomics demand it

### Legs

> **Note:** Tentative suggestions, not commitments. Refined per leg as work progresses.
> **Conventions for all legs**: leg artifacts use anchor-by-symbol-name (NOT `file.py:LINE`) per F1 debrief recommendation; each leg's post-completion checklist includes `make lint` clean (or "no NEW ruff errors") before `[HANDOFF:review-needed]` per F1 debrief Action Item.

- [x] `01-sdk-pin-and-skeleton` — Add `mcp==1.27.0` to `pyproject.toml` base deps; create `the_one/mcp/` package skeleton (`__init__.py` with `_PINNED_PROTOCOL_VERSION`, `MCP_DEFAULT_TIMEOUT_SECONDS`, `MCP_DEFAULT_CALL_TIMEOUT_SECONDS`); create `the_one/mcp/errors.py` with the `MCPClientError` hierarchy; create `the_one/mcp/types.py` with `MCPTool` and `MCPToolResult` dataclasses; create empty `the_one/mcp/client.py` and `the_one/mcp/transports/{stdio,streamable_http}.py` stubs that import without error; **extend F1's `_validate_mcp_source_config` stdio branch to validate `config.env: dict[str, str]`** (mirrors existing `headers` validation; rejects 422 on bad shape) — this is a one-block API patch with one new test in `tests/test_db_api.py::TestMCPSourceAPI`. Update `CLAUDE.md` and `agents.md` enumerating the 6 F2 contracts: (1) module layout `the_one/mcp/{...}`, (2) `_PINNED_PROTOCOL_VERSION` location and upgrade procedure, (3) F4-pool compat invariants (`is_alive`, `last_activity`, idempotent disconnect, picklable-free), (4) `build_stdio_environ` env-assembly helper signature and the explicit non-consumption of `merged_config()` for stdio (rationale captured so a future maintainer doesn't "fix" by switching), (5) the fail-hard version-handshake stance and pre-1.0 rationale, (6) `MCPTool`/`MCPToolResult` dataclass shapes. Verification: `pip install -e ".[dev,all-llms]"` succeeds; `from the_one import mcp` works; `mcp.types.LATEST_PROTOCOL_VERSION == the_one.mcp._PINNED_PROTOCOL_VERSION` asserted in a unit test; existing 1099-test suite still green; new `config.env` shape validation test passes.

- [x] `02-client-lifecycle-and-handshake` — Implement `MCPClient.__init__/connect/disconnect/__aenter__/__aexit__/__repr__` + the version handshake (including the SDK `RuntimeError` → `MCPVersionMismatch` translation) + capability negotiation. Mock `ClientSession` at the import boundary in unit tests (no real transport). Implement F4-compat properties (`is_alive`, `last_activity`, `negotiated_protocol_version`, `server_capabilities`). Verification: ~10 unit tests covering state machine (uninitialized → connecting → alive → disconnected), version-match-vs-mismatch (exact match passes; mismatch raises; SDK-rejected version raises as `MCPVersionMismatch`), capability-tools-present-vs-missing, double-disconnect-idempotency, last_activity-updates-via-mock-list-tools-call (real list_tools is L6a; here it's a mocked stub), `__repr__` format pinned. Test note: `_PINNED_PROTOCOL_VERSION` read at call time so `monkeypatch.setattr` works in tests.

- [x] `03-fastmcp-hello-fixture` — Author `tests/fixtures/mcp/hello_server.py` with `FastMCP("hello")`, `echo(message: str) -> str`, `add(a: int, b: int) -> int`. Add CLI flag dispatch: `--stdio` runs `mcp.run()`, `--http` returns the Starlette app for ASGI embedding (with a usage note that the in-process pytest path doesn't actually run this CLI, only the stdio path does). Wire pytest fixtures: `mcp_fixture_stdio` yields a `StdioServerParameters`-shaped dict pointing at the subprocess; `mcp_fixture_http_asgi` yields a configured `httpx.AsyncClient` with `ASGITransport` over the FastMCP app (no socket). Verification: 2 smoke tests confirm the fixture loads and responds to a bare `tools/list` call via raw SDK (without `MCPClient` involvement) — one per mode.

- [x] `04-streamable-http-transport` — Implement `the_one/mcp/transports/streamable_http.py`: headers-assembly helper (analogous to `build_stdio_environ` — flat merge of `config.headers ∪ secrets`) + the streamable-http connection plumbing using `streamable_http_client(url, http_client=...)` (current API name, NOT deprecated `streamablehttp_client`). Static-bearer support emerges from the kv-table itself (operator types `Authorization | Bearer xxx | sensitive=true`). Wire `MCPClient.connect()` to dispatch on `source.type == "streamable-http"`. Verification: ~4 unit tests for headers assembly (empty, sensitive-only, plaintext-only, mixed-with-collision); ~3 integration tests against L3's `mcp_fixture_http_asgi` (connect → list → call(echo) → disconnect; connect → list → call(add) with structured result; double-connect raises). Streamable-http-first ordering chosen because the new SDK API + ASGI in-process path is structurally simpler than stdio (no subprocess management); MCPClient's transport-agnostic concerns get exercised end-to-end before L5 introduces subprocess complications.

- [x] `05-stdio-transport` — Implement `the_one/mcp/transports/stdio.py`: import `_ENV_ALLOWLIST` and `_build_subprocess_env` from `the_one.platform.env` (DO NOT re-declare); implement `build_stdio_environ()` per §11; stdio-specific connection plumbing (translate `MCPSource` to `StdioServerParameters`, open `stdio_client` context, wrap result in `ClientSession`). Wire `MCPClient.connect()` to dispatch on `source.type == "stdio"`. Verification: ~6 unit tests for `build_stdio_environ` (2-layer precedence, secrets-wins-on-collision, allowlist-floor, empty config.env, missing config.env key, allowlist isolation [secrets cannot overwrite allowlist? deferred — not currently enforced; document]); ~3 integration tests against L3's `mcp_fixture_stdio` (connect → list → call(echo) → disconnect; connect → list → call(add) → disconnect; broken-pipe handling via SIGKILL'd subprocess).

- [x] `06a-list-tools-and-call-tool-happy-path` — Implement `MCPClient.list_tools()` + `call_tool()` end-to-end. `MCPToolResult` text-flattening for text-only blocks; `structured` field populated from `structuredContent`. `is_error` raises `MCPCallError` (not returned as a flag). `MCPToolNotFoundError` for unknown tool name (raised before wire call). Verification: ~6 unit tests covering: list_tools with mocked session returning 2 tools → returns 2 MCPTool dataclasses; call_tool with text result → MCPToolResult with .text populated; call_tool with structured result → .structured populated; call_tool with no_schema tool → no validation, succeeds; call_tool with isError=true → MCPCallError raised with server message; call_tool with unknown tool name → MCPToolNotFoundError. ~3 integration tests against both fixtures (echo round-trip; add round-trip with structured; unknown-tool error path).

- [x] `06b-input-validation-and-error-paths` — Add input validation: `call_tool` validates `arguments` against the tool's `inputSchema` via `jsonschema.validate`; tools without `inputSchema` skip validation; mismatch raises `MCPArgumentError(tool_name, validation_error_message)`. Add non-text content-block rendering in `MCPToolResult.text`: image/audio/resource_link/resource → placeholder strings (formats locked in §4). Translate remaining SDK error paths: `httpx.HTTPError` → `MCPConnectionError`; `anyio.ClosedResourceError` → `MCPConnectionError`; `asyncio.TimeoutError` → `MCPConnectionError` with operation-specific message; SDK's `mcp.shared.exceptions.McpError` → `MCPCallError` (for tool calls) or `MCPConnectionError` (for session lifecycle); `UrlElicitationRequiredError` propagates as-is. Verification: ~5 unit tests for input validation (valid args / type mismatch / missing required / extra unknown / no-schema-skip); ~5 unit tests for content-block placeholders (one per non-text block type); ~5 unit tests for error-path translation (one per error class); ~2 integration tests confirming end-to-end (call_tool with deliberately-bad args raises MCPArgumentError; call_tool against a fixture tool that errors out via FastMCP's error-result path raises MCPCallError).

- [x] `07-hat-mcp-foundation` *(optional — completed in HAT walkthrough; in-repo FastMCP fixture used instead of npm server, all 5 + bonus steps PASSED; defect captured for F4)* — Structured 5-step verification list:
  1. Install a real MCP server locally (suggestion: `npx -y @modelcontextprotocol/server-filesystem /tmp` for stdio; or any community Python MCP server)
  2. Configure as an MCP source via the F1 admin UI (verifies F1↔F2 contract end-to-end)
  3. From a Python REPL, `async with MCPClient(source) as c: print(c.negotiated_protocol_version, c.server_capabilities)` — confirm both populate
  4. `print(await c.list_tools())` — at least one tool listed
  5. `print(await c.call_tool(<tool>, {<args>}))` — gets a non-error `MCPToolResult` whose `.text` is human-readable
  
  Bonus step 6 (version-mismatch path verification): downgrade `mcp` SDK locally to a version targeting an older protocol revision; confirm `connect()` raises `MCPVersionMismatch` with both versions in the message; revert.
  
  Binary go/no-go: all 5 steps pass = ✓; any step fails or produces unexpected output = file an issue and fix before flight close. Bonus step is informational; not a gate.

---

## Post-Flight

### Completion Checklist

- [ ] All required legs (L1–L6b) completed; L7 optional
- [ ] All checkpoints (C1–C6b) met
- [ ] `mcp==1.27.0` pinned in `pyproject.toml`
- [ ] `_PINNED_PROTOCOL_VERSION = "2025-11-25"` and matches the SDK's `LATEST_PROTOCOL_VERSION` at install time
- [ ] `make test` green (existing 1099 tests + ~30–35 new MCP-client tests)
- [ ] `make lint` clean (per-leg gate; no accumulated drift)
- [ ] CLAUDE.md and agents.md updated with all 6 F2 contracts (per L1 enumeration)

### Verification

How to confirm the flight achieved its objective:

1. **Unit + integration tests pass**: `pytest tests/test_mcp_client.py tests/test_mcp_integration.py` — green
2. **Manual smoke (HAT-style)**: in a Python REPL, `async with MCPClient(stdio_source) as c: print(await c.list_tools()); print(await c.call_tool("echo", {"message": "hi"}))` returns the expected `MCPToolResult` with `text == "hi"`
3. **Version handshake regression**: `monkeypatch.setattr("the_one.mcp._PINNED_PROTOCOL_VERSION", "2099-01-01")` in a test override and confirm `MCPVersionMismatch` raises from `connect()` against the FastMCP fixture (note: implementation must read the constant at call time, NOT at module-load via `from the_one.mcp import _PINNED_PROTOCOL_VERSION`)
4. **F4-compat properties**: `is_alive` and `last_activity` reflect activity correctly across a connect → 3 calls → idle → disconnect cycle (one unit test pinning each transition)
5. **Lint + existing-suite regression**: `make lint && make test` shows no new failures attributable to F2 changes
6. **Mission Open Q closure (debrief task)**: F2's debrief explicitly captures that mission Open Q "Reference server choice for tests and HAT" closes at F2 — in-repo FastMCP fixture, no `mcp-server-everything` dependency

The flight delivers the runtime foundation that F3 (sandbox), F4 (warm pool), F5 (OAuth), F6 (agent integration), and F7 (inspector) all consume. None of those flights needs to import anything from F2 except `MCPClient`, `MCPToolResult`, `MCPTool`, the `MCPClientError` family, and the `_PINNED_PROTOCOL_VERSION` constant — the public API surface is deliberately small.
