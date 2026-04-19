# Extension Guide

Step-by-step recipes for extending the-one with new capabilities. All paths reference the target architecture (post-restructure).

---

## How to Add a Tool

**Steps: 2**

### Step 1: Create the Tool File

Create a new file in `the_one/tools/` (e.g., `the_one/tools/my_tool.py`):

```python
from the_one.tools.base import Tool


class MyTool(Tool):
    name = "my_tool"
    description = "Brief description of what this tool does"
    parameters = {
        "type": "object",
        "properties": {
            "input": {
                "type": "string",
                "description": "What this parameter does",
            },
        },
        "required": ["input"],
    }

    async def execute(self, **kwargs) -> str:
        input_val = kwargs["input"]
        # Do the work
        result = f"Processed: {input_val}"
        return result
```

**Requirements**:
- Inherit from `Tool`
- Set `name` (unique slug), `description`, and `parameters` (JSON Schema)
- Implement `async execute(**kwargs) -> str`
- Return a string result (the agent sees this as the tool output)
- Raise exceptions for errors — the agent loop catches and wraps them

### Step 2: Register in BuiltinToolProvider

Add the import and instantiation to `the_one/tools/builtins.py`:

```python
def get_tools(self) -> list[Tool]:
    # ... existing imports ...
    from the_one.tools.my_tool import MyTool

    return [
        # ... existing tools ...
        MyTool(),
    ]
```

**That's it.** The tool is now available to all agents (unless filtered by `enabled_tools`/`disabled_tools` in their config).

### Tips

- Keep tools focused — one tool, one responsibility
- If your tool needs settings (paths, URLs), accept them as constructor parameters with defaults from `settings`
- If your tool has optional dependencies, the lazy import in `builtins.py` handles it — the dependency is only loaded when the tool is instantiated
- Group related tools in one file (like `filesystem.py` has `ReadFileTool`, `WriteFileTool`, `ListDirTool`)
- Tool names should be `snake_case` slugs

---

## How to Add an LLM Provider

**Steps: 3**

### Step 1: Create the Provider File

Create a new file in `the_one/llm/` (e.g., `the_one/llm/gemini_provider.py`):

```python
from the_one.llm.base import LLMProvider, Message, ToolCall, Role, TokenUsage


class GeminiProvider(LLMProvider):
    name = "gemini"
    max_context_tokens = 1_000_000

    def __init__(self, model: str = "gemini-2.5-pro", **kwargs) -> None:
        self.model = model
        # Initialize client

    async def complete(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
    ) -> Message:
        # Convert messages to provider format
        # Call the API
        # Convert response back to Message
        ...

    def tool_schema(self, tool_def: dict) -> dict:
        """Override if the provider uses a non-OpenAI tool format."""
        # Default (OpenAI format) works for most providers
        return super().tool_schema(tool_def)
```

**Requirements**:
- Inherit from `LLMProvider`
- Set `name` (unique slug) and `max_context_tokens`
- Implement `async complete()` returning a `Message`
- Override `tool_schema()` only if the provider needs a different format than OpenAI's

### Step 2: Register the Provider

Add registration at the bottom of your provider file:

```python
from the_one.llm.registry import register_provider

register_provider("gemini", GeminiProvider)
```

### Step 3: Add Lazy-Load Entry

In `the_one/llm/registry.py`, add to `_try_load_builtin()`:

```python
def _try_load_builtin(name: str) -> None:
    builtins = {
        "anthropic": "the_one.llm.anthropic_provider",
        "openai": "the_one.llm.openai_provider",
        "ollama": "the_one.llm.ollama_provider",
        "gemini": "the_one.llm.gemini_provider",  # Add this line
    }
    if name in builtins:
        importlib.import_module(builtins[name])
```

**Usage**: Set `THE_ONE_LLM_PROVIDER=gemini` and `THE_ONE_LLM_MODEL=gemini-2.5-pro` in `.env`.

### Tips

- The default `tool_schema()` uses OpenAI's function-calling format. Only override if your provider needs something different.
- Add the provider's SDK to `pyproject.toml` as an optional dependency group
- Test with `the-one chat` to verify the provider works end-to-end

