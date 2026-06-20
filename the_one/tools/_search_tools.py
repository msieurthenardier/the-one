"""Unified search_tools: searches both built-in tools and attached MCP servers.

Iterates the agent's ToolRegistry, applies search-tool exclusions, tokenized-
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

Matching semantics (M16 F03 L08A in-flight adaptation):
- The query is tokenized on whitespace (lowercase). A tool matches if ANY
  query token is a substring of the tool's ``name + ' ' + description``
  (case-insensitive). This makes multi-word natural-language queries
  permissive enough to surface relevant tools.
- Noise tokens are dropped before matching: tokens shorter than 3 chars AND
  a small stopword set are filtered out. If ALL tokens are filtered, the
  original query is treated as a single substring (old behavior preserved).
- Results are ranked by the number of distinct query tokens matched
  (descending); stable order within the same score.
- An empty query returns all non-excluded schemas (unchanged).
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

# Maximum number of results returned for a non-empty query. Keeps the result
# set focused enough for small models to pick from. Empty queries are exempt —
# "list everything" must remain uncapped (SEARCH_TOOLS_SCHEMA contract).
_MAX_SEARCH_RESULTS = 8

# Stopwords filtered out before token matching. Keep this list short and
# focused on noise that would match spuriously across many tools. Single-
# keyword queries are unaffected (tokens shorter than 3 chars are also
# dropped, so "a", "an", "to" are covered by the length gate).
_STOPWORDS: frozenset[str] = frozenset(
    {
        "run",
        "get",
        "the",
        "and",
        "with",
        "use",
        "can",
        "you",
        "please",
        "find",
        "out",
        "what",
        "how",
        "are",
        "for",
        "my",
        "me",
        "of",
        "in",
        "on",
        "your",
        "is",
    }
)


def _tokenize_query(query: str) -> list[str]:
    """Tokenize a query, dropping short tokens and stopwords.

    Returns a non-empty list of meaningful tokens, or an empty list if
    all tokens were filtered (caller should fall back to whole-phrase match).
    """
    tokens = query.lower().split()
    meaningful = [t for t in tokens if len(t) >= 3 and t not in _STOPWORDS]
    return meaningful


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


def _match_score(haystack: str, tokens: list[str], fallback_phrase: str) -> int:
    """Return the number of distinct tokens matched in haystack.

    When ``tokens`` is empty (all tokens were stopwords/short), falls back to
    whole-phrase substring matching: returns 1 if the phrase matches, else 0.
    """
    if not tokens:
        return 1 if fallback_phrase in haystack else 0
    return sum(1 for t in tokens if t in haystack)


def _filter_candidates(
    schemas: list[dict[str, Any]],
    source_index: dict[str, dict[str, Any]],
    query: str,
) -> list[dict[str, Any]]:
    """Filter all schemas (built-in + MCP) by the search rules + tokenized query.

    Built-in tools match against ``name`` + ``description``. MCP tools
    (``mcp__``-prefixed) match against the same fields AND can also be
    selected en bloc when the query matches their source name or synthetic
    description in ``source_index``.

    Matching semantics:
    - The query is tokenized on whitespace. A tool matches if ANY token is a
      substring of its ``name + ' ' + description`` (case-insensitive).
    - Short tokens (< 3 chars) and stopwords are filtered. If all tokens are
      filtered, the original query is used as a single whole-phrase substring
      (backward-compatible with single-keyword queries).
    - Results are ranked by number of distinct tokens matched (descending);
      stable order within the same score.
    - Empty query returns every non-excluded schema. ``search_tools`` itself
      is always filtered out.
    """
    q = query.lower()
    tokens = _tokenize_query(q) if q else []

    # Source-level MCP matches: collect prefixed tool names from any source
    # whose name + synthetic description matches the query.
    # Uses tokenized matching with the same semantics as per-tool matching.
    source_matched_names: set[str] = set()
    source_scores: dict[str, int] = {}  # prefixed name → best source-level score
    if q:
        for source_name, info in source_index.items():
            haystack = f"{source_name} {info.get('synthetic_description', '')}".lower()
            score = _match_score(haystack, tokens, q)
            if score > 0:
                for prefixed in info.get("tool_names_prefixed", []):
                    source_matched_names.add(prefixed)
                    # Keep the best source-level score for ranking; may be
                    # superseded by a higher per-tool score below.
                    source_scores[prefixed] = max(source_scores.get(prefixed, 0), score)

    # Collect (schema, score) pairs for all candidates.
    candidates: list[tuple[dict[str, Any], int]] = []
    seen: set[str] = set()
    for s in schemas:
        name = s.get("name", "")
        if name in _EXCLUDED_NAMES or name in seen:
            continue
        seen.add(name)
        if not q:
            candidates.append((s, 0))
            continue
        haystack = f"{name} {s.get('description', '')}".lower()
        per_tool_score = _match_score(haystack, tokens, q)
        if name in source_matched_names:
            # Take the better of source-level and per-tool scores.
            score = max(source_scores.get(name, 0), per_tool_score)
            candidates.append((s, score))
        elif per_tool_score > 0:
            candidates.append((s, per_tool_score))

    if not q:
        # Empty query: preserve original schema order, no ranking needed.
        # NOT capped — "empty query returns everything" is a contract invariant.
        return [s for s, _ in candidates]

    # Rank by score descending (stable sort preserves original order within
    # the same score bucket), then cap to the top N most-relevant matches.
    candidates.sort(key=lambda pair: pair[1], reverse=True)
    ranked = [s for s, _ in candidates]
    return ranked[:_MAX_SEARCH_RESULTS]


def _format_result(
    matches: list[dict[str, Any]],
    query: str,
    *,
    capped: bool = False,
) -> str:
    """Format matches as a single grouped line: built-in first, then per-source.

    When ``capped`` is True (non-empty query result hit the ``_MAX_SEARCH_RESULTS``
    ceiling), appends "(top matches)" after the count to signal that more tools
    exist but were not returned.
    """
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

    count_str = f"{len(matches)} tools (top matches)" if capped else f"{len(matches)} tools"
    if query:
        return f"Found {count_str} matching {query!r}: {body}."
    return f"Found {count_str}: {body}."


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
        # Detect whether the cap was applied: non-empty query and result is at
        # the ceiling. We can't know the pre-cap count from here, so we check
        # whether results hit the cap threshold.
        capped = bool(query) and len(matches) == _MAX_SEARCH_RESULTS
        return _format_result(matches, query, capped=capped)
