"""One work group per chat turn (sortie 16 L02, flight DD2-DD9): the chat module
``areas/chat/turn-work.js`` on the live frames and on replay.

Live turns are scripted with ``_chats.emit_frame`` (the real ``ws.onmessage`` path); replay
shapes are seeded sessions or a join whose history the socket script rewrites. Each test
asserts the whole shape of the turn, including what must be absent: no assistant bubble
before ``done``, never two groups, never a second reply.

Covers flow items 1 to 5, 8, 10, 11, 12, 13 and 16; the rest are leg 3 (turn-work-tests).
"""

from __future__ import annotations

import json

import pytest
from browser import _chats, _nav
from browser.seeders import SeededApp, seed_session
from playwright.sync_api import Page, expect

from the_one.db.codec import encode_messages
from the_one.llm.base import Message, ThinkingBlock, ToolCall, ToolResult

pytestmark = pytest.mark.browser

INPUT = '[data-testid="chat-input"]'
STOP = '[data-testid="chat-stop-btn"]'
STOPPED = '[data-testid="chat-stopped"]'

TOOL_CALL = {
    "type": "tool_call",
    "name": "shell",
    "arguments": {"command": "ls"},
    "tool_call_id": "t1",
    "parent_message_id": "pm-1",
}
TOOL_RESULT = {
    "type": "tool_result",
    "content": "ok",
    "is_error": False,
    "tool_call_id": "t1",
    "parent_message_id": "pm-1",
}
AUTH = {
    "type": "auth_required",
    "source_id": "src-1",
    "source_name": "Goldfinch",
    "tool_call_id": "t1",
    "consent_url": None,
    "parent_message_id": "pm-1",
}


class _Script:
    """Connects the page's socket to the real server, then rewrites each ``session_joined``
    (``history``: the events to show, ``processing``: its ``is_processing``) and, with
    ``swallow``, drops every ``message`` the page sends so no turn really runs."""

    def __init__(
        self,
        history: list[dict] | None = None,
        processing: bool = False,
        swallow: bool = False,
    ) -> None:
        self.history = history
        self.processing = processing
        self.swallow = swallow

    def install(self, page: Page) -> None:
        page.route_web_socket("**/ws", self._on_connect)

    def _on_connect(self, ws) -> None:
        server = ws.connect_to_server()
        server.on_message(lambda message: ws.send(self._rewrite(message)))
        ws.on_message(lambda message: self._from_page(server, message))

    def _rewrite(self, message):
        try:
            data = json.loads(message)
        except (TypeError, ValueError):
            return message
        if not isinstance(data, dict) or data.get("type") != "session_joined":
            return message
        if self.history is not None:
            data["history"] = self.history
        if self.processing:
            data["is_processing"] = True
        return json.dumps(data)

    def _from_page(self, server, message) -> None:
        try:
            data = json.loads(message)
        except (TypeError, ValueError):
            data = None
        if self.swallow and isinstance(data, dict) and "message" in data:
            return
        server.send(message)


def _open(
    page: Page,
    app: SeededApp,
    script: _Script | None = None,
    messages: list[Message] | None = None,
) -> str:
    """Open a joined chat (an empty seeded session, or one holding ``messages``)."""
    sid = seed_session(
        app.base_url,
        app.agent_name,
        "Work chat",
        "2026-01-02T00:00:00Z",
        messages=encode_messages(messages) if messages else None,
    )
    if script is not None:
        script.install(page)
    _nav.goto_root(page, app.base_url)
    _chats.open_chat(page, sid)
    return sid


def _frames(page: Page, *frames: dict) -> None:
    for f in frames:
        _chats.emit_frame(page, f)


def _user(text: str) -> dict:
    return {"type": "user", "content": text}


def _chunk(text: str) -> dict:
    return {"type": "assistant_chunk", "content": text}


def _text(text: str) -> dict:
    return {"type": "assistant", "content": text}


def _thinking(text: str) -> dict:
    return {"type": "thinking", "content": text}


DONE = {"type": "done"}

# The same multi-pass turn, live and stored: thinking above its pass's text; the last text is
# the reply.
_ITEMS = ["thinking:T1", "narration:Let me look.", "tool", "tool"]


# ── 1 and 2: a multi-pass turn, live and after a reload ───────────────────────


