"""The GleepGlorp corner button and drawer shell (M36 F3 L2, flight DD1).

An empty drawer frame on every destination except Chats: the corner button, open and close, focus,
push or overlay by width, the "Looking at" line, the setup state, the content padding that keeps
the button off the last control, and the Jump to candidate. Leg 3 mounts the chat into the frame.

Covers, as state transitions:

* [needs a model] the button on Agents, Library and Settings, never on Chats; [off] nowhere;
* [closed] -> [open] -> [closed] by click, Close and Esc, with the focus rules;
* [open] across destinations and Chats: remembered, hidden on Chats, restored on leaving it;
* [push] and [overlay] by width, crossing 1280px live, and the Save button clear of the overlay;
* the "Looking at" line on a destination change, an item change and a save-create sync;
* the setup block ([needs a model], [ready]) and the Settings toggle that hides the button;
* the last control of a long page never under the button (a real click, no force);
* Jump to's "Ask GleepGlorp" candidate, off Chats only, while enabled.

Falls in the ``shared`` browser lane (it is not claimed by a named lane glob).
"""

from __future__ import annotations

import httpx
import pytest
from browser import _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp, seed_mcp_source
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

BTN = '[data-testid="gg-corner-button"]'
DRAWER = '[data-testid="gg-drawer"]'
TITLE = '[data-testid="gg-drawer-title"]'
CLOSE = '[data-testid="gg-drawer-close"]'
CONTEXT = '[data-testid="gg-drawer-context"]'
SETUP = '[data-testid="gg-drawer-setup"]'
SETUP_ACTION = '[data-testid="gg-drawer-setup-action"]'
SLOT = '[data-testid="gg-drawer-body"]'
JUMP = '[data-testid="rail-jump-to"]'
JUMP_INPUT = '[data-testid="jump-to-input"]'
ASK_ROW = '[data-testid="jump-to-result"][data-kind="gleepglorp-ask"]'


def _body(**over) -> dict:
    return {
        "enabled": True,
        "provider_config_id": None,
        "model": None,
        "web_access": True,
        "memory": True,
        "retention_days": 30,
        **over,
    }


def _put(base: str, **over) -> None:
    r = httpx.put(
        f"{base}/api/gleepglorp",
        json=_body(**over),
        headers=auth_headers_for(base),
        timeout=5.0,
    )
    assert r.status_code == 200, r.text


def _ready(app: SeededApp) -> None:
    _put(app.base_url, provider_config_id=app.provider_id, model="mock-default")


def _open(page: Page, base: str, route: str) -> None:
    """Load *route* and wait until the drawer shell knows GleepGlorp's state."""
    _nav.goto(page, base, route)
    dest = route.split("/")[0]
    expect(_nav.destination_panel(page, dest)).to_be_visible(timeout=8000)
    page.wait_for_function(
        "() => App.gleepglorpDrawer && App.gleepglorpDrawer.state() !== null", timeout=8000
    )


def _active(page: Page) -> str:
    return page.evaluate(
        "() => document.activeElement && (document.activeElement.dataset.testid"
        " || document.activeElement.id || document.activeElement.tagName)"
    )


def _width(page: Page, selector: str) -> float:
    return page.evaluate("(s) => document.querySelector(s).getBoundingClientRect().width", selector)


def _box(page: Page, selector: str) -> dict:
    return page.evaluate(
        "(s) => { const r = document.querySelector(s).getBoundingClientRect();"
        " return {l: r.left, t: r.top, r: r.right, b: r.bottom, w: r.width, h: r.height}; }",
        selector,
    )


def _top_at_centre_is(page: Page, selector: str) -> bool:
    """The element (or a child of it) is what a pointer would hit at its centre."""
    return page.evaluate(
        """(s) => { const e = document.querySelector(s); const r = e.getBoundingClientRect();
          const t = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
          return !!t && e.contains(t); }""",
        selector,
    )


def _intersects(a: dict, b: dict) -> bool:
    return a["l"] < b["r"] and b["l"] < a["r"] and a["t"] < b["b"] and b["t"] < a["b"]


# ── The button ──────────────────────────────────────────────────────────────


