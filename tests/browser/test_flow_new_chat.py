"""End-to-end flow tests for the F3 leg 05 new-chat restructure.

Covers:
- The welcome adapts to setup state: the guidance (no provider, no agent) or,
  since M25 F4 L4b, the empty state ("Hello.", "Start a conversation with one
  of your agents." and New chat); the welcome's agent listbox is retired
- The empty state's New chat opens the agent picker; a pick starts a pending
  chat (M25 F4 L4b; it replaced the pick from the welcome listbox)
- Picking another agent in the agent picker (the Chats list's New chat, M25 F4
  L4a; it replaced the sidebar agent dropdown) starts a new chat with it
- "Pick a different agent" in the new-chat state re-picks, replacing the
  pending chat (M25 F4 L4b; it replaced the header's retired "New Chat")
- Deleting the last session (the Chats list row's delete action) returns to the
  welcome canvas (no auto-create)
- The Chats list (title "Chats") groups sessions under a "Today" caption
- "You" / agent attribution labels render under user / assistant bubbles
- Telemetry overlay starts collapsed and expands on focus
- Thinking indicator appears on send and clears on assistant reply
"""

from __future__ import annotations

import re

import httpx
import pytest
from browser import _chats, _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp, seed_mock_agent
from playwright.sync_api import Page, expect

# ── Welcome canvas: state-aware content ──────────────────────────────────


def _welcome_link(route: str) -> str:
    """Selector for a welcome-canvas link to *route*.

    The welcome links keep their legacy hrefs until the item-history leg
    converts them to the new scheme, so either form matches (the router
    redirects the legacy one).
    """
    return (
        f'.chat-welcome-link[href="{_nav.href(route)}"], '
        f'.chat-welcome-link[href="{_nav.legacy_hash(route)}"]'
    )


@pytest.mark.browser
def test_welcome_no_setup_shows_both_links(app_clean: str, page: Page) -> None:
    """No providers and no agents → guidance points to Library AND Agents.

    The provider link goes to the create form of Library's Model providers group
    (``#library/providers/~new``, sortie 02, DD6); it was Settings › Providers.
    """
    page.goto(app_clean)
    welcome = _chats.welcome(page)
    expect(welcome).to_be_visible(timeout=5000)

    # The "Hello." h1 present; the prompt hidden and no New chat (M25 F4 L4b,
    # AC5: setup incomplete shows the guidance instead).
    expect(page.locator("h1.chat-welcome-greeting")).to_have_text("Hello.")
    expect(page.locator(".chat-welcome-prompt")).to_be_hidden()
    expect(_chats.empty_new_button(page)).to_have_count(0)

    # Both deep-links present.
    library_link = page.locator(_welcome_link("library/providers/~new"))
    studio_link = page.locator(_welcome_link("agents"))
    expect(library_link).to_have_text("Library")
    expect(studio_link).to_have_text("Agents")


@pytest.mark.browser
def test_welcome_provider_only_shows_studio_link(app_with_provider: SeededApp, page: Page) -> None:
    """Provider seeded, no agents → guidance only points to Agents."""
    page.goto(app_with_provider.base_url)
    welcome = _chats.welcome(page)
    expect(welcome).to_be_visible(timeout=5000)

    expect(page.locator("h1.chat-welcome-greeting")).to_have_text("Hello.")
    expect(page.locator(".chat-welcome-prompt")).to_be_hidden()
    expect(_chats.empty_new_button(page)).to_have_count(0)
    expect(page.locator(_welcome_link("agents"))).to_have_text("Agents")
    expect(page.locator(_welcome_link("library/providers/~new"))).to_have_count(0)


@pytest.mark.browser
def test_welcome_with_agent_shows_the_empty_state(app_with_agent: SeededApp, page: Page) -> None:
    """Provider + agent seeded, no sessions → the empty state (M25 F4 L4b, AC4).

    Replaces ``test_welcome_with_agent_shows_listbox``: the welcome's agent
    listbox is retired. Auto-create-on-load was removed in leg 05; with no
    sessions we land on the welcome: the "Hello." h1, the prompt "Start a
    conversation with one of your agents." and New chat (the agent picker
    opens from it). No guidance, no header.
    """
    page.goto(app_with_agent.base_url)
    welcome = _chats.welcome(page)
    expect(welcome).to_be_visible(timeout=5000)

    expect(welcome.locator("h1.chat-welcome-greeting")).to_have_text("Hello.")
    expect(page.locator(".chat-welcome-prompt")).to_have_text(
        "Start a conversation with one of your agents."
    )
    new_btn = _chats.empty_new_button(page)
    expect(new_btn).to_be_visible()
    expect(new_btn).to_have_text("New chat")
    expect(new_btn).to_have_class(re.compile(r"\bbtn-filled-primary\b"))
    expect(page.locator(".chat-welcome-guidance")).to_have_count(0)
    expect(welcome.get_by_role("listbox")).to_have_count(0)
    expect(_chats.chat_header(page)).to_be_hidden()


