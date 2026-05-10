"""F10 L3: Tests for the real SearchMcps implementation.

Covers:
- filter_mcp_tools_by_override helper (shared with MCPToolProvider)
- _build_synthetic_description pure function (two-pass truncation logic)
- _filter_mcp_candidates pure function (source-level + per-tool match, dedup)
- SearchMcps.execute paths (empty query, source match, per-tool match,
  no-match, no-attached-sources, excludes non-mcp tools)
- Idempotency (repeated execute calls don't grow loaded_schemas)
- Factory integration wiring (SearchMcps, not SearchMcpsStub)
- No-cache source: logged at WARNING and skipped from source_index
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from the_one.agent.config import AgentConfig
from the_one.db.models import MCPSource
from the_one.mcp._tool_provider import filter_mcp_tools_by_override
from the_one.mcp.types import MCPTool
from the_one.tools._search_mcps import (
    SearchMcps,
    _build_synthetic_description,
    _filter_mcp_candidates,
)
from the_one.tools._search_stubs import SearchMcpsStub
from the_one.tools.base import Tool, ToolRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mcp_tool(
    name: str,
    description: str = "",
    input_schema: dict | None = None,
) -> MCPTool:
    return MCPTool(
        name=name,
        description=description,
        input_schema=(
            input_schema
            if input_schema is not None
            else {"type": "object", "properties": {}}
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


def _make_schema(name: str, description: str = "") -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "parameters": {"type": "object", "properties": {}, "required": []},
    }


class _MockTool(Tool):
    """Minimal Tool subclass for synthetic registry tests."""

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


def _make_on_match(
    loaded_schemas: list[dict],
    loaded_tool_names: set[str],
) -> Any:
    """Replicate the _on_search_match closure from factory.py."""

    def _on_match(schemas: list[dict]) -> None:
        for s in schemas:
            if s["name"] not in loaded_tool_names:
                loaded_schemas.append(s)
                loaded_tool_names.add(s["name"])

    return _on_match


def _make_search_mcps(
    mcp_tools: list[tuple[str, str]] | None = None,
    source_index: dict[str, Any] | None = None,
    loaded_schemas: list[dict] | None = None,
    loaded_tool_names: set[str] | None = None,
    agent_name: str | None = "test",
) -> tuple[SearchMcps, ToolRegistry, list[dict], set[str]]:
    """Build a SearchMcps with a synthetic registry and source_index."""
    registry = ToolRegistry()
    if mcp_tools:
        for tool_name, desc in mcp_tools:
            registry.register(_MockTool(tool_name, desc))

    ls: list[dict] = loaded_schemas if loaded_schemas is not None else []
    ltn: set[str] = loaded_tool_names if loaded_tool_names is not None else set()
    on_match = _make_on_match(ls, ltn)
    idx = source_index if source_index is not None else {}
    sm = SearchMcps(
        on_match=on_match,
        registry=registry,
        source_index=idx,
        agent_name=agent_name,
    )
    return sm, registry, ls, ltn


def _make_provider_config_for_factory():
    from the_one.db.models import LLMProviderConfig

    return LLMProviderConfig(
        id="test-provider",
        name="Test Provider",
        type="ollama",
        base_url="http://localhost:11434/v1",
    )


# ---------------------------------------------------------------------------
# Tests: filter_mcp_tools_by_override
# ---------------------------------------------------------------------------


async def test_filter_mcp_tools_by_override_no_payload() -> None:
    """None / empty payload → all tools returned unchanged."""
    tools = [_make_mcp_tool("foo"), _make_mcp_tool("bar")]
    src = _make_source()

    result_none = filter_mcp_tools_by_override(tools, src, None)
    result_empty = filter_mcp_tools_by_override(tools, src, {})

    assert result_none == tools
    assert result_empty == tools


async def test_filter_mcp_tools_by_override_enabled_tools_whitelist() -> None:
    """payload with enabled_tools=['foo'] returns only foo."""
    tools = [_make_mcp_tool("foo"), _make_mcp_tool("bar"), _make_mcp_tool("baz")]
    src = _make_source(source_type="stdio")
    payload = {"enabled_tools": ["foo"]}

    result = filter_mcp_tools_by_override(tools, src, payload)

    assert [t.name for t in result] == ["foo"]


async def test_filter_mcp_tools_by_override_disabled_tools_subtract() -> None:
    """payload with disabled_tools=['foo'] excludes foo, returns rest."""
    tools = [_make_mcp_tool("foo"), _make_mcp_tool("bar"), _make_mcp_tool("baz")]
    src = _make_source(source_type="stdio")
    payload = {"disabled_tools": ["foo"]}

    result = filter_mcp_tools_by_override(tools, src, payload)

    assert [t.name for t in result] == ["bar", "baz"]


async def test_filter_mcp_tools_by_override_stdio_vs_http() -> None:
    """Same enabled_tools semantics on both transports (stdio + streamable-http)."""
    tools = [_make_mcp_tool("alpha"), _make_mcp_tool("beta")]
    payload = {"enabled_tools": ["alpha"]}

    src_stdio = _make_source(source_type="stdio")
    src_http = _make_source(source_type="streamable-http")

    result_stdio = filter_mcp_tools_by_override(tools, src_stdio, payload)
    result_http = filter_mcp_tools_by_override(tools, src_http, payload)

    assert [t.name for t in result_stdio] == ["alpha"]
    assert [t.name for t in result_http] == ["alpha"]


# ---------------------------------------------------------------------------
# Tests: _build_synthetic_description
# ---------------------------------------------------------------------------


async def test_build_synthetic_description_basic() -> None:
    """3-tool source builds 'foo: a, b, c (3 tools)'."""
    result = _build_synthetic_description("foo", ["a", "b", "c"])
    assert result == "foo: a, b, c (3 tools)"


async def test_build_synthetic_description_empty_tools() -> None:
    """0-tool source builds 'foo: (no cached tools)'."""
    result = _build_synthetic_description("foo", [])
    assert result == "foo: (no cached tools)"


async def test_build_synthetic_description_truncation() -> None:
    """50-tool source: description ≤200 chars, ends with '...' and '(50 tools)'."""
    # Build 50 tools with short predictable names.
    tool_names = [f"tool_{i:02d}" for i in range(50)]
    result = _build_synthetic_description("my_source", tool_names)

    assert len(result) <= 200, f"Expected ≤200 chars, got {len(result)}: {result!r}"
    assert "..." in result, "Expected truncation ellipsis"
    assert "(50 tools)" in result, "Expected count suffix"
    assert result.startswith("my_source: "), "Expected source name prefix"


async def test_build_synthetic_description_fits_exactly() -> None:
    """Verify the two-pass logic: a list that JUST fits is not truncated."""
    # Construct a list that fills available space exactly.
    # char_cap=200, prefix="src: " (5), suffix=" (1 tools)" (10)
    # available = 200 - 5 - 10 = 185 chars for the body.
    # One tool name of exactly 185 chars should fit without truncation.
    long_name = "x" * 185
    result = _build_synthetic_description("src", [long_name], char_cap=200)
    # Should NOT contain "..." since it fits exactly.
    assert "..." not in result
    assert result == f"src: {long_name} (1 tools)"


async def test_build_synthetic_description_boundary_no_spurious_truncation() -> None:
    """Boundary: last name fits exactly → should NOT get spurious '...'."""
    # With char_cap=20: prefix="s: " (3), suffix=" (2 tools)" (10)
    # available = 20 - 3 - 10 = 7 chars for body.
    # "a, b" = 4 chars — fits. Should produce "s: a, b (2 tools)" = 18 chars.
    result = _build_synthetic_description("s", ["a", "b"], char_cap=20)
    assert "..." not in result
    assert result == "s: a, b (2 tools)"


# ---------------------------------------------------------------------------
# Tests: _filter_mcp_candidates
# ---------------------------------------------------------------------------


async def test_filter_mcp_candidates_empty_query_returns_all_mcp() -> None:
    """Empty query returns all mcp__-prefixed schemas."""
    schemas = [
        _make_schema("mcp__foo__a"),
        _make_schema("mcp__foo__b"),
        _make_schema("read_file"),  # non-mcp; excluded
    ]
    result = _filter_mcp_candidates(schemas, {}, "")
    result_names = {s["name"] for s in result}
    assert result_names == {"mcp__foo__a", "mcp__foo__b"}
    assert "read_file" not in result_names


async def test_filter_mcp_candidates_source_level_match() -> None:
    """Query matches a source name → returns ALL of that source's tools."""
    schemas = [
        _make_schema("mcp__cloudflare__list_zones"),
        _make_schema("mcp__cloudflare__get_zone"),
        _make_schema("mcp__github__get_repo"),
    ]
    source_index = {
        "cloudflare": {
            "synthetic_description": "cloudflare: list_zones, get_zone (2 tools)",
            "tool_names_prefixed": ["mcp__cloudflare__list_zones", "mcp__cloudflare__get_zone"],
        },
        "github": {
            "synthetic_description": "github: get_repo (1 tools)",
            "tool_names_prefixed": ["mcp__github__get_repo"],
        },
    }

    result = _filter_mcp_candidates(schemas, source_index, "cloudflare")
    result_names = {s["name"] for s in result}
    assert result_names == {"mcp__cloudflare__list_zones", "mcp__cloudflare__get_zone"}
    assert "mcp__github__get_repo" not in result_names


