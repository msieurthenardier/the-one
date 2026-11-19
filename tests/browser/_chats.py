"""Chat helpers for browser tests (M25 F4 leg 3a, DD12).

Flight 4 rebuilds Chats in steps that would each touch every test that starts,
joins or inspects a chat.  Tests reach those mechanics through this module
instead of naming the chat surface's selectors, so each step changes the helper
BODIES here rather than every test:

* **Leg 3a** built this seam on the old DOM and the old semantics (the client
  sent ``new_session`` on a pick, so a session existed the moment a start
  returned).
* **Leg 3b** flipped the semantics: a pick opens a *pending* chat (no
  session, the route ``#chats/~new/{agent}``, a ``leave`` frame), and the first
  send creates the session through ``start_session``.  ``start_chat`` returns
  at the pending chat; ``send_first`` creates the session; tests that asserted
  a session right after the start call ``send_first`` first.
* **Leg 4a** replaced the sidebar: the ``agent-select`` dropdown and the old
  history list gave way to the Chats list (``App.ui.listPane``, testid
  ``chats-list``: rows ``chat-row`` with ``data-id``, the pending row with
  ``data-pending``, a delete action ``chat-row-delete``) and the agent picker
  (``agent-picker``, opened by the list's New chat, ``chats-new-btn``).
  ``start_chat`` picks through the picker.
* **Leg 4b (today)** replaced the pane: the welcome's agent list, the header's
  New Chat and its agent badge gave way to the chat header (``chat-header``:
  an ``h1`` title and ``chat-agent-line`` "with {agent}"), the new-chat state
  (``chat-new-state``, with ``chat-pick-different-btn``) and the empty state's
  New chat (``chat-empty-new-btn``) under the kept ``chat-welcome``.
  ``expect_chat`` reads the header; ``new_chat_button`` is the list's New
  chat; ``welcome_item`` and ``agent_badge`` are gone.

The helpers:

* ``start_chat(page, agent)`` -- start a new (pending) chat with *agent* and
  wait until it is ready to type in;
* ``send_first(page, text)`` -- send the chat's first message, wait for the
  session it creates, and return its id;
* ``expect_chat(page, agent, title=None)`` -- the open chat's header shows
  *agent* (and *title*); ``chat_header(page)``, ``chat_title(page)``,
  ``chat_agent_line(page)`` -- its parts;
* ``new_chat_state(page)`` / ``pick_different_button(page)`` -- the pending
  chat's new-chat state and its "Pick a different agent";
  ``empty_new_button(page)`` -- the empty state's New chat;
* ``current_session_id(page)`` -- the chat area's current session id, or None;
* ``session_state(page)`` -- the chat area's session state (``name``, ``id``,
  ``agent``, ``clientId``, ...); ``pending_row(page)`` -- the pending chat's row;
* ``chat_row(page, id)`` / ``open_chat(page, id)`` -- a session's row in the
  Chats list, and opening it; ``chat_rows(page)`` -- every session row;
  ``chat_row_delete(page, id)`` -- a row's delete action;
* ``chats_new_button(page)`` -- the Chats list's New chat;
  ``open_picker(page)`` -- click it and wait for the agent picker;
  ``pick(page, agent)`` -- pick *agent* in the picker (type, then Enter);
  ``picker(page)``, ``picker_search(page)``, ``picker_rows(page)``,
  ``picker_row(page, agent)`` -- the picker's parts;
* ``chat_frames(page)`` -- a live list of the chat WebSocket's sent frames;
* ``welcome(page)`` -- the pane's empty and guidance state;
  ``new_chat_button(page)`` -- the Chats list's New chat (``chats_new_button``).

Since leg 4b this module is subject to ``tests/test_nav_helper.py``'s
retired-selector guard like every other file: the leg 3a chat-seam guard that
fenced ``.chat-welcome-item`` and ``.session-agent-badge`` outside it is gone,
and those fragments (with ``new-chat-btn``) are ``RETIRED_SELECTORS`` entries.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
from browser import _nav
from browser._credential_registry import auth_headers_for
from playwright.sync_api import Locator, Page, expect

# The chat pane (leg 4b): the empty and guidance state, the header and the
# new-chat state.
_WELCOME = '[data-testid="chat-welcome"]'
_EMPTY_NEW_BTN = '[data-testid="chat-empty-new-btn"]'
_HEADER = '[data-testid="chat-header"]'
_AGENT_LINE = '[data-testid="chat-agent-line"]'
_NEW_STATE = '[data-testid="chat-new-state"]'
_PICK_DIFFERENT = '[data-testid="chat-pick-different-btn"]'
# The Chats list and the agent picker (leg 4a).
_CHATS_NEW_BTN = '[data-testid="chats-new-btn"]'
_ROW = '[data-testid="chat-row"]'
_SESSION_ROW = '[data-testid="chat-row"][data-id]'
_PENDING_ROW = '[data-testid="chat-row"][data-pending]'
_ROW_DELETE = '[data-testid="chat-row-delete"]'
_PICKER = '[data-testid="agent-picker"]'
_PICKER_SEARCH = '[data-testid="agent-picker-search"]'
_PICKER_ROW = '[data-testid="agent-picker-row"]'
_INPUT = '[data-testid="chat-input"]'
_USER_MSG = '[data-testid="message"].ui-message--user'

# The chat area's current session id (null before the area is initialised).
_SESSION_ID_JS = (
    "() => { const a = ((window.App && App.areas) || []).find(x => x.id === 'chat');"
    " return (a && a._currentSessionId) || null; }"
)

# The chat area's session state (M25 F4 L3b; null before the area is initialised).
_STATE_JS = (
    "() => { const a = ((window.App && App.areas) || []).find(x => x.id === 'chat');"
    " return a && a._sessionState ? a._sessionState() : null; }"
)

# Settled: the welcome canvas is shown with nothing open, or a chat is open
# (joined, pending or starting). A join still in flight is not settled.
_SETTLED_JS = (
    "() => { const a = ((window.App && App.areas) || []).find(x => x.id === 'chat');"
    " if (!a || !a._sessionState) return null; const st = a._sessionState().name;"
    " if (st === 'joined' || st === 'pending' || st === 'starting') return 'open';"
    " if (st !== 'idle') return null;"
    " const w = document.querySelector('" + _WELCOME + "');"
    " return w && !w.hidden ? 'welcome' : null; }"
)

# Pending with *agent* (the pick landed).
_PENDING_JS = (
    "(agent) => { const a = ((window.App && App.areas) || []).find(x => x.id === 'chat');"
    " if (!a || !a._sessionState) return false; const st = a._sessionState();"
    " return st.name === 'pending' && st.agent === agent; }"
)

# The picker's active option's agent (its search input's aria-activedescendant).
_PICKER_ACTIVE_JS = (
    "(sel) => { const i = document.querySelector(sel);"
    " const id = i && i.getAttribute('aria-activedescendant');"
    " const o = id && document.getElementById(id); return o ? o.dataset.agent : null; }"
)

# Joined to a session other than *before* (the first send's session_joined).
_JOINED_NEW_JS = (
    "(before) => { const a = ((window.App && App.areas) || []).find(x => x.id === 'chat');"
    " if (!a || !a._sessionState) return false; const st = a._sessionState();"
    " return st.name === 'joined' && !!st.id && st.id !== before; }"
)

_JOINED_ID_JS = (
    "(id) => { const a = ((window.App && App.areas) || []).find(x => x.id === 'chat');"
    " if (!a || !a._sessionState) return false; const st = a._sessionState();"
    " return st.name === 'joined' && st.id === id; }"
)


def message_sel(role: str, *modifiers: str) -> str:
    """The CSS selector for a transcript message bubble of *role* (``user``,
    ``assistant``, ``tool`` or ``system``), plus optional modifiers (``api``,
    ``error``, ``peer``, ``operator-only``). The bubble is ``App.ui.message``
    (M31 F6 L05c): the role and modifiers are its ``ui-message--*`` classes; the
    ``message`` testid is unchanged. Every browser test names a bubble through
    this (or :func:`messages`), never through the control's classes."""
    return (
        '[data-testid="message"].ui-message--'
        + role
        + "".join(".ui-message--" + m for m in modifiers)
    )


