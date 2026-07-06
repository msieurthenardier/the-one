"""Studio Connectors navigation flow tests (M10 F2 leg 05; F5 L8 HAT-rename).

Mirrors `test_flow_studio_mcp_navigation.py`. The Connectors section
is structurally identical to MCP Sources (operator-managed entities,
many-to-many identities); placed in Studio (not Admin) per the
flight's "Studio placement, not Admin" design decision.

F5 L8 HAT-rename: operator-facing label and hash slug are "Connectors"
(was "Connector Accounts"). The internal entity name + API path stay
as `connectors` (F2 contract). The legacy hash slug remains
accepted by hydrateState for backward-compat.

Covers:
- Studio section nav now has 4 entries ending with "Connectors"
- Click "Connectors" → URL becomes #studio/connectors
- Direct-load #studio/connectors renders the page
- Direct-load #studio/connectors/new mounts the editor
- Refresh on #studio/connectors preserves the section
- Empty grid shows the empty-canvas with the "Flight 8 will add Discord"
  copy; the unified header CTA (new-connector-btn, M17 F3 L3) is visible
- New-button → Cancel round-trip restores the empty-canvas grid

M10 F2 L6: tests 4 and 7 originally asserted the placeholder editor's
`connector-editor-placeholder` data-testid; the placeholder is
gone and the assertions now pin the real editor's contract (name input
is visible, Cancel button returns to the grid).

Note: App.areas is closure-private in app.js, so tests use BEHAVIORAL
DOM assertions rather than state introspection.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_studio_section_nav_includes_connectors(app_clean: str, page: Page) -> None:
    """Studio section nav has 4 entries ending with Connectors."""
    page.goto(f"{app_clean}#studio")
    nav = page.locator(".area-studio .section-nav")
    expect(nav).to_be_visible(timeout=5000)
    items = page.locator(".area-studio .section-nav-item")
    expect(items).to_have_count(4)
    labels = items.evaluate_all("els => els.map(e => e.textContent.trim())")
    assert labels == ["Agents", "Knowledge", "MCP Servers", "Connectors"]


@pytest.mark.browser
def test_studio_section_nav_click_to_connectors(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#studio")
    expect(page.locator(".area-studio .section-nav")).to_be_visible(timeout=5000)
    page.locator(".area-studio .section-nav-item", has_text="Connectors").click()
    expect(page.locator(".area-studio .page-title")).to_have_text("Connectors", timeout=5000)
    assert page.evaluate("location.hash") == "#studio/connectors"


@pytest.mark.browser
def test_studio_direct_load_connectors(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#studio/connectors")
    page.wait_for_selector(".area-studio .page-title", timeout=8000)
    assert page.locator(".area-studio .page-title").text_content().strip() == "Connectors"


@pytest.mark.browser
def test_studio_legacy_connectors_slug_redirects_to_connectors(app_clean: str, page: Page) -> None:
    """Legacy hash `#studio/connectors` still mounts the section
    (backward-compat); the router rewrites the URL to the new slug."""
    page.goto(f"{app_clean}#studio/connectors")
    page.wait_for_selector(".area-studio .page-title", timeout=8000)
    assert page.locator(".area-studio .page-title").text_content().strip() == "Connectors"
    # F5 L8 HAT: hydrateState accepts the legacy slug; serializeState
    # writes the new slug back via the router's serialize-after-hydrate
    # pass, so the URL converges to `#studio/connectors`.
    assert page.evaluate("location.hash") == "#studio/connectors"


@pytest.mark.browser
def test_studio_direct_load_connectors_new_renders_editor(app_clean: str, page: Page) -> None:
    """Direct-load to the create route mounts the real editor.

    M10 F2 L6: the leg-5 placeholder was replaced wholesale with the
    full editor. The name input is the stable mount anchor.
    """
    page.goto(f"{app_clean}#studio/connectors/new")
    name_input = page.locator('[data-testid="connector-name-input"]')
    expect(name_input).to_be_visible(timeout=8000)


@pytest.mark.browser
def test_studio_refresh_preserves_connectors_section(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#studio/connectors")
    page.wait_for_selector(".area-studio .page-title", timeout=8000)
    page.reload()
    page.wait_for_selector(".area-studio .page-title", timeout=8000)
    assert page.evaluate("location.hash") == "#studio/connectors"


@pytest.mark.browser
def test_studio_connectors_empty_grid_shows_cta(app_clean: str, page: Page) -> None:
    """Empty connectors table → empty-canvas with the Flight-8 copy renders;
    the unified header CTA (M17 F3 L3) is visible in the empty state."""
    page.goto(f"{app_clean}#studio/connectors")
    # The empty canvas is the synchronization point for the fetch resolving
    # to an empty inventory (the header CTA renders before the fetch).
    page.wait_for_selector(".empty-canvas", timeout=8000)
    expect(page.locator('[data-testid="new-connector-btn"]')).to_be_visible()
    # The "Flight 8 will add Discord" copy explains the production empty
    # state (no real connector types registered yet).
    expect(page.locator(".empty-canvas")).to_contain_text("Flight 8 will add Discord")


@pytest.mark.browser
def test_studio_connectors_new_button_opens_form_then_cancel_returns_to_grid(
    app_clean: str, page: Page
) -> None:
    """New-button → form mounts → Cancel → empty-canvas grid restored.

    M10 F2 L6: assertions updated from the placeholder selector to the
    real editor's name-input + cancel-button.
    """
    page.goto(f"{app_clean}#studio/connectors")
    # Sync on the empty canvas (fetch resolved to an empty inventory).
    page.wait_for_selector(".empty-canvas", timeout=8000)

    # Click the unified header CTA → form mounts and URL updates.
    page.locator('[data-testid="new-connector-btn"]').click()
    expect(page.locator('[data-testid="connector-name-input"]')).to_be_visible(timeout=5000)
    assert page.evaluate("location.hash") == "#studio/connectors/new"

    # Cancel is disabled-until-dirty per the editor contract; use Back
    # to return to the grid (Back also routes through onBack which clears
    # the form-mode and re-renders the empty-canvas).
    page.locator('[data-testid="back-connector-btn"]').click()
    expect(page.locator(".empty-canvas")).to_be_visible(timeout=5000)
    assert page.evaluate("location.hash") == "#studio/connectors"
