"""The GleepGlorp drawer's chat (M36 F3 L3, flight DD2 and DD3).

A second chat instance (``App.chat.create``, the drawer profile) is mounted in the drawer shell
and connects its own WebSocket at page load. Covers, as state transitions:

* [closed] -> [open] -> [working] -> [replied]: a chat from Library, the URL never changes;
* Chats and the drawer are independent conversations (and the drawer's shows in the Chats list);
* [pending] -> [joined] -> reload -> first open re-joins; New chat clears; a second tab shares it;
* Open in Chats (guarded, absent while pending) and back;
* the socket gap: a window that never visits Chats still receives the window-wide frames;
* the drawer socket is quiet (no ``list_sessions``, ``join`` or ``start_session`` unasked);
* the window frames run once with two sockets open;
* a deleted or stale conversation returns the drawer to a fresh pending chat;
* no duplicate construct-time testids, and the focus rules.

Falls in the ``shared`` browser lane (it is not claimed by a named lane glob).
"""

from __future__ import annotations

import httpx
import pytest
from browser import _chats, _drawer, _nav
from browser._credential_registry import auth_headers_for
from browser._drawer import (  # noqa: F401  (the constants are used by name below)
    BTN,
    DRAWER,
    EMPTY,
    INPUT,
    NEW_CHAT,
    OPEN_IN_CHATS,
    SEND,
    SETUP_ACTION,
    STAY,
    STORE,
    SUGGESTION,
)
from browser.seeders import SeededApp, seed_gleepglorp_proposal, seed_mock_provider
from browser.test_flow_chat_proposals import _world
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

# The shared drawer helpers live in tests/browser/_drawer.py (M36 F3 L6); the underscore names
# below are kept so this file's tests read as before.
_RECORD = _drawer.RECORD
_DRAWER_INDEX = _drawer.DRAWER_INDEX
_DELIVER = _drawer.DELIVER
_put = _drawer.put_settings
_ready = _drawer.ready
_ready_with_reply = _drawer.ready_with_reply
_boot = _drawer.boot
_wait_socket = _drawer.wait_socket
_drawer_sent = _drawer.drawer_sent
_actions = _drawer.actions
_open_drawer = _drawer.open_drawer
_drawer_msgs = _drawer.drawer_msgs
_send = _drawer.send
_stored = _drawer.stored
_drawer_session = _drawer.drawer_session
_wait_joined = _drawer.wait_joined
_chat_with = _drawer.chat_with


# ── AC1: the drawer chat works ───────────────────────────────────────────────