---

## How to Define a New Agent

**Steps: 1**

### Step 1: Create a JSON File

Create `~/.the-one/agents/{name}.json`:

```json
{
  "name": "researcher",
  "description": "Research-focused agent with web access but no code modification",
  "llm_provider": "anthropic",
  "llm_model": "claude-sonnet-4-6",
  "system_prompt": "You are a research assistant. Use web search and HTTP requests to find information. Summarize findings clearly and cite sources. You cannot modify files or run code.",
  "enabled_tools": ["http_request", "web_search", "read_file", "list_dir"],
  "disabled_tools": [],
  "max_iterations": 15,
  "direct_actions": false
}
```

**That's it.** The agent is immediately available via `factory.create("researcher")`.

### Field Reference

| Field | Required | Default | Notes |
|-------|----------|---------|-------|
| `name` | yes | — | Slug format: `[a-z0-9][a-z0-9-]*` |
| `description` | no | `""` | Human-readable, not sent to LLM |
| `llm_provider` | no | `"ollama"` | Must match a registered provider |
| `llm_model` | no | `"qwen2.5:7b"` | Passed to provider constructor |
| `llm_base_url` | no | `null` | Override provider's default URL |
| `system_prompt` | no | `""` | Empty = use default prompt |
| `enabled_tools` | no | `null` | `null` = all tools; `[]` = none |
| `disabled_tools` | no | `[]` | Always applied after whitelist |
| `max_iterations` | no | `20` | Safety limit per step |
| `direct_actions` | no | `true` | Regex shortcuts (restart, rollback) |

### Common Patterns

**Chat-only agent** (no tools):
```json
{
  "name": "chat-only",
  "description": "Pure conversation, no tool access",
  "enabled_tools": []
}
```

**Restricted agent** (all tools except dangerous ones):
```json
{
  "name": "safe",
  "description": "Full access minus deployment tools",
  "disabled_tools": ["self_deploy", "rollback", "restart", "shell"]
}
```

**Remote model agent**:
```json
{
  "name": "remote-llama",
  "description": "Uses a remote Ollama instance",
  "llm_provider": "ollama",
  "llm_model": "llama3.1:70b",
  "llm_base_url": "http://gpu-server:11434/v1"
}
```

---

## How to Add an MCP Tool Server (Future)

**Status**: Not yet implemented. The `ToolProvider` protocol is the integration surface.

### Step 1: Implement ToolProvider

Create a provider class that connects to an MCP server:

```python
from the_one.tools.base import Tool
from the_one.tools.provider import ToolProvider


class McpToolProvider:
    def __init__(self, server_url: str, server_name: str) -> None:
        self.server_url = server_url
        self._name = f"mcp:{server_name}"

    @property
    def name(self) -> str:
        return self._name

    def get_tools(self) -> list[Tool]:
        # Connect to MCP server
        # Discover available tools
        # Wrap each as McpTool (adapter implementing Tool ABC)
        ...
```

### Step 2: Create McpTool Adapter

```python
class McpTool(Tool):
    """Wraps an MCP tool as a local Tool instance."""

    def __init__(self, mcp_tool_def: dict, client: McpClient) -> None:
        self.name = mcp_tool_def["name"]
        self.description = mcp_tool_def["description"]
        self.parameters = mcp_tool_def["inputSchema"]
        self._client = client

    async def execute(self, **kwargs) -> str:
        result = await self._client.call_tool(self.name, kwargs)
        return str(result)
```

### Step 3: Pass to AgentFactory

```python
factory = AgentFactory(
    tool_providers=[
        BuiltinToolProvider(),
        McpToolProvider("http://localhost:3000", "slack"),
    ]
)
```

MCP tools appear in the registry alongside built-in tools. Per-agent filtering (`enabled_tools`/`disabled_tools`) applies identically.

### What Needs to Be Built

- `McpClient` — handles MCP protocol (stdio/SSE transport)
- `McpTool` — adapter from MCP tool format to `Tool` ABC
- `McpToolProvider` — discovers and wraps MCP tools
- Agent config extension — specify MCP servers per agent (future schema addition)
