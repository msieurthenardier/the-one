"""End-to-end flow test: first-start provider setup.

Drives a real Chromium session through the empty-DB onboarding flow:
- Welcome canvas guidance points to Settings + Agent Studio (no providers yet)
- Navigate to Admin → LLM Providers
- Add a mock provider via the form
- Verify it appears in the list with a mock badge
- Edit it, click Test Connection, see success
- Navigate back to Chat, welcome guidance now points only to Agent Studio
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_first_start_provider_setup_flow(app_clean: str, page: Page) -> None:
    base_url = app_clean

    # 1. Open app (defaults to #chat). Welcome canvas guidance shows the
    #    full setup path: Settings + Agent Studio.
    page.goto(base_url)
    welcome_guidance = page.locator(".chat-welcome-guidance")
    expect(welcome_guidance).to_be_visible(timeout=5000)
    expect(welcome_guidance).to_contain_text("Settings")
    expect(welcome_guidance).to_contain_text("Agent Studio")

    # 2. Navigate to Admin → LLM Providers.
    page.goto(f"{base_url}#admin")
    page.locator(".section-nav-item", has_text="LLM Providers").click()

    # 3. Click + New Provider.
    page.locator('[data-testid="new-provider-btn"]').click()

    # 4-5. Fill name, select mock type (auto-hides base_url and api_key inputs).
    page.locator("#pf-name").fill("Mock Test")
    page.locator("#pf-type").select_option("mock")

    # 6. Click Create.
    page.locator('[data-testid="save-provider-btn"]').click()

    # 7. Form auto-switches to edit mode after successful Create. Post-leg-03
    #    the editor title is the provider's name (not "Edit Provider"); the
    #    Test button is only rendered in edit mode.
    expect(page.locator(".editor-title")).to_have_text("Mock Test")
    test_btn = page.locator('[data-testid="test-connection-btn"]')
    expect(test_btn).to_be_visible()

    # 8-9. Click Test Connection. The mock branch (leg 02) returns
    #      {"status": "ok", "detail": "Mock provider (dev mode)"}.
    test_btn.click()
    expect(page.locator(".test-result")).to_contain_text("Mock", timeout=5000)

    # 10. Clean form (just tested, no edits) — Cancel is disabled; use Back to return.
    page.locator('[data-testid="back-provider-btn"]').click()

    # 11. Provider card visible with name "Mock Test" and mock badge.
    card = page.locator('[data-testid="provider-card"]')
    expect(card).to_be_visible()
    expect(card.locator(".entity-tile-name")).to_have_text("Mock Test")
    expect(card.locator(".admin-provider-badge")).to_have_text("mock")

    # 12. Navigate back to Chat. Welcome guidance now reflects the next setup
    #     gap (provider exists, agent does not).
    page.goto(f"{base_url}#chat")
    expect(welcome_guidance).to_be_visible(timeout=5000)
    expect(welcome_guidance).to_contain_text("Agent Studio")
    expect(welcome_guidance).not_to_contain_text("Settings")
