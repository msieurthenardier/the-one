# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Rail and shell tests against the real app (M25 F2 L6, DD7).

Geometry and colour of the rail against reference spec section 2 (computed style,
both themes), the shell layout (flex row, landmarks, skip link, widths at 1024 and
1440), rail hrefs and restore, and the destination icons. Chromium only: the
engine-parametrized factory contract is ``test_ui_rail_contract.py``, and the WebKit
pass over the app shell is ``scripts/webkitgtk_probe.py``. Falls in the ``shared`` lane.

Waits are state-driven (route, element or attribute); no fixed sleeps.
"""

from __future__ import annotations

import httpx
import pytest
from browser import _chats, _nav
from browser._credential_registry import auth_headers_for
from browser.design_tokens import DARK, LIGHT
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

DESTS = ("chats", "agents", "library", "settings")


def _rgb(hex_: str) -> str:
    h = hex_.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgb({r}, {g}, {b})"


def _set_theme(page: Page, theme: str) -> None:
    page.evaluate(f"App.theme.set('{theme}')")
    page.wait_for_function(f"document.documentElement.getAttribute('data-theme') === '{theme}'")


def _rail(page: Page, dest: str):
    return page.locator(f'[data-testid="rail-{dest}"]')


def _hrefs(page: Page) -> dict[str, str | None]:
    return {d: _rail(page, d).get_attribute("href") for d in DESTS}


def _boot(page: Page, base: str, route: str = "chats") -> None:
    _nav.goto_settled(page, base, route)
    expect(_nav.destination_panel(page, route.split("/")[0])).to_be_visible(timeout=8000)
    expect(page.locator('.ui-rail-item[aria-current="page"]')).to_have_count(1, timeout=8000)


# ── Shell structure (AC3) ───────────────────────────────────────────────────


def test_top_bar_is_gone_and_the_shell_is_a_flex_row_with_a_rail(
    app_with_agent: SeededApp, page: Page
) -> None:
    _boot(page, app_with_agent.base_url)
    out = page.evaluate(
        """() => {
          const row = document.querySelector('.app-shell-row');
          return {
            topbar: (document.getElementById('app-topbar') ? 1 : 0) + document.querySelectorAll('[class*="app-picker"], [class*="app-brand"]').length,
            kids: Array.from(row.children).map((c) => c.id),
            display: getComputedStyle(row).display,
            railMount: document.getElementById('app-rail').firstElementChild.className,
            bodyKids: Array.from(document.body.children).filter((c) => c.tagName !== 'SCRIPT').map((c) => c.tagName + '.' + c.className),
            wordmark: document.body.textContent.indexOf('GleepGlorp AI') !== -1,
          };
        }"""
    )
    assert out["topbar"] == 0
    # M25 F4 L6 (DD7): the agent drawer's static slot follows <main>.
    assert out["kids"] == ["app-rail", "app-sidebar", "main-content", "chat-drawer"]
    assert out["display"] == "flex"
    assert out["railMount"] == "ui-rail"
    # The route announcer (live region, appended at router start) is the only
    # other body child.
    assert out["bodyKids"] == ["A.skip-link", "DIV.app-shell-row", "DIV.visually-hidden"]
    assert out["wordmark"] is False  # the wordmark is dropped; only the mark's alt remains
    expect(page.get_by_role("img", name="GleepGlorp AI")).to_have_count(1)


_LANDMARKS_JS = """() => Array.from(document.querySelectorAll('nav[aria-label], aside[aria-label], main[aria-label], [role=navigation][aria-label]'))
    .filter((n) => n.getClientRects().length)
    .map((n) => [n.getAttribute('role') || {NAV: 'navigation', ASIDE: 'complementary', MAIN: 'main'}[n.tagName], n.getAttribute('aria-label')])"""


def test_landmarks_and_aside_labels(app_with_agent: SeededApp, page: Page) -> None:
    base = app_with_agent.base_url
    _boot(page, base)
    expect(page.locator('nav[aria-label="Main"]')).to_have_count(1)
    expect(page.locator("main#main-content")).to_have_count(1)
    aside = page.locator("aside#app-sidebar")
    expect(aside).to_be_visible()
    expect(aside).to_have_attribute("aria-label", "Chats")
    # The agent drawer (M25 F4 L6, DD7): a complementary landmark after
    # <main>, hidden while idle (out of the tree), and named uniquely when
    # open (1280 is push mode: open by default).
    drawer = page.locator("aside#chat-drawer")
    expect(drawer).to_be_hidden()
    expect(page.get_by_role("complementary", name="This chat's agent")).to_have_count(0)
    _chats.start_chat(page, app_with_agent.agent_name)
    expect(drawer).to_be_visible()
    expect(page.get_by_role("complementary", name="This chat's agent")).to_have_count(1)
    open_pairs = [tuple(x) for x in page.evaluate(_LANDMARKS_JS)]
    assert len(open_pairs) == len(set(open_pairs)), open_pairs
    assert ("complementary", "This chat's agent") in open_pairs, open_pairs
    assert ("complementary", "Chats") in open_pairs and ("navigation", "Main") in open_pairs
    expect(page.get_by_role("main")).to_have_count(1)
    _nav.open_destination(page, "library")
    expect(_nav.destination_panel(page, "library")).to_be_visible()
    expect(aside).to_have_attribute("aria-label", "Library")
    _nav.open_destination(page, "settings")
    expect(_nav.destination_panel(page, "settings")).to_be_visible()
    expect(aside).to_have_attribute("aria-label", "Settings")
    # No two landmarks of the same role share a name (the ARIA landmark rule).
    # Since M25 F3 L5a the Settings aside (complementary, "Settings") holds the
    # Settings nav (navigation, "Settings", reference spec section 8.1): one name
    # across two roles, which assistive tech announces apart ("Settings
    # complementary", "Settings navigation").
    expect(drawer).to_be_hidden()  # off Chats
    pairs = [tuple(x) for x in page.evaluate(_LANDMARKS_JS)]
    assert len(pairs) == len(set(pairs)), pairs
    assert ("navigation", "Settings") in pairs and ("complementary", "Settings") in pairs, pairs


def test_aside_shows_the_agents_list_column_and_main_fills_the_rest(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Inverted (M25 F3 L3): Agents' aside was hidden; it now holds the agents
    list column at --list-w with no top padding, and main fills the rest."""
    page.set_viewport_size({"width": 1440, "height": 900})
    _boot(page, app_with_agent.base_url, "agents")
    aside = page.locator("aside#app-sidebar")
    expect(aside).to_be_visible()
    expect(aside).to_have_attribute("aria-label", "Agents")
    expect(aside.locator('[data-testid="agents-list"]')).to_be_visible()
    out = page.evaluate(
        """() => {
          const a = document.getElementById('app-sidebar');
          const m = document.getElementById('main-content').getBoundingClientRect();
          return {asideLeft: a.getBoundingClientRect().left, asideW: a.getBoundingClientRect().width,
                  padTop: getComputedStyle(a).paddingTop, left: m.left, right: m.right, w: innerWidth};
        }"""
    )
    # No empty track: the aside starts where the rail ends, main where it ends.
    assert out["asideLeft"] == 72 and out["asideW"] == LIST_W, out
    assert out["padTop"] == "0px", out
    assert out["left"] == 72 + LIST_W and out["right"] == out["w"], out


