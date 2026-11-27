"""Per-chat drafts (M31 F6 L10c): each conversation keeps its own unsent message-box text and
staged images, in memory for this window.

Falls in the ``chats-transcript`` browser lane.
"""

from __future__ import annotations

import base64

import pytest
from browser import _chats, _nav
from browser.seeders import SeededApp, seed_session
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
INPUT = '[data-testid="chat-input"]'
CHIPS = '[data-testid="chat-attachment"]'
STATUS = '[data-testid="chat-attachments-status"]'


def _png(name: str) -> dict[str, object]:
    return {"name": name, "mimeType": "image/png", "buffer": _PNG}


def _stage_two(page: Page) -> None:
    page.locator('[data-testid="chat-image-input"]').set_input_files(
        files=[_png("a.png"), _png("b.png")]
    )
    expect(page.locator(CHIPS)).to_have_count(2, timeout=5000)


def _two_chats(app: SeededApp, page: Page) -> tuple[str, str]:
    a = seed_session(app.base_url, app.agent_name, "Chat A", "2026-10-01T10:00:00+00:00")
    b = seed_session(app.base_url, app.agent_name, "Chat B", "2026-10-01T09:00:00+00:00")
    _nav.goto_root(page, app.base_url)
    _chats.open_chat(page, a)
    return a, b


def test_draft_follows_its_chat(app_with_agent: SeededApp, page: Page) -> None:
    a, b = _two_chats(app_with_agent, page)
    page.locator(INPUT).fill("draft for A")
    _stage_two(page)
    _chats.open_chat(page, b)
    expect(page.locator(INPUT)).to_have_value("")
    expect(page.locator(CHIPS)).to_have_count(0)
    page.locator(INPUT).fill("draft for B")
    _chats.open_chat(page, a)
    expect(page.locator(INPUT)).to_have_value("draft for A")
    expect(page.locator(CHIPS)).to_have_count(2)
    _chats.open_chat(page, b)
    expect(page.locator(INPUT)).to_have_value("draft for B")
    expect(page.locator(CHIPS)).to_have_count(0)


def test_restore_is_silent_and_moves_no_focus(app_with_agent: SeededApp, page: Page) -> None:
    a, b = _two_chats(app_with_agent, page)
    _stage_two(page)
    page.locator(INPUT).fill("keep")
    status_before = page.locator(STATUS).text_content()
    _chats.open_chat(page, b)
    _chats.open_chat(page, a)
    expect(page.locator(CHIPS)).to_have_count(2)
    assert page.locator(STATUS).text_content() == status_before
    focused = page.evaluate(
        "document.activeElement && document.activeElement.getAttribute('data-testid')"
    )
    assert focused != "chat-input"


def test_sending_clears_the_draft(app_with_agent: SeededApp, page: Page) -> None:
    a, b = _two_chats(app_with_agent, page)
    _chats.send_first(page, "sent from A")
    _chats.open_chat(page, b)
    _chats.open_chat(page, a)
    expect(page.locator(INPUT)).to_have_value("")


def test_pending_draft_survives_a_chat_and_agents(app_with_agent: SeededApp, page: Page) -> None:
    app = app_with_agent
    a = seed_session(app.base_url, app.agent_name, "Chat A", "2026-10-01T10:00:00+00:00")
    _nav.goto_root(page, app.base_url)
    _chats.start_chat(page, app.agent_name)
    expect(page.locator(INPUT)).to_have_value("")
    page.locator(INPUT).fill("pending draft")
    _chats.open_chat(page, a)
    expect(page.locator(INPUT)).to_have_value("")
    _chats.start_chat(page, app.agent_name)
    expect(page.locator(INPUT)).to_have_value("pending draft")
    _nav.open_destination(page, "agents")
    _nav.open_destination(page, "chats")
    expect(page.locator(INPUT)).to_have_value("pending draft")


def test_text_typed_while_starting_survives_promotion(
    app_with_agent: SeededApp, page: Page
) -> None:
    app = app_with_agent
    b = seed_session(app.base_url, app.agent_name, "Chat B", "2026-10-01T09:00:00+00:00")
    _nav.goto_root(page, app.base_url)
    _chats.start_chat(page, app.agent_name)
    box = page.locator(INPUT)
    box.fill("first message")
    # Press Enter and type again in the same tick, while the chat is starting.
    page.evaluate(
        """(sel) => {
          const el = document.querySelector(sel);
          document.querySelector('[data-testid="chat-send-btn"]').click();
          el.value = 'typed while starting';
          el.dispatchEvent(new Event('input', {bubbles: true}));
        }""",
        INPUT,
    )
    sid = None
    for _ in range(40):
        sid = _chats.current_session_id(page)
        if sid:
            break
        page.wait_for_timeout(100)
    assert sid
    page.wait_for_function(_chats._JOINED_ID_JS, arg=sid, timeout=8000)
    _chats.open_chat(page, b)
    _chats.open_chat(page, sid)
    expect(box).to_have_value("typed while starting")


