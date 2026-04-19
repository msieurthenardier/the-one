# Flight Log: Architecture Blueprint

**Flight**: [Architecture Blueprint](flight.md)

## Summary

All four legs completed. Design artifacts produced covering target architecture, multi-agent model, plugin protocol, and extension guide. No code changes made — design-only flight as planned.

---

## Leg Progress

### target-architecture
**Status**: completed
**Started**: 2026-04-18
**Completed**: 2026-04-18

#### Changes Made
- Created leg spec: `legs/01-target-architecture.md`
- Created design artifact: `target-architecture.md`
- Documented current state baseline with all coupling points
- Defined target directory layout with 7 new files and 9 modified files
- Established module boundaries and dependency flow diagram
- Mapped every extracted symbol to its target location
- Identified `memory.py` and `self_deploy.py` as tools requiring decoupling
- Planned CLAUDE.md reconciliation for Flight 2
- Resolved module granularity question: flat tools, no directory-per-tool

#### Notes
Module granularity resolved in favor of flat structure — 14 tools is manageable, directory-per-tool adds overhead without proportional benefit.

---

### multi-agent-model
**Status**: completed
**Started**: 2026-04-18
**Completed**: 2026-04-18

#### Changes Made
- Created leg spec: `legs/02-multi-agent-model.md`
- Created design artifact: `multi-agent-model.md`
- Designed AgentConfig dataclass with 10 fields, defaults, and helper methods
- Defined agent definition JSON schema with validation rules
- Specified default agent config that reproduces current hardcoded behavior
- Defined AgentConfigStore protocol (5 methods: list, load, save, delete, exists)
- Designed FilesystemConfigStore with JSON serialization
- Designed AgentFactory with create() workflow and default fallback
- Mapped interface changes: _make_agent() → factory.create()

#### Notes
Default agent is synthesized from settings at factory init time (not module level) to always reflect current env vars. No default.json file on disk unless user creates one.

---

### plugin-protocol
**Status**: completed
**Started**: 2026-04-18
**Completed**: 2026-04-18

#### Changes Made
- Created leg spec: `legs/03-plugin-protocol.md`
- Created design artifact: `plugin-protocol.md`
- Defined ToolProvider protocol (Protocol, not ABC — duck-typing friendly)
- Designed BuiltinToolProvider as load_defaults() replacement
- Specified per-agent filtering with whitelist + blacklist + truth table
- Placed filtering at factory time — Agent sees pre-filtered registry
- Identified MCP integration surface without over-designing
- Clarified tool schema translation chain is unchanged

#### Notes
Protocol chosen over ABC to minimize coupling. MCP integration deferred but the protocol surface is sufficient to plug it in later.

---

### agents-md-and-extension-guide
**Status**: completed
**Started**: 2026-04-18
**Completed**: 2026-04-18

#### Changes Made
- Created leg spec: `legs/04-agents-md-and-extension-guide.md`
- Created `the_one/agents.md` — development-facing architecture doc
- Created design artifact: `extension-guide.md`
- agents.md covers architecture overview, module map, dependency graph, key patterns
- Extension guide has 4 recipes: add tool (2 steps), add provider (3 steps), define agent (1 step), add MCP server (future)

#### Notes
agents.md describes the target architecture, not current state. It will need a pass after Flight 2 to verify accuracy against actual implementation.

---

## Decisions

### Module Granularity: Flat Tools
**Context**: Open question from mission — should tools/ remain flat or adopt directory-per-tool?
**Decision**: Keep flat. 14 tools in single files is manageable. Group related tools in one file (filesystem.py, web.py).
**Impact**: Simpler structure, fewer files to navigate. Reconsider if a tool exceeds ~200 lines.

### Protocol vs ABC for ToolProvider
**Context**: Could have used ABC (like Tool and LLMProvider) or Protocol.
**Decision**: Protocol (structural typing) — any object with `name` and `get_tools()` works.
**Impact**: Lower coupling. MCP providers don't need to inherit from anything in this codebase.

### Default Agent Synthesized, Not Stored
**Context**: Should the default agent config live on disk?
**Decision**: Synthesized from settings at factory init time. Users can optionally create `default.json` to override.
**Impact**: Zero-config default behavior. No file management for the common case.

---

## Deviations

_(none — flight executed as planned)_

---

## Anomalies

_(none)_

---

## Session Notes

**2026-04-18**: Executed all four legs in a single session. Design artifacts are internally consistent — target-architecture defines the structure, multi-agent-model defines the persistence and factory patterns, plugin-protocol defines the tool loading strategy, and extension-guide provides actionable recipes. The agents.md file ties it all together as a developer reference.
