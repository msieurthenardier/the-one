"""End-to-end factory integration for the openrouter provider type."""

from __future__ import annotations

from unittest.mock import patch

import aiosqlite
import pytest
from cryptography.fernet import Fernet

from the_one.agent.config import AgentConfig
from the_one.agent.factory import AgentFactory
from the_one.db.models import LLMProviderConfig
from the_one.db.repositories import LLMProviderRepository, SQLiteAgentStore
from the_one.db.schema import ensure_schema
from the_one.encryption import Encryptor
from the_one.llm.openrouter_provider import OpenRouterProvider


@pytest.mark.asyncio
async def test_factory_resolves_openrouter_provider(tmp_path, monkeypatch):
    """Stored encrypted openrouter provider + agent resolves to OpenRouterProvider
    via AgentFactory.create with all decrypted fields wired through."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    # Set up isolated DB + encryptor
    db_path = tmp_path / "test.db"
    conn = await aiosqlite.connect(str(db_path))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(conn)

    enc = Encryptor(Fernet.generate_key())
    prov_repo = LLMProviderRepository(conn, enc)
    agent_store = SQLiteAgentStore(conn)

    # Insert openrouter provider config — repo encrypts the key on write
    prov_cfg = LLMProviderConfig(
        id="p-or",
        name="OR",
        type="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key="sk-stored",
        config={"referer": "https://myapp.example", "title": "MyApp"},
    )
    await prov_repo.create(prov_cfg)

    # Insert agent referencing it
    agent_cfg = AgentConfig(
        name="alice",
        provider_config_id="p-or",
        llm_model="anthropic/claude-3.5-sonnet",
    )
    await agent_store.save(agent_cfg)

    # Patch the _connection singleton so get_connection() returns the test conn
    monkeypatch.setattr("the_one.db.connection._connection", conn)

    # Patch get_encryptor at its definition module — factory.py uses a
    # lazy `from the_one.encryption import get_encryptor` INSIDE create(),
    # so the binding is resolved at call-time against the_one.encryption
    # module, not the factory namespace.
    with (
        patch("the_one.agent.factory.settings") as mock_settings,
        patch("the_one.encryption.get_encryptor", return_value=enc),
    ):
        mock_settings.data_dir = tmp_path
        mock_settings.ensure_dirs = lambda: None

        # Build factory with no tool providers — avoids touching filesystem
        # allowlist / cross-config wiring. The real ToolConfigRepository runs
        # against the test DB and returns [] (no rows in tool_configs table).
        factory = AgentFactory(store=agent_store, tool_providers=[])
        agent = await factory.create("alice")

    # Assert llm is an OpenRouterProvider with the decrypted key + headers
    assert isinstance(agent.llm, OpenRouterProvider)
    assert agent.llm.client.api_key == "sk-stored"
    assert agent.llm.model == "anthropic/claude-3.5-sonnet"
    assert "openrouter.ai" in str(agent.llm.client.base_url)
    assert agent.llm.client.default_headers.get("HTTP-Referer") == "https://myapp.example"
    assert agent.llm.client.default_headers.get("X-Title") == "MyApp"

    await conn.close()
