# ruff: noqa: E501  (inline widget sources are evaluated verbatim)
"""The widget frame's focus gate (M35 F2 L3, AC1, DD10): focus stays the operator's.

In Chromium a sandboxed frame's ``input.focus()`` takes focus from the page's composer even with
no user activation, so the operator's typing would go to the widget. The prelude replaces every
``focus`` so it runs only while ``navigator.userActivation.isActive`` is true AND a trusted
gesture happened inside the frame within about a second. Measurements use real
``page.mouse`` / ``page.keyboard`` input and in-frame counters: ``frame.evaluate`` grants user
activation and would hide the very thing under test. Headless WebKit never shows the steal, so
the two steal tests are Chromium-only; the positive tests run in both engines.
"""

from __future__ import annotations

import pytest
from browser._widget_harness import add_page_textarea, click_in_frame, frame, load, mount
from browser._widget_sink import WidgetSink
from playwright.sync_api import Page

pytestmark = pytest.mark.browser

# An input over a button, both 200x30 at the frame's top-left. `__fid` is the id of the element
# that last took focus (in-frame, never read through a call that grants activation).
BASE = (
    "<style>body{margin:0}input,button{display:block;box-sizing:border-box;width:200px;height:30px;margin:0}</style>"
    "<input id=i><button id=b>b</button>"
    "<script>window.__fid = ''; window.__ready = false;"
    "document.addEventListener('focusin', function (e) { window.__fid = e.target.id; });"
)


def _src(extra: str) -> str:
    return BASE + extra + "window.__ready = true;</script>"


@pytest.fixture(scope="module")
def sink():
    s = WidgetSink()
    try:
        yield s
    finally:
        s.close()


def _chromium_only(page: Page) -> None:
    if page.context.browser.browser_type.name != "chromium":
        pytest.skip("headless WebKit never shows the focus steal; Chromium is the falsifier")


def _setup(page: Page, sink: WidgetSink, extra: str = "", **mount_opts) -> None:
    load(page, sink)
    add_page_textarea(page)
    mount(page, _src(extra), **mount_opts)
    frame(page).wait_for_function("() => window.__ready === true")
    page.wait_for_timeout(300)


def _textarea_length(page: Page) -> int:
    return int(page.evaluate("() => document.getElementById('ptext').value.length"))


def test_a_focus_loop_cannot_steal_typing_from_the_page(
    engine_page: Page, sink: WidgetSink
) -> None:
    """(a) Chromium: the page textarea has focus, the widget calls input.focus() every 10 ms, the
    operator types 40 characters: all 40 land in the textarea."""
    _chromium_only(engine_page)
    _setup(
        engine_page, sink, "setInterval(function () { document.getElementById('i').focus(); }, 10);"
    )
    engine_page.focus("#ptext")
    engine_page.keyboard.type("x" * 40, delay=20)
    assert _textarea_length(engine_page) == 40
    assert frame(engine_page).evaluate("() => window.__fid") == ""


def test_transient_activation_does_not_let_the_loop_steal_back(
    engine_page: Page, sink: WidgetSink
) -> None:
    """(b) Chromium: a real click into the widget's input focuses it and typing reaches it. The
    click leaves transient activation on for about 5 s, so a gate on isActive alone would let a
    loop that starts later steal the operator's typing. Here the loop starts 2 s after the click
    (past the 1 s gesture window) and the operator types into the page textarea: at least 39 of
    40 characters land there."""
    _chromium_only(engine_page)
    _setup(
        engine_page,
        sink,
        "document.addEventListener('click', function () { setTimeout(function () {"
        "setInterval(function () { document.getElementById('i').focus(); }, 10); }, 2000); }, true);",
    )
    click_in_frame(engine_page, 20, 15)
    frame(engine_page).wait_for_function("() => window.__fid === 'i'")
    engine_page.keyboard.type("abc")
    assert frame(engine_page).evaluate("() => document.getElementById('i').value") == "abc"
    engine_page.click("#ptext")
    engine_page.wait_for_timeout(2300)
    engine_page.keyboard.type("y" * 40, delay=25)
    got = _textarea_length(engine_page)
    print(f"[widget-focus] chromium typed 40 after a click inside the widget: {got}/40")
    assert got >= 39


