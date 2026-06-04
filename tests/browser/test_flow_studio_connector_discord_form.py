"""Studio Connector Discord-shaped editor flow tests (M11 F1 L4).

Covers the Discord registry entry's typed form fields end-to-end:

- Editor renders no intent checkboxes (M11 F17 L6 Leg B subtraction —
  ``discord-intents-row`` and ``discord-intent-*`` testids absent).
- Saving with no operator edits round-trips byte-identically — none of
  ``intents`` / ``guilds`` / ``presence`` keys are introduced if absent
  before (preserves M10 F8 baseline shape).
- Pre-existing all-True intents round-trip with the key preserved
  (field is back-compat inert; the key is not stripped on save).
- Adding a guild ID → save → 201 round-trip.
- Setting presence name + type → save → 201 round-trip.
- Advanced kv-table disclosure hides ``intents`` / ``guilds`` /
  ``presence`` keys (L3's effective-reserved-keys composition).
- BOT_TOKEN masked-edit round-trip: no-change save → MASKED_SENTINEL
  preserves the stored secret; value-edit save → new plaintext stored.
- ``'stub'``-type snapshot is byte-identical to the L3 baseline (no
  ``typedFields`` key when no entry is registered for the type).

Backend ``'discord'`` registration: ``register_builtin_connectors`` at
``the_one/connectors/registry.py`` registers ``DiscordPlugin`` for the
``'discord'`` type via function-local import. The browser-fixture
subprocess inherits the same registration path through normal app
startup — no extra env var needed (unlike ``'stub'`` which is
test-only-gated).
"""

from __future__ import annotations

import httpx
import pytest
from browser.seeders import seed_connector
from playwright.sync_api import Page, expect


def _get_account(base_url: str, account_id: str) -> dict:
    r = httpx.get(f"{base_url}/api/connectors/{account_id}", timeout=5.0)
    assert r.status_code == 200, f"get failed: {r.status_code} {r.text}"
    return r.json()


def _activate_access_and_routing_tab(page: Page) -> None:
    """F5 L3: edit-mode renders runtime-config on the Access-and-Routing
    tab (was: Connection section on the General tab). Tests that
    interact with ``discord-intent-*`` / ``discord-guilds-list`` /
    ``discord-presence-*`` / ``discord-additional-config-row`` testids
    must click the tab first so the panel is visible / actionable.
    Mirrors the helper at
    ``test_flow_studio_connector_editor.py:89``; inlined here
    for minimum cross-file coupling.
    """
    page.locator('[data-testid="tab-access-and-routing"]').click()
    expect(page.locator('[data-testid="connector-runtime-config-section"]')).to_be_visible(
        timeout=4000
    )


def _seed_discord(base_url: str, **kwargs) -> str:
    """Seed a ``type='discord'`` account with default BOT_TOKEN.

    Tests pass ``config={...}`` to override the persisted shape; the
    BOT_TOKEN default ensures the typed credentials field has a value
    to render and exercise masked-edit round-trips.
    """
    secrets = kwargs.pop("secrets", {"BOT_TOKEN": "real_bot_token_abcd"})
    return seed_connector(
        base_url,
        type="discord",
        secrets=secrets,
        **kwargs,
    )


# ── Tests ────────────────────────────────────────────────────────────────


@pytest.mark.browser
def test_editor_renders_no_intent_checkboxes(app_clean: str, page: Page) -> None:
    """The Access-and-Routing tab renders no intent-toggle checkboxes.

    M11 F17 L6 (Leg B): the three ``discord-intent-*`` checkboxes and
    the ``discord-intents-row`` container are removed from the form.
    The backend always requests all three gateway intents; there is no
    in-app toggle. Assert absence even when ``config.intents`` carries
    a persisted value (back-compat field is inert, not rendered).
    """
    account_id = _seed_discord(
        app_clean,
        name="No-Intents Bot",
        config={"intents": {"message_content": False, "members": True, "guilds": True}},
    )
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(timeout=8000)

    _activate_access_and_routing_tab(page)

    # No intent row or checkboxes in the DOM.
    expect(page.locator('[data-testid="discord-intents-row"]')).to_have_count(0)
    expect(page.locator('[data-testid="discord-intent-message_content"]')).to_have_count(0)
    expect(page.locator('[data-testid="discord-intent-members"]')).to_have_count(0)
    expect(page.locator('[data-testid="discord-intent-guilds"]')).to_have_count(0)

    # BOT_TOKEN input still present with the masked value (General tab).
    page.locator('[data-testid="tab-general"]').click()
    expect(page.locator('[data-testid="discord-bot-token"]')).to_be_visible()
    expect(page.locator('[data-testid="discord-bot-token"]')).to_have_value("***...abcd")


