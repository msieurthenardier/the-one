"""Tests for AgentFactory."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from conftest import FakeLLM, StubTool

from the_one.agent.config import AgentConfig
from the_one.agent.factory import AgentFactory
from the_one.agent.store import FilesystemConfigStore
from the_one.tools.base import Tool

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


@pytest.fixture
def store(tmp_path: Path) -> FilesystemConfigStore:
    return FilesystemConfigStore(tmp_path / "agents")


@pytest.fixture
def factory(store: FilesystemConfigStore) -> AgentFactory:
    with patch("the_one.agent.factory.get_provider", _fake_get_provider), \
         patch("the_one.agent.factory.settings") as mock_settings:
        mock_settings.llm_provider = "fake"
        mock_settings.llm_model = "stub-model"
        mock_settings.llm_base_url = None
        mock_settings.agents_dir = store.agents_dir
        mock_settings.data_dir = store.agents_dir.parent
        mock_settings.ensure_dirs = lambda: None
        yield AgentFactory(store=store, tool_providers=[StubToolProvider()])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDefaultAgent:
    def test_create_default_returns_agent(self, factory: AgentFactory) -> None:
        agent = factory.create()
        assert agent is not None
        assert agent.max_iterations == 20

    def test_default_has_tools(self, factory: AgentFactory) -> None:
        agent = factory.create()
        names = agent.tools.tool_names
        assert "tool_a" in names
        assert "tool_b" in names
        assert "tool_c" in names

    def test_default_has_system_prompt(self, factory: AgentFactory) -> None:
        agent = factory.create()
        assert len(agent.system_prompt) > 0


class TestNamedAgent:
    def test_create_from_stored_config(
        self, factory: AgentFactory, store: FilesystemConfigStore
    ) -> None:
        cfg = AgentConfig(
            name="custom",
            description="A custom agent",
            llm_provider="fake",
            llm_model="stub-model",
            max_iterations=5,
        )
        store.save(cfg)
        agent = factory.create("custom")
        assert agent.max_iterations == 5

    def test_unknown_agent_raises_key_error(self, factory: AgentFactory) -> None:
        with pytest.raises(KeyError, match="Unknown agent"):
            factory.create("nonexistent")


class TestToolFiltering:
    def test_disabled_tools_excluded(
        self, factory: AgentFactory, store: FilesystemConfigStore
    ) -> None:
        cfg = AgentConfig(
            name="limited",
            llm_provider="fake",
            llm_model="stub-model",
            disabled_tools=["tool_a"],
        )
        store.save(cfg)
        agent = factory.create("limited")
        assert "tool_a" not in agent.tools.tool_names
        assert "tool_b" in agent.tools.tool_names

    def test_enabled_tools_whitelist(
        self, factory: AgentFactory, store: FilesystemConfigStore
    ) -> None:
        cfg = AgentConfig(
            name="restricted",
            llm_provider="fake",
            llm_model="stub-model",
            enabled_tools=["tool_a"],
        )
        store.save(cfg)
        agent = factory.create("restricted")
        assert agent.tools.tool_names == ["tool_a"]


class TestListAgents:
    def test_includes_default(self, factory: AgentFactory) -> None:
        names = factory.list_agents()
        assert "default" in names

    def test_includes_stored_agents(
        self, factory: AgentFactory, store: FilesystemConfigStore
    ) -> None:
        store.save(AgentConfig(name="alpha"))
        store.save(AgentConfig(name="bravo"))
        names = factory.list_agents()
        assert "default" in names
        assert "alpha" in names
        assert "bravo" in names
