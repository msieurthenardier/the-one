# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A general-purpose, LLM-powered personal agent. No agent frameworks — the agent loop, tool registry, LLM abstraction, and message protocol are all hand-rolled. Built-in tools cover filesystem, execution, and web; a layered system prompt composes a foundational base with optional per-agent personas.

## Commands

```bash
# Install (editable, with all optional deps)
pip install -e ".[all-llms,dev]"

# Run CLI
the-one chat

# Run web server (port 8484)
the-one serve

# Tests
python -m pytest tests/ --tb=short -q
python -m pytest tests/test_example.py -q          # single file
python -m pytest tests/test_example.py::test_name   # single test
pytest -m live tests/test_aiat.py                   # AIAT (needs running instance)
pytest -m browser tests/browser/                    # Browser tests (needs THE_ONE_DEV_MODE=true)

# Lint & format
ruff check the_one/ tests/
ruff format the_one/ tests/
```

## Local dev with Docker

The container at `localhost:8484` serves from image-baked code (`Dockerfile COPY the_one/`) — **editing source on the host does NOT update the running app**. The test suite spawns its own uvicorn subprocess; that path is independent of the served daemon at port 8484. Browser tests can therefore go green while the user-facing app serves stale JS — `make rebuild` is the cure.

Use the Makefile rather than raw `docker compose` calls so the rebuild + verify step is consistent:

```bash
make rebuild                # rebuild image + restart + verify static assets (use after editing JS/CSS/Python)
make rebuild-clean          # rebuild + wipe DB volume + restart fresh (HAT prep — empty-state walkthroughs)
make reset-db CONFIRM=1     # wipe DB volume + restart (without rebuild). Gated to prevent accidental data loss.
make up                     # start without rebuilding
make down                   # stop
make logs                   # follow container logs
make shell                  # bash into the container
make test                   # run all default tests inside the container
make test-unit              # unit tests only
make test-browser           # Playwright browser tests
make lint                   # ruff check
make format                 # ruff format
make verify-serving         # curl-check that admin sub-modules return 200 (catches stale-image bugs)
make help                   # list all targets
```

**When `make rebuild` is required**: any change under `the_one/` — JS, CSS, HTML, Python. The Dockerfile copies these at build time; live-reload is intentionally NOT enabled (mirrors the Concourse CI/prod path).

**When `make rebuild` is NOT required**: editing files under `tests/` (the test suite spawns its own uvicorn subprocess, independent of the served daemon) or running ad-hoc one-off pytest invocations.

## Architecture

The system has four layers that compose bottom-up:

**LLM layer** (`the_one/llm/`) — Abstract `LLMProvider` base with `complete()` method. Three implementations (ollama, openai, anthropic) lazy-loaded via a registry (`get_provider(name)`). All share the `Message`/`ToolCall`/`ToolResult` dataclasses from `base.py`. Provider is resolved from the database via `LLMProviderRepository` — each agent references a provider config by `provider_config_id`.

**Tool layer** (`the_one/tools/`) — Abstract `Tool` base class with `execute(**kwargs) -> str`. `ToolRegistry` holds all tools and generates JSON schemas for the LLM. `BuiltinToolProvider` (`builtins.py`) provides all 19 built-in tools via lazy import, implementing the `ToolProvider` protocol (`provider.py`): one `shell`, nine filesystem (`read_file`, `write_file`, `edit_file`, `delete_file`, `move_file`, `mkdir`, `glob`, `grep`, `list_dir`), one `python_exec`, four PTY session tools (`shell_session_start`, `shell_session_send`, `shell_session_close`, `shell_session_list`), and four web (`http_request`, `fetch_url`, `download_file`, `web_search`). Tools are the agent's only way to affect the outside world.

**Agent loop** (`the_one/agent/core.py`) — The `Agent` class runs: user input → LLM call → tool execution → repeat until no tool calls remain. The agent uses a virtual `CONTINUE_SCHEMA` (defined inline in `core.py`) as a turn-keeping signal — when the LLM calls `continue`, the loop registers another iteration. Max 20 iterations per step as a safety limit.

Agent configuration (`agent/config.py`) defines `AgentConfig` (Pydantic model) with `provider_config_id` (FK to `llm_providers`), `llm_model`, prompt, tool filtering, and behavior settings. `AgentFactory` (`agent/factory.py`) resolves the provider config from DB, maps the provider type to the registry name, and wires config + LLM + tools into a ready-to-use Agent. Agent configs persist via `SQLiteAgentStore` in the DB.

**Persistence** (`the_one/db/`) — SQLite via aiosqlite. `get_connection()` returns a shared async connection. Repository classes (`SQLiteAgentStore`, `KnowledgeBaseRepository`, `MCPSourceRepository`, `ChatSessionRepository`, `KBItemRepository`, `LLMProviderRepository`) each wrap a table with CRUD operations over Pydantic models. `LLMProviderRepository` takes an `Encryptor` for transparent encrypt-on-write / decrypt-on-read of API keys. Schema is versioned (currently v7) and auto-migrated on first connection.

