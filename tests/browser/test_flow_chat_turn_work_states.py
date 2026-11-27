"""One work group per chat turn, the remaining states (sortie 16 L03, flight DD4-DD7).

Scripted live frames (``_chats.emit_frame``, the real ``ws.onmessage`` path) and seeded or
rewritten history, like ``test_flow_chat_turn_work.py``. Each test asserts the whole shape of the
turn, including what must be absent (no reply bubble, no running dots, no second group).

Covers flow items 6, 7, 9, 14, 15, 17, 18, 19 (the chart half; the widget half is in
``test_flow_chat_widgets.py``) and 21. The ``chats-transcript`` lane.
"""

from __future__ import annotations

import pytest
from browser import _chats, _nav
from browser.seeders import SeededApp, seed_session
from browser.test_flow_chat_turn_work import (
    DONE,
    INPUT,
    STOP,
    STOPPED,
    TOOL_CALL,
    TOOL_RESULT,
    _chunk,
    _frames,
    _Script,
    _text,
    _user,
)
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

SEND = '[data-testid="chat-send-btn"]'
COPY = '[data-testid="message-copy"]'
AGENT_ERROR = '[data-testid="chat-agent-error"]'
STEP_LIMIT = '[data-testid="chat-step-limit"]'
CONTINUE = '[data-testid="chat-step-limit-continue"]'
CHART = '[data-testid="chat-chart"]'
CHART_ERROR = '[data-testid="chat-chart-error"]'

_CLIPBOARD_SPY = """() => {
  window.__copied = [];
  Object.defineProperty(navigator, 'clipboard', {configurable: true,
    value: {writeText: (t) => { window.__copied.push(t); return Promise.resolve(); }}});
}"""

# The log's direct children that matter, in DOM order: work groups, reply bubbles, user bubbles.
_ORDER_JS = """() => Array.from(document.querySelectorAll(
  '.area-chat .messages > [data-testid="turn-work"],'
  + ' .area-chat .messages > .ui-message--assistant,'
  + ' .area-chat .messages > .ui-message--user'
)).map(e => e.getAttribute('data-testid') === 'turn-work' ? 'work'
  : e.classList.contains('ui-message--user') ? 'user:' + e.textContent.trim() : 'reply')"""


def _open_chat(
    page: Page, app: SeededApp, script: _Script | None = None, platform: str | None = None
) -> str:
    """Open a joined, empty seeded chat (a connector chat when ``platform`` is set)."""
    sid = seed_session(
        app.base_url, app.agent_name, "States chat", "2026-01-02T00:00:00Z", platform=platform
    )
    if script is not None:
        script.install(page)
    _nav.goto_root(page, app.base_url)
    _chats.open_chat(page, sid)
    return sid


def _send(page: Page, text: str) -> None:
    page.locator(INPUT).fill(text)
    page.locator(INPUT).press("Enter")


def _tool_turn(*texts: str) -> list[dict]:
    """A turn frames: user, a pass of text, a tool call and its result."""
    return [_user("go"), _chunk(texts[0]), TOOL_CALL, TOOL_RESULT]


# ── 6: Stop racing done ───────────────────────────────────────────────────────


def test_a_done_after_a_stop_click_still_lands_the_reply_and_the_line_reads_work(
    app_with_agent: SeededApp, page: Page
) -> None:
    # `swallow`: nothing reaches the server, so the test owns every frame of the turn.
    _open_chat(page, app_with_agent, _Script(swallow=True))
    _send(page, "go")
    expect(_chats.working_turns(page)).to_have_count(1)
    _frames(page, _chunk("narration"), TOOL_CALL, TOOL_RESULT, _chunk("the answer"))
    group = _chats.turn_group(page)
    assert not _chats.turn_dots_stopped(group)
    expect(page.locator(STOP)).to_be_visible()
    page.locator(STOP).click()
    # The click only stops the dots: the state changes on frames alone.
    page.wait_for_function(
        "() => document.querySelector('[data-testid=\"turn-work\"] .ui-turn-work-spin')"
        ".getAttribute('data-stopped') === 'true'"
    )
    assert _chats.turn_dots_stopped(group)
    assert _chats.turn_state(group) == "working"
    expect(_chats.replies(page)).to_have_count(0)
    # The turn had already finished: `done` (and no `cancelled`) arrives.
    _frames(page, DONE)
    expect(_chats.replies(page)).to_have_text(["the answer"])
    assert _chats.turn_state(group) == "done"
    assert _chats.turn_line(group) == "Work · 1 tool call"
    expect(_chats.working_turns(page)).to_have_count(0)
    expect(page.locator(STOPPED)).to_have_count(0)
    expect(page.locator(SEND)).to_be_enabled()