# ── The empty state's New chat → the picker → a pending chat ─────────────


@pytest.mark.browser
def test_empty_state_new_chat_opens_the_picker_and_starts_a_chat(
    app_with_provider: SeededApp, page: Page
) -> None:
    """The empty state's New chat opens the agent picker (focus in its search);
    picking an agent is a pending chat with it: the header ("New chat", "with
    picker-agent"), the new-chat state, no welcome, no session until the first
    send (M25 F4 L3b, DD1). Replaces
    ``test_picking_agent_from_welcome_starts_session`` (the welcome listbox's
    pick, retired in leg 4b)."""
    seed_mock_agent(app_with_provider.base_url, app_with_provider.provider_id, name="picker-agent")

    page.goto(app_with_provider.base_url)
    expect(_chats.welcome(page)).to_be_visible(timeout=5000)

    new_btn = _chats.empty_new_button(page)
    new_btn.click()
    expect(_chats.picker(page)).to_be_visible(timeout=8000)
    expect(_chats.picker_search(page)).to_be_focused()
    # Escape returns focus to the empty state's New chat.
    page.keyboard.press("Escape")
    expect(_chats.picker(page)).to_have_count(0)
    expect(new_btn).to_be_focused()

    new_btn.click()
    _chats.picker_search(page).fill("picker-agent")
    expect(_chats.picker_rows(page)).to_have_count(1)
    _chats.picker_search(page).press("Enter")

    expect(page.locator(".chat-chrome")).to_be_visible(timeout=8000)
    _chats.expect_chat(page, "picker-agent", title="New chat", timeout=5000)
    expect(_chats.new_chat_state(page)).to_be_visible()
    expect(_chats.welcome(page)).to_be_hidden()
    _nav.expect_route(page, "chats/~new/picker-agent")
    assert _chats.current_session_id(page) is None
    expect(_chats.pending_row(page)).to_have_count(1)
    # The first send creates the session; the new-chat state gives way to the
    # message log.
    sid = _chats.send_first(page, "hi")
    _nav.expect_route(page, f"chats/{_nav.seg(sid)}")
    expect(_chats.new_chat_state(page)).to_be_hidden()


# ── The picker switches agent → starts a new chat ────────────────────────


@pytest.mark.browser
def test_picker_pick_of_another_agent_starts_new_chat(
    app_with_provider: SeededApp, page: Page
) -> None:
    """M25 F4 L4a replaced the sidebar agent dropdown with the agent picker
    (``test_dropdown_change_starts_new_session`` became this test): from an
    open chat, New chat opens the picker; typing and Enter picks agent-b, a
    fresh pending chat with it (`#chats/~new/agent-b`, a `leave`, no session),
    and its first send makes a fresh session."""
    seed_mock_agent(app_with_provider.base_url, app_with_provider.provider_id, name="agent-a")
    seed_mock_agent(app_with_provider.base_url, app_with_provider.provider_id, name="agent-b")
    frames = _chats.chat_frames(page, actions=("leave", "start_session"))
    page.goto(app_with_provider.base_url)

    _chats.start_chat(page, "agent-a")
    first = _chats.send_first(page, "to a")

    # New chat → the picker, focus in its search; type, Enter.
    _chats.open_picker(page)
    _chats.picker_search(page).fill("agent-b")
    expect(_chats.picker_rows(page)).to_have_count(1)
    _chats.picker_search(page).press("Enter")
    expect(_chats.picker(page)).to_have_count(0)

    # The pending chat with agent-b; nothing created.
    _chats.expect_chat(page, "agent-b")
    _nav.expect_route(page, "chats/~new/agent-b")
    assert _chats.current_session_id(page) is None
    expect(_chats.pending_row(page)).to_have_count(1)
    assert [f["action"] for f in frames] == ["start_session", "leave"]

    # The first send makes a different session.
    second = _chats.send_first(page, "to b")
    assert second != first, "a pick should produce a fresh session id"
    _chats.expect_chat(page, "agent-b")


