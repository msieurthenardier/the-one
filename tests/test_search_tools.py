"""Tests for the unified SearchTools implementation.

Covers the filter logic (built-in + MCP source-level + per-tool), substring
matching, case-insensitivity, exclusion of search_tools itself, on_match
mutation, idempotency, result formatting, the _build_synthetic_description
helper, and factory integration wiring.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from the_one.agent.config import AgentConfig
from the_one.agent.factory import AgentFactory
from the_one.db.models import MCPSource
from the_one.mcp._tool_provider import filter_mcp_tools_by_override
from the_one.mcp.types import MCPTool
from the_one.tools._search_stubs import SearchToolsStub
from the_one.tools._search_tools import (
    _MAX_SEARCH_RESULTS,
    _STOPWORDS,
    SearchTools,
    _build_synthetic_description,
    _filter_candidates,
    _format_result,
    _tokenize_query,
)
from the_one.tools.base import Tool, ToolRegistry
from the_one.tools.builtins import BuiltinToolProvider

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_registry_with_real_tools(agent_name: str = "test") -> ToolRegistry:
    """Build a ToolRegistry populated by BuiltinToolProvider (factory path)."""
    provider = BuiltinToolProvider()
    registry = ToolRegistry()
    for tool in provider.get_tools({}, {}, agent_name=agent_name):
        registry.register(tool)
    return registry


def _make_on_match(
    loaded_schemas: list[dict],
    loaded_tool_names: set[str],
) -> Any:
    def _on_match(schemas: list[dict]) -> None:
        for s in schemas:
            if s["name"] not in loaded_tool_names:
                loaded_schemas.append(s)
                loaded_tool_names.add(s["name"])

    return _on_match


def _make_search_tools(
    registry: ToolRegistry | None = None,
    source_index: dict[str, dict[str, Any]] | None = None,
    loaded_schemas: list[dict] | None = None,
    loaded_tool_names: set[str] | None = None,
    agent_name: str | None = "test",
) -> tuple[SearchTools, list[dict], set[str]]:
    if registry is None:
        registry = _make_registry_with_real_tools(agent_name or "test")
    ls: list[dict] = loaded_schemas if loaded_schemas is not None else []
    ltn: set[str] = loaded_tool_names if loaded_tool_names is not None else set()
    on_match = _make_on_match(ls, ltn)
    st = SearchTools(
        on_match=on_match,
        registry=registry,
        source_index=source_index or {},
        agent_name=agent_name,
    )
    return st, ls, ltn


def _make_provider_config_for_factory():
    from the_one.db.models import LLMProviderConfig

    return LLMProviderConfig(
        id="test-provider",
        name="Test Provider",
        type="ollama",
        base_url="http://localhost:11434/v1",
    )


def _make_mcp_tool(
    name: str,
    description: str = "",
    input_schema: dict | None = None,
) -> MCPTool:
    return MCPTool(
        name=name,
        description=description,
        input_schema=(
            input_schema if input_schema is not None else {"type": "object", "properties": {}}
        ),
        output_schema=None,
        annotations=None,
    )


def _make_source(
    source_id: str = "src-1",
    name: str = "cloudflare",
    source_type: str = "stdio",
    config: dict | None = None,
    secrets: dict | None = None,
) -> MCPSource:
    return MCPSource(
        id=source_id,
        name=name,
        type=source_type,  # type: ignore[arg-type]
        config=config or {},
        secrets=secrets or {},
    )


def _synthetic_schema(name: str, description: str = "") -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "parameters": {"type": "object", "properties": {}, "required": []},
    }


class _MockTool(Tool):
    def __init__(self, tool_name: str, description: str = "") -> None:
        super().__init__()
        self.name = tool_name
        self.description = description
        self.parameters: dict[str, Any] = {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> str:
        return "ok"


# ---------------------------------------------------------------------------
# Built-in catalog tests
# ---------------------------------------------------------------------------


async def test_empty_query_returns_all_filtered_builtins() -> None:
    """Empty query returns all built-in tools (excluding search_tools)."""
    registry = _make_registry_with_real_tools()
    st, ls, _ = _make_search_tools(registry=registry)

    result = await st.execute("")

    assert result.startswith("Found ")
    assert "built-in:" in result
    assert len(ls) > 0

    loaded_names = {s["name"] for s in ls}
    assert "search_tools" not in loaded_names
    assert "read_file" in loaded_names
    assert "write_file" in loaded_names
    assert "shell" in loaded_names


async def test_query_substring_match_on_name() -> None:
    """Query 'shell' returns shell, shell_session_*."""
    registry = _make_registry_with_real_tools()
    st, ls, _ = _make_search_tools(registry=registry)

    result = await st.execute("shell")

    loaded_names = {s["name"] for s in ls}
    assert "shell" in loaded_names
    assert "shell_session_start" in loaded_names
    assert "shell_session_send" in loaded_names
    assert "shell_session_close" in loaded_names
    assert "shell_session_list" in loaded_names
    assert "read_file" not in loaded_names

    assert result.startswith("Found ")
    assert "'shell'" in result


async def test_query_substring_match_on_description() -> None:
    """Query 'contents' matches read_file via its description."""
    registry = _make_registry_with_real_tools()
    st, ls, _ = _make_search_tools(registry=registry)

    result = await st.execute("contents")

    loaded_names = {s["name"] for s in ls}
    assert "read_file" in loaded_names
    assert result.startswith("Found ")


async def test_query_case_insensitive() -> None:
    """Query 'SHELL' returns the same set as 'shell'."""
    registry = _make_registry_with_real_tools()
    st_lower, ls_lower, _ = _make_search_tools(registry=registry)
    await st_lower.execute("shell")

    registry2 = _make_registry_with_real_tools()
    st_upper, ls_upper, _ = _make_search_tools(registry=registry2)
    await st_upper.execute("SHELL")

    assert {s["name"] for s in ls_lower} == {s["name"] for s in ls_upper}


async def test_no_match_returns_helpful_text() -> None:
    """Query with no matches returns the exact no-match string; loaded_schemas unchanged."""
    registry = _make_registry_with_real_tools()
    st, ls, _ = _make_search_tools(registry=registry)

    result = await st.execute("xyzzy_nonexistent")

    assert result == "No tools found matching 'xyzzy_nonexistent'."
    assert len(ls) == 0


async def test_excludes_search_tools_from_results() -> None:
    """Query 'search' does NOT return search_tools itself."""
    registry = ToolRegistry()
    for tool in BuiltinToolProvider().get_tools({}, {}, agent_name="test"):
        registry.register(tool)
    on_match_inner = _make_on_match([], set())
    registry.register(SearchToolsStub(on_match=on_match_inner))

    st, ls, _ = _make_search_tools(registry=registry)
    await st.execute("search")

    loaded_names = {s["name"] for s in ls}
    assert "search_tools" not in loaded_names


async def test_mutates_loaded_schemas_via_on_match() -> None:
    registry = _make_registry_with_real_tools()
    st, ls, ltn = _make_search_tools(registry=registry)

    assert len(ls) == 0
    await st.execute("file")

    assert len(ls) > 0
    loaded_names = {s["name"] for s in ls}
    assert "read_file" in loaded_names
    assert "write_file" in loaded_names
    assert loaded_names == ltn


async def test_idempotent_on_repeated_calls() -> None:
    registry = _make_registry_with_real_tools()
    st, ls, ltn = _make_search_tools(registry=registry)

    await st.execute("file")
    count_after_first = len(ls)
    assert count_after_first > 0

    await st.execute("file")
    assert len(ls) == count_after_first
    assert len(ltn) == count_after_first


# ---------------------------------------------------------------------------
# MCP-side coverage in the unified search
# ---------------------------------------------------------------------------


async def test_empty_query_includes_mcp_tools() -> None:
    """Empty query returns built-ins AND mcp__-prefixed schemas."""
    registry = ToolRegistry()
    registry.register(_MockTool("read_file", "Read the contents of a file"))
    registry.register(_MockTool("mcp__foo__a", "foo a"))
    registry.register(_MockTool("mcp__bar__c", "bar c"))

    source_index = {
        "foo": {
            "synthetic_description": "foo: a (1 tools)",
            "tool_names_prefixed": ["mcp__foo__a"],
        },
        "bar": {
            "synthetic_description": "bar: c (1 tools)",
            "tool_names_prefixed": ["mcp__bar__c"],
        },
    }
    st, ls, _ = _make_search_tools(registry=registry, source_index=source_index)

    result = await st.execute("")

    loaded_names = {s["name"] for s in ls}
    assert loaded_names == {"read_file", "mcp__foo__a", "mcp__bar__c"}
    assert "built-in: read_file" in result
    assert "mcp:foo: mcp__foo__a" in result
    assert "mcp:bar: mcp__bar__c" in result


async def test_query_matches_mcp_source_name() -> None:
    """Query matching a source name returns ALL of that source's tools."""
    registry = ToolRegistry()
    registry.register(_MockTool("mcp__cloudflare__list_zones", "list zones"))
    registry.register(_MockTool("mcp__cloudflare__get_zone", "get zone"))
    registry.register(_MockTool("mcp__github__get_repo", "get repo"))
    source_index = {
        "cloudflare": {
            "synthetic_description": "cloudflare: list_zones, get_zone (2 tools)",
            "tool_names_prefixed": [
                "mcp__cloudflare__list_zones",
                "mcp__cloudflare__get_zone",
            ],
        },
        "github": {
            "synthetic_description": "github: get_repo (1 tools)",
            "tool_names_prefixed": ["mcp__github__get_repo"],
        },
    }
    st, ls, _ = _make_search_tools(registry=registry, source_index=source_index)

    result = await st.execute("cloudflare")

    loaded_names = {s["name"] for s in ls}
    assert loaded_names == {
        "mcp__cloudflare__list_zones",
        "mcp__cloudflare__get_zone",
    }
    assert "mcp:cloudflare:" in result


