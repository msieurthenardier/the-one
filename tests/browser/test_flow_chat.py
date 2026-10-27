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
from browser import _chats
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_chat_send_receives_mock_response(app_with_agent: SeededApp, page: Page) -> None:
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name  # "test-agent"

    # 1. Open #chat. Default area is chat, so this is the home page.
    page.goto(base_url)

    # 2. Welcome canvas shows because no sessions exist yet (leg-05 removed
    #    auto-create-on-load). Pick the seeded agent to bootstrap a session.
    _chats.start_chat(page, agent_name)

    # 3-4. Type and send.
    _chats.send_first(page, "hello")

    # 5. User message renders.
    user_msg = _chats.messages(page, "user")
    expect(user_msg).to_have_text("hello", timeout=5000)

    # 6. Assistant message renders with the mock provider's default response.
    #    Per leg 02, MockProvider.complete() with no config["response"] returns
    #    "Mock response from the mock provider."
    assistant_msg = _chats.messages(page, "assistant")
    expect(assistant_msg).to_have_text("Mock response from the mock provider.", timeout=10000)

    # 7. Send button re-enabled after `done` event (busy=false).
    expect(page.locator('[data-testid="chat-send-btn"]')).to_be_enabled()


@pytest.mark.browser
def test_chat_message_log_has_live_region(app_with_agent: SeededApp, page: Page) -> None:
    """A11y leg 02 regression: the chat message log container is exposed as
    an ARIA live region so screen readers announce assistant replies.

    Acceptance criteria from missions/06-maintenance/.../02-chat-a11y-baseline.md:
    - <div class="messages"> has role="log" + aria-live="polite"
    - the chat input has an accessible name ("Message"; since M25 F4 L5 from
      a visually hidden <label for>, not aria-label)
    """
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name

    page.goto(base_url)
    _chats.start_chat(page, agent_name)

    # M25 F4 L4b: a pending chat shows the new-chat state; its log is in the
    # tree (zero height until it holds a notice), so the live region exists
    # before anything is announced. It shows once the first send lands.
    log = page.locator("[role='log']")
    expect(log).to_be_attached()
    assert log.get_attribute("aria-live") == "polite"
    assert log.get_attribute("aria-relevant") == "additions"
    _chats.send_first(page, "hello")
    expect(log).to_be_visible()

    chat_input = page.locator('[data-testid="chat-input"]')
    expect(chat_input).to_have_accessible_name("Message")
    assert chat_input.get_attribute("aria-label") is None
