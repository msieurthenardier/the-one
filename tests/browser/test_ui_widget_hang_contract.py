# ruff: noqa: E501  (inline widget sources are evaluated verbatim)
"""The widget hang guard (M35 F2 L5, flight DD9): the crash record, stall detection and heartbeat
loss. Both engines, driven through the clock seam; the real runaway widget is full Chromium only
(a runaway freezes the headless shell and WebKit page)."""

from __future__ import annotations

import re
import time

import pytest
from browser._widget_harness import (
    COUNTER,
    card_frame,
    make_cards,
    setup_cards,
    states,
    wait_states,
)
from browser._widget_sink import WidgetSink
from playwright.sync_api import Page, Playwright

pytestmark = pytest.mark.browser


@pytest.fixture(scope="module")
def sink():
    s = WidgetSink()
    try:
        yield s
    finally:
        s.close()


def seed(page: Page, age_ms: int, hidden: bool, keys: list[str], rid: str = "seed1") -> None:
    """Plant a foreign crash record before the library loads (it is read when the module loads)."""
    page.add_init_script(
        "try { localStorage.setItem('widget-running:%s', JSON.stringify({keys: %s, ts: Date.now() - %d, hidden: %s})); } catch (e) {}"
        % (rid, str(keys).replace("'", '"'), age_ms, "true" if hidden else "false")
    )


def storage_keys(page: Page) -> list[str]:
    return page.evaluate(
        "() => Object.keys(localStorage).filter((k) => k.startsWith('widget-running:'))"
    )


def jump(page: Page, ms: int) -> None:
    """Move the manager's clock forward and run one tick, in one synchronous step."""
    page.evaluate(
        """(ms) => {
          const real = App.ui.widget._clock;
          window.__off = (window.__off || 0) + ms;
          App.ui.widget._clock = () => performance.now() + window.__off;
          App.ui.widget._tick();
        }""",
        ms,
    )


# ---- the crash record --------------------------------------------------------------------------


def test_a_fresh_foreign_record_is_ignored(engine_page: Page, sink: WidgetSink) -> None:
    p = engine_page
    seed(p, 5000, False, ["k0"])
    p.set_viewport_size({"width": 900, "height": 900})
    setup_cards(p, sink)
    assert p.evaluate("() => App.ui.widget._stale()") == []
    assert "widget-running:seed1" in storage_keys(p)
    make_cards(p, 1)
    wait_states(p, ["running"])


def test_a_stale_visible_record_stops_its_keys_for_the_pages_lifetime(
    engine_page: Page, sink: WidgetSink
) -> None:
    p = engine_page
    seed(p, 11000, False, ["k0", "k5"])
    p.set_viewport_size({"width": 900, "height": 900})
    setup_cards(p, sink)
    assert p.evaluate("() => App.ui.widget._stale()") == ["k0", "k5"]
    assert "widget-running:seed1" not in storage_keys(p)  # the record is deleted
    make_cards(p, 2)  # keys k0, k1
    wait_states(p, ["stopped-hung", "running"])
    assert "stopped responding last time" in p.get_by_test_id("w0-stopped").inner_text()
    assert p.get_by_test_id("w0-start").inner_text().strip() == "Start anyway"
    # a card created later (a history render) with a stale key also comes up stopped
    p.evaluate("(s) => { __make(s, {key: 'k5'}); }", COUNTER)
    wait_states(p, ["stopped-hung", "running", "stopped-hung"])
    # Start anyway consumes the key: the card runs, and a new card with that key is not stopped
    p.get_by_test_id("w0-start").click()
    wait_states(p, ["running", "running", "stopped-hung"])
    assert p.evaluate("() => App.ui.widget._stale()") == ["k5"]
    p.evaluate("(s) => { __make(s, {key: 'k0'}); }", COUNTER)
    wait_states(p, ["running", "running", "stopped-hung", "running"])


