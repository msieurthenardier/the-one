"""The ``overview`` and ``settings`` views (split out of ``views.py``, squawk 0386)."""

from __future__ import annotations

from typing import Any

from the_one.gleepglorp.view_core import (
    _MAX_LIST_NAMES,
    Ctx,
    _agent_names,
    _emit,
    _names,
    _scalar_name,
    _surface_owners,
)


async def overview_view(ctx: Ctx, name: str | None = None) -> dict[str, Any]:
    from the_one import gleepglorp, time_zones
    from the_one.tools.builtins import _TOOL_CLASSES

    conn = ctx.conn
    gg = await gleepglorp.load_settings(conn)
    state = await gleepglorp.state(conn, gg)
    eff = await time_zones.load_effective_zone(conn)
    surface_ids = set(await _surface_owners(conn))
    names: dict[str, list[str]] = {
        "agents": await _agent_names(conn),
        "mcp_servers": [n for i, n in await _names(conn, "mcp_sources") if i not in surface_ids],
        "providers": [n for _, n in await _names(conn, "llm_providers")],
        "knowledge_bases": [n for _, n in await _names(conn, "knowledge_bases")],
        "connectors": [n for _, n in await _names(conn, "connectors")],
        "secrets": [n for _, n in await _names(conn, "secrets")],
    }
    counts = {k: len(v) for k, v in names.items()}
    counts["built_in_tools"] = len(_TOOL_CLASSES)
    return _emit(
        "overview",
        "detail",
        {
            "gleepglorp": {
                "state": state,
                "model": gg.model,
                "provider": await _scalar_name(conn, "llm_providers", gg.provider_config_id),
                "web_access": gg.web_access,
                "memory": gg.memory,
            },
            "time_zone": eff.key or "system default",
            "counts": counts,
            "names": {k: v[:_MAX_LIST_NAMES] for k, v in names.items()},
        },
    )


async def settings_view(ctx: Ctx, name: str | None = None) -> dict[str, Any]:
    from the_one import time_zones
    from the_one.knowledge.settings import load_knowledge_settings

    setting = await time_zones.load_setting(ctx.conn)
    eff = await time_zones.load_effective_zone(ctx.conn)
    ks = await load_knowledge_settings(ctx.conn)
    return _emit(
        "settings",
        "detail",
        {
            "time_zone": {"mode": setting.mode, "zone": setting.zone, "effective": eff.key},
            "knowledge_indexing": {
                "chunking": {
                    "size_chars": ks.chunking.size_chars,
                    "overlap_chars": ks.chunking.overlap_chars,
                },
                "monitoring": {
                    "watch_enabled": ks.monitoring.watch_enabled,
                    "reconcile_interval_seconds": ks.monitoring.reconcile_interval_seconds,
                },
                "embedding": {
                    "backend": ks.embedding.backend,
                    "model_id": ks.embedding.model_id,
                    "dim": ks.embedding.dim,
                },
            },
        },
    )
