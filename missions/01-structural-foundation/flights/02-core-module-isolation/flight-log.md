# Flight Log: Core Module Isolation

**Flight**: [Core Module Isolation](flight.md)

## Summary

Flight 2 in progress. Design artifact patches applied in Leg 1.

---

## Leg Progress

### Leg 1: patch-design-artifacts (completed)

**Started**: 2026-04-18

Changes applied:

1. **target-architecture.md** — Corrected `self_deploy.py` coupling characterization from "module-level settings references" / "import-time binding problem" to "accesses settings inside `execute()` at call time". Updated both the Coupling Points section (item 4), the directory layout comment, and the Tools Requiring Decoupling subsection. Constructor injection rationale reframed to focus on testability and per-agent configuration.
2. **target-architecture.md** — Added `_extract_tool_calls()` to "What Moves Where" table with full signature: `extract_tool_calls(text: str, valid_names: set[str]) -> list[ToolCall]`, plus call site note showing `set(self.tools.tool_names) | {"continue"}`.
3. **target-architecture.md** — Added `_match_direct_action()` to "What Moves Where" table with target signature: `match_direct_action(user_input: str) -> tuple[str, dict] | None`.
4. **multi-agent-model.md** — Updated `AgentConfig` from `@dataclass` to Pydantic `BaseModel` (`from pydantic import BaseModel, Field`, `disabled_tools` uses `Field(default_factory=list)`).
5. **multi-agent-model.md** — Added `llm_base_url=settings.llm_base_url` to `_default_config()` snippet.
6. **multi-agent-model.md** — Changed `AgentConfig(**data)` to `AgentConfig.model_validate(data)` in `FilesystemConfigStore.load()`.
7. **flight-debrief.md** — Checked off action items 1-3 (items 4-5 deferred to later legs).

---

## Decisions

---

## Deviations

---

## Anomalies

---

## Session Notes
