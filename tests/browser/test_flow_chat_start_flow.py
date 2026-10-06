"""The chat start flow on the existing DOM (M25 F4 leg 3b, DD1, DD2).

A pick is the route ``#chats/~new/{agent}``: a *pending* chat with no session
(only a ``leave`` goes out). The first send is one ``start_session``; the first
turn behaves like any later turn. The session state gates every inbound frame,
so nothing from a session the socket left can reach the pending chat.

What this file pins (the leg's acceptance criteria):

* AC3   frames from the previous session never reach a pending chat, and a late
        ``session_joined`` from a cold-load auto-join cannot take it over;
* AC6   ``/reset`` in a pending chat is a client-side notice; a send with the
        socket closed keeps its text; Stop while starting cancels the new
        session's first turn;
* AC7   the first turn behaves like any turn (bubble, thinking, Stop, the hold
        chip, the reply) and creates exactly one session;
* AC9   leaving Chats while starting, then the rail back, keeps the session;
* AC9b  bare ``#chats`` while pending keeps the pending chat;
* AC12  the hydrate of ``#chats/~new/{agent}`` validates and heals; a re-pick
        on a ``~new`` route replaces, a first pick pushes;
* AC2   a ``start_failed`` restores the composer text and the staged images.

Falls in the ``chats`` browser lane (``test_flow_chat*``).
"""

from __future__ import annotations

import base64
import time
from typing import Any

import httpx
import pytest
from browser import _chats, _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp, seed_mock_agent, seed_mock_provider, seed_session
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

INPUT = '[data-testid="chat-input"]'
SEND = '[data-testid="chat-send-btn"]'
STOP = '[data-testid="chat-stop-btn"]'
USER_MSG = '[data-testid="message"].user'
ASSISTANT_MSG = '[data-testid="message"].assistant'
THINKING = '[data-testid="thinking-indicator"]'
CHIP = '[data-testid="pending-queued"]'
MESSAGES = ".area-chat .messages"

# Holds every session_joined for window.__delayJoined ms, and queues every
# frame behind it, delivering them IN ORDER afterwards (a reordering delay
# would be a harness artefact: the server never reorders a socket's frames).
_DELAY_JOINED = """
(() => {
  if (window.__delayJoined === undefined) window.__delayJoined = %d;
  const desc = Object.getOwnPropertyDescriptor(WebSocket.prototype, 'onmessage');
  Object.defineProperty(WebSocket.prototype, 'onmessage', {
    configurable: true,
    get() { return desc.get.call(this); },
    set(fn) {
      if (typeof fn !== 'function') { desc.set.call(this, fn); return; }
      const sock = this;
      const queue = [];
      let holding = false;
      desc.set.call(this, (e) => {
        if (holding) { queue.push(e); return; }
        let joined = false;
        try { joined = JSON.parse(e.data).type === 'session_joined'; } catch (x) { /* ignore */ }
        const ms = window.__delayJoined || 0;
        if (joined && ms > 0) {
          holding = true;
          queue.push(e);
          setTimeout(() => {
            holding = false;
            queue.splice(0).forEach(ev => fn.call(sock, ev));
          }, ms);
          return;
        }
        fn.call(sock, e);
      });
    },
  });
})();
"""


def _sessions(base: str) -> list[dict[str, Any]]:
    r = httpx.get(f"{base}/api/chat/sessions", headers=auth_headers_for(base), timeout=5)
    r.raise_for_status()
    return r.json()


def _state(page: Page) -> dict[str, Any]:
    return _chats.session_state(page) or {}


def _wait_state(page: Page, name: str, timeout: float = 10000) -> None:
    page.wait_for_function(
        "n => App.areas.find(a => a.id === 'chat')._sessionState().name === n",
        arg=name,
        timeout=timeout,
    )


def _seq(page: Page) -> int:
    return page.evaluate("history.state && history.state.seq")


def _slow_agent(base: str, name: str = "slow-agent", delay_ms: int = 400) -> str:
    provider = seed_mock_provider(
        base,
        name=f"{name}-provider",
        config={"stream_chunks": ["one ", "two ", "three"], "delay_ms": delay_ms},
    )
    return seed_mock_agent(base, provider, name=name)


