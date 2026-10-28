"""Browser tests for M16 F09 leg 02 — send-while-thinking CLIENT-HOLD queue.

The send-while-thinking queue (F07 DD4; many messages, in order, capped at 10, since M31 F6
L10a) uses a **client-hold** model: a message queued while a turn is running is HELD locally
(not sent to the backend) and shown as a **pinned chip** above the composer. On the running
turn's ``done`` it is sent via the normal send path; a cancel (×) on the chip
discards it (nothing was ever sent). This fixes three HAT findings:

- **F09-04 (pin)**: the queued chip renders in a pinned region above the
  composer, OUTSIDE the scrolling message list, so it can't scroll away.
- **F09-04 (cancel)**: the chip's cancel (×) discards the held message — and
  because nothing was sent to the backend, no turn runs for it.
- **F09-02 (render)**: when the running turn finishes, the held message is sent
  and appears as a normal user bubble, after that turn's response and before the
  queued turn's response, with the thinking/Send-disabled state carrying over.
- **F09-03 (Stop)**: clicking Stop while a message is queued cancels the running
  turn (backend ``_session_inflight`` set-cancel) and discards the held message.

Assertions are DOM/structure based (bubble text, DOM order, element ancestry);
no committed visual snapshots (snapshot baselines are gitignored / local-only).
"""

from __future__ import annotations

import pytest
from browser import _chats
from browser.seeders import seed_mock_agent, seed_mock_provider
from playwright.sync_api import Page, expect


def _message_order(page: Page) -> list[dict[str, str]]:
    """Return the live transcript's message bubbles in DOM order.

    Each entry is ``{"cls": <className>, "text": <textContent>}``. The thinking
    indicator (``data-testid="thinking-indicator"``) and the queued chip
    (``data-testid="pending-queued"``) are excluded — only real
    user/assistant/tool/system bubbles carry ``data-testid="message"``.
    """
    return page.evaluate(
        """() => Array.from(document.querySelectorAll('[data-testid="message"]'))
            .map(e => ({ cls: e.className, text: e.textContent }))"""
    )


def _chip_placement(page: Page) -> dict[str, bool]:
    """Report where the queued chip sits in the DOM relative to the scroll list."""
    return page.evaluate(
        """() => {
            const chip = document.querySelector('[data-testid="pending-queued"]');
            const region = document.querySelector('[data-testid="pending-queued-region"]');
            const messages = document.querySelector('.area-chat .messages');
            return {
                found: !!chip,
                inRegion: !!(chip && region && region.contains(chip)),
                inMessages: !!(chip && messages && messages.contains(chip)),
            };
        }"""
    )


def _start_slow_turn(page: Page, base_url: str, chunks: list[str], delay_ms: int) -> str:
    """Seed a slow streaming mock turn, open the chat, and return the agent name."""
    provider_id = seed_mock_provider(
        base_url, config={"stream_chunks": chunks, "delay_ms": delay_ms}
    )
    agent_name = seed_mock_agent(base_url, provider_id)
    page.goto(base_url)
    _chats.start_chat(page, agent_name)
    return agent_name


@pytest.mark.browser
def test_queued_chip_is_pinned_outside_scroll_list(app_clean: str, page: Page) -> None:
    """F09-04 (pin): the queued chip renders in the pinned region above the
    composer, NOT inside the scrolling message list, and stays put when the
    message list scrolls."""
    base_url = app_clean
    _start_slow_turn(page, base_url, ["one ", "two ", "three"], 400)

    # Turn 1: send and wait until it is streaming (proves in-flight).
    _chats.send_first(page, "first")
    expect(_chats.messages(page, "assistant").first).to_contain_text("one", timeout=8000)

    # Queue a message via Enter (the Send button is disabled during a turn).
    page.locator('[data-testid="chat-input"]').fill("held message")
    page.locator('[data-testid="chat-input"]').press("Enter")

    chip = page.locator('[data-testid="pending-queued"]')
    expect(chip).to_be_visible(timeout=3000)
    expect(chip).to_contain_text("held message")

    # The chip is in the pinned region and NOT inside the scrolling .messages.
    placement = _chip_placement(page)
    assert placement == {"found": True, "inRegion": True, "inMessages": False}, placement

    # It does not move when the message list is scrolled (it is outside it).
    box_before = chip.bounding_box()
    page.evaluate(
        "() => { const m = document.querySelector('.area-chat .messages');"
        " if (m) m.scrollTop = m.scrollHeight; }"
    )
    page.wait_for_timeout(100)
    box_after = chip.bounding_box()
    assert box_before is not None and box_after is not None
    assert abs(box_before["y"] - box_after["y"]) < 1.0, (box_before, box_after)


