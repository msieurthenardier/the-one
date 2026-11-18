"""M25 F4 L2 — the chat WebSocket start protocol (DD1).

Drives the real ``websocket_endpoint`` coroutine against a fake WebSocket,
in the ``tests/test_ws_message_branch_crash_guard.py`` style, but with the
REAL session create/restore/persist path behind it:

- a per-test SQLite DB (``isolated_db``); rows are counted with
  ``ChatSessionRepository.list()`` and read with ``.get(sid)``;
- ``_get_factory`` patched to a fake factory whose agents (modelled on
  ``tests/test_cancel.py``'s ``_QuickAgent``) append to ``messages`` and
  yield one assistant reply, so ``_save_session_to_db`` persists a real turn;
- ``_send_to_session`` / ``_save_session_to_db`` NOT patched;
- ``_create_session`` patched only where a test needs to park or fail it.

Covers ``leave``, ``start_session`` (validation, the existing-id join, the
reservation, the strict create, the swap/joined/spawn order), the shared
``_validate_message_payload``, the broadened bare-message auto-create catch,
``join``'s ``join_failed`` for an unknown id, and ``_restore_session``'s
in-flight skip-rebuild guard.

Spawned turns outlive ``websocket_endpoint`` (the fake socket disconnects
when its script runs out), so tests await them (``_drain_turns``) before
asserting persistence, and assert on ``ws.sent`` frames and ``_sessions``
rather than on subscriber state after the script ends.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import sqlite3
from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest
from starlette.websockets import WebSocketDisconnect

from the_one.agent.factory import AgentNotFoundError
from the_one.db.codec import decode_messages
from the_one.db.connection import get_connection
from the_one.db.repositories import ChatSessionRepository
from the_one.interfaces.web import app as app_module
from the_one.interfaces.web.app import (
    IMAGE_ATTACHMENT_CAP_BYTES,
    IMAGE_ATTACHMENT_MAX_COUNT,
    _inflight_tasks,
    _session_inflight,
    websocket_endpoint,
)
from the_one.llm.base import Message, Role, content_to_text
from the_one.sessions import clear_for_test, clear_locks_for_test, subscribers_for

STEP_TIMEOUT_S = 5.0

# ── Fake agent / factory ──────────────────────────────────────────────────


class _LLMShim:
    max_context_tokens = 128_000


class _Recorder:
    """Shared by every agent the fake factory builds."""

    def __init__(self) -> None:
        self.creates: list[str] = []
        self.steps: list[tuple[str, str]] = []
        self.step_started: dict[str, asyncio.Event] = {}
        # Per-message-text gates: a step whose text is a key parks until set.
        self.gates: dict[str, asyncio.Event] = {}
        self.missing_agents: set[str] = set()
        self.fail_create: BaseException | None = None

    def started(self, text: str) -> asyncio.Event:
        return self.step_started.setdefault(text, asyncio.Event())


class _FakeAgent:
    """What the WS loop and ``_process_and_broadcast`` touch, and no more."""

    def __init__(self, recorder: _Recorder, name: str) -> None:
        self.messages: list[Message] = [Message.system(f"You are {name}.")]
        self.llm = _LLMShim()
        self._deferred_tool_calls = None
        self.stopped_at_step_limit = False
        self.max_iterations = 20
        self._recorder = recorder
        self._name = name

    async def step(
        self,
        user_input: Any,
        on_chunk: Any = None,  # noqa: ARG002
        on_usage: Any = None,  # noqa: ARG002
    ) -> AsyncIterator[Message]:
        text = content_to_text(user_input)
        self._recorder.steps.append((self._name, text))
        self.messages.append(Message.user(text))
        self._recorder.started(text).set()
        gate = self._recorder.gates.get(text)
        if gate is not None:
            await gate.wait()
        reply = Message(role=Role.ASSISTANT, content=f"reply to {text}")
        self.messages.append(reply)
        yield reply

    def reset(self) -> None:
        self.messages = self.messages[:1]

    async def resume_after_auth(self) -> AsyncIterator[Message]:  # pragma: no cover
        if False:
            yield  # type: ignore[unreachable]


class _FakeFactory:
    def __init__(self, recorder: _Recorder) -> None:
        self._recorder = recorder

    async def create(self, name: str) -> _FakeAgent:
        if name in self._recorder.missing_agents:
            raise AgentNotFoundError(name)
        if self._recorder.fail_create is not None:
            raise self._recorder.fail_create
        self._recorder.creates.append(name)
        return _FakeAgent(self._recorder, name)


# ── Fake WebSocket with awaitable script steps ───────────────────────────


async def _until(predicate: Callable[[], bool], timeout: float = STEP_TIMEOUT_S) -> None:
    async def _poll() -> None:
        while not predicate():
            await asyncio.sleep(0.002)

    await asyncio.wait_for(_poll(), timeout)


class Wait:
    """Script step: wait for an event before reading the next frame."""

    def __init__(self, event: asyncio.Event) -> None:
        self.event = event

    async def run(self, ws: FakeWebSocket) -> None:  # noqa: ARG002
        await asyncio.wait_for(self.event.wait(), STEP_TIMEOUT_S)


class WaitFrame:
    """Script step: wait until ``count`` frames of ``type_`` were sent."""

    def __init__(self, type_: str, count: int = 1) -> None:
        self.type_ = type_
        self.count = count

    async def run(self, ws: FakeWebSocket) -> None:
        await _until(lambda: len(ws.frames(self.type_)) >= self.count)


class Do:
    """Script step: run a (sync or async) callable. It runs only after the
    previous frame was fully handled, since the WS loop is sequential."""

    def __init__(self, fn: Callable[[], Any]) -> None:
        self.fn = fn

    async def run(self, ws: FakeWebSocket) -> None:  # noqa: ARG002
        result = self.fn()
        if inspect.isawaitable(result):
            await result


class NoYield:
    """Script step: a frame delivered WITHOUT the receive's usual yield, so a
    task spawned by the previous frame has not run its first step yet."""

    def __init__(self, frame: dict) -> None:
        self.frame = frame


class FakeWebSocket:
    """Copied from ``test_ws_message_branch_crash_guard.py`` and extended
    with awaitable script steps (``Wait``/``WaitFrame``/``Do``) and an
    optional send failure. Raises ``WebSocketDisconnect`` when the script
    runs out."""

    def __init__(self, script: list[Any], *, fail_send_on: str | None = None) -> None:
        self._script = list(script)
        self.sent: list[dict] = []
        self.consumed: list[dict] = []
        self.accepted = False
        self._fail_send_on = fail_send_on

    async def accept(self) -> None:
        self.accepted = True

    async def receive_text(self) -> str:
        # Yield like a real receive, so just-spawned tasks get to run (a
        # `NoYield` frame is the one exception).
        if not (self._script and isinstance(self._script[0], NoYield)):
            await asyncio.sleep(0)
        while self._script:
            step = self._script.pop(0)
            if isinstance(step, NoYield):
                step = step.frame
            if isinstance(step, dict):
                self.consumed.append(step)
                return json.dumps(step)
            await step.run(self)
        raise WebSocketDisconnect()

    async def send_json(self, data: dict) -> None:
        if self._fail_send_on is not None and data.get("type") == self._fail_send_on:
            raise WebSocketDisconnect()
        self.sent.append(data)

    def frames(self, type_: str) -> list[dict]:
        return [f for f in self.sent if f.get("type") == type_]

    def types(self) -> list[str]:
        return [f.get("type") for f in self.sent]


# ── Helpers ───────────────────────────────────────────────────────────────


def _sid(n: int) -> str:
    """A valid client id: 32 lowercase hex characters."""
    return f"{n:032x}"


def _start(sid: Any, message: Any = "hello", agent: Any = "alpha", **extra: Any) -> dict:
    return {
        "action": "start_session",
        "session_id": sid,
        "agent_name": agent,
        "message": message,
        **extra,
    }


async def _repo() -> ChatSessionRepository:
    return ChatSessionRepository(await get_connection())


async def _row_ids() -> set[str]:
    return {r.id for r in await (await _repo()).list()}


async def _persisted(sid: str) -> list[tuple[str, str]]:
    row = await (await _repo()).get(sid)
    return [
        (m.role.value, content_to_text(m.content))
        for m in decode_messages(row.messages)
        if m.role != Role.SYSTEM
    ]


async def _drain_turns() -> None:
    async def _drain() -> None:
        while _inflight_tasks:
            await asyncio.gather(*list(_inflight_tasks), return_exceptions=True)
            await asyncio.sleep(0)

    await asyncio.wait_for(_drain(), STEP_TIMEOUT_S)


async def _run(*sockets: FakeWebSocket) -> None:
    await asyncio.wait_for(
        asyncio.gather(*(websocket_endpoint(ws) for ws in sockets)),  # type: ignore[arg-type]
        STEP_TIMEOUT_S * 3,
    )
    await _drain_turns()


async def _precreate(sid: str, agent: str = "alpha") -> app_module.Session:
    """A session with a DB row and an empty history (the real create path)."""
    return await app_module._create_session(agent_name=agent, session_id=sid)


def _probe(sid_or_session: Any) -> Callable[[], Any]:
    """A ``Do`` body broadcasting a probe frame to a session's subscribers."""

    async def _send() -> None:
        session = (
            app_module._sessions[sid_or_session]
            if isinstance(sid_or_session, str)
            else sid_or_session
        )
        await app_module._send_to_session(session, {"type": "probe"})

    return _send


