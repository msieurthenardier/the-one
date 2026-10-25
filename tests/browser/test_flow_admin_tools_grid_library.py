"""M31 F4 leg 06 (tools-grid): the Built-in tools list on the library.

Defects found in planning (DD8 1-3), each written to fail on the pre-leg code:

* 1  the tile switch is a ``role=switch`` named "Enable {name} for all agents";
* 2  a failing ``GET /api/tools/configs`` shows a load error and a Retry, not
     "Loading tools…" for good;
* 3  a failing detail ``GET`` for ``#settings/tools/{name}`` leaves the URL at
     ``#settings/tools`` with the list usable and an error shown.

And the grid's contract: a toggle patches its tile (no rebuild), a failed PUT
reverts it with the server's reason, the tiles show the per-tool summary and no
category badge (B1, A6), the active tab survives leaving and re-entering the
page, and a tool that disappears from the list hands focus to a neighbour.
"""

from __future__ import annotations

import json

import pytest
from browser import _lists, _nav
from playwright.sync_api import Page, Route, expect

TOGGLE_NAME = "Enable web_search for all agents"
ADMIN_REFRESH = "() => App.areas.find((a) => a.id === 'admin')._refresh()"

OBSERVER_JS = """() => {
  window.__removed = [];
  const list = document.querySelector('.settings-list');
  new MutationObserver((records) => {
    for (const r of records) {
      for (const n of r.removedNodes) {
        if (n.nodeType === 1 && (n.matches('[data-testid="tool-card"]') ||
            n.querySelector('[data-testid="tool-card"]'))) {
          window.__removed.push(n.getAttribute('data-name') || n.className);
        }
      }
      for (const n of r.addedNodes) {
        if (n.nodeType === 1 && n.matches('[data-testid="tool-card"]')) {
          window.__removed.push('added:' + n.getAttribute('data-name'));
        }
      }
    }
  }).observe(list, {childList: true, subtree: true});
}"""


def _open(page: Page, base: str, route: str = "settings/tools") -> None:
    _nav.goto(page, base, route)
    expect(page.locator(".area-admin .page-title")).to_have_text("Built-in tools", timeout=8000)


def _web_tab(page: Page) -> None:
    page.locator('[data-testid="tab-web"]').click()
    expect(page.locator("#tools-panel-web")).to_be_visible()


# ── DD8-1 ────────────────────────────────────────────────────────────────────


@pytest.mark.browser
def test_tile_toggle_is_a_named_switch(app_clean: str, page: Page) -> None:
    _open(page, app_clean)
    _web_tab(page)
    switch = page.get_by_role("switch", name=TOGGLE_NAME)
    expect(switch).to_have_count(1)
    expect(switch).to_be_checked()
    # The state is announced by the role, not by hidden words in the name.
    assert (
        page.evaluate(
            '() => document.querySelector(\'[data-testid="tool-toggle"][data-name="web_search"]\')'
            ".getAttribute('role')"
        )
        == "switch"
    )


# ── DD8-2 ────────────────────────────────────────────────────────────────────


@pytest.mark.browser
def test_list_load_failure_shows_error_and_retry(app_clean: str, page: Page) -> None:
    def fail(route: Route) -> None:
        route.fulfill(status=500, content_type="application/json", body='{"detail": "boom now"}')

    page.route("**/api/tools/configs", fail)
    _open(page, app_clean)
    status = page.locator(".settings-list [data-testid='tools-load-error']")
    expect(status).to_contain_text("Couldn't load the built-in tools.", timeout=8000)
    expect(status).to_contain_text("boom now")
    expect(page.locator(".settings-list")).not_to_contain_text("Loading tools")
    retry = page.locator('[data-testid="tools-load-retry"]')
    expect(retry).to_be_visible()
    page.unroute("**/api/tools/configs")
    retry.click()
    expect(page.locator('#tools-panel-filesystem [data-testid="tool-card"]')).to_have_count(
        9, timeout=8000
    )
    expect(status).to_have_count(0)


# ── DD8-3 ────────────────────────────────────────────────────────────────────


