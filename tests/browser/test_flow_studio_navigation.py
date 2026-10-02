"""End-to-end flow tests: Library section navigation (F5 leg 01; M25 F2 L3).

Covers the Library section nav (Knowledge / MCP Servers / Connectors). Agents
is its own destination with NO section nav, and its aside is hidden (M25 F2
L3 (c)); the section nav is labelled "Library sections".

- Section nav buttons render with correct ARIA + roving tabindex
- Click navigation updates the route + active section
- Keyboard navigation: Up/Down/Home/End move focus between buttons,
  Enter/Space activate the focused button
- Refreshing on each section URL returns to that section
- aria-current="page" tracks the active section button
- Each destination keeps its selection (rail-restore, DD4): leaving an open
  agent for Library and returning restores the agent; clicking the CURRENT
  destination goes to its root.
"""

from __future__ import annotations

import pytest
from browser import _nav
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect


def _wait_library_ready(page: Page) -> None:
    """Wait for the Library destination to mount (active panel + section nav)."""
    expect(_nav.destination_panel(page, "library")).to_be_visible(timeout=8000)
    expect(page.locator(".area-studio .section-nav-item").first).to_be_visible(timeout=8000)


def _wait_agents_ready(page: Page) -> None:
    """Wait for the Agents destination to mount (the readiness probe)."""
    expect(_nav.destination_panel(page, "agents")).to_be_visible(timeout=8000)


@pytest.mark.browser
def test_library_section_nav_renders_three_buttons(app_clean: str, page: Page) -> None:
    """The Library section nav has three buttons (Knowledge / MCP Servers / Connectors)."""
    _nav.goto(page, app_clean, "library")
    _wait_library_ready(page)

    expect(page.locator('.section-nav[aria-label="Library sections"]')).to_be_visible()
    buttons = page.locator(".section-nav-item")
    expect(buttons).to_have_count(3)
    expect(buttons.nth(0)).to_have_text("Knowledge")
    expect(buttons.nth(1)).to_have_text("MCP Servers")
    expect(buttons.nth(2)).to_have_text("Connectors")
    # The aside is labelled by the destination, the nav inside by its sections.
    expect(page.locator("#app-sidebar")).to_have_attribute("aria-label", "Library")


@pytest.mark.browser
def test_agents_has_no_section_nav_and_hidden_aside(app_clean: str, page: Page) -> None:
    """Agents is its own destination: no section nav, and the aside is hidden."""
    _nav.goto(page, app_clean, "agents")
    _wait_agents_ready(page)

    expect(page.locator("#app-sidebar")).to_be_hidden()
    expect(page.locator("#app-sidebar")).to_have_attribute("hidden", "")
    # No active section button anywhere on Agents.
    expect(page.locator('.section-nav-item[aria-current="page"]')).to_have_count(0)
    _nav.expect_route(page, "agents")

    # ...and the aside comes back, labelled, on Library.
    _nav.open_destination(page, "library")
    _wait_library_ready(page)
    expect(page.locator("#app-sidebar")).to_be_visible()


@pytest.mark.browser
def test_library_default_section_is_knowledge(app_clean: str, page: Page) -> None:
    """Landing on bare `library` defaults to Knowledge with aria-current='page'.

    The bare destination redirects to `library/knowledge` (replaceState).
    """
    _nav.goto(page, app_clean, "library")
    _wait_library_ready(page)

    active = page.locator('.section-nav-item[aria-current="page"]')
    expect(active).to_have_count(1)
    expect(active).to_have_text("Knowledge")
    assert page.evaluate("location.hash") == _nav.href("library/knowledge")


@pytest.mark.browser
def test_library_section_nav_roving_tabindex(app_clean: str, page: Page) -> None:
    """Only the active section button has tabindex='0'; others have tabindex='-1'."""
    _nav.goto(page, app_clean, "library")
    _wait_library_ready(page)

    knowledge_btn = page.locator('.section-nav-item[data-section="knowledge"]')
    mcp_btn = page.locator('.section-nav-item[data-section="mcp-sources"]')
    connectors_btn = page.locator('.section-nav-item[data-section="connectors"]')

    expect(knowledge_btn).to_have_attribute("tabindex", "0")
    expect(mcp_btn).to_have_attribute("tabindex", "-1")
    expect(connectors_btn).to_have_attribute("tabindex", "-1")


