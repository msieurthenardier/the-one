"""End-to-end browser tests for the F4 leg-04 streaming infrastructure.

Validates two contracts:

1. Streamed chunks land as one reply — when the mock provider is configured with
   ``stream_chunks``, the client receives ``assistant_chunk`` events; since sortie 16 their text
   is only a quiet preview in the turn's work group, and at ``done`` the whole concatenation
   becomes exactly one assistant bubble (the growing-bubble streaming is gone; the work-group
   shape itself is pinned in ``test_flow_chat_turn_work*.py``).

2. Persistence contract — after the streaming round closes, refreshing
   the page (rejoining the session via the session list) renders the
   accumulated assistant text from session history. Confirms that
   ``session.add_event`` is called server-side with the synthesized
   final assistant Message even though the WS broadcast for that
   Message is suppressed (chunks-only WS contract).
"""

from __future__ import annotations

import pytest
from browser import _chats
from browser.seeders import SeededApp, seed_mock_agent, seed_mock_provider
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_streamed_chunks_land_as_one_reply_bubble_at_done(app_clean: str, page: Page) -> None:
    """Streamed chunks end as exactly one assistant bubble holding their concatenation.

    Configures the mock provider with ``stream_chunks=["Hello, ", "world", "!"]``
    so the agent emits three ``assistant_chunk`` WS events plus a final
    metadata chunk. They are a preview only; at ``done`` the reply is one
    ``[data-testid="message"]`` assistant bubble and the turn has no work group (a plain reply).
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
    _chats.start_chat(page, agent_name)

    _chats.send_first(page, "hi")

    user_msg = _chats.messages(page, "user")
    expect(user_msg).to_have_text("hi", timeout=5000)

    # There is exactly one assistant bubble and its text is the concatenated content.
    assistant_msg = _chats.messages(page, "assistant")
    expect(assistant_msg).to_have_text("Hello, world!", timeout=10000)
    expect(assistant_msg).to_have_count(1)
    expect(_chats.turn_groups(page)).to_have_count(0)

    # Send button re-enabled after `done`.
    expect(page.locator('[data-testid="chat-send-btn"]')).to_be_enabled()


@pytest.mark.browser
def test_streaming_message_persists_to_history(app_clean: str, page: Page) -> None:
    """Reloading the page rejoins the session and renders the streamed text.

    This validates the persistence contract: although the final synthesized
    assistant Message is NOT broadcast over WS (the client already has the
    text from the chunks), it IS appended to session history server-side
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
    _chats.start_chat(page, agent_name)

    _chats.send_first(page, "ping")

    # Wait for the streaming round to land.
    assistant_msg = _chats.messages(page, "assistant")
    expect(assistant_msg).to_have_text("chunk-one chunk-two", timeout=10000)
    expect(page.locator('[data-testid="chat-send-btn"]')).to_be_enabled()

    # Reload — session id is in the URL hash; the client rejoins it on load
    # and replays history through `renderHistory`.
    page.reload()
    _chats.expect_chat(page, agent_name)
    # The assistant bubble re-renders from server-side history. If
    # `session.add_event` had NOT been called for the streamed message,
    # this expectation would fail (history would only contain the user msg).
    rejoined_assistant = _chats.messages(page, "assistant")
    expect(rejoined_assistant).to_have_text("chunk-one chunk-two", timeout=8000)