@pytest.mark.browser
def test_detail_failure_does_not_strand_the_page(app_clean: str, page: Page) -> None:
    def fail(route: Route) -> None:
        if route.request.method != "GET":
            route.continue_()
            return
        route.fulfill(status=500, content_type="application/json", body='{"detail": "detail down"}')

    page.route("**/api/tools/configs/read_file", fail)
    _nav.goto(page, app_clean, "settings/tools/read_file")
    expect(page.locator(".app-flash.error")).to_contain_text("detail down", timeout=8000)
    _nav.expect_route(page, "settings/tools")
    _lists.expect_none_selected(page, "settings/tools")
    expect(page.locator(".editor-title")).to_have_count(0)
    # The list is usable: another tool opens.
    page.unroute("**/api/tools/configs/read_file")
    _lists.open_tool(page, "list_dir")
    expect(page.locator(".editor-title")).to_have_text("list_dir", timeout=8000)


@pytest.mark.browser
def test_detail_404_still_heals_the_url(app_clean: str, page: Page) -> None:
    _nav.goto(page, app_clean, "settings/tools/no_such_tool")
    _nav.expect_route(page, "settings/tools")
    expect(page.locator(".editor-title")).to_have_count(0)
    expect(page.locator("#tools-panel-filesystem")).to_be_visible()
    expect(page.locator(".app-flash")).to_have_count(0)


# ── No rebuild on a toggle ───────────────────────────────────────────────────


@pytest.mark.browser
def test_toggle_patches_its_tile_and_keeps_focus(app_clean: str, page: Page) -> None:
    _open(page, app_clean)
    _web_tab(page)
    toggle = _lists.tool_toggle(page, "web_search")
    toggle.focus()
    page.evaluate(OBSERVER_JS)
    held: list[Route] = []

    def hold(route: Route) -> None:
        if route.request.method == "PUT":
            held.append(route)
        else:
            route.continue_()

    page.route("**/api/tools/configs/web_search", hold)
    page.keyboard.press("Space")
    expect(toggle).to_be_disabled()
    expect(toggle).not_to_be_checked()
    for _ in range(100):  # route handlers run while Playwright is called
        if held:
            break
        page.wait_for_timeout(50)
    assert len(held) == 1
    held[0].continue_()
    expect(toggle).not_to_be_disabled(timeout=5000)
    expect(toggle).to_be_focused()
    assert page.evaluate("() => window.__removed") == []


@pytest.mark.browser
def test_failed_toggle_reverts_in_place_with_the_server_reason(app_clean: str, page: Page) -> None:
    _open(page, app_clean)
    _web_tab(page)

    def fail(route: Route) -> None:
        if route.request.method == "PUT":
            route.fulfill(status=500, content_type="application/json", body='{"detail": "no disk"}')
        else:
            route.continue_()

    page.route("**/api/tools/configs/web_search", fail)
    toggle = _lists.tool_toggle(page, "web_search")
    expect(toggle).to_be_checked()
    page.evaluate(OBSERVER_JS)
    toggle.click(force=True)
    expect(page.locator(".app-flash.error")).to_contain_text("no disk", timeout=5000)
    expect(toggle).to_be_checked()
    expect(toggle).not_to_be_disabled()
    assert page.evaluate("() => window.__removed") == []


# ── B1 and A6 ────────────────────────────────────────────────────────────────


@pytest.mark.browser
def test_tiles_show_the_summary_and_no_category_badge(app_clean: str, page: Page) -> None:
    _open(page, app_clean)
    summaries = page.evaluate("() => fetch('/api/tools/configs').then((r) => r.json())")
    by_name = {t["name"]: t for t in summaries}
    tile = _lists.list_row(page, "settings/tools", "read_file")
    assert by_name["read_file"]["summary"]
    expect(tile.locator(".ui-tool-tile-desc")).to_have_text(by_name["read_file"]["summary"])
    expect(page.locator('[data-testid="tool-card"] .badge')).to_have_count(0)


@pytest.mark.browser
def test_tile_falls_back_to_the_description_without_a_summary(app_clean: str, page: Page) -> None:
    def strip(route: Route) -> None:
        response = route.fetch()
        data = response.json()
        for t in data:
            t.pop("summary", None)
        route.fulfill(response=response, body=json.dumps(data))

    page.route("**/api/tools/configs", strip)
    _open(page, app_clean)
    tile = _lists.list_row(page, "settings/tools", "read_file")
    expect(tile.locator(".ui-tool-tile-desc")).not_to_have_text("", timeout=8000)
    description = page.evaluate(
        "() => fetch('/api/tools/configs/read_file').then((r) => r.json())"
        ".then((d) => d.description)"
    )
    expect(tile.locator(".ui-tool-tile-desc")).to_have_text(description)


# ── Tabs ─────────────────────────────────────────────────────────────────────


