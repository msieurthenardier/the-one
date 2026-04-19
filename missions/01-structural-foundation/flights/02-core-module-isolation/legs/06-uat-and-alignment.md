# Leg: uat-and-alignment

**Status**: completed
**Flight**: [Core Module Isolation](../flight.md)

## Objective

Verify the restructured codebase works end-to-end: CLI chat, web server, tool execution, factory behavior, and extension guide accuracy.

## Acceptance Criteria

- [x] `the-one chat` launches without errors
- [x] `the-one serve` starts the web server without errors
- [x] `AgentFactory().create()` returns an agent with 14 tools and correct system prompt
- [x] `BuiltinToolProvider().get_tools()` returns 14 tools
- [x] No circular imports
- [x] `ruff check the_one/` has no new errors
- [x] `python -m pytest tests/` passes (or no tests exist)
- [x] Extension guide file paths are valid against restructured codebase

## Verification Steps

1. Factory behavior: `AgentFactory().create()` equivalence
2. BuiltinToolProvider: 14 tools, protocol compliance
3. Circular import check: all key modules importable
4. Lint check: ruff clean
5. CLI launch test: `the-one chat` starts
6. Web server test: `the-one serve` starts
7. Extension guide spot-check

## Files Affected

- None (verification only, fixes if needed)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] Update flight.md status to `landed` (this IS the final leg)
- [x] Check off flight in mission.md
- [x] Commit all changes together (code + artifacts)