async def test_filter_mcp_candidates_per_tool_match() -> None:
    """Query matches a per-tool description → returns just the matched tool."""
    schemas = [
        _make_schema("mcp__foo__get_widget", description="Retrieve a widget by ID"),
        _make_schema("mcp__foo__list_widgets", description="List all widgets"),
        _make_schema("mcp__foo__delete_widget", description="Delete a widget"),
    ]
    source_index = {
        "foo": {
            "synthetic_description": "foo: get_widget, list_widgets, delete_widget (3 tools)",
            "tool_names_prefixed": [
                "mcp__foo__get_widget",
                "mcp__foo__list_widgets",
                "mcp__foo__delete_widget",
            ],
        }
    }

    result = _filter_mcp_candidates(schemas, source_index, "retrieve")
    result_names = {s["name"] for s in result}
    assert result_names == {"mcp__foo__get_widget"}


async def test_filter_mcp_candidates_dedup() -> None:
    """Source-level + per-tool match for same tool → appears once."""
    schemas = [_make_schema("mcp__cloudflare__list_zones", description="list cloudflare zones")]
    source_index = {
        "cloudflare": {
            "synthetic_description": "cloudflare: list_zones (1 tools)",
            "tool_names_prefixed": ["mcp__cloudflare__list_zones"],
        }
    }
    # "cloudflare" matches source AND tool name AND description.
    result = _filter_mcp_candidates(schemas, source_index, "cloudflare")
    assert len(result) == 1
    assert result[0]["name"] == "mcp__cloudflare__list_zones"


