"""M31 F4 leg 07c: the Built-in tools editor's Save and Cancel model.

Defects found in planning (DD8), each written to fail on the pre-leg editor:

* 5  Cancel during an in-flight Save shows values the server no longer holds;
* 6  an edit typed during a Save is marked saved but was never sent;
* 7  a Save response for tool A writes into tool B's editor and drops B's leave guard;
* 8  the secret is not re-masked after Save.

The timing-sensitive tests hold a request with ``page.route`` and release it from the test
body (DD10: never a fixed wait to prove "nothing changed after a late response"). Playwright
sync mode runs a route handler only while a Playwright call is in progress, so a handler just
collects the Route and the test resolves it.

Also here: the remount side-effect inventory (a test for each "re-run" item), the busy rule,
no remount on Save or Cancel, and the Enabled race with the list toggle.
"""

from __future__ import annotations

import httpx
import pytest
from browser import _lists, _nav
from browser._credential_registry import auth_headers_for
from playwright.sync_api import Page, Route, expect

ITEM = ".area-admin .settings-item"
SAVE = '[data-testid="save-tool-btn"]'
CANCEL = '[data-testid="cancel-tool-btn"]'
UNSAVED = '[data-testid="editor-unsaved"]'

REMOUNT_OBSERVER_JS = """() => {
  window.__removed = [];
  const root = document.querySelector('.settings-item');
  new MutationObserver((records) => {
    for (const r of records) {
      for (const n of r.removedNodes) {
        if (n.nodeType === 1 && (n.matches('.editor-header, .editor-section') ||
            n.querySelector('.editor-header, .editor-section'))) {
          window.__removed.push(n.className);
        }
      }
    }
  }).observe(root, {childList: true, subtree: true});
}"""


def _open(page: Page, base: str, tool: str) -> None:
    _nav.goto(page, base, f"settings/tools/{tool}")
    expect(page.locator(".editor-title")).to_have_text(tool, timeout=8000)


def _hold_puts(page: Page, tool: str) -> list[Route]:
    held: list[Route] = []

    def handler(route: Route) -> None:
        if route.request.method == "PUT":
            held.append(route)
        else:
            route.continue_()

    page.route(f"**/api/tools/configs/{tool}", handler)
    return held


def _wait_held(page: Page, held: list[Route], count: int) -> None:
    for _ in range(200):  # the handler runs while Playwright is called
        if len(held) >= count:
            return
        page.wait_for_timeout(25)
    raise AssertionError(f"expected {count} held request(s), saw {len(held)}")


def _stored(base: str, tool: str) -> dict:
    r = httpx.get(f"{base}/api/tools/configs/{tool}", timeout=5.0, headers=auth_headers_for(base))
    assert r.status_code == 200, r.text
    return r.json()


def _wait_saved(page: Page) -> None:
    """The Save response has landed: the caption is cleared and Save is disabled again.
    (Save is also disabled while busy, so a disabled Save alone proves nothing.)"""
    expect(page.locator(UNSAVED)).to_have_text("", timeout=8000)
    expect(page.locator(SAVE)).to_be_disabled()


def _dirty(page: Page) -> bool:
    return page.evaluate("App.nav.isDirty()")


# ── DD8-5 ────────────────────────────────────────────────────────────────────


@pytest.mark.browser
def test_cancel_is_unavailable_during_a_save_and_the_form_shows_what_was_saved(
    app_clean: str, page: Page
) -> None:
    _open(page, app_clean, "web_search")
    held = _hold_puts(page, "web_search")
    page.locator('[data-field="search_backend"]').select_option("searxng")
    page.locator('input[data-field="searxng_base_url"]').fill("https://searx.example.org")
    page.locator(SAVE).click()
    _wait_held(page, held, 1)
    expect(page.locator(CANCEL)).to_be_disabled()
    held[0].continue_()
    _wait_saved(page)
    expect(page.locator('[data-field="search_backend"]')).to_have_value("searxng")
    expect(page.locator('input[data-field="searxng_base_url"]')).to_have_value(
        "https://searx.example.org"
    )
    expect(page.locator(UNSAVED)).to_have_text("")
    assert _stored(app_clean, "web_search")["config"]["search_backend"] == "searxng"


