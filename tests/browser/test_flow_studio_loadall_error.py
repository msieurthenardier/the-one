"""Studio `loadAll()` rejection handling (squawk 0014).

`loadAll()` is a `Promise.all` over five fetches (agents, tools, MCP
sources, knowledge bases, providers). Neither call site
(`init()`, `self._refresh`) had a `.catch` — a rejection (network blip,
non-JSON error body) left the area silently blank / stuck, with nothing
shown to the operator. None of the five fetch helpers check `r.ok`, so a
JSON error body does NOT reject `.json()`; only a non-JSON body (the
realistic shape of an unhandled-exception 500 page) or a network failure
does. The stubs below return a plain-text 500 body to reproduce that.

Covers:
- `init()` path: loadAll rejects on first mount — a visible, persistent
  `.admin-loading` error line appears (mirrors the existing per-section
  fetch-failure convention already used elsewhere in studio.js).
- Healthy baseline: with all five routes healthy, the area renders
  normally and no error line appears — regression guard against the fix
  itself misfiring.
- `_refresh` path (triggered by `activate()` on area re-entry): loadAll
  rejects on a SECOND studio mount — a non-destructive `App.showFlash`
  toast appears WITHOUT blanking the already-rendered area (the header +
  "New Agent" button stay visible throughout).
"""

from __future__ import annotations

import pytest
from browser import _nav
from playwright.sync_api import Page, expect


def _fail_knowledge_bases(route) -> None:
    """Return a non-JSON 500 body — the shape that actually makes
    `r.json()` reject (a JSON error body would resolve fine, since none
    of loadAll's five fetch helpers check `r.ok`)."""
    route.fulfill(status=500, content_type="text/plain", body="Internal Server Error")


@pytest.mark.browser
def test_loadall_failure_on_init_shows_visible_error(app_clean: str, page: Page) -> None:
    """A rejected loadAll() on first mount surfaces a visible error line
    instead of leaving the area silently blank."""
    page.route("**/api/knowledge-bases", lambda route: _fail_knowledge_bases(route))

    _nav.goto(page, app_clean, "agents")

    error_line = page.locator(".studio-loadall-error")
    expect(error_line).to_be_visible(timeout=8000)
    expect(error_line).to_contain_text("Unable to load Studio data")
    expect(error_line).to_have_attribute("role", "alert")


@pytest.mark.browser
def test_loadall_healthy_renders_normally(app_clean: str, page: Page) -> None:
    """Baseline: with all routes healthy, the area renders as normal and
    the new error line never appears."""
    _nav.goto(page, app_clean, "agents")

    expect(page.locator('[data-testid="new-agent-btn"]')).to_be_visible(timeout=8000)
    expect(page.locator(".studio-loadall-error")).to_have_count(0)
    expect(page.locator(".app-flash.error")).to_have_count(0)


@pytest.mark.browser
def test_refresh_failure_shows_error_without_blanking_content(app_clean: str, page: Page) -> None:
    """A rejected loadAll() from `_refresh` (area re-entry via activate())
    shows a non-destructive error and does NOT blank the already-rendered
    area."""
    # 1. Healthy first mount.
    _nav.goto(page, app_clean, "agents")
    new_agent_btn = page.locator('[data-testid="new-agent-btn"]')
    expect(new_agent_btn).to_be_visible(timeout=8000)

    # 2. Stub the next knowledge-bases fetch to fail, then leave and
    #    return to studio — `activate()` calls `self._refresh()`, which
    #    calls loadAll() again.
    page.route("**/api/knowledge-bases", lambda route: _fail_knowledge_bases(route))
    _nav.open_destination(page, "chats")
    _nav.open_destination(page, "agents")

    # 3. Non-destructive error surfaces...
    expect(page.locator(".app-flash.error")).to_be_visible(timeout=8000)
    expect(page.locator(".app-flash.error")).to_contain_text("Unable to load Studio data")

    # 4. ...and the already-rendered area is NOT blanked — the header/CTA
    #    that was visible before the refresh is still there.
    expect(new_agent_btn).to_be_visible()
    expect(page.locator(".studio-loadall-error")).to_have_count(0)


@pytest.mark.browser
def test_loadall_rejects_on_agents_list_500(app_clean: str, page: Page) -> None:
    """M25 F2 L7 (AC5a): App.store.get rejects on a non-2xx LIST response, so
    loadAll() rejects and the load-error line shows -- no tile or save is
    offered (squawk 0014). Only the exact list route fails."""

    def fail(route) -> None:
        if route.request.method == "GET" and route.request.url.split("?")[0].endswith(
            "/api/agents"
        ):
            route.fulfill(status=500, content_type="application/json", body='{"detail": "boom"}')
        else:
            route.continue_()

    page.route("**/api/agents", fail)
    _nav.goto(page, app_clean, "agents")
    error_line = page.locator(".studio-loadall-error")
    expect(error_line).to_be_visible(timeout=8000)
    expect(page.locator('[data-testid="agent-item"]')).to_have_count(0)
