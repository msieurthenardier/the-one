"""Router leave-guard, section-root and leak-regression tests (M25 F2 L3,
AC8, AC9, AC13).

Router contract tests: literal hashes are allowed here (the migration guard
exempts ``tests/browser/test_router_*.py`` at file level).

The leave guard (``App.nav``, leg 5): the router consults it on EVERY ``go()``
(unless bypassed) and on every traversal. The in-area section-nav / category
gates are gone, so a dirty editor prompts exactly once on any path; a Continue
resets the dirty mirror so no phantom prompt follows it.

M25 F3 L4a: the Library section nav is retired (the grouped Library list
replaces it), so the Library "current section closes the editor" tests go to
the section root. Leg 4b retired the editors' interim Back: they go through the
item header breadcrumb's group link (``editor-breadcrumb-link``) -- the same
pushed go() to ``#library/<section>``. M25 F3 L5a: the Settings section nav is
retired too; a Settings item closes through the Settings nav's link to its page
(``_lists.settings_nav_link``), a pushed go() to ``#settings/<section>``. Leg 5b
opens Settings items below their list and retires their Back: the item headers'
"Settings / Providers" and "Settings / Built-in tools" breadcrumb links close
them too.
"""

from __future__ import annotations

import httpx
import pytest
from browser import _lists, _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp, seed_mock_agent
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

DIALOG = '[data-testid="confirm-dialog-overlay"]'
STAY = '[data-testid="modal-cancel-btn"]'
CONTINUE = '[data-testid="modal-confirm-btn"]'


def _open_dirty_agent(page: Page, app: SeededApp) -> str:
    """Open the seeded agent's editor (Agents destination) and dirty it."""
    _nav.goto_settled(page, app.base_url, "agents")
    expect(_nav.destination_panel(page, "agents")).to_be_visible(timeout=8000)
    page.locator('[data-testid="agent-item"]').first.click()
    expect(page.locator('[data-testid="tab-general"]')).to_be_visible(timeout=8000)
    route = f"agents/{_nav.seg(app.agent_name)}/general"
    _nav.expect_route(page, route)
    _dirty(page)
    return route


def _dirty(page: Page) -> None:
    desc = page.locator('[data-field="description"]')
    desc.click()
    desc.fill("dirty edit")
    expect(page.locator('[data-testid="save-agent-btn"]')).to_be_enabled()


def _studio_state(page: Page) -> dict:
    return page.evaluate(
        """() => {
          const s = App.areas.find(a => a.id === 'studio');
          return { agent: s._selectedAgent && s._selectedAgent.name, create: s._createMode,
                   mcp: s._mcpSourceFormMode, kb: s._selectedKbId, dirty: s._dirty,
                   section: s._activeSection };
        }"""
    )


def _no_second_dialog(page: Page) -> None:
    page.wait_for_timeout(400)
    expect(page.locator(DIALOG)).to_have_count(0)


# ── AC8 (a): dirty agent -> rail Library -> ONE dialog ───────────────────


def test_dirty_agent_rail_library_one_dialog(app_with_agent: SeededApp, page: Page) -> None:
    route = _open_dirty_agent(page, app_with_agent)
    _nav.open_destination(page, "library")
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)

    # Stay keeps the editor and the URL.
    page.locator(STAY).click()
    _no_second_dialog(page)
    expect(page.locator('[data-testid="tab-general"]')).to_be_visible()
    _nav.expect_route(page, route)
    assert _studio_state(page)["dirty"] is True

    # Continue lands on Library, with exactly one dialog throughout.
    _nav.open_destination(page, "library")
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(CONTINUE).click()
    _no_second_dialog(page)
    expect(_nav.destination_panel(page, "library")).to_be_visible(timeout=8000)
    _nav.expect_route(page, "library/knowledge")


# ── (b): the same flow via browser Back ─────────────────────────────────────