def messages(page: Page, role: str, *modifiers: str) -> Locator:
    """Every transcript bubble of *role* (see :func:`message_sel`)."""
    return page.locator(message_sel(role, *modifiers))


def turn_groups(page: Page) -> Locator:
    """Every turn work group in the log (``turn-work``, ``App.ui.turnWork``, sortie 16 L02).
    A turn has at most one; a plain reply has none. Tests name a group through these helpers,
    never through the control's classes."""
    return page.locator('[data-testid="turn-work"]')


def working_turns(page: Page) -> Locator:
    """The turn work groups still running (``data-state="working"``): the "in flight" signal
    that replaced the old "Thinking" line."""
    return page.locator('[data-testid="turn-work"][data-state="working"]')


def turn_group(page: Page, nth: int = -1) -> Locator:
    """One turn work group (the last by default; ``nth`` counts from 0)."""
    groups = turn_groups(page)
    return groups.last if nth == -1 else groups.nth(nth)


def turn_state(group: Locator) -> str | None:
    """The group's ``data-state``: ``working``, ``done``, ``stopped``, ``error``,
    ``step-limit`` or ``sign-in``."""
    return group.get_attribute("data-state")


def turn_summary(group: Locator) -> Locator:
    """The group's work line (its ``<summary>``, the first: a widget or notice inside the group
    brings its own)."""
    return group.locator("summary").first