def test_a_multi_pass_turn_live_is_one_group_and_one_reply(
    app_with_agent: SeededApp, page: Page
) -> None:
    _open(page, app_with_agent)
    _frames(page, _user("go"), _chunk("Let me "), _chunk("look."))
    expect(_chats.working_turns(page)).to_have_count(1)
    group = _chats.turn_group(page)
    # The pending text is a quiet preview; there is no reply bubble yet.
    expect(_chats.turn_preview(group)).to_be_visible()
    expect(_chats.turn_preview(group)).to_contain_text("Let me look.")
    expect(_chats.replies(page)).to_have_count(0)

    _frames(page, _thinking("T1"), TOOL_CALL)
    expect(_chats.turn_groups(page)).to_have_count(1)
    line = _chats.turn_line(group)
    assert "Working" in line and "1 tool call" in line and "shell" in line, line
    expect(_chats.turn_preview(group)).to_be_hidden()
    _frames(page, TOOL_RESULT)
    assert "shell" not in _chats.turn_line(group)

    _frames(page, _chunk("All "), _chunk("done."))
    expect(_chats.turn_preview(group)).to_contain_text("All done.")
    expect(_chats.replies(page)).to_have_count(0)

    _frames(page, DONE)
    expect(_chats.replies(page)).to_have_text(["All done."])
    expect(_chats.turn_groups(page)).to_have_count(1)
    assert _chats.turn_state(group) == "done"
    assert _chats.turn_line(group) == "Work · 1 tool call"
    expect(_chats.turn_preview(group)).to_be_hidden()
    assert _chats.turn_item_list(group) == _ITEMS
    assert not _chats.turn_is_open(group)
    # The reply comes after the group in the log.
    order = page.evaluate(
        """() => Array.from(document.querySelectorAll(
          '.area-chat .messages > [data-testid="turn-work"],'
          + ' .area-chat .messages > .ui-message--assistant'
        )).map(e => e.getAttribute('data-testid') === 'turn-work' ? 'work' : 'reply')"""
    )
    assert order == ["work", "reply"]


def test_the_same_turn_after_a_reload_has_the_same_shape(
    app_with_agent: SeededApp, page: Page
) -> None:
    msgs = [
        Message.user("go"),
        Message.assistant(
            "Let me look.",
            tool_calls=[ToolCall(id="t1", name="shell", arguments={"command": "ls"})],
            thinking=[ThinkingBlock(type="thinking", thinking="T1", signature="s")],
        ),
        Message.tool(ToolResult(tool_call_id="t1", content="ok", is_error=False)),
        Message.assistant("All done."),
    ]
    _open(page, app_with_agent, messages=msgs)
    expect(_chats.replies(page)).to_have_text(["All done."])
    expect(_chats.turn_groups(page)).to_have_count(1)
    group = _chats.turn_group(page)
    assert _chats.turn_state(group) == "done"
    assert _chats.turn_line(group) == "Work · 1 tool call"
    assert _chats.turn_item_list(group) == _ITEMS
    assert not _chats.turn_is_open(group)
    expect(_chats.turn_preview(group)).to_be_hidden()


# ── 3 and 4: a turn that ends on a tool call; plain and thinking-only replies ──


def test_a_turn_that_ends_on_a_tool_call_makes_its_last_text_the_reply(
    app_with_agent: SeededApp, page: Page
) -> None:
    _open(page, app_with_agent)
    _frames(page, _user("go"), _chunk("Checking now."), TOOL_CALL, TOOL_RESULT)
    # Still working: the text is narration, not a reply.
    expect(_chats.replies(page)).to_have_count(0)
    _frames(page, DONE)
    expect(_chats.replies(page)).to_have_text(["Checking now."])
    group = _chats.turn_group(page)
    expect(_chats.turn_groups(page)).to_have_count(1)
    # The text moved out of the group: it is the reply only (no duplicate narration).
    assert _chats.turn_item_list(group) == ["tool", "tool"]
    assert _chats.turn_line(group) == "Work · 1 tool call"


def test_a_plain_reply_has_no_work_line_and_thinking_only_reads_work_thinking(
    app_with_agent: SeededApp, page: Page
) -> None:
    _open(page, app_with_agent)
    _frames(page, _user("hi"), _chunk("hello"))
    # While it streams the line is running; the reply lands whole at done.
    expect(_chats.working_turns(page)).to_have_count(1)
    expect(_chats.replies(page)).to_have_count(0)
    _frames(page, DONE)
    expect(_chats.replies(page)).to_have_text(["hello"])
    expect(_chats.turn_groups(page)).to_have_count(0)

    _frames(page, _user("again"), _thinking("ponder"), _chunk("ok"), DONE)
    expect(_chats.replies(page)).to_have_text(["hello", "ok"])
    expect(_chats.turn_groups(page)).to_have_count(1)
    group = _chats.turn_group(page)
    assert _chats.turn_line(group) == "Work · thinking"
    assert _chats.turn_item_list(group) == ["thinking:ponder"]


# ── 5: Stopped ────────────────────────────────────────────────────────────────


