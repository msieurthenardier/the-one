# ruff: noqa: E501  (inline widget sources are evaluated verbatim)
"""The widget card (``App.ui.widget``, M35 F2 L4): marking, controls, notices, states, sweep.

Both engines. Frame readings are in-frame counters taken through the frame (never user-activation
sensitive state), and the page-side calls go through ``page.evaluate`` on the card's handle.
"""

from __future__ import annotations

import pytest
from browser._widget_harness import frame, load
from browser._widget_sink import WidgetSink
from playwright.sync_api import Page

pytestmark = pytest.mark.browser

PLAIN = "<title>Hello card</title><div id=x>hi</div><script>window.__n = (window.__n || 0) + 1; window.__ticks = 0; setInterval(function () { window.__ticks++; }, 20);</script>"


@pytest.fixture(scope="module")
def sink():
    s = WidgetSink()
    try:
        yield s
    finally:
        s.close()


def _setup(page: Page, sink: WidgetSink, theme: str = "dark") -> None:
    load(page, sink, theme=theme)
    page.evaluate(
        """() => {
          window.__cards = [];
          window.__make = (source, extra) => {
            const c = App.ui.widget(Object.assign({source, agentName: 'Ada', managed: false, testid: 'w' + window.__cards.length}, extra || {}));
            window.__cards.push(c);
            if (c) document.getElementById('harness-root').appendChild(c.el);
            return c;
          };
        }"""
    )


def _make(page: Page, source: str, **extra) -> None:
    page.evaluate("([s, x]) => { __make(s, x); }", [source, extra])


def _make_wait(page: Page, source: str = PLAIN, idx: int = 0, **extra) -> None:
    _make(page, source, **extra)
    page.wait_for_function(f"() => __cards[{idx}]._frame() && __cards[{idx}]._frame().loads() >= 1")


def _text(page: Page, sel: str) -> str:
    return page.locator(sel).first.inner_text().strip()


def _ticks(page: Page) -> int:
    return int(frame(page).evaluate("() => window.__ticks"))


# ---- AC1 -------------------------------------------------------------------------------------


def test_structure_and_marking(engine_page: Page, sink: WidgetSink) -> None:
    _setup(engine_page, sink)
    _make_wait(engine_page)
    p = engine_page
    assert p.locator("figure.ui-widget[data-testid=w0]").count() == 1
    head = p.locator("[data-testid=w0] .ui-widget-head")
    assert head.locator("svg.ui-widget-icon").get_attribute("aria-hidden") == "true"
    assert _text(p, "[data-testid=w0] .ui-widget-by") == "Widget by Ada"
    assert _text(p, "[data-testid=w0] .ui-widget-title") == "· Hello card"
    kids = head.evaluate(
        "e => Array.from(e.children).map(c => c.className.baseVal === undefined ? c.className : c.className.baseVal)"
    )
    assert kids[0].startswith("ui-icon") and "ui-widget-by" in kids[1]
    assert (
        "ui-widget-title" in kids[2]
        and "ui-widget-chip-slot" in kids[3]
        and "ui-widget-spacer" in kids[4]
    )
    assert "ui-widget-btn" in kids[5] and "ui-widget-btn" in kids[6]
    assert p.get_by_test_id("w0-pause").get_attribute("aria-label") == "Pause widget"
    assert p.get_by_test_id("w0-pause").get_attribute("aria-pressed") is None
    assert p.get_by_test_id("w0-restart").get_attribute("aria-label") == "Restart widget"
    assert p.get_by_test_id("w0-frame").get_attribute("title") == "Widget by Ada"
    assert p.get_by_test_id("w0-frame").evaluate("e => e.tagName") == "IFRAME"
    # View source: a closed disclosure with the exact source
    assert p.get_by_test_id("w0-source-details").evaluate("e => e.open") is False
    assert (
        p.get_by_test_id("w0-source").inner_text() == PLAIN
        or p.get_by_test_id("w0-source").text_content() == PLAIN
    )
    # order: header, hidden status, body, disclosure
    assert p.locator("[data-testid=w0]").evaluate(
        "e => Array.from(e.children).map(c => c.className.split(' ')[0])"
    ) == ["ui-widget-head", "ui-widget-status", "ui-widget-body", "ui-disclosure"]


