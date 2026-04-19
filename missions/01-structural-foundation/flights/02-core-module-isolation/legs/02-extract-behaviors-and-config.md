# Leg: extract-behaviors-and-config

**Status**: completed
**Flight**: [Core Module Isolation](../flight.md)

## Objective

Extract behavioral constants and tool-call parsing from `core.py` into `agent/behaviors.py`, create `agent/config.py` with `AgentConfig` Pydantic model and `DEFAULT_SYSTEM_PROMPT`, and add `agents_dir` property to Settings.

## Context

- Flight 1 blueprint specifies these extractions in target-architecture.md "What Moves Where" table
- `core.py` is overloaded with the agent loop, system prompt, behavioral constants, and parsing logic
- `AgentConfig` uses Pydantic `BaseModel` per the flight design decision (not `@dataclass`)
- This leg creates the foundation modules that Legs 3-4 depend on

## Inputs

- `the_one/agent/core.py` — source of all symbols to extract
- `the_one/config.py` — needs `agents_dir` property addition
- Design artifacts: `target-architecture.md`, `multi-agent-model.md` (corrected in Leg 1)

## Outputs

- `the_one/agent/behaviors.py` — new file with extracted behavioral symbols
- `the_one/agent/config.py` — new file with AgentConfig and DEFAULT_SYSTEM_PROMPT
- `the_one/agent/core.py` — slimmed, imports from new modules
- `the_one/config.py` — with `agents_dir` property
- `the_one/agent/__init__.py` — updated exports

## Acceptance Criteria

- [x] `the_one/agent/behaviors.py` exists and exports:
  - `DIRECT_ACTIONS` (renamed from `_DIRECT_ACTIONS`, same content)
  - `CONTINUE_SCHEMA` (renamed from `_CONTINUE_SCHEMA`, same content)
  - `extract_tool_calls(text: str, valid_names: set[str]) -> list[ToolCall]` — standalone function (was `_extract_tool_calls` method)
  - `match_direct_action(user_input: str) -> tuple[str, dict] | None` — standalone function (was `_match_direct_action` static method)
- [x] `the_one/agent/config.py` exists and exports:
  - `DEFAULT_SYSTEM_PROMPT` (moved from `core.py` `SYSTEM_PROMPT`, renamed)
  - `AgentConfig` Pydantic BaseModel with 10 fields: `name`, `description`, `llm_provider`, `llm_model`, `llm_base_url`, `system_prompt`, `enabled_tools`, `disabled_tools`, `max_iterations`, `direct_actions`
  - `AgentConfig.is_tool_enabled(tool_name)` method
  - `AgentConfig.get_system_prompt()` method (returns `DEFAULT_SYSTEM_PROMPT` when empty)
