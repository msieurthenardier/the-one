"""List helpers for browser tests (M25 F3 leg 1, DD11).

Flight 3 turns every destination's surface into a list beside a detail pane:
the agent grid, the Library grids and section nav, and the Settings grids and
Back buttons are retired leg by leg. Tests reach list rows through this module
instead of naming those surfaces' selectors, so each leg changes one table here
rather than every test that opens an item:

* ``list_row(page, dest, name)`` -- the row locator for the item named *name*;
* ``open_item(page, dest, name)`` -- click that row and wait until the item is
  open (its route, or the editor title where the item has no route yet).

*dest* names a list as a new-scheme route (see ``_nav``): ``"chats"``, ``"agents"``,
``"library/providers"``, ``"library/knowledge"``, ``"library/mcp"``,
``"library/connectors"`` or ``"settings/tools"``.  ``library/providers`` is scoped
under ``library-list`` (providers have one host since sortie 02).  Rows are found through the
testids every surface keeps (``agent-item``, ``knowledge-base-card``,
``mcp-source-card``, ``connector-card``, ``provider-card``, ``tool-card``) and
matched by a non-badge element whose text is exactly *name*, so "Agent" never
matches "Agent 2".  Later legs add the helpers their surfaces need.

Agents (leg 3) is a list column (``App.ui.listPane``, testid ``agents-list``)
beside the detail pane, so a row stays visible while its agent is open:

* ``first_row(page, dest)`` -- the list's first row;
* ``expect_selected(page, "agents", name)`` -- the row carries
  ``aria-current="page"`` (and is the only one that does);
* ``filter_agents(page, q)`` -- type *q* into the list's filter;
* ``agents_new(page)`` -- click "New" and wait for the create form at
  ``#agents/~new``;
* ``agents_empty_state(page)`` -- the detail pane's start page (no agent
  open): ``agent-select-empty`` with agents, ``agent-empty`` without.

Library (leg 4a) is one grouped list column (testid ``library-list``: Knowledge
bases, MCP servers, Connectors) with an Add menu, beside the detail pane; every
Library row has an item route (connectors included):

* ``expect_selected(page, "library/knowledge", name)`` (or ``library/mcp``,
  ``library/connectors``) -- as for agents;
* ``library_add(page, kind)`` -- open the Add menu, choose *kind*
  (``"providers"``, ``"knowledge"``, ``"mcp"`` or ``"connectors"``) and wait for its create
  route ``#library/<kind>/~new``;
* ``library_start(page)`` -- the detail pane's start page at the Library root
  (``library-start``; it holds all four types' blocks).

Leg 4b retired the Library editors' Back controls (leg 3 retired the agent
editor's): every Agents and Library item header carries a breadcrumb whose last
segment links to its root ("Agents" -> ``#agents``, "Knowledge bases" ->
``#library/knowledge``, "MCP servers" -> ``#library/mcp``, "Connectors" ->
``#library/connectors``), and that link is how a test closes an item:

* ``breadcrumb_link(page)`` -- the open item header's root link
  (``editor-breadcrumb-link``, visible ones only);
* ``close_item(page)`` -- click it. It returns at once: a dirty editor asks
  first (the router's leave guard), so the caller asserts what follows.

Settings (leg 5a) is a grouped nav of plain links (``App.ui.navGroups``, testid
``settings-nav``) beside the page; its items are ``settings-nav-{section}``, one
per page (``SETTINGS_PAGES``: the four General pages, Built-in tools and
Knowledge indexing):

* ``settings_nav(page)`` -- the ``<nav aria-label="Settings">``;
* ``settings_nav_link(page, section)`` -- one page's link;
* ``open_settings_page(page, section)`` -- click that link and wait for the page
  (its route and its page header's title, ``SETTINGS_PAGE_TITLES``). A dirty
  editor asks first, so a test that expects the leave dialog clicks
  ``settings_nav_link`` itself;
* ``expect_settings_selected(page, section)`` -- that link is the nav's one
  ``aria-current="page"`` item;
* ``settings_page_title(page)`` -- the open Settings page's ``h1``.

Settings item pages (leg 5b; Built-in tools only since sortie 02) keep their
list visible: opening a built-in tool renders its editor in an item section
BELOW the list (``.settings-item``), and the editor header's breadcrumb
("Settings / Built-in tools") closes it (``close_item``). A tool tile keeps
``tool-card`` but only its tool NAME is a link (the tile is no click target,
its toggle never navigates):

* ``list_row(page, "settings/tools", name)`` -- the tool's tile;
* ``item_link(page, dest, name)`` -- the row's item link (the row itself for
  every list but the tools, whose link is the tile's name);
* ``open_item`` clicks that link; ``expect_selected`` checks ``aria-current``
  on it;
* ``settings_item(page)`` -- the page's item section (the open editor);
* ``open_tool(page, name)`` -- select the tool's category tab, then open it;
* ``tool_toggle(page, name)`` -- the tool tile's enable switch.

Chats (Flight 4 leg 4a) is a list column too (``App.ui.listPane``, testid
``chats-list``): ``list_row(page, "chats", title)`` is the session row whose
title is exactly *title* (``chat-row`` with a ``data-id``; never the pending
chat's row), and ``open_item(page, "chats", title)`` clicks it and waits for its
``#chats/{id}`` route.  Sessions are found by id through
``tests/browser/_chats.py`` (``chat_row``, ``open_chat``), which also waits
for the join; use this list when a test names a chat by its title.

The retired selectors are fenced by the AST guard in ``tests/test_nav_helper.py``
(``RETIRED_SELECTORS``, ``test_no_retired_selectors_in_browser_tests``): no
browser test and no helper module (this one included) may name them.  The
per-file allow-list that carried the Flight 3 migration was removed in leg 6,
so no file is exempt.
"""

