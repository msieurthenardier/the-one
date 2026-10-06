"""Item history, exact rendering, dead ids and one-dialog-per-intent (M25 F2 L4).

Router contract tests: literal hashes are allowed here (the migration guard
exempts ``tests/browser/test_router_*.py`` at file level).

What this file pins (leg 04, ``item-history-and-exact-rendering``):

* AC2  item opens PUSH history (agent tile, provider/MCP/KB rows); tab switches
       and MCP focus changes REPLACE.
* AC3  a section-root route renders exactly the root: a clean close (an item
       header breadcrumb's root link: M25 F3 L4b retired the Library Backs and
       L5b the Settings ones) closes the editor and resets ``dirty``; an agent
       create form is closed by a section-root ``go()``; dirty prompts once.
* AC4  an intent ``go()`` to an item consumes the cached list: no list refetch,
       no list re-render, no empty/"Loading" flash of the list (since M25 F3
       the lists stay beside, or above, the open item).
* AC5  a dead id (traversal, ``fresh: true``) heals to the section root.
* AC5b exactly ONE dialog per converted intent when dirty; Continue proceeds
       without a second prompt.
* AC6  the Chats session row pushes and joins exactly once.
* AC7  in-app links use new-scheme hrefs; ``#agents/x/mcps/s2`` while on s1
       focuses s2; ``mcps-tab.js`` owns no ``hashchange`` listener.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import httpx
import pytest
from browser import _lists, _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp, seed_mock_agent, seed_mock_provider
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

DIALOG = '[data-testid="confirm-dialog-overlay"]'
STAY = '[data-testid="modal-cancel-btn"]'
CONTINUE = '[data-testid="modal-confirm-btn"]'

STATIC_JS = Path(__file__).resolve().parents[2] / "the_one/interfaces/web/static/js"


# ── helpers ─────────────────────────────────────────────────────────────────


def _post(base: str, path: str, payload: dict) -> dict:
    r = httpx.post(base + path, json=payload, headers=auth_headers_for(base), timeout=5.0)
    assert r.status_code in (200, 201), f"{path}: {r.status_code} {r.text}"
    return r.json()


def _delete(base: str, path: str) -> None:
    r = httpx.delete(base + path, headers=auth_headers_for(base), timeout=5.0)
    assert r.status_code in (200, 204), f"DELETE {path}: {r.status_code} {r.text}"


def _go(page: Page, route: str) -> None:
    """An intent ``App.router.go`` (block body: a held promise would hang evaluate)."""
    page.evaluate("(r) => { App.router.go('#' + r); }", route)


def _area(page: Page, area_id: str, expr: str):
    return page.evaluate(
        f"() => {{ const a = App.areas.find(x => x.id === '{area_id}'); return {expr}; }}"
    )


def _wait_area_none(page: Page, area_id: str, expr: str, timeout: float = 8000) -> None:
    """State-driven wait for an area field to become null/undefined (no fixed sleep)."""
    page.wait_for_function(
        f"() => {{ const a = App.areas.find(x => x.id === '{area_id}'); "
        f"const v = {expr}; return v === null || v === undefined; }}",
        timeout=timeout,
    )


def _wait_area_false(page: Page, area_id: str, expr: str, timeout: float = 8000) -> None:
    """State-driven wait for an area flag to become falsy."""
    page.wait_for_function(
        f"() => {{ const a = App.areas.find(x => x.id === '{area_id}'); return !({expr}); }}",
        timeout=timeout,
    )


def _no_second_dialog(page: Page) -> None:
    page.wait_for_timeout(400)
    expect(page.locator(DIALOG)).to_have_count(0)


def _seq(page: Page) -> int:
    return page.evaluate("history.state && history.state.seq")


def _watch_requests(page: Page) -> list[str]:
    """Record every request path (``METHOD path``) from now on."""
    seen: list[str] = []

    def _on(req):  # noqa: ANN001
        m = re.match(r"https?://[^/]+(/[^?#]*)", req.url)
        if m:
            seen.append(f"{req.method} {m.group(1)}")

    page.on("request", _on)
    return seen


def _arm_providers_grid_watch(page: Page) -> None:
    """Flag ``window.__tableEmptied`` if the Providers grid ever loses its tiles
    (or shows a "Loading" line), and mark every current tile node so a rebuild
    is visible (``_providers_rows_kept``). M25 F3 L5b/L7: the grid stays above
    the open provider; selection is applied in place."""
    page.evaluate(
        """() => { window.__tableEmptied = false;
          const list = document.querySelector('.area-admin .settings-list');
          document.querySelectorAll('.provider-tile-grid [role="listitem"]').forEach(
            (t) => { t.__kept = true; });
          new MutationObserver(() => {
            const g = list.querySelector('.provider-tile-grid');
            if (!g || !g.querySelector('[role="listitem"]')
                || /Loading/.test(list.textContent || '')) {
              window.__tableEmptied = true;
            }
          }).observe(list, {childList: true, subtree: true}); }"""
    )


def _providers_rows_kept(page: Page) -> bool:
    return page.evaluate(
        "() => { const t = [...document.querySelectorAll("
        "'.provider-tile-grid [role=\"listitem\"]')];"
        " return t.length > 0 && t.every((n) => n.__kept === true); }"
    )


def _arm_list_emptied_observer(page: Page, testid: str) -> None:
    """Flag ``window.__listEmptied`` if the list pane's body ever loses its rows
    or hides (a list flash). Lists replace the grids (M25 F3 L3/L4a)."""
    page.evaluate(
        """(tid) => { window.__listEmptied = false;
          const body = document.querySelector(`[data-testid="${tid}"] .ui-list-pane-body`);
          new MutationObserver(() => {
            const rows = body.querySelector('.ui-list-pane-row');
            if (!rows || body.hidden) window.__listEmptied = true;
          }).observe(body, {childList: true, subtree: true, attributes: true}); }""",
        testid,
    )


def _two_agents(app: SeededApp) -> tuple[str, str]:
    other = seed_mock_agent(app.base_url, app.provider_id, name="agent-two")
    assert app.agent_name
    return app.agent_name, other


# ── AC2: item history ───────────────────────────────────────────────────────


def test_agent_items_push_and_tabs_replace(app_with_agent: SeededApp, page: Page) -> None:
    a, b = _two_agents(app_with_agent)
    _nav.goto_settled(page, app_with_agent.base_url, "agents")
    expect(_nav.destination_panel(page, "agents")).to_be_visible(timeout=8000)

    _lists.open_item(page, "agents", a)
    expect(page.locator('[data-testid="tab-general"]')).to_be_visible(timeout=8000)
    _nav.expect_route(page, f"agents/{_nav.seg(a)}/general")

    # A tab switch REPLACES: the entry count must not grow.
    seq = _seq(page)
    page.locator('[data-testid="tab-tools"]').click()
    _nav.expect_route(page, f"agents/{_nav.seg(a)}/tools")
    assert _seq(page) == seq

    # A second agent PUSHES.
    _go(page, f"agents/{_nav.seg(b)}")
    _nav.expect_route(page, f"agents/{_nav.seg(b)}/general")
    expect(page.locator(".editor-title, [data-testid='agent-editor-title']").first).to_be_visible()

    page.go_back()
    _nav.expect_route(page, f"agents/{_nav.seg(a)}/tools")
    expect(page.locator('[data-testid="tab-tools"]')).to_have_attribute("aria-selected", "true")
    page.go_back()
    _nav.expect_route(page, "agents")
    expect(page.locator('[data-testid="agent-item"]').first).to_be_visible(timeout=8000)
    expect(page.locator('[data-testid="tab-general"]')).to_have_count(0)
    expect(page.locator('[data-testid="agent-item"][aria-current="page"]')).to_have_count(0)
    _wait_area_false(page, "studio", "a._dirty")


def test_provider_items_push(app_with_provider: SeededApp, page: Page) -> None:
    base = app_with_provider.base_url
    first = app_with_provider.provider_id
    second = seed_mock_provider(base, name="second-provider")
    _nav.goto_settled(page, base, "settings/providers")
    page.locator(f'[data-testid="provider-card"][data-id="{first}"]').click()
    expect(page.locator("#pf-name")).to_be_visible(timeout=8000)
    _nav.expect_route(page, f"settings/providers/{_nav.seg(first)}")

    _go(page, f"settings/providers/{_nav.seg(second)}")
    _nav.expect_route(page, f"settings/providers/{_nav.seg(second)}")
    expect(page.locator("#pf-name")).to_have_value("second-provider", timeout=8000)

    page.go_back()
    _nav.expect_route(page, f"settings/providers/{_nav.seg(first)}")
    expect(page.locator("#pf-name")).to_have_value("mock", timeout=8000)
    page.go_back()
    _nav.expect_route(page, "settings/providers")
    expect(page.locator("#pf-name")).to_have_count(0)
    expect(page.locator('[data-testid="provider-card"]').first).to_be_visible()


def test_kb_items_push(app_clean: str, page: Page) -> None:
    k1 = _post(app_clean, "/api/knowledge-bases", {"name": "KB One"})["id"]
    k2 = _post(app_clean, "/api/knowledge-bases", {"name": "KB Two"})["id"]
    _nav.goto_settled(page, app_clean, "library/knowledge")
    _lists.open_item(page, "library/knowledge", "KB One")
    expect(page.locator('[data-testid="save-knowledge-btn"]')).to_be_visible(timeout=8000)
    _nav.expect_route(page, f"library/knowledge/{_nav.seg(k1)}")

    _go(page, f"library/knowledge/{_nav.seg(k2)}")
    _nav.expect_route(page, f"library/knowledge/{_nav.seg(k2)}")
    expect(page.locator('[data-testid="kb-name-input"]')).to_have_value("KB Two", timeout=8000)

    page.go_back()
    _nav.expect_route(page, f"library/knowledge/{_nav.seg(k1)}")
    expect(page.locator('[data-testid="kb-name-input"]')).to_have_value("KB One", timeout=8000)
    page.go_back()
    _nav.expect_route(page, "library/knowledge")
    expect(_lists.library_empty_state(page, "knowledge")).to_be_visible(timeout=8000)


def test_mcp_items_push(app_clean: str, page: Page) -> None:
    s1 = _post(
        app_clean, "/api/mcp-sources", {"name": "one", "type": "stdio", "config": {"command": "x"}}
    )["id"]
    s2 = _post(
        app_clean, "/api/mcp-sources", {"name": "two", "type": "stdio", "config": {"command": "y"}}
    )["id"]
    _nav.goto_settled(page, app_clean, "library/mcp")
    _lists.open_item(page, "library/mcp", "one")
    expect(page.locator('[data-field="name"]')).to_have_value("one", timeout=8000)
    _nav.expect_route(page, f"library/mcp/{_nav.seg(s1)}")

    _go(page, f"library/mcp/{_nav.seg(s2)}")
    _nav.expect_route(page, f"library/mcp/{_nav.seg(s2)}")
    expect(page.locator('[data-field="name"]')).to_have_value("two", timeout=8000)

    page.go_back()
    _nav.expect_route(page, f"library/mcp/{_nav.seg(s1)}")
    expect(page.locator('[data-field="name"]')).to_have_value("one", timeout=8000)
    page.go_back()
    _nav.expect_route(page, "library/mcp")
    expect(_lists.library_empty_state(page, "mcp")).to_be_visible(timeout=8000)
    expect(page.locator('[data-testid="mcp-source-card"]').first).to_be_visible(timeout=8000)


def test_tool_items_push(app_clean: str, page: Page) -> None:
    _nav.goto_settled(page, app_clean, "settings/tools")
    cards = page.locator('[data-testid="tool-card"]')
    expect(cards.first).to_be_visible(timeout=8000)
    name = cards.first.get_attribute("data-name")
    assert name
    # The tool name is the item link (M25 F3 L5b); the tile is no click target.
    _lists.open_item(page, "settings/tools", name)
    expect(page.locator(".editor-title")).to_have_text(name, timeout=8000)
    _nav.expect_route(page, f"settings/tools/{_nav.seg(name)}")
    page.go_back()
    _nav.expect_route(page, "settings/tools")
    expect(page.locator(".editor-title")).to_have_count(0)


# ── AC3: exact rendering ────────────────────────────────────────────────────


def test_provider_breadcrumb_clean_closes_editor(app_with_provider: SeededApp, page: Page) -> None:
    """Renamed from the Back-button test (M25 F3 L5b retired the Settings
    Backs): the breadcrumb's "Providers" link closes the editor; the table
    stays, and focus lands on the closed provider's row (DD8)."""
    base = app_with_provider.base_url
    _nav.goto_settled(page, base, f"settings/providers/{_nav.seg(app_with_provider.provider_id)}")
    expect(page.locator("#pf-name")).to_be_visible(timeout=8000)
    _lists.close_item(page)
    expect(page.locator("#pf-name")).to_have_count(0, timeout=8000)
    expect(page.locator('[data-testid="provider-card"]').first).to_be_visible(timeout=8000)
    _nav.expect_route(page, "settings/providers")
    _wait_area_false(page, "admin", "a._dirty")
    expect(page.locator(DIALOG)).to_have_count(0)
    expect(_lists.list_row(page, "settings/providers", "mock")).to_be_focused()
    # The close was a push: the browser Back re-opens the provider (DD4).
    page.go_back()
    expect(page.locator("#pf-name")).to_be_visible(timeout=8000)


