"""Studio Connector Directive-section browser tests (M11 F2 L4).

Covers the Discord registry entry's ``renderDirectiveSection`` hook,
the substrate's directive-section mount between Pairing and Attached
Agents, the verbatim-Python-text invariant, the auto-relay reactive
annotation, the ``collect``/``snapshot``/round-trip wiring, plus the
two bundled F1-debrief polish items: lifted
``window.App.studio.MASKED_SENTINEL`` constant and ``data-account-id``
attribute on the editor mount node (replacing the prior
``window.location.hash`` parse in
``connector-form-discord.js:_resolveAccountFromContainer``).

Modelled on ``tests/browser/test_flow_studio_connector_invite_section.py``
(registry-mediated section + Playwright probe pattern).
"""

from __future__ import annotations

import httpx
import pytest
from browser.seeders import seed_connector_account
from playwright.sync_api import Page, expect

# Verbatim Python constants — the JS-side disclosure ``<code>`` text
# must equal these byte-for-byte. A future flight that edits the
# Python constants MUST update the JS twins in the same diff (per
# L4's atomic-leg pattern); this test catches drift on the spot.
from the_one.agent.config import (
    _CONNECTOR_AUTO_RELAY_DIRECTIVE,
    _CONNECTOR_TOOL_DISABLED_DIRECTIVE,
    _CONNECTOR_TOOL_ENABLED_DIRECTIVE,
)


def _get_account(base_url: str, account_id: str) -> dict:
    r = httpx.get(f"{base_url}/api/connector-accounts/{account_id}", timeout=5.0)
    assert r.status_code == 200, f"get failed: {r.status_code} {r.text}"
    return r.json()


def _seed_discord(base_url: str, *, name: str = "Directive Bot", **kwargs) -> str:
    """Seed a ``type='discord'`` account with a default BOT_TOKEN."""
    secrets = kwargs.pop("secrets", {"BOT_TOKEN": "plaintext"})
    config = kwargs.pop("config", {})
    return seed_connector_account(
        base_url,
        type="discord",
        name=name,
        config=config,
        secrets=secrets,
    )


# ── Tests ────────────────────────────────────────────────────────────────


@pytest.mark.browser
def test_directive_section_renders_on_discord_general_tab(
    app_clean: str, page: Page
) -> None:
    """Edit-mode mounts the System Prompt Directive section on the
    General tab. The section sits between Pairing and Attached Agents.
    """
    account_id = _seed_discord(app_clean, name="General Tab Bot")
    page.goto(f"{app_clean}#studio/connectors/{account_id}")

    section = page.locator('[data-testid="connector-account-directive-section"]')
    expect(section).to_be_visible(timeout=8000)

    # Section ordering: the directive section's index in the General
    # tab's children must be > pairing section and < attached-agents
    # section. We probe via evaluate to read the DOM order.
    panel = page.locator('#connector-tab-panel-general')
    order = panel.evaluate(
        """(panelEl) => {
            const ids = [];
            for (const child of panelEl.children) {
                const testid = child.getAttribute('data-testid')
                    || (child.querySelector('[data-testid]') &&
                        child.querySelector('[data-testid]').getAttribute('data-testid'))
                    || child.className;
                ids.push(testid);
            }
            return ids;
        }"""
    )
    # The directive section node has its own data-testid attribute.
    # The pairing section uses a class-based identifier in the parent
    # editor-section; we look for substring matches per the helper above.
    directive_idx = next(
        (i for i, t in enumerate(order) if t == "connector-account-directive-section"),
        -1,
    )
    pairing_idx = next(
        (i for i, t in enumerate(order) if t and "pairing" in str(t).lower()),
        -1,
    )
    attached_idx = next(
        (i for i, t in enumerate(order) if t and "attached" in str(t).lower()),
        -1,
    )
    assert directive_idx >= 0, f"directive section not in General tab: {order!r}"
    if pairing_idx >= 0:
        assert pairing_idx < directive_idx, (
            f"directive must follow pairing in DOM order; got {order!r}"
        )
    if attached_idx >= 0:
        assert directive_idx < attached_idx, (
            f"directive must precede attached-agents in DOM order; got {order!r}"
        )