@pytest.mark.browser
def test_cancel_chip_discards_held_message_no_turn_runs(app_clean: str, page: Page) -> None:
    """F09-04 (cancel): activating the chip's cancel (×) removes the chip and
    discards the held message — and because nothing was sent, no turn runs for
    it (no extra assistant response, no new user bubble)."""
    base_url = app_clean
    _start_slow_turn(page, base_url, ["one ", "two ", "three"], 400)

    _chats.send_first(page, "first")
    expect(_chats.messages(page, "assistant").first).to_contain_text("one", timeout=8000)

    # Queue, then cancel via the × button (keyboard-accessible native button).
    page.locator('[data-testid="chat-input"]').fill("discard me")
    page.locator('[data-testid="chat-input"]').press("Enter")
    expect(page.locator('[data-testid="pending-queued"]')).to_be_visible(timeout=3000)
    page.locator('[data-testid="pending-queued-cancel"]').click()

    # Chip gone immediately.
    expect(page.locator('[data-testid="pending-queued"]')).to_have_count(0)

    # Let turn 1 finish and settle. The discarded message must NOT run: no
    # second turn means exactly one user bubble and one assistant bubble.
    expect(page.locator('[data-testid="chat-send-btn"]')).to_be_enabled(timeout=10000)
    page.wait_for_timeout(1500)
    expect(_chats.messages(page, "user")).to_have_count(1)
    expect(_chats.messages(page, "user")).to_have_text("first")
    expect(_chats.messages(page, "assistant")).to_have_count(1)


@pytest.mark.browser
def test_cancelling_the_chip_by_keyboard_focuses_the_composer(app_clean: str, page: Page) -> None:
    """WCAG 2.4.3 and 4.1.3: the cancel button held focus, so the composer input takes it
    after the chip goes; the live region stays rendered (never hidden) while empty."""
    _start_slow_turn(page, app_clean, ["one ", "two ", "three"], 400)
    _chats.send_first(page, "first")
    expect(_chats.messages(page, "assistant").first).to_contain_text("one", timeout=8000)
    region = page.locator('[data-testid="pending-queued-region"]')
    expect(region).to_have_attribute("aria-live", "polite")
    assert region.evaluate("(e) => e.hasAttribute('hidden')") is False
    page.locator('[data-testid="chat-input"]').fill("discard me")
    page.locator('[data-testid="chat-input"]').press("Enter")
    cancel = page.locator('[data-testid="pending-queued-cancel"]')
    expect(cancel).to_be_visible(timeout=3000)
    cancel.focus()
    page.keyboard.press("Enter")
    expect(page.locator('[data-testid="pending-queued"]')).to_have_count(0)
    expect(page.locator('[data-testid="chat-input"]')).to_be_focused()
    assert region.evaluate("(e) => e.hasAttribute('hidden')") is False


