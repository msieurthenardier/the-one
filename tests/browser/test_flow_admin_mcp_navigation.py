"""Admin MCP Sources navigation flow tests for M07 F1 L5/L6.

Covers:
- Section nav now includes "MCP Servers" (4th entry)
- Click "MCP Servers" → URL becomes #admin/mcp-sources
- Direct-load #admin/mcp-sources renders the MCP Servers page
- Direct-load #admin/mcp-sources/new renders the editor (L6 replaced the
  L5 placeholder with App.admin.renderMcpSourceEditor)
- Refresh on #admin/mcp-sources preserves the section
- Empty grid shows the centered CTA (precondition: empty mcp_sources table)

Note: App.areas is closure-private in app.js, so tests use BEHAVIORAL DOM
assertions (e.g., `[data-testid="save-mcp-source-btn"]` visible) rather
than state introspection.

L6 history: ``test_admin_direct_load_mcp_sources_new_renders_placeholder``
was refactored to assert the editor renders.
``test_admin_mcp_placeholder_navigation_skips_confirm`` was deleted because
the placeholder no longer exists; coverage moved to
``test_flow_admin_mcp_editor.py`` (dirty/clean editor navigation tests).
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_admin_section_nav_includes_mcp_servers(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#admin/system")
    nav = page.locator(".area-admin .section-nav")
    expect(nav).to_be_visible(timeout=5000)
    items = page.locator(".area-admin .section-nav-item")
    expect(items).to_have_count(4)
    labels = items.evaluate_all("els => els.map(e => e.textContent.trim())")
    assert "MCP Servers" in labels


@pytest.mark.browser
def test_admin_section_nav_click_to_mcp_sources(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#admin/system")
    expect(page.locator(".page-title")).to_have_text("General", timeout=5000)
    page.locator(".area-admin .section-nav-item", has_text="MCP Servers").click()
    expect(page.locator(".page-title")).to_have_text("MCP Servers", timeout=5000)
    assert page.evaluate("location.hash") == "#admin/mcp-sources"


@pytest.mark.browser
def test_admin_direct_load_mcp_sources(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#admin/mcp-sources")
    page.wait_for_selector(".area-admin .page-title", timeout=8000)
    assert page.locator(".area-admin .page-title").text_content().strip() == "MCP Servers"


@pytest.mark.browser
def test_admin_direct_load_mcp_sources_new_renders_editor(
    app_clean: str, page: Page
) -> None:
    """Direct-load to the create route renders the editor (L6).

    L5 staged a placeholder with data-testid="mcp-editor-placeholder";
    L6 replaced that placeholder with App.admin.renderMcpSourceEditor,
    which renders the canonical editor scaffold (header / save button /
    name input). We assert the editor's save button is present as the
    BEHAVIORAL contract — App.areas state introspection is not possible
    because App.areas is closure-private in app.js.
    """
    page.goto(f"{app_clean}#admin/mcp-sources/new")
    save_btn = page.locator('[data-testid="save-mcp-source-btn"]')
    expect(save_btn).to_be_visible(timeout=8000)
    expect(page.locator('[data-field="name"]')).to_be_visible()
    # The L5 placeholder is no longer rendered.
    assert page.locator('[data-testid="mcp-editor-placeholder"]').count() == 0


@pytest.mark.browser
def test_admin_refresh_preserves_mcp_sources_section(
    app_clean: str, page: Page
) -> None:
    page.goto(f"{app_clean}#admin/mcp-sources")
    page.wait_for_selector(".area-admin .page-title", timeout=8000)
    page.reload()
    page.wait_for_selector(".area-admin .page-title", timeout=8000)
    assert page.evaluate("location.hash") == "#admin/mcp-sources"


@pytest.mark.browser
def test_admin_mcp_sources_empty_grid_shows_cta(app_clean: str, page: Page) -> None:
    """Empty mcp_sources table → empty-canvas with centered CTA renders."""
    page.goto(f"{app_clean}#admin/mcp-sources")
    page.wait_for_selector('[data-testid="new-mcp-source-btn-empty"]', timeout=8000)
    cta = page.locator('[data-testid="new-mcp-source-btn-empty"]')
    expect(cta).to_be_visible()