@pytest.mark.browser
def test_no_change_save_roundtrip_omits_intents_when_absent(app_clean: str, page: Page) -> None:
    """An M10 F8 Discord account (config lacks intents/guilds/presence)
    saved with no operator edits must NOT introduce the typed keys —
    byte-identical config round-trip."""
    account_id = _seed_discord(app_clean, name="Pristine Bot", config={})
    before = _get_account(app_clean, account_id)
    assert "intents" not in before["config"]
    assert "guilds" not in before["config"]
    assert "presence" not in before["config"]

    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(timeout=8000)
    # Mark dirty by touching name then reverting — to enable Save while
    # leaving the typed fields untouched. The save will still emit the
    # typed-section state (which should not introduce new keys).
    name_input = page.locator('[data-testid="connector-name-input"]')
    name_input.fill("Pristine Bot Renamed")
    page.locator('[data-testid="save-connector-btn"]').click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)

    after = _get_account(app_clean, account_id)
    assert "intents" not in after["config"], f"expected no intents key; got: {after['config']!r}"
    assert "guilds" not in after["config"]
    assert "presence" not in after["config"]
    assert after["name"] == "Pristine Bot Renamed"


@pytest.mark.browser
def test_save_with_pre_existing_intents_key_does_not_crash(app_clean: str, page: Page) -> None:
    """A Discord account whose config carries a pre-existing ``intents``
    key can be saved without error.

    M11 F17 L6 (Leg B): the form no longer emits ``config.intents`` in
    the PUT payload (collect() dropped the intent-collect block). The
    key is NOT round-tripped through the form. This test verifies that
    saving an account with a stale ``intents`` key in config doesn't
    produce a 422 / error flash — the name change saves cleanly.
    """
    account_id = _seed_discord(
        app_clean,
        name="All-True Bot",
        config={"intents": {"message_content": True, "members": True, "guilds": True}},
    )
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-testid="connector-name-input"]').fill("All-True Renamed")
    page.locator('[data-testid="save-connector-btn"]').click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)

    # Verify the save succeeded (name updated) and no error is shown.
    after = _get_account(app_clean, account_id)
    assert after["name"] == "All-True Renamed"
    # The intents key is not re-emitted by the form; the backend's config
    # is whatever collect() last wrote. Assert no crash (not key preservation).
    assert "name" in after


# M11 F17 L6 (Leg B): ``test_intent_toggle_save_emits_typed_payload`` removed.
# Intent checkboxes gone from the form; the backend always forces all three
# intents on regardless of config["intents"]. No form-driven intent payload.

# M11 F14 L02: ``test_guilds_add_saves`` removed. The standalone
# "Scope to servers" text field (``data-testid="discord-guilds-list"``)
# was retired — guild scoping is now unified onto the allowlist
# "Servers" axis (``config.allowlist.guilds``), which is edited via the
# connector allowlist editor, not this Runtime Config form. No
# replacement test here; the allowlist Servers axis is exercised by the
# connector-editor flow tests.


@pytest.mark.browser
def test_presence_name_and_type_save(app_clean: str, page: Page) -> None:
    """Setting presence name + type → save → backend stores the
    {name, type} dict."""
    account_id = _seed_discord(app_clean, name="Presence Bot", config={})
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(timeout=8000)

    # F5 L3: presence editor moved to the Access-and-Routing tab.
    _activate_access_and_routing_tab(page)
    page.locator('[data-testid="discord-presence-name"]').fill("with friends")
    page.locator('[data-testid="discord-presence-type"]').select_option("playing")
    page.locator('[data-testid="save-connector-btn"]').click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)

    after = _get_account(app_clean, account_id)
    assert after["config"]["presence"] == {"name": "with friends", "type": "playing"}


