"""TurnContext premise (Mission 27 F2 L2, AC2/AC3): a context set around
``Agent.step`` is visible AND mutable inside ``tool.execute`` (the divert
condition for the frozen-loop design, DD5)."""

from __future__ import annotations

from typing import Any

import pytest
from conftest import FakeLLM

from the_one.agent._context import TurnContext, TurnPeer, current_turn
from the_one.agent.core import Agent
from the_one.llm.base import Message, ToolCall
from the_one.tools.base import Tool, ToolRegistry


class _CtxTool(Tool):
    name = "ctx_probe"
    description = "reads and bumps the turn context"
    parameters: dict[str, Any] = {"type": "object", "properties": {}, "required": []}

    def __init__(self) -> None:
        super().__init__()
        self.seen: TurnContext | None = None

    async def execute(self, **kwargs: Any) -> str:
        ctx = current_turn.get()
        self.seen = ctx
        assert ctx is not None
        ctx.writes += 1
        return "ok"


@pytest.mark.asyncio
async def test_turn_context_is_visible_and_mutable_inside_execute() -> None:
    tool = _CtxTool()
    reg = ToolRegistry()
    reg.register(tool)
    llm = FakeLLM(
        [
            Message.assistant("", tool_calls=[ToolCall(id="c1", name="ctx_probe", arguments={})]),
            Message.assistant("done"),
        ]
    )
    agent = Agent(llm=llm, tools=reg, system_prompt="sys")
    ctx = TurnContext(peer=None, session_id="s1")
    token = current_turn.set(ctx)
    try:
        async for _ in agent.step("go"):
            pass
    finally:
        current_turn.reset(token)
    assert tool.seen is ctx
    assert ctx.writes == 1
    assert current_turn.get() is None


def test_turn_peer_fields() -> None:
    p = TurnPeer(platform="discord", connector_id="c", peer_id="p", peer_name="Pat")
    assert (p.platform, p.connector_id, p.peer_id, p.peer_name) == ("discord", "c", "p", "Pat")
