"""Browser tests for the routing-rules editor's registry-mediated
dropdown dispatch (M11 F3 L6b).

These tests pin the L6b refactor of
``connector-editor.js:_wireRoutingMatchChiplist`` / the new
``_mountRoutingMatchEditor`` dispatch helper applied per-row to the
routing-rules table's match-value cell:

- Discord accounts mount the live-data ``discoverableDropdown``
  component on each rule row's match cell, with the API axis derived
  from the row's scope:
    - ``scope='channel'`` → API axis ``'channels'``
    - ``scope='thread'``  → API axis ``'channels'``
    - ``scope='dm'``      → API axis ``'peers'``
    - ``scope='peer'``    → API axis ``'peers'``
- Stub-type accounts continue mounting the chip-list editor — the
  regression contract for any connector type without a
  ``renderDiscoverableDropdown`` hook.
- Scope changes re-mount the dropdown with the new axis AND clear
  previously-selected match values (ids belonged to the previous
  axis).
- Selecting an item round-trips through ``account.config.routing`` via
  the per-slot ``_routingMatchValues`` getter (the dropdown-path
  bridge for the collect path in ``collectRoutingFromContainer``).

The ``discoverable-entities`` API is stubbed via ``page.route()`` so
the tests do not depend on a warm Discord-connector pool or live
Discord credentials.
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


# ── Stub payloads + route helpers (mirrors L6a) ─────────────────────────


_DISCOVERABLE_PAYLOAD = {
    "entities": {
        "peers": [
            {
                "id": "user-1",
                "label": "@operator",
                "group": None,
                "metadata": {},
                "stale": False,
            },
            {
                "id": "user-2",
                "label": "@deputy",
                "group": None,
                "metadata": {},
                "stale": False,
            },
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


def _attach_agent_to_account(base_url: str, agent_name: str, account_id: str) -> None:
    """Replicate the helper from
    ``test_flow_studio_connector_editor.py``: PUT-attach the
    agent so the routing section's agent dropdown has a selectable
    option once ``fetchAttachedAgents`` resolves.
    """
    cur = httpx.get(f"{base_url}/api/agents/{agent_name}", timeout=5.0)
    assert cur.status_code == 200, f"get agent failed: {cur.status_code} {cur.text}"
    cfg = cur.json()
    ids = list(cfg.get("connector_ids") or [])
    if account_id not in ids:
        ids.append(account_id)
    cfg["connector_ids"] = ids
    r = httpx.put(f"{base_url}/api/agents/{agent_name}", json=cfg, timeout=5.0)
    assert r.status_code == 200, f"attach agent failed: {r.status_code} {r.text}"


def _seed_discord_with_agent(
    base_url: str,
    *,
    account_name: str = "Routing Discord Bot",
    agent_name: str = "router-disco",
    config: dict | None = None,
) -> tuple[str, str]:
    """Seed a ``type='discord'`` account with an attached agent so the
    routing-rules agent dropdown can populate.
    """
    provider_id = seed_mock_provider(base_url, name=f"mock-for-{agent_name}")
    seed_mock_agent(base_url, provider_id, name=agent_name)
    account_id = seed_connector(
        base_url,
        type="discord",
        name=account_name,
        secrets={"BOT_TOKEN": "real_bot_token_abcd"},
        config=config,
    )
    _attach_agent_to_account(base_url, agent_name, account_id)
    return account_id, agent_name


def _seed_stub_with_agent(
    base_url: str,
    *,
    account_name: str = "Routing Stub Bot",
    agent_name: str = "router-stub",
    config: dict | None = None,
) -> tuple[str, str]:
    """Stub-type analogue for the chip-list regression test."""
    provider_id = seed_mock_provider(base_url, name=f"mock-for-{agent_name}")
    seed_mock_agent(base_url, provider_id, name=agent_name)
    account_id = seed_connector(
        base_url,
        name=account_name,
        config=config,
    )
    _attach_agent_to_account(base_url, agent_name, account_id)
    return account_id, agent_name


def _get_account(base_url: str, account_id: str) -> dict:
    r = httpx.get(f"{base_url}/api/connectors/{account_id}", timeout=5.0)
    assert r.status_code == 200, f"get failed: {r.status_code} {r.text}"
    return r.json()


def _activate_access_and_routing_tab(page: Page) -> None:
    page.locator('[data-testid="tab-access-and-routing"]').click()


def _wait_for_routing_agent_dropdown_populated(page: Page, agent_name: str) -> None:
    expect(
        page.locator(
            f'[data-testid="connector-routing-default"] option[value="{agent_name}"]'
        )
    ).to_have_count(1, timeout=8000)


# ── Tests ────────────────────────────────────────────────────────────────


@pytest.mark.browser
def test_routing_match_renders_dropdown_for_discord_channel_scope(
    app_clean: str, page: Page
) -> None:
    """Discord account with one seeded ``scope='channel'`` rule → the
    rule row's match cell mounts the dropdown component with
    ``data-axis="channels"`` (NOT the chip-list editor).
    """
    seeded_rules = [
        {"scope": "channel", "match": ["111"], "agent": "router-disco"},
    ]
    account_id, agent_name = _seed_discord_with_agent(
        app_clean,
        account_name="Routing Channel Bot",
        config={"routing": {"rules": seeded_rules, "default": None}},
    )
    _route_discoverable_ok(page, account_id)
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(
        timeout=8000
    )
    _activate_access_and_routing_tab(page)
    _wait_for_routing_agent_dropdown_populated(page, agent_name)

    row = page.locator('tr.connector-routing-row[data-routing-rule-idx="0"]')
    expect(row).to_be_attached()
    # Match cell hosts the dropdown component (data-axis="channels").
    match_slot = row.locator('[data-routing-match]')
    expect(match_slot.locator('[data-axis="channels"]')).to_have_count(1)
    expect(match_slot.locator('[data-testid="discoverable-dropdown-channels"]')).to_have_count(1)
    # And no chip-list input remains inside the dropdown-mounted slot
    # (the dropdown component owns the slot's children wholesale).
    expect(match_slot.locator('> input.chip-list-input')).to_have_count(0)


@pytest.mark.browser
def test_routing_match_renders_dropdown_for_discord_peer_scope(
    app_clean: str, page: Page
) -> None:
    """Discord account with one seeded ``scope='peer'`` rule → the
    match cell mounts the dropdown with ``data-axis="peers"``.
    """
    seeded_rules = [
        {"scope": "peer", "match": ["user-1"], "agent": "router-disco"},
    ]
    account_id, agent_name = _seed_discord_with_agent(
        app_clean,
        account_name="Routing Peer Bot",
        config={"routing": {"rules": seeded_rules, "default": None}},
    )
    _route_discoverable_ok(page, account_id)
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(
        timeout=8000
    )
    _activate_access_and_routing_tab(page)
    _wait_for_routing_agent_dropdown_populated(page, agent_name)

    row = page.locator('tr.connector-routing-row[data-routing-rule-idx="0"]')
    match_slot = row.locator('[data-routing-match]')
    expect(match_slot.locator('[data-axis="peers"]')).to_have_count(1)
    expect(match_slot.locator('[data-testid="discoverable-dropdown-peers"]')).to_have_count(1)


@pytest.mark.browser
def test_routing_match_thread_scope_uses_channels_axis(
    app_clean: str, page: Page
) -> None:
    """Discord account, ``scope='thread'`` row → the match cell's
    dropdown axis is ``channels`` (per the thread→channels mapping
    centralized in ``_mountRoutingMatchEditor``).
    """
    seeded_rules = [
        {"scope": "thread", "match": ["111"], "agent": "router-disco"},
    ]
    account_id, agent_name = _seed_discord_with_agent(
        app_clean,
        account_name="Routing Thread Bot",
        config={"routing": {"rules": seeded_rules, "default": None}},
    )
    _route_discoverable_ok(page, account_id)
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(
        timeout=8000
    )
    _activate_access_and_routing_tab(page)
    _wait_for_routing_agent_dropdown_populated(page, agent_name)

    row = page.locator('tr.connector-routing-row[data-routing-rule-idx="0"]')
    match_slot = row.locator('[data-routing-match]')
    # Threads narrow channels at the routing-engine layer; the dropdown
    # shows the channel feed.
    expect(match_slot.locator('[data-axis="channels"]')).to_have_count(1)
    expect(match_slot.locator('[data-axis="peers"]')).to_have_count(0)


@pytest.mark.browser
def test_routing_match_renders_chiplist_for_stub_account(
    app_clean: str, page: Page
) -> None:
    """Stub-type account with one seeded routing rule → the match cell
    still renders the pre-existing chip-list editor (regression
    contract for any connector type without a
    ``renderDiscoverableDropdown`` hook).
    """
    seeded_rules = [
        {"scope": "channel", "match": ["ch-a"], "agent": "router-stub"},
    ]
    account_id, agent_name = _seed_stub_with_agent(
        app_clean,
        account_name="Routing Stub Bot",
        config={"routing": {"rules": seeded_rules, "default": None}},
    )
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(
        timeout=8000
    )
    _activate_access_and_routing_tab(page)
    _wait_for_routing_agent_dropdown_populated(page, agent_name)

    row = page.locator('tr.connector-routing-row[data-routing-rule-idx="0"]')
    match_slot = row.locator('[data-routing-match]')
    # The chip-list editor is the slot itself (.connector-routing-match-chiplist);
    # the seeded chip + the live input both remain.
    expect(match_slot.locator('.chip')).to_have_count(1)
    expect(match_slot.locator('.chip-list-input')).to_have_count(1)
    # And no dropdown rendered.
    expect(match_slot.locator('[data-testid^="discoverable-dropdown-"]')).to_have_count(0)


@pytest.mark.browser
def test_routing_scope_change_re_mounts_dropdown_with_new_axis(
    app_clean: str, page: Page
) -> None:
    """Discord account, row scope changes from ``'channel'`` to
    ``'peer'`` → the match cell re-mounts the dropdown with
    ``data-axis="peers"`` AND previous match values are CLEARED (the
    simpler semantics — ids belong to the previous axis).
    """
    seeded_rules = [
        {"scope": "channel", "match": ["111"], "agent": "router-disco"},
    ]
    account_id, agent_name = _seed_discord_with_agent(
        app_clean,
        account_name="Routing Scope-Change Bot",
        config={"routing": {"rules": seeded_rules, "default": None}},
    )
    _route_discoverable_ok(page, account_id)
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(
        timeout=8000
    )
    _activate_access_and_routing_tab(page)
    _wait_for_routing_agent_dropdown_populated(page, agent_name)

    row = page.locator('tr.connector-routing-row[data-routing-rule-idx="0"]')
    match_slot = row.locator('[data-routing-match]')
    # Baseline: channels axis with the pre-selected chip.
    expect(match_slot.locator('[data-axis="channels"]')).to_have_count(1, timeout=8000)
    expect(match_slot.locator('[data-testid="discoverable-dropdown-chip-channels"]')).to_have_count(1)

    # Change scope → expect the dropdown to re-mount with the peers axis.
    row.locator('[data-routing-scope]').select_option("peer")
    expect(match_slot.locator('[data-axis="peers"]')).to_have_count(1)
    expect(match_slot.locator('[data-axis="channels"]')).to_have_count(0)
    # Previous match values are cleared.
    expect(match_slot.locator('[data-testid="discoverable-dropdown-chip-peers"]')).to_have_count(0)


@pytest.mark.browser
def test_routing_match_onChange_persists_via_save_round_trip(
    app_clean: str, page: Page
) -> None:
    """Discord account with an empty routing-rules row → operator
    picks an axis + an item → save → reload → the item id persists in
    ``account.config.routing.rules[0].match`` (pins the
    ``_routingMatchValues`` collect-path bridge).
    """
    account_id, agent_name = _seed_discord_with_agent(
        app_clean,
        account_name="Routing Persist Bot",
    )
    _route_discoverable_ok(page, account_id)
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(
        timeout=8000
    )
    _activate_access_and_routing_tab(page)
    _wait_for_routing_agent_dropdown_populated(page, agent_name)

    # Add a routing rule, pick scope=channel, select a channel from the
    # dropdown, pick the agent, save.
    page.locator('[data-testid="connector-routing-add-row-btn"]').click()
    row = page.locator('tr.connector-routing-row[data-routing-rule-idx="0"]')
    row.locator('[data-routing-scope]').select_option("channel")

    # Scope the dropdown queries to the row's match cell — the allowlist
    # section also renders a channels-axis dropdown on the same tab, so
    # the ambient testids resolve to >1 element.
    match_slot = row.locator('[data-routing-match]')
    items = match_slot.locator('[data-testid="discoverable-dropdown-item-channels"]')
    expect(items).to_have_count(2, timeout=8000)
    input_el = match_slot.locator('[data-testid="discoverable-dropdown-input-channels"]')
    expect(input_el).to_be_enabled(timeout=4000)
    input_el.focus()
    items.filter(has_text="#general").click()
    expect(
        match_slot.locator('[data-testid="discoverable-dropdown-chip-channels"]')
    ).to_have_count(1)

    row.locator('[data-routing-agent]').select_option(agent_name)

    save_btn = page.locator('[data-testid="save-connector-btn"]')
    expect(save_btn).not_to_be_disabled(timeout=4000)
    save_btn.click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)

    persisted = _get_account(app_clean, account_id)
    routing = (persisted.get("config") or {}).get("routing") or {}
    rules = routing.get("rules") or []
    assert len(rules) == 1, f"expected one routing rule persisted; got {rules!r}"
    assert rules[0]["match"] == ["111"], (
        f"expected match=['111'] persisted via dropdown getter; got {rules[0]!r}"
    )
    assert rules[0]["scope"] == "channel"
    assert rules[0]["agent"] == agent_name
