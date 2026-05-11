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

**Agent loop** (`the_one/agent/core.py`) — The `Agent` class runs: user input → LLM call → tool execution → repeat until no tool calls remain. The agent uses a virtual `CONTINUE_SCHEMA` (defined inline in `core.py`) as a turn-keeping signal — when the LLM calls `continue`, the loop registers another iteration. Max 20 iterations per step as a safety limit. **Capability gate**: when `LLMProvider.supports_tools()` returns False (e.g. Ollama Gemma — `/api/show` capabilities lack `"tools"`), the agent drops both real tool schemas AND `CONTINUE_SCHEMA` from the wire payload and runs a single LLM iteration as plain chat. Silent fallback by design — Studio's red `no tools` capability chip on the model selector is the only operator-facing signal.

Agent configuration (`agent/config.py`) defines `AgentConfig` (Pydantic model) with `provider_config_id` (FK to `llm_providers`), `llm_model`, prompt, tool filtering, and behavior settings. `AgentFactory` (`agent/factory.py`) resolves the provider config from DB, maps the provider type to the registry name, and wires config + LLM + tools into a ready-to-use Agent. Agent configs persist via `SQLiteAgentStore` in the DB.

**Persistence** (`the_one/db/`) — SQLite via aiosqlite. `get_connection()` returns a shared async connection. Repository classes (`SQLiteAgentStore`, `KnowledgeBaseRepository`, `MCPSourceRepository`, `ChatSessionRepository`, `KBItemRepository`, `LLMProviderRepository`) each wrap a table with CRUD operations over Pydantic models. `LLMProviderRepository` takes an `Encryptor` for transparent encrypt-on-write / decrypt-on-read of API keys. Schema is versioned (currently v7) and auto-migrated on first connection.

**Encryption** (`the_one/encryption.py`) — Fernet symmetric encryption for API credentials. Key auto-generated at `{data_dir}/encryption.key` (mode 0600). `get_encryptor(data_dir)` returns an `Encryptor` instance. Supports key rotation via `rotate_key()`.

### `__MASKED__` sentinel for API key updates

The provider edit form sends the literal string `__MASKED__` as the `api_key` field when the user has not modified it. The backend (`update_provider` in `interfaces/web/api.py`) detects this sentinel and preserves the existing stored key rather than overwriting it with the masked display value. Anyone touching the provider edit form needs to know this contract.

**Interfaces** (`the_one/interfaces/`) — CLI (Rich + prompt-toolkit) and Web (FastAPI + WebSocket). Both use `AgentFactory.create()` to get configured agents, then call `agent.step(user_input)` which yields messages. The web app adds session management and broadcasts events to WebSocket subscribers.

The web UI has three functional areas sharing a sidebar + content panel layout:
- **Chat** — Multi-session chat with agent selection, WebSocket streaming, context telemetry
- **Studio** — Agent configuration editor (CRUD agents, tool toggles, connections)
- **Administration** — General page (Appearance theme toggle, Encryption key rotation, read-only Base Prompt; section id stays `system` for URL stability), provider management via `/api/providers` endpoints (CRUD, connection test, model discovery, key rotation), and the Built-in Tools admin grid via `/api/tools/configs`. Provider configurations are stored in the database with encrypted API keys.

Areas register via `App.registerArea({ id, label, icon, order, init, activate, deactivate })`. The `init(sidebar, content)` function receives DOM elements on first activation; `activate()` fires on every switch-to (use for data refresh); `deactivate()` fires on switch-away. CSS is scoped under `.area-{id}`. Shared utilities like `App.escapeHtml()` are available on the `App` object.

The web UI ships with a token-based design system (GleepGlorp violet accent — originally NEXUS-style cyan, retuned in Mission 08; Geist Sans + Geist Mono self-hosted, ~20 Lucide SVG icons via `App.icon('name')`) and a tri-state theme switcher (`App.theme.{get,resolved,set}` with `'light'/'dark'/'auto'` semantics, OS-preference fallback, localStorage persistence under key `theme-preference`). The user-facing toggle lives in **Admin → General → Appearance**. Token definitions and the load-bearing contrast pair tables for both themes live in `the_one/agents.md` "Design system" section; per-theme values are mirrored in `tests/browser/design_tokens.py` for tests that assert on token values.

