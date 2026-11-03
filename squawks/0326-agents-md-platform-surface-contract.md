# Squawk 0326: Document the platform-surface contract in agents.md

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-03
**Completed**: —

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
*(written at completion)*

## Verification
Read the new `agents.md` text against `_tool.py` and `factory.py`, and check that every cited symbol exists.

## Sign-Off
*(written at completion)*
