"""Shared core of GleepGlorp's whitelist views (M36 F1 L05; split out of ``views.py``, squawk 0386).

Holds the declared output keys per kind (``ALLOWED``), the runtime guard ``_emit``, the error
types, the small scrubbing helpers and the shared list-or-detail driver. The per-kind views
live in the sibling ``view_*.py`` modules and are collected, with the public entry point
``read``, by :mod:`the_one.gleepglorp.views`. See that module's docstring for the rule.
"""

from __future__ import annotations

import json
import logging
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
    "fields",
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
# MCP servers and providers also list ``id`` (the id a proposal targets; M36 F4 L1b).
_LIST_KEYS_WITH_ID = _LIST_KEYS | {"id"}

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
        "nested": frozenset({"number", "text", "enabled"}),
    },
    "mcp_servers": {
        "list": _LIST_KEYS_WITH_ID,
        "detail": frozenset(
            {
                "id",
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
        "list": _LIST_KEYS_WITH_ID,
        "detail": frozenset(
            {"id", "name", "type", "address", "oauth_active", "agents", "used_by_gleepglorp"}
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
    # Generated from the proposal shape (M36 F2 L2): a field description, never a stored value.
    "fields": {
        "list": _LIST_KEYS,
        "detail": frozenset({"name", "fields"}),
        "nested": frozenset(
            {
                "name",
                "label",
                "type",
                "required_on_create",
                "create_only",
                "min",
                "max",
                "hint",
                "reference",
            }
        ),
    },
}

# --- provenance, per output path (M36 F2 L3, DD9) ----------------------------------------
# Who can write a value decides whether it is operator-typed: ``outside`` when an agent
# (self-configuration, routine tools) or a server (MCP reports, catalog data) can write it,
# ``operator`` when only the operator's credential-gated routes can, free text included.
# Paths are dotted: ``{kind}.{list|detail}.{key}[.{nested}]``, with ``[]`` for each list
# level. A path matches itself and everything beneath it (the longest declared match wins);
# a path in neither table is treated as outside (fail closed). ``tests/
# test_gleepglorp_views_provenance.py`` pins that no path is in both and that every path the
# views emit is declared.
OPERATOR_PATHS: dict[str, frozenset[str]] = {
    "overview": frozenset(
        {
            "overview.detail.time_zone",
            "overview.detail.gleepglorp.state",
            "overview.detail.gleepglorp.model",
            "overview.detail.gleepglorp.provider",
            "overview.detail.gleepglorp.web_access",
            "overview.detail.gleepglorp.memory",
            "overview.detail.counts.agents",
            "overview.detail.counts.mcp_servers",
            "overview.detail.counts.providers",
            "overview.detail.counts.knowledge_bases",
            "overview.detail.counts.connectors",
            "overview.detail.counts.secrets",
            "overview.detail.counts.built_in_tools",
            "overview.detail.names.agents",
            "overview.detail.names.mcp_servers",
            "overview.detail.names.providers",
            "overview.detail.names.knowledge_bases",
            "overview.detail.names.connectors",
            "overview.detail.names.secrets",
        }
    ),
    "agents": frozenset(
        {
            "agents.list.name",
            "agents.list.summary",
            "agents.detail.name",
            "agents.detail.model",
            "agents.detail.provider",
            "agents.detail.enabled_tools",
            "agents.detail.disabled_tools",
            "agents.detail.tools_with_overrides",
            "agents.detail.rules[].number",
            "agents.detail.rules[].enabled",
            "agents.detail.mcp_servers",
            "agents.detail.knowledge_bases",
            "agents.detail.routines_count",
            "agents.detail.notes_count",
            "agents.detail.rich_visuals",
            "agents.detail.self_configuration",
        }
    ),
    "mcp_servers": frozenset(
        {
            "mcp_servers.list.id",
            "mcp_servers.list.name",
            "mcp_servers.list.summary",
            "mcp_servers.detail.id",
            "mcp_servers.detail.name",
            "mcp_servers.detail.type",
            "mcp_servers.detail.command",
            "mcp_servers.detail.args",
            "mcp_servers.detail.working_directory",
            "mcp_servers.detail.address",
            "mcp_servers.detail.header_names",
            "mcp_servers.detail.env_names",
            "mcp_servers.detail.connection.status",
            "mcp_servers.detail.connection.checked_at",
            "mcp_servers.detail.tool_count",
            "mcp_servers.detail.signed_in",
            "mcp_servers.detail.agents",
        }
    ),
    "providers": frozenset(
        {
            "providers.list.id",
            "providers.list.name",
            "providers.list.summary",
            "providers.detail.id",
            "providers.detail.name",
            "providers.detail.type",
            "providers.detail.address",
            "providers.detail.oauth_active",
            "providers.detail.agents",
            "providers.detail.used_by_gleepglorp",
        }
    ),
    "knowledge_bases": frozenset(
        {
            "knowledge_bases.list.name",
            "knowledge_bases.list.summary",
            "knowledge_bases.detail.name",
            "knowledge_bases.detail.description",
            "knowledge_bases.detail.folders",
            "knowledge_bases.detail.items.pending",
            "knowledge_bases.detail.items.indexing",
            "knowledge_bases.detail.items.indexed",
            "knowledge_bases.detail.items.failed",
            "knowledge_bases.detail.latest_indexed",
            "knowledge_bases.detail.indexer",
            "knowledge_bases.detail.agents",
        }
    ),
    "connectors": frozenset(
        {
            "connectors.list.name",
            "connectors.list.summary",
            "connectors.detail.name",
            "connectors.detail.type",
            "connectors.detail.enabled",
            "connectors.detail.default_agent",
            "connectors.detail.channel_bindings[].channel",
            "connectors.detail.channel_bindings[].agent",
        }
    ),
    "routines": frozenset(
        {
            "routines.detail.agent",
            "routines.detail.routines[].schedule",
            "routines.detail.routines[].next_run",
            "routines.detail.routines[].enabled",
        }
    ),
    "secrets": frozenset(
        {
            "secrets.list.name",
            "secrets.list.summary",
            "secrets.detail.name",
            "secrets.detail.description",
            "secrets.detail.keys",
            "secrets.detail.allowed_tools",
            "secrets.detail.agents",
        }
    ),
    "built_in_tools": frozenset(
        {
            "built_in_tools.list.name",
            "built_in_tools.list.summary",
            "built_in_tools.detail.name",
            "built_in_tools.detail.enabled",
            "built_in_tools.detail.summary",
            # The one dynamic map: a tool's own non-secret Config field names (no fixed key
            # set), so the prefix stays. Values are operator-set tool settings.
            "built_in_tools.detail.settings",
        }
    ),
    "settings": frozenset(
        {
            "settings.detail.time_zone.mode",
            "settings.detail.time_zone.zone",
            "settings.detail.time_zone.effective",
            "settings.detail.knowledge_indexing.chunking.size_chars",
            "settings.detail.knowledge_indexing.chunking.overlap_chars",
            "settings.detail.knowledge_indexing.monitoring.watch_enabled",
            "settings.detail.knowledge_indexing.monitoring.reconcile_interval_seconds",
            "settings.detail.knowledge_indexing.embedding.backend",
            "settings.detail.knowledge_indexing.embedding.model_id",
            "settings.detail.knowledge_indexing.embedding.dim",
        }
    ),
    "fields": frozenset(
        {
            "fields.list.name",
            "fields.list.summary",
            "fields.detail.name",
            "fields.detail.fields[].name",
            "fields.detail.fields[].label",
            "fields.detail.fields[].type",
            "fields.detail.fields[].required_on_create",
            "fields.detail.fields[].create_only",
            "fields.detail.fields[].min",
            "fields.detail.fields[].max",
            "fields.detail.fields[].hint",
            "fields.detail.fields[].reference",
        }
    ),
}

OUTSIDE_PATHS: dict[str, frozenset[str]] = {
    "overview": frozenset(),
    "agents": frozenset(
        {
            "agents.detail.description",
            "agents.detail.system_prompt",
            "agents.detail.rules[].text",
        }
    ),
    "mcp_servers": frozenset(
        {
            "mcp_servers.detail.tools",
            "mcp_servers.detail.connection.protocol_version",
            "mcp_servers.detail.connection.auth_posture",
            "mcp_servers.detail.connection.protocol_fallback",
        }
    ),
    "providers": frozenset(),
    "knowledge_bases": frozenset(),
    "connectors": frozenset(),
    "routines": frozenset({"routines.detail.routines[].name", "routines.detail.routines[].prompt"}),
    "secrets": frozenset(),
    "built_in_tools": frozenset(),
    "settings": frozenset(),
    "fields": frozenset(),
}

# A value under an otherwise operator path is outside when it starts with the prefix: an MCP
# tool name in an agent's tool lists was named by the server (built-in names stay operator).
OUTSIDE_VALUE_PREFIXES: dict[str, str] = {
    "agents.detail.enabled_tools[]": "mcp__",
    "agents.detail.disabled_tools[]": "mcp__",
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
        "fields",
    }
)

_SINGULAR = {
    "fields": "proposable kind",
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
    # Only ``agents_view`` reads it: the detail without free text (M36 F2 L3).
    fields_only: bool = False


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
    id_of: Callable[[Any], str | None] | None = None,
) -> Any:
    """The list (no ``name``) or one entry's detail.

    ``id_of`` (MCP servers and providers only) maps an entry's key to the id the model may pass
    back as a target; it adds ``id`` to each list entry and to the detail, and ``name`` then
    matches an id before a name. A key that maps to ``None`` (the synthetic self-configuration
    entry) gets no ``id``. The "…" overflow entry never has one.
    """
    if name is None:
        out = []
        for key, item_name in entries[:_MAX_LIST_NAMES]:
            try:
                summary = await summarize(key, item_name)
            except Exception:  # noqa: BLE001 - one bad row never fails the list
                logger.debug("read_app_config: %s %r unreadable", kind, item_name, exc_info=True)
                summary = UNREADABLE
            row: dict[str, Any] = {"name": item_name, "summary": cut(summary, 160)}
            item_id = id_of(key) if id_of else None
            if item_id is not None:
                row = {"id": item_id, **row}
            out.append(_emit(kind, "list", row))
        if len(entries) > _MAX_LIST_NAMES:
            out.append(
                _emit(
                    kind,
                    "list",
                    {"name": "…", "summary": f"{len(entries) - _MAX_LIST_NAMES} more not shown"},
                )
            )
        return out
    # An id match wins over a name match (two servers may share a name; only the id tells
    # them apart); otherwise the first entry with that name, as before.
    chosen = next((e for e in entries if id_of and id_of(e[0]) == name), None)
    if chosen is None:
        chosen = next((e for e in entries if e[1] == name), None)
    if chosen is None:
        raise _no_such(kind, name, [n for _, n in entries])
    key, item_name = chosen
    try:
        data = await detail(key, item_name)
        item_id = id_of(key) if id_of else None
        if item_id is not None:
            data = {"id": item_id, **data}
        return _emit(kind, "detail", data)
    except (PlainMessage, UndeclaredKeyError):
        raise
    except Exception:  # noqa: BLE001
        logger.debug("read_app_config: %s %r unreadable", kind, name, exc_info=True)
        raise PlainMessage(f"{item_name}: {UNREADABLE}") from None
