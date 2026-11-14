# ruff: noqa: E501  (inline widget sources and fact tables are evaluated verbatim)
"""The widget lifecycle manager (M35 F2 L5, flight DD7): the pure ``reconcile`` table, then the
live lifecycle in a tall harness page with real scrolling. Both engines."""

from __future__ import annotations

import pytest
from browser._ui_engines import load_harness
from browser._widget_harness import (
    COUNTER,
    card_frame,
    counter,
    fake_hidden,
    make_cards,
    scroll_to_card,
    setup_cards,
    states,
    wait_states,
)
from browser._widget_sink import WidgetSink
from playwright.sync_api import Page

pytestmark = pytest.mark.browser


@pytest.fixture(scope="module")
def sink():
    s = WidgetSink()
    try:
        yield s
    finally:
        s.close()


# ---- AC1: reconcile, table-driven ------------------------------------------------------------


def fact(id, **kw):
    base = {
        "id": id,
        "inView": False,
        "userPaused": False,
        "stopped": False,
        "loaded": False,
        "running": False,
        "startOrder": 0,
        "startRequested": False,
        "lastVisibleAt": 0,
        "loadedAt": 0,
    }
    base.update(kw)
    return base


def run(id, order, **kw):  # running, in view
    return fact(id, inView=True, loaded=True, running=True, startOrder=order, **kw)


def off(id, seen, **kw):  # loaded, off screen, paused-auto
    return fact(id, loaded=True, lastVisibleAt=seen, loadedAt=seen, **kw)


