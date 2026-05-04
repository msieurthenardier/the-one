"""Tests for Ollama auto-load on chat in _process_and_broadcast / _ensure_ollama_model_loaded."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import aiosqlite
import pytest
from conftest import FakeLLM

from the_one.agent.config import AgentConfig
from the_one.agent.core import Agent
from the_one.db.models import LLMProviderConfig
from the_one.db.repositories import LLMProviderRepository, SQLiteAgentStore
from the_one.db.schema import ensure_schema
from the_one.encryption import Encryptor

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
def encryptor():
    from cryptography.fernet import Fernet

    return Encryptor(Fernet.generate_key())


@pytest.fixture
async def ollama_provider(conn, encryptor):
    """Create an ollama provider config in the DB and return it."""
    repo = LLMProviderRepository(conn, encryptor)
    provider = LLMProviderConfig(
        id="ollama-local",
        name="Local Ollama",
        type="ollama",
        base_url="http://localhost:11434",
    )
    await repo.create(provider)
    return provider


@pytest.fixture
async def openai_provider(conn, encryptor):
    """Create an openai provider config in the DB and return it."""
    repo = LLMProviderRepository(conn, encryptor)
    provider = LLMProviderConfig(
        id="openai-prod",
        name="OpenAI",
        type="openai",
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
    )
    await repo.create(provider)
    return provider


@pytest.fixture
async def ollama_agent(conn, ollama_provider):
    """Create an agent config that uses the ollama provider."""
    store = SQLiteAgentStore(conn)
    config = AgentConfig(
        name="ollama-agent",
        provider_config_id="ollama-local",
        llm_model="qwen2.5:7b",
    )
    await store.save(config)
    return config


@pytest.fixture
async def openai_agent(conn, openai_provider):
    """Create an agent config that uses the openai provider."""
    store = SQLiteAgentStore(conn)
    config = AgentConfig(
        name="openai-agent",
        provider_config_id="openai-prod",
        llm_model="gpt-4o",
    )
    await store.save(config)
    return config


def _make_fake_agent() -> Agent:
    from the_one.tools.base import ToolRegistry

    return Agent(llm=FakeLLM([]), tools=ToolRegistry(), system_prompt="test")


def _make_session(app_module, agent_name: str | None, session_id: str = "test-session"):
    from the_one.interfaces.web.app import Session

    session = Session(
        id=session_id,
        agent=_make_fake_agent(),
        created="2024-01-01T00:00:00",
        agent_name=agent_name,
    )
    app_module._sessions[session_id] = session
    return session


@pytest.fixture
def patched_app(conn, encryptor, tmp_path):
    """Patch app module to use test DB and settings."""
    import the_one.interfaces.web.app as app_module
    from the_one.config import settings

    original_sessions = app_module._sessions
    app_module._sessions = {}

    with (
        patch.object(app_module, "get_connection", AsyncMock(return_value=conn)),
        patch.object(app_module, "get_encryptor", return_value=encryptor),
        patch("the_one.interfaces.web.app.settings", settings),
    ):
        yield app_module

    app_module._sessions = original_sessions


# ---------------------------------------------------------------------------
# Tests for _ensure_ollama_model_loaded
# ---------------------------------------------------------------------------


class TestEnsureOllamaModelLoaded:
    async def test_loads_model_when_not_running(self, patched_app, ollama_agent):
        """Should send loading message and call load_model when model is not loaded."""
        session = _make_session(patched_app, "ollama-agent")

        mock_ws = AsyncMock()
        session.subscribers.add(mock_ws)

        with (
            patch("the_one.llm.ollama_api.list_running", AsyncMock(return_value=[])) as mock_list,
            patch("the_one.llm.ollama_api.load_model", AsyncMock()) as mock_load,
        ):
            await patched_app._ensure_ollama_model_loaded(session)

            mock_list.assert_called_once_with("http://localhost:11434")
            mock_load.assert_called_once_with("http://localhost:11434", "qwen2.5:7b")

        # Check system message was sent
        calls = mock_ws.send_json.call_args_list
        assert any(c.args[0] == {"type": "system", "content": "Loading model..."} for c in calls)

    async def test_skips_when_model_already_loaded(self, patched_app, ollama_agent):
        """Should not send message or call load_model when model is running."""
        session = _make_session(patched_app, "ollama-agent")

        mock_ws = AsyncMock()
        session.subscribers.add(mock_ws)

        running = [{"name": "qwen2.5:7b", "size": 4_000_000_000}]

        with (
            patch("the_one.llm.ollama_api.list_running", AsyncMock(return_value=running)),
            patch("the_one.llm.ollama_api.load_model", AsyncMock()) as mock_load,
        ):
            await patched_app._ensure_ollama_model_loaded(session)
            mock_load.assert_not_called()

        # No system message sent
        mock_ws.send_json.assert_not_called()

    async def test_skips_for_non_ollama_provider(self, patched_app, openai_agent):
        """Should skip entirely for non-ollama providers."""
        session = _make_session(patched_app, "openai-agent")

        with (
            patch("the_one.llm.ollama_api.list_running", AsyncMock()) as mock_list,
            patch("the_one.llm.ollama_api.load_model", AsyncMock()) as mock_load,
        ):
            await patched_app._ensure_ollama_model_loaded(session)
            mock_list.assert_not_called()
            mock_load.assert_not_called()

    async def test_skips_for_default_agent_without_db_record(self, patched_app):
        """Default agent with no DB record should skip gracefully."""
        session = _make_session(patched_app, None)

        with (
            patch("the_one.llm.ollama_api.list_running", AsyncMock()) as mock_list,
        ):
            await patched_app._ensure_ollama_model_loaded(session)
            mock_list.assert_not_called()

    async def test_handles_ollama_connection_error(self, patched_app, ollama_agent, caplog):
        """Connection errors should be caught and logged, not propagated."""
        import logging

        session = _make_session(patched_app, "ollama-agent")

        with (
            patch(
                "the_one.llm.ollama_api.list_running",
                AsyncMock(side_effect=ConnectionError("Ollama unreachable")),
            ),
            caplog.at_level(logging.WARNING),
        ):
            # Should not raise
            await patched_app._ensure_ollama_model_loaded(session)

        assert "Auto-load check failed" in caplog.text

    async def test_handles_load_model_error(self, patched_app, ollama_agent, caplog):
        """load_model errors should be caught and logged, not propagated."""
        import logging

        session = _make_session(patched_app, "ollama-agent")

        with (
            patch("the_one.llm.ollama_api.list_running", AsyncMock(return_value=[])),
            patch(
                "the_one.llm.ollama_api.load_model",
                AsyncMock(side_effect=ConnectionError("Timeout loading")),
            ),
            caplog.at_level(logging.WARNING),
        ):
            await patched_app._ensure_ollama_model_loaded(session)

        assert "Auto-load check failed" in caplog.text

    async def test_matches_model_with_latest_tag(self, patched_app, ollama_agent):
        """Should match when running model has :latest suffix."""
        session = _make_session(patched_app, "ollama-agent")

        running = [{"name": "qwen2.5:7b:latest"}]

        with (
            patch("the_one.llm.ollama_api.list_running", AsyncMock(return_value=running)),
            patch("the_one.llm.ollama_api.load_model", AsyncMock()) as mock_load,
        ):
            await patched_app._ensure_ollama_model_loaded(session)
            # qwen2.5:7b won't match qwen2.5:7b:latest exactly —
            # the :latest logic handles "name" == "model:latest" case
            # Since "qwen2.5:7b:latest" != "qwen2.5:7b" and
            # "qwen2.5:7b:latest" != "qwen2.5:7b:latest" (f"{model_name}:latest" = "qwen2.5:7b:latest")  # noqa: E501
            # Actually it DOES match: f"{model_name}:latest" == "qwen2.5:7b:latest"
            mock_load.assert_not_called()

    async def test_no_match_for_different_model(self, patched_app, ollama_agent):
        """Should not match a different model that happens to be running."""
        session = _make_session(patched_app, "ollama-agent")

        running = [{"name": "llama3:8b", "size": 4_000_000_000}]

        with (
            patch("the_one.llm.ollama_api.list_running", AsyncMock(return_value=running)),
            patch("the_one.llm.ollama_api.load_model", AsyncMock()) as mock_load,
        ):
            await patched_app._ensure_ollama_model_loaded(session)
            mock_load.assert_called_once_with("http://localhost:11434", "qwen2.5:7b")
