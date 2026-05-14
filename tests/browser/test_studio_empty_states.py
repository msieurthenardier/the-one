"""Empty-state coverage for the Studio · Agents area (L4.2).

When no agents exist on the Agents sub-tab, the Studio body renders a
bracket-framed headline + two CTAs (+ NEW AGENT and → start from preset),
sitting BELOW the area-header (which already carries the STUDIO · AGENTS
eyebrow and the dynamic subtitle).
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_studio_agents_empty_shows_bracket_and_two_ctas(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#studio/agents")
    expect(page.locator(".eyebrow:has-text('STUDIO · AGENTS')").first).to_be_visible(timeout=4000)
    expect(page.locator(".brack:has-text('Build your first agent')")).to_be_visible()
    expect(page.locator(".btn-mono:has-text('NEW AGENT')")).to_be_visible()
    expect(page.locator("button:has-text('start from preset')")).to_be_visible()