CASES = [
    # (name, hidden, instances, states, load, unload, capped)
    ("in view under the cap runs", False, [fact(1, inView=True)], {1: "running"}, [1], [], []),
    (
        "cap reached: a waiting card is capped",
        False,
        [run(1, 1), run(2, 2), run(3, 3), fact(4, inView=True)],
        {1: "running", 2: "running", 3: "running", 4: "waiting"},
        [],
        [],
        [4],
    ),
    (
        "cap reached: a loaded card goes paused-auto",
        False,
        [run(1, 1), run(2, 2), run(3, 3), fact(4, inView=True, loaded=True)],
        {1: "running", 2: "running", 3: "running", 4: "paused-auto"},
        [],
        [],
        [],
    ),
    (
        "out of view and loaded is paused-auto; unloaded stays waiting",
        False,
        [fact(1, loaded=True, running=True), fact(2)],
        {1: "paused-auto", 2: "waiting"},
        [],
        [],
        [],
    ),
    (
        "userPaused is paused-user in view or not and takes no running slot",
        False,
        [
            fact(1, userPaused=True, loaded=True, inView=True),
            fact(2, userPaused=True, loaded=True),
            fact(3, inView=True),
            fact(4, inView=True),
            fact(5, inView=True),
        ],
        {1: "paused-user", 2: "paused-user", 3: "running", 4: "running", 5: "running"},
        [3, 4, 5],
        [],
        [],
    ),
    (
        "stopped is unchanged",
        False,
        [fact(1, stopped=True, inView=True), fact(2, stopped=True)],
        {1: "stopped", 2: "stopped"},
        [],
        [],
        [],
    ),
    (
        "hidden pauses every loaded card and loads none",
        True,
        [run(1, 1), run(2, 2), fact(3, inView=True), fact(4, userPaused=True, inView=True)],
        {1: "paused-auto", 2: "paused-auto", 3: "waiting", 4: "waiting"},
        [],
        [],
        [],
    ),
    (
        "fill order: paused-auto resumes before waiting starts",
        False,
        [
            run(1, 1),
            run(2, 2),
            fact(3, inView=True),
            fact(4, inView=True, loaded=True),
            fact(5, inView=True),
        ],
        {1: "running", 2: "running", 3: "waiting", 4: "running", 5: "waiting"},
        [],
        [],
        [3, 5],
    ),
    (
        "fill order: waiting cards start top to bottom",
        False,
        [fact(1, inView=True), fact(2, inView=True), fact(3, inView=True), fact(4, inView=True)],
        {1: "running", 2: "running", 3: "running", 4: "waiting"},
        [1, 2, 3],
        [],
        [4],
    ),
    (
        "ceiling 8: the oldest off-screen paused-auto is unloaded",
        False,
        [off(1, 50), off(2, 10), off(3, 30)]
        + [off(i, 100 + i) for i in range(4, 9)]
        + [fact(9, inView=True)],
        {**{i: "paused-auto" for i in (1, 3, 4, 5, 6, 7, 8)}, 2: "waiting", 9: "running"},
        [9],
        [2],
        [],
    ),
    (
        "ceiling 8: paused-auto outranks an older paused-user",
        False,
        [fact(1, userPaused=True, loaded=True, lastVisibleAt=1)]
        + [off(i, 100 + i) for i in range(2, 9)]
        + [fact(9, inView=True)],
        {**{i: "paused-auto" for i in range(3, 9)}, 1: "paused-user", 2: "waiting", 9: "running"},
        [9],
        [2],
        [],
    ),
    (
        "ceiling 8: with no paused-auto, the oldest off-screen paused-user goes",
        False,
        [fact(i, userPaused=True, loaded=True, lastVisibleAt=40 - i) for i in range(1, 9)]
        + [fact(9, inView=True)],
        {**{i: "paused-user" for i in range(1, 8)}, 8: "waiting", 9: "running"},
        [9],
        [8],
        [],
    ),
    (
        "ceiling 8: nothing off screen to unload keeps the new card waiting",
        False,
        [run(1, 1), run(2, 2)]
        + [fact(i, userPaused=True, loaded=True, inView=True) for i in range(3, 9)]
        + [fact(9, inView=True)],
        {1: "running", 2: "running", **{i: "paused-user" for i in range(3, 9)}, 9: "waiting"},
        [],
        [],
        [9],
    ),
    (
        "start requested outranks the oldest-started running card",
        False,
        [run(1, 1), run(2, 2), run(3, 3), fact(4, inView=True, startRequested=True)],
        {1: "paused-auto", 2: "running", 3: "running", 4: "running"},
        [4],
        [],
        [],
    ),
    (
        "start requested on a loaded card pauses the oldest-started runner",
        False,
        [run(1, 5), run(2, 2), run(3, 3), fact(4, inView=True, loaded=True, startRequested=True)],
        {1: "running", 2: "paused-auto", 3: "running", 4: "running"},
        [],
        [],
        [],
    ),
    (
        "an in-view unloaded userPaused card loads (reduced motion); loaded userPaused cards take no running slot",
        False,
        [
            fact(1, userPaused=True, loaded=True, inView=True),
            fact(2, userPaused=True, loaded=True, inView=True),
            run(3, 1),
            run(4, 2),
            fact(5, inView=True),
            fact(6, userPaused=True, inView=True),
        ],
        {
            1: "paused-user",
            2: "paused-user",
            3: "running",
            4: "running",
            5: "running",
            6: "paused-user",
        },
        [5, 6],
        [],
        [],
    ),
    (
        "loaded userPaused cards count against the ceiling",
        False,
        [fact(i, userPaused=True, loaded=True, lastVisibleAt=i) for i in range(1, 9)]
        + [fact(9, inView=True)],
        {**{i: "paused-user" for i in range(2, 9)}, 1: "waiting", 9: "running"},
        [9],
        [1],
        [],
    ),
    (
        "an out-of-view unloaded userPaused card stays waiting",
        False,
        [fact(1, userPaused=True)],
        {1: "waiting"},
        [],
        [],
        [],
    ),
]


@pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
def test_reconcile_table(engine_page: Page, case) -> None:
    name, hidden, instances, expected, load, unload, capped = case
    load_harness(engine_page)
    out = engine_page.evaluate(
        "(f) => App.ui.util.widgetReconcile(f)", {"hidden": hidden, "instances": instances}
    )
    got = {int(k): v for k, v in out["states"].items()}
    assert got == expected, name
    assert sorted(out["load"]) == sorted(load), name
    assert sorted(out["unload"]) == sorted(unload), name
    assert sorted(out["capped"]) == sorted(capped), name


def test_reconcile_is_pure_and_idempotent(engine_page: Page) -> None:
    load_harness(engine_page)
    facts = {"hidden": False, "instances": [run(1, 1), run(2, 2), run(3, 3), fact(4, inView=True)]}
    res = engine_page.evaluate(
        """(f) => {
          const before = JSON.stringify(f);
          const a = App.ui.util.widgetReconcile(f);
          const b = App.ui.util.widgetReconcile(f);
          return {same: JSON.stringify(a) === JSON.stringify(b), untouched: JSON.stringify(f) === before};
        }""",
        facts,
    )
    assert res == {"same": True, "untouched": True}


# ---- AC2: the live lifecycle ------------------------------------------------------------------


