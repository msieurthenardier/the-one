# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""The Settings nav, the General split and its redirects (M25 F3 leg 5a, DD6, DD13).

Settings' column is one ``App.ui.navGroups`` (testid ``settings-nav``): a
``<nav aria-label="Settings">`` with the heading "Settings" and grouped plain
links (``settings-nav-{section}``), reference spec section 8.1. The former single
General page is three pages with their own routes (Appearance, Prompts,
Encryption); ``#settings/general`` (any suffix) is an alias for
``#settings/appearance``, and the legacy ``#admin``, ``#admin/system`` and
``#admin/general`` redirect there directly.

* AC1 -- nav structure: groups in order, links, ``aria-current`` (exactly one,
  following navigation and item routes), 28px items, the heading aligned with
  the item text (A3), 260px wide at 1440 and 1024 (A2), in Chromium AND WebKit;
  three groups without dev mode;
* AC2 -- each link navigates; the three General pages each render one block and
  one ``h1`` with their existing controls; the theme flip on Appearance;
* AC3 -- redirects: ``settings/general`` cold and in-app, its suffix dropped,
  the legacy hashes directly (no intermediate history write), ``lastRoute``
  never ``settings/general``, the rail's first-use href;
* AC4 -- every Settings page has a page header with the board's label and no
  second ``h1``, item pages included (an open provider, its ``~new`` form, an
  open tool: the editor title is an ``h2``, the flight-end review);
* the leave guard: a dirty provider editor plus a nav-link click asks once.

