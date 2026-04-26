"""End-to-end flow test: Studio agent CRUD.

Drives a real Chromium session through the agent lifecycle:
- Empty Studio (mock provider already seeded by fixture)
- Click + to create an agent
- Fill form (name, description, provider, model, system prompt)
- Click Create — agent appears in sidebar, editor switches to edit mode
- Edit description, click Save — change persists
- Click Delete (two-click confirm) — agent removed, empty state restored
"""

from __future__ import annotations

import pytest
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_studio_agent_crud_flow(app_with_provider: SeededApp, page: Page) -> None:
    base_url = app_with_provider.base_url

    # 1. Open Studio. Empty state shows "No agents yet".
    page.goto(f"{base_url}#studio")
    empty = page.locator('[data-testid="agent-empty"]')
    expect(empty).to_be_visible()
    expect(empty).to_contain_text("No agents yet")

    # 2. Click + to enter create mode.
    page.locator('[data-testid="new-agent-btn"]').click()
    expect(page.locator(".editor-title")).to_have_text("New Agent")

    # 3-4. Fill name and description.
    page.locator('[data-field="name"]').fill("test-agent")
    page.locator('[data-field="description"]').fill("An agent for tests")

    # 5. Provider dropdown auto-selected (only one — the seeded mock provider).
    expect(page.locator("#studio-provider")).to_have_value(app_with_provider.provider_id)

    # 6-7. Wait for model dropdown to populate; select "mock-default".
    #      The fetch fires on initial render via fetchModelsForProvider.
    expect(page.locator('#studio-model option[value="mock-default"]')).to_be_attached(timeout=5000)
    page.locator("#studio-model").select_option("mock-default")

    # 8. Fill system prompt.
    page.locator('[data-field="system_prompt"]').fill("You are a test agent.")

    # 9. Click Create.
    page.locator('[data-testid="save-agent-btn"]').click()

    # 10. Sidebar contains exactly one new agent item with our name.
    agent_item = page.locator('[data-testid="agent-item"]')
    expect(agent_item).to_have_count(1)
    expect(agent_item).to_contain_text("test-agent")

    # 11. Editor switched to edit mode — title shows agent name, Delete Agent visible.
    expect(page.locator(".editor-title")).to_have_text("test-agent")
    delete_btn = page.locator('[data-testid="delete-agent-btn"]')
    expect(delete_btn).to_be_visible()
    expect(delete_btn).to_have_text("Delete Agent")

    # 12-13. Edit description, save, verify persisted (re-render keeps the value).
    description_input = page.locator('[data-field="description"]')
    description_input.fill("Edited description")
    page.locator('[data-testid="save-agent-btn"]').click()
    # After save, editor re-renders with updated agent. Description still set.
    expect(page.locator('[data-field="description"]')).to_have_value(
        "Edited description", timeout=5000
    )

    # 14. First click on Delete — confirm state ("Confirm Delete?").
    delete_btn.click()
    expect(delete_btn).to_have_text("Confirm Delete?")

    # 15. Second click — DELETE fires, agent removed, empty state returns.
    delete_btn.click()
    expect(empty).to_be_visible(timeout=5000)
    expect(empty).to_contain_text("No agents yet")
    # Agent item gone from sidebar; editor returns to its empty state.
    expect(page.locator('[data-testid="agent-item"]')).to_have_count(0)
    expect(page.locator(".editor-empty")).to_be_visible()
