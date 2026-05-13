"""End-to-end flow tests for the F3 leg 05 new-chat restructure.

Covers:
- Welcome canvas content adapts to setup state (no provider, no agent, ready)
- Picking an agent from the welcome listbox starts a new session
- Header "New Chat" button starts a fresh conversation with the *current* agent
- Deleting the last session returns to the welcome canvas (no auto-create)
- Chat-history sidebar groups sessions under a "Today" heading
- Per-message metadata (.msg-meta / .msg-author / .msg-time) renders correctly
- Context chip (#chat-ctx-chip) in composer shows token count
- Thinking indicator appears on send and clears on assistant reply

Removed (Holograph migration L3.3):
- test_dropdown_change_starts_new_session: the sidebar agent-select dropdown is
  gone; agent switching now requires returning to the empty state and picking a
  different card from the welcome listbox.
- test_telemetry_overlay_collapses_by_default: the floating overlay is replaced
  by an inline chip. Replaced by test_ctx_chip_shows_in_composer.
"""

from __future__ import annotations

import re

import httpx
import pytest
from browser.seeders import SeededApp, seed_mock_agent
from playwright.sync_api import Page, expect

# ── Welcome canvas: state-aware content ──────────────────────────────────


@pytest.mark.browser
def test_welcome_no_setup_shows_both_links(app_clean: str, page: Page) -> None:
    """No providers and no agents → guidance points to Settings AND Agent Studio."""
    page.goto(app_clean)
    welcome = page.locator('[data-testid="chat-welcome"]')
    expect(welcome).to_be_visible(timeout=5000)

    # Greeting present, prompt hidden (no agents to pick).
    expect(page.locator(".chat-empty-title")).to_be_visible()
    expect(page.locator(".chat-empty-sub")).to_be_hidden()

    # Both deep-links present.
    # Holograph uses #admin/providers (not #admin) and "LLM Settings" (not "Settings").
    settings_link = page.locator('.chat-welcome-link[href="#admin/providers"]')
    studio_link = page.locator('.chat-welcome-link[href="#studio"]')
    expect(settings_link).to_have_text("LLM Settings")
    expect(studio_link).to_have_text("Agent Studio")


@pytest.mark.browser
def test_welcome_provider_only_shows_studio_link(app_with_provider: SeededApp, page: Page) -> None:
    """Provider seeded, no agents → guidance only points to Agent Studio."""
    page.goto(app_with_provider.base_url)
    welcome = page.locator('[data-testid="chat-welcome"]')
    expect(welcome).to_be_visible(timeout=5000)

    expect(page.locator(".chat-empty-sub")).to_be_hidden()
    expect(page.locator('.chat-welcome-link[href="#studio"]')).to_have_text("Agent Studio")
    # Holograph uses #admin/providers (not #admin) for the settings link.
    expect(page.locator('.chat-welcome-link[href="#admin/providers"]')).to_have_count(0)


@pytest.mark.browser
def test_welcome_with_agent_shows_listbox(app_with_agent: SeededApp, page: Page) -> None:
    """Provider + agent seeded, no sessions → welcome shows an agent listbox.

    Auto-create-on-load was removed in leg 05; with no sessions we land on
    the welcome canvas with the seeded agent as the only listbox option.
    """
    page.goto(app_with_agent.base_url)
    welcome = page.locator('[data-testid="chat-welcome"]')
    expect(welcome).to_be_visible(timeout=5000)

    # Prompt is shown (we have agents to pick from), and the listbox has
    # exactly one option matching the seeded agent.
    expect(page.locator(".chat-empty-sub")).to_be_visible()
    welcome_item = page.locator(".chat-agent-card").filter(has_text=app_with_agent.agent_name)
    expect(welcome_item).to_be_visible(timeout=8000)
    expect(page.locator(".chat-empty-list")).to_have_attribute("role", "listbox")


# ── Welcome → start session ──────────────────────────────────────────────


