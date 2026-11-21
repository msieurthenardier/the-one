"""Chats sends no page context (M36 F3 L4, AC6).

Only the GleepGlorp drawer has a page hook; the Chats instance's ``start_session`` and
``message`` frames carry no ``page`` key at all, whatever route the operator is on.
"""

from __future__ import annotations

import pytest
from browser import _chats, _nav
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser


def test_chats_frames_have_no_page_key(app_with_agent: SeededApp, page: Page) -> None:
    # A plain message frame is `{message}` with no `action`, so every frame is captured and the
    # ones that carry a message are kept.
    all_frames = _chats.chat_frames(page)
    _nav.goto(page, app_with_agent.base_url, "chats")
    _chats.start_chat(page, app_with_agent.agent_name)
    _chats.send_first(page, "first message")
    expect(_chats.messages(page, "assistant").last).to_be_visible(timeout=10000)
    box = page.locator('[data-testid="chat-input"]')
    box.fill("second message")
    box.press("Enter")
    expect(_chats.messages(page, "assistant")).to_have_count(2, timeout=10000)
    page.wait_for_timeout(200)
    frames = [f for f in all_frames if "message" in f]
    assert [f.get("action") for f in frames] == ["start_session", None], frames
    assert [f["message"] for f in frames] == ["first message", "second message"]
    for f in all_frames:
        assert "page" not in f, f
    expect(page.locator('[data-testid="message-context"]')).to_have_count(0)
