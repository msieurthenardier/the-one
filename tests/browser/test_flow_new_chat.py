"""End-to-end flow tests for the F3 leg 05 new-chat restructure.

Covers:
- Welcome canvas content adapts to setup state (no provider, no agent, ready)
- Picking an agent from the welcome listbox starts a new session
- Sidebar agent dropdown change starts a new conversation with that agent
- Header "New Chat" button starts a fresh conversation with the *current* agent
- Deleting the last session returns to the welcome canvas (no auto-create)
- Chat-history sidebar groups sessions under a "Today" heading
- "You" / agent attribution labels render under user / assistant bubbles
- Telemetry overlay starts collapsed and expands on focus
- Thinking indicator appears on send and clears on assistant reply
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
    """No providers and no agents → guidance points to LLM Settings AND Agent Studio.

    Link updated from '#admin' → '#admin/providers' (text: 'Settings' → 'LLM Settings')
    per the chore commit 717cfa5 (UI cleanups + Ollama tool-capability handling).
    """
    page.goto(app_clean)
    welcome = page.locator('[data-testid="chat-welcome"]')
    expect(welcome).to_be_visible(timeout=5000)

    # Greeting present, prompt hidden (no agents to pick).
    expect(page.locator(".chat-welcome-greeting")).to_be_visible()
    expect(page.locator(".chat-welcome-prompt")).to_be_hidden()

    # Both deep-links present.
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

    expect(page.locator(".chat-welcome-prompt")).to_be_hidden()
    expect(page.locator('.chat-welcome-link[href="#studio"]')).to_have_text("Agent Studio")
    expect(page.locator('.chat-welcome-link[href="#admin"]')).to_have_count(0)


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
    expect(page.locator(".chat-welcome-prompt")).to_be_visible()
    welcome_item = page.locator(".chat-welcome-item").filter(has_text=app_with_agent.agent_name)
    expect(welcome_item).to_be_visible(timeout=8000)
    expect(page.locator(".chat-welcome-list")).to_have_attribute("role", "listbox")


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
    agent_item = page.locator(".chat-welcome-item").filter(has_text="picker-agent")
    expect(agent_item).to_be_visible(timeout=8000)

    # Click → session_joined fires → chrome appears, badge populated.
    agent_item.click()

    expect(page.locator(".chat-chrome")).to_be_visible(timeout=8000)
    expect(page.locator(".session-agent-badge")).to_have_text("picker-agent", timeout=5000)
    expect(page.locator('[data-testid="chat-welcome"]')).to_be_hidden()


# ── Dropdown switches agent → starts new conversation ────────────────────


@pytest.mark.browser
def test_dropdown_change_starts_new_session(app_with_provider: SeededApp, page: Page) -> None:
    """Changing the sidebar agent dropdown starts a fresh session with that agent."""
    seed_mock_agent(app_with_provider.base_url, app_with_provider.provider_id, name="agent-a")
    seed_mock_agent(app_with_provider.base_url, app_with_provider.provider_id, name="agent-b")

    page.goto(app_with_provider.base_url)

    # Pick agent-a from the welcome listbox to bootstrap into chrome.
    expect(page.locator(".chat-welcome-item").filter(has_text="agent-a")).to_be_visible(
        timeout=8000
    )
    page.locator(".chat-welcome-item").filter(has_text="agent-a").click()
    expect(page.locator(".session-agent-badge")).to_have_text("agent-a", timeout=8000)

    # Capture session id from the URL hash so we can assert it changes.
    first_hash = page.evaluate("location.hash")
    assert first_hash.startswith("#chat/sessions/")

    # Change the dropdown to agent-b — this fires the change handler which
    # sends `new_session` with agent_name=agent-b.
    page.locator('[data-testid="agent-select"]').select_option("agent-b")

    # Badge should update once the new session is joined.
    expect(page.locator(".session-agent-badge")).to_have_text("agent-b", timeout=8000)

    # Hash should now point at a different session id.
    second_hash = page.evaluate("location.hash")
    assert second_hash.startswith("#chat/sessions/")
    assert second_hash != first_hash, "dropdown change should produce a fresh session id"


# ── Header "New Chat" → new conversation, same agent ─────────────────────


@pytest.mark.browser
def test_header_new_chat_button_starts_session_with_current_agent(
    app_with_agent: SeededApp, page: Page
) -> None:
    """The header `+ New Chat` button opens a new session with the current agent."""
    page.goto(app_with_agent.base_url)
    # Bootstrap a session via the welcome listbox.
    page.locator(".chat-welcome-item").filter(has_text=app_with_agent.agent_name).click()
    expect(page.locator(".session-agent-badge")).to_have_text(
        app_with_agent.agent_name, timeout=8000
    )

    first_hash = page.evaluate("location.hash")
    assert first_hash.startswith("#chat/sessions/")

    page.locator('[data-testid="new-chat-btn"]').click()

    # Same agent — no badge churn.
    expect(page.locator(".session-agent-badge")).to_have_text(
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
    page.locator(".chat-welcome-item").filter(has_text=app_with_agent.agent_name).click()
    expect(page.locator(".session-agent-badge")).to_have_text(
        app_with_agent.agent_name, timeout=8000
    )

    # The bootstrapped session is the only one. Hover to reveal the delete
    # button (display:none → block via :hover), then click it twice — F4 HAT
    # added a two-step confirm pattern (first click marks .confirm-delete,
    # second click within 3s actually deletes; mirrors studio's pattern).
    # F2 leg 01: the row was restructured from a single wrapper-div into a
    # <li class="list-item"> holding <button class="session-item"> + sibling
    # <button class="list-item-delete">. The .confirm-delete class is now
    # applied to the <li>, and the delete button is queried from the row.
    row = page.locator(".area-chat .session-group-list .list-item").first
    expect(row).to_be_visible(timeout=5000)
    row.hover()
    row.locator(".list-item-delete").click()
    expect(row).to_have_class(re.compile(r".*confirm-delete.*"), timeout=2000)
    row.locator(".list-item-delete").click()

    # Welcome canvas takes over once session_deleted lands and the empty
    # session_list refresh fires.
    expect(page.locator('[data-testid="chat-welcome"]')).to_be_visible(timeout=8000)
    expect(page.locator(".chat-chrome")).to_be_hidden()


# ── Chat history grouping ────────────────────────────────────────────────


@pytest.mark.browser
def test_chat_history_today_group_renders(app_with_agent: SeededApp, page: Page) -> None:
    """Today's auto-created session lives under a 'Today' group label."""
    page.goto(app_with_agent.base_url)
    page.locator(".chat-welcome-item").filter(has_text=app_with_agent.agent_name).click()
    expect(page.locator(".session-agent-badge")).to_have_text(
        app_with_agent.agent_name, timeout=8000
    )

    expect(page.locator(".session-list > .section-title")).to_have_text("Chat History")
    expect(page.locator(".session-group-label").filter(has_text="Today")).to_be_visible(
        timeout=5000
    )