@pytest.mark.browser
def test_directive_textarea_renders_with_persisted_value(
    app_clean: str, page: Page
) -> None:
    """Seed an account with a non-empty ``config.system_prompt_directive``;
    the textarea pre-fills with the persisted value on edit-mode mount."""
    persisted = "Sign replies with a coffee emoji."
    account_id = _seed_discord(
        app_clean,
        name="Persisted Directive Bot",
        config={"system_prompt_directive": persisted},
    )
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-account-btn"]')).to_be_visible(
        timeout=8000
    )

    textarea = page.locator(
        '[data-testid="connector-account-system-prompt-directive"]'
    )
    expect(textarea).to_have_value(persisted)


@pytest.mark.browser
def test_three_default_disclosures_render_verbatim_python_text(
    app_clean: str, page: Page
) -> None:
    """Each of the three ``<details>`` disclosures renders its
    ``<pre><code>`` block with text byte-equal to the corresponding
    Python constant in ``the_one/agent/config.py``. Pins the
    JS-twin-of-Python-constant invariant."""
    account_id = _seed_discord(app_clean, name="Verbatim Bot")
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(
        page.locator('[data-testid="connector-account-directive-section"]')
    ).to_be_visible(timeout=8000)

    on_text = page.locator(
        '[data-testid="directive-default-auto-relay-on-text"]'
    ).text_content()
    off_text = page.locator(
        '[data-testid="directive-default-auto-relay-off-text"]'
    ).text_content()
    disabled_text = page.locator(
        '[data-testid="directive-default-tool-disabled-text"]'
    ).text_content()

    assert on_text == _CONNECTOR_AUTO_RELAY_DIRECTIVE, (
        "auto-relay-on disclosure drifted from Python constant "
        "_CONNECTOR_AUTO_RELAY_DIRECTIVE"
    )
    assert off_text == _CONNECTOR_TOOL_ENABLED_DIRECTIVE, (
        "auto-relay-off disclosure drifted from Python constant "
        "_CONNECTOR_TOOL_ENABLED_DIRECTIVE"
    )
    assert disabled_text == _CONNECTOR_TOOL_DISABLED_DIRECTIVE, (
        "tool-disabled disclosure drifted from Python constant "
        "_CONNECTOR_TOOL_DISABLED_DIRECTIVE"
    )


@pytest.mark.browser
def test_current_state_annotation_on_auto_relay_on_disclosure(
    app_clean: str, page: Page
) -> None:
    """A default account (auto-relay absent → True at consume time)
    shows the ``(this account's current)`` annotation on the
    auto-relay-ON disclosure summary."""
    account_id = _seed_discord(app_clean, name="Default Auto-Relay Bot")
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(
        page.locator('[data-testid="connector-account-directive-section"]')
    ).to_be_visible(timeout=8000)

    on_summary = page.locator(
        '[data-testid="directive-default-auto-relay-on-summary"]'
    )
    off_summary = page.locator(
        '[data-testid="directive-default-auto-relay-off-summary"]'
    )
    disabled_summary = page.locator(
        '[data-testid="directive-default-tool-disabled-summary"]'
    )

    expect(on_summary).to_contain_text("(this account's current)")
    # The off-summary must NOT carry the annotation in the default state.
    off_text = off_summary.text_content() or ""
    assert "(this account's current)" not in off_text, (
        f"off-summary unexpectedly carries annotation: {off_text!r}"
    )
    # Tool-disabled never carries the annotation from the account editor.
    disabled_text = disabled_summary.text_content() or ""
    assert "(this account's current)" not in disabled_text, (
        f"tool-disabled summary unexpectedly carries annotation: {disabled_text!r}"
    )