def test_title_markup_cap_missing_and_null_agent(engine_page: Page, sink: WidgetSink) -> None:
    _setup(engine_page, sink)
    p = engine_page
    _make_wait(p, "<title>A <b>B</b>\n  C</title><p>x</p>", idx=0)
    assert _text(p, "[data-testid=w0] .ui-widget-title") == "· A B C"
    _make_wait(p, "<title>" + "x" * 200 + "</title><p>x</p>", idx=1)
    t = _text(p, "[data-testid=w1] .ui-widget-title")
    assert t == "· " + "x" * 60
    _make_wait(p, "<p>no title</p>", idx=2, agentName=None)
    assert p.locator("[data-testid=w2] .ui-widget-title").is_hidden()
    assert _text(p, "[data-testid=w2] .ui-widget-by") == "Widget by the agent"
    assert p.get_by_test_id("w2-frame").get_attribute("title") == "Widget by the agent"
    # a title past the first 8 KiB is not read
    _make_wait(p, "<p>" + "y" * 9000 + "</p><title>late</title>", idx=3)
    assert p.locator("[data-testid=w3] .ui-widget-title").is_hidden()


def test_title_is_text_not_markup(engine_page: Page, sink: WidgetSink) -> None:
    _setup(engine_page, sink)
    _make_wait(engine_page, "<title>&lt;img src=x onerror=alert(1)&gt;</title><p>x</p>")
    assert engine_page.locator("[data-testid=w0] .ui-widget-head img").count() == 0


# ---- AC2 -------------------------------------------------------------------------------------


def test_pause_resume_and_restart(engine_page: Page, sink: WidgetSink) -> None:
    _setup(engine_page, sink)
    p = engine_page
    _make_wait(p)
    frame(p).wait_for_function("() => window.__ticks > 5")
    p.get_by_test_id("w0-pause").click()
    assert p.get_by_test_id("w0-pause").get_attribute("aria-pressed") is None  # label swap only
    assert p.get_by_test_id("w0-pause").get_attribute("aria-label") == "Resume widget"
    assert _text(p, "[data-testid=w0-pause]") == "Resume"
    assert p.get_by_test_id("w0-paused").inner_text().strip() == "Paused"
    assert p.evaluate("() => __cards[0].state()") == "paused-user"
    p.wait_for_timeout(300)
    a = _ticks(p)
    p.wait_for_timeout(500)
    assert _ticks(p) == a
    p.get_by_test_id("w0-pause").click()
    assert p.get_by_test_id("w0-pause").get_attribute("aria-pressed") is None
    assert p.get_by_test_id("w0-paused").count() == 0
    p.wait_for_timeout(400)
    assert _ticks(p) > a
    # Restart: a fresh frame whose own counter starts again; a paused widget is unpaused
    p.get_by_test_id("w0-pause").click()
    old = p.evaluate("() => { window.__old = __cards[0]._frame(); return 1; }")
    assert old == 1
    p.get_by_test_id("w0-restart").click()
    p.wait_for_function(
        "() => __cards[0]._frame() && __cards[0]._frame() !== __old && __cards[0]._frame().loads() === 1"
    )
    assert p.evaluate("() => __cards[0].state()") == "running"
    assert p.get_by_test_id("w0-paused").count() == 0
    assert p.get_by_test_id("w0-pause").get_attribute("aria-pressed") is None
    frame(p).wait_for_function("() => window.__n === 1 && window.__ticks > 3")
    assert p.locator("iframe").count() == 1


def test_paused_option_mounts_paused(engine_page: Page, sink: WidgetSink) -> None:
    _setup(engine_page, sink)
    p = engine_page
    _make_wait(p, paused=True)
    assert p.get_by_test_id("w0-paused").count() == 1
    assert p.get_by_test_id("w0-pause").get_attribute("aria-pressed") is None  # label swap only
    p.wait_for_timeout(600)
    assert _ticks(p) <= 1
    p.get_by_test_id("w0-pause").click()
    frame(p).wait_for_function("() => window.__ticks > 5")


