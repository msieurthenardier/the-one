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
def test_studio_connector_doctor_no_plugin_registered(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Doctor on a "discord" connector (no plugin registered this flight —
    Discord lands Flight 3) renders a clean report, never a crash."""
    page.goto(f"{app_with_agent.base_url}#studio/connectors")
    page.locator('[data-testid="new-connector-btn"]').click()
    page.locator('[data-field="name"]').fill("Doctor Test Connector")
    page.locator('[data-field="default_agent"]').select_option(app_with_agent.agent_name)
    page.locator('[data-testid="save-connector-btn"]').click()

    doctor_btn = page.locator('[data-testid="connector-doctor-btn"]')
    expect(doctor_btn).to_be_visible(timeout=8000)
    doctor_btn.click()

    result = page.locator('[data-testid="connector-doctor-result"]')
    expect(result).to_contain_text("no plugin registered", timeout=8000)


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
