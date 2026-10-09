"""Central navigation helper for browser tests (M25 F2 leg 1).

Browser tests state routes in the NEW scheme (flight 02 DD1), without the
leading ``#``: ``"settings/providers/~new"``, ``"agents/My%20Agent/tools"``,
``"library/mcp/abc"``, ``"chats"``.  This module maps them to whatever the app
serves, so the shell/router rewrites are a one-line flip in here rather than a
60-file edit:

* ``SCHEME = "new"`` (leg 3 flipped it) -- routes are the app's own hashes
  (``new_hash``: ``"#" + route``).  ``"legacy"`` maps them to the pre-router
  hashes (``#studio``, ``#admin/...``, ``#chat/sessions/...``) per the DD2
  table; it is kept for the parity/unit tests and the legacy-URL redirect
  proofs, which write RAW legacy hashes.
* ``open_destination`` clicks the rail links (``[data-testid=rail-<id>]``,
  M25 F2 leg 6).

Route table (new scheme -> legacy hash)::

    chats                          -> #chat
    chats/{sid}                    -> #chat/sessions/{sid}
    chats/~new/{agent}             -> (none: ``legacy_hash`` raises)
    agents                         -> #studio          (app redirects to #studio/agents)
    agents/{name}[/{tab}[/{sid}]]  -> #studio/agents/{name}[/...]
    library                        -> #studio/knowledge
    library/knowledge              -> #studio/knowledge
    library/knowledge/~new         -> #studio/knowledge/new
    library/knowledge/{kbId}       -> #studio/knowledge/{kbId}
    library/mcp                    -> #studio/mcp-sources
    library/mcp/~new               -> #studio/mcp-sources/new
    library/mcp/{id}               -> #studio/mcp-sources/{id}
    library/connectors             -> #studio/connectors
    library/connectors/~new        -> #studio/connectors/new
    library/connectors/{id}        -> #studio/connectors/{id}
    settings                       -> #admin           (app redirects to #settings/appearance)
    settings/appearance            -> #admin/appearance
    settings/prompts               -> #admin/prompts
    settings/encryption            -> #admin/encryption
    settings/providers[/~new|/{id}]-> #admin/providers[/new|/{id}]
    settings/tools[/{name}]        -> #admin/tools[/...]
    settings/knowledge-indexing    -> #admin/knowledge
    settings/design-language       -> #admin/design-language

``~new`` is the reserved create segment (DD1) and is rewritten to ``/new`` ONLY
for providers and the three Library sections (knowledge bases, MCP sources and,
since M25 F3 leg 4a, connectors); ``agents/new/general`` is an agent NAMED
"new" and passes through untouched.

Canonicalisation (``canonical``) folds the app's own default redirects, so
``expect_route`` / ``current_route`` accept either form: ``#studio`` ==
``#studio/agents`` (both are ``agents``), ``settings`` == ``settings/appearance``,
``library`` == ``library/knowledge`` and a bare ``chats/~new`` == ``chats``.
``chats/~new/{agent}`` is the pending new chat (M25 F4 L3b); it never had a
legacy form, so ``legacy_hash`` raises for it.  Since M25 F3 leg 5a the former single
General page is three (Appearance, Prompts, Encryption): the app redirects
``settings/general`` (any suffix) and the legacy ``#admin``, ``#admin/system`` and
``#admin/general`` to ``settings/appearance``.  The legacy observations fold
there (``route_from_hash`` under ``SCHEME = "legacy"``), but ``canonical`` does
NOT fold ``settings/general``: a page left on it never equals
``settings/appearance``, so ``expect_route`` catches a missing redirect, and
``legacy_hash`` rejects it as an unknown route.
Routes compare PER SEGMENT after ``unquote`` so a ``%2F`` inside an id stays
distinct from a path separator while ``%20`` and a space compare equal.

``goto_settled`` / ``wait_settled`` are the state-driven readiness waits for
areas that load (and re-render) their inventory more than once on first
activation, or whose editor mounts only after a fetch resolves: they wait for
the app's own fetch activity to go quiet instead of a fixed ``expect`` timeout.

Callers encode ids with ``seg(value)`` (exactly JS ``encodeURIComponent``,
plus a leading ``~`` -> ``%7E``); ``_nav`` never re-encodes a route.

Legacy-URL tests (AC6)
----------------------
``LEGACY_URL_TESTS`` is the deliberate set of tests that keep a RAW legacy
``page.goto("...#studio/...")`` as their setup and assert through
``expect_route`` with the new-scheme route, so they prove the app's redirects.
They are the only functions the migration guard
(``tests/test_nav_helper.py::test_no_raw_route_hashes_in_browser_tests``)
lets use raw route hashes:

* test_flow_admin_settings_nav.py::test_legacy_general_hashes_redirect_directly
* test_flow_admin_tools_grid.py::test_admin_tools_deep_link_to_tool_loads_editor
* test_flow_agent_tabs.py::test_refresh_on_knowledge_tab_persists
* test_flow_chat_peer_attribution.py::test_chat_renders_peer_attribution
* test_flow_hash_routing.py::test_studio_knowledge_section_persists_on_refresh
* test_flow_provider_grid.py::test_unknown_provider_id_falls_back_to_grid
* test_flow_studio_mcp_navigation.py::test_studio_direct_load_mcp_sources
"""

