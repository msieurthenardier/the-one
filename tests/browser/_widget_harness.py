# ruff: noqa: E501  (the in-page scripts are evaluated verbatim)
"""Shared helpers for the widget frame contract tests (M35 F2 L1 and L3).

The widget contract files (``test_ui_widget_frame_*``) load the library at a real http URL served
by the sink (``_widget_sink.WidgetSink``) and mount widgets through ``window.__mount``. Not a test
module: the ``contracts-widget`` lane globs ``test_ui_widget*`` only.
"""

from __future__ import annotations

from browser._ui_engines import load_harness
from browser._widget_sink import WidgetSink
from playwright.sync_api import Page

INITIAL_HEIGHT = 240


def engine(page: Page) -> str:
    return page.context.browser.browser_type.name


def load(page: Page, sink: WidgetSink, theme: str = "dark") -> None:
    sink.reset()
    load_harness(page, theme=theme, url=sink.harness_url)
    page.evaluate(
        """() => {
          window.__esc = 0; window.__beats = 0; window.__sizes = [];
          window.__pop = 0; window.addEventListener('popstate', () => window.__pop++);
          window.__url0 = location.href;
          window.__mount = (source, extra) => {
            const slot = document.createElement('div');
            document.getElementById('harness-root').appendChild(slot);
            window.__slot = slot;
            window.__h = App.ui.widgetFrame(Object.assign({
              slot, source, title: 'Test widget',
              onEscape: () => window.__esc++, onHeartbeat: () => window.__beats++,
              onSize: (h) => window.__sizes.push(h),
            }, extra || {}));
            return window.__h;
          };
        }"""
    )


def mount(page: Page, source: str, wait_load: bool = True, **extra) -> None:
    page.evaluate("([s, x]) => { window.__mount(s, x); }", [source, extra])
    if wait_load:
        page.wait_for_function("() => __h.loads() >= 1")


def frame(page: Page):
    frames = [f for f in page.frames if f != page.main_frame]
    assert frames, "no widget frame"
    return frames[0]


def add_page_textarea(page: Page) -> None:
    """A page textarea above the widget: the operator's composer stand-in."""
    page.evaluate(
        """() => {
          const t = document.createElement('textarea');
          t.id = 'ptext';
          t.style.cssText = 'display:block;width:300px;height:60px;margin:4px';
          document.getElementById('harness-root').appendChild(t);
        }"""
    )


def click_in_frame(page: Page, x: float, y: float) -> None:
    """A REAL mouse click at (x, y) inside the widget's iframe (never ``frame.evaluate``, which
    grants user activation)."""
    box = page.locator("iframe").first.bounding_box()
    assert box is not None, "iframe has no box"
    page.mouse.click(box["x"] + x, box["y"] + y)


# ---- managed cards (M35 F2 L5, the lifecycle and hang contract files) ----------------------

COUNTER = (
    '<div style="height:100px">w</div><script>window.__n = 0;'
    "setInterval(function () { window.__n++; }, 20);</script>"
)


def setup_cards(page: Page, sink: WidgetSink, theme: str = "dark") -> None:
    """Load the library and define ``__make(source, extra)``, which builds a MANAGED card with
    the testid ``w{i}`` and the key ``k{i}`` and appends it to ``#stack`` (cards in document order).
    ``__states()`` lists every card's state."""
    load(page, sink, theme=theme)
    page.evaluate(
        """() => {
          const stack = document.createElement('div');
          stack.id = 'stack';
          const st = document.createElement('style');
          st.textContent = '#stack > * { margin: 8px 0; }';
          document.head.appendChild(st);
          document.getElementById('harness-root').appendChild(stack);
          window.__cards = [];
          window.__make = (source, extra) => {
            const i = window.__cards.length;
            const c = App.ui.widget(Object.assign({source, agentName: 'Ada', testid: 'w' + i, key: 'k' + i}, extra || {}));
            window.__cards.push(c);
            stack.appendChild(c.el);
            return c;
          };
          window.__states = () => window.__cards.map((c) => c.state());
        }"""
    )


def make_cards(page: Page, n: int, source: str = COUNTER, **extra) -> None:
    page.evaluate(
        "([n, s, x]) => { for (let i = 0; i < n; i++) __make(s, x); }", [n, source, extra]
    )


def states(page: Page) -> list[str]:
    return page.evaluate("() => __states()")


def wait_states(page: Page, expected: list[str], timeout: int = 8000) -> None:
    page.wait_for_function(
        "(e) => JSON.stringify(__states()) === JSON.stringify(e)", arg=expected, timeout=timeout
    )


def card_frame(page: Page, i: int):
    """The Playwright Frame of card ``i`` (None when it has no frame)."""
    loc = page.locator(f"[data-testid=w{i}-frame]")
    if loc.count() == 0:
        return None
    return loc.first.element_handle().content_frame()


def counter(page: Page, i: int) -> int:
    f = card_frame(page, i)
    assert f is not None, f"card {i} has no frame"
    return int(f.evaluate("() => window.__n"))


def scroll_to_card(page: Page, i: int) -> None:
    page.evaluate("(i) => __cards[i].el.scrollIntoView({block: 'start'})", i)


def fake_hidden(page: Page, hidden: bool) -> None:
    """Emulate ``document.hidden`` and dispatch ``visibilitychange``; ``delete`` restores."""
    page.evaluate(
        """(h) => {
          if (h) {
            Object.defineProperty(document, 'hidden', {configurable: true, get: () => true});
            Object.defineProperty(document, 'visibilityState', {configurable: true, get: () => 'hidden'});
          } else {
            delete document.hidden;
            delete document.visibilityState;
          }
          document.dispatchEvent(new Event('visibilitychange'));
        }""",
        hidden,
    )