For architecture internals, see `the_one/agents.md`. Project-wide conventions (`trust-the-runtime`, `canonical-import + convenience-re-export`, `structural-Protocol-satisfaction`, `verbatim-message-equality`) live in `the_one/agents.md`'s "Project Conventions" section.

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

**Agent-mode marker dispatch** (Studio Built-in Tools tab override panels at `the_one/interfaces/web/static/js/areas/admin/tools-form-helpers.js`):
- `Narrow` (int) → `<input type=number min={prop.minimum} max={operator_value}>` — operator's saved value as ceiling, schema floor preserved.
- `Narrow` (list[str]) → chip-list constrained to subset of operator's items.
- `NarrowSuperset` (list[str]) → chip-list with operator's items as **locked chips** rendered WITHOUT the `<button class="chip-remove">` element entirely (NOT just CSS-hidden — keyboard focus order skips them; screen readers don't announce a remove affordance).
- `NarrowPrefix` (list[str]) → chip-list (the prefix semantic is purely server-side validation in the resolver).
- `Substitute` (any) → free-form input typed to the field's base type.
- Unmarked field (e.g., `WebConfig.redirect_cap`) → HIDDEN from the agent override surface entirely. The F2 resolver raises `ValueError("... no Narrow/Substitute marker ...")` on agent override of an unmarked field.

**`tool_overrides` shape** — `AgentConfig.tool_overrides: dict[str, dict[str, Any]] | None = None` at `the_one/agent/config.py:65`. Empty dict semantics: `null` (NOT `{}`) when no overrides set; per-tool entries appear only when at least one field is set. Save path (`studio.js::collectFormData`) walks `[data-tool-override-tool][data-tool-override-field]` inputs, drops empty per-tool entries, returns `null` for empty top-level. Round-trip pinned by `tests/test_agent_tool_overrides_round_trip.py`.

**Schema migration v9 pattern** — idempotent `ALTER TABLE ... ADD COLUMN` guarded by `PRAGMA table_info`; individual `await conn.execute(...)` calls (NOT `executescript`); `INSERT OR IGNORE INTO schema_version` LAST. New columns must be `NOT NULL` with explicit `DEFAULT` to avoid orphaned NULL rows on existing data. Mirrors v8 (`schema.py:292-336`); v9 lives at `schema.py:338-360`.

**Schema migration v10 pattern (M07 F1)** — whole-table-rebuild ceremony (CREATE new + INSERT-SELECT old + DROP old + RENAME new under `PRAGMA foreign_keys=OFF/ON` brackets) using v8/v9's individual-execute pattern (NOT `executescript`) and `INSERT OR IGNORE INTO schema_version` LAST for retry-on-partial-apply safety. Required because SQLite has no `ALTER TABLE DROP CONSTRAINT` and v10 changed `mcp_sources`'s CHECK constraint (`type IN ('stdio', 'sse')` → `type IN ('stdio', 'streamable-http')`) AND added a `secrets TEXT NOT NULL DEFAULT '{}'` column. The deprecated `'sse'` literal rename is applied inline via `CASE WHEN type='sse' THEN 'streamable-http' ELSE type END` inside the `INSERT INTO mcp_sources_new SELECT ...` step — NOT a pre-rebuild `UPDATE` on the old table, since the still-active old CHECK constraint would reject the literal `'streamable-http'` if written before the constraint swap. Lives at `schema.py:362-...`.

**MCP source storage contract (authoritative for F2-F8)** — `mcp_sources` schema v10 uses **field-segregated encryption with two columns**: `config TEXT DEFAULT '{}'` plaintext (transport, command, args, URL, non-sensitive headers, OAuth issuer/client_id/scopes/redirect_uri); `secrets TEXT DEFAULT '{}'` encrypted (single Fernet ciphertext over a JSON dict of operator-marked sensitive field values). The `MCPSource` Pydantic model (`the_one/db/models.py`) exposes both fields plus `merged_config()` for callers that need a flat dict. `MCPSourceRepository` stores the `Encryptor` **as a reference, not a copy** so `Encryptor.install_key()` post-rotation propagates to live instances (mirrors `LLMProviderRepository`). The `__MASKED__` sentinel extends to a **per-key semantic on the `secrets` dict**: an incoming `secrets[key] == "__MASKED__"` on PUT preserves the existing stored value for that key; other keys overwrite. GET masks each value individually as `***...{tail4}` (or `***` for `<=4` chars), never the full encrypted blob.

