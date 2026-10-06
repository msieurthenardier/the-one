"""Reconnect while starting re-sends ``start_session``; while joined it re-joins.

M25 F4 leg 3b (DD1, AC8) inverted this file, renamed from
``test_flow_chat_start_recovery.py``: that file pinned squawk 0111's bounded
10s timer, which re-sent a stalled ``new_session`` on an OPEN socket. The timer
and ``new_session`` are gone. A first send is one idempotent ``start_session``
with a client-generated id, and only a socket CLOSE triggers a re-send:

* **starting** -- at ``onopen`` the client re-sends the SAME ``start_session``
  (same id, same payload; never ``join``). The server joins or creates it
  exactly once, and delivers the first message exactly once.
* **joined** -- the first ``session_list`` on the fresh socket re-joins the
  session when it is still listed, else goes idle with a notice (never a
  ``join`` of an unknown id, and never a plain message on an unbound socket,
  either of which would create a default-agent session).

A lost reply on an open socket is deliberately no longer recovered (the server
always replies; squawk 0111's corrective action records this).

Falls in the ``chats`` browser lane (``test_flow_chat*``).
"""

from __future__ import annotations

import time
from typing import Any

import httpx
import pytest
from browser import _chats, _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

USER_MSG = '[data-testid="message"].user'
ASSISTANT_MSG = '[data-testid="message"].assistant'
REPLY = "Mock response from the mock provider."

# Drops the FIRST start_session frame the page sends (the server never sees
# it) and counts every start_session attempt.
_DROP_FIRST_START = """
(() => {
  window.__startSends = 0;
  const orig = WebSocket.prototype.send;
  WebSocket.prototype.send = function (data) {
    try {
      if (JSON.parse(data).action === 'start_session') {
        window.__startSends += 1;
        if (window.__startSends === 1) return;
      }
    } catch (e) { /* not JSON */ }
    return orig.call(this, data);
  };
})();
"""

# Swallows the FIRST session_joined the page receives: the server created the
# session, but the client never hears it (it stays starting).
_SWALLOW_FIRST_JOINED = """
(() => {
  window.__joinedSwallowed = 0;
  const desc = Object.getOwnPropertyDescriptor(WebSocket.prototype, 'onmessage');
  Object.defineProperty(WebSocket.prototype, 'onmessage', {
    configurable: true,
    get() { return desc.get.call(this); },
    set(fn) {
      desc.set.call(this, typeof fn !== 'function' ? fn : (e) => {
        let joined = false;
        try { joined = JSON.parse(e.data).type === 'session_joined'; } catch (x) { /* ignore */ }
        if (joined && window.__joinedSwallowed === 0) { window.__joinedSwallowed = 1; return; }
        fn.call(this, e);
      });
    },
  });
})();
"""


def _sessions(base: str) -> list[dict[str, Any]]:
    r = httpx.get(f"{base}/api/chat/sessions", headers=auth_headers_for(base), timeout=5)
    r.raise_for_status()
    return r.json()


def _user_messages(base: str, sid: str) -> list[str]:
    r = httpx.get(f"{base}/api/chat/sessions/{sid}", headers=auth_headers_for(base), timeout=5)
    r.raise_for_status()
    out = []
    for m in r.json().get("messages", []):
        if m.get("role") == "user":
            c = m.get("content")
            out.append(c if isinstance(c, str) else str(c))
    return out


def _wait(page: Page, predicate, timeout: float = 10.0, what: str = "condition") -> Any:
    """Poll *predicate*, sleeping through the page so Playwright's sync API
    keeps dispatching its events (``chat_frames`` lists fill from them; a
    plain ``time.sleep`` would freeze them)."""
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = predicate()
        if last:
            return last
        page.wait_for_timeout(100)
    raise AssertionError(f"timed out waiting for {what} (last={last!r})")


def _state(page: Page) -> str:
    return (_chats.session_state(page) or {}).get("name")


def _close_socket(page: Page) -> None:
    page.evaluate("App.areas.find(a => a.id === 'chat')._ws().close()")


def _wait_reconnected(page: Page, timeout: float = 10000) -> None:
    page.wait_for_function(
        "() => { const ws = App.areas.find(a => a.id === 'chat')._ws();"
        " return ws && ws.readyState === WebSocket.OPEN; }",
        timeout=timeout,
    )


