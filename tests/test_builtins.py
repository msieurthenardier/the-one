"""Tests for BuiltinToolProvider."""

from __future__ import annotations

from the_one.tools.builtins import BuiltinToolProvider
from the_one.tools.provider import ToolProvider


class TestBuiltinToolProvider:
    def test_name_is_builtin(self) -> None:
        assert BuiltinToolProvider().name == "builtin"

    def test_get_tools_returns_14_tools(self) -> None:
        tools = BuiltinToolProvider().get_tools()
        assert len(tools) == 14

    def test_protocol_compliance(self) -> None:
        assert isinstance(BuiltinToolProvider(), ToolProvider)

    def test_all_tools_have_required_attributes(self) -> None:
        tools = BuiltinToolProvider().get_tools()
        for tool in tools:
            assert hasattr(tool, "name"), "Tool missing 'name'"
            assert hasattr(tool, "description"), f"Tool {tool.name} missing 'description'"
            assert hasattr(tool, "parameters"), f"Tool {tool.name} missing 'parameters'"
            assert isinstance(tool.name, str)
            assert isinstance(tool.description, str)
            assert isinstance(tool.parameters, dict)
