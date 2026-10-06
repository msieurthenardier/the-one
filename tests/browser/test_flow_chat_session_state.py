"""The chat area's session state machine, unit-tested (M25 F4 leg 3b, DD1).

``App.chat.createSessionState()`` (``static/js/areas/chat/session-state.js``) is
PURE: no DOM, no WebSocket, no timers. Every transition returns its effects as
data, so each row of the leg's transition table (AC2), the idle rules (AC2b),
the frame gate (AC3), ``serialize`` (AC5), ``activeId`` (AC6) and
``reconnectAction`` (AC8) is a plain input/output case run through
``page.evaluate`` on the module loaded from disk (no app, no chat DOM).

Falls in the ``chats`` browser lane (``test_flow_chat*``).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, Page

pytestmark = pytest.mark.browser

MODULE = (
    Path(__file__).resolve().parents[2]
    / "the_one/interfaces/web/static/js/areas/chat/session-state.js"
)

# Runs `steps` ([op, ...args]) on a fresh machine; returns every effect, the
# final state and the queries.
_RUN_JS = """
(steps) => {
  const sm = App.chat.createSessionState();
  const effects = [];
  for (const step of steps) {
    const op = step[0];
    effects.push(sm[op].apply(null, step.slice(1)));
  }
  return { effects, state: sm.state(), activeId: sm.activeId(), boundId: sm.boundId(),
           serialize: sm.serialize(), startFrame: sm.startFrame() };
}
"""


@pytest.fixture(scope="module")
def sm_page(browser: Browser) -> Iterator[Page]:
    """One page with only the state module loaded (it needs no app)."""
    context = browser.new_context()
    page = context.new_page()
    page.set_content("<!doctype html><html><body></body></html>")
    page.add_script_tag(path=str(MODULE))
    try:
        yield page
    finally:
        context.close()


def run(page: Page, *steps: list[Any]) -> dict[str, Any]:
    return page.evaluate(_RUN_JS, [list(s) for s in steps])


def frame(type_: str, **kw: Any) -> list[Any]:
    return ["onFrame", {"type": type_, **kw}]


def joined(sid: str, history: list[Any] | None = None, status: str = "ok") -> list[Any]:
    return frame("session_joined", session_id=sid, status=status, history=history or [])


def subset(actual: dict[str, Any], expected: dict[str, Any]) -> None:
    for k, v in expected.items():
        assert actual.get(k) == v, (k, actual)


PAYLOAD = {"message": "hi", "images": [{"data": "AAAA", "media_type": "image/png"}]}

# Setup step lists that reach each state.
TO = {
    "idle": [],
    "pending": [["pick", "A"]],
    "starting": [["pick", "A"], ["startSend", "c1", PAYLOAD]],
    "joining": [["openConversation", "s1"]],
    "joined": [["openConversation", "s1"], joined("s1", [{"type": "user", "content": "x"}])],
}


def test_initial_state_and_shape(sm_page: Page) -> None:
    """AC1: idle at first; the API is exactly the leg's transitions and queries."""
    out = run(sm_page)
    assert out["state"] == {
        "name": "idle",
        "id": None,
        "agent": None,
        "clientId": None,
        "startedFrom": None,
        "suppressAutoJoin": False,
    }
    assert out["activeId"] is None and out["boundId"] is None and out["serialize"] is None
    keys = sm_page.evaluate("Object.keys(App.chat.createSessionState()).sort()")
    assert keys == sorted(
        [
            "state",
            "pick",
            "openConversation",
            "startSend",
            "onFrame",
            "reset",
            "accepts",
            "activeId",
            "boundId",
            "serialize",
            "startFrame",
            "reconnectAction",
            "idleRules",
        ]
    )
    # Pure: no DOM, no WebSocket, no timers in the module's code (comments
    # stripped).
    code = "\n".join(line.split("//", 1)[0] for line in MODULE.read_text().splitlines())
    for banned in ("document", "WebSocket", "setTimeout", "setInterval", "fetch(", "App.router"):
        assert banned not in code, banned


