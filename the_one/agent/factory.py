"""Agent factory for creating configured Agent instances."""

from __future__ import annotations

from the_one.agent.config import AgentConfig
from the_one.agent.core import Agent
from the_one.agent.store import AgentConfigStore
from the_one.config import settings
from the_one.llm import get_provider
from the_one.tools.base import ToolRegistry
from the_one.tools.builtins import BuiltinToolProvider
from the_one.tools.provider import ToolProvider

# Map provider config type to LLM registry name
_PROVIDER_TYPE_MAP = {
    "ollama": "ollama",
    "openai-compatible": "ollama",
    "openai": "openai",
    "anthropic": "anthropic",
}


class AgentFactory:
    """Creates configured Agent instances from named agent definitions."""

    def __init__(
        self,
        store: AgentConfigStore | None = None,
        tool_providers: list[ToolProvider] | None = None,
    ) -> None:
        self.store = store
        self.tool_providers = tool_providers or [BuiltinToolProvider()]

    async def create(self, name: str = "default") -> Agent:
        """Create an Agent instance from a named config."""
        settings.ensure_dirs()
        config = await self._load_config(name)

        if config.provider_config_id is None:
            raise ValueError(
                f"Agent '{name}' has no provider configured. "
                "Please assign a provider in the agent settings."
            )

        # Resolve provider config from DB
        from the_one.db.connection import get_connection
        from the_one.db.repositories import LLMProviderRepository
        from the_one.encryption import get_encryptor

        conn = await get_connection()
        encryptor = get_encryptor(settings.data_dir)
        provider_repo = LLMProviderRepository(conn, encryptor)
        provider_config = await provider_repo.get(config.provider_config_id)

        # Map config type to registry name
        registry_name = _PROVIDER_TYPE_MAP.get(provider_config.type)
        if registry_name is None:
            raise ValueError(
                f"Unknown provider type '{provider_config.type}'. "
                f"Supported types: {', '.join(sorted(_PROVIDER_TYPE_MAP))}"
            )

        llm = get_provider(
            registry_name,
            model=config.llm_model,
            base_url=provider_config.base_url,
            api_key=provider_config.api_key,
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

    async def list_agents(self) -> list[str]:
        """List all available agent names (stored + default)."""
        if self.store is None:
            return ["default"]
        names = set(await self.store.list_agents())
        names.add("default")
        return sorted(names)

    async def _load_config(self, name: str) -> AgentConfig:
        """Load config from store, falling back to default for 'default'."""
        if self.store is not None and await self.store.exists(name):
            return await self.store.load(name)
        if name == "default":
            return self._default_config()
        raise KeyError(f"Unknown agent: {name}")

    def _default_config(self) -> AgentConfig:
        """Synthesize the default agent config from current settings."""
        return AgentConfig(
            name="default",
            description="General-purpose agent with full tool access",
        )
