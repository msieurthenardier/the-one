"""Tests for Agent loop (Agent.step())."""

from __future__ import annotations

from typing import Any

from conftest import FakeLLM, StubTool

from the_one.agent.core import Agent
from the_one.llm.base import Message, Role, ToolCall, ToolResult
from the_one.mcp.errors import MCPAuthRequired
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
        agent = Agent(llm=llm, tools=_make_registry(), system_prompt="test")
        msgs = await _collect(agent, "hi")

        assert len(msgs) == 1
        assert msgs[0].role == Role.ASSISTANT
        assert msgs[0].content == "hello"


class TestToolExecution:
    async def test_tool_call_then_final_response(self) -> None:
        """LLM calls a tool, gets result, then responds with text."""
        tool_a = StubTool("tool_a")
        llm = FakeLLM(
            [
                Message.assistant(
                    "",
                    tool_calls=[ToolCall(id="1", name="tool_a", arguments={})],
                ),
                Message.assistant("done"),
            ]
        )
        agent = Agent(llm=llm, tools=_make_registry(tool_a), system_prompt="test")
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


class TestContinueSignal:
    async def test_continue_not_yielded_to_caller(self) -> None:
        """Continue tool result is NOT yielded, but the loop continues."""
        tool_a = StubTool("tool_a")
        llm = FakeLLM(
            [
                # Iteration 1: LLM calls continue
                Message.assistant(
                    "thinking...",
                    tool_calls=[
                        ToolCall(id="1", name="continue", arguments={"reason": "more work"})
                    ],
                ),
                # Iteration 2: LLM responds with final text
                Message.assistant("all done"),
            ]
        )
        agent = Agent(llm=llm, tools=_make_registry(tool_a), system_prompt="test")
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
        agent = Agent(llm=llm, tools=_make_registry(tool_a), max_iterations=2, system_prompt="test")
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
        llm = FakeLLM(
            [
                Message.assistant(
                    "",
                    tool_calls=[ToolCall(id="1", name="bad_tool", arguments={})],
                ),
                Message.assistant("sorry about that"),
            ]
        )
        agent = Agent(llm=llm, tools=_make_registry(bad), system_prompt="test")
        msgs = await _collect(agent, "call bad_tool")

        assert len(msgs) == 3
        assert msgs[1].role == Role.TOOL
        assert msgs[1].tool_result is not None
        assert msgs[1].tool_result.is_error is True
        assert "kaboom" in msgs[1].content


class TestCredentialsRejected:
    async def test_rejected_credentials_is_an_error_result_without_auth_metadata(self) -> None:
        """Sortie 04 DD4: MCPCredentialsRejected (an MCPConnectionError) reaches the
        generic arm: an error tool result, no ``is_auth_required`` metadata, so chat
        offers no login button."""
        from the_one.mcp.errors import MCPCredentialsRejected

        class _Rejected(Tool):
            name = "rejected_tool"
            description = "always rejected"
            parameters: dict[str, Any] = {"type": "object", "properties": {}, "required": []}

            async def execute(self, **kwargs: Any) -> str:
                raise MCPCredentialsRejected("src-1", "goldfinch")

        llm = FakeLLM(
            [
                Message.assistant(
                    "", tool_calls=[ToolCall(id="1", name="rejected_tool", arguments={})]
                ),
                Message.assistant("done"),
            ]
        )
        agent = Agent(llm=llm, tools=_make_registry(_Rejected()), system_prompt="test")
        msgs = await _collect(agent, "go")
        result = msgs[1].tool_result
        assert result is not None
        assert result.is_error is True
        assert not (result.metadata or {}).get("is_auth_required")
        assert "rejected the configured credentials" in msgs[1].content


class TestReset:
    async def test_reset_clears_to_system_prompt(self) -> None:
        """After step, reset() leaves only the system prompt."""
        llm = FakeLLM([Message.assistant("hi")])
        agent = Agent(llm=llm, tools=_make_registry(), system_prompt="test")
        await _collect(agent, "hello")

        assert len(agent.messages) > 1  # system + user + assistant
        agent.reset()
        assert len(agent.messages) == 1
        assert agent.messages[0].role == Role.SYSTEM