def test_stop_status_focus_and_figure_name(engine_page: Page, sink: WidgetSink) -> None:
    _setup(engine_page, sink)
    p = engine_page
    _make_wait(p)
    # 1.3.1: the figure is named by its "Widget by" header
    assert (
        p.get_by_test_id("w0").evaluate(
            "e => document.getElementById(e.getAttribute('aria-labelledby')).textContent"
        )
        == "Widget by Ada"
    )
    # 4.1.3: the status node exists from construction, empty; pauses announce nothing
    status = p.get_by_test_id("w0-status")
    assert status.get_attribute("role") == "status"
    assert status.text_content() == ""
    p.evaluate("() => __cards[0].pause()")
    p.evaluate("() => __cards[0].autoPause()")
    assert status.text_content() == ""
    p.evaluate("() => { __cards[0].resume(); __cards[0].autoResume(); }")
    p.evaluate("() => __cards[0].stop('hung')")
    assert status.text_content() == "This widget stopped responding."
    # 2.4.3: Start anyway by keyboard hands focus to Pause, not <body>
    p.get_by_test_id("w0-start").focus()
    p.keyboard.press("Enter")
    p.wait_for_function("() => __cards[0]._frame() && __cards[0]._frame().loads() >= 1")
    assert p.evaluate("() => document.activeElement.dataset.testid") == "w0-pause"
    assert status.text_content() == ""
    # focus is never moved when it was elsewhere
    p.evaluate("() => __cards[0].stop('hung-last')")
    assert status.text_content() == "This widget stopped responding last time."
    p.evaluate("() => document.activeElement.blur()")
    p.evaluate("() => __cards[0].restart()")
    p.wait_for_function("() => __cards[0]._frame() && __cards[0]._frame().loads() >= 1")
    assert p.evaluate("() => document.activeElement === document.body")


def test_start_anyway_after_stop(engine_page: Page, sink: WidgetSink) -> None:
    _setup(engine_page, sink)
    p = engine_page
    _make_wait(p)
    p.evaluate("() => __cards[0].pause()")
    p.evaluate("() => __cards[0].stop('hung')")
    assert p.locator("iframe").count() == 0
    assert (
        _text(p, "[data-testid=w0-stopped] .ui-widget-stopped-text")
        == "This widget stopped responding."
    )
    assert p.get_by_test_id("w0-pause").is_disabled()
    p.get_by_test_id("w0-start").click()
    p.wait_for_function("() => __cards[0]._frame() && __cards[0]._frame().loads() >= 1")
    assert p.evaluate("() => __cards[0].state()") == "running"
    assert p.get_by_test_id("w0-stopped").count() == 0
    assert p.get_by_test_id("w0-paused").count() == 0
    p.evaluate("() => __cards[0].stop('hung-last')")
    assert (
        _text(p, "[data-testid=w0-stopped] .ui-widget-stopped-text")
        == "This widget stopped responding last time."
    )
    assert p.evaluate("() => __cards[0].state()") == "stopped-hung"
    assert p.get_by_test_id("w0-start").count() == 1


# ---- AC3 -------------------------------------------------------------------------------------


def test_empty_source_returns_null(engine_page: Page, sink: WidgetSink) -> None:
    _setup(engine_page, sink)
    p = engine_page
    assert p.evaluate("() => App.ui.widget({source: ''})") is None
    assert p.evaluate("() => App.ui.widget({source: ' \\n\\t '})") is None
    assert p.evaluate("() => App.ui.widget({})") is None


