# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Narrow-window panels: the agent panel and GleepGlorp's drawer fill the pane (sortie 21 leg 2).

Below 768px both drawers use the factory's ``fill`` mode: they span from the rail's edge to the
right edge, take focus when the operator opens them, keep the two panes ``inert`` behind them (the
rail stays live), close on Escape, on their Close button and on any navigation except a
GleepGlorp fill's (``keepCovered``), and return focus when they close. At 768px and wider both
behave exactly as before.

Covers AC3-AC8 of the leg. The core open/focus/Tab/Escape/Close cases run in Chromium and WebKit
(``engine_browser`` + ``credentialed_context``); run the lane with ``THE_ONE_REQUIRE_WEBKIT=1`` so a
WebKit launch failure fails instead of skipping. The factory's own ``fill`` contract cases are in
``test_ui_drawer_contract.py``.
"""

from __future__ import annotations

import json

import pytest
from browser import _nav
from browser.conftest import credentialed_context
from browser.seeders import SeededApp, seed_session
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

NARROW = {"width": 624, "height": 321}
TOGGLE = '[data-testid="chat-drawer-toggle"]'
PANEL = '[data-testid="chat-drawer"]'
PANEL_CLOSE = '[data-testid="chat-drawer-close"]'
PANEL_SETTINGS = '[data-testid="chat-drawer-settings-link"]'
BTN = '[data-testid="gg-corner-button"]'
GG = '[data-testid="gg-drawer"]'
GG_CLOSE = '[data-testid="gg-drawer-close"]'
GG_SETUP = '[data-testid="gg-drawer-setup-action"]'
JUMP = '[data-testid="rail-jump-to"]'
JUMP_INPUT = '[data-testid="jump-to-input"]'
DIALOG = '[data-testid="confirm-dialog-overlay"]'
CONTINUE = '[data-testid="modal-confirm-btn"]'
DESC = '[data-field="description"]'
STORAGE_KEY = "chat-drawer-open"

T_A = "2026-06-15T11:30:00+00:00"

_COVER_JS = """() => {
  const sb = document.getElementById('app-sidebar');
  const mn = document.getElementById('main-content');
  const rail = document.getElementById('app-rail');
  return {
    sidebar: sb.hasAttribute('inert'), main: mn.hasAttribute('inert'),
    rail: rail.hasAttribute('inert') || !!rail.closest('[inert]'),
    count: document.querySelectorAll('[inert]').length,
  };
}"""

_FOCUS_JS = """(sel) => {
  const a = document.activeElement;
  const d = document.querySelector(sel);
  return {
    body: !a || a === document.body || a === document.documentElement,
    inSidebar: !!a && document.getElementById('app-sidebar').contains(a),
    inMain: !!a && document.getElementById('main-content').contains(a),
    inRail: !!a && !!a.closest('#app-rail'),
    inDrawer: !!a && !!d && d.contains(a),
    id: a ? (a.getAttribute('data-testid') || a.id || a.tagName) : null,
  };
}"""

_BOX_JS = """(sel) => {
  const r = document.querySelector(sel).getBoundingClientRect();
  const row = document.querySelector('.app-shell-row').getBoundingClientRect();
  return {left: r.left, right: r.right, top: r.top - row.top, bottom: row.bottom - r.bottom,
          width: r.width, rowRight: row.right};
}"""

NO_COVER = {"sidebar": False, "main": False, "rail": False, "count": 0}


def _cover(page: Page) -> dict:
    return page.evaluate(_COVER_JS)


def _focus(page: Page, drawer: str = PANEL) -> dict:
    return page.evaluate(_FOCUS_JS, drawer)


def _main_width(page: Page) -> float:
    return page.evaluate(
        "() => document.getElementById('main-content').getBoundingClientRect().width"
    )


def _not_on_body(page: Page, timeout: float = 5000) -> None:
    page.wait_for_function(
        "() => document.activeElement && document.activeElement !== document.body"
        " && document.activeElement !== document.documentElement",
        timeout=timeout,
    )


def _seed(app: SeededApp) -> str:
    return seed_session(app.base_url, app.agent_name, "Chat A", T_A)


def _open_chat_narrow(page: Page, app: SeededApp, size: dict | None = None) -> str:
    sid = _seed(app)
    page.set_viewport_size(size or NARROW)
    _nav.goto_settled(page, app.base_url, f"chats/{_nav.seg(sid)}")
    expect(page.locator(TOGGLE)).to_be_visible(timeout=8000)
    return sid


def _open_gg_narrow(page: Page, app: SeededApp, route: str = "agents", size: dict | None = None):
    page.set_viewport_size(size or NARROW)
    _nav.goto_settled(page, app.base_url, route)
    page.wait_for_function(
        "() => App.gleepglorpDrawer && App.gleepglorpDrawer.state() !== null", timeout=8000
    )
    expect(page.locator(BTN)).to_be_visible(timeout=8000)


def _tab_never_enters_the_panes(page: Page, drawer: str, steps: int = 16) -> None:
    """Tab and Shift+Tab around the whole cycle: focus is never in a covered pane, and the rail is
    reachable."""
    seen_rail = False
    for key in ("Tab", "Shift+Tab"):
        for _ in range(steps):
            page.keyboard.press(key)
            f = _focus(page, drawer)
            assert not f["inSidebar"] and not f["inMain"], (key, f)
            seen_rail = seen_rail or f["inRail"]
    assert seen_rail, "the rail stays reachable by keyboard while a drawer covers the panes"


def _panel_state_wait(page: Page, open_: bool) -> None:
    if open_:
        expect(page.locator(PANEL)).to_be_visible(timeout=8000)
    else:
        expect(page.locator(PANEL)).to_be_hidden(timeout=8000)


# ── AC3 + AC5 + AC8: the agent panel at 624x321, in both engines ─────────────


@pytest.mark.parametrize(
    ("open_by", "close_by"),
    [("mouse", "escape"), ("keyboard", "button")],
    ids=["mouse-esc", "key-btn"],
)
def test_agent_panel_fills_the_pane_and_closes_with_focus_back(
    engine_browser, app_with_agent: SeededApp, open_by: str, close_by: str
) -> None:
    app = app_with_agent
    sid = _seed(app)
    context = credentialed_context(engine_browser, app.base_url, viewport=NARROW)
    page = context.new_page()
    try:
        _nav.goto_settled(page, app.base_url, f"chats/{_nav.seg(sid)}")
        toggle = page.locator(TOGGLE)
        expect(toggle).to_be_visible(timeout=8000)
        assert _cover(page) == NO_COVER
        expect(page.locator(PANEL)).to_be_hidden()
        assert _main_width(page) >= 360

        if open_by == "mouse":
            toggle.click()
        else:
            toggle.focus()
            page.keyboard.press("Enter")
        _panel_state_wait(page, True)

        box = page.evaluate(_BOX_JS, PANEL)
        assert box["left"] == 72 and box["right"] == box["rowRight"], box
        assert box["top"] == 0 and box["bottom"] == 0, box
        assert _cover(page) == {"sidebar": True, "main": True, "rail": False, "count": 2}
        expect(toggle).to_be_hidden()  # the chat-header toggle is hidden while the panel fills
        expect(page.locator(PANEL_CLOSE)).to_be_visible()
        f = _focus(page)
        assert f["inDrawer"] and f["id"] == "chat-drawer-close", f  # focus moved in
        _tab_never_enters_the_panes(page, PANEL)

        # Back to the first control, then close.
        page.locator(PANEL_CLOSE).focus()
        if close_by == "escape":
            page.keyboard.press("Escape")
        else:
            page.keyboard.press("Enter")
        _panel_state_wait(page, False)
        assert _cover(page) == NO_COVER
        expect(toggle).to_be_visible()
        f = _focus(page)
        assert f["id"] == "chat-drawer-toggle", f  # focus returned to the opener
        assert _main_width(page) >= 360
    finally:
        context.close()


def test_agent_panel_close_button_names_and_visibility(
    app_with_agent: SeededApp, page: Page
) -> None:
    """The Close button is an icon-only ghost button, shown below 768px only (by CSS on the
    drawer's data-mode); at 1024 and 1280 the header toggle stays and the Close button is hidden."""
    app = app_with_agent
    _open_chat_narrow(page, app)
    page.locator(TOGGLE).click()
    _panel_state_wait(page, True)
    close = page.locator(PANEL_CLOSE)
    expect(close).to_have_attribute("aria-label", "Close agent panel")
    assert page.evaluate("() => document.getElementById('chat-drawer').dataset.mode") == "fill"
    page.set_viewport_size({"width": 1024, "height": 768})
    page.wait_for_function(
        "() => document.getElementById('chat-drawer').dataset.mode === 'overlay'", timeout=8000
    )
    assert (
        page.evaluate("(s) => getComputedStyle(document.querySelector(s)).display", PANEL_CLOSE)
        == "none"
    )
    expect(page.locator(TOGGLE)).to_be_visible()


# ── AC6: navigation closes a covering drawer ─────────────────────────────────


def _expect_closed_and_uncovered(page: Page) -> None:
    _panel_state_wait(page, False)
    assert _cover(page) == NO_COVER


@pytest.mark.parametrize("how", ["rail", "back", "jump-to", "open-settings"])
def test_navigation_closes_the_agent_panel(app_with_agent: SeededApp, page: Page, how: str) -> None:
    app = app_with_agent
    sid = _seed(app)
    page.set_viewport_size(NARROW)
    if how == "back":
        _nav.goto_settled(page, app.base_url, "agents")
        assert page.evaluate("(r) => App.router.go(r)", f"chats/{_nav.seg(sid)}") is True
    else:
        _nav.goto_settled(page, app.base_url, f"chats/{_nav.seg(sid)}")
    expect(page.locator(TOGGLE)).to_be_visible(timeout=8000)
    page.locator(TOGGLE).click()
    _panel_state_wait(page, True)
    assert _cover(page)["count"] == 2

    if how == "rail":
        page.locator('[data-testid="rail-library"]').click()
        _nav.expect_route(page, "library")
    elif how == "back":
        page.evaluate("() => history.back()")
        _nav.expect_route(page, "agents")
    elif how == "jump-to":
        # Jump to started from inside the drawer (the focused element is the opener): it closes.
        assert _focus(page)["inDrawer"]
        page.keyboard.press("Control+k")
        expect(page.locator(JUMP_INPUT)).to_be_visible(timeout=5000)
        page.locator(JUMP_INPUT).fill("settings")
        page.keyboard.press("Enter")
        page.wait_for_function(
            "() => App.router.current().destination === 'settings'", timeout=8000
        )
    else:
        page.locator(PANEL_SETTINGS).click()
        page.wait_for_function("() => App.router.current().destination === 'agents'", timeout=8000)
    _expect_closed_and_uncovered(page)
    _not_on_body(page)  # the opener may be unmounted by the navigation: focus is never on <body>


# ── AC3: the narrow open state is session-only ───────────────────────────────


def test_narrow_open_state_is_session_only_and_never_stored(
    app_with_agent: SeededApp, page: Page
) -> None:
    app = app_with_agent
    sid = _seed(app)
    page.set_viewport_size({"width": 1280, "height": 800})
    _nav.goto_settled(page, app.base_url, f"chats/{_nav.seg(sid)}")
    expect(page.locator(TOGGLE)).to_be_visible(timeout=8000)
    stored = json.dumps({"push": True, "overlay": False})
    page.evaluate("([k, v]) => localStorage.setItem(k, v)", [STORAGE_KEY, stored])
    page.reload()
    _nav.wait_router(page, f"chats/{_nav.seg(sid)}")
    _panel_state_wait(page, True)  # push, stored open
    assert page.evaluate("(k) => localStorage.getItem(k)", STORAGE_KEY) == stored

    # Wide -> narrow never opens the panel (it resets on entering fill); the store is untouched.
    page.set_viewport_size(NARROW)
    _panel_state_wait(page, False)
    assert _cover(page) == NO_COVER
    page.locator(TOGGLE).click()
    _panel_state_wait(page, True)
    assert _cover(page)["count"] == 2
    assert page.evaluate("(k) => localStorage.getItem(k)", STORAGE_KEY) == stored
    page.keyboard.press("Escape")  # the Escape path does not persist in fill either
    _panel_state_wait(page, False)
    assert page.evaluate("(k) => localStorage.getItem(k)", STORAGE_KEY) == stored

    # Open at narrow, then widen: no inert left, push state as stored (open).
    page.locator(TOGGLE).click()
    _panel_state_wait(page, True)
    page.set_viewport_size({"width": 1280, "height": 800})
    page.wait_for_function(
        "() => document.getElementById('chat-drawer').dataset.mode === 'push'", timeout=8000
    )
    assert _cover(page) == NO_COVER
    _panel_state_wait(page, True)
    expect(page.locator(TOGGLE)).to_be_visible()
    assert page.evaluate("(k) => localStorage.getItem(k)", STORAGE_KEY) == stored

    # Narrow, open, wide and narrow again: closed on every entry into fill.
    page.set_viewport_size(NARROW)
    _panel_state_wait(page, False)
    page.locator(TOGGLE).click()
    _panel_state_wait(page, True)
    page.set_viewport_size({"width": 1280, "height": 800})
    page.wait_for_function(
        "() => document.getElementById('chat-drawer').dataset.mode === 'push'", timeout=8000
    )
    page.set_viewport_size(NARROW)
    _panel_state_wait(page, False)
    assert _cover(page) == NO_COVER

    # A reload while narrow starts closed, whatever was open.
    page.locator(TOGGLE).click()
    _panel_state_wait(page, True)
    page.reload()
    _nav.wait_router(page, f"chats/{_nav.seg(sid)}")
    expect(page.locator(TOGGLE)).to_be_visible(timeout=8000)
    _panel_state_wait(page, False)
    assert _cover(page) == NO_COVER
    assert page.evaluate("(k) => localStorage.getItem(k)", STORAGE_KEY) == stored


# ── AC4 + AC5 + AC8: GleepGlorp's drawer at 624x321, in both engines ─────────


@pytest.mark.parametrize("close_by", ["escape", "button"])
def test_gleepglorp_drawer_fills_the_pane_and_closes_with_focus_back(
    engine_browser, app_with_agent: SeededApp, close_by: str
) -> None:
    app = app_with_agent
    context = credentialed_context(engine_browser, app.base_url, viewport=NARROW)
    page = context.new_page()
    try:
        _nav.goto_settled(page, app.base_url, "agents")
        page.wait_for_function(
            "() => App.gleepglorpDrawer && App.gleepglorpDrawer.state() !== null", timeout=8000
        )
        btn = page.locator(BTN)
        expect(btn).to_be_visible(timeout=8000)
        assert _cover(page) == NO_COVER
        btn.focus()
        page.keyboard.press("Enter")
        expect(page.locator(GG)).to_be_visible(timeout=8000)
        box = page.evaluate(_BOX_JS, GG)
        assert box["left"] == 72 and box["right"] == box["rowRight"], box
        assert box["top"] == 0 and box["bottom"] == 0, box
        assert _cover(page) == {"sidebar": True, "main": True, "rail": False, "count": 2}
        assert _focus(page, GG)["inDrawer"]
        _tab_never_enters_the_panes(page, GG)

        page.locator(GG_CLOSE).focus()
        if close_by == "escape":
            page.keyboard.press("Escape")
        else:
            page.keyboard.press("Enter")
        expect(page.locator(GG)).to_be_hidden(timeout=8000)
        assert _cover(page) == NO_COVER
        assert _focus(page, GG)["id"] == "gg-corner-button"
        assert _main_width(page) >= 360 or page.evaluate(
            "() => !document.getElementById('main-content').getClientRects().length"
        )
    finally:
        context.close()


def test_gleepglorp_drawer_closes_on_entering_fill(app_with_agent: SeededApp, page: Page) -> None:
    """A drawer open in a wide window closes when the window narrows (it never suddenly covers the
    pane); focus that was inside returns to the corner button; no inert is left."""
    app = app_with_agent
    _open_gg_narrow(page, app, size={"width": 1280, "height": 800})
    page.locator(BTN).click()
    expect(page.locator(GG)).to_be_visible(timeout=8000)
    assert _focus(page, GG)["inDrawer"]
    page.set_viewport_size(NARROW)
    expect(page.locator(GG)).to_be_hidden(timeout=8000)
    assert _cover(page) == NO_COVER
    page.wait_for_function(
        "() => document.activeElement && document.activeElement.dataset.testid === 'gg-corner-button'",
        timeout=5000,
    )


def test_a_rail_click_and_the_setup_link_close_the_gleepglorp_drawer(
    app_with_agent: SeededApp, page: Page
) -> None:
    app = app_with_agent
    _open_gg_narrow(page, app)
    page.locator(BTN).click()
    expect(page.locator(GG)).to_be_visible(timeout=8000)
    page.locator('[data-testid="rail-library"]').click()
    _nav.expect_route(page, "library")
    expect(page.locator(GG)).to_be_hidden(timeout=8000)
    assert _cover(page) == NO_COVER
    _not_on_body(page)
    # The drawer's own setup link ("Choose a model", default state) also closes it.
    page.locator(BTN).click()
    expect(page.locator(GG)).to_be_visible(timeout=8000)
    expect(page.locator(GG_SETUP)).to_be_visible()
    page.locator(GG_SETUP).click()
    page.wait_for_function("() => App.router.current().destination === 'settings'", timeout=8000)
    expect(page.locator(GG)).to_be_hidden(timeout=8000)
    assert _cover(page) == NO_COVER
    _not_on_body(page)


# ── AC6: keepCovered (GleepGlorp fills only) and the router's decision record ─


def test_keep_covered_keeps_the_drawer_and_the_cover_and_a_plain_go_closes_it(
    app_with_agent: SeededApp, page: Page
) -> None:
    app = app_with_agent
    _open_gg_narrow(page, app)
    assert page.evaluate("() => App.router.lastDecision()") == {
        "opener": None, "arrived": True, "keepCovered": False,
    }  # fmt: skip
    page.locator(BTN).click()
    expect(page.locator(GG)).to_be_visible(timeout=8000)
    assert page.evaluate("() => App.router.go('library', {keepCovered: true})") is True
    _nav.expect_route(page, "library")
    d = page.evaluate("() => App.router.lastDecision()")
    assert d["keepCovered"] is True and d["arrived"] is False, d
    expect(page.locator(GG)).to_be_visible()
    assert _cover(page) == {"sidebar": True, "main": True, "rail": False, "count": 2}
    assert page.evaluate("() => App.router.go('settings')") is True
    expect(page.locator(GG)).to_be_hidden(timeout=8000)
    assert page.evaluate("() => App.router.lastDecision().keepCovered") is False
    assert _cover(page) == NO_COVER


def _dirty_agent_editor(page: Page, app: SeededApp) -> None:
    page.set_viewport_size(NARROW)
    _nav.goto_settled(page, app.base_url, "settings/appearance")
    assert page.evaluate("(r) => App.router.go(r)", f"agents/{_nav.seg(app.agent_name)}/general")
    expect(page.locator(DESC)).to_be_visible(timeout=8000)
    page.locator(DESC).fill("dirty edit")
    page.wait_for_function("App.nav.isDirty()")
    page.wait_for_function(
        "() => App.gleepglorpDrawer && App.gleepglorpDrawer.state() !== null", timeout=8000
    )
    page.locator(BTN).click()
    expect(page.locator(GG)).to_be_visible(timeout=8000)


@pytest.mark.parametrize(
    ("second", "stays"),
    [
        ("() => { App.router.go('settings'); }", False),  # a rail click joins a guarded fill
        ("() => { App.router.go('settings', {keepCovered: true}); }", True),  # latest wins (set)
        ("() => history.back()", False),  # a traversal joining the pending decision overrides it
    ],
    ids=["plain-join", "keep-join", "arrival-join"],
)
def test_keep_covered_follows_the_latest_join_on_a_guarded_decision(
    app_with_agent: SeededApp, page: Page, second: str, stays: bool
) -> None:
    app = app_with_agent
    _dirty_agent_editor(page, app)
    # A guarded GleepGlorp fill is pending (the leave guard shows)...
    page.evaluate("() => { window.__fill = App.router.go('library', {keepCovered: true}); }")
    expect(page.locator(DIALOG)).to_be_visible(timeout=8000)
    # ...and a later navigation joins it: the latest target and its flag win.
    page.evaluate(second)
    page.locator(CONTINUE).click()
    expect(page.locator(DIALOG)).to_have_count(0, timeout=8000)
    page.wait_for_function("() => !App.router.isDeciding()", timeout=8000)
    if stays:
        expect(page.locator(GG)).to_be_visible()
        assert _cover(page)["count"] == 2
        assert page.evaluate("() => App.router.lastDecision().keepCovered") is True
    else:
        expect(page.locator(GG)).to_be_hidden(timeout=8000)
        assert _cover(page) == NO_COVER
        assert page.evaluate("() => App.router.lastDecision().keepCovered") is False


# ── AC7: at 768px and wider nothing changes ──────────────────────────────────


@pytest.mark.parametrize(
    ("width", "height", "mode"),
    [(1024, 768, "overlay"), (900, 700, "overlay"), (1280, 800, "push")],
)
def test_wide_agent_panel_is_unchanged(
    app_with_agent: SeededApp, page: Page, width: int, height: int, mode: str
) -> None:
    app = app_with_agent
    _open_chat_narrow(page, app, {"width": width, "height": height})
    assert page.evaluate("() => document.getElementById('chat-drawer').dataset.mode") == mode
    toggle = page.locator(TOGGLE)
    if mode == "overlay":
        expect(page.locator(PANEL)).to_be_hidden()
        toggle.focus()
        page.keyboard.press("Enter")
        _panel_state_wait(page, True)
        f = _focus(page)
        assert f["id"] == "chat-drawer-toggle", f  # no focus-in at wide widths
        box = page.evaluate(_BOX_JS, PANEL)
        assert box["width"] == 320 and box["right"] == box["rowRight"], box
    else:
        _panel_state_wait(page, True)
    expect(toggle).to_be_visible()
    assert (
        page.evaluate("(s) => getComputedStyle(document.querySelector(s)).display", PANEL_CLOSE)
        == "none"
    )
    assert _cover(page) == NO_COVER
    # The stored shape is still {push, overlay}.
    stored = json.loads(page.evaluate("(k) => localStorage.getItem(k)", STORAGE_KEY) or "{}")
    assert set(stored) <= {"push", "overlay"}, stored


@pytest.mark.parametrize(
    ("width", "height", "mode"),
    [(1024, 768, "overlay"), (900, 700, "overlay"), (1280, 800, "push")],
)
def test_wide_gleepglorp_drawer_is_unchanged(
    app_with_agent: SeededApp, page: Page, width: int, height: int, mode: str
) -> None:
    app = app_with_agent
    _open_gg_narrow(page, app, size={"width": width, "height": height})
    page.locator(BTN).click()
    expect(page.locator(GG)).to_be_visible(timeout=8000)
    assert page.evaluate("() => document.getElementById('gleepglorp-drawer').dataset.mode") == mode
    box = page.evaluate(_BOX_JS, GG)
    assert box["width"] == 360, box
    assert _cover(page) == NO_COVER
    page.keyboard.press("Escape")
    expect(page.locator(GG)).to_be_hidden(timeout=8000)
    assert _focus(page, GG)["id"] == "gg-corner-button"


def test_the_skip_link_goes_to_the_covering_drawer(app_with_agent: SeededApp, page: Page) -> None:
    """With <main> inert under a fill drawer the skip link focuses the drawer, not the dead pane."""
    app = app_with_agent
    _open_gg_narrow(page, app, route="agents/~new")
    page.locator(BTN).click()
    expect(page.locator(GG)).to_be_visible(timeout=8000)
    page.locator(".skip-link").focus()
    page.keyboard.press("Enter")
    page.wait_for_function(
        "() => document.getElementById('gleepglorp-drawer').contains(document.activeElement)",
        timeout=5000,
    )


# ── Edge cases: store-driven apply(), deleting the open chat, rail focus ─────


def test_a_store_driven_apply_does_not_close_the_open_agent_panel(
    app_with_agent: SeededApp, page: Page
) -> None:
    """An ``agents`` store refresh re-renders the pane, which calls the drawer's ``apply()``; the
    reset-on-fill belongs to *entering* fill (the media change), never to ``apply()``."""
    app = app_with_agent
    _open_chat_narrow(page, app)
    page.locator(TOGGLE).click()
    _panel_state_wait(page, True)
    page.evaluate("() => App.store.get('agents', {force: true})")
    page.evaluate("() => App.store.get('providers', {force: true})")
    page.wait_for_timeout(300)
    _panel_state_wait(page, True)
    assert _cover(page)["count"] == 2
    assert _focus(page)["inDrawer"]


def test_deleting_the_open_chat_closes_the_filling_panel_without_stranding_focus(
    app_with_agent: SeededApp, page: Page
) -> None:
    app = app_with_agent
    # The chat's own socket receives `session_deleted` (the list that would delete it is inert
    # under the panel), so send the delete over it, as the list's delete button does.
    page.add_init_script(
        "(() => { const W = window.WebSocket; window.__socks = [];"
        " window.WebSocket = function (...a) { const s = new W(...a); window.__socks.push(s); return s; };"
        " window.WebSocket.prototype = W.prototype;"
        " for (const k of ['CONNECTING', 'OPEN', 'CLOSING', 'CLOSED']) window.WebSocket[k] = W[k]; })()"
    )
    sid = _open_chat_narrow(page, app)
    page.locator(TOGGLE).click()
    _panel_state_wait(page, True)
    page.wait_for_function("() => window.__socks.some(s => s.readyState === 1)", timeout=8000)
    page.evaluate(
        "(id) => window.__socks.filter(s => s.readyState === 1).forEach("
        "s => s.send(JSON.stringify({action: 'delete_session', session_id: id})))",
        sid,
    )
    _panel_state_wait(page, False)
    assert _cover(page) == NO_COVER
    _not_on_body(page)
    page.wait_for_timeout(1200)  # past any deferred focus check
    _not_on_body(page, timeout=1000)
    f = _focus(page)
    assert not f["body"], f


@pytest.mark.parametrize("drawer", ["agent-panel", "gleepglorp"])
def test_a_rail_click_while_a_drawer_covers_leaves_focus_on_the_rail_link(
    engine_browser, app_with_agent: SeededApp, drawer: str
) -> None:
    """Leg 1 AC7: a rail click leaves focus on the rail link, even when it closes a covering drawer
    (the shell's deferred focus check must never move focus off a visible element)."""
    app = app_with_agent
    sid = _seed(app)
    context = credentialed_context(engine_browser, app.base_url, viewport=NARROW)
    page = context.new_page()
    try:
        if drawer == "agent-panel":
            _nav.goto_settled(page, app.base_url, f"chats/{_nav.seg(sid)}")
            expect(page.locator(TOGGLE)).to_be_visible(timeout=8000)
            page.locator(TOGGLE).click()
            _panel_state_wait(page, True)
        else:
            _nav.goto_settled(page, app.base_url, "agents")
            page.wait_for_function(
                "() => App.gleepglorpDrawer && App.gleepglorpDrawer.state() !== null", timeout=8000
            )
            page.locator(BTN).click()
            expect(page.locator(GG)).to_be_visible(timeout=8000)
        page.locator('[data-testid="rail-library"]').click()
        _nav.expect_route(page, "library")
        if drawer == "agent-panel":
            _expect_closed_and_uncovered(page)
        else:
            expect(page.locator(GG)).to_be_hidden(timeout=8000)
        for _ in range(8):  # across the deferred checks (a bounded run, ~1.2s)
            f = _focus(page)
            assert f["inRail"] and f["id"] == "rail-library", f
            page.wait_for_timeout(150)
    finally:
        context.close()
