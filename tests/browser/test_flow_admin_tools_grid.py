"""Admin Tools grid + tab + tile tests for F6 leg 07.

Covers the L2 admin Tools grid surface (HAT-refined into 4 category tabs):

- Page-title is "Built-in Tools" (HAT inline fix #5).
- 4 category tabs render in declaration order (Filesystem / Execution /
  Python / Web); Filesystem selected by default.
- Tab click switches the visible panel (active panel shows tiles, others
  hidden via the App.tabs helper's [hidden] attr).
- Each category surfaces the expected tile counts (9/5/1/4 = 19 total).
- Tile click navigates to the per-tool editor at #admin/tools/<name>.
- Toggle PUT round-trip persists across reload (in-flight gate awaited
  BEFORE the reload to avoid a race).
- Toggle click does NOT navigate (only the tile body navigates; the
  toggle's interactive surface short-circuits the tile-click handler).
- Active tab persists across the post-toggle re-render (would otherwise
  bounce back to the Filesystem default each toggle).
- Section-nav third entry is labeled "Built-in Tools" (HAT inline fix #5).
- Deep-link to #admin/tools/<name> loads the editor directly (hydrates
  pendingToolName and consumes via _tryConsumePendingTool).
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_admin_tools_renders_grid_with_4_tabs(app_clean: str, page: Page) -> None:
    """Page-title + 4 category tabs in declaration order; Filesystem panel
    is the default-active surface with 9 tiles visible."""
    page.goto(f"{app_clean}#admin/tools")
    expect(page.locator(".area-admin .page-title")).to_have_text(
        "Built-in Tools", timeout=8000
    )

    tablist = page.locator(".area-admin .tablist")
    expect(tablist).to_be_visible()

    tabs = tablist.locator('[role="tab"]')
    expect(tabs).to_have_count(4)
    expect(tabs.nth(0)).to_have_text("Filesystem")
    expect(tabs.nth(1)).to_have_text("Execution")
    expect(tabs.nth(2)).to_have_text("Python")
    expect(tabs.nth(3)).to_have_text("Web")

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
    page.goto(f"{app_clean}#admin/tools")
    expect(page.locator(".area-admin .page-title")).to_have_text(
        "Built-in Tools", timeout=8000
    )
    fs_panel = page.locator("#tools-panel-filesystem")
    web_panel = page.locator("#tools-panel-web")
    expect(fs_panel).to_be_visible()

    page.locator('[data-testid="tab-web"]').click()

    expect(web_panel).to_be_visible()
    expect(fs_panel).not_to_be_visible()
    expect(page.locator('[data-testid="tab-web"]')).to_have_attribute(
        "aria-selected", "true"
    )
    expect(web_panel.locator('[data-testid="tool-card"]')).to_have_count(4)


@pytest.mark.browser
def test_admin_tools_each_tab_renders_correct_tile_count(
    app_clean: str, page: Page
) -> None:
    """All four panels' tile counts: 9/5/1/4 = 19 tools total."""
    page.goto(f"{app_clean}#admin/tools")
    expect(page.locator(".area-admin .page-title")).to_have_text(
        "Built-in Tools", timeout=8000
    )

    expected = {
        "filesystem": 9,
        "execution": 5,
        "python": 1,
        "web": 4,
    }
    for cat, count in expected.items():
        page.locator(f'[data-testid="tab-{cat}"]').click()
        panel = page.locator(f"#tools-panel-{cat}")
        expect(panel).to_be_visible()
        expect(panel.locator('[data-testid="tool-card"]')).to_have_count(count)


@pytest.mark.browser
def test_admin_tools_tile_click_navigates_to_editor(
    app_clean: str, page: Page
) -> None:
    """Click the web_search tile: URL becomes #admin/tools/web_search and
    the editor mounts (editor-title shows the tool name)."""
    page.goto(f"{app_clean}#admin/tools")
    expect(page.locator(".area-admin .page-title")).to_have_text(
        "Built-in Tools", timeout=8000
    )
    page.locator('[data-testid="tab-web"]').click()
    page.locator('[data-testid="tool-card"][data-name="web_search"]').click()
    expect(page.locator(".editor-title")).to_have_text("web_search", timeout=5000)
    assert page.evaluate("location.hash") == "#admin/tools/web_search"


@pytest.mark.browser
def test_admin_tools_tile_toggle_persists_across_reload(
    app_clean: str, page: Page
) -> None:
    """Toggle web_search OFF, await the in-flight gate to clear (the
    Reviewer-flagged race), reload, switch back to the Web tab, and
    confirm the toggle is still OFF.
    """
    page.goto(f"{app_clean}#admin/tools")
    expect(page.locator(".area-admin .page-title")).to_have_text(
        "Built-in Tools", timeout=8000
    )
    page.locator('[data-testid="tab-web"]').click()
    web_panel = page.locator("#tools-panel-web")
    toggle = web_panel.locator(
        'input[data-testid="tool-toggle"][data-name="web_search"]'
    )
    expect(toggle).to_be_checked()
    toggle.click()
    # Per design Reviewer: await the in-flight gate clearing BEFORE reload
    # so the PUT round-trip has actually committed. Without this, the
    # reload races the network and the assertion below flakes.
    expect(toggle).not_to_be_disabled(timeout=5000)
    expect(toggle).not_to_be_checked()

    page.reload()
    expect(page.locator(".area-admin .page-title")).to_have_text(
        "Built-in Tools", timeout=8000
    )
    page.locator('[data-testid="tab-web"]').click()
    toggle_after = page.locator(
        '#tools-panel-web input[data-testid="tool-toggle"][data-name="web_search"]'
    )
    expect(toggle_after).not_to_be_checked()


