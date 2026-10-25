"""Admin Tools grid + tab + tile tests for F6 leg 07.

Covers the L2 admin Tools grid surface (HAT-refined into category tabs):

- Page-title is "Built-in tools" (HAT inline fix #5; sentence case since M25
  F3 leg 5a).
- 5 category tabs render in declaration order (Filesystem / Execution /
  Web / Connectors / Time); Filesystem selected by default. Connectors added by
  squawk 0032 (mirrors squawk 0028's studio.js Connectors category).
- Tab click switches the visible panel (active panel shows tiles, others
  hidden via the tabs [hidden] attr).
- Each category surfaces the expected tile counts (9/6/4/2 = 21 total).
- The tool NAME is the item link (M25 F3 leg 5b; the tile is no longer a
  click target): clicking it navigates to the per-tool editor at
  #settings/tools/<name>, which opens below the list.
- Toggle PUT round-trip persists across reload (in-flight gate awaited
  BEFORE the reload to avoid a race).
- Toggle click does NOT navigate (nothing on the tile but the name link
  navigates; the toggle only toggles enablement).
- Active tab persists across the post-toggle re-render (would otherwise
  bounce back to the Filesystem default each toggle).
- The Settings nav's tools link is labeled "Built-in tools" (HAT inline fix #5).
- Deep-link to #admin/tools/<name> loads the editor directly (hydrates
  pendingToolName and consumes via _tryConsumePendingTool).
"""

from __future__ import annotations

import pytest
from browser import _lists, _nav
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_admin_tools_renders_grid_with_4_tabs(app_clean: str, page: Page) -> None:
    """Page-title + 4 category tabs in declaration order; Filesystem panel
    is the default-active surface with 9 tiles visible.

    Python tab was removed from the admin tools grid (Leg 02 / later — the
    Python tools moved to the Execution category or were regrouped), then
    Connectors was added by squawk 0032. The current 5 tabs are:
    Filesystem, Execution, Web, Connectors, Time (M28).
    """
    _nav.goto(page, app_clean, "settings/tools")
    expect(page.locator(".area-admin .page-title")).to_have_text("Built-in tools", timeout=8000)

    tablist = page.locator(".area-admin .tablist")
    expect(tablist).to_be_visible()

    tabs = tablist.locator('[role="tab"]')
    expect(tabs).to_have_count(5)
    expect(tabs.nth(0)).to_have_text("Filesystem")
    expect(tabs.nth(1)).to_have_text("Execution")
    expect(tabs.nth(2)).to_have_text("Web")
    expect(tabs.nth(3)).to_have_text("Connectors")
    expect(tabs.nth(4)).to_have_text("Time")

    # Filesystem selected by default; its panel is the visible one.
    expect(page.locator('[data-testid="tab-filesystem"]')).to_have_attribute(
        "aria-selected", "true"
    )
    fs_panel = page.locator("#tools-panel-filesystem")
    expect(fs_panel).to_be_visible()
    expect(fs_panel.locator('[data-testid="tool-card"]')).to_have_count(9)


@pytest.mark.browser
def test_admin_tools_tab_click_switches_panel(app_clean: str, page: Page) -> None:
    """Clicking a sibling tab swaps the active panel: previously-active
    panel becomes hidden, target panel becomes visible with its tile set.
    """
    _nav.goto(page, app_clean, "settings/tools")
    expect(page.locator(".area-admin .page-title")).to_have_text("Built-in tools", timeout=8000)
    fs_panel = page.locator("#tools-panel-filesystem")
    web_panel = page.locator("#tools-panel-web")
    expect(fs_panel).to_be_visible()

    page.locator('[data-testid="tab-web"]').click()

    expect(web_panel).to_be_visible()
    expect(fs_panel).not_to_be_visible()
    expect(page.locator('[data-testid="tab-web"]')).to_have_attribute("aria-selected", "true")
    expect(web_panel.locator('[data-testid="tool-card"]')).to_have_count(4)


@pytest.mark.browser
def test_admin_tools_each_tab_renders_correct_tile_count(app_clean: str, page: Page) -> None:
    """All five panels' tile counts: 9/6/4/3/1 = 23 tools total (M25 F4 L6: the
    shared table, `tool-categories.js`, puts M23 F4 L3's
    `find_platform_destination` under Connectors; no copy had it, so it showed
    in no tab)."""
    _nav.goto(page, app_clean, "settings/tools")
    expect(page.locator(".area-admin .page-title")).to_have_text("Built-in tools", timeout=8000)

    expected = {
        "filesystem": 9,
        "execution": 6,
        "web": 4,
        "connectors": 3,
        "time": 1,
    }
    for cat, count in expected.items():
        page.locator(f'[data-testid="tab-{cat}"]').click()
        panel = page.locator(f"#tools-panel-{cat}")
        expect(panel).to_be_visible()
        expect(panel.locator('[data-testid="tool-card"]')).to_have_count(count)