async def test_query_matches_mcp_per_tool() -> None:
    """Query matching a per-tool description returns just that tool."""
    registry = ToolRegistry()
    registry.register(_MockTool("mcp__myapi__alpha_tool", "Frobnicate the alpha resource"))
    registry.register(_MockTool("mcp__myapi__beta_tool", "Manage beta resources"))
    source_index = {
        "myapi": {
            "synthetic_description": "myapi: alpha_tool, beta_tool (2 tools)",
            "tool_names_prefixed": [
                "mcp__myapi__alpha_tool",
                "mcp__myapi__beta_tool",
            ],
        }
    }
    st, ls, _ = _make_search_tools(registry=registry, source_index=source_index)

    await st.execute("frobnicate")

    loaded_names = {s["name"] for s in ls}
    assert loaded_names == {"mcp__myapi__alpha_tool"}


async def test_query_dedupes_source_and_per_tool() -> None:
    """A tool matched both source-level AND per-tool appears once."""
    registry = ToolRegistry()
    registry.register(_MockTool("mcp__cloudflare__list_zones", "list cloudflare zones"))
    source_index = {
        "cloudflare": {
            "synthetic_description": "cloudflare: list_zones (1 tools)",
            "tool_names_prefixed": ["mcp__cloudflare__list_zones"],
        }
    }
    st, ls, _ = _make_search_tools(registry=registry, source_index=source_index)

    await st.execute("cloudflare")

    assert len(ls) == 1
    assert ls[0]["name"] == "mcp__cloudflare__list_zones"


