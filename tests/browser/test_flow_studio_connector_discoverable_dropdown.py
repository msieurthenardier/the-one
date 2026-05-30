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
from browser.seeders import seed_connector
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
        f"**/api/connectors/{account_id}/discoverable-entities*",
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

    def test_dropdown_refresh_event_triggers_refresh_endpoint(
        self, app_clean: str, page: Page
    ) -> None:
        # F5 L6 HAT R5: per-axis Refresh button removed; refresh now
        # flows from the section-level banner via the
        # ``connector-discoverable-refresh-requested`` event
        # (the banner's Refresh button dispatches it on `document` with
        # ``{ accountId }`` detail; all 4 mounted axis dropdowns listen
        # and POST /refresh on a match). This test mounts the dropdown
        # in isolation (no editor scaffold, so no banner button), then
        # dispatches the event directly to validate the new contract.
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
            f"**/api/connectors/{account_id}/discoverable-entities*",
            handle,
        )
        page.goto(app_clean)
        page.wait_for_load_state("domcontentloaded")

        _mount(page, account_id)
        expect(page.locator(
            '[data-testid="discoverable-dropdown-item-channels"]'
        )).to_have_count(3, timeout=8000)

        # Use ``page.expect_request`` to wait for the POST to fire as a
        # direct consequence of the dispatched event.
        with page.expect_request(
            lambda req: (
                req.method == "POST"
                and req.url.rstrip("/").endswith(
                    "/discoverable-entities/refresh"
                )
            ),
            timeout=8000,
        ) as request_info:
            page.evaluate(
                """(accountId) => {
                    document.dispatchEvent(new CustomEvent(
                        'connector-discoverable-refresh-requested',
                        { detail: { accountId: accountId } }
                    ));
                }""",
                account_id,
            )

        request = request_info.value
        assert request.method == "POST"
        assert "/discoverable-entities/refresh" in request.url

    def test_dropdown_hides_menu_on_pre_probe_404(
        self, app_clean: str, page: Page
    ) -> None:
        # F5 L6 HAT R5: per-axis pre-probe hint removed — the hint now
        # lives on the section-level banner (see
        # ``test_flow_studio_connector_editor.py`` for the
        # banner-state coverage). The dropdown's own status line is
        # cleared on a 404; the menu stays hidden so the operator
        # can't open an empty dropdown.
        account_id = "fake-account-404"
        hint = "Run Test Connection first — cold account."

        def handle(route):
            route.fulfill(
                status=404,
                content_type="application/json",
                body=json.dumps({"detail": hint}),
            )

        page.route(
            f"**/api/connectors/{account_id}/discoverable-entities*",
            handle,
        )
        page.goto(app_clean)
        page.wait_for_load_state("domcontentloaded")

        _mount(page, account_id)

        # Status line clears on a 404 (banner carries the message now).
        # Wait for the menu to be hidden as the proxy for "404 handled".
        menu = page.locator('[data-testid="discoverable-dropdown-menu-channels"]')
        expect(menu).to_be_hidden(timeout=8000)

        status = page.locator('[data-testid="discoverable-dropdown-status-channels"]')
        expect(status).to_have_text("")


# ── M11 F4 L4 fold-in: pool-warmed event refreshes mounted dropdowns ──


