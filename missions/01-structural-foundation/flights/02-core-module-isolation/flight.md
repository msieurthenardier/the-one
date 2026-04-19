# Flight: Core Module Isolation

**Status**: in-flight
**Mission**: [Structural Foundation](../../mission.md)

## Contributing to Criteria

- [ ] Each architectural concern lives in a clearly bounded module with explicit public interfaces
- [ ] New functionality can be added by creating files in designated locations without modifying core agent code
- [ ] The tool system supports registry-based management with runtime enable/disable per agent
- [ ] The plugin architecture supports both built-in tools and future MCP client integrations through a unified `ToolProvider` protocol
- [ ] The architecture supports multiple agent definitions, each with their own prompt, tool set, LLM provider, and configuration
- [ ] A developer (human or LLM) can understand where to add a new capability by reading the project structure and extension documentation alone

---

## Pre-Flight

### Objective

Restructure the existing codebase into the module boundaries defined by the Flight 1 Architecture Blueprint. Extract clean interfaces, create the AgentConfig/AgentFactory/AgentConfigStore stack, implement the ToolProvider protocol, and decouple settings from tools. Verify the agent still works end-to-end (CLI, web) after restructuring.

### Open Questions

- [x] Design artifact corrections → first leg patches the 3 debrief items
- [x] Verification approach → guided UAT leg at the end
- [x] Branch strategy → main; agentic workflow creates its own branch

### Design Decisions

**Incorporate debrief corrections before implementing**: The Flight 1 debrief identified 3 issues in the design artifacts. These are patched first so implementation follows corrected blueprints.
- Rationale: Implementation agents read the design artifacts — they must be accurate
- Trade-off: One extra leg, but prevents propagating errors

**Pydantic for AgentConfig**: Use a Pydantic model instead of plain dataclass for AgentConfig. Pydantic is already a dependency (for Settings), and it provides field validation, clear error messages for malformed JSON, and `model_validate()` for deserialization.
- Rationale: Debrief recommendation #2. Plain dataclass with `**data` gives no validation on load. A typo in a JSON config would be silently ignored or raise an opaque TypeError.
- Trade-off: Slightly heavier than a dataclass, but zero new dependencies

**Guided UAT as final gate**: An interactive UAT leg verifies CLI chat, web chat, tool execution, and factory behavior before the flight is marked landed.
- Rationale: Restructuring is high-risk for silent regressions. Automated tests may miss wiring issues.
- Trade-off: Requires human presence

**Always pass `base_url` to `get_provider()` in the factory**: Match current `_make_agent()` behavior exactly — always pass `base_url` even when it's the default. Providers that don't use it ignore it via `**kwargs`.
- Rationale: Architect review caught that conditionally passing `base_url` changes behavior for Ollama. Current code always passes it.
- Trade-off: None — consistent with existing behavior

**`Agent.__init__` keeps a default system prompt**: After extraction, `Agent.__init__` defaults to `DEFAULT_SYSTEM_PROMPT` from `agent/config.py`. The factory always passes explicitly, but direct construction still works for tests and simple usage.
- Rationale: Preserves backward compatibility for anyone constructing `Agent` directly
- Trade-off: None

### Prerequisites

- [x] Flight 1 (Architecture Blueprint) completed
- [x] Design artifacts exist: target-architecture.md, multi-agent-model.md, plugin-protocol.md, extension-guide.md
- [x] Current agent works (baseline for regression testing)
- [ ] Concourse autopilot paused before merging structural changes to main

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

Follow the Flight 1 blueprint to restructure the codebase. The work is primarily mechanical — extracting symbols from existing files into new modules, creating new abstractions (AgentConfig, AgentFactory, ToolProvider), and updating import paths. No behavioral changes to the agent loop.

The restructuring preserves all existing functionality:
- Same 14 tools, same 3 LLM providers, same agent loop behavior
- Same CLI and web interfaces (only internal wiring changes)
- Same configuration via `THE_ONE_*` env vars

Key ordering constraint: new modules must exist before dependents can import from them. Legs are sequenced accordingly — foundations first (behaviors, config), then abstractions (provider, factory), then consumers (interfaces).

### Reference Documents