def test_mcp_breadcrumb_clean_closes_editor(app_clean: str, page: Page) -> None:
    sid = _post(
        app_clean,
        "/api/mcp-sources",
        {"name": "close-me", "type": "stdio", "config": {"command": "x"}},
    )["id"]
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)
    _lists.close_item(page)
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_have_count(0, timeout=8000)
    # M25 F3 L4b (AC2): the breadcrumb's "MCP servers" link (Back is retired)
    # returns to the section root's empty state, beside the list.
    expect(_lists.library_empty_state(page, "mcp")).to_be_visible(timeout=8000)
    expect(page.locator('[data-testid="mcp-source-card"]').first).to_be_visible(timeout=8000)
    _nav.expect_route(page, "library/mcp")
    _wait_area_false(page, "studio", "a._dirty")
    expect(page.locator(DIALOG)).to_have_count(0)


def test_connector_editor_closed_by_breadcrumb_to_the_section_root(
    app_clean: str, page: Page
) -> None:
    """M25 F3 L4a/L4b: connectors are routed; the section nav that used to close
    the editor is retired, and so is the interim Back (leg 4b): the item header
    breadcrumb's "Connectors" link closes it (a pushed go() to
    ``#library/connectors``, the section root's empty state). (Formerly
    ``test_connector_editor_closed_by_library_connectors_section``, then
    ``test_connector_editor_closed_by_back_to_the_section_root``.)"""
    cid = _post(
        app_clean,
        "/api/connectors",
        {"name": "Closable", "type": "discord", "config": {"enabled": False}, "secrets": {}},
    )["id"]
    _nav.goto_settled(page, app_clean, "library/connectors")
    _lists.open_item(page, "library/connectors", "Closable")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(timeout=8000)
    _nav.expect_route(page, f"library/connectors/{_nav.seg(cid)}")
    _lists.close_item(page)
    expect(page.locator('[data-testid="save-connector-btn"]')).to_have_count(0, timeout=8000)
    expect(_lists.library_empty_state(page, "connectors")).to_be_visible(timeout=8000)
    _nav.expect_route(page, "library/connectors")
    _wait_area_false(page, "studio", "a._dirty")
    expect(page.locator(DIALOG)).to_have_count(0)
    # The close was a push: the browser Back re-opens the connector.
    page.go_back()
    expect(page.locator(".editor-title")).to_have_text("Closable", timeout=8000)


