"""Regression: the WebSocket receive loop must NOT block on long tool calls.

Bug surfaced during F4 HAT scenario 1 (`sleep 200` clipped to 120s): the
WebSocket handler `await`-ed `_process_and_broadcast` directly, blocking
the receive loop for the full duration of the agent's reply chain. A
user switching conversations or listing sessions saw nothing for 1-2
minutes until the tool call timed out.

Fix: spawn `_process_and_broadcast` as an `asyncio.Task` via
`_spawn_message_processing`. The session's `processing_lock` serializes
successive messages on the same session; concurrent session-management
actions go through.

These tests verify the spawn-and-lock contract at the helper level
without standing up a real WebSocket — that's covered by the live
container smoke during HAT.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from the_one.interfaces.web.app import (
    Session,
    _inflight_tasks,
    _spawn_message_processing,
)


class _FakeAgent:
    """Stand-in for `the_one.agent.Agent` — only the bits Session uses."""

    def __init__(self) -> None:
        self.messages = []


def _make_session(session_id: str = "s1") -> Session:
    return Session(
        id=session_id,
        agent=_FakeAgent(),  # type: ignore[arg-type]
        created=datetime.now(timezone.utc).isoformat(),
    )


class TestProcessingLock:
    async def test_lock_lazily_created(self) -> None:
        s = _make_session()
        assert s.processing_lock is None  # not bound yet — avoids loop affinity

        # Acquire path: helper creates the lock on first use.
        async def fake_pb(*_a, **_kw) -> None:
            pass

        # Monkey-patch the inner call inside `_spawn_message_processing`
        # so we exercise lock creation without driving an actual agent.
        # We need a way that doesn't import-cycle: reach in via attribute.
        from the_one.interfaces.web import app as app_module

        original = app_module._process_and_broadcast
        app_module._process_and_broadcast = fake_pb  # type: ignore[assignment]
        try:
            await _spawn_message_processing(s, "hi", "web", None)
        finally:
            app_module._process_and_broadcast = original  # type: ignore[assignment]

        assert isinstance(s.processing_lock, asyncio.Lock)

    async def test_second_message_waits_for_first(self) -> None:
        """Two concurrent messages on the same session: the second waits."""
        s = _make_session()
        from the_one.interfaces.web import app as app_module

        order: list[str] = []
        first_started = asyncio.Event()
        first_release = asyncio.Event()

        async def slow_first(*_a, **_kw) -> None:
            order.append("first-start")
            first_started.set()
            await first_release.wait()
            order.append("first-end")

        async def fast_second(*_a, **_kw) -> None:
            order.append("second-start")
            order.append("second-end")

        original = app_module._process_and_broadcast
        try:
            # First task: slow.
            app_module._process_and_broadcast = slow_first  # type: ignore[assignment]
            t1 = asyncio.create_task(_spawn_message_processing(s, "m1", "web", None))
            await first_started.wait()

            # Swap to the fast handler for the second task.
            app_module._process_and_broadcast = fast_second  # type: ignore[assignment]
            t2 = asyncio.create_task(_spawn_message_processing(s, "m2", "web", None))

            # Give the second task a chance to start; it must be blocked
            # on the lock — `second-start` should NOT be in `order` yet.
            await asyncio.sleep(0.05)
            assert order == ["first-start"], order

            # Release the first; the second proceeds.
            first_release.set()
            await asyncio.gather(t1, t2)
        finally:
            app_module._process_and_broadcast = original  # type: ignore[assignment]

        assert order == ["first-start", "first-end", "second-start", "second-end"]

    async def test_exception_inside_processing_does_not_crash_task(self) -> None:
        """If `_process_and_broadcast` raises, the wrapper logs + suppresses."""
        s = _make_session()
        from the_one.interfaces.web import app as app_module

        async def boom(*_a, **_kw) -> None:
            raise RuntimeError("intentional test failure")

        original = app_module._process_and_broadcast
        original_send = app_module._send_to_session

        # Stub the broadcast helper so the error-fallback `_send_to_session`
        # call doesn't try to actually broadcast over a fake session.
        async def fake_send(*_a, **_kw) -> None:
            return None

        app_module._process_and_broadcast = boom  # type: ignore[assignment]
        app_module._send_to_session = fake_send  # type: ignore[assignment]
        try:
            # Should NOT raise — wrapper catches Exception and broadcasts a
            # `system` event to subscribers.
            await _spawn_message_processing(s, "boom", "web", None)
        finally:
            app_module._process_and_broadcast = original  # type: ignore[assignment]
            app_module._send_to_session = original_send  # type: ignore[assignment]

    async def test_inflight_tasks_self_discard_on_completion(self) -> None:
        """Tasks spawned and tracked in `_inflight_tasks` self-remove on done."""
        s = _make_session()
        from the_one.interfaces.web import app as app_module

        async def quick(*_a, **_kw) -> None:
            return None

        original = app_module._process_and_broadcast
        app_module._process_and_broadcast = quick  # type: ignore[assignment]
        try:
            task = asyncio.create_task(
                _spawn_message_processing(s, "hi", "web", None)
            )
            _inflight_tasks.add(task)
            task.add_done_callback(_inflight_tasks.discard)
            await task
            # `discard` callback runs on the loop's next tick — yield.
            await asyncio.sleep(0)
            assert task not in _inflight_tasks
        finally:
            app_module._process_and_broadcast = original  # type: ignore[assignment]


class TestRestoreSkipsRebuildDuringInflight:
    """Regression: rejoining a session that's actively processing must
    NOT clobber the in-memory `Session.agent`/`history` with a stale DB
    snapshot.

    Before the fix, `_restore_session` always rebuilt the agent and
    replaced `history = ui_events_from_db`. The user's just-submitted
    message is in memory but not persisted yet → rebuilding rendered
    the chat blank on rejoin during a long tool call.

    After the fix, `_restore_session` short-circuits to the cached
    session if its `processing_lock` is held.
    """

    async def test_rebuild_skipped_when_lock_held(self) -> None:
        from the_one.interfaces.web import app as app_module
        from the_one.interfaces.web.app import _restore_session, _sessions

        s = _make_session("locked-sess")
        s.processing_lock = asyncio.Lock()
        s.history = [{"type": "user", "content": "hi"}]
        _sessions[s.id] = s

        # Stub repo + factory to detect whether the rebuild path runs.
        rebuild_invoked = False

        class FakeRepo:
            async def get(self, _sid):
                # Returns a minimal db_session-shaped object.
                from the_one.db.models import ChatSession as ChatSessionModel
                return ChatSessionModel(
                    id=s.id, agent_name=None, title="Old",
                    messages="[]", created_at="2020-01-01T00:00:00",
                    updated_at="2020-01-01T00:00:00",
                )

        async def fake_chat_repo():
            return FakeRepo()

        class FakeFactory:
            async def create(self, _name):
                nonlocal rebuild_invoked
                rebuild_invoked = True
                return _FakeAgent()

        original_repo = app_module._chat_repo
        original_get_factory = app_module._get_factory
        app_module._chat_repo = fake_chat_repo  # type: ignore[assignment]
        app_module._get_factory = lambda: FakeFactory()  # type: ignore[assignment]
        try:
            async with s.processing_lock:
                restored = await _restore_session(s.id)
            assert restored.session is s
            assert restored.session.history == [{"type": "user", "content": "hi"}]
            assert not rebuild_invoked, (
                "factory.create should NOT run while processing_lock is held"
            )
        finally:
            app_module._chat_repo = original_repo  # type: ignore[assignment]
            app_module._get_factory = original_get_factory  # type: ignore[assignment]
            _sessions.pop(s.id, None)

    async def test_rebuild_runs_when_lock_unheld(self) -> None:
        """Rebuild path must still run for normal joins (config-edit
        propagation is the original purpose)."""
        from the_one.interfaces.web import app as app_module
        from the_one.interfaces.web.app import _restore_session, _sessions

        s = _make_session("unlocked-sess")
        s.processing_lock = asyncio.Lock()  # exists but not held
        s.history = [{"type": "user", "content": "old"}]
        _sessions[s.id] = s

        rebuild_invoked = False

        class FakeRepo:
            async def get(self, _sid):
                from the_one.db.models import ChatSession as ChatSessionModel
                return ChatSessionModel(
                    id=s.id, agent_name=None, title="DBTitle",
                    messages="[]", created_at="2020-01-01T00:00:00",
                    updated_at="2020-01-01T00:00:00",
                )

        async def fake_chat_repo():
            return FakeRepo()

        class FakeFactory:
            async def create(self, _name):
                nonlocal rebuild_invoked
                rebuild_invoked = True
                return _FakeAgent()

        original_repo = app_module._chat_repo
        original_get_factory = app_module._get_factory
        app_module._chat_repo = fake_chat_repo  # type: ignore[assignment]
        app_module._get_factory = lambda: FakeFactory()  # type: ignore[assignment]
        try:
            restored = await _restore_session(s.id)
            assert restored.session is s
            assert rebuild_invoked, "factory.create should run for non-processing rejoins"
            assert restored.session.title == "DBTitle"
        finally:
            app_module._chat_repo = original_repo  # type: ignore[assignment]
            app_module._get_factory = original_get_factory  # type: ignore[assignment]
            _sessions.pop(s.id, None)


@pytest.fixture(autouse=True)
async def _drain_inflight() -> None:
    """Cancel any leaked tasks between tests so one test doesn't poison
    another via the module-global `_inflight_tasks` set."""
    yield
    for t in list(_inflight_tasks):
        t.cancel()
    if _inflight_tasks:
        # Swallow any final exceptions from cancelled tasks.
        await asyncio.gather(*list(_inflight_tasks), return_exceptions=True)
    _inflight_tasks.clear()