def test_a_stopped_turn_keeps_its_text_in_the_group_and_builds_no_reply(
    app_with_agent: SeededApp, page: Page
) -> None:
    _open(page, app_with_agent)
    _frames(
        page,
        _user("go"),
        _chunk("part one"),
        TOOL_CALL,
        TOOL_RESULT,
        _chunk("partial two"),
        {"type": "cancelled"},
    )
    expect(page.locator(STOPPED)).to_have_text("Stopped.")
    expect(_chats.replies(page)).to_have_count(0)
    expect(_chats.turn_groups(page)).to_have_count(1)
    group = _chats.turn_group(page)
    assert _chats.turn_state(group) == "stopped"
    assert _chats.turn_line(group) == "Stopped · 1 tool call"
    assert _chats.turn_item_list(group) == [
        "narration:part one",
        "tool",
        "tool",
        "narration:partial two",
    ]
    # No running dots or preview remain.
    expect(_chats.working_turns(page)).to_have_count(0)
    expect(_chats.turn_preview(group)).to_be_hidden()


# ── 8: a validation error and /reset remove the empty group ───────────────────


@pytest.mark.parametrize("content", ["Context cleared.", "Message rejected: too long."])
def test_a_turn_ending_system_frame_removes_the_empty_group(
    app_with_agent: SeededApp, page: Page, content: str
) -> None:
    _open(page, app_with_agent, _Script(swallow=True))
    page.locator(INPUT).fill("go")
    page.locator(INPUT).press("Enter")
    # The send opened the running line (nothing reached the server).
    expect(_chats.working_turns(page)).to_have_count(1)
    expect(page.locator(STOP)).to_be_visible()
    _frames(page, {"type": "system", "content": content})
    expect(_chats.turn_groups(page)).to_have_count(0)
    expect(page.locator(STOP)).to_be_hidden()
    expect(_chats.messages(page, "system")).to_contain_text([content])


# ── 10: sign-in pause ─────────────────────────────────────────────────────────


def test_a_sign_in_pause_keeps_one_group_and_ends_with_one_reply(
    app_with_agent: SeededApp, page: Page
) -> None:
    _open(page, app_with_agent)
    _frames(page, _user("go"), _chunk("I will call it."), TOOL_CALL, AUTH)
    group = _chats.turn_group(page)
    expect(_chats.turn_groups(page)).to_have_count(1)
    assert _chats.turn_state(group) == "sign-in"
    assert _chats.turn_line(group) == "Waiting for sign-in · 1 tool call"
    # The sign-in block is the group's next sibling, never inside it; no reply was built.
    expect(page.locator('[data-testid="turn-work"] + .login-required-group')).to_have_count(1)
    expect(page.locator('[data-testid="turn-work"] .login-required-group')).to_have_count(0)
    expect(_chats.replies(page)).to_have_count(0)
    # The latest narration stays plain: the turn may resume.
    assert _chats.turn_item_list(group) == ["narration:I will call it.", "tool"]

    _frames(page, {"type": "auth_resolved", "source_id": "src-1"})
    assert _chats.turn_state(group) == "working"
    _frames(page, TOOL_RESULT, _chunk("Signed in and done."), DONE)
    expect(_chats.turn_groups(page)).to_have_count(1)
    expect(_chats.replies(page)).to_have_text(["Signed in and done."])
    assert _chats.turn_state(group) == "done"
    assert _chats.turn_item_list(group) == ["narration:I will call it.", "tool", "tool"]


# ── 11 to 13: joins (the trailing turn) ───────────────────────────────────────

_PAUSED = [
    {"type": "user", "content": "go", "source": "restored"},
    {"type": "assistant", "content": "Calling it."},
    {
        "type": "tool_call",
        "name": "shell",
        "arguments": {"command": "ls"},
        "tool_call_id": "t1",
        "parent_message_id": "replay-msg-1",
    },
]


def test_a_join_on_a_paused_turn_reopens_it_and_ends_with_one_reply(
    app_with_agent: SeededApp, page: Page
) -> None:
    _open(page, app_with_agent, _Script(history=_PAUSED))
    # Replay closed the turn, as for any finished one.
    expect(_chats.replies(page)).to_have_text(["Calling it."])
    # The server then replays the cached auth_required: the turn is open again, without a reply.
    _frames(page, AUTH)
    expect(_chats.replies(page)).to_have_count(0)
    expect(_chats.turn_groups(page)).to_have_count(1)
    group = _chats.turn_group(page)
    assert _chats.turn_state(group) == "sign-in"
    assert _chats.turn_line(group) == "Waiting for sign-in · 1 tool call"
    expect(page.locator('[data-testid="turn-work"] + .login-required-group')).to_have_count(1)

    _frames(
        page,
        {"type": "auth_resolved", "source_id": "src-1"},
        TOOL_RESULT,
        _chunk("Finished."),
        DONE,
    )
    expect(_chats.replies(page)).to_have_text(["Finished."])
    expect(_chats.turn_groups(page)).to_have_count(1)
    assert _chats.turn_state(_chats.turn_group(page)) == "done"
    assert _chats.turn_item_list(_chats.turn_group(page)) == [
        "narration:Calling it.",
        "tool",
        "tool",
    ]


