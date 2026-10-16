"""Focus after an in-place tool action (M25 F6 L1b, flight DD2).

Keyboard-driven (focus on the button, then Enter): a Save or edit-mode Cancel
leaves focus on the editor's `.editor-title`; a Test returns focus to its own button once
it re-enables. The provider cases live in `test_flow_provider_focus_after.py` (squawk 0189).
"""

from __future__ import annotations

import json

import pytest
from browser import _lists, _nav
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

TITLE = ".editor-title"


def _press(page: Page, testid: str) -> None:
    btn = page.locator(f'[data-testid="{testid}"]')
    expect(btn).to_be_enabled()
    btn.focus()
    page.keyboard.press("Enter")


def test_tool_save_cancel_and_test(app_clean: str, page: Page) -> None:
    _nav.goto_settled(page, app_clean, "settings/tools/web_search")
    expect(page.locator('[data-testid="save-tool-btn"]')).to_be_visible(timeout=8000)
    # Cancel
    page.locator('[data-field="search_backend"]').select_option("searxng")
    _press(page, "cancel-tool-btn")
    expect(page.locator('[data-testid="cancel-tool-btn"]')).to_be_disabled(timeout=8000)
    expect(page.locator(TITLE)).to_be_focused(timeout=8000)
    # Save
    page.locator('[data-field="search_backend"]').select_option("searxng")
    page.locator('input[data-field="searxng_base_url"]').fill("https://searx.example.org")
    _press(page, "save-tool-btn")
    expect(page.locator('[data-testid="save-tool-btn"]')).to_be_disabled(timeout=8000)
    expect(page.locator(TITLE)).to_be_focused(timeout=8000)
    # Test
    page.route(
        "**/api/tools/configs/web_search/test",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"ok": True, "output": "fine", "duration_ms": 1}),
        ),
    )
    btn = page.locator('[data-testid="test-tool-btn"]')
    btn.focus()
    page.keyboard.press("Enter")
    expect(btn).to_be_enabled(timeout=8000)
    expect(btn).to_be_focused(timeout=8000)
    _lists.close_item(page)