def test_dirty_agent_browser_back_one_dialog(app_with_agent: SeededApp, page: Page) -> None:
    _nav.goto_settled(page, app_with_agent.base_url, "library")
    expect(_nav.destination_panel(page, "library")).to_be_visible(timeout=8000)
    _nav.open_destination(page, "agents")
    expect(_nav.destination_panel(page, "agents")).to_be_visible(timeout=8000)
    page.locator('[data-testid="agent-item"]').first.click()
    expect(page.locator('[data-testid="tab-general"]')).to_be_visible(timeout=8000)
    route = _nav.current_route(page)
    _dirty(page)
    seq = page.evaluate("history.state.seq")

    page.go_back()
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(STAY).click()
    _no_second_dialog(page)
    # Stay reverted the traversal: same entry, editor intact, URL unchanged.
    page.wait_for_function("seq => history.state && history.state.seq === seq", arg=seq)
    _nav.expect_route(page, route)
    expect(page.locator('[data-testid="tab-general"]')).to_be_visible()

    page.go_back()
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(CONTINUE).click()
    _no_second_dialog(page)
    # Item opens push (leg 04): the entry before the agent is the Agents root,
    # not the previous destination. The editor closed, the dirty flag was reset.
    _nav.expect_route(page, "agents")
    expect(page.locator('[data-testid="tab-general"]')).to_have_count(0)
    page.go_back()
    expect(_nav.destination_panel(page, "library")).to_be_visible(timeout=8000)
    _nav.expect_route(page, "library/knowledge")


# ── (c): hash change to another agent while dirty -> Continue -> no 2nd dialog


def test_hash_change_to_other_agent_continue_has_no_second_dialog(
    app_with_agent: SeededApp, page: Page
) -> None:
    seed_mock_agent(app_with_agent.base_url, app_with_agent.provider_id, name="second-agent")
    _nav.goto_settled(page, app_with_agent.base_url, "agents")
    expect(_nav.destination_panel(page, "agents")).to_be_visible(timeout=8000)
    page.locator('[data-testid="agent-item"]').first.click()
    expect(page.locator('[data-testid="tab-general"]')).to_be_visible(timeout=8000)
    current = page.locator(".editor-title").inner_text()
    other = "test-agent" if current == "second-agent" else "second-agent"
    _dirty(page)

    _nav.set_route(page, f"agents/{_nav.seg(other)}/general")
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(CONTINUE).click()
    _no_second_dialog(page)
    expect(page.locator(".editor-title")).to_have_text(other, timeout=8000)
    _nav.expect_route(page, f"agents/{_nav.seg(other)}/general")
    assert _studio_state(page)["dirty"] is False


# ── (d): dirty agent -> Settings -> Continue -> back to the agent: no phantom


def test_dirty_agent_settings_continue_then_restore_has_no_phantom_dialog(
    app_with_agent: SeededApp, page: Page
) -> None:
    route = _open_dirty_agent(page, app_with_agent)
    _nav.open_destination(page, "settings")
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(CONTINUE).click()
    expect(_nav.destination_panel(page, "settings")).to_be_visible(timeout=8000)
    _no_second_dialog(page)

    # Back to the agent via the restore route (the Agents button -> lastRoute).
    _nav.open_destination(page, "agents")
    expect(_nav.destination_panel(page, "agents")).to_be_visible(timeout=8000)
    expect(page.locator('[data-testid="tab-general"]')).to_be_visible(timeout=8000)
    _nav.expect_route(page, route)
    _no_second_dialog(page)
    # The restore re-opened the agent fresh from the server: the abandoned edit
    # is gone and nothing is dirty.
    expect(page.locator('[data-field="description"]')).not_to_have_value("dirty edit")
    assert _studio_state(page)["dirty"] is False

    # ...and leaving again is silent (no phantom prompt).
    _nav.open_destination(page, "settings")
    expect(_nav.destination_panel(page, "settings")).to_be_visible(timeout=8000)
    _no_second_dialog(page)


