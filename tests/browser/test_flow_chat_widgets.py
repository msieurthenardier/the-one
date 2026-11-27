# ruff: noqa: E501  (inline JS snippets and widget sources are evaluated verbatim)
"""Browser flow tests for widgets in chat (M35 F2 L6, flight DD1, DD7, DD9, DD12, DD17).

A ``widget`` fenced block in an assistant reply is a managed ``App.ui.widget`` card, mounted when
the reply lands at ``done`` (sortie 16: while the turn runs the work group's preview reads
"Building a widget" and the block's source is nowhere in the log) and in history. Assertions are
structural; no pixels. Chromium. The ``chats-widgets`` lane.
"""

from __future__ import annotations

import json

import pytest
from browser import _chats, _nav
from browser.seeders import seed_mock_agent, seed_mock_provider, seed_session
from browser.test_flow_chat_turn_work import (
    DONE,
    TOOL_CALL,
    TOOL_RESULT,
    _chunk,
    _frames,
    _Script,
    _text,
    _user,
)
from playwright.sync_api import Page, expect

from the_one.db.codec import encode_messages
from the_one.llm.base import Message

pytestmark = pytest.mark.browser

CARD = '[data-testid="chat-widget"]'
FRAME = '[data-testid="chat-widget-frame"]'
NOTICE = '[data-testid="chat-widget-notice"]'
SEND = '[data-testid="chat-send-btn"]'

# A 300 px counter widget: the counter proves it runs.
CTR = '<div style="height:300px">w</div><script>window.__n = 0; setInterval(function () { window.__n++; }, 20);</script>'
CTR2 = '<div style="height:300px">second</div><script>window.__n = 0; setInterval(function () { window.__n++; }, 20);</script>'
CHART = json.dumps({"type": "line", "x": {"values": [1, 2, 3]}, "series": [{"values": [3, 5, 4]}]})


def _widget(src: str = CTR) -> str:
    return "```widget\n" + src + "\n```\n"


def _chunks(text: str, size: int) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]


def _provider_agent(base: str, config: dict, name: str = "test-agent") -> str:
    provider_id = seed_mock_provider(base, name=f"mock-{name}", config=config)
    return seed_mock_agent(base, provider_id, name=name)


def _reply(page: Page, base: str, text: str) -> str:
    """A non-streamed reply: the mock answers with *text*. Returns the agent name."""
    agent = _provider_agent(base, {"response": {"content": text}})
    _nav.goto_root(page, base)
    _chats.start_chat(page, agent)
    _chats.send_first(page, "go")
    expect(page.locator(SEND)).to_be_enabled(timeout=15000)
    return agent


def _stream(page: Page, base: str, chunks: list[str], delay_ms: int) -> str:
    agent = _provider_agent(base, {"stream_chunks": chunks, "delay_ms": delay_ms})
    _nav.goto_root(page, base)
    _chats.start_chat(page, agent)
    return agent


def _done(page: Page, timeout: float = 30000) -> None:
    expect(_chats.messages(page, "assistant").first).to_be_visible(timeout=timeout)
    expect(page.locator(SEND)).to_be_enabled(timeout=timeout)


def _frame_n(page: Page, i: int = 0) -> int:
    handle = page.locator(CARD).nth(i).locator("iframe").element_handle()
    f = handle.content_frame()
    assert f is not None
    return int(f.evaluate("() => window.__n"))


def _keys(page: Page) -> list[str]:
    return page.evaluate(
        "() => Array.from(document.querySelectorAll('[data-testid=\"chat-widget\"]')).map((c) => c.getAttribute('data-widget-key'))"
    )


def _seed_history(base: str, agent: str, replies: list[str], title: str = "hist") -> str:
    msgs: list[Message] = []
    for r in replies:
        msgs.append(Message.user("show"))
        msgs.append(Message.assistant(r))
    return seed_session(
        base,
        agent,
        title,
        "2026-10-27T09:00:00+00:00",
        messages=encode_messages(msgs),
    )


