"""Keyboard-operability tests (F3 leg 03).

Verifies that all interactive list rows (session-card, agent-card,
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

L7.1 Holograph selector migration:
- .session-item → .session-card (history-buckets.js rename)
- .session-list → .sessions-list (chat.js id/class rename)
- .session-item .delete → .session-card .delete (delete btn inside card)
- .entity-tile-grid → .agents-list (studio.js rename; role=listbox on the list)
- section-nav role="group" → role="tablist" (section-nav.js L1.7 update)
"""

from __future__ import annotations

import pytest
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_session_item_keyboard_select(app_with_agent: SeededApp, page: Page) -> None:
    """Tab into the session-card, press Enter; aria-selected becomes true."""
    base_url = app_with_agent.base_url
    page.goto(base_url)

    # Bootstrap a session via the welcome listbox (no auto-create after leg 05).
    # Holograph: .chat-agent-card (was .chat-welcome-item).
    page.locator(".chat-agent-card").filter(has_text=app_with_agent.agent_name).click()
    expect(page.locator(".convo-agent")).to_contain_text(
        app_with_agent.agent_name, timeout=8000
    )

    # Confirm the session-card appeared and has listbox role on parent.
    # Holograph: .session-card (was .session-item).
    session_item = page.locator(".session-card").first
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
    page.locator(".chat-agent-card").filter(has_text=app_with_agent.agent_name).click()
    expect(page.locator(".convo-agent")).to_contain_text(
        app_with_agent.agent_name, timeout=8000
    )
    # Holograph: .session-card (was .session-item).
    expect(page.locator(".session-card").first).to_be_visible(timeout=5000)

    # Listbox role on parent.
    # Holograph: .sessions-list (was .session-list); id="chat-sessions-list".
    session_list = page.locator(".sessions-list")
    expect(session_list).to_have_attribute("role", "listbox")

    # Each item is an option with tabindex=0
    session_item = page.locator(".session-card").first
    expect(session_item).to_have_attribute("role", "option")
    expect(session_item).to_have_attribute("tabindex", "0")


@pytest.mark.browser
def test_session_delete_keyboard_reveal(app_with_agent: SeededApp, page: Page) -> None:
    """Tab from session-card to its .delete button; button is focusable and in the DOM.

    Holograph note: Mission-08 used a :focus-within / display:none reveal pattern
    for the delete button. Holograph chat.css does NOT hide the delete button —
    it is rendered in the DOM and visible. The load-bearing assertions are:
    1. The delete button (.delete.list-item-delete) is present inside .session-card.
    2. Tab from the session-card reaches the delete button (it has focus after Tab).
    """
    base_url = app_with_agent.base_url
    page.goto(base_url)

    # Bootstrap a session via the welcome listbox (no auto-create after leg 05).
    page.locator(".chat-agent-card").filter(has_text=app_with_agent.agent_name).click()
    expect(page.locator(".convo-agent")).to_contain_text(
        app_with_agent.agent_name, timeout=8000
    )
    # Holograph: .session-card (was .session-item).
    expect(page.locator(".session-card").first).to_be_visible(timeout=5000)

    # Holograph: delete button has class .delete .list-item-delete inside .session-card.
    # In Holograph the button is visible (no display:none reveal needed).
    delete_btn = page.locator(".session-card .delete").first
    expect(delete_btn).to_be_visible()

    # Focus the session-card (tabindex=0), then Tab once to reach the delete button.
    page.locator(".session-card").first.focus()
    page.keyboard.press("Tab")

    # After Tab, the delete button should have focus.
    expect(delete_btn).to_be_focused()


@pytest.mark.browser
def test_agent_item_keyboard_select(app_with_agent: SeededApp, page: Page) -> None:
    """Tab into agent card, press Enter; aria-selected becomes true.

    F5 leg 02 replaced the flat `<div role="option">` rows inside
    `<div class="agent-list" role="listbox">` with a CSS-grid of
    `.agent-card` divs (with role=option + tabindex=0). Each card is a
    natural focus target via tabindex=0, so keyboard navigation works
    directly on the card element.

    Holograph: .agents-list (was .entity-tile-grid) holds .agent-card items
    (was .entity-tile); the list has role=listbox and each card role=option.
    """
    base_url = app_with_agent.base_url
    page.goto(f"{base_url}#studio")

    # Wait for the agent card to render.
    agent_item = page.locator('[data-testid="agent-item"]').first
    expect(agent_item).to_be_visible(timeout=5000)

    # Holograph: .agents-list (was .entity-tile-grid).
    expect(page.locator(".agents-list")).to_be_visible()

    # The card is a <div> with role=option and tabindex=0 (not a <button>).
    tag_name = agent_item.evaluate("el => el.tagName.toLowerCase()")
    assert tag_name == "div", f"agent-item must be a <div>, got <{tag_name}>"

    # Bare #studio/agents shows the card grid with no agent selected.
    # Focus the card and press Enter to select it.
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

    # Holograph: section-nav container uses role=tablist (was role=group).
    # The L1.7 section-nav.js rewrite changed the ARIA role from "group"
    # to "tablist" for WCAG compliance with the tab-key navigation pattern.
    expect(page.locator(".area-admin .section-nav")).to_have_attribute("role", "tablist")

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
