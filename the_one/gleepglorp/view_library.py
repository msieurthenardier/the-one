"""The Library views: providers, knowledge bases, connectors, secrets and built-in tools
(split out of ``views.py``, squawk 0386)."""

from __future__ import annotations

import json
import re
from typing import Any

from the_one.gleepglorp.view_core import (
    UNREADABLE,
    Ctx,
    PlainMessage,
    _list_or_detail,
    _names,
    _secret_field_names,
    cut,
    scrub_url,
)


async def providers_view(ctx: Ctx, name: str | None = None) -> Any:
    from the_one import gleepglorp
    from the_one.db.repositories import LLMProviderRepository, SQLiteAgentStore

    conn = ctx.conn
    repo = LLMProviderRepository(conn, ctx.enc)
    store = SQLiteAgentStore(conn, ctx.enc)
    entries = await _names(conn, "llm_providers")

    async def summarize(key: str, item_name: str) -> str:
        p = await repo.get(key)
        return p.type

    async def detail(key: str, item_name: str) -> dict[str, Any]:
        p = await repo.get(key)
        gg = await gleepglorp.load_settings(conn)
        sec = p.secrets or {}
        return {
            "name": p.name,
            "type": p.type,
            # Scheme, host and port only: a key in the path or query never shows.
            "address": scrub_url(p.base_url, keep_path=False),
            "oauth_active": p.type == "anthropic-plan"
            and bool(sec.get("access_token") and sec.get("refresh_token")),
            "agents": await store.list_by_provider(p.id),
            "used_by_gleepglorp": gg.provider_config_id == p.id,
        }

    return await _list_or_detail(
        "providers", entries, summarize, detail, name, id_of=lambda key: key
    )


async def knowledge_bases_view(ctx: Ctx, name: str | None = None) -> Any:
    from the_one.db.repositories import KBItemRepository, KnowledgeBaseRepository, SQLiteAgentStore
    from the_one.knowledge.manager import get_manager

    conn = ctx.conn
    kbs = KnowledgeBaseRepository(conn)
    items = KBItemRepository(conn)
    store = SQLiteAgentStore(conn, ctx.enc)
    entries = await _names(conn, "knowledge_bases")

    async def summarize(key: str, item_name: str) -> str:
        counts = await items.count_by_status(key, type="file")
        return f"{counts.get('indexed', 0)} of {sum(counts.values())} files indexed"

    async def detail(key: str, item_name: str) -> dict[str, Any]:
        kb = await kbs.get(key)
        manager = get_manager()
        return {
            "name": kb.name,
            "description": kb.description,
            "folders": [f.path_or_url for f in await items.list_folders(key)],
            "items": await items.count_by_status(key, type="file"),
            "latest_indexed": await items.latest_indexed_at(key, type="file"),
            "indexer": manager.state(key) if manager is not None else "idle",
            "agents": await store.list_by_kb(key),
        }

    return await _list_or_detail("knowledge_bases", entries, summarize, detail, name)


async def connectors_view(ctx: Ctx, name: str | None = None) -> Any:
    """Plain columns only: a connector's ``secrets`` column is never selected."""
    conn = ctx.conn
    async with conn.execute("SELECT id, name, type, config FROM connectors ORDER BY name") as cur:
        rows = {r[0]: (r[1], r[2], r[3]) for r in await cur.fetchall()}
    entries = [(i, v[0]) for i, v in rows.items()]

    def parse(key: str) -> tuple[str, dict[str, Any]]:
        _, ctype, raw = rows[key]
        cfg = json.loads(raw or "{}")
        return ctype, cfg if isinstance(cfg, dict) else {}

    async def summarize(key: str, item_name: str) -> str:
        ctype, cfg = parse(key)
        return f"{ctype}, {'enabled' if cfg.get('enabled', True) is True else 'disabled'}"

    async def detail(key: str, item_name: str) -> dict[str, Any]:
        ctype, cfg = parse(key)
        cmap = cfg.get("channel_map")
        default = cfg.get("default_agent")
        return {
            "name": item_name,
            "type": ctype,
            "enabled": cfg.get("enabled", True) is True,
            "default_agent": default if isinstance(default, str) else None,
            "channel_bindings": [
                {"channel": str(c), "agent": a}
                for c, a in (cmap.items() if isinstance(cmap, dict) else [])
                if isinstance(a, str)
            ],
        }

    return await _list_or_detail("connectors", entries, summarize, detail, name)


async def secrets_view(ctx: Ctx, name: str | None = None) -> Any:
    """Names, descriptions, key names, allowed tools and grants. Never a value: the
    repository's ``list``/``get`` do not decrypt, and no value method is called."""
    from the_one.db.repositories import SecretRepository, SQLiteAgentStore

    repo = SecretRepository(ctx.conn, ctx.enc)
    store = SQLiteAgentStore(ctx.conn, ctx.enc)
    entries = await _names(ctx.conn, "secrets")

    async def summarize(key: str, item_name: str) -> str:
        s = await repo.get(key)
        if s is None:
            return UNREADABLE
        return cut(s.description, 100) or f"{len(s.values)} key(s)"

    async def detail(key: str, item_name: str) -> dict[str, Any]:
        s = await repo.get(key)
        if s is None:
            raise PlainMessage(f"{item_name}: {UNREADABLE}")
        return {
            "name": s.name,
            "description": s.description,
            "keys": [v.key for v in s.values],
            "allowed_tools": list(s.allowed_tools),
            "agents": await store.list_by_secret(s.id),
        }

    return await _list_or_detail("secrets", entries, summarize, detail, name)


_URL_LIKE = re.compile(r"^\s*[A-Za-z][A-Za-z0-9+.-]*://")


def _scrub_if_url(value: Any) -> Any:
    """A URL-valued setting without user info, query or fragment; anything else as is."""
    if isinstance(value, str) and _URL_LIKE.match(value):
        return scrub_url(value, keep_path=True)
    return value


async def built_in_tools_view(ctx: Ctx, name: str | None = None) -> Any:
    """The stored ``config`` column only (plain JSON) and ``enabled``; the ``secrets``
    column is never selected. Only the tool's own non-secret Config fields are shown."""
    from the_one.tools.builtins import _TOOL_CLASSES

    async with ctx.conn.execute("SELECT name, config, enabled FROM tool_configs") as cur:
        rows = {r[0]: (r[1], r[2]) for r in await cur.fetchall()}
    entries = [(n, n) for n in sorted(_TOOL_CLASSES)]

    def enabled_of(key: str) -> bool:
        row = rows.get(key)
        return bool(row[1]) if row is not None and row[1] is not None else True

    async def summarize(key: str, item_name: str) -> str:
        return f"{'on' if enabled_of(key) else 'off'}: {_TOOL_CLASSES[key].summary}"

    async def detail(key: str, item_name: str) -> dict[str, Any]:
        cls = _TOOL_CLASSES[key]
        stored: dict[str, Any] = {}
        if key in rows and rows[key][0]:
            parsed = json.loads(rows[key][0])
            stored = parsed if isinstance(parsed, dict) else {}
        config_cls = getattr(cls, "Config", None)
        fields = set(getattr(config_cls, "model_fields", {}))
        secret = _secret_field_names(config_cls) if config_cls is not None else set()
        return {
            "name": key,
            "enabled": enabled_of(key),
            "summary": cls.summary,
            "settings": {
                k: _scrub_if_url(v) for k, v in stored.items() if k in fields and k not in secret
            },
        }

    return await _list_or_detail("built_in_tools", entries, summarize, detail, name)
