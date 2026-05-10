"""F10 L2: Tests for the real SearchTools implementation.

Covers filter logic, substring matching, case-insensitivity, exclusion rules,
on_match callback mutation, idempotency, pure helper function, and factory
integration wiring.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from the_one.agent.config import AgentConfig
from the_one.agent.factory import AgentFactory
from the_one.tools._search_stubs import SearchToolsStub
from the_one.tools._search_tools import SearchTools, _filter_candidates
from the_one.tools.base import Tool, ToolRegistry
from the_one.tools.builtins import BuiltinToolProvider

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_registry_with_real_tools(
    agent_name: str = "test",
) -> ToolRegistry:
    """Build a ToolRegistry populated by BuiltinToolProvider (factory path).

    Mirrors factory.py:178-181 under default conditions (no disabled tools,
    no per-agent overrides). Does NOT register search_tools or search_mcps
    (those are registered separately in production; tests that need them can
    add them manually).
    """
    provider = BuiltinToolProvider()
    registry = ToolRegistry()
    for tool in provider.get_tools({}, {}, agent_name=agent_name):
        registry.register(tool)
    return registry


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


def _make_search_tools(
    registry: ToolRegistry | None = None,
    loaded_schemas: list[dict] | None = None,
    loaded_tool_names: set[str] | None = None,
    agent_name: str | None = "test",
) -> tuple[SearchTools, list[dict], set[str]]:
    """Construct a SearchTools wired to shared containers."""
    if registry is None:
        registry = _make_registry_with_real_tools(agent_name or "test")
    ls: list[dict] = loaded_schemas if loaded_schemas is not None else []
    ltn: set[str] = loaded_tool_names if loaded_tool_names is not None else set()
    on_match = _make_on_match(ls, ltn)
    st = SearchTools(on_match=on_match, registry=registry, agent_name=agent_name)
    return st, ls, ltn


def _make_provider_config_for_factory():
    from the_one.db.models import LLMProviderConfig

    return LLMProviderConfig(
        id="test-provider",
        name="Test Provider",
        type="ollama",
        base_url="http://localhost:11434/v1",
    )


# ---------------------------------------------------------------------------
# Synthetic-registry helpers for filter-rule isolation
# ---------------------------------------------------------------------------


def _synthetic_schema(
    name: str, description: str = ""
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "parameters": {"type": "object", "properties": {}, "required": []},
    }


# ---------------------------------------------------------------------------
# Test 1: empty query returns all filtered built-in tools
# ---------------------------------------------------------------------------


async def test_empty_query_returns_all_filtered() -> None:
    """Empty query returns all built-in tools (excluding search_tools, search_mcps, mcp__*)."""
    registry = _make_registry_with_real_tools()
    st, ls, _ = _make_search_tools(registry=registry)

    result = await st.execute("")

    # Must have found tools
    assert result.startswith("Found ")
    assert "tools:" in result

    # loaded_schemas must contain entries
    assert len(ls) > 0

    # None of the excluded names must appear
    loaded_names = {s["name"] for s in ls}
    assert "search_tools" not in loaded_names
    assert "search_mcps" not in loaded_names
    for n in loaded_names:
        assert not n.startswith("mcp__"), f"mcp__-prefixed tool leaked: {n!r}"

    # Expected built-in tools should be present
    assert "read_file" in loaded_names
    assert "write_file" in loaded_names
    assert "shell" in loaded_names


# ---------------------------------------------------------------------------
# Test 2: substring match on name — "shell" returns shell + shell_session_*
# ---------------------------------------------------------------------------


async def test_query_substring_match_on_name() -> None:
    """Query 'shell' returns shell, shell_session_start/send/close/list."""
    registry = _make_registry_with_real_tools()
    st, ls, _ = _make_search_tools(registry=registry)

    result = await st.execute("shell")

    loaded_names = {s["name"] for s in ls}
    assert "shell" in loaded_names
    assert "shell_session_start" in loaded_names
    assert "shell_session_send" in loaded_names
    assert "shell_session_close" in loaded_names
    assert "shell_session_list" in loaded_names

    # Non-shell tools that don't mention "shell" must NOT appear
    assert "read_file" not in loaded_names
    # python_exec legitimately matches: its description contains the word "shell"
    # (it mentions `shell` and `shell_session_send` as alternatives). This is
    # correct substring-match behavior.

    assert result.startswith("Found ")
    assert "'shell'" in result


# ---------------------------------------------------------------------------
# Test 3: substring match on description — "contents" matches read_file
# ---------------------------------------------------------------------------


async def test_query_substring_match_on_description() -> None:
    """Query 'contents' matches read_file (description: 'Read the contents of a file.')."""
    registry = _make_registry_with_real_tools()
    st, ls, _ = _make_search_tools(registry=registry)

    result = await st.execute("contents")

    loaded_names = {s["name"] for s in ls}
    # 'read_file' description contains 'contents'
    assert "read_file" in loaded_names
    assert result.startswith("Found ")


# ---------------------------------------------------------------------------
# Test 4: case-insensitive query — "SHELL" == "shell"
# ---------------------------------------------------------------------------


async def test_query_case_insensitive() -> None:
    """Query 'SHELL' returns the same set as 'shell'."""
    registry = _make_registry_with_real_tools()
    st_lower, ls_lower, _ = _make_search_tools(registry=registry)
    await st_lower.execute("shell")

    registry2 = _make_registry_with_real_tools()
    st_upper, ls_upper, _ = _make_search_tools(registry=registry2)
    await st_upper.execute("SHELL")

    assert {s["name"] for s in ls_lower} == {s["name"] for s in ls_upper}


# ---------------------------------------------------------------------------
# Test 5: no-match returns helpful text, does NOT mutate loaded_schemas
# ---------------------------------------------------------------------------


async def test_no_match_returns_helpful_text() -> None:
    """Query 'xyzzy_nonexistent' returns the exact no-match string; loaded_schemas unchanged."""
    registry = _make_registry_with_real_tools()
    st, ls, _ = _make_search_tools(registry=registry)

    result = await st.execute("xyzzy_nonexistent")

    assert result == "No tools found matching 'xyzzy_nonexistent'."
    # loaded_schemas must NOT have been mutated
    assert len(ls) == 0


# ---------------------------------------------------------------------------
# Test 6: search_tools and search_mcps are excluded from results
# ---------------------------------------------------------------------------


async def test_excludes_search_tools_from_results() -> None:
    """Query 'search' does NOT return search_tools or search_mcps."""
    # Build a registry that INCLUDES search_tools and search_mcps (synthetic)
    registry = ToolRegistry()
    # Add real built-ins
    for tool in BuiltinToolProvider().get_tools({}, {}, agent_name="test"):
        registry.register(tool)
    # Add search stubs to the registry so they're present during iteration
    from the_one.tools._search_stubs import SearchMcpsStub, SearchToolsStub

    loaded_schemas: list[dict] = []
    loaded_tool_names: set[str] = set()
    on_match_inner = _make_on_match(loaded_schemas, loaded_tool_names)
    registry.register(SearchToolsStub(on_match=on_match_inner))
    registry.register(SearchMcpsStub(on_match=on_match_inner))

    st, ls, _ = _make_search_tools(registry=registry)
    await st.execute("search")

    loaded_names = {s["name"] for s in ls}
    assert "search_tools" not in loaded_names
    assert "search_mcps" not in loaded_names


# ---------------------------------------------------------------------------
# Test 7: mcp__-prefixed tools are excluded from results
# ---------------------------------------------------------------------------


async def test_excludes_mcp_prefixed_tools_from_results() -> None:
    """Synthetic registry with mcp__foo__bar; query 'foo' returns nothing."""
    registry = ToolRegistry()
    # A minimal fake MCP tool
    fake_mcp = _MockTool("mcp__foo__bar", "foo bar description")
    registry.register(fake_mcp)

    st, ls, _ = _make_search_tools(registry=registry)
    result = await st.execute("foo")

    assert result == "No tools found matching 'foo'."
    assert len(ls) == 0


# ---------------------------------------------------------------------------
# Test 8: on_match callback receives matched schemas (mutation test)
# ---------------------------------------------------------------------------


async def test_mutates_loaded_schemas_via_on_match() -> None:
    """execute('file') mutates shared container with matched schemas."""
    registry = _make_registry_with_real_tools()
    st, ls, ltn = _make_search_tools(registry=registry)

    assert len(ls) == 0
    await st.execute("file")

    assert len(ls) > 0
    loaded_names = {s["name"] for s in ls}
    # 'file' should match read_file, write_file, edit_file, delete_file, move_file
    assert "read_file" in loaded_names
    assert "write_file" in loaded_names
    # loaded_tool_names mirrors loaded_schemas
    assert loaded_names == ltn


# ---------------------------------------------------------------------------
# Test 9: idempotency — repeated calls with same query don't grow loaded_schemas
# ---------------------------------------------------------------------------


async def test_idempotent_on_repeated_calls() -> None:
    """Calling execute('file') twice doesn't double-count matched schemas."""
    registry = _make_registry_with_real_tools()
    st, ls, ltn = _make_search_tools(registry=registry)

    await st.execute("file")
    count_after_first = len(ls)
    assert count_after_first > 0

    await st.execute("file")
    assert len(ls) == count_after_first  # no growth on second call
    assert len(ltn) == count_after_first


