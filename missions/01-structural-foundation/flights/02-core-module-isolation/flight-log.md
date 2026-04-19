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

### Leg 2: extract-behaviors-and-config (completed)

**Started**: 2026-04-18

Changes applied:

1. **the_one/agent/behaviors.py** — Created. Extracted `DIRECT_ACTIONS` (renamed from `_DIRECT_ACTIONS`), `CONTINUE_SCHEMA` (renamed from `_CONTINUE_SCHEMA`), `extract_tool_calls()` standalone function (was `_extract_tool_calls` method), `match_direct_action()` standalone function (was `_match_direct_action` static method). Imports `ToolCall` from `the_one.llm.base`.
2. **the_one/agent/config.py** — Created. Contains `DEFAULT_SYSTEM_PROMPT` (moved from `core.py` `SYSTEM_PROMPT`), `AgentConfig` Pydantic BaseModel with 10 fields per multi-agent-model.md design, including `is_tool_enabled()` and `get_system_prompt()` methods.
3. **the_one/agent/core.py** — Slimmed. Removed `SYSTEM_PROMPT`, `_DIRECT_ACTIONS`, `_CONTINUE_SCHEMA`, inline `_extract_tool_calls` logic, inline `_match_direct_action` logic, and unused `json`/`re`/`uuid` imports. Added imports from `behaviors` and `config`. `_extract_tool_calls` and `_match_direct_action` now delegate to standalone functions.
4. **the_one/config.py** — Added `agents_dir` property to `Settings` returning `self.data_dir / "agents"`.
5. **the_one/agent/__init__.py** — Verified, no changes needed (exports `Agent` only).
6. Fixed line-length lint issue in `behaviors.py` DIRECT_ACTIONS pattern (reformatted multi-line).

Verification: All 4 import checks pass. Ruff clean on all modified files (45 pre-existing errors in other files remain untouched).

---

## Decisions

---

## Deviations

---

## Anomalies

---

## Session Notes
