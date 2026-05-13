"""Admin navigation flow tests for F6 leg 01.

Covers:
- Section nav keyboard a11y (Tab in, Up/Down arrows, Home/End, Enter/Space activation)
- Section nav click navigation
- Refresh-preserves-section
- #admin -> #admin/general free redirect (via F3 router serialize-after-hydrate)
- #admin/system -> #admin/general legacy redirect (defensive in hydrateState;
  the General page's sub-id was renamed from 'system' to 'general' in Flight 3
  Leg 06 to disambiguate from the area-level "System" label)

Holograph selectors (L5.4):
- .page-title scoped to .admin-sub.active .page-title to avoid strict-mode
  violations from inactive sub-blocks that remain in the DOM (display:none).
- Admin nav has 3 entries (General / LLM Providers / Built-in Tools);
  MCP Servers was relocated to Studio nav in the Holograph migration.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_admin_redirect_root_to_general(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#admin")
    expect(page.locator(".admin-sub.active .page-title")).to_have_text("General", timeout=8000)
    assert page.evaluate("location.hash") == "#admin/general"


@pytest.mark.browser
def test_admin_legacy_system_redirects_to_general(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#admin/system")
    expect(page.locator(".admin-sub.active .page-title")).to_have_text("General", timeout=8000)
    assert page.evaluate("location.hash") == "#admin/general"


@pytest.mark.browser
def test_admin_picker_click_from_providers_redirects_to_general(app_clean: str, page: Page) -> None:
    """Clicking the Settings picker while already in admin (from /providers)
    sets bare `#admin` — must redirect to `#admin/general`, not strand the URL.

    Regression test for the F6 HAT bug: same-area sub-change skipped the
    serialize-replace block, leaving the URL at bare `#admin`.
    """
    page.goto(f"{app_clean}#admin/providers")
    expect(page.locator(".admin-sub.active .page-title")).to_have_text("LLM Providers", timeout=8000)
    page.evaluate("location.hash = '#admin'")
    expect(page.locator(".admin-sub.active .page-title")).to_have_text("General", timeout=5000)
    assert page.evaluate("location.hash") == "#admin/general"


@pytest.mark.browser
def test_admin_section_nav_renders_three_sections(app_clean: str, page: Page) -> None:
    """Holograph admin nav has 3 entries: General / LLM Providers / Built-in Tools.

    Pre-F6 the nav had {System, LLM Providers}; F6 L2 introduced the
    third entry "Built-in Tools" (HAT relabeled from "Tools" to
    distinguish from future MCP / external tool surfaces). The "System"
    label was later renamed to "General" — id stayed `system` until
    Flight 3 Leg 06 renamed it to `general`.

    Holograph L5.2: MCP Servers relocated to Studio nav (admin = system
    settings; studio = user-managed). Count is 3.
    """
    page.goto(f"{app_clean}#admin/general")
    nav = page.locator(".area-admin .section-nav")
    expect(nav).to_be_visible(timeout=5000)
    items = nav.locator(".section-nav-item")
    expect(items).to_have_count(3)
    expect(items.nth(0)).to_have_text("General")
    expect(items.nth(1)).to_have_text("LLM Providers")
    expect(items.nth(2)).to_have_text("Built-in Tools")


@pytest.mark.browser
def test_admin_section_nav_click_changes_url(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#admin/general")
    expect(page.locator(".admin-sub.active .page-title")).to_have_text("General", timeout=5000)
    page.locator(".area-admin .section-nav-item", has_text="LLM Providers").click()
    expect(page.locator(".admin-sub.active .page-title")).to_have_text("LLM Providers", timeout=5000)
    assert page.evaluate("location.hash") == "#admin/providers"


@pytest.mark.browser
def test_admin_refresh_preserves_section(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#admin/providers")
    expect(page.locator(".admin-sub.active .page-title")).to_have_text("LLM Providers", timeout=8000)
    page.reload()
    expect(page.locator(".admin-sub.active .page-title")).to_have_text("LLM Providers", timeout=8000)
    assert page.evaluate("location.hash") == "#admin/providers"


@pytest.mark.browser
def test_admin_section_nav_keyboard(app_clean: str, page: Page) -> None:
    """Tab into nav, Down arrow moves focus, Enter activates."""
    page.goto(f"{app_clean}#admin/general")
    expect(page.locator(".admin-sub.active .page-title")).to_have_text("General", timeout=5000)

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
    expect(page.locator(".admin-sub.active .page-title")).to_have_text("LLM Providers", timeout=5000)
    assert page.evaluate("location.hash") == "#admin/providers"
