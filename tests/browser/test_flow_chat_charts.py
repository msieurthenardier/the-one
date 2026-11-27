# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Browser flow tests for charts in chat (M35 F1 L2, flight DD6, DD8, DD10, DD14).

A ``chart`` fenced block in an assistant reply is drawn as a chart when the reply lands at
``done`` (sortie 16: while the turn runs the work group's preview reads "Drawing a chart" and
nothing of the block is in the log) and in history. The mock provider streams explicit
``stream_chunks`` so the opener, the ``"type"`` key and the closing fence fall in separate
chunks. A landed reply is compared with a direct render of the same text after normalising each
chart subtree. Assertions are structural; no pixels and no snapshots.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from browser import _chats, _nav
from browser.seeders import seed_mock_agent, seed_mock_provider
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

CORPUS = Path(__file__).resolve().parent.parent / "fixtures" / "charts" / "valid"
LINE = json.dumps(json.loads((CORPUS / "line-minimal.json").read_text(encoding="utf-8")))
BAR = json.dumps(json.loads((CORPUS / "bar-minimal.json").read_text(encoding="utf-8")))
PIE = json.dumps(json.loads((CORPUS / "pie-minimal.json").read_text(encoding="utf-8")))

CHART = '[data-testid="chat-chart"]'
CHART_ERROR = '[data-testid="chat-chart-error"]'
SEND = '[data-testid="chat-send-btn"]'


def _chunks(text: str, size: int) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]


def _open(page: Page, base_url: str, chunks: list[str], delay_ms: int = 0):
    provider_id = seed_mock_provider(
        base_url, config={"stream_chunks": chunks, "delay_ms": delay_ms}
    )
    agent = seed_mock_agent(base_url, provider_id)
    _nav.goto_root(page, base_url)
    _chats.start_chat(page, agent)
    return agent


def _send(page: Page) -> None:
    _chats.send_first(page, "go")


def _done(page: Page, timeout: float = 30000) -> None:
    expect(_chats.messages(page, "assistant").first).to_be_visible(timeout=timeout)
    expect(page.locator(SEND)).to_be_enabled(timeout=timeout)


def _bubble(page: Page):
    return _chats.messages(page, "assistant").last


def _child_tags(page: Page) -> list[str]:
    return page.evaluate(
        """() => {
          const b = Array.from(document.querySelectorAll('[data-testid="message"].ui-message--assistant')).pop();
          return Array.from(b.children).map((c) => c.tagName.toLowerCase());
        }"""
    )


# ── AC8.1: streaming a chart ──────────────────────────────────────────────────


