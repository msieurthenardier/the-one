# Leg: 03-search-mcps-implementation

**Status**: completed
**Flight**: [Lazy tool discovery](../flight.md)

## Objective

Replace L1's `SearchMcpsStub` (canned-data) with `SearchMcps` — a real implementation that enables an agent to discover MCP tools attached to it via substring search across source names + synthetic descriptions + per-tool name+description. Matched MCP tool schemas are auto-loaded into `_loaded_schemas` via the shared `on_match` callback. Per-source `mcp_overrides` (`enabled_tools` / `disabled_tools`) are respected via a SHARED helper that L3 ALSO refactors out of `_tool_provider.py:264-284` so `MCPToolProvider.get_tools_for_agent` and `SearchMcps` share one filter implementation. Synthetic descriptions are built from each source's cached tool short-names, truncated to ~200 chars. By leg close, an agent calling `search_mcps("cloudflare")` against a Cloudflare API source sees the relevant `mcp__cloudflare_api__*` tools appear in next iteration's `tools=` array.

**Path A confirmed at L3 design time**: per F10 §10, the candidate-set construction question is resolved as **Path A** (existing eager `MCPToolProvider.get_tools_for_agent` continues to do `acquire`+`list_tools` at agent build time). `MCPClientTool.__init__` at `_tool.py:94-133` is feasible for Path B (cache-only hydration; constructor requires only `mcp_tool: MCPTool` + `effective_source: MCPSource`, NOT a live client), but the additional refactor surface (factory swap + Path B method on `MCPToolProvider` + no-cache fallback semantics) would inflate L3 ~~200-250 LOC sizing to ~600+. Path A keeps factory's MCP integration UNCHANGED; L3 only adds `SearchMcps` real impl + shared filter helper. F10's primary user-facing wins (lazy schema-visibility, mid-session attach pickup at next session start) work with either Path A or B; Path B's server-side acquire-on-demand optimization is deferred to a follow-up flight if measurement shows the eager acquire cost is material.

## Context

- **F10 §1 (auto-load)** — `search_mcps` mutates `_loaded_schemas` as a side effect of being called. L3 lands the real implementation; semantics unchanged from L1's stub.
- **F10 §3 (loaded set = visibility filter, not registry membership)** — the `ToolRegistry` holds the FULL candidate set including `MCPClientTool` instances for every attached + filtered MCP tool (registered eagerly via `factory.py:189-195` calling `MCPToolProvider.get_tools_for_agent`). `SearchMcps` queries the registry filtered to `mcp__`-prefixed names + adds matched schemas to visibility. Dispatch via `self.tools.get("mcp__source__tool")` always finds the `MCPClientTool` instance regardless of loaded-set state.
- **F10 §4 (substring match)** — same as L2's pattern: lowercase query; lowercase candidate text; check `in`. No embeddings, no scoring.
- **F10 §5 (synthetic source descriptions)** — `SearchMcps` builds source-level descriptions from `_cache.tools` short-names (e.g. `"cloudflare_api: list_zones, get_zone, list_dns_records, ... (37 tools)"`) truncated to ~200 chars. Source name + synthetic description form the source-level search haystack; matching a source returns ALL of its tools (subject to `mcp_overrides` filter). Per-tool matching against name+description (case-insensitive substring) is the tool-level search haystack.
- **F10 §10 (Path A confirmed)** — see Objective above. `factory.create`'s MCP integration at `factory.py:189-195` is UNCHANGED.
- **L1+L2 outcome carry-forward**:
  - `SearchToolsStub` is now test-only fixture (post-L2); `SearchMcpsStub` is still live in production at `factory.py:177`. L3 replaces the latter.
  - Agent has `_loaded_schemas: list[dict]` and `_loaded_tool_names: set[str]` instance state (L1).
  - `_compute_visible_schemas()` returns `[search_tools, search_mcps, continue] + self._loaded_schemas` per iteration (L1).
  - `search_tools` (L2) iterates registry, filters out search tools + `mcp__` prefix, substring-matches name+description, mutates loaded set. L3 mirrors the iteration pattern but inverts the prefix filter.
  - 12 visibility-filter contract tests in `tests/test_agent_visibility_filter.py` continue to pass (L1+L2 invariant); 12 search-tools tests in `tests/test_search_tools.py` continue to pass (L2 invariant).
