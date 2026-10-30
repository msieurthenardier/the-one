"""Shared scaffolding for the routine-tool tests (M33 F2 L3): a real ``Agent`` with
``FakeLLM`` scripted calls, the real routine and notes tools bound to it, and a
schema-template database behind the connection singleton."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from _routine_schedules import once_in
from conftest import FakeLLM

from the_one.agent._context import TurnContext, current_turn
from the_one.agent.config import AgentConfig
from the_one.agent.core import Agent
from the_one.db.models import ChatSession
from the_one.db.repositories import ChatSessionRepository, SQLiteAgentStore
from the_one.interfaces.web.app import _bind_turn_user_marks
from the_one.llm.base import Message, Role, ToolCall
from the_one.notes.tool_provider import NotesToolProvider
from the_one.routines.tool_provider import RoutineToolProvider
from the_one.tools.base import Tool, ToolRegistry

NAME = "alpha"


class Stub(Tool):
    parameters: dict[str, Any] = {"type": "object", "properties": {}, "required": []}

    def __init__(self, name: str, output: str = "result") -> None:
        super().__init__()
        self.name = name
        self.description = f"stub {name}"
        self.output = output

    async def execute(self, **kwargs: Any) -> str:
        return self.output


def call(cid: str, tool: str, /, **args: Any) -> ToolCall:
    return ToolCall(id=cid, name=tool, arguments=args)


def asst(*calls: ToolCall) -> Message:
    return Message.assistant("", tool_calls=list(calls))


def done() -> Message:
    return Message.assistant("done")


IN_2H = once_in(2, "hours")


async def setup_agent(conn, *, approval: bool = False, name: str = NAME) -> None:
    store = SQLiteAgentStore(conn)
    await store.save(AgentConfig(name=name))
    await store.set_notes_enabled(name, True)
    await store.set_routines_self_config(name, enabled=True, requires_approval=approval)


async def add_chat(conn, sid: str, agent: str = NAME) -> None:
    await ChatSessionRepository(conn).create(ChatSession(id=sid, agent_name=agent, title="t"))


async def make_agent(
    responses: list[Message], *extra: Tool, llm: FakeLLM | None = None, name: str = NAME
) -> Agent:
    reg = ToolRegistry()
    for t in extra:
        reg.register(t)
    reg.register(Stub("fetch_url", "PAGE TEXT"))
    cfg = AgentConfig(name=name, notes_enabled=True, routines_self_config_enabled=True)
    tools = await NotesToolProvider().get_tools_for_agent(cfg, agent_name=name)
    tools += await RoutineToolProvider().get_tools_for_agent(cfg, agent_name=name)
    for t in tools:
        reg.register(t)
    agent = Agent(llm=llm or FakeLLM(responses), tools=reg, system_prompt="sys")
    for t in tools:
        t.bind_agent(agent)  # type: ignore[attr-defined]
    return agent


async def run_turn(
    agent: Agent,
    text: str = "go",
    *,
    session_id: str | None = "sess-1",
    ctx: TurnContext | None = None,
    routine: dict[str, Any] | None = None,
    bind: bool = False,
) -> tuple[list[Message], TurnContext]:
    """One step. ``routine`` builds the TurnContext the app builds for a routine run;
    ``bind`` then binds the turn's marks onto the USER message like the app's post-step."""
    if ctx is None:
        ctx = TurnContext(session_id=session_id)
        if routine is not None:
            ctx.routine_id = routine.get("id")
            ctx.routine_name = routine.get("name")
            ctx.routine_sources = list(routine.get("untrusted_sources") or [])
    pre = len(agent.messages)
    token = current_turn.set(ctx)
    try:
        out = [m async for m in agent.step(text)]
    finally:
        current_turn.reset(token)
    if bind:
        _bind_turn_user_marks(SimpleNamespace(agent=agent, platform=None), pre, routine)  # type: ignore[arg-type]
    return out, ctx


def results(msgs: list[Message]):
    return [m.tool_result for m in msgs if m.role == Role.TOOL and m.tool_result]
