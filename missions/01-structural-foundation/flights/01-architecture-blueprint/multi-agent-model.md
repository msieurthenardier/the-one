# Multi-Agent Model

## AgentConfig Model

```python
from pydantic import BaseModel, Field
from typing import Any


class AgentConfig(BaseModel):
    """Definition of an agent's identity and capabilities."""

    # Identity
    name: str                                          # Unique identifier (slug, e.g. "default", "code-reviewer")
    description: str = ""                              # Human-readable purpose

    # LLM
    llm_provider: str = "ollama"                       # Provider name (ollama, openai, anthropic)
    llm_model: str = "qwen2.5:7b"                      # Model identifier
    llm_base_url: str | None = None                    # Override provider's default base URL

    # Prompt
    system_prompt: str = ""                            # Full system prompt (empty = use DEFAULT_SYSTEM_PROMPT)

    # Tools
    enabled_tools: list[str] | None = None             # Whitelist (None = all tools)
    disabled_tools: list[str] = Field(default_factory=list)  # Blacklist (always applied after whitelist)

    # Behavior
    max_iterations: int = 20                           # Safety limit for agent loop
    direct_actions: bool = True                        # Enable regex-based direct action bypass

    def is_tool_enabled(self, tool_name: str) -> bool:
        """Check if a specific tool should be available to this agent."""
        if self.enabled_tools is not None and tool_name not in self.enabled_tools:
            return False
        if tool_name in self.disabled_tools:
            return False
        return True

    def get_system_prompt(self) -> str:
        """Return the effective system prompt (default if empty)."""
        return self.system_prompt if self.system_prompt else DEFAULT_SYSTEM_PROMPT
```

### Field Semantics

| Field | Type | Default | Meaning |
|-------|------|---------|---------|
| `name` | `str` | required | Unique slug identifier. Used as filename (`{name}.json`) and factory key. |
| `description` | `str` | `""` | What this agent is for. Not sent to the LLM. |
| `llm_provider` | `str` | `"ollama"` | Must match a registered provider name in `llm/registry.py`. |
| `llm_model` | `str` | `"qwen2.5:7b"` | Passed to the provider constructor. |
| `llm_base_url` | `str \| None` | `None` | If set, overrides the provider's default URL. Useful for pointing ollama at a remote host. |
| `system_prompt` | `str` | `""` | Full system prompt text. Empty string means "use `DEFAULT_SYSTEM_PROMPT`". |
| `enabled_tools` | `list[str] \| None` | `None` | If `None`, all tools from all providers are available. If a list, only named tools are included. |
| `disabled_tools` | `list[str]` | `[]` | Tools to exclude regardless of `enabled_tools`. Blacklist always wins. |
| `max_iterations` | `int` | `20` | Maximum LLM call iterations per `agent.step()`. Safety valve. |
| `direct_actions` | `bool` | `True` | Whether regex-based shortcuts (restart, rollback) bypass the LLM. |

---

## Agent Definition JSON Schema

Agent definitions are stored as JSON files at `{settings.data_dir}/agents/{name}.json` (default: `~/.the-one/agents/{name}.json`).

### Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["name"],
  "properties": {
    "name": {
      "type": "string",
      "pattern": "^[a-z0-9][a-z0-9-]*$",
      "description": "Unique slug identifier"
    },
    "description": {
      "type": "string",
      "default": ""
    },
    "llm_provider": {
      "type": "string",
      "default": "ollama"
    },
    "llm_model": {
      "type": "string",
      "default": "qwen2.5:7b"
    },
    "llm_base_url": {
      "type": ["string", "null"],
      "default": null
    },
    "system_prompt": {
      "type": "string",
      "default": ""
    },
    "enabled_tools": {
      "type": ["array", "null"],
      "items": { "type": "string" },
      "default": null
    },
    "disabled_tools": {
      "type": "array",
      "items": { "type": "string" },
      "default": []
    },
    "max_iterations": {
      "type": "integer",
      "minimum": 1,
      "default": 20
    },
    "direct_actions": {
      "type": "boolean",
      "default": true
    }
  },
  "additionalProperties": false
}
```

### Example: Code Reviewer Agent

```json
{
  "name": "code-reviewer",
  "description": "Reviews code changes for quality, security, and consistency",
  "llm_provider": "anthropic",
  "llm_model": "claude-sonnet-4-6",
  "system_prompt": "You are a code reviewer for the-one project. Review changes for correctness, security issues, and adherence to project conventions. You have read-only access to the filesystem and git history. Never modify files.",
  "enabled_tools": ["read_file", "list_dir", "git", "shell"],
  "disabled_tools": ["write_file", "self_deploy", "restart", "rollback"],
  "max_iterations": 10,
  "direct_actions": false
}
```

---

## Default Agent Config

When no agent config file exists, or when `factory.create("default")` is called without a matching file, the factory uses this hardcoded fallback:

```python
DEFAULT_AGENT_CONFIG = AgentConfig(
    name="default",
    description="General-purpose agent with full tool access",
    llm_provider=settings.llm_provider,     # From THE_ONE_LLM_PROVIDER env var
    llm_model=settings.llm_model,           # From THE_ONE_LLM_MODEL env var
    llm_base_url=settings.llm_base_url if hasattr(settings, 'llm_base_url') else None,
    system_prompt="",                        # Empty = DEFAULT_SYSTEM_PROMPT
    enabled_tools=None,                      # All tools
    disabled_tools=[],                       # No exclusions
    max_iterations=20,
    direct_actions=True,
)
```

This produces **identical behavior** to the current hardcoded setup:
- Same LLM provider and model (from env vars)
- Same system prompt (`DEFAULT_SYSTEM_PROMPT`, which is the current `SYSTEM_PROMPT`)
- All 14 tools enabled
- Direct actions enabled
- 20 iteration limit

The default agent config is constructed at factory initialization time, not at module level, so it always reflects current settings values.

---

## AgentConfigStore Protocol

```python
from typing import Protocol, runtime_checkable


@runtime_checkable
class AgentConfigStore(Protocol):
    """Protocol for persisting and retrieving agent configurations."""

    def list_agents(self) -> list[str]:
        """Return names of all stored agent configs."""
        ...

    def load(self, name: str) -> AgentConfig:
        """Load an agent config by name. Raises KeyError if not found."""
        ...

    def save(self, config: AgentConfig) -> None:
        """Persist an agent config. Creates or overwrites."""
        ...

    def delete(self, name: str) -> None:
        """Delete an agent config by name. Raises KeyError if not found."""
        ...

    def exists(self, name: str) -> bool:
        """Check if a named agent config exists."""
        ...
```

### Design Notes

- `runtime_checkable` allows `isinstance()` checks if needed
- `load()` raises `KeyError` (not returns `None`) — callers must handle missing configs explicitly
- `save()` is idempotent — creates or overwrites
- The protocol does not include a `list_agents_with_details()` — callers load individually if they need details
- No async methods — filesystem operations are fast enough for sync, and this avoids async ceremony for 2-5 config files

---

## FilesystemConfigStore

```python
import json
from pathlib import Path


class FilesystemConfigStore:
    """Stores agent configs as JSON files in a directory."""

    def __init__(self, agents_dir: Path) -> None:
        self.agents_dir = agents_dir

    def list_agents(self) -> list[str]:
        if not self.agents_dir.exists():
            return []
        return sorted(
            p.stem for p in self.agents_dir.glob("*.json")
        )

    def load(self, name: str) -> AgentConfig:
        path = self._path(name)
        if not path.exists():
            raise KeyError(f"Agent config not found: {name}")
        data = json.loads(path.read_text())
        return AgentConfig.model_validate(data)

    def save(self, config: AgentConfig) -> None:
        self.agents_dir.mkdir(parents=True, exist_ok=True)
        path = self._path(config.name)
        # Serialize only non-default fields for cleaner JSON
        data = {
            "name": config.name,
            "description": config.description,
        }
        # Include fields that differ from defaults
        defaults = AgentConfig(name=config.name)
        for field_name in ("llm_provider", "llm_model", "llm_base_url",
                          "system_prompt", "enabled_tools", "disabled_tools",
                          "max_iterations", "direct_actions"):
            value = getattr(config, field_name)
            if value != getattr(defaults, field_name):
                data[field_name] = value
        path.write_text(json.dumps(data, indent=2) + "\n")

    def delete(self, name: str) -> None:
        path = self._path(name)
        if not path.exists():
            raise KeyError(f"Agent config not found: {name}")
        path.unlink()

    def exists(self, name: str) -> bool:
        return self._path(name).exists()

    def _path(self, name: str) -> Path:
        return self.agents_dir / f"{name}.json"
