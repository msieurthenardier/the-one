"""End-to-end Playwright flow tests for the F5 L5 OAuth login UX.

These tests drive the chat-area UI through the OAuth modal flow by:

  - Navigating to the chat area (via app_with_agent fixture).
  - Synthesizing fake ``auth_required`` / ``auth_resolved`` events directly
    on the running ``ws.onmessage`` handler via ``page.evaluate(...)`` —
    avoids needing a real OAuth Authorization Server in-the-loop for L5
    UI verification (L6 HAT exercises the full RFC-compliant fixture).
  - Asserting the resulting DOM transitions: inline Login button →
    modal → modal close on auth_resolved.

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