**OAuth `client_secret` payload-key contract** — F1 routes the OAuth client secret to `secrets["oauth_client_secret"]` (top-level on the `secrets` dict), NOT `config.oauth.client_secret`. F5 will look up by this exact key when implementing the live OAuth flow. Routing the secret elsewhere would leak through any code path reading `config` plaintext.

**Encryption rotation invariant: no non-DML between SELECT and commit** — `/api/encryption/rotate` (`api.py`) re-encrypts every `llm_providers.api_key` AND every `mcp_sources.secrets` blob in a single auto-begin transaction: SELECT all rows from BOTH tables → re-encrypt all in memory → single UPDATE loop covering both tables → single `commit()` → file replace via `os.replace`. **No PRAGMA, no DDL, no `CREATE TEMP TABLE` between the SELECTs and the commit** — aiosqlite's default isolation mode silently COMMITs before any non-DML statement (per `schema.py` v8 docstring), which would break the all-or-nothing rotation invariant. This rule, originally a v8-migration constraint, is now also the rotation-endpoint constraint and applies to any future rotation extension.

## F2 (MCP Client Foundation) Contracts (authoritative for F3-F8)

**1. Module layout** — The MCP client foundation lives at `the_one/mcp/{__init__.py, client.py, errors.py, types.py, transports/{__init__.py, stdio.py, streamable_http.py}}`. This is a **peer of `the_one/llm/`**, NOT a sub-package of `the_one/tools/`. MCPClient is a service abstraction (transport + lifecycle); F6 wraps individual MCPTools into the project's existing `Tool` abstraction via a separate `MCPToolProvider`.

**2. `_PINNED_PROTOCOL_VERSION` constant** — Defined in `the_one/mcp/__init__.py` as `"2025-11-25"` (matches `mcp.types.LATEST_PROTOCOL_VERSION` for SDK pin `mcp==1.27.0`). **Upgrade procedure**: bump the SDK pin in `pyproject.toml` → run `python -c "from mcp.types import LATEST_PROTOCOL_VERSION; print(LATEST_PROTOCOL_VERSION)"` → update the constant → run integration tests against a fresh fixture build → confirm the version-mismatch test (`test_pinned_protocol_version_matches_sdk`) still passes. **Read at call time** via `the_one.mcp._PINNED_PROTOCOL_VERSION`, NOT `from the_one.mcp import _PINNED_PROTOCOL_VERSION` — the latter binds at module-load time and breaks `monkeypatch.setattr` in tests.

**3. F4-pool compatibility invariants** — `MCPClient` instances expose `is_alive: bool` (false until `connect()` returns; true thereafter; false from `disconnect()` start) and `last_activity: float` (monotonic-clock timestamp, updated on every `list_tools`/`call_tool`). `disconnect()` is **idempotent and never raises**. Instances carry no thread-locals and no module-globals. Naming is **deliberately aligned with `PtySession`** (`the_one/platform/pty.py`) so F4 builds one reaper code path that handles both abstractions.

**4. `build_stdio_environ` helper signature** — `build_stdio_environ(source: MCPSource, allowlist_env: dict[str, str]) -> dict[str, str]` performs a 2-layer flat merge: `allowlist_env` ∪ `(config.env ∪ secrets)`, with secrets winning on collision. **Do NOT consume `MCPSource.merged_config()` for stdio environ assembly** — that helper produces a flat top-level merge that would inject `command`/`args`/etc. as env-var-shaped keys into the spawned subprocess. Future maintainer caution: don't "fix" this back to `merged_config()`.

