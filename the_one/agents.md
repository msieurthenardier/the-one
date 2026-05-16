# agents.md

Development-facing architecture reference for the-one. This file describes the **target architecture** of the system. It is updated as missions extend or refactor it. It is not loaded at runtime.

For usage, commands, and conventions, see `CLAUDE.md`.

---

## Architecture Overview

The-one is a general-purpose LLM agent built without frameworks. Four layers compose bottom-up:

```
┌─────────────────────────────────────────────────────┐
│  Interfaces (cli.py, web/app.py)                    │
│  → User-facing shells that create agents via factory │
├─────────────────────────────────────────────────────┤
│  Agent (core.py, factory.py, config.py, store.py)   │
│  → Agent loop, configuration, persistence, creation  │
├─────────────────────────────────────────────────────┤
│  Tools (base.py, provider.py, builtins.py, *.py)    │  LLM (base.py, registry.py, *_provider.py)
│  → Tool ABC, registry, provider protocol             │  → Provider ABC, lazy registry, 3 providers
├─────────────────────────────────────────────────────┤
│  Config (config.py)                                  │
│  → Pydantic-settings singleton, THE_ONE_* env vars   │
└─────────────────────────────────────────────────────┘
```

---

## Module Map

### `the_one/config.py`

Global configuration via `pydantic-settings`. All values from `THE_ONE_*` env vars or `.env` file.

| Export | Type | Purpose |
|--------|------|---------|
| `Settings` | class | Pydantic-settings model |
| `settings` | instance | Global singleton |

Key properties: `data_dir` (`~/.the-one`), `agents_dir` (`data_dir / "agents"`), `db_path` (`data_dir / "the-one.db"`), `dev_mode` (default: `false`).

### `the_one/encryption.py`

Fernet-based encryption for API keys stored in the database. Generates and caches an `Encryptor` per `data_dir`. Provides an `install_key()` helper plus a public `key_path` property; the API rotation path (`POST /api/encryption/rotate`) re-encrypts all provider credentials AND all MCP source secrets in a single crash-safe transaction, commits the DB, then atomically replaces the key file via `os.replace`. The single-pass rotation is the authoritative invariant: a partial rotation that handled only one of the two surfaces would leave the other encrypted under a key no longer on disk. The legacy `rotate_key()` callback API is retained for non-API callers.

### `the_one/db/repositories.py`

Database repositories including `LLMProviderRepository` for CRUD on `llm_provider_configs` table. Provider configs store `name`, `type`, `base_url`, and encrypted `api_key`. Referenced by `AgentConfig.provider_config_id`.

