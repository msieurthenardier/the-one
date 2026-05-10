# Leg: 02-search-tools-implementation

**Status**: completed
**Flight**: [Lazy tool discovery](../flight.md)

## Objective

Replace L1's `SearchToolsStub` (canned-data) with `SearchTools` — a real implementation that iterates the agent's `ToolRegistry`, filters out the search tools themselves and any `mcp__`-prefixed names (those belong to `search_mcps` per L3's split), substring-matches the query against name + description (case-insensitive), and adds matched schemas to `_loaded_schemas` via the shared `on_match` callback. Empty query returns all built-in tools available to the agent. Per-agent `enabled_tools` / `disabled_tools` filtering is ALREADY APPLIED at registry-build time by `factory.py:178-181` — `SearchTools` does NOT re-apply it; the registry passed at construction already excludes denied tools. L1's `SearchMcpsStub` is untouched (L3's territory). By leg close, an agent calling `search_tools("file")` sees real built-in tools like `read_file`, `write_file`, `list_dir`, `edit_file`, `delete_file`, `move_file` appear in next iteration's `tools=` array.

## Context

- **F10 §1 (auto-load)** — search auto-loads matched schemas into next iteration's visibility. L2 lands the real implementation; semantics unchanged from L1's stub.
- **F10 §2 (strict 2-tool baseline)** — built-in tools are NEVER registered into the model-visible catalog by default; the agent must call `search_tools` to discover them. L1 already enforces this (visibility filter via `_compute_visible_schemas`); L2 makes the search return real results.
- **F10 §3 (loaded set = visibility filter, not registry membership)** — the `ToolRegistry` passed to `SearchTools` at construction already holds every built-in tool the agent is allowed to use (per-agent `enabled_tools` / `disabled_tools` filtered at `factory.py:178-181`). `SearchTools` filters out the search tools themselves + MCP tools by namespace prefix; remaining tools are the agent's true built-in surface. Dispatch via `self.tools.get(name)` continues to work — `SearchTools` only mutates visibility, not registry membership.
- **F10 §4 (substring match, case-insensitive)** — no embeddings, no scoring. Lowercase the query; lowercase the candidate's name + description; return candidates whose concatenated text contains the query substring. Empty query returns all (after the search-tool + mcp__ prefix filter).
- **L1 outcome carry-forward**:
  - `SearchToolsStub` + `SearchMcpsStub` live in `the_one/tools/_search_stubs.py`. L2 keeps the file (`SearchMcpsStub` stays for L3 replacement; `SearchToolsStub` becomes test-only fixture for L1's visibility-filter contract tests).
  - Factory at `the_one/agent/factory.py:175-176` registers both stubs with `agent_name=name` + the `_on_search_match` closure.
  - Agent at `the_one/agent/core.py:80` (class declaration; `__init__` at line 91); accepts `loaded_schemas` + `loaded_tool_names` kwargs (loaded_schemas at line 98); `_compute_visible_schemas()` at line 128 reads them per iteration.
  - 12 tests in `tests/test_agent_visibility_filter.py` lock in the L1 contract using the stubs directly. L2 leaves these tests UNCHANGED — they continue to use stubs as test-only fixtures.
- **Built-in tool catalog** (current state of `the_one/tools/`): ~20 tools across `filesystem.py`, `shell.py`, `python_exec.py`, `web.py`, `sessions.py`. Includes (sample): `shell`, `python_exec`, `read_file`, `write_file`, `list_dir`, `edit_file`, `delete_file`, `move_file`, `mkdir`, `glob`, `grep`, `http_request`, `fetch_url`, `download_file`, `web_search`, `shell_session_start`, `shell_session_send`, `shell_session_close`, `shell_session_list`. Plus `search_tools` + `search_mcps` themselves (in registry after L1). Per-agent enabling may reduce this set.
- **Why the stubs stay**: L1 tests heavily exercise `SearchToolsStub`'s canned-data behavior to lock in the visibility-filter contract (mutation, persistence across turns, reset semantics, dedup idempotency). Migrating these tests to use the real impl would require shimming real tool names, complicate dedup assertions, and add coupling between the agent-loop tests and the actual built-in tool catalog. Cleaner: keep stubs as test fixtures, register real impl in production. The stub class continues to live in `_search_stubs.py`; L1 tests import it directly. **The factory uses the real impl from L2 onward; tests that need precise canned mutation use the stub directly.**

## Inputs

What exists before this leg runs:

- L1 landed: 12 tests in `tests/test_agent_visibility_filter.py` passing; full unit suite at 1462 pass; F10 branch `flight/10-lazy-tool-discovery` checked out.
- `the_one/tools/_search_stubs.py` (133 LOC): `SearchToolsStub` (lines 59-92) + `SearchMcpsStub` (lines 100-133) + canned schema constants.
- `the_one/agent/core.py:33 — SEARCH_TOOLS_SCHEMA` (module constant; `SearchTools` will reuse the description + parameters via class attributes).
- `the_one/agent/core.py:56 — SEARCH_MCPS_SCHEMA` (used by `_compute_visible_schemas` at line 128; not modified by L2).
- `the_one/agent/factory.py:12 — from the_one.tools._search_stubs import SearchMcpsStub, SearchToolsStub` (L1 import).
- `the_one/agent/factory.py:155-176 — wiring sequence` (containers + closure + stub registrations).
- `the_one/agent/factory.py:178-181 — built-in tool filter loop` (`for provider in self.tool_providers: for tool in provider.get_tools(...): if tool.name not in disabled_names and config.is_tool_enabled(tool.name): registry.register(tool)` — pre-filters by per-agent `enabled_tools` / `disabled_tools`).
- `the_one/agent/factory.py:193-194 — MCP tool filter loop` (same per-agent filter applied to MCP tools).
- `the_one/tools/base.py:114-131 — class ToolRegistry` (`register`, `get`, `all_schemas`, `tool_names`).
- Built-in tool sources: `the_one/tools/{filesystem,shell,python_exec,web,sessions}.py` — class names + name constants verified.

## Outputs

What exists after this leg completes:

- **NEW**: `the_one/tools/_search_tools.py` (~150 LOC):
  - `SearchTools(Tool)` real implementation. Class attributes `name = "search_tools"`, `description` + `parameters` imported from `SEARCH_TOOLS_SCHEMA` at `agent.core` (single source of truth).
  - Constructor: `__init__(self, on_match: Callable[[list[dict]], None], registry: ToolRegistry, agent_name: str | None = None)`. Calls `super().__init__(agent_name=agent_name)`. Stores `self._on_match`, `self._registry`, `self._agent_name`.
  - `execute(query: str = "") -> str`: iterates `self._registry.all_schemas()`, applies filter chain (search-tool name exclusion → mcp__ prefix exclusion → substring match), calls `self._on_match(matches)`, returns formatted result text.
  - Helper: `_filter_candidates(schemas, query)` for testability — extracted pure function returning the filtered list given the raw schemas + query string.
- **MODIFIED**: `the_one/agent/factory.py` (~5 LOC net change):
  - Add import of `SearchTools` from `_search_tools` alongside existing stub imports.
  - At line 175 (search stub registration), REPLACE `SearchToolsStub(on_match=_on_search_match, agent_name=name)` with `SearchTools(on_match=_on_search_match, registry=registry, agent_name=name)`.
  - Line 176 (`SearchMcpsStub` registration) UNCHANGED — L3 will replace.
- **MODIFIED**: `the_one/tools/_search_stubs.py` (no functional change; module-level docstring updated):
  - Add a module-level comment noting `SearchToolsStub` is now a test-only fixture (post-L2); production wiring uses `SearchTools` from `_search_tools.py`. `SearchMcpsStub` remains live in production until L3 replaces it.
- **NEW**: `tests/test_search_tools.py` (~250 LOC, 8-12 tests):
  - `test_empty_query_returns_all_filtered` — empty query returns all built-in tools (excluding `search_tools`, `search_mcps`, and `mcp__*`).
  - `test_query_substring_match_on_name` — query `"shell"` returns `shell`, `shell_session_start`, `shell_session_send`, `shell_session_close`, `shell_session_list` (and nothing else).
  - `test_query_substring_match_on_description` — query against text known to appear in a tool's description (verify by reading the actual tool's description at test-write time) returns that tool.
  - `test_query_case_insensitive` — query `"SHELL"` returns the same set as `"shell"`.
  - `test_no_match_returns_helpful_text` — query `"xyzzy_nonexistent"` returns `"No tools found matching 'xyzzy_nonexistent'."` (==-assert the exact format string from the implementation, including trailing period); also assert `_loaded_schemas` was NOT mutated.
  - `test_excludes_search_tools_from_results` — query `"search"` does NOT return `search_tools` or `search_mcps` in the result, even though they're in the registry and their names match.
  - `test_excludes_mcp_prefixed_tools_from_results` — register a mock tool with name `"mcp__foo__bar"` in a test registry; query `"foo"` does NOT return it (filtered by `mcp__` prefix).
  - `test_mutates_loaded_schemas_via_on_match` — call `execute("file")` against a registry with real built-in tools; assert shared container received the matched schemas.
  - `test_idempotent_on_repeated_calls` — call `execute("file")` twice; verify dedup via `on_match` callback (shared loaded_tool_names dedupes; shared loaded_schemas doesn't grow on second call). Mirrors L1's `test_search_stub_idempotent`.
  - `test_real_impl_in_factory_wiring` — call `AgentFactory.create("default")` (or equivalent); assert the registry contains a `SearchTools` instance (not `SearchToolsStub`) under the name `"search_tools"`.
  - `test_filter_helper_pure_function` — unit-test `_filter_candidates(schemas, query)` independently of any registry or agent state; covers empty schemas list, empty query, mixed filter exclusions.
  - `test_real_impl_per_agent_filter_applied_at_registry_level` — set `enabled_tools=["read_file", "write_file"]` on a test agent config; create agent via factory; verify `search_tools("")` empty-query returns ONLY those two (plus exclude search tools + mcp__*); the registry-level filter is the source of truth.

## Acceptance Criteria

- [ ] `the_one/tools/_search_tools.py` exists with `SearchTools(Tool)` class as described in Outputs.
- [ ] `SearchTools.name` is the class attribute `"search_tools"` (matches `ToolRegistry.register`'s `self._tools[tool.name]` keying).
- [ ] `SearchTools.__init__` calls `super().__init__(agent_name=agent_name)` so `Tool`'s base fields are set; no `AttributeError` on any path reading them.
- [ ] `SearchTools.description` and `SearchTools.parameters` are class attributes mirroring `SEARCH_TOOLS_SCHEMA` from `agent.core` (single source of truth — import the schema constant).
- [ ] `SearchTools.execute("")` returns ALL built-in tool schemas in the registry, excluding `search_tools`, `search_mcps`, and any `mcp__`-prefixed names. Result text is operator-readable.
- [ ] `SearchTools.execute(query)` for non-empty query: lowercase the query; lowercase each candidate's `f"{name} {description}"`; return candidates whose concatenated text contains the lowercased query.
- [ ] `SearchTools.execute(query)` calls `self._on_match(matches)` exactly once per call, with the list of matched schemas. `on_match` dedup (via `loaded_tool_names`) prevents duplicate additions across repeated calls.
- [ ] No-match path: return helpful text (e.g., `"No tools found matching {query!r}"`) AND do not mutate `_loaded_schemas`.
- [ ] `the_one/agent/factory.py` imports `SearchTools` and registers it (NOT `SearchToolsStub`) at the search-tools registration site (line 175). `SearchMcpsStub` registration at line 176 unchanged.
- [ ] `the_one/tools/_search_stubs.py` module-level comment updated to note that `SearchToolsStub` is now test-only (post-L2); `SearchMcpsStub` remains live in production until L3.
- [ ] All L1 tests in `tests/test_agent_visibility_filter.py` PASS UNMODIFIED (they use stubs directly; no production-wiring assumption inside).
- [ ] All 8-12 new tests in `tests/test_search_tools.py` pass.
- [ ] Full unit suite passes: `docker exec the-one pytest -q --timeout 120 --ignore=tests/test_mcp_pool.py`. Expected post-L2 count is `1462 + N` where N = L2 test count (8-12).
- [ ] No regression in F8 baseline browser suite (`docker exec the-one pytest tests/browser/ -q --timeout 120 -m browser` should still show 255 pass / 43 pre-existing flakes).

## Verification Steps

- Run unit tests scoped to L2's surface: `docker exec the-one pytest tests/test_search_tools.py -x --timeout 30 -v`. Expect 8-12 passes.
- Run L1 regression: `docker exec the-one pytest tests/test_agent_visibility_filter.py -x --timeout 30 -v`. Expect 12 passes (all L1 contract tests still passing; stubs untouched).
- Run touched test files: `docker exec the-one pytest tests/test_search_tools.py tests/test_agent_visibility_filter.py tests/test_factory.py tests/test_agent.py -x --timeout 30 -v`. Expect green.
- Run full unit suite at leg-end: `docker exec the-one pytest -q --timeout 120 --ignore=tests/test_mcp_pool.py`. Expect `1462 + N` pass (where N = L2's test count).
- Manual sanity (optional): in a Python shell, construct a registry with the built-in providers + register `SearchTools`; call `await search_tools.execute("file")`; verify the result text mentions the filesystem tools.

## Implementation Guidance

### Recommended `SearchTools` shape

```python
# the_one/tools/_search_tools.py

"""F10 L2: real implementation of search_tools.

Replaces L1's SearchToolsStub at production wiring. Iterates the agent's
ToolRegistry, applies the search-tool + mcp__ prefix exclusions, substring-
matches against name + description (case-insensitive), and mutates the
shared visibility-filter container via the on_match callback.

Per-agent enabled_tools/disabled_tools filtering is ALREADY APPLIED at
registry-build time by factory.py:178-181. SearchTools relies on that;
it does NOT re-apply per-agent filtering. The registry passed at
construction is the source of truth.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from the_one.agent.core import SEARCH_TOOLS_SCHEMA
from the_one.tools.base import Tool, ToolRegistry

# Schemas to exclude from search_tools results.
# search_tools and search_mcps are infrastructure — they shouldn't surface
# in their own results. mcp__-prefixed names are MCP tools (L3 territory).
_EXCLUDED_NAMES: frozenset[str] = frozenset({"search_tools", "search_mcps"})
_MCP_PREFIX = "mcp__"


def _filter_candidates(
    schemas: list[dict[str, Any]],
    query: str,
) -> list[dict[str, Any]]:
    """Pure function: filter schemas by the search-tools rules + substring query.
    
    Extracted for unit-testability without registry/agent state. Returns
    schemas whose name passes the exclusion rules AND whose concatenated
    name+description contains the lowercased query as substring. Empty
    query returns all schemas that pass the exclusion rules.
    """
    out: list[dict[str, Any]] = []
    q = query.lower()
    for s in schemas:
        name = s.get("name", "")
        if name in _EXCLUDED_NAMES:
            continue
        if name.startswith(_MCP_PREFIX):
            continue
        if q:
            haystack = f"{name} {s.get('description', '')}".lower()
            if q not in haystack:
                continue
        out.append(s)
    return out


class SearchTools(Tool):
    """F10 L2: real search_tools implementation."""

    # CLASS attributes — required by ToolRegistry.register at base.py:118-119.
    name = "search_tools"
    description = SEARCH_TOOLS_SCHEMA["description"]
    parameters = SEARCH_TOOLS_SCHEMA["parameters"]

    def __init__(
        self,
        on_match: Callable[[list[dict[str, Any]]], None],
        registry: ToolRegistry,
        agent_name: str | None = None,
    ) -> None:
        super().__init__(agent_name=agent_name)
        self._on_match = on_match
        self._registry = registry

    async def execute(self, query: str = "") -> str:  # type: ignore[override]
        all_schemas = self._registry.all_schemas()
        matches = _filter_candidates(all_schemas, query)
        if not matches:
            # Use precise format for the no-match string so tests can ==-assert it.
            return f"No tools found matching {query!r}."
        self._on_match(matches)
        names = ", ".join(m["name"] for m in matches)
        # Empty-query path omits the "matching ''" clause for readability;
        # non-empty path includes the query for clarity. Both paths are pinned
        # in tests via ==-assertion against the exact string.
        if query:
            return f"Found {len(matches)} tools matching {query!r}: {names}."
        return f"Found {len(matches)} tools: {names}."
```

### Factory wiring change

```python
# the_one/agent/factory.py

# Line 12 — drop SearchToolsStub from factory import (no longer used in production wiring;
# tests that need it import it directly from _search_stubs.py per test_agent_visibility_filter.py:29-36):
from the_one.tools._search_stubs import SearchMcpsStub
from the_one.tools._search_tools import SearchTools

# Around line 175 — replace SearchToolsStub registration:
registry.register(SearchTools(on_match=_on_search_match, registry=registry, agent_name=name))
registry.register(SearchMcpsStub(on_match=_on_search_match, agent_name=name))
```

**Note on registry self-reference**: `SearchTools` receives the SAME registry it's being registered into. This works because the registry is a mutable container — by the time `SearchTools.execute()` is called at runtime, every other tool has been registered. Built-in tool registration at lines 178-181 runs AFTER the search-tools registration; MCP tool registration at lines 193-194 runs even later. By the time the agent's first user message triggers a search call, the registry holds the full candidate set.

### `_search_stubs.py` module docstring update

```python
"""F10 L1: CANNED-DATA stub tools for search_tools and search_mcps.

POST-L2 STATUS: SearchToolsStub is now test-only (used by L1's visibility-
filter contract tests in tests/test_agent_visibility_filter.py). Production
wiring uses SearchTools from _search_tools.py instead.

SearchMcpsStub is still used in production wiring at factory.py:176 until
L3 lands the real implementation.
"""
```

### Test design notes

- **Real-registry test fixture**: construct a real `ToolRegistry` populated by `BuiltinToolProvider().get_tools({}, {}, agent_name="test")` — this matches what `factory.py:178-181` produces under default conditions. Alternative: use a synthetic registry with hand-picked schemas for filter-rule isolation. Use the real registry for end-to-end tests and the synthetic for filter-rule tests.
- **Per-agent filter test (factory integration)**: `AgentFactory.create(name)` loads `AgentConfig` from the store via `_load_config`. To test `enabled_tools` filtering without standing up a real DB, either: (a) inject a mock `AgentConfigStore` into `AgentFactory(store=mock_store)`, where `mock_store.get(name)` returns a hand-constructed `AgentConfig(name="test", enabled_tools=["read_file", "write_file"], provider_config_id="...")`; or (b) bypass the factory entirely by manually constructing the `ToolRegistry` + `SearchTools` and asserting filter behavior. Use (a) for `test_real_impl_in_factory_wiring` + `test_real_impl_per_agent_filter_applied_at_registry_level` to actually exercise the factory path; use (b) for pure filter-rule tests. **Implementer**: check `tests/test_factory.py` for an existing mock-store fixture (L1 added test_factory.py modifications, so similar patterns are likely already present).
- **`_filter_candidates` pure-function tests**: feed synthetic schema lists `[{"name": "alpha", "description": "alpha tool"}, {"name": "mcp__foo__bar", ...}, {"name": "search_tools", ...}]` and assert exclusion behavior cleanly.
- **Idempotency test**: similar to L1's `test_search_stub_idempotent` but for the real impl. The `on_match` callback's `loaded_tool_names` dedup already handles this; just verify by inspection.
- **`test_real_impl_in_factory_wiring`**: assert `isinstance(registry.get("search_tools"), SearchTools)` and NOT `isinstance(..., SearchToolsStub)`. The L1 stub assertion was `isinstance(..., SearchToolsStub)`; this is the L2 counterpart.

## Edge Cases

- **Empty registry**: registry has only the two search tools (factory edge case if all built-ins are disabled per-agent). `search_tools("")` returns "No tools found" (both search tools excluded by name).
- **Query with special characters**: substring match is plain string `in`-test, NOT regex. Special chars in query are matched literally (e.g., `"read_"` matches `read_file`). No escaping needed.
- **Query with leading/trailing whitespace**: NOT stripped — passed as-is to the lowercased substring match. Empty-after-strip queries are NOT treated as empty; they'd never match. This is a design choice for predictability (the LLM should send clean queries; not the search tool's job to repair).
- **Tool with missing description**: `s.get("description", "")` falls back to empty string; match haystack is just the name then.
- **Tool with no `name` key**: `s.get("name", "")` falls back to empty string; the name is in `_EXCLUDED_NAMES` check uses set membership (empty string isn't in the set, so it passes); won't be excluded by mcp__ prefix unless empty starts with `mcp__` (it doesn't). Unlikely path; if it happens, the schema is malformed and the result is undefined. Not L2's responsibility to repair.
- **`on_match` callback raises**: not handled by `SearchTools.execute`; propagates to the caller (Agent's `_execute_tool`), which catches generic exceptions via `agent/core.py:275 — except Exception as e:` and returns `ToolResult(is_error=True, content="[error] Tool execution failed: ...")`. Same as any other tool failure. NOT a special case.
- **Repeated calls with same query**: idempotency via `on_match` callback's name-set dedup. First call adds N schemas; second call adds 0 (all already in loaded_tool_names). Verify with `test_idempotent_on_repeated_calls`.
- **Concurrent calls** (parallel tool calls in same iteration): `_dispatch_tool_calls` in `core.py:159` iterates sequentially; concurrent search calls don't happen in practice. Even if they did, the `_on_search_match` closure uses simple list/set mutation which is atomic in CPython under the GIL for small operations. Not a concern at L2 scope.

## Files Affected

- `the_one/tools/_search_tools.py` — NEW (~150 LOC)
- `the_one/agent/factory.py` — wiring change (~5 LOC net: 1 line import addition, 1 line registration swap, 3 lines comment context)
- `the_one/tools/_search_stubs.py` — docstring update only (~5 LOC)
- `tests/test_search_tools.py` — NEW (~250 LOC, 8-12 tests)

**Total**: ~410 LOC. Within F10 sizing.

## Citation Audit

Citations verified against current code at L2 design time (2026-05-10):

- `the_one/agent/core.py:33 — SEARCH_TOOLS_SCHEMA = {` ✓ verified (L1-landed)
- `the_one/agent/core.py:56 — SEARCH_MCPS_SCHEMA = {` ✓ verified (L1-landed)
- `the_one/agent/core.py:128 — return [SEARCH_TOOLS_SCHEMA, SEARCH_MCPS_SCHEMA, CONTINUE_SCHEMA] + self._loaded_schemas` ✓ verified
- `the_one/agent/factory.py:12 — from the_one.tools._search_stubs import SearchMcpsStub, SearchToolsStub` ✓ verified
- `the_one/agent/factory.py:155-176 — wiring sequence (containers + closure + stub registrations)` ✓ verified
- `the_one/agent/factory.py:178-181 — built-in tool registry filter (for provider in self.tool_providers: ... if tool.name not in disabled_names and config.is_tool_enabled(tool.name): registry.register(tool))` ✓ verified
- `the_one/agent/factory.py:193-194 — MCP tool registry filter (same per-agent guard)` ✓ verified
- `the_one/tools/base.py:114-131 — class ToolRegistry with register/get/all_schemas/tool_names` ✓ verified
- `the_one/tools/_search_stubs.py:59-92 — SearchToolsStub class` ✓ verified (L1-landed)
- `the_one/tools/_search_stubs.py:100-133 — SearchMcpsStub class` ✓ verified (L1-landed; L3 territory)
- `the_one/tools/shell.py:19-20 — class ShellTool(Tool): name = "shell"` ✓ verified
- `the_one/tools/filesystem.py:339-340 — class ReadFileTool(Tool): name = "read_file"` ✓ verified
- `the_one/tools/sessions.py:78-79 — class ShellSessionStartTool(Tool): name = "shell_session_start"` ✓ verified
- `tests/test_agent_visibility_filter.py:30-31 — imports SearchMcpsStub/SearchToolsStub` ✓ verified (L1 tests retain stub usage)

**Audit summary**: 14 citations verified against current code at leg design time. 14 OK, 0 drifted, 0 gone, 0 unverifiable.

---

## Post-Completion Checklist

**Complete ALL steps before marking leg `landed`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (file-scoped + L1 regression + full unit suite vs L1 post-landing baseline of 1462 pass)
- [ ] Update flight-log.md with leg progress entry under "Leg Progress" section, including: implementation notes, anomalies surfaced (if any), test count delta vs L1 baseline, LOC count by file
- [ ] Set this leg's status to `landed` (in this file's header) — NOT `completed` (completion happens at Phase 2d after flight-batched review + commit)
- [ ] Check off this leg in flight.md Legs list
- [ ] **Do NOT commit** — per agentic-workflow Phase 2d, commits are deferred until after the last autonomous leg
- [ ] **Do NOT signal `[HANDOFF:review-needed]`** — that signal is reserved for Phase 2d (flight-level review), not per-leg