# ── DD8-6 ────────────────────────────────────────────────────────────────────


@pytest.mark.browser
def test_an_edit_typed_during_a_save_stays_dirty_and_is_not_lost(
    app_clean: str, page: Page
) -> None:
    _open(page, app_clean, "fetch_url")
    held = _hold_puts(page, "fetch_url")
    agent = page.locator('input[data-field="default_user_agent"]')
    agent.fill("first-agent")
    page.locator(SAVE).click()
    _wait_held(page, held, 1)
    expect(agent).to_be_enabled()  # the fields stay live during the request
    agent.fill("second-agent")
    held[0].continue_()
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes", timeout=5000)
    expect(agent).to_have_value("second-agent")
    expect(page.locator(SAVE)).to_be_enabled()
    assert _dirty(page) is True
    assert _stored(app_clean, "fetch_url")["config"]["default_user_agent"] == "first-agent"
    held.clear()
    page.unroute("**/api/tools/configs/fetch_url")
    page.locator(SAVE).click()
    _wait_saved(page)
    assert _stored(app_clean, "fetch_url")["config"]["default_user_agent"] == "second-agent"


# ── DD8-7 ────────────────────────────────────────────────────────────────────


@pytest.mark.browser
def test_a_late_save_for_one_tool_never_touches_another_tools_editor(
    app_clean: str, page: Page
) -> None:
    _open(page, app_clean, "fetch_url")
    page.locator('[data-tab-id="web"]').first.wait_for(state="attached")
    held = _hold_puts(page, "fetch_url")
    # Make A's save visible in the list: turn it off, and edit a field too.
    page.get_by_role("switch", name="Enabled for all agents").evaluate("e => e.click()")
    page.locator('input[data-field="default_user_agent"]').fill("agent-from-a")
    page.locator(SAVE).click()
    _wait_held(page, held, 1)
    # Open B through its link: A is dirty, so the leave dialog asks; continue.
    _lists.item_link(page, "settings/tools", "http_request").click()
    overlay = page.locator('[data-testid="confirm-dialog-overlay"]')
    expect(overlay).to_be_visible(timeout=5000)
    page.locator('[data-testid="modal-confirm-btn"]').click()
    expect(page.locator(".editor-title")).to_have_text("http_request", timeout=8000)
    b_field = page.locator('input[data-field="default_user_agent"]')
    b_field.fill("agent-from-b")
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    assert _dirty(page) is True
    # Release A's response now.
    held[0].continue_()
    expect(_lists.tool_toggle(page, "fetch_url")).not_to_be_checked(timeout=8000)  # A's tile
    # B is untouched: value, caption, leave guard, errors, no stale flash.
    expect(b_field).to_have_value("agent-from-b")
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    expect(page.locator(SAVE)).to_be_enabled()
    expect(page.locator(CANCEL)).to_be_enabled()
    expect(page.locator(f"{ITEM} .editor-error")).to_have_text("")
    expect(page.locator(".app-flash")).to_have_count(0)
    assert _dirty(page) is True


# ── DD8-8 ────────────────────────────────────────────────────────────────────


@pytest.mark.browser
def test_a_secret_is_remasked_after_save(app_clean: str, page: Page) -> None:
    _open(page, app_clean, "web_search")
    page.locator('[data-field="search_backend"]').select_option("brave")
    key = page.locator('input[data-field="brave_api_key"]')
    key.fill("BSA-supersecret-token-1234")
    page.locator(SAVE).click()
    _wait_saved(page)
    value = key.input_value()
    assert value != "BSA-supersecret-token-1234", "the plaintext must not stay in the field"
    assert value.startswith("***") and value.endswith("1234"), value
    expect(page.locator(UNSAVED)).to_have_text("")


