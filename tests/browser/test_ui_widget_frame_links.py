# ruff: noqa: E501  (inline widget sources are evaluated verbatim)
"""DD6 layered link blocking (M35 F2 L3, AC2): a preconnect link in a widget's head must never open
a connection. WebKit opens a bare TCP connection for ``<link rel=preconnect>`` and the frame's
policy does not stop it, so ``buildDocument`` rewrites link tags in the source and the prelude
rewrites every in-frame HTML entry point. One test per route, in both engines; each reads the sink
(HTTP, UDP, TCP accepts all 0) and checks that no ``HTMLLinkElement`` is left in the frame.
"""

from __future__ import annotations

import json

import pytest
from browser._widget_harness import engine, frame, load, mount
from browser._widget_sink import WidgetSink, escape_fixture
from playwright.sync_api import Page

pytestmark = pytest.mark.browser

# Routes handled by the fixture's `link-<route>` mode (built at run time, so the page's source
# rewrite does not touch them: these exercise the prelude).
FIXTURE_ROUTES = [
    "createElement",
    "createElementNS",
    "createElementNS-prefixed",
    "innerHTML",
    "outerHTML",
    "shadow-innerHTML",
    "insertAdjacentHTML",
    "domparser-html-adopt",
    "domparser-xml-import",
    "createHTMLDocument-adopt",
    "createContextualFragment",
    "template-content",
    "setHTMLUnsafe",
]


# Routes that must run while the parser is still in the head: a literal tag in the source (the
# source rewrite) and document.write, whole and split across calls (the prelude's carry-over).
def _parse_time_sources(url: str) -> dict[str, str]:
    return {
        "parser": f'<link rel="preconnect" href="{url}"><p>x</p>',
        "parser-uppercase": f'<LINK rel="preconnect" href="{url}"><p>x</p>',
        "parser-slash-terminated": f'<link/rel="preconnect"/href="{url}"><p>x</p>',
        "document-write": f"<script>document.write('<' + 'link rel=\"preconnect\" href=\"{url}\">')</script><p>x</p>",
        "document-write-split": f"<script>document.write('<li'); document.write('nk rel=\"preconnect\" href=\"{url}\">')</script><p>x</p>",
        "document-write-split-three": f"<script>document.write('<'); document.write('LIN'); document.write('K rel=preconnect href={url}>')</script><p>x</p>",
    }


@pytest.fixture(scope="module")
def sink():
    s = WidgetSink()
    try:
        yield s
    finally:
        s.close()


def _settle(page: Page, sink: WidgetSink, route: str) -> dict:
    page.wait_for_function("() => __h.loads() >= 1")
    page.wait_for_timeout(1600)
    counts = sink.counts()
    print(f"[widget-links] {engine(page)} {route}: {json.dumps(counts)}")
    return counts


def _assert_zero(counts: dict) -> None:
    assert counts["http"] == 0, counts
    assert counts["udp"] == 0, counts
    assert counts["tcp"] == 0, counts


@pytest.mark.parametrize("route", FIXTURE_ROUTES)
def test_link_route_opens_no_connection(engine_page: Page, sink: WidgetSink, route: str) -> None:
    load(engine_page, sink)
    mount(engine_page, sink.fill(escape_fixture(), f"link-{route}"))
    frame(engine_page).wait_for_function("() => window.__done === true", timeout=10000)
    counts = _settle(engine_page, sink, route)
    _assert_zero(counts)
    assert frame(engine_page).evaluate("() => window.__links") == 0
    grid = frame(engine_page).evaluate("() => window.__grid")
    if route != "setHTMLUnsafe":
        assert grid["link"]["status"] == "attempted", grid
    assert engine_page.evaluate("() => [__h.loads(), __esc]") == [1, 0]


@pytest.mark.parametrize(
    "route",
    [
        "parser",
        "parser-uppercase",
        "parser-slash-terminated",
        "document-write",
        "document-write-split",
        "document-write-split-three",
    ],
)
def test_parse_time_link_opens_no_connection(
    engine_page: Page, sink: WidgetSink, route: str
) -> None:
    load(engine_page, sink)
    mount(engine_page, _parse_time_sources(f"http://127.0.0.1:{sink.tcp_port}/")[route])
    counts = _settle(engine_page, sink, route)
    _assert_zero(counts)
    assert frame(engine_page).evaluate("() => document.querySelectorAll('link').length") == 0
    assert frame(engine_page).evaluate("() => document.getElementsByTagName('p').length") == 1