from __future__ import annotations

from typing import NamedTuple

from browser import _nav
from playwright.sync_api import Locator, Page, expect


class _List(NamedTuple):
    row: str  # CSS selector of one row (a kept testid)
    item_route: bool  # True: opening an item moves the route to "<dest>/<id>"
    # The row's item link, as a selector inside the row; None: the row IS the
    # link (it carries aria-current="page" when its item is open).
    link: str | None = None


LISTS: dict[str, _List] = {
    "chats": _List('[data-testid="chat-row"][data-id]', True),
    "agents": _List('[data-testid="agent-item"]', True),
    "library/providers": _List('[data-testid="library-list"] [data-testid="provider-card"]', True),
    "library/knowledge": _List('[data-testid="knowledge-base-card"]', True),
    "library/mcp": _List('[data-testid="mcp-source-card"]', True),
    "library/connectors": _List('[data-testid="connector-card"]', True),
    "settings/tools": _List('[data-testid="tool-card"]', True, link="a"),
}


def _list(dest: str) -> _List:
    if dest not in LISTS:
        raise ValueError(f"unknown list {dest!r} (want one of {sorted(LISTS)})")
    return LISTS[dest]


def list_row(page: Page, dest: str, name: str) -> Locator:
    """The row of list *dest* whose name is exactly *name*.

    A badge is never the name: a provider row's type badge can read "mock" while
    another row is NAMED "mock".
    """
    spec = _list(dest)
    name_el = page.get_by_text(name, exact=True).and_(page.locator(":not([class*=badge])"))
    rows = page.locator(spec.row)
    return rows.filter(has=name_el)


def item_link(page: Page, dest: str, name: str) -> Locator:
    """The item link of the row named *name* (the row itself, except for a
    tool tile, whose link is its name)."""
    spec = _list(dest)
    row = list_row(page, dest, name)
    return row.locator(spec.link) if spec.link else row


def first_row(page: Page, dest: str) -> Locator:
    """The first row of list *dest* (for tests that open "an" item, not a named one)."""
    return page.locator(_list(dest).row).first


def _selected_selector(dest: str) -> str:
    spec = _list(dest)
    link = f" {spec.link}" if spec.link else ""
    return f'{spec.row}{link}[aria-current="page"]'