def test_kb_breadcrumb_clean_closes_detail(app_clean: str, page: Page) -> None:
    """M25 F3 L4a (AC3), moved onto the breadcrumb in L4b: the knowledge-base
    detail's "Knowledge bases" link returns to the section root's empty state,
    beside the list, and focus goes to the closed item's row (DD8)."""
    kb = _post(app_clean, "/api/knowledge-bases", {"name": "Closed KB"})["id"]
    _nav.goto_settled(page, app_clean, f"library/knowledge/{_nav.seg(kb)}")
    expect(page.locator('[data-testid="kb-name-input"]')).to_be_visible(timeout=8000)
    _lists.close_item(page)
    expect(_lists.library_empty_state(page, "knowledge")).to_be_visible(timeout=8000)
    _nav.expect_route(page, "library/knowledge")
    row = _lists.list_row(page, "library/knowledge", "Closed KB")
    expect(row).to_be_visible()
    expect(row).to_be_focused(timeout=8000)
    expect(page.locator(DIALOG)).to_have_count(0)


def test_agent_create_closed_by_agents_rail_link(app_with_provider: SeededApp, page: Page) -> None:
    _nav.goto_settled(page, app_with_provider.base_url, "agents")
    expect(_nav.destination_panel(page, "agents")).to_be_visible(timeout=8000)
    page.locator('[data-testid="new-agent-btn"]').first.click()
    expect(page.locator('[data-testid="save-agent-btn"]')).to_be_visible(timeout=8000)
    assert _area(page, "studio", "a._createMode") is True
    _nav.open_destination(page, "agents")  # the current destination -> its root
    expect(page.locator('[data-testid="save-agent-btn"]')).to_have_count(0, timeout=8000)
    assert _area(page, "studio", "a._createMode") is False
    _wait_area_false(page, "studio", "a._dirty")
    expect(page.locator(DIALOG)).to_have_count(0)


