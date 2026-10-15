# Squawk 0219: Name "set state before the yield" and the stub rule in agents.md's Project Conventions

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-15
**Completed**: —

## Report
Sortie 04 found two pre-existing pause/resume defects that came from two general patterns, but the lessons are only recorded in an MCP-specific paragraph. Add both to `the_one/agents.md`'s "Project Conventions" as named patterns:
- **set-state-before-yield**: state that a consumer reads after an async generator yields must be set before the yield, because consumers may `break` at that message and code after the yield never runs (origin: `Agent._dispatch_tool_calls`).
- **stub-presets-only-reachable-state**: a test stub may preset a state only if a real-component test shows the real collaborator reaches that state through the same consumer (origin: the `StubAgent` in `tests/test_app_websocket_pause_resume.py`, which preset `_deferred_tool_calls` and hid the bug).
Keep the MCP paragraph, pointing at the new entries.

## Evidence
- `the_one/agents.md` "## Project Conventions" (~l.103); the sortie 04 paragraph "Auth-pause state is set before the yield" (~l.1189, end of "MCP error translation").
- `sorties/04-honest-mcp-sign-in/flight-debrief.md` "Key Learnings".

## Corrective Action
*(written at completion)*

## Verification
Doc review; `make lint` (no code change).

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