**Encryption** (`the_one/encryption.py`) — Fernet symmetric encryption for API credentials. Key auto-generated at `{data_dir}/encryption.key` (mode 0600). `get_encryptor(data_dir)` returns an `Encryptor` instance. Supports key rotation via `rotate_key()`.

### `__MASKED__` sentinel for API key updates

The provider edit form sends the literal string `__MASKED__` as the `api_key` field when the user has not modified it. The backend (`update_provider` in `interfaces/web/api.py`) detects this sentinel and preserves the existing stored key rather than overwriting it with the masked display value. Anyone touching the provider edit form needs to know this contract.

**Interfaces** (`the_one/interfaces/`) — CLI (Rich + prompt-toolkit) and Web (FastAPI + WebSocket). Both use `AgentFactory.create()` to get configured agents, then call `agent.step(user_input)` which yields messages. The web app adds session management and broadcasts events to WebSocket subscribers.

The web UI has three functional areas sharing a sidebar + content panel layout:
- **Chat** — Multi-session chat with agent selection, WebSocket streaming, context telemetry
- **Studio** — Agent configuration editor (CRUD agents, tool toggles, connections)
- **Administration** — Settings display from `GET /api/settings`, provider management via `/api/providers` endpoints (CRUD, connection test, model discovery, key rotation). Provider configurations are stored in the database with encrypted API keys.

Areas register via `App.registerArea({ id, label, icon, order, init, activate, deactivate })`. The `init(sidebar, content)` function receives DOM elements on first activation; `activate()` fires on every switch-to (use for data refresh); `deactivate()` fires on switch-away. CSS is scoped under `.area-{id}`. Shared utilities like `App.escapeHtml()` are available on the `App` object.

The web UI ships with a token-based design system (NEXUS-style cyan accent, Geist Sans + Geist Mono self-hosted, ~20 Lucide SVG icons via `App.icon('name')`) and a tri-state theme switcher (`App.theme.{get,resolved,set}` with `'light'/'dark'/'auto'` semantics, OS-preference fallback, localStorage persistence under key `theme-preference`). The user-facing toggle lives in **Admin → System → Appearance**. Token definitions and the load-bearing contrast pair tables for both themes live in `the_one/agents.md` "Design system" section; per-theme values are mirrored in `tests/browser/design_tokens.py` for tests that assert on token values.

For architecture internals, see `the_one/agents.md`.

## Tool Configuration Layer (M05 Flight 2)

### Two-layer config model
- **Tool-level**: `tool_configs` SQLite table — operator-set defaults shared by all agents.
- **Agent-level**: `AgentConfig.tool_overrides: dict[str, dict[str, Any]] | None` — per-agent narrowing or substitution. NULL means "no overrides set".

### Resolver semantics
`the_one/tools/resolver.py::resolve(schema, tool_config, agent_override)` composes the two layers per-key:
- `Annotated[type, Narrow]`: agent override must be ≤ tool-level value (bool: True→False or equal; int/float: cap; list: subset). Widening raises `ValueError`.
- `Annotated[type, NarrowPrefix]`: agent override on a `list[str]` of paths is narrowing iff every agent entry is a descendant-of (or equal to) at least one tool entry, checked via `the_one.platform.paths.is_within`. Used by `FilesystemConfig.path_allowlist`.
- `Annotated[type, NarrowSuperset]`: agent override on a `list[T]` is narrowing iff every tool entry is also in the agent value (agent ⊇ tool — agent ADDS restrictions). Used by `FilesystemConfig.path_denylist`.
- `Annotated[type, Substitute]`: agent override replaces tool-level value (no comparison). For identity / shared-credential / KV values.
- Fields with multiple markers OR no marker raise `ValueError` on resolve. Markers are mutually exclusive — declare exactly one of `(Narrow, NarrowPrefix, NarrowSuperset, Substitute)`.

### Filesystem constraint surface (F3)
`the_one/tools/filesystem.py::FilesystemConfig` is the per-category Config shared by all 9 filesystem tools. Four fields:
- `path_allowlist: list[str]` (NarrowPrefix) — default `["~"]`.
- `path_denylist: list[str]` (NarrowSuperset) — default 19-entry curated list (system secrets, browser/app data, agent internals, system paths).
- `read_size_cap_bytes: int` (Narrow) — default 1 MiB; bounds `[1024, 100 MB]`.
- `allow_binary_files: bool` (Narrow) — default False; positively-named permission so resolver's True=permissive reading aligns.

