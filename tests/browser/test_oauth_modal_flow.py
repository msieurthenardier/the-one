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
from browser import _chats
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect


def _open_chat(page: Page, base_url: str, agent_name: str) -> None:
    """Open a JOINED chat: since M25 F4 L3b a start is a pending chat whose
    session-scoped frames (``auth_*`` included) are gated until its first send
    joins it; the first turn is let finish before a test injects frames."""
    page.goto(base_url)
    _chats.start_chat(page, agent_name)
    _chats.send_first(page, "hello")
    expect(page.locator('[data-testid="chat-send-btn"]')).to_be_enabled(timeout=10000)


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
def test_login_button_renders_with_source_name(app_with_agent: SeededApp, page: Page) -> None:
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
    expect(btn).to_have_text("Log in to Cloudflare MCP")


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
    expect(btn).to_have_text("Log in to src-no-name")


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
    # Bounded wait (squawk 0201): under heavy load the navigation may land a
    # moment after the emit, so poll rather than read once.
    consent = "https://idp.example.com/authorize?state=ST"
    page.wait_for_function(
        "(u) => window.__lastPopup && window.__lastPopup.location.href === u",
        arg=consent,
        timeout=10_000,
    )
    href = page.evaluate("() => window.__lastPopup && window.__lastPopup.location.href")
    assert href == consent


@pytest.mark.browser
def test_button_clears_on_auth_resolved_event(app_with_agent: SeededApp, page: Page) -> None:
    """A11 — auth_resolved removes the inline Login-required button."""
    _open_chat(page, app_with_agent.base_url, app_with_agent.agent_name)
    _emit_ws_event(page, {"type": "auth_required", "source_id": "src-5"})
    btn = page.locator(".login-required-btn")
    expect(btn).to_be_visible()
    _emit_ws_event(page, {"type": "auth_resolved", "source_id": "src-5"})
    expect(btn).to_have_count(0)


@pytest.mark.browser
def test_popup_closes_on_auth_resolved_event(app_with_agent: SeededApp, page: Page) -> None:
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
    page.wait_for_function(
        "() => window.__lastPopup && window.__lastPopup.closed === true",
        timeout=10_000,
    )
    closed = page.evaluate("() => window.__lastPopup && window.__lastPopup.closed")
    assert closed is True


# ─── Sortie 04: honest sign-in (link block; null popup is not a failure) ───

CONSENT = "https://idp.example.com/authorize?state=ST2"


def _stub_oauth_start(page: Page) -> list:
    """Answer POST /api/oauth/start 200 and record the request bodies."""
    posts: list = []

    def handle(route):
        posts.append(route.request.post_data)
        route.fulfill(status=200, content_type="application/json", body="{}")

    page.route("**/api/oauth/start", handle)
    return posts


def _wait_for_posts(page: Page, posts: list, count: int, timeout_ms: int = 5000) -> None:
    """Block until the route handler has recorded ``count`` POSTs.

    ``expect_request`` returns on the page's ``request`` event, which can fire
    before the route handler has run and appended to ``posts``; reading
    ``len(posts)`` straight after it is racy under load. Poll instead.
    """
    waited = 0
    while len(posts) < count and waited < timeout_ms:
        page.wait_for_timeout(25)
        waited += 25
    assert len(posts) == count, (
        f"expected {count} recorded POST /api/oauth/start, saw {len(posts)} after {waited} ms"
    )


def _auth_frame(source_id: str, consent_url: str | None = None) -> dict:
    return {
        "type": "auth_required",
        "source_id": source_id,
        "source_name": "Goldfinch",
        "tool_call_id": "tc-1",
        "consent_url": consent_url,
    }


def _install_null_window_open(page: Page) -> None:
    page.evaluate(
        "() => { window.__openCalls = []; window.open = function (url, name, features) {"
        " window.__openCalls.push({url, name, features}); return null; }; }"
    )


@pytest.mark.browser
def test_null_popup_still_starts_the_flow_and_shows_the_link_block(
    app_with_agent: SeededApp, page: Page
) -> None:
    _open_chat(page, app_with_agent.base_url, app_with_agent.agent_name)
    posts = _stub_oauth_start(page)
    _install_null_window_open(page)
    _emit_ws_event(page, _auth_frame("src-n1"))
    with page.expect_request("**/api/oauth/start"):
        page.locator(".login-required-btn").click()
    _wait_for_posts(page, posts, 1)
    expect(page.locator(".msg.system", has_text="Popup blocked")).to_have_count(0)
    _emit_ws_event(page, _auth_frame("src-n1", CONSENT))
    url = page.locator('[data-testid="chat-consent-link-url"]')
    expect(url).to_have_value(CONSENT)
    anchor = page.locator('[data-testid="chat-consent-link-open"]')
    expect(anchor).to_have_attribute("href", CONSENT)
    expect(anchor).to_have_attribute("target", "_blank")
    expect(page.locator('[data-testid="chat-consent-link-copy"]')).to_be_visible()
    expect(page.locator(".login-required-btn")).to_be_hidden()
    expect(page.locator(".login-required-group")).to_have_count(1)
    # about:blank at click time (browser mode), then one best-effort open of the URL.
    calls = page.evaluate("() => window.__openCalls")
    assert [c["url"] for c in calls] == ["about:blank", CONSENT]
    assert calls[1]["name"] == "_blank"