# ---------------------------------------------------------------------------
# F5 L3 — pause/resume tests
#
# These are FLAT module-level functions (NOT class methods) per
# cycle-2 NEW-M1 — keeps the new test surface easy to scan and avoids
# accidental fixture-scope coupling with the legacy Test* classes above.
# ---------------------------------------------------------------------------


class AuthRequiredStubTool(Tool):
    """Stub tool whose first invocation returns ``metadata.is_auth_required=True``.

    Tracks ``self.calls`` (list — matches StubTool's contract per
    cycle-1 D4) so tests assert ``len(tool.calls) == 0`` for
    not-invoked tools and ``== N`` for the resume path.

    A tool that flips to ``is_auth_required=False`` after the first
    invocation can be configured via ``auth_required_calls``: any call
    index >= that value returns success. Default is "always
    auth_required" — tests that need success after one call set
    ``auth_required_calls=1``.
    """

    def __init__(
        self,
        name: str = "auth_tool",
        source_id: str = "src1",
        auth_required_calls: int = 999,
        success_content: str = "ok",
    ) -> None:
        self.name = name
        self.description = "A tool that requires auth on the first call."
        self.parameters: dict[str, Any] = {
            "type": "object",
            "properties": {},
            "required": [],
        }
        self.calls: list[dict[str, Any]] = []
        self._source_id = source_id
        self._auth_required_calls = auth_required_calls
        self._success_content = success_content

    async def execute(self, **kwargs: Any) -> str:
        # A real tool returning auth_required would do so via the
        # ``ToolResult.metadata`` field, NOT by raising. Since the
        # stub Tool interface forces us to return a string, we patch
        # ``Agent._execute_tool`` in tests instead — see the helper
        # ``_install_auth_required_executor`` below.
        self.calls.append(kwargs)
        return self._success_content


def _install_auth_required_executor(
    agent: Agent,
    auth_tools: dict[str, AuthRequiredStubTool],
) -> None:
    """Monkey-patch ``Agent._execute_tool`` so configured tools return
    ``ToolResult(metadata={"is_auth_required": True, ...})`` for the first
    ``auth_required_calls`` invocations.

    Needed because the public ``Tool.execute`` contract returns a plain
    string. L4 will be the first production caller that puts
    auth_required metadata on a real ``ToolResult`` (via
    ``MCPClient.call_tool`` raising ``MCPAuthRequired``); L3 tests
    simulate that here via a monkeypatched executor.
    """
    original_execute = agent._execute_tool

    async def patched(tool_call: ToolCall) -> ToolResult:
        tool = auth_tools.get(tool_call.name)
        if tool is None:
            return await original_execute(tool_call)
        # Count the call up-front so the next-iteration check sees it.
        tool.calls.append(dict(tool_call.arguments))
        if len(tool.calls) <= tool._auth_required_calls:
            return ToolResult(
                tool_call_id=tool_call.id,
                content="auth required",
                metadata={
                    "is_auth_required": True,
                    "source_id": tool._source_id,
                    "resource_metadata_url": f"https://{tool._source_id}/.well-known/oauth-protected-resource",
                    "tool_call_id": tool_call.id,
                },
            )
        return ToolResult(
            tool_call_id=tool_call.id,
            content=tool._success_content,
        )

    agent._execute_tool = patched  # type: ignore[method-assign]