def test_two_cards_with_the_same_key_are_both_stopped_by_a_matching_record(
    engine_page: Page, sink: WidgetSink
) -> None:
    """AC4: the key identifies a card in the record; a shared key is documented to stop both."""
    p = engine_page
    seed(p, 11000, False, ["shared"])
    p.set_viewport_size({"width": 900, "height": 900})
    setup_cards(p, sink)
    p.evaluate(
        "(s) => { __make(s, {key: 'shared'}); __make(s, {key: 'shared'}); __make(s, {key: 'other'}); }",
        COUNTER,
    )
    wait_states(p, ["stopped-hung", "stopped-hung", "running"])


@pytest.mark.parametrize(
    ("age_ms", "hidden", "stale"),
    [
        (11000, False, True),
        (9000, False, False),
        (60000, True, False),  # a hidden page's timers are throttled to about once a minute
        (91000, True, True),
        (60000, False, True),
    ],
    ids=["visible-11s", "visible-9s", "hidden-60s", "hidden-91s", "visible-60s"],
)
def test_record_staleness_thresholds(
    engine_page: Page, sink: WidgetSink, age_ms, hidden, stale
) -> None:
    p = engine_page
    seed(p, age_ms, hidden, ["k0"])
    setup_cards(p, sink)
    assert p.evaluate("() => App.ui.widget._stale()") == (["k0"] if stale else [])
    assert ("widget-running:seed1" not in storage_keys(p)) is stale


def test_own_record_is_written_while_loaded_and_cleared_on_pagehide(
    engine_page: Page, sink: WidgetSink
) -> None:
    p = engine_page
    p.set_viewport_size({"width": 900, "height": 900})
    setup_cards(p, sink)
    assert storage_keys(p) == []
    make_cards(p, 2)
    wait_states(p, ["running", "running"])
    rec = p.evaluate(
        """() => {
          App.ui.widget._tick();
          const k = Object.keys(localStorage).filter((k) => k.startsWith('widget-running:'));
          return {n: k.length, own: k[0] === 'widget-running:' + App.ui.widget._pageId(),
                  rec: JSON.parse(localStorage.getItem(k[0]))};
        }"""
    )
    assert rec["n"] == 1 and rec["own"]
    assert sorted(rec["rec"]["keys"]) == ["k0", "k1"] and rec["rec"]["hidden"] is False
    assert abs(rec["rec"]["ts"] - time.time() * 1000) < 60000
    p.evaluate("() => window.dispatchEvent(new Event('pagehide'))")
    assert storage_keys(p) == []


def test_storage_failures_are_survived(engine_page: Page, sink: WidgetSink) -> None:
    p = engine_page
    errors: list[str] = []
    p.on("pageerror", lambda e: errors.append(str(e)))
    p.add_init_script(
        "Storage.prototype.setItem = function () { throw new Error('quota'); };"
        "Storage.prototype.getItem = function () { throw new Error('denied'); };"
    )
    p.set_viewport_size({"width": 900, "height": 900})
    setup_cards(p, sink)
    make_cards(p, 1)
    wait_states(p, ["running"])
    p.evaluate("() => App.ui.widget._tick()")
    assert errors == []


# ---- stall, suspend, heartbeat -----------------------------------------------------------------


def test_a_five_second_stall_stops_every_loaded_card_and_a_long_gap_is_a_suspend(
    engine_page: Page, sink: WidgetSink
) -> None:
    p = engine_page
    p.set_viewport_size({"width": 900, "height": 1000})
    setup_cards(p, sink)
    make_cards(p, 3)
    wait_states(p, ["running", "running", "running"])
    p.evaluate("() => __cards[1].pause()")  # a paused card is guarded too
    wait_states(p, ["running", "paused-user", "running"])
    # a gap over 60 s is a suspend: reset, stop nothing (the heartbeat age alone would stop them)
    jump(p, 61000)
    assert states(p) == ["running", "paused-user", "running"]
    # a 5 s gap is a stall: every loaded card, paused or not, is stopped
    jump(p, 5000)
    assert states(p) == ["stopped-hung"] * 3
    assert "This widget stopped responding." in p.get_by_test_id("w0-stopped").inner_text()
    assert "last time" not in p.get_by_test_id("w0-stopped").inner_text()
    assert p.get_by_test_id("w0-start").inner_text().strip() == "Start anyway"
    assert p.locator("iframe").count() == 0
    assert storage_keys(p) == []  # nothing is loaded, so no record