def _frozen(page: Page, i: int) -> bool:
    a = counter(page, i)
    page.wait_for_timeout(300)
    return counter(page, i) == a


def _ticking(page: Page, i: int) -> bool:
    a = counter(page, i)
    page.wait_for_timeout(300)
    return counter(page, i) > a


SPACER = "() => { const s = document.createElement('div'); s.style.height = '4000px'; document.getElementById('stack').after(s); }"


def test_cap_card_scroll_pause_and_resume(engine_page: Page, sink: WidgetSink) -> None:
    p = engine_page
    p.set_viewport_size({"width": 900, "height": 1400})
    setup_cards(p, sink)
    make_cards(p, 4)
    p.evaluate(SPACER)
    wait_states(p, ["running", "running", "running", "waiting"])
    # the cap card: the body text and a Start button
    assert "Paused: three widgets are already running." in p.get_by_test_id("w3").inner_text()
    assert p.get_by_test_id("w3-start").inner_text().strip() == "Start"
    assert p.get_by_test_id("w3-frame").count() == 0
    assert p.evaluate("() => __cards[3]._frame()") is None
    # scroll card 0 out of view: it is paused-auto with its counter frozen; the capped card starts
    p.evaluate(
        "() => window.scrollTo(0, __cards[0].el.getBoundingClientRect().bottom + window.scrollY + 10)"
    )
    wait_states(p, ["paused-auto", "running", "running", "running"])
    assert _frozen(p, 0)
    assert p.get_by_test_id("w3-start").count() == 0
    n_before = counter(p, 0)
    p.wait_for_function(
        "() => __cards[0]._frame() && __cards[0]._frame().loads() >= 1", timeout=8000
    )
    loads = p.evaluate("() => __cards[0]._frame().loads()")
    # back in view: the cap holds (B, C, D run), so card 0 stays paused-auto until a slot frees
    p.evaluate("() => window.scrollTo(0, 0)")
    p.wait_for_timeout(400)
    assert states(p) == ["paused-auto", "running", "running", "running"]
    # the operator pauses card 3: a slot frees and card 0 resumes where it was (no restart)
    p.evaluate("() => __cards[3].pause()")
    wait_states(p, ["running", "running", "running", "paused-user"])
    assert p.evaluate("() => __cards[0]._frame().loads()") == loads
    assert _ticking(p, 0)
    assert counter(p, 0) >= n_before


def test_start_on_a_capped_card_pauses_the_oldest_started(
    engine_page: Page, sink: WidgetSink
) -> None:
    p = engine_page
    p.set_viewport_size({"width": 900, "height": 1400})
    setup_cards(p, sink)
    make_cards(p, 4)
    wait_states(p, ["running", "running", "running", "waiting"])
    p.get_by_test_id("w3-start").click()
    wait_states(p, ["paused-auto", "running", "running", "running"])
    assert p.get_by_test_id("w3-start").count() == 0
    assert _ticking(p, 3)
    assert _frozen(p, 0)


def test_cap_card_status_and_focus_after_start(engine_page: Page, sink: WidgetSink) -> None:
    p = engine_page
    p.set_viewport_size({"width": 900, "height": 1400})
    setup_cards(p, sink)
    make_cards(p, 4)
    wait_states(p, ["running", "running", "running", "waiting"])
    # the cap announces through the card's status, present since construction
    assert p.get_by_test_id("w3-status").get_attribute("role") == "status"
    assert (
        p.get_by_test_id("w3-status").text_content() == "Paused: three widgets are already running."
    )
    assert p.get_by_test_id("w0-status").text_content() == ""  # a running card says nothing
    # Start by keyboard: the focused button goes away, focus lands on the card's Pause
    p.get_by_test_id("w3-start").focus()
    p.keyboard.press("Enter")
    wait_states(p, ["paused-auto", "running", "running", "running"])
    assert (
        p.evaluate("() => document.activeElement && document.activeElement.dataset.testid")
        == "w3-pause"
    )
    assert p.get_by_test_id("w3-status").text_content() == ""
    # an automatic pause announces nothing
    assert p.get_by_test_id("w0-status").text_content() == ""


