# Target Architecture

## Current State Baseline

### Directory Layout

```
the_one/
├── __init__.py                    # Version only
├── agent/
│   ├── __init__.py                # Re-exports Agent
│   └── core.py                    # SYSTEM_PROMPT, _DIRECT_ACTIONS, _CONTINUE_SCHEMA,
│                                  # extract_tool_calls(), Agent class (~230 lines)
├── config.py                      # Settings (pydantic-settings), global singleton
├── llm/
│   ├── __init__.py                # Re-exports base classes + get_provider
│   ├── base.py                    # LLMProvider ABC, Message, ToolCall, ToolResult, Role, TokenUsage
│   ├── registry.py                # register_provider(), get_provider(), lazy loading
│   ├── anthropic_provider.py      # AnthropicProvider
│   ├── openai_provider.py         # OpenAIProvider
│   └── ollama_provider.py         # OllamaProvider
├── interfaces/
│   ├── cli.py                     # _make_agent(), Rich REPL (~86 lines)
│   └── web/
│       ├── app.py                 # _make_agent(), FastAPI, sessions, WebSocket (~380 lines)
│       └── static/                # Frontend assets
├── tools/
│   ├── __init__.py                # Re-exports Tool, ToolRegistry
│   ├── base.py                    # Tool ABC, ToolRegistry with load_defaults() (~77 lines)
│   ├── shell.py                   # ShellTool
│   ├── filesystem.py              # ReadFileTool, WriteFileTool, ListDirTool
│   ├── git.py                     # GitTool
│   ├── test_runner.py             # TestRunnerTool
│   ├── python_exec.py             # PythonExecTool
│   ├── web.py                     # HttpRequestTool, WebSearchTool
│   ├── memory.py                  # MemoryTool (module-level MEMORY_DIR = settings.workspace_dir)
│   ├── self_deploy.py             # SelfDeployTool (settings accessed at call time in execute())
│   ├── restart.py                 # RestartTool
│   ├── rollback.py                # RollbackTool
│   └── mission_control.py         # MissionControlTool
└── main.py                        # CLI entry point (chat/serve/version)
```

### Coupling Points

1. **`agent/core.py` is overloaded** — contains the agent loop, system prompt, direct action patterns, continue signal schema, and tool call extraction. These are distinct concerns mixed in one file.

2. **`ToolRegistry.load_defaults()` couples registry to all tools** — the registry class shouldn't know about specific tool implementations. Every new tool requires editing `base.py`.

3. **`memory.py` module-level settings** — `MEMORY_DIR = settings.workspace_dir / ".memory"` evaluated at import time. Cannot be overridden per-agent or per-test without monkeypatching.

4. **`self_deploy.py` call-time settings access** — accesses `settings.workspace_dir`, `settings.concourse_target`, `settings.concourse_pipeline` inside `execute()` at call time, not at import/module level. No import-time binding problem, but constructor injection is still warranted for testability and per-agent configuration.

5. **Duplicate `_make_agent()`** — identical factory logic in `cli.py` and `web/app.py`. Both create an LLM provider, a ToolRegistry, call `load_defaults()`, and instantiate Agent.

6. **No multi-agent support** — single hardcoded system prompt, no way to configure different tool sets or providers per agent.

### What Needs to Change

- Extract behavioral constants from `core.py` into their own module
- Replace `load_defaults()` with a `ToolProvider` pattern
- Decouple `memory.py` and `self_deploy.py` from module-level settings
- Unify `_make_agent()` into an `AgentFactory`
- Add agent configuration model and persistence
- Add `agents_dir` property to Settings

---

## Target Directory Layout

