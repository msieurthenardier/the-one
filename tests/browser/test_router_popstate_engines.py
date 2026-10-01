"""Engine proof for the router's traversal authority (M25 F2 L3, AC1 / DD4).

The router treats ``popstate`` as the single authoritative traversal event and
de-duplicates the ``hashchange`` that follows it.  That is only sound if every
engine the app ships in fires ``popstate`` for the three ways the URL can move
without a page load:

* browser Back/Forward across entries;
* a fragment-only ``page.goto(sameURL#x)`` (what a typed hash does);
* an ``<a href="#...">`` click that slipped past interception.

This runs in Chromium and WebKit on a ``page.route``-fulfilled synthetic http
origin (a real document with a real history, unlike the ``about:blank`` disk
harness).  If WebKit fails one of these the flight diverts to ``hashchange`` as
the authority (flight.md "Divert if").
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page

pytestmark = pytest.mark.browser

ORIGIN = "http://router-proof.test"
PAGE_URL = ORIGIN + "/page"

_HTML = """<!doctype html><html><head><title>router proof</title></head><body>
<a id="lnk" href="#clicked">link</a>
<script>
window.__ev = [];
window.addEventListener('popstate', function (e) {
  window.__ev.push({ type: 'popstate', hash: location.hash, state: e.state });
});
window.addEventListener('hashchange', function () {
  window.__ev.push({ type: 'hashchange', hash: location.hash });
});
</script></body></html>"""


def _open(page: Page) -> None:
    page.route(
        ORIGIN + "/**",
        lambda route: route.fulfill(status=200, content_type="text/html", body=_HTML),
    )
    page.goto(PAGE_URL)
    page.wait_for_function("Array.isArray(window.__ev)")


def _events(page: Page) -> list[dict]:
    return page.evaluate("window.__ev")


def _wait_for(page: Page, n: int) -> list[dict]:
    page.wait_for_function("n => window.__ev.length >= n", arg=n, timeout=5000)
    # Let a trailing hashchange land (it is queued as a later task).
    page.wait_for_timeout(150)
    return _events(page)


def _types(events: list[dict]) -> list[str]:
    return [e["type"] for e in events]


def test_popstate_fires_on_back_and_forward(engine_page: Page) -> None:
    page = engine_page
    _open(page)
    page.evaluate(
        """() => {
            history.replaceState({ seq: 1 }, '', '#a');
            history.pushState({ seq: 2 }, '', '#b');
            window.__ev.length = 0;
        }"""
    )
    page.go_back()
    ev = _wait_for(page, 1)
    pops = [e for e in ev if e["type"] == "popstate"]
    assert pops, f"no popstate on Back: {ev}"
    assert pops[0]["hash"] == "#a" and pops[0]["state"] == {"seq": 1}, ev
    # Authority order: popstate is dispatched before its hashchange.
    assert _types(ev)[0] == "popstate", ev

    page.evaluate("window.__ev.length = 0")
    page.go_forward()
    ev = _wait_for(page, 1)
    pops = [e for e in ev if e["type"] == "popstate"]
    assert pops, f"no popstate on Forward: {ev}"
    assert pops[0]["hash"] == "#b" and pops[0]["state"] == {"seq": 2}, ev
    assert _types(ev)[0] == "popstate", ev


def test_popstate_fires_on_fragment_only_goto(engine_page: Page) -> None:
    page = engine_page
    _open(page)
    page.evaluate("window.__ev.length = 0")
    page.goto(PAGE_URL + "#typed")
    ev = _wait_for(page, 1)
    # Same document (no reload): the listeners and the log survived.
    assert any(e["type"] == "popstate" and e["hash"] == "#typed" for e in ev), (
        f"fragment-only goto fired no popstate: {ev}"
    )
    assert _types(ev)[0] == "popstate", ev
    assert page.evaluate("history.state") is None  # a typed URL has a null state


def test_popstate_fires_on_anchor_click(engine_page: Page) -> None:
    page = engine_page
    _open(page)
    page.evaluate("window.__ev.length = 0")
    page.click("#lnk")
    ev = _wait_for(page, 1)
    pops = [e for e in ev if e["type"] == "popstate"]
    assert pops and pops[0]["hash"] == "#clicked", f"anchor click fired no popstate: {ev}"
    assert pops[0]["state"] is None, ev  # link clicks traverse with a null state
    assert _types(ev)[0] == "popstate", ev
