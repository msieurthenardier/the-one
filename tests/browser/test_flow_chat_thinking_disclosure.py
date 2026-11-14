"""M16 F10 L05 — Playwright browser flow: extended-thinking disclosure
(sortie 16 L02: the thinking is an item of the turn's work group).

Drives a real Chromium session through the full emit → codec-replay → render
path using the MockProvider thinking seam (no live Anthropic key). Proves:

  1. A turn that produces thinking + a tool call renders ONE work group
     (``turn-work``) that is COLLAPSED by default, holding the thinking and the
     tool call as items in stream order.
  2. It EXPANDS on toggle (native <details>: click the summary), revealing the
     reasoning text.
  3. After a page reload / chat reopen the group re-renders from history
     replay (the codec re-derives the thinking event from persisted
     ``msg.thinking``), still collapsed by default, thinking above the tool call.

DOM-shape assertions only — NO committed visual snapshots.

The mock agent is seeded with ``max_iterations=1`` so the static mock (which
returns the same tool_call every turn) yields exactly one assistant message
(empty content + thinking + tool_call) and one tool result — the core shape
from Leg 05 criterion #1 (a thinking event with NO preceding assistant bubble).
"""

from __future__ import annotations

import pytest
from browser import _chats
from browser.seeders import seed_mock_agent, seed_mock_provider
from playwright.sync_api import Page, expect

# The reasoning text the mock returns as a type="thinking" block. Distinctive
# so the expanded-body assertion is unambiguous.
_THINKING_TEXT = "Let me reason step by step about the request."


@pytest.mark.browser
def test_thinking_item_in_collapsed_work_group_expands_and_survives_reopen(
    app_clean: str, page: Page
) -> None:
    # ── Seed a mock provider that returns thinking + a tool call ──────────────
    # Empty content + a tool_call + a thinking block = criterion #1's core turn.
    provider_id = seed_mock_provider(
        app_clean,
        name="thinking-provider",
        config={
            "response": {
                "content": "",
                "thinking": [
                    {"type": "thinking", "thinking": _THINKING_TEXT, "signature": "sig-abc"}
                ],
                "tool_calls": [
                    {"id": "tc-1", "name": "shell", "arguments": {"command": "echo hi"}}
                ],
            }
        },
    )
    # max_iterations=1 bounds the static-mock tool loop to a single turn.
    agent_name = seed_mock_agent(
        app_clean,
        provider_id,
        name="thinking-agent",
        max_iterations=1,
    )

    # ── Bootstrap into chrome ─────────────────────────────────────────────────
    page.goto(app_clean)
    expect(_chats.welcome(page)).to_be_visible(timeout=8000)
    _chats.start_chat(page, agent_name)

    # ── Send a message ───────────────────────────────────────────────────────
    _chats.send_first(page, "please think then act")

    # ── (1) One work group renders, collapsed by default ─────────────────────
    expect(_chats.turn_groups(page)).to_have_count(1, timeout=10000)
    group = _chats.turn_group(page)
    expect(group).to_be_visible(timeout=10000)
    # The turn ends (no `working` line left); the group never opens on its own.
    expect(group).not_to_have_attribute("data-state", "working", timeout=10000)
    assert not _chats.turn_is_open(group), "the work group should be collapsed by default"
    # The thinking and the tool call are items of the same group, in stream order
    # (the live frames send the thinking before the tool call).
    kinds = group.locator("[data-kind]").evaluate_all("els => els.map(e => e.dataset.kind)")
    assert kinds[:2] == ["thinking", "tool"], kinds
    thinking = _chats.turn_items(group, "thinking")
    expect(thinking).to_be_hidden()

    # ── (2) It expands on toggle, revealing the reasoning text ───────────────
    _chats.open_turn(group)
    assert _chats.turn_is_open(group), "the work group should be open after a click"
    expect(thinking).to_be_visible()
    expect(thinking).to_contain_text(_THINKING_TEXT)
    # The opaque signature never reaches the client.
    assert "sig-abc" not in (group.text_content() or "")

    # ── (3) Survives a chat reopen (history replay) ──────────────────────────
    page.reload()
    _chats.expect_chat(page, agent_name, timeout=10000)

    expect(_chats.turn_groups(page)).to_have_count(1, timeout=10000)
    replayed = _chats.turn_group(page)
    expect(replayed).to_be_visible(timeout=10000)
    assert replayed.get_attribute("data-state") == "done"
    # Collapsed again on replay (a fresh group — no persisted open-state).
    assert not _chats.turn_is_open(replayed), "the replayed group should be collapsed"
    # Thinking above the tool call, as live; expanding reveals the reasoning text.
    replayed_kinds = replayed.locator("[data-kind]").evaluate_all(
        "els => els.map(e => e.dataset.kind)"
    )
    assert replayed_kinds[:2] == ["thinking", "tool"], replayed_kinds
    _chats.open_turn(replayed)
    expect(_chats.turn_items(replayed, "thinking")).to_contain_text(_THINKING_TEXT)