```
the_one/
├── __init__.py                    # Version only (unchanged)
├── agent/
│   ├── __init__.py                # Re-exports Agent, AgentConfig, AgentFactory
│   ├── core.py                    # Agent class only — slimmed to loop + step + reset
│   ├── config.py                  # AgentConfig dataclass, DEFAULT_SYSTEM_PROMPT
│   ├── factory.py                 # AgentFactory — create(name), list_agents()
│   ├── store.py                   # AgentConfigStore protocol + FilesystemConfigStore
│   └── behaviors.py               # _DIRECT_ACTIONS, _CONTINUE_SCHEMA, extract_tool_calls()
├── config.py                      # Settings + agents_dir property (minor addition)
├── llm/                           # Unchanged structure
│   ├── __init__.py
│   ├── base.py
│   ├── registry.py
│   ├── anthropic_provider.py
│   ├── openai_provider.py
│   └── ollama_provider.py
├── tools/
│   ├── __init__.py                # Re-exports Tool, ToolRegistry, ToolProvider
│   ├── base.py                    # Tool ABC, ToolRegistry (load_defaults removed)
│   ├── provider.py                # ToolProvider protocol
│   ├── builtins.py                # BuiltinToolProvider (replaces load_defaults)
│   ├── shell.py                   # Unchanged
│   ├── filesystem.py              # Unchanged
│   ├── git.py                     # Unchanged
│   ├── test_runner.py             # Unchanged
│   ├── python_exec.py             # Unchanged
│   ├── web.py                     # Unchanged
│   ├── memory.py                  # Decoupled: MEMORY_DIR passed via constructor
│   ├── self_deploy.py             # Decoupled: settings passed via constructor
│   ├── restart.py                 # Unchanged
│   ├── rollback.py                # Unchanged
│   └── mission_control.py         # Unchanged
├── interfaces/
│   ├── cli.py                     # _make_agent() replaced with factory.create()
│   └── web/
│       ├── app.py                 # _make_agent() replaced with factory.create()
│       └── static/                # Unchanged
├── main.py                        # Unchanged
└── agents.md                      # Dev-facing self-awareness doc (not loaded at runtime)
```

### New Files

| File | Purpose |
|------|---------|
| `agent/config.py` | `AgentConfig` Pydantic model, `DEFAULT_SYSTEM_PROMPT` constant |
| `agent/factory.py` | `AgentFactory` — reads config, wires LLM + tools + prompt |
| `agent/store.py` | `AgentConfigStore` protocol + `FilesystemConfigStore` implementation |
| `agent/behaviors.py` | `_DIRECT_ACTIONS`, `_CONTINUE_SCHEMA`, `extract_tool_calls()` |
| `tools/provider.py` | `ToolProvider` protocol definition |
| `tools/builtins.py` | `BuiltinToolProvider` — lazy-imports and provides all 14 built-in tools |
| `agents.md` | Development-facing architecture doc |

### Modified Files

| File | Change |
|------|--------|
| `agent/core.py` | Remove `SYSTEM_PROMPT`, `_DIRECT_ACTIONS`, `_CONTINUE_SCHEMA`, `extract_tool_calls()`. Import from `behaviors.py` and `config.py`. |
| `tools/base.py` | Remove `load_defaults()` method from `ToolRegistry` |
| `tools/memory.py` | Accept `memory_dir` as constructor parameter instead of module-level `MEMORY_DIR` |
| `tools/self_deploy.py` | Accept `workspace_dir`, `concourse_target`, `concourse_pipeline` via constructor |
| `interfaces/cli.py` | Replace `_make_agent()` with `AgentFactory` usage |
| `interfaces/web/app.py` | Replace `_make_agent()` with `AgentFactory` usage |
| `config.py` | Add `agents_dir` property returning `self.data_dir / "agents"` |
| `agent/__init__.py` | Add exports for `AgentConfig`, `AgentFactory` |
| `tools/__init__.py` | Add export for `ToolProvider` |

### Unchanged Files

All LLM provider files, `main.py`, `__init__.py` (root), `shell.py`, `filesystem.py`, `git.py`, `test_runner.py`, `python_exec.py`, `web.py`, `restart.py`, `rollback.py`, `mission_control.py`, and all static assets.

---

## Module Boundaries

### `agent/` — Agent Runtime

