"""Studio Connector effective-directive codeblock browser tests
(M11 F5 L6 HAT round-8 — replaces the M11 F2 L4 directive-section
test suite).

Mission M11 criterion #14 ("operator-editable system-prompt directive
per connector account") was REVERTED in F5 L6 HAT round-8. The
editable General-tab "System Prompt Directive" section was removed;
the three substrate-default directives were collapsed to two; and the
remaining surface is a read-only styled codeblock under the Auto-reply
toggle in the Session section (Access and Routing tab) that swaps
content reactively as the operator flips the Auto-reply switch.

These tests pin:
- the General-tab editable directive section is GONE
- the read-only codeblock is mounted in the Session section
- the codeblock content equals one of the two Python defaults
  (byte-equality with ``the_one/agent/config.py``)
- toggling Auto-reply swaps the codeblock content reactively
- ``data-account-id`` attribute on the editor mount node still
  resolves (carried over from L4-debrief polish)
- ``window.App.studio.MASKED_SENTINEL`` constant still resolves
  (carried over from L4-debrief polish)
"""

from __future__ import annotations

import pytest
from browser.seeders import seed_connector_account
from playwright.sync_api import Page, expect

# The two surviving substrate-default directives. The JS twins in
# ``connector-account-editor.js`` MUST equal these byte-for-byte; any
# drift fails ``test_codeblock_content_matches_python_default``.
from the_one.agent.config import (
    _CONNECTOR_AUTO_RELAY_DIRECTIVE,
    _CONNECTOR_AUTO_RELAY_OFF_DIRECTIVE,
)


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
def test_editable_directive_section_removed_from_general_tab(
    app_clean: str, page: Page
) -> None:
    """The pre-round-8 editable System Prompt Directive section is no
    longer mounted anywhere — neither the section wrapper nor its
    textarea field render."""
    account_id = _seed_discord(app_clean, name="No Directive Section Bot")
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-account-btn"]')).to_be_visible(
        timeout=8000
    )

    # Section wrapper absent.
    expect(
        page.locator('[data-testid="connector-account-directive-section"]')
    ).to_have_count(0)
    # Textarea absent.
    expect(
        page.locator('[data-testid="connector-account-system-prompt-directive"]')
    ).to_have_count(0)
    # Old three-disclosure summaries absent.
    expect(
        page.locator('[data-testid="directive-default-auto-relay-on-summary"]')
    ).to_have_count(0)
    expect(
        page.locator('[data-testid="directive-default-auto-relay-off-summary"]')
    ).to_have_count(0)
    expect(
        page.locator('[data-testid="directive-default-tool-disabled-summary"]')
    ).to_have_count(0)


@pytest.mark.browser
def test_effective_directive_codeblock_renders_in_session_section(
    app_clean: str, page: Page
) -> None:
    """The read-only codeblock mounts inside the Session section (which
    lives on the Access and Routing tab in edit mode)."""
    account_id = _seed_discord(app_clean, name="Codeblock Bot")
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-account-btn"]')).to_be_visible(
        timeout=8000
    )

    # Hop to the Access and Routing tab where the Session section lives.
    routing_tab = page.locator('[data-testid="tab-access-and-routing"]')
    if routing_tab.count() > 0:
        routing_tab.click()

    codeblock = page.locator(
        '[data-testid="connector-account-effective-directive-codeblock"]'
    )
    expect(codeblock).to_be_visible(timeout=4000)

    # Sanity: the codeblock sits AFTER the Auto-reply toggle row in DOM
    # order (the toggle's reactive listener feeds the codeblock).
    panel = page.locator('#connector-tab-panel-access-and-routing')
    auto_relay_pos = panel.evaluate(
        """(panelEl) => {
            const toggle = panelEl.querySelector(
              '[data-testid="connector-account-auto-relay-toggle"]'
            );
            const block = panelEl.querySelector(
              '[data-testid="connector-account-effective-directive-codeblock"]'
            );
            if (!toggle || !block) return null;
            const rel = toggle.compareDocumentPosition(block);
            return (rel & Node.DOCUMENT_POSITION_FOLLOWING) ? 'follows' : 'precedes';
        }"""
    )
    assert auto_relay_pos == "follows", (
        f"effective-directive codeblock must FOLLOW the Auto-reply toggle "
        f"in DOM order; got {auto_relay_pos!r}"
    )


@pytest.mark.browser
def test_codeblock_content_matches_auto_relay_on_default(
    app_clean: str, page: Page
) -> None:
    """A default account (auto-relay absent → True at consume time)
    renders the AUTO_RELAY (ON) directive verbatim inside the codeblock.
    Pins the JS-twin-of-Python-constant invariant for the ON branch."""
    account_id = _seed_discord(app_clean, name="Auto-Relay On Bot")
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-account-btn"]')).to_be_visible(
        timeout=8000
    )

    routing_tab = page.locator('[data-testid="tab-access-and-routing"]')
    if routing_tab.count() > 0:
        routing_tab.click()

    text = page.locator(
        '[data-testid="connector-account-effective-directive-text"]'
    ).text_content()
    assert text == _CONNECTOR_AUTO_RELAY_DIRECTIVE, (
        "ON-state codeblock drifted from Python constant "
        "_CONNECTOR_AUTO_RELAY_DIRECTIVE"
    )


