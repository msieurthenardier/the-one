"""Studio Connector Invite-section browser tests (M11 F1 L5).

Covers the Discord registry entry's ``renderInviteSection`` hook and the
substrate's invite-section mount between Test Connection and Danger Zone:

- Pre-probe state: the invite-hint is visible; the URL display is
  hidden (post-mount default when no probe has populated the cache).
- Post-probe state: a doctor report whose ``details.application_id``
  is set triggers ``setApplicationId`` → the URL display becomes
  visible with a ``permissions=2147552256`` substring and the constant
  ``client_id={appId}`` substring.
- Intent-toggle stability: toggling an intent checkbox after the URL
  is rendered does NOT change the URL string (intents and permissions
  are orthogonal per F1 Design Decisions) AND the literal
  ``permissions=2147552256`` substring is preserved (catches both
  "URL got rewritten" and "future bug swapped the constant").
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
from browser.seeders import seed_connector_account
from playwright.sync_api import Browser, Page, expect


_DISCORD_PERMISSIONS_CONSTANT = "2147552256"


@pytest.fixture
def clipboard_page(browser: Browser) -> Iterator[Page]:
    """Function-scoped Playwright page with clipboard permissions granted.

    Headless Chromium denies ``navigator.clipboard.readText`` /
    ``writeText`` by default; the default ``page`` fixture in
    ``conftest.py:214`` does not grant them. This fixture mirrors the
    precedent at ``tests/browser/test_markdown.py:127-151`` — a new
    context with ``permissions=["clipboard-read", "clipboard-write"]``
    so the Copy-button e2e exercises the success path.
    """
    context = browser.new_context(
        color_scheme="no-preference",
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
    return seed_connector_account(
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
    expect(
        page.locator('[data-testid="connector-account-runtime-config-section"]')
    ).to_be_visible(timeout=4000)


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

    page.route(
        f"**/api/connector-accounts/{account_id}/test/connect", handler
    )


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
def test_post_probe_url_visible_with_permissions_constant(
    app_clean: str, page: Page
) -> None:
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
    expect(url_code).to_contain_text(
        f"permissions={_DISCORD_PERMISSIONS_CONSTANT}"
    )
    expect(url_code).to_contain_text("scope=bot+applications.commands")


@pytest.mark.browser
def test_intent_toggle_preserves_url_and_permissions_constant(
    app_clean: str, page: Page
) -> None:
    """Toggling an intent checkbox after the URL is rendered must NOT
    change the URL string (intents and permissions are orthogonal) AND
    the literal ``permissions=2147552256`` substring is preserved."""
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
    url_before = url_code.text_content() or ""
    assert (
        f"permissions={_DISCORD_PERMISSIONS_CONSTANT}" in url_before
    ), f"baseline URL missing permissions constant: {url_before!r}"

    # Toggle message_content intent and let the change-handler tick.
    # F5 L3 moved the Intent checkboxes from the General tab to the
    # Access-and-Routing tab; activate that tab before interacting.
    _activate_access_and_routing_tab(page)
    page.locator('[data-testid="discord-intent-message_content"]').click()
    page.wait_for_timeout(50)

    url_after = url_code.text_content() or ""
    assert url_after == url_before, (
        f"URL drift after intent toggle:\n  before={url_before!r}\n  after ={url_after!r}"
    )
    assert (
        f"permissions={_DISCORD_PERMISSIONS_CONSTANT}" in url_after
    ), f"permissions constant lost after toggle: {url_after!r}"


@pytest.mark.browser
def test_stub_type_renders_no_invite_section(app_clean: str, page: Page) -> None:
    """``'stub'``-type accounts have no registry entry providing
    ``renderInviteSection`` → the substrate renders no HTML for that
    section → the section node is absent entirely."""
    account_id = seed_connector_account(app_clean, name="Stub Bot")
    page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(page.locator('[data-testid="connector-test-connection-btn"]')).to_be_visible(
        timeout=8000
    )

    section = page.locator('[data-testid="connector-invite-section"]')
    expect(section).to_have_count(0)


@pytest.mark.browser
def test_copy_button_writes_url_to_clipboard(
    app_clean: str, clipboard_page: Page
) -> None:
    """Clicking the Copy button writes the invite URL to the system
    clipboard. The test reads it back via ``navigator.clipboard.readText``
    in a context that has been granted clipboard permissions."""
    account_id = _seed_discord(app_clean, name="Copy Bot")
    _fulfill_probe(clipboard_page, account_id, application_id="77777777")
    clipboard_page.goto(f"{app_clean}#studio/connectors/{account_id}")
    expect(
        clipboard_page.locator('[data-testid="connector-test-connection-btn"]')
    ).to_be_visible(timeout=8000)

    clipboard_page.locator('[data-testid="connector-test-connection-btn"]').click()
    expect(
        clipboard_page.locator('[data-testid="connector-test-led"]')
    ).to_have_attribute("data-state", "ok", timeout=8000)

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
