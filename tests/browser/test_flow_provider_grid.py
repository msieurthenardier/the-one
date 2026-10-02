"""Provider tile grid + page-header + hash routing tests for F6 leg 02.

Rewritten against post-M08-F4-rebrand markup in M17 F1 L02; re-simplified
to the unified create-CTA contract in M17 F3 L3. Covers:
- LLM Providers page renders .page-header with title; the header
  "+ New Provider" CTA is ALWAYS visible (empty and populated states).
- Tile grid renders provider tiles with name + badge + url.
- Click tile navigates to #admin/providers/{id}; refresh preserves.
- "+ New Provider" navigates to #admin/providers/new; refresh preserves.
- Back from a clean create form returns to #admin/providers grid.
- Unknown provider id keeps URL stable; grid renders.

Unified create CTA (M17 F3 L3): one always-visible header button per
entity grid (data-testid="new-provider-btn", icon + text label). The
former state-split — an in-canvas `-empty` variant owning the affordance
while CSS hid the header button on empty grids — is retired. The empty
canvas still renders a second instance of the same component (same class
+ handler, no testid) as an inviting duplicate; tests target the unified
testid, which matches exactly one element in every state.
"""

from __future__ import annotations

import re

import pytest
from browser import _nav
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_provider_grid_page_header_empty_state(app_clean: str, page: Page) -> None:
    """EMPTY state: the unified header CTA is visible with its text label;
    the empty canvas renders a second instance of the same component."""
    _nav.goto(page, app_clean, "settings/providers")
    expect(page.locator(".area-admin .page-header")).to_be_visible(timeout=8000)
    expect(page.locator(".area-admin .page-title")).to_have_text("LLM Providers")
    header_cta = page.locator('[data-testid="new-provider-btn"]')
    expect(header_cta).to_be_visible()
    expect(header_cta).to_contain_text("New Provider")
    # The empty canvas keeps an inviting duplicate: same component class
    # + handler, no testid (the unified testid matches exactly one element).
    expect(page.locator(".empty-canvas .empty-canvas-cta")).to_be_visible()


@pytest.mark.browser
def test_provider_grid_page_header_populated(app_with_provider: SeededApp, page: Page) -> None:
    """POPULATED state: the same unified header CTA is visible."""
    _nav.goto(page, app_with_provider.base_url, "settings/providers")
    expect(page.locator(".area-admin .page-header")).to_be_visible(timeout=8000)
    expect(page.locator(".area-admin .page-title")).to_have_text("LLM Providers")
    header_cta = page.locator('[data-testid="new-provider-btn"]')
    expect(header_cta).to_be_visible()
    expect(header_cta).to_contain_text("New Provider")


@pytest.mark.browser
def test_provider_grid_empty_state(app_clean: str, page: Page) -> None:
    _nav.goto(page, app_clean, "settings/providers")
    expect(page.locator(".admin-provider-empty")).to_be_visible(timeout=8000)
    expect(page.locator(".admin-provider-empty")).to_contain_text("No providers configured")


@pytest.mark.browser
def test_provider_grid_renders_tiles(app_with_provider: SeededApp, page: Page) -> None:
    """The seed_mock_provider helper creates a provider named 'mock' (default)."""
    _nav.goto(page, app_with_provider.base_url, "settings/providers")
    tile = page.locator('[data-testid="provider-card"]')
    expect(tile).to_be_visible(timeout=8000)
    expect(tile).to_have_class(re.compile(r"\bentity-tile\b"))
    expect(tile.locator(".entity-tile-name")).to_have_text("mock")
    # Type badge
    expect(tile.locator(".entity-tile-badge")).to_be_visible()
    # Provider type badge text
    expect(tile.locator(".entity-tile-badge")).to_have_text("mock")


@pytest.mark.browser
def test_new_provider_canvas_cta_navigates_to_new_url(app_clean: str, page: Page) -> None:
    """EMPTY state: the in-canvas duplicate CTA opens the create editor
    (same handler as the header CTA)."""
    _nav.goto(page, app_clean, "settings/providers")
    expect(page.locator(".empty-canvas .empty-canvas-cta")).to_be_visible(timeout=8000)
    page.locator(".empty-canvas .empty-canvas-cta").click()
    # Editor opens (post-leg-03 uses .editor-title with "New Provider").
    expect(page.locator(".editor-title")).to_have_text("New Provider", timeout=5000)
    _nav.expect_route(page, "settings/providers/~new")


