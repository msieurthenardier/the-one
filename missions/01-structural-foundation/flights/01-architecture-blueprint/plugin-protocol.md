# Plugin Protocol

## ToolProvider Protocol

```python
from typing import Protocol, runtime_checkable


@runtime_checkable
class ToolProvider(Protocol):
    """Protocol for sources of tools."""

    @property
    def name(self) -> str:
        """Unique identifier for this provider (e.g., 'builtin', 'mcp:slack')."""
        ...

    def get_tools(self) -> list[Tool]:
        """Return all tools this provider can supply."""
        ...
```

### Design Decisions

- **Protocol, not ABC**: Providers don't need to inherit from a base class. Any object with a `name` property and `get_tools()` method satisfies the protocol. This enables duck-typing and keeps the interface minimal.
- **`runtime_checkable`**: Allows `isinstance(obj, ToolProvider)` for validation at registration time.
- **Returns `list[Tool]`**: Providers return fully instantiated `Tool` objects. The registry doesn't know or care how they were created.
- **No async**: Tool *discovery* is fast (import + instantiate). Tool *execution* is async (on the `Tool.execute()` method). This separation avoids async ceremony during factory startup.
- **No `get_tool(name)`**: Individual tool lookup is the registry's job. Providers are bulk sources.

---

## BuiltinToolProvider

Replaces `ToolRegistry.load_defaults()`. Same lazy-import pattern, same 14 tools, but decoupled from the registry class.

```python
from the_one.tools.base import Tool


class BuiltinToolProvider:
    """Provides all built-in tools via lazy imports."""

    @property
    def name(self) -> str:
        return "builtin"

    def get_tools(self) -> list[Tool]:
        """Lazy-import and instantiate all 14 built-in tools."""
        from the_one.tools.shell import ShellTool
        from the_one.tools.filesystem import ReadFileTool, WriteFileTool, ListDirTool
        from the_one.tools.web import HttpRequestTool, WebSearchTool
        from the_one.tools.python_exec import PythonExecTool
        from the_one.tools.git import GitTool
        from the_one.tools.test_runner import TestRunnerTool
        from the_one.tools.self_deploy import SelfDeployTool
        from the_one.tools.rollback import RollbackTool
        from the_one.tools.restart import RestartTool
        from the_one.tools.mission_control import MissionControlTool
        from the_one.tools.memory import MemoryTool

        return [
            ShellTool(),
            ReadFileTool(),
            WriteFileTool(),
            ListDirTool(),
            HttpRequestTool(),
            WebSearchTool(),
            PythonExecTool(),
            GitTool(),
            TestRunnerTool(),
            SelfDeployTool(),
            RollbackTool(),
            RestartTool(),
            MissionControlTool(),
            MemoryTool(),
        ]
```

### Why This Structure

- **Lazy imports inside `get_tools()`**: Same pattern as current `load_defaults()`. Optional dependencies (anthropic, openai SDKs) are never imported unless a tool that needs them is loaded.
- **Returns fresh instances**: Each `get_tools()` call creates new tool instances. The factory calls this once during `create()`, so no performance concern.
- **No caching**: The provider is stateless. Caching would add complexity for zero benefit — `get_tools()` is called once per agent creation.

---

## Per-Agent Tool Views

Each agent definition specifies which tools it can use via two fields:

```python
@dataclass
class AgentConfig:
    enabled_tools: list[str] | None = None    # Whitelist (None = all)
    disabled_tools: list[str] = field(default_factory=list)  # Blacklist
```

### Filtering Logic

```python
def is_tool_enabled(self, tool_name: str) -> bool:
    # Step 1: Whitelist check (None means "all allowed")
    if self.enabled_tools is not None and tool_name not in self.enabled_tools:
        return False
    # Step 2: Blacklist check (always applied)
    if tool_name in self.disabled_tools:
        return False
    return True
```

### Truth Table

| `enabled_tools` | `disabled_tools` | Tool "shell" | Tool "git" | Tool "memory" |
|-----------------|------------------|-------------|-----------|--------------|
| `None` | `[]` | enabled | enabled | enabled |
| `None` | `["memory"]` | enabled | enabled | **disabled** |
| `["shell", "git"]` | `[]` | enabled | enabled | **disabled** |
| `["shell", "git", "memory"]` | `["memory"]` | enabled | enabled | **disabled** |
| `[]` | `[]` | **disabled** | **disabled** | **disabled** |