def test_nine_loaded_unloads_the_oldest_visible_paused_auto(
    engine_page: Page, sink: WidgetSink
) -> None:
    p = engine_page
    p.set_viewport_size({"width": 900, "height": 560})
    setup_cards(p, sink)
    make_cards(p, 9)
    for i in range(9):
        scroll_to_card(p, i)
        p.wait_for_function("(i) => __cards[i].state() === 'running'", arg=i, timeout=8000)
    p.wait_for_timeout(300)
    st = states(p)
    assert st.count("waiting") == 1 and st[0] == "waiting", st
    assert sum(1 for s in st if s != "waiting") == 8
    # back at the top it loads again, from the beginning (a fresh frame)
    scroll_to_card(p, 0)
    p.wait_for_function("() => __cards[0].state() === 'running'", timeout=8000)
    # a card reads running as soon as it mounts, before its load is counted
    p.wait_for_function(
        "() => __cards[0]._frame() && __cards[0]._frame().loads() === 1", timeout=8000
    )
    assert p.evaluate("() => __cards[0]._frame().loads()") == 1
    assert states(p).count("waiting") == 1


def test_paused_user_stays_paused_across_scrolling(engine_page: Page, sink: WidgetSink) -> None:
    p = engine_page
    p.set_viewport_size({"width": 900, "height": 560})
    setup_cards(p, sink)
    make_cards(p, 2)
    p.evaluate(
        "() => { const s = document.createElement('div'); s.style.height = '3000px'; document.getElementById('stack').after(s); }"
    )
    wait_states(p, ["running", "running"])
    p.get_by_test_id("w0-pause").click()
    assert states(p)[0] == "paused-user"
    p.evaluate("() => window.scrollTo(0, 2500)")
    p.wait_for_timeout(500)
    assert states(p)[0] == "paused-user"
    p.evaluate("() => window.scrollTo(0, 0)")
    p.wait_for_timeout(500)
    assert states(p) == ["paused-user", "running"]
    assert _frozen(p, 0)
    p.get_by_test_id("w0-pause").click()
    wait_states(p, ["running", "running"])
    assert _ticking(p, 0)


def test_hidden_pauses_everything_and_visible_resumes(engine_page: Page, sink: WidgetSink) -> None:
    p = engine_page
    p.set_viewport_size({"width": 900, "height": 1000})
    setup_cards(p, sink)
    make_cards(p, 2)
    wait_states(p, ["running", "running"])
    fake_hidden(p, True)
    wait_states(p, ["paused-auto", "paused-auto"])
    assert _frozen(p, 0) and _frozen(p, 1)
    fake_hidden(p, False)
    wait_states(p, ["running", "running"])
    assert _ticking(p, 0) and _ticking(p, 1)


def test_a_card_created_while_hidden_waits_until_visible(
    engine_page: Page, sink: WidgetSink
) -> None:
    p = engine_page
    p.set_viewport_size({"width": 900, "height": 1000})
    setup_cards(p, sink)
    fake_hidden(p, True)
    make_cards(p, 1)
    p.wait_for_timeout(500)
    assert states(p) == ["waiting"]
    assert card_frame(p, 0) is None
    fake_hidden(p, False)
    wait_states(p, ["running"])


def test_a_tall_card_in_a_short_viewport_is_in_view_by_the_half_root_rule(
    engine_page: Page, sink: WidgetSink
) -> None:
    p = engine_page
    p.set_viewport_size({"width": 900, "height": 180})
    setup_cards(p, sink)
    tall = '<div style="height:720px">t</div><script>window.__n = 0; setInterval(function () { window.__n++; }, 20);</script>'
    make_cards(p, 1, source=tall)
    wait_states(p, ["running"])
    p.wait_for_function("() => __cards[0].el.getBoundingClientRect().height > 700", timeout=8000)
    p.wait_for_timeout(600)
    # the visible part is under a quarter of the card but over half of the viewport
    ratio = p.evaluate("() => 180 / __cards[0].el.getBoundingClientRect().height")
    assert ratio < 0.25
    assert states(p) == ["running"]
    p.evaluate("() => window.scrollBy(0, 300)")
    p.wait_for_timeout(500)
    assert states(p) == ["running"]
    assert _ticking(p, 0)


def test_destroy_before_the_observer_callback_is_a_no_op(
    engine_page: Page, sink: WidgetSink
) -> None:
    p = engine_page
    errors: list[str] = []
    p.on("pageerror", lambda e: errors.append(str(e)))
    setup_cards(p, sink)
    p.evaluate(
        """(s) => {
          const a = __make(s), b = __make(s);
          a.destroy();                       // its observer entry is still queued
          window.__b = b;
        }""",
        COUNTER,
    )
    p.wait_for_timeout(600)
    assert errors == []
    assert p.evaluate("() => App.ui.widget._counts().cards") == 1
    assert p.evaluate("() => __b.state()") == "running"
    assert p.evaluate("() => document.querySelectorAll('iframe').length") == 1


