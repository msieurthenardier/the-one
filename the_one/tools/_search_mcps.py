"""F10 L3: real implementation of search_mcps.

Replaces SearchMcpsStub at production wiring. Searches across attached
MCP sources (by source name + synthetic description) AND per-tool
(name + description). Matched MCP tool schemas are added to the
agent's _loaded_schemas via on_match.

Per-source enabled_tools/disabled_tools filtering is ALREADY APPLIED at
agent build time by MCPToolProvider.get_tools_for_agent (via shared
helper filter_mcp_tools_by_override). SearchMcps relies on the registry
+ source_index already reflecting that filter; it does NOT re-apply.

Source index shape: ``dict[str, dict]`` where each entry is
``{source_name: {"synthetic_description": str, "tool_names_prefixed": list[str]}}``.
Built by the factory at agent-build time from each attached source's
``_cache.tools`` (filtered through mcp_overrides).

Consistency caveat: a source whose ``_cache.tools`` is populated will
appear in source_index, but if ``get_tools_for_agent`` later fails to
``acquire`` for that source, its tools won't land in the registry.
Source-level matching against that source will return zero schemas
(since ``_filter_mcp_candidates`` reads schemas from the registry, not
the index). This is acceptable for L3 scope — per-tool name matching
against the registry's ``mcp__``-prefixed schemas still works.

Two sources with the same name are impossible due to the DB unique
constraint on source.name; if it ever happened, source_index would
silently dedupe (second source's entry overwrites first). Not L3's
concern — mentioned here for future safety.

NOTE: ``mcp__``-prefixed names are assumed to identify MCP tools. A
future built-in tool starting with ``mcp__`` would be erroneously
included in SearchMcps results — do NOT create built-in tools with
that prefix.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from the_one.agent.core import SEARCH_MCPS_SCHEMA
from the_one.tools.base import Tool, ToolRegistry

_MCP_PREFIX = "mcp__"
_DEFAULT_DESCRIPTION_CAP = 200


def _build_synthetic_description(
    source_name: str,
    tool_short_names: list[str],
    char_cap: int = _DEFAULT_DESCRIPTION_CAP,
) -> str:
    """Build a synthetic source-level description from tool short names.

    Format: ``"{source_name}: {comma-separated short names} ({N} tools)"``.
    Truncated to ``char_cap`` with ellipsis when the full list would exceed
    the budget.

    Two-pass logic:

    1. Compute the full body — if it fits within ``char_cap``, emit
       complete without truncation.
    2. Truncation path: accumulate names until the NEXT segment would
       exceed the budget (after reserving 3 chars for ``"..."``). The
       guard is ``> available`` (NOT ``> available - 3``) — the ``- 3``
       form drops the last name even when it would have fit exactly,
       producing a spurious ``"..."`` at the boundary case.

    Zero-tool source returns ``"{source_name}: (no cached tools)"``.
    """
    if not tool_short_names:
        return f"{source_name}: (no cached tools)"

    count = len(tool_short_names)
    suffix = f" ({count} tools)"
    prefix = f"{source_name}: "
    available = char_cap - len(prefix) - len(suffix)

    # First pass: check if the full list fits without truncation.
    full_body = ", ".join(tool_short_names)
    if len(full_body) <= available:
        return f"{prefix}{full_body}{suffix}"

    # Truncation path: reserve 3 chars for "...".
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


def _filter_mcp_candidates(
    schemas: list[dict[str, Any]],
    source_index: dict[str, dict[str, Any]],
    query: str,
) -> list[dict[str, Any]]:
    """Pure function: filter mcp__-prefixed schemas by query.

    Empty query returns all mcp__-prefixed schemas. Non-empty query
    case-insensitively matches against:

    * **Source level** — source name + synthetic_description. Matching a
      source returns ALL of that source's registered tools.
    * **Per-tool level** — individual tool name + description.

    Results are the union of source-level and per-tool matches, deduped
    by tool name (preserving order: source-matched tools first, per-tool
    additions appended).

    NOTE: this function reads from ``schemas`` (the registry snapshot) —
    NOT from ``source_index`` — so it only returns tools that are
    actually registered. A source that appears in source_index but whose
    tools failed to register (e.g. ``acquire`` error) will not surface
    any tools in the output.
    """
    q = query.lower()
    mcp_schemas = [s for s in schemas if s.get("name", "").startswith(_MCP_PREFIX)]

    if not q:
        return mcp_schemas

    # Source-level matching: collect prefixed tool names from matching sources.
    source_matches: set[str] = set()
    for source_name, info in source_index.items():
        haystack = f"{source_name} {info.get('synthetic_description', '')}".lower()
        if q in haystack:
            source_matches.update(info.get("tool_names_prefixed", []))

    # Build result: source-matched tools first, then per-tool matches.
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for s in mcp_schemas:
        name = s.get("name", "")
        if name in seen:
            continue
        if name in source_matches:
            out.append(s)
            seen.add(name)
            continue
        haystack = f"{name} {s.get('description', '')}".lower()
        if q in haystack:
            out.append(s)
            seen.add(name)
    return out


class SearchMcps(Tool):
    """F10 L3: real search_mcps implementation.

    Replaces SearchMcpsStub in production wiring. Searches the agent's
    attached MCP sources by source name + synthetic description (source-
    level) and by individual tool name + description (per-tool). Matched
    MCP tool schemas are added to the agent's visibility set via the
    ``on_match`` callback, making them available to the LLM in subsequent
    turns.
    """

    # CLASS attributes — required by ToolRegistry.register at base.py:118-119.
    name = "search_mcps"
    description = SEARCH_MCPS_SCHEMA["description"]
    parameters = SEARCH_MCPS_SCHEMA["parameters"]

    def __init__(
        self,
        on_match: Callable[[list[dict[str, Any]]], None],
        registry: ToolRegistry,
        source_index: dict[str, dict[str, Any]],
        agent_name: str | None = None,
    ) -> None:
        # super().__init__ sets self._agent_name via Tool's base __init__.
        # Do NOT re-assign self._agent_name = agent_name here — that would
        # duplicate base initialization and drift from L2's SearchTools pattern.
        super().__init__(agent_name=agent_name)
        self._on_match = on_match
        self._registry = registry
        self._source_index = source_index

    async def execute(self, query: str = "") -> str:  # type: ignore[override]
        all_schemas = self._registry.all_schemas()
        mcp_in_registry = [
            s for s in all_schemas if s.get("name", "").startswith(_MCP_PREFIX)
        ]
        # Empty-registry-no-attached-MCPs UX: distinguish from "search returned 0".
        if not mcp_in_registry and not self._source_index:
            return "No MCP sources are attached to this agent."

        matches = _filter_mcp_candidates(all_schemas, self._source_index, query)
        if not matches:
            return f"No MCP tools found matching {query!r}."

        self._on_match(matches)

        # Format result: source-grouped breakdown.
        # Parse "mcp__{source}__{tool}" → source = middle segment.
        by_source: dict[str, list[str]] = {}
        for s in matches:
            parts = s["name"].split("__", 2)
            src = parts[1] if len(parts) >= 3 else "unknown"
            by_source.setdefault(src, []).append(s["name"])
        groups = []
        for src, names in by_source.items():
            groups.append(f"{src}: {', '.join(names)}")
        if query:
            return (
                f"Found {len(matches)} MCP tools matching {query!r}: "
                + "; ".join(groups)
                + "."
            )
        return f"Found {len(matches)} MCP tools: " + "; ".join(groups) + "."
