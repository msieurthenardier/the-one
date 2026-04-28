"""End-to-end flow tests: studio section navigation (F5 leg 01).

Covers the three-section sidebar (Agents / Knowledge / Tools) introduced in
F5 leg 01:

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
TOOLS_TEXT = "MCP servers and built-in tools will be configured here in a future mission."


def _wait_studio_ready(page: Page) -> None:
    """Wait for the studio area to mount (section-nav + Studio header visible)."""
    expect(page.locator(".section-nav-header")).to_have_text("Studio", timeout=8000)


@pytest.mark.browser
def test_studio_section_nav_renders_three_buttons(app_clean: str, page: Page) -> None:
    """The section-nav has three buttons (Agents / Knowledge / Tools)."""
    page.goto(f"{app_clean}#studio")
    _wait_studio_ready(page)

    buttons = page.locator(".section-nav-item")
    expect(buttons).to_have_count(3)
    expect(buttons.nth(0)).to_have_text("Agents")
    expect(buttons.nth(1)).to_have_text("Knowledge")
    expect(buttons.nth(2)).to_have_text("Tools")


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
    tools_btn = page.locator('.section-nav-item[data-section="tools"]')

    expect(agents_btn).to_have_attribute("tabindex", "0")
    expect(knowledge_btn).to_have_attribute("tabindex", "-1")
    expect(tools_btn).to_have_attribute("tabindex", "-1")


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
def test_studio_click_tools_section(app_clean: str, page: Page) -> None:
    """Clicking the Tools section button updates URL and shows the stub."""
    page.goto(f"{app_clean}#studio")
    _wait_studio_ready(page)

    page.locator('.section-nav-item[data-section="tools"]').click()

    assert page.evaluate("location.hash") == "#studio/tools"

    stub = page.locator('[data-testid="studio-tools-stub"]')
    expect(stub).to_be_visible(timeout=2000)
    expect(stub).to_have_text(TOOLS_TEXT)

    active = page.locator('.section-nav-item[aria-current="page"]')
    expect(active).to_have_count(1)
    expect(active).to_have_text("Tools")


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

    # ArrowDown → Tools.
    page.keyboard.press("ArrowDown")
    focused_section = page.evaluate("() => document.activeElement?.dataset?.section")
    assert focused_section == "tools"

    # ArrowDown wraps → Agents.
    page.keyboard.press("ArrowDown")
    focused_section = page.evaluate("() => document.activeElement?.dataset?.section")
    assert focused_section == "agents"

    # ArrowUp wraps backward → Tools.
    page.keyboard.press("ArrowUp")
    focused_section = page.evaluate("() => document.activeElement?.dataset?.section")
    assert focused_section == "tools"

    # End → Tools (already there); Home → Agents.
    page.keyboard.press("Home")
    focused_section = page.evaluate("() => document.activeElement?.dataset?.section")
    assert focused_section == "agents"

    page.keyboard.press("End")
    focused_section = page.evaluate("() => document.activeElement?.dataset?.section")
    assert focused_section == "tools"

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
def test_studio_tools_section_persists_on_refresh(app_clean: str, page: Page) -> None:
    """Navigating to #studio/tools + refreshing returns to that section."""
    page.goto(f"{app_clean}#studio/tools")
    _wait_studio_ready(page)

    expect(page.locator('[data-testid="studio-tools-stub"]')).to_be_visible(timeout=5000)
    assert page.evaluate("location.hash") == "#studio/tools"

    page.reload()
    _wait_studio_ready(page)

    expect(page.locator('[data-testid="studio-tools-stub"]')).to_be_visible(timeout=5000)
    assert page.evaluate("location.hash") == "#studio/tools"

    active = page.locator('.section-nav-item[aria-current="page"]')
    expect(active).to_have_text("Tools")


@pytest.mark.browser
def test_studio_section_round_trip_preserves_agent_selection(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Switching Agents → Knowledge → Agents preserves the selected agent.

    The editor pane stays mounted (just hidden) so a return to Agents doesn't
    lose state. This is the load-bearing contract for the leg 04 dirty-state
    confirm dialog (you don't lose unsaved edits on a Knowledge round-trip).
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

    # Switch back to Agents — agent still selected, editor visible.
    page.locator('.section-nav-item[data-section="agents"]').click()
    expect(page.locator(".editor-title")).to_have_text(agent_name, timeout=5000)
    active_item = page.locator(f'.agent-item[data-name="{agent_name}"][aria-selected="true"]')
    expect(active_item).to_be_visible(timeout=2000)


@pytest.mark.browser
def test_studio_editor_hidden_on_knowledge_section(app_with_agent: SeededApp, page: Page) -> None:
    """When Knowledge/Tools is active, the studio-editor is hidden."""
    base_url = app_with_agent.base_url

    page.goto(f"{base_url}#studio/knowledge")
    _wait_studio_ready(page)

    editor = page.locator(".studio-editor")
    expect(editor).to_have_class("studio-editor is-hidden", timeout=5000)
