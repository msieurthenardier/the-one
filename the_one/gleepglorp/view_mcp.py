"""The ``mcp_servers`` view (split out of ``views.py``, squawk 0386)."""

from __future__ import annotations

from typing import Any

from the_one.gleepglorp.view_core import (
    _DESC_CUT,
    _MAX_ARGS,
    _MAX_MCP_TOOLS,
    SURFACE_SUMMARY,
    Ctx,
    _iso,
    _list_or_detail,
    _names,
    _surface_owners,
    cut,
    scrub_url,
)


def _mcp_connection(cfg: dict[str, Any]) -> dict[str, Any]:
    cache = cfg.get("_cache")
    cache = cache if isinstance(cache, dict) else {}
    last = cache.get("last_check")
    last = last if isinstance(last, dict) else None
    if last is not None and isinstance(last.get("status"), str):
        status, at = cut(last["status"], 30), _iso(last.get("at"))
    elif cache.get("last_updated") is not None:
        status, at = "tools listed", _iso(cache.get("last_updated"))
    else:
        status, at = "not checked yet", None

    def word(key: str) -> str | None:
        v = cache.get(key)
        return cut(v, 40) if isinstance(v, str) and v else None

    return {
        "status": status,
        "checked_at": at,
        "protocol_version": word("protocol_version"),
        "auth_posture": word("auth_posture"),
        "protocol_fallback": word("protocol_fallback"),
    }


def _mcp_tools(cfg: dict[str, Any]) -> tuple[int, list[dict[str, str]]]:
    cache = cfg.get("_cache")
    tools = cache.get("tools") if isinstance(cache, dict) else None
    if not isinstance(tools, list):
        return 0, []
    out = []
    for t in tools[:_MAX_MCP_TOOLS]:
        if isinstance(t, dict) and isinstance(t.get("name"), str):
            out.append(
                {"name": cut(t["name"], 100), "description": cut(t.get("description"), _DESC_CUT)}
            )
    return len(tools), out


async def mcp_servers_view(ctx: Ctx, name: str | None = None) -> Any:
    from the_one.db.repositories import MCPSourceRepository, SQLiteAgentStore
    from the_one.mcp.oauth.storage import OAUTH_MANAGED_SECRET_KEYS
    from the_one.self_configuration.constants import SURFACE_ROW_NAME

    conn = ctx.conn
    repo = MCPSourceRepository(conn, ctx.enc)
    store = SQLiteAgentStore(conn, ctx.enc)
    surface_ids = set(await _surface_owners(conn))
    entries: list[tuple[Any, str]] = [
        (i, n) for i, n in await _names(conn, "mcp_sources") if i not in surface_ids
    ]
    # One synthetic entry stands for every agent's self-configuration surface row.
    entries.append((None, SURFACE_ROW_NAME))
    entries.sort(key=lambda e: e[1].lower())

    async def summarize(key: Any, item_name: str) -> str:
        if key is None:
            return SURFACE_SUMMARY
        src = await repo.get(key)
        conn_state = _mcp_connection(src.config or {})["status"]
        return f"{src.type}, {conn_state}"

    async def detail(key: Any, item_name: str) -> dict[str, Any]:
        if key is None:
            attached: list[str] = []
            for sid in surface_ids:
                attached += await store.list_by_mcp_source(sid)
            return {
                "name": SURFACE_ROW_NAME,
                "type": SURFACE_SUMMARY,
                "agents": sorted(set(attached)),
            }
        src = await repo.get(key)
        cfg = src.config or {}
        secret_names = [k for k in src.secrets if k not in OAUTH_MANAGED_SECRET_KEYS]
        out: dict[str, Any] = {"name": src.name, "type": src.type}
        if src.type == "stdio":
            args = cfg.get("args")
            env = cfg.get("env")
            out["command"] = cut(cfg.get("command"), 500)
            out["args"] = [cut(a, 500) for a in (args if isinstance(args, list) else [])][
                :_MAX_ARGS
            ]
            out["working_directory"] = cfg.get("cwd") if isinstance(cfg.get("cwd"), str) else None
            out["env_names"] = sorted(
                {
                    *(k for k in (env if isinstance(env, dict) else {}) if isinstance(k, str)),
                    *secret_names,
                }
            )
        else:
            headers = cfg.get("headers")
            out["address"] = scrub_url(cfg.get("url"), keep_path=True)
            out["header_names"] = sorted(
                {
                    *(
                        k
                        for k in (headers if isinstance(headers, dict) else {})
                        if isinstance(k, str)
                    ),
                    *secret_names,
                }
            )
            # Signed in iff any OAuth-managed key is stored (the MCP rule); only the
            # boolean leaves this function.
            out["signed_in"] = any(k in src.secrets for k in OAUTH_MANAGED_SECRET_KEYS)
        total, tools = _mcp_tools(cfg)
        out["connection"] = _mcp_connection(cfg)
        out["tool_count"] = total
        out["tools"] = tools
        out["agents"] = await store.list_by_mcp_source(src.id)
        return out

    return await _list_or_detail("mcp_servers", entries, summarize, detail, name)