@pytest.mark.browser
def test_desktop_webview_skips_the_about_blank_pre_open(
    app_with_agent: SeededApp, page: Page
) -> None:
    _open_chat(page, app_with_agent.base_url, app_with_agent.agent_name)
    posts = _stub_oauth_start(page)
    _install_null_window_open(page)
    page.evaluate("() => { window.App.desktop.isWebview = () => true; }")
    _emit_ws_event(page, _auth_frame("src-d1"))
    with page.expect_request("**/api/oauth/start"):
        page.locator(".login-required-btn").click()
    _wait_for_posts(page, posts, 1)
    assert page.evaluate("() => window.__openCalls") == []
    _emit_ws_event(page, _auth_frame("src-d1", CONSENT))
    expect(page.locator('[data-testid="chat-consent-link-url"]')).to_have_value(CONSENT)
    calls = page.evaluate("() => window.__openCalls")
    assert [c["url"] for c in calls] == [CONSENT]


@pytest.mark.browser
def test_replayed_frame_keeps_the_block_and_does_not_reopen(
    app_with_agent: SeededApp, page: Page
) -> None:
    _open_chat(page, app_with_agent.base_url, app_with_agent.agent_name)
    posts = _stub_oauth_start(page)
    _install_null_window_open(page)
    page.evaluate("() => { window.App.desktop.isWebview = () => true; }")
    _emit_ws_event(page, _auth_frame("src-r1"))
    with page.expect_request("**/api/oauth/start"):
        page.locator(".login-required-btn").click()
    _emit_ws_event(page, _auth_frame("src-r1", CONSENT))
    expect(page.locator('[data-testid="chat-consent-link-url"]')).to_have_value(CONSENT)
    # Reconnect replays: consent_url is null (rebuilt from tool-result metadata).
    for _ in range(3):
        _emit_ws_event(page, _auth_frame("src-r1", None))
    expect(page.locator('[data-testid="chat-consent-link-url"]')).to_have_value(CONSENT)
    expect(page.locator(".login-required-group")).to_have_count(1)
    expect(page.locator(".login-required-btn")).to_be_hidden()
    assert [c["url"] for c in page.evaluate("() => window.__openCalls")] == [CONSENT]
    _wait_for_posts(page, posts, 1)


@pytest.mark.browser
def test_auth_failed_removes_the_block_and_offers_log_in_again(
    app_with_agent: SeededApp, page: Page
) -> None:
    _open_chat(page, app_with_agent.base_url, app_with_agent.agent_name)
    _stub_oauth_start(page)
    _install_null_window_open(page)
    _emit_ws_event(page, _auth_frame("src-f1"))
    with page.expect_request("**/api/oauth/start"):
        page.locator(".login-required-btn").click()
    _emit_ws_event(page, _auth_frame("src-f1", CONSENT))
    expect(page.locator('[data-testid="chat-consent-link-url"]')).to_be_visible()
    _emit_ws_event(page, {"type": "auth_failed", "source_id": "src-f1", "description": "denied"})
    expect(page.locator('[data-testid="chat-consent-link-url"]')).to_have_count(0)
    expect(page.locator(".login-required-btn")).to_be_visible()
    expect(page.locator(".msg.system", has_text="OAuth failed: denied")).to_have_count(1)
    # The flow state is cleared: a replay with no URL shows "Log in", not a block.
    _emit_ws_event(page, _auth_frame("src-f1", None))
    expect(page.locator(".login-required-btn")).to_be_visible()
    expect(page.locator('[data-testid="chat-consent-link-url"]')).to_have_count(0)
    expect(page.locator(".login-required-group")).to_have_count(1)