def expect_selected(page: Page, dest: str, name: str, timeout: float = 8000) -> None:
    """The row named *name* is the list's one selected row (``aria-current``
    on its item link)."""
    expect(item_link(page, dest, name)).to_have_attribute("aria-current", "page", timeout=timeout)
    expect(page.locator(_selected_selector(dest))).to_have_count(1)


def expect_none_selected(page: Page, dest: str, timeout: float = 8000) -> None:
    """No row of list *dest* is selected."""
    expect(page.locator(_selected_selector(dest))).to_have_count(0, timeout=timeout)


def filter_agents(page: Page, q: str) -> None:
    """Type *q* into the Agents list filter (replacing what is there)."""
    page.locator('[data-testid="agents-filter"]').fill(q)


def agents_new(page: Page, timeout: float = 8000) -> None:
    """Click the Agents list's "New" and wait for the create form at ``#agents/~new``."""
    page.locator('[data-testid="new-agent-btn"]').click()
    _nav.expect_route(page, "agents/~new", timeout=timeout)
    expect(page.locator(".editor-title")).to_have_text("New Agent", timeout=timeout)


def agents_empty_state(page: Page) -> Locator:
    """The Agents start page node (either variant; the ``h1`` is a sibling)."""
    return page.locator('[data-testid="agent-select-empty"], [data-testid="agent-empty"]')


LIBRARY_KINDS = ("providers", "knowledge", "mcp", "connectors")

# The Add menu item per kind (an unknown kind raises in ``_kind``, never falls
# back to the connector).
LIBRARY_ADD_ITEMS = {
    "providers": "library-add-provider",
    "knowledge": "library-add-knowledge",
    "mcp": "library-add-mcp",
    "connectors": "library-add-connector",
}


def _kind(kind: str) -> str:
    if kind not in LIBRARY_KINDS:
        raise ValueError(f"unknown Library kind {kind!r} (want one of {LIBRARY_KINDS})")
    return kind


def library_add(page: Page, kind: str, timeout: float = 8000) -> None:
    """Open the Library list's Add menu, choose *kind*, and wait for its create route."""
    item_testid = LIBRARY_ADD_ITEMS[_kind(kind)]
    page.locator('[data-testid="library-add-btn"]').click()
    page.locator(f'[data-testid="{item_testid}"]').click()
    _nav.expect_route(page, f"library/{kind}/~new", timeout=timeout)


def library_start(page: Page) -> Locator:
    """The Library start page (``#library``, the one root: a card per group, providers first)."""
    return page.locator('[data-testid="library-start"]')


def breadcrumb_link(page: Page) -> Locator:
    """The open item header's breadcrumb root link (visible only: one item
    header shows at a time)."""
    return page.locator('[data-testid="editor-breadcrumb-link"]:visible')


def close_item(page: Page, timeout: float = 8000) -> None:
    """Click the open item header's breadcrumb root link (it closes the item to
    its root's empty state; a dirty editor asks first, so nothing is awaited)."""
    link = breadcrumb_link(page)
    expect(link).to_be_visible(timeout=timeout)
    link.click()


# ── Settings nav (leg 5a) ───────────────────────────────────────────────

# The Settings pages in nav order, by route section, with their page titles.
SETTINGS_PAGE_TITLES: dict[str, str] = {
    "appearance": "Appearance",
    "date-and-time": "Date and time",
    "prompts": "Prompts",
    "encryption": "Encryption",
    "tools": "Built-in tools",
    "knowledge-indexing": "Knowledge indexing",
}
SETTINGS_PAGES = tuple(SETTINGS_PAGE_TITLES)


def _section(section: str) -> str:
    if section not in SETTINGS_PAGE_TITLES:
        raise ValueError(f"unknown Settings page {section!r} (want one of {SETTINGS_PAGES})")
    return section


def settings_nav(page: Page) -> Locator:
    """The Settings nav (``<nav aria-label="Settings">``)."""
    return page.locator('[data-testid="settings-nav"]')


def settings_nav_link(page: Page, section: str) -> Locator:
    """The Settings nav link of page *section* (a route section, e.g. ``"tools"``)."""
    return page.locator(f'[data-testid="settings-nav-{_section(section)}"]')


