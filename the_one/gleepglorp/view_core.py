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
