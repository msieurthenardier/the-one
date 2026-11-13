# ruff: noqa: E501  (inline widget sources and JS snippets are evaluated verbatim)
"""A canvas widget sized from ``offsetWidth`` at start, on the real chat page, in a Chromium with
site isolation for sandboxed frames (M35 F2 HAT step 9, amended DD2).

Under ``--site-per-process --enable-features=IsolateSandboxedIframes`` (the default of desktop
Chrome and Edge, and so of WebView2) a sandboxed ``srcdoc`` child learns its viewport width only
once the parent has laid the iframe out. A frame given its document at insertion saw width 0 when
its script ran, so a canvas sized from ``offsetWidth`` was 0 wide and blank until Restart. The frame
is now inserted, laid out, and only then given its document. The ``chats-widgets`` lane; Chromium
only (it launches its own browser and skips cleanly when the isolation cannot be had).
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from browser import _chats, _nav
from browser._ui_engines import isolated_chromium_policy
from browser.seeders import seed_mock_agent, seed_mock_provider, seed_session
from playwright.sync_api import Browser, Page, expect

from the_one.db.codec import encode_messages
from the_one.llm.base import Message, ToolCall, ToolResult

pytestmark = pytest.mark.browser

CARD = '[data-testid="chat-widget"]'
ARGS = ["--site-per-process", "--enable-features=IsolateSandboxedIframes"]

CANVAS = """<canvas id="canvas"></canvas>
<style>canvas{display:block;background:var(--surface);width:100%;height:400px}</style>
<script>
const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');
canvas.width = canvas.offsetWidth;
canvas.height = canvas.offsetHeight;
function animate() { ctx.fillStyle = '#e33'; ctx.fillRect(0, 0, canvas.width, canvas.height); requestAnimationFrame(animate); }
animate();
</script>"""

PROBE_PAGE = (
    "<!doctype html><body style='margin:0'><div id=s style='width:700px'></div><script>"
    "window.res=[];addEventListener('message',e=>res.push(e.data));"
    "const f=document.createElement('iframe');f.setAttribute('sandbox','allow-scripts');"
    "f.style.cssText='display:block;width:100%;height:50px;border:0';"
    "f.srcdoc='<script>parent.postMessage(document.documentElement.clientWidth,\"*\")<\\/script>';"
    "document.getElementById('s').appendChild(f);</script>"
)


@pytest.fixture(scope="module")
def browser(playwright_instance) -> Iterator[Browser]:  # noqa: ANN001
    def decide(problem: str | None) -> None:
        r = isolated_chromium_policy(os.environ, problem)
        if r.kind == "fail":
            pytest.fail(r.reason)
        if r.kind == "skip":
            pytest.skip(r.reason)

    try:
        b = playwright_instance.chromium.launch(headless=True, args=ARGS)
    except Exception as exc:  # pragma: no cover - environment dependent
        decide(f"cannot launch an isolating Chromium: {exc}")
        raise
    # The test is vacuous unless the isolation really gives an early child width of 0.
    probe = b.new_page()
    probe.set_content(PROBE_PAGE)
    probe.wait_for_timeout(800)
    early = probe.evaluate("() => window.res[0]")
    probe.close()
    problem = (
        None
        if early == 0
        else f"this Chromium does not isolate sandboxed frames (early width {early})"
    )
    try:
        decide(problem)
    except BaseException:
        b.close()
        raise
    yield b
    b.close()


def _history(base: str) -> str:
    prov = seed_mock_provider(base, name="mock-iso", config={"response": {"content": "x"}})
    agent = seed_mock_agent(base, prov, name="iso-agent")
    msgs = [
        Message.user("Make an animation."),
        Message.assistant("", tool_calls=[ToolCall(id="t1", name="current_time", arguments={})]),
        Message.tool(ToolResult(tool_call_id="t1", content="2026-11-11T20:06:31-06:00")),
        Message.assistant("Here you go:\n\n```widget\n" + CANVAS + "\n```\nEnjoy."),
    ]
    return seed_session(
        base, agent, "iso", "2026-10-27T09:00:00+00:00", messages=encode_messages(msgs)
    )


def _state(page: Page) -> dict:
    handle = page.locator(CARD).first.locator("iframe").element_handle()
    f = handle.content_frame()
    assert f is not None
    return f.evaluate(
        """() => { const c = document.getElementById('canvas');
          const g = c.getContext('2d').getImageData(Math.floor(c.width / 2), Math.floor(c.height / 2), 1, 1).data;
          return { w: c.width, h: c.height, red: g[0] }; }"""
    )


def test_canvas_sized_from_offsetwidth_paints_and_survives_restart(
    app_clean: str, page: Page
) -> None:
    sid = _history(app_clean)
    page.set_viewport_size({"width": 1440, "height": 900})
    _nav.goto(page, app_clean, "chats")
    _chats.open_chat(page, sid)
    expect(page.locator(CARD).first.locator("iframe")).to_have_count(1, timeout=15000)
    page.wait_for_timeout(1500)
    first = _state(page)
    assert first["w"] > 100 and first["h"] > 100 and first["red"] > 200, first
    page.locator('[data-testid="chat-widget-restart"]').first.click()
    expect(page.locator(CARD).first.locator("iframe")).to_have_count(1, timeout=15000)
    page.wait_for_timeout(1500)
    again = _state(page)
    assert again["w"] > 100 and again["h"] > 100 and again["red"] > 200, again
