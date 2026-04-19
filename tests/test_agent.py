"""Tests for Agent loop (Agent.step())."""

from __future__ import annotations

from typing import Any

from conftest import FakeLLM, StubTool

from the_one.agent.core import Agent
from the_one.llm.base import Message, Role, ToolCall
from the_one.tools.base import Tool, ToolRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class ErrorTool(Tool):
    """Tool that always raises an exception."""

    def __init__(self, name: str = "bad_tool") -> None:
        self.name = name
        self.description = "A tool that always fails."
        self.parameters: dict[str, Any] = {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> str:
        raise RuntimeError("kaboom")


def _make_registry(*tools: Tool) -> ToolRegistry:
    """Build a fresh ToolRegistry from the given tools."""
    reg = ToolRegistry()
    for t in tools:
        reg.register(t)
    return reg


async def _collect(agent: Agent, user_input: str) -> list[Message]:
    """Collect all yielded messages from agent.step()."""
    msgs: list[Message] = []
    async for m in agent.step(user_input):
        msgs.append(m)
    return msgs


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestNormalFlow:
    async def test_text_only_response(self) -> None:
        """LLM responds with text only — yields one message, loop ends."""
        llm = FakeLLM([Message.assistant("hello")])
        agent = Agent(llm=llm, tools=_make_registry())
        msgs = await _collect(agent, "hi")

        assert len(msgs) == 1
        assert msgs[0].role == Role.ASSISTANT
        assert msgs[0].content == "hello"


class TestToolExecution:
    async def test_tool_call_then_final_response(self) -> None:
        """LLM calls a tool, gets result, then responds with text."""
        tool_a = StubTool("tool_a")
        llm = FakeLLM([
            Message.assistant(
                "",
                tool_calls=[ToolCall(id="1", name="tool_a", arguments={})],
            ),
            Message.assistant("done"),
        ])
        agent = Agent(llm=llm, tools=_make_registry(tool_a))
        msgs = await _collect(agent, "use tool_a")

        # Should yield: assistant (with tool_call), tool result, final assistant
        assert len(msgs) == 3
        assert msgs[0].role == Role.ASSISTANT
        assert msgs[1].role == Role.TOOL
        assert msgs[1].content == "stub: tool_a"
        assert msgs[2].role == Role.ASSISTANT
        assert msgs[2].content == "done"
        # Tool was actually called
        assert len(tool_a.calls) == 1


class TestDirectAction:
    async def test_restart_bypass(self) -> None:
        """'restart yourself' matches direct action — calls tool without LLM."""
        restart_tool = StubTool("restart")
        llm = FakeLLM([])  # No responses needed — LLM not called
        agent = Agent(llm=llm, tools=_make_registry(restart_tool))
        msgs = await _collect(agent, "restart yourself")

        assert len(msgs) == 1
        assert msgs[0].role == Role.ASSISTANT
        assert msgs[0].content == "stub: restart"
        assert len(restart_tool.calls) == 1
        # LLM was never called
        assert len(llm.calls) == 0


class TestContinueSignal:
    async def test_continue_not_yielded_to_caller(self) -> None:
        """Continue tool result is NOT yielded, but the loop continues."""
        tool_a = StubTool("tool_a")
        llm = FakeLLM([
            # Iteration 1: LLM calls continue
            Message.assistant(
                "thinking...",
                tool_calls=[ToolCall(id="1", name="continue", arguments={"reason": "more work"})],
            ),
            # Iteration 2: LLM responds with final text
            Message.assistant("all done"),
        ])
        agent = Agent(llm=llm, tools=_make_registry(tool_a))
        msgs = await _collect(agent, "think hard")

        # The assistant message preceding the continue IS yielded (line 59 of core.py)
        # The continue tool_result is NOT yielded
        # Then the final assistant message is yielded
        assert len(msgs) == 2
        assert msgs[0].role == Role.ASSISTANT
        assert msgs[0].content == "thinking..."
        assert msgs[1].role == Role.ASSISTANT
        assert msgs[1].content == "all done"

        # But the continue result IS in agent.messages internally
        tool_msgs = [m for m in agent.messages if m.role == Role.TOOL]
        assert len(tool_msgs) == 1
        assert tool_msgs[0].content == "more work"


class TestMaxIterations:
    async def test_stops_at_max_iterations(self) -> None:
        """LLM always calls tools — loop stops after max_iterations."""
        tool_a = StubTool("tool_a")
        responses = [
            Message.assistant(
                f"call {i}",
                tool_calls=[ToolCall(id=str(i), name="tool_a", arguments={})],
            )
            for i in range(5)  # More than max_iterations=2
        ]
        llm = FakeLLM(responses)
        agent = Agent(llm=llm, tools=_make_registry(tool_a), max_iterations=2)
        msgs = await _collect(agent, "loop forever")

        # 2 iterations: each yields assistant + tool_result = 4 messages
        assert len(msgs) == 4
        assert len(llm.calls) == 2
        # Verify alternating pattern
        assert msgs[0].role == Role.ASSISTANT
        assert msgs[1].role == Role.TOOL
        assert msgs[2].role == Role.ASSISTANT
        assert msgs[3].role == Role.TOOL


class TestToolError:
    async def test_tool_exception_yields_error_result(self) -> None:
        """Tool raises exception — yields ToolResult with is_error=True."""
        bad = ErrorTool("bad_tool")
        llm = FakeLLM([
            Message.assistant(
                "",
                tool_calls=[ToolCall(id="1", name="bad_tool", arguments={})],
            ),
            Message.assistant("sorry about that"),
        ])
        agent = Agent(llm=llm, tools=_make_registry(bad))
        msgs = await _collect(agent, "call bad_tool")

        assert len(msgs) == 3
        assert msgs[1].role == Role.TOOL
        assert msgs[1].tool_result is not None
        assert msgs[1].tool_result.is_error is True
        assert "kaboom" in msgs[1].content


class TestTextEmbeddedToolCalls:
    async def test_json_in_text_extracted_and_executed(self) -> None:
        """LLM returns text with JSON tool call — extracted and executed."""
        tool_a = StubTool("tool_a")
        llm = FakeLLM([
            # First response: text with embedded JSON, no formal tool_calls
            Message.assistant('I will use the tool {"name": "tool_a", "arguments": "hello"}'),
            # Second response: after tool execution
            Message.assistant("done"),
        ])
        agent = Agent(llm=llm, tools=_make_registry(tool_a))
        msgs = await _collect(agent, "use tool_a via text")

        # assistant (with embedded call), tool result, final assistant
        assert len(msgs) == 3
        assert msgs[0].role == Role.ASSISTANT
        assert msgs[1].role == Role.TOOL
        assert msgs[1].content == "stub: tool_a"
        assert msgs[2].role == Role.ASSISTANT
        assert msgs[2].content == "done"
        # Tool was called with extracted args
        assert len(tool_a.calls) == 1
        assert tool_a.calls[0] == {"args": "hello"}


class TestReset:
    async def test_reset_clears_to_system_prompt(self) -> None:
        """After step, reset() leaves only the system prompt."""
        llm = FakeLLM([Message.assistant("hi")])
        agent = Agent(llm=llm, tools=_make_registry())
        await _collect(agent, "hello")

        assert len(agent.messages) > 1  # system + user + assistant
        agent.reset()
        assert len(agent.messages) == 1
        assert agent.messages[0].role == Role.SYSTEM