@pytest.mark.browser
def test_held_message_sent_as_user_bubble_on_done(app_clean: str, page: Page) -> None:
    """F09-02 (render): on the running turn's ``done`` the held message is sent
    via the normal path — it appears as a user bubble after that turn's response,
    and the session stays in-flight for the queued turn."""
    base_url = app_clean
    # Both turns share this slow config (the mock provider is stateless), so the
    # queued turn is also slow enough to observe the carry-over in-flight state.
    _start_slow_turn(page, base_url, ["resp-one ", "resp-two ", "resp-DONE"], 400)

    _chats.send_first(page, "first")
    assistant = _chats.messages(page, "assistant")
    expect(assistant.first).to_contain_text("resp-one", timeout=8000)

    # Hold "second" while turn 1 runs (Enter — Send is disabled during a turn).
    page.locator('[data-testid="chat-input"]').fill("second")
    page.locator('[data-testid="chat-input"]').press("Enter")
    chip = page.locator('[data-testid="pending-queued"]')
    expect(chip).to_be_visible(timeout=3000)
    expect(chip).to_contain_text("second")

    # When turn 1 finishes, the held message is sent and renders as a real user
    # bubble (the core of F09-02). Before the fix this never appeared live.
    user_bubbles = _chats.messages(page, "user")
    expect(user_bubbles).to_have_count(2, timeout=10000)
    expect(user_bubbles.nth(1)).to_have_text("second")

    # The chip is gone (the held message is now in progress).
    expect(page.locator('[data-testid="pending-queued"]')).to_have_count(0)

    # Ordering: the "second" user bubble sits AFTER turn 1's assistant response.
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
    # after the dequeue. (Send-disabled is the durable carry-over signal; the
    # thinking indicator is replaced by the streaming bubble once turn 2's first
    # chunk arrives, same as a normal turn.)
    expect(page.locator('[data-testid="chat-send-btn"]')).to_be_disabled()

    # The queued turn runs as a real turn: its own assistant response appears,
    # then the UI returns to idle.
    expect(_chats.messages(page, "assistant")).to_have_count(2, timeout=10000)
    expect(page.locator('[data-testid="chat-send-btn"]')).to_be_enabled(timeout=10000)


@pytest.mark.browser
def test_stop_during_queued_state_cancels_running_turn(app_clean: str, page: Page) -> None:
    """F09-03: clicking Stop while a message is queued cancels the RUNNING turn
    (it does not run to completion) and discards the held message."""
    base_url = app_clean
    # The running turn streams a distinctive final sentinel chunk only at the
    # end. If Stop cancels the running turn (correct), that sentinel never
    # renders; if the running turn continued (the bug), the sentinel would show.
    _start_slow_turn(page, base_url, ["alpha ", "beta ", "gamma-FINAL"], 500)

    _chats.send_first(page, "running")
    assistant = _chats.messages(page, "assistant")
    expect(assistant.first).to_contain_text("alpha", timeout=8000)
    expect(assistant.first).not_to_contain_text("gamma-FINAL")

    # Hold a second message while turn 1 runs.
    page.locator('[data-testid="chat-input"]').fill("queued")
    page.locator('[data-testid="chat-input"]').press("Enter")
    expect(page.locator('[data-testid="pending-queued"]')).to_be_visible(timeout=3000)

    # Stop: must cancel the running turn.
    page.locator('[data-testid="chat-stop-btn"]').click()

    # Wait well past the running turn's natural completion (3 chunks x 500ms ≈
    # 1s). If it had continued (the bug), the sentinel would have rendered.
    page.wait_for_timeout(2500)
    expect(_chats.messages(page, "assistant")).not_to_contain_text("gamma-FINAL")

    # The held message was discarded ("stop = stop everything"): no second user
    # bubble, no lingering chip.
    expect(_chats.messages(page, "user")).to_have_count(1)
    expect(page.locator('[data-testid="pending-queued"]')).to_have_count(0)

    # The UI returns to idle (Send re-enabled, no thinking indicator).
    expect(page.locator('[data-testid="chat-send-btn"]')).to_be_enabled(timeout=8000)
    expect(page.locator('[data-testid="thinking-indicator"]')).to_have_count(0)


# ── M31 F6 L10a: several held messages ────────────────────────────────────────

CHIPS = '[data-testid="pending-queued"]'
CANCELS = '[data-testid="pending-queued-cancel"]'
INPUT = '[data-testid="chat-input"]'


def _hold(page: Page, text: str) -> None:
    page.locator(INPUT).fill(text)
    page.locator(INPUT).press("Enter")


def _running_turn(page: Page, base_url: str, delay_ms: int = 700) -> None:
    _start_slow_turn(page, base_url, ["one ", "two ", "three"], delay_ms)
    _chats.send_first(page, "first")
    expect(_chats.messages(page, "assistant").first).to_contain_text("one", timeout=8000)


