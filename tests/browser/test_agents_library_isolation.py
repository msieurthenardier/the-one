# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Agents <-> Library isolation inside the one studio module (M25 F3 L3/L4a, DD3).

Agents and Library share ``areas/studio.js`` (DD3: extend, do not split), and
``mountArea`` never re-runs ``init``/``deactivate`` between them, so
``setActiveSection`` alone owns the sidebar hosts: it creates each destination's
list pane on entering it and destroys it on leaving, and shows exactly one of the
two hosts (``.studio-agents-list`` / ``.studio-library-list``). A move between
Library sections keeps the Library pane (one list). These tests pin the leak
classes the DD3 guards name:

* (a)/(b)/(e) the destination walk -- Agents -> agent A -> Library (an item) ->
  Agents -> Library -> Agents: the visible host matches the destination, exactly
  one list pane is mounted on either destination, the right selection and
  detail show, and no stray rows survive; Library sections share one pane;
* (d) switching destination while work is in flight -- an initial ``loadAll``, a
  ``doSelect`` fresh-agent fetch (``selectSeq``), an MCP editor waiting for its
  types (``editorGen``) and a knowledge-base status poll -- with no stale render
  on arrival and the poll stopped, asserted through request counters and DOM
  state, not timing.

Requests are HELD (a stored Playwright route released later from the test body),
so "in flight" is a fact, not a race. Chromium only. Falls in the ``agents`` lane.
"""

from __future__ import annotations

import httpx
import pytest
from browser import _lists, _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp, seed_mock_agent
from playwright.sync_api import Page, Route, expect

pytestmark = pytest.mark.browser

SIDEBAR = "#app-sidebar .sidebar-panel.area-studio"


def _post(base: str, path: str, payload: dict) -> dict:
    r = httpx.post(base + path, json=payload, headers=auth_headers_for(base), timeout=5.0)
    assert r.status_code in (200, 201), f"{path}: {r.status_code} {r.text}"
    return r.json()


def _sidebar(page: Page) -> dict:
    return page.evaluate(
        """(sel) => {
          const p = document.querySelector(sel);
          const list = p.querySelector('.studio-agents-list');
          const lib = p.querySelector('.studio-library-list');
          const shown = (el) => !!el && el.getClientRects().length > 0;
          const labels = (q) => Array.from(p.querySelectorAll(q))
            .map((r) => r.querySelector('.ui-list-pane-label').textContent);
          return {
            listShown: shown(list), libShown: shown(lib),
            panes: p.querySelectorAll('.ui-list-pane').length,
            agentPanes: p.querySelectorAll('[data-testid="agents-list"]').length,
            libPanes: p.querySelectorAll('[data-testid="library-list"]').length,
            navs: p.querySelectorAll('.section-nav').length,
            rows: p.querySelectorAll('[data-testid="agent-item"]').length,
            selected: labels('[data-testid="agent-item"][aria-current="page"]'),
            libSelected: labels('[data-testid="library-list"] [aria-current="page"]'),
            siblings: list && lib ? list.parentElement === lib.parentElement : false,
          };
        }""",
        SIDEBAR,
    )


def _studio(page: Page) -> dict:
    return page.evaluate(
        """() => { const s = App.areas.find((a) => a.id === 'studio');
                   return {section: s._activeSection, agent: s._selectedAgent && s._selectedAgent.name,
                           create: s._createMode, pending: s._pendingSelectName, kb: s._selectedKbId,
                           poll: !!s._knowledgePollTimer, mcp: s._mcpSourceFormMode}; }"""
    )


def _expect_agents_host(page: Page, n_agents: int, selected: list[str]) -> None:
    expect(page.locator('[data-testid="agents-list"]')).to_be_visible(timeout=8000)
    expect(page.locator('[data-testid="agent-item"]')).to_have_count(n_agents, timeout=8000)
    sb = _sidebar(page)
    assert sb["listShown"] and not sb["libShown"] and sb["siblings"], sb
    assert sb["panes"] == 1 and sb["agentPanes"] == 1 and sb["libPanes"] == 0, sb
    assert sb["rows"] == n_agents and sb["navs"] == 0, sb
    assert sb["selected"] == selected, sb


def _expect_library_host(page: Page, selected: list[str] | None = None) -> None:
    expect(page.locator('[data-testid="library-list"]')).to_be_visible(timeout=8000)
    sb = _sidebar(page)
    assert not sb["listShown"] and sb["libShown"], sb
    assert sb["panes"] == 1 and sb["libPanes"] == 1 and sb["agentPanes"] == 0, sb
    assert sb["rows"] == 0 and sb["selected"] == [] and sb["navs"] == 0, sb
    if selected is not None:
        assert sb["libSelected"] == selected, sb


# ── (a)/(b)/(e): the destination walk ───────────────────────────────────────


def test_agents_library_walk_keeps_one_list_and_the_right_detail(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, a = app_with_agent.base_url, app_with_agent.agent_name
    seed_mock_agent(base, app_with_agent.provider_id, name="other-agent")
    kb = _post(base, "/api/knowledge-bases", {"name": "Walk KB"})["id"]

    # Agents: open agent A.
    _nav.goto_settled(page, base, "agents")
    _expect_agents_host(page, 2, [])
    _lists.open_item(page, "agents", a)
    expect(page.locator(".editor-title")).to_have_text(a, timeout=8000)
    _expect_agents_host(page, 2, [a])

    # Library: open the knowledge base (an item) -- in-app, no reload.
    _nav.open_destination(page, "library")
    _nav.expect_route(page, "library")
    _lists.open_item(page, "library/knowledge", "Walk KB")
    _nav.expect_route(page, f"library/knowledge/{_nav.seg(kb)}")
    expect(page.locator(".studio-section-content .editor-title")).to_have_text(
        "Walk KB", timeout=8000
    )
    _expect_library_host(page, ["Walk KB"])
    st = _studio(page)
    assert st["section"] == "knowledge" and st["agent"] is None and st["kb"] == kb, st
    expect(page.locator(".studio-editor")).to_be_hidden()

    # Agents: the rail restores agent A, selected, beside the list.
    _nav.open_destination(page, "agents")
    _nav.expect_route(page, f"agents/{_nav.seg(a)}/general")
    expect(page.locator(".studio-editor .editor-title")).to_have_text(a, timeout=8000)
    _expect_agents_host(page, 2, [a])
    st = _studio(page)
    assert st["kb"] is None and not st["poll"], st
    # Nothing of the Library detail is left in the detail pane.
    expect(page.locator('[data-testid="kb-name-input"]')).to_have_count(0)

    # Library again: its last item (the knowledge base) is restored.
    _nav.open_destination(page, "library")
    _nav.expect_route(page, f"library/knowledge/{_nav.seg(kb)}")
    expect(page.locator(".studio-section-content .editor-title")).to_have_text(
        "Walk KB", timeout=8000
    )
    _expect_library_host(page, ["Walk KB"])
    assert _studio(page)["agent"] is None

    # Agents once more: one pane, A still selected, no stray rows.
    _nav.open_destination(page, "agents")
    expect(page.locator(".studio-editor .editor-title")).to_have_text(a, timeout=8000)
    _expect_agents_host(page, 2, [a])


# ── (d): destination switches while work is in flight ───────────────────────


class _Hold:
    """Hold matching requests until released (state, not timing)."""

    def __init__(self, page: Page, pattern: str, predicate=None) -> None:  # noqa: ANN001
        self.routes: list[Route] = []
        self.page = page
        self.pattern = pattern
        self.released = False
        self.predicate = predicate or (lambda req: req.method == "GET")
        page.route(pattern, self._handle)

    def _handle(self, route: Route) -> None:
        if self.released or not self.predicate(route.request):
            route.continue_()
        else:
            self.routes.append(route)

    def wait_held(self, n: int = 1, timeout: float = 8000) -> None:
        deadline = timeout
        while len(self.routes) < n and deadline > 0:
            self.page.wait_for_timeout(50)
            deadline -= 50
        assert len(self.routes) >= n, f"no request held on {self.pattern}"

    def release(self) -> None:
        """Continue every held request, then pass later ones straight through.
        (The handler stays routed: unrouting first would let Playwright settle
        the held routes itself.)"""
        self.released = True
        while self.routes:
            self.routes.pop(0).continue_()


def test_switch_to_library_while_the_first_agents_load_is_in_flight(
    app_with_agent: SeededApp, page: Page
) -> None:
    """A cold boot on an agent item, with the agents list held: leaving for
    Library before it lands renders nothing on arrival (no rows, no editor)."""
    base, a = app_with_agent.base_url, app_with_agent.agent_name
    hold = _Hold(page, "**/api/agents")
    _nav._install_tracker(page)  # wait_settled reads the app's fetch tracker
    _nav.goto(page, base, f"agents/{_nav.seg(a)}/general")
    hold.wait_held()
    st = _studio(page)
    assert st["pending"] == a and st["agent"] is None, st
    _nav.open_destination(page, "library")
    _nav.expect_route(page, "library")
    expect(page.locator('[data-testid="library-start"]')).to_be_visible(timeout=8000)

    hold.release()
    _nav.wait_settled(page)
    _expect_library_host(page)
    st = _studio(page)
    assert st["agent"] is None and st["pending"] is None and st["section"] == "library", st
    expect(page.locator(".studio-editor")).to_be_hidden()
    expect(page.locator(".studio-editor .editor-title")).to_have_count(0)
    _nav.expect_route(page, "library")

    # Back on Agents the list renders from the landed load, nothing selected
    # but the restored route's agent.
    _nav.open_destination(page, "agents")
    expect(page.locator(".studio-editor .editor-title")).to_have_text(a, timeout=8000)
    _expect_agents_host(page, 1, [a])


def test_switch_to_library_while_an_agent_open_is_in_flight(
    app_with_agent: SeededApp, page: Page
) -> None:
    """``selectSeq``: the open's fresh-agent fetch (``GET /api/agents/{name}``) is
    held; leaving for Library invalidates it, so its resolution renders nothing."""
    base, a = app_with_agent.base_url, app_with_agent.agent_name
    _nav.goto_settled(page, base, "agents")
    expect(page.locator('[data-testid="agent-item"]')).to_have_count(1, timeout=8000)
    hold = _Hold(page, f"**/api/agents/{_nav.seg(a)}")
    _lists.list_row(page, "agents", a).click()
    hold.wait_held()
    _nav.open_destination(page, "library")
    _nav.expect_route(page, "library")
    expect(page.locator('[data-testid="library-start"]')).to_be_visible(timeout=8000)

    hold.release()
    _nav.wait_settled(page)
    st = _studio(page)
    assert st["agent"] is None and st["section"] == "library", st
    expect(page.locator(".studio-editor")).to_be_hidden()
    expect(page.locator(".studio-editor .editor-title")).to_have_count(0)
    _expect_library_host(page)


def test_switch_to_agents_while_an_mcp_editor_waits_for_its_types(
    app_with_agent: SeededApp, page: Page
) -> None:
    """``editorGen``: the MCP create form waits for ``/api/mcp-sources/types``
    (held from boot); leaving for Agents closes it (closeOpenItem bumps the
    generation), so the late types never mount the editor over Agents."""
    base = app_with_agent.base_url
    hold = _Hold(page, "**/api/mcp-sources/types")
    _nav._install_tracker(page)  # wait_settled reads the app's fetch tracker
    _nav.goto(page, base, "library/mcp/~new")
    hold.wait_held()
    st = _studio(page)
    assert st["mcp"] == "add", st
    _nav.open_destination(page, "agents")
    _nav.expect_route(page, "agents")
    expect(page.locator('[data-testid="agent-select-empty"]')).to_be_visible(timeout=8000)

    hold.release()
    _nav.wait_settled(page)
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_have_count(0)
    expect(page.locator('[data-testid="agent-select-empty"]')).to_be_visible()
    st = _studio(page)
    assert st["mcp"] is None and st["section"] == "agents", st
    _expect_agents_host(page, 1, [])


def test_leaving_library_stops_the_knowledge_base_poll(
    app_with_agent: SeededApp, page: Page
) -> None:
    """The 5-second status poll of an open knowledge base stops when the user
    leaves for Agents: the status-request counter stops moving."""
    base = app_with_agent.base_url
    kb = _post(base, "/api/knowledge-bases", {"name": "Polled KB"})["id"]
    status_hits: list[str] = []
    page.on(
        "request",
        lambda r: status_hits.append(r.url) if r.url.endswith(f"/{kb}/status") else None,
    )
    _nav.goto_settled(page, base, f"library/knowledge/{_nav.seg(kb)}")
    expect(page.locator(".editor-title")).to_have_text("Polled KB", timeout=8000)
    # The poll is live: at least one poll request lands after the mount's.
    mount_hits = len(status_hits)
    deadline = 12000
    while len(status_hits) <= mount_hits and deadline > 0:
        page.wait_for_timeout(250)
        deadline -= 250
    assert len(status_hits) > mount_hits, "the knowledge-base poll never fired"
    assert _studio(page)["poll"] is True

    _nav.open_destination(page, "agents")
    _nav.expect_route(page, "agents")
    st = _studio(page)
    assert st["poll"] is False and st["kb"] is None, st
    left_at = len(status_hits)
    # One full poll interval (5 s) and a margin: the counter must not move.
    page.wait_for_timeout(6500)
    assert len(status_hits) == left_at, status_hits[left_at:]
    _expect_agents_host(page, 1, [])


# ── M25 F3 L4a: the Library list pane ───────────────────────────────────────


def test_library_sections_share_one_pane_and_agents_swaps_it(
    app_with_agent: SeededApp, page: Page
) -> None:
    """A move between Library sections keeps the SAME list pane (one list, so
    not a leave); Agents <-> Library swaps the panes, exactly one at a time, and
    a fresh Library pane is a new node with the right selection."""
    base = app_with_agent.base_url
    kb = _post(base, "/api/knowledge-bases", {"name": "Pane KB"})["id"]
    _post(
        base,
        "/api/mcp-sources",
        {"name": "pane-mcp", "type": "stdio", "config": {"command": "x"}, "secrets": {}},
    )
    _nav.goto_settled(page, base, "library")
    _expect_library_host(page, [])
    page.evaluate(
        "() => { window.__libPane = document.querySelector('[data-testid=\"library-list\"]'); }"
    )

    same = "() => document.querySelector('[data-testid=\"library-list\"]') === window.__libPane"
    for route in (
        "library/mcp",
        "library/connectors",
        "library/connectors/~new",
        "library/knowledge",
    ):
        page.evaluate("r => App.router.go(r)", "#" + route)
        _nav.expect_route(page, route)
        _expect_library_host(page)
        assert page.evaluate(same), route
    _lists.open_item(page, "library/knowledge", "Pane KB")
    _nav.expect_route(page, f"library/knowledge/{_nav.seg(kb)}")
    _lists.open_item(page, "library/mcp", "pane-mcp")
    _expect_library_host(page, ["pane-mcp"])
    assert page.evaluate(same)

    _nav.open_destination(page, "agents")
    _expect_agents_host(page, 1, [])
    assert page.evaluate("() => window.__libPane.isConnected") is False

    _nav.open_destination(page, "library")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)
    _expect_library_host(page, ["pane-mcp"])
    assert page.evaluate(same) is False  # a new pane for the new visit