from __future__ import annotations

import time
from urllib.parse import quote, unquote, urlsplit

from playwright.sync_api import Page

# The one mapping switch.  "new": DD1 routes (the app).  "legacy": pre-router hashes.
SCHEME = "new"

# file::function identifiers (see module docstring).
LEGACY_URL_TESTS: frozenset[str] = frozenset(
    {
        "test_flow_admin_settings_nav.py::test_legacy_general_hashes_redirect_directly",
        "test_flow_admin_tools_grid.py::test_admin_tools_deep_link_to_tool_loads_editor",
        "test_flow_agent_tabs.py::test_refresh_on_knowledge_tab_persists",
        "test_flow_chat_peer_attribution.py::test_chat_renders_peer_attribution",
        "test_flow_hash_routing.py::test_studio_knowledge_section_persists_on_refresh",
        "test_flow_provider_grid.py::test_unknown_provider_id_falls_back_to_grid",
        "test_flow_studio_mcp_navigation.py::test_studio_direct_load_mcp_sources",
    }
)

DESTINATIONS = ("chats", "agents", "library", "settings")

_RESERVED_NEW = "~new"


# ── Encoding / segments ───────────────────────────────────────────────────


def seg(value: str) -> str:
    """Encode one path segment exactly like JS ``encodeURIComponent``.

    A leading ``~`` additionally becomes ``%7E`` (DD1) so an agent named
    ``~new`` can never collide with the reserved create segment.
    """
    out = quote(str(value), safe="!'()*")
    if out.startswith("~"):
        out = "%7E" + out[1:]
    return out


def _norm_seg(s: str) -> str:
    """Normalise one already-encoded segment (idempotent)."""
    if s == _RESERVED_NEW:
        return s
    return seg(unquote(s))


def _split(route: str) -> list[str]:
    route = route.lstrip("#").strip("/")
    return [] if route == "" else route.split("/")


def _join(segs: list[str]) -> str:
    return "/".join(segs)


def canonical(route: str) -> str:
    """Fold the app's default redirects and normalise segment encoding.

    Accepts a new-scheme route (with or without a leading ``#``).
    """
    s = [_norm_seg(x) for x in _split(route)]
    if not s:
        return ""
    head = s[0]
    if head == "library" and len(s) == 1:
        return "library/knowledge"
    if head == "settings" and len(s) == 1:
        return "settings/appearance"
    if head == "chats" and s[1:] == [_RESERVED_NEW]:
        return "chats"
    return _join(s)


def routes_equal(a: str, b: str) -> bool:
    """Per-segment, canonical comparison of two new-scheme routes."""
    return canonical(a) == canonical(b)


# ── Mapping tables ────────────────────────────────────────────────────────


def new_hash(route: str) -> str:
    """The new-scheme hash for *route*: ``"#" + route``."""
    return "#" + _join(_split(route))