@pytest.mark.browser
def test_tabs_keyboard_and_persisted_category(app_clean: str, page: Page) -> None:
    _open(page, app_clean)
    tab_fs = page.locator('[data-testid="tab-filesystem"]')
    tab_fs.focus()
    page.keyboard.press("ArrowRight")
    expect(page.locator('[data-testid="tab-execution"]')).to_be_focused()
    expect(tab_fs).to_have_attribute("aria-selected", "true")  # arrows move focus only
    page.keyboard.press("End")
    expect(page.locator('[data-testid="tab-time"]')).to_be_focused()
    page.keyboard.press("Enter")
    expect(page.locator("#tools-panel-time")).to_be_visible()
    # Leave Settings and come back: the category the operator chose is kept.
    _lists.open_settings_page(page, "appearance")
    _lists.open_settings_page(page, "tools")
    expect(page.locator('[data-testid="tab-time"]')).to_have_attribute("aria-selected", "true")
    expect(page.locator("#tools-panel-time")).to_be_visible()


@pytest.mark.browser
def test_opening_a_tool_reveals_its_category_once(app_clean: str, page: Page) -> None:
    _open(page, app_clean, "settings/tools/fetch_url")
    expect(page.locator('[data-testid="tab-web"]')).to_have_attribute("aria-selected", "true")
    # A toggle in the open tool's list keeps the revealed tab and the editor.
    toggle = _lists.tool_toggle(page, "fetch_url")
    toggle.click(force=True)
    expect(toggle).not_to_be_disabled(timeout=5000)
    expect(page.locator('[data-testid="tab-web"]')).to_have_attribute("aria-selected", "true")
    expect(page.locator(".editor-title")).to_have_text("fetch_url")


# ── Switching category closes an open editor (HAT step 3, ledger 49) ─────────

OVERLAY = '[data-testid="confirm-dialog-overlay"]'


def _tab(page: Page, cat: str):
    return page.locator(f'[data-testid="tab-{cat}"]')


def _expect_closed_on_web(page: Page) -> None:
    expect(page.locator(".editor-title")).to_have_count(0, timeout=5000)
    _nav.expect_route(page, "settings/tools")
    expect(page.locator("#tools-panel-web")).to_be_visible()
    expect(_tab(page, "web")).to_have_attribute("aria-selected", "true")
    expect(page.locator('[data-testid="tool-card"] a[aria-current="page"]')).to_have_count(0)


def _dirty_web_search(page: Page, base: str) -> None:
    _open(page, base, "settings/tools/web_search")
    expect(page.locator(".editor-title")).to_have_text("web_search", timeout=8000)
    page.locator('[data-field="search_backend"]').select_option("searxng")


@pytest.mark.browser
def test_switching_tab_with_a_clean_editor_closes_it(app_clean: str, page: Page) -> None:
    _open(page, app_clean, "settings/tools/read_file")
    expect(page.locator(".editor-title")).to_have_text("read_file", timeout=8000)
    _tab(page, "web").click()
    expect(page.locator(OVERLAY)).to_have_count(0)
    _expect_closed_on_web(page)
    expect(_tab(page, "web")).to_be_focused()  # not main: the tab the user activated


@pytest.mark.browser
def test_switching_tab_with_a_dirty_editor_stay_keeps_everything(
    app_clean: str, page: Page
) -> None:
    _dirty_web_search(page, app_clean)
    _tab(page, "time").click()
    expect(page.locator(OVERLAY)).to_be_visible(timeout=5000)
    page.locator('[data-testid="modal-cancel-btn"]').click()
    expect(page.locator(OVERLAY)).to_have_count(0)
    # Stay: the dialog returns focus to its opener (the tab clicked)
    expect(_tab(page, "time")).to_be_focused()
    expect(page.locator(".editor-title")).to_have_text("web_search")
    expect(page.locator('[data-field="search_backend"]')).to_have_value("searxng")
    expect(_tab(page, "web")).to_have_attribute("aria-selected", "true")
    expect(_tab(page, "time")).to_have_attribute("aria-selected", "false")
    expect(page.locator("#tools-panel-web")).to_be_visible()
    _nav.expect_route(page, "settings/tools/web_search")


