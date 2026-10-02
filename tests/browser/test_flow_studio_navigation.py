"""End-to-end flow tests: Library navigation (F5 leg 01; M25 F2 L3; M25 F3 L4a).

Since M25 F3 L4a the Library aside holds one grouped list (Knowledge bases /
MCP servers / Connectors, testid ``library-list``) with an Add menu; the
"Library sections" nav is retired. Agents is its own destination: its aside
holds the agents list column instead (M25 F2 L3 (c); M25 F3 L3).

- The list renders its title, intro, Add and the three groups in order
- Exactly one list pane per destination; the section nav never renders
- A bare ``library`` lands on Knowledge with its empty detail state
- Roving tabindex over the rows (one tab stop: the selected row, else the first)
- Row clicks open each type's item beside the list (aria-current)
- Keyboard: Up/Down/Home/End move focus across the groups (flat, clamped),
  Enter opens the focused row; the Add menu opens and closes by keyboard
- Refreshing on each section URL returns to that section
- Each destination keeps its selection (rail-restore, DD4): leaving an open
  agent for Library and returning restores the agent; clicking the CURRENT
  destination goes to its root.
"""

from __future__ import annotations

import pytest
from browser import _lists, _nav
from browser.seeders import SeededApp, seed_connector, seed_knowledge_base, seed_mcp_source
from playwright.sync_api import Page, expect


def _wait_library_ready(page: Page) -> None:
    """Wait for the Library destination to mount (active panel + the list's groups)."""
    expect(_nav.destination_panel(page, "library")).to_be_visible(timeout=8000)
    expect(page.locator('[data-testid="library-list"] .ui-list-pane-caption').first).to_be_visible(
        timeout=8000
    )


def _wait_agents_ready(page: Page) -> None:
    """Wait for the Agents destination to mount (the readiness probe)."""
    expect(_nav.destination_panel(page, "agents")).to_be_visible(timeout=8000)


def _seed(base: str) -> None:
    """Two knowledge bases, one MCP server, one connector (A-Z order differs from creation)."""
    seed_knowledge_base(base, "Zeta notes")
    seed_knowledge_base(base, "Alpha notes")
    seed_mcp_source(base, "mcp-one")
    seed_connector(base, "Conn one")


def _rows(page: Page):
    return page.locator('[data-testid="library-list"] li:not([hidden]) > .ui-list-pane-row')


def _focused_label(page: Page) -> str | None:
    return page.evaluate(
        "() => { const r = document.activeElement && document.activeElement.closest"
        "('.ui-list-pane-row');"
        " return r ? r.querySelector('.ui-list-pane-label').textContent : null; }"
    )


@pytest.mark.browser
def test_library_list_renders_title_intro_add_and_groups(app_clean: str, page: Page) -> None:
    """The Library list: title, intro, Add, then the three groups in order (DD5)."""
    _nav.goto(page, app_clean, "library")
    _wait_library_ready(page)

    library = page.locator('[data-testid="library-list"]')
    expect(library.locator(".ui-list-pane-title")).to_have_text("Library")
    expect(library.locator(".ui-list-pane-intro")).to_have_text(
        "Things agents can use. Attach them from an agent\u2019s Knowledge and MCPs tabs."
    )
    expect(library.locator('[data-testid="library-add-btn"]')).to_have_text("Add")
    expect(library.locator(".ui-list-pane-caption")).to_have_text(
        ["Knowledge bases", "MCP servers", "Connectors"]
    )
    # The aside is labelled by the destination; no section nav exists.
    expect(page.locator("#app-sidebar")).to_have_attribute("aria-label", "Library")
    expect(page.locator(".area-studio .section-nav")).to_have_count(0)


@pytest.mark.browser
def test_agents_aside_shows_the_agents_list_not_the_library_list(
    app_clean: str, page: Page
) -> None:
    """Agents is its own destination: its aside holds the agents list, and the
    Library list exists only on Library (exactly one pane at a time)."""
    _nav.goto(page, app_clean, "agents")
    _wait_agents_ready(page)

    aside = page.locator("#app-sidebar")
    expect(aside).to_be_visible()
    expect(aside).to_have_attribute("aria-label", "Agents")
    expect(aside.locator('[data-testid="agents-list"]')).to_be_visible()
    expect(page.locator('[data-testid="library-list"]')).to_have_count(0)
    _nav.expect_route(page, "agents")

    # ...and on Library the Library list is there and the agents list is gone.
    _nav.open_destination(page, "library")
    _wait_library_ready(page)
    expect(aside).to_be_visible()
    expect(aside).to_have_attribute("aria-label", "Library")
    expect(page.locator('[data-testid="agents-list"]')).to_have_count(0)
    expect(page.locator(".ui-list-pane")).to_have_count(1)


