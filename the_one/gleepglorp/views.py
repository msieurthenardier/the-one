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
    SURFACE_SUMMARY,
    UNREADABLE,
    Ctx,
    PlainMessage,
    UndeclaredKeyError,
    cut,
    scrub_url,
)
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
    "SURFACE_SUMMARY",
    "UNREADABLE",
    "VIEWS",
    "PlainMessage",
    "UndeclaredKeyError",
    "cut",
    "read",
    "scrub_url",
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
}


async def read(conn: Any, enc: Any, kind: str, name: str | None = None) -> Any:
    """One view. Raises :class:`PlainMessage` for a reply meant for the model as text."""
    view = VIEWS.get(kind)
    if view is None:
        raise PlainMessage(f"Unknown kind {cut(str(kind), 60)!r}. Valid kinds: {', '.join(KINDS)}")
    if not isinstance(name, str) or not name.strip() or kind in {"overview", "settings"}:
        name = None  # an empty name is no name; these two kinds take none
    return await view(Ctx(conn, enc), name)