@pytest.mark.browser
def test_codeblock_content_swaps_on_auto_relay_toggle(
    app_clean: str, page: Page
) -> None:
    """Unchecking the Auto-reply switch swaps the codeblock content from
    the ON directive to the OFF directive live (no save required).
    Re-checking swaps it back."""
    account_id = _seed_discord(app_clean, name="Toggle Codeblock Bot")
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="save-connector-account-btn"]')).to_be_visible(
        timeout=8000
    )

    routing_tab = page.locator('[data-testid="tab-access-and-routing"]')
    if routing_tab.count() > 0:
        routing_tab.click()

    code = page.locator(
        '[data-testid="connector-account-effective-directive-text"]'
    )
    toggle = page.locator(
        '[data-testid="connector-account-auto-relay-toggle"]'
    )

    # Initial: ON directive.
    assert (code.text_content() or "") == _CONNECTOR_AUTO_RELAY_DIRECTIVE

    # Flip OFF.
    toggle.click()
    page.wait_for_timeout(50)
    assert (code.text_content() or "") == _CONNECTOR_AUTO_RELAY_OFF_DIRECTIVE

    # Flip back ON.
    toggle.click()
    page.wait_for_timeout(50)
    assert (code.text_content() or "") == _CONNECTOR_AUTO_RELAY_DIRECTIVE


@pytest.mark.browser
def test_codeblock_absent_in_create_mode(app_clean: str, page: Page) -> None:
    """Create mode (no persisted account yet) does NOT render the
    effective-directive codeblock — there is no account state to
    preview against, and the Session section's flat-create layout
    doesn't include the codeblock row."""
    page.goto(f"{app_clean}#studio/connectors/new")
    expect(
        page.locator('[data-testid="create-and-test-connector-account-btn"]')
    ).to_be_visible(timeout=8000)
    expect(
        page.locator(
            '[data-testid="connector-account-effective-directive-codeblock"]'
        )
    ).to_have_count(0)


@pytest.mark.browser
def test_codeblock_absent_on_stub_account(app_clean: str, page: Page) -> None:
    """Stub-type accounts also get the read-only codeblock — the
    Session section is type-agnostic (Auto-reply toggle + codeblock
    apply to any connector that opts into the Session row). Pinned
    here so a future stub-type change doesn't accidentally hide the
    Session preview."""
    account_id = seed_connector_account(app_clean, name="Stub Codeblock Bot")
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(
        page.locator('[data-testid="connector-test-connection-btn"]')
    ).to_be_visible(timeout=8000)

    routing_tab = page.locator('[data-testid="tab-access-and-routing"]')
    if routing_tab.count() > 0:
        routing_tab.click()

    codeblock = page.locator(
        '[data-testid="connector-account-effective-directive-codeblock"]'
    )
    expect(codeblock).to_be_visible(timeout=4000)


@pytest.mark.browser
def test_data_account_id_attribute_set_in_edit_mode(
    app_clean: str, page: Page
) -> None:
    """In edit mode, the ``.connector-account-editor`` root carries a
    ``data-account-id`` attribute equal to the seeded ``account.id``.
    Carried over from the M11 F2 L4 debrief polish — the DOM-anchored
    account resolution still depends on it."""
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
    ``data-account-id`` attribute."""
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
    """``window.App.studio.MASKED_SENTINEL`` equals ``'__MASKED__'``."""
    page.goto(f"{app_clean}#studio/connectors")
    page.wait_for_load_state("networkidle")

    sentinel = page.evaluate(
        "() => (window.App && window.App.studio && window.App.studio.MASKED_SENTINEL) || null"
    )
    assert sentinel == "__MASKED__", (
        f"window.App.studio.MASKED_SENTINEL not set to '__MASKED__'; got {sentinel!r}"
    )


@pytest.mark.browser
def test_create_mode_type_pick_does_not_crash(
    app_clean: str, page: Page
) -> None:
    """Create form → pick Discord → form re-mounts. The effective-
    directive codeblock is edit-mode-only; the create-mode re-render
    skips it. The Auto-reply listener still fires checkDirty but the
    codeblock helper's null-guards no-op when the codeblock is absent."""
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))

    page.goto(f"{app_clean}#studio/connectors/new")
    expect(
        page.locator('[data-testid="create-and-test-connector-account-btn"]')
    ).to_be_visible(timeout=8000)

    page.locator('[data-testid="connector-account-type-select"]').select_option(
        "discord"
    )

    expect(page.locator('[data-testid="discord-bot-token"]')).to_be_visible(
        timeout=4000
    )
    expect(
        page.locator('[data-testid="discord-intents-row"]')
    ).to_have_count(0)
    expect(
        page.locator(
            '[data-testid="connector-account-effective-directive-codeblock"]'
        )
    ).to_have_count(0)

    assert errors == [], (
        f"page errors during create-mode Discord pick: {errors!r}"
    )
