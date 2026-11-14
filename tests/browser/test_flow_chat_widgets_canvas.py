# ruff: noqa: E501  (inline widget sources and JS snippets are evaluated verbatim)
"""Canvas widgets written like a real model writes them (M35 F2 HAT step 9), on the real chat page,
in Chromium and WebKit: a widget that sizes its canvas from ``offsetWidth`` when it starts must
paint without a Restart, in a reply that lands at the end of a streamed turn (sortie 16: it is
mounted when the reply lands) and from history, and its frame must never scroll. The
``chats-widgets`` lane."""

from __future__ import annotations

import pytest
from browser import _chats, _nav
from browser._ui_engines import engine_browser  # noqa: F401  (fixture)
from browser.seeders import seed_mock_agent, seed_mock_provider, seed_session
from playwright.sync_api import Page, expect

from the_one.db.codec import encode_messages
from the_one.llm.base import Message

pytestmark = pytest.mark.browser

CARD = '[data-testid="chat-widget"]'


@pytest.fixture(scope="module")
def browser(engine_browser):  # noqa: F811
    return engine_browser


# Sizes the canvas from the layout once at start (the way the model's pendulum and balls do) and
# draws every frame; a 2px border on a 100%-wide, 300px-high canvas.
CANVAS = """<canvas id="canvas"></canvas>
<style>canvas{display:block;background:var(--surface);width:100%;height:300px;border:2px solid var(--fg)}</style>
<script>
const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');
canvas.width = canvas.offsetWidth;
canvas.height = canvas.offsetHeight;
window.__w = canvas.width;
function animate() {
  ctx.fillStyle = '#e33';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  requestAnimationFrame(animate);
}
animate();
</script>"""

REPLY = (
    "Here you go.\n\n```widget\n"
    + CANVAS
    + "\n```\nClosing words that keep streaming for a while after it."
)

PROBE = """() => {
  const c = document.getElementById('canvas');
  const d = document.documentElement;
  const g = c.getContext('2d').getImageData(Math.floor(c.width / 2), Math.floor(c.height / 2), 1, 1).data;
  return { w: window.__w, cw: c.width, red: g[0], sw: d.scrollWidth, cwid: d.clientWidth,
           sh: d.scrollHeight, ch: d.clientHeight, bsw: document.body.scrollWidth,
           iw: window.innerWidth };
}"""


def _agent(base: str, config: dict) -> str:
    return seed_mock_agent(
        base, seed_mock_provider(base, name="mock-canvas", config=config), name="cv"
    )


def _probe(page: Page) -> dict:
    handle = page.locator(CARD).first.locator("iframe").element_handle()
    f = handle.content_frame()
    assert f is not None
    return f.evaluate(PROBE)


def _check(page: Page) -> None:
    expect(page.locator(CARD).first.locator("iframe")).to_have_count(1, timeout=15000)
    page.wait_for_timeout(1500)
    p = _probe(page)
    assert p["w"] > 100, p  # the canvas was sized from a real, laid-out width at start
    assert p["red"] > 200, p  # and it painted without a Restart
    assert p["sw"] <= p["cwid"] and p["sh"] <= p["ch"] and p["bsw"] <= p["iw"], p  # no scrollbars


def test_a_canvas_widget_in_a_streamed_reply_paints_when_it_lands_and_does_not_scroll(
    app_clean: str, page: Page
) -> None:
    chunks = [REPLY[i : i + 40] for i in range(0, len(REPLY), 40)]
    agent = _agent(app_clean, {"stream_chunks": chunks, "delay_ms": 10})
    page.goto(app_clean)
    _chats.start_chat(page, agent)
    _chats.send_first(page, "go")
    _check(page)


def test_history_canvas_widget_below_the_fold_paints_when_scrolled_into_view(
    app_clean: str, page: Page
) -> None:
    agent = _agent(app_clean, {"response": {"content": "x"}})
    filler = "\n\n".join(
        f"Paragraph {i} of filler text that makes the reply tall." for i in range(60)
    )
    msgs = [
        Message.user("show"),
        Message.assistant(filler + "\n\n```widget\n" + CANVAS + "\n```\nEnd."),
    ]
    sid = seed_session(
        app_clean, agent, "hist2", "2026-10-27T09:00:00+00:00", messages=encode_messages(msgs)
    )
    page.set_viewport_size({"width": 1440, "height": 900})
    _nav.goto(page, app_clean, "chats")
    _chats.open_chat(page, sid)
    page.evaluate("() => { document.querySelector('.messages').scrollTop = 0; }")
    page.wait_for_timeout(800)
    page.locator(CARD).first.scroll_into_view_if_needed()
    _check(page)


def test_history_canvas_widget_paints_and_does_not_scroll(app_clean: str, page: Page) -> None:
    agent = _agent(app_clean, {"response": {"content": "x"}})
    msgs = [Message.user("show"), Message.assistant(REPLY)]
    sid = seed_session(
        app_clean, agent, "hist", "2026-10-27T09:00:00+00:00", messages=encode_messages(msgs)
    )
    page.set_viewport_size({"width": 1440, "height": 900})
    _nav.goto(page, app_clean, "chats")
    _chats.open_chat(page, sid)
    _check(page)
