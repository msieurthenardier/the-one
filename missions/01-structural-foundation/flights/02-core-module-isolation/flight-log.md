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

### Leg 3: tool-provider-and-decoupling (completed)

**Started**: 2026-04-18

Changes applied:

1. **the_one/tools/provider.py** — Created. `ToolProvider` as `@runtime_checkable` Protocol with `name` property and `get_tools() -> list[Tool]` method.
2. **the_one/tools/builtins.py** — Created. `BuiltinToolProvider` with `name` property returning `"builtin"` and `get_tools()` lazy-importing and instantiating all 14 built-in tools.
3. **the_one/tools/base.py** — Removed `load_defaults()` method from `ToolRegistry` (lines 46-76 deleted).
4. **the_one/tools/memory.py** — Removed module-level `MEMORY_DIR` binding. Added `__init__` with `memory_dir: Path | None = None` defaulting to `settings.workspace_dir / ".memory"`. All 7 internal references replaced with `self.memory_dir`.
5. **the_one/tools/self_deploy.py** — Added `__init__` with `workspace_dir`, `concourse_target`, `concourse_pipeline` params defaulting from settings. `execute()` uses `self.*` instead of direct settings access. Removed unused `json` import.
6. **the_one/tools/__init__.py** — Added `ToolProvider` to imports and `__all__`.
7. **the_one/interfaces/cli.py** — `_make_agent()` now uses `BuiltinToolProvider().get_tools()` loop instead of `tools.load_defaults()`.
8. **the_one/interfaces/web/app.py** — Same `BuiltinToolProvider` replacement. Ruff auto-fixed unused `Message` import and `pathlib` import ordering.

Verification: All 7 verification commands pass. `BuiltinToolProvider` returns 14 tools, satisfies `isinstance(b, ToolProvider)` check. Agent import OK. Ruff clean on all modified/new files (pre-existing E501 errors in cli.py and web/app.py remain untouched).

### Leg 4: agent-store-and-factory (completed)

**Started**: 2026-04-18

Changes applied:

1. **the_one/agent/store.py** — Created. `AgentConfigStore` as `@runtime_checkable` Protocol with 5 methods (`list_agents`, `load`, `save`, `delete`, `exists`). `FilesystemConfigStore` implementation using `model_validate()` for load and `model_dump()` for save, JSON storage in `agents_dir`.
2. **the_one/agent/factory.py** — Created. `AgentFactory` with `create()`, `list_agents()`, `_load_config()`, `_default_config()`. Always passes `base_url` unconditionally to `get_provider()`. Calls `settings.ensure_dirs()` in `create()`. Default config synthesized from settings including `llm_base_url`.
3. **the_one/interfaces/cli.py** — Removed `_make_agent()` function. Replaced with `AgentFactory().create()` in `_run_cli()`. Removed unused imports (`get_provider`, `ToolRegistry`, `BuiltinToolProvider`, `Agent`). Added `AgentFactory` import.
4. **the_one/interfaces/web/app.py** — Removed `_make_agent()` function. Added module-level `_factory = AgentFactory()`. Replaced usage in `_get_session()` and `selftest()` endpoint with `_factory.create()`. Removed unused imports (`get_provider`, `ToolRegistry`, `BuiltinToolProvider`). Retained `Agent` import for `Session` type annotation.
5. **the_one/agent/__init__.py** — Updated exports to include `Agent`, `AgentConfig`, `AgentFactory` in `__all__`.

Verification: Store imports OK. Factory creates agent with 14 tools and correct system prompt. All 3 exports from `the_one.agent` succeed. Ruff clean on all new/modified files (pre-existing E501 errors in cli.py and web/app.py remain untouched).

### Leg 5: update-docs (completed)

**Started**: 2026-04-18

Changes applied:

1. **CLAUDE.md** — Updated architecture section:
   - Tool layer: replaced `load_defaults()` reference with `BuiltinToolProvider` and `ToolProvider` protocol description.
   - Agent loop: noted that behavioral constants and helpers (`match_direct_action()`, `extract_tool_calls()`, `CONTINUE_SCHEMA`) live in `behaviors.py`.
   - Added new paragraph describing `AgentConfig` (Pydantic model), `AgentFactory`, and `AgentConfigStore`.
   - Interfaces: updated to say both use `AgentFactory.create()` instead of creating agents directly.
   - Added `agents.md` reference: "For architecture internals, see `the_one/agents.md`".
   - Configuration: added `agents_dir` property mention.
2. **the_one/agents.md** — Verified and fixed discrepancies:
   - `config.py` entry: changed "dataclass" to "Pydantic model" (line 49).
   - `behaviors.py` entry: added `match_direct_action()` to exports list (line 52).
   - Verified module map matches actual file exports (all accurate).
   - Verified dependency graph matches actual import structure (all accurate).
   - Verified key patterns descriptions match actual behavior (all accurate).

Verification: `ruff check the_one/` shows 36 pre-existing errors only — no new issues from docs changes.

---

## Decisions

---

## Deviations

---

## Anomalies

---

## Session Notes
