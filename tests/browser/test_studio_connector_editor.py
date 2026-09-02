"""Studio Connector-editor form flow tests (Mission 23 Flight 2 Leg 2, DD-9).

Covers: empty-state CTA, create → masked-token redisplay (the round-trip
the backend's `_looks_masked` contract exists to protect), doctor (no
plugin registered — the NORM this flight, Discord lands Flight 3), and
pairing-code generation. Kept small — the end-to-end stub round-trip
(create → pair → message → reply) is leg 3's behavior test's job, not
this browser lane's.
"""

from __future__ import annotations

import pytest
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_studio_connectors_empty_grid_shows_cta(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#studio/connectors")
    page.wait_for_selector(".area-studio .page-title", timeout=8000)
    assert page.locator(".area-studio .page-title").text_content().strip() == "Connectors"
    expect(page.locator('[data-testid="new-connector-btn"]')).to_be_visible()


@pytest.mark.browser
def test_studio_create_connector_shows_masked_token_on_redisplay(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Create a connector with a real token; after save, the token field
    redisplays the MASKED shape, never the plaintext — the same contract
    `tests/test_api_secret_mask_roundtrip.py` pins at the API layer."""
    page.goto(f"{app_with_agent.base_url}#studio/connectors")
    page.locator('[data-testid="new-connector-btn"]').click()

    save_btn = page.locator('[data-testid="save-connector-btn"]')
    expect(save_btn).to_be_visible(timeout=8000)

    page.locator('[data-field="name"]').fill("Browser Test Connector")
    page.locator('[data-field="type"]').select_option("discord")
    page.locator('[data-field="token"]').fill("real-plaintext-secret-value")
    page.locator('[data-field="default_agent"]').select_option(app_with_agent.agent_name)

    save_btn.click()
    expect(page.locator('[data-testid="delete-connector-btn"]')).to_be_visible(timeout=8000)

    token_value = page.locator('[data-field="token"]').input_value()
    assert token_value != "real-plaintext-secret-value"
    assert "real-plaintext-secret-value" not in page.content()


@pytest.mark.browser
def test_studio_connector_doctor_reports_plugin_failure_without_token(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Doctor on a "discord" connector (the browser lane's only creatable
    type without the stub gate, and the type leg 1 unconditionally
    registers in production) with no token configured renders the real
    plugin's own failure report, never a crash.

    RENAMED and re-aimed (Mission 23 Flight 3 Leg 3, AC-5): this test
    originally pinned the pre-Discord "no plugin registered" doctor path
    for a discord-typed connector. Leg 1's unconditional production
    Discord registration falsified that premise — the real plugin now
    answers with its own no-token failure instead. Stub-with-gate-closed
    was considered as the re-aim target and found unimplementable: stub
    creatability and stub plugin registration share the SAME dual gate
    (`api.py` `_creatable_connector_types` vs `app.py`'s startup hook), so
    with the gate closed the "stub" type isn't even selectable in this
    form — the browser lane never opens `THE_ONE_STUB_TEST_ENDPOINT`. This
    test instead targets the state the lane CAN reach: a tokenless
    discord-typed connector, asserting the failed status + message SHAPE
    (not exact prose) per the leg's design.
    """
    page.goto(f"{app_with_agent.base_url}#studio/connectors")
    page.locator('[data-testid="new-connector-btn"]').click()
    page.locator('[data-field="name"]').fill("Doctor Test Connector")
    page.locator('[data-field="default_agent"]').select_option(app_with_agent.agent_name)
    page.locator('[data-testid="save-connector-btn"]').click()

    doctor_btn = page.locator('[data-testid="connector-doctor-btn"]')
    expect(doctor_btn).to_be_visible(timeout=8000)
    doctor_btn.click()

    result = page.locator('[data-testid="connector-doctor-result"]')
    expect(result).to_contain_text("failed", timeout=8000)
    expect(result).to_contain_text("token", timeout=8000)


@pytest.mark.browser
def test_studio_connector_enabled_checkbox_default_checked_and_persists(
    app_with_agent: SeededApp, page: Page
) -> None:
    """AC-10 (Mission 23 Flight 3 Leg 2, DD-6): Enabled checkbox defaults to
    checked; saving without touching it omits ``config.enabled`` (sparse-
    config pattern) — reopening the saved connector shows it still checked."""
    page.goto(f"{app_with_agent.base_url}#studio/connectors")
    page.locator('[data-testid="new-connector-btn"]').click()
    page.locator('[data-field="name"]').fill("Enabled Default Connector")
    page.locator('[data-field="default_agent"]').select_option(app_with_agent.agent_name)

    checkbox = page.locator('[data-field="enabled"]')
    expect(checkbox).to_be_visible(timeout=8000)
    expect(checkbox).to_be_checked()

    page.locator('[data-testid="save-connector-btn"]').click()
    expect(page.locator('[data-testid="delete-connector-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-testid="back-connector-btn"]').click()
    page.locator('[data-testid="connector-card"]').first.click()
    expect(page.locator('[data-field="enabled"]')).to_be_checked(timeout=8000)


@pytest.mark.browser
def test_studio_connector_enabled_checkbox_unchecked_persists_disabled(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Unchecking the Enabled checkbox saves ``enabled: false``; editing a
    disabled connector shows it unchecked (the checked-state trap: the
    render must key off ``!== false``, never a truthy check)."""
    page.goto(f"{app_with_agent.base_url}#studio/connectors")
    page.locator('[data-testid="new-connector-btn"]').click()
    page.locator('[data-field="name"]').fill("Disabled Connector")
    page.locator('[data-field="default_agent"]').select_option(app_with_agent.agent_name)
    page.locator('[data-field="enabled"]').uncheck()

    page.locator('[data-testid="save-connector-btn"]').click()
    expect(page.locator('[data-testid="delete-connector-btn"]')).to_be_visible(timeout=8000)
    expect(page.locator('[data-field="enabled"]')).not_to_be_checked()

    page.locator('[data-testid="back-connector-btn"]').click()
    page.locator('[data-testid="connector-card"]').first.click()
    expect(page.locator('[data-field="enabled"]')).not_to_be_checked(timeout=8000)


@pytest.mark.browser
def test_studio_connector_pairing_code_generation(app_with_agent: SeededApp, page: Page) -> None:
    page.goto(f"{app_with_agent.base_url}#studio/connectors")
    page.locator('[data-testid="new-connector-btn"]').click()
    page.locator('[data-field="name"]').fill("Pairing Test Connector")
    page.locator('[data-field="default_agent"]').select_option(app_with_agent.agent_name)
    page.locator('[data-testid="save-connector-btn"]').click()

    pairing_btn = page.locator('[data-testid="connector-pairing-btn"]')
    expect(pairing_btn).to_be_visible(timeout=8000)
    pairing_btn.click()

    result = page.locator('[data-testid="connector-pairing-result"]')
    expect(result).to_contain_text("Code:", timeout=8000)
    expect(result).to_contain_text("expires", timeout=8000)
