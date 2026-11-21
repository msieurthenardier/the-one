"""``App.router.onRouteChange`` and ``describeCurrent`` (M36 F3 L2, AC3).

The router's own contract tests use literal hashes (the migration guard exempts
``tests/browser/test_router_*.py``). Covers: one notification per commit, at the end of the
commit (after the area's hydrate); one per successful sync and none for a dropped sync; the
``{route, destination, parts}`` shape equal to the announcer's parts; the unsubscribe; a throwing
subscriber that breaks neither a commit nor a sync; and a cold item route whose store loads
afterwards (``describeCurrent`` then names the item).
"""

from __future__ import annotations

import pytest
from browser import _chats
from browser.seeders import SeededApp, seed_mcp_source
from playwright.sync_api import Page

pytestmark = pytest.mark.browser

_RECORD_JS = """() => {
  window.__rc = [];
  window.__rcUnsub = App.router.onRouteChange((info) => {
    window.__rc.push({
      info: info,
      // Read inside the subscriber: has the area mounted its panel by now?
      panel: !!document.querySelector('.content-panel.active[data-destination]'),
    });
  });
  return true;
}"""


def _boot(page: Page, base: str, hash_: str = "") -> None:
    _chats.gleepglorp_off(base)
    page.goto(base + "/" + hash_)
    page.wait_for_function("() => !!(window.App && App.router && App.router.current())")
    page.wait_for_function(
        "() => !!document.querySelector('.content-panel.active[data-destination]')"
    )


def _calls(page: Page) -> list[dict]:
    return page.evaluate("() => window.__rc")


def test_a_commit_notifies_once_after_the_area_mounted(
    app_with_agent: SeededApp, page: Page
) -> None:
    _boot(page, app_with_agent.base_url, "#settings/appearance")
    page.evaluate(_RECORD_JS)
    page.evaluate("() => App.router.go('library')")
    page.wait_for_function("() => window.__rc.length >= 1")
    page.wait_for_timeout(300)
    calls = _calls(page)
    assert len(calls) == 1, calls
    assert calls[0]["info"] == {"route": "library", "destination": "library", "parts": ["Library"]}
    assert calls[0]["panel"] is True  # the area had mounted: end of commit, not applyShell
    # The same shape on demand, for the current route.
    assert page.evaluate("() => App.router.describeCurrent()") == calls[0]["info"]


def test_parts_equal_what_the_announcer_speaks(app_with_agent: SeededApp, page: Page) -> None:
    _boot(page, app_with_agent.base_url, "#library")
    page.evaluate(_RECORD_JS)
    page.evaluate("() => App.router.go('library/mcp/~new')")
    page.wait_for_function("() => window.__rc.length >= 1")
    page.wait_for_timeout(300)
    info = _calls(page)[-1]["info"]
    assert info["destination"] == "library"
    assert info["parts"] == ["Library", "MCP servers", "New"]
    spoken = page.evaluate(
        "() => document.querySelector('[data-testid=route-announcer]').textContent"
    )
    assert spoken == " — ".join(info["parts"])


def test_a_successful_sync_notifies_once_and_a_dropped_sync_does_not(
    app_with_agent: SeededApp, page: Page
) -> None:
    _boot(page, app_with_agent.base_url, "#library/mcp/~new")
    page.evaluate(_RECORD_JS)
    page.wait_for_timeout(300)
    before = len(_calls(page))
    # A successful sync (a save-create canonicalising to the new item), with a name hint.
    ok = page.evaluate(
        "() => App.router.sync('studio', 'mcp-sources/abc123', {name: 'Hinted server'})"
    )
    assert ok is True
    calls = _calls(page)
    assert len(calls) == before + 1
    assert calls[-1]["info"]["route"] == "library/mcp/abc123"
    assert calls[-1]["info"]["parts"] == ["Library", "MCP servers", "Hinted server"]
    # A dropped sync: another destination than the current one.
    dropped = page.evaluate("() => App.router.sync('admin', 'general')")
    assert dropped is False
    assert len(_calls(page)) == before + 1


def test_unsubscribe_and_a_throwing_subscriber(app_with_agent: SeededApp, page: Page) -> None:
    _boot(page, app_with_agent.base_url, "#settings/appearance")
    page.evaluate(
        """() => {
          window.__bad = 0;
          App.router.onRouteChange(() => { window.__bad += 1; throw new Error('subscriber'); });
        }"""
    )
    page.evaluate(_RECORD_JS)
    page.evaluate("() => App.router.go('library')")
    page.wait_for_function("() => window.__rc.length >= 1")
    page.wait_for_timeout(300)
    # The throwing subscriber ran and the commit still completed (the later subscriber ran).
    assert page.evaluate("() => window.__bad") >= 1
    assert len(_calls(page)) == 1
    page.evaluate("() => window.__rcUnsub()")
    page.evaluate("() => App.router.go('settings/appearance')")
    page.wait_for_function("() => App.router.current().route === 'settings/appearance'")
    page.wait_for_timeout(300)
    assert len(_calls(page)) == 1  # unsubscribed: no further call


def test_a_throwing_hydrate_does_not_silence_later_notifications(
    app_with_agent: SeededApp, page: Page
) -> None:
    _boot(page, app_with_agent.base_url, "#library")
    page.evaluate(_RECORD_JS)
    # The Settings area's hydrate calls toolsPage.parseSub for a non-empty sub: make it throw once.
    page.evaluate(
        """() => {
          const orig = App.admin.toolsPage.parseSub;
          let thrown = false;
          App.admin.toolsPage.parseSub = function () {
            if (!thrown) {
              thrown = true;
              window.__thrown = true;
              throw new Error('hydrate failed');
            }
            return orig.apply(this, arguments);
          };
          window.__threw = false;
          try { App.router.go('settings/appearance'); } catch (e) { window.__threw = true; }
        }"""
    )
    page.wait_for_timeout(300)
    assert page.evaluate("() => window.__thrown") is True  # the hydrate did throw
    n = len(_calls(page))
    # A sync right after the failed commit still notifies (the flag was not left set): a later
    # successful commit would reset it, so this is checked before any further navigation.
    assert page.evaluate("() => App.router.sync('admin', 'knowledge')") is True
    assert len(_calls(page)) == n + 1
    # And a later navigation notifies too.
    page.evaluate("() => App.router.go('library')")
    page.wait_for_function(f"() => window.__rc.length > {n + 1}")
    assert _calls(page)[-1]["info"]["destination"] == "library"


def test_a_cold_item_route_is_named_once_its_store_loads(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    _chats.gleepglorp_off(base)
    mcp_id = seed_mcp_source(base, "Cold server")
    held: list = []
    page.route("**/api/mcp-sources", lambda route: held.append(route))
    page.goto(base + f"/#library/mcp/{mcp_id}")
    page.wait_for_function("() => !!(window.App && App.router && App.router.current())")
    # The list request is held, so the store is cold: the type noun stands in for the name.
    page.wait_for_function("() => App.router.describeCurrent().parts.length === 3")
    assert page.evaluate("() => App.router.describeCurrent().parts") == [
        "Library",
        "MCP servers",
        "MCP server",
    ]
    page.evaluate(
        "() => { window.__loaded = false;"
        " App.store.subscribe('mcp-sources', () => { window.__loaded = true; }); }"
    )
    # Removing the handler lets the held requests through (Playwright continues them).
    page.unroute("**/api/mcp-sources")
    page.wait_for_function("() => window.__loaded === true", timeout=8000)
    assert page.evaluate("() => App.router.describeCurrent().parts") == [
        "Library",
        "MCP servers",
        "Cold server",
    ]
