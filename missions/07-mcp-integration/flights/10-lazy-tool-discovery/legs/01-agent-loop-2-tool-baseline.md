# Leg: 01-agent-loop-2-tool-baseline

**Status**: completed
**Flight**: [Lazy tool discovery](../flight.md)

## Objective

Refactor the agent loop so the schemas visible to the LLM at each iteration are computed by a per-iteration `_compute_visible_schemas()` method on the `Agent` class — returning `[SEARCH_TOOLS_SCHEMA, SEARCH_MCPS_SCHEMA, CONTINUE_SCHEMA] + self._loaded_schemas` — rather than the once-per-step `self.tools.all_schemas()` read at the top of `_run_iterations`. Ship CANNED-DATA stubs for `search_tools` and `search_mcps` that, when called, mutate the agent's `_loaded_schemas` list with a fixed set of 1-2 canned schemas, so the persistence-across-turns test actually exercises the mutation. L1 produces NO operator-felt improvement on its own — its standalone value is purely architectural (the new loop shape + state machine + per-iteration recompute + reset semantics + dispatch invariant under F5 pause/resume). The full search semantics land at L2 (`search_tools` real implementation) and L3 (`search_mcps` real implementation).

## Context

- **F10 §1 (auto-load)** — search tools mutate `_loaded_schemas` as a side effect of being called. Stubs in L1 demonstrate the mutation via canned results; L2+L3 land real filter logic.
- **F10 §2 (strict 2-tool baseline)** — only `search_tools`, `search_mcps`, and `continue` are visible to the LLM at session start. No always-loaded core.
- **F10 §3 (loaded set = visibility filter, not registry membership)** — the `ToolRegistry` (`self.tools`) holds the FULL candidate set as today (built-ins + every MCP tool from every attached source via existing `factory.create` flow). Dispatch via `self.tools.get(name)` in `_execute_tool` (`agent/core.py:255`) always finds the tool, regardless of loaded-set state. `_loaded_schemas` is purely a model-visibility filter. **L1 must preserve this invariant** — F5's deferred-then-resumed pause/resume path must compose trivially (a tool whose schema is in `_loaded_schemas` and whose execute triggers `MCPAuthRequired` gets deferred, then resumed via `resume_after_auth` at `core.py:209`; the resumed dispatch still finds the tool in the registry).
- **F10 §9 (per-iteration recompute)** — `_run_iterations` reads schemas inside the while-loop body via `_compute_visible_schemas()`. The `supports_tools()` gate (`core.py:108`) stays OUTSIDE the loop (one-time gate); only the schema computation moves into the loop body. A search call within iteration N adds schemas that show up in iteration N+1's `tools=` array.
- **F10 §10 (candidate-set construction Path A/B)** — L1 does NOT resolve Path A vs Path B. Factory keeps its current MCP integration (`factory.py:157-163` — `mcp_provider.get_tools_for_agent`). L1's scope is the loop + visibility filter; the cache-only-hydration question is L3's first task.
- **F10 design-review affirmation (architect, 2026-05-10)**: the visibility-filter framing resolves F5 pause/resume composition cleanly. L1 must add an explicit test for the deferred-then-resumed-MCP-tool path to lock in the invariant.
- **HAT-script interpretive shift**: `tests/HAT.md:111-113` and `:167` script-count `agent.tools.all_schemas()` filtered by `mcp__*` prefix. Under L1's contract, `all_schemas()` returns the FULL candidate set (registry membership), NOT the model-visible set. The assertions ("agent has these MCP tools") still pass because the candidate registry is unchanged — but the prose interpretation must be updated to say "the agent CAN load these MCP tools," not "the LLM sees these MCP tools."

## Inputs

What exists before this leg runs:

- F1-F8 + F9 L1+L2+L3 production state on `main` (= F10 branch base).
- F9 paused; F9 flight log Decision entry "F9 paused for F10 lazy-tool-discovery pivot (2026-05-10)" carried forward as uncommitted change on F10 branch.
- `the_one/agent/core.py` (291 LOC) — current state with `CONTINUE_SCHEMA` at line 11; `Agent.__init__` at line 42; `_run_iterations` at line 88 reading `tool_schemas = (self.tools.all_schemas() or []) + [CONTINUE_SCHEMA]` once per step at line 109; `_dispatch_tool_calls` at line 159; `resume_after_auth` at line 209; `_execute_tool` at line 244 dispatching via `self.tools.get(tool_call.name)` at line 255; `reset` at line 284.
- `the_one/agent/factory.py:78-174` — `AgentFactory.create()` builds the registry with built-in tools (`factory.py:147-150`), MCP tools (`factory.py:157-163`), and constructs `Agent(llm, tools=registry, ...)` at line 169-174.
- `the_one/agent/config.py:BASE_PROMPT` (line 9-32) — global prompt. L1 does NOT modify; L4 will.
- `the_one/tools/base.py:114-131 — class ToolRegistry` with `register`, `get`, `all_schemas`, `tool_names`. L1 does NOT modify this class.
- `tests/HAT.md` (269 LOC) — operator-facing HAT script with `agent.tools.all_schemas()` introspection at lines 111 + 167.

## Outputs

What exists after this leg completes:

- `the_one/agent/core.py` modified:
  - Two new module-level constants `SEARCH_TOOLS_SCHEMA` and `SEARCH_MCPS_SCHEMA` alongside `CONTINUE_SCHEMA` (~30 LOC). **These constants live in `agent/core.py` exclusively** — `_search_stubs.py` imports them from here to avoid a `tools → agent` import cycle (the existing direction is `agent → tools` at `core.py:8`, so reverse import would cycle).
  - `Agent.__init__` accepts `loaded_schemas: list[dict] | None = None` and `loaded_tool_names: set[str] | None = None` parameters (defaulting to fresh empty containers if omitted, for backward compatibility with non-factory call sites). Stores them as `self._loaded_schemas` and `self._loaded_tool_names` (~10 LOC).
  - New `Agent._compute_visible_schemas() -> list[dict]` method returning `[SEARCH_TOOLS_SCHEMA, SEARCH_MCPS_SCHEMA, CONTINUE_SCHEMA] + self._loaded_schemas` (~5 LOC).
  - **Remove the existing `_tool_schemas()` method at `core.py:60-63`** — it returns `self.tools.all_schemas() + [CONTINUE_SCHEMA]` which becomes dead code after L1 (no caller). Leaving it would mislead future readers; remove cleanly with a one-line commit message note (~4 LOC removal).
  - `_run_iterations` modified: hoist `supports_tools()` await to a local `supports_tools: bool` at the top (still outside the while-loop, one-time gate). The once-per-step `tool_schemas = (self.tools.all_schemas() or []) + [CONTINUE_SCHEMA]` at line 109 is REPLACED by a per-iteration call to `_compute_visible_schemas()` inside the while-loop body, gated by the hoisted `supports_tools` bool (~10 LOC net).
  - `Agent.reset()` modified to also clear `self._loaded_schemas` (`.clear()` in-place) and `self._loaded_tool_names` (`.clear()` in-place) — re-assignment would orphan the stub tools' closure-captured references (~3 LOC).