Policy refusals raise `ConstraintError`; tool wrappers format as `[error] [constraint] {msg}`. Environmental errors format as `[error] {e}` so agents can distinguish policy refusals from runtime failures. `ConstraintError` lives in `the_one/tools/base.py` (next to the `Tool` ABC — the two-clause `try/except` envelope is the tool authorship contract); `filesystem.py` re-exports it for backward-compat with F3 test imports.

### Execution constraint surface (F4)
`the_one/tools/execution.py::ExecutionConfig` is the per-category Config shared by all 6 execution tools (`shell`, `python_exec`, `shell_session_start`, `shell_session_send`, `shell_session_close`, `shell_session_list`). Six fields plus a cross-field invariant:
- `timeout_seconds_default: int` (Narrow) — default 30s; used when the agent omits `timeout`. Bounds `[1, 3600]`.
- `timeout_seconds_max: int` (Narrow) — default 120s; hard ceiling, agent value clipped to it. Bounds `[1, 3600]`.
- `output_cap_bytes: int` (Narrow) — default 256 KB; combined stdout+stderr tail-preserving cap. Bounds `[1024, 100 MB]`.
- `command_denylist: list[str]` (NarrowSuperset) — default 19-entry curated list (`sudo `, `rm -rf /`, `mkfs`, `shutdown`, fork bomb, etc.). Substring match with trailing-space convention to avoid the `sudoku` false positive. **Trip-wire, not fence** — catches obvious-stupid; not a defence against adversarial agents.
- `pty_session_idle_ttl_seconds: int` (Narrow) — default 5 minutes; reaper closes sessions idle longer than this. Bounds `[10, 3600]`.
- `max_concurrent_sessions: int` (Narrow) — default 5; per-agent cap on simultaneous PTY sessions. Bounds `[1, 50]`.
- `model_validator(mode="after")` enforces `timeout_seconds_default <= timeout_seconds_max` after resolver dispatch (prevents an agent from widening `default` past a narrowed `max`).

`PythonExecConfig(ExecutionConfig)` is a subclass with `timeout_seconds_default = 90` (the cap and all other constraints inherit unchanged). Both Configs are `frozen=True` so the per-call shared `cross_configs` view cannot be mutated by one tool to corrupt another's view.

The 8-key subprocess environment allowlist (`PATH, HOME, USER, LOGNAME, LANG, LC_ALL, TERM, TZ`) is module-level and **NOT operator-configurable** — it lives in `the_one/platform/env.py` (`_ENV_ALLOWLIST` constant, `_build_subprocess_env()` helper) and is enforced at all 3 execution call sites: `the_one/platform/shell.py::run_shell`, `the_one/platform/interpreter.py::run_python`, and `the_one/platform/pty.py::UnixPtySession` (fork-then-execv with `os.environ.clear()` + `os.environ.update(_build_subprocess_env())` in the child before `os.execvp`).

### Web constraint surface (F5)
`the_one/tools/_web_config.py::WebConfig` is the per-category Config shared by all 4 web tools (`http_request`, `fetch_url`, `download_file`, `web_search`). Seven fields:
- `timeout_seconds_default: int` (Narrow) — default 30s; bounds `[1, 3600]`. Used when the agent omits `timeout`.
- `timeout_seconds_max: int` (Narrow) — default 120s; bounds `[1, 3600]`. Hard ceiling, agent value clipped.
- `response_size_cap_bytes: int` (Narrow) — default 1 MiB; bounds `[1024, 100 MB]`. Per-response tail-preserving cap.
- `redirect_cap: int` (Field-only, NO marker) — default 5; bounds `[0, 20]`. Tool-level only — agents cannot narrow this; an agent override on this key raises `ValueError` at agent-build time (Decision 9).
- `host_allowlist: list[str]` (Narrow) — empty default = allow-all; non-empty restricts to those hosts.
- `host_denylist: list[str]` (NarrowSuperset) — default empty.
- `extra_allowed_hosts: list[str]` (Narrow) — operator-named hosts that bypass the SSRF default-block. Host-by-host opt-in for internal addresses.

`model_config = ConfigDict(frozen=True)` mirrors `FilesystemConfig` / `ExecutionConfig`. A `model_validator(mode="after")` enforces `timeout_seconds_default <= timeout_seconds_max` after resolver dispatch.

**Two-layer SSRF enforcement** — `_url_check(url, cfg)` gates scheme / `host_allowlist` / `host_denylist` at the tool boundary; `SSRFGuardedTransport(httpx.AsyncHTTPTransport)` resolves DNS once and pins the connect target to that IP, refusing loopback / link-local / RFC1918 / cloud-metadata / IPv6 ULA + ULL by default. **IP-literal hosts are also gated** by `_is_ssrf_blocked(host)` inside the transport's IP-literal short-circuit branch (HAT scenario 3 inline fix — the pre-fix short-circuit bypassed SSRF for raw `http://169.254.169.254/`, `http://10.0.0.1/`, `http://127.0.0.1/`; the post-fix default-block list refuses raw IP literals BEFORE any connect attempt with `ConstraintError(f"IP literal {host} is in the SSRF block list")`). `extra_allowed_hosts` is honored as an operator override on both the hostname-resolution path and the IP-literal path.