def test_a_cancelled_with_no_open_group_adds_only_the_notices(
    app_with_agent: SeededApp, page: Page
) -> None:
    _open_chat(page, app_with_agent)
    _frames(page, {"type": "cancelled"})
    expect(page.locator(STOPPED)).to_have_text("Stopped.")
    expect(_chats.turn_groups(page)).to_have_count(0)
    expect(_chats.replies(page)).to_have_count(0)


# ── 7: errors ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "content",
    [
        "Agent error: boom",
        "An error occurred while processing your message.",
        "Failed to resume after authentication.",
    ],
)
def test_an_error_ends_the_group_with_no_reply_and_the_trailing_done_promotes_nothing(
    app_with_agent: SeededApp, page: Page, content: str
) -> None:
    _open_chat(page, app_with_agent)
    _frames(page, *_tool_turn("working on it"), {"type": "system", "content": content})
    group = _chats.turn_group(page)
    assert _chats.turn_state(group) == "error"
    assert _chats.turn_line(group) == "Ended with an error · 1 tool call"
    expect(_chats.working_turns(page)).to_have_count(0)
    expect(_chats.replies(page)).to_have_count(0)
    # The text the model wrote is kept in the group.
    assert _chats.turn_item_list(group) == ["narration:working on it", "tool", "tool"]
    if content.startswith("Agent error"):
        expect(page.locator(AGENT_ERROR)).to_have_count(1)
    else:
        expect(_chats.messages(page, "system")).to_contain_text([content])
    # The `done` the server sends after an agent error promotes nothing.
    _frames(page, DONE)
    expect(_chats.replies(page)).to_have_count(0)
    expect(_chats.turn_groups(page)).to_have_count(1)
    assert _chats.turn_state(group) == "error"
    assert _chats.turn_item_list(group) == ["narration:working on it", "tool", "tool"]


# ── 9: the step limit ─────────────────────────────────────────────────────────


def test_a_step_limit_pauses_the_group_and_continue_starts_a_turn_with_its_own_group(
    app_with_agent: SeededApp, page: Page
) -> None:
    _open_chat(page, app_with_agent, _Script(swallow=True))
    _frames(page, *_tool_turn("partial"), {"type": "step_limit", "steps": 5}, DONE)
    group = _chats.turn_group(page)
    assert _chats.turn_state(group) == "step-limit"
    assert _chats.turn_line(group) == "Paused at the step limit · 1 tool call"
    expect(page.locator(STEP_LIMIT)).to_have_count(1)
    expect(page.locator(CONTINUE)).to_have_count(1)
    expect(_chats.replies(page)).to_have_count(0)
    expect(_chats.working_turns(page)).to_have_count(0)
    assert _chats.turn_item_list(group) == ["narration:partial", "tool", "tool"]

    page.locator(CONTINUE).click()
    expect(_chats.messages(page, "user").last).to_have_text("continue")
    # The next turn has its own group; the paused one stays as it was.
    expect(_chats.working_turns(page)).to_have_count(1)
    expect(_chats.turn_groups(page)).to_have_count(2)
    assert _chats.turn_state(_chats.turn_group(page, 0)) == "step-limit"
    _frames(page, _chunk("narr"), TOOL_CALL, TOOL_RESULT, _chunk("Finished."), DONE)
    expect(_chats.turn_groups(page)).to_have_count(2)
    expect(_chats.replies(page)).to_have_text(["Finished."])
    assert _chats.turn_state(_chats.turn_group(page, 0)) == "step-limit"
    assert _chats.turn_state(_chats.turn_group(page, 1)) == "done"
    assert _chats.turn_item_list(_chats.turn_group(page, 0)) == [
        "narration:partial",
        "tool",
        "tool",
    ]


# ── 14: a second window ───────────────────────────────────────────────────────


