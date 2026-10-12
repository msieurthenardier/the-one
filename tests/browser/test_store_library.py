"""App.store Library collections and App.usage (M25 F3 leg 2, DD9).

The store gains ``knowledge-bases``, ``mcp-sources`` (the plain list shape) and
``connectors``; the Library grids read through it.  Covers:

* AC1 -- the store API for each new collection (copies, force joins an
  in-flight request, failure keeps the last value, generation-safe
  invalidation, subscribe);
* AC2 -- the invalidation map, through the UI (knowledge-base create and
  delete, MCP delete, connector create);
* AC3 -- the Library list request counts per activation (M25 F3 L4a: the
  Library list's fetch policy -- pane creation and studio activate force-get
  the four collections, a move between Library sections fetches nothing);
* AC4 -- the pure ``App.usage`` helpers over fixed arrays.
"""

from __future__ import annotations

from urllib.parse import urlsplit

import httpx
import pytest
from browser import _lists, _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

COLLECTIONS = ("knowledge-bases", "mcp-sources", "connectors")


def _post(base: str, path: str, body: dict) -> dict:
    r = httpx.post(f"{base}{path}", json=body, headers=auth_headers_for(base), timeout=5)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _seed_library(app: SeededApp) -> dict[str, str]:
    """One knowledge base, one MCP source and one (disabled) connector."""
    base = app.base_url
    kb = _post(base, "/api/knowledge-bases", {"name": "Seed KB"})
    mcp = _post(
        base,
        "/api/mcp-sources",
        {"name": "seed-mcp", "type": "stdio", "config": {"command": "x"}, "secrets": {}},
    )
    conn = _post(
        base,
        "/api/connectors",
        {
            "name": "Seed Connector",
            "type": "discord",
            "config": {"default_agent": app.agent_name, "enabled": False},
            "secrets": {},
        },
    )
    return {"knowledge-bases": kb["id"], "mcp-sources": mcp["id"], "connectors": conn["id"]}


def _ready(page: Page, base: str, route: str = "chats") -> None:
    _nav.goto_settled(page, base, route)
    page.wait_for_function("() => !!(window.App && App.store)")


def _list_path(url: str) -> tuple[str, str]:
    parts = urlsplit(url)
    return parts.path, parts.query


class _Counter:
    """GET requests per Library list (the plain shape only for mcp-sources)."""

    def __init__(self, page: Page) -> None:
        self.reset()
        page.on("request", self._on_request)

    def reset(self) -> None:
        self.providers = self.kb = self.mcp = self.mcp_surfaces = self.conn = 0

    def _on_request(self, req) -> None:
        if req.method != "GET":
            return
        path, query = _list_path(req.url)
        if path.endswith("/api/providers"):
            self.providers += 1
        elif path.endswith("/api/knowledge-bases"):
            self.kb += 1
        elif path.endswith("/api/mcp-sources"):
            if "include_agent_surfaces" in query:
                self.mcp_surfaces += 1
            else:
                self.mcp += 1
        elif path.endswith("/api/connectors"):
            self.conn += 1

    def snapshot(self) -> tuple[int, int, int, int]:
        return (self.providers, self.kb, self.mcp, self.conn)


# ── AC1 -- store API per collection ──────────────────────────────────────


@pytest.mark.parametrize("name", COLLECTIONS)
def test_get_returns_a_copy(app_with_agent: SeededApp, page: Page, name: str) -> None:
    _seed_library(app_with_agent)
    _ready(page, app_with_agent.base_url)
    got = page.evaluate(
        """async (n) => {
          const a = await App.store.get(n, {force: true});
          const before = a[0].name;
          a[0].name = 'MUTATED'; a.push({name: 'x'});
          const p = App.store.peek(n).value;
          p[0].name = 'MUTATED2';
          const again = await App.store.get(n);
          return [before, again.length, again[0].name, App.store.peek(n).value[0].name];
        }""",
        name,
    )
    assert got[1] == 1
    assert got[0] == got[2] == got[3], got


@pytest.mark.parametrize("name", COLLECTIONS)
def test_force_joins_an_in_flight_request(app_with_agent: SeededApp, page: Page, name: str) -> None:
    _seed_library(app_with_agent)
    _ready(page, app_with_agent.base_url)
    page.evaluate("n => App.store.invalidate(n)", name)
    counter = _Counter(page)
    res = page.evaluate(
        """async (n) => {
          const out = await Promise.all([App.store.get(n), App.store.get(n, {force: true}),
                                         App.store.get(n, {force: true})]);
          return out.map(a => a.length);
        }""",
        name,
    )
    assert res == [1, 1, 1]
    idx = COLLECTIONS.index(name) + 1  # the snapshot leads with providers
    assert counter.snapshot()[idx] == 1, counter.snapshot()


