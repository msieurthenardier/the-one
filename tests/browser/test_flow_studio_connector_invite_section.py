"""Studio Connector Invite-section browser tests (M11 F1 L5).

Covers the Discord registry entry's ``renderInviteSection`` hook and the
substrate's invite-section mount between Test Connection and Danger Zone:

- Pre-probe state: the invite-hint is visible; the URL display is
  hidden (post-mount default when no probe has populated the cache).
- Post-probe state: a doctor report whose ``details.application_id``
  is set triggers ``setApplicationId`` → the URL display becomes
  visible with a ``permissions=2147552256`` substring and the constant
  ``client_id={appId}`` substring.
- URL stability + no intent toggles (M11 F17 L6): the ``permissions``
  integer is stable at 2147552256 post-probe; no ``discord-intents-row``
  or ``discord-intent-*`` checkboxes appear (Leg B subtraction). Intent
  toggles were removed — the backend always-on path makes them a trap.
- Stub-type account: no invite-section in the DOM (Stub entry does not
  provide ``renderInviteSection``; the substrate falls through to no
  HTML for that type — the section node is absent entirely).
- Copy button: writes the URL to the system clipboard via
  ``navigator.clipboard.writeText``; the test reads it back via
  ``navigator.clipboard.readText`` in a context with clipboard-read
  permission granted.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest
from browser.conftest import credentialed_context
from browser.seeders import seed_connector
from playwright.sync_api import Browser, Page, expect

_DISCORD_PERMISSIONS_CONSTANT = "2147552256"


@pytest.fixture
def clipboard_page(app_clean: str, browser: Browser) -> Iterator[Page]:
    """Function-scoped Playwright page with clipboard permissions granted.

    Headless Chromium denies ``navigator.clipboard.readText`` /
    ``writeText`` by default; the default ``page`` fixture in
    ``conftest.py`` does not grant them, so this fixture builds its own
    context via ``permissions=["clipboard-read", "clipboard-write"]``.

    Mission 20 / Flight 1 / Leg 4 review fix: this used to call
    ``browser.new_context(...)`` directly, bypassing the credential
    treatment ``conftest.py``'s shared ``page`` fixture gives every other
    test — no ``Authorization`` header, no handoff session cookie — so once
    the gate went live the studio content behind ``app_clean`` never
    loaded (``connector-test-connection-btn`` was never found). Routed
    through ``credentialed_context()`` (``conftest.py``) so this gets the
    same header + handoff-cookie treatment as ``page``, plus its own
    clipboard permissions layered on top via ``**context_kwargs``.
    """
    context = credentialed_context(
        browser,
        app_clean,
        permissions=["clipboard-read", "clipboard-write"],
    )
    page = context.new_page()
    try:
        yield page
    finally:
        context.close()


def _seed_discord(base_url: str, *, name: str = "Invite Bot", **kwargs) -> str:
    """Seed a ``type='discord'`` account with a default BOT_TOKEN."""
    secrets = kwargs.pop("secrets", {"BOT_TOKEN": "plaintext"})
    config = kwargs.pop("config", {})
    return seed_connector(
        base_url,
        type="discord",
        name=name,
        config=config,
        secrets=secrets,
    )


def _activate_access_and_routing_tab(page: Page) -> None:
    """F5 L3: edit-mode renders runtime-config (intents, guilds,
    presence, advanced kv) on the Access-and-Routing tab (was: the
    General tab's Connection section). Tests that interact with
    ``discord-intent-*`` testids must click the tab first so the panel
    is visible / actionable. Mirrors the helper at
    ``test_flow_studio_connector_discord_form.py:45``; inlined here for
    minimum cross-file coupling.
    """
    page.locator('[data-testid="tab-access-and-routing"]').click()
    expect(page.locator('[data-testid="connector-runtime-config-section"]')).to_be_visible(
        timeout=4000
    )


def _fulfill_probe(page: Page, account_id: str, application_id: str) -> None:
    """Install a ``page.route`` interceptor that returns a doctor
    report with ``details.application_id=application_id`` on the
    Test Connection POST."""
    payload = {
        "status": "ok",
        "message": "discord probe ok",
        "details": {"application_id": application_id},
    }

    def handler(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(payload),
        )

    page.route(f"**/api/connectors/{account_id}/test/connect", handler)


# ── Tests ────────────────────────────────────────────────────────────────


@pytest.mark.browser
def test_pre_probe_hint_visible_url_hidden(app_clean: str, page: Page) -> None:
    """Edit-mode mounts the Invite section. Before the doctor probe
    has populated the cache, the hint is visible and the URL display
    is hidden."""
    account_id = _seed_discord(app_clean, name="Pre-Probe Bot")
    page.goto(f"{app_clean}#studio/connectors/{account_id}")

    section = page.locator('[data-testid="connector-invite-section"]')
    expect(section).to_be_visible(timeout=8000)

    hint = page.locator('[data-testid="connector-invite-hint"]')
    url_wrap = page.locator('[data-testid="connector-invite-url-wrap"]')
    expect(hint).to_be_visible()
    expect(url_wrap).to_be_hidden()


@pytest.mark.browser
def test_post_probe_url_visible_with_permissions_constant(app_clean: str, page: Page) -> None:
    """After a successful Test Connection whose report carries
    ``details.application_id``, the URL display becomes visible with
    the computed invite URL — including ``client_id={appId}`` and
    the literal ``permissions=2147552256`` substring."""
    account_id = _seed_discord(app_clean, name="Post-Probe Bot")
    _fulfill_probe(page, account_id, application_id="999000111222333444")
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="connector-test-connection-btn"]')).to_be_visible(
        timeout=8000
    )

    page.locator('[data-testid="connector-test-connection-btn"]').click()

    # LED flips to ok → the banner-render path ran → setApplicationId
    # was called → the invite URL display now reflects the cache.
    led = page.locator('[data-testid="connector-test-led"]')
    expect(led).to_have_attribute("data-state", "ok", timeout=8000)

    url_wrap = page.locator('[data-testid="connector-invite-url-wrap"]')
    hint = page.locator('[data-testid="connector-invite-hint"]')
    expect(url_wrap).to_be_visible()
    expect(hint).to_be_hidden()

    url_code = page.locator('[data-testid="connector-invite-url"]')
    expect(url_code).to_contain_text("client_id=999000111222333444")
    expect(url_code).to_contain_text(f"permissions={_DISCORD_PERMISSIONS_CONSTANT}")
    expect(url_code).to_contain_text("scope=bot+applications.commands")


@pytest.mark.browser
def test_permissions_constant_stable_and_no_intent_checkboxes(app_clean: str, page: Page) -> None:
    """Post-probe invite URL has the stable ``permissions=2147552256``
    constant AND the editor renders no intent-toggle checkboxes.

    M11 F17 L6 (Leg B): intent checkboxes removed — the URL is no
    longer driven by a toggle. The permissions integer is pinned at
    2147552256 unconditionally; the absence of ``discord-intents-row``
    and ``discord-intent-*`` elements is also asserted here as a
    browser-level confirmation of the Leg B subtraction.
    """
    account_id = _seed_discord(app_clean, name="Stability Bot")
    _fulfill_probe(page, account_id, application_id="42424242424242")
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="connector-test-connection-btn"]')).to_be_visible(
        timeout=8000
    )

    page.locator('[data-testid="connector-test-connection-btn"]').click()
    expect(page.locator('[data-testid="connector-test-led"]')).to_have_attribute(
        "data-state", "ok", timeout=8000
    )

    url_code = page.locator('[data-testid="connector-invite-url"]')
    url_text = url_code.text_content() or ""
    assert f"permissions={_DISCORD_PERMISSIONS_CONSTANT}" in url_text, (
        f"permissions constant missing from invite URL: {url_text!r}"
    )

    # Navigate to the Access-and-Routing tab and assert no intent
    # checkboxes or intent row are rendered (Leg B subtraction).
    _activate_access_and_routing_tab(page)
    expect(page.locator('[data-testid="discord-intents-row"]')).to_have_count(0)
    expect(page.locator('[data-testid="discord-intent-message_content"]')).to_have_count(0)
    expect(page.locator('[data-testid="discord-intent-members"]')).to_have_count(0)
    expect(page.locator('[data-testid="discord-intent-guilds"]')).to_have_count(0)


@pytest.mark.browser
def test_stub_type_renders_no_invite_section(app_clean: str, page: Page) -> None:
    """``'stub'``-type accounts have no registry entry providing
    ``renderInviteSection`` → the substrate renders no HTML for that
    section → the section node is absent entirely."""
    account_id = seed_connector(app_clean, name="Stub Bot")
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="connector-test-connection-btn"]')).to_be_visible(
        timeout=8000
    )

    section = page.locator('[data-testid="connector-invite-section"]')
    expect(section).to_have_count(0)


@pytest.mark.browser
def test_copy_button_writes_url_to_clipboard(app_clean: str, clipboard_page: Page) -> None:
    """Clicking the Copy button writes the invite URL to the system
    clipboard. The test reads it back via ``navigator.clipboard.readText``
    in a context that has been granted clipboard permissions."""
    account_id = _seed_discord(app_clean, name="Copy Bot")
    _fulfill_probe(clipboard_page, account_id, application_id="77777777")
    clipboard_page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(clipboard_page.locator('[data-testid="connector-test-connection-btn"]')).to_be_visible(
        timeout=8000
    )

    clipboard_page.locator('[data-testid="connector-test-connection-btn"]').click()
    expect(clipboard_page.locator('[data-testid="connector-test-led"]')).to_have_attribute(
        "data-state", "ok", timeout=8000
    )

    url_code = clipboard_page.locator('[data-testid="connector-invite-url"]')
    expected_url = url_code.text_content() or ""
    assert f"permissions={_DISCORD_PERMISSIONS_CONSTANT}" in expected_url

    clipboard_page.locator('[data-testid="connector-invite-copy-btn"]').click()
    # Brief tick to allow the writeText promise to settle.
    clipboard_page.wait_for_timeout(100)

    clipboard_text = clipboard_page.evaluate("navigator.clipboard.readText()")
    assert clipboard_text == expected_url, (
        f"clipboard mismatch:\n  expected={expected_url!r}\n  got     ={clipboard_text!r}"
    )