# ── AC3: the frame gate in the real chat area ────────────────────────────────

_FEED_JS = """
(oldId) => {
  const ws = App.areas.find(a => a.id === 'chat')._ws();
  const feed = (f) => ws.onmessage({ data: JSON.stringify(f) });
  feed({ type: 'user', content: 'LEAK user' });
  feed({ type: 'assistant_chunk', content: 'LEAK chunk' });
  feed({ type: 'assistant', content: 'LEAK assistant' });
  feed({ type: 'thinking', thinking: 'LEAK thinking' });
  feed({ type: 'tool_call', name: 'leak', arguments: { a: 1 }, tool_call_id: 't1' });
  feed({ type: 'tool_result', content: 'LEAK tool', tool_call_id: 't1' });
  feed({ type: 'system', content: 'LEAK system' });
  feed({ type: 'usage', input_tokens: 9, output_tokens: 9, context_tokens: 9 });
  feed({ type: 'auth_required', source_id: 'leak', source_name: 'LEAK auth' });
  feed({ type: 'done' });
  feed({ type: 'cancelled' });
  feed({ type: 'session_joined', session_id: oldId, status: 'ok', agent_name: 'x',
         history: [{ type: 'user', content: 'LEAK history' }], is_processing: true });
}
"""


def test_frames_from_the_previous_session_never_reach_a_pending_chat(
    app_with_provider: SeededApp, page: Page
) -> None:
    base = app_with_provider.base_url
    slow = _slow_agent(base)
    other = seed_mock_agent(base, app_with_provider.provider_id, name="other-agent")
    frames = _chats.chat_frames(page, actions=("leave", "start_session", "join"))
    _nav.goto(page, base, "chats")
    _chats.start_chat(page, slow)
    old = _chats.send_first(page, "stream please")
    # Mid-turn on the old session: pick another agent.
    expect(page.locator(ASSISTANT_MSG)).to_have_count(1, timeout=10000)
    _chats.pick(page, other)  # the agent picker (M25 F4 L4a; was the dropdown)
    _wait_state(page, "pending")
    assert [f["action"] for f in frames][-1] == "leave"
    # The old session's real remaining chunks (and its done) never render.
    page.wait_for_timeout(1500)
    expect(page.locator(f"{MESSAGES} [data-testid='message']")).to_have_count(0)
    # Fed frames of every session-scoped kind, plus a late session_joined(old).
    page.evaluate(_FEED_JS, old)
    page.wait_for_timeout(200)
    assert "LEAK" not in (page.locator(MESSAGES).text_content() or "")
    expect(page.locator(".login-required-btn")).to_have_count(0)
    assert _state(page)["name"] == "pending" and _state(page)["agent"] == other
    _nav.expect_route(page, f"chats/~new/{_nav.seg(other)}")
    expect(_chats.pending_row(page)).to_have_count(1)
    expect(page.locator(SEND)).to_be_enabled()


def test_a_late_cold_load_join_cannot_take_over_a_pending_chat(
    app_with_agent: SeededApp, page: Page
) -> None:
    """A cold ``#chats`` auto-joins the most recent session; its session_joined
    is slow. A pick in that window leaves (after the join on the socket), and
    the late session_joined is dropped: the chat stays pending."""
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    old = seed_session(
        base,
        agent,
        "Old chat",
        "2026-01-01T00:00:00+00:00",
        messages=[{"role": "user", "content": "OLD HISTORY"}],
    )
    page.add_init_script(_DELAY_JOINED % 1500)
    frames = _chats.chat_frames(page, actions=("leave", "start_session", "join"))
    _nav.goto(page, base, "chats")
    _wait_state(page, "joining")
    assert _state(page)["id"] == old
    # The pick lands while the join is still in flight (the picker, M25 F4 L4a;
    # `start_chat` would wait for the join to settle first).
    _chats.pick(page, agent)
    _wait_state(page, "pending")
    page.wait_for_timeout(2500)  # outlast the held session_joined(old)
    assert _state(page)["name"] == "pending"
    assert [(f["action"], f.get("session_id")) for f in frames] == [("join", old), ("leave", None)]
    assert "OLD HISTORY" not in (page.locator(MESSAGES).text_content() or "")
    _nav.expect_route(page, f"chats/~new/{_nav.seg(agent)}")
    expect(_chats.pending_row(page)).to_have_count(1)
    expect(_chats.chat_row(page, old)).to_be_visible()
    expect(_chats.chat_row(page, old)).not_to_have_attribute("aria-current", "page")


