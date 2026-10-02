"""Settings item pages keep their list visible (M25 F3 leg 5b; flight DD7, DD2, DD8).

Providers is the reference spec section 8.2 table (Name, Type, Used by) and a
provider -- or the create form -- opens in an item section BELOW the table;
Built-in tools keeps its tabs and tiles, the tool NAME is the item link and the
tool editor opens below the list. Both editors carry the breadcrumb ("Settings
/ Providers", "Settings / Built-in tools"), no Back, and the unsaved caption.

AC1 the table; AC2 a provider below it (visibility at 1440x900, focus, the
breadcrumb, a dirty editor asks once on another row); AC3 create, Cancel and
delete (focus); AC4 tools (link, selection, toggle isolation, deep-link
category, scroll and focus); AC5 the unsaved caption; plus the focus discipline
(a store notification or refresh never moves focus) and the keyboard order.
Settings lane (``test_flow_settings_*`` in ``scripts/run-tests.sh``).
"""

from __future__ import annotations

import re

import httpx
import pytest
from browser import _lists, _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp, seed_mock_agent, seed_mock_provider
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

DIALOG = '[data-testid="confirm-dialog-overlay"]'
STAY = '[data-testid="modal-cancel-btn"]'
CONTINUE = '[data-testid="modal-confirm-btn"]'
ANNOUNCER = '[data-testid="route-announcer"]'
ITEM_TITLE = ".area-admin .settings-item .editor-title"
UNSAVED = '.area-admin .settings-item [data-testid="editor-unsaved"]'


# ── helpers ─────────────────────────────────────────────────────────────────


def _seed_three(app: SeededApp) -> dict[str, str]:
    """ "mock" (the fixture's, 0 agents), "Bravo" (2 agents), "Alpha" (1 agent)."""
    base = app.base_url
    ids = {"mock": app.provider_id}
    ids["Bravo"] = seed_mock_provider(base, name="Bravo")
    ids["Alpha"] = seed_mock_provider(base, name="Alpha")
    seed_mock_agent(base, ids["Bravo"], name="bravo one")
    seed_mock_agent(base, ids["Bravo"], name="bravo two")
    seed_mock_agent(base, ids["Alpha"], name="alpha one")
    return ids


def _row_texts(page: Page) -> list[list[str]]:
    return page.evaluate(
        """() => [...document.querySelectorAll('table.providers-table tbody tr')].map(
            (tr) => [...tr.cells].map((td) => td.textContent.trim()))"""
    )


def _focused(page: Page) -> dict:
    return page.evaluate(
        """() => { const a = document.activeElement;
          return { tag: a.tagName, text: (a.textContent || '').trim(),
                   testid: a.getAttribute('data-testid'), cls: a.className, id: a.id }; }"""
    )


def _mark(page: Page, selector: str, value: str) -> None:
    page.evaluate(
        "([sel, v]) => { document.querySelector(sel).dataset.keep = v; }", [selector, value]
    )


def _mark_of(page: Page, selector: str) -> str | None:
    return page.evaluate(
        "sel => { const n = document.querySelector(sel);"
        " return n ? (n.dataset.keep || null) : 'gone'; }",
        selector,
    )


def _in_viewport(page: Page, selector: str) -> bool:
    return page.evaluate(
        """(sel) => { const r = document.querySelector(sel).getBoundingClientRect();
          return r.top >= 0 && r.bottom <= window.innerHeight && r.height > 0; }""",
        selector,
    )


def _ready(page: Page, base: str, route: str) -> None:
    _nav.goto_settled(page, base, route)
    expect(page.locator(".area-admin .page-title")).to_be_visible(timeout=8000)


# ── AC1: the Providers table ────────────────────────────────────────────────