@pytest.mark.parametrize("name", COLLECTIONS)
def test_500_rejects_and_peek_keeps_last_value(
    app_with_agent: SeededApp, page: Page, name: str
) -> None:
    _seed_library(app_with_agent)
    _ready(page, app_with_agent.base_url)
    first = page.evaluate("async n => (await App.store.get(n, {force: true}))[0].name", name)

    def fail(route) -> None:
        path, query = _list_path(route.request.url)
        if route.request.method == "GET" and path.endswith(f"/api/{name}") and not query:
            route.fulfill(status=500, content_type="application/json", body='{"detail": "boom"}')
        else:
            route.continue_()

    page.route(f"**/api/{name}", fail)
    res = page.evaluate(
        """async (n) => {
          let rejected = false;
          try { await App.store.get(n, {force: true}); } catch (e) { rejected = true; }
          const p = App.store.peek(n);
          return {rejected, ok: p.ok, loaded: p.loaded, first: p.value[0].name};
        }""",
        name,
    )
    assert res == {"rejected": True, "ok": False, "loaded": True, "first": first}
    page.unroute(f"**/api/{name}", fail)


@pytest.mark.parametrize("name", COLLECTIONS)
def test_invalidate_mid_flight_then_get_issues_a_second_request(
    app_with_agent: SeededApp, page: Page, name: str
) -> None:
    _seed_library(app_with_agent)
    _ready(page, app_with_agent.base_url)
    held: list = []
    calls: list[int] = []

    def handler(route) -> None:
        path, query = _list_path(route.request.url)
        if route.request.method != "GET" or not path.endswith(f"/api/{name}") or query:
            route.continue_()
            return
        calls.append(1)
        if len(calls) == 1:
            held.append(route)
        else:
            route.continue_()

    page.route(f"**/api/{name}", handler)
    page.evaluate("n => { window.__p1 = App.store.get(n, {force: true}); }", name)
    page.wait_for_function("() => true")
    assert len(held) == 1
    second = page.evaluate(
        "async n => { App.store.invalidate(n); return (await App.store.get(n)).length; }", name
    )
    assert second == 1
    assert len(calls) == 2, "a get after invalidate must not join the stale request"
    held[0].fulfill(status=200, content_type="application/json", body="[]")
    assert page.evaluate("async () => (await window.__p1).length") == 0
    assert page.evaluate("n => App.store.peek(n).value.length", name) == 1
    page.unroute(f"**/api/{name}", handler)


@pytest.mark.parametrize("name", COLLECTIONS)
def test_subscribers_are_notified(app_with_agent: SeededApp, page: Page, name: str) -> None:
    _seed_library(app_with_agent)
    _ready(page, app_with_agent.base_url)
    res = page.evaluate(
        """async (n) => {
          const events = [];
          const off = App.store.subscribe(n, v => events.push(v.length));
          await App.store.get(n, {force: true});
          await App.store.get(n, {force: true});
          off();
          await App.store.get(n, {force: true});
          return events;
        }""",
        name,
    )
    assert res == [1, 1]


# ── AC3 -- request counts per activation ─────────────────────────────────


def _go(page: Page, route: str) -> None:
    """An in-app intent navigation (what a Library row or Back does)."""
    page.evaluate("r => App.router.go(r)", "#" + route)
    _nav.expect_route(page, route)
    _nav.wait_settled(page)


def _rail(page: Page, dest: str) -> None:
    _nav.open_destination(page, dest)
    expect(_nav.destination_panel(page, dest)).to_be_visible(timeout=8000)
    _nav.wait_settled(page)


def _reload_at(page: Page, route: str) -> None:
    """A cold boot at *route*: reload the document (the hash is already there)."""
    page.reload()
    _nav.wait_settled(page)
    _nav.expect_route(page, route)


