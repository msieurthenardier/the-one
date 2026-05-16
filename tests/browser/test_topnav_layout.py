"""L7 — topnav layout regression guards.

These are cheap contract tests that catch the M10 regression where
``.topnav-spacer`` had no rule and the right cluster collapsed against
the search. They run on the dark theme only (the rule is theme-agnostic).
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_topnav_spacer_grows(app_clean: str, page: Page) -> None:
    page.goto(app_clean)
    expect(page.locator(".topnav-spacer")).to_be_visible()
    flex_grow = page.evaluate(
        "() => getComputedStyle(document.querySelector('.topnav-spacer')).flexGrow"
    )
    assert flex_grow == "1", f"topnav-spacer flex-grow regressed: {flex_grow!r}"


@pytest.mark.browser
def test_topnav_search_wrap_has_width(app_clean: str, page: Page) -> None:
    page.goto(app_clean)
    width = page.evaluate(
        "() => document.querySelector('.search-wrap').getBoundingClientRect().width"
    )
    # 240 from the CSS rule; allow 4px tolerance for padding/border.
    assert 236 <= width <= 248, f"search-wrap width regressed: {width}"


@pytest.mark.browser
def test_topnav_event_fires_on_area_switch(app_clean: str, page: Page) -> None:
    page.goto(app_clean)
    page.evaluate(
        """() => {
            window.__rerenderCount = 0;
            document.addEventListener('topnav:rerender', () => window.__rerenderCount++);
        }"""
    )
    page.locator('button[data-area="studio"]').click()
    page.wait_for_function("() => window.__rerenderCount >= 1", timeout=2000)
    count = page.evaluate("() => window.__rerenderCount")
    assert count >= 1, f"topnav:rerender did not fire on area switch (count={count})"
