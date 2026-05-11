"""End-to-end integration tests for the lazy tool discovery protocol.

Drives the full search → load → call sequence via a scripted FakeLLM
provider, verifying that:
- The agent's baseline tools= array contains exactly [search_tools, continue].
- search_tools loads matching schemas (built-in OR MCP) into subsequent
  iterations' tools= arrays.
- Loaded schemas persist across user turns within a session.
- No-match searches do not add anything to the loaded set.
- BASE_PROMPT contains the Tool discovery section before Tool use.
"""

from __future__ import annotations

from typing import Any

import pytest

from conftest import FakeLLM, StubTool
from the_one.agent.core import Agent, CONTINUE_SCHEMA, SEARCH_TOOLS_SCHEMA
from the_one.llm.base import Message, Role, ToolCall
from the_one.tools._search_tools import SearchTools
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
    source_index: dict[str, Any] | None = None,
    agent_name: str = "test",
) -> SearchTools:
    on_match = _make_on_match(loaded_schemas, loaded_tool_names)
    return SearchTools(
        on_match=on_match,
        registry=registry,
        source_index=source_index or {},
        agent_name=agent_name,
    )


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
    """BASE_PROMPT must teach the lazy-discovery protocol.

    If this test fails after a future edit, the discovery section was
    removed — either reinstate it or update the design contract.
    """
    from the_one.agent.config import BASE_PROMPT

    assert "search_tools" in BASE_PROMPT
    assert "Tool discovery" in BASE_PROMPT
    # The discovery section must mention MCP server tools surface through
    # the same search (the whole point of the merge).
    assert "MCP" in BASE_PROMPT
    # Order lock: discovery section before "Tool use:".
    assert BASE_PROMPT.index("Tool discovery") < BASE_PROMPT.index("Tool use:")


@pytest.mark.asyncio
async def test_baseline_visible_at_session_start() -> None:
    """Turn 1 LLM sees exactly [search_tools, continue] — nothing more."""
    llm = FakeLLM(
        [
            Message.assistant(content="done"),
        ]
    )

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
    assert baseline_names == ["search_tools", "continue"]


@pytest.mark.asyncio
async def test_search_then_call_loaded_builtin_tool() -> None:
    """End-to-end: turn 1 calls search_tools('shell'), turn 2 calls shell, turn 3 ends."""
    loaded_schemas: list[dict] = []
    loaded_tool_names: set[str] = set()

    shell_stub = StubTool("shell", description="Run a shell command.")
    full_registry = _make_registry(shell_stub)

    search_tools = _make_search_tools(
        registry=full_registry,
        loaded_schemas=loaded_schemas,
        loaded_tool_names=loaded_tool_names,
    )

    agent_registry = _make_registry(search_tools, shell_stub)

    llm = FakeLLM(
        [
            Message.assistant(
                content="",
                tool_calls=[ToolCall(id="tc1", name="search_tools", arguments={"query": "shell"})],
            ),
            Message.assistant(
                content="",
                tool_calls=[ToolCall(id="tc2", name="shell", arguments={"command": "ls"})],
            ),
            Message.assistant(content="Files listed."),
        ]
    )

    agent = Agent(
        llm=llm,
        tools=agent_registry,
        system_prompt="test",
        loaded_schemas=loaded_schemas,
        loaded_tool_names=loaded_tool_names,
    )
    msgs = await _collect(agent, "list the files")

    assert _schema_names(llm.calls[0]["tools"]) == ["search_tools", "continue"]
    iter2_names = _schema_names(llm.calls[1]["tools"])
    assert "shell" in iter2_names

    assert len(shell_stub.calls) == 1
    assert shell_stub.calls[0] == {"command": "ls"}

    final_msg = [m for m in msgs if m.role == Role.ASSISTANT][-1]
    assert final_msg.content == "Files listed."