@pytest.mark.browser
def test_several_sends_are_held_in_order_then_drain_one_per_turn(
    app_clean: str, page: Page
) -> None:
    _running_turn(page, app_clean, 200)
    for text in ("alpha", "bravo", "charlie"):
        _hold(page, text)
    chips = page.locator(CHIPS)
    expect(chips).to_have_count(3, timeout=3000)
    expect(chips.nth(0)).to_contain_text("alpha")
    expect(chips.nth(1)).to_contain_text("bravo")
    expect(chips.nth(2)).to_contain_text("charlie")
    expect(page.locator(INPUT)).to_have_value("")
    # Nothing was sent: only "first" is a user bubble while the first turn runs.
    expect(_chats.messages(page, "user")).to_have_count(1)
    # The live status line counts them; each cancel is named by its place.
    expect(page.locator('[data-testid="pending-queued-status"]')).to_have_text("3 messages queued")
    names = [page.locator(CANCELS).nth(i).get_attribute("aria-label") for i in range(3)]
    assert names == [
        "Cancel queued message 1 of 3",
        "Cancel queued message 2 of 3",
        "Cancel queued message 3 of 3",
    ]
    # One per turn end, first first: the bubbles arrive in send order, the chips drain.
    expect(_chats.messages(page, "user")).to_have_text(
        ["first", "alpha", "bravo", "charlie"], timeout=20000
    )
    expect(chips).to_have_count(0)
    expect(_chats.messages(page, "assistant")).to_have_count(4, timeout=20000)
    expect(page.locator('[data-testid="chat-send-btn"]')).to_be_enabled(timeout=10000)


@pytest.mark.browser
def test_removing_the_middle_then_the_last_chip_moves_focus_and_renames(
    app_clean: str, page: Page
) -> None:
    _running_turn(page, app_clean, 1500)
    for text in ("alpha", "bravo", "charlie"):
        _hold(page, text)
    chips = page.locator(CHIPS)
    expect(chips).to_have_count(3, timeout=3000)
    page.locator(CANCELS).nth(1).focus()
    page.keyboard.press("Enter")
    expect(chips).to_have_count(2)
    expect(chips.nth(0)).to_contain_text("alpha")
    expect(chips.nth(1)).to_contain_text("charlie")
    # Focus went to the next chip (now at the removed index); names are recomputed.
    expect(page.locator(CANCELS).nth(1)).to_be_focused()
    last = page.locator(CANCELS).nth(1)
    assert last.get_attribute("aria-label") == "Cancel queued message 2 of 2"
    expect(page.locator('[data-testid="pending-queued-status"]')).to_have_text("2 messages queued")
    # Removing the last: focus goes to the previous chip.
    page.keyboard.press("Enter")
    expect(chips).to_have_count(1)
    expect(page.locator(CANCELS).first).to_be_focused()
    assert page.locator(CANCELS).first.get_attribute("aria-label") == "Cancel queued message"
    expect(page.locator('[data-testid="pending-queued-status"]')).to_have_text("1 message queued")
    # Removing the only one: the message box.
    page.keyboard.press("Enter")
    expect(chips).to_have_count(0)
    expect(page.locator(INPUT)).to_be_focused()


@pytest.mark.browser
def test_the_queue_is_capped_at_ten_and_the_eleventh_stays_in_the_box(
    app_clean: str, page: Page
) -> None:
    _running_turn(page, app_clean, 2000)
    for i in range(10):
        _hold(page, f"m{i}")
    expect(page.locator(CHIPS)).to_have_count(10, timeout=5000)
    _hold(page, "eleven")
    expect(page.locator(CHIPS)).to_have_count(10)
    expect(page.locator(INPUT)).to_have_value("eleven")
    expect(page.locator('[data-testid="pending-queued-full"]')).to_have_text("Queue is full (10)")


@pytest.mark.browser
def test_chips_are_not_announced_individually(app_clean: str, page: Page) -> None:
    _running_turn(page, app_clean, 1500)
    _hold(page, "alpha")
    expect(page.locator(CHIPS)).to_have_count(1, timeout=3000)
    assert page.locator(CHIPS).first.get_attribute("aria-live") == "off"
