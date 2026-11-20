"""Agent factory for creating configured Agent instances."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from typing import TYPE_CHECKING, Any

from the_one.agent.config import AgentConfig
from the_one.agent.core import CONTINUE_SCHEMA, SEARCH_TOOLS_SCHEMA, Agent
from the_one.agent.platform_prompt import capabilities_from_registry
from the_one.agent.prompt_layers import build_system_prompts, time_tool_available
from the_one.agent.store import AgentConfigStore
from the_one.agent.tool_exposure import decide_exposure
from the_one.config import settings
from the_one.db._provider_types import PROVIDER_TYPE_LABELS
from the_one.llm import get_provider
from the_one.llm.registry import PROVIDER_TYPE_MAP
from the_one.naming import GLEEPGLORP_AGENT_NAME
from the_one.secret_store.runtime import SecretResolver
from the_one.self_configuration.constants import override_for
from the_one.time_zones import CURRENT_TIME_TOOL_NAME
from the_one.tools._search_tools import SearchTools
from the_one.tools.base import Tool, ToolRegistry
from the_one.tools.builtins import BuiltinToolProvider
from the_one.tools.connector_history import FETCH_CHANNEL_HISTORY_TOOL_NAME
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
    from the_one.routines.tool_provider import RoutineToolProvider

logger = logging.getLogger(__name__)

# Sortie 11 AC3: the bound on the build-time context-window lookup. A resolver that is
# slower keeps running in the background (held in `_WINDOW_LOOKUP_TASKS`), the agent is
# built on discovery, and the provider's sentinel is set when the resolver finishes.
WINDOW_LOOKUP_TIMEOUT_S = 2.0
# Module-level, not per factory: the context-window route builds a throwaway factory per
# request, and a task with no strong reference can be collected mid-flight.
_WINDOW_LOOKUP_TASKS: set[asyncio.Future] = set()


def _window_lookup_done(task: asyncio.Future) -> None:
    _WINDOW_LOOKUP_TASKS.discard(task)
    if not task.cancelled():
        task.exception()  # retrieve it, so a late failure leaves no "never retrieved" noise


async def _lookup_context_window(llm: Any) -> None:
    """Resolve the provider's context window, bounded; never raises (unknown on any failure)."""
    try:
        resolver = getattr(llm, "_resolve_max_context_tokens_if_needed", None)
        if resolver is None:
            return
        task = asyncio.ensure_future(resolver())
        _WINDOW_LOOKUP_TASKS.add(task)
        task.add_done_callback(_window_lookup_done)
        await asyncio.wait_for(asyncio.shield(task), WINDOW_LOOKUP_TIMEOUT_S)
    except Exception:  # noqa: BLE001 - any failure means "window unknown"
        logger.debug("context window lookup did not complete", exc_info=True)


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
        # Sortie 09 DD4: a stored agent that uses its own credentials on this
        # source reads its per-agent cache (only the build or the route fills it,
        # so a cold row skips the source here); everyone else the shared `_cache`.
        from the_one.mcp._agent_cache import per_agent_tools

        per_agent, per_agent_payload, _ = await per_agent_tools(
            conn, agent_name, config.mcp_overrides, source
        )
        if per_agent:
            cached_tools_payload: list[dict[str, Any]] = per_agent_payload or []
        else:
            cached_tools_payload = source.config.get("_cache", {}).get("tools") or []
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
        override_payload = override_for(config.mcp_overrides, source)
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


class GleepGlorpUnavailableError(ProviderNotConfiguredError):
    """GleepGlorp cannot be built: it is off, has no model, or its provider is gone.

    ``state`` is the setting's derived state (``off``, ``needs_model`` or
    ``provider_missing``).
    """

    def __init__(self, state: str) -> None:
        from the_one.gleepglorp.messages import unavailable_sentence

        self.state = state
        super().__init__(unavailable_sentence(state))