**5. Fail-hard version-handshake stance** — `MCPClient.connect()` raises `MCPVersionMismatch` when the server's announced `protocolVersion != _PINNED_PROTOCOL_VERSION` (exact match required). This is **narrower than the SDK's `SUPPORTED_PROTOCOL_VERSIONS` whitelist**; the SDK's own `RuntimeError` from `session.initialize()` on truly-unsupported versions is caught and re-raised as `MCPVersionMismatch` so operators see one consistent error type. Pre-release stance; revisit at 1.0.

**6. `MCPTool` and `MCPToolResult` dataclass shapes** — Both are `@dataclass(frozen=True)` defined in `the_one/mcp/types.py`. `MCPTool` fields: `name`, `description`, `input_schema`, `output_schema`, `annotations` (per flight §5b). `MCPToolResult` fields: `text`, `raw`, `structured`, `is_error` (per flight §4). F6 reads `MCPTool` to wrap as `Tool` instances; F7 reads `MCPToolResult.raw` for the inspector trace pane; the agent loop reads `MCPToolResult.text` for tool-result rendering.

## F3 (MCP Sandbox) Contracts (authoritative for F4-F8)

The F3 sandbox layer wraps every locally-spawned stdio MCP server in a strict-by-default bubblewrap (`bwrap`) jail on Linux. The contracts below paraphrase F3 flight design decisions §1, §4, §6, §10, §11, §12, §13. Forward-references to symbols that don't yet exist in the tree (e.g. `MCPSandbox`, `SandboxProfile`, `SpawnSpec`, `MCPSandboxError`) carry an explicit "L2/L3/L4 lands" qualifier so a reader landing between L1b and L2 knows where each symbol arrives.

**1. Module home** — Sandbox runtime code lives at `the_one/platform/sandbox/{__init__.py, base.py, bubblewrap.py}` (peer of `the_one/platform/env.py` and `the_one/platform/pty.py`). The `MCPSandboxError` exception lives canonically at `the_one/mcp/errors.py` (alongside other `MCPClientError` subclasses); `the_one/platform/sandbox/__init__.py` re-exports it for convenience but the canonical import path is `from the_one.mcp.errors import MCPSandboxError`. **L2 lands the actual code; this entry documents the contract for readers landing between L1b and L2.**

**2. Strict-by-default trust model (§1)** — Locally-spawned MCP server processes get a sandbox whose default posture is read-only filesystem outside an explicit operator-configured `writable_paths` list; network OFF unless `network_allowed=True`. Mission constraint #47's "trip-wire, not fence" framing applies in the OTHER direction here: the env-allowlist alone is a trip-wire, but bwrap is the actual fence. Operator-trust threat model: the operator is responsible for not configuring untrusted MCP sources with broad `writable_paths` or `network_allowed=True`; the sandbox does not claim to defend against operator mistakes, only against MCP-author mistakes / supply-chain compromises within the sandboxed scope.

**3. Sandbox profile storage (§4)** — `MCPSource.config["sandbox"] = {"writable_paths": list[str], "network_allowed": bool}` lives plaintext alongside `command`/`args`/`env` (NOT encrypted; no secrets here, just policy). Both fields are optional; defaults are `[]` and `false` when absent. Reserved namespace-flag fields (`pid_unshare`, `ipc_unshare`, `uts_unshare`, all bool-defaulting-True per §12) live in the same dict as advanced JSON-edit-only knobs; the API validator passes them through without inspection per "unknown keys ignored." NOT a separate column / NOT a separate table — the `mcp_sources` schema is unchanged from F1's v10. **L1b extends `_validate_mcp_source_config` with this sub-block validator at the API boundary; L2 lands `SandboxProfile.from_dict` for the runtime side.**

**4. `MCPSandbox` Protocol shape (§11)** — `prepare_spawn(profile: SandboxProfile, command: str, args: list[str], env: dict[str, str], cwd: str | None = None) -> SpawnSpec`. `SpawnSpec` is a `@dataclass(frozen=True)` with `command/args/env/cwd` plus Windows-only `creation_flags: int = 0` and `attribute_list: dict[str, Any] | None = None`. Linux/macOS callers feed `spec.command/args/env/cwd` directly into `mcp.client.stdio.StdioServerParameters(...)`; the Windows fields exist purely so a future Windows backend can populate them without changing the Protocol. **L2 lands the Protocol; L3 implements `BubblewrapSandbox.prepare_spawn`; L4 wires it into `connect_stdio`.**

