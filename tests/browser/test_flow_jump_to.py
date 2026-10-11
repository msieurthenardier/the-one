# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""The jump-to palette and Ctrl K (M25 F4 L7, flight DD9, DD10, DD14, DD15 A10/A11/A17).

The rail's bottom control (``rail-jump-to``) and a shell-level Ctrl K (Meta K on
macOS) open ``App.jumpTo``: an ``App.ui.searchList`` in an ``App.ui.modal`` chooser
named by ``ariaLabel`` "Jump to" (``jump-to``, input ``jump-to-input``, rows
``jump-to-result``, its own "Esc" ``jump-to-close``). Candidates in board order
(agents A-Z, chats newest first, New chat…, knowledge bases, MCP servers,
connectors, Settings pages), the first 8 matches of a case-insensitive substring
over ``label + " " + where``. The EMPTY query is a mix instead (flight 4 leg 9, the
operator's DD13 option C): up to 3 recent chats, New chat…, up to 4 recently used
agents, then the board order, 8 in total. A pick closes the palette FIRST, then goes through the
router's leave guard with the captured opener, so a dirty editor asks exactly once.

Chromium; falls in the ``shared`` lane (the complement: no ``run-tests.sh`` glob
claims ``test_flow_jump_to*``).
"""

from __future__ import annotations

import json

import pytest
from browser import _chats, _lists, _nav
from browser._a11y_resolvers import assert_controls_labelled_and_described
from browser.seeders import (
    SeededApp,
    seed_connector,
    seed_knowledge_base,
    seed_mcp_source,
    seed_mock_agent,
    seed_session,
)
from playwright.sync_api import Page, Route, expect

pytestmark = pytest.mark.browser

PALETTE = '[data-testid="jump-to"]'
INPUT = '[data-testid="jump-to-input"]'
RESULT = '[data-testid="jump-to-result"]'
CLOSE = '[data-testid="jump-to-close"]'
RAIL_JUMP = '[data-testid="rail-jump-to"]'
DIALOG = '[data-testid="confirm-dialog-overlay"]'
STAY = '[data-testid="modal-cancel-btn"]'
CONTINUE = '[data-testid="modal-confirm-btn"]'
DESCRIPTION = '[data-field="description"]'

PLACEHOLDER = "Jump to an agent, chat, library item or setting"
SETTINGS_PAGES = [
    ("appearance", "Appearance", "Settings · General"),
    ("date-and-time", "Date and time", "Settings · General"),
    ("prompts", "Prompts", "Settings · General"),
    ("encryption", "Encryption", "Settings · General"),
    ("providers", "Providers", "Settings"),
    ("tools", "Built-in tools", "Settings · Defaults for agents"),
    ("knowledge-indexing", "Knowledge indexing", "Settings · Defaults for agents"),
    ("design-language", "Design language", "Settings · Developer"),
]

_ROWS_JS = """() => Array.from(document.querySelectorAll('[data-testid="jump-to-result"]')).map((r) => [
  r.dataset.kind, r.dataset.id, r.querySelector('.ui-search-list-label').textContent,
  (r.querySelector('.ui-search-list-meta') || {}).textContent || null])"""

_ACTIVE_JS = """() => { const i = document.querySelector('[data-testid="jump-to-input"]');
  const id = i && i.getAttribute('aria-activedescendant'); const r = id && document.getElementById(id);
  return r ? [r.dataset.kind, r.dataset.id, r.getAttribute('aria-selected')] : null; }"""

_FOCUSED_JS = "() => { const a = document.activeElement; return a ? (a.dataset.testid || a.dataset.field || a.id || a.tagName) : null; }"

# Records every App.confirmDialog call with what was open at that moment: the
# leave guard's confirm must open with NO other modal in the stack (the palette
# closed first, AC10). App.nav looks the adapter up at call time; isOpen is kept.
_SPY_CONFIRM_JS = """() => {
  const orig = App.confirmDialog;
  window.__confirmCalls = [];
  const spy = function () {
    window.__confirmCalls.push({anyOpen: App.ui.modal.anyOpen(),
      openDialogs: document.querySelectorAll('dialog[open]').length,
      palette: document.querySelectorAll('[data-testid="jump-to"]').length});
    return orig.apply(this, arguments);
  };
  spy.isOpen = orig.isOpen;
  App.confirmDialog = spy;
  return true;
}"""


def _rows(page: Page) -> list[list[str | None]]:
    return page.evaluate(_ROWS_JS)


def _focused(page: Page) -> str | None:
    return page.evaluate(_FOCUSED_JS)


def _open_with_keys(page: Page) -> None:
    page.keyboard.press("Control+k")
    expect(page.locator(PALETTE)).to_be_visible()
    expect(page.locator(INPUT)).to_be_focused()


def _jump(page: Page, query: str, kind: str, item_id: str) -> None:
    """Open the palette with Ctrl K, type *query*, move the active row to the
    (kind, id) row with the arrow keys, and press Enter."""
    _open_with_keys(page)
    page.locator(INPUT).fill(query)
    row = page.locator(f'{RESULT}[data-kind="{kind}"][data-id="{item_id}"]')
    expect(row).to_be_visible()
    for _ in range(16):
        rows = [r[:2] for r in _rows(page)]
        active = page.evaluate(_ACTIVE_JS)
        if active and active[:2] == [kind, item_id]:
            break
        here = rows.index(active[:2]) if active and active[:2] in rows else 0
        page.locator(INPUT).press("ArrowDown" if rows.index([kind, item_id]) > here else "ArrowUp")
    assert page.evaluate(_ACTIVE_JS)[:2] == [kind, item_id]
    page.locator(INPUT).press("Enter")
    expect(page.locator(PALETTE)).to_have_count(0)


def _blank_title(page: Page, session_id: str) -> None:
    """Serve session *session_id* with an empty title (the server stores an
    empty title as "New chat", so the palette's "Untitled chat" fallback is
    reached only through the wire)."""

    def handler(route: Route) -> None:
        if route.request.method != "GET":
            route.continue_()
            return
        response = route.fetch()
        rows = response.json()
        for row in rows:
            if row.get("id") == session_id:
                row["title"] = ""
        route.fulfill(response=response, body=json.dumps(rows))

    page.route("**/api/chat/sessions", handler)


def _wait_for_rows(page: Page, *kinds: str) -> None:
    for kind in kinds:
        expect(page.locator(f'{RESULT}[data-kind="{kind}"]').first).to_be_visible()


def _boot(page: Page, base: str, route: str) -> None:
    _nav.goto(page, base, route)
    expect(page.locator(RAIL_JUMP)).to_be_visible(timeout=8000)
    dest = route.split("/")[0]
    expect(_nav.destination_panel(page, dest)).to_be_visible(timeout=8000)


def _open_editor(page: Page, base: str, name: str) -> None:
    _nav.goto(page, base, f"agents/{_nav.seg(name)}")
    expect(page.locator('[data-testid="tab-general"]')).to_be_visible(timeout=8000)
    expect(page.locator(".editor-title")).to_have_text(name, timeout=8000)


@pytest.fixture
def world(app_with_agent: SeededApp) -> dict:
    """Two agents, five chats (two sharing a timestamp, one untitled with no
    agent, one titled like an agent), a knowledge base, an MCP server and a
    connector."""
    base, pid = app_with_agent.base_url, app_with_agent.provider_id
    seed_mock_agent(base, pid, name="Alpha")
    out = {
        "base": base,
        "agent": app_with_agent.agent_name,  # "test-agent"
        "kb": seed_knowledge_base(base, "Team wiki"),
        "mcp": seed_mcp_source(base, "GitHub", tools=["a", "b"]),
        "connector": seed_connector(base, "Discord bot"),
        "newest": seed_session(base, "Alpha", "Newest chat", "2026-10-05T10:00:00Z"),
        "tie_one": seed_session(base, app_with_agent.agent_name, "Tie one", "2026-10-04T10:00:00Z"),
        "tie_two": seed_session(base, "Alpha", "Tie two", "2026-10-04T10:00:00Z"),
        # No agent; its title is blanked on the wire where a test needs it.
        "untitled": seed_session(base, None, "", "2026-10-03T10:00:00Z"),
        "alpha_chat": seed_session(
            base, app_with_agent.agent_name, "Alpha", "2026-10-01T10:00:00Z"
        ),
    }
    return out


# ── The rail control (AC3) and the palette's shape (AC6, AC13) ───────────────


def test_rail_control_opens_the_palette_and_escape_returns_focus_to_it(
    app_with_agent: SeededApp, page: Page
) -> None:
    page.set_viewport_size({"width": 1440, "height": 900})
    _boot(page, app_with_agent.base_url, "agents")
    jump = page.locator(RAIL_JUMP)
    out = jump.evaluate(
        """(b) => { const r = b.getBoundingClientRect(), rail = document.querySelector('.ui-rail').getBoundingClientRect();
                    const svg = b.querySelector('svg').getBoundingClientRect();
                    return {cls: b.className, name: b.getAttribute('aria-label'), keys: b.getAttribute('aria-keyshortcuts'),
                            text: b.textContent, tag: b.tagName, size: [r.width, r.height], svg: [svg.width, svg.height],
                            bottom: rail.bottom - r.bottom, inFooter: b.parentElement.className,
                            inRail: !!b.closest('nav[aria-label="Main"]'), item: b.classList.contains('ui-rail-item')}; }"""
    )
    assert out["tag"] == "BUTTON" and out["cls"] == "btn-ghost btn-icon"
    assert out["name"] == "Jump to (Ctrl K)" and out["keys"] == "Control+K" and out["text"] == ""
    assert out["size"] == [44, 44] and out["svg"] == [16, 16]
    assert abs(out["bottom"] - 12) <= 0.5, out  # pinned 12px above the bottom edge
    assert out["inFooter"] == "ui-rail-footer" and out["inRail"] and not out["item"]
    expect(page.get_by_role("button", name="Jump to (Ctrl K)")).to_have_count(1)

    jump.click()
    palette = page.locator(PALETTE)
    expect(palette).to_be_visible()
    shape = palette.evaluate(
        """(d) => { const card = d.querySelector('.modal-dialog'), r = card.getBoundingClientRect();
                    const input = d.querySelector('[data-testid="jump-to-input"]');
                    const bar = input.parentElement, close = d.querySelector('[data-testid="jump-to-close"]');
                    const label = d.querySelector('label[for="' + input.id + '"]');
                    return {label: d.getAttribute('aria-label'), labelledby: d.hasAttribute('aria-labelledby'),
                            h2: d.querySelectorAll('h2').length, header: d.querySelectorAll('.modal-dialog-header').length,
                            card: [r.left, r.top, r.width], vw: innerWidth, placeholder: input.placeholder,
                            hiddenLabel: label && label.textContent, labelHidden: label && label.className,
                            bar: Array.from(bar.children).map((c) => c.dataset.testid || c.className || c.tagName),
                            close: [close.textContent, close.getAttribute('aria-label'), close.className],
                            footer: Array.from(d.querySelectorAll('.modal-dialog-footer span')).map((s) => [s.textContent, s.className]),
                            dismissible: true}; }"""
    )
    assert shape["label"] == "Jump to" and shape["labelledby"] is False
    assert shape["h2"] == 0 and shape["header"] == 0
    assert shape["card"][1] == 96 and shape["card"][2] == 600
    assert abs(shape["card"][0] - (shape["vw"] - 600) / 2) <= 0.5
    assert shape["placeholder"] == PLACEHOLDER
    assert (shape["hiddenLabel"], shape["labelHidden"]) == ("Jump to", "visually-hidden")
    # The input bar: the search icon, the hidden label, the input, the Esc button.
    assert shape["bar"] == ["jump-to-bar-icon", "visually-hidden", "jump-to-input", "jump-to-close"]
    assert shape["close"] == ["Esc", "Close (Esc)", "btn-ghost btn-sm"]
    assert shape["footer"] == [
        ["Ctrl K from anywhere", ""],
        ["Enter to open", ""],
    ]  # both on the left
    expect(page.locator(INPUT)).to_be_focused()
    expect(page.get_by_role("dialog", name="Jump to")).to_have_count(1)

    # Escape closes it; focus goes back to the control that opened it.
    page.keyboard.press("Escape")
    expect(palette).to_have_count(0)
    expect(jump).to_be_focused()
    # The Esc button does the same, and so does a backdrop click.
    jump.click()
    page.locator(CLOSE).click()
    expect(palette).to_have_count(0)
    expect(jump).to_be_focused()
    jump.click()
    expect(palette).to_be_visible()
    page.mouse.click(1400, 860)  # the backdrop, outside the card
    expect(palette).to_have_count(0)
    expect(jump).to_be_focused()


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_palette_resolver_active_row_and_keys(world: dict, page: Page, theme: str) -> None:
    page.add_init_script(
        f"try {{ localStorage.setItem('theme-preference', '{theme}'); }} catch (e) {{}}"
    )
    _boot(page, world["base"], "agents")
    assert page.evaluate("document.documentElement.dataset.theme") == theme
    _open_with_keys(page)
    _wait_for_rows(page, "agent", "chat")
    assert_controls_labelled_and_described(page, PALETTE)
    # The first row is active (A10): aria-activedescendant on the input, aria-selected on the row.
    # The empty query's mix starts with the newest chat (leg 9); wait for the
    # recent agents so the list is settled.
    _wait_for_rows(page, "action")
    expect(page.locator(f'{RESULT}[data-kind="agent"][data-id="test-agent"]')).to_be_visible()
    second = _rows(page)[1][:2]
    assert page.evaluate(_ACTIVE_JS) == ["chat", world["newest"], "true"]
    assert page.locator(f'{RESULT}[aria-selected="true"]').count() == 1
    page.keyboard.press("ArrowDown")
    assert page.evaluate(_ACTIVE_JS) == [*second, "true"]
    page.keyboard.press("ArrowUp")
    assert page.evaluate(_ACTIVE_JS) == ["chat", world["newest"], "true"]
    # The pointer sets the active row too.
    page.locator(f'{RESULT}[data-kind="action"]').hover()
    assert page.evaluate(_ACTIVE_JS) == ["action", "new-chat", "true"]
    assert page.locator(f'{RESULT}[aria-selected="true"]').count() == 1
    # Focus never left the input; Enter opens the active row (here: the second agent).
    page.locator(f'{RESULT}[data-kind="agent"][data-id="Alpha"]').hover()
    page.keyboard.press("ArrowDown")
    expect(page.locator(INPUT)).to_be_focused()
    page.keyboard.press("Enter")
    expect(page.locator(PALETTE)).to_have_count(0)
    _nav.wait_for_route_prefix(page, "agents/test-agent")


# ── Ctrl K (AC4, AC12) ────────────────────────────────────────────────────────


def test_ctrl_k_from_agents_from_inside_a_field_and_from_settings(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    _boot(page, base, "agents")
    page.evaluate(
        """() => { window.__prevented = []; window.addEventListener('keydown', (e) => {
             if (e.key.toLowerCase() === 'k') window.__prevented.push(e.defaultPrevented); }); return true; }"""
    )
    # From Agents with nothing focused: the opener is <body>, so focus returns to <main>.
    _open_with_keys(page)
    assert page.evaluate("window.__prevented") == [True]
    page.keyboard.press("Escape")
    expect(page.locator(PALETTE)).to_have_count(0)
    assert _focused(page) == "main-content"

    # From inside a text field: Ctrl K is not a text-editing key here.
    flt = page.locator('[data-testid="agents-filter"]')
    flt.click()
    flt.press_sequentially("te")
    _open_with_keys(page)
    expect(flt).to_have_value("te")  # nothing was typed into the field
    page.keyboard.press("Escape")
    expect(page.locator(PALETTE)).to_have_count(0)
    expect(flt).to_be_focused()  # the opener

    # From Settings: focus goes back to whatever held it at Ctrl K.
    _nav.open_destination(page, "settings")
    expect(_nav.destination_panel(page, "settings")).to_be_visible()
    held = _focused(page)
    _open_with_keys(page)
    page.keyboard.press("Escape")
    expect(page.locator(PALETTE)).to_have_count(0)
    assert _focused(page) == held


def test_ctrl_k_while_the_palette_is_open_focuses_its_input(
    app_with_agent: SeededApp, page: Page
) -> None:
    _boot(page, app_with_agent.base_url, "agents")
    _open_with_keys(page)
    page.keyboard.press("Tab")
    expect(page.locator(CLOSE)).to_be_focused()
    page.keyboard.press("Control+k")
    expect(page.locator(INPUT)).to_be_focused()
    expect(page.locator(PALETTE)).to_have_count(1)
    assert page.evaluate("document.querySelectorAll('dialog[open]').length") == 1


def test_ctrl_k_while_the_picker_is_open_does_nothing(
    app_with_agent: SeededApp, page: Page
) -> None:
    # The agent picker is open: Ctrl K leaves it in charge.
    _boot(page, app_with_agent.base_url, "chats")
    _chats.open_picker(page)
    page.keyboard.press("Control+k")
    page.wait_for_timeout(200)
    expect(page.locator(PALETTE)).to_have_count(0)
    expect(_chats.picker(page)).to_be_visible()
    expect(_chats.picker_search(page)).to_be_focused()
    page.keyboard.press("Escape")
    expect(_chats.picker(page)).to_have_count(0)


def test_ctrl_k_while_the_confirm_is_open_does_nothing(
    app_with_agent: SeededApp, page: Page
) -> None:
    # The leave guard's confirm is open: Ctrl K leaves it in charge.
    base, name = app_with_agent.base_url, app_with_agent.agent_name
    _open_editor(page, base, name)
    page.locator(DESCRIPTION).fill("an unsaved edit")
    _nav.open_destination(page, "settings")
    expect(page.locator(DIALOG)).to_have_count(1)
    expect(page.locator(STAY)).to_be_focused()
    page.keyboard.press("Control+k")
    page.wait_for_timeout(200)
    expect(page.locator(PALETTE)).to_have_count(0)
    expect(page.locator(DIALOG)).to_have_count(1)
    expect(page.locator(STAY)).to_be_focused()
    page.keyboard.press("Enter")  # Stay
    expect(page.locator(DIALOG)).to_have_count(0)
    expect(page.locator(DESCRIPTION)).to_have_value("an unsaved edit")


def test_modified_ctrl_k_and_an_ime_composition_do_nothing(
    app_with_agent: SeededApp, page: Page
) -> None:
    _boot(page, app_with_agent.base_url, "agents")
    for combo in ("Control+Shift+k", "Control+Alt+k", "Meta+k", "Control+Meta+k", "k"):
        page.keyboard.press(combo)
        page.wait_for_timeout(100)
        expect(page.locator(PALETTE)).to_have_count(0)
    dispatch = """(init) => {
      const ev = new KeyboardEvent('keydown', Object.assign({bubbles: true, cancelable: true}, init.ev));
      if (init.keyCode) Object.defineProperty(ev, 'keyCode', {get: () => init.keyCode});
      (document.activeElement || document.body).dispatchEvent(ev);
      return ev.defaultPrevented;
    }"""
    # An IME composition: isComposing, or the 229 keyCode.
    assert (
        page.evaluate(
            dispatch, {"ev": {"key": "k", "code": "KeyK", "ctrlKey": True, "isComposing": True}}
        )
        is False
    )
    assert (
        page.evaluate(
            dispatch, {"ev": {"key": "k", "code": "KeyK", "ctrlKey": True}, "keyCode": 229}
        )
        is False
    )
    page.wait_for_timeout(100)
    expect(page.locator(PALETTE)).to_have_count(0)
    # Positive controls on the same path: Caps Lock (key "K") and a non-Latin
    # layout (code KeyK) both open it.
    assert page.evaluate(dispatch, {"ev": {"key": "K", "code": "KeyK", "ctrlKey": True}}) is True
    expect(page.locator(PALETTE)).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator(PALETTE)).to_have_count(0)
    assert page.evaluate(dispatch, {"ev": {"key": "л", "code": "KeyK", "ctrlKey": True}}) is True
    expect(page.locator(PALETTE)).to_be_visible()


def test_platform_detector_and_key_matcher_unit_cases(app_clean: str, page: Page) -> None:
    _boot(page, app_clean, "chats")
    cases = [
        ({"platform": "MacIntel"}, True),
        ({"platform": "Win32"}, False),
        ({"platform": "Linux x86_64"}, False),
        ({"platform": "iPhone"}, True),
        ({"platform": "iPad"}, True),
        ({"userAgentData": {"platform": "macOS"}}, True),
        ({"userAgentData": {"platform": "Windows"}, "platform": "MacIntel"}, False),  # UA-CH wins
        (
            {"userAgentData": {"platform": ""}, "platform": "MacIntel"},
            True,
        ),  # empty UA-CH falls back
        ({}, False),
    ]
    for nav, want in cases:
        assert page.evaluate("(n) => App.shortcuts.isMacPlatform(n)", nav) is want, nav
    assert page.evaluate("() => App.shortcuts.isMacPlatform(null)") is False
    keys = [
        ({"key": "k", "ctrlKey": True}, False, True),
        ({"key": "K", "ctrlKey": True}, False, True),
        ({"key": "л", "code": "KeyK", "ctrlKey": True}, False, True),
        ({"key": "k", "ctrlKey": True, "metaKey": True}, False, False),
        ({"key": "k", "ctrlKey": True, "shiftKey": True}, False, False),
        ({"key": "k", "ctrlKey": True, "altKey": True}, False, False),
        ({"key": "k", "metaKey": True}, False, False),
        ({"key": "j", "ctrlKey": True}, False, False),
        ({"key": "k", "metaKey": True}, True, True),
        ({"key": "k", "ctrlKey": True}, True, False),  # kill-line on macOS
        ({"key": "k", "ctrlKey": True, "metaKey": True}, True, False),
        ({"key": "k", "metaKey": True, "shiftKey": True}, True, False),
        ({"key": "k", "metaKey": True, "altKey": True}, True, False),
    ]
    for ev, mac, want in keys:
        got = page.evaluate("([e, mac]) => App.shortcuts.isJumpToKey(e, mac)", [ev, mac])
        assert got is want, (ev, mac)
    assert page.evaluate("() => App.shortcuts.jumpToKeys(false)") == {
        "hint": "Ctrl K",
        "aria": "Control+K",
    }
    assert page.evaluate("() => App.shortcuts.jumpToKeys(true)") == {
        "hint": "⌘ K",
        "aria": "Meta+K",
    }


def test_macos_takes_meta_k_and_shows_the_command_copy(
    app_with_agent: SeededApp, page: Page
) -> None:
    page.add_init_script(
        """Object.defineProperty(Navigator.prototype, 'platform', {get: () => 'MacIntel', configurable: true});
           Object.defineProperty(Navigator.prototype, 'userAgentData', {get: () => undefined, configurable: true});"""
    )
    _boot(page, app_with_agent.base_url, "agents")
    jump = page.locator(RAIL_JUMP)
    expect(jump).to_have_attribute("aria-label", "Jump to (⌘ K)")
    expect(jump).to_have_attribute("aria-keyshortcuts", "Meta+K")
    page.keyboard.press("Control+k")  # kill-line on macOS: not ours
    page.wait_for_timeout(150)
    expect(page.locator(PALETTE)).to_have_count(0)
    page.keyboard.press("Meta+k")
    expect(page.locator(PALETTE)).to_be_visible()
    expect(page.locator(f"{PALETTE} .modal-dialog-footer span").first).to_have_text(
        "⌘ K from anywhere"
    )


# ── Candidates, order, cap and matching (AC7, AC8) ───────────────────────────


def _wait_for_exact_rows(page: Page, expected: list, timeout_ms: int = 8000) -> None:
    """Poll until the palette's rows equal *expected* (the collections load
    independently, so the empty-query mix changes as they arrive)."""
    waited = 0
    while _rows(page) != expected and waited < timeout_ms:
        page.wait_for_timeout(100)
        waited += 100
    assert _rows(page) == expected


def _chat_row(sid: str, title: str, agent: str) -> list:
    return ["chat", sid, title, "Chat · " + agent]


def _agent_row(name: str) -> list:
    return ["agent", name, name, "Agent"]


NEW_CHAT_ROW = ["action", "new-chat", "New chat…", "Action"]


def test_empty_query_mixes_recent_chats_new_chat_and_recent_agents(world: dict, page: Page) -> None:
    _blank_title(page, world["untitled"])
    _boot(page, world["base"], "agents")
    _open_with_keys(page)
    _wait_for_rows(page, "chat", "agent")  # the sessions store is loaded
    order = page.evaluate(
        """() => App.store.peek('sessions').value.filter((s) => s.title === 'Tie one' || s.title === 'Tie two').map((s) => s.title)"""
    )
    ties = {"Tie one": world["tie_one"], "Tie two": world["tie_two"]}
    tie_rows = [_chat_row(ties[t], t, "Alpha" if t == "Tie two" else "test-agent") for t in order]
    _wait_for_exact_rows(
        page,
        [
            _chat_row(world["newest"], "Newest chat", "Alpha"),
            *tie_rows,  # equal timestamps keep the store's order
            NEW_CHAT_ROW,
            _agent_row("Alpha"),
            _agent_row("test-agent"),
            _chat_row(world["untitled"], "Untitled chat", "Default agent"),
            _chat_row(world["alpha_chat"], "Alpha", "test-agent"),
        ],
    )
    # The first row is active once every collection has arrived (DD10).
    assert page.evaluate(_ACTIVE_JS) == ["chat", world["newest"], "true"]
    # No group captions (the board draws none); the where text is not mono.
    assert page.locator(f"{PALETTE} .ui-search-list-caption").count() == 0
    assert page.locator(f"{PALETTE} .ui-search-list-meta-mono").count() == 0


def test_empty_query_caps_three_chats_and_four_recent_agents(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, pid = app_with_agent.base_url, app_with_agent.provider_id
    names = ["test-agent", "Echo", "Delta", "Charlie", "Bravo", "Alpha"]
    for n in names[1:]:
        seed_mock_agent(base, pid, name=n)
    sids = [
        seed_session(base, n, f"chat-{i}", f"2026-10-0{6 - i}T10:00:00Z")
        for i, n in enumerate(names)
    ]
    _boot(page, base, "chats")
    _open_with_keys(page)
    _wait_for_exact_rows(
        page,
        [
            _chat_row(sids[0], "chat-0", "test-agent"),
            _chat_row(sids[1], "chat-1", "Echo"),
            _chat_row(sids[2], "chat-2", "Delta"),
            NEW_CHAT_ROW,
            _agent_row("test-agent"),
            _agent_row("Echo"),
            _agent_row("Delta"),
            _agent_row("Charlie"),
        ],
    )
    rows = _rows(page)
    assert len({(r[0], r[1]) for r in rows}) == len(rows)  # no duplicate in the fill
    assert page.evaluate("() => [App.jumpTo.RECENT_CHATS, App.jumpTo.RECENT_AGENTS]") == [3, 4]


def test_empty_query_leaves_a_connector_only_agent_out_of_the_recent_agents(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, pid = app_with_agent.base_url, app_with_agent.provider_id
    for n in ("Conn", "Web1", "Web2"):
        seed_mock_agent(base, pid, name=n)
    conn = seed_session(base, "Conn", "from discord", "2026-10-06T10:00:00Z", platform="discord")
    w1 = seed_session(base, "Web1", "web one", "2026-10-05T10:00:00Z")
    w2 = seed_session(base, "Web2", "web two", "2026-10-04T10:00:00Z")
    _boot(page, base, "chats")
    _open_with_keys(page)
    # The connector chat is a recent chat; Conn is not a recent agent (it is
    # only the A-Z fill, after Web1 and Web2).
    _wait_for_exact_rows(
        page,
        [
            _chat_row(conn, "from discord", "Conn"),
            _chat_row(w1, "web one", "Web1"),
            _chat_row(w2, "web two", "Web2"),
            NEW_CHAT_ROW,
            _agent_row("Web1"),
            _agent_row("Web2"),
            _agent_row("Conn"),
            _agent_row("test-agent"),
        ],
    )


def test_empty_query_with_no_sessions_is_new_chat_agents_then_the_board_order(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, pid = app_with_agent.base_url, app_with_agent.provider_id
    for n in ("Alpha", "Bravo"):
        seed_mock_agent(base, pid, name=n)
    _boot(page, base, "chats")
    _open_with_keys(page)
    _wait_for_exact_rows(
        page,
        [
            NEW_CHAT_ROW,
            _agent_row("Alpha"),
            _agent_row("Bravo"),
            _agent_row("test-agent"),
            *[["settings", s, label, where] for s, label, where in SETTINGS_PAGES[:4]],
        ],
    )
    assert page.evaluate(_ACTIVE_JS) == ["action", "new-chat", "true"]


def test_empty_query_shows_a_deleted_agents_chat_but_not_the_agent(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    ghost = seed_session(base, "Ghost", "ghost chat", "2026-10-06T10:00:00Z")
    mine = seed_session(base, app_with_agent.agent_name, "mine", "2026-10-05T10:00:00Z")
    _boot(page, base, "chats")
    _open_with_keys(page)
    _wait_for_exact_rows(
        page,
        [
            _chat_row(ghost, "ghost chat", "Ghost"),
            _chat_row(mine, "mine", "test-agent"),
            NEW_CHAT_ROW,
            _agent_row("test-agent"),
            *[["settings", s, label, where] for s, label, where in SETTINGS_PAGES[:4]],
        ],
    )
    assert not [r for r in _rows(page) if r[0] == "agent" and r[1] == "Ghost"]


def test_matching_finds_each_kind_case_insensitively_and_has_an_empty_state(
    world: dict, page: Page
) -> None:
    _blank_title(page, world["untitled"])
    _boot(page, world["base"], "agents")
    _open_with_keys(page)
    _wait_for_rows(page, "agent", "chat")
    expect(
        page.locator(f'{RESULT}[data-kind="chat"][data-id="{world["alpha_chat"]}"]')
    ).to_be_visible()
    inp = page.locator(INPUT)
    inp.fill("library")
    expect(page.locator(RESULT)).to_have_count(3)
    assert _rows(page) == [
        ["knowledge-base", world["kb"], "Team wiki", "Library · Knowledge base"],
        ["mcp-server", world["mcp"], "GitHub", "Library · MCP server"],
        ["connector", world["connector"], "Discord bot", "Library · Connector"],
    ]
    # A chat titled like an agent: both rows, told apart by their where text.
    inp.fill("alpha")
    expect(page.locator(RESULT)).to_have_count(4)
    assert _rows(page) == [
        ["agent", "Alpha", "Alpha", "Agent"],
        ["chat", world["newest"], "Newest chat", "Chat · Alpha"],
        ["chat", world["tie_two"], "Tie two", "Chat · Alpha"],
        ["chat", world["alpha_chat"], "Alpha", "Chat · test-agent"],
    ]
    # Trimmed and case-insensitive, over label + where.
    inp.fill("   DEFAULTS FOR AGENTS ")
    expect(page.locator(RESULT)).to_have_count(2)
    assert [r[1] for r in _rows(page)] == ["tools", "knowledge-indexing"]
    inp.fill("settings")
    # Eight pages now, and the palette shows at most 8 matches.
    expect(page.locator(RESULT)).to_have_count(8)
    assert [[r[1], r[2], r[3]] for r in _rows(page)] == [list(p) for p in SETTINGS_PAGES]
    inp.fill("default agent")
    expect(page.locator(RESULT)).to_have_count(1)
    assert _rows(page)[0][:3] == ["chat", world["untitled"], "Untitled chat"]
    inp.fill("new chat")
    assert _rows(page) == [["action", "new-chat", "New chat…", "Action"]]
    # The cap holds for a query too: "a" matches every candidate here.
    inp.fill("a")
    expect(page.locator(RESULT)).to_have_count(8)
    # No match.
    inp.fill("zzz")
    expect(page.locator(RESULT)).to_have_count(0)
    empty = page.locator(f"{PALETTE} .ui-search-list-empty")
    expect(empty).to_be_visible()
    expect(empty).to_contain_text('No matches for "zzz".')
    expect(page.locator(f"{PALETTE} [role=listbox]")).to_be_hidden()
    expect(page.locator(f"{PALETTE} [role=status]")).to_have_text('No matches for "zzz".')


def test_an_empty_install_lists_new_chat_and_the_settings_pages(app_clean: str, page: Page) -> None:
    _boot(page, app_clean, "chats")
    _open_with_keys(page)
    expect(page.locator(RESULT)).to_have_count(8)
    page.wait_for_timeout(300)  # every collection has resolved (empty)
    # New chat plus the first seven pages: the empty mix is capped at 8.
    assert _rows(page) == [["action", "new-chat", "New chat…", "Action"]] + [
        ["settings", s, label, where] for s, label, where in SETTINGS_PAGES[:7]
    ]


def test_design_language_is_a_candidate_only_in_dev_mode(app_clean: str, page: Page) -> None:
    _boot(page, app_clean, "settings/appearance")
    _open_with_keys(page)
    page.locator(INPUT).fill("design")
    assert _rows(page) == [
        ["settings", "design-language", "Design language", "Settings · Developer"]
    ]
    page.keyboard.press("Enter")
    _nav.expect_route(page, "settings/design-language")
    page.wait_for_selector("[data-ui-demo]")


def test_design_language_is_not_a_candidate_without_dev_mode(app_clean: str, page: Page) -> None:
    def no_dev_mode(route: Route) -> None:
        response = route.fetch()
        body = response.json()
        body["dev_mode"] = False
        route.fulfill(response=response, body=json.dumps(body))

    page.route("**/api/config", no_dev_mode)
    _boot(page, app_clean, "settings/appearance")
    assert page.evaluate("App.config.dev_mode") is False
    _open_with_keys(page)
    page.locator(INPUT).fill("design")
    expect(page.locator(RESULT)).to_have_count(0)
    expect(page.locator(f"{PALETTE} [role=status]")).to_have_text('No matches for "design".')
    page.locator(INPUT).fill("settings")
    expect(page.locator(RESULT)).to_have_count(7)


# ── Opening a result (AC10) ──────────────────────────────────────────────────


def test_each_kind_opens_its_route(world: dict, page: Page) -> None:
    base = world["base"]
    _boot(page, base, "agents")
    # An agent: its route, and the Agents filter is cleared (it hid the agent).
    expect(_lists.list_row(page, "agents", "Alpha")).to_be_visible(timeout=8000)
    _lists.filter_agents(page, "zzz")
    expect(_lists.list_row(page, "agents", "Alpha")).to_be_hidden()
    _jump(page, "alpha", "agent", "Alpha")
    _nav.wait_for_route_prefix(page, "agents/Alpha")
    expect(page.locator('[data-testid="agents-filter"]')).to_have_value("")
    _lists.expect_selected(page, "agents", "Alpha")

    # A chat: joined at its route.
    _jump(page, "newest", "chat", world["newest"])
    _nav.expect_route(page, f"chats/{_nav.seg(world['newest'])}", timeout=8000)
    page.wait_for_function(
        "(id) => { const a = (App.areas || []).find((x) => x.id === 'chat'); const st = a && a._sessionState && a._sessionState(); return !!st && st.name === 'joined' && st.id === id; }",
        arg=world["newest"],
        timeout=8000,
    )

    # A knowledge base, by a click on its row.
    _open_with_keys(page)
    page.locator(INPUT).fill("team wiki")
    page.locator(f'{RESULT}[data-kind="knowledge-base"]').click()
    expect(page.locator(PALETTE)).to_have_count(0)
    _nav.expect_route(page, f"library/knowledge/{_nav.seg(world['kb'])}", timeout=8000)
    _lists.expect_selected(page, "library/knowledge", "Team wiki")

    # An MCP server and a connector.
    _jump(page, "github", "mcp-server", world["mcp"])
    _nav.expect_route(page, f"library/mcp/{_nav.seg(world['mcp'])}", timeout=8000)
    _jump(page, "discord", "connector", world["connector"])
    _nav.expect_route(page, f"library/connectors/{_nav.seg(world['connector'])}", timeout=8000)

    # Settings pages: the route segment, through the router's mapping.
    _jump(page, "knowledge indexing", "settings", "knowledge-indexing")
    _nav.expect_route(page, "settings/knowledge-indexing", timeout=8000)
    _lists.expect_settings_selected(page, "knowledge-indexing")
    _jump(page, "providers", "settings", "providers")
    _nav.expect_route(page, "settings/providers", timeout=8000)
    _lists.expect_settings_selected(page, "providers")
    # No dialog was ever raised: nothing was dirty.
    expect(page.locator(DIALOG)).to_have_count(0)


def test_new_chat_opens_the_agent_picker(world: dict, page: Page) -> None:
    _boot(page, world["base"], "agents")
    _jump(page, "new chat", "action", "new-chat")
    _nav.expect_route(page, "chats", timeout=8000)
    expect(_chats.picker(page)).to_be_visible(timeout=8000)
    expect(_chats.picker_search(page)).to_be_focused()
    assert page.evaluate("document.querySelectorAll('dialog[open]').length") == 1
    page.keyboard.press("Escape")
    expect(_chats.picker(page)).to_have_count(0)
    assert _focused(page) == "main-content"  # the palette's opener was <body>
    # From Chats, too: the picker opens in place.
    _jump(page, "new chat", "action", "new-chat")
    expect(_chats.picker(page)).to_be_visible(timeout=8000)


def test_a_pick_from_a_dirty_editor_asks_once_and_stay_returns_to_the_opener(
    world: dict, page: Page
) -> None:
    base, name = world["base"], world["agent"]
    _open_editor(page, base, name)
    desc = page.locator(DESCRIPTION)
    desc.fill("an unsaved edit")
    expect(page.locator('[data-testid="editor-unsaved"]')).to_have_text("Unsaved changes")
    page.evaluate(_SPY_CONFIRM_JS)
    desc.focus()  # the opener

    _jump(page, "team wiki", "knowledge-base", world["kb"])
    # Exactly one confirm, and it opened with nothing else in the modal stack:
    # the palette had closed before the router's guard ran.
    expect(page.locator(DIALOG)).to_have_count(1)
    assert page.evaluate("window.__confirmCalls") == [
        {"anyOpen": False, "openDialogs": 0, "palette": 0}
    ]
    assert page.evaluate("document.querySelectorAll('dialog[open]').length") == 1
    expect(page.locator(STAY)).to_be_focused()
    page.keyboard.press("Enter")  # Stay
    expect(page.locator(DIALOG)).to_have_count(0)
    # The edit is kept, the route unchanged, the palette stays closed, and focus
    # is back on the palette's opener.
    _nav.expect_route(page, f"agents/{_nav.seg(name)}/general")
    expect(desc).to_have_value("an unsaved edit")
    expect(page.locator('[data-testid="editor-unsaved"]')).to_have_text("Unsaved changes")
    expect(page.locator(PALETTE)).to_have_count(0)
    expect(desc).to_be_focused()

    # New chat… from the dirty editor: openPicker's own go asks once; Stay
    # keeps the edit and the picker never opens.
    _jump(page, "new chat", "action", "new-chat")
    expect(page.locator(DIALOG)).to_have_count(1)
    assert len(page.evaluate("window.__confirmCalls")) == 2
    assert page.evaluate("window.__confirmCalls")[1]["anyOpen"] is False
    page.keyboard.press("Enter")  # Stay
    expect(page.locator(DIALOG)).to_have_count(0)
    expect(_chats.picker(page)).to_have_count(0)
    expect(desc).to_have_value("an unsaved edit")
    expect(desc).to_be_focused()

    # Continue: one confirm, then the knowledge base.
    _jump(page, "team wiki", "knowledge-base", world["kb"])
    expect(page.locator(DIALOG)).to_have_count(1)
    page.locator(CONTINUE).click()
    expect(page.locator(DIALOG)).to_have_count(0)
    _nav.expect_route(page, f"library/knowledge/{_nav.seg(world['kb'])}", timeout=8000)
    assert len(page.evaluate("window.__confirmCalls")) == 3


# ── Cold data (AC11) ─────────────────────────────────────────────────────────


def test_open_force_fetches_sessions_and_leaves_a_failed_collection_out(
    world: dict, page: Page
) -> None:
    page.route("**/api/knowledge-bases", lambda route: route.fulfill(status=500, body="{}"))
    session_gets: list[str] = []
    page.on(
        "request",
        lambda r: (
            session_gets.append(r.url)
            if r.method == "GET" and r.url.endswith("/api/chat/sessions")
            else None
        ),
    )
    _boot(page, world["base"], "settings/appearance")
    before = len(session_gets)
    _open_with_keys(page)
    expect(page.locator(f'{RESULT}[data-kind="chat"]').first).to_be_visible()
    assert len(session_gets) == before + 1
    # The failed knowledge-bases read is left out; the other collections show.
    page.locator(INPUT).fill("library")
    expect(page.locator(RESULT)).to_have_count(2)
    assert [r[0] for r in _rows(page)] == ["mcp-server", "connector"]
    page.locator(INPUT).fill("agent")
    assert [r[0] for r in _rows(page)][:2] == ["agent", "agent"]
    page.keyboard.press("Escape")
    # A second open fetches sessions again (forced, though loaded).
    _open_with_keys(page)
    expect(page.locator(f'{RESULT}[data-kind="chat"]').first).to_be_visible()
    assert len(session_gets) == before + 2


def test_a_closed_palette_is_never_refreshed(world: dict, page: Page) -> None:
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    _boot(page, world["base"], "settings/appearance")
    held: list[Route] = []
    page.route("**/api/chat/sessions", lambda route: held.append(route))
    _open_with_keys(page)
    page.wait_for_function("() => true")
    for _ in range(50):
        if held:
            break
        page.wait_for_timeout(50)
    assert len(held) == 1  # the forced sessions read is in flight
    page.evaluate(
        "() => { window.__lb = document.querySelector('[data-testid=\"jump-to\"] [role=listbox]'); return true; }"
    )
    page.keyboard.press("Escape")
    expect(page.locator(PALETTE)).to_have_count(0)
    assert page.evaluate("() => window.__lb.children.length") == 0  # destroyed on close
    held[0].continue_()
    page.wait_for_function("() => App.store.peek('sessions').loaded", timeout=8000)
    page.wait_for_timeout(200)
    # The resolution did not render into the closed palette's list.
    assert page.evaluate("() => window.__lb.children.length") == 0
    assert page.evaluate("() => App.jumpTo.isOpen()") is False
    assert errors == []