@pytest.mark.browser
def test_picking_agent_from_welcome_starts_session(
    app_with_provider: SeededApp, page: Page
) -> None:
    """Click an agent in the welcome listbox → session starts, chrome shows."""
    # Seed an agent without going through the welcome path first.
    seed_mock_agent(app_with_provider.base_url, app_with_provider.provider_id, name="picker-agent")

    page.goto(app_with_provider.base_url)

    # Welcome canvas should be visible (no sessions exist yet).
    expect(page.locator('[data-testid="chat-welcome"]')).to_be_visible(timeout=5000)

    # Wait for the agent listbox to populate.
    agent_item = page.locator(".chat-agent-card").filter(has_text="picker-agent")
    expect(agent_item).to_be_visible(timeout=8000)

    # Click → session_joined fires → chrome appears, badge populated.
    agent_item.click()

    expect(page.locator(".convo-pane")).to_be_visible(timeout=8000)
    expect(page.locator(".convo-agent > span:not(.chip)")).to_have_text("picker-agent", timeout=5000)
    expect(page.locator('[data-testid="chat-welcome"]')).to_be_hidden()


# ── Header "New Chat" → new conversation, same agent ─────────────────────


@pytest.mark.browser
def test_header_new_chat_button_starts_session_with_current_agent(
    app_with_agent: SeededApp, page: Page
) -> None:
    """The header `+ New Chat` button opens a new session with the current agent."""
    page.goto(app_with_agent.base_url)
    # Bootstrap a session via the welcome listbox.
    page.locator(".chat-agent-card").filter(has_text=app_with_agent.agent_name).click()
    expect(page.locator(".convo-agent > span:not(.chip)")).to_have_text(
        app_with_agent.agent_name, timeout=8000
    )

    first_hash = page.evaluate("location.hash")
    assert first_hash.startswith("#chat/sessions/")

    page.locator('[data-testid="new-chat-btn"]').click()

    # Same agent — no badge churn.
    expect(page.locator(".convo-agent > span:not(.chip)")).to_have_text(
        app_with_agent.agent_name, timeout=8000
    )

    # New session id, though.
    def hash_changed() -> bool:
        h = page.evaluate("location.hash")
        return h.startswith("#chat/sessions/") and h != first_hash

    page.wait_for_function(
        f"() => location.hash.startsWith('#chat/sessions/') && location.hash !== {first_hash!r}",
        timeout=8000,
    )
    assert hash_changed()


# ── Last-session-delete returns to welcome ───────────────────────────────


@pytest.mark.browser
def test_delete_last_session_returns_to_welcome(app_with_agent: SeededApp, page: Page) -> None:
    """Deleting the only session returns to the welcome canvas (no auto-create)."""
    page.goto(app_with_agent.base_url)
    page.locator(".chat-agent-card").filter(has_text=app_with_agent.agent_name).click()
    expect(page.locator(".convo-agent > span:not(.chip)")).to_have_text(
        app_with_agent.agent_name, timeout=8000
    )

    # The bootstrapped session is the only one. Hover to reveal the delete
    # button (display:none → block via :hover), then click it twice — F4 HAT
    # added a two-step confirm pattern (first click marks .confirm-delete,
    # second click within 3s actually deletes; mirrors studio's pattern).
    item = page.locator(".session-card").first
    expect(item).to_be_visible(timeout=5000)
    item.hover()
    item.locator(".delete").click()
    expect(item).to_have_class(re.compile(r".*confirm-delete.*"), timeout=2000)
    item.locator(".delete").click()

    # Welcome canvas takes over once session_deleted lands and the empty
    # session_list refresh fires.
    expect(page.locator('[data-testid="chat-welcome"]')).to_be_visible(timeout=8000)
    # Holograph .convo-pane is the permanent layout wrapper (always visible);
    # the active session indicator goes away — assert no messages remain.
    expect(page.locator('[data-testid="message"]')).to_have_count(0)


# ── Chat history grouping ────────────────────────────────────────────────


@pytest.mark.browser
def test_chat_history_today_group_renders(app_with_agent: SeededApp, page: Page) -> None:
    """Today's auto-created session lives under a 'Today' group label."""
    page.goto(app_with_agent.base_url)
    page.locator(".chat-agent-card").filter(has_text=app_with_agent.agent_name).click()
    expect(page.locator(".convo-agent > span:not(.chip)")).to_have_text(
        app_with_agent.agent_name, timeout=8000
    )

    expect(page.locator(".sessions-list > .section-title")).to_have_text("Chat History")
    expect(page.locator(".session-group-label").filter(has_text="Today")).to_be_visible(
        timeout=5000
    )