async def test_unified_query_mixes_builtin_and_mcp() -> None:
    """A query that matches in both catalogs returns both, source-tagged in output."""
    registry = ToolRegistry()
    registry.register(_MockTool("read_file", "Read the contents of a file"))
    registry.register(_MockTool("write_file", "Write a file"))
    registry.register(_MockTool("mcp__store__read_object", "Read an object"))
    source_index = {
        "store": {
            "synthetic_description": "store: read_object (1 tools)",
            "tool_names_prefixed": ["mcp__store__read_object"],
        }
    }
    st, ls, _ = _make_search_tools(registry=registry, source_index=source_index)

    result = await st.execute("read")

    loaded_names = {s["name"] for s in ls}
    assert "read_file" in loaded_names
    assert "mcp__store__read_object" in loaded_names
    assert "built-in: read_file" in result
    assert "mcp:store: mcp__store__read_object" in result


# ---------------------------------------------------------------------------
# Knowledge-base (`kb__`) group tests (Mission 24 Flight 5 Leg 2, DD-7 as
# amended / AC-20 / AC-21). No `source_index` entry exists for a knowledge
# base — matching runs entirely through the tool's own name + description.
# ---------------------------------------------------------------------------


async def test_kb_tool_matches_via_description_not_name() -> None:
    """AC-20: a query matching the knowledge base's DESCRIPTION (not its
    tool name) still returns the tool, via the per-tool matching path —
    the only path there is after the DD-7 amendment (no `source_index`
    entry is ever built for a knowledge base)."""
    registry = ToolRegistry()
    registry.register(
        _MockTool(
            "kb__docs__search",
            "Search the 'Docs' knowledge base. Internal engineering runbooks and postmortems.",
        )
    )
    st, ls, _ = _make_search_tools(registry=registry, source_index={})

    result = await st.execute("runbooks")

    assert ls[0]["name"] == "kb__docs__search"
    assert "kb__docs__search" in result


async def test_kb_group_label_is_kb_colon_slug() -> None:
    """AC-20: the rendered group label is `kb:{slug}:`."""
    registry = ToolRegistry()
    registry.register(_MockTool("kb__docs__search", "Search the 'Docs' knowledge base."))
    st, _, _ = _make_search_tools(registry=registry, source_index={})

    result = await st.execute("docs")

    assert "kb:docs: kb__docs__search" in result


async def test_kb_slug_containing_double_underscore_mis_renders() -> None:
    """AC-21: the recorded latent flaw, pinned. A slug normalized from a
    name containing internal whitespace collisions (e.g. `"My  Notes"` ->
    `"My__Notes"`) produces `kb__My__Notes__search`, whose
    `split("__", 2)[1]` is `"My"` — not the full slug. Same flaw as the
    MCP path; recorded, not fixed."""
    registry = ToolRegistry()
    registry.register(_MockTool("kb__My__Notes__search", "Search the notes knowledge base."))
    st, _, _ = _make_search_tools(registry=registry, source_index={})

    result = await st.execute("notes")

    assert "kb:My: kb__My__Notes__search" in result


async def test_kb_and_mcp_and_builtin_groups_coexist() -> None:
    registry = ToolRegistry()
    registry.register(_MockTool("read_file", "Read a file"))
    registry.register(_MockTool("mcp__store__read_object", "Read an object"))
    registry.register(_MockTool("kb__docs__search", "Read the docs knowledge base"))
    source_index = {
        "store": {
            "synthetic_description": "store: read_object (1 tools)",
            "tool_names_prefixed": ["mcp__store__read_object"],
        }
    }
    st, ls, _ = _make_search_tools(registry=registry, source_index=source_index)

    result = await st.execute("read")

    loaded_names = {s["name"] for s in ls}
    assert "read_file" in loaded_names
    assert "mcp__store__read_object" in loaded_names
    assert "kb__docs__search" in loaded_names
    assert "built-in: read_file" in result
    assert "mcp:store: mcp__store__read_object" in result
    assert "kb:docs: kb__docs__search" in result


# ---------------------------------------------------------------------------
# _filter_candidates pure-function tests
# ---------------------------------------------------------------------------


async def test_filter_helper_excludes_search_tools_and_includes_mcp() -> None:
    schemas = [
        _synthetic_schema("alpha", "alpha tool"),
        _synthetic_schema("beta", "beta tool"),
        _synthetic_schema("search_tools", "search tool"),
        _synthetic_schema("mcp__foo__bar", "foo bar"),
    ]
    source_index = {
        "foo": {
            "synthetic_description": "foo: bar (1 tools)",
            "tool_names_prefixed": ["mcp__foo__bar"],
        }
    }

    assert _filter_candidates([], source_index, "alpha") == ([], 0)

    # Empty query → returns all except search_tools.
    result, total = _filter_candidates(schemas, source_index, "")
    names = {s["name"] for s in result}
    assert names == {"alpha", "beta", "mcp__foo__bar"}
    assert total == len(result)  # empty query is never truncated

    # Substring match on built-in name.
    result, _ = _filter_candidates(schemas, source_index, "alpha")
    assert [s["name"] for s in result] == ["alpha"]

    # Source-level match pulls in the MCP tool.
    result, _ = _filter_candidates(schemas, source_index, "foo")
    assert [s["name"] for s in result] == ["mcp__foo__bar"]

    # search_tools is always excluded.
    result, _ = _filter_candidates(schemas, source_index, "search")
    names = {s["name"] for s in result}
    assert "search_tools" not in names

    # Case-insensitive (both list and total agree).
    assert _filter_candidates(schemas, source_index, "ALPHA") == _filter_candidates(
        schemas, source_index, "alpha"
    )

    # Missing description → empty-string haystack.
    schemas_no_desc = [{"name": "my_tool"}]
    result, _ = _filter_candidates(schemas_no_desc, {}, "my")
    assert len(result) == 1


