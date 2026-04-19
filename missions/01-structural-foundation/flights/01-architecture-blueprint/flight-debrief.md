# Flight Debrief: Architecture Blueprint

**Date**: 2026-04-18
**Flight**: [Architecture Blueprint](flight.md)
**Status**: landed
**Duration**: 2026-04-18 (single session)
**Legs Completed**: 4 of 4

## Outcome Assessment

### Objectives Achieved

The flight produced a complete architectural blueprint for restructuring the-one from a vibe-coded prototype into a structured multi-agent platform. Four design documents and one source file were created:

- **target-architecture.md** — current-state baseline, target directory layout, module boundaries, dependency flow, symbol migration map, decoupling plan, CLAUDE.md reconciliation plan
- **multi-agent-model.md** — AgentConfig dataclass, JSON schema, AgentConfigStore protocol, FilesystemConfigStore, AgentFactory design
- **plugin-protocol.md** — ToolProvider protocol, BuiltinToolProvider, per-agent tool filtering, MCP integration surface
- **extension-guide.md** — 4 step-by-step recipes for extending the system
- **agents.md** — development-facing architecture reference (in source tree)

The artifacts are internally consistent and cross-reference each other coherently. The blueprint is sufficient to guide Flight 2 implementation with three caveats noted below.

### Mission Criteria Advanced

This flight advances all 8 flight-contributing criteria via design specification:

- [x] Each architectural concern lives in a clearly bounded module with explicit public interfaces — **designed** in target-architecture.md
- [x] New functionality can be added by creating files in designated locations — **documented** in extension-guide.md
- [x] Tool system supports registry-based management with per-agent enable/disable — **designed** in plugin-protocol.md
- [x] Plugin architecture supports built-in tools and future MCP integrations via ToolProvider — **designed** in plugin-protocol.md
- [x] Architecture supports multiple agent definitions with own prompt/tools/provider — **designed** in multi-agent-model.md
- [x] agents.md provides development-facing self-awareness context — **created** at the_one/agents.md
- [x] Extension model documented with clear patterns — **documented** in extension-guide.md
- [x] Developer can understand where to add capabilities from project structure alone — **validated** by extension guide recipes

These criteria are "designed" not "implemented" — implementation is Flights 2-5.

## What Went Well

1. **Current-state baseline accuracy.** The baseline in target-architecture.md was verified against the actual codebase by both developer and architect reviewers. Directory layout, coupling points, and symbol locations are accurate.

2. **Design is implementation-ready.** The artifacts include concrete code snippets with correct types, imports, and method signatures. An agent executing Flight 2 can follow them without additional design decisions (with the three caveats below).

3. **Consistent vocabulary across documents.** All four design docs plus agents.md use identical naming (`AgentConfig`, `AgentFactory`, `ToolProvider`, `BuiltinToolProvider`) with consistent semantics.

4. **Clean concern separation in leg structure.** The four legs mapped naturally to four architectural concerns: structure, persistence/factory, tool loading, and documentation. Each built on the prior.

5. **Module granularity decision was well-reasoned.** Flat tools with a ~200 line threshold for extraction is proportionate. The decision was made with rationale, not deferred.

## What Could Be Improved

### Process

- **No review cycle.** All four legs completed in a single session. The design didn't benefit from a "sleep on it" review pass. For design-only flights, consider splitting across two sessions with a review gate between.
- **Leg acceptance criteria left unchecked.** The leg specs have `- [ ]` acceptance criteria that were never checked off in the spec files themselves. Consider a convention: either check them off or note that verification happens at debrief.

### Technical

Three issues identified that require attention before Flight 2:

1. **`self_deploy.py` coupling overstated.** target-architecture.md describes it as having "module-level settings references" with an "import-time binding problem." In reality, `self_deploy.py` accesses `settings.workspace_dir`, `settings.concourse_target`, and `settings.concourse_pipeline` inside `execute()` at call time — not at import time. Only `memory.py` has the genuine module-level binding problem (`MEMORY_DIR = settings.workspace_dir / ".memory"` at line 11). The proposed constructor injection fix is still correct (for testability and per-agent configuration), but the urgency and framing should be corrected. Flight 2 implementers should verify each coupling point against the actual code before restructuring.

