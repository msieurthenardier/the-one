"""Agent factory for creating configured Agent instances."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from the_one.agent.config import AgentConfig
from the_one.agent.core import Agent
from the_one.agent.prompt_layers import build_system_prompt, time_tool_available
from the_one.agent.store import AgentConfigStore
from the_one.config import settings
from the_one.llm import get_provider
from the_one.llm.registry import PROVIDER_TYPE_MAP
from the_one.time_zones import CURRENT_TIME_TOOL_NAME
from the_one.tools._search_tools import SearchTools
from the_one.tools.base import Tool, ToolRegistry
from the_one.tools.builtins import BuiltinToolProvider
from the_one.tools.connector_lookup import FIND_PLATFORM_DESTINATION_TOOL_NAME
from the_one.tools.connector_send import SEND_TO_PLATFORM_CHANNEL_TOOL_NAME
from the_one.tools.provider import ToolProvider

if TYPE_CHECKING:
    # Type-only imports — both ``KBToolProvider`` and ``MCPToolProvider``
    # are lazy-imported at __init__ call time (see comments in
    # ``AgentFactory.__init__``) to avoid the circular import cycle
    # ``agent.__init__ -> agent.factory -> db.repositories -> agent.config
    # -> agent.__init__`` that ``_build_source_index``'s docstring records.
    # This block only runs under static type checkers; no runtime cost.
    # Without it, ruff F821 flags the string-quoted annotations as
    # undefined.
    from the_one.knowledge.tool_provider import KBToolProvider
    from the_one.mcp._tool_provider import MCPToolProvider
    from the_one.notes.tool_provider import NotesToolProvider

logger = logging.getLogger(__name__)


def _kb_tool_is_disabled(tool: Tool, disabled_tools: list[str]) -> bool:
    """M24 F07 L01, DD-13: read-side reconcile for the detach -> rename ->
    reattach hole. ``compute_tool_names`` (``knowledge/tool_provider.py``)
    applies the ``sha256(kb_id)`` discriminator to a ``kb__…__search``
    name UNCONDITIONALLY, so it is a stable fingerprint of the knowledge
    base's identity that survives a rename — this treats a
    ``disabled_tools`` entry as disabling ``tool`` when the entry carries
    a discriminator derived from ``tool.kb_id``, even when the entry's
    slug no longer matches ``tool``'s CURRENT name (a stale entry left
    behind by a rename that happened while the knowledge base was
    detached, the one case ``knowledge/kb_rename.py``'s write-side
    rewrite structurally cannot see — it only reaches currently-attached
    agents).

    This is exactly equivalent to the un-reconciled ``tool.name in
    disabled_tools`` for a CURRENT-name entry (the exact-match check
    below), plus the reconcile for a STALE one. Only called for `kb__`
    tools (which always carry a real ``kb_id``) — the AC-15 caller never
    mutates ``disabled_tools``; this returns a plain bool over a local
    view.

    **The matching rule never parses the slug** (a knowledge-base name
    can itself normalize to a slug containing ``_``/``__`` —
    ``tool_provider.py:82-86``): it strips the fixed ``kb__``/``__search``
    wrapper and checks only whether what remains ENDS WITH
    ``"_" + discriminator``, tried at every ``_HASH_LENGTHS`` width (8,
    12, 16 — AC-12) since the discriminator can widen on a slug
    collision within the SET the name was originally computed against.
    """
    if tool.name in disabled_tools:
        return True

    kb_id = getattr(tool, "kb_id", None)
    if kb_id is None or not disabled_tools:
        return False

    from the_one.knowledge.tool_provider import (
        _HASH_LENGTHS,
        _NAME_PREFIX,
        _NAME_SUFFIX,
        _discriminator,
    )

    discriminators = {_discriminator(kb_id, hash_len) for hash_len in _HASH_LENGTHS}
    for entry in disabled_tools:
        if not (entry.startswith(_NAME_PREFIX) and entry.endswith(_NAME_SUFFIX)):
            continue
        body = entry[len(_NAME_PREFIX) : -len(_NAME_SUFFIX)]
        if any(body.endswith("_" + disc) for disc in discriminators):
            return True
    return False


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
# ``the_one.llm.registry.PROVIDER_TYPE_MAP`` (single source of truth for
# this factory and the provider API branches — the connector dispatcher's
# ``connectors/_inference.py`` was a third caller before Mission 23 Flight 1
# deleted the connector package). The module-load drift assert moved with it.


# ─────────────────────────────────────────────────────────────────────────────
# Module-level factory accessor (M10 F8 L4; Mission 23 Flight 2 gave it its
# first real caller after the connector reset)
# ─────────────────────────────────────────────────────────────────────────────
#
# A connector plugin's gateway listener spawns from inside ``plugin.connect``
# — i.e. inside the pool's per-(agent, account) worker task — so it cannot
# receive an :class:`AgentFactory` reference through the
# ``plugin.connect(account, encryptor, on_inbound)`` signature. Adding it
# would also break the stateless-plugin contract.
#
# Instead, the FastAPI lifespan startup calls :func:`set_factory` once
# after constructing the application factory; the connector inbound
# pipeline (``the_one/connectors/inbound.py::dispatch_inbound``, invoked
# from the ``on_inbound`` callback ``ConnectorManager`` threads into every
# ``plugin.connect`` call) calls :func:`get_factory` at dispatch time —
# today exercised through the stub plugin's test seams; Discord (Flight 3)
# and later platforms (Flight 4) will drive the same path through a real
# gateway listener. Returns ``None`` during the pre-startup window and
# after shutdown; consumers MUST handle the ``None`` case defensively (log
# and return rather than dereference) — ``dispatch_inbound`` does exactly
# this.
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
    """Install the application :class:`AgentFactory` for connector-listener access.

    Called once at FastAPI lifespan startup after constructing the
    factory (see ``the_one/interfaces/web/app.py``). Pass ``None`` at
    teardown to release the reference.
    """
    global _factory
    _factory = factory


def get_factory() -> "AgentFactory | None":
    """Return the application :class:`AgentFactory`, or ``None`` pre-startup.

    Consumed by the connector inbound pipeline
    (``the_one/connectors/inbound.py::dispatch_inbound``) at dispatch
    time — today via the stub plugin's test seams, and via a real gateway
    listener once Discord (Flight 3) and later platforms (Flight 4) land.
    Returns ``None`` when the lifespan has not yet run :func:`set_factory`
    or has torn down — callers MUST handle this gracefully (log a WARNING
    and return rather than dereferencing).
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
        kb_provider: "KBToolProvider | None" = None,
        notes_provider: "NotesToolProvider | None" = None,
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

        # Flight 5 Leg 2 (DD-5, AC-14): KBToolProvider injected the same
        # way, for the same testability reason — tests pass None to
        # disable KB wiring. Lazy import for the same cycle-avoidance
        # reason as MCPToolProvider above.
        from the_one.knowledge.tool_provider import KBToolProvider as _KBToolProvider

        self.kb_provider = kb_provider if kb_provider is not None else _KBToolProvider()

        # Mission 27 F2 (DD3): NotesToolProvider injected the same way (lazy
        # import for the same cycle-avoidance reason); tests pass a stub.
        from the_one.notes.tool_provider import NotesToolProvider as _NotesToolProvider

        self.notes_provider = notes_provider if notes_provider is not None else _NotesToolProvider()

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
        # Token plan type: the pasted setup-token (stored in ``api_key``) is
        # the bearer. No credential source, so no provider_config_id.
        elif registry_name == "anthropic-plan-token":
            provider_kwargs["access_token"] = provider_config.api_key

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
            # Mission 23 Flight 1 (backend-removal leg): this used to branch
            # on `isinstance(provider, BuiltinToolProvider)` to pass extra
            # `connector_ids`/`connector_acls` construction kwargs — removed
            # with the connector package (DD-4), so every provider now takes
            # the same call shape.
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

        # Flight 5 Leg 2 (DD-5 AC-15/AC-16): knowledge-base tool attach,
        # immediately after the MCP block, behind the SAME filter. Guarded
        # only by `self.kb_provider is not None` (mirroring the MCP idiom
        # above) even though `get_tools_for_agent` already returns `[]`
        # cheaply for an empty `config.kb_ids` (AC-12) — a reader expects
        # the same structural shape as the MCP block. No ordering
        # constraint relative to `SearchTools`'s registration above: DD-7's
        # amendment removed the `source_index` entries that used to create
        # one. Registering last does NOT make these tools shadow-proof in
        # general (`ToolRegistry.register` is `self._tools[name] = tool` —
        # last-write-wins) — it is safe here only because the `kb__` prefix
        # makes a name collision with a built-in or MCP tool impossible.
        # DD-13: `config.is_tool_enabled(tool.name)` is replaced here (ONLY
        # here — the shared method itself is untouched, per DD-13's own
        # scoping) with the reconciled disable check. For a `kb__` name
        # `is_tool_enabled` reduces to `tool.name not in
        # config.disabled_tools` (`kb__` is in `UNGATED_TOOL_PREFIXES`, so
        # the `enabled_tools` whitelist branch never applies) — so this is
        # exactly that check, plus the stale-entry reconcile.
        # `_kb_tool_is_disabled` never mutates `config.disabled_tools`
        # (AC-15): it only ever reads it.
        if self.kb_provider is not None:
            kb_tools = await self.kb_provider.get_tools_for_agent(config, agent_name=name)
            for tool in kb_tools:
                if tool.name not in disabled_names and not _kb_tool_is_disabled(
                    tool, config.disabled_tools
                ):
                    registry.register(tool)

        # Mission 27 F2 (DD3): the notes tools, only when the operator's
        # `notes_enabled` switch is on. Registered OUTSIDE the
        # `is_tool_enabled` / `disabled_names` filter on purpose: they are not
        # built-ins, so a built-in-only `enabled_tools` whitelist must never
        # strip them. The notes switch is their only control.
        notes_tools: list[Tool] = []
        if self.notes_provider is not None:
            notes_tools = await self.notes_provider.get_tools_for_agent(config, agent_name=name)
            for tool in notes_tools:
                registry.register(tool)

        # DD-5 (Mission 23 Flight 3 Leg 2, mission-owner-amended baseline-
        # visibility carve-out): SEED the containers rather than append
        # inside Agent._compute_visible_schemas — a pre-seeded name is
        # automatically covered by _on_search_match's dedup above, so a
        # later search_tools hit never sends the model a duplicate schema.
        # Membership check via tool_names (a KeyError-free `in` check) —
        # NOT registry.get(...), which raises KeyError when the tool was
        # filtered out above (disabled operator-side or per-agent).
        #
        # DD-6 (Mission 23 Flight 4 Leg 3): generalized to the connector
        # tool PAIR — the lookup tool joins the send tool in this same
        # sanctioned seed block (a two-name iteration; `agent/core.py`
        # stays untouched, the seed/reset mechanism already handles N
        # entries). `fetch_channel_history` deliberately stays
        # search-discovered (not chain-critical) and is NOT seeded here.
        for seed_tool_name in (
            SEND_TO_PLATFORM_CHANNEL_TOOL_NAME,
            FIND_PLATFORM_DESTINATION_TOOL_NAME,
            CURRENT_TIME_TOOL_NAME,
        ):
            if seed_tool_name in registry.tool_names:
                seed_tool = registry.get(seed_tool_name)
                loaded_schemas.append(seed_tool.to_schema())
                loaded_tool_names.add(seed_tool_name)

        # Mission 27 F2 (DD3): seed the notes tools into the baseline so they
        # are visible from the first turn (factory-only: `agent/core.py` is
        # frozen and its seed/reset mechanism already handles N entries).
        for notes_tool in notes_tools:
            loaded_schemas.append(notes_tool.to_schema())
            loaded_tool_names.add(notes_tool.name)

        # 3. Resolve system prompt
        tool_available = await time_tool_available(registry, llm)
        system_prompt = await build_system_prompt(
            config.name, config.system_prompt, conn=conn, tool_available=tool_available
        )

        # 4. Create agent
        # F10 L1: pass the shared containers so the Agent's
        # _compute_visible_schemas() picks up mutations from stub search calls.
        agent = Agent(
            llm=llm,
            tools=registry,
            system_prompt=system_prompt,
            max_iterations=config.max_iterations,
            loaded_schemas=loaded_schemas,
            loaded_tool_names=loaded_tool_names,
        )
        # Mission 27 F2 (DD5/DD6): each notes tool reads its owning Agent's
        # messages at execute time to compute the untrusted flag. Bound after
        # construction (the Agent does not exist while tools are built).
        for notes_tool in notes_tools:
            notes_tool.bind_agent(agent)  # type: ignore[attr-defined]
        return agent

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
