"""End-to-end flow test: first-start provider setup.

Drives a real Chromium session through the empty-DB onboarding flow:
- See setup banner in Chat
- Navigate to Admin → LLM Providers
- Add a mock provider via the form
- Verify it appears in the list with a mock badge
- Edit it, click Test Connection, see success
- Navigate back to Chat, banner now says "No agents"
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_first_start_provider_setup_flow(app_clean: str, page: Page) -> None:
    base_url = app_clean

    # 1. Open app (defaults to #chat). Setup banner shows "Getting started".
    page.goto(base_url)
    setup_banner = page.locator('[data-testid="setup-banner"]')
    expect(setup_banner).to_be_visible()
    expect(setup_banner).to_contain_text("Getting started")

    # 2. Navigate to Admin → LLM Providers.
    page.goto(f"{base_url}#admin")
    page.locator(".admin-category-item", has_text="LLM Providers").click()

    # 3. Click + Add Provider.
    page.locator('[data-testid="add-provider-btn"]').click()

    # 4-5. Fill name, select mock type (auto-hides base_url and api_key inputs).
    page.locator("#pf-name").fill("Mock Test")
    page.locator("#pf-type").select_option("mock")

    # 6. Click Create.
    page.locator('[data-testid="save-provider-btn"]').click()

    # 7. Form auto-switches to edit mode after successful Create
    #    (admin.js:665-670). Confirm by waiting for the title and the
    #    Test Connection button (only rendered in edit mode).
    expect(page.locator(".admin-title")).to_have_text("Edit Provider")
    test_btn = page.locator('[data-testid="test-connection-btn"]')
    expect(test_btn).to_be_visible()

    # 8-9. Click Test Connection. The mock branch (leg 02) returns
    #      {"status": "ok", "detail": "Mock provider (dev mode)"}.
    test_btn.click()
    expect(page.locator(".admin-pf-test-result")).to_contain_text("Mock", timeout=5000)

    # 10. Click Cancel to return to the provider list.
    page.locator(".admin-pf-cancel").click()

    # 11. Provider card visible with name "Mock Test" and mock badge.
    card = page.locator('[data-testid="provider-card"]')
    expect(card).to_be_visible()
    expect(card.locator(".admin-provider-name")).to_have_text("Mock Test")
    expect(card.locator(".admin-provider-badge")).to_have_text("mock")

    # 12. Navigate back to Chat. Banner now reflects the next setup gap.
    page.goto(f"{base_url}#chat")
    expect(setup_banner).to_be_visible()
    expect(setup_banner).to_contain_text("No agents")