@pytest.mark.browser
def test_studio_click_knowledge_section(app_clean: str, page: Page) -> None:
    """Clicking the Knowledge section button updates URL and shows the inventory."""
    _nav.goto(page, app_clean, "library/mcp")
    _wait_library_ready(page)

    page.locator('.section-nav-item[data-section="knowledge"]').click()

    # URL updated.
    _nav.expect_route(page, "library/knowledge")

    # Inventory rendered.
    inventory = page.locator('[data-testid="studio-knowledge-inventory"]')
    expect(inventory).to_be_visible(timeout=2000)

    # aria-current moved to Knowledge.
    active = page.locator('.section-nav-item[aria-current="page"]')
    expect(active).to_have_count(1)
    expect(active).to_have_text("Knowledge")


@pytest.mark.browser
def test_studio_click_mcp_sources_section(app_clean: str, page: Page) -> None:
    """Clicking the MCP Servers section button updates URL and shows the grid.

    Post-F2 retrofit: replaces the test that previously clicked the
    "Tools" stub. The grid renders a page-header with title "MCP Servers"
    and either an empty-state CTA or a tile grid depending on inventory.
    """
    _nav.goto(page, app_clean, "library")
    _wait_library_ready(page)

    page.locator('.section-nav-item[data-section="mcp-sources"]').click()

    _nav.expect_route(page, "library/mcp")

    expect(page.locator(".area-studio .page-title")).to_have_text("MCP Servers", timeout=5000)

    active = page.locator('.section-nav-item[aria-current="page"]')
    expect(active).to_have_count(1)
    expect(active).to_have_text("MCP Servers")


@pytest.mark.browser
def test_studio_keyboard_arrow_navigation(app_clean: str, page: Page) -> None:
    """Up/Down arrows move focus between section buttons (focus only, no activation).

    Manual-activation contract: arrow keys move focus + visual highlight, but do
    NOT mutate URL or activate the section. Enter/Space commits.
    """
    _nav.goto(page, app_clean, "library")
    _wait_library_ready(page)

    def focused() -> str | None:
        return page.evaluate("() => document.activeElement?.dataset?.section")

    # Focus the active (Knowledge) button explicitly.
    page.locator('.section-nav-item[data-section="knowledge"]').focus()

    page.keyboard.press("ArrowDown")  # -> MCP Servers
    assert focused() == "mcp-sources"

    page.keyboard.press("ArrowDown")  # -> Connectors (the last entry)
    assert focused() == "connectors"

    page.keyboard.press("ArrowDown")  # wraps -> Knowledge
    assert focused() == "knowledge"

    page.keyboard.press("ArrowUp")  # wraps backward -> Connectors
    assert focused() == "connectors"

    page.keyboard.press("Home")
    assert focused() == "knowledge"

    page.keyboard.press("End")
    assert focused() == "connectors"

    # Focus moved but the route did NOT change (manual activation).
    _nav.expect_route(page, "library/knowledge")


@pytest.mark.browser
def test_studio_keyboard_enter_activates(app_clean: str, page: Page) -> None:
    """Pressing Enter on a focused section button activates it (URL + section change)."""
    _nav.goto(page, app_clean, "library")
    _wait_library_ready(page)

    page.locator('.section-nav-item[data-section="knowledge"]').focus()
    page.keyboard.press("ArrowDown")  # focus -> MCP Servers
    page.keyboard.press("Enter")

    _nav.expect_route(page, "library/mcp")
    expect(page.locator(".area-studio .page-title")).to_have_text("MCP Servers", timeout=5000)

    # Roving tabindex updated.
    mcp_btn = page.locator('.section-nav-item[data-section="mcp-sources"]')
    knowledge_btn = page.locator('.section-nav-item[data-section="knowledge"]')
    expect(mcp_btn).to_have_attribute("tabindex", "0")
    expect(knowledge_btn).to_have_attribute("tabindex", "-1")


