"""Picker + skip-link browser tests (F3 leg 02)."""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_picker_renders_closed(app_clean: str, page: Page) -> None:
    page.goto(app_clean)
    expect(page.locator(".app-picker-button")).to_have_attribute("aria-expanded", "false")
    expect(page.locator(".app-picker-popover")).to_have_attribute("data-open", "false")


@pytest.mark.browser
def test_picker_opens_on_click(app_clean: str, page: Page) -> None:
    page.goto(app_clean)
    page.click(".app-picker-button")
    expect(page.locator(".app-picker-button")).to_have_attribute("aria-expanded", "true")
    expect(page.locator(".app-picker-popover")).to_have_attribute("data-open", "true")
    options = page.locator(".app-picker-option")
    expect(options).to_have_count(3)


@pytest.mark.browser
def test_picker_keyboard_open_close(app_clean: str, page: Page) -> None:
    page.goto(app_clean)
    page.locator(".app-picker-button").focus()
    page.keyboard.press("Enter")
    expect(page.locator(".app-picker-popover")).to_have_attribute("data-open", "true")
    page.keyboard.press("Escape")
    expect(page.locator(".app-picker-popover")).to_have_attribute("data-open", "false")


@pytest.mark.browser
def test_skip_link_first_tab(app_clean: str, page: Page) -> None:
    page.goto(app_clean)
    page.keyboard.press("Tab")
    active = page.evaluate("document.activeElement.className")
    assert "skip-link" in active, f"First Tab should land skip-link; got: {active!r}"
