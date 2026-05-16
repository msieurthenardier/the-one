"""F10 L1: Agent visibility filter tests.

Tests the per-iteration _compute_visible_schemas() contract, stub tool
mutation, reset semantics, persistence across turns, and the F5
pause/resume invariant under loaded-set mutation.

Fixture pattern: tests construct Agent directly (without factory) to avoid
DB dependencies — the new loaded_schemas / loaded_tool_names kwargs default
to fresh containers if omitted (backward-compat path). Factory integration
is covered by tests/test_agent_factory.py.
"""

from __future__ import annotations

from typing import Any

from conftest import FakeLLM, StubTool

from the_one.agent.core import (
    CONTINUE_SCHEMA,
    SEARCH_TOOLS_SCHEMA,
    Agent,
)
from the_one.llm.base import LLMProvider, Message, ToolCall, ToolResult
from the_one.mcp.errors import MCPAuthRequired
from the_one.tools._search_stubs import (
    _CANNED_TOOL_SCHEMA_A,
    _CANNED_TOOL_SCHEMA_B,
    SearchToolsStub,
)
from the_one.tools.base import Tool, ToolRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_registry(*tools: Tool) -> ToolRegistry:
    reg = ToolRegistry()
    for t in tools:
        reg.register(t)
    return reg


def _make_on_match(
    loaded_schemas: list[dict],
    loaded_tool_names: set[str],
) -> Any:
    """Factory for the _on_search_match closure used in factory.py."""

    def _on_match(schemas: list[dict]) -> None:
        for s in schemas:
            if s["name"] not in loaded_tool_names:
                loaded_schemas.append(s)
                loaded_tool_names.add(s["name"])

    return _on_match


def _make_agent_with_stubs(
    llm: LLMProvider,
    extra_tools: list[Tool] | None = None,
    max_iterations: int = 20,
) -> tuple[Agent, list[dict], set[str]]:
    """Build an Agent with the stub search tool wired to shared containers.

    Returns (agent, loaded_schemas, loaded_tool_names) so tests can
    inspect and mutate the shared containers directly.
    """
    loaded_schemas: list[dict] = []
    loaded_tool_names: set[str] = set()
    on_match = _make_on_match(loaded_schemas, loaded_tool_names)

    tools_stub = SearchToolsStub(on_match=on_match)
    registry = _make_registry(tools_stub, *(extra_tools or []))

    agent = Agent(
        llm=llm,
        tools=registry,
        system_prompt="test",
        max_iterations=max_iterations,
        loaded_schemas=loaded_schemas,
        loaded_tool_names=loaded_tool_names,
    )
    return agent, loaded_schemas, loaded_tool_names


async def _collect(agent: Agent, user_input: str) -> list[Message]:
    msgs: list[Message] = []
    async for m in agent.step(user_input):
        msgs.append(m)
    return msgs


# ---------------------------------------------------------------------------
# Test 1: default visible schemas at session start
# ---------------------------------------------------------------------------


async def test_default_visible_schemas_at_session_start() -> None:
    """A fresh agent (no stubs called) exposes exactly [search_tools, continue]."""
    agent, _, _ = _make_agent_with_stubs(FakeLLM([]))
    schemas = agent._compute_visible_schemas()

    assert schemas == [SEARCH_TOOLS_SCHEMA, CONTINUE_SCHEMA]
    assert len(schemas) == 2


# ---------------------------------------------------------------------------
# Test 2: stub mutates loaded schemas
# ---------------------------------------------------------------------------


async def test_search_stub_mutates_loaded_schemas() -> None:
    """Calling SearchToolsStub.execute() extends the shared loaded_schemas list;
    _compute_visible_schemas() on the next call reflects the addition.
    """
    agent, loaded_schemas, _ = _make_agent_with_stubs(FakeLLM([]))

    # Call the stub directly (simulating a tool dispatch)
    tools_stub = agent.tools.get("search_tools")
    assert isinstance(tools_stub, SearchToolsStub)
    await tools_stub.execute(query="")

    # loaded_schemas now has 2 canned entries
    assert len(loaded_schemas) == 2
    assert loaded_schemas[0]["name"] == _CANNED_TOOL_SCHEMA_A["name"]
    assert loaded_schemas[1]["name"] == _CANNED_TOOL_SCHEMA_B["name"]

    # _compute_visible_schemas() reflects the addition
    schemas = agent._compute_visible_schemas()
    assert len(schemas) == 4  # 2 baseline + 2 canned
    canned_names = {s["name"] for s in schemas}
    assert _CANNED_TOOL_SCHEMA_A["name"] in canned_names
    assert _CANNED_TOOL_SCHEMA_B["name"] in canned_names


