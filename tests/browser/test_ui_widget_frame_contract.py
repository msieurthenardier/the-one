# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for ``App.ui.widgetFrame`` (M35 F2 L1, flight DD2-DD6, DD17):
the sandboxed ``srcdoc`` frame core, its pinned prelude, the size channel, the theme variables and
the escape battery. Chromium (headless shell) and WebKit through ``engine_page`` + ``load_harness``
at a real http URL whose response carries the app's own ``FRAME_POLICY`` header (served by the
sink), so the page policy under test is the production constant. Falls in ``contracts-widget``
(its focus, link and pause companions are ``test_ui_widget_frame_focus`` / ``_links`` / ``_pause``).

The sink (``_widget_sink.WidgetSink``) counts HTTP requests, UDP datagrams and TCP accepts that a
widget manages to send out. Every engine must read 0 for all three (DD6 layered link blocking
closed the WebKit ``preconnect`` result; there is no allow-list entry).
"""

from __future__ import annotations

import json

import pytest
from browser._widget_harness import INITIAL_HEIGHT
from browser._widget_harness import engine as _engine
from browser._widget_harness import frame as _frame
from browser._widget_harness import load as _load
from browser._widget_harness import mount as _mount
from browser._widget_sink import WidgetSink, escape_fixture
from playwright.sync_api import Page

pytestmark = pytest.mark.browser


@pytest.fixture(scope="module")
def sink():
    s = WidgetSink()
    try:
        yield s
    finally:
        s.close()


def assert_sink_clean(page: Page, sink: WidgetSink, label: str) -> None:
    counts = sink.counts()
    print(f"[widget-sink] {_engine(page)} {label}: {json.dumps(counts)}")
    assert counts["http"] == 0, counts
    assert counts["udp"] == 0, counts
    assert counts["tcp"] == 0, counts


def _wait_done(page: Page) -> None:
    page.wait_for_function("() => __h.loads() >= 1")
    _frame(page).wait_for_function("() => window.__done === true", timeout=10000)


# ── AC2: attributes and order ──────────────────────────────────────────────────


def test_frame_attributes_and_single_load(engine_page: Page, sink: WidgetSink) -> None:
    _load(engine_page, sink)
    # Read at creation: the frame's first size message later replaces the initial height.
    attrs = engine_page.evaluate(
        """() => { const f = __mount('<p id=x>hello</p>').iframe; return {
          sandbox: f.getAttribute('sandbox'), ref: f.getAttribute('referrerpolicy'),
          allow: f.getAttribute('allow'), title: f.getAttribute('title'),
          hasSrcdoc: f.hasAttribute('srcdoc'), height: f.style.height, tag: f.tagName,
          keys: Object.keys(__h).sort(),
        }; }"""
    )
    assert attrs["tag"] == "IFRAME"
    assert attrs["sandbox"] == "allow-scripts"
    assert attrs["ref"] == "no-referrer"
    assert attrs["allow"] == ""
    assert attrs["title"] == "Test widget"
    assert attrs["height"] == f"{INITIAL_HEIGHT}px"
    assert {"iframe", "destroy", "postTheme", "postPause", "postResume", "loads"} <= set(
        attrs["keys"]
    )
    engine_page.wait_for_function("() => __h.loads() >= 1")
    engine_page.wait_for_timeout(1500)
    assert engine_page.evaluate("() => __h.loads()") == 1
    assert engine_page.evaluate("() => __esc") == 0
    assert _frame(engine_page).evaluate("() => document.getElementById('x').textContent") == "hello"


def test_the_frame_is_inserted_sandboxed_then_srcdoc_is_assigned(
    engine_page: Page, sink: WidgetSink
) -> None:
    """Amended DD2 (HAT step 9): the frame is inserted first (already sandboxed, no srcdoc yet) so
    the parent lays it out, and only then is the document assigned; the initial about:blank load
    at insertion is not counted, so the srcdoc load is the one counted load and no escape fires.
    The document carries the prelude and policy before any model byte."""
    _load(engine_page, sink)
    res = engine_page.evaluate(
        """() => {
          const log = [];
          const slot = document.createElement('div');
          document.getElementById('harness-root').appendChild(slot);
          const orig = slot.appendChild.bind(slot);
          slot.appendChild = (n) => { log.push('append:' + n.getAttribute('sandbox') + ':' + (n.hasAttribute('srcdoc') ? 'has-srcdoc' : 'no-srcdoc')); return orig(n); };
          window.__esc2 = 0;
          const h = App.ui.widgetFrame({slot, source: '<i>m</i>', title: 't', onEscape: () => window.__esc2++});
          window.__h2 = h;
          const doc = h.iframe.getAttribute('srcdoc');
          return {log, startsDoctype: doc.indexOf('<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy"') === 0,
                  modelAfterPrelude: doc.lastIndexOf('</script>') < doc.indexOf('<i>m</i>')};
        }"""
    )
    assert res["log"] == ["append:allow-scripts:no-srcdoc"]
    assert res["startsDoctype"] and res["modelAfterPrelude"]
    engine_page.wait_for_function("() => __h2.loads() >= 1")
    engine_page.wait_for_timeout(1000)
    assert engine_page.evaluate("() => [__h2.loads(), __esc2, document.querySelectorAll('iframe').length]") == [1, 0, 1]


def test_a_detached_slot_loads_only_once_attached(engine_page: Page, sink: WidgetSink) -> None:
    _load(engine_page, sink)
    engine_page.evaluate(
        """() => {
          const slot = document.createElement('div');
          window.__slot = slot;
          window.__h = App.ui.widgetFrame({slot, source: '<p>late</p>', title: 't', onEscape: () => window.__esc++});
        }"""
    )
    engine_page.wait_for_timeout(300)
    assert engine_page.evaluate("() => __h.loads()") == 0
    engine_page.evaluate("() => document.getElementById('harness-root').appendChild(__slot)")
    engine_page.wait_for_function("() => __h.loads() === 1")
    engine_page.wait_for_timeout(500)
    assert engine_page.evaluate("() => [__h.loads(), __esc]") == [1, 0]


def test_destroy_is_idempotent_and_the_listener_pairs(engine_page: Page, sink: WidgetSink) -> None:
    """The window message listener is installed once while a frame exists and removed with the
    last one (AC9)."""
    _load(engine_page, sink)
    res = engine_page.evaluate(
        """() => {
          const adds = [], removes = [];
          const a = window.addEventListener.bind(window), r = window.removeEventListener.bind(window);
          window.addEventListener = (t, f, o) => { if (t === 'message') adds.push(1); return a(t, f, o); };
          window.removeEventListener = (t, f, o) => { if (t === 'message') removes.push(1); return r(t, f, o); };
          const mk = () => { const s = document.createElement('div'); document.getElementById('harness-root').appendChild(s); return App.ui.widgetFrame({slot: s, source: 'x', title: 't'}); };
          const h1 = mk(), h2 = mk();
          const mid = [adds.length, removes.length];
          h1.destroy(); h1.destroy();
          const afterOne = [adds.length, removes.length];
          h2.destroy(); h2.destroy();
          const end = [adds.length, removes.length];
          const h3 = mk(); h3.destroy();
          window.addEventListener = a; window.removeEventListener = r;
          return {mid, afterOne, end, again: [adds.length, removes.length], frames: document.querySelectorAll('iframe').length};
        }"""
    )
    assert res["mid"] == [1, 0]
    assert res["afterOne"] == [1, 0]
    assert res["end"] == [1, 1]
    assert res["again"] == [2, 2]
    assert res["frames"] == 0


# ── AC3: neutering ─────────────────────────────────────────────────────────────

NEUTER_SRC = """<script>
window.__checks = {};
function tryDelete(o, n) { try { delete o[n]; } catch (e) {} }
function tryDef(o, n, v) { try { Object.defineProperty(o, n, {value: v, configurable: true, writable: true}); } catch (e) {} }
['RTCPeerConnection', 'webkitRTCPeerConnection', 'RTCDataChannel'].forEach(function (n) {
  tryDelete(window, n); tryDef(window, n, function () {});
  window.__checks[n] = (window[n] === undefined);
});
window.__checks['constructor.RTCPeerConnection'] = (window.constructor.RTCPeerConnection === undefined);
['back', 'forward', 'go', 'pushState', 'replaceState'].forEach(function (n) {
  var orig = Object.getOwnPropertyDescriptor(History.prototype, n);
  tryDelete(History.prototype, n); tryDef(History.prototype, n, function () { return 'widget'; });
  var d = Object.getOwnPropertyDescriptor(History.prototype, n);
  window.__checks['History.' + n] = !!d && d.value === orig.value && d.writable === false && d.configurable === false && history[n]() === undefined;
});
tryDelete(Document.prototype, 'execCommand'); tryDef(Document.prototype, 'execCommand', function () { return true; });
window.__checks['execCommand'] = (document.execCommand('copy') === false);
window.__done = true;
</script>"""


def test_neutered_names_hold_after_delete_and_define(engine_page: Page, sink: WidgetSink) -> None:
    _load(engine_page, sink)
    _mount(engine_page, NEUTER_SRC)
    _frame(engine_page).wait_for_function("() => window.__done === true")
    checks = _frame(engine_page).evaluate("() => window.__checks")
    assert checks, "no checks ran"
    assert all(checks.values()), checks
    assert len(checks) == 10, checks
    assert engine_page.evaluate("() => [location.href === __url0, __pop]") == [True, 0]


# ── AC4: the size channel ──────────────────────────────────────────────────────


def _height(page: Page) -> int:
    return int(page.evaluate("() => parseInt(__h.iframe.style.height, 10)"))


def test_size_follows_content_clamped_to_48_720(engine_page: Page, sink: WidgetSink) -> None:
    _load(engine_page, sink)
    _mount(engine_page, "<div id=d style='height:120px'></div>")
    engine_page.wait_for_function("() => __h.iframe.style.height === '120px'")
    frame = _frame(engine_page)
    frame.evaluate("() => { document.getElementById('d').style.height = '3000px'; }")
    engine_page.wait_for_function("() => __h.iframe.style.height === '720px'")
    frame.evaluate("() => { document.getElementById('d').style.height = '6px'; }")
    engine_page.wait_for_function("() => __h.iframe.style.height === '48px'")
    assert engine_page.evaluate("() => __sizes") == [120, 720, 48]


def test_heartbeat_survives_a_widget_clearing_every_timer(
    engine_page: Page, sink: WidgetSink
) -> None:
    _load(engine_page, sink)
    _mount(
        engine_page,
        "<script>for (var i = 0; i <= 10000; i++) { clearInterval(i); clearTimeout(i); }"
        "window.__cleared = true;</script>",
    )
    _frame(engine_page).wait_for_function("() => window.__cleared === true")
    engine_page.wait_for_function("() => __beats >= 1")
    before = engine_page.evaluate("() => __beats")
    engine_page.wait_for_function(f"() => __beats >= {before + 2}", timeout=6000)


def test_forged_and_malformed_messages_are_ignored(engine_page: Page, sink: WidgetSink) -> None:
    """The page matches by event.source against live frames only: a message from the page itself,
    from a second unrelated frame, of the wrong shape, or with a non-finite h changes nothing."""
    _load(engine_page, sink)
    _mount(engine_page, "<div style='height:150px'></div>")
    engine_page.wait_for_function("() => __h.iframe.style.height === '150px'")
    engine_page.evaluate("() => { window.__beats = 0; window.__sizes.length = 0; }")
    # 1. from the page itself
    engine_page.evaluate(
        "() => { window.postMessage({t: 'size', h: 600}, '*'); window.postMessage({t: 'size', h: 61}, '*'); }"
    )
    # 2. from a second, unrelated sandboxed frame (its origin is "null" like every widget's)
    engine_page.evaluate(
        """() => {
          const other = document.createElement('iframe');
          other.setAttribute('sandbox', 'allow-scripts');
          other.srcdoc = '<script>parent.postMessage({t:"size",h:600},"*");parent.postMessage({t:"size",h:61},"*")<\\/script>';
          document.body.appendChild(other);
          window.__other = other;
        }"""
    )
    engine_page.wait_for_function("() => __other.contentWindow && true")
    engine_page.wait_for_timeout(600)
    # 3. wrong shapes and non-finite heights, from the real frame
    _frame(engine_page).evaluate(
        """() => {
          [null, 5, 'size', {t: 'size'}, {t: 'size', h: '300'}, {t: 'size', h: NaN}, {t: 'size', h: Infinity},
           {t: 'size', h: -Infinity}, {t: 'other', h: 400}, {h: 400}, [], {t: 'size', h: null}].forEach(function (m) { parent.postMessage(m, '*'); });
        }"""
    )
    engine_page.wait_for_timeout(500)
    sizes = engine_page.evaluate("() => __sizes")
    assert 600 not in sizes and 61 not in sizes and 300 not in sizes and 400 not in sizes, sizes
    assert _height(engine_page) == 150
    engine_page.evaluate("() => __other.remove()")


def test_a_flood_causes_at_most_one_height_write_per_frame(
    engine_page: Page, sink: WidgetSink
) -> None:
    _load(engine_page, sink)
    _mount(engine_page, "<div style='height:100px'></div>")
    engine_page.wait_for_function("() => __h.iframe.style.height === '100px'")
    engine_page.evaluate(
        """() => {
          window.__writes = 0; window.__ticks = 0;
          new MutationObserver((rs) => { window.__writes += rs.length; }).observe(__h.iframe, {attributes: true, attributeFilter: ['style']});
          (function tick() { window.__ticks++; window.__raf = requestAnimationFrame(tick); })();
        }"""
    )
    _frame(engine_page).evaluate(
        """() => { for (var i = 0; i < 1000; i++) { parent.postMessage({t: 'size', h: 50 + (i % 600)}, '*'); } window.__sent = true; }"""
    )
    engine_page.wait_for_timeout(1000)
    res = engine_page.evaluate(
        "() => { cancelAnimationFrame(__raf); return {writes: __writes, ticks: __ticks}; }"
    )
    print(f"[widget-flood] {_engine(engine_page)} {res}")
    assert 1 <= res["writes"] <= res["ticks"], res
    assert res["writes"] < 100, res


# ── AC5: theme ─────────────────────────────────────────────────────────────────

THEME_KEYS = ["--bg", "--surface", "--fg", "--fg-muted", "--border", "--accent", "--danger"] + [
    f"--chart-{i}" for i in range(1, 9)
]


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_mount_defines_literal_theme_variables(
    engine_page: Page, sink: WidgetSink, theme: str
) -> None:
    _load(engine_page, sink, theme=theme)
    _mount(engine_page, "<p>t</p>")
    page_vals = engine_page.evaluate(
        """(keys) => { const cs = getComputedStyle(document.getElementById('harness-root')); const o = {};
          keys.forEach((k) => { o[k] = cs.getPropertyValue(k === '--danger' ? '--status-danger' : k).trim(); }); return o; }""",
        THEME_KEYS,
    )
    assert all(page_vals.values()), page_vals
    frame_vals = _frame(engine_page).evaluate(
        """(keys) => { const cs = getComputedStyle(document.documentElement); const o = {};
          keys.forEach((k) => { o[k] = cs.getPropertyValue(k).trim(); });
          o.mode = document.documentElement.getAttribute('data-theme'); o.scheme = cs.colorScheme; return o; }""",
        THEME_KEYS,
    )
    for k in THEME_KEYS:
        assert frame_vals[k].lower() == page_vals[k].lower(), (k, frame_vals[k], page_vals[k])
        assert "var(" not in frame_vals[k]
    assert frame_vals["mode"] == theme
    assert theme in frame_vals["scheme"]


def test_post_theme_updates_variables_and_fires_themechange(
    engine_page: Page, sink: WidgetSink
) -> None:
    _load(engine_page, sink, theme="dark")
    _mount(
        engine_page,
        "<script>window.__tc = 0; addEventListener('themechange', function () { __tc++; });</script>",
    )
    engine_page.evaluate(
        "() => __h.postTheme({vars: {'--bg': '#123456', '--accent': 'rgb(1, 2, 3)', 'bad': 'x', '--x y': 'z'}, mode: 'light'})"
    )
    frame = _frame(engine_page)
    frame.wait_for_function("() => window.__tc === 1")
    res = frame.evaluate(
        "() => ({bg: document.documentElement.style.getPropertyValue('--bg'), accent: document.documentElement.style.getPropertyValue('--accent'), mode: document.documentElement.getAttribute('data-theme'), scheme: document.documentElement.style.colorScheme, tc: __tc})"
    )
    assert res == {
        "bg": "#123456",
        "accent": "rgb(1, 2, 3)",
        "mode": "light",
        "scheme": "light",
        "tc": 1,
    }


def test_theme_pushed_before_load_is_applied_at_load(engine_page: Page, sink: WidgetSink) -> None:
    _load(engine_page, sink, theme="dark")
    engine_page.evaluate(
        "() => { __mount('<p>t</p>'); __h.postTheme({vars: {'--bg': '#abcdef'}, mode: 'light'}); }"
    )
    engine_page.wait_for_function("() => __h.loads() === 1")
    _frame(engine_page).wait_for_function(
        "() => document.documentElement.style.getPropertyValue('--bg') === '#abcdef'"
    )


def test_a_root_theme_change_is_pushed_to_every_live_frame(
    engine_page: Page, sink: WidgetSink
) -> None:
    _load(engine_page, sink)
    engine_page.evaluate(
        """() => {
          document.documentElement.setAttribute('data-theme', 'dark');
          const slot = document.createElement('div');
          document.body.appendChild(slot);
          window.__h = App.ui.widgetFrame({slot, source: '<script>window.__tc = 0; addEventListener("themechange", function () { __tc++; });<\\/script>', title: 't'});
        }"""
    )
    engine_page.wait_for_function("() => __h.loads() === 1")
    frame = _frame(engine_page)
    dark = frame.evaluate(
        "() => getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()"
    )
    engine_page.evaluate("() => document.documentElement.setAttribute('data-theme', 'light')")
    frame.wait_for_function("() => document.documentElement.getAttribute('data-theme') === 'light'")
    light = frame.evaluate(
        "() => getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()"
    )
    assert dark and light and dark != light
    assert frame.evaluate("() => __tc") == 1


# ── AC6: the escape battery ────────────────────────────────────────────────────

BREACH_IDS = [
    "parent-dom", "top-dom", "top-location-read", "top-navigation", "cookie", "local-storage",
    "session-storage", "window-open", "alert", "nested-realm", "webrtc-undefined", "webrtc-stun",
    "exec-command", "neutered-hold",
]  # fmt: skip
ATTEMPTED_IDS = [
    "fetch", "xhr", "image", "beacon", "form-post", "link-prefetch", "css-url", "css-import",
    "data-worker", "blob-worker", "dynamic-import", "preconnect-script", "dns-prefetch",
    "history", "flood",
]  # fmt: skip


def _battery(page: Page, sink: WidgetSink, mode: str):
    dialogs: list[str] = []
    new_pages: list[str] = []
    page.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
    page.context.on("page", lambda p: new_pages.append(p.url))
    _load(page, sink)
    page.evaluate("(doc) => { __mount(doc); }", sink.fill(escape_fixture(), mode))
    return dialogs, new_pages


def test_escape_battery_main(engine_page: Page, sink: WidgetSink) -> None:
    dialogs, new_pages = _battery(engine_page, sink, "main")
    _wait_done(engine_page)
    engine_page.wait_for_timeout(800)
    grid = _frame(engine_page).evaluate("() => window.__grid")
    # (e) every in-frame attempt is refused; network attempts were made (the sink is their verdict)
    for gid in BREACH_IDS:
        assert grid[gid]["status"] == "refused", (gid, grid[gid])
    for gid in ATTEMPTED_IDS:
        assert grid[gid]["status"] in ("attempted", "refused"), (gid, grid[gid])
    assert not [g for g, v in grid.items() if v["status"] == "open"], grid
    # (a) the sink
    assert_sink_clean(engine_page, sink, "main")
    # (b) the page is untouched
    state = engine_page.evaluate(
        "() => ({same: location.href === __url0, hash: location.hash, pop: __pop, loads: __h.loads(), esc: __esc})"
    )
    assert state == {"same": True, "hash": "", "pop": 0, "loads": 1, "esc": 0}, state
    # (c) no dialog, no new page
    assert dialogs == [] and new_pages == []
    # the forged flood stays inside the clamp
    assert _height(engine_page) <= 720


NAV_MODES = ["nav-href", "nav-assign", "nav-replace", "nav-meta", "nav-link", "nav-reload"]


@pytest.mark.parametrize("mode", NAV_MODES)
def test_escape_battery_self_navigation_is_a_second_load(
    engine_page: Page, sink: WidgetSink, mode: str
) -> None:
    """DD3: with srcdoc set before insertion, any load after the first is a navigation attempt.
    The control fires onEscape exactly once and removes the frame; nothing reaches the sink."""
    dialogs, new_pages = _battery(engine_page, sink, mode)
    engine_page.wait_for_function("() => __esc >= 1", timeout=10000)
    engine_page.wait_for_timeout(1200)
    state = engine_page.evaluate(
        "() => ({esc: __esc, loads: __h.loads(), frames: document.querySelectorAll('iframe').length, same: location.href === __url0, hash: location.hash, pop: __pop})"
    )
    print(
        f"[widget-nav] {_engine(engine_page)} {mode}: {state} history.length={engine_page.evaluate('history.length')}"
    )
    assert state == {"esc": 1, "loads": 2, "frames": 0, "same": True, "hash": "", "pop": 0}, state
    assert_sink_clean(engine_page, sink, mode)
    assert dialogs == [] and new_pages == []


# ── Edge cases ─────────────────────────────────────────────────────────────────


def test_a_full_document_source_cannot_loosen_the_policy(
    engine_page: Page, sink: WidgetSink
) -> None:
    hostile = (
        "<!doctype html><html><head><meta http-equiv=\"Content-Security-Policy\" content=\"default-src * 'unsafe-inline' 'unsafe-eval'\">"
        '<base href="http://127.0.0.1:{{HTTP}}/"></head><body><p id=m>full</p>'
        "<script>window.__r = {}; try { fetch('http://127.0.0.1:{{HTTP}}/leak?p=full').then(function () { __r.fetch = 'open'; }, function () { __r.fetch = 'refused'; }); } catch (e) { __r.fetch = 'refused'; }"
        "new Image().src = '/relative-leak.png'; window.__done = true;</script></body></html>"
        "</script><script>1</script>"
    )
    _load(engine_page, sink)
    engine_page.evaluate("(s) => { __mount(s); }", sink.fill(hostile))
    _wait_done(engine_page)
    engine_page.wait_for_timeout(600)
    assert _frame(engine_page).evaluate(
        "() => [document.getElementById('m').textContent, __r.fetch]"
    ) == ["full", "refused"]
    assert engine_page.evaluate("() => [__h.loads(), __esc]") == [1, 0]
    assert_sink_clean(engine_page, sink, "full-document")


def test_nul_and_invalid_surrogates_do_not_crash(engine_page: Page, sink: WidgetSink) -> None:
    _load(engine_page, sink)
    engine_page.evaluate("() => { __mount('<p id=m>a\\u0000b\\ud800c</p>'); }")
    engine_page.wait_for_function("() => __h.loads() === 1")
    engine_page.wait_for_timeout(500)
    assert engine_page.evaluate(
        "() => [__h.loads(), __esc, document.querySelectorAll('iframe').length]"
    ) == [1, 0, 1]
    assert _frame(engine_page).evaluate("() => document.getElementById('m') !== null") is True
