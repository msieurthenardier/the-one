# ruff: noqa: E501  (inline widget sources are evaluated verbatim)
"""The widget frame's cooperative pause gate (M35 F2 L3, AC3, DD8).

The prelude wraps the widget's clock: animation-frame callbacks queue, due timers are deferred (an
interval collapses to one run), CSS and Web Animations and audio contexts are paused, and
``performance.now()`` and the animation-frame timestamps exclude paused time (``Date`` is left
alone). The initial state is in the document (``paused: true``), so no widget timer runs first.
Every reading is an in-frame counter, taken through the frame. Both engines.
"""

from __future__ import annotations

import pytest
from browser._widget_harness import frame, load, mount
from browser._widget_sink import WidgetSink
from playwright.sync_api import Page

pytestmark = pytest.mark.browser

COUNTERS = (
    "<style>@keyframes mv{from{transform:translateX(0)}to{transform:translateX(80px)}}"
    "#box{width:20px;height:20px;background:currentColor;animation:mv 2s linear infinite}</style>"
    "<div id=box></div>"
    "<script>"
    "window.__r = 0; window.__i = 0; window.__ready = false;"
    "(function loop() { window.__r++; requestAnimationFrame(loop); })();"
    "setInterval(function () { window.__i++; }, 20);"
    "window.__wa = document.getElementById('box').animate([{opacity: 1}, {opacity: 0.4}], {duration: 2000, iterations: Infinity});"
    "window.__snap = function () {"
    "var css = document.getAnimations().filter(function (a) { return a.animationName === 'mv'; })[0];"
    "return {r: window.__r, i: window.__i, css: css ? css.currentTime : -1, wa: window.__wa.currentTime,"
    "now: performance.now(), date: Date.now()};"
    "};"
    "window.__ready = true;"
    "</script>"
)

# A widget that tries to undo the gate before it starts.
ATTACK = (
    "<script>"
    "try { delete window.requestAnimationFrame; } catch (e) {}"
    "try { window.requestAnimationFrame = function (f) { return 0; }; } catch (e) {}"
    "try { Object.defineProperty(window, 'setInterval', {value: function () { return 0; }}); } catch (e) {}"
    "try { Object.defineProperty(window, 'setTimeout', {value: function () { return 0; }}); } catch (e) {}"
    "try { Object.defineProperty(Performance.prototype, 'now', {value: function () { return 12345; }}); } catch (e) {}"
    "try { delete Performance.prototype.now; } catch (e) {}"
    "window.__attack = [typeof requestAnimationFrame, performance.now() !== 12345];"
    "</script>"
)


@pytest.fixture(scope="module")
def sink():
    s = WidgetSink()
    try:
        yield s
    finally:
        s.close()


def _snap(page: Page) -> dict:
    return frame(page).evaluate("() => window.__snap()")


def _start(page: Page, sink: WidgetSink, source: str = COUNTERS, **opts) -> None:
    load(page, sink)
    mount(page, source, **opts)
    frame(page).wait_for_function("() => window.__ready === true")
    frame(page).wait_for_function("() => window.__r > 5 && window.__i > 5", timeout=10000)


def _pause(page: Page) -> None:
    page.evaluate("() => __h.postPause()")
    page.wait_for_timeout(300)


def _resume(page: Page) -> None:
    page.evaluate("() => __h.postResume()")


def _beats(page: Page) -> int:
    return int(page.evaluate("() => __beats"))


def _assert_frozen(a: dict, b: dict) -> None:
    for key in ("r", "i", "css", "wa", "now"):
        assert a[key] == b[key], (key, a, b)