# ---------------------------------------------------------------------------
# Test 3: per-iteration recompute
# ---------------------------------------------------------------------------


async def test_per_iteration_recompute() -> None:
    """F10 §9: schemas added in iteration N appear in iteration N+1's tools=.

    Drive _run_iterations with a mock LLM that calls search_tools in
    iteration 0, then calls _stub_canned_tool_a in iteration 1.
    The iteration 1 stream call should receive schemas containing
    _stub_canned_tool_a's schema (which was loaded by the search call).
    """
    # Iteration 0: LLM calls search_tools
    # Iteration 1: LLM calls _stub_canned_tool_a
    # Iteration 2: LLM returns text-only (done)
    canned_tool = StubTool(_CANNED_TOOL_SCHEMA_A["name"])
    llm = FakeLLM(
        [
            Message.assistant(
                "",
                tool_calls=[ToolCall(id="t0", name="search_tools", arguments={"query": ""})],
            ),
            Message.assistant(
                "",
                tool_calls=[ToolCall(id="t1", name=_CANNED_TOOL_SCHEMA_A["name"], arguments={})],
            ),
            Message.assistant("done"),
        ]
    )
    agent, loaded_schemas, _ = _make_agent_with_stubs(llm, extra_tools=[canned_tool])

    await _collect(agent, "go")

    # canned_tool was actually called (meaning it was dispatched in iter 1)
    assert len(canned_tool.calls) == 1

    # The LLM received 3 stream calls total
    assert len(llm.calls) == 3

    # iter-1's tools= (index 1) must contain _CANNED_TOOL_SCHEMA_A
    iter1_tools = llm.calls[1]["tools"]
    assert iter1_tools is not None
    iter1_names = {t["name"] for t in iter1_tools}
    assert _CANNED_TOOL_SCHEMA_A["name"] in iter1_names

    # iter-0's tools= (index 0) must NOT contain _CANNED_TOOL_SCHEMA_A
    # (it wasn't loaded yet at the start of iteration 0)
    iter0_tools = llm.calls[0]["tools"]
    assert iter0_tools is not None
    iter0_names = {t["name"] for t in iter0_tools}
    assert _CANNED_TOOL_SCHEMA_A["name"] not in iter0_names


# ---------------------------------------------------------------------------
# Test 4: reset clears loaded state
# ---------------------------------------------------------------------------


async def test_reset_clears_loaded_state() -> None:
    """agent.reset() clears _loaded_schemas and _loaded_tool_names;
    _compute_visible_schemas() returns the baseline 2 schemas only.
    """
    agent, loaded_schemas, loaded_tool_names = _make_agent_with_stubs(FakeLLM([]))

    # Manually populate via the stub
    tools_stub = agent.tools.get("search_tools")
    assert isinstance(tools_stub, SearchToolsStub)
    await tools_stub.execute()

    assert len(loaded_schemas) == 2
    assert len(loaded_tool_names) == 2

    agent.reset()

    # Containers cleared in-place
    assert len(loaded_schemas) == 0
    assert len(loaded_tool_names) == 0
    assert agent._loaded_schemas is loaded_schemas  # same container (not re-assigned)
    assert agent._loaded_tool_names is loaded_tool_names

    # Visible schemas back to baseline
    schemas = agent._compute_visible_schemas()
    assert schemas == [SEARCH_TOOLS_SCHEMA, CONTINUE_SCHEMA]


# ---------------------------------------------------------------------------
# Test 5: reset clears — stub mutation lands in agent AFTER reset
# ---------------------------------------------------------------------------


async def test_reset_clears_and_stub_still_works_after_reset() -> None:
    """After reset(), calling stub.execute() again mutates the SAME containers
    (not an orphaned pre-reset container). Validates .clear() vs re-assignment.
    """
    agent, loaded_schemas, loaded_tool_names = _make_agent_with_stubs(FakeLLM([]))

    tools_stub = agent.tools.get("search_tools")
    assert isinstance(tools_stub, SearchToolsStub)
    await tools_stub.execute()
    assert len(loaded_schemas) == 2

    agent.reset()
    assert len(loaded_schemas) == 0

    # Execute stub again post-reset — mutation must still land in the shared container
    await tools_stub.execute()
    assert len(loaded_schemas) == 2
    assert len(agent._loaded_schemas) == 2  # agent sees the same container


# ---------------------------------------------------------------------------
# Test 6: persistence across user turns
# ---------------------------------------------------------------------------