def _action(f: dict[str, Any]) -> str:
    return f.get("action", "message")


def test_start_session_that_never_reached_the_server_is_resent_on_reconnect(
    app_with_agent: SeededApp, page: Page
) -> None:
    """The first send's start_session is dropped, then the socket closes. At
    the reconnect's onopen the SAME start_session goes out (never `join`): one
    session, the first message delivered once. A send in the reconnect gap is
    held (never a plain message on an unbound socket) and lands in the same
    session after the first turn."""
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    page.add_init_script(_DROP_FIRST_START)
    wire = _chats.chat_frames(page)
    _nav.goto(page, base, "chats")
    _chats.start_chat(page, agent)

    page.locator('[data-testid="chat-input"]').fill("hello")
    page.locator('[data-testid="chat-input"]').press("Enter")
    page.wait_for_function("window.__startSends === 1")
    assert _state(page) == "starting"
    expect(page.locator(USER_MSG)).to_have_text(["hello"])
    page.wait_for_timeout(500)
    assert _sessions(base) == []  # the server never saw it
    cid = (_chats.session_state(page) or {})["clientId"]

    _close_socket(page)
    # The reconnect gap: a second Send is held in the starting chat's slot.
    page.locator('[data-testid="chat-input"]').fill("second")
    page.locator('[data-testid="chat-input"]').press("Enter")
    expect(page.locator('[data-testid="pending-queued"]')).to_be_visible()
    assert _state(page) == "starting"

    _wait_reconnected(page)
    page.wait_for_function(
        "() => App.areas.find(a => a.id === 'chat')._sessionState().name === 'joined'",
        timeout=10000,
    )
    assert page.evaluate("window.__startSends") == 2
    assert _chats.current_session_id(page) == cid
    _nav.expect_route(page, f"chats/{cid}")

    # The held message goes out after the first turn, on the joined path.
    expect(page.locator(USER_MSG)).to_have_text(["hello", "second"], timeout=10000)
    expect(page.locator(ASSISTANT_MSG)).to_have_count(2, timeout=10000)
    sessions = _wait(page, lambda: _sessions(base), what="the session")
    assert [s["id"] for s in sessions] == [cid]
    assert _wait(
        page,
        lambda: _user_messages(base, cid) if len(_user_messages(base, cid)) >= 2 else None,
        what="both messages persisted",
    ) == ["hello", "second"]
    assert len(_sessions(base)) == 1
    sent = [(_action(f), f.get("session_id")) for f in wire if _action(f) != "list_sessions"]
    # On the wire: the re-sent start (the dropped one never left), then the
    # held message after the first turn's `done`. Never a `join` while
    # starting, never a plain message before the start.
    assert sent == [("start_session", cid), ("message", None)], sent


def test_start_session_that_reached_the_server_is_resent_idempotently(
    app_with_agent: SeededApp, page: Page
) -> None:
    """The server creates the session but its session_joined never reaches the
    client; the socket closes. The re-sent start_session joins the existing
    session: still one session, the first message delivered once, and the
    re-bound socket carries the next send into it."""
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    page.add_init_script(_SWALLOW_FIRST_JOINED)
    wire = _chats.chat_frames(page, actions=("start_session", "join", "leave"))
    _nav.goto(page, base, "chats")
    _chats.start_chat(page, agent)

    page.locator('[data-testid="chat-input"]').fill("hello")
    page.locator('[data-testid="chat-input"]').press("Enter")
    page.wait_for_function("window.__joinedSwallowed === 1", timeout=10000)
    cid = (_chats.session_state(page) or {})["clientId"]
    assert _state(page) == "starting"
    # The server has the session (and runs the turn); the client still waits.
    _wait(page, lambda: [s for s in _sessions(base) if s["id"] == cid], what="the server session")

    _close_socket(page)
    _wait_reconnected(page)
    page.wait_for_function(
        "() => App.areas.find(a => a.id === 'chat')._sessionState().name === 'joined'",
        timeout=10000,
    )
    assert _chats.current_session_id(page) == cid
    assert [(f["action"], f["session_id"]) for f in wire] == [
        ("start_session", cid),
        ("start_session", cid),
    ]
    expect(page.locator(USER_MSG)).to_have_text(["hello"])
    expect(page.locator(ASSISTANT_MSG)).to_have_text([REPLY], timeout=10000)
    assert _wait(page, lambda: _user_messages(base, cid), what="the first message") == ["hello"]

    # Re-bound: a send after the reconnect lands in the same session.
    _chats.send_first(page, "after")
    expect(page.locator(ASSISTANT_MSG)).to_have_count(2, timeout=10000)
    assert _wait(
        page,
        lambda: _user_messages(base, cid) if len(_user_messages(base, cid)) >= 2 else None,
        what="the second message persisted",
    ) == ["hello", "after"]
    assert [s["id"] for s in _sessions(base)] == [cid]


