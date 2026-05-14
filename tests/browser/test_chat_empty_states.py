"""Empty-state coverage for the Chat area.

Three states drive the first-run flow:
  (1) No provider, no agent  → eyebrow IDLE, step01 .next, step02 empty
  (2) Provider, no agent     → eyebrow IDLE, step01 .done, step02 .next
  (3) Agent ready, no session→ eyebrow READY, no step cards
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from tests.browser.seeders import SeededApp


@pytest.mark.browser
def test_chat_empty_first_run_shows_two_step_cards(app_clean: str, page: Page) -> None:
    """Cold first-run: no provider, no agent. Step 01 is next, Step 02 is empty."""
    page.goto(app_clean)
    expect(page.locator(".chat-empty .eyebrow:has-text('HOLOGRAPH · CHAT · IDLE')")).to_be_visible(timeout=4000)
    expect(page.locator(".chat-empty .brack:has-text('Two steps to your first message')")).to_be_visible()
    step1 = page.locator(".chat-empty .step:has-text('STEP 01')")
    step2 = page.locator(".chat-empty .step:has-text('STEP 02')")
    expect(step1).to_be_visible()
    expect(step2).to_be_visible()
    # Step 1 is `.next` (highlighted as the active step). Step 2 carries no
    # state class because the user has not yet unlocked it.
    expect(step1).to_have_class("step next", timeout=1000)
    expect(step2).to_have_class("step")


@pytest.mark.browser
def test_chat_empty_provider_only_shows_step01_done(app_with_provider: SeededApp, page: Page) -> None:
    """One provider, no agents. Step 01 is .done, Step 02 is .next."""
    page.goto(app_with_provider.base_url)
    expect(page.locator(".chat-empty .eyebrow:has-text('HOLOGRAPH · CHAT · IDLE')")).to_be_visible(timeout=4000)
    expect(page.locator(".chat-empty .brack:has-text('One step left')")).to_be_visible()
    step1 = page.locator(".chat-empty .step:has-text('STEP 01')")
    step2 = page.locator(".chat-empty .step:has-text('STEP 02')")
    expect(step1).to_have_class("step done", timeout=1000)
    expect(step2).to_have_class("step next")


@pytest.mark.browser
def test_chat_empty_agent_ready_shows_ready_eyebrow(app_with_agent: SeededApp, page: Page) -> None:
    """Provider + agent present, no session. Eyebrow READY, no step cards."""
    page.goto(app_with_agent.base_url)
    expect(page.locator(".chat-empty .eyebrow:has-text('HOLOGRAPH · CHAT · READY')")).to_be_visible(timeout=4000)
    expect(page.locator(".chat-empty .brack:has-text('Ready when you are')")).to_be_visible()
    # No step cards in the ready state.
    expect(page.locator(".chat-empty .step")).to_have_count(0)