# ---------------------------------------------------------------------------
# Tests: SearchMcps.execute
# ---------------------------------------------------------------------------


async def test_search_mcps_empty_query_returns_all() -> None:
    """Empty query returns ALL mcp__-prefixed schemas; mutates loaded_schemas."""
    mcp_tools = [
        ("mcp__foo__a", "foo tool a"),
        ("mcp__foo__b", "foo tool b"),
        ("mcp__bar__c", "bar tool c"),
    ]
    source_index = {
        "foo": {
            "synthetic_description": "foo: a, b (2 tools)",
            "tool_names_prefixed": ["mcp__foo__a", "mcp__foo__b"],
        },
        "bar": {
            "synthetic_description": "bar: c (1 tools)",
            "tool_names_prefixed": ["mcp__bar__c"],
        },
    }
    sm, _, ls, _ = _make_search_mcps(mcp_tools=mcp_tools, source_index=source_index)

    result = await sm.execute("")

    assert result.startswith("Found 3 MCP tools:")
    assert len(ls) == 3
    loaded_names = {s["name"] for s in ls}
    assert loaded_names == {"mcp__foo__a", "mcp__foo__b", "mcp__bar__c"}


async def test_search_mcps_query_matches_source_name() -> None:
    """Query matching a source name returns ALL tools from that source."""
    mcp_tools = [
        ("mcp__cloudflare__list_zones", "list zones"),
        ("mcp__cloudflare__get_zone", "get zone"),
        ("mcp__github__get_repo", "get repo"),
    ]
    source_index = {
        "cloudflare": {
            "synthetic_description": "cloudflare: list_zones, get_zone (2 tools)",
            "tool_names_prefixed": ["mcp__cloudflare__list_zones", "mcp__cloudflare__get_zone"],
        },
        "github": {
            "synthetic_description": "github: get_repo (1 tools)",
            "tool_names_prefixed": ["mcp__github__get_repo"],
        },
    }
    sm, _, ls, _ = _make_search_mcps(mcp_tools=mcp_tools, source_index=source_index)

    result = await sm.execute("cloudflare")

    loaded_names = {s["name"] for s in ls}
    assert "mcp__cloudflare__list_zones" in loaded_names
    assert "mcp__cloudflare__get_zone" in loaded_names
    assert "mcp__github__get_repo" not in loaded_names
    assert "cloudflare" in result
    assert "Found 2" in result