# ── (e): a click on the current section / destination root while dirty ──────


def test_current_destination_click_while_dirty_one_dialog_continue_closes_editor(
    app_with_agent: SeededApp, page: Page
) -> None:
    _open_dirty_agent(page, app_with_agent)
    _nav.open_destination(page, "agents")  # the CURRENT destination -> its root
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(STAY).click()
    _no_second_dialog(page)
    expect(page.locator('[data-testid="tab-general"]')).to_be_visible()

    _nav.open_destination(page, "agents")
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(CONTINUE).click()
    _no_second_dialog(page)
    # Continue closed the editor (same-section close preserved).
    expect(page.locator(".studio-editor")).to_have_class("studio-editor is-hidden", timeout=5000)
    expect(page.locator('[data-testid="agent-item"]').first).to_be_visible()
    _nav.expect_route(page, "agents")
    st = _studio_state(page)
    assert st["agent"] is None and st["dirty"] is False


def test_current_section_click_while_dirty_one_dialog_continue_closes_editor(
    app_clean: str, page: Page
) -> None:
    """Library: a dirty MCP create form, then a go() to the MCP section root
    through the breadcrumb's group link (M25 F3 L4b; Back is retired)."""
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    name = page.locator('[data-field="name"]')
    expect(name).to_be_visible(timeout=8000)
    name.fill("dirty-source")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_enabled()

    _lists.close_item(page)
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(STAY).click()
    _no_second_dialog(page)
    expect(name).to_have_value("dirty-source")

    _lists.close_item(page)
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(CONTINUE).click()
    _no_second_dialog(page)
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_have_count(0, timeout=5000)
    _nav.expect_route(page, "library/mcp")
    assert _studio_state(page)["mcp"] is None


# ── (f): the root-route variant of (d) ──────────────────────────────────────


def test_dirty_agent_settings_continue_then_root_then_tile_has_no_dialog(
    app_with_agent: SeededApp, page: Page
) -> None:
    _open_dirty_agent(page, app_with_agent)
    _nav.open_destination(page, "settings")
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(CONTINUE).click()
    expect(_nav.destination_panel(page, "settings")).to_be_visible(timeout=8000)

    _nav.set_route(page, "agents")  # the Agents ROOT, not the restore route
    expect(_nav.destination_panel(page, "agents")).to_be_visible(timeout=8000)
    page.locator('[data-testid="agent-item"]').first.click()
    expect(page.locator('[data-testid="tab-general"]')).to_be_visible(timeout=8000)
    _no_second_dialog(page)


# ── (g): a dirty agent CREATE form -> Settings -> one dialog ────────────────


def test_dirty_agent_create_form_prompts_on_leaving(app_with_agent: SeededApp, page: Page) -> None:
    _nav.goto_settled(page, app_with_agent.base_url, "agents")
    expect(_nav.destination_panel(page, "agents")).to_be_visible(timeout=8000)
    page.locator('[data-testid="new-agent-btn"]').first.click()
    name = page.locator('[data-field="name"]')
    expect(name).to_be_visible(timeout=8000)
    name.fill("half-made-agent")
    expect(page.locator('[data-testid="save-agent-btn"]')).to_be_enabled()

    _nav.open_destination(page, "settings")
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(STAY).click()
    _no_second_dialog(page)
    expect(name).to_have_value("half-made-agent")

    _nav.open_destination(page, "settings")
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(CONTINUE).click()
    _no_second_dialog(page)
    expect(_nav.destination_panel(page, "settings")).to_be_visible(timeout=8000)


# ── (i): clean same-section re-click closes the open item ───────────────────
# Library items close through the item header breadcrumb's group link (M25 F3
# L4b retired Back); Settings items through the Settings nav's link to their
# page (M25 F3 L5a; leg 5b adds their breadcrumbs).


