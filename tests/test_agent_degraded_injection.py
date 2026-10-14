"""Chat-only degraded-path injection tests (M16 F03 L08C, #105).

M16 F03 L08C: non-tool-capable models (supports_tools()=False) are CHAT-ONLY.
The degraded system prompt is tool-free (PLATFORM_TOOL_FREE — no catalog, no
tool_code format spec, no continue-tool semantics). Recovery is gated OFF at the
provider level, so this agent-layer test suite only needs to verify:

- The degraded system message is tool-free (no catalog/format/tool_code).
- self.messages is not mutated (request copy only).
- The capable path is byte-identical to pre-leg behavior.

Retired (M16 F03 L08A tests, now moot):
- test_search_tools_dispatch_mutates_loaded_schemas_and_next_turn_rerenders
- test_backstop_does_not_misfire_on_search_then_different_concrete_tool
These tested the 08A discovery hop which 08C deletes.

test_degraded_loop_dispatches_recovered_tool_code is re-authored: the degraded
system prompt is tool-free (no catalog/format), and the agent-layer mock returns
structured tool_calls (which bypasses the provider recovery gate — that gate is
tested at the provider layer in test_ollama_provider_recovery.py). This pinning
test validates the _build_degraded_messages ephemeral-swap + dispatch wiring with
structured tool_calls (a legitimate path for future tool-capable-but-flag-gated
models or custom providers).

Hermetic: a capturing fake provider, no network.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from tests._old_prompts import OLD_PLATFORM_TOOL_FREE as PLATFORM_TOOL_FREE
from tests._old_prompts import OLD_PLATFORM_TOOLS as PLATFORM_TOOLS
from the_one.agent.config import compose_system_prompt
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
    """A registry holding shell + a (virtual) search_tools stub."""

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
    return compose_system_prompt(PLATFORM_TOOLS, persona)


def _degraded_prompt(persona: str = "You are Aria, terse and dry.") -> str:
    return compose_system_prompt(PLATFORM_TOOL_FREE, persona)


def _agent(llm: Any, persona: str = "You are Aria, terse and dry.") -> Agent:
    """An agent built the way the factory builds one: both prompts, passed in."""
    return Agent(
        llm=llm,
        tools=_registry_with_virtuals(),
        system_prompt=_system_prompt(persona),
        degraded_system_prompt=_degraded_prompt(persona),
    )


async def _collect(agent: Agent, user_input: str) -> list[Message]:
    msgs: list[Message] = []
    async for m in agent.step(user_input):
        msgs.append(m)
    return msgs


# ---------------------------------------------------------------------------
# Degraded branch — chat-only (M16 F03 L08C)
# ---------------------------------------------------------------------------


class TestDegradedInjection:
    async def test_chat_only_prompt_no_tool_sections(self) -> None:
        """M16 F03 L08C: degraded system message is tool-free.

        The chat-only prompt must contain:
        - NO tool catalog (no shell(command), no search_tools(query))
        - NO tool_code format spec
        - NO "Tool use" or "Tool discovery" sections
        - NO "continue" tool turn semantics
        Persona survives the base swap. Wire tools= is None.
        """
        llm = CapturingLLM([Message.assistant("ok")], supports=False)
        agent = _agent(llm)

        await _collect(agent, "hello there")

        sent = llm.calls[0]["messages"]
        # Exactly ONE leading system message (replace, not prepend).
        assert sent[0].role == Role.SYSTEM
        assert sum(1 for m in sent if m.role == Role.SYSTEM) == 1
        sys_content = sent[0].content

        # No tool catalog entries.
        assert "shell(command)" not in sys_content
        assert "search_tools(query)" not in sys_content
        # No tool protocol/format block.
        assert "```tool_code" not in sys_content
        # No tool sections.
        assert "Tool discovery:" not in sys_content
        assert "Tool use:" not in sys_content
        # No continue-tool turn semantics.
        assert "call the `continue` tool" not in sys_content
        # Persona survived the base swap.
        assert "You are Aria, terse and dry." in sys_content

        # Wire tools= is None on the degraded path.
        assert llm.calls[0]["tools"] is None

    async def test_degraded_prompt_is_the_one_built_at_agent_build_time(self) -> None:
        """The degraded system message is ``degraded_system_prompt``, verbatim."""
        llm = CapturingLLM([Message.assistant("ok")], supports=False)
        agent = _agent(llm)

        await _collect(agent, "hello")

        sent = llm.calls[0]["messages"]
        sys_content = sent[0].content
        # PLATFORM_TOOL_FREE is the base; its identity line must be present.
        assert "You are an AI assistant" in sys_content
        # The direct, concise response note is kept.
        assert "direct, concise responses" in sys_content
        assert sys_content == _degraded_prompt()

    async def test_without_a_degraded_prompt_the_system_prompt_is_sent_verbatim(self) -> None:
        """No ``degraded_system_prompt`` -> no prefix recovery, no swap."""
        llm = CapturingLLM([Message.assistant("ok")], supports=False)
        agent = Agent(llm=llm, tools=_registry_with_virtuals(), system_prompt=_system_prompt())
        assert agent.degraded_system_prompt is None

        await _collect(agent, "hello")

        assert llm.calls[0]["messages"][0].content == _system_prompt()

    async def test_self_messages_unmutated_and_tail_passthrough(self) -> None:
        """self.messages[0] remains the ORIGINAL (capable) system prompt."""
        llm = CapturingLLM([Message.assistant("ok")], supports=False)
        agent = _agent(llm)
        original_system = agent.messages[0].content

        await _collect(agent, "hello there")

        # self.messages[0] is the ORIGINAL system prompt (capable shape) —
        # the injection only touched the ephemeral request copy.
        assert agent.messages[0].content == original_system
        # The original has PLATFORM_TOOLS content (tool discovery block).
        assert "Tool discovery:" in agent.messages[0].content
        assert "```tool_code" not in agent.messages[0].content

        # The request captured at stream() time was [chat_only_system, user].
        sent = llm.calls[0]["messages"]
        assert len(sent) == 2  # swapped system + the one user turn
        assert sent[1].role == Role.USER
        assert sent[1].content == "hello there"
        assert sent[1].content == agent.messages[1].content

    async def test_degraded_loop_dispatches_structured_tool_calls(self) -> None:
        """Re-authored from test_degraded_loop_dispatches_recovered_tool_code (M16 F03 L08C).

        Under 08C the degraded system prompt is tool-free (no catalog/format). This
        test uses a CapturingLLM that returns pre-formed structured tool_calls directly
        (bypassing the provider recovery kernel, which is gated off for non-tool models).
        This pins the _build_degraded_messages ephemeral-swap wiring and the dispatch
        path with structured tool_calls — a valid path for custom providers or future
        models that return structured calls despite supports_tools()=False.

        The key assertions are:
        - The system prompt sent to the LLM is tool-free (no tool_code, no catalog).
        - The tool is dispatched and the loop completes normally.
        - tools= is None on the wire (degraded path).
        """
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

        # The shell tool was dispatched with the structured command.
        assert shell.calls == [{"command": "echo hi"}]
        # The loop produced: assistant(tool_call), tool result, assistant(done).
        assert [m.role for m in msgs] == [Role.ASSISTANT, Role.TOOL, Role.ASSISTANT]
        assert isinstance(msgs[1].tool_result, ToolResult)
        assert msgs[1].content == "ran: echo hi"
        # Both turns went out with tools=None (degraded).
        assert all(c["tools"] is None for c in llm.calls)
        # The system prompt sent was tool-free.
        sys_content = llm.calls[0]["messages"][0].content
        assert "```tool_code" not in sys_content
        assert "shell(command)" not in sys_content


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
