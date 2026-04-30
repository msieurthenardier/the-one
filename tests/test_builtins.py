"""Tests for BuiltinToolProvider."""

from __future__ import annotations

from the_one.tools.builtins import BuiltinToolProvider
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
        # Same shape: 13 tools, same names, in the same order.
        assert [t.name for t in zero_arg] == [t.name for t in explicit_none]
        assert len(zero_arg) == 13

    def test_empty_dicts_go_through_factory_path(self) -> None:
        # Both args are non-None empty dicts → factory path. Each tool's
        # Config resolves to the empty default; result still has 13 tools.
        provider = BuiltinToolProvider()
        tools = provider.get_tools({}, {})
        assert len(tools) == 13
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
            "http_request",
            "web_search",
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
        # An unknown tool name in agent_overrides must not raise; the 13
        # known tools are still instantiated. Mirrors the v7
        # enabled_tools/disabled_tools strip semantic.
        provider = BuiltinToolProvider()
        tools = provider.get_tools(None, {"nonexistent_tool": {"foo": "bar"}})
        assert len(tools) == 13
        names = {t.name for t in tools}
        assert "nonexistent_tool" not in names