Falls in the ``settings`` lane (``test_flow_admin_*`` in ``scripts/run-tests.sh``).
"""

from __future__ import annotations

import json
import re

import pytest
from browser import _lists, _nav
from browser.conftest import credentialed_context
from browser.seeders import SeededApp
from playwright.sync_api import Page, Route, expect

pytestmark = pytest.mark.browser

DIALOG = '[data-testid="confirm-dialog-overlay"]'

# Reference spec section 8.1, in order. Developer is dev-mode only.
GROUPS = [
    ("General", ["appearance", "prompts", "encryption"]),
    ("Models", ["providers"]),
    ("Defaults for agents", ["tools", "knowledge-indexing"]),
    ("Developer", ["design-language"]),
]

# The nav as rendered: [{caption, links: [[text, href, testid, tag]]}].
_NAV_SHAPE_JS = """() => {
  const nav = document.querySelector('[data-testid="settings-nav"]');
  return {
    tag: nav.tagName, label: nav.getAttribute('aria-label'),
    heading: nav.querySelector('h2').textContent,
    groups: Array.from(nav.querySelectorAll('.ui-nav-groups-group')).map((g) => ({
      caption: g.querySelector('.ui-nav-groups-caption').textContent,
      links: Array.from(g.querySelectorAll('li > *')).map((a) => [
        a.textContent, a.getAttribute('href'), a.getAttribute('data-testid'), a.tagName]),
    })),
    current: Array.from(nav.querySelectorAll('[aria-current]')).map((a) => [a.getAttribute('data-testid'), a.getAttribute('aria-current')]),
    host: nav.parentElement.className,
    panel: nav.parentElement.parentElement.className,
    oldWrapper: document.querySelectorAll('.admin-section-nav').length,
  };
}"""

# Geometry of the column at the current viewport.
_GEOMETRY_JS = """() => {
  const aside = document.getElementById('app-sidebar');
  const nav = document.querySelector('[data-testid="settings-nav"]');
  const host = nav.parentElement;
  const textLeft = (el) => { const r = document.createRange(); r.selectNodeContents(el); return r.getBoundingClientRect().left; };
  const a = aside.getBoundingClientRect();
  const hs = getComputedStyle(host);
  const links = Array.from(nav.querySelectorAll('a'));
  const last = links[links.length - 1].getBoundingClientRect();
  return {
    asideW: a.width, asideLeft: a.left, asideBottom: a.bottom, asidePadTop: getComputedStyle(aside).paddingTop,
    hostPad: hs.padding, hostOverflowY: hs.overflowY,
    headingText: textLeft(nav.querySelector('h2')),
    itemText: links.map(textLeft),
    itemH: links.map((l) => l.getBoundingClientRect().height),
    lastBottom: last.bottom, lastRight: last.right, asideRight: a.right,
  };
}"""


def _expected_links(groups):
    return [
        {
            "caption": caption,
            "links": [
                [
                    _lists.SETTINGS_PAGE_TITLES[s],
                    _nav.href(f"settings/{s}"),
                    f"settings-nav-{s}",
                    "A",
                ]
                for s in sections
            ],
        }
        for caption, sections in groups
    ]


def _active_panel_h1s(page: Page) -> list[str]:
    return page.evaluate(
        "() => Array.from(document.querySelectorAll('.content-panel.active h1')).map((h) => h.textContent)"
    )


# ── AC1: structure, selection, geometry ──────────────────────────────────────


def test_settings_nav_groups_links_heading_and_mount(app_clean: str, page: Page) -> None:
    _nav.goto(page, app_clean, "settings/appearance")
    expect(_lists.settings_nav(page)).to_be_visible(timeout=8000)
    shape = page.evaluate(_NAV_SHAPE_JS)
    assert shape["tag"] == "NAV" and shape["label"] == "Settings", shape
    assert shape["heading"] == "Settings", shape
    assert shape["groups"] == _expected_links(GROUPS), shape["groups"]
    assert shape["current"] == [["settings-nav-appearance", "page"]], shape
    # Mounted on a child of the sidebar panel, never the panel itself; the
    # former <nav class="admin-section-nav"> wrapper is gone.
    assert shape["host"] == "admin-settings-nav", shape
    assert "sidebar-panel" in shape["panel"] and "area-admin" in shape["panel"], shape
    assert shape["oldWrapper"] == 0, shape
    # Plain links: no click handler, roving tabindex or role overrides.
    links = _lists.settings_nav(page).locator("a")
    for k in range(links.count()):
        assert links.nth(k).get_attribute("tabindex") is None
        assert links.nth(k).get_attribute("role") is None


def test_settings_nav_without_dev_mode_has_three_groups(app_clean: str, page: Page) -> None:
    """Dev mode off: the Developer group (Design language) is absent."""

    def no_dev_mode(route: Route) -> None:
        response = route.fetch()
        body = response.json()
        body["dev_mode"] = False
        route.fulfill(response=response, body=json.dumps(body))

    page.route("**/api/config", no_dev_mode)
    _nav.goto(page, app_clean, "settings/appearance")
    expect(_lists.settings_nav(page)).to_be_visible(timeout=8000)
    assert page.evaluate("App.config.dev_mode") is False
    shape = page.evaluate(_NAV_SHAPE_JS)
    assert shape["groups"] == _expected_links(GROUPS[:3]), shape["groups"]
    expect(page.locator('[data-testid="settings-nav-design-language"]')).to_have_count(0)


@pytest.mark.parametrize(("width", "height"), [(1440, 900), (1024, 768)])
def test_settings_nav_geometry_in_both_engines(
    engine_browser, app_clean: str, width: int, height: int
) -> None:
    """Section 8.1 geometry: 260px column (A2), padding-top 0 with the 14px 10px
    column padding on the scrolling host, 28px items, and the heading's text
    aligned with the items' text at 20px from the column edge (A3)."""
    context = credentialed_context(
        engine_browser, app_clean, viewport={"width": width, "height": height}
    )
    page = context.new_page()
    try:
        _nav.goto(page, app_clean, "settings/appearance")
        expect(_lists.settings_nav(page)).to_be_visible(timeout=8000)
        page.evaluate("document.fonts.ready.then(() => true)")
        g = page.evaluate(_GEOMETRY_JS)
        assert g["asideW"] == 260, g
        assert g["asidePadTop"] == "0px", g
        assert g["hostPad"] == "14px 10px", g
        assert g["hostOverflowY"] == "auto", g
        assert all(abs(h - 28) <= 1 for h in g["itemH"]), g
        assert all(abs(x - g["headingText"]) <= 1 for x in g["itemText"]), g
        assert abs(g["headingText"] - (g["asideLeft"] + 20)) <= 1, g
        # The Developer group's link is inside the column, unclipped.
        assert g["lastBottom"] <= g["asideBottom"] + 0.5, g
        assert g["lastRight"] <= g["asideRight"] + 0.5, g
    finally:
        context.close()


