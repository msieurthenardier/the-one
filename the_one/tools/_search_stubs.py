"""Canned-data stub for the unified search_tools.

Test-only. Used by ``tests/test_agent_visibility_filter.py`` to exercise the
shared-loaded-set mutation contract without depending on a real
ToolRegistry or source_index. Production wiring uses ``SearchTools`` from
``_search_tools.py`` instead.

Satisfies the strict baseline visible-tools contract: only ``search_tools``
and ``continue`` are visible to the LLM at session start. When called, the
stub mutates the shared ``_loaded_schemas`` / ``_loaded_tool_names``
containers via the on_match callback so the persistence-across-turns test
can exercise the mutation.

Imports ``SEARCH_TOOLS_SCHEMA`` from ``agent.core`` (single source of
truth); the existing agent → tools import direction is preserved.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from the_one.agent.core import SEARCH_TOOLS_SCHEMA
from the_one.tools.base import Tool

# Canned schemas. Names use _stub_canned_* prefix so they cannot collide
# with any real tool name in the production catalog.
_CANNED_TOOL_SCHEMA_A: dict[str, Any] = {
    "name": "_stub_canned_tool_a",
    "description": "Test-only canned tool A — not a real tool.",
    "parameters": {"type": "object", "properties": {}, "required": []},
}

_CANNED_TOOL_SCHEMA_B: dict[str, Any] = {
    "name": "_stub_canned_tool_b",
    "description": "Test-only canned tool B — not a real tool.",
    "parameters": {"type": "object", "properties": {}, "required": []},
}


class SearchToolsStub(Tool):
    """Stub for search_tools that returns canned data.

    Class-attribute ``name`` (not instance attribute) is required by
    ``ToolRegistry.register`` which keys on ``tool.name``.
    """

    name = "search_tools"
    description = SEARCH_TOOLS_SCHEMA["description"]
    parameters = SEARCH_TOOLS_SCHEMA["parameters"]

    def __init__(
        self,
        on_match: Callable[[list[dict[str, Any]]], None],
        agent_name: str | None = None,
    ) -> None:
        super().__init__(agent_name=agent_name)
        self._on_match = on_match

    async def execute(self, query: str = "") -> str:  # type: ignore[override]
        canned = [_CANNED_TOOL_SCHEMA_A, _CANNED_TOOL_SCHEMA_B]
        self._on_match(canned)
        return (
            f"Found {len(canned)} tools matching {query!r}: "
            f"{_CANNED_TOOL_SCHEMA_A['name']}, {_CANNED_TOOL_SCHEMA_B['name']} "
            f"(stub data)."
        )
