"""M16 F06 L01 — unit tests for per-turn usage snapshot persistence.

Covers both turn-settle paths:

  - Non-paused settle: ``_process_and_broadcast`` writes ``last_usage`` to the
    DB and in-memory ``session.session_metadata`` after the step loop completes.
  - Resume settle: ``_resume_paused_session`` accumulates usage over the
    ``resume_after_auth()`` loop and writes the resume-segment snapshot.

Tests assert the **exact** derived ``context_tokens`` (the last assistant
message's ``input_tokens``, not the cumulative sum) so a sum-vs-last-input bug
is caught here rather than surfacing in the overlay.

DB-assertion shape follows the existing
``set_session_metadata_key`` tests at ``tests/test_db_repositories.py:2988-3053``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, patch

import aiosqlite
import pytest

from tests._schema_template import connect_template_db
from the_one.agent.config import AgentConfig
from the_one.db.models import ChatSession
from the_one.db.repositories import ChatSessionRepository, SQLiteAgentStore
from the_one.interfaces.web import app as web_app
from the_one.interfaces.web.app import (
    Session,
    _persist_last_usage,
    _process_and_broadcast,
    _resume_paused_session,
)
from the_one.llm.base import Message, TokenUsage, ToolCall, ToolResult

# ---------------------------------------------------------------------------
# Shared DB fixture (mirrors test_db_repositories.py:23-41)
# ---------------------------------------------------------------------------


@pytest.fixture
async def conn(tmp_path):
    """Fresh aiosqlite connection with schema applied."""
    db_path = tmp_path / "test.db"
    connection = await connect_template_db(db_path)
    yield connection
    await connection.close()


@pytest.fixture
def agent_store(conn):
    return SQLiteAgentStore(conn)


@pytest.fixture
def chat_repo(conn):
    return ChatSessionRepository(conn)


# ---------------------------------------------------------------------------
# Stub agent — minimal, following test_app_websocket_pause_resume.py pattern
# ---------------------------------------------------------------------------


class StubAgent:
    """Minimal Agent stub for WebSocket-layer testing."""

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

        class _LLMShim:
            max_context_tokens = 128_000

        self.llm = _LLMShim()

    async def step(
        self,
        user_input: str,  # noqa: ARG002
        on_chunk: Any = None,  # noqa: ARG002
        on_usage: Any = None,  # noqa: ARG002
    ) -> AsyncIterator[Message]:
        for m in self._step_messages:
            yield m

    async def resume_after_auth(self) -> AsyncIterator[Message]:
        if self._deferred_tool_calls is None:
            return
        self._deferred_tool_calls = None
        for m in self._resume_messages:
            yield m

    def reset(self) -> None:  # pragma: no cover
        self.messages = []
        self._deferred_tool_calls = None


# ---------------------------------------------------------------------------
# A01 — _persist_last_usage helper: DB write + in-memory mirror
# ---------------------------------------------------------------------------


async def test_persist_last_usage_writes_to_db_and_in_memory(
    agent_store: SQLiteAgentStore,
    chat_repo: ChatSessionRepository,
    conn: aiosqlite.Connection,
) -> None:
    """The shared helper writes the snapshot to DB and mirrors it in-memory.

    Assertion shape follows test_db_repositories.py:test_set_session_metadata_key_writes_new_key.
    """
    await agent_store.save(AgentConfig(name="agent1"))
    await chat_repo.create(ChatSession(id="s-p01", agent_name="agent1"))

    session = Session(
        id="s-p01",
        agent=StubAgent(),  # type: ignore[arg-type]
        created="2026-06-20T00:00:00+00:00",
        session_metadata=None,
    )

    with patch("the_one.interfaces.web.app.get_connection", return_value=conn):
        await _persist_last_usage(
            session,
            input_tokens=500,
            output_tokens=120,
            context_tokens=480,
        )

    # DB assertion
    loaded = await chat_repo.get("s-p01")
    assert loaded.session_metadata == {
        "last_usage": {
            "input_tokens": 500,
            "output_tokens": 120,
            "context_tokens": 480,
        }
    }

    # In-memory mirror assertion
    assert session.session_metadata == {
        "last_usage": {
            "input_tokens": 500,
            "output_tokens": 120,
            "context_tokens": 480,
        }
    }


async def test_persist_last_usage_preserves_sibling_keys(
    agent_store: SQLiteAgentStore,
    chat_repo: ChatSessionRepository,
    conn: aiosqlite.Connection,
) -> None:
    """Writing last_usage does not clobber sibling keys like ``routing``."""
    await agent_store.save(AgentConfig(name="agent1"))
    await chat_repo.create(ChatSession(id="s-p02", agent_name="agent1"))
    await chat_repo.set_session_metadata_key("s-p02", "routing", ["r1", "r2"])

    session = Session(
        id="s-p02",
        agent=StubAgent(),  # type: ignore[arg-type]
        created="2026-06-20T00:00:00+00:00",
        session_metadata={"routing": ["r1", "r2"]},
    )

    with patch("the_one.interfaces.web.app.get_connection", return_value=conn):
        await _persist_last_usage(
            session,
            input_tokens=100,
            output_tokens=20,
            context_tokens=90,
        )

    loaded = await chat_repo.get("s-p02")
    assert loaded.session_metadata == {
        "routing": ["r1", "r2"],
        "last_usage": {"input_tokens": 100, "output_tokens": 20, "context_tokens": 90},
    }
    # In-memory also preserves siblings
    assert session.session_metadata is not None
    assert session.session_metadata["routing"] == ["r1", "r2"]


# ---------------------------------------------------------------------------
# A02 — Non-paused settle: _process_and_broadcast persists last_usage
# ---------------------------------------------------------------------------


async def test_non_paused_settle_persists_last_usage_with_exact_context_tokens(
    agent_store: SQLiteAgentStore,
    chat_repo: ChatSessionRepository,
    conn: aiosqlite.Connection,
    monkeypatch,
) -> None:
    """Non-paused turn: DB gets the exact accumulated snapshot with
    context_tokens = last assistant message's input_tokens (not the sum).

    This is the key correctness assertion: with two assistant messages
    (input=300 then input=200), context_tokens must be 200, NOT 500.
    """
    await agent_store.save(AgentConfig(name="agent1"))
    await chat_repo.create(ChatSession(id="s-np01", agent_name="agent1"))

    # Two assistant messages: first step produces usage(300, 50),
    # second step produces usage(200, 80). The final snapshot should be:
    #   input_tokens  = 300 + 200 = 500
    #   output_tokens = 50  + 80  = 130
    #   context_tokens = 200  (the LAST message's input_tokens, not the sum)
    msg1 = Message.assistant("first response", usage=TokenUsage(input_tokens=300, output_tokens=50))
    msg2 = Message.assistant(
        "second response", usage=TokenUsage(input_tokens=200, output_tokens=80)
    )

    agent = StubAgent(step_messages=[msg1, msg2])
    session = Session(
        id="s-np01",
        agent=agent,  # type: ignore[arg-type]
        created="2026-06-20T00:00:00+00:00",
    )

    monkeypatch.setattr(web_app, "_ensure_ollama_model_loaded", AsyncMock(return_value=None))
    monkeypatch.setattr(web_app, "_save_session_to_db", AsyncMock(return_value=None))
    monkeypatch.setattr(web_app, "_send_to_session", AsyncMock(return_value=None))

    with patch("the_one.interfaces.web.app.get_connection", return_value=conn):
        await _process_and_broadcast(session, "hello")

    loaded = await chat_repo.get("s-np01")
    assert loaded.session_metadata is not None
    last_usage = loaded.session_metadata["last_usage"]
    assert last_usage["input_tokens"] == 500
    assert last_usage["output_tokens"] == 130
    # context_tokens MUST be 200 (last-input), NOT 500 (sum)
    assert last_usage["context_tokens"] == 200

    # In-memory must match the DB write
    assert session.session_metadata is not None
    assert session.session_metadata["last_usage"] == last_usage


async def test_non_paused_settle_zero_usage_does_not_write_snapshot(
    agent_store: SQLiteAgentStore,
    chat_repo: ChatSessionRepository,
    conn: aiosqlite.Connection,
    monkeypatch,
) -> None:
    """When no usage event fires (agent error before usage), no snapshot is written.

    Guards the prior snapshot: a turn with no usage must NOT write an all-zeros
    ``last_usage`` that would make a restored overlay read ``0 / max``.
    """
    await agent_store.save(AgentConfig(name="agent1"))
    await chat_repo.create(ChatSession(id="s-np02", agent_name="agent1"))

    # Write a prior snapshot so we can verify it survives
    await chat_repo.set_session_metadata_key(
        "s-np02",
        "last_usage",
        {"input_tokens": 400, "output_tokens": 60, "context_tokens": 380},
    )

    # Assistant message WITHOUT usage — simulates error before usage event
    msg_no_usage = Message.assistant("response without usage")

    agent = StubAgent(step_messages=[msg_no_usage])
    session = Session(
        id="s-np02",
        agent=agent,  # type: ignore[arg-type]
        created="2026-06-20T00:00:00+00:00",
    )

    monkeypatch.setattr(web_app, "_ensure_ollama_model_loaded", AsyncMock(return_value=None))
    monkeypatch.setattr(web_app, "_save_session_to_db", AsyncMock(return_value=None))
    monkeypatch.setattr(web_app, "_send_to_session", AsyncMock(return_value=None))

    with patch("the_one.interfaces.web.app.get_connection", return_value=conn):
        await _process_and_broadcast(session, "hello")

    # Prior snapshot must survive untouched
    loaded = await chat_repo.get("s-np02")
    assert loaded.session_metadata == {
        "last_usage": {"input_tokens": 400, "output_tokens": 60, "context_tokens": 380}
    }


async def test_non_paused_settle_in_memory_matches_db(
    agent_store: SQLiteAgentStore,
    chat_repo: ChatSessionRepository,
    conn: aiosqlite.Connection,
    monkeypatch,
) -> None:
    """In-memory session_metadata["last_usage"] matches what was written to DB."""
    await agent_store.save(AgentConfig(name="agent1"))
    await chat_repo.create(ChatSession(id="s-np03", agent_name="agent1"))

    msg = Message.assistant("hello", usage=TokenUsage(input_tokens=150, output_tokens=30))
    agent = StubAgent(step_messages=[msg])
    session = Session(
        id="s-np03",
        agent=agent,  # type: ignore[arg-type]
        created="2026-06-20T00:00:00+00:00",
    )

    monkeypatch.setattr(web_app, "_ensure_ollama_model_loaded", AsyncMock(return_value=None))
    monkeypatch.setattr(web_app, "_save_session_to_db", AsyncMock(return_value=None))
    monkeypatch.setattr(web_app, "_send_to_session", AsyncMock(return_value=None))

    with patch("the_one.interfaces.web.app.get_connection", return_value=conn):
        await _process_and_broadcast(session, "hello")

    loaded = await chat_repo.get("s-np03")
    assert session.session_metadata is not None
    assert session.session_metadata["last_usage"] == loaded.session_metadata["last_usage"]  # type: ignore[index]
    assert session.session_metadata["last_usage"] == {
        "input_tokens": 150,
        "output_tokens": 30,
        "context_tokens": 150,
    }


# ---------------------------------------------------------------------------
# A03 — Resume settle: _resume_paused_session persists resume-segment last_usage
# ---------------------------------------------------------------------------


async def test_resume_settle_persists_resume_segment_with_exact_context_tokens(
    agent_store: SQLiteAgentStore,
    chat_repo: ChatSessionRepository,
    conn: aiosqlite.Connection,
    monkeypatch,
) -> None:
    """Resume-path: snapshot reflects the resume segment only (not pre-pause partial).

    Two resumed assistant messages: usage(400, 70) then usage(250, 90).
    Expected snapshot:
      input_tokens  = 400 + 250 = 650
      output_tokens = 70  + 90  = 160
      context_tokens = 250  (the LAST resumed message's input_tokens, not the sum)
    """
    await agent_store.save(AgentConfig(name="agent1"))
    await chat_repo.create(ChatSession(id="s-r01", agent_name="agent1"))

    resumed_msg1 = Message.assistant(
        "resumed step 1", usage=TokenUsage(input_tokens=400, output_tokens=70)
    )
    resumed_msg2 = Message.assistant(
        "resumed step 2", usage=TokenUsage(input_tokens=250, output_tokens=90)
    )
    tc = ToolCall(id="tc1", name="some_tool", arguments={})

    agent = StubAgent(
        resume_messages=[resumed_msg1, resumed_msg2],
        deferred_tool_calls=[tc],
    )
    session = Session(
        id="s-r01",
        agent=agent,  # type: ignore[arg-type]
        created="2026-06-20T00:00:00+00:00",
    )

    monkeypatch.setattr(web_app, "_ensure_ollama_model_loaded", AsyncMock(return_value=None))
    monkeypatch.setattr(web_app, "_save_session_to_db", AsyncMock(return_value=None))
    monkeypatch.setattr(web_app, "_send_to_session", AsyncMock(return_value=None))

    with patch("the_one.interfaces.web.app.get_connection", return_value=conn):
        await _resume_paused_session(session)

    loaded = await chat_repo.get("s-r01")
    assert loaded.session_metadata is not None
    last_usage = loaded.session_metadata["last_usage"]
    assert last_usage["input_tokens"] == 650
    assert last_usage["output_tokens"] == 160
    # context_tokens MUST be 250 (last-input), NOT 650 (sum)
    assert last_usage["context_tokens"] == 250

    # In-memory must match DB
    assert session.session_metadata is not None
    assert session.session_metadata["last_usage"] == last_usage


async def test_resume_settle_zero_usage_does_not_write_snapshot(
    agent_store: SQLiteAgentStore,
    chat_repo: ChatSessionRepository,
    conn: aiosqlite.Connection,
    monkeypatch,
) -> None:
    """Resume with no assistant usage events leaves the prior snapshot intact."""
    await agent_store.save(AgentConfig(name="agent1"))
    await chat_repo.create(ChatSession(id="s-r02", agent_name="agent1"))

    # Write a prior snapshot
    await chat_repo.set_session_metadata_key(
        "s-r02",
        "last_usage",
        {"input_tokens": 300, "output_tokens": 50, "context_tokens": 280},
    )

    # Resume yields only a tool_result (no assistant usage event)
    tool_msg = Message.tool(ToolResult(tool_call_id="tc1", content="tool ok"))
    tc = ToolCall(id="tc1", name="some_tool", arguments={})

    agent = StubAgent(
        resume_messages=[tool_msg],
        deferred_tool_calls=[tc],
    )
    session = Session(
        id="s-r02",
        agent=agent,  # type: ignore[arg-type]
        created="2026-06-20T00:00:00+00:00",
    )

    monkeypatch.setattr(web_app, "_ensure_ollama_model_loaded", AsyncMock(return_value=None))
    monkeypatch.setattr(web_app, "_save_session_to_db", AsyncMock(return_value=None))
    monkeypatch.setattr(web_app, "_send_to_session", AsyncMock(return_value=None))

    with patch("the_one.interfaces.web.app.get_connection", return_value=conn):
        await _resume_paused_session(session)

    # Prior snapshot must survive untouched
    loaded = await chat_repo.get("s-r02")
    assert loaded.session_metadata == {
        "last_usage": {"input_tokens": 300, "output_tokens": 50, "context_tokens": 280}
    }


async def test_resume_settle_single_message_context_tokens_equals_that_messages_input(
    agent_store: SQLiteAgentStore,
    chat_repo: ChatSessionRepository,
    conn: aiosqlite.Connection,
    monkeypatch,
) -> None:
    """Single resumed assistant message: context_tokens == that message's input_tokens."""
    await agent_store.save(AgentConfig(name="agent1"))
    await chat_repo.create(ChatSession(id="s-r03", agent_name="agent1"))

    resumed_msg = Message.assistant(
        "single resume response", usage=TokenUsage(input_tokens=350, output_tokens=65)
    )
    tc = ToolCall(id="tc1", name="some_tool", arguments={})

    agent = StubAgent(
        resume_messages=[resumed_msg],
        deferred_tool_calls=[tc],
    )
    session = Session(
        id="s-r03",
        agent=agent,  # type: ignore[arg-type]
        created="2026-06-20T00:00:00+00:00",
    )

    monkeypatch.setattr(web_app, "_ensure_ollama_model_loaded", AsyncMock(return_value=None))
    monkeypatch.setattr(web_app, "_save_session_to_db", AsyncMock(return_value=None))
    monkeypatch.setattr(web_app, "_send_to_session", AsyncMock(return_value=None))

    with patch("the_one.interfaces.web.app.get_connection", return_value=conn):
        await _resume_paused_session(session)

    loaded = await chat_repo.get("s-r03")
    assert loaded.session_metadata is not None
    last_usage = loaded.session_metadata["last_usage"]
    assert last_usage["input_tokens"] == 350
    assert last_usage["output_tokens"] == 65
    assert last_usage["context_tokens"] == 350  # == the single message's input_tokens


async def test_resume_settle_in_memory_matches_db(
    agent_store: SQLiteAgentStore,
    chat_repo: ChatSessionRepository,
    conn: aiosqlite.Connection,
    monkeypatch,
) -> None:
    """In-memory session_metadata["last_usage"] matches DB after resume settle."""
    await agent_store.save(AgentConfig(name="agent1"))
    await chat_repo.create(ChatSession(id="s-r04", agent_name="agent1"))

    resumed_msg = Message.assistant("resume", usage=TokenUsage(input_tokens=180, output_tokens=40))
    tc = ToolCall(id="tc1", name="some_tool", arguments={})

    agent = StubAgent(
        resume_messages=[resumed_msg],
        deferred_tool_calls=[tc],
    )
    session = Session(
        id="s-r04",
        agent=agent,  # type: ignore[arg-type]
        created="2026-06-20T00:00:00+00:00",
    )

    monkeypatch.setattr(web_app, "_ensure_ollama_model_loaded", AsyncMock(return_value=None))
    monkeypatch.setattr(web_app, "_save_session_to_db", AsyncMock(return_value=None))
    monkeypatch.setattr(web_app, "_send_to_session", AsyncMock(return_value=None))

    with patch("the_one.interfaces.web.app.get_connection", return_value=conn):
        await _resume_paused_session(session)

    loaded = await chat_repo.get("s-r04")
    assert session.session_metadata is not None
    assert session.session_metadata["last_usage"] == loaded.session_metadata["last_usage"]  # type: ignore[index]


# ---------------------------------------------------------------------------
# Sortie 14 DD2 - cache counts never reach the usage frame or last_usage
# ---------------------------------------------------------------------------


async def test_cache_fields_do_not_change_usage_frame_or_last_usage(
    agent_store: SQLiteAgentStore,
    chat_repo: ChatSessionRepository,
    conn: aiosqlite.Connection,
    monkeypatch,
) -> None:
    """A TokenUsage carrying cache counts produces the same ``usage`` frame and
    ``last_usage`` as the same totals with the cache counts zeroed."""
    await agent_store.save(AgentConfig(name="agent1"))
    results: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}

    for label, (read, write) in {"cached": (7000, 900), "plain": (0, 0)}.items():
        sid = f"s-cache-{label}"
        await chat_repo.create(ChatSession(id=sid, agent_name="agent1"))
        msg = Message.assistant(
            "reply",
            usage=TokenUsage(
                input_tokens=8000,
                output_tokens=40,
                cache_read_tokens=read,
                cache_write_tokens=write,
            ),
        )
        session = Session(
            id=sid,
            agent=StubAgent(step_messages=[msg]),  # type: ignore[arg-type]
            created="2026-06-20T00:00:00+00:00",
        )
        send = AsyncMock(return_value=None)
        monkeypatch.setattr(web_app, "_ensure_ollama_model_loaded", AsyncMock(return_value=None))
        monkeypatch.setattr(web_app, "_save_session_to_db", AsyncMock(return_value=None))
        monkeypatch.setattr(web_app, "_send_to_session", send)

        with patch("the_one.interfaces.web.app.get_connection", return_value=conn):
            await _process_and_broadcast(session, "hello")

        frames = [c.args[1] for c in send.call_args_list if c.args[1].get("type") == "usage"]
        assert len(frames) == 1
        loaded = await chat_repo.get(sid)
        assert loaded.session_metadata is not None
        results[label] = (frames[0], loaded.session_metadata["last_usage"])

    frame, last_usage = results["cached"]
    assert set(frame) == {
        "type",
        "input_tokens",
        "output_tokens",
        "context_tokens",
        "max_context_tokens",
    }
    assert frame["context_tokens"] == 8000
    assert results["cached"] == results["plain"]
    assert not any("cache" in k for k in last_usage)