def test_byte_limit_is_utf8_exact(engine_page: Page, sink: WidgetSink) -> None:
    _setup(engine_page, sink)
    p = engine_page
    # exactly 65,536 bytes runs; one more does not
    p.evaluate("() => { window.__ok = '<p>' + 'a'.repeat(65536 - 3); }")
    assert p.evaluate("() => new Blob([__ok]).size") == 65536
    _make(p, p.evaluate("() => __ok"), testid="edge")
    p.wait_for_function("() => __cards[0] && __cards[0]._frame && __cards[0]._frame().loads() >= 1")
    assert p.get_by_test_id("edge").count() == 1
    over = p.evaluate("() => __ok + 'a'")
    _make(p, over, testid="over")
    assert p.get_by_test_id("over").count() == 0
    notice = p.get_by_test_id("over-notice")
    assert notice.count() == 1
    assert "Couldn't run this widget." in notice.inner_text()
    assert "This widget is too large to run (65 KB; the limit is 64 KB)." in notice.inner_text()
    assert p.locator("iframe").count() == 1  # only the edge card


def test_astral_characters_count_four_bytes(engine_page: Page, sink: WidgetSink) -> None:
    _setup(engine_page, sink)
    p = engine_page
    # 16,385 astral characters = 65,540 bytes (but only 32,770 UTF-16 units): over the limit
    src = p.evaluate("() => '\\u{1F600}'.repeat(16385)")
    _make(p, src, testid="astral")
    assert p.get_by_test_id("astral-notice").count() == 1
    assert "(65 KB;" in p.get_by_test_id("astral-notice").inner_text()
    # 16,384 astral characters = exactly 65,536 bytes: runs
    src = p.evaluate("() => '\\u{1F600}'.repeat(16384)")
    _make(p, src, testid="astral2")
    assert p.get_by_test_id("astral2").count() == 1


def test_cut_off_source_never_runs(engine_page: Page, sink: WidgetSink) -> None:
    _setup(engine_page, sink)
    p = engine_page
    _make(p, "<script>window.top.__ran = 1</script><p>half", closed=False, testid="cut")
    assert p.get_by_test_id("cut").count() == 0
    n = p.get_by_test_id("cut-notice")
    assert "This widget was cut off before it finished." in n.inner_text()
    assert p.locator("iframe").count() == 0
    assert p.evaluate("() => window.__ran") is None
    n.get_by_text("Technical details").click()
    assert "<p>half" in p.get_by_test_id("cut-notice-details").inner_text()


def test_escape_stops_the_card_and_keeps_the_marking(engine_page: Page, sink: WidgetSink) -> None:
    _setup(engine_page, sink)
    p = engine_page
    _make_wait(p, "<p>x</p><script>setTimeout(function () { location.reload(); }, 50)</script>")
    p.wait_for_function("() => __cards[0].state() === 'stopped-escape'")
    assert (
        _text(p, "[data-testid=w0-stopped] .ui-widget-stopped-text")
        == "This widget tried to leave its frame and was stopped."
    )
    assert p.get_by_test_id("w0-start").count() == 1
    assert _text(p, "[data-testid=w0] .ui-widget-by") == "Widget by Ada"
    assert p.locator("iframe").count() == 0


def test_height_follows_size_and_unload_keeps_the_slot(engine_page: Page, sink: WidgetSink) -> None:
    _setup(engine_page, sink)
    p = engine_page
    _make_wait(p, '<div style="height:333px;background:red"></div>')
    h0 = p.evaluate("() => __cards[0]._frame().iframe.getBoundingClientRect().height")
    assert h0 == 240 or h0 > 0
    p.wait_for_function(
        "() => Math.round(__cards[0]._frame().iframe.getBoundingClientRect().height) >= 333"
    )
    h = round(p.evaluate("() => __cards[0]._frame().iframe.getBoundingClientRect().height"))
    # unload keeps the last height, so the log does not jump
    p.evaluate("() => __cards[0].unload()")
    assert p.locator("iframe").count() == 0
    body = round(
        p.locator("[data-testid=w0] .ui-widget-body").evaluate(
            "e => e.getBoundingClientRect().height"
        )
    )
    assert body == h


# ---- AC4 -------------------------------------------------------------------------------------