def test_skip_link_is_first_in_tab_order_and_focuses_main(
    app_with_agent: SeededApp, page: Page
) -> None:
    _boot(page, app_with_agent.base_url)
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.classList.contains('skip-link')")
    page.keyboard.press("Tab")
    # The rail is next, and is ONE tab stop: the current destination.
    assert page.evaluate("document.activeElement.dataset.testid") == "rail-chats"
    page.keyboard.press("Shift+Tab")
    page.keyboard.press("Enter")
    page.wait_for_function("document.activeElement && document.activeElement.id === 'main-content'")
    # The fragment link is not a route: the router leaves the destination alone.
    expect(_nav.destination_panel(page, "chats")).to_be_visible()


# The aside's width per destination (M25 F3 DD1; Chats since M25 F4 L4a, DD5):
# the Chats, Agents and Library list column (--list-w) and the Settings nav
# (--settings-nav-w) are fixed at every supported width. (Chats took the
# retired --sidebar-w, 240px narrowing to 200px under 1280px, until L4a.)
LIST_W = 300
SETTINGS_NAV_W = 260


@pytest.mark.parametrize(
    ("width", "height"),
    [(1024, 768), (1279, 800), (1280, 800), (1440, 900)],
)
def test_shell_geometry_at_supported_widths(
    app_with_agent: SeededApp, page: Page, width: int, height: int
) -> None:
    page.set_viewport_size({"width": width, "height": height})
    base = app_with_agent.base_url
    widths = {
        "chats": LIST_W,
        "agents": LIST_W,
        "library": LIST_W,
        "settings/appearance": SETTINGS_NAV_W,
    }
    for route, aside_w in widths.items():
        _boot(page, base, route)
        out = page.evaluate(
            """() => {
              const r = document.querySelector('.ui-rail').getBoundingClientRect();
              const m = document.getElementById('main-content').getBoundingClientRect();
              const a = document.getElementById('app-sidebar').getBoundingClientRect();
              const panel = document.querySelector('.content-panel.active');
              const over = Array.from(panel.children).filter((c) => c.getClientRects().length && c.getBoundingClientRect().right > m.right + 0.5)
                .map((c) => c.className || c.tagName);
              return {rail: [r.left, r.right, r.top, r.bottom], vw: innerWidth, vh: innerHeight,
                      mainRight: m.right, aside: [a.left, a.width], over, docW: document.documentElement.scrollWidth};
            }"""
        )
        assert out["rail"][0] == 0 and out["rail"][1] == 72, (route, out)
        assert out["rail"][2] >= 0 and out["rail"][3] <= out["vh"], (route, out)
        assert out["mainRight"] <= out["vw"], (route, out)
        assert out["aside"] == [72, aside_w], (route, out)
        assert out["over"] == [], (route, out)
        assert out["docW"] <= out["vw"], (route, out)