@pytest.mark.asyncio
async def test_search_then_call_loaded_mcp_tool() -> None:
    """End-to-end MCP path: search_tools('') loads MCP tools too; calling one succeeds."""
    loaded_schemas: list[dict] = []
    loaded_tool_names: set[str] = set()

    mcp_tool_name = "mcp__test_source__calc"
    mcp_stub = StubTool(mcp_tool_name, description="A calculator tool.")

    full_registry = _make_registry(mcp_stub)

    source_index = {
        "test_source": {
            "synthetic_description": "Test MCP source with a calculator.",
            "tool_names_prefixed": [mcp_tool_name],
        }
    }

    search_tools = _make_search_tools(
        registry=full_registry,
        loaded_schemas=loaded_schemas,
        loaded_tool_names=loaded_tool_names,
        source_index=source_index,
    )

    agent_registry = _make_registry(search_tools, mcp_stub)

    llm = FakeLLM(
        [
            Message.assistant(
                content="",
                tool_calls=[ToolCall(id="tc1", name="search_tools", arguments={"query": ""})],
            ),
            Message.assistant(
                content="",
                tool_calls=[ToolCall(id="tc2", name=mcp_tool_name, arguments={"x": 2, "y": 3})],
            ),
            Message.assistant(content="Result: 5."),
        ]
    )

    agent = Agent(
        llm=llm,
        tools=agent_registry,
        system_prompt="test",
        loaded_schemas=loaded_schemas,
        loaded_tool_names=loaded_tool_names,
    )
    msgs = await _collect(agent, "calculate 2 + 3")

    assert _schema_names(llm.calls[0]["tools"]) == ["search_tools", "continue"]
    iter2_names = _schema_names(llm.calls[1]["tools"])
    assert mcp_tool_name in iter2_names

    assert len(mcp_stub.calls) == 1

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

    llm = FakeLLM(
        [
            Message.assistant(
                content="",
                tool_calls=[ToolCall(id="s1", name="search_tools", arguments={"query": "read"})],
            ),
            Message.assistant(content="Found read_file."),
            Message.assistant(
                content="",
                tool_calls=[ToolCall(id="s2", name="read_file", arguments={"path": "/tmp/x.txt"})],
            ),
            Message.assistant(content="File content here."),
        ]
    )

    agent = Agent(
        llm=llm,
        tools=agent_registry,
        system_prompt="test",
        loaded_schemas=loaded_schemas,
        loaded_tool_names=loaded_tool_names,
    )

    await _collect(agent, "find me a file reading tool")
    await _collect(agent, "now read /tmp/x.txt")

    assert _schema_names(llm.calls[0]["tools"]) == ["search_tools", "continue"]
    assert "read_file" in _schema_names(llm.calls[1]["tools"])

    step2_iter1_names = _schema_names(llm.calls[2]["tools"])
    assert "read_file" in step2_iter1_names

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

    llm = FakeLLM(
        [
            Message.assistant(
                content="",
                tool_calls=[
                    ToolCall(id="tc1", name="search_tools", arguments={"query": "python"}),
                    ToolCall(id="tc2", name="continue", arguments={"reason": "need to run code"}),
                ],
            ),
            Message.assistant(
                content="",
                tool_calls=[
                    ToolCall(id="tc3", name="python_exec", arguments={"code": "print(1+1)"}),
                    ToolCall(id="tc4", name="continue", arguments={"reason": "wrapping up"}),
                ],
            ),
            Message.assistant(content="The answer is 2."),
        ]
    )

    agent = Agent(
        llm=llm,
        tools=agent_registry,
        system_prompt="test",
        loaded_schemas=loaded_schemas,
        loaded_tool_names=loaded_tool_names,
    )
    msgs = await _collect(agent, "run some python")

    assert _schema_names(llm.calls[0]["tools"]) == ["search_tools", "continue"]
    assert "python_exec" in _schema_names(llm.calls[1]["tools"])
    assert len(python_stub.calls) == 1
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

    llm = FakeLLM(
        [
            Message.assistant(
                content="",
                tool_calls=[
                    ToolCall(
                        id="tc1",
                        name="search_tools",
                        arguments={"query": "xyzzy_no_match"},
                    )
                ],
            ),
            Message.assistant(content="No tools found for that query."),
        ]
    )

    agent = Agent(
        llm=llm,
        tools=agent_registry,
        system_prompt="test",
        loaded_schemas=loaded_schemas,
        loaded_tool_names=loaded_tool_names,
    )
    await _collect(agent, "find me xyzzy_no_match")

    assert _schema_names(llm.calls[0]["tools"]) == ["search_tools", "continue"]
    iter2_names = _schema_names(llm.calls[1]["tools"])
    assert iter2_names == ["search_tools", "continue"]
    assert loaded_schemas == []
    assert loaded_tool_names == set()
