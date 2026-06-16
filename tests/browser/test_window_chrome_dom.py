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

HAT-fix (Leg 2 re-open): the original tests only covered the "bridge present at
load" path via add_init_script. The real HAT failure on the Windows second window
was a timing bug: pywebview injects window.pywebview AFTER NavigationCompleted on
a background thread, so the pywebviewready event can fire before the listener is
registered (already-fired, silently missed). Three new timing tests cover:
  (a) bridge present before DOMContentLoaded → controls render immediately.
  (b) bridge absent at load, set later + pywebviewready dispatched → controls
      appear via the event listener path.
  (c) bridge absent at load, set later, NO event dispatched → controls appear
      via the poll backstop (window.pywebview polled every 100ms).
  (d) no bridge ever → no controls (browser mode, poll times out silently).

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


# ── HAT-fix timing tests (M15 F7 Leg 2 re-open) ─────────────────────────────
#
# These tests exercise the three timing paths fixed by the robust bridge
# detection helper (_watchBridge IIFE) — the scenarios the original tests
# missed because add_init_script always made the bridge present at load.


@pytest.mark.browser
def test_controls_render_when_bridge_present_before_domcontentloaded(
    app_clean: str, page: Page
) -> None:
    """(a) Bridge present before DOMContentLoaded → controls render immediately.

    Simulates the case where pywebview injects window.pywebview before or
    during script evaluation (path (a) in _watchBridge — the IIFE's synchronous
    check fires and calls renderTopBar() without waiting for any event).
    add_init_script runs before any page script, so window.pywebview is set
    before app.js's IIFE evaluates.
    """
    # Bridge present at script-eval time: _watchBridge (a) path, no event needed.
    page.add_init_script(_PYWEBVIEW_STUB)
    page.goto(app_clean, wait_until="domcontentloaded")
    # No manual event dispatch — controls must render via the synchronous (a) path.
    page.wait_for_selector("#app-topbar .pywebview-drag-region", timeout=5000)
    expect(page.locator("#app-topbar .win-controls")).to_have_count(1)
    expect(page.locator("#app-topbar .win-controls .win-ctrl-btn")).to_have_count(3)


@pytest.mark.browser
def test_controls_render_when_bridge_set_after_load_via_event(
    app_clean: str, page: Page
) -> None:
    """(b) Bridge absent at load, set later + pywebviewready fired → controls appear.

    Simulates the real WebView2 timing: pywebview injects window.pywebview on a
    background thread AFTER NavigationCompleted. No init_script — bridge is absent
    when app.js evaluates. Then the test sets window.pywebview and dispatches
    pywebviewready (exactly what pywebview's finish.js does), which _watchBridge's
    event listeners catch.
    """
    # No add_init_script — bridge absent at script-eval time.
    page.goto(app_clean, wait_until="domcontentloaded")
    page.wait_for_selector("#app-topbar .app-picker-button", timeout=8000)

    # No controls yet — bridge not present.
    assert page.locator("#app-topbar .win-controls").count() == 0

    # Inject bridge then dispatch pywebviewready (mirrors finish.js exactly).
    page.evaluate(
        """
        window.pywebview = {
          api: {
            minimize: function() {},
            toggle_maximize: function() {},
            close: function() {}
          }
        };
        window.dispatchEvent(new CustomEvent('pywebviewready'));
        """
    )
    # Controls must appear via the event-listener path.
    page.wait_for_selector("#app-topbar .pywebview-drag-region", timeout=5000)
    expect(page.locator("#app-topbar .win-controls")).to_have_count(1)
    expect(page.locator("#app-topbar .win-controls .win-ctrl-btn")).to_have_count(3)


@pytest.mark.browser
def test_controls_render_when_bridge_set_after_load_via_poll(
    app_clean: str, page: Page
) -> None:
    """(c) Bridge absent at load, set later, NO event dispatched → controls via poll.

    Simulates the edge case where the pywebviewready event fires before the
    listener is attached (already-fired, missed) but window.pywebview was set.
    The poll backstop in _watchBridge detects window.pywebview within 100ms
    and calls renderTopBar() without waiting for any event.
    """
    # No add_init_script — bridge absent at script-eval time.
    page.goto(app_clean, wait_until="domcontentloaded")
    page.wait_for_selector("#app-topbar .app-picker-button", timeout=8000)

    # No controls yet.
    assert page.locator("#app-topbar .win-controls").count() == 0

    # Set window.pywebview WITHOUT dispatching any event — poll backstop must detect it.
    page.evaluate(
        """
        window.pywebview = {
          api: {
            minimize: function() {},
            toggle_maximize: function() {},
            close: function() {}
          }
        };
        """
    )
    # Controls must appear within the poll interval (100ms × up to 100 ticks = 10s).
    # Use a generous 3s timeout — on CI the first poll tick (100ms) should be enough.
    page.wait_for_selector("#app-topbar .pywebview-drag-region", timeout=3000)
    expect(page.locator("#app-topbar .win-controls")).to_have_count(1)
    expect(page.locator("#app-topbar .win-controls .win-ctrl-btn")).to_have_count(3)