# ---------------------------------------------------------------------------
# Tokenization helpers
# ---------------------------------------------------------------------------


def test_tokenize_query_single_keyword() -> None:
    """Single meaningful keyword returns itself as the only token."""
    assert _tokenize_query("shell") == ["shell"]


def test_tokenize_query_drops_short_tokens() -> None:
    """Tokens shorter than 3 chars are dropped."""
    assert _tokenize_query("a file") == ["file"]
    assert _tokenize_query("in") == []


def test_tokenize_query_drops_stopwords() -> None:
    """Stopwords are filtered out even when >= 3 chars."""
    assert "run" in _STOPWORDS
    assert _tokenize_query("run") == []
    assert _tokenize_query("get the file") == ["file"]


def test_tokenize_query_empty_returns_empty() -> None:
    assert _tokenize_query("") == []
    assert _tokenize_query("   ") == []


def test_tokenize_query_multiword() -> None:
    """Multi-word natural-language query: stopwords/short filtered, rest kept."""
    tokens = _tokenize_query("run shell command")
    # "run" is a stopword; "shell" and "command" are meaningful
    assert "shell" in tokens
    assert "command" in tokens
    assert "run" not in tokens


def test_tokenize_query_all_stopwords_returns_empty() -> None:
    """All-stopword query: all tokens filtered → empty list → caller falls back."""
    tokens = _tokenize_query("get the")
    assert tokens == []


# ---------------------------------------------------------------------------
# Tokenized matching — _filter_candidates new semantics (M16 F03 L08A)
# ---------------------------------------------------------------------------


async def test_multiword_query_run_shell_command_matches_shell() -> None:
    """'run shell command' → matches shell and shell_session_* tools (ANY token hits).

    M16 F03 L08A: tokenized matching. 'run' is a stopword; 'shell' and 'command'
    are the meaningful tokens. shell's name contains 'shell' → matches. shell_session_*
    names contain 'shell' too. read_file has neither token in name+description.
    """
    registry = _make_registry_with_real_tools()
    st, ls, _ = _make_search_tools(registry=registry)

    result = await st.execute("run shell command")

    loaded_names = {s["name"] for s in ls}
    assert "shell" in loaded_names, "shell must match 'run shell command'"
    assert "shell_session_start" in loaded_names, "shell_session_start must match"
    assert result.startswith("Found ")
    assert "'run shell command'" in result


async def test_multiword_query_list_files_directory_matches_file_tools() -> None:
    """'list files directory' → file/dir tools match and rank above pure-shell tools.

    Tokens: 'list', 'files', 'directory'. Tokenized ANY-match surfaces any tool
    whose haystack contains at least one of these tokens. list_dir, glob, and
    read_file are expected matches. Ranking puts tools with more token hits first.
    """
    registry = _make_registry_with_real_tools()
    st, ls, _ = _make_search_tools(registry=registry)

    result = await st.execute("list files directory")

    loaded_names = {s["name"] for s in ls}
    # Core file/dir tools must be in the results (each matches multiple tokens).
    assert "list_dir" in loaded_names, f"list_dir must match; got {loaded_names}"
    assert "glob" in loaded_names or "read_file" in loaded_names, (
        f"At least one of glob/read_file must match; got {loaded_names}"
    )
    assert result.startswith("Found ")


async def test_stopword_only_query_falls_back_to_phrase_match() -> None:
    """A stopword-only query ('get the') falls back to whole-phrase substring match.

    After filtering, all tokens are removed; _filter_candidates falls back to
    treating the original lowercase query as a single substring. 'get the' is
    unlikely to appear in any tool's name+description verbatim, so the result
    is either empty (no match) or returns only tools whose haystack contains
    the literal phrase 'get the'. The key invariant: it does NOT dump the full
    catalog (which would happen if empty-after-filter were treated as match-all).
    """
    registry = _make_registry_with_real_tools()
    st, ls, _ = _make_search_tools(registry=registry)

    await st.execute("get the")

    # The whole catalog has ~24+ tools; a stopword-only fallback to a rare
    # phrase should surface at most a handful (likely 0 or very few). If
    # the catalog were dumped, loaded_names would contain shell/read_file/etc.
    # We assert it does NOT equal the full catalog.
    all_schema_names = {
        s["name"]
        for s in _make_registry_with_real_tools().all_schemas()
        if s["name"] != "search_tools"
    }
    loaded_names = {s["name"] for s in ls}
    # The fallback-phrase result must be a proper subset of the full catalog
    # (it never dumps everything for a stopword-only query).
    assert loaded_names != all_schema_names, "Stopword-only query must not dump the full catalog"


def test_ranking_more_tokens_ranks_higher() -> None:
    """A tool matching 2 query tokens ranks above one matching 1 token.

    Query 'shell command': tokens ['shell', 'command'].
    - shell_tool: name 'shell' (matches 'shell'), description 'Execute a shell command'
      (matches both 'shell' and 'command') → score 2.
    - read_tool: name 'read', description 'shell only' → matches only 'shell' → score 1.
    shell_tool must appear before read_tool.
    """
    schemas = [
        _synthetic_schema("read_tool", "shell only"),
        _synthetic_schema("shell_tool", "Execute a shell command"),
    ]
    result, _ = _filter_candidates(schemas, {}, "shell command")
    names = [s["name"] for s in result]
    assert "shell_tool" in names
    assert "read_tool" in names
    # shell_tool (score 2) must rank before read_tool (score 1).
    assert names.index("shell_tool") < names.index("read_tool"), (
        f"Expected shell_tool before read_tool; got order {names}"
    )