def test_aside_hidden_wins_over_the_destination_width_rule(
    app_with_agent: SeededApp, page: Page
) -> None:
    """[hidden] beats a data-destination width rule, so a destination with no
    sidebar content takes no space. Every destination has one since M25 F3 L3
    (Agents was the last without), so the test hides the Agents aside by hand,
    exactly as applyShell would for a destination with sidebar: false."""
    page.set_viewport_size({"width": 1440, "height": 900})
    _boot(page, app_with_agent.base_url, "agents")
    out = page.evaluate(
        """() => {
          const a = document.getElementById('app-sidebar');
          a.hidden = true;
          const o = {dest: a.dataset.destination, hidden: a.hidden,
                  matches: a.matches('#app-sidebar[data-destination="agents"]'),
                  display: getComputedStyle(a).display, w: a.offsetWidth,
                  mainLeft: document.getElementById('main-content').getBoundingClientRect().left};
          a.hidden = false;
          return o;
        }"""
    )
    assert out == {
        "dest": "agents",
        "hidden": True,
        "matches": True,
        "display": "none",
        "w": 0,
        "mainLeft": 72,
    }


def test_aside_data_destination_follows_every_commit(app_with_agent: SeededApp, page: Page) -> None:
    """applyShell stamps the destination on the aside for every commit (rail
    clicks, Back and Forward), and the width follows it."""
    page.set_viewport_size({"width": 1440, "height": 900})
    _boot(page, app_with_agent.base_url, "chats")

    def state() -> list:
        return page.evaluate(
            """() => { const a = document.getElementById('app-sidebar');
                       return [a.dataset.destination, a.hidden ? 0 : a.getBoundingClientRect().width]; }"""
        )

    def expect_state(dest: str, w: int) -> None:
        page.wait_for_function(
            "(d) => document.getElementById('app-sidebar').dataset.destination === d", arg=dest
        )
        assert state() == [dest, w]

    expect_state("chats", LIST_W)
    for dest, w in (("library", LIST_W), ("settings", SETTINGS_NAV_W), ("agents", LIST_W)):
        _nav.open_destination(page, dest)
        expect(_nav.destination_panel(page, dest)).to_be_visible(timeout=8000)
        expect_state(dest, w)
    page.go_back()
    expect_state("settings", SETTINGS_NAV_W)
    page.go_back()
    expect_state("library", LIST_W)
    page.go_back()
    expect_state("chats", LIST_W)
    page.go_forward()
    expect_state("library", LIST_W)


