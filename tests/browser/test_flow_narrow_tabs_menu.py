# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Below 768px a tabbed page shows one menu button naming the current tab (sortie 21 HAT feature).

The agent editor's six tabs and the Built-in tools page's categories become a menu button (label =
the current tab, popup = every tab as a ``menuitemradio``); choosing an item routes exactly as a
tab click does. Contract-level cases (veto, keyboard, resize) are in ``test_ui_tabs_contract.py``.
Falls in the ``layout`` lane (``test_flow_narrow_*``).
"""

from __future__ import annotations

import urllib.parse

import pytest
from browser import _nav
from browser.seeders import SeededApp
from browser.test_flow_studio_tools_notices import _seed_overrides, _tighten
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

SMALL = {"width": 624, "height": 321}
AGENT_BTN = '[data-testid="agent-tabs-menu-btn"]'
TOOLS_BTN = '[data-testid="tools-tabs-menu-btn"]'


def _no_sideways_scroll(page: Page) -> None:
    over = page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert over <= 0, f"page scrolls sideways by {over}px"


def test_agent_tabs_are_a_menu_button_that_routes(app_with_agent: SeededApp, page: Page) -> None:
    name = app_with_agent.agent_name
    assert name is not None
    page.set_viewport_size(SMALL)
    _nav.goto(page, app_with_agent.base_url, f"agents/{_nav.seg(name)}/tools")
    btn = page.locator(AGENT_BTN)
    expect(btn).to_have_text("Tools", timeout=8000)
    # The strip is gone: no tab is visible, nothing scrolls sideways, the panel is named by its tab.
    expect(page.get_by_role("tab")).to_have_count(0)
    expect(page.get_by_role("tabpanel", name="Tools")).to_have_count(1)
    _no_sideways_scroll(page)
    assert (
        page.evaluate(
            "() => document.querySelector('#agent-tab-panel-tools').getAttribute('aria-labelledby')"
        )
        == "agent-tab-tools"
    )
    # The popup lists every tab, the current one checked; choose "Rules and notes".
    btn.click()
    expect(page.get_by_role("menu", name="Agent settings")).to_be_visible()
    items = page.get_by_role("menuitemradio")
    expect(items).to_have_count(6)
    assert [i.strip() for i in items.all_inner_texts()] == [
        "General",
        "Rules and notes",
        "Knowledge",
        "Tools",
        "Routines",
        "Self-configuration",
    ]
    expect(page.locator('[data-testid="tab-tools-menu-item"]')).to_have_attribute(
        "aria-checked", "true"
    )
    page.locator('[data-testid="tab-rules-and-notes-menu-item"]').click()
    _nav.expect_route(page, f"agents/{_nav.seg(name)}/rules-and-notes")
    expect(btn).to_have_text("Rules and notes")
    expect(page.locator("#agent-tab-panel-rules-and-notes")).to_be_visible()
    expect(page.locator("#agent-tab-panel-tools")).to_be_hidden()
    expect(btn).to_be_focused()
    expect(page.get_by_role("tabpanel", name="Rules and notes")).to_have_count(1)
    _no_sideways_scroll(page)


def test_router_driven_tab_change_relabels_the_button(
    app_with_agent: SeededApp, page: Page
) -> None:
    """A route change (not the menu) moves the label and the check too."""
    name = app_with_agent.agent_name
    assert name is not None
    page.set_viewport_size(SMALL)
    _nav.goto(page, app_with_agent.base_url, f"agents/{_nav.seg(name)}/general")
    expect(page.locator(AGENT_BTN)).to_have_text("General", timeout=8000)
    assert page.evaluate("(r) => App.router.go(r)", f"agents/{_nav.seg(name)}/routines") is True
    expect(page.locator(AGENT_BTN)).to_have_text("Routines")
    expect(page.locator("#agent-tab-panel-routines")).to_be_visible()


def test_wide_window_keeps_the_tablist(app_with_agent: SeededApp, page: Page) -> None:
    name = app_with_agent.agent_name
    assert name is not None
    page.set_viewport_size({"width": 1024, "height": 700})
    _nav.goto(page, app_with_agent.base_url, f"agents/{_nav.seg(name)}/general")
    expect(page.locator('[data-testid="tab-general"]')).to_have_attribute(
        "aria-selected", "true", timeout=8000
    )
    expect(page.get_by_role("tab")).to_have_count(6)
    expect(page.locator(AGENT_BTN)).to_have_count(0)


def test_tools_tab_indicator_shows_on_the_button_and_the_item(
    app_with_agent: SeededApp, page: Page
) -> None:
    name = app_with_agent.agent_name
    assert name is not None
    base = app_with_agent.base_url
    _seed_overrides(base, name)
    _tighten(base)
    page.set_viewport_size(SMALL)
    _nav.goto(page, base, f"agents/{_nav.seg(urllib.parse.quote(name))}/tools")
    btn = page.locator(AGENT_BTN)
    expect(btn.locator(".ui-menu-trigger-label")).to_have_text("Tools", timeout=8000)
    expect(page.get_by_role("button", name="Tools, 2 notices", exact=True)).to_have_count(1)
    expect(btn.locator(".ui-tab-indicator-dot")).to_have_count(1)
    btn.click()
    expect(page.get_by_role("menuitemradio", name="Tools, 2 notices", exact=True)).to_have_count(1)


def test_builtin_tools_categories_are_a_menu_button(app_clean: str, page: Page) -> None:
    page.set_viewport_size(SMALL)
    _nav.goto(page, app_clean, "settings/tools")
    expect(page.locator(".area-admin .page-title")).to_have_text("Built-in tools", timeout=8000)
    btn = page.locator(TOOLS_BTN)
    expect(btn).to_be_visible(timeout=8000)
    expect(page.get_by_role("tab")).to_have_count(0)
    _no_sideways_scroll(page)
    label = btn.inner_text().strip()
    assert label  # the first category's name
    btn.click()
    expect(page.get_by_role("menu", name="Tool categories")).to_be_visible()
    expect(page.get_by_role("menuitemradio")).to_have_count(
        page.evaluate("() => document.querySelectorAll('[role=tabpanel]').length")
    )
    page.locator('[data-testid="tab-web-menu-item"]').click()
    expect(page.locator("#tools-panel-web")).to_be_visible()
    expect(page.locator("#tools-panel-filesystem")).to_be_hidden()
    expect(btn).to_be_focused()
    assert btn.inner_text().strip() != label
    expect(page.locator('[data-testid="tab-web-menu-item"]')).to_have_attribute(
        "aria-checked", "true"
    )
    _no_sideways_scroll(page)