**Mission invariant — "no full-disable"**: `WebConfig` deliberately has no `disable_ssrf` / `ssrf_disabled` / `disable_ssrf_protection` field. SSRF protection is always-on; operators reaching specific internal hosts must list them in `extra_allowed_hosts`. The invariant is encoded by the absence of the field — no enforcement code is needed because the field doesn't exist. Preserve this in any future changes.

The three HTTP tools (`http_request`, `fetch_url`, `download_file`) call a per-tool `_build_transport(cfg) → SSRFGuardedTransport(extra_allowed_hosts=cfg.extra_allowed_hosts)` helper to construct an `httpx.AsyncClient`. `WebSearchTool` does NOT use the SSRF transport — search-engine traffic to the public domain `html.duckduckgo.com` is acceptable as-is in F5; SSRF-pinning of search-backend traffic is a future enhancement if the backend list grows.

### SearchBackend Protocol (F5)
`the_one/tools/_search_backends.py` defines a single-method `Protocol`:

```python
class SearchBackend(Protocol):
    async def search(self, query: str, limit: int) -> list[SearchResult]: ...
```

`DDGSearchBackend` is the F5 default implementation; `SearchResult` is a shared `BaseModel` (title / url / snippet) for shape uniformity across backends. **Backend dispatch is via `cross_configs[SearchBackend]`** (F5 Decision 12 — Protocol-keyed service entry, NOT a constructor parameter): `BuiltinToolProvider.get_tools` constructs a `DDGSearchBackend()` (no client injected) and stores it under `cross_configs[SearchBackend]`; `WebSearchTool` declares `Requires = (SearchBackend,)` and reads `self._cross_configs[SearchBackend]` in `execute`. `DDGSearchBackend.__init__(http_client=None)` defers to its own `httpx.AsyncClient(timeout=15)` per call when no client was injected — that is the F5 production path. Tests inject a fake `SearchBackend` by overriding `cross_configs[SearchBackend]` on the per-call view; no monkeypatching of module internals. Future Brave / SerpAPI / Bing backends implement the same Protocol and slot into the same `cross_configs[SearchBackend]` slot. This is the supported test seam (F5 Decision 2 + Decision 12).

### Cross-Config dispatch (F4)
Tools may declare `Requires: tuple[type[BaseModel], ...] = (FilesystemConfig,)` to receive the resolved `FilesystemConfig` (or any other declared Config) via `cross_configs: dict[type[BaseModel], BaseModel]` passed into `Tool.__init__`. `BuiltinToolProvider.get_tools` builds the per-call shared view once by walking `_TOOL_CLASSES` in declared order. Used by `ShellTool` and `PythonExecTool` to validate `cwd` against the filesystem path-scope, and by `ShellSessionStartTool` / `ShellSessionSendTool` for the same. `DownloadFileTool` (F5 L4) declares the same so destination-path validation flows through `_filesystem_check(path, fs_cfg, CheckMode.WRITE_EXISTING_PARENT)` (post-F5 L0 helper unification — Decision 1; the parent directory must pre-exist, no auto-mkdir — agents call the `mkdir` tool first if needed). `Tool.__init__` also accepts `agent_name: str | None = None` (threaded from `AgentFactory.create()`) — the four session tools key the `_session_registry` on `(agent_name, session_id)` for cross-agent isolation; `agent_name=None` is the introspection path and produces a clean `ConstraintError` from session tools.

### PTY session lifecycle (F4)
PTY sessions ship via `the_one/platform/pty.py::PtySession` ABC (`UnixPtySession` concrete; Windows `ConPTY` deferred to a future mission). Sessions are registered in `the_one/tools/_session_registry.py` keyed on `(agent_name, session_id)`; per-agent `count_for_agent()` enforces the `max_concurrent_sessions` cap; a single asyncio reaper task spawns lazily on first registration and wakes every 30s to close sessions idle past `pty_session_idle_ttl_seconds`. The reaper registers with the FastAPI lifespan so shutdown drains the registry cleanly. Readiness detection uses an idle-mark (`_read_until_idle` blocks until the master_fd has been silent for 100ms, with a 2s hard cap) — robust against shells that emit prompts inconsistently. Per-call denylist re-check applies on every `shell_session_send` (Decision 11) so agents cannot pre-stage a denylisted command behind an open session.