@pytest.mark.browser
def test_current_state_annotation_moves_on_auto_relay_toggle(
    app_clean: str, page: Page
) -> None:
    """Unchecking the auto-relay checkbox in the editor moves the
    ``(this account's current)`` annotation onto the auto-relay-OFF
    disclosure live (no save required). Re-checking moves it back."""
    account_id = _seed_discord(app_clean, name="Toggle Bot")
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(
        page.locator('[data-testid="connector-account-directive-section"]')
    ).to_be_visible(timeout=8000)

    on_summary = page.locator(
        '[data-testid="directive-default-auto-relay-on-summary"]'
    )
    off_summary = page.locator(
        '[data-testid="directive-default-auto-relay-off-summary"]'
    )
    auto_relay_cb = page.locator(
        '[data-testid="connector-account-auto-relay-toggle"]'
    )

    # Initial state — annotation on ON.
    expect(on_summary).to_contain_text("(this account's current)")

    # The auto-relay checkbox lives on the Access and Routing tab in
    # edit mode (Lifecycle section). Switch to that tab so click()
    # resolves an interactable target.
    routing_tab = page.locator('[data-testid="tab-access-and-routing"]')
    if routing_tab.count() > 0:
        routing_tab.click()

    auto_relay_cb.click()  # uncheck
    page.wait_for_timeout(50)

    # Annotation moves onto OFF; ON loses it.
    expect(off_summary).to_contain_text("(this account's current)")
    on_text = on_summary.text_content() or ""
    assert "(this account's current)" not in on_text, (
        f"on-summary still carries annotation after toggle: {on_text!r}"
    )

    auto_relay_cb.click()  # re-check
    page.wait_for_timeout(50)

    expect(on_summary).to_contain_text("(this account's current)")
    off_text = off_summary.text_content() or ""
    assert "(this account's current)" not in off_text, (
        f"off-summary still carries annotation after re-toggle: {off_text!r}"
    )


@pytest.mark.browser
def test_directive_save_round_trip_emits_config_key(
    app_clean: str, page: Page
) -> None:
    """Type a directive → save → GET account → confirm the persisted
    ``config.system_prompt_directive`` equals the typed value (trimmed)."""
    account_id = _seed_discord(app_clean, name="Roundtrip Bot")
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-account-btn"]')).to_be_visible(
        timeout=8000
    )

    textarea = page.locator(
        '[data-testid="connector-account-system-prompt-directive"]'
    )
    textarea.fill("Reply formally.")

    save_btn = page.locator('[data-testid="save-connector-account-btn"]')
    expect(save_btn).not_to_be_disabled()
    save_btn.click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)

    after = _get_account(app_clean, account_id)
    assert after["config"].get("system_prompt_directive") == "Reply formally.", (
        f"directive did not persist; config={after['config']!r}"
    )


@pytest.mark.browser
def test_directive_save_omits_key_when_empty(app_clean: str, page: Page) -> None:
    """Leave the textarea empty → save → GET account → confirm
    ``system_prompt_directive`` is NOT in the persisted config (no
    empty-string noise; L3 validator rejects empty strings)."""
    account_id = _seed_discord(app_clean, name="Empty Directive Bot")
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-account-btn"]')).to_be_visible(
        timeout=8000
    )

    # Touch the name to enable the Save button without putting any
    # directive text in the textarea.
    page.locator('[data-testid="connector-account-name-input"]').fill(
        "Empty Directive Bot Renamed"
    )
    save_btn = page.locator('[data-testid="save-connector-account-btn"]')
    expect(save_btn).not_to_be_disabled()
    save_btn.click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)

    after = _get_account(app_clean, account_id)
    assert "system_prompt_directive" not in after["config"], (
        f"empty directive leaked into config; config={after['config']!r}"
    )


@pytest.mark.browser
def test_directive_section_absent_on_stub_account(
    app_clean: str, page: Page
) -> None:
    """Stub-type accounts have no registry entry providing
    ``renderDirectiveSection`` → the substrate renders no HTML for that
    section → the section node is absent entirely."""
    account_id = seed_connector_account(app_clean, name="Stub Directive Bot")
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="connector-test-connection-btn"]')).to_be_visible(
        timeout=8000
    )

    section = page.locator('[data-testid="connector-account-directive-section"]')
    expect(section).to_have_count(0)