class _ParkingCreate:
    """Wraps the real ``_create_session``: the FIRST call parks until
    ``release`` is set (then optionally fails); later calls go straight
    through."""

    def __init__(self, real: Any, *, fail_first: BaseException | None = None) -> None:
        self._real = real
        self._fail_first = fail_first
        self.calls: list[str | None] = []
        self.inside = asyncio.Event()
        self.release = asyncio.Event()

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append(kwargs.get("session_id"))
        if len(self.calls) == 1:
            self.inside.set()
            await asyncio.wait_for(self.release.wait(), STEP_TIMEOUT_S * 2)
            if self._fail_first is not None:
                raise self._fail_first
        return await self._real(*args, **kwargs)


async def _settle(ws: FakeWebSocket, n_consumed: int) -> None:
    """Wait until ``ws`` has read ``n_consumed`` frames, then let its handler
    run up to its next suspension (the reservation wait is reached with no
    I/O in between)."""
    await _until(lambda: len(ws.consumed) >= n_consumed)
    for _ in range(20):
        await asyncio.sleep(0)


# ── Fixtures ──────────────────────────────────────────────────────────────


def _reset_state() -> None:
    _inflight_tasks.clear()
    _session_inflight.clear()
    app_module._cancel_tokens.clear()
    app_module._started_tasks.clear()
    app_module._running_tasks.clear()
    app_module._start_reservations.clear()
    app_module._sessions.clear()
    clear_for_test()
    clear_locks_for_test()


@pytest.fixture(autouse=True)
async def recorder(isolated_db, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_Recorder]:  # noqa: ARG001
    rec = _Recorder()
    factory = _FakeFactory(rec)
    monkeypatch.setattr(app_module, "_get_factory", lambda: factory)
    _reset_state()
    yield rec
    # Spawned turns outlive the endpoint: cancel and await before the DB
    # fixture closes the connection.
    for t in list(_inflight_tasks):
        t.cancel()
    if _inflight_tasks:
        await asyncio.gather(*list(_inflight_tasks), return_exceptions=True)
    _reset_state()


# ── AC1: the shared validator ────────────────────────────────────────────
# (`_validate_message_payload`'s own unit tests live in
# `tests/test_ws_build_user_content.py`, which needs no DB.)


class TestMessagePathUsesTheValidator:
    async def test_non_text_message_sends_system_and_creates_nothing(
        self, recorder: _Recorder
    ) -> None:
        ws = FakeWebSocket([{"action": "message", "message": 5}, {"action": "list_sessions"}])
        await _run(ws)
        assert ws.types() == ["system", "session_list"]
        assert ws.sent[0]["content"] == "Message must be text."
        assert app_module._sessions == {}
        assert await _row_ids() == set()
        assert recorder.creates == []

    async def test_null_message_stays_silent(self) -> None:
        ws = FakeWebSocket([{"action": "message", "message": None}, {"action": "list_sessions"}])
        await _run(ws)
        assert ws.types() == ["session_list"]
        assert app_module._sessions == {}

    async def test_content_build_failure_creates_no_session(self, recorder: _Recorder) -> None:
        """The recorded order change: the content build now runs BEFORE the
        auto-create, so a build failure creates nothing."""
        ws = FakeWebSocket(
            [
                {
                    "action": "message",
                    "message": "",
                    "images": [{"media_type": "image/png", "data": "a", "bogus": "x"}],
                },
                {"action": "list_sessions"},
            ]
        )
        await _run(ws)
        assert ws.types() == ["system", "session_list"]
        assert ws.sent[0]["content"].startswith("Cannot process message: ")
        assert app_module._sessions == {}
        assert await _row_ids() == set()
        assert recorder.creates == []

    async def test_bare_message_with_no_session_is_refused_and_creates_nothing(
        self, recorder: _Recorder
    ) -> None:
        """M36 F1 L03: there is no Default agent, so a message with no session cannot start
        a chat: the client gets "Cannot start chat: …" and nothing is stored."""
        ws = FakeWebSocket([{"action": "message", "message": "hi"}, {"action": "list_sessions"}])
        await _run(ws)
        assert ws.frames("session_joined") == []
        assert (
            ws.frames("system")[0]["content"]
            == "Cannot start chat: Choose an agent to start a chat."
        )
        assert recorder.steps == []
        assert recorder.creates == []
        assert app_module._sessions == {}
        assert await _row_ids() == set()
        assert _session_inflight == {}


