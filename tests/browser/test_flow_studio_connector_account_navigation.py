"""Studio Connector Accounts navigation flow tests (M10 F2 leg 05).

Mirrors `test_flow_studio_mcp_navigation.py`. The Connector Accounts
section is structurally identical to MCP Sources (operator-managed
entities, many-to-many identities); placed in Studio (not Admin) per
the flight's "Studio placement, not Admin" design decision.

Covers:
- Studio section nav now has 4 entries ending with "Connector Accounts"
- Click "Connector Accounts" → URL becomes #studio/connector-accounts
- Direct-load #studio/connector-accounts renders the page
- Direct-load #studio/connector-accounts/new mounts the editor
- Refresh on #studio/connector-accounts preserves the section
- Empty grid shows the centered CTA + the "Flight 8 will add Discord" copy
- New-button → Cancel round-trip restores the empty-canvas grid

M10 F2 L6: tests 4 and 7 originally asserted the placeholder editor's
`connector-account-editor-placeholder` data-testid; the placeholder is
gone and the assertions now pin the real editor's contract (name input
is visible, Cancel button returns to the grid).

Note: App.areas is closure-private in app.js, so tests use BEHAVIORAL
DOM assertions rather than state introspection.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_studio_section_nav_includes_connector_accounts(app_clean: str, page: Page) -> None:
    """Studio section nav has 4 entries ending with Connector Accounts."""
    page.goto(f"{app_clean}#studio")
    nav = page.locator(".area-studio .section-nav")
    expect(nav).to_be_visible(timeout=5000)
    items = page.locator(".area-studio .section-nav-item")
    expect(items).to_have_count(4)
    labels = items.evaluate_all("els => els.map(e => e.textContent.trim())")
    assert labels == ["Agents", "Knowledge", "MCP Servers", "Connector Accounts"]


@pytest.mark.browser
def test_studio_section_nav_click_to_connector_accounts(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#studio")
    expect(page.locator(".area-studio .section-nav")).to_be_visible(timeout=5000)
    page.locator(".area-studio .section-nav-item", has_text="Connector Accounts").click()
    expect(page.locator(".area-studio .page-title")).to_have_text(
        "Connector Accounts", timeout=5000
    )
    assert page.evaluate("location.hash") == "#studio/connector-accounts"


@pytest.mark.browser
def test_studio_direct_load_connector_accounts(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#studio/connector-accounts")
    page.wait_for_selector(".area-studio .page-title", timeout=8000)
    assert page.locator(".area-studio .page-title").text_content().strip() == "Connector Accounts"


@pytest.mark.browser
def test_studio_direct_load_connector_accounts_new_renders_editor(
    app_clean: str, page: Page
) -> None:
    """Direct-load to the create route mounts the real editor.

    M10 F2 L6: the leg-5 placeholder was replaced wholesale with the
    full editor. The name input is the stable mount anchor.
    """
    page.goto(f"{app_clean}#studio/connector-accounts/new")
    name_input = page.locator('[data-testid="connector-account-name-input"]')
    expect(name_input).to_be_visible(timeout=8000)


@pytest.mark.browser
def test_studio_refresh_preserves_connector_accounts_section(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#studio/connector-accounts")
    page.wait_for_selector(".area-studio .page-title", timeout=8000)
    page.reload()
    page.wait_for_selector(".area-studio .page-title", timeout=8000)
    assert page.evaluate("location.hash") == "#studio/connector-accounts"


@pytest.mark.browser
def test_studio_connector_accounts_empty_grid_shows_cta(app_clean: str, page: Page) -> None:
    """Empty connector_accounts table → empty-canvas with the Flight-8 copy renders."""
    page.goto(f"{app_clean}#studio/connector-accounts")
    page.wait_for_selector('[data-testid="new-connector-account-btn-empty"]', timeout=8000)
    cta = page.locator('[data-testid="new-connector-account-btn-empty"]')
    expect(cta).to_be_visible()
    # The "Flight 8 will add Discord" copy explains the production empty
    # state (no real connector types registered yet).
    expect(page.locator(".empty-canvas")).to_contain_text("Flight 8 will add Discord")


@pytest.mark.browser
def test_studio_connector_accounts_new_button_opens_form_then_cancel_returns_to_grid(
    app_clean: str, page: Page
) -> None:
    """New-button → form mounts → Cancel → empty-canvas grid restored.

    M10 F2 L6: assertions updated from the placeholder selector to the
    real editor's name-input + cancel-button.
    """
    page.goto(f"{app_clean}#studio/connector-accounts")
    page.wait_for_selector('[data-testid="new-connector-account-btn-empty"]', timeout=8000)

    # Click the empty-canvas CTA → form mounts and URL updates.
    page.locator('[data-testid="new-connector-account-btn-empty"]').click()
    expect(page.locator('[data-testid="connector-account-name-input"]')).to_be_visible(
        timeout=5000
    )
    assert page.evaluate("location.hash") == "#studio/connector-accounts/new"

    # Cancel is disabled-until-dirty per the editor contract; use Back
    # to return to the grid (Back also routes through onBack which clears
    # the form-mode and re-renders the empty-canvas).
    page.locator('[data-testid="back-connector-account-btn"]').click()
    expect(page.locator(".empty-canvas")).to_be_visible(timeout=5000)
    assert page.evaluate("location.hash") == "#studio/connector-accounts"