def test_providers_table_anatomy_and_used_by_counts(
    app_with_provider: SeededApp, page: Page
) -> None:
    _seed_three(app_with_provider)
    _ready(page, app_with_provider.base_url, "settings/providers")
    table = _lists.providers_table(page)
    expect(table).to_be_visible(timeout=8000)
    expect(page.locator(".area-admin .settings-intro")).to_have_text(
        "A provider is an account or server that runs models."
        " Agents pick one in their Model section."
    )
    heads = table.locator("thead th")
    expect(heads).to_have_text(["Name", "Type", "Used by"])
    # The rows sort A-Z; counts come from the agents list (singular for one).
    expect(table.locator("tbody tr")).to_have_count(3, timeout=8000)
    page.wait_for_function(
        "() => !document.querySelector('table.providers-table').textContent.includes('—')"
    )
    assert _row_texts(page) == [
        ["Alpha", "mock", "1 agent"],
        ["Bravo", "mock", "2 agents"],
        ["mock", "mock", "0 agents"],
    ]
    # Name is a weight-600 link to the item; Type is the kind badge.
    link = _lists.list_row(page, "settings/providers", "Bravo")
    weight = link.evaluate("(a) => getComputedStyle(a).fontWeight")
    assert weight == "600", weight
    # The Name cell is the row header (th scope=row, the flight-end review,
    # WCAG 1.3.1) with the body cells' look; Type is the first data cell.
    first = table.locator("tbody tr").first
    expect(first.locator('th[scope="row"] [data-testid="provider-card"]')).to_have_count(1)
    expect(table.get_by_role("rowheader", name="Alpha")).to_have_count(1)
    expect(first.locator("td").nth(0).locator(".badge.badge--mock")).to_have_count(1)
    look = first.evaluate(
        """(tr) => { const s = (el) => { const c = getComputedStyle(el);
            return [c.textAlign, c.paddingTop, c.paddingLeft, c.borderBottomWidth,
                    c.verticalAlign]; };
          return { th: s(tr.querySelector('th')), td: s(tr.querySelector('td')),
                   thWeight: getComputedStyle(tr.querySelector('th')).fontWeight }; }"""
    )
    assert look["th"] == look["td"], look
    assert look["thWeight"] == "400", look
    # Pre-accepted deviations D1/D2: no Status column, no health banner.
    expect(table.get_by_role("columnheader", name="Status")).to_have_count(0)
    expect(page.locator(".area-admin .banner-error:visible")).to_have_count(0)
    _lists.expect_none_selected(page, "settings/providers")


def test_used_by_reads_a_dash_until_agents_load(app_with_provider: SeededApp, page: Page) -> None:
    """While the agents list has never loaded (here: every read fails), the
    "Used by" cells read "—", never "0 agents" (A23)."""
    page.route("**/api/agents", lambda route: route.fulfill(status=500, body="{}"))
    _nav.goto_settled(page, app_with_provider.base_url, "settings/providers")
    expect(_lists.providers_table(page).locator("tbody tr")).to_have_count(1, timeout=8000)
    assert _row_texts(page) == [["mock", "mock", "—"]]


def test_long_provider_name_ellipsizes(app_with_provider: SeededApp, page: Page) -> None:
    name = "A provider with a very long name " * 6
    seed_mock_provider(app_with_provider.base_url, name=name.strip())
    page.set_viewport_size({"width": 1024, "height": 768})
    _ready(page, app_with_provider.base_url, "settings/providers")
    link = _lists.list_row(page, "settings/providers", name.strip())
    expect(link).to_be_visible(timeout=8000)
    m = link.evaluate(
        """(a) => { const t = a.closest('table'); const list = t.parentElement;
          return { sw: a.scrollWidth, cw: a.clientWidth, cell: a.parentElement.clientWidth,
                   table: t.getBoundingClientRect().right, list: list.getBoundingClientRect().right,
                   overflow: getComputedStyle(a).textOverflow }; }"""
    )
    assert m["overflow"] == "ellipsis", m
    assert m["sw"] > m["cw"], m  # truncated, not wrapped or overflowing
    assert m["table"] <= m["list"] + 0.5, m


# ── AC2: a provider opens below the table ──────────────────────────────────