def test_reduced_motion_starts_paused_with_one_frame_drawn(
    engine_page: Page, sink: WidgetSink
) -> None:
    p = engine_page
    p.emulate_media(reduced_motion="reduce")
    p.set_viewport_size({"width": 900, "height": 1000})
    setup_cards(p, sink)
    raf = (
        '<div style="height:80px">r</div><script>window.__frames = 0;'
        "(function f() { window.__frames++; requestAnimationFrame(f); })();</script>"
    )
    make_cards(p, 1, source=raf)
    wait_states(p, ["paused-user"])
    p.wait_for_selector("iframe", timeout=8000)
    f = card_frame(p, 0)
    f.wait_for_function("() => window.__frames >= 1")
    p.wait_for_timeout(500)
    held = int(f.evaluate("() => window.__frames"))
    p.wait_for_timeout(400)
    assert int(f.evaluate("() => window.__frames")) == held  # held after the first round
    assert p.get_by_test_id("w0-paused").inner_text().strip() == "Paused"
    p.get_by_test_id("w0-pause").click()
    wait_states(p, ["running"])
    p.wait_for_timeout(400)
    assert int(f.evaluate("() => window.__frames")) > held


def test_the_manager_is_released_with_the_last_card(engine_page: Page, sink: WidgetSink) -> None:
    p = engine_page
    p.set_viewport_size({"width": 900, "height": 1400})
    setup_cards(p, sink)
    assert p.evaluate("() => App.ui.widget._counts()") == {
        "observers": 0,
        "ticks": 0,
        "listeners": 0,
        "cards": 0,
    }
    make_cards(p, 3)
    wait_states(p, ["running", "running", "running"])
    assert p.evaluate("() => App.ui.widget._counts()") == {
        "observers": 1,
        "ticks": 1,
        "listeners": 2,
        "cards": 3,
    }
    # the log is wiped without destroy(): sweep reaps every card and the manager lets go
    # (one task: a separate evaluate lets the observer's next callback reap the cards first, which
    # is also clean but makes the sweep count 0: a race, flaky at about one run in two)
    swept = p.evaluate(
        "() => { document.getElementById('stack').replaceChildren(); return App.ui.widget.sweep(); }"
    )
    assert swept == 3
    assert p.evaluate("() => App.ui.widget._counts()") == {
        "observers": 0,
        "ticks": 0,
        "listeners": 0,
        "cards": 0,
    }
    assert p.evaluate("() => App.ui.widget._instances()") == 0
    assert (
        p.evaluate(
            "() => Object.keys(localStorage).filter((k) => k.startsWith('widget-running:')).length"
        )
        == 0
    )
    # and a new card installs it again
    make_cards(p, 1)
    p.wait_for_function("() => __cards[3].state() === 'running'", timeout=8000)
    assert p.evaluate("() => App.ui.widget._counts().cards") == 1


def test_a_waiting_card_keeps_the_manager_alive(engine_page: Page, sink: WidgetSink) -> None:
    p = engine_page
    p.set_viewport_size({"width": 900, "height": 400})
    setup_cards(p, sink)
    make_cards(p, 1)
    p.evaluate(SPACER)
    p.evaluate("() => window.scrollTo(0, 3000)")
    p.wait_for_timeout(300)
    assert p.evaluate("() => App.ui.widget._counts()") == {
        "observers": 1,
        "ticks": 1,
        "listeners": 2,
        "cards": 1,
    }
    p.evaluate("() => __cards[0].destroy()")
    assert p.evaluate("() => App.ui.widget._counts()") == {
        "observers": 0,
        "ticks": 0,
        "listeners": 0,
        "cards": 0,
    }


def test_restart_and_start_anyway_go_through_the_manager(
    engine_page: Page, sink: WidgetSink
) -> None:
    p = engine_page
    p.set_viewport_size({"width": 900, "height": 1400})
    setup_cards(p, sink)
    make_cards(p, 4)
    wait_states(p, ["running", "running", "running", "waiting"])
    # Restart on a running card remounts it under the cap (a fresh frame, still running)
    p.evaluate("() => { window.__old = __cards[1]._frame(); }")
    p.get_by_test_id("w1-restart").click()
    p.wait_for_function("() => __cards[1]._frame() && __cards[1]._frame() !== __old", timeout=8000)
    wait_states(p, ["running", "running", "running", "waiting"])
    # a stopped card's Start anyway is a request subject to the cap
    p.evaluate("() => __cards[2].stop('hung')")
    wait_states(p, ["running", "running", "stopped-hung", "running"])
    p.get_by_test_id("w2-start").click()
    wait_states(p, ["paused-auto", "running", "running", "running"])
    assert _ticking(p, 2)


