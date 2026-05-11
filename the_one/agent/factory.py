"""Agent factory for creating configured Agent instances."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from the_one.agent.config import AgentConfig
from the_one.agent.core import Agent
from the_one.agent.store import AgentConfigStore
from the_one.config import settings
from the_one.db._provider_types import PROVIDER_TYPES
from the_one.llm import get_provider
from the_one.tools._search_mcps import SearchMcps
from the_one.tools._search_tools import SearchTools
from the_one.tools.base import ToolRegistry
from the_one.tools.builtins import BuiltinToolProvider
from the_one.tools.provider import ToolProvider

if TYPE_CHECKING:
    # Type-only import — ``MCPToolProvider`` is lazy-imported at __init__
    # call time (see comment in ``AgentFactory.__init__``). This block
    # only runs under static type checkers; no runtime cost. Without
    # this, ruff F821 flags the string-quoted annotation as undefined.
    from the_one.mcp._tool_provider import MCPToolProvider

logger = logging.getLogger(__name__)

async def _build_source_index(
    config: AgentConfig,
    agent_name: str,
    source_index: dict[str, Any],
) -> None:
    """Populate ``source_index`` in-place for each attached MCP source.

    Reads ``_cache.tools`` from the source's config (populated by the
    source-edit page Refresh action), applies ``mcp_overrides`` filtering
    via the shared ``filter_mcp_tools_by_override`` helper, and builds a
    synthetic description from the filtered tool short-names. Sources with
    empty ``_cache.tools`` are logged at WARNING and skipped.

    All imports are lazy (inside the function body) to avoid the circular
    import cycle: ``agent.__init__`` → ``agent.factory`` → ``db.repositories``
    → ``agent.config`` → ``agent.__init__``. Any DB/MCP import that transitively
    reaches ``the_one.agent`` must stay lazy here.

    F10 L3: module-level helper so tests can patch
    ``the_one.agent.factory.MCPSourceRepository`` (or
    ``the_one.db.repositories.MCPSourceRepository``) without touching the
    ``MCPToolProvider`` path. The function mutates ``source_index`` (passed
    by reference) rather than returning it so the caller's variable binding
    is preserved.
    """
    # Lazy imports — all of these transitively reach db.repositories which
    # reaches agent.config, triggering the circular-import cycle if imported
    # at module level in factory.py.
    from the_one.db.connection import get_connection
    from the_one.db.repositories import MCPSourceRepository
    from the_one.encryption import get_encryptor
    from the_one.mcp._tool import _normalize_source_name
    from the_one.mcp._tool_provider import filter_mcp_tools_by_override
    from the_one.mcp.types import MCPTool
    from the_one.tools._search_mcps import _build_synthetic_description

    conn = await get_connection()
    encryptor = get_encryptor(settings.data_dir)
    repo = MCPSourceRepository(conn, encryptor)
    for source_id in (config.mcp_source_ids or []):
        try:
            source = await repo.get(source_id)
        except (KeyError, Exception):
            # KeyError: deleted source — already warned by
            # MCPToolProvider.get_tools_for_agent; skip silently here.
            # Other exceptions (e.g. DB connectivity): log + skip.
            continue
        cached_tools_payload: list[dict[str, Any]] = (
            source.config.get("_cache", {}).get("tools") or []
        )
        if not cached_tools_payload:
            logger.warning(
                "agent %r: MCP source %r has no cached tools; "
                "refresh on source-edit page to enable discovery "
                "via search_mcps",
                agent_name,
                source.name,
            )
            continue
        # Reconstruct MCPTool objects from cached payload for the filter
        # helper. MCPTool has FIVE required fields; the _cache.tools payload
        # only stores the first three — pass None for output_schema and
        # annotations so the frozen dataclass constructs cleanly.
        cached_mcp_tools = [
            MCPTool(
                name=t["name"],
                description=t.get("description", ""),
                input_schema=t.get(
                    "input_schema", {"type": "object", "properties": {}}
                ),
                output_schema=None,
                annotations=None,
            )
            for t in cached_tools_payload
        ]
        override_payload = (config.mcp_overrides or {}).get(source.name)
        filtered = filter_mcp_tools_by_override(
            cached_mcp_tools, source, override_payload
        )
        prefixed_names = [
            f"mcp__{_normalize_source_name(source.name)}__{mt.name}"
            for mt in filtered
        ]
        synthetic_description = _build_synthetic_description(
            source.name,
            [mt.name for mt in filtered],
            char_cap=200,
        )
        source_index[source.name] = {
            "synthetic_description": synthetic_description,
            "tool_names_prefixed": prefixed_names,
        }


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
        mcp_provider: "MCPToolProvider | None" = None,
    ) -> None:
        self.store = store
        self.tool_providers = tool_providers or [BuiltinToolProvider()]
        # F6 L2: MCPToolProvider injected for testability; default to
        # fresh instance. Tests pass None to disable MCP wiring. Lazy
        # import inside __init__ avoids a circular-import risk because
        # ``mcp._tool_provider`` imports ``agent.config`` (indirectly via
        # the resolver chain). Keep this import lazy.
        from the_one.mcp._tool_provider import MCPToolProvider as _MCPToolProvider
        self.mcp_provider = (
            mcp_provider if mcp_provider is not None else _MCPToolProvider()
        )

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

        # F10 L1: shared state containers for the visibility filter. Both
        # the stub search tools and the Agent reference these — stubs MUTATE
        # them as a side effect of being called; the Agent READS them to
        # compute model-visible schemas per iteration (§3: registry holds the
        # FULL candidate set; _loaded_schemas is purely a model-visibility
        # filter; dispatch via self.tools.get(name) always finds the tool).
        loaded_schemas: list[dict] = []
        loaded_tool_names: set[str] = set()

        def _on_search_match(schemas: list[dict]) -> None:
            """Extend the shared visibility set with newly-matched schemas.

            Idempotent — re-adding a schema already in the set is a no-op.
            Uses name-set for O(1) dedup so callers can freely re-invoke
            search without growing the loaded set unnecessarily.
            """
            for s in schemas:
                if s["name"] not in loaded_tool_names:
                    loaded_schemas.append(s)
                    loaded_tool_names.add(s["name"])

        # F10 L3: build source_index for SearchMcps BEFORE registering
        # SearchMcps so its constructor receives a fully-populated index.
        # Uses a separate DB load per attached source (option (b) from
        # leg artifact §Outputs) — clean separation, ~5 LOC of extra DB
        # calls, simple to reason about, no public API churn on
        # get_tools_for_agent. Sources with empty _cache.tools are logged
        # + skipped (operator state issue, not a code defect).
        source_index: dict[str, Any] = {}
        if config.mcp_source_ids and self.mcp_provider is not None:
            await _build_source_index(
                config=config,
                agent_name=name,
                source_index=source_index,
            )

        # Register search tools BEFORE the built-in tool loop. They do not
        # depend on other tools; registering first ensures dispatch can find
        # them regardless of the built-in loop's disabled-filter outcomes.
        # Pass agent_name so the plumbing assertion (_agent_name == factory's
        # agent name for every registered tool) holds (test_factory.py L1b).
        registry.register(SearchTools(on_match=_on_search_match, registry=registry, agent_name=name))
        # F10 L3: register real SearchMcps with the populated source_index.
        # SearchMcpsStub replaced here.
        registry.register(SearchMcps(on_match=_on_search_match, registry=registry, source_index=source_index, agent_name=name))

        for provider in self.tool_providers:
            for tool in provider.get_tools(tool_configs_by_name, agent_overrides, agent_name=name):
                if tool.name not in disabled_names and config.is_tool_enabled(tool.name):
                    registry.register(tool)

        # F6 L2: MCP attach. After the built-in tool loop registers
        # disabled-aware tools, the MCPToolProvider produces the
        # per-agent MCP tool list; the same enabled/disabled filter
        # applies (operators can disable an MCP tool by its prefixed
        # name — `disabled_tools=["mcp__github__delete_repo"]`).
        if self.mcp_provider is not None and config.mcp_source_ids:
            mcp_tools = await self.mcp_provider.get_tools_for_agent(
                config, agent_name=name
            )
            for tool in mcp_tools:
                if tool.name not in disabled_names and config.is_tool_enabled(tool.name):
                    registry.register(tool)

        # 3. Resolve system prompt
        system_prompt = config.get_system_prompt()

        # 4. Create agent
        # F10 L1: pass the shared containers so the Agent's
        # _compute_visible_schemas() picks up mutations from stub search calls.
        return Agent(
            llm=llm,
            tools=registry,
            system_prompt=system_prompt,
            max_iterations=config.max_iterations,
            loaded_schemas=loaded_schemas,
            loaded_tool_names=loaded_tool_names,
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
