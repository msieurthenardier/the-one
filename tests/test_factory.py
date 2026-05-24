"""Tests for AgentFactory."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from conftest import FakeLLM, StubTool

from the_one.agent.config import (
    _CONNECTOR_AUTO_RELAY_DIRECTIVE,
    _CONNECTOR_AUTO_RELAY_OFF_DIRECTIVE,
    BASE_PROMPT,
    AgentConfig,
)
from the_one.agent.factory import AgentFactory
from the_one.db.models import ConnectorAccount, LLMProviderConfig, ToolConfig
from the_one.tools.base import Tool
from the_one.tools.builtins import BuiltinToolProvider

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

    # M10 F8 L11 HAT Fix #5: factory now does a per-account lookup to
    # resolve ``auto_relay`` for the system-prompt directive. Mock the
    # repository to return a permissive (auto_relay=True default) account
    # for any account_id the caller's AgentConfig references.
    mock_acc_repo = AsyncMock()
    mock_acc_repo.get = AsyncMock(
        side_effect=lambda aid: ConnectorAccount(id=aid, name=aid, type="stub")
    )

    with (
        patch("the_one.agent.factory.get_provider", _fake_get_provider),
        patch("the_one.agent.factory.settings") as mock_settings,
        patch("the_one.db.connection.get_connection", new_callable=AsyncMock),
        patch("the_one.encryption.get_encryptor", return_value=AsyncMock()),
        patch("the_one.db.repositories.LLMProviderRepository", return_value=mock_repo),
        patch("the_one.db.repositories.ToolConfigRepository", return_value=mock_tool_repo),
        patch(
            "the_one.db.repositories.ConnectorAccountRepository",
            return_value=mock_acc_repo,
        ),
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
        # search_tools is always in the registry (registered before the
        # built-in loop, bypassing the enabled/disabled filter). The
        # enabled_tools whitelist still gates the built-in catalog; only
        # tool_a passes.
        assert "search_tools" in agent.tools.tool_names
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


class TestProviderTypeMap:
    def test_openrouter_in_provider_type_map(self) -> None:
        from the_one.agent.factory import _PROVIDER_TYPE_MAP

        assert _PROVIDER_TYPE_MAP.get("openrouter") == "openrouter"


# ---------------------------------------------------------------------------
# F4 (M10) L3: connector carve-out + system-prompt + provider wiring
# ---------------------------------------------------------------------------


@pytest.fixture
def factory_with_builtin_tool_configs(store: InMemoryStore):
    """Yields a callable that builds a factory using BuiltinToolProvider.

    The callable accepts ``tool_configs`` (a list[ToolConfig] seeded into
    ``mock_tool_repo.list()``) and returns a context manager. Patches are
    activated on ``__enter__`` and torn down on ``__exit__`` — patches
    stay live for the body of the ``with`` block (and therefore during
    ``factory.create()``), matching the patch-scope correctness of the
    existing ``factory`` fixture at tests/test_factory.py:115-126.
    """
    mock_repo = AsyncMock()
    mock_repo.get = AsyncMock(return_value=_make_provider_config())

    def _make_with_tool_configs(
        tool_configs: list[ToolConfig] | None = None,
        extra_tool_providers: list | None = None,
        connector_accounts: dict[str, ConnectorAccount] | None = None,
    ):
        class _Ctx:
            def __enter__(self):
                mock_tool_repo = AsyncMock()
                mock_tool_repo.list = AsyncMock(return_value=tool_configs or [])

                # M10 F8 L11 HAT Fix #5: per-account lookup for auto_relay
                # resolution. ``connector_accounts`` is a {account_id:
                # ConnectorAccount} mapping; missing IDs synthesize a
                # default-on (no opt-out) ConnectorAccount so the
                # caller's existing tests stay green without rework.
                accounts_map = dict(connector_accounts or {})
                mock_acc_repo = AsyncMock()

                async def _acc_get(aid: str) -> ConnectorAccount:
                    if aid in accounts_map:
                        return accounts_map[aid]
                    return ConnectorAccount(id=aid, name=aid, type="stub")

                mock_acc_repo.get = AsyncMock(side_effect=_acc_get)

                self._patches = [
                    patch("the_one.agent.factory.get_provider", _fake_get_provider),
                    patch("the_one.agent.factory.settings"),
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
                    patch(
                        "the_one.db.repositories.ConnectorAccountRepository",
                        return_value=mock_acc_repo,
                    ),
                ]
                self._active = [p.start() for p in self._patches]
                # Index 1 corresponds to the settings patch.
                self._active[1].agents_dir = Path("/tmp/test-agents")
                self._active[1].data_dir = Path("/tmp/test-data")
                self._active[1].ensure_dirs = lambda: None
                providers = [BuiltinToolProvider()]
                if extra_tool_providers:
                    providers.extend(extra_tool_providers)
                return AgentFactory(
                    store=store,
                    tool_providers=providers,
                    mcp_provider=None,
                )

            def __exit__(self, *args):
                for p in self._patches:
                    p.stop()

        return _Ctx()

    yield _make_with_tool_configs


class TestConnectorBaselineCarveOut:
    """F10 baseline carve-out: send_to_platform_channel is pre-loaded into
    the model-visible set when the agent is connector-attached AND the
    operator + per-agent gates both pass."""

    async def test_carveout_loads_send_tool_when_attached_and_enabled(
        self,
        factory_with_builtin_tool_configs,
        store: InMemoryStore,
    ) -> None:
        cfg = AgentConfig(
            name="connector-agent",
            provider_config_id="test-provider",
            llm_model="stub-model",
            connector_account_ids=["acc-1"],
        )
        await store.save(cfg)
        # No ToolConfig row for send_to_platform_channel → not in
        # disabled_names → operator-enabled by default.
        with factory_with_builtin_tool_configs(tool_configs=[]) as factory:
            agent = await factory.create("connector-agent")
        assert "send_to_platform_channel" in agent._loaded_tool_names
        schema_names = [s["name"] for s in agent._loaded_schemas]
        assert schema_names == ["send_to_platform_channel"]

    async def test_no_carveout_when_no_connector_accounts(
        self,
        factory_with_builtin_tool_configs,
        store: InMemoryStore,
    ) -> None:
        cfg = AgentConfig(
            name="non-connector-agent",
            provider_config_id="test-provider",
            llm_model="stub-model",
            connector_account_ids=[],
        )
        await store.save(cfg)
        with factory_with_builtin_tool_configs(tool_configs=[]) as factory:
            agent = await factory.create("non-connector-agent")
        assert agent._loaded_schemas == []
        assert agent._loaded_tool_names == set()

    async def test_no_carveout_when_tool_operator_disabled(
        self,
        factory_with_builtin_tool_configs,
        store: InMemoryStore,
    ) -> None:
        cfg = AgentConfig(
            name="connector-agent",
            provider_config_id="test-provider",
            llm_model="stub-model",
            connector_account_ids=["acc-1"],
        )
        await store.save(cfg)
        tool_configs = [
            ToolConfig(name="send_to_platform_channel", config={}, enabled=False),
        ]
        with factory_with_builtin_tool_configs(tool_configs=tool_configs) as factory:
            agent = await factory.create("connector-agent")
        assert agent._loaded_schemas == []
        assert "send_to_platform_channel" not in agent._loaded_tool_names

    async def test_no_carveout_when_tool_per_agent_disabled(
        self,
        factory_with_builtin_tool_configs,
        store: InMemoryStore,
    ) -> None:
        cfg = AgentConfig(
            name="connector-agent",
            provider_config_id="test-provider",
            llm_model="stub-model",
            connector_account_ids=["acc-1"],
            disabled_tools=["send_to_platform_channel"],
        )
        await store.save(cfg)
        with factory_with_builtin_tool_configs(tool_configs=[]) as factory:
            agent = await factory.create("connector-agent")
        assert agent._loaded_schemas == []
        assert "send_to_platform_channel" not in agent._loaded_tool_names


class TestConnectorSystemPrompt:
    """The factory composes a connector-aware system prompt: a directive is
    inserted between BASE_PROMPT and the persona when the agent is
    connector-attached."""

    async def test_non_connector_uses_base_prompt(
        self,
        factory_with_builtin_tool_configs,
        store: InMemoryStore,
    ) -> None:
        cfg = AgentConfig(
            name="non-connector-agent",
            provider_config_id="test-provider",
            llm_model="stub-model",
            connector_account_ids=[],
        )
        await store.save(cfg)
        with factory_with_builtin_tool_configs(tool_configs=[]) as factory:
            agent = await factory.create("non-connector-agent")
        assert agent.system_prompt == BASE_PROMPT

    async def test_connector_attached_tool_enabled_default_auto_relay_includes_auto_relay_directive(
        self,
        factory_with_builtin_tool_configs,
        store: InMemoryStore,
    ) -> None:
        """M10 F8 L11 HAT Fix #5: default-on auto-relay lands the
        auto-relay (ON) directive."""
        cfg = AgentConfig(
            name="connector-agent",
            provider_config_id="test-provider",
            llm_model="stub-model",
            connector_account_ids=["acc-1"],
        )
        await store.save(cfg)
        with factory_with_builtin_tool_configs(tool_configs=[]) as factory:
            agent = await factory.create("connector-agent")
        assert _CONNECTOR_AUTO_RELAY_DIRECTIVE in agent.system_prompt
        assert _CONNECTOR_AUTO_RELAY_OFF_DIRECTIVE not in agent.system_prompt

    async def test_connector_attached_auto_relay_opt_out_includes_off_directive(
        self,
        factory_with_builtin_tool_configs,
        store: InMemoryStore,
    ) -> None:
        """Opt-out (``auto_relay_platform_replies=False`` on the attached
        account) lands the OFF directive — round-8 simplification: the
        OFF directive's "if available" hedge covers both tool-enabled
        and tool-disabled cases, so no separate dispatch is needed."""
        cfg = AgentConfig(
            name="connector-agent",
            provider_config_id="test-provider",
            llm_model="stub-model",
            connector_account_ids=["acc-1"],
        )
        await store.save(cfg)
        opt_out_account = ConnectorAccount(
            id="acc-1",
            name="acc-1",
            type="stub",
            config={"auto_relay_platform_replies": False},
        )
        with factory_with_builtin_tool_configs(
            tool_configs=[],
            connector_accounts={"acc-1": opt_out_account},
        ) as factory:
            agent = await factory.create("connector-agent")
        assert _CONNECTOR_AUTO_RELAY_OFF_DIRECTIVE in agent.system_prompt
        assert _CONNECTOR_AUTO_RELAY_DIRECTIVE not in agent.system_prompt

    async def test_connector_attached_multi_account_any_opt_out_wins(
        self,
        factory_with_builtin_tool_configs,
        store: InMemoryStore,
    ) -> None:
        """M10 F8 L11 HAT Fix #5: multi-account agents where ANY attached
        account has auto_relay=False ⇒ treat as opt-out (most-restrictive
        wins). The remaining accounts' default-on stance does not
        re-enable the auto-relay directive — the OFF directive lands."""
        cfg = AgentConfig(
            name="connector-agent",
            provider_config_id="test-provider",
            llm_model="stub-model",
            connector_account_ids=["acc-1", "acc-2"],
        )
        await store.save(cfg)
        acc1 = ConnectorAccount(id="acc-1", name="acc-1", type="stub")
        acc2_opt_out = ConnectorAccount(
            id="acc-2",
            name="acc-2",
            type="stub",
            config={"auto_relay_platform_replies": False},
        )
        with factory_with_builtin_tool_configs(
            tool_configs=[],
            connector_accounts={"acc-1": acc1, "acc-2": acc2_opt_out},
        ) as factory:
            agent = await factory.create("connector-agent")
        assert _CONNECTOR_AUTO_RELAY_OFF_DIRECTIVE in agent.system_prompt
        assert _CONNECTOR_AUTO_RELAY_DIRECTIVE not in agent.system_prompt

    async def test_connector_attached_tool_disabled_uses_on_directive_when_relay_on(
        self,
        factory_with_builtin_tool_configs,
        store: InMemoryStore,
    ) -> None:
        """Round-8: when the send tool is disabled but auto_relay is
        ON (default), the ON directive still lands. The dedicated
        ``_CONNECTOR_TOOL_DISABLED_DIRECTIVE`` was removed in round-8
        because the LLM cannot call a disabled tool regardless of the
        prompt directive — the OFF directive's "if available" hedge
        covers the explicit-opt-out case where the operator both
        disables the tool AND turns off auto-relay."""
        cfg = AgentConfig(
            name="connector-agent",
            provider_config_id="test-provider",
            llm_model="stub-model",
            connector_account_ids=["acc-1"],
        )
        await store.save(cfg)
        tool_configs = [
            ToolConfig(name="send_to_platform_channel", config={}, enabled=False),
        ]
        with factory_with_builtin_tool_configs(tool_configs=tool_configs) as factory:
            agent = await factory.create("connector-agent")
        # Default auto_relay=True (account has no opt-out) ⇒ ON directive.
        assert _CONNECTOR_AUTO_RELAY_DIRECTIVE in agent.system_prompt
        assert _CONNECTOR_AUTO_RELAY_OFF_DIRECTIVE not in agent.system_prompt


# M11 F5 L6 HAT round-8: ``TestConnectorOperatorDirectiveCollection``
# was REMOVED here (3 tests). The M11 F2 L3 per-account
# ``system_prompt_directive`` collection block in
# ``AgentFactory.create`` no longer exists (criterion #14 reverted);
# nothing to exercise.


class TestFactoryToolProviderWiring:
    """The factory passes connector_account_ids to BuiltinToolProvider only;
    other providers in the list (test stubs, future provider types) get the
    unwidened 3-arg call."""

    async def test_builtin_provider_receives_connector_account_ids(
        self,
        factory_with_builtin_tool_configs,
        store: InMemoryStore,
    ) -> None:
        captured_builtin: dict[str, Any] = {}
        captured_stub: dict[str, Any] = {}

        # Wrap BuiltinToolProvider.get_tools to capture the kwargs without
        # losing the real behavior (we still need the tool registry populated).
        original_get_tools = BuiltinToolProvider.get_tools

        def _wrapped_builtin_get_tools(self, *args, **kwargs):
            captured_builtin["args"] = args
            captured_builtin["kwargs"] = kwargs
            return original_get_tools(self, *args, **kwargs)

        # Build a stub provider that captures its call shape too.
        class CapturingStubProvider:
            @property
            def name(self) -> str:
                return "capturing-stub"

            def get_tools(
                self,
                tool_configs: dict[str, dict] | None = None,
                agent_overrides: dict[str, dict] | None = None,
                agent_name: str | None = None,
            ) -> list[Tool]:
                captured_stub["tool_configs"] = tool_configs
                captured_stub["agent_overrides"] = agent_overrides
                captured_stub["agent_name"] = agent_name
                return []

        cfg = AgentConfig(
            name="connector-agent",
            provider_config_id="test-provider",
            llm_model="stub-model",
            connector_account_ids=["acc-1"],
        )
        await store.save(cfg)

        with patch.object(
            BuiltinToolProvider, "get_tools", _wrapped_builtin_get_tools
        ):
            ctx = factory_with_builtin_tool_configs(
                tool_configs=[],
                extra_tool_providers=[CapturingStubProvider()],
            )
            with ctx as factory:
                await factory.create("connector-agent")

        # BuiltinToolProvider receives connector_account_ids kwarg.
        assert captured_builtin["kwargs"].get("connector_account_ids") == ["acc-1"]
        # Stub provider does NOT receive the kwarg (no isinstance branch hit).
        assert captured_stub["agent_name"] == "connector-agent"


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
