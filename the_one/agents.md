# agents.md

Development-facing architecture reference for the-one. This file describes the **target architecture** — the structure being implemented during the Structural Foundation mission. It is not loaded at runtime.

For usage, commands, and conventions, see `CLAUDE.md`.

---

## Architecture Overview

The-one is a self-modifying LLM agent built without frameworks. Four layers compose bottom-up:

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

Key properties: `data_dir` (`~/.the-one`), `workspace_dir` (`/workspace`), `agents_dir` (`data_dir / "agents"`), `db_path` (`data_dir / "the-one.db"`).

### `the_one/encryption.py`

Fernet-based encryption for API keys stored in the database. Generates and caches an `Encryptor` per `data_dir`. Provides an `install_key()` helper plus a public `key_path` property; the API rotation path (`POST /api/encryption/rotate`) re-encrypts all provider credentials, commits the DB, then atomically replaces the key file via `os.replace`. The legacy `rotate_key()` callback API is retained for non-API callers.

### `the_one/db/repositories.py`

Database repositories including `LLMProviderRepository` for CRUD on `llm_provider_configs` table. Provider configs store `name`, `type`, `base_url`, and encrypted `api_key`. Referenced by `AgentConfig.provider_config_id`.

### `the_one/agent/`

| File | Exports | Purpose |
|------|---------|---------|
| `core.py` | `Agent` | The agent loop: `step()` yields messages, max 20 iterations |
| `config.py` | `AgentConfig`, `DEFAULT_SYSTEM_PROMPT` | Agent definition Pydantic model (includes `provider_config_id` for LLM provider resolution) and fallback prompt |
| `factory.py` | `AgentFactory` | `create(name)` → configured Agent; `list_agents()` |
| `store.py` | `AgentConfigStore`, `FilesystemConfigStore` | CRUD for agent configs (`~/.the-one/agents/*.json`) |
| `behaviors.py` | `DIRECT_ACTIONS`, `CONTINUE_SCHEMA`, `match_direct_action()` | Behavioral patterns extracted from core |

**Agent.step() flow**: user input → check direct actions → LLM call → execute tools → repeat until no tool calls or max iterations.

### `the_one/llm/`

| File | Exports | Purpose |
|------|---------|---------|
| `base.py` | `LLMProvider`, `Message`, `ToolCall`, `ToolResult`, `Role`, `TokenUsage` | Core types |
| `registry.py` | `register_provider`, `get_provider` | Lazy-loaded provider registry |
| `ollama_provider.py` | `OllamaProvider` | Local Ollama and OpenAI-compatible servers; model selection comes from agent config |
| `openai_provider.py` | `OpenAIProvider` | GPT-4o |
| `anthropic_provider.py` | `AnthropicProvider` | Claude (claude-sonnet-4-6 default) |

Providers are lazy-loaded on first `get_provider(name)` call. Each converts messages/tools to its wire format and back.

### `the_one/tools/`

| File | Exports | Purpose |
|------|---------|---------|
| `base.py` | `Tool`, `ToolRegistry` | Tool ABC (`execute(**kwargs) -> str`) and registry |
| `provider.py` | `ToolProvider` | Protocol: `name` property + `get_tools()` method |
| `builtins.py` | `BuiltinToolProvider` | Provides all 14 built-in tools via lazy import |
| `shell.py` | `ShellTool` | Arbitrary shell commands |
| `filesystem.py` | `ReadFileTool`, `WriteFileTool`, `ListDirTool` | File operations |
| `git.py` | `GitTool` | Version control with safety guards |
| `test_runner.py` | `TestRunnerTool` | pytest integration |
| `python_exec.py` | `PythonExecTool` | Python subprocess execution |
| `web.py` | `HttpRequestTool`, `WebSearchTool` | HTTP and web search |
| `memory.py` | `MemoryTool` | Persistent key-value store (`.memory/` directory) |
| `self_deploy.py` | `SelfDeployTool` | Concourse CI deployment trigger |
| `restart.py` | `RestartTool` | Container restart via Concourse |
| `rollback.py` | `RollbackTool` | Docker image rollback via Concourse |
| `mission_control.py` | `MissionControlTool` | Flight Control methodology access |

### `the_one/interfaces/`

| File | Exports | Purpose |
|------|---------|---------|
| `cli.py` | `run()` | Rich + prompt-toolkit REPL |
| `web/app.py` | `app` | FastAPI server with WebSocket sessions |

Both use `AgentFactory.create()` to get agents. The web app adds session management.

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
        agent/behaviors.py
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

`ToolProvider` is a protocol with `name` + `get_tools()`. `BuiltinToolProvider` provides the 14 built-in tools. Future `McpToolProvider` implements the same protocol for MCP server tools.

### Direct Actions

Regex patterns in `behaviors.py` that bypass the LLM for known commands (restart, rollback). This avoids small models reaching for `shell` when a dedicated tool exists.

### Continue Signal

A virtual tool (`CONTINUE_SCHEMA`) that the LLM calls to indicate it needs another iteration. Not a real tool — the agent loop intercepts it and loops.

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

---

## Provider type extension checklist

To add a new LLM provider type, six layers must coordinate. Missing any one of them causes either silent rejection (validation) or runtime errors.

> **History**: The M04 flight that added the `mock` provider type initially missed the SQLite CHECK constraint (#4 below) during state-machine reachability audit. First test run failed with `IntegrityError: CHECK constraint failed`, requiring schema migration v6. The checklist below is the post-incident enumeration.

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
   - Add `TYPE_BADGE_COLORS["<type>"]` for the type badge in the provider list

When all six layers are aligned, an integration test posting a provider with the new type round-trips successfully through DB persistence, factory resolution, and UI rendering.