def test_provider_opens_below_the_table_with_focus_and_visibility(
    app_with_provider: SeededApp, page: Page
) -> None:
    """At 1440x900 with 6 providers, opening the last row keeps the table above
    the editor, the selected row and the editor header both in the viewport,
    and focus on the editor's title (an h2)."""
    base = app_with_provider.base_url
    for name in ("p2", "p3", "p4", "p5", "zz last"):
        seed_mock_provider(base, name=name)
    page.set_viewport_size({"width": 1440, "height": 900})
    _ready(page, base, "settings/providers")
    expect(_lists.providers_table(page).locator("tbody tr")).to_have_count(6, timeout=8000)
    _lists.open_item(page, "settings/providers", "zz last")
    expect(page.locator(ITEM_TITLE)).to_have_text("zz last", timeout=8000)
    expect(_lists.providers_table(page)).to_be_visible()
    _lists.expect_selected(page, "settings/providers", "zz last")
    expect(page.locator(ITEM_TITLE)).to_be_focused()
    table_bottom = _lists.providers_table(page).bounding_box()
    header = page.locator(".area-admin .settings-item .editor-header").bounding_box()
    assert table_bottom and header and header["y"] >= table_bottom["y"] + table_bottom["height"]
    assert _in_viewport(page, "tr.providers-table-row.is-selected")
    assert _in_viewport(page, ".area-admin .settings-item .editor-header")
    # The item header: breadcrumb "Settings / Providers", no Back, one editor.
    expect(page.locator(".area-admin .settings-item .editor-breadcrumb")).to_have_text(
        "Settings / Providers"
    )
    # The root link is underlined at rest (not colour alone; the flight-end review).
    crumb_link = page.locator(".area-admin .settings-item .editor-breadcrumb-link")
    assert crumb_link.evaluate("(a) => getComputedStyle(a).textDecorationLine") == "underline"
    expect(page.locator(".back-btn")).to_have_count(0)
    expect(page.locator(".area-admin .settings-item .editor-header")).to_have_count(1)


def test_dirty_provider_and_another_row_asks_once(app_with_provider: SeededApp, page: Page) -> None:
    ids = _seed_three(app_with_provider)
    _ready(page, app_with_provider.base_url, f"settings/providers/{_nav.seg(ids['Alpha'])}")
    expect(page.locator("#pf-name")).to_have_value("Alpha", timeout=8000)
    page.locator("#pf-name").fill("Alpha edited")
    _lists.list_row(page, "settings/providers", "Bravo").click()
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(STAY).click()
    expect(page.locator(DIALOG)).to_have_count(0)
    expect(page.locator("#pf-name")).to_have_value("Alpha edited")
    _nav.expect_route(page, f"settings/providers/{_nav.seg(ids['Alpha'])}")
    _lists.expect_selected(page, "settings/providers", "Alpha")
    _lists.list_row(page, "settings/providers", "Bravo").click()
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(CONTINUE).click()
    expect(page.locator("#pf-name")).to_have_value("Bravo", timeout=8000)
    page.wait_for_timeout(300)
    expect(page.locator(DIALOG)).to_have_count(0)
    _lists.expect_selected(page, "settings/providers", "Bravo")
    # The title takes focus last (after nav.js's Continue focus on <main>).
    expect(page.locator(ITEM_TITLE)).to_be_focused()


def test_clicking_the_open_provider_row_does_not_ask_or_remount(
    app_with_provider: SeededApp, page: Page
) -> None:
    """The open item's own row is not a navigation: a dirty editor is neither
    asked about nor re-mounted; the editor is brought into view and focused."""
    _ready(
        page,
        app_with_provider.base_url,
        f"settings/providers/{_nav.seg(app_with_provider.provider_id)}",
    )
    expect(page.locator("#pf-name")).to_have_value("mock", timeout=8000)
    _mark(page, ".area-admin .settings-item .editor-header", "kept")
    page.locator("#pf-name").fill("mock edited")
    _lists.list_row(page, "settings/providers", "mock").click()
    page.wait_for_timeout(300)
    expect(page.locator(DIALOG)).to_have_count(0)
    expect(page.locator("#pf-name")).to_have_value("mock edited")
    assert _mark_of(page, ".area-admin .settings-item .editor-header") == "kept"
    expect(page.locator(ITEM_TITLE)).to_be_focused()