def test_client_id_is_32_lowercase_hex(sm_page: Page) -> None:
    ids = sm_page.evaluate("[1,2,3,4].map(() => App.chat.newClientId())")
    assert len(set(ids)) == 4
    for cid in ids:
        assert len(cid) == 32 and all(c in "0123456789abcdef" for c in cid), cid


# ── AC2: the transition table ────────────────────────────────────────────────


@pytest.mark.parametrize("start", ["pending", "starting"])
def test_pick_same_agent_while_pending_or_starting_is_a_noop(sm_page: Page, start: str) -> None:
    before = run(sm_page, *TO[start])
    out = run(sm_page, *TO[start], ["pick", "A"])
    assert out["effects"][-1] == {"noop": True}
    assert out["state"] == before["state"]  # no leave, no reset


@pytest.mark.parametrize(
    ("start", "leave", "discard"),
    [
        ("idle", False, None),
        ("pending", False, None),  # another agent
        ("joining", True, None),
        ("joined", True, "s1"),
        ("starting", True, "c1"),
    ],
)
def test_pick_another_agent_goes_pending(sm_page: Page, start: str, leave: bool, discard) -> None:
    out = run(sm_page, *TO[start], ["pick", "B"])
    subset(
        out["effects"][-1],
        {
            "leave": leave,
            "discardHeld": discard,
            "clearPendingJoin": True,
            "render": "pending",
        },
    )
    subset(
        out["state"],
        {
            "name": "pending",
            "agent": "B",
            "id": None,
            "clientId": None,
            "startedFrom": None,
            "suppressAutoJoin": False,
        },
    )


def test_pick_clears_started_from_and_suppress(sm_page: Page) -> None:
    # startedFrom (a joined start) and suppressAutoJoin (a join_failed) are
    # both cleared by a pick.
    out = run(sm_page, *TO["starting"], joined("c1"), ["pick", "A"])
    assert out["state"]["startedFrom"] is None
    out = run(
        sm_page, ["openConversation", "x"], frame("join_failed", session_id="x"), ["pick", "A"]
    )
    assert out["state"]["suppressAutoJoin"] is False


def test_start_send_from_pending(sm_page: Page) -> None:
    out = run(sm_page, *TO["pending"], ["startSend", "c1", PAYLOAD])
    eff = out["effects"][-1]
    assert eff["busy"] is True
    assert eff["send"] == {
        "action": "start_session",
        "session_id": "c1",
        "agent_name": "A",
        "message": "hi",
        "images": PAYLOAD["images"],
    }
    subset(out["state"], {"name": "starting", "clientId": "c1", "agent": "A"})
    assert out["startFrame"] == eff["send"]
    # Text only: no images key.
    out = run(sm_page, ["pick", "A"], ["startSend", "c2", {"message": "t"}])
    assert "images" not in out["effects"][-1]["send"]


@pytest.mark.parametrize("start", ["idle", "starting", "joining", "joined"])
def test_start_send_outside_pending_is_a_noop(sm_page: Page, start: str) -> None:
    before = run(sm_page, *TO[start])
    out = run(sm_page, *TO[start], ["startSend", "c9", {"message": "x"}])
    assert out["effects"][-1] == {"noop": True}
    assert out["state"] == before["state"]


def test_starting_joined_ok_empty_history_keeps_the_bubble(sm_page: Page) -> None:
    out = run(sm_page, *TO["starting"], joined("c1"))
    subset(
        out["effects"][-1],
        {
            "accept": True,
            "fromStart": True,
            "render": "keep",
            "sync": "sessions/c1",
            "refreshList": True,
        },
    )
    subset(out["state"], {"name": "joined", "id": "c1", "startedFrom": {"agent": "A", "cid": "c1"}})


def test_starting_joined_ok_with_history_renders_it(sm_page: Page) -> None:
    out = run(sm_page, *TO["starting"], joined("c1", [{"type": "user", "content": "hi"}]))
    assert out["effects"][-1]["render"] == "history"
    assert out["state"]["name"] == "joined"


