"""Navigation + skip-link browser tests.

The Mission-08 app-picker-popover concept (F3 leg 02) is gone in Holograph.
Navigation is now flat .navlink buttons in #app-topnav — no popover, no
app-picker-button, no app-picker-option. The three picker-popover tests
(test_picker_renders_closed, test_picker_opens_on_click,
test_picker_keyboard_open_close) have been removed.

Retained:
- test_skip_link_first_tab — skip-link is preserved in Holograph.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_skip_link_first_tab(app_clean: str, page: Page) -> None:
    page.goto(app_clean)
    page.keyboard.press("Tab")
    active = page.evaluate("document.activeElement.className")
    assert "skip-link" in active, f"First Tab should land skip-link; got: {active!r}"
