"""Sortie 07 leg 5 (DD8, AC6): Settings > Built-in tools warns before a save narrows agents.

The editor asks ``POST /api/tools/configs/{name}/impact`` first; a non-empty answer opens the
"Saving narrows N agents" dialog (Save anyway / Cancel). Cancel leaves the form dirty and
stores nothing; a save that narrows nobody has no dialog; a saved config and the tile's
on/off switch both invalidate the ``agents`` store. Falls in the ``settings-tools`` lane.
"""

from __future__ import annotations

import urllib.parse

import httpx
import pytest
from browser import _lists, _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp, seed_mock_agent, seed_tool_config
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

SAVE = '[data-testid="save-tool-btn"]'
UNSAVED = '[data-testid="editor-unsaved"]'
DIALOG = '[data-testid="confirm-dialog-overlay"]'
HOSTS = "#tef-extra_allowed_hosts"


def _agent(base: str, name: str) -> dict:
    url = f"{base}/api/agents/{urllib.parse.quote(name)}"
    return httpx.get(url, timeout=5.0, headers=auth_headers_for(base)).json()


def _give_override(base: str, name: str) -> None:
    url = f"{base}/api/agents/{urllib.parse.quote(name)}"
    cfg = _agent(base, name)
    cfg["tool_overrides"] = {"http_request": {"extra_allowed_hosts": ["a.com", "b.com"]}}
    r = httpx.put(url, json=cfg, timeout=5.0, headers=auth_headers_for(base))
    assert r.status_code == 200, r.text


def _stored_hosts(base: str) -> list[str]:
    r = httpx.get(
        f"{base}/api/tools/configs/http_request", timeout=5.0, headers=auth_headers_for(base)
    )
    return r.json()["config"].get("extra_allowed_hosts", [])


def _setup(app: SeededApp) -> tuple[str, list[str]]:
    base = app.base_url
    assert app.agent_name is not None
    second = seed_mock_agent(base, app.provider_id, name="second-agent")
    seed_tool_config(base, "http_request", config={"extra_allowed_hosts": ["a.com", "b.com"]})
    names = [app.agent_name, second]
    for n in names:
        _give_override(base, n)
    return base, names


def _drop_last_host(page: Page) -> None:
    page.locator(HOSTS).press("Backspace")
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes", timeout=5000)


def _spy_invalidate(page: Page) -> None:
    page.evaluate(
        """() => { window.__inv = []; const o = App.store.invalidate;
          App.store.invalidate = function (n) {
            window.__inv.push(n); return o.apply(this, arguments);
          }; }"""
    )


