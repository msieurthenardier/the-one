"""Keyboard-operability tests (F3 leg 03).

Verifies that all interactive list rows (the Chats list's chat-row, M25 F4
leg 4a; agent-item) and the Settings nav links (M25 F3 leg 5a), plus their
inline action buttons (a chat row's delete, chip-remove), are reachable and
activatable via keyboard.

Design choices:
- Session tests use a single auto-created session (WS creates one on load).
  The "two sessions" scenario from the spec is trimmed — single-session
  Enter activation is the load-bearing assertion.
- Chip-remove keyboard test is dropped: no MCP sources are seeded in
  the default fixtures, so driving chip-add via UI would be brittle.
  The closest() dispatch fix is verified by the JS unit tests instead.
- The Settings nav tests use app_clean (no agent/provider needed for navigation).
"""

from __future__ import annotations

import re

import pytest
from browser import _chats, _lists, _nav
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_session_item_keyboard_select(app_with_agent: SeededApp, page: Page) -> None:
    """Focus the session's row, press Enter; aria-current becomes 'page'.

    F2 leg 01 retired the listbox/option roles on the session list (nested
    interactive elements under role="option" violated WCAG 4.1.2). Since M25
    F4 leg 4a the row is an App.ui.listPane link (``chat-row``) inside an
    ``<li>`` beside its delete action; the active-session signal is
    aria-current="page" (as the list and nav controls).
    """
    base_url = app_with_agent.base_url
    page.goto(base_url)

    # Bootstrap a session via the welcome listbox (no auto-create after leg 05);
    # a start is pending until its first send (M25 F4 L3b).
    _chats.start_chat(page, app_with_agent.agent_name)
    _chats.send_first(page, "hello")

    session_item = _chats.chat_row(page, _chats.current_session_id(page))
    expect(session_item).to_be_visible(timeout=5000)

    # Focus directly and press Enter
    session_item.focus()
    page.keyboard.press("Enter")

    # aria-current="page" marks the active session post-restructure.
    expect(session_item).to_have_attribute("aria-current", "page")


@pytest.mark.browser
def test_chats_list_shape(app_with_agent: SeededApp, page: Page) -> None:
    """The Chats list is an App.ui.listPane: a ``<section>`` labelled by its
    "Chats" ``<h2>``, recency-group ``<ul>``s of ``<li>``s, each holding the
    row (a native ``<a href>`` link, ``chat-row``) and, for a session, its
    sibling delete action (a native ``<button>``, ``chat-row-delete``, named
    "Delete chat: {title}"). One roving stop: only the stop row's action is
    tabbable, so Tab goes from the row to its action, then out of the list.

    M25 F4 L4a replaced ``test_session_list_shape`` (the retired
    ``<nav class="session-list">`` of ``<button class="session-item">``s).
    """
    base_url = app_with_agent.base_url
    page.goto(base_url)

    # A start is pending until its first send (M25 F4 L3b).
    _chats.start_chat(page, app_with_agent.agent_name)
    sid = _chats.send_first(page, "hello")
    row = _chats.chat_row(page, sid)
    expect(row).to_be_visible(timeout=5000)
    expect(_chats.pending_row(page)).to_have_count(0)

    shape = page.evaluate(
        """(sid) => {
          const pane = document.querySelector('[data-testid="chats-list"]');
          const row = pane.querySelector('[data-testid="chat-row"][data-id="' + sid + '"]');
          const li = row.parentElement;
          const act = li.querySelector('[data-testid="chat-row-delete"]');
          const title = pane.querySelector('h2');
          return {pane: pane.tagName, labelledBy: pane.getAttribute('aria-labelledby') === title.id,
                  title: title.textContent, li: li.tagName, ul: li.parentElement.tagName,
                  row: row.tagName, href: row.getAttribute('href'),
                  action: act.tagName, actionType: act.type, actionParent: act.parentElement === li,
                  actionName: act.getAttribute('aria-label'),
                  rowLabel: row.querySelector('.ui-list-pane-label').textContent};
        }""",
        sid,
    )
    assert shape == {
        "pane": "SECTION",
        "labelledBy": True,
        "title": "Chats",
        "li": "LI",
        "ul": "UL",
        "row": "A",
        "href": _nav.href(f"chats/{_nav.seg(sid)}"),
        "action": "BUTTON",
        "actionType": "button",
        "actionParent": True,
        "actionName": "Delete chat: " + shape["rowLabel"],
        "rowLabel": shape["rowLabel"],
    }, shape

    # Tab from the row reaches its action, then leaves the list.
    delete_btn = _chats.chat_row_delete(page, sid)
    expect(delete_btn).to_be_hidden()  # display:none until the <li> has focus
    row.focus()
    page.keyboard.press("Tab")
    expect(delete_btn).to_be_focused()
    expect(delete_btn).to_be_visible()
    page.keyboard.press("Tab")
    assert page.evaluate(
        "() => !document.querySelector('[data-testid=\"chats-list\"]')"
        ".contains(document.activeElement)"
    )