- **`mcp_overrides` filter logic** at `_tool_provider.py:264-284` (the model-validate dance for `StdioMCPOverride` / `StreamableHttpMCPOverride` + `enabled_tools`/`disabled_tools` filter) needs to be EXTRACTED into a shared helper BEFORE forking it into `search_mcps`. Both `MCPToolProvider.get_tools_for_agent` and `SearchMcps` will call the helper. Without the extraction, L3 would duplicate the filter logic and create a long-term maintenance hazard.
- **No-cache fallback**: if a source is registered but its `_cache.tools` is empty or absent (operator never clicked Refresh on source-edit page), `search_mcps` skips it (no candidates added) and logs a WARNING (`"MCP source %r has no cached tools; refresh on source-edit page to enable discovery"`). The source appears in the search corpus only by name; matching it returns the warning text, not a tool list. Operator-felt UX: clean error path, not silent omission.
- **Why `SearchMcpsStub` is replaced (vs. kept as test fixture like SearchToolsStub)**: L1's 12 visibility-filter tests use BOTH stubs interchangeably (via the shared `on_match` callback path). When L3 lands, the production wiring uses `SearchMcps` (real); the L1 tests continue to use `SearchMcpsStub` directly (just like L2 left `SearchToolsStub` alone). The stub class stays in `_search_stubs.py` as test-only post-L3, mirroring L2's pattern.

## Inputs

What exists before this leg runs:

- L2 landed: 1474 pass (1462 baseline + 12 L2 tests).
- `the_one/agent/factory.py:12 — from the_one.tools._search_stubs import SearchMcpsStub` + `:13 — from the_one.tools._search_tools import SearchTools` (post-L2 import structure).
- `the_one/agent/factory.py:176 — registry.register(SearchTools(on_match=_on_search_match, registry=registry, agent_name=name))` (L2 wiring).
- `the_one/agent/factory.py:177 — registry.register(SearchMcpsStub(on_match=_on_search_match, agent_name=name))` (L3 replaces this).
- `the_one/agent/factory.py:188-194 — MCP tool integration via mcp_provider.get_tools_for_agent` (UNCHANGED by L3).
- `the_one/mcp/_tool_provider.py:175 — class MCPToolProvider` + `:183 — async def get_tools_for_agent` + `:264-284 — per-source enabled_tools/disabled_tools filter (the block to extract)`.
- `the_one/mcp/_tool.py:64 — class MCPClientTool` + `:94-133 — __init__ taking (mcp_tool, source_id, source_name, agent_name, effective_source)`.
- `the_one/mcp/types — MCPTool` dataclass (`name`, `description`, `input_schema` — matches `_cache.tools` payload shape).
- `the_one/db/models — MCPSource` (`name`, `type`, `config`, `secrets`; no `description` field).
- `the_one/mcp/_overrides — StdioMCPOverride` + `StreamableHttpMCPOverride` (with `.enabled_tools` and `.disabled_tools` properties).
- `the_one/tools/_search_stubs.py:100-133 — SearchMcpsStub` (L3 replaces in production; keeps in file as test-only fixture).
- `the_one/tools/_search_tools.py — SearchTools` (L2's real impl; reference for L3's structural pattern).
- 12 tests in `tests/test_agent_visibility_filter.py` (L1) + 12 in `tests/test_search_tools.py` (L2).

## Outputs

What exists after this leg completes:

- **MODIFIED**: `the_one/mcp/_tool_provider.py` (~40 LOC net):
  - Add module-level `filter_mcp_tools_by_override(mcp_tools, source, override_payload) -> list[MCPTool]` helper. Encapsulates `StdioMCPOverride.model_validate` / `StreamableHttpMCPOverride.model_validate` dispatch by `source.type` + `enabled_tools` / `disabled_tools` filter logic.
  - Refactor `get_tools_for_agent` (lines 264-284) to call the helper instead of inlining the filter. Behavior preserved exactly.
- **NEW**: `the_one/tools/_search_mcps.py` (~200 LOC):
  - `SearchMcps(Tool)` real implementation. Class attributes `name = "search_mcps"`, `description` + `parameters` imported from `SEARCH_MCPS_SCHEMA` at `agent.core` (single source of truth).
  - Constructor: `__init__(self, on_match, registry, source_index, agent_name=None)`. Calls `super().__init__(agent_name=agent_name)`. Stores `self._on_match`, `self._registry`, `self._source_index`, `self._agent_name`.
  - Source index shape: `dict[str, dict]` where each entry is `{source_name: {"synthetic_description": str, "tool_names_prefixed": list[str]}}`. Built by factory at agent-build time from each attached source's `_cache.tools` (filtered through `mcp_overrides`).
  - `execute(query: str = "") -> str`: source-level + per-tool matching against the registry's `mcp__`-prefixed schemas. Adds matched schemas to `_loaded_schemas` via `self._on_match`. Returns formatted result with source-grouped breakdown.
  - Helper: `_filter_mcp_candidates(schemas, source_index, query)` — pure function for testability. Returns the filtered list of matched schemas.
  - Helper: `_build_synthetic_description(source_name, tool_names, char_cap=200) -> str` — pure function for testability. Builds `"{source_name}: {comma-separated short names}, ... ({N} tools)"` and truncates to char_cap with ellipsis.
