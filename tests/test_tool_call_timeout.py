"""Tests for per-tool-call timeout (DD2 / Leg 2).

Verifies that:
- A slow tool that exceeds THE_ONE_TOOL_CALL_TIMEOUT_SECONDS produces a
  timeout ToolResult (is_error=True) and the agent loop still terminates
  cleanly (yields a final assistant message — no hang).
- The auth-required path (MCPAuthRequired) is not interfered with by the
  asyncio.wait_for wrapper.
- The ContextVar current_tool_call_id is reset after a timeout (finally runs).
- The env var is read at call time (monkeypatched low value takes effect).
- A bad env var value falls back to the default (no crash).
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from conftest import FakeLLM, StubTool

from the_one.agent._context import current_tool_call_id
from the_one.agent.core import Agent, _get_tool_call_timeout
from the_one.llm.base import Message, Role, ToolCall
from the_one.mcp.errors import MCPAuthRequired
from the_one.tools.base import Tool, ToolRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class SlowTool(Tool):
    """Tool that sleeps for ``sleep_seconds`` before returning.

    Designed to exceed a monkeypatched low timeout so the ``asyncio.wait_for``
    in ``_execute_tool`` fires.
    """

    def __init__(self, name: str = "slow_tool", sleep_seconds: float = 10.0) -> None:
        self.name = name
        self.description = "A tool that sleeps before returning."
        self.parameters: dict[str, Any] = {
            "type": "object",
            "properties": {},
            "required": [],
        }
        self.sleep_seconds = sleep_seconds
        self.calls: list[dict[str, Any]] = []

    async def execute(self, **kwargs: Any) -> str:
        self.calls.append(kwargs)
        await asyncio.sleep(self.sleep_seconds)
        return f"slow: {self.name}"


class AuthRaisingTool(Tool):
    """Tool that raises MCPAuthRequired on its first call.

    Used to verify that the asyncio.wait_for wrapper does not swallow or
    interfere with the MCPAuthRequired control-flow exception path in
    _execute_tool.
    """

    def __init__(self, name: str = "auth_tool") -> None:
        self.name = name
        self.description = "A tool that raises MCPAuthRequired."
        self.parameters: dict[str, Any] = {
            "type": "object",
            "properties": {},
            "required": [],
        }
        self.calls: list[dict[str, Any]] = []

    async def execute(self, **kwargs: Any) -> str:
        self.calls.append(kwargs)
        raise MCPAuthRequired(
            "src_test",
            source_name="Test Source",
            resource_metadata_url="https://src_test/.well-known/oauth-protected-resource",
            consent_url=None,
        )


def _make_registry(*tools: Tool) -> ToolRegistry:
    reg = ToolRegistry()
    for t in tools:
        reg.register(t)
    return reg


async def _collect(agent: Agent, user_input: str) -> list[Message]:
    msgs: list[Message] = []
    async for m in agent.step(user_input):
        msgs.append(m)
    return msgs


# ---------------------------------------------------------------------------
# _get_tool_call_timeout unit tests
# ---------------------------------------------------------------------------


class TestGetToolCallTimeout:
    def test_default_when_env_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("THE_ONE_TOOL_CALL_TIMEOUT_SECONDS", raising=False)
        assert _get_tool_call_timeout() == 120.0

    def test_custom_value_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("THE_ONE_TOOL_CALL_TIMEOUT_SECONDS", "30")
        assert _get_tool_call_timeout() == 30.0

    def test_bad_value_falls_back_to_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("THE_ONE_TOOL_CALL_TIMEOUT_SECONDS", "not-a-number")
        assert _get_tool_call_timeout() == 120.0

    def test_below_floor_clamped_to_floor(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("THE_ONE_TOOL_CALL_TIMEOUT_SECONDS", "0")
        assert _get_tool_call_timeout() == 1.0

    def test_negative_value_clamped_to_floor(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("THE_ONE_TOOL_CALL_TIMEOUT_SECONDS", "-5")
        assert _get_tool_call_timeout() == 1.0

    def test_float_value_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("THE_ONE_TOOL_CALL_TIMEOUT_SECONDS", "2.5")
        assert _get_tool_call_timeout() == 2.5


# ---------------------------------------------------------------------------
# _execute_tool timeout tests
# ---------------------------------------------------------------------------


class TestExecuteToolTimeout:
    async def test_slow_tool_returns_timeout_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A slow tool exceeding the ceiling returns a timeout ToolResult."""
        monkeypatch.setenv("THE_ONE_TOOL_CALL_TIMEOUT_SECONDS", "1")  # 1 s floor
        slow = SlowTool("slow_tool", sleep_seconds=10.0)
        agent = Agent(
            llm=FakeLLM([]),
            tools=_make_registry(slow),
            system_prompt="test",
        )
        tool_call = ToolCall(id="tc1", name="slow_tool", arguments={})
        result = await agent._execute_tool(tool_call)

        assert result.is_error is True
        assert "slow_tool" in result.content
        assert "timed out" in result.content
        assert "1s" in result.content

    async def test_timeout_error_includes_tool_name_and_seconds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Error message format: 'tool {name} timed out after {N}s'."""
        monkeypatch.setenv("THE_ONE_TOOL_CALL_TIMEOUT_SECONDS", "1")
        slow = SlowTool("my_slow_tool", sleep_seconds=5.0)
        agent = Agent(
            llm=FakeLLM([]),
            tools=_make_registry(slow),
            system_prompt="test",
        )
        tool_call = ToolCall(id="tc2", name="my_slow_tool", arguments={})
        result = await agent._execute_tool(tool_call)

        assert result.is_error is True
        assert result.content == "tool my_slow_tool timed out after 1s"

    async def test_context_var_reset_after_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """current_tool_call_id ContextVar is reset after a timeout (finally runs)."""
        monkeypatch.setenv("THE_ONE_TOOL_CALL_TIMEOUT_SECONDS", "1")
        slow = SlowTool("slow_tool", sleep_seconds=5.0)
        agent = Agent(
            llm=FakeLLM([]),
            tools=_make_registry(slow),
            system_prompt="test",
        )
        # Baseline: no current tool call id set
        assert current_tool_call_id.get(None) is None

        tool_call = ToolCall(id="tc_ctx", name="slow_tool", arguments={})
        result = await agent._execute_tool(tool_call)

        assert result.is_error is True
        # ContextVar must be reset to its pre-call state
        assert current_tool_call_id.get(None) is None


# ---------------------------------------------------------------------------
# Agent loop with timeout: turn still terminates with done
# ---------------------------------------------------------------------------


class TestAgentLoopWithTimeout:
    async def test_timeout_tool_loop_yields_final_message(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A timed-out tool produces a tool-error; the loop completes (no hang)."""
        monkeypatch.setenv("THE_ONE_TOOL_CALL_TIMEOUT_SECONDS", "1")
        slow = SlowTool("slow_tool", sleep_seconds=10.0)
        llm = FakeLLM(
            [
                Message.assistant(
                    "",
                    tool_calls=[ToolCall(id="tc1", name="slow_tool", arguments={})],
                ),
                Message.assistant("done despite timeout"),
            ]
        )
        agent = Agent(llm=llm, tools=_make_registry(slow), system_prompt="test")
        msgs = await _collect(agent, "call slow_tool")

        # assistant (tool_call) + tool_result (error) + final assistant
        assert len(msgs) == 3
        assert msgs[0].role == Role.ASSISTANT
        assert msgs[1].role == Role.TOOL
        assert msgs[1].tool_result is not None
        assert msgs[1].tool_result.is_error is True
        assert "timed out" in msgs[1].content
        assert msgs[2].role == Role.ASSISTANT
        assert msgs[2].content == "done despite timeout"

    async def test_fast_tool_not_timed_out(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A fast tool completes normally even with a small-but-sufficient timeout."""
        monkeypatch.setenv("THE_ONE_TOOL_CALL_TIMEOUT_SECONDS", "5")
        fast = StubTool("fast_tool")  # returns immediately
        llm = FakeLLM(
            [
                Message.assistant(
                    "",
                    tool_calls=[ToolCall(id="tc1", name="fast_tool", arguments={})],
                ),
                Message.assistant("all good"),
            ]
        )
        agent = Agent(llm=llm, tools=_make_registry(fast), system_prompt="test")
        msgs = await _collect(agent, "call fast_tool")

        assert len(msgs) == 3
        assert msgs[1].role == Role.TOOL
        assert msgs[1].tool_result is not None
        assert msgs[1].tool_result.is_error is False
        assert "stub: fast_tool" in msgs[1].content
        assert msgs[2].content == "all good"


# ---------------------------------------------------------------------------
# Auth-required path: no interference from wait_for
# ---------------------------------------------------------------------------


class TestAuthPauseUnaffected:
    async def test_auth_required_tool_produces_pause_result(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """MCPAuthRequired still produces a pause ToolResult (no interference)."""
        # Use a low timeout to confirm auth-required fires BEFORE timeout
        monkeypatch.setenv("THE_ONE_TOOL_CALL_TIMEOUT_SECONDS", "5")
        auth_tool = AuthRaisingTool("auth_tool")
        agent = Agent(
            llm=FakeLLM([]),
            tools=_make_registry(auth_tool),
            system_prompt="test",
        )
        tool_call = ToolCall(id="tc_auth", name="auth_tool", arguments={})
        result = await agent._execute_tool(tool_call)

        # Must be an auth-required pause, NOT a timeout error
        assert result.is_error is False
        assert result.metadata is not None
        assert result.metadata.get("is_auth_required") is True
        assert result.metadata.get("source_id") == "src_test"

    async def test_auth_pause_in_loop_defers_and_exits(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Auth-required tool in the loop still pauses the step (no interference)."""
        monkeypatch.setenv("THE_ONE_TOOL_CALL_TIMEOUT_SECONDS", "5")
        auth_tool = AuthRaisingTool("auth_tool")
        llm = FakeLLM(
            [
                Message.assistant(
                    "",
                    tool_calls=[ToolCall(id="tc_auth", name="auth_tool", arguments={})],
                ),
            ]
        )
        agent = Agent(
            llm=llm,
            tools=_make_registry(auth_tool),
            system_prompt="test",
            max_iterations=10,
        )
        msgs = await _collect(agent, "trigger auth")

        # Two messages: assistant (tool_call) + auth-required tool_result
        assert len(msgs) == 2
        assert msgs[0].role == Role.ASSISTANT
        assert msgs[1].role == Role.TOOL
        assert msgs[1].tool_result is not None
        assert msgs[1].tool_result.metadata is not None
        assert msgs[1].tool_result.metadata.get("is_auth_required") is True
        # Loop should be paused (deferred_tool_calls set)
        assert agent._deferred_tool_calls is not None