def test_a_second_window_that_only_receives_the_frames_shows_one_group_and_one_reply(
    app_with_agent: SeededApp, page: Page
) -> None:
    # No local send: another window's turn arrives as a `user` frame, then the turn's frames.
    _open_chat(page, app_with_agent)
    _frames(page, _user("from another window"), _chunk("Let me check."), TOOL_CALL, TOOL_RESULT)
    expect(_chats.messages(page, "user")).to_have_text(["from another window"])
    expect(_chats.working_turns(page)).to_have_count(1)
    expect(_chats.replies(page)).to_have_count(0)
    _frames(page, _chunk("All good."), DONE)
    expect(_chats.turn_groups(page)).to_have_count(1)
    expect(_chats.replies(page)).to_have_text(["All good."])
    group = _chats.turn_group(page)
    assert _chats.turn_state(group) == "done"
    assert _chats.turn_line(group) == "Work · 1 tool call"
    assert _chats.turn_item_list(group) == ["narration:Let me check.", "tool", "tool"]


# ── 15: a held message ────────────────────────────────────────────────────────


def test_a_held_message_follows_the_reply_in_the_log(app_with_agent: SeededApp, page: Page) -> None:
    _open_chat(page, app_with_agent, _Script(swallow=True))
    _send(page, "go")
    expect(_chats.working_turns(page)).to_have_count(1)
    _frames(page, TOOL_CALL, TOOL_RESULT, _chunk("the reply"))
    _send(page, "queued")
    expect(page.locator('[data-testid="pending-queued"]')).to_have_count(1)
    assert page.evaluate(_ORDER_JS) == ["user:go", "work"]
    _frames(page, DONE)
    expect(_chats.messages(page, "user")).to_have_text(["go", "queued"])
    # The reply lands first, then the queued message's bubble, then the queued turn's own
    # running group.
    assert page.evaluate(_ORDER_JS) == ["user:go", "work", "reply", "user:queued", "work"]
    expect(_chats.turn_groups(page)).to_have_count(2)
    assert _chats.turn_state(_chats.turn_group(page, 0)) == "done"
    assert _chats.turn_state(_chats.turn_group(page, 1)) == "working"
    expect(page.locator('[data-testid="pending-queued"]')).to_have_count(0)


# ── 17: a connector chat ──────────────────────────────────────────────────────


def test_a_connector_group_carries_the_operator_chip_and_a_delivered_result_stays_outside(
    app_with_agent: SeededApp, page: Page
) -> None:
    _open_chat(page, app_with_agent, platform="discord")
    op = {"visibility": "operator"}
    delivered = {
        "type": "tool_result",
        "content": "[platform-send-ok] sent",
        "is_error": False,
        "tool_call_id": "t2",
        "parent_message_id": "pm-1",
    }
    _frames(
        page,
        _user("please send"),
        {**_chunk("checking"), **op},
        {**TOOL_CALL, **op},
        {**TOOL_RESULT, **op},
        delivered,
        _chunk("Sent it."),
        DONE,
    )
    group = _chats.turn_group(page)
    expect(_chats.turn_groups(page)).to_have_count(1)
    assert _chats.turn_state(group) == "done"
    # The chip is on the group once; the items inside do not repeat it.
    assert (group.text_content() or "").count("Operator only") == 1
    assert "Operator only" in (_chats.turn_summary(group).inner_text() or "")
    assert _chats.turn_item_list(group) == ["narration:checking", "tool", "tool"]
    # The delivered result is a top-level bubble after the group, not an item of it.
    expect(page.locator(".area-chat .messages > .ui-message--tool")).to_have_count(1)
    expect(page.locator(".area-chat .messages > .ui-message--tool")).to_contain_text(
        "platform-send-ok"
    )
    expect(group.locator(".ui-message--tool")).to_have_count(2)
    assert "platform-send-ok" not in (group.text_content() or "")
    expect(_chats.replies(page)).to_have_text(["Sent it."])


# ── 18: Copy reply ────────────────────────────────────────────────────────────