- **MODIFIED**: `the_one/agent/factory.py` (~20 LOC net):
  - At line 12 region: drop `SearchMcpsStub` from import (no longer used in production); add `from the_one.tools._search_mcps import SearchMcps`.
  - After the MCP tool registration loop (line 188-194), build the source index for `SearchMcps`. For each attached source: read `source.config._cache.tools`, apply `filter_mcp_tools_by_override` with the source's `mcp_overrides` payload, build synthetic description from the filtered tool short-names, store `{source.name: {"synthetic_description": ..., "tool_names_prefixed": [prefixed_name for each filtered tool]}}` in the index. Sources with empty `_cache.tools` are LOGGED with a warning and SKIPPED from the index (their tools are not registered either — since `get_tools_for_agent` does its own acquire which won't return any tools if the server is unreachable; the no-cache case is a separate operator-state issue).
  - At line 177 region: replace `SearchMcpsStub(on_match=_on_search_match, agent_name=name)` with `SearchMcps(on_match=_on_search_match, registry=registry, source_index=source_index, agent_name=name)`.
  - **Note on source index construction**: factory needs to load sources from DB (already done by `MCPToolProvider.get_tools_for_agent` internally at lines 211-220). Options: (a) refactor `get_tools_for_agent` to return `(tools, sources_list)` tuple — change public API; (b) factory loads sources independently via `MCPSourceRepository.get(source_id)` for each attached source — adds a small DB cost; (c) `MCPToolProvider` exposes the loaded sources via instance state after `get_tools_for_agent` returns. **Decision: use option (b)** with these properties: clean separation, ~5 LOC of extra DB calls (small overhead per agent build), simple to reason about, no public API churn. **Sequence**: build source_index FIRST (before MCP tool registration), then register `SearchMcps` with the populated index, THEN run the MCP tool registration loop (`get_tools_for_agent`) — this keeps `SearchMcps`'s constructor receiving a fully-populated index, avoiding placeholder + post-update patterns. **Consistency note**: a source whose `_cache.tools` is populated will appear in source_index, but if `get_tools_for_agent` later fails to `acquire` for that source, its tools won't land in the registry. Source-level matching against that source will return zero schemas (since `_filter_mcp_candidates` reads schemas from the registry, not the index). This is acceptable for L3's scope — document in the `_search_mcps.py` module docstring so future maintainers don't pursue a "why did source-match return nothing?" debug.
- **MODIFIED**: `the_one/tools/_search_stubs.py` (~5 LOC):
  - Update module docstring: `SearchMcpsStub` is now test-only (post-L3); production wiring uses `SearchMcps` from `_search_mcps.py`. `SearchToolsStub` continues to be test-only (post-L2).
- **NEW**: `tests/test_search_mcps.py` (~280 LOC, 10-13 tests):
  - `test_filter_mcp_tools_by_override_no_payload` — empty/None payload returns all tools unchanged.
  - `test_filter_mcp_tools_by_override_enabled_tools_whitelist` — payload with `enabled_tools=["foo"]` returns only `foo`.
  - `test_filter_mcp_tools_by_override_disabled_tools_subtract` — payload with `disabled_tools=["foo"]` excludes `foo`, returns rest.
  - `test_filter_mcp_tools_by_override_stdio_vs_http` — same payload semantics on both transports.
  - `test_build_synthetic_description_basic` — 3-tool source builds `"foo: a, b, c (3 tools)"`.
  - `test_build_synthetic_description_truncation` — 50-tool source builds description ≤200 chars, ends with ellipsis indicator + `(50 tools)`.
  - `test_build_synthetic_description_empty_tools` — 0-tool source builds `"foo: (no cached tools)"` or similar (verify the no-cache path).
  - `test_search_mcps_empty_query_returns_all` — empty query returns all `mcp__`-prefixed schemas in registry; mutates loaded set.
  - `test_search_mcps_query_matches_source_name` — query matches a source name → returns ALL of that source's tools.
  - `test_search_mcps_query_matches_per_tool` — query matches a per-tool name → returns just that tool.
  - `test_search_mcps_query_matches_synthetic_description` — query word that appears in the synthetic description (e.g., one of the constituent tool short-names) returns the source's tools.
  - `test_search_mcps_no_match_returns_helpful_text` — query `"xyzzy"` returns `"No MCP tools found matching 'xyzzy'."` (==-assert exactly); does NOT mutate `_loaded_schemas`.
  - `test_search_mcps_excludes_non_mcp_tools` — registry contains `read_file` (built-in) and `mcp__foo__bar`; query `"read"` does NOT return `read_file` (filtered by `mcp__` prefix requirement).
  - `test_real_impl_in_factory_wiring` — `AgentFactory.create(...)` with mock store; assert registry has `SearchMcps` instance under name `"search_mcps"` (NOT `SearchMcpsStub`).
  - `test_search_mcps_no_cache_source_logged_and_skipped` — register a mock MCP source with empty `_cache.tools`; verify warning logged; verify it's NOT in source_index; verify search doesn't return its tools.

