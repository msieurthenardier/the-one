"""Whitelist views of the app's configuration for GleepGlorp (M36 F1 L05, DD5 as amended).

GleepGlorp reads the app through these views and nothing else. Each view builds its
output **field by field** from repositories and models, so a field is shown only if a
view lists it; the API's response helpers are not used (they pass several
secret-bearing fields through: MCP ``config.env``/``config.headers`` values, an agent's
``tool_overrides``, a provider's free-form ``config`` and secret tails).

The repositories decrypt on load, so plaintext secrets are in memory while a view runs.
The rule is **never emit**: every emitted dict goes through :func:`_emit`, which refuses, at
runtime, a top-level key (``list`` or ``detail`` level) that is not in the kind's declared
``ALLOWED`` constant; the ``nested`` keys are enforced by the test (``check_output_keys`` in
``tests/test_gleepglorp_views.py``), not at runtime. The secret parity test seeds a distinct
value in every secret slot and asserts none reaches the output. A view never writes, never
fetches, never reads a chat, a file or a log.

Documented residuals (``SECURITY-MODEL.md`` "GleepGlorp's read surface"): a token placed
in an MCP command argument, in an MCP address path, or in free text such as a system
prompt, description, rule or routine prompt is shown as written.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

UNREADABLE = "unreadable (the encryption key changed)"

KINDS: tuple[str, ...] = (
    "overview",
    "agents",
    "mcp_servers",
    "providers",
    "knowledge_bases",
    "connectors",
    "routines",
    "secrets",
    "built_in_tools",
    "settings",
)

# A list is capped so a very large configuration stays short; details are whole.
_MAX_LIST_NAMES = 100
_MAX_MCP_TOOLS = 50
_MAX_ARGS = 50
_DESC_CUT = 200

# --- the declared output keys, per kind -------------------------------------------
# ``list``: keys of one list entry. ``detail``: keys of a detail dict. ``nested``: keys
# of dicts inside a detail. A key not listed here can never be emitted (``_emit``).

_LIST_KEYS = frozenset({"name", "summary"})

ALLOWED: dict[str, dict[str, frozenset[str]]] = {
    "overview": {
        "list": frozenset(),
        "detail": frozenset({"gleepglorp", "time_zone", "counts", "names"}),
        "nested": frozenset(
            {"state", "model", "provider", "web_access", "memory"}
            | set(KINDS)
            | {"agents", "mcp_servers", "providers", "knowledge_bases", "connectors", "secrets"}
        ),
    },
    "agents": {
        "list": _LIST_KEYS,
        "detail": frozenset(
            {
                "name",
                "description",
                "system_prompt",
                "model",
                "provider",
                "enabled_tools",
                "disabled_tools",
                "tools_with_overrides",
                "rules",
                "mcp_servers",
                "knowledge_bases",
                "routines_count",
                "notes_count",
                "rich_visuals",
                "self_configuration",
            }
        ),
        "nested": frozenset({"text", "enabled"}),
    },
    "mcp_servers": {
        "list": _LIST_KEYS,
        "detail": frozenset(
            {
                "name",
                "type",
                "command",
                "args",
                "working_directory",
                "address",
                "header_names",
                "env_names",
                "connection",
                "tool_count",
                "tools",
                "signed_in",
                "agents",
            }
        ),
        "nested": frozenset(
            {
                "status",
                "checked_at",
                "protocol_version",
                "auth_posture",
                "protocol_fallback",
                "name",
                "description",
            }
        ),
    },
    "providers": {
        "list": _LIST_KEYS,
        "detail": frozenset(
            {"name", "type", "address", "oauth_active", "agents", "used_by_gleepglorp"}
        ),
        "nested": frozenset(),
    },
    "knowledge_bases": {
        "list": _LIST_KEYS,
        "detail": frozenset(
            {"name", "description", "folders", "items", "latest_indexed", "indexer", "agents"}
        ),
        "nested": frozenset({"pending", "indexing", "indexed", "failed"}),
    },
    "connectors": {
        "list": _LIST_KEYS,
        "detail": frozenset({"name", "type", "enabled", "default_agent", "channel_bindings"}),
        "nested": frozenset({"channel", "agent"}),
    },
    "routines": {
        "list": frozenset(),
        "detail": frozenset({"agent", "routines"}),
        "nested": frozenset({"name", "schedule", "next_run", "prompt", "enabled"}),
    },
    "secrets": {
        "list": _LIST_KEYS,
        "detail": frozenset({"name", "description", "keys", "allowed_tools", "agents"}),
        "nested": frozenset(),
    },
    "built_in_tools": {
        "list": _LIST_KEYS,
        "detail": frozenset({"name", "enabled", "summary", "settings"}),
        # A tool's settings keys are its own non-secret Config field names.
        "nested": frozenset(),
    },
    "settings": {
        "list": frozenset(),
        "detail": frozenset({"time_zone", "knowledge_indexing"}),
        "nested": frozenset(
            {
                "mode",
                "zone",
                "effective",
                "chunking",
                "monitoring",
                "embedding",
                "size_chars",
                "overlap_chars",
                "watch_enabled",
                "reconcile_interval_seconds",
                "backend",
                "model_id",
                "dim",
            }
        ),
    },
}

# Kinds whose output is a list of ``{name, summary}`` without a name, a detail with one.
LIST_KINDS = frozenset(
    {
        "agents",
        "mcp_servers",
        "providers",
        "knowledge_bases",
        "connectors",
        "secrets",
        "built_in_tools",
    }
)

_SINGULAR = {
    "agents": "agent",
    "mcp_servers": "MCP server",
    "providers": "model provider",
    "knowledge_bases": "knowledge base",
    "connectors": "connector",
    "secrets": "secret",
    "built_in_tools": "built-in tool",
    "routines": "agent",
}

SURFACE_SUMMARY = (
    "Self-configuration (built in, controlled from the agent's Self-configuration tab)"
)


class PlainMessage(Exception):  # noqa: N818 - a reply, not an error
    """A plain-words reply for the model (an unknown name, an unreadable item)."""


class UndeclaredKeyError(RuntimeError):
    """A view tried to emit a key its kind's constant does not list (a bug, never shown)."""