def test_a_narrowing_save_asks_first_and_cancel_stores_nothing(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, names = _setup(app_with_agent)
    _nav.goto(page, base, "settings/tools/http_request")
    expect(page.locator(".editor-title")).to_have_text("http_request", timeout=8000)
    _drop_last_host(page)
    page.locator(SAVE).click()
    dialog = page.locator(DIALOG)
    expect(dialog).to_be_visible(timeout=5000)
    expect(dialog).to_contain_text("Saving narrows 2 agents")
    listing = page.locator('[data-testid="tool-impact-list"]')
    for n in names:
        expect(listing).to_contain_text(n)
    expect(listing).to_contain_text("Extra allowed hosts")
    expect(listing).to_contain_text("b.com")
    # Cancel: the form stays dirty and nothing was stored.
    page.locator('[data-testid="modal-cancel-btn"]').click()
    expect(dialog).to_have_count(0)
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    assert _stored_hosts(base) == ["a.com", "b.com"]
    assert all(_agent(base, n)["notices"] == [] for n in names)
    # Save again and confirm: stored, and both agents now carry the notice.
    page.locator(SAVE).click()
    expect(dialog).to_be_visible(timeout=5000)
    page.locator('[data-testid="modal-confirm-btn"]').click()
    expect(page.locator(UNSAVED)).to_have_text("", timeout=8000)
    assert _stored_hosts(base) == ["a.com"]
    assert all(
        [x["field"] for x in _agent(base, n)["notices"]] == ["extra_allowed_hosts"] for n in names
    )


def test_a_save_that_narrows_nobody_has_no_dialog(app_with_agent: SeededApp, page: Page) -> None:
    base = app_with_agent.base_url
    seed_tool_config(base, "http_request", config={"extra_allowed_hosts": ["a.com"]})
    _nav.goto(page, base, "settings/tools/http_request")
    expect(page.locator(".editor-title")).to_have_text("http_request", timeout=8000)
    inp = page.locator(HOSTS)
    inp.fill("z.com")
    inp.press("Enter")
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes", timeout=5000)
    page.locator(SAVE).click()
    expect(page.locator(UNSAVED)).to_have_text("", timeout=8000)
    assert page.locator(DIALOG).count() == 0
    assert _stored_hosts(base) == ["a.com", "z.com"]


def test_a_save_and_the_tile_switch_invalidate_the_agents_store(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    _nav.goto(page, base, "settings/tools/http_request")
    expect(page.locator(".editor-title")).to_have_text("http_request", timeout=8000)
    _spy_invalidate(page)
    inp = page.locator(HOSTS)
    inp.fill("q.com")
    inp.press("Enter")
    page.locator(SAVE).click()
    expect(page.locator(UNSAVED)).to_have_text("", timeout=8000)
    assert page.evaluate("() => window.__inv.filter((n) => n === 'agents').length") == 1
    _lists.tool_toggle(page, "http_request").click(force=True)  # the track covers the input
    page.wait_for_function(
        "() => window.__inv.filter((n) => n === 'agents').length === 2", timeout=8000
    )


def _enabled(base: str) -> bool:
    r = httpx.get(
        f"{base}/api/tools/configs/http_request", timeout=5.0, headers=auth_headers_for(base)
    )
    return r.json()["enabled"]


def test_turning_a_tool_on_lists_the_agents_it_narrows_first(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Squawk 0322: the tile switch runs the impact check before an enabling toggle; Cancel
    leaves the tool off, confirming turns it on."""
    base, names = _setup(app_with_agent)
    seed_tool_config(base, "http_request", enabled=False, config={"extra_allowed_hosts": ["a.com"]})
    _nav.goto(page, base, "settings/tools")
    page.locator(f'[data-testid="tab-{_lists.TOOL_TABS["http_request"]}"]').click()
    toggle = _lists.tool_toggle(page, "http_request")
    expect(toggle).not_to_be_checked(timeout=8000)
    held: list = []
    page.route("**/api/tools/configs/http_request/impact", lambda route: held.append(route))
    toggle.click(force=True)
    for _ in range(50):
        if held:
            break
        page.wait_for_timeout(100)
    assert held, "the impact preview was not requested"
    # The preview is in flight: the switch is disabled so a second press cannot flip it.
    expect(toggle).to_be_disabled()
    held[0].continue_()
    dialog = page.locator(DIALOG)
    expect(dialog).to_be_visible(timeout=5000)
    expect(toggle).to_be_enabled()
    expect(dialog).to_contain_text("Turning on http_request affects 2 agents")
    listing = page.locator('[data-testid="tool-impact-list"]')
    for n in names:
        expect(listing).to_contain_text(n)
    page.locator('[data-testid="modal-cancel-btn"]').click()
    expect(dialog).to_have_count(0)
    expect(toggle).not_to_be_checked()
    expect(toggle).to_be_focused()
    assert _enabled(base) is False
    page.unroute("**/api/tools/configs/http_request/impact")
    toggle.click(force=True)
    expect(dialog).to_be_visible(timeout=5000)
    page.locator('[data-testid="modal-confirm-btn"]').click()
    expect(toggle).to_be_checked(timeout=8000)
    page.wait_for_timeout(500)
    assert _enabled(base) is True


def test_turning_a_tool_on_that_narrows_nobody_has_no_dialog(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    seed_tool_config(base, "http_request", enabled=False)
    _nav.goto(page, base, "settings/tools")
    page.locator(f'[data-testid="tab-{_lists.TOOL_TABS["http_request"]}"]').click()
    toggle = _lists.tool_toggle(page, "http_request")
    expect(toggle).not_to_be_checked(timeout=8000)
    toggle.click(force=True)
    expect(toggle).to_be_checked(timeout=8000)
    assert page.locator(DIALOG).count() == 0
    page.wait_for_timeout(500)
    assert _enabled(base) is True
