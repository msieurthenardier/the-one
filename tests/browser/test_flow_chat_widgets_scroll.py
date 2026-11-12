# ruff: noqa: E501  (inline widget sources and JS snippets are evaluated verbatim)
"""Scrolling up a long chat of animated widgets (M35 F2 HAT step 4), on the REAL chat page, in
Chromium and WebKit.

The chat opens at the bottom, so every card above is never seen: it sits at the initial slot height
and first-loads (to its real height) while the reader scrolls up. That first mount must not move the
reader's scroll position (in WebKit it jumped by a whole slot). The ``chats-widgets`` lane.

What this proves: in headless Chromium and WebKit, with Playwright's wheel (which scrolls at once,
not with the smooth-scroll animation a real wheel uses), scrollTop never rises while scrolling up
a Long chat. It guards the WebKit mount-clearing jump. It does NOT prove the smooth-wheel anchoring
case in desktop Chrome (the pre-layout 48 px report); that one is pinned structurally by the
slot-height sequence tests in ``test_ui_widget_lifecycle_contract.py`` and was checked by hand in
headed Chrome.
"""

from __future__ import annotations

import pytest
from browser import _chats, _nav
from browser._ui_engines import engine_browser  # noqa: F401  (fixture)
from browser.seeders import seed_mock_agent, seed_mock_provider, seed_session
from playwright.sync_api import Page

from the_one.db.codec import encode_messages
from the_one.llm.base import Message

pytestmark = pytest.mark.browser


@pytest.fixture(scope="module")
def browser(engine_browser):  # noqa: F811
    """Every test here runs in both engines: ``page`` builds on this."""
    return engine_browser


def small_widget(i: int) -> str:
    return f"""<title>Frame counter {i}</title>
<div style="font-family:sans-serif;color:var(--fg)"><canvas id="c" width="300" height="60" style="width:100%;max-width:300px"></canvas>
<div>Frames: <span id="n">0</span></div></div>
<script>let n = 0; const c = document.getElementById('c'), g = c.getContext('2d');
function f() {{ n++; document.getElementById('n').textContent = n; window.__n = n;
g.fillStyle = '#888'; g.fillRect(0, 0, 300, 60); g.fillStyle = '#08f'; g.fillRect((n * 3) % 280, 20, 20, 20); requestAnimationFrame(f); }}
requestAnimationFrame(f);</script>"""


def _long_chat(base: str) -> str:
    provider = seed_mock_provider(base, name="mock-scroll", config={"response": {"content": "x"}})
    agent = seed_mock_agent(base, provider, name="scroll-agent")
    msgs: list[Message] = []
    for i in range(1, 13):
        msgs.append(Message.user(f"Show me widget number {i}."))
        msgs.append(
            Message.assistant(
                f"Widget number {i} follows; it counts frames.\n\n```widget\n{small_widget(i).strip()}\n```\nThat was widget {i} of 12."
            )
        )
    return seed_session(
        base, agent, "Long chat", "2026-10-27T09:00:00+00:00", messages=encode_messages(msgs)
    )


@pytest.mark.parametrize("viewport", [(1280, 900), (1024, 640)], ids=["1280", "1024"])
def test_scrolling_up_a_long_widget_chat_never_jumps(
    app_clean: str, page: Page, viewport: tuple[int, int]
) -> None:
    sid = _long_chat(app_clean)
    page.set_viewport_size({"width": viewport[0], "height": viewport[1]})
    _nav.goto(page, app_clean, "chats")
    _chats.open_chat(page, sid)
    page.wait_for_function(
        "() => document.querySelectorAll('[data-testid=\"chat-widget\"]').length === 12", timeout=15000
    )
    page.wait_for_timeout(1500)
    page.evaluate(
        """() => {
          const m = document.querySelector('.messages');
          window.__m = m;
          m.scrollTop = m.scrollHeight;
          window.__log = [];
          (function tick() { window.__log.push(m.scrollTop); requestAnimationFrame(tick); })();
        }"""
    )
    page.wait_for_timeout(1200)
    box = page.locator(".messages").first.bounding_box()
    assert box is not None
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.evaluate("() => { window.__log.length = 0; }")
    steps = 0
    for _ in range(160):
        if page.evaluate("() => __m.scrollTop") < 5:
            break
        page.mouse.wheel(0, -60)
        page.wait_for_timeout(100)
        steps += 1
    log = page.evaluate("() => window.__log")
    assert steps > 40 and page.evaluate("() => __m.scrollTop") < 5
    # The reader only ever moves up: no frame may raise scrollTop (a jump toward the bottom).
    ups = [(a, b) for a, b in zip(log, log[1:]) if b > a + 1]
    assert ups == [], ups[:5]
