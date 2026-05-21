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
    page.goto(f"{app_clean}#studio/connectors/new")
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

    page.goto(f"{app_clean}#studio/connectors/new")
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
    """Create returns 422 → operator stays on create form; probe NOT fired.

    F5 L8 HAT: the idle-timeout dropdown no longer allows out-of-range
    values (the previous path to force a backend 422 from the UI). We
    instead intercept POST /api/connector-accounts via Playwright route
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
    # MUST only fulfill on POST; GET /api/connector-accounts and GET
    # /api/connector-accounts/types must pass through (the editor mount
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

    page.route("**/api/connector-accounts", handle_create)

    page.goto(f"{app_clean}#studio/connectors/new")
    expect(page.locator('[data-testid="create-and-test-connector-account-btn"]')).to_be_visible(
        timeout=8000
    )

    page.locator('[data-testid="connector-account-name-input"]').fill("Will-422 Bot")
    page.locator('[data-testid="connector-account-type-select"]').select_option("stub")

    page.locator('[data-testid="create-and-test-connector-account-btn"]').click()

    # Error span surfaces the 422.
    error_el = page.locator('[data-testid="connector-account-editor-error"]')
    expect(error_el).not_to_be_empty(timeout=8000)

    # Operator stays on the create form — Create & Test button still visible.
    expect(page.locator('[data-testid="create-and-test-connector-account-btn"]')).to_be_visible()
    # URL still on /new.
    assert page.evaluate("location.hash") == "#studio/connectors/new"

    # The probe MUST NOT have fired.
    assert probe_requests == [], f"unexpected probe requests: {probe_requests}"


@pytest.mark.browser
def test_create_mode_pick_discord_renders_typed_form(
    app_clean: str, page: Page
) -> None:
    """M11 F1 L7 HAT: picking Discord in create mode re-renders the typed form.

    Pre-fix bug: ``connActiveType`` was hardcoded to ``''`` in create
    mode, so the registry-mediated typed-form path never ran — the
    operator saw the generic kv-table fallback even after picking
    Discord.

    Fix verifies:
      - The Discord typed-form fields (intents fieldset with all three
        checkboxes checked, BOT_TOKEN typed field, guilds list, presence
        editor, Advanced disclosure) appear after picking ``discord``.
      - The generic kv-table is no longer at the top level (it lives
        inside the Advanced ``<details>`` disclosure now).
      - The operator's prior Name input is preserved across the
        re-render.
      - The Type select retains the picked value.
    """
    page.goto(f"{app_clean}#studio/connectors/new")
    expect(page.locator('[data-testid="create-and-test-connector-account-btn"]')).to_be_visible(
        timeout=8000
    )

    # Pre-fix baseline: with no type picked, the generic kv-table is in
    # the DOM (the pre-stub render path falls back to it). Pre-pick the
    # Discord typed-form fields MUST NOT be mounted yet — confirms the
    # registry consult is gated on the picked type.
    expect(page.locator('[data-testid="connector-account-config-table"]')).to_have_count(
        1, timeout=4000
    )
    expect(page.locator('[data-testid="discord-intents-fieldset"]')).to_have_count(0)
    expect(page.locator('[data-testid="discord-bot-token"]')).to_have_count(0)

    # Operator types a name BEFORE picking type — must be preserved on re-render.
    page.locator('[data-testid="connector-account-name-input"]').fill("My Discord Bot")

    # Pick Discord — triggers the create-mode type-change re-render.
    page.locator('[data-testid="connector-account-type-select"]').select_option("discord")

    # Typed Discord fields are now present.
    expect(page.locator('[data-testid="discord-intents-fieldset"]')).to_be_visible(timeout=4000)
    # All three intent checkboxes are checked by default.
    for axis in ("message_content", "members", "guilds"):
        expect(page.locator(f'[data-testid="discord-intent-{axis}"]')).to_be_checked()
    # Typed BOT_TOKEN field.
    expect(page.locator('[data-testid="discord-bot-token"]')).to_be_visible()
    # Guilds list + presence editor.
    expect(page.locator('[data-testid="discord-guilds-list"]')).to_be_visible()
    expect(page.locator('[data-testid="discord-presence-name"]')).to_be_visible()
    expect(page.locator('[data-testid="discord-presence-type"]')).to_be_visible()
    # Advanced kv-table disclosure (closed by default — assert <details>
    # is present but NOT open).
    advanced = page.locator('[data-testid="discord-advanced-kv-disclosure"]')
    expect(advanced).to_be_visible()
    assert advanced.evaluate("(el) => el.open") is False

    # The top-level generic kv-table is no longer at the top of the
    # Config section — it now lives inside the Advanced disclosure.
    # The disclosure being closed means the kv-table is hidden from
    # view, but the DOM node still exists inside <details>. Assert the
    # kv-table's ancestor chain includes the Advanced disclosure.
    kv_table = page.locator('[data-testid="connector-account-config-table"]')
    in_disclosure = kv_table.evaluate(
        "(el) => !!el.closest('[data-testid=\"discord-advanced-kv-disclosure\"]')"
    )
    assert in_disclosure, "generic kv-table should be nested inside the Advanced disclosure"

    # Operator's Name input is preserved across the re-render.
    name_input = page.locator('[data-testid="connector-account-name-input"]')
    expect(name_input).to_have_value("My Discord Bot")

    # Type select retains the picked value.
    type_select = page.locator('[data-testid="connector-account-type-select"]')
    expect(type_select).to_have_value("discord")

    # Save button is enabled (picking a type IS a dirty edit relative
    # to the pre-pick baseline).
    expect(
        page.locator('[data-testid="create-and-test-connector-account-btn"]')
    ).to_be_enabled()