async def test_pause_at_single_tool_defers_and_exits() -> None:
    """A1/A3: a single tool returning auth_required pauses the step."""
    auth_tool = AuthRequiredStubTool(name="auth_tool")
    llm = FakeLLM(
        [
            Message.assistant(
                "",
                tool_calls=[ToolCall(id="tc_a", name="auth_tool", arguments={})],
            ),
        ]
    )
    agent = Agent(
        llm=llm,
        tools=_make_registry(auth_tool),
        system_prompt="test",
        max_iterations=20,
    )
    _install_auth_required_executor(agent, {"auth_tool": auth_tool})

    msgs = await _collect(agent, "trigger auth")

    # Yields: assistant (with tool_call) + auth_required tool_msg = 2
    assert len(msgs) == 2
    assert msgs[0].role == Role.ASSISTANT
    assert msgs[1].role == Role.TOOL
    assert msgs[1].tool_result is not None
    assert msgs[1].tool_result.metadata is not None
    assert msgs[1].tool_result.metadata.get("is_auth_required") is True

    # Pause state set
    assert agent._deferred_tool_calls is not None
    assert [tc.id for tc in agent._deferred_tool_calls] == ["tc_a"]
    # max_iterations=20, paused after iteration 0 → 19 remain
    assert agent._remaining_iterations == 19
    # Step exited without a follow-up assistant
    assert len(llm.calls) == 1


async def test_pause_at_tc_b_defers_tc_b_and_tc_c() -> None:
    """A4: multi-tool deferral — tc_A succeeds, tc_B pauses, tc_C not invoked.

    Iteration counter (cycle-1 D8 lock): pause-during-iteration-i CONSUMES
    iteration i; with ``max_iterations=3``, ``_remaining_iterations == 2``.
    """
    tool_a = StubTool("tool_a")
    auth_tool_b = AuthRequiredStubTool(name="tool_b")
    tool_c = StubTool("tool_c")
    llm = FakeLLM(
        [
            Message.assistant(
                "",
                tool_calls=[
                    ToolCall(id="tc_a", name="tool_a", arguments={}),
                    ToolCall(id="tc_b", name="tool_b", arguments={}),
                    ToolCall(id="tc_c", name="tool_c", arguments={}),
                ],
            ),
        ]
    )
    agent = Agent(
        llm=llm,
        tools=_make_registry(tool_a, auth_tool_b, tool_c),
        system_prompt="test",
        max_iterations=3,
    )
    _install_auth_required_executor(agent, {"tool_b": auth_tool_b})

    msgs = await _collect(agent, "trigger")

    # Yields: assistant + tc_a tool_msg + tc_b auth_required tool_msg = 3
    assert len(msgs) == 3
    assert msgs[1].tool_result is not None
    assert msgs[1].tool_result.tool_call_id == "tc_a"
    assert msgs[1].tool_result.metadata is None
    assert msgs[2].tool_result is not None
    assert msgs[2].tool_result.tool_call_id == "tc_b"
    assert msgs[2].tool_result.metadata is not None
    assert msgs[2].tool_result.metadata.get("is_auth_required") is True

    # Deferred = current + remaining (NOT just tc_C)
    assert agent._deferred_tool_calls is not None
    assert [tc.id for tc in agent._deferred_tool_calls] == ["tc_b", "tc_c"]
    # tc_C NOT invoked — cycle-1 D4: .calls list, not .call_count
    assert len(tool_c.calls) == 0
    # Pause-on-iteration-0 consumes iteration 0 — 2 remain (cycle-1 D8 lock)
    assert agent._remaining_iterations == 2