def test_document_write_is_a_no_op_after_the_document_loaded(
    engine_page: Page, sink: WidgetSink
) -> None:
    """Edge case: a write after DOMContentLoaded would replace the document (and its prelude), so
    it does nothing; open() does nothing either."""
    load(engine_page, sink)
    mount(
        engine_page,
        "<p id=keep>kept</p><script>window.addEventListener('load', function () {"
        "setTimeout(function () { document.open(); document.write('<p id=gone>x</p>'); document.close(); window.__done = true; }, 50); });</script>",
    )
    frame(engine_page).wait_for_function("() => window.__done === true", timeout=10000)
    res = frame(engine_page).evaluate(
        "() => [!!document.getElementById('keep'), !!document.getElementById('gone')]"
    )
    assert res == [True, False]
    assert engine_page.evaluate("() => [__h.loads(), __esc]") == [1, 0]


def test_a_harmless_held_back_fragment_is_flushed(engine_page: Page, sink: WidgetSink) -> None:
    """The carry-over holds a trailing `<li` and flushes it with the next call: a list item, not
    a link, written across two calls still reaches the document."""
    load(engine_page, sink)
    mount(
        engine_page,
        "<ul id=u><script>document.write('<li'); document.write('>one</li><li>two</li>');</script></ul>",
    )
    assert frame(engine_page).evaluate(
        "() => Array.prototype.map.call(document.querySelectorAll('#u li'), function (l) { return l.textContent; })"
    ) == ["one", "two"]


def test_the_inert_element_names_are_what_the_prelude_promises(
    engine_page: Page, sink: WidgetSink
) -> None:
    load(engine_page, sink)
    mount(
        engine_page,
        "<script>window.__r = {"
        "a: document.createElement('LINK').localName,"
        "b: document.createElementNS('http://www.w3.org/1999/xhtml', 'link').localName,"
        "c: document.createElement('div').localName,"
        "d: document.implementation.createHTMLDocument('').createElement('link').localName,"
        "e: document.createElement('div').outerHTML,"
        "f: (function () { var d = document.createElement('div'); d.innerHTML = '<' + 'link rel=x>'; return d.innerHTML; })(),"
        "g: (function () { var d = document.createElement('div'); d.innerHTML = null; return d.innerHTML; })()"
        "}; window.__done = true;</script>",
    )
    frame(engine_page).wait_for_function("() => window.__done === true", timeout=10000)
    r = frame(engine_page).evaluate("() => window.__r")
    assert r["a"] == "x-link" and r["b"] == "x-link" and r["d"] == "x-link", r
    assert r["c"] == "div" and r["e"] == "<div></div>"
    assert r["f"].startswith("<x-link"), r
    assert r["g"] == "", r


def test_hostile_replacements_cannot_lift_the_link_wrappers(
    engine_page: Page, sink: WidgetSink
) -> None:
    """The wrapped entry points are non-configurable and non-writable: delete and redefine fail,
    and a stringifying object is read once, so it cannot show one string to the check and another
    to the parser."""
    load(engine_page, sink)
    mount(
        engine_page,
        "<script>(function () {"
        "var r = {};"
        "try { delete Document.prototype.createElement; } catch (e) {}"
        "try { Object.defineProperty(Document.prototype, 'createElement', {value: function () { return 1; }}); } catch (e) {}"
        "try { Object.defineProperty(Element.prototype, 'innerHTML', {set: function () {}}); } catch (e) {}"
        "r.ce = document.createElement('link').localName;"
        "var n = 0, d = document.createElement('div');"
        "d.innerHTML = {toString: function () { n++; return n === 1 ? 'a' : '<' + 'link rel=x>'; }};"
        "r.inner = d.innerHTML; r.calls = n;"
        "window.__r = r; window.__done = true;"
        "})();</script>",
    )
    frame(engine_page).wait_for_function("() => window.__done === true", timeout=10000)
    r = frame(engine_page).evaluate("() => window.__r")
    assert r["ce"] == "x-link", r
    assert r["inner"] == "a" and r["calls"] == 1, r
