# Squawk 0326: Document the platform-surface contract in agents.md

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-03
**Completed**: 2026-11-14

## Report
`the_one/agents.md` has a one-line "Sortie 08" bullet that names `MCPClientTool.is_platform_surface` and says a non-surface row named exactly `self-configuration` is unsupported. It does not give the contract a later maintainer needs (sortie 08 debrief, Recommendation 3). Add:
- **`is_platform_surface`**:
  - It is set from the ownership marker (`is_surface_row(effective_source)`), never from the name.
  - `AgentFactory` reads it with `getattr(tool, "is_platform_surface", False)`, so injected stub tools (`tests/test_factory.py`'s `StubMCPProvider`) keep the `disabled_tools` filter.
  - Promote it to a `Tool` base attribute with a default if a second platform-owned source ever appears.
- **The unsupported state**: why there is no carve-out. Such a row exists only if it was created before the M21 F01 L03 reservation, and it already collides on prefixed tool names (`_tool_provider.py`'s first-source-wins check drops one source's tools). So DD3, the startup strip and DD7 treat the key and the prefix as the surface. Don't add a carve-out.

Docs only.

## Evidence
- `the_one/agents.md:920`: the "Sortie 08 — the server owns the surface on an agent" bullet (the existing one-line mentions).
- `the_one/mcp/_tool.py::MCPClientTool.is_platform_surface`.
- `the_one/agent/factory.py`, the MCP registration loop: `getattr(tool, "is_platform_surface", False)`.
- Rationale: `sorties/08-self-configuration-off-tools-tab/flight.md` DD4 "Unsupported state" and the flight log, Architect review 2.

## Corrective Action
Added two sub-bullets under the "Sortie 08 — the server owns the surface on an agent" bullet in `the_one/agents.md`: "The `is_platform_surface` contract" (set from `is_surface_row(effective_source)`, never the name; `getattr(tool, "is_platform_surface", False)` in `AgentFactory.create` so injected stubs keep the filter; promote to a `Tool` base attribute if a second platform-owned source appears) and "Why the unsupported state has no carve-out" (a pre-reservation row named `self-configuration` already collides on the `mcp__self-configuration__` prefix through the first-source-wins check, so DD3, the startup strip and DD7 treat key and prefix as the surface). Documentation only.

## Verification
Read the new text against `the_one/mcp/_tool.py` (`__init__`, the `is_platform_surface` property), `the_one/agent/factory.py` (the MCP registration loop) and `the_one/self_configuration/constants.py::is_surface_row`; the first-source-wins check is in `the_one/mcp/_tool_provider.py` (module docstring "Prefix collision"). All cited symbols exist. `tests/test_factory.py` and `tests/test_self_configuration_agent_writes.py` reference `is_platform_surface` as described.

Gate (Flight Director, full gate on the final tree, 2026-11-14): unit tier 10155 passed, 15 skipped (under `THE_ONE_TEST_NETNS=1`); browser `PARALLEL_RESULT rc=0 total=2253s lanes=20 failed=-`.

## Sign-Off
**Reviewer**: independent Reviewer (Sonnet tier, because the batch diff touches the MCP sandbox error path), who confirmed the batch diff with `[HANDOFF:confirmed]` on 2026-11-14 with no high or medium issues.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-14` commit on `squawk/turnaround-2026-11-14`
