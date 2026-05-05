"""End-to-end browser tests for the F4 leg-04 streaming infrastructure.

Validates two contracts:

1. Streaming chunk events arrive and accumulate into a single rendered
   assistant bubble — when the mock provider is configured with
   ``stream_chunks``, the client receives ``assistant_chunk`` events and
   the chat.js wire-up appends each delta to a single bubble. Final
   rendered text equals the concatenation of all chunks.

2. Persistence contract — after the streaming round closes, refreshing
   the page (rejoining the session via the session list) renders the
   accumulated assistant text from session history. Confirms that
   ``session.add_event`` is called server-side with the synthesized
   final assistant Message even though the WS broadcast for that
   Message is suppressed (chunks-only WS contract).
"""

from __future__ import annotations

import pytest
from browser.seeders import SeededApp, seed_mock_agent, seed_mock_provider
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_streaming_chunks_accumulate_in_single_bubble(app_clean: str, page: Page) -> None:
    """Streaming chunks render delta-by-delta into one assistant bubble.

    Configures the mock provider with ``stream_chunks=["Hello, ", "world", "!"]``
    so the agent emits three ``assistant_chunk`` WS events plus a final
    metadata chunk. The chat.js leg-04 wire-up (option B minimal rendering)
    accumulates them into a single ``[data-testid="message"].assistant``.
    """
    base_url = app_clean
    provider_id = seed_mock_provider(
        base_url,
        config={
            "stream_chunks": ["Hello, ", "world", "!"],
            "delay_ms": 0,
        },
    )
    agent_name = seed_mock_agent(base_url, provider_id)
    _ = SeededApp(base_url=base_url, provider_id=provider_id, agent_name=agent_name)

    page.goto(base_url)
    page.locator(".chat-welcome-item").filter(has_text=agent_name).click()
    expect(page.locator(".session-agent-badge")).to_have_text(agent_name, timeout=8000)

    page.locator('[data-testid="chat-input"]').fill("hi")
    page.locator('[data-testid="chat-send-btn"]').click()

    user_msg = page.locator('[data-testid="message"].user')
    expect(user_msg).to_have_text("hi", timeout=5000)

    # The assistant bubble accumulates all three chunks. There is exactly
    # one assistant bubble (chunks land in the same element) and its text
    # is the concatenated content.
    assistant_msg = page.locator('[data-testid="message"].assistant')
    expect(assistant_msg).to_have_text("Hello, world!", timeout=10000)
    expect(assistant_msg).to_have_count(1)

    # Send button re-enabled after `done`.
    expect(page.locator('[data-testid="chat-send-btn"]')).to_be_enabled()


@pytest.mark.browser
def test_streaming_message_persists_to_history(app_clean: str, page: Page) -> None:
    """Reloading the page rejoins the session and renders the streamed text.

    This validates the persistence contract: although the final synthesized
    assistant Message is NOT broadcast over WS (the client already has the
    text via the chunk stream), it IS appended to session history server-side
    via ``session.add_event``. So when the page reloads and rejoins the
    session, ``renderHistory`` walks the saved events and the assistant text
    appears.
    """
    base_url = app_clean
    provider_id = seed_mock_provider(
        base_url,
        config={
            "stream_chunks": ["chunk-one ", "chunk-two"],
            "delay_ms": 0,
        },
    )
    agent_name = seed_mock_agent(base_url, provider_id)

    page.goto(base_url)
    page.locator(".chat-welcome-item").filter(has_text=agent_name).click()
    expect(page.locator(".session-agent-badge")).to_have_text(agent_name, timeout=8000)

    page.locator('[data-testid="chat-input"]').fill("ping")
    page.locator('[data-testid="chat-send-btn"]').click()

    # Wait for the streaming round to land.
    assistant_msg = page.locator('[data-testid="message"].assistant')
    expect(assistant_msg).to_have_text("chunk-one chunk-two", timeout=10000)
    expect(page.locator('[data-testid="chat-send-btn"]')).to_be_enabled()

    # Reload — session id is in the URL hash; the client rejoins it on load
    # and replays history through `renderHistory`.
    page.reload()
    expect(page.locator(".session-agent-badge")).to_have_text(agent_name, timeout=8000)
    # The assistant bubble re-renders from server-side history. If
    # `session.add_event` had NOT been called for the streamed message,
    # this expectation would fail (history would only contain the user msg).
    rejoined_assistant = page.locator('[data-testid="message"].assistant')
    expect(rejoined_assistant).to_have_text("chunk-one chunk-two", timeout=8000)
