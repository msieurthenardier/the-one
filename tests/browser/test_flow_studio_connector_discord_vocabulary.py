"""Studio Connector Discord-vocabulary display-text tests (M11 F1 L6).

L6 introduces a frontend per-connector-type vocabulary map
(``App.studio.connectorVocabulary``) consulted at three editor render
sites: Allowlist labels + hints, Attached-agents table headers, and
the Routing-rules scope-dropdown option text. The substrate vocabulary
(Pydantic models, ``_VALID_ROUTING_SCOPES`` literals, ACL field names,
audit-log keys) stays unchanged — only the rendered display text
varies per type.

Coverage:

- Discord-type account renders the substituted labels ("Users",
  "Servers") in the Allowlist section and "Users" in the Attached-
  agents table header.
- Discord-type account hints drop the "Discord-flavored" qualifier on
  the groups + roles rows (``hintTone === 'native'``).
- Discord-type account renders ``<option>`` textContent "user" for the
  ``peer`` scope value in the routing-rules scope dropdown — while the
  ``<option value>`` attribute STAYS at the literal ``peer``.
- ``'stub'``-type account preserves the pre-L6 "Peers / Channels /
  Guilds / Roles" labels (generic baseline; existing tests must pass
  unmodified).
- Save round-trip on a Discord account: ``config.allowlist.peers`` /
  ``.channels`` / ``.guilds`` / ``.roles`` field names persist (the
  wire-layer vocabulary is unchanged by the display-text substitution).
"""

from __future__ import annotations

import httpx
import pytest
from browser.seeders import seed_connector_account
from playwright.sync_api import Page, expect


def _get_account(base_url: str, account_id: str) -> dict:
    r = httpx.get(f"{base_url}/api/connector-accounts/{account_id}", timeout=5.0)
    assert r.status_code == 200, f"get failed: {r.status_code} {r.text}"
    return r.json()


def _put_account(base_url: str, account_id: str, payload: dict) -> dict:
    r = httpx.put(
        f"{base_url}/api/connector-accounts/{account_id}", json=payload, timeout=5.0
    )
    assert r.status_code == 200, f"put failed: {r.status_code} {r.text}"
    return r.json()


# ── Tests ────────────────────────────────────────────────────────────────


@pytest.mark.browser
def test_discord_account_renders_substituted_allowlist_labels(
    app_clean: str, page: Page
) -> None:
    """Discord-type account: Allowlist <label> text reads "Users" and
    "Servers" (substituted via ``connectorVocabulary``). The pre-L6
    "Peers" / "Guilds" labels MUST NOT appear on the page."""
    account_id = seed_connector_account(
        app_clean,
        name="Vocab Discord",
        type="discord",
        secrets={"BOT_TOKEN": "plaintext"},
    )
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-account-btn"]')).to_be_visible(
        timeout=8000
    )

    # Switch to the Access and Routing tab so the allowlist section is
    # visible (the L9 tabbed layout puts Allowlist behind the secondary
    # tab; the section is mounted in the DOM at editor-load but only
    # the active tab's content is visually present for text queries).
    page.locator('[data-testid="tab-access-and-routing"]').click()

    # Read the four allowlist <label> elements directly off the section
    # — we anchor to the section selector instead of a page-wide text
    # match so the L4-form's own connection-side "Guilds" label
    # (Discord-intent typed input) doesn't pollute the assertion. L6
    # owns the allowlist surface; L4 owns the typed connection fields.
    allowlist_labels = page.locator(
        '.connector-allowlist-section .connector-account-acl-fieldlabel'
    ).evaluate_all("els => els.map(e => e.textContent.trim())")
    assert allowlist_labels == ["Users", "Channels", "Servers", "Roles"], (
        f"Discord allowlist labels drifted; got: {allowlist_labels!r}"
    )