### Dev iteration: source auto-reload
The dev container runs `uvicorn ... --reload --reload-dir /app/the_one` (wired into `docker-compose.yml`'s `command:`). Edits to any file under `./the_one/` propagate to the running server within ~1s via `WatchFiles`; no manual restart needed. `./tests/` is bind-mounted but NOT watched (avoids noise from test edits) — `docker exec the-one pytest ...` still sees fresh test code on every invocation. Historical note: F4 L7 HAT scenario 1 originally exposed the cached-import problem (uvicorn's worker held pre-L3 imports); pre-fix the workaround was `docker compose restart the-one`, post-fix the reload is automatic.

### Session-bound freshness
Resolved tool configs are computed at `AgentFactory.create()` time and held as instance state on each tool. Mid-session operator updates to `tool_configs` rows or `AgentConfig.tool_overrides` apply at the **next** `AgentFactory.create()` invocation, NOT to in-flight agents. F6's admin UI must communicate "applies to next session" clearly.

### Platform abstraction layer
`the_one/platform/` isolates platform-divergent concerns:
- `paths.py` — `canonicalize`, `safe_resolve`, `is_within`
- `shell.py` — `select_shell`, `run_shell` (kill+reap on timeout via `start_new_session=True` + `killpg(SIGKILL)`)
- `interpreter.py` — `resolve_python` (returns `sys.executable`), `run_python`
- `tempdirs.py` — `temp_dir`, `user_home`, `user_config_dir`

F3-F5 populated per-tool Pydantic Configs with real constraint values on top of this seam (`FilesystemConfig`, `ExecutionConfig`, `WebConfig`).

## Tool Authorship Contract

Patterns every tool author must follow. Codifies the F2-F5 patterns; new tools should mirror these or document a deliberate deviation in the leg artifact.

### Envelope shape

**Three-clause envelope (filesystem, execution-without-timeout)**:
```python
try:
    ...
except ConstraintError as e:
    return f"[error] [constraint] {e}"
except Exception as e:
    return f"[error] {e}"
```

**Four-clause envelope (timeout-prone tools — shell, python_exec, pty session, all web tools)**:
```python
try:
    ...
except ConstraintError as e:
    return f"[error] [constraint] {e}"
except (asyncio.TimeoutError, httpx.TimeoutException):  # if httpx
    return f"[error] {tool-specific} timed out after {clipped}s"
except httpx.TooManyRedirects:  # web tools only
    return f"[error] [constraint] exceeded redirect cap of {cfg.redirect_cap}"
except Exception as e:
    return f"[error] {e}"
```

**Critical**: `httpx.TimeoutException` is NOT a subclass of `asyncio.TimeoutError` — any tool that calls httpx must group both in one `except` clause or its production timeouts will fall through to the generic `Exception` clause and return `[error] {e}` instead of the per-tool timeout message. Verified against httpx 0.28.1 MRO (`TimeoutException → TransportError → RequestError → HTTPError → Exception`).

### Float-preserving timeout clip

```python
if timeout is None:
    clipped = cfg.timeout_seconds_default
else:
    clipped = min(timeout, cfg.timeout_seconds_max)
    if clipped <= 0:
        clipped = 1
```

NOT `max(1, min(timeout, max))` — that floors fractional `timeout=0.5` calls to 1, breaking the F2 `test_timeout_returns_promptly` contract.

### Two-phase lock-and-await

Any registry-style state with `asyncio.Lock`: snapshot under lock, release lock, then `await session.close()` (or other long-running cleanup). Holding the lock across the cleanup blocks all other registry operations. See `the_one/tools/_session_registry.py::close` and `_reap_once`.

### Cross-Config dispatch

Tools that need another category's config or service declare:
```python
class MyTool(Tool):
    Config = MyConfig
    Requires = (FilesystemConfig, SearchBackend)  # advisory; declarative
```
And consume via:
```python
fs_cfg = self._cross_configs[FilesystemConfig]
backend = self._cross_configs[SearchBackend]
```

`cross_configs` is `dict[type, object]`. Two categories of entries (introduced in F4 + F5):
- **Pydantic Configs** (`FilesystemConfig`, `ExecutionConfig`, `PythonExecConfig`, `WebConfig`): frozen via `ConfigDict(frozen=True)` so shared-by-reference across tool instances cannot be mutated.
- **Protocol-keyed services** (`SearchBackend`): per-`get_tools()`-call-fresh; not frozen because they own stateful resources (e.g., `httpx.AsyncClient`). Per-call lifecycle replaces frozenness as the safety mechanism — every agent invocation gets a fresh provider call.

When introducing a new typed dispatch slot, pre-declare which category it belongs to in the leg artifact.

### Pydantic v2 `json_schema_extra` does NOT inherit on `Annotated` re-declaration

