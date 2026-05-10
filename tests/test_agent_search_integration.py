"""F10 L4: End-to-end integration tests for the lazy tool discovery protocol.

Tests in this file drive the full search → load → call sequence via a
scripted FakeLLM provider, verifying that:
- The agent's baseline tools= array contains exactly the 2-tool surface.
- Searching loads matching schemas into subsequent iterations' tools= arrays.
- Loaded schemas persist across user turns within a session.
- No-match searches do not add anything to the loaded set.
- BASE_PROMPT contains the Tool discovery section before Tool use.
"""

from __future__ import annotations

from typing import Any

import pytest

from conftest import FakeLLM, StubTool
from the_one.agent.core import Agent, CONTINUE_SCHEMA, SEARCH_MCPS_SCHEMA, SEARCH_TOOLS_SCHEMA
from the_one.llm.base import Message, Role, ToolCall
from the_one.tools._search_tools import SearchTools
from the_one.tools._search_mcps import SearchMcps
from the_one.tools.base import Tool, ToolRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_registry(*tools: Tool) -> ToolRegistry:
    reg = ToolRegistry()
    for t in tools:
        reg.register(t)
    return reg


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
    registry: ToolRegistry,
    loaded_schemas: list[dict],
    loaded_tool_names: set[str],
    agent_name: str = "test",
) -> SearchTools:
    on_match = _make_on_match(loaded_schemas, loaded_tool_names)
    return SearchTools(on_match=on_match, registry=registry, agent_name=agent_name)


class _MockMcpTool(Tool):
    """Minimal Tool to stand in for an MCP tool in the registry."""

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
        return f"mcp-result: {self.name}"


def _make_search_mcps(
    mcp_tools: list[tuple[str, str]],
    source_index: dict[str, Any],
    loaded_schemas: list[dict],
    loaded_tool_names: set[str],
    agent_name: str = "test",
) -> tuple[SearchMcps, ToolRegistry]:
    """Build a SearchMcps with a synthetic MCP registry and source_index."""
    registry = ToolRegistry()
    for tool_name, desc in mcp_tools:
        registry.register(_MockMcpTool(tool_name, desc))

    on_match = _make_on_match(loaded_schemas, loaded_tool_names)
    sm = SearchMcps(
        on_match=on_match,
        registry=registry,
        source_index=source_index,
        agent_name=agent_name,
    )
    return sm, registry


async def _collect(agent: Agent, user_input: str) -> list[Message]:
    msgs: list[Message] = []
    async for m in agent.step(user_input):
        msgs.append(m)
    return msgs


def _schema_names(schemas: list[dict] | None) -> list[str]:
    if schemas is None:
        return []
    return [s["name"] for s in schemas]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_base_prompt_includes_discovery_section() -> None:
    """L4: BASE_PROMPT must teach the lazy-discovery protocol.

    If this test fails after a future edit, the discovery section was
    removed — either reinstate it or update F10's design contract.
    """
    from the_one.agent.config import BASE_PROMPT

    assert "search_tools" in BASE_PROMPT
    assert "search_mcps" in BASE_PROMPT
    assert "Tool discovery" in BASE_PROMPT
    # Order lock: discovery section must appear BEFORE "Tool use:".
    # This locks the intended reading flow — agent learns "you start
    # with search tools" before reading general tool-use guidance.
    assert BASE_PROMPT.index("Tool discovery") < BASE_PROMPT.index("Tool use:")


@pytest.mark.asyncio
async def test_baseline_visible_at_session_start() -> None:
    """Turn 1 LLM sees exactly [search_tools, search_mcps, continue] — nothing more."""
    llm = FakeLLM([
        # Turn 1: LLM emits final text immediately (no tool calls).
        Message.assistant(content="done"),
    ])

    loaded_schemas: list[dict] = []
    loaded_tool_names: set[str] = set()

    agent = Agent(
        llm=llm,
        tools=_make_registry(),
        system_prompt="test",
        loaded_schemas=loaded_schemas,
        loaded_tool_names=loaded_tool_names,
    )
    await _collect(agent, "hello")

    assert len(llm.calls) == 1
    baseline_names = _schema_names(llm.calls[0]["tools"])
    assert baseline_names == ["search_tools", "search_mcps", "continue"]