def settings_page_title(page: Page) -> Locator:
    """The open Settings page's ``h1`` (its page header's title)."""
    return page.locator(".area-admin .page-header .page-title")


def open_settings_page(page: Page, section: str, timeout: float = 8000) -> None:
    """Click the nav link of page *section* and wait for that page's route and title."""
    settings_nav_link(page, section).click()
    _nav.expect_route(page, f"settings/{section}", timeout=timeout)
    expect(settings_page_title(page)).to_have_text(SETTINGS_PAGE_TITLES[section], timeout=timeout)


def expect_settings_selected(page: Page, section: str, timeout: float = 8000) -> None:
    """Page *section*'s link is the Settings nav's one selected (``aria-current``) item."""
    expect(settings_nav_link(page, section)).to_have_attribute(
        "aria-current", "page", timeout=timeout
    )
    expect(settings_nav(page).locator('[aria-current="page"]')).to_have_count(1)


def open_item(page: Page, dest: str, name: str, timeout: float = 8000) -> None:
    """Click the row named *name* and wait until its item is open.

    With an item route, waits for the hash to move under ``<dest>/`` to a
    route other than the pre-click one (so it never matches a previously open
    item). Opening the item that is already open is not a navigation; assert
    that state directly instead.
    """
    spec = _list(dest)
    row = item_link(page, dest, name)
    before = page.evaluate("location.hash")
    row.click()
    if not spec.item_route:
        expect(page.locator(".editor-title")).to_have_text(name, timeout=timeout)
        return
    prefix = _nav.hash_for(dest) + "/"
    page.wait_for_function(
        "([p, before]) => location.hash.startsWith(p) && location.hash !== before",
        arg=[prefix, before],
        timeout=timeout,
    )


# ── Settings item pages (leg 5b) ────────────────────────────────────────

# The Built-in tools category tab of each tool (mirrors App.toolCategories'
# categoryOf, static/js/tool-categories.js since M25 F4 L6; the tests only open
# these).
TOOL_TABS: dict[str, str] = {
    "read_file": "filesystem",
    "write_file": "filesystem",
    "list_dir": "filesystem",
    "shell": "execution",
    "python_exec": "execution",
    "http_request": "web",
    "fetch_url": "web",
    "download_file": "web",
    "web_search": "web",
    "send_to_platform_channel": "connectors",
    "fetch_channel_history": "connectors",
    "current_time": "time",
}


def settings_item(page: Page) -> Locator:
    """The Settings page's item section, below its list (the open editor)."""
    return page.locator(".area-admin .settings-item")


def tool_toggle(page: Page, name: str) -> Locator:
    """The tool tile's enable switch (``tool-toggle``)."""
    return page.locator(f'input[data-testid="tool-toggle"][data-name="{name}"]')


def open_tool(page: Page, name: str, timeout: float = 8000) -> None:
    """Select *name*'s category tab, click its name link and wait for its route
    (the editor then mounts below the list)."""
    tab = TOOL_TABS.get(name)
    if tab is None:
        raise ValueError(f"unknown tool {name!r} (want one of {sorted(TOOL_TABS)})")
    page.locator(f'[data-testid="tab-{tab}"]').click()
    item_link(page, "settings/tools", name).click()
    _nav.expect_route(page, f"settings/tools/{_nav.seg(name)}", timeout=timeout)


def wait_active_testid(page: Page, testids: tuple[str, ...], timeout: float = 10000) -> str:
    """Wait until ``document.activeElement`` carries one of *testids*; return it.

    Asserts element identity, not window focus, and waits for it: a focus
    restore can land after the visible state it follows (async re-read), and a
    loaded headless run can leave the page without window focus, so a single
    read or ``to_be_focused`` is flaky (squawk 0187).  Bounded by *timeout* (ms).
    """
    page.wait_for_function(
        """(ids) => {
          const a = document.activeElement;
          return !!a && ids.includes(a.getAttribute('data-testid'));
        }""",
        arg=list(testids),
        timeout=timeout,
    )
    return page.evaluate("document.activeElement.getAttribute('data-testid')")