def _open_seeded(page: Page, base: str, sid: str) -> None:
    page.set_viewport_size({"width": 1440, "height": 900})
    _nav.goto(page, base, "chats")
    _chats.open_chat(page, sid)


# ── AC1: rendering ────────────────────────────────────────────────────────────


def test_a_non_streamed_widget_reply_runs_and_shows_its_exact_source(
    app_clean: str, page: Page
) -> None:
    text = "Here it is:\n\n" + _widget() + "\nEnjoy."
    agent = _reply(page, app_clean, text)
    card = page.locator(CARD)
    expect(card).to_have_count(1)
    expect(card.locator(".ui-widget-by")).to_have_text(f"Widget by {agent}")
    expect(page.locator(FRAME)).to_have_count(1, timeout=10000)
    a = _frame_n(page)
    page.wait_for_timeout(300)
    assert _frame_n(page) > a
    page.locator('[data-testid="chat-widget-source-details"] summary').click()
    expect(page.locator('[data-testid="chat-widget-source"]')).to_contain_text("setInterval")
    shown = page.evaluate(
        "() => document.querySelector('[data-testid=\"chat-widget-source\"]').textContent"
    )
    assert CTR in shown


def test_a_widget_and_a_chart_in_one_reply_show_both(app_clean: str, page: Page) -> None:
    text = "Both:\n\n" + _widget() + "\n```chart\n" + CHART + "\n```\n\nEnd.\n"
    _reply(page, app_clean, text)
    expect(page.locator(CARD)).to_have_count(1)
    expect(page.locator('[data-testid="chat-chart"]')).to_have_count(1)


def test_html_and_javascript_blocks_stay_code_blocks(app_clean: str, page: Page) -> None:
    text = "```html\n<b>x</b>\n```\n\n```javascript\nwindow.x = 1;\n```\n"
    _reply(page, app_clean, text)
    expect(page.locator(CARD)).to_have_count(0)
    expect(page.locator("iframe")).to_have_count(0)
    bubble = _chats.messages(page, "assistant").last
    expect(bubble).to_contain_text("<b>x</b>")
    expect(bubble).to_contain_text("window.x = 1;")


def test_user_and_routine_messages_with_a_widget_fence_stay_text(
    app_clean: str, page: Page
) -> None:
    provider_id = seed_mock_provider(app_clean)
    agent = seed_mock_agent(app_clean, provider_id)
    fence = _widget()
    msgs = [
        Message.user("my fence:\n" + fence),
        Message.assistant("ok"),
        Message.user("routine fence:\n" + fence, routine_id="r-1", routine_name="Morning brief"),
        Message.assistant("done"),
    ]
    sid = seed_session(
        app_clean,
        agent,
        "text only",
        "2026-10-27T09:00:00+00:00",
        messages=encode_messages(msgs),
        session_metadata={
            "routine": {
                "id": "r-1",
                "name": "Morning brief",
                "last_run_at": "2026-10-27T09:00:00+00:00",
            }
        },
    )
    _open_seeded(page, app_clean, sid)
    expect(_chats.messages(page, "user")).to_have_count(2)
    expect(page.locator(CARD)).to_have_count(0)
    expect(page.locator("iframe")).to_have_count(0)
    expect(_chats.messages(page, "user").first).to_contain_text("```widget")
    expect(_chats.messages(page, "user").last).to_contain_text("```widget")


def test_copy_reply_copies_the_raw_markdown_including_the_widget_source(
    app_clean: str, page: Page
) -> None:
    text = "Here:\n\n" + _widget() + "\nEnd.\n"
    _reply(page, app_clean, text)
    page.evaluate(
        """() => {
          window.written = [];
          Object.defineProperty(navigator, 'clipboard', {configurable: true,
            value: {writeText: (t) => { window.written.push(t); return Promise.resolve(); }}});
        }"""
    )
    page.locator('[data-testid="message-copy"]').last.click()
    page.wait_for_function("() => window.written.length === 1")
    copied = page.evaluate("() => window.written[0]")
    assert copied == text
    assert "```widget" in copied and CTR in copied


