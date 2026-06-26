"""Browser tests for M16 F09 leg 02 — send-while-thinking one-slot queue.

Covers two send-while-thinking (F07 DD4 one-slot queue) defects:

- **F09-02** (frontend, chat.js ``done`` handler): a message queued while a
  turn is running must render as a *real* user bubble in the live transcript
  once the running turn finishes — positioned AFTER the finishing turn's
  response and BEFORE the queued turn's response — and the thinking
  indicator / Send-disabled state must carry into the queued turn. Before the
  fix the queued message only showed a "(queued)" indicator and then vanished
  from the live transcript (it was persisted, so a reload showed it, but the
  live session never rendered it).

- **F09-03** (backend, app.py ``_session_inflight`` set): clicking Stop while a
  message is queued must cancel the **running** turn (and discard the queued
  message) — "stop = stop everything". Before the fix the per-session in-flight
  map held only the queued (lock-blocked) task, so Stop cancelled the queued
  task and let the running turn continue to completion.

Assertions are DOM/structure based (message bubble text + DOM order); no
committed visual snapshots (snapshot baselines are gitignored / local-only).
"""

from __future__ import annotations

import pytest
from browser.seeders import seed_mock_agent, seed_mock_provider
from playwright.sync_api import Page, expect


def _message_order(page: Page) -> list[dict[str, str]]:
    """Return the live transcript's message bubbles in DOM order.

    Each entry is ``{"cls": <className>, "text": <textContent>}``. The
    thinking indicator carries ``data-testid="thinking-indicator"`` (not
    ``"message"``) so it is excluded — only real user/assistant/tool/system
    bubbles are returned.
    """
    return page.evaluate(
        """() => Array.from(document.querySelectorAll('[data-testid="message"]'))
            .map(e => ({ cls: e.className, text: e.textContent }))"""
    )


@pytest.mark.browser
def test_queued_message_renders_as_user_bubble_on_done(app_clean: str, page: Page) -> None:
    """F09-02: a message queued during a slow turn renders as a real user
    bubble once the running turn finishes, after that turn's response, and the
    session stays in-flight for the queued turn."""
    base_url = app_clean
    # Slow streaming turns so there is a window to queue during turn 1 and to
    # observe the carry-over thinking state at the start of turn 2. Both turns
    # share this config (the mock provider is stateless), so turn 2 is also slow.
    provider_id = seed_mock_provider(
        base_url,
        config={
            "stream_chunks": ["resp-one ", "resp-two ", "resp-DONE"],
            "delay_ms": 400,
        },
    )
    agent_name = seed_mock_agent(base_url, provider_id)

    page.goto(base_url)
    page.locator(".chat-welcome-item").filter(has_text=agent_name).click()
    expect(page.locator(".session-agent-badge")).to_have_text(agent_name, timeout=8000)

    # Turn 1: send "first" and wait until it is streaming (proves in-flight).
    page.locator('[data-testid="chat-input"]').fill("first")
    page.locator('[data-testid="chat-send-btn"]').click()
    assistant = page.locator('[data-testid="message"].assistant')
    expect(assistant.first).to_contain_text("resp-one", timeout=8000)

    # Queue "second" while turn 1 is still running. The Send button is disabled
    # during an in-flight turn, so queueing happens via Enter on the input
    # (which stays enabled). The one-slot queue shows a "(queued)" indicator and
    # sends the message to the backend immediately.
    page.locator('[data-testid="chat-input"]').fill("second")
    page.locator('[data-testid="chat-input"]').press("Enter")
    pending = page.locator(".pending-queued")
    expect(pending).to_be_visible(timeout=3000)
    expect(pending).to_contain_text("second")
    expect(pending).to_contain_text("(queued)")

    # When turn 1 finishes, the queued message must render as a real user
    # bubble. This is the core of F09-02 — before the fix this bubble never
    # appeared in the live transcript.
    user_bubbles = page.locator('[data-testid="message"].user')
    expect(user_bubbles).to_have_count(2, timeout=10000)
    expect(user_bubbles.nth(1)).to_have_text("second")

    # The "(queued)" indicator is gone (the queued message is now in progress).
    expect(page.locator(".pending-queued")).to_have_count(0)

    # Ordering: the dequeued "second" user bubble sits AFTER turn 1's assistant
    # response. (Turn 2's response, if any yet, sits after "second".)
    order = _message_order(page)
    first_assistant_idx = next(
        i for i, m in enumerate(order) if "assistant" in m["cls"] and "resp-DONE" in m["text"]
    )
    second_user_idx = next(
        i for i, m in enumerate(order) if "user" in m["cls"] and m["text"] == "second"
    )
    assert second_user_idx > first_assistant_idx, (
        f"queued bubble must follow turn-1 response; order={order}"
    )

    # The session stays in-flight for the queued turn: Send is disabled right
    # after the dequeue (the queued turn is now running). The thinking indicator
    # is shown only until turn 2's first chunk arrives, which replaces it with
    # the streaming bubble — same as a normal turn — so Send-disabled is the
    # durable carry-over signal.
    expect(page.locator('[data-testid="chat-send-btn"]')).to_be_disabled()

    # The queued turn runs as a real turn: it produces its own assistant
    # response (a second assistant bubble) and then the UI returns to idle.
    expect(page.locator('[data-testid="message"].assistant')).to_have_count(2, timeout=10000)
    expect(page.locator('[data-testid="chat-send-btn"]')).to_be_enabled(timeout=10000)