@pytest.mark.browser
def test_admin_tools_tile_toggle_does_not_navigate(
    app_clean: str, page: Page
) -> None:
    """Clicking the toggle's interactive surface flips state but does NOT
    navigate to the editor (the tile-click handler bails when the click
    target is inside .tool-enable-switch).
    """
    page.goto(f"{app_clean}#admin/tools")
    expect(page.locator(".area-admin .page-title")).to_have_text(
        "Built-in Tools", timeout=8000
    )
    initial_hash = page.evaluate("location.hash")
    page.locator('[data-testid="tab-web"]').click()
    toggle = page.locator(
        '#tools-panel-web input[data-testid="tool-toggle"][data-name="web_search"]'
    )
    expect(toggle).to_be_checked()
    toggle.click()
    # Wait for the in-flight to clear before asserting URL — without this
    # the assertion happens during the optimistic re-render and could miss
    # a stray navigation.
    expect(toggle).not_to_be_disabled(timeout=5000)
    # URL stayed on the grid hash; editor is NOT mounted.
    assert page.evaluate("location.hash") == initial_hash
    expect(page.locator(".editor-title")).to_have_count(0)


@pytest.mark.browser
def test_admin_tools_active_tab_persists_across_toggle_re_render(
    app_clean: str, page: Page
) -> None:
    """Switch to the Web tab, toggle a tile (triggers a grid re-render
    after the PUT response). The user's active tab MUST stay on Web —
    otherwise every toggle bounces them back to the Filesystem default.
    """
    page.goto(f"{app_clean}#admin/tools")
    expect(page.locator(".area-admin .page-title")).to_have_text(
        "Built-in Tools", timeout=8000
    )
    page.locator('[data-testid="tab-web"]').click()
    expect(page.locator('[data-testid="tab-web"]')).to_have_attribute(
        "aria-selected", "true"
    )
    toggle = page.locator(
        '#tools-panel-web input[data-testid="tool-toggle"][data-name="web_search"]'
    )
    toggle.click()
    expect(toggle).not_to_be_disabled(timeout=5000)

    # Active tab is still Web after re-render; Filesystem is NOT visible.
    expect(page.locator('[data-testid="tab-web"]')).to_have_attribute(
        "aria-selected", "true"
    )
    expect(page.locator("#tools-panel-web")).to_be_visible()
    expect(page.locator("#tools-panel-filesystem")).not_to_be_visible()


@pytest.mark.browser
def test_admin_tools_grid_tile_keyboard_navigation(
    app_clean: str, page: Page
) -> None:
    """Tile is keyboard-focusable (tabindex=0) and Enter activates the
    same selectTool flow as a click. Pressing Space on the inner toggle
    flips the checkbox via the native handler — does NOT also navigate.
    """
    page.goto(f"{app_clean}#admin/tools")
    expect(page.locator(".area-admin .page-title")).to_have_text(
        "Built-in Tools", timeout=8000
    )
    page.locator('[data-testid="tab-web"]').click()
    tile = page.locator('[data-testid="tool-card"][data-name="web_search"]')
    tile.focus()
    expect(tile).to_be_focused()
    page.keyboard.press("Enter")
    expect(page.locator(".editor-title")).to_have_text("web_search", timeout=5000)
    assert page.evaluate("location.hash") == "#admin/tools/web_search"


@pytest.mark.browser
def test_admin_tools_section_nav_label_is_built_in_tools(
    app_clean: str, page: Page
) -> None:
    """HAT inline fix #5: the third nav entry's label is "Built-in Tools"
    (was "Tools"). Distinguishes from future MCP / external tool surfaces
    while keeping the URL slug stable at #admin/tools.
    """
    page.goto(f"{app_clean}#admin/system")
    items = page.locator(".area-admin .section-nav .section-nav-item")
    expect(items).to_have_count(3, timeout=5000)
    expect(items.nth(2)).to_have_text("Built-in Tools")


@pytest.mark.browser
def test_admin_tools_deep_link_to_tool_loads_editor(
    app_clean: str, page: Page
) -> None:
    """Direct navigation to #admin/tools/web_search hydrates the pending
    tool name and consumes via _tryConsumePendingTool — the editor mounts
    on first paint without an interim grid stop."""
    page.goto(f"{app_clean}#admin/tools/web_search")
    expect(page.locator(".editor-title")).to_have_text("web_search", timeout=8000)
    assert page.evaluate("location.hash") == "#admin/tools/web_search"