def _measure(page: Page, base: str) -> dict[str, tuple[int, int, int, int]]:
    """(providers, knowledge-bases, mcp-sources plain, connectors) GETs per step."""
    counter = _Counter(page)
    out: dict[str, tuple[int, int, int, int]] = {}

    def step(label: str, action, before=None) -> None:
        if before is not None:
            before()  # setup, not counted
        counter.reset()
        action()
        out[label] = counter.snapshot()

    _ready(page, base, "chats")
    step("Chats -> Library (first Studio activation, Knowledge)", lambda: _rail(page, "library"))
    step("Knowledge -> MCP (first)", lambda: _go(page, "library/mcp"))
    step("MCP -> Connectors (first)", lambda: _go(page, "library/connectors"))
    step("Connectors -> Knowledge (re-activation)", lambda: _go(page, "library/knowledge"))
    step("Knowledge -> MCP (re-activation)", lambda: _go(page, "library/mcp"))
    step("MCP -> Connectors (re-activation)", lambda: _go(page, "library/connectors"))
    # Studio re-activation, landing on the section Studio was last showing.
    for section in ("knowledge", "mcp", "connectors"):
        step(
            f"Chats -> Library/{section} (Studio re-activation, same section)",
            lambda s=section: _go(page, f"library/{s}"),
            before=lambda s=section: (_go(page, f"library/{s}"), _rail(page, "chats")),
        )
    # ...and on a different section than the one Studio was last showing.
    for last, section in (("connectors", "knowledge"), ("knowledge", "mcp"), ("mcp", "connectors")):
        step(
            f"Chats -> Library/{section} (Studio re-activation, last on {last})",
            lambda s=section: _go(page, f"library/{s}"),
            before=lambda la=last: (_go(page, f"library/{la}"), _rail(page, "chats")),
        )
    step(
        "Agents -> Library/knowledge (Studio already active)",
        lambda: _go(page, "library/knowledge"),
        before=lambda: _rail(page, "agents"),
    )
    for section in ("knowledge", "mcp", "connectors"):
        step(
            f"Cold boot library/{section}",
            lambda s=section: _reload_at(page, f"library/{s}"),
            before=lambda s=section: _go(page, f"library/{s}"),
        )
    return out


# The Library list's fetch policy (M25 F3 L4a, design review H3; DD9's
# freshness bound), as (providers, knowledge-bases, mcp-sources plain,
# connectors) GETs per step (providers joined as the first group in sortie 02):
#   - pane creation (entering Library from Chats or Agents, a cold boot onto a
#     Library route) force-gets the four: (1, 1, 1, 1);
#   - studio activate on a Library route (the pane survived the trip to Chats)
#     force-gets the four: (1, 1, 1, 1);
#   - a move between Library sections fetches nothing: (0, 0, 0, 0).
# Leg 2's per-section loads (each section fetched its own list on its first
# move, e.g. "Knowledge -> MCP (first)" was (0, 1, 0)) are gone: the one list
# holds all the groups.
PANE = (1, 1, 1, 1)
MOVE = (0, 0, 0, 0)
EXPECTED: dict[str, tuple[int, int, int, int]] = {
    "Chats -> Library (first Studio activation, Knowledge)": PANE,
    "Knowledge -> MCP (first)": MOVE,
    "MCP -> Connectors (first)": MOVE,
    "Connectors -> Knowledge (re-activation)": MOVE,
    "Knowledge -> MCP (re-activation)": MOVE,
    "MCP -> Connectors (re-activation)": MOVE,
    "Chats -> Library/knowledge (Studio re-activation, same section)": PANE,
    "Chats -> Library/mcp (Studio re-activation, same section)": PANE,
    "Chats -> Library/connectors (Studio re-activation, same section)": PANE,
    "Chats -> Library/knowledge (Studio re-activation, last on connectors)": PANE,
    "Chats -> Library/mcp (Studio re-activation, last on knowledge)": PANE,
    "Chats -> Library/connectors (Studio re-activation, last on mcp)": PANE,
    "Agents -> Library/knowledge (Studio already active)": PANE,
    "Cold boot library/knowledge": PANE,
    "Cold boot library/mcp": PANE,
    "Cold boot library/connectors": PANE,
}


def test_library_list_request_counts(app_with_agent: SeededApp, page: Page) -> None:
    """At most one request per collection per step, exactly the policy above,
    and none at all on a move between Library sections."""
    _seed_library(app_with_agent)
    got = _measure(page, app_with_agent.base_url)
    for label, counts in got.items():
        print(
            f"COUNTS | {label} | providers={counts[0]} kb={counts[1]} "
            f"mcp={counts[2]} conn={counts[3]}"
        )
    assert set(got) == set(EXPECTED)
    assert len(got) == 16
    for label, counts in got.items():
        assert all(n <= 1 for n in counts), f"duplicate list request in one step: {label} {counts}"
        assert counts == EXPECTED[label], f"{label}: {counts} != {EXPECTED[label]}"
    # Every move between Library sections is free (the pane and its data stay).
    for label in (
        "Knowledge -> MCP (first)",
        "MCP -> Connectors (first)",
        "Connectors -> Knowledge (re-activation)",
        "Knowledge -> MCP (re-activation)",
        "MCP -> Connectors (re-activation)",
    ):
        assert got[label] == MOVE, (label, got[label])