@pytest.mark.browser
def test_directive_key_hidden_from_advanced_kv_table(
    app_clean: str, page: Page
) -> None:
    """A Discord account whose config carries
    ``system_prompt_directive`` does NOT render that key as a row in
    the Advanced kv-table (reserved-config-keys composition)."""
    account_id = _seed_discord(
        app_clean,
        name="Hidden Key Bot",
        config={
            "system_prompt_directive": "Sign with a kettle.",
            "extra_key": "extra_value",
        },
    )
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-account-btn"]')).to_be_visible(
        timeout=8000
    )

    expect(
        page.locator('[data-testid="discord-advanced-kv-disclosure"]')
    ).to_be_attached()

    key_inputs = page.locator(
        ".connector-account-config-row .config-key-input"
    )
    keys = key_inputs.evaluate_all("els => els.map(e => e.value)")
    assert "system_prompt_directive" not in keys, (
        f"system_prompt_directive leaked into Advanced kv-table; keys={keys!r}"
    )
    assert "extra_key" in keys, (
        f"extra_key missing from kv-table; keys={keys!r}"
    )


@pytest.mark.browser
def test_data_account_id_attribute_set_in_edit_mode(
    app_clean: str, page: Page
) -> None:
    """In edit mode, the ``.connector-account-editor`` root carries a
    ``data-account-id`` attribute equal to the seeded ``account.id``.
    This is the replacement for the prior ``window.location.hash``
    parse in ``_resolveAccountFromContainer``."""
    account_id = _seed_discord(app_clean, name="Attr Bot")
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-account-btn"]')).to_be_visible(
        timeout=8000
    )

    editor = page.locator(".connector-account-editor")
    expect(editor).to_have_attribute("data-account-id", account_id)


@pytest.mark.browser
def test_data_account_id_attribute_absent_in_create_mode(
    app_clean: str, page: Page
) -> None:
    """In create mode, the ``.connector-account-editor`` root has NO
    ``data-account-id`` attribute (no ``account.id`` exists yet — the
    F1 L7 type-pick re-mount uses a stub that also has no id)."""
    page.goto(f"{app_clean}#studio/connectors/new")
    expect(
        page.locator('[data-testid="create-and-test-connector-account-btn"]')
    ).to_be_visible(timeout=8000)

    editor = page.locator(".connector-account-editor")
    has_attr = editor.evaluate("(el) => el.hasAttribute('data-account-id')")
    assert has_attr is False, (
        "create-mode editor unexpectedly carries data-account-id; "
        "must be absent until an id exists"
    )


@pytest.mark.browser
def test_masked_sentinel_global_constant(app_clean: str, page: Page) -> None:
    """``window.App.studio.MASKED_SENTINEL`` equals ``'__MASKED__'`` and
    is set by the studio's earliest-loading module
    (``connector-form-registry.js``)."""
    page.goto(f"{app_clean}#studio/connectors")
    # Wait for the studio area to load — the registry module is
    # parsed by the time any studio page paints.
    page.wait_for_load_state("networkidle")

    sentinel = page.evaluate(
        "() => (window.App && window.App.studio && window.App.studio.MASKED_SENTINEL) || null"
    )
    assert sentinel == "__MASKED__", (
        f"window.App.studio.MASKED_SENTINEL not set to '__MASKED__'; got {sentinel!r}"
    )


@pytest.mark.browser
def test_create_mode_type_pick_does_not_crash_with_directive(
    app_clean: str, page: Page
) -> None:
    """Create form → pick Discord → form re-mounts. The directive
    section is registry-mediated but edit-mode-only; create mode
    consult returns no section → no exception. Auto-relay toggle (if
    any) does not throw because ``_updateDirectiveAnnotation``'s
    null-guards no-op when summaries don't exist
    (registry-dispatch-create-mode-AC application)."""
    # Capture page errors so we fail loudly on any exception.
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))

    page.goto(f"{app_clean}#studio/connectors/new")
    expect(
        page.locator('[data-testid="create-and-test-connector-account-btn"]')
    ).to_be_visible(timeout=8000)

    # Pick Discord — triggers create-mode type-change re-render.
    page.locator('[data-testid="connector-account-type-select"]').select_option(
        "discord"
    )

    # The typed Discord fields appear.
    expect(page.locator('[data-testid="discord-intents-fieldset"]')).to_be_visible(
        timeout=4000
    )

    # Directive section is NOT mounted in create mode.
    expect(
        page.locator('[data-testid="connector-account-directive-section"]')
    ).to_have_count(0)

    # No page errors during the re-mount.
    assert errors == [], (
        f"page errors during create-mode Discord pick: {errors!r}"
    )
