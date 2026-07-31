"""Agent factory for creating configured Agent instances."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from the_one.agent.config import BASE_PROMPT, AgentConfig, compose_system_prompt
from the_one.agent.core import Agent
from the_one.agent.store import AgentConfigStore
from the_one.config import settings
from the_one.llm import get_provider
from the_one.llm.registry import PROVIDER_TYPE_MAP
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
    from the_one.tools._search_tools import _build_synthetic_description

    conn = await get_connection()
    encryptor = get_encryptor(settings.data_dir)
    repo = MCPSourceRepository(conn, encryptor)
    for source_id in config.mcp_source_ids or []:
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
                "via search_tools",
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
                input_schema=t.get("input_schema", {"type": "object", "properties": {}}),
                output_schema=None,
                annotations=None,
            )
            for t in cached_tools_payload
        ]
        override_payload = (config.mcp_overrides or {}).get(source.name)
        filtered = filter_mcp_tools_by_override(cached_mcp_tools, source, override_payload)
        prefixed_names = [
            f"mcp__{_normalize_source_name(source.name)}__{mt.name}" for mt in filtered
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


# M19 F01 L02: the provider-type → registry-name map now lives in
# ``the_one.llm.registry.PROVIDER_TYPE_MAP`` (single source of truth for the
# three dispatch callers: this factory, ``connectors/_inference.py``, and the
# provider API branches). The module-load drift assert moved with it.


# ─────────────────────────────────────────────────────────────────────────────
# Module-level factory accessor (M10 F8 L4)
# ─────────────────────────────────────────────────────────────────────────────
#
# Gateway listeners (Discord's ``on_message`` handler in F8, Slack's
# event handler in F9, …) spawn from inside ``plugin.connect`` — i.e.
# inside the pool's per-(agent, account) worker task — so they cannot
# receive an :class:`AgentFactory` reference through the
# ``plugin.connect(account, encryptor)`` signature. Adding it would also
# break the stateless-plugin contract.
#
# Instead, the FastAPI lifespan startup calls :func:`set_factory` once
# after constructing the application factory; listeners call
# :func:`get_factory` at dispatch time. Returns ``None`` during the
# pre-startup window and after shutdown; consumers MUST handle the
# ``None`` case defensively (log and return rather than dereference).
#
# Mirrors the existing precedent at
# ``the_one/interfaces/web/app.py:_get_factory`` (which reads from a
# private dict). The module-level accessor here is the canonical
# subsystem-facing surface; ``app.py``'s helper continues to serve the
# web routes.
#
# Thread-safety: ``set_factory`` is called exactly once at lifespan
# startup (single-task synchronous write); ``get_factory`` reads only
# (no read-write race possible after startup completes). Tests may
# reset the slot to ``None`` between cases.

_factory: "AgentFactory | None" = None


def set_factory(factory: "AgentFactory | None") -> None:
    """Install the application :class:`AgentFactory` for gateway-listener access.

    Called once at FastAPI lifespan startup after constructing the
    factory (see ``the_one/interfaces/web/app.py``). Pass ``None`` at
    teardown to release the reference.
    """
    global _factory
    _factory = factory


def get_factory() -> "AgentFactory | None":
    """Return the application :class:`AgentFactory`, or ``None`` pre-startup.

    Consumed by gateway listeners (Discord's ``on_message`` in F8 L4,
    Slack's event handler in F9, …) at dispatch time. Returns ``None``
    when the lifespan has not yet run :func:`set_factory` or has torn
    down — callers MUST handle this gracefully (log a WARNING and
    return rather than dereferencing).
    """
    return _factory


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

        self.mcp_provider = mcp_provider if mcp_provider is not None else _MCPToolProvider()

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
        registry_name = PROVIDER_TYPE_MAP.get(provider_config.type)
        if registry_name is None:
            raise ValueError(
                f"Unknown provider type '{provider_config.type}'. "
                f"Supported types: {', '.join(sorted(PROVIDER_TYPE_MAP))}"
            )

        provider_kwargs: dict[str, Any] = {
            "model": config.llm_model,
            "base_url": provider_config.base_url,
            "api_key": provider_config.api_key,
            "config": provider_config.config,
        }
        # Only REAL Ollama (type "ollama") gets native /api/chat generation so
        # ``num_ctx`` is honoured. Type "openai-compatible" (LM Studio, vLLM,
        # llama.cpp) shares the OllamaProvider class but MUST stay on /v1 — it
        # has no native endpoint. The flag is provider-specific, so scope it to
        # the ollama registry to avoid passing an unknown kwarg to others.
        if registry_name == "ollama":
            provider_kwargs["native_api"] = provider_config.type == "ollama"
        # M19 F01 L02 (DD-3): plan providers self-resolve their credential
        # source by provider-config id — no static access token is threaded.
        # Scoped to the plan type (mirrors the ``native_api`` scoping above)
        # so no other constructor receives an unexpected kwarg.
        if registry_name == "anthropic-plan":
            provider_kwargs["provider_config_id"] = provider_config.id

        llm = get_provider(registry_name, **provider_kwargs)

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
        tool_configs_repo = ToolConfigRepository(conn, encryptor)
        configs = await tool_configs_repo.list()
        # merged_config() folds the decrypted `secrets` over `config` so the
        # tool-policy resolver / build_search_backend receive the REAL keyed-
        # engine API keys (M16 F08 L03) — not the masked admin-GET view.
        tool_configs_by_name = {c.name: c.merged_config() for c in configs}
        disabled_names = {c.name for c in configs if not c.enabled}
        agent_overrides = config.tool_overrides or {}

        # F4 (M10) L3: connector carve-out flags.
        # - connector_attached: agent has at least one connector account.
        # - send_tool_enabled: the platform-send tool passes both the operator
        #   filter (not in disabled_names) AND the per-agent filter
        #   (config.is_tool_enabled). This is the SAME predicate the
        #   registry-build for-loop below uses.
        # The carve-out (loading the tool's schema into the F10 baseline-
        # visible set) and the system-prompt directive both consult these
        # flags. Computed once here so the post-loop carve-out site reuses.
        connector_attached = bool(config.connector_ids)
        send_tool_enabled = (
            "send_to_platform_channel" not in disabled_names
            and config.is_tool_enabled("send_to_platform_channel")
        )

        # M11 F5 L6 HAT round-8: the M11 F2 L3 per-account
        # ``system_prompt_directive`` collection block was REMOVED here.
        # Mission M11 criterion #14 (operator-editable system-prompt
        # directive per connector account) was reverted in this round;
        # substrate defaults are used universally. The ``operator_directive``
        # kwarg on ``compose_system_prompt`` was likewise removed.
        # The ``system_prompt_directive`` key on persisted
        # ``Connector.config`` is now IGNORED at agent-create time
        # (the API validator no longer accepts it on new writes; old rows
        # that still carry it have no effect on prompt composition).

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

        # Build source_index for SearchTools BEFORE registering it so its
        # constructor receives a fully-populated index. One DB load per
        # attached source; sources with empty _cache.tools are logged +
        # skipped (operator state issue, not a code defect).
        source_index: dict[str, Any] = {}
        if config.mcp_source_ids and self.mcp_provider is not None:
            await _build_source_index(
                config=config,
                agent_name=name,
                source_index=source_index,
            )

        # Register the unified search_tools BEFORE the built-in tool loop.
        # It does not depend on other tools; registering first ensures
        # dispatch can find it regardless of the built-in loop's disabled-
        # filter outcomes. Pass agent_name so the plumbing assertion
        # (_agent_name == factory's agent name for every registered tool)
        # holds (test_factory.py L1b).
        registry.register(
            SearchTools(
                on_match=_on_search_match,
                registry=registry,
                source_index=source_index,
                agent_name=name,
            )
        )

        for provider in self.tool_providers:
            if isinstance(provider, BuiltinToolProvider):
                tools = provider.get_tools(
                    tool_configs_by_name,
                    agent_overrides,
                    agent_name=name,
                    connector_ids=config.connector_ids,
                    connector_acls=config.connector_acls,
                )
            else:
                # Non-builtin providers (test stubs, future provider types)
                # use the unwidened signature. Adding `connector_ids`
                # to the ToolProvider Protocol would force every test stub
                # to accept it; the branch keeps the change scoped.
                tools = provider.get_tools(
                    tool_configs_by_name,
                    agent_overrides,
                    agent_name=name,
                )
            for tool in tools:
                if tool.name not in disabled_names and config.is_tool_enabled(tool.name):
                    registry.register(tool)

        # F6 L2: MCP attach. After the built-in tool loop registers
        # disabled-aware tools, the MCPToolProvider produces the
        # per-agent MCP tool list; the same enabled/disabled filter
        # applies (operators can disable an MCP tool by its prefixed
        # name — `disabled_tools=["mcp__github__delete_repo"]`).
        if self.mcp_provider is not None and config.mcp_source_ids:
            mcp_tools = await self.mcp_provider.get_tools_for_agent(config, agent_name=name)
            for tool in mcp_tools:
                if tool.name not in disabled_names and config.is_tool_enabled(tool.name):
                    registry.register(tool)

        # F4 (M10) L3: F10 baseline carve-out. When the agent is connector-
        # attached AND the platform-send tool is enabled (both layers), the
        # tool's schema is pre-loaded into the baseline-visible set so the
        # agent doesn't have to invoke `search_tools` to discover it. The
        # `registry.tool_names` (public @property at tools/base.py:129-131)
        # membership guard is defensive: in test scenarios where the
        # tool_providers list omits BuiltinToolProvider, the tool is absent
        # from the registry and the carve-out cannot fire — instead of
        # crashing, skip silently (the test setup is non-production).
        if (
            connector_attached
            and send_tool_enabled
            and "send_to_platform_channel" in registry.tool_names
        ):
            _send_tool = registry.get("send_to_platform_channel")
            loaded_schemas.append(_send_tool.to_schema())
            loaded_tool_names.add(_send_tool.name)

        # 3. Resolve system prompt
        system_prompt = compose_system_prompt(
            BASE_PROMPT,
            config.system_prompt,
            connector_attached=connector_attached,
            send_tool_enabled=send_tool_enabled,
        )

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
