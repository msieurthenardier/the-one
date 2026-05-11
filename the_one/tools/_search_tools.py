"""Unified search_tools: searches both built-in tools and attached MCP servers.

Iterates the agent's ToolRegistry, applies search-tool exclusions, substring-
matches against name + description (case-insensitive) for built-in tools and
both source-level (source name + synthetic description) + per-tool for MCP
tools, and mutates the shared visibility-filter container via the on_match
callback.

Per-agent enabled_tools/disabled_tools filtering is ALREADY APPLIED at
registry-build time by ``AgentFactory.create``. Per-source MCP override
filtering is ALREADY APPLIED at agent build time by
``MCPToolProvider.get_tools_for_agent`` (via the shared
``filter_mcp_tools_by_override`` helper). This module relies on the
registry + source_index already reflecting those filters; it does NOT
re-apply.

Source index shape: ``dict[str, dict]`` where each entry is
``{source_name: {"synthetic_description": str, "tool_names_prefixed": list[str]}}``.
Built by the factory at agent-build time from each attached source's
``_cache.tools``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from the_one.agent.core import SEARCH_TOOLS_SCHEMA
from the_one.tools.base import Tool, ToolRegistry

# Names that must NEVER appear in search results — they're infrastructure.
_EXCLUDED_NAMES: frozenset[str] = frozenset({"search_tools"})
_MCP_PREFIX = "mcp__"
_DEFAULT_DESCRIPTION_CAP = 200


def _build_synthetic_description(
    source_name: str,
    tool_short_names: list[str],
    char_cap: int = _DEFAULT_DESCRIPTION_CAP,
) -> str:
    """Synthetic source-level description from tool short names.

    Format: ``"{source_name}: {comma-separated short names} ({N} tools)"``,
    truncated to ``char_cap`` with ellipsis when the full list exceeds the
    budget. Zero-tool source returns ``"{source_name}: (no cached tools)"``.

    Truncation budgets ``"..."`` (3 chars) against the available body width
    and uses ``> available`` (NOT ``> available - 3``) to avoid dropping a
    name that would have fit exactly at the boundary.
    """
    if not tool_short_names:
        return f"{source_name}: (no cached tools)"

    count = len(tool_short_names)
    suffix = f" ({count} tools)"
    prefix = f"{source_name}: "
    available = char_cap - len(prefix) - len(suffix)

    full_body = ", ".join(tool_short_names)
    if len(full_body) <= available:
        return f"{prefix}{full_body}{suffix}"

    truncation_marker = "..."
    truncation_budget = available - len(truncation_marker)
    body = ""
    for i, name in enumerate(tool_short_names):
        segment = name if i == 0 else f", {name}"
        if len(body) + len(segment) > truncation_budget:
            break
        body += segment
    body += truncation_marker
    return f"{prefix}{body}{suffix}"


def _filter_candidates(
    schemas: list[dict[str, Any]],
    source_index: dict[str, dict[str, Any]],
    query: str,
) -> list[dict[str, Any]]:
    """Filter all schemas (built-in + MCP) by the search rules + substring query.

    Built-in tools match against ``name`` + ``description``. MCP tools
    (``mcp__``-prefixed) match against the same fields AND can also be
    selected en bloc when the query matches their source name or synthetic
    description in ``source_index``.

    Empty query returns every non-excluded schema. ``search_tools`` itself
    is always filtered out.
    """
    q = query.lower()

    # Source-level MCP matches: collect prefixed tool names from any source
    # whose name + synthetic description contains the query.
    source_matched_names: set[str] = set()
    if q:
        for source_name, info in source_index.items():
            haystack = f"{source_name} {info.get('synthetic_description', '')}".lower()
            if q in haystack:
                source_matched_names.update(info.get("tool_names_prefixed", []))

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for s in schemas:
        name = s.get("name", "")
        if name in _EXCLUDED_NAMES or name in seen:
            continue
        if not q:
            out.append(s)
            seen.add(name)
            continue
        if name in source_matched_names:
            out.append(s)
            seen.add(name)
            continue
        haystack = f"{name} {s.get('description', '')}".lower()
        if q in haystack:
            out.append(s)
            seen.add(name)
    return out


def _format_result(matches: list[dict[str, Any]], query: str) -> str:
    """Format matches as a single grouped line: built-in first, then per-source."""
    builtin: list[str] = []
    by_source: dict[str, list[str]] = {}
    for s in matches:
        name = s["name"]
        if name.startswith(_MCP_PREFIX):
            parts = name.split("__", 2)
            src = parts[1] if len(parts) >= 3 else "unknown"
            by_source.setdefault(src, []).append(name)
        else:
            builtin.append(name)

    groups: list[str] = []
    if builtin:
        groups.append(f"built-in: {', '.join(builtin)}")
    for src, names in by_source.items():
        groups.append(f"mcp:{src}: {', '.join(names)}")
    body = "; ".join(groups)

    if query:
        return f"Found {len(matches)} tools matching {query!r}: {body}."
    return f"Found {len(matches)} tools: {body}."


class SearchTools(Tool):
    """Unified search_tools — covers built-in catalog + attached MCP servers."""

    # CLASS attributes — required by ToolRegistry.register at base.py:118-119.
    name = "search_tools"
    description = SEARCH_TOOLS_SCHEMA["description"]
    parameters = SEARCH_TOOLS_SCHEMA["parameters"]

    def __init__(
        self,
        on_match: Callable[[list[dict[str, Any]]], None],
        registry: ToolRegistry,
        source_index: dict[str, dict[str, Any]] | None = None,
        agent_name: str | None = None,
    ) -> None:
        super().__init__(agent_name=agent_name)
        self._on_match = on_match
        self._registry = registry
        self._source_index: dict[str, dict[str, Any]] = source_index or {}

    async def execute(self, query: str = "") -> str:  # type: ignore[override]
        all_schemas = self._registry.all_schemas()
        matches = _filter_candidates(all_schemas, self._source_index, query)
        if not matches:
            return f"No tools found matching {query!r}."
        self._on_match(matches)
        return _format_result(matches, query)