def test_starting_joined_degraded_empty_is_a_start_failure(sm_page: Page) -> None:
    out = run(sm_page, *TO["starting"], joined("c1", status="agent_deleted"))
    eff = out["effects"][-1]
    subset(eff, {"accept": True, "startFailed": True, "clientId": "c1", "payload": PAYLOAD})
    assert "deleted" in eff["error"]
    subset(out["state"], {"name": "pending", "agent": "A", "clientId": None})


def test_starting_start_failed_back_to_pending_with_the_payload(sm_page: Page) -> None:
    out = run(sm_page, *TO["starting"], frame("start_failed", session_id="c1", error="boom"))
    subset(
        out["effects"][-1],
        {
            "accept": True,
            "startFailed": True,
            "clientId": "c1",
            "error": "boom",
            "payload": PAYLOAD,
        },
    )
    subset(out["state"], {"name": "pending", "agent": "A"})


def test_pending_drops_a_late_session_joined_and_refreshes_the_list(sm_page: Page) -> None:
    out = run(sm_page, *TO["pending"], joined("old"))
    assert out["effects"][-1] == {"accept": False, "refreshList": True}
    subset(out["state"], {"name": "pending", "agent": "A"})


def test_abandoned_start_refreshes_the_list(sm_page: Page) -> None:
    """A pick while starting abandons the start; its late session_joined is
    dropped, with a list refresh (the server may have created it)."""
    out = run(sm_page, *TO["starting"], ["pick", "B"], joined("c1"))
    assert out["effects"][-1] == {"accept": False, "refreshList": True}
    subset(out["state"], {"name": "pending", "agent": "B"})


@pytest.mark.parametrize("start", ["idle", "pending", "starting", "joining", "joined"])
def test_open_conversation_from_any_state(sm_page: Page, start: str) -> None:
    prev = run(sm_page, *TO[start])
    out = run(sm_page, *TO[start], ["openConversation", "s2"])
    eff = out["effects"][-1]
    assert eff["join"] == "s2"
    prev_active = prev["activeId"]
    assert eff["discardHeld"] == (prev_active if prev_active and prev_active != "s2" else None)
    assert out["state"] == {
        "name": "joining",
        "id": "s2",
        "agent": None,
        "clientId": None,
        "startedFrom": None,
        "suppressAutoJoin": False,
    }


def test_joining_same_id_joins_and_renders_history(sm_page: Page) -> None:
    out = run(sm_page, *TO["joining"], joined("s1"))
    subset(out["effects"][-1], {"accept": True, "render": "history", "sync": "sessions/s1"})
    subset(out["state"], {"name": "joined", "id": "s1", "startedFrom": None})


def test_joining_drops_another_id(sm_page: Page) -> None:
    out = run(sm_page, *TO["joining"], joined("other"))
    assert out["effects"][-1] == {"accept": False}
    subset(out["state"], {"name": "joining", "id": "s1"})


def test_quick_a_then_b_with_a_late_joined_a(sm_page: Page) -> None:
    out = run(
        sm_page, ["openConversation", "A"], ["openConversation", "B"], joined("A"), joined("B")
    )
    assert out["effects"][2] == {"accept": False}
    subset(out["effects"][3], {"accept": True, "render": "history"})
    subset(out["state"], {"name": "joined", "id": "B"})


def test_joining_join_failed_goes_idle_and_suppresses_the_auto_join(sm_page: Page) -> None:
    out = run(sm_page, *TO["joining"], frame("join_failed", session_id="s1", error="not_found"))
    subset(
        out["effects"][-1],
        {
            "accept": True,
            "toIdle": True,
            "refreshList": True,
            "notice": "That conversation no longer exists",
        },
    )
    subset(out["state"], {"name": "idle", "suppressAutoJoin": True})