# ── AC2 -- invalidation map, through the UI ──────────────────────────────

# Records every App.store.invalidate(name): a grid's forced refetch would make
# the next get fresh even without the mutation's invalidation, so each test
# also asserts the call itself.
SPY = """
() => {
  window.__inv = [];
  const orig = App.store.invalidate;
  App.store.invalidate = function (n) { window.__inv.push(n); return orig.apply(this, arguments); };
}
"""


def _invalidated(page: Page) -> list[str]:
    return page.evaluate("() => window.__inv.slice()")


def test_kb_create_invalidates_knowledge_bases(app_with_agent: SeededApp, page: Page) -> None:
    base = app_with_agent.base_url
    _ready(page, base, "library/knowledge")
    page.wait_for_function("() => App.store.peek('knowledge-bases').loaded")
    assert page.evaluate("() => App.store.peek('knowledge-bases').value.length") == 0
    page.evaluate(SPY)
    _lists.library_add(page, "knowledge")
    page.locator('[data-testid="kb-create-name-input"]').fill("Made In UI")
    page.locator('[data-testid="kb-create-submit-btn"]').click()
    # The row appears through reloadLibrary (M25 F3 L4a), with no page reload.
    expect(page.locator('[data-testid="knowledge-base-card"]')).to_have_count(1, timeout=8000)
    assert "knowledge-bases" in _invalidated(page)
    names = page.evaluate("async () => (await App.store.get('knowledge-bases')).map(k => k.name)")
    assert names == ["Made In UI"]


def test_kb_delete_invalidates_knowledge_bases(app_with_agent: SeededApp, page: Page) -> None:
    base = app_with_agent.base_url
    ids = _seed_library(app_with_agent)
    _ready(page, base, "library/knowledge")
    page.wait_for_function("() => App.store.peek('knowledge-bases').value.length === 1")
    _nav.set_route(page, f"library/knowledge/{_nav.seg(ids['knowledge-bases'])}")
    delete = page.locator('[data-testid="delete-knowledge-base-btn"]')
    page.evaluate(SPY)
    delete.click()
    delete.click()
    _nav.expect_route(page, "library", timeout=8000)
    assert {"knowledge-bases", "agents"} <= set(_invalidated(page))
    assert page.evaluate("async () => (await App.store.get('knowledge-bases')).length") == 0
    expect(page.locator('[data-testid="knowledge-base-card"]')).to_have_count(0)


def test_mcp_delete_invalidates_mcp_sources(app_with_agent: SeededApp, page: Page) -> None:
    base = app_with_agent.base_url
    ids = _seed_library(app_with_agent)
    _ready(page, base, "library/mcp")
    page.wait_for_function("() => App.store.peek('mcp-sources').value.length === 1")
    _nav.set_route(page, f"library/mcp/{_nav.seg(ids['mcp-sources'])}")
    delete = page.locator('[data-testid="delete-mcp-source-btn"]')
    expect(delete).to_be_visible(timeout=8000)
    page.evaluate(SPY)
    delete.click()
    delete.click()
    _nav.expect_route(page, "library", timeout=8000)
    assert {"mcp-sources", "agents"} <= set(_invalidated(page))
    assert page.evaluate("async () => (await App.store.get('mcp-sources')).length") == 0
    expect(page.locator('[data-testid="mcp-source-card"]')).to_have_count(0)


def test_connector_create_invalidates_connectors(app_with_agent: SeededApp, page: Page) -> None:
    base = app_with_agent.base_url
    _ready(page, base, "library/connectors")
    page.wait_for_function("() => App.store.peek('connectors').loaded")
    assert page.evaluate("() => App.store.peek('connectors').value.length") == 0
    page.evaluate(SPY)
    _lists.library_add(page, "connectors")
    page.locator('[data-field="name"]').fill("UI Connector")
    page.locator('[data-field="default_agent"]').select_option(app_with_agent.agent_name)
    page.locator('[data-field="enabled"]').uncheck()
    page.locator('[data-testid="save-connector-btn"]').click()
    expect(page.locator('[data-testid="delete-connector-btn"]')).to_be_visible(timeout=8000)
    assert "connectors" in _invalidated(page)
    # The save invalidated the collection (and the list reloaded through it):
    # a plain get reads the new connector.
    got = page.evaluate(
        "async () => (await App.store.get('connectors')).map(c => [c.name, c.config.default_agent])"
    )
    assert got == [["UI Connector", app_with_agent.agent_name]]


# ── AC4 -- App.usage ─────────────────────────────────────────────────────