@pytest.mark.browser
def test_discord_account_hints_drop_discord_flavored_qualifier(
    app_clean: str, page: Page
) -> None:
    """Discord-type account: the Guilds + Roles hints drop the
    "Discord-flavored; ignored by other platforms." qualifier
    (``hintTone === 'native'``). The substituted singular ("server" /
    "role") still appears in the leading hint text."""
    account_id = seed_connector_account(
        app_clean,
        name="Hint Discord",
        type="discord",
        secrets={"BOT_TOKEN": "plaintext"},
    )
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-account-btn"]')).to_be_visible(
        timeout=8000
    )
    page.locator('[data-testid="tab-access-and-routing"]').click()

    guilds_hint = page.locator('[data-testid="connector-allowlist-guilds-hint"]')
    roles_hint = page.locator('[data-testid="connector-allowlist-roles-hint"]')
    expect(guilds_hint).to_be_visible()
    expect(roles_hint).to_be_visible()

    guilds_text = guilds_hint.text_content() or ""
    roles_text = roles_hint.text_content() or ""

    # Substituted leading hint text.
    assert "no server restriction" in guilds_text, (
        f"expected substituted 'server' singular in guilds hint; got: {guilds_text!r}"
    )
    assert "no role restriction" in roles_text, (
        f"expected 'role' singular in roles hint; got: {roles_text!r}"
    )

    # Drop the "Discord-flavored" qualifier on a Discord-type account.
    assert "Discord-flavored" not in guilds_text, (
        f"native-tone account should not show 'Discord-flavored' in guilds hint; "
        f"got: {guilds_text!r}"
    )
    assert "Discord-flavored" not in roles_text, (
        f"native-tone account should not show 'Discord-flavored' in roles hint; "
        f"got: {roles_text!r}"
    )

    # Page-wide: the full disclaimer string must not appear anywhere on
    # the rendered editor for a Discord-type account.
    assert (
        page.get_by_text(
            "Discord-flavored; ignored by other platforms.", exact=False
        ).count()
        == 0
    )


@pytest.mark.browser
def test_discord_account_attached_agents_header_renders_substituted_labels(
    app_clean: str, page: Page
) -> None:
    """Discord-type account: when ``renderAttachedAgentsList`` is
    invoked with non-empty rows, the <th> cells read "Users" /
    "Channels" (substituted) instead of "Peers" / "Channels".

    Forcing a non-empty render path: we drive the function directly
    via ``page.evaluate`` using the global module namespace. The
    function is IIFE-local, but the rendered table is what we assert
    against — so we mount the table by injecting a stub row through
    the live function reference, which is reachable because the
    editor's IIFE attaches ``renderConnectorAccountEditor`` to the
    global namespace (other functions are local). The pragmatic
    fallback: navigate to the editor and check the DOM after the
    real fetchAttachedAgents resolves — but the fixture has no
    attached agents, so the header would not render.
    """
    # Pragmatic approach: inject a mock fetch response so the
    # attached-agents fetch resolves with non-empty rows, then read
    # the rendered <th> cells.
    account_id = seed_connector_account(
        app_clean,
        name="Attached Discord",
        type="discord",
        secrets={"BOT_TOKEN": "plaintext"},
    )

    # Stub the fetch BEFORE navigation so the attached-agents fetch
    # is intercepted on initial mount. Playwright route interception
    # only fires for the page's own requests; httpx seeders use the
    # outer process and don't go through this route.
    page.route(
        f"**/api/connector-accounts/{account_id}/attached-agents",
        lambda r: r.fulfill(
            status=200,
            content_type="application/json",
            body='[{"name":"mock-agent","peers":["alice"],"channels":["general"]}]',
        ),
    )

    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-account-btn"]')).to_be_visible(
        timeout=8000
    )

    # Wait for the attached-agents table to render (the fetch resolves
    # asynchronously after mount). The General tab is default, so the
    # attached-agents section is already visible.
    expect(
        page.locator(
            '[data-testid="connector-attached-agents-table"]'
        )
    ).to_be_visible(timeout=8000)

    # Read the <th> cells in document order.
    header_cells = page.locator(
        '[data-testid="connector-attached-agents-table"] thead th'
    ).evaluate_all("els => els.map(e => e.textContent.trim())")
    assert header_cells == ["Agent", "Users", "Channels"], (
        f"Discord attached-agents headers drifted; got: {header_cells!r}"
    )


@pytest.mark.browser
def test_discord_routing_scope_dropdown_substitutes_peer_textcontent(
    app_clean: str, page: Page
) -> None:
    """Discord-type account: the routing-rules scope dropdown's
    ``<option value="peer">`` renders textContent "user" — the
    persisted ``value`` attribute STAYS at ``peer`` (substrate
    vocabulary preserved at the wire layer)."""
    # Seed a Discord account with a pre-existing routing rule so the
    # scope dropdown renders an <option> for each valid scope. The
    # L2 validator requires both ``rules`` and ``default`` keys when
    # ``routing`` is present.
    account_id = seed_connector_account(
        app_clean,
        name="Routing Discord",
        type="discord",
        config={
            "routing": {
                "rules": [
                    {"scope": "peer", "match": ["alice"], "agent": "general"}
                ],
                "default": None,
            }
        },
        secrets={"BOT_TOKEN": "plaintext"},
    )
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-account-btn"]')).to_be_visible(
        timeout=8000
    )
    page.locator('[data-testid="tab-access-and-routing"]').click()

    # Read the textContent of every option whose value is "peer".
    peer_option_texts = page.locator(
        '[data-routing-scope] option[value="peer"]'
    ).evaluate_all("els => els.map(e => e.textContent.trim())")
    assert len(peer_option_texts) >= 1, (
        "expected at least one routing-scope <option value='peer'> on the editor"
    )
    for text in peer_option_texts:
        assert text == "user", (
            f"expected substituted 'user' textContent for value='peer'; got: {text!r}"
        )

    # The <option value> attribute MUST stay at the substrate literal.
    peer_values = page.locator(
        '[data-routing-scope] option[value="peer"]'
    ).evaluate_all("els => els.map(e => e.value)")
    for val in peer_values:
        assert val == "peer", f"persistence vocabulary drift; got value={val!r}"

    # Channel option: textContent should be "channel" (substituted via
    # vocab.channel — which happens to equal the literal 'channel' for
    # Discord, but the substitution still flows through).
    channel_texts = page.locator(
        '[data-routing-scope] option[value="channel"]'
    ).evaluate_all("els => els.map(e => e.textContent.trim())")
    for text in channel_texts:
        assert text == "channel", (
            f"expected 'channel' textContent for value='channel'; got: {text!r}"
        )