def legacy_hash(route: str) -> str:
    """Map a new-scheme route to today's legacy hash (DD2 table, inverted)."""
    s = _split(route)
    if not s:
        raise ValueError("empty route")
    head, rest = s[0], s[1:]
    if head == "chats":
        if rest[:1] == [_RESERVED_NEW]:
            raise ValueError(f"no legacy hash for the pending new chat: {route!r}")
        return "#chat" if not rest else "#" + _join(["chat", "sessions", *rest])
    if head == "agents":
        # Bare `agents` -> bare `#studio` (what most tests use); the app
        # redirects it to #studio/agents.
        return "#studio" if not rest else "#" + _join(["studio", "agents", *rest])
    if head == "library":
        if not rest:
            return "#studio/knowledge"
        sec, tail = rest[0], rest[1:]
        tail = ["new" if (i == 0 and t == _RESERVED_NEW) else t for i, t in enumerate(tail)]
        if sec == "knowledge":
            return "#" + _join(["studio", "knowledge", *tail])
        if sec == "mcp":
            return "#" + _join(["studio", "mcp-sources", *tail])
        if sec == "connectors":
            return "#" + _join(["studio", "connectors", *tail])
        raise ValueError(f"unknown library route: {route!r}")
    if head == "settings":
        if not rest:
            return "#admin"
        sec, tail = rest[0], rest[1:]
        if sec in ("appearance", "prompts", "encryption"):
            return "#" + _join(["admin", sec, *tail])
        if sec == "providers":
            tail = ["new" if (i == 0 and t == _RESERVED_NEW) else t for i, t in enumerate(tail)]
            return "#" + _join(["admin", "providers", *tail])
        if sec == "tools":
            return "#" + _join(["admin", "tools", *tail])
        if sec == "knowledge-indexing":
            return "#admin/knowledge"
        if sec == "design-language":
            return "#admin/design-language"
        raise ValueError(f"unknown settings route: {route!r}")
    raise ValueError(f"unknown route destination: {route!r}")


def _from_legacy(hash_: str) -> str:
    """Inverse of ``legacy_hash``: an observed legacy hash -> canonical route."""
    s = _split(hash_)
    if not s:
        return ""
    head, rest = s[0], s[1:]
    if head == "chat":
        if rest[:1] == ["sessions"]:
            rest = rest[1:]
        return canonical(_join(["chats", *rest]))
    if head == "studio":
        if not rest or rest == ["tools"]:
            return "agents"
        sec, tail = rest[0], rest[1:]
        if sec == "agents":
            return canonical(_join(["agents", *tail]))
        library_tail = [_RESERVED_NEW if (i == 0 and t == "new") else t for i, t in enumerate(tail)]
        if sec == "knowledge":
            return canonical(_join(["library", "knowledge", *library_tail]))
        if sec == "mcp-sources":
            return canonical(_join(["library", "mcp", *library_tail]))
        if sec == "connectors":
            return canonical(_join(["library", "connectors", *library_tail]))
        return canonical(hash_)
    if head == "admin":
        if not rest:
            return "settings/appearance"
        sec, tail = rest[0], rest[1:]
        if sec in ("system", "general"):
            return "settings/appearance"
        if sec == "providers":
            tail = [_RESERVED_NEW if (i == 0 and t == "new") else t for i, t in enumerate(tail)]
            return canonical(_join(["settings", "providers", *tail]))
        if sec == "knowledge":
            return "settings/knowledge-indexing"
        return canonical(_join(["settings", sec, *tail]))
    return canonical(hash_)


def route_from_hash(hash_: str) -> str:
    """Observed ``location.hash`` -> canonical new-scheme route (per SCHEME)."""
    if SCHEME == "legacy":
        return _from_legacy(hash_)
    return canonical(hash_)


def hash_for(route: str) -> str:
    """The hash the app serves for *route* under the active SCHEME."""
    return legacy_hash(route) if SCHEME == "legacy" else new_hash(route)


def href(route: str) -> str:
    """``"#" + <scheme hash>`` for app-emitted link selectors."""
    return hash_for(route)


# ── Page operations ───────────────────────────────────────────────────────


def _origin(page: Page) -> str:
    parts = urlsplit(page.url)
    return f"{parts.scheme}://{parts.netloc}"


def goto(page: Page, base: str, route: str, **kw):
    """Navigate *page* to *route* on the app at *base*.

    Passes an absolute URL to ``page.goto`` so the conftest wrapper (credential
    + handoff, keyed on the origin) is never re-implemented here.
    """
    return page.goto(base.rstrip("/") + "/" + hash_for(route), **kw)


# In-page fetch tracker for ``goto_settled`` / ``wait_settled``.  Registered as
# an init script so it is in place before the app's first fetch on every
# navigation.  Idempotent per document.
_TRACK_JS = """
(() => {
  if (window.__navTrack) return;
  const t = (window.__navTrack = { inflight: 0, seen: 0, lastEnd: performance.now() });
  const orig = window.fetch.bind(window);
  window.fetch = function (...args) {
    t.inflight++;
    t.seen++;
    const done = () => { t.inflight--; t.lastEnd = performance.now(); };
    let p;
    try { p = orig(...args); } catch (e) { done(); throw e; }
    p.then(done, done);
    return p;
  };
})();
"""

