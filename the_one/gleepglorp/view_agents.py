"""The ``agents`` and ``routines`` views (split out of ``views.py``, squawk 0386)."""

from __future__ import annotations

from typing import Any

from the_one.gleepglorp.view_core import (
    _MAX_LIST_NAMES,
    Ctx,
    PlainMessage,
    _agent_names,
    _emit,
    _list_or_detail,
    _names,
    _no_such,
    _scalar_name,
    _surface_owners,
    cut,
)


async def agents_view(ctx: Ctx, name: str | None = None) -> Any:
    from the_one.db.repositories import (
        AgentNoteRepository,
        AgentRuleRepository,
        SQLiteAgentStore,
    )
    from the_one.routines.repository import AgentRoutineRepository

    conn = ctx.conn
    store = SQLiteAgentStore(conn, ctx.enc)
    entries = [(n, n) for n in await _agent_names(conn)]

    async def summarize(key: str, item_name: str) -> str:
        cfg = await store.load(key)
        return cut(cfg.description, 100) or f"model {cfg.llm_model or 'not set'}"

    async def detail(key: str, item_name: str) -> dict[str, Any]:
        cfg = await store.load(key)
        mcp_names = {i: n for i, n in await _names(conn, "mcp_sources")}
        kb_names = {i: n for i, n in await _names(conn, "knowledge_bases")}
        owners = await _surface_owners(conn)
        rules = await AgentRuleRepository(conn).list_for_agent(key)
        routines = await AgentRoutineRepository(conn).list_for_agent(key)
        return {
            "name": cfg.name,
            "description": cfg.description,
            "system_prompt": cfg.system_prompt,
            "model": cfg.llm_model or None,
            "provider": await _scalar_name(conn, "llm_providers", cfg.provider_config_id),
            "enabled_tools": "all" if cfg.enabled_tools is None else list(cfg.enabled_tools),
            "disabled_tools": list(cfg.disabled_tools),
            "tools_with_overrides": sorted(cfg.tool_overrides or {}),
            "rules": [{"text": r.text, "enabled": r.enabled} for r in rules],
            "mcp_servers": [mcp_names[i] for i in cfg.mcp_source_ids if i in mcp_names],
            "knowledge_bases": [kb_names[i] for i in cfg.kb_ids if i in kb_names],
            "routines_count": len(routines),
            "notes_count": await AgentNoteRepository(conn).count_for_agent(key),
            "rich_visuals": cfg.rich_visuals,
            "self_configuration": any(
                owner == key and sid in cfg.mcp_source_ids for sid, owner in owners.items()
            ),
        }

    return await _list_or_detail("agents", entries, summarize, detail, name)


async def routines_view(ctx: Ctx, name: str | None = None) -> Any:
    from the_one import time_zones
    from the_one.routines import describe
    from the_one.routines.repository import AgentRoutineRepository

    agents = await _agent_names(ctx.conn)
    if name is None:
        raise PlainMessage(
            "routines needs an agent name. Valid names: "
            + (", ".join(agents[:_MAX_LIST_NAMES]) if agents else "(none)")
        )
    if name not in agents:
        raise _no_such("routines", name, agents)
    zone = (await time_zones.load_effective_zone(ctx.conn)).tzinfo
    out = []
    for r in await AgentRoutineRepository(ctx.conn).list_for_agent(name):
        out.append(
            {
                "name": r.name,
                "schedule": describe.schedule_sentence(r.schedule, r.anchor_at, zone),
                "next_run": describe.describe_next(r.next_run_at, zone),
                "prompt": r.prompt,
                "enabled": r.enabled,
            }
        )
    return _emit("routines", "detail", {"agent": name, "routines": out})