async def test_resume_after_auth_redispatches_deferred_and_continues() -> None:
    """A5: resume_after_auth re-dispatches deferred + runs next LLM iteration."""
    tool_a = StubTool("tool_a")
    # tool_b becomes successful on resume — auth_required only on the
    # first invocation; the second (resume) invocation succeeds.
    auth_tool_b = AuthRequiredStubTool(name="tool_b", auth_required_calls=1, success_content="b ok")
    tool_c = StubTool("tool_c")
    llm = FakeLLM(
        [
            Message.assistant(
                "",
                tool_calls=[
                    ToolCall(id="tc_a", name="tool_a", arguments={}),
                    ToolCall(id="tc_b", name="tool_b", arguments={}),
                    ToolCall(id="tc_c", name="tool_c", arguments={}),
                ],
            ),
            # Iteration 1 (after resume re-enters _run_iterations) — done.
            Message.assistant("all done"),
        ]
    )
    agent = Agent(
        llm=llm,
        tools=_make_registry(tool_a, auth_tool_b, tool_c),
        system_prompt="test",
        max_iterations=3,
    )
    _install_auth_required_executor(agent, {"tool_b": auth_tool_b})

    # First step: pauses on tc_b
    await _collect(agent, "trigger")
    assert agent._deferred_tool_calls is not None

    # Resume — yields tc_b success + tc_c success + final assistant
    resume_msgs: list[Message] = []
    async for m in agent.resume_after_auth():
        resume_msgs.append(m)

    # tc_b tool_msg + tc_c tool_msg + assistant text = 3 messages
    assert len(resume_msgs) == 3
    assert resume_msgs[0].tool_result is not None
    assert resume_msgs[0].tool_result.tool_call_id == "tc_b"
    assert resume_msgs[0].tool_result.metadata is None  # success path
    assert resume_msgs[1].tool_result is not None
    assert resume_msgs[1].tool_result.tool_call_id == "tc_c"
    assert resume_msgs[2].role == Role.ASSISTANT
    assert resume_msgs[2].content == "all done"

    # Pause state cleared after successful resume
    assert agent._deferred_tool_calls is None


async def test_resume_after_auth_with_no_deferred_state_is_noop() -> None:
    """A7: resume_after_auth on a fresh agent yields nothing and skips the LLM."""
    llm = FakeLLM([])
    agent = Agent(llm=llm, tools=_make_registry(), system_prompt="test")

    msgs = [m async for m in agent.resume_after_auth()]
    assert msgs == []
    # Did NOT touch LLM
    assert len(llm.calls) == 0
    # Did NOT touch messages (only system prompt remains)
    assert len(agent.messages) == 1
    assert agent.messages[0].role == Role.SYSTEM


async def test_resume_re_pauses_when_tool_returns_auth_required_again() -> None:
    """A8 + A8b: tc_B re-pauses on resume (token revoked); second resume completes.

    A8b head-of-list re-pause: first iteration's tool calls are
    ``[tc_a_auth, tc_b_auth, tc_c]`` so the FIRST tool of a multi-tool
    iteration returns auth_required. This confirms the
    slice-from-current-index pattern works at index 0.
    """
    # tool_a needs auth on call #1; succeeds on call #2 (after first resume)
    auth_tool_a = AuthRequiredStubTool(name="tool_a", auth_required_calls=1, success_content="a ok")
    # tool_b needs auth on call #1 (during the first resume — that's its
    # first invocation since tc_a paused the initial step); succeeds on
    # call #2 (during the second resume).
    auth_tool_b = AuthRequiredStubTool(name="tool_b", auth_required_calls=1, success_content="b ok")
    tool_c = StubTool("tool_c")
    llm = FakeLLM(
        [
            Message.assistant(
                "",
                tool_calls=[
                    ToolCall(id="tc_a", name="tool_a", arguments={}),
                    ToolCall(id="tc_b", name="tool_b", arguments={}),
                    ToolCall(id="tc_c", name="tool_c", arguments={}),
                ],
            ),
            Message.assistant("all done"),
        ]
    )
    agent = Agent(
        llm=llm,
        tools=_make_registry(auth_tool_a, auth_tool_b, tool_c),
        system_prompt="test",
        max_iterations=3,
    )
    _install_auth_required_executor(agent, {"tool_a": auth_tool_a, "tool_b": auth_tool_b})

    # Initial step pauses on tc_a (head of list) — A8b lock
    await _collect(agent, "trigger")
    assert agent._deferred_tool_calls is not None
    assert [tc.id for tc in agent._deferred_tool_calls] == ["tc_a", "tc_b", "tc_c"]
    assert len(auth_tool_b.calls) == 0  # tc_b NOT invoked on first pass

    # First resume — tc_a succeeds, tc_b re-pauses, tc_c not invoked
    resume1_msgs: list[Message] = []
    async for m in agent.resume_after_auth():
        resume1_msgs.append(m)
    assert len(resume1_msgs) == 2
    assert resume1_msgs[0].tool_result is not None
    assert resume1_msgs[0].tool_result.tool_call_id == "tc_a"
    assert resume1_msgs[0].tool_result.metadata is None  # tc_a now succeeds
    assert resume1_msgs[1].tool_result is not None
    assert resume1_msgs[1].tool_result.tool_call_id == "tc_b"
    assert resume1_msgs[1].tool_result.metadata is not None
    assert resume1_msgs[1].tool_result.metadata.get("is_auth_required") is True

    # Re-deferred = [tc_b, tc_c]; tc_c still not invoked
    assert agent._deferred_tool_calls is not None
    assert [tc.id for tc in agent._deferred_tool_calls] == ["tc_b", "tc_c"]
    assert len(tool_c.calls) == 0

    # Second resume — tc_b succeeds, tc_c succeeds, LLM iteration 1 yields text
    resume2_msgs: list[Message] = []
    async for m in agent.resume_after_auth():
        resume2_msgs.append(m)
    assert len(resume2_msgs) == 3
    assert resume2_msgs[0].tool_result is not None
    assert resume2_msgs[0].tool_result.tool_call_id == "tc_b"
    assert resume2_msgs[0].tool_result.metadata is None
    assert resume2_msgs[1].tool_result is not None
    assert resume2_msgs[1].tool_result.tool_call_id == "tc_c"
    assert resume2_msgs[2].role == Role.ASSISTANT
    assert resume2_msgs[2].content == "all done"
    assert agent._deferred_tool_calls is None
    # tc_c was invoked exactly once on the second resume
    assert len(tool_c.calls) == 1