def test_the_same_source_twice_gets_keys_0_and_1_and_a_reload_keeps_them(
    app_clean: str, page: Page
) -> None:
    text = "One:\n\n" + _widget() + "\nTwo:\n\n" + _widget() + "\nThree:\n\n" + _widget(CTR2)
    _reply(page, app_clean, text)
    expect(page.locator(CARD)).to_have_count(3)
    live = _keys(page)
    suffixes = [k.rsplit(":", 1)[1] for k in live]
    assert suffixes == ["0", "1", "0"]
    sid = _chats.current_session_id(page)
    assert all(k.startswith(sid + ":") for k in live)
    assert live[0].split(":")[1] == live[1].split(":")[1] != live[2].split(":")[1]
    page.reload()
    expect(page.locator(CARD)).to_have_count(3, timeout=10000)
    assert _keys(page) == live


# ── AC2: streaming ────────────────────────────────────────────────────────────

STREAM = [
    "Intro paragraph.\n\n",
    "```wid",
    "get\n",
    '<div style="height:300px">w</div>',
    "<script>window.__n = 0; setInterval(function () { window.__n++; }, 20);</script>\n",
    "```\n",
    "Closing words.",
]


# A page-side watch (flight DD3): on every mutation of the log, before any reply bubble exists,
# record any moment the block's source text is anywhere in the log's text (the work group's
# preview and its closed items included, hence textContent).
SOURCE_WATCH_JS = """() => {
  window.__leaks = [];
  const log = document.querySelector('.area-chat .messages');
  new MutationObserver(() => {
    if (log.querySelector('.ui-message--assistant')) return;
    const t = log.textContent;
    if (t.indexOf('```') >= 0 || t.indexOf('setInterval') >= 0 || t.indexOf('<script') >= 0) window.__leaks.push(t);
  }).observe(log, {childList: true, subtree: true, characterData: true, attributes: true});
}"""


def test_a_streaming_widget_shows_only_the_building_phrase_until_the_reply_lands(
    app_clean: str, page: Page
) -> None:
    """Flight DD3: while the block streams the preview reads "Building a widget" and no card,
    frame or source is in the log; the card is mounted when the reply lands."""
    _stream(page, app_clean, STREAM, delay_ms=700)
    page.evaluate(SOURCE_WATCH_JS)
    _chats.send_first(page, "go")
    expect(_chats.working_turns(page)).to_have_count(1, timeout=10000)
    expect(_chats.turn_preview(_chats.turn_group(page))).to_have_text(
        "Building a widget", timeout=10000
    )
    visible = page.locator(".area-chat .messages").evaluate("(el) => el.innerText")
    assert "```" not in visible and "setInterval" not in visible and "<script" not in visible
    expect(page.locator(CARD)).to_have_count(0)
    expect(page.locator("iframe")).to_have_count(0)
    expect(_chats.replies(page)).to_have_count(0)
    _done(page)
    assert page.evaluate("() => window.__leaks") == [], "block source was visible before done"
    expect(page.locator(CARD)).to_have_count(1)
    expect(page.locator(FRAME)).to_have_count(1, timeout=10000)
    bubble = _chats.messages(page, "assistant").last
    expect(bubble.locator("p").first).to_have_text("Intro paragraph.")
    expect(bubble.locator("p").last).to_have_text("Closing words.")


_WATCH_NESTED_JS = """() => {
  window.__leaks = [];
  const log = document.querySelector('.area-chat .messages');
  new MutationObserver(() => {
    if (log.querySelector('.ui-message--assistant')) return;
    const t = log.textContent;
    if (t.indexOf('```') >= 0 || t.indexOf('SECRET_') >= 0) window.__leaks.push(t);
  }).observe(log, {childList: true, subtree: true, characterData: true, attributes: true});
}"""


