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

Layout (squawk 0386): this module is the one public entry point (:func:`read`, ``VIEWS``,
``KINDS``, ``ALLOWED``...). The shared core (declared keys, ``_emit``, helpers) is
``view_core.py``; the per-kind views are ``view_overview.py`` (overview, settings),
``view_agents.py`` (agents, routines), ``view_mcp.py`` (MCP servers) and ``view_library.py``
(providers, knowledge bases, connectors, secrets, built-in tools). A new kind adds its view to
the matching module, its keys to ``ALLOWED`` and a row to ``VIEWS`` here.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from the_one.gleepglorp.view_agents import agents_view, routines_view
from the_one.gleepglorp.view_core import (
    ALLOWED,
    KINDS,
    LIST_KINDS,
    OPERATOR_PATHS,
    OUTSIDE_PATHS,
    OUTSIDE_VALUE_PREFIXES,
    SURFACE_SUMMARY,
    UNREADABLE,
    Ctx,
    PlainMessage,
    UndeclaredKeyError,
    cut,
    scrub_url,
)
from the_one.gleepglorp.view_fields import fields_view
from the_one.gleepglorp.view_library import (
    built_in_tools_view,
    connectors_view,
    knowledge_bases_view,
    providers_view,
    secrets_view,
)
from the_one.gleepglorp.view_mcp import mcp_servers_view
from the_one.gleepglorp.view_overview import overview_view, settings_view

__all__ = [
    "ALLOWED",
    "KINDS",
    "LIST_KINDS",
    "OPERATOR_PATHS",
    "OUTSIDE_PATHS",
    "SURFACE_SUMMARY",
    "UNREADABLE",
    "VIEWS",
    "PlainMessage",
    "UndeclaredKeyError",
    "cut",
    "is_operator_only",
    "path_provenance",
    "read",
    "read_with_provenance",
    "scrub_url",
    "walk_paths",
]

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
    "fields": fields_view,
}


async def read(conn: Any, enc: Any, kind: str, name: str | None = None) -> Any:
    """One view. Raises :class:`PlainMessage` for a reply meant for the model as text."""
    return (await read_with_provenance(conn, enc, kind, name))[0]


def _resolve(path: str, table: dict[str, frozenset[str]], kind: str) -> int | None:
    """Length of the longest declared path in ``table[kind]`` that ``path`` equals or is under."""
    best: int | None = None
    for declared in table.get(kind, frozenset()):
        if path == declared or path.startswith((declared + ".", declared + "[")):
            best = max(best or 0, len(declared))
    return best


def path_provenance(kind: str, path: str) -> str | None:
    """``"operator"``, ``"outside"`` or ``None`` (declared in neither table) for one path."""
    op = _resolve(path, OPERATOR_PATHS, kind)
    out = _resolve(path, OUTSIDE_PATHS, kind)
    if op is None and out is None:
        return None
    if out is None or (op is not None and op > out):
        return "operator"
    return "outside"


def walk_paths(kind: str, data: Any) -> list[tuple[str, Any]]:
    """Every non-empty leaf of a view's output as ``(path, value)``; a list level is ``[]``.

    A list kind's output is a list of list entries (level ``list``); anything else is one
    detail dict (level ``detail``), except the list-or-detail kinds asked for a name.
    """
    leaves: list[tuple[str, Any]] = []

    def go(path: str, value: Any) -> None:
        if isinstance(value, dict):
            for k, v in value.items():
                go(f"{path}.{k}", v)
        elif isinstance(value, (list, tuple)):
            for v in value:
                go(f"{path}[]", v)
        elif value is not None and value != "":
            leaves.append((path, value))

    if isinstance(data, list) and kind in LIST_KINDS:
        for entry in data:
            go(f"{kind}.list", entry)
    else:
        go(f"{kind}.detail", data)
    return leaves


def is_operator_only(kind: str, data: Any) -> bool:
    """True when no leaf of ``data`` can carry text an outside party wrote (fail closed)."""
    for path, value in walk_paths(kind, data):
        if path_provenance(kind, path) != "operator":
            return False
        prefix = OUTSIDE_VALUE_PREFIXES.get(path)
        if prefix is not None and isinstance(value, str) and value.startswith(prefix):
            return False
    return True


async def read_with_provenance(
    conn: Any, enc: Any, kind: str, name: str | None = None, *, fields_only: bool = False
) -> tuple[Any, bool]:
    """One view and whether its output is operator-only. Same errors as :func:`read`."""
    view = VIEWS.get(kind)
    if view is None:
        raise PlainMessage(f"Unknown kind {cut(str(kind), 60)!r}. Valid kinds: {', '.join(KINDS)}")
    if not isinstance(name, str) or not name.strip() or kind in {"overview", "settings"}:
        name = None  # an empty name is no name; these two kinds take none
    data = await view(Ctx(conn, enc, fields_only=fields_only), name)
    return data, is_operator_only(kind, data)