def test_same_id_update_keeps_caret_and_chips(app_with_agent: SeededApp, page: Page) -> None:
    frames = _chats.chat_frames(page, ("join",))
    a, _b = _two_chats(app_with_agent, page)
    box = page.locator(INPUT)
    box.fill("hello world")
    _stage_two(page)
    box.evaluate("el => el.setSelectionRange(3, 3)")
    frames.clear()
    _chats.emit_frame(page, {"type": "session_updated", "session_id": a})
    for _ in range(50):
        if frames:
            break
        page.wait_for_timeout(100)
    assert frames, "no re-join sent"
    page.wait_for_timeout(500)
    expect(box).to_have_value("hello world")
    expect(page.locator(CHIPS)).to_have_count(2)
    assert box.evaluate("el => el.selectionStart") == 3


def test_deleting_the_open_chat_drops_its_draft(app_with_agent: SeededApp, page: Page) -> None:
    a, b = _two_chats(app_with_agent, page)
    page.locator(INPUT).fill("doomed draft")
    row_delete = _chats.chat_row_delete(page, a)
    page.locator("li").filter(has=_chats.chat_row(page, a)).hover()
    row_delete.click()
    row_delete.click()
    expect(_chats.chat_row(page, a)).to_have_count(0, timeout=8000)
    _chats.open_chat(page, b)
    expect(page.locator(INPUT)).to_have_value("")


def test_a_started_pending_chat_leaves_no_draft_behind(
    app_with_agent: SeededApp, page: Page
) -> None:
    app = app_with_agent
    b = seed_session(app.base_url, app.agent_name, "Chat B", "2026-10-01T09:00:00+00:00")
    _nav.goto_root(page, app.base_url)
    _chats.start_chat(page, app.agent_name)
    page.locator(INPUT).fill("stale words")
    _chats.open_chat(page, b)
    _chats.start_chat(page, app.agent_name)
    expect(page.locator(INPUT)).to_have_value("stale words")
    _chats.send_first(page, "go")
    _chats.start_chat(page, app.agent_name)
    expect(page.locator(INPUT)).to_have_value("")


def test_image_attached_in_a_second_pending_chat_after_a_promotion(
    app_with_agent: SeededApp, page: Page
) -> None:
    app = app_with_agent
    _nav.goto_root(page, app.base_url)
    _chats.start_chat(page, app.agent_name)
    _chats.send_first(page, "go")
    _chats.start_chat(page, app.agent_name)
    page.locator('[data-testid="chat-image-input"]').set_input_files(files=[_png("a.png")])
    expect(page.locator(CHIPS)).to_have_count(1, timeout=5000)


def test_a_late_read_from_a_dead_pending_chat_is_dropped(
    app_with_agent: SeededApp, page: Page
) -> None:
    app = app_with_agent
    b = seed_session(app.base_url, app.agent_name, "Chat B", "2026-10-01T09:00:00+00:00")
    _nav.goto_root(page, app.base_url)
    _chats.start_chat(page, app.agent_name)
    # Hold every file read until released, so the read completes after the instance changed.
    page.evaluate(
        """() => {
          window.__held = [];
          var orig = FileReader.prototype.readAsDataURL;
          FileReader.prototype.readAsDataURL = function (f) {
            var self = this;
            var cb = self.onload;
            self.onload = null;
            self.addEventListener('load', function () {
              window.__held.push(function () { cb.call(self); });
            });
            orig.call(self, f);
          };
        }"""
    )
    page.locator('[data-testid="chat-image-input"]').set_input_files(files=[_png("a.png")])
    _chats.open_chat(page, b)
    _chats.start_chat(page, app.agent_name)
    expect(page.locator(CHIPS)).to_have_count(0)
    page.wait_for_timeout(500)
    page.evaluate("() => window.__held.forEach(function (f) { f(); })")
    page.wait_for_timeout(300)
    expect(page.locator(CHIPS)).to_have_count(0)
