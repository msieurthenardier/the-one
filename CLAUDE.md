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

**Tool layer** (`the_one/tools/`) — Abstract `Tool` base class with `execute(**kwargs) -> str`. `ToolRegistry` holds all tools and generates JSON schemas for the LLM. `BuiltinToolProvider` (`builtins.py`) provides all 17 built-in tools via lazy import, implementing the `ToolProvider` protocol (`provider.py`): one `shell`, nine filesystem (`read_file`, `write_file`, `edit_file`, `delete_file`, `move_file`, `mkdir`, `glob`, `grep`, `list_dir`), one `python_exec`, four PTY session tools (`shell_session_start`, `shell_session_send`, `shell_session_close`, `shell_session_list`), and two web (`http_request`, `web_search`). Tools are the agent's only way to affect the outside world.

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

### Cross-Config dispatch (F4)
Tools may declare `Requires: tuple[type[BaseModel], ...] = (FilesystemConfig,)` to receive the resolved `FilesystemConfig` (or any other declared Config) via `cross_configs: dict[type[BaseModel], BaseModel]` passed into `Tool.__init__`. `BuiltinToolProvider.get_tools` builds the per-call shared view once by walking `_TOOL_CLASSES` in declared order. Used by `ShellTool` and `PythonExecTool` to validate `cwd` against the filesystem path-scope, and by `ShellSessionStartTool` / `ShellSessionSendTool` for the same. `Tool.__init__` also accepts `agent_name: str | None = None` (threaded from `AgentFactory.create()`) — the four session tools key the `_session_registry` on `(agent_name, session_id)` for cross-agent isolation; `agent_name=None` is the introspection path and produces a clean `ConstraintError` from session tools.

### PTY session lifecycle (F4)
PTY sessions ship via `the_one/platform/pty.py::PtySession` ABC (`UnixPtySession` concrete; Windows `ConPTY` deferred to a future mission). Sessions are registered in `the_one/tools/_session_registry.py` keyed on `(agent_name, session_id)`; per-agent `count_for_agent()` enforces the `max_concurrent_sessions` cap; a single asyncio reaper task spawns lazily on first registration and wakes every 30s to close sessions idle past `pty_session_idle_ttl_seconds`. The reaper registers with the FastAPI lifespan so shutdown drains the registry cleanly. Readiness detection uses an idle-mark (`_read_until_idle` blocks until the master_fd has been silent for 100ms, with a 2s hard cap) — robust against shells that emit prompts inconsistently. Per-call denylist re-check applies on every `shell_session_send` (Decision 11) so agents cannot pre-stage a denylisted command behind an open session.

### Dev iteration: container restart
**When iterating on tool source code mid-flight, restart the container** (`docker compose restart the-one`) so uvicorn picks up new imports. The bind-mount makes new code visible to **new** Python invocations (e.g., `docker exec the-one python /app/_tmp_clip.py` sees post-edit code) but does NOT affect modules already imported by the long-running uvicorn worker. Surfaced during F4 L7 HAT scenario 1 — the timeout-cap clip fix from L3-L4 was not engaging through the chat API until the container was restarted; HAT then passed cleanly. See F4 flight-log Anomalies for the full incident write-up. Optional follow-up (out of F4 scope): add `--reload` to uvicorn in the dev compose file, OR an `App.onChange` script that auto-restarts on `the_one/**/*.py` changes.

### Session-bound freshness
Resolved tool configs are computed at `AgentFactory.create()` time and held as instance state on each tool. Mid-session operator updates to `tool_configs` rows or `AgentConfig.tool_overrides` apply at the **next** `AgentFactory.create()` invocation, NOT to in-flight agents. F6's admin UI must communicate "applies to next session" clearly.

### Platform abstraction layer
`the_one/platform/` isolates platform-divergent concerns:
- `paths.py` — `canonicalize`, `safe_resolve`, `is_within`
- `shell.py` — `select_shell`, `run_shell` (kill+reap on timeout via `start_new_session=True` + `killpg(SIGKILL)`)
- `interpreter.py` — `resolve_python` (returns `sys.executable`), `run_python`
- `tempdirs.py` — `temp_dir`, `user_home`, `user_config_dir`

F3-F5 will populate per-tool Pydantic Configs with real constraint values on top of this seam.

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
