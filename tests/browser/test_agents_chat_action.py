"""The agent editor's Chat header action (M25 F4 L6, flight DD8).

Chat (``agent-chat-btn``: ``App.ui.button`` secondary, the ``chat`` icon) sits in
the editor header's ``.form-actions`` before Cancel on a saved agent, and is
absent in create mode. From a clean editor it lands on ``#chats/~new/{name}``
with the pending chat; from a dirty one the router's guard asks once (Stay keeps
the edit and focus returns to Chat; Continue lands on the pending chat). It takes
no part in the Save/Cancel bookkeeping, and it is a deliberate start: a joined
session started from the same agent is not restored instead (the chat area's
pick intent). Chromium; falls in the ``agents`` lane (``test_agents_*``).
"""

from __future__ import annotations

import pytest
from browser import _chats, _lists, _nav
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

CHAT = '[data-testid="agent-chat-btn"]'
DIALOG = '[data-testid="confirm-dialog-overlay"]'
STAY = '[data-testid="modal-cancel-btn"]'
CONTINUE = '[data-testid="modal-confirm-btn"]'

_PENDING_JS = (
    "(agent) => { const a = (App.areas || []).find((x) => x.id === 'chat');"
    " return !!(a && a._sessionState) && a._sessionState().name === 'pending'"
    " && a._sessionState().agent === agent; }"
)


def _open_editor(page: Page, base: str, name: str) -> None:
    _nav.goto(page, base, f"agents/{_nav.seg(name)}")
    expect(page.locator('[data-testid="tab-general"]')).to_be_visible(timeout=8000)
    expect(page.locator(".editor-title")).to_have_text(name, timeout=8000)


def _expect_pending_chat(page: Page, name: str) -> None:
    _nav.expect_route(page, f"chats/~new/{_nav.seg(name)}", timeout=8000)
    page.wait_for_function(_PENDING_JS, arg=name, timeout=8000)
    _chats.expect_chat(page, name, title="New chat")
    expect(_chats.new_chat_state(page)).to_be_visible()


def test_chat_from_a_clean_editor_starts_a_pending_chat(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, name = app_with_agent.base_url, app_with_agent.agent_name
    _open_editor(page, base, name)
    chat = page.locator(CHAT)
    expect(chat).to_have_text("Chat")
    expect(chat).to_have_class("btn-outlined-primary agent-chat-btn")
    expect(chat).to_be_enabled()
    assert chat.evaluate("b => b.type") == "button"
    assert chat.evaluate("b => !!b.querySelector('svg[aria-hidden=\"true\"]')")
    # In the header's actions, after the unsaved caption and before Cancel.
    order = page.evaluate(
        """() => Array.from(document.querySelector('.editor-header .form-actions').children)
             .map((c) => c.getAttribute('data-testid') || c.className)"""
    )
    assert order[:4] == ["editor-unsaved", "agent-chat-btn", "cancel-agent-btn", "save-agent-btn"]
    chat.click()
    expect(page.locator(DIALOG)).to_have_count(0)
    _expect_pending_chat(page, name)


def test_chat_is_absent_in_create_mode(app_with_agent: SeededApp, page: Page) -> None:
    base, name = app_with_agent.base_url, app_with_agent.agent_name
    _nav.goto(page, base, "agents")
    expect(_lists.first_row(page, "agents")).to_be_visible(timeout=8000)
    _lists.agents_new(page)
    expect(page.locator('[data-testid="save-agent-btn"]')).to_be_visible()
    expect(page.locator(CHAT)).to_have_count(0)
    # And back on a saved agent it is there again (re-created per header render).
    _lists.open_item(page, "agents", name)
    expect(page.locator(CHAT)).to_have_count(1)


def test_chat_from_a_dirty_editor_asks_once_stay_then_continue(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, name = app_with_agent.base_url, app_with_agent.agent_name
    _open_editor(page, base, name)
    desc = page.locator('[data-field="description"]')
    desc.fill("an unsaved edit")
    expect(page.locator('[data-testid="editor-unsaved"]')).to_have_text("Unsaved changes")
    chat = page.locator(CHAT)
    expect(chat).to_be_enabled()  # no part in the Save/Cancel bookkeeping
    expect(page.locator('[data-testid="save-agent-btn"]')).to_be_enabled()

    # Stay: the edit is kept, the route is unchanged, focus is back on Chat.
    chat.click()
    expect(page.locator(DIALOG)).to_have_count(1)
    page.locator(STAY).click()
    expect(page.locator(DIALOG)).to_have_count(0)
    _nav.expect_route(page, f"agents/{_nav.seg(name)}/general")
    expect(desc).to_have_value("an unsaved edit")
    expect(page.locator('[data-testid="editor-unsaved"]')).to_have_text("Unsaved changes")
    expect(chat).to_be_focused()

    # Continue: one dialog again, then the pending chat with the agent.
    chat.click()
    expect(page.locator(DIALOG)).to_have_count(1)
    page.locator(CONTINUE).click()
    expect(page.locator(DIALOG)).to_have_count(0)
    _expect_pending_chat(page, name)
    # The edit was discarded, not saved.
    _nav.open_destination(page, "agents")
    expect(page.locator(DIALOG)).to_have_count(0)


def test_chat_is_a_deliberate_start_not_the_rail_restore(
    app_with_agent: SeededApp, page: Page
) -> None:
    """The AC9 rail restore keeps a joined session started from `~new/{agent}`
    when that route is hydrated again with no pick since. Chat carries the
    chat area's pick intent, so it opens a NEW pending chat instead."""
    base, name = app_with_agent.base_url, app_with_agent.agent_name
    _nav.goto(page, base, "chats")
    _chats.start_chat(page, name)
    sid = _chats.send_first(page, "hello")
    assert _chats.session_state(page)["startedFrom"]["agent"] == name
    _open_editor(page, base, name)
    page.locator(CHAT).click()
    _expect_pending_chat(page, name)
    assert _chats.current_session_id(page) is None
    expect(_chats.chat_row(page, sid)).to_be_visible()  # the earlier chat is still listed