def test_dirty_agent_create_prompts_once_on_rail_and_continue_closes(
    app_with_provider: SeededApp, page: Page
) -> None:
    _nav.goto_settled(page, app_with_provider.base_url, "agents")
    expect(_nav.destination_panel(page, "agents")).to_be_visible(timeout=8000)
    page.locator('[data-testid="new-agent-btn"]').first.click()
    name = page.locator('[data-field="name"]')
    expect(name).to_be_visible(timeout=8000)
    name.fill("half-typed")
    _nav.open_destination(page, "agents")
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(CONTINUE).click()
    _no_second_dialog(page)
    expect(page.locator('[data-testid="save-agent-btn"]')).to_have_count(0, timeout=8000)
    assert _area(page, "studio", "a._createMode") is False
    _wait_area_false(page, "studio", "a._dirty")


def test_dirty_provider_breadcrumb_prompts_once_and_continue_closes(
    app_with_provider: SeededApp, page: Page
) -> None:
    base = app_with_provider.base_url
    _nav.goto_settled(page, base, f"settings/providers/{_nav.seg(app_with_provider.provider_id)}")
    name = page.locator("#pf-name")
    expect(name).to_be_visible(timeout=8000)
    name.fill("dirty-edit")
    expect(page.locator('[data-testid="save-provider-btn"]')).to_be_enabled()
    _lists.close_item(page)
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(STAY).click()
    _no_second_dialog(page)
    expect(page.locator("#pf-name")).to_have_value("dirty-edit")
    _lists.close_item(page)
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(CONTINUE).click()
    _no_second_dialog(page)
    expect(page.locator("#pf-name")).to_have_count(0, timeout=8000)
    _nav.expect_route(page, "settings/providers")
    _wait_area_false(page, "admin", "a._dirty")


def test_dirty_mcp_breadcrumb_prompts_once_and_continue_closes(app_clean: str, page: Page) -> None:
    sid = _post(
        app_clean,
        "/api/mcp-sources",
        {"name": "dirty-me", "type": "stdio", "config": {"command": "x"}},
    )["id"]
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    name = page.locator('[data-field="name"]')
    expect(name).to_be_visible(timeout=8000)
    name.fill("typed-name")
    _lists.close_item(page)
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(CONTINUE).click()
    _no_second_dialog(page)
    expect(_lists.library_empty_state(page, "mcp")).to_be_visible(timeout=8000)
    expect(page.locator('[data-testid="mcp-source-card"]').first).to_be_visible(timeout=8000)
    _nav.expect_route(page, "library/mcp")
    _wait_area_false(page, "studio", "a._dirty")