def _post(base: str, path: str, payload: dict) -> dict:
    r = httpx.post(base + path, json=payload, headers=auth_headers_for(base), timeout=5.0)
    assert r.status_code in (200, 201), f"{path}: {r.status_code} {r.text}"
    return r.json()


def test_clean_reclick_closes_mcp_editor(app_clean: str, page: Page) -> None:
    sid = _post(
        app_clean,
        "/api/mcp-sources",
        {"name": "reclick", "type": "stdio", "config": {"command": "x", "env": {}}},
    )["id"]
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)
    _lists.close_item(page)
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_have_count(0, timeout=5000)
    expect(_lists.library_empty_state(page, "mcp")).to_be_visible()
    _nav.expect_route(page, "library/mcp")
    expect(page.locator(DIALOG)).to_have_count(0)


def test_clean_reclick_closes_connector_editor(app_clean: str, page: Page) -> None:
    _nav.goto_settled(page, app_clean, "library/connectors")
    _lists.library_add(page, "connectors")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(timeout=8000)
    _lists.close_item(page)
    expect(page.locator('[data-testid="save-connector-btn"]')).to_have_count(0, timeout=5000)
    expect(_lists.library_empty_state(page, "connectors")).to_be_visible()
    _nav.expect_route(page, "library/connectors")
    expect(page.locator(DIALOG)).to_have_count(0)
    assert page.evaluate("App.areas.find(a => a.id === 'studio')._dirty") is False


def test_clean_reclick_closes_kb_detail(app_clean: str, page: Page) -> None:
    kb = _post(app_clean, "/api/knowledge-bases", {"name": "Reclick KB"})
    _nav.goto_settled(page, app_clean, f"library/knowledge/{_nav.seg(kb['id'])}")
    expect(page.locator('[data-testid="save-knowledge-btn"]')).to_be_visible(timeout=8000)
    _lists.close_item(page)
    expect(page.locator('[data-testid="save-knowledge-btn"]')).to_have_count(0, timeout=5000)
    expect(_lists.library_empty_state(page, "knowledge")).to_be_visible()
    _nav.expect_route(page, "library/knowledge")
    assert _studio_state(page)["kb"] is None


def test_clean_reclick_closes_provider_editor(app_with_provider: SeededApp, page: Page) -> None:
    _nav.goto_settled(
        page,
        app_with_provider.base_url,
        f"settings/providers/{_nav.seg(app_with_provider.provider_id)}",
    )
    expect(page.locator("#pf-name")).to_be_visible(timeout=8000)
    _lists.settings_nav_link(page, "providers").click()
    expect(page.locator("#pf-name")).to_have_count(0, timeout=5000)
    expect(page.locator(".page-title")).to_have_text("Providers")
    _nav.expect_route(page, "settings/providers")
    expect(page.locator(DIALOG)).to_have_count(0)
    # The table stays; nothing is selected any more (M25 F3 leg 5b).
    _lists.expect_none_selected(page, "settings/providers")


def test_clean_reclick_closes_tool_editor(app_clean: str, page: Page) -> None:
    _nav.goto_settled(page, app_clean, "settings/tools/web_search")
    expect(page.locator('[data-testid="save-tool-btn"]')).to_be_visible(timeout=8000)
    _lists.settings_nav_link(page, "tools").click()
    expect(page.locator('[data-testid="save-tool-btn"]')).to_have_count(0, timeout=5000)
    _nav.expect_route(page, "settings/tools")
    expect(page.locator(DIALOG)).to_have_count(0)
    _lists.expect_none_selected(page, "settings/tools")


