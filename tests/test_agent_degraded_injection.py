"""Degraded-path direct-tool-protocol injection tests (M16 F03 L08, #105).

Pins the agent-loop behavior on the non-tool-capable path:
- the leading system message of the request carries the direct-tool-protocol
  addendum AND does NOT carry the ``search_tools`` discovery instruction (DD-G);
- there is exactly ONE leading system message (replace, not prepend — DD-D);
- ``self.messages[1:]`` passes through unchanged and ``self.messages`` is
  UNMUTATED;
- ``tools=None`` on the wire for the degraded path;
- the tool-capable path is unchanged (no addendum, ``messages=self.messages``,
  the visible-schema array as ``tools=``);
- the full degraded loop dispatches a recovered ```tool_code call.

Hermetic: a capturing fake provider, no network. The recovery + positional
binding are covered by legs 01/07; this pins the *degraded loop wiring*.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from the_one.agent.config import BASE_PROMPT, compose_system_prompt
from the_one.agent.core import Agent
from the_one.llm.base import (
    LLMProvider,
    Message,
    Role,
    StreamChunk,
    ToolCall,
    ToolResult,
)
from the_one.tools.base import Tool, ToolRegistry


class CapturingLLM(LLMProvider):
    """Fake provider capturing the messages/tools it is streamed.

    ``supports_tools`` is configurable so the same provider exercises both the
    capable and degraded branches. ``responses`` is a list of Messages returned
    in order from ``stream()``.
    """

    name = "capturing"

    def __init__(self, responses: list[Message], *, supports: bool) -> None:
        self.responses = list(responses)
        self._supports = supports
        self.calls: list[dict[str, Any]] = []

    async def supports_tools(self) -> bool:
        return self._supports

    async def complete(  # pragma: no cover - agent loop calls stream(), not complete()
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
    ) -> Message:
        raise NotImplementedError("CapturingLLM only implements stream()")

    async def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
    ) -> AsyncIterator[StreamChunk]:
        # Capture COPIES of the list refs so later mutation of self.messages
        # can't retroactively change what we recorded.
        self.calls.append({"messages": list(messages), "tools": tools})
        msg = self.responses.pop(0)
        yield StreamChunk(
            content=msg.content,
            is_final=True,
            tool_calls=msg.tool_calls,
            usage=msg.usage,
            message=msg,
        )


class ShellLikeTool(Tool):
    """Minimal real-ish tool with a ``command`` parameter."""

    def __init__(self) -> None:
        self.name = "shell"
        self.description = "Execute a shell command."
        self.parameters: dict[str, Any] = {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        }
        self.calls: list[dict[str, Any]] = []

    async def execute(self, **kwargs: Any) -> str:
        self.calls.append(kwargs)
        return f"ran: {kwargs.get('command')}"


def _registry_with_virtuals() -> ToolRegistry:
    """A registry holding shell + a (virtual) search_tools stub.

    The catalog filter excludes search_tools/continue by name; including a
    search_tools entry here proves the exclusion fires.
    """

    class _SearchStub(Tool):
        def __init__(self) -> None:
            self.name = "search_tools"
            self.description = "Search every tool available to you."
            self.parameters = {"type": "object", "properties": {"query": {}}, "required": []}

        async def execute(self, **kwargs: Any) -> str:  # pragma: no cover - never dispatched
            return ""

    reg = ToolRegistry()
    reg.register(ShellLikeTool())
    reg.register(_SearchStub())
    return reg


def _system_prompt(persona: str = "You are Aria, terse and dry.") -> str:
    return compose_system_prompt(BASE_PROMPT, persona)


async def _collect(agent: Agent, user_input: str) -> list[Message]:
    msgs: list[Message] = []
    async for m in agent.step(user_input):
        msgs.append(m)
    return msgs


# ---------------------------------------------------------------------------
# Degraded branch
# ---------------------------------------------------------------------------


class TestDegradedInjection:
    async def test_addendum_injected_and_search_tools_suppressed(self) -> None:
        llm = CapturingLLM([Message.assistant("ok")], supports=False)
        reg = _registry_with_virtuals()
        system_prompt = _system_prompt()
        agent = Agent(llm=llm, tools=reg, system_prompt=system_prompt)

        await _collect(agent, "do a thing")

        sent = llm.calls[0]["messages"]
        # Exactly ONE leading system message (replace, not prepend).
        assert sent[0].role == Role.SYSTEM
        assert sum(1 for m in sent if m.role == Role.SYSTEM) == 1
        sys_content = sent[0].content

        # Addendum present.
        assert "```tool_code" in sys_content
        assert "shell(command)" in sys_content
        # search_tools NOT listed in the catalog (excluded by name, DD-B).
        assert "search_tools(query)" not in sys_content
        # DD-G: the search_tools discovery instruction is GONE.
        assert "call `search_tools`" not in sys_content
        assert "you have only `search_tools`" not in sys_content
        assert "Tool discovery:" not in sys_content
        # Persona survived the base swap.
        assert "You are Aria, terse and dry." in sys_content
        # Non-discovery base guidance kept.
        assert "Turn semantics:" in sys_content

        # Wire tools= is None on the degraded path.
        assert llm.calls[0]["tools"] is None

    async def test_self_messages_unmutated_and_tail_passthrough(self) -> None:
        llm = CapturingLLM([Message.assistant("ok")], supports=False)
        agent = Agent(llm=llm, tools=_registry_with_virtuals(), system_prompt=_system_prompt())
        original_system = agent.messages[0].content

        await _collect(agent, "hello there")

        # self.messages[0] is the ORIGINAL system prompt (capable shape) —
        # the injection only touched the ephemeral request copy.
        assert agent.messages[0].content == original_system
        assert "Tool discovery:" in agent.messages[0].content  # discovery NOT stripped here
        assert "```tool_code" not in agent.messages[0].content

        # The request captured at stream() time was [degraded_system, user] —
        # the user turn passed through verbatim (the assistant response is
        # appended to self.messages only AFTER the stream returns, so compare
        # against the captured request, not the post-run history).
        sent = llm.calls[0]["messages"]
        assert len(sent) == 2  # swapped system + the one user turn
        assert sent[1].role == Role.USER
        assert sent[1].content == "hello there"
        # And the user turn object is the same one in persisted history.
        assert sent[1].content == agent.messages[1].content

    async def test_degraded_loop_dispatches_recovered_tool_code(self) -> None:
        # The model returns a ```tool_code fenced call (no native tool_calls).
        # The Ollama recovery kernel normally lifts this; here we simulate the
        # *recovered* call shape the loop dispatches to pin the full degraded
        # loop end-to-end (recovery itself is covered by legs 01/07).
        tool_call_turn = Message.assistant(
            "",
            tool_calls=[ToolCall(id="shell_0", name="shell", arguments={"command": "echo hi"})],
        )
        final_turn = Message.assistant("done")
        llm = CapturingLLM([tool_call_turn, final_turn], supports=False)
        reg = _registry_with_virtuals()
        shell = reg.get("shell")
        agent = Agent(llm=llm, tools=reg, system_prompt=_system_prompt())

        msgs = await _collect(agent, "run echo hi")

        # The shell tool was dispatched with the recovered command.
        assert shell.calls == [{"command": "echo hi"}]
        # The loop produced: assistant(tool_call), tool result, assistant(done).
        assert [m.role for m in msgs] == [Role.ASSISTANT, Role.TOOL, Role.ASSISTANT]
        assert isinstance(msgs[1].tool_result, ToolResult)
        assert msgs[1].content == "ran: echo hi"
        # Both turns went out with tools=None (degraded).
        assert all(c["tools"] is None for c in llm.calls)


# ---------------------------------------------------------------------------
# Capable branch — byte-identical to pre-leg behavior
# ---------------------------------------------------------------------------


class TestCapableUnchanged:
    async def test_no_addendum_and_messages_are_self_messages(self) -> None:
        llm = CapturingLLM([Message.assistant("ok")], supports=True)
        agent = Agent(llm=llm, tools=_registry_with_virtuals(), system_prompt=_system_prompt())

        await _collect(agent, "do a thing")

        sent = llm.calls[0]["messages"]
        # The capable path passes self.messages directly (same object identity
        # for the leading system message content).
        assert sent[0].content == agent.messages[0].content
        assert "```tool_code" not in sent[0].content
        assert "Tool discovery:" in sent[0].content  # discovery block intact

        # tools= carries the visible-schema array (search_tools + continue at
        # minimum), NOT None.
        assert llm.calls[0]["tools"] is not None
        names = {t["name"] for t in llm.calls[0]["tools"]}
        assert "search_tools" in names
        assert "continue" in names
