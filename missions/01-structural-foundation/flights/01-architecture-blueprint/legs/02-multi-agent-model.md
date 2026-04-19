# Leg: multi-agent-model

**Status**: completed
**Flight**: [Architecture Blueprint](../flight.md)

## Objective

Design the agent definition schema, AgentConfigStore protocol, and AgentFactory pattern for multi-agent support.

## Context

- Flight design decisions specify filesystem JSON in `settings.data_dir / "agents/"` for persistence
- The current `Agent.__init__` already accepts `system_prompt` as a parameter — the factory leverages this
- Both `cli.py` and `web/app.py` have duplicate `_make_agent()` functions that will be replaced by factory calls
- Multi-agent coordination is out of scope — this covers definition and instantiation only

## Inputs

- Target architecture from Leg 1
- Mission resolved questions (persistence layer, multi-agent scope, agent switching)
- Current `Agent.__init__` signature and `_make_agent()` implementations

## Outputs

- `multi-agent-model.md` — design artifact in the flight directory
- AgentConfig dataclass, JSON schema, AgentConfigStore protocol, AgentFactory design

## Acceptance Criteria

- [ ] AgentConfig dataclass has all fields with types, defaults, and validation rules
- [ ] Agent definition JSON schema is complete with field semantics and example
- [ ] Default agent config maps exactly to the current hardcoded SYSTEM_PROMPT behavior
- [ ] AgentConfigStore protocol defines all CRUD operations with signatures
- [ ] FilesystemConfigStore implementation strategy is specified
- [ ] AgentFactory.create() workflow is step-by-step clear
- [ ] Interface migration path shows how _make_agent() becomes factory.create()

## Verification Steps

- Verify AgentConfig fields cover all current Agent constructor parameters
- Confirm default config produces identical behavior to current hardcoded setup
- Check that JSON schema is valid and parseable

## Implementation Guidance

1. **Define AgentConfig dataclass** — fields, types, defaults, helper methods
2. **Design JSON schema** — the on-disk format for agent definitions
3. **Specify default agent** — the config that reproduces current behavior
4. **Define AgentConfigStore protocol** — CRUD interface
5. **Plan FilesystemConfigStore** — directory structure, file naming, error handling
6. **Design AgentFactory** — how it wires LLM + tools + prompt from a config
7. **Map interface changes** — how cli.py and app.py adopt the factory

## Edge Cases

- **Missing config file**: Factory falls back to default agent config
- **Invalid JSON**: Store raises a clear error, does not silently use defaults
- **Unknown LLM provider**: Factory raises at creation time, not at first LLM call

## Files Affected

- `missions/01-structural-foundation/flights/01-architecture-blueprint/multi-agent-model.md` — created (design artifact)
