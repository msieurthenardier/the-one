"""Browser tests for the per-agent overlay checkbox-mode label
resolver (M11 F4 L3 A2).

The per-agent overlay's checkbox-mode renders one row per
account-scope chip. F3 L7 HAT surfaced that the row labels were
raw Discord snowflake IDs (e.g. ``1506831630923333722``) instead of
friendly labels (``#gleepglorp-text``). F4 L3 resolves labels via
a lazy fetch of the L4 discoverable-entities cache on first axis
expand, with raw-id fallback on 503 (stub-type), 404 (cold pool),
and network errors.
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
        ],
        "groups": [],
        "roles": [],
    },
    "fetched_at": "2026-05-23T00:00:00Z",
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


def _route_discoverable_503(page: Page, account_id: str) -> None:
    def handle(route):
        route.fulfill(status=503, body="{}")

    page.route(
        f"**/api/connectors/{account_id}/discoverable-entities*",
        handle,
    )


def _route_discoverable_network_error(page: Page, account_id: str) -> None:
    def handle(route):
        route.abort("failed")

    page.route(
        f"**/api/connectors/{account_id}/discoverable-entities*",
        handle,
    )


def _attach_agent_to_account(
    base_url: str, agent_name: str, account_id: str
) -> None:
    cur = httpx.get(f"{base_url}/api/agents/{agent_name}", timeout=5.0)
    assert cur.status_code == 200, f"get agent failed: {cur.status_code} {cur.text}"
    cfg = cur.json()
    ids = list(cfg.get("connector_ids") or [])
    if account_id not in ids:
        ids.append(account_id)
    cfg["connector_ids"] = ids
    r = httpx.put(
        f"{base_url}/api/agents/{agent_name}", json=cfg, timeout=5.0
    )
    assert r.status_code == 200, f"attach agent failed: {r.status_code} {r.text}"


def _open_agent_connectors_tab(
    page: Page, base_url: str, agent_name: str
) -> None:
    page.goto(f"{base_url}#studio/agents/{agent_name}")
    expect(page.locator('[data-testid="tab-connectors"]')).to_be_visible(
        timeout=8000
    )
    page.locator('[data-testid="tab-connectors"]').click()


# ── Tests ────────────────────────────────────────────────────────────


@pytest.mark.browser
def test_per_agent_overlay_checkbox_mode_resolves_discord_labels(
    app_clean: str, page: Page
) -> None:
    """Discord account with channels in allowlist (checkbox-mode) →
    checkbox-row name spans display friendly labels resolved from
    the L4 cache, NOT raw snowflake IDs."""
    provider_id = seed_mock_provider(app_clean, name="mock-label-resolver")
    agent_name = seed_mock_agent(
        app_clean, provider_id, name="label-resolver-agent"
    )
    account_id = seed_connector(
        app_clean,
        type="discord",
        name="Label Resolver Bot",
        secrets={"BOT_TOKEN": "real_bot_token_abcd"},
        config={
            "allowlist": {
                "peers": [],
                "channels": ["111", "222"],
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

    toggle = tile.locator(
        f'[data-testid="connector-acl-axis-toggle-channels-{account_id}"]'
    )
    toggle.click()

    checkbox_wrap = tile.locator(
        f'[data-testid="connector-acl-channels-checkboxes-{account_id}"]'
    )
    expect(checkbox_wrap).to_be_visible(timeout=8000)

    # Name spans display friendly labels (NOT raw IDs).
    name_spans = checkbox_wrap.locator(".mcp-tool-toggle-name")
    expect(name_spans).to_have_count(2)
    expect(name_spans.nth(0)).to_have_text("#general", timeout=8000)
    expect(name_spans.nth(1)).to_have_text("#random")


@pytest.mark.browser
def test_per_agent_overlay_checkbox_mode_stub_shows_raw_ids(
    app_clean: str, page: Page
) -> None:
    """Stub account (plugin lacks enumerate_discoverable_entities;
    L4 returns 503) → checkbox-row name spans display raw IDs
    (regression contract for stub-type / no-hook accounts).
    """
    provider_id = seed_mock_provider(app_clean, name="mock-stub-fallback")
    agent_name = seed_mock_agent(
        app_clean, provider_id, name="stub-fallback-agent"
    )
    account_id = seed_connector(
        app_clean,
        type="stub",
        name="Stub Fallback Bot",
        secrets={"BOT_TOKEN": "any_value"},
        config={
            "allowlist": {
                "peers": [],
                "channels": ["raw-id-A", "raw-id-B"],
                "guilds": [],
                "roles": [],
            }
        },
    )
    _attach_agent_to_account(app_clean, agent_name, account_id)
    _route_discoverable_503(page, account_id)
    _open_agent_connectors_tab(page, app_clean, agent_name)

    tile = page.locator(f'[data-testid="connector-row-{account_id}"]')
    expect(tile).to_be_visible(timeout=8000)

    toggle = tile.locator(
        f'[data-testid="connector-acl-axis-toggle-channels-{account_id}"]'
    )
    toggle.click()

    checkbox_wrap = tile.locator(
        f'[data-testid="connector-acl-channels-checkboxes-{account_id}"]'
    )
    expect(checkbox_wrap).to_be_visible(timeout=8000)

    name_spans = checkbox_wrap.locator(".mcp-tool-toggle-name")
    expect(name_spans).to_have_count(2)
    expect(name_spans.nth(0)).to_have_text("raw-id-A")
    expect(name_spans.nth(1)).to_have_text("raw-id-B")


@pytest.mark.browser
def test_per_agent_overlay_checkbox_mode_network_error_shows_raw_ids(
    app_clean: str, page: Page
) -> None:
    """Discord account; the L4 GET fails (route.abort) →
    checkbox-row name span displays the raw ID (the .catch()
    branch in _ensureLabelCache swallows the error and resolves
    _labelCache to an empty axis-bucketed dict). Regression
    contract for transport-error fallback."""
    provider_id = seed_mock_provider(app_clean, name="mock-net-error")
    agent_name = seed_mock_agent(
        app_clean, provider_id, name="net-error-agent"
    )
    account_id = seed_connector(
        app_clean,
        type="discord",
        name="Net Error Bot",
        secrets={"BOT_TOKEN": "real_bot_token_abcd"},
        config={
            "allowlist": {
                "peers": [],
                "channels": ["111"],
                "guilds": [],
                "roles": [],
            }
        },
    )
    _attach_agent_to_account(app_clean, agent_name, account_id)
    _route_discoverable_network_error(page, account_id)
    _open_agent_connectors_tab(page, app_clean, agent_name)

    tile = page.locator(f'[data-testid="connector-row-{account_id}"]')
    expect(tile).to_be_visible(timeout=8000)

    toggle = tile.locator(
        f'[data-testid="connector-acl-axis-toggle-channels-{account_id}"]'
    )
    toggle.click()

    checkbox_wrap = tile.locator(
        f'[data-testid="connector-acl-channels-checkboxes-{account_id}"]'
    )
    expect(checkbox_wrap).to_be_visible(timeout=8000)

    name_spans = checkbox_wrap.locator(".mcp-tool-toggle-name")
    expect(name_spans).to_have_count(1)
    # Raw-id fallback held; the .catch() branch set _labelCache to
    # an empty axis-bucketed dict so no span was rewritten.
    expect(name_spans.nth(0)).to_have_text("111")