# ── AC2: leave ────────────────────────────────────────────────────────────


class TestLeave:
    async def test_leave_unbinds_without_frame_write_or_cancel(self, recorder: _Recorder) -> None:
        sid = _sid(1)
        gate = recorder.gates["slow"] = asyncio.Event()
        state: dict[str, Any] = {}

        async def _before_leave() -> None:
            session = app_module._sessions[sid]
            state["session"] = session
            state["frames_before"] = len(ws.sent)
            state["row_before"] = await (await _repo()).get(sid)
            session.last_activity = 0.0

        async def _after_leave() -> None:
            session = state["session"]
            assert session.last_activity > 0.0, "leave must touch last_activity"
            # Nothing written to the DB (the turn is still parked).
            assert await (await _repo()).get(sid) == state["row_before"]
            # No frame was sent for the leave.
            assert len(ws.sent) == state["frames_before"]
            # A broadcast to the old session no longer reaches this socket.
            await _probe(session)()
            # The running turn was not cancelled: release it and let it finish.
            gate.set()
            await _drain_turns()
            state["touched"] = session.last_activity

        ws = FakeWebSocket(
            [
                _start(sid, "slow"),
                Wait(recorder.started("slow")),
                Do(_before_leave),
                {"action": "leave"},
                Do(_after_leave),
            ]
        )
        await _run(ws)

        # Only the joined frame ever reached this socket: no probe, no
        # assistant/done from the turn that completed after the leave.
        assert ws.types() == ["session_joined"]
        # The turn completed and persisted (it was never cancelled).
        assert await _persisted(sid) == [("user", "slow"), ("assistant", "reply to slow")]
        # The disconnect after `leave` saw no bound session and did nothing.
        assert state["session"].last_activity == state["touched"]

    async def test_leave_without_a_bound_session_is_a_noop(self) -> None:
        ws = FakeWebSocket([{"action": "leave"}, {"action": "list_sessions"}])
        await _run(ws)
        assert ws.types() == ["session_list"]

    async def test_leave_after_the_bound_session_was_deleted(self, recorder: _Recorder) -> None:
        sid = _sid(2)

        async def _delete_elsewhere() -> None:
            other = FakeWebSocket([{"action": "delete_session", "session_id": sid}])
            await websocket_endpoint(other)  # type: ignore[arg-type]
            assert other.types() == ["session_deleted"]

        ws = FakeWebSocket(
            [
                _start(sid),
                WaitFrame("done"),
                Do(_delete_elsewhere),
                {"action": "leave"},
                {"action": "list_sessions"},
            ]
        )
        await _run(ws)
        assert ws.types()[-1] == "session_list"
        assert ws.frames("session_list")[0]["sessions"] == []
        assert "system" not in ws.types()
        assert sid not in app_module._sessions
        assert await _row_ids() == set()


# ── AC3: start_session validation ─────────────────────────────────────────

_BAD_IMAGE = [{"media_type": "image/png", "data": "abc", "bogus_key": "x"}]
_OVERSIZED = [
    {"media_type": "image/png", "data": "A" * (int((IMAGE_ATTACHMENT_CAP_BYTES + 1) * 4 / 3) + 4)}
]


@pytest.mark.parametrize(
    ("payload", "echo", "error"),
    [
        (
            {"action": "start_session", "agent_name": "alpha", "message": "hi"},
            None,
            "Invalid session id.",
        ),
        (_start(None), None, "Invalid session id."),
        (_start(12345), None, "Invalid session id."),
        (_start(["x"]), None, "Invalid session id."),
        (_start("abc123"), "abc123", "Invalid session id."),
        (_start("0123456789ab"), "0123456789ab", "Invalid session id."),
        (_start("A" * 32), "A" * 32, "Invalid session id."),
        (_start("a" * 33), "a" * 33, "Invalid session id."),
        (_start("g" * 32), "g" * 32, "Invalid session id."),
        (_start(_sid(7) + "\n"), _sid(7) + "\n", "Invalid session id."),
        (
            {"action": "start_session", "session_id": _sid(7), "message": "hi"},
            _sid(7),
            "Invalid agent name.",
        ),
        (_start(_sid(7), agent=""), _sid(7), "Invalid agent name."),
        (_start(_sid(7), agent="default"), _sid(7), "Invalid agent name."),
        (_start(_sid(7), agent="Default"), _sid(7), "Invalid agent name."),
        # M36 F1 L04: exactly `GleepGlorp` is admitted (TestGleepGlorp); any other spelling is not.
        (_start(_sid(7), agent="gleepglorp"), _sid(7), "Invalid agent name."),
        (_start(_sid(7), agent="GLEEPGLORP"), _sid(7), "Invalid agent name."),
        (_start(_sid(7), agent=7), _sid(7), "Invalid agent name."),
        (_start(_sid(7), message=""), _sid(7), "Message is empty."),
        (_start(_sid(7), message=None), _sid(7), "Message is empty."),
        (_start(_sid(7), message="", images=[]), _sid(7), "Message is empty."),
        (_start(_sid(7), message="/reset"), _sid(7), "A new chat cannot start with /reset."),
        (_start(_sid(7), message=5), _sid(7), "Message must be text."),
        (
            _start(_sid(7), images=123),
            _sid(7),
            "Malformed images payload; expected a list of image objects.",
        ),
        (
            _start(
                _sid(7),
                images=[{"media_type": "image/png", "data": "Zm9v"}]
                * (IMAGE_ATTACHMENT_MAX_COUNT + 1),
            ),
            _sid(7),
            f"Too many images attached ({IMAGE_ATTACHMENT_MAX_COUNT + 1}); "
            f"max is {IMAGE_ATTACHMENT_MAX_COUNT}.",
        ),
        (
            _start(_sid(7), images=_OVERSIZED),
            _sid(7),
            f"An attached image exceeds the {IMAGE_ATTACHMENT_CAP_BYTES // (1024 * 1024)} "
            "MB per-image limit.",
        ),
        (_start(_sid(7), message="", images=_BAD_IMAGE), _sid(7), "Cannot process message: "),
    ],
    ids=[
        "sid-absent",
        "sid-null",
        "sid-int",
        "sid-list",
        "sid-short",
        "sid-server-12-hex",
        "sid-uppercase",
        "sid-33",
        "sid-non-hex",
        "sid-trailing-newline",
        "agent-absent",
        "agent-empty",
        "agent-default",
        "agent-Default",
        "agent-gleepglorp",
        "agent-GLEEPGLORP",
        "agent-int",
        "message-empty",
        "message-null",
        "message-empty-images",
        "message-reset",
        "message-int",
        "images-malformed",
        "images-too-many",
        "images-oversized",
        "content-build-failure",
    ],
)
async def test_start_session_rejects_and_creates_nothing(
    recorder: _Recorder, payload: dict, echo: str | None, error: str
) -> None:
    bound = _sid(99)
    await _precreate(bound)
    ws = FakeWebSocket(
        [
            {"action": "join", "session_id": bound},
            payload,
            Do(_probe(bound)),
            {"action": "list_sessions"},
        ]
    )
    await _run(ws)

    failed = ws.frames("start_failed")
    assert len(failed) == 1
    assert failed[0]["session_id"] == echo
    if error.endswith(": "):
        assert failed[0]["error"].startswith(error)
    else:
        assert failed[0]["error"] == error
    # Exactly: the join, the rejection, the probe (still bound), the list.
    assert ws.types() == ["session_joined", "start_failed", "probe", "session_list"]
    # Nothing created, nothing processed (never fell into the message path).
    assert set(app_module._sessions) == {bound}
    assert await _row_ids() == {bound}
    assert recorder.steps == []
    assert app_module._start_reservations == {}


