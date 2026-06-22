"""Redundant-tool-call loop backstop tests (M16 F03 L09, #105).

CP4 fix: on the DEGRADED path (``supports_tools`` False) gemma3:4b re-emits a
tool call whose result it already holds and terminates with an empty message —
leaving an empty final assistant message (no answer). This pins the
dispatch-side backstop:

- Executed-map keyed on (name, canonical-json(RAW args)) → result content.
- Partition each degraded response into new vs redundant; dispatch only new.
- All-redundant + empty content → REPLACE the empty terminal message with a
  synthesized closing surfacing the prior result(s) (DD-C); no empty assistant
  message and no orphaned tool_calls left in agent.messages.
- All-redundant + non-empty text → keep the text, clear leftover tool_calls,
  no synthesized closing, no duplicate message (DD-C2).
- The capable path (supports_tools True) is unaffected — a re-emitted identical
  call is NOT short-circuited (DD-D).

Hermetic: a scripted fake provider, no network. Recovery + positional binding
are covered by legs 01/07; this pins the loop backstop.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from the_one.agent.config import BASE_PROMPT, compose_system_prompt
from the_one.agent.core import Agent, _executed_key, _synthesize_closing
from the_one.llm.base import (
    LLMProvider,
    Message,
    Role,
    StreamChunk,
    ToolCall,
)
from the_one.tools.base import Tool, ToolRegistry


class ScriptedLLM(LLMProvider):
    """Fake provider replaying a scripted sequence of assistant Messages.

    ``supports`` selects the capable vs degraded branch. Each ``stream()`` call
    pops the next Message from ``responses``.
    """

    name = "scripted"

    def __init__(self, responses: list[Message], *, supports: bool) -> None:
        self.responses = list(responses)
        self._supports = supports
        self.calls: list[dict[str, Any]] = []

    async def supports_tools(self) -> bool:
        return self._supports

    async def complete(  # pragma: no cover - loop uses stream()
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
    ) -> Message:
        raise NotImplementedError("ScriptedLLM only implements stream()")

    async def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
    ) -> AsyncIterator[StreamChunk]:
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
    """Minimal shell-ish tool recording its dispatched args."""

    def __init__(self, output: str = "hi") -> None:
        self.name = "shell"
        self.description = "Execute a shell command."
        self.parameters: dict[str, Any] = {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        }
        self._output = output
        self.calls: list[dict[str, Any]] = []

    def bind_positional_args(self, arguments: dict[str, Any]) -> dict[str, Any]:
        # Mirror the real positional-recovery binding: a recovered gemma call
        # arrives as {"__positional_args__": [...]} and binds to ``command``.
        # Crucially this does NOT mutate the passed ``arguments`` dict — the
        # ToolCall's raw shape stays stable across re-emissions (DD-A).
        if "__positional_args__" in arguments:
            pos = arguments["__positional_args__"]
            return {"command": pos[0] if pos else ""}
        return dict(arguments)

    async def execute(self, **kwargs: Any) -> str:
        self.calls.append(kwargs)
        return f"ran: {kwargs.get('command')} -> {self._output}"


class _SearchStub(Tool):
    def __init__(self) -> None:
        self.name = "search_tools"
        self.description = "Search every tool available to you."
        self.parameters = {"type": "object", "properties": {"query": {}}, "required": []}

    async def execute(self, **kwargs: Any) -> str:  # pragma: no cover - never dispatched
        return ""


def _registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(ShellLikeTool())
    reg.register(_SearchStub())
    return reg


def _system_prompt() -> str:
    return compose_system_prompt(BASE_PROMPT, "You are Aria.")


def _agent(responses: list[Message], *, supports: bool, reg: ToolRegistry | None = None) -> Agent:
    reg = reg or _registry()
    llm = ScriptedLLM(responses, supports=supports)
    return Agent(llm=llm, tools=reg, system_prompt=_system_prompt())


async def _collect(agent: Agent, user_input: str) -> list[Message]:
    return [m async for m in agent.step(user_input)]


def _recovered_call(idx: int, command: str = "echo hi") -> ToolCall:
    """A gemma-recovered call: raw positional args + a fresh synthesized id.

    Each re-emission gets a DIFFERENT id (``shell_{idx}``) but the SAME raw
    arguments shape — so id-based lookup of the prior result would fail; the
    executed-map keys on (name, args) instead (DD-A).
    """
    return ToolCall(id=f"shell_{idx}", name="shell", arguments={"__positional_args__": [command]})


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestExecutedKey:
    def test_key_stable_across_reemissions_despite_id_change(self) -> None:
        # Two re-emissions: different ids, same raw args → same key.
        a = _recovered_call(0)
        b = _recovered_call(5)
        assert a.id != b.id
        assert _executed_key(a) == _executed_key(b)

    def test_key_order_insensitive(self) -> None:
        a = ToolCall(id="x", name="t", arguments={"a": 1, "b": 2})
        b = ToolCall(id="y", name="t", arguments={"b": 2, "a": 1})
        assert _executed_key(a) == _executed_key(b)

    def test_distinct_calls_distinct_keys(self) -> None:
        a = _recovered_call(0, "echo hi")
        b = _recovered_call(1, "echo bye")
        assert _executed_key(a) != _executed_key(b)


class TestSynthesizeClosing:
    def test_single_result_non_empty(self) -> None:
        out = _synthesize_closing([("shell", "ran: echo hi", False)])
        assert out.strip()
        assert "shell" in out
        assert "ran: echo hi" in out

    def test_error_marked_as_failure(self) -> None:
        out = _synthesize_closing([("shell", "boom", True)])
        assert "failed" in out.lower()
        assert "boom" in out

    def test_multiple_results_compact_list(self) -> None:
        out = _synthesize_closing([("shell", "out-a", False), ("shell", "out-b", False)])
        assert "out-a" in out
        assert "out-b" in out

    def test_oversized_result_truncated(self) -> None:
        from the_one.db.codec import MAX_TOOL_RESULT_INLINE_CONTENT

        huge = "x" * (MAX_TOOL_RESULT_INLINE_CONTENT + 5000)
        out = _synthesize_closing([("shell", huge, False)])
        assert len(out) < len(huge)
        assert "x" * 100 in out  # some content preserved


# ---------------------------------------------------------------------------
# DD-C: all-redundant + empty content → REPLACE the empty terminal message
# ---------------------------------------------------------------------------


class TestAllRedundantBackstop:
    async def test_backstop_replaces_empty_message_with_closing(self) -> None:
        # Iter 1: a recovered call (dispatched). Iter 2: the SAME call again +
        # empty content → backstop fires, replacing the empty message.
        responses = [
            Message.assistant("", tool_calls=[_recovered_call(0)]),
            Message.assistant("", tool_calls=[_recovered_call(1)]),
        ]
        reg = _registry()
        shell = reg.get("shell")
        agent = _agent(responses, supports=False, reg=reg)

        msgs = await _collect(agent, "run echo hi")

        # The tool dispatched exactly ONCE (the redundant re-emission suppressed).
        assert shell.calls == [{"command": "echo hi"}]

        # The bite — assert directly on agent.messages. The dangling artifact
        # the backstop must avoid is the EMPTY terminal assistant message that
        # still carries its redundant (undispatched) tool_calls. (The iter-1
        # assistant message legitimately has empty content + tool_calls — but
        # those calls WERE dispatched and are followed by a tool_result, so it
        # is not orphaned.)
        all_tool_call_ids = {tc.id for m in agent.messages for tc in m.tool_calls}
        all_result_ids = {
            m.tool_result.tool_call_id for m in agent.messages if m.tool_result is not None
        }
        # No orphaned tool_call: every emitted tool_call has a following result.
        assert all_tool_call_ids <= all_result_ids, all_tool_call_ids - all_result_ids
        # No empty-content assistant message that ALSO carries tool_calls
        # (the exact stray-message-with-orphans signature the backstop kills).
        assert not [
            m
            for m in agent.messages
            if m.role == Role.ASSISTANT
            and not m.content.strip()
            and m.tool_calls
            and any(tc.id not in all_result_ids for tc in m.tool_calls)
        ]
        # The final assistant message is the synthesized, non-empty closing
        # (NOT an empty terminal message) and carries no tool_calls.
        assert agent.messages[-1].role == Role.ASSISTANT
        assert agent.messages[-1].content.strip()
        assert not agent.messages[-1].tool_calls
        assert "ran: echo hi" in agent.messages[-1].content

        # Exactly one TOOL message (the single real dispatch).
        tool_msgs = [m for m in agent.messages if m.role == Role.TOOL]
        assert len(tool_msgs) == 1

        # The last yielded message is the closing too.
        assert msgs[-1].content == agent.messages[-1].content

    async def test_backstop_surfaces_error_result(self) -> None:
        class FailingShell(ShellLikeTool):
            async def execute(self, **kwargs: Any) -> str:
                self.calls.append(kwargs)
                raise RuntimeError("kaboom")

        reg = ToolRegistry()
        reg.register(FailingShell())
        reg.register(_SearchStub())
        responses = [
            Message.assistant("", tool_calls=[_recovered_call(0)]),
            Message.assistant("", tool_calls=[_recovered_call(1)]),
        ]
        agent = _agent(responses, supports=False, reg=reg)

        await _collect(agent, "run echo hi")

        closing = agent.messages[-1]
        assert closing.role == Role.ASSISTANT
        assert closing.content.strip()
        assert "failed" in closing.content.lower()


# ---------------------------------------------------------------------------
# DD-B: partition — dispatch only the new call
# ---------------------------------------------------------------------------


class TestPartition:
    async def test_only_new_call_dispatched(self) -> None:
        # Iter 1: dispatch echo hi. Iter 2: redundant echo hi + NEW echo bye →
        # only echo bye dispatches. Iter 3: text answer ends the turn.
        responses = [
            Message.assistant("", tool_calls=[_recovered_call(0, "echo hi")]),
            Message.assistant(
                "",
                tool_calls=[_recovered_call(1, "echo hi"), _recovered_call(2, "echo bye")],
            ),
            Message.assistant("all done"),
        ]
        reg = _registry()
        shell = reg.get("shell")
        agent = _agent(responses, supports=False, reg=reg)

        await _collect(agent, "go")

        # echo hi dispatched once (iter 1); echo bye dispatched once (iter 2).
        # The redundant echo hi in iter 2 was dropped.
        assert shell.calls == [{"command": "echo hi"}, {"command": "echo bye"}]
        assert agent.messages[-1].content == "all done"


# ---------------------------------------------------------------------------
# DD-C2: all-redundant + non-empty text → keep text, clear tool_calls
# ---------------------------------------------------------------------------


class TestRedundantButText:
    async def test_text_kept_tool_calls_cleared_no_synthesis(self) -> None:
        responses = [
            Message.assistant("", tool_calls=[_recovered_call(0)]),
            Message.assistant("Here is the answer.", tool_calls=[_recovered_call(1)]),
        ]
        reg = _registry()
        shell = reg.get("shell")
        agent = _agent(responses, supports=False, reg=reg)

        msgs = await _collect(agent, "go")

        # Only the first call dispatched; the redundant re-emission not run.
        assert shell.calls == [{"command": "echo hi"}]
        # The model's own text IS the answer — not the synthesized closing.
        assert agent.messages[-1].content == "Here is the answer."
        assert "Done. The output" not in agent.messages[-1].content
        # Its leftover (undispatched) tool_calls were cleared.
        assert agent.messages[-1].tool_calls == []
        # No duplicate trailing assistant message was appended.
        assert msgs[-1].content == "Here is the answer."
        assistants = [m for m in agent.messages if m.role == Role.ASSISTANT]
        assert assistants[-1].content == "Here is the answer."


# ---------------------------------------------------------------------------
# DD-D: capable path is unaffected — re-emitted call is NOT short-circuited
# ---------------------------------------------------------------------------


class TestCapablePathUnchanged:
    async def test_capable_reemitted_call_still_dispatched(self) -> None:
        # supports_tools True. Same (name,args) re-emitted across iterations →
        # dispatched BOTH times (today's behavior — e.g. re-polling shell("date")).
        call_a = ToolCall(id="c0", name="shell", arguments={"command": "date"})
        call_b = ToolCall(id="c1", name="shell", arguments={"command": "date"})
        responses = [
            Message.assistant("", tool_calls=[call_a]),
            Message.assistant("", tool_calls=[call_b]),
            Message.assistant("final"),
        ]
        reg = _registry()
        shell = reg.get("shell")
        agent = _agent(responses, supports=True, reg=reg)

        await _collect(agent, "what time is it")

        # Dispatched BOTH times — no short-circuit on the capable path.
        assert shell.calls == [{"command": "date"}, {"command": "date"}]
        assert agent.messages[-1].content == "final"


# ---------------------------------------------------------------------------
# No false positives
# ---------------------------------------------------------------------------


class TestNoFalsePositives:
    async def test_clean_multistep_dispatches_all(self) -> None:
        # Distinct new calls each iteration → all dispatch, backstop never fires.
        responses = [
            Message.assistant("", tool_calls=[_recovered_call(0, "echo a")]),
            Message.assistant("", tool_calls=[_recovered_call(1, "echo b")]),
            Message.assistant("", tool_calls=[_recovered_call(2, "echo c")]),
            Message.assistant("done"),
        ]
        reg = _registry()
        shell = reg.get("shell")
        agent = _agent(responses, supports=False, reg=reg)

        await _collect(agent, "go")

        assert shell.calls == [
            {"command": "echo a"},
            {"command": "echo b"},
            {"command": "echo c"},
        ]
        assert agent.messages[-1].content == "done"

    async def test_normal_single_call_then_text(self) -> None:
        # Single call → result → text answer is unaffected (degraded path).
        responses = [
            Message.assistant("", tool_calls=[_recovered_call(0)]),
            Message.assistant("The output was hi."),
        ]
        reg = _registry()
        shell = reg.get("shell")
        agent = _agent(responses, supports=False, reg=reg)

        await _collect(agent, "go")

        assert shell.calls == [{"command": "echo hi"}]
        assert agent.messages[-1].content == "The output was hi."
        # No synthesized closing; the model's text stands.
        assert "Done. The output of" not in agent.messages[-1].content
