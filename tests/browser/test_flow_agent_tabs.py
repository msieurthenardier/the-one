"""End-to-end flow tests: agent editor tab idiom (F5 leg 03).

Covers the W3C ARIA tablist with manual activation introduced in F5 leg 03:

- Tablist renders three tabs (General / Knowledge / Tools) with correct ARIA
- Default tab on agent select is General; URL upgrades to .../general
- Arrow Left/Right move focus + visual highlight only — URL unchanged
- Enter (or Space) commits the focused tab — URL updates, aria-selected
  toggles, roving tabindex updates, panel visibility swaps
- Home/End jump to first/last tab (focus only)
- Click on a tab commits (same as Enter)
- Refresh on .../{tab} returns the user to that tab
- Tools tab renders the built-in tool checkboxes (interactive)
- Knowledge tab renders the real attach surface (M24 F06 L03)
- Advanced collapsible: visible, disabled inputs, "Coming soon" caption
- Test button: disabled when no provider; click triggers fetch and renders
  the result in the .test-result span
"""

from __future__ import annotations

import urllib.parse

import pytest
from browser import _lists, _nav
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect


def _wait_editor_ready(page: Page, expected_tab: str = "general") -> None:
    """Wait for the agent editor to be the visible child in the main panel.

    Bare `#agents` shows the agents list beside an empty detail pane, with no
    agent auto-selected (F5 leg 05 design; M25 F3 L3 list column): the editor
    is hidden. Click the first list row to open it. Deep-link
    navigations (`#agents/<name>/...`) hydrate the selection and the
    editor mounts asynchronously via L5's `refreshToolConfigsCache().then(renderEditor)`
    wrapper inside `doSelect` (studio.js); skip the click in that case and
    wait for the async mount to complete.

    expected_tab: which tab is expected to be active after the editor mounts.
    Defaults to 'general' for tests that select an agent without specifying
    a tab. Deep-link tests (/knowledge, /tools) override this so the helper
    waits for the deep-linked tab's `aria-selected="true"` before returning,
    avoiding the race with the L5 async editor-mount wrapper.
    """
    expect(_nav.destination_panel(page, "agents")).to_be_visible(timeout=8000)
    # If the URL hash deep-links into an agent (`#agents/<name>...`), the
    # editor mount is already in flight via the async wrapper — wait for it
    # to complete instead of clicking a row (a click would re-open it on
    # the General tab, racing the deep-linked tab).
    deep_linked = _nav.current_route(page).startswith("agents/")
    if not deep_linked:
        editor_hidden = page.evaluate(
            "() => document.querySelector('.studio-editor')?.classList.contains('is-hidden')"
        )
        if editor_hidden:
            _lists.first_row(page, "agents").click()
    expect(page.locator(f'[data-testid="tab-{expected_tab}"]')).to_be_visible(timeout=8000)
    # Wait for the expected tab to be active (handles the L5 async editor-mount race).
    expect(page.locator(f'[data-testid="tab-{expected_tab}"]')).to_have_attribute(
        "aria-selected", "true", timeout=8000
    )


@pytest.mark.browser
def test_tablist_renders_with_five_tabs(app_with_agent: SeededApp, page: Page) -> None:
    """The agent editor renders a tablist with tabs and correct ARIA.

    The Self-configuration tab (M21 F01 L02) sits last, so the tablist
    renders 5 tabs in order: General / Knowledge / MCPs / Built-in Tools /
    Self-configuration. (A Connectors tab sat between MCPs and Built-in
    Tools from M10 through Mission 23 Flight 1, which reset the connector
    subsystem and removed it.)
    """
    base_url = app_with_agent.base_url
    _nav.goto(page, base_url, "agents")
    _wait_editor_ready(page)

    tablist = page.locator('[role="tablist"]')
    expect(tablist).to_be_visible()

    tabs = page.locator('[role="tab"]')
    # General + Knowledge + MCPs + Built-in Tools + Self-configuration
    expect(tabs).to_have_count(5)

    expect(page.locator('[data-testid="tab-general"]')).to_have_attribute("aria-selected", "true")
    expect(page.locator('[data-testid="tab-knowledge"]')).to_have_attribute(
        "aria-selected", "false"
    )
    expect(page.locator('[data-testid="tab-mcps"]')).to_have_attribute("aria-selected", "false")
    expect(page.locator('[data-testid="tab-tools"]')).to_have_attribute("aria-selected", "false")
    expect(page.locator('[data-testid="tab-self-configuration"]')).to_have_attribute(
        "aria-selected", "false"
    )


@pytest.mark.browser
def test_default_tab_is_general_on_select(app_with_agent: SeededApp, page: Page) -> None:
    """Selecting an agent activates General; URL upgrades to .../general."""
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name
    _nav.goto(page, base_url, "agents")
    _wait_editor_ready(page)

    expected = f"agents/{_nav.seg(agent_name)}/general"
    _nav.expect_route(page, expected)
    # General tab content is mounted (form fields visible).
    expect(page.locator('[data-field="description"]')).to_be_visible()


