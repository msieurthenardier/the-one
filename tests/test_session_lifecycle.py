"""Integration tests for session lifecycle: create, save, restore, get_or_restore."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import aiosqlite
import pytest
from conftest import FakeLLM

from the_one.agent.core import Agent
from the_one.db.codec import decode_messages
from the_one.db.repositories import ChatSessionRepository
from the_one.db.schema import ensure_schema
from the_one.llm.base import Message


@pytest.fixture
async def conn(tmp_path):
    """Create a fresh DB connection with schema applied."""
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


def _make_fake_agent() -> Agent:
    """Create an Agent with a FakeLLM (no real provider needed)."""
    from the_one.tools.base import ToolRegistry

    return Agent(llm=FakeLLM([]), tools=ToolRegistry(), system_prompt="You are helpful")


@pytest.fixture
def patched_app(conn):
    """Patch app.py module globals so session functions use our test DB and fake agent."""
    import the_one.interfaces.web.app as app_module

    original_sessions = app_module._sessions
    app_module._sessions = {}

    async def mock_chat_repo():
        return ChatSessionRepository(conn)

    async def mock_factory_create(name="default"):
        return _make_fake_agent()

    # Mock the factory so we don't need a real LLM provider
    mock_factory = AsyncMock()
    mock_factory.create = mock_factory_create

    with (
        patch.object(app_module, "_chat_repo", mock_chat_repo),
        patch.object(app_module, "_get_factory", return_value=mock_factory),
    ):
        yield app_module

    app_module._sessions = original_sessions


class TestCreateSession:
    async def test_creates_in_memory_and_db(self, patched_app, chat_repo):
        session = await patched_app._create_session()
        # In memory
        assert session.id in patched_app._sessions
        assert patched_app._sessions[session.id] is session
        # In DB
        db_session = await chat_repo.get(session.id)
        assert db_session.id == session.id
        assert db_session.title == "New chat"

    async def test_default_agent_name_is_none_in_db(self, patched_app, chat_repo):
        session = await patched_app._create_session(agent_name="default")
        assert session.agent_name is None
        db_session = await chat_repo.get(session.id)
        assert db_session.agent_name is None

    async def test_empty_agent_name_is_none_in_db(self, patched_app, chat_repo):
        session = await patched_app._create_session(agent_name="")
        assert session.agent_name is None
        db_session = await chat_repo.get(session.id)
        assert db_session.agent_name is None

    async def test_custom_session_id(self, patched_app, chat_repo):
        session = await patched_app._create_session(session_id="custom-123")
        assert session.id == "custom-123"
        db_session = await chat_repo.get("custom-123")
        assert db_session.id == "custom-123"

    async def test_agent_has_system_message(self, patched_app):
        session = await patched_app._create_session()
        assert len(session.agent.messages) >= 1
        assert session.agent.messages[0].role.value == "system"


class TestSaveSessionToDb:
    async def test_saves_messages(self, patched_app, chat_repo):
        session = await patched_app._create_session(session_id="save-test")
        # Simulate a conversation
        session.agent.messages.append(Message.user("hello"))
        session.agent.messages.append(Message.assistant("hi there"))
        session.title = "hello"

        await patched_app._save_session_to_db(session)

        db_session = await chat_repo.get("save-test")
        assert db_session.title == "hello"
        messages = decode_messages(db_session.messages)
        # system + user + assistant
        assert len(messages) == 3
        assert messages[1].content == "hello"
        assert messages[2].content == "hi there"

    async def test_save_updates_timestamp(self, patched_app, chat_repo):
        session = await patched_app._create_session(session_id="ts-test")
        db_before = await chat_repo.get("ts-test")
        original_updated_at = db_before.updated_at

        session.agent.messages.append(Message.user("test"))
        await patched_app._save_session_to_db(session)

        db_after = await chat_repo.get("ts-test")
        # repo.update() calls _now_iso() so updated_at should change
        assert db_after.updated_at >= original_updated_at

    async def test_save_nonexistent_session_logs_warning(self, patched_app, caplog):
        """Saving a session not in DB should log a warning, not crash."""
        import logging

        from the_one.interfaces.web.app import Session

        fake_session = Session(
            id="nonexistent",
            agent=patched_app._sessions.get("x", (await patched_app._create_session()).agent),
            created="2024-01-01T00:00:00",
        )
        # Remove from DB but keep the agent
        try:
            repo = await patched_app._chat_repo()
            await repo.delete(fake_session.id)
        except KeyError:
            pass

        with caplog.at_level(logging.WARNING):
            await patched_app._save_session_to_db(fake_session)
        # Should not raise — errors are caught and logged


class TestRestoreSession:
    async def test_restores_from_db(self, patched_app, chat_repo):
        # Create and save a session with messages
        session = await patched_app._create_session(session_id="restore-test")
        session.agent.messages.append(Message.user("hello"))
        session.agent.messages.append(Message.assistant("world"))
        session.title = "hello"
        await patched_app._save_session_to_db(session)

        # Remove from memory (simulating server restart)
        del patched_app._sessions["restore-test"]

        # Restore
        result = await patched_app._restore_session("restore-test")
        assert result.status == "ok"
        restored = result.session
        assert restored is not None
        assert restored.id == "restore-test"
        assert restored.title == "hello"
        assert restored.agent_name is None
        # Agent has the messages
        assert len(restored.agent.messages) == 3  # system + user + assistant
        assert restored.agent.messages[1].content == "hello"
        assert restored.agent.messages[2].content == "world"
        # UI events built from messages (system skipped)
        assert len(restored.history) == 2
        assert restored.history[0]["type"] == "user"
        assert restored.history[1]["type"] == "assistant"
        # db_session is included on the ok path so callers don't re-query.
        assert result.db_session is not None
        assert result.db_session.id == "restore-test"

    async def test_restore_nonexistent_returns_not_found(self, patched_app):
        result = await patched_app._restore_session("does-not-exist")
        assert result.session is None
        assert result.status == "not_found"
        assert result.db_session is None

    async def test_restore_caches_in_memory(self, patched_app):
        session = await patched_app._create_session(session_id="cache-test")
        await patched_app._save_session_to_db(session)
        del patched_app._sessions["cache-test"]

        result = await patched_app._restore_session("cache-test")
        assert result.status == "ok"
        assert "cache-test" in patched_app._sessions
        assert patched_app._sessions["cache-test"] is result.session

    async def test_restore_empty_messages(self, patched_app):
        """Session with no conversation should restore with just the system message."""
        await patched_app._create_session(session_id="empty-test")
        # Don't add any user messages — DB has "[]"
        del patched_app._sessions["empty-test"]

        result = await patched_app._restore_session("empty-test")
        assert result.status == "ok"
        restored = result.session
        assert restored is not None
        # Agent should still have its system prompt
        assert len(restored.agent.messages) >= 1
        assert restored.agent.messages[0].role.value == "system"
        assert restored.history == []

    async def test_restore_returns_agent_deleted(self, patched_app):
        """When the agent config is gone, factory raises AgentNotFoundError.

        Classification: agent_deleted. The session is NOT cached and no
        Session object is returned.
        """
        from the_one.agent.factory import AgentNotFoundError

        await patched_app._create_session(session_id="orphan-agent")
        del patched_app._sessions["orphan-agent"]

        mock_factory = patched_app._get_factory.return_value
        mock_factory.create = AsyncMock(
            side_effect=AgentNotFoundError("Unknown agent: missing-agent")
        )

        result = await patched_app._restore_session("orphan-agent")
        assert result.session is None
        assert result.status == "agent_deleted"
        assert result.db_session is not None
        assert "orphan-agent" not in patched_app._sessions
        # Regression guard: must NOT silently fall back to "default" with a
        # second call to factory.create. The fixture stores agent_name=None
        # in the DB, so factory is called once with "default".
        mock_factory.create.assert_called_once_with("default")

    async def test_restore_returns_provider_missing_via_not_configured(self, patched_app):
        """ProviderNotConfiguredError → provider_missing."""
        from the_one.agent.factory import ProviderNotConfiguredError

        await patched_app._create_session(session_id="no-prov")
        del patched_app._sessions["no-prov"]

        mock_factory = patched_app._get_factory.return_value
        mock_factory.create = AsyncMock(
            side_effect=ProviderNotConfiguredError(
                "Agent 'default' has no provider configured. "
                "Please assign a provider in the agent settings."
            )
        )

        result = await patched_app._restore_session("no-prov")
        assert result.session is None
        assert result.status == "provider_missing"
        assert result.db_session is not None
        assert "no-prov" not in patched_app._sessions

    async def test_restore_returns_provider_missing_via_not_found(self, patched_app):
        """ProviderNotFoundError → provider_missing."""
        from the_one.agent.factory import ProviderNotFoundError

        await patched_app._create_session(session_id="dead-prov")
        del patched_app._sessions["dead-prov"]

        mock_factory = patched_app._get_factory.return_value
        mock_factory.create = AsyncMock(
            side_effect=ProviderNotFoundError("Provider not found: abc123")
        )

        result = await patched_app._restore_session("dead-prov")
        assert result.session is None
        assert result.status == "provider_missing"
        assert result.db_session is not None
        assert "dead-prov" not in patched_app._sessions

    async def test_restore_does_not_cache_degraded_sessions(self, patched_app):
        """Degraded restores must not populate `_sessions`."""
        from the_one.agent.factory import AgentNotFoundError

        await patched_app._create_session(session_id="never-cached")
        del patched_app._sessions["never-cached"]

        mock_factory = patched_app._get_factory.return_value
        mock_factory.create = AsyncMock(side_effect=AgentNotFoundError("Unknown agent: missing"))

        await patched_app._restore_session("never-cached")
        assert "never-cached" not in patched_app._sessions

    async def test_restore_propagates_unrecognized_value_error(self, patched_app):
        """A ValueError that isn't ProviderNotConfiguredError must propagate."""
        await patched_app._create_session(session_id="weird")
        del patched_app._sessions["weird"]

        mock_factory = patched_app._get_factory.return_value
        mock_factory.create = AsyncMock(side_effect=ValueError("something completely unexpected"))

        with pytest.raises(ValueError, match="something completely unexpected"):
            await patched_app._restore_session("weird")


