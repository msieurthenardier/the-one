"""Browser tests for the per-peer DM toggle + legacy-entry indicator
(M11 F12 L4).

The per-peer DM toggle lives inside each peer chip in the account-scope
allowlist editor. Visibility is gated by the account-scope
``dm_admission`` mode:

  - ``admin-approved`` → toggle visible + interactive (CSS class
    ``dm-admission-admin-approved`` on the peers field-row).
  - ``all`` / ``none`` → toggle hidden (the class is absent).

Saving persists the boolean per-peer at
``account.config.allowlist.peers[i].dm_allowed`` per the structured-
tuple shape introduced in F12 L3.

The legacy-entry indicator renders on channel/role chips whose
``guild_id`` is ``None`` (pre-v24 migration leaves the field
backfilled to NULL); ``data-legacy="true"`` lands on the chip and an
info glyph (``connector-allowlist-legacy-indicator``) with a tooltip
explains why.

Per-agent overlay (Connectors tab) OMITS the per-peer DM toggle and
renders a one-line note ``"DM admission is account-scope only."`` per
the F12 L3 Truth Table (per-agent ``dm_allowed`` is structurally
uniform but NOT consulted by ACL).
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


# Shared discoverable payload used to stub the Discord-type entities GET.
# ``user-1`` is the peer the tests pre-allowlist + toggle DM on.
_DISCOVERABLE_PAYLOAD = {
    "entities": {
        "peers": [
            {
                "id": "user-1",
                "label": "@alice",
                "group": None,
                "metadata": {},
                "stale": False,
            },
            {
                "id": "user-2",
                "label": "@bob",
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
        ],
        "groups": [
            {
                "id": "guild-1",
                "label": "Test Guild",
                "group": None,
                "metadata": {},
                "stale": False,
            }
        ],
        "roles": [
            {
                "id": "role-1",
                "label": "@mods",
                "group": "guild-1",
                "metadata": {},
                "stale": False,
            },
        ],
    },
    "fetched_at": "2026-05-29T00:00:00Z",
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


def _seed_discord_with_allowlist(
    base_url: str, name: str, *, dm_admission: str = "admin-approved",
    peers: list | None = None, channels: list | None = None,
    roles: list | None = None,
) -> str:
    """Seed a Discord-type account with a fully-structured allowlist."""
    return seed_connector(
        base_url,
        type="discord",
        name=name,
        secrets={"BOT_TOKEN": "real_bot_token_abcd"},
        config={
            "allowlist": {
                "peers": peers if peers is not None else [],
                "channels": channels if channels is not None else [],
                "guilds": [],
                "roles": roles if roles is not None else [],
                "dm_admission": dm_admission,
            }
        },
    )


def _get_account(base_url: str, account_id: str) -> dict:
    r = httpx.get(f"{base_url}/api/connectors/{account_id}", timeout=5.0)
    assert r.status_code == 200, f"get failed: {r.status_code} {r.text}"
    return r.json()


def _activate_access_and_routing_tab(page: Page) -> None:
    page.locator('[data-testid="tab-access-and-routing"]').click()


# ── Tests ────────────────────────────────────────────────────────────────


@pytest.mark.browser
def test_per_peer_dm_toggle_visible_only_under_admin_approved(
    app_clean: str, page: Page
) -> None:
    """Switching ``dm_admission`` between ``admin-approved`` / ``all`` /
    ``none`` toggles the per-peer DM toggle's visibility CSS class on
    the peers section. The toggle DOM stays in the tree across mode
    flips (path (b) — CSS-toggle preserves checkbox state).
    """
    account_id = _seed_discord_with_allowlist(
        app_clean,
        name="DM Toggle Visibility Bot",
        dm_admission="admin-approved",
        peers=[{"id": "user-1", "dm_allowed": True}],
    )
    _route_discoverable_ok(page, account_id)

    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(
        timeout=8000
    )
    _activate_access_and_routing_tab(page)

    peers_row = page.locator('[data-testid="connector-allowlist-peers-row"]')
    expect(peers_row).to_be_visible()

    # Under admin-approved: the peers section carries the CSS class.
    expect(peers_row).to_have_class(
        # The class list contains additional tokens; pattern-match with
        # has_attribute_contains via explicit JS evaluation.
        # Playwright's to_have_class matches the FULL class attribute;
        # use evaluate-based assertion instead.
        # Fall back to attribute-content checks.
        peers_row.evaluate("el => el.className")
    )
    cls_now = peers_row.evaluate("el => el.className")
    assert "dm-admission-admin-approved" in cls_now, (
        f"expected dm-admission-admin-approved class; got: {cls_now!r}"
    )

    # The per-peer toggle's DOM node exists (CSS hides under other modes;
    # we don't assert visibility because Playwright reads display:none
    # on inheritance, and the chip's own visibility depends on the
    # entities GET completing — verify presence-via-locator instead).
    toggle = page.locator(
        '[data-testid="connector-allowlist-peer-dm-toggle-user-1"]'
    )
    # Wait for the chip to render after the discoverable GET resolves.
    expect(toggle).to_have_count(1, timeout=8000)

    # Flip dm_admission → "all": class drops.
    page.locator(
        '[data-testid="connector-allowlist-dm-admission-select"]'
    ).select_option("all")
    cls_all = peers_row.evaluate("el => el.className")
    assert "dm-admission-admin-approved" not in cls_all, (
        f"expected class removed under 'all'; got: {cls_all!r}"
    )
    # Toggle DOM remains (preserves checkbox state).
    expect(toggle).to_have_count(1)

    # Flip → "none": class still absent.
    page.locator(
        '[data-testid="connector-allowlist-dm-admission-select"]'
    ).select_option("none")
    cls_none = peers_row.evaluate("el => el.className")
    assert "dm-admission-admin-approved" not in cls_none, (
        f"expected class removed under 'none'; got: {cls_none!r}"
    )

    # Flip back → "admin-approved": class returns.
    page.locator(
        '[data-testid="connector-allowlist-dm-admission-select"]'
    ).select_option("admin-approved")
    cls_back = peers_row.evaluate("el => el.className")
    assert "dm-admission-admin-approved" in cls_back, (
        f"expected class restored; got: {cls_back!r}"
    )


@pytest.mark.browser
def test_per_peer_dm_toggle_persists_on_save(
    app_clean: str, page: Page
) -> None:
    """Toggling the per-peer DM checkbox and saving round-trips the
    boolean at ``account.config.allowlist.peers[*].dm_allowed``.
    """
    account_id = _seed_discord_with_allowlist(
        app_clean,
        name="DM Toggle Persist Bot",
        dm_admission="admin-approved",
        peers=[{"id": "user-1", "dm_allowed": False}],
    )
    _route_discoverable_ok(page, account_id)

    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(
        timeout=8000
    )
    _activate_access_and_routing_tab(page)

    toggle = page.locator(
        '[data-testid="connector-allowlist-peer-dm-toggle-user-1"]'
    )
    expect(toggle).to_have_count(1, timeout=8000)
    # Pre-state: unchecked (matches the seeded ``dm_allowed: False``).
    expect(toggle).not_to_be_checked()

    # Toggle on + save.
    toggle.check()
    save_btn = page.locator('[data-testid="save-connector-btn"]')
    expect(save_btn).not_to_be_disabled(timeout=4000)
    save_btn.click()
    expect(save_btn).to_be_disabled(timeout=8000)

    # Round-trip: peer's dm_allowed flipped to True.
    after = _get_account(app_clean, account_id)
    peers = after["config"]["allowlist"]["peers"]
    target = next((p for p in peers if p.get("id") == "user-1"), None)
    assert target is not None, f"peer 'user-1' lost on save; peers={peers!r}"
    assert target["dm_allowed"] is True, (
        f"expected dm_allowed=True after toggle; got: {target!r}"
    )


@pytest.mark.browser
def test_per_peer_dm_toggle_hidden_under_all_mode(
    app_clean: str, page: Page
) -> None:
    """Account-scope ``dm_admission="all"`` → peers row does NOT carry
    the ``dm-admission-admin-approved`` class on mount, so the per-peer
    DM toggle is hidden by CSS.
    """
    account_id = _seed_discord_with_allowlist(
        app_clean,
        name="DM Toggle All-Mode Bot",
        dm_admission="all",
        peers=[{"id": "user-1", "dm_allowed": True}],
    )
    _route_discoverable_ok(page, account_id)
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(
        timeout=8000
    )
    _activate_access_and_routing_tab(page)

    peers_row = page.locator('[data-testid="connector-allowlist-peers-row"]')
    expect(peers_row).to_be_visible()
    cls = peers_row.evaluate("el => el.className")
    assert "dm-admission-admin-approved" not in cls, (
        f"expected class absent under 'all'; got: {cls!r}"
    )


@pytest.mark.browser
def test_per_peer_dm_toggle_hidden_under_none_mode(
    app_clean: str, page: Page
) -> None:
    """Account-scope ``dm_admission="none"`` → peers row does NOT carry
    the ``dm-admission-admin-approved`` class on mount.
    """
    account_id = _seed_discord_with_allowlist(
        app_clean,
        name="DM Toggle None-Mode Bot",
        dm_admission="none",
        peers=[{"id": "user-1", "dm_allowed": True}],
    )
    _route_discoverable_ok(page, account_id)
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(
        timeout=8000
    )
    _activate_access_and_routing_tab(page)

    peers_row = page.locator('[data-testid="connector-allowlist-peers-row"]')
    cls = peers_row.evaluate("el => el.className")
    assert "dm-admission-admin-approved" not in cls, (
        f"expected class absent under 'none'; got: {cls!r}"
    )


# M11 F12 L5 — The L4 legacy-indicator browser tests were retired here:
#   - ``test_channel_legacy_indicator_renders_for_null_guild_id``
#   - ``test_role_legacy_indicator_renders_for_null_guild_id``
# Post-v25 there are no null-``guild_id`` channel/role entries to
# indicate (the migration deletes them; the Pydantic validator rejects
# new ones). The migration regression test
# ``TestSchemaV25::test_v25_deletes_orphan_null_guild_id_channels_and_roles``
# covers the "v25 deletes orphans" assertion at a cheaper layer.


@pytest.mark.browser
def test_per_agent_overlay_omits_dm_toggle(
    app_clean: str, page: Page
) -> None:
    """The per-agent overlay (Connectors tab on the agent editor) does
    NOT render per-peer DM toggles — DM admission is account-scope only
    per the F12 L3 Truth Table. The peers axis body renders an
    explanatory note instead.
    """
    provider_id = seed_mock_provider(app_clean, name="mock-no-dm-toggle")
    agent_name = seed_mock_agent(
        app_clean, provider_id, name="no-dm-toggle-agent"
    )
    account_id = _seed_discord_with_allowlist(
        app_clean,
        name="Per-Agent Overlay No-Toggle Bot",
        dm_admission="admin-approved",
        peers=[{"id": "user-1", "dm_allowed": True}],
    )
    # Attach agent.
    cur = httpx.get(f"{app_clean}/api/agents/{agent_name}", timeout=5.0)
    cfg = cur.json()
    cfg["connector_ids"] = list(cfg.get("connector_ids") or []) + [account_id]
    r = httpx.put(
        f"{app_clean}/api/agents/{agent_name}", json=cfg, timeout=5.0
    )
    assert r.status_code == 200, f"attach failed: {r.status_code} {r.text}"
    _route_discoverable_ok(page, account_id)

    page.goto(f"{app_clean}#studio/agents/{agent_name}")
    expect(page.locator('[data-testid="tab-connectors"]')).to_be_visible(
        timeout=8000
    )
    page.locator('[data-testid="tab-connectors"]').click()

    # Expand the peers axis.
    toggle = page.locator(
        f'[data-testid="connector-acl-axis-toggle-peers-{account_id}"]'
    )
    expect(toggle).to_be_visible(timeout=8000)
    toggle.click()

    # The peers section carries the account-scope-only note (testid
    # carries the account id so multiple attached accounts don't
    # collide).
    note = page.locator(
        f'[data-testid="agent-connector-peers-dm-note-{account_id}"]'
    )
    expect(note).to_be_visible(timeout=4000)
    assert "account-scope only" in (note.text_content() or "").lower(), (
        f"expected account-scope note text; got: {note.text_content()!r}"
    )

    # The per-peer DM toggle MUST NOT render anywhere on the agent
    # editor's Connectors tab (the toggle is the connector-editor's
    # surface; per-agent overlay omits it).
    expect(
        page.locator(
            '[data-testid^="connector-allowlist-peer-dm-toggle-"]'
        )
    ).to_have_count(0)