def test_settings_nav_labels_and_chat_rows_do_not_clip_at_1024(
    app_with_agent: SeededApp, page: Page
) -> None:
    page.set_viewport_size({"width": 1024, "height": 768})
    base = app_with_agent.base_url
    # Settings nav links: each fits inside the aside (fixed since M25 F3 L1: 260px
    # on Settings; every aside is fixed since M25 F4 L4a), wrapping rather than
    # clipping. The section nav is retired (Library in M25 F3 L4a, Settings in
    # L5a: the Settings nav is App.ui.navGroups links); the Library list column
    # is checked below.
    for route in ("settings/appearance",):
        _boot(page, base, route)
        rows = page.evaluate(
            """() => {
              const aside = document.getElementById('app-sidebar').getBoundingClientRect();
              const nav = document.querySelector('#app-sidebar [data-testid="settings-nav"]');
              return Array.from(nav.querySelectorAll('a')).map((b) => {
                const r = b.getBoundingClientRect(), s = getComputedStyle(b);
                return {text: b.textContent.trim(), right: r.right, asideRight: aside.right,
                        fits: b.scrollWidth <= b.clientWidth + 1,
                        wraps: s.whiteSpace === 'normal' || s.whiteSpace === 'pre-wrap',
                        ellipsis: s.textOverflow === 'ellipsis' && s.overflow === 'hidden'};
              });
            }"""
        )
        assert rows, route
        for row in rows:
            assert row["right"] <= row["asideRight"] + 0.5, row
            assert row["fits"] and (row["wraps"] or row["ellipsis"]), row
    # The Library list column (M25 F3 L4a, 300px at every width): the title row,
    # the intro, the group captions and a row with a very long name all stay
    # inside the aside; the long name ellipsizes.
    httpx.post(
        f"{base}/api/knowledge-bases",
        json={"name": "A knowledge base with an extremely long name " + "x" * 80},
        headers=auth_headers_for(base),
        timeout=5,
    )
    _boot(page, base, "library")
    expect(page.locator('[data-testid="knowledge-base-card"]')).to_have_count(1, timeout=8000)
    lib = page.evaluate(
        """() => {
          const aside = document.getElementById('app-sidebar').getBoundingClientRect();
          const pane = document.querySelector('[data-testid="library-list"]');
          const parts = pane.querySelectorAll(
            '.ui-list-pane-header, .ui-list-pane-intro, .ui-list-pane-caption, .ui-list-pane-row');
          const label = pane.querySelector('[data-testid="knowledge-base-card"] .ui-list-pane-label');
          const s = getComputedStyle(label);
          return {asideRight: aside.right, rights: Array.from(parts).map((n) => n.getBoundingClientRect().right),
                  n: parts.length, truncated: label.scrollWidth > label.clientWidth,
                  ellipsis: s.textOverflow === 'ellipsis' && s.overflow === 'hidden'};
        }"""
    )
    assert lib["n"] >= 7, lib  # header, intro, four captions, a provider row and the KB row
    assert all(r <= lib["asideRight"] + 0.5 for r in lib["rights"]), lib
    assert lib["truncated"] and lib["ellipsis"], lib
    # Chat session rows (the Chats list, M25 F4 L4a): a very long title
    # ellipsizes inside the aside.
    _boot(page, base, "chats")
    _chats.start_chat(page, app_with_agent.agent_name)
    sid = _chats.send_first(page, "hello")  # a start is pending until its first send
    row = _chats.chat_row(page, sid)
    expect(row).to_be_visible(timeout=8000)
    out = row.evaluate(
        """(row) => {
          const t = row.querySelector('.ui-list-pane-label');
          t.textContent = 'An extremely long conversation title that would overflow a narrow sidebar ' + 'x'.repeat(120);
          const aside = document.getElementById('app-sidebar').getBoundingClientRect();
          const li = t.closest('li').getBoundingClientRect(), tr = t.getBoundingClientRect(), s = getComputedStyle(t);
          return {liRight: li.right, titleRight: tr.right, asideRight: aside.right,
                  ellipsis: s.textOverflow === 'ellipsis' && s.overflow === 'hidden' && s.whiteSpace === 'nowrap'};
        }"""
    )
    assert out["ellipsis"] is True
    assert (
        out["titleRight"] <= out["asideRight"] + 0.5 and out["liRight"] <= out["asideRight"] + 0.5
    )