def turn_line(group: Locator) -> str:
    """The work line's visible words, whitespace collapsed ("Work · 2 tool calls")."""
    return " ".join((turn_summary(group).inner_text() or "").split())


def turn_name(group: Locator) -> str | None:
    """The work line's accessible name (its ``aria-label``)."""
    return turn_summary(group).get_attribute("aria-label")


def turn_dots_stopped(group: Locator) -> bool:
    """True when the running line's three dots are frozen (visible, no animation running): the
    Stop click does this without changing the group's state."""
    return bool(
        group.evaluate(
            """el => {
              const spin = el.querySelector('.ui-turn-work-spin');
              if (!spin || spin.hidden) return false;
              const dots = Array.from(spin.querySelectorAll('.ui-turn-work-dot'));
              return dots.length === 3 && dots.every(d => {
                const s = getComputedStyle(d);
                return s.animationName === 'none' && parseFloat(s.opacity) > 0;
              });
            }"""
        )
    )


def turn_preview(group: Locator) -> Locator:
    """The group's quiet preview (``turn-work-preview``); hidden unless the group is working."""
    return group.locator('[data-testid="turn-work-preview"]')


def turn_items(group: Locator, kind: str | None = None) -> Locator:
    """The group's items in order (``kind``: ``narration``, ``thinking`` or ``tool``, or all).
    They exist while the group is collapsed; read them with ``text_content``, or open the
    group first (:func:`open_turn`)."""
    return group.locator("[data-kind]" if kind is None else f'[data-kind="{kind}"]')


def turn_texts(group: Locator, kind: str | None = None) -> list[str]:
    """The text of each item (see :func:`turn_items`), whitespace collapsed."""
    return [" ".join((t or "").split()) for t in turn_items(group, kind).all_text_contents()]


def turn_item_list(group: Locator) -> list[str]:
    """The group's items as a compact ordered list: ``thinking:<text>``, ``narration:<text>``
    and ``tool`` (one per tool row, calls and results alike). Read from the DOM, so it works
    while the group is collapsed."""
    return group.evaluate(
        """el => Array.from(el.querySelectorAll('[data-kind]')).map(e => {
          const k = e.getAttribute('data-kind');
          if (k === 'thinking') return 'thinking:' + e.textContent.replace('Thinking', '').trim();
          if (k === 'narration') return 'narration:' + e.textContent.trim();
          return 'tool';
        })"""
    )


def turn_is_open(group: Locator) -> bool:
    """True when the group is expanded."""
    # `.first`: the group's own `<details>` precedes any a widget or notice inside it brings.
    return bool(group.locator("details").first.evaluate("el => el.open"))


def open_turn(group: Locator) -> None:
    """Expand the group with a real click on its work line (a no-op when already open)."""
    if not turn_is_open(group):
        turn_summary(group).click()


def replies(page: Page) -> Locator:
    """Every assistant reply bubble (an alias of ``messages(page, "assistant")``): a finished
    turn has exactly one, and none exists before ``done``."""
    return messages(page, "assistant")


def telemetry(page: Page) -> Locator:
    """The telemetry readout (``chat-telemetry``, ``App.ui.telemetry``) in the composer's
    telemetry row."""
    return page.locator('[data-testid="chat-telemetry"]')


def emit_frame(page: Page, payload: dict[str, Any]) -> None:
    """Push a synthetic server frame into the chat area's ``ws.onmessage`` handler (the real
    frame path, without a live turn). The chat must be joined for session-scoped frames to
    pass the frame gate."""
    page.evaluate(
        """(payload) => {
          const area = window.App.areas.find(a => a.id === 'chat');
          if (!area || !area._ws || !area._ws()) throw new Error('chat area or ws not available');
          area._ws().onmessage({ data: JSON.stringify(payload) });
        }""",
        payload,
    )