@pytest.mark.parametrize(
    "chunks",
    [
        # a widget inside a blockquote
        ["Quote:\n\n> ```wid", "get\n> SECRET_Q1 <b>x</b>\n", "> SECRET_Q2\n", "> ```\n", "After."],
        # a body with a fence-like line and a template-literal line
        [
            "Go:\n\n```widget\n<script>\nSECRET_F1 = `\n",
            "```js\nSECRET_F2\n",
            "`;</script>\n",
            "```\n",
            "After.",
        ],
    ],
    ids=["blockquote", "fence-like-body"],
)
def test_a_nested_or_tricky_widget_never_shows_source_while_streaming(
    app_clean: str, page: Page, chunks: list[str]
) -> None:
    _stream(page, app_clean, chunks, delay_ms=300)
    page.evaluate(_WATCH_NESTED_JS)
    _chats.send_first(page, "go")
    expect(_chats.working_turns(page)).to_have_count(1, timeout=10000)
    _done(page)
    assert page.evaluate("() => window.__leaks") == [], "block source was visible before done"


def test_a_chart_and_a_widget_in_one_streamed_reply_are_drawn_when_it_lands(
    app_clean: str, page: Page
) -> None:
    chunks = [
        "First:\n\n",
        "```chart\n",
        CHART[:20],
        CHART[20:] + "\n```\n\n",
        "Then:\n\n",
        "```widget\n",
        CTR + "\n",
        "```\n",
        "Done.",
    ]
    _stream(page, app_clean, chunks, delay_ms=600)
    _chats.send_first(page, "go")
    preview = _chats.turn_preview(_chats.turn_group(page))
    expect(preview).to_have_text("Drawing a chart", timeout=10000)
    expect(preview).to_have_text("Building a widget", timeout=15000)
    # Nothing is drawn until the reply lands.
    expect(page.locator('[data-testid="chat-chart"]')).to_have_count(0)
    expect(page.locator(CARD)).to_have_count(0)
    _done(page)
    expect(page.locator('[data-testid="chat-chart"]')).to_have_count(1)
    expect(page.locator(CARD)).to_have_count(1)


def test_a_stopped_turn_folds_an_unclosed_widget_block_into_the_group_and_it_never_runs(
    app_clean: str, page: Page
) -> None:
    """Flight DD5: a stop folds the pending text into the group; the unclosed widget block there
    shows the cut-off notice and no frame is ever created."""
    chunks = [
        "Before.\n\n",
        # The opener and some body arrive together (an empty cut-off block has nothing to show).
        '```widget\n<div style="height:100px">w</div>',
        "<script>window.parent.postMessage(1, '*');",
        " setInterval(function () {}, 20);</script>\n",
        "```\n",
    ]
    _stream(page, app_clean, chunks, delay_ms=900)
    _chats.send_first(page, "go")
    expect(_chats.working_turns(page)).to_have_count(1, timeout=10000)
    expect(_chats.turn_preview(_chats.turn_group(page))).to_have_text(
        "Building a widget", timeout=10000
    )
    page.locator('[data-testid="chat-stop-btn"]').click()
    err = page.locator(NOTICE)
    expect(err).to_have_count(1, timeout=10000)
    assert "ui-notice--muted" in err.get_attribute("class")
    expect(err).to_contain_text("This widget was cut off before it finished.")
    # The notice is inside the stopped group; no reply, no card, no frame.
    expect(page.locator(f'[data-testid="turn-work"] {NOTICE}')).to_have_count(1)
    assert _chats.turn_state(_chats.turn_group(page)) == "stopped"
    expect(_chats.replies(page)).to_have_count(0)
    expect(page.locator(CARD)).to_have_count(0)
    expect(page.locator("iframe")).to_have_count(0)
    expect(page.locator(SEND)).to_be_enabled(timeout=10000)


# ── AC3: teardown ─────────────────────────────────────────────────────────────