def test_aria_current_follows_navigation_and_item_routes(
    app_with_provider: SeededApp, page: Page
) -> None:
    base = app_with_provider.base_url
    _nav.goto(page, base, "settings/appearance")
    _lists.expect_settings_selected(page, "appearance")
    # An item route marks its SECTION, never the item.
    _nav.goto(page, base, f"settings/providers/{_nav.seg(app_with_provider.provider_id)}")
    expect(page.locator("#pf-name")).to_be_visible(timeout=8000)
    _lists.expect_settings_selected(page, "providers")
    _nav.goto(page, base, "settings/tools/web_search")
    expect(page.locator(".editor-title")).to_have_text("web_search", timeout=8000)
    _lists.expect_settings_selected(page, "tools")
    # An intent from an item route moves the selection too.
    _lists.open_settings_page(page, "prompts")
    _lists.expect_settings_selected(page, "prompts")
    # Back and Forward follow.
    page.go_back()
    _nav.expect_route(page, "settings/tools/web_search")
    _lists.expect_settings_selected(page, "tools")
    page.go_forward()
    _nav.expect_route(page, "settings/prompts")
    _lists.expect_settings_selected(page, "prompts")


# ── AC2 + AC4: every link navigates; one page header and one h1 per page ─────


def test_each_link_opens_its_page_under_one_page_header(app_clean: str, page: Page) -> None:
    _nav.goto(page, app_clean, "settings/appearance")
    expect(_lists.settings_nav(page)).to_be_visible(timeout=8000)
    sections = [s for _, group in GROUPS for s in group]
    # Start from the last page so the first click is a real navigation.
    _lists.open_settings_page(page, sections[-1])
    for section in sections:
        _lists.open_settings_page(page, section)
        _lists.expect_settings_selected(page, section)
        title = _lists.SETTINGS_PAGE_TITLES[section]
        expect(page.locator(".content-panel.active .page-header")).to_have_count(1)
        assert _active_panel_h1s(page) == [title], section
        # No breadcrumb and no border on a Settings page header (section 4).
        header = page.locator(".content-panel.active .page-header")
        assert header.locator(".editor-breadcrumb").count() == 0
        assert header.evaluate("el => getComputedStyle(el).borderBottomStyle") == "none"


def _item_title_tag(page: Page) -> str | None:
    return page.evaluate(
        "() => { const t = document.querySelector('.content-panel.active .settings-item .editor-title');"
        " return t ? t.tagName : null; }"
    )


def test_settings_item_pages_keep_one_h1_with_an_h2_editor_title(
    app_with_provider: SeededApp, page: Page
) -> None:
    """Flight-end review (a): an open provider, the provider ``~new`` form and an
    open tool keep the page header's ``h1`` as the page's only one; the item
    editor's title is an ``h2`` (still the ``tabindex=-1`` focus target)."""
    base = app_with_provider.base_url
    item = page.locator(".content-panel.active .settings-item .editor-title")
    cases = (
        (f"settings/providers/{_nav.seg(app_with_provider.provider_id)}", "Providers", "mock"),
        ("settings/providers/~new", "Providers", "New Provider"),
        ("settings/tools/web_search", "Built-in tools", "web_search"),
    )
    for route, page_title, editor_title in cases:
        _nav.goto(page, base, route)
        expect(item).to_have_text(editor_title, timeout=8000)
        assert _active_panel_h1s(page) == [page_title], route
        assert _item_title_tag(page) == "H2", route
        expect(item).to_have_attribute("tabindex", "-1")
        expect(item).to_be_focused()