def test_breadcrumb_closes_the_provider_and_focuses_its_row(
    app_with_provider: SeededApp, page: Page
) -> None:
    ids = _seed_three(app_with_provider)
    _ready(page, app_with_provider.base_url, f"settings/providers/{_nav.seg(ids['Bravo'])}")
    expect(page.locator(ITEM_TITLE)).to_have_text("Bravo", timeout=8000)
    link = _lists.breadcrumb_link(page)
    expect(link).to_have_text("Providers")
    expect(link).to_have_attribute("href", _nav.href("settings/providers"))
    before = page.evaluate("history.length")
    _lists.close_item(page)
    _nav.expect_route(page, "settings/providers")
    expect(page.locator(ITEM_TITLE)).to_have_count(0, timeout=5000)
    expect(_lists.list_row(page, "settings/providers", "Bravo")).to_be_focused()
    _lists.expect_none_selected(page, "settings/providers")
    assert page.evaluate("history.length") == before + 1  # a pushed close
    # Dirty: asks once; Stay focuses the link back, Continue closes.
    _lists.open_item(page, "settings/providers", "Bravo")
    page.locator("#pf-name").fill("Bravo edited")
    _lists.close_item(page)
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(STAY).click()
    expect(_lists.breadcrumb_link(page)).to_be_focused()
    _lists.close_item(page)
    page.locator(CONTINUE).click()
    expect(page.locator(ITEM_TITLE)).to_have_count(0, timeout=5000)
    expect(_lists.list_row(page, "settings/providers", "Bravo")).to_be_focused()
    assert page.evaluate("App.nav.isDirty()") is False


# ── AC3: create, Cancel and delete ─────────────────────────────────────────


def test_add_provider_opens_the_form_below_and_save_create_keeps_it(
    app_with_provider: SeededApp, page: Page
) -> None:
    _ready(page, app_with_provider.base_url, "settings/providers")
    expect(_lists.providers_table(page)).to_be_visible(timeout=8000)
    page.locator('[data-testid="new-provider-btn"]').click()
    _nav.expect_route(page, "settings/providers/~new")
    expect(page.locator(ITEM_TITLE)).to_have_text("New Provider", timeout=8000)
    expect(_lists.providers_table(page)).to_be_visible()
    expect(page.locator(ITEM_TITLE)).to_be_focused()
    page.locator("#pf-name").fill("Made provider")
    page.locator("#pf-type").select_option("mock")
    before = page.evaluate("history.length")
    page.locator('[data-testid="save-provider-btn"]').click()
    page.wait_for_function(
        "p => location.hash.startsWith(p) && !location.hash.endsWith('/~new')",
        arg=_nav.href("settings/providers") + "/",
        timeout=8000,
    )
    expect(page.locator(ITEM_TITLE)).to_have_text("Made provider", timeout=8000)
    expect(page.locator(ANNOUNCER)).to_have_text("Settings — Providers — Made provider")
    _lists.expect_selected(page, "settings/providers", "Made provider")
    new_id = _lists.list_row(page, "settings/providers", "Made provider").get_attribute("data-id")
    _nav.expect_route(page, f"settings/providers/{new_id}")
    assert page.evaluate("history.length") == before
    # The editor is now in edit mode (Test, Danger Zone), still under the table.
    expect(page.locator('[data-testid="test-connection-btn"]')).to_be_visible()
    expect(_lists.providers_table(page)).to_be_visible()
    expect(page.locator(UNSAVED)).to_have_text("")
    assert page.evaluate("App.nav.isDirty()") is False
    # The next row click opens with no prompt.
    _lists.list_row(page, "settings/providers", "mock").click()
    expect(page.locator(ITEM_TITLE)).to_have_text("mock", timeout=8000)
    expect(page.locator(DIALOG)).to_have_count(0)