async def test_search_mcps_query_matches_per_tool() -> None:
    """Query matching a per-tool description (but NOT source name/description) returns just that tool.

    The source_index here does NOT include the query word in the synthetic
    description or source name, so only per-tool matching fires.
    """
    mcp_tools = [
        ("mcp__myapi__alpha_tool", "Frobnicate the alpha resource"),
        ("mcp__myapi__beta_tool", "Manage beta resources"),
    ]
    # Synthetic description uses short names 'alpha_tool' and 'beta_tool'.
    # Query 'frobnicate' appears ONLY in alpha_tool's description (per-tool match).
    source_index = {
        "myapi": {
            "synthetic_description": "myapi: alpha_tool, beta_tool (2 tools)",
            "tool_names_prefixed": ["mcp__myapi__alpha_tool", "mcp__myapi__beta_tool"],
        }
    }
    sm, _, ls, _ = _make_search_mcps(mcp_tools=mcp_tools, source_index=source_index)

    result = await sm.execute("frobnicate")

    loaded_names = {s["name"] for s in ls}
    assert "mcp__myapi__alpha_tool" in loaded_names
    assert "mcp__myapi__beta_tool" not in loaded_names
    assert "Found 1" in result


async def test_search_mcps_query_matches_synthetic_description() -> None:
    """Query matching text in the synthetic description returns the source's tools."""
    mcp_tools = [
        ("mcp__myapi__create_widget", "Create a widget"),
        ("mcp__myapi__delete_widget", "Delete a widget"),
    ]
    # The synthetic description contains "widget" — a word from the tool names.
    source_index = {
        "myapi": {
            "synthetic_description": "myapi: create_widget, delete_widget (2 tools)",
            "tool_names_prefixed": ["mcp__myapi__create_widget", "mcp__myapi__delete_widget"],
        }
    }
    sm, _, ls, _ = _make_search_mcps(mcp_tools=mcp_tools, source_index=source_index)

    result = await sm.execute("widget")

    loaded_names = {s["name"] for s in ls}
    assert "mcp__myapi__create_widget" in loaded_names
    assert "mcp__myapi__delete_widget" in loaded_names
    assert "Found 2" in result


async def test_search_mcps_no_match_returns_helpful_text() -> None:
    """Query 'xyzzy' returns exact no-match string; does NOT mutate loaded_schemas."""
    mcp_tools = [("mcp__foo__bar", "foo bar tool")]
    source_index = {
        "foo": {
            "synthetic_description": "foo: bar (1 tools)",
            "tool_names_prefixed": ["mcp__foo__bar"],
        }
    }
    sm, _, ls, _ = _make_search_mcps(mcp_tools=mcp_tools, source_index=source_index)

    result = await sm.execute("xyzzy")

    assert result == "No MCP tools found matching 'xyzzy'."
    assert len(ls) == 0  # loaded_schemas unchanged


async def test_search_mcps_excludes_non_mcp_tools() -> None:
    """Registry contains read_file (built-in) and mcp__foo__bar; query 'read' returns nothing."""
    registry = ToolRegistry()
    registry.register(_MockTool("read_file", "Read the contents of a file"))
    registry.register(_MockTool("mcp__foo__bar", "bar tool"))

    ls: list[dict] = []
    ltn: set[str] = set()
    on_match = _make_on_match(ls, ltn)
    sm = SearchMcps(
        on_match=on_match,
        registry=registry,
        source_index={
            "foo": {
                "synthetic_description": "foo: bar (1 tools)",
                "tool_names_prefixed": ["mcp__foo__bar"],
            }
        },
        agent_name="test",
    )

    result = await sm.execute("read")

    # read_file is built-in, not mcp__-prefixed → excluded
    assert result == "No MCP tools found matching 'read'."
    assert len(ls) == 0


