"""Narrow-window shell: one pane at a time below 768px (sortie 21 leg 1).

Below 768px the shell shows ONE pane, chosen by the operator's intent held in the router
(``App.router.paneIntent()``: ``list`` after a bare-destination navigation, ``detail`` after opening
an item); the current rail icon is the way back to the list. At 768px and wider nothing changes.

Covers AC1-AC9 of the leg: the intent rule and its sticky list flag (the input table), arrivals
and the Stay revert, the hook and the unchanged shapes, the stamp and hiding rule, the Settings
rail href, the pane layout at 624x321, focus, the transcript re-pin, and the wide layout
untouched. The core layout assertions run in Chromium and WebKit (``engine_browser`` +
``credentialed_context``); run the lane with ``THE_ONE_REQUIRE_WEBKIT=1`` so a WebKit launch
failure fails instead of skipping.

Short-height rules, corner-button clearance and width clamps are a later leg; nothing here
asserts the charter's full criterion 1.
"""

from __future__ import annotations

import pytest
from browser import _chats, _lists, _nav
from browser.conftest import credentialed_context
from browser.seeders import SeededApp, seed_session
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

NARROW = {"width": 624, "height": 321}
DIALOG = '[data-testid="confirm-dialog-overlay"]'
STAY = '[data-testid="modal-cancel-btn"]'
CONTINUE = '[data-testid="modal-confirm-btn"]'
DESC = '[data-field="description"]'

# Session timestamps: A is the newest, so the idle rules auto-join it.
T_A = "2026-06-15T11:30:00+00:00"
T_B = "2026-06-14T11:30:00+00:00"

_STATE_JS = """() => {
  const row = document.querySelector('.app-shell-row');
  const sb = document.getElementById('app-sidebar');
  const mn = document.getElementById('main-content');
  const shown = (e) => !!e && e.getClientRects().length > 0;
  return {
    intent: App.router.paneIntent(),
    pane: row.getAttribute('data-pane'),
    sidebar: shown(sb), main: shown(mn),
    sidebarW: sb.getBoundingClientRect().width, mainW: mn.getBoundingClientRect().width,
    overflow: document.scrollingElement.scrollWidth - document.scrollingElement.clientWidth,
    route: App.router.current() && App.router.current().route,
  };
}"""

_FOCUS_JS = """() => {
  const a = document.activeElement;
  const sb = document.getElementById('app-sidebar');
  const mn = document.getElementById('main-content');
  return {
    body: !a || a === document.body || a === document.documentElement,
    inSidebar: !!a && sb.contains(a), inMain: !!a && mn.contains(a),
    inRail: !!a && !!a.closest('#app-rail'),
    tag: a ? a.tagName + '#' + (a.id || '') + '.' + (a.getAttribute('data-testid') || '') : null,
  };
}"""


def _state(page: Page) -> dict:
    return page.evaluate(_STATE_JS)


def _wait_pane(page: Page, pane: str, timeout: float = 8000) -> dict:
    """Wait until the router's intent and the row's stamp both read *pane*; return the state."""
    page.wait_for_function(
        """(p) => App.router.paneIntent() === p
          && document.querySelector('.app-shell-row').getAttribute('data-pane') === p""",
        arg=pane,
        timeout=timeout,
    )
    return _state(page)


def _expect_one_pane(st: dict, which: str, floor: int = 360) -> None:
    """Exactly one pane is visible, it is *which* and at least *floor* wide, and the page does
    not scroll sideways."""
    assert st["sidebar"] != st["main"], st
    if which == "list":
        assert st["sidebar"] and not st["main"] and st["sidebarW"] >= floor, st
    else:
        assert st["main"] and not st["sidebar"] and st["mainW"] >= floor, st
    assert st["overflow"] <= 0, st


def _rail(page: Page, dest: str):
    return page.locator(f'[data-testid="rail-{dest}"]')


def _go(page: Page, route: str) -> bool:
    return page.evaluate("(r) => App.router.go(r)", route)


