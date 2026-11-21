"""Page awareness for the GleepGlorp drawer (M36 F3 L4, flight DD5).

A drawer message carries a page descriptor, ``{destination, section?, item?, item_name?,
tab?, create?}``, built by the client from the route. The server validates its shape
(:func:`validate_descriptor`, pure and sync), resolves the open item's stored name and builds
one marked line, ``Library › MCP servers › New MCP server`` (:func:`resolve_page`, async).
The pure parts import without the database, so the eval harness and Leg 5 use them freely.

Two kinds of fault, handled differently by the caller: a *shape* fault (a non-dict, an
unknown key, a wrong type, a string over its cap) refuses the message; a *value* fault (a
destination, section or tab not in the tables below) keeps the message and drops the page,
so a client/server table drift can never break the drawer. A value fault's error starts with
:data:`VALUE_FAULT`.

Every label table here is pinned equal to the client source it copies by
``tests/test_gleepglorp_page.py`` through ``tests/_app_routes.py``.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

VALUE_FAULT = "value: "
"""Prefix of the error of a value fault (the message is kept, the page dropped)."""

DESTINATIONS: dict[str, str] = {"agents": "Agents", "library": "Library", "settings": "Settings"}

# router.js LIBRARY_LABELS
LIBRARY_LABELS: dict[str, str] = {
    "providers": "Model providers",
    "knowledge": "Knowledge bases",
    "mcp": "MCP servers",
    "connectors": "Connectors",
    "secrets": "Secrets",
}

# settings-pages.js PAGES
SETTINGS_LABELS: dict[str, str] = {
    "gleepglorp": "GleepGlorp",
    "appearance": "Appearance",
    "date-and-time": "Date and time",
    "prompts": "Prompts",
    "encryption": "Encryption",
    "tools": "Built-in tools",
    "knowledge-indexing": "Knowledge indexing",
}

# agent-editor.js TAB_ITEMS
TAB_LABELS: dict[str, str] = {
    "general": "General",
    "rules-and-notes": "Rules and notes",
    "knowledge": "Knowledge",
    "tools": "Tools",
    "routines": "Routines",
    "self-configuration": "Self-configuration",
}

# The create-editor titles, copied exactly. Key: the Library group, or "agents".
CREATE_NAMES: dict[str, str] = {
    "agents": "New Agent",
    "providers": "New model provider",
    "knowledge": "New knowledge base",
    "mcp": "New MCP server",
    "connectors": "New Connector",
    "secrets": "New secret",
}

KEYS = frozenset({"destination", "section", "item", "item_name", "tab", "create"})
ITEM_MAX = 200
ITEM_NAME_MAX = 200
NAME_CAP = 80
LINE_CAP = 240
_SEP = " › "

_BIDI = frozenset("؜‎‏‪‫‬‭‮⁦⁧⁨⁩")


def sanitize_name(s: str) -> str:
    """A name safe to put in the line: control, bidi and line characters removed, ``[``,
    ``]`` and ``›`` removed, whitespace collapsed, capped at 80 characters with an ellipsis.
    It can never open a bracket, a line or a breadcrumb level."""
    out: list[str] = []
    for ch in str(s):
        cat = unicodedata.category(ch)
        if ch in _BIDI or cat == "Cf":
            continue
        if cat in ("Cc", "Zl", "Zp"):
            out.append(" ")
        elif ch in "[]›":
            continue
        else:
            out.append(ch)
    text = re.sub(r"\s+", " ", "".join(out)).strip()
    if len(text) > NAME_CAP:
        text = text[: NAME_CAP - 1].rstrip() + "…"
    return text


def validate_descriptor(raw: Any) -> tuple[dict[str, Any] | None, str | None]:
    """Check a descriptor's shape and its values. Returns ``(descriptor, None)`` when valid,
    ``(None, error)`` otherwise; an error that starts with :data:`VALUE_FAULT` is a value
    fault (keep the message, drop the page), any other is a shape fault (refuse)."""
    if not isinstance(raw, dict):
        return None, "the page must be an object"
    unknown = sorted(str(k) for k in raw if k not in KEYS)
    if unknown:
        return None, f"unknown page key: {unknown[0]}"
    out: dict[str, Any] = {}
    for key, cap in (("item", ITEM_MAX), ("item_name", ITEM_NAME_MAX)):
        if key in raw and raw[key] is not None:
            v = raw[key]
            if not isinstance(v, str):
                return None, f"page {key} must be a string"
            if len(v) > cap:
                return None, f"page {key} is too long"
            if key == "item" and not v:
                return None, "page item must not be empty"
            out[key] = v
    for key in ("destination", "section", "tab"):
        if key in raw and raw[key] is not None:
            if not isinstance(raw[key], str):
                return None, f"page {key} must be a string"
            if len(raw[key]) > 64:
                return None, f"page {key} is too long"
            out[key] = raw[key]
    if "create" in raw and raw["create"] is not None:
        if not isinstance(raw["create"], bool):
            return None, "page create must be a boolean"
        if raw["create"]:
            out["create"] = True
    if "destination" not in out:
        return None, "page destination is required"
    # Shape is fine. Now the values against the tables.
    dest = out["destination"]
    if dest not in DESTINATIONS:
        return None, f"{VALUE_FAULT}unknown destination {dest!r}"
    section = out.get("section")
    if dest == "agents" and section is not None:
        return None, f"{VALUE_FAULT}agents has no section"
    if dest == "library" and section is not None and section not in LIBRARY_LABELS:
        return None, f"{VALUE_FAULT}unknown Library group {section!r}"
    if dest == "settings":
        if section is None or section not in SETTINGS_LABELS:
            return None, f"{VALUE_FAULT}unknown Settings section {section!r}"
    if dest == "library" and section is None and ("item" in out or out.get("create")):
        return None, f"{VALUE_FAULT}a Library item needs a group"
    if "tab" in out and (dest != "agents" or out["tab"] not in TAB_LABELS):
        return None, f"{VALUE_FAULT}unknown tab {out['tab']!r}"
    if out.get("create") and dest == "settings":
        return None, f"{VALUE_FAULT}Settings has nothing to create"
    return out, None


def _create_name(descriptor: dict[str, Any]) -> str | None:
    key = "agents" if descriptor["destination"] == "agents" else descriptor.get("section")
    return CREATE_NAMES.get(key or "")


def build_line(descriptor: dict[str, Any], resolved_name: str | None = None) -> str:
    """The line for a validated descriptor, labels joined with `` › ``. ``resolved_name`` is
    the item's stored name; without it the sanitised ``item_name``, then the segment."""
    dest = descriptor["destination"]
    parts = [DESTINATIONS[dest]]
    section = descriptor.get("section")
    if dest == "library" and section:
        parts.append(LIBRARY_LABELS[section])
    elif dest == "settings" and section:
        parts.append(SETTINGS_LABELS[section])
    if descriptor.get("create"):
        name = _create_name(descriptor)
        if name:
            parts.append(name)
    elif descriptor.get("item"):
        name = ""
        for candidate in (resolved_name, descriptor.get("item_name"), descriptor["item"]):
            if candidate:
                name = sanitize_name(candidate)
                if name:
                    break
        if name:
            parts.append(name)
        if dest == "agents" and descriptor.get("tab"):
            parts.append(TAB_LABELS[descriptor["tab"]])
    line = _SEP.join(parts)
    if len(line) > LINE_CAP:
        line = line[: LINE_CAP - 1].rstrip() + "…"
    return line


