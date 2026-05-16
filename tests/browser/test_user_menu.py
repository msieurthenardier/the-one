"""L9 — User menu behavior."""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_user_menu_opens_on_avatar_click(app_clean: str, page: Page) -> None:
    page.goto(app_clean)
    page.locator(".avatar").click()
    expect(page.locator('[data-testid="user-menu"]')).to_be_visible()


@pytest.mark.browser
def test_user_menu_theme_switch(app_clean: str, page: Page) -> None:
    page.goto(app_clean)
    page.evaluate("() => window.App.theme.set('dark')")
    page.locator(".avatar").click()
    expect(page.locator('[data-testid="user-menu"]')).to_be_visible()
    # The Light radio comes from App.theme.renderToggle — match by role + name.
    page.get_by_role("radio", name="Light").click()
    page.wait_for_function(
        "() => document.documentElement.getAttribute('data-theme') === 'light'",
        timeout=2000,
    )


@pytest.mark.browser
def test_user_menu_system_link(app_clean: str, page: Page) -> None:
    page.goto(app_clean)
    page.locator(".avatar").click()
    page.get_by_role("menuitem", name="System → General").click()
    page.wait_for_function(
        "() => window.location.hash === '#admin/general'",
        timeout=2000,
    )
    expect(page.locator('[data-testid="user-menu"]')).to_be_hidden()


@pytest.mark.browser
def test_user_menu_version_footer(app_clean: str, page: Page) -> None:
    page.goto(app_clean)
    page.locator(".avatar").click()
    footer = page.locator(".user-menu-version")
    expect(footer).to_be_visible()
    text = footer.text_content() or ""
    assert text.startswith("Holograph v"), f"Unexpected version footer: {text!r}"
    assert "unknown" not in text, "Version not read from App.config.version"


@pytest.mark.browser
def test_user_menu_closes_on_outside_click(app_clean: str, page: Page) -> None:
    page.goto(app_clean)
    page.locator(".avatar").click()
    expect(page.locator('[data-testid="user-menu"]')).to_be_visible()
    page.locator("body").click(position={"x": 5, "y": 200})
    expect(page.locator('[data-testid="user-menu"]')).to_be_hidden()