@pytest.mark.browser
def test_chat_row_delete_keyboard_reveal(app_with_agent: SeededApp, page: Page) -> None:
    """Tab from a chat row to its sibling delete action; :focus-within reveals it.

    A display:none element cannot be focused directly. The reveal is driven by
    Tab from the focused row link into its sibling delete action under the
    same ``<li>``. Once the action has focus, the ``<li>``'s :focus-within
    fires and display:none becomes inline-flex. M25 F4 L4a re-pinned
    ``test_session_delete_keyboard_reveal`` (the retired ``.list-item`` /
    ``.list-item-delete`` pair) on the Chats list's row action, and adds Enter
    on the action: it arms the confirm in place.
    """
    base_url = app_with_agent.base_url
    page.goto(base_url)

    # A start is pending until its first send (M25 F4 L3b).
    _chats.start_chat(page, app_with_agent.agent_name)
    sid = _chats.send_first(page, "hello")
    session_item = _chats.chat_row(page, sid)
    expect(session_item).to_be_visible(timeout=5000)

    delete_btn = _chats.chat_row_delete(page, sid)

    # Before focus: delete is hidden (display:none)
    expect(delete_btn).to_be_hidden()

    # Focus the row link, then Tab once to reach the sibling delete.
    session_item.focus()
    page.keyboard.press("Tab")

    # :focus-within on the wrapping <li> fires when the action receives focus.
    expect(delete_btn).to_be_visible()
    expect(delete_btn).to_be_focused()
    # Enter arms the two-step confirm on the row's <li> (nothing deleted yet).
    page.keyboard.press("Enter")
    li = page.locator("li").filter(has=session_item)
    expect(li).to_have_class(re.compile(r"\bconfirm-delete\b"))
    expect(session_item.locator(".ui-list-pane-label")).to_have_text("Confirm delete?")


@pytest.mark.browser
def test_agent_item_keyboard_select(app_with_agent: SeededApp, page: Page) -> None:
    """Tab from the filter into the agents list, press Enter; the row's agent
    opens and the row carries aria-current="page".

    M25 F3 L3 replaced the tile grid (`<button>` tiles) with an App.ui.listPane
    column: each row is a native `<a href>` (Enter navigates natively, App.nav
    routes the click), with one roving tab stop -- the selected row, else the
    first visible row. The filter sits before the list in Tab order.
    """
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name
    # goto_settled: Studio's first activation loads the inventory twice
    # (init() and activate()->_refresh()); both passes re-render the rows, so
    # wait for the fetch activity to go quiet before focusing one.
    _nav.goto_settled(page, base_url, "agents")

    agent_item = _lists.list_row(page, "agents", agent_name)
    expect(agent_item).to_be_visible(timeout=5000)
    tag_name = agent_item.evaluate("el => el.tagName.toLowerCase()")
    assert tag_name == "a", f"agent-item must be an <a> link, got <{tag_name}>"

    # The filter is the tab stop before the list; Tab lands on the row.
    page.locator('[data-testid="agents-filter"]').focus()
    page.keyboard.press("Tab")
    expect(agent_item).to_be_focused()
    page.keyboard.press("Enter")

    _nav.expect_route(page, f"agents/{_nav.seg(agent_name)}/general")
    expect(page.locator(".editor-title")).to_have_text(agent_name, timeout=8000)
    _lists.expect_selected(page, "agents", agent_name)


# The Settings nav (M25 F3 leg 5a, DD10) is App.ui.navGroups: plain links in Tab
# order with no roving tabindex and no arrow keys (the board's <a> items). The
# former section nav's roving-tabindex test is rewritten for the new control:
# keyboard coverage stays, the behaviour under test changes with it.
_SETTINGS_NAV_ORDER = (
    "appearance",
    "date-and-time",
    "prompts",
    "encryption",
    "providers",
    "tools",
    "knowledge-indexing",
    "design-language",  # the browser lanes run in dev mode
)


@pytest.mark.browser
def test_settings_nav_links_are_in_tab_order(app_clean: str, page: Page) -> None:
    """Tab reaches each Settings nav link in group order, with a visible focus ring."""
    _nav.goto(page, app_clean, "settings/appearance")
    nav = _lists.settings_nav(page)
    expect(nav).to_be_visible(timeout=5000)
    # A <nav> landmark named "Settings" (no explicit role attribute needed).
    assert nav.evaluate("el => el.tagName") == "NAV"
    expect(nav).to_have_attribute("aria-label", "Settings")

    links = nav.locator("a")
    expect(links).to_have_count(len(_SETTINGS_NAV_ORDER))
    for k, section in enumerate(_SETTINGS_NAV_ORDER):
        link = links.nth(k)
        expect(link).to_have_attribute("data-testid", f"settings-nav-{section}")
        # Plain links: no roving tabindex, every one is a Tab stop.
        assert link.get_attribute("tabindex") is None, section

    # Focus the first link, then Tab walks the rest in order.
    _lists.settings_nav_link(page, "appearance").focus()
    for section in _SETTINGS_NAV_ORDER[1:]:
        page.keyboard.press("Tab")
        link = _lists.settings_nav_link(page, section)
        expect(link).to_be_focused()
        # Keyboard focus is visible (the factory's :focus-visible ring).
        assert link.evaluate("el => el.matches(':focus-visible')"), section
        assert link.evaluate("el => getComputedStyle(el).outlineStyle") == "solid", section


@pytest.mark.browser
def test_settings_nav_enter_navigates_and_moves_aria_current(app_clean: str, page: Page) -> None:
    """Enter on a focused link navigates; aria-current follows the page."""
    _nav.goto(page, app_clean, "settings/appearance")
    _lists.expect_settings_selected(page, "appearance")

    providers = _lists.settings_nav_link(page, "providers")
    providers.focus()
    page.keyboard.press("Enter")
    _nav.expect_route(page, "settings/providers")
    expect(_lists.settings_page_title(page)).to_have_text("Providers", timeout=5000)
    _lists.expect_settings_selected(page, "providers")

    appearance = _lists.settings_nav_link(page, "appearance")
    appearance.focus()
    page.keyboard.press("Enter")
    _nav.expect_route(page, "settings/appearance")
    expect(_lists.settings_page_title(page)).to_have_text("Appearance", timeout=5000)
    _lists.expect_settings_selected(page, "appearance")