# ── "Pick a different agent" → the picker → a re-pick ───────────────────


@pytest.mark.browser
def test_pick_a_different_agent_re_picks(app_with_provider: SeededApp, page: Page) -> None:
    """The new-chat state's "Pick a different agent" opens the agent picker
    (focus back on it on Escape); a pick replaces the pending chat (the
    ``~new`` route is replaced, not pushed: reference spec 10, item 14) and
    sends nothing. Replaces
    ``test_header_new_chat_button_starts_session_with_current_agent`` (the
    header's "New Chat" is retired in M25 F4 L4b)."""
    seed_mock_agent(app_with_provider.base_url, app_with_provider.provider_id, name="agent-a")
    seed_mock_agent(app_with_provider.base_url, app_with_provider.provider_id, name="agent-b")
    frames = _chats.chat_frames(page, actions=("leave", "start_session", "join"))
    page.goto(app_with_provider.base_url)
    _chats.start_chat(page, "agent-a")
    seq = page.evaluate("history.state && history.state.seq")

    pick_btn = _chats.pick_different_button(page)
    expect(pick_btn).to_have_text("Pick a different agent")
    pick_btn.click()
    expect(_chats.picker(page)).to_be_visible(timeout=8000)
    expect(_chats.picker_search(page)).to_be_focused()
    page.keyboard.press("Escape")
    expect(_chats.picker(page)).to_have_count(0)
    expect(pick_btn).to_be_focused()

    pick_btn.click()
    _chats.picker_search(page).fill("agent-b")
    expect(_chats.picker_rows(page)).to_have_count(1)
    _chats.picker_search(page).press("Enter")

    _chats.expect_chat(page, "agent-b", title="New chat")
    _nav.expect_route(page, "chats/~new/agent-b")
    assert page.evaluate("history.state && history.state.seq") == seq  # replaced
    expect(_chats.new_chat_state(page).locator("h2")).to_have_text("agent-b")
    expect(_chats.pending_row(page)).to_have_count(1)
    assert _chats.current_session_id(page) is None
    assert frames == []  # nothing was bound, so not even a leave

    second = _chats.send_first(page, "to b")
    _chats.expect_chat(page, "agent-b")
    assert [(f["action"], f.get("agent_name")) for f in frames] == [("start_session", "agent-b")]
    assert second == _chats.current_session_id(page)


# ── Last-session-delete returns to welcome ───────────────────────────────


@pytest.mark.browser
def test_delete_last_session_returns_to_welcome(app_with_agent: SeededApp, page: Page) -> None:
    """Deleting the only session returns to the welcome canvas (no auto-create)."""
    page.goto(app_with_agent.base_url)
    _chats.start_chat(page, app_with_agent.agent_name)
    sid = _chats.send_first(page, "hello")  # a start is pending; the send makes the session

    # The bootstrapped session is the only one. Hover to reveal the delete
    # action (display:none until the row's <li> is hovered or has focus),
    # then click it twice — F4 HAT added a two-step confirm pattern (first
    # click marks .confirm-delete, second click within 3s actually deletes).
    # M25 F4 L4a: the row is an App.ui.listPane <li> holding the row link
    # (chat-row) and its sibling delete action (chat-row-delete); the
    # .confirm-delete class is applied to the <li>.
    row = page.locator("li").filter(has=_chats.chat_row(page, sid))
    expect(row).to_be_visible(timeout=5000)
    row.hover()
    _chats.chat_row_delete(page, sid).click()
    expect(row).to_have_class(re.compile(r".*confirm-delete.*"), timeout=2000)
    _chats.chat_row_delete(page, sid).click()

    # Welcome canvas takes over once session_deleted lands and the empty
    # session_list refresh fires: the empty state (M25 F4 L4b), not a header.
    expect(_chats.welcome(page)).to_be_visible(timeout=8000)
    expect(page.locator(".chat-chrome")).to_be_hidden()
    expect(_chats.empty_new_button(page)).to_be_visible()


