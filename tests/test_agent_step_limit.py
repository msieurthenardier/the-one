"""Agent.stopped_at_step_limit lifecycle (M31 F6 leg 06, DD8)."""

from __future__ import annotations

from conftest import FakeLLM, StubTool

from tests.test_agent import (
    AuthRequiredStubTool,
    _collect,
    _install_auth_required_executor,
    _make_registry,
)
from tests.test_agent_redundant_backstop import _agent as _degraded_agent
from the_one.agent.core import Agent
from the_one.llm.base import Message, ToolCall


def _call(i: int, name: str = "tool_a") -> Message:
    return Message.assistant("", tool_calls=[ToolCall(id=f"c{i}", name=name, arguments={})])


async def test_default_is_false() -> None:
    agent = Agent(llm=FakeLLM([]), tools=_make_registry(), system_prompt="t")
    assert agent.stopped_at_step_limit is False


async def test_tool_call_every_iteration_sets_flag() -> None:
    llm = FakeLLM([_call(1), _call(2)])
    agent = Agent(
        llm=llm, tools=_make_registry(StubTool("tool_a")), system_prompt="t", max_iterations=2
    )
    await _collect(agent, "go")
    assert agent.stopped_at_step_limit is True


async def test_last_iteration_with_text_and_tool_calls_sets_flag() -> None:
    msg = Message.assistant("more", tool_calls=[ToolCall(id="c1", name="tool_a", arguments={})])
    agent = Agent(
        llm=FakeLLM([msg]),
        tools=_make_registry(StubTool("tool_a")),
        system_prompt="t",
        max_iterations=1,
    )
    await _collect(agent, "go")
    assert agent.stopped_at_step_limit is True


async def test_text_answer_does_not_set_flag() -> None:
    agent = Agent(
        llm=FakeLLM([_call(1), Message.assistant("done")]),
        tools=_make_registry(StubTool("tool_a")),
        system_prompt="t",
        max_iterations=2,
    )
    await _collect(agent, "go")
    assert agent.stopped_at_step_limit is False


async def test_auth_pause_does_not_set_flag() -> None:
    auth = AuthRequiredStubTool(name="auth_tool")
    agent = Agent(
        llm=FakeLLM([_call(1, "auth_tool")]),
        tools=_make_registry(auth),
        system_prompt="t",
        max_iterations=1,
    )
    _install_auth_required_executor(agent, {"auth_tool": auth})
    await _collect(agent, "go")
    assert agent._deferred_tool_calls is not None
    assert agent.stopped_at_step_limit is False


async def test_degraded_backstop_exit_does_not_set_flag() -> None:
    call = Message.assistant(
        "", tool_calls=[ToolCall(id="1", name="shell", arguments={"command": "x"})]
    )
    again = Message.assistant(
        "", tool_calls=[ToolCall(id="2", name="shell", arguments={"command": "x"})]
    )
    agent = _degraded_agent([call, again], supports=False)
    agent.max_iterations = 5
    await _collect(agent, "go")
    assert agent.stopped_at_step_limit is False


async def test_resume_that_finishes_with_text_does_not_set_flag() -> None:
    auth = AuthRequiredStubTool(name="tool_b", auth_required_calls=1)
    agent = Agent(
        llm=FakeLLM([_call(1, "tool_b"), Message.assistant("done")]),
        tools=_make_registry(auth),
        system_prompt="t",
        max_iterations=3,
    )
    _install_auth_required_executor(agent, {"tool_b": auth})
    await _collect(agent, "go")
    [m async for m in agent.resume_after_auth()]
    assert agent.stopped_at_step_limit is False


async def test_resume_with_zero_budget_sets_flag() -> None:
    auth = AuthRequiredStubTool(name="tool_b", auth_required_calls=1)
    agent = Agent(
        llm=FakeLLM([_call(1, "tool_b")]),
        tools=_make_registry(auth),
        system_prompt="t",
        max_iterations=1,
    )
    _install_auth_required_executor(agent, {"tool_b": auth})
    await _collect(agent, "go")
    assert agent._remaining_iterations == 0
    assert agent.stopped_at_step_limit is False
    [m async for m in agent.resume_after_auth()]
    assert agent.stopped_at_step_limit is True


async def test_re_paused_resume_does_not_set_flag() -> None:
    auth = AuthRequiredStubTool(name="tool_b", auth_required_calls=2)
    agent = Agent(
        llm=FakeLLM([_call(1, "tool_b")]),
        tools=_make_registry(auth),
        system_prompt="t",
        max_iterations=1,
    )
    _install_auth_required_executor(agent, {"tool_b": auth})
    await _collect(agent, "go")
    [m async for m in agent.resume_after_auth()]
    assert agent._deferred_tool_calls is not None
    assert agent.stopped_at_step_limit is False


async def test_next_step_clears_flag() -> None:
    agent = Agent(
        llm=FakeLLM([_call(1), Message.assistant("fine")]),
        tools=_make_registry(StubTool("tool_a")),
        system_prompt="t",
        max_iterations=1,
    )
    await _collect(agent, "one")
    assert agent.stopped_at_step_limit is True
    agent.max_iterations = 2
    await _collect(agent, "two")
    assert agent.stopped_at_step_limit is False


async def test_resume_noop_clears_flag() -> None:
    agent = Agent(llm=FakeLLM([]), tools=_make_registry(), system_prompt="t")
    agent.stopped_at_step_limit = True
    [m async for m in agent.resume_after_auth()]
    assert agent.stopped_at_step_limit is False


async def test_reset_clears_flag() -> None:
    agent = Agent(llm=FakeLLM([]), tools=_make_registry(), system_prompt="t")
    agent.stopped_at_step_limit = True
    agent.reset()
    assert agent.stopped_at_step_limit is False


async def test_zero_max_iterations_sets_flag_at_once() -> None:
    agent = Agent(llm=FakeLLM([]), tools=_make_registry(), system_prompt="t", max_iterations=0)
    msgs = await _collect(agent, "go")
    assert msgs == []
    assert agent.stopped_at_step_limit is True