@pytest.mark.browser
def test_auth_resolved_clears_the_block(app_with_agent: SeededApp, page: Page) -> None:
    _open_chat(page, app_with_agent.base_url, app_with_agent.agent_name)
    _stub_oauth_start(page)
    _install_null_window_open(page)
    # The block shows only for a flow this tab started, so click "Log in" first.
    _emit_ws_event(page, _auth_frame("src-ok1"))
    with page.expect_request("**/api/oauth/start"):
        page.locator(".login-required-btn").click()
    _emit_ws_event(page, _auth_frame("src-ok1", CONSENT))
    expect(page.locator('[data-testid="chat-consent-link-url"]')).to_have_value(CONSENT)
    _emit_ws_event(page, {"type": "auth_resolved", "source_id": "src-ok1"})
    expect(page.locator('[data-testid="chat-consent-link-url"]')).to_have_count(0)
    expect(page.locator(".login-required-group")).to_have_count(0)


@pytest.mark.browser
def test_in_band_consent_frame_is_ignored_and_log_in_starts_a_fresh_flow(
    app_with_agent: SeededApp, page: Page
) -> None:
    """HAT H2: the SDK's in-band flow broadcasts a consent_url this tab did not
    start; it dies at the connect timeout. It must not render a link block, and
    "Log in" must start a fresh /api/oauth/start rather than reopen it."""
    _open_chat(page, app_with_agent.base_url, app_with_agent.agent_name)
    posts = _stub_oauth_start(page)
    _install_null_window_open(page)
    page.evaluate("() => { window.App.desktop.isWebview = () => true; }")
    _emit_ws_event(page, _auth_frame("src-ib1", CONSENT))
    expect(page.locator(".login-required-btn")).to_be_visible()
    expect(page.locator('[data-testid="chat-consent-link-url"]')).to_have_count(0)
    assert page.evaluate("() => window.__openCalls") == []
    # The pause frame replays with consent_url null.
    _emit_ws_event(page, _auth_frame("src-ib1", None))
    expect(page.locator(".login-required-btn")).to_be_visible()
    expect(page.locator('[data-testid="chat-consent-link-url"]')).to_have_count(0)
    # Negative case: the UI expects above prove the frames were handled; add a
    # short bounded settle so a (wrongly) started flow would have reached the
    # route handler before we assert nothing was posted.
    page.wait_for_timeout(500)
    assert posts == []
    with page.expect_request("**/api/oauth/start"):
        page.locator(".login-required-btn").click()
    _wait_for_posts(page, posts, 1)
    assert page.evaluate("() => window.__openCalls") == []
    # The fresh flow's own consent frame now renders the block.
    fresh = "https://idp.example.com/authorize?state=FRESH"
    _emit_ws_event(page, _auth_frame("src-ib1", fresh))
    expect(page.locator('[data-testid="chat-consent-link-url"]')).to_have_value(fresh)
    expect(page.locator(".login-required-btn")).to_be_hidden()


UNSAFE = "javascript:alert(1)"


@pytest.mark.browser
def test_non_web_consent_url_is_never_opened_or_linked(
    app_with_agent: SeededApp, page: Page
) -> None:
    _open_chat(page, app_with_agent.base_url, app_with_agent.agent_name)
    _stub_oauth_start(page)
    page.evaluate(
        "() => { window.__openCalls = []; window.__popup = {closed: false, hrefs: [],"
        " close() { this.closed = true; }, focus() {},"
        " location: { set href(v) { window.__popup.hrefs.push(v); } } };"
        " window.open = function (url) { window.__openCalls.push(url);"
        " return url === 'about:blank' ? window.__popup : null; }; }"
    )
    _emit_ws_event(page, _auth_frame("src-u1"))
    with page.expect_request("**/api/oauth/start"):
        page.locator(".login-required-btn").click()
    _emit_ws_event(page, _auth_frame("src-u1", UNSAFE))
    expect(page.locator(".consent-link-unsafe")).to_be_visible()
    expect(page.locator('[data-testid="chat-consent-link-open"]')).to_have_count(0)
    expect(page.locator('[data-testid="chat-consent-link-url"]')).to_have_count(0)
    assert page.evaluate("() => window.__openCalls") == ["about:blank"]
    assert page.evaluate("() => window.__popup.hrefs") == []


@pytest.mark.browser
def test_auth_resolved_moves_focus_from_the_block_to_the_composer(
    app_with_agent: SeededApp, page: Page
) -> None:
    _open_chat(page, app_with_agent.base_url, app_with_agent.agent_name)
    _stub_oauth_start(page)
    _install_null_window_open(page)
    _emit_ws_event(page, _auth_frame("src-f1"))
    with page.expect_request("**/api/oauth/start"):
        page.locator(".login-required-btn").click()
    _emit_ws_event(page, _auth_frame("src-f1", CONSENT))
    anchor = page.locator('[data-testid="chat-consent-link-open"]')
    anchor.focus()
    expect(anchor).to_be_focused()
    _emit_ws_event(page, {"type": "auth_resolved", "source_id": "src-f1"})
    expect(page.locator(".login-required-group")).to_have_count(0)
    expect(page.locator('[data-testid="chat-input"]')).to_be_focused()