@pytest.mark.browser
def test_a_secret_retyped_during_the_save_is_kept(app_clean: str, page: Page) -> None:
    _open(page, app_clean, "web_search")
    held = _hold_puts(page, "web_search")
    page.locator('[data-field="search_backend"]').select_option("brave")
    key = page.locator('input[data-field="brave_api_key"]')
    key.fill("BSA-first-1111")
    page.locator(SAVE).click()
    _wait_held(page, held, 1)
    key.fill("BSA-second-2222")
    held[0].continue_()
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes", timeout=5000)
    expect(key).to_have_value("BSA-second-2222")


# ── No remount; busy ─────────────────────────────────────────────────────────


@pytest.mark.browser
def test_save_and_cancel_patch_in_place(app_clean: str, page: Page) -> None:
    _open(page, app_clean, "web_search")
    page.evaluate(REMOUNT_OBSERVER_JS)
    page.locator('[data-field="search_backend"]').select_option("searxng")
    page.locator('input[data-field="searxng_base_url"]').fill("https://searx.example.org")
    page.locator(SAVE).click()
    _wait_saved(page)
    page.locator('input[data-field="searxng_base_url"]').fill("https://other.example.org")
    page.locator(CANCEL).focus()
    page.keyboard.press("Enter")
    expect(page.locator('input[data-field="searxng_base_url"]')).to_have_value(
        "https://searx.example.org"
    )
    expect(page.locator(".editor-title")).to_be_focused()
    assert page.evaluate("() => window.__removed") == []


@pytest.mark.browser
def test_busy_disables_save_cancel_and_test_but_not_the_fields(app_clean: str, page: Page) -> None:
    _open(page, app_clean, "fetch_url")
    held = _hold_puts(page, "fetch_url")
    agent = page.locator('input[data-field="default_user_agent"]')
    agent.fill("busy-agent")
    page.locator(SAVE).click()
    _wait_held(page, held, 1)
    expect(page.locator(SAVE)).to_be_disabled()
    expect(page.locator(CANCEL)).to_be_disabled()
    expect(page.locator('[data-testid="test-tool-btn"]')).to_be_disabled()
    expect(agent).to_be_enabled()
    page.locator(SAVE).click(force=True)  # a second click sends nothing
    page.wait_for_timeout(100)
    assert len(held) == 1
    held[0].continue_()
    _wait_saved(page)
    expect(page.locator('[data-testid="test-tool-btn"]')).to_be_enabled()


@pytest.mark.browser
def test_save_is_blocked_while_a_test_is_in_flight(app_clean: str, page: Page) -> None:
    _open(page, app_clean, "fetch_url")
    held: list[Route] = []

    def handler(route: Route) -> None:
        held.append(route)

    page.route("**/api/tools/configs/fetch_url/test", handler)
    page.locator('input[data-field="default_user_agent"]').fill("testing-agent")
    expect(page.locator(SAVE)).to_be_enabled()
    page.locator('[data-testid="test-tool-btn"]').click()
    _wait_held(page, held, 1)
    expect(page.locator(SAVE)).to_be_disabled()
    held[0].fulfill(
        status=200,
        content_type="application/json",
        body='{"output": "ok", "elapsed_ms": 3, "outcome": "ok"}',
    )
    expect(page.locator(SAVE)).to_be_enabled(timeout=5000)


# ── The remount side-effect inventory: items re-run on Save or Cancel ────────


@pytest.mark.browser
def test_cancel_reapplies_show_if_and_drops_field_and_editor_errors(
    app_clean: str, page: Page
) -> None:
    _open(page, app_clean, "web_search")
    row = page.locator(f'{ITEM} .tools-editor-field[data-field-name="brave_api_key"]')
    expect(row).to_be_hidden()
    page.locator('[data-field="search_backend"]').select_option("brave")
    expect(row).to_be_visible()
    page.locator('input[data-field="brave_api_key"]').fill("BSA-typed-not-saved-0000")
    page.locator(CANCEL).click()
    expect(row).to_be_hidden()  # show_if re-run against the restored backend
    expect(page.locator('[data-field="search_backend"]')).to_have_value("duckduckgo")
    expect(page.locator('input[data-field="brave_api_key"]')).to_have_value("")
    expect(page.locator(CANCEL)).to_be_disabled()
    # Errors are cleared too.
    _open_fetch_with_errors(page, app_clean)


