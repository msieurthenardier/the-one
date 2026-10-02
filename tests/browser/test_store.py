"""App.store -- the shared client data layer (M25 F2 L7, DD8).

Agents and providers only.  Covers the store API in the real page (de-dup,
copies, failure handling, generation-safe invalidation, subscribe), the
request-count table for first activation of each destination, copy isolation
from Studio's own agent copies, subscription propagation into Studio's tile
grid, and the AC5 load-state gating by route.

The Library collections (``knowledge-bases``, ``mcp-sources``, ``connectors``),
their request counts and invalidation map, and ``App.usage`` (M25 F3 L2) are in
``test_store_library.py``.
"""

from __future__ import annotations

import httpx
import pytest
from browser import _lists, _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp, seed_mock_agent
from playwright.sync_api import Page, expect


def _path(url: str) -> str:
    return url.split("?")[0].split("#")[0]


def _is_list(url: str, tail: str) -> bool:
    return _path(url).endswith(tail)


def _ready(page: Page, base: str, route: str = "chats") -> None:
    _nav.goto_settled(page, base, route)
    page.wait_for_function("() => !!(window.App && App.store)")


def _counter(page: Page, tail: str) -> list[str]:
    seen: list[str] = []

    def on_request(req) -> None:
        if req.method == "GET" and _is_list(req.url, tail):
            seen.append(req.url)

    page.on("request", on_request)
    return seen


# ── AC1 -- store API ─────────────────────────────────────────────────────


@pytest.mark.browser
def test_concurrent_gets_and_force_share_one_request(app_with_agent: SeededApp, page: Page) -> None:
    _ready(page, app_with_agent.base_url)
    page.evaluate("() => App.store.invalidate('agents')")
    seen = _counter(page, "/api/agents")
    res = page.evaluate(
        """async () => {
          const ps = [App.store.get('agents'), App.store.get('agents'),
                      App.store.get('agents', {force: true})];
          const out = await Promise.all(ps);
          return out.map(a => a.length);
        }"""
    )
    assert res == [1, 1, 1]
    assert len(seen) == 1


@pytest.mark.browser
def test_cached_get_makes_no_request_and_invalidate_refetches(
    app_with_agent: SeededApp, page: Page
) -> None:
    _ready(page, app_with_agent.base_url)
    page.evaluate("() => App.store.get('agents', {force: true})")
    seen = _counter(page, "/api/agents")
    page.evaluate("() => App.store.get('agents')")
    assert len(seen) == 0
    page.evaluate("() => { App.store.invalidate('agents'); return App.store.get('agents'); }")
    assert len(seen) == 1
    page.evaluate("() => App.store.get('agents', {force: true})")
    assert len(seen) == 2


@pytest.mark.browser
def test_values_are_copies(app_with_agent: SeededApp, page: Page) -> None:
    _ready(page, app_with_agent.base_url)
    name = app_with_agent.agent_name
    got = page.evaluate(
        """async () => {
          const a = await App.store.get('agents');
          a[0].name = 'MUTATED'; a.push({name: 'x'});
          const p = App.store.peek('agents').value;
          p[0].name = 'MUTATED2';
          return App.store.peek('agents').value.map(x => x.name);
        }"""
    )
    assert got == [name]


@pytest.mark.browser
def test_failure_rejects_keeps_last_good_and_retries(app_with_agent: SeededApp, page: Page) -> None:
    _ready(page, app_with_agent.base_url)
    name = app_with_agent.agent_name
    page.evaluate("() => App.store.get('agents', {force: true})")

    def fail(route) -> None:
        if route.request.method == "GET" and _is_list(route.request.url, "/api/agents"):
            route.fulfill(status=500, content_type="text/plain", body="boom")
        else:
            route.continue_()

    page.route("**/api/agents", fail)
    res = page.evaluate(
        """async () => {
          let rejected = false;
          try { await App.store.get('agents', {force: true}); } catch (e) { rejected = true; }
          const p = App.store.peek('agents');
          return {rejected, ok: p.ok, loaded: p.loaded,
                  names: p.value.map(x => x.name), hasError: !!p.error};
        }"""
    )
    assert res == {"rejected": True, "ok": False, "loaded": True, "names": [name], "hasError": True}
    page.unroute("**/api/agents", fail)
    seen = _counter(page, "/api/agents")
    ok = page.evaluate(
        "async () => { const a = await App.store.get('agents'); "
        "return [a.length, App.store.peek('agents').ok]; }"
    )
    assert ok == [1, True]
    assert len(seen) == 1, "a failure is never cached: the next get must retry"


