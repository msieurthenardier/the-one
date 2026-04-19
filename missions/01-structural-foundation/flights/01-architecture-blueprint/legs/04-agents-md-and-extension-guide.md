# Leg: agents-md-and-extension-guide

**Status**: completed
**Flight**: [Architecture Blueprint](../flight.md)

## Objective

Write the agents.md development-facing self-awareness document and the extension guide with step-by-step recipes.

## Context

- agents.md is analogous to CLAUDE.md but describes the target architecture for LLMs working on the codebase
- agents.md describes the *target* architecture (post-restructure), not the current state
- The extension guide provides actionable recipes for the four main extension patterns
- Both documents are separate artifacts — agents.md lives in the source tree, extension guide in the flight directory

## Inputs

- Target architecture from Leg 1
- Multi-agent model from Leg 2
- Plugin protocol from Leg 3
- Current CLAUDE.md for tone and structure reference

## Outputs

- `the_one/agents.md` — development-facing architecture doc (in source tree)
- `extension-guide.md` — recipes for extending the system (in flight directory)

## Acceptance Criteria

- [ ] agents.md covers architecture overview, module map, and dependency graph
- [ ] agents.md describes the target architecture, not the current state
- [ ] agents.md is NOT loaded at runtime (development-facing only)
- [ ] Extension guide has recipe for adding a tool (2 steps)
- [ ] Extension guide has recipe for adding an LLM provider (3 steps)
- [ ] Extension guide has recipe for defining a new agent (1 step)
- [ ] Extension guide has recipe for adding an MCP tool server (future)
- [ ] Each recipe is concrete with file paths, code snippets, and example content

## Verification Steps

- Verify agents.md module map matches target architecture from Leg 1
- Confirm extension guide recipes reference correct file paths from target layout
- Check that agents.md would not be imported by any runtime code

## Implementation Guidance

1. **Write agents.md** — architecture overview, module map, dependency graph, key patterns
2. **Write extension guide recipes**:
   - Adding a tool: create file + register in builtins.py
   - Adding an LLM provider: create file + register + add lazy-load
   - Defining a new agent: create JSON file in agents directory
   - Adding MCP tool server: implement ToolProvider protocol (future)
3. **Include code snippets** — minimal but complete examples for each recipe

## Edge Cases

- **agents.md vs CLAUDE.md overlap**: agents.md focuses on architecture internals; CLAUDE.md focuses on usage, commands, and conventions. Minimal overlap.

## Files Affected

- `the_one/agents.md` — created (development-facing doc)
- `missions/01-structural-foundation/flights/01-architecture-blueprint/extension-guide.md` — created (design artifact)