@pytest.mark.browser
def test_admin_tools_connectors_tab_renders_its_three_tools_without_a_badge(
    app_clean: str, page: Page
) -> None:
    """Squawk 0032: the three connector tools render under the Connectors tab
    (the pre-fix TOOL_CATEGORIES mirror gap left them in no tab). Since M31 F4 L06
    (ledger row 6, A6) a tile carries no category badge: the tab is the category."""
    _nav.goto(page, app_clean, "settings/tools")
    expect(page.locator(".area-admin .page-title")).to_have_text("Built-in tools", timeout=8000)
    page.locator('[data-testid="tab-connectors"]').click()
    panel = page.locator("#tools-panel-connectors")
    expect(panel).to_be_visible()

    for name in ("send_to_platform_channel", "fetch_channel_history", "find_platform_destination"):
        tile = panel.locator(f'[data-testid="tool-card"][data-name="{name}"]')
        expect(tile).to_be_visible()
        expect(tile.locator(".badge")).to_have_count(0)


@pytest.mark.browser
def test_admin_tools_tile_click_navigates_to_editor(app_clean: str, page: Page) -> None:
    """Click the web_search name link: URL becomes #settings/tools/web_search
    and the editor mounts below the list (editor-title shows the tool name)."""
    _nav.goto(page, app_clean, "settings/tools")
    expect(page.locator(".area-admin .page-title")).to_have_text("Built-in tools", timeout=8000)
    page.locator('[data-testid="tab-web"]').click()
    link = _lists.item_link(page, "settings/tools", "web_search")
    expect(link).to_have_attribute("href", _nav.href("settings/tools/web_search"))
    link.click()
    expect(page.locator(".editor-title")).to_have_text("web_search", timeout=5000)
    _nav.expect_route(page, "settings/tools/web_search")
    expect(page.locator('#tools-panel-web [data-testid="tool-card"]')).to_have_count(4)


@pytest.mark.browser
def test_admin_tools_tile_body_is_not_a_click_target(app_clean: str, page: Page) -> None:
    """M25 F3 leg 5b: a click on the tile's description (away from the name
    link) does not open the tool, and the tile is not in the Tab order."""
    _nav.goto(page, app_clean, "settings/tools")
    expect(page.locator(".area-admin .page-title")).to_have_text("Built-in tools", timeout=8000)
    page.locator('[data-testid="tab-web"]').click()
    tile = _lists.list_row(page, "settings/tools", "web_search")
    expect(tile).not_to_have_attribute("tabindex", "0")
    initial_route = _nav.current_route(page)
    tile.locator(".entity-" + "tile-description").click()
    page.wait_for_timeout(300)
    _nav.expect_route(page, initial_route)
    expect(page.locator(".editor-title")).to_have_count(0)


@pytest.mark.browser
def test_admin_tools_tile_toggle_persists_across_reload(app_clean: str, page: Page) -> None:
    """Toggle web_search OFF, await the in-flight gate to clear (the
    Reviewer-flagged race), reload, switch back to the Web tab, and
    confirm the toggle is still OFF.
    """
    _nav.goto(page, app_clean, "settings/tools")
    expect(page.locator(".area-admin .page-title")).to_have_text("Built-in tools", timeout=8000)
    page.locator('[data-testid="tab-web"]').click()
    web_panel = page.locator("#tools-panel-web")
    toggle = web_panel.locator('input[data-testid="tool-toggle"][data-name="web_search"]')
    expect(toggle).to_be_checked()
    toggle.click(force=True)
    # Per design Reviewer: await the in-flight gate clearing BEFORE reload
    # so the PUT round-trip has actually committed. Without this, the
    # reload races the network and the assertion below flakes.
    expect(toggle).not_to_be_disabled(timeout=5000)
    expect(toggle).not_to_be_checked()

    page.reload()
    expect(page.locator(".area-admin .page-title")).to_have_text("Built-in tools", timeout=8000)
    page.locator('[data-testid="tab-web"]').click()
    toggle_after = page.locator(
        '#tools-panel-web input[data-testid="tool-toggle"][data-name="web_search"]'
    )
    expect(toggle_after).not_to_be_checked()


@pytest.mark.browser
def test_admin_tools_tile_toggle_does_not_navigate(app_clean: str, page: Page) -> None:
    """Clicking the toggle's interactive surface flips state but does NOT
    navigate to the editor (since M25 F3 leg 5b nothing on the tile but the
    name link navigates; the toggle's change event only toggles enablement).
    """
    _nav.goto(page, app_clean, "settings/tools")
    expect(page.locator(".area-admin .page-title")).to_have_text("Built-in tools", timeout=8000)
    initial_route = _nav.current_route(page)
    page.locator('[data-testid="tab-web"]').click()
    toggle = page.locator(
        '#tools-panel-web input[data-testid="tool-toggle"][data-name="web_search"]'
    )
    expect(toggle).to_be_checked()
    toggle.click(force=True)
    # Wait for the in-flight to clear before asserting URL — without this
    # the assertion happens during the optimistic re-render and could miss
    # a stray navigation.
    expect(toggle).not_to_be_disabled(timeout=5000)
    # URL stayed on the grid hash; editor is NOT mounted.
    _nav.expect_route(page, initial_route)
    expect(page.locator(".editor-title")).to_have_count(0)


