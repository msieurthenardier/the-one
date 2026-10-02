"""End-to-end flow test: first-start provider setup.

Drives a real Chromium session through the empty-DB onboarding flow:
- Welcome canvas guidance points to Settings + Agents (no providers yet)
- Navigate to Settings → Providers
- Add a mock provider via the form (the form opens below the Providers table)
- Create keeps the editor open in edit mode; click Test Connection, see success
- Verify it appears in the table with a mock badge (selected: it is open)
- Navigate back to Chat, welcome guidance now points only to Agents
"""

from __future__ import annotations

import pytest
from browser import _lists, _nav
from playwright.sync_api import Page, expect

# History (M08 F4 → M17 F1 → M17 F3): this module was skipped as "hangs, root
# cause unidentified". The hang itself was fixed by the F5 L01 SQLite-isolation
# fix in tests/conftest.py; the remaining deterministic failure was root-caused
# in M17 F1 L02 as the state-split create CTA (the affordance moved between an
# in-canvas `-empty` variant and a hidden-when-empty header button). M17 F3 L3
# unified the CTA: the header button (data-testid="new-provider-btn") is
# always visible with an icon + text label in BOTH empty and populated grid
# states, and the `-empty` testid variants are retired.


@pytest.mark.browser
def test_first_start_provider_setup_flow(app_clean: str, page: Page) -> None:
    base_url = app_clean

    # 1. Open app (defaults to #chat). Welcome canvas guidance shows the
    #    full setup path: Settings + Agents.
    page.goto(base_url)
    welcome_guidance = page.locator(".chat-welcome-guidance")
    expect(welcome_guidance).to_be_visible(timeout=5000)
    expect(welcome_guidance).to_contain_text("Settings")
    expect(welcome_guidance).to_contain_text("Agents")

    # 2. Navigate to Settings → Providers (the Settings nav link).
    _nav.goto(page, base_url, "settings")
    _lists.open_settings_page(page, "providers")

    # 3. Click the unified header CTA (+ Add provider). It is visible even
    #    with an empty DB (M17 F3 L3 CTA unification).
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

    # 10. The new provider's row is in the table above the editor, selected
    #     (it is the open item), with its mock type badge (M25 F3 leg 5b).
    link = _lists.list_row(page, "settings/providers", "Mock Test")
    expect(link).to_be_visible()
    _lists.expect_selected(page, "settings/providers", "Mock Test")
    row = _lists.providers_table(page).locator("tbody tr").filter(has=link)
    expect(row.locator(".badge")).to_have_text("mock")

    # 11. Clean form (just tested, no edits): the breadcrumb closes it.
    _lists.close_item(page)
    expect(page.locator(".editor-title")).to_have_count(0, timeout=5000)
    expect(link).to_be_visible()

    # 12. Navigate back to Chat. Welcome guidance now reflects the next setup
    #     gap (provider exists, agent does not).
    _nav.goto(page, base_url, "chats")
    expect(welcome_guidance).to_be_visible(timeout=5000)
    expect(welcome_guidance).to_contain_text("Agents")
    expect(welcome_guidance).not_to_contain_text("Settings")