- New file `the_one/tools/_search_stubs.py` (~80 LOC):
  - `SearchToolsStub(Tool)` with `name = "search_tools"` as a **class attribute** (matches `ToolRegistry.register`'s `self._tools[tool.name]` at `base.py:118-119`). `description` and `parameters` also class attributes mirroring `SEARCH_TOOLS_SCHEMA`. `execute(query: str = "") -> str` appends 1-2 canned schemas to a shared `loaded_schemas` list via a constructor-supplied mutator callback. Returns a one-line result string like `"Found 2 tools: canned_tool_a, canned_tool_b (stub data; real implementation lands at L2)"`.
  - **Constructor calls `super().__init__()` (zero-arg valid because `Tool.__init__(config=None, cross_configs=None, agent_name=None)` defaults all three to None)** before storing `self._on_match`. Without this, `self._config` / `self._cross_configs` / `self._agent_name` are unset and any code path reading them raises AttributeError. (Alternative: mirror conftest.StubTool's pattern of manually setting the three base fields. Prefer `super().__init__()` for clarity.)
  - `SearchMcpsStub(Tool)` analogous, with its own class attributes and canned schemas.
  - Module-level `_CANNED_TOOL_SCHEMA_A`, `_CANNED_TOOL_SCHEMA_B`, `_CANNED_MCP_SCHEMA_A`, `_CANNED_MCP_SCHEMA_B` constants — minimal valid schemas suitable for test assertion (each has a unique `name` like `"_stub_canned_tool_a"`).
  - Imports `SEARCH_TOOLS_SCHEMA` and `SEARCH_MCPS_SCHEMA` from `the_one.agent.core` (single source of truth; no circular import since `agent → tools` is the existing direction).
- `the_one/agent/factory.py:create` modified to register the stub search tools in the registry (~10 LOC):
  - **Insertion point**: AFTER `registry = ToolRegistry()` at `factory.py:146`, BEFORE the built-in tool loop at `factory.py:147-150`. The stubs do not depend on other tools, so they can register first.
  - Create a shared `loaded_schemas: list[dict] = []` and `loaded_tool_names: set[str] = set()`.
  - Construct `SearchToolsStub` and `SearchMcpsStub` with a mutator callback (`_on_search_match`) that extends `loaded_schemas` and `loaded_tool_names` with idempotency-via-name-set (skips schemas whose `name` is already in `loaded_tool_names`).
  - Register both in the registry (so dispatch finds them).
  - Pass the same containers to `Agent.__init__` via the new keyword parameters at `factory.py:169-174`.
- `tests/HAT.md` updated (~20 LOC) — script comments at lines 111-113 + 167 updated to reflect the contract shift ("registry membership" vs "model-visibility"). Assertions unchanged; only the surrounding prose. Add a one-paragraph note at the top of the file flagging the F10 change for HAT readers.
- New test file `tests/test_agent_visibility_filter.py` (~200 LOC, ~7-11 tests):
  - `test_default_visible_schemas_at_session_start` — `_compute_visible_schemas()` on a fresh agent returns exactly `[SEARCH_TOOLS_SCHEMA, SEARCH_MCPS_SCHEMA, CONTINUE_SCHEMA]`.
  - `test_search_stub_mutates_loaded_schemas` — calling `SearchToolsStub.execute(...)` extends the shared `loaded_schemas` list with canned entries; `_compute_visible_schemas()` next call reflects the addition.
  - `test_per_iteration_recompute` — drive `_run_iterations` with a mock LLM that calls `search_tools` in iteration N, calls `_stub_canned_tool_a` in iteration N+1; assert iteration N+1's `tools=` argument contains `_stub_canned_tool_a`'s schema.
  - `test_reset_clears_loaded_state` — populate `_loaded_schemas` via a stub call, call `agent.reset()`, assert `_compute_visible_schemas()` returns the baseline 3 schemas only.
  - `test_persistence_across_user_turns` — call `step()` twice with a mock LLM that calls `search_tools` in turn 1's iteration, calls `_stub_canned_tool_a` in turn 2's iteration; assert turn 2 sees the loaded schema (i.e., loaded state is not cleared between turns).
  - `test_deferred_resumed_mcp_tool_dispatch` — register a mock MCP tool whose execute raises `MCPAuthRequired`; populate `_loaded_schemas` with its schema via stub call; drive `step()` so the deferred-tool-calls path fires; call `resume_after_auth()`; assert the resumed dispatch via `self.tools.get(...)` succeeds even though the loaded-set state has been mutated since the defer. **This is the F5 pause/resume invariant lock-in test.**
  - `test_supports_tools_gate_outside_loop` — verify that a provider returning `supports_tools() = False` runs plain chat (empty `tools=` to llm.stream); only ONE `supports_tools()` await **per `_run_iterations` entry** (NOT per user turn). Mock provider with `await_count` instrumentation. **Resume-path note**: `resume_after_auth` at `core.py:209-242` re-enters `_run_iterations` at its tail, so a full step-with-deferred-tool-call exercises `_run_iterations` twice and thus awaits `supports_tools()` twice (once in the original entry, once in resume). Acceptable — the contract is "once per `_run_iterations` entry," not "once per user turn." `test_deferred_resumed_mcp_tool_dispatch` should assert total `supports_tools()` call count is 2 across the full defer+resume path.
  - `test_search_stub_idempotent` — call `SearchToolsStub.execute(...)` twice with the same query; assert `_loaded_schemas` has 2 entries (not 4) and `_loaded_tool_names` has 2 entries. Validates the `_on_search_match` deduplication.

## Acceptance Criteria

- [ ] `the_one/agent/core.py` has module-level `SEARCH_TOOLS_SCHEMA` + `SEARCH_MCPS_SCHEMA` constants alongside `CONTINUE_SCHEMA` (line 11 region).
- [ ] `Agent.__init__` accepts `loaded_schemas` + `loaded_tool_names` keyword parameters; stores them as instance state; both default to fresh empty containers if omitted.
- [ ] `Agent._compute_visible_schemas()` returns exactly `[SEARCH_TOOLS_SCHEMA, SEARCH_MCPS_SCHEMA, CONTINUE_SCHEMA] + self._loaded_schemas` (in that order).
- [ ] `_run_iterations` reads `_compute_visible_schemas()` per iteration (inside the while-loop), NOT once per step. `supports_tools()` await stays outside the loop.
- [ ] `Agent.reset()` clears `self._loaded_schemas` (back to empty list) and `self._loaded_tool_names` (back to empty set).
- [ ] `the_one/tools/_search_stubs.py` provides `SearchToolsStub` and `SearchMcpsStub` Tool subclasses with canned-data execute behavior; both accept a constructor mutator callback that extends `loaded_schemas` and `loaded_tool_names`.
- [ ] `AgentFactory.create` registers `SearchToolsStub` and `SearchMcpsStub` in the registry before returning the Agent; the same `loaded_schemas` + `loaded_tool_names` containers are passed to `Agent.__init__`.
- [ ] `tests/HAT.md` prose updated at lines 111-113 + 167 to clarify the registry-vs-visibility contract; existing assertions still pass UNMODIFIED.
- [ ] All 7-11 tests in `tests/test_agent_visibility_filter.py` pass.
- [ ] All prior tests pass (verify against F8 baseline: `1376 unit / 255 browser / 43 pre-existing flakes`). L1's 7-11 new tests in `tests/test_agent_visibility_filter.py` are net additions; expected post-L1 unit count is `1376 + N` where N = L1's test count. Existing `tests/test_tool_registry.py` is unchanged (registry contract unchanged at L1). `tests/test_agent.py` may need one or more tests updated if they directly assert on the model-visible `tools=` array — those assertions now expect the new baseline (`[search_tools, search_mcps, continue]`) instead of the full registry. Update those inline as part of L1.
- [ ] **`SearchToolsStub.name` and `SearchMcpsStub.name` are CLASS attributes** (not instance attributes) so `ToolRegistry.register` at `base.py:118-119` can index `self._tools[tool.name]` correctly.
- [ ] **Both stub `__init__` methods call `super().__init__()`** so `Tool`'s base fields (`self._config`, `self._cross_configs`, `self._agent_name`) are set; no `AttributeError` on any path that reads them.
- [ ] **`Agent._tool_schemas()` method at `core.py:60-63` is removed** — becomes dead code under L1's per-iteration `_compute_visible_schemas()` contract.
- [ ] F5 pause/resume invariant locked in by `test_deferred_resumed_mcp_tool_dispatch` — a deferred MCP tool whose schema was in `_loaded_schemas` resumes successfully even if `_loaded_schemas` has been mutated since the defer.

## Verification Steps

- Run unit tests scoped to L1's surface: `docker exec the-one pytest tests/test_agent_visibility_filter.py -x --timeout 30 -v`. Expect 7-11 passes.
- Run touched test files: `docker exec the-one pytest tests/test_agent.py tests/test_agent_factory.py tests/test_tool_registry.py -x --timeout 30 -v`. Expect green. (Note: the actual agent-loop test file is `tests/test_agent.py`, not `tests/test_agent_core.py` — fixtures come from `tests/conftest.py` including `FakeLLM` and `StubTool`.)
- Run full unit suite once at leg-end: `docker exec the-one pytest -q --timeout 120 --ignore=tests/test_mcp_pool.py`. Expect 1376 pass (matches F8 baseline; no regressions).
- Confirm HAT.md prose updates: `git diff tests/HAT.md` shows only prose changes around lines 111-113 + 167 and the new top-of-file note. No assertion changes.
- Manual sanity: open Python shell, construct an `Agent` with a fresh `ToolRegistry` (no real tools beyond the stubs registered by factory equivalent), inspect `agent._compute_visible_schemas()` — should return exactly 3 schemas (`search_tools`, `search_mcps`, `continue`).

## Implementation Guidance

### Wiring the stubs into the factory

The factory currently constructs the `ToolRegistry` (line 146), populates it with built-in tools (147-150), populates it with MCP tools (157-163), then constructs the `Agent` (169-174). L1 inserts the search-stubs registration plus the shared-container plumbing.

**Recommended shape** (one of several valid; the implementing agent may pick a different shape if it composes more cleanly with existing patterns):

```python
# In factory.create, after registry = ToolRegistry() (line 146):

# F10 L1: shared state container for the visibility filter. The stub
# search tools and the Agent both reference these — the stubs MUTATE
# them as a side effect of being called; the Agent READS them to
# compute model-visible schemas per iteration.
loaded_schemas: list[dict] = []
loaded_tool_names: set[str] = set()

def _on_search_match(schemas: list[dict]) -> None:
    """Extend the shared visibility set with newly-matched schemas.
    Idempotent — re-adding a schema already in the set is a no-op."""
    for s in schemas:
        if s["name"] not in loaded_tool_names:
            loaded_schemas.append(s)
            loaded_tool_names.add(s["name"])

registry.register(SearchToolsStub(on_match=_on_search_match))
registry.register(SearchMcpsStub(on_match=_on_search_match))

# ... existing built-in + MCP registration unchanged ...

# When constructing the Agent (line 169-174):
return Agent(
    llm=llm,
    tools=registry,
    system_prompt=system_prompt,
    max_iterations=config.max_iterations,
    loaded_schemas=loaded_schemas,
    loaded_tool_names=loaded_tool_names,
)
```

### Stub Tool shape

```python
# the_one/tools/_search_stubs.py

from collections.abc import Callable

from the_one.tools.base import Tool

# Minimal valid tool schemas for canned mutation. Names are deliberately
# distinctive (_stub_canned_*) so test assertions can spot them without
# colliding with any real tool name in the codebase.
_CANNED_TOOL_SCHEMA_A = {
    "name": "_stub_canned_tool_a",
    "description": "L1 stub canned tool A — not a real tool. Replaced by L2's real search_tools.",
    "parameters": {"type": "object", "properties": {}, "required": []},
}
_CANNED_TOOL_SCHEMA_B = {
    "name": "_stub_canned_tool_b",
    "description": "L1 stub canned tool B — not a real tool. Replaced by L2's real search_tools.",
    "parameters": {"type": "object", "properties": {}, "required": []},
}
# ... and _CANNED_MCP_SCHEMA_A, _CANNED_MCP_SCHEMA_B analogously

SEARCH_TOOLS_SCHEMA = {  # also re-exported from agent/core.py for direct use
    "name": "search_tools",
    "description": (
        "Search the built-in tool catalog for tools matching a query. "
        "Matched tools are automatically added to your available toolset "
        "for the rest of this conversation. Call with an empty query to "
        "list all available tools."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Substring to search for in tool names and descriptions. Empty string returns all."},
        },
        "required": [],
    },
}

class SearchToolsStub(Tool):
    """L1 stub for search_tools. Returns canned data so persistence tests
    can exercise the mutation. Replaced by the real implementation at L2."""

    name = "search_tools"
    description = SEARCH_TOOLS_SCHEMA["description"]
    parameters = SEARCH_TOOLS_SCHEMA["parameters"]

    def __init__(self, on_match: Callable[[list[dict]], None]) -> None:
        self._on_match = on_match

    async def execute(self, query: str = "") -> str:
        canned = [_CANNED_TOOL_SCHEMA_A, _CANNED_TOOL_SCHEMA_B]
        self._on_match(canned)
        return (
            f"Found {len(canned)} tools matching {query!r}: "
            f"{_CANNED_TOOL_SCHEMA_A['name']}, {_CANNED_TOOL_SCHEMA_B['name']} "
            f"(L1 stub data; real implementation lands at L2)."
        )
```

`SearchMcpsStub` follows the same pattern with `_CANNED_MCP_SCHEMA_*` constants. The `SEARCH_TOOLS_SCHEMA` / `SEARCH_MCPS_SCHEMA` constants can live in `agent/core.py` (preferred — alongside `CONTINUE_SCHEMA`) and be imported by `_search_stubs.py`, OR vice versa. Pick whichever import direction avoids circular imports given current module layout.

### Agent changes

```python
# agent/core.py

# Module-level alongside CONTINUE_SCHEMA (line 11):
SEARCH_TOOLS_SCHEMA = {"name": "search_tools", "description": "...", "parameters": {...}}
SEARCH_MCPS_SCHEMA = {"name": "search_mcps", "description": "...", "parameters": {...}}

class Agent:
    def __init__(
        self,
        llm: LLMProvider,
        tools: ToolRegistry,
        system_prompt: str,
        max_iterations: int = 20,
        *,
        loaded_schemas: list[dict] | None = None,
        loaded_tool_names: set[str] | None = None,
    ) -> None:
        # ... existing fields ...
        # F10 L1: visibility filter. SHARED CONTAINERS with the factory-
        # constructed search-stub tools — mutations from those tools land
        # in these containers; _compute_visible_schemas reads them.
        self._loaded_schemas: list[dict] = loaded_schemas if loaded_schemas is not None else []
        self._loaded_tool_names: set[str] = loaded_tool_names if loaded_tool_names is not None else set()

    def _compute_visible_schemas(self) -> list[dict]:
        """F10 L1: per-iteration model-visible schemas.

        Returns the 2-tool baseline (search_tools, search_mcps) + continue
        + any schemas the search tools have loaded into the visibility set
        as a side effect of being called. The Agent's ToolRegistry holds
        the FULL candidate set; this method computes the filtered view
        the LLM sees on each iteration's tools= array."""
        return [SEARCH_TOOLS_SCHEMA, SEARCH_MCPS_SCHEMA, CONTINUE_SCHEMA] + self._loaded_schemas
```

`_run_iterations` changes (lines 108-111 region):

```python
# Resolve supports_tools ONCE per _run_iterations entry (network call
# in some provider implementations). The schemas computation moves
# inside the while loop so search-driven additions to _loaded_schemas
# show up on the next iteration's tools= array.
supports_tools = await self.llm.supports_tools()

while self._remaining_iterations > 0:
    self._remaining_iterations -= 1

    # F10 L1: per-iteration visibility filter recompute.
    if supports_tools:
        tool_schemas = self._compute_visible_schemas()
    else:
        tool_schemas = []

    # ... rest of the iteration body unchanged ...
```

`reset()` (line 284):

```python
def reset(self) -> None:
    """Reset messages to the system prompt and clear pause state."""
    self.messages = [Message.system(self.system_prompt)]
    self._deferred_tool_calls = None
    self._remaining_iterations = 0
    # F10 L1: clear visibility filter so the next step starts blind.
    self._loaded_schemas.clear()
    self._loaded_tool_names.clear()
```

Note: `.clear()` mutates in-place — important because the same containers may be referenced by the stub tools via the `on_match` callback's closure. Re-assignment (`self._loaded_schemas = []`) would orphan the stubs' reference and break post-reset searches.

### F5 pause/resume invariant test detail

```python
async def test_deferred_resumed_mcp_tool_dispatch(...):
    """F10 L1 lock-in: a tool whose schema is in _loaded_schemas and
    whose execute triggers MCPAuthRequired gets deferred via
    _dispatch_tool_calls; resume_after_auth re-dispatches via
    self.tools.get(name); the resumed dispatch must succeed even if
    _loaded_schemas has been mutated since the defer (e.g., a different
    search call added other schemas in between).
    
    This locks in F10 §3's invariant: registry holds the full candidate
    set; loaded_schemas is purely a visibility filter; dispatch is
    independent of loaded-set state."""
    
    # Setup: agent with a mock MCP tool registered in self.tools; its
    # execute() raises MCPAuthRequired on first call, returns a normal
    # ToolResult on second call.
    # Drive: step() with a mock LLM that calls the mock MCP tool.
    # Expect: _deferred_tool_calls captures the call; _broadcast_one
    # emits auth_required (no tool message).
    # Now mutate: append a different canned schema to _loaded_schemas
    # (simulating an unrelated search call between defer and resume).
    # Drive: resume_after_auth().
    # Expect: the resumed dispatch via self.tools.get(...) succeeds and
    # the second call's normal ToolResult flows through.
```

### Test scaffolding notes

- **Test file location**: agent loop tests are in `tests/test_agent.py`; fixtures are in `tests/conftest.py` (including `FakeLLM` and `StubTool`). `FakeLLM` only implements `complete()`; `stream()` is inherited from `LLMProvider.stream()` at `llm/base.py:100-119` which delegates to `complete()` and yields a single `StreamChunk` with `is_final=True`. This is sufficient for L1's tests — each `step()` call consumes one `responses` entry per iteration via the existing `FakeLLM.responses` queue pattern.
- For `test_per_iteration_recompute`: pre-load `FakeLLM.responses` with `[response_calling_search_tools, response_calling_canned_tool_a, response_with_text_only]`. Drive `step()`; assert iteration 2's `llm.stream` call's `tools=` argument contains `_CANNED_TOOL_SCHEMA_A`. May need to instrument `FakeLLM` (or wrap it) to record `tools=` per call.
- For `test_persistence_across_user_turns`: call `step()` twice. First `step()`: pre-load `[response_calling_search_tools, response_with_text_only]`. Second `step()`: pre-load `[response_calling_canned_tool_a, response_with_text_only]`. Verify second `step()`'s first iteration's `tools=` contains `_CANNED_TOOL_SCHEMA_A` (i.e., loaded state persisted across the user-turn boundary).
- **`tests/conftest.py:StubTool`** at lines 80-109 demonstrates the manual-base-field-mirror pattern. L1's stubs prefer `super().__init__()` over manual mirroring for clarity, but if `super().__init__()` causes any issue (it shouldn't, since `Tool.__init__` defaults all three params to None), fall back to conftest.StubTool's manual pattern.

### HAT.md updates

```diff
@@ Line 111-113 region @@
-    schemas = agent.tools.all_schemas()
-    print(f"Total tools: {len(schemas)}")
-    mcp_tools = [s for s in schemas if s["name"].startswith("mcp__")]
+    # NOTE (F10 L1): agent.tools.all_schemas() returns the full CANDIDATE
+    # registry — the tools the agent CAN load via search, not the ones
+    # currently visible to the LLM in tools=. The MCP-prefix count below
+    # still validates "the registry was correctly populated by factory."
+    schemas = agent.tools.all_schemas()
+    print(f"Total candidate tools: {len(schemas)}")
+    mcp_tools = [s for s in schemas if s["name"].startswith("mcp__")]
```

Plus a similar interpretive-note comment at line 167. Add a top-of-file paragraph (after the existing intro) flagging the F10 contract shift:

```diff
+## F10 contract note
+
+Post-F10 (lazy tool discovery): `agent.tools.all_schemas()` returns the
+full CANDIDATE registry — every tool the agent CAN load via search. The
+LLM only sees `[search_tools, search_mcps, continue] + agent._loaded_schemas`
+per iteration. HAT scripts in this file that script-count `all_schemas()`
+filtered by `mcp__*` prefix are validating registry membership, not
+model-visibility. The assertions still hold; the prose interpretation has
+shifted.
```

## Edge Cases

- **Empty registry (no built-in tools, no MCPs)**: `_compute_visible_schemas()` returns exactly `[search_tools, search_mcps, continue]`. Verify in `test_default_visible_schemas_at_session_start`.
- **`supports_tools()` returns False**: the existing behavior (run plain chat with no tools) is preserved — `tool_schemas = []` inside the loop. Verify in `test_supports_tools_gate_outside_loop` (which also asserts the `await self.llm.supports_tools()` is called exactly once per `_run_iterations` entry).
- **Resume after auth with mutated loaded set**: locked in by `test_deferred_resumed_mcp_tool_dispatch`. The resumed dispatch ignores `_loaded_schemas` entirely; it reads from `self.tools` directly.
- **Container reassignment vs in-place mutation in `reset()`**: must use `.clear()` (mutates in place) so the stub tools' closure-captured reference stays valid. Test: call stub.execute() after reset, verify the mutation lands in `agent._loaded_schemas` not an orphaned container.
- **Stub returns canned schemas with names that collide with existing real tools**: deliberately chose `_stub_canned_*` prefix to make collisions impossible against the production catalog. Verify by greping for `_stub_canned` in the production codebase — should be only in the new `_search_stubs.py` file.
- **Backward compatibility with non-factory Agent construction**: some tests likely construct Agent directly without going through factory (e.g., `tests/test_agent.py`). The new `loaded_schemas` + `loaded_tool_names` parameters default to None / fresh empty containers, so direct-construction tests pass without modification.
- **F9 flight-log change carried in working tree**: the F9 pivot-decision commit landed on F10 branch as part of the branch-creation carry-over. NOT L1's concern; it flows through with the eventual flight-close commit.

## Files Affected

- `the_one/agent/core.py` — primary modification (~50 LOC additions, ~5 LOC modifications)
- `the_one/tools/_search_stubs.py` — NEW (~80 LOC)
- `the_one/agent/factory.py` — wiring (~10 LOC additions)
- `tests/HAT.md` — prose updates (~20 LOC across 2 sites + top-of-file note)
- `tests/test_agent_visibility_filter.py` — NEW (~200 LOC, 7-11 tests)

**Total**: ~360 LOC. Within F10 §2 sizing.

## Citation Audit

Citations verified against current code at L1 design time (2026-05-10):

- `the_one/agent/core.py:11 — CONTINUE_SCHEMA = {` ✓ verified
- `the_one/agent/core.py:42 — def __init__(` (Agent class) ✓ verified
- `the_one/agent/core.py:88 — async def _run_iterations(` ✓ verified
- `the_one/agent/core.py:108-111 — supports_tools gate + tool_schemas assign` ✓ verified
- `the_one/agent/core.py:118-121 — async for chunk in self.llm.stream(...tools=tool_schemas or None)` ✓ verified
- `the_one/agent/core.py:159 — async def _dispatch_tool_calls(` ✓ verified
- `the_one/agent/core.py:209 — async def resume_after_auth(` ✓ verified
- `the_one/agent/core.py:244 — async def _execute_tool(self, tool_call: ToolCall)` ✓ verified
- `the_one/agent/core.py:255 — tool = self.tools.get(tool_call.name)` ✓ verified
- `the_one/agent/core.py:284 — def reset(self) -> None:` ✓ verified
- `the_one/agent/factory.py:78 — async def create(self, name: str = "default")` ✓ verified
- `the_one/agent/factory.py:146 — registry = ToolRegistry()` ✓ verified
- `the_one/agent/factory.py:147-150 — for provider in self.tool_providers: for tool in provider.get_tools(...): registry.register(tool)` ✓ verified
- `the_one/agent/factory.py:157-163 — if self.mcp_provider is not None and config.mcp_source_ids: ... registry.register(tool)` ✓ verified
- `the_one/agent/factory.py:169-174 — return Agent(llm=llm, tools=registry, ...)` ✓ verified
- `the_one/tools/base.py:114 — class ToolRegistry:` ✓ verified
- `the_one/tools/base.py:126 — def all_schemas(self) -> list[dict[str, Any]]:` ✓ verified
- `tests/HAT.md:111 — schemas = agent.tools.all_schemas()` ✓ verified
- `tests/HAT.md:113 — mcp_tools = [s for s in schemas if s["name"].startswith("mcp__")]` ✓ verified
- `tests/HAT.md:167 — mcp_tools = [s["name"] for s in agent.tools.all_schemas() if s["name"].startswith("mcp__")]` ✓ verified

**Audit summary**: 20 citations verified against current code at leg design time. 20 OK, 0 drifted, 0 gone, 0 unverifiable.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (file-scoped + full unit suite vs F8 baseline)
- [ ] Update flight-log.md with leg progress entry under "Leg Progress" section, including: implementation notes, anomalies surfaced (if any), test count delta vs F8 baseline, LOC count
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md Legs list
- [ ] **Do NOT commit yet** — per agentic-workflow Phase 2d, commits are deferred until after the last autonomous leg
- [ ] Signal `[HANDOFF:review-needed]` (NOT `[COMPLETE:leg]` — that comes after the flight-batched commit)