@pytest.mark.browser
def test_library_default_section_is_knowledge(app_clean: str, page: Page) -> None:
    """Landing on bare `library` defaults to Knowledge: the route and the
    Knowledge empty detail state.

    The bare destination redirects to `library/knowledge` (replaceState).
    """
    _nav.goto(page, app_clean, "library")
    _wait_library_ready(page)

    expect(_lists.library_empty_state(page, "knowledge")).to_be_visible()
    assert page.evaluate("location.hash") == _nav.href("library/knowledge")
    expect(page.locator('[data-testid="library-list"] [aria-current="page"]')).to_have_count(0)


@pytest.mark.browser
def test_library_list_roving_tabindex(app_clean: str, page: Page) -> None:
    """One tab stop: the first row with nothing selected, the selected row after a pick."""
    _seed(app_clean)
    _nav.goto(page, app_clean, "library")
    _wait_library_ready(page)
    rows = _rows(page)
    expect(rows).to_have_count(4)
    stops = page.locator('[data-testid="library-list"] .ui-list-pane-row[tabindex="0"]')
    expect(stops).to_have_count(1)
    expect(stops.first).to_contain_text("Alpha notes")

    _lists.open_item(page, "library/mcp", "mcp-one")
    expect(stops).to_have_count(1)
    expect(stops.first).to_contain_text("mcp-one")
    expect(rows.nth(0)).to_have_attribute("tabindex", "-1")


@pytest.mark.browser
def test_library_click_knowledge_row(app_clean: str, page: Page) -> None:
    """Clicking a knowledge-base row opens its detail beside the list."""
    _seed(app_clean)
    _nav.goto(page, app_clean, "library/mcp")
    _wait_library_ready(page)

    _lists.open_item(page, "library/knowledge", "Alpha notes")

    inventory = page.locator('[data-testid="studio-knowledge-inventory"]')
    expect(inventory).to_be_visible(timeout=5000)
    expect(page.locator(".editor-title")).to_have_text("Alpha notes")
    _lists.expect_selected(page, "library/knowledge", "Alpha notes")
    expect(page.locator('[data-testid="library-list"]')).to_be_visible()


@pytest.mark.browser
def test_library_click_mcp_and_connector_rows(app_clean: str, page: Page) -> None:
    """MCP and connector rows open their editors beside the list (connectors are routed)."""
    _seed(app_clean)
    _nav.goto(page, app_clean, "library")
    _wait_library_ready(page)

    _lists.open_item(page, "library/mcp", "mcp-one")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=5000)
    _lists.expect_selected(page, "library/mcp", "mcp-one")

    _lists.open_item(page, "library/connectors", "Conn one")
    expect(page.locator(".editor-title")).to_have_text("Conn one", timeout=5000)
    _lists.expect_selected(page, "library/connectors", "Conn one")
    assert page.evaluate("location.hash").startswith(_nav.href("library/connectors") + "/")


@pytest.mark.browser
def test_library_keyboard_arrow_navigation(app_clean: str, page: Page) -> None:
    """Up/Down move focus across the groups (one flat list, clamped at the
    ends); Home/End jump. Focus only: the route does not change."""
    _seed(app_clean)
    _nav.goto(page, app_clean, "library")
    _wait_library_ready(page)
    expect(_rows(page)).to_have_count(4)

    _rows(page).first.focus()
    assert _focused_label(page) == "Alpha notes"
    page.keyboard.press("ArrowDown")
    assert _focused_label(page) == "Zeta notes"
    page.keyboard.press("ArrowDown")  # crosses into the MCP servers group
    assert _focused_label(page) == "mcp-one"
    page.keyboard.press("ArrowDown")
    assert _focused_label(page) == "Conn one"
    page.keyboard.press("ArrowDown")  # clamped at the end
    assert _focused_label(page) == "Conn one"
    page.keyboard.press("Home")
    assert _focused_label(page) == "Alpha notes"
    page.keyboard.press("ArrowUp")  # clamped at the start
    assert _focused_label(page) == "Alpha notes"
    page.keyboard.press("End")
    assert _focused_label(page) == "Conn one"

    _nav.expect_route(page, "library/knowledge")


@pytest.mark.browser
def test_library_keyboard_enter_opens_the_focused_row(app_clean: str, page: Page) -> None:
    """Enter on a focused row opens its item (the row is a link)."""
    _seed(app_clean)
    _nav.goto(page, app_clean, "library")
    _wait_library_ready(page)
    expect(_rows(page)).to_have_count(4)

    _rows(page).first.focus()
    page.keyboard.press("ArrowDown")
    page.keyboard.press("ArrowDown")  # -> mcp-one
    page.keyboard.press("Enter")

    page.wait_for_function(
        "p => location.hash.startsWith(p)", arg=_nav.href("library/mcp") + "/", timeout=5000
    )
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=5000)
    _lists.expect_selected(page, "library/mcp", "mcp-one")


