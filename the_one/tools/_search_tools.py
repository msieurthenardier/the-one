"""F10 L2: real implementation of search_tools.

Replaces L1's SearchToolsStub at production wiring. Iterates the agent's
ToolRegistry, applies the search-tool + mcp__ prefix exclusions, substring-
matches against name + description (case-insensitive), and mutates the
shared visibility-filter container via the on_match callback.

Per-agent enabled_tools/disabled_tools filtering is ALREADY APPLIED at
registry-build time by factory.py:178-181. SearchTools relies on that;
it does NOT re-apply per-agent filtering. The registry passed at
construction is the source of truth.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from the_one.agent.core import SEARCH_TOOLS_SCHEMA
from the_one.tools.base import Tool, ToolRegistry

# Schemas to exclude from search_tools results.
# search_tools and search_mcps are infrastructure — they shouldn't surface
# in their own results. mcp__-prefixed names are MCP tools (L3 territory).
_EXCLUDED_NAMES: frozenset[str] = frozenset({"search_tools", "search_mcps"})
_MCP_PREFIX = "mcp__"


def _filter_candidates(
    schemas: list[dict[str, Any]],
    query: str,
) -> list[dict[str, Any]]:
    """Pure function: filter schemas by the search-tools rules + substring query.

    Extracted for unit-testability without registry/agent state. Returns
    schemas whose name passes the exclusion rules AND whose concatenated
    name+description contains the lowercased query as substring. Empty
    query returns all schemas that pass the exclusion rules.
    """
    out: list[dict[str, Any]] = []
    q = query.lower()
    for s in schemas:
        name = s.get("name", "")
        if name in _EXCLUDED_NAMES:
            continue
        if name.startswith(_MCP_PREFIX):
            continue
        if q:
            haystack = f"{name} {s.get('description', '')}".lower()
            if q not in haystack:
                continue
        out.append(s)
    return out


class SearchTools(Tool):
    """F10 L2: real search_tools implementation."""

    # CLASS attributes — required by ToolRegistry.register at base.py:118-119.
    name = "search_tools"
    description = SEARCH_TOOLS_SCHEMA["description"]
    parameters = SEARCH_TOOLS_SCHEMA["parameters"]

    def __init__(
        self,
        on_match: Callable[[list[dict[str, Any]]], None],
        registry: ToolRegistry,
        agent_name: str | None = None,
    ) -> None:
        super().__init__(agent_name=agent_name)
        self._on_match = on_match
        self._registry = registry

    async def execute(self, query: str = "") -> str:  # type: ignore[override]
        all_schemas = self._registry.all_schemas()
        matches = _filter_candidates(all_schemas, query)
        if not matches:
            # Use precise format for the no-match string so tests can ==-assert it.
            return f"No tools found matching {query!r}."
        self._on_match(matches)
        names = ", ".join(m["name"] for m in matches)
        # Empty-query path omits the "matching ''" clause for readability;
        # non-empty path includes the query for clarity. Both paths are pinned
        # in tests via ==-assertion against the exact string.
        if query:
            return f"Found {len(matches)} tools matching {query!r}: {names}."
        return f"Found {len(matches)} tools: {names}."