def test_a_join_during_a_resume_continues_the_turn_in_one_group(
    app_with_agent: SeededApp, page: Page
) -> None:
    # The join reports no turn in flight (the resume takes no session lock), then the resumed
    # turn's frames arrive live with no `user` frame before them.
    _open(page, app_with_agent, _Script(history=_PAUSED))
    expect(_chats.replies(page)).to_have_text(["Calling it."])
    _frames(page, TOOL_RESULT, _text("Second."), DONE)
    expect(_chats.turn_groups(page)).to_have_count(1)
    expect(_chats.replies(page)).to_have_text(["Second."])
    group = _chats.turn_group(page)
    assert _chats.turn_state(group) == "done"
    assert _chats.turn_item_list(group) == ["narration:Calling it.", "tool", "tool"]


def test_a_join_while_a_turn_runs_leaves_the_trailing_turn_working(
    app_with_agent: SeededApp, page: Page
) -> None:
    history = _PAUSED + [
        {
            "type": "tool_result",
            "content": "ok",
            "is_error": False,
            "tool_call_id": "t1",
            "parent_message_id": "replay-msg-1",
        }
    ]
    _open(page, app_with_agent, _Script(history=history, processing=True))
    expect(_chats.working_turns(page)).to_have_count(1)
    group = _chats.turn_group(page)
    expect(_chats.turn_groups(page)).to_have_count(1)
    # No reply bubble: the text so far is the latest narration, shown as it was written.
    expect(_chats.replies(page)).to_have_count(0)
    assert "1 tool call" in _chats.turn_line(group)
    assert _chats.turn_item_list(group) == ["narration:Calling it.", "tool", "tool"]
    expect(page.locator(STOP)).to_be_visible()

    # Live frames continue the same group.
    _frames(page, _chunk("Final answer."), DONE)
    expect(_chats.turn_groups(page)).to_have_count(1)
    expect(_chats.replies(page)).to_have_text(["Final answer."])
    assert _chats.turn_state(group) == "done"
    assert _chats.turn_item_list(group) == ["narration:Calling it.", "tool", "tool"]


# ── 16: "Loading model" never makes a second group ────────────────────────────


def test_loading_model_on_a_fresh_turn_keeps_one_group(
    app_with_agent: SeededApp, page: Page
) -> None:
    _open(page, app_with_agent, _Script(swallow=True))
    page.locator(INPUT).fill("go")
    page.locator(INPUT).press("Enter")
    expect(_chats.working_turns(page)).to_have_count(1)
    _frames(page, {"type": "system", "content": "Loading model..."})
    # The empty running line gives way to the loading line.
    expect(page.locator('[data-testid="model-loading"]')).to_be_visible()
    expect(_chats.turn_groups(page)).to_have_count(1)
    expect(_chats.turn_group(page)).to_be_hidden()
    _frames(page, {"type": "system", "content": "Model loaded."})
    expect(page.locator('[data-testid="model-loading"]')).to_have_text("Model loaded.")
    expect(_chats.turn_groups(page)).to_have_count(1)
    expect(_chats.working_turns(page)).to_be_visible()
    _frames(page, _chunk("hello"), DONE)
    expect(_chats.replies(page)).to_have_text(["hello"])
    expect(_chats.turn_groups(page)).to_have_count(0)


def test_loading_model_on_a_resume_keeps_one_group(app_with_agent: SeededApp, page: Page) -> None:
    _open(page, app_with_agent, _Script(history=_PAUSED))
    _frames(page, AUTH, {"type": "auth_resolved", "source_id": "src-1"})
    expect(_chats.turn_groups(page)).to_have_count(1)
    # The resume loads the model: a group that already has items is never hidden or replaced.
    _frames(page, {"type": "system", "content": "Loading model..."})
    expect(page.locator('[data-testid="model-loading"]')).to_be_visible()
    expect(_chats.turn_groups(page)).to_have_count(1)
    expect(_chats.turn_group(page)).to_be_visible()
    _frames(page, {"type": "system", "content": "Model loaded."})
    expect(_chats.turn_groups(page)).to_have_count(1)
    _frames(page, TOOL_RESULT, _chunk("Resumed."), DONE)
    expect(_chats.turn_groups(page)).to_have_count(1)
    expect(_chats.replies(page)).to_have_text(["Resumed."])
