"""Empty-state coverage for the Admin area (L4.4).

When no providers exist, the Admin · LLM Providers subtab renders a
4-card provider-type grid (Anthropic RECOMMENDED · OpenAI · OpenAI-compatible
· Ollama) instead of the legacy "No providers configured…" canvas. Each card
preselects its type in the provider-editor on click.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_admin_providers_empty_shows_four_provider_cards(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#admin/providers")
    expect(page.locator(".eyebrow:has-text('SYSTEM · LLM PROVIDERS')")).to_be_visible(timeout=4000)
    expect(page.locator(".area-title:has-text('LLM Providers')")).to_be_visible()
    expect(page.locator(".provider-type-card:has-text('Anthropic')")).to_be_visible()
    expect(page.locator(".provider-type-card:has-text('OpenAI')").first).to_be_visible()
    expect(page.locator(".provider-type-card:has-text('Ollama')")).to_be_visible()
    rec = page.locator(".provider-type-card:has-text('Anthropic')")
    expect(rec.locator(".provider-type-cat")).to_have_text("RECOMMENDED")