@pytest.mark.browser
def test_arrow_keys_move_focus_only(app_with_agent: SeededApp, page: Page) -> None:
    """Arrow Left/Right move focus + visual highlight only; URL stays."""
    base_url = app_with_agent.base_url
    _nav.goto(page, base_url, "agents")
    _wait_editor_ready(page)

    initial_route = _nav.current_route(page)
    # Focus the General tab.
    page.locator('[data-testid="tab-general"]').focus()

    # Arrow Right → focus moves to Knowledge but URL/aria-selected stay.
    page.keyboard.press("ArrowRight")
    focused_id = page.evaluate("document.activeElement?.id")
    assert focused_id == "agent-tab-knowledge"

    # URL unchanged.
    _nav.expect_route(page, initial_route)
    # aria-selected unchanged (still General).
    expect(page.locator('[data-testid="tab-general"]')).to_have_attribute("aria-selected", "true")
    expect(page.locator('[data-testid="tab-knowledge"]')).to_have_attribute(
        "aria-selected", "false"
    )


@pytest.mark.browser
def test_enter_commits_focused_tab(app_with_agent: SeededApp, page: Page) -> None:
    """Enter on a focused tab commits — URL updates, aria-selected toggles."""
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name
    _nav.goto(page, base_url, "agents")
    _wait_editor_ready(page)

    # Move focus to Knowledge then Enter.
    page.locator('[data-testid="tab-general"]').focus()
    page.keyboard.press("ArrowRight")
    page.keyboard.press("Enter")

    expected = f"agents/{_nav.seg(agent_name)}/knowledge"
    _nav.expect_route(page, expected)
    expect(page.locator('[data-testid="tab-knowledge"]')).to_have_attribute("aria-selected", "true")
    expect(page.locator('[data-testid="tab-general"]')).to_have_attribute("aria-selected", "false")

    # Roving tabindex: now Knowledge is the only tabindex="0".
    expect(page.locator('[data-testid="tab-knowledge"]')).to_have_attribute("tabindex", "0")
    expect(page.locator('[data-testid="tab-general"]')).to_have_attribute("tabindex", "-1")

    # Knowledge panel visible; General hidden.
    knowledge_panel = page.locator('[data-testid="agent-knowledge-tab"]')
    expect(knowledge_panel).to_be_visible()


@pytest.mark.browser
def test_home_end_jump_to_first_last(app_with_agent: SeededApp, page: Page) -> None:
    """Home/End jump focus to first/last tab (without committing)."""
    base_url = app_with_agent.base_url
    _nav.goto(page, base_url, "agents")
    _wait_editor_ready(page)

    page.locator('[data-testid="tab-general"]').focus()

    page.keyboard.press("End")
    # M21 F01 L02: Self-configuration is now the LAST tab (after Built-in
    # Tools), so End lands there.
    assert page.evaluate("document.activeElement?.id") == "agent-tab-self-configuration"

    page.keyboard.press("Home")
    assert page.evaluate("document.activeElement?.id") == "agent-tab-general"


@pytest.mark.browser
def test_click_commits_tab(app_with_agent: SeededApp, page: Page) -> None:
    """Clicking a tab commits — URL updates and panel becomes visible."""
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name
    _nav.goto(page, base_url, "agents")
    _wait_editor_ready(page)

    page.locator('[data-testid="tab-tools"]').click()

    expected = f"agents/{_nav.seg(agent_name)}/tools"
    _nav.expect_route(page, expected)
    # Leg 02 restructured Built-in Tools tab into category tiles with iOS-pill
    # master toggles. The hidden checkbox (.tool-toggle, display:none) backs
    # the pill visual (.tool-switch). Assert the visible pill instead.
    expect(page.locator(".tool-switch").first).to_be_visible()


@pytest.mark.browser
def test_refresh_on_knowledge_tab_persists(app_with_agent: SeededApp, page: Page) -> None:
    """Refresh on /knowledge URL returns the user to the Knowledge tab."""
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name
    # legacy URL on purpose (AC6)
    target = f"{base_url}#studio/agents/{urllib.parse.quote(agent_name)}/knowledge"
    page.goto(target)
    _wait_editor_ready(page, expected_tab="knowledge")
    _nav.expect_route(page, f"agents/{_nav.seg(agent_name)}/knowledge")

    expect(page.locator('[data-testid="agent-knowledge-tab"]')).to_be_visible(timeout=8000)
    expect(page.locator('[data-testid="tab-knowledge"]')).to_have_attribute("aria-selected", "true")


