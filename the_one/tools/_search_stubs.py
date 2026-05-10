"""F10 L1: CANNED-DATA stub tools for search_tools and search_mcps.

POST-L2 STATUS: SearchToolsStub is now test-only (used by L1's visibility-
filter contract tests in tests/test_agent_visibility_filter.py). Production
wiring uses SearchTools from _search_tools.py instead.

POST-L3 STATUS: SearchMcpsStub is now also test-only. Production wiring
uses SearchMcps from _search_mcps.py. SearchMcpsStub is retained here for
use by L1's visibility-filter contract tests in
tests/test_agent_visibility_filter.py (same pattern as SearchToolsStub
post-L2).

These stubs satisfy the F10 §2 strict 2-tool baseline: only search_tools,
search_mcps, and continue are visible to the LLM at session start. When
called, they mutate the shared _loaded_schemas / _loaded_tool_names
containers via the on_match callback so the persistence-across-turns test
can exercise the mutation. Real search logic landed at L2 (search_tools)
and L3 (search_mcps).

Import direction: this module imports SEARCH_TOOLS_SCHEMA and
SEARCH_MCPS_SCHEMA from agent.core (single source of truth). The existing
agent → tools import direction is preserved; no circular import.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from the_one.agent.core import SEARCH_MCPS_SCHEMA, SEARCH_TOOLS_SCHEMA
from the_one.tools.base import Tool

# ---------------------------------------------------------------------------
# Canned schemas. Names use _stub_canned_* prefix so they cannot collide
# with any real tool name in the production catalog. Used by the stub
# execute() methods to populate _loaded_schemas via the on_match callback.
# ---------------------------------------------------------------------------

_CANNED_TOOL_SCHEMA_A: dict[str, Any] = {
    "name": "_stub_canned_tool_a",
    "description": "L1 stub canned tool A — not a real tool. Replaced by L2's real search_tools.",
    "parameters": {"type": "object", "properties": {}, "required": []},
}

_CANNED_TOOL_SCHEMA_B: dict[str, Any] = {
    "name": "_stub_canned_tool_b",
    "description": "L1 stub canned tool B — not a real tool. Replaced by L2's real search_tools.",
    "parameters": {"type": "object", "properties": {}, "required": []},
}

_CANNED_MCP_SCHEMA_A: dict[str, Any] = {
    "name": "_stub_canned_mcp_a",
    "description": "L1 stub canned MCP tool A — not a real tool. Replaced by L3's real search_mcps.",
    "parameters": {"type": "object", "properties": {}, "required": []},
}

_CANNED_MCP_SCHEMA_B: dict[str, Any] = {
    "name": "_stub_canned_mcp_b",
    "description": "L1 stub canned MCP tool B — not a real tool. Replaced by L3's real search_mcps.",
    "parameters": {"type": "object", "properties": {}, "required": []},
}


# ---------------------------------------------------------------------------
# SearchToolsStub
# ---------------------------------------------------------------------------


class SearchToolsStub(Tool):
    """L1 stub for search_tools. Returns canned data so persistence tests
    can exercise the mutation. Replaced by the real implementation at L2.

    Class-attribute name (not instance attribute) is required by
    ToolRegistry.register at base.py:118-119 which keys on tool.name.
    """

    # CLASS attributes — required for ToolRegistry.register to key correctly.
    name = "search_tools"
    description = SEARCH_TOOLS_SCHEMA["description"]
    parameters = SEARCH_TOOLS_SCHEMA["parameters"]

    def __init__(
        self,
        on_match: Callable[[list[dict[str, Any]]], None],
        agent_name: str | None = None,
    ) -> None:
        # Call super().__init__() so Tool base fields (_config, _cross_configs,
        # _agent_name) are set. Zero-arg config is valid: Tool.__init__ defaults
        # all three params to None. Pass agent_name through so the plumbing
        # assertion in test_factory.py (L1b: every registered tool must carry
        # _agent_name == the factory's agent name) is satisfied.
        super().__init__(agent_name=agent_name)
        self._on_match = on_match

    async def execute(self, query: str = "") -> str:  # type: ignore[override]
        canned = [_CANNED_TOOL_SCHEMA_A, _CANNED_TOOL_SCHEMA_B]
        self._on_match(canned)
        return (
            f"Found {len(canned)} tools matching {query!r}: "
            f"{_CANNED_TOOL_SCHEMA_A['name']}, {_CANNED_TOOL_SCHEMA_B['name']} "
            f"(L1 stub data; real implementation lands at L2)."
        )


# ---------------------------------------------------------------------------
# SearchMcpsStub
# ---------------------------------------------------------------------------


class SearchMcpsStub(Tool):
    """L1 stub for search_mcps. Returns canned MCP tool data so persistence
    tests can exercise the mutation. Replaced by the real implementation at L3.

    Class-attribute name (not instance attribute) is required by
    ToolRegistry.register at base.py:118-119 which keys on tool.name.
    """

    # CLASS attributes — required for ToolRegistry.register to key correctly.
    name = "search_mcps"
    description = SEARCH_MCPS_SCHEMA["description"]
    parameters = SEARCH_MCPS_SCHEMA["parameters"]

    def __init__(
        self,
        on_match: Callable[[list[dict[str, Any]]], None],
        agent_name: str | None = None,
    ) -> None:
        # Call super().__init__() so Tool base fields (_config, _cross_configs,
        # _agent_name) are set. Zero-arg config is valid: Tool.__init__ defaults
        # all three params to None. Pass agent_name through so the plumbing
        # assertion in test_factory.py (L1b: every registered tool must carry
        # _agent_name == the factory's agent name) is satisfied.
        super().__init__(agent_name=agent_name)
        self._on_match = on_match

    async def execute(self, query: str = "") -> str:  # type: ignore[override]
        canned = [_CANNED_MCP_SCHEMA_A, _CANNED_MCP_SCHEMA_B]
        self._on_match(canned)
        return (
            f"Found {len(canned)} MCP tools matching {query!r}: "
            f"{_CANNED_MCP_SCHEMA_A['name']}, {_CANNED_MCP_SCHEMA_B['name']} "
            f"(L1 stub data; real implementation lands at L3)."
        )