def test_general_pages_each_render_their_own_block(app_clean: str, page: Page) -> None:
    """Appearance, Prompts and Encryption: one block each, with the controls and
    test ids of the former General page's blocks, and nothing of the others."""
    blocks = page.locator(".content-panel.active .admin-system-section")
    theme = page.locator(".content-panel.active .admin-theme-toggle")
    prompt = page.locator('[data-testid="base-prompt-content"]')
    rotate = page.locator('[data-testid="rotate-key-btn"]')

    _nav.goto(page, app_clean, "settings/appearance")
    expect(_lists.settings_page_title(page)).to_have_text("Appearance", timeout=8000)
    expect(blocks).to_have_count(1)
    expect(theme.locator('[role="radio"]')).to_have_count(3)
    # The radiogroup is still named "Appearance": its aria-labelledby target
    # is now the page's h1.
    expect(page.get_by_role("radiogroup", name="Appearance")).to_be_visible()
    assert page.locator("#admin-appearance-heading").evaluate("el => el.tagName") == "H1"
    expect(prompt).to_have_count(0)
    expect(rotate).to_have_count(0)

    _lists.open_settings_page(page, "prompts")
    expect(blocks).to_have_count(1)
    expect(prompt).to_be_visible()
    expect(prompt).not_to_have_text("Loading…", timeout=8000)
    expect(theme).to_have_count(0)
    expect(rotate).to_have_count(0)

    _lists.open_settings_page(page, "encryption")
    expect(blocks).to_have_count(1)
    expect(rotate).to_be_visible()
    expect(rotate).to_contain_text("Rotate Encryption Key")
    expect(page.locator(".content-panel.active .banner-warning")).to_be_visible()
    expect(theme).to_have_count(0)
    expect(prompt).to_have_count(0)


def test_design_language_page_has_no_section_nav_sample(app_clean: str, page: Page) -> None:
    """AC5: the retired section nav left no sample on the Design language page;
    the navGroups demo (Library: lists and navigation) stands in for it."""
    _nav.goto(page, app_clean, "settings/design-language")
    surfaces = page.locator('.design-language-section[data-section="surfaces"]')
    expect(surfaces.locator(".list-item").first).to_be_visible(timeout=8000)
    assert (
        page.evaluate(
            "() => document.querySelectorAll('.content-panel.active [class*=\"section-nav\"]').length"
        )
        == 0
    )
    demo = page.locator('.design-language-section[data-section="uiLists"] .ui-nav-groups')
    expect(demo.first).to_be_visible()


def test_theme_flip_works_on_appearance(app_clean: str, page: Page) -> None:
    _nav.goto(page, app_clean, "settings/appearance")
    expect(_lists.settings_page_title(page)).to_have_text("Appearance", timeout=8000)
    html = page.locator("html")
    for pref, resolved in (("dark", "dark"), ("light", "light"), ("dark", "dark")):
        option = page.locator(f'.admin-theme-option[data-theme-pref="{pref}"]')
        option.click()
        expect(option).to_have_attribute("aria-checked", "true")
        expect(html).to_have_attribute("data-theme", resolved)
    auto = page.locator('.admin-theme-option[data-theme-pref="auto"]')
    auto.click()
    expect(auto).to_have_attribute("aria-checked", "true")
    # Auto follows the emulated colour scheme (the harness's light default).
    expect(html).to_have_attribute("data-theme", "light")


def test_providers_page_primary_action_is_add_provider(app_clean: str, page: Page) -> None:
    _nav.goto(page, app_clean, "settings/providers")
    header = page.locator(".content-panel.active .page-header")
    expect(header.locator(".page-title")).to_have_text("Providers", timeout=8000)
    action = header.locator('[data-testid="new-provider-btn"]')
    expect(action).to_have_text("Add provider")
    expect(action).to_have_class(re.compile(r"\bbtn-outlined-primary\b"))
    action.click()
    _nav.expect_route(page, "settings/providers/~new")


# ── AC3: redirects ───────────────────────────────────────────────────────────