_WARMED_PAYLOAD = {
    "entities": {
        "peers": [],
        "channels": [
            {
                "id": "111",
                "label": "#general",
                "group": "guild-1",
                "metadata": {},
                "stale": False,
            }
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
    "fetched_at": "2026-05-23T00:00:00Z",
    "stale_seconds": 0,
}


@pytest.mark.browser
def test_test_connection_pool_warmed_event_refreshes_dropdowns(
    app_clean: str, page: Page
) -> None:
    """M11 F4 L4 HAT fold-in: Test Connection that warms the pool
    (envelope ``details.pool_warmed=true``, the A1 contract) must
    re-fetch any mounted ``discoverable-dropdown`` for the same
    account without requiring the operator to click each axis's
    Refresh button.

    Setup:
      - Seed a Discord account.
      - Stub the L4 GET ``/discoverable-entities`` to return 404
        ("cold pool") for the FIRST call, then 200 with a payload
        carrying ``#general`` for subsequent calls — modeling the
        cold → warm transition.
      - Stub the POST ``/test/connect`` to return
        ``{status: "ok", details: {pool_warmed: true, ...}}``.

    Click Test Connection. Assert the dropdown repopulates from
    the second GET response (``#general`` becomes visible) WITHOUT
    a page reload.
    """
    account_id = seed_connector(
        app_clean,
        name="F4 L4 Warm Bot",
        type="discord",
        secrets={"BOT_TOKEN": "real_bot_token_xyzw"},
        # M11 F12 L5 — channels dropdown is server-scoped post-
        # restructure (rendered inside the server row). Seed a guild
        # so the in-row channels dropdown mounts and the pool-warmed
        # refresh has a target to repopulate.
        config={
            "allowlist": {
                "peers": [],
                "channels": [],
                "guilds": ["guild-1"],
                "roles": [],
            }
        },
    )

    # Pool-state-driven L4 GET router: while the pool is cold, every
    # GET → 404 with the operator-facing hint (mirroring all 4 axes
    # mounted on the Access and Routing tab). After Test Connection's
    # POST flips the state to warm, subsequent GETs → 200 with payload.
    pool_state = {"warm": False}
    get_calls = {"cold": 0, "warm": 0}

    def handle_discoverable(route):
        if route.request.method == "GET":
            if not pool_state["warm"]:
                get_calls["cold"] += 1
                route.fulfill(
                    status=404,
                    content_type="application/json",
                    body=json.dumps(
                        {"detail": "Run Test Connection first — cold account."}
                    ),
                )
                return
            get_calls["warm"] += 1
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(_WARMED_PAYLOAD),
            )
            return
        # POST /refresh path — irrelevant to this test, mirror 200.
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(_WARMED_PAYLOAD),
        )

    page.route(
        f"**/api/connectors/{account_id}/discoverable-entities*",
        handle_discoverable,
    )

    # Stub the Test Connection POST to return a warmed-pool envelope
    # matching the A1 contract pinned at F4 L2. The side-effect of
    # serving this response flips ``pool_state`` so subsequent GETs
    # return the warm payload.
    def handle_test_connect(route):
        pool_state["warm"] = True
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "status": "ok",
                    "message": "ok",
                    "details": {
                        "pool_warmed": True,
                        "pool_warm_error": None,
                    },
                }
            ),
        )

    page.route(
        f"**/api/connectors/{account_id}/test/connect",
        handle_test_connect,
    )

    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(
        page.locator('[data-testid="save-connector-btn"]')
    ).to_be_visible(timeout=8000)

    # Open the Access and Routing tab so the discoverable-dropdown
    # components mount and fire their initial (cold-pool 404) GET.
    # The components ARE mounted as soon as the editor renders (the
    # tab system only toggles the ``hidden`` attribute on panels —
    # both panels' DOM exists simultaneously), but clicking the tab
    # also exercises the operator-realistic mount path.
    page.locator('[data-testid="tab-access-and-routing"]').click()

    # Pre-condition: the section-level banner (F5 L6 HAT R5 — replaces
    # the per-axis pre-probe hint that lived on each dropdown's status
    # line pre-R5) reads the pre-probe state. The banner mounts in
    # the pessimistic ``pre-probe`` pose and the editor-side probe
    # confirms it after the 404 round-trips.
    banner = page.locator('[data-testid="connector-allowlist-banner"]')
    expect(banner).to_have_attribute("data-state", "pre-probe", timeout=8000)

    # Sanity: at least one cold-pool GET fired (one per mounted axis
    # — peers/channels/groups/roles — plus one from the banner probe).
    # We only require ≥1 to confirm the cold-pool state was observed
    # by at least one listener.
    assert get_calls["cold"] >= 1, (
        f"expected ≥1 cold-pool GET, got {get_calls['cold']}"
    )
    assert get_calls["warm"] == 0, (
        f"expected 0 warm GETs pre-click, got {get_calls['warm']}"
    )

    # Switch back to the General tab — that's where Test Connection
    # lives. The Access and Routing panel's dropdowns remain mounted
    # in the DOM (just hidden), so their pool-warmed event listeners
    # are still active.
    page.locator('[data-testid="tab-general"]').click()

    # Click Test Connection. The mocked POST returns
    # ``details.pool_warmed=true``, which should dispatch
    # ``connector-pool-warmed`` and re-fetch the dropdowns
    # even though their tab panel is hidden.
    page.locator('[data-testid="connector-test-connection-btn"]').click()

    # Wait for the LED to flip to ``ok`` so we know
    # ``renderTestConnectionBanner`` ran (and therefore the
    # pool-warmed event has been dispatched).
    expect(
        page.locator('[data-testid="connector-test-led"]')
    ).to_have_attribute("data-state", "ok", timeout=8000)

    # Flip back to Access and Routing to observe the dropdown's
    # post-event state. (The re-fetch already happened in the
    # background while the panel was hidden.)
    page.locator('[data-testid="tab-access-and-routing"]').click()

    # Assert the channels-axis dropdown repopulated from the
    # post-warm GET response without a page reload.
    items = page.locator('[data-testid="discoverable-dropdown-item-channels"]')
    expect(items).to_have_count(1, timeout=8000)
    expect(items.first).to_contain_text("#general")

    # And at least one warm GET fired AFTER the POST — proving the
    # event-driven nudge actually triggered a fresh fetch (not just
    # a stale render carried over).
    assert get_calls["warm"] >= 1, (
        f"expected ≥1 warm GET after pool-warmed event, "
        f"got {get_calls['warm']}"
    )