@pytest.mark.asyncio
async def test_search_tools_then_call_loaded_tool() -> None:
    """End-to-end: turn 1 calls search_tools('shell'), turn 2 calls shell, turn 3 ends."""
    loaded_schemas: list[dict] = []
    loaded_tool_names: set[str] = set()

    # Build a real shell stub and a SearchTools wired to the shared containers.
    shell_stub = StubTool("shell", description="Run a shell command.")
    full_registry = _make_registry(shell_stub)

    search_tools = _make_search_tools(
        registry=full_registry,
        loaded_schemas=loaded_schemas,
        loaded_tool_names=loaded_tool_names,
    )

    # The agent's ToolRegistry must have BOTH search_tools AND shell.
    agent_registry = _make_registry(search_tools, shell_stub)

    llm = FakeLLM([
        # Iteration 1: LLM calls search_tools("shell")
        Message.assistant(
            content="",
            tool_calls=[ToolCall(id="tc1", name="search_tools", arguments={"query": "shell"})],
        ),
        # Iteration 2: LLM calls shell (now loaded via search)
        Message.assistant(
            content="",
            tool_calls=[ToolCall(id="tc2", name="shell", arguments={"command": "ls"})],
        ),
        # Iteration 3: LLM emits final text
        Message.assistant(content="Files listed."),
    ])

    agent = Agent(
        llm=llm,
        tools=agent_registry,
        system_prompt="test",
        loaded_schemas=loaded_schemas,
        loaded_tool_names=loaded_tool_names,
    )
    msgs = await _collect(agent, "list the files")

    # Iteration 1: tools= should be the 2-tool baseline (shell not yet loaded)
    assert _schema_names(llm.calls[0]["tools"]) == ["search_tools", "search_mcps", "continue"]

    # Iteration 2: tools= should include shell (loaded by search_tools call)
    iter2_names = _schema_names(llm.calls[1]["tools"])
    assert "shell" in iter2_names

    # Shell was actually dispatched
    assert len(shell_stub.calls) == 1
    assert shell_stub.calls[0] == {"command": "ls"}

    # Final assistant message is the last message
    final_msg = [m for m in msgs if m.role == Role.ASSISTANT][-1]
    assert final_msg.content == "Files listed."


@pytest.mark.asyncio
async def test_search_mcps_then_call_loaded_mcp_tool() -> None:
    """End-to-end MCP path: search_mcps('') → call mcp__test__calc → final text."""
    loaded_schemas: list[dict] = []
    loaded_tool_names: set[str] = set()

    mcp_tool_name = "mcp__test_source__calc"
    mcp_tools = [(mcp_tool_name, "A calculator tool.")]
    source_index = {
        "test_source": {
            "synthetic_description": "Test MCP source with a calculator.",
            "tool_names_prefixed": [mcp_tool_name],
        }
    }

    search_mcps, mcp_registry = _make_search_mcps(
        mcp_tools=mcp_tools,
        source_index=source_index,
        loaded_schemas=loaded_schemas,
        loaded_tool_names=loaded_tool_names,
    )

    # The MCP tool needs to be callable from the agent — use a StubTool
    # that can be dispatched by the agent loop.
    mcp_stub = StubTool(mcp_tool_name, description="A calculator tool.")

    agent_registry = _make_registry(search_mcps, mcp_stub)

    llm = FakeLLM([
        # Iteration 1: LLM calls search_mcps("") (empty = list all)
        Message.assistant(
            content="",
            tool_calls=[ToolCall(id="tc1", name="search_mcps", arguments={"query": ""})],
        ),
        # Iteration 2: LLM calls the MCP tool (now loaded)
        Message.assistant(
            content="",
            tool_calls=[ToolCall(id="tc2", name=mcp_tool_name, arguments={"x": 2, "y": 3})],
        ),
        # Iteration 3: LLM emits final text
        Message.assistant(content="Result: 5."),
    ])

    agent = Agent(
        llm=llm,
        tools=agent_registry,
        system_prompt="test",
        loaded_schemas=loaded_schemas,
        loaded_tool_names=loaded_tool_names,
    )
    msgs = await _collect(agent, "calculate 2 + 3")

    # Iteration 1: baseline only
    assert _schema_names(llm.calls[0]["tools"]) == ["search_tools", "search_mcps", "continue"]

    # Iteration 2: MCP tool schema is now visible
    iter2_names = _schema_names(llm.calls[1]["tools"])
    assert mcp_tool_name in iter2_names

    # MCP stub was dispatched
    assert len(mcp_stub.calls) == 1

    # Final message renders correctly
    final_msg = [m for m in msgs if m.role == Role.ASSISTANT][-1]
    assert final_msg.content == "Result: 5."