async def test_continue_signal_metadata_is_none() -> None:
    """A9: the continue virtual signal's synthesized ToolResult has metadata=None.

    Inspects the ToolResult that ``_dispatch_tool_calls`` synthesizes
    for the continue signal — verifies the auth_required check
    short-circuits cleanly on it. Also confirms the existing
    ``TestContinueSignal.test_continue_not_yielded_to_caller``
    semantic is preserved (continue is appended but NOT yielded).
    """
    tool_a = StubTool("tool_a")
    llm = FakeLLM(
        [
            Message.assistant(
                "thinking...",
                tool_calls=[
                    ToolCall(id="cont1", name="continue", arguments={"reason": "more"}),
                ],
            ),
            Message.assistant("done"),
        ]
    )
    agent = Agent(llm=llm, tools=_make_registry(tool_a), system_prompt="test", max_iterations=3)

    msgs = await _collect(agent, "go")
    # 2 yielded — continue's tool_msg is NOT yielded (preserved semantic)
    assert len(msgs) == 2

    # Find the continue's appended tool_msg in agent.messages
    tool_msgs = [m for m in agent.messages if m.role == Role.TOOL]
    assert len(tool_msgs) == 1
    assert tool_msgs[0].tool_result is not None
    # Critical: continue's metadata is None — auth_required check
    # short-circuits cleanly without reading metadata.
    assert tool_msgs[0].tool_result.metadata is None
    assert agent._deferred_tool_calls is None  # never paused


async def test_reset_clears_pause_state() -> None:
    """A10: agent.reset() zeroes _deferred_tool_calls and _remaining_iterations."""
    auth_tool = AuthRequiredStubTool(name="auth_tool")
    llm = FakeLLM(
        [
            Message.assistant(
                "",
                tool_calls=[ToolCall(id="tc_a", name="auth_tool", arguments={})],
            ),
        ]
    )
    agent = Agent(
        llm=llm,
        tools=_make_registry(auth_tool),
        system_prompt="test",
        max_iterations=20,
    )
    _install_auth_required_executor(agent, {"auth_tool": auth_tool})

    await _collect(agent, "trigger")
    assert agent._deferred_tool_calls is not None
    assert agent._remaining_iterations == 19

    agent.reset()
    assert agent._deferred_tool_calls is None
    assert agent._remaining_iterations == 0
    # Messages also reset
    assert len(agent.messages) == 1
    assert agent.messages[0].role == Role.SYSTEM