async def test_search_mcps_no_attached_mcps_returns_helpful_message() -> None:
    """Empty registry + empty source_index → 'No MCP sources are attached.'."""
    sm, _, ls, _ = _make_search_mcps(mcp_tools=[], source_index={})

    result = await sm.execute("")

    assert result == "No MCP sources are attached to this agent."
    assert len(ls) == 0


async def test_search_mcps_idempotent_on_repeated_calls() -> None:
    """Repeated execute() calls with same query don't grow loaded_schemas."""
    mcp_tools = [
        ("mcp__foo__a", "a"),
        ("mcp__foo__b", "b"),
    ]
    source_index = {
        "foo": {
            "synthetic_description": "foo: a, b (2 tools)",
            "tool_names_prefixed": ["mcp__foo__a", "mcp__foo__b"],
        }
    }
    sm, _, ls, ltn = _make_search_mcps(mcp_tools=mcp_tools, source_index=source_index)

    await sm.execute("")
    count_after_first = len(ls)
    assert count_after_first == 2

    await sm.execute("")
    assert len(ls) == count_after_first  # no growth on second call
    assert len(ltn) == count_after_first


# ---------------------------------------------------------------------------
# Test: factory wiring — SearchMcps (NOT SearchMcpsStub) in registry
# ---------------------------------------------------------------------------


async def test_real_impl_in_factory_wiring() -> None:
    """AgentFactory.create() registers SearchMcps, not SearchMcpsStub, under 'search_mcps'."""
    from the_one.agent.factory import AgentFactory

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

    mock_llm_repo = AsyncMock()
    mock_llm_repo.get = AsyncMock(return_value=_make_provider_config_for_factory())
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
        patch("the_one.db.repositories.LLMProviderRepository", return_value=mock_llm_repo),
        patch("the_one.db.repositories.ToolConfigRepository", return_value=mock_tool_repo),
    ):
        mock_settings.agents_dir = Path("/tmp/test-agents")
        mock_settings.data_dir = Path("/tmp/test-data")
        mock_settings.ensure_dirs = lambda: None

        factory = AgentFactory(store=_InMemoryStore())
        agent = await factory.create("wiring-test")

    search_mcp_tool = agent.tools.get("search_mcps")
    assert isinstance(search_mcp_tool, SearchMcps), (
        f"Expected SearchMcps, got {type(search_mcp_tool).__name__}"
    )
    assert not isinstance(search_mcp_tool, SearchMcpsStub), (
        "search_mcps should be real SearchMcps, not SearchMcpsStub"
    )


# ---------------------------------------------------------------------------
# Test: no-cache source logged and skipped from source_index
# ---------------------------------------------------------------------------


async def test_search_mcps_no_cache_source_logged_and_skipped(caplog: Any) -> None:
    """MCP source with empty _cache.tools: WARNING logged; NOT in source_index."""
    from the_one.agent.factory import AgentFactory, _build_source_index

    # Build a source with no cached tools.
    source_no_cache = _make_source(
        source_id="src-empty",
        name="empty_source",
        source_type="stdio",
        config={},  # no _cache key → empty tools
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

    # Source with no cached tools must NOT appear in source_index.
    assert "empty_source" not in source_index
    assert source_index == {}

    # WARNING must have been logged.
    assert any(
        "empty_source" in rec.getMessage() and "no cached tools" in rec.getMessage()
        for rec in caplog.records
    ), f"Expected WARNING about no cached tools; got records: {[r.getMessage() for r in caplog.records]}"


# ---------------------------------------------------------------------------
# Test: no-cache source: search returns nothing for it
# ---------------------------------------------------------------------------


async def test_search_mcps_no_cache_source_not_in_search_results() -> None:
    """Source absent from source_index (no cache) does NOT appear in search results."""
    # Only mcp__legit__tool is registered; source_index has no entry for "nocache"
    sm, _, ls, _ = _make_search_mcps(
        mcp_tools=[("mcp__legit__tool", "a tool")],
        source_index={
            "legit": {
                "synthetic_description": "legit: tool (1 tools)",
                "tool_names_prefixed": ["mcp__legit__tool"],
            }
        },
    )

    result = await sm.execute("nocache")

    assert "No MCP tools found" in result
    assert len(ls) == 0
