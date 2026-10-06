"""Smoke tests for ``tests/browser/_chats.py`` against today's chat surface (M25 F4 L3a).

Every chat-starting browser test goes through ``_chats``; these tests prove each
helper path directly: a start with no chat open, the same agent again, and
another agent. Leg 3b flipped the semantics (a start is a pending chat that
sends only ``leave``; the first send's ``start_session`` creates the session);
leg 4a moved every start onto the agent picker (``start_chat`` -> ``pick``) and
the rows onto the Chats list; leg 4b moved ``expect_chat`` onto the chat
header; these tests keep proving the helpers on each.
Falls in the ``chats`` browser lane.
"""

from __future__ import annotations

import pytest
from browser import _chats, _nav
from browser.seeders import SeededApp, seed_mock_agent
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser


def test_chats_helper_start_paths_rows_and_frames(app_with_provider: SeededApp, page: Page) -> None:
    base = app_with_provider.base_url
    seed_mock_agent(base, app_with_provider.provider_id, name="Alpha")
    seed_mock_agent(base, app_with_provider.provider_id, name="Alpha 2")
    frames = _chats.chat_frames(page, actions=("new_session", "leave", "start_session", "join"))
    _nav.goto(page, base, "chats")
    expect(_chats.welcome(page)).to_be_visible(timeout=8000)
    assert _chats.current_session_id(page) is None
    # The empty state (leg 4b retired the welcome's agent options); the
    # picker's typed "Alpha" lists both agents, A-Z, with Alpha active, and
    # `pick` makes the exact name the active option.
    expect(_chats.empty_new_button(page)).to_be_visible(timeout=8000)
    expect(_chats.new_chat_button(page)).to_have_attribute("data-testid", "chats-new-btn")

    # No chat open: the picker. Since leg 3b a start is a pending chat:
    # no session, the `~new` route, the pending row, nothing sent (nothing was
    # bound, so no `leave`).
    _chats.start_chat(page, "Alpha")
    assert _chats.current_session_id(page) is None
    assert _chats.session_state(page)["name"] == "pending"
    _nav.expect_route(page, "chats/~new/Alpha")
    expect(_chats.welcome(page)).to_be_hidden()
    expect(_chats.pending_row(page)).to_have_count(1)
    expect(_chats.chat_rows(page)).to_have_count(0)
    assert frames == []
    # The same agent again while pending: the same pending chat, nothing sent.
    _chats.start_chat(page, "Alpha")
    assert frames == []
    s1 = _chats.send_first(page, "one")
    _nav.expect_route(page, f"chats/{_nav.seg(s1)}")

    # The same agent again (leg 3a: the header New Chat; leg 4a: the picker).
    _chats.start_chat(page, "Alpha")
    s2 = _chats.send_first(page, "two")
    assert s2 != s1

    # Another agent (leg 3a: the dropdown; leg 4a: the picker, "Alpha 2" typed).
    _chats.start_chat(page, "Alpha 2")
    s3 = _chats.send_first(page, "three")
    assert s3 not in (s1, s2)
    _chats.expect_chat(page, "Alpha 2", title="three")
    starts = [(f["action"], f.get("agent_name"), f.get("session_id")) for f in frames]
    assert starts == [
        ("start_session", "Alpha", s1),
        ("leave", None, None),
        ("start_session", "Alpha", s2),
        ("leave", None, None),
        ("start_session", "Alpha 2", s3),
    ]

    # Rows: one per session; opening one joins it exactly once.
    for sid in (s1, s2, s3):
        expect(_chats.chat_row(page, sid)).to_be_visible(timeout=8000)
    expect(_chats.pending_row(page)).to_have_count(0)
    expect(_chats.chat_row(page, s3)).to_have_attribute("aria-current", "page")
    frames.clear()
    _chats.open_chat(page, s1)
    _chats.expect_chat(page, "Alpha")
    assert [(f["action"], f.get("session_id")) for f in frames] == [("join", s1)]
    expect(_chats.chat_row(page, s1)).to_have_attribute("aria-current", "page")


def test_chats_helper_send_first(app_with_agent: SeededApp, page: Page) -> None:
    _nav.goto(page, app_with_agent.base_url, "chats")
    _chats.start_chat(page, app_with_agent.agent_name)
    sid = _chats.send_first(page, "hello")
    assert sid and sid == _chats.current_session_id(page)
    expect(page.locator('[data-testid="message"].user')).to_have_text("hello")
    expect(page.locator('[data-testid="chat-input"]')).to_have_value("")
    expect(page.locator('[data-testid="message"].assistant')).to_have_text(
        "Mock response from the mock provider.", timeout=10000
    )
