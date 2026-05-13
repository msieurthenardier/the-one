"""End-to-end flow tests: studio agent tile grid (F5 leg 02 + leg 05).

Covers the CSS-grid tile layout:

- `.entity-tile-grid` renders as the agents container in the main panel
- Each tile is a `<button class="entity-tile">` carrying the legacy
  `.agent-item` class (composed for test-selector continuity), plus
  `data-testid="agent-item"`, `data-name`, `aria-selected`
- Tile click navigates to the editor

F5 leg 05 removed the per-tile X-button. Agent deletion lives in the
editor's General-tab Danger Zone — see `test_flow_agent_crud.py`.
"""

from __future__ import annotations

import pytest
from browser.seeders import SeededApp, seed_mock_agent
from playwright.sync_api import Page, expect


def _wait_studio_ready(page: Page) -> None:
    """Wait for the studio area to mount (section-nav visible)."""
    expect(page.locator('.section-nav[aria-label="Agent Studio sections"]')).to_be_visible(timeout=8000)


@pytest.mark.browser
def test_agent_tile_grid_renders(app_with_agent: SeededApp, page: Page) -> None:
    """The agents pane uses `.entity-tile-grid` with `<button class="entity-tile">` tiles."""
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name

    page.goto(f"{base_url}#studio")
    _wait_studio_ready(page)

    grid = page.locator(".entity-tile-grid")
    expect(grid).to_be_visible(timeout=5000)

    tile = page.locator(f'button.entity-tile[data-name="{agent_name}"]')
    expect(tile).to_have_count(1)
    expect(tile).to_have_attribute("data-testid", "agent-item")


@pytest.mark.browser
def test_agent_tile_click_opens_editor(app_with_agent: SeededApp, page: Page) -> None:
    """Clicking the tile navigates to the editor (selectAgent fires)."""
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name

    page.goto(f"{base_url}#studio")
    _wait_studio_ready(page)

    tile = page.locator(f'button.entity-tile[data-name="{agent_name}"]')
    expect(tile).to_be_visible(timeout=5000)
    tile.click()

    expect(page.locator(".editor-title")).to_have_text(agent_name, timeout=5000)
    expect(tile).to_have_attribute("aria-selected", "true")


@pytest.mark.browser
def test_multiple_tiles_render_in_grid(app_with_provider: SeededApp, page: Page) -> None:
    """Multiple agents render as multiple tiles inside the same grid container."""
    base_url = app_with_provider.base_url
    seed_mock_agent(base_url, app_with_provider.provider_id, name="agent-alpha")
    seed_mock_agent(base_url, app_with_provider.provider_id, name="agent-beta")

    page.goto(f"{base_url}#studio")
    _wait_studio_ready(page)

    grid = page.locator(".entity-tile-grid")
    expect(grid).to_be_visible(timeout=5000)

    tiles = page.locator("button.entity-tile")
    expect(tiles).to_have_count(2, timeout=5000)

    alpha = page.locator('button.entity-tile[data-name="agent-alpha"]')
    expect(alpha.locator(".entity-tile-name")).to_have_text("agent-alpha")
    beta = page.locator('button.entity-tile[data-name="agent-beta"]')
    expect(beta.locator(".entity-tile-name")).to_have_text("agent-beta")