## Acceptance Criteria

- [ ] `the_one/mcp/_tool_provider.py` has new module-level `filter_mcp_tools_by_override(mcp_tools, source, override_payload)` helper function. Returns `list[MCPTool]`. Idempotent on empty/None override. Handles `stdio` + `streamable-http` transports correctly.
- [ ] `MCPToolProvider.get_tools_for_agent` (lines 264-284) refactored to call `filter_mcp_tools_by_override` — inline block replaced. Behavior preserved exactly; existing tests for `get_tools_for_agent` all pass unmodified.
- [ ] `the_one/tools/_search_mcps.py` exists with `SearchMcps(Tool)` class. Class attribute `name = "search_mcps"`. Constructor calls `super().__init__(agent_name=agent_name)`. Stores `on_match`, `registry`, `source_index`, `agent_name`.
- [ ] `SearchMcps.description` + `SearchMcps.parameters` are class attributes mirroring `SEARCH_MCPS_SCHEMA` from `agent.core` (imported, not duplicated).
- [ ] `SearchMcps.execute("")` returns ALL `mcp__`-prefixed schemas in the registry; mutates `_loaded_schemas` via `on_match`. Result text includes source-grouped breakdown showing how many tools per source.
- [ ] `SearchMcps.execute(query)` for non-empty query: substring-matches case-insensitively against (source_name + synthetic_description) for source-level matching AND per-tool (name + description) for tool-level matching. Source-level matches return ALL of that source's tools. Tool-level matches return just the matched tools. Union the two; dedup by tool name. Mutate `_loaded_schemas` via `on_match` (which dedupes via `loaded_tool_names`).
- [ ] No-match path: return `"No MCP tools found matching {query!r}."` exactly (==-assertable). Do NOT mutate `_loaded_schemas`.
- [ ] `SearchMcps.execute` skips non-`mcp__`-prefixed schemas in the registry — built-in tools and search tools never appear in `SearchMcps` results.
- [ ] `_build_synthetic_description(source_name, tool_names, char_cap=200)` is a pure-function helper. 3-tool source → `"foo: a, b, c (3 tools)"`. 50-tool source → ≤200 chars, ending with ellipsis + `(50 tools)`. 0-tool source → `"foo: (no cached tools)"`.
- [ ] Factory at `factory.py` post-MCP-tool-registration: builds a source index for `SearchMcps` by reading each attached source's `_cache.tools`, applying `filter_mcp_tools_by_override` (via `mcp_overrides` payload), building synthetic descriptions. Skips sources with empty `_cache.tools` (logs WARNING).
- [ ] Factory replaces `SearchMcpsStub` registration at line 177 with `SearchMcps(...)` registration passing `on_match`, `registry`, `source_index`, `agent_name`.
- [ ] `_search_stubs.py` module docstring updated to note `SearchMcpsStub` is now test-only (post-L3).
- [ ] All L1 tests in `tests/test_agent_visibility_filter.py` PASS UNMODIFIED.
- [ ] All L2 tests in `tests/test_search_tools.py` PASS UNMODIFIED.
- [ ] All 10-13 new tests in `tests/test_search_mcps.py` pass.
- [ ] All existing tests in `tests/test_mcp_tool_provider.py` (or analogous file testing `get_tools_for_agent`) PASS UNMODIFIED — the filter helper extraction is a pure refactor.
- [ ] Full unit suite passes: expected post-L3 count is `1474 + N` where N = L3 test count (10-13).
- [ ] No regression vs F8 browser baseline.

## Verification Steps