# Every history write, so a redirect can be shown to write its target directly.
_RECORD_WRITES_JS = """
(() => {
  window.__writes = [];
  for (const kind of ['replaceState', 'pushState']) {
    const orig = history[kind].bind(history);
    history[kind] = function (state, title, url) {
      window.__writes.push({ kind, url: String(url) });
      return orig(state, title, url);
    };
  }
})();
"""


def _writes(page: Page) -> list[dict]:
    return page.evaluate("window.__writes")


def _assert_never_general(page: Page) -> None:
    writes = _writes(page)
    assert not [w for w in writes if "general" in w["url"]], writes
    assert page.evaluate("App.router.lastRoute('settings')") == "settings/appearance"
    assert page.evaluate("App.router.current().route") == "settings/appearance"


def test_settings_general_redirects_on_a_cold_load(app_clean: str, page: Page) -> None:
    """A cold load of the alias (any suffix dropped) boots on Appearance with one
    replaceState and no pushed entry. One server; a fresh page per route."""
    page.goto(app_clean)  # the fixture page's first goto lands the session cookie
    for route in ["settings/general", "settings/general/x", "settings/general/x/y"]:
        fresh = page.context.new_page()
        try:
            fresh.add_init_script(_RECORD_WRITES_JS)
            _nav.goto(fresh, app_clean, route)
            expect(_lists.settings_page_title(fresh)).to_have_text("Appearance", timeout=8000)
            _nav.expect_route(fresh, "settings/appearance")
            writes = _writes(fresh)
            assert writes[0]["kind"] == "replaceState", (route, writes)
            assert writes[0]["url"] == _nav.href("settings/appearance"), (route, writes)
            assert not [w for w in writes if w["kind"] == "pushState"], (route, writes)
            _lists.expect_settings_selected(fresh, "appearance")
            _assert_never_general(fresh)
        finally:
            fresh.close()


def test_settings_general_redirects_in_app(app_clean: str, page: Page) -> None:
    """In-app: an intent (go) pushes Appearance itself; a typed hash is rewritten
    in place (one entry, the typed one); Back returns to where the user was."""
    page.add_init_script(_RECORD_WRITES_JS)
    _nav.goto_settled(page, app_clean, "settings/providers")
    expect(_lists.settings_page_title(page)).to_have_text("Providers", timeout=8000)

    before = page.evaluate("history.length")
    assert page.evaluate("App.router.go('settings/general/x')") is True
    _nav.expect_route(page, "settings/appearance")
    expect(_lists.settings_page_title(page)).to_have_text("Appearance", timeout=5000)
    assert page.evaluate("history.length") == before + 1
    _assert_never_general(page)

    page.go_back()
    _nav.expect_route(page, "settings/providers")
    expect(_lists.settings_page_title(page)).to_have_text("Providers", timeout=5000)

    # A typed hash: the browser makes the entry, the router rewrites it in place
    # (replaceState only, straight to the target).
    page.evaluate("window.__writes = []")
    _nav.set_route(page, "settings/general")
    _nav.expect_route(page, "settings/appearance")
    expect(_lists.settings_page_title(page)).to_have_text("Appearance", timeout=5000)
    writes = _writes(page)
    assert writes and all(
        w == {"kind": "replaceState", "url": _nav.href("settings/appearance")} for w in writes
    ), writes
    _assert_never_general(page)
    page.go_back()
    _nav.expect_route(page, "settings/providers")


