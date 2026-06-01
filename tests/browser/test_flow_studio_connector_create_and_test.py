"""Browser tests for the connector 'Create & Test' combined-action flow (M10 F2 L6).

The Create & Test button on the create form fires:
  1. POST /api/connectors
  2. on 201, POST /api/connectors/{new_id}/test/connect
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
    r = httpx.get(f"{base_url}/api/connectors", timeout=5.0)
    assert r.status_code == 200
    return r.json()


@pytest.mark.browser
def test_create_succeeds_probe_succeeds_lands_in_edit_mode_with_green_banner(
    app_clean: str, page: Page
) -> None:
    """Create + probe ok → operator lands in edit-mode with green LED banner."""
    # Use real stub doctor — default response is status=ok.
    page.goto(f"{app_clean}#studio/connectors/new")
    expect(page.locator('[data-testid="create-and-test-connector-btn"]')).to_be_visible(
        timeout=8000
    )

    page.locator('[data-testid="connector-name-input"]').fill("Happy Path Bot")
    page.locator('[data-testid="connector-type-select"]').select_option("stub")

    page.locator('[data-testid="create-and-test-connector-btn"]').click()

    # Editor transitions to edit-mode — Save button (not Create & Test) visible.
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(timeout=8000)
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

    page.route("**/api/connectors/*/test/connect", handle_probe)

    page.goto(f"{app_clean}#studio/connectors/new")
    expect(page.locator('[data-testid="create-and-test-connector-btn"]')).to_be_visible(
        timeout=8000
    )

    page.locator('[data-testid="connector-name-input"]').fill("Failure Bot")
    page.locator('[data-testid="connector-type-select"]').select_option("stub")

    page.locator('[data-testid="create-and-test-connector-btn"]').click()

    # Editor transitions to edit-mode.
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(timeout=8000)
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
    """Create returns 422 → operator stays on create form; probe NOT fired.

    F5 L8 HAT: the idle-timeout dropdown no longer allows out-of-range
    values (the previous path to force a backend 422 from the UI). We
    instead intercept POST /api/connectors via Playwright route
    to synthesize a 422 response, then verify the error surfaces inline
    and the probe call is NEVER fired.
    """
    # Capture every request to /test/connect — must be zero at the end.
    probe_requests: list[str] = []

    def on_request(req):
        if "/test/connect" in req.url:
            probe_requests.append(req.url)

    page.on("request", on_request)

    # Intercept the POST so the test owns the 422 response. The handler
    # MUST only fulfill on POST; GET /api/connectors and GET
    # /api/connectors/types must pass through (the editor mount
    # depends on the types fetch resolving).
    def handle_create(route):
        if route.request.method == "POST":
            route.fulfill(
                status=422,
                content_type="application/json",
                body=(
                    '{"detail":[{"loc":["body","idle_timeout_seconds"],'
                    '"msg":"value must be >= 1","type":"value_error"}]}'
                ),
            )
        else:
            route.continue_()

    page.route("**/api/connectors", handle_create)

    page.goto(f"{app_clean}#studio/connectors/new")
    expect(page.locator('[data-testid="create-and-test-connector-btn"]')).to_be_visible(
        timeout=8000
    )

    page.locator('[data-testid="connector-name-input"]').fill("Will-422 Bot")
    page.locator('[data-testid="connector-type-select"]').select_option("stub")

    page.locator('[data-testid="create-and-test-connector-btn"]').click()

    # Error span surfaces the 422.
    error_el = page.locator('[data-testid="connector-editor-error"]')
    expect(error_el).not_to_be_empty(timeout=8000)

    # Operator stays on the create form — Create & Test button still visible.
    expect(page.locator('[data-testid="create-and-test-connector-btn"]')).to_be_visible()
    # URL still on /new.
    assert page.evaluate("location.hash") == "#studio/connectors/new"

    # The probe MUST NOT have fired.
    assert probe_requests == [], f"unexpected probe requests: {probe_requests}"


@pytest.mark.browser
def test_create_mode_pick_discord_does_not_render_runtime_config_inline(
    app_clean: str, page: Page
) -> None:
    """F5 L6 HAT: picking Discord in create mode does NOT render runtime config inline.

    Pre-L6 behavior: ``renderConnectionFields(account, isCreate=true)``
    delegated to ``_renderRuntimeConfigBody`` so the operator saw
    Intents / Servers / Presence / Advanced inside the create-mode flat
    layout. Operator HAT feedback (F5 L6) was that create-mode should be
    minimal — typed runtime config is configured post-create on the
    Access-and-Routing tab in edit mode. The hook was inverted to return
    ``''`` unconditionally; this test pins the inverted contract.

    The ``registry-dispatch-create-mode-AC`` convention itself is
    unchanged — it remains about post-pick re-render correctness, NOT
    about which fields render. This test asserts the post-pick re-render
    still executes (the Type select retains the picked value, the
    operator's Name input is preserved across the re-render, and the
    page doesn't crash) — it just doesn't surface the runtime-config
    typed fields anymore.
    """
    page.goto(f"{app_clean}#studio/connectors/new")
    expect(page.locator('[data-testid="create-and-test-connector-btn"]')).to_be_visible(
        timeout=8000
    )

    # Pre-pick baseline: the generic kv-table is in the DOM (pre-stub
    # render path) and the Discord typed-form fields are not yet mounted.
    expect(page.locator('[data-testid="connector-config-table"]')).to_have_count(
        1, timeout=4000
    )
    # F5 L6 HAT round-2: testid migrated from ``discord-intents-fieldset``
    # to ``discord-intents-row`` (the fieldset was replaced with a
    # ``.field-row.admin-pf-row`` container).
    expect(page.locator('[data-testid="discord-intents-row"]')).to_have_count(0)
    expect(page.locator('[data-testid="discord-bot-token"]')).to_have_count(0)

    # Operator types a name BEFORE picking type — must be preserved on re-render.
    page.locator('[data-testid="connector-name-input"]').fill("My Discord Bot")

    # Pick Discord — triggers the create-mode type-change re-render.
    page.locator('[data-testid="connector-type-select"]').select_option("discord")

    # F5 L6 HAT inversion: the Discord typed-form runtime-config fields
    # (intents fieldset, guilds list, presence editor, Advanced
    # disclosure) MUST NOT render in create mode. Configure on the A&R
    # tab post-create. Use ``to_have_count(0)`` because the node is not
    # mounted at all (an absent element is not "visible" but also has
    # zero matches — the stronger assertion).
    # F5 L6 HAT round-2: testids migrated for the restructured rows —
    # ``discord-intents-fieldset`` → ``discord-intents-row`` and
    # ``discord-advanced-kv-disclosure`` → ``discord-additional-config-row``.
    # The per-input testids (presence-name / presence-type) were
    # preserved. M11 F14 L02: the ``discord-guilds-list`` ("Scope to
    # servers") field was retired entirely — guild scoping unified onto
    # the allowlist "Servers" axis — so it no longer renders in either
    # create or edit mode and its create-mode-absence assertion is
    # dropped.
    expect(page.locator('[data-testid="discord-intents-row"]')).to_have_count(0)
    expect(page.locator('[data-testid="discord-presence-name"]')).to_have_count(0)
    expect(page.locator('[data-testid="discord-presence-type"]')).to_have_count(0)
    expect(page.locator('[data-testid="discord-additional-config-row"]')).to_have_count(0)

    # The Discord typed BOT_TOKEN field DOES render in create mode (it's
    # in the Credentials section, not the runtime-config block) —
    # explicit positive assertion so the test pins which Discord typed
    # fields are still surfaced.
    expect(page.locator('[data-testid="discord-bot-token"]')).to_be_visible(timeout=4000)

    # The Type select retains the picked value (post-pick re-render
    # correctness — the registry-dispatch-create-mode-AC convention).
    type_select = page.locator('[data-testid="connector-type-select"]')
    expect(type_select).to_have_value("discord")

    # Operator's Name input is preserved across the re-render.
    name_input = page.locator('[data-testid="connector-name-input"]')
    expect(name_input).to_have_value("My Discord Bot")

    # Type select retains the picked value.
    type_select = page.locator('[data-testid="connector-type-select"]')
    expect(type_select).to_have_value("discord")

    # Save button is enabled (picking a type IS a dirty edit relative
    # to the pre-pick baseline).
    expect(
        page.locator('[data-testid="create-and-test-connector-btn"]')
    ).to_be_enabled()
