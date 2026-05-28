"""Browser tests for the allowlist-editor's registry-mediated dropdown
dispatch (M11 F3 L6a).

These tests pin the L6a refactor of
``connector-editor.js:renderAllowlistSection`` / the
``_mountAllowlistAxisEditor`` dispatch helper:

- Discord accounts mount the live-data ``discoverableDropdown``
  component on each of the 4 axes (peers, channels, guilds, roles).
- Stub-type accounts continue mounting the chip-list editor — the
  regression contract for any connector type without a
  ``renderDiscoverableDropdown`` registry hook.
- Storage axis ``'guilds'`` translates to API axis ``'groups'`` before
  the dropdown is invoked (pins the bidirectional mapping centralized
  in the mount helper).
- Selecting / removing items round-trips through
  ``account.config.allowlist.{axis}`` via the per-slot
  ``_allowlistValues`` getter (the dropdown-path bridge for the
  collect path).
- Create-mode does NOT render the allowlist (it is structurally
  edit-mode-only); picking Discord in create-mode must therefore NOT
  fire any GET to ``/api/connectors/*/discoverable-entities``.

The ``discoverable-entities`` API is stubbed via ``page.route()`` so
the tests do not depend on a warm Discord-connector pool or live
Discord credentials.
"""

from __future__ import annotations

import json

import httpx
import pytest
from browser.seeders import seed_connector
from playwright.sync_api import Page, expect


# ── Stub payloads + route helpers ───────────────────────────────────────


_DISCOVERABLE_PAYLOAD = {
    "entities": {
        "peers": [
            {
                "id": "user-1",
                "label": "@operator",
                "group": None,
                "metadata": {},
                "stale": False,
            }
        ],
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
        "roles": [
            {
                "id": "role-1",
                "label": "@admins",
                "group": "guild-1",
                "metadata": {},
                "stale": False,
            }
        ],
    },
    "fetched_at": "2026-05-22T00:00:00Z",
    "stale_seconds": 0,
}


def _route_discoverable_ok(page: Page, account_id: str,
                            payload: dict | None = None) -> None:
    """Stub GET + POST /api/connectors/{id}/discoverable-entities."""
    body = payload if payload is not None else _DISCOVERABLE_PAYLOAD

    def handle(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(body),
        )

    page.route(
        f"**/api/connectors/{account_id}/discoverable-entities*",
        handle,
    )


def _seed_discord(base_url: str, **kwargs) -> str:
    """Seed a ``type='discord'`` account with a default BOT_TOKEN.

    Mirrors the helper in ``test_flow_studio_connector_discord_form.py``
    so the Discord registry entry's typed credentials field has a value
    to render. Extra keyword args pass straight through to
    ``seed_connector``.
    """
    secrets = kwargs.pop("secrets", {"BOT_TOKEN": "real_bot_token_abcd"})
    return seed_connector(
        base_url,
        type="discord",
        secrets=secrets,
        **kwargs,
    )


def _get_account(base_url: str, account_id: str) -> dict:
    r = httpx.get(f"{base_url}/api/connectors/{account_id}", timeout=5.0)
    assert r.status_code == 200, f"get failed: {r.status_code} {r.text}"
    return r.json()


def _activate_access_and_routing_tab(page: Page) -> None:
    """Edit-mode renders a two-tab layout; the allowlist lives on the
    "Access and Routing" tab. Mirrors the helper in
    ``test_flow_studio_connector_editor.py``."""
    page.locator('[data-testid="tab-access-and-routing"]').click()


# ── Tests ────────────────────────────────────────────────────────────────


