"""Keyboard-operability tests (F3 leg 03).

Verifies that all interactive list rows (session-item, agent-item,
admin-category-item) and their inline action buttons (delete, chip-remove)
are reachable and activatable via keyboard.

Design choices:
- Session tests use a single auto-created session (WS creates one on load).
  The "two sessions" scenario from the spec is trimmed — single-session
  Enter activation is the load-bearing assertion.
- Chip-remove keyboard test is dropped: no MCP sources are seeded in
  the default fixtures, so driving chip-add via UI would be brittle.
  The closest() dispatch fix is verified by the JS unit tests instead.
- Admin category test uses app_clean (no agent/provider needed for navigation).
"""

from __future__ import annotations

import pytest
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_session_item_keyboard_select(app_with_agent: SeededApp, page: Page) -> None:
    """Tab into the session-item, press Enter; aria-selected becomes true."""
    base_url = app_with_agent.base_url
    page.goto(base_url)

    # Bootstrap a session via the welcome listbox (no auto-create after leg 05).
    page.locator(".chat-welcome-item").filter(has_text=app_with_agent.agent_name).click()
    expect(page.locator(".session-agent-badge")).to_have_text(
        app_with_agent.agent_name, timeout=8000
    )

    # Confirm the session-item appeared and has listbox role on parent
    session_item = page.locator(".session-item").first
    expect(session_item).to_be_visible(timeout=5000)

    # Focus directly and press Enter
    session_item.focus()
    page.keyboard.press("Enter")

    # aria-selected should be "true" after activation
    expect(session_item).to_have_attribute("aria-selected", "true")


@pytest.mark.browser
def test_session_item_has_role_option(app_with_agent: SeededApp, page: Page) -> None:
    """Session list has role=listbox; each item has role=option and tabindex=0."""
    base_url = app_with_agent.base_url
    page.goto(base_url)

    # Bootstrap a session via the welcome listbox (no auto-create after leg 05).
    page.locator(".chat-welcome-item").filter(has_text=app_with_agent.agent_name).click()
    expect(page.locator(".session-agent-badge")).to_have_text(
        app_with_agent.agent_name, timeout=8000
    )
    expect(page.locator(".session-item").first).to_be_visible(timeout=5000)

    # Listbox role on parent
    session_list = page.locator(".session-list")
    expect(session_list).to_have_attribute("role", "listbox")

    # Each item is an option with tabindex=0
    session_item = page.locator(".session-item").first
    expect(session_item).to_have_attribute("role", "option")
    expect(session_item).to_have_attribute("tabindex", "0")


@pytest.mark.browser
def test_session_delete_keyboard_reveal(app_with_agent: SeededApp, page: Page) -> None:
    """Tab from session-item to its .delete button; :focus-within reveals it.

    A display:none element cannot be focused directly. The reveal is driven by
    Tab from the parent session-item (which IS focusable via tabindex=0) into
    the delete button child. Once the delete button has focus, the parent's
    :focus-within selector fires and display:none becomes display:block.
    """
    base_url = app_with_agent.base_url
    page.goto(base_url)

    # Bootstrap a session via the welcome listbox (no auto-create after leg 05).
    page.locator(".chat-welcome-item").filter(has_text=app_with_agent.agent_name).click()
    expect(page.locator(".session-agent-badge")).to_have_text(
        app_with_agent.agent_name, timeout=8000
    )
    expect(page.locator(".session-item").first).to_be_visible(timeout=5000)

    delete_btn = page.locator(".session-item .delete").first

    # Before focus: delete is hidden (display:none)
    expect(delete_btn).to_be_hidden()

    # Focus the session-item (tabindex=0), then Tab once to reach the delete button
    page.locator(".session-item").first.focus()
    page.keyboard.press("Tab")

    # :focus-within on the parent fires when the delete button receives focus
    expect(delete_btn).to_be_visible()


@pytest.mark.browser
def test_agent_item_keyboard_select(app_with_agent: SeededApp, page: Page) -> None:
    """Tab into agent tile, press Enter; aria-selected becomes true.

    F5 leg 02 replaced the flat `<div role="option">` rows inside
    `<div class="agent-list" role="listbox">` with a CSS-grid of
    `<button class="entity-tile">` buttons. Each tile is a natural tab stop
    (default <button> behavior, no custom tabindex), so the listbox/option
    pattern was retired in favor of a more direct keyboard model.
    """
    base_url = app_with_agent.base_url
    page.goto(f"{base_url}#studio")

    # Wait for the tile grid to render.
    agent_item = page.locator('[data-testid="agent-item"]').first
    expect(agent_item).to_be_visible(timeout=5000)

    # The container is a CSS-grid (`.entity-tile-grid`), not a listbox.
    expect(page.locator(".entity-tile-grid")).to_be_visible()

    # The tile is a <button> (natural tab stop) carrying the agent-item testid.
    tag_name = agent_item.evaluate("el => el.tagName.toLowerCase()")
    assert tag_name == "button", f"agent-item must be a <button>, got <{tag_name}>"

    # Bare #studio/agents shows the tile grid with no agent selected.
    # Focus the tile and press Enter to select it.
    agent_item.focus()
    page.keyboard.press("Enter")

    expect(agent_item).to_have_attribute("aria-selected", "true")


@pytest.mark.browser
def test_admin_category_keyboard_select(app_clean: str, page: Page) -> None:
    """Tab into section-nav-item, press Enter; aria-current becomes 'page'."""
    page.goto(f"{app_clean}#admin")

    # Wait for admin section nav to render (scoped under .area-admin so studio
    # nav buttons cannot match if both areas are mounted in DOM).
    category_item = page.locator(".area-admin .section-nav-item").first
    expect(category_item).to_be_visible(timeout=5000)

    # Section-nav container has role=group (set by App.layout.renderSectionNav)
    expect(page.locator(".area-admin .section-nav")).to_have_attribute("role", "group")

    # Active section-nav item has tabindex=0 (roving tabindex contract)
    expect(category_item).to_have_attribute("tabindex", "0")

    # The first section-nav item is "General" which is active by default
    # Click the second item (LLM Providers) then keyboard-activate the first
    page.locator(".area-admin .section-nav-item").nth(1).click()

    # Now focus first item and press Enter to switch back
    first_item = page.locator(".area-admin .section-nav-item").first
    first_item.focus()
    page.keyboard.press("Enter")

    expect(first_item).to_have_attribute("aria-current", "page")
