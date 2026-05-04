"""Tests for F6 L1 operator-disable enforcement at the AgentFactory boundary.

L1 widens `AgentFactory.create()` to read `ToolConfigRepository.list()`
(full models with the L0 `enabled` flag) and project two derived
structures: `tool_configs_by_name: dict[str, dict]` for the resolver
path AND `disabled_names: set[str]` for the registry-build filter.

Disabled tools are filtered out of the registry independently of the
per-agent `enabled_tools` / `disabled_tools` whitelist.

The introspection path (`BuiltinToolProvider.get_tools()` with no args)
is NOT modified — `GET /api/tools` continues to list all tools regardless
of disable state. Enforcement is factory-only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import pytest

from the_one.agent.config import AgentConfig
from the_one.agent.factory import AgentFactory
from the_one.db.models import LLMProviderConfig
from the_one.db.repositories import ToolConfigRepository
from the_one.db.schema import ensure_schema
from the_one.tools.base import Tool


class InMemoryStore:
    """Minimal async store backed by a dict."""

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

    async def exists(self, name: str) -> bool:
        return name in self._data


class StubProvider:
    """Returns a fixed set of tools mirroring builtin tool names."""

    @property
    def name(self) -> str:
        return "stub"

    def get_tools(
        self,
        tool_configs: dict[str, dict] | None = None,
        agent_overrides: dict[str, dict] | None = None,
        agent_name: str | None = None,
    ) -> list[Tool]:
        from conftest import StubTool

        return [
            StubTool("web_search", agent_name=agent_name),
            StubTool("fetch_url", agent_name=agent_name),
            StubTool("shell", agent_name=agent_name),
        ]


def _fake_get_provider(name: str, **kwargs: Any) -> Any:
    from conftest import FakeLLM

    return FakeLLM(responses=[])


def _make_provider_config() -> LLMProviderConfig:
    return LLMProviderConfig(
        id="test-provider",
        name="Test Provider",
        type="ollama",
        base_url="http://localhost:11434/v1",
    )


@pytest.fixture
async def db_conn(tmp_path):
    """Open a fresh isolated SQLite DB with the v9 schema applied."""
    conn = await aiosqlite.connect(str(tmp_path / "test.db"))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(conn)
    yield conn
    await conn.close()


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()


def _patch_block(conn, mock_provider_repo, real_tool_repo: ToolConfigRepository):
    """Patch the factory's DB/provider/encryptor wiring; route the real
    `ToolConfigRepository(conn)` construction to the supplied repo so we
    exercise the actual `list()` call against the in-memory DB."""
    return patch.multiple(
        "the_one.agent.factory",
        get_provider=_fake_get_provider,
        settings=MagicMock(
            agents_dir=Path("/tmp/test-agents"),
            data_dir=Path("/tmp/test-data"),
            ensure_dirs=lambda: None,
        ),
    )


async def _build_factory(
    conn,
    store: InMemoryStore,
    cfg: AgentConfig,
    provider: StubProvider,
):
    await store.save(cfg)
    mock_provider_repo = AsyncMock()
    mock_provider_repo.get = AsyncMock(return_value=_make_provider_config())

    with patch("the_one.agent.factory.get_provider", _fake_get_provider), \
         patch("the_one.agent.factory.settings") as mock_settings, \
         patch(
             "the_one.db.connection.get_connection",
             new_callable=AsyncMock,
             return_value=conn,
         ), \
         patch("the_one.encryption.get_encryptor", return_value=AsyncMock()), \
         patch(
             "the_one.db.repositories.LLMProviderRepository",
             return_value=mock_provider_repo,
         ):
        mock_settings.agents_dir = Path("/tmp/test-agents")
        mock_settings.data_dir = Path("/tmp/test-data")
        mock_settings.ensure_dirs = lambda: None

        factory = AgentFactory(store=store, tool_providers=[provider])
        agent = await factory.create(cfg.name)
    return agent


class TestDisableEnforcement:
    async def test_disabled_tool_excluded_from_registry(
        self, db_conn, store: InMemoryStore
    ) -> None:
        """Operator disables `web_search`; factory registry omits it."""
        repo = ToolConfigRepository(db_conn)
        await repo.upsert("web_search", {}, enabled=False)

        cfg = AgentConfig(
            name="agent-a",
            provider_config_id="test-provider",
            llm_model="stub-model",
        )
        agent = await _build_factory(db_conn, store, cfg, StubProvider())
        names = agent.tools.tool_names
        assert "web_search" not in names
        assert "fetch_url" in names
        assert "shell" in names

    async def test_disabled_tool_independent_of_per_agent_whitelist(
        self, db_conn, store: InMemoryStore
    ) -> None:
        """Operator disable wins even if the agent's `enabled_tools`
        whitelist names the tool."""
        repo = ToolConfigRepository(db_conn)
        await repo.upsert("web_search", {}, enabled=False)

        cfg = AgentConfig(
            name="agent-a",
            provider_config_id="test-provider",
            llm_model="stub-model",
            enabled_tools=["web_search", "fetch_url"],
        )
        agent = await _build_factory(db_conn, store, cfg, StubProvider())
        assert "web_search" not in agent.tools.tool_names
        assert "fetch_url" in agent.tools.tool_names

    async def test_re_enabling_restores_tool_to_registry(
        self, db_conn, store: InMemoryStore
    ) -> None:
        """Disable, then re-enable; the registry contains the tool again."""
        repo = ToolConfigRepository(db_conn)
        await repo.upsert("web_search", {}, enabled=False)
        await repo.upsert("web_search", {}, enabled=True)

        cfg = AgentConfig(
            name="agent-a",
            provider_config_id="test-provider",
            llm_model="stub-model",
        )
        agent = await _build_factory(db_conn, store, cfg, StubProvider())
        assert "web_search" in agent.tools.tool_names

    async def test_per_agent_disable_independent_of_operator_disable(
        self, db_conn, store: InMemoryStore
    ) -> None:
        """Operator-enabled, agent-disabled (via `disabled_tools`); the
        tool is still absent. Confirms the two filters are independent."""
        # No DB row → operator default (enabled=True).
        cfg = AgentConfig(
            name="agent-a",
            provider_config_id="test-provider",
            llm_model="stub-model",
            disabled_tools=["web_search"],
        )
        agent = await _build_factory(db_conn, store, cfg, StubProvider())
        assert "web_search" not in agent.tools.tool_names
        assert "fetch_url" in agent.tools.tool_names

    async def test_factory_does_not_call_list_all(
        self, db_conn, store: InMemoryStore
    ) -> None:
        """Light regression net: the L1 projection switches the factory's
        repo call from `list_all()` to `list()`. Spy on the repository
        and verify `list_all` is never invoked on the factory path."""
        cfg = AgentConfig(
            name="agent-a",
            provider_config_id="test-provider",
            llm_model="stub-model",
        )
        await store.save(cfg)
        mock_provider_repo = AsyncMock()
        mock_provider_repo.get = AsyncMock(return_value=_make_provider_config())

        # Build a wrapper repo that delegates to the real one but tracks
        # whether `list_all` was called.
        real_repo = ToolConfigRepository(db_conn)
        list_all_calls = 0
        list_calls = 0

        original_list_all = real_repo.list_all
        original_list = real_repo.list

        async def tracked_list_all() -> dict[str, dict]:
            nonlocal list_all_calls
            list_all_calls += 1
            return await original_list_all()

        async def tracked_list():
            nonlocal list_calls
            list_calls += 1
            return await original_list()

        real_repo.list_all = tracked_list_all  # type: ignore[assignment]
        real_repo.list = tracked_list  # type: ignore[assignment]

        with patch("the_one.agent.factory.get_provider", _fake_get_provider), \
             patch("the_one.agent.factory.settings") as mock_settings, \
             patch(
                 "the_one.db.connection.get_connection",
                 new_callable=AsyncMock,
                 return_value=db_conn,
             ), \
             patch("the_one.encryption.get_encryptor", return_value=AsyncMock()), \
             patch(
                 "the_one.db.repositories.LLMProviderRepository",
                 return_value=mock_provider_repo,
             ), \
             patch(
                 "the_one.db.repositories.ToolConfigRepository",
                 return_value=real_repo,
             ):
            mock_settings.agents_dir = Path("/tmp/test-agents")
            mock_settings.data_dir = Path("/tmp/test-data")
            mock_settings.ensure_dirs = lambda: None

            factory = AgentFactory(
                store=store, tool_providers=[StubProvider()]
            )
            await factory.create(cfg.name)

        assert list_all_calls == 0, "factory must not call repo.list_all() in L1+"
        assert list_calls == 1, "factory must call repo.list() exactly once"
