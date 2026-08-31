"""M16 F06 L03 — in-process integration round-trip test.

Proves the full persist → restart → restore chain end-to-end:

  1. Drive a turn through the real ``_process_and_broadcast`` path using a
     StubAgent that yields a Message with ``usage=TokenUsage(input_tokens=N)``.
     Assert ``last_usage`` lands in the DB with ``context_tokens == N``.

  2. Drop the in-memory ``_sessions`` entry (``_sessions.pop``), then call
     ``_restore_session``.  After the pop, ``session_id in _sessions`` is
     False, so restore falls through to the fresh-Session DB-reload branch
     (``app.py:970-986``) — this is a genuine restart simulation, NOT the
     warm-cache branch.  Assert the returned Session object is a fresh
     identity (differs from the pre-pop object).

  3. ok-path: ``_build_session_joined_ok(restored.session)
     ["session_metadata"]["last_usage"]["context_tokens"] == N``.

  4. degraded-path (separate setup): construct a ``RestoredSession`` with a
     degraded status by hand (mirroring L02's
     ``tests/test_session_joined_payload.py`` pattern), with its
     ``db.session_metadata`` carrying the written ``last_usage``, and assert
     ``_build_session_joined_degraded(restored)["session_metadata"]
     ["last_usage"]["context_tokens"] == N``.

N = 750 (arbitrary but large enough to distinguish from zero noise).

The stub-agent approach (rather than a live MockProvider through the factory)
is used here because wiring a MockProvider through the real agent factory
in-process requires live DB access to the providers table, agent_configs, etc.,
which adds significant fixture weight without covering new seam territory.  The
MockProvider's config["input_tokens"] seam is covered separately by the unit
tests in tests/test_mock_provider.py and by the browser flow test.

DB-assertion shape follows ``test_db_repositories.py:2988-3053``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import aiosqlite
import pytest

from the_one.agent.config import AgentConfig
from the_one.db.models import ChatSession
from the_one.db.models import ChatSession as ChatSessionModel
from the_one.db.repositories import ChatSessionRepository, SQLiteAgentStore
from the_one.db.schema import ensure_schema
from the_one.interfaces.web import app as web_app
from the_one.interfaces.web.app import (
    SESSION_STATUS_AGENT_DELETED,
    RestoredSession,
    Session,
    _build_session_joined_degraded,
    _build_session_joined_ok,
    _process_and_broadcast,
    _restore_session,
    _sessions,
    _sessions_lock,
)
from the_one.llm.base import Message, TokenUsage

# ---------------------------------------------------------------------------
# N — the token count we thread through the entire round-trip
# ---------------------------------------------------------------------------

_N = 750  # arbitrary; large enough to distinguish from incidental zeros


# ---------------------------------------------------------------------------
# Fixtures (mirror test_last_usage_persistence.py)
# ---------------------------------------------------------------------------


@pytest.fixture
async def conn(tmp_path):
    """Fresh aiosqlite connection with schema applied."""
    db_path = tmp_path / "test.db"
    connection = await aiosqlite.connect(str(db_path))
    connection.row_factory = aiosqlite.Row
    await connection.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(connection)
    yield connection
    await connection.close()


@pytest.fixture
def agent_store(conn):
    return SQLiteAgentStore(conn)


@pytest.fixture
def chat_repo(conn):
    return ChatSessionRepository(conn)


# ---------------------------------------------------------------------------
# Stub agent — yields one assistant Message with usage.input_tokens == _N
# ---------------------------------------------------------------------------


class _StubAgentN:
    """Minimal Agent stub that yields one assistant Message with input_tokens=N."""

    def __init__(self) -> None:
        self.messages: list[Message] = []

        class _LLMShim:
            max_context_tokens = 128_000

        self.llm = _LLMShim()
        self._deferred_tool_calls = None

    async def step(
        self,
        user_input: str,  # noqa: ARG002
        on_chunk: Any = None,  # noqa: ARG002
        on_usage: Any = None,  # noqa: ARG002
    ) -> AsyncIterator[Message]:
        yield Message.assistant(
            "round-trip test response",
            usage=TokenUsage(input_tokens=_N, output_tokens=20),
        )

    async def resume_after_auth(self) -> AsyncIterator[Message]:  # pragma: no cover
        if False:
            yield  # type: ignore[unreachable]

    def reset(self) -> None:  # pragma: no cover
        self.messages = []


# ---------------------------------------------------------------------------
# Helper: ensure the session is NOT in _sessions (clean state for each test)
# ---------------------------------------------------------------------------


async def _evict(session_id: str) -> None:
    """Remove session_id from _sessions under the lock."""
    async with _sessions_lock:
        _sessions.pop(session_id, None)


# ---------------------------------------------------------------------------
# Round-trip test
# ---------------------------------------------------------------------------


async def test_last_usage_round_trip_db_reload_branch(
    agent_store: SQLiteAgentStore,
    chat_repo: ChatSessionRepository,
    conn: aiosqlite.Connection,
    monkeypatch,
) -> None:
    """Full persist → DB-reload restore → both join payloads carry context_tokens == N.

    Steps:
      1. Drive a turn → last_usage in DB (context_tokens == N).
      2. Drop _sessions entry → _restore_session takes the DB-reload branch.
      3. Assert returned Session is a fresh object (proves DB path ran, not warm-cache).
      4. ok-path: _build_session_joined_ok payload carries context_tokens == N.
      5. degraded-path (hand-constructed): _build_session_joined_degraded payload
         carries context_tokens == N.
    """
    session_id = "s-rt01"
    await agent_store.save(AgentConfig(name="agent1"))
    await chat_repo.create(ChatSession(id=session_id, agent_name="agent1"))

    agent = _StubAgentN()
    session = Session(
        id=session_id,
        agent=agent,  # type: ignore[arg-type]
        created=datetime.now(timezone.utc).isoformat(),
        session_metadata=None,
    )

    # ── Step 1: register the session in _sessions and drive a turn ─────────
    async with _sessions_lock:
        _sessions[session_id] = session

    monkeypatch.setattr(web_app, "_ensure_ollama_model_loaded", AsyncMock(return_value=None))
    monkeypatch.setattr(web_app, "_save_session_to_db", AsyncMock(return_value=None))
    monkeypatch.setattr(web_app, "_send_to_session", AsyncMock(return_value=None))

    with patch("the_one.interfaces.web.app.get_connection", return_value=conn):
        await _process_and_broadcast(session, "hello")

    # Verify last_usage is in the DB with the exact expected values.
    loaded = await chat_repo.get(session_id)
    assert loaded.session_metadata is not None, "DB must carry session_metadata after turn"
    last_usage_written = loaded.session_metadata["last_usage"]
    assert last_usage_written["context_tokens"] == _N, (
        f"DB context_tokens must be {_N}, got {last_usage_written['context_tokens']}"
    )
    assert last_usage_written["input_tokens"] == _N
    assert last_usage_written["output_tokens"] == 20

    # ── Step 2: drop the warm session → force DB-reload branch ─────────────
    pre_pop_session = _sessions.get(session_id)
    assert pre_pop_session is not None, "session must be in _sessions before pop"

    async with _sessions_lock:
        _sessions.pop(session_id, None)

    # Confirm it's gone (so _restore_session will NOT hit the warm-cache branch).
    assert session_id not in _sessions, "session must be absent from _sessions before restore"

    # ── Step 3: call _restore_session → must take DB-reload branch ─────────
    # The factory is called inside _restore_session to rebuild the agent.
    # We need to mock factory.create so it returns our stub (no real LLM setup).
    mock_factory = AsyncMock()
    mock_factory.create = AsyncMock(return_value=_StubAgentN())
    monkeypatch.setattr(web_app, "_get_factory", lambda: mock_factory)

    # _restore_session internally calls _chat_repo() → get_connection() → DB.
    # Patch get_connection to return our test conn. (Mission 23 Flight 1,
    # backend-removal leg: _restore_session no longer calls
    # _merge_pending_approvals_into_history — deleted along with the
    # connector package, DD-2 — so no second patch is needed.)
    with patch("the_one.interfaces.web.app.get_connection", return_value=conn):
        restored = await _restore_session(session_id)

    # Assert the restore succeeded.
    from the_one.interfaces.web.app import SESSION_STATUS_OK

    assert restored.status == SESSION_STATUS_OK, f"restore status: {restored.status}"
    assert restored.session is not None

    # Assert we hit the DB-reload branch (fresh Session object, NOT the pre-pop one).
    assert restored.session is not pre_pop_session, (
        "Restored Session must be a fresh object (DB-reload branch), "
        "not the pre-pop warm-cache Session identity."
    )

    # ── Step 4: ok-path payload carries context_tokens == N ────────────────
    ok_payload = _build_session_joined_ok(restored.session)
    ok_meta = ok_payload.get("session_metadata")
    assert ok_meta is not None, "ok payload must carry session_metadata"
    ok_last_usage = ok_meta.get("last_usage")
    assert ok_last_usage is not None, "ok payload session_metadata must have last_usage"
    assert ok_last_usage["context_tokens"] == _N, (
        f"ok-path context_tokens must be {_N}, got {ok_last_usage['context_tokens']}"
    )
    assert ok_last_usage["input_tokens"] == _N
    assert ok_last_usage["output_tokens"] == 20

    # ── Step 5: degraded-path payload carries context_tokens == N ──────────
    # _restore_session after a successful pop+reload returns SESSION_STATUS_OK,
    # so it cannot also yield a degraded payload.  Construct a RestoredSession
    # with a degraded status by hand, with db.session_metadata carrying the
    # written last_usage.  This mirrors the L02 degraded-path test pattern in
    # tests/test_session_joined_payload.py.
    degraded_db_row = ChatSessionModel(
        id=session_id,
        agent_name="agent1",
        session_metadata=loaded.session_metadata,  # carries the written last_usage
    )
    degraded_restored = RestoredSession(None, SESSION_STATUS_AGENT_DELETED, degraded_db_row)

    degraded_payload = await _build_session_joined_degraded(degraded_restored)

    degraded_meta = degraded_payload.get("session_metadata")
    assert degraded_meta is not None, "degraded payload must carry session_metadata"
    degraded_last_usage = degraded_meta.get("last_usage")
    assert degraded_last_usage is not None, "degraded payload session_metadata must have last_usage"
    assert degraded_last_usage["context_tokens"] == _N, (
        f"degraded-path context_tokens must be {_N}, got {degraded_last_usage['context_tokens']}"
    )
    assert degraded_last_usage["input_tokens"] == _N
    assert degraded_last_usage["output_tokens"] == 20

    # Cleanup: remove the restored session from _sessions (test isolation).
    await _evict(session_id)