def test_ranking_single_keyword_stable() -> None:
    """Single-keyword query behaves the same as before: all matching tools returned.

    'shell' is a single meaningful token. All tools containing 'shell' in their
    name or description match with score 1. Relative order among them is stable
    (original schema order preserved within the same score bucket).
    """
    schemas = [
        _synthetic_schema("alpha_shell", "alpha shell tool"),
        _synthetic_schema("beta_shell", "beta shell tool"),
        _synthetic_schema("no_match", "unrelated"),
    ]
    result, _ = _filter_candidates(schemas, {}, "shell")
    names = [s["name"] for s in result]
    assert names == ["alpha_shell", "beta_shell"], (
        f"Expected original order preserved within same score; got {names}"
    )


def test_empty_query_still_returns_all_non_excluded() -> None:
    """Empty query still returns all non-excluded schemas (unchanged by tokenization)."""
    schemas = [
        _synthetic_schema("alpha"),
        _synthetic_schema("search_tools"),
        _synthetic_schema("beta"),
    ]
    result, total = _filter_candidates(schemas, {}, "")
    names = [s["name"] for s in result]
    assert "alpha" in names
    assert "beta" in names
    assert "search_tools" not in names
    assert total == len(result)  # empty query: total == returned


def test_search_tools_excluded_from_tokenized_results() -> None:
    """search_tools is excluded even when 'search' is a query token."""
    schemas = [
        _synthetic_schema("search_tools", "search among tools"),
        _synthetic_schema("other_tool", "search something"),
    ]
    result, _ = _filter_candidates(schemas, {}, "search")
    names = [s["name"] for s in result]
    assert "search_tools" not in names
    assert "other_tool" in names


def test_mcp_source_tokenized_match() -> None:
    """Source-level MCP matching also uses tokenized semantics.

    Query 'list zones': tokens ['list', 'zones']. The cloudflare source's
    synthetic description contains 'list_zones', which contains both 'list'
    and 'zones'. github's description ('get_repo') matches neither.
    """
    schemas = [
        _synthetic_schema("mcp__cloudflare__list_zones", "list zones"),
        _synthetic_schema("mcp__github__get_repo", "get repo"),
    ]
    source_index = {
        "cloudflare": {
            "synthetic_description": "cloudflare: list_zones (1 tools)",
            "tool_names_prefixed": ["mcp__cloudflare__list_zones"],
        },
        "github": {
            "synthetic_description": "github: get_repo (1 tools)",
            "tool_names_prefixed": ["mcp__github__get_repo"],
        },
    }
    result, _ = _filter_candidates(schemas, source_index, "list zones")
    names = {s["name"] for s in result}
    assert "mcp__cloudflare__list_zones" in names
    assert "mcp__github__get_repo" not in names


# ---------------------------------------------------------------------------
# _format_result tests
# ---------------------------------------------------------------------------


def test_format_result_built_in_only() -> None:
    matches = [_synthetic_schema("a"), _synthetic_schema("b")]
    assert _format_result(matches, "") == "Found 2 tools: built-in: a, b."
    assert _format_result(matches, "q") == "Found 2 tools matching 'q': built-in: a, b."


def test_format_result_mixed_groups() -> None:
    matches = [
        _synthetic_schema("a"),
        _synthetic_schema("mcp__foo__x"),
        _synthetic_schema("mcp__foo__y"),
        _synthetic_schema("mcp__bar__z"),
    ]
    out = _format_result(matches, "")
    assert "built-in: a" in out
    assert "mcp:foo: mcp__foo__x, mcp__foo__y" in out
    assert "mcp:bar: mcp__bar__z" in out
    assert out.startswith("Found 4 tools:")


# ---------------------------------------------------------------------------
# _build_synthetic_description tests
# ---------------------------------------------------------------------------


def test_build_synthetic_description_basic() -> None:
    assert _build_synthetic_description("foo", ["a", "b", "c"]) == "foo: a, b, c (3 tools)"


def test_build_synthetic_description_empty_tools() -> None:
    assert _build_synthetic_description("foo", []) == "foo: (no cached tools)"


def test_build_synthetic_description_truncation() -> None:
    tool_names = [f"tool_{i:02d}" for i in range(50)]
    result = _build_synthetic_description("my_source", tool_names)
    assert len(result) <= 200
    assert "..." in result
    assert "(50 tools)" in result
    assert result.startswith("my_source: ")


def test_build_synthetic_description_fits_exactly() -> None:
    long_name = "x" * 185
    result = _build_synthetic_description("src", [long_name], char_cap=200)
    assert "..." not in result
    assert result == f"src: {long_name} (1 tools)"


def test_build_synthetic_description_boundary() -> None:
    """Last name fits exactly → no spurious '...'."""
    result = _build_synthetic_description("s", ["a", "b"], char_cap=20)
    assert "..." not in result
    assert result == "s: a, b (2 tools)"


# ---------------------------------------------------------------------------
# filter_mcp_tools_by_override (shared helper) tests
# ---------------------------------------------------------------------------


async def test_filter_mcp_tools_by_override_no_payload() -> None:
    tools = [_make_mcp_tool("foo"), _make_mcp_tool("bar")]
    src = _make_source()
    assert filter_mcp_tools_by_override(tools, src, None) == tools
    assert filter_mcp_tools_by_override(tools, src, {}) == tools


async def test_filter_mcp_tools_by_override_enabled_whitelist() -> None:
    tools = [_make_mcp_tool("foo"), _make_mcp_tool("bar"), _make_mcp_tool("baz")]
    src = _make_source(source_type="stdio")
    result = filter_mcp_tools_by_override(tools, src, {"enabled_tools": ["foo"]})
    assert [t.name for t in result] == ["foo"]


