"""Routine handling on the web turn path (Mission 33 F1 L3, AC3-AC7)."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timezone
from typing import Any

import pytest

from the_one.interfaces.web import app as web_app
from the_one.interfaces.web.app import (
    Session,
    _inflight_tasks,
    _session_inflight,
    _silent_cancel,
    _spawn_message_processing,
    _spawn_routine_turn,
)
from the_one.llm.base import OPERATOR_VISIBILITY, Message, Role, ToolCall, ToolResult
from the_one.sessions import clear_for_test as _clear_session_registry
from the_one.sessions import is_session_busy


class _LLMShim:
    max_context_tokens = 128_000


class _Agent:
    """Appends the user message like ``Agent.step`` then follows a script."""

    stopped_at_step_limit = False
    max_iterations = 5

    def __init__(self, mode: str = "ok", reply: str = "the reply") -> None:
        self.messages: list[Message] = []
        self.llm = _LLMShim()
        self._deferred_tool_calls = None
        self.mode = mode
        self.reply = reply
        self.started = asyncio.Event()
        self.gate = asyncio.Event()

    async def step(self, user_input, on_chunk=None, on_usage=None):
        self.messages.append(Message.user(user_input))
        self.started.set()
        if self.mode == "block":
            await self.gate.wait()
        if self.mode == "raise":
            raise RuntimeError("boom " * 80)
        if self.mode == "pause":
            call = Message.assistant(
                "", tool_calls=[ToolCall(id="c1", name="srv_tool", arguments={})]
            )
            self.messages.append(call)
            yield call
            res = Message(
                role=Role.TOOL,
                content="auth",
                tool_result=ToolResult(
                    "c1", "auth", metadata={"is_auth_required": True, "source_name": "Notion"}
                ),
            )
            self.messages.append(res)
            yield res
            return
        msg = Message.assistant(self.reply)
        self.messages.append(msg)
        yield msg

    async def resume_after_auth(self):  # pragma: no cover
        if False:
            yield


class _Client:
    def __init__(self) -> None:
        self.sent: list[tuple[Any, str]] = []

    async def send(self, target, content):
        self.sent.append((target, content))


class _Manager:
    def __init__(self, client: _Client) -> None:
        self.client = client

    def client_for(self, connector_id):
        return self.client


def _session(agent: _Agent, sid: str = "s-rt", platform: str | None = None) -> Session:
    s = Session(
        id=sid,
        agent=agent,  # type: ignore[arg-type]
        created=datetime.now(timezone.utc).isoformat(),
    )
    s.platform = platform
    return s


def _routine() -> dict[str, Any]:
    return {"id": "r1", "name": "Morning"}


@pytest.fixture(autouse=True)
async def _cleanup():
    yield
    for t in list(_inflight_tasks):
        t.cancel()
    if _inflight_tasks:
        await asyncio.gather(*list(_inflight_tasks), return_exceptions=True)
    _inflight_tasks.clear()
    _session_inflight.clear()
    _silent_cancel.clear()
    _clear_session_registry()


@pytest.fixture
def env(monkeypatch):
    frames: list[dict] = []
    saves: list[list[Message]] = []

    async def fake_send(sess, payload, exclude=None):
        frames.append(payload)

    async def fake_save(sess):
        saves.append([_copy(m) for m in sess.agent.messages])

    async def noop(sess):
        pass

    monkeypatch.setattr(web_app, "_send_to_session", fake_send)
    monkeypatch.setattr(web_app, "_save_session_to_db", fake_save)
    monkeypatch.setattr(web_app, "_ensure_ollama_model_loaded", noop)
    monkeypatch.setattr(web_app, "_resync_session_from_db", noop)
    return frames, saves


def _copy(m: Message) -> Message:
    import copy

    return copy.copy(m)


def _use_manager(monkeypatch, client: _Client) -> None:
    monkeypatch.setattr(web_app, "_connector_manager", _Manager(client))


# ── turn_info keys ────────────────────────────────────────────────────────


async def test_clean_routine_turn_binds_marker_and_events(env):
    frames, saves = env
    session = _session(_Agent())
    info: dict[str, Any] = {"routine": _routine()}
    await web_app._spawn_message_processing(session, "do it", "routine", None, info)

    assert info["started"] is True and "delivery" not in info
    msgs = session.agent.messages
    assert (msgs[0].routine_id, msgs[0].routine_name) == ("r1", "Morning")
    assert msgs[0].visibility is None and msgs[1].visibility is None
    assert saves[-1][0].routine_id == "r1"
    user = next(f for f in frames if f["type"] == "user")
    assert user["source"] == "routine"
    assert user["routine_id"] == "r1" and user["routine_name"] == "Morning"
    assert user["session_id"] == "s-rt"
    assert not any(f["type"] == "session_updated" for f in frames)
    assert frames[-1]["type"] == "done"


async def test_routine_turn_in_a_connector_chat_posts_nothing(env, monkeypatch):
    """A routine reply is never delivered to a platform, even when the chat is a
    connector's and a live client exists (the agent's own send tool is the only way)."""
    client = _Client()
    _use_manager(monkeypatch, client)
    session = _session(_Agent(), platform="stub")
    info: dict[str, Any] = {"routine": _routine()}
    await web_app._spawn_message_processing(session, "do it", "routine", None, info)
    assert client.sent == [] and "delivery" not in info
    assert info["started"] is True and session.agent.messages[0].routine_id == "r1"


class _CapturingAgent(_Agent):
    """Records the TurnContext the app set around ``step`` (M33 F2 L3)."""

    seen = None

    async def step(self, user_input, on_chunk=None, on_usage=None):
        from the_one.agent._context import current_turn

        self.seen = current_turn.get()
        async for m in super().step(user_input, on_chunk, on_usage):
            yield m


async def test_flagged_routine_run_binds_snapshot_and_turn_context(env):
    agent = _CapturingAgent()
    session = _session(agent)
    info: dict[str, Any] = {"routine": {**_routine(), "untrusted_sources": ["web_fetch", "peer:x"]}}
    await web_app._spawn_message_processing(session, "do it", "routine", None, info)
    m = session.agent.messages[0]
    assert m.routine_untrusted_sources == ["web_fetch", "peer:x"]
    ctx = agent.seen
    assert (ctx.routine_id, ctx.routine_name) == ("r1", "Morning")
    assert ctx.routine_sources == ["web_fetch", "peer:x"] and ctx.routine_writes == 0


async def test_unflagged_routine_run_binds_an_empty_list(env):
    agent = _CapturingAgent()
    session = _session(agent)
    info: dict[str, Any] = {"routine": {**_routine(), "untrusted_sources": []}}
    await web_app._spawn_message_processing(session, "do it", "routine", None, info)
    assert session.agent.messages[0].routine_untrusted_sources == []
    assert agent.seen.routine_sources == [] and agent.seen.routine_id == "r1"
    # a Flight 1 style routine dict (no key at all) is also unflagged
    session2 = _session(_CapturingAgent(), sid="s-rt2")
    await web_app._spawn_message_processing(
        session2, "do it", "routine", None, {"routine": _routine()}
    )
    assert session2.agent.messages[0].routine_untrusted_sources == []


async def test_ordinary_turn_has_no_snapshot_and_no_routine_context(env):
    agent = _CapturingAgent()
    session = _session(agent)
    await web_app._spawn_message_processing(session, "hi", "web", None, None)
    assert session.agent.messages[0].routine_untrusted_sources is None
    assert agent.seen.routine_id is None and agent.seen.routine_sources == []


def test_snapshot_round_trips_through_the_codec_and_stays_out_of_ui_events():
    from the_one.db.codec import decode_messages, encode_messages, messages_to_ui_events

    flagged = Message.user("run")
    flagged.routine_id, flagged.routine_name = "r1", "Morning"
    flagged.routine_untrusted_sources = ["web_fetch"]
    empty = Message.user("run 2")
    empty.routine_untrusted_sources = []
    plain = Message.user("hello")
    back = decode_messages(encode_messages([flagged, empty, plain]))
    assert [m.routine_untrusted_sources for m in back] == [["web_fetch"], [], None]
    for ev in messages_to_ui_events(back):
        assert "routine_untrusted_sources" not in ev
    events = messages_to_ui_events(back)
    assert events[0]["routine_id"] == "r1"  # the marker still spreads


async def test_no_routine_no_extra_keys(env):
    session = _session(_Agent())
    info: dict[str, Any] = {}
    await web_app._spawn_message_processing(session, "hi", "web", None, info)
    assert info["started"] is True and info["step_limit"] is False
    assert "delivery" not in info
    assert session.agent.messages[0].routine_id is None


async def test_error_sets_info(env):
    session = _session(_Agent("raise"))
    info: dict[str, Any] = {"routine": _routine()}
    await web_app._spawn_message_processing(session, "x", "routine", None, info)
    assert len(info["error"]) <= 200 and info["error"].startswith("boom")
    assert session.agent.messages[0].routine_id == "r1"


async def test_pause_sets_server(env):
    frames, saves = env
    session = _session(_Agent("pause"))
    info: dict[str, Any] = {"routine": _routine()}
    await web_app._spawn_message_processing(session, "x", "routine", None, info)
    assert info["paused"] == "Notion"
    assert saves and saves[-1][0].routine_id == "r1"
    assert not any(f["type"] == "done" for f in frames)


async def test_cancel_sets_info(env):
    frames, saves = env
    agent = _Agent("block")
    session = _session(agent)
    info: dict[str, Any] = {"routine": _routine()}
    task = asyncio.create_task(_spawn_message_processing(session, "x", "routine", None, info))
    await agent.started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert info["cancelled"] is True
    assert sum(1 for f in frames if f["type"] == "cancelled") == 1
    assert saves[-1][0].routine_id == "r1"  # cancel-path save binds the marker


async def test_step_limit_is_recorded_in_turn_info(env, monkeypatch):
    client = _Client()
    _use_manager(monkeypatch, client)
    agent = _Agent()
    agent.stopped_at_step_limit = True
    session = _session(agent, platform="stub")
    info: dict[str, Any] = {"routine": _routine()}
    await web_app._spawn_message_processing(session, "x", "routine", None, info)
    assert info["step_limit"] is True
    assert client.sent == []  # no platform line for a routine run


# ── cancel-path tagging on every turn ─────────────────────────────────────


async def test_web_cancel_in_connector_chat_tags_operator_only(env):
    agent = _Agent("block")
    session = _session(agent, platform="stub")
    task = asyncio.create_task(_spawn_message_processing(session, "x", "web", None))
    await agent.started.wait()
    # an assistant message appended mid-turn is tagged too
    agent.messages.append(Message.assistant("partial"))
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert all(m.visibility == OPERATOR_VISIBILITY for m in agent.messages)


# ── silent cancel ─────────────────────────────────────────────────────────


async def _queued_behind_holder(env, silent: bool, ws_style: bool = False):
    frames, _ = env
    holder = _Agent("block")
    session = _session(holder, sid="s-q")
    web_task = web_app._spawn_web_message(session, "first", None)  # type: ignore[arg-type]
    await holder.started.wait()
    info: dict[str, Any] = {}
    rt = _spawn_routine_turn(session, "routine prompt", info)
    await asyncio.sleep(0.05)
    assert "started" not in info
    if ws_style:
        web_app._cancel_tokens[session.id] = {"sent": False, "running": False}
    if silent:
        web_app._mark_silent_and_cancel(rt)
    else:
        rt.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await rt
    return frames, holder, web_task, session


async def test_silent_cancel_of_queued_routine_sends_no_cancelled(env):
    frames, holder, web_task, session = await _queued_behind_holder(env, silent=True)
    assert not any(f["type"] == "cancelled" for f in frames)
    assert rt_cleared()
    holder.gate.set()
    await web_task
    assert frames[-1]["type"] == "done"
    assert not any(f["type"] == "cancelled" for f in frames)


def rt_cleared() -> bool:
    return not _silent_cancel


async def test_unmarked_cancel_sends_exactly_one_cancelled(env):
    frames, holder, web_task, _ = await _queued_behind_holder(env, silent=False)
    assert sum(1 for f in frames if f["type"] == "cancelled") == 1
    holder.gate.set()
    await web_task


async def test_ws_style_cancel_of_silent_queued_task_at_most_one(env):
    frames, holder, web_task, _ = await _queued_behind_holder(env, silent=True, ws_style=True)
    assert sum(1 for f in frames if f["type"] == "cancelled") <= 1
    holder.gate.set()
    await web_task


# ── registration and titled sessions ──────────────────────────────────────


async def test_spawn_routine_turn_marks_session_busy(env):
    agent = _Agent("block")
    session = _session(agent, sid="s-busy")
    info: dict[str, Any] = {}
    task = _spawn_routine_turn(session, "go", info)
    assert is_session_busy(session.id)
    assert task in _inflight_tasks and task in _session_inflight[session.id]
    await agent.started.wait()
    agent.gate.set()
    await task
    await asyncio.sleep(0)
    assert not is_session_busy(session.id)
    assert info["started"] is True


async def test_create_session_title(monkeypatch):
    class _Factory:
        async def create(self, name):
            return _Agent()

    class _Repo:
        created = None

        async def create(self, row):
            _Repo.created = row

    async def repo():
        return _Repo()

    monkeypatch.setattr(web_app, "_get_factory", lambda: _Factory())
    monkeypatch.setattr(web_app, "_chat_repo", repo)
    s = await web_app._create_session("a", title="Morning routine")
    try:
        assert s.title == "Morning routine" and _Repo.created.title == "Morning routine"
        s.add_event({"type": "user", "content": "hello"})
        assert s.title == "Morning routine"
    finally:
        web_app._sessions.pop(s.id, None)
