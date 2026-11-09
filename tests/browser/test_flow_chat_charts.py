# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Browser flow tests for charts in chat (M35 F1 L2, flight DD6, DD8, DD10, DD14).

A ``chart`` fenced block in an assistant reply is drawn as a chart, live (the streaming
placeholder, then the chart the moment the closing fence line arrives) and in history. The mock
provider streams explicit ``stream_chunks`` so the opener, the ``"type"`` key and the closing
fence fall in separate chunks. Streamed replies are compared with a non-streamed render of the
same text after normalising each chart subtree (parser-confirmed boundaries must never split a
fence). Assertions are structural; no pixels and no snapshots.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from browser import _chats
from browser.seeders import seed_mock_agent, seed_mock_provider
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

CORPUS = Path(__file__).resolve().parent.parent / "fixtures" / "charts" / "valid"
LINE = json.dumps(json.loads((CORPUS / "line-minimal.json").read_text(encoding="utf-8")))
BAR = json.dumps(json.loads((CORPUS / "bar-minimal.json").read_text(encoding="utf-8")))
PIE = json.dumps(json.loads((CORPUS / "pie-minimal.json").read_text(encoding="utf-8")))

PLACEHOLDER = '[data-testid="chat-chart-placeholder"]'
CHART = '[data-testid="chat-chart"]'
CHART_ERROR = '[data-testid="chat-chart-error"]'
SEND = '[data-testid="chat-send-btn"]'

# Notes a page-side watcher keeps: how many placeholders were ever added, and parse calls.
WATCH_JS = """() => {
  window.__ph = 0;
  new MutationObserver((recs) => {
    for (const r of recs) for (const n of r.addedNodes) {
      if (n.nodeType !== 1) continue;
      if (n.matches('[data-testid="chat-chart-placeholder"]') || n.querySelector('[data-testid="chat-chart-placeholder"]')) window.__ph++;
    }
  }).observe(document.body, {childList: true, subtree: true});
  window.__parses = 0;
  const real = App.markdown.parse;
  App.markdown.parse = function (t) { window.__parses++; return real.call(App.markdown, t); };
}"""


def _chunks(text: str, size: int) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]


def _open(page: Page, base_url: str, chunks: list[str], delay_ms: int = 0, watch: bool = False):
    provider_id = seed_mock_provider(
        base_url, config={"stream_chunks": chunks, "delay_ms": delay_ms}
    )
    agent = seed_mock_agent(base_url, provider_id)
    page.goto(base_url)
    _chats.start_chat(page, agent)
    if watch:
        page.evaluate(WATCH_JS)
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


def test_streamed_chart_shows_the_placeholder_then_the_chart_before_the_stream_ends(
    app_clean: str, page: Page
) -> None:
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
    _send(page)
    bubble = _bubble(page)
    # the text before the fence is committed as markdown
    expect(bubble.locator("p")).to_have_count(1, timeout=10000)
    ph = page.locator(PLACEHOLDER)
    expect(ph).to_be_visible(timeout=10000)
    expect(ph).to_contain_text("Rendering chart")
    # no raw fence or JSON is visible while the placeholder shows (the source well is closed)
    visible = bubble.evaluate("(el) => el.innerText")
    assert "```" not in visible and '{"type"' not in visible
    expect(ph).to_contain_text("Rendering line chart", timeout=10000)
    # "Show source" holds the partial JSON
    ph.locator("summary").click()
    expect(page.locator('[data-testid="chat-chart-placeholder-source"]')).to_contain_text('"line"')
    # the chart replaces the placeholder at the closing fence, while the text after still streams
    expect(page.locator(CHART)).to_have_count(1, timeout=15000)
    expect(page.locator(PLACEHOLDER)).to_have_count(0)
    assert "Closing words" not in bubble.inner_text()
    expect(page.locator(SEND)).to_be_disabled()
    _done(page)
    assert _child_tags(page) == ["p", "figure", "p"]
    expect(bubble.locator("p").last).to_have_text("Closing words.")


# ── AC8.2-8.4 ─────────────────────────────────────────────────────────────────