def test_cancel_on_create_returns_to_the_root_focusing_add_provider(
    app_with_provider: SeededApp, page: Page
) -> None:
    _ready(page, app_with_provider.base_url, "settings/providers")
    page.locator('[data-testid="new-provider-btn"]').click()
    expect(page.locator(ITEM_TITLE)).to_have_text("New Provider", timeout=8000)
    page.locator("#pf-name").fill("never saved")
    before = page.evaluate("history.length")
    page.locator('[data-testid="cancel-provider-btn"]').click()
    _nav.expect_route(page, "settings/providers")
    expect(page.locator(ITEM_TITLE)).to_have_count(0, timeout=5000)
    expect(page.locator('[data-testid="new-provider-btn"]')).to_be_focused()
    expect(page.locator(DIALOG)).to_have_count(0)
    assert page.evaluate("App.nav.isDirty()") is False
    expect(_lists.list_row(page, "settings/providers", "never saved")).to_have_count(0)
    # Replaced, not pushed: Back never lands on the discarded create form.
    assert page.evaluate("history.length") == before
    page.go_back()
    _nav.expect_route(page, "settings/providers")
    expect(page.locator(ITEM_TITLE)).to_have_count(0)


@pytest.mark.parametrize(
    ("victim", "focus"),
    [("Bravo", "mock"), ("mock", "Bravo")],
    ids=["middle-focuses-next", "last-focuses-previous"],
)
def test_delete_focuses_the_nearest_row(
    app_with_provider: SeededApp, page: Page, victim: str, focus: str
) -> None:
    """Delete replaces to the root and focuses the next row, else the previous
    (rows sort A-Z: Alpha, Bravo, mock; no agents use them, so the delete is
    not hard-blocked)."""
    base = app_with_provider.base_url
    ids = {"mock": app_with_provider.provider_id}
    ids["Alpha"] = seed_mock_provider(base, name="Alpha")
    ids["Bravo"] = seed_mock_provider(base, name="Bravo")
    _ready(page, base, f"settings/providers/{_nav.seg(ids[victim])}")
    expect(page.locator(ITEM_TITLE)).to_have_text(victim, timeout=8000)
    delete = page.locator('[data-testid="delete-provider-btn"]')
    delete.click()
    expect(delete).to_have_class(re.compile(r"\bconfirm-delete\b"), timeout=5000)
    delete.click()
    _nav.expect_route(page, "settings/providers", timeout=8000)
    expect(page.locator(ITEM_TITLE)).to_have_count(0, timeout=5000)
    expect(_lists.list_row(page, "settings/providers", victim)).to_have_count(0)
    expect(_lists.list_row(page, "settings/providers", focus)).to_be_focused()


# ── AC4: Built-in tools ─────────────────────────────────────────────────────


def test_tool_opens_below_the_list_scrolled_and_focused(app_clean: str, page: Page) -> None:
    page.set_viewport_size({"width": 1440, "height": 900})
    _ready(page, app_clean, "settings/tools")
    _lists.open_tool(page, "web_search")
    expect(page.locator(ITEM_TITLE)).to_have_text("web_search", timeout=8000)
    tile = _lists.list_row(page, "settings/tools", "web_search")
    expect(tile).to_be_visible()
    _lists.expect_selected(page, "settings/tools", "web_search")
    expect(tile).to_have_class(re.compile(r"\bactive\b"))
    grid = page.locator("#tools-panel-web").bounding_box()
    header = page.locator(".area-admin .settings-item .editor-header").bounding_box()
    assert grid and header and header["y"] >= grid["y"] + grid["height"]
    expect(page.locator(ITEM_TITLE)).to_be_focused()
    assert _in_viewport(page, ".area-admin .settings-item .editor-header")
    expect(page.locator(".area-admin .settings-item .editor-breadcrumb")).to_have_text(
        "Settings / Built-in tools"
    )
    expect(_lists.breadcrumb_link(page)).to_have_attribute("href", _nav.href("settings/tools"))
    expect(page.locator(".back-btn")).to_have_count(0)


def test_tool_toggle_never_navigates(app_clean: str, page: Page) -> None:
    _ready(page, app_clean, "settings/tools")
    page.locator('[data-testid="tab-web"]').click()
    toggle = _lists.tool_toggle(page, "http_request")
    expect(toggle).to_be_checked()
    before = page.evaluate("history.length")
    toggle.click()
    expect(toggle).not_to_be_disabled(timeout=5000)
    expect(toggle).not_to_be_checked()
    _nav.expect_route(page, "settings/tools")
    expect(page.locator(ITEM_TITLE)).to_have_count(0)
    assert page.evaluate("history.length") == before
    toggle.click()
    expect(toggle).not_to_be_disabled(timeout=5000)
    expect(toggle).to_be_checked()


