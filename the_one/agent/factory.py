"""Agent factory for creating configured Agent instances."""

from __future__ import annotations

from the_one.agent.config import AgentConfig
from the_one.agent.core import Agent
from the_one.agent.store import AgentConfigStore, FilesystemConfigStore
from the_one.config import settings
from the_one.llm import get_provider
from the_one.tools.base import ToolRegistry
from the_one.tools.builtins import BuiltinToolProvider
from the_one.tools.provider import ToolProvider


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
        settings.ensure_dirs()
        config = self._load_config(name)

        # 1. Get LLM provider — always pass base_url unconditionally
        llm = get_provider(
            config.llm_provider, model=config.llm_model, base_url=config.llm_base_url
        )

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