# ---- Remounts keep the slot height (HAT step 4: scrolling up fought the reader) ---------------

BODY_H = "(i) => Math.round(__cards[i].el.querySelector('.ui-widget-body').getBoundingClientRect().height)"
TALL = '<div style="height:300px">w</div><script>setInterval(function(){},50);</script>'


def test_a_remount_keeps_the_slot_and_frame_height(engine_page: Page, sink: WidgetSink) -> None:
    p = engine_page
    setup_cards(p, sink)
    p.evaluate("(s) => __make(s, {managed: false})", TALL)
    p.wait_for_function("() => __cards[0]._frame().iframe.style.height === '300px'")
    # Remount: before the new document's first size message the slot and the new frame are
    # already at the reported height (not the 240px initial height).
    got = p.evaluate(
        """() => {
          const c = __cards[0];
          c.restart();
          const body = c.el.querySelector('.ui-widget-body');
          return [body.style.height, c._frame().iframe.style.height, Math.round(body.getBoundingClientRect().height)];
        }"""
    )
    assert got == ["300px", "300px", 300]


def test_a_first_mount_still_starts_at_the_initial_height(
    engine_page: Page, sink: WidgetSink
) -> None:
    p = engine_page
    setup_cards(p, sink)
    got = p.evaluate(
        """(s) => {
          const c = __make(s, {managed: false});
          const body = c.el.querySelector('.ui-widget-body');
          return [body.style.height, c._frame().iframe.style.height];
        }""",
        TALL,
    )
    assert got == ["", "240px"]


def test_the_cap_card_does_not_shrink_a_seen_slot(engine_page: Page, sink: WidgetSink) -> None:
    p = engine_page
    p.set_viewport_size({"width": 900, "height": 560})
    setup_cards(p, sink)
    make_cards(p, 9, TALL)
    for i in range(9):
        scroll_to_card(p, i)
        p.wait_for_function("(i) => __cards[i].state() === 'running'", arg=i, timeout=8000)
    p.wait_for_timeout(300)
    # card 0 was unloaded (the ninth loaded card) after being seen at 300px
    assert states(p)[0] == "waiting"
    assert p.evaluate(BODY_H, 0) == 300
    # every card in view at once: three run, the others are held by the cap
    p.set_viewport_size({"width": 900, "height": 4200})
    p.wait_for_timeout(800)
    st = states(p)
    capped = [i for i, s in enumerate(st) if s == "waiting"]
    assert capped, st
    for i in capped:
        assert p.get_by_test_id(f"w{i}-start").count() == 1
        # every card here was seen at 300px: the cap card keeps that slot height
        assert p.evaluate(BODY_H, i) == 300, (i, st)


# A reader scrolling up a long chat of animated cards must not be pushed back (the card above
# reloading as it enters must not change the slot height).
CANVAS = (
    '<title>Orbit</title><canvas id="c" width="400" height="200" style="width:100%;max-width:400px"></canvas>'
    '<script>const g=document.getElementById("c").getContext("2d");let t=0;'
    "function f(){t+=.03;g.clearRect(0,0,400,200);g.beginPath();g.arc(200+70*Math.cos(t),100+70*Math.sin(t),12,0,7);g.fill();requestAnimationFrame(f)}f();</script>"
)


def test_scrolling_up_across_reloading_cards_never_snaps_back(
    engine_page: Page, sink: WidgetSink
) -> None:
    p = engine_page
    p.set_viewport_size({"width": 900, "height": 700})
    setup_cards(p, sink)
    make_cards(p, 12, CANVAS)
    p.evaluate(
        """() => {
          const s = document.getElementById('stack');
          s.style.cssText = 'height:600px;overflow-y:auto;width:800px';
          window.__log = [];
          (function tick() { window.__log.push(s.scrollTop); requestAnimationFrame(tick); })();
        }"""
    )
    p.wait_for_timeout(1000)
    to_bottom = (
        "() => { const s = document.getElementById('stack'); s.scrollTop = s.scrollHeight; }"
    )
    p.mouse.move(400, 300)
    for rnd in range(2):
        p.evaluate(to_bottom)
        p.wait_for_timeout(1200)
        p.evaluate("() => { window.__log.length = 0; }")
        for _ in range(48):
            if p.evaluate("() => document.getElementById('stack').scrollTop") < 5:
                break
            p.mouse.wheel(0, -60)
            p.wait_for_timeout(100)
        log = p.evaluate("() => window.__log")
        if rnd == 1:
            # second pass = every card above reloads as it enters: scrollTop never increases
            ups = [(a, b) for a, b in zip(log, log[1:]) if b > a + 1]
            assert ups == [], ups


