# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""The chat transcript on the control library (M31 F6 L05c, flight DD4, DD7, DD8, DD11, DD15).

The message log is built from ``App.ui.message`` (bubbles and attributions), ``App.ui.thinking``,
``App.ui.trace``, ``App.ui.telemetry`` and ``App.ui.notice``. These tests pin what the migration
changed on the real app page:

* DD11 4 -- no model-loading interval survives a log wipe (and the dots are static under reduced
  motion);
* DD11 5 and 0.3 -- the context-window fetch is keyed on the session and skipped for a deleted agent;
* F1 -- a finished agent reply has one "Copy reply" button that copies its full content;
* B2 -- the thinking disclosure sits above its own iteration's reply, live and on replay;
* B9 -- Stop leaves a "Stopped." line (and "Queued message discarded."), never stored;
* A4 -- an agent error is a danger notice with its raw text under "Technical details";
* A8, A15, A18, B3, B5 -- the approved looks, as computed-style or text assertions.

Falls in the ``chats-transcript`` browser lane.
"""

from __future__ import annotations

import json
import re
import uuid

import httpx
import pytest
from browser import _chats, _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import seed_mock_agent, seed_mock_provider, seed_session
from playwright.sync_api import Page, expect

from the_one.db.codec import encode_messages
from the_one.llm.base import OPERATOR_VISIBILITY, Message, ThinkingBlock, ToolCall, ToolResult

pytestmark = pytest.mark.browser

SEND = '[data-testid="chat-send-btn"]'
STOP = '[data-testid="chat-stop-btn"]'
INPUT = '[data-testid="chat-input"]'
COPY = '[data-testid="message-copy"]'
STOPPED = '[data-testid="chat-stopped"]'
DISCARDED = '[data-testid="chat-discarded"]'
AGENT_ERROR = '[data-testid="chat-agent-error"]'
MESSAGES = ".area-chat .messages"

# Counts the 120 ms dot intervals (the thinking and model-loading dots) that are alive.
_COUNT_INTERVALS = """
(() => {
  const set = window.setInterval, clr = window.clearInterval;
  window.__live = new Set();
  window.setInterval = function (fn, ms, ...rest) {
    const id = set.call(window, fn, ms, ...rest);
    if (ms === 120) window.__live.add(id);
    return id;
  };
  window.clearInterval = function (id) { window.__live.delete(id); return clr.call(window, id); };
})();
"""

_CLIPBOARD_SPY = """() => {
  window.__copied = [];
  Object.defineProperty(navigator, 'clipboard', {configurable: true,
    value: {writeText: (t) => { window.__copied.push(t); return Promise.resolve(); }}});
}"""

# The log's direct children as a compact kind list, in DOM order.
_KINDS_JS = """() => Array.from(document.querySelector('.area-chat .messages').children).map(e => {
  const t = e.getAttribute('data-testid');
  if (t === 'turn-work') return 'work';
  if (t === 'message') {
    const role = e.className.match(/ui-message--(user|assistant|tool|system)/)[1];
    return role + ':' + e.textContent.trim().slice(0, 24);
  }
  if (e.classList.contains('ui-message-attribution')) return 'attr';
  return e.getAttribute('data-testid') || e.className || e.tagName;
})"""

# The items of the log's turn work groups as a compact list, in DOM order (the group is
# collapsed, so textContent, not visible text).
_WORK_ITEMS_JS = """() => Array.from(document.querySelectorAll('[data-testid="turn-work"] [data-kind]')).map(e => {
  const k = e.getAttribute('data-kind');
  if (k === 'thinking') return 'thinking:' + e.textContent.replace('Thinking', '').trim();
  if (k === 'narration') return 'narration:' + e.textContent.trim();
  return 'tool';
})"""

_TELEMETRY_MAX_JS = """() => {
  const el = document.querySelector('[data-testid="chat-telemetry"]');
  const rows = el.querySelectorAll('.ui-telemetry-row');
  return rows[rows.length - 1].querySelector('.ui-telemetry-value').textContent;
}"""


def provider_suffix() -> str:
    return uuid.uuid4().hex[:6]


def _agent(base: str, **config) -> str:
    provider_id = seed_mock_provider(base, name=f"p-{provider_suffix()}", config=config or None)
    return seed_mock_agent(base, provider_id, name=f"a-{provider_suffix()}")


def _joined(page: Page, base: str, agent: str, text: str = "hello") -> None:
    page.goto(base)
    _chats.start_chat(page, agent)
    _chats.send_first(page, text)
    expect(page.locator(SEND)).to_be_enabled(timeout=15000)


def _telemetry_handle(page: Page, js: str):
    return page.evaluate(
        "() => { const h = window.App.areas.find(a => a.id === 'chat')._telemetry();"
        " return (" + js + ")(h); }"
    )


# ── DD11 4: the model-loading interval ─────────────────────────────────────────


def test_model_loading_interval_stops_on_a_log_wipe(app_clean: str, page: Page) -> None:
    page.add_init_script(_COUNT_INTERVALS)
    first = _agent(app_clean)
    second = seed_mock_agent(
        app_clean, seed_mock_provider(app_clean, name="p-other"), name="other-agent"
    )
    _joined(page, app_clean, first)
    assert page.evaluate("() => window.__live.size") == 0
    _chats.emit_frame(page, {"type": "system", "content": "Loading model..."})
    expect(page.locator('[data-testid="model-loading"]')).to_have_text(
        re.compile(r"^Loading model")
    )
    assert page.evaluate("() => window.__live.size") == 1
    # A picker switch wipes the log: nothing may keep ticking.
    _chats.start_chat(page, second)
    page.wait_for_function("() => window.__live.size === 0", timeout=1500)
    expect(page.locator('[data-testid="model-loading"]')).to_have_count(0)


def test_model_loading_dots_are_static_under_reduced_motion(app_clean: str, page: Page) -> None:
    page.emulate_media(reduced_motion="reduce")
    page.add_init_script(_COUNT_INTERVALS)
    _joined(page, app_clean, _agent(app_clean))
    _chats.emit_frame(page, {"type": "system", "content": "Loading model..."})
    loading = page.locator('[data-testid="model-loading"]')
    expect(loading).to_have_text(re.compile(r"^Loading model\s?…$"))
    assert page.evaluate("() => window.__live.size") == 0
    # It settles in place on "Model loaded." (no class query).
    _chats.emit_frame(page, {"type": "system", "content": "Model loaded."})
    expect(page.locator('[data-testid="model-loading"]')).to_have_text("Model loaded.")


def test_the_working_label_and_its_static_dots(app_clean: str, page: Page) -> None:
    """A8: the running work line reads "Working" with the control's dots (static under
    reduced motion)."""
    page.emulate_media(reduced_motion="reduce")
    agent = _agent(app_clean, delay_ms=3000)
    page.goto(app_clean)
    _chats.start_chat(page, agent)
    _chats.send_first(page, "hi")
    working = _chats.working_turns(page)
    expect(working).to_have_count(1, timeout=5000)
    expect(working).to_contain_text("Working")
    assert _chats.turn_name(working) == "Working"


# ── DD11 5 and 0.3: the context-window fetch ───────────────────────────────────


def test_a_late_context_window_response_for_another_session_is_dropped(
    app_clean: str, page: Page
) -> None:
    pa = seed_mock_provider(app_clean, name="pa")
    a = seed_mock_agent(app_clean, pa, name="agent-a")
    b = seed_mock_agent(app_clean, pa, name="agent-b")
    sid_a = seed_session(app_clean, a, "Chat A", "2026-01-02T00:00:00Z")
    sid_b = seed_session(app_clean, b, "Chat B", "2026-01-01T00:00:00Z")
    held: list = []
    seen: list[str] = []

    def handle(route):
        url = route.request.url
        seen.append(url)
        if "/agent-a/" in url:
            held.append(route)  # A's response waits until released
        else:
            route.fulfill(status=404, content_type="application/json", body="{}")

    page.route("**/api/agents/*/context-window", handle)
    page.goto(app_clean)
    _chats.open_chat(page, sid_a)
    page.wait_for_function("() => true")
    expect_wait = 0
    while not held and expect_wait < 50:
        page.wait_for_timeout(100)
        expect_wait += 1
    assert held, "A's context-window request was never made"
    _chats.open_chat(page, sid_b)
    while not any("/agent-b/" in u for u in seen) and expect_wait < 100:
        page.wait_for_timeout(100)
        expect_wait += 1
    held[0].fulfill(
        status=200, content_type="application/json", body=json.dumps({"max_context_tokens": 99000})
    )
    page.wait_for_timeout(400)
    assert page.evaluate(_TELEMETRY_MAX_JS) == "0", "A's late max reached B's readout"


def test_a_deleted_agents_chat_makes_no_context_window_request(app_clean: str, page: Page) -> None:
    """0.3: nothing to fetch for a deleted agent, so no request and no console error."""
    # Sortie 20: deleting an agent deletes its chats, so the deleted-agent state is a chat for a
    # name that never existed.
    sid = seed_session(app_clean, "doomed", "Doomed chat", "2026-01-02T00:00:00Z")
    requests: list[str] = []
    errors: list[str] = []
    page.on(
        "request", lambda req: requests.append(req.url) if "/context-window" in req.url else None
    )
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.goto(app_clean)
    _chats.open_chat(page, sid)
    expect(page.locator(".chat-health-banner")).to_contain_text("deleted", timeout=8000)
    page.wait_for_timeout(500)
    assert requests == []
    assert errors == []


def test_a_restored_count_is_never_zeroed_by_a_zero_maximum(app_clean: str, page: Page) -> None:
    _joined(page, app_clean, _agent(app_clean))
    # The chat's own context-window fetch (the current model's limit, which rightly wins when
    # it lands) must settle before the test injects, or it would overwrite the test's setMax.
    page.wait_for_function(
        "(js) => { const r = eval(js)(); return r !== '0'; }",
        arg=_TELEMETRY_MAX_JS,
        timeout=8000,
    )
    page.evaluate(
        "() => { const t = window.App.areas.find(a => a.id === 'chat')._telemetry();"
        " t.update({input_tokens: 5, output_tokens: 2, context_tokens: 50, max_context_tokens: 0});"
        " t.setMax(100); }"
    )
    expect(_chats.telemetry(page)).to_contain_text("50%")
    assert page.evaluate(_TELEMETRY_MAX_JS) == "100"


# ── F1: Copy reply ──────────────────────────────────────────────────────────────

_CHUNKS = [
    "Here is code:\n\n",
    "```python\nprint('a')\n\nprint('b')\n```\n\n",
    "| h1 | h2 |\n|----|----|\n| a | b |\n\n",
    "done",
]


def test_copy_reply_copies_the_stored_content_live_and_on_replay(
    app_clean: str, page: Page
) -> None:
    agent = _agent(app_clean, stream_chunks=_CHUNKS, delay_ms=350)
    expected = "".join(_CHUNKS)
    page.goto(app_clean)
    _chats.start_chat(page, agent)
    _chats.send_first(page, "go")
    expect(_chats.working_turns(page)).to_have_count(1, timeout=8000)
    expect(_chats.turn_preview(_chats.turn_group(page))).to_contain_text(
        "Here is code", timeout=8000
    )
    # Until the turn ends the text is only a preview: no reply bubble, so no Copy.
    expect(_chats.replies(page)).to_have_count(0)
    expect(page.locator(COPY)).to_have_count(0)
    expect(page.locator(SEND)).to_be_enabled(timeout=15000)
    expect(page.locator(COPY)).to_have_count(1)
    page.evaluate(_CLIPBOARD_SPY)
    page.locator(COPY).click()
    page.wait_for_function("() => window.__copied.length === 1")
    assert page.evaluate("() => window.__copied[0]") == expected
    # A replayed reply has one Copy, with the same text.
    page.reload()
    _chats.expect_chat(page, agent, timeout=10000)
    expect(_chats.messages(page, "assistant").first).to_contain_text("done", timeout=10000)
    expect(page.locator(COPY)).to_have_count(1)
    page.evaluate(_CLIPBOARD_SPY)
    page.locator(COPY).click()
    page.wait_for_function("() => window.__copied.length === 1")
    assert page.evaluate("() => window.__copied[0]") == expected


def _code_copy_announces_outside_the_log(page: Page) -> None:
    code_copy = page.locator(f"{MESSAGES} .markdown-copy-btn")
    expect(code_copy).to_have_count(1)
    # No per-block status node inside the role=log list.
    expect(page.locator(f"{MESSAGES} .markdown-code-wrap [role=status]")).to_have_count(0)
    page.evaluate(_CLIPBOARD_SPY)
    code_copy.click()
    page.wait_for_function("() => window.__copied.length === 1")
    shared = page.locator('[data-testid="chat-copy-status"]')
    expect(shared).to_have_text("Copied")
    assert page.evaluate(
        "() => !document.querySelector('.area-chat .messages').contains("
        "document.querySelector('[data-testid=\"chat-copy-status\"]'))"
    )
    expect(page.locator(f"{MESSAGES} [role=status]")).to_have_count(0)


def test_a_code_block_copy_announces_in_the_shared_node_outside_the_log(
    app_clean: str, page: Page
) -> None:
    agent = _agent(app_clean, stream_chunks=_CHUNKS, delay_ms=50)
    page.goto(app_clean)
    _chats.start_chat(page, agent)
    _chats.send_first(page, "go")
    expect(page.locator(SEND)).to_be_enabled(timeout=15000)
    _code_copy_announces_outside_the_log(page)
    # The same holds for a replayed reply.
    page.reload()
    _chats.expect_chat(page, agent, timeout=10000)
    expect(_chats.messages(page, "assistant").first).to_contain_text("done", timeout=10000)
    _code_copy_announces_outside_the_log(page)


def test_an_empty_reply_has_no_copy_and_delivered_results_have_none(
    app_clean: str, page: Page
) -> None:
    _joined(page, app_clean, _agent(app_clean))
    before = page.locator(COPY).count()
    # A turn whose only text is empty builds no reply, so it has no Copy.
    for f in (
        {"type": "user", "content": "q1"},
        {"type": "assistant", "content": ""},
        {"type": "done"},
    ):
        _chats.emit_frame(page, f)
    expect(_chats.working_turns(page)).to_have_count(0)
    expect(page.locator(COPY)).to_have_count(before)
    # Nor does a whole `assistant` frame before `done`: the reply lands (with its Copy) at `done`.
    for f in ({"type": "user", "content": "q2"}, {"type": "assistant", "content": "filled"}):
        _chats.emit_frame(page, f)
    expect(page.locator(COPY)).to_have_count(before)
    _chats.emit_frame(page, {"type": "done"})
    expect(page.locator(COPY)).to_have_count(before + 1)


def test_a_stopped_turn_keeps_every_received_character_inside_the_group(
    app_clean: str, page: Page
) -> None:
    """Flight DD5: a stop drops no received character. The text goes into the work group (not a
    reply bubble), so there is no Copy; the whole text is there."""
    _joined(page, app_clean, _agent(app_clean))
    text = "x" * 3000
    for f in (
        {"type": "user", "content": "go"},
        {"type": "assistant_chunk", "content": text},
        {"type": "cancelled"},
    ):
        _chats.emit_frame(page, f)
    expect(page.locator(STOPPED)).to_have_count(1)
    group = _chats.turn_group(page)
    assert _chats.turn_state(group) == "stopped"
    assert _chats.turn_texts(group, "narration") == [text]
    # No reply bubble, so no Copy and no second rendering of the text.
    expect(_chats.replies(page).filter(has_text="xxx")).to_have_count(0)
    expect(page.locator(COPY)).to_have_count(1)  # the first turn's reply from `_joined` only


# ── B2: the thinking disclosure above its reply ────────────────────────────────


def test_thinking_work_group_precedes_its_reply_live_and_on_replay(
    app_clean: str, page: Page
) -> None:
    agent = _agent(
        app_clean,
        response={
            "content": "the answer",
            "thinking": [{"type": "thinking", "thinking": "pondering", "signature": "s"}],
        },
    )
    page.goto(app_clean)
    _chats.start_chat(page, agent)
    _chats.send_first(page, "q")
    expect(_chats.messages(page, "assistant")).to_have_count(1, timeout=10000)
    expect(_chats.turn_groups(page)).to_have_count(1, timeout=10000)

    def order() -> list[str]:
        return page.evaluate(_KINDS_JS)

    live = order()
    assert live.index("work") + 1 == live.index("assistant:the answer"), live
    assert page.evaluate(_WORK_ITEMS_JS) == ["thinking:pondering"]
    assert _chats.turn_line(_chats.turn_group(page)) == "Work · thinking"
    page.reload()
    _chats.expect_chat(page, agent, timeout=10000)
    expect(_chats.turn_groups(page)).to_have_count(1, timeout=10000)
    replayed = order()
    assert replayed.index("work") + 1 == replayed.index("assistant:the answer"), replayed
    assert page.evaluate(_WORK_ITEMS_JS) == ["thinking:pondering"]


_ITERATIONS = [
    "user:go",
    "attr",
    "work",
    "assistant:second",
    "attr",
]
# Each pass's thinking sits above that pass's own text; the reply is the last text.
_ITERATION_ITEMS = ["thinking:T1", "narration:first", "tool", "tool", "thinking:T2"]


def test_each_iterations_thinking_sits_above_its_own_narration_live(
    app_clean: str, page: Page
) -> None:
    _joined(page, app_clean, _agent(app_clean))
    frames = [
        {"type": "user", "content": "go"},
        {"type": "assistant", "content": "first"},
        {"type": "thinking", "content": "T1"},
        {
            "type": "tool_call",
            "name": "shell",
            "arguments": {},
            "tool_call_id": "t1",
            "parent_message_id": "p1",
        },
        {
            "type": "tool_result",
            "content": "ok",
            "is_error": False,
            "tool_call_id": "t1",
            "parent_message_id": "p1",
        },
        {"type": "assistant", "content": "second"},
        {"type": "thinking", "content": "T2"},
        {"type": "done"},
    ]
    for f in frames:
        _chats.emit_frame(page, f)
    kinds = page.evaluate(_KINDS_JS)
    assert kinds[kinds.index("user:go") :] == _ITERATIONS, kinds
    assert page.evaluate(_WORK_ITEMS_JS) == _ITERATION_ITEMS


def test_each_iterations_thinking_sits_above_its_own_narration_on_replay(
    app_clean: str, page: Page
) -> None:
    pid = seed_mock_provider(app_clean, name="pr")
    agent = seed_mock_agent(app_clean, pid, name="replayer")
    msgs = [
        Message.user("go"),
        Message.assistant(
            "first",
            tool_calls=[ToolCall(id="t1", name="shell", arguments={})],
            thinking=[ThinkingBlock(type="thinking", thinking="T1", signature="s")],
        ),
        Message.tool(ToolResult(tool_call_id="t1", content="ok", is_error=False)),
        Message.assistant(
            "second", thinking=[ThinkingBlock(type="thinking", thinking="T2", signature="s")]
        ),
    ]
    sid = seed_session(
        app_clean, agent, "Iterations", "2026-01-02T00:00:00Z", messages=encode_messages(msgs)
    )
    page.goto(app_clean)
    _chats.open_chat(page, sid)
    expect(_chats.turn_groups(page)).to_have_count(1, timeout=10000)
    kinds = page.evaluate(_KINDS_JS)
    assert kinds[kinds.index("user:go") :] == _ITERATIONS, kinds
    assert page.evaluate(_WORK_ITEMS_JS) == _ITERATION_ITEMS


# ── B9: Stopped. ────────────────────────────────────────────────────────────────


def _slow_turn(page: Page, base: str) -> None:
    agent = _agent(base, stream_chunks=["alpha ", "beta ", "gamma-FINAL"], delay_ms=700)
    page.goto(base)
    _chats.start_chat(page, agent)
    _chats.send_first(page, "running")
    _wait_running(page)


def _wait_running(page: Page) -> None:
    """The turn is running and its text has begun to arrive (the group's quiet preview)."""
    expect(_chats.working_turns(page)).to_have_count(1, timeout=8000)
    expect(_chats.turn_preview(_chats.turn_group(page))).to_contain_text("alpha", timeout=8000)


def test_stop_shows_stopped_and_a_discarded_held_message(app_clean: str, page: Page) -> None:
    _slow_turn(page, app_clean)
    page.locator(INPUT).fill("held")
    page.locator(INPUT).press("Enter")
    expect(page.locator('[data-testid="pending-queued"]')).to_be_visible(timeout=3000)
    page.locator(STOP).click()
    expect(page.locator(STOPPED)).to_have_text("Stopped.", timeout=8000)
    expect(page.locator(DISCARDED)).to_have_text("Queued message discarded.")
    # Stopped. first, then the discarded line, after the reply.
    kinds = page.evaluate(_KINDS_JS)
    assert kinds[-2:] == ["chat-stopped", "chat-discarded"], kinds
    # A re-join shows neither (neither is stored).
    page.reload()
    expect(page.locator(MESSAGES)).to_be_visible(timeout=10000)
    expect(_chats.messages(page, "user").first).to_be_visible(timeout=10000)
    expect(page.locator(STOPPED)).to_have_count(0)
    expect(page.locator(DISCARDED)).to_have_count(0)


def test_stop_without_a_held_message_shows_only_stopped_and_consumes_the_flag(
    app_clean: str, page: Page
) -> None:
    _slow_turn(page, app_clean)
    page.locator(STOP).click()
    expect(page.locator(STOPPED)).to_have_count(1, timeout=8000)
    expect(page.locator(DISCARDED)).to_have_count(0)
    expect(page.locator(SEND)).to_be_enabled(timeout=8000)
    # A second Stop in a later turn does not inherit anything.
    page.locator(INPUT).fill("again")
    page.locator(INPUT).press("Enter")
    _wait_running(page)
    page.locator(STOP).click()
    expect(page.locator(STOPPED)).to_have_count(2, timeout=8000)
    expect(page.locator(DISCARDED)).to_have_count(0)


def test_a_cancel_from_elsewhere_with_a_held_message_discards_it_too(
    app_clean: str, page: Page
) -> None:
    """A Stop from another tab never ran this tab's click handler: the `cancelled` frame finds
    the held message still present and reports it."""
    _slow_turn(page, app_clean)
    page.locator(INPUT).fill("held")
    page.locator(INPUT).press("Enter")
    expect(page.locator('[data-testid="pending-queued"]')).to_be_visible(timeout=3000)
    _chats.emit_frame(page, {"type": "cancelled"})
    expect(page.locator(STOPPED)).to_have_count(1)
    expect(page.locator(DISCARDED)).to_have_text("Queued message discarded.")


def test_stop_with_several_held_messages_reports_the_count(app_clean: str, page: Page) -> None:
    _slow_turn(page, app_clean)
    for text in ("one", "two"):
        page.locator(INPUT).fill(text)
        page.locator(INPUT).press("Enter")
    expect(page.locator('[data-testid="pending-queued"]')).to_have_count(2, timeout=3000)
    page.locator(STOP).click()
    expect(page.locator(STOPPED)).to_have_text("Stopped.", timeout=8000)
    expect(page.locator(DISCARDED)).to_have_text("2 queued messages discarded.")
    expect(page.locator('[data-testid="pending-queued"]')).to_have_count(0)


def test_an_agent_error_discards_the_whole_queue_and_sends_nothing(
    app_clean: str, page: Page
) -> None:
    _slow_turn(page, app_clean)
    for text in ("one", "two"):
        page.locator(INPUT).fill(text)
        page.locator(INPUT).press("Enter")
    expect(page.locator('[data-testid="pending-queued"]')).to_have_count(2, timeout=3000)
    _chats.emit_frame(page, {"type": "system", "content": "Agent error: boom"})
    expect(page.locator(DISCARDED)).to_have_text("2 queued messages discarded.")
    expect(page.locator('[data-testid="pending-queued"]')).to_have_count(0)
    page.wait_for_timeout(1500)
    expect(_chats.messages(page, "user")).to_have_count(1)


# ── A4: an agent error ──────────────────────────────────────────────────────────


def test_an_agent_error_is_a_danger_notice_with_technical_details(
    app_clean: str, page: Page
) -> None:
    r = httpx.post(
        f"{app_clean}/api/providers",
        json={
            "name": "dead",
            "type": "openai-compatible",
            "base_url": "http://127.0.0.1:1/v1",
            "api_key": "k",
        },
        headers=auth_headers_for(app_clean),
        timeout=5,
    )
    assert r.status_code == 201, r.text
    agent = seed_mock_agent(app_clean, r.json()["id"], name="dead-agent", model="m")
    page.goto(app_clean)
    _chats.start_chat(page, agent)
    _chats.send_first(page, "hello")
    notice = page.locator(AGENT_ERROR)
    expect(notice).to_be_visible(timeout=45000)
    expect(notice).to_contain_text("The agent couldn't finish this reply.")
    assert "ui-notice--danger" in (notice.get_attribute("class") or "")
    details = notice.locator("details")
    assert details.evaluate("el => el.open") is False
    expect(details.locator("summary")).to_have_text("Technical details")
    assert (details.locator(".ui-disclosure-body, div").last.text_content() or "").strip() != ""
    # It is not a system bubble.
    expect(_chats.messages(page, "system").filter(has_text="Agent error")).to_have_count(0)


# ── A15, A18, B3, B5: the approved looks ───────────────────────────────────────


def _seed_operator_session(base: str) -> tuple[str, str]:
    pid = seed_mock_provider(base, name="po")
    agent = seed_mock_agent(base, pid, name="op-agent")
    msgs = [
        Message.user("hello"),
        Message.assistant(
            "checking",
            tool_calls=[ToolCall(id="t1", name="shell", arguments={})],
            visibility=OPERATOR_VISIBILITY,
        ),
        Message.tool(ToolResult(tool_call_id="t1", content="ok", is_error=False)),
        Message.assistant("done", visibility=OPERATOR_VISIBILITY),
    ]
    sid = seed_session(
        base, agent, "Operator chat", "2026-01-02T00:00:00Z", messages=encode_messages(msgs)
    )
    return agent, sid


def test_operator_only_is_a_chip_and_the_work_group_names_its_tool_calls(
    app_clean: str, page: Page
) -> None:
    _, sid = _seed_operator_session(app_clean)
    page.goto(app_clean)
    _chats.open_chat(page, sid)
    chip = page.locator(".ui-message-operator-chip").first
    expect(chip).to_have_text("Operator only", timeout=10000)
    expect(page.locator(MESSAGES)).not_to_contain_text("[operator-only]")
    group = _chats.turn_group(page)
    expect(group).to_have_count(1)
    assert _chats.turn_line(group).startswith("Work · 1 tool call")
    # The group carries the chip for its operator-only items (items do not repeat it).
    assert "Operator only" in (_chats.turn_summary(group).inner_text() or "")
    # The reply is the last text; the earlier text and the tool rows are in the group.
    assert page.evaluate(_WORK_ITEMS_JS) == ["narration:checking", "tool", "tool"]


def test_timestamps_are_full_strength_and_the_telemetry_focus_offset_is_two_pixels(
    app_clean: str, page: Page
) -> None:
    _joined(page, app_clean, _agent(app_clean))
    stamp = page.locator(".ui-message-attribution-ts").first
    assert stamp.evaluate("el => getComputedStyle(el).opacity") == "1"
    offset = page.evaluate(
        """() => {
          const walk = (rules) => {
            for (const r of rules) {
              if (r.selectorText === '.ui-telemetry:focus-visible') return r.style.outlineOffset;
              if (r.cssRules) { const hit = walk(r.cssRules); if (hit) return hit; }
            }
            return null;
          };
          for (const sheet of document.styleSheets) {
            let rules; try { rules = sheet.cssRules; } catch (e) { continue; }
            const hit = walk(rules);
            if (hit) return hit;
          }
          return null;
        }"""
    )
    assert offset == "2px"


# ── M31 F6 L06 (DD8 F2): the step-limit notice ─────────────────────────────────

STEP_LIMIT = '[data-testid="chat-step-limit"]'
STEP_LIMIT_LINK = '[data-testid="chat-step-limit-link"]'
_TOOL_REPLY = {
    "tool_calls": [{"id": "t1", "name": "current_time", "arguments": {}}],
}
_STEP_TEXT = (
    "Stopped: this agent used its 2 steps for this message. "
    "Click Continue or raise max iterations in its settings."
)
_STEP_TEXT_NO_BUTTON = (
    "Stopped: this agent used its 2 steps for this message. "
    "Send another message to continue, or raise max iterations in its settings."
)


def _step_limit_agent(base: str) -> str:
    provider_id = seed_mock_provider(
        base, name=f"p-{provider_suffix()}", config={"response": _TOOL_REPLY}
    )
    return seed_mock_agent(base, provider_id, name=f"sl-{provider_suffix()}", max_iterations=2)


def test_the_step_limit_notice_links_to_the_agent_and_is_not_stored(
    app_clean: str, page: Page
) -> None:
    agent = _step_limit_agent(app_clean)
    _joined(page, app_clean, agent)
    notice = page.locator(STEP_LIMIT)
    expect(notice).to_be_visible(timeout=15000)
    # The Continue button (L10d) sits below the sentence, so its label follows the text.
    expect(notice).to_contain_text(_STEP_TEXT)
    # The button is on its own line below the sentence, centred.
    below = page.evaluate(
        """() => {
          const t = document.querySelector('[data-testid="chat-step-limit"]');
          const b = t.querySelector('[data-testid="chat-step-limit-continue"]');
          const r = b.getBoundingClientRect(), n = t.getBoundingClientRect();
          const l = t.querySelector('a').getBoundingClientRect();
          return [r.top >= l.bottom - 1, Math.abs((r.left + r.right) / 2 - (n.left + n.right) / 2) < 40];
        }"""
    )
    assert below == [True, True]
    assert "ui-notice--muted" in (notice.get_attribute("class") or "")
    link = page.locator(STEP_LIMIT_LINK)
    expect(link).to_have_text("max iterations")
    # After the turn's last tool result, in the log.
    assert page.evaluate(_KINDS_JS)[-1] == "chat-step-limit"
    # Not stored: a re-join renders none.
    page.reload()
    expect(page.locator(MESSAGES)).to_be_visible(timeout=10000)
    expect(_chats.messages(page, "user").first).to_be_visible(timeout=10000)
    expect(page.locator(STEP_LIMIT)).to_have_count(0)


def test_the_step_limit_link_goes_to_the_agent_settings(app_clean: str, page: Page) -> None:
    agent = _step_limit_agent(app_clean)
    _joined(page, app_clean, agent)
    page.locator(STEP_LIMIT_LINK).click()
    _nav.expect_route(page, f"agents/{_nav.seg(agent)}/general")


def test_the_step_limit_notice_for_a_deleted_agent_is_plain_text(
    app_clean: str, page: Page
) -> None:
    # Sortie 20: a deleted agent's chats are deleted with it, so the chat is for a name that never
    # existed; the notice is driven by a frame, as the real agent is not needed.
    sid = seed_session(
        app_clean,
        "gone-agent",
        "Gone chat",
        "2026-01-02T00:00:00Z",
        messages=[{"role": "user", "content": "hello"}],
    )
    page.goto(app_clean)
    _chats.open_chat(page, sid)
    expect(_chats.messages(page, "user").first).to_be_visible(timeout=10000)
    expect(page.locator(INPUT)).to_be_disabled()
    page.evaluate(
        """async () => {
          App.store.invalidate('agents');
          await App.store.get('agents', {force: true});
          App.areas.find(a => a.id === 'chat')._turnFrames().handle({type: 'step_limit', steps: 2});
        }"""
    )
    last = page.locator(STEP_LIMIT).last
    # The chat is blocked (no Continue button), so the notice carries the no-button sentence.
    expect(last).to_have_text(_STEP_TEXT_NO_BUTTON)
    expect(last.locator("a")).to_have_count(0)


# ── M31 F6 L10d: the step-limit notice's Continue button ───────────────────────

CONTINUE = '[data-testid="chat-step-limit-continue"]'


def _user_texts(page: Page) -> list[str]:
    return page.evaluate(
        """() => Array.from(document.querySelectorAll('.area-chat .ui-message--user'))
            .map(e => e.textContent.trim())"""
    )


def test_continue_sends_exactly_one_message_and_the_button_goes(app_clean: str, page: Page) -> None:
    agent = _step_limit_agent(app_clean)
    _joined(page, app_clean, agent)
    btn = page.locator(CONTINUE)
    expect(btn).to_have_count(1, timeout=15000)
    expect(btn).to_have_text("Continue")
    assert btn.evaluate("e => e.tagName") == "BUTTON"
    btn.click()
    # The agent's next turn runs and hits the limit again: the first notice stays in the log with
    # its button gone (a notice is never removed except by a log wipe), and the second notice
    # carries the one fresh button. Wait for the second notice; a count of 1 would also match the
    # moment before it renders (squawk 0305).
    expect(_chats.messages(page, "user").nth(1)).to_have_text("continue", timeout=10000)
    expect(page.locator(STEP_LIMIT)).to_have_count(2, timeout=15000)
    expect(page.locator(CONTINUE)).to_have_count(1, timeout=15000)
    expect(page.locator(STEP_LIMIT).last.locator(CONTINUE)).to_have_count(1)
    expect(page.locator(STEP_LIMIT).first.locator(CONTINUE)).to_have_count(0)
    assert _user_texts(page).count("continue") == 1
    assert len(_user_texts(page)) == 2


def test_a_double_click_on_continue_sends_once(app_clean: str, page: Page) -> None:
    agent = _step_limit_agent(app_clean)
    _joined(page, app_clean, agent)
    btn = page.locator(CONTINUE)
    expect(btn).to_have_count(1, timeout=15000)
    btn.dblclick(force=True)
    # The old notice stays and the second turn adds one (squawk 0305).
    expect(page.locator(STEP_LIMIT)).to_have_count(2, timeout=15000)
    expect(page.locator(CONTINUE)).to_have_count(1, timeout=15000)
    assert _user_texts(page).count("continue") == 1


def test_continue_keeps_the_draft_and_focuses_the_message_box(app_clean: str, page: Page) -> None:
    agent = _step_limit_agent(app_clean)
    _joined(page, app_clean, agent)
    expect(page.locator(CONTINUE)).to_have_count(1, timeout=15000)
    page.locator(INPUT).fill("my draft")
    page.locator(CONTINUE).click()
    expect(page.locator(INPUT)).to_be_focused()
    expect(page.locator(INPUT)).to_have_value("my draft")


def test_a_frame_from_elsewhere_or_a_typed_message_removes_the_button(
    app_clean: str, page: Page
) -> None:
    agent = _step_limit_agent(app_clean)
    _joined(page, app_clean, agent)
    expect(page.locator(CONTINUE)).to_have_count(1, timeout=15000)
    page.evaluate(
        """() => App.areas.find(a => a.id === 'chat')._turnFrames()
            .handle({type: 'user', content: 'from another tab'})"""
    )
    expect(page.locator(CONTINUE)).to_have_count(0)
    # The notice text stays.
    expect(page.locator(STEP_LIMIT)).to_have_count(1)


def test_a_blocked_chat_renders_no_continue_button(app_clean: str, page: Page) -> None:
    # Sortie 20: a deleted agent's chats are deleted with it, so the blocked chat is one for a
    # name that never existed.
    sid = seed_session(
        app_clean,
        "gone-agent",
        "Gone chat",
        "2026-01-02T00:00:00Z",
        messages=[{"role": "user", "content": "hello"}],
    )
    page.goto(app_clean)
    _chats.open_chat(page, sid)
    expect(_chats.messages(page, "user").first).to_be_visible(timeout=10000)
    expect(page.locator(INPUT)).to_be_disabled()
    page.evaluate(
        """() => App.areas.find(a => a.id === 'chat')._turnFrames()
            .handle({type: 'step_limit', steps: 2})"""
    )
    expect(page.locator(STEP_LIMIT)).to_have_count(1)
    expect(page.locator(CONTINUE)).to_have_count(0)
    expect(page.locator(STEP_LIMIT)).to_have_text(_STEP_TEXT_NO_BUTTON)


def test_no_continue_button_when_a_message_is_queued(app_clean: str, page: Page) -> None:
    provider_id = seed_mock_provider(
        app_clean,
        name=f"p-{provider_suffix()}",
        config={"response": _TOOL_REPLY, "delay_ms": 600},
    )
    agent = seed_mock_agent(
        app_clean, provider_id, name=f"sl-{provider_suffix()}", max_iterations=2
    )
    page.goto(app_clean)
    _chats.start_chat(page, agent)
    _chats.send_first(page, "go")
    page.locator(INPUT).fill("held")
    page.locator(INPUT).press("Enter")
    expect(page.locator('[data-testid="pending-queued"]')).to_be_visible(timeout=3000)
    expect(page.locator(STEP_LIMIT).first).to_be_visible(timeout=15000)
    expect(page.locator(CONTINUE)).to_have_count(0)
    expect(page.locator(STEP_LIMIT).first).to_have_text(_STEP_TEXT_NO_BUTTON)