# ---------------------------------------------------------------------------
# Test 10: pure helper function _filter_candidates
# ---------------------------------------------------------------------------


async def test_filter_helper_pure_function() -> None:
    """Unit-test _filter_candidates independently of registry/agent state."""
    schemas = [
        _synthetic_schema("alpha", "alpha tool description"),
        _synthetic_schema("beta", "beta tool description"),
        _synthetic_schema("search_tools", "search tool description"),
        _synthetic_schema("search_mcps", "search mcps description"),
        _synthetic_schema("mcp__foo__bar", "foo bar mcp description"),
    ]

    # Empty schemas list → empty result
    assert _filter_candidates([], "alpha") == []

    # Empty query → returns all except excluded names
    result = _filter_candidates(schemas, "")
    result_names = {s["name"] for s in result}
    assert "alpha" in result_names
    assert "beta" in result_names
    assert "search_tools" not in result_names
    assert "search_mcps" not in result_names
    assert "mcp__foo__bar" not in result_names

    # Substring match on name
    result = _filter_candidates(schemas, "alpha")
    assert len(result) == 1
    assert result[0]["name"] == "alpha"

    # Substring match on description
    result = _filter_candidates(schemas, "beta tool")
    assert len(result) == 1
    assert result[0]["name"] == "beta"

    # Exclusion: search_tools excluded even if query matches
    result = _filter_candidates(schemas, "search")
    result_names = {s["name"] for s in result}
    assert "search_tools" not in result_names
    assert "search_mcps" not in result_names

    # Exclusion: mcp__ prefix excluded
    result = _filter_candidates(schemas, "foo")
    assert result == []

    # Case-insensitive
    result_lower = _filter_candidates(schemas, "alpha")
    result_upper = _filter_candidates(schemas, "ALPHA")
    assert result_lower == result_upper

    # Missing description falls back to empty string (name-only haystack)
    schemas_no_desc = [{"name": "my_tool"}]
    result = _filter_candidates(schemas_no_desc, "my")
    assert len(result) == 1
    assert result[0]["name"] == "my_tool"


