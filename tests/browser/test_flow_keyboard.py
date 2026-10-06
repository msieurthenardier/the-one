"""Keyboard-operability tests (F3 leg 03).

Verifies that all interactive list rows (session-item, agent-item) and the
Settings nav links (M25 F3 leg 5a), plus their inline action buttons (delete,
chip-remove), are reachable and activatable via keyboard.

Design choices:
- Session tests use a single auto-created session (WS creates one on load).
  The "two sessions" scenario from the spec is trimmed — single-session
  Enter activation is the load-bearing assertion.
- Chip-remove keyboard test is dropped: no MCP sources are seeded in
  the default fixtures, so driving chip-add via UI would be brittle.
  The closest() dispatch fix is verified by the JS unit tests instead.
- The Settings nav tests use app_clean (no agent/provider needed for navigation).
"""

from __future__ import annotations

import pytest
from browser import _lists, _nav
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_session_item_keyboard_select(app_with_agent: SeededApp, page: Page) -> None:
    """Tab into the session-item, press Enter; aria-current becomes 'page'.

    F2 leg 01 retired the listbox/option roles on the session list (nested
    interactive elements under role="option" violated WCAG 4.1.2). The row
    is now <li class="list-item"><button class="session-item">...; the
    active-session signal is aria-current="page" (as the list and nav controls).
    """
    base_url = app_with_agent.base_url
    page.goto(base_url)

    # Bootstrap a session via the welcome listbox (no auto-create after leg 05).
    page.locator(".chat-welcome-item").filter(has_text=app_with_agent.agent_name).click()
    expect(page.locator(".session-agent-badge")).to_have_text(
        app_with_agent.agent_name, timeout=8000
    )

    session_item = page.locator(".session-item").first
    expect(session_item).to_be_visible(timeout=5000)

    # Focus directly and press Enter
    session_item.focus()
    page.keyboard.press("Enter")

    # aria-current="page" marks the active session post-restructure.
    expect(session_item).to_have_attribute("aria-current", "page")


@pytest.mark.browser
def test_session_list_shape(app_with_agent: SeededApp, page: Page) -> None:
    """Session list is a <nav> landmark; items are <button class="session-item">.

    F2 leg 01: the prior `<div role="listbox">` + `<div role="option">` pair
    was retired because role="option" forbids nested interactive elements
    (the sibling delete button). Container is now <nav class="session-list">
    with bucketed <ul>s of <li class="list-item"><button class="session-item">.
    """
    base_url = app_with_agent.base_url
    page.goto(base_url)

    # Bootstrap a session via the welcome listbox (no auto-create after leg 05).
    page.locator(".chat-welcome-item").filter(has_text=app_with_agent.agent_name).click()
    expect(page.locator(".session-agent-badge")).to_have_text(
        app_with_agent.agent_name, timeout=8000
    )
    expect(page.locator(".session-item").first).to_be_visible(timeout=5000)

    # Container is a <nav> landmark (no listbox role).
    session_list = page.locator(".session-list")
    tag_name = session_list.evaluate("el => el.tagName.toLowerCase()")
    assert tag_name == "nav", f"session-list must be <nav>, got <{tag_name}>"

    # Each item is a native <button> (no role=option, no custom tabindex).
    session_item = page.locator(".session-item").first
    item_tag = session_item.evaluate("el => el.tagName.toLowerCase()")
    assert item_tag == "button", f".session-item must be <button>, got <{item_tag}>"


@pytest.mark.browser
def test_session_delete_keyboard_reveal(app_with_agent: SeededApp, page: Page) -> None:
    """Tab from session-item to its sibling .delete button; :focus-within reveals it.

    A display:none element cannot be focused directly. The reveal is driven by
    Tab from the focused session-button into its sibling delete button under
    the same <li class="list-item">. Once the delete button has focus, the
    .list-item's :focus-within fires and display:none becomes display:block.
    F2 leg 01: the row was restructured from a single <div role="option">
    holding both the title and the delete button into a sibling button-pair
    wrapped by an <li class="list-item">; the CSS reveal rule still keys on
    .list-item, so the affordance behaves identically.
    """
    base_url = app_with_agent.base_url
    page.goto(base_url)

    # Bootstrap a session via the welcome listbox (no auto-create after leg 05).
    page.locator(".chat-welcome-item").filter(has_text=app_with_agent.agent_name).click()
    expect(page.locator(".session-agent-badge")).to_have_text(
        app_with_agent.agent_name, timeout=8000
    )
    expect(page.locator(".session-item").first).to_be_visible(timeout=5000)

    # Delete button is a sibling of .session-item under the row <li>.
    delete_btn = page.locator(".list-item .list-item-delete").first

    # Before focus: delete is hidden (display:none)
    expect(delete_btn).to_be_hidden()

    # Focus the session-item button, then Tab once to reach the sibling delete.
    page.locator(".session-item").first.focus()
    page.keyboard.press("Tab")

    # :focus-within on the wrapping .list-item fires when the delete button
    # receives focus.
    expect(delete_btn).to_be_visible()


