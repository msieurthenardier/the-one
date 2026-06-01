"""End-to-end flow tests: studio section navigation (F5 leg 01).

Covers the four-section sidebar (Agents / Knowledge / MCP Servers /
Connector Accounts). Post-F2 retrofit: the third section was originally
a "Tools" stub and became the relocated "MCP Servers" surface (moved
from the admin nav because MCP sources are user-managed entities, not
system settings). M10 F2 leg 05 added the fourth section, "Connector
Accounts" — the same operator-managed-entity shape as MCP Sources.

- Section nav buttons render with correct ARIA + roving tabindex
- Click navigation updates URL hash + active section
- Keyboard navigation: Up/Down/Home/End move focus between buttons,
  Enter/Space activate the focused button
- Refreshing on each section URL returns to that section
- aria-current="page" tracks the active section button
"""

from __future__ import annotations

import pytest
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect

KNOWLEDGE_TEXT = "Knowledge bases will be created and managed here in a future mission."


def _wait_studio_ready(page: Page) -> None:
    """Wait for the studio area to mount.

    Sidebar headers were removed (commit 0d3d42e: "drop redundant sidebar
    headers"); the topbar's app-picker pill names the active area instead.
    Wait for the section-nav buttons to render — that's the canonical
    "studio mounted" signal once the headers are gone.
    """
    expect(page.locator(".area-studio .section-nav-item").first).to_be_visible(timeout=8000)


@pytest.mark.browser
def test_studio_section_nav_renders_four_buttons(app_clean: str, page: Page) -> None:
    """The section-nav has four buttons (Agents / Knowledge / MCP Servers / Connectors).

    F5 L8 HAT: fourth label renamed from "Connector Accounts" → "Connectors".
    The internal section id `connectors` is unchanged (data-section
    attribute still matches the F2 contract).
    """
    page.goto(f"{app_clean}#studio")
    _wait_studio_ready(page)

    buttons = page.locator(".section-nav-item")
    expect(buttons).to_have_count(4)
    expect(buttons.nth(0)).to_have_text("Agents")
    expect(buttons.nth(1)).to_have_text("Knowledge")
    expect(buttons.nth(2)).to_have_text("MCP Servers")
    expect(buttons.nth(3)).to_have_text("Connectors")


@pytest.mark.browser
def test_studio_default_section_is_agents(app_clean: str, page: Page) -> None:
    """Landing on #studio defaults to the Agents section with aria-current='page'.

    The redirect from #studio to #studio/agents is performed by the F3 router's
    serialize-after-hydrate path (no new redirect logic in studio.js).
    """
    page.goto(f"{app_clean}#studio")
    _wait_studio_ready(page)

    # Active section is Agents — the only button with aria-current="page".
    active = page.locator('.section-nav-item[aria-current="page"]')
    expect(active).to_have_count(1)
    expect(active).to_have_text("Agents")

    # URL was rewritten to #studio/agents.
    assert page.evaluate("location.hash") == "#studio/agents"


@pytest.mark.browser
def test_studio_section_nav_roving_tabindex(app_clean: str, page: Page) -> None:
    """Only the active section button has tabindex='0'; others have tabindex='-1'."""
    page.goto(f"{app_clean}#studio")
    _wait_studio_ready(page)

    agents_btn = page.locator('.section-nav-item[data-section="agents"]')
    knowledge_btn = page.locator('.section-nav-item[data-section="knowledge"]')
    mcp_btn = page.locator('.section-nav-item[data-section="mcp-sources"]')
    connector_btn = page.locator('.section-nav-item[data-section="connectors"]')

    expect(agents_btn).to_have_attribute("tabindex", "0")
    expect(knowledge_btn).to_have_attribute("tabindex", "-1")
    expect(mcp_btn).to_have_attribute("tabindex", "-1")
    expect(connector_btn).to_have_attribute("tabindex", "-1")


@pytest.mark.browser
def test_studio_click_knowledge_section(app_clean: str, page: Page) -> None:
    """Clicking the Knowledge section button updates URL and shows the stub."""
    page.goto(f"{app_clean}#studio")
    _wait_studio_ready(page)

    page.locator('.section-nav-item[data-section="knowledge"]').click()

    # URL updated.
    assert page.evaluate("location.hash") == "#studio/knowledge"

    # Stub text visible.
    stub = page.locator('[data-testid="studio-knowledge-stub"]')
    expect(stub).to_be_visible(timeout=2000)
    expect(stub).to_have_text(KNOWLEDGE_TEXT)

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
    page.goto(f"{app_clean}#studio")
    _wait_studio_ready(page)

    page.locator('.section-nav-item[data-section="mcp-sources"]').click()

    assert page.evaluate("location.hash") == "#studio/mcp-sources"

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
    page.goto(f"{app_clean}#studio")
    _wait_studio_ready(page)

    # Focus the active (Agents) button explicitly.
    page.locator('.section-nav-item[data-section="agents"]').focus()

    # ArrowDown → focus moves to Knowledge.
    page.keyboard.press("ArrowDown")
    focused_section = page.evaluate("() => document.activeElement?.dataset?.section")
    assert focused_section == "knowledge"

    # ArrowDown → MCP Servers.
    page.keyboard.press("ArrowDown")
    focused_section = page.evaluate("() => document.activeElement?.dataset?.section")
    assert focused_section == "mcp-sources"

    # ArrowDown → Connector Accounts (the new last entry, M10 F2 leg 05).
    page.keyboard.press("ArrowDown")
    focused_section = page.evaluate("() => document.activeElement?.dataset?.section")
    assert focused_section == "connectors"

    # ArrowDown wraps → Agents.
    page.keyboard.press("ArrowDown")
    focused_section = page.evaluate("() => document.activeElement?.dataset?.section")
    assert focused_section == "agents"

    # ArrowUp wraps backward → Connector Accounts (new last entry).
    page.keyboard.press("ArrowUp")
    focused_section = page.evaluate("() => document.activeElement?.dataset?.section")
    assert focused_section == "connectors"

    # Home → Agents.
    page.keyboard.press("Home")
    focused_section = page.evaluate("() => document.activeElement?.dataset?.section")
    assert focused_section == "agents"

    # End → Connector Accounts (the new last entry).
    page.keyboard.press("End")
    focused_section = page.evaluate("() => document.activeElement?.dataset?.section")
    assert focused_section == "connectors"

    # Focus moved but URL did NOT change (manual activation).
    assert page.evaluate("location.hash") == "#studio/agents"