@pytest.mark.asyncio
async def test_search_then_call_preserves_loaded_set_across_step() -> None:
    """Loaded schemas survive across user turns (two agent.step() calls)."""
    loaded_schemas: list[dict] = []
    loaded_tool_names: set[str] = set()

    read_stub = StubTool("read_file", description="Read a file.")
    full_registry = _make_registry(read_stub)

    search_tools = _make_search_tools(
        registry=full_registry,
        loaded_schemas=loaded_schemas,
        loaded_tool_names=loaded_tool_names,
    )
    agent_registry = _make_registry(search_tools, read_stub)

    llm = FakeLLM([
        # Step 1, iteration 1: search_tools("read")
        Message.assistant(
            content="",
            tool_calls=[ToolCall(id="s1", name="search_tools", arguments={"query": "read"})],
        ),
        # Step 1, iteration 2: final text
        Message.assistant(content="Found read_file."),
        # Step 2, iteration 1: call read_file (loaded from step 1)
        Message.assistant(
            content="",
            tool_calls=[ToolCall(id="s2", name="read_file", arguments={"path": "/tmp/x.txt"})],
        ),
        # Step 2, iteration 2: final text
        Message.assistant(content="File content here."),
    ])

    agent = Agent(
        llm=llm,
        tools=agent_registry,
        system_prompt="test",
        loaded_schemas=loaded_schemas,
        loaded_tool_names=loaded_tool_names,
    )

    # Step 1
    await _collect(agent, "find me a file reading tool")
    # Step 2
    await _collect(agent, "now read /tmp/x.txt")

    # Step 1, iteration 1: baseline
    assert _schema_names(llm.calls[0]["tools"]) == ["search_tools", "search_mcps", "continue"]
    # Step 1, iteration 2: read_file loaded after search
    assert "read_file" in _schema_names(llm.calls[1]["tools"])

    # Step 2, iteration 1: read_file STILL visible (persisted across step())
    step2_iter1_names = _schema_names(llm.calls[2]["tools"])
    assert "read_file" in step2_iter1_names

    # read_file was dispatched in step 2
    assert len(read_stub.calls) == 1


@pytest.mark.asyncio
async def test_search_then_call_with_continue_signal() -> None:
    """search_tools + continue on the same turn works; loop continues correctly."""
    loaded_schemas: list[dict] = []
    loaded_tool_names: set[str] = set()

    python_stub = StubTool("python_exec", description="Execute Python code.")
    full_registry = _make_registry(python_stub)

    search_tools = _make_search_tools(
        registry=full_registry,
        loaded_schemas=loaded_schemas,
        loaded_tool_names=loaded_tool_names,
    )
    agent_registry = _make_registry(search_tools, python_stub)

    llm = FakeLLM([
        # Iteration 1: search_tools("python") + continue
        Message.assistant(
            content="",
            tool_calls=[
                ToolCall(id="tc1", name="search_tools", arguments={"query": "python"}),
                ToolCall(id="tc2", name="continue", arguments={"reason": "need to run code"}),
            ],
        ),
        # Iteration 2: call python_exec (now loaded) + continue
        Message.assistant(
            content="",
            tool_calls=[
                ToolCall(id="tc3", name="python_exec", arguments={"code": "print(1+1)"}),
                ToolCall(id="tc4", name="continue", arguments={"reason": "wrapping up"}),
            ],
        ),
        # Iteration 3: final text
        Message.assistant(content="The answer is 2."),
    ])

    agent = Agent(
        llm=llm,
        tools=agent_registry,
        system_prompt="test",
        loaded_schemas=loaded_schemas,
        loaded_tool_names=loaded_tool_names,
    )
    msgs = await _collect(agent, "run some python")

    # Iteration 1: baseline
    assert _schema_names(llm.calls[0]["tools"]) == ["search_tools", "search_mcps", "continue"]
    # Iteration 2: python_exec visible (search + continue both executed in iter 1)
    assert "python_exec" in _schema_names(llm.calls[1]["tools"])
    # python_exec was dispatched
    assert len(python_stub.calls) == 1
    # Final text rendered
    final_msg = [m for m in msgs if m.role == Role.ASSISTANT][-1]
    assert final_msg.content == "The answer is 2."


@pytest.mark.asyncio
async def test_search_with_no_matches_does_not_load() -> None:
    """search_tools with a query that matches nothing adds nothing to _loaded_schemas."""
    loaded_schemas: list[dict] = []
    loaded_tool_names: set[str] = set()

    shell_stub = StubTool("shell", description="Run shell commands.")
    full_registry = _make_registry(shell_stub)

    search_tools = _make_search_tools(
        registry=full_registry,
        loaded_schemas=loaded_schemas,
        loaded_tool_names=loaded_tool_names,
    )
    agent_registry = _make_registry(search_tools, shell_stub)

    llm = FakeLLM([
        # Iteration 1: search_tools("xyzzy_no_match") — no results
        Message.assistant(
            content="",
            tool_calls=[ToolCall(id="tc1", name="search_tools", arguments={"query": "xyzzy_no_match"})],
        ),
        # Iteration 2: LLM emits final text (no tool to call — search failed)
        Message.assistant(content="No tools found for that query."),
    ])

    agent = Agent(
        llm=llm,
        tools=agent_registry,
        system_prompt="test",
        loaded_schemas=loaded_schemas,
        loaded_tool_names=loaded_tool_names,
    )
    await _collect(agent, "find me xyzzy_no_match")

    # Iteration 1: baseline
    assert _schema_names(llm.calls[0]["tools"]) == ["search_tools", "search_mcps", "continue"]
    # Iteration 2: STILL the 2-tool baseline — nothing loaded
    iter2_names = _schema_names(llm.calls[1]["tools"])
    assert iter2_names == ["search_tools", "search_mcps", "continue"]
    # Loaded set is empty
    assert loaded_schemas == []
    assert loaded_tool_names == set()
