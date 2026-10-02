"""Skip-link browser test (F3 leg 02; the dead picker tests retired with the
top bar in M25 F2 leg 6)."""

from __future__ import annotations

import pytest
from playwright.sync_api import Page


@pytest.mark.browser
def test_skip_link_first_tab(app_clean: str, page: Page) -> None:
    page.goto(app_clean)
    page.keyboard.press("Tab")
    active = page.evaluate("document.activeElement.className")
    assert "skip-link" in active, f"First Tab should land skip-link; got: {active!r}"
