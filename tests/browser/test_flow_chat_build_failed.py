"""The client half of the ``build_failed`` degraded chat (sortie 07 leg 2, DD7).

The server half (``session_joined`` with ``status: "build_failed"`` and a fixed ``reason``)
is unit-tested in ``tests/test_session_build_failed.py``. Here a local
``page.route_web_socket`` helper rewrites the REAL server's ``session_joined`` reply so the
client sees that frame, with no product test seam:

* a joined chat shows the server's reason in the health banner, disables the composer and still
  renders the stored history;
* a start that lands on ``build_failed`` with an empty history goes back to the pending chat
  and shows the reason.

Falls in the ``chats`` browser lane (``test_flow_chat*``).
"""

from __future__ import annotations

import json

import pytest
from browser import _chats, _nav
from browser.seeders import SeededApp, seed_session
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

REASON = "Server says: this agent could not be set up (test reason)."


class _BuildFailedSocket:
    """Connects the page's socket to the real server, then rewrites each ``session_joined``
    reply to ``build_failed`` with ``REASON`` (and, when ``empty_history``, no history)."""

    def __init__(self, empty_history: bool = False) -> None:
        self.empty_history = empty_history
        self.rewritten = 0

    def install(self, page: Page) -> None:
        page.route_web_socket("**/ws", self._on_connect)

    def _on_connect(self, ws) -> None:
        server = ws.connect_to_server()
        server.on_message(lambda message: ws.send(self._rewrite(message)))
        ws.on_message(lambda message: server.send(message))

    def _rewrite(self, message):
        try:
            data = json.loads(message)
        except (TypeError, ValueError):
            return message
        if not isinstance(data, dict) or data.get("type") != "session_joined":
            return message
        data["status"] = "build_failed"
        data["reason"] = REASON
        if self.empty_history:
            data["history"] = []
        self.rewritten += 1
        return json.dumps(data)


def test_a_joined_build_failed_chat_shows_the_reason_and_the_history(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    sid = seed_session(
        base,
        agent,
        "Stored chat",
        "2026-01-02T00:00:00Z",
        messages=[
            {"role": "user", "content": "STORED QUESTION"},
            {"role": "assistant", "content": "STORED ANSWER"},
        ],
    )
    script = _BuildFailedSocket()
    script.install(page)
    _nav.goto_root(page, base)
    _chats.open_chat(page, sid)

    banner = page.locator(".chat-health-banner")
    expect(banner).to_contain_text(REASON, timeout=8000)
    expect(page.locator('[data-testid="chat-input"]')).to_be_disabled()
    expect(page.locator('[data-testid="chat-send-btn"]')).to_be_disabled()
    expect(_chats.messages(page, "user")).to_contain_text(["STORED QUESTION"])
    expect(_chats.messages(page, "assistant")).to_contain_text(["STORED ANSWER"])
    assert script.rewritten >= 1


def test_a_start_that_lands_on_build_failed_returns_to_the_pending_chat(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    script = _BuildFailedSocket(empty_history=True)
    script.install(page)
    _nav.goto_root(page, base)
    _chats.start_chat(page, agent)
    page.locator('[data-testid="chat-input"]').fill("hello there")
    page.locator('[data-testid="chat-input"]').press("Enter")

    expect(_chats.messages(page, "system")).to_contain_text([REASON], timeout=8000)
    assert (_chats.session_state(page) or {}).get("name") == "pending"
    expect(_chats.new_chat_state(page)).to_be_visible()
    # The unsent text returns to the box so nothing is lost.
    expect(page.locator('[data-testid="chat-input"]')).to_have_value("hello there")
