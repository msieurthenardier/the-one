"""Browser tests for window-chrome DOM-shape (M15 F7 Leg 2).

Verifies that:
1. When window.pywebview is present (stubbed via add_init_script), renderTopBar()
   injects the .pywebview-drag-region element and the .win-controls group into
   #app-topbar.
2. The .pywebview-drag-region element contains NO interactive children (buttons,
   inputs, anchors) — only outside elements can reliably receive click events
   since pywebview has no no-drag exemption.
3. The .win-controls group is a sibling of .app-topbar-actions, not a descendant
   of .pywebview-drag-region.
4. Nav (.app-picker-button) click handlers still fire when pywebview is stubbed.
5. When window.pywebview is absent (plain browser), neither .pywebview-drag-region
   nor .win-controls appears in #app-topbar.

The pywebviewready event is dispatched manually after the stub is installed to
trigger the second renderTopBar() call (the DOMContentLoaded render fires before
add_init_script takes effect; pywebviewready is what draws the controls).

These tests are marked @pytest.mark.browser and excluded from the default CI run
(see pyproject.toml addopts). The native drag-move effect and frameless resize are
HAT-verified on a real Windows install (Leg 7).
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


# Stub that mirrors pywebview's real runtime form (zero-arg JS calls after
# pywebview strips self).  Calls are recorded on window._apiCalls for assertions.
_PYWEBVIEW_STUB = """
window.pywebview = {
  api: {
    minimize: function() {
      window._apiCalls = window._apiCalls || [];
      window._apiCalls.push('minimize');
    },
    toggle_maximize: function() {
      window._apiCalls = window._apiCalls || [];
      window._apiCalls.push('toggle_maximize');
    },
    close: function() {
      window._apiCalls = window._apiCalls || [];
      window._apiCalls.push('close');
    }
  }
};
"""


def _load_with_pywebview(page: Page, base_url: str) -> None:
    """Navigate to the app with window.pywebview pre-stubbed and pywebviewready fired."""
    page.add_init_script(_PYWEBVIEW_STUB)
    page.goto(base_url, wait_until="domcontentloaded")
    # pywebviewready is what triggers the second renderTopBar() call that draws
    # the controls — dispatch it now that the bridge stub is present.
    page.evaluate("window.dispatchEvent(new Event('pywebviewready'))")
    # Wait for the topbar to settle (drag region must exist).
    page.wait_for_selector(".pywebview-drag-region", timeout=5000)


@pytest.mark.browser
def test_drag_region_present_when_pywebview_stub_active(
    app_clean: str, page: Page
) -> None:
    """With window.pywebview stubbed, .pywebview-drag-region is in #app-topbar."""
    _load_with_pywebview(page, app_clean)
    drag_region = page.locator("#app-topbar .pywebview-drag-region")
    expect(drag_region).to_have_count(1)


@pytest.mark.browser
def test_win_controls_present_when_pywebview_stub_active(
    app_clean: str, page: Page
) -> None:
    """With window.pywebview stubbed, .win-controls group is in #app-topbar."""
    _load_with_pywebview(page, app_clean)
    win_controls = page.locator("#app-topbar .win-controls")
    expect(win_controls).to_have_count(1)
    # Three buttons: minimize, maximize, close.
    expect(win_controls.locator(".win-ctrl-btn")).to_have_count(3)


@pytest.mark.browser
def test_drag_region_has_no_interactive_children(
    app_clean: str, page: Page
) -> None:
    """The .pywebview-drag-region element must contain NO interactive elements.

    pywebview has no no-drag exemption: only elements that are siblings of
    (not descendants of) the drag region can receive click events reliably.
    """
    _load_with_pywebview(page, app_clean)
    # Count interactive descendants of the drag region.
    interactive_count = page.evaluate(
        """
        (function() {
          var region = document.querySelector('.pywebview-drag-region');
          if (!region) return -1;
          return region.querySelectorAll('button, input, a, select, textarea').length;
        })()
        """
    )
    assert interactive_count == 0, (
        f"drag-region must have no interactive children; found {interactive_count}"
    )


@pytest.mark.browser
def test_win_controls_are_sibling_of_drag_region_not_descendant(
    app_clean: str, page: Page
) -> None:
    """.win-controls must NOT be inside .pywebview-drag-region."""
    _load_with_pywebview(page, app_clean)
    inside_drag = page.evaluate(
        """
        (function() {
          var region = document.querySelector('.pywebview-drag-region');
          if (!region) return false;
          return region.querySelector('.win-controls') !== null;
        })()
        """
    )
    assert inside_drag is False, ".win-controls must be a sibling, not inside .pywebview-drag-region"


@pytest.mark.browser
def test_nav_buttons_still_fire_when_pywebview_stub_active(
    app_clean: str, page: Page
) -> None:
    """Nav (.app-picker-button) click handlers still navigate even with pywebview stub.

    Confirms that the drag-region does not swallow clicks on the nav buttons
    (they are siblings of the drag-region, not descendants).
    """
    _load_with_pywebview(page, app_clean)
    # Click the first nav button (outside drag region) and verify hash changes.
    first_btn = page.locator("#app-topbar .app-picker-button").first
    area_id = first_btn.get_attribute("data-area")
    first_btn.click()
    # The hash should update to the area id.
    page.wait_for_function(
        f"location.hash === '#{area_id}'",
        timeout=3000,
    )


@pytest.mark.browser
def test_no_controls_without_pywebview(app_clean: str, page: Page) -> None:
    """In plain browser mode (no window.pywebview), no controls or drag-region appear."""
    # Navigate WITHOUT the stub — plain browser mode.
    page.goto(app_clean, wait_until="domcontentloaded")
    page.wait_for_selector("#app-topbar .app-picker-button", timeout=8000)

    # Neither element should exist.
    assert page.locator("#app-topbar .pywebview-drag-region").count() == 0
    assert page.locator("#app-topbar .win-controls").count() == 0