# ── Rail geometry and colour (AC2), both themes ─────────────────────────────


@pytest.mark.parametrize(("theme", "pal"), [("dark", DARK), ("light", LIGHT)])
def test_rail_geometry_and_colour_against_the_reference_spec(
    app_with_agent: SeededApp, page: Page, theme: str, pal: dict[str, str]
) -> None:
    page.emulate_media(reduced_motion="reduce")  # hover reads are not mid-transition
    page.set_viewport_size({"width": 1440, "height": 900})
    _boot(page, app_with_agent.base_url, "agents")
    _set_theme(page, theme)
    measured = page.evaluate(
        """() => {
          const nav = document.querySelector('.ui-rail'), ns = getComputedStyle(nav);
          const brand = document.querySelector('.ui-rail-brand').getBoundingClientRect();
          const items = Array.from(document.querySelectorAll('.ui-rail-item')).map((a) => {
            const r = a.getBoundingClientRect(), s = getComputedStyle(a);
            const ic = a.querySelector('svg').getBoundingClientRect();
            const lb = a.querySelector('.ui-rail-label'), ls = getComputedStyle(lb);
            return {id: a.dataset.testid, x: r.left, y: r.top, w: r.width, h: r.height, color: s.color,
                    bg: s.backgroundColor, shadow: s.boxShadow, radius: s.borderTopLeftRadius,
                    border: s.borderTopWidth + ' ' + s.borderTopStyle + ' ' + s.borderTopColor,
                    gap: s.rowGap, dir: s.flexDirection, icon: [ic.width, ic.height],
                    labelSize: ls.fontSize, labelWeight: ls.fontWeight, labelBelow: lb.getBoundingClientRect().top >= ic.bottom,
                    current: a.getAttribute('aria-current')};
          });
          return {w: nav.getBoundingClientRect().width, h: nav.getBoundingClientRect().height, vh: innerHeight,
                  bg: ns.backgroundColor, borderR: ns.borderRightWidth + ' ' + ns.borderRightStyle + ' ' + ns.borderRightColor,
                  gap: ns.rowGap, align: ns.alignItems, dir: ns.flexDirection, pad: ns.padding,
                  brand: [brand.left, brand.top, brand.width, brand.height], items};
        }"""
    )
    # Rail: 72px, full height, --surface ground, 1px --border right edge.
    assert measured["w"] == 72 and measured["h"] == measured["vh"]
    assert measured["bg"] == _rgb(pal["surface"])
    assert measured["borderR"] == f"1px solid {_rgb(pal['border'])}"
    assert (measured["dir"], measured["align"], measured["gap"]) == ("column", "center", "6px")
    assert measured["brand"][2:] == [24, 24] and measured["brand"][1] == 12
    items = measured["items"]
    assert [i["id"] for i in items] == [f"rail-{d}" for d in DESTS]
    for item in items:
        assert item["w"] == 60 and item["h"] == 53, item
        assert (
            item["icon"] == [18, 18]
            and item["labelSize"] == "10px"
            and item["labelWeight"] == "400"
        )
        assert item["labelBelow"] and item["gap"] == "4px" and item["dir"] == "column"
        assert item["radius"] == "6px"
        assert item["border"].startswith("1px solid")
    # Pitch: 53px items + 6px gap, directly under the 24px brand mark.
    ys = [i["y"] for i in items]
    assert [b - a for a, b in zip(ys, ys[1:])] == [59, 59, 59], ys
    # Inactive: --fg-secondary on a transparent ground.
    for item in items:
        if item["current"] is None:
            assert item["color"] == _rgb(pal["fg_secondary"]), item
            assert item["bg"] == "rgba(0, 0, 0, 0)" and item["shadow"] == "none"
    # Current (Agents): --fg ink, accent wash, inset 1px accent ring (DD14).
    (cur,) = [i for i in items if i["current"] == "page"]
    assert cur["id"] == "rail-agents" and cur["color"] == _rgb(pal["fg"])
    wash = "rgba(167, 139, 250, 0.1)" if theme == "dark" else "rgba(109, 40, 217, 0.08)"
    assert cur["bg"] == wash, cur
    assert _rgb(pal["accent"]) in cur["shadow"] and "inset" in cur["shadow"], cur
    # Hover on a non-current item: --surface-elevated, --fg ink.
    _rail(page, "library").hover()
    hovered = page.evaluate(
        """() => { const s = getComputedStyle(document.querySelector('[data-testid=rail-library]'));
                   return {bg: s.backgroundColor, color: s.color}; }"""
    )
    assert hovered == {"bg": _rgb(pal["surface_elevated"]), "color": _rgb(pal["fg"])}


