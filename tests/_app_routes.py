"""The app's valid route patterns and aliases, parsed from the client source (M36 F1 L07).

One shared module for the guide's drift test (``tests/test_gleepglorp_guide.py``) and the
prompt link check (Leg 8). Nothing is hand-copied: the Library groups come from the
router's ``SECTIONS`` rows, the Settings sections from ``settings-pages.js`` and the agent
tabs from ``TAB_ITEMS`` in ``studio/agent-editor.js``. The alias rules mirror
``router.js`` ``resolve()``: a route that redirects is not a link target, because the page
the reader lands on is not the page the text names.

Valid link targets (the ``#`` is optional here):

* ``chats``, ``chats/~new/{agent}``, ``chats/{id}``
* ``agents``, ``agents/~new``, ``agents/{name}``, ``agents/{name}/{tab}``
* ``library``, ``library/{group}/~new``, ``library/{group}/{id}``
* ``settings/{section}``, ``settings/tools/{name}``

Aliases that redirect (a link to one is a failure): bare ``chats/~new``, bare
``library/{group}``, bare ``settings``, ``settings/general...``, ``agents/{name}/mcps...``
and the legacy ``chat``, ``studio`` and ``admin`` heads.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

JS = Path(__file__).resolve().parent.parent / "the_one" / "interfaces" / "web" / "static" / "js"

_LIBRARY_ROW = re.compile(r"\{ dest: 'library', area: '[^']+', route: '([^']+)'")
_SETTINGS_ROW = re.compile(r"\{ section: '([^']+)', label: '[^']+', group: '[^']+' \}")
_TAB_ITEM = re.compile(r"\{ id: '([^']+)', label: '[^']+' \}")

LEGACY_HEADS = frozenset({"chat", "studio", "admin"})
RESERVED_NEW = "~new"


@dataclass(frozen=True)
class Routes:
    """The three parsed sets a route is checked against."""

    library_groups: frozenset[str]
    settings_sections: frozenset[str]
    agent_tabs: frozenset[str]


def library_groups() -> list[str]:
    """The router's Library ``SECTIONS`` rows, in order."""
    return _LIBRARY_ROW.findall((JS / "router.js").read_text(encoding="utf-8"))


def settings_sections() -> list[str]:
    """The Settings page table's sections, in nav order."""
    return _SETTINGS_ROW.findall((JS / "settings-pages.js").read_text(encoding="utf-8"))


def agent_tabs() -> list[str]:
    """The agent editor's ``TAB_ITEMS`` ids, in order."""
    text = (JS / "areas" / "studio" / "agent-editor.js").read_text(encoding="utf-8")
    start = text.index("var TAB_ITEMS = [")
    return _TAB_ITEM.findall(text[start : text.index("];", start)])


_LINK = re.compile(r"\]\(([^)\s]*)\)")


def link_targets(markdown: str) -> list[str]:
    """Every ``](target)`` in a markdown text, in order (the target as written)."""
    return _LINK.findall(markdown)


def load_routes() -> Routes:
    return Routes(
        frozenset(library_groups()), frozenset(settings_sections()), frozenset(agent_tabs())
    )


def check_route(fragment: str, routes: Routes | None = None) -> str | None:
    """``None`` when ``fragment`` (a hash, with or without ``#``) is a link target the app
    serves, else one plain sentence saying why not."""
    r = routes or load_routes()
    segs = [s for s in fragment.removeprefix("#").split("/") if s]
    if not segs:
        return "an empty route"
    head = segs[0]
    if head in LEGACY_HEADS:
        return f"'{head}' is a legacy alias that redirects"
    if head == "chats":
        if len(segs) == 1:
            return None
        if segs[1] == RESERVED_NEW:
            return None if len(segs) == 3 else "bare 'chats/~new' is an alias that redirects"
        return None if len(segs) == 2 else "too many segments for a chat"
    if head == "agents":
        if len(segs) == 1 or (len(segs) == 2):
            return None
        if segs[1] == RESERVED_NEW:
            return "extra segments after 'agents/~new' are dropped"
        if len(segs) == 3:
            if segs[2] == "mcps":
                return "'mcps' is an alias that redirects to the Tools tab"
            if segs[2] in r.agent_tabs:
                return None
            return f"'{segs[2]}' is not an agent tab"
        return "too many segments for an agent"
    if head == "library":
        if len(segs) == 1:
            return None
        if segs[1] not in r.library_groups:
            return f"'{segs[1]}' is not a Library group"
        if len(segs) == 2:
            return f"bare 'library/{segs[1]}' is an alias that redirects"
        return None if len(segs) == 3 else "too many segments for a Library item"
    if head == "settings":
        if len(segs) == 1:
            return "bare 'settings' is an alias that redirects"
        if segs[1] == "general":
            return "'settings/general' is an alias that redirects"
        if segs[1] not in r.settings_sections:
            return f"'{segs[1]}' is not a Settings section"
        if len(segs) == 2:
            return None
        if segs[1] == "tools" and len(segs) == 3:
            return None
        return f"'settings/{segs[1]}' has no item pages"
    return f"'{head}' is not a destination"