# ── AC7: the first turn behaves like any turn ────────────────────────────────


def test_first_turn_behaves_like_any_turn(app_with_provider: SeededApp, page: Page) -> None:
    base = app_with_provider.base_url
    agent = _slow_agent(base)
    _nav.goto(page, base, "chats")
    _chats.start_chat(page, agent)
    assert _sessions(base) == []
    box = page.locator(INPUT)
    box.fill("first")
    box.press("Enter")
    # Optimistic bubble, thinking, Stop, Send disabled -- through the join.
    expect(page.locator(USER_MSG)).to_have_text(["first"])
    expect(page.locator(THINKING)).to_be_visible()
    expect(page.locator(STOP)).to_be_visible()
    expect(page.locator(SEND)).to_be_disabled()
    _wait_state(page, "joined")
    sid = _chats.current_session_id(page)
    _nav.expect_route(page, f"chats/{_nav.seg(sid)}")
    expect(page.locator(USER_MSG)).to_have_text(["first"])  # kept by the empty-history join
    expect(page.locator(STOP)).to_be_visible()
    # A second Send during the first turn is held (the chip), not sent.
    box.fill("queued")
    box.press("Enter")
    expect(page.locator(CHIP)).to_be_visible()
    expect(page.locator(USER_MSG)).to_have_count(1)
    # The reply, then the held message goes out as the next turn.
    expect(page.locator(ASSISTANT_MSG).first).to_have_text("one two three", timeout=15000)
    expect(page.locator(USER_MSG)).to_have_text(["first", "queued"], timeout=15000)
    expect(page.locator(CHIP)).to_have_count(0)
    expect(page.locator(ASSISTANT_MSG)).to_have_count(2, timeout=15000)
    expect(page.locator(STOP)).to_be_hidden(timeout=15000)
    expect(page.locator(SEND)).to_be_enabled()
    assert [s["id"] for s in _sessions(base)] == [sid]  # exactly one new session


# ── AC6: /reset, a closed socket, Stop while starting ────────────────────────