`MCPSourceRepository` (M07 F1) handles CRUD on `mcp_sources` (schema v10). Storage shape is **field-segregated encryption with two columns**: `config TEXT DEFAULT '{}'` holds plaintext non-sensitive fields (transport-aware: `command`/`args`/`env` for `'stdio'`, `url`/`headers` for `'streamable-http'`); `secrets TEXT DEFAULT '{}'` holds a single Fernet-encrypted JSON blob whose decoded value is a dict of operator-marked sensitive field values (env-var values, bearer headers, OAuth-managed keys). Encryption is per-row, one `Fernet.encrypt`/`decrypt` per row — NOT per-field inside the JSON. The repository stores the `Encryptor` **as a reference, not a copy**, so post-rotation `install_key()` propagates to live repository instances (mirrors `LLMProviderRepository`'s pattern). The deprecated `'sse'` transport literal was renamed to `'streamable-http'` per MCP spec revision 2025-11-25 in v10's table-rebuild migration via `CASE WHEN type='sse' THEN 'streamable-http' ELSE type END` inside the `INSERT INTO mcp_sources_new SELECT ...` step. The `MCPSource` Pydantic model exposes both fields and a `merged_config()` helper for callers (F2 connect path) that need a flat dict; UI / masking / rotation / F4 resolver consumers keep the split visible.

**`__MASKED__` per-key sentinel on `secrets`**: extends the LLM-provider `__MASKED__` sentinel pattern (single-column) to a per-key semantic on the `secrets` dict. GET `/api/mcp-sources/{id}` returns `{config: {...plaintext...}, secrets: {key: "***...{tail4}", ...}}` with each VALUE masked individually (`***...{tail4}` for `>4` chars, `***` otherwise; mirrors `_mask_api_key`). On PUT, `secrets[key] == "__MASKED__"` preserves the existing stored value for that key; other keys overwrite. This per-key handling is what lets the operator save form edits without re-typing every secret.

**OAuth managed secret keys** post-F6.5: `secrets["dcr_credentials"]` (the OAuthClientInformationFull payload from RFC 7591 DCR), `secrets["access_token"]`, `secrets["refresh_token"]`, `secrets["token_expires_at"]`. Operator-supplied env-var values, headers, etc. are stored under their own operator-chosen keys; the four managed keys are written exclusively by `MCPSourceTokenStorage` (F5) and are stripped+preserved on PUT by the API layer's `_OAUTH_MANAGED_SECRET_KEYS` logic.

**F2 (MCP Client Foundation) contracts** — for full text, see CLAUDE.md "F2 (MCP Client Foundation) Contracts":

- **F2 module home**: `the_one/mcp/` (peer of `the_one/llm/`, NOT under `the_one/tools/`); MCPClient is a service abstraction. F6 wraps MCPClient → Tool via MCPToolProvider.
- **F2 SDK pin + protocol revision**: `mcp==1.27.0` exact pin; `_PINNED_PROTOCOL_VERSION = "2025-11-25"` constant in `the_one/mcp/__init__.py` (read at call time, not import-bound).
- **F2 fail-hard version policy**: `connect()` raises `MCPVersionMismatch` on any mismatch with `_PINNED_PROTOCOL_VERSION`; narrower than the SDK's `SUPPORTED_PROTOCOL_VERSIONS` whitelist; pre-release stance, revisit at 1.0.
- **F2 F4-pool compat**: MCPClient exposes `is_alive: bool` and `last_activity: float` (PtySession-aligned); `disconnect()` is idempotent; instances are picklable-free (no thread-locals, no module-globals).
- **F2 stdio environ helper**: `build_stdio_environ(source, allowlist_env)` does 2-layer flat merge of `the_one.platform.env._ENV_ALLOWLIST` + (config.env ∪ secrets); **do NOT consume `MCPSource.merged_config()`** for stdio environ (that's a flat top-level merge that injects `command`/`args` as env-var keys).
- **F2 dataclasses**: `MCPTool` and `MCPToolResult` are frozen dataclasses in `the_one/mcp/types.py`; `MCPToolResult.text` for agent, `.raw` for F7 inspector, `.structured` for typed-object form.

**F3 (MCP Sandbox) contracts** — for full text, see CLAUDE.md "F3 (MCP Sandbox) Contracts":

- **F3 module home**: `the_one/platform/sandbox/{__init__.py, base.py, bubblewrap.py}` (peer of `the_one/platform/env.py`); `MCPSandboxError` canonical at `the_one/mcp/errors.py`. **L2 lands the package.**
- **F3 trust model**: strict by default — read-only FS outside `writable_paths`; network OFF unless `network_allowed=True`. Operator's responsibility to scope writable paths and network policy per source.
- **F3 sandbox-profile storage**: `MCPSource.config["sandbox"] = {"writable_paths": list[str], "network_allowed": bool}` plaintext; both fields optional; defaults `[]` / `false`; namespace-flag fields (`pid_unshare`, `ipc_unshare`, `uts_unshare`) JSON-edit-only via API. **L1b extends the F1 API validator; L2 lands `SandboxProfile.from_dict`.**
- **F3 Protocol shape**: `MCPSandbox.prepare_spawn(profile, command, args, env, cwd) -> SpawnSpec`; `SpawnSpec` is frozen with command/args/env/cwd + Windows-only `creation_flags`/`attribute_list`. Linux/macOS callers feed `spec.command/args/env/cwd` into `StdioServerParameters`. **L2 lands.**
- **F3 failure boundary**: `MCPSandboxError(MCPClientError)` for setup failures (bwrap missing, writable_paths nonexistent, EPERM on unshare, generic bwrap exit-code != 0); F2's `MCPConnectionError` for post-spawn failures. The bwrap-prefix discriminator (`^\s*bwrap:`) gates the directionality so inner-process failures stay in `MCPConnectionError`. No unsandboxed fallback. **L2 adds the exception class AND enforces the boundary in `connect_stdio` via stderr-capture-and-translate.**
- **F3 privilege model**: dev container `cap_add: [SYS_ADMIN]` + `security_opt: [seccomp:unconfined]` (both required); Playwright CI uses pytest-only `THE_ONE_SANDBOX_DISABLED=1 + THE_ONE_TEST_MODE=1` double-flag bypass; production sandbox always on. **L1a applied the dev-container grants; L4 wires the bypass.**
- **F3 HOME override**: `BubblewrapSandbox` forces `env["HOME"] = "/tmp"` so `~/.cache`-writing MCPs find a usable home dir under `--tmpfs /tmp`. Sandbox policy, not operator-configurable. **L3 implements.**

### `the_one/agent/`

| File | Exports | Purpose |
|------|---------|---------|
| `core.py` | `Agent` | The agent loop: `step()` yields messages, max 20 iterations |
| `config.py` | `AgentConfig`, `BASE_PROMPT` | Agent definition Pydantic model (includes `provider_config_id` for LLM provider resolution) and the foundational base prompt for layered composition |
| `factory.py` | `AgentFactory` | `create(name)` → configured Agent; `list_agents()` |
| `store.py` | `AgentConfigStore`, `FilesystemConfigStore` | CRUD for agent configs (`~/.the-one/agents/*.json`) |

**Agent.step() flow**: user input → LLM call → execute tools → repeat until no tool calls or max iterations.

### `the_one/llm/`

| File | Exports | Purpose |
|------|---------|---------|
| `base.py` | `LLMProvider`, `Message`, `ToolCall`, `ToolResult`, `Role`, `TokenUsage` | Core types |
| `registry.py` | `register_provider`, `get_provider` | Lazy-loaded provider registry |
| `ollama_provider.py` | `OllamaProvider` | Local Ollama and OpenAI-compatible servers; model selection comes from agent config |
| `openai_provider.py` | `OpenAIProvider` | GPT-4o |
| `anthropic_provider.py` | `AnthropicProvider` | Claude (claude-sonnet-4-6 default) |

Providers are lazy-loaded on first `get_provider(name)` call. Each converts messages/tools to its wire format and back.

### `the_one/mcp/`

| File | Exports | Purpose |
|------|---------|---------|
| `__init__.py` | `MCPClient`, `MCP_DEFAULT_TIMEOUT_SECONDS`, `_PINNED_PROTOCOL_VERSION`, `acquire`, `shutdown_drain`, `MCPClientError`, `MCPConnectionError`, `MCPSandboxError`, `MCPVersionMismatch`, `MCPTool`, `MCPToolResult` | Public surface — re-exports the client class, the lifecycle helpers (`acquire`, `shutdown_drain`), the error hierarchy, and the result dataclasses. `_PINNED_PROTOCOL_VERSION` and `MCP_DEFAULT_TIMEOUT_SECONDS` are read at call time from `the_one.mcp` (NOT bound at module load) so monkeypatching from tests works (see `the_one/mcp/README.md` §5). |
| `client.py` | `MCPClient` | Core client class — `connect`/`disconnect`/`list_tools`/`call_tool`. Uses an owned `AsyncExitStack` for transport composition (see `the_one/mcp/README.md` §3). `disconnect` is idempotent and never raises (cross-task safety net documented in §2). The `_DEFAULT = object()` sentinel preserves "caller passed nothing vs caller passed None" — DO NOT refactor to None-with-default (see `the_one/mcp/README.md` §4). |
| `errors.py` | `MCPClientError`, `MCPConnectionError`, `MCPSandboxError`, `MCPVersionMismatch` | Exception hierarchy. `MCPSandboxError` is canonical here per the project's `canonical-import + convenience-re-export` convention; `the_one.platform.sandbox.__init__` re-exports it for convenience but the canonical import is `from the_one.mcp.errors import MCPSandboxError`. |
| `types.py` | `MCPTool`, `MCPToolResult` | Frozen dataclasses for tool metadata + tool-call results. `MCPToolResult.text` is the agent-facing string; `.raw` is the F7 inspector view; `.structured` is the typed-object form. |
| `transports/stdio.py` | `connect_stdio`, `build_stdio_environ` | Stdio transport context manager (kept as `@asynccontextmanager` per the L1a scope-reduction deviation; see `the_one/mcp/README.md` §3) + the 2-layer flat-merge env-var assembly helper (allowlist + config.env + secrets, secrets win on collision; see `the_one/mcp/README.md` §6). Owns the bwrap stderr capture + translation to `MCPSandboxError` (post-L2 A02 RESOLVED; see `the_one/mcp/README.md` §7). |
| `transports/streamable_http.py` | `connect_streamable_http`, `build_request_headers`, `_test_http_client_override` | Streamable-HTTP transport context manager + headers flat-merge (mirrors stdio's env-var pattern). `_test_http_client_override` is the canonical test seam (3-property contract: underscore prefix + `__all__` exclusion + `# TEST-ONLY` tag; see `the_one/mcp/README.md` §1). |
| `_pool.py` | `acquire`, `shutdown_drain`, `_clear_for_test`, `_RegistryEntry` | Per-`(agent_name, source_id)` worker-task pool of warm `MCPClient` instances (F4). Lazy demand-paged spawn, idle-TTL reap (default 300s, env-tunable via `MCP_POOL_IDLE_TTL_SECONDS`), worker-task-per-entry pattern that satisfies anyio's cross-task `CancelScope.__aexit__` guard mechanically. `shutdown_drain` is wired into FastAPI's `lifespan` shutdown branch in PTY → MCP → DB order (see `the_one/mcp/README.md` §8). |

For the full set of runtime invariants (test-seam pattern, F4-pool-compat invariants, AsyncExitStack pattern, `_DEFAULT` sentinel rationale, `_PINNED_PROTOCOL_VERSION` read-at-call-time invariant, env-var assembly contract, sandbox-wrap composition, F4 pool semantics, cross-references), see `the_one/mcp/README.md`.

### `the_one/tools/`

| File | Exports | Purpose |
|------|---------|---------|
| `base.py` | `Tool`, `ToolRegistry`, `ConstraintError` | Tool ABC (`Config: type[BaseModel]`, `Requires: tuple[type[BaseModel], ...]`, `__init__(config, cross_configs=None, agent_name=None)`, `execute(**kwargs) -> str`); `ConstraintError` exception (F4 L1a — promoted from `filesystem.py` next to the ABC because the two-clause `try/except` envelope IS the tool authorship contract) |
| `provider.py` | `ToolProvider` | Protocol: `name` property + `get_tools(tool_configs=None, agent_overrides=None, agent_name=None)` method |
| `builtins.py` | `BuiltinToolProvider` | Per-agent instantiation of all 19 built-in tools via module-level `_TOOL_CLASSES` (F5 grew the count from F4's 17 by adding `fetch_url` and `download_file`) |
| `resolver.py` | `Narrow`, `NarrowPrefix`, `NarrowSuperset`, `Substitute`, `resolve` | Tool policy resolver — composes tool-level + agent-level configs per per-key marker semantics |
| `shell.py` | `ShellTool` | Arbitrary shell commands (F4: `Config = ExecutionConfig`, `Requires = (FilesystemConfig,)`) |
| `filesystem.py` | `FilesystemConfig`, `ReadFileTool`, `WriteFileTool`, `EditFileTool`, `DeleteFileTool`, `MoveFileTool`, `MkdirTool`, `GlobTool`, `GrepTool`, `ListDirTool` | Per-category Config + 9 file operations (F3 expansion; F4 sets `model_config = ConfigDict(frozen=True)` retroactively) |
| `execution.py` | `ExecutionConfig`, `PythonExecConfig`, `_command_check`, `_cwd_check`, `_truncate_output`, `DEFAULT_COMMAND_DENYLIST` | Per-category execution Config + helpers (F4 L2). `PythonExecConfig` is a subclass with a 90s timeout default for `PythonExecTool`. |
| `python_exec.py` | `PythonExecTool` | Python subprocess execution (F4: `Config = PythonExecConfig`, `Requires = (FilesystemConfig,)`) |
| `sessions.py` | `ShellSessionStartTool`, `ShellSessionSendTool`, `ShellSessionCloseTool`, `ShellSessionListTool` | F4 PTY session tools (per-explicit-handle `session_id` addressing; per-agent isolation; idle reap; per-call denylist re-check on `_send`) |
| `_session_registry.py` | `register`, `get`, `close`, `list_for_agent`, `count_for_agent`, `_clear_for_test` | F4 L5b module-level session registry keyed on `(agent_name, session_id)`; lazy reaper task; FastAPI-lifespan-drained at shutdown |
| `web.py` | `HttpRequestTool`, `FetchUrlTool`, `DownloadFileTool`, `WebSearchTool` | HTTP, structured fetch, file download, and web search (F5: all four migrated to `Config = WebConfig`; the three HTTP tools acquire transport via `_build_transport(self._config) → SSRFGuardedTransport(extra_allowed_hosts=cfg.extra_allowed_hosts)`; `WebSearchTool` reads its backend from `cross_configs[SearchBackend]` (Decision 12) — F5 wires `DDGSearchBackend()` with no injected client, so the backend uses its own `httpx.AsyncClient(timeout=15)`; SSRF-pinning of search-engine traffic is a future enhancement) |
| `_web_config.py` | `WebConfig`, `SSRFGuardedTransport`, `_url_check`, `_host_matches`, `_is_ssrf_blocked`, `_is_binary_content_type`, `_truncate_response` | F5 L1 — single per-category Config + SSRF-pinning transport + URL/host-scope helpers shared by all four web tools |
| `_search_backends.py` | `SearchBackend` (Protocol), `DDGSearchBackend` | F5 L5 — search-engine extensibility seam: a single-method `Protocol` (`async def search(query, limit) -> list[SearchResult]`) plus the default DDG implementation. Future Brave / SerpAPI backends implement the same Protocol and slot in via the `cross_configs[SearchBackend]` service slot wired by `BuiltinToolProvider.get_tools` (Decision 12). |

### `the_one/interfaces/`

| File | Exports | Purpose |
|------|---------|---------|
| `cli.py` | `run()` | Rich + prompt-toolkit REPL |
| `web/app.py` | `app` | FastAPI server with WebSocket sessions |
| `web/middleware.py` | `OriginAllowlistMiddleware`, `_is_safe_origin` | F1 L5 — ASGI middleware gating state-mutating HTTP + WS upgrades by `Origin`/`Referer` against `THE_ONE_ORIGIN_ALLOWLIST` |

Both use `AgentFactory.create()` to get agents. The web app adds session management.

### App.chat helpers

The chat area's pure-helper layer lives at `the_one/interfaces/web/static/js/areas/chat/`. Each file is its own IIFE that attaches functions to `window.App.chat`; `chat.js` (the orchestrator) consumes them via the namespace and owns all closure state. A 3-line `App.markdown = {}` stub at `static/js/markdown.js` is loaded ahead of the chat helpers; flight F4 leg 03 replaces it with the real markdown library.

**Pure** (take inputs, return DOM):

- `App.chat.welcomeLink(text, areaId) → <a>`
- `App.chat.startOfDay(d) → number`
- `App.chat.bucketForSession(s, nowDay) → BucketLabel`
- `App.chat.fmtTokens(n) → string`
- `App.chat.renderMessage(cls, text, opts) → <div.msg>` — `opts.renderMarkdown: bool` is reserved for the markdown integration (leg 05). The flight spec's `(cls, text, attribution, opts)` shape is split into two functions: `renderMessage` (returns the bubble) plus `renderAttribution` (separate label). Leg 05's wire-up calls them as a pair, not as a single combined invocation.
- `App.chat.renderAttribution(side, text) → <div.msg-attribution>` — `side` is `'from-you'` (user) or `'from-agent'` (everything else); caller-determined.
- `App.chat.renderTelemetry() → <div.telemetry-overlay>` — returns the full overlay DOM (`.telemetry-summary`, `.context-bar-wrap` / `.context-bar`, `.t-ctx-pct`, `.telemetry-details`, the three `in:` / `out:` / `ctx:` rows). Built via `document.createElement` calls (not innerHTML) and preserves the F2/F3 `tabindex="0"` / `role="status"` / `aria-label="Token usage"` attributes verbatim.
- `App.chat.updateTelemetry(chromeContent, data)` — mutates the `.t-in` / `.t-out` / `.t-ctx` / `.t-ctx-pct` slots and the `.context-bar` width/class under the chrome content element.
- `App.chat.createThinking() → <div.msg.thinking>` — returns an element that owns its dot-animation interval (`el._dotTimer`); `THINKING_FRAMES` is module-private inside `thinking-indicator.js`.
- `App.chat.removeThinking(el)` — idempotent (no-op on null/undefined); clears the interval and removes the element from its parent.

**Callback-injected** (closure references replaced with explicit callbacks):

- `App.chat.renderWelcomeList(welcomeEl, welcomeListEl, agents, setupState, callbacks)` — `callbacks = { onStart: function(agentName) }`. (No `onLink` — `welcomeLink` returns `<a href>` and the browser handles navigation.)
- `App.chat.renderSessionList(sessionListEl, sessions, currentSessionId, callbacks)` — `callbacks = { onJoin: function(id), onDelete: function(id, btn) }`.
- `App.chat.buildSessionItem(session, currentSessionId, callbacks)` — same callbacks shape.

The orchestrator (`chat.js`) owns closure state — `ws`, `currentSessionId`, `currentAgentName`, `pendingJoinId`, `availableAgents`, `setupState`, the WS lifecycle, the welcome-listbox roving-tabindex keydown handler, and the system-message `Loading model...` / `Model loaded.` flow. It wires WS events to helpers via the callbacks above.

Load order (set in `index.html`): `app.js` → `icons.js` → `markdown.js` → `areas/chat/welcome.js` → `areas/chat/history-buckets.js` → `areas/chat/message-bubble.js` → `areas/chat/telemetry-overlay.js` → `areas/chat/thinking-indicator.js` → `areas/chat.js` → `areas/studio.js` → `areas/admin.js`. Helpers MUST load before `chat.js` because the orchestrator calls `App.chat.renderTelemetry()` synchronously during `init`.

---

## Project Conventions

Four named project-wide patterns canonicalised from F3's debrief (M07). These apply across the codebase, NOT only to `the_one/mcp/`. Each pattern names a recurring decision shape so future authors can apply it consistently and code reviewers can flag deviations by name.

### `trust-the-runtime`

Don't validate at the API layer what the runtime will catch with a clear error. Pre-validation duplicates the runtime's check, introduces TOCTOU windows (the file-system or environment may change between the pre-check and the runtime call), and bloats the surface with branches that exist purely to translate good-enough runtime errors into hand-written API errors.

**Live example**: F3's `BubblewrapSandbox.prepare_spawn` does NOT pre-validate `writable_paths` for existence. bwrap fails at exec time with `Can't find source path`, which L2's stderr-capture-and-translate path converts to a clean `MCPSandboxError` with catalog message #1 (see `CLAUDE.md`'s F3 contracts §5). The runtime's check is authoritative; the API layer trusts it.

**Counter-example (what NOT to do)**: pre-validating `os.path.isdir(path)` on every entry of `writable_paths` inside `prepare_spawn` would (a) duplicate bwrap's check, (b) introduce a TOCTOU window between the check and the bwrap exec (the directory could be deleted in between), and (c) couple the API to the host filesystem at API-construction time, which the strict-by-default trust model deliberately avoids.

The pattern applies whenever the runtime emits a clear, actionable error message that can be matched + translated. It does NOT apply when the runtime's error is opaque (a generic `OSError` with no discriminator), in which case a pre-check + named exception is the right call. The judgment call is: "does the runtime's error carry enough information for a clean translation?" If yes, trust the runtime; if no, pre-check.

### `canonical-import + convenience-re-export`

Each symbol has ONE canonical import path; lower-level packages re-export for convenience. The authoritative path is the canonical one — code that touches the symbol's identity (subclassing, isinstance checks, exception handlers) MUST use the canonical path. Convenience re-exports are for surface ergonomics only.

**Live example**: `MCPSandboxError` is canonical at `the_one.mcp.errors`; `the_one.platform.sandbox.__init__` re-exports it for convenience. The canonical path is `from the_one.mcp.errors import MCPSandboxError`. Inside `the_one/platform/sandbox/`, `from .errors import MCPSandboxError` could be a convenience import, but production code outside the sandbox package uses the canonical `the_one.mcp.errors` path.

**Counter-example (what NOT to do)**: defining `MCPSandboxError` at `the_one.platform.sandbox.errors` AND `the_one.mcp.errors` (two parallel definitions) would mean `isinstance(exc, the_one.mcp.errors.MCPSandboxError)` returns False for an exception raised through the platform path, even though they "look like" the same class. Re-export, never re-define.

The convention also forbids "re-export only" — every symbol has ONE place that defines it (the canonical home) and zero or more re-exports. The canonical home is named after the symbol's primary semantics (errors live with errors, types with types, the `MCPClient` lives in the client module).

### `structural-Protocol-satisfaction`

Classes structurally satisfy `runtime_checkable` Protocols WITHOUT inheriting from them. Inheritance couples the implementation class to the Protocol's identity in a way that is rarely useful (the `runtime_checkable` decorator already gives `isinstance` semantics) and constrains future Protocol evolution (adding a method to the Protocol would force a no-op default in every implementer).

**Live example**: `BubblewrapSandbox` structurally satisfies the `MCPSandbox` Protocol (defined in `the_one.platform.sandbox.base`) but does NOT inherit from it. `runtime_checkable` is what gives `isinstance(BubblewrapSandbox(), MCPSandbox) == True`; the absence of inheritance means future Protocol additions can land with `@runtime_checkable` semantics extended over the existing implementer surface, with no forced default-method propagation.

The pattern decouples implementation from the abstract contract and allows multiple unrelated classes to satisfy the same Protocol — for instance, a future `WindowsSandbox` could satisfy `MCPSandbox` without sharing a base class with `BubblewrapSandbox`. Inheritance would have made that future work lift-and-shift; structural satisfaction makes it net-new with zero retrofit.

**Counter-example (what NOT to do)**: declaring `class BubblewrapSandbox(MCPSandbox):` would couple the two and make Protocol changes a coordinated change across all implementers. The `Protocol` ABC stays a contract; implementers stay independent.

### `verbatim-message-equality`

Error messages are tested via verbatim string equality (or substring `in str(exc)` when the message includes interpolated values), NOT via regex or fuzzy matching. Verbatim equality:

- Pins the exact operator-facing wording, so future authors cannot accidentally rephrase an error message and pass tests with the rewording in place.
- Surfaces typo fixes as deliberate test updates, NOT silent regressions.
- Avoids regex-overkill: the message is a string literal in source; the test asserts on the same literal.

**Live example**: F3 §6 catalog messages (the three `MCPSandboxError` interpolation templates) are checked via `assert str(exc) == expected` for the no-interpolation message and via substring `in str(exc)` for the interpolated forms. The catalog text lives in `CLAUDE.md`'s F3 contracts §5 verbatim; the test asserts on the same verbatim text.

**Counter-example (what NOT to do)**: matching `re.match(r"MCP sandbox setup failed.*writable_paths", str(exc))` would pass even if the message were silently rephrased to `"sandbox setup failed for the writable_paths field"`. Operator-facing wording would drift; the test would not flag it.

The pattern applies only to error messages and other operator-facing strings. It does NOT apply to log messages (which evolve more freely) or to internal debug strings (which are not part of the contract surface).

### `gated-debug-instrumentation`

Debugging-only and measurement-only modules are gated by **both** a URL query-string flag and a `localStorage` key, capture the enabled state at module-load time, and short-circuit to no-ops when disabled. Production paths pay zero cost; the gate survives SPA navigation; activation is achievable both ad-hoc (URL) and persistently (localStorage).

**Live example**: `App.perf` (`the_one/interfaces/web/static/js/perf.js`) — gated by `?perf=1` in the URL query string OR `localStorage.getItem('the-one-perf') === '1'`. The `enabled` flag is captured at module-load time (the file's `isEnabled()` IIFE), and every public method (`mark`, `measure`, `captureHeap`, `dump`, `summary`) short-circuits when disabled. See **Performance Measurement (F7)** below (this file) for full operational mechanics including the activation procedure, browser-support caveats, and the four canonical measurement scenarios that consume the surface.

**Counter-example (what NOT to do)**: compile-time-excluding debug instrumentation via a build flag would break the project's "no build step for vanilla JS" architecture, AND would prevent operators from activating instrumentation on an already-deployed instance for ad-hoc diagnosis. Pre-compiling debug paths out of production also forecloses the "turn it on in production for one incident, turn it off after" workflow that the localStorage gate enables.

The pattern applies whenever a frontend module exists primarily to support diagnosis (perf measurement, debug logging, trace capture, etc.) and is not part of the user-facing feature surface. Future modules following this convention should mirror `App.perf`'s shape: a module-load-time `isEnabled()` gate, public methods that short-circuit when disabled, and one-line activation via either URL or localStorage. The two activation channels are intentional — URL is ad-hoc (no operator commitment), localStorage is sticky (survives reloads, useful for measurement campaigns).

### `live-read-across-lazy-resolver-boundary`

When a provider field is **lazily resolved** on first call (i.e. the field starts as a sentinel — `None`, a default — and is replaced inside the provider's own `complete()` / `stream()` path after a one-time upstream probe), every downstream consumer must read the field **live at the point of use**, not pre-capture it at the entry of a surrounding function. Eager capture sees the pre-resolution sentinel; the resolver fires later inside the provider call, but the captured local is never re-read.

**Live example**: `LLMProvider.max_context_tokens` follows this pattern as of M07 F6.5 (Ollama queries `/api/show` once per model and caches the result on the provider instance). The bug F6.5 L4 found was in `_process_and_broadcast` (`the_one/agent/core.py`) — that function captured `max_context_tokens` into a local at function entry, then looped over the agent's call sequence; the first call's resolver fire never propagated to subsequent iterations of the loop. M07 F7 L05 pins the contract with `test_max_context_tokens_live_read_across_resolver` (in `tests/test_agent_core.py`).

**Pattern**: read `provider.max_context_tokens` at the point of use, not at the start of the surrounding function. If a loop body needs the value, read it inside the loop body, not before the `for`/`while` statement. If a helper function needs it, pass the provider (or the agent that owns the provider), not the pre-captured int.

**Counter-example (what NOT to do)**: capturing the value into a kwarg at the top-level `agent.run()` entry "for performance" — the resolver hasn't fired yet at that point; the kwarg snapshots the sentinel and downstream context-window decisions are made against the wrong number until the agent is reconstructed.

The pattern generalizes to any future field where the upstream value is unknown until a per-model / per-session probe completes (per-model token limits, per-model tool-calling shapes, etc.). The contract is: lazily-resolved fields are owned by the provider and must be read through the provider, never copied across a function boundary.

---

## Dependency Graph

```
config.py ←── llm/ ←──┐
    ↑                  │
    ├──── tools/ ←─────┤
    │                  │
    └── agent/core.py ─┘
            ↑
        agent/factory.py ←── interfaces/ ←── main.py
            ↑
        agent/store.py
        agent/config.py
```

**Rules**:
- Arrows point from dependent → dependency
- `config.py` is the leaf — imported by everything, imports nothing from the project
- `llm/` and `tools/` are peers — neither imports the other
- `agent/` imports from `llm/` and `tools/`
- `interfaces/` imports from `agent/factory.py` only (not core, not store)
- No circular imports anywhere

---

## Key Patterns

### Multi-Agent via AgentFactory

Agents are defined as JSON files in `~/.the-one/agents/` (or rows in the SQLite DB). The factory reads a config, resolves the LLM provider via `provider_config_id` (a reference to `llm_provider_configs` table), wires up filtered tools + prompt, and returns a ready-to-use `Agent`. A "default" agent has `provider_config_id=None` and must be configured through the Admin UI to assign a provider.

### Tool Filtering

`AgentConfig` has `enabled_tools` (whitelist, `null`=all) and `disabled_tools` (blacklist). Filtering happens in the factory — the Agent receives a pre-filtered `ToolRegistry` and never knows about disabled tools.

### Tool Providers

`ToolProvider` is a single-method protocol: `name` property + `get_tools(tool_configs=None, agent_overrides=None, agent_name=None) -> list[Tool]`. `BuiltinToolProvider` provides the 19 built-in tools (F4 grew the count from F3's 13 by adding the four `shell_session_*` tools; F5 grew it from F4's 17 by adding `fetch_url` and `download_file`), instantiated fresh per call (no shared singletons). Future `McpToolProvider` implements the same protocol for MCP server tools.

**Two call paths**: when both `tool_configs` and `agent_overrides` are `None` (introspection — e.g., `/api/tools`, zero-arg tests), each tool is instantiated with its empty default Config. When at least one is supplied (factory path — `AgentFactory.create()`), the provider invokes `the_one.tools.resolver.resolve(...)` per tool, builds a per-call shared `cross_configs: dict[type[BaseModel], BaseModel]` view (F4 L1b — Decision 7), and hands `(resolved_config, cross_configs, agent_name)` into each tool's `__init__`. `agent_name` threads from `AgentFactory.create()` through the provider call so session tools can key their registry on `(agent_name, session_id)` for cross-agent isolation.

### Cross-Config dispatch (F4)

Tools may declare `Requires: tuple[type[BaseModel], ...]` to opt into the shared `cross_configs` view. Used by:
- `ShellTool` and `PythonExecTool` declare `Requires = (FilesystemConfig,)` so cwd validation can call `_cwd_check(target_cwd, fs_cfg)` against the filesystem path-scope.
- `ShellSessionStartTool` and `ShellSessionSendTool` declare the same; `ShellSessionCloseTool` and `ShellSessionListTool` declare `Requires = ()` because they're session-id-only operations.
- `DownloadFileTool` (F5 L4) declares `Requires = (FilesystemConfig,)` so destination-path validation flows through the same `_filesystem_check(path, fs_cfg, CheckMode.WRITE_EXISTING_PARENT)` helper (post-F5 L0 unification — Decision 1) the filesystem write tools use; the parent directory must pre-exist (no auto-mkdir — agents call the `mkdir` tool first if needed). The other two HTTP tools (`HttpRequestTool`, `FetchUrlTool`) declare `Requires = ()` because they don't write to disk; `WebSearchTool` declares `Requires = (SearchBackend,)` to receive its backend from `cross_configs` (Decision 12).

The view is built once per `get_tools()` call by walking `_TOOL_CLASSES` in declared order and resolving each distinct Config class once. Both `ExecutionConfig` and `FilesystemConfig` are `frozen=True` so a tool cannot mutate the shared view to corrupt another tool's read.

### Tool Policy Resolver

`the_one/tools/resolver.py` is a pure function: `resolve(schema, tool_config, agent_override) -> BaseModel`. It composes tool-level config (operator-set defaults persisted in the `tool_configs` SQLite table) with agent-level overrides (`AgentConfig.tool_overrides`) per per-key marker semantics declared on the tool's `Config` schema:

- `Annotated[type, Narrow]` — agent override must not widen the tool value. Per-type comparisons: `bool` (True→False is narrowing), `int`/`float` (lower cap is narrowing), `list`/`tuple` (subset is narrowing). Other types raise `NotImplementedError` — the field author must declare per-tool semantics or use `Substitute`.
- `Annotated[type, NarrowPrefix]` — agent override on a `list[str]` of paths is narrowing iff every agent entry is descendant-of (or equal to) at least one tool entry, checked via `the_one.platform.paths.is_within`. Used by `FilesystemConfig.path_allowlist`. Non-list values raise `NotImplementedError`.
- `Annotated[type, NarrowSuperset]` — agent override on a `list[T]` is narrowing iff every tool entry is also in the agent value (agent ⊇ tool — agent adds restrictions). Used by `FilesystemConfig.path_denylist`. Membership uses raw `==` equality; canonicalization is consumer-side. Non-list values raise `NotImplementedError`.
- `Annotated[type, Substitute]` — agent override replaces the tool value (no comparison). Used for identity / shared-credential / KV fields.

Invoked once at agent build time inside `BuiltinToolProvider.get_tools(...)`; the resolved Config flows into the per-agent tool instance via `Tool.__init__(config, cross_configs, agent_name)` and is held as `self._config`. Session-bound freshness contract (Decision 8): mid-session operator updates apply at the next `AgentFactory.create()` call. F2's seven tools had empty Configs (`Tool.Config = _EmptyConfig`); F3 introduced `FilesystemConfig` (4 fields, used by all 9 filesystem tools); F4 introduced `ExecutionConfig` (6 fields + `default <= max` cross-field invariant, used by all 6 execution tools — `shell`, `python_exec`, and the four `shell_session_*` tools — with `PythonExecConfig` as the 90s-default subclass for `PythonExecTool`); F5 introduced `WebConfig` (timeout + size caps + URL/host scope: `timeout_seconds_default`, `timeout_seconds_max`, `response_size_cap_bytes`, `redirect_cap` (Field-only, no marker — tool-level only), `host_allowlist`, `host_denylist`, `extra_allowed_hosts` — used by all four web tools `http_request`, `fetch_url`, `download_file`, `web_search`).

### Constraint surface

The six **active** constraint types after F5 are:

| Type | Source flight | Config field(s) | Marker(s) | Applies to |
|------|---------------|-----------------|-----------|------------|
| Path scope (allowlist + denylist) | F3 | `FilesystemConfig.path_allowlist`, `path_denylist` | `NarrowPrefix` + `NarrowSuperset` | All 9 filesystem tools + cwd validation in all 6 execution tools (cross-Config dispatch) + `download_file`'s destination check (cross-Config dispatch into filesystem helpers, F5 L4) |
| Read-size cap | F3 | `FilesystemConfig.read_size_cap_bytes`, `allow_binary_files` | `Narrow` (`int`) + `Narrow` (`bool`) | `read_file`, `grep`, indirect via `edit_file` pre-read |
| Output cap | F4 | `ExecutionConfig.output_cap_bytes` | `Narrow` (`int`) | All 6 execution tools (combined stdout+stderr, tail-preserving truncation; default 256 KB) |
| Timeout caps | F4 | `ExecutionConfig.timeout_seconds_default`, `timeout_seconds_max` | `Narrow` (`int`) × 2, plus a `model_validator(mode="after")` cross-field invariant `default <= max` | All 6 execution tools (agent value clipped to `[1, max]`; `default` used when agent omits) |
| Command denylist | F4 | `ExecutionConfig.command_denylist` | `NarrowSuperset` (`list[str]`) | `shell`, `python_exec`, `shell_session_send` (per-call re-check, Decision 11). Substring match with trailing-space convention to avoid the `sudoku` false-positive class. |
| URL/host scope + SSRF | F5 | `WebConfig.timeout_seconds_default` (`Narrow` `int`, default 30s), `timeout_seconds_max` (`Narrow` `int`, default 120s), `response_size_cap_bytes` (`Narrow` `int`, default 1 MiB), `redirect_cap` (`int` — Field-only, NO marker, default 5; agent override raises `ValueError` at agent-build time per Decision 9), `host_allowlist` (`Narrow` `list[str]`), `host_denylist` (`NarrowSuperset` `list[str]`), `extra_allowed_hosts` (`Narrow` `list[str]`) | All four web tools (`http_request`, `fetch_url`, `download_file`, `web_search`). The two-layer enforcement: (1) `_url_check(url, cfg)` — scheme `http(s)` + `host_allowlist` (if non-empty) + `host_denylist` gate at the tool boundary; (2) `SSRFGuardedTransport` — resolves DNS once and pins the connect target to that IP, refusing loopback / link-local / RFC1918 / cloud-metadata / IPv6 ULA + ULL by default. **IP-literal hosts are also gated** by `_is_ssrf_blocked(host)` inside the transport's IP-literal short-circuit branch (HAT scenario 3 inline fix — pre-fix the IP-literal short-circuit bypassed SSRF; post-fix the default-block list refuses raw IP literals BEFORE any connect attempt with `ConstraintError(f"IP literal {host} is in the SSRF block list")`). `extra_allowed_hosts` is the operator override for both the hostname-resolution path and the IP-literal path. A `model_validator(mode="after")` enforces `timeout_seconds_default <= timeout_seconds_max` after resolver dispatch (mirrors the `ExecutionConfig` cross-field invariant from F4). |

**SSRF "no full-disable" mission invariant**: there is intentionally no `disable_ssrf` / `ssrf_disabled` / `disable_ssrf_protection` field on `WebConfig`. SSRF protection is always-on; operators who need to reach a specific internal host must add it to `extra_allowed_hosts` (a host-by-host opt-in), not flip a global kill-switch. The invariant is encoded by the absence of the field — no enforcement code is needed because the field doesn't exist. F5 regression sweep `grep -rn 'disable_ssrf\|ssrf_disabled' the_one/` returns zero hits in source (only documentation comments in `_web_config.py` describing the invariant itself).

PTY-specific knobs `pty_session_idle_ttl_seconds` (default 5min) and `max_concurrent_sessions` (default 5) live on the same `ExecutionConfig` (Narrow ints) so per-tool overrides flow through the same resolver path. They're enforced by the registry + reaper rather than at the tool's `execute` boundary, but they're still operator-tunable via `tool_configs` and agent-narrowable via `tool_overrides`.

### Subprocess environment (F4 invariant)

All three execution call sites — `the_one/platform/shell.py::run_shell`, `the_one/platform/interpreter.py::run_python`, and `the_one/platform/pty.py::UnixPtySession` (fork-then-execv with `os.environ.clear()` + `os.environ.update(_build_subprocess_env())` in the child before `os.execvp`) — pass an explicit subprocess env built from a hardcoded 8-key allowlist:

```
PATH, HOME, USER, LOGNAME, LANG, LC_ALL, TERM, TZ
```

Defined as `_ENV_ALLOWLIST: tuple[str, ...]` in `the_one/platform/env.py` alongside `_build_subprocess_env()`. **NOT operator-configurable** — Decision 10 pins this as part of the F4 trust contract: the agent has no path to read or carry through host secrets via subprocess inheritance. `the_one/tools/execution.py` re-exports both names for backward-compat with L2/L3/L4 tests; `the_one/platform/pty.py` consumes `_build_subprocess_env` directly to avoid a backwards `platform/ → tools/` dependency. The HAT scenario 5 (env-allowlist invariant) verified the agent observes only allowlisted keys at the `env` boundary.

### Threat model — trip-wire, not fence

F4 Decision 3 framing for the `command_denylist`: it is a **trip-wire** that catches obvious-stupid (agent typos, prompt-injection telegraphs in plaintext, the operator's company-specific dangerous patterns). It is **NOT a fence** against adversarial agents — `bash -c "$(echo c3VkbyB3aG9hbWk= | base64 -d)"` is not in the denylist and would not be caught. The trip-wire produces a clean small-model-readable error rather than a destructive side-effect; bypasses are an accepted property because the operator-trust threat model assumes the agent is not actively adversarial. Operators wanting fence-grade isolation should run the agent in a sandbox (container, VM, namespace) and treat the denylist as the inner-defence layer, not the only one. False-positive surface is also accepted: legitimate text containing a denylisted token (`echo "do not run sudo"`) is refused; the workaround is to write the literal through a file (`echo $S > /tmp/x` after setting `S` outside the denylist) — documented in the `shell_session_send` tool description.

### PTY session lifecycle (F4)

PTY sessions ship via `the_one/platform/pty.py::PtySession` ABC (Unix concrete; `UnixPtySession`). On import under `os.name == "nt"` the module raises `NotImplementedError("Windows ConPTY support deferred to a future mission")` — Windows PTY is explicitly out of M05 scope.

**Session addressing** (Decision 4): per-explicit-handle. `shell_session_start` returns a `pty-{12hex}` token; the agent passes that token back into `_send` / `_close`. The four discrete tools (`_start`, `_send`, `_close`, `_list`) replace the action-enum (`shell_session(action="...")`) shape rejected during flight design — discrete tools surface JSON-Schema constraints that the action-enum would not.

**Per-agent isolation**: `the_one/tools/_session_registry.py::_sessions: dict[tuple[str, str], _SessionEntry]` keyed on `(agent_name, session_id)`. Cross-agent `_send` / `_close` returns `[error] [constraint] session 'pty-...' not owned by this agent or does not exist` — the same error shape as a non-existent session, so the agent cannot probe for other agents' session ids. `agent_name=None` (introspection path) raises `ConstraintError("session tools require an agent context")` from a free-function `_require_agent_name(tool)` helper.

**Idle reap** (Decision 5): a single asyncio reaper task spawns lazily on first session registration, wakes every 30s, and closes sessions whose `time.monotonic() - session.last_activity > pty_session_idle_ttl_seconds` (default 5 minutes; Narrow on `ExecutionConfig`). The reaper registers with the FastAPI lifespan (`the_one/interfaces/web/app.py` lifespan context) so shutdown drains the registry cleanly. On `CancelledError`, the reaper closes all live sessions and exits.

**Max concurrent**: `count_for_agent < max_concurrent_sessions` (default 5; Narrow). The L6 leg-spec accepted a documented race — concurrent `_start` calls from a single agent could race past the cap because `(count_for_agent, register)` is not atomic under one lock acquisition. HAT scenario 8 surfaced the **bonus finding** that the registry's internal lock serialized correctly under single-process asyncio, so the documented race did not actually fire even when Haiku 4.5 made 6 parallel `_start` tool calls in one turn. The "accept the race" stance remains conservative; for F6+ HTTP parallelism, the registry can grow a `register_if_under_cap()` helper that does count+insert under one lock acquisition.

**Idle-mark prompt detection**: `UnixPtySession` does NOT scan for shell prompts. Instead, `_read_until_idle` blocks until the master_fd has been silent for 100ms (`_DEFAULT_IDLE_WINDOW`), with a 2s hard cap (`_DEFAULT_IDLE_DEADLINE`). Robust against shells that emit prompts inconsistently (zsh themes, sudo prompt detection, etc.). `start()` blocks on this idle-mark before returning so the agent's first `send` doesn't race with shell init.

**Per-call denylist re-check** (Decision 11): every `_send` runs `_command_check(input, exec_cfg)` BEFORE forwarding to the PTY. Agents cannot pre-stage a denylisted command behind an open session. The same trailing-space convention applies (`"sudo "` denied; `"sudoku"` allowed).

### Web tools (F5)

`WebConfig` (defined exactly once in `the_one/tools/_web_config.py`) is the per-category Config for all four web tools — `http_request`, `fetch_url`, `download_file`, `web_search`. Fields: `timeout_seconds_default: Annotated[int, Narrow]` (default 30s; bounds `[1, 3600]`; used when agent omits `timeout`), `timeout_seconds_max: Annotated[int, Narrow]` (default 120s; bounds `[1, 3600]`; hard ceiling, agent value clipped), `response_size_cap_bytes: Annotated[int, Narrow]` (default 1 MiB; bounds `[1024, 100 MB]`; tail-preserving), `redirect_cap: int = Field(5, ge=0, le=20)` (**Field-only, NO `Annotated` marker** — tool-level only; an agent override on this key raises `ValueError("... no Narrow/Substitute marker ...")` at the resolver per Decision 9), `host_allowlist: Annotated[list[str], Narrow]` (empty = allow-all), `host_denylist: Annotated[list[str], NarrowSuperset]`, `extra_allowed_hosts: Annotated[list[str], Narrow]` (operator-named hosts that bypass the SSRF default-block — host-by-host opt-in for internal addresses). `model_config = ConfigDict(frozen=True)` mirrors `FilesystemConfig` / `ExecutionConfig` so the shared `cross_configs` view cannot be mutated by one tool to corrupt another's read. A `model_validator(mode="after")` enforces `timeout_seconds_default <= timeout_seconds_max` after resolver dispatch (mirrors `ExecutionConfig._default_le_max` from F4 Decision 1).

**Two-layer SSRF enforcement**:
1. `_url_check(url, cfg)` runs at the tool boundary — refuses non-`http(s)` schemes, enforces `host_allowlist` (when non-empty) and `host_denylist`. Failure surfaces as `ConstraintError(f"...")` caught by the tool's outer `[error] [constraint] {e}` envelope.
2. `SSRFGuardedTransport(httpx.AsyncHTTPTransport)` runs at the connect layer — resolves the hostname once via `loop.getaddrinfo`, picks the first public IP, and pins the connect target to that IP via `request.url.copy_with(host=ip)` while preserving the `Host:` header and setting `request.extensions["sni_hostname"]` for TLS validation. The default-block refuses loopback / link-local (`169.254.0.0/16` IPv4 + `fe80::/10` IPv6) / RFC1918 (`10/8`, `172.16/12`, `192.168/16`) / cloud-metadata (`169.254.169.254`) / IPv6 ULA (`fc00::/7`) / IPv6 ULL (`::1`) addresses. **DNS-rebind protection**: the resolve-then-pin strategy means the second-call rebind to a private IP does not reach the connect layer because the URL has already been rewritten to the first call's pinned public IP — a unit test in `tests/test_web_helpers.py` covers this exact scenario.
3. **IP-literal hosts also gated** (HAT scenario 3 inline fix): the transport's IP-literal short-circuit branch consults `_is_ssrf_blocked(original_host)` BEFORE `super().handle_async_request`. Pre-fix the IP-literal short-circuit bypassed SSRF entirely (the original L1 design intended `host_denylist` + tool-level `_url_check` to gate raw IPs, but `host_denylist` is opt-in default-empty and `_url_check` doesn't classify IPs — there was no default-on gate for IP literals). Post-fix the default-block list refuses raw `http://169.254.169.254/`, `http://10.0.0.1/`, `http://127.0.0.1/` etc. with `ConstraintError(f"IP literal {host} is in the SSRF block list")`. `extra_allowed_hosts` is honored as an operator override on both the hostname-resolution path and the IP-literal path (uniform UX). Five regression tests cover the IP-literal SSRF path; the `try/except ValueError` envelope around `ipaddress.ip_address(host)` is preserved (ValueError = "not an IP literal, fall through to resolve+pin"; `ConstraintError` is `Exception`-derived, not `ValueError`, so the SSRF refusal raised inside the IP-literal branch propagates correctly).

**No-full-disable invariant**: `WebConfig` deliberately has no `disable_ssrf` / `ssrf_disabled` / `disable_ssrf_protection` field. SSRF protection is always-on; operators reaching specific internal hosts must list them in `extra_allowed_hosts` (host-by-host opt-in), not flip a global kill-switch. The invariant is encoded by the absence of the field — no enforcement code is needed because the field doesn't exist. The F5 regression sweep `grep -rn 'disable_ssrf\|ssrf_disabled\|disable_ssrf_protection' the_one/` returns zero source-code hits (only documentation comments in `_web_config.py` describing the invariant itself); preserve this property in any future changes.

**Transport acquisition**: each of the three HTTP tools (`http_request`, `fetch_url`, `download_file`) calls a per-tool `_build_transport(cfg) → SSRFGuardedTransport(extra_allowed_hosts=cfg.extra_allowed_hosts)` helper at execute-time and constructs an `httpx.AsyncClient(transport=...)` for the request. `WebSearchTool` does NOT use the SSRF transport — `BuiltinToolProvider.get_tools` constructs `DDGSearchBackend()` with no injected client (`cross_configs[SearchBackend] = DDGSearchBackend()`), so `DDGSearchBackend.search` falls back to its own `httpx.AsyncClient(timeout=15)` per call. F5's accepted posture: `html.duckduckgo.com` is a public domain so search-engine traffic is acceptable as-is; SSRF-pinning of search-backend traffic is a future enhancement once non-DDG backends ship or operator config calls for it.

### Origin allowlist (M06 F1 L5)

`OriginAllowlistMiddleware` (`the_one/interfaces/web/middleware.py`) is an ASGI middleware that gates state-mutating HTTP requests (`POST` / `PUT` / `PATCH` / `DELETE`) and WebSocket upgrades by `Origin` / `Referer` against `THE_ONE_ORIGIN_ALLOWLIST`. Default allowlist is `http://127.0.0.1:*` and `http://localhost:*` — port-wildcard with strict-digits enforcement to reject `http://127.0.0.1.evil.com`-class confusion attacks. Missing-Origin requests pass through (server-to-server clients are NOT browser-originating). WS upgrade gating fires at the ASGI layer with `{"type": "websocket.close", "code": 1008}` BEFORE the route handler can `accept()` — `Depends()` cannot do this because it runs post-`accept()`. Policy and rationale: `SECURITY-MODEL.md`.

### SearchBackend Protocol (F5)

`the_one/tools/_search_backends.py` defines a single-method `Protocol`:

```python
class SearchBackend(Protocol):
    async def search(self, query: str, limit: int) -> list[SearchResult]: ...
```

`SearchResult` is the shared `BaseModel` for shape uniformity across backends (title / url / snippet). `DDGSearchBackend` is the F5 default implementation — its `__init__(http_client: httpx.AsyncClient | None = None)` accepts an optional injected client (allows future SSRF-pinning if needed) but F5 wires it with no client, so `search` falls back to a short-lived `httpx.AsyncClient(timeout=15)` owned by the backend. **Backend dispatch is via `cross_configs[SearchBackend]`** (Decision 12 — Protocol-keyed service entry, NOT a constructor parameter): `WebSearchTool` declares `Requires = (SearchBackend,)` and reads `self._cross_configs[SearchBackend]` at execute-time; `BuiltinToolProvider.get_tools` populates `cross_configs[SearchBackend] = DDGSearchBackend()` once per `get_tools(...)` call. F6 admin will let operators pick the backend by swapping the `cross_configs[SearchBackend]` value. **Tests inject a fake `SearchBackend`** by overriding the `cross_configs[SearchBackend]` entry on the per-call view — no monkeypatching of module internals — which is the supported test seam (Decision 2). Future Brave / SerpAPI / Bing backends implement the same Protocol and slot into the same `cross_configs[SearchBackend]` slot. The Protocol intentionally does NOT include backend-specific configuration (api keys, rate-limit policy) — backends own their own config and read it from `WebConfig` extension fields if they need operator-tunable knobs.

### Built-in tool admin (F6)

Operators manage built-in tool defaults via `Settings → Built-in Tools` in the web UI (route `#admin/tools`). The grid renders the 19 builtins under 3 category tabs (Filesystem / Execution / Web) with one tile per tool — each carrying a category badge, name, prompt, and an enable/disable toggle. `python_exec` is filed under Execution alongside `shell` and the four `shell_session_*` tools (it shares `PythonExecConfig`, a subclass of `ExecutionConfig`). Toggling persists immediately via `PUT /api/tools/configs/{name}` with `{enabled: bool}` (REPLACE-not-merge — omitting `config` preserves the saved row's config).

The per-tool editor (`#admin/tools/{name}`) drives form rendering from `_enrich_schema_with_markers(Config.model_json_schema(), Config)` (`the_one/interfaces/web/api.py:75-115`) which injects `x_marker` per top-level property. Field-widget dispatch lives in `App.adminFormHelpers.renderField` at `the_one/interfaces/web/static/js/areas/admin/tools-form-helpers.js`:

- `bool` → checkbox.
- `int` + `ui_hint=dropdown` + non-empty `ui_choices` → `<select>` of choices.
- `int` (any marker) → `<input type=number min={prop.minimum} max={prop.maximum}>`.
- `array` (list[str]) → chip-list editor (Enter/comma adds, × removes; agent-mode adds NarrowSuperset locked-chip rendering).
- `string` → text input.

The Configuration section's "Enabled for all agents" row uses the same iOS-toggle as the grid tile — visually consistent kill switch. Each field carries an `ⓘ` info icon to the right of the input that surfaces the field's `description` as a hover tooltip; an `// prompt` block in the editor header surfaces the agent-visible tool description.

`web_search` and `fetch_url` editors expose a "Test connection" panel (`POST /api/tools/configs/{name}/test`) with a custom-input field (pre-filled with the fixture default — query `"the one cli agent"` for web_search; URL `"https://example.com/"` for fetch_url) so operators can verify constraints work against arbitrary inputs. The endpoint runs the named tool through `BuiltinToolProvider().get_tools(...)` against the operator's currently-saved Config (named-tool isolation — see `api.py:297-303`) so failed tests surface the agent's view of the refusal directly (`[error] [constraint] ...` rendered in the result `<pre>`, refusal pinned via `output.indexOf('[error]') === 0` heuristic).

### Per-agent tool overrides (F6)

The Studio agent editor's **Built-in Tools** tab surfaces operator state for every tool. (A sibling **MCPs** tab — currently a stub at `static/js/areas/studio/mcps-tab.js` with `data-testid="agent-mcps-tab-stub"` — will host MCP-server attach UI in a future flight.)

- **Operator-disabled tools** render with a strikethrough name + dim row + "Disabled by operator" tooltip + `disabled` HTML attribute on the checkbox. The agent's existing `enabled_tools` / `disabled_tools` on/off state is preserved across operator-disable cycles (HTML `disabled` blocks user toggling but not property reads — `studio.js::collectFormData` walks `.tool-toggle.checked` regardless of disabled state).
- **Per-agent overrides**: each enabled tool with marker-bearing fields gets a collapsible `<details>` panel labeled "Details". On first expand, the panel lazy-fetches `GET /api/tools/configs/{name}` for the marker-enriched schema (the schema fetch is closure-cached — concurrent in-flight callers reuse the same Promise; cache survives across agent changes within the studio area lifetime).

Agent-mode marker dispatch differs from admin mode (operator-mode renders schema's `le`/`ge` as ceilings; agent-mode uses operator's saved value):

- `Narrow` (int) → `<input type=number min={prop.minimum} max={operator_value}>` — operator's saved value as ceiling, schema floor preserved.
- `Narrow` (list[str]) → chip-list constrained to subset of operator's items.
- `NarrowSuperset` (list[str]) → chip-list with operator's items rendered as locked chips (rendered WITHOUT the `<button class="chip-remove">` element entirely — keyboard focus order skips them; screen readers don't announce a remove affordance) plus an input for agent additions.
- `NarrowPrefix` (list[str]) → chip-list (the prefix semantic is server-side validation only).
- `Substitute` → free-form input.
- Unmarked field → HIDDEN from agent override surface entirely (the F2 resolver raises `ValueError("... no Narrow/Substitute marker ...")` on agent override of an unmarked field).

Save propagates through `studio.js::collectFormData`'s `[data-tool-override-tool][data-tool-override-field]` walk, building `tool_overrides: {tool_name: {field: value}}` and dropping empty per-tool entries. Empty top-level → `null` (not `{}`). The shape lands in `AgentConfig.tool_overrides: dict[str, dict[str, Any]] | None` at `the_one/agent/config.py:65` and is validated by the resolver at `AgentFactory.create()` time.

### Dev iteration: source auto-reload

The dev container at `localhost:8484` runs `uvicorn ... --reload --reload-dir /app/the_one` (wired into `docker-compose.yml`'s `command:`). Edits to any file under `./the_one/` on the host trigger a graceful uvicorn worker restart within ~1s — no manual `docker compose restart` needed.

To verify the reload fired, watch the container logs:

```bash
docker logs --tail 20 the-one
# WARNING:  WatchFiles detected changes in 'the_one/<file>'. Reloading...
# INFO:     Started server process [<new-pid>]
```

`./tests/` is also bind-mounted but **not** watched by `--reload-dir` — test edits don't bounce the server (avoids noise). Run tests with `docker exec the-one pytest ...`; fresh Python interpreters always see the latest test code.

**Historical note** — surfaced during F4 L7 HAT scenario 1, the timeout-cap clip from L3-L4 was not engaging through the chat API because uvicorn had cached the pre-L3 imports. Pre-fix the workaround was `docker compose restart the-one`; post-fix the reload is automatic.

### Continue Signal

A virtual tool (`CONTINUE_SCHEMA`, defined inline in `core.py`) that the LLM calls to indicate it needs another iteration. Not a real tool — the agent loop intercepts it and loops.

**Capability gate**: `Agent.step()` consults `LLMProvider.supports_tools()` once per turn. When the provider reports tools as unsupported (e.g. Ollama Gemma — `/api/show` capabilities lack `"tools"`), the agent drops EVERYTHING from the wire payload — both real tool schemas AND the virtual `CONTINUE_SCHEMA` — and runs a single LLM iteration as plain chat. No exception is raised; Studio's red `no tools` capability chip on the model selector is the only operator-facing signal that the agent will run in single-shot mode (silent fallback was deliberately chosen over refusing the user's message at send time). See "Model capability surface" below.

### Model capability surface

Surfaces per-model capability data from Ollama's `/api/show` end-to-end so operators can see at a glance which models support tool calling — without us having to maintain an allowlist.

**Provider-side hook** — `LLMProvider.supports_tools()` (`base.py`) is an async method, default `True` for cloud providers (OpenAI, Anthropic, mock). `OllamaProvider.supports_tools()` overrides via `ollama_api.get_model_capabilities(base_url, model)`, which:
- Fetches `/api/show` for the model and reads the `capabilities` array.
- Caches per `(base_url, model)` with a 5-minute TTL (`_capabilities_cache` in `ollama_api.py`).
- Returns `frozenset[str] | None`. `None` means "couldn't determine" (network blip, model missing) — the agent treats that as `True` (fall through, trust the provider, surface any error via the improved 400-body diagnostic in `chat_stream` / `complete()`).

**API enrichment** — `GET /api/providers/{id}/models` (`api.py:list_provider_models`) async-gathers per-model `/api/show` capabilities for Ollama providers and returns a `capabilities: list[str] | null` field on each model dict. Other provider types (OpenAI, Anthropic, openai-compatible) return models without the field. Failures are non-fatal: a single model's capability fetch failing degrades to `null`, the rest of the list still renders.

**Library search empty-q semantics** — `GET /api/ollama-library/search` returns the FULL alphabetical library (capped at 500) when `q=""`, used by the Studio Pull Model dropdown to populate without a typeahead. Non-empty `q` keeps the legacy substring filter (capped at 30).

**Shared chip helper** — `App.admin.renderCapabilityChips(caps)` in `static/js/areas/admin/provider-models.js` renders the canonical `.cap-chip-row` element: each capability becomes a grey `.chip.cap-chip`; absence of `"tools"` adds a red `.chip.cap-chip.cap-chip-no-tools` chip with a tooltip. Returns `''` for null/empty caps so callers can append unconditionally.

**Three consumer surfaces**:
- **LLM Providers admin grid** (`provider-models.js`) — chips next to each model row in both Running and Available sections. The Running section sources caps from a `capsBy[name]` lookup built from `/models` (which carries them) since `/models/status` doesn't.
- **Studio agent tile grid** (`studio.js renderAgentList`) — chips below the provider · model meta line, sourced from `self._modelCapsByProvider` (populated by `fetchProviderModelCaps` during `loadAll`, only fetches Ollama-typed providers).
- **Studio agent editor model selector** (`studio.js renderModelCapabilities`) — chips under the model dropdown, refresh on `change`. Caps stored in `modelCapsBy` closure populated by `fetchModelsForProvider`.

**Deliberately NOT enriched** — the Pull Model dropdown options. Ollama's library `/api/tags` doesn't carry capabilities, so populating chips per option would mean an N×`/api/show` round-trip per dropdown open. Easy to revisit if the cost trade-off changes.

**CSS** — `.cap-chip-row` (display: inline-flex), `.cap-chip` (small uppercase chip), `.cap-chip-no-tools` (danger palette + `cursor: help` for the tooltip) live in `admin.css`. `.field-info-icon` button reset is un-scoped in `components.css` so the same form-helper module renders cleanly under both admin and Studio.

### Test conventions and schema metadata

Tests monkeypatch built-in tool registration via
`the_one.tools.builtins._TOOL_CLASSES` (module-level dict) — this is the
supported seam; do NOT reach into `BuiltinToolProvider` internals.
See `tests/CONVENTIONS.md` for the four established test patterns
(asyncio_mode auto, monkeypatch.setenv HOME for tilde-expansion tests,
httpx MockTransport `_install_mock` recursion-avoidance, kill+reap
timeout-budget assertions).

Pydantic Config schemas may declare UI-presentation hints via
`Field(json_schema_extra={"ui_hint": "...", "ui_choices": [...]})`
so the F6 admin form generator (`App.adminFormHelpers.renderField` at
`the_one/interfaces/web/static/js/areas/admin/tools-form-helpers.js`)
renders finite-set fields (e.g., read-size cap, redirect cap) as
dropdowns rather than free-form numeric inputs. F6 also added
server-side `_enrich_schema_with_markers` (`api.py:75-115`) which
injects `x_marker` per property so the renderer can dispatch on
marker class — admin and Studio share the same renderer with
mode-specific widget shapes (see "Built-in tool admin (F6)" and
"Per-agent tool overrides (F6)" entries above). The convention
introduced in F3 Decision 11:
`ui_hint` is the rendering strategy ("dropdown", future: "slider",
"toggle"); `ui_choices` is a list of `{"value": ..., "label": ...}`
dicts. F4-F6 should reuse the same metadata keys for any
finite-value configuration field.

---

## Browser test fixtures

Browser tests live in `tests/browser/` (with fixtures in `tests/browser/conftest.py` and seeders in `tests/browser/seeders.py`) and use Playwright (Python binding) to drive a real Chromium session against a per-test app subprocess. Three layered fixtures:

| Fixture | Setup | Use for |
|---------|-------|---------|
| `app_clean` | Fresh subprocess + empty DB + `THE_ONE_DEV_MODE=true` | First-start / setup-flow tests |
| `app_with_provider` | + 1 mock provider seeded via API | Agent CRUD tests |
| `app_with_agent` | + 1 agent referencing the mock provider | Chat tests |

Each test gets its own subprocess on a random port (via `socket.bind(('', 0))`) with an isolated `tmp_path` data_dir. Teardown sends SIGTERM, escalates to SIGKILL after 10s if needed. Browser navigates to `http://127.0.0.1:{port}` (not `localhost`) to avoid IPv6 first-attempt delay on WSL2.

**Playwright fixtures (`playwright_instance`, `browser`) are module-scoped, NOT session-scoped.** Originally session-scoped during F1 leg 03 design; switched to module scope during implementation because session scope kept the asyncio loop alive across modules and broke the leg-01 standalone smoke test (`test_smoke.py` creates its own `sync_playwright()` context). Module scope still amortizes Chromium across tests within the same module while keeping the standalone smoke test green.

The `mock` provider type (production code, dev-mode-gated) provides deterministic LLM responses without external services — see "Provider type extension checklist" below for the full type wiring.

Tests rely on `data-testid` attributes on load-bearing UI elements rather than CSS classes, so the tests survive UI redesigns. Each flow leg adds 3-5 testids on a budget.

### Pytest markers and what runs where

| Marker | Tests | Default `pytest` | CI |
|---|---|---|---|
| (no marker) | unit tests | runs | runs |
| `live` | hits real LLM APIs (paid) | skipped | skipped |
| `browser` | Playwright **functional** flow tests | skipped (run with `-m browser`) | runs `-m browser` |
| `pixel` | Playwright **visual** snapshot regression | skipped (run with `-m pixel`) | **never runs** |

Default `addopts` deselects `live`, `browser`, AND `pixel` so a bare `pytest` runs only unit tests. Override at the CLI to opt in: `pytest -m browser`, `pytest -m pixel`, or `pytest -m "browser or pixel"`.

### Visual snapshot workflow (local-only)

Snapshot baselines under `tests/browser/__snapshots__/` are **gitignored** — they are local regression artifacts, not shared source. The flow:

1. **First run on a fresh checkout**: `pytest -m pixel --snapshot-update` (or `UPDATE_SNAPSHOTS=1 pytest -m pixel`). The helper writes a baseline PNG for each scenario (3 areas × 2 states × 2 themes = 12 baselines). Missing-baseline auto-generation also kicks in on a bare `pytest -m pixel` first run, but `--snapshot-update` is the explicit affordance.
2. **Subsequent runs**: `pytest -m pixel`. Each test compares its current screenshot against the locally-stored baseline; >2% pixel diff fails and writes `<name>-actual.png` + `<name>-diff.png` next to the baseline for inspection.
3. **After an intentional layout change**: `pytest -m pixel --snapshot-update` to regenerate.
4. **CI**: never runs `-m pixel`. Functional Playwright coverage is provided by `-m browser`. The pixel suite has no shared baselines to compare against in CI by design — pixel diffs are a developer's local feedback loop, not a regression gate.

If the visual-snapshot suite ever needs CI-side regression detection, the right move is to capture a fresh baseline on each run, store it as a build artifact, and compare against the previous successful build's artifact — not to commit baselines to git.

---

## Design system

The web UI uses a token-driven design system (mission M04 / flight F2). Both
themes (`[data-theme="dark"]` and `[data-theme="light"]`) live in
`the_one/interfaces/web/static/css/tokens.css` and share token names; only
values differ per theme. Component CSS files reference tokens — no hex/rgba
literals leak into component rules (enforced by a grep gate in CI; only
`tokens.css`, `fonts.css`, and SVG `data:` URLs may contain literals).

### Affordance patterns

The interface uses six recurring affordance patterns. Each is identifiable by its visual treatment and intended interaction class. New UI work should compose with these patterns rather than invent parallel idioms. Where the live UI diverges from these descriptions today, the divergence is pre-realization debt to be resolved during the per-area alignment flights (F4 Chat / F5 Studio / F6 Administration).

1. **Info banner** — neutral disclosure inside a surface. Documented pattern: background `var(--surface-elevated)`, border `1px solid var(--border)`, text `var(--fg-secondary)`. Live UI today: `.admin-note` uses `var(--surface)` and the `.chat-no-providers` banner uses a primary-accented gradient — both are pre-realization variants. Used at the top of provider lists, agent editors, and admin sub-pages to surface non-actionable context.

2. **Outlined primary** — secondary action; reads as available but de-emphasized. Pattern: background transparent, border `1px solid var(--accent)`, text `var(--accent)`, hover background `var(--accent-translucent)`. Live UI today: `.new-chat` (chat sidebar's "+ new" button), `.new-entity-btn` (studio + admin page-headers, F6 leg 02 lift from `.new-agent-btn`). Future use: "edit", "configure", and similar non-CTA actions across all areas.

3. **Filled primary CTA** — primary action; reads as the recommended next step. Pattern: background `var(--accent)`, text `var(--fg-on-accent)`, hover via `filter: brightness(1.1)` or explicit hover token. Used for "save", "submit", "create" — one CTA per page is the convention.

4. **Muted-default-then-glow destructive** — irreversible action; reads as recessive at idle, glows on focus/confirm. Pattern: transparent background at idle, text/border `var(--status-danger-muted)`. Confirm state (after first click): background `var(--status-danger)`, text `var(--fg-on-danger)`, glow `var(--status-danger-glow)`. Used for delete affordances on session items, agent items, chip-removes. Never used for routine actions.

5. **Neutral utility** — small, non-categorical action with no surrounding chrome. Pattern: background transparent, text `var(--fg-secondary)`, hover text `var(--fg)`, no border. Examples: inline `x` icon buttons, dropdown-chevron indicators, decorative scroll affordances. NOT for "+ new" buttons (those are outlined-primary, pattern 2).

6. **Palette-island rule** — components that establish their own chrome (the `#app-topbar` post-F3) declare their own `--nav-*` palette family in `tokens.css`. The body palette and the chrome palette MUST NOT share token names. Rule: never reach into chrome tokens from body components or vice versa. (The `--nav-*` token-family name is retained for continuity even though F3 replaced the original left nav rail with the topbar app-picker; the rule applies to chrome surfaces generally, not to a specific layout.)

#### Affordance vocabulary (shared class catalog)

The F4 leg 02 lift consolidates per-area duplications into shared primitives in `components.css`. Templates compose the shared class with the legacy area-specific class so existing test selectors and styling hooks keep working.

**Shared class catalog** (in `components.css` `@layer components`):
- `.list-item` + `.list-item-delete` — sidebar/category list rows with a focus-within-revealed inline delete affordance. Used in chat (`.session-item`), studio (`.agent-item`), admin (`.admin-category-item`).
- `.field-row` + `.field-input` + `.field-textarea` + `.field-select` — editable form rows with label + input. Used in studio (agent editor) and admin (provider form).
- `.section-title` (with `// PREFIX` `::before`) — section headers in editor / form contexts.
- `.btn-outlined-primary` — secondary affordance buttons (transparent + 1px solid accent border).
- `.btn-filled-primary` — primary CTAs (accent fill + glow).
- `.btn-muted-destructive` — delete-confirm-style buttons (muted danger color until hover).
- `.chip` + `.chip-remove` — tag-like rows (currently studio-only; lifted for vocabulary completeness).
- `.empty-state` — small inline empty-list messaging (per-tab / per-row contexts: per-tab "No tools" inside admin's Tools tabpanels, model-list "No models found" inside provider editors, agent-editor stub tabs, etc.). For PAGE-level empty states (LLM Providers, Studio Agents, Knowledge stub, Tools stub), use `.empty-canvas` (next entry).
- `.empty-canvas` + `.empty-canvas-inner` — page-level centered empty state. Mirrors `.chat-welcome`'s flex-1 vertical centering; the canvas takes the remaining vertical space below `.page-header` and centers a max-520px inner block. Used by LLM Providers grid (when no providers configured), Studio Agents grid (when no agents created), Knowledge stub, Tools stub. **`.entity-tile-grid:has(> .empty-canvas)`** override switches the grid container to flex layout when its sole child is an empty canvas, so the canvas can claim full grid area instead of being a single CSS-grid cell. Existing test hooks (`agent-empty`, `admin-provider-empty`, etc.) are preserved as inner-element classes for browser-test selector continuity.
- `.entity-tile` + `.entity-tile-name` + `.entity-tile-description` + `.entity-tile-meta` + `.entity-tile-badge` + `.entity-tile-grid` — CSS-grid tile primitive for area inventories. **Renamed from `.agent-tile` family in F6 leg 02** (no composition aliases retained — breaking rename). Two consumers: studio's agent inventory (`<button class="entity-tile agent-item">...</button>` per agent — composes the legacy `.agent-item` class for selector continuity) and admin's provider inventory (`<button class="entity-tile provider-tile">...</button>`). DOM: tile is a single `<button>` (no wrap-with-siblings sibling-X pattern — F5 HAT removed the per-tile X delete in favor of editor-only Danger Zone deletion). Tile content slots: `.entity-tile-name` (large bold), `.entity-tile-description` (2-line clamp; studio uses it for agent description), `.entity-tile-meta` (monospace, smaller, muted; studio uses "{provider} · {model}", admin uses base_url snippet or "—"), `.entity-tile-badge` (top-right absolute-positioned slot for type badges; admin uses for provider type — composes with admin's per-type color rules `.admin-provider-badge--{type}`). Test-attribute placement: `data-testid` (e.g. `agent-item`, `provider-card`), `data-id` / `data-name`, `aria-selected="true|false"` on the tile button. ARIA: grid container uses `role="listbox"`; tiles use `role="option"`. `.entity-tile-grid` is the canonical CSS-grid layout (`grid-template-columns: repeat(auto-fill, minmax(280px, 1fr))`) — un-area-scoped and consumed by both areas. Tile delete is NOT a per-tile affordance — clicking a tile navigates to its editor; deletion lives in the editor's Danger Zone (see `.danger-zone` entry below).
- **Confirm-delete (in-place two-step)** — `App.confirmDelete(itemEl, onConfirm, opts?)` in `static/js/confirm.js` (F5 leg 02). The single canonical helper for two-step destructive confirms: first call adds `.confirm-delete` to `itemEl`, swaps the title text (`opts.titleSelector`, default `[data-confirm-title]`) to `opts.confirmLabel` (default `'Confirm delete?'`), starts an `opts.revertMs` (default 3000) timer that restores the original on expiry. Second call within the timer window invokes `onConfirm(itemEl, revertFn)` — the helper passes `revertFn` so transport-failure callers can roll the UI back. Original-title capture happens ONLY in the first-click branch and is stored on `itemEl._confirmOriginalTitle` (capturing on every call would record the placeholder text on the second click, and a subsequent revert would overwrite the user's data). Title-element hook: callers add `<span data-confirm-title>` around the visible label text. **Four permanent consumers** post-F6: chat session items (`.session-item` parent, `.session-item-title` inner — uses default selector via title's data-attribute), studio agent editor's `Delete Agent` (`<button class="btn-muted-destructive delete-btn"><span data-confirm-title>Delete Agent</span></button>` — F6 leg 04 migration from inline two-step), admin's provider editor `Delete Provider` (`<button class="btn-muted-destructive delete-btn"><span data-confirm-title>Delete Provider</span></button>` — F6 leg 04), admin's system-page `Rotate Encryption Key` (F6 HAT migration; uses `confirmLabel: 'Confirm Rotate?'`). All editor consumers pass `confirmLabel: 'Confirm Delete?'` (capital-D) for label parity. Canonical armed-state class is `.confirm-delete` (NOT `.confirm` — F6 leg 04 rename); CSS rules at `components.css` cover both `.list-item.confirm-delete` (chat sidebar) and `.delete-btn.confirm-delete` (editor buttons). **Keydown-bubble guard is the parent activatable element's responsibility, NOT the helper's** — the parent applies `if (e.target !== el) return;` in its keydown listener so descendant focusable children don't bubble to fire the parent's activation. **The agent-tile per-tile X-button is gone** — F5 HAT removed it; deletion is centralized to the editor's Danger Zone. **Hard-block precedes confirm**: when the action would orphan related entities (admin's provider-with-active-agents), surface a sibling `.action-blocked-message` banner BEFORE invoking the helper (see "Action-blocked message" entry below); the confirm flow only runs when the action is safe.
- `.section-nav` + `.section-nav-header` + `.section-nav-item` — sidebar sub-section navigation. Vertical list of `<button class="section-nav-item">` elements representing in-area sections. The container uses `role="group"` (NOT `role="tablist"` — these sections have side-effects like URL change and content rerender, and are persistent destinations rather than tab-like alternative views of the same data). The "active" button carries `aria-current="page"` AND `tabindex="0"`; the others carry `tabindex="-1"` (roving tabindex, single-tabstop into the group). Keyboard contract: Tab into the group lands on the active button; Up/Down arrows move focus between buttons (wrapping); Home/End jump to first/last; Enter or Space (or click) commits — fires the `onSelect(sectionId)` callback. **Manual activation**: arrow-key navigation moves focus only; activation requires Enter/Space/click. Two consumers: studio's Agents/Knowledge/Tools sidebar (F5 leg 01) and admin's General/LLM Providers/Built-in Tools sidebar (F6 leg 01 migration from `.admin-category-item`; section was originally labeled "System", later renamed — id stays `system`). Helpers: **`App.layout.renderSectionNav(container, items, active, {onSelect, header, ariaLabel})` + `App.layout.updateActiveSection(container, active)`** in `static/js/areas/layout/section-nav.js` (lifted from `App.studio.*` namespace in F6 leg 01 to the area-agnostic `App.layout.*` so admin can consume the same helper). Each consumer passes its own `items` array + `header` text + `ariaLabel` — no values hardcoded in the helper. **Single-mount-per-container contract**: the helper sets `className` on the passed container, so callers MUST pass a child element (e.g., `<div class="admin-section-nav">`) rather than the area panel itself, otherwise the area scoping class (`.area-admin` / `.area-studio`) gets clobbered. **Section nav vs. tablist distinction (F5 leg 03)**: section navigation (this entry) is for *persistent destinations* — sections occupy distinct URL spaces (`#studio/agents`, `#studio/knowledge`, `#studio/tools`) and have side-effects like content rerender. The tab idiom (next entry) is for *within-entity views* — tabs are alternative facets of the same entity (the agent editor's General/Knowledge/Tools tabs all describe the same agent under `#studio/agents/{name}/{tab}`). Section nav uses `role="group"` with arrow-key roving focus; the tab idiom uses `role="tablist"` with arrow-key roving focus AND manual activation. Don't confuse the two — section nav inside the editor would be wrong (sections are persistent destinations, not within-entity views), and tablist for the sidebar would be wrong (each section has its own URL and its own data, not a different facet of the same data).
- **Tab idiom** — `.tablist` + `.tab` + `.tabpanel` (F5 leg 03). The codebase's first canonical tab vocabulary, established for the studio agent editor's General / Knowledge / MCPs / Built-in Tools tabs. DOM shape: `<div role="tablist" class="tablist" aria-label="...">` containing `<button role="tab" class="tab" aria-controls="<panel-id>" data-tab-id="<short-id>" aria-selected="true|false" tabindex="0|-1">` elements, followed by `<div role="tabpanel" class="tabpanel" id="<panel-id>" data-tab-id="<short-id>" hidden>` panels. Only one panel is unhidden at a time (`[hidden]` controls visibility via `display: none`). **Manual activation contract** (W3C ARIA Authoring Practices for tabs whose activation has side effects): Arrow Left/Right and Home/End move focus + visual highlight ONLY — the URL does not mutate, `aria-selected` does not toggle, panel visibility stays put. Enter or Space (or click) on the focused tab commits — fires `onChange(tabId)`, swaps `[hidden]` on panels, updates `aria-selected` and roving `tabindex`. **Roving tabindex**: only the active tab carries `tabindex="0"`; the others carry `tabindex="-1"` (excluded from natural Tab order, but `.focus()` calls still land on them — that's how arrow-key navigation moves focus between tabs without losing the roving-tabindex contract). Roving tabindex updates only on activation, not on arrow nav. Helper: `App.tabs(tablistEl, panelsEl, {onChange, initial})` in `static/js/tabs.js` returns `{activate(tabId), getActive()}` for imperative control. Tab/panel id resolution prefers the short `data-tab-id` over `aria-controls` / `id` so callers can pass logical ids (`'general'`) without leaking DOM-id details. Why manual (not auto-on-arrow) activation: arrow-key auto-activation would mutate the URL on every keypress (Right arrow rotates through three URL states), polluting browser history even with `replaceState` and aligning poorly with screen-reader exploration patterns. Consumed in F5 leg 03 by the agent editor; future tabbed surfaces (admin's provider editor in F6 if needed) inherit the helper ready-to-use.
- **Editor header** — `.editor-header` + `.editor-header-text` + `.editor-title` + `.editor-subtitle` (F5 leg 03). Canonical entity-name + description block above an editor's tablist (or other content). Two consumers: studio's agent editor + admin's provider editor (F6 leg 03 — provider-editor.js consumes; title shows provider name, subtitle shows `{type} · {base_url}` in edit mode, omitted in create mode). DOM shape: `<div class="editor-header"><div class="editor-header-text"><h1 class="editor-title">{name}</h1><p class="editor-subtitle">{description}</p></div><div class="form-actions">...action cluster...</div></div>`. Flex layout — name/description on the left flex, action cluster on the right; bottom-border separator; padding 12px 20px. Designed to compose with `.form-actions` for the right-aligned button cluster.
- **Form actions** — `.form-actions` (F5 leg 03). Right-aligned button cluster. Used by the agent editor's `[← Back] [Delete] [Save] <error>` cluster inside `.editor-header`; reusable for future modal `.modal-actions` composition (F5 leg 04 will land `.modal-overlay` + `.modal-dialog` + `.modal-actions` for `App.confirmDialog`, where `.modal-actions` composes onto `.form-actions` since both are right-aligned button rows). Includes a `.editor-error` selector inside the cluster for inline error text. Designed to be theme- and area-agnostic; per-area button cosmetics (`.btn-filled-primary`, `.btn-outlined-primary`, `.btn-muted-destructive`) compose onto the cluster's children.
- **Test result** — `.test-result` + `.test-result-pending` + `.test-result-ok` + `.test-result-fail` (F5 leg 03 + F6 leg 03 `-pending` addition). Canonical span for connectivity-test results, used by studio's agent editor General-tab Test button + admin's provider editor Connection-section Test button (F6 leg 03 migration from `.admin-pf-test-*`). Pattern: container `<div class="test-result" aria-live="polite">`; in-flight content `<span class="test-result-pending">Testing…</span>`; success `<span class="test-result-ok">✓ {detail}</span>`; failure `<span class="test-result-fail">✗ {detail}</span>`. Status modifiers use the existing `--status-success` / `--status-danger` / `--fg-secondary` design tokens. Generic by design — area-agnostic. Pairs with the JS pattern: read the LIVE provider-select form value (NOT the persisted config) to support unsaved provider changes; surface a flash via `App.showFlash(container, detail, isError)`.
- **Confirm dialog (modal)** — `.modal-overlay` + `.modal-dialog` + `.modal-actions` (F5 leg 04). Canonical modal-blocking-decision primitive, paired with `App.confirmDialog({title, message, confirmText, cancelText, onConfirm, onCancel})` in `static/js/dialog.js`. DOM shape: `<div class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="<title-id>" aria-describedby="<message-id>"><div class="modal-dialog"><h2 class="modal-dialog-title">…</h2><p class="modal-dialog-message">…</p><div class="modal-actions form-actions">[Cancel][Confirm]</div></div></div>`. **`.modal-actions` composes onto `.form-actions`** via multi-class on the container (`class="modal-actions form-actions"`) so the existing `.form-actions` right-aligned layout applies; the `.modal-actions` class itself is currently a documentation/grep alias with no extra rules — the composition pattern is documented here so future modals are unambiguous about which side carries layout. **Defaults**: `title='Unsaved changes'`, `message='You have unsaved changes. Continue without saving?'`, `confirmText='Continue'`, `cancelText='Stay'`. The wording avoids the false-promise of "Discard" — the helper navigates without auto-reverting form state, so "Continue/Stay" reads more accurately than "Discard/Cancel". **Keyboard contract**: Escape calls `onCancel` then closes; Enter calls `onConfirm` then closes (skipped when focus is in a `<textarea>` so newline insertion still works); Tab and Shift-Tab implement a **full focus-trap** — focus cycles within the dialog's focusable descendants and wraps at both ends. **Restore-focus on close**: helper captures `document.activeElement` on open and refocuses it on close; if the trigger was removed from the DOM (e.g., a deleted tile), `.focus()` falls back to body. **Singleton**: only one dialog is open at a time; second `App.confirmDialog` call while one is open is a no-op + `console.warn('App.confirmDialog: already open; second call ignored.')` — surfaces spurious double-dispatch in dev/test. **Click-on-overlay is a deliberate no-op** (does NOT call `onCancel`); requires explicit Cancel/Escape. Prevents accidental dismissal from a stray outside-click. **Capture-phase keydown** (`document.addEventListener('keydown', ..., true)`) so the modal sees keys before any focused-field listener can swallow them. **Distinct from `App.confirmDelete`** — `confirmDelete` is the in-place two-step destructive confirm (single action, single agent/session); `confirmDialog` is the blocking modal for multi-option / unsaved-changes decisions. **Editor Danger-Zone delete on a dirty entity does NOT layer this dialog** — the Danger-Zone delete is itself a two-step destructive confirm (capital-D "Confirm Delete?" inline two-step in studio's agent editor, `App.confirmDelete` with `confirmLabel: 'Confirm Delete?'` in admin's provider editor); layering an additional "you have unsaved changes" modal on top is UX clutter (the user is opting into a destructive action that obviously discards everything about that entity, including unsaved edits). Deliberate non-gate. Historical note: pre-F5-HAT, the same rationale applied to the per-tile X-button delete; F5 HAT removed the X-button affordance and centralized destruction to the editor's Danger Zone. Consumers (F5 leg 04): studio's `selectAgent`, `enterCreateMode`, `handleBack`, section-nav `onSelect` (only when in agents+selected-agent context), and tab `onBeforeChange` (via the `App.tabs` helper's new `onBeforeChange(tabId, commit)` hook that wraps both click and Enter/Space activation). Future use: any blocking decision modal across all areas.
- **Beforeunload guard** — register-once-in-area-init pattern (F5 leg 04 + F6 leg 04). Two consumer areas: studio + admin. Each registers a single `window.addEventListener('beforeunload', …)` listener at its own `init()` time, gated by its closure `dirty` flag. **Critical**: `init()` runs once per area lifetime (gated by `app.js`'s `initialized[areaId]` check), but `activate()` and `deactivate()` run on every cross-area transition. **Do NOT remove the listener on `deactivate()`** — that would silently break tab-close protection after cross-area round-trips. The closure `dirty` flag handles all cases: when in another area, dirty is `false` because the editor isn't mounted; when in the area with unsaved changes, dirty is `true` and the listener fires `e.preventDefault(); e.returnValue = ''`. **Modern browsers ignore the custom `returnValue` string** and show a generic "Leave site?" dialog. **Multi-area listener safety**: studio + admin each register their own listener; both fire independently on every `beforeunload`; the closure-flag short-circuit makes each a no-op when its own area is clean. **Test pattern**: Playwright's headless Chromium suppresses the native dialog, so dispatch a synthetic `beforeunload` event via `page.evaluate` and inspect `event.defaultPrevented`. **For admin specifically (F6 leg 04)**: the dirty flag lives in admin's orchestrator closure (`admin.js init()`), bridged from the editor sub-module's local flag via the `onDirtyChange(d)` callback the orchestrator passes into `App.admin.renderProviderEditor`. The orchestrator's mirror is the source of truth for navigation gates; the editor sub-module's local flag drives the disabled-button SSoT.

- **Page header** — `.page-header` + `.page-title` + `.new-entity-btn` (F6 leg 02 lift from studio's `.studio-page-header` family; breaking rename, no aliases). Top-of-area-content header bar: title on the left, the new-entity affordance sits inline next to it. Pattern: `<div class="page-header"><h1 class="page-title">{Label}</h1><button class="new-entity-btn" data-testid="new-{entity}-btn">{icon} <span>New {Entity}</span></button></div>`. Five consumers post-F6: studio Agents/Knowledge/Tools page-headers (3) + admin LLM Providers + admin General. The `square-pen` icon is the canonical choice (`App.icon('square-pen')`). **Hover-expand behaviour**: `.new-entity-btn` renders icon-only at rest (no border, transparent background) and expands to the full pill on hover/focus via a CSS `max-width` + `padding` transition with the `<span>` opacity fading in over the same window. **Empty-state CTA modifier** — `.new-entity-btn.is-expanded` is the always-expanded variant rendered inside `.empty-canvas-inner`, used as the centered call-to-action below the empty-state message. The header CTA hides itself via `.page-header:has(+ .entity-tile-grid > .empty-canvas) .new-entity-btn` when the inventory below is empty, deferring to the centered empty-state CTA. Once the user has at least one entity, the header CTA returns and the empty canvas disappears.
- **Editor section + section divider** — `.editor-section` + `.editor-section + .editor-section` (F6 leg 03 lift from studio's per-area rule). Vertical rhythm + section-divider border for entity editors. Every direct-child `.editor-section` after the first gets a top border + 16px padding-top (sibling-adjacent selector). Studio's agent editor uses these inside `.tabpanel` (which provides 20px horizontal padding); admin's provider editor adds horizontal padding via per-area `.area-admin .editor-section` override since admin has no `.tabpanel` wrapper.
- **Danger Zone** — `.danger-zone` + `.danger-zone-title` (F6 leg 03 lift from studio's `.area-studio .danger-zone-title` rule). Destructive section at the bottom of an entity editor. Markup: `<div class="editor-section danger-zone"><div class="section-title danger-zone-title">Danger Zone</div>{destructive button}{optional .action-blocked-message}</div>`. Two consumers: studio agent editor + admin provider editor. The `.danger-zone-title` color is `var(--status-danger)` to flag the section visually.
- **API-key wrapper** — `.api-key-wrap` + `.api-key-eye` (F6 leg 03 lift from `.admin-pf-password-wrap` / `.admin-pf-eye`). Wrapper for password-typed inputs with a show/hide eye toggle. Pattern: `<div class="api-key-wrap"><input type="password" .../><button class="api-key-eye" type="button" aria-label="Show password">{eye-icon}</button></div>`. Eye-toggle handler swaps `passwordInput.type` between `password` and `text`, swaps `App.icon('eye')` ↔ `App.icon('eye-off')`, updates the `aria-label`. Generic by design — area-agnostic; future API-credential surfaces inherit ready-to-use.
- **Action-blocked message** — `.action-blocked-message` (F6 HAT). Sibling-of-button banner that surfaces "you can't do this right now" messaging WITHOUT deforming the button itself. Pattern: button stays at its idle label + becomes disabled; a sibling `<div class="action-blocked-message" role="status" aria-live="assertive" hidden>` becomes visible (remove `hidden`) with the explanation. Destructive-tinted (left red border + soft danger background). Used by admin's provider-editor Danger Zone for the agent-usage hard-block path (when a provider has agents attached, deletion is blocked). Layout: 10px margin-top from the button; 8px 12px padding; 3px solid `var(--status-danger)` left border; `var(--status-danger-bg-soft)` background; `var(--status-danger)` color. The `[hidden]` attribute is canonical (declarative show/hide via attribute toggle, not class). Pairs with a 3-second auto-revert: `removeAttribute('hidden')` + `setTimeout(() => setAttribute('hidden', ''), 3000)`.
- **Refresh button** — `.refresh-btn` (F6 HAT). Icon-button shape paired with `.btn-outlined-primary` for color: `display: inline-flex; align-items: center; gap: 4px; padding: 4px 10px; svg { width: 14px; height: 14px; }`. Pattern: `<button class="btn-outlined-primary refresh-btn">{App.icon('refresh-cw')} Refresh</button>`. Used by admin's provider-editor Models panel header (basic-list + Ollama lifecycle). Mirrors `.back-btn` and `.test-provider-btn` shape — three icon-button siblings forming a coherent family.
- **Button size modifiers** — `.btn-sm` + `.btn-lg` + `.btn-xl` (F6 HAT). Optional modifiers overriding the primitive's default padding + font-size + border-radius. Compose onto any of `.btn-outlined-primary` / `.btn-filled-primary` / `.btn-muted-destructive`. Defaults (no modifier) keep each primitive's idiomatic size; modifiers come AFTER the primitives in source order so equal-specificity later-wins resolves to them. Sizes: `.btn-sm` = `2px 8px / tiny / 4px-radius` (used by Ollama panel's per-row Load/Unload/Delete + Pull Model + Pull); `.btn-lg` = `8px 20px / body / panel-radius-sm`; `.btn-xl` = `12px 32px / h3 / panel-radius`. Add new size modifiers here when a new consumer earns the lift (≥2 consumers); avoid adding them speculatively. Example: `<button class="btn-outlined-primary btn-sm">Refresh</button>`.
- **Cancel button** (`.cancel-btn`) — purely a JS testid/grep hook (F6 leg 03). NO canonical CSS rule. Disabled-when-clean opacity comes from `.btn-outlined-primary:disabled`; the `.cancel-btn` class itself only marks the element for selector convenience. Convention: any "discard the current edit" button in an editor surface composes `class="btn-outlined-primary cancel-btn"` and adds `data-testid="cancel-{entity}-btn"`.
- **Save button** (`.save-btn`) + **Back button** (`.back-btn`) + **Test-provider button** (`.test-provider-btn`) + **Delete button** (`.delete-btn`) — F5 leg 03 / F6 leg 04 canonical button shapes (lifted from `.area-studio` per-area scoping). All four compose onto the canonical color primitives (`.btn-filled-primary` for Save, `.btn-outlined-primary` for Back/Test, `.btn-muted-destructive` for Delete). `.save-btn[disabled]` + `:not([disabled])` opacity hooks key off the `disabled` attribute (Save + Cancel both flip together via `checkDirty()` — see "Dirty-state SSoT" entry below). `.back-btn` and `.test-provider-btn` carry `display: inline-flex; gap: 4px; padding: 4px 10px;` for icon-with-text spacing. `.delete-btn.confirm-delete` is the App.confirmDelete-armed state (full red-fill bg).
- **Dirty-state SSoT** — `disabled` attribute as single source of truth for Save + Cancel buttons (F5 leg 04 + F6 leg 03/04). The closure-local `dirty` flag drives `checkDirty()` which flips both `.save-btn[disabled]` and `.cancel-btn[disabled]` together — never use `.dirty` / `.clean` classes. Pattern: snapshot the form values on editor mount; on every `input`/`change` event, recompute snapshot and compare to baseline; flip both buttons' disabled state. **For F6 admin specifically**: the editor sub-module owns its local `dirty` and bridges to the orchestrator's closure mirror via `callbacks.onDirtyChange(dirty)`. The orchestrator's mirror is the gate for `App.confirmDialog`-protected navigation routes (Back, section-nav). The editor sub-module's flag is the gate for the disabled-button flip. Both reset on editor mount + on successful save.
- **Hydrate-vs-fetch race + stale-then guard** — when an area has hash-deep-linked sub-state but its data is fetched async (chat sessions, studio agents, admin providers), hash hydration may fire BEFORE the data load resolves. **Pattern**: each affected area carries a `_pendingX` field (e.g., `_pendingSelectName` in studio, `_pendingProviderId` in admin); hydrate stores the desired target there; the data-fetch's `.then()` calls `_tryConsumePendingX()` which finds the target in the now-loaded data and selects it. **F6 HAT addition — stale-then guard**: when the user has navigated AWAY from the loading area before the fetch resolves (e.g., clicked Studio while admin's `fetchProviders` is in-flight), the `.then()` handler must check `currentCategory` (or the area-equivalent) before mutating the DOM. Otherwise the late-resolving render clobbers the now-active surface (e.g., admin's grid `.then` would overwrite the General page if hydrate just switched to it). Guard pattern: `if (currentCategory !== 'providers') return;` at the top of `populateProviderGrid`.
- **Bare-area hash redirect** — when the user navigates to bare `#admin` (no sub), the area should redirect to its canonical default sub (`#admin/system`). **Two-piece contract** (F6 HAT fix): (1) the F3 router (`app.js`) calls `syncUrlFromState(areaId, sub)` after BOTH cross-area AND same-area-sub-change hydration to sync the URL with the area's `serializeState()` return value. (2) the area's `hydrateState(null)` MUST reset to its default — for admin, calling `_setCategory('system')` so `serializeState` returns `'system'` and the router's sync rewrites the URL. Without (2), the router's sync would rewrite to whatever sub the area was last on (e.g., `#admin/providers` after the user clicked Settings expecting "go to defaults"). Applies to any area with a default sub-state.

**Utility classes** (in `components.css` `@layer utilities`):
- `.is-hidden { display: none !important; }`
- `.u-flex { display: flex !important; }`
- `.u-block { display: block !important; }`

JavaScript should toggle visibility via `el.classList.toggle('is-hidden', !visible)` rather than writing `el.style.display = ...` inline. The `@layer utilities` declaration in `index.html` is the highest-precedence named layer, so utilities win over `@layer components` and `@layer areas` rules by design.

### Vibe-leg conventions

Patterns for running interactive vibe legs efficiently:

- **"Land dark, port light."** For vibe legs translating symmetrically across themes, iterate to operator-confirmed dark theme first (the aesthetic anchor); port to light at leg close as a value-swap exercise. Avoids 2× decision load during operator-bandwidth bottleneck. Established in Flight 3.5 (shell chrome). Use when the aesthetic translates symmetrically — if light requires structurally different decisions (not just value swaps), parallel iteration is necessary.

- **Gallery-as-iteration-substrate.** Build vibe variants as `.iter-*`-prefixed gallery samples in the design-language gallery (`#admin/design-language`). Operator picks + hybridizes from side-by-side comparison. Variant code stays in the gallery as reference for the rest of the vibe leg, then ripped at flight-close via the iteration-cleanup grep. Cleaner than direct-iterating on production surfaces. Established in Flights 2 + 3 + 3.5.

### Mission 08 Flight 02 — Design Language Layer (glass + bezel + motion)

A second layer on top of the M04 affordance patterns: a **glass + bezel + LED + motion** aesthetic that puts a "control-panel chrome with reflective glass" face on the existing token-driven primitives. The tokens are defined in `tokens.css` per theme; primitives compose them rather than encoding aesthetic details inline. Reduced-transparency and reduced-motion fallbacks live at the token layer too, so every consumer degrades automatically.

**Tokens added (both themes — same names, theme-tuned values)**:

| Token | Role | Dark | Light |
|---|---|---|---|
| `--glass-bg` | Translucent surface tint | `rgba(167,139,250,0.04)` (accent) | `rgba(100,116,139,0.15)` (slate) |
| `--glass-blur` | `backdrop-filter` blur radius | `12px` | `12px` |
| `--glass-saturate` | `backdrop-filter` saturate | `130%` | `130%` |
| `--glass-border` | 1px tile/popover/modal rim | `rgba(167,139,250,0.18)` | `rgba(109,40,217,0.40)` |
| `--glass-highlight` | Top-edge inset highlight color | `rgba(255,255,255,0.18)` | `rgba(255,255,255,0.95)` |
| `--glass-gleam` | Reflection-overlay `background-image` | violet→fade gradient | silver-chrome + violet bottom-fade stacked |
| `--bezel-shadow` | Full directional-depth bezel (4-layer) | white/black inset stack | white/black inset stack |
| `--bezel-shadow-mini` | Simplified 2-layer edge-only bezel | matching alphas | matching alphas |
| `--bezel-shadow-inset` | "Pressed-in" inset for form inputs | dark-top + light-bottom | dark-top + light-bottom |
| `--ease-tactile` | Primary easing curve | `cubic-bezier(0.4, 0, 0.2, 1)` | same |
| `--motion-fast` | Hover/focus transition duration | `150ms` | same |
| `--motion-base` | Panel/state transition duration | `250ms` | same |

`@media (prefers-reduced-transparency: reduce)` overrides glass + bezel tokens to opaque/single-layer fallbacks. `@media (prefers-reduced-motion: reduce)` collapses motion durations to `0ms`. Both fallbacks live in `tokens.css` so consumers don't need per-rule overrides.

**Composition rules**:

1. **Full-glass surfaces** (entity-tile, app-picker-popover, modal-dialog) compose: `background-color: var(--glass-bg) + background-image: var(--glass-gleam) + backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate)) + border: 1px solid var(--glass-border) + box-shadow: var(--bezel-shadow)`. Replaces the prior accent-tinted shadow treatment on these surfaces (it would composite poorly with the bezel stack).

2. **Mini-glass surfaces** (list-item-active, section-nav-active, chat-welcome-hover) compose the gleam image + `--bezel-shadow-mini` but skip the backdrop-filter (small surfaces don't benefit from blur, and the perf cost stacks).

3. **Input surfaces** (`.field-input`, `.field-textarea`, `.field-select`) compose `box-shadow: var(--bezel-shadow-inset)` — the OPPOSITE direction from raised bezel (dark on top, light on bottom). Reads as "pressed-in" vs the "raised" output panels.

4. **Asymmetric in/out motion** on hoverable chrome: the base rule's `transition` uses `--motion-base` (slow) and the `:hover` rule's `transition` uses `--motion-fast` (fast). Browser reads the destination state's transition at the moment of state change → entering hover takes 150ms (fast feedback), leaving hover takes 250ms (gentle disengagement). Pattern is established on `.entity-tile`, `.btn-outlined-primary`, `.btn-muted-destructive`, `.app-picker-button`. Reduced-motion users get 0ms in both directions.

5. **Theme generalization via tokenization.** When a chrome/component treatment differs only by value across themes, parametrize through tokens and drop the `[data-theme="..."]` selector prefix. Selectors stay theme-agnostic; tokens carry theme. Example: F3.5's shell rules (`#main-content`, `#app-topbar`, `#app-sidebar`) apply in both themes with values driven entirely by per-theme tokens (`--shell-chamfer`, `--shell-frame-fill`, `--shell-content-fill`, `--shell-chrome-bg`, `--shell-topbar-sheen`). If a treatment requires structurally different selectors per theme (not just value swaps), this rule does not apply — use theme-prefixed selectors.

**Button family — V3b treatment** (supersedes the pre-Mission-08 outlined-primary "transparent + accent border" pattern in `### Affordance patterns` #2 above):

All four button consumers — `.btn-outlined-primary`, `.btn-filled-primary`, `.btn-muted-destructive`, `.app-picker-button` — share the same V3 gradient shape at rest: a top-third white highlight + soft fade through the middle + bottom darkening overlay. They differ in base color (translucent vs solid vs danger-soft) and outer effects (filled-primary adds the `--accent-glow` halo for "primary CTA" reading; muted-destructive swaps to danger-glow on hover). All share `--glass-border` (translucent violet) rim, `--bezel-shadow-mini`, and asymmetric motion.

**New affordance vocabulary entries** (extend the `### Affordance patterns` § Affordance vocabulary catalog above):

- **`.checkbox-primary`** — multi-select bool primitive (Mission 08 F1 L5 lifted from studio MCP-tab; F2 L5 polished). 16px square, 1.5px `--border-strong` border, no border-radius (crisp square), accent fill when checked, white checkmark via rotated-rect `::after`. `vertical-align: middle` so it composes against text in non-flex labels. Distinct from the iOS-toggle `.tool-enable-switch` primitive (admin.css) which expresses a single binary feature flip (slide-toggle, not checkbox). Use `.checkbox-primary` for "select any of these"; use `.tool-enable-switch` for "is this feature on or off."
- **`.indicator-led`** — lit-status dot (Mission 08 F2 L5). 10px circle with two stacked `radial-gradient` background layers: white top-left reflective crescent + black bottom-right shadow. `.indicator-led--success/warning/danger/idle` modifiers fill with `--status-*` colors + matching `--status-*-glow` outer halo (idle has no glow). Also auto-applied to `.test-result-{ok,fail,warning,pending}` via `::before` pseudo-element retrofit, so existing connection-test consumers (provider editor, agent editor, tool editor) display the LED without JS markup changes.
- **`.telemetry-strip`** — gallery-only status readout primitive (Mission 08 F2 L5). Justified row: `.section-title` eyebrow on the left, mono-uppercase `.telemetry-value` on the right (often containing an `.indicator-led`), bottom-border between rows. Sibling to `.section-title` (NOT a variant) — section header vs. status readout are distinct semantic roles. Gallery-only by default; graduates to `components.css` once a downstream polish flight finds a consumer.
- **`.chip` (accent-tinted)** — Mission 08 F2 L5 retune: was `var(--surface)` + `var(--border)` (neutral), now `var(--accent-translucent)` + `var(--glass-border)` (accent-tinted flat). No gradient or shadow — distinguishes chips from raised buttons by reading as colored-but-flat tags.

### Mission 08 Flight 03 — Administration Polish Layer (banner + code-block + cross-area dirty gate)

The Admin polish flight surfaced four shared primitives + two cross-cutting structural rules that future polish flights should consume rather than re-derive. The patterns here sit on top of the F2 Design Language Layer.

**New shared primitives** (canonical, in `components.css`):

- **`.banner`** — inline status/advisory callout (Mission 08 F3 L3). Three semantic variants:
  - `.banner-error` — blocked actions, hard failures (destructive palette)
  - `.banner-warning` — irreversible operations, attention-required state
  - `.banner-info` — informational notes, neutral advisories

  Shape: 3px solid variant-color left border + variant-tinted `linear-gradient(to right, …bg-soft, transparent)` + asymmetric corner-radius (sharp left, `--panel-radius-sm` right). Supports `[hidden]`. Compose: `<div class="banner banner-{variant}">…</div>`. Replaces bespoke `.action-blocked-message` + `.admin-system-warning` styles; consumers include provider-editor's agent-usage hard-block (`.action-blocked-message banner banner-error`), system page's encryption-rotate warning (`.banner banner-warning`), and any future inline callout. **Use when** a contextual advisory needs to surface adjacent to its trigger.

- **`.code-block`** — read-only code/prompt artifact (Mission 08 F3 L3 + L7 light-theme retune). Theme-aware via tokens:
  - Dark: `--code-block-bg: #000` + `--code-block-fg: var(--status-warning)` (terminal aesthetic)
  - Light: `--code-block-bg: var(--surface-elevated)` (slate-50) + `--code-block-fg: var(--fg)` (slate-900) — AAA-grade contrast (~17:1), composes already-audited pairs

  Shape: 12px 14px padding, mono, `--panel-radius-sm`, 1px `var(--border)` framing, `pre-wrap` + `word-break: break-word`. Consumers: System page base prompt (`.admin-base-prompt code-block`), Tools editor prompt body (`.editor-prompt-text code-block`). **Use when** rendering operator-visible read-only code/prompt text that should read as a distinct "code well" against panel chrome.

**New cross-area contract**:

- **`confirmLeave(proceed, abort)`** — optional hook on the area descriptor (Mission 08 F3 L6). Called by `app.js switchTo()` BEFORE deactivating the outgoing area on cross-area navigation. Hook contract:
  - Clean state: call `proceed()` immediately
  - Dirty state: open a confirm dialog; on confirm call `proceed()`, on cancel call `abort()` (the gate restores the prior URL via `history.replaceState`)

  Areas without the hook fall through to immediate proceed. **Admin implements it** via `self._confirmLeaveImpl` wired inside `init()` so it can close over the local `dirty` flag. Same condition as the sidebar `setCategory` dirty-gate: `dirty && inEditor`. Covers all cross-area paths uniformly: topbar button clicks, browser back/forward, direct hash typing. **Use when** an area has unsaved-state that should block cross-area navigation.

**Cross-cutting structural rules**:

1. **`body { overflow: hidden }` + `min-height: 0` flex-column chain** (Mission 08 F3 L3). In SPA shells where `body { height: 100vh; display: flex; flex-direction: column }`, flex children default to `min-height: auto` (content-sized). A tall inner element's intrinsic min-height can push body content past 100vh, surfacing a document-level scrollbar that runs the FULL viewport (visible behind the topbar). Two-part fix: `body { overflow: hidden }` (body never scrolls — inner area scroll containers handle page scrolling) + `min-height: 0` on every flex-column descendant in the chain (`#main-content`, `.content-panel`, `.area-admin .admin-content`). The `min-height: 0` allows flex items to shrink below intrinsic content size — required for `overflow-y: auto` to actually clip rather than propagate up.

2. **Stale-then guard for `area.activate()` async fetches**. When an area's `activate()` runs `_refresh()` and that handler kicks off async work, `switchTo()` may subsequently mutate state synchronously via `hydrateState()`. By the time the async work resolves, the area's state may have changed — the `.then` block must guard against clobbering the now-current page. **Pattern**:
   ```js
   .then(function (detail) {
     if (currentCategory !== 'tools') return;  // stale-state guard
     // ...apply mutation + render...
   })
   ```
   Apply this in EVERY `area.activate()`-reachable async fetch's then-handler. Admin's `populateProviderGrid` (admin.js:378) and `selectTool.then` (admin.js:511) both use it. Future area code that kicks off async work from `activate()`/`_refresh()` must include the same guard at design time — catching this via HAT means a snapshot regen has already locked in the bad state.

**New affordance vocabulary entries** (extend the F2 catalog):

- **Chip-list-editor UX** (`tools-form-helpers.js`, Mission 08 F3 L5): keydown commits chip on Enter, comma, or **Tab** (Tab on empty input falls through to default focus-advance). Click on a chip body (not the × button) re-positions the chip-list-input DOM node BEFORE that chip + focuses it — enables insert-before-existing-chip flow. Backspace-on-empty deletes the chip immediately before the input's current position (walks `previousElementSibling`, skipping locked chips). `.chip-remove` color: `--accent` at rest → `--status-danger` on hover (visible + signals destructive). Consumed by admin tools editor + studio per-agent tools tab via the shared `wireChipListEditor` code path.

- **Topbar layout — 3 flat area buttons + brand banner** (Mission 08 F3 L2). One flat `.app-picker-button` per registered area, emitted via loop over `order[]`. Active area's button gets `aria-current="page"` styling (accent-translucent + accent border, no outer glow). Brand banner image (`<img class="app-topbar-banner">`) replaces the `<h1>` wordmark. Retired the chevron + popover affordance entirely (saved ~100 LOC of state machine for a 3-item menu).

- **Ollama lifecycle `.indicator-led` consumer pattern** (Mission 08 F3 L4). Worked example of consuming the F2 `.indicator-led` primitive at a non-`.test-result-*` site: `provider-models.js` emits `<span class="indicator-led indicator-led--success"></span>` for loaded models and `--idle` for available. Retired the prior bespoke `.admin-pf-model-dot` class pair. **Pattern**: when adding a new lit-status surface, prefer composing the canonical primitive at the markup site over defining a new bespoke dot class.

- **Topbar `<img>` CLS contract + legacy class-as-JS-handle pattern**: documented under F3.5 — see F3.5's section `### Mission 08 Flight 3.5 — Shell Chrome Polish Layer` below.

### Mission 08 Flight 3.5 — Shell Chrome Polish Layer (alien-dashboard housing)

Outer app-shell surfaces (`body` bg, `#app-topbar`, `#app-sidebar`, `#main-content`) take the design-language vocabulary to closure. Aesthetic target: alien-dashboard / Galaxy from GleepGlorp — solid black main panel (white in light theme) framed by a chamfered violet L-bracket border, sitting inside a unified metallic-chrome housing that wraps the topbar + sidebar as one continuous L-shaped component. Reads as a polished phone-screen-style canvas with sci-fi corner detail.

**New shell tokens** (theme-aware, in `tokens.css`):

| Token | Role | Dark | Light |
|---|---|---|---|
| `--shell-chamfer` | Corner-cut size on `#main-content` top-left | `14px` | `14px` |
| `--shell-frame-fill` | L-bracket accent color | `var(--accent)` (violet-400) | `var(--accent)` (violet-700) |
| `--shell-content-fill` | Main panel interior | `#000` | `#fff` |
| `--shell-frame-glow` | Inner halo at L-bracket meeting point | `var(--accent-glow)` | `var(--accent-glow)` |
| `--shell-chrome-bg` | Topbar + sidebar + body bg | gunmetal `#20202a` + white horizontal grain | silver `#d4d8df` + black horizontal grain |
| `--shell-bg` | Body backdrop | `var(--shell-chrome-bg)` | `var(--shell-chrome-bg)` |

`color-scheme: dark/light` is set per theme block so browser UA chrome (scrollbars, native form controls) follows the active theme rather than OS preference. Without this, scrollbars surface in the OS-theme color regardless of app theme.

**Composition rules**:

1. **L-bracket frame on `#main-content`** — nested-clip technique (operator-named "V1b" during vibe iteration). Outer element has `background: var(--shell-frame-fill)` (accent) + `clip-path: polygon(chamfer 0, 100% 0, 100% 100%, 0 100%, 0 chamfer)` (pentagon with chamfered top-left). Inner `::before` pseudo at `top: 1px; left: 1px; right: 0; bottom: 0` paints `var(--shell-content-fill)` + matching clip-path + `z-index: -1` (so it paints UNDER in-flow content — positioned-auto-z-index pseudos otherwise paint after non-positioned siblings, which would cover headers + labels). The 1px gap on top + left shows the accent fill = the L-bracket strokes. The right + bottom are flush (no border).

2. **Directional inner glow** on the inner pseudo — layered linear gradients fade `var(--shell-frame-glow)` inward from top + left edges over 20px, layered over the solid content fill. Reads as a soft halo near the L-bracket meeting point.

3. **Top-edge content fade-mask** — `mask-image: linear-gradient(180deg, transparent 0px, black 8px)` on `.content-panel` (both themes). Scrolled content fades to invisible as it approaches the top edge, "tucking under" the L-bracket border + glow. **A solid black overlay does NOT work for this** — the panel + content backgrounds are the same color in both themes, so an overlay-based fade is invisible against itself. `mask-image` is the correct technique because it removes the element's own pixels at the top, regardless of what's painted beneath.

4. **No `backdrop-filter` on viewport-edge chrome** — topbar + sidebar sit at viewport edges; nothing scrolls behind them to refract. The housing aesthetic needs texture (gradient + grain + sheen), not transparency. Static layered backgrounds via `--shell-chrome-bg` give the metallic look without the perf cost of `backdrop-filter`. Reserve `backdrop-filter` (still used elsewhere — entity-tile, popover, modal) for surfaces with scrollable content behind them.

5. **Unified L-shaped chrome housing** — `#app-topbar` + `#app-sidebar` share `var(--shell-chrome-bg)` so the topbar's bg continues seamlessly into the sidebar's bg below. **The top-edge sheen** (`linear-gradient(180deg, rgba(255,255,255,0.06) 0%, transparent 6px)`) is stacked separately on `#app-topbar` ONLY (not in the token) — if it also applied to `#app-sidebar`, the sidebar's own top edge (at y=topbar_h in viewport coords, just below the topbar) would also paint a sheen, creating a visible seam against the topbar's already-faded sheen.

6. **Body bg matches chrome** — `--shell-bg: var(--shell-chrome-bg)`. Body is only visible through `#main-content`'s chamfer cut at the top-left; making body the chrome bg lets that corner read as "the metallic housing continues through the panel cut" rather than as a black hole. Without this, the chamfer would reveal whatever the body bg-gradient was (originally a dark/pale fade, then `#000` before this fix).

**Cross-cutting structural rules** (extend Flight 3's body-overflow + min-height-zero chain):

- `#app-topbar` + `#app-sidebar` drop their `border-bottom` / `border-right` separators — they paint visible seams on the unified chrome. Use the L-bracket accent on `#main-content` for visual separation between chrome and panel instead.
- `.section-nav` drops its `border-bottom` for the same reason (paints a visible line on the metallic sidebar).
- `#app-sidebar` adds `padding-top: 10px` so the section-nav's first menu item visually aligns with the new chrome treatment.

**New affordance vocabulary entries** (extend Flight 3 catalog):

- **Topbar `<img>` CLS contract** (Flight 3 debrief carry-forward): the topbar banner image (`<img class="app-topbar-banner">`) requires explicit `height` + `flex-shrink: 0` so the topbar reserves its space immediately on first paint. Without explicit dimensions, the image loads → height resolves → layout shifts → topbar height jumps → main-content reflows. Same rule applies to any `<img>` placed in flex-shrink-0 chrome.

- **Legacy class-as-JS-handle pattern** (Flight 3 debrief carry-forward): when extracting a bespoke class into a shared primitive (e.g., `.action-blocked-message` → `.banner.banner-error`), retain the original class on the markup as a JS-query handle if any JS already queries it. The legacy class stays in the markup but its styling rule is removed from CSS — the canonical primitive's classes (added alongside) own the look. Example: `<div class="action-blocked-message banner banner-error" data-testid="delete-blocked-message">` — JS still uses `.querySelector('.action-blocked-message')` while the visual styling flows through `.banner.banner-error`. See `components.css` near the retired `.action-blocked-message` rule for the canonical example.

### Mission 08 Flight 04 — Studio Polish Layer (MCP polish + dirty-gate parity)

**Studio dirty-gate parity** (Leg 05). Studio's area descriptor now exposes the
`confirmLeave(proceed, abort)` hook, mirroring admin's pattern from F3 L06. The
hook delegates to a `_confirmLeaveImpl` closure inside `init()` that closes over
the local `dirty` flag. Same predicate as the existing sidebar inline gate:
`dirty && inEditor` where `inEditor` covers both agent-editor and mcp-server-editor
mount contexts. The sidebar `onSelect` gate now delegates to the same impl for
DRY — single source of truth for the dirty predicate.

**Same-section-click clears editor state** (Leg 07 inline HAT fix). Clicking
the active section's nav item while an editor is mounted now treats the click
as "back to grid" — clears `_selectedAgent` / `_createMode` (agents) or
`mcpSourceFormMode` / `editingMcpSource` (mcp-sources) so
`updateContentVisibility` swaps the editor for the grid. Without this,
`setActiveSection` re-rendered the grid behind a still-mounted editor and the
click visually no-op'd. Symmetric fix in `hydrateState`: a bare-section URL
(`#studio` or `#studio/agents`) clears the same closure-local state so
returning from another area lands on the grid, not a stale agent detail.

**Stale-then guard** (Leg 05). Studio's `fetchMcpSources_().then(() =>
tryConsumePendingMcpSource())` continuation now guards
`if (self._activeSection !== 'mcp-sources') return;` to prevent
`tryConsumePendingMcpSource` from firing after the user navigated away.
Mirrors admin's stale-then convention from F3 L06.

**MCP cache schema additions** (Leg 03). The MCP source `_cache` payload now
persists `meta` (the spec-optional `InitializeResult._meta`),
`protocol_version` (the negotiated MCP protocol version). The GET
`/api/mcp-sources/{id}` response now includes `has_access_token: bool` as a
presence-only flag for race-free post-OAuth state polling.

**OAuth popup-loop fix** (Leg 03). The `/api/oauth/callback` HTML page posts a
result message via `window.opener.postMessage` before auto-closing. Studio's
`launchConsentPopup` polls `GET /api/mcp-sources/{id}` for
`has_access_token: true` from popup-open onward (postMessage-independent —
Cloudflare's COOP severs `window.opener`). The race-condition window between
popup auto-close and the SDK's token-exchange completion is closed by the
polling state machine.

**Cross-area dirty-gate B2 regression test** (Leg 05). A new parametrized
Playwright test file `tests/browser/test_flow_cross_area_dirty_gate.py` locks
4 scenarios across admin + studio (cancel-keeps-state + confirm-navigates-
cleanly per area).

**Per-tool MCP tile body shape** (Leg 03). The MCP source editor's tool list
renders each tool as a glass tile whose body splits into two labeled sections:
`PROMPT` (the tool description) and `INPUT SCHEMA` (the JSON schema, or
`(no input schema)` muted text when absent). Replaces the prior nested
`<details>` schema collapsible.

**Server section on the MCP source editor** (Leg 03 functional batch). The MCP
source editor renders a "Server" section above Tools when any of `server_info`
/ `instructions` / `capabilities` / `meta` / `protocol_version` are present in
the cache. Surfaces icon + title/name + version line (`v{version} · protocol
{pv}`) + website URL + capability flags + collapsible `INSTRUCTIONS` +
collapsible `METADATA`. Information flows on the page (`.editor-section`
shape) — no tile container.

**LED on the connection-actions row** (Leg 07 inline HAT fix). The
`mcp-server-editor.js` connection-state LED moved from the
`mcp-test-status` banner up to the `mcp-connection-actions` row so it sits
adjacent to the Refresh connection button that drives its state. The status
banner below keeps its `data-testid="mcp-test-status"` hook + the tool-count
text (`Server exposes N tool(s).` or `Click Refresh connection above...`)
that browser tests assert against.

### Color contrast (WCAG AA)

The F2 design tokens were audited against WCAG 2.1 AA contrast standards on
2026-04-25 (manual + automated). All load-bearing color pairs pass at the
following thresholds:

- **4.5:1** for body text (success criterion 1.4.3)
- **3.0:1** for large text (≥18pt or ≥14pt bold), UI components, and non-text
  contrast (success criterion 1.4.11)

Pair ratios below are computed by `tests/test_design_tokens_a11y.py` using
the canonical WCAG 2.1 sRGB-luminance formula.

#### Dark theme load-bearing pairs

| Pair | Ratio | Threshold | Status |
|------|-------|-----------|--------|
| `--fg` on `--bg` | 15.00:1 | 4.5:1 (body) | PASS |
| `--fg` on `--surface` | 13.18:1 | 4.5:1 (body) | PASS |
| `--fg-secondary` on `--bg` | 5.58:1 | 4.5:1 (body) | PASS |
| `--fg-secondary` on `--surface` | 4.91:1 | 4.5:1 (body) | PASS |
| `--fg-tertiary` on `--bg` | 3.45:1 | 3.0:1 (large/UI) | PASS |
| `--fg-tertiary` on `--surface` | 3.03:1 | 3.0:1 (large/UI) | PASS |
| `--accent` on `--bg` | 10.96:1 | 3.0:1 (UI) | PASS |
| `--accent` on `--surface` | 9.63:1 | 3.0:1 (UI) | PASS |
| `--fg-on-accent` on `--accent` | 11.62:1 | 4.5:1 (body) | PASS |
| `--fg-on-danger` on `--status-danger` | 6.33:1 | 4.5:1 (body) | PASS (retuned to `#000` — see below) |
| `--status-success` on `--bg` | 9.42:1 | 3.0:1 (large/UI) | PASS |
| `--status-warning` on `--bg` | 9.77:1 | 3.0:1 (large/UI) | PASS |
| `--status-danger` on `--bg` | 5.97:1 | 3.0:1 (large/UI) | PASS |
| `--status-danger-muted` on `--bg` | 5.46:1 | 3.0:1 (large/UI) | PASS (idle-state delete affordance, leg 09 HAT) |
| `--status-danger-muted` on `--surface` | 4.80:1 | 3.0:1 (large/UI) | PASS |

#### Light theme load-bearing pairs

| Pair | Ratio | Threshold | Status |
|------|-------|-----------|--------|
| `--fg` on `--bg` | 17.23:1 | 4.5:1 (body) | PASS |
| `--fg` on `--surface` | 17.85:1 | 4.5:1 (body) | PASS |
| `--fg-secondary` on `--bg` | 9.99:1 | 4.5:1 (body) | PASS |
| `--fg-secondary` on `--surface` | 10.35:1 | 4.5:1 (body) | PASS |
| `--fg-tertiary` on `--bg` | 7.31:1 | 4.5:1 (body) | PASS |
| `--fg-tertiary` on `--surface` | 7.58:1 | 4.5:1 (body) | PASS |
| `--fg-muted` on `--bg` | 4.59:1 | 3.0:1 (large/UI) | PASS |
| `--fg-muted` on `--surface` | 4.76:1 | 3.0:1 (large/UI) | PASS |
| `--accent` on `--bg` | 5.17:1 | 3.0:1 (UI) | PASS [historical: pre-Mission-08 cyan-600 → cyan-700 retune; Mission 08 Flight 01 Leg 02 retuned again from cyan-700 to violet-700 #6d28d9, same 5.17:1 ratio against `--bg` #fafbfc] |
| `--accent` on `--surface` | 5.36:1 | 3.0:1 (UI) | PASS |
| `--fg-on-accent` on `--accent` | 5.36:1 | 4.5:1 (body) | PASS |
| `--fg-on-danger` on `--status-danger` | 4.83:1 | 4.5:1 (body) | PASS |
| `--status-success` on `--bg` | 4.84:1 | 4.5:1 (body) | PASS (retuned green-600 → green-700) |
| `--status-warning` on `--bg` | 4.75:1 | 4.5:1 (body) | PASS (retuned yellow-600 → yellow-700) |
| `--status-danger` on `--bg` | 4.66:1 | 4.5:1 (body) | PASS |
| `--status-danger-muted` on `--bg` | 5.16:1 | 3.0:1 (large/UI) | PASS (idle-state delete affordance, leg 09 HAT) |
| `--status-danger-muted` on `--surface` | 5.35:1 | 3.0:1 (large/UI) | PASS |

#### Token retunes (leg 07)

> **[Mission 08 update]** The palette below is the historical leg-07 audit
> narrative — the four retunes happened while the accent family was cyan.
> Mission 08 Flight 01 Leg 02 subsequently retuned `--accent` from cyan-700
> to GleepGlorp violet (`#6d28d9` light, `#a78bfa` dark) and updated the
> accent-glow / accent-translucent rgba tokens in
> lockstep at equivalent contrast ratios. The bullet below preserves the
> cyan-iteration story for context; for current `--accent` values see
> `tokens.css` and Mission 08 Flight 01 Leg 02. The other three retunes
> (status-success, status-warning, fg-on-danger) are still in force as
> described.

Four token values were retuned during the audit to lift them above the
applicable AA threshold:

- **Light `--accent`** [historical: cyan-iteration narrative; Mission 08
  Flight 01 Leg 02 superseded with violet retune]: `#0891b2` (cyan-600) →
  `#0e7490` (cyan-700). White on `#0891b2` reads at 4.46:1 — a body-AA
  fail when used on filled cyan buttons (e.g., `.input-area button`,
  `.save-btn`). Cyan-700 reads at 5.36:1. The accent-glow /
  accent-translucent rgba tokens were updated in lockstep so derived
  shadows, borders, and translucent fills track the new accent.
- **Light `--status-success`**: `#16a34a` (green-600) → `#15803d` (green-700).
  Used as status text colour (e.g., model-loaded indicator); green-600 read
  at 3.18:1 (body-AA fail). Green-700 reads at 4.84:1.
- **Light `--status-warning`**: `#ca8a04` (yellow-600) → `#a16207`
  (yellow-700). Used as warning text in studio's VRAM warning and provider
  badges; yellow-600 read at 2.84:1 (body-AA fail). Yellow-700 reads at
  4.75:1.
- **Dark `--fg-on-danger`**: `#ffffff` → `#000000`. White on the bright
  dark-theme `--status-danger: #ff4a4a` reads at 3.32:1 (body-AA fail) on
  delete-confirm buttons. Black reads at 6.33:1. Black-on-bright-red
  remains a strong destructive-action signal, so the change is purely a
  contrast lift, not a design-language shift.

#### Deliberate exceptions

Two tokens are intentionally below body AA (4.5:1) and pinned by tests
that assert "ratio is in the faint band, not zero, not body-AA":

- **`--fg-faint` (dark)**: `#444` on `#0a0a0a` ≈ 2.03:1. Used for
  de-emphasized annotation labels (chat-area telemetry eyebrows
  "in:"/"out:"/"ctx:", env-var hints in admin), disabled placeholders, and
  decorative recessive marks. Never body prose, never an interactive UI
  affordance. Test: `test_fg_faint_dark_is_intentional_low_contrast`.
- **`--fg-faint` (light)**: `#94a3b8` on `#fafbfc` ≈ 2.47:1. Used for the
  same annotation-label / placeholder / decorative contexts as the dark
  counterpart. Test: `test_fg_faint_light_is_intentional_low_contrast`.

Each exception carries a `# DELIBERATE EXCEPTION` comment in the test file
explaining the rationale; the assertion bands trip if a future retune
drifts the value out of "faint" territory.

#### Focus visibility

All `:focus-visible` rules across `base.css`, `chat.css`, `studio.css`,
`admin.css`, and `components.css` use the same pattern:

```css
outline: 1px/2px solid var(--accent);
box-shadow: 0 0 0 3px var(--accent-glow);
```

In dark this resolves to a `#a78bfa` outline + violet glow; in light it
resolves to a `#6d28d9` outline + violet glow (post-Mission-08 Flight 01
Leg 02 retune from the original cyan `#22d3ee` / `#0e7490` outlines). Both
meet the 3:1 non-text contrast threshold (WCAG 1.4.11) against adjacent
surfaces. Manually verified by tabbing through chat input, send button,
and the topbar app-picker in both themes.

#### Semantic attributes

`role="alert"` (errors) and `role="status"` + `aria-live="polite"` (info)
are set on `.app-flash` elements at creation time
(`the_one/interfaces/web/static/js/app.js`). Other live-region elements
(`.admin-system-flash`, `.admin-pf-test-result`, `.admin-pf-models-list`,
`.studio-vram-warning`) use `aria-live="polite"` and, where applicable,
`role="status"`. Verified intact post-leg-07.

#### Regression net

`tests/test_design_tokens_a11y.py` (36 tests) runs as part of
`pytest tests/` and fails if any token retune breaks AA. **Before changing
a color token, re-run this suite.** The tests hardcode token values to
mirror `tokens.css`; canonical mirror lives in
`tests/browser/design_tokens.py` (`DARK` / `LIGHT` dicts) — both the a11y
suite and any future test that needs to reference token values import
from there. If the CSS values change, update that single module in
lockstep — the brittleness is intentional (lightweight; no CSS-parser
dependency).

`tests/test_token_definitions.py` (1 test, leg 08) parses every
`var(--x)` reference across `static/css/*.css` and asserts each
referenced token has a definition in `tokens.css` or `fonts.css`. Catches
typos like `var(--accnet)` that CSS would silently treat as `unset` —
no visual failure, just a missing colour. Runs as part of `pytest
tests/`.

### Typography scale

Defined in `static/css/fonts.css` as CSS custom properties (theme-agnostic
— typography doesn't vary per theme; the scale lives in `:root`, NOT in
the `[data-theme]` blocks).

**Families** (Geist + Geist Mono, self-hosted, OFL/SIL pinned to
`vercel/geist-font@1.8.0`):

- `--font-family-sans`: `'Geist', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif` — UI / prose / body text
- `--font-family-mono`: `'Geist Mono', 'JetBrains Mono', ui-monospace, 'SF Mono', Menlo, Consolas, monospace` — data, code, identifiers, section-header `// PREFIX` cyberpunk markers

**Sizes**:

| Token | Value | Used for |
|-------|-------|----------|
| `--font-size-display` | 24px | Future hero / display text |
| `--font-size-h1` | 18px | Top-level area / editor titles (`.editor-title`) |
| `--font-size-h2` | 16px | Sidebar group headings (`.sidebar h3`) |
| `--font-size-body-lg` | 14px | Default body, controls, primary CTAs |
| `--font-size-body` | 13px | Secondary body, form labels |
| `--font-size-body-sm` | 12px | Tool names, sidebar items, compact rows |
| `--font-size-caption` | 11px | Tool descriptions, captions, badges |
| `--font-size-tiny` | 10px | Section-title `// PREFIX` markers, telemetry |

**Weights**:

| Token | Value |
|-------|-------|
| `--font-weight-regular` | 400 |
| `--font-weight-medium` | 500 |
| `--font-weight-semibold` | 600 |
| `--font-weight-bold` | 700 |

**Line-heights**:

| Token | Value |
|-------|-------|
| `--line-height-tight` | 1.2 |
| `--line-height-normal` | 1.5 |

**Documented exception**: `.admin-category-badge` uses a hard-coded
`font-size: 9px` (one step below `--font-size-tiny`); inline-commented
in `admin.css` because the badge sits beside denser text and needs to
recede smaller than the scale's smallest token. The "Soon" label is the
only text that uses 9px; if a future leg adds another sub-tiny use case
it should be promoted to a token.

### Icon catalog

Lucide icons available via `App.icons.{name}` (returns inline SVG string)
or `App.icon(name)` (with miss-warn). Pinned to `lucide@v0.265.0` (see
`static/js/icons.js` header). All SVGs use `stroke="currentColor"` so
colour inherits from the surrounding context (theme-aware via
`var(--accent)`, `var(--fg-secondary)`, etc.).

| Name | Lucide source | Used in |
|------|---------------|---------|
| `chat` | `message-circle` | topbar app-picker (Chat area option) |
| `studio` | `bot` | topbar app-picker (Studio area option) |
| `admin` | `settings` | topbar app-picker (Admin area option) |
| `plus` | `plus` | new-agent button (Studio sidebar) |
| `x` | `x` | session-delete, agent-delete, chip-remove, password-toggle-close, model-pull-cancel |
| `edit` | `edit` | (curated; future use) |
| `trash` | `trash-2` | (curated; future use) |
| `check` | `check` | (curated; future use) |
| `alert-triangle` | `alert-triangle` | (curated; future use) |
| `alert-circle` | `alert-circle` | (curated; future use) |
| `info` | `info` | (curated; future use) |
| `eye` | `eye` | password-reveal toggle (admin add/edit-provider form, masked state) |
| `eye-off` | `eye-off` | password-reveal toggle (admin add/edit-provider form, revealed state) |
| `refresh` | `refresh-cw` | (curated; future use) |
| `send` | `send` | (curated; future use — chat send button is currently text "Send") |
| `download` | `download` | (curated; future use) |
| `chevron-down` | `chevron-down` | (curated; future use — current dropdown arrows are inline SVG `data:` URLs in CSS) |
| `chevron-right` | `chevron-right` | (curated; future use) |
| `zap` | `zap` | (curated; future use) |
| `sparkles` | `sparkles` | (curated; future use) |
| `menu` | `menu` | app-picker hamburger button (topbar) |

Add a new icon by editing `static/js/icons.js`: append the inlined
single-line SVG markup to the `Icons` object (preserving Lucide's
standard `width="24" height="24" viewBox="0 0 24 24" stroke="currentColor"`
shape) and pin the same release tag. Lucide is MIT-licensed.

CSS sizing: each icon's host element sets a `svg { width: Npx; height: Npx; display: block }` rule (e.g., `.nav-item svg { 20×20 }`,
`.session-item .delete svg { 12×12 }`, `.new-agent-btn svg { 14×14 }`).
Currents include `.nav-item svg` (20×20), `.new-agent-btn svg` (14×14),
`.agent-item-delete svg` (10×10), `.chip-remove svg` (10×10), `.session-item .delete svg` (12×12), `.admin-pf-eye svg` (14×14), `.admin-pf-pull-cancel svg` (12×12).

### App shell

The web UI shell (F3 leg 02) uses a vertical flex-column layout: a fixed-height top bar
across the full viewport width, with a flex-row inner row below containing the sidebar and
main content area.

```
<body>
  <a class="skip-link" href="#main-content">  ← first focusable element, visually hidden until focused
  <header id="app-topbar">                    ← chrome strip; height: var(--topbar-h)
    <h1 class="app-topbar-title">             ← "the-one"; single <h1> per page
    <div class="app-topbar-actions">          ← right side: theme toggle + picker button
      <div class="theme-toggle-compact-mount">
      <button class="app-picker-button">      ← hamburger; aria-haspopup + aria-expanded
    <nav class="app-picker-popover">          ← dropdown; data-open="true/false"
  <div class="app-shell-row">                 ← flex: 1; min-height: 0; overflow: hidden
    <aside id="app-sidebar">                  ← aria-label set per active area
    <main id="main-content" tabindex="-1">   ← skip-link target; tabindex="-1" for programmatic focus
```

#### Top bar

`#app-topbar` uses the `--nav-*` palette island (same chrome tokens as the old nav rail):
`--nav-bg` background, `--nav-border` bottom border, `--nav-fg` / `--nav-fg-active` for
icon and accent colours. The `--topbar-h: 48px` token replaces the old `--nav-w` (rail
width) — same 48 px value, new semantic name.

**Known limitation**: the picker popover uses `position: absolute; right: 16px` from the
topbar. On viewports narrower than ~200px it can overflow off-screen. Acceptable for v1
(the app is desktop-first).

#### App picker contract

The hamburger button (`<button class="app-picker-button">`) toggles an inline `<nav
class="app-picker-popover">` dropdown containing one `<button class="app-picker-option">`
per registered area.

- **Open**: `data-open="true"` on the popover (CSS switches `display: none → block`);
  `aria-expanded="true"` on the picker button; focus moves to the first option.
- **Close**: `data-open="false"`; `aria-expanded="false"`; triggered by: Escape key (focus
  returns to picker button), click-outside, or option selection.
- **Keyboard model**: Enter/Space opens when picker button is focused; ArrowDown / ArrowRight
  advances through options (wraps); ArrowUp / ArrowLeft reverses (wraps); Escape closes and
  returns focus to the button.
- **Active area accent**: the current area's option carries `.active` class → primary-accent
  `::before` left-border stripe (ported from the old `.nav-item.active::before` treatment).
- **Click-outside guard**: option-click handlers call `e.stopPropagation()` (defensive —
  the click-outside `document.addEventListener` fires on bubble; `stopPropagation` prevents
  a race if the outside listener fires after the option already called `closePicker()`).

All picker wiring (open/close, click-outside, keyboard) is defined INSIDE `renderTopBar()`
so `closePicker` is in shared closure scope — no separate `wirePicker` function (that
pattern introduced a closure-scope hazard in the F3 design-review round 1).

#### Skip-link contract

`<a class="skip-link" href="#main-content">` is the FIRST element in `<body>` (before the
topbar). CSS: `position: absolute; top: -40px;` at rest; `:focus { top: 0; }` to reveal.
Background `var(--accent)`, text `var(--fg-on-accent)` for visibility.

Activating the skip-link sets `location.hash = '#main-content'`, which fires the
`hashchange` listener. The listener bails immediately (`if (!areas[hash]) return`) because
`main-content` is not a registered area hash — the skip-link does NOT force-reset the active
area to chat. `<main id="main-content" tabindex="-1">` receives programmatic focus.

#### Area sidebar label (`sidebarLabel`)

`App.registerArea()` accepts an optional `sidebarLabel` property on the descriptor. After
each `switchTo`, `<aside id="app-sidebar">` receives `aria-label` set to:
- `descriptor.sidebarLabel` if present, OR
- `descriptor.label + ' sidebar'` as fallback.

Current values: chat → `'Chat sessions'`; studio → `'Agent list'`; admin → `'Admin categories'`.

### Hash routing

F3 leg 04 extends URL routing from area-only (`#chat`, `#studio`, `#admin`) to area-plus-sub (`#chat/sessions/<id>`, `#studio/agents/<name>`, `#admin/providers`), enabling browser refresh to restore the user's exact location within each area.

#### URL format

```
#area[/sub]
```

- **area**: one of `chat`, `studio`, `admin`. Required. Defaults to `chat` if absent or unknown.
- **sub**: optional, area-specific:
  - chat: `sessions/<uuid>` (e.g., `#chat/sessions/abc-123`)
  - studio: `agents/<name>` (URL-encoded, e.g., `#studio/agents/my%20agent`)
  - admin: bare category id (e.g., `#admin/providers`, `#admin/system`, `#admin/general`)

`serializeState()` returns the sub WITHOUT the area prefix. The framework (`app.js`) owns the `area/` segment.

#### `serializeState` / `hydrateState` contract

Each area descriptor passed to `App.registerArea()` may optionally define two methods:

```javascript
App.registerArea({
  id, label, icon, order, sidebarLabel,
  init, activate, deactivate,
  serializeState,   // optional: () => string | null  — null/undefined means "no sub"
  hydrateState,     // optional: (sub: string | null) => void
});
```

- **`serializeState()`** — returns the current sub-state string (e.g., `'sessions/<id>'`), or `null` if no sub state to encode. Called by area code to compute the sub before calling `App.router.replaceSub`.
- **`hydrateState(sub)`** — applies a sub-state string to the area (e.g., joins the given session). Called by `switchTo` immediately after `activate`. On cold entry (`activate` just fired async work), `hydrateState` MUST stash a pending target and resolve it when async work completes — it must NOT assume data is ready synchronously.

Areas without `serializeState`/`hydrateState` behave exactly as before.

#### `App.router` namespace

`app.js` exposes two helpers under `window.App.router`:

```javascript
App.router.parseHash(hashString)
// → { area: string|null, sub: string|null }
// Examples:
//   parseHash('#admin/providers') → { area: 'admin', sub: 'providers' }
//   parseHash('#chat')            → { area: 'chat', sub: null }
//   parseHash('')                 → { area: null, sub: null }
//   parseHash('#/something')      → { area: '', sub: 'something' }  ← bailed in listener

App.router.replaceSub(sub)
// Updates the URL sub-state WITHOUT pushing history.
// The area is implicit (currentId). sub=null clears to bare #area.
// Uses history.replaceState — does NOT fire hashchange.
```

#### History semantics

Two navigation modes have distinct history behavior:

| Navigation type | Mechanism | History effect |
|----------------|-----------|----------------|
| Cross-area (picker click, `location.hash = 'admin'`) | `location.hash =` assignment | Pushes new entry |
| Area-internal sub-change (session click, admin category click) | `history.replaceState` | Replaces current entry |

**Critical invariant**: `history.replaceState` does NOT fire `hashchange`, so calling it from inside an option-click handler does not re-enter `switchTo`. If this invariant is ever broken by using `location.hash =` for sub-navigation, a recursion loop results: `switchTo` → `replaceSub` → `hashchange` → `switchTo` → ...

The net effect: pressing browser back exits the area entirely (or returns to the previous area), and does NOT walk back through sub-page history within an area.

#### Lifecycle ordering

- **Cold entry** (first activation of an area, or cross-area navigation):
  `init()` → `activate()` → `hydrateState(sub)`
- **Same-area sub-change** (user was already in this area, hash sub changed):
  `hydrateState(sub)` only — `init` and `activate` do NOT re-fire.
- **No-op** (same area AND same sub): returns immediately.

#### Async hydration pattern

`hydrateState` runs synchronously after `activate` returns, but `activate` may have kicked off async work. Each area handles this differently:

- **Chat**: `hydrateState('sessions/<id>')` stashes `pendingJoinId`. The `session_list` WebSocket message (which fires when the WS opens after `activate`) checks `pendingJoinId` and joins it instead of auto-joining `sessions[0]`.
- **Studio**: `hydrateState('agents/<name>')` stashes `pendingSelectName`. The `loadAll().then(...)` continuation in `init` calls `tryConsumePendingSelect()` before the default-select-first behavior.
- **Admin**: `hydrateState` updates `currentCategory` synchronously. `init` sets `currentCategory='general'`; if hydration sets it to (e.g.) `providers`, there is a brief double-fetch (general then providers). The general fetch's completion checks for `.admin-form` element existence and bails — no visual flicker. Documented as benign.

#### `replaceSub` call sites

Each area calls `App.router.replaceSub(sub)` after every internal sub-state change:

| Area | Trigger | Call site |
|------|---------|-----------|
| chat | Session joined (WS `session_joined` message) | After `currentSessionId = data.session_id` |
| chat | New chat started | After `currentSessionId = null` (clears sub during gap) |
| chat | Session deleted | After `currentSessionId = null` |
| studio | Agent selected | Bottom of `selectAgent(agent)` |
| studio | Create mode entered | Inside `enterCreateMode()` |
| studio | Agent deleted | After `selectedAgent = null` in delete handler |
| admin | Category clicked | Inside `el.onclick` in `renderCategoryList`, before re-render |

### Keyboard operability

F3 leg 03 converts all interactive `<div>`/`<span>` elements to keyboard-operable equivalents. The two patterns used across all areas are:

#### Listbox/option pattern (list rows with child action affordances)

Used where a parent row is clickable AND contains an inline delete affordance (chat session-item, studio agent-item, admin category-item). The nested-button rule prohibits `<button>` inside `<button>`, so the parent stays as a `<div>` with ARIA roles instead.

- **Parent container** (`session-list`, `agent-list`, `admin-category-list`): receives `role="listbox"` and `aria-label="<purpose>"` at init time.
- **Each row** (`session-item`, `agent-item`, `admin-category-item`): `<div role="option" tabindex="0" aria-selected="true|false">`. The row keeps its existing class-based active/hover CSS. A `keydown` listener on each row fires the activation handler on Enter or Space (`e.preventDefault()` suppresses scroll on Space).
- **`aria-selected`** is set at render time inside the list-build loop (not in a separate post-render walk). `highlightActiveSession` / `selectAgent` also update `aria-selected` on all items after activating one.
- **Simplification**: all options use `tabindex="0"` (each adds a Tab stop); no roving tabindex. For ~5–20 items this is WCAG-compliant and simpler than arrow-key navigation. Revisit at ~50 items.
- **Deliberate accepted deviation**: `role="option"` technically SHOULD NOT contain interactive children (the ARIA spec says option is a leaf). In practice, NVDA and VoiceOver handle this correctly — they announce the option, then announce the inner button separately. Document in review if a strict audit requires sibling-restructure instead.

#### Button pattern (inline action affordances)

Used for elements that are purely action-only with no child interactive content — `<span class="delete">` → `<button class="delete" type="button" aria-label="Delete session">`, `<span class="agent-item-delete">` → `<button class="agent-item-delete" type="button" aria-label="Delete agent">`, and three `<span class="chip-remove">` → `<button class="chip-remove" type="button" aria-label="Remove">` sites. No keydown handler needed — native `<button>` activates on Enter (keydown) and Space (keyup) by default.

#### `:focus-within` reveal convention

Hover-only delete affordances (hidden by `display: none` at rest) are revealed via the parent's `:focus-within` selector when the user Tabs into the child button:

```css
/* Before: */
.area-chat .session-item:hover .delete { display: block; }

/* After: */
.area-chat .session-item:hover .delete,
.area-chat .session-item:focus-within .delete { display: block; }
```

The chip-remove (`chip-remove`) is always-visible — no `:focus-within` reveal needed.

#### `:focus-visible` accent-ring convention

Two variants, both using `var(--accent)` (primary accent):

- **Inset variant** (list rows with backgrounds — `session-item`, `agent-item`, `admin-category-item`):
  ```css
  outline: 2px solid var(--accent);
  outline-offset: -2px;
  box-shadow: inset 0 0 0 3px var(--accent-glow);
  ```
- **Standard variant** (inline action buttons — `.delete`, `.agent-item-delete`, `.chip-remove`):
  ```css
  outline: 2px solid var(--accent);
  outline-offset: 2px;
  box-shadow: 0 0 0 3px var(--accent-glow);
  ```

#### Button reset for converted `<span>` → `<button>` elements

Any `<span>` converted to `<button>` must neutralize browser button defaults. Add to the element's CSS rule: `background: transparent; border: none; cursor: pointer; padding: 0;` (preserve existing `padding` value if intentional).

#### SVG-resilient chip-remove dispatch

The chip-remove click handler uses `e.target.closest('.chip-remove')` (not `e.target.classList.contains('chip-remove')`). When the button contains an SVG icon, clicking on the SVG yields `e.target = <svg>` — the `classList` check fails silently. `closest()` walks up the DOM and reliably finds the button regardless of which descendant was the click target.

### Theme switching contract

Tri-state preference (`'dark'` | `'light'` | `'auto'`) persisted in
`localStorage` under the key `theme-preference`. The `<html>` element
carries `data-theme="dark"` or `"light"` attribute, applied
synchronously by `static/js/theme.js` BEFORE any stylesheet load — the
`<script>` tag is in `<head>` ahead of `<link rel="stylesheet">` to
avoid FOUC.

**API** (exposed on `App.theme`, defined in `static/js/theme.js`):

- `App.theme.get()` → `'dark'` | `'light'` | `'auto'` — the user's
  stored preference (or `'auto'` if unset).
- `App.theme.resolved()` → `'dark'` | `'light'` — the currently-applied
  theme (reads `data-theme` from `<html>`).  When the preference is
  `'auto'`, this is the OS-resolved value.
- `App.theme.set(pref)` — sets the preference.  `'auto'` removes the
  localStorage key (so the page falls back to OS).  Throws on any other
  value than `'dark'` / `'light'` / `'auto'`.

**Auto-mode resolution**: when preference is `'auto'`, theme.js queries
`matchMedia('(prefers-color-scheme: dark)')` and
`matchMedia('(prefers-color-scheme: light)')`.  Resolution priority:
`dark` if `darkMedia.matches`, else `light` if `lightMedia.matches`,
else `'dark'` (canonical default — the F2 design language is
dark-first).  Live OS-preference changes propagate via `change`
listeners on both media queries; `auto`-mode pages re-apply on the next
frame.

**localStorage**: key `theme-preference`, value `'dark'` | `'light'`
(never `'auto'` — auto removes the key).  Reads/writes wrapped in
try/catch (`safeGet`/`safeSet`/`safeRemove`) so private-browsing or
storage-disabled contexts degrade gracefully to in-memory
non-persistent.

**Test environment**: Playwright's `browser.new_context(color_scheme="no-preference")` (set in `tests/browser/conftest.py`)
makes neither `darkMedia` nor `lightMedia` match, exercising the
canonical-default branch (auto → dark).  To capture the light theme in
a test, call `page.evaluate("App.theme.set('light')")` after navigation
and wait for the next animation frame (`page.wait_for_function("App.theme.resolved() === 'light'")`).  The
`tests/browser/test_visual_snapshots.py` helper `_set_theme(page, theme)`
does this and waits for fonts + paint stability.

#### Visual snapshot regression net

`tests/browser/test_visual_snapshots.py` (12 baselines, leg 08): three UI
areas (chat, studio, admin) × two states (empty, populated) × two themes
(dark, light) = 12 PNG screenshots stored in `tests/browser/__snapshots__/`.
Implementation uses PIL + pixelmatch (the JS-Playwright
`expect(page).to_have_screenshot()` API is not exposed in the Python
binding); tolerance is 2% pixel diff via `pixelmatch`'s
`includeAA=False` mode.  Run via `pytest -m browser tests/browser/`;
regenerate baselines via `pytest -m browser tests/browser/test_visual_snapshots.py --snapshot-update`
(or `UPDATE_SNAPSHOTS=1 pytest ...`).  Baselines are committed to git;
CI runs comparison-only.  On mismatch, the helper writes
`<name>-actual.png` and `<name>-diff.png` next to the baseline for
inspection.

- **Lucide icon pin**: icons are pinned to `lucide-icons/lucide@v0.265.0`. Adding new icons requires fetching from this exact tag — do NOT pull from `main` or `latest`. The pin is what keeps `tests/browser/__snapshots__/` baselines stable.
- **Playwright `color_scheme`**: browser tests pin `color_scheme="no-preference"` so they don't inherit the host OS theme preference. Without this, a CI environment with `prefers-color-scheme: dark` would resolve `auto` to `dark` and produce a different snapshot than a developer's light-mode laptop.

---

## Markdown rendering

Hand-rolled CommonMark-subset library at `static/js/markdown.js`. Public API:

- `App.markdown.parse(text) → AST` — `{type: 'document', children: Node[]}`. Walk the tree to inspect or transform.
- `App.markdown.render(text) → DocumentFragment` — caller appends the fragment to a parent.
- `App.markdown.NodeType` — frozen object with the string constants for all 14 node types.

### AST node shape

`{type: NodeType_value, children?: Node[], value?: string, meta?: object}`. Specific shapes documented in markdown.js header comment.

### Supported subset (v1)

paragraphs, ATX headers (`#` to `######`), fenced code blocks with optional language tag, blockquotes (single level), unordered + ordered lists (one nesting level), horizontal rules (`---` / `***`), emphasis (`*` or `_`), strong (`**` or `__`), inline code (`` ` ``), links (`[text](url)` — including URLs with balanced parens like Wikipedia citations), soft breaks (single `\n`), hard breaks (trailing TWO spaces + `\n`; a single trailing space + `\n` is a soft break, not hard).

### Out of subset (v1 non-goals)

tables, footnotes, definition lists, autolinks (bare URLs), reference-style links, HTML passthrough, recursive nested emphasis. The test corpus locks v1 in; adding any of these requires a new flight or leg with a corresponding test-case expansion.

### Nested-emphasis v1 contract

`***word***` renders as `<em><strong>word</strong></em>` (outer-em-first, inner-strong). Recursive nested emphasis (the full CommonMark "left/right flanking delimiter run" algorithm) is v2 scope. `**bold *with em***` renders as `<strong>bold *with em*</strong>` — the inner `*with em*` is literal text since recursive emphasis is off. The mechanism is an `inEmphasisRun` suppression flag in the inline parser: once an emphasis or strong run opens, emphasis-delimiter recognition is disabled inside it (only inline code, links, soft/hard breaks, plain text are honoured). The closing-delimiter-run scan returns the position such that consuming `delimLen` chars lands at the END of the run, so a 3-char `***` closer for a `**` opener has its leading `*` fall INTO the inner span as literal content.

### XSS guarantee

Renderer constructs DOM via `document.createElement` + `textContent` exclusively. The library NEVER uses `innerHTML` — `grep -n innerHTML markdown.js` returns zero hits (including comments). The icons.js SVG string injection on the code-block copy button is done via `DOMParser().parseFromString(svg, 'image/svg+xml').documentElement` to keep the no-innerHTML invariant intact. Link `href` values pass through a scheme allow-list (`http`, `https`, `mailto`, `tel`, `/`, `#`); other schemes (notably `javascript:`, `data:`, `vbscript:`, `file:`) are stripped to `#`. Future contributors cannot accidentally introduce XSS via crafted markdown — the structural property of "no innerHTML anywhere in the markdown pipeline" makes this a compile-time guarantee.

### Robustness contract (streaming-friendly inputs)

`App.markdown.parse(null)`, `parse(undefined)`, and `parse('')` all return `{type: 'document', children: []}` — no exception. `render(null) / render(undefined) / render('')` all return an empty `DocumentFragment`. This is deliberate: streaming callers can pass partial buffers (or a not-yet-arrived text) without try/catch ceremony. Whitespace-only input behaves the same as empty.

### Streaming + flash attachment contract

Callers must attach the rendered `DocumentFragment` (or its host element) to the document tree BEFORE user interaction with the rendered DOM. The code-block copy button's "Copied!" flash uses `App.showFlash(container, msg)` which appends the flash element to the container; if the container is detached, the flash never becomes visible to the user. In leg 05's chat integration this is naturally satisfied (rendered messages are appended to `.messages` which is in the document); test cases must explicitly attach via `document.body.appendChild(host)` before clicking.

### Extension contract

Adding a new construct: (1) add a `NodeType` constant, (2) add the tokeniser/parser case, (3) add the renderer branch, (4) add at least 3 parametrized test cases. All four land together in the same leg or flight. PRs that add a parser case without test cases (or vice versa) fail review.

### Code-block copy-button a11y

`<button class="markdown-copy-btn" aria-label="Copy code" type="button">` with `aria-hidden="true"` on the SVG icon (carried over from the icons.js Lucide template). On click, copies `<code>.textContent` via `navigator.clipboard.writeText`; on success, emits a "Copied!" flash via `App.showFlash`; on failure (clipboard permission denied), emits a "Copy failed" error flash. Keyboard-reachable via Tab (the button is in the natural tab order); `:focus-within` on the `.markdown-code-wrap` reveals the button so keyboard users see it before activating, and `:hover` on the button itself keeps it visible if the pointer leaves the wrap (defence-in-depth).

### Chat integration

`App.chat.renderMessage(cls, text, opts)` renders assistant messages via `App.markdown.render(text)` by default (no opt-in needed). User, tool, and system messages stay `textContent` — markdown is assistant-only. Detection uses a first-token whitespace split (`cls.split(' ')[0] === 'assistant'`) so a hypothetical `'assistant-error'` composite would NOT trigger markdown rendering; only the bare `'assistant'` first token does.

Pass `{ renderMarkdown: false }` to force textContent — used by the streaming-accumulation path so chunk-by-chunk text appends as plain text. On the `done` event (and on every streaming-bubble reset boundary — `tool_call`, `tool_result`, direct-action `assistant`), `finalizeStreamingBubble()` swaps the accumulated text for the markdown-rendered DocumentFragment. The helper extracts the buffer via `currentStreamingMsg.textContent` (not `firstChild.nodeValue`) so the algorithm is robust to future structural changes; it clears the closure pointer via `void 0` so a stray bare `currentStreamingMsg = null` reset literal never appears outside the `var` declaration.

The same default applies to historical assistant messages on session-rejoin (`renderHistory` → `addMsg('assistant', ...)` → `renderMessage` → markdown). The persistence contract (leg 04: synthesized assistant `Message` added to `session.history` server-side) carries through cleanly: streamed markdown shows on first send AND on rejoin.

Mid-stream markdown rendering is intentionally NOT supported — partial markdown syntax has no canonical semantics (`**bold` mid-token has no end). The streaming path uses `textContent` accumulation followed by a single swap on `done`. Block-element resets in `static/css/chat.css` (scoped under `.area-chat .msg.assistant`) strip default top/bottom margins on `<p>`, `<ul>`, `<ol>`, `<pre>`, `<blockquote>` so paragraph-style markdown answers don't shift bubble heights from browser defaults.

---

## Streaming protocol

F4 leg 04 added a streaming path through the LLM stack so assistant content fans out to the chat client chunk-by-chunk during generation. The protocol is provider-agnostic at the agent layer; per-provider native streaming sits behind a single `LLMProvider.stream(...)` method.

### `LLMProvider.stream(...)`

```python
async def stream(
    self,
    messages: list[Message],
    tools: list[dict[str, Any]] | None = None,
    temperature: float = 0.0,
    max_tokens: int = 16384,
) -> AsyncIterator[StreamChunk]
```

**NOT abstract** — the base class supplies a default implementation that calls `complete()` and yields exactly one `StreamChunk(is_final=True, ...)`. Forward-compat for any future provider that doesn't natively stream. Subclasses MAY override for native chunk delivery.

### `StreamChunk` shape

```python
@dataclass
class StreamChunk:
    content: str = ""               # NEW tokens since the last chunk; delta semantics, NOT cumulative
    is_final: bool = False           # True only on the final chunk
    tool_calls: list[ToolCall] = []  # populated on final chunk
    usage: TokenUsage | None = None  # populated on final chunk where exposed
    message: Message | None = None   # populated on final chunk; the synthesised assistant Message
```

**Delta semantics**: `content` is the NEW tokens for that chunk, NOT cumulative. The agent accumulates by string concatenation. The final chunk MAY carry a content delta (some providers emit a stop-event with trailing text); the agent's accumulator handles that by checking `chunk.content` regardless of `is_final`.

**Final-chunk contract**: providers populate `message` with the synthesised assistant `Message` so `Agent.step` can prefer it over rebuilding from accumulator state. When `message` is None on the final chunk, the agent rebuilds from accumulated `content` + `tool_calls` + `usage`.

### Per-provider streaming notes

- **Anthropic** (`anthropic_provider.py`): native streaming via `client.messages.stream(...)`. Yields `text_stream` deltas in real time; final message comes from `stream.get_final_message()` (text content + `tool_use` blocks + usage). **Ports the F3 `BadRequestError` temperature-retry**: catches `BadRequestError` containing "temperature", strips the kwarg, retries once. Gated by a `yielded_any` flag so the retry is only safe BEFORE any chunk has emitted (post-yield retries would duplicate output to the consumer; in practice Anthropic raises pre-stream, so the gate is defence-in-depth). The shared `_build_kwargs` helper DRYs the retry so `complete()` and `stream()` share a single kwargs construction path.
- **OpenAI** (`openai_provider.py`): native streaming via `chat.completions.create(stream=True, stream_options={"include_usage": True}, ...)`. The `include_usage` flag is **required** — without it the trailing metadata-only chunk has no `usage` field and the F4 telemetry overlay's end-of-stream update breaks. Tool-call deltas accumulate by `index` and emit on the final chunk.
- **Ollama** (`ollama_provider.py` + `ollama_api.chat_stream`): native streaming via the new `ollama_api.chat_stream(provider_url, body) → AsyncIterator[dict]` SSE helper. Wire format is **true SSE** (`data: {...}` lines + `data: [DONE]` terminator), distinct from `pull_model`'s JSONL. The provider consumes the parsed dicts and reuses the OpenAI-shape tool-call accumulation pattern (the Ollama OpenAI-compatible endpoint emits the same chunk shape).
- **Mock** (`mock.py`): honours a new `config["stream_chunks"]: list[str]` option. When set (non-empty list), `stream()` yields each chunk with the existing `delay_ms` between deltas; the final chunk synthesises a `Message` from accumulated content + the configured `response.tool_calls`. When `stream_chunks` is unset/empty, falls back to the default-impl path **inline** (calls `self.complete()` + yields one final chunk — NOT `super().stream(...)` delegation, for clarity and to avoid async-generator delegation overhead).

### `Agent.step` `on_chunk` callback

```python
async def step(
    self,
    user_input: str,
    on_chunk: Callable[[str], Awaitable[None]] | None = None,
) -> AsyncIterator[Message]
```

Internally calls `self.llm.stream(...)` and accumulates content per iteration. When `on_chunk` is provided, it is invoked once per content delta during streaming. The Message-yielding contract is unchanged for callers that don't pass `on_chunk` — chunks fan out internally but only the synthesised final `Message` flows up via `yield`. The direct-action shortcut path bypasses the LLM entirely so `on_chunk` is never invoked there.

### WS event vocabulary

| Event | When | Direction |
|------|-----|-----------|
| `assistant_chunk` | Per-content-delta during streaming | server → client |
| `assistant` | Direct-action shortcut path only (no chunks fired) | server → client |
| `tool_call` | Tool-call emitted by the model (non-streamed) | server → client |
| `tool_result` | Tool execution result | server → client |
| `usage` | Token usage on each iteration's final chunk | server → client |
| `done` | End of agent step | server → client |

The streaming WS contract is **chunks-only-no-final-assistant**: when the chunk path fires, the legacy `assistant` event is suppressed server-side. The client already has the accumulated text via the chunk stream. The legacy `assistant` event survives for the direct-action shortcut path (early-return in `Agent.step` before any LLM call).

### Tool event discriminator fields

**`tool_call` and `tool_result` events carry a paired `parent_message_id` + `tool_call_id` discriminator** (introduced Flight 05 Leg 02). The `parent_message_id` (string) identifies which assistant turn owns the tool activity; `tool_call_id` (string) is sourced from `ToolCall.id` / `ToolResult.tool_call_id`. Both fields are derived at projection time from the message index and existing ToolCall fields — no new Message dataclass field required.

The `parent_message_id` format follows a namespace convention: live sessions use `{session.id}-msg-N` (where N is the agent.messages index); replayed sessions use `replay-msg-N`. The frontend treats these as opaque grouping keys — different namespace prefixes between live and replay are not collisions; the browser buckets events by string equality. L03's frontend groups all events with the same `parent_message_id` into a per-assistant-turn collapsible `.trace-shell` container (see `the_one/interfaces/web/static/js/areas/chat/trace-shell.js`) using native `<details>`/`<summary>` elements.

### `chunks_seen` invariant in `_process_and_broadcast`

The server distinguishes streaming from direct-action via a per-iteration `chunks_seen` flag captured in the agent-step closure. The flag is set inside `_broadcast_chunk` (the callback passed to `agent.step`), and reset **unconditionally at the end of each Role.ASSISTANT block** in the `async for msg in agent.step(...)` loop. The unconditional reset matters for multi-iteration agent loops: a tool-call-only iteration (empty `msg.content`, non-empty `msg.tool_calls`) must still reset the flag for iteration N+1. Resetting inside `if msg.content:` would skip the reset on tool-call-only responses and incorrectly carry `chunks_seen=True` into the next iteration.

### Persistence contract

The synthesised final assistant `Message` is **NOT broadcast** as `{"type": "assistant"}` over the WS during streaming (the client already has the text). It IS:

- Appended to `session.history` via `session.add_event(event)` so session rejoin / refresh re-renders the assistant text from server-side history.
- Appended to `result_messages` so the HTTP API caller (POST /api/sessions/{id}/messages) receives the full message list.

This split — stream-the-deltas-over-WS, persist-the-full-message-server-side — is the F4 leg-04 contract. Browser test `test_streaming_message_persists_to_history` enforces it end-to-end: send a streaming message, reload the page, and assert the assistant text re-appears from history.

### chat.js wire-up (option B minimal rendering)

The chat.js wire-up renders chunks via a `currentStreamingMsg` pointer that holds the current assistant bubble. First `assistant_chunk`: clear the thinking indicator, mint a fresh `<div class="msg assistant">` + attribution (built via `App.chat.renderMessage('assistant', '', { renderMarkdown: false })` so `textContent` semantics hold during accumulation), store the bubble pointer. Subsequent chunks: append the delta to the bubble's text node. At every streaming-bubble reset boundary (`tool_call`, `tool_result`, direct-action `assistant`, AND `done`) the wire-up calls `finalizeStreamingBubble()` — leg-05 — which swaps the accumulated `textContent` buffer for the markdown-rendered `DocumentFragment` and clears the pointer. Iteration N+1 (in a multi-iteration agent loop) therefore lands chunks in a fresh bubble after each iteration boundary, with the closed iteration's bubble already markdown-rendered.

---

## Provider type extension checklist

To add a new LLM provider type, six layers must coordinate. Missing any one of them causes either silent rejection (validation) or runtime errors.

> **History**: The M04 flight that added the `mock` provider type initially missed the SQLite CHECK constraint (#4 below) during state-machine reachability audit. First test run failed with `IntegrityError: CHECK constraint failed`, requiring schema migration v6. The checklist below is the post-incident enumeration.

### Provider URL validation (M06 F1 L5)

`_is_safe_provider_url` (`the_one/interfaces/web/api.py`) enforces `https://` for non-localhost hosts on LLM provider `base_url`. Called at endpoint time from `create_provider` (L772), `update_provider` (L811), and `test_provider` (L864) — NOT a Pydantic validator. Reason: `update_provider` accepts `__MASKED__` for unchanged fields (see `### __MASKED__ sentinel for API key updates` in `CLAUDE.md`); the validator must run on the **resolved** `base_url` post-`model_copy(update=data)`, not the request payload. Two skip layers: (a) provider types in `_URL_VALIDATION_SKIPPED_TYPES = frozenset({"mock", "ollama"})` bypass URL validation entirely; (b) for the remaining types, `http://` is allowed only when the host is `localhost`, `127.0.0.1`, `::1`, or any `*.localdomain` name. RFC1918 / link-local / `0.0.0.0` are NOT exempt — they require `https://`.

1. **Pydantic `Literal`** — `db/models.py` `LLMProviderConfig.type`. Add the new value to the `Literal[...]` tuple. Without this, `model_validate` rejects.
2. **`_PROVIDER_TYPE_MAP`** — `agent/factory.py`. Add `"<type>": "<registry-name>"`. Without this, `AgentFactory.create()` raises `ValueError` for agents pointing at the new type.
3. **Registry `loaders` dict** — `llm/registry.py:_try_load_builtin`. Add `"<type>": lambda: __import__("the_one.llm.<provider_module>", fromlist=["_"])`. Without this, `get_provider("<type>")` raises a misleading `ImportError("requires extra dependencies")`.
4. **SQLite `CHECK` constraint** — `db/schema.py` (table definition AND migration). The `llm_providers` table's `CHECK (type IN (...))` clause hard-codes allowed values. Adding a new type requires a schema migration (see v6 for the pattern: `PRAGMA foreign_keys=OFF` + table rebuild). Without this, `INSERT` fails with `IntegrityError: CHECK constraint failed`.
5. **API gating / branches** — `interfaces/web/api.py`:
   - `create_provider` and `update_provider` — add type-specific gating if the new type has a precondition (e.g., dev-mode flag for `mock`)
   - `test_provider` — add a branch returning health/test result for the new type
   - `list_provider_models` — add a branch returning the model list (may query an upstream API or read from `LLMProviderConfig.config`)
   - `GET /api/providers/types` — include or exclude based on any feature gating
6. **Frontend handling** — `interfaces/web/static/js/areas/admin.js`:
   - `PROVIDER_TYPES` is fetched from `/api/providers/types` (post-leg-02), so the type appears in the dropdown when allowed by the API
   - Add `TYPE_DEFAULTS["<type>"] = { base_url, showBaseUrl, showApiKey }` (unconditional — needed for editing existing providers even if the type is later hidden from creation)
   - Add `<type>` to the `KNOWN_BADGE_TYPES` array in `admin.js` (so the renderer emits `.admin-provider-badge--<type>`) and add a `--badge-<type>` token in `tokens.css` plus the matching `.admin-provider-badge--<type>` rule in `admin.css` (post-leg-02 the badge styling is CSS-driven; no JS color literals)
7. **`_init_provider_state(self, kwargs: dict) -> None`** (optional hook on `LLMProvider`) — called from `LLMProvider.__init__` after the standard fields (`model`, `api_key`, `base_url`, etc.) have been assigned. Implement when the new provider needs to capture configuration that is not part of the base field set (e.g. OpenRouter pulls `app_url` / `app_name` out of `kwargs` to populate its `HTTP-Referer` / `X-Title` analytics headers; Ollama uses the hook to seed lazy-resolved `max_context_tokens` state). Without the hook the constructor would have to be subclassed wholesale; with it, only the per-type capture lives in the subclass. Reference implementation: see `_init_provider_state` in `the_one/llm/openrouter_provider.py` (locate by symbol — line numbers drift).

When all six (plus optional 7th) layers are aligned, an integration test posting a provider with the new type round-trips successfully through DB persistence, factory resolution, and UI rendering.

---

## Performance Measurement (F7)

This section documents the four canonical MCP-runnable performance scenarios for the UI. Each scenario exercises one of the leak / latency surfaces identified in the F7 flight design and produces a serializable measurement blob via `App.perf.dump()` / `App.perf.summary()`.

**Activation gate**: `App.perf` is loaded by `the_one/interfaces/web/static/js/perf.js` (loads BEFORE `app.js` in `index.html`) but is INACTIVE by default. Activate via:
- URL query string: append `?perf=1` to any page URL (e.g. `http://localhost:8484/?perf=1#chat`), OR
- localStorage: `localStorage.setItem('the-one-perf', '1')` then reload the page.

The `enabled` flag is captured at module-load time — toggling localStorage mid-session requires a reload before perf marks/measures begin firing.

**Browser support note** (cycle-1 reviewer empirical finding): `performance.memory` is Chromium-only AND only exposed in same-origin-isolated contexts; values are throttled to 100KB precision and may require `--enable-precise-memory-info` for fine-grained readings. `App.perf.captureHeap()` returns `null` when `performance.memory` is unavailable.
- **F7 L01 empirical finding (Flight-Director-filled)**: `App.perf.captureHeap()` against the running app at `localhost:8484` returned: TBD (`null` vs numbers — to be filled by Flight Director after MCP capture pass).
- When `captureHeap()` returns null, scenarios fall back exclusively to `mcp__chrome-devtools__take_memory_snapshot` for heap-growth signals.

**Common MCP-runnable export pattern** (used by every scenario):
```
mcp__chrome-devtools__navigate_page(url='http://localhost:8484/?perf=1#chat')
mcp__chrome-devtools__evaluate_script(function='() => App.perf.reset()')   # zero out marks/measures
# ... scenario actions ...
mcp__chrome-devtools__evaluate_script(function='() => App.perf.summary()')  # aggregated p50/p95/max per measure
# OR for raw entries:
mcp__chrome-devtools__evaluate_script(function='() => App.perf.dump()')     # raw marks + measures + heap snapshot
```

### Scenario 1: Area-switch cycles (200 cross-area transitions over 50 cycles)

**Purpose**: detect retention growth across area-lifecycle activate/deactivate cycles. Mission criterion: "memory behavior across `App.areas.activate` / `deactivate` cycles." 50 loops × 4 transitions per loop = 200 area-switches total provides a strong leak-detection signal.

**MCP procedure**:
```
1. mcp__chrome-devtools__navigate_page(url='http://localhost:8484/?perf=1#chat')
2. mcp__chrome-devtools__evaluate_script(function='() => App.perf.reset()')
3. mcp__chrome-devtools__take_memory_snapshot()  # pre-cycle heap
4. Loop 50 times: click topbar Chat -> Studio -> Admin -> Chat
   (4 transitions per loop = 200 area-switches total). Use:
     mcp__chrome-devtools__click(selector='[data-area="studio"]')
     mcp__chrome-devtools__click(selector='[data-area="admin"]')
     mcp__chrome-devtools__click(selector='[data-area="chat"]')
5. mcp__chrome-devtools__take_memory_snapshot()  # post-cycle heap
6. mcp__chrome-devtools__evaluate_script(function='() => App.perf.summary()')
```

**Expected baseline** (F7 L01 capture, operator's machine, 2026-05-15):
- Pre-cycle heap: 1.64 MB (1,635,692 bytes)
- Post-cycle heap: 2.14 MB (2,140,714 bytes)
- Heap growth: 505 KB / **+30.88% — EXCEEDS BUDGET** (BUDGET: <=20%). L02 confirmed-live target.
- p50 `area-switch.full` measure: 0.10 ms (BUDGET: <=50ms) ✓
- p95 `area-switch.full` measure: 0.20 ms (BUDGET: <=100ms) ✓
- p50 `area-switch.deactivate` measure: 0.00 ms ✓
- p95 `area-switch.deactivate` measure: 0.10 ms ✓
- Capture details: 50 loops × 3 effective hashchange transitions (chat→chat is a no-op) = 150 area-switch.full measures; total wall time 6.1s
- **`performance.memory` IS available** in this Chrome context — heap reads return numeric values, not null

**Post-L03 baseline (H1 fix landed, 2026-05-15)**:
- Pre-cycle heap: 2.18 MB
- Post-cycle heap: 2.26 MB
- Heap growth: **85 KB / +3.92% — WELL UNDER BUDGET** ✓ (was +30.88% pre-fix; 87% reduction)
- p50 / p95 `area-switch.full`: 0.10 ms / 0.20 ms (unchanged from pre-fix — fix was leak-side only, not latency-side)
- **H1 confirmed as primary leak driver**. H2 subsumed by H1 (document listener was the retainer root for the detached DOM trees). Remaining +3.92% is normal V8/JIT warm-up + perf.js mark-buffer instrumentation artifact (H3 — gated off in production)

**Acceptable variance**: heap growth within +/-5pp across runs on the same machine; p95 latency within +/-25% across runs.

**On failure**: leak roots are most likely in `chat.js:init()`'s closure state (per-init listeners attached to globally-rooted elements survive deactivate); investigate via L02's heap-diff procedure. Candidate fix areas: `the_one/interfaces/web/static/js/areas/chat.js` (`init()` listener registration), `the_one/interfaces/web/static/js/app.js` (`performCrossAreaSwitch` panel-show/hide DOM mutation).

### Scenario 2: Long-chat session (100-message conversation rendering + scroll)

**Purpose**: measure DOM-growth + per-message render cost for `addMsg()`, smart-scroll, and session-join replay paths. Mission criterion: "rendering performance with long conversation history."

**MCP procedure**:
```
1. mcp__chrome-devtools__navigate_page(url='http://localhost:8484/?perf=1#chat')
2. Seed a 100-message session (manual or via the existing dev-seed; pick an
   existing session with >=100 messages OR run a scripted producer).
3. mcp__chrome-devtools__evaluate_script(function='() => App.perf.reset()')
4. mcp__chrome-devtools__take_memory_snapshot()  # pre-join heap
5. mcp__chrome-devtools__click(selector='[data-session-id="<session-id>"]')
   # triggers session_joined replay -> 100 addMsg calls
6. mcp__chrome-devtools__evaluate_script(function='() => App.perf.summary()')
7. Scroll to top/bottom 5 times via mcp__chrome-devtools__evaluate_script
   to exercise smart-scroll under load.
8. mcp__chrome-devtools__take_memory_snapshot()  # post-replay heap
```

**Expected baseline** (F7 L01 capture, 2026-05-15):
- Pre-join heap: 2.24 MB (operator-machine baseline at chat-area idle)
- Post-replay heap: 2.24 MB (no session selected during capture — operator had cleared sessions in F6 HAT)
- Heap delta: ~0 (no replay fired)
- p50 / p95 / max `addMsg`: not captured — no session-join replay during FD capture window
- `session-join.ws-to-dom`: not captured — same reason
- `session-join.dom-to-paint`: not captured — same reason
- **Operator-task during L06 HAT**: re-run this scenario with at least one populated session (>=100 messages) to capture meaningful baselines. The capture-procedure above remains valid; the FD's pass landed without an existing session to exercise.

**Acceptable variance**: per-message p95 within +/-30% across runs; ws-to-dom budget breach >50% indicates `renderHistory()` regression.

**On failure**: investigate `renderHistory()` in `the_one/interfaces/web/static/js/areas/chat.js` (lines around 207-248) and `App.chat.renderMessage` in `the_one/interfaces/web/static/js/areas/chat/message-bubble.js`. Candidate fix areas: batched DOM-fragment append in `renderHistory`, deferring markdown render off the critical path.

### Scenario 3: Large session-history list (sidebar with 50+ sessions)

**Purpose**: detect O(n) work in `refreshSessionList` / `session_list` render when the session sidebar carries 50+ entries. Mission criterion: "session-list render cost with many sessions."

**MCP procedure**:
```
1. Seed at least 50 sessions (dev-seed script OR repeated new_session pings).
2. mcp__chrome-devtools__navigate_page(url='http://localhost:8484/?perf=1#chat')
3. mcp__chrome-devtools__evaluate_script(function='() => App.perf.reset()')
4. mcp__chrome-devtools__take_memory_snapshot()  # pre-render heap
5. Trigger 10 refreshSessionList calls in sequence (e.g. click a session,
   send a message, wait for completion, refresh -> 10x).
6. mcp__chrome-devtools__evaluate_script(function='() => App.perf.summary()')
7. mcp__chrome-devtools__take_memory_snapshot()  # post-render heap
```

**Expected baseline** (F7 L01 capture, 2026-05-15):
- Pre-render heap: 2.24 MB
- Post-render heap: 2.24 MB
- Heap delta: ~0 — operator had 0 sessions visible in the sidebar at FD capture time (cleared in F6 HAT)
- p50 / p95 sidebar refresh: not captured — empty sidebar; refresh is degenerate
- **Operator-task during L06 HAT**: re-run this scenario with at least 50 seeded sessions to capture meaningful baselines. The capture-procedure above remains valid.

**Acceptable variance**: +/-25% across runs.

**On failure**: investigate the session-list render path in `the_one/interfaces/web/static/js/areas/chat.js` (search for `refreshSessionList` / `session_list` handler). Candidate fix areas: virtualization, DocumentFragment batching, deferred-render queue.

### Scenario 4: Many-agents-in-studio rendering

**Purpose**: measure render cost when the studio agent-list carries many agents; detect retention in the agent-editor mount/unmount cycle. Mission criterion: "studio render performance with many agents."

**MCP procedure**:
```
1. Seed at least 30 agents via /api/agents POST (or fixture).
2. mcp__chrome-devtools__navigate_page(url='http://localhost:8484/?perf=1#studio')
3. mcp__chrome-devtools__evaluate_script(function='() => App.perf.reset()')
4. mcp__chrome-devtools__take_memory_snapshot()  # pre-render heap
5. Click 20 different agents in sequence to exercise the editor mount/unmount
   (mcp__chrome-devtools__click against each agent-list item).
6. mcp__chrome-devtools__evaluate_script(function='() => App.perf.summary()')
7. mcp__chrome-devtools__take_memory_snapshot()  # post-cycle heap
```

**Expected baseline** (F7 L01 capture, 2026-05-15):
- Pre-render heap: 2.24 MB
- Post-cycle heap: 2.31 MB
- Heap delta: 73 KB after a single studio area-switch + ~1.5s render window
- `agent-tile` count visible: 0 (studio either didn't fully render in the 1.5s capture window OR operator has no agents configured)
- **Operator-task during L06 HAT**: re-run this scenario after seeding >=30 agents to capture meaningful baselines. The capture-procedure above remains valid.

**Acceptable variance**: +/-25% across runs.

**On failure**: investigate `the_one/interfaces/web/static/js/areas/studio/agent-editor.js` for listener leaks on mount/unmount and `the_one/interfaces/web/static/js/areas/studio.js` for agent-list rendering. Candidate fix areas: explicit `removeEventListener` on editor teardown, agent-list DocumentFragment batching.

---

**Operator note**: the baseline TBD values above are captured during the F7 L01 Flight-Director pass by running each MCP procedure end-to-end. Once captured, they become the reference threshold for L02-L05 to compare against post-fix.

---

### `make rebuild` wipes Playwright Chromium

**Symptom**: running `docker exec the-one pytest -m browser` immediately after `make rebuild` fails with hundreds of `Error: BrowserType.launch: Executable doesn't exist at /root/.cache/ms-playwright/...` errors in under 15 seconds — every browser-marked test errors before doing real work.

**Cause**: `make rebuild` rebuilds the container image, wiping the cached Playwright Chromium binary from `/root/.cache/ms-playwright/`. The image-build pipeline doesn't re-install Chromium; that step lives in a separate make target.

**Recovery**: run `make _ensure-playwright` on the host. This reinstalls Chromium into the container's cache (~30-60s on a warm network). Then re-run the browser suite — should pass cleanly at the prior baseline (F7 baseline: 316 passing / 35 skipped).

**Surfaced in**: F5, F6, F6.5, F7 HATs. Every flight that runs `make rebuild` during execution hits this. A future maintenance flight could fold the Chromium-install step into the `make rebuild` recipe itself (idempotent re-install); until then, the recovery procedure is the documented workaround. M08 F7 L05 (F6.5 debrief AI #6).