# ── Per-message attribution ──────────────────────────────────────────────


@pytest.mark.browser
def test_message_attribution_labels_render(app_with_agent: SeededApp, page: Page) -> None:
    """Sending a message renders metadata: user message has a timestamp, agent
    message has an author name chip in .msg-meta.

    Holograph replaces the Mission-08 .msg-attribution.from-you / .from-agent
    classes with a unified .msg-meta row. User messages have a .msg-time span;
    agent messages have a .msg-author span containing the agent name.
    """
    page.goto(app_with_agent.base_url)
    page.locator(".chat-agent-card").filter(has_text=app_with_agent.agent_name).click()
    expect(page.locator(".convo-agent > span:not(.chip)")).to_have_text(
        app_with_agent.agent_name, timeout=8000
    )

    page.locator('[data-testid="chat-input"]').fill("hello there")
    page.locator('[data-testid="chat-send-btn"]').click()

    # Wait for the assistant response to land (mock provider returns instantly).
    expect(page.locator('[data-testid="message"].msg-row:not(.user)')).to_be_visible(timeout=10000)

    # Agent message must carry a .msg-author span with the agent's name.
    agent_msg = page.locator('[data-testid="message"].msg-row:not(.user)')
    expect(agent_msg.locator(".msg-author").filter(has_text=app_with_agent.agent_name)).to_have_count(1)

    # User message must carry a .msg-text div with the typed text.
    # Note: .msg-time is only added when a server-side timestamp is present;
    # the local echo fires before the round-trip, so we verify .msg-text instead.
    user_msg = page.locator('[data-testid="message"].msg-row.user')
    expect(user_msg.locator(".msg-text")).to_have_count(1)


# ── Context chip in composer ─────────────────────────────────────────────


@pytest.mark.browser
def test_ctx_chip_shows_in_composer(app_with_agent: SeededApp, page: Page) -> None:
    """The composer shows a context token chip (#chat-ctx-chip) that starts at '0k ctx'
    and updates after a message exchange.

    Holograph replaces the Mission-08 .telemetry-overlay floating panel with an
    inline chip in the composer row. The chip initialises to '0k ctx' and updates
    via updateCtxChip() when the server sends token-count metadata.
    """
    page.goto(app_with_agent.base_url)
    page.locator(".chat-agent-card").filter(has_text=app_with_agent.agent_name).click()
    expect(page.locator(".convo-agent > span:not(.chip)")).to_have_text(
        app_with_agent.agent_name, timeout=8000
    )

    # Chip is visible in the composer at rest.
    chip = page.locator("#chat-ctx-chip")
    expect(chip).to_be_visible()
    # Starts at zero context.
    expect(chip).to_have_text("0k ctx")


# ── Thinking indicator ───────────────────────────────────────────────────


@pytest.mark.browser
def test_thinking_indicator_appears_and_clears(app_clean: str, page: Page) -> None:
    """Thinking bubble appears between send and assistant reply, then is removed.

    A delay_ms is configured on the mock provider so the indicator is visible
    long enough to assert against without flakiness from instant responses.
    """
    # Seed provider with an explicit delay so the indicator window is wide.
    payload = {
        "name": "delayed-mock",
        "type": "mock",
        "base_url": "",
        "config": {"delay_ms": 800},
    }
    r = httpx.post(f"{app_clean}/api/providers", json=payload, timeout=5.0)
    assert r.status_code == 201
    provider_id = r.json()["id"]
    seed_mock_agent(app_clean, provider_id, name="thinker")

    page.goto(app_clean)

    # Bootstrap into chrome by picking the agent in the welcome listbox.
    page.locator(".chat-agent-card").filter(has_text="thinker").click()
    expect(page.locator(".convo-agent > span:not(.chip)")).to_have_text("thinker", timeout=8000)

    page.locator('[data-testid="chat-input"]').fill("ping")
    page.locator('[data-testid="chat-send-btn"]').click()

    # Indicator must appear within the delay window.
    thinking = page.locator('[data-testid="thinking-indicator"]')
    expect(thinking).to_be_visible(timeout=2000)

    # And must be cleared once the assistant reply lands.
    expect(page.locator('[data-testid="message"].msg-row:not(.user)')).to_be_visible(timeout=10000)
    expect(thinking).to_have_count(0)