@pytest.mark.browser
def test_session_delete_confirm_lapse_is_visually_distinct(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Mission 24 Flight 7 confirm-lapse leg, AC-4: the chat session-delete
    confirm is distinguishable on screen from one that was never armed, past
    the real 3s `revertMs`. M25 F4 L4a re-pinned it on the Chats list's
    App.ui.listPane row `<li>` (the delete is the row's `chat-row-delete`
    action): an ARMED `<li>` survives a `setItems` rebuild (the listPane
    reuses it, DD5), but a lapsed one does not, so a session_list broadcast
    after the lapse still rebuilds it without the cue -- the limitation the
    M24 leg recorded at this site. Nothing in this quiescent single-session
    test triggers one: the turn's reply (and its list refresh) lands before
    the arm."""
    page.goto(app_with_agent.base_url)
    _chats.start_chat(page, app_with_agent.agent_name)
    sid = _chats.send_first(page, "hello")  # a start is pending; the send makes the session
    expect(page.locator('[data-testid="message"].assistant')).to_be_visible(timeout=10000)

    row = page.locator("li").filter(has=_chats.chat_row(page, sid))
    expect(row).to_be_visible(timeout=5000)
    expect(row).not_to_have_class(re.compile(r"\bconfirm-lapsed\b"))
    row.hover()
    _chats.chat_row_delete(page, sid).click()
    expect(row).to_have_class(re.compile(r"\bconfirm-delete\b"), timeout=2000)

    expect(row).not_to_have_class(re.compile(r"\bconfirm-delete\b"), timeout=4000)
    expect(row).to_have_class(re.compile(r"\bconfirm-lapsed\b"))
    # Never committed: still on the same session, chrome still visible.
    expect(page.locator(".chat-chrome")).to_be_visible()


# ── The Chats list's grouping ────────────────────────────────────────────


@pytest.mark.browser
def test_chats_list_title_and_today_group_render(app_with_agent: SeededApp, page: Page) -> None:
    """The Chats list is titled "Chats" and today's chat (the pending one, then
    its session) lives under a "Today" caption. M25 F4 L4a re-pinned
    ``test_chat_history_today_group_renders`` (the retired "Chat History"
    heading and bucket label) on the App.ui.listPane title and caption."""
    page.goto(app_with_agent.base_url)
    _chats.start_chat(page, app_with_agent.agent_name)

    chats = page.locator('[data-testid="chats-list"]')
    expect(chats.locator(".ui-list-pane-title")).to_have_text("Chats")
    today = chats.locator(".ui-list-pane-group").filter(
        has=page.locator(".ui-list-pane-caption", has_text="Today")
    )
    expect(today).to_be_visible(timeout=5000)
    expect(today.locator('[data-testid="chat-row"][data-pending]')).to_have_count(1)
    sid = _chats.send_first(page, "hello")
    expect(today.locator(f'[data-testid="chat-row"][data-id="{sid}"]')).to_be_visible()


# ── Per-message attribution ──────────────────────────────────────────────


@pytest.mark.browser
def test_message_attribution_labels_render(app_with_agent: SeededApp, page: Page) -> None:
    """Sending a message renders 'You' (right) + agent name (left) labels."""
    page.goto(app_with_agent.base_url)
    _chats.start_chat(page, app_with_agent.agent_name)

    _chats.send_first(page, "hello there")

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
    """The token overlay's details panel is collapsed (max-width 0) at rest.

    M25 F4 L5 (reference spec 5.3, 5.4): the readout sits in the composer's
    telemetry row, shown only while a chat is joined, so this is pinned to a
    joined chat (it was read right after the start, in the pending chat)."""
    page.goto(app_with_agent.base_url)
    _chats.start_chat(page, app_with_agent.agent_name)
    overlay = page.locator(".telemetry-overlay")
    expect(overlay).to_be_hidden()  # pending: no telemetry
    _chats.send_first(page, "hello")
    expect(page.locator('[data-testid="message"].assistant')).to_be_visible(timeout=10000)

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
    r = httpx.post(
        f"{app_clean}/api/providers", json=payload, timeout=5.0, headers=auth_headers_for(app_clean)
    )
    assert r.status_code == 201
    provider_id = r.json()["id"]
    seed_mock_agent(app_clean, provider_id, name="thinker")

    page.goto(app_clean)

    # Bootstrap into the chrome: a pending chat through the agent picker.
    _chats.start_chat(page, "thinker")

    _chats.send_first(page, "ping")

    # Indicator must appear within the delay window.
    thinking = page.locator('[data-testid="thinking-indicator"]')
    expect(thinking).to_be_visible(timeout=2000)

    # And must be cleared once the assistant reply lands.
    expect(page.locator('[data-testid="message"].assistant')).to_be_visible(timeout=10000)
    expect(thinking).to_have_count(0)