Subclassing a Config and re-declaring a field with a different default (e.g., F4's `PythonExecConfig.timeout_seconds_default = 90`) loses the parent's `json_schema_extra` (including `ui_choices`). Hoist shared metadata to module-level constants and re-reference in both the parent and the override.

### Frozen Configs for cross-tool sharing

Any Config that gets passed via `cross_configs` (i.e., declared in any tool's `Requires`) must be `model_config = ConfigDict(frozen=True)`. This is methodology, not per-flight discretion.

### Scaffolding-leg consumer test

A leg that introduces helpers WITHOUT immediately wiring them through a tool must ship a "stub-tool" consumer test that exercises the helpers end-to-end through a tool-shaped scenario. F4 L2 surfaced this requirement (helper formatting drift discovered at L3 integration); F5 L1 followed and caught real issues in `tests/test_web_stub_tool.py`. Mandatory pattern.

### `_build_transport(cfg)` test seam (web tools)

Each web tool defines a one-line `_build_transport` method returning the SSRF-guarded transport. Tests monkeypatch `MyWebTool._build_transport` to inject `httpx.MockTransport(handler)` and bypass SSRF. Per-tool isolation (vs a shared base-class helper) keeps test seams independent. Document copies of this pattern as deliberate, not as duplication for refactor.

### `_safe_unlink(target)` for cleanup-before-streaming

When a tool creates an artifact (file, session, etc.) BEFORE a streaming or long-running operation begins, every error clause must clean up the partial artifact. F5 L4 caught this for `download_file`: `target.open("wb")` creates the file before `client.stream()` runs, so a `TooManyRedirects` or `TimeoutException` mid-stream leaves an empty file. The `_safe_unlink(target)` helper at module level is called from each error clause; the `if target is None` guard handles the case where `_filesystem_check` raised before `target` was bound.

### Library-API drift checklist

Any leg touching a third-party library must document the installed version and verify the API shape against current docs (not training-cutoff knowledge). The architect-review-per-leg cycle has caught 5+ high-severity items in this class across F4-F5 (httpx SNI extension API, `asyncio.get_running_loop` vs deprecated `get_event_loop`, Pydantic v2 `json_schema_extra` non-inheritance, lxml install path, httpx exception MRO). Cheap to verify; expensive to miss.

### F6 admin UI patterns

F6 added the operator-facing tool admin surface (Settings → Built-in Tools) plus the Studio per-agent override panels. The patterns below are mandatory for any future flight extending tool config UI.

**Operator-set kill switch** — schema v9 added `tool_configs.enabled INTEGER NOT NULL DEFAULT 1`; `ToolConfig.enabled: bool = True` mirrors it in the Pydantic model. `AgentFactory.create()` (`the_one/agent/factory.py:108-136`) projects `repo.list()` into `tool_configs_by_name: dict[str, dict]` AND `disabled_names: set[str]`, and the registry-build filter composes `tool.name not in disabled_names AND config.is_tool_enabled(tool.name)`. `BuiltinToolProvider.get_tools()` (no-arg introspection path) is intentionally NOT modified — the disable filter lives ONLY at the factory boundary so admin surfaces (`GET /api/tools/configs`, the L2 grid) can render disabled tools as such.

**Marker enrichment for admin UI** — Pydantic v2's `Model.model_json_schema()` strips marker classes (`Narrow` / `NarrowPrefix` / `NarrowSuperset` / `Substitute`). Server-side helper `_enrich_schema_with_markers(schema, config_class)` at `the_one/interfaces/web/api.py:75-115` walks `field_info.metadata` with identity checks (`m is Narrow`, etc., same pattern as `the_one/tools/resolver.py:233-236`) and injects `x_marker` per top-level property. Tool authors who introduce new marker classes MUST extend the helper's `marker_map`. Assumes flat schemas (no nested BaseModel under `$defs`); a future Config nesting another model needs a `$defs` walk added.

**REPLACE-not-merge PUT contract** — `PUT /api/tools/configs/{name}` accepts `{enabled?: bool, config?: dict}`. When `config` is present in the body, REPLACES the saved config wholesale (REST PUT convention). When omitted, preserves the existing saved config. Top-level `enabled` is preserved when omitted. The L3 form always submits the full state, so REPLACE matches its actual behaviour. To wipe to defaults, send `{"config": {}}` — distinguishes from "config absent" (preserve).

**JSON-encoding of `ValidationError.errors()`** — Pydantic v2's `model_validator` paths populate `ctx['error']` with a raw exception, which is NOT JSON-serializable. Without `include_context=False` on `e.errors()`, FastAPI's JSONResponse crashes and surfaces 500 instead of 422. Always pass `include_context=False` when constructing `HTTPException(status_code=422, detail=e.errors(...))`. See `api.py:236-247` for the canonical pattern.

**Named-tool isolation in test endpoint** — `BuiltinToolProvider.get_tools` builds `cross_configs[Config]` by walking `_TOOL_CLASSES` in declared order and resolving from the FIRST tool name carrying that Config. For `WebConfig` that's `http_request`. The test endpoint (`POST /api/tools/configs/{name}/test`) re-keys EVERY tool sharing the named tool's Config class to use the named tool's saved row — so `cross_configs[NamedConfig]` carries the tested tool's saved config regardless of declaration order. See `api.py:297-303`. This differs from the agent runtime, where the FIRST-declared-tool semantics intentionally apply (operator policy is unified across same-Config tools at agent-create time).

**Agent-mode marker dispatch** (Studio Tools tab override panels at `the_one/interfaces/web/static/js/areas/admin/tools-form-helpers.js`):
- `Narrow` (int) → `<input type=number min={prop.minimum} max={operator_value}>` — operator's saved value as ceiling, schema floor preserved.
- `Narrow` (list[str]) → chip-list constrained to subset of operator's items.
- `NarrowSuperset` (list[str]) → chip-list with operator's items as **locked chips** rendered WITHOUT the `<button class="chip-remove">` element entirely (NOT just CSS-hidden — keyboard focus order skips them; screen readers don't announce a remove affordance).
- `NarrowPrefix` (list[str]) → chip-list (the prefix semantic is purely server-side validation in the resolver).
- `Substitute` (any) → free-form input typed to the field's base type.
- Unmarked field (e.g., `WebConfig.redirect_cap`) → HIDDEN from the agent override surface entirely. The F2 resolver raises `ValueError("... no Narrow/Substitute marker ...")` on agent override of an unmarked field.

**`tool_overrides` shape** — `AgentConfig.tool_overrides: dict[str, dict[str, Any]] | None = None` at `the_one/agent/config.py:65`. Empty dict semantics: `null` (NOT `{}`) when no overrides set; per-tool entries appear only when at least one field is set. Save path (`studio.js::collectFormData`) walks `[data-tool-override-tool][data-tool-override-field]` inputs, drops empty per-tool entries, returns `null` for empty top-level. Round-trip pinned by `tests/test_agent_tool_overrides_round_trip.py`.

**Schema migration v9 pattern** — idempotent `ALTER TABLE ... ADD COLUMN` guarded by `PRAGMA table_info`; individual `await conn.execute(...)` calls (NOT `executescript`); `INSERT OR IGNORE INTO schema_version` LAST. New columns must be `NOT NULL` with explicit `DEFAULT` to avoid orphaned NULL rows on existing data. Mirrors v8 (`schema.py:292-336`); v9 lives at `schema.py:338-360`.

**iOS-toggle CSS positioning trap** — the grid tile's `.tool-enable-switch` is `position: absolute; bottom: 12px; right: 12px;` (designed for a `position: relative` tile container). Reusing the same widget inside an editor row requires an unpinning override (`.tools-editor-enabled-row .tool-enable-switch { position: relative; bottom: auto; right: auto; }`) — without this, the toggle floats off-screen relative to the document. See `admin.css:243-252` for the override.

**Shared form helpers** — `window.App.adminFormHelpers` (at `the_one/interfaces/web/static/js/areas/admin/tools-form-helpers.js`) is the canonical form-rendering substrate, consumed by both admin (`tools-editor.js`) and Studio (`studio/tools-tab.js`). Future flights extending tool-config UI consume these helpers via the context object: `{mode: 'admin' | 'agent', operatorValue?: any, attrPrefix: 'data-field' | 'data-tool-override-field', toolName?: string}`. Owned by `admin/` because admin was the first consumer; future migration to `shared/` if a third area imports.

**Lazy schema fetch caches the PROMISE** — Studio's per-agent override panels lazy-fetch each tool's schema on first `<details>` open. The closure cache stores the in-flight Promise (NOT the resolved value), so concurrent callers (operator opens + closes + opens fast) reuse the same fetch. The cache survives across agent changes within the studio area lifetime — schemas are static at runtime. Operator's saved `tool_configs` and `disabledTools` are RE-fetched on every agent-edit mount (those can change between tabs).

**Validation-error humanization** — Pydantic v2's raw error messages start with prefixes like `"Value error, "` / `"Input should be "` / `"Assertion failed, "`. The L3 editor's `humanizeValidationMsg` helper (mirrored in `tools-editor.js` and `tools-form-helpers.js`) strips these and capitalizes the first character. Model-level errors (`loc: []`) render in the prominent `.editor-error-banner` above the Configuration section; field-level errors (`loc` matching a `[data-field-name]` row) render inline next to the field via `.field-error`. Heuristic field-name matching for model-level errors highlights the offending rows via `.field-error-highlight` (red border + label tint).

## Configuration

Runtime config via env vars prefixed `THE_ONE_` (see `.env.example`): host, port, data_dir, dev_mode. Managed by pydantic-settings in `the_one/config.py`. The `settings` singleton is imported directly. LLM provider configuration is managed through the database (not env vars) — see the `/api/providers` endpoints.

### Dev mode and the mock provider

When `THE_ONE_DEV_MODE=true` is set, a fifth provider type `mock` becomes available alongside `ollama`, `openai-compatible`, `openai`, and `anthropic`. The mock provider returns deterministic scripted responses sourced from its `LLMProviderConfig.config["response"]` field — defaults to `"Mock response from the mock provider."` if no `response` key is set. Used by browser tests for deterministic chat flows; also useful for offline dev work and demos.

- Backend rejects mock-typed creates/updates with HTTP 400 when dev mode is off
- UI dropdown filters out `mock` when dev mode is off (driven by `GET /api/providers/types`)
- Existing mock providers continue to render correctly in the admin UI even after dev mode is later disabled (the `TYPE_DEFAULTS` defaults and the `KNOWN_BADGE_TYPES` array are unconditional, so the badge styling resolves regardless of dev_mode)

## Conventions

- Python 3.11+, async throughout
- ruff for linting (rules: E, F, I, N, W) and formatting, line length 100
- Tools return strings, errors are caught and wrapped by the agent loop
- LLM provider schemas default to OpenAI function-calling format; override `tool_schema()` for others

## HAT Design Guidance

For UI-heavy flights, structure HAT steps as **state transition sequences** rather than isolated checks. Name each transition explicitly and include multiple assertions per state (UI elements, error area, button states). Include negative assertions ("no error messages") to catch race conditions and leftover state.

Example format:
```
1. [no-setup]: Open Chat with empty DB
   - Banner: "Getting started..."
   - Session list: empty, no auto-create
   - No error messages
2. [no-setup] -> [provider-only]: Add provider, switch to Chat
   - Banner updates to "No agents..."
   - No error messages (catches race conditions)
3. [provider-only] -> [fully-configured]: Create agent, switch to Chat
   - Banner: gone
   - Session auto-created
```

This format caught three bugs during Flight 04 HAT that end-state-only specs missed (simultaneous banner + error, race condition on auto-join, stuck button state). If this approach proves effective across 2-3 more flights, recommend a permanent update to the mission-control leg skill to include state-transition guidance for UI-focused HAT legs.

## Testing

**Unit tests** run by default with `pytest tests/` — fast, no external dependencies, ~212 tests in <6s.

**Color contrast tests** (`tests/test_design_tokens_a11y.py`): WCAG 2.1 AA contrast audits for the F2 design tokens. Run via default `pytest tests/`. See `the_one/agents.md` "Color contrast (WCAG AA)" for the audited pairs and any deliberate exceptions.

**Visual snapshot tests** (`tests/browser/test_visual_snapshots.py`): 12 Playwright baseline screenshots covering 3 UI areas × 2 states × 2 themes. Run via `pytest -m browser tests/browser/test_visual_snapshots.py`. Baselines live in `tests/browser/__snapshots__/`; tolerance 2% pixel diff. Regenerate with `--snapshot-update` (commit baselines to git; CI compares only).

**Token-definition test** (`tests/test_token_definitions.py`): asserts every `var(--x)` reference in component CSS is defined in `tokens.css` or `fonts.css`. Catches typos that CSS would silently treat as `unset`.

**AIAT tests** (Agent-in-a-Test) are live integration tests that hit a running instance. They are excluded from default runs via `addopts = "-m 'not live'"` in `pyproject.toml`.

- **`THE_ONE_TEST_URL`** env var sets the target URL (default `http://localhost:8484`)
- **`@pytest.mark.live`** decorator marks AIAT tests — all live in `tests/test_aiat.py`
- Run live tests: `pytest -m live tests/test_aiat.py`

**Browser tests** are end-to-end browser-driven tests using Playwright. They are excluded from default runs via `addopts = "-m 'not live and not browser'"` in `pyproject.toml`.

- **`@pytest.mark.browser`** marks browser tests — all live in `tests/browser/`
- Run browser tests: `pytest -m browser tests/browser/`
- Each test spawns its own app subprocess on a random port with an isolated `tmp_path` data_dir; teardown via SIGTERM
- Mock LLM responses are deterministic via the `mock` provider type (see below)
- See `tests/browser/conftest.py` for fixture documentation

**Test patterns** (no mock libraries):

- **`FakeLLM`** (`tests/conftest.py`): An `LLMProvider` subclass that returns pre-scripted `Message` responses in order. Records all calls for assertion. Enables deterministic agent loop testing.
- **`StubTool`** (`tests/conftest.py`): A `Tool` subclass that records calls and returns a canned string. Used to verify the agent executes tools correctly without side effects.
- **`make_registry`** fixture: Creates a `ToolRegistry` pre-loaded with StubTools for quick test setup.