| File | Exports | Purpose |
|------|---------|---------|
| `core.py` | `Agent` | The agent loop: step(), reset(), message history management |
| `config.py` | `AgentConfig`, `DEFAULT_SYSTEM_PROMPT` | Agent definition Pydantic model and default prompt |
| `factory.py` | `AgentFactory` | Creates configured Agent instances from named configs |
| `store.py` | `AgentConfigStore`, `FilesystemConfigStore` | CRUD operations for agent definitions |
| `behaviors.py` | `DIRECT_ACTIONS`, `CONTINUE_SCHEMA`, `extract_tool_calls()` | Behavioral constants and text-based tool call extraction |

### `tools/` — Tool System

| File | Exports | Purpose |
|------|---------|---------|
| `base.py` | `Tool`, `ToolRegistry` | Tool ABC and registry (no load_defaults) |
| `provider.py` | `ToolProvider` | Protocol for tool sources |
| `builtins.py` | `BuiltinToolProvider` | Provides all 14 built-in tools via lazy import |
| `[tool files]` | Individual tool classes | Tool implementations |

### `llm/` — LLM Abstraction (Unchanged)

| File | Exports | Purpose |
|------|---------|---------|
| `base.py` | `LLMProvider`, `Message`, `ToolCall`, `ToolResult`, `Role`, `TokenUsage` | Core types |
| `registry.py` | `register_provider`, `get_provider` | Provider registration and lazy loading |
| `[provider files]` | Individual provider classes | LLM implementations |

### `interfaces/` — User-Facing Layers

| File | Exports | Purpose |
|------|---------|---------|
| `cli.py` | `run()` | Rich REPL, uses AgentFactory |
| `web/app.py` | `app` (FastAPI) | Web server, uses AgentFactory |

### `config.py` — Global Configuration

| Export | Purpose |
|--------|---------|
| `Settings` | Pydantic-settings class with all THE_ONE_* env vars |
| `settings` | Global singleton instance |

---

## Dependency Flow

```
                    config.py (settings)
                    ┌─────┴─────┐
                    │           │
                  llm/        tools/
                    │           │
                    └─────┬─────┘
                          │
                    agent/core.py
                    agent/config.py
                    agent/behaviors.py
                    agent/store.py
                          │
                    agent/factory.py
                          │
                    interfaces/
                    (cli.py, web/app.py)
                          │
                      main.py
```

### Allowed Import Directions

- `config.py` → imported by everything (leaf dependency)
- `llm/` → imports `config.py` only
- `tools/` → imports `config.py` only (individual tools may import `settings` for defaults)
- `agent/core.py` → imports `llm/`, `tools/`, `agent/behaviors.py`
- `agent/config.py` → imports `pydantic` only (pure model definition)
- `agent/behaviors.py` → imports `llm/base.py` (for `ToolCall` type only)
- `agent/store.py` → imports `agent/config.py`, `config.py`
- `agent/factory.py` → imports `agent/core.py`, `agent/config.py`, `agent/store.py`, `llm/`, `tools/`
- `interfaces/` → imports `agent/factory.py`, `config.py`
- `main.py` → imports `interfaces/`, `config.py`

### Prohibited Import Directions

- `llm/` must NOT import from `tools/` or `agent/`
- `tools/` must NOT import from `agent/` or `interfaces/`
- `agent/core.py` must NOT import from `interfaces/`
- `agent/config.py` must NOT import from `agent/core.py` (no circular deps)
- `config.py` must NOT import from any other project module

---

## What Moves Where

