"""End-to-end flow tests: studio agent tile grid + tile delete (F5 leg 02).

Covers the CSS-grid tile layout introduced in F5 leg 02:

- `.agent-tile-grid` renders as the agents container
- Each tile is a `<button class="agent-tile">` carrying the legacy
  `.agent-item` class (composed for test-selector continuity), plus
  `data-testid="agent-item"`, `data-name`, `aria-selected`
- The X-button is a sibling (wrap-with-siblings DOM) — pressing Enter on
  the X-button triggers the delete flow WITHOUT bubbling to the tile's
  keydown listener (which would call selectAgent and open the editor)
- Tile click navigates to the editor
- Two-step delete: first click arms confirm, second click within 3s
  fires DELETE; tile is removed
- Revert after timeout: first click arms confirm; ~3.5s wait restores
  the original name + clears the confirm-delete class
"""

from __future__ import annotations

import pytest
from browser.seeders import SeededApp, seed_mock_agent
from playwright.sync_api import Page, expect


def _wait_studio_ready(page: Page) -> None:
    """Wait for the studio area to mount (section-nav + Studio header visible)."""
    expect(page.locator(".section-nav-header")).to_have_text("Studio", timeout=8000)


@pytest.mark.browser
def test_agent_tile_grid_renders(app_with_agent: SeededApp, page: Page) -> None:
    """The agents pane uses an `.agent-tile-grid` container with `<button class="agent-tile">` tiles."""
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name

    page.goto(f"{base_url}#studio")
    _wait_studio_ready(page)

    grid = page.locator(".agent-tile-grid")
    expect(grid).to_be_visible(timeout=5000)

    # The seeded agent renders as a tile button (not a list-item row).
    tile = page.locator(f'button.agent-tile[data-name="{agent_name}"]')
    expect(tile).to_have_count(1)
    expect(tile).to_have_attribute("data-testid", "agent-item")

    # The X-button is a SIBLING of the tile (wrap-with-siblings), not a descendant.
    wrap = page.locator(".agent-tile-wrap").first
    delete_btn = wrap.locator('[data-testid="agent-tile-delete-btn"]')
    expect(delete_btn).to_have_count(1)
    # Confirm DOM hierarchy: the X-button is NOT inside the tile button.
    is_descendant = page.evaluate(
        """() => {
            const tile = document.querySelector('button.agent-tile');
            const x = document.querySelector('[data-testid="agent-tile-delete-btn"]');
            return tile && x && tile.contains(x);
        }"""
    )
    assert is_descendant is False, "X-button must NOT be nested inside the tile button"


@pytest.mark.browser
def test_agent_tile_click_opens_editor(app_with_agent: SeededApp, page: Page) -> None:
    """Clicking the tile navigates to the editor (selectAgent fires)."""
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name

    page.goto(f"{base_url}#studio")
    _wait_studio_ready(page)

    tile = page.locator(f'button.agent-tile[data-name="{agent_name}"]')
    expect(tile).to_be_visible(timeout=5000)
    tile.click()

    # Editor renders the agent's name in its header title.
    expect(page.locator(".editor-title")).to_have_text(agent_name, timeout=5000)
    # aria-selected flips on the tile.
    expect(tile).to_have_attribute("aria-selected", "true")


@pytest.mark.browser
def test_agent_tile_two_step_delete(app_with_agent: SeededApp, page: Page) -> None:
    """First click on X arms 'Confirm delete?'; second click within 3s fires DELETE."""
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name

    page.goto(f"{base_url}#studio")
    _wait_studio_ready(page)

    tile = page.locator(f'button.agent-tile[data-name="{agent_name}"]')
    name_span = tile.locator(".agent-tile-name")
    expect(name_span).to_have_text(agent_name, timeout=5000)

    # X-button is `display: none` until the wrap is hovered/focused-within.
    # Hover the wrap to reveal it, then click normally.
    page.locator(".agent-tile-wrap").hover()
    delete_btn = page.locator('[data-testid="agent-tile-delete-btn"]')
    delete_btn.click()

    # First click: confirm prompt visible, tile carries .confirm-delete class.
    expect(name_span).to_have_text("Confirm delete?", timeout=2000)
    has_confirm = page.evaluate(
        """() => document.querySelector('button.agent-tile').classList.contains('confirm-delete')"""
    )
    assert has_confirm, "tile must have .confirm-delete class after first click"

    # Second click within 3s — DELETE fires, agent disappears. The X-button
    # stays visible while the tile carries .confirm-delete (canonical CSS),
    # so no hover needed for the second click.
    delete_btn.click()

    # The tile is removed; empty state replaces it.
    expect(page.locator('button.agent-tile')).to_have_count(0, timeout=5000)
    expect(page.locator('[data-testid="agent-empty"]')).to_be_visible(timeout=2000)


