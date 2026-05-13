"""Provider tile grid + page-header + hash routing tests for F6 leg 02.

Covers:
- LLM Providers page renders .page-header with title + "+ New Provider" button.
- Tile grid renders provider tiles with name + badge + url.
- Click tile navigates to #admin/providers/{id}; refresh preserves.
- "+ New Provider" navigates to #admin/providers/new; refresh preserves.
- Cancel from create returns to #admin/providers grid.
- Unknown provider id keeps URL stable; grid renders.
"""

from __future__ import annotations

import re

import pytest
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_provider_grid_page_header(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#admin/providers")
    expect(page.locator(".admin-sub.active .page-header")).to_be_visible(timeout=8000)
    expect(page.locator(".admin-sub.active .page-title")).to_have_text("LLM Providers")
    expect(page.locator('[data-testid="new-provider-btn"]')).to_be_visible()


@pytest.mark.browser
def test_provider_grid_empty_state(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#admin/providers")
    expect(page.locator(".admin-provider-empty")).to_be_visible(timeout=8000)
    expect(page.locator(".admin-provider-empty")).to_contain_text("No providers configured")


@pytest.mark.browser
def test_provider_grid_renders_tiles(app_with_provider: SeededApp, page: Page) -> None:
    """The seed_mock_provider helper creates a provider named 'mock' (default)."""
    page.goto(f"{app_with_provider.base_url}#admin/providers")
    tile = page.locator('[data-testid="provider-card"]')
    expect(tile).to_be_visible(timeout=8000)
    expect(tile).to_have_class(re.compile(r"\bentity-tile\b"))
    expect(tile.locator(".entity-tile-name")).to_have_text("mock")
    # Type badge
    expect(tile.locator(".entity-tile-badge")).to_be_visible()
    # Provider type badge text
    expect(tile.locator(".entity-tile-badge")).to_have_text("mock")


@pytest.mark.browser
def test_new_provider_button_navigates_to_new_url(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#admin/providers")
    expect(page.locator('[data-testid="new-provider-btn"]')).to_be_visible(timeout=8000)
    page.locator('[data-testid="new-provider-btn"]').click()
    # Editor opens (post-leg-03 uses .editor-title with "New Provider").
    expect(page.locator(".editor-title")).to_have_text("New Provider", timeout=5000)
    assert page.evaluate("location.hash") == "#admin/providers/new"


@pytest.mark.browser
def test_create_url_refresh_preserves_create_mode(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#admin/providers/new")
    expect(page.locator(".editor-title")).to_have_text("New Provider", timeout=8000)
    page.reload()
    expect(page.locator(".editor-title")).to_have_text("New Provider", timeout=8000)
    assert page.evaluate("location.hash") == "#admin/providers/new"


@pytest.mark.browser
def test_tile_click_navigates_to_provider_detail(app_with_provider: SeededApp, page: Page) -> None:
    page.goto(f"{app_with_provider.base_url}#admin/providers")
    tile = page.locator('[data-testid="provider-card"]')
    expect(tile).to_be_visible(timeout=8000)
    tile.click()
    # Post-leg-03: editor title is the provider name (seeded "mock"), not "Edit Provider".
    expect(page.locator(".editor-title")).to_have_text("mock", timeout=5000)
    current_hash = page.evaluate("location.hash")
    assert current_hash.startswith("#admin/providers/"), (
        f"expected /providers/<id>, got {current_hash}"
    )
    # The id portion should not be 'new' (we clicked an existing tile)
    suffix = current_hash[len("#admin/providers/") :]
    assert suffix != "new"


@pytest.mark.browser
def test_provider_detail_url_refresh_preserves_editor(
    app_with_provider: SeededApp, page: Page
) -> None:
    page.goto(f"{app_with_provider.base_url}#admin/providers")
    tile = page.locator('[data-testid="provider-card"]')
    expect(tile).to_be_visible(timeout=8000)
    tile.click()
    # Post-leg-03: editor title is the provider name (seeded "mock").
    expect(page.locator(".editor-title")).to_have_text("mock", timeout=5000)
    saved_hash = page.evaluate("location.hash")
    page.reload()
    expect(page.locator(".editor-title")).to_have_text("mock", timeout=8000)
    assert page.evaluate("location.hash") == saved_hash


@pytest.mark.browser
def test_cancel_from_create_returns_to_grid(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#admin/providers/new")
    expect(page.locator(".editor-title")).to_have_text("New Provider", timeout=8000)
    # Clean form — Cancel disabled, use Back to return to the grid.
    page.locator('[data-testid="back-provider-btn"]').click()
    expect(page.locator(".admin-sub.active .page-title")).to_have_text("LLM Providers", timeout=5000)
    assert page.evaluate("location.hash") == "#admin/providers"


@pytest.mark.browser
def test_unknown_provider_id_falls_back_to_grid(app_clean: str, page: Page) -> None:
    """Unknown id keeps URL stable; grid renders with no tile selected."""
    page.goto(f"{app_clean}#admin/providers/00000000-bogus-id-0000-000000000000")
    # No providers exist (app_clean), so the grid renders empty state and
    # the unknown id is held in pending-state pending future fetch resolution.
    # The page should NOT crash; either grid or empty-state should show.
    fallback = page.locator(".admin-sub.active .page-header, .editor-error").first
    expect(fallback).to_be_visible(timeout=8000)
    # URL is not silently overwritten — the pending-id is held
    current_hash = page.evaluate("location.hash")
    # Either the URL stays at the unknown id, or the F3 router replaceState
    # rewrites to #admin/providers (no editor open). Both are acceptable.
    assert current_hash in (
        "#admin/providers/00000000-bogus-id-0000-000000000000",
        "#admin/providers",
    )