def test_copy_reply_copies_the_reply_and_none_of_the_narration(
    app_with_agent: SeededApp, page: Page
) -> None:
    _open_chat(page, app_with_agent)
    _frames(
        page,
        _user("go"),
        _text("Let me look."),
        TOOL_CALL,
        TOOL_RESULT,
        _text("The answer is **42**."),
        DONE,
    )
    expect(_chats.replies(page)).to_have_count(1)
    expect(page.locator(COPY)).to_have_count(1)
    page.evaluate(_CLIPBOARD_SPY)
    page.locator(COPY).click()
    page.wait_for_function("() => window.__copied.length === 1")
    copied = page.evaluate("() => window.__copied[0]")
    # The reply's source, not its rendering; nothing the narration said.
    assert copied == "The answer is **42**."
    assert "Let me look" not in copied
    assert "shell" not in copied


# ── 19 (chart half) and 21: visuals in a reply, and the preview ───────────────

_CHART = '{"type": "line", "x": {"values": [1, 2, 3]}, "series": [{"values": [3, 5, 4]}]}'


def test_a_chart_in_a_reply_is_drawn_when_the_reply_lands(
    app_with_agent: SeededApp, page: Page
) -> None:
    _open_chat(page, app_with_agent)
    _frames(page, _user("go"), _chunk("Here:\n\n```chart\n" + _CHART + "\n```\n"), _chunk("Done."))
    expect(_chats.replies(page)).to_have_count(0)
    expect(page.locator(CHART)).to_have_count(0)
    _frames(page, DONE)
    expect(page.locator(CHART)).to_have_count(1)
    expect(_chats.replies(page)).to_have_count(1)
    expect(_chats.replies(page).locator(CHART)).to_have_count(1)
    # A plain reply: no work group.
    expect(_chats.turn_groups(page)).to_have_count(0)


def test_a_reply_that_ends_inside_an_open_chart_fence_shows_the_cut_off_notice(
    app_with_agent: SeededApp, page: Page
) -> None:
    _open_chat(page, app_with_agent)
    _frames(page, _user("go"), _chunk('Before.\n\n```chart\n{"type": "bar", "x": {"val'), DONE)
    err = page.locator(CHART_ERROR)
    expect(err).to_have_count(1)
    expect(err).to_contain_text("This chart was cut off before it finished.")
    expect(page.locator(CHART)).to_have_count(0)
    expect(_chats.replies(page).locator(CHART_ERROR)).to_have_count(1)


def test_the_preview_shows_a_phrase_and_never_the_source_of_a_chart_or_widget(
    app_with_agent: SeededApp, page: Page
) -> None:
    _open_chat(page, app_with_agent)
    _frames(page, _user("go"), _chunk("A chart:\n\n```chart\n" + _CHART[:40]))
    group = _chats.turn_group(page)
    preview = _chats.turn_preview(group)
    expect(preview).to_have_text("Drawing a chart")
    log = page.locator(".area-chat .messages")
    visible = log.evaluate("el => el.innerText")
    assert '{"type"' not in visible and "```" not in visible and "values" not in visible
    # The fence closes: the preview is the text again (the block is drawn only at `done`).
    _frames(page, _chunk(_CHART[40:] + "\n```\n\nThen a widget:\n\n```widget\n<script>var a = 1;"))
    expect(preview).to_have_text("Building a widget")
    visible = log.evaluate("el => el.innerText")
    assert "<script" not in visible and "var a" not in visible and "```" not in visible
    expect(page.locator(CHART)).to_have_count(0)
    expect(page.locator('[data-testid="chat-widget"]')).to_have_count(0)
    expect(page.locator("iframe")).to_have_count(0)


# ── previewFor against the real renderer (flight DD3) ────────────────────────

