"""L8 — Command Palette end-to-end behavior."""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_palette_opens_on_cmd_k(app_clean: str, page: Page) -> None:
    page.goto(app_clean)
    page.keyboard.press("Meta+k")
    expect(page.locator('[data-testid="command-palette"]')).to_be_visible()
    expect(page.locator(".cp-input")).to_be_focused()


@pytest.mark.browser
def test_palette_navigates_to_providers(app_clean: str, page: Page) -> None:
    page.goto(app_clean)
    page.keyboard.press("Meta+k")
    expect(page.locator('[data-testid="command-palette"]')).to_be_visible()
    page.locator(".cp-input").fill("prov")
    # Wait for at least one ranked result.
    expect(page.locator(".cp-item.active")).to_be_visible()
    page.keyboard.press("Enter")
    expect(page.locator('[data-testid="command-palette"]')).to_be_hidden()
    page.wait_for_function("() => window.location.hash === '#admin/providers'", timeout=2000)


@pytest.mark.browser
def test_palette_toggles_theme(app_clean: str, page: Page) -> None:
    page.goto(app_clean)
    # Force a known starting state.
    page.evaluate("() => window.App.theme.set('dark')")
    page.keyboard.press("Meta+k")
    page.locator(".cp-input").fill("theme: light")
    page.keyboard.press("Enter")
    page.wait_for_function(
        "() => document.documentElement.getAttribute('data-theme') === 'light'",
        timeout=2000,
    )


@pytest.mark.browser
def test_palette_escape_restores_focus(app_clean: str, page: Page) -> None:
    page.goto(app_clean)
    # Open via the topnav trigger so focus restoration is observable.
    page.locator("#topnav-search").click()
    expect(page.locator('[data-testid="command-palette"]')).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator('[data-testid="command-palette"]')).to_be_hidden()
    expect(page.locator("#topnav-search")).to_be_focused()


@pytest.mark.browser
def test_palette_closes_on_hashchange(app_clean: str, page: Page) -> None:
    page.goto(app_clean)
    page.keyboard.press("Meta+k")
    expect(page.locator('[data-testid="command-palette"]')).to_be_visible()
    page.evaluate("() => { window.location.hash = '#studio'; }")
    expect(page.locator('[data-testid="command-palette"]')).to_be_hidden()
