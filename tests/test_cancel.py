"""F7 L03 cancel-backend tests.

Covers:
- cancel mid-LLM-stream: partial text persisted as interrupted Message,
  ``cancelled`` event emitted, session lock released (next message runs).
- cancel mid-tool-call: CancelledError raised during tool execution
  (no streamed text), no synthetic Message appended, ``cancelled`` emitted,
  lock released.
- ``except Exception`` at the sibling block does NOT catch ``CancelledError``
  (CancelledError is BaseException, not Exception — a regression guard so
  a future refactor to ``except BaseException`` is caught by tests).
- per-session task-map: registered on spawn, cleared in done-callback with
  identity guard.
- cancel no-op: ``cancel`` action when no session, or task already done.

Tests drive ``_process_and_broadcast`` and ``_spawn_message_processing``
directly without spinning up the full FastAPI app.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

import pytest

from the_one.interfaces.web import app as web_app
from the_one.interfaces.web.app import (
    Session,
    _inflight_tasks,
    _process_and_broadcast,
    _session_inflight,
    _spawn_message_processing,
)
from the_one.llm.base import Message
from the_one.sessions import clear_for_test as _clear_session_registry
from the_one.sessions import session_locks

# ── Helpers ───────────────────────────────────────────────────────────────


class _LLMShim:
    max_context_tokens = 128_000


def _make_session(session_id: str = "s-cancel") -> Session:
    """Return a minimal Session with a no-op stub agent."""
    return Session(
        id=session_id,
        agent=_SlowStreamAgent(),  # type: ignore[arg-type]
        created=datetime.now(timezone.utc).isoformat(),
    )


class _SlowStreamAgent:
    """Agent that streams one chunk then blocks until cancelled.

    Mimics mid-LLM-stream cancellation: on_chunk is called once
    (delivering partial text to the accumulator in _broadcast_chunk),
    then the step async generator awaits an event that never fires —
    so the task must be cancelled externally.
    """

    def __init__(
        self, chunks: list[str] | None = None, hang_event: asyncio.Event | None = None
    ) -> None:
        self.messages: list[Message] = []
        self.llm = _LLMShim()
        self._deferred_tool_calls = None
        self._chunks = chunks or []
        # Each test can supply its own Event to signal when hanging starts.
        self._started = asyncio.Event()
        self._hang_event = hang_event or asyncio.Event()  # never set by default

    async def step(
        self,
        user_input: str,  # noqa: ARG002
        on_chunk: Any = None,
        on_usage: Any = None,  # noqa: ARG002
    ) -> AsyncIterator[Message]:
        for chunk in self._chunks:
            if on_chunk:
                await on_chunk(chunk)
        self._started.set()
        # Block until an external cancel arrives.
        await self._hang_event.wait()
        if False:  # pragma: no cover
            yield  # type: ignore[misc]  — make it an async generator

    async def resume_after_auth(self) -> AsyncIterator[Message]:  # pragma: no cover
        if False:
            yield  # type: ignore[unreachable]


class _QuickAgent:
    """Agent whose step() yields nothing and returns immediately."""

    def __init__(self) -> None:
        self.messages: list[Message] = []
        self.llm = _LLMShim()
        self._deferred_tool_calls = None
        self._started = asyncio.Event()

    async def step(
        self,
        user_input: str,  # noqa: ARG002
        on_chunk: Any = None,  # noqa: ARG002
        on_usage: Any = None,  # noqa: ARG002
    ) -> AsyncIterator[Message]:
        self._started.set()
        if False:  # pragma: no cover
            yield  # type: ignore[misc]

    async def resume_after_auth(self) -> AsyncIterator[Message]:  # pragma: no cover
        if False:
            yield  # type: ignore[unreachable]


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
async def _cleanup():
    """Cancel leaked tasks, clear session registry, reset _session_inflight."""
    yield
    for t in list(_inflight_tasks):
        t.cancel()
    if _inflight_tasks:
        await asyncio.gather(*list(_inflight_tasks), return_exceptions=True)
    _inflight_tasks.clear()
    _session_inflight.clear()
    _clear_session_registry()


# ── Helpers for monkeypatching ─────────────────────────────────────────────


async def _noop_send(sess, payload, exclude=None) -> None:  # noqa: ARG001
    pass


async def _noop_save(sess) -> None:  # noqa: ARG001
    pass


async def _noop_load(sess) -> None:  # noqa: ARG001
    pass


# ── Test: cancel mid-LLM-stream ───────────────────────────────────────────


class TestCancelMidStream:
    """Cancel fires while the LLM is streaming chunks — partial text must be
    persisted as an interrupted assistant Message."""

    async def test_partial_text_persisted(self, monkeypatch) -> None:
        """Cancelling mid-stream appends an interrupted Message to history."""
        agent = _SlowStreamAgent(chunks=["Hello partial"])
        session = _make_session("s-mid-stream")
        session.agent = agent  # type: ignore[assignment]

        captured: list[dict] = []

        async def fake_send(sess, payload, exclude=None):  # noqa: ARG001
            captured.append(payload)

        monkeypatch.setattr(web_app, "_send_to_session", fake_send)
        monkeypatch.setattr(web_app, "_save_session_to_db", _noop_save)
        monkeypatch.setattr(web_app, "_ensure_ollama_model_loaded", _noop_load)

        task = asyncio.create_task(_process_and_broadcast(session, "trigger", source="web"))

        # Wait until the agent has streamed its chunk and is hanging.
        await agent._started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        # (a) The interrupted Message is in agent.messages.
        interrupted = [
            m
            for m in session.agent.messages
            if hasattr(m, "content") and "_[interrupted]_" in (m.content or "")
        ]
        assert len(interrupted) >= 1, (
            f"Expected interrupted Message in agent.messages; got {session.agent.messages!r}"
        )
        assert "Hello partial" in interrupted[0].content

        # (b) ``cancelled`` event was emitted.
        assert any(e.get("type") == "cancelled" for e in captured), (
            f"Expected 'cancelled' event; got types: {[e.get('type') for e in captured]!r}"
        )

    async def test_cancelled_event_shape(self, monkeypatch) -> None:
        """The ``cancelled`` event is ``{"type": "cancelled"}`` (flat, no session_id)."""
        agent = _SlowStreamAgent(chunks=["text"])
        session = _make_session("s-event-shape")
        session.agent = agent  # type: ignore[assignment]

        captured: list[dict] = []

        async def fake_send(sess, payload, exclude=None):  # noqa: ARG001
            captured.append(payload)

        monkeypatch.setattr(web_app, "_send_to_session", fake_send)
        monkeypatch.setattr(web_app, "_save_session_to_db", _noop_save)
        monkeypatch.setattr(web_app, "_ensure_ollama_model_loaded", _noop_load)

        task = asyncio.create_task(_process_and_broadcast(session, "trigger", source="web"))
        await agent._started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        cancelled_events = [e for e in captured if e.get("type") == "cancelled"]
        assert len(cancelled_events) >= 1
        # Shape must include "type": "cancelled"; no session_id required.
        evt = cancelled_events[0]
        assert evt["type"] == "cancelled"

    async def test_lock_released_after_stream_cancel(self, monkeypatch) -> None:
        """(c) Session lock is released after cancel — a subsequent message runs."""
        agent = _SlowStreamAgent(chunks=["partial"])
        session = _make_session("s-lock-release")
        session.agent = agent  # type: ignore[assignment]

        monkeypatch.setattr(web_app, "_send_to_session", _noop_send)
        monkeypatch.setattr(web_app, "_save_session_to_db", _noop_save)
        monkeypatch.setattr(web_app, "_ensure_ollama_model_loaded", _noop_load)

        task = asyncio.create_task(_spawn_message_processing(session, "m1", "web", None))
        _inflight_tasks.add(task)
        task.add_done_callback(_inflight_tasks.discard)

        await agent._started.wait()
        task.cancel()
        # _spawn_message_processing re-raises CancelledError so the task
        # itself is cancelled. Suppress it here — we only care the lock freed.
        with contextlib.suppress(asyncio.CancelledError):
            await task

        # The session lock MUST be free now.
        lock = session_locks[session.id]
        acquired = False
        try:
            await asyncio.wait_for(lock.acquire(), timeout=0.5)
            acquired = True
        except asyncio.TimeoutError:
            pass

        assert acquired, "Session lock was not released after cancel mid-stream"
        if acquired:
            lock.release()

    async def test_save_called_with_partial_message(self, monkeypatch) -> None:
        """_save_session_to_db is called after the interrupted Message is appended."""
        agent = _SlowStreamAgent(chunks=["saved text"])
        session = _make_session("s-save")
        session.agent = agent  # type: ignore[assignment]

        save_calls: list[list[Message]] = []

        async def capture_save(sess) -> None:
            save_calls.append(list(sess.agent.messages))

        monkeypatch.setattr(web_app, "_send_to_session", _noop_send)
        monkeypatch.setattr(web_app, "_save_session_to_db", capture_save)
        monkeypatch.setattr(web_app, "_ensure_ollama_model_loaded", _noop_load)

        task = asyncio.create_task(_process_and_broadcast(session, "trigger", source="web"))
        await agent._started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert len(save_calls) >= 1, "Expected _save_session_to_db to be called on cancel"
        saved_messages = save_calls[-1]
        assert any("_[interrupted]_" in (m.content or "") for m in saved_messages), (
            "Interrupted Message should be in agent.messages at save time"
        )

    async def test_next_message_accepted_after_stream_cancel(self, monkeypatch) -> None:
        """(c) A subsequent message on the same session is accepted after cancel."""
        agent1 = _SlowStreamAgent(chunks=["partial"])
        session = _make_session("s-next-msg")
        session.agent = agent1  # type: ignore[assignment]

        monkeypatch.setattr(web_app, "_send_to_session", _noop_send)
        monkeypatch.setattr(web_app, "_save_session_to_db", _noop_save)
        monkeypatch.setattr(web_app, "_ensure_ollama_model_loaded", _noop_load)

        task1 = asyncio.create_task(_spawn_message_processing(session, "m1", "web", None))
        _inflight_tasks.add(task1)
        task1.add_done_callback(_inflight_tasks.discard)

        await agent1._started.wait()
        task1.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task1

        # Swap to a quick agent for the second message.
        agent2 = _QuickAgent()
        session.agent = agent2  # type: ignore[assignment]

        task2 = asyncio.create_task(_spawn_message_processing(session, "m2", "web", None))
        _inflight_tasks.add(task2)
        task2.add_done_callback(_inflight_tasks.discard)

        await asyncio.wait_for(agent2._started.wait(), timeout=2.0)
        assert agent2._started.is_set(), "Second message did not run after cancel"
        await task2


# ── Test: cancel mid-tool-call ────────────────────────────────────────────


class TestCancelMidToolCall:
    """Cancel fires during a tool call (no text streamed yet)."""

    async def test_no_synthetic_message_when_no_text(self, monkeypatch) -> None:
        """If no text was streamed, no interrupted Message is appended."""
        # Agent that hangs WITHOUT calling on_chunk (simulates mid-tool-call).
        agent = _SlowStreamAgent(chunks=[])  # no chunks
        session = _make_session("s-mid-tool")
        session.agent = agent  # type: ignore[assignment]

        captured: list[dict] = []

        async def fake_send(sess, payload, exclude=None):  # noqa: ARG001
            captured.append(payload)

        monkeypatch.setattr(web_app, "_send_to_session", fake_send)
        monkeypatch.setattr(web_app, "_save_session_to_db", _noop_save)
        monkeypatch.setattr(web_app, "_ensure_ollama_model_loaded", _noop_load)

        task = asyncio.create_task(_process_and_broadcast(session, "trigger", source="web"))
        await agent._started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        # (a) No interrupted Message — nothing was streamed before cancel.
        interrupted = [
            m
            for m in session.agent.messages
            if hasattr(m, "content") and "_[interrupted]_" in (m.content or "")
        ]
        assert len(interrupted) == 0, (
            f"No interrupted Message expected when no text streamed; got {interrupted!r}"
        )

        # (b) ``cancelled`` event was still emitted.
        types_seen = [e.get("type") for e in captured]
        assert any(e.get("type") == "cancelled" for e in captured), (
            f"Expected 'cancelled' event even mid-tool-call; got: {types_seen!r}"
        )

    async def test_lock_released_after_tool_cancel(self, monkeypatch) -> None:
        """(c) Lock is released after cancel mid-tool-call."""
        agent = _SlowStreamAgent(chunks=[])
        session = _make_session("s-tool-lock")
        session.agent = agent  # type: ignore[assignment]

        monkeypatch.setattr(web_app, "_send_to_session", _noop_send)
        monkeypatch.setattr(web_app, "_save_session_to_db", _noop_save)
        monkeypatch.setattr(web_app, "_ensure_ollama_model_loaded", _noop_load)

        task = asyncio.create_task(_spawn_message_processing(session, "m1", "web", None))
        _inflight_tasks.add(task)
        task.add_done_callback(_inflight_tasks.discard)

        await agent._started.wait()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        lock = session_locks[session.id]
        acquired = False
        try:
            await asyncio.wait_for(lock.acquire(), timeout=0.5)
            acquired = True
        except asyncio.TimeoutError:
            pass

        assert acquired, "Session lock was not released after mid-tool-call cancel"
        if acquired:
            lock.release()

    async def test_next_message_accepted_after_tool_cancel(self, monkeypatch) -> None:
        """A subsequent message on the same session runs after cancel mid-tool."""
        agent1 = _SlowStreamAgent(chunks=[])
        session = _make_session("s-tool-next")
        session.agent = agent1  # type: ignore[assignment]

        monkeypatch.setattr(web_app, "_send_to_session", _noop_send)
        monkeypatch.setattr(web_app, "_save_session_to_db", _noop_save)
        monkeypatch.setattr(web_app, "_ensure_ollama_model_loaded", _noop_load)

        task1 = asyncio.create_task(_spawn_message_processing(session, "m1", "web", None))
        _inflight_tasks.add(task1)
        task1.add_done_callback(_inflight_tasks.discard)

        await agent1._started.wait()
        task1.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task1

        agent2 = _QuickAgent()
        session.agent = agent2  # type: ignore[assignment]

        task2 = asyncio.create_task(_spawn_message_processing(session, "m2", "web", None))
        _inflight_tasks.add(task2)
        task2.add_done_callback(_inflight_tasks.discard)

        await asyncio.wait_for(agent2._started.wait(), timeout=2.0)
        assert agent2._started.is_set(), "Second message did not run — lock was not released"
        await task2


# ── Test: except Exception does NOT catch CancelledError ─────────────────


class TestExceptExceptionDoesNotCatchCancelledError:
    """Regression guard: CancelledError must propagate through the
    ``except Exception`` block in _process_and_broadcast.

    If a future refactor changes ``except Exception`` to
    ``except BaseException``, cancel's lock-release semantics break because
    CancelledError would be swallowed inside the function instead of
    propagating to _spawn_message_processing's `async with` release.

    This test asserts the property directly on Python's exception hierarchy —
    no app code needed; it documents the contract so reviewers understand why
    the two `except` clauses are SIBLINGS.

    Context: in _process_and_broadcast (~app.py), the cancel handler is:

        except asyncio.CancelledError:   # ← new sibling (F7 L03)
            ...
            raise
        except Exception as exc:         # ← original handler
            ...

    Because CancelledError inherits BaseException (not Exception) in Python ≥ 3.8,
    the ``except Exception`` block does NOT intercept a CancelledError — the
    ``except asyncio.CancelledError`` sibling catches it instead.
    """

    def test_cancelled_error_is_not_subclass_of_exception(self) -> None:
        """CancelledError inherits BaseException, NOT Exception, in Python ≥ 3.8.

        This is the property that makes `except Exception` a safe sibling to
        `except asyncio.CancelledError` in _process_and_broadcast.
        If Python ever changes this hierarchy (which it won't), the cancel
        mechanism would silently break — this test would catch that regression.
        """
        assert not issubclass(asyncio.CancelledError, Exception), (
            "asyncio.CancelledError must NOT be a subclass of Exception; "
            "if it were, `except Exception` in _process_and_broadcast would "
            "catch it and swallow the cancel, stranding the session lock."
        )
        assert issubclass(asyncio.CancelledError, BaseException), (
            "asyncio.CancelledError must be a BaseException subclass."
        )

    async def test_cancelled_error_propagates_through_process_and_broadcast(
        self, monkeypatch
    ) -> None:
        """CancelledError raised inside step() propagates out of _process_and_broadcast.

        If ``except Exception`` were ``except BaseException``, this test would fail
        because the function would swallow the error instead of re-raising it.
        """
        agent = _SlowStreamAgent(chunks=[])
        session = _make_session("s-propagate")
        session.agent = agent  # type: ignore[assignment]

        monkeypatch.setattr(web_app, "_send_to_session", _noop_send)
        monkeypatch.setattr(web_app, "_save_session_to_db", _noop_save)
        monkeypatch.setattr(web_app, "_ensure_ollama_model_loaded", _noop_load)

        task = asyncio.create_task(_process_and_broadcast(session, "trigger", source="web"))
        await agent._started.wait()
        task.cancel()

        # CancelledError MUST propagate out (not be swallowed).
        with pytest.raises(asyncio.CancelledError):
            await task


# ── Test: per-session task map ────────────────────────────────────────────


class TestSessionInflightMap:
    """_session_inflight is populated at spawn and cleared in done-callback."""

    async def test_task_registered_on_spawn(self, monkeypatch) -> None:
        """Task is registered in _session_inflight at spawn time."""
        gate = asyncio.Event()
        started = asyncio.Event()

        async def slow_pb(
            sess,
            user_input,
            source="web",
            exclude_user_echo=None,  # noqa: ARG001
        ) -> list:
            started.set()
            await gate.wait()
            return []

        monkeypatch.setattr(web_app, "_process_and_broadcast", slow_pb)

        session = _make_session("s-reg")
        task = asyncio.create_task(_spawn_message_processing(session, "hi", "web", None))
        _inflight_tasks.add(task)
        task.add_done_callback(_inflight_tasks.discard)

        # Simulate what the WS handler does:
        _session_inflight[session.id] = task

        def _clear(t: asyncio.Task, _sid: str = session.id) -> None:
            if _session_inflight.get(_sid) is t:
                del _session_inflight[_sid]

        task.add_done_callback(_clear)

        await started.wait()
        assert _session_inflight.get(session.id) is task, (
            "Task should be registered in _session_inflight while running"
        )

        gate.set()
        await task
        await asyncio.sleep(0)  # let done-callback fire
        assert session.id not in _session_inflight, (
            "Task should be cleared from _session_inflight after completion"
        )

    async def test_identity_guard_prevents_stale_clear(self, monkeypatch) -> None:
        """Done-callback clears only if the map still points at THIS task.

        Simulates the WS handler queue-depth-1 scenario:
        - t1 is spawned, registered in _session_inflight, and starts running.
        - t2 is spawned before t1 finishes, overwriting t1 in _session_inflight.
        - t1 finishes; its done-callback should NOT clear the map (it now → t2).
        - t2 finishes; its done-callback clears the map.

        We use _spawn_message_processing with monkeypatched _process_and_broadcast.
        Note: _spawn_message_processing holds session_locks[session.id] under async-with,
        so t1 must FINISH (not just reach "started") before t2 can run. We register t2
        in the map before t1 finishes, then release t1's gate — simulating the WS handler
        registering t2 at spawn time while t1 is still running.
        """
        gate1 = asyncio.Event()
        gate2 = asyncio.Event()
        started1 = asyncio.Event()
        started2 = asyncio.Event()

        # _process_and_broadcast signature: (session, user_input, source, exclude_user_echo)
        async def slow1(
            sess,
            user_input,
            source="web",
            exclude_user_echo=None,  # noqa: ARG001
        ) -> list:
            started1.set()
            await gate1.wait()
            return []

        async def slow2(
            sess,
            user_input,
            source="web",
            exclude_user_echo=None,  # noqa: ARG001
        ) -> list:
            started2.set()
            await gate2.wait()
            return []

        session = _make_session("s-identity")

        original_pb = web_app._process_and_broadcast
        try:
            web_app._process_and_broadcast = slow1  # type: ignore[assignment]
            t1 = asyncio.create_task(_spawn_message_processing(session, "m1", "web", None))
            _inflight_tasks.add(t1)
            t1.add_done_callback(_inflight_tasks.discard)
            _session_inflight[session.id] = t1

            def _clear1(t: asyncio.Task, _sid: str = session.id) -> None:
                if _session_inflight.get(_sid) is t:
                    del _session_inflight[_sid]

            t1.add_done_callback(_clear1)

            await started1.wait()

            # Overwrite the map with t2 BEFORE t1 finishes — this is what the
            # WS handler does when a second message arrives while one is running.
            # t2 can't run until t1 releases the session lock.
            web_app._process_and_broadcast = slow2  # type: ignore[assignment]
            t2 = asyncio.create_task(_spawn_message_processing(session, "m2", "web", None))
            _inflight_tasks.add(t2)
            t2.add_done_callback(_inflight_tasks.discard)
            _session_inflight[session.id] = t2  # overwrite: map now → t2

            def _clear2(t: asyncio.Task, _sid: str = session.id) -> None:
                if _session_inflight.get(_sid) is t:
                    del _session_inflight[_sid]

            t2.add_done_callback(_clear2)

            # Release t1 — its done-callback fires; map now → t2, so it should NOT clear.
            gate1.set()
            # t2 starts once t1 releases the lock.
            await asyncio.wait_for(started2.wait(), timeout=2.0)

            # After t1's done-callback fires, map must still point at t2.
            await asyncio.sleep(0)
            assert _session_inflight.get(session.id) is t2, (
                "Identity guard failed: t1's done-callback should not clear "
                "the map when it was overwritten by t2"
            )

            # Let t2 finish.
            gate2.set()
            await asyncio.gather(t1, t2)
            await asyncio.sleep(0)
        finally:
            web_app._process_and_broadcast = original_pb  # type: ignore[assignment]

        assert session.id not in _session_inflight, "Map entry should be cleared after t2 completes"


# ── Test: cancel no-ops ───────────────────────────────────────────────────


class TestCancelNoOps:
    """cancel action is a no-op when there is nothing to cancel."""

    async def test_cancel_already_done_task_is_noop(self, monkeypatch) -> None:
        """Cancelling an already-completed task returns False and is safe."""
        agent = _QuickAgent()
        session = _make_session("s-noop-done")
        session.agent = agent  # type: ignore[assignment]

        monkeypatch.setattr(web_app, "_send_to_session", _noop_send)
        monkeypatch.setattr(web_app, "_save_session_to_db", _noop_save)
        monkeypatch.setattr(web_app, "_ensure_ollama_model_loaded", _noop_load)

        task = asyncio.create_task(_spawn_message_processing(session, "m1", "web", None))
        _inflight_tasks.add(task)
        task.add_done_callback(_inflight_tasks.discard)
        _session_inflight[session.id] = task

        def _clear(t: asyncio.Task, _sid: str = session.id) -> None:
            if _session_inflight.get(_sid) is t:
                del _session_inflight[_sid]

        task.add_done_callback(_clear)

        await task
        await asyncio.sleep(0)

        # Simulate cancel action: task is done → no-op.
        t = _session_inflight.get(session.id)
        if t and not t.done():
            t.cancel()  # pragma: no cover — should not reach here
        # No exception raised — clean.

    def test_cancel_with_no_task_registered_is_noop(self) -> None:
        """cancel action when session has no registered task is a no-op."""
        session = _make_session("s-nomap")
        # Nothing registered for this session.
        t = _session_inflight.get(session.id)
        if t and not t.done():
            t.cancel()  # pragma: no cover
        # No exception.


class TestCancelInConnectorChat:
    """M33 F1 L3: the cancel path tags a connector chat's messages operator-only."""

    async def test_cancelled_web_turn_in_connector_chat_is_operator_only(self, monkeypatch) -> None:
        from the_one.llm.base import OPERATOR_VISIBILITY

        class _Agent(_SlowStreamAgent):
            async def step(self, user_input, on_chunk=None, on_usage=None):
                self.messages.append(Message.user(user_input))
                self.messages.append(Message.assistant("partial reply"))
                async for _ in super().step(user_input, on_chunk, on_usage):
                    yield _  # pragma: no cover

        agent = _Agent()
        session = _make_session("s-conn-cancel")
        session.agent = agent  # type: ignore[assignment]
        session.platform = "discord"

        monkeypatch.setattr(web_app, "_send_to_session", _noop_send)
        monkeypatch.setattr(web_app, "_save_session_to_db", _noop_save)
        monkeypatch.setattr(web_app, "_ensure_ollama_model_loaded", _noop_load)

        task = asyncio.create_task(_process_and_broadcast(session, "trigger", source="web"))
        await agent._started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert len(agent.messages) >= 2
        assert all(m.visibility == OPERATOR_VISIBILITY for m in agent.messages)


class _TurnAgent(_SlowStreamAgent):
    """Streams text per iteration, yields stored assistant messages, then hangs.

    ``script`` is a list of steps: ``("text", str)`` streams a chunk,
    ``("assistant", Message)`` appends and yields that message (as ``Agent``
    does). The agent hangs after the last step, like a running tool or stream.
    """

    def __init__(self, script: list[tuple[str, Any]]) -> None:
        super().__init__()
        self._script = script

    async def step(self, user_input, on_chunk=None, on_usage=None):  # noqa: ARG002
        self.messages.append(Message.user(user_input))
        for kind, value in self._script:
            if kind == "text":
                await on_chunk(value)
            else:
                self.messages.append(value)
                yield value
        self._started.set()
        await self._hang_event.wait()


async def _cancel_turn(monkeypatch, agent, sid) -> Session:
    session = _make_session(sid)
    session.agent = agent  # type: ignore[assignment]
    saves: list[list[Message]] = []

    async def capture_save(sess) -> None:
        saves.append(list(sess.agent.messages))

    monkeypatch.setattr(web_app, "_send_to_session", _noop_send)
    monkeypatch.setattr(web_app, "_save_session_to_db", capture_save)
    monkeypatch.setattr(web_app, "_ensure_ollama_model_loaded", _noop_load)
    task = asyncio.create_task(_process_and_broadcast(session, "trigger", source="web"))
    await agent._started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    session.saves = saves  # type: ignore[attr-defined]
    return session


class TestCancelKeepsToolCallsAnswered:
    """Squawk 0353: a cancel mid-tool-call must not leave an unanswered call."""

    async def test_saved_history_has_a_result_for_every_tool_call(self, monkeypatch) -> None:
        from the_one.llm.base import ToolCall, ToolResult

        calls = [
            ToolCall(id="a", name="shell", arguments={}),
            ToolCall(id="b", name="x", arguments={}),
        ]
        agent = _TurnAgent(
            [
                ("assistant", Message.assistant("", tool_calls=calls)),
                ("assistant", Message.tool(ToolResult(tool_call_id="a", content="ok"))),
            ]
        )
        session = await _cancel_turn(monkeypatch, agent, "s-tool-answered")
        saved = session.saves[-1]  # type: ignore[attr-defined]
        answered = [m.tool_result.tool_call_id for m in saved if m.tool_result is not None]
        assert answered == ["a", "b"]
        assert saved[-1].tool_result.is_error is True

    async def test_live_auth_pause_is_not_repaired_on_cancel(self, monkeypatch) -> None:
        from the_one.llm.base import ToolCall

        agent = _TurnAgent(
            [("assistant", Message.assistant("", tool_calls=[ToolCall("a", "shell", {})]))]
        )
        agent._deferred_tool_calls = [ToolCall("a", "shell", {})]  # type: ignore[assignment]
        session = await _cancel_turn(monkeypatch, agent, "s-paused")
        assert all(m.tool_result is None for m in session.saves[-1])  # type: ignore[attr-defined]

    async def test_next_turn_repairs_history_left_broken(self, monkeypatch) -> None:
        from the_one.llm.base import ToolCall

        agent = _QuickAgent()
        agent.messages = [
            Message.user("old"),
            Message.assistant("", tool_calls=[ToolCall("z", "shell", {})]),
        ]
        session = _make_session("s-next-repair")
        session.agent = agent  # type: ignore[assignment]
        monkeypatch.setattr(web_app, "_send_to_session", _noop_send)
        monkeypatch.setattr(web_app, "_save_session_to_db", _noop_save)
        monkeypatch.setattr(web_app, "_ensure_ollama_model_loaded", _noop_load)
        await _process_and_broadcast(session, "again", source="web")
        assert [m.role.value for m in agent.messages][:3] == ["user", "assistant", "tool"]


class TestInterruptedMessageHoldsOnlyTheCutOffReply:
    """Squawk 0355: earlier iterations' text is not repeated in the interrupted message."""

    async def test_only_text_since_last_assistant_message(self, monkeypatch) -> None:
        agent = _TurnAgent(
            [
                ("text", "First reply."),
                ("assistant", Message.assistant("First reply.")),
                ("text", "Second, cut off"),
            ]
        )
        session = await _cancel_turn(monkeypatch, agent, "s-interrupt-only-new")
        last = session.agent.messages[-1]
        assert last.content == "Second, cut off\n\n_[interrupted]_"
        assert sum("First reply." in (m.content or "") for m in session.agent.messages) == 1

    async def test_no_interrupted_message_when_nothing_streamed_since(self, monkeypatch) -> None:
        agent = _TurnAgent(
            [("text", "Done thinking."), ("assistant", Message.assistant("Done thinking."))]
        )
        session = await _cancel_turn(monkeypatch, agent, "s-interrupt-none")
        assert not any("_[interrupted]_" in (m.content or "") for m in session.agent.messages)
