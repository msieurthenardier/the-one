"""Tests for BuiltinToolProvider."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

from the_one.tools.base import Tool
from the_one.tools.builtins import BuiltinToolProvider
from the_one.tools.filesystem import FilesystemConfig
from the_one.tools.provider import ToolProvider


class TestBuiltinToolProvider:
    def test_name_is_builtin(self) -> None:
        assert BuiltinToolProvider().name == "builtin"

    def test_get_tools_returns_tools(self) -> None:
        # Existing zero-arg form — introspection path. Must keep working
        # post-L3 via signature defaults.
        tools = BuiltinToolProvider().get_tools()
        assert len(tools) > 0

    def test_protocol_compliance(self) -> None:
        # `runtime_checkable` Protocol checks method NAMES only, so widening
        # `get_tools` is non-breaking for this isinstance check.
        assert isinstance(BuiltinToolProvider(), ToolProvider)

    def test_all_tools_have_required_attributes(self) -> None:
        # Existing zero-arg form — introspection path.
        tools = BuiltinToolProvider().get_tools()
        for tool in tools:
            assert hasattr(tool, "name"), "Tool missing 'name'"
            assert hasattr(tool, "description"), f"Tool {tool.name} missing 'description'"
            assert hasattr(tool, "parameters"), f"Tool {tool.name} missing 'parameters'"
            assert isinstance(tool.name, str)
            assert isinstance(tool.description, str)
            assert isinstance(tool.parameters, dict)


# ---------------------------------------------------------------------------
# L3 additions — explicit-None vs factory-path; per-agent isolation; unknown
# tool name in agent_overrides silently ignored.
# ---------------------------------------------------------------------------


class TestBuiltinToolProviderL3:
    def test_explicit_none_args_match_zero_arg_form(self) -> None:
        provider = BuiltinToolProvider()
        zero_arg = provider.get_tools()
        explicit_none = provider.get_tools(tool_configs=None, agent_overrides=None)
        # Same shape: 24 tools (20 base + the four M11 F7 L10
        # channel-context tools), same names, in the same order.
        assert [t.name for t in zero_arg] == [t.name for t in explicit_none]
        assert len(zero_arg) == 24

    def test_empty_dicts_go_through_factory_path(self) -> None:
        # Both args are non-None empty dicts → factory path. Each tool's
        # Config resolves to the empty default; result still has 24 tools.
        provider = BuiltinToolProvider()
        tools = provider.get_tools({}, {})
        assert len(tools) == 24
        names = {t.name for t in tools}
        assert names == {
            "shell",
            "read_file",
            "write_file",
            "edit_file",
            "delete_file",
            "move_file",
            "mkdir",
            "glob",
            "grep",
            "list_dir",
            "python_exec",
            "shell_session_start",
            "shell_session_send",
            "shell_session_close",
            "shell_session_list",
            "http_request",
            "fetch_url",
            "download_file",
            "web_search",
            "send_to_platform_channel",
            "fetch_channel_history",
            "fetch_thread_history",
            "fetch_dm_history",
            "list_visible_channels",
        }

    def test_per_agent_isolation_factory_path(self) -> None:
        provider = BuiltinToolProvider()
        tools_a = provider.get_tools({}, {})
        tools_b = provider.get_tools({}, {})
        # Aligned by index — `_TOOL_CLASSES` is dict-ordered so both calls
        # produce instances in the same order.
        for ta, tb in zip(tools_a, tools_b):
            assert ta is not tb, f"singleton leaked for {ta.name}"

    def test_per_agent_isolation_introspection_path(self) -> None:
        # Even the both-None path returns fresh instances per call.
        provider = BuiltinToolProvider()
        tools_a = provider.get_tools()
        tools_b = provider.get_tools()
        for ta, tb in zip(tools_a, tools_b):
            assert ta is not tb, f"singleton leaked for {ta.name}"

    def test_unknown_tool_name_in_overrides_silently_ignored(self) -> None:
        # An unknown tool name in agent_overrides must not raise; the 24
        # known tools are still instantiated. Mirrors the v7
        # enabled_tools/disabled_tools strip semantic.
        provider = BuiltinToolProvider()
        tools = provider.get_tools(None, {"nonexistent_tool": {"foo": "bar"}})
        assert len(tools) == 24
        names = {t.name for t in tools}
        assert "nonexistent_tool" not in names


# ---------------------------------------------------------------------------
# L1b additions — cross_configs dispatch, agent_name plumbing, intra-call
# sharing, inter-call freshness, Requires-declaring fixture tool.
# ---------------------------------------------------------------------------


class _ExecutionStub(BaseModel):
    """Stand-in Config for a fixture tool — F4 L2 will introduce the real
    ExecutionConfig; here we only need a non-empty BaseModel."""

    cap: int = 100


class _FixtureRequiresFsTool(Tool):
    """Fixture tool declaring `Requires = (FilesystemConfig,)` so the L1b
    cross_configs dispatch path can be asserted without coupling to any of
    the 17 real tools' Config wiring."""

    name = "fixture_requires_fs"
    description = "Fixture tool that depends on FilesystemConfig."
    parameters: dict[str, Any] = {"type": "object", "properties": {}, "required": []}
    Config = _ExecutionStub
    Requires = (FilesystemConfig,)

    async def execute(self, **kwargs: Any) -> str:
        return "ok"