def test_switching_chats_removes_every_widget_frame_and_reopening_restores_the_keys(
    app_clean: str, page: Page
) -> None:
    provider_id = seed_mock_provider(app_clean)
    agent = seed_mock_agent(app_clean, provider_id)
    a = _seed_history(
        app_clean, agent, ["A:\n\n" + _widget() + "\n" + _widget(CTR2)], title="with widgets"
    )
    b = seed_session(app_clean, agent, "plain", "2026-10-26T09:00:00+00:00")
    _open_seeded(page, app_clean, a)
    expect(page.locator(CARD)).to_have_count(2, timeout=10000)
    expect(page.locator(FRAME).first).to_be_attached(timeout=10000)
    first = _keys(page)
    assert len(set(first)) == 2
    _chats.open_chat(page, b)
    expect(page.locator(CARD)).to_have_count(0)
    expect(page.locator("iframe")).to_have_count(0)
    assert page.evaluate("() => App.ui.widget._counts().cards") == 0
    assert page.evaluate("() => App.ui.widget._instances()") == 0
    _chats.open_chat(page, a)
    expect(page.locator(CARD)).to_have_count(2, timeout=10000)
    assert _keys(page) == first


def test_a_chat_cleared_in_the_same_task_it_rendered_in_leaks_no_card(
    app_clean: str, page: Page
) -> None:
    """The race the sweep alone misses: cards built in a fragment and cleared before any observer
    callback ever saw them connected are destroyed by clearLog's explicit handle destroy."""
    provider_id = seed_mock_provider(app_clean)
    agent = seed_mock_agent(app_clean, provider_id)
    sid = seed_session(app_clean, agent, "plain", "2026-10-26T09:00:00+00:00")
    _open_seeded(page, app_clean, sid)
    left = page.evaluate(
        """([text]) => {
          const tr = App.areas.find((a) => a.id === 'chat')._transcript();
          tr.renderHistory([{type: 'assistant', content: text}, {type: 'assistant', content: text}], 'x');
          tr.renderHistory([], 'x');
          return {cards: App.ui.widget._counts().cards, instances: App.ui.widget._instances(), frames: document.querySelectorAll('iframe').length};
        }""",
        ["W:\n\n" + _widget() + "\n" + _widget(CTR2)],
    )
    assert left == {"cards": 0, "instances": 0, "frames": 0}


# ── AC4: history and the lifecycle in chat ────────────────────────────────────


def test_a_reopened_chat_runs_only_the_widgets_in_view_and_scrolling_swaps_them(
    app_clean: str, page: Page
) -> None:
    provider_id = seed_mock_provider(app_clean)
    agent = seed_mock_agent(app_clean, provider_id)
    srcs = [
        f'<div style="height:300px">w{i}</div><script>window.__n = 0; setInterval(function () {{ window.__n++; }}, 20);</script>'
        for i in range(5)
    ]
    sid = _seed_history(app_clean, agent, ["\n".join(_widget(s) for s in srcs)])
    _open_seeded(page, app_clean, sid)
    expect(page.locator(CARD)).to_have_count(5, timeout=10000)
    page.evaluate(
        "() => { const l = document.querySelector('.messages'); l.scrollTop = l.scrollHeight; }"
    )
    page.wait_for_function("() => document.querySelectorAll('iframe').length >= 1", timeout=10000)
    page.wait_for_timeout(600)
    loaded = page.evaluate("() => document.querySelectorAll('iframe').length")
    assert 1 <= loaded <= 3
    # the top card is out of view and has no frame; the last one runs
    assert page.locator(CARD).nth(0).locator("iframe").count() == 0
    assert page.locator(CARD).nth(4).locator("iframe").count() == 1
    a = _frame_n(page, 4)
    page.wait_for_timeout(300)
    assert _frame_n(page, 4) > a
    # scroll to the top: the first card runs, and the bottom one is paused (its counter freezes)
    page.evaluate("() => { document.querySelector('.messages').scrollTop = 0; }")
    expect(page.locator(CARD).nth(0).locator("iframe")).to_have_count(1, timeout=10000)
    page.wait_for_timeout(600)
    b = _frame_n(page, 4)
    page.wait_for_timeout(400)
    assert _frame_n(page, 4) == b
    c = _frame_n(page, 0)
    page.wait_for_timeout(300)
    assert _frame_n(page, 0) > c
    # paused cards stay loaded (up to 8), but at most 3 run: count the counters that advance
    n_frames = page.locator(CARD).locator("iframe").count()
    before = [
        _frame_n(page, i) for i in range(5) if page.locator(CARD).nth(i).locator("iframe").count()
    ]
    page.wait_for_timeout(300)
    after = [
        _frame_n(page, i) for i in range(5) if page.locator(CARD).nth(i).locator("iframe").count()
    ]
    assert len(before) == len(after) == n_frames
    assert 1 <= sum(1 for x, y in zip(before, after, strict=True) if y > x) <= 3