def test_a_real_click_focuses_the_widgets_input_and_typing_reaches_it(
    engine_page: Page, sink: WidgetSink
) -> None:
    """(c) both engines."""
    _setup(engine_page, sink)
    click_in_frame(engine_page, 20, 15)
    frame(engine_page).wait_for_function("() => window.__fid === 'i'")
    engine_page.keyboard.type("hello")
    assert frame(engine_page).evaluate("() => document.getElementById('i').value") == "hello"


def test_tab_from_the_page_focuses_the_first_focusable_element(
    engine_page: Page, sink: WidgetSink
) -> None:
    """(d) both engines: Tab into the frame is the browser's own focus move, not a focus() call."""
    _setup(engine_page, sink)
    engine_page.focus("#ptext")
    engine_page.keyboard.press("Tab")
    frame(engine_page).wait_for_function("() => window.__fid === 'i'")


def test_a_click_handler_may_move_focus_to_an_input(engine_page: Page, sink: WidgetSink) -> None:
    """(e) both engines: the click is a trusted gesture under a second old, so the widget's own
    handler can call input.focus()."""
    _setup(
        engine_page,
        sink,
        "document.getElementById('b').addEventListener('click', function () { document.getElementById('i').focus(); });",
    )
    click_in_frame(engine_page, 20, 45)
    frame(engine_page).wait_for_function("() => window.__fid === 'i'")
    engine_page.keyboard.type("ok")
    assert frame(engine_page).evaluate("() => document.getElementById('i').value") == "ok"


def test_keyboard_only_use_may_move_focus_from_a_button(
    engine_page: Page, sink: WidgetSink
) -> None:
    """Edge case: Tab into the frame, Tab to the button, Enter on it; keydown is a trusted gesture."""
    _setup(
        engine_page,
        sink,
        "document.getElementById('b').addEventListener('click', function () { window.__clicked = true; document.getElementById('i').focus(); });",
    )
    engine_page.focus("#ptext")
    engine_page.keyboard.press("Tab")
    frame(engine_page).wait_for_function("() => window.__fid === 'i'")
    engine_page.keyboard.press("Tab")
    frame(engine_page).wait_for_function("() => window.__fid === 'b'")
    engine_page.keyboard.press("Enter")
    frame(engine_page).wait_for_function("() => window.__clicked === true")
    frame(engine_page).wait_for_function("() => window.__fid === 'i'")


def test_autofocus_cannot_take_focus_from_the_page(engine_page: Page, sink: WidgetSink) -> None:
    """The autofocus attribute is stripped and its property neutered; the page keeps its focus."""
    load(engine_page, sink)
    add_page_textarea(engine_page)
    engine_page.focus("#ptext")
    mount(
        engine_page,
        "<input id=a autofocus><script>window.__r = {prop: (function () { var x = document.createElement('input'); x.autofocus = true; return x.autofocus; })()};"
        "setTimeout(function () { var d = document.createElement('input'); d.setAttribute('autofocus', ''); document.body.appendChild(d); window.__ready = true; }, 100);</script>",
    )
    frame(engine_page).wait_for_function("() => window.__ready === true")
    engine_page.wait_for_timeout(400)
    engine_page.keyboard.type("z" * 10)
    assert _textarea_length(engine_page) == 10
    assert frame(engine_page).evaluate("() => document.querySelectorAll('[autofocus]').length") == 0
    assert frame(engine_page).evaluate("() => window.__r.prop") is False


def test_the_focus_wrappers_cannot_be_replaced(engine_page: Page, sink: WidgetSink) -> None:
    """The wrapped functions are non-configurable and non-writable; a widget cannot put the
    original back, and other focus routes do not move focus either."""
    load(engine_page, sink)
    add_page_textarea(engine_page)
    mount(
        engine_page,
        "<input id=i><script>(function () {"
        "var r = {};"
        "var d = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'focus');"
        "r.locked = !!d && d.writable === false && d.configurable === false;"
        "try { delete HTMLElement.prototype.focus; } catch (e) {}"
        "try { HTMLElement.prototype.focus = function () { window.__stole = true; }; } catch (e) {}"
        "try { Object.defineProperty(HTMLElement.prototype, 'focus', {value: function () { window.__stole = true; }}); } catch (e) {}"
        "var w = Object.getOwnPropertyDescriptor(window, 'focus');"
        "r.winLocked = !w || (w.writable === false && w.configurable === false);"
        "window.__r = r; window.__ready = true;"
        "})();</script>",
    )
    frame(engine_page).wait_for_function("() => window.__ready === true")
    r = frame(engine_page).evaluate("() => window.__r")
    assert r == {"locked": True, "winLocked": True}, r