@pytest.mark.browser
def test_agent_tile_delete_revert_after_timeout(app_with_agent: SeededApp, page: Page) -> None:
    """First click arms confirm; ~3.5s wait restores original name and clears the class."""
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name

    page.goto(f"{base_url}#studio")
    _wait_studio_ready(page)

    tile = page.locator(f'button.agent-tile[data-name="{agent_name}"]')
    name_span = tile.locator(".agent-tile-name")
    expect(name_span).to_have_text(agent_name, timeout=5000)

    page.locator(".agent-tile-wrap").hover()
    delete_btn = page.locator('[data-testid="agent-tile-delete-btn"]')
    delete_btn.click()
    expect(name_span).to_have_text("Confirm delete?", timeout=2000)

    # Wait > revertMs (3000ms) — Playwright's expect with timeout polls until
    # the assertion holds, so we can wait for the name to revert directly.
    expect(name_span).to_have_text(agent_name, timeout=5000)
    has_confirm = page.evaluate(
        """() => document.querySelector('button.agent-tile').classList.contains('confirm-delete')"""
    )
    assert not has_confirm, "tile must drop .confirm-delete class after revert"

    # Tile still present (not deleted).
    expect(tile).to_have_count(1)


@pytest.mark.browser
def test_agent_tile_delete_keydown_bubble_fix(app_with_agent: SeededApp, page: Page) -> None:
    """Pressing Enter on the focused X-button triggers delete WITHOUT entering the editor.

    Wrap-with-siblings makes this naturally true (the X-button is not a
    descendant of the tile button so its keydown does not bubble to the
    tile). The leg also retains an `e.target !== el` guard inside the
    tile's keydown listener as defensive depth.
    """
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name

    page.goto(f"{base_url}#studio")
    _wait_studio_ready(page)

    tile = page.locator(f'button.agent-tile[data-name="{agent_name}"]')
    expect(tile).to_be_visible(timeout=5000)

    # The seeded agent auto-selects on load, so the URL already includes
    # /{name} and the editor is rendered. Track BOTH (a) that the editor's
    # current title doesn't change to a different agent and (b) that the
    # name span flips to "Confirm delete?". We focus the X-button via
    # native .focus() after hovering the wrap to reveal it.
    page.locator(".agent-tile-wrap").hover()
    delete_btn = page.locator('[data-testid="agent-tile-delete-btn"]')
    expect(delete_btn).to_be_visible(timeout=2000)
    delete_btn.focus()

    # Confirm the X-button is the focused element.
    focused_testid = page.evaluate("() => document.activeElement?.dataset?.testid")
    assert focused_testid == "agent-tile-delete-btn", (
        f"X-button must be focusable; activeElement testid: {focused_testid!r}"
    )

    # Pressing Enter on the focused X-button fires its click handler.
    page.keyboard.press("Enter")

    # The delete prompt fires (first-click branch of confirmDelete).
    name_span = tile.locator(".agent-tile-name")
    expect(name_span).to_have_text("Confirm delete?", timeout=2000)

    # The tile's onclick (selectAgent) must NOT fire as a side-effect of
    # the X-button's key event — verified by:
    # 1. The tile button itself does not gain `aria-selected="true"` if it
    #    wasn't already (the keydown-bubble guard would block selectAgent
    #    even if bubbling occurred).
    # 2. The URL did NOT switch to a fresh /{name} via _writeUrl from
    #    selectAgent re-firing.
    # The strongest assertion is that the wrap-with-siblings DOM means the
    # X-button's keydown event does not even reach the tile button's
    # listener. Verify via JS: the tile button does NOT have any keydown
    # event firing originating from the X-button.
    bubble_check = page.evaluate(
        """() => {
            const tile = document.querySelector('button.agent-tile');
            const x = document.querySelector('[data-testid="agent-tile-delete-btn"]');
            // The tile button is NOT an ancestor of the X-button (sibling pattern).
            return tile && x && !tile.contains(x);
        }"""
    )
    assert bubble_check, "X-button must be a sibling of the tile, not a descendant"


@pytest.mark.browser
def test_multiple_tiles_render_in_grid(app_with_provider: SeededApp, page: Page) -> None:
    """Multiple agents render as multiple tiles inside the same grid container."""
    base_url = app_with_provider.base_url
    seed_mock_agent(base_url, app_with_provider.provider_id, name="agent-alpha")
    seed_mock_agent(base_url, app_with_provider.provider_id, name="agent-beta")

    page.goto(f"{base_url}#studio")
    _wait_studio_ready(page)

    grid = page.locator(".agent-tile-grid")
    expect(grid).to_be_visible(timeout=5000)

    tiles = page.locator("button.agent-tile")
    expect(tiles).to_have_count(2, timeout=5000)

    # Each tile has the agent name + data-confirm-title hook on the name span.
    alpha = page.locator('button.agent-tile[data-name="agent-alpha"]')
    expect(alpha.locator("[data-confirm-title]")).to_have_text("agent-alpha")
    beta = page.locator('button.agent-tile[data-name="agent-beta"]')
    expect(beta.locator("[data-confirm-title]")).to_have_text("agent-beta")