def test_reset_in_a_pending_chat_is_a_client_side_notice(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    frames = _chats.chat_frames(page)
    _nav.goto(page, base, "chats")
    _chats.start_chat(page, agent)
    box = page.locator(INPUT)
    box.fill("/reset")
    box.press("Enter")
    expect(page.locator(f"{MESSAGES} .msg.system")).to_have_text(
        "Send a message to start the chat first"
    )
    page.wait_for_timeout(300)
    assert [f for f in frames if f.get("action", "message") in ("message", "start_session")] == []
    assert _state(page)["name"] == "pending"
    assert _sessions(base) == []


def test_send_in_a_pending_chat_with_the_socket_closed_keeps_the_text(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    frames = _chats.chat_frames(page, actions=("start_session",))
    _nav.goto(page, base, "chats")
    _chats.start_chat(page, agent)
    page.evaluate("App.areas.find(a => a.id === 'chat')._ws().close()")
    box = page.locator(INPUT)
    box.fill("not yet")
    box.press("Enter")
    expect(box).to_have_value("not yet")
    assert _state(page)["name"] == "pending"
    page.wait_for_function(
        "() => App.areas.find(a => a.id === 'chat')._ws().readyState === WebSocket.OPEN",
        timeout=10000,
    )
    page.wait_for_timeout(300)
    assert frames == [] and _state(page)["name"] == "pending"  # reconnect: nothing to do
    sid = _chats.send_first(page, "now")
    assert [s["id"] for s in _sessions(base)] == [sid]


def test_stop_while_starting_cancels_the_first_turn(
    app_with_provider: SeededApp, page: Page
) -> None:
    """Stop while starting (the client has not seen session_joined yet) sends
    `cancel` after `start_session` on the socket, so the server cancels the
    new session's first turn.

    The click waits until the server has created the session (its turn is
    then under way): a `cancel` the server processes before the spawned turn's
    first step gets no `cancelled` reply at all (squawk 0120, which predates
    this flight and affects a plain message the same way)."""
    base = app_with_provider.base_url
    agent = _slow_agent(base, delay_ms=600)
    page.add_init_script(_DELAY_JOINED % 0)
    frames = _chats.chat_frames(page, actions=("start_session", "cancel"))
    _nav.goto(page, base, "chats")
    _chats.start_chat(page, agent)
    page.evaluate("window.__delayJoined = 2000")
    box = page.locator(INPUT)
    box.fill("stop me")
    box.press("Enter")
    expect(page.locator(STOP)).to_be_visible()
    deadline = time.monotonic() + 5
    while not _sessions(base) and time.monotonic() < deadline:
        page.wait_for_timeout(50)
    page.wait_for_timeout(300)
    assert _state(page)["name"] == "starting"  # session_joined is still held
    page.locator(STOP).click()
    _wait_state(page, "joined")
    # The cancel went out after the start, so it bound to the new session.
    assert [f["action"] for f in frames] == ["start_session", "cancel"]
    sid = frames[0]["session_id"]
    expect(page.locator(STOP)).to_be_hidden(timeout=10000)
    expect(page.locator(SEND)).to_be_enabled()
    page.wait_for_timeout(1500)  # the turn would have finished by now
    assert "three" not in (page.locator(MESSAGES).text_content() or "")
    assert [s["id"] for s in _sessions(base)] == [sid]


# ── AC2: start_failed restores the composer ──────────────────────────────────

_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def test_start_failed_restores_the_text_and_the_staged_image(
    app_with_provider: SeededApp, page: Page
) -> None:
    """The agent is deleted after the pick: the server answers start_failed.
    The bubble goes, the text and the image come back, the error shows in the
    pending pane, and nothing was created."""
    base = app_with_provider.base_url
    agent = seed_mock_agent(base, app_with_provider.provider_id, name="doomed")
    _nav.goto(page, base, "chats")
    _chats.start_chat(page, agent)
    page.locator('[data-testid="chat-image-input"]').set_input_files(
        files=[{"name": "dot.png", "mimeType": "image/png", "buffer": _PNG}]
    )
    expect(page.locator('[data-testid="chat-image-input"]')).to_have_attribute(
        "data-staged", "true"
    )
    r = httpx.delete(f"{base}/api/agents/{agent}", headers=auth_headers_for(base), timeout=5)
    assert r.status_code in (200, 204), r.text
    box = page.locator(INPUT)
    box.fill("will fail")
    box.press("Enter")
    expect(page.locator(f"{MESSAGES} .msg.system")).to_contain_text(
        "Cannot start chat", timeout=8000
    )
    _wait_state(page, "pending")
    expect(page.locator(USER_MSG)).to_have_count(0)
    expect(box).to_have_value("will fail")
    expect(page.locator('[data-testid="chat-attachment"]')).to_have_count(1)
    expect(page.locator(THINKING)).to_have_count(0)
    expect(page.locator(STOP)).to_be_hidden()
    expect(page.locator(SEND)).to_be_enabled()
    assert _sessions(base) == []


# ── AC9 / AC9b: the rail and bare #chats ─────────────────────────────────────


def test_leaving_chats_while_starting_and_coming_back_keeps_the_session(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    page.add_init_script(_DELAY_JOINED % 0)
    frames = _chats.chat_frames(page, actions=("leave", "start_session", "join"))
    _nav.goto(page, base, "chats")
    _chats.start_chat(page, agent)
    page.evaluate("window.__delayJoined = 1200")
    box = page.locator(INPUT)
    box.fill("hello")
    box.press("Enter")
    assert _state(page)["name"] == "starting"
    _nav.open_destination(page, "settings")
    _nav.expect_route(page, "settings/appearance")
    _wait_state(page, "joined")  # landed while away; its sync was dropped
    cid = _state(page)["id"]
    assert page.evaluate("App.router.lastRoute('chats')") == f"chats/~new/{_nav.seg(agent)}"
    _nav.open_destination(page, "chats")
    _nav.expect_route(page, f"chats/{_nav.seg(cid)}")
    st = _state(page)
    assert st["name"] == "joined" and st["id"] == cid
    assert st["startedFrom"] == {"agent": agent, "cid": cid}
    expect(page.locator(USER_MSG)).to_have_text(["hello"])
    expect(_chats.pending_row(page)).to_have_count(0)
    assert [f["action"] for f in frames] == ["start_session"]  # no leave, no new pending
    assert [s["id"] for s in _sessions(base)] == [cid]
    # A deliberate New chat is still a pick (the rail-restore rule is not):
    # the Chats list's New chat, then the same agent in the picker (M25 F4
    # L4b retired the header's New Chat, which picked the current agent).
    _chats.pick(page, agent)
    _wait_state(page, "pending")
    _nav.expect_route(page, f"chats/~new/{_nav.seg(agent)}")


def test_bare_chats_keeps_the_pending_chat(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _nav.goto(page, base, "chats")
    _chats.start_chat(page, agent)
    _nav.open_destination(page, "chats")  # the current destination's link: bare #chats
    _nav.expect_route(page, f"chats/~new/{_nav.seg(agent)}")
    st = _state(page)
    assert st["name"] == "pending" and st["agent"] == agent
    expect(_chats.pending_row(page)).to_have_count(1)


# ── AC12: hydrate, validate, heal; push and replace ──────────────────────────


def test_new_chat_route_hydrates_and_heals(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    # Cold load of a known agent: pending at once, validated, ready to type.
    _nav.goto(page, base, f"chats/~new/{_nav.seg(agent)}")
    _wait_state(page, "pending")
    _chats.expect_chat(page, agent)
    expect(page.locator(INPUT)).to_be_enabled()
    _nav.expect_route(page, f"chats/~new/{_nav.seg(agent)}")
    assert _sessions(base) == []

    # Unknown, `default`, malformed: each heals to #chats and the idle rules
    # (no sessions: the welcome, i.e. the empty state: idle with no chat to
    # auto-join), cold (a reload) and warm (a traversal).
    for bad in ("ghost", "default", "%E0%A4%A"):
        _nav.set_route(page, f"chats/~new/{bad}")
        _nav.expect_route(page, "chats", timeout=8000)
        _wait_state(page, "idle")
        expect(_chats.welcome(page)).to_be_visible()
        page.evaluate(
            "h => history.replaceState(history.state, '', h)", _nav.hash_for(f"chats/~new/{bad}")
        )
        page.reload()
        _nav.expect_route(page, "chats", timeout=8000)
        _wait_state(page, "idle")
        expect(_chats.welcome(page)).to_be_visible()
    # Bare ~new is just Chats.
    _nav.set_route(page, "chats/~new")
    _nav.expect_route(page, "chats")
    assert _sessions(base) == []


def test_a_first_pick_pushes_and_a_re_pick_replaces(
    app_with_provider: SeededApp, page: Page
) -> None:
    base = app_with_provider.base_url
    a = seed_mock_agent(base, app_with_provider.provider_id, name="agent-a")
    b = seed_mock_agent(base, app_with_provider.provider_id, name="agent-b")
    c = seed_mock_agent(base, app_with_provider.provider_id, name="agent-c")
    _nav.goto(page, base, "chats")
    _chats.start_chat(page, a)
    sid = _chats.send_first(page, "hi")
    seq = _seq(page)
    _chats.start_chat(page, b)  # from a session: pushed
    assert _seq(page) == seq + 1
    _chats.start_chat(page, c)  # from a ~new route: replaced
    assert _seq(page) == seq + 1
    _nav.expect_route(page, f"chats/~new/{_nav.seg(c)}")
    expect(page.locator('[data-testid="route-announcer"]')).to_have_text(
        f"Chats — New chat with {c}"
    )
    page.go_back()  # one step back: the session (the pending chat is discarded)
    _nav.expect_route(page, f"chats/{_nav.seg(sid)}")
    _wait_state(page, "joined")
    assert _state(page)["id"] == sid
    expect(_chats.pending_row(page)).to_have_count(0)