def test_toggling_another_tool_keeps_the_open_editor_and_its_edit(
    app_clean: str, page: Page
) -> None:
    """With web_search open and dirty, toggling http_request refreshes the list
    and leaves the editor mounted (same node) with its edit and caption; the
    toggle keeps focus across the list re-render."""
    _ready(page, app_clean, "settings/tools/web_search")
    expect(page.locator(ITEM_TITLE)).to_have_text("web_search", timeout=8000)
    _mark(page, ".area-admin .settings-item .editor-header", "kept")
    page.locator('[data-field="search_backend"]').select_option("searxng")
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    toggle = _lists.tool_toggle(page, "http_request")
    toggle.click()
    expect(toggle).not_to_be_disabled(timeout=5000)
    expect(toggle).not_to_be_checked()
    expect(toggle).to_be_focused()
    assert _mark_of(page, ".area-admin .settings-item .editor-header") == "kept"
    expect(page.locator('[data-field="search_backend"]')).to_have_value("searxng")
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    _nav.expect_route(page, "settings/tools/web_search")
    _lists.expect_selected(page, "settings/tools", "web_search")
    assert page.evaluate("App.nav.isDirty()") is True


def test_toggling_the_open_tool_updates_its_enabled_control_in_place(
    app_clean: str, page: Page
) -> None:
    _ready(page, app_clean, "settings/tools/web_search")
    expect(page.locator(ITEM_TITLE)).to_have_text("web_search", timeout=8000)
    _mark(page, ".area-admin .settings-item .editor-header", "kept")
    enabled = page.locator('.area-admin .settings-item [data-field="enabled"]')
    expect(enabled).to_be_checked()
    toggle = _lists.tool_toggle(page, "web_search")
    toggle.click()
    expect(toggle).not_to_be_disabled(timeout=5000)
    expect(enabled).not_to_be_checked()
    # Saved state, not an edit: the editor stays clean, Cancel stays disabled.
    expect(page.locator(UNSAVED)).to_have_text("")
    expect(page.locator('[data-testid="cancel-tool-btn"]')).to_be_disabled()
    assert _mark_of(page, ".area-admin .settings-item .editor-header") == "kept"
    toggle.click()
    expect(toggle).not_to_be_disabled(timeout=5000)
    expect(enabled).to_be_checked()


def test_deep_link_to_a_non_default_category(app_clean: str, page: Page) -> None:
    _ready(page, app_clean, "settings/tools/send_to_platform_channel")
    expect(page.locator(ITEM_TITLE)).to_have_text("send_to_platform_channel", timeout=8000)
    expect(page.locator('[data-testid="tab-connectors"]')).to_have_attribute(
        "aria-selected", "true"
    )
    expect(page.locator("#tools-panel-connectors")).to_be_visible()
    _lists.expect_selected(page, "settings/tools", "send_to_platform_channel")
    expect(page.locator(ITEM_TITLE)).to_be_focused()
    # A later toggle re-render keeps the tab the user chose since.
    page.locator('[data-testid="tab-web"]').click()
    toggle = _lists.tool_toggle(page, "fetch_url")
    toggle.click()
    expect(toggle).not_to_be_disabled(timeout=5000)
    expect(page.locator('[data-testid="tab-web"]')).to_have_attribute("aria-selected", "true")
    toggle.click()
    expect(toggle).not_to_be_disabled(timeout=5000)


def test_breadcrumb_closes_the_tool_and_focuses_its_name_link(app_clean: str, page: Page) -> None:
    _ready(page, app_clean, "settings/tools/fetch_url")
    expect(page.locator(ITEM_TITLE)).to_have_text("fetch_url", timeout=8000)
    _lists.close_item(page)
    _nav.expect_route(page, "settings/tools")
    expect(page.locator(ITEM_TITLE)).to_have_count(0, timeout=5000)
    expect(_lists.item_link(page, "settings/tools", "fetch_url")).to_be_focused()
    _lists.expect_none_selected(page, "settings/tools")


