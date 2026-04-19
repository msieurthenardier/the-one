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

Key properties: `data_dir` (`~/.the-one`), `workspace_dir` (`/workspace`), `agents_dir` (`data_dir / "agents"`), `llm_provider`, `llm_model`.

### `the_one/agent/`

| File | Exports | Purpose |
|------|---------|---------|
| `core.py` | `Agent` | The agent loop: `step()` yields messages, max 20 iterations |
| `config.py` | `AgentConfig`, `DEFAULT_SYSTEM_PROMPT` | Agent definition Pydantic model and fallback prompt |
| `factory.py` | `AgentFactory` | `create(name)` → configured Agent; `list_agents()` |
| `store.py` | `AgentConfigStore`, `FilesystemConfigStore` | CRUD for agent configs (`~/.the-one/agents/*.json`) |
| `behaviors.py` | `DIRECT_ACTIONS`, `CONTINUE_SCHEMA`, `extract_tool_calls()`, `match_direct_action()` | Behavioral patterns extracted from core |

**Agent.step() flow**: user input → check direct actions → LLM call → extract tool calls → execute tools → repeat until no tool calls or max iterations.

### `the_one/llm/`

| File | Exports | Purpose |
|------|---------|---------|
| `base.py` | `LLMProvider`, `Message`, `ToolCall`, `ToolResult`, `Role`, `TokenUsage` | Core types |
| `registry.py` | `register_provider`, `get_provider` | Lazy-loaded provider registry |
| `ollama_provider.py` | `OllamaProvider` | Local models (qwen2.5:7b default) |
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

Agents are defined as JSON files in `~/.the-one/agents/`. The factory reads a config, wires up the right LLM + filtered tools + prompt, and returns a ready-to-use `Agent`. A "default" agent is synthesized from env vars when no config file exists.

### Tool Filtering

`AgentConfig` has `enabled_tools` (whitelist, `null`=all) and `disabled_tools` (blacklist). Filtering happens in the factory — the Agent receives a pre-filtered `ToolRegistry` and never knows about disabled tools.

### Tool Providers

`ToolProvider` is a protocol with `name` + `get_tools()`. `BuiltinToolProvider` provides the 14 built-in tools. Future `McpToolProvider` implements the same protocol for MCP server tools.

### Direct Actions

Regex patterns in `behaviors.py` that bypass the LLM for known commands (restart, rollback). This avoids small models reaching for `shell` when a dedicated tool exists.

### Continue Signal

A virtual tool (`CONTINUE_SCHEMA`) that the LLM calls to indicate it needs another iteration. Not a real tool — the agent loop intercepts it and loops.

### Tool Call Extraction

`extract_tool_calls()` in `behaviors.py` parses JSON tool calls from text output. This handles models that embed tool calls in prose instead of using native function calling.