async def test_filter_mcp_tools_by_override_disabled_subtract() -> None:
    tools = [_make_mcp_tool("foo"), _make_mcp_tool("bar"), _make_mcp_tool("baz")]
    src = _make_source(source_type="stdio")
    result = filter_mcp_tools_by_override(tools, src, {"disabled_tools": ["foo"]})
    assert [t.name for t in result] == ["bar", "baz"]


async def test_filter_mcp_tools_by_override_stdio_vs_http() -> None:
    tools = [_make_mcp_tool("alpha"), _make_mcp_tool("beta")]
    payload = {"enabled_tools": ["alpha"]}
    src_stdio = _make_source(source_type="stdio")
    src_http = _make_source(source_type="streamable-http")
    assert [t.name for t in filter_mcp_tools_by_override(tools, src_stdio, payload)] == ["alpha"]
    assert [t.name for t in filter_mcp_tools_by_override(tools, src_http, payload)] == ["alpha"]


# ---------------------------------------------------------------------------
# Factory wiring
# ---------------------------------------------------------------------------


async def test_real_impl_in_factory_wiring() -> None:
    """AgentFactory.create() registers SearchTools (not the stub) under 'search_tools'."""

    class _InMemoryStore:
        async def list_agents(self) -> list[str]:
            return ["wiring-test"]

        async def load(self, name: str) -> AgentConfig:
            return AgentConfig(
                name="wiring-test",
                provider_config_id="test-provider",
                llm_model="stub-model",
            )

        async def exists(self, name: str) -> bool:
            return name == "wiring-test"

    mock_repo = AsyncMock()
    mock_repo.get = AsyncMock(return_value=_make_provider_config_for_factory())
    mock_tool_repo = AsyncMock()
    mock_tool_repo.list = AsyncMock(return_value=[])

    from conftest import FakeLLM

    def _fake_get_provider(name: str, **kwargs: Any) -> FakeLLM:
        return FakeLLM(responses=[])

    with (
        patch("the_one.agent.factory.get_provider", _fake_get_provider),
        patch("the_one.agent.factory.settings") as mock_settings,
        patch("the_one.db.connection.get_connection", new_callable=AsyncMock),
        patch("the_one.encryption.get_encryptor", return_value=AsyncMock()),
        patch("the_one.db.repositories.LLMProviderRepository", return_value=mock_repo),
        patch("the_one.db.repositories.ToolConfigRepository", return_value=mock_tool_repo),
        patch(
            "the_one.db.repositories.AgentRuleRepository",
            return_value=AsyncMock(list_for_agent=AsyncMock(return_value=[])),
        ),
        patch(
            "the_one.db.repositories.AgentNoteRepository",
            return_value=AsyncMock(list_if_enabled=AsyncMock(return_value=None)),
        ),
    ):
        mock_settings.agents_dir = Path("/tmp/test-agents")
        mock_settings.data_dir = Path("/tmp/test-data")
        mock_settings.ensure_dirs = lambda: None

        factory = AgentFactory(store=_InMemoryStore())
        agent = await factory.create("wiring-test")

    search_tool = agent.tools.get("search_tools")
    assert isinstance(search_tool, SearchTools)
    assert not isinstance(search_tool, SearchToolsStub)
    # search_mcps no longer exists as a separate tool.
    assert "search_mcps" not in agent.tools.tool_names


async def test_real_impl_per_agent_filter_applied_at_registry_level() -> None:
    """enabled_tools=['read_file', 'write_file'] → empty search returns only those."""

    class _InMemoryStore:
        async def list_agents(self) -> list[str]:
            return ["filter-test"]

        async def load(self, name: str) -> AgentConfig:
            return AgentConfig(
                name="filter-test",
                provider_config_id="test-provider",
                llm_model="stub-model",
                enabled_tools=["read_file", "write_file"],
            )

        async def exists(self, name: str) -> bool:
            return name == "filter-test"

    mock_repo = AsyncMock()
    mock_repo.get = AsyncMock(return_value=_make_provider_config_for_factory())
    mock_tool_repo = AsyncMock()
    mock_tool_repo.list = AsyncMock(return_value=[])

    from conftest import FakeLLM

    def _fake_get_provider(name: str, **kwargs: Any) -> FakeLLM:
        return FakeLLM(responses=[])

    with (
        patch("the_one.agent.factory.get_provider", _fake_get_provider),
        patch("the_one.agent.factory.settings") as mock_settings,
        patch("the_one.db.connection.get_connection", new_callable=AsyncMock),
        patch("the_one.encryption.get_encryptor", return_value=AsyncMock()),
        patch("the_one.db.repositories.LLMProviderRepository", return_value=mock_repo),
        patch("the_one.db.repositories.ToolConfigRepository", return_value=mock_tool_repo),
        patch(
            "the_one.db.repositories.AgentRuleRepository",
            return_value=AsyncMock(list_for_agent=AsyncMock(return_value=[])),
        ),
        patch(
            "the_one.db.repositories.AgentNoteRepository",
            return_value=AsyncMock(list_if_enabled=AsyncMock(return_value=None)),
        ),
    ):
        mock_settings.agents_dir = Path("/tmp/test-agents")
        mock_settings.data_dir = Path("/tmp/test-data")
        mock_settings.ensure_dirs = lambda: None

        factory = AgentFactory(store=_InMemoryStore())
        agent = await factory.create("filter-test")

    registry_names = set(agent.tools.tool_names)
    assert "read_file" in registry_names
    assert "write_file" in registry_names
    assert "search_tools" in registry_names
    assert "shell" not in registry_names

    search_tool = agent.tools.get("search_tools")
    assert isinstance(search_tool, SearchTools)

    loaded_schemas: list[dict] = agent._loaded_schemas
    initial_count = len(loaded_schemas)

    result = await search_tool.execute("")

    new_schemas = loaded_schemas[initial_count:]
    loaded_names = {s["name"] for s in new_schemas}
    assert loaded_names == {"read_file", "write_file"}
    # current_time (M28) is exempt from the whitelist and already seeded, but
    # SearchTools still lists it as a match; it is not re-loaded (dedupe above).
    assert "Found 3 tools:" in result
    assert "built-in: read_file, write_file, current_time" in result


