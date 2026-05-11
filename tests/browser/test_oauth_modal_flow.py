"""End-to-end Playwright flow tests for the MCP OAuth login UX.

These tests drive the chat-area UI through the OAuth login flow by:

  - Navigating to the chat area (via app_with_agent fixture).
  - Synthesizing fake ``auth_required`` / ``auth_resolved`` events directly
    on the running ``ws.onmessage`` handler via ``page.evaluate(...)`` —
    avoids needing a real OAuth Authorization Server in-the-loop for UI
    verification.
  - Stubbing ``window.open`` to record calls without spawning real browser
    windows in the headless test environment.
  - Asserting the resulting DOM transitions: inline Login button →
    popup opened on click → popup closed on auth_resolved.

The ``app_with_agent`` fixture seeds a mock provider + agent so the chat
area is reachable; the OAuth UI surface is independent of the mock agent
and renders against synthesized WS events.

Historical note: an earlier iteration of this UX surfaced an intermediate
``oauth-modal`` dialog between the chat button and the consent window.
The dialog was dropped because (1) it added a redundant click without
adding signal, and (2) opening the consent ``window.open()`` from inside
the modal's Connect-button handler — after the user-gesture chain had
already been broken by the WS round-trip — caused some browsers to
convert the popup into a fresh tab with stripped Referer, breaking the
OAuth provider's CSRF checks. The current path opens the consent popup
synchronously during the button click and navigates it when the WS
event with the real ``consent_url`` arrives.
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


def _install_window_open_stub(page: Page) -> None:
    """Replace window.open with a recorder that returns a fake popup.

    Captures calls into ``window.__openCalls`` and returns a stub
    object exposing ``close()``, ``focus()``, ``closed``, and a settable
    ``location.href`` so the chat code can navigate the "popup" when the
    second ``auth_required`` event arrives.
    """
    page.evaluate(
        """
        () => {
          window.__openCalls = [];
          window.__lastPopup = null;
          window.open = function (url, name, features) {
            const popup = {
              _url: url,
              _name: name,
              _features: features,
              closed: false,
              focus: function () {},
              close: function () { this.closed = true; },
              location: {
                _href: url,
                get href() { return this._href; },
                set href(v) { this._href = v; },
              },
            };
            window.__openCalls.push({ url, name, features, popup });
            window.__lastPopup = popup;
            return popup;
          };
        }
        """
    )


@pytest.mark.browser
def test_login_button_renders_with_source_name(
    app_with_agent: SeededApp, page: Page
) -> None:
    """The inline button renders the human-readable source_name when present
    in the event, falling back to source_id only when name is absent.
    """
    _open_chat(page, app_with_agent.base_url, app_with_agent.agent_name)
    _emit_ws_event(
        page,
        {
            "type": "auth_required",
            "source_id": "src-1",
            "source_name": "Cloudflare MCP",
            "tool_call_id": "tc-1",
            "resource_metadata_url": None,
            "consent_url": None,
        },
    )
    btn = page.locator(".login-required-btn")
    expect(btn).to_be_visible()
    expect(btn).to_have_text("Login required for Cloudflare MCP")


@pytest.mark.browser
def test_login_button_falls_back_to_source_id_when_no_name(
    app_with_agent: SeededApp, page: Page
) -> None:
    _open_chat(page, app_with_agent.base_url, app_with_agent.agent_name)
    _emit_ws_event(
        page,
        {
            "type": "auth_required",
            "source_id": "src-no-name",
            "tool_call_id": "tc-1",
            "resource_metadata_url": None,
            "consent_url": None,
        },
    )
    btn = page.locator(".login-required-btn")
    expect(btn).to_be_visible()
    expect(btn).to_have_text("Login required for src-no-name")


@pytest.mark.browser
def test_button_click_opens_popup_with_window_open_features(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Clicking the inline button opens a popup via ``window.open`` with
    explicit width/height features (NOT a new tab) — this preserves the
    user-gesture chain and avoids OAuth Referer/CSRF issues with tab-
    converted popups.
    """
    _open_chat(page, app_with_agent.base_url, app_with_agent.agent_name)
    _install_window_open_stub(page)
    _emit_ws_event(
        page,
        {
            "type": "auth_required",
            "source_id": "src-2",
            "source_name": "Test MCP",
            "tool_call_id": "tc-1",
            "consent_url": None,
        },
    )
    page.locator(".login-required-btn").click()
    calls = page.evaluate("() => window.__openCalls")
    assert len(calls) == 1, f"expected exactly 1 window.open call, got {len(calls)}"
    call = calls[0]
    assert call["url"] == "about:blank", (
        f"first open should be about:blank placeholder; got {call['url']!r}"
    )
    # Features must include explicit dimensions — that is what makes the
    # browser open a popup window rather than a foreground tab.
    assert "width=600" in call["features"]
    assert "height=700" in call["features"]
    assert "src-2" in call["name"], (
        f"popup name should incorporate source_id for routing; got {call['name']!r}"
    )


@pytest.mark.browser
def test_second_auth_required_event_navigates_popup_to_consent_url(
    app_with_agent: SeededApp, page: Page
) -> None:
    """The lazy-OAuth flow emits two ``auth_required`` events: the first
    has ``consent_url=None`` and renders the button; the second (after
    /api/oauth/start drives the SDK flow) carries the real consent URL.
    When the second event arrives, the popup opened during the button
    click should navigate to the consent URL.
    """
    _open_chat(page, app_with_agent.base_url, app_with_agent.agent_name)
    _install_window_open_stub(page)
    _emit_ws_event(
        page,
        {
            "type": "auth_required",
            "source_id": "src-3",
            "source_name": "Test MCP",
            "tool_call_id": "tc-1",
            "consent_url": None,
        },
    )
    page.locator(".login-required-btn").click()
    _emit_ws_event(
        page,
        {
            "type": "auth_required",
            "source_id": "src-3",
            "source_name": "Test MCP",
            "tool_call_id": "tc-1",
            "consent_url": "https://idp.example.com/authorize?state=ST",
        },
    )
    href = page.evaluate("() => window.__lastPopup && window.__lastPopup.location.href")
    assert href == "https://idp.example.com/authorize?state=ST"


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


@pytest.mark.browser
def test_popup_closes_on_auth_resolved_event(
    app_with_agent: SeededApp, page: Page
) -> None:
    """When the OAuth callback fires and broadcasts ``auth_resolved``,
    the chat handler closes the popup that was opened during the button
    click. (In production the callback page also calls window.close()
    itself; this assertion covers the chat-side fallback path.)
    """
    _open_chat(page, app_with_agent.base_url, app_with_agent.agent_name)
    _install_window_open_stub(page)
    _emit_ws_event(
        page,
        {
            "type": "auth_required",
            "source_id": "src-4",
            "tool_call_id": "tc-1",
            "consent_url": None,
        },
    )
    page.locator(".login-required-btn").click()
    _emit_ws_event(page, {"type": "auth_resolved", "source_id": "src-4"})
    closed = page.evaluate("() => window.__lastPopup && window.__lastPopup.closed")
    assert closed is True