@pytest.mark.browser
def test_refresh_on_tools_tab_persists(app_with_agent: SeededApp, page: Page) -> None:
    """Refresh on /tools URL returns the user to the Built-in Tools tab."""
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name
    _nav.goto(page, base_url, f"agents/{_nav.seg(agent_name)}/tools")
    _wait_editor_ready(page, expected_tab="tools")

    # Leg 02 restructured Built-in Tools tab into category tiles with iOS-pill
    # master toggles. The hidden checkbox (.tool-toggle, display:none) backs
    # the pill visual (.tool-switch). Assert the visible pill instead.
    expect(page.locator(".tool-switch").first).to_be_visible(timeout=8000)
    expect(page.locator('[data-testid="tab-tools"]')).to_have_attribute("aria-selected", "true")


@pytest.mark.browser
def test_tools_tab_renders_builtin_checkboxes(app_with_agent: SeededApp, page: Page) -> None:
    """Tools tab contains built-in tool checkboxes; interactive."""
    base_url = app_with_agent.base_url
    _nav.goto(page, base_url, "agents")
    _wait_editor_ready(page)

    page.locator('[data-testid="tab-tools"]').click()

    # The "Built-in tools" section shows checkboxes via .tool-toggle.
    toggles = page.locator(".tool-toggle")
    assert toggles.count() > 0


@pytest.mark.browser
def test_knowledge_tab_renders_attach_surface(app_with_agent: SeededApp, page: Page) -> None:
    """Knowledge tab renders the real attach surface (M24 F06 L03).

    L3-D6: the retired stub's content assertion
    (`to_contain_text("Knowledge bases will be attached")`) does not carry
    forward — the attach tab's content is data-driven (Leg 3's dedicated
    `test_flow_studio_knowledge_attach.py` covers rows/toggles/tool
    names); this test keeps only the visibility/mount assertion its two
    siblings above already establish as the pattern.
    """
    base_url = app_with_agent.base_url
    _nav.goto(page, base_url, "agents")
    _wait_editor_ready(page)

    page.locator('[data-testid="tab-knowledge"]').click()

    panel = page.locator('[data-testid="agent-knowledge-tab"]')
    expect(panel).to_be_visible()


@pytest.mark.browser
def test_test_button_renders_result(app_with_agent: SeededApp, page: Page) -> None:
    """Test button click triggers fetch; result renders in .test-result span.

    The seeded mock provider's /test endpoint returns ok with a deterministic
    detail message — exercises the success path. The button is also enabled
    (the agent has a provider_config_id) since it's seeded.
    """
    base_url = app_with_agent.base_url
    _nav.goto(page, base_url, "agents")
    _wait_editor_ready(page)

    test_btn = page.locator('[data-testid="test-provider-btn"]')
    expect(test_btn).to_be_visible()
    expect(test_btn).to_be_enabled()

    test_btn.click()

    result = page.locator('[data-testid="test-provider-result"]')
    # Wait for the test to resolve — either ok or fail; both render text.
    expect(result).not_to_have_text("Testing…", timeout=8000)
    # Should carry the .test-result-ok or .test-result-fail modifier.
    cls = result.get_attribute("class") or ""
    assert "test-result-ok" in cls or "test-result-fail" in cls


@pytest.mark.browser
def test_retention_days_input_renders_above_max_iterations(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Retention-days input renders in the Behavior section above Max Iterations.

    Asserts:
    - [data-field="chat_history_retention_days"] is visible with the correct
      id, type, min, and max attributes.
    - The retention input precedes [data-field="max_iterations"] in DOM order
      (compareDocumentPosition idiom — see test_flow_studio_mcp_editor.py).
    """
    base_url = app_with_agent.base_url
    _nav.goto(page, base_url, "agents")
    _wait_editor_ready(page)

    retention_input = page.locator('[data-field="chat_history_retention_days"]')
    expect(retention_input).to_be_visible()
    assert retention_input.get_attribute("id") == "studio-retention-days"
    assert retention_input.get_attribute("type") == "number"
    assert retention_input.get_attribute("min") == "1"
    assert retention_input.get_attribute("max") == "365"

    # DOM-order check: retention input must precede max_iterations input.
    # Node.compareDocumentPosition returns a bitmask; bit 2 (value 4,
    # DOCUMENT_POSITION_FOLLOWING) is set when the argument follows the caller.
    retention_before_maxiter = page.evaluate(
        "() => {"
        "  var r = document.querySelector('[data-field=\"chat_history_retention_days\"]');"
        "  var m = document.querySelector('[data-field=\"max_iterations\"]');"
        "  if (!r || !m) return false;"
        "  return !!(r.compareDocumentPosition(m) & Node.DOCUMENT_POSITION_FOLLOWING);"
        "}"
    )
    assert retention_before_maxiter, (
        "chat_history_retention_days input must precede max_iterations in DOM order"
    )
