"""Flight 6 leg 1a (visible-fixes): the Settings-side fixes.

* DD3 (squawk 0116) -- the Built-in tools tiles' name never overlaps its badge,
  in both themes at 1024 and 1440 wide, and a short name is not truncated early;
* squawk 0114 -- every tool editor ``field-info-icon`` has an accessible name.

(The provider-editor half moved to ``test_flow_provider_visible_fixes.py`` with
providers, sortie 02.)

Falls in the ``settings`` lane (``test_flow_settings_*``).
"""

from __future__ import annotations

import pytest
from browser import _lists, _nav
from browser._a11y_resolvers import assert_controls_labelled_and_described
from playwright.sync_api import Page, expect


def _overlap(page: Page, tile_sel: str, name_sel: str, badge_sel: str) -> dict:
    return page.evaluate(
        """([t, n, b]) => {
          const tile = document.querySelector(t);
          const name = tile.querySelector(n).getBoundingClientRect();
          const badge = tile.querySelector(b).getBoundingClientRect();
          const tr = tile.getBoundingClientRect();
          return {
            overlap: name.right > badge.left + 0.5 && name.left < badge.right &&
                     name.bottom > badge.top && name.top < badge.bottom,
            badgeInside: badge.right <= tr.right + 0.5 && badge.left >= tr.left,
            nameRight: name.right, badgeLeft: badge.left,
          };
        }""",
        [tile_sel, name_sel, badge_sel],
    )


@pytest.mark.browser
@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [1024, 1440])
def test_tool_tile_name_never_overlaps_badge(
    app_clean: str, page: Page, scheme: str, width: int
) -> None:
    page.emulate_media(color_scheme=scheme)
    page.set_viewport_size({"width": width, "height": 900})
    # A long tool name (the DOM text is swapped; the names are fixed).
    _nav.goto(page, app_clean, "settings/tools")
    tile = page.locator('[data-testid="tool-card"]').first
    expect(tile).to_be_visible(timeout=8000)
    short_fits = tile.locator(".tool-tile-link").evaluate("e => e.scrollWidth <= e.clientWidth")
    assert short_fits, "short tool name truncated early"
    page.evaluate(
        "(n) => { document.querySelector('[data-testid=\"tool-card\"] .tool-tile-link')"
        ".textContent = n; }",
        "an_extremely_long_tool_name_" + "y" * 90,
    )
    r = _overlap(page, '[data-testid="tool-card"]', ".tool-tile-link", ".admin-tool-badge")
    assert not r["overlap"], r
    assert r["badgeInside"], r


# ── 0114: info icons are named ───────────────────────────────────────────


@pytest.mark.browser
def test_tools_editor_info_icons_have_accessible_names(app_clean: str, page: Page) -> None:
    _nav.goto(page, app_clean, "settings/tools")
    _lists.open_tool(page, "web_search")
    icons = page.locator("button.field-info-icon")
    expect(icons.first).to_be_attached(timeout=8000)
    for i in range(icons.count()):
        assert icons.nth(i).get_attribute("aria-describedby") is None, i
    assert_controls_labelled_and_described(page, ".settings-item")