# ── AC5: the page header and the OAuth listener ───────────────────────────────


def test_the_page_carries_the_frame_policy_header(app_clean: str, page: Page) -> None:
    _nav.goto_root(page, app_clean)
    csp = page.evaluate(
        "() => fetch('/', {cache: 'no-store'}).then((r) => r.headers.get('content-security-policy'))"
    )
    assert csp == "frame-src 'none'; child-src 'none'"


def test_a_widgets_forged_oauth_message_arrives_with_origin_null(
    app_clean: str, page: Page
) -> None:
    """The OAuth listener (areas/studio/mcp-oauth-consent.js) returns on
    ``evt.origin !== window.location.origin``; a sandboxed widget's origin is the string "null",
    so its forged ``mcp-oauth-result`` is dropped. (Attached only during a Library consent flow,
    so the live collision cannot be staged in Chats: this pins the origin the check relies on.)"""
    forge = '<div>f</div><script>parent.postMessage({type: "mcp-oauth-result", status: "failed"}, "*");</script>'
    provider_id = seed_mock_provider(app_clean)
    agent = seed_mock_agent(app_clean, provider_id)
    sid = _seed_history(app_clean, agent, [_widget(forge)])
    page.add_init_script(
        """(() => {
          window.__oauth = [];
          window.addEventListener('message', (e) => {
            if (e.data && e.data.type === 'mcp-oauth-result') window.__oauth.push({origin: e.origin, here: location.origin});
          });
        })();"""
    )
    _nav.goto_root(page, app_clean)
    _open_seeded(page, app_clean, sid)
    page.wait_for_function("() => window.__oauth.length >= 1", timeout=15000)
    ev = page.evaluate("() => window.__oauth[0]")
    assert ev["origin"] == "null"
    assert ev["origin"] != ev["here"]


# ── Sortie 16 L03: widgets and the turn work group (flow items 19 and 20) ──────

_W = "Here:\n\n" + _widget()
_T2 = {
    "type": "tool_call",
    "name": "shell",
    "arguments": {"command": "pwd"},
    "tool_call_id": "t2",
    "parent_message_id": "pm-2",
}
_R2 = {
    "type": "tool_result",
    "content": "/x",
    "is_error": False,
    "tool_call_id": "t2",
    "parent_message_id": "pm-2",
}
# One turn: a widget in the first narration, a second narration, and a final reply.
_TURN = [
    _user("show"),
    _text(_W),
    TOOL_CALL,
    TOOL_RESULT,
    _text("Then more."),
    _T2,
    _R2,
]
_HISTORY = [
    {"type": "user", "content": "show"},
    {"type": "assistant", "content": _W},
    TOOL_CALL,
    TOOL_RESULT,
    {"type": "assistant", "content": "Then more."},
    _T2,
    _R2,
    {"type": "assistant", "content": "Final."},
]


def _joined_chat(page: Page, base: str, script: _Script | None = None) -> str:
    provider_id = seed_mock_provider(base)
    agent = seed_mock_agent(base, provider_id)
    sid = seed_session(base, agent, "widget turn", "2026-10-27T09:00:00+00:00")
    if script is not None:
        script.install(page)
    page.set_viewport_size({"width": 1440, "height": 900})
    _nav.goto_root(page, base)
    _chats.open_chat(page, sid)
    return sid