def current_session_id(page: Page) -> str | None:
    """The chat area's current session id (``_currentSessionId``), or None.

    That is the joined or joining session's id: it is set the moment a
    ``join`` is sent (a row click, a deep link, the cold-load auto-join) and
    when a first send's ``session_joined`` lands. A pending chat (and a
    starting one) has no session, so this is None until the first send's
    ``session_joined``.
    """
    return page.evaluate(_SESSION_ID_JS)


def session_state(page: Page) -> dict[str, Any] | None:
    """The chat area's session state machine state (M25 F4 L3b):
    ``{name, id, agent, clientId, startedFrom, suppressAutoJoin}``, where
    ``name`` is ``idle``, ``joining``, ``joined``, ``pending`` or ``starting``."""
    return page.evaluate(_STATE_JS)


def pending_row(page: Page) -> Locator:
    """The pending chat's row in the Chats list ("New chat", "now", the agent;
    ``data-pending``, no ``data-id``, no delete action; a link to its own
    ``#chats/~new/{agent}``). There while a chat is pending or starting."""
    return page.locator(_PENDING_ROW)


def _css_str(value: str) -> str:
    """*value* as a double-quoted CSS attribute-selector string."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def chats_new_button(page: Page) -> Locator:
    """The Chats list's New chat button (``chats-new-btn``, the list pane's
    header block): it opens the agent picker; disabled while setup is
    incomplete."""
    return page.locator(_CHATS_NEW_BTN)


def gleepglorp_off(base_url: str) -> None:
    """Turn GleepGlorp off (M36 F1 L04), before the page loads. It is on by default and adds a
    "Built in" picker group, a Jump to candidate and the setup-gate exception; a test of the
    agent-only picker or of the setup-incomplete gate calls this first."""
    body = {
        "enabled": False,
        "provider_config_id": None,
        "model": None,
        "web_access": True,
        "memory": True,
        "retention_days": 30,
    }
    r = httpx.put(
        f"{base_url}/api/gleepglorp", json=body, headers=auth_headers_for(base_url), timeout=5.0
    )
    assert r.status_code == 200, r.text


def picker(page: Page) -> Locator:
    """The agent picker dialog (``agent-picker``)."""
    return page.locator(_PICKER)


def picker_search(page: Page) -> Locator:
    """The agent picker's search input (``agent-picker-search``)."""
    return page.locator(_PICKER_SEARCH)


def picker_rows(page: Page) -> Locator:
    """Every option row in the agent picker, in display order (an agent in both
    "Recently used" and "All agents" has two)."""
    return page.locator(_PICKER_ROW)


def picker_row(page: Page, agent: str) -> Locator:
    """The picker's option row(s) for *agent* (``data-agent``, exact)."""
    return page.locator(f"{_PICKER_ROW}[data-agent={_css_str(agent)}]")


def open_picker(page: Page, timeout: float = 8000) -> None:
    """Click the Chats list's New chat and wait for the agent picker, with
    focus in its search input."""
    chats_new_button(page).click(timeout=timeout)
    expect(picker(page)).to_be_visible(timeout=timeout)
    expect(picker_search(page)).to_be_focused(timeout=timeout)


def pick(page: Page, agent: str, timeout: float = 8000) -> None:
    """Pick *agent* through the agent picker: open it (New chat), type the
    agent's name, make its option the active one (ArrowDown past any other
    match the A-Z order puts first) and press Enter.

    Returns as soon as Enter is pressed (the picker closes and its onClose
    runs the pick); it does not wait for the pending chat. ``start_chat``
    waits for the chat area to settle first and for the pending chat after.
    """
    open_picker(page, timeout=timeout)
    search = picker_search(page)
    search.fill(agent)
    expect(picker_row(page, agent).first).to_be_visible(timeout=timeout)
    n = picker_rows(page).count()
    for _ in range(n):
        if page.evaluate(_PICKER_ACTIVE_JS, _PICKER_SEARCH) == agent:
            break
        search.press("ArrowDown")
    assert page.evaluate(_PICKER_ACTIVE_JS, _PICKER_SEARCH) == agent, (
        f"pick: no active option for {agent!r}"
    )
    search.press("Enter")