| Symbol | Current Location | Target Location |
|--------|-----------------|----------------|
| `SYSTEM_PROMPT` | `agent/core.py:38-94` | `agent/config.py` as `DEFAULT_SYSTEM_PROMPT` |
| `_DIRECT_ACTIONS` | `agent/core.py:13-16` | `agent/behaviors.py` as `DIRECT_ACTIONS` |
| `_CONTINUE_SCHEMA` | `agent/core.py:19-36` | `agent/behaviors.py` as `CONTINUE_SCHEMA` |
| `_extract_tool_calls()` | `agent/core.py:191-220` (method) | `agent/behaviors.py` as `extract_tool_calls(text: str, valid_names: set[str]) -> list[ToolCall]`. Call site in `core.py` becomes `extract_tool_calls(text, set(self.tools.tool_names) \| {"continue"})` |
| `_match_direct_action()` | `agent/core.py:222-229` (static method) | `agent/behaviors.py` as `match_direct_action(user_input: str) -> tuple[str, dict] \| None` |
| `_make_agent()` | `interfaces/cli.py:20-27` | Deleted; replaced by `AgentFactory.create()` |
| `_make_agent()` | `interfaces/web/app.py:58-65` | Deleted; replaced by `AgentFactory.create()` |
| `load_defaults()` | `tools/base.py:46-76` | Deleted; replaced by `BuiltinToolProvider.get_tools()` |

---

## Tools Requiring Decoupling

### `memory.py` — Module-Level `MEMORY_DIR`

**Current**: `MEMORY_DIR = settings.workspace_dir / ".memory"` at module level (line 11)

**Problem**: Evaluated at import time. Cannot override per-agent or per-test.

**Fix**: Accept `memory_dir: Path` as a constructor parameter with a default:

```python
class MemoryTool(Tool):
    def __init__(self, memory_dir: Path | None = None) -> None:
        self.memory_dir = memory_dir or (settings.workspace_dir / ".memory")
```

`BuiltinToolProvider` passes the default; tests or specialized agents can override.

### `self_deploy.py` — Call-Time Settings Access

**Current**: Accesses `settings.workspace_dir`, `settings.concourse_target`, `settings.concourse_pipeline` inside `execute()` at call time (lines 36-38). No module-level or class-level settings binding.

**Problem**: Not an import-time issue, but settings are still accessed as globals inside the method body. This makes testing difficult (requires monkeypatching the settings singleton) and prevents per-agent configuration of deploy targets.

**Fix**: Accept configuration via constructor with defaults from settings, enabling testability and per-agent configuration:

```python
class SelfDeployTool(Tool):
    def __init__(
        self,
        workspace_dir: Path | None = None,
        concourse_target: str | None = None,
        concourse_pipeline: str | None = None,
    ) -> None:
        self.workspace_dir = workspace_dir or settings.workspace_dir
        self.concourse_target = concourse_target or settings.concourse_target
        self.concourse_pipeline = concourse_pipeline or settings.concourse_pipeline
```

---

## Module Granularity Decision

**Decision**: Keep tools flat (one file per tool or per tool group). Do NOT adopt directory-per-tool.

**Rationale**:
- 14 tools is manageable in a flat structure
- Most tools are single-class, 30-80 line files
- Directory-per-tool adds navigation overhead without proportional benefit
- `filesystem.py` grouping 3 related tools (ReadFile, WriteFile, ListDir) is a good pattern
- `web.py` grouping 2 related tools (HttpRequest, WebSearch) is similarly fine

**When to reconsider**: If a tool grows beyond ~200 lines or requires multiple helper modules, extract it into its own directory at that point.

---

## CLAUDE.md Reconciliation Plan

The current CLAUDE.md accurately describes the four-layer architecture but will need updates after Flight 2 restructuring:

### Sections to Update in Flight 2

1. **Architecture section** — Add mentions of:
   - `agent/config.py`, `agent/factory.py`, `agent/store.py`, `agent/behaviors.py`
   - `tools/provider.py`, `tools/builtins.py`
   - `AgentFactory` replacing `_make_agent()`
   - `BuiltinToolProvider` replacing `load_defaults()`

2. **Tool layer description** — Change "load_defaults() registers all 14 built-in tools" to describe BuiltinToolProvider

3. **Agent loop description** — Note that behaviors (direct actions, continue signal, tool call extraction) are in `behaviors.py`

4. **Interfaces description** — Note that both use `AgentFactory` instead of local `_make_agent()`

5. **Add agents.md reference** — Point developers to `agents.md` for architecture details

### Sections That Remain Accurate

- Commands section (unchanged)
- Self-Deployment section (unchanged)
- Configuration section (add `agents_dir` mention)
- Conventions section (unchanged)