def test_pause_freezes_the_clock_and_resume_continues_without_a_jump(
    engine_page: Page, sink: WidgetSink
) -> None:
    _start(engine_page, sink)
    _pause(engine_page)
    beats0 = _beats(engine_page)
    s1 = _snap(engine_page)
    engine_page.wait_for_timeout(1400)
    s2 = _snap(engine_page)
    _assert_frozen(s1, s2)
    # Date is left alone: the wall clock moved while performance.now did not.
    assert s2["date"] - s1["date"] >= 1000, (s1, s2)
    # the heartbeat is never gated
    assert _beats(engine_page) > beats0
    _resume(engine_page)
    engine_page.wait_for_timeout(500)
    s3 = _snap(engine_page)
    assert s3["r"] > s2["r"] + 5 and s3["i"] > s2["i"] + 5, (s2, s3)
    assert s3["css"] > s2["css"] and s3["wa"] > s2["wa"], (s2, s3)
    # No jump: the clock advanced about as long as the widget actually ran (not the 1.7 s paused).
    assert 0 <= s3["now"] - s2["now"] < 1000, (s2, s3)
    print(
        f"[widget-pause] {engine_page.context.browser.browser_type.name} paused window "
        f"date+{s2['date'] - s1['date']:.0f} ms now+{s2['now'] - s1['now']:.0f} ms; "
        f"after resume now+{s3['now'] - s2['now']:.0f} ms"
    )


def test_pause_defers_a_due_timeout_and_collapses_an_interval(
    engine_page: Page, sink: WidgetSink
) -> None:
    load(engine_page, sink)
    mount(
        engine_page,
        "<script>window.__to = 0; window.__iv = 0; window.__idle = 0; window.__pt = 0;"
        "setTimeout(function () { window.__to++; }, 700);"
        "setInterval(function () { window.__iv++; }, 50);"
        "window.__has = {idle: typeof requestIdleCallback === 'function', task: !!(window.scheduler && scheduler.postTask)};"
        "window.__ready = true;</script>",
    )
    frame(engine_page).wait_for_function("() => window.__ready === true")
    _pause(engine_page)  # arrives before the 700 ms timeout is due
    assert frame(engine_page).evaluate("() => window.__to") == 0
    has = frame(engine_page).evaluate("() => window.__has")
    frame(engine_page).evaluate(
        "() => { if (__has.idle) requestIdleCallback(function () { __idle++; });"
        "if (__has.task) scheduler.postTask(function () { __pt++; }); }"
    )
    engine_page.wait_for_timeout(1300)  # the timeout came due once; the interval, ~25 times
    assert frame(engine_page).evaluate("() => window.__to") == 0
    held = frame(engine_page).evaluate("() => window.__iv")
    assert frame(engine_page).evaluate("() => [__idle, __pt]") == [0, 0]
    _resume(engine_page)
    frame(engine_page).wait_for_function("() => window.__to === 1")
    delta = frame(engine_page).evaluate("() => window.__iv") - held
    print(f"[widget-pause] interval runs right after resume: {delta} (about 25 were due)")
    assert 1 <= delta <= 3, delta
    engine_page.wait_for_timeout(300)
    assert frame(engine_page).evaluate("() => window.__to") == 1  # exactly once
    assert frame(engine_page).evaluate("() => __iv") > held + 3  # it keeps its period
    idle, task = frame(engine_page).evaluate("() => [__idle, __pt]")
    assert idle == (1 if has["idle"] else 0) and task == (1 if has["task"] else 0), (
        idle,
        task,
        has,
    )


def test_a_widget_built_paused_runs_one_frame_round_and_no_timers(
    engine_page: Page, sink: WidgetSink
) -> None:
    load(engine_page, sink)
    mount(
        engine_page,
        "<canvas id=c width=10 height=10></canvas><script>"
        "window.__r = 0; window.__i = 0; window.__t = 0; window.__drawn = 0; window.__idle = 0;"
        "requestAnimationFrame(function f() { window.__r++; if (!window.__drawn) { window.__drawn = performance.now() + 1; }"
        "document.getElementById('c').getContext('2d').fillRect(0, 0, 5, 5); requestAnimationFrame(f); });"
        "setInterval(function () { window.__i++; }, 20);"
        "setTimeout(function () { window.__t++; }, 50);"
        "window.__ready = true;</script>",
        paused=True,
    )
    frame(engine_page).wait_for_function("() => window.__ready === true")
    frame(engine_page).wait_for_function("() => window.__r === 1", timeout=5000)
    engine_page.wait_for_timeout(1500)
    state = frame(engine_page).evaluate("() => [__r, __i, __t, !!__drawn, performance.now()]")
    assert state[:4] == [1, 0, 0, True], state
    assert frame(engine_page).evaluate("() => performance.now()") == state[4]  # frozen
    # the heartbeat runs, and a theme push still applies while gated
    assert int(engine_page.evaluate("() => __beats")) >= 1
    engine_page.evaluate("() => __h.postTheme({vars: {'--bg': '#123456'}, mode: 'light'})")
    frame(engine_page).wait_for_function(
        "() => document.documentElement.getAttribute('data-theme') === 'light'"
    )
    _resume(engine_page)
    frame(engine_page).wait_for_function("() => __r > 5 && __i > 5 && __t === 1", timeout=5000)