# ── Per-message attribution ──────────────────────────────────────────────


@pytest.mark.browser
def test_message_attribution_labels_render(app_with_agent: SeededApp, page: Page) -> None:
    """Sending a message renders 'You' (right) + agent name (left) labels."""
    page.goto(app_with_agent.base_url)
    page.locator(".chat-welcome-item").filter(has_text=app_with_agent.agent_name).click()
    expect(page.locator(".session-agent-badge")).to_have_text(
        app_with_agent.agent_name, timeout=8000
    )

    page.locator('[data-testid="chat-input"]').fill("hello there")
    page.locator('[data-testid="chat-send-btn"]').click()

    # Wait for the assistant response to land (mock provider returns instantly).
    expect(page.locator('[data-testid="message"].assistant')).to_be_visible(timeout=10000)

    # Two attribution labels: one "You" and one with the agent name.
    you_label = page.locator(".msg-attribution.from-you").filter(has_text="You")
    agent_label = page.locator(".msg-attribution.from-agent").filter(
        has_text=app_with_agent.agent_name
    )
    expect(you_label).to_have_count(1)
    expect(agent_label).to_have_count(1)


# ── Telemetry overlay collapsed-by-default ───────────────────────────────


@pytest.mark.browser
def test_telemetry_overlay_collapses_by_default(app_with_agent: SeededApp, page: Page) -> None:
    """The token overlay's details panel is collapsed (max-width 0) at rest."""
    page.goto(app_with_agent.base_url)
    page.locator(".chat-welcome-item").filter(has_text=app_with_agent.agent_name).click()
    expect(page.locator(".session-agent-badge")).to_have_text(
        app_with_agent.agent_name, timeout=8000
    )

    overlay = page.locator(".telemetry-overlay")
    expect(overlay).to_be_visible()

    details_max_width = page.evaluate(
        "() => getComputedStyle(document.querySelector('.telemetry-details')).maxWidth"
    )
    # Either '0px' (chrome) or '0%' depending on browser; both indicate collapsed.
    assert details_max_width in ("0px", "0%"), (
        f"telemetry-details should start collapsed, got max-width={details_max_width!r}"
    )

    # Focus reveals — focus-within lifts max-width above 0.
    overlay.focus()
    page.wait_for_function(
        "() => parseFloat(getComputedStyle(document.querySelector("
        "'.telemetry-details')).maxWidth) > 0",
        timeout=2000,
    )


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
    page.locator(".chat-welcome-item").filter(has_text="thinker").click()
    expect(page.locator(".session-agent-badge")).to_have_text("thinker", timeout=8000)

    page.locator('[data-testid="chat-input"]').fill("ping")
    page.locator('[data-testid="chat-send-btn"]').click()

    # Indicator must appear within the delay window.
    thinking = page.locator('[data-testid="thinking-indicator"]')
    expect(thinking).to_be_visible(timeout=2000)

    # And must be cleared once the assistant reply lands.
    expect(page.locator('[data-testid="message"].assistant')).to_be_visible(timeout=10000)
    expect(thinking).to_have_count(0)