_PREVIEW_CORPUS: dict[str, str] = {
    "top chart": "Intro\n\n```chart\nSECRET_A1\n```\n\nAfter",
    "top widget": "Intro\n```widget\n<b>SECRET_A2</b>\n```\nAfter",
    "crlf": "hi\r\n```chart\r\nSECRET_B1\r\n```\r\nbye",
    "lone cr": "hi\r```chart\rSECRET_B2\r```\rbye",
    "blockquote": "> ```chart\n> SECRET_C1\n> ```\nAfter",
    "blockquote no space": ">```chart\n>SECRET_C3\n>```\nAfter",
    "indented blockquote": "   > ```chart\n   > SECRET_C4\n   > ```",
    "nested blockquote": "> > ```widget\n> > SECRET_C2\n> > ```\n",
    "bullet continuation": "- item\n  ```chart\n  SECRET_D1\n  ```\n- next",
    "bullet first line": "- ```chart\n  SECRET_D2\n  ```\n",
    "star bullet": "* ```widget\n  SECRET_D5\n  ```\n",
    "ordered": "1. ```widget\n   SECRET_D3\n   ```\n2. two",
    "ordered two digits": "10. ```chart\n    SECRET_D6\n    ```\n",
    "list in blockquote": "> - ```chart\n>   SECRET_D4\n>   ```\n",
    "task item": "- [x] ```chart\n  SECRET_J2\n  ```\n",
    "nested list": "- a\n  - ```chart\n    SECRET_J5\n    ```\n",
    "indented fence in body": "```chart\nSECRET_E1\n  ```\nSECRET_E2\n```\nAfter",
    "js fence in body": "```widget\nSECRET_E3\n```js\nSECRET_E4\n```\nAfter",
    "fence with text in body": "```chart\nSECRET_E5\n```x\nSECRET_E6\n```",
    "template literal body": (
        "```widget\n<script>\nSECRET_E7 = `\n```js\nSECRET_E8\n`;</script>\n```\n"
    ),
    "indented bare close in body": "```chart\nSECRET_I2\n  ```\nSECRET_I3\n```\nz",
    "two blocks": "```chart\nSECRET_F1\n```\ntext\n```widget\nSECRET_F2\n```",
    "closed then prose": "```chart\nSECRET_F3\n```\nprose after",
    "closed then open": "```chart\nSECRET_F4\n```\nmid\n```widget\nSECRET_F5\n",
    "info attributes": "```chart title=x\nSECRET_G1\n```\n",
    "info trailing spaces": "```chart   \nSECRET_G2\n```  \nAfter",
    "info tab": "```widget\t\nSECRET_I4\n```",
    "four backtick wrap": "````\n```chart\nSECRET_H1\n```\n````\n",
    "python with chart line": "```python\n```chart\nSECRET_H2\n```\nafter\n",
    "python then chart": "```python\nx = 1\n```\n```chart\nSECRET_J1\n```",
    "upper case": "```Chart\nSECRET_H3\n```",
    "tilde fence": "~~~chart\nSECRET_H4\n~~~",
    "inline backticks": "use ```chart inline ``` here\nand more",
    "indented opener": "  ```chart\n  SECRET_I1\n  ```",
    "quote then prose": "> ```chart\n> SECRET_I5\n> ```\n> more\nPROSE_VISIBLE\n",
    # Markers of any length (no fixed look-ahead window may hide a fence from the preview).
    "ordered 30 digits": "1" * 30 + ". ```chart\n   SECRET_K1_1\n   SECRET_K1_2\n   ```\n",
    "ordered 200 digits": "7" * 200 + ". ```widget\n   SECRET_K2_1\n   SECRET_K2_2\n   ```\n",
    "marker then 100 spaces": "-" + " " * 100 + "```chart\n  SECRET_K3_1\n  SECRET_K3_2\n```\n",
    "60 nested quotes": "> " * 60 + "```chart\n" + "> " * 60 + "SECRET_K4_1\n",
    "plain json-like body": (
        "```chart\nSECRET_K5_1\n"
        '{"type": "bar", "note": "SECRET_K5_2",\n'
        ' "values": [1, 2, SECRET_K5_3]}\nplain words SECRET_K5_4\n```\nAfter'
    ),
}

