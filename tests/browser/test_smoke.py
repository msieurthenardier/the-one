"""Smoke test: confirms Playwright + Chromium are installed and working.

This test does NOT require the-one app to be running. It loads a data: URL
to verify the toolchain. Real flow tests against the app land in legs 05-07.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import sync_playwright


@pytest.mark.browser
def test_playwright_loads_data_url() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.goto("data:text/html,<title>the-one smoke</title><h1>hi</h1>")
            assert page.title() == "the-one smoke"
            assert page.locator("h1").text_content() == "hi"
        finally:
            browser.close()
