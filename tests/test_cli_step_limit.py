"""The CLI's step-limit line (M31 F6 leg 06, DD8)."""

from __future__ import annotations

from conftest import FakeLLM, StubTool
from rich.console import Console

from the_one.agent.core import Agent
from the_one.interfaces import cli
from the_one.llm.base import Message, ToolCall
from the_one.tools.base import ToolRegistry


async def _turn(responses: list[Message], max_iterations: int) -> Agent:
    reg = ToolRegistry()
    reg.register(StubTool("tool_a"))
    agent = Agent(
        llm=FakeLLM(responses), tools=reg, system_prompt="t", max_iterations=max_iterations
    )
    async for _ in agent.step("go"):
        pass
    return agent


def _capture(monkeypatch) -> Console:
    console = Console(record=True, width=200)
    monkeypatch.setattr(cli, "console", console)
    return console


def _call(i: int) -> Message:
    return Message.assistant("", tool_calls=[ToolCall(id=f"c{i}", name="tool_a", arguments={})])


async def test_exhausted_turn_prints_the_line(monkeypatch) -> None:
    console = _capture(monkeypatch)
    agent = await _turn([_call(1), _call(2)], 2)
    cli._print_step_limit_notice(agent)
    assert console.export_text().strip() == (
        "Stopped: this agent used its 2 steps for this message. "
        "Send another message to continue, or raise Max iterations in its settings."
    )


async def test_normal_turn_prints_nothing(monkeypatch) -> None:
    console = _capture(monkeypatch)
    agent = await _turn([Message.assistant("hi")], 2)
    cli._print_step_limit_notice(agent)
    assert console.export_text() == ""


def test_count_is_left_out_below_one() -> None:
    assert cli.step_limit_text(0).startswith(
        "Stopped: this agent reached its step limit for this message."
    )