async def test_no_cache_source_logged_and_skipped(caplog: Any) -> None:
    """MCP source with empty _cache.tools: WARNING logged; NOT in source_index."""
    from the_one.agent.factory import _build_source_index

    source_no_cache = _make_source(
        source_id="src-empty",
        name="empty_source",
        source_type="stdio",
        config={},
    )

    mock_repo = MagicMock()
    mock_repo.get = AsyncMock(return_value=source_no_cache)

    config = AgentConfig(
        name="test-agent",
        provider_config_id="test-provider",
        mcp_source_ids=["src-empty"],
    )

    source_index: dict[str, Any] = {}

    with (
        patch("the_one.agent.factory.settings") as mock_settings,
        patch("the_one.db.connection.get_connection", new_callable=AsyncMock),
        patch("the_one.encryption.get_encryptor", return_value=MagicMock()),
        patch("the_one.db.repositories.MCPSourceRepository", return_value=mock_repo),
    ):
        mock_settings.data_dir = Path("/tmp/test-data")
        with caplog.at_level(logging.WARNING, logger="the_one.agent.factory"):
            await _build_source_index(
                config=config,
                agent_name="test-agent",
                source_index=source_index,
            )

    assert "empty_source" not in source_index
    assert source_index == {}
    assert any(
        "empty_source" in rec.getMessage() and "no cached tools" in rec.getMessage()
        for rec in caplog.records
    ), f"Expected WARNING; got {[r.getMessage() for r in caplog.records]}"


# ---------------------------------------------------------------------------
# Result cap tests (M16 F03 L08A tuning pass 2)
# ---------------------------------------------------------------------------


def _make_schemas_for_cap_test() -> list[dict[str, Any]]:
    """Build a schema set with a clear name-match / description-only split for 'widget'.

    Single-token query 'widget' (all matches score 1, so the name-vs-description
    class is what differentiates them):
    - 2 NAME matches: 'widget_create', 'widget_delete' — token 'widget' is in the
      tool NAME (descriptions deliberately do NOT contain it).
    - 10 DESCRIPTION-ONLY matches: 'plain_NN' whose description mentions 'widget'
      but whose name does not.
    - Total matches for 'widget': 12 — above _MAX_SEARCH_RESULTS (8).

    New contract: both name matches are guaranteed and ranked first; the
    remaining 6 slots are filled with description-only matches; 4 description-only
    matches are dropped; the reported pre-cap total is 12.
    """
    schemas: list[dict[str, Any]] = [
        _synthetic_schema("widget_create", "create a thing"),  # name match
        _synthetic_schema("widget_delete", "delete a thing"),  # name match
    ]
    for i in range(10):
        schemas.append(_synthetic_schema(f"plain_{i:02d}", f"manages a widget #{i}"))  # desc-only
    return schemas


def test_cap_description_only_matches_capped_total_reported() -> None:
    """When name matches < cap, fill with description-only matches up to the cap.

    12 matches total (2 name + 10 description-only). The result holds exactly
    _MAX_SEARCH_RESULTS (8) tools and the returned pre-cap total is the true 12.
    """
    schemas = _make_schemas_for_cap_test()
    result, total = _filter_candidates(schemas, {}, "widget")
    assert len(result) == _MAX_SEARCH_RESULTS, (
        f"Expected exactly {_MAX_SEARCH_RESULTS} results; got {len(result)}"
    )
    assert total == 12, f"Expected true pre-cap total 12; got {total}"


def test_cap_name_matches_guaranteed_in_results() -> None:
    """Both name matches are always included when the cap is applied."""
    schemas = _make_schemas_for_cap_test()
    result, _ = _filter_candidates(schemas, {}, "widget")
    names = [s["name"] for s in result]
    assert "widget_create" in names and "widget_delete" in names, (
        f"Name matches must be guaranteed in top-{_MAX_SEARCH_RESULTS}; got {names}"
    )


def test_cap_name_matches_rank_first() -> None:
    """Within the capped set, name matches appear before description-only matches."""
    schemas = _make_schemas_for_cap_test()
    result, _ = _filter_candidates(schemas, {}, "widget")
    names = [s["name"] for s in result]
    assert names[:2] == ["widget_create", "widget_delete"], (
        f"Name matches must rank first; got order {names}"
    )
    # Every name match precedes every description-only match.
    last_name_idx = max(names.index("widget_create"), names.index("widget_delete"))
    first_desc_idx = min(i for i, n in enumerate(names) if n.startswith("plain_"))
    assert last_name_idx < first_desc_idx


def test_cap_description_only_beyond_cap_excluded() -> None:
    """A description-only match beyond the cap is dropped (but counted in the total)."""
    schemas = _make_schemas_for_cap_test()
    result, total = _filter_candidates(schemas, {}, "widget")
    result_names = {s["name"] for s in result}
    all_matching = {s["name"] for s in schemas}  # all 12 match
    excluded = all_matching - result_names
    # 4 description-only matches must be excluded; no name match may be excluded.
    assert len(excluded) == 4, f"Expected 4 dropped description-only matches; got {excluded}"
    assert all(n.startswith("plain_") for n in excluded), (
        f"Only description-only matches may be dropped; got {excluded}"
    )
    assert total == 12, "The dropped matches must still be reflected in the true total"


