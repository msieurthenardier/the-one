"""End-to-end flow test: first-start provider setup.

Drives a real Chromium session through the empty-DB onboarding flow:
- Welcome canvas guidance points to Library + Agents (no providers yet; the
  provider link moved from Settings to Library in sortie 02)
- Navigate to Library and add a mock provider through the Add menu
- Create keeps the editor open in edit mode; click Test Connection, see success
- Navigate back to Chat, welcome guidance now points only to Agents

(The Library list row, selection and badge checks live in
``test_flow_provider_library.py``; the provider moved there from Settings in
sortie 02.)
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
# states, and the `-empty` testid variants are retired. Sortie 02 moved the
# create CTA to the Library Add menu (`library-add-provider`).


@pytest.mark.browser
def test_first_start_provider_setup_flow(app_clean: str, page: Page) -> None:
    base_url = app_clean

    # 1. Open app (defaults to #chat). Welcome canvas guidance shows the
    #    full setup path: Library + Agents.
    _nav.goto_root(page, base_url)
    welcome_guidance = page.locator(".chat-welcome-guidance")
    expect(welcome_guidance).to_be_visible(timeout=5000)
    expect(welcome_guidance).to_contain_text("Library")
    expect(welcome_guidance).to_contain_text("Agents")

    # 2. Navigate to Library and add a provider through the Add menu (visible
    #    even with an empty DB).
    _nav.goto(page, base_url, "library")
    _lists.library_add(page, "providers")

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
    expect(page.locator('[data-testid="provider-test-result"]')).to_contain_text(
        "Mock", timeout=5000
    )

    # 10. Navigate back to Chat. Welcome guidance now reflects the next setup
    #     gap (provider exists, agent does not).
    _nav.goto(page, base_url, "chats")
    expect(welcome_guidance).to_be_visible(timeout=5000)
    expect(welcome_guidance).to_contain_text("Agents")
    expect(welcome_guidance).not_to_contain_text("Library")