@pytest.mark.browser
def test_auth_resolved_does_not_steal_focus_from_elsewhere(
    app_with_agent: SeededApp, page: Page
) -> None:
    _open_chat(page, app_with_agent.base_url, app_with_agent.agent_name)
    _stub_oauth_start(page)
    _install_null_window_open(page)
    _emit_ws_event(page, _auth_frame("src-f2"))
    with page.expect_request("**/api/oauth/start"):
        page.locator(".login-required-btn").click()
    _emit_ws_event(page, _auth_frame("src-f2", CONSENT))
    page.locator('[data-testid="chat-send-btn"]').focus()
    _emit_ws_event(page, {"type": "auth_resolved", "source_id": "src-f2"})
    expect(page.locator(".login-required-group")).to_have_count(0)
    expect(page.locator('[data-testid="chat-send-btn"]')).to_be_focused()


@pytest.mark.browser
def test_copy_name_follows_its_text_while_the_live_region_announces(
    app_with_agent: SeededApp, page: Page
) -> None:
    _open_chat(page, app_with_agent.base_url, app_with_agent.agent_name)
    _stub_oauth_start(page)
    _install_null_window_open(page)
    _emit_ws_event(page, _auth_frame("src-c1"))
    with page.expect_request("**/api/oauth/start"):
        page.locator(".login-required-btn").click()
    _emit_ws_event(page, _auth_frame("src-c1", CONSENT))
    page.evaluate("() => { navigator.clipboard.writeText = () => Promise.resolve(); }")
    copy = page.locator('[data-testid="chat-consent-link-copy"]')
    copy.click()
    expect(copy).to_have_text("Copied")
    # Immediate, non-retrying reads: the "Copied" flash lasts 2s and an auto-retrying
    # expect would pass once it reverts. The name follows the visible text (WCAG 2.5.3).
    assert copy.get_attribute("aria-label") is None
    assert page.get_by_role("button", name="Copied", exact=True).count() == 1
    expect(page.locator(".consent-link-live")).to_have_text("Link copied")


@pytest.mark.browser
def test_keyboard_log_in_moves_focus_to_the_sign_in_link(
    app_with_agent: SeededApp, page: Page
) -> None:
    _open_chat(page, app_with_agent.base_url, app_with_agent.agent_name)
    _stub_oauth_start(page)
    _install_null_window_open(page)
    _emit_ws_event(page, _auth_frame("src-k1"))
    btn = page.locator(".login-required-btn")
    btn.focus()
    page.keyboard.press("Enter")
    _emit_ws_event(page, _auth_frame("src-k1", CONSENT))
    anchor = page.locator('[data-testid="chat-consent-link-open"]')
    expect(anchor).to_be_focused()
    expect(anchor).to_have_accessible_name("Open sign-in page (opens in your browser)")
    expect(page.locator('[data-testid="chat-consent-link-url"]')).to_have_attribute(
        "aria-label", "Sign-in address for Goldfinch"
    )


@pytest.mark.browser
def test_sign_in_group_sits_after_the_trace_shell_not_inside_it(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Operator HAT decision (sortie 04): the sign-in control must not hide in the
    collapsible "Tool activity" panel. It is the trace shell's next sibling."""
    _open_chat(page, app_with_agent.base_url, app_with_agent.agent_name)
    _emit_ws_event(
        page,
        {
            "type": "tool_call",
            "name": "probe",
            "arguments": {},
            "tool_call_id": "tc-1",
            "parent_message_id": "pm-1",
        },
    )
    shell = page.locator(".trace-shell")
    expect(shell).to_have_count(1)
    frame = _auth_frame("src-t1") | {"parent_message_id": "pm-1"}
    _emit_ws_event(page, frame)
    group = page.locator(".login-required-group")
    expect(group).to_have_count(1)
    expect(page.locator(".trace-shell .login-required-group")).to_have_count(0)
    adjacent = page.locator(".trace-shell + .login-required-group")
    expect(adjacent).to_have_count(1)
    # The trace's item count is the tool activity only (the one tool call).
    expect(page.locator(".trace-count")).to_have_text("1")
    # Collapsing the trace leaves the control visible.
    page.evaluate("() => { document.querySelector('.trace-shell details').open = false; }")
    expect(page.locator(".login-required-btn")).to_be_visible()
    # A replay keeps exactly one group, in the same place.
    _emit_ws_event(page, frame)
    expect(group).to_have_count(1)
    expect(adjacent).to_have_count(1)
    expect(page.locator(".trace-shell .login-required-group")).to_have_count(0)
    expect(page.locator(".trace-count")).to_have_text("1")
