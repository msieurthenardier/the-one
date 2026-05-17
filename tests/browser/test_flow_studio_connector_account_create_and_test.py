"""Browser tests for the connector-account 'Create & Test' combined-action flow (M10 F2 L6).

The Create & Test button on the create form fires:
  1. POST /api/connector-accounts
  2. on 201, POST /api/connector-accounts/{new_id}/test/connect
  3. transitions to edit-mode with the probe banner rendered inline.

Three coverage permutations:
  - create + probe both succeed → green banner, account persisted.
  - create succeeds + probe fails → red banner, account is still
    persisted (operator can fix and re-test from edit mode).
  - create returns 422 → operator stays on create form with the error
    surfaced; the probe is NOT fired (asserted via the network log).

Probe responses are stubbed via Playwright ``page.route()`` because
``app_clean`` spawns a uvicorn subprocess (see
``test_connector_test_connection_button.py`` for the rationale).
"""

from __future__ import annotations

import json

import httpx
import pytest
from playwright.sync_api import Page, expect


def _list_accounts(base_url: str) -> list[dict]:
    r = httpx.get(f"{base_url}/api/connector-accounts", timeout=5.0)
    assert r.status_code == 200
    return r.json()


@pytest.mark.browser
def test_create_succeeds_probe_succeeds_lands_in_edit_mode_with_green_banner(
    app_clean: str, page: Page
) -> None:
    """Create + probe ok → operator lands in edit-mode with green LED banner."""
    # Use real stub doctor — default response is status=ok.
    page.goto(f"{app_clean}#studio/connector-accounts/new")
    expect(page.locator('[data-testid="create-and-test-connector-account-btn"]')).to_be_visible(
        timeout=8000
    )

    page.locator('[data-testid="connector-account-name-input"]').fill("Happy Path Bot")
    page.locator('[data-testid="connector-account-type-select"]').select_option("stub")

    page.locator('[data-testid="create-and-test-connector-account-btn"]').click()

    # Editor transitions to edit-mode — Save button (not Create & Test) visible.
    expect(page.locator('[data-testid="save-connector-account-btn"]')).to_be_visible(timeout=8000)
    # LED is green (ok).
    led = page.locator('[data-testid="connector-test-led"]')
    expect(led).to_have_attribute("data-state", "ok", timeout=8000)
    assert "indicator-led--success" in (led.get_attribute("class") or "")

    # Account is persisted — backend list contains it.
    accounts = _list_accounts(app_clean)
    assert any(a["name"] == "Happy Path Bot" for a in accounts)


@pytest.mark.browser
def test_create_succeeds_probe_fails_persists_account_with_red_banner(
    app_clean: str, page: Page
) -> None:
    """Create succeeds but probe fails → account persisted, red LED banner."""
    # Intercept the probe call to fulfill a 'failed' response. The
    # account id isn't known until create succeeds — match any id in the
    # account-id route segment.
    failure_payload = {
        "status": "failed",
        "message": "platform unreachable",
        "details": {"reason": "stub-side simulated outage"},
    }

    def handle_probe(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(failure_payload),
        )

    page.route("**/api/connector-accounts/*/test/connect", handle_probe)

    page.goto(f"{app_clean}#studio/connector-accounts/new")
    expect(page.locator('[data-testid="create-and-test-connector-account-btn"]')).to_be_visible(
        timeout=8000
    )

    page.locator('[data-testid="connector-account-name-input"]').fill("Failure Bot")
    page.locator('[data-testid="connector-account-type-select"]').select_option("stub")

    page.locator('[data-testid="create-and-test-connector-account-btn"]').click()

    # Editor transitions to edit-mode.
    expect(page.locator('[data-testid="save-connector-account-btn"]')).to_be_visible(timeout=8000)
    # Red LED, failure message, details rendered.
    led = page.locator('[data-testid="connector-test-led"]')
    expect(led).to_have_attribute("data-state", "failed", timeout=8000)
    assert "indicator-led--danger" in (led.get_attribute("class") or "")
    expect(page.locator('[data-testid="connector-test-message"]')).to_contain_text(
        "platform unreachable"
    )
    expect(page.locator('[data-testid="connector-test-details"]')).to_contain_text(
        "stub-side simulated outage"
    )

    # Account IS persisted regardless of probe outcome.
    accounts = _list_accounts(app_clean)
    assert any(a["name"] == "Failure Bot" for a in accounts)


@pytest.mark.browser
def test_create_422_blocks_probe_and_surfaces_error_inline(
    app_clean: str, page: Page
) -> None:
    """Create returns 422 → operator stays on create form; probe NOT fired."""
    # Capture every request to /test/connect — must be zero at the end.
    probe_requests: list[str] = []

    def on_request(req):
        if "/test/connect" in req.url:
            probe_requests.append(req.url)

    page.on("request", on_request)

    page.goto(f"{app_clean}#studio/connector-accounts/new")
    expect(page.locator('[data-testid="create-and-test-connector-account-btn"]')).to_be_visible(
        timeout=8000
    )

    # Submit with an empty name → backend 422 (Pydantic rejects empty
    # name via the model_validate path). Type set so the frontend's own
    # 'Name is required' check doesn't short-circuit — backend ownership
    # of validation surface is the leg-artifact expectation.
    #
    # To force a backend 422 (the frontend short-circuits empty name),
    # use an out-of-range idle_timeout that the frontend allows but the
    # backend rejects.
    page.locator('[data-testid="connector-account-name-input"]').fill("Will-422 Bot")
    page.locator('[data-testid="connector-account-type-select"]').select_option("stub")
    page.locator('[data-testid="connector-account-idle-timeout-input"]').fill("0")

    page.locator('[data-testid="create-and-test-connector-account-btn"]').click()

    # Error span surfaces the 422.
    error_el = page.locator('[data-testid="connector-account-editor-error"]')
    expect(error_el).not_to_be_empty(timeout=8000)

    # Operator stays on the create form — Create & Test button still visible.
    expect(page.locator('[data-testid="create-and-test-connector-account-btn"]')).to_be_visible()
    # URL still on /new.
    assert page.evaluate("location.hash") == "#studio/connector-accounts/new"

    # The probe MUST NOT have fired.
    assert probe_requests == [], f"unexpected probe requests: {probe_requests}"
