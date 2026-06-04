"""Browser tests for the hierarchical Server-as-parent allowlist editor
(M11 F12 L5).

Replaces the L4 flat 3-section layout (Servers / Channels / Roles as
siblings) with a hierarchical layout where Servers are the parent
organizer; channels + roles render as nested sub-chiplists under each
server row. The dropdown for channels + roles is server-scoped (i.e.
the operator picks from entities belonging to that specific server).

Wildcard sentinel ``"*"`` rendering: when a server row has no explicit
channel narrowing (channels list is empty for that guild_id), the UI
renders a single ``"(all channels)"`` sentinel chip with
``data-testid="connector-allowlist-channels-wildcard-{guild_id}"``.
Same for roles.

Cascade-delete: when the operator removes a server row, all channel +
role entries with that guild_id are deleted from the underlying state
(including any ``"*"`` sentinels).
"""

from __future__ import annotations

import json

import pytest
from browser.seeders import seed_connector
from playwright.sync_api import Page, expect

# Discoverable payload — 2 servers, each with 1+ channels + roles.
_DISCOVERABLE_PAYLOAD = {
    "entities": {
        "groups": [
            {
                "id": "guild-A",
                "label": "Guild A",
                "metadata": {},
                "stale": False,
            },
            {
                "id": "guild-B",
                "label": "Guild B",
                "metadata": {},
                "stale": False,
            },
        ],
        "channels": [
            {
                "id": "chan-A-1",
                "label": "general",
                "group": "guild-A",
                "metadata": {},
                "stale": False,
            },
            {
                "id": "chan-A-2",
                "label": "off-topic",
                "group": "guild-A",
                "metadata": {},
                "stale": False,
            },
            {
                "id": "chan-B-1",
                "label": "lobby",
                "group": "guild-B",
                "metadata": {},
                "stale": False,
            },
        ],
        "roles": [
            {
                "id": "role-A-mod",
                "label": "moderator",
                "group": "guild-A",
                "metadata": {},
                "stale": False,
            },
            {
                "id": "role-B-admin",
                "label": "admin",
                "group": "guild-B",
                "metadata": {},
                "stale": False,
            },
        ],
        "peers": [
            {
                "id": "user-1",
                "label": "alice",
                "metadata": {},
                "stale": False,
            },
        ],
    },
    "fetched_at": "2026-05-30T00:00:00Z",
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


def _seed_discord_with_hierarchical_allowlist(
    base_url: str,
    name: str,
    *,
    dm_admission: str = "admin-approved",
    peers: list | None = None,
    guilds: list | None = None,
    channels: list | None = None,
    roles: list | None = None,
) -> str:
    """Seed a Discord-type account with a hierarchical allowlist."""
    return seed_connector(
        base_url,
        type="discord",
        name=name,
        secrets={"BOT_TOKEN": "real_bot_token_abcd"},
        config={
            "allowlist": {
                "peers": peers if peers is not None else [],
                "channels": channels if channels is not None else [],
                "guilds": guilds if guilds is not None else [],
                "roles": roles if roles is not None else [],
                "dm_admission": dm_admission,
            }
        },
    )


def _activate_access_and_routing_tab(page: Page) -> None:
    page.locator('[data-testid="tab-access-and-routing"]').click()


@pytest.mark.browser
def test_server_row_renders_with_nested_channels_and_roles(app_clean: str, page: Page) -> None:
    """A server row in the Servers section renders with nested
    channels + roles sub-chiplists. The row's testid is keyed by
    guild_id; the nested chips carry guild-scoped testids."""
    account_id = _seed_discord_with_hierarchical_allowlist(
        app_clean,
        name="Hierarchical Bot",
        guilds=["guild-A"],
        channels=[
            {"guild_id": "guild-A", "channel_id": "chan-A-1"},
        ],
        roles=[
            {"guild_id": "guild-A", "role_id": "role-A-mod"},
        ],
    )
    _route_discoverable_ok(page, account_id)
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(timeout=8000)
    _activate_access_and_routing_tab(page)

    # Server row renders.
    server_row = page.locator('[data-testid="connector-allowlist-server-row-guild-A"]')
    expect(server_row).to_have_count(1, timeout=8000)

    # Nested explicit-channel chip renders inside the row. M11 F12 L5
    # post-fix: explicit chips are owned by the discoverable-dropdown
    # (one chip per id, with friendly label); the L5 raw-id
    # ``connector-allowlist-channel-chip-*`` testids were retired to
    # eliminate the duplicate-chip bug.
    channel_chip = server_row.locator(
        '[data-testid="discoverable-dropdown-chip-channels"][data-id="chan-A-1"]'
    )
    expect(channel_chip).to_have_count(1)

    # Nested explicit-role chip renders inside the row.
    role_chip = server_row.locator(
        '[data-testid="discoverable-dropdown-chip-roles"][data-id="role-A-mod"]'
    )
    expect(role_chip).to_have_count(1)


@pytest.mark.browser
def test_server_added_without_explicit_children_shows_wildcard_sentinels(
    app_clean: str, page: Page
) -> None:
    """When a server row has no explicit channels or roles for its
    guild_id, the UI renders the ``"(all channels)"`` and
    ``"(all roles)"`` wildcard sentinel chips. Tests the
    architect-locked "render sentinel on empty server row" rule
    (regardless of pre-/post-L5 origin)."""
    account_id = _seed_discord_with_hierarchical_allowlist(
        app_clean,
        name="Empty Server Row Bot",
        guilds=["guild-A"],
        # channels + roles intentionally empty for guild-A: the
        # pre-L5 empty-server-row rendering rule means the UI shows
        # the wildcard sentinel even though storage has no entry.
        channels=[],
        roles=[],
    )
    _route_discoverable_ok(page, account_id)
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(timeout=8000)
    _activate_access_and_routing_tab(page)

    # Wildcard sentinel chips render.
    channels_sentinel = page.locator(
        '[data-testid="connector-allowlist-channels-wildcard-guild-A"]'
    )
    expect(channels_sentinel).to_have_count(1, timeout=8000)
    roles_sentinel = page.locator('[data-testid="connector-allowlist-roles-wildcard-guild-A"]')
    expect(roles_sentinel).to_have_count(1)


@pytest.mark.browser
def test_remove_server_row_button_renders_per_server(app_clean: str, page: Page) -> None:
    """Each server row carries a remove button keyed by its guild_id;
    the operator can remove a single server independently."""
    account_id = _seed_discord_with_hierarchical_allowlist(
        app_clean,
        name="Multi-Server Bot",
        guilds=["guild-A", "guild-B"],
        channels=[
            {"guild_id": "guild-A", "channel_id": "chan-A-1"},
            {"guild_id": "guild-B", "channel_id": "chan-B-1"},
        ],
        roles=[],
    )
    _route_discoverable_ok(page, account_id)
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(timeout=8000)
    _activate_access_and_routing_tab(page)

    # Both server rows render with their own remove buttons.
    expect(
        page.locator('[data-testid="connector-allowlist-server-row-remove-guild-A"]')
    ).to_have_count(1, timeout=8000)
    expect(
        page.locator('[data-testid="connector-allowlist-server-row-remove-guild-B"]')
    ).to_have_count(1)


@pytest.mark.browser
def test_explicit_channel_chip_renders_without_wildcard_sentinel(
    app_clean: str, page: Page
) -> None:
    """When a server row has at least one explicit channel chip, the
    wildcard sentinel chip is NOT rendered (the explicit chip
    supersedes the sentinel — per the AC's "sentinel-replacement-on-
    explicit" wiring)."""
    account_id = _seed_discord_with_hierarchical_allowlist(
        app_clean,
        name="Explicit Channel Bot",
        guilds=["guild-A"],
        channels=[
            {"guild_id": "guild-A", "channel_id": "chan-A-1"},
        ],
        roles=[],
    )
    _route_discoverable_ok(page, account_id)
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(timeout=8000)
    _activate_access_and_routing_tab(page)

    # Explicit chip present. M11 F12 L5 post-fix: rendered by the
    # discoverable-dropdown inside the server-scoped channels dropdown.
    server_row = page.locator('[data-testid="connector-allowlist-server-row-guild-A"]')
    expect(server_row).to_have_count(1, timeout=8000)
    expect(
        server_row.locator(
            '[data-testid="discoverable-dropdown-chip-channels"][data-id="chan-A-1"]'
        )
    ).to_have_count(1, timeout=8000)
    # Wildcard channels sentinel NOT present (explicit narrowing).
    expect(
        page.locator('[data-testid="connector-allowlist-channels-wildcard-guild-A"]')
    ).to_have_count(0)
    # Roles sentinel IS present (no explicit role narrowing).
    expect(
        page.locator('[data-testid="connector-allowlist-roles-wildcard-guild-A"]')
    ).to_have_count(1)


@pytest.mark.browser
def test_servers_section_renders_with_section_testid(app_clean: str, page: Page) -> None:
    """The Servers section is the parent organizer; its top-level slot
    carries ``data-testid="connector-allowlist-servers-slot"`` and the
    enclosing row carries
    ``data-testid="connector-allowlist-servers-section"``. Pins the
    structural anchors for future tests."""
    account_id = _seed_discord_with_hierarchical_allowlist(
        app_clean,
        name="Empty Servers Bot",
        guilds=[],  # no servers — the section still renders empty.
    )
    _route_discoverable_ok(page, account_id)
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(timeout=8000)
    _activate_access_and_routing_tab(page)

    expect(page.locator('[data-testid="connector-allowlist-servers-section"]')).to_have_count(
        1, timeout=8000
    )
    expect(page.locator('[data-testid="connector-allowlist-servers-slot"]')).to_have_count(1)
    # No server rows when guilds is empty.
    expect(
        page.locator(
            '[data-testid="connector-allowlist-server-rows"] '
            '> [data-testid^="connector-allowlist-server-row-"]'
        )
    ).to_have_count(0)


@pytest.mark.browser
def test_explicit_wildcard_storage_renders_as_sentinel_chip(app_clean: str, page: Page) -> None:
    """When the underlying storage carries an explicit ``channel_id="*"``
    wildcard entry (i.e. the operator added a server via the
    hierarchical UI without explicit channel narrowing), the chip
    renders as the wildcard sentinel — same testid as the
    rendered-on-empty path."""
    account_id = _seed_discord_with_hierarchical_allowlist(
        app_clean,
        name="Explicit Wildcard Bot",
        guilds=["guild-A"],
        # Explicit wildcard in storage (post-L5 "(all channels)"
        # sentinel) — verify the chip renders.
        channels=[
            {"guild_id": "guild-A", "channel_id": "*"},
        ],
        roles=[
            {"guild_id": "guild-A", "role_id": "*"},
        ],
    )
    _route_discoverable_ok(page, account_id)
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(timeout=8000)
    _activate_access_and_routing_tab(page)

    expect(
        page.locator('[data-testid="connector-allowlist-channels-wildcard-guild-A"]')
    ).to_have_count(1, timeout=8000)
    expect(
        page.locator('[data-testid="connector-allowlist-roles-wildcard-guild-A"]')
    ).to_have_count(1)


@pytest.mark.browser
def test_top_level_channels_and_roles_sections_no_longer_render(app_clean: str, page: Page) -> None:
    """The L4 flat 3-section layout (Channels / Roles as siblings of
    Servers) is gone. Verify the L4 hint testids that anchored those
    rows are NOT present in the post-L5 markup."""
    account_id = _seed_discord_with_hierarchical_allowlist(
        app_clean,
        name="No Flat Sections Bot",
    )
    _route_discoverable_ok(page, account_id)
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(timeout=8000)
    _activate_access_and_routing_tab(page)

    # The L4 flat Channels hint at the top level is gone.
    expect(page.locator('[data-testid="connector-allowlist-channels-hint"]')).to_have_count(0)
    # The L4 flat Roles hint at the top level is gone.
    expect(page.locator('[data-testid="connector-allowlist-roles-hint"]')).to_have_count(0)
    # The Servers (Guilds) hint IS present (still rendered as the
    # parent organizer label).
    expect(page.locator('[data-testid="connector-allowlist-guilds-hint"]')).to_have_count(1)