@pytest.mark.browser
def test_new_provider_header_cta_navigates_to_new_url(
    app_with_provider: SeededApp, page: Page
) -> None:
    """POPULATED state: the unified header CTA opens the create editor."""
    _nav.goto(page, app_with_provider.base_url, "settings/providers")
    expect(page.locator('[data-testid="new-provider-btn"]')).to_be_visible(timeout=8000)
    page.locator('[data-testid="new-provider-btn"]').click()
    expect(page.locator(".editor-title")).to_have_text("New Provider", timeout=5000)
    _nav.expect_route(page, "settings/providers/~new")


@pytest.mark.browser
def test_create_url_refresh_preserves_create_mode(app_clean: str, page: Page) -> None:
    _nav.goto(page, app_clean, "settings/providers/~new")
    expect(page.locator(".editor-title")).to_have_text("New Provider", timeout=8000)
    page.reload()
    expect(page.locator(".editor-title")).to_have_text("New Provider", timeout=8000)
    _nav.expect_route(page, "settings/providers/~new")


@pytest.mark.browser
def test_tile_click_navigates_to_provider_detail(app_with_provider: SeededApp, page: Page) -> None:
    _nav.goto(page, app_with_provider.base_url, "settings/providers")
    tile = page.locator('[data-testid="provider-card"]')
    expect(tile).to_be_visible(timeout=8000)
    tile.click()
    # Post-leg-03: editor title is the provider name (seeded "mock"), not "Edit Provider".
    expect(page.locator(".editor-title")).to_have_text("mock", timeout=5000)
    route = _nav.current_route(page)
    assert route.startswith("settings/providers/"), f"expected /providers/<id>, got {route}"
    # The id portion should not be the create segment (we clicked an existing tile)
    suffix = route[len("settings/providers/") :]
    assert suffix != "~new"


@pytest.mark.browser
def test_provider_detail_url_refresh_preserves_editor(
    app_with_provider: SeededApp, page: Page
) -> None:
    _nav.goto(page, app_with_provider.base_url, "settings/providers")
    tile = page.locator('[data-testid="provider-card"]')
    expect(tile).to_be_visible(timeout=8000)
    tile.click()
    # Post-leg-03: editor title is the provider name (seeded "mock").
    expect(page.locator(".editor-title")).to_have_text("mock", timeout=5000)
    saved_route = _nav.current_route(page)
    page.reload()
    expect(page.locator(".editor-title")).to_have_text("mock", timeout=8000)
    _nav.expect_route(page, saved_route)


@pytest.mark.browser
def test_cancel_from_create_returns_to_grid(app_clean: str, page: Page) -> None:
    _nav.goto(page, app_clean, "settings/providers/~new")
    expect(page.locator(".editor-title")).to_have_text("New Provider", timeout=8000)
    # Clean form — Cancel disabled, use Back to return to the grid.
    page.locator('[data-testid="back-provider-btn"]').click()
    expect(page.locator(".area-admin .page-title")).to_have_text("LLM Providers", timeout=5000)
    _nav.expect_route(page, "settings/providers")


@pytest.mark.browser
def test_unknown_provider_id_falls_back_to_grid(app_clean: str, page: Page) -> None:
    """An unknown provider id (legacy deep link) redirects, then heals to the grid.

    The legacy `#admin/providers/<bogus>` redirects to `settings/providers/<bogus>`;
    the id is absent from the fresh provider fetch, so the dead pending id is
    never kept: the URL heals to `settings/providers` and the grid renders with
    no tile selected.
    """
    # legacy URL on purpose (AC6)
    page.goto(f"{app_clean}#admin/providers/00000000-bogus-id-0000-000000000000")
    # No providers exist (app_clean), so the grid renders the empty state.
    # The page should NOT crash; either grid or empty-state should show.
    fallback = page.locator(".area-admin .page-header, .editor-error").first
    expect(fallback).to_be_visible(timeout=8000)
    _nav.expect_route(page, "settings/providers")