def test_cap_name_matches_exceeding_cap_all_kept() -> None:
    """When name matches alone exceed the cap, ALL of them are kept (cap is a floor)."""
    # 11 tools whose NAME contains 'zone' → 11 name matches, above the cap of 8.
    schemas = [_synthetic_schema(f"zone_tool_{i:02d}", "unrelated text") for i in range(11)]
    result, total = _filter_candidates(schemas, {}, "zone")
    assert len(result) == 11, (
        f"All name matches must be kept even beyond the cap; got {len(result)}"
    )
    assert total == 11


def test_name_match_guaranteed_when_descriptions_fill_cap() -> None:
    """A name match is never pushed out by a wall of description-only matches.

    Mirrors the Sonos bug (F09-01): 10 tools mention 'volume' only in their
    description (would naturally fill the 8 slots), plus one 'set_volume' whose
    NAME hits. The name match must be present AND ranked first.
    """
    schemas = [_synthetic_schema(f"audio_{i:02d}", f"adjusts the volume #{i}") for i in range(10)]
    schemas.append(_synthetic_schema("set_volume", "set the speaker level"))  # name match, last
    result, total = _filter_candidates(schemas, {}, "volume")
    names = [s["name"] for s in result]
    assert "set_volume" in names, "Name match must be guaranteed despite >8 description matches"
    assert names[0] == "set_volume", f"Name match must rank first; got {names}"
    assert len(result) == _MAX_SEARCH_RESULTS
    assert total == 11, f"Expected true pre-cap total 11; got {total}"


def test_empty_query_not_capped_returns_all() -> None:
    """Empty query is exempt from the cap — all non-excluded schemas must be returned.

    We register more than _MAX_SEARCH_RESULTS tools and assert every one appears,
    and that the reported total equals the (uncapped) returned count.
    """
    schemas = [
        _synthetic_schema(f"tool_{i:02d}", f"description {i}")
        for i in range(_MAX_SEARCH_RESULTS + 5)
    ]
    schemas.append(_synthetic_schema("search_tools", "excluded"))
    result, total = _filter_candidates(schemas, {}, "")
    result_names = {s["name"] for s in result}
    assert len(result) > _MAX_SEARCH_RESULTS, (
        f"Empty query must not be capped; expected "
        f">{_MAX_SEARCH_RESULTS} results, got {len(result)}"
    )
    assert total == len(result), "Empty query is never truncated: total == returned"
    assert "search_tools" not in result_names
    for i in range(_MAX_SEARCH_RESULTS + 5):
        assert f"tool_{i:02d}" in result_names, f"tool_{i:02d} missing from empty-query results"


async def test_empty_query_real_registry_not_capped() -> None:
    """Empty query against the real BuiltinToolProvider returns > _MAX_SEARCH_RESULTS tools.

    The built-in catalog has well over 8 tools; the cap must NOT apply.
    """
    registry = _make_registry_with_real_tools()
    st, ls, _ = _make_search_tools(registry=registry)

    await st.execute("")

    assert len(ls) > _MAX_SEARCH_RESULTS, (
        f"Empty query must return all built-ins (>{_MAX_SEARCH_RESULTS}); got {len(ls)}"
    )


def test_format_result_truncated_reports_true_total() -> None:
    """When total > returned, _format_result renders 'N of M' + a recovery hint."""
    matches = [_synthetic_schema(f"t{i}") for i in range(_MAX_SEARCH_RESULTS)]
    result = _format_result(matches, "volume", total=14)
    assert f"Found {_MAX_SEARCH_RESULTS} of 14 tools matching 'volume'" in result
    # The signal must tell a small model how to recover.
    assert "narrow your query or search a specific tool name to see the rest" in result


def test_format_result_not_truncated_no_signal() -> None:
    """When total equals (or is None for) the returned count, no truncation signal."""
    matches = [_synthetic_schema("a"), _synthetic_schema("b")]
    # total omitted (None) → not truncated.
    assert "of" not in _format_result(matches, "q").split(":")[0].split()
    # total == returned → not truncated.
    result = _format_result(matches, "q", total=2)
    assert "narrow your query" not in result
    assert "Found 2 tools matching 'q'" in result


async def test_execute_truncated_query_reports_true_total() -> None:
    """When a non-empty query is truncated, execute() reports the honest 'N of M' total.

    11 tools match 'data' via their DESCRIPTION only (names don't contain it), so
    8 are returned and the true total of 11 must be reported with the recovery hint.
    """
    registry = ToolRegistry()
    total_tools = _MAX_SEARCH_RESULTS + 3  # 11
    for i in range(total_tools):
        registry.register(_MockTool(f"metric_{i:02d}", f"processes data stream #{i}"))

    st, ls, _ = _make_search_tools(registry=registry)
    result = await st.execute("data")

    assert f"{_MAX_SEARCH_RESULTS} of {total_tools}" in result, (
        f"Expected honest 'N of M' total when truncated; got: {result!r}"
    )
    assert "narrow your query or search a specific tool name to see the rest" in result
    assert len(ls) == _MAX_SEARCH_RESULTS


async def test_execute_untruncated_query_no_signal() -> None:
    """When a non-empty query returns fewer than the cap, no truncation signal."""
    registry = ToolRegistry()
    registry.register(_MockTool("unique_frobnicate_tool", "frobnicate widgets"))

    st, ls, _ = _make_search_tools(registry=registry)
    result = await st.execute("frobnicate")

    assert "narrow your query" not in result
    assert " of " not in result
    assert len(ls) == 1
