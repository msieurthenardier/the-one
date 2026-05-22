"""Browser tests for ``App.studio.discoverableDropdown`` (M11 F3 L5).

The component is mounted in isolation via ``page.evaluate()`` into a
test harness ``<div>``; the API GET (and Refresh POST) are fulfilled by
``page.route()`` so the tests do not depend on a warm connector pool.
The route handlers MUST be registered BEFORE ``page.goto(...)`` so the
initial app load + the in-component ``fetch()`` both hit the stubbed
responses (rather than a real backend or 404).

Test contract pinned: typeahead filter; chip selection / removal fires
onChange; stale-entry rendering; Refresh POST; pre-probe 404 hint;
group-section rendering; data-stale attribute propagation.
"""

from __future__ import annotations

import json

import pytest
from playwright.sync_api import Page, expect


_STUB_PAYLOAD = {
    "entities": {
        "peers": [],
        "channels": [
            {
                "id": "111",
                "label": "#general",
                "group": "guild-1",
                "metadata": {},
                "stale": False,
            },
            {
                "id": "222",
                "label": "#random",
                "group": "guild-1",
                "metadata": {},
                "stale": False,
            },
            {
                "id": "333",
                "label": "#deprecated",
                "group": "guild-1",
                "metadata": {},
                "stale": True,
            },
        ],
        "groups": [
            {
                "id": "guild-1",
                "label": "GleepGlorp Guild",
                "group": None,
                "metadata": {},
                "stale": False,
            }
        ],
        "roles": [],
    },
    "fetched_at": "2026-05-22T00:00:00Z",
    "stale_seconds": 0,
}


_MOUNT_HARNESS_JS = """
({ accountId, axis, currentValues }) => {
    let harness = document.getElementById('dd-test-harness');
    if (harness) harness.remove();
    harness = document.createElement('div');
    harness.id = 'dd-test-harness';
    document.body.appendChild(harness);

    window._lastOnChange = null;
    const element = window.App.studio.discoverableDropdown({
        axis: axis,
        accountId: accountId,
        currentValues: currentValues || [],
        onChange: function (values) { window._lastOnChange = values; },
        vocab: { peer: 'user', channel: 'channel', group: 'server', role: 'role' }
    });
    harness.appendChild(element);
    return true;
}
"""


def _route_get_ok(page: Page, account_id: str, payload: dict | None = None) -> None:
    body = payload if payload is not None else _STUB_PAYLOAD

    def handle(route):
        if route.request.method == "POST":
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(body),
            )
        else:
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(body),
            )

    page.route(
        f"**/api/connector-accounts/{account_id}/discoverable-entities*",
        handle,
    )


def _mount(page: Page, account_id: str, axis: str = "channels",
           current_values: list | None = None) -> None:
    page.evaluate(
        _MOUNT_HARNESS_JS,
        {"accountId": account_id, "axis": axis,
         "currentValues": current_values or []},
    )