# ---- One slot change per first load, kept heights, remembered heights --------------------------

# Make a managed card with a testable record: ``__seq`` (every distinct slot height, in order)
# and ``__ins`` (the slot height and the frame height at the moment the iframe is inserted).
MAKE_RECORDED = """([src, key]) => {
  const c = __make(src, {key});
  const body = c.el.querySelector('.ui-widget-body');
  window.__seq = [body.style.height]; window.__ins = null;
  new MutationObserver(() => {
    const v = body.style.height;
    if (window.__seq[window.__seq.length - 1] !== v) window.__seq.push(v);
    const f = body.querySelector('iframe');
    if (f && !window.__ins) window.__ins = [body.style.height, f.style.height];
  }).observe(body, {attributes: true, attributeFilter: ['style'], childList: true});
  return __cards.length - 1;
}"""


def test_a_first_load_changes_the_slot_once_not_twice(engine_page: Page, sink: WidgetSink) -> None:
    p = engine_page
    p.set_viewport_size({"width": 900, "height": 900})
    setup_cards(p, sink)
    # A widget whose first report comes before layout (raw height 0; headed Chrome showed this
    # for a canvas widget). The widget posts it itself, so the test is deterministic.
    pre_layout = (
        '<div id="d"></div><script>setTimeout(function () { '
        'document.getElementById("d").style.height = "300px"; }, 400);'
        "setInterval(function () {}, 50);</script>"
    )
    i = p.evaluate(MAKE_RECORDED, [pre_layout, "first-key"])
    p.wait_for_function(f"() => __cards[{i}].state() === 'running'", timeout=8000)
    p.wait_for_function(
        f"() => __cards[{i}]._frame().iframe.style.height === '300px'", timeout=8000
    )
    p.wait_for_timeout(800)
    # waiting height, then the real height: never the 48 px minimum in between
    assert p.evaluate("() => __seq") == ["240px", "300px"]


def test_a_content_under_the_minimum_still_ends_at_the_minimum(
    engine_page: Page, sink: WidgetSink
) -> None:
    p = engine_page
    setup_cards(p, sink)
    i = p.evaluate(MAKE_RECORDED, ['<div style="height:10px">w</div>', "tiny-key"])
    p.wait_for_function(
        f"() => __cards[{i}]._frame() && __cards[{i}]._frame().iframe.style.height === '48px'",
        timeout=8000,
    )
    assert p.evaluate("() => __seq")[-1] == "48px"


def test_a_stopped_card_keeps_its_slot_height(engine_page: Page, sink: WidgetSink) -> None:
    p = engine_page
    p.set_viewport_size({"width": 900, "height": 900})
    setup_cards(p, sink)
    make_cards(p, 1, TALL)
    p.wait_for_function(
        "() => __cards[0]._frame() && __cards[0]._frame().iframe.style.height === '300px'",
        timeout=8000,
    )
    p.evaluate("() => __cards[0].stop('hung')")
    assert p.evaluate(BODY_H, 0) == 300
    # a never-seen card that is stopped keeps the waiting height, and so does an escaped one
    p.evaluate("(s) => { __make(s, {managed: false}); }", "<div>x</div>")
    p.evaluate("() => __cards[1].stop('hung')")
    # (the known height is a minimum in these states, so the notice can grow past it)
    assert (
        p.evaluate("() => __cards[1].el.querySelector('.ui-widget-body').style.minHeight")
        == "240px"
    )


FIT = """(i) => {
  const c = __cards[i];
  const body = c.el.querySelector('.ui-widget-body').getBoundingClientRect();
  const btn = c.el.querySelector('.ui-widget-body button').getBoundingClientRect();
  const txt = c.el.querySelector('.ui-widget-body span').getBoundingClientRect();
  const src = c.el.querySelector('.ui-widget-source').getBoundingClientRect();
  return {body: [body.top, body.bottom], btn: [btn.top, btn.bottom], txt: [txt.top, txt.bottom], src: src.top, h: body.height};
}"""