def welcome(page: Page) -> Locator:
    """The pane's empty and guidance state (``chat-welcome``), shown only while
    the session state is idle with no chat to auto-join (never while joining).

    Leg 4b kept the testid on it (DD3): the mascot, the "Hello." ``h1``, then
    the prompt and New chat (``empty_new_button``) when setup is complete, or
    the guidance links when it is not.
    """
    return page.locator(_WELCOME)


def empty_new_button(page: Page) -> Locator:
    """The empty state's New chat (``chat-empty-new-btn``): it opens the agent
    picker. Absent while setup is incomplete (the guidance shows instead)."""
    return page.locator(_EMPTY_NEW_BTN)


def new_chat_button(page: Page) -> Locator:
    """The New chat that opens the agent picker: since leg 4b the Chats list's
    (``chats-new-btn``, ``chats_new_button``). The chat header's own
    ``new-chat-btn`` is retired."""
    return chats_new_button(page)


def chat_header(page: Page) -> Locator:
    """The chat header (``chat-header``): an ``h1`` title and the agent line.
    Shown while a chat is open (pending, starting, joining, joined)."""
    return page.locator(_HEADER)


def chat_title(page: Page) -> Locator:
    """The chat header's ``h1``: the session's title (from the ``sessions``
    store, so it follows the auto-title), or "New chat" while pending."""
    return chat_header(page).locator("h1")


def chat_agent_line(page: Page) -> Locator:
    """The chat header's "with {agent}" (``chat-agent-line``)."""
    return page.locator(_AGENT_LINE)


def new_chat_state(page: Page) -> Locator:
    """The new-chat state (``chat-new-state``), shown only while a chat is
    pending: the model badge, the agent's name and description, and "Pick a
    different agent"."""
    return page.locator(_NEW_STATE)


def pick_different_button(page: Page) -> Locator:
    """The new-chat state's "Pick a different agent"
    (``chat-pick-different-btn``): it opens the agent picker."""
    return page.locator(_PICK_DIFFERENT)


def start_chat(page: Page, agent: str, timeout: float = 8000) -> None:
    """Start a new chat with *agent* and wait until it is ready to type in.

    **Since leg 4a** every start goes through the agent picker: once the chat
    area has settled (the welcome is shown, or a chat is open), ``pick`` opens
    it with the Chats list's New chat, types *agent* and presses Enter. (Leg
    3a's three surfaces -- the welcome option, the header ``new-chat-btn`` and
    the ``agent-select`` dropdown -- were one path each.)

    **Since leg 3b** a pick is the route ``#chats/~new/{agent}``: the client
    sends only a ``leave`` and shows a *pending* chat, with no session. This
    returns at that pending chat: the state is ``pending`` with *agent*, the
    route is ``chats/~new/{agent}``, the header reads "New chat" with "with
    {agent}" (``expect_chat``) and ``chat-input`` is enabled. ``send_first``
    creates the session. A start with the agent already pending changes
    nothing (the same pending chat).
    """
    page.wait_for_function(_SETTLED_JS, timeout=timeout)
    pick(page, agent, timeout=timeout)
    page.wait_for_function(_PENDING_JS, arg=agent, timeout=timeout)
    _nav.expect_route(page, f"chats/~new/{_nav.seg(agent)}", timeout=timeout)
    expect_chat(page, agent, timeout=timeout)
    expect(page.locator(_INPUT)).to_be_enabled(timeout=timeout)


def send_first(page: Page, text: str, timeout: float = 8000) -> str:
    """Send a chat's first message: fill ``chat-input`` with *text*, press Enter,
    wait for the turn to begin, and return the session id.

    **Since leg 3b** the first send of a pending chat creates the session
    (``start_session``): this waits for the user's bubble (the client renders
    it as it sends) and for the session's ``session_joined`` (the state is
    ``joined`` to a new id, the route ``chats/{id}``). Any staged images go
    with it, as with the Send button. On a chat that is already joined it is a
    plain send, and returns that session's id.
    """
    before_state = session_state(page) or {}
    before_id = before_state.get("id") if before_state.get("name") == "joined" else None
    before = page.locator(_USER_MSG).count()
    box = page.locator(_INPUT)
    box.fill(text)
    box.press("Enter")
    page.wait_for_function(
        "([sel, n]) => document.querySelectorAll(sel).length > n",
        arg=[_USER_MSG, before],
        timeout=timeout,
    )
    if before_id is None:
        page.wait_for_function(_JOINED_NEW_JS, arg=None, timeout=timeout)
    sid = current_session_id(page)
    assert sid, "send_first: no session after the first send"
    _nav.expect_route(page, f"chats/{_nav.seg(sid)}", timeout=timeout)
    return sid