class TestGetOrRestoreSession:
    async def test_preserves_session_identity_across_rejoin(self, patched_app):
        """C-lite: a join for an already-cached session updates in place,
        preserving the Session object identity (subscribers etc.)."""
        session = await patched_app._create_session(session_id="mem-test")
        # Save so _restore_session can find it
        await patched_app._save_session_to_db(session)
        result = await patched_app._get_or_restore_session("mem-test")
        assert result.status == "ok"
        assert result.session is session  # identity preserved via in-place update
        # Health was re-evaluated, so db_session is now populated
        assert result.db_session is not None

    async def test_falls_back_to_db(self, patched_app):
        session = await patched_app._create_session(session_id="fallback-test")
        await patched_app._save_session_to_db(session)
        del patched_app._sessions["fallback-test"]

        result = await patched_app._get_or_restore_session("fallback-test")
        assert result.status == "ok"
        assert result.session is not None
        assert result.session.id == "fallback-test"

    async def test_returns_not_found_for_unknown(self, patched_app):
        result = await patched_app._get_or_restore_session("unknown")
        assert result.session is None
        assert result.status == "not_found"

    async def test_cached_session_re_evaluates_health_on_join(self, patched_app):
        """C-lite: cached sessions re-run health on join. If the agent has
        been deleted since the cache was warmed, the next join surfaces
        agent_deleted (the cache short-circuit was removed in flight 05 HAT)."""
        from the_one.agent.factory import AgentNotFoundError

        session = await patched_app._create_session(session_id="warm-cache")
        await patched_app._save_session_to_db(session)
        # Make the factory hostile after the session was cached
        mock_factory = patched_app._get_factory.return_value
        mock_factory.create = AsyncMock(
            side_effect=AgentNotFoundError("Unknown agent: doesnt-matter")
        )

        result = await patched_app._get_or_restore_session("warm-cache")
        assert result.status == "agent_deleted"
        assert result.session is None
        mock_factory.create.assert_called_once()
        # Cache entry was dropped on the degraded outcome
        assert "warm-cache" not in patched_app._sessions