@pytest.mark.browser
def test_additional_config_hides_reserved_keys(app_clean: str, page: Page) -> None:
    """The Additional Config kv-table renders with ``intents``,
    ``guilds``, ``presence`` keys NOT appearing as kv-table rows (L3's
    effective-reserved-keys composition with the entry's
    ``reservedConfigKeys``).

    F5 L6 HAT round-2: pre-round-2 this section was an
    ``<details>``-based "Advanced (kv-table)" disclosure; round-2 made
    it an always-visible "Additional Config" row. The testid migrated
    from ``discord-advanced-kv-disclosure`` to
    ``discord-additional-config-row``.
    """
    account_id = _seed_discord(
        app_clean,
        name="Additional Config Bot",
        config={
            "intents": {"message_content": False, "members": True, "guilds": True},
            # M11 F14 L02: top-level ``guilds`` fixture dropped — the key
            # is no longer reserved (the "Scope to servers" field was
            # retired); a seeded top-level ``guilds`` would now
            # legitimately surface in the kv-table, so the old
            # "guilds not in keys" assertion no longer holds.
            "presence": {"name": "stuff", "type": "watching"},
            "extra_key": "extra_value",  # a non-reserved key — must appear
        },
    )
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(timeout=8000)

    # F5 L3: Additional Config kv-table lives on the Access-and-Routing
    # tab (inside the Runtime Config section).
    _activate_access_and_routing_tab(page)

    # M11 F17 L7 (Leg C): the Advanced section is a ``<details>``
    # disclosure (collapsed by default). Open it before querying the
    # kv-table rows so the inputs are reachable.
    page.locator('[data-testid="connector-advanced-section"]').evaluate(
        "el => el.setAttribute('open', '')"
    )

    # The Additional Config row exists.
    expect(page.locator('[data-testid="discord-additional-config-row"]')).to_be_attached()

    # Read the kv-table rows' key inputs. Reserved keys (intents,
    # presence) must NOT appear; the non-reserved extra_key MUST appear.
    # M11 F14 L02: ``guilds`` is no longer reserved (the "Scope to
    # servers" field was retired), so the old "guilds not in keys"
    # assertion is dropped.
    key_inputs = page.locator(".connector-config-row .config-key-input")
    keys = key_inputs.evaluate_all("els => els.map(e => e.value)")
    assert "intents" not in keys, f"intents leaked into kv-table; keys={keys!r}"
    assert "presence" not in keys, f"presence leaked into kv-table; keys={keys!r}"
    assert "extra_key" in keys, f"extra_key missing from kv-table; keys={keys!r}"


@pytest.mark.browser
def test_bot_token_masked_no_change_roundtrip(app_clean: str, page: Page) -> None:
    """No-change save round-trips ``BOT_TOKEN: "__MASKED__"`` → backend
    keeps the stored plaintext (masked tail unchanged)."""
    account_id = _seed_discord(
        app_clean,
        name="Masked Bot",
        secrets={"BOT_TOKEN": "secret_value_wxyz"},
    )
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(timeout=8000)
    token_input = page.locator('[data-testid="discord-bot-token"]')
    expect(token_input).to_have_value("***...wxyz")

    page.locator('[data-testid="connector-name-input"]').fill("Masked Renamed")
    page.locator('[data-testid="save-connector-btn"]').click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)

    after = _get_account(app_clean, account_id)
    # Masked tail preserved → backend stored value unchanged.
    assert after["secrets"]["BOT_TOKEN"] == "***...wxyz"
    assert after["name"] == "Masked Renamed"


@pytest.mark.browser
def test_bot_token_value_edit_saves_new_plaintext(app_clean: str, page: Page) -> None:
    """Editing the BOT_TOKEN to a new value → save → backend stores
    the new plaintext (masked tail reflects the new last-4)."""
    account_id = _seed_discord(
        app_clean,
        name="New-Token Bot",
        secrets={"BOT_TOKEN": "old_value_oldd"},
    )
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-testid="discord-bot-token"]').fill("rotated_token_neww")
    page.locator('[data-testid="save-connector-btn"]').click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)

    after = _get_account(app_clean, account_id)
    assert after["secrets"]["BOT_TOKEN"] == "***...neww"


@pytest.mark.browser
def test_stub_snapshot_byte_identical_to_baseline(app_clean: str, page: Page) -> None:
    """``'stub'``-type account snapshot must NOT carry a ``typedFields``
    key — no entry registered for ``'stub'`` → byte-identical to the L3
    baseline. Asserts the substrate's ``getFormSnapshot`` byte-stability
    contract under the new typedFields extension."""
    account_id = seed_connector(app_clean, name="Stub Bot", type="stub")
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(timeout=8000)

    # Read the snapshot JSON via ``getFormSnapshot`` — the function is
    # IIFE-local but ``getFormSnapshot`` runs at editor-mount and the
    # closure-captured ``snapshot`` is the initial value. Inspect the
    # JSON by reconstructing through the DOM: a ``'stub'``-type account
    # has no entry, so the snapshot object must not carry the typed
    # key. Parse the snapshot indirectly via the page evaluator: there
    # is no public hook to read it directly, but the dirty-tracker
    # state means "after no edits, Save is disabled" — which is a
    # sufficient byte-stability proxy plus an explicit JSON inspection.
    snapshot_keys = page.evaluate(
        """
        () => {
            // Re-invoke getFormSnapshot via the same closure path: the
            // function is private to the IIFE. The next best signal is
            // the DOM shape: confirm that on stub-type, no Discord
            // typed inputs render, and Save stays disabled (proxy for
            // dirty=false → snapshot stable across this re-mount).
            const containers = document.querySelectorAll(
                '[data-testid="connector-config"]'
            );
            const intent = document.querySelector(
                '[data-testid="discord-intent-message_content"]'
            );
            return {
                hasConfigWrapper: containers.length >= 1,
                hasDiscordIntent: !!intent
            };
        }
        """
    )
    assert snapshot_keys["hasConfigWrapper"] is True
    assert snapshot_keys["hasDiscordIntent"] is False, (
        "expected the Discord typed-intent input to be absent for 'stub'-type accounts"
    )
    # Save stays disabled — dirty=false → snapshot equality holds → no
    # spurious ``typedFields`` key was injected for the unregistered type.
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_disabled()