@pytest.mark.browser
def test_admin_tools_active_tab_persists_across_toggle_re_render(
    app_clean: str, page: Page
) -> None:
    """Switch to the Web tab, toggle a tile (triggers a grid re-render
    after the PUT response). The user's active tab MUST stay on Web —
    otherwise every toggle bounces them back to the Filesystem default.
    """
    _nav.goto(page, app_clean, "settings/tools")
    expect(page.locator(".area-admin .page-title")).to_have_text("Built-in tools", timeout=8000)
    page.locator('[data-testid="tab-web"]').click()
    expect(page.locator('[data-testid="tab-web"]')).to_have_attribute("aria-selected", "true")
    toggle = page.locator(
        '#tools-panel-web input[data-testid="tool-toggle"][data-name="web_search"]'
    )
    toggle.click(force=True)
    expect(toggle).not_to_be_disabled(timeout=5000)

    # Active tab is still Web after re-render; Filesystem is NOT visible.
    expect(page.locator('[data-testid="tab-web"]')).to_have_attribute("aria-selected", "true")
    expect(page.locator("#tools-panel-web")).to_be_visible()
    expect(page.locator("#tools-panel-filesystem")).not_to_be_visible()


@pytest.mark.browser
def test_admin_tools_grid_tile_keyboard_navigation(app_clean: str, page: Page) -> None:
    """The tool name link is in the Tab order and Enter on it opens the tool
    (M25 F3 leg 5b: the link replaced the focusable tile). Space on the
    toggle flips it natively and does NOT navigate; the toggle is separately
    focusable, after its tile's link.
    """
    _nav.goto(page, app_clean, "settings/tools")
    expect(page.locator(".area-admin .page-title")).to_have_text("Built-in tools", timeout=8000)
    page.locator('[data-testid="tab-web"]').click()
    link = _lists.item_link(page, "settings/tools", "web_search")
    toggle = _lists.tool_toggle(page, "web_search")
    link.focus()
    expect(link).to_be_focused()
    page.keyboard.press("Tab")
    expect(toggle).to_be_focused()
    expect(toggle).to_be_checked()
    page.keyboard.press("Space")
    expect(toggle).not_to_be_checked()
    expect(toggle).not_to_be_disabled(timeout=5000)
    _nav.expect_route(page, "settings/tools")
    expect(page.locator(".editor-title")).to_have_count(0)
    # The re-rendered list gives focus back to the same toggle once its PUT
    # settles; put the tool back, then open it from its link with Enter.
    expect(toggle).to_be_focused()
    page.keyboard.press("Space")
    expect(toggle).to_be_checked()
    expect(toggle).not_to_be_disabled(timeout=5000)
    link.focus()
    page.keyboard.press("Enter")
    expect(page.locator(".editor-title")).to_have_text("web_search", timeout=5000)
    _nav.expect_route(page, "settings/tools/web_search")


@pytest.mark.browser
def test_admin_tools_settings_nav_label_is_built_in_tools(app_clean: str, page: Page) -> None:
    """HAT inline fix #5: the tools nav entry's label is "Built-in tools"
    (was "Tools"). Distinguishes from MCP / external tool surfaces while
    keeping the URL slug stable at #settings/tools.

    Since M25 F3 leg 5a the Settings nav is grouped links; the tools link sits
    under "Defaults for agents". MCP servers live in the Library.
    """
    _nav.goto(page, app_clean, "settings/appearance")
    link = _lists.settings_nav_link(page, "tools")
    expect(link).to_have_text("Built-in tools", timeout=5000)
    expect(link).to_have_attribute("href", _nav.href("settings/tools"))


@pytest.mark.browser
def test_admin_tools_deep_link_to_tool_loads_editor(app_clean: str, page: Page) -> None:
    """Direct navigation to #admin/tools/web_search hydrates the pending
    tool name and consumes via _tryConsumePendingTool — the editor mounts
    below the list, whose Web tab is active with the tool selected."""
    page.goto(f"{app_clean}#admin/tools/web_search")  # legacy URL on purpose (AC6)
    expect(page.locator(".editor-title")).to_have_text("web_search", timeout=8000)
    _nav.expect_route(page, "settings/tools/web_search")
    expect(page.locator('[data-testid="tab-web"]')).to_have_attribute("aria-selected", "true")
    _lists.expect_selected(page, "settings/tools", "web_search")