async def test_persistence_across_user_turns() -> None:
    """F10 §1: loaded state is NOT cleared between user turns (step() calls).

    Turn 1: search_tools called in iteration 0 → canned schemas loaded.
    Turn 2: first iteration's tools= should contain the canned schema.
    """
    canned_tool = StubTool(_CANNED_TOOL_SCHEMA_A["name"])
    llm = FakeLLM(
        [
            # Turn 1, iteration 0: search_tools
            Message.assistant(
                "",
                tool_calls=[ToolCall(id="s0", name="search_tools", arguments={})],
            ),
            # Turn 1, iteration 1: done
            Message.assistant("turn 1 done"),
            # Turn 2, iteration 0: use the canned tool loaded in turn 1
            Message.assistant(
                "",
                tool_calls=[ToolCall(id="t1", name=_CANNED_TOOL_SCHEMA_A["name"], arguments={})],
            ),
            # Turn 2, iteration 1: done
            Message.assistant("turn 2 done"),
        ]
    )
    agent, _, _ = _make_agent_with_stubs(llm, extra_tools=[canned_tool])

    await _collect(agent, "turn 1")
    await _collect(agent, "turn 2")

    # canned_tool was dispatched in turn 2
    assert len(canned_tool.calls) == 1

    # turn 2's first LLM call (index 2 overall) should include canned schema
    # (calls[0] and [1] are turn-1; calls[2] and [3] are turn-2)
    assert len(llm.calls) == 4
    turn2_iter0_tools = llm.calls[2]["tools"]
    assert turn2_iter0_tools is not None
    turn2_names = {t["name"] for t in turn2_iter0_tools}
    assert _CANNED_TOOL_SCHEMA_A["name"] in turn2_names


# ---------------------------------------------------------------------------
# Test 7: F5 pause/resume invariant — the critical lock-in
# ---------------------------------------------------------------------------