def test_dirty_kb_breadcrumb_prompts_once_and_continue_closes(app_clean: str, page: Page) -> None:
    kb = _post(app_clean, "/api/knowledge-bases", {"name": "Dirty KB"})["id"]
    _nav.goto_settled(page, app_clean, f"library/knowledge/{_nav.seg(kb)}")
    name = page.locator('[data-testid="kb-name-input"]')
    expect(name).to_be_visible(timeout=8000)
    name.fill("Dirty KB Edited")
    _lists.close_item(page)
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(CONTINUE).click()
    _no_second_dialog(page)
    expect(_lists.library_empty_state(page, "knowledge")).to_be_visible(timeout=8000)
    _nav.expect_route(page, "library/knowledge")
    _wait_area_false(page, "studio", "a._dirty")


def test_dirty_tool_breadcrumb_prompts_once_and_continue_closes(app_clean: str, page: Page) -> None:
    _nav.goto_settled(page, app_clean, "settings/tools/web_search")
    expect(page.locator(".editor-title")).to_have_text("web_search", timeout=8000)
    page.locator('[data-field="search_backend"]').select_option("searxng")
    expect(page.locator(".save-btn")).not_to_be_disabled()
    _lists.close_item(page)
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(CONTINUE).click()
    _no_second_dialog(page)
    expect(page.locator(".editor-title")).to_have_count(0, timeout=8000)
    _nav.expect_route(page, "settings/tools")
    _wait_area_false(page, "admin", "a._dirty")


