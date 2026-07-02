# Leg: tool-whitelist-mcp-decouple

**Status**: ready
**Flight**: [HAT — Provider Chat Sweep](../flight.md)

## Objective
Stop an agent's built-in-tool `enabled_tools` whitelist from silently disabling its MCP
tools: scope the `enabled_tools`/whitelist semantics to built-in tools only, and let MCP
tools be governed by `mcp_overrides` (as the editor already intends).

## Context
- HAT finding **F09-08** (full diagnosis in flight-log). `is_tool_enabled`
  (`agent/config.py:569-575`) treats a non-null `enabled_tools` as a **global** whitelist
  over ALL tool names, including `mcp__`-prefixed ones. The agent editor
  (`static/js/areas/studio.js:1983-2007`) builds `enabled_tools` from **only** built-in
  checkboxes (`input[data-tool]`) — MCP tools use a separate control
  (`data-mcp-tool-toggle` / `mcp_overrides`). When built-in enabled ≤ disabled, the editor
  emits a built-ins-only whitelist (`:2002`), so every MCP tool falls outside it and is
  filtered at agent build (`agent/factory.py:421`, gated on `is_tool_enabled`).
- **Operator-chosen fix: backend decouple.** Making the whitelist built-in-only means the
  editor's existing behavior becomes correct (a built-ins-only whitelist no longer implies
  "MCP off"), so **no required frontend change**. MCP tools are already override-filtered
  upstream in `MCPToolProvider.get_tools_for_agent` (via `filter_mcp_tools_by_override`);
  the `is_tool_enabled` gate should not *also* apply the built-in whitelist to them.
- Operator's live agent already restored out-of-band (API: `enabled_tools=null` +
  `disabled_tools=[17 built-ins]`); this leg fixes the root cause so the editor path is safe.

## Inputs
- `the_one/agent/config.py` — `is_tool_enabled` (`:569-575`), the `enabled_tools`/
  `disabled_tools`/`mcp_overrides` fields.
- `the_one/agent/factory.py` — built-in registration (`:409-411`) + MCP registration
  (`:418-422`), and how `mcp_overrides` is applied via `get_tools_for_agent` /
  `filter_mcp_tools_by_override`.
- `tests/test_config.py` — existing `is_tool_enabled` unit tests.

## Outputs
- `is_tool_enabled` no longer lets a built-in `enabled_tools` whitelist disable
  `mcp__`-prefixed tools; MCP enablement is governed by `mcp_overrides` (+ explicit
  `disabled_tools` as a universal off-switch).
- Tests proving an agent with `enabled_tools=[built-ins…]` + attached MCP source keeps its
  MCP tools.

## Acceptance Criteria
- [ ] With `enabled_tools=['read_file', …built-ins…]` (non-null, no `mcp__` names) and an MCP
      source attached, all that source's tools remain enabled (`is_tool_enabled('mcp__X__y')`
      → True) and register at agent build.
- [ ] The built-in whitelist still governs built-ins: a built-in NOT in a non-null
      `enabled_tools` is disabled; `enabled_tools=None` still means all built-ins on.
- [ ] `disabled_tools` remains a universal explicit blacklist (an `mcp__…` name in
      `disabled_tools` is still disabled — explicit off-switch preserved).
- [ ] MCP enable/disable via `mcp_overrides` is unchanged and still authoritative for MCP
      tools (no regression to per-source allow/deny filtering in `get_tools_for_agent`).
- [ ] `enabled_tools=[]` (empty) semantics: decide + document — recommend it still blocks all
      **built-in** tools but does NOT block MCP tools (consistent with the decouple). State
      the choice in a comment/test.
- [ ] Tests: `tests/test_config.py` gains MCP-prefixed cases; a factory-level test (or
      existing suite) shows MCP tools register despite a built-ins-only whitelist. `ruff`
      clean; suite green.
- [ ] No required frontend change (confirm the editor's built-ins-only whitelist is now
      correct under the new semantics; if a small studio.js consistency tweak is warranted,
      keep it minimal and note it).

## Implementation Guidance
1. In `is_tool_enabled` (`config.py:569`), detect MCP tools by the `mcp__` prefix. Apply the
   `enabled_tools` whitelist **only to non-MCP (built-in) names**. Keep the `disabled_tools`
   check universal (explicit blacklist wins for any name). Sketch:
   ```python
   def is_tool_enabled(self, tool_name: str) -> bool:
       is_mcp = tool_name.startswith("mcp__")
       if not is_mcp and self.enabled_tools is not None and tool_name not in self.enabled_tools:
           return False
       if tool_name in self.disabled_tools:
           return False
       return True
   ```
   (Confirm `mcp__` is the canonical MCP prefix used at registration — see `_search_tools.py`
   `_MCP_PREFIX` and factory naming.)
2. Verify MCP enablement still flows through `mcp_overrides` in
   `MCPToolProvider.get_tools_for_agent` / `filter_mcp_tools_by_override` — this leg does NOT
   change that path; it only stops the built-in whitelist from double-gating MCP tools.
3. Add unit tests in `tests/test_config.py`: (a) built-ins whitelist + `mcp__X__y` → MCP
   enabled; (b) `mcp__X__y` in `disabled_tools` → disabled; (c) built-in not in whitelist →
   disabled; (d) `enabled_tools=None` → all on. Add/extend a factory test if one exists that
   builds an agent with an MCP source + a built-ins-only whitelist and asserts MCP tools
   register.
4. Frontend: no functional change required. Optionally add a code comment near
   `studio.js:2002` noting the whitelist is built-in-only by backend contract (so a future
   dev doesn't "fix" the frontend to inject `mcp__` names, which would reintroduce coupling).

## Edge Cases
- **`enabled_tools=[]`** — was "block everything"; under the decouple it blocks all built-ins
  but not MCP. Document the chosen behavior explicitly (test it).
- **A legacy agent with `mcp__` names in `enabled_tools`** (shouldn't exist via the UI) —
  under the decouple those entries are ignored for gating (MCP via overrides). Acceptable;
  note it. If any such agent exists, `mcp_overrides` governs it.
- **Built-in and MCP name collision** — none expected (MCP names are `mcp__`-prefixed).

## Files Affected
- `the_one/agent/config.py` — `is_tool_enabled`.
- `tests/test_config.py` (+ a factory test if present) — MCP-prefixed coverage.
- *(optional)* `static/js/areas/studio.js` — a clarifying comment only.

---

## Post-Completion Checklist
- [ ] Acceptance criteria verified (unit + factory tests)
- [ ] Update flight-log.md (F09-08 resolved)
- [ ] Set leg status `completed` (after verify)
- [ ] Check off in flight.md; re-land the flight
- [ ] Commit (rolls into next build)