_SETTLED_JS = """
(quietMs) => {
  const t = window.__navTrack;
  return !!t && t.seen > 0 && t.inflight === 0 && performance.now() - t.lastEnd >= quietMs;
}
"""


def _install_tracker(page: Page) -> None:
    if not getattr(page, "_nav_tracker_installed", False):
        page.add_init_script(_TRACK_JS)
        page._nav_tracker_installed = True


def wait_settled(page: Page, quiet_ms: int = 400, timeout: float = 30000) -> None:
    """Wait until the app has issued fetches and none is in flight for *quiet_ms*.

    State-driven (the app's own fetch activity), so it holds under a slow
    server or a slow link where a fixed ``expect`` timeout would not.  Needs
    the tracker, i.e. a page navigated with ``goto_settled``.
    """
    page.wait_for_function(_SETTLED_JS, arg=quiet_ms, timeout=timeout, polling=100)


def goto_settled(page: Page, base: str, route: str, quiet_ms: int = 400, **kw):
    """``goto`` then wait for the area's initial data loads to finish.

    Several areas load their inventory more than once on first activation
    (``init()`` and ``activate()``/``_refresh()`` each fetch and re-render);
    interacting with a node from an earlier pass loses it to the later one.
    """
    _install_tracker(page)
    resp = goto(page, base, route, **kw)
    wait_settled(page, quiet_ms)
    # "Quiet" is a heuristic: under load the gap before the area issues its
    # list fetch can exceed quiet_ms, so a settled page may still be a grid.
    # A deep-linked MCP editor therefore also waits on its own mount.
    parts = [unquote(p) for p in route.strip("/").split("/")]
    if len(parts) == 3 and parts[:2] == ["library", "mcp"]:
        page.wait_for_selector(
            '[data-testid="save-mcp-source-btn"]', state="attached", timeout=30000
        )
    return resp


def set_route(page: Page, route: str) -> None:
    """Same-document hash write (fires ``hashchange``)."""
    page.evaluate("h => { location.hash = h; }", hash_for(route))


def current_route(page: Page) -> str:
    """The canonical new-scheme route the page is showing."""
    return route_from_hash(page.evaluate("location.hash"))


def expect_route(page: Page, route: str, timeout: float = 5000) -> None:
    """Retry until the page shows *route* (canonical, per-segment compare)."""
    want = canonical(route)
    deadline = time.monotonic() + timeout / 1000
    got = current_route(page)
    while got != want:
        if time.monotonic() >= deadline:
            raise AssertionError(
                f"expected route {want!r}, got {got!r} "
                f"(location.hash={page.evaluate('location.hash')!r})"
            )
        page.wait_for_timeout(50)
        got = current_route(page)


def wait_for_route_prefix(
    page: Page, prefix: str, *, not_equal: str | None = None, timeout: float = 5000
) -> str:
    """Wait until the hash starts with *prefix* (a route prefix ending in ``/``).

    *not_equal* is an optional full route the hash must differ from.  Returns
    the observed canonical route.
    """
    if SCHEME == "legacy":
        if prefix.strip("/") == "chats":
            hp = "#chat/sessions/"
        else:
            hp = legacy_hash(prefix.rstrip("/")) + "/"
    else:
        hp = "#" + prefix.strip("/") + "/"
    ne = hash_for(not_equal) if not_equal else None
    page.wait_for_function(
        "([p, ne]) => location.hash.startsWith(p) && location.hash !== ne",
        arg=[hp, ne],
        timeout=timeout,
    )
    return current_route(page)


def destination_locator(page: Page, name: str):
    """The control that opens destination *name*.

    The rail link (``[data-testid=rail-<id>]``), so it can never match the
    active content panel, which carries ``data-destination``.
    """
    if name not in DESTINATIONS:
        raise ValueError(f"unknown destination {name!r} (want one of {DESTINATIONS})")
    return page.locator(f'[data-testid="rail-{name}"]')


def destination_panel(page: Page, name: str):
    """The ACTIVE content panel of destination *name* -- the readiness probe.

    ``.content-panel.active[data-destination=...]``: the router sets the
    attribute on the active panel only, so this is visible exactly while the
    destination is the one being shown (and its area module has mounted).
    """
    if name not in DESTINATIONS:
        raise ValueError(f"unknown destination {name!r} (want one of {DESTINATIONS})")
    return page.locator(f'.content-panel.active[data-destination="{name}"]')


def open_destination(page: Page, name: str) -> None:
    """Open a top-level destination: chats | agents | library | settings."""
    destination_locator(page, name).click()