- [x] `the_one/agent/core.py` no longer contains: `SYSTEM_PROMPT`, `_DIRECT_ACTIONS`, `_CONTINUE_SCHEMA`, `_extract_tool_calls` method body, `_match_direct_action` method body
- [x] `core.py` imports from `behaviors`: `CONTINUE_SCHEMA`, `extract_tool_calls`, `match_direct_action`. Imports from `config`: `DEFAULT_SYSTEM_PROMPT`. (`DIRECT_ACTIONS` is NOT imported — it's used only internally by `match_direct_action` in `behaviors.py`)
- [x] `core.py` `Agent.__init__` default is `system_prompt: str = DEFAULT_SYSTEM_PROMPT`
- [x] `core.py` `_extract_tool_calls` calls `extract_tool_calls(text, set(self.tools.tool_names) | {"continue"})`
- [x] `core.py` `_match_direct_action` calls `match_direct_action(user_input)`
- [x] `the_one/config.py` Settings has `agents_dir` property returning `self.data_dir / "agents"`
- [x] No circular imports — `python -c "from the_one.agent import Agent"` succeeds
- [x] `ruff check the_one/` is clean

## Verification Steps

- `python -c "from the_one.agent.behaviors import DIRECT_ACTIONS, CONTINUE_SCHEMA, extract_tool_calls, match_direct_action"`
- `python -c "from the_one.agent.config import AgentConfig, DEFAULT_SYSTEM_PROMPT"`
- `python -c "from the_one.agent import Agent"`
- `python -c "from the_one.config import settings; print(settings.agents_dir)"`
- `ruff check the_one/`

## Implementation Guidance

1. **Create `the_one/agent/behaviors.py`**
   - Move `_DIRECT_ACTIONS` from `core.py:13-16` → `DIRECT_ACTIONS` (drop leading underscore)
   - Move `_CONTINUE_SCHEMA` from `core.py:19-36` → `CONTINUE_SCHEMA` (drop leading underscore)
   - Extract `_extract_tool_calls` method (core.py:191-220) → standalone `extract_tool_calls(text: str, valid_names: set[str]) -> list[ToolCall]`
     - Remove `self` parameter
     - Add `valid_names: set[str]` parameter (replaces `set(self.tools.tool_names) | {"continue"}`)
     - Keep all internal logic identical
   - Extract `_match_direct_action` static method (core.py:222-229) → standalone `match_direct_action(user_input: str) -> tuple[str, dict] | None`
     - References `DIRECT_ACTIONS` (now in same module, just use the module-level name)
   - Imports needed: `re`, `json`, `uuid` from stdlib; `ToolCall` from `the_one.llm.base`

2. **Create `the_one/agent/config.py`**
   - Move `SYSTEM_PROMPT` from `core.py:38-94` → `DEFAULT_SYSTEM_PROMPT`
   - Create `AgentConfig(BaseModel)` with 10 fields per multi-agent-model.md
   - Add `is_tool_enabled()` and `get_system_prompt()` methods
   - Imports: `pydantic.BaseModel`, `pydantic.Field`

3. **Slim `the_one/agent/core.py`**
   - Remove lines 11-94 (all constants and prompt)
   - Add imports: `from the_one.agent.behaviors import CONTINUE_SCHEMA, extract_tool_calls, match_direct_action`
   - Add import: `from the_one.agent.config import DEFAULT_SYSTEM_PROMPT`
   - Update `Agent.__init__` default: `system_prompt: str = DEFAULT_SYSTEM_PROMPT`
   - Replace `_tool_schemas` body: use `CONTINUE_SCHEMA` (already imported)
   - Replace `_extract_tool_calls` method body with delegation: `return extract_tool_calls(text, set(self.tools.tool_names) | {"continue"})`
   - Replace `_match_direct_action` static method body with delegation: `return match_direct_action(user_input)`
   - Remove unused imports: `re`, `json`, `uuid` (all three are only used by extracted code)

4. **Add `agents_dir` to Settings in `the_one/config.py`**
   - Add property: `@property` `def agents_dir(self) -> Path: return self.data_dir / "agents"`

5. **Update `the_one/agent/__init__.py`**
   - Keep `Agent` export, no new exports needed yet (AgentConfig, AgentFactory added in Leg 4)

## Edge Cases

- **Import order**: `behaviors.py` imports from `the_one.llm.base` (for `ToolCall`). This is allowed by the dependency flow — `agent/` can import from `llm/`.
- **`json` import in core.py**: Only used in `_extract_tool_calls`. After extraction, remove it.
- **`re` import in core.py**: Only used by `_DIRECT_ACTIONS` and `_extract_tool_calls`. After extraction, remove it.
- **`uuid` import in core.py**: Only used in `_extract_tool_calls`. After extraction, remove it.

## Files Affected

- `the_one/agent/behaviors.py` — Create
- `the_one/agent/config.py` — Create
- `the_one/agent/core.py` — Modify (slim down)
- `the_one/config.py` — Modify (add `agents_dir`)
- `the_one/agent/__init__.py` — Verify (no changes needed yet)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [ ] If final leg of flight:
  - [ ] Update flight.md status to `landed`
  - [ ] Check off flight in mission.md
- [x] Commit all changes together (code + artifacts)