def _seed_two_chats(app: SeededApp) -> tuple[str, str]:
    a = seed_session(app.base_url, app.agent_name, "Chat A", T_A)
    b = seed_session(app.base_url, app.agent_name, "Chat B", T_B)
    return a, b


def _open_narrow(page: Page, base: str, route: str) -> None:
    page.set_viewport_size(NARROW)
    _nav.goto_settled(page, base, route)


def _expect_dialog_then(page: Page, button: str) -> None:
    expect(page.locator(DIALOG)).to_be_visible(timeout=8000)
    page.locator(button).click()
    expect(page.locator(DIALOG)).to_have_count(0, timeout=8000)


# ── AC1: the intent rule (the input table) ───────────────────────────────────

# (start route, input to go(), expected intent once settled). `{agent}` is the seeded agent.
INPUT_TABLE = [
    pytest.param("agents/{agent}/general", "agents", "list", id="bare-agents"),
    pytest.param("agents/{agent}/general", "library", "list", id="bare-library"),
    pytest.param("agents/{agent}/general", "settings", "list", id="bare-settings"),
    pytest.param("agents/{agent}/general", "chats", "list", id="bare-chats-with-sessions"),
    pytest.param("agents/{agent}/general", "chats/~new", "list", id="bare-chats-new"),
    pytest.param("agents/{agent}/general", "settings/general", "detail", id="settings-general"),
    pytest.param("agents/{agent}/general", "settings/appearance", "detail", id="settings-page"),
    pytest.param("agents/{agent}/general", "library/providers", "list", id="library-section-alias"),
    pytest.param("agents/{agent}/general", "chat", "detail", id="legacy-chat-then-autojoin"),
    pytest.param("settings/appearance", "studio", "list", id="legacy-studio-lands-on-list-route"),
    pytest.param("settings/appearance", "agents/~new", "detail", id="agents-new"),
    pytest.param("settings/appearance", "agents/{agent}/general", "detail", id="agent-item"),
]


@pytest.mark.parametrize(("start", "target", "expected"), INPUT_TABLE)
def test_intent_input_table(
    app_with_agent: SeededApp, page: Page, start: str, target: str, expected: str
) -> None:
    app = app_with_agent
    _seed_two_chats(app)
    agent = _nav.seg(app.agent_name)
    _open_narrow(page, app.base_url, start.format(agent=agent))
    # Let a start on chats settle on its auto-joined chat, so the go() is the intent.
    assert _go(page, target.format(agent=agent)) is True
    page.wait_for_timeout(600)  # an area's auto-join sync lands after the commit
    st = _wait_pane(page, expected)
    _expect_one_pane(st, expected, floor=360)


def test_first_load_on_chats_shows_the_auto_joined_chat(
    app_with_agent: SeededApp, page: Page
) -> None:
    """First load on bare ``#chats`` with sessions: boot is an arrival (no intent, flag unset), so
    the join's sync to ``chats/{id}`` shows the chat, not the list."""
    app = app_with_agent
    a, _ = _seed_two_chats(app)
    _open_narrow(page, app.base_url, "chats")
    _nav.expect_route(page, f"chats/{_nav.seg(a)}")
    st = _wait_pane(page, "detail")
    _expect_one_pane(st, "detail")
    assert st["route"] == f"chats/{_nav.seg(a)}"


def test_first_load_on_chats_without_sessions_stays_on_the_list(
    app_with_agent: SeededApp, page: Page
) -> None:
    _open_narrow(page, app_with_agent.base_url, "chats")
    _expect_one_pane(_wait_pane(page, "list"), "list")


