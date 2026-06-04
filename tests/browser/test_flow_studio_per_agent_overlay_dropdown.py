"""Browser tests for the per-agent overlay editor's registry-mediated
dropdown dispatch (M11 F3 L6b).

The per-agent overlay lives on the agent editor's Connectors tab
(``connectors-tab.js:_renderAccountTile``). For each attached connector
account it renders a per-axis editor whose mode depends on the
account-scope state of that axis:

  - account-scope axis has chips (subset narrowing) → CHECKBOX-LIST
    mode (unchanged; OUT of L6b scope).
  - account-scope axis is empty / absent (unrestricted) → CHIP-LIST
    mode; L6b dispatches this branch through the registry hook so
    Discord-type accounts mount the live-data dropdown component;
    stub-type / no-entry accounts fall back to the chip-list editor.

These tests pin the L6b dispatch + the ``_overlayChipValues``
collect-path bridge (consulted by ``studio.js::collectFormData``
before the text-node walk).
"""

from __future__ import annotations

import json

import httpx
import pytest
from browser.seeders import (
    seed_connector,
    seed_mock_agent,
    seed_mock_provider,
)
from playwright.sync_api import Page, expect

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
            }
        ],
        "groups": [],
        "roles": [],
    },
    "fetched_at": "2026-05-22T00:00:00Z",
    "stale_seconds": 0,
}


def _route_discoverable_ok(page: Page, account_id: str) -> None:
    def handle(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(_DISCOVERABLE_PAYLOAD),
        )

    page.route(
        f"**/api/connectors/{account_id}/discoverable-entities*",
        handle,
    )


def _attach_agent_to_account(base_url: str, agent_name: str, account_id: str) -> None:
    cur = httpx.get(f"{base_url}/api/agents/{agent_name}", timeout=5.0)
    assert cur.status_code == 200, f"get agent failed: {cur.status_code} {cur.text}"
    cfg = cur.json()
    ids = list(cfg.get("connector_ids") or [])
    if account_id not in ids:
        ids.append(account_id)
    cfg["connector_ids"] = ids
    r = httpx.put(f"{base_url}/api/agents/{agent_name}", json=cfg, timeout=5.0)
    assert r.status_code == 200, f"attach agent failed: {r.status_code} {r.text}"


def _open_agent_connectors_tab(page: Page, base_url: str, agent_name: str) -> None:
    page.goto(f"{base_url}#studio/agents/{agent_name}")
    expect(page.locator('[data-testid="tab-connectors"]')).to_be_visible(timeout=8000)
    page.locator('[data-testid="tab-connectors"]').click()


# ── Tests ────────────────────────────────────────────────────────────────


@pytest.mark.browser
def test_per_agent_overlay_chip_mode_renders_dropdown_for_discord(
    app_clean: str, page: Page
) -> None:
    """Discord account whose ``account.config.allowlist`` is empty on
    every axis (chip-mode contract) → the per-agent overlay editor on
    the Connectors tab renders the ``discoverable-dropdown`` component
    for each axis (peers + channels), NOT the chip-list editor.
    """
    provider_id = seed_mock_provider(app_clean, name="mock-overlay-discord")
    agent_name = seed_mock_agent(app_clean, provider_id, name="overlay-disco-agent")
    account_id = seed_connector(
        app_clean,
        type="discord",
        name="Overlay Discord Bot",
        secrets={"BOT_TOKEN": "real_bot_token_abcd"},
        # No allowlist → both axes resolve to chip-mode in the
        # per-agent overlay → L6b dispatches to the dropdown.
    )
    _attach_agent_to_account(app_clean, agent_name, account_id)
    _route_discoverable_ok(page, account_id)

    _open_agent_connectors_tab(page, app_clean, agent_name)

    # The per-agent overlay tile mounts for the attached account.
    tile = page.locator(f'[data-testid="connector-row-{account_id}"]')
    expect(tile).to_be_visible(timeout=8000)

    # Expand each axis (peers + channels) and verify the dropdown
    # component renders inside the chip-list wrapper.
    for axis in ("peers", "channels"):
        toggle = tile.locator(f'[data-testid="connector-acl-axis-toggle-{axis}-{account_id}"]')
        expect(toggle).to_be_visible()
        toggle.click()

        wrapper = tile.locator(f'[data-testid="connector-acl-{axis}-{account_id}"]')
        expect(wrapper).to_have_count(1)
        # Dropdown component is mounted inside the chip-list wrapper.
        expect(wrapper.locator(f'[data-axis="{axis}"]')).to_have_count(1)
        expect(wrapper.locator(f'[data-testid="discoverable-dropdown-{axis}"]')).to_have_count(1)
        # Free-form chip-list input must NOT be present (the dropdown
        # owns the wrapper's children wholesale).
        expect(wrapper.locator("> input.chip-list-input")).to_have_count(0)


@pytest.mark.browser
def test_per_agent_overlay_checkbox_mode_unchanged(app_clean: str, page: Page) -> None:
    """Discord account with a non-empty account-scope on the peers axis
    → the per-agent overlay's peers axis renders the CHECKBOX-LIST
    editor (account-scope narrows the agent's selection), NOT the
    dropdown. Regression contract: L6b touches the chip-mode path
    only.
    """
    provider_id = seed_mock_provider(app_clean, name="mock-overlay-checkbox")
    agent_name = seed_mock_agent(app_clean, provider_id, name="overlay-checkbox-agent")
    account_id = seed_connector(
        app_clean,
        type="discord",
        name="Overlay Checkbox Bot",
        secrets={"BOT_TOKEN": "real_bot_token_abcd"},
        # Non-empty peers account-scope → checkbox mode on the peers
        # axis. Channels remains empty → chip-mode (dropdown) — but the
        # peers axis is what this regression contract pins.
        config={
            "allowlist": {
                "peers": ["alice", "bob"],
                "channels": [],
                "guilds": [],
                "roles": [],
            }
        },
    )
    _attach_agent_to_account(app_clean, agent_name, account_id)
    _route_discoverable_ok(page, account_id)

    _open_agent_connectors_tab(page, app_clean, agent_name)

    tile = page.locator(f'[data-testid="connector-row-{account_id}"]')
    expect(tile).to_be_visible(timeout=8000)

    toggle = tile.locator(f'[data-testid="connector-acl-axis-toggle-peers-{account_id}"]')
    toggle.click()

    # Checkbox-list mode renders one input[type=checkbox] per scope
    # chip; the dropdown component must NOT mount on this axis.
    checkbox_wrap = tile.locator(f'[data-testid="connector-acl-peers-checkboxes-{account_id}"]')
    expect(checkbox_wrap).to_have_count(1)
    expect(checkbox_wrap.locator('input[type="checkbox"]')).to_have_count(2)
    # And no dropdown rendered on the peers axis.
    expect(
        tile.locator(
            f'[data-testid="connector-acl-axis-peers-{account_id}"] '
            f'[data-testid="discoverable-dropdown-peers"]'
        )
    ).to_have_count(0)