def test_the_button_is_on_every_destination_but_chats_and_follows_off(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    # [needs a model] (the default): visible, named, collapsed, wired to the drawer.
    _open(page, base, "agents")
    btn = page.locator(BTN)
    expect(btn).to_be_visible()
    expect(page.get_by_role("button", name="Ask GleepGlorp")).to_have_count(1)
    expect(btn).to_have_attribute("aria-expanded", "false")
    expect(btn).to_have_attribute("aria-controls", "gleepglorp-drawer")
    expect(btn).to_have_attribute("id", "gleepglorp-corner-button")
    # It is the last child of the shell row and sits at the bottom-right.
    assert (
        page.evaluate("() => document.querySelector('.app-shell-row').lastElementChild.id")
        == "gleepglorp-corner-button"
    )
    row = _box(page, ".app-shell-row")
    b = _box(page, BTN)
    assert (b["w"], b["h"]) == (48, 48)
    assert round(row["r"] - b["r"]) == 24 and round(row["b"] - b["b"]) == 24
    for dest in ("library", "settings"):
        _nav.open_destination(page, dest)
        expect(_nav.destination_panel(page, dest)).to_be_visible()
        expect(btn).to_be_visible()
    # [..] -> [Chats]: neither the button nor the drawer.
    _nav.open_destination(page, "chats")
    expect(btn).to_be_hidden()
    expect(page.locator(DRAWER)).to_be_hidden()
    expect(page.get_by_role("button", name="Ask GleepGlorp")).to_have_count(0)

    # [off]: nowhere, on any destination.
    _put(base, enabled=False)
    _open(page, base, "library")
    expect(btn).to_be_hidden()
    _nav.open_destination(page, "agents")
    expect(btn).to_be_hidden()
    expect(page.locator(DRAWER)).to_be_hidden()


def test_the_settings_toggle_shows_and_hides_the_button_without_a_reload(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    _open(page, base, "settings/gleepglorp")
    expect(page.locator(BTN)).to_be_visible()
    page.locator(".ui-toggle-label").filter(
        has=page.locator('[data-testid="gleepglorp-enabled"]')
    ).click()
    page.locator('[data-testid="gleepglorp-save-btn"]').click()
    expect(page.locator(BTN)).to_be_hidden(timeout=8000)
    page.locator(".ui-toggle-label").filter(
        has=page.locator('[data-testid="gleepglorp-enabled"]')
    ).click()
    page.locator('[data-testid="gleepglorp-save-btn"]').click()
    expect(page.locator(BTN)).to_be_visible(timeout=8000)


# ── Open, close, focus ──────────────────────────────────────────────────────


def test_open_close_and_esc_with_the_focus_rules(app_with_agent: SeededApp, page: Page) -> None:
    base = app_with_agent.base_url
    _open(page, base, "library")
    drawer, btn = page.locator(DRAWER), page.locator(BTN)
    # [closed] on every load.
    expect(drawer).to_be_hidden()
    expect(page.locator(".app-shell-row")).to_have_class("app-shell-row gg-corner-on")

    # [closed] -> [open]: the button gives way; focus is the AC10 target (M36 F3 L3): the setup
    # link while GleepGlorp is not ready, the composer while ready.
    btn.click()
    expect(drawer).to_be_visible()
    expect(btn).to_be_hidden()
    assert _active(page) == "gg-drawer-setup-action"
    assert page.get_by_test_id("gg-drawer-title").evaluate("e => e.tagName") == "H2"
    expect(drawer).to_have_attribute("aria-label", "GleepGlorp")
    assert (
        page.evaluate(
            "() => document.getElementById('gleepglorp-corner-button')"
            ".getAttribute('aria-expanded')"
        )
        == "true"
    )
    assert "gg-corner-on" not in page.evaluate(
        "() => document.querySelector('.app-shell-row').className"
    )
    # The header: a labelled Close that names its key; no document-level surprises.
    close = page.locator(CLOSE)
    expect(close).to_have_text("Close")
    expect(close).to_have_attribute("aria-keyshortcuts", "Escape")

    # [open] -> [closed] by Close: the button is back and has focus.
    close.click()
    expect(drawer).to_be_hidden()
    expect(btn).to_be_visible()
    assert _active(page) == "gg-corner-button"
    expect(btn).to_have_attribute("aria-expanded", "false")

    # [closed] -> [open] -> [closed] by Esc from inside the drawer.
    btn.click()
    expect(drawer).to_be_visible()
    page.keyboard.press("Escape")
    expect(drawer).to_be_hidden()
    expect(btn).to_be_visible()
    assert _active(page) == "gg-corner-button"

    # Keyboard open: Enter on the focused button.
    btn.focus()
    page.keyboard.press("Enter")
    expect(drawer).to_be_visible()
    assert _active(page) == "gg-drawer-setup-action"

    # A reload starts closed again.
    page.reload()
    page.wait_for_function("() => App.gleepglorpDrawer.state() !== null", timeout=8000)
    expect(page.locator(DRAWER)).to_be_hidden()
    expect(page.locator(BTN)).to_be_visible()


def test_esc_with_focus_outside_the_drawer_does_not_close_it(
    app_with_agent: SeededApp, page: Page
) -> None:
    _open(page, app_with_agent.base_url, "library")
    page.locator(BTN).click()
    expect(page.locator(DRAWER)).to_be_visible()
    page.locator("#main-content").focus()
    page.keyboard.press("Escape")
    expect(page.locator(DRAWER)).to_be_visible()


def test_esc_after_a_click_on_empty_drawer_space_closes_it(
    app_with_agent: SeededApp, page: Page
) -> None:
    _open(page, app_with_agent.base_url, "library")
    page.locator(BTN).click()
    expect(page.locator(DRAWER)).to_be_visible()
    # Click empty space in the body (a non-focusable area), then Escape.
    page.locator(DRAWER + " .ui-drawer-body").click(position={"x": 5, "y": 5})
    assert page.evaluate(
        "() => document.getElementById('gleepglorp-drawer').contains(document.activeElement)"
    )
    page.keyboard.press("Escape")
    expect(page.locator(DRAWER)).to_be_hidden()
    assert _active(page) == "gg-corner-button"


def test_the_open_state_is_kept_across_destinations_and_chats(
    app_with_agent: SeededApp, page: Page
) -> None:
    _open(page, app_with_agent.base_url, "agents")
    drawer, btn = page.locator(DRAWER), page.locator(BTN)
    btn.click()
    expect(drawer).to_be_visible()
    for dest in ("library", "settings"):
        _nav.open_destination(page, dest)
        expect(_nav.destination_panel(page, dest)).to_be_visible()
        expect(drawer).to_be_visible()
        expect(btn).to_be_hidden()
    # [open] -> [Chats]: neither is shown; the state is remembered.
    _nav.open_destination(page, "chats")
    expect(drawer).to_be_hidden()
    expect(btn).to_be_hidden()
    # [Chats] -> [open]: restored.
    _nav.open_destination(page, "agents")
    expect(drawer).to_be_visible()
    expect(btn).to_be_hidden()
    # Closed stays closed across a Chats visit.
    page.locator(CLOSE).click()
    expect(btn).to_be_visible()
    _nav.open_destination(page, "chats")
    expect(btn).to_be_hidden()
    _nav.open_destination(page, "library")
    expect(btn).to_be_visible()
    expect(drawer).to_be_hidden()


def test_turned_off_while_open_closes_it_and_moves_focus_to_main(
    app_with_agent: SeededApp, page: Page
) -> None:
    _open(page, app_with_agent.base_url, "library")
    page.locator(BTN).click()
    page.locator(CLOSE).focus()
    page.evaluate(
        "() => App.gleepglorp.prime(Object.assign({}, App.gleepglorp.peek().value,"
        " {enabled: false, state: 'off'}))"
    )
    expect(page.locator(DRAWER)).to_be_hidden()
    expect(page.locator(BTN)).to_be_hidden()
    assert _active(page) == "main-content"
    # Back on: closed, with the button (the open state was cleared).
    page.evaluate(
        "() => App.gleepglorp.prime(Object.assign({}, App.gleepglorp.peek().value,"
        " {enabled: true, state: 'needs_model'}))"
    )
    expect(page.locator(BTN)).to_be_visible()
    expect(page.locator(DRAWER)).to_be_hidden()


# ── Width ───────────────────────────────────────────────────────────────────


def test_push_at_1280_overlay_below_and_a_live_switch(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    page.set_viewport_size({"width": 1280, "height": 800})
    _open(page, base, "agents")
    before = _width(page, "#main-content")
    page.locator(BTN).click()
    drawer = page.locator(DRAWER)
    expect(drawer).to_have_attribute("data-mode", "push")
    assert _width(page, DRAWER) == 360
    assert round(before - _width(page, "#main-content")) == 360
    # Crossing below 1280 while open: overlay, main takes its width back, the drawer keeps 360.
    page.set_viewport_size({"width": 1200, "height": 800})
    expect(drawer).to_have_attribute("data-mode", "overlay")
    assert _width(page, DRAWER) == 360
    page.set_viewport_size({"width": 1279, "height": 800})
    main_open = _width(page, "#main-content")
    page.locator(CLOSE).click()
    assert round(_width(page, "#main-content")) == round(main_open)  # overlay never reflows main
    # And back up.
    page.locator(BTN).click()
    page.set_viewport_size({"width": 1400, "height": 800})
    expect(drawer).to_have_attribute("data-mode", "push")


def test_at_1024_the_editors_save_button_is_in_main_and_clear_of_the_button(
    app_with_agent: SeededApp, page: Page
) -> None:
    """At 1024px (768px to 1279px; below 768px one pane shows and the drawer fills it, from 1280px
    it pushes) the drawer is an overlay, which by definition covers the right of
    <main> while it is open (the Save button sits at the editor header's right end, so the open
    overlay covers it: the operator closes the drawer, with Close or Esc, to reach it). So the
    leg's AC6 "does not intersect the drawer" cannot hold for an overlay; what is pinned here is
    the part that can: Save is inside <main>, the corner button never covers it, and the
    overlay covers it only while open."""
    base = app_with_agent.base_url
    page.set_viewport_size({"width": 1024, "height": 768})
    _open(page, base, f"agents/{_nav.seg(app_with_agent.agent_name)}")
    save = page.locator('[data-testid="save-agent-btn"]')
    expect(save).to_be_visible(timeout=8000)
    main, s = _box(page, "#main-content"), save.bounding_box()
    save_box = {"l": s["x"], "t": s["y"], "r": s["x"] + s["width"], "b": s["y"] + s["height"]}
    assert main["l"] <= save_box["l"] and save_box["r"] <= main["r"]
    assert not _intersects(save_box, _box(page, BTN))
    assert _top_at_centre_is(page, '[data-testid="save-agent-btn"]')  # not intercepted
    page.locator(BTN).click()
    expect(page.locator(DRAWER)).to_have_attribute("data-mode", "overlay")
    assert _intersects(save_box, _box(page, DRAWER))  # open: the overlay covers it
    page.keyboard.press("Escape")
    expect(page.locator(DRAWER)).to_be_hidden()
    assert _top_at_centre_is(page, '[data-testid="save-agent-btn"]')  # closed again: reachable


# ── The "Looking at" line ───────────────────────────────────────────────────


def test_the_looking_at_line_follows_the_page(app_with_agent: SeededApp, page: Page) -> None:
    base = app_with_agent.base_url
    mcp_id = seed_mcp_source(base, "Docs server")
    agent = app_with_agent.agent_name
    _open(page, base, "library/mcp/~new")
    page.locator(BTN).click()
    ctx = page.locator(CONTEXT)
    expect(ctx).to_have_text("Looking at Library › MCP servers › New MCP server")
    # An item change within the destination.
    page.evaluate(f"() => App.router.go('library/mcp/{mcp_id}')")
    expect(ctx).to_have_text("Looking at Library › MCP servers › Docs server", timeout=8000)
    # A destination change.
    page.evaluate(f"() => App.router.go('agents/{_nav.seg(agent)}/tools')")
    expect(ctx).to_have_text(f"Looking at Agents › {agent} › Tools", timeout=8000)
    page.evaluate("() => App.router.go('settings/appearance')")
    expect(ctx).to_have_text("Looking at Settings › Appearance", timeout=8000)
    # A save-create's sync (a ~new route canonicalised to the new item).
    page.evaluate("() => App.router.go('library/mcp/~new')")
    expect(ctx).to_have_text("Looking at Library › MCP servers › New MCP server", timeout=8000)
    page.evaluate("() => App.router.sync('studio', 'mcp-sources/fresh', {name: 'Brand new'})")
    expect(ctx).to_have_text("Looking at Library › MCP servers › Brand new")


@pytest.mark.parametrize(
    ("route", "line"),
    [
        ("agents/~new", "Agents › New Agent"),
        ("library/providers/~new", "Library › Model providers › New model provider"),
        ("library/knowledge/~new", "Library › Knowledge bases › New knowledge base"),
        ("library/mcp/~new", "Library › MCP servers › New MCP server"),
        ("library/connectors/~new", "Library › Connectors › New Connector"),
        ("library/secrets/~new", "Library › Secrets › New secret"),
    ],
)
def test_the_looking_at_line_uses_the_create_editor_names(
    app_with_agent: SeededApp, page: Page, route: str, line: str
) -> None:
    """Squawk 0396: a create route reads the server's page-line words, not 'New'."""
    _open(page, app_with_agent.base_url, route)
    page.locator(BTN).click()
    expect(page.locator(CONTEXT)).to_have_text(f"Looking at {line}", timeout=8000)


def test_a_cold_deep_link_to_an_item_gets_its_name_when_the_store_loads(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    mcp_id = seed_mcp_source(base, "Deep linked")
    _open(page, base, f"library/mcp/{mcp_id}")
    page.locator(BTN).click()
    expect(page.locator(CONTEXT)).to_have_text(
        "Looking at Library › MCP servers › Deep linked", timeout=8000
    )


# ── The setup state ─────────────────────────────────────────────────────────


def test_setup_state_then_ready(app_with_agent: SeededApp, page: Page) -> None:
    base = app_with_agent.base_url
    _open(page, base, "library")
    page.locator(BTN).click()
    setup = page.locator(SETUP)
    # [needs a model]: the chat banner's sentence and one link to Settings.
    expect(setup).to_be_visible()
    sentence = page.evaluate("() => App.chat.gleepglorpBanner('needs_model')")
    expect(setup).to_contain_text(sentence)
    action = page.locator(SETUP_ACTION)
    expect(action).to_have_text("Choose a model")
    expect(action).to_have_attribute("href", _nav.href("settings/gleepglorp"))
    # [provider removed]: its own sentence.
    page.evaluate(
        "() => App.gleepglorp.prime(Object.assign({}, App.gleepglorp.peek().value,"
        " {state: 'provider_missing'}))"
    )
    expect(setup).to_contain_text(
        page.evaluate("() => App.chat.gleepglorpBanner('provider_missing')")
    )
    # The link goes to Settings > GleepGlorp.
    action.click()
    _nav.expect_route(page, "settings/gleepglorp")
    # [ready]: no setup block, and the body slot holds the chat (M36 F3 L3).
    page.evaluate(
        "() => App.gleepglorp.prime(Object.assign({}, App.gleepglorp.peek().value,"
        " {state: 'ready'}))"
    )
    expect(setup).to_be_hidden()
    assert page.evaluate("(s) => document.querySelector(s).children.length", SLOT) > 0


def test_a_ready_state_from_the_server_has_no_setup_block(
    app_with_agent: SeededApp, page: Page
) -> None:
    _ready(app_with_agent)
    _open(page, app_with_agent.base_url, "agents")
    page.locator(BTN).click()
    expect(page.locator(DRAWER)).to_be_visible()
    expect(page.locator(SETUP)).to_be_hidden()
    expect(page.locator(SLOT)).to_be_attached()


# ── The button never covers content ─────────────────────────────────────────

_LAST_CONTROL_JS = """() => {
  const sel = '.area-studio .studio-editor, .area-studio .studio-section-content, '
    + '.area-admin .admin-content';
  const containers = Array.from(document.querySelectorAll(sel))
    .filter((c) => c.getClientRects().length && c.scrollHeight > 0);
  const c = containers.find((x) => x.closest('.content-panel.active')) || containers[0];
  c.scrollTop = c.scrollHeight;
  const focusable = Array.from(
    c.querySelectorAll('button, a[href], input, select, textarea, [tabindex="0"]'))
    .filter((e) => !e.disabled && e.getClientRects().length
      && getComputedStyle(e).visibility !== 'hidden'
      && !(e.tagName === 'INPUT' && (e.type === 'checkbox' || e.type === 'radio'))
      && e.getBoundingClientRect().width >= 8 && e.getBoundingClientRect().height >= 8);
  const last = focusable[focusable.length - 1];
  last.setAttribute('data-gg-last', '1');
  return {scrollable: c.scrollHeight > c.clientHeight, count: focusable.length};
}"""


@pytest.mark.parametrize(
    "route",
    ["library/mcp/~new", "settings/prompts", "settings/tools", "AGENT_TOOLS"],
)
def test_the_last_control_of_a_scrolled_page_is_clear_of_the_button(
    app_with_agent: SeededApp, page: Page, route: str
) -> None:
    base = app_with_agent.base_url
    if route == "AGENT_TOOLS":
        route = f"agents/{_nav.seg(app_with_agent.agent_name)}/tools"
    page.set_viewport_size({"width": 1280, "height": 560})
    _open(page, base, route)
    expect(page.locator(BTN)).to_be_visible()
    page.wait_for_timeout(500)
    info = page.evaluate(_LAST_CONTROL_JS)
    assert info["count"] > 0, info
    last = page.locator('[data-gg-last="1"]')
    page.wait_for_timeout(100)
    lb, bb = _box(page, '[data-gg-last="1"]'), _box(page, BTN)
    assert not _intersects(lb, bb), (route, lb, bb)
    # A real click, no force: the button does not intercept it. (Scroll the control into view
    # first only by the container's own bottom position; Playwright's own scroll stays a no-op.)
    last.click(trial=True, timeout=5000)


# ── Jump to ─────────────────────────────────────────────────────────────────


def _jump_open(page: Page) -> None:
    page.locator(JUMP).click()
    expect(page.locator(JUMP_INPUT)).to_be_visible()


def test_jump_to_asks_gleepglorp_off_chats_only_and_while_enabled(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    _open(page, base, "library")
    _jump_open(page)
    page.locator(JUMP_INPUT).fill("ask")
    row = page.locator(ASK_ROW)
    expect(row).to_be_visible()
    expect(row).to_contain_text("Ask GleepGlorp")
    page.keyboard.press("Enter")
    # The palette is gone, the drawer is open and focus is on its setup link (M36 F3 L3).
    expect(page.locator(JUMP_INPUT)).to_have_count(0)
    expect(page.locator(DRAWER)).to_be_visible()
    page.wait_for_function(
        "() => document.activeElement"
        " && document.activeElement.dataset.testid === 'gg-drawer-setup-action'"
    )
    # Open again from the palette while it is open: focus goes to the setup link, not a second
    # open.
    page.locator("#main-content").focus()
    _jump_open(page)
    page.locator(JUMP_INPUT).fill("ask")
    page.keyboard.press("Enter")
    page.wait_for_function(
        "() => document.activeElement"
        " && document.activeElement.dataset.testid === 'gg-drawer-setup-action'"
    )

    # On Chats the candidate is absent (the GleepGlorp candidate starts a chat there).
    _nav.open_destination(page, "chats")
    _jump_open(page)
    page.locator(JUMP_INPUT).fill("ask")
    expect(page.locator(ASK_ROW)).to_have_count(0)
    page.keyboard.press("Escape")

    # Off: absent everywhere.
    _put(base, enabled=False)
    _open(page, base, "library")
    _jump_open(page)
    page.locator(JUMP_INPUT).fill("ask")
    expect(page.locator(ASK_ROW)).to_have_count(0)
    page.keyboard.press("Escape")


def test_the_empty_query_never_lists_ask_gleepglorp_ahead_of_the_board_order(
    app_with_agent: SeededApp, page: Page
) -> None:
    _open(page, app_with_agent.base_url, "library")
    kinds = page.evaluate("() => App.jumpTo.match('').map((c) => c.kind)")
    assert "gleepglorp-ask" not in kinds[:4], kinds
