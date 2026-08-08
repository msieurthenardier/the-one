"""Browser tests for M11 F17 L5 — connector live status + invite pre-Test.

Covers:
  1. ``connector-live-status`` testid renders on the General tab in edit mode.
  2. Live status is present; old "Not tested" text is absent.
  3. Validate button (formerly Test Connection) still has ``connector-test-connection-btn`` testid.
  4. Validate button label reads "Validate" (not "Test connection").
  5. Invite section renders the correct info-icon tooltip text.
  6. Invite renders from persisted ``config.application_id`` without a prior Validate.
  7. Discoverable-entities banner appears in the Access-and-Routing tab (new location).
"""

from __future__ import annotations

import httpx
import pytest
from browser._credential_registry import auth_headers_for
from browser.seeders import seed_connector
from playwright.sync_api import Page, expect


def _seed_discord_with_app_id(
    base_url: str, *, name: str = "Discord Bot", application_id: str | None = None
) -> str:
    """Seed a discord-type connector, optionally with a persisted application_id.

    Uses httpx directly so we can seed config.application_id without running
    through the Validate endpoint (which would need a live Discord connection).
    """
    config: dict = {}
    if application_id:
        config["application_id"] = application_id
    r = httpx.post(
        f"{base_url}/api/connectors",
        json={
            "name": name,
            "type": "discord",
            "config": config,
            "secrets": {"BOT_TOKEN": "fake-token"},
        },
        timeout=5.0,
        headers=auth_headers_for(base_url),
    )
    assert r.status_code == 201, f"seed discord failed: {r.status_code} {r.text}"
    return r.json()["id"]


@pytest.mark.browser
def test_live_status_indicator_renders_on_general_tab(app_clean: str, page: Page) -> None:
    """``connector-live-status`` testid renders in edit mode on the General tab."""
    account_id = seed_connector(app_clean, name="Status Bot")
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    # Wait for the editor to load (test-connection-btn is a reliable edit-mode marker).
    expect(page.locator('[data-testid="connector-test-connection-btn"]')).to_be_visible(
        timeout=8000
    )
    live_status = page.locator('[data-testid="connector-live-status"]')
    expect(live_status).to_be_visible()


@pytest.mark.browser
def test_not_tested_text_absent(app_clean: str, page: Page) -> None:
    """The old hardcoded 'Not tested' string is absent from the DOM."""
    account_id = seed_connector(app_clean, name="No Not-Tested Bot")
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="connector-test-connection-btn"]')).to_be_visible(
        timeout=8000
    )
    # Assert "Not tested" text is not present anywhere in the editor.
    # The test-message span is now empty by default; the status reads from
    # the live-status poll, not a hardcoded string.
    editor = page.locator(".connector-editor")
    expect(editor).not_to_contain_text("Not tested")


@pytest.mark.browser
def test_validate_button_testid_preserved(app_clean: str, page: Page) -> None:
    """``connector-test-connection-btn`` testid is preserved (relabel only)."""
    account_id = seed_connector(app_clean, name="Validate Testid Bot")
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    btn = page.locator('[data-testid="connector-test-connection-btn"]')
    expect(btn).to_be_visible(timeout=8000)


@pytest.mark.browser
def test_validate_button_label_text(app_clean: str, page: Page) -> None:
    """The Validate button's visible label reads 'Validate', not 'Test connection'."""
    account_id = seed_connector(app_clean, name="Label Bot")
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    btn = page.locator('[data-testid="connector-test-connection-btn"]')
    expect(btn).to_be_visible(timeout=8000)
    expect(btn).to_contain_text("Validate")
    expect(btn).not_to_contain_text("Test connection")


@pytest.mark.browser
def test_invite_info_icon_tooltip_text(app_clean: str, page: Page) -> None:
    """Invite info-icon title attribute carries the updated tooltip."""
    account_id = _seed_discord_with_app_id(app_clean, name="Invite Tooltip Bot")
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="connector-test-connection-btn"]')).to_be_visible(
        timeout=8000
    )
    info_icon = page.locator('[data-testid="connector-invite-info"]')
    expect(info_icon).to_be_visible()
    title_val = info_icon.get_attribute("title") or ""
    assert "add the bot to a Discord server" in title_val, (
        f"Expected invite tooltip to mention 'add the bot to a Discord server', got: {title_val!r}"
    )
    assert "needed once per server" in title_val, (
        f"Expected invite tooltip to mention 'needed once per server', got: {title_val!r}"
    )


@pytest.mark.browser
def test_invite_renders_from_persisted_application_id(app_clean: str, page: Page) -> None:
    """When ``config.application_id`` is persisted, the invite URL renders without a Validate."""
    account_id = _seed_discord_with_app_id(
        app_clean, name="Pre-Seeded Invite Bot", application_id="123456789012345678"
    )
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="connector-test-connection-btn"]')).to_be_visible(
        timeout=8000
    )
    # The invite URL wrap should be visible (not hidden) because
    # renderInviteSection seeded the cache from config.application_id.
    url_wrap = page.locator('[data-testid="connector-invite-url-wrap"]')
    hint = page.locator('[data-testid="connector-invite-hint"]')
    expect(url_wrap).to_be_visible(timeout=4000)
    expect(hint).to_be_hidden()
    url_code = page.locator('[data-testid="connector-invite-url"]')
    expect(url_code).to_contain_text("123456789012345678")


@pytest.mark.browser
def test_discoverable_entities_banner_in_access_routing_tab(app_clean: str, page: Page) -> None:
    """Discoverable-entities banner renders at the top of the Access-and-Routing tab."""
    account_id = seed_connector(app_clean, name="Banner Location Bot")
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="connector-test-connection-btn"]')).to_be_visible(
        timeout=8000
    )
    # Activate the Access-and-Routing tab.
    page.locator('[data-testid="tab-access-and-routing"]').click()
    # Banner testid should be visible (it's now at the top of the tab).
    banner = page.locator('[data-testid="connector-allowlist-banner"]')
    expect(banner).to_be_visible(timeout=4000)
    # The label "Entries last refreshed" should appear in the banner area.
    expect(banner).to_contain_text("Entries last refreshed")
