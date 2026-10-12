"""Browser flow: Library → new openrouter provider → save → edit → round-trip.

Covers:
- Selecting the openrouter type pre-fills base_url.
- Saving a new openrouter provider transitions the editor to edit mode and
  sets the URL to #library/providers/{id}.
- Re-opening the saved provider in edit mode round-trips name + base_url.
- The api_key field shows the masked sentinel on re-open.

Ranking headers (HTTP-Referer / X-Title) identify *the app* (the-one), not
the operator — they are hardcoded constants in openrouter_provider.py and
are NOT operator-configurable. No UI fields exist for them.
"""

from __future__ import annotations

import pytest
from browser import _lists, _nav
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_openrouter_type_prefills_base_url(app_clean: str, page: Page) -> None:
    """Picking openrouter type pre-fills the Base URL to openrouter.ai/api/v1."""
    _nav.goto(page, app_clean, "library/providers/~new")
    expect(page.locator(".editor-title")).to_have_text("New model provider", timeout=8000)

    page.locator("#pf-type").select_option("openrouter")

    # base_url row becomes visible and is pre-filled
    base_url_input = page.locator("#pf-base-url")
    expect(base_url_input).to_be_visible(timeout=3000)
    expect(base_url_input).to_have_value("https://openrouter.ai/api/v1")


@pytest.mark.browser
def test_openrouter_create_and_round_trip(app_clean: str, page: Page) -> None:
    """Create an openrouter provider, save, re-open and assert all fields
    round-tripped."""
    _nav.goto(page, app_clean, "library/providers/~new")
    expect(page.locator(".editor-title")).to_have_text("New model provider", timeout=8000)

    # 1. Select openrouter type — triggers base_url pre-fill.
    page.locator("#pf-type").select_option("openrouter")
    expect(page.locator("#pf-base-url")).to_be_visible(timeout=3000)

    # 2. Fill all fields.
    page.locator("#pf-name").fill("OR Test")
    page.locator("#pf-base-url").fill("https://openrouter.ai/api/v1")
    page.locator("#pf-api-key").fill("sk-or-test")

    # 3. Save button should now be enabled (form is dirty).
    save_btn = page.locator('[data-testid="save-provider-btn"]')
    expect(save_btn).not_to_be_disabled(timeout=2000)
    save_btn.click()

    # 4. After save, editor transitions to edit mode: title = provider name.
    expect(page.locator(".editor-title")).to_have_text("OR Test", timeout=5000)
    current_route = _nav.current_route(page)
    assert current_route.startswith("library/providers/"), (
        f"expected library/providers/<id>, got {current_route!r}"
    )
    assert current_route != "library/providers/~new", "route must not remain create after save"

    # 5. Test button is present in edit mode.
    expect(page.locator('[data-testid="test-connection-btn"]')).to_be_visible()

    # 6. Assert fields round-tripped.
    expect(page.locator("#pf-name")).to_have_value("OR Test")
    expect(page.locator("#pf-base-url")).to_have_value("https://openrouter.ai/api/v1")

    # api_key is masked on edit (***…last4 or empty).
    api_key_val = page.locator("#pf-api-key").input_value()
    assert api_key_val.startswith("***") or api_key_val == "", (
        f"expected masked display value (***…) or empty, got {api_key_val!r}"
    )


@pytest.mark.browser
def test_openrouter_create_navigate_back_and_reopen(app_clean: str, page: Page) -> None:
    """After saving, close the editor (its breadcrumb link) and re-open the
    provider from its list row to confirm it is persisted and round-trips on
    a second open."""
    _nav.goto(page, app_clean, "library/providers/~new")
    expect(page.locator(".editor-title")).to_have_text("New model provider", timeout=8000)

    page.locator("#pf-type").select_option("openrouter")
    expect(page.locator("#pf-base-url")).to_be_visible(timeout=3000)

    page.locator("#pf-name").fill("OR Persisted")
    page.locator("#pf-api-key").fill("sk-or-test2")

    page.locator('[data-testid="save-provider-btn"]').click()
    expect(page.locator(".editor-title")).to_have_text("OR Persisted", timeout=5000)

    # Close the editor (back to the Library root; the list stays).
    _lists.close_item(page)
    expect(page.locator(".editor-title")).to_have_count(0, timeout=5000)

    # The row is in the Library list, with its openrouter type badge.
    link = _lists.list_row(page, "library/providers", "OR Persisted")
    expect(link).to_be_visible(timeout=5000)
    expect(link.locator(".badge")).to_contain_text("openrouter")

    # Click the name to re-open it in edit mode.
    _lists.open_item(page, "library/providers", "OR Persisted")
    expect(page.locator(".editor-title")).to_have_text("OR Persisted", timeout=5000)

    # Round-trip assertions.
    expect(page.locator("#pf-name")).to_have_value("OR Persisted")
    expect(page.locator("#pf-base-url")).to_have_value("https://openrouter.ai/api/v1")
