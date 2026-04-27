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
    """Tab into agent-item, press Enter; aria-selected becomes true."""
    base_url = app_with_agent.base_url
    page.goto(f"{base_url}#studio")

    # Wait for agent list to populate
    agent_item = page.locator('[data-testid="agent-item"]').first
    expect(agent_item).to_be_visible(timeout=5000)

    # Agent list has role=listbox
    expect(page.locator(".agent-list")).to_have_attribute("role", "listbox")

    # Agent item is role=option with tabindex=0
    expect(agent_item).to_have_attribute("role", "option")
    expect(agent_item).to_have_attribute("tabindex", "0")

    # Focus and press Enter — selectAgent fires, aria-selected becomes true
    agent_item.focus()
    page.keyboard.press("Enter")

    expect(agent_item).to_have_attribute("aria-selected", "true")


@pytest.mark.browser
def test_admin_category_keyboard_select(app_clean: str, page: Page) -> None:
    """Tab into admin-category-item, press Enter; aria-selected becomes true."""
    page.goto(f"{app_clean}#admin")

    # Wait for admin category list to render
    category_item = page.locator(".admin-category-item").first
    expect(category_item).to_be_visible(timeout=5000)

    # Category list has role=listbox
    expect(page.locator(".admin-category-list")).to_have_attribute("role", "listbox")

    # Category item has role=option with tabindex=0
    expect(category_item).to_have_attribute("role", "option")
    expect(category_item).to_have_attribute("tabindex", "0")

    # The first category is "General" which is active by default
    # Click the second category (Providers) then keyboard-activate the first
    page.locator(".admin-category-item").nth(1).click()

    # Now focus first item and press Enter to switch back
    first_item = page.locator(".admin-category-item").first
    first_item.focus()
    page.keyboard.press("Enter")

    expect(first_item).to_have_attribute("aria-selected", "true")
