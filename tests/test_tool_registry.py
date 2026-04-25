"""Tests for ToolRegistry and Tool.to_schema()."""

from __future__ import annotations

import pytest
from conftest import StubTool

from the_one.tools.base import ToolRegistry


class TestToolToSchema:
    """Test Tool.to_schema() output format."""

    def test_to_schema_has_required_keys(self) -> None:
        tool = StubTool("my_tool", description="Does things")
        schema = tool.to_schema()
        assert set(schema.keys()) == {"name", "description", "parameters"}

    def test_to_schema_values_match_attributes(self) -> None:
        tool = StubTool("my_tool", description="Does things")
        schema = tool.to_schema()
        assert schema["name"] == "my_tool"
        assert schema["description"] == "Does things"
        assert schema["parameters"] == tool.parameters


class TestToolRegistry:
    """Test ToolRegistry register/get/all_schemas/tool_names."""

    def test_register_and_get(self) -> None:
        registry = ToolRegistry()
        tool = StubTool("alpha")
        registry.register(tool)
        assert registry.get("alpha") is tool

    def test_get_unknown_raises_key_error(self) -> None:
        registry = ToolRegistry()
        with pytest.raises(KeyError, match="Unknown tool: nope"):
            registry.get("nope")

    def test_all_schemas_returns_list_of_dicts(self) -> None:
        registry = ToolRegistry()
        registry.register(StubTool("a"))
        registry.register(StubTool("b"))
        schemas = registry.all_schemas()
        assert isinstance(schemas, list)
        assert len(schemas) == 2
        for s in schemas:
            assert isinstance(s, dict)
            assert "name" in s

    def test_tool_names_returns_list_of_strings(self) -> None:
        registry = ToolRegistry()
        registry.register(StubTool("x"))
        registry.register(StubTool("y"))
        names = registry.tool_names
        assert isinstance(names, list)
        assert set(names) == {"x", "y"}

    def test_tool_names_empty_registry(self) -> None:
        registry = ToolRegistry()
        assert registry.tool_names == []

    def test_duplicate_registration_overwrites(self) -> None:
        registry = ToolRegistry()
        tool1 = StubTool("dup", description="first")
        tool2 = StubTool("dup", description="second")
        registry.register(tool1)
        registry.register(tool2)
        assert registry.get("dup") is tool2
        assert len(registry.tool_names) == 1