# ── AC4: an existing id joins ─────────────────────────────────────────────


class TestExistingIdJoins:
    async def test_resend_is_idempotent_on_one_socket_and_across_sockets(
        self, recorder: _Recorder, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sid = _sid(3)
        real_create = app_module._create_session
        create_calls: list[Any] = []

        async def _counting_create(*args: Any, **kwargs: Any) -> Any:
            create_calls.append(kwargs.get("session_id"))
            return await real_create(*args, **kwargs)

        monkeypatch.setattr(app_module, "_create_session", _counting_create)

        a = FakeWebSocket(
            [
                _start(sid, "hello"),
                WaitFrame("session_joined"),
                _start(sid, "hello"),
                WaitFrame("session_joined", 2),
                WaitFrame("done"),
            ]
        )
        await _run(a)
        b = FakeWebSocket([_start(sid, "hello"), WaitFrame("session_joined")])
        await _run(b)

        assert [f["session_id"] for f in a.frames("session_joined")] == [sid, sid]
        assert [f["session_id"] for f in b.frames("session_joined")] == [sid]
        assert a.frames("start_failed") == [] and b.frames("start_failed") == []
        assert create_calls == [sid]
        assert set(app_module._sessions) == {sid}
        assert await _row_ids() == {sid}
        assert recorder.steps == [("alpha", "hello")]
        assert await _persisted(sid) == [("user", "hello"), ("assistant", "reply to hello")]

    async def test_existing_empty_session_delivers_the_message_exactly_once(
        self, recorder: _Recorder
    ) -> None:
        """A session persisted empty (a disconnect between the create and the
        spawn) gets its first message on the re-send; a second re-send, with
        history now present, does not process it again."""
        sid = _sid(4)
        await _precreate(sid)
        first = FakeWebSocket([_start(sid, "first"), WaitFrame("done")])
        await _run(first)
        again = FakeWebSocket([_start(sid, "first"), WaitFrame("session_joined")])
        await _run(again)

        assert first.frames("session_joined")[0]["is_processing"] is True
        assert again.frames("session_joined")[0]["is_processing"] is False
        assert recorder.steps == [("alpha", "first")]
        assert await _persisted(sid) == [("user", "first"), ("assistant", "reply to first")]

    async def test_existing_session_of_another_agent_is_joined(self, recorder: _Recorder) -> None:
        sid = _sid(5)
        await _run(FakeWebSocket([_start(sid, "one", agent="alpha"), WaitFrame("done")]))
        ws = FakeWebSocket([_start(sid, "two", agent="beta"), WaitFrame("session_joined")])
        await _run(ws)

        joined = ws.frames("session_joined")[0]
        assert joined["session_id"] == sid
        assert joined["agent_name"] == "alpha"
        assert "beta" not in recorder.creates
        assert recorder.steps == [("alpha", "one")]
        assert await _row_ids() == {sid}

    @pytest.mark.parametrize("exc", [RuntimeError("db down"), ImportError("no provider module")])
    async def test_lookup_failure_sends_start_failed_and_keeps_the_socket(
        self, recorder: _Recorder, monkeypatch: pytest.MonkeyPatch, exc: BaseException
    ) -> None:
        async def _boom(_sid: str) -> Any:
            raise exc

        monkeypatch.setattr(app_module, "_get_or_restore_session", _boom)
        sid = _sid(6)
        ws = FakeWebSocket([_start(sid), {"action": "list_sessions"}])
        await _run(ws)

        assert ws.types() == ["start_failed", "session_list"]
        assert ws.sent[0] == {
            "type": "start_failed",
            "session_id": sid,
            "error": f"Cannot start chat: {exc}",
        }
        assert app_module._sessions == {}
        assert await _row_ids() == set()
        assert recorder.steps == []
        assert app_module._start_reservations == {}

    @pytest.mark.parametrize("same_id", [True, False], ids=["same-id", "other-id"])
    async def test_degraded_existing_id_unbinds_whatever_was_bound(
        self, recorder: _Recorder, same_id: bool
    ) -> None:
        bound, target = _sid(10), _sid(11)
        state: dict[str, Any] = {}
        if not same_id:
            await _precreate(target, agent="ghost")

        def _delete_agent() -> None:
            state["bound"] = app_module._sessions[bound]
            recorder.missing_agents.update({"alpha", "ghost"})

        ws = FakeWebSocket(
            [
                _start(bound, "first"),
                WaitFrame("done"),
                Do(_drain_turns),
                Do(_delete_agent),
                _start(bound if same_id else target, "again"),
                Do(lambda: _probe(state["bound"])()),
                {"action": "list_sessions"},
            ]
        )
        await _run(ws)

        degraded = ws.frames("session_joined")[-1]
        assert degraded["status"] == "agent_deleted"
        assert degraded["session_id"] == (bound if same_id else target)
        # Unbound: the probe to the previously bound session never arrived.
        assert "probe" not in ws.types()
        assert ws.types()[-1] == "session_list"
        assert ws.frames("start_failed") == []
        assert recorder.steps == [("alpha", "first")]

    async def test_degraded_same_id_rejoin_unsubscribes_the_socket(
        self, recorder: _Recorder
    ) -> None:
        """Squawk 0119: `join` of the already-bound id, degraded, drops the sub."""
        sid = _sid(12)
        await _precreate(sid)
        state: dict[str, Any] = {}

        def _delete_agent() -> None:
            state["session"] = app_module._sessions[sid]
            recorder.missing_agents.add("alpha")

        ws = FakeWebSocket(
            [
                {"action": "join", "session_id": sid},
                Do(lambda: state.__setitem__("bound", ws in app_module.subscribers_for(sid))),
                Do(_delete_agent),
                {"action": "join", "session_id": sid},
                Do(lambda: _probe(state["session"])()),
                {"action": "list_sessions"},
            ]
        )
        await _run(ws)

        assert state["bound"] is True
        assert ws.frames("session_joined")[-1]["status"] == "agent_deleted"
        assert ws not in app_module.subscribers_for(sid)
        assert "probe" not in ws.types()


# ── AC5: the reservation ──────────────────────────────────────────────────


class TestReservation:
    async def test_concurrent_starts_create_once(
        self, recorder: _Recorder, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sid = _sid(20)
        create = _ParkingCreate(app_module._create_session)
        monkeypatch.setattr(app_module, "_create_session", create)
        a = FakeWebSocket([_start(sid, "from A"), WaitFrame("done")])
        b = FakeWebSocket([Wait(create.inside), _start(sid, "from B"), WaitFrame("session_joined")])

        async def _director() -> None:
            await asyncio.wait_for(create.inside.wait(), STEP_TIMEOUT_S)
            await _settle(b, 1)  # B is now waiting on A's reservation
            create.release.set()

        await asyncio.wait_for(
            asyncio.gather(
                websocket_endpoint(a),  # type: ignore[arg-type]
                websocket_endpoint(b),  # type: ignore[arg-type]
                _director(),
            ),
            STEP_TIMEOUT_S * 3,
        )
        await _drain_turns()

        assert create.calls == [sid]
        assert [f["session_id"] for f in a.frames("session_joined")] == [sid]
        assert [f["session_id"] for f in b.frames("session_joined")] == [sid]
        assert a.frames("start_failed") == [] and b.frames("start_failed") == []
        assert recorder.steps == [("alpha", "from A")]
        assert set(app_module._sessions) == {sid}
        assert await _row_ids() == {sid}
        assert app_module._start_reservations == {}

    async def test_failed_creator_hands_over_to_the_waiter(
        self, recorder: _Recorder, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sid = _sid(21)
        create = _ParkingCreate(app_module._create_session, fail_first=RuntimeError("boom"))
        monkeypatch.setattr(app_module, "_create_session", create)
        a = FakeWebSocket([_start(sid, "from A"), WaitFrame("start_failed")])
        b = FakeWebSocket([Wait(create.inside), _start(sid, "from B"), WaitFrame("done")])

        async def _director() -> None:
            await asyncio.wait_for(create.inside.wait(), STEP_TIMEOUT_S)
            await _settle(b, 1)
            create.release.set()

        await asyncio.wait_for(
            asyncio.gather(
                websocket_endpoint(a),  # type: ignore[arg-type]
                websocket_endpoint(b),  # type: ignore[arg-type]
                _director(),
            ),
            STEP_TIMEOUT_S * 3,
        )
        await _drain_turns()

        assert a.sent == [
            {"type": "start_failed", "session_id": sid, "error": "Cannot start chat: boom"}
        ]
        assert [f["session_id"] for f in b.frames("session_joined")] == [sid]
        assert b.frames("session_joined")[0]["is_processing"] is True
        assert create.calls == [sid, sid]
        assert recorder.steps == [("alpha", "from B")]
        assert set(app_module._sessions) == {sid}
        assert await _row_ids() == {sid}
        assert await _persisted(sid) == [("user", "from B"), ("assistant", "reply to from B")]

    async def test_a_waiter_timeout_does_not_cancel_the_shared_reservation(
        self, recorder: _Recorder, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sid = _sid(22)
        monkeypatch.setattr(app_module, "_START_RESERVATION_WAIT_S", 1.0)
        create = _ParkingCreate(app_module._create_session)
        monkeypatch.setattr(app_module, "_create_session", create)
        c_go = asyncio.Event()
        a = FakeWebSocket([_start(sid, "from A"), WaitFrame("done")])
        b = FakeWebSocket([Wait(create.inside), _start(sid, "from B"), WaitFrame("start_failed")])
        c = FakeWebSocket([Wait(c_go), _start(sid, "from C"), WaitFrame("session_joined")])

        async def _director() -> None:
            await asyncio.wait_for(create.inside.wait(), STEP_TIMEOUT_S)
            # B times out on its own wait ...
            await _until(lambda: bool(b.frames("start_failed")))
            # ... then C starts waiting on the same (still pending) reservation.
            c_go.set()
            await _settle(c, 1)
            create.release.set()

        await asyncio.wait_for(
            asyncio.gather(
                websocket_endpoint(a),  # type: ignore[arg-type]
                websocket_endpoint(b),  # type: ignore[arg-type]
                websocket_endpoint(c),  # type: ignore[arg-type]
                _director(),
            ),
            STEP_TIMEOUT_S * 3,
        )
        await _drain_turns()

        assert b.sent == [
            {
                "type": "start_failed",
                "session_id": sid,
                "error": "Timed out waiting for this chat to start.",
            }
        ]
        assert [f["session_id"] for f in a.frames("session_joined")] == [sid]
        assert [f["session_id"] for f in c.frames("session_joined")] == [sid]
        assert create.calls == [sid]
        assert recorder.steps == [("alpha", "from A")]
        assert await _row_ids() == {sid}
        assert app_module._start_reservations == {}


# ── AC6: the strict create ────────────────────────────────────────────────


async def _gleepglorp(*, provider: str = "p1", **over: Any) -> None:
    """Store GleepGlorp's settings (a provider row is inserted unless `provider` is not `p1`)."""
    from the_one.gleepglorp import GleepGlorpSettings, save_settings

    conn = await get_connection()
    await conn.execute(
        "INSERT OR IGNORE INTO llm_providers (id, name, type, base_url) "
        "VALUES ('p1', 'P', 'ollama', 'http://x')"
    )
    await conn.commit()
    fields: dict[str, Any] = {"provider_config_id": provider, "model": "m"}
    fields.update(over)
    await save_settings(conn, GleepGlorpSettings(**fields))


_UNAVAILABLE = {
    "off": ({"enabled": False}, "GleepGlorp is turned off.", "gleepglorp_off"),
    "needs_model": (
        {"provider_config_id": None, "model": None},
        "GleepGlorp needs a model.",
        "gleepglorp_needs_model",
    ),
    "provider_missing": (
        {"provider": "gone"},
        "GleepGlorp's model provider was removed.",
        "gleepglorp_provider_missing",
    ),
}


class TestGleepGlorp:
    """M36 F1 L04: the built-in assistant over the WebSocket."""

    async def test_start_admits_the_exact_name_and_runs_the_turn(self, recorder: _Recorder) -> None:
        sid = _sid(70)
        await _gleepglorp()
        ws = FakeWebSocket([_start(sid, "hi", agent="GleepGlorp"), WaitFrame("done")])
        await _run(ws)
        assert ws.sent[0]["status"] == "ok"
        assert ws.sent[0]["agent_name"] == "GleepGlorp"
        assert (await (await _repo()).get(sid)).agent_name == "GleepGlorp"
        assert recorder.steps == [("GleepGlorp", "hi")]

    @pytest.mark.parametrize("state", sorted(_UNAVAILABLE))
    async def test_start_unavailable_sends_the_sentence_and_stores_nothing(
        self, recorder: _Recorder, state: str
    ) -> None:
        from the_one.agent.factory import GleepGlorpUnavailableError

        sid = _sid(71)
        recorder.fail_create = GleepGlorpUnavailableError(state)
        ws = FakeWebSocket([_start(sid, "hi", agent="GleepGlorp"), {"action": "list_sessions"}])
        await _run(ws)
        failed = ws.frames("start_failed")
        assert [f["error"] for f in failed] == [_UNAVAILABLE[state][1]]
        assert await _row_ids() == set()
        assert recorder.steps == []

    @pytest.mark.parametrize("state", sorted(_UNAVAILABLE))
    async def test_join_of_a_stored_chat_is_degraded_with_its_status(
        self, recorder: _Recorder, state: str
    ) -> None:
        from the_one.agent.factory import GleepGlorpUnavailableError

        sid = _sid(72)
        await _precreate(sid, "GleepGlorp")
        app_module._sessions.pop(sid, None)
        recorder.fail_create = GleepGlorpUnavailableError(state)
        ws = FakeWebSocket([{"action": "join", "session_id": sid}])
        await _run(ws)
        joined = ws.frames("session_joined")
        assert [f["status"] for f in joined] == [_UNAVAILABLE[state][2]]
        assert joined[0]["agent_name"] == "GleepGlorp"
        assert app_module.RestoredSession(None, _UNAVAILABLE[state][2]).is_degraded

    @pytest.mark.parametrize("state", sorted(_UNAVAILABLE))
    async def test_a_message_is_refused_from_the_settings_read_now(
        self, recorder: _Recorder, state: str
    ) -> None:
        sid = _sid(73)
        await _gleepglorp()
        await _precreate(sid, "GleepGlorp")  # built while ready: the session caches that
        await _gleepglorp(**_UNAVAILABLE[state][0])
        ws = FakeWebSocket(
            [
                {"action": "list_sessions"},
                Do(lambda: app_module.add_subscriber(sid, ws)),
                Do(lambda: _spawn_to(sid, ws, "hello")),
                WaitFrame("system"),
            ]
        )
        await _run(ws)
        assert [f["content"] for f in ws.frames("system")] == [_UNAVAILABLE[state][1]]
        assert ws.frames("done") == []
        assert recorder.steps == []
        assert await _persisted(sid) == []

    async def test_a_message_runs_while_ready(self, recorder: _Recorder) -> None:
        sid = _sid(74)
        await _gleepglorp()
        await _precreate(sid, "GleepGlorp")
        ws = FakeWebSocket(
            [
                {"action": "list_sessions"},
                Do(lambda: app_module.add_subscriber(sid, ws)),
                Do(lambda: _spawn_to(sid, ws, "hello")),
                WaitFrame("done"),
            ]
        )
        await _run(ws)
        assert recorder.steps == [("GleepGlorp", "hello")]


def _spawn_to(sid: str, ws: Any, text: str) -> None:
    app_module._spawn_web_message(app_module._sessions[sid], text, ws)


class TestStrictCreate:
    @pytest.mark.parametrize("failure", ["factory", "persist"])
    async def test_create_failure_leaves_nothing_and_keeps_the_binding(
        self, recorder: _Recorder, monkeypatch: pytest.MonkeyPatch, failure: str
    ) -> None:
        bound, sid = _sid(30), _sid(31)
        await _precreate(bound)

        async def _failing_insert(self: Any, session: Any) -> None:  # noqa: ARG001
            raise sqlite3.IntegrityError("UNIQUE constraint failed: chat_sessions.id")

        def _arm() -> None:
            if failure == "factory":
                recorder.fail_create = RuntimeError("no provider")
            else:
                monkeypatch.setattr(ChatSessionRepository, "create", _failing_insert)

        ws = FakeWebSocket(
            [
                {"action": "join", "session_id": bound},
                Do(_arm),
                _start(sid),
                Do(_probe(bound)),
                {"action": "list_sessions"},
            ]
        )
        await _run(ws)

        assert ws.types() == ["session_joined", "start_failed", "probe", "session_list"]
        failed = ws.frames("start_failed")[0]
        assert failed["session_id"] == sid
        expected = "no provider" if failure == "factory" else "UNIQUE constraint failed"
        assert failed["error"].startswith("Cannot start chat: ")
        assert expected in failed["error"]
        assert set(app_module._sessions) == {bound}
        assert await _row_ids() == {bound}
        assert recorder.steps == []

    async def test_strict_create_pops_on_cancellation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sid = _sid(32)
        parked = asyncio.Event()

        async def _parked_insert(self: Any, session: Any) -> None:  # noqa: ARG001
            parked.set()
            await asyncio.Event().wait()

        monkeypatch.setattr(ChatSessionRepository, "create", _parked_insert)
        task = asyncio.create_task(
            app_module._create_session(agent_name="alpha", session_id=sid, strict=True)
        )
        await asyncio.wait_for(parked.wait(), STEP_TIMEOUT_S)
        assert sid in app_module._sessions
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert sid not in app_module._sessions

    async def test_non_strict_create_still_swallows_a_persist_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sid = _sid(33)

        async def _failing_insert(self: Any, session: Any) -> None:  # noqa: ARG001
            raise sqlite3.OperationalError("disk I/O error")

        monkeypatch.setattr(ChatSessionRepository, "create", _failing_insert)
        session = await app_module._create_session(agent_name="alpha", session_id=sid)
        assert app_module._sessions[sid] is session
        assert await _row_ids() == set()


# ── AC7: swap, joined, spawn ──────────────────────────────────────────────


class TestSwapJoinedSpawn:
    async def test_frame_order_and_persistence(self, recorder: _Recorder) -> None:
        sid = _sid(40)
        ws = FakeWebSocket([_start(sid, "hello"), WaitFrame("done")])
        await _run(ws)

        joined = ws.sent[0]
        assert joined["type"] == "session_joined"
        assert joined["session_id"] == sid
        assert joined["status"] == "ok"
        assert joined["agent_name"] == "alpha"
        assert joined["is_processing"] is True
        turn = [t for t in ws.types() if t.startswith("assistant") or t == "done"]
        assert turn == ["assistant", "done"]
        assert ws.frames("assistant")[0]["content"] == "reply to hello"
        assert ws.types().index("session_joined") < ws.types().index("assistant")

        row = await (await _repo()).get(sid)
        assert row.agent_name == "alpha"
        assert row.title == "hello"
        assert await _persisted(sid) == [("user", "hello"), ("assistant", "reply to hello")]
        assert recorder.steps == [("alpha", "hello")]

    async def test_swap_leaves_a_running_turn_which_completes(self, recorder: _Recorder) -> None:
        first, second = _sid(41), _sid(42)
        gate = recorder.gates["slow"] = asyncio.Event()

        async def _release_slow() -> None:
            gate.set()
            await _drain_turns()

        ws = FakeWebSocket(
            [
                _start(first, "slow"),
                Wait(recorder.started("slow")),
                _start(second, "fast"),
                WaitFrame("done"),
                Do(_release_slow),
                Do(_probe(first)),
            ]
        )
        await _run(ws)

        assert [f["session_id"] for f in ws.frames("session_joined")] == [first, second]
        # Only the new session's turn reached this socket.
        assert [f["content"] for f in ws.frames("assistant")] == ["reply to fast"]
        assert len(ws.frames("done")) == 1
        assert "probe" not in ws.types()
        # The old session's turn completed and persisted anyway.
        assert await _persisted(first) == [("user", "slow"), ("assistant", "reply to slow")]
        assert await _persisted(second) == [("user", "fast"), ("assistant", "reply to fast")]

    async def test_resend_after_a_disconnect_before_the_spawn_delivers_once(
        self, recorder: _Recorder
    ) -> None:
        """The socket drops while sending `session_joined`: the session was
        created and bound (so no `start_failed`), the outer disconnect handler
        unsubscribed it (bind-before-send), and nothing was spawned. The
        re-send on a fresh socket delivers the first message."""
        sid = _sid(43)
        dropped = FakeWebSocket([_start(sid, "hello")], fail_send_on="session_joined")
        await _run(dropped)

        assert dropped.sent == []
        assert sid in app_module._sessions
        assert subscribers_for(sid) == set()
        assert await _row_ids() == {sid}
        assert recorder.steps == []

        again = FakeWebSocket([_start(sid, "hello"), WaitFrame("done")])
        await _run(again)
        assert again.frames("session_joined")[0]["is_processing"] is True
        assert recorder.steps == [("alpha", "hello")]
        assert await _persisted(sid) == [("user", "hello"), ("assistant", "reply to hello")]


# ── AC8: the broadened bare-message auto-create catch ─────────────────────


async def test_bare_message_auto_create_import_error_keeps_the_socket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _import_error(*args: Any, **kwargs: Any) -> Any:  # noqa: ARG001
        raise ImportError("No module named 'the_one.llm.frozen_out'")

    monkeypatch.setattr(app_module, "_create_session", _import_error)
    ws = FakeWebSocket([{"action": "message", "message": "hi"}, {"action": "list_sessions"}])
    await _run(ws)
    assert ws.types() == ["system", "session_list"]
    assert ws.sent[0]["content"] == "Cannot start chat: No module named 'the_one.llm.frozen_out'"


# ── AC8a: join of an unknown id ───────────────────────────────────────────


class TestJoinFailed:
    @pytest.mark.parametrize("deleted_while_bound", [False, True], ids=["unknown", "deleted"])
    async def test_join_unknown_id_fails_creates_nothing_and_unbinds(
        self, recorder: _Recorder, deleted_while_bound: bool
    ) -> None:
        bound = _sid(50)
        target = bound if deleted_while_bound else _sid(51)
        await _precreate(bound)
        state: dict[str, Any] = {}

        async def _delete_row() -> None:
            state["bound"] = app_module._sessions[bound]
            if deleted_while_bound:
                await (await _repo()).delete(bound)

        ws = FakeWebSocket(
            [
                {"action": "join", "session_id": bound},
                Do(_delete_row),
                {"action": "join", "session_id": target},
                Do(lambda: _probe(state["bound"])()),
                {"action": "list_sessions"},
            ]
        )
        creates_before = len(recorder.creates)
        await _run(ws)

        assert ws.types() == ["session_joined", "join_failed", "session_list"]
        assert ws.frames("join_failed")[0] == {
            "type": "join_failed",
            "session_id": target,
            "error": "not_found",
        }
        # Nothing created: no new session, row or agent build.
        expected = set() if deleted_while_bound else {bound}
        assert await _row_ids() == expected
        assert set(app_module._sessions) <= {bound}
        assert target == bound or target not in app_module._sessions
        # One rebuild for the first join; none for the failed one.
        assert len(recorder.creates) == creates_before + 1

    async def test_join_without_an_id_is_refused_and_creates_nothing(
        self, recorder: _Recorder
    ) -> None:
        ws = FakeWebSocket([{"action": "join"}, {"action": "list_sessions"}])
        await _run(ws)
        assert ws.frames("session_joined") == []
        assert ws.frames("system")[0]["content"].startswith("Cannot start chat: ")
        assert recorder.creates == []
        assert app_module._sessions == {}
        assert await _row_ids() == set()


# ── AC8b: the restore guard ───────────────────────────────────────────────


class TestRestoreGuard:
    async def test_no_rebuild_while_a_turn_is_registered_in_flight(
        self, recorder: _Recorder
    ) -> None:
        sid = _sid(60)
        session = await _precreate(sid)
        session.history = [{"type": "user", "content": "in flight"}]
        pending = asyncio.create_task(asyncio.Event().wait())
        _session_inflight[sid] = {pending}
        try:
            creates_before = len(recorder.creates)
            restored = await app_module._restore_session(sid)
            assert restored.session is session
            assert session.history == [{"type": "user", "content": "in flight"}]
            assert len(recorder.creates) == creates_before
        finally:
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
            _session_inflight.clear()

        # Control: with nothing in flight the rebuild runs again.
        restored = await app_module._restore_session(sid)
        assert restored.session is session
        assert session.history == []
        assert len(recorder.creates) == creates_before + 1


class TestRestoreNotFoundVsReservation:
    async def test_not_found_join_keeps_a_reserved_cached_session(
        self, recorder: _Recorder
    ) -> None:
        """Flight-end R2: `_create_session` caches the session before its row
        lands; a not-found restore for an id held in `_start_reservations`
        must not evict it. Without a reservation it still pops."""
        sid = _sid(61)
        session = await _precreate(sid)
        # Simulate the window: cached, but the DB row does not exist yet.
        repo = await app_module._chat_repo()
        await repo.delete(sid)
        fut: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        app_module._start_reservations[sid] = fut
        try:
            restored = await app_module._restore_session(sid)
            assert restored.session is None
            assert app_module._sessions.get(sid) is session
        finally:
            app_module._start_reservations.pop(sid, None)
        # Control: with the reservation gone the not-found path evicts it.
        restored = await app_module._restore_session(sid)
        assert restored.session is None
        assert sid not in app_module._sessions


# ── M25 F4 leg 3b (AC15): new_session is removed ──────────────────────────


async def test_new_session_is_gone_and_creates_nothing(recorder: _Recorder) -> None:
    """Leg 3b removed the `new_session` branch (no client sends it: a pick is a
    `leave`, the first send a `start_session`). The frame now falls through to
    the message path, whose shared validator finds an empty payload and
    `continue`s: no reply, no session, no row."""
    ws = FakeWebSocket([{"action": "new_session", "agent_name": "alpha"}])
    await _run(ws)
    assert ws.frames("session_joined") == []
    assert ws.frames("system") == []
    assert await _row_ids() == set()
    assert recorder.creates == []


# ── Squawk 0120: exactly one `cancelled` per `cancel` ─────────────────────


class TestCancelSendsExactlyOneCancelled:
    async def test_a_cancel_before_the_spawned_task_starts(self, recorder: _Recorder) -> None:
        sid = _sid(30)
        await _precreate(sid)
        ws = FakeWebSocket(
            [
                {"action": "join", "session_id": sid},
                {"action": "message", "message": "never"},
                NoYield({"action": "cancel"}),
                WaitFrame("cancelled"),
                Do(_drain_turns),
            ]
        )
        await _run(ws)

        assert len(ws.frames("cancelled")) == 1
        assert recorder.steps == []
        assert not app_module.session_locks[sid].locked()
        assert app_module._session_inflight == {}
        assert app_module._cancel_tokens == {}
        assert not app_module.is_session_processing(sid)

    async def test_a_cancel_while_the_task_waits_on_the_session_lock(
        self, recorder: _Recorder
    ) -> None:
        sid = _sid(31)
        await _precreate(sid)
        lock = app_module.session_locks[sid]
        await lock.acquire()
        released: list[bool] = []

        def _release() -> None:
            lock.release()
            released.append(True)

        ws = FakeWebSocket(
            [
                {"action": "join", "session_id": sid},
                {"action": "message", "message": "queued"},
                Do(lambda: _until(lambda: len(app_module._started_tasks) == 1)),
                {"action": "cancel"},
                WaitFrame("cancelled"),
                Do(_release),
                Do(_drain_turns),
            ]
        )
        await _run(ws)

        assert released == [True]
        assert len(ws.frames("cancelled")) == 1
        assert recorder.steps == []
        assert not lock.locked()
        assert app_module._session_inflight == {}
        assert app_module._cancel_tokens == {}
        assert not app_module.is_session_processing(sid)

    async def test_a_cancel_of_a_running_turn(self, recorder: _Recorder) -> None:
        sid = _sid(32)
        await _precreate(sid)
        recorder.gates["slow"] = asyncio.Event()
        ws = FakeWebSocket(
            [
                {"action": "join", "session_id": sid},
                {"action": "message", "message": "slow"},
                Wait(recorder.started("slow")),
                {"action": "cancel"},
                WaitFrame("cancelled"),
                Do(_drain_turns),
            ]
        )
        await _run(ws)

        assert len(ws.frames("cancelled")) == 1
        assert not app_module.session_locks[sid].locked()
        assert app_module._session_inflight == {}
        assert app_module._cancel_tokens == {}
        assert not app_module.is_session_processing(sid)

    async def test_one_cancel_over_a_running_turn_and_an_unstarted_one(
        self, recorder: _Recorder
    ) -> None:
        sid = _sid(33)
        await _precreate(sid)
        recorder.gates["slow"] = asyncio.Event()
        ws = FakeWebSocket(
            [
                {"action": "join", "session_id": sid},
                {"action": "message", "message": "slow"},
                Wait(recorder.started("slow")),
                {"action": "message", "message": "second"},
                NoYield({"action": "cancel"}),
                WaitFrame("cancelled"),
                Do(_drain_turns),
            ]
        )
        await _run(ws)

        cancelled_at = ws.types().index("cancelled")
        assert len(ws.frames("cancelled")) == 1
        assert recorder.steps == [("alpha", "slow")]
        assert not app_module.session_locks[sid].locked()
        assert app_module._session_inflight == {}
        assert app_module._cancel_tokens == {}
        assert not app_module.is_session_processing(sid)
        assert cancelled_at == len(ws.types()) - 1 or "done" not in ws.types()[cancelled_at:]
