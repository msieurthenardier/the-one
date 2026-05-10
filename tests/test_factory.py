"""Tests for AgentFactory."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from conftest import FakeLLM, StubTool

from the_one.agent.config import AgentConfig
from the_one.agent.factory import AgentFactory
from the_one.db.models import LLMProviderConfig, ToolConfig
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

    def __init__(self) -> None:
        self.captured_agent_name: str | None = None

    @property
    def name(self) -> str:
        return "stub"

    def get_tools(
        self,
        tool_configs: dict[str, dict] | None = None,
        agent_overrides: dict[str, dict] | None = None,
        agent_name: str | None = None,
    ) -> list[Tool]:
        # Signature widens to match the (post-L1b) ToolProvider Protocol —
        # `agent_name` is the per-agent state-isolation key (F4 Decision 4).
        # F2 doesn't exercise the args here — the factory test asserts they
        # arrive populated via the `received_args` helper test below.
        self.captured_agent_name = agent_name
        return [
            StubTool("tool_a", agent_name=agent_name),
            StubTool("tool_b", agent_name=agent_name),
            StubTool("tool_c", agent_name=agent_name),
        ]


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

    # F6 L1: factory now constructs `ToolConfigRepository(conn)` and awaits
    # `list()` (returning `list[ToolConfig]`) — switched from L3's
    # `list_all()` -> `dict[str, dict]` shape. The factory projects this
    # into `tool_configs_by_name` (dict) AND `disabled_names` (set) and
    # composes operator-disable with the per-agent enabled/disabled
    # whitelist. Patch with an empty list so the resolver path
    # short-circuits cleanly. Without `list = AsyncMock(return_value=[])`
    # the await would yield an `AsyncMock`, breaking the provider call.
    mock_tool_repo = AsyncMock()
    mock_tool_repo.list = AsyncMock(return_value=[])

    with (
        patch("the_one.agent.factory.get_provider", _fake_get_provider),
        patch("the_one.agent.factory.settings") as mock_settings,
        patch("the_one.db.connection.get_connection", new_callable=AsyncMock),
        patch("the_one.encryption.get_encryptor", return_value=AsyncMock()),
        patch("the_one.db.repositories.LLMProviderRepository", return_value=mock_repo),
        patch("the_one.db.repositories.ToolConfigRepository", return_value=mock_tool_repo),
    ):
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
        # F10 L1: search_tools + search_mcps are always in the registry
        # (registered before the built-in loop, bypass enabled/disabled filter).
        # The enabled_tools whitelist still gates the built-in catalog; only
        # tool_a passes. The full registry is the F10 baseline stubs + tool_a.
        assert "search_tools" in agent.tools.tool_names
        assert "search_mcps" in agent.tools.tool_names
        assert "tool_a" in agent.tools.tool_names
        assert "tool_b" not in agent.tools.tool_names
        assert "tool_c" not in agent.tools.tool_names


class TestResolverWiring:
    """Verify the factory passes tool_configs and agent_overrides through to
    the provider's get_tools call (the resolver invocation path)."""

    async def test_factory_passes_resolver_args_to_provider(self, store: InMemoryStore) -> None:
        """When AgentFactory.create() runs, it should:
        * Construct a ToolConfigRepository, await list_all(), and pass that
          dict as the first positional arg to provider.get_tools(...).
        * Pass config.tool_overrides (or {} if None) as the second arg.
        """
        captured: dict[str, Any] = {}

        class CapturingProvider:
            @property
            def name(self) -> str:
                return "capturing"

            def get_tools(
                self,
                tool_configs: dict[str, dict] | None = None,
                agent_overrides: dict[str, dict] | None = None,
                agent_name: str | None = None,
            ) -> list[Tool]:
                captured["tool_configs"] = tool_configs
                captured["agent_overrides"] = agent_overrides
                captured["agent_name"] = agent_name
                return [StubTool("tool_a")]

        mock_repo = AsyncMock()
        mock_repo.get = AsyncMock(return_value=_make_provider_config())
        mock_tool_repo = AsyncMock()
        mock_tool_repo.list = AsyncMock(
            return_value=[
                ToolConfig(
                    name="shell",
                    config={"output_cap": 1000},
                    enabled=True,
                ),
            ]
        )

        cfg = AgentConfig(
            name="resolver-wired",
            provider_config_id="test-provider",
            llm_model="stub-model",
            tool_overrides={"shell": {"output_cap": 500}},
        )
        await store.save(cfg)

        with (
            patch("the_one.agent.factory.get_provider", _fake_get_provider),
            patch("the_one.agent.factory.settings") as mock_settings,
            patch("the_one.db.connection.get_connection", new_callable=AsyncMock),
            patch("the_one.encryption.get_encryptor", return_value=AsyncMock()),
            patch(
                "the_one.db.repositories.LLMProviderRepository",
                return_value=mock_repo,
            ),
            patch(
                "the_one.db.repositories.ToolConfigRepository",
                return_value=mock_tool_repo,
            ),
        ):
            mock_settings.agents_dir = Path("/tmp/test-agents")
            mock_settings.data_dir = Path("/tmp/test-data")
            mock_settings.ensure_dirs = lambda: None

            factory = AgentFactory(store=store, tool_providers=[CapturingProvider()])
            await factory.create("resolver-wired")

        assert captured["tool_configs"] == {"shell": {"output_cap": 1000}}
        assert captured["agent_overrides"] == {"shell": {"output_cap": 500}}
        # L1b: factory threads the agent name into get_tools so providers
        # can scope per-agent runtime state (e.g. PTY session ownership).
        assert captured["agent_name"] == "resolver-wired"

    async def test_factory_passes_empty_overrides_when_none(self, store: InMemoryStore) -> None:
        """When config.tool_overrides is None, the factory should pass {}
        (NOT None) to provider.get_tools — the locked-down NULL semantic
        flips to an empty dict at the factory boundary so the provider
        doesn't have to disambiguate."""
        captured: dict[str, Any] = {}

        class CapturingProvider:
            @property
            def name(self) -> str:
                return "capturing"

            def get_tools(
                self,
                tool_configs: dict[str, dict] | None = None,
                agent_overrides: dict[str, dict] | None = None,
                agent_name: str | None = None,
            ) -> list[Tool]:
                captured["agent_overrides"] = agent_overrides
                captured["agent_name"] = agent_name
                return []

        mock_repo = AsyncMock()
        mock_repo.get = AsyncMock(return_value=_make_provider_config())
        mock_tool_repo = AsyncMock()
        mock_tool_repo.list = AsyncMock(return_value=[])

        cfg = AgentConfig(
            name="no-overrides",
            provider_config_id="test-provider",
            llm_model="stub-model",
            # tool_overrides defaults to None
        )
        await store.save(cfg)

        with (
            patch("the_one.agent.factory.get_provider", _fake_get_provider),
            patch("the_one.agent.factory.settings") as mock_settings,
            patch("the_one.db.connection.get_connection", new_callable=AsyncMock),
            patch("the_one.encryption.get_encryptor", return_value=AsyncMock()),
            patch(
                "the_one.db.repositories.LLMProviderRepository",
                return_value=mock_repo,
            ),
            patch(
                "the_one.db.repositories.ToolConfigRepository",
                return_value=mock_tool_repo,
            ),
        ):
            mock_settings.agents_dir = Path("/tmp/test-agents")
            mock_settings.data_dir = Path("/tmp/test-data")
            mock_settings.ensure_dirs = lambda: None

            factory = AgentFactory(store=store, tool_providers=[CapturingProvider()])
            await factory.create("no-overrides")

        assert captured["agent_overrides"] == {}


class TestAgentNamePlumbing:
    """L1b: AgentFactory.create(name) must thread `name` into the provider so
    each tool instance carries `_agent_name == name`. PTY session ownership
    in F4 keys on `(agent_name, session_id)` — without this thread, sessions
    cannot be scoped per-agent."""

    async def test_agent_name_threads_to_tools(
        self, factory: AgentFactory, store: InMemoryStore
    ) -> None:
        cfg = AgentConfig(
            name="test-agent",
            provider_config_id="test-provider",
            llm_model="stub-model",
        )
        await store.save(cfg)
        agent = await factory.create("test-agent")
        # Every tool must have observed the agent name during construction.
        for tool in agent.tools._tools.values():  # type: ignore[attr-defined]
            assert tool._agent_name == "test-agent", (
                f"tool {tool.name} got _agent_name={tool._agent_name!r}"
            )


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