def test_legacy_general_hashes_redirect_directly(app_clean: str, page: Page) -> None:
    """The legacy forms go straight to Appearance: their one history write is the
    target, never ``settings/general`` (no chained redirect). One server; a fresh
    page per legacy form."""
    page.goto(app_clean)  # the fixture page's first goto lands the session cookie
    for legacy in ["admin", "admin/system", "admin/general"]:
        fresh = page.context.new_page()
        try:
            fresh.add_init_script(_RECORD_WRITES_JS)
            fresh.goto(f"{app_clean}/#" + legacy)  # legacy URL on purpose: proves the redirect
            expect(_lists.settings_page_title(fresh)).to_have_text("Appearance", timeout=8000)
            _nav.expect_route(fresh, "settings/appearance")
            writes = _writes(fresh)
            expected = {"kind": "replaceState", "url": _nav.href("settings/appearance")}
            assert writes[0] == expected, (legacy, writes)
            _assert_never_general(fresh)
            # A typed legacy hash after boot: rewritten in place, directly.
            assert fresh.evaluate("App.router.go('settings/providers')") is True
            expect(_lists.settings_page_title(fresh)).to_have_text("Providers", timeout=8000)
            fresh.evaluate("h => { window.__writes = []; location.hash = h; }", "#admin/general")
            _nav.expect_route(fresh, "settings/appearance")
            expect(_lists.settings_page_title(fresh)).to_have_text("Appearance", timeout=5000)
            writes = _writes(fresh)
            assert writes and all(w == expected for w in writes), (legacy, writes)
        finally:
            fresh.close()


def test_rail_first_use_and_last_route_are_appearance(app_clean: str, page: Page) -> None:
    """Before any Settings visit the rail's Settings href is the root,
    ``#settings/appearance``; after a visit to the alias the remembered route is
    Appearance, never ``settings/general``."""
    _nav.goto_settled(page, app_clean, "chats")
    rail = page.locator('[data-testid="rail-settings"]')
    expect(rail).to_have_attribute("href", _nav.href("settings/appearance"))
    assert page.evaluate("App.router.root('settings')") == "settings/appearance"
    assert page.evaluate("App.router.lastRoute('settings')") == "settings/appearance"
    rail.click()
    _nav.expect_route(page, "settings/appearance")
    expect(_lists.settings_page_title(page)).to_have_text("Appearance", timeout=8000)
    _lists.expect_settings_selected(page, "appearance")

    # Leave Settings from the alias, then come back through the rail.
    assert page.evaluate("App.router.go('settings/general')") is True
    assert page.evaluate("App.router.go('chats')") is True
    assert page.evaluate("App.router.lastRoute('settings')") == "settings/appearance"
    expect(rail).to_have_attribute("href", _nav.href("settings/appearance"))
    # A real page is remembered as itself.
    assert page.evaluate("App.router.go('settings/encryption')") is True
    assert page.evaluate("App.router.go('chats')") is True
    expect(rail).to_have_attribute("href", _nav.href("settings/encryption"))
    rail.click()
    _nav.expect_route(page, "settings/encryption")
    _lists.expect_settings_selected(page, "encryption")


# ── The leave guard through the nav ─────────────────────────────────────────


def test_dirty_provider_editor_and_a_nav_link_ask_once(
    app_with_provider: SeededApp, page: Page
) -> None:
    _nav.goto_settled(
        page,
        app_with_provider.base_url,
        f"settings/providers/{_nav.seg(app_with_provider.provider_id)}",
    )
    name = page.locator("#pf-name")
    expect(name).to_be_visible(timeout=8000)
    item_route = _nav.current_route(page)
    name.fill("dirty-edit")
    expect(page.locator('[data-testid="save-provider-btn"]')).to_be_enabled()

    link = _lists.settings_nav_link(page, "appearance")
    link.click()
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    # Stay: the edit, the route and the selection are kept.
    page.locator('[data-testid="modal-cancel-btn"]').click()
    expect(page.locator(DIALOG)).to_have_count(0)
    _nav.expect_route(page, item_route)
    expect(name).to_have_value("dirty-edit")
    _lists.expect_settings_selected(page, "providers")

    # Continue: one dialog only, then Appearance.
    link.click()
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator('[data-testid="modal-confirm-btn"]').click()
    _nav.expect_route(page, "settings/appearance")
    expect(_lists.settings_page_title(page)).to_have_text("Appearance", timeout=5000)
    page.wait_for_timeout(300)
    expect(page.locator(DIALOG)).to_have_count(0)
    _lists.expect_settings_selected(page, "appearance")
    assert page.evaluate("App.areas.find(a => a.id === 'admin')._dirty") is False