def test_heartbeat_loss_stops_a_loaded_card_while_the_page_ticks(
    engine_page: Page, sink: WidgetSink
) -> None:
    p = engine_page
    p.set_viewport_size({"width": 900, "height": 900})
    setup_cards(p, sink)
    make_cards(p, 2)
    wait_states(p, ["running", "running"])
    # "running" is the card's mode, true from the moment it mounts; the guard's heartbeat clock
    # starts only when its iframe has loaded. Under load the second iframe can still be loading,
    # so wait for both loads or the tick below finds no beat to age out (squawk 0351).
    for i in range(2):
        frame = card_frame(p, i)
        assert frame is not None
        frame.wait_for_load_state("load")
    p.evaluate("() => new Promise((r) => requestAnimationFrame(() => r()))")
    p.evaluate("() => __cards[1].pause()")
    res = p.evaluate(
        """() => {
          // Each tick gap stays under 5 s, so only the heartbeat age can trip.
          const t = App.ui.widget._tick;
          t();
          window.__off = 3900;
          App.ui.widget._clock = () => performance.now() + window.__off;
          t();
          const a = __states();
          window.__off += 3900;
          t();
          return {a, b: __states()};
        }"""
    )
    assert res["a"] == ["running", "paused-user"]
    assert res["b"] == ["stopped-hung", "stopped-hung"]


def test_hidden_suspends_the_checks_and_visible_resets_them(
    engine_page: Page, sink: WidgetSink
) -> None:
    p = engine_page
    p.set_viewport_size({"width": 900, "height": 900})
    setup_cards(p, sink)
    make_cards(p, 1)
    wait_states(p, ["running"])
    p.evaluate(
        "() => { Object.defineProperty(document, 'hidden', {configurable: true, get: () => true}); document.dispatchEvent(new Event('visibilitychange')); }"
    )
    wait_states(p, ["paused-auto"])
    jump(p, 30000)  # far past every threshold, but the page is hidden
    assert states(p) == ["paused-auto"]
    rec = p.evaluate(
        "() => JSON.parse(localStorage.getItem('widget-running:' + App.ui.widget._pageId()))"
    )
    assert rec["hidden"] is True
    p.evaluate(
        "() => { delete document.hidden; document.dispatchEvent(new Event('visibilitychange')); App.ui.widget._tick(); }"
    )
    wait_states(p, ["running"])  # the tick and the heartbeats were reset on becoming visible


# ---- a real runaway widget: full Chromium only -------------------------------------------------


def test_a_real_runaway_widget_is_stopped_while_the_page_keeps_ticking(
    playwright_instance: Playwright, sink: WidgetSink
) -> None:
    try:
        browser = playwright_instance.chromium.launch(channel="chromium", headless=True)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"full Chromium (channel=chromium) cannot launch: {exc}")
    try:
        # The runaway wedges the headless shell; only the full browser keeps the page responsive.
        # The launched channel is asserted: the full browser reports a reduced user agent
        # (`/N.0.0.0`), the shell its whole version.
        ctx = browser.new_context()
        p = ctx.new_page()
        ua = p.evaluate("navigator.userAgent")
        assert re.search(r"Chrome/\d+\.0\.0\.0", ua), f"not the full Chromium channel: {ua}"
        p.set_viewport_size({"width": 900, "height": 900})
        setup_cards(p, sink)
        p.evaluate("() => { window.__pt = 0; setInterval(() => window.__pt++, 100); }")
        make_cards(
            p,
            1,
            source='<div style="height:80px">x</div><script>setTimeout(function () { for (;;); }, 100);</script>',
        )
        t0 = time.monotonic()
        p.wait_for_function("() => __cards[0].state() === 'stopped-hung'", timeout=12000)
        elapsed = time.monotonic() - t0
        assert elapsed < 9.5, elapsed
        ticks = p.evaluate("() => window.__pt")
        p.wait_for_timeout(500)
        assert p.evaluate("() => window.__pt") > ticks  # the page itself never froze
        assert p.locator("iframe").count() == 0
        assert "stopped responding" in p.get_by_test_id("w0-stopped").inner_text()
    finally:
        browser.close()