def test_a_drawer_chat_from_library_never_changes_the_url(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    _ready_with_reply(base, "Hello from the mock", delay_ms=1200)
    _boot(page, base, "library")
    route = _nav.current_route(page)
    _open_drawer(page)
    expect(page.locator(EMPTY)).to_be_visible()
    expect(page.locator(INPUT)).to_have_attribute("placeholder", "Message GleepGlorp…")
    _send(page, "hello")
    expect(_drawer_msgs(page, "user").last).to_contain_text("hello")
    # [working]: the turn work group while the model answers, then the reply.
    expect(page.locator(f'{DRAWER} [data-testid="turn-work"]')).to_be_visible(timeout=8000)
    expect(_drawer_msgs(page, "assistant").last).to_contain_text(
        "Hello from the mock", timeout=15000
    )
    sid = _wait_joined(page)
    assert _nav.current_route(page) == route
    # The empty state is gone and Open in Chats appears.
    expect(page.locator(EMPTY)).to_be_hidden()
    expect(page.locator(OPEN_IN_CHATS)).to_be_visible()
    # The Chats list (opened afterwards) lists the conversation as a GleepGlorp chat.
    _nav.open_destination(page, "chats")
    row = _chats.chat_row(page, sid)
    expect(row).to_be_visible(timeout=8000)
    expect(row).to_contain_text("GleepGlorp")


# ── AC2: Chats and the drawer are independent ────────────────────────────────


def test_chats_and_the_drawer_keep_separate_conversations(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _ready_with_reply(base, "Drawer reply")
    _boot(page, base, "chats", connected=False)
    _chats.start_chat(page, agent)
    chats_sid = _chats.send_first(page, "chats message")
    expect(_chats.messages(page, "assistant").last).to_be_visible(timeout=10000)
    chats_route = _nav.current_route(page)

    _nav.open_destination(page, "agents")
    page.wait_for_function(
        "() => App.gleepglorpDrawer.state() !== null && App.gleepglorpDrawerChat.instance()"
        ".ws().readyState === 1",
        timeout=8000,
    )
    drawer_sid = _chat_with(page, "drawer message", "Drawer reply")
    assert drawer_sid != chats_sid

    # Back to Chats: its chat is as it was, with no drawer messages, and the list has both rows.
    _nav.open_destination(page, "chats")
    assert _nav.current_route(page) == chats_route
    expect(_chats.messages(page, "user").last).to_contain_text("chats message")
    expect(_chats.messages(page, "user").filter(has_text="drawer message")).to_have_count(0)
    expect(_chats.chat_row(page, drawer_sid)).to_be_visible(timeout=8000)
    expect(page.locator(DRAWER)).to_be_hidden()

    # Leaving Chats again: the drawer shows its own conversation.
    _nav.open_destination(page, "library")
    expect(page.locator(DRAWER)).to_be_visible()
    expect(_drawer_msgs(page, "user").last).to_contain_text("drawer message")
    expect(_drawer_msgs(page, "user").filter(has_text="chats message")).to_have_count(0)


# ── AC3: continuity ──────────────────────────────────────────────────────────


def test_the_conversation_persists_across_pages_and_a_reload_joins_on_first_open(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    _ready_with_reply(base, "Persisted reply")
    _boot(page, base, "library")
    sid = _chat_with(page, "remember me", "Persisted reply")
    assert _stored(page) == sid
    # Across pages the drawer keeps the conversation.
    _nav.open_destination(page, "settings")
    expect(_drawer_msgs(page, "user").last).to_contain_text("remember me")

    # A reload: boot sends no join; the first open joins the stored id.
    page.reload()
    _wait_socket(page)
    assert "join" not in _actions(_drawer_sent(page))
    assert _actions(_drawer_sent(page)) == []
    _open_drawer(page)
    expect(_drawer_msgs(page, "user").last).to_contain_text("remember me", timeout=10000)
    assert _drawer_session(page) == sid
    joins = [f for f in _drawer_sent(page) if f.get("action") == "join"]
    assert joins == [{"action": "join", "session_id": sid}]


def test_new_chat_starts_a_pending_chat_and_a_reload_opens_pending(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    _ready_with_reply(base, "First reply")
    _boot(page, base, "agents")
    sid = _chat_with(page, "first", "First reply")
    expect(page.locator(NEW_CHAT)).to_have_accessible_name("New chat")
    page.locator(NEW_CHAT).click()
    expect(page.locator(EMPTY)).to_be_visible()
    expect(_drawer_msgs(page, "user")).to_have_count(0)
    expect(page.locator(OPEN_IN_CHATS)).to_be_hidden()
    assert _stored(page) is None
    expect(page.locator(INPUT)).to_be_focused()
    page.reload()
    _wait_socket(page)
    _open_drawer(page)
    expect(page.locator(EMPTY)).to_be_visible()
    assert "join" not in _actions(_drawer_sent(page))
    # The old conversation is still in the list (New chat never deleted it).
    assert httpx.get(f"{base}/api/chat/sessions", headers=auth_headers_for(base), timeout=5).json()
    assert sid


def test_a_second_tab_opening_the_drawer_shows_the_same_conversation(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    _ready_with_reply(base, "Shared reply")
    _boot(page, base, "agents")
    sid = _chat_with(page, "shared text", "Shared reply")
    other = page.context.new_page()
    other.add_init_script(_RECORD)
    _nav.goto(other, base, "library")
    _wait_socket(other)
    _open_drawer(other)
    expect(_drawer_msgs(other, "user").last).to_contain_text("shared text", timeout=10000)
    assert _drawer_session(other) == sid
    other.close()


def test_opening_before_the_socket_is_open_joins_once_it_opens(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    _ready_with_reply(base, "Late reply")
    _boot(page, base, "agents")
    sid = _chat_with(page, "late join", "Late reply")
    # Reload with the drawer socket held CONNECTING.
    page.add_init_script("window.__hold = true;")
    page.reload()
    page.wait_for_function(
        "() => window.__socks.length >= 1 && window.__socks[0].opened === true", timeout=8000
    )
    page.wait_for_function(
        "() => App.gleepglorpDrawer && App.gleepglorpDrawer.state() !== null", timeout=8000
    )
    assert page.evaluate("() => App.gleepglorpDrawerChat.instance().ws().readyState") == 0
    _open_drawer(page)
    assert _actions(_drawer_sent(page)) == []
    page.evaluate("() => window.__releaseSocks()")
    expect(_drawer_msgs(page, "user").last).to_contain_text("late join", timeout=10000)
    assert _drawer_session(page) == sid


# ── AC4: Open in Chats ───────────────────────────────────────────────────────


def test_open_in_chats_moves_to_chats_and_the_drawer_follows_a_message_sent_there(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    _ready_with_reply(base, "Open reply")
    _boot(page, base, "library")
    _open_drawer(page)
    # Absent while pending.
    expect(page.locator(OPEN_IN_CHATS)).to_be_hidden()
    expect(page.locator(OPEN_IN_CHATS)).to_have_attribute("aria-label", "Open in Chats")
    sid = _chat_with(page, "start here", "Open reply")
    page.locator(OPEN_IN_CHATS).click()
    _nav.expect_route(page, f"chats/{sid}", timeout=8000)
    expect(page.locator(DRAWER)).to_be_hidden()
    page.wait_for_function(_chats_joined_js(sid), timeout=10000)
    expect(_chats.messages(page, "user").last).to_contain_text("start here")
    # A message sent in Chats shows in the drawer's conversation on leaving Chats.
    box = page.locator('[data-testid="chat-input"]')
    box.fill("sent in chats")
    box.press("Enter")
    expect(_chats.messages(page, "assistant").last).to_contain_text("Open reply", timeout=15000)
    _nav.open_destination(page, "agents")
    expect(page.locator(DRAWER)).to_be_visible()
    expect(_drawer_msgs(page, "user").filter(has_text="sent in chats")).to_have_count(
        1, timeout=15000
    )


_LOG_ROLE_JS = "() => App.gleepglorpDrawerChat.instance().messagesEl.getAttribute('role')"


def test_the_log_is_a_live_region_only_while_the_drawer_is_shown(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    _ready_with_reply(base)
    _boot(page, base, "library")
    _open_drawer(page)
    assert page.evaluate(_LOG_ROLE_JS) == "log"
    # Navigating to Chats hides the drawer through apply(): the listeners are told.
    _nav.open_destination(page, "chats")
    expect(page.locator(DRAWER)).to_be_hidden()
    assert page.evaluate(_LOG_ROLE_JS) is None
    assert (
        page.evaluate(
            "() => App.gleepglorpDrawerChat.instance().messagesEl.hasAttribute('aria-live')"
        )
        is False
    )
    # Back on Agents the remembered open state shows the drawer, and the log is live again.
    _nav.open_destination(page, "agents")
    expect(page.locator(DRAWER)).to_be_visible()
    assert page.evaluate(_LOG_ROLE_JS) == "log"
    # GleepGlorp turning off hides it the same way.
    _chats.gleepglorp_off(base)
    expect(page.locator(DRAWER)).to_be_hidden(timeout=8000)
    assert page.evaluate(_LOG_ROLE_JS) is None


def _chats_joined_js(sid: str) -> str:
    return (
        "() => { const a = App.areas.find(x => x.id === 'chat'); const st = a._sessionState();"
        f" return st.name === 'joined' && st.id === '{sid}'; }}"
    )


# ── AC5: the socket gap is closed ────────────────────────────────────────────


def test_an_approval_reaches_an_editor_in_a_window_that_never_visited_chats(
    app_with_data_dir: tuple, page: Page
) -> None:
    w = _world(app_with_data_dir)
    agent = "plain"
    pid = seed_gleepglorp_proposal(
        w.data,
        w.sid,
        agent_name=agent,
        changes={"description": "Approved with no Chats visit"},
        base={"description": ""},
    )
    _boot(page, w.base, f"agents/{_nav.seg(agent)}/general")
    assert (
        page.evaluate(
            "() => { const a = App.areas.find(x => x.id === 'chat'); return !a._ws || !a._ws(); }"
        )
        is True
    )
    expect(page.locator("#studio-description")).to_be_attached(timeout=8000)
    expect(page.locator("#studio-model")).to_have_value("mock-default", timeout=8000)
    r = httpx.post(
        f"{w.base}/api/gleepglorp/proposals/{pid}/approve",
        headers=auth_headers_for(w.base),
        timeout=10,
    )
    assert r.status_code == 200, r.text
    expect(page.locator("#studio-description")).to_have_value(
        "Approved with no Chats visit", timeout=8000
    )
    expect(
        page.locator('[data-testid="agent-approved-change-note"][data-field="description"]')
    ).to_have_count(1, timeout=8000)


def test_a_gleepglorp_push_updates_the_window_without_a_chats_visit(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    _ready(app_with_agent)
    _boot(page, base, "agents")
    expect(page.locator(BTN)).to_be_visible()
    # Turned off from "another window": the corner button hides with no reload.
    _put(base, enabled=False, provider_config_id=app_with_agent.provider_id, model="mock-default")
    expect(page.locator(BTN)).to_be_hidden(timeout=8000)
    _ready(app_with_agent)
    expect(page.locator(BTN)).to_be_visible(timeout=8000)


# ── AC6: the drawer socket is quiet ──────────────────────────────────────────


def test_the_drawer_socket_sends_nothing_on_boot_or_unasked(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    _ready_with_reply(base, "Quiet reply", delay_ms=800)
    _boot(page, base, "agents")
    page.wait_for_timeout(1200)
    assert _drawer_sent(page) == []
    # Opening the drawer on its own sends nothing either (nothing is stored).
    _open_drawer(page)
    page.wait_for_timeout(300)
    assert _drawer_sent(page) == []
    # A send starts the chat: one start_session, never list_sessions.
    _send(page, "hello")
    expect(_drawer_msgs(page, "assistant").last).to_contain_text("Quiet reply", timeout=15000)
    _wait_joined(page)
    acts = _actions(_drawer_sent(page))
    assert acts == ["start_session"], acts
    # A start failure (a frame for the in-flight start) restores the pending chat, still quiet.
    page.locator(NEW_CHAT).click()
    _send(page, "again")
    cid = page.evaluate(
        "() => { const i = App.gleepglorpDrawerChat.instance(); return i.serialize(); }"
    )
    assert cid.startswith("new/")
    start = [f for f in _drawer_sent(page) if f.get("action") == "start_session"][-1]
    page.evaluate(
        """(sid) => { const i = App.gleepglorpDrawerChat.instance();
          const r = window.__socks.find(x => x.ws === i.ws());
          r.ws.onmessage({ data: JSON.stringify({ type: 'start_failed', session_id: sid,
                                                  error: 'Could not start.' }) }); }""",
        start["session_id"],
    )
    expect(page.locator(EMPTY)).to_be_visible(timeout=8000)
    assert "list_sessions" not in _actions(_drawer_sent(page))


def test_a_join_failed_for_a_stale_id_goes_pending_and_clears_it_with_no_listing(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    _ready(app_with_agent)
    stale = "0" * 32
    page.add_init_script(f"localStorage.setItem('{STORE}', '{stale}');")
    _boot(page, base, "library")
    assert _drawer_sent(page) == []
    _open_drawer(page)
    expect(page.locator(EMPTY)).to_be_visible(timeout=10000)
    page.wait_for_function(f"() => localStorage.getItem('{STORE}') === null", timeout=8000)
    acts = _actions(_drawer_sent(page))
    assert acts == ["join"], acts
    expect(page.locator(OPEN_IN_CHATS)).to_be_hidden()


# ── AC7: window frames run once ──────────────────────────────────────────────

_INSTRUMENT = """
() => {
  window.__rec = [];
  const orig = App.approvals.record;
  App.approvals.record = function (d) {
    const r = orig.call(this, d); window.__rec.push(r); return r;
  };
  window.__events = 0;
  document.addEventListener(App.approvals.CONFIG_CHANGED, () => { window.__events++; });
  window.__notes = 0;
  window.addEventListener('gleepglorp-notes-changed', () => { window.__notes++; });
  window.__ggNotify = 0;
  App.gleepglorp.subscribe(() => { window.__ggNotify++; });
}
"""


def test_window_frames_run_once_with_both_sockets_open(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _ready(app_with_agent)
    _boot(page, base, "chats", connected=False)
    page.wait_for_function(
        "() => window.__socks.length >= 2 && window.__socks.every(r => r.ws.readyState === 1)",
        timeout=10000,
    )
    _nav.open_destination(page, "agents")
    page.evaluate(_INSTRUMENT)

    frame = {
        "type": "config_changed",
        "kind": "agent",
        "agent": agent,
        "fields": ["description"],
        "session_id": "sess-x",
        "proposal_id": 4242,
        "at": "2026-01-02T15:05:00+00:00",
    }
    page.evaluate(_DELIVER, frame)
    assert page.evaluate("() => window.__rec") == [True, False]
    assert page.evaluate("() => window.__events") == 1

    # A notes-only push reaches both sockets in separate tasks: one event.
    page.evaluate(_DELIVER, {"type": "gleepglorp_changed"})
    assert page.evaluate("() => window.__notes") == 1

    # Unchanged settings notify nobody; a changed value notifies once (not twice).
    settings = page.evaluate("() => App.gleepglorp.peek().value")
    page.evaluate(_DELIVER, {"type": "gleepglorp_changed", "settings": settings})
    assert page.evaluate("() => window.__ggNotify") == 0
    changed = dict(settings, retention_days=settings["retention_days"] + 1)
    page.evaluate(_DELIVER, {"type": "gleepglorp_changed", "settings": changed})
    assert page.evaluate("() => window.__ggNotify") == 1


# ── AC8: a deleted or stale drawer conversation ──────────────────────────────


def test_deleting_the_conversation_from_chats_resets_the_drawer(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    _ready_with_reply(base, "Doomed reply")
    _boot(page, base, "agents")
    sid = _chat_with(page, "delete me", "Doomed reply")
    assert _stored(page) == sid
    _nav.open_destination(page, "chats")
    page.wait_for_function(_chats_joined_js(sid), timeout=10000)
    page.locator("li").filter(has=_chats.chat_row(page, sid)).hover()
    _chats.chat_row_delete(page, sid).click()
    _chats.chat_row_delete(page, sid).click()
    expect(_chats.chat_row(page, sid)).to_have_count(0, timeout=8000)
    _nav.open_destination(page, "agents")
    expect(page.locator(DRAWER)).to_be_visible()
    expect(page.locator(EMPTY)).to_be_visible(timeout=8000)
    expect(_drawer_msgs(page, "user")).to_have_count(0)
    assert _stored(page) is None
    assert page.evaluate("() => App.gleepglorpDrawerChat.instance().sessionState().name") == (
        "pending"
    )


# ── AC9: no duplicate construct-time testids ─────────────────────────────────

_DUPES = """
() => {
  const bad = [];
  document.querySelectorAll('#gleepglorp-drawer [data-testid]').forEach((n) => {
    const t = n.getAttribute('data-testid');
    if (t.indexOf('gg-') === 0) return;
    if (document.querySelectorAll('[data-testid="' + t + '"]').length !== 1) bad.push(t);
  });
  return bad;
}
"""


def test_the_drawer_instance_has_no_duplicate_construct_time_testids(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    _ready(app_with_agent)
    # Chats visited first, so its panel (with its own ids) is built beside the drawer's.
    _boot(page, base, "chats", connected=False)
    _nav.open_destination(page, "agents")
    page.wait_for_function(
        "() => App.gleepglorpDrawerChat.instance().ws().readyState === 1", timeout=8000
    )
    assert page.evaluate(_DUPES) == []
    _open_drawer(page)
    assert page.evaluate(_DUPES) == []
    # The ids the Chats header, welcome and mascot own are not built in the drawer.
    for tid in ("chat-header", "chat-welcome", "chat-welcome-mascot", "chat-agent-line"):
        assert (
            page.evaluate(
                "(t) => document.querySelectorAll("
                "'#gleepglorp-drawer [data-testid=\"' + t + '\"]').length",
                tid,
            )
            == 0
        )


# ── AC10: focus ──────────────────────────────────────────────────────────────


def test_open_focuses_the_composer_when_ready_and_the_setup_link_when_not(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    # [needs a model]: the setup link, and the suggestion is disabled.
    _boot(page, base, "agents")
    _open_drawer(page)
    expect(page.locator(SETUP_ACTION)).to_be_focused()
    expect(page.locator(SUGGESTION)).to_be_disabled()
    # [ready]: the composer.
    _ready(app_with_agent)
    page.reload()
    _wait_socket(page)
    page.wait_for_function(
        "() => App.gleepglorp.peek().value && App.gleepglorp.peek().value.state === 'ready'",
        timeout=8000,
    )
    _open_drawer(page)
    expect(page.locator(INPUT)).to_be_focused()
    expect(page.locator(SUGGESTION)).to_be_enabled()


def test_the_suggestion_sends_its_text_and_new_chat_focuses_the_composer(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    _ready_with_reply(base, "It does things")
    _boot(page, base, "library")
    _open_drawer(page)
    page.locator(SUGGESTION).click()
    expect(_drawer_msgs(page, "user").last).to_contain_text("What does this page do?")
    expect(_drawer_msgs(page, "assistant").last).to_contain_text("It does things", timeout=15000)
    page.locator(NEW_CHAT).click()
    expect(page.locator(INPUT)).to_be_focused()


def test_open_in_chats_is_guarded_and_stay_returns_focus_to_the_button(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    _ready_with_reply(base, "Guarded reply")
    _boot(page, base, "agents")
    _chat_with(page, "guard me", "Guarded reply")
    page.evaluate("() => App.nav.registerSource('t', { isDirty: () => true, discard() {} })")
    page.locator(OPEN_IN_CHATS).click()
    expect(page.locator(STAY)).to_be_visible(timeout=5000)
    page.locator(STAY).click()
    expect(page.locator(OPEN_IN_CHATS)).to_be_focused()
    assert _nav.current_route(page).startswith("agents")


def test_the_drawer_stores_one_bare_session_id_under_one_key(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    _ready_with_reply(base, "Id reply")
    _boot(page, base, "agents")
    sid = _chat_with(page, "id please", "Id reply")
    keys = page.evaluate(
        "() => Object.keys(localStorage).filter(k => k.indexOf('gleepglorp') === 0)"
    )
    assert keys == [STORE]
    assert _stored(page) == sid


# ── M36 F3 L4: the page travels with each drawer message, and shows as a chip ─────────────

CHIP = f'{DRAWER} [data-testid="message-context"]'
MCP_NEW_LINE = "Library › MCP servers › New MCP server"
MCP_NEW_PAGE = {"destination": "library", "section": "mcp", "create": True}

# Drop the named frame types the page receives (a window that has not heard of a settings change).
_DROP = """
(() => {
  const Native = window.WebSocket;
  window.__drop = [];
  const desc = Object.getOwnPropertyDescriptor(Native.prototype, 'onmessage');
  Object.defineProperty(Native.prototype, 'onmessage', {
    set(fn) {
      desc.set.call(this, fn ? function (ev) {
        try { if (window.__drop.includes(JSON.parse(ev.data).type)) return; } catch (e) {}
        return fn.call(this, ev);
      } : fn);
    },
    get() { return desc.get.call(this); },
    configurable: true,
  });
})();
"""


def _frames(page: Page, action: str) -> list[dict]:
    """The drawer's sent frames of an action; a plain `message` frame is `{message}` alone
    (no `action` key), so "message" selects those."""
    if action == "message":
        return [f for f in _drawer_sent(page) if "message" in f and "action" not in f]
    return [f for f in _drawer_sent(page) if f.get("action") == action]


def _chip_precedes_its_bubble(page: Page, index: int = 0) -> bool:
    return page.evaluate(
        """(i) => { const c = document.querySelectorAll(
            '#gleepglorp-drawer [data-testid="message-context"]')[i];
          const n = c && c.nextElementSibling;
          return !!n && n.matches('[data-testid="message"].ui-message--user'); }""",
        index,
    )


def test_the_first_message_carries_the_page_and_its_bubble_gains_the_servers_line(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    _ready_with_reply(base, "Page reply")
    _boot(page, base, "library/mcp/~new")
    _open_drawer(page)
    _send(page, "what is this?")
    expect(page.locator(CHIP)).to_have_text(MCP_NEW_LINE, timeout=15000)
    assert [f["page"] for f in _frames(page, "start_session")] == [MCP_NEW_PAGE]
    assert _chip_precedes_its_bubble(page)
    # The chip is not a bubble: the user-message count is unchanged by it.
    expect(_drawer_msgs(page, "user")).to_have_count(1)
    expect(_drawer_msgs(page, "assistant").last).to_contain_text("Page reply", timeout=15000)


def test_a_later_message_carries_the_agent_tab_it_was_sent_from(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _ready_with_reply(base, "Tab reply")
    _boot(page, base, "agents")
    _chat_with(page, "first", "Tab reply")
    _nav.set_route(page, f"agents/{_nav.seg(agent)}/tools")
    expect(page.locator("#main-content .editor-title")).to_have_text(agent, timeout=8000)
    _send(page, "second")
    expect(_drawer_msgs(page, "assistant")).to_have_count(2, timeout=15000)
    pages = [f["page"] for f in _frames(page, "message")]
    assert pages == [{"destination": "agents", "item": agent, "item_name": agent, "tab": "tools"}]
    assert [f["page"] for f in _frames(page, "start_session")] == [{"destination": "agents"}]
    expect(page.locator(CHIP)).to_have_text(["Agents", f"Agents › {agent} › Tools"])


def test_a_queued_message_carries_the_page_it_was_queued_on(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    _ready_with_reply(base, "Held reply", delay_ms=2500)
    _boot(page, base, "library/mcp/~new")
    _open_drawer(page)
    _send(page, "one")
    expect(page.locator(f'{DRAWER} [data-testid="turn-work"]')).to_be_visible(timeout=8000)
    _send(page, "two")  # held: queued on page A (the new MCP server editor)
    expect(page.locator(f'{DRAWER} [data-testid="gg-pending-queued"]')).to_have_count(1)
    _nav.open_destination(page, "settings")  # page B, before the turn ends
    _nav.expect_route(page, "settings/appearance", timeout=8000)
    expect(_drawer_msgs(page, "assistant")).to_have_count(2, timeout=25000)
    messages = _frames(page, "message")
    assert [f["message"] for f in messages] == ["two"]
    assert messages[0]["page"] == MCP_NEW_PAGE, "the page captured at queue time, not at send time"
    expect(page.locator(CHIP)).to_have_text([MCP_NEW_LINE, MCP_NEW_LINE])


def test_the_chip_survives_a_reload_and_shows_in_chats_and_a_chats_chat_has_none(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _ready_with_reply(base, "Chip reply")
    _boot(page, base, "library/mcp/~new")
    _open_drawer(page)
    _send(page, "hello there")
    expect(page.locator(CHIP)).to_have_text(MCP_NEW_LINE, timeout=15000)
    sid = _wait_joined(page)
    page.reload()
    _wait_socket(page)
    _open_drawer(page)
    expect(page.locator(CHIP)).to_have_text(MCP_NEW_LINE, timeout=10000)
    assert _chip_precedes_its_bubble(page)
    # The conversation opened in Chats shows the same chip, with no hook.
    page.locator(OPEN_IN_CHATS).click()
    _nav.expect_route(page, f"chats/{sid}", timeout=8000)
    page.wait_for_function(_chats_joined_js(sid), timeout=10000)
    chip = page.locator('#main-content [data-testid="message-context"]')
    expect(chip).to_have_text(MCP_NEW_LINE, timeout=8000)
    expect(_chats.messages(page, "user")).to_have_count(1)
    # A conversation started in Chats has none.
    _chats.start_chat(page, agent)
    _chats.send_first(page, "chats only")
    expect(_chats.messages(page, "assistant").last).to_be_visible(timeout=10000)
    expect(page.locator('#main-content [data-testid="message-context"]')).to_have_count(0)


def test_a_refused_turn_leaves_no_chip_on_the_next_message(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    _ready_with_reply(base, "Fine reply")
    page.add_init_script(_DROP)
    _boot(page, base, "library/mcp/~new")
    _open_drawer(page)
    # [not ready, unheard]: the server turns GleepGlorp off; the window drops the push.
    page.evaluate("() => { window.__drop = ['gleepglorp_changed', 'config_changed']; }")
    _put(base, enabled=False)
    _send(page, "refused")
    expect(page.locator(EMPTY)).to_be_visible(timeout=8000)  # start_failed: pending again
    expect(page.locator(CHIP)).to_have_count(0)
    # [ready again]: the next message gets exactly one chip, on its own bubble.
    provider = seed_mock_provider(base, name="gg-mock-2", config={"response": {"content": "Ok"}})
    _put(base, provider_config_id=provider, model="mock-default")
    _send(page, "accepted")
    expect(page.locator(CHIP)).to_have_count(1, timeout=15000)
    expect(page.locator(CHIP)).to_have_text(MCP_NEW_LINE)
    expect(_drawer_msgs(page, "user")).to_have_count(1)
    assert _chip_precedes_its_bubble(page)


def test_a_malformed_page_is_refused_and_leaves_no_chip_on_the_next_message(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    _ready_with_reply(base, "Fine reply")
    _boot(page, base, "library/mcp/~new")
    _open_drawer(page)
    sid = _chat_with(page, "start", "Fine reply")
    expect(page.locator(CHIP)).to_have_count(1)
    # One send with a malformed page (a section over its cap, a shape fault).
    page.evaluate(
        "() => { window.__realParse = App.router.parse;"
        " App.router.parse = () => ({ destination: 'library', section: 'x'.repeat(100) }); }"
    )
    _send(page, "bad page")
    expect(page.locator(f'{DRAWER} [data-testid="message"].ui-message--system')).to_contain_text(
        "Malformed page context.", timeout=8000
    )
    page.evaluate("() => { App.router.parse = window.__realParse; }")
    expect(page.locator(CHIP)).to_have_count(1)
    assert _drawer_session(page) == sid
    _send(page, "good page")
    expect(page.locator(CHIP)).to_have_count(2, timeout=15000)
    assert _chip_precedes_its_bubble(page, 1)
    # The refused bubble ("bad page") has no chip: the first chip belongs to "start".
    assert page.evaluate(
        """() => { const c = document.querySelectorAll(
            '#gleepglorp-drawer [data-testid="message-context"]');
          return c[1].nextElementSibling.textContent.indexOf('good page') !== -1; }"""
    )


def test_every_route_the_drawer_can_be_on_gives_a_descriptor_the_server_accepts(
    app_with_agent: SeededApp, page: Page
) -> None:
    from the_one.gleepglorp.page import build_line, validate_descriptor

    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _ready(app_with_agent)
    _boot(page, base, "agents")
    tabs = ["general", "rules-and-notes", "knowledge", "tools", "routines", "self-configuration"]
    routes = ["agents", "agents/~new", f"agents/{_nav.seg(agent)}"]
    routes += [f"agents/{_nav.seg(agent)}/{t}" for t in tabs]
    routes.append("library")
    for group in ["providers", "knowledge", "mcp", "connectors", "secrets"]:
        routes.append(f"library/{group}/~new")
    routes.append(f"library/providers/{app_with_agent.provider_id}")
    for section in [
        "gleepglorp",
        "appearance",
        "date-and-time",
        "prompts",
        "encryption",
        "tools",
        "knowledge-indexing",
    ]:
        routes.append(f"settings/{section}")
    routes.append("settings/tools/web_search")
    for route in routes:
        _nav.set_route(page, route)
        page.wait_for_function(
            "(r) => App.router.current() && App.router.current().route.indexOf(r) === 0",
            arg=route.split("/")[0],
            timeout=8000,
        )
        page.wait_for_timeout(150)
        d = page.evaluate("() => App.gleepglorpDrawerChat.pageContext()")
        assert d is not None, route
        checked, error = validate_descriptor(d)
        assert error is None, (route, d, error)
        assert build_line(checked), route