```

### Directory Structure

```
~/.the-one/
├── agents/
│   ├── code-reviewer.json
│   └── researcher.json
└── cli_history
```

The `default` agent does NOT have a JSON file by default — it's synthesized from settings. Users can create `default.json` to customize the default agent, which overrides the synthesized config.

---

## AgentFactory

```python
from the_one.agent.config import AgentConfig, DEFAULT_SYSTEM_PROMPT
from the_one.agent.core import Agent
from the_one.agent.store import AgentConfigStore, FilesystemConfigStore
from the_one.config import settings
from the_one.llm import get_provider
from the_one.tools.base import ToolRegistry
from the_one.tools.builtins import BuiltinToolProvider


class AgentFactory:
    """Creates configured Agent instances from named agent definitions."""

    def __init__(
        self,
        store: AgentConfigStore | None = None,
        tool_providers: list[ToolProvider] | None = None,
    ) -> None:
        self.store = store or FilesystemConfigStore(settings.agents_dir)
        self.tool_providers = tool_providers or [BuiltinToolProvider()]

    def create(self, name: str = "default") -> Agent:
        """Create an Agent instance from a named config."""
        config = self._load_config(name)

        # 1. Get LLM provider
        provider_kwargs = {"model": config.llm_model}
        if config.llm_base_url:
            provider_kwargs["base_url"] = config.llm_base_url
        llm = get_provider(config.llm_provider, **provider_kwargs)

        # 2. Build filtered tool registry
        registry = ToolRegistry()
        for provider in self.tool_providers:
            for tool in provider.get_tools():
                if config.is_tool_enabled(tool.name):
                    registry.register(tool)

        # 3. Resolve system prompt
        system_prompt = config.get_system_prompt()

        # 4. Create agent
        return Agent(
            llm=llm,
            tools=registry,
            system_prompt=system_prompt,
            max_iterations=config.max_iterations,
        )

    def list_agents(self) -> list[str]:
        """List all available agent names (stored + default)."""
        names = set(self.store.list_agents())
        names.add("default")
        return sorted(names)

    def _load_config(self, name: str) -> AgentConfig:
        """Load config from store, falling back to default for 'default'."""
        if self.store.exists(name):
            return self.store.load(name)
        if name == "default":
            return self._default_config()
        raise KeyError(f"Unknown agent: {name}")

    def _default_config(self) -> AgentConfig:
        """Synthesize the default agent config from current settings."""
        return AgentConfig(
            name="default",
            description="General-purpose agent with full tool access",
            llm_provider=settings.llm_provider,
            llm_model=settings.llm_model,
            llm_base_url=settings.llm_base_url,
        )
```

### Factory Workflow

```
factory.create("code-reviewer")
    │
    ├── 1. Load config from store (or default)
    │       └── FilesystemConfigStore.load("code-reviewer")
    │           └── Read ~/.the-one/agents/code-reviewer.json
    │           └── Parse into AgentConfig
    │
    ├── 2. Get LLM provider
    │       └── get_provider("anthropic", model="claude-sonnet-4-6")
    │
    ├── 3. Build filtered ToolRegistry
    │       ├── BuiltinToolProvider.get_tools() → 14 tools
    │       └── Filter by config.is_tool_enabled() → 4 tools
    │
    ├── 4. Resolve system prompt
    │       └── config.system_prompt (custom) or DEFAULT_SYSTEM_PROMPT
    │
    └── 5. Return Agent(llm, tools, system_prompt, max_iterations)
```

---

## Interface Changes

### Current: `cli.py`

```python
def _make_agent() -> Agent:
    provider = get_provider(settings.llm_provider, model=settings.llm_model)
    tools = ToolRegistry()
    tools.load_defaults()
    return Agent(llm=provider, tools=tools)
```

### Target: `cli.py`

```python
from the_one.agent.factory import AgentFactory

factory = AgentFactory()
agent = factory.create()  # "default" agent
```

### Current: `web/app.py`

```python
def _make_agent() -> Agent:
    provider = get_provider(settings.llm_provider, model=settings.llm_model)
    tools = ToolRegistry()
    tools.load_defaults()
    return Agent(llm=provider, tools=tools)
```

### Target: `web/app.py`

```python
from the_one.agent.factory import AgentFactory

factory = AgentFactory()

# In session creation:
agent = factory.create()  # Default agent for now
# Future: agent = factory.create(session.agent_name)
```

The factory is instantiated once per process. Each `create()` call produces a fresh Agent instance with its own message history. The factory itself is stateless after initialization — it holds references to the store and tool providers but creates no mutable state.
