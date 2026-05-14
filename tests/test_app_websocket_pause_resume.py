"""F5 L3 WebSocket-layer tests for pause/resume integration.

Covers A11 (auth_required broadcast in ``_process_and_broadcast``),
A12 (oauth_callback schedules ``_resume_paused_session``), and A13
(reconnect snapshot derived from agent state).

These tests do NOT spin up the full FastAPI app — they drive
``_process_and_broadcast``, ``_resume_paused_session``, and
``_send_pause_snapshot_if_needed`` directly with stub Agents and a
captured broadcast sink.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, patch

import aiosqlite
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from the_one.db.schema import ensure_schema
from the_one.encryption import Encryptor
from the_one.interfaces.web import app as web_app
from the_one.interfaces.web.api import router
from the_one.interfaces.web.app import (
    Session,
    _process_and_broadcast,
    _send_pause_snapshot_if_needed,
)
from the_one.llm.base import Message, ToolCall, ToolResult
from the_one.mcp.oauth import _state


@pytest.fixture(autouse=True)
def _reset_oauth_state():
    _state._pending.clear()
    yield
    _state._pending.clear()


class StubAgent:
    """Minimal stub of ``Agent`` for WebSocket-layer testing.

    Drives ``_process_and_broadcast`` and ``_resume_paused_session``
    by yielding scripted ``Message`` instances. The real ``Agent``
    requires an ``LLMProvider`` and a ``ToolRegistry``; here we just
    surface what those helpers consume:

      - ``llm.max_context_tokens`` (used by ``_broadcast_one`` for usage
        events; we hardcode 128_000 to match the LLMProvider default).
      - ``messages`` (used by ``_send_pause_snapshot_if_needed`` to
        walk backwards finding the last auth_required tool_msg).
      - ``_deferred_tool_calls`` (used by the resume guard).
      - ``step(user_input, on_chunk=...)`` async generator (used by
        ``_process_and_broadcast``).
      - ``resume_after_auth()`` async generator (used by
        ``_resume_paused_session``).
    """

    def __init__(
        self,
        step_messages: list[Message] | None = None,
        resume_messages: list[Message] | None = None,
        deferred_tool_calls: list[ToolCall] | None = None,
        agent_messages: list[Message] | None = None,
    ) -> None:
        self._step_messages = step_messages or []
        self._resume_messages = resume_messages or []
        self._deferred_tool_calls = deferred_tool_calls
        self.messages: list[Message] = agent_messages or []

        # Provide a minimal ``llm`` shim with ``max_context_tokens``.
        class _LLMShim:
            max_context_tokens = 128_000

        self.llm = _LLMShim()

    async def step(
        self,
        user_input: str,  # noqa: ARG002
        on_chunk: Any = None,  # noqa: ARG002
    ) -> AsyncIterator[Message]:
        for m in self._step_messages:
            yield m

    async def resume_after_auth(self) -> AsyncIterator[Message]:
        # Match real Agent's no-deferred-state contract.
        if self._deferred_tool_calls is None:
            return
        # Mark consumed BEFORE yielding so re-entry sees None
        self._deferred_tool_calls = None
        for m in self._resume_messages:
            yield m

    def reset(self) -> None:  # pragma: no cover — not invoked here
        self.messages = []
        self._deferred_tool_calls = None


# ---------------------------------------------------------------------------
# A11 — _process_and_broadcast emits auth_required, skips done
# ---------------------------------------------------------------------------


async def test_yielded_auth_required_tool_msg_broadcasts_auth_required_event_and_skips_done(
    monkeypatch,
) -> None:
    """A11: auth_required tool_msg → broadcast auth_required, skip tool_result + done."""
    # Stub the Ollama auto-load + DB save out — they hit external state
    # and are not under test here.
    monkeypatch.setattr(
        web_app, "_ensure_ollama_model_loaded", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        web_app, "_save_session_to_db", AsyncMock(return_value=None)
    )

    captured: list[dict[str, Any]] = []

    async def capture(session, payload, exclude=None):  # noqa: ARG001
        captured.append(payload)

    monkeypatch.setattr(web_app, "_send_to_session", capture)

    auth_metadata = {
        "is_auth_required": True,
        "source_id": "src1",
        "resource_metadata_url": "https://x/.well-known/oauth-protected-resource",
        "tool_call_id": "tc_a",
        # consent_url intentionally absent — lazy-path seam (cycle-1 D10)
    }
    auth_tool_msg = Message.tool(
        ToolResult(
            tool_call_id="tc_a",
            content="auth required",
            metadata=auth_metadata,
        )
    )
    pre_assistant = Message.assistant(
        "",
        tool_calls=[ToolCall(id="tc_a", name="auth_tool", arguments={})],
    )
    agent = StubAgent(step_messages=[pre_assistant, auth_tool_msg])
    session = Session(
        id="cs-A11",
        agent=agent,  # type: ignore[arg-type]
        created="2026-05-07T00:00:00+00:00",
    )

    await _process_and_broadcast(session, "trigger auth")

    # Filter: which event types fired?
    event_types = [p.get("type") for p in captured]

    # User echo + tool_call event + auth_required (NO tool_result, NO done)
    assert "auth_required" in event_types
    # The auth_required event should match the metadata-derived shape
    auth_events = [p for p in captured if p.get("type") == "auth_required"]
    assert len(auth_events) == 1
    assert auth_events[0]["source_id"] == "src1"
    assert auth_events[0]["tool_call_id"] == "tc_a"
    assert auth_events[0]["resource_metadata_url"] == auth_metadata["resource_metadata_url"]
    # Lazy-path seam: consent_url is None
    assert auth_events[0]["consent_url"] is None

    # No tool_result event for the auth_required message
    tool_results = [p for p in captured if p.get("type") == "tool_result"]
    assert tool_results == []

    # No done event — pause is still in flight
    assert "done" not in event_types


# ---------------------------------------------------------------------------
# A12 — oauth_callback schedules _resume_paused_session
# ---------------------------------------------------------------------------


@pytest.fixture
async def oauth_callback_client(tmp_path):
    """FastAPI TestClient with isolated DB + Encryptor patch.

    Mirrors ``tests/test_oauth_callback_route.py``.
    """
    db_path = tmp_path / "callback.db"
    conn = await aiosqlite.connect(str(db_path))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(conn)
    encryptor = Encryptor(Fernet.generate_key(), key_path=tmp_path / "test.key")

    with (
        patch(
            "the_one.interfaces.web.api.get_connection", return_value=conn
        ),
        patch(
            "the_one.interfaces.web.api.get_encryptor", return_value=encryptor
        ),
    ):
        test_app = FastAPI()
        test_app.include_router(router)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

    await conn.close()


async def test_oauth_callback_resume_dispatches_resume_after_auth(
    oauth_callback_client: AsyncClient, monkeypatch
) -> None:
    """A12: oauth_callback success path schedules _resume_paused_session.

    Sets up a ``Session`` whose stub agent has
    ``_deferred_tool_calls=[tc_X]``; triggers the route via TestClient;
    asserts the resume task was scheduled and the resumed tool_msg
    was broadcast.
    """
    # Capture broadcasts from BOTH _send_to_session paths (the
    # auth_resolved one in oauth_callback, and the per-message ones
    # inside _resume_paused_session via _broadcast_one).
    captured: list[tuple[str, dict[str, Any]]] = []

    async def capture(session, payload, exclude=None):  # noqa: ARG001
        captured.append((session.id, payload))

    monkeypatch.setattr(web_app, "_send_to_session", capture)
    monkeypatch.setattr(
        web_app, "_ensure_ollama_model_loaded", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        web_app, "_save_session_to_db", AsyncMock(return_value=None)
    )

    # Build a paused stub agent: deferred=[tc_X]; resume yields one
    # success tool_msg + one final assistant message.
    tc_x = ToolCall(id="tc_x", name="tool_x", arguments={})
    success_tool_msg = Message.tool(
        ToolResult(tool_call_id="tc_x", content="x ok", metadata=None)
    )
    final_assistant = Message.assistant("done")
    agent = StubAgent(
        resume_messages=[success_tool_msg, final_assistant],
        deferred_tool_calls=[tc_x],
    )
    sess = Session(
        id="cs-A12",
        agent=agent,  # type: ignore[arg-type]
        created="2026-05-07T00:00:00+00:00",
    )
    web_app._sessions["cs-A12"] = sess

    # Spy on asyncio.create_task — the route should call it for the resume
    import asyncio as _asyncio

    real_create_task = _asyncio.create_task
    create_task_calls: list[Any] = []

    def spy_create_task(coro, *args, **kwargs):
        task = real_create_task(coro, *args, **kwargs)
        create_task_calls.append(task)
        return task

    try:
        # Register pending OAuth flow
        fut = _state.register(
            "S-A12",
            source_id="src-x",
            tool_call_id="tc_x",
            chat_session_id="cs-A12",
        )

        with patch(
            "the_one.interfaces.web.api.asyncio.create_task",
            side_effect=spy_create_task,
        ):
            resp = await oauth_callback_client.get(
                "/api/oauth/callback",
                params={"state": "S-A12", "code": "code-A12"},
            )

        assert resp.status_code == 200
        assert "Login successful" in resp.text
        assert fut.done()

        # asyncio.create_task was called — for _resume_paused_session
        assert len(create_task_calls) == 1

        # Wait for the resume task to complete so its broadcasts are in
        # ``captured`` before assertion.
        await create_task_calls[0]

        # Verify auth_resolved + resumed tool_result + done were broadcast
        payloads = [p for sid, p in captured if sid == "cs-A12"]
        types = [p.get("type") for p in payloads]
        assert "auth_resolved" in types
        # tool_result for the resumed tc_x
        tool_results = [p for p in payloads if p.get("type") == "tool_result"]
        assert any("x ok" in tr["content"] for tr in tool_results)
        # final assistant message broadcast
        assistants = [p for p in payloads if p.get("type") == "assistant"]
        assert any(a["content"] == "done" for a in assistants)
        # done event fires after resume completes
        assert "done" in types

        # Pause state cleared after resume (StubAgent zeros it on entry)
        assert agent._deferred_tool_calls is None
    finally:
        web_app._sessions.pop("cs-A12", None)


# ---------------------------------------------------------------------------
# A13 — WebSocket reconnect snapshot derives from agent state
# ---------------------------------------------------------------------------


class _StubWebSocket:
    """Minimal stub mimicking ``starlette.websockets.WebSocket.send_json``.

    Captures payloads sent to it. The reconnect-snapshot helper uses
    ``await websocket.send_json(...)``; nothing else is required here.
    """

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send_json(self, payload: dict[str, Any]) -> None:
        self.sent.append(payload)


async def test_websocket_reconnect_replays_auth_required_from_agent_state() -> None:
    """A13: new subscriber on a paused session receives auth_required from agent.messages.

    Walks ``agent.messages`` BACKWARDS to find the last
    ``role=TOOL`` message with ``metadata.is_auth_required`` —
    confirms the walk finds the message even when intervening
    non-tool messages are present after the pause.
    """
    auth_metadata = {
        "is_auth_required": True,
        "source_id": "src-A13",
        "resource_metadata_url": "https://x/.well-known/oauth-protected-resource",
        "tool_call_id": "tc_a13",
    }
    auth_tool_msg = Message.tool(
        ToolResult(
            tool_call_id="tc_a13",
            content="auth required",
            metadata=auth_metadata,
        )
    )

    # Simulate intervening messages added after the pause — e.g. an
    # assistant retort that the chat UI surfaced as an error system
    # message. The walk-backwards must skip these.
    intervening_user = Message.user("ok wait, what?")
    intervening_assistant = Message.assistant("Please log in to continue.")

    agent = StubAgent(
        deferred_tool_calls=[ToolCall(id="tc_a13", name="auth_tool", arguments={})],
        agent_messages=[
            Message.system("system"),
            Message.user("trigger"),
            Message.assistant(
                "",
                tool_calls=[
                    ToolCall(id="tc_a13", name="auth_tool", arguments={})
                ],
            ),
            auth_tool_msg,
            intervening_user,
            intervening_assistant,
        ],
    )
    session = Session(
        id="cs-A13",
        agent=agent,  # type: ignore[arg-type]
        created="2026-05-07T00:00:00+00:00",
    )

    new_ws = _StubWebSocket()
    existing_ws = _StubWebSocket()
    session.subscribers.add(existing_ws)  # type: ignore[arg-type]
    session.subscribers.add(new_ws)  # type: ignore[arg-type]

    # Send the snapshot ONLY to the new ws
    await _send_pause_snapshot_if_needed(session, new_ws)  # type: ignore[arg-type]

    # New ws received the auth_required event derived from the metadata
    assert len(new_ws.sent) == 1
    payload = new_ws.sent[0]
    assert payload["type"] == "auth_required"
    assert payload["source_id"] == "src-A13"
    assert payload["tool_call_id"] == "tc_a13"
    assert payload["resource_metadata_url"] == auth_metadata["resource_metadata_url"]

    # Existing subscriber did NOT receive a duplicate
    assert existing_ws.sent == []

    # No-op when the agent is not paused
    agent._deferred_tool_calls = None
    new_ws.sent.clear()
    await _send_pause_snapshot_if_needed(session, new_ws)  # type: ignore[arg-type]
    assert new_ws.sent == []


# ---------------------------------------------------------------------------
# F5 L02 — parent_message_id discriminator across pause + resume round-trip
# ---------------------------------------------------------------------------


async def test_paused_auth_required_carries_parent_message_id_matching_tool_call(
    monkeypatch,
) -> None:
    """L02: the auth_required event broadcast by ``_process_and_broadcast``
    carries a ``parent_message_id`` matching the preceding tool_call event's
    parent. Verifies the discriminator survives the live broadcast path.
    """
    monkeypatch.setattr(
        web_app, "_ensure_ollama_model_loaded", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        web_app, "_save_session_to_db", AsyncMock(return_value=None)
    )

    captured: list[dict[str, Any]] = []

    async def capture(session, payload, exclude=None):  # noqa: ARG001
        captured.append(payload)

    monkeypatch.setattr(web_app, "_send_to_session", capture)

    auth_metadata = {
        "is_auth_required": True,
        "source_id": "src-L02a",
        "resource_metadata_url": "https://x/.well-known/oauth-protected-resource",
        "tool_call_id": "tc_L02a",
    }
    pre_assistant = Message.assistant(
        "",
        tool_calls=[ToolCall(id="tc_L02a", name="auth_tool", arguments={})],
    )
    auth_tool_msg = Message.tool(
        ToolResult(
            tool_call_id="tc_L02a",
            content="auth required",
            metadata=auth_metadata,
        )
    )
    agent = StubAgent(step_messages=[pre_assistant, auth_tool_msg])
    session = Session(
        id="cs-L02a",
        agent=agent,  # type: ignore[arg-type]
        created="2026-05-13T00:00:00+00:00",
    )

    await _process_and_broadcast(session, "trigger auth")

    tc_events = [p for p in captured if p.get("type") == "tool_call"]
    auth_events = [p for p in captured if p.get("type") == "auth_required"]
    assert len(tc_events) == 1
    assert len(auth_events) == 1
    # Both events share the same parent_message_id discriminator
    assert tc_events[0]["parent_message_id"] is not None
    assert tc_events[0]["parent_message_id"] == auth_events[0]["parent_message_id"]
    # tool_call_id discriminator present on the tool_call event
    assert tc_events[0]["tool_call_id"] == "tc_L02a"
    # auth_required carries tool_call_id from the metadata (existing
    # behaviour — preserved)
    assert auth_events[0]["tool_call_id"] == "tc_L02a"
    # The broadcast namespace uses the live "{session.id}-msg-N" prefix,
    # NOT the codec "replay-msg-N" prefix — guards against accidental
    # cross-namespace leakage.
    assert auth_events[0]["parent_message_id"].startswith("cs-L02a-msg-")


async def test_resumed_tool_result_inherits_parent_message_id(monkeypatch) -> None:
    """L02: after a paused tool_result is resolved and ``_broadcast_one``
    re-broadcasts the resumed tool_result via the resume path, the
    resumed tool_result carries the SAME ``parent_message_id`` as the
    original paused tool_call. Verifies the projection rule (look back
    for the most recent assistant with tool_calls) is consistent across
    the live broadcast and resume paths.
    """
    monkeypatch.setattr(
        web_app, "_ensure_ollama_model_loaded", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        web_app, "_save_session_to_db", AsyncMock(return_value=None)
    )

    captured: list[dict[str, Any]] = []

    async def capture(session, payload, exclude=None):  # noqa: ARG001
        captured.append(payload)

    monkeypatch.setattr(web_app, "_send_to_session", capture)

    # Build agent.messages reflecting the paused state: an assistant
    # turn with a tool_call, then the original auth_required tool_msg.
    pre_assistant = Message.assistant(
        "",
        tool_calls=[ToolCall(id="tc_L02b", name="auth_tool", arguments={})],
    )
    auth_metadata = {
        "is_auth_required": True,
        "source_id": "src-L02b",
        "resource_metadata_url": "https://x/.well-known/oauth-protected-resource",
        "tool_call_id": "tc_L02b",
    }
    auth_tool_msg = Message.tool(
        ToolResult(
            tool_call_id="tc_L02b",
            content="auth required",
            metadata=auth_metadata,
        )
    )

    # Resume yields the success tool_msg replacing the auth_required one.
    # In real Agent.resume_after_auth, the success tool_msg is appended
    # to agent.messages BEFORE being yielded. Replicate that here so
    # _broadcast_one's _find_parent_assistant_index walk sees it.
    success_tool_result = ToolResult(tool_call_id="tc_L02b", content="x ok")

    class _ResumeStubAgent(StubAgent):
        async def resume_after_auth(self):  # type: ignore[override]
            if self._deferred_tool_calls is None:
                return
            self._deferred_tool_calls = None
            # Replace the auth_required tool_msg with a success one
            # (the real Agent doesn't actually replace — it appends —
            # but for the projection rule, what matters is that the
            # parent assistant message is still at the same index in
            # the list when the resumed tool_msg is broadcast).
            success_msg = Message.tool(success_tool_result)
            self.messages.append(success_msg)
            yield success_msg

    agent = _ResumeStubAgent(
        deferred_tool_calls=[ToolCall(id="tc_L02b", name="auth_tool", arguments={})],
        agent_messages=[
            Message.user("trigger"),
            pre_assistant,
            auth_tool_msg,
        ],
    )
    session = Session(
        id="cs-L02b",
        agent=agent,  # type: ignore[arg-type]
        created="2026-05-13T00:00:00+00:00",
    )

    # Pre-compute the parent_message_id the ORIGINAL tool_call would carry:
    # the assistant message is at index 1 in agent.messages.
    expected_parent_id = "cs-L02b-msg-1"

    # Drive the resume path directly.
    from the_one.interfaces.web.app import _resume_paused_session

    await _resume_paused_session(session)

    tr_events = [p for p in captured if p.get("type") == "tool_result"]
    assert len(tr_events) >= 1
    resumed_tr = tr_events[0]
    # Resumed tool_result inherits the SAME parent_message_id the
    # original paused tool_call would have carried.
    assert resumed_tr["parent_message_id"] == expected_parent_id
    assert resumed_tr["tool_call_id"] == "tc_L02b"


async def test_pause_snapshot_emits_parent_message_id() -> None:
    """L02: ``_send_pause_snapshot_if_needed`` emits an ``auth_required``
    event whose ``parent_message_id`` matches the parent assistant
    message's id. Verifies the rejoin-snapshot path also carries the
    discriminator (so the L03 frontend renders the consent button
    inside the right trace shell on session rejoin).
    """
    auth_metadata = {
        "is_auth_required": True,
        "source_id": "src-L02c",
        "resource_metadata_url": "https://x/.well-known/oauth-protected-resource",
        "tool_call_id": "tc_L02c",
    }
    auth_tool_msg = Message.tool(
        ToolResult(
            tool_call_id="tc_L02c",
            content="auth required",
            metadata=auth_metadata,
        )
    )

    agent = StubAgent(
        deferred_tool_calls=[ToolCall(id="tc_L02c", name="auth_tool", arguments={})],
        agent_messages=[
            Message.system("system"),
            Message.user("trigger"),
            Message.assistant(
                "",
                tool_calls=[ToolCall(id="tc_L02c", name="auth_tool", arguments={})],
            ),
            auth_tool_msg,
        ],
    )
    session = Session(
        id="cs-L02c",
        agent=agent,  # type: ignore[arg-type]
        created="2026-05-13T00:00:00+00:00",
    )

    new_ws = _StubWebSocket()
    session.subscribers.add(new_ws)  # type: ignore[arg-type]

    await _send_pause_snapshot_if_needed(session, new_ws)  # type: ignore[arg-type]

    assert len(new_ws.sent) == 1
    payload = new_ws.sent[0]
    assert payload["type"] == "auth_required"
    # parent_message_id derived from the assistant at index 2 in agent.messages
    assert payload["parent_message_id"] == "cs-L02c-msg-2"
    # tool_call_id preserved from metadata (existing behaviour)
    assert payload["tool_call_id"] == "tc_L02c"