def test_states_and_transitions(engine_page: Page, sink: WidgetSink) -> None:
    _setup(engine_page, sink)
    p = engine_page
    _make_wait(p)
    st = lambda: p.evaluate("() => __cards[0].state()")  # noqa: E731
    assert st() == "running"
    p.evaluate("() => __cards[0].pause()")
    assert st() == "paused-user"
    p.evaluate("() => __cards[0].resume()")
    assert st() == "running"
    p.evaluate("() => __cards[0].autoPause()")
    assert st() == "paused-auto"
    assert p.get_by_test_id("w0-paused").count() == 0  # no chip for the automatic pause
    assert p.get_by_test_id("w0-pause").get_attribute("aria-pressed") is None
    p.wait_for_timeout(300)
    a = _ticks(p)
    p.wait_for_timeout(400)
    assert _ticks(p) == a
    p.evaluate("() => __cards[0].autoResume()")
    assert st() == "running"
    p.wait_for_timeout(300)
    assert _ticks(p) > a
    # both pauses: the frame stays gated until both lift
    p.evaluate("() => { __cards[0].pause(); __cards[0].autoPause(); __cards[0].autoResume(); }")
    assert st() == "paused-user"
    p.evaluate("() => __cards[0].resume()")
    assert st() == "running"
    # unload -> waiting -> start
    p.evaluate("() => __cards[0].unload()")
    assert st() == "waiting"
    assert p.locator("iframe").count() == 0
    assert p.get_by_test_id("w0-frame").count() == 0
    p.evaluate("() => __cards[0].start()")
    p.wait_for_function("() => __cards[0]._frame() && __cards[0]._frame().loads() >= 1")
    assert st() == "running"
    # a pause while waiting mounts paused at start
    p.evaluate("() => { __cards[0].unload(); __cards[0].pause(); __cards[0].start(); }")
    assert st() == "paused-user"
    p.evaluate("() => __cards[0].stop('hung')")
    assert st() == "stopped-hung"
    p.evaluate("() => __cards[0].restart()")
    assert st() == "running"


# ---- AC5 -------------------------------------------------------------------------------------


def test_theme_follows_and_new_cards_mount_in_the_new_theme(
    engine_page: Page, sink: WidgetSink
) -> None:
    _setup(engine_page, sink)
    p = engine_page
    # The app themes the document root; drop the harness's own inner theme so the root decides.
    p.evaluate("() => document.getElementById('harness-root').removeAttribute('data-theme')")
    p.evaluate("() => document.documentElement.setAttribute('data-theme', 'dark')")
    _make_wait(p, "<p>a</p>", idx=0)
    _make_wait(p, "<p>b</p>", idx=1)
    bg = "() => getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()"
    read = "() => getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()"
    before = [f.evaluate(read) for f in p.frames if f != p.main_frame]
    assert len(before) == 2
    p.evaluate("() => document.documentElement.setAttribute('data-theme', 'light')")
    p.wait_for_function("() => Array.from(document.querySelectorAll('iframe')).length === 2")
    p.wait_for_timeout(400)
    after = [f.evaluate(read) for f in p.frames if f != p.main_frame]
    assert after[0] == after[1]
    assert after != before
    _make_wait(p, "<p>c</p>", idx=2)
    third = [f for f in p.frames if f != p.main_frame][2].evaluate(read)
    assert third == after[0]
    assert bg  # the page-side read is only a reference


# ---- AC6 -------------------------------------------------------------------------------------


def test_destroy_is_idempotent_and_sweep_reaps_detached_cards(
    engine_page: Page, sink: WidgetSink
) -> None:
    _setup(engine_page, sink)
    p = engine_page
    for i in range(3):
        _make_wait(p, f"<p>c{i}</p>", idx=i)
    p.evaluate("() => { window.__wins = __cards.map(c => c._frame().iframe.contentWindow); }")
    assert p.evaluate("() => App.ui.widget._instances()") == 3
    assert p.evaluate("() => __wins.every(w => App.ui.widgetFrame._has(w))") is True
    p.evaluate("() => { __cards[0].el.remove(); __cards[1].el.remove(); }")
    # a card that was never attached is kept
    p.evaluate(
        "() => { window.__loose = App.ui.widget({source: '<p>loose</p>', managed: false, testid: 'loose'}); }"
    )
    assert p.evaluate("() => App.ui.widget._instances()") == 4
    assert p.evaluate("() => App.ui.widget.sweep()") == 2
    assert p.evaluate("() => App.ui.widget._instances()") == 2
    assert p.evaluate("() => __wins.map(w => App.ui.widgetFrame._has(w))") == [False, False, True]
    assert p.evaluate("() => __cards[2].state()") == "running"
    p.evaluate("() => __loose.destroy()")
    # destroy is idempotent
    p.evaluate("() => { __cards[2].destroy(); __cards[2].destroy(); }")
    assert p.evaluate("() => App.ui.widget._instances()") == 0
    assert p.evaluate("() => App.ui.widgetFrame._has(__wins[2])") is False
    assert p.locator("iframe").count() == 0


