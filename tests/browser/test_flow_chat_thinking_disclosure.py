"""M16 F10 L05 — Playwright browser flow: extended-thinking disclosure.

Drives a real Chromium session through the full emit → codec-replay → render
path using the MockProvider thinking seam (no live Anthropic key). Proves:

  1. A turn that produces thinking + a tool call renders a
     ``.thinking-disclosure`` <details> that is COLLAPSED by default.
  2. It EXPANDS on toggle (native <details>: click the summary), revealing the
     reasoning text.
  3. The tool trace (``.trace-shell``) ALSO renders — the two disclosures
     coexist (distinct identifiers, no shared toggle).
  4. After a page reload / chat reopen the disclosure re-renders from history
     replay (the codec re-derives the thinking event from persisted
     ``msg.thinking``), still collapsed by default.

DOM-shape assertions only — NO committed visual snapshots.

The mock agent is seeded with ``max_iterations=1`` so the static mock (which
returns the same tool_call every turn) yields exactly one assistant message
(empty content + thinking + tool_call) and one tool result — the core shape
from Leg 05 criterion #1 (a thinking event with NO preceding assistant bubble).
"""

from __future__ import annotations

import pytest
from browser.seeders import seed_mock_agent, seed_mock_provider
from playwright.sync_api import Page, expect

# The reasoning text the mock returns as a type="thinking" block. Distinctive
# so the expanded-body assertion is unambiguous.
_THINKING_TEXT = "Let me reason step by step about the request."


@pytest.mark.browser
def test_thinking_disclosure_collapsed_expands_coexists_and_survives_reopen(
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
    expect(page.locator('[data-testid="chat-welcome"]')).to_be_visible(timeout=8000)
    agent_item = page.locator(".chat-welcome-item").filter(has_text=agent_name)
    expect(agent_item).to_be_visible(timeout=8000)
    agent_item.click()
    expect(page.locator(".session-agent-badge")).to_have_text(agent_name, timeout=8000)

    # ── Send a message ───────────────────────────────────────────────────────
    page.locator('[data-testid="chat-input"]').fill("please think then act")
    page.locator('[data-testid="chat-send-btn"]').click()

    # ── (1) The thinking disclosure renders, collapsed by default ────────────
    disclosure = page.locator('[data-testid="thinking-disclosure"]')
    expect(disclosure).to_be_visible(timeout=10000)
    # <details> is collapsed by default: the `open` property is False and the
    # body content is not visible.
    assert disclosure.evaluate("el => el.open") is False, (
        "thinking disclosure should be collapsed (not open) by default"
    )
    body = disclosure.locator(".thinking-body")
    expect(body).to_be_hidden()

    # ── (3) The tool trace coexists (distinct disclosure) ────────────────────
    trace = page.locator(".trace-shell")
    expect(trace.first).to_be_visible(timeout=10000)
    # The two are distinct DOM subtrees — the thinking body is NOT inside the
    # trace shell (it is its own disclosure, not a tool-trace child).
    assert page.locator(".trace-shell .thinking-disclosure").count() == 0, (
        "thinking disclosure must not be nested inside the tool-trace shell"
    )

    # ── (2) It expands on toggle, revealing the reasoning text ───────────────
    disclosure.locator("summary.thinking-toggle").click()
    assert disclosure.evaluate("el => el.open") is True, (
        "thinking disclosure should be open after clicking its summary"
    )
    expect(body).to_be_visible()
    expect(body).to_contain_text(_THINKING_TEXT)
    # The opaque signature never reaches the client.
    assert "sig-abc" not in (disclosure.text_content() or "")

    # ── (4) Survives a chat reopen (history replay) ──────────────────────────
    page.reload()
    expect(page.locator(".session-agent-badge")).to_have_text(agent_name, timeout=10000)

    replayed = page.locator('[data-testid="thinking-disclosure"]')
    expect(replayed).to_be_visible(timeout=10000)
    # Collapsed again on replay (renderThinking builds a fresh collapsed
    # <details> — no persisted open-state).
    assert replayed.evaluate("el => el.open") is False, (
        "replayed thinking disclosure should be collapsed by default"
    )
    # The tool trace also replays (codec emits thinking before the tool_call).
    expect(page.locator(".trace-shell").first).to_be_visible(timeout=10000)
    # Expanding the replayed disclosure still reveals the reasoning text.
    replayed.locator("summary.thinking-toggle").click()
    expect(replayed.locator(".thinking-body")).to_contain_text(_THINKING_TEXT)
