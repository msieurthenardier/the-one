# Leg: 04-system-prompt-and-integration

**Status**: completed
**Flight**: [Lazy tool discovery](../flight.md)

## Objective

Teach the agent its new lazy-discovery protocol via `BASE_PROMPT` extension in `agent/config.py`, and add an end-to-end integration test that drives the full search → load → call sequence using a scripted `FakeLLM` provider. Browser-level operator-felt verification deferred to L5's HAT (where the full "what tools do you have available?" success scenario lands against a real LLM + real MCP source). L4's deliverable is the protocol documentation in the prompt + automated regression coverage for the iteration loop's discovery semantics — not the operator UX.

## Context

- **F10 §6 (system prompt teaches the protocol)** — `BASE_PROMPT` is the global instruction. Tool descriptions on `search_tools` / `search_mcps` reinforce but the canonical statement lives in the prompt. L4 lands the additions.
- **F10 acceptance criteria carry-forward** — L1+L2+L3 deliver the visibility-filter machinery + real `SearchTools` + `SearchMcps`. L4 makes the protocol VISIBLE to the LLM. Without the prompt instruction, a default-trained model may not understand the strict 2-tool baseline + auto-load semantics.
- **Browser test scope** — F10 flight.md mentions browser tests in L4's sketch, but the operator-felt "what tools do you have?" → list → attach → updated list scenario is L5's HAT territory. L4 ships automated regression coverage (integration test with `FakeLLM`) only; browser tests for full search+load+call sequences would require a deterministic LLM at the browser layer, which existing chat browser tests (e.g., `tests/browser/test_flow_chat.py`) don't have. Defer to L5 HAT.
- **L1+L2+L3 outcome carry-forward**:
  - Agent has 2-tool baseline + visibility filter (L1).
  - `SearchTools` real impl wired in production at `factory.py:176` (L2).
  - `SearchMcps` real impl wired in production at `factory.py:177` (L3, post-implementation).
  - Full unit suite at 1498 pass post-L3 (1474 L2 baseline + 24 L3 tests).
- **`FakeLLM` test pattern** at `tests/conftest.py:48-72` — pre-loads `responses: list[Message]`; each `complete()` call pops the next response. Tests script multi-iteration sequences by pre-loading 3+ responses representing each iteration's LLM output (including `tool_calls` in `Message.assistant` payloads).
- **`Message.assistant` with `tool_calls`** — see `tests/test_agent.py:72-99` for example test scripting tool calls via `Message.assistant(content="", tool_calls=[ToolCall(...)])`.

## Inputs

What exists before this leg runs:

- L1+L2+L3 landed (uncommitted in working tree). Full unit suite at 1498 pass.
- `the_one/agent/config.py:9-32 — BASE_PROMPT` — current prompt (~24 lines of guidance covering tool use, turn semantics, continue signal). L4 extends this.
- `the_one/agent/config.py:88-93 — AgentConfig.get_system_prompt` — already returns `BASE_PROMPT` (optionally with per-agent persona appended via `---` separator). L4 does NOT modify this method; just the underlying constant.
- `the_one/agent/core.py:_compute_visible_schemas` — returns `[SEARCH_TOOLS_SCHEMA, SEARCH_MCPS_SCHEMA, CONTINUE_SCHEMA] + self._loaded_schemas` per iteration. The agent operates as the prompt instructs ONLY if the prompt actually instructs it.
- `the_one/tools/_search_tools.py:SearchTools` (L2) + `the_one/tools/_search_mcps.py:SearchMcps` (L3) — real impls.
- `tests/conftest.py:48-72 — FakeLLM` — pre-loaded responses pattern; agent loop drives via scripted responses.
- `tests/test_agent.py` — existing patterns for multi-iteration scripted tests (e.g., `test_pause_at_tc_b_defers_tc_b_and_tc_c` at line 322 walks a 3-iteration sequence).
- Built-in tool catalog: ~20 tools per the L2 inventory (`shell`, `read_file`, `python_exec`, etc.). L4 integration tests use one or two of these as scripted target tools (e.g., `shell`).

## Outputs

What exists after this leg completes:

- **MODIFIED**: `the_one/agent/config.py` (~25 LOC addition):
  - `BASE_PROMPT` extended with a new "Tool discovery" section explaining the lazy-discovery protocol. Existing sections (Tool use, Turn semantics, persona spillover) preserved unchanged. The new section is positioned BEFORE "Tool use" (so the model reads "you have search tools first, here's how they work" before the general tool-use guidance).
  - Suggested wording (final exact text TBD by implementer; aim for the existing `BASE_PROMPT` voice — direct, concise, second-person):
    ```
    Tool discovery:
    - At the start of each conversation, you have only `search_tools`, `search_mcps`, and `continue` available.
    - To use any other capability, call `search_tools` (for built-in tools like shell, file ops, web fetch) or `search_mcps` (for tools from attached MCP servers) with a query describing what you need. Empty query lists everything available; a specific query narrows results.
    - Matched tools are automatically added to your available toolset for the rest of this conversation. Once you've searched for a tool, you can call it by name on subsequent turns; no need to search again.
    - New conversations start with the baseline 2-tool surface. If the operator attached a new MCP server mid-session, you'll see it in your next session, not the current one.
    ```
- **NEW**: `tests/test_agent_search_integration.py` (~250 LOC, 5-7 tests):
  - `test_search_tools_then_call_loaded_tool` — script: turn 1 LLM calls `search_tools("shell")`; turn 2 LLM calls `shell` (now loaded); turn 3 LLM emits final text. Verify: turn 2's `tools=` arg contained the `shell` schema; turn 2's `shell` dispatch succeeded; final text rendered.
  - `test_search_mcps_then_call_loaded_mcp_tool` — script: turn 1 LLM calls `search_mcps("")`; turn 2 LLM calls a loaded `mcp__test_source__test_tool`; turn 3 LLM emits final text. **NOTE**: `SearchMcps` reads its `source_index` from constructor injection (NOT from `MCPSourceRepository` at runtime — L3's `_search_mcps.py:169-183` confirms). Use L3's `_make_search_mcps` test helper at `tests/test_search_mcps.py:114-137` which accepts `mcp_tools=[...]` + `source_index={...}` as plain dicts; pass the same shared `loaded_schemas` + `loaded_tool_names` containers to `Agent(...)` for cross-iteration visibility. No MCPSourceRepository mock needed.
  - `test_baseline_visible_at_session_start` — script: turn 1 LLM emits final text (no tool calls). Verify: turn 1's `tools=` arg contained EXACTLY `[search_tools, search_mcps, continue]` schemas in order. Locks the baseline post-prompt-update.
  - `test_search_then_call_preserves_loaded_set_across_step` — script across TWO `step()` calls: step 1 LLM searches `search_tools("shell")` + emits text. step 2 LLM calls `shell` (still loaded from step 1) + emits text. Verify: step 2's first iteration's `tools=` arg contains the `shell` schema (loaded set persisted across user turns).
  - `test_search_then_call_with_continue_signal` — script: turn 1 LLM calls `search_tools("file") + continue`; turn 2 LLM calls `read_file` + `continue`; turn 3 LLM emits final text. Verify the continue signal still operates correctly alongside search calls.
  - `test_search_with_no_matches_does_not_load` — script: turn 1 LLM calls `search_tools("xyzzy_no_match")`; turn 2 LLM emits final text. Verify: turn 2's `tools=` arg is still the 2-tool baseline (no spurious loads from a no-match search).
  - `test_base_prompt_includes_discovery_section` — assertion test: `BASE_PROMPT` contains the phrase "search_tools" AND "search_mcps" (verifies the prompt update landed and survives future edits without quiet removal of the discovery section).

## Acceptance Criteria

- [ ] `the_one/agent/config.py:BASE_PROMPT` includes a new "Tool discovery" (or equivalent heading) section explaining the lazy-discovery protocol. The section appears BEFORE the existing "Tool use" section so the model reads "you have search tools first" before general tool-use guidance.
- [ ] The new section mentions `search_tools` AND `search_mcps` by name, references that matched tools are auto-loaded for the rest of the conversation, and notes that new conversations start with the baseline 2-tool surface.
- [ ] `BASE_PROMPT` net additions are ~20-30 LOC. Existing sections (Tool use, Turn semantics, persona spillover) preserved unchanged.
- [ ] `AgentConfig.get_system_prompt` (line 88-93) is NOT modified — the per-agent persona append behavior unchanged.
- [ ] `tests/test_agent_search_integration.py` exists with 5-7 tests as listed in Outputs. All pass.
- [ ] At least one test verifies the baseline `tools=` array contains exactly `[search_tools, search_mcps, continue]` schemas at session start.
- [ ] At least one test verifies the search → call sequence (search in turn 1, call loaded tool in turn 2) works end-to-end through the agent loop with `FakeLLM`.
- [ ] At least one test verifies loaded state persists across user turns within a session (`agent.step()` called twice, second call sees loaded tools from first).
- [ ] At least one test verifies the no-match search does NOT add anything to `_loaded_schemas` (visibility filter unchanged after no-match).
- [ ] All L1 tests in `tests/test_agent_visibility_filter.py` PASS UNMODIFIED.
- [ ] All L2 tests in `tests/test_search_tools.py` PASS UNMODIFIED.
- [ ] All L3 tests in `tests/test_search_mcps.py` PASS UNMODIFIED.
- [ ] Existing `BASE_PROMPT` tests in `tests/test_config.py:166-183` audited and confirmed safe: lines 166 + 170 use `==` equality (`cfg.get_system_prompt() == BASE_PROMPT` and `... == BASE_PROMPT + "\n\n---\n\nCustom prompt."`); lines 181-183 only check `isinstance(BASE_PROMPT, str)` + `len > 0`. Adding content to `BASE_PROMPT` does NOT break any of these. No test modification needed. If any OTHER test surfaces during implementation-time grep that asserts on substring/length/order of `BASE_PROMPT`, update inline and flag in flight log.
- [ ] Full unit suite passes: expected post-L4 count is `1498 + N` where N = L4 test count (5-7).
- [ ] No regression vs F8 browser baseline.

## Verification Steps

- Run unit tests scoped to L4's surface: `docker exec the-one pytest tests/test_agent_search_integration.py -x --timeout 30 -v`. Expect 5-7 passes.
- Run L1+L2+L3 regression: `docker exec the-one pytest tests/test_agent_visibility_filter.py tests/test_search_tools.py tests/test_search_mcps.py -x --timeout 30 -v`. Expect 48 passes (12 + 12 + 24).
- Run touched test files: `docker exec the-one pytest tests/test_agent.py tests/test_agent_search_integration.py tests/test_factory.py -x --timeout 30 -v`. Expect green.
- Run full unit suite at leg-end: `docker exec the-one pytest -q --timeout 120 --ignore=tests/test_mcp_pool.py`. Expect `1498 + N` pass.
- Manual sanity (optional): construct an `AgentConfig` with no per-agent persona; call `config.get_system_prompt()`; verify the resulting string contains both the original prompt content AND the new discovery section.

## Implementation Guidance

### `BASE_PROMPT` extension

Current `BASE_PROMPT` at `agent/config.py:9-32`:

```python
BASE_PROMPT = """\
You are an AI agent with access to a set of tools. Use them to accomplish what the \
operator asks.

Tool use:
- When an action is needed, take the action. Don't describe what you would do.
- Prefer the right tool for the job. Read files with the file-reading tool, not by \
asking the operator to paste them. Run commands with the shell tool, not by \
speculating about output.
- On failure, try a different approach before giving up. State what failed and what \
you're trying next.
- Tool descriptions tell you what each tool does and when it applies. Read them.

Turn semantics:
- Each user message starts a turn. Within a turn you may call tools, see their \
results, and call more tools.
- When you still have work to do but want to think or act in another step, call the \
`continue` tool. It signals "give me another turn"; nothing more.
- When you're done, just respond with text. No `continue` call ends your turn.

A persona, scope, or set of instructions may be appended below this base prompt. \
Treat any addition as a refinement, not a replacement. If no persona is set, default \
to direct, concise responses.
"""
```

L4 modification — insert "Tool discovery" section BETWEEN the opening paragraph and "Tool use":

```python
BASE_PROMPT = """\
You are an AI agent with access to a set of tools. Use them to accomplish what the \
operator asks.

Tool discovery:
- At the start of each conversation, you have only `search_tools`, `search_mcps`, and \
`continue` available.
- To use any other capability, call `search_tools` (for built-in tools like shell, \
file operations, web fetch) or `search_mcps` (for tools from attached MCP servers) \
with a query describing what you need. Empty query lists everything available; a \
specific query narrows results.
- Matched tools are automatically added to your available toolset for the rest of \
this conversation. Once you've searched for a tool, you can call it by name on \
subsequent turns; no need to search again.
- New conversations start fresh with the baseline two-tool surface. If the operator \
attached a new MCP server mid-session, you'll see it in your next session, not the \
current one.

Tool use:
- When an action is needed, take the action. Don't describe what you would do.
...
"""
```

(Rest of existing prompt preserved unchanged.)

### Integration test scaffolding

Pattern follows `tests/test_agent.py:72-99` and `:322` for multi-iteration scripts. Sample:

```python
# tests/test_agent_search_integration.py

import pytest
from conftest import FakeLLM
from the_one.llm.base import Message, Role, ToolCall
from the_one.agent.core import Agent
from the_one.tools.base import ToolRegistry
# ... other imports

@pytest.mark.asyncio
async def test_search_tools_then_call_loaded_tool() -> None:
    """End-to-end: agent searches, gets shell loaded, then calls shell."""
    # Pre-load FakeLLM with 3 responses representing each iteration:
    llm = FakeLLM([
        # Turn 1, Iteration 1: LLM calls search_tools("shell")
        Message.assistant(
            content="",
            tool_calls=[ToolCall(id="tc1", name="search_tools", arguments={"query": "shell"})],
        ),
        # Turn 1, Iteration 2: LLM calls shell (now loaded via search)
        Message.assistant(
            content="",
            tool_calls=[ToolCall(id="tc2", name="shell", arguments={"command": "ls"})],
        ),
        # Turn 1, Iteration 3: LLM emits final text
        Message.assistant(content="Files listed."),
    ])

    # Build registry with real SearchTools + real shell tool (via factory pattern
    # or by direct construction matching factory.py's wiring).
    # ... setup registry, loaded_schemas containers, etc. ...

    # Capture each llm.stream call's `tools=` arg for assertions.
    captured_tools_per_call: list[list[dict] | None] = []
    # ... instrument or wrap FakeLLM ...

    agent = Agent(
        llm=llm,
        tools=registry,
        system_prompt="test",  # bypass BASE_PROMPT for isolation
        loaded_schemas=loaded_schemas,
        loaded_tool_names=loaded_tool_names,
    )
    messages = []
    async for m in agent.step("list the files"):
        messages.append(m)

    # Assertions:
    # 1. Iteration 1's tools= contained only [search_tools, search_mcps, continue].
    # 2. Iteration 2's tools= contained `shell` (auto-loaded by search_tools call).
    # 3. shell dispatch succeeded; result lands in agent.messages as tool message.
    # 4. Final assistant message is "Files listed."
```

### Test for `BASE_PROMPT` content

A simple assertion test that locks in the discovery-section's presence:

```python
def test_base_prompt_includes_discovery_section() -> None:
    """L4: BASE_PROMPT must teach the lazy-discovery protocol.

    If this test fails after a future edit, the discovery section was
    removed — either reinstate it or update F10's design contract.
    """
    from the_one.agent.config import BASE_PROMPT
    assert "search_tools" in BASE_PROMPT
    assert "search_mcps" in BASE_PROMPT
    assert "Tool discovery" in BASE_PROMPT  # or whatever heading you use
    # Order lock: discovery section must appear BEFORE "Tool use:".
    # This locks the intended reading flow — agent learns "you start
    # with search tools" before reading general tool-use guidance.
    assert BASE_PROMPT.index("Tool discovery") < BASE_PROMPT.index("Tool use:")
```

### `FakeLLM` instrumentation for `tools=` capture

**No wrapper needed** — `FakeLLM` at `conftest.py:48-72` already captures every call into `self.calls: list[dict]` with the full kwargs including `tools=`. Tests inspect `llm.calls[N]["tools"]` directly:

```python
llm = FakeLLM([
    Message.assistant(content="", tool_calls=[ToolCall(...)]),
    Message.assistant(content="result"),
])
# Run agent.step(...)
assert llm.calls[0]["tools"] == [...]  # iteration 1's tools= arg
assert llm.calls[1]["tools"] == [...]  # iteration 2's tools= arg
```

This is simpler than a `TracingFakeLLM` subclass and avoids any signature-mismatch concerns. Confirm the `calls` list captures `tools=` by reading `conftest.py:53-72` before relying on it.

### Factory / agent integration for the integration tests

The integration tests need an agent + registry mirroring factory wiring. Three reuse opportunities:

- **L3 helper `_make_search_mcps`** at `tests/test_search_mcps.py:114-137` — accepts `mcp_tools=[...]` + `source_index={...}` + `loaded_schemas` + `loaded_tool_names` as plain values; returns a `SearchMcps` instance bound to those containers. Reusable directly for L4. If you import it from `test_search_mcps.py`, the cross-test-file import works (Python allows it). Alternative: promote `_make_search_mcps` to `tests/conftest.py` as part of L4's work so other tests can use it cleanly — at the implementer's discretion (small refactor, ~25 LOC move).
- **L2 helper for `SearchTools`** — `tests/test_search_tools.py` has analogous helpers for L2's real impl. Inspect for a `_make_search_tools` or similar pattern; reuse if present.
- **`AgentFactory(store=mock_store)` pattern** from L2/L3 tests — builds an agent with real `SearchTools` + `SearchMcps` + the built-in tool catalog via the actual production wiring. Heavier setup but exercises factory regressions too.

**Recommended for L4 integration tests**: use the `_make_search_mcps`/`_make_search_tools` helpers for surgical control over the test's tool set + source index, plus direct `Agent` construction with shared containers. Reserves Option A (full factory) for `test_real_impl_in_factory_wiring`-style assertions if you want to lock down that the prompt + factory together produce the right baseline.

## Edge Cases

- **Existing tests that assert against `BASE_PROMPT` content**: grep `tests/` for `BASE_PROMPT` usage. If any test asserts on the prompt's substring presence/absence, that test may need updating after L4's additions. The grep + audit is part of the implementer's pre-commit work.
- **Agent with a per-agent persona append**: `get_system_prompt` returns `f"{BASE_PROMPT}\n\n---\n\n{self.system_prompt}"` when `self.system_prompt` is non-empty. L4's additions are inside `BASE_PROMPT` so personas continue to append cleanly. Test: construct an agent with `system_prompt="You are a research assistant."` + verify `get_system_prompt()` contains both the discovery section AND the persona separator.
- **Token-cost regression**: `BASE_PROMPT` grows by ~20-30 lines, adding ~50-100 tokens to every system message. The token-cost story for F10 is in L5's measurement; L4 should note this addition in the flight log so L5's "before-vs-after" comparison includes the prompt-growth signal alongside the schema-shrink signal.
- **Test sequencing for `FakeLLM` pre-loaded responses**: the agent loop yields multiple messages per iteration (assistant + tool_result). The test's expected message count should account for the full sequence, not just the LLM's responses count.
- **`Message.assistant` with `tool_calls` payload**: verify the project's `Message` class supports the kwarg shape used in existing tests (`Message.assistant(content="", tool_calls=[ToolCall(...)])`). Read `the_one/llm/base.py` to confirm before scripting.

## Files Affected

- `the_one/agent/config.py` — `BASE_PROMPT` extension (~25 LOC)
- `tests/test_agent_search_integration.py` — NEW (~250 LOC, 5-7 tests)
- Possibly `tests/test_agent.py` — IF any existing test asserts on `BASE_PROMPT` substring content (audit during implementation)
- Possibly `tests/conftest.py` — IF the `TracingFakeLLM` helper is extracted (defer; not required for L4)

**Total**: ~275 LOC. Above F10's ~50-100 LOC estimate, mostly from the integration tests (the prompt update alone is ~25 LOC; tests are the bulk). Acceptable; flag for L8 review queue if any concern.

## Citation Audit

Citations verified against current code at L4 design time (2026-05-10):

- `the_one/agent/config.py:9-32 — BASE_PROMPT constant` ✓ verified (line 9 start, line 32 end of the triple-quoted string)
- `the_one/agent/config.py:88-93 — AgentConfig.get_system_prompt` ✓ verified
- `the_one/agent/core.py:_compute_visible_schemas` (line 128) ✓ verified (L1-landed)
- `the_one/tools/_search_tools.py:SearchTools` ✓ verified (L2-landed)
- `the_one/tools/_search_mcps.py:SearchMcps` ✓ verified (L3-landed)
- `tests/conftest.py:48 — class FakeLLM(LLMProvider)` ✓ verified
- `tests/conftest.py:53-72 — FakeLLM.__init__ + complete` ✓ verified
- `tests/test_agent.py:7 — from conftest import FakeLLM, StubTool` ✓ verified
- `tests/test_agent.py:72-99 — example multi-response FakeLLM scripted test` ✓ verified
- `tests/test_agent.py:322 — test_pause_at_tc_b_defers_tc_b_and_tc_c (multi-iteration scripting reference)` ✓ verified

**Audit summary**: 10 citations verified against current code at leg design time. 10 OK, 0 drifted, 0 gone, 0 unverifiable.

---

## Post-Completion Checklist

**Complete ALL steps before marking leg `landed`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (file-scoped + L1+L2+L3 regression + full unit suite vs L3 post-landing baseline of 1498 pass)
- [ ] Update flight-log.md with L4 leg progress entry under "Leg Progress" section
- [ ] Set this leg's status to `landed` (NOT `completed`)
- [ ] Check off this leg in flight.md Legs list
- [ ] **Do NOT commit** — Phase 2d batches commits
- [ ] **Do NOT signal `[HANDOFF:review-needed]`** — reserved for Phase 2d
