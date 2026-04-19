# Leg: patch-design-artifacts

**Status**: completed
**Flight**: [Core Module Isolation](../flight.md)

## Objective

Fix 3 debrief action items in Flight 1 design artifacts so implementation legs follow corrected blueprints.

## Context

- Flight 1 debrief identified 3 technical issues in design artifacts
- These must be corrected before implementation begins (Legs 2-4 read these artifacts)
- All changes are to `.md` files only — no source code modifications

## Inputs

- `flights/01-architecture-blueprint/target-architecture.md` — has inaccurate `self_deploy.py` coupling description
- `flights/01-architecture-blueprint/multi-agent-model.md` — missing `llm_base_url` in `_default_config()`, uses `AgentConfig(**data)` instead of `model_validate()`
- `flights/01-architecture-blueprint/flight-debrief.md` — lists the 3 action items

## Outputs

- Updated `target-architecture.md` with:
  - Corrected `self_deploy.py` coupling characterization
  - `extract_tool_calls(text: str, valid_names: set[str])` in the "What Moves Where" table
  - `match_direct_action` added to the "What Moves Where" table
- Updated `multi-agent-model.md` with:
  - `AgentConfig` class changed from `@dataclass` to Pydantic `BaseModel` (consistent with flight design decision)
  - `llm_base_url=settings.llm_base_url` in `_default_config()`
  - `AgentConfig.model_validate(data)` in `FilesystemConfigStore.load()`
- Debrief action items 1-3 checked off (items 4-5 are addressed in later legs)

## Acceptance Criteria

- [x] `target-architecture.md` "Tools Requiring Decoupling" section correctly states that `self_deploy.py` accesses settings inside `execute()` at call time, not at module/import level. The proposed constructor injection fix rationale is updated to focus on testability and per-agent configuration, not import-time binding.
- [x] `target-architecture.md` "What Moves Where" table includes `extract_tool_calls()` with signature `extract_tool_calls(text: str, valid_names: set[str]) -> list[ToolCall]` and notes that `core.py` call site passes `set(self.tools.tool_names) | {"continue"}`
- [x] `target-architecture.md` "What Moves Where" table includes `match_direct_action` (was `_match_direct_action` static method)
- [x] `multi-agent-model.md` `_default_config()` snippet includes `llm_base_url=settings.llm_base_url`
- [x] `multi-agent-model.md` `AgentConfig` class definition updated from `@dataclass` to Pydantic `BaseModel` with equivalent fields
- [x] `multi-agent-model.md` `FilesystemConfigStore.load()` uses `AgentConfig.model_validate(data)` instead of `AgentConfig(**data)`
- [x] Flight 1 debrief action items 1-3 checked off (items 4-5 deferred to later legs)

## Verification Steps

- Read the modified files and confirm each correction matches the acceptance criteria
- Cross-reference `self_deploy.py` description against actual source (`the_one/tools/self_deploy.py` lines 36-38)

## Implementation Guidance

1. **Fix `self_deploy.py` characterization in target-architecture.md**
   - In "Coupling Points" section (item 4), change from "module-level settings references" to "accesses settings inside `execute()` at call time"
   - In "Tools Requiring Decoupling > self_deploy.py" section, update "Current" and "Problem" descriptions
   - Keep the "Fix" (constructor injection) — but reframe rationale as testability/per-agent config, not import-time binding

2. **Add `extract_tool_calls` and `match_direct_action` to migration table**
   - Add row: `_extract_tool_calls()` | `agent/core.py:191-220` (method) | `agent/behaviors.py` as `extract_tool_calls(text: str, valid_names: set[str]) -> list[ToolCall]`
   - Add note: `core.py` call site becomes `extract_tool_calls(text, set(self.tools.tool_names) | {"continue"})`
   - Add row: `_match_direct_action()` | `agent/core.py:222-229` (static method) | `agent/behaviors.py` as `match_direct_action(user_input: str) -> tuple[str, dict] | None`

3. **Update `AgentConfig` class in multi-agent-model.md to Pydantic BaseModel**
   - Change `from dataclasses import dataclass, field` to `from pydantic import BaseModel, Field`
   - Change `@dataclass class AgentConfig` to `class AgentConfig(BaseModel)`
   - Update `disabled_tools: list[str] = field(default_factory=list)` to `disabled_tools: list[str] = Field(default_factory=list)`
   - Update `enabled_tools` default similarly if needed
   - Keep all fields, methods, and semantics identical

4. **Fix `_default_config()` in multi-agent-model.md**
   - Add `llm_base_url=settings.llm_base_url,` to the `_default_config()` code snippet

5. **Fix `FilesystemConfigStore.load()` in multi-agent-model.md**
   - Change `return AgentConfig(**data)` to `return AgentConfig.model_validate(data)`

6. **Check off debrief action items 1-3** (items 4-5 are for later legs)

## Edge Cases

- None — this is a documentation-only patch

## Files Affected

- `missions/01-structural-foundation/flights/01-architecture-blueprint/target-architecture.md` — coupling description fix, migration table additions
- `missions/01-structural-foundation/flights/01-architecture-blueprint/multi-agent-model.md` — default config fix, model_validate fix
- `missions/01-structural-foundation/flights/01-architecture-blueprint/flight-debrief.md` — check off action items

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing (N/A — documentation-only patch)
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [ ] If final leg of flight:
  - [ ] Update flight.md status to `landed`
  - [ ] Check off flight in mission.md
- [x] Commit all changes together (code + artifacts)
