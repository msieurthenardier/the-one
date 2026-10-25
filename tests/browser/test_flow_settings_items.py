"""Settings item pages keep their list visible (M25 F3 leg 5b; flight DD7, DD2, DD8).

Built-in tools keeps its tabs and tiles, the tool NAME is the item link and the
tool editor opens below the list, with the breadcrumb ("Settings / Built-in
tools"), no Back, and the unsaved caption: link, selection, toggle isolation,
deep-link category, scroll and focus, the unsaved caption and the forced-colours
cue. (The provider half of this file moved to ``test_flow_provider_items.py``
when providers moved to Library, sortie 02; Settings has no Providers page now.)
Settings lane (``test_flow_settings_*`` in ``scripts/run-tests.sh``).
"""

from __future__ import annotations

import re

import pytest
from browser import _lists, _nav
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

DIALOG = '[data-testid="confirm-dialog-overlay"]'
STAY = '[data-testid="modal-cancel-btn"]'
CONTINUE = '[data-testid="modal-confirm-btn"]'
ANNOUNCER = '[data-testid="route-announcer"]'
ITEM_TITLE = ".area-admin .settings-item .editor-title"
UNSAVED = '.area-admin .settings-item [data-testid="editor-unsaved"]'


# ── helpers ─────────────────────────────────────────────────────────────────


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


# ── Built-in tools ─────────────────────────────────────────────────────


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
    toggle.click(force=True)
    expect(toggle).not_to_be_disabled(timeout=5000)
    expect(toggle).not_to_be_checked()
    _nav.expect_route(page, "settings/tools")
    expect(page.locator(ITEM_TITLE)).to_have_count(0)
    assert page.evaluate("history.length") == before
    toggle.click(force=True)
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
    toggle.click(force=True)
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
    toggle.click(force=True)
    expect(toggle).not_to_be_disabled(timeout=5000)
    expect(enabled).not_to_be_checked()
    # Saved state, not an edit: the editor stays clean, Cancel stays disabled.
    expect(page.locator(UNSAVED)).to_have_text("")
    expect(page.locator('[data-testid="cancel-tool-btn"]')).to_be_disabled()
    assert _mark_of(page, ".area-admin .settings-item .editor-header") == "kept"
    toggle.click(force=True)
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
    toggle.click(force=True)
    expect(toggle).not_to_be_disabled(timeout=5000)
    expect(page.locator('[data-testid="tab-web"]')).to_have_attribute("aria-selected", "true")
    toggle.click(force=True)
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


# ── Forced colours (flight-end review, WCAG 1.4.11) ─────────────────────────

_TILE_PROBE_JS = """(sel) => {
  const probe = document.createElement('span');
  probe.style.color = 'Highlight';
  document.body.appendChild(probe);
  const highlight = getComputedStyle(probe).color;
  probe.remove();
  return [...document.querySelectorAll(sel)]
    .filter((t) => t.offsetParent !== null)
    .map((t) => { const s = getComputedStyle(t);
      return {active: t.classList.contains('active'),
              outline: s.outlineWidth + ' ' + s.outlineStyle,
              border: s.borderTopColor === highlight, outlineHi: s.outlineColor === highlight}; });
}"""


def test_forced_colors_keep_the_open_tool_distinct(app_clean: str, page: Page) -> None:
    """Chromium forced-colours emulation (WebKit has none in Playwright): the
    wash is dropped, so the open tool's tile carries a Highlight border plus a
    1px Highlight outline that no other tile has (the shared
    ``.entity-tile.active`` forced-colours cue)."""
    # Reduced motion collapses the tile's border-color transition, so the
    # probe reads the settled colour.
    page.emulate_media(forced_colors="active", reduced_motion="reduce")
    _ready(page, app_clean, "settings/tools")
    _lists.open_tool(page, "web_search")
    expect(page.locator(ITEM_TITLE)).to_have_text("web_search", timeout=8000)
    tiles = page.evaluate(_TILE_PROBE_JS, ".area-admin .tool-tile")
    active = [t for t in tiles if t["active"]]
    assert len(active) == 1, tiles
    assert active[0] == {"active": True, "outline": "1px solid", "border": True, "outlineHi": True}
    for tile in tiles:
        if not tile["active"]:
            assert tile["outline"].endswith("none") and not tile["border"], tiles