def test_pause_queued_before_the_frame_loads_is_applied_at_load(
    engine_page: Page, sink: WidgetSink
) -> None:
    load(engine_page, sink)
    mount(engine_page, COUNTERS, wait_load=False)
    engine_page.evaluate("() => __h.postPause()")
    engine_page.wait_for_function("() => __h.loads() >= 1")
    frame(engine_page).wait_for_function("() => window.__ready === true")
    engine_page.wait_for_timeout(700)
    s1 = _snap(engine_page)
    engine_page.wait_for_timeout(700)
    _assert_frozen(s1, _snap(engine_page))
    # a resume queued the same way wins when it is the newest
    engine_page.evaluate("() => { __h.postPause(); __h.postResume(); }")
    frame(engine_page).wait_for_function(f"() => window.__r > {s1['r']} + 5", timeout=5000)


def test_the_widget_cannot_undo_the_gate(engine_page: Page, sink: WidgetSink) -> None:
    """Reassigning, redefining and deleting the wrapped functions does not lift the gate."""
    load(engine_page, sink)
    mount(engine_page, ATTACK + COUNTERS)
    frame(engine_page).wait_for_function("() => window.__ready === true")
    assert frame(engine_page).evaluate("() => window.__attack") == ["function", True]
    frame(engine_page).wait_for_function("() => window.__r > 5 && window.__i > 5", timeout=10000)
    _pause(engine_page)
    s1 = _snap(engine_page)
    engine_page.wait_for_timeout(900)
    _assert_frozen(s1, _snap(engine_page))
    _resume(engine_page)
    engine_page.wait_for_timeout(300)
    assert _snap(engine_page)["r"] > s1["r"]


def test_a_cleared_timer_never_runs_after_resume(engine_page: Page, sink: WidgetSink) -> None:
    load(engine_page, sink)
    mount(
        engine_page,
        "<script>window.__a = 0; window.__b = 0; window.__af = 0;"
        "window.__ta = setTimeout(function () { window.__a++; }, 300);"
        "window.__tb = setTimeout(function () { window.__b++; }, 300);"
        "window.__fa = requestAnimationFrame(function () { window.__af++; });"
        "window.__ready = true;</script>",
        paused=True,
    )
    frame(engine_page).wait_for_function("() => window.__ready === true")
    engine_page.wait_for_timeout(800)  # both came due while gated
    frame(engine_page).evaluate("() => { clearTimeout(__ta); }")
    _resume(engine_page)
    frame(engine_page).wait_for_function("() => window.__b === 1")
    engine_page.wait_for_timeout(300)
    assert frame(engine_page).evaluate("() => [__a, __b]") == [0, 1]


def test_audio_contexts_are_wrapped_and_still_audio_contexts(
    engine_page: Page, sink: WidgetSink
) -> None:
    load(engine_page, sink)
    mount(
        engine_page,
        "<script>(function () { var r = {has: typeof AudioContext === 'function'};"
        "if (r.has) { var c = new AudioContext(); r.inst = c instanceof AudioContext; r.state = c.state; r.ctor = typeof c.createGain; }"
        "window.__r = r; window.__ready = true; })();</script>",
        paused=True,
    )
    frame(engine_page).wait_for_function("() => window.__ready === true")
    r = frame(engine_page).evaluate("() => window.__r")
    if r["has"]:
        assert r["inst"] is True and r["ctor"] == "function", r
        assert r["state"] in ("suspended", "closed"), r  # built while gated
