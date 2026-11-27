"""Library MCP servers navigation flow tests.

Originally `test_flow_admin_mcp_navigation.py` (M07 F1 L5/L6 — admin nav);
relocated to studio post-F2 retrofit because MCP sources are user-managed
entities, not system settings. Since M25 F3 L4a MCP servers are the second
group of the Library list (the section nav and the tile grid are retired).

Covers:
- The Library list has the "MCP servers" group; the section nav is gone
- An MCP row opens its editor beside the list (``#library/mcp/{id}``)
- Direct-load ``#studio/mcp-sources`` (legacy) renders the MCP section root
- Direct-load ``#library/mcp/~new`` renders the editor
- Refresh on ``#library/mcp`` preserves the section
- An empty inventory shows the group's empty line and the section root's
  empty state, whose action opens the create form

Note: App.areas is closure-private in app.js, so tests use BEHAVIORAL DOM
assertions (e.g., `[data-testid="save-mcp-source-btn"]` visible) rather
than state introspection.
"""

from __future__ import annotations

import httpx
import pytest
from browser import _lists, _nav
from browser._credential_registry import auth_headers_for
from playwright.sync_api import Page, expect


def _seed_mcp(base: str, name: str) -> str:
    r = httpx.post(
        f"{base}/api/mcp-sources",
        json={"name": name, "type": "stdio", "config": {"command": "x"}, "secrets": {}},
        headers=auth_headers_for(base),
        timeout=5,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


@pytest.mark.browser
def test_library_list_has_the_mcp_group_and_no_section_nav(app_clean: str, page: Page) -> None:
    """The Library list's groups replace the section nav (DD5)."""
    _nav.goto_settled(page, app_clean, "library")
    library = page.locator('[data-testid="library-list"]')
    expect(library).to_be_visible(timeout=5000)
    captions = library.locator(".ui-list-pane-caption")
    expect(captions).to_have_text(
        ["Model providers", "Knowledge bases", "MCP servers", "Connectors", "Secrets"]
    )
    expect(page.locator(".area-studio .section-nav")).to_have_count(0)
    expect(page.get_by_role("navigation", name="Library sections")).to_have_count(0)


@pytest.mark.browser
def test_mcp_row_opens_its_editor_beside_the_list(app_clean: str, page: Page) -> None:
    _seed_mcp(app_clean, "nav-mcp")
    _nav.goto_settled(page, app_clean, "library")
    _lists.open_item(page, "library/mcp", "nav-mcp")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)
    _lists.expect_selected(page, "library/mcp", "nav-mcp")
    expect(page.locator('[data-testid="library-list"]')).to_be_visible()


@pytest.mark.browser
def test_studio_direct_load_mcp_sources(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#studio/mcp-sources")  # legacy URL on purpose (AC6)
    _nav.wait_router_started(page)
    _nav.expect_route(page, "library", timeout=8000)
    expect(_lists.library_start(page)).to_be_visible(timeout=8000)


@pytest.mark.browser
def test_studio_direct_load_mcp_sources_new_renders_editor(app_clean: str, page: Page) -> None:
    """Direct-load to the create route renders the editor.

    Asserts the editor's save button + name input are present as the
    BEHAVIORAL contract — App.areas state introspection is not possible
    because App.areas is closure-private in app.js.
    """
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    save_btn = page.locator('[data-testid="save-mcp-source-btn"]')
    expect(save_btn).to_be_visible(timeout=8000)
    expect(page.locator('[data-field="name"]')).to_be_visible()


@pytest.mark.browser
def test_studio_refresh_preserves_mcp_sources_section(app_clean: str, page: Page) -> None:
    _nav.goto_settled(page, app_clean, "library")
    expect(_lists.library_start(page)).to_be_visible(timeout=8000)
    page.reload()
    expect(_lists.library_start(page)).to_be_visible(timeout=8000)
    _nav.expect_route(page, "library")


@pytest.mark.browser
def test_studio_mcp_sources_empty_inventory_shows_group_line_and_add(
    app_clean: str, page: Page
) -> None:
    """Empty mcp_sources table: the group shows its empty line, and the section
    root's empty-state action opens the create form."""
    _nav.goto_settled(page, app_clean, "library")
    library = page.locator('[data-testid="library-list"]')
    expect(
        library.locator(".ui-list-pane-group-empty", has_text="No MCP servers yet.")
    ).to_be_visible(timeout=8000)
    page.locator('[data-testid="library-start-mcp-add"]').click()
    _nav.expect_route(page, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)