@pytest.mark.browser
class TestDiscoverableDropdown:
    def test_dropdown_populates_from_api_response(
        self, app_clean: str, page: Page
    ) -> None:
        account_id = "fake-account-populates"
        _route_get_ok(page, account_id)
        page.goto(app_clean)
        page.wait_for_load_state("domcontentloaded")

        _mount(page, account_id)

        # Wait for the GET to settle and the menu to render the items.
        items = page.locator('[data-testid="discoverable-dropdown-item-channels"]')
        expect(items).to_have_count(3, timeout=8000)
        # Group-section is present (channels share ``guild-1``).
        expect(page.locator(
            '[data-testid="discoverable-dropdown-menu-channels"] '
            '.discoverable-dropdown-group'
        )).to_have_count(1)

    def test_dropdown_typeahead_filters_by_label_substring(
        self, app_clean: str, page: Page
    ) -> None:
        account_id = "fake-account-typeahead"
        _route_get_ok(page, account_id)
        page.goto(app_clean)
        page.wait_for_load_state("domcontentloaded")

        _mount(page, account_id)
        expect(page.locator(
            '[data-testid="discoverable-dropdown-item-channels"]'
        )).to_have_count(3, timeout=8000)

        input_el = page.locator('[data-testid="discoverable-dropdown-input-channels"]')
        # Wait for the input to be enabled (initial load completes).
        expect(input_el).to_be_enabled(timeout=8000)
        input_el.fill("gen")

        # Only #general should remain visible; the other two are hidden.
        visible = page.locator(
            '[data-testid="discoverable-dropdown-item-channels"]:not([hidden])'
        )
        expect(visible).to_have_count(1, timeout=4000)
        expect(visible).to_have_text("#general")

    def test_dropdown_select_item_fires_onChange_with_new_value(
        self, app_clean: str, page: Page
    ) -> None:
        account_id = "fake-account-select"
        _route_get_ok(page, account_id)
        page.goto(app_clean)
        page.wait_for_load_state("domcontentloaded")

        _mount(page, account_id)
        items = page.locator('[data-testid="discoverable-dropdown-item-channels"]')
        expect(items).to_have_count(3, timeout=8000)

        # Open the menu by focusing the input, then click the item.
        input_el = page.locator('[data-testid="discoverable-dropdown-input-channels"]')
        expect(input_el).to_be_enabled(timeout=4000)
        input_el.focus()

        general = items.filter(has_text="#general")
        general.click()

        # Read the captured onChange argument.
        result = page.evaluate("() => window._lastOnChange")
        assert result == ["111"], f"Expected ['111'], got {result!r}"

    def test_dropdown_chip_remove_fires_onChange_with_value_dropped(
        self, app_clean: str, page: Page
    ) -> None:
        account_id = "fake-account-remove"
        _route_get_ok(page, account_id)
        page.goto(app_clean)
        page.wait_for_load_state("domcontentloaded")

        _mount(page, account_id, current_values=["111"])
        # Wait for the initial fetch to settle so chip labels resolve.
        expect(page.locator(
            '[data-testid="discoverable-dropdown-item-channels"]'
        )).to_have_count(3, timeout=8000)

        # Chip is rendered for the pre-populated value.
        chip = page.locator('[data-testid="discoverable-dropdown-chip-channels"]')
        expect(chip).to_have_count(1)

        remove = page.locator(
            '[data-testid="discoverable-dropdown-chip-remove-channels"]'
        )
        remove.click()

        result = page.evaluate("() => window._lastOnChange")
        assert result == [], f"Expected [], got {result!r}"
        # And the chip is no longer in the DOM.
        expect(chip).to_have_count(0)

    def test_dropdown_stale_entry_renders_with_data_stale_attribute(
        self, app_clean: str, page: Page
    ) -> None:
        account_id = "fake-account-stale"
        _route_get_ok(page, account_id)
        page.goto(app_clean)
        page.wait_for_load_state("domcontentloaded")

        _mount(page, account_id)
        items = page.locator('[data-testid="discoverable-dropdown-item-channels"]')
        expect(items).to_have_count(3, timeout=8000)

        # The #deprecated item has stale=true in the stub payload.
        stale_item = items.filter(has_text="#deprecated")
        expect(stale_item).to_have_attribute("data-stale", "true")
        # And the broader stale-selector check via evaluate (the CSS
        # rule lives behind it; we assert the attribute is what the
        # selector matches).
        match_count = page.evaluate(
            """() => document.querySelectorAll(
                '.discoverable-dropdown-item[data-stale="true"]'
            ).length"""
        )
        assert match_count == 1, f"Expected exactly 1 stale item, got {match_count}"

    def test_dropdown_refresh_button_posts_refresh_endpoint(
        self, app_clean: str, page: Page
    ) -> None:
        account_id = "fake-account-refresh"
        # Capture every method-URL the route handler sees so we can
        # assert that POST .../refresh was called.
        captured: list[tuple[str, str]] = []

        def handle(route):
            captured.append((route.request.method, route.request.url))
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(_STUB_PAYLOAD),
            )

        page.route(
            f"**/api/connector-accounts/{account_id}/discoverable-entities*",
            handle,
        )
        page.goto(app_clean)
        page.wait_for_load_state("domcontentloaded")

        _mount(page, account_id)
        expect(page.locator(
            '[data-testid="discoverable-dropdown-item-channels"]'
        )).to_have_count(3, timeout=8000)

        refresh = page.locator('[data-testid="discoverable-dropdown-refresh-channels"]')
        # Use ``page.expect_request`` to wait for the POST to fire as a
        # direct consequence of the click. This is more reliable than
        # polling the captured list because the Playwright route handler
        # runs out-of-band relative to the test thread.
        with page.expect_request(
            lambda req: (
                req.method == "POST"
                and req.url.rstrip("/").endswith(
                    "/discoverable-entities/refresh"
                )
            ),
            timeout=8000,
        ) as request_info:
            refresh.click()

        request = request_info.value
        assert request.method == "POST"
        assert "/discoverable-entities/refresh" in request.url

    def test_dropdown_renders_pre_probe_hint_when_api_404(
        self, app_clean: str, page: Page
    ) -> None:
        account_id = "fake-account-404"
        hint = "Run Test Connection first — cold account."

        def handle(route):
            route.fulfill(
                status=404,
                content_type="application/json",
                body=json.dumps({"detail": hint}),
            )

        page.route(
            f"**/api/connector-accounts/{account_id}/discoverable-entities*",
            handle,
        )
        page.goto(app_clean)
        page.wait_for_load_state("domcontentloaded")

        _mount(page, account_id)

        status = page.locator('[data-testid="discoverable-dropdown-status-channels"]')
        expect(status).to_contain_text(hint, timeout=8000)

        menu = page.locator('[data-testid="discoverable-dropdown-menu-channels"]')
        expect(menu).to_be_hidden()