async def test_iteration_counter_resumes_correctly_with_max_iterations_3() -> None:
    """A6: Iteration counter resumes correctly across pause boundary.

    Scenario per leg artifact A6:
      - Iter 0 LLM call returns ``[tc_a, tc_b]``; tc_a succeeds, tc_b
        auth_required → defer ``[tc_b]``; ``_remaining_iterations=2``.
      - Resume re-dispatches ``[tc_b]`` (now succeeds) then re-enters
        ``_run_iterations``; iter 1 LLM returns ``[tc_c]``; tc_c
        succeeds; ``_remaining_iterations=1``.
      - Iter 2 LLM returns text-only; loop ends; ``_remaining_iterations=0``.
      - Total LLM calls = 3 == ``max_iterations``.
    """
    tool_a = StubTool("tool_a")
    auth_tool_b = AuthRequiredStubTool(name="tool_b", auth_required_calls=1, success_content="b ok")
    tool_c = StubTool("tool_c")
    llm = FakeLLM(
        [
            # Iter 0
            Message.assistant(
                "",
                tool_calls=[
                    ToolCall(id="tc_a", name="tool_a", arguments={}),
                    ToolCall(id="tc_b", name="tool_b", arguments={}),
                ],
            ),
            # Iter 1 (after resume re-enters _run_iterations)
            Message.assistant(
                "",
                tool_calls=[ToolCall(id="tc_c", name="tool_c", arguments={})],
            ),
            # Iter 2 — text only
            Message.assistant("all done"),
        ]
    )
    agent = Agent(
        llm=llm,
        tools=_make_registry(tool_a, auth_tool_b, tool_c),
        system_prompt="test",
        max_iterations=3,
    )
    _install_auth_required_executor(agent, {"tool_b": auth_tool_b})

    await _collect(agent, "trigger")
    # After iter-0 pause: 2 iterations remain (cycle-1 D8 lock)
    assert agent._remaining_iterations == 2
    assert len(llm.calls) == 1

    [m async for m in agent.resume_after_auth()]
    # After resume completes: 0 iterations remain (consumed iter 1 + iter 2)
    assert agent._remaining_iterations == 0
    assert len(llm.calls) == 3  # = max_iterations
    assert agent._deferred_tool_calls is None


async def test_execute_tool_translates_mcp_auth_required_to_metadata() -> None:
    """F5 L4 A10: Agent._execute_tool catches MCPAuthRequired and populates
    ToolResult.metadata.is_auth_required=True so the L3 step loop's
    auth_required check fires.

    L3 simulates this via a monkeypatched ``_execute_tool``; L4 wires
    the real production catch. This test exercises the real catch
    directly (no monkeypatch).
    """

    class AuthRequiredTool(Tool):
        def __init__(self) -> None:
            self.name = "auth_tool"
            self.description = "raises auth required"
            self.parameters: dict[str, Any] = {
                "type": "object",
                "properties": {},
                "required": [],
            }

        async def execute(self, **kwargs: Any) -> str:
            raise MCPAuthRequired(
                source_id="s1",
                resource_metadata_url="https://x/.well-known/oauth-protected-resource",
            )

    agent = Agent(
        llm=FakeLLM([]),
        tools=_make_registry(AuthRequiredTool()),
        system_prompt="test",
    )
    tc = ToolCall(id="tc1", name="auth_tool", arguments={})
    result = await agent._execute_tool(tc)

    assert result.tool_call_id == "tc1"
    assert result.content == "<auth required>"
    assert result.is_error is False  # control-flow signal, NOT an error
    assert result.metadata == {
        "is_auth_required": True,
        "source_id": "s1",
        "source_name": None,
        "resource_metadata_url": "https://x/.well-known/oauth-protected-resource",
        "tool_call_id": "tc1",
        "consent_url": None,
    }


class _SwitchableAuthTool(Tool):
    """Raises ``MCPAuthRequired`` until ``signed_in`` is flipped, then succeeds."""

    def __init__(self) -> None:
        self.name = "mcp__x__echo"
        self.description = "auth-gated"
        self.parameters: dict[str, Any] = {"type": "object", "properties": {}}
        self.signed_in = False

    async def execute(self, **kwargs: Any) -> str:
        if not self.signed_in:
            raise MCPAuthRequired(source_id="s1", resource_metadata_url=None)
        return "signed-in ok"