@dataclass
class Ctx:
    conn: Any
    enc: Any


def _emit(kind: str, level: str, data: dict[str, Any]) -> dict[str, Any]:
    """Return ``data`` after checking its keys against the kind's declared constant."""
    extra = set(data) - ALLOWED[kind][level]
    if extra:
        raise UndeclaredKeyError(f"view {kind!r} tried to emit undeclared keys {sorted(extra)}")
    return data


def cut(text: Any, n: int) -> str:
    s = text if isinstance(text, str) else ""
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def scrub_url(url: Any, *, keep_path: bool) -> str | None:
    """``scheme://host[:port][/path]`` with user info, query and fragment dropped.

    ``None`` when the value has no scheme and host (never echoed, so a malformed value
    holding a credential cannot be shown).
    """
    if not isinstance(url, str) or not url.strip():
        return None
    try:
        p = urlsplit(url.strip())
        host = p.hostname
        port = p.port
    except ValueError:
        return None
    if not p.scheme or not host:
        return None
    if ":" in host:
        host = f"[{host}]"
    out = f"{p.scheme}://{host}" + (f":{port}" if port else "")
    if keep_path and p.path:
        out += p.path
    return out


def _iso(ts: Any) -> str | None:
    if isinstance(ts, bool) or not isinstance(ts, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(ts, tz=UTC).isoformat(timespec="seconds")
    except (OverflowError, OSError, ValueError):
        return None


def _secret_field_names(config_cls: type) -> set[str]:
    """The names a tool Config marks ``secret: true`` (a neutral twin of the API's)."""
    names: set[str] = set()
    for field_name, info in getattr(config_cls, "model_fields", {}).items():
        extra = info.json_schema_extra or {}
        if isinstance(extra, dict) and extra.get("secret") is True:
            names.add(field_name)
    return names


async def _names(conn: Any, table: str) -> list[tuple[str, str]]:
    """``[(id, name)]`` from one of a fixed set of tables, by name."""
    if table not in {"llm_providers", "mcp_sources", "knowledge_bases", "secrets", "connectors"}:
        raise ValueError(table)
    async with conn.execute(
        f"SELECT id, name FROM {table} ORDER BY name COLLATE NOCASE, id"  # noqa: S608
    ) as cur:
        return [(r[0], r[1]) for r in await cur.fetchall()]


async def _scalar_name(conn: Any, table: str, row_id: str | None) -> str | None:
    if not row_id or table not in {"llm_providers", "mcp_sources", "knowledge_bases"}:
        return None
    async with conn.execute(f"SELECT name FROM {table} WHERE id = ?", (row_id,)) as cur:  # noqa: S608
        row = await cur.fetchone()
    return row[0] if row else None


async def _agent_names(conn: Any) -> list[str]:
    async with conn.execute("SELECT name FROM agents ORDER BY name COLLATE NOCASE") as cur:
        return [r[0] for r in await cur.fetchall()]


async def _surface_owners(conn: Any) -> dict[str, str]:
    """``{source_id: owning agent}`` for the self-configuration surface rows."""
    owners: dict[str, str] = {}
    async with conn.execute("SELECT id, config FROM mcp_sources") as cur:
        rows = await cur.fetchall()
    for row in rows:
        try:
            cfg = json.loads(row[1] or "{}")
        except ValueError:
            continue
        marker = cfg.get("self_configuration") if isinstance(cfg, dict) else None
        if isinstance(marker, dict) and isinstance(marker.get("agent"), str) and marker["agent"]:
            owners[row[0]] = marker["agent"]
    return owners


def _no_such(kind: str, name: str, valid: list[str]) -> PlainMessage:
    shown = ", ".join(valid[:_MAX_LIST_NAMES]) if valid else "(none)"
    more = f" (and {len(valid) - _MAX_LIST_NAMES} more)" if len(valid) > _MAX_LIST_NAMES else ""
    return PlainMessage(f"No {_SINGULAR[kind]} named {cut(name, 80)!r}. Valid names: {shown}{more}")


async def _list_or_detail(
    kind: str,
    entries: list[tuple[Any, str]],
    summarize: Callable[[Any, str], Awaitable[str]],
    detail: Callable[[Any, str], Awaitable[dict[str, Any]]],
    name: str | None,
) -> Any:
    if name is None:
        out = []
        for key, item_name in entries[:_MAX_LIST_NAMES]:
            try:
                summary = await summarize(key, item_name)
            except Exception:  # noqa: BLE001 - one bad row never fails the list
                logger.debug("read_app_config: %s %r unreadable", kind, item_name, exc_info=True)
                summary = UNREADABLE
            out.append(_emit(kind, "list", {"name": item_name, "summary": cut(summary, 160)}))
        if len(entries) > _MAX_LIST_NAMES:
            out.append(
                _emit(
                    kind,
                    "list",
                    {"name": "…", "summary": f"{len(entries) - _MAX_LIST_NAMES} more not shown"},
                )
            )
        return out
    for key, item_name in entries:
        if item_name == name:
            try:
                return _emit(kind, "detail", await detail(key, item_name))
            except (PlainMessage, UndeclaredKeyError):
                raise
            except Exception:  # noqa: BLE001
                logger.debug("read_app_config: %s %r unreadable", kind, name, exc_info=True)
                raise PlainMessage(f"{item_name}: {UNREADABLE}") from None
    raise _no_such(kind, name, [n for _, n in entries])


# --- overview -----------------------------------------------------------------------


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


# --- agents -------------------------------------------------------------------------


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


# --- MCP servers --------------------------------------------------------------------


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


# --- providers ----------------------------------------------------------------------


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

    return await _list_or_detail("providers", entries, summarize, detail, name)


# --- knowledge bases ----------------------------------------------------------------


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


# --- connectors ---------------------------------------------------------------------


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


# --- routines -----------------------------------------------------------------------


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


# --- secrets (Library) --------------------------------------------------------------


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


# --- built-in tools -----------------------------------------------------------------

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


# --- settings -----------------------------------------------------------------------


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


VIEWS: dict[str, Callable[..., Awaitable[Any]]] = {
    "overview": overview_view,
    "agents": agents_view,
    "mcp_servers": mcp_servers_view,
    "providers": providers_view,
    "knowledge_bases": knowledge_bases_view,
    "connectors": connectors_view,
    "routines": routines_view,
    "secrets": secrets_view,
    "built_in_tools": built_in_tools_view,
    "settings": settings_view,
}


async def read(conn: Any, enc: Any, kind: str, name: str | None = None) -> Any:
    """One view. Raises :class:`PlainMessage` for a reply meant for the model as text."""
    view = VIEWS.get(kind)
    if view is None:
        raise PlainMessage(f"Unknown kind {cut(str(kind), 60)!r}. Valid kinds: {', '.join(KINDS)}")
    if not isinstance(name, str) or not name.strip() or kind in {"overview", "settings"}:
        name = None  # an empty name is no name; these two kinds take none
    return await view(Ctx(conn, enc), name)
