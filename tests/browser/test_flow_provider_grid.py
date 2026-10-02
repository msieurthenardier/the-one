"""Providers page: page header, table, empty state and hash routing.

Rewritten against post-M08-F4-rebrand markup in M17 F1 L02; re-simplified to
the unified create-CTA contract in M17 F3 L3; since M25 F3 leg 5b the tile grid
is the reference spec section 8.2 TABLE (the file keeps its name). Covers:

- The Providers page renders .page-header with title "Providers" and the
  header "+ Add provider" CTA, ALWAYS visible (empty and populated states).
- The table: intro, Name / Type / Used by columns, the name link
  (``provider-card``, ``data-id``) and the type badge.
- Clicking a name navigates to #settings/providers/{id}; refresh preserves.
- "+ Add provider" navigates to #settings/providers/~new; refresh preserves.
- The breadcrumb's "Providers" link closes a clean create form.
- Unknown provider id keeps URL stable; the table renders.

Unified create CTA (M17 F3 L3): one always-visible header button
(``new-provider-btn``). The zero-providers empty state (``providers-empty``,
leg 5b) carries a second "Add provider" (``providers-empty-add``).
"""

from __future__ import annotations

import pytest
from browser import _lists, _nav
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_provider_grid_page_header_empty_state(app_clean: str, page: Page) -> None:
    """EMPTY state: the unified header CTA is visible with its text label; the
    empty state renders its own "Add provider" action."""
    _nav.goto(page, app_clean, "settings/providers")
    expect(page.locator(".area-admin .page-header")).to_be_visible(timeout=8000)
    expect(page.locator(".area-admin .page-title")).to_have_text("Providers")
    header_cta = page.locator('[data-testid="new-provider-btn"]')
    expect(header_cta).to_be_visible()
    expect(header_cta).to_contain_text("Add provider")
    expect(page.locator('[data-testid="providers-empty-add"]')).to_be_visible()
    expect(page.locator('[data-testid="providers-empty-add"]')).to_contain_text("Add provider")


@pytest.mark.browser
def test_provider_grid_page_header_populated(app_with_provider: SeededApp, page: Page) -> None:
    """POPULATED state: the same unified header CTA is visible."""
    _nav.goto(page, app_with_provider.base_url, "settings/providers")
    expect(page.locator(".area-admin .page-header")).to_be_visible(timeout=8000)
    expect(page.locator(".area-admin .page-title")).to_have_text("Providers")
    header_cta = page.locator('[data-testid="new-provider-btn"]')
    expect(header_cta).to_be_visible()
    expect(header_cta).to_contain_text("Add provider")


@pytest.mark.browser
def test_provider_grid_empty_state(app_clean: str, page: Page) -> None:
    """Zero providers: a pane-size empty state, no table."""
    _nav.goto(page, app_clean, "settings/providers")
    empty = page.locator('[data-testid="providers-empty"]')
    expect(empty).to_be_visible(timeout=8000)
    expect(empty.get_by_role("heading", level=2)).to_have_text("No providers yet.")
    expect(_lists.providers_table(page)).to_have_count(0)


@pytest.mark.browser
def test_provider_grid_renders_tiles(app_with_provider: SeededApp, page: Page) -> None:
    """The seed_mock_provider helper creates a provider named 'mock' (default):
    its table row shows the name link, the type badge and the used-by count."""
    _nav.goto(page, app_with_provider.base_url, "settings/providers")
    link = _lists.list_row(page, "settings/providers", "mock")
    expect(link).to_be_visible(timeout=8000)
    expect(link).to_have_attribute(
        "href", _nav.href(f"settings/providers/{app_with_provider.provider_id}")
    )
    expect(link).to_have_attribute("data-id", app_with_provider.provider_id)
    row = _lists.providers_table(page).locator("tbody tr")
    expect(row).to_have_count(1)
    # The Name cell is the row header (th scope=row); Type and Used by are data cells.
    expect(row.locator('th[scope="row"] [data-testid="provider-card"]')).to_have_count(1)
    cells = row.locator("td")
    expect(cells).to_have_count(2)
    expect(cells.nth(0).locator(".badge.badge--mock")).to_have_text("mock")
    expect(cells.nth(1)).to_have_text("0 agents")


@pytest.mark.browser
def test_new_provider_canvas_cta_navigates_to_new_url(app_clean: str, page: Page) -> None:
    """EMPTY state: the empty state's "Add provider" opens the create editor
    (same intent as the header CTA)."""
    _nav.goto(page, app_clean, "settings/providers")
    action = page.locator('[data-testid="providers-empty-add"]')
    expect(action).to_be_visible(timeout=8000)
    action.click()
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
    _lists.open_item(page, "settings/providers", "mock")
    # Post-leg-03: editor title is the provider name (seeded "mock"), not "Edit Provider".
    expect(page.locator(".editor-title")).to_have_text("mock", timeout=5000)
    _nav.expect_route(page, f"settings/providers/{_nav.seg(app_with_provider.provider_id)}")
    # The table stays above the open provider (leg 5b).
    expect(_lists.providers_table(page)).to_be_visible()


@pytest.mark.browser
def test_provider_detail_url_refresh_preserves_editor(
    app_with_provider: SeededApp, page: Page
) -> None:
    _nav.goto(page, app_with_provider.base_url, "settings/providers")
    _lists.open_item(page, "settings/providers", "mock")
    # Post-leg-03: editor title is the provider name (seeded "mock").
    expect(page.locator(".editor-title")).to_have_text("mock", timeout=5000)
    saved_route = _nav.current_route(page)
    page.reload()
    expect(page.locator(".editor-title")).to_have_text("mock", timeout=8000)
    _nav.expect_route(page, saved_route)
    _lists.expect_selected(page, "settings/providers", "mock")


@pytest.mark.browser
def test_cancel_from_create_returns_to_grid(app_clean: str, page: Page) -> None:
    """A clean create form closes through the breadcrumb's "Providers" link
    (Back is retired, leg 5b). Cancel is enabled on it too since the flight's
    behavior-gate fix; focus after either close is pinned in
    `test_flow_settings_items.py`."""
    _nav.goto(page, app_clean, "settings/providers/~new")
    expect(page.locator(".editor-title")).to_have_text("New Provider", timeout=8000)
    _lists.close_item(page)
    expect(page.locator(".editor-title")).to_have_count(0, timeout=5000)
    expect(page.locator(".area-admin .page-title")).to_have_text("Providers")
    _nav.expect_route(page, "settings/providers")


@pytest.mark.browser
def test_unknown_provider_id_falls_back_to_grid(app_clean: str, page: Page) -> None:
    """An unknown provider id (legacy deep link) redirects, then heals to the root.

    The legacy `#admin/providers/<bogus>` redirects to `settings/providers/<bogus>`;
    the id is absent from the fresh provider fetch, so the dead pending id is
    never kept: the URL heals to `settings/providers` and the page renders with
    no row selected and no editor.
    """
    # legacy URL on purpose (AC6)
    page.goto(f"{app_clean}#admin/providers/00000000-bogus-id-0000-000000000000")
    # No providers exist (app_clean), so the page renders the empty state.
    expect(page.locator('[data-testid="providers-empty"]')).to_be_visible(timeout=8000)
    _nav.expect_route(page, "settings/providers")
    expect(page.locator(".editor-title")).to_have_count(0)