@pytest.mark.browser
def test_library_add_menu_keyboard(app_clean: str, page: Page) -> None:
    """The Add menu opens by Enter, Space and ArrowDown on the trigger; Escape
    closes it and returns focus to the trigger; Enter on an item opens its form."""
    _nav.goto(page, app_clean, "library")
    _wait_library_ready(page)
    trigger = page.locator('[data-testid="library-add-btn"]')
    menu = page.locator('[data-testid="library-add-knowledge"]').locator("xpath=..")

    for key in ("Enter", "Space", "ArrowDown"):
        trigger.focus()
        page.keyboard.press(key)
        expect(menu).to_be_visible()
        expect(trigger).to_have_attribute("aria-expanded", "true")
        expect(page.locator('[data-testid="library-add-knowledge"]')).to_be_focused()
        page.keyboard.press("Escape")
        expect(menu).to_be_hidden()
        expect(trigger).to_be_focused()

    trigger.focus()
    page.keyboard.press("ArrowDown")
    page.keyboard.press("ArrowDown")  # -> MCP server
    expect(page.locator('[data-testid="library-add-mcp"]')).to_be_focused()
    page.keyboard.press("Enter")
    _nav.expect_route(page, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=5000)


@pytest.mark.browser
def test_studio_knowledge_section_persists_on_refresh(app_clean: str, page: Page) -> None:
    """Navigating to library/knowledge directly + refreshing returns to that section."""
    _nav.goto(page, app_clean, "library/knowledge")
    _wait_library_ready(page)

    expect(_lists.library_empty_state(page, "knowledge")).to_be_visible(timeout=5000)
    _nav.expect_route(page, "library/knowledge")

    page.reload()
    _wait_library_ready(page)

    expect(_lists.library_empty_state(page, "knowledge")).to_be_visible(timeout=5000)
    _nav.expect_route(page, "library/knowledge")


@pytest.mark.browser
def test_studio_mcp_sources_section_persists_on_refresh(app_clean: str, page: Page) -> None:
    """Navigating to library/mcp + refreshing returns to that section."""
    _nav.goto(page, app_clean, "library/mcp")
    _wait_library_ready(page)

    expect(_lists.library_empty_state(page, "mcp")).to_be_visible(timeout=5000)
    _nav.expect_route(page, "library/mcp")

    page.reload()
    _wait_library_ready(page)

    expect(_lists.library_empty_state(page, "mcp")).to_be_visible(timeout=5000)
    _nav.expect_route(page, "library/mcp")


@pytest.mark.browser
def test_agents_destination_restores_open_agent_after_library_trip(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Agents -> Library -> Agents restores the open agent (DD4: each destination
    keeps its selection).

    This inverts the M10 F6 L7 contract ("return to the listing") for
    OTHER-destination clicks; the authority is reference board B3 section 10
    item 2. The Library trip tears the open agent down (outgoing-section
    cleanup), and the restore re-opens it fresh through the pending path.
    """
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name

    _nav.goto_settled(page, base_url, "agents")
    _wait_agents_ready(page)

    _lists.open_item(page, "agents", agent_name)
    expect(page.locator(".editor-title")).to_have_text(agent_name, timeout=5000)
    agent_route = f"agents/{_nav.seg(agent_name)}/general"
    _nav.expect_route(page, agent_route)

    _nav.open_destination(page, "library")
    _wait_library_ready(page)
    expect(_lists.library_empty_state(page, "knowledge")).to_be_visible(timeout=3000)

    _nav.open_destination(page, "agents")
    expect(page.locator(".editor-title")).to_have_text(agent_name, timeout=5000)
    _nav.expect_route(page, agent_route)
    expect(page.locator(".studio-editor")).not_to_have_class("studio-editor is-hidden")
    _lists.expect_selected(page, "agents", agent_name)


@pytest.mark.browser
def test_current_destination_click_returns_to_agent_listing(
    app_with_agent: SeededApp, page: Page
) -> None:
    """A click on the CURRENT destination's button goes to its root: the editor
    closes and the empty detail state owns the main panel beside the list
    (kept from M10 F6 L7)."""
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name

    _nav.goto_settled(page, base_url, "agents")
    _wait_agents_ready(page)
    _lists.open_item(page, "agents", agent_name)
    expect(page.locator(".editor-title")).to_have_text(agent_name, timeout=5000)

    _nav.open_destination(page, "agents")
    expect(page.locator(".studio-editor")).to_have_class("studio-editor is-hidden", timeout=5000)
    expect(page.locator(".studio-section-content")).not_to_have_class(
        "studio-section-content is-hidden"
    )
    _nav.expect_route(page, "agents")
    expect(_lists.agents_empty_state(page)).to_be_visible()
    expect(page.locator('[data-testid="agent-item"][aria-current="page"]')).to_have_count(0)


@pytest.mark.browser
def test_studio_editor_hidden_on_knowledge_section(app_with_agent: SeededApp, page: Page) -> None:
    """When Knowledge or MCP Servers is active, the studio-editor is hidden."""
    base_url = app_with_agent.base_url

    _nav.goto(page, base_url, "library/knowledge")
    _wait_library_ready(page)

    editor = page.locator(".studio-editor")
    expect(editor).to_have_class("studio-editor is-hidden", timeout=5000)
