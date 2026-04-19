# Flight: Architecture Blueprint

**Status**: completed
**Mission**: [Structural Foundation](../../mission.md)

## Contributing to Criteria

- [ ] Each architectural concern lives in a clearly bounded module with explicit public interfaces
- [ ] New functionality can be added by creating files in designated locations without modifying core agent code
- [ ] The tool system supports registry-based management with runtime enable/disable per agent
- [ ] The plugin architecture supports both built-in tools and future MCP client integrations through a unified `ToolProvider` protocol
- [ ] The architecture supports multiple agent definitions, each with their own prompt, tool set, LLM provider, and configuration
- [ ] An `agents.md` file provides development-facing self-awareness context
- [ ] The extension model is documented with clear patterns for adding tools, providers, and future extension types
- [ ] A developer (human or LLM) can understand where to add a new capability by reading the project structure and extension documentation alone

---

## Pre-Flight

### Objective

Produce the complete architectural blueprint for the-one: target directory structure, module boundaries, public interfaces, multi-agent model, persistence strategy, plugin protocol, and `agents.md` specification. This is a design-only flight — no code changes, only documentation artifacts that guide all subsequent flights.

### Open Questions

- [x] Persistence layer → filesystem JSON with `AgentConfigStore` protocol (see mission resolved questions)
- [x] Multi-agent scope → definition and instantiation only, not coordination
- [x] `agents.md` vs runtime prompts → sharp separation (see mission resolved questions)
- [x] `ToolProvider` protocol timing → stub in Flight 2, implement in Flight 3
- [x] Module granularity for tools → resolved during target-architecture leg
- [x] Where design docs land → flight directory (`missions/01-structural-foundation/flights/01-architecture-blueprint/`)
- [x] System prompt templating for multi-agent → each agent definition carries its own prompt; current hardcoded prompt becomes the default agent's config. Detailed templating deferred to Flight 3.

### Design Decisions

**Filesystem JSON for agent configs via `settings.data_dir`**: Agent definitions stored as JSON files in `settings.data_dir / "agents/"` (defaults to `~/.the-one/agents/`, overridable via `THE_ONE_DATA_DIR`)
- Rationale: Zero external deps, human-editable, git-friendly, sufficient for single-user case. Inherits existing config infrastructure.
- Trade-off: No queryability, but we don't need it for 2-5 agent configs

**Registry-based tool management with per-agent views**: Global tool registry holds all available tools; each agent definition specifies which tools are enabled
- Rationale: A bad tool can be disabled per-agent without code rollback; different agents can have different capabilities. `load_defaults()` is the primary coupling to eliminate.
- Trade-off: Slightly more complex than flat `load_defaults()`, but essential for multi-agent

**`AgentFactory` pattern for instantiation**: A factory reads agent definitions and produces configured `Agent` instances with the right provider, tools, and prompt. The existing `Agent.__init__` already accepts `system_prompt` as a parameter — this is leveraged, not redesigned.
- Rationale: Decouples agent config from interface code; interfaces just ask for an agent by name
- Trade-off: One more layer of indirection

**Design-only flight**: No code changes in this flight
- Rationale: The blueprint must be agreed before any restructuring begins; wrong architectural decisions compound through every subsequent flight
- Trade-off: Delays implementation by one flight cycle

### Prerequisites

- [x] Mission approved
- [x] Open questions resolved
- [x] Access to codebase for reference

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

Analyze the current codebase structure, identify the target architecture, and produce design documents that cover:

1. **Target directory layout** — where every file type lives, naming conventions, module boundaries, with current-state baseline inline
2. **Public interfaces** — what each module exports, how modules interact
3. **Multi-agent model** — agent definition schema, config store protocol, factory pattern
4. **Plugin protocol** — high-level `ToolProvider` decisions (built-in vs MCP loading, per-agent views, enable/disable). Detailed ABC interface deferred to Flight 2 stub.
5. **`agents.md` specification** — what it contains, how it's structured, how it differs from runtime config
6. **Extension guide** — documented recipes for "how to add a tool", "how to add a provider", "how to define a new agent"

Design documents are written to the flight directory. No source code changes.

### Checkpoints

- [x] Target directory structure defined with current-state baseline
- [x] Module interfaces specified
- [x] Multi-agent model designed (schema, config store, factory)
- [x] Plugin protocol high-level decisions made
- [x] `agents.md` spec written
- [x] Extension guide produced
- [x] Target architecture reconciled with existing CLAUDE.md (plan for updating in Flight 2)

### Adaptation Criteria

**Divert if**:
- Analysis reveals the current codebase is more tangled than expected and can't be restructured without a full rewrite (contradicts mission constraint)

**Acceptable variations**:
- Module names or directory structure may shift during design as better patterns emerge
- Additional extension types may be identified beyond tools/providers
- Where `_CONTINUE_SCHEMA` and `_DIRECT_ACTIONS` land may evolve (behaviors/signals module vs core)

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `target-architecture` — Define the target directory layout, module boundaries, and public interfaces. Includes current-state baseline inline for context. The structural blueprint that Flight 2 will implement. Resolves module granularity question (e.g., flat tools vs directory-per-tool).
- [x] `multi-agent-model` — Design the agent definition schema, `AgentConfigStore` protocol, and `AgentFactory` pattern. Defines how agents are configured, persisted, and instantiated.
- [x] `plugin-protocol` — High-level design for the `ToolProvider` protocol, tool registry with per-agent views, and the built-in vs MCP tool loading strategy. Detailed ABC deferred to Flight 2 stub.
- [x] `agents-md-and-extension-guide` — Write the `agents.md` spec (separate document) and the extension guide (separate document) for adding tools, providers, and agent definitions.

---

## Post-Flight

### Completion Checklist

- [x] All legs completed
- [ ] Design documents reviewed and approved
- [x] No code changes made (design-only flight)
- [ ] Blueprint is sufficient to guide Flight 2 implementation

### Verification

The flight is verified when:
- A developer can read the blueprint and know exactly where to create files for a new tool, provider, or agent definition
- The multi-agent model is concrete enough to implement without further design decisions
- The plugin protocol decisions are clear enough to guide the `ToolProvider` stub in Flight 2
- All mission open questions about module granularity are resolved
- The target architecture is reconciled with existing CLAUDE.md, with a plan for updating it in Flight 2