@pytest.mark.parametrize("sid", ["s1", "other"])
def test_joined_drops_any_session_joined(sm_page: Page, sid: str) -> None:
    out = run(sm_page, *TO["joined"], joined(sid))
    assert out["effects"][-1] == {"accept": False}
    subset(out["state"], {"name": "joined", "id": "s1"})


def test_joined_session_deleted_goes_idle(sm_page: Page) -> None:
    out = run(sm_page, *TO["joined"], frame("session_deleted", session_id="s1"))
    subset(out["effects"][-1], {"accept": True, "toIdle": True, "deleted": True})
    assert out["state"]["name"] == "idle"
    # Another id: the list only.
    out = run(sm_page, *TO["joined"], frame("session_deleted", session_id="zz"))
    assert out["effects"][-1] == {"accept": True, "refreshList": True}
    assert out["state"]["name"] == "joined"


@pytest.mark.parametrize("start", ["idle", "pending", "starting", "joining", "joined"])
def test_reset_goes_idle_and_clears_suppress(sm_page: Page, start: str) -> None:
    prev = run(sm_page, *TO[start])
    out = run(sm_page, *TO[start], ["reset"])
    assert out["effects"][-1] == {"toIdle": True, "discardHeld": prev["activeId"]}
    assert out["state"]["name"] == "idle" and out["state"]["suppressAutoJoin"] is False
    out = run(sm_page, ["openConversation", "x"], frame("join_failed", session_id="x"), ["reset"])
    assert out["state"]["suppressAutoJoin"] is False


@pytest.mark.parametrize(
    ("start", "frm"),
    [
        ("idle", joined("zz")),
        ("starting", joined("zz")),
        ("starting", frame("start_failed", session_id="zz", error="x")),
        ("pending", frame("start_failed", session_id="c1", error="x")),
        ("joined", frame("start_failed", session_id="s1", error="x")),
        ("joining", frame("join_failed", session_id="zz", error="not_found")),
        ("joined", frame("join_failed", session_id="s1", error="not_found")),
        ("idle", frame("join_failed", session_id="s1", error="not_found")),
    ],
)
def test_no_op_frames(sm_page: Page, start: str, frm: list[Any]) -> None:
    before = run(sm_page, *TO[start])
    out = run(sm_page, *TO[start], frm)
    assert out["effects"][-1] == {"accept": False}
    assert out["state"] == before["state"]


# ── AC2b: the idle rules ─────────────────────────────────────────────────────

LIST = [{"id": "s1"}, {"id": "s2"}]


def test_idle_rules(sm_page: Page) -> None:
    def rules(steps, lst, pjid=None):
        return sm_page.evaluate(
            """([steps, lst, pjid]) => { const sm = App.chat.createSessionState();
                 for (const s of steps) sm[s[0]].apply(null, s.slice(1));
                 return sm.idleRules(lst, pjid); }""",
            [steps, lst, pjid],
        )

    assert rules([], LIST, "s2") == {"open": "s2", "clearPendingJoin": True, "welcome": False}
    # pendingJoinId not listed: falls through to the most recent session.
    assert rules([], LIST, "gone") == {"open": "s1", "clearPendingJoin": True, "welcome": False}
    assert rules([], LIST) == {"open": "s1", "clearPendingJoin": False, "welcome": False}
    assert rules([], []) == {"open": None, "clearPendingJoin": False, "welcome": True}
    # Suppressed auto-join (after a join_failed): the welcome, but a listed
    # pendingJoinId still opens.
    suppressed = [
        ["openConversation", "x"],
        ["onFrame", {"type": "join_failed", "session_id": "x"}],
    ]
    assert rules(suppressed, LIST) == {"open": None, "clearPendingJoin": False, "welcome": True}
    assert rules(suppressed, LIST, "s2")["open"] == "s2"
    # Never outside idle: pending and starting never auto-join or show the welcome.
    for start in ("pending", "starting", "joining", "joined"):
        assert rules(TO[start], LIST, "s2") == {}, start


# ── AC3: the frame gate ──────────────────────────────────────────────────────

