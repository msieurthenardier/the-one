"""Agent factory for creating configured Agent instances."""

from __future__ import annotations

from the_one.agent.config import AgentConfig
from the_one.agent.core import Agent
from the_one.agent.store import AgentConfigStore
from the_one.config import settings
from the_one.db._provider_types import PROVIDER_TYPES
from the_one.llm import get_provider
from the_one.tools.base import ToolRegistry
from the_one.tools.builtins import BuiltinToolProvider
from the_one.tools.provider import ToolProvider

# Map provider config type to LLM registry name. Keys MUST equal
# ``PROVIDER_TYPES`` exactly (pinned by
# ``tests/test_provider_types_consistency.py``); the ``openai-compatible`` →
# ``ollama`` re-route is the one historical alias and lives here only.
_PROVIDER_TYPE_MAP = {
    "ollama": "ollama",
    "openai-compatible": "ollama",
    "openai": "openai",
    "anthropic": "anthropic",
    "mock": "mock",
    "openrouter": "openrouter",
}

assert set(_PROVIDER_TYPE_MAP.keys()) == set(PROVIDER_TYPES), (
    "_PROVIDER_TYPE_MAP keys drifted from PROVIDER_TYPES — "
    "every type declared in db/_provider_types.py must dispatch to a registry name."
)


class AgentNotFoundError(KeyError):
    """Raised when a named agent config does not exist.

    Subclasses KeyError for back-compat — callers catching ``KeyError`` still
    work, but new code can disambiguate the agent-vs-provider lookup failures
    via ``isinstance`` / typed except clauses.
    """


class ProviderNotFoundError(KeyError):
    """Raised when an agent's ``provider_config_id`` references a deleted provider.

    Subclasses KeyError for back-compat. Distinct from ``AgentNotFoundError``
    so session-health classification doesn't have to message-match.
    """


class ProviderNotConfiguredError(ValueError):
    """Raised when an agent has no ``provider_config_id`` set.

    Subclasses ValueError for back-compat.
    """


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
            raise ProviderNotConfiguredError(
                f"Agent '{name}' has no provider configured. "
                "Please assign a provider in the agent settings."
            )

        # Resolve provider config from DB
        from the_one.db.connection import get_connection
        from the_one.db.repositories import (
            LLMProviderRepository,
            ToolConfigRepository,
        )
        from the_one.encryption import get_encryptor

        conn = await get_connection()
        encryptor = get_encryptor(settings.data_dir)
        provider_repo = LLMProviderRepository(conn, encryptor)
        try:
            provider_config = await provider_repo.get(config.provider_config_id)
        except KeyError as exc:
            # Repository raises generic KeyError("Provider not found: ...");
            # convert to the typed exception so callers can disambiguate.
            raise ProviderNotFoundError(str(exc)) from exc

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
            config=provider_config.config,
        )

        # 2. Load tool-level configs and agent-level overrides for the
        # tool policy resolver. Resolved per-agent — Decision 8's
        # session-bound freshness contract: mid-session updates apply at
        # the next AgentFactory.create() call.
        #
        # F6 L1: project the full ToolConfig list into TWO derived
        # structures — the resolver-facing `{name: config_dict}` (which
        # `list_all()` would return identically) AND a `disabled_names`
        # set for the registry-build filter. We deliberately do NOT
        # widen `list_all()` to carry `enabled`; pushing the projection
        # to the factory keeps the resolver's API surface pure (see
        # L0's `test_list_all_omits_enabled`).
        tool_configs_repo = ToolConfigRepository(conn)
        configs = await tool_configs_repo.list()
        tool_configs_by_name = {c.name: c.config for c in configs}
        disabled_names = {c.name for c in configs if not c.enabled}
        agent_overrides = config.tool_overrides or {}

        # 3. Build filtered tool registry — fresh ToolRegistry per call,
        # populated with fresh per-agent tool instances (the provider
        # invokes the resolver internally per Decision 10). The filter
        # composes operator-disable (tool_configs.enabled) with per-agent
        # disable (config.is_tool_enabled) — both must pass.
        registry = ToolRegistry()
        for provider in self.tool_providers:
            for tool in provider.get_tools(tool_configs_by_name, agent_overrides, agent_name=name):
                if tool.name not in disabled_names and config.is_tool_enabled(tool.name):
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
        raise AgentNotFoundError(f"Unknown agent: {name}")

    def _default_config(self) -> AgentConfig:
        """Synthesize the default agent config from current settings."""
        return AgentConfig(
            name="default",
            description="General-purpose agent with full tool access",
        )