**Key rules**:
- `enabled_tools=None` means "start with all tools" (current behavior)
- `enabled_tools=[]` means "no tools" (useful for chat-only agents)
- Blacklist (`disabled_tools`) always wins over whitelist
- An empty blacklist is a no-op

---

## Filtering at Factory Time

The `AgentFactory` applies tool filtering when building the `ToolRegistry` for an agent. The `Agent` class itself never sees disabled tools — it receives a pre-filtered registry.

```python
# In AgentFactory.create():
registry = ToolRegistry()
for provider in self.tool_providers:
    for tool in provider.get_tools():
        if config.is_tool_enabled(tool.name):
            registry.register(tool)

# Agent only sees what passed the filter
agent = Agent(llm=llm, tools=registry, ...)
```

### Why Filter at Factory, Not Agent

1. **Separation of concerns**: The Agent runs a loop. It shouldn't enforce access policy.
2. **Simplicity**: `Agent` already works with whatever `ToolRegistry` it receives. No changes needed to the Agent class.
3. **Security**: A misconfigured Agent can't access tools it shouldn't — they literally aren't in its registry.
4. **Testability**: Tests can create agents with specific tool sets by passing a pre-built registry, no config needed.

---

## Future MCP Integration Surface

MCP (Model Context Protocol) tool servers could be integrated by implementing the same `ToolProvider` protocol:

```python
class McpToolProvider:
    """Provides tools from an MCP server (future implementation)."""

    def __init__(self, server_url: str, server_name: str) -> None:
        self.server_url = server_url
        self._name = f"mcp:{server_name}"

    @property
    def name(self) -> str:
        return self._name

    def get_tools(self) -> list[Tool]:
        """Connect to MCP server, discover tools, wrap as Tool instances."""
        # 1. Connect to MCP server
        # 2. List available tools
        # 3. Wrap each as a McpTool (adapts MCP protocol to Tool ABC)
        # 4. Return list
        ...
```

### Integration Points

| Component | MCP Responsibility |
|-----------|-------------------|
| `ToolProvider.get_tools()` | Connect to MCP server, discover tools, return as `Tool` instances |
| `McpTool(Tool)` | Adapter class that wraps MCP tool calls as `Tool.execute()` |
| `AgentFactory` | Accepts multiple `ToolProvider` instances — builtins + MCP providers |
| `AgentConfig` | `enabled_tools` / `disabled_tools` work identically for MCP tools |
| `Agent` | No changes — receives a ToolRegistry, doesn't know tool origin |

### What's NOT Designed Here

- MCP server discovery and lifecycle management
- MCP transport details (stdio, SSE, WebSocket)
- MCP resource and prompt support (only tools)
- Agent config schema for specifying MCP servers

These are deferred to a future mission. The `ToolProvider` protocol is the only surface needed now — it's sufficient to plug in MCP later without changing the factory or agent.

---

## Tool Schema Translation

### Current Flow

```
Tool.to_schema()          → Canonical format: {name, description, parameters}
    │
LLMProvider.tool_schema() → Provider-specific format:
    ├── OpenAI:    {"type": "function", "function": {name, description, parameters}}
    ├── Anthropic: {name, description, input_schema}
    └── Ollama:    Same as OpenAI (OpenAI-compatible)
```

### Where Each Piece Lives

| Responsibility | Location | Notes |
|---------------|----------|-------|
| Canonical tool definition | `Tool.to_schema()` in `tools/base.py` | Provider-agnostic JSON Schema |
| Provider-specific wrapping | `LLMProvider.tool_schema()` in `llm/base.py` | Default is OpenAI format |
| Anthropic override | `AnthropicProvider.tool_schema()` in `llm/anthropic_provider.py` | Uses `input_schema` key |

### Unchanged by Plugin Protocol

The schema translation chain is unaffected by the ToolProvider refactor. ToolProviders return `Tool` objects, which have `to_schema()`. The LLM provider wraps schemas at call time. No new translation layer is needed.

The only new consideration: MCP tools would need their own `to_schema()` implementation in the `McpTool` adapter class, converting MCP's tool description format to the canonical `{name, description, parameters}` format.
