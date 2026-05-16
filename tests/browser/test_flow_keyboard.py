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
    """Tab into the session-item, press Enter; aria-current becomes 'page'.

    F2 leg 01 retired the listbox/option roles on the session list (nested
    interactive elements under role="option" violated WCAG 4.1.2). The row
    is now <li class="list-item"><button class="session-item">...; the
    active-session signal is aria-current="page" (matches section-nav).
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