@pytest.mark.browser
def test_studio_knowledge_section_persists_on_refresh(app_clean: str, page: Page) -> None:
    """Navigating to #studio/knowledge directly + refreshing returns to that section."""
    _nav.goto(page, app_clean, "library/knowledge")
    _wait_library_ready(page)

    expect(page.locator('[data-testid="studio-knowledge-inventory"]')).to_be_visible(timeout=5000)
    _nav.expect_route(page, "library/knowledge")

    page.reload()
    _wait_library_ready(page)

    expect(page.locator('[data-testid="studio-knowledge-inventory"]')).to_be_visible(timeout=5000)
    _nav.expect_route(page, "library/knowledge")

    active = page.locator('.section-nav-item[aria-current="page"]')
    expect(active).to_have_text("Knowledge")


@pytest.mark.browser
def test_studio_mcp_sources_section_persists_on_refresh(app_clean: str, page: Page) -> None:
    """Navigating to #studio/mcp-sources + refreshing returns to that section.

    Post-F2 retrofit: replaces the test that previously asserted the
    "Tools" stub persists on refresh. The MCP Servers section is the new
    third nav entry.
    """
    _nav.goto(page, app_clean, "library/mcp")
    _wait_library_ready(page)

    expect(page.locator(".area-studio .page-title")).to_have_text("MCP Servers", timeout=5000)
    _nav.expect_route(page, "library/mcp")

    page.reload()
    _wait_library_ready(page)

    expect(page.locator(".area-studio .page-title")).to_have_text("MCP Servers", timeout=5000)
    _nav.expect_route(page, "library/mcp")

    active = page.locator('.section-nav-item[aria-current="page"]')
    expect(active).to_have_text("MCP Servers")


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

    page.locator('[data-testid="agent-item"]').click()
    expect(page.locator(".editor-title")).to_have_text(agent_name, timeout=5000)
    agent_route = f"agents/{_nav.seg(agent_name)}/general"
    _nav.expect_route(page, agent_route)

    _nav.open_destination(page, "library")
    _wait_library_ready(page)
    expect(page.locator('[data-testid="studio-knowledge-inventory"]')).to_be_visible(timeout=3000)

    _nav.open_destination(page, "agents")
    expect(page.locator(".editor-title")).to_have_text(agent_name, timeout=5000)
    _nav.expect_route(page, agent_route)
    expect(page.locator(".studio-editor")).not_to_have_class("studio-editor is-hidden")


@pytest.mark.browser
def test_current_destination_click_returns_to_agent_listing(
    app_with_agent: SeededApp, page: Page
) -> None:
    """A click on the CURRENT destination's button goes to its root: the editor
    closes and the tile grid owns the main panel (kept from M10 F6 L7)."""
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name

    _nav.goto_settled(page, base_url, "agents")
    _wait_agents_ready(page)
    page.locator('[data-testid="agent-item"]').click()
    expect(page.locator(".editor-title")).to_have_text(agent_name, timeout=5000)

    _nav.open_destination(page, "agents")
    expect(page.locator(".studio-editor")).to_have_class("studio-editor is-hidden", timeout=5000)
    expect(page.locator(".studio-section-content")).not_to_have_class(
        "studio-section-content is-hidden"
    )
    _nav.expect_route(page, "agents")


@pytest.mark.browser
def test_studio_editor_hidden_on_knowledge_section(app_with_agent: SeededApp, page: Page) -> None:
    """When Knowledge or MCP Servers is active, the studio-editor is hidden."""
    base_url = app_with_agent.base_url

    _nav.goto(page, base_url, "library/knowledge")
    _wait_library_ready(page)

    editor = page.locator(".studio-editor")
    expect(editor).to_have_class("studio-editor is-hidden", timeout=5000)