# ---------------------------------------------------------------------------
# Test 11: factory wiring — SearchTools (NOT SearchToolsStub) in registry
# ---------------------------------------------------------------------------


async def test_real_impl_in_factory_wiring() -> None:
    """AgentFactory.create() registers SearchTools, not SearchToolsStub, under 'search_tools'."""
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
    assert isinstance(search_tool, SearchTools), (
        f"Expected SearchTools, got {type(search_tool).__name__}"
    )
    assert not isinstance(search_tool, SearchToolsStub), (
        "search_tools should be real SearchTools, not SearchToolsStub"
    )


# ---------------------------------------------------------------------------
# Test 12: per-agent filter applied at registry level
# ---------------------------------------------------------------------------


async def test_real_impl_per_agent_filter_applied_at_registry_level() -> None:
    """With enabled_tools=['read_file', 'write_file'], empty-query search returns only those two."""
    from the_one.agent.factory import AgentFactory

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

    # The registry has search_tools + search_mcps + read_file + write_file only
    registry_names = set(agent.tools.tool_names)
    assert "read_file" in registry_names
    assert "write_file" in registry_names
    assert "search_tools" in registry_names
    assert "search_mcps" in registry_names
    # All other built-ins excluded by enabled_tools filter
    assert "shell" not in registry_names
    assert "python_exec" not in registry_names

    # Now exercise SearchTools.execute("") — should return only read_file + write_file
    search_tool = agent.tools.get("search_tools")
    assert isinstance(search_tool, SearchTools)

    loaded_schemas: list[dict] = agent._loaded_schemas
    initial_count = len(loaded_schemas)

    result = await search_tool.execute("")

    new_schemas = loaded_schemas[initial_count:]
    loaded_names = {s["name"] for s in new_schemas}

    # Only these two built-ins pass the registry-level filter
    assert loaded_names == {"read_file", "write_file"}
    # Verify result text
    assert "Found 2 tools:" in result


# ---------------------------------------------------------------------------
# Minimal mock tool for synthetic registry tests
# ---------------------------------------------------------------------------


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
