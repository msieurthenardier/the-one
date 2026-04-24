"""Tests for AgentFactory."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from conftest import FakeLLM, StubTool

from the_one.agent.config import AgentConfig
from the_one.agent.factory import AgentFactory
from the_one.db.models import LLMProviderConfig
from the_one.tools.base import Tool

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class InMemoryStore:
    """Minimal async store backed by a dict for testing."""

    def __init__(self) -> None:
        self._data: dict[str, AgentConfig] = {}

    async def list_agents(self) -> list[str]:
        return sorted(self._data.keys())

    async def load(self, name: str) -> AgentConfig:
        if name not in self._data:
            raise KeyError(f"Agent config not found: {name}")
        return self._data[name]

    async def save(self, config: AgentConfig) -> None:
        self._data[config.name] = config

    async def delete(self, name: str) -> None:
        if name not in self._data:
            raise KeyError(f"Agent config not found: {name}")
        del self._data[name]

    async def exists(self, name: str) -> bool:
        return name in self._data


class StubToolProvider:
    """Minimal ToolProvider that returns a fixed set of StubTools."""

    @property
    def name(self) -> str:
        return "stub"

    def get_tools(self) -> list[Tool]:
        return [StubTool("tool_a"), StubTool("tool_b"), StubTool("tool_c")]


def _fake_get_provider(name: str, **kwargs: Any) -> FakeLLM:
    """Return a FakeLLM regardless of provider name."""
    return FakeLLM(responses=[])


def _make_provider_config(
    provider_id: str = "test-provider",
    ptype: str = "ollama",
    base_url: str = "http://localhost:11434/v1",
) -> LLMProviderConfig:
    return LLMProviderConfig(
        id=provider_id,
        name="Test Provider",
        type=ptype,
        base_url=base_url,
    )


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture
def factory(store: InMemoryStore) -> AgentFactory:
    mock_repo = AsyncMock()
    mock_repo.get = AsyncMock(return_value=_make_provider_config())

    with patch("the_one.agent.factory.get_provider", _fake_get_provider), \
         patch("the_one.agent.factory.settings") as mock_settings, \
         patch("the_one.db.connection.get_connection", new_callable=AsyncMock), \
         patch("the_one.encryption.get_encryptor", return_value=AsyncMock()), \
         patch("the_one.db.repositories.LLMProviderRepository", return_value=mock_repo):
        mock_settings.agents_dir = Path("/tmp/test-agents")
        mock_settings.data_dir = Path("/tmp/test-data")
        mock_settings.ensure_dirs = lambda: None
        yield AgentFactory(store=store, tool_providers=[StubToolProvider()])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDefaultAgent:
    async def test_create_default_raises_without_provider(self, store: InMemoryStore) -> None:
        """Default agent has no provider_config_id, so create() should raise."""
        with patch("the_one.agent.factory.settings") as mock_settings:
            mock_settings.ensure_dirs = lambda: None
            factory = AgentFactory(store=store, tool_providers=[StubToolProvider()])
            with pytest.raises(ValueError, match="no provider configured"):
                await factory.create()

    async def test_default_has_system_prompt(self, store: InMemoryStore) -> None:
        """Default config should have a system prompt even without a provider."""
        factory = AgentFactory(store=store, tool_providers=[StubToolProvider()])
        # Use _default_config directly since create() will fail without provider
        config = factory._default_config()
        assert config.get_system_prompt() != ""


class TestNamedAgent:
    async def test_create_from_stored_config(
        self, factory: AgentFactory, store: InMemoryStore
    ) -> None:
        cfg = AgentConfig(
            name="custom",
            description="A custom agent",
            provider_config_id="test-provider",
            llm_model="stub-model",
            max_iterations=5,
        )
        await store.save(cfg)
        agent = await factory.create("custom")
        assert agent.max_iterations == 5

    async def test_unknown_agent_raises_key_error(self, factory: AgentFactory) -> None:
        with pytest.raises(KeyError, match="Unknown agent"):
            await factory.create("nonexistent")

    async def test_agent_without_provider_raises_value_error(
        self, factory: AgentFactory, store: InMemoryStore
    ) -> None:
        cfg = AgentConfig(
            name="no-provider",
            provider_config_id=None,
        )
        await store.save(cfg)
        with pytest.raises(ValueError, match="no provider configured"):
            await factory.create("no-provider")


class TestToolFiltering:
    async def test_disabled_tools_excluded(
        self, factory: AgentFactory, store: InMemoryStore
    ) -> None:
        cfg = AgentConfig(
            name="limited",
            provider_config_id="test-provider",
            llm_model="stub-model",
            disabled_tools=["tool_a"],
        )
        await store.save(cfg)
        agent = await factory.create("limited")
        assert "tool_a" not in agent.tools.tool_names
        assert "tool_b" in agent.tools.tool_names

    async def test_enabled_tools_whitelist(
        self, factory: AgentFactory, store: InMemoryStore
    ) -> None:
        cfg = AgentConfig(
            name="restricted",
            provider_config_id="test-provider",
            llm_model="stub-model",
            enabled_tools=["tool_a"],
        )
        await store.save(cfg)
        agent = await factory.create("restricted")
        assert agent.tools.tool_names == ["tool_a"]


class TestListAgents:
    async def test_includes_default(self, factory: AgentFactory) -> None:
        names = await factory.list_agents()
        assert "default" in names

    async def test_includes_stored_agents(
        self, factory: AgentFactory, store: InMemoryStore
    ) -> None:
        await store.save(AgentConfig(name="alpha"))
        await store.save(AgentConfig(name="bravo"))
        names = await factory.list_agents()
        assert "default" in names
        assert "alpha" in names
        assert "bravo" in names