@pytest.mark.browser
def test_stop_during_queued_state_cancels_running_turn(app_clean: str, page: Page) -> None:
    """F09-03: clicking Stop while a message is queued cancels the RUNNING turn
    (it does not run to completion) and discards the queued message."""
    base_url = app_clean
    # The running turn streams a distinctive final sentinel chunk only at the
    # end. If Stop cancels the running turn (correct), that sentinel never
    # renders; if Stop only cancels the queued task (the bug), the running turn
    # completes and the sentinel appears.
    provider_id = seed_mock_provider(
        base_url,
        config={
            "stream_chunks": ["alpha ", "beta ", "gamma-FINAL"],
            "delay_ms": 500,
        },
    )
    agent_name = seed_mock_agent(base_url, provider_id)

    page.goto(base_url)
    page.locator(".chat-welcome-item").filter(has_text=agent_name).click()
    expect(page.locator(".session-agent-badge")).to_have_text(agent_name, timeout=8000)

    # Turn 1: send and wait for the first chunk (running, not yet finished).
    page.locator('[data-testid="chat-input"]').fill("running")
    page.locator('[data-testid="chat-send-btn"]').click()
    assistant = page.locator('[data-testid="message"].assistant')
    expect(assistant.first).to_contain_text("alpha", timeout=8000)
    # Guard: the final sentinel has not streamed yet at this point.
    expect(assistant.first).not_to_contain_text("gamma-FINAL")

    # Queue a second message while turn 1 runs (Enter — the Send button is
    # disabled during an in-flight turn).
    page.locator('[data-testid="chat-input"]').fill("queued")
    page.locator('[data-testid="chat-input"]').press("Enter")
    expect(page.locator(".pending-queued")).to_be_visible(timeout=3000)

    # Stop: must cancel the running turn.
    page.locator('[data-testid="chat-stop-btn"]').click()

    # Wait well past the running turn's natural completion time (3 chunks x
    # 500ms ≈ 1s). If the running turn had continued (the bug), the final
    # sentinel would have rendered by now.
    page.wait_for_timeout(2500)
    expect(page.locator('[data-testid="message"].assistant')).not_to_contain_text("gamma-FINAL")

    # The queued message was discarded ("stop = stop everything"): no second
    # user bubble, no lingering "(queued)" indicator.
    expect(page.locator('[data-testid="message"].user')).to_have_count(1)
    expect(page.locator(".pending-queued")).to_have_count(0)

    # The UI returns to idle (Send re-enabled, no thinking indicator).
    expect(page.locator('[data-testid="chat-send-btn"]')).to_be_enabled(timeout=8000)
    expect(page.locator('[data-testid="thinking-indicator"]')).to_have_count(0)
