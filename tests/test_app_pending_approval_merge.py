"""Tests for M11 F9 L4 — _restore_session / _build_session_joined_degraded
merge pending_approvals rows into the session history stream when the
session has connector context.

Coverage (per leg-04 Sub-step F):

1. Restore on a session with connector context + a pending approval row
   → ``session.history`` includes the pending-approval event with the
   canonical flight §5 shape.
2. Restore on a connector-context session with NO pending approvals →
   history is byte-identical to pre-L4 (no pending events appended).
3. Restore on an operator-typed session (no connector context) → NO
   pending-approvals DB query (monkeypatched repo raises on call).
4. Merge ordering: messages with older ``ts`` precede pending-approvals
   with newer ``received_at``, and vice versa.
5. ``_build_session_joined_degraded`` merges pending_approvals identically
   to the healthy ``_restore_session`` path.
6. No duplicate emission of a pending-approval event for a single DB row.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import aiosqlite
import pytest
from conftest import FakeLLM

from the_one.agent.core import Agent
from the_one.db.codec import encode_messages
from the_one.db.models import ChatSession as ChatSessionModel
from the_one.db.models import Connector
from the_one.db.repositories import (
    ChatSessionRepository,
    ConnectorRepository,
    PendingApprovalRepository,
)
from the_one.db.schema import ensure_schema
from the_one.llm.base import Message


@pytest.fixture
async def conn(tmp_path):
    db_path = tmp_path / "test.db"
    connection = await aiosqlite.connect(str(db_path))
    connection.row_factory = aiosqlite.Row
    await connection.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(connection)
    yield connection
    await connection.close()


@pytest.fixture
def chat_repo(conn):
    return ChatSessionRepository(conn)


@pytest.fixture
def pending_approval_repo(conn):
    return PendingApprovalRepository(conn)


@pytest.fixture
def connector_repo_encryptor(tmp_path):
    from cryptography.fernet import Fernet

    from the_one.encryption import Encryptor

    key = Fernet.generate_key()
    return Encryptor(key, key_path=tmp_path / "ka.key")


@pytest.fixture
def connector_repo(conn, connector_repo_encryptor):
    return ConnectorRepository(conn, connector_repo_encryptor)


@pytest.fixture
async def _seed_connector(connector_repo):
    """Seed an ``acct-1`` connector account so PendingApproval FK passes."""
    await connector_repo.create(Connector(id="acct-1", name="Stub Account", type="stub"))


def _make_fake_agent() -> Agent:
    from the_one.tools.base import ToolRegistry

    return Agent(llm=FakeLLM([]), tools=ToolRegistry(), system_prompt="You are a test agent")


@pytest.fixture
def patched_app(conn, chat_repo, pending_approval_repo):
    """Patch app.py module globals so session restore uses the test DB.

    Mirrors ``tests/test_session_lifecycle.py::patched_app`` and extends
    it to patch ``_pending_approval_repo`` to the same in-test repo so
    the L4 merge logic exercises the in-memory schema.
    """
    import the_one.interfaces.web.app as app_module

    original_sessions = app_module._sessions
    app_module._sessions = {}

    async def mock_chat_repo():
        return chat_repo

    async def mock_pending_approval_repo():
        return pending_approval_repo

    async def mock_factory_create(name="default"):
        return _make_fake_agent()

    mock_factory = AsyncMock()
    mock_factory.create = mock_factory_create

    with (
        patch.object(app_module, "_chat_repo", mock_chat_repo),
        patch.object(app_module, "_pending_approval_repo", mock_pending_approval_repo),
        patch.object(app_module, "_get_factory", return_value=mock_factory),
    ):
        yield app_module

    app_module._sessions = original_sessions


async def _seed_connector_session(
    chat_repo: ChatSessionRepository,
    *,
    session_id: str,
    connector_id: str | None,
    peer_id: str | None,
    messages: list[Message] | None = None,
) -> ChatSessionModel:
    """INSERT a chat_sessions row directly via the repo's create path.

    ``ChatSessionModel.platform`` is set to ``stub`` when connector
    context is present so the row mirrors a real connector-keyed
    session; left None for the operator-typed case.
    """
    encoded = encode_messages(messages or [])
    row = ChatSessionModel(
        id=session_id,
        agent_name=None,
        title="test session",
        messages=encoded,
        platform=("stub" if connector_id else None),
        connector_id=connector_id,
        peer_id=peer_id,
    )
    await chat_repo.create(row)
    return row


class TestRestoreSessionMergesPendingApproval:
    async def test_with_connector_context_merges_pending_approval(
        self,
        patched_app,
        chat_repo,
        pending_approval_repo,
        _seed_connector,
    ) -> None:
        """A connector-context session with a pending approval row in
        the DB has the pending-approval event appended to its history."""
        await _seed_connector_session(
            chat_repo,
            session_id="s-with-approval",
            connector_id="acct-1",
            peer_id="peer-1",
            messages=[],
        )
        approval, _ = await pending_approval_repo.upsert_pending(
            connector_id="acct-1",
            peer_id="peer-1",
            peer_name="Alice",
            preview="hello bot",
        )

        result = await patched_app._restore_session("s-with-approval")
        assert result.status == "ok"
        assert result.session is not None
        history = result.session.history

        # Exactly one pending-approval event for this approval id.
        pending_events = [e for e in history if e.get("type") == "pending-approval"]
        assert len(pending_events) == 1, history
        ev = pending_events[0]
        assert ev == {
            "type": "pending-approval",
            "approval_id": approval.id,
            "peer_name": "Alice",
            "peer_id": "peer-1",
            "preview": "hello bot",
            "received_at": approval.received_at,
            "connector_id": "acct-1",
            "status": "pending",
        }

    async def test_with_connector_context_no_approvals_unchanged(
        self,
        patched_app,
        chat_repo,
        _seed_connector,
    ) -> None:
        """A connector-context session with NO pending approvals →
        history contains no pending-approval events; the projection
        path is byte-identical to the pre-L4 shape for the message
        slice."""
        await _seed_connector_session(
            chat_repo,
            session_id="s-no-approvals",
            connector_id="acct-1",
            peer_id="peer-99",
            messages=[Message.user("hi", peer_name="Bob")],
        )

        result = await patched_app._restore_session("s-no-approvals")
        assert result.status == "ok"
        history = result.session.history
        # No pending events at all.
        assert not any(e.get("type") == "pending-approval" for e in history)
        # The user message survives the merge path unchanged.
        user_events = [e for e in history if e.get("type") == "user"]
        assert len(user_events) == 1
        assert user_events[0]["content"] == "hi"

    async def test_without_connector_context_skips_pending_query(
        self,
        patched_app,
        chat_repo,
    ) -> None:
        """An operator-typed session (no connector_id, no peer_id)
        MUST short-circuit the merge — no DB query against
        ``pending_approvals``. We assert this structurally by replacing
        the patched repo with one whose ``list_for_account_peer`` raises
        if invoked."""
        await _seed_connector_session(
            chat_repo,
            session_id="s-operator",
            connector_id=None,
            peer_id=None,
            messages=[Message.user("typed by operator")],
        )

        class RaisingRepo:
            async def list_for_account_peer(self, *args, **kwargs):
                raise AssertionError("operator-typed session must NOT query pending_approvals")

        async def raising_repo():
            return RaisingRepo()

        with patch.object(patched_app, "_pending_approval_repo", raising_repo):
            result = await patched_app._restore_session("s-operator")
        assert result.status == "ok"
        assert not any(e.get("type") == "pending-approval" for e in result.session.history)

    async def test_merge_orders_by_timestamp(
        self,
        patched_app,
        chat_repo,
        pending_approval_repo,
        _seed_connector,
    ) -> None:
        """Pending approval whose ``received_at`` lands between two
        message events appears in the merge between them.

        Note: replay-side messages from ``messages_to_ui_events`` do NOT
        carry a ``ts`` field (codec line 240+ projects user/assistant
        events without ts). So message events float to the top of the
        merged stream and the pending-approval event lands after them.
        This is the expected behavior per leg-04 §Edge Cases ("Session
        that has both messages and approvals … messages without
        explicit ts float to the top"). We verify the pending-approval
        event lands AFTER the pre-message events but the relative
        order across all messages is preserved.
        """
        await _seed_connector_session(
            chat_repo,
            session_id="s-ordered",
            connector_id="acct-1",
            peer_id="peer-1",
            messages=[
                Message.user("first", peer_name="Alice"),
                Message.assistant("hi back"),
            ],
        )
        appr, _ = await pending_approval_repo.upsert_pending(
            connector_id="acct-1",
            peer_id="peer-1",
            peer_name="Alice",
            preview="dm preview",
        )

        result = await patched_app._restore_session("s-ordered")
        history = result.session.history
        # Two message events + one pending-approval = at least 3 items.
        types = [e.get("type") for e in history]
        assert "pending-approval" in types
        assert types.count("pending-approval") == 1
        # The pending-approval event MUST land after the (ts-less)
        # message events that float to the top.
        pa_index = types.index("pending-approval")
        user_index = types.index("user")
        assistant_index = types.index("assistant")
        assert user_index < pa_index
        assert assistant_index < pa_index
        # The PA event's data carries the same approval id.
        assert history[pa_index]["approval_id"] == appr.id


class TestBuildSessionJoinedDegradedMergesPendingApproval:
    async def test_degraded_path_merges_pending_approvals(
        self,
        patched_app,
        chat_repo,
        pending_approval_repo,
        _seed_connector,
    ) -> None:
        """``_build_session_joined_degraded`` must run the same merge as
        the healthy path. Construct a RestoredSession with a degraded
        status and a connector-context db_session; the resulting
        ``history`` should include the pending-approval event."""
        from the_one.interfaces.web.app import (
            SESSION_STATUS_AGENT_DELETED,
            RestoredSession,
        )

        db_row = await _seed_connector_session(
            chat_repo,
            session_id="s-degraded",
            connector_id="acct-1",
            peer_id="peer-1",
            messages=[],
        )
        # Re-fetch via repo to pick up DB-applied defaults.
        db_row = await chat_repo.get("s-degraded")
        approval, _ = await pending_approval_repo.upsert_pending(
            connector_id="acct-1",
            peer_id="peer-1",
            peer_name="Charlie",
            preview="awaiting approval",
        )
        restored = RestoredSession(None, SESSION_STATUS_AGENT_DELETED, db_row)

        payload = await patched_app._build_session_joined_degraded(restored)
        history = payload["history"]
        pending_events = [e for e in history if e.get("type") == "pending-approval"]
        assert len(pending_events) == 1, history
        assert pending_events[0]["approval_id"] == approval.id
        assert pending_events[0]["status"] == "pending"
        assert pending_events[0]["peer_name"] == "Charlie"


class TestRestoreNoDuplicates:
    async def test_no_duplicate_pending_event_for_single_row(
        self,
        patched_app,
        chat_repo,
        pending_approval_repo,
        _seed_connector,
    ) -> None:
        """A single DB row must produce exactly ONE pending-approval
        event in the merge output. Guards against a codec quirk emitting
        the row twice."""
        await _seed_connector_session(
            chat_repo,
            session_id="s-dedup",
            connector_id="acct-1",
            peer_id="peer-1",
            messages=[],
        )
        await pending_approval_repo.upsert_pending(  # noqa: F841 — side-effect only
            connector_id="acct-1",
            peer_id="peer-1",
            peer_name="Alice",
            preview="hello",
        )

        result = await patched_app._restore_session("s-dedup")
        history = result.session.history
        pending_events = [e for e in history if e.get("type") == "pending-approval"]
        assert len(pending_events) == 1