@pytest.mark.browser
def test_allowlist_axis_renders_dropdown_for_discord_account(
    app_clean: str, page: Page
) -> None:
    """Edit an existing Discord account → each of the 4 allowlist axes
    renders the ``discoverable-dropdown`` component (NOT the chip-list).

    The mapped API axis names are peers / channels / groups / roles —
    the dropdown's ``data-testid`` carries the API axis name, NOT the
    storage axis name. So the ``guilds`` storage row exposes a
    ``discoverable-dropdown-groups`` element.
    """
    account_id = _seed_discord(app_clean, name="Discord Allowlist Bot")
    _route_discoverable_ok(page, account_id)
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(
        timeout=8000
    )
    _activate_access_and_routing_tab(page)

    expect(page.locator('[data-testid="discoverable-dropdown-peers"]')).to_have_count(
        1, timeout=8000
    )
    expect(page.locator('[data-testid="discoverable-dropdown-channels"]')).to_have_count(1)
    # Storage axis "guilds" → API axis "groups".
    expect(page.locator('[data-testid="discoverable-dropdown-groups"]')).to_have_count(1)
    expect(page.locator('[data-testid="discoverable-dropdown-roles"]')).to_have_count(1)
    # And the chip-list editors must NOT be present for any of the 4 axes.
    expect(
        page.locator('[data-testid^="connector-allowlist-"][data-testid$="-chiplist"]')
    ).to_have_count(0)


@pytest.mark.browser
def test_allowlist_axis_renders_chiplist_for_stub_account(
    app_clean: str, page: Page
) -> None:
    """Edit an existing stub account → each axis still renders the
    pre-existing chip-list editor (the regression contract for any
    connector type without a ``renderDiscoverableDropdown`` hook).
    """
    account_id = seed_connector(app_clean, name="Stub Allowlist Bot")
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(
        timeout=8000
    )
    _activate_access_and_routing_tab(page)

    # Existing chip-list testids per ``connector-editor.js:1860``
    # — prefix is ``connector-allowlist-``; the axis name is interpolated
    # before the ``-chiplist`` suffix.
    for axis in ("peers", "channels", "guilds", "roles"):
        expect(
            page.locator(f'[data-testid="connector-allowlist-{axis}-chiplist"]')
        ).to_have_count(1)
    # And no dropdown components rendered for any axis.
    expect(page.locator('[data-testid^="discoverable-dropdown-"]')).to_have_count(0)


@pytest.mark.browser
def test_allowlist_dropdown_onChange_updates_account_config_allowlist(
    app_clean: str, page: Page
) -> None:
    """Open a Discord account → pick a channels-axis item → save → the
    selected id round-trips into ``account.config.allowlist.channels``.

    Pins the full collect-path through the per-slot
    ``_allowlistValues`` getter installed by ``_mountAllowlistAxisEditor``.
    """
    account_id = _seed_discord(app_clean, name="Discord Channels Bot")
    _route_discoverable_ok(page, account_id)
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(
        timeout=8000
    )
    _activate_access_and_routing_tab(page)

    items = page.locator('[data-testid="discoverable-dropdown-item-channels"]')
    expect(items).to_have_count(2, timeout=8000)

    input_el = page.locator('[data-testid="discoverable-dropdown-input-channels"]')
    expect(input_el).to_be_enabled(timeout=4000)
    input_el.focus()
    items.filter(has_text="#general").click()

    # A chip should now render for the selected id.
    expect(
        page.locator('[data-testid="discoverable-dropdown-chip-channels"]')
    ).to_have_count(1)

    save_btn = page.locator('[data-testid="save-connector-btn"]')
    expect(save_btn).not_to_be_disabled(timeout=4000)
    save_btn.click()

    # Wait for save to settle (button is disabled when the recapture fires).
    expect(save_btn).to_be_disabled(timeout=8000)

    persisted = _get_account(app_clean, account_id)
    allowlist = (persisted.get("config") or {}).get("allowlist") or {}
    assert "111" in (allowlist.get("channels") or []), (
        f"expected channel id '111' persisted; allowlist={allowlist!r}"
    )