def _is_auth_msg(m: Message) -> bool:
    return bool(m.tool_result and (m.tool_result.metadata or {}).get("is_auth_required"))


class TestPauseStateSetBeforeYield:
    """The deferred state must exist even if the consumer stops at the pause message."""

    async def test_consumer_that_breaks_at_pause_message_sees_deferred_calls(self) -> None:
        tc = ToolCall(id="tc1", name="mcp__x__echo", arguments={})
        llm = FakeLLM([Message.assistant("", tool_calls=[tc])])
        agent = Agent(llm=llm, tools=_make_registry(_SwitchableAuthTool()), system_prompt="t")

        gen = agent.step("hi")
        async for m in gen:
            if _is_auth_msg(m):
                break  # the WebSocket layer does exactly this

        assert agent._deferred_tool_calls == [tc]

    async def test_draining_consumer_sees_same_deferred_calls(self) -> None:
        tc = ToolCall(id="tc1", name="mcp__x__echo", arguments={})
        llm = FakeLLM([Message.assistant("", tool_calls=[tc])])
        agent = Agent(llm=llm, tools=_make_registry(_SwitchableAuthTool()), system_prompt="t")

        await _collect(agent, "hi")

        assert agent._deferred_tool_calls == [tc]

    async def test_repause_during_resume_with_breaking_consumer_sets_state_again(self) -> None:
        tc = ToolCall(id="tc1", name="mcp__x__echo", arguments={})
        llm = FakeLLM([Message.assistant("", tool_calls=[tc])])
        agent = Agent(llm=llm, tools=_make_registry(_SwitchableAuthTool()), system_prompt="t")
        async for m in agent.step("hi"):
            if _is_auth_msg(m):
                break

        gen = agent.resume_after_auth()
        async for m in gen:
            if _is_auth_msg(m):
                break  # still signed out: re-pauses

        assert agent._deferred_tool_calls == [tc]


def _tool_result_ids(messages: list[Message]) -> list[str]:
    return [m.tool_result.tool_call_id for m in messages if m.tool_result is not None]


class TestResumeDropsAuthPlaceholder:
    """Providers reject two tool results for one tool_use id."""

    async def test_resume_leaves_one_result_per_call_and_no_placeholder(self) -> None:
        tool = _SwitchableAuthTool()
        tc = ToolCall(id="tc1", name="mcp__x__echo", arguments={})
        llm = FakeLLM([Message.assistant("", tool_calls=[tc]), Message.assistant("done")])
        agent = Agent(llm=llm, tools=_make_registry(tool), system_prompt="t")
        await _collect(agent, "hi")
        assert _tool_result_ids(agent.messages) == ["tc1"]  # the placeholder

        tool.signed_in = True
        await _collect_resume(agent)

        assert _tool_result_ids(agent.messages) == ["tc1"]
        assert not any(_is_auth_msg(m) for m in agent.messages)
        assert [m.tool_result.content for m in agent.messages if m.tool_result] == ["signed-in ok"]
        # What the provider actually received must not carry duplicates.
        sent = _tool_result_ids(llm.calls[-1]["messages"])
        assert sent == ["tc1"]

    async def test_repause_leaves_exactly_one_placeholder(self) -> None:
        tc = ToolCall(id="tc1", name="mcp__x__echo", arguments={})
        llm = FakeLLM([Message.assistant("", tool_calls=[tc])])
        agent = Agent(llm=llm, tools=_make_registry(_SwitchableAuthTool()), system_prompt="t")
        await _collect(agent, "hi")

        await _collect_resume(agent)  # still signed out

        assert _tool_result_ids(agent.messages) == ["tc1"]
        assert sum(_is_auth_msg(m) for m in agent.messages) == 1
        assert agent._deferred_tool_calls == [tc]


async def _collect_resume(agent: Agent) -> list[Message]:
    return [m async for m in agent.resume_after_auth()]