def _open_fetch_with_errors(page: Page, base: str) -> None:
    _open(page, base, "fetch_url")
    original = page.locator('input[data-field="redirect_cap"]').input_value()
    page.locator('input[data-field="redirect_cap"]').fill("-1")
    page.locator('input[data-field="timeout_seconds_max"]').fill("10")
    page.locator(SAVE).click()
    expect(page.locator('input[data-field="redirect_cap"]')).to_have_attribute(
        "aria-invalid", "true", timeout=5000
    )
    page.locator(CANCEL).click()
    expect(page.locator('input[data-field="redirect_cap"]')).not_to_have_attribute(
        "aria-invalid", "true"
    )
    expect(page.locator(f"{ITEM} .editor-error")).to_have_text("")
    expect(page.locator('input[data-field="redirect_cap"]')).to_have_value(original)


@pytest.mark.browser
def test_cancel_restores_the_masked_secret(app_clean: str, page: Page) -> None:
    _open(page, app_clean, "web_search")
    page.locator('[data-field="search_backend"]').select_option("brave")
    key = page.locator('input[data-field="brave_api_key"]')
    key.fill("BSA-saved-token-4321")
    page.locator(SAVE).click()
    _wait_saved(page)
    masked = key.input_value()
    assert masked.startswith("***")
    key.fill("BSA-typed-over-8888")
    page.locator(CANCEL).click()
    expect(key).to_have_value(masked)


@pytest.mark.browser
def test_save_updates_the_tile_and_clears_the_leave_guard(app_clean: str, page: Page) -> None:
    _open(page, app_clean, "http_request")
    page.get_by_role("switch", name="Enabled for all agents").evaluate("e => e.click()")
    assert _dirty(page) is True
    page.locator(SAVE).click()
    _wait_saved(page)
    expect(_lists.tool_toggle(page, "http_request")).not_to_be_checked()
    assert _dirty(page) is False
    expect(page.locator(".app-flash")).to_contain_text("Tool saved")


# ── The Enabled race with the list toggle ────────────────────────────────────


@pytest.mark.browser
@pytest.mark.parametrize("save_first", [True, False])
def test_enabled_follows_the_server_when_a_save_and_a_list_toggle_race(
    app_clean: str, page: Page, save_first: bool
) -> None:
    _open(page, app_clean, "fetch_url")
    held = _hold_puts(page, "fetch_url")
    page.locator('input[data-field="default_user_agent"]').fill("racing-agent")
    page.locator(SAVE).click()  # the body holds enabled: true
    _wait_held(page, held, 1)
    _lists.tool_toggle(page, "fetch_url").click(force=True)  # {enabled: false}
    _wait_held(page, held, 2)
    save_route, toggle_route = held[0], held[1]
    for route in (save_route, toggle_route) if save_first else (toggle_route, save_route):
        route.continue_()
        page.wait_for_timeout(150)  # let the server answer before the next is released
    expect(_lists.tool_toggle(page, "fetch_url")).not_to_be_disabled(timeout=8000)
    expect(page.locator(SAVE)).to_be_disabled(timeout=8000)
    oracle = _stored(app_clean, "fetch_url")["enabled"]
    assert oracle is (not save_first)  # the later write wins on the server
    switch = page.get_by_role("switch", name="Enabled for all agents")
    if oracle:
        expect(switch).to_be_checked()
        expect(_lists.tool_toggle(page, "fetch_url")).to_be_checked()
    else:
        expect(switch).not_to_be_checked()
        expect(_lists.tool_toggle(page, "fetch_url")).not_to_be_checked()
