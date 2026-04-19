# Mission: Structural Foundation

**Status**: active

## Outcome

The-one evolves from a vibe-coded prototype into a well-structured, multi-agent platform. The codebase follows clear architectural patterns that make it obvious where new functionality belongs — whether added by a human, an LLM, or the agent itself. The system is designed from the ground up to support multiple specialized agents, each with their own tools, MCP connections, LLM provider, and prompt configuration. Each concern is isolated, independently testable, and pluggable. The result is a codebase that meets industry standards for open-source quality without relying on heavy framework dependencies.

## Context

The-one was built in a couple of hours as a proof-of-concept. The core ideas are sound — hand-rolled agent loop, tool registry, LLM abstraction, self-deployment — but the implementation grew organically without architectural guardrails. As the agent gains the ability to modify itself, the lack of clear boundaries becomes a liability: the agent (or any contributor) can't reliably add functionality without risking unintended side effects. The small models used as primary LLMs make tight isolation even more critical — they need clear, predictable patterns to work within.

The system needs to support multiple specialized agents that can be composed at runtime — each with different tools, models, and behaviors. This is not a future consideration; it's foundational to the architecture. A tool registry that can enable/disable tools per agent, a persistence layer for agent configurations, and clear boundaries between the agent runtime and agent definitions are all required from the start.

This mission establishes the structural foundation that all future capabilities (MCP client support, skills, multi-agent coordination, self-modification workflows) will build on.

## Success Criteria

- [ ] Each architectural concern (LLM providers, tools, agent loop, interfaces, configuration, persistence) lives in a clearly bounded module with explicit public interfaces
- [ ] New functionality can be added by creating files in designated locations without modifying core agent code
- [ ] The tool system supports registry-based management with runtime enable/disable per agent — a problematic tool can be disabled without rolling back code
- [ ] The plugin architecture supports both built-in tools (zero overhead, no external process) and future MCP client integrations (external tool servers) through a unified `ToolProvider` protocol
- [ ] The architecture supports multiple agent definitions, each with their own prompt, tool set, LLM provider, and configuration, managed through a persistence layer
- [ ] An `agents.md` file provides development-facing self-awareness context (like CLAUDE.md for the project's own architecture), distinct from runtime agent prompts/configuration
- [ ] The extension model is documented with clear patterns for adding tools, providers, and future extension types (skills, behaviors, integrations)
- [ ] Core modules (agent loop, tool registry, LLM registry) have unit tests that run in isolation; integration tests validate the agent step cycle end-to-end
- [ ] The Concourse pipeline runs the full test suite as a hard gate before deployment (no swallowed failures)
- [ ] The codebase has minimal external dependencies — functionality is hand-written where the alternative is a library that adds transitive dependency risk
- [ ] A developer (human or LLM) can understand where to add a new capability by reading the project structure and extension documentation alone

## Stakeholders

- **Primary user**: Solo developer/operator who interacts with the agent daily and needs confidence that self-modifications won't break things
- **Future self-modification**: The agent itself, which needs predictable patterns to safely add and test new functionality

## Constraints

- **Minimal dependencies**: Prefer writing code over adding libraries. Each new dependency must justify its inclusion against supply-chain risk. Current core deps (httpx, pydantic, rich, prompt-toolkit, fastapi, uvicorn, websockets, jinja2) are the baseline — additions need strong justification.
- **Small-model friendly**: Architecture must be navigable by small local models (7B-class). This means tight isolation, clear file naming, predictable patterns, and minimal cross-module coupling.
- **No framework adoption**: No LangChain, CrewAI, or similar. The value of this project is hand-rolled control.
- **Preserve working functionality**: The agent currently works (chat, tools, deploy, rollback). Restructuring must not break existing capabilities — refactor, don't rewrite from scratch.
- **Python 3.11+, async throughout**: Maintain current runtime requirements.
- **Concourse CI**: All CI/CD stays on the existing Concourse infrastructure.
- **Pause autopilot during restructuring**: The Concourse autopilot job (30-min cycle) must be paused before structural changes begin. An active autopilot could trigger a deploy mid-refactor, breaking the running container. Unpause only after the final validation flight confirms the restructured agent deploys cleanly.

## Environment Requirements

- Local Python 3.11+ with editable install (`pip install -e ".[all-llms,dev]"`)
- Docker and docker-compose for container testing
- Concourse CI instance (concourse-local) for pipeline validation
- Ollama with qwen2.5:7b (or equivalent) for local LLM testing
- ruff for linting and formatting

## Open Questions

- What is the right granularity for module boundaries? (e.g., should `tools/` remain flat or adopt a one-directory-per-tool pattern for complex tools?)

## Resolved Questions

- **Persistence layer**: Filesystem JSON (`~/.the-one/agents/`) with a thin `AgentConfigStore` protocol so SQLite can be swapped later. Minimal deps, human-editable, sufficient for single-user case.
- **Persistence scope**: Agent configs only. Conversation history and tool execution logs are deferred to a future mission.
- **Multi-agent runtime model**: This mission covers agent *definition and instantiation* only. Multi-agent coordination (agents delegating to each other) is a separate future mission.
- **Agent switching in interfaces**: Infrastructure only (factory + config layer). CLI and web UI keep a single default agent for now; full agent-switching UI is a future concern.
- **`agents.md` vs runtime prompts**: `agents.md` is a development-facing static file (like CLAUDE.md) for LLMs working on the codebase. Runtime agent prompts are per-agent config stored in the persistence layer. Sharp separation.
- **`ToolProvider` protocol timing**: Flight 2 (module isolation) includes the protocol stub (interface only) to guide extraction. Flight 3 implements it.

## Known Issues

_(none yet — this is the first mission)_

## Flights

> **Note:** These are tentative suggestions, not commitments. Flights are planned and created one at a time as work progresses. This list will evolve based on discoveries during implementation.

- [x] Flight 1: **Architecture Blueprint** — Define the target module structure, public interfaces, extension points, multi-agent model, persistence strategy, and `agents.md` specification. Resolve all open questions. No code changes — pure design artifact.
- [x] Flight 2: **Core Module Isolation** — Restructure the existing code into the defined module boundaries. Extract clean interfaces, establish module-level exports, and ensure each module is independently importable. Also implements ToolProvider protocol, AgentConfig/AgentFactory/AgentConfigStore stack, and agents.md (absorbing original Flight 3 scope). Verify the agent still works end-to-end (CLI, web, deploy).
- ~~Flight 3: **Plugin & Agent Architecture**~~ — Absorbed into Flight 2. The module isolation naturally required implementing the target architecture's abstractions (ToolProvider, AgentConfig, AgentFactory, AgentConfigStore, tool filtering, agents.md).
- [ ] Flight 3: **Test Infrastructure & CI Hardening** — Unit tests for core modules (agent loop, tool registry, LLM registry, config, factory, store, behaviors), mock LLM for deterministic testing, AIAT conversion, and Concourse pipeline fixes (remove `|| true`, de-hardcode paths, DRY up docker run blocks).
- [ ] Flight 4: **Validation & Hardening** — End-to-end verification: CLI, web, deploy, rollback, autopilot. Fix regressions, clean up dead code, verify all tests pass in pipeline. Unpause autopilot.
