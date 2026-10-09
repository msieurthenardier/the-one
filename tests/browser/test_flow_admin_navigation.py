"""Admin navigation flow tests (F6 leg 01; Settings nav since M25 F3 leg 5a).

Covers:
- The Settings nav (``App.ui.navGroups``): its stable pages, link navigation,
  and Enter on a focused link (the links are plain ``<a href>`` in Tab order;
  the full Tab-order walk is ``test_flow_keyboard.py``)
- Refresh-preserves-section
- ``#admin`` -> ``#settings/appearance`` (legacy root redirect)
- ``#admin/system`` -> ``#settings/appearance`` (the General page's interim
  sub-id; since M25 F3 leg 5a General is three pages and the legacy subs land on
  the first, Appearance, directly)

The new-scheme redirects (``#settings/general`` and its suffixes, the rail's
first-use href, ``lastRoute``) are ``test_flow_admin_settings_nav.py``.
"""

from __future__ import annotations

import pytest
from browser import _lists, _nav
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_admin_picker_click_from_providers_redirects_to_appearance(
    app_clean: str, page: Page
) -> None:
    """Going to bare ``#settings`` while already in Settings (from /providers)
    must land on the root page, ``#settings/appearance``, not strand the URL.

    Regression test for the F6 HAT bug: same-area sub-change skipped the
    serialize-replace block, leaving the URL at the bare destination.
    """
    _nav.goto(page, app_clean, "settings/providers")
    expect(_lists.settings_page_title(page)).to_have_text("Providers", timeout=8000)
    _nav.set_route(page, "settings")
    expect(_lists.settings_page_title(page)).to_have_text("Appearance", timeout=5000)
    _nav.expect_route(page, "settings/appearance")
    _lists.expect_settings_selected(page, "appearance")


@pytest.mark.browser
def test_admin_settings_nav_renders_the_stable_pages(app_clean: str, page: Page) -> None:
    """The nav's six always-present pages (Design language is dev-mode only).

    MCP Servers was originally an admin section (M07 F1 L5) but was relocated
    to Studio (now the Library) post-F2 retrofit (admin = system settings,
    studio = user-managed); it must NOT appear in Settings.
    """
    _nav.goto(page, app_clean, "settings/appearance")
    nav = _lists.settings_nav(page)
    expect(nav).to_be_visible(timeout=5000)
    for section in ("appearance", "prompts", "encryption", "providers", "tools"):
        expect(_lists.settings_nav_link(page, section)).to_have_text(
            _lists.SETTINGS_PAGE_TITLES[section]
        )
    expect(_lists.settings_nav_link(page, "knowledge-indexing")).to_have_text("Knowledge indexing")
    expect(nav.get_by_role("link", name="MCP servers", exact=False)).to_have_count(0)


@pytest.mark.browser
def test_admin_settings_nav_click_changes_url(app_clean: str, page: Page) -> None:
    _nav.goto(page, app_clean, "settings/appearance")
    expect(_lists.settings_page_title(page)).to_have_text("Appearance", timeout=5000)
    _lists.open_settings_page(page, "providers")
    _lists.expect_settings_selected(page, "providers")


@pytest.mark.browser
def test_admin_refresh_preserves_section(app_clean: str, page: Page) -> None:
    _nav.goto(page, app_clean, "settings/providers")
    expect(_lists.settings_page_title(page)).to_have_text("Providers", timeout=8000)
    page.reload()
    expect(_lists.settings_page_title(page)).to_have_text("Providers", timeout=8000)
    _nav.expect_route(page, "settings/providers")
    _lists.expect_settings_selected(page, "providers")


@pytest.mark.browser
def test_admin_settings_nav_enter_on_a_focused_link(app_clean: str, page: Page) -> None:
    """A focused nav link activates on Enter (a plain link: no roving tabindex)."""
    _nav.goto(page, app_clean, "settings/appearance")
    expect(_lists.settings_page_title(page)).to_have_text("Appearance", timeout=5000)
    providers = _lists.settings_nav_link(page, "providers")
    providers.focus()
    expect(providers).to_be_focused()
    page.keyboard.press("Enter")
    expect(_lists.settings_page_title(page)).to_have_text("Providers", timeout=5000)
    _nav.expect_route(page, "settings/providers")
    _lists.expect_settings_selected(page, "providers")