AGENTS = [
    {"name": "a", "provider_config_id": "p1", "kb_ids": ["k1", "k2"], "mcp_source_ids": ["m1"]},
    {"name": "b", "provider_config_id": "p1", "kb_ids": ["k1"], "mcp_source_ids": []},
    {"name": "c", "provider_config_id": "p2"},  # no kb_ids / mcp_source_ids at all
    {"name": "d", "provider_config_id": None, "kb_ids": None, "mcp_source_ids": None},
]


def test_usage_agent_counts(app_with_agent: SeededApp, page: Page) -> None:
    _ready(page, app_with_agent.base_url)
    got = page.evaluate(
        """(agents) => {
          const u = App.usage;
          return {
            p1: u.providerAgents(agents, 'p1'), p2: u.providerAgents(agents, 'p2'),
            p0: u.providerAgents(agents, 'nope'),
            k1: u.kbAgents(agents, 'k1'), k2: u.kbAgents(agents, 'k2'),
            k0: u.kbAgents(agents, 'nope'),
            m1: u.mcpAgents(agents, 'm1'), m0: u.mcpAgents(agents, 'nope'),
            empty: [u.providerAgents([], 'p1'), u.kbAgents(null, 'k1'),
                    u.mcpAgents(undefined, 'm1')],
          };
        }""",
        AGENTS,
    )
    assert got == {
        "p1": 2, "p2": 1, "p0": 0,
        "k1": 2, "k2": 1, "k0": 0,
        "m1": 1, "m0": 0,
        "empty": [0, 0, 0],
    }  # fmt: skip


def test_usage_connector_agents_are_distinct(app_with_agent: SeededApp, page: Page) -> None:
    _ready(page, app_with_agent.base_url)
    got = page.evaluate(
        """() => {
          const u = App.usage;
          return {
            both: u.connectorAgents({config: {default_agent: 'a',
                                              channel_map: {'1': 'b', '2': 'a', '3': 'b'}}}),
            defaultOnly: u.connectorAgents({config: {default_agent: 'a'}}),
            mapOnly: u.connectorAgents({config: {channel_map: {'1': 'c'}}}),
            skipped: u.connectorAgents({config: {default_agent: '',
                                                 channel_map: {'1': '', '2': 7, '3': null}}}),
            neither: u.connectorAgents({config: {}}),
            noConfig: u.connectorAgents({}),
            nothing: u.connectorAgents(null),
          };
        }"""
    )
    assert got == {
        "both": ["a", "b"],
        "defaultOnly": ["a"],
        "mapOnly": ["c"],
        "skipped": [],
        "neither": [],
        "noConfig": [],
        "nothing": [],
    }


def test_usage_mcp_tool_count(app_with_agent: SeededApp, page: Page) -> None:
    _ready(page, app_with_agent.base_url)
    got = page.evaluate(
        """() => {
          const u = App.usage;
          return [
            u.mcpToolCount({config: {_cache: {tools: [{name: 'x'}, {name: 'y'}]}}}),
            u.mcpToolCount({config: {_cache: {tools: []}}}),
            u.mcpToolCount({config: {_cache: {}}}),
            u.mcpToolCount({config: {}}),
            u.mcpToolCount({}),
            u.mcpToolCount(null),
          ];
        }"""
    )
    assert got == [2, 0, None, None, None, None]


def test_usage_reads_the_live_list_shape(app_with_agent: SeededApp, page: Page) -> None:
    """The real GET /api/agents list carries the fields App.usage reads."""
    ids = _seed_library(app_with_agent)
    base, name = app_with_agent.base_url, app_with_agent.agent_name
    h = auth_headers_for(base)
    # A full-body PUT: update_agent does not merge a partial body.
    body = httpx.get(f"{base}/api/agents/{name}", headers=h, timeout=5).json()
    body.update(kb_ids=[ids["knowledge-bases"]], mcp_source_ids=[ids["mcp-sources"]])
    r = httpx.put(f"{base}/api/agents/{name}", json=body, headers=h, timeout=5)
    assert r.status_code == 200, r.text
    _ready(page, base)
    got = page.evaluate(
        """async ([pid, kb, mcp]) => {
          const agents = await App.store.get('agents', {force: true});
          const conns = await App.store.get('connectors', {force: true});
          return [App.usage.providerAgents(agents, pid), App.usage.kbAgents(agents, kb),
                  App.usage.mcpAgents(agents, mcp), App.usage.connectorAgents(conns[0])];
        }""",
        [app_with_agent.provider_id, ids["knowledge-bases"], ids["mcp-sources"]],
    )
    assert got == [1, 1, 1, [name]]
