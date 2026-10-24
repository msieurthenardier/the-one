"""DD8-19 (M31 F4 L08a): the Appearance page's theme listener does not outlive it.

``theme.js``'s old ``renderToggle`` added a document ``theme-preference-changed``
listener that only the NEXT ``renderToggle`` call cleaned up, so after leaving
Appearance the listener (and the detached page it updated) stayed alive.

The picker is now an ``App.ui.radioGroup`` built by ``system-page.js``; its
listener prunes itself: on each event it checks that the group is still in the
document and removes itself when it is not. The test therefore spies on
``document.addEventListener`` / ``removeEventListener`` before the page loads,
leaves Appearance, dispatches the event ONCE and asserts that the adds and
removes balance and that the old page's radio was not updated. It never asserts
"the listener is gone" before the dispatch: a pruning listener legitimately
stays until the first event.
"""

from __future__ import annotations

import pytest
from browser import _nav
from playwright.sync_api import Page, expect

_SPY = """
(() => {
  const EVT = 'theme-preference-changed';
  window.__themeListeners = { adds: 0, removes: 0 };
  const add = document.addEventListener.bind(document);
  const rem = document.removeEventListener.bind(document);
  document.addEventListener = function (type, fn, opts) {
    if (type === EVT) window.__themeListeners.adds += 1;
    return add(type, fn, opts);
  };
  document.removeEventListener = function (type, fn, opts) {
    if (type === EVT) window.__themeListeners.removes += 1;
    return rem(type, fn, opts);
  };
})();
"""


@pytest.mark.browser
def test_theme_listener_is_pruned_after_leaving_appearance(app_clean: str, page: Page) -> None:
    page.add_init_script(_SPY)
    _nav.goto(page, app_clean, "settings/appearance")
    picker = page.locator('[data-testid="theme-picker"]')
    expect(picker).to_be_visible(timeout=8000)
    page.evaluate("window.App.theme.set('light')")
    # Hold the old page's radio so its state stays inspectable once detached.
    page.evaluate(
        "window.__oldDark = document.querySelector('[data-testid=\"theme-option-dark\"]');"
        "window.__oldLight = document.querySelector('[data-testid=\"theme-option-light\"]');"
    )
    expect(page.locator('[data-testid="theme-option-light"]')).to_be_checked()

    _nav.goto(page, app_clean, "settings/prompts")
    expect(page.locator('[data-testid="theme-picker"]')).to_have_count(0)
    assert page.evaluate("document.contains(window.__oldDark)") is False

    # One event after leaving: the old page must not be updated, and the
    # listener must have removed itself (adds and removes balance).
    page.evaluate(
        "document.dispatchEvent(new CustomEvent('theme-preference-changed',"
        " { detail: { pref: 'dark' } }))"
    )
    state = page.evaluate(
        "({ listeners: window.__themeListeners, darkChecked: window.__oldDark.checked,"
        " lightChecked: window.__oldLight.checked })"
    )
    assert state["darkChecked"] is False, "the detached page's radio was updated"
    assert state["lightChecked"] is True
    assert state["listeners"]["adds"] >= 1
    assert state["listeners"]["adds"] == state["listeners"]["removes"], state["listeners"]


@pytest.mark.browser
def test_remounting_appearance_does_not_stack_listeners(app_clean: str, page: Page) -> None:
    """Entering Appearance again leaves one live listener: the old one prunes on
    the next event, the new one updates the visible picker."""
    page.add_init_script(_SPY)
    _nav.goto(page, app_clean, "settings/appearance")
    expect(page.locator('[data-testid="theme-picker"]')).to_be_visible(timeout=8000)
    _nav.goto(page, app_clean, "settings/prompts")
    _nav.goto(page, app_clean, "settings/appearance")
    expect(page.locator('[data-testid="theme-picker"]')).to_be_visible(timeout=8000)
    page.evaluate("window.App.theme.set('dark')")
    expect(page.locator('[data-testid="theme-option-dark"]')).to_be_checked()
    counts = page.evaluate("window.__themeListeners")
    assert counts["adds"] - counts["removes"] <= 1, counts


@pytest.mark.browser
def test_leaving_appearance_removes_listener_without_any_theme_event(
    app_clean: str, page: Page
) -> None:
    """The listener is removed on teardown, not only on the next event."""
    page.add_init_script(_SPY)
    _nav.goto(page, app_clean, "settings/appearance")
    expect(page.locator('[data-testid="theme-picker"]')).to_be_visible(timeout=8000)
    for _ in range(3):
        _nav.goto(page, app_clean, "settings/prompts")
        _nav.goto(page, app_clean, "settings/appearance")
        expect(page.locator('[data-testid="theme-picker"]')).to_be_visible(timeout=8000)
    _nav.goto(page, app_clean, "settings/prompts")
    expect(page.locator('[data-testid="theme-picker"]')).to_have_count(0)
    counts = page.evaluate("window.__themeListeners")
    assert counts["adds"] >= 1
    assert counts["adds"] == counts["removes"], counts
