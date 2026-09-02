"""Tests for AgentFactory."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from conftest import FakeLLM, StubTool

from the_one.agent.config import (
    AgentConfig,
)
from the_one.agent.core import CONTINUE_SCHEMA, SEARCH_TOOLS_SCHEMA
from the_one.agent.factory import AgentFactory
from the_one.db.models import LLMProviderConfig, ToolConfig
from the_one.llm.base import Message
from the_one.tools.base import Tool
from the_one.tools.builtins import BuiltinToolProvider
from the_one.tools.connector_send import SEND_TO_PLATFORM_CHANNEL_TOOL_NAME

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


@pytest.fixture
def builtin_factory(store: InMemoryStore) -> AgentFactory:
    """Mission 23 Flight 3 Leg 2 (DD-5): a factory wired to the REAL
    ``BuiltinToolProvider`` (not ``StubToolProvider``) so the carve-out
    pin tests exercise the real ``send_to_platform_channel`` tool and its
    real ``to_schema()`` output — never a hand-built dict, matching the
    dedup comparison ``_on_search_match`` performs against
    ``SearchTools``'s ``registry.all_schemas()`` source.
    """
    mock_repo = AsyncMock()
    mock_repo.get = AsyncMock(return_value=_make_provider_config())
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
        yield AgentFactory(store=store, tool_providers=[BuiltinToolProvider()])


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
        # search_tools is always in the registry (registered before the
        # built-in loop, bypassing the enabled/disabled filter). The
        # enabled_tools whitelist still gates the built-in catalog; only
        # tool_a passes.
        assert "search_tools" in agent.tools.tool_names
        assert "tool_a" in agent.tools.tool_names
        assert "tool_b" not in agent.tools.tool_names
        assert "tool_c" not in agent.tools.tool_names

    async def test_builtins_whitelist_does_not_strip_mcp_tools(
        self, factory: AgentFactory, store: InMemoryStore
    ) -> None:
        # F09-08 regression: a built-ins-only `enabled_tools` whitelist (as the
        # agent editor emits) must NOT filter out `mcp__`-prefixed MCP tools.
        # MCP enablement is governed by `mcp_overrides` upstream in
        # MCPToolProvider.get_tools_for_agent, not the built-in whitelist.
        mcp_names = ["mcp__github__create_issue", "mcp__github__list_repos"]

        class StubMCPProvider:
            async def get_tools_for_agent(
                self, config: AgentConfig, agent_name: str | None = None
            ) -> list[Tool]:
                return [StubTool(n, agent_name=agent_name) for n in mcp_names]

        factory.mcp_provider = StubMCPProvider()
        cfg = AgentConfig(
            name="mcp-restricted",
            provider_config_id="test-provider",
            llm_model="stub-model",
            enabled_tools=["tool_a"],  # built-ins-only whitelist
            mcp_source_ids=["github"],
        )
        await store.save(cfg)
        # `mcp_source_ids` also drives factory.py's `_build_source_index`
        # (search_tools index — unrelated to what this test exercises via
        # `mcp_provider`/`StubMCPProvider` above). Left unpatched,
        # `MCPSourceRepository` runs for real against the `factory` fixture's
        # AsyncMock `conn`, whose auto-specced `.execute(...)` returns an
        # un-awaited coroutine instead of an async-context-manager result —
        # raising an unrelated TypeError that the broad `except (KeyError,
        # Exception)` in `_build_source_index` swallows, leaking an
        # "AsyncMockMixin._execute_mock_call was never awaited"
        # RuntimeWarning. Patch it to raise the *intended* KeyError path
        # (matching the "deleted source" comment in `_build_source_index`)
        # so the index build takes the real skip-silently branch instead of
        # an accidental mock-shape crash.
        mock_source_repo = AsyncMock()
        mock_source_repo.get = AsyncMock(side_effect=KeyError("source not found"))
        with patch(
            "the_one.db.repositories.MCPSourceRepository",
            return_value=mock_source_repo,
        ):
            agent = await factory.create("mcp-restricted")
        # Built-in whitelist still gates built-ins...
        assert "tool_a" in agent.tools.tool_names
        assert "tool_b" not in agent.tools.tool_names
        # ...but every MCP tool survives despite not being in enabled_tools.
        for name in mcp_names:
            assert name in agent.tools.tool_names

    async def test_disabled_tools_still_gates_mcp_at_build(
        self, factory: AgentFactory, store: InMemoryStore
    ) -> None:
        # `disabled_tools` remains a universal explicit off-switch even for
        # `mcp__` names (factory.py:421 gate).
        class StubMCPProvider:
            async def get_tools_for_agent(
                self, config: AgentConfig, agent_name: str | None = None
            ) -> list[Tool]:
                return [
                    StubTool("mcp__github__delete_repo", agent_name=agent_name),
                    StubTool("mcp__github__list_repos", agent_name=agent_name),
                ]

        factory.mcp_provider = StubMCPProvider()
        cfg = AgentConfig(
            name="mcp-blacklist",
            provider_config_id="test-provider",
            llm_model="stub-model",
            enabled_tools=["tool_a"],
            disabled_tools=["mcp__github__delete_repo"],
            mcp_source_ids=["github"],
        )
        await store.save(cfg)
        # See the matching comment in test_builtins_whitelist_does_not_strip_mcp_tools:
        # `mcp_source_ids` also drives `_build_source_index`, which — left
        # unpatched — runs the real `MCPSourceRepository` against the
        # `factory` fixture's AsyncMock `conn` and leaks an "AsyncMockMixin
        # never awaited" RuntimeWarning via an unrelated mock-shape TypeError.
        # Patch it to take the intended "deleted source" KeyError branch.
        mock_source_repo = AsyncMock()
        mock_source_repo.get = AsyncMock(side_effect=KeyError("source not found"))
        with patch(
            "the_one.db.repositories.MCPSourceRepository",
            return_value=mock_source_repo,
        ):
            agent = await factory.create("mcp-blacklist")
        assert "mcp__github__delete_repo" not in agent.tools.tool_names
        assert "mcp__github__list_repos" in agent.tools.tool_names


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


class TestProviderTypeMap:
    def test_openrouter_in_provider_type_map(self) -> None:
        # M19 F01 L02: the map lives in the registry now; the factory
        # consumes it from there.
        from the_one.agent.factory import PROVIDER_TYPE_MAP

        assert PROVIDER_TYPE_MAP.get("openrouter") == "openrouter"


class TestPlanProviderConstruction:
    """M19 F01 L02 (DD-3): the factory threads provider_config_id to the
    anthropic-plan constructor — the provider self-resolves its credential
    source; no static access token crosses the factory boundary."""

    def _plan_config(self) -> LLMProviderConfig:
        return LLMProviderConfig(
            id="plan-prov",
            name="Claude Plan",
            type="anthropic-plan",
            base_url="https://api.anthropic.com",
        )

    def _patches(self, get_provider_patch, provider_config: LLMProviderConfig):
        mock_repo = AsyncMock()
        mock_repo.get = AsyncMock(return_value=provider_config)
        mock_tool_repo = AsyncMock()
        mock_tool_repo.list = AsyncMock(return_value=[])
        return (
            patch("the_one.agent.factory.get_provider", get_provider_patch),
            patch("the_one.agent.factory.settings"),
            patch("the_one.db.connection.get_connection", new_callable=AsyncMock),
            patch("the_one.encryption.get_encryptor", return_value=AsyncMock()),
            patch("the_one.db.repositories.LLMProviderRepository", return_value=mock_repo),
            patch("the_one.db.repositories.ToolConfigRepository", return_value=mock_tool_repo),
        )

    async def _create(self, store: InMemoryStore, get_provider_patch, provider_config=None):
        cfg = AgentConfig(
            name="plan-agent",
            provider_config_id="plan-prov",
            llm_model="claude-sonnet-4-6",
        )
        await store.save(cfg)
        from contextlib import ExitStack

        patches = self._patches(get_provider_patch, provider_config or self._plan_config())
        with ExitStack() as stack:
            active = [stack.enter_context(p) for p in patches]
            mock_settings = active[1]
            mock_settings.agents_dir = Path("/tmp/test-agents")
            mock_settings.data_dir = Path("/tmp/test-data")
            mock_settings.ensure_dirs = lambda: None
            factory = AgentFactory(
                store=store, tool_providers=[StubToolProvider()], mcp_provider=None
            )
            return await factory.create("plan-agent")

    async def test_factory_passes_provider_config_id_no_static_token(
        self, store: InMemoryStore
    ) -> None:
        captured: dict[str, Any] = {}

        def _capturing_get_provider(name: str, **kwargs: Any) -> FakeLLM:
            captured["name"] = name
            captured["kwargs"] = kwargs
            return FakeLLM(responses=[])

        await self._create(store, _capturing_get_provider)
        assert captured["name"] == "anthropic-plan"
        assert captured["kwargs"]["provider_config_id"] == "plan-prov"
        assert "access_token" not in captured["kwargs"]

    async def test_factory_builds_real_plan_provider(self, store: InMemoryStore) -> None:
        """Unpatched get_provider: a working AnthropicPlanProvider comes out,
        keyed to the provider-config id (token resolution deferred to request
        time via the credential source)."""
        from the_one.llm import get_provider as real_get_provider
        from the_one.llm.anthropic_plan_provider import AnthropicPlanProvider

        agent = await self._create(store, real_get_provider)
        assert isinstance(agent.llm, AnthropicPlanProvider)
        assert agent.llm.provider_config_id == "plan-prov"
        assert agent.llm.model == "claude-sonnet-4-6"

    async def test_factory_non_plan_type_gets_no_provider_config_id(
        self, store: InMemoryStore
    ) -> None:
        captured: dict[str, Any] = {}

        def _capturing_get_provider(name: str, **kwargs: Any) -> FakeLLM:
            captured["kwargs"] = kwargs
            return FakeLLM(responses=[])

        await self._create(
            store,
            _capturing_get_provider,
            provider_config=_make_provider_config(provider_id="plan-prov", ptype="anthropic"),
        )
        assert "provider_config_id" not in captured["kwargs"]


# ---------------------------------------------------------------------------
# Connector carve-out / system-prompt / provider-wiring tests are deleted:
# Mission 23 Flight 1 (backend-removal leg, DD-4) removed the F4/F10
# connector baseline carve-out, the connector-aware system-prompt
# directive, and the ``connector_ids``/``connector_acls`` kwarg threading
# through ``BuiltinToolProvider.get_tools`` entirely — ``compose_system_
# prompt`` takes no connector kwargs, and every tool provider now gets
# the same plain 3-arg call. ``set_factory``/``get_factory`` (below) are
# unaffected and stay.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Module-level factory accessor (M10 F8 L4)
# ---------------------------------------------------------------------------
#
# Gateway listeners (Discord's on_message in F8 L4, Slack's event handler in
# F9, …) need access to the application AgentFactory at dispatch time but
# cannot receive it through plugin.connect's signature. The accessor pattern
# at the_one/agent/factory.py:set_factory / get_factory codifies the
# read/write contract; these tests pin round-trip behavior + the
# pre-startup-None case.


class TestFactoryAccessor:
    """Round-trip + reset semantics for set_factory / get_factory."""

    @pytest.fixture(autouse=True)
    def _reset_module_slot(self) -> Any:
        """Reset the module-level ``_factory`` slot around every test.

        Without this, a test that calls ``set_factory(factory)`` would
        leave the slot populated for subsequent tests, including the
        pre-startup-None pin below. The fixture restores the prior
        value so we play nicely with parallel tests if any survive
        between cases.
        """
        from the_one.agent import factory as factory_mod

        saved = factory_mod._factory
        factory_mod._factory = None
        try:
            yield
        finally:
            factory_mod._factory = saved

    def test_get_returns_none_before_set(self) -> None:
        from the_one.agent.factory import get_factory

        assert get_factory() is None

    def test_set_then_get_round_trip(self) -> None:
        from the_one.agent.factory import AgentFactory, get_factory, set_factory

        instance = AgentFactory()
        set_factory(instance)
        assert get_factory() is instance

    def test_set_none_clears_the_slot(self) -> None:
        from the_one.agent.factory import AgentFactory, get_factory, set_factory

        set_factory(AgentFactory())
        assert get_factory() is not None
        set_factory(None)
        assert get_factory() is None

    def test_set_overwrites_prior_value(self) -> None:
        from the_one.agent.factory import AgentFactory, get_factory, set_factory

        first = AgentFactory()
        second = AgentFactory()
        set_factory(first)
        set_factory(second)
        assert get_factory() is second


class TestNativeApiWiring:
    """The factory must enable native /api/chat ONLY for provider type
    "ollama" (real Ollama); "openai-compatible" stays on /v1
    (``native_api=False``). Both share the OllamaProvider class."""

    @pytest.mark.parametrize(
        ("ptype", "expected_native"),
        [("ollama", True), ("openai-compatible", False)],
    )
    async def test_native_api_flag_from_provider_type(
        self, store: InMemoryStore, ptype: str, expected_native: bool
    ) -> None:
        captured: dict[str, Any] = {}

        def _capturing_get_provider(name: str, **kwargs: Any) -> FakeLLM:
            captured["name"] = name
            captured["kwargs"] = kwargs
            return FakeLLM(responses=[])

        mock_repo = AsyncMock()
        mock_repo.get = AsyncMock(
            return_value=_make_provider_config(ptype=ptype, base_url="http://localhost:11434")
        )
        mock_tool_repo = AsyncMock()
        mock_tool_repo.list = AsyncMock(return_value=[])

        await store.save(
            AgentConfig(
                name="ollama-agent",
                provider_config_id="test-provider",
                llm_model="ministral-3:8b",
            )
        )

        with (
            patch("the_one.agent.factory.get_provider", _capturing_get_provider),
            patch("the_one.agent.factory.settings") as mock_settings,
            patch("the_one.db.connection.get_connection", new_callable=AsyncMock),
            patch("the_one.encryption.get_encryptor", return_value=AsyncMock()),
            patch("the_one.db.repositories.LLMProviderRepository", return_value=mock_repo),
            patch("the_one.db.repositories.ToolConfigRepository", return_value=mock_tool_repo),
        ):
            mock_settings.agents_dir = Path("/tmp/test-agents")
            mock_settings.data_dir = Path("/tmp/test-data")
            mock_settings.ensure_dirs = lambda: None
            factory = AgentFactory(store=store, tool_providers=[StubToolProvider()])
            await factory.create("ollama-agent")

        assert captured["name"] == "ollama"
        assert captured["kwargs"].get("native_api") is expected_native


class TestSendToolCarveOut:
    """DD-5 pin tests (Mission 23 Flight 3 Leg 2, mission-owner-amended
    baseline-visibility carve-out). AC-1..AC-5, ALL through the REAL
    factory seed path (``builtin_factory.create``) — never hand-built
    containers, per the leg's ``AgentFactory.create()`` requirement.
    """

    async def test_present_when_enabled_absent_when_disabled(
        self, builtin_factory: AgentFactory, store: InMemoryStore
    ) -> None:
        """AC-1: present (from the FIRST iteration, i.e. seeded at build
        time, not via search) when enabled for the agent; absent when
        disabled."""
        await store.save(
            AgentConfig(name="enabled-agent", provider_config_id="test-provider", llm_model="m")
        )
        await store.save(
            AgentConfig(
                name="disabled-agent",
                provider_config_id="test-provider",
                llm_model="m",
                disabled_tools=[SEND_TO_PLATFORM_CHANNEL_TOOL_NAME],
            )
        )

        enabled_agent = await builtin_factory.create("enabled-agent")
        assert SEND_TO_PLATFORM_CHANNEL_TOOL_NAME in enabled_agent._loaded_tool_names
        enabled_names = {s["name"] for s in enabled_agent._compute_visible_schemas()}
        assert SEND_TO_PLATFORM_CHANNEL_TOOL_NAME in enabled_names

        disabled_agent = await builtin_factory.create("disabled-agent")
        assert SEND_TO_PLATFORM_CHANNEL_TOOL_NAME not in disabled_agent._loaded_tool_names
        disabled_names = {s["name"] for s in disabled_agent._compute_visible_schemas()}
        assert SEND_TO_PLATFORM_CHANNEL_TOOL_NAME not in disabled_names

    async def test_baseline_otherwise_unchanged(
        self, builtin_factory: AgentFactory, store: InMemoryStore
    ) -> None:
        """AC-2: exact visible-set shape in both states — no other schema
        leaks in either way."""
        await store.save(
            AgentConfig(
                name="disabled-agent",
                provider_config_id="test-provider",
                llm_model="m",
                disabled_tools=[SEND_TO_PLATFORM_CHANNEL_TOOL_NAME],
            )
        )
        await store.save(
            AgentConfig(name="enabled-agent", provider_config_id="test-provider", llm_model="m")
        )

        disabled_agent = await builtin_factory.create("disabled-agent")
        assert disabled_agent._compute_visible_schemas() == [SEARCH_TOOLS_SCHEMA, CONTINUE_SCHEMA]

        enabled_agent = await builtin_factory.create("enabled-agent")
        schemas = enabled_agent._compute_visible_schemas()
        assert schemas[:2] == [SEARCH_TOOLS_SCHEMA, CONTINUE_SCHEMA]
        assert len(schemas) == 3
        assert schemas[2]["name"] == SEND_TO_PLATFORM_CHANNEL_TOOL_NAME

    async def test_no_search_needed_first_llm_call(
        self, builtin_factory: AgentFactory, store: InMemoryStore
    ) -> None:
        """AC-3 (live-shaped): the first LLM call's tools= array carries the
        send-tool schema WITHOUT any search_tools invocation."""
        await store.save(
            AgentConfig(name="enabled-agent", provider_config_id="test-provider", llm_model="m")
        )
        agent = await builtin_factory.create("enabled-agent")
        agent.llm.responses = [Message.assistant("done")]

        msgs = [m async for m in agent.step("hello")]

        assert len(agent.llm.calls) == 1  # a single, text-only turn
        first_call_tools = agent.llm.calls[0]["tools"]
        assert first_call_tools is not None
        assert SEND_TO_PLATFORM_CHANNEL_TOOL_NAME in {t["name"] for t in first_call_tools}
        assert not any(tc.name == "search_tools" for m in msgs for tc in (m.tool_calls or []))

    async def test_no_duplication_on_search_match(
        self, builtin_factory: AgentFactory, store: InMemoryStore
    ) -> None:
        """AC-4: a search_tools call whose results include the seeded tool
        must NOT duplicate its schema — _on_search_match's name-set dedup
        covers the seed because seed names are already in loaded_tool_names."""
        await store.save(
            AgentConfig(name="enabled-agent", provider_config_id="test-provider", llm_model="m")
        )
        agent = await builtin_factory.create("enabled-agent")
        assert len(agent._loaded_schemas) == 1  # just the seed, pre-search

        search_tool = agent.tools.get("search_tools")
        await search_tool.execute(query="")  # empty query returns every schema

        schema_names = [s["name"] for s in agent._loaded_schemas]
        assert schema_names.count(SEND_TO_PLATFORM_CHANNEL_TOOL_NAME) == 1
        # Length parity is the other half of "no duplicate entry": the name
        # set and the schema list must stay in lockstep.
        assert len(agent._loaded_tool_names) == len(agent._loaded_schemas)

    async def test_reset_survival_and_container_identity(
        self, builtin_factory: AgentFactory, store: InMemoryStore
    ) -> None:
        """AC-5: after Agent.reset(), the carve-out reappears when enabled
        and stays absent when disabled; the re-seed mutates the ORIGINAL
        container objects in place (the closure-capture invariant)."""
        await store.save(
            AgentConfig(name="enabled-agent", provider_config_id="test-provider", llm_model="m")
        )
        await store.save(
            AgentConfig(
                name="disabled-agent",
                provider_config_id="test-provider",
                llm_model="m",
                disabled_tools=[SEND_TO_PLATFORM_CHANNEL_TOOL_NAME],
            )
        )

        enabled_agent = await builtin_factory.create("enabled-agent")
        schemas_obj = enabled_agent._loaded_schemas
        names_obj = enabled_agent._loaded_tool_names
        enabled_agent.reset()
        assert enabled_agent._loaded_schemas is schemas_obj  # object identity survives
        assert enabled_agent._loaded_tool_names is names_obj
        assert SEND_TO_PLATFORM_CHANNEL_TOOL_NAME in {
            s["name"] for s in enabled_agent._compute_visible_schemas()
        }

        disabled_agent = await builtin_factory.create("disabled-agent")
        disabled_agent.reset()
        assert SEND_TO_PLATFORM_CHANNEL_TOOL_NAME not in {
            s["name"] for s in disabled_agent._compute_visible_schemas()
        }