@pytest.mark.browser
def test_stub_account_preserves_baseline_allowlist_labels(
    app_clean: str, page: Page
) -> None:
    """Regression: a ``'stub'``-type account still renders the pre-L6
    baseline labels "Peers" / "Channels" / "Guilds" / "Roles" — the
    generic-fallback path of ``connectorVocabulary.get('stub')`` (no
    entry registered → default vocab)."""
    account_id = seed_connector_account(app_clean, name="Vocab Stub", type="stub")
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-account-btn"]')).to_be_visible(
        timeout=8000
    )
    page.locator('[data-testid="tab-access-and-routing"]').click()

    # The pre-L6 baseline labels remain on a generic-tone account.
    allowlist_labels = page.locator(
        '.connector-allowlist-section .connector-account-acl-fieldlabel'
    ).evaluate_all("els => els.map(e => e.textContent.trim())")
    assert allowlist_labels == ["Peers", "Channels", "Guilds", "Roles"], (
        f"stub-account allowlist baseline drifted; got: {allowlist_labels!r}"
    )

    # The "Discord-flavored" qualifier appears in the hints (generic
    # tone keeps it).
    guilds_hint = page.locator('[data-testid="connector-allowlist-guilds-hint"]')
    guilds_text = guilds_hint.text_content() or ""
    assert "Discord-flavored" in guilds_text, (
        f"generic-tone account should retain the 'Discord-flavored' qualifier; "
        f"got: {guilds_text!r}"
    )


@pytest.mark.browser
def test_discord_account_save_roundtrip_preserves_substrate_field_names(
    app_clean: str, page: Page
) -> None:
    """Save round-trip on a Discord account: the persisted config
    keeps the substrate's literal field names ``peers`` / ``channels``
    / ``guilds`` / ``roles`` (NOT ``users`` / ``servers``). The
    display-text substitution does not leak into the wire layer."""
    account_id = seed_connector_account(
        app_clean,
        name="Wire Discord",
        type="discord",
        config={
            "allowlist": {
                "peers": ["alice", "bob"],
                "channels": ["general"],
                "guilds": ["111"],
                "roles": ["mod"],
            }
        },
        secrets={"BOT_TOKEN": "plaintext"},
    )

    # Direct GET to confirm the seeded shape persisted unchanged.
    before = _get_account(app_clean, account_id)
    assert "peers" in before["config"]["allowlist"]
    assert "channels" in before["config"]["allowlist"]
    assert "guilds" in before["config"]["allowlist"]
    assert "roles" in before["config"]["allowlist"]
    assert before["config"]["allowlist"]["peers"] == ["alice", "bob"]
    assert before["config"]["allowlist"]["guilds"] == ["111"]
    # Substituted display vocabulary keys MUST NOT appear at the wire
    # layer.
    assert "users" not in before["config"]["allowlist"]
    assert "servers" not in before["config"]["allowlist"]

    # Round-trip via the UI: open the editor, mark dirty (rename), and
    # save. The substrate field names must survive.
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-account-btn"]')).to_be_visible(
        timeout=8000
    )
    page.locator('[data-testid="connector-account-name-input"]').fill(
        "Wire Discord Renamed"
    )
    page.locator('[data-testid="save-connector-account-btn"]').click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)

    after = _get_account(app_clean, account_id)
    assert after["name"] == "Wire Discord Renamed"
    assert after["config"]["allowlist"]["peers"] == ["alice", "bob"], (
        f"peers field-name drifted at save round-trip; got: "
        f"{after['config']['allowlist']!r}"
    )
    assert after["config"]["allowlist"]["channels"] == ["general"]
    assert after["config"]["allowlist"]["guilds"] == ["111"]
    assert after["config"]["allowlist"]["roles"] == ["mod"]
    assert "users" not in after["config"]["allowlist"]
    assert "servers" not in after["config"]["allowlist"]
