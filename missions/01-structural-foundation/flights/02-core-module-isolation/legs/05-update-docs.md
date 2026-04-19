# Leg: update-docs

**Status**: completed
**Flight**: [Core Module Isolation](../flight.md)

## Objective

Update CLAUDE.md to reflect the restructured architecture and verify agents.md accuracy against the actual implementation.

## Context

- CLAUDE.md architecture section is stale — references `load_defaults()`, doesn't mention `AgentFactory`, `BuiltinToolProvider`, `behaviors.py`, `agents.md`
- `agents.md` was written for the target architecture during Flight 1 and should be mostly accurate, but needs verification against actual implementation
- Flight 1 design artifact `target-architecture.md` has a CLAUDE.md reconciliation plan listing specific sections to update

## Inputs

- Current `CLAUDE.md` — stale architecture section
- Current `the_one/agents.md` — needs verification
- `target-architecture.md` "CLAUDE.md Reconciliation Plan" section
- Actual source files (for verification)

## Outputs

- Updated `CLAUDE.md` with accurate architecture description
- Verified `the_one/agents.md` with any discrepancies fixed

## Acceptance Criteria

- [x] CLAUDE.md architecture section updated:
  - Tool layer mentions `BuiltinToolProvider` instead of `load_defaults()`
  - Agent loop section notes behaviors are in `behaviors.py`
  - Interfaces section notes both use `AgentFactory` instead of local `_make_agent()`
  - `agents.md` reference added (e.g., "For architecture internals, see `the_one/agents.md`")
  - Configuration section mentions `agents_dir` property
- [x] `agents.md` verified against actual implementation:
  - Module map matches actual file exports
  - `behaviors.py` entry includes `match_direct_action`
  - `config.py` entry says "Pydantic model" not "dataclass"
  - Dependency graph is accurate
  - Key patterns descriptions match actual behavior
- [x] No factual inaccuracies in either file
- [x] `ruff check the_one/` still clean (docs-only changes shouldn't affect this, but verify)

## Verification Steps

- Read updated CLAUDE.md and cross-reference claims against actual source
- Read agents.md and cross-reference module map against actual exports
- `ruff check the_one/`

## Implementation Guidance

1. **Update CLAUDE.md architecture section**
   Following the reconciliation plan from target-architecture.md:
   - **Tool layer**: Change "load_defaults() registers all 14 built-in tools" to describe BuiltinToolProvider pattern
   - **Agent loop**: Note that direct actions, continue signal schema, and tool call extraction are in `behaviors.py`, not `core.py`
   - **Interfaces**: Note both use `AgentFactory` instead of `_make_agent()`
   - **Add agents.md reference**: Add line like "For architecture internals, see `the_one/agents.md`"
   - **Configuration**: Mention `agents_dir` property

2. **Verify and fix agents.md**
   - Check `behaviors.py` entry — should include `match_direct_action` (was added in Leg 2)
   - Check `config.py` entry — should say "Pydantic model" not "dataclass" (changed in Leg 1)
   - Verify dependency graph against actual import structure
   - Verify all file/export descriptions match reality

## Edge Cases

- None — documentation-only changes

## Files Affected

- `CLAUDE.md` — Update architecture section
- `the_one/agents.md` — Verify and fix discrepancies

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [ ] If final leg of flight:
  - [ ] Update flight.md status to `landed`
  - [ ] Check off flight in mission.md
- [x] Commit all changes together (code + artifacts)
