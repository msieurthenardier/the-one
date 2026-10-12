"""Smoke tests for ``tests/browser/_lists.py`` against today's surfaces (M25 F3 L1, DD11).

One test per destination proves ``list_row`` finds a row by its exact name and
``open_item`` opens it: the route moves to the item (connectors included, since
leg 4a gave them routes). Later legs swap the surfaces under these helpers; these
tests keep proving the helpers on each one.
Falls in the ``shared`` browser lane.
"""

from __future__ import annotations

import httpx
import pytest
from browser import _lists, _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp, seed_mock_agent, seed_mock_provider
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser


def _post(base: str, path: str, payload: dict) -> dict:
    r = httpx.post(base + path, json=payload, headers=auth_headers_for(base), timeout=5.0)
    assert r.status_code in (200, 201), f"{path}: {r.status_code} {r.text}"
    return r.json()


def test_lists_helper_unknown_list_is_rejected(app_clean: str, page: Page) -> None:
    with pytest.raises(ValueError, match="unknown list"):
        _lists.list_row(page, "library", "x")


def test_lists_helper_agents(app_with_agent: SeededApp, page: Page) -> None:
    base = app_with_agent.base_url
    seed_mock_agent(base, app_with_agent.provider_id, name="Alpha")
    seed_mock_agent(base, app_with_agent.provider_id, name="Alpha 2")
    _nav.goto_settled(page, base, "agents")
    # Exact-name match: "Alpha" never matches "Alpha 2".
    expect(_lists.list_row(page, "agents", "Alpha")).to_have_count(1, timeout=8000)
    expect(_lists.list_row(page, "agents", "Alpha 2")).to_have_count(1)
    _lists.open_item(page, "agents", "Alpha")
    _nav.expect_route(page, "agents/Alpha/general")
    _lists.expect_selected(page, "agents", "Alpha")
    # The list stays beside the open agent (leg 3): the next open goes
    # straight from one item to the other.
    expect(_lists.list_row(page, "agents", "Alpha 2")).to_be_visible(timeout=8000)
    _lists.open_item(page, "agents", "Alpha 2")
    _nav.expect_route(page, f"agents/{_nav.seg('Alpha 2')}/general")
    _lists.expect_selected(page, "agents", "Alpha 2")
    # filter_agents narrows the rows; agents_new opens the create route;
    # agents_empty_state is the detail pane's empty state at the root.
    _lists.filter_agents(page, "alpha 2")
    expect(page.locator('[data-testid="agent-item"]:visible')).to_have_count(1)
    _lists.filter_agents(page, "")
    _lists.agents_new(page)
    _nav.set_route(page, "agents")
    expect(_lists.agents_empty_state(page)).to_be_visible(timeout=8000)


def test_lists_helper_library(app_clean: str, page: Page) -> None:
    kb = _post(app_clean, "/api/knowledge-bases", {"name": "Design docs"})["id"]
    _post(app_clean, "/api/knowledge-bases", {"name": "Design docs archive"})
    src = _post(
        app_clean,
        "/api/mcp-sources",
        {"name": "files", "type": "stdio", "config": {"command": "x"}},
    )["id"]
    conn = _post(
        app_clean,
        "/api/connectors",
        {"name": "Team chat", "type": "discord", "config": {"enabled": False}},
    )["id"]
    _nav.goto_settled(page, app_clean, "library")
    expect(_lists.list_row(page, "library/knowledge", "Design docs")).to_have_count(1, timeout=8000)
    _lists.open_item(page, "library/knowledge", "Design docs")
    _nav.expect_route(page, f"library/knowledge/{_nav.seg(kb)}")

    _nav.goto_settled(page, app_clean, "library")
    _lists.open_item(page, "library/mcp", "files")
    _nav.expect_route(page, f"library/mcp/{_nav.seg(src)}")

    _nav.goto_settled(page, app_clean, "library")
    _lists.open_item(page, "library/connectors", "Team chat")
    _nav.expect_route(page, f"library/connectors/{_nav.seg(conn)}")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible()
    _lists.expect_selected(page, "library/connectors", "Team chat")

    # The leg 4a helpers: the section root's empty state and the Add menu.
    _nav.set_route(page, "library/mcp")
    expect(_lists.library_start(page)).to_be_visible(timeout=8000)
    for kind in ("providers", "knowledge", "mcp", "connectors"):
        _lists.library_add(page, kind)
        _nav.expect_route(page, f"library/{kind}/~new")
    with pytest.raises(ValueError, match="unknown Library kind"):
        _lists.library_add(page, "library")


def test_lists_helper_library_providers(app_with_provider: SeededApp, page: Page) -> None:
    base = app_with_provider.base_url
    other = seed_mock_provider(base, name="mock two")
    _nav.goto_settled(page, base, "library")
    # Both rows carry a "mock" type badge; only one is NAMED "mock".
    expect(_lists.list_row(page, "library/providers", "mock")).to_have_count(1, timeout=8000)
    _lists.expect_none_selected(page, "library/providers")
    _lists.open_item(page, "library/providers", "mock two")
    _nav.expect_route(page, f"library/providers/{_nav.seg(other)}")
    expect(page.locator("#pf-name")).to_have_value("mock two", timeout=8000)
    _lists.expect_selected(page, "library/providers", "mock two")
    _lists.close_item(page)
    _nav.expect_route(page, "library")
    _lists.expect_none_selected(page, "library/providers")


def test_lists_helper_settings(app_with_provider: SeededApp, page: Page) -> None:
    base = app_with_provider.base_url
    _nav.goto_settled(page, base, "settings/tools")
    first = page.locator('[data-testid="tool-card"]').first
    expect(first).to_be_visible(timeout=8000)
    name = first.get_attribute("data-name")
    assert name
    _lists.open_item(page, "settings/tools", name)
    _nav.expect_route(page, f"settings/tools/{_nav.seg(name)}")
    _lists.expect_selected(page, "settings/tools", name)
    # open_tool switches to the tool's category tab first.
    _lists.open_tool(page, "web_search")
    expect(_lists.settings_item(page).locator(".editor-title")).to_have_text("web_search")
    _lists.expect_selected(page, "settings/tools", "web_search")
    expect(_lists.tool_toggle(page, "web_search")).to_be_visible()
    with pytest.raises(ValueError, match="unknown tool"):
        _lists.open_tool(page, "nope")