SCOPED = [
    "user",
    "assistant_chunk",
    "assistant",
    "thinking",
    "tool_call",
    "tool_result",
    "system",
    "usage",
    "done",
    "cancelled",
    "auth_required",
    "auth_resolved",
    "auth_failed",
    "anything",
]


@pytest.mark.parametrize("start", ["idle", "pending", "starting", "joining", "joined"])
def test_frame_gate(sm_page: Page, start: str) -> None:
    got = sm_page.evaluate(
        """([steps, types]) => { const sm = App.chat.createSessionState();
             for (const s of steps) sm[s[0]].apply(null, s.slice(1));
             return types.map(t => [t, sm.accepts({type: t}), sm.onFrame({type: t}).accept,
                                    sm.state().name]); }""",
        [TO[start], SCOPED + ["session_list", "session_deleted"]],
    )
    for t, accepts, accepted, name in got:
        want = True if t in ("session_list", "session_deleted") else start == "joined"
        assert (accepts, accepted) == (want, want), (start, t)
        assert name == start, (start, t)  # never a state change


def test_frames_after_a_pick_are_dropped_and_a_late_joined_keeps_pending(sm_page: Page) -> None:
    """The previous session's in-flight frames (chunks, tools, system, done)
    and its late session_joined after a pick: none accepted, still pending."""
    steps = [*TO["joined"], ["pick", "B"]] + [frame(t) for t in SCOPED] + [joined("s1")]
    out = run(sm_page, *steps)
    assert all(e.get("accept") is False for e in out["effects"][len(TO["joined"]) + 1 :])
    subset(out["state"], {"name": "pending", "agent": "B"})


# ── AC5 / AC6: serialize and activeId ────────────────────────────────────────


def test_serialize_and_active_id(sm_page: Page) -> None:
    want = {
        "idle": (None, None, None),
        "pending": ("new/A", None, None),
        "starting": ("new/A", "c1", None),
        "joining": ("sessions/s1", None, "s1"),
        "joined": ("sessions/s1", "s1", "s1"),
    }
    for start, (ser, active, bound) in want.items():
        out = run(sm_page, *TO[start])
        assert (out["serialize"], out["activeId"], out["boundId"]) == (ser, active, bound), start
    # The agent is percent-encoded (a space, a leading ~ which
    # encodeURIComponent leaves alone; the router escapes it to %7E).
    out = run(sm_page, ["pick", "~My Agent/é"])
    assert out["serialize"] == "new/~My%20Agent%2F%C3%A9"


# ── AC8: reconnectAction ─────────────────────────────────────────────────────


def test_reconnect_action(sm_page: Page) -> None:
    # Not bound on an earlier socket: nothing, whatever the state.
    for start in TO:
        out = run(sm_page, *TO[start], ["reconnectAction", ["s1"], False])
        assert out["effects"][-1] == {"send": None}, start
    # Starting: the SAME start_session (same cid and payload), never join.
    out = run(sm_page, *TO["starting"], ["reconnectAction", None, True])
    assert out["effects"][-1] == {"send": "start_session", "frame": out["startFrame"]}
    assert out["startFrame"]["session_id"] == "c1" and out["state"]["name"] == "starting"
    # Joined / joining, listed: joining(id) + join(id).
    for start in ("joined", "joining"):
        out = run(sm_page, *TO[start], ["reconnectAction", ["s1", "s2"], True])
        assert out["effects"][-1] == {"send": "join", "id": "s1"}, start
        subset(out["state"], {"name": "joining", "id": "s1"})
        # Not listed (deleted while down): idle with a notice, never a join.
        out = run(sm_page, *TO[start], ["reconnectAction", ["s2"], True])
        assert out["effects"][-1] == {
            "send": None,
            "toIdle": True,
            "notice": "That conversation no longer exists",
        }, start
        assert out["state"]["name"] == "idle"
    # Pending and idle: nothing.
    for start in ("pending", "idle"):
        out = run(sm_page, *TO[start], ["reconnectAction", ["s1"], True])
        assert out["effects"][-1] == {"send": None}, start
