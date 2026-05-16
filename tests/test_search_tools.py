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
    SearchTools,
    _build_synthetic_description,
    _filter_candidates,
    _format_result,
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

    assert _filter_candidates([], source_index, "alpha") == []

    # Empty query → returns all except search_tools.
    result = _filter_candidates(schemas, source_index, "")
    names = {s["name"] for s in result}
    assert names == {"alpha", "beta", "mcp__foo__bar"}

    # Substring match on built-in name.
    result = _filter_candidates(schemas, source_index, "alpha")
    assert [s["name"] for s in result] == ["alpha"]

    # Source-level match pulls in the MCP tool.
    result = _filter_candidates(schemas, source_index, "foo")
    assert [s["name"] for s in result] == ["mcp__foo__bar"]

    # search_tools is always excluded.
    result = _filter_candidates(schemas, source_index, "search")
    names = {s["name"] for s in result}
    assert "search_tools" not in names

    # Case-insensitive.
    assert _filter_candidates(schemas, source_index, "ALPHA") == _filter_candidates(
        schemas, source_index, "alpha"
    )

    # Missing description → empty-string haystack.
    schemas_no_desc = [{"name": "my_tool"}]
    result = _filter_candidates(schemas_no_desc, {}, "my")
    assert len(result) == 1


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
    assert "Found 2 tools:" in result
    assert "built-in: " in result


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
