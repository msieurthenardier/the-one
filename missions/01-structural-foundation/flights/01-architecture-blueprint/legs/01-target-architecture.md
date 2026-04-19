# Leg: target-architecture

**Status**: completed
**Flight**: [Architecture Blueprint](../flight.md)

## Objective

Define the target directory layout, module boundaries, and public interfaces for the-one's restructured architecture.

## Context

- The current codebase works but grew organically — `agent/core.py` bundles the system prompt, direct actions, continue schema, and tool call extraction alongside the agent loop
- `load_defaults()` on `ToolRegistry` creates tight coupling between the registry and all 14 tool implementations
- `memory.py` and `self_deploy.py` reference the global `settings` singleton at module level
- This leg resolves the open question about module granularity (flat tools vs directory-per-tool)

## Inputs

- Current codebase at `/home/cprch/projects/the-one/`
- Mission design decisions (filesystem JSON, registry-based tools, AgentFactory)
- Flight design decisions (design-only, no code changes)

## Outputs

- `target-architecture.md` — design artifact in the flight directory
- Current-state baseline, target directory layout, module boundaries, dependency flow, migration mapping

## Acceptance Criteria

- [ ] Current state baseline accurately reflects the existing codebase
- [ ] Target directory layout is complete with every new and moved file
- [ ] Module boundaries specify what each module exports
- [ ] Dependency flow diagram shows allowed and prohibited import directions
- [ ] Migration mapping shows where every extracted symbol lands
- [ ] Tools requiring decoupling (settings references) are identified with remediation plan
- [ ] CLAUDE.md reconciliation plan covers what needs updating in Flight 2

## Verification Steps

- Cross-reference current state baseline against actual `the_one/` directory structure
- Verify every file in target layout is accounted for (new, moved, or unchanged)
- Confirm dependency flow has no circular imports

## Implementation Guidance

1. **Audit current directory structure** — document every file, its purpose, and its dependencies
2. **Identify coupling points** — module-level imports of `settings`, cross-module references
3. **Design target layout** — new files, moved symbols, unchanged modules
4. **Define module exports** — what each `__init__.py` exposes
5. **Draw dependency flow** — allowed import directions between layers
6. **Map migrations** — symbol-by-symbol: where it is now, where it goes
7. **Plan CLAUDE.md updates** — what sections need rewriting after restructure

## Edge Cases

- **Circular imports**: The current `config.py` → `settings` singleton is imported everywhere; target must preserve this without circular deps
- **Tool lazy-loading**: Moving from `load_defaults()` to `BuiltinToolProvider` must maintain lazy imports to avoid loading optional deps

## Files Affected

- `missions/01-structural-foundation/flights/01-architecture-blueprint/target-architecture.md` — created (design artifact)