_PREVIEW_JS = """(corpus) => {
  const pf = App.chat.turnWork.create(
    {state: {}, messagesEl: document.createElement('div')}).previewFor;
  const out = {};
  const tokens = (s) => s.match(/SECRET_[A-Z0-9]+/g) || [];
  Object.keys(corpus).forEach((name) => {
    const text = corpus[name];
    const sources = [];
    const spy = (src) => { sources.push(src); return document.createElement('span'); };
    App.markdown.render(text, {codeBlockRenderers: {chart: spy, widget: spy}});
    const full = [];
    const fullLines = [];
    sources.forEach((s) => {
      tokens(s).forEach((t) => full.push(t));
      s.split('\\n').forEach((l) => { if (l.trim().length >= 8) fullLines.push(l.trim()); });
    });
    const found = sources.length;
    const bad = [];
    for (let n = 0; n <= text.length; n++) {
      const prefix = text.slice(0, n);
      const here = [];
      const spy2 = (src) => { here.push(src); return document.createElement('span'); };
      App.markdown.render(prefix, {codeBlockRenderers: {chart: spy2, widget: spy2}});
      const toks = full.slice();
      here.forEach((s) => tokens(s).forEach((t) => toks.push(t)));
      const p = pf(prefix);
      toks.forEach((t) => { if (p.indexOf(t) !== -1) bad.push([n, 'token ' + t, p]); });
      // Any body line the renderer draws (this prefix's own, or the full text's), and any
      // partially typed token, is a leak.
      const lines = fullLines.slice();
      here.forEach((s) => s.split('\\n').forEach((l) => {
        if (l.trim().length >= 8) lines.push(l.trim());
      }));
      lines.forEach((l) => { if (p.indexOf(l) !== -1) bad.push([n, 'line ' + l, p]); });
      if (found + here.length > 0 && p.indexOf('SECRET_') !== -1) bad.push([n, 'partial', p]);
      const ticks = p.indexOf('```chart') !== -1 || p.indexOf('```widget') !== -1;
      if (found + here.length > 0 && ticks) {
        bad.push([n, 'opener', p]);
      }
    }
    out[name] = {found: found, bad: bad.slice(0, 3)};
  });
  return out;
}"""

_PREVIEW_FN = (
    "App.chat.turnWork.create({state: {}, messagesEl: document.createElement('div')}).previewFor"
)


def test_the_preview_never_shows_source_the_renderer_would_draw_at_any_prefix(
    app_with_agent: SeededApp, page: Page
) -> None:
    _nav.goto_root(page, app_with_agent.base_url)
    page.wait_for_function("() => window.App && App.chat && App.chat.turnWork")
    result = page.evaluate(_PREVIEW_JS, _PREVIEW_CORPUS)
    leaks = {k: v["bad"] for k, v in result.items() if v["bad"]}
    assert leaks == {}, leaks
    # The corpus is not vacuous: the renderer hands these to the chart or widget renderer.
    must_draw = [
        "top chart", "top widget", "crlf", "lone cr", "blockquote", "nested blockquote",
        "bullet continuation", "bullet first line", "ordered", "list in blockquote",
        "indented fence in body", "js fence in body", "template literal body", "two blocks",
        "closed then open", "info attributes", "info trailing spaces", "ordered 30 digits",
        "ordered 200 digits", "marker then 100 spaces", "60 nested quotes",
        "plain json-like body",
    ]  # fmt: skip
    for name in must_draw:
        assert result[name]["found"] >= 1, name


def test_the_preview_does_not_throw_on_odd_input(app_with_agent: SeededApp, page: Page) -> None:
    _nav.goto_root(page, app_with_agent.base_url)
    page.wait_for_function("() => window.App && App.chat && App.chat.turnWork")
    out = page.evaluate(
        "() => { const pf = " + _PREVIEW_FN + ";"
        " return [null, undefined, '', '`', '``', '```', '``````', '> ', '- ', '>>>>', '\\r',"
        " 'x'.repeat(50000)].map((v) => typeof pf(v)); }"
    )
    assert set(out) == {"string"}


def test_the_preview_keeps_ordinary_text_visible_and_holds_back_an_unfinished_opener(
    app_with_agent: SeededApp, page: Page
) -> None:
    _nav.goto_root(page, app_with_agent.base_url)
    page.wait_for_function("() => window.App && App.chat && App.chat.turnWork")
    out = page.evaluate(
        "() => { const pf = " + _PREVIEW_FN + "; return {"
        " prose: pf('Hello there.\\n\\nA second line, with `code`.'),"
        " py: pf('Look:\\n```python\\nx = 1\\n```\\nDone'),"
        " held: pf('Intro\\n```ch'), heldBare: pf('Intro\\n```'),"
        " onlyChart: pf('```chart\\n{\"a\": 1}'), onlyWidget: pf('```widget\\n<b>x</b>\\n') }; }"
    )
    assert out["prose"] == "Hello there.\n\nA second line, with `code`."
    assert out["py"] == "Look:\n```python\nx = 1\n```\nDone"
    assert out["held"] == "Intro"
    assert out["heldBare"] == "Intro"
    assert out["onlyChart"] == "Drawing a chart"
    assert out["onlyWidget"] == "Building a widget"