def test_a_streaming_chart_shows_only_the_drawing_phrase_until_the_reply_lands(
    app_clean: str, page: Page
) -> None:
    """Flight DD3: while the block streams the preview reads "Drawing a chart" and nothing of
    the block (no source, no chart) is in the log; the chart is drawn when the reply lands."""
    chunks = [
        "Intro paragraph.\n\n",
        "```ch",
        "art\n",
        '{"ty',
        'pe": "line", ',
        '"x": {"values": [1, 2, 3, 4, 5]}, ',
        '"series": [{"values": [3, 5, 4, 8, 6]}]}\n',
        "```\n",
        "Closing words.",
    ]
    _open(page, app_clean, chunks, delay_ms=700)
    # A page-side watch (flight DD3): before any reply bubble exists, record any moment the
    # chart's source text is anywhere in the log (the work group included, hence textContent).
    page.evaluate(
        """() => {
          window.__leaks = [];
          const log = document.querySelector('.area-chat .messages');
          new MutationObserver(() => {
            if (log.querySelector('.ui-message--assistant')) return;
            const t = log.textContent;
            if (t.indexOf('```') >= 0 || t.indexOf('"values"') >= 0 || t.indexOf('"series"') >= 0 || t.indexOf('{"ty') >= 0) window.__leaks.push(t);
          }).observe(log, {childList: true, subtree: true, characterData: true, attributes: true});
        }"""
    )
    _send(page)
    expect(_chats.working_turns(page)).to_have_count(1, timeout=10000)
    preview = _chats.turn_preview(_chats.turn_group(page))
    expect(preview).to_have_text("Drawing a chart", timeout=10000)
    visible = page.locator(".area-chat .messages").evaluate("(el) => el.innerText")
    assert "```" not in visible and '{"ty' not in visible and "line" not in visible, visible
    expect(page.locator(CHART)).to_have_count(0)
    expect(_chats.replies(page)).to_have_count(0)
    expect(page.locator(SEND)).to_be_disabled()
    # The chart is drawn only when the reply lands, with the text before and after it.
    _done(page)
    assert page.evaluate("() => window.__leaks") == [], "chart source was visible before done"
    expect(page.locator(CHART)).to_have_count(1)
    assert _child_tags(page) == ["p", "figure", "p"]
    expect(_bubble(page).locator("p").last).to_have_text("Closing words.")
    expect(_chats.turn_groups(page)).to_have_count(0)


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
        # a chart inside a blockquote
        ["Quote:\n\n> ```ch", "art\n> SECRET_Q1 ", '{"type": "bar"}\n', "> ```\n", "After."],
        # a body with fence-like lines: an indented fence and a fence with text
        [
            "Go:\n\n```chart\nSECRET_F1\n",
            "  ```x\nSECRET_F2\n",
            "```js\nSECRET_F3\n",
            "```\n",
            "After.",
        ],
    ],
    ids=["blockquote", "fence-like-body"],
)
def test_a_nested_or_tricky_chart_never_shows_source_while_streaming(
    app_clean: str, page: Page, chunks: list[str]
) -> None:
    _open(page, app_clean, chunks, delay_ms=300)
    page.evaluate(_WATCH_NESTED_JS)
    _send(page)
    expect(_chats.working_turns(page)).to_have_count(1, timeout=10000)
    _done(page)
    assert page.evaluate("() => window.__leaks") == [], "chart source was visible before done"


def test_a_chart_in_a_landed_reply_fills_the_reply_width(app_clean: str, page: Page) -> None:
    chunks = [
        "Short.\n\n",
        "```chart\n",
        '{"type": "line", "x": {"values": [1, 2, 3]}, "series": [{"values": [3, 5, 4]}]}\n',
        "```\n",
        "Done.",
    ]
    _open(page, app_clean, chunks, delay_ms=50)
    _send(page)
    _done(page)
    expect(page.locator(CHART)).to_have_count(1)
    # expected width: the bubble's computed cap, limited by the pane it sits in
    measure = """() => {
      const b = document.querySelector('.ui-message--assistant');
      const cap = parseFloat(getComputedStyle(b).maxWidth) || Infinity;
      const pane = b.parentElement.getBoundingClientRect().width;
      const f = document.querySelector('[data-testid="chat-chart"]');
      return {w: f.getBoundingClientRect().width, cap: Math.min(cap, pane)};
    }"""
    ch_m = page.evaluate(measure)
    assert ch_m["w"] >= 0.9 * ch_m["cap"] - 24, ch_m


# ── AC8.2-8.4 ─────────────────────────────────────────────────────────────────


def test_a_reply_ending_with_a_chart_draws_it_at_finalize(app_clean: str, page: Page) -> None:
    text = "Here it is:\n\n```chart\n" + LINE + "\n```"  # a bare final fence: finalize-only
    _open(page, app_clean, _chunks(text, 14), delay_ms=20)
    _send(page)
    _done(page)
    expect(page.locator(CHART)).to_have_count(1)
    assert _child_tags(page) == ["p", "figure"]


def test_a_broken_chart_shows_the_error_notice_and_the_rest_of_the_reply(
    app_clean: str, page: Page
) -> None:
    text = 'Before.\n\n```chart\n{"type": "bar"}\n```\n\nRest of the reply.\n'
    _open(page, app_clean, _chunks(text, 10), delay_ms=10)
    _send(page)
    _done(page)
    expect(page.locator(CHART)).to_have_count(0)
    err = page.locator(CHART_ERROR)
    expect(err).to_have_count(1)
    expect(err.locator(".ui-visual-notice-head")).to_have_text("Couldn't draw this chart.")
    assert err.locator(".ui-visual-notice-reason").inner_text().strip() != ""
    assert 'type": "bar"' in err.locator("details pre").text_content()
    bubble = _bubble(page)
    expect(bubble.locator("p").first).to_have_text("Before.")
    expect(bubble.locator("p").last).to_have_text("Rest of the reply.")