def test_clean_breadcrumb_closes_provider_and_tool_editors(
    app_with_provider: SeededApp, page: Page
) -> None:
    """M25 F3 leg 5b: the Settings item headers' breadcrumb links close the
    item to the page root like the Library ones (no dialog when clean)."""
    _nav.goto_settled(
        page,
        app_with_provider.base_url,
        f"settings/providers/{_nav.seg(app_with_provider.provider_id)}",
    )
    expect(_lists.breadcrumb_link(page)).to_have_text("Providers", timeout=8000)
    _lists.close_item(page)
    expect(page.locator("#pf-name")).to_have_count(0, timeout=5000)
    _nav.expect_route(page, "settings/providers")
    expect(page.locator(DIALOG)).to_have_count(0)
    _nav.goto_settled(page, app_with_provider.base_url, "settings/tools/web_search")
    expect(_lists.breadcrumb_link(page)).to_have_text("Built-in tools", timeout=8000)
    _lists.close_item(page)
    expect(page.locator('[data-testid="save-tool-btn"]')).to_have_count(0, timeout=5000)
    _nav.expect_route(page, "settings/tools")
    expect(page.locator(DIALOG)).to_have_count(0)


# ── AC9: the Agents <-> Library leak regression ─────────────────────────────


def test_agents_library_chats_library_does_not_leak_agent_state(
    app_with_agent: SeededApp, page: Page
) -> None:
    _nav.goto_settled(page, app_with_agent.base_url, "agents")
    expect(_nav.destination_panel(page, "agents")).to_be_visible(timeout=8000)
    page.locator('[data-testid="agent-item"]').first.click()
    expect(page.locator('[data-testid="tab-general"]')).to_be_visible(timeout=8000)
    _dirty(page)  # an open, DIRTY item: the worst case for a leak

    item_gets: list[str] = []
    page.on(
        "request",
        lambda r: (
            item_gets.append(r.url) if r.method == "GET" and "/api/agents/" in r.url else None
        ),
    )

    _nav.open_destination(page, "library")
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(CONTINUE).click()
    expect(_nav.destination_panel(page, "library")).to_be_visible(timeout=8000)
    _nav.open_destination(page, "chats")
    expect(_nav.destination_panel(page, "chats")).to_be_visible(timeout=8000)
    _nav.open_destination(page, "library")
    expect(_nav.destination_panel(page, "library")).to_be_visible(timeout=8000)
    page.wait_for_timeout(800)  # let any late _refresh / loadAll settle

    st = _studio_state(page)
    assert st["agent"] is None, st
    assert st["mcp"] is None, st
    assert st["dirty"] is False, st
    assert st["section"] == "knowledge", st
    assert item_gets == [], f"an agent item was re-fetched: {item_gets}"
    expect(page.locator(DIALOG)).to_have_count(0)
    expect(_lists.library_empty_state(page, "knowledge")).to_be_visible()
    _nav.expect_route(page, "library/knowledge")


def test_restore_to_deleted_item_heals_the_url(app_clean: str, page: Page) -> None:
    """Restoring lastRoute(library) to a knowledge base deleted meanwhile does
    not hang: the item route falls back to the section root and the URL heals."""
    kb = _post(app_clean, "/api/knowledge-bases", {"name": "Doomed KB"})
    _nav.goto_settled(page, app_clean, f"library/knowledge/{_nav.seg(kb['id'])}")
    expect(page.locator('[data-testid="save-knowledge-btn"]')).to_be_visible(timeout=8000)
    _nav.open_destination(page, "settings")
    expect(_nav.destination_panel(page, "settings")).to_be_visible(timeout=8000)

    r = httpx.delete(
        f"{app_clean}/api/knowledge-bases/{kb['id']}",
        headers=auth_headers_for(app_clean),
        timeout=5.0,
    )
    assert r.status_code in (200, 204), r.text

    _nav.open_destination(page, "library")  # restores the dead item route
    expect(_lists.library_empty_state(page, "knowledge")).to_be_visible(timeout=8000)
    _nav.expect_route(page, "library/knowledge")
    expect(page.locator('[data-testid="save-knowledge-btn"]')).to_have_count(0)