@pytest.mark.browser
def test_switching_tab_with_a_dirty_editor_continue_closes_it(app_clean: str, page: Page) -> None:
    _dirty_web_search(page, app_clean)
    _tab(page, "time").click()
    expect(page.locator(OVERLAY)).to_be_visible(timeout=5000)
    page.locator('[data-testid="modal-confirm-btn"]').click()
    expect(page.locator(".editor-title")).to_have_count(0, timeout=5000)
    _nav.expect_route(page, "settings/tools")
    expect(page.locator("#tools-panel-time")).to_be_visible()
    expect(_tab(page, "time")).to_have_attribute("aria-selected", "true")
    expect(page.locator('[data-testid="tool-card"] a[aria-current="page"]')).to_have_count(0)
    expect(_tab(page, "time")).to_be_focused()


@pytest.mark.browser
def test_switching_tab_with_no_editor_open_changes_no_route(app_clean: str, page: Page) -> None:
    _open(page, app_clean)
    _tab(page, "web").click()
    expect(page.locator("#tools-panel-web")).to_be_visible()
    _nav.expect_route(page, "settings/tools")
    expect(page.locator(OVERLAY)).to_have_count(0)


@pytest.mark.browser
def test_keyboard_tab_switch_closes_the_editor_like_a_click(app_clean: str, page: Page) -> None:
    _dirty_web_search(page, app_clean)
    _tab(page, "web").focus()
    page.keyboard.press("ArrowRight")  # focus only: nothing is asked yet
    expect(page.locator(OVERLAY)).to_have_count(0)
    expect(page.locator(".editor-title")).to_have_text("web_search")
    page.keyboard.press("Enter")
    expect(page.locator(OVERLAY)).to_be_visible(timeout=5000)
    page.locator('[data-testid="modal-cancel-btn"]').click()
    expect(page.locator(".editor-title")).to_have_text("web_search")
    expect(_tab(page, "web")).to_have_attribute("aria-selected", "true")
    page.keyboard.press("Enter")
    expect(page.locator(OVERLAY)).to_be_visible(timeout=5000)
    page.locator('[data-testid="modal-confirm-btn"]').click()
    expect(page.locator(".editor-title")).to_have_count(0, timeout=5000)
    _nav.expect_route(page, "settings/tools")
    activated = page.locator('[role="tab"][aria-selected="true"]')
    expect(activated).to_be_focused()


# ── Empty category and a vanishing tool ──────────────────────────────────────


@pytest.mark.browser
def test_empty_category_shows_no_tools(app_clean: str, page: Page) -> None:
    def only_fs(route: Route) -> None:
        response = route.fetch()
        data = [t for t in response.json() if t["name"] in ("read_file", "list_dir")]
        route.fulfill(response=response, body=json.dumps(data))

    page.route("**/api/tools/configs", only_fs)
    _open(page, app_clean)
    expect(page.locator('#tools-panel-filesystem [data-testid="tool-card"]')).to_have_count(2)
    page.locator('[data-testid="tab-web"]').click()
    expect(page.locator("#tools-panel-web")).to_contain_text("No tools.")
    expect(page.locator('#tools-panel-web [data-testid="tool-card"]')).to_have_count(0)


@pytest.mark.browser
def test_focus_moves_to_the_next_toggle_when_the_focused_tool_disappears(
    app_clean: str, page: Page
) -> None:
    state = {"drop": None}

    def listing(route: Route) -> None:
        response = route.fetch()
        data = response.json()
        if state["drop"]:
            data = [t for t in data if t["name"] != state["drop"]]
        route.fulfill(response=response, body=json.dumps(data))

    page.route("**/api/tools/configs", listing)
    _open(page, app_clean)
    names = page.evaluate(
        "() => [...document.querySelectorAll("
        "'#tools-panel-filesystem [data-testid=\"tool-card\"]')]"
        ".map((n) => n.dataset.name)"
    )
    victim, successor = names[2], names[3]
    _lists.tool_toggle(page, victim).focus()
    state["drop"] = victim
    page.evaluate(ADMIN_REFRESH)
    expect(page.locator(f'[data-testid="tool-card"][data-name="{victim}"]')).to_have_count(
        0, timeout=8000
    )
    expect(_lists.tool_toggle(page, successor)).to_be_focused()
    # The last tile: focus goes to the previous one.
    last, before = names[-1], names[-2]
    state["drop"] = None
    page.evaluate(ADMIN_REFRESH)
    expect(page.locator(f'[data-testid="tool-card"][data-name="{victim}"]')).to_have_count(1)
    _lists.tool_toggle(page, last).focus()
    state["drop"] = last
    page.evaluate(ADMIN_REFRESH)
    expect(page.locator(f'[data-testid="tool-card"][data-name="{last}"]')).to_have_count(
        0, timeout=8000
    )
    expect(_lists.tool_toggle(page, before)).to_be_focused()