@pytest.mark.browser
def test_allowlist_dropdown_chip_remove_updates_account_config_allowlist(
    app_clean: str, page: Page
) -> None:
    """Discord account pre-seeded with an allowlisted channel → operator
    clicks the chip's × button → save → the id is gone from
    ``account.config.allowlist.channels`` on reload.
    """
    account_id = _seed_discord(
        app_clean,
        name="Discord Remove Bot",
        config={"allowlist": {"peers": [], "channels": ["111"], "guilds": [], "roles": []}},
    )
    _route_discoverable_ok(page, account_id)
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(
        timeout=8000
    )
    _activate_access_and_routing_tab(page)

    # Wait for the GET to settle so the pre-selected chip's label resolves.
    expect(page.locator('[data-testid="discoverable-dropdown-item-channels"]')).to_have_count(
        2, timeout=8000
    )
    chip = page.locator('[data-testid="discoverable-dropdown-chip-channels"]')
    expect(chip).to_have_count(1)

    remove = page.locator('[data-testid="discoverable-dropdown-chip-remove-channels"]')
    remove.click()
    expect(chip).to_have_count(0)

    save_btn = page.locator('[data-testid="save-connector-btn"]')
    expect(save_btn).not_to_be_disabled(timeout=4000)
    save_btn.click()
    expect(save_btn).to_be_disabled(timeout=8000)

    persisted = _get_account(app_clean, account_id)
    allowlist = (persisted.get("config") or {}).get("allowlist") or {}
    channels = allowlist.get("channels") or []
    assert "111" not in channels, (
        f"expected '111' removed from channels; allowlist={allowlist!r}"
    )


@pytest.mark.browser
def test_allowlist_storage_axis_guilds_maps_to_api_groups(
    app_clean: str, page: Page
) -> None:
    """The storage-axis ``'guilds'`` slot mounts a dropdown whose
    component-internal axis is ``'groups'``. Pins the bidirectional
    storage↔API axis translation centralized in
    ``_mountAllowlistAxisEditor``.
    """
    account_id = _seed_discord(app_clean, name="Discord Groups Bot")
    _route_discoverable_ok(page, account_id)
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(
        timeout=8000
    )
    _activate_access_and_routing_tab(page)

    # The guilds STORAGE slot div contains a dropdown whose outermost
    # element has data-axis="groups" (the API axis name).
    guilds_slot = page.locator('[data-allowlist-chiplist-slot="guilds"]')
    expect(guilds_slot).to_have_count(1)
    dropdown_in_slot = guilds_slot.locator('[data-axis="groups"]')
    expect(dropdown_in_slot).to_have_count(1)
    expect(dropdown_in_slot).to_have_attribute(
        "data-testid", "discoverable-dropdown-groups"
    )

    # And the other three slots host dropdowns whose data-axis matches
    # their storage axis (no translation).
    for storage_axis in ("peers", "channels", "roles"):
        slot = page.locator(f'[data-allowlist-chiplist-slot="{storage_axis}"]')
        expect(slot.locator(f'[data-axis="{storage_axis}"]')).to_have_count(1)


@pytest.mark.browser
def test_create_mode_discord_does_not_render_allowlist(
    app_clean: str, page: Page
) -> None:
    """Create-mode renders flat (no tabs) and structurally omits the
    allowlist section. Picking Discord in the type dropdown MUST NOT
    render any allowlist UI AND MUST NOT fire a GET to
    ``/api/connectors/*/discoverable-entities``.

    Per the F1 L1 ``registry-dispatch-create-mode-AC`` convention's
    "structurally guaranteed" exclusion: the dispatch key (registry
    entry for the picked type) is irrelevant when the surface itself
    does not render in create mode. This is the defensive coverage of
    that exclusion.
    """
    # Capture every request to discoverable-entities so we can assert
    # none fired.
    captured: list[str] = []

    def handle(route):
        captured.append(route.request.method + " " + route.request.url)
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(_DISCOVERABLE_PAYLOAD),
        )

    page.route("**/discoverable-entities*", handle)

    page.goto(f"{app_clean}#studio/connectors/new")
    expect(page.locator('[data-testid="connector-type-select"]')).to_be_visible(
        timeout=8000
    )
    page.locator('[data-testid="connector-type-select"]').select_option("discord")

    # No allowlist UI of either flavor renders.
    expect(
        page.locator('[data-testid^="connector-allowlist-"]')
    ).to_have_count(0)
    expect(page.locator('[data-testid^="discoverable-dropdown-"]')).to_have_count(0)
    expect(
        page.locator('[data-allowlist-chiplist-slot]')
    ).to_have_count(0)

    # And no discoverable-entities fetch fired.
    assert captured == [], (
        f"expected zero discoverable-entities calls in create mode; got {captured!r}"
    )
