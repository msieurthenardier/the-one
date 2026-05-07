"""Browser flow: admin → new openrouter provider → save → edit → round-trip.

Covers:
- Selecting the openrouter type pre-fills base_url and shows the optional
  config fields (referer, title).
- Saving a new openrouter provider transitions the editor to edit mode and
  sets the URL to #admin/providers/{id}.
- Re-opening the saved provider in edit mode round-trips all stored fields:
  name, base_url, config.referer, config.title.
- The api_key field shows the masked sentinel on re-open.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_openrouter_type_prefills_base_url(app_clean: str, page: Page) -> None:
    """Picking openrouter type pre-fills the Base URL to openrouter.ai/api/v1."""
    page.goto(f"{app_clean}#admin/providers/new")
    expect(page.locator(".editor-title")).to_have_text("New Provider", timeout=8000)

    page.locator("#pf-type").select_option("openrouter")

    # base_url row becomes visible and is pre-filled
    base_url_input = page.locator("#pf-base-url")
    expect(base_url_input).to_be_visible(timeout=3000)
    expect(base_url_input).to_have_value("https://openrouter.ai/api/v1")


@pytest.mark.browser
def test_openrouter_type_shows_config_fields(app_clean: str, page: Page) -> None:
    """Picking openrouter type reveals the optional config rows (referer, title)."""
    page.goto(f"{app_clean}#admin/providers/new")
    expect(page.locator(".editor-title")).to_have_text("New Provider", timeout=8000)

    page.locator("#pf-type").select_option("openrouter")

    # The openrouter-specific config rows become visible
    expect(page.locator("#pf-referer")).to_be_visible(timeout=3000)
    expect(page.locator("#pf-title")).to_be_visible(timeout=3000)


@pytest.mark.browser
def test_openrouter_create_and_round_trip(app_clean: str, page: Page) -> None:
    """Create an openrouter provider with all fields, save, re-open and assert
    all fields round-tripped."""
    page.goto(f"{app_clean}#admin/providers/new")
    expect(page.locator(".editor-title")).to_have_text("New Provider", timeout=8000)

    # 1. Select openrouter type — triggers base_url pre-fill + config row reveal.
    page.locator("#pf-type").select_option("openrouter")
    expect(page.locator("#pf-base-url")).to_be_visible(timeout=3000)

    # 2. Fill all fields.
    page.locator("#pf-name").fill("OR Test")
    # base_url is already pre-filled; overwrite to a clean known value.
    page.locator("#pf-base-url").fill("https://openrouter.ai/api/v1")
    page.locator("#pf-api-key").fill("sk-or-test")
    page.locator("#pf-referer").fill("https://myapp.example")
    page.locator("#pf-title").fill("MyApp")

    # 3. Save button should now be enabled (form is dirty).
    save_btn = page.locator('[data-testid="save-provider-btn"]')
    expect(save_btn).not_to_be_disabled(timeout=2000)
    save_btn.click()

    # 4. After save, editor transitions to edit mode: title = provider name.
    expect(page.locator(".editor-title")).to_have_text("OR Test", timeout=5000)
    # URL hash contains the new provider id (not 'new').
    current_hash = page.evaluate("location.hash")
    assert current_hash.startswith("#admin/providers/"), (
        f"expected #admin/providers/<id>, got {current_hash!r}"
    )
    assert current_hash != "#admin/providers/new", "hash must not remain /new after save"

    # 5. Test button is present in edit mode.
    expect(page.locator('[data-testid="test-connection-btn"]')).to_be_visible()

    # 6. Assert fields round-tripped (Cancel to revert would clear dirty state;
    #    we read directly from the live editor which re-rendered with saved data).
    expect(page.locator("#pf-name")).to_have_value("OR Test")
    expect(page.locator("#pf-base-url")).to_have_value("https://openrouter.ai/api/v1")
    expect(page.locator("#pf-referer")).to_have_value("https://myapp.example")
    expect(page.locator("#pf-title")).to_have_value("MyApp")

    # api_key is masked on edit: the server returns "***...{last4}" via
    # _mask_api_key(), which the editor pre-fills into the password input.
    # The MASKED_SENTINEL ("__MASKED__") is sent back to the server when
    # the user saves without changing the key — it is NOT the display value.
    api_key_val = page.locator("#pf-api-key").input_value()
    assert api_key_val.startswith("***") or api_key_val == "", (
        f"expected masked display value (***…) or empty, got {api_key_val!r}"
    )


@pytest.mark.browser
def test_openrouter_create_navigate_back_and_reopen(app_clean: str, page: Page) -> None:
    """After saving, navigate back to the provider grid and re-click the tile
    to confirm the provider is persisted and round-trips on second open."""
    page.goto(f"{app_clean}#admin/providers/new")
    expect(page.locator(".editor-title")).to_have_text("New Provider", timeout=8000)

    page.locator("#pf-type").select_option("openrouter")
    expect(page.locator("#pf-base-url")).to_be_visible(timeout=3000)

    page.locator("#pf-name").fill("OR Persisted")
    page.locator("#pf-api-key").fill("sk-or-test2")
    page.locator("#pf-referer").fill("https://persistent.example")
    page.locator("#pf-title").fill("PersistApp")

    page.locator('[data-testid="save-provider-btn"]').click()
    expect(page.locator(".editor-title")).to_have_text("OR Persisted", timeout=5000)

    # Navigate back to the provider grid.
    page.locator('[data-testid="back-provider-btn"]').click()
    expect(page.locator(".area-admin .page-title")).to_have_text("LLM Providers", timeout=5000)

    # The tile should be visible.
    tile = page.locator('[data-testid="provider-card"]')
    expect(tile).to_be_visible(timeout=5000)
    expect(tile.locator(".entity-tile-name")).to_have_text("OR Persisted")
    # Badge should show the provider type.
    expect(tile.locator(".entity-tile-badge")).to_contain_text("openrouter")

    # Click the tile to re-open in edit mode.
    tile.click()
    expect(page.locator(".editor-title")).to_have_text("OR Persisted", timeout=5000)

    # Round-trip assertions.
    expect(page.locator("#pf-name")).to_have_value("OR Persisted")
    expect(page.locator("#pf-base-url")).to_have_value("https://openrouter.ai/api/v1")
    expect(page.locator("#pf-referer")).to_have_value("https://persistent.example")
    expect(page.locator("#pf-title")).to_have_value("PersistApp")