2. **`llm_base_url` default omission will break Ollama.** The current `_make_agent()` in both `cli.py` and `web/app.py` always passes `base_url=settings.llm_base_url` to `get_provider()`. The factory's `_default_config()` does not set `llm_base_url`, so the Ollama provider would receive no `base_url` and fall back to its constructor default. If the constructor default differs from `settings.llm_base_url`, this is a silent regression. **Fix**: `_default_config()` should include `llm_base_url=settings.llm_base_url`.

3. **`extract_tool_calls` interface change unspecified.** The function currently accesses `self.tools.tool_names` to validate extracted tool names. When extracted to `behaviors.py` as a standalone function, it needs a `valid_names: set[str]` parameter. The design documents don't address this explicitly. It is straightforward to resolve, but Flight 2 should specify the new signature.

### Documentation

- **`agents.md` vs `CLAUDE.md` boundary undocumented.** No artifact explains the relationship between these two developer-facing documents. The extension guide mentions CLAUDE.md in passing but doesn't clarify scope boundaries.
- **Hybrid typing pattern undocumented.** `ToolProvider` uses Protocol (structural typing) while `Tool` and `LLMProvider` use ABC (nominal typing). The rationale is in plugin-protocol.md but not in agents.md where developers will look for pattern guidance.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| None — flight executed exactly as planned | N/A | N/A |

## Key Learnings

1. **Design-only flights work well for architectural restructuring.** Producing the blueprint before any code changes creates a shared reference that prevents architectural drift. The four-document structure (architecture, model, protocol, guide) is a natural decomposition for this kind of work.

2. **Current-state baselines catch mischaracterizations early.** The baseline surfaced that `self_deploy.py` coupling is less severe than assumed. Without the baseline, this would have been discovered during implementation, potentially wasting effort on a non-problem.

3. **Code snippets in design docs should be self-contained.** The `AgentConfig` snippet references `DEFAULT_SYSTEM_PROMPT` which is defined elsewhere. The `FilesystemConfigStore.save()` snippet's selective serialization logic has a subtle edge case. Code in design docs should either be complete or explicitly note "see [X] for full context."

## Recommendations

1. **Before Flight 2: patch the three technical issues above** in the design artifacts. Correct `self_deploy.py` characterization, add `llm_base_url` to default config, specify `extract_tool_calls` new signature. These are small edits to existing artifacts, not new design work.

2. **Consider Pydantic for AgentConfig.** Both reviewers noted that plain dataclass + manual `**data` unpacking provides no validation. Pydantic is already a dependency (for Settings). Using it for AgentConfig would give automatic JSON schema generation, field validation, and clear error messages for invalid configs — with zero new dependencies.

3. **Add an end-to-end verification checkpoint to Flight 2.** The restructuring must prove the agent still works (CLI chat, web chat, deploy). This should be an explicit checkpoint, not an afterthought.

4. **Document the agents.md/CLAUDE.md boundary.** Add a one-line scope note to both files: "For architecture internals, see agents.md" in CLAUDE.md and "For usage and commands, see CLAUDE.md" in agents.md.

5. **Standardize constructor injection with settings defaults.** The pattern `def __init__(self, x=None): self.x = x or settings.whatever` should be the canonical approach for any module that needs settings access. Never bind at module level.

## Skill Effectiveness

### Mission Skill
The mission provided strong context. Success criteria were clear and measurable. The resolved questions section prevented re-litigating decisions during the flight.

### Flight Skill
The flight structure worked well for a design-only flight. The checkpoints mapped cleanly to deliverables. The only gap: the post-flight checklist should distinguish "reviewed" (human confirms) from "completed" (mechanically verifiable).

### Leg Skill
Leg specs were clear and sufficient. Acceptance criteria were verifiable. One improvement: for design legs, acceptance criteria should explicitly include "cross-reference consistency with prior leg artifacts."

## Action Items

- [x] Correct `self_deploy.py` coupling characterization in target-architecture.md before Flight 2
- [x] Add `llm_base_url=settings.llm_base_url` to AgentFactory._default_config() in multi-agent-model.md
- [x] Specify `extract_tool_calls(text, valid_names)` signature in target-architecture.md
- [ ] Add scope boundary notes to agents.md and CLAUDE.md (can be done in Flight 2)
- [x] Consider Pydantic for AgentConfig during Flight 2 planning — adopted; AgentConfig updated to Pydantic BaseModel in multi-agent-model.md