def _assert_notice_fits(p: Page) -> None:
    r = p.evaluate(FIT, 0)
    assert r["btn"][0] >= r["body"][0] - 0.5 and r["btn"][1] <= r["body"][1] + 0.5, r
    assert r["txt"][0] >= r["body"][0] - 0.5 and r["txt"][1] <= r["body"][1] + 0.5, r
    assert r["body"][1] <= r["src"] + 0.5, r
    # the slot never shrinks below the known height (48 px), and grew to fit the notice
    assert r["h"] > 48, r


def test_a_stopped_small_widget_notice_fits_at_a_narrow_width(
    engine_page: Page, sink: WidgetSink
) -> None:
    p = engine_page
    p.set_viewport_size({"width": 900, "height": 900})
    setup_cards(p, sink)
    p.evaluate("() => { document.getElementById('stack').style.width = '320px'; }")
    make_cards(
        p, 1, '<div style="height:10px">w</div><script>setInterval(function(){},50);</script>'
    )
    p.wait_for_function(
        "() => __cards[0]._frame() && __cards[0]._frame().iframe.style.height === '48px'",
        timeout=8000,
    )
    p.evaluate("() => __cards[0].stop('hung')")
    _assert_notice_fits(p)


def test_a_capped_small_widget_notice_fits_at_a_narrow_width(
    engine_page: Page, sink: WidgetSink
) -> None:
    p = engine_page
    p.set_viewport_size({"width": 900, "height": 900})
    setup_cards(p, sink)
    p.evaluate("() => { document.getElementById('stack').style.width = '320px'; }")
    p.evaluate(
        "(s) => { __make(s, {managed: false}); }",
        '<div style="height:10px">w</div><script>setInterval(function(){},50);</script>',
    )
    p.wait_for_function(
        "() => __cards[0]._frame() && __cards[0]._frame().iframe.style.height === '48px'",
        timeout=8000,
    )
    p.evaluate("() => { __cards[0].unload(); __cards[0]._setCapped(true); }")
    assert p.get_by_test_id("w0-start").count() == 1
    _assert_notice_fits(p)


def test_a_re_rendered_card_starts_at_its_remembered_height(
    engine_page: Page, sink: WidgetSink
) -> None:
    p = engine_page
    p.set_viewport_size({"width": 900, "height": 900})
    setup_cards(p, sink)
    i = p.evaluate(MAKE_RECORDED, [TALL, "memo-key"])
    p.wait_for_function(
        f"() => __cards[{i}]._frame() && __cards[{i}]._frame().iframe.style.height === '300px'",
        timeout=8000,
    )
    p.wait_for_timeout(300)
    p.evaluate("() => { __cards[0].destroy(); __cards[0].el.remove(); }")
    # the same history rendered again at the same width: same key, so the slot starts at 300 and
    # the frame is inserted at 300; loading changes nothing
    j = p.evaluate(MAKE_RECORDED, [TALL, "memo-key"])
    p.wait_for_function(
        f"() => __cards[{j}]._frame() && __cards[{j}]._frame().iframe.style.height === '300px'",
        timeout=8000,
    )
    p.wait_for_timeout(600)
    assert p.evaluate("() => __ins") == ["300px", "300px"]
    assert p.evaluate("() => __seq") == ["240px", "300px"]


def test_a_width_change_ignores_the_remembered_height(engine_page: Page, sink: WidgetSink) -> None:
    p = engine_page
    p.set_viewport_size({"width": 900, "height": 900})
    setup_cards(p, sink)
    p.evaluate("() => { document.getElementById('stack').style.width = '800px'; }")
    i = p.evaluate(MAKE_RECORDED, [TALL, "width-key"])
    p.wait_for_function(
        f"() => __cards[{i}]._frame() && __cards[{i}]._frame().iframe.style.height === '300px'",
        timeout=8000,
    )
    p.wait_for_timeout(300)
    p.evaluate(
        "() => { __cards[0].destroy(); __cards[0].el.remove(); document.getElementById('stack').style.width = '500px'; }"
    )
    j = p.evaluate(MAKE_RECORDED, [TALL, "width-key"])
    p.wait_for_function(
        f"() => __cards[{j}]._frame() && __cards[{j}]._frame().iframe.style.height === '300px'",
        timeout=8000,
    )
    assert p.evaluate("() => __ins") == ["240px", "240px"]