def test_a_widget_in_a_reply_is_mounted_when_the_reply_lands(app_clean: str, page: Page) -> None:
    _joined_chat(page, app_clean)
    _frames(page, _user("show"), _chunk("Here it is:\n\n" + _widget() + "\nEnjoy."))
    expect(page.locator(CARD)).to_have_count(0)
    expect(page.locator("iframe")).to_have_count(0)
    _frames(page, DONE)
    expect(_chats.replies(page).locator(CARD)).to_have_count(1)
    expect(page.locator(FRAME)).to_have_count(1, timeout=10000)
    expect(_chats.turn_groups(page)).to_have_count(0)


def test_a_reply_that_ends_inside_an_open_widget_fence_shows_the_cut_off_notice_and_runs_nothing(
    app_clean: str, page: Page
) -> None:
    _joined_chat(page, app_clean)
    _frames(
        page, _user("show"), _chunk("Before.\n\n```widget\n<div>w</div><script>window.__ran = 1;")
    )
    _frames(page, DONE)
    err = page.locator(NOTICE)
    expect(err).to_have_count(1)
    expect(err).to_contain_text("This widget was cut off before it finished.")
    expect(_chats.replies(page).locator(NOTICE)).to_have_count(1)
    expect(page.locator(CARD)).to_have_count(0)
    page.wait_for_timeout(300)
    expect(page.locator("iframe")).to_have_count(0)


def test_a_widget_in_narration_is_not_mounted_while_its_group_is_closed_and_mounts_once_on_open(
    app_clean: str, page: Page
) -> None:
    _joined_chat(page, app_clean)
    _frames(page, *_TURN)
    group = _chats.turn_group(page)
    # The first narration was rendered when the second text arrived; its group is closed.
    expect(page.locator(CARD)).to_have_count(1)
    assert not _chats.turn_is_open(group)
    page.wait_for_timeout(600)
    expect(page.locator("iframe")).to_have_count(0)
    _chats.open_turn(group)
    expect(page.locator(FRAME)).to_have_count(1, timeout=10000)
    page.wait_for_timeout(300)
    expect(page.locator("iframe")).to_have_count(1)
    a = _frame_n(page)
    page.wait_for_timeout(300)
    assert _frame_n(page) > a


def test_a_widgets_key_is_the_same_live_and_after_a_reload(app_clean: str, page: Page) -> None:
    script = _Script()
    sid = _joined_chat(page, app_clean, script)
    _frames(page, *_TURN, _text("Final."), DONE)
    expect(page.locator(CARD)).to_have_count(1)
    live = _keys(page)
    assert len(live) == 1 and live[0].startswith(sid + ":") and live[0].endswith(":0"), live
    # The reload replays the same turn from stored history.
    script.history = _HISTORY
    page.reload()
    _chats.expect_chat(page, "test-agent", timeout=10000)
    expect(page.locator(CARD)).to_have_count(1, timeout=10000)
    expect(_chats.replies(page)).to_have_text(["Final."])
    assert _keys(page) == live


def test_a_widget_in_the_latest_narration_that_becomes_the_reply_is_drawn_exactly_once(
    app_clean: str, page: Page
) -> None:
    sid = _joined_chat(page, app_clean)
    # The turn ends on a tool call: the latest narration (with the widget, still plain text in
    # the group) becomes the reply at `done`.
    _frames(page, _user("show"), _text(_W), TOOL_CALL, TOOL_RESULT)
    expect(page.locator(CARD)).to_have_count(0)
    _frames(page, DONE)
    expect(_chats.replies(page).locator(CARD)).to_have_count(1)
    page.wait_for_timeout(500)  # a sweep of any wrongly built second card would have run
    expect(page.locator(CARD)).to_have_count(1)
    keys = _keys(page)
    assert len(keys) == 1 and keys[0].startswith(sid + ":") and keys[0].endswith(":0"), keys
    assert page.evaluate("() => App.ui.widget._counts().cards") == 1
    group = _chats.turn_group(page)
    assert _chats.turn_item_list(group) == ["tool", "tool"]
    expect(page.locator(FRAME)).to_have_count(1, timeout=10000)