**5. `MCPSandboxError(MCPClientError)` failure-mode boundary (§6)** — Failures BEFORE bwrap successfully wraps-and-execs the target command raise `MCPSandboxError` (bwrap binary missing, `writable_paths` entry doesn't exist, `EPERM` on `unshare`, container lacks the §10 privilege grants). Failures AFTER (target spawned but exits non-zero, initialize handshake fails) raise the existing `MCPConnectionError` / `MCPVersionMismatch` per F2. There is NO unsandboxed fallback; production never reads `THE_ONE_SANDBOX_DISABLED`. The three §6 catalog messages are: **#1** `"MCP sandbox setup failed: writable_paths entry {path!r} does not exist. Create the directory or remove from writable_paths."`; **#2** `"MCP sandbox setup failed: bubblewrap exited non-zero. Check that the dev/CI environment has cap_add: SYS_ADMIN AND security_opt: seccomp:unconfined per F3 design decision §10. bwrap stderr: {snippet!r}"` (snippet is ≤500 chars of stripped captured stderr; the synthetic exit-code interpolation that earlier revisions had is dropped — the SDK doesn't surface bwrap's exit code observably); **#3** `"MCP sandbox setup failed: namespace creation refused (EPERM on unshare). The container likely lacks the privilege grants required by §10."`. The bwrap-prefix discriminator (`_BWRAP_OWN_PREFIX_RE` matching `^\s*bwrap:`) gates patterns #2/#3 so inner-process failures (post-bwrap-success) continue to surface as `MCPConnectionError`. **L2 adds the exception class AND enforces the boundary in `connect_stdio` via stderr-capture-and-translate (via SDK `errlog=` parameter); flight 04 leg 02 lands the enforcement.** **Post-L4 runtime invariants**: see `the_one/mcp/README.md` for the full sandbox-wrap composition + pool semantics (sections §7 and §8).

**6. Privilege model: dev container, browser-test CI, production (§10)** — Dev container: `cap_add: [SYS_ADMIN]` AND `security_opt: [seccomp:unconfined]` (BOTH; SYS_ADMIN alone is filtered by docker's default seccomp profile per L1a's pre-§10 baseline `unshare(CLONE_NEWUSER) → EPERM`). Browser-test CI image (`mcr.microsoft.com/playwright/python:v1.58.0-jammy`): no privilege grants; `THE_ONE_SANDBOX_DISABLED=1` AND `THE_ONE_TEST_MODE=1` (BOTH; the double-flag is set ONLY by `tests/conftest.py::pytest_configure`, never in any image-level env source). Production: no flag, no skip — bwrap is mandatory; `MCPSandboxError` raises if missing. **Operational guardrail**: `THE_ONE_TEST_MODE` MUST NOT appear in any Dockerfile, docker-compose service env, entrypoint script, k8s manifest, or CI variable; presence outside pytest is a deployment defect. **L1a verified the dev-container privilege grant lifted `unshare -U` EPERM via the 5-assertion probe; L4 wires the double-flag bypass.**

**7. HOME override under sandbox (§13)** — `BubblewrapSandbox.prepare_spawn` overrides `env["HOME"] = "/tmp"` regardless of operator-supplied env. Reasoning: the assembled environ inherits HOME from the host (likely `/root` in the dev container), and `--ro-bind / /` makes `/root` read-accessible-but-not-writable, so subprocesses writing to `~/.cache` would hit EACCES; `/tmp` is writable via `--tmpfs /tmp`. **Operators cannot override HOME via the kv-table** — this is sandbox policy, not operator-configurable. Operators needing a specific HOME add the path to `writable_paths` AND set a different env var (e.g. `MY_HOME`) pointing at it. **L3 implements the override.**

- Forward-references in this section name symbols (`MCPSandbox`, `SandboxProfile`, `SpawnSpec`, `MCPSandboxError`) that L2 lands; this F3 contract section is authoritative for the contracts, and the symbols themselves are authoritative for the implementation. Readers landing between L1b and L2 should treat the symbols as named-but-not-yet-importable.

## MCP Error Translation Contracts

`MCPClient.{connect, list_tools, call_tool}` raise one of: `MCPVersionMismatch`, `MCPAuthRequired`, `MCPSandboxError` (stdio only), or `MCPConnectionError` (catchall). `MCPToolProvider.get_tools_for_agent` graceful-skips all four. Adding a fifth typed exception requires updating BOTH the translator and the consumer's match list.

**Nested `try/except*` for `connect()`** — Python (PEP 654) forbids mixing `except` and `except*` in one block, so when an existing `except RuntimeError` must stay (version-mismatch path), the new OAuth `except*` nests inside its own innermost `try`. See `the_one/mcp/client.py:238-273`. `list_tools`/`call_tool` use a flat shape because they have no `except` siblings to preserve. Don't "tidy up" the asymmetry.

**`connect()` translates 401 from three distinct sources** — inner `except* (OAuthFlowError, OAuthTokenError)` (SDK auth pre-HTTP), outer `BaseExceptionGroup.subgroup(httpx.HTTPStatusError)` walk (server 401 with `WWW-Authenticate` → `resource_metadata_url`), and `except asyncio.CancelledError` (cleanup-deadlock races, post-F6.6 narrowed to non-OAuth/non-401 only — narrowing is preserved by comments, not structure). Don't collapse them.

**No `except MCPAuthRequired: raise` guard needed in `connect()`** — its outer `except (MCPClientError, NotImplementedError): … raise` already propagates `MCPAuthRequired` cleanly. `list_tools`/`call_tool` DO need the guard because their outer `except McpError` would re-wrap. Asymmetry by design.

**Synthetic chat-session-id pattern** — three csid shapes pass through `the_one/mcp/oauth/handlers.py::redirect_handler`: real csids (12-char `[0-9a-f]` hex, per chat WS), `f"test:{source_id}"` (Test connection endpoint), `f"agent_build:{source.id}"` (`_pool._entry_worker` when OAuth tokens persisted outside a chat path). Disjoint by character-set construction — hex cannot produce `:`. Synthetic csids no-op the `auth_required` broadcast (no chat UI to surface a modal). Full contract in `handlers.py` module docstring.

**iOS-toggle CSS positioning trap** — the grid tile's `.tool-enable-switch` is `position: absolute; bottom: 12px; right: 12px;` (designed for a `position: relative` tile container). Reusing the same widget inside an editor row requires an unpinning override (`.tools-editor-enabled-row .tool-enable-switch { position: relative; bottom: auto; right: auto; }`) — without this, the toggle floats off-screen relative to the document. See `admin.css:243-252` for the override.

**Shared form helpers** — `window.App.adminFormHelpers` (at `the_one/interfaces/web/static/js/areas/admin/tools-form-helpers.js`) is the canonical form-rendering substrate, consumed by both admin (`tools-editor.js`) and Studio (`studio/tools-tab.js`). Future flights extending tool-config UI consume these helpers via the context object: `{mode: 'admin' | 'agent', operatorValue?: any, attrPrefix: 'data-field' | 'data-tool-override-field', toolName?: string}`. Owned by `admin/` because admin was the first consumer; future migration to `shared/` if a third area imports.

**Lazy schema fetch caches the PROMISE** — Studio's per-agent override panels lazy-fetch each tool's schema on first `<details>` open. The closure cache stores the in-flight Promise (NOT the resolved value), so concurrent callers (operator opens + closes + opens fast) reuse the same fetch. The cache survives across agent changes within the studio area lifetime — schemas are static at runtime. Operator's saved `tool_configs` and `disabledTools` are RE-fetched on every agent-edit mount (those can change between tabs).

**Validation-error humanization** — Pydantic v2's raw error messages start with prefixes like `"Value error, "` / `"Input should be "` / `"Assertion failed, "`. The L3 editor's `humanizeValidationMsg` helper (mirrored in `tools-editor.js` and `tools-form-helpers.js`) strips these and capitalizes the first character. Model-level errors (`loc: []`) render in the prominent `.editor-error-banner` above the Configuration section; field-level errors (`loc` matching a `[data-field-name]` row) render inline next to the field via `.field-error`. Heuristic field-name matching for model-level errors highlights the offending rows via `.field-error-highlight` (red border + label tint).

## MCP Sources operator workflows

**Test connection button** — Each MCP source's Studio source-edit page (Studio → MCP Sources → select source → Edit) exposes a Test connection button. Clicking it invokes `POST /api/mcp-sources/{id}/test/connect` against the live source: `MCPClient.connect()` runs the lifecycle handshake and `list_tools()` returns the server's tool catalogue. For OAuth-protected sources, the first click drives the spec-compliant DCR + auth-code flow in a popup — operator completes consent at the IdP, tokens persist encrypted in `secrets`, and the second click renders the tool list. Side effect: subsequent agent builds attached to the source see fresh tokens (`access_token`, `refresh_token`, `dcr_credentials`) and register the server's real tools, closing the auth-on-`tools/list` blocking gap.

## Configuration

Runtime config via env vars prefixed `THE_ONE_` (see `.env.example`): host, port, data_dir, dev_mode. Managed by pydantic-settings in `the_one/config.py`. The `settings` singleton is imported directly. LLM provider configuration is managed through the database (not env vars) — see the `/api/providers` endpoints.

### Dev mode and the mock provider

When `THE_ONE_DEV_MODE=true` is set, a fifth provider type `mock` becomes available alongside `ollama`, `openai-compatible`, `openai`, and `anthropic`. The mock provider returns deterministic scripted responses sourced from its `LLMProviderConfig.config["response"]` field — defaults to `"Mock response from the mock provider."` if no `response` key is set. Used by browser tests for deterministic chat flows; also useful for offline dev work and demos.

- Backend rejects mock-typed creates/updates with HTTP 400 when dev mode is off
- UI dropdown filters out `mock` when dev mode is off (driven by `GET /api/providers/types`)
- Existing mock providers continue to render correctly in the admin UI even after dev mode is later disabled (the `TYPE_DEFAULTS` defaults and the `KNOWN_BADGE_TYPES` array are unconditional, so the badge styling resolves regardless of dev_mode)

## Security posture

See [SECURITY-MODEL.md](SECURITY-MODEL.md) for the project's threat model and intentional security choices (no-auth-by-design, single-user local-only, Origin-allowlist mitigation, SSRF/subprocess boundaries).

**Origin allowlist override**: set `THE_ONE_ORIGIN_ALLOWLIST` to a comma-separated list of `scheme://host:port` patterns (port supports `*` wildcard) to extend the default `http://127.0.0.1:*` / `http://localhost:*` allowlist. See `SECURITY-MODEL.md` for the threat-model context.

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

**Canonical command for non-interactive runs**: `docker exec the-one pytest …` (matches the Makefile's `make test*` targets). Do **NOT** use `docker compose exec the-one pytest …` from non-interactive contexts (CI, agents, scripts) — `docker compose exec` defaults to `-it` (interactive + TTY) and hangs forever when stdin isn't a TTY. If you must use compose subcommands, pass `-T` to disable TTY allocation. This applies to anything driven from Claude Code's Bash tool, GitHub Actions, or shell scripts. Interactive shells (operator at terminal) can use either.

**Always pair pytest with `-x`** for autonomous runs unless you specifically want to see full failure surface — pytest-asyncio's per-test loop teardown can hang if a test leaves orphaned state on a torn-down loop, and `-x` exits on first failure before that hang surfaces. Without `-x`, a single broken test can wedge the suite indefinitely.

**Unit tests** run by default with `docker exec the-one pytest tests/` — fast, no external dependencies, ~213 tests in <6s.

**`tests/test_mcp_pool.py`** ships 10 pure-unit pool tests + 2 bwrap-dependent integration tests. The integration tests use `@pytest.mark.requires_bwrap` (registered in `pyproject.toml::markers`) and are deselected by default via the `not requires_bwrap` clause in `addopts`. To run the integration tests on a host with bwrap available: `pytest -m requires_bwrap tests/test_mcp_pool.py`.

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