def test_rail_click_with_chat_open_shows_list_and_join_keeps_it(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Rail click on Chats with a chat open (a re-join syncs to ``chats/{id}``): the list stays
    (the sticky flag), and opening a row shows that chat."""
    app = app_with_agent
    a, b = _seed_two_chats(app)
    _open_narrow(page, app.base_url, f"chats/{_nav.seg(a)}")
    _wait_pane(page, "detail")
    _rail(page, "chats").click()
    st = _wait_pane(page, "list")
    page.wait_for_timeout(600)  # the re-join reply's sync
    st = _wait_pane(page, "list")
    _expect_one_pane(st, "list")
    assert st["route"] == f"chats/{_nav.seg(a)}"
    _chats.open_chat(page, b)
    _expect_one_pane(_wait_pane(page, "detail"), "detail")


def test_delete_open_chat_shows_list_even_after_auto_join(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Deleting the open chat: ``sync(null)`` is bare (list, sticky); the idle rules then auto-join
    the next session and sync to ``chats/{id}``, which keeps the list."""
    app = app_with_agent
    a, b = _seed_two_chats(app)
    _open_narrow(page, app.base_url, f"chats/{_nav.seg(a)}")
    _wait_pane(page, "detail")
    _rail(page, "chats").click()
    _wait_pane(page, "list")
    row = page.locator("li").filter(has=_chats.chat_row(page, a))
    row.hover()
    _chats.chat_row_delete(page, a).click()  # arm
    _chats.chat_row_delete(page, a).click()  # confirm
    expect(_chats.chat_row(page, a)).to_have_count(0, timeout=8000)
    _nav.expect_route(page, f"chats/{_nav.seg(b)}")  # auto-joined the next session
    page.wait_for_timeout(400)
    st = _wait_pane(page, "list")
    _expect_one_pane(st, "list")
    focus = page.evaluate(_FOCUS_JS)
    assert not focus["body"] and not focus["inMain"], focus


# ── AC2: arrivals and the Stay revert ────────────────────────────────────────


def test_back_after_rail_click_shows_the_chat(app_with_agent: SeededApp, page: Page) -> None:
    """From ``chats/A``: a rail click shows the list; Back (an arrival) shows chat A."""
    app = app_with_agent
    a, _ = _seed_two_chats(app)
    _open_narrow(page, app.base_url, f"chats/{_nav.seg(a)}")
    _wait_pane(page, "detail")
    _rail(page, "chats").click()
    _wait_pane(page, "list")
    page.go_back()
    st = _wait_pane(page, "detail")
    _expect_one_pane(st, "detail")
    assert st["route"] == f"chats/{_nav.seg(a)}"


def test_stay_on_refused_back_leaves_the_pane_alone(app_with_agent: SeededApp, page: Page) -> None:
    """A dirty editor refuses Back; the router's own revert lands in the same-route arrival branch
    and must not recompute the intent (the ``reverting`` flag)."""
    app = app_with_agent
    _open_narrow(page, app.base_url, "agents")
    _wait_pane(page, "list")
    _lists.open_item(page, "agents", app.agent_name)
    _wait_pane(page, "detail")
    page.locator(DESC).fill("dirty edit")
    page.wait_for_function("App.nav.isDirty()")
    page.go_back()
    _expect_dialog_then(page, STAY)
    page.wait_for_timeout(500)  # the revert's popstate
    st = _wait_pane(page, "detail")
    _expect_one_pane(st, "detail")
    assert st["route"].startswith("agents/"), st
    # A later genuine Back still works (the flag did not leak): Continue goes to the list.
    page.go_back()
    _expect_dialog_then(page, CONTINUE)
    _expect_one_pane(_wait_pane(page, "list"), "list")


def test_stay_on_refused_back_keeps_a_sticky_list_on_a_detail_route(
    app_with_agent: SeededApp, page: Page
) -> None:
    """The Settings nav (bare ``#settings`` -> ``settings/appearance``) is a sticky ``list`` on a
    route that would otherwise read ``detail``. A refused Back's revert must leave it ``list``."""
    app = app_with_agent
    _open_narrow(page, app.base_url, "chats")
    _rail(page, "settings").click()
    st = _wait_pane(page, "list")
    assert st["route"] == "settings/appearance", st
    page.evaluate("App.nav.registerSource('t', { isDirty: () => true, discard() {} })")
    page.go_back()
    _expect_dialog_then(page, STAY)
    page.wait_for_timeout(500)  # the revert's popstate
    st = _wait_pane(page, "list")
    _expect_one_pane(st, "list")
    assert st["route"] == "settings/appearance", st
    page.evaluate("App.nav.registerSource('t', { isDirty: () => false, discard() {} })")


def test_rail_click_while_dirty_stay_keeps_detail_continue_shows_list(
    app_with_agent: SeededApp, page: Page
) -> None:
    app = app_with_agent
    _open_narrow(page, app.base_url, "agents")
    _lists.open_item(page, "agents", app.agent_name)
    _wait_pane(page, "detail")
    page.locator(DESC).fill("dirty edit")
    page.wait_for_function("App.nav.isDirty()")
    _rail(page, "agents").click()
    _expect_dialog_then(page, STAY)
    st = _wait_pane(page, "detail")
    _expect_one_pane(st, "detail")
    _rail(page, "agents").click()
    _expect_dialog_then(page, CONTINUE)
    _expect_one_pane(_wait_pane(page, "list"), "list")


def test_save_create_stays_on_the_detail(app_with_agent: SeededApp, page: Page) -> None:
    """``agents/~new`` -> ``agents/{name}`` (a sync after the ``~new`` commit) stays ``detail``."""
    app = app_with_agent
    _open_narrow(page, app.base_url, "agents/~new")
    _wait_pane(page, "detail")
    page.evaluate("App.router.sync('studio', 'agents/created-one', { name: 'created-one' })")
    page.wait_for_timeout(200)
    assert page.evaluate("App.router.paneIntent()") == "detail"


# ── AC3: the hook and the unchanged shapes ───────────────────────────────────

_INSTALL_PROBE = """
(() => {
  const t = setInterval(() => {
    if (window.App && App.router && App.router.onPaneIntentChange) {
      clearInterval(t);
      window.__initialIntent = App.router.paneIntent();
      window.__intents = [];
      App.router.onPaneIntentChange((v) => window.__intents.push(v));
    }
  }, 1);
})();
"""


def test_first_commit_fires_the_hook_from_null(app_with_agent: SeededApp, page: Page) -> None:
    page.add_init_script(_INSTALL_PROBE)
    page.set_viewport_size(NARROW)
    _nav.goto_settled(page, app_with_agent.base_url, "agents")
    assert page.evaluate("window.__initialIntent") is None
    intents = page.evaluate("window.__intents")
    assert intents and intents[0] in ("list", "detail"), intents
    assert intents[-1] == "list", intents


def test_hook_unsubscribes_and_a_throwing_subscriber_breaks_nothing(
    app_with_agent: SeededApp, page: Page
) -> None:
    app = app_with_agent
    _open_narrow(page, app.base_url, "agents")
    seen = page.evaluate(
        """async (agent) => {
          const seen = [];
          const off1 = App.router.onPaneIntentChange(() => { throw new Error('boom'); });
          const off2 = App.router.onPaneIntentChange((v) => seen.push(v));
          const off3 = App.router.onPaneIntentChange((v) => seen.push('late:' + v));
          await App.router.go('agents/' + agent + '/general');
          off1(); off2(); off3();
          await App.router.go('agents');
          return seen;
        }""",
        _nav.seg(app.agent_name),
    )
    assert seen == ["detail", "late:detail"], seen
    assert _wait_pane(page, "list")["pane"] == "list"


def test_public_shapes_do_not_gain_the_pane_field(app_with_agent: SeededApp, page: Page) -> None:
    _open_narrow(page, app_with_agent.base_url, "agents")
    shape = page.evaluate(
        """() => ({
          current: Object.keys(App.router.describeCurrent()).sort(),
          resolved: Object.keys(App.router.resolve('chats')).sort(),
          resolvedSettings: Object.keys(App.router.resolve('settings')).sort(),
        })"""
    )
    assert shape["current"] == ["destination", "parts", "route"], shape
    assert "bare" not in shape["resolved"] and "bare" not in shape["resolvedSettings"], shape
    assert shape["resolved"] == ["area", "destination", "kind", "redirected", "route", "sub"], shape


# ── AC4 + AC6: the stamp, the hiding rule and the destinations at 624x321 ────


def test_destinations_show_exactly_one_pane_at_624x321(
    engine_browser, app_with_agent: SeededApp
) -> None:
    app = app_with_agent
    a, b = _seed_two_chats(app)
    context = credentialed_context(engine_browser, app.base_url, viewport=NARROW)
    page = context.new_page()
    try:
        _nav.goto_settled(page, app.base_url, f"chats/{_nav.seg(a)}")
        _expect_one_pane(_wait_pane(page, "detail"), "detail")  # a chat, after boot

        _rail(page, "chats").click()  # the Chats list after a rail click with a chat open
        _expect_one_pane(_wait_pane(page, "list"), "list")
        _chats.open_chat(page, b)  # that chat after opening it
        _expect_one_pane(_wait_pane(page, "detail"), "detail")

        _rail(page, "agents").click()  # the agent list
        _expect_one_pane(_wait_pane(page, "list"), "list")
        _lists.open_item(page, "agents", app.agent_name)  # an agent's tab
        # Below 768px the tabs are one menu button naming the current tab (the tablist is hidden).
        expect(page.locator('[data-testid="agent-tabs-menu-btn"]')).to_have_text(
            "General", timeout=8000
        )
        _expect_one_pane(_wait_pane(page, "detail"), "detail")

        _rail(page, "library").click()  # the Library grouped list (start page hidden)
        _expect_one_pane(_wait_pane(page, "list"), "list")
        assert _go(page, f"library/providers/{app.provider_id}") is True  # a Library item
        _expect_one_pane(_wait_pane(page, "detail"), "detail")

        _rail(page, "settings").click()  # the Settings nav on first entry (last route Appearance)
        _expect_one_pane(_wait_pane(page, "list"), "list")
        expect(_lists.settings_nav(page)).to_be_visible(timeout=8000)
        _lists.open_settings_page(page, "prompts")  # a Settings page after choosing it
        _expect_one_pane(_wait_pane(page, "detail"), "detail")
    finally:
        context.close()


def test_stamp_and_hiding_rule_css(app_with_agent: SeededApp, page: Page) -> None:
    """The stamp is an attribute (the row's className is pinned), the rules sit in the base layer,
    only the hidden pane sets ``display``, and a ``[hidden]`` aside still wins."""
    _open_narrow(page, app_with_agent.base_url, "agents")
    info = page.evaluate(
        """() => {
          const row = document.querySelector('.app-shell-row');
          const sb = document.getElementById('app-sidebar');
          const mn = document.getElementById('main-content');
          const before = { cls: row.className, main: getComputedStyle(mn).display,
                           sbFlex: getComputedStyle(sb).flexGrow };
          return { cls: before.cls, mainDisplay: before.main, sbFlex: before.sbFlex,
                   pane: row.getAttribute('data-pane') };
        }"""
    )
    assert info["pane"] == "list" and info["mainDisplay"] == "none" and info["sbFlex"] == "1", info
    assert "data-pane" not in info["cls"] and "list" not in info["cls"].split(), info
    # A sidebar:false destination stamps detail and the hidden aside stays hidden.
    hidden = page.evaluate(
        """async () => {
          const dest = App.router.destinations.find((d) => d.id === 'agents');
          dest.sidebar = false;
          await App.router.go('agents');
          const sb = document.getElementById('app-sidebar');
          const mn = document.getElementById('main-content');
          return {
            display: getComputedStyle(sb).display,
            mainShown: mn.getClientRects().length > 0,
            pane: document.querySelector('.app-shell-row').getAttribute('data-pane'),
            intent: App.router.paneIntent(),
          };
        }"""
    )
    assert hidden == {"display": "none", "mainShown": True, "pane": "detail", "intent": "list"}, (
        hidden
    )


# ── AC5: the rail ────────────────────────────────────────────────────────────


def test_rail_settings_href_rule(app_with_agent: SeededApp, page: Page) -> None:
    """Bare ``#settings`` when Settings is current or its last route is the root page; any other
    last route is that page's own route. Every other rail href is its last route."""
    app = app_with_agent
    _nav.goto_settled(page, app.base_url, "chats")
    rail = _rail(page, "settings")
    expect(rail).to_have_attribute("href", _nav.bare_href("settings"))
    assert page.evaluate("App.router.root('settings')") == "settings/appearance"
    assert _go(page, "settings/encryption") is True
    expect(rail).to_have_attribute("href", _nav.bare_href("settings"))  # current
    assert _go(page, "chats") is True
    expect(rail).to_have_attribute("href", _nav.href("settings/encryption"))
    assert _go(page, "settings/general") is True  # the alias lands on Appearance
    assert _go(page, "chats") is True
    expect(rail).to_have_attribute("href", _nav.bare_href("settings"))
    for dest in ("agents", "library"):
        expect(_rail(page, dest)).to_have_attribute("href", _nav.href(dest))


# ── AC7: focus ───────────────────────────────────────────────────────────────


def test_focus_is_never_on_body_or_in_the_hidden_pane(
    app_with_agent: SeededApp, page: Page
) -> None:
    app = app_with_agent
    a, b = _seed_two_chats(app)
    _open_narrow(page, app.base_url, f"chats/{_nav.seg(a)}")
    _wait_pane(page, "detail")
    # A rail click leaves focus on the rail link.
    _rail(page, "chats").click()
    _wait_pane(page, "list")
    page.wait_for_timeout(200)
    focus = page.evaluate(_FOCUS_JS)
    assert focus["inRail"] and not focus["body"], focus
    # Back to the chat (an arrival): focus is not on body and not in the hidden list.
    page.go_back()
    _wait_pane(page, "detail")
    page.wait_for_timeout(200)
    focus = page.evaluate(_FOCUS_JS)
    assert not focus["body"] and not focus["inSidebar"], focus
    # A focus left in the sidebar when it hides moves to the visible pane.
    _rail(page, "agents").click()
    _wait_pane(page, "list")
    _lists.open_item(page, "agents", app.agent_name)
    _wait_pane(page, "detail")
    page.wait_for_timeout(200)
    focus = page.evaluate(_FOCUS_JS)
    assert not focus["body"] and not focus["inSidebar"], focus


def test_media_change_moves_focus_out_of_the_hidden_pane(
    app_with_agent: SeededApp, page: Page
) -> None:
    app = app_with_agent
    a, _ = _seed_two_chats(app)
    page.set_viewport_size({"width": 1024, "height": 768})
    _nav.goto_settled(page, app.base_url, f"chats/{_nav.seg(a)}")
    _wait_pane(page, "detail")
    _chats.chat_row(page, a).focus()  # focus in the sidebar, which is the pane that will hide
    focus = page.evaluate(_FOCUS_JS)
    assert focus["inSidebar"], focus
    page.set_viewport_size(NARROW)
    page.wait_for_function(
        "() => !document.getElementById('app-sidebar').getClientRects().length", timeout=8000
    )
    page.wait_for_timeout(200)
    focus = page.evaluate(_FOCUS_JS)
    assert not focus["body"] and not focus["inSidebar"], focus


def test_skip_link_lands_in_the_visible_pane_only_below_768(
    app_with_agent: SeededApp, page: Page
) -> None:
    app = app_with_agent
    _open_narrow(page, app.base_url, "agents")
    _wait_pane(page, "list")
    skip = page.locator(".skip-link")
    skip.focus()
    page.keyboard.press("Enter")
    page.wait_for_timeout(200)
    focus = page.evaluate(_FOCUS_JS)
    assert focus["inSidebar"] and not focus["body"], focus
    # At 768px and wider the skip link is untouched: <main> takes focus as before.
    page.set_viewport_size({"width": 1024, "height": 768})
    page.wait_for_function(
        "() => document.getElementById('app-sidebar').getClientRects().length > 0", timeout=8000
    )
    skip.focus()
    page.keyboard.press("Enter")
    page.wait_for_function(
        "() => document.activeElement === document.getElementById('main-content')", timeout=5000
    )


# ── AC8: the transcript stays pinned across a hide ───────────────────────────


def _long_history(n: int = 40) -> list[dict]:
    out: list[dict] = []
    for i in range(n):
        out.append({"role": "user", "content": f"question number {i}"})
        out.append({"role": "assistant", "content": f"answer number {i} " + "lorem ipsum " * 12})
    return out


def _expect_pinned(page: Page, label: str) -> None:
    page.wait_for_function(
        """() => {
          const el = document.querySelector('[role="log"]');
          return !!el && el.clientHeight > 0 && el.scrollHeight > el.clientHeight
            && el.scrollHeight - el.scrollTop - el.clientHeight <= 80;
        }""",
        timeout=8000,
    )


def test_transcript_stays_pinned_when_its_pane_reappears(
    engine_browser, app_with_agent: SeededApp
) -> None:
    """A transcript that was pinned stays pinned when its box reappears (chromium and webkit), also
    when the chat joined while the list was showing. A transcript scrolled up before the hide is not
    re-pinned (its position may reset); that case is accepted and not asserted."""
    app = app_with_agent
    a = seed_session(app.base_url, app.agent_name, "Long A", T_A, messages=_long_history())
    b = seed_session(app.base_url, app.agent_name, "Long B", T_B, messages=_long_history())
    context = credentialed_context(engine_browser, app.base_url, viewport=NARROW)
    page = context.new_page()
    try:
        # Joined while the list shows: boot on Agents, then a bare Chats intent auto-joins under it.
        _nav.goto_settled(page, app.base_url, "agents")
        assert _go(page, "chats") is True
        _nav.expect_route(page, f"chats/{_nav.seg(a)}")
        _wait_pane(page, "list")
        page.wait_for_timeout(500)  # the join's history render finishes while the box is hidden
        _chats.chat_row(page, a).click()  # the already-joined chat: no re-render, only a reveal
        _wait_pane(page, "detail")
        _expect_pinned(page, "joined under the list")
        # Pinned, hidden by a rail click, shown again by opening the same chat.
        _rail(page, "chats").click()
        _wait_pane(page, "list")
        _chats.open_chat(page, b)
        _wait_pane(page, "detail")
        _expect_pinned(page, "after hide and show")
        # A width change while pinned keeps it pinned (the box resizes).
        page.set_viewport_size({"width": 900, "height": 321})
        page.wait_for_timeout(300)
        _expect_pinned(page, "after resize")
    finally:
        context.close()


# ── AC9: wide unchanged ──────────────────────────────────────────────────────


@pytest.mark.parametrize(("width", "height"), [(1024, 768), (1280, 800)])
def test_wide_layout_shows_both_panes_at_todays_widths(
    engine_browser, app_with_agent: SeededApp, width: int, height: int
) -> None:
    app = app_with_agent
    a, _ = _seed_two_chats(app)
    context = credentialed_context(
        engine_browser, app.base_url, viewport={"width": width, "height": height}
    )
    page = context.new_page()
    try:
        _nav.goto_settled(page, app.base_url, f"chats/{_nav.seg(a)}")
        st = _wait_pane(page, "detail")  # stamped at every width
        assert st["sidebar"] and st["main"], st
        assert round(st["sidebarW"]) == 300, st  # --list-w, as today
        _rail(page, "chats").click()
        st = _wait_pane(page, "list")
        assert st["sidebar"] and st["main"], st  # inert: both panes still show
        assert round(st["sidebarW"]) == 300 and st["mainW"] > 396, st
        _rail(page, "settings").click()
        st = _wait_pane(page, "list")
        assert st["sidebar"] and st["main"] and round(st["sidebarW"]) == 260, st
        assert st["overflow"] <= 0, st
    finally:
        context.close()


def test_768_is_side_by_side_and_767_is_one_pane(app_with_agent: SeededApp, page: Page) -> None:
    app = app_with_agent
    _nav.goto_settled(page, app.base_url, "agents")
    page.set_viewport_size({"width": 768, "height": 600})
    st = _wait_pane(page, "list")
    assert st["sidebar"] and st["main"], st
    page.set_viewport_size({"width": 767, "height": 600})
    page.wait_for_function(
        "() => !document.getElementById('main-content').getClientRects().length", timeout=5000
    )
    _expect_one_pane(_state(page), "list", floor=360)