def test_a_stream_that_ends_inside_the_block_shows_the_cut_off_notice(
    app_clean: str, page: Page
) -> None:
    text = 'Before.\n\n```chart\n{"type": "bar", "x": {"val'
    _open(page, app_clean, _chunks(text, 12), delay_ms=10)
    _send(page)
    _done(page)
    err = page.locator(CHART_ERROR)
    expect(err).to_have_count(1)
    assert "ui-notice--muted" in err.get_attribute("class")
    expect(err.locator(".ui-visual-notice-head")).to_have_text(
        "This chart was cut off before it finished."
    )
    expect(page.locator(CHART)).to_have_count(0)


def test_complete_valid_json_without_a_closing_fence_still_draws(
    app_clean: str, page: Page
) -> None:
    text = "Before.\n\n```chart\n" + LINE + "\n"
    _open(page, app_clean, _chunks(text, 12), delay_ms=10)
    _send(page)
    _done(page)
    expect(page.locator(CHART)).to_have_count(1)


def test_a_stopped_turn_folds_an_unclosed_chart_block_into_the_group_with_the_cut_off_notice(
    app_clean: str, page: Page
) -> None:
    """Flight DD5: a stop folds the pending text into the group; the unclosed chart block there
    shows the cut-off notice (the kept `closed: false` handling) and no reply is built."""
    chunks = [
        "Before.\n\n",
        "```chart\n",
        '{"type": "bar", "x": {"val',
        'ues": ["A", "B"]}, "series": [{"val',
        'ues": [1, 2]}]}',
        "\n```\n",
    ]
    _open(page, app_clean, chunks, delay_ms=900)
    _send(page)
    expect(_chats.working_turns(page)).to_have_count(1, timeout=10000)
    expect(_chats.turn_preview(_chats.turn_group(page))).to_have_text(
        "Drawing a chart", timeout=10000
    )
    page.locator('[data-testid="chat-stop-btn"]').click()
    err = page.locator(CHART_ERROR)
    expect(err).to_have_count(1, timeout=10000)
    assert "ui-notice--muted" in err.get_attribute("class")
    # The notice lives inside the stopped group, not in a reply bubble.
    expect(page.locator(f'[data-testid="turn-work"] {CHART_ERROR}')).to_have_count(1)
    assert _chats.turn_state(_chats.turn_group(page)) == "stopped"
    expect(_chats.replies(page)).to_have_count(0)
    expect(page.locator(CHART)).to_have_count(0)
    expect(page.locator(SEND)).to_be_enabled(timeout=10000)


# ── AC8.5-8.6: history and copy ───────────────────────────────────────────────


def test_reopening_the_chat_draws_the_same_charts_and_copy_keeps_the_raw_block(
    app_clean: str, page: Page
) -> None:
    text = "One:\n\n```chart\n" + BAR + "\n```\n\n```chart\n" + PIE + "\n```\n\nEnd.\n"
    agent = _open(page, app_clean, _chunks(text, 16), delay_ms=5)
    _send(page)
    _done(page)
    expect(page.locator(CHART)).to_have_count(2)
    page.reload()
    _chats.expect_chat(page, agent)
    expect(page.locator(CHART)).to_have_count(2, timeout=10000)
    types = page.evaluate(
        "() => Array.from(document.querySelectorAll('[data-testid=\"chat-chart\"]')).map((c) => c.getAttribute('data-chart-type'))"
    )
    assert types == ["bar", "pie"]
    # Copy reply copies the raw markdown, block and all
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
    assert "```chart" in copied


# ── AC8.7: fence regression cases ─────────────────────────────────────────────