def test_dirty_agent_rail_root_prompts_once_and_continue_closes(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Renamed from the Back-button test (M25 F3 L3 retired Back): the rail's
    current-destination link goes to the Agents root, asking once."""
    _nav.goto_settled(page, app_with_agent.base_url, "agents")
    _lists.first_row(page, "agents").click()
    desc = page.locator('[data-field="description"]')
    expect(desc).to_be_visible(timeout=8000)
    desc.fill("dirty edit")
    _nav.open_destination(page, "agents")
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(CONTINUE).click()
    _no_second_dialog(page)
    _nav.expect_route(page, "agents")
    expect(page.locator('[data-testid="tab-general"]')).to_have_count(0)
    _wait_area_false(page, "studio", "a._dirty")


def test_dirty_agent_row_click_prompts_once(app_with_agent: SeededApp, page: Page) -> None:
    """A sibling's list row while dirty (the list stays beside the editor
    since M25 F3 L3, so it is a real click) asks exactly once."""
    a, b = _two_agents(app_with_agent)
    _nav.goto_settled(page, app_with_agent.base_url, "agents")
    _lists.open_item(page, "agents", a)
    desc = page.locator('[data-field="description"]')
    expect(desc).to_be_visible(timeout=8000)
    desc.fill("dirty edit")
    _lists.list_row(page, "agents", b).click()
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(CONTINUE).click()
    _no_second_dialog(page)
    _nav.expect_route(page, f"agents/{_nav.seg(b)}/general")


def test_agent_create_route_and_connector_breadcrumb_each_ask_once(
    app_with_agent: SeededApp, page: Page
) -> None:
    """ "New" from a dirty agent asks ONCE (since M25 F3 L3 agent create is the
    `#agents/~new` route, guarded by the router, not an inline gate). Since M25
    F3 L4a the connector editor is routed too: its breadcrumb's "Connectors"
    link (L4b; it was the interim Back) is a router go(), so a dirty connector
    create form asks ONCE through the router guard (the inline dialog is gone),
    and so does the Add menu from a dirty form."""
    _nav.goto_settled(page, app_with_agent.base_url, "agents")
    _lists.first_row(page, "agents").click()
    desc = page.locator('[data-field="description"]')
    expect(desc).to_be_visible(timeout=8000)
    desc.fill("dirty edit")
    page.locator('[data-testid="new-agent-btn"]').click()
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(CONTINUE).click()
    _no_second_dialog(page)
    _nav.expect_route(page, "agents/~new")
    expect(page.locator(".editor-title")).to_have_text("New Agent", timeout=8000)
    assert _area(page, "studio", "a._createMode") is True

    _nav.goto_settled(page, app_with_agent.base_url, "library/connectors")
    _lists.library_add(page, "connectors")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(timeout=8000)
    page.locator('[data-field="name"]').first.fill("conn")
    _lists.close_item(page)
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(CONTINUE).click()
    _no_second_dialog(page)
    expect(_lists.library_empty_state(page, "connectors")).to_be_visible(timeout=5000)
    _nav.expect_route(page, "library/connectors")
    _wait_area_false(page, "studio", "a._dirty")

    # The Add menu from a dirty connector form: one router prompt, Stay keeps it.
    _lists.library_add(page, "connectors")
    page.locator('[data-field="name"]').first.fill("conn again")
    page.locator('[data-testid="library-add-btn"]').click()
    page.locator('[data-testid="library-add-knowledge"]').click()
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator('[data-testid="modal-cancel-btn"]').click()
    _no_second_dialog(page)
    _nav.expect_route(page, "library/connectors/~new")
    expect(page.locator('[data-field="name"]').first).to_have_value("conn again")


# ── AC4: no grid flash, no list refetch (intent go) ─────────────────────────


def test_agent_row_open_no_refetch_no_flash(app_with_agent: SeededApp, page: Page) -> None:
    """Opening an agent from its list row refetches no list and never empties
    the list (M25 F3 L3: the list stays beside the editor)."""
    _nav.goto_settled(page, app_with_agent.base_url, "agents")
    expect(page.locator('[data-testid="agent-item"]').first).to_be_visible(timeout=8000)
    _nav.wait_settled(page, quiet_ms=1500)
    seen = _watch_requests(page)
    page.evaluate(
        """() => { window.__listEmptied = false;
          const body = document.querySelector('[data-testid="agents-list"] .ui-list-pane-body');
          new MutationObserver(() => {
            const rows = body.querySelector('.ui-list-pane-row');
            if (!rows || body.hidden) window.__listEmptied = true;
          }).observe(body, {childList: true, subtree: true, attributes: true}); }"""
    )
    _lists.first_row(page, "agents").click()
    expect(page.locator('[data-testid="tab-general"]')).to_be_visible(timeout=8000)
    _nav.wait_settled(page)
    assert "GET /api/agents" not in seen, seen
    assert page.evaluate("window.__listEmptied") is False
    _lists.expect_selected(page, "agents", app_with_agent.agent_name)


def test_provider_open_no_refetch_no_flash(app_with_provider: SeededApp, page: Page) -> None:
    """Opening a provider from its tile's name link refetches no list and never
    rebuilds or empties the grid (M25 F3 L5b/L7: the grid stays above the
    editor; the tile is selected in place)."""
    base = app_with_provider.base_url
    _nav.goto_settled(page, base, "settings/providers")
    card = page.locator('[data-testid="provider-card"]').first
    expect(card).to_be_visible(timeout=8000)
    _nav.wait_settled(page, quiet_ms=1500)
    seen = _watch_requests(page)
    _arm_providers_grid_watch(page)
    card.click()
    expect(page.locator("#pf-name")).to_be_visible(timeout=8000)
    _nav.wait_settled(page)
    assert "GET /api/providers" not in seen, seen
    assert page.evaluate("window.__tableEmptied") is False
    assert _providers_rows_kept(page)
    _lists.expect_selected(page, "settings/providers", "mock")


def test_mcp_open_no_refetch_no_flash(app_clean: str, page: Page) -> None:
    """Opening an MCP server from its Library row refetches no list and never
    empties the list (M25 F3 L4a: the list stays beside the editor)."""
    _post(app_clean, "/api/mcp-sources", {"name": "m", "type": "stdio", "config": {"command": "x"}})
    _nav.goto_settled(page, app_clean, "library/mcp")
    row = _lists.list_row(page, "library/mcp", "m")
    expect(row).to_be_visible(timeout=8000)
    _nav.wait_settled(page, quiet_ms=1500)
    seen = _watch_requests(page)
    _arm_list_emptied_observer(page, "library-list")
    row.click()
    expect(page.locator('[data-field="name"]')).to_be_visible(timeout=8000)
    _nav.wait_settled(page)
    assert "GET /api/mcp-sources" not in seen, seen
    assert page.evaluate("window.__listEmptied") is False
    _lists.expect_selected(page, "library/mcp", "m")


def test_kb_open_no_list_refetch_no_list_flash(app_clean: str, page: Page) -> None:
    """Knowledge differs: the detail view's own status/items fetches (and its
    "Loading knowledge base" placeholder) are inherent. Only the no-flash-of-
    the-LIST part is asserted: the list is not refetched and never empties."""
    _post(app_clean, "/api/knowledge-bases", {"name": "Cached KB"})
    _nav.goto_settled(page, app_clean, "library/knowledge")
    row = _lists.list_row(page, "library/knowledge", "Cached KB")
    expect(row).to_be_visible(timeout=8000)
    _nav.wait_settled(page, quiet_ms=1500)
    seen = _watch_requests(page)
    _arm_list_emptied_observer(page, "library-list")
    row.click()
    expect(page.locator('[data-testid="kb-name-input"]')).to_be_visible(timeout=8000)
    assert "GET /api/knowledge-bases" not in seen, seen
    assert page.evaluate("window.__listEmptied") is False


# ── AC5: dead ids (traversal, fresh) ────────────────────────────────────────


def test_dead_provider_id_on_forward_heals_to_root(
    app_with_provider: SeededApp, page: Page
) -> None:
    base = app_with_provider.base_url
    doomed = _post(
        base,
        "/api/providers",
        {"name": "doomed", "type": "mock", "base_url": "", "config": {}},
    )["id"]
    _nav.goto_settled(page, base, "settings/providers")
    _go(page, f"settings/providers/{_nav.seg(doomed)}")
    expect(page.locator("#pf-name")).to_have_value("doomed", timeout=8000)
    page.go_back()
    _nav.expect_route(page, "settings/providers")
    expect(page.locator("#pf-name")).to_have_count(0)
    _delete(base, f"/api/providers/{doomed}")

    page.go_forward()
    _nav.expect_route(page, "settings/providers")
    expect(page.locator("#pf-name")).to_have_count(0)
    expect(page.locator('[data-testid="provider-card"]').first).to_be_visible(timeout=8000)
    _wait_area_none(page, "admin", "a._pendingProviderId")
    _wait_area_none(page, "admin", "a._pendingFormMode")
    _nav.expect_route(page, "settings/providers")


def test_dead_mcp_source_on_forward_heals_to_root(app_clean: str, page: Page) -> None:
    sid = _post(
        app_clean,
        "/api/mcp-sources",
        {"name": "doomed", "type": "stdio", "config": {"command": "x"}},
    )["id"]
    _post(
        app_clean, "/api/mcp-sources", {"name": "keep", "type": "stdio", "config": {"command": "y"}}
    )
    _nav.goto_settled(page, app_clean, "library/mcp")
    _go(page, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-field="name"]')).to_have_value("doomed", timeout=8000)
    page.go_back()
    _nav.expect_route(page, "library/mcp")
    _delete(app_clean, f"/api/mcp-sources/{sid}")

    page.go_forward()
    _nav.expect_route(page, "library/mcp")
    expect(page.locator('[data-testid="mcp-source-card"]').first).to_be_visible(timeout=8000)
    expect(_lists.library_empty_state(page, "mcp")).to_be_visible(timeout=8000)
    expect(page.locator('[data-field="name"]')).to_have_count(0)
    _wait_area_none(page, "studio", "a._pendingMcpSourceId")
    _wait_area_none(page, "studio", "a._pendingMcpSourceFormMode")
    _nav.expect_route(page, "library/mcp")


def test_unknown_tool_name_heals_to_tools_root(app_clean: str, page: Page) -> None:
    _nav.goto_settled(page, app_clean, "settings/tools/nope")
    _nav.expect_route(page, "settings/tools")
    expect(page.locator('[data-testid="tool-card"]').first).to_be_visible(timeout=8000)
    expect(page.locator(".editor-title")).to_have_count(0)
    _wait_area_none(page, "admin", "a._pendingToolName")


def test_dead_agent_and_kb_ids_heal_to_root(app_with_agent: SeededApp, page: Page) -> None:
    base = app_with_agent.base_url
    _nav.goto_settled(page, base, "agents/ghost/general")
    _nav.expect_route(page, "agents")
    expect(page.locator('[data-testid="agent-item"]').first).to_be_visible(timeout=8000)
    _wait_area_none(page, "studio", "a._pendingSelectName")

    _nav.goto_settled(page, base, "library/knowledge/ghost")
    _nav.expect_route(page, "library/knowledge")
    expect(_lists.library_empty_state(page, "knowledge")).to_be_visible(timeout=8000)
    _wait_area_none(page, "studio", "a._selectedKbId")


def test_dead_agent_on_empty_inventory_heals(app_with_provider: SeededApp, page: Page) -> None:
    """No agents at all: a pending id must not stay pending forever."""
    _nav.goto_settled(page, app_with_provider.base_url, "agents/ghost/general")
    _nav.expect_route(page, "agents")
    _wait_area_none(page, "studio", "a._pendingSelectName")


# ── AC6: Chats ──────────────────────────────────────────────────────────────


def test_session_row_pushes_and_joins_once(app_with_agent: SeededApp, page: Page) -> None:
    frames: list[tuple[str, str | None]] = []

    def _on_ws(ws):  # noqa: ANN001
        def _sent(payload):  # noqa: ANN001
            try:
                msg = json.loads(payload)
            except (TypeError, ValueError):
                return
            if isinstance(msg, dict) and msg.get("action") in ("join", "new_session"):
                frames.append((msg["action"], msg.get("session_id")))

        ws.on("framesent", _sent)

    page.on("websocket", _on_ws)
    page.goto(app_with_agent.base_url)
    page.locator(".chat-welcome-item").filter(has_text=app_with_agent.agent_name).click()
    expect(page.locator(".session-agent-badge")).to_have_text(
        app_with_agent.agent_name, timeout=8000
    )
    first_route = _nav.current_route(page)
    s1 = first_route.split("/", 1)[1]

    page.locator('[data-testid="new-chat-btn"]').click()
    _nav.wait_for_route_prefix(page, "chats/", not_equal=first_route, timeout=8000)
    second_route = _nav.current_route(page)
    s2 = second_route.split("/", 1)[1]
    row1 = page.locator(f'button.session-item[data-id="{s1}"]')
    row2 = page.locator(f'button.session-item[data-id="{s2}"]')
    expect(row1).to_be_visible(timeout=8000)
    expect(row2).to_be_visible(timeout=8000)
    expect(page.locator("button.session-item")).to_have_count(2)
    assert [a for a, _ in frames].count("new_session") == 2, frames

    frames.clear()
    seq = _seq(page)
    row1.click()
    _nav.expect_route(page, first_route)
    expect(row1).to_have_class(re.compile(r"\bactive\b"))
    assert _seq(page) == seq + 1  # pushed
    assert frames == [("join", s1)], frames  # exactly one join, no create

    frames.clear()
    page.go_back()
    _nav.expect_route(page, second_route)
    expect(row2).to_have_class(re.compile(r"\bactive\b"))
    assert frames == [("join", s2)], frames
    expect(page.locator("button.session-item")).to_have_count(2)


# ── AC7: links and the MCP tab ──────────────────────────────────────────────


def test_in_app_links_use_new_scheme_hrefs(app_clean: str, page: Page) -> None:
    # Welcome link (no providers, no agents).
    page.goto(app_clean)
    link = page.locator(".chat-welcome-link").first
    expect(link).to_be_visible(timeout=8000)
    hrefs = page.locator(".chat-welcome-link").evaluate_all(
        "els => els.map(e => e.getAttribute('href'))"
    )
    assert hrefs and all(h.startswith(("#settings/", "#agents")) for h in hrefs), hrefs


def test_knowledge_tab_and_mcps_tab_empty_links_use_new_scheme(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    _nav.goto_settled(page, base, f"agents/{_nav.seg(app_with_agent.agent_name)}/knowledge")
    link = page.locator('[data-testid="agent-knowledge-empty-state"] a')
    expect(link).to_have_attribute("href", "#library/knowledge", timeout=8000)
    page.locator('[data-testid="tab-mcps"]').click()
    link = page.locator('[data-testid="mcp-empty-state"] a')
    expect(link).to_have_attribute("href", "#library/mcp", timeout=8000)


def test_mcp_tab_focus_follows_the_url_for_the_same_agent(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    name = app_with_agent.agent_name
    s1 = _post(
        base, "/api/mcp-sources", {"name": "s-one", "type": "stdio", "config": {"command": "x"}}
    )["id"]
    s2 = _post(
        base, "/api/mcp-sources", {"name": "s-two", "type": "stdio", "config": {"command": "y"}}
    )["id"]
    _nav.goto_settled(page, base, f"agents/{_nav.seg(name)}/mcps/{_nav.seg(s1)}")
    row1 = page.locator(f'[data-testid="mcp-source-row-{s1}"]')
    row2 = page.locator(f'[data-testid="mcp-source-row-{s2}"]')
    expect(row1).to_have_attribute("aria-expanded", "true", timeout=8000)
    expect(row2).to_have_attribute("aria-expanded", "false")

    _go(page, f"agents/{_nav.seg(name)}/mcps/{_nav.seg(s2)}")
    expect(row2).to_have_attribute("aria-expanded", "true", timeout=8000)
    expect(row1).to_have_attribute("aria-expanded", "false")
    _nav.expect_route(page, f"agents/{_nav.seg(name)}/mcps/{_nav.seg(s2)}")


def test_mcps_tab_js_has_no_hashchange_listener_or_hash_read() -> None:
    src = (STATIC_JS / "areas/studio/mcps-tab.js").read_text()
    assert "hashchange" not in src
    assert "location.hash" not in src


_DELAY_SESSION_JOINED_JS = """
(() => {
  // Delay ``list_sessions`` 0.8s and every ``session_joined`` reply 1.5s, so the list
  // reply lands between a new-chat send and its join (the window a loaded host opens).
  const send = WebSocket.prototype.send;
  WebSocket.prototype.send = function (d) {
    try {
      if (typeof d === 'string' && JSON.parse(d).action === 'list_sessions') {
        setTimeout(() => send.call(this, d), 800);
        return;
      }
    } catch (x) { /* not JSON */ }
    return send.call(this, d);
  };
  const desc = Object.getOwnPropertyDescriptor(WebSocket.prototype, 'onmessage');
  Object.defineProperty(WebSocket.prototype, 'onmessage', {
    configurable: true,
    get() { return desc.get.call(this); },
    set(fn) {
      desc.set.call(this, typeof fn !== 'function' ? fn : (e) => {
        let held = false;
        try { held = JSON.parse(e.data).type === 'session_joined'; } catch (x) { /* ignore */ }
        if (held) setTimeout(() => fn.call(this, e), 1500); else fn.call(this, e);
      });
    },
  });
})();
"""


def test_new_chat_before_pending_session_list_creates_exactly_one_session(
    app_with_agent: SeededApp, page: Page
) -> None:
    """New chat while the post-join ``session_list`` refresh is still in flight.

    The reply lands between the new-chat send and its ``session_joined``; the list
    handler's queued-intent drain must not re-send ``new_session`` (a third session).
    """
    creates: list[str] = []

    def _on_ws(ws):  # noqa: ANN001
        def _sent(payload):  # noqa: ANN001
            try:
                msg = json.loads(payload)
            except (TypeError, ValueError):
                return
            if isinstance(msg, dict) and msg.get("action") == "new_session":
                creates.append(msg.get("agent_name"))

        ws.on("framesent", _sent)

    page.add_init_script(_DELAY_SESSION_JOINED_JS)
    page.on("websocket", _on_ws)
    page.goto(app_with_agent.base_url)
    page.locator(".chat-welcome-item").filter(has_text=app_with_agent.agent_name).click()
    expect(page.locator(".session-agent-badge")).to_have_text(
        app_with_agent.agent_name, timeout=8000
    )
    first_route = _nav.current_route(page)
    page.locator('[data-testid="new-chat-btn"]').click()
    _nav.wait_for_route_prefix(page, "chats/", not_equal=first_route, timeout=8000)
    page.wait_for_timeout(2500)  # outlast the delayed list reply and any re-send
    expect(page.locator("button.session-item")).to_have_count(2)
    assert len(creates) == 2, creates