async def _stored_name(conn: Any, descriptor: dict[str, Any]) -> str | None:
    """The stored name of the open item, or None when it does not resolve."""
    dest = descriptor["destination"]
    item = descriptor.get("item")
    if not item or descriptor.get("create"):
        return None
    if dest == "settings":
        return item
    if dest == "agents":
        async with conn.execute("SELECT name FROM agents WHERE name = ?", (item,)) as cur:
            row = await cur.fetchone()
        return row[0] if row else None
    from the_one.config import settings
    from the_one.db.repositories import (
        ConnectorRepository,
        KnowledgeBaseRepository,
        LLMProviderRepository,
        MCPSourceRepository,
        SecretRepository,
    )
    from the_one.encryption import get_encryptor

    section = descriptor.get("section")
    if section == "knowledge":
        found: Any = await KnowledgeBaseRepository(conn).get(item)
    else:
        enc = get_encryptor(settings.data_dir)
        if section == "providers":
            found = await LLMProviderRepository(conn, enc).get(item)
        elif section == "mcp":
            found = await MCPSourceRepository(conn, enc).get(item)
        elif section == "connectors":
            found = await ConnectorRepository(conn, enc).get(item)
        elif section == "secrets":
            found = await SecretRepository(conn, enc).get(item)
        else:
            return None
    name = getattr(found, "name", None)
    return name if isinstance(name, str) and name else None


async def resolve_page(conn: Any, descriptor: dict[str, Any]) -> dict[str, Any]:
    """Resolve a validated descriptor into ``{"line", "descriptor"}``. A repository error or
    an unknown id falls back to ``item_name``, then the segment, and never fails the turn."""
    resolved: str | None = None
    try:
        resolved = await _stored_name(conn, descriptor)
    except Exception:  # noqa: BLE001 - a lookup failure must not fail the turn
        resolved = None
    return {"line": build_line(descriptor, resolved), "descriptor": descriptor}
