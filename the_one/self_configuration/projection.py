"""The two read projections — LD5's explicit field lists, verbatim.

Pure functions over repositories: neither builds an ``Agent`` (building one
from inside that agent's own tool call would recurse into the surface — see
LD5). Both are unit-tested in isolation, and both are the site the AC6/AC7
"secret-free" regression net exercises: assert the *serialized result text*
never contains a seeded secret value, mirroring
``test_list_returns_masked_secrets``.
"""

from __future__ import annotations

from typing import Any

from the_one.agent.config import AgentConfig
from the_one.db.repositories import (
    KnowledgeBaseRepository,
    LLMProviderRepository,
    MCPSourceRepository,
    ToolConfigRepository,
)
from the_one.mcp._tool_provider import filter_mcp_tools_by_override
from the_one.mcp.types import MCPTool
from the_one.self_configuration.constants import override_for
from the_one.tools.builtins import BuiltinToolProvider


async def build_get_my_configuration(
    config: AgentConfig,
    *,
    provider_repo: LLMProviderRepository,
    kb_repo: KnowledgeBaseRepository,
) -> dict[str, Any]:
    """LD5's ``get_my_configuration`` projection.

    Exactly: ``name``, ``description``, ``system_prompt``, ``llm_model``,
    ``provider`` (``{name, type}`` — never the id, api_key, base_url, or
    secrets), ``max_iterations``, ``chat_history_retention_days``,
    ``enabled_tools``, ``disabled_tools``, ``knowledge_bases`` (names).
    Never touches ``tool_overrides``, ``mcp_overrides``, ``provider_config_id``,
    ``kb_ids``, or ``mcp_source_ids``.

    Edge case: no provider configured → ``provider: None`` (a provider is a
    chat concern, not a self-configuration-surface gate).
    """
    provider: dict[str, str] | None = None
    if config.provider_config_id:
        try:
            row = await provider_repo.get(config.provider_config_id)
        except KeyError:
            provider = None
        else:
            provider = {"name": row.name, "type": row.type}

    knowledge_bases: list[str] = []
    for kb_id in config.kb_ids:
        try:
            kb = await kb_repo.get(kb_id)
        except KeyError:
            continue
        knowledge_bases.append(kb.name)

    return {
        "name": config.name,
        "description": config.description,
        "system_prompt": config.system_prompt,
        "llm_model": config.llm_model,
        "provider": provider,
        "max_iterations": config.max_iterations,
        "chat_history_retention_days": config.chat_history_retention_days,
        "enabled_tools": config.enabled_tools,
        "disabled_tools": config.disabled_tools,
        "knowledge_bases": knowledge_bases,
    }


def _builtin_tools_for_agent(
    config: AgentConfig,
    tool_configs: list[Any],
) -> list[dict[str, str]]:
    """The same two predicates ``AgentFactory.create`` uses (operator
    ``ToolConfig.enabled`` and ``AgentConfig.is_tool_enabled``) — applied to
    :class:`BuiltinToolProvider`'s introspection output directly rather than
    building an ``Agent``."""
    tool_configs_by_name = {c.name: c.merged_config() for c in tool_configs}
    disabled_names = {c.name for c in tool_configs if not c.enabled}
    agent_overrides = config.tool_overrides or {}
    provider = BuiltinToolProvider()
    tools = provider.get_tools(
        tool_configs_by_name,
        agent_overrides,
        agent_name=config.name,
    )
    return [
        {"name": t.name, "description": t.description}
        for t in tools
        if t.name not in disabled_names and config.is_tool_enabled(t.name)
    ]


async def build_describe_my_capabilities(
    config: AgentConfig,
    *,
    tool_config_repo: ToolConfigRepository,
    mcp_repo: MCPSourceRepository,
) -> dict[str, Any]:
    """LD5's ``describe_my_capabilities`` projection.

    ``builtin_tools`` (name + description, filtered by the operator +
    per-agent predicates) and ``mcp_sources`` (name, type, and tool names
    from ``config._cache.tools`` run through
    :func:`filter_mcp_tools_by_override` — never bypassed). No source
    config, URL, header, or secret ever appears here.

    Mission 23 Flight 1 (backend-removal leg, DD-5): the payload no longer
    carries a ``connectors`` key — the connector subsystem (and this
    projection's ``ConnectorRepository`` dependency) is gone. A future
    flight may re-add a minimal field over the kept ``connectors`` table.

    The self-configuration surface itself is listed among ``mcp_sources``
    with no special-casing: once enabled, its row is an ordinary entry in
    ``config.mcp_source_ids`` like any other MCP source (flight open
    question, resolved: visible, not writable — the write allowlist is the
    tool catalog's shape).

    Edge case: a source whose ``_cache.tools`` is empty/unpopulated is
    reported with ``tools: [], tools_known: False`` — never connected to
    from this read path.
    """
    tool_configs = await tool_config_repo.list()
    builtin_tools = _builtin_tools_for_agent(config, tool_configs)

    mcp_sources: list[dict[str, Any]] = []
    for source_id in config.mcp_source_ids:
        try:
            source = await mcp_repo.get(source_id)
        except KeyError:
            continue
        # Sortie 09 DD4: an agent that uses its own credentials on this source is
        # described from its per-agent cache (read-only here: a cold row reports
        # `tools_known: False` and never connects). The table is reached through the
        # source repository's own connection.
        from the_one.mcp._agent_cache import per_agent_tools

        per_agent, per_agent_payload, _ = await per_agent_tools(
            mcp_repo.conn, config.name, config.mcp_overrides, source
        )
        if per_agent:
            cached = per_agent_payload
        else:
            cached = ((source.config or {}).get("_cache") or {}).get("tools")
        if not cached:
            mcp_sources.append(
                {"name": source.name, "type": source.type, "tools": [], "tools_known": False}
            )
            continue
        mcp_tools = [
            MCPTool(
                name=t["name"],
                description=t.get("description", ""),
                input_schema=t.get("input_schema", {"type": "object", "properties": {}}),
                output_schema=None,
                annotations=None,
            )
            for t in cached
        ]
        override_payload = override_for(config.mcp_overrides, source)
        filtered = filter_mcp_tools_by_override(mcp_tools, source, override_payload)
        mcp_sources.append(
            {
                "name": source.name,
                "type": source.type,
                "tools": [t.name for t in filtered],
                "tools_known": True,
            }
        )

    return {
        "builtin_tools": builtin_tools,
        "mcp_sources": mcp_sources,
    }