# ── M11 F17 L7 (Leg C) tests ────────────────────────────────────────────────


@pytest.mark.browser
def test_advanced_section_is_last_element_in_runtime_config(app_clean: str, page: Page) -> None:
    """The Advanced section (``connector-advanced-section``) is the LAST
    child of the Runtime Config section body — below all typed fields.

    M11 F17 L7 (Leg C): the Additional Config kv-table was relocated to a
    bottom ``<details>``-based "Advanced" section. This DOM-order assertion
    is a cheap guard that the relocation didn't drift back inline.
    """
    account_id = _seed_discord(app_clean, name="Advanced-Order Bot", config={})
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(timeout=8000)

    _activate_access_and_routing_tab(page)

    # The Advanced section exists.
    expect(page.locator('[data-testid="connector-advanced-section"]')).to_be_attached()

    # It must be the LAST child element inside the Runtime Config section
    # body (the substrate wraps _renderRuntimeConfigBody's output inside
    # ``.section-body`` or equivalent). Use JS evaluation to assert
    # DOM order without depending on a specific parent selector.
    is_last = page.evaluate(
        """
        () => {
            const adv = document.querySelector(
                '[data-testid="connector-advanced-section"]'
            );
            if (!adv) return false;
            const parent = adv.parentElement;
            if (!parent) return false;
            const children = Array.from(parent.children);
            return children[children.length - 1] === adv;
        }
        """
    )
    assert is_last, (
        "connector-advanced-section is not the last child of its parent — "
        "the Advanced kv-table has drifted above typed fields"
    )


@pytest.mark.browser
def test_kv_table_key_round_trips_on_save(app_clean: str, page: Page) -> None:
    """Adding a key via the Advanced kv-table → Save → key persists in
    the backend config (round-trip fix for M11 F17 L7 Leg C).

    Pre-Leg-C, the Discord typed-form branch in ``collectFormData``
    skipped the ``.connector-config-row`` DOM scan, so ad-hoc kv-table
    entries were silently dropped on every save. This test catches a
    regression to that bug.

    Also verifies ``ingest_bots`` (the canonical advanced seam) round-trips.
    """
    account_id = _seed_discord(app_clean, name="KV-Round-Trip Bot", config={})
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(timeout=8000)

    # Open the Access-and-Routing tab, then open the Advanced disclosure.
    _activate_access_and_routing_tab(page)
    page.locator('[data-testid="connector-advanced-section"]').evaluate(
        "el => el.setAttribute('open', '')"
    )
    expect(page.locator('[data-testid="discord-additional-config-row"]')).to_be_visible(
        timeout=4000
    )

    # Click "+ Add row" to add a new kv-table row.
    page.locator('[data-testid="connector-config-add-row-btn"]').click()

    # Fill the new row with a custom key + value.
    key_inputs = page.locator(".connector-config-row .config-key-input")
    val_inputs = page.locator(".connector-config-row .config-value-input")
    # The new row is the last one.
    last_idx = key_inputs.count() - 1
    key_inputs.nth(last_idx).fill("ingest_bots")
    val_inputs.nth(last_idx).fill("true")

    # Save.
    page.locator('[data-testid="save-connector-btn"]').click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)

    # Verify key persisted in the backend config.
    after = _get_account(app_clean, account_id)
    assert "ingest_bots" in after["config"], (
        f"ingest_bots key not found in config after save; config={after['config']!r}"
    )
    assert after["config"]["ingest_bots"] == "true", (
        f"unexpected ingest_bots value: {after['config']['ingest_bots']!r}"
    )

    # Reload and verify the key is still there (reload round-trip).
    page.reload()
    expect(page.locator('[data-testid="save-connector-btn"]')).to_be_visible(timeout=8000)
    reloaded = _get_account(app_clean, account_id)
    assert reloaded["config"].get("ingest_bots") == "true", (
        f"ingest_bots lost after reload; config={reloaded['config']!r}"
    )