- Run unit tests scoped to L3's surface: `docker exec the-one pytest tests/test_search_mcps.py -x --timeout 30 -v`. Expect 10-13 passes.
- Run L1+L2 regression: `docker exec the-one pytest tests/test_agent_visibility_filter.py tests/test_search_tools.py -x --timeout 30 -v`. Expect 24 passes.
- Run MCPToolProvider tests: `docker exec the-one pytest tests/test_mcp_tool_provider.py tests/test_factory.py -x --timeout 30 -v` (find the actual file name via `find tests -name "*tool_provider*"` if `test_mcp_tool_provider.py` doesn't exist). Expect green — the filter helper extraction is a refactor; no behavior change.
- Run full unit suite at leg-end: `docker exec the-one pytest -q --timeout 120 --ignore=tests/test_mcp_pool.py`. Expect `1474 + N` pass.
- Manual sanity (optional): in Python shell, construct a fake source index `{"foo": {"synthetic_description": "foo: a, b, c (3 tools)", "tool_names_prefixed": ["mcp__foo__a", "mcp__foo__b", "mcp__foo__c"]}}`; construct a `SearchMcps` with that index and a registry containing three `MCPClientTool`-like schemas; call `await search_mcps.execute("a")`; verify result mentions `mcp__foo__a`.

## Implementation Guidance

### Shared filter helper extraction (FIRST task per F10 design-review)

Move the block from `_tool_provider.py:264-284` into a new module-level function:

```python
# the_one/mcp/_tool_provider.py — new helper, module-level

def filter_mcp_tools_by_override(
    mcp_tools: list[MCPTool],
    source: MCPSource,
    override_payload: dict[str, Any] | None,
) -> list[MCPTool]:
    """Apply per-source enabled_tools / disabled_tools filter from override.

    Returns a NEW filtered list. Idempotent on empty/None override
    (returns input unchanged). Handles stdio and streamable-http
    transports via the appropriate override model. Unknown source types
    fall through to returning input unchanged (logged at the call site
    if needed).

    NOTE: model_validate is used directly (NOT resolve()) because the
    resolver raises ValueError on untagged fields (resolver.py:244-248).
    """
    if not override_payload:
        return mcp_tools

    override_model: StdioMCPOverride | StreamableHttpMCPOverride | None
    if source.type == "stdio":
        override_model = StdioMCPOverride.model_validate(override_payload)
    elif source.type == "streamable-http":
        override_model = StreamableHttpMCPOverride.model_validate(override_payload)
    else:
        return mcp_tools

    enabled = override_model.enabled_tools
    disabled = override_model.disabled_tools or []
    out = mcp_tools
    if enabled is not None:
        out = [mt for mt in out if mt.name in enabled]
    if disabled:
        out = [mt for mt in out if mt.name not in disabled]
    return out
```

Then in `MCPToolProvider.get_tools_for_agent` (lines 264-284), replace the inline block with a single call:

```python
            # F10 L3: shared filter helper (same logic as before; extracted
            # for reuse by SearchMcps).
            mcp_tools = filter_mcp_tools_by_override(
                mcp_tools, source, override_payload
            )
```

### Source index construction in factory

```python
# the_one/agent/factory.py — after the existing MCP tool registration block

# F10 L3: build source index for SearchMcps. For each attached source,
# read _cache.tools (populated by source-edit page Refresh), apply
# mcp_overrides filter via shared helper, build synthetic description
# from filtered tool short-names. Sources with empty _cache.tools are
# logged + skipped (operator state issue, not a code defect).
source_index: dict[str, dict[str, Any]] = {}
if config.mcp_source_ids and self.mcp_provider is not None:
    conn = await get_connection()
    encryptor = get_encryptor(settings.data_dir)
    repo = MCPSourceRepository(conn, encryptor)
    for source_id in config.mcp_source_ids:
        try:
            source = await repo.get(source_id)
        except KeyError:
            # Already warned by MCPToolProvider.get_tools_for_agent;
            # skip silently here.
            continue
        cached_tools_payload = source.config.get("_cache", {}).get("tools") or []
        if not cached_tools_payload:
            logger.warning(
                "agent %r: MCP source %r has no cached tools; "
                "refresh on source-edit page to enable discovery via search_mcps",
                name,
                source.name,
            )
            continue
        # Reconstruct MCPTool objects from cached payload for the filter helper.
        # MCPTool is a frozen dataclass with FIVE required fields per
        # the_one/mcp/types.py: name, description, input_schema, output_schema,
        # annotations. The _cache.tools payload (per api.py:1014-1020) only
        # stores the first three; pass None for the remaining two so the
        # dataclass construction doesn't TypeError.
        cached_mcp_tools = [
            MCPTool(
                name=t["name"],
                description=t.get("description", ""),
                input_schema=t.get("input_schema", {"type": "object", "properties": {}}),
                output_schema=None,
                annotations=None,
            )
            for t in cached_tools_payload
        ]
        override_payload = (config.mcp_overrides or {}).get(source.name)
        filtered = filter_mcp_tools_by_override(
            cached_mcp_tools, source, override_payload
        )
        prefixed_names = [
            f"mcp__{_normalize_source_name(source.name)}__{mt.name}"
            for mt in filtered
        ]
        synthetic_description = _build_synthetic_description(
            source.name,
            [mt.name for mt in filtered],
            char_cap=200,
        )
        source_index[source.name] = {
            "synthetic_description": synthetic_description,
            "tool_names_prefixed": prefixed_names,
        }
```

Add the `MCPTool` + `MCPSourceRepository` + helper imports as needed at the top of `factory.py`.

### `SearchMcps` shape

```python
# the_one/tools/_search_mcps.py

"""F10 L3: real implementation of search_mcps.

Replaces SearchMcpsStub at production wiring. Searches across attached
MCP sources (by source name + synthetic description) AND per-tool
(name + description). Matched MCP tool schemas are added to the
agent's _loaded_schemas via on_match.

Per-source enabled_tools/disabled_tools filtering is ALREADY APPLIED at
agent build time by MCPToolProvider.get_tools_for_agent (via shared
helper filter_mcp_tools_by_override). SearchMcps relies on the registry
+ source_index already reflecting that filter; it does NOT re-apply.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from the_one.agent.core import SEARCH_MCPS_SCHEMA
from the_one.tools.base import Tool, ToolRegistry

_MCP_PREFIX = "mcp__"
_DEFAULT_DESCRIPTION_CAP = 200


def _build_synthetic_description(
    source_name: str,
    tool_short_names: list[str],
    char_cap: int = _DEFAULT_DESCRIPTION_CAP,
) -> str:
    """Build a synthetic source-level description from tool short names.

    Two-pass: first determine whether the full list fits within char_cap;
    if yes, emit complete; if no, accumulate as many names as possible
    leaving room for the "..." truncation indicator. Single-segment guard
    `> available` (NOT `> available - 3`) — the `- 3` form drops the last
    name even when it would have fit exactly, producing a spurious "..."
    at the boundary case.
    """
    if not tool_short_names:
        return f"{source_name}: (no cached tools)"
    count = len(tool_short_names)
    suffix = f" ({count} tools)"
    prefix = f"{source_name}: "
    available = char_cap - len(prefix) - len(suffix)

    # First, compute the full body to check if it fits without truncation.
    full_body = ", ".join(tool_short_names)
    if len(full_body) <= available:
        return f"{prefix}{full_body}{suffix}"

    # Truncation path: leave room for "..." (3 chars). Build incrementally.
    truncation_marker = "..."
    truncation_budget = available - len(truncation_marker)
    body = ""
    for i, name in enumerate(tool_short_names):
        segment = name if i == 0 else f", {name}"
        if len(body) + len(segment) > truncation_budget:
            break
        body += segment
    body += truncation_marker
    return f"{prefix}{body}{suffix}"


def _filter_mcp_candidates(
    schemas: list[dict[str, Any]],
    source_index: dict[str, dict[str, Any]],
    query: str,
) -> list[dict[str, Any]]:
    """Pure function: filter mcp__-prefixed schemas by query.

    Empty query returns all mcp__-prefixed schemas. Non-empty query
    matches against source-level (source name + synthetic_description)
    AND per-tool (name + description). Source-level matches return all
    of that source's tools; per-tool matches return just the matched
    tools. Union + dedup by name.
    """
    q = query.lower()
    mcp_schemas = [s for s in schemas if s.get("name", "").startswith(_MCP_PREFIX)]

    if not q:
        return mcp_schemas

    # Source-level matching: include all tools from sources whose name or
    # synthetic description contains the query substring.
    source_matches: set[str] = set()  # prefixed tool names from matching sources
    for source_name, info in source_index.items():
        haystack = f"{source_name} {info.get('synthetic_description', '')}".lower()
        if q in haystack:
            source_matches.update(info.get("tool_names_prefixed", []))

    # Per-tool matching: substring match against name + description.
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for s in mcp_schemas:
        name = s.get("name", "")
        if name in seen:
            continue
        if name in source_matches:
            out.append(s)
            seen.add(name)
            continue
        haystack = f"{name} {s.get('description', '')}".lower()
        if q in haystack:
            out.append(s)
            seen.add(name)
    return out


class SearchMcps(Tool):
    """F10 L3: real search_mcps implementation."""

    name = "search_mcps"
    description = SEARCH_MCPS_SCHEMA["description"]
    parameters = SEARCH_MCPS_SCHEMA["parameters"]

    def __init__(
        self,
        on_match: Callable[[list[dict[str, Any]]], None],
        registry: ToolRegistry,
        source_index: dict[str, dict[str, Any]],
        agent_name: str | None = None,
    ) -> None:
        # super().__init__ sets self._agent_name via Tool's base __init__.
        # Do NOT re-assign self._agent_name = agent_name here — that would
        # duplicate base initialization and drift from L2's SearchTools pattern.
        super().__init__(agent_name=agent_name)
        self._on_match = on_match
        self._registry = registry
        self._source_index = source_index

    async def execute(self, query: str = "") -> str:  # type: ignore[override]
        all_schemas = self._registry.all_schemas()
        mcp_in_registry = [s for s in all_schemas if s.get("name", "").startswith(_MCP_PREFIX)]
        # Empty-registry-no-attached-MCPs UX: distinguish from "search returned 0".
        if not mcp_in_registry and not self._source_index:
            return "No MCP sources are attached to this agent."
        matches = _filter_mcp_candidates(all_schemas, self._source_index, query)
        if not matches:
            return f"No MCP tools found matching {query!r}."
        self._on_match(matches)
        # Format result: source-grouped breakdown.
        by_source: dict[str, list[str]] = {}
        for s in matches:
            # Parse "mcp__source__tool" → source = middle segment
            parts = s["name"].split("__", 2)
            src = parts[1] if len(parts) >= 3 else "unknown"
            by_source.setdefault(src, []).append(s["name"])
        groups = []
        for src, names in by_source.items():
            groups.append(f"{src}: {', '.join(names)}")
        if query:
            return f"Found {len(matches)} MCP tools matching {query!r}: " + "; ".join(groups) + "."
        return f"Found {len(matches)} MCP tools: " + "; ".join(groups) + "."
```

### Factory wiring change

```python
# the_one/agent/factory.py — imports

from the_one.tools._search_stubs import SearchMcpsStub  # REMOVE this line
from the_one.tools._search_mcps import SearchMcps      # ADD this line
from the_one.mcp._tool_provider import filter_mcp_tools_by_override  # already imported by _tool_provider users
from the_one.mcp._tool import _normalize_source_name   # if needed for prefix construction
from the_one.mcp.types import MCPTool                   # for cache hydration
# (other imports as needed)
```

```python
# the_one/agent/factory.py — registration around line 176-177

registry.register(SearchTools(on_match=_on_search_match, registry=registry, agent_name=name))
# F10 L3: source_index built later (after MCP tool registration); defer
# SearchMcps registration until then. Or: register a placeholder SearchMcps
# with empty source_index, then update its index after MCP loop. The
# placeholder approach is cleaner — no two-phase Tool registration.

# Actually: build source_index BEFORE MCP loop, register SearchMcps with it,
# then run the MCP loop. The MCP loop's tools (built via get_tools_for_agent)
# are dispatched by the registry; SearchMcps reads the registry at execute
# time, so the order doesn't matter for dispatch — but the source_index
# must be populated when SearchMcps.execute runs. Build it from a separate
# DB load OR refactor get_tools_for_agent to expose the loaded sources.

# Recommended sequence:
# 1. Build source_index (separate DB load — see Outputs section option (b))
# 2. Register SearchMcps with the populated index
# 3. Run MCP tool registration loop (existing logic)
```

### Test scaffolding notes

- **Filter helper tests**: instantiate `MCPSource(type="stdio", ...)` / `MCPSource(type="streamable-http", ...)` via Pydantic constructor; pass synthetic `mcp_tools = [MCPTool(name=..., description=..., input_schema=...)]` lists; assert filter behavior.
- **Synthetic description tests**: pure function — pass `(source_name, tool_short_names_list, char_cap)`; assert exact string output. For truncation, use 50-tool list with predictable names so length math is verifiable.
- **`SearchMcps.execute` tests**: build a synthetic `ToolRegistry` with mock `MCPClientTool` instances (or use unittest.mock.Mock to construct objects with `.name`, `.description`, `.parameters`, `.to_schema()`); build a fake source_index dict; call `execute()`; verify result format + `_loaded_schemas` mutation.
- **Factory integration tests** (`test_real_impl_in_factory_wiring`, `test_search_mcps_no_cache_source_logged_and_skipped`): use mock `AgentConfigStore` injection (same pattern as L2's factory tests in `test_search_tools.py`) AND mock `MCPSourceRepository.get` to return controlled source objects with controlled `_cache.tools` payloads.

## Edge Cases

- **Source with `_cache.tools` but `mcp_overrides` disables ALL its tools**: `filter_mcp_tools_by_override` returns empty list → synthetic description is `"foo: (no cached tools)"` (since the filter returned empty, looks like no cache from the description builder's POV). The source still appears in source_index but with empty `tool_names_prefixed`. Search returns no tools for it. This is correct behavior — the operator explicitly denied all tools.
- **Source name with special characters in the prefix**: `_normalize_source_name` (from `_tool.py:54-61`) normalizes non-alphanumeric chars to underscore. The synthetic description uses the source's ORIGINAL name (pre-normalization); the prefixed tool name uses normalized. Slight inconsistency but consistent with existing behavior — operator-facing display uses original, machine dispatch uses normalized.
- **`mcp__` prefix in a non-MCP tool name (collision)**: highly unlikely — built-in tools never start with `mcp__`. If a future built-in does, it'd be erroneously included in `SearchMcps` results. Not L3's responsibility; add a code comment warning future tool authors.
- **Query with empty source_index (no attached MCPs)**: `_filter_mcp_candidates` returns empty list → execute returns "No MCP tools found." This is consistent.
- **Source's tools registered via `get_tools_for_agent` but absent from source_index** (e.g., source has live tools via `acquire` but `_cache.tools` is empty in DB — operator hit Test but never saved? edge case): factory's source_index loop SKIPS sources with empty `_cache.tools`. The MCP tools ARE in the registry (via `get_tools_for_agent`), but `SearchMcps` source-level matching won't surface them. Per-tool matching against the registry's `mcp__`-prefixed schemas still works. Slight inconsistency in operator UX (source-level discoverability gap) but tools remain reachable via per-tool match. Document in code comment.
- **Two sources with same name** (impossible — DB unique constraint on source.name, verify): if it ever happened, source_index would dedupe; second source's tools dropped. Not L3's concern; mention in comment for future safety.

## Files Affected

- `the_one/mcp/_tool_provider.py` — extract filter helper + refactor (~40 LOC net)
- `the_one/tools/_search_mcps.py` — NEW (~200 LOC)
- `the_one/agent/factory.py` — wiring + source index construction (~20 LOC net)
- `the_one/tools/_search_stubs.py` — docstring update (~5 LOC)
- `tests/test_search_mcps.py` — NEW (~280 LOC, 10-13 tests)

**Total**: ~545 LOC. Above the F10 §10 sizing estimate of ~200-250 LOC (which assumed a simpler implementation; the shared filter helper + source index plumbing adds the extra). Operator-approval threshold: this is the natural shape of the work; pushing it under the estimate would force a less-clean implementation. Flag for L8 review queue.

## Citation Audit

Citations verified against current code at L3 design time (2026-05-10):

- `the_one/agent/core.py:33 — SEARCH_TOOLS_SCHEMA` ✓ verified (L1-landed)
- `the_one/agent/core.py:56 — SEARCH_MCPS_SCHEMA` ✓ verified (L1-landed)
- `the_one/agent/core.py:128 — _compute_visible_schemas` ✓ verified (L1-landed)
- `the_one/agent/factory.py:12-13 — imports of SearchMcpsStub + SearchTools` ✓ verified (post-L2)
- `the_one/agent/factory.py:176 — registry.register(SearchTools(...))` ✓ verified (L2-landed)
- `the_one/agent/factory.py:177 — registry.register(SearchMcpsStub(...))` ✓ verified (L1-landed; L3 replaces)
- `the_one/agent/factory.py:188-194 — MCP tool integration via mcp_provider.get_tools_for_agent` ✓ verified
- `the_one/mcp/_tool_provider.py:175 — class MCPToolProvider` ✓ verified
- `the_one/mcp/_tool_provider.py:183 — async def get_tools_for_agent` ✓ verified
- `the_one/mcp/_tool_provider.py:211-220 — Phase A loads sources from DB` ✓ verified
- `the_one/mcp/_tool_provider.py:264-284 — per-source enabled_tools/disabled_tools filter` ✓ verified (the block to extract)
- `the_one/mcp/_tool_provider.py:65 — _apply_override` ✓ verified
- `the_one/mcp/_tool.py:64 — class MCPClientTool` ✓ verified
- `the_one/mcp/_tool.py:94-133 — MCPClientTool.__init__` ✓ verified
- `the_one/mcp/_tool.py:54-61 — _normalize_source_name` ✓ verified
- `the_one/mcp/_overrides — StdioMCPOverride + StreamableHttpMCPOverride` ✓ verified via _tool_provider.py imports
- `the_one/mcp/types — MCPTool` ✓ verified via _tool_provider.py imports
- `the_one/tools/_search_stubs.py:100-133 — SearchMcpsStub` ✓ verified (L1-landed)
- `the_one/tools/_search_tools.py — SearchTools (L2)` ✓ verified (L2-landed; reference pattern)

**Audit summary**: 19 citations verified against current code at leg design time. 19 OK, 0 drifted, 0 gone, 0 unverifiable.

---

## Post-Completion Checklist

**Complete ALL steps before marking leg `landed`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (file-scoped + L1+L2 regression + full unit suite vs L2 post-landing baseline of 1474 pass)
- [ ] Update flight-log.md with L3 leg progress entry under "Leg Progress" section
- [ ] Set this leg's status to `landed` (NOT `completed`)
- [ ] Check off this leg in flight.md Legs list
- [ ] **Do NOT commit** — Phase 2d batches commits
- [ ] **Do NOT signal `[HANDOFF:review-needed]`** — reserved for Phase 2d