All implementation follows these Flight 1 artifacts:
- `flights/01-architecture-blueprint/target-architecture.md` — directory layout, module boundaries, dependency flow, symbol migration map
- `flights/01-architecture-blueprint/multi-agent-model.md` — AgentConfig, AgentConfigStore, AgentFactory
- `flights/01-architecture-blueprint/plugin-protocol.md` — ToolProvider, BuiltinToolProvider, per-agent filtering
- `flights/01-architecture-blueprint/extension-guide.md` — verification that extension recipes work against new structure

### Checkpoints

- [x] Design artifact corrections applied
- [x] `agent/behaviors.py` exists with DIRECT_ACTIONS, CONTINUE_SCHEMA, extract_tool_calls, match_direct_action; `core.py` slimmed
- [x] `agent/config.py` exists with AgentConfig and DEFAULT_SYSTEM_PROMPT
- [x] `tools/provider.py` and `tools/builtins.py` exist; `load_defaults()` removed
- [x] `memory.py` and `self_deploy.py` decoupled from module-level settings
- [x] `agent/store.py` and `agent/factory.py` exist; `_make_agent()` replaced in both interfaces
- [x] `config.py` has `agents_dir` property
- [ ] CLAUDE.md updated to reflect new structure
- [ ] `agents.md` verified against actual implementation
- [ ] All tests pass, lint clean
- [ ] UAT confirms CLI chat, web chat, and tool execution work

### Adaptation Criteria

**Divert if**:
- Circular import discovered that can't be resolved by the dependency flow in target-architecture.md
- Restructuring breaks a tool or provider in a way that requires redesigning the interface

**Acceptable variations**:
- Minor naming adjustments if the blueprint names conflict with Python builtins or conventions
- Additional helper methods on AgentConfig or AgentFactory if needed for clean implementation
- `__init__.py` export lists may differ slightly from blueprint

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `patch-design-artifacts` — Fix 3 debrief action items in Flight 1 design artifacts: correct self_deploy.py coupling characterization, add llm_base_url to default config, specify extract_tool_calls standalone signature.
- [x] `extract-behaviors-and-config` — Create `agent/behaviors.py` (DIRECT_ACTIONS, CONTINUE_SCHEMA, extract_tool_calls with valid_names param, match_direct_action). Update `core.py` to import from behaviors.py and call `extract_tool_calls(text, set(self.tools.tool_names) | {"continue"})`. Create `agent/config.py` (AgentConfig Pydantic model, DEFAULT_SYSTEM_PROMPT). Update `Agent.__init__` default to `DEFAULT_SYSTEM_PROMPT`. Add `agents_dir` property to Settings.
- [x] `tool-provider-and-decoupling` — Create `tools/provider.py` (ToolProvider protocol) and `tools/builtins.py` (BuiltinToolProvider). Decouple `memory.py` (constructor injection for memory_dir) and `self_deploy.py` (constructor injection for workspace/concourse settings). Remove `load_defaults()` from ToolRegistry. Update `tools/__init__.py`.
- [x] `agent-store-and-factory` — Create `agent/store.py` (AgentConfigStore protocol, FilesystemConfigStore using `model_validate()`) and `agent/factory.py` (AgentFactory — always passes `base_url` to `get_provider()`). Replace `_make_agent()` in `cli.py` and `web/app.py` with `AgentFactory.create()`. Update `agent/__init__.py`.
- [ ] `update-docs` — Update CLAUDE.md architecture section to reflect new module structure. Verify `agents.md` accuracy against actual implementation, fix any discrepancies.
- [ ] `uat-and-alignment` *(optional)* — Guided UAT session: verify CLI chat, web server, tool execution, and factory behavior. Walk through extension guide recipes against actual code. Fix issues iteratively until satisfied.

---

## Post-Flight

### Completion Checklist

- [ ] All legs completed
- [ ] Tests passing (`python -m pytest tests/ --tb=short -q`)
- [ ] Lint clean (`ruff check the_one/ tests/`)
- [ ] No behavioral regressions (UAT verified)
- [ ] Documentation updated (CLAUDE.md, agents.md)
- [ ] All new files have appropriate `__init__.py` exports

### Verification

The flight is verified when:
- The agent produces identical behavior to pre-restructure baseline (same tools, same LLM providers, same responses)
- `AgentFactory().create()` produces an Agent equivalent to the old `_make_agent()`
- `BuiltinToolProvider().get_tools()` returns the same 14 tools as `load_defaults()`
- `AgentConfig` validates and rejects malformed agent JSON files with clear errors
- A developer can follow the extension guide recipes against the restructured codebase
- No circular imports exist
