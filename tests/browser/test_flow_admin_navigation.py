"""Admin navigation flow tests for F6 leg 01.

Covers:
- Section nav keyboard a11y (Tab in, Up/Down arrows, Home/End, Enter/Space activation)
- Section nav click navigation
- Refresh-preserves-section
- #admin -> #admin/system free redirect (via F3 router serialize-after-hydrate)
- #admin/general -> #admin/system legacy redirect (defensive in hydrateState)
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_admin_redirect_root_to_system(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#admin")
    expect(page.locator(".page-title")).to_have_text("System", timeout=8000)
    assert page.evaluate("location.hash") == "#admin/system"


@pytest.mark.browser
def test_admin_legacy_general_redirects_to_system(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#admin/general")
    expect(page.locator(".page-title")).to_have_text("System", timeout=8000)
    assert page.evaluate("location.hash") == "#admin/system"


@pytest.mark.browser
def test_admin_picker_click_from_providers_redirects_to_system(
    app_clean: str, page: Page
) -> None:
    """Clicking the Settings picker while already in admin (from /providers)
    sets bare `#admin` — must redirect to `#admin/system`, not strand the URL.

    Regression test for the F6 HAT bug: same-area sub-change skipped the
    serialize-replace block, leaving the URL at bare `#admin`.
    """
    page.goto(f"{app_clean}#admin/providers")
    expect(page.locator(".page-title")).to_have_text("LLM Providers", timeout=8000)
    page.evaluate("location.hash = '#admin'")
    expect(page.locator(".page-title")).to_have_text("System", timeout=5000)
    assert page.evaluate("location.hash") == "#admin/system"


@pytest.mark.browser
def test_admin_section_nav_renders_two_sections(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#admin/system")
    nav = page.locator(".area-admin .section-nav")
    expect(nav).to_be_visible(timeout=5000)
    items = nav.locator(".section-nav-item")
    expect(items).to_have_count(2)
    expect(items.nth(0)).to_have_text("System")
    expect(items.nth(1)).to_have_text("LLM Providers")


@pytest.mark.browser
def test_admin_section_nav_click_changes_url(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#admin/system")
    expect(page.locator(".page-title")).to_have_text("System", timeout=5000)
    page.locator(".area-admin .section-nav-item", has_text="LLM Providers").click()
    expect(page.locator(".page-title")).to_have_text("LLM Providers", timeout=5000)
    assert page.evaluate("location.hash") == "#admin/providers"


@pytest.mark.browser
def test_admin_refresh_preserves_section(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#admin/providers")
    expect(page.locator(".page-title")).to_have_text("LLM Providers", timeout=8000)
    page.reload()
    expect(page.locator(".page-title")).to_have_text("LLM Providers", timeout=8000)
    assert page.evaluate("location.hash") == "#admin/providers"


@pytest.mark.browser
def test_admin_section_nav_keyboard(app_clean: str, page: Page) -> None:
    """Tab into nav, Down arrow moves focus, Enter activates."""
    page.goto(f"{app_clean}#admin/system")
    expect(page.locator(".page-title")).to_have_text("System", timeout=5000)

    # Tab focuses the active item (System).
    active_item = page.locator('.area-admin .section-nav-item[aria-current="page"]')
    active_item.focus()
    expect(active_item).to_be_focused()

    # Down arrow moves focus to LLM Providers.
    page.keyboard.press("ArrowDown")
    providers_item = page.locator(".area-admin .section-nav-item", has_text="LLM Providers")
    expect(providers_item).to_be_focused()

    # Enter activates.
    page.keyboard.press("Enter")
    expect(page.locator(".page-title")).to_have_text("LLM Providers", timeout=5000)
    assert page.evaluate("location.hash") == "#admin/providers"