@pytest.mark.browser
def test_agent_item_keyboard_select(app_with_agent: SeededApp, page: Page) -> None:
    """Tab from the filter into the agents list, press Enter; the row's agent
    opens and the row carries aria-current="page".

    M25 F3 L3 replaced the tile grid (`<button>` tiles) with an App.ui.listPane
    column: each row is a native `<a href>` (Enter navigates natively, App.nav
    routes the click), with one roving tab stop -- the selected row, else the
    first visible row. The filter sits before the list in Tab order.
    """
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name
    # goto_settled: Studio's first activation loads the inventory twice
    # (init() and activate()->_refresh()); both passes re-render the rows, so
    # wait for the fetch activity to go quiet before focusing one.
    _nav.goto_settled(page, base_url, "agents")

    agent_item = _lists.list_row(page, "agents", agent_name)
    expect(agent_item).to_be_visible(timeout=5000)
    tag_name = agent_item.evaluate("el => el.tagName.toLowerCase()")
    assert tag_name == "a", f"agent-item must be an <a> link, got <{tag_name}>"

    # The filter is the tab stop before the list; Tab lands on the row.
    page.locator('[data-testid="agents-filter"]').focus()
    page.keyboard.press("Tab")
    expect(agent_item).to_be_focused()
    page.keyboard.press("Enter")

    _nav.expect_route(page, f"agents/{_nav.seg(agent_name)}/general")
    expect(page.locator(".editor-title")).to_have_text(agent_name, timeout=8000)
    _lists.expect_selected(page, "agents", agent_name)


# The Settings nav (M25 F3 leg 5a, DD10) is App.ui.navGroups: plain links in Tab
# order with no roving tabindex and no arrow keys (the board's <a> items). The
# former section nav's roving-tabindex test is rewritten for the new control:
# keyboard coverage stays, the behaviour under test changes with it.
_SETTINGS_NAV_ORDER = (
    "appearance",
    "prompts",
    "encryption",
    "providers",
    "tools",
    "knowledge-indexing",
    "design-language",  # the browser lanes run in dev mode
)


@pytest.mark.browser
def test_settings_nav_links_are_in_tab_order(app_clean: str, page: Page) -> None:
    """Tab reaches each Settings nav link in group order, with a visible focus ring."""
    _nav.goto(page, app_clean, "settings/appearance")
    nav = _lists.settings_nav(page)
    expect(nav).to_be_visible(timeout=5000)
    # A <nav> landmark named "Settings" (no explicit role attribute needed).
    assert nav.evaluate("el => el.tagName") == "NAV"
    expect(nav).to_have_attribute("aria-label", "Settings")

    links = nav.locator("a")
    expect(links).to_have_count(len(_SETTINGS_NAV_ORDER))
    for k, section in enumerate(_SETTINGS_NAV_ORDER):
        link = links.nth(k)
        expect(link).to_have_attribute("data-testid", f"settings-nav-{section}")
        # Plain links: no roving tabindex, every one is a Tab stop.
        assert link.get_attribute("tabindex") is None, section

    # Focus the first link, then Tab walks the rest in order.
    _lists.settings_nav_link(page, "appearance").focus()
    for section in _SETTINGS_NAV_ORDER[1:]:
        page.keyboard.press("Tab")
        link = _lists.settings_nav_link(page, section)
        expect(link).to_be_focused()
        # Keyboard focus is visible (the factory's :focus-visible ring).
        assert link.evaluate("el => el.matches(':focus-visible')"), section
        assert link.evaluate("el => getComputedStyle(el).outlineStyle") == "solid", section


@pytest.mark.browser
def test_settings_nav_enter_navigates_and_moves_aria_current(app_clean: str, page: Page) -> None:
    """Enter on a focused link navigates; aria-current follows the page."""
    _nav.goto(page, app_clean, "settings/appearance")
    _lists.expect_settings_selected(page, "appearance")

    providers = _lists.settings_nav_link(page, "providers")
    providers.focus()
    page.keyboard.press("Enter")
    _nav.expect_route(page, "settings/providers")
    expect(_lists.settings_page_title(page)).to_have_text("Providers", timeout=5000)
    _lists.expect_settings_selected(page, "providers")

    appearance = _lists.settings_nav_link(page, "appearance")
    appearance.focus()
    page.keyboard.press("Enter")
    _nav.expect_route(page, "settings/appearance")
    expect(_lists.settings_page_title(page)).to_have_text("Appearance", timeout=5000)
    _lists.expect_settings_selected(page, "appearance")
