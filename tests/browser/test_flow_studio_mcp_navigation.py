"""Studio MCP Sources navigation flow tests.

Originally `test_flow_admin_mcp_navigation.py` (M07 F1 L5/L6 — admin nav);
relocated to studio post-F2 retrofit because MCP sources are user-managed
entities, not system settings.

Covers:
- Studio section nav has 4 entries (Agents / Knowledge / MCP Servers /
  Connectors — the Tools stub was replaced by MCP Servers in the F2
  retrofit; Connector Accounts (renamed to "Connectors" in F5 L8 HAT)
  was added in M10 F2 leg 05)
- Click "MCP Servers" → URL becomes #studio/mcp-sources
- Direct-load #studio/mcp-sources renders the MCP Servers page
- Direct-load #studio/mcp-sources/new renders the editor
- Refresh on #studio/mcp-sources preserves the section
- Empty grid shows the empty-canvas; the unified header CTA
  (new-mcp-source-btn, M17 F3 L3) is visible (precondition: empty
  mcp_sources table)

Note: App.areas is closure-private in app.js, so tests use BEHAVIORAL DOM
assertions (e.g., `[data-testid="save-mcp-source-btn"]` visible) rather
than state introspection.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_studio_section_nav_includes_mcp_servers(app_clean: str, page: Page) -> None:
    """Studio section nav has 4 entries: Agents | Knowledge | MCP Servers | Connectors.

    F5 L8 HAT: the fourth label was renamed from "Connector Accounts" → "Connectors".
    """
    page.goto(f"{app_clean}#studio")
    nav = page.locator(".area-studio .section-nav")
    expect(nav).to_be_visible(timeout=5000)
    items = page.locator(".area-studio .section-nav-item")
    expect(items).to_have_count(4)
    labels = items.evaluate_all("els => els.map(e => e.textContent.trim())")
    assert labels == ["Agents", "Knowledge", "MCP Servers", "Connectors"]


@pytest.mark.browser
def test_studio_section_nav_click_to_mcp_sources(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#studio")
    expect(page.locator(".area-studio .section-nav")).to_be_visible(timeout=5000)
    page.locator(".area-studio .section-nav-item", has_text="MCP Servers").click()
    expect(page.locator(".area-studio .page-title")).to_have_text("MCP Servers", timeout=5000)
    assert page.evaluate("location.hash") == "#studio/mcp-sources"


@pytest.mark.browser
def test_studio_direct_load_mcp_sources(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#studio/mcp-sources")
    page.wait_for_selector(".area-studio .page-title", timeout=8000)
    assert page.locator(".area-studio .page-title").text_content().strip() == "MCP Servers"


@pytest.mark.browser
def test_studio_direct_load_mcp_sources_new_renders_editor(app_clean: str, page: Page) -> None:
    """Direct-load to the create route renders the editor.

    Asserts the editor's save button + name input are present as the
    BEHAVIORAL contract — App.areas state introspection is not possible
    because App.areas is closure-private in app.js.
    """
    page.goto(f"{app_clean}#studio/mcp-sources/new")
    save_btn = page.locator('[data-testid="save-mcp-source-btn"]')
    expect(save_btn).to_be_visible(timeout=8000)
    expect(page.locator('[data-field="name"]')).to_be_visible()


@pytest.mark.browser
def test_studio_refresh_preserves_mcp_sources_section(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#studio/mcp-sources")
    page.wait_for_selector(".area-studio .page-title", timeout=8000)
    page.reload()
    page.wait_for_selector(".area-studio .page-title", timeout=8000)
    assert page.evaluate("location.hash") == "#studio/mcp-sources"


@pytest.mark.browser
def test_studio_mcp_sources_empty_grid_shows_cta(app_clean: str, page: Page) -> None:
    """Empty mcp_sources table → empty-canvas renders; the unified header
    CTA (M17 F3 L3) is visible in the empty state."""
    page.goto(f"{app_clean}#studio/mcp-sources")
    # The empty canvas is the synchronization point for the fetch resolving
    # to an empty inventory (the header CTA renders before the fetch).
    page.wait_for_selector(".empty-canvas", timeout=8000)
    expect(page.locator('[data-testid="new-mcp-source-btn"]')).to_be_visible()
