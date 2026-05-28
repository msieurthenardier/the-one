"""Browser tests for the connector Test Connection button (M10 F2 L6).

Mirrors `test_mcp_test_connection_button.py` for the connector probe.
Configured doctor responses use Playwright ``page.route()`` to fulfill
the POST ``/api/connectors/{id}/test/connect`` call because
``app_clean`` spawns a uvicorn subprocess (`conftest.py:112-178`); the
test process can't mutate the subprocess's ``StubPlugin.doctor_response``.

The MCP test-connection button at
``tests/browser/test_mcp_test_connection_button.py:216-405`` is the
canonical ``page.route()`` reference.
"""

from __future__ import annotations

import json

import pytest
from browser.seeders import seed_connector
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_test_connection_button_visible_in_edit_mode(app_clean: str, page: Page) -> None:
    """Test Connection button renders in edit-mode."""
    account_id = seed_connector(app_clean, name="Edit Mode Bot")
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="connector-test-connection-btn"]')).to_be_visible(
        timeout=8000
    )


@pytest.mark.browser
def test_test_connection_button_absent_in_create_mode(app_clean: str, page: Page) -> None:
    """Test Connection button is NOT rendered in create-mode."""
    page.goto(f"{app_clean}#studio/connectors/new")
    expect(page.locator('[data-testid="create-and-test-connector-btn"]')).to_be_visible(
        timeout=8000
    )
    expect(page.locator('[data-testid="connector-test-connection-btn"]')).to_have_count(0)


@pytest.mark.browser
def test_default_stub_probe_renders_success_with_no_details(
    app_clean: str, page: Page
) -> None:
    """Click → real stub doctor returns status=ok, details={} → green LED
    + no details panel surfaced (M07 inspector convention: status +
    one-sentence message at-a-glance; details panel opens only on
    debug-needed states)."""
    account_id = seed_connector(app_clean, name="OK Stub Bot")
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="connector-test-connection-btn"]')).to_be_visible(
        timeout=8000
    )

    page.locator('[data-testid="connector-test-connection-btn"]').click()

    led = page.locator('[data-testid="connector-test-led"]')
    expect(led).to_have_attribute("data-state", "ok", timeout=8000)
    # LED class swaps to the success token.
    led_class = led.get_attribute("class")
    assert "indicator-led--success" in (led_class or ""), led_class

    message = page.locator('[data-testid="connector-test-message"]')
    expect(message).to_contain_text("stub probe ok")

    details_wrap = page.locator('[data-testid="connector-test-details-wrap"]')
    expect(details_wrap).to_be_hidden()


@pytest.mark.browser
def test_configured_failure_response_renders_red_led_and_details(
    app_clean: str, page: Page
) -> None:
    """page.route()-fulfilled failure → red LED + details k/v block."""
    account_id = seed_connector(app_clean, name="Failure Bot")

    stub_payload = {
        "status": "failed",
        "message": "platform rejected the token",
        "details": {"http_status": "401", "platform": "stub-platform"},
    }

    def handle_test_connect(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(stub_payload),
        )

    page.route(
        f"**/api/connectors/{account_id}/test/connect", handle_test_connect
    )

    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="connector-test-connection-btn"]')).to_be_visible(
        timeout=8000
    )

    page.locator('[data-testid="connector-test-connection-btn"]').click()

    led = page.locator('[data-testid="connector-test-led"]')
    expect(led).to_have_attribute("data-state", "failed", timeout=8000)
    led_class = led.get_attribute("class")
    assert "indicator-led--danger" in (led_class or ""), led_class

    expect(page.locator('[data-testid="connector-test-message"]')).to_contain_text(
        "platform rejected the token"
    )
    details = page.locator('[data-testid="connector-test-details"]')
    expect(details).to_contain_text("http_status")
    expect(details).to_contain_text("401")
    expect(details).to_contain_text("platform")
    expect(details).to_contain_text("stub-platform")


@pytest.mark.browser
def test_degraded_response_renders_warning_led(app_clean: str, page: Page) -> None:
    """page.route()-fulfilled degraded → amber LED."""
    account_id = seed_connector(app_clean, name="Degraded Bot")

    stub_payload = {
        "status": "degraded",
        "message": "platform is slow but responsive",
        "details": {"latency_ms": "1200"},
    }

    def handle_test_connect(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(stub_payload),
        )

    page.route(
        f"**/api/connectors/{account_id}/test/connect", handle_test_connect
    )

    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="connector-test-connection-btn"]')).to_be_visible(
        timeout=8000
    )

    page.locator('[data-testid="connector-test-connection-btn"]').click()

    led = page.locator('[data-testid="connector-test-led"]')
    expect(led).to_have_attribute("data-state", "degraded", timeout=8000)
    led_class = led.get_attribute("class")
    assert "indicator-led--warning" in (led_class or ""), led_class


@pytest.mark.browser
def test_non_string_detail_renders_as_font_mono_json(app_clean: str, page: Page) -> None:
    """Non-string detail values do NOT surface on `status:'ok'` — details
    panel stays hidden per M07 inspector convention. (Failure-status path
    covers the structured-details rendering shape.)"""
    account_id = seed_connector(app_clean, name="NonString Bot")

    stub_payload = {
        "status": "ok",
        "message": "ok",
        "details": {"count": 42, "enabled": True, "tags": ["a", "b"]},
    }

    def handle_test_connect(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(stub_payload),
        )

    page.route(
        f"**/api/connectors/{account_id}/test/connect", handle_test_connect
    )

    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="connector-test-connection-btn"]')).to_be_visible(
        timeout=8000
    )
    page.locator('[data-testid="connector-test-connection-btn"]').click()

    expect(page.locator('[data-testid="connector-test-led"]')).to_have_attribute(
        "data-state", "ok", timeout=8000
    )
    details_wrap = page.locator('[data-testid="connector-test-details-wrap"]')
    expect(details_wrap).to_be_hidden()


@pytest.mark.browser
def test_secret_shaped_detail_value_passes_through_unmasked(
    app_clean: str, page: Page
) -> None:
    """A masked-token detail value on `status:'ok'` is never surfaced —
    `details_wrap` stays hidden per M07 inspector convention. The
    no-leak property is preserved structurally: the wrap never renders
    on the ok path, so the token never reaches the DOM."""
    account_id = seed_connector(app_clean, name="Masked Detail Bot")

    masked_value = "***...abc1"
    stub_payload = {
        "status": "ok",
        "message": "stub probe ok",
        "details": {"masked_token": masked_value},
    }

    def handle_test_connect(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(stub_payload),
        )

    page.route(
        f"**/api/connectors/{account_id}/test/connect", handle_test_connect
    )

    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="connector-test-connection-btn"]')).to_be_visible(
        timeout=8000
    )
    page.locator('[data-testid="connector-test-connection-btn"]').click()

    led = page.locator('[data-testid="connector-test-led"]')
    expect(led).to_have_attribute("data-state", "ok", timeout=8000)
    details_wrap = page.locator('[data-testid="connector-test-details-wrap"]')
    expect(details_wrap).to_be_hidden(timeout=8000)