# ── Hrefs, restore and the interceptor (AC4) ────────────────────────────────


def test_rail_hrefs_follow_the_router_and_restore_the_last_item(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    agent = _nav.seg(app_with_agent.agent_name)
    _boot(page, base, "chats")
    # First boot: every link points at its destination root; Chats is current.
    assert _hrefs(page) == {
        "chats": _nav.href("chats"),
        "agents": _nav.href("agents"),
        "library": _nav.href("library"),
        "settings": _nav.href("settings/appearance"),
    }
    expect(_rail(page, "chats")).to_have_attribute("aria-current", "page")
    # Open an agent: Agents is current, so its link points at its root.
    _nav.open_destination(page, "agents")
    expect(_nav.destination_panel(page, "agents")).to_be_visible(timeout=8000)
    page.locator('[data-testid="agent-item"]').first.click()
    _nav.expect_route(page, f"agents/{agent}/general")
    expect(_rail(page, "agents")).to_have_attribute("aria-current", "page")
    assert _rail(page, "agents").get_attribute("href") == _nav.href("agents")
    # Leave for Settings: Agents' link now restores the agent; the others stay at their roots.
    _nav.open_destination(page, "settings")
    _nav.expect_route(page, "settings/appearance")
    expect(_rail(page, "settings")).to_have_attribute("aria-current", "page")
    expect(_rail(page, "agents")).not_to_have_attribute("aria-current", "page")
    assert _rail(page, "agents").get_attribute("href") == _nav.href(f"agents/{agent}/general")
    assert _rail(page, "settings").get_attribute("href") == _nav.href("settings/appearance")
    # Click Agents on the rail: the agent is restored (not the Agents root).
    _rail(page, "agents").click()
    _nav.expect_route(page, f"agents/{agent}/general")
    expect(page.locator('[data-testid="tab-general"]')).to_be_visible(timeout=8000)
    # Clicking the CURRENT destination goes to its root.
    _rail(page, "agents").click()
    _nav.expect_route(page, "agents")
    expect(page.locator('[data-testid="tab-general"]')).to_have_count(0)


def test_clicking_the_current_destination_resets_to_its_root(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    _boot(page, base, "settings/tools")
    assert _rail(page, "settings").get_attribute("href") == _nav.href("settings/appearance")
    _rail(page, "settings").click()
    _nav.expect_route(page, "settings/appearance")


def test_rail_links_are_real_fragment_links_that_pass_modifier_clicks_through(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    _boot(page, base, "library/mcp")
    # Library is current (root), Settings and the rest are at their routes: real
    # fragment hrefs a middle-click can open (the interceptor ignores modifiers).
    assert _rail(page, "library").get_attribute("href") == _nav.href("library")
    for dest in DESTS:
        assert (_rail(page, dest).get_attribute("href") or "").startswith(_nav.href(dest))
    info = page.evaluate(
        """() => {
          const out = [];
          const a = document.querySelector('[data-testid=rail-settings]');
          // The interceptor must not preventDefault a modified click. The test
          // swallows the default itself so nothing opens.
          const swallow = (e) => { out.push(e.defaultPrevented); e.preventDefault(); };
          document.addEventListener('click', swallow, false);
          for (const mods of [{ctrlKey: true}, {metaKey: true}, {shiftKey: true}, {button: 1}]) {
            a.dispatchEvent(new MouseEvent('click', Object.assign({bubbles: true, cancelable: true}, mods)));
          }
          document.removeEventListener('click', swallow, false);
          return out;
        }"""
    )
    assert info == [False, False, False, False]
    _nav.expect_route(page, "library")  # nothing navigated


# ── Icons (AC5) ─────────────────────────────────────────────────────────────


def test_destination_icons_exist_parse_and_render_at_18px(
    app_with_agent: SeededApp, page: Page
) -> None:
    _boot(page, app_with_agent.base_url)
    out = page.evaluate(
        """() => App.router.destinations.map((d) => {
          const svg = App.ui.util.icon(d.iconKey);
          return {id: d.id, key: d.iconKey, known: !!App.icons[d.iconKey], tag: svg.nodeName,
                  hidden: svg.getAttribute('aria-hidden'), focusable: svg.getAttribute('focusable'),
                  stroke: svg.getAttribute('stroke')};
        })"""
    )
    assert [o["key"] for o in out] == ["chat", "studio", "database", "admin"]
    for o in out:
        assert o["known"] and o["tag"] == "svg"
        assert (o["hidden"], o["focusable"], o["stroke"]) == ("true", "false", "currentColor")
    sizes = page.evaluate(
        "() => Array.from(document.querySelectorAll('.ui-rail-item svg')).map((s) => { const r = s.getBoundingClientRect(); return [r.width, r.height]; })"
    )
    assert sizes == [[18, 18]] * 4


# ── onCommit hook ───────────────────────────────────────────────────────────


def test_router_on_commit_notifies_on_every_commit_and_unsubscribes(
    app_with_agent: SeededApp, page: Page
) -> None:
    _boot(page, app_with_agent.base_url)
    page.evaluate(
        """() => { window.__seen = [];
                   window.__off = App.router.onCommit((d) => window.__seen.push(d)); }"""
    )
    _nav.open_destination(page, "library")
    page.wait_for_function("window.__seen.length >= 1")
    _nav.open_destination(page, "settings")
    page.wait_for_function("window.__seen.length >= 2")
    assert page.evaluate("window.__seen.slice(0, 2)") == ["library", "settings"]
    page.evaluate("window.__off()")
    n = page.evaluate("window.__seen.length")
    _nav.open_destination(page, "chats")
    expect(_nav.destination_panel(page, "chats")).to_be_visible()
    assert page.evaluate("window.__seen.length") == n
    # A throwing subscriber never breaks a commit.
    page.evaluate("App.router.onCommit(() => { throw new Error('boom'); })")
    _nav.open_destination(page, "library")
    expect(_nav.destination_panel(page, "library")).to_be_visible()