# ── AC5: the unsaved caption ────────────────────────────────────────────────


def test_unsaved_caption_on_the_provider_editor(app_with_provider: SeededApp, page: Page) -> None:
    _ready(
        page,
        app_with_provider.base_url,
        f"settings/providers/{_nav.seg(app_with_provider.provider_id)}",
    )
    caption = page.locator(UNSAVED)
    expect(caption).to_have_text("", timeout=8000)
    expect(caption).to_have_attribute("role", "status")
    _mark(page, UNSAVED, "same")
    page.locator("#pf-name").fill("mock edited")
    expect(caption).to_have_text("Unsaved changes")
    page.locator('[data-testid="cancel-provider-btn"]').click()
    expect(caption).to_have_text("")
    page.locator("#pf-name").fill("mock saved")
    expect(caption).to_have_text("Unsaved changes")
    page.locator('[data-testid="save-provider-btn"]').click()
    expect(caption).to_have_text("", timeout=8000)
    assert _mark_of(page, UNSAVED) == "same"


def test_unsaved_caption_on_the_tool_editor_survives_cancel(app_clean: str, page: Page) -> None:
    """The tool editor's Cancel re-mounts the form; the caption is the SAME
    live-region node before and after."""
    _ready(page, app_clean, "settings/tools/web_search")
    caption = page.locator(UNSAVED)
    expect(caption).to_have_text("", timeout=8000)
    _mark(page, UNSAVED, "same")
    page.locator('[data-field="search_backend"]').select_option("searxng")
    expect(caption).to_have_text("Unsaved changes")
    page.locator('[data-testid="cancel-tool-btn"]').click()
    expect(caption).to_have_text("")
    assert _mark_of(page, UNSAVED) == "same"
    page.locator('[data-field="search_backend"]').select_option("searxng")
    page.locator('input[data-field="searxng_base_url"]').fill("https://searx.example.org")
    expect(caption).to_have_text("Unsaved changes")
    page.locator('[data-testid="save-tool-btn"]').click()
    expect(caption).to_have_text("", timeout=8000)
    assert _mark_of(page, UNSAVED) == "same"


# ── Focus discipline and keyboard ───────────────────────────────────────────


def test_store_notification_and_refresh_never_move_focus(
    app_with_provider: SeededApp, page: Page
) -> None:
    """A providers / agents store load, and the area's _refresh, re-render the
    table body only: the editor is not re-mounted and focus stays put."""
    ids = _seed_three(app_with_provider)
    _ready(
        page,
        app_with_provider.base_url,
        f"settings/providers/{_nav.seg(app_with_provider.provider_id)}",
    )
    name = page.locator("#pf-name")
    expect(name).to_have_value("mock", timeout=8000)
    _mark(page, ".area-admin .settings-item .editor-header", "kept")
    name.focus()
    page.evaluate(
        "async () => { await App.store.get('providers', {force: true});"
        " await App.store.get('agents', {force: true}); }"
    )
    page.evaluate("() => App.areas.find((a) => a.id === 'admin')._refresh()")
    _nav.wait_settled(page)
    expect(name).to_be_focused()
    assert _mark_of(page, ".area-admin .settings-item .editor-header") == "kept"
    _lists.expect_selected(page, "settings/providers", "mock")
    # A focused row link keeps focus across a table re-render too (a renamed
    # provider changes the rows, so the body is rebuilt).
    r = httpx.put(
        f"{app_with_provider.base_url}/api/providers/{ids['Bravo']}",
        json={"name": "Bravo two"},
        headers=auth_headers_for(app_with_provider.base_url),
        timeout=5.0,
    )
    assert r.status_code == 200, r.text
    _lists.list_row(page, "settings/providers", "Alpha").focus()
    page.evaluate("async () => { await App.store.get('providers', {force: true}); }")
    expect(_lists.list_row(page, "settings/providers", "Bravo two")).to_be_visible(timeout=8000)
    expect(_lists.list_row(page, "settings/providers", "Alpha")).to_be_focused()
    expect(name).to_have_value("mock")