class TestBuiltinToolProviderL1b:
    def test_factory_path_populates_cross_configs_for_filesystem(self) -> None:
        # The 9 filesystem tools all carry `Config = FilesystemConfig`; on
        # the factory path the provider must resolve FilesystemConfig once
        # and stash it in `cross_configs` keyed by the Config type.
        tools = BuiltinToolProvider().get_tools({}, {})
        for tool in tools:
            assert FilesystemConfig in tool._cross_configs, (
                f"tool {tool.name} missing FilesystemConfig in cross_configs"
            )
            assert isinstance(tool._cross_configs[FilesystemConfig], FilesystemConfig)

    def test_introspection_path_has_empty_cross_configs(self) -> None:
        # Zero-arg / both-None calls must not invoke the resolver; tools come
        # back with the `Tool.__init__` defaults.
        tools = BuiltinToolProvider().get_tools()
        for tool in tools:
            assert tool._cross_configs == {}
            assert tool._agent_name is None

    def test_agent_name_threads_to_every_tool(self) -> None:
        tools = BuiltinToolProvider().get_tools({}, {}, agent_name="alpha")
        for tool in tools:
            assert tool._agent_name == "alpha"

    def test_cross_configs_shared_by_reference_within_one_call(self) -> None:
        # Shared dict means a frozen Config protects every tool from a peer
        # mutating its view (FilesystemConfig is frozen as of L1b).
        tools = BuiltinToolProvider().get_tools({}, {})
        first = tools[0]._cross_configs
        for tool in tools[1:]:
            assert tool._cross_configs is first

    def test_cross_configs_fresh_per_call(self) -> None:
        # Each `get_tools` call builds its own cross_configs dict — no
        # cross-call leakage even though the dict is shared within a call.
        tools_a = BuiltinToolProvider().get_tools({}, {})
        tools_b = BuiltinToolProvider().get_tools({}, {})
        assert tools_a[0]._cross_configs is not tools_b[0]._cross_configs

    def test_requires_fixture_tool_receives_filesystem_config(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Inject the fixture tool into _TOOL_CLASSES; the provider must
        # resolve the FilesystemConfig (declared via `Requires`) and pass
        # the dict to the fixture tool so it sees a FilesystemConfig
        # instance keyed by the Config class.
        from the_one.tools import builtins as builtins_mod

        patched = dict(builtins_mod._TOOL_CLASSES)
        patched["fixture_requires_fs"] = _FixtureRequiresFsTool
        monkeypatch.setattr(builtins_mod, "_TOOL_CLASSES", patched)

        tools = BuiltinToolProvider().get_tools({}, {}, agent_name="alpha")
        fixture = next(t for t in tools if t.name == "fixture_requires_fs")
        assert FilesystemConfig in fixture._cross_configs
        assert isinstance(fixture._cross_configs[FilesystemConfig], FilesystemConfig)
        assert fixture._agent_name == "alpha"

    def test_cross_configs_skips_empty_config(self) -> None:
        # Tools with the inherited `_EmptyConfig` default must NOT contribute
        # an entry to cross_configs — the per-call view collapses empties so
        # cross-Config consumers don't see noise. Post-F5-L6 ALL of the 19
        # built-in tools have a non-empty Config (`WebSearchTool` migrated
        # from `_EmptyConfig` to `WebConfig` in F5 L6); the assertion still
        # holds defensively against future tools that may inherit the empty
        # default.
        from the_one.tools.resolver import _EmptyConfig

        tools = BuiltinToolProvider().get_tools({}, {})
        for tool in tools:
            assert _EmptyConfig not in tool._cross_configs

    def test_cross_configs_contains_expected_entries(self) -> None:
        """Lock the dispatch shape: the per-call ``cross_configs`` view
        contains SIX entries — five Pydantic-keyed Configs
        (``{FilesystemConfig, ExecutionConfig, PythonExecConfig, WebConfig,
        WebSearchConfig}``) plus one Protocol-keyed service (``SearchBackend``).

        ``_EmptyConfig`` is skipped; ``PythonExecConfig`` (a subclass of
        ``ExecutionConfig``) is a DISTINCT key from its parent (the
        resolver dispatch layer treats them as independent Config types);
        ``WebConfig`` entered the set with F5 L2 (``HttpRequestTool``
        migration); ``SearchBackend`` enters with F5 L6 (``WebSearchTool``
        migration). M16 F08 L02 splits ``web_search`` off ``WebConfig`` onto
        its own ``WebSearchConfig`` (engine selector + per-engine fields), so
        ``WebSearchConfig`` joins the set as the sixth entry. The Protocol-keyed
        entry coexists with the Pydantic-keyed entries thanks to F5 L6's
        ``cross_configs`` type widening from ``dict[type[BaseModel], BaseModel]``
        to ``dict[type, object]``.

        Guards against future drift if a new Config / service sneaks in or
        one of these gets removed."""
        from the_one.tools._search_backends import SearchBackend
        from the_one.tools._web_config import WebConfig
        from the_one.tools._web_search_config import WebSearchConfig
        from the_one.tools.execution import ExecutionConfig, PythonExecConfig

        tools = BuiltinToolProvider().get_tools({}, {})
        # All tools share one cross_configs dict by reference; sample tool[0].
        cross_configs = tools[0]._cross_configs
        expected_keys = {
            FilesystemConfig,
            ExecutionConfig,
            PythonExecConfig,
            WebConfig,
            WebSearchConfig,
            SearchBackend,
        }
        assert expected_keys <= set(cross_configs.keys())
        # Ensure no unexpected drift either — the post-M16-F08-L02 view is
        # exactly these six entries.
        assert set(cross_configs.keys()) == expected_keys