# ---- AC7 -------------------------------------------------------------------------------------


def test_width_in_a_bubble_and_narrow_layout(engine_page: Page, sink: WidgetSink) -> None:
    _setup(engine_page, sink)
    p = engine_page
    p.evaluate(
        """() => {
          const bubble = document.createElement('div');
          bubble.className = 'ui-message ui-message--assistant';
          bubble.id = 'bub';
          document.getElementById('harness-root').appendChild(bubble);
          window.__bub = bubble;
        }"""
    )
    c = p.evaluate(
        "() => { window.__c = App.ui.widget({source: PLAIN_SRC(), testid: 'b', managed: false, agentName: 'Ada'}); __bub.appendChild(__c.el); return 1; }".replace(
            "PLAIN_SRC()", repr(PLAIN)
        )
    )
    assert c == 1
    p.wait_for_function("() => __c._frame().loads() >= 1")
    rem = p.evaluate("() => parseFloat(getComputedStyle(document.documentElement).fontSize)")
    p.set_viewport_size({"width": 1300, "height": 800})
    w = p.get_by_test_id("b").evaluate("e => e.getBoundingClientRect().width")
    # 46rem preferred, capped at the bubble's content box (the bubble itself caps at 46rem)
    assert 600 < w <= 46 * rem + 1, (w, rem)
    p.evaluate("() => { __bub.style.maxWidth = '300px'; __bub.style.width = '300px'; }")
    w = p.get_by_test_id("b").evaluate("e => e.getBoundingClientRect().width")
    assert w <= 300 + 1, w


def test_narrow_card_hides_labels_but_keeps_names(engine_page: Page, sink: WidgetSink) -> None:
    _setup(engine_page, sink)
    p = engine_page
    _make_wait(p, "<title>" + "very long title " * 10 + "</title><p>x</p>")
    wide = p.locator("[data-testid=w0-pause] .ui-widget-btn-label").evaluate(
        "e => e.getBoundingClientRect().width"
    )
    assert wide > 10
    p.evaluate("() => { document.querySelector('[data-testid=w0]').style.width = '340px'; }")
    p.wait_for_timeout(100)
    label_w = p.locator("[data-testid=w0-pause] .ui-widget-btn-label").evaluate(
        "e => e.getBoundingClientRect().width"
    )
    assert label_w <= 1, label_w
    assert p.get_by_test_id("w0-pause").get_attribute("aria-label") == "Pause widget"
    assert p.get_by_test_id("w0-restart").get_attribute("aria-label") == "Restart widget"
    # the accessible name via the tree survives
    name = p.get_by_test_id("w0-restart").evaluate("e => e.getAttribute('aria-label')")
    assert name == "Restart widget"
    title = p.locator("[data-testid=w0] .ui-widget-title")
    assert title.evaluate("e => getComputedStyle(e).textOverflow") == "ellipsis"
    head = p.locator("[data-testid=w0] .ui-widget-head")
    assert head.evaluate("e => e.scrollWidth <= e.clientWidth + 1") is True
    # and the buttons stay inside the 340 px card
    box = p.get_by_test_id("w0-restart").bounding_box()
    card = p.get_by_test_id("w0").bounding_box()
    assert box["x"] + box["width"] <= card["x"] + card["width"] + 1
