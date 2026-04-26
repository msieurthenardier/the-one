"""End-to-end flow test: chat with mock agent.

Drives a real Chromium session through the chat flow:
- Open #chat with seeded mock provider + agent
- WebSocket connects, session auto-creates with the seeded agent
- Send "hello" message
- Assistant response renders deterministically (mock provider returns its
  default content)
- Send button re-enabled after `done` event
"""

from __future__ import annotations

import pytest
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_chat_send_receives_mock_response(app_with_agent: SeededApp, page: Page) -> None:
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name  # "test-agent"

    # 1. Open #chat. Default area is chat, so this is the home page.
    page.goto(base_url)

    # WebSocket connects → status changes to "connected".
    expect(page.locator(".status")).to_have_text("connected", timeout=5000)

    # 2. Session auto-creates with the seeded agent. Agent badge updates.
    expect(page.locator(".session-agent-badge")).to_have_text(agent_name, timeout=5000)

    # 3-4. Type and send.
    page.locator('[data-testid="chat-input"]').fill("hello")
    page.locator('[data-testid="chat-send-btn"]').click()

    # 5. User message renders.
    user_msg = page.locator('[data-testid="message"].user')
    expect(user_msg).to_have_text("hello", timeout=5000)

    # 6. Assistant message renders with the mock provider's default response.
    #    Per leg 02, MockProvider.complete() with no config["response"] returns
    #    "Mock response from the mock provider."
    assistant_msg = page.locator('[data-testid="message"].assistant')
    expect(assistant_msg).to_have_text("Mock response from the mock provider.", timeout=10000)

    # 7. Send button re-enabled after `done` event (busy=false).
    expect(page.locator('[data-testid="chat-send-btn"]')).to_be_enabled()
