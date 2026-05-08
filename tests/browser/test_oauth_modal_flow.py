"""End-to-end Playwright flow tests for the F5 L5 OAuth login UX.

These tests drive the chat-area UI through the OAuth modal flow by:

  - Navigating to the chat area (via app_with_agent fixture).
  - Synthesizing fake ``auth_required`` / ``auth_resolved`` events directly
    on the running ``ws.onmessage`` handler via ``page.evaluate(...)`` —
    avoids needing a real OAuth Authorization Server in-the-loop for L5
    UI verification (L6 HAT exercises the full RFC-compliant fixture).
  - Asserting the resulting DOM transitions: inline Login button →
    modal → form-toggle → manual-entry submit → modal close.

The ``app_with_agent`` fixture seeds a mock provider + agent so the chat
area is reachable; the OAuth UI surface is independent of the mock agent
and renders against synthesized WS events.
"""

from __future__ import annotations

import pytest
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect


def _open_chat(page: Page, base_url: str, agent_name: str) -> None:
    page.goto(base_url)
    page.locator(".chat-welcome-item").filter(has_text=agent_name).click()
    expect(page.locator(".session-agent-badge")).to_have_text(agent_name, timeout=8000)


def _emit_ws_event(page: Page, payload: dict) -> None:
    """Push a synthetic event into the chat area's ``ws.onmessage`` handler.

    The chat area binds ``ws.onmessage = function (e) { ... }`` once on
    init; we invoke it directly with a synthetic ``MessageEvent``-shaped
    object. This mirrors the real WS path without needing to mint a real
    OAuth flow for UI-only assertions.
    """
    js = """
    (payload) => {
      const area = (window.App && window.App.areas)
        ? window.App.areas.find(a => a.id === 'chat')
        : null;
      if (!area || !area._ws || !area._ws()) {
        throw new Error('chat area or ws not available');
      }
      const ws = area._ws();
      ws.onmessage({ data: JSON.stringify(payload) });
    }
    """
    page.evaluate(js, payload)


@pytest.mark.browser
def test_login_button_renders_on_auth_required_event(
    app_with_agent: SeededApp, page: Page
) -> None:
    """A11 — auth_required event with consent_url=None renders the inline
    "Login required for <source_id>" button.
    """
    _open_chat(page, app_with_agent.base_url, app_with_agent.agent_name)
    _emit_ws_event(
        page,
        {
            "type": "auth_required",
            "source_id": "src-1",
            "tool_call_id": "tc-1",
            "resource_metadata_url": None,
            "consent_url": None,
        },
    )
    btn = page.locator(".login-required-btn")
    expect(btn).to_be_visible()
    expect(btn).to_have_text("Login required for src-1")


@pytest.mark.browser
def test_modal_opens_on_button_click(
    app_with_agent: SeededApp, page: Page
) -> None:
    """A11 — clicking the inline button opens the OAuth modal with the
    correct title.
    """
    _open_chat(page, app_with_agent.base_url, app_with_agent.agent_name)
    _emit_ws_event(
        page,
        {
            "type": "auth_required",
            "source_id": "src-2",
            "tool_call_id": "tc-1",
        },
    )
    page.locator(".login-required-btn").click()
    overlay = page.locator('[data-testid="oauth-modal-overlay"]')
    expect(overlay).to_be_visible()
    title = page.locator(".oauth-modal-overlay .modal-dialog-title")
    expect(title).to_have_text("Login required for src-2")


@pytest.mark.browser
def test_manual_entry_disclosure_toggles(
    app_with_agent: SeededApp, page: Page
) -> None:
    """A11 — clicking "Use manual entry instead" reveals the 3-field form."""
    _open_chat(page, app_with_agent.base_url, app_with_agent.agent_name)
    _emit_ws_event(page, {"type": "auth_required", "source_id": "src-3"})
    page.locator(".login-required-btn").click()
    form = page.locator('[data-testid="oauth-modal-manual-form"]')
    expect(form).to_be_hidden()
    page.locator('[data-testid="oauth-modal-manual-toggle-btn"]').click()
    expect(form).to_be_visible()
    expect(page.locator('input[name="client_id"]')).to_be_visible()
    expect(page.locator('input[name="auth_endpoint"]')).to_be_visible()
    expect(page.locator('input[name="token_endpoint"]')).to_be_visible()