class AgentFactory:
    """Creates configured Agent instances from named agent definitions."""

    def __init__(
        self,
        store: AgentConfigStore | None = None,
        tool_providers: list[ToolProvider] | None = None,
        mcp_provider: "MCPToolProvider | None" = None,
        kb_provider: "KBToolProvider | None" = None,
        notes_provider: "NotesToolProvider | None" = None,
        routines_provider: "RoutineToolProvider | None" = None,
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

        # Mission 33 F2 L3 (DD1): the routine tools, the same way; the provider returns
        # nothing unless the agent's Routines item is on.
        from the_one.routines.tool_provider import RoutineToolProvider as _RoutineToolProvider

        self.routines_provider = (
            routines_provider if routines_provider is not None else _RoutineToolProvider()
        )

    async def create(self, name: str = GLEEPGLORP_AGENT_NAME) -> Agent:
        """Create an Agent instance from a named config.

        The exact name ``GleepGlorp`` (M36 F1 L03, DD1) builds the built-in assistant
        from its settings: it has no ``agents`` row. Every other name is a stored agent.
        """
        settings.ensure_dirs()
        if name == GLEEPGLORP_AGENT_NAME:
            from the_one.db.connection import get_connection as _get_conn
            from the_one.gleepglorp import settings as gg_settings
            from the_one.gleepglorp.build import gleepglorp_config

            _conn = await _get_conn()
            gg = await gg_settings.load_settings(_conn)
            gg_state = await gg_settings.state(_conn, gg)
            if gg_state != "ready":
                raise GleepGlorpUnavailableError(gg_state)
            return await self._build(gleepglorp_config(gg), gleepglorp=True)
        return await self._build(await self._load_config(name))

    async def _build(self, config: AgentConfig, *, gleepglorp: bool = False) -> Agent:
        """Build an Agent from a resolved config (a stored agent's, or GleepGlorp's)."""
        name = config.name

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
            # The name connection errors use: "Ollama", or "OpenAI-compatible" for
            # the shared-class openai-compatible type (M31 F6 L06, DD11 2).
            provider_kwargs["server_label"] = PROVIDER_TYPE_LABELS[provider_config.type]
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
        # structures — the resolver-facing `{name: config_dict}` AND a
        # `disabled_names` set for the registry-build filter. The
        # `enabled` flag stays out of each config dict; the projection
        # lives here so the resolver's API surface stays pure (see
        # `test_list_omits_enabled_from_config`).
        tool_configs_repo = ToolConfigRepository(conn, encryptor)
        configs = await tool_configs_repo.list()
        # merged_config() folds the decrypted `secrets` over `config` so the
        # tool-policy resolver / build_search_backend receive the REAL keyed-
        # engine API keys (M16 F08 L03) — not the masked admin-GET view.
        tool_configs_by_name = {c.name: c.merged_config() for c in configs}
        disabled_names = {c.name for c in configs if not c.enabled}
        if gleepglorp:
            # M36 F1 L06: web search needs a usable engine (a keyed one with a field empty
            # is not); the same function feeds `web_search_available` in the settings.
            from the_one.gleepglorp.web import search_configured

            if not search_configured(
                tool_configs_by_name.get("web_search"), enabled="web_search" not in disabled_names
            ):
                config = config.model_copy(
                    update={
                        "enabled_tools": [
                            t for t in config.enabled_tools or [] if t != "web_search"
                        ]
                    }
                )
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
        # Sortie 09 AC5: the MCP tools are built BEFORE the index so a credentialed
        # agent's cold per-agent cache (filled by that listing) is visible to the
        # index in the same build. They are registered further down, unchanged.
        built_mcp_tools: list[Any] | None = None
        if gleepglorp:
            # DD1: GleepGlorp's config carries no MCP, knowledge or routines (its notes are
            # its own, behind the `memory` setting).
            assert not (
                config.mcp_source_ids or config.kb_ids or config.routines_self_config_enabled
            )
        if self.mcp_provider is not None and config.mcp_source_ids:
            built_mcp_tools = await self.mcp_provider.get_tools_for_agent(config, agent_name=name)
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

        if gleepglorp:
            # M36 F1 L05 (DD5): GleepGlorp's one read tool. Registered here, outside every
            # tool filter (it is not a built-in, so no agent but GleepGlorp can have it).
            from the_one.gleepglorp.read_tool import ReadAppConfigTool

            registry.register(ReadAppConfigTool(agent_name=name))
            # M36 F1 L07 (DD6): the app guide, shipped help text (trusted in the taint rule).
            from the_one.gleepglorp.guide_tool import GetAppGuideTool

            registry.register(GetAppGuideTool(agent_name=name))
            # M36 F2 L2 (DD5): the proposal tool. It records a row and changes nothing else;
            # bound to the agent after construction (below) for the taint scan.
            from the_one.gleepglorp.proposals.tool import ProposeChangeTool

            propose_tool = ProposeChangeTool(agent_name=name)
            registry.register(propose_tool)

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
        # name — `disabled_tools=["mcp__github__delete_repo"]`). The platform's
        # own self-configuration surface is exempt (sortie 08 DD7): its four
        # tools follow only the Self-configuration tab's switch, so a stored
        # withhold never applies. Keyed on the tool's `is_platform_surface`
        # (the source marker), never the name prefix; a tool without the
        # attribute (an injected stub) is still filtered.
        if built_mcp_tools is not None:
            for tool in built_mcp_tools:
                if getattr(tool, "is_platform_surface", False) or (
                    tool.name not in disabled_names and config.is_tool_enabled(tool.name)
                ):
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

        # Mission 33 F2 L3 (DD1): the routine tools, only while the agent's Routines item is
        # on; outside the `disabled_names` filter like the notes tools (the item is their
        # only control). The tool also checks the switch at call time (a cached Agent).
        routine_tools: list[Tool] = []
        if self.routines_provider is not None:
            routine_tools = await self.routines_provider.get_tools_for_agent(
                config, agent_name=name
            )
            for tool in routine_tools:
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
        # search-discovered (not chain-critical) and is NOT seeded here for an agent
        # that is not exposed; an exposed agent (sortie 11 DD1, below) gets it with the
        # pair when connector-bound, like every other enabled tool.
        #
        # Flight 2 leg 1c (DD7): the connector pair is seeded only for an
        # agent some connector's binding names (default_agent or a
        # channel_map value). Others still find the pair through
        # `search_tools`. An agent mapped after its web session started sees
        # the pair seeded on rejoin (accepted staleness). `current_time`
        # stays seeded for everyone.
        from the_one.db.repositories import agent_names_in_use

        try:
            # A connector cannot bind GleepGlorp (M36 F1 L02), so it never gets the pair.
            connector_bound = not gleepglorp and config.name in await agent_names_in_use(conn)
        except (sqlite3.Error, ValueError):  # fail open to the pre-DD7 behaviour (seed the pair)
            logger.warning("Could not read connector bindings; seeding the pair", exc_info=True)
            connector_bound = True
        seed_names = [CURRENT_TIME_TOOL_NAME]
        if connector_bound:
            seed_names = [
                SEND_TO_PLATFORM_CHANNEL_TOOL_NAME,
                FIND_PLATFORM_DESTINATION_TOOL_NAME,
                CURRENT_TIME_TOOL_NAME,
            ]
        for seed_tool_name in seed_names:
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

        # Mission 33 F2 L3 (DD1): seed the routine tools the same way.
        for routine_tool in routine_tools:
            loaded_schemas.append(routine_tool.to_schema())
            loaded_tool_names.add(routine_tool.name)

        # Sortie 11 DD1/DD2: tool exposure. One bounded provider-metadata lookup, run
        # beside the `supports_tools` probe so an unresponsive provider costs one bound.
        _, tool_available = await asyncio.gather(
            _lookup_context_window(llm), time_tool_available(registry, llm)
        )
        window_known = getattr(llm, "context_window_known", False) is True
        window = getattr(llm, "max_context_tokens", None) if window_known else None
        # `fetch_channel_history` joins the connector pair for a bound agent (DD1).
        unbound_excluded = (
            set()
            if connector_bound
            else {
                SEND_TO_PLATFORM_CHANNEL_TOOL_NAME,
                FIND_PLATFORM_DESTINATION_TOOL_NAME,
                FETCH_CHANNEL_HISTORY_TOOL_NAME,
            }
        )
        exposure_names = [
            n
            for n in registry.tool_names
            if n != SEARCH_TOOLS_SCHEMA["name"]
            and n not in loaded_tool_names
            and n not in unbound_excluded
        ]
        exposure_schemas = [registry.get(n).to_schema() for n in exposure_names]
        tool_exposure, to_append = decide_exposure(
            window_known=window_known,
            window=window,
            bytes_per_token=getattr(llm, "bytes_per_token", 4.0),
            starting=[SEARCH_TOOLS_SCHEMA, CONTINUE_SCHEMA] + loaded_schemas,
            candidates=exposure_schemas,
        )
        if tool_exposure.decided:
            loaded_schemas.extend(to_append)
            loaded_tool_names.update(exposure_names)
        if gleepglorp:
            # DD1: every tool GleepGlorp has is in its starting set whatever the exposure
            # decision (`current_time` is seeded above; this seeds `read_app_config`).
            for n in registry.tool_names:
                if n != SEARCH_TOOLS_SCHEMA["name"] and n not in loaded_tool_names:
                    loaded_schemas.append(registry.get(n).to_schema())
                    loaded_tool_names.add(n)

        # 3. Resolve system prompt
        if gleepglorp:
            from the_one.gleepglorp.prompt import build_prompts as _gg_prompts

            prompts = await _gg_prompts(conn, tool_available=tool_available)
        else:
            caps = capabilities_from_registry(
                registry,
                notes=bool(notes_tools),
                rules=True,
                time_tool=tool_available,
                tools_preloaded=tool_exposure.decided,
                visuals=config.rich_visuals,
            )
            prompts = await build_system_prompts(
                config.name,
                config.system_prompt,
                conn=conn,
                tool_available=tool_available,
                knowledge=caps.knowledge,
                time_tool=caps.time_tool,
                exec_tools=caps.exec_tools,
                tools_preloaded=caps.tools_preloaded,
                visuals=caps.visuals,
            )

        # 4. Create agent
        # F10 L1: pass the shared containers so the Agent's
        # _compute_visible_schemas() picks up mutations from stub search calls.
        agent = Agent(
            llm=llm,
            tools=registry,
            system_prompt=prompts.tool_capable,
            degraded_system_prompt=prompts.tool_free,
            max_iterations=config.max_iterations,
            loaded_schemas=loaded_schemas,
            loaded_tool_names=loaded_tool_names,
            # Sortie 10 DD7: every factory-built agent gets a resolver, grants or not.
            secrets=SecretResolver(config.name),
        )
        agent.tool_exposure = tool_exposure  # type: ignore[attr-defined]
        agent.rich_visuals = config.rich_visuals  # type: ignore[attr-defined]
        # Mission 27 F2 (DD5/DD6): each notes tool reads its owning Agent's
        # messages at execute time to compute the untrusted flag. Bound after
        # construction (the Agent does not exist while tools are built).
        for notes_tool in notes_tools:
            notes_tool.bind_agent(agent)  # type: ignore[attr-defined]
        for routine_tool in routine_tools:
            routine_tool.bind_agent(agent)  # type: ignore[attr-defined]
        if gleepglorp:
            propose_tool.bind_agent(agent)
        return agent

    async def list_agents(self) -> list[str]:
        """List the stored agent names (GleepGlorp is not an agent)."""
        if self.store is None:
            return []
        return sorted(await self.store.list_agents())

    async def _load_config(self, name: str) -> AgentConfig:
        """Load a stored agent's config; an unknown name is an error."""
        if self.store is not None and await self.store.exists(name):
            return await self.store.load(name)
        raise AgentNotFoundError(f"Unknown agent: {name}")