def test_tab_order_runs_through_the_name_links_then_into_the_editor(
    app_with_provider: SeededApp, page: Page
) -> None:
    ids = _seed_three(app_with_provider)
    _ready(page, app_with_provider.base_url, f"settings/providers/{_nav.seg(ids['mock'])}")
    expect(page.locator(ITEM_TITLE)).to_be_focused(timeout=8000)
    page.locator('[data-testid="new-provider-btn"]').focus()
    seen = []
    for _ in range(5):
        page.keyboard.press("Tab")
        seen.append(_focused(page))
    assert [f["text"] for f in seen[:3]] == ["Alpha", "Bravo", "mock"], seen
    assert all(f["testid"] == "provider-card" for f in seen[:3]), seen
    # Then into the editor: its breadcrumb link, then its first control.
    assert seen[3]["testid"] == "editor-breadcrumb-link", seen


# ── Forced colours (flight-end review, WCAG 1.4.11) ─────────────────────────

_FORCED_PROBE_JS = """() => {
  const probe = document.createElement('span');
  probe.style.color = 'Highlight';
  document.body.appendChild(probe);
  const highlight = getComputedStyle(probe).color;
  probe.remove();
  const edge = (el) => { const s = getComputedStyle(el);
    return [s.borderTopWidth, s.borderTopStyle, s.borderTopColor === highlight]; };
  const rows = [...document.querySelectorAll('tr.providers-table-row')].map((tr) => ({
    selected: tr.classList.contains('is-selected'), cells: [...tr.cells].map(edge)}));
  return {rows};
}"""

_TILE_PROBE_JS = """() => {
  const probe = document.createElement('span');
  probe.style.color = 'Highlight';
  document.body.appendChild(probe);
  const highlight = getComputedStyle(probe).color;
  probe.remove();
  return [...document.querySelectorAll('.area-admin .tool-tile')]
    .filter((t) => t.offsetParent !== null)
    .map((t) => { const s = getComputedStyle(t);
      return {active: t.classList.contains('active'),
              outline: s.outlineWidth + ' ' + s.outlineStyle,
              border: s.borderTopColor === highlight, outlineHi: s.outlineColor === highlight}; });
}"""


def test_forced_colors_keep_the_open_provider_and_tool_distinct(
    app_with_provider: SeededApp, page: Page
) -> None:
    """Chromium forced-colours emulation (WebKit has none in Playwright): the
    wash is dropped, so the open provider's row cells carry a 2px Highlight
    rule above (and below) that no other row has, and the open tool's tile a
    Highlight border plus a 1px Highlight outline that no other tile has."""
    ids = _seed_three(app_with_provider)
    # Reduced motion collapses the tile's border-color transition, so the
    # probe reads the settled colour.
    page.emulate_media(forced_colors="active", reduced_motion="reduce")
    _ready(page, app_with_provider.base_url, f"settings/providers/{_nav.seg(ids['Bravo'])}")
    expect(page.locator(ITEM_TITLE)).to_have_text("Bravo", timeout=8000)
    _lists.expect_selected(page, "settings/providers", "Bravo")
    rows = page.evaluate(_FORCED_PROBE_JS)["rows"]
    assert [r["selected"] for r in rows] == [False, True, False], rows
    for row in rows:
        for cell in row["cells"]:
            if row["selected"]:
                assert cell == ["2px", "solid", True], rows
            else:
                assert cell[0] == "0px", rows

    _lists.open_settings_page(page, "tools")
    _lists.open_tool(page, "web_search")
    expect(page.locator(ITEM_TITLE)).to_have_text("web_search", timeout=8000)
    tiles = page.evaluate(_TILE_PROBE_JS)
    active = [t for t in tiles if t["active"]]
    assert len(active) == 1, tiles
    assert active[0] == {"active": True, "outline": "1px solid", "border": True, "outlineHi": True}
    for tile in tiles:
        if not tile["active"]:
            assert tile["outline"].endswith("none") and not tile["border"], tiles