def test_a_reply_ending_with_a_chart_draws_it_at_finalize(app_clean: str, page: Page) -> None:
    text = "Here it is:\n\n```chart\n" + LINE + "\n```"  # a bare final fence: finalize-only
    _open(page, app_clean, _chunks(text, 14), delay_ms=20)
    _send(page)
    _done(page)
    expect(page.locator(CHART)).to_have_count(1)
    expect(page.locator(PLACEHOLDER)).to_have_count(0)
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
    expect(err.locator(".ui-chart-error-head")).to_have_text("Couldn't draw this chart.")
    assert err.locator(".ui-chart-error-reason").inner_text().strip() != ""
    assert 'type": "bar"' in err.locator("details pre").text_content()
    bubble = _bubble(page)
    expect(bubble.locator("p").first).to_have_text("Before.")
    expect(bubble.locator("p").last).to_have_text("Rest of the reply.")
    expect(page.locator(PLACEHOLDER)).to_have_count(0)


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
    expect(err.locator(".ui-chart-error-head")).to_have_text(
        "This chart was cut off before it finished."
    )
    expect(page.locator(PLACEHOLDER)).to_have_count(0)
    expect(page.locator(CHART)).to_have_count(0)


def test_complete_valid_json_without_a_closing_fence_still_draws(
    app_clean: str, page: Page
) -> None:
    text = "Before.\n\n```chart\n" + LINE + "\n"
    _open(page, app_clean, _chunks(text, 12), delay_ms=10)
    _send(page)
    _done(page)
    expect(page.locator(CHART)).to_have_count(1)
    expect(page.locator(PLACEHOLDER)).to_have_count(0)


def test_stop_in_the_middle_of_a_block_leaves_the_cut_off_notice(
    app_clean: str, page: Page
) -> None:
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
    expect(page.locator(PLACEHOLDER)).to_be_visible(timeout=10000)
    page.locator('[data-testid="chat-stop-btn"]').click()
    err = page.locator(CHART_ERROR)
    expect(err).to_have_count(1, timeout=10000)
    assert "ui-notice--muted" in err.get_attribute("class")
    expect(page.locator(PLACEHOLDER)).to_have_count(0)
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
    expect(page.locator(PLACEHOLDER)).to_have_count(0)
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
def test_streamed_reply_matches_a_non_streamed_render(
    app_clean: str, page: Page, name: str
) -> None:
    text, _ = CASES[name]
    # 5 characters every 100 ms is slower than the 16 ms pacing drains, so every tick sees the
    # tail grow by a little and the commit logic runs at each boundary (a fast stream would be
    # drained in one go at `done`, exercising nothing).
    _open(page, app_clean, _chunks(text, 5), delay_ms=100, watch=True)
    _send(page)
    _done(page)
    expect(page.locator(PLACEHOLDER)).to_have_count(0)
    page.evaluate("(t) => { window.__raw = t; }", text)
    out = page.evaluate(NORMALIZE_JS)
    assert out["streamed"]["types"] == out["reference"]["types"]
    assert out["streamed"]["html"] == out["reference"]["html"], name
    if name in (
        "chart-line-inside-an-open-fence-stays-code",
        "charts-opener-is-a-code-block",
        "chart-in-a-list-item",
        "chart-fence-quoted-in-a-blockquote",
        "cycle-2-nested-fence-ended-by-a-column-0-line",
    ):
        assert page.evaluate("() => window.__ph") == 0, "no placeholder for a non-top-level chart"


# ── AC6 perf: the parser is not called per tick ───────────────────────────────


def test_parse_count_stays_bounded_after_a_nested_fence_the_parser_leaves_open(
    app_clean: str, page: Page
) -> None:
    text = "- Step:\n  ```python\n  x = 1\n```\n\n" + "Para.\n\n" * 30
    _open(page, app_clean, _chunks(text, 5), delay_ms=100, watch=True)
    _send(page)
    _done(page)
    parses = page.evaluate("() => window.__parses")
    assert parses <= 8, parses


def test_one_long_unclosed_top_level_fence_never_asks_the_parser(
    app_clean: str, page: Page
) -> None:
    text = "```text\n" + "code\n\n" * 30
    _open(page, app_clean, _chunks(text, 5), delay_ms=100, watch=True)
    _send(page)
    _done(page)
    assert page.evaluate("() => window.__parses") == 0
    expect(_bubble(page).locator("pre")).to_have_count(1)


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
    chunks = [PARAS, "More text.\n\n", "```chart\n", BAR + "\n", "```\n", "Tail text.\n"]
    _open(page, app_clean, chunks, delay_ms=500)
    _send(page)
    expect(_bubble(page)).to_contain_text("Paragraph number 39", timeout=20000)
    assert page.evaluate(DIST_JS)[1] > page.evaluate(DIST_JS)[2] + 300, (
        "must overflow well past 80px"
    )
    page.evaluate("() => { document.querySelector('.messages').scrollTop = 0; }")
    expect(page.locator(CHART)).to_have_count(1, timeout=20000)
    _done(page)
    page.wait_for_timeout(400)
    assert page.evaluate(DIST_JS)[3] <= 8