NORMALIZE_JS = """() => {
  const live = document.querySelector('[data-testid="chat-copy-status"]');
  const strip = ['id', 'for', 'aria-labelledby', 'aria-describedby', 'aria-controls', 'style'];
  const norm = (root) => {
    const types = Array.from(root.querySelectorAll('[data-testid="chat-chart"]')).map((c) => c.getAttribute('data-chart-type'));
    root.querySelectorAll('[data-testid="chat-chart"]').forEach((c) => {
      const stub = document.createElement('div');
      stub.setAttribute('data-stub', 'chart');
      stub.setAttribute('data-chart-type', c.getAttribute('data-chart-type') || '');
      const t = c.querySelector('table');
      stub.textContent = t ? t.textContent : '';
      c.replaceWith(stub);
    });
    root.querySelectorAll('*').forEach((e) => strip.forEach((a) => e.removeAttribute(a)));
    return {html: root.innerHTML, types: types};
  };
  const bubble = Array.from(document.querySelectorAll('[data-testid="message"].ui-message--assistant')).pop();
  const streamed = norm(bubble.cloneNode(true));
  // The raw text the stream carried, rendered the same way the streamed path does.
  const raw = window.__raw;
  const ref = document.createElement('div');
  ref.appendChild(App.markdown.render(raw, {copyLiveEl: live, codeBlockRenderers: {chart: (s, m) => App.ui.chart.block(s, {closed: m.closed, testid: 'chat-chart'})}}));
  return {streamed: streamed, reference: norm(ref), raw: raw};
}"""

CASES = {
    "numbered-step-with-nested-python-and-a-blank-line": (
        "1. Step one:\n   ```python\n   x = 1\n\n   y = 2\n   ```\n2. Step two\n\nDone.\n",
        0,
    ),
    "cycle-2-nested-fence-ended-by-a-column-0-line": (
        "- Step:\n  ```python\n  x = 1\n```\n\nSome text\n\nmore\n```",
        0,
    ),
    "indented-fence-line-inside-a-top-level-block": (
        "Intro\n\n```text\nline\n  ```\nstill code\n\nmore code\n```\n\nAfter\n",
        0,
    ),
    "chart-line-inside-an-open-fence-stays-code": (
        "Intro\n\n```\n```chart\n" + LINE + "\n```\n\nAfter the block\n",
        0,
    ),
    "chart-in-a-list-item": (
        "1. Revenue:\n   ```chart\n   " + LINE + "\n   ```\n\nDone.\n",
        1,
    ),
    "charts-opener-is-a-code-block": ("Intro\n\n```charts\n" + LINE + "\n```\n\nAfter\n", 0),
    "chart-fence-quoted-in-a-blockquote": (
        "Intro\n\n> ```chart\n> " + LINE + "\n> ```\n\nAfter\n",
        1,
    ),
    "chart-opener-directly-after-a-list-item": (
        "- one\n- two\n```chart\n" + LINE + "\n```\nAfter the chart.\n",
        1,
    ),
    "chart-opener-directly-after-a-blockquote": (
        "> a quote\n```chart\n" + BAR + "\n```\nAfter the chart.\n",
        1,
    ),
    "chart-opener-directly-after-a-table": (
        "| a | b |\n|---|---|\n| 1 | 2 |\n```chart\n" + PIE + "\n```\nAfter the chart.\n",
        1,
    ),
    "two-charts-back-to-back": (
        "```chart\n" + BAR + "\n```\n```chart\n" + LINE + "\n```\nEnd.\n",
        2,
    ),
    "chart-on-the-first-line-then-text": ("```chart\n" + LINE + "\n```\n\nAfter.\n", 1),
    "whitespace-then-a-chart": ("   \n\n\n```chart\n" + LINE + "\n```\n\nAfter.\n", 1),
}


@pytest.mark.parametrize("name", list(CASES))
def test_a_landed_reply_matches_a_direct_render(app_clean: str, page: Page, name: str) -> None:
    """The reply the turn lands (built once at `done` from the streamed chunks) is the same DOM
    as rendering the whole text directly, fence cases included. (Before sortie 16 this compared a
    reply committed piece by piece while it streamed.)"""
    text, _ = CASES[name]
    _open(page, app_clean, _chunks(text, 40), delay_ms=10)
    _send(page)
    _done(page)
    page.evaluate("(t) => { window.__raw = t; }", text)
    out = page.evaluate(NORMALIZE_JS)
    assert out["streamed"]["types"] == out["reference"]["types"]
    assert out["streamed"]["html"] == out["reference"]["html"], name