@pytest.mark.browser
def test_studio_keyboard_enter_activates(app_clean: str, page: Page) -> None:
    """Pressing Enter on a focused section button activates it (URL + section change)."""
    page.goto(f"{app_clean}#studio")
    _wait_studio_ready(page)

    page.locator('.section-nav-item[data-section="agents"]').focus()
    page.keyboard.press("ArrowDown")  # focus → Knowledge
    page.keyboard.press("Enter")

    assert page.evaluate("location.hash") == "#studio/knowledge"
    expect(page.locator('[data-testid="studio-knowledge-stub"]')).to_be_visible(timeout=2000)

    # Roving tabindex updated.
    knowledge_btn = page.locator('.section-nav-item[data-section="knowledge"]')
    agents_btn = page.locator('.section-nav-item[data-section="agents"]')
    expect(knowledge_btn).to_have_attribute("tabindex", "0")
    expect(agents_btn).to_have_attribute("tabindex", "-1")


@pytest.mark.browser
def test_studio_knowledge_section_persists_on_refresh(app_clean: str, page: Page) -> None:
    """Navigating to #studio/knowledge directly + refreshing returns to that section."""
    page.goto(f"{app_clean}#studio/knowledge")
    _wait_studio_ready(page)

    expect(page.locator('[data-testid="studio-knowledge-stub"]')).to_be_visible(timeout=5000)
    assert page.evaluate("location.hash") == "#studio/knowledge"

    page.reload()
    _wait_studio_ready(page)

    expect(page.locator('[data-testid="studio-knowledge-stub"]')).to_be_visible(timeout=5000)
    assert page.evaluate("location.hash") == "#studio/knowledge"

    active = page.locator('.section-nav-item[aria-current="page"]')
    expect(active).to_have_text("Knowledge")


@pytest.mark.browser
def test_studio_mcp_sources_section_persists_on_refresh(app_clean: str, page: Page) -> None:
    """Navigating to #studio/mcp-sources + refreshing returns to that section.

    Post-F2 retrofit: replaces the test that previously asserted the
    "Tools" stub persists on refresh. The MCP Servers section is the new
    third nav entry.
    """
    page.goto(f"{app_clean}#studio/mcp-sources")
    _wait_studio_ready(page)

    expect(page.locator(".area-studio .page-title")).to_have_text("MCP Servers", timeout=5000)
    assert page.evaluate("location.hash") == "#studio/mcp-sources"

    page.reload()
    _wait_studio_ready(page)

    expect(page.locator(".area-studio .page-title")).to_have_text("MCP Servers", timeout=5000)
    assert page.evaluate("location.hash") == "#studio/mcp-sources"

    active = page.locator('.section-nav-item[aria-current="page"]')
    expect(active).to_have_text("MCP Servers")


@pytest.mark.browser
def test_studio_section_round_trip_returns_to_agent_listing(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Switching Agents → Knowledge → Agents lands on the agent listing.

    M10 F6 L7 HAT (commit 93c4120) inverted the navigation contract: leaving
    the Agents section clears the selected agent, so a return to Agents shows
    the tile grid with the editor hidden — not the previously-edited agent.
    """
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name

    page.goto(f"{base_url}#studio")
    _wait_studio_ready(page)

    # Select the seeded agent.
    page.locator('[data-testid="agent-item"]').click()
    expect(page.locator(".editor-title")).to_have_text(agent_name, timeout=5000)

    # Switch to Knowledge.
    page.locator('.section-nav-item[data-section="knowledge"]').click()
    expect(page.locator('[data-testid="studio-knowledge-stub"]')).to_be_visible(timeout=2000)

    # Switch back to Agents — selection was cleared on leaving, so the editor
    # is hidden and the tile grid (section-content) owns the main panel.
    page.locator('.section-nav-item[data-section="agents"]').click()
    expect(page.locator(".studio-editor")).to_have_class("studio-editor is-hidden")
    expect(page.locator(".studio-section-content")).not_to_have_class(
        "studio-section-content is-hidden"
    )


@pytest.mark.browser
def test_studio_editor_hidden_on_knowledge_section(app_with_agent: SeededApp, page: Page) -> None:
    """When Knowledge or MCP Servers is active, the studio-editor is hidden."""
    base_url = app_with_agent.base_url

    page.goto(f"{base_url}#studio/knowledge")
    _wait_studio_ready(page)

    editor = page.locator(".studio-editor")
    expect(editor).to_have_class("studio-editor is-hidden", timeout=5000)