@pytest.mark.browser
def test_manual_register_submission_persists_dcr_credentials(
    app_with_agent: SeededApp, page: Page
) -> None:
    """A11 — manual-entry form submit POSTs to /api/oauth/manual-register
    and the source's dcr_credentials are persisted server-side.

    We seed an MCPSource via the API first so the manual-register call
    has a target. The form submit also fires /api/oauth/start (the modal's
    chained call) but with no real OAuth AS, that POST will 404/500
    silently — we only assert manual-register persisted.
    """
    import httpx

    base_url = app_with_agent.base_url
    # Seed a streamable-http source.
    httpx.post(
        f"{base_url}/api/mcp-sources",
        json={
            "id": "src-mr",
            "name": "Source for manual-register",
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
        },
        timeout=5.0,
    )

    _open_chat(page, base_url, app_with_agent.agent_name)
    # Open modal directly via openManual so we don't need a button-click intercept.
    _emit_ws_event(
        page,
        {
            "type": "oauth_manual_registration_required",
            "source_id": "src-mr",
        },
    )
    expect(page.locator('[data-testid="oauth-modal-overlay"]')).to_be_visible()
    page.locator('input[name="client_id"]').fill("operator-cid-1")
    page.locator('input[name="auth_endpoint"]').fill(
        "https://example.com/authorize"
    )
    page.locator('input[name="token_endpoint"]').fill("https://example.com/token")
    page.locator('[data-testid="oauth-modal-manual-submit-btn"]').click()

    # Poll the API for the persisted dcr_credentials.
    persisted = None
    for _ in range(30):
        r = httpx.get(f"{base_url}/api/mcp-sources/src-mr", timeout=3.0)
        if r.status_code == 200:
            secrets = r.json().get("secrets", {})
            if "dcr_credentials" in secrets:
                persisted = secrets["dcr_credentials"]
                break
        page.wait_for_timeout(100)
    assert persisted is not None, (
        "dcr_credentials never appeared in source after manual-register submit"
    )
    # ``client_id`` is masked under L2's _OAUTH_MANAGED_SECRET_KEYS GET
    # contract — verify the structure / registration_method instead.
    assert persisted.get("registration_method") == "manual"


@pytest.mark.browser
def test_modal_closes_on_auth_resolved_event(
    app_with_agent: SeededApp, page: Page
) -> None:
    """A11 — modal auto-closes when an auth_resolved event arrives."""
    _open_chat(page, app_with_agent.base_url, app_with_agent.agent_name)
    _emit_ws_event(page, {"type": "auth_required", "source_id": "src-4"})
    page.locator(".login-required-btn").click()
    overlay = page.locator('[data-testid="oauth-modal-overlay"]')
    expect(overlay).to_be_visible()
    _emit_ws_event(page, {"type": "auth_resolved", "source_id": "src-4"})
    expect(overlay).to_be_hidden()


@pytest.mark.browser
def test_button_clears_on_auth_resolved_event(
    app_with_agent: SeededApp, page: Page
) -> None:
    """A11 — auth_resolved removes the inline Login-required button."""
    _open_chat(page, app_with_agent.base_url, app_with_agent.agent_name)
    _emit_ws_event(page, {"type": "auth_required", "source_id": "src-5"})
    btn = page.locator(".login-required-btn")
    expect(btn).to_be_visible()
    _emit_ws_event(page, {"type": "auth_resolved", "source_id": "src-5"})
    expect(btn).to_have_count(0)