class _MCPToolBehavior:
    """Tracks call count; returns MCPAuthRequired on call 1, success on call 2."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.call_count = 0

    async def execute_patched(self, tool_call: ToolCall) -> ToolResult:
        self.call_count += 1
        if self.call_count == 1:
            raise MCPAuthRequired(
                source_id="src1",
                resource_metadata_url="https://src1/.well-known/oauth-protected-resource",
            )
        return ToolResult(tool_call_id=tool_call.id, content="mcp_result_ok")


class _MCPTool(Tool):
    """Minimal MCP-style tool that raises MCPAuthRequired on first call."""

    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name
        self.description = "Mock MCP tool"
        self.parameters: dict[str, Any] = {
            "type": "object",
            "properties": {},
            "required": [],
        }
        self._call_count = 0

    async def execute(self, **kwargs: Any) -> str:
        self._call_count += 1
        if self._call_count == 1:
            raise MCPAuthRequired(
                source_id="src1",
                resource_metadata_url="https://src1/.well-known/oauth-protected-resource",
            )
        return "mcp_result_ok"


async def test_deferred_resumed_mcp_tool_dispatch() -> None:
    """F10 L1 lock-in: F5 pause/resume invariant under loaded-set mutation.

    A tool whose execute() raises MCPAuthRequired gets deferred via
    _dispatch_tool_calls. Between defer and resume, _loaded_schemas is mutated
    (simulating an unrelated search call). resume_after_auth() dispatches via
    self.tools.get(name) — registry-based, NOT loaded-set-based — so it
    succeeds regardless.

    Asserts:
    - supports_tools() is awaited exactly twice across the full step+resume
      path (once per _run_iterations entry, per F10 §9).
    - resumed dispatch returns the normal ToolResult (second MCPAuthRequired
      call returns success).
    """
    mcp_tool = _MCPTool(name="mock_mcp_tool")

    # supports_tools call counter
    supports_tools_count = 0

    class _CountingFakeLLM(FakeLLM):
        async def supports_tools(self) -> bool:
            nonlocal supports_tools_count
            supports_tools_count += 1
            return True

    llm = _CountingFakeLLM(
        [
            # step(): LLM calls the mock MCP tool (triggers MCPAuthRequired → defer)
            Message.assistant(
                "",
                tool_calls=[ToolCall(id="tc_mcp", name="mock_mcp_tool", arguments={})],
            ),
            # resume_after_auth() re-enters _run_iterations after re-dispatch:
            # the resumed dispatch succeeds; _run_iterations gets a text-only response
            Message.assistant("resumed ok"),
        ]
    )
    agent, loaded_schemas, loaded_tool_names = _make_agent_with_stubs(llm, extra_tools=[mcp_tool])

    # step(): mcp_tool.execute() raises MCPAuthRequired → gets deferred
    step_msgs: list[Message] = []
    async for m in agent.step("trigger mcp"):
        step_msgs.append(m)

    # step paused: assistant msg + auth_required tool_msg
    assert len(step_msgs) == 2
    assert step_msgs[1].tool_result is not None
    assert step_msgs[1].tool_result.metadata is not None
    assert step_msgs[1].tool_result.metadata.get("is_auth_required") is True

    # Deferred state is set
    assert agent._deferred_tool_calls is not None
    assert agent._deferred_tool_calls[0].name == "mock_mcp_tool"

    # CRITICAL: mutate _loaded_schemas between defer and resume
    # (simulate an unrelated search call adding a different schema)
    extra_schema = {
        "name": "_unrelated_schema_added_between_defer_and_resume",
        "description": "simulates a search result added mid-pause",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }
    loaded_schemas.append(extra_schema)
    loaded_tool_names.add(extra_schema["name"])
    assert len(loaded_schemas) == 1  # only the injected one (no search calls yet)

    # resume_after_auth(): dispatches via self.tools.get(name) — registry-based
    # The MCP tool's second call returns success; _run_iterations gets a text response
    resume_msgs: list[Message] = []
    async for m in agent.resume_after_auth():
        resume_msgs.append(m)

    # resumed dispatch yields: mcp_tool success tool_msg + final assistant text
    assert len(resume_msgs) == 2
    assert resume_msgs[0].tool_result is not None
    assert resume_msgs[0].tool_result.tool_call_id == "tc_mcp"
    assert resume_msgs[0].tool_result.metadata is None  # success path
    assert resume_msgs[0].content == "mcp_result_ok"
    assert resume_msgs[1].role is not None
    assert resume_msgs[1].content == "resumed ok"

    # Pause state cleared
    assert agent._deferred_tool_calls is None

    # supports_tools() was awaited exactly 2 times:
    # once in step()'s _run_iterations entry, once in resume()'s _run_iterations entry
    assert supports_tools_count == 2


# ---------------------------------------------------------------------------
# Test 8: supports_tools gate stays outside the loop
# ---------------------------------------------------------------------------


async def test_supports_tools_gate_outside_loop() -> None:
    """F10 §9: supports_tools() is awaited exactly ONCE per _run_iterations entry
    (NOT per iteration). A two-iteration step should yield supports_tools call count = 1.
    """
    supports_tools_count = 0

    class _CountingFakeLLM(FakeLLM):
        async def supports_tools(self) -> bool:
            nonlocal supports_tools_count
            supports_tools_count += 1
            return True

    llm = _CountingFakeLLM(
        [
            # Iteration 0: continue signal
            Message.assistant(
                "thinking",
                tool_calls=[ToolCall(id="c0", name="continue", arguments={"reason": "more"})],
            ),
            # Iteration 1: text-only done
            Message.assistant("done"),
        ]
    )
    agent, _, _ = _make_agent_with_stubs(llm)
    await _collect(agent, "go")

    # 2 iterations in 1 step — supports_tools awaited once
    assert len(llm.calls) == 2
    assert supports_tools_count == 1


async def test_supports_tools_false_runs_plain_chat() -> None:
    """When supports_tools() returns False, tools= is None in the LLM call."""

    class _NoToolsFakeLLM(FakeLLM):
        async def supports_tools(self) -> bool:
            return False

    llm = _NoToolsFakeLLM([Message.assistant("plain response")])
    agent, _, _ = _make_agent_with_stubs(llm)
    await _collect(agent, "hello")

    assert len(llm.calls) == 1
    # tools= must be None (not the baseline 3 schemas)
    assert llm.calls[0]["tools"] is None


# ---------------------------------------------------------------------------
# Test 9: stub idempotency
# ---------------------------------------------------------------------------


async def test_search_stub_idempotent() -> None:
    """Calling SearchToolsStub.execute() twice with the same query should
    result in 2 entries in loaded_schemas (not 4) — dedup-via-name-set.
    """
    agent, loaded_schemas, loaded_tool_names = _make_agent_with_stubs(FakeLLM([]))

    tools_stub = agent.tools.get("search_tools")
    assert isinstance(tools_stub, SearchToolsStub)

    await tools_stub.execute(query="test")
    await tools_stub.execute(query="test")

    # 2 canned entries, NOT 4 (idempotent dedup)
    assert len(loaded_schemas) == 2
    assert len(loaded_tool_names) == 2
    # Names are the canned ones
    assert {s["name"] for s in loaded_schemas} == {
        _CANNED_TOOL_SCHEMA_A["name"],
        _CANNED_TOOL_SCHEMA_B["name"],
    }