@pytest.mark.browser
def test_invalidate_during_flight_does_not_cache_stale_response(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    _ready(page, base)
    name = app_with_agent.agent_name
    held: list = []
    calls: list[int] = []

    def handler(route) -> None:
        if route.request.method != "GET" or not _is_list(route.request.url, "/api/agents"):
            route.continue_()
            return
        calls.append(1)
        if len(calls) == 1:
            held.append(route)  # the pre-invalidation request: held open
        else:
            route.continue_()

    page.route("**/api/agents", handler)
    page.evaluate("() => { window.__p1 = App.store.get('agents', {force: true}); }")
    page.wait_for_function("() => true")
    assert len(held) == 1
    second = page.evaluate(
        "async () => { App.store.invalidate('agents'); "
        "const a = await App.store.get('agents'); return a.map(x => x.name); }"
    )
    assert second == [name]
    assert len(calls) == 2, "a get after invalidate must not join the stale request"
    held[0].fulfill(status=200, content_type="application/json", body="[]")
    stale = page.evaluate("async () => (await window.__p1).length")
    assert stale == 0  # the original caller still resolves with what it asked for
    cached = page.evaluate("() => App.store.peek('agents').value.map(x => x.name)")
    assert cached == [name], "the stale response must not populate the cache"
    page.unroute("**/api/agents", handler)


@pytest.mark.browser
def test_subscribe_notifies_after_each_successful_load(
    app_with_agent: SeededApp, page: Page
) -> None:
    _ready(page, app_with_agent.base_url)
    res = page.evaluate(
        """async () => {
          const events = [];
          const off = App.store.subscribe('providers', v => events.push(v.length));
          await App.store.get('providers', {force: true});
          await App.store.get('providers', {force: true});
          off();
          await App.store.get('providers', {force: true});
          return events;
        }"""
    )
    assert res == [1, 1]


# ── AC2 -- request counts ────────────────────────────────────────────────


@pytest.mark.browser
def test_request_counts_per_activation(app_with_agent: SeededApp, page: Page) -> None:
    base = app_with_agent.base_url
    agents = _counter(page, "/api/agents")
    providers = _counter(page, "/api/providers")

    # Chats, cold boot.
    _nav.goto_settled(page, base, "chats")
    assert (len(agents), len(providers)) == (1, 1), (agents, providers)

    # Chats -> Agents (first Studio mount): init + activate share one read.
    agents.clear()
    providers.clear()
    _nav.open_destination(page, "agents")
    page.locator('[data-testid="agent-item"]').first.wait_for()
    _nav.wait_settled(page)
    assert (len(agents), len(providers)) == (1, 1), (agents, providers)

    # Agents <-> Library never re-activates the studio module: no re-reads.
    agents.clear()
    providers.clear()
    _nav.open_destination(page, "library")
    _nav.wait_settled(page)
    _nav.open_destination(page, "agents")
    _nav.wait_settled(page)
    assert (len(agents), len(providers)) == (0, 0), (agents, providers)

    # Agents -> Chats (re-activation): one of each.
    _nav.open_destination(page, "chats")
    _nav.wait_settled(page)
    assert (len(agents), len(providers)) == (1, 1), (agents, providers)

    # Settings -> Providers: one /api/providers.
    agents.clear()
    providers.clear()
    _nav.open_destination(page, "settings")
    page.wait_for_function(
        "() => document.querySelectorAll('.content-panel.active[data-destination=settings]').length"
    )
    _nav.wait_settled(page)
    _nav.set_route(page, "settings/providers")
    _lists.providers_table(page).wait_for()
    _nav.wait_settled(page)
    assert len(providers) <= 1, providers


@pytest.mark.browser
def test_cold_boot_agents_one_read_each(app_with_agent: SeededApp, page: Page) -> None:
    agents = _counter(page, "/api/agents")
    providers = _counter(page, "/api/providers")
    _nav.goto_settled(page, app_with_agent.base_url, "agents")
    page.locator('[data-testid="agent-item"]').first.wait_for()
    assert (len(agents), len(providers)) == (1, 1), (agents, providers)


@pytest.mark.browser
def test_cold_boot_providers_one_read(app_with_agent: SeededApp, page: Page) -> None:
    providers = _counter(page, "/api/providers")
    _nav.goto_settled(page, app_with_agent.base_url, "settings/providers")
    _lists.providers_table(page).wait_for()
    _nav.wait_settled(page)
    assert len(providers) == 1, providers


# ── AC3 -- isolation and propagation ─────────────────────────────────────


@pytest.mark.browser
def test_studio_detail_copy_does_not_leak_into_store(app_with_agent: SeededApp, page: Page) -> None:
    base, name = app_with_agent.base_url, app_with_agent.agent_name
    _nav.goto_settled(page, base, f"agents/{name}")
    page.locator('[data-testid="save-agent-btn"], .save-btn').first.wait_for(state="attached")
    _nav.wait_settled(page)
    shapes = page.evaluate("() => App.store.peek('agents').value.map(a => 'kb_tool_names' in a)")
    assert shapes == [False], "detail-shaped agents must never be written back to the store"


@pytest.mark.browser
def test_external_store_load_repaints_agents_list_via_subscription(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    _nav.goto_settled(page, base, "agents")
    expect(page.locator('[data-testid="agent-item"]')).to_have_count(1)
    seed_mock_agent(base, app_with_agent.provider_id, name="second-agent")
    # A load Studio did not initiate (as Chats activation / Library would).
    page.evaluate("() => { App.store.invalidate('agents'); return App.store.get('agents'); }")
    expect(page.locator('[data-testid="agent-item"]')).to_have_count(2)


@pytest.mark.browser
def test_external_store_load_repaints_the_list_beside_an_open_agent(
    app_with_agent: SeededApp, page: Page
) -> None:
    """M25 F3 L3: the agents list sits beside the editor, so the subscription
    repaints it even while an agent is open (it used to skip that case), and
    the open agent's row stays selected."""
    base, name = app_with_agent.base_url, app_with_agent.agent_name
    _nav.goto_settled(page, base, f"agents/{name}/general")
    expect(page.locator(".editor-title")).to_have_text(name, timeout=8000)
    seed_mock_agent(base, app_with_agent.provider_id, name="second-agent")
    page.evaluate("() => { App.store.invalidate('agents'); return App.store.get('agents'); }")
    expect(page.locator('[data-testid="agent-item"]')).to_have_count(2)
    _lists.expect_selected(page, "agents", name)
    expect(page.locator(".editor-title")).to_have_text(name)


@pytest.mark.browser
def test_agent_save_invalidates_store(app_with_agent: SeededApp, page: Page) -> None:
    base, name = app_with_agent.base_url, app_with_agent.agent_name
    _nav.goto_settled(page, base, f"agents/{name}")
    page.locator('[data-field="description"]').first.wait_for()
    page.locator('[data-field="description"]').first.fill("saved via ui")
    seen = _counter(page, "/api/agents")
    page.locator('[data-testid="save-agent-btn"]').click()
    page.wait_for_function(
        "() => App.store.peek('agents').value.some(a => a.description === 'saved via ui')"
    )
    assert len(seen) >= 1
    # Chats reflects the saved value on activation.
    _nav.open_destination(page, "chats")
    _nav.wait_settled(page)
    desc = page.evaluate("() => App.store.peek('agents').value[0].description")
    assert desc == "saved via ui"


# ── AC4 -- invalidation map (spy on App.store.invalidate) ────────────────


SPY = """
() => {
  window.__inv = [];
  const orig = App.store.invalidate;
  App.store.invalidate = function (n) { window.__inv.push(n); return orig.apply(this, arguments); };
}
"""


@pytest.mark.browser
def test_agent_create_and_delete_invalidate_agents(
    app_with_provider: SeededApp, page: Page
) -> None:
    base = app_with_provider.base_url
    _nav.goto_settled(page, base, "agents")
    page.evaluate(SPY)
    page.locator('[data-testid="new-agent-btn"]').click()
    page.locator('[data-field="name"]').first.fill("made-in-ui")
    expect(page.locator('#studio-model option[value="mock-default"]')).to_be_attached()
    page.locator("#studio-model").select_option("mock-default")
    page.locator('[data-field="system_prompt"]').fill("You are a test agent.")
    page.locator('[data-testid="save-agent-btn"]').click()
    page.wait_for_function("() => window.__inv.indexOf('agents') >= 0")
    page.wait_for_function(
        "() => App.store.peek('agents').value.some(a => a.name === 'made-in-ui')"
    )
    page.evaluate("() => { window.__inv = []; }")
    delete = page.locator('[data-testid="delete-agent-btn"]')
    delete.click()
    delete.click()
    page.wait_for_function("() => window.__inv.indexOf('agents') >= 0")
    page.wait_for_function(
        "() => !App.store.peek('agents').value.some(a => a.name === 'made-in-ui')"
    )


@pytest.mark.browser
def test_provider_save_and_delete_invalidate_providers(
    app_with_provider: SeededApp, page: Page
) -> None:
    base = app_with_provider.base_url
    _nav.goto_settled(page, base, f"settings/providers/{app_with_provider.provider_id}")
    page.locator('[data-testid="save-provider-btn"], .save-btn').first.wait_for()
    page.evaluate(SPY)
    page.locator('[data-field="name"]').first.fill("renamed-provider")
    page.locator('[data-testid="save-provider-btn"], .save-btn').first.click()
    page.wait_for_function("() => window.__inv.indexOf('providers') >= 0")
    names = page.evaluate("async () => (await App.store.get('providers')).map(p => p.name)")
    assert names == ["renamed-provider"], "the next read after a save must be fresh"


@pytest.mark.browser
def test_kb_rename_and_delete_invalidate_agents(app_with_provider: SeededApp, page: Page) -> None:
    base = app_with_provider.base_url
    h = auth_headers_for(base)
    kb = httpx.post(f"{base}/api/knowledge-bases", json={"name": "kb-one"}, headers=h, timeout=5)
    assert kb.status_code in (200, 201), kb.text
    kb_id = kb.json()["id"]
    _nav.goto_settled(page, base, f"library/knowledge/{kb_id}")
    page.evaluate(SPY)
    page.locator('[data-testid="kb-name-input"]').fill("kb-renamed")
    page.locator('[data-testid="save-knowledge-btn"]').click()
    page.wait_for_function("() => window.__inv.indexOf('agents') >= 0")
    page.evaluate("() => { window.__inv = []; }")
    delete = page.locator('[data-testid="delete-knowledge-base-btn"]')
    delete.click()
    delete.click()
    page.wait_for_function("() => window.__inv.indexOf('agents') >= 0")
