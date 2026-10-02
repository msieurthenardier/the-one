"""A new_session whose join never arrives recovers without a reconnect.

The chat area marks a sent ``new_session`` (``pendingStart.sent``) so a
``session_list`` reply cannot re-send it. The protocol has no error frame for
it, so if the reply is lost the flag would stay set until a reconnect. A
bounded timer (``App.chatStartJoinTimeoutMs`` overrides the 10s default) clears
it and re-requests the list, whose drain re-sends the request.
"""

from __future__ import annotations

import pytest
from browser import _nav
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

# Drops the FIRST new_session frame the page sends (the server never sees it),
# and counts every new_session attempt.
_DROP_FIRST_NEW_SESSION = """
(() => {
  window.__newSessionSends = 0;
  const orig = WebSocket.prototype.send;
  WebSocket.prototype.send = function (data) {
    try {
      if (JSON.parse(data).action === 'new_session') {
        window.__newSessionSends += 1;
        if (window.__newSessionSends === 1) return;
      }
    } catch (e) { /* not JSON */ }
    return orig.call(this, data);
  };
})();
"""


def test_stalled_new_session_is_resent_after_the_bounded_wait(
    app_with_agent: SeededApp, page: Page
) -> None:
    page.add_init_script(_DROP_FIRST_NEW_SESSION)
    page.goto(app_with_agent.base_url)
    page.evaluate("App.chatStartJoinTimeoutMs = 500")
    page.locator(".chat-welcome-item").filter(has_text=app_with_agent.agent_name).click()

    # The first send was dropped; the recovery timer re-sends it and the join lands.
    page.wait_for_function("window.__newSessionSends >= 2", timeout=15000)
    expect(page.locator(".session-agent-badge")).to_have_text(
        app_with_agent.agent_name, timeout=8000
    )
    assert _nav.current_route(page).startswith("chats/")
    assert page.evaluate("window.__newSessionSends") == 2