def test_reconnect_while_joined_rejoins_the_session(app_with_agent: SeededApp, page: Page) -> None:
    """Joined, the socket drops: a send in the gap keeps its text, the first
    session_list on the fresh socket re-joins, and the next send lands in the
    same session (it used to reach an unbound socket and auto-create a
    default-agent session)."""
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    wire = _chats.chat_frames(page, actions=("start_session", "join", "leave"))
    _nav.goto(page, base, "chats")
    _chats.start_chat(page, agent)
    sid = _chats.send_first(page, "hello")
    expect(page.locator(ASSISTANT_MSG)).to_have_count(1, timeout=10000)
    expect(page.locator('[data-testid="chat-send-btn"]')).to_be_enabled(timeout=10000)
    wire.clear()

    _close_socket(page)
    box = page.locator('[data-testid="chat-input"]')
    box.fill("in the gap")
    box.press("Enter")
    expect(box).to_have_value("in the gap")  # kept, not sent
    _wait_reconnected(page)
    # The re-join goes out on the fresh socket (the state was joined before
    # the drop too, so wait for the frame first, then for its reply).
    _wait(
        page,
        lambda: [(f["action"], f.get("session_id")) for f in wire] == [("join", sid)],
        what="exactly one re-join",
    )
    page.wait_for_function(
        "(id) => { const st = App.areas.find(a => a.id === 'chat')._sessionState();"
        " return st.name === 'joined' && st.id === id; }",
        arg=sid,
        timeout=10000,
    )
    box.press("Enter")
    expect(page.locator(USER_MSG)).to_have_text(["hello", "in the gap"], timeout=10000)
    expect(page.locator(ASSISTANT_MSG)).to_have_count(2, timeout=10000)
    assert _wait(
        page,
        lambda: _user_messages(base, sid) if len(_user_messages(base, sid)) >= 2 else None,
        what="the second message persisted",
    ) == ["hello", "in the gap"]
    assert [s["id"] for s in _sessions(base)] == [sid]


def test_reconnect_after_the_joined_session_was_deleted_goes_idle(
    app_with_agent: SeededApp, page: Page
) -> None:
    """The joined session is deleted (REST) while the socket is down: the
    reconnect goes idle with a notice, never joins the unknown id, and no
    default-agent session appears."""
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    wire = _chats.chat_frames(page, actions=("start_session", "join", "leave"))
    _nav.goto(page, base, "chats")
    _chats.start_chat(page, agent)
    sid = _chats.send_first(page, "hello")
    expect(page.locator(ASSISTANT_MSG)).to_have_count(1, timeout=10000)
    expect(page.locator('[data-testid="chat-send-btn"]')).to_be_enabled(timeout=10000)
    wire.clear()

    _close_socket(page)
    r = httpx.delete(f"{base}/api/chat/sessions/{sid}", headers=auth_headers_for(base), timeout=5)
    assert r.status_code in (200, 204), r.text
    _wait_reconnected(page)
    page.wait_for_function(
        "() => App.areas.find(a => a.id === 'chat')._sessionState().name === 'idle'",
        timeout=10000,
    )
    expect(_chats.welcome(page)).to_be_visible(timeout=8000)
    expect(_chats.welcome(page).get_by_role("status")).to_have_text(
        "That conversation no longer exists"
    )
    assert _chats.current_session_id(page) is None
    _nav.expect_route(page, "chats")
    page.wait_for_timeout(500)
    assert wire == []  # no join of the deleted id
    assert _sessions(base) == []  # nothing auto-created