def expect_chat(page: Page, agent: str, title: str | None = None, timeout: float = 8000) -> None:
    """The open chat's header shows *agent*: a joined session (after a send, a
    row open, a deep link or a reload) or a pending chat.

    Since leg 4b that is the chat header (``chat-header``, visible) with its
    agent line reading "with {agent}" and, given *title*, its ``h1`` reading
    *title* ("New chat" for a pending chat). (Until leg 4b it was the old
    header's agent badge.)
    """
    expect(chat_header(page)).to_be_visible(timeout=timeout)
    expect(chat_agent_line(page)).to_have_text(f"with {agent}", timeout=timeout)
    if title is not None:
        expect(chat_title(page)).to_have_text(title, timeout=timeout)


def chat_row(page: Page, session_id: str) -> Locator:
    """The Chats list's row for session *session_id*: the ``App.ui.listPane``
    link ``chat-row`` with that ``data-id`` (``aria-current="page"`` on the open
    session's row; never the pending row, which has no ``data-id``)."""
    return page.locator(f"{_ROW}[data-id={_css_str(session_id)}]")


def wait_row_has_focus(page: Page, session_id: str, timeout: float = 10000) -> None:
    """Wait until the Chats list row for *session_id* is ``document.activeElement``.

    Asserts element identity, not window focus: Playwright's ``to_be_focused``
    reads "inactive" when a parallel, loaded headless run leaves the page
    without window focus (squawk 0204).  Bounded by *timeout* (ms)."""
    page.wait_for_function(
        """(id) => {
          const a = document.activeElement;
          return !!a && a.getAttribute('data-testid') === 'chat-row'
            && a.getAttribute('data-id') === id;
        }""",
        arg=session_id,
        timeout=timeout,
    )


def chat_row_delete(page: Page, session_id: str) -> Locator:
    """The delete action (``chat-row-delete``) of session *session_id*'s row: a
    sibling of the row link in its ``<li>``, shown on hover and focus-within."""
    return page.locator("li").filter(has=chat_row(page, session_id)).locator(_ROW_DELETE)


def chat_rows(page: Page) -> Locator:
    """Every session row in the Chats list (``chat_row`` without an id): the
    ``chat-row`` links with a ``data-id``, so never the pending chat's row (see
    ``pending_row``)."""
    return page.locator(_SESSION_ROW)


def open_chat(page: Page, session_id: str, timeout: float = 8000) -> None:
    """Click session *session_id*'s Chats list row and wait until the chat area
    is on it.

    The row is a link: the click is a pushed ``App.router.go`` (through
    ``App.nav``'s link interceptor) whose hydrate sends one ``join``; this waits
    for the route ``chats/{id}`` and for the session to be joined (its
    ``session_joined`` landed).
    """
    chat_row(page, session_id).click(timeout=timeout)
    _nav.expect_route(page, f"chats/{_nav.seg(session_id)}", timeout=timeout)
    page.wait_for_function(_JOINED_ID_JS, arg=session_id, timeout=timeout)


def chat_frames(page: Page, actions: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
    """A live list of the JSON frames the page sends on its WebSockets.

    Call it BEFORE ``page.goto`` to see a page's first frames. Every frame sent
    afterwards is parsed and appended (non-JSON frames are skipped), so a test
    may ``clear()`` it between steps. With *actions*, only frames whose
    ``action`` is one of them are kept.

    The mechanism is Playwright's ``websocket`` / ``framesent`` events (the
    engine-neutral form of CDP's ``Network.webSocketFrameSent``), as
    ``test_router_items.py`` used before this helper. Since leg 3b a pick sends
    ``leave``, the first send ``start_session`` and a row open ``join``
    (``new_session`` is gone).
    """
    frames: list[dict[str, Any]] = []

    def _on_ws(ws) -> None:  # noqa: ANN001
        def _sent(payload) -> None:  # noqa: ANN001
            try:
                msg = json.loads(payload)
            except (TypeError, ValueError):
                return
            if not isinstance(msg, dict):
                return
            if actions is None or msg.get("action") in actions:
                frames.append(msg)

        ws.on("framesent", _sent)

    page.on("websocket", _on_ws)
    return frames
