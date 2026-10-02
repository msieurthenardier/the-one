"""Admin navigation flow tests for F6 leg 01.

Covers:
- Section nav keyboard a11y (Tab in, Up/Down arrows, Home/End, Enter/Space activation)
- Section nav click navigation
- Refresh-preserves-section
- #admin -> #admin/general free redirect (via F3 router serialize-after-hydrate)
- #admin/system -> #admin/general legacy redirect (defensive in hydrateState;
  the General page's sub-id was renamed from 'system' to 'general' in Flight 3
  Leg 06 to disambiguate from the area-level "System" label)
"""

from __future__ import annotations

import pytest
from browser import _nav
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_admin_redirect_root_to_general(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#admin")  # legacy URL on purpose: proves the redirect (AC6)
    expect(page.locator(".page-title")).to_have_text("General", timeout=8000)
    _nav.expect_route(page, "settings/general")


@pytest.mark.browser
def test_admin_legacy_system_redirects_to_general(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#admin/system")  # legacy URL on purpose: proves the redirect (AC6)
    expect(page.locator(".page-title")).to_have_text("General", timeout=8000)
    _nav.expect_route(page, "settings/general")


@pytest.mark.browser
def test_admin_picker_click_from_providers_redirects_to_general(app_clean: str, page: Page) -> None:
    """Clicking the Settings rail link while already in admin (from /providers)
    sets bare `#admin` — must redirect to `#admin/general`, not strand the URL.

    Regression test for the F6 HAT bug: same-area sub-change skipped the
    serialize-replace block, leaving the URL at bare `#admin`.
    """
    _nav.goto(page, app_clean, "settings/providers")
    expect(page.locator(".page-title")).to_have_text("LLM Providers", timeout=8000)
    _nav.set_route(page, "settings")
    expect(page.locator(".page-title")).to_have_text("General", timeout=5000)
    _nav.expect_route(page, "settings/general")


@pytest.mark.browser
def test_admin_section_nav_renders_three_sections(app_clean: str, page: Page) -> None:
    """F6 L7: nav has 3 stable entries (General, LLM Providers, Built-in Tools).

    Pre-F6 the nav had {System, LLM Providers}; F6 L2 introduced the
    third entry "Built-in Tools" (HAT relabeled from "Tools" to
    distinguish from future MCP / external tool surfaces). The "System"
    label was later renamed to "General" — id stayed `system` until
    Flight 3 Leg 06 renamed it to `general`.

    MCP Servers was originally added (M07 F1 L5) but was later relocated
    to the Studio nav post-F2 retrofit (admin = system settings,
    studio = user-managed). Design Language is a dev_mode-only 4th entry.
    This test asserts the 3 always-present sections by label.
    """
    _nav.goto(page, app_clean, "settings/general")
    nav = page.locator(".area-admin .section-nav")
    expect(nav).to_be_visible(timeout=5000)
    # Assert the 3 stable (non-dev-mode) sections are present in order.
    expect(nav.locator(".section-nav-item", has_text="General")).to_be_visible()
    expect(nav.locator(".section-nav-item", has_text="LLM Providers")).to_be_visible()
    expect(nav.locator(".section-nav-item", has_text="Built-in Tools")).to_be_visible()
    # MCP Servers was relocated to Studio nav — must NOT appear in admin.
    expect(nav.locator(".section-nav-item", has_text="MCP Servers")).to_have_count(0)


@pytest.mark.browser
def test_admin_section_nav_click_changes_url(app_clean: str, page: Page) -> None:
    _nav.goto(page, app_clean, "settings/general")
    expect(page.locator(".page-title")).to_have_text("General", timeout=5000)
    page.locator(".area-admin .section-nav-item", has_text="LLM Providers").click()
    expect(page.locator(".page-title")).to_have_text("LLM Providers", timeout=5000)
    _nav.expect_route(page, "settings/providers")


@pytest.mark.browser
def test_admin_refresh_preserves_section(app_clean: str, page: Page) -> None:
    _nav.goto(page, app_clean, "settings/providers")
    expect(page.locator(".page-title")).to_have_text("LLM Providers", timeout=8000)
    page.reload()
    expect(page.locator(".page-title")).to_have_text("LLM Providers", timeout=8000)
    _nav.expect_route(page, "settings/providers")


@pytest.mark.browser
def test_admin_section_nav_keyboard(app_clean: str, page: Page) -> None:
    """Tab into nav, Down arrow moves focus, Enter activates."""
    _nav.goto(page, app_clean, "settings/general")
    expect(page.locator(".page-title")).to_have_text("General", timeout=5000)

    # Tab focuses the active item (General).
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
    _nav.expect_route(page, "settings/providers")