# ── AC8.8 and AC9: theme and the table style ──────────────────────────────────


def test_a_theme_switch_repaints_the_chart_on_screen_and_its_table_has_its_own_style(
    app_clean: str, page: Page
) -> None:
    text = "Chart:\n\n```chart\n" + BAR + "\n```\n\nEnd.\n"
    _open(page, app_clean, _chunks(text, 30), delay_ms=5)
    _send(page)
    _done(page)
    expect(page.locator(CHART)).to_have_count(1)
    page.wait_for_selector(CHART + " rect.ui-chart-bar", state="attached", timeout=10000)
    page.evaluate("() => document.documentElement.setAttribute('data-theme', 'dark')")
    read = """() => getComputedStyle(document.querySelector('[data-testid="chat-chart"] rect.ui-chart-bar')).fill"""
    assert page.evaluate(read) == "rgb(167, 139, 250)"
    page.evaluate("() => document.documentElement.setAttribute('data-theme', 'light')")
    assert page.evaluate(read) == "rgb(109, 40, 217)"
    # AC9: the chart's table is styled by its own classes, not the bubble's markdown table rules
    page.locator('[data-testid="chat-chart-data"] summary').click()
    style = page.evaluate(
        """() => {
          const th = document.querySelector('[data-testid="chat-chart"] .ui-chart-table thead th');
          const cs = getComputedStyle(th);
          return [cs.paddingLeft, cs.borderTopWidth, cs.borderBottomWidth];
        }"""
    )
    assert style[0] == "10px" and style[1] == "0px" and style[2] == "1px"


# ── AC10: scroll ──────────────────────────────────────────────────────────────

PARAS = "".join(f"Paragraph number {i} of the reply.\n\n" for i in range(40))
DIST_JS = """() => {
  const m = document.querySelector('.messages');
  return [m.scrollHeight - m.scrollTop - m.clientHeight, m.scrollHeight, m.clientHeight, m.scrollTop];
}"""


def test_a_pinned_transcript_stays_at_the_bottom_across_a_chart(app_clean: str, page: Page) -> None:
    chunks = [PARAS, "```chart\n", BAR[:30], BAR[30:] + "\n", "```\n", "Tail text.\n"]
    _open(page, app_clean, chunks, delay_ms=300)
    _send(page)
    expect(page.locator(CHART)).to_have_count(1, timeout=20000)
    _done(page)
    page.wait_for_timeout(400)  # the chart's first layout lands after the swap
    dist, height, client, _ = page.evaluate(DIST_JS)
    assert height > client + 200, "the transcript must overflow for this test to mean anything"
    assert dist <= 4, dist


def test_a_reader_who_scrolled_up_is_never_pulled_down_by_a_chart(
    app_clean: str, page: Page
) -> None:
    # The reader scrolls up while a turn runs; when its reply (a chart) lands at `done`, the
    # transcript must not pull them down. The first turn makes the log overflow.
    _open(page, app_clean, [PARAS, "More text.\n\n"], delay_ms=10)
    _send(page)
    _done(page)
    assert page.evaluate(DIST_JS)[1] > page.evaluate(DIST_JS)[2] + 300, (
        "must overflow well past 80px"
    )
    page.evaluate("() => { document.querySelector('.messages').scrollTop = 0; }")
    for f in (
        {"type": "user", "content": "again"},
        {"type": "assistant", "content": "A chart:\n\n```chart\n" + BAR + "\n```\n"},
    ):
        _chats.emit_frame(page, f)
    expect(_chats.working_turns(page)).to_have_count(1)
    _chats.emit_frame(page, {"type": "done"})
    expect(page.locator(CHART)).to_have_count(1, timeout=20000)
    page.wait_for_timeout(400)
    assert page.evaluate(DIST_JS)[3] <= 8
