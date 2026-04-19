# Leg: test-factory-and-agent-loop

**Status**: completed
**Flight**: [Test Infrastructure & CI Hardening](../flight.md)

## Objective

Add unit tests for AgentFactory and the Agent loop (`Agent.step()`), using FakeLLM for deterministic testing of all branching paths.

## Context

- Legs 1-2 complete — FakeLLM, StubTool, ToolRegistry tests, LLM registry tests all passing
- Agent loop is the most critical code — currently only tested by live AIAT
- FakeLLM enables deterministic testing of iteration limits, tool execution flow, direct action bypass, continue signal, and error handling
- AgentFactory depends on Settings, LLM registry, and BuiltinToolProvider — tests need to mock/patch these

## Inputs

- `the_one/agent/factory.py` — `AgentFactory` (create, list_agents, _load_config, _default_config)
- `the_one/agent/core.py` — `Agent` (step, _execute_tool, _extract_tool_calls, _match_direct_action, reset)
- `the_one/agent/config.py` — `AgentConfig`
- `the_one/agent/store.py` — `FilesystemConfigStore`
- `the_one/config.py` — `Settings`, `settings` singleton
- `tests/conftest.py` — FakeLLM, StubTool, make_registry fixture

## Outputs

- `tests/test_factory.py` — AgentFactory unit tests
- `tests/test_agent.py` — Agent loop unit tests

## Acceptance Criteria

- [x] `test_factory.py`: default agent creation (uses settings) produces a valid Agent
- [x] `test_factory.py`: named agent from store (save config, create from it)
- [x] `test_factory.py`: unknown agent raises KeyError
- [x] `test_factory.py`: tool filtering (disabled_tools, enabled_tools) works correctly
- [x] `test_factory.py`: list_agents() includes "default"
- [x] `test_factory.py`: uses tmp_path for store, patches LLM provider
- [x] `test_agent.py`: normal flow — LLM responds with text only, no tool calls → yields one message, loop ends
- [x] `test_agent.py`: tool execution — LLM responds with tool call → tool executes → result yielded → LLM responds with text
- [x] `test_agent.py`: direct action bypass — "restart yourself" → tool called without LLM
- [x] `test_agent.py`: continue signal — LLM calls "continue" → loop continues, no tool result yielded to caller
- [x] `test_agent.py`: max iterations — LLM always calls tools → loop stops at max_iterations
- [x] `test_agent.py`: tool execution error — tool raises exception → error ToolResult yielded
- [x] `test_agent.py`: text-embedded tool calls — LLM returns text with JSON tool call → extracted and executed
- [x] `test_agent.py`: reset() — messages reset to system prompt only
- [x] All new tests pass: `pytest tests/test_factory.py tests/test_agent.py -q`
- [x] `ruff check tests/` clean
- [x] All existing tests still pass (no regressions)

## Verification Steps

- `python3 -m pytest tests/test_factory.py tests/test_agent.py --tb=short -q`
- `python3 -m pytest tests/ --tb=short -q` — full suite
- `ruff check tests/`

## Implementation Guidance

1. **Create `tests/test_factory.py`**
   - AgentFactory needs: a store, tool providers, and the LLM registry
   - Use `tmp_path` for FilesystemConfigStore
   - Patch `the_one.llm.get_provider` to return a FakeLLM instead of hitting real LLM registry
   - Patch `the_one.agent.factory.settings` to control `llm_provider`, `llm_model`, `agents_dir`, etc.
   - Create a simple StubToolProvider that implements ToolProvider protocol and returns a few StubTools
   - Test default agent: factory.create() should return an Agent with tools and system prompt
   - Test named agent: save an AgentConfig to the store, then factory.create("name") should load it
   - Test unknown: factory.create("nonexistent") should raise KeyError
   - Test tool filtering: save config with disabled_tools=["tool_a"], verify tool_a is not in the created agent's registry
   - Test list_agents: should always include "default" plus any saved configs

2. **Create `tests/test_agent.py`**
   - All tests are async (use pytest-asyncio with auto mode)
   - Create Agent directly: `Agent(llm=FakeLLM(responses), tools=registry, max_iterations=N)`
   - Use `make_registry` fixture for a pre-loaded tool registry
   - Collect yielded messages from `async for msg in agent.step("input"):`

   Test cases:
   - **Normal flow**: FakeLLM returns `Message.assistant("hello")` (no tool_calls). Expect 1 yielded message with content "hello".
   - **Tool execution**: FakeLLM returns `Message.assistant("", tool_calls=[ToolCall(id="1", name="tool_a", arguments={})])`, then `Message.assistant("done")`. Expect: assistant msg, tool result msg, final assistant msg.
   - **Direct action**: `agent.step("restart yourself")`. The agent should call the "restart" tool directly without going to LLM. Need to register a StubTool named "restart" in the registry.
   - **Continue signal**: FakeLLM returns msg with tool_calls=[ToolCall(id="1", name="continue", arguments={"reason": "thinking"})], then `Message.assistant("done")`. The continue tool result should NOT be yielded to caller, but the loop should continue.
   - **Max iterations**: FakeLLM always returns tool calls. Set max_iterations=2. Should stop after 2 iterations.
   - **Tool error**: Register a tool that raises an exception. FakeLLM calls it. Expect ToolResult with is_error=True.
   - **Text-embedded tool calls**: FakeLLM returns `Message.assistant('I will use the tool {"name": "tool_a", "arguments": "hello"}')`. The JSON should be extracted and tool_a executed. Note: only string arguments work due to the regex limitation documented in Leg 1.
   - **Reset**: After a step, call agent.reset(). Verify agent.messages has only the system prompt.

## Edge Cases

- **FakeLLM exhaustion**: If tests don't provide enough responses, IndexError — tests must provide exactly the right number
- **Continue signal not yielded**: The continue tool result is fed back to the LLM (appended to messages) but NOT yielded to the caller. This is a critical behavioral distinction to test.
- **Direct action with missing tool**: If "restart" tool is not in registry, the agent catches the KeyError and returns an error message
- **Agent factory settings patching**: Must patch the settings singleton carefully to avoid affecting other tests

## Files Affected

- `tests/test_factory.py` — Create
- `tests/test_agent.py` — Create

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] Commit all changes together (code + artifacts)
