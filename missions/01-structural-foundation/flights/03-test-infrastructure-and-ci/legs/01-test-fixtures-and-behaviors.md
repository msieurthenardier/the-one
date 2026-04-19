# Leg: test-fixtures-and-behaviors

**Status**: completed
**Flight**: [Test Infrastructure & CI Hardening](../flight.md)

## Objective

Create shared test infrastructure (`conftest.py` with FakeLLM, StubTool, fixtures, markers) and unit tests for `behaviors.py` and `config.py`.

## Context

- Flight 2 completed — all modules exist and are functional
- FakeLLM design decision: minimal class with list of pre-scripted responses, no mock library
- `pytest-asyncio` added to dev dependencies for async test support
- `live` marker needed for AIAT tests (Leg 4) — register it now in conftest

## Inputs

- `the_one/agent/behaviors.py` — `extract_tool_calls()`, `match_direct_action()`, `DIRECT_ACTIONS`, `CONTINUE_SCHEMA`
- `the_one/agent/config.py` — `AgentConfig`, `DEFAULT_SYSTEM_PROMPT`
- `the_one/llm/base.py` — `LLMProvider`, `Message`, `ToolCall`, `ToolResult` (for FakeLLM base class)
- `the_one/tools/base.py` — `Tool` (for StubTool base class)

## Outputs

- `tests/conftest.py` — FakeLLM, StubTool, make_registry fixture, live marker, asyncio_mode config
- `tests/test_behaviors.py` — Unit tests for behaviors module
- `tests/test_config.py` — Unit tests for config module
- `tests/test_example.py` — Deleted (placeholder replaced by real tests)

## Acceptance Criteria

- [x] `FakeLLM(LLMProvider)` exists in conftest, takes list of `Message` responses, returns them in sequence from `complete()`
- [x] `StubTool(Tool)` exists in conftest, records calls and returns canned response
- [x] `make_registry()` fixture creates a `ToolRegistry` with StubTools
- [x] `live` marker registered for AIAT tests
- [x] `asyncio_mode = "auto"` configured
- [x] `test_behaviors.py` tests `extract_tool_calls()`: valid JSON, invalid JSON, unknown tool names, string arguments, nested arguments, no matches, multiple calls
- [x] `test_behaviors.py` tests `match_direct_action()`: restart patterns, rollback patterns, case insensitivity, non-matching input, "please" prefix
- [x] `test_behaviors.py` validates `DIRECT_ACTIONS` and `CONTINUE_SCHEMA` structure
- [x] `test_config.py` tests `AgentConfig` construction with defaults and all fields
- [x] `test_config.py` tests `is_tool_enabled()`: no filters, whitelist only, blacklist only, both, edge cases
- [x] `test_config.py` tests `get_system_prompt()`: empty returns DEFAULT, custom prompt returned as-is
- [x] `test_config.py` validates `DEFAULT_SYSTEM_PROMPT` is non-empty string
- [x] `tests/test_example.py` deleted
- [x] `pytest tests/test_behaviors.py tests/test_config.py -q` passes
- [x] `ruff check tests/` clean

## Verification Steps

- `python3 -m pytest tests/test_behaviors.py tests/test_config.py --tb=short -q` — all pass
- `ruff check tests/` — no errors
- `python3 -c "from tests.conftest import FakeLLM, StubTool"` — imports work

## Implementation Guidance

1. **Delete `tests/test_example.py`** — placeholder file, no longer needed

2. **Create `tests/conftest.py`**
   - Import `LLMProvider`, `Message`, `Tool`, `ToolRegistry` from the_one
   - `FakeLLM(LLMProvider)`: `__init__(self, responses: list[Message])`, `name = "fake"`, `async def complete(...)` pops from list
   - `StubTool(Tool)`: `name`, `description`, `parameters` attrs, `async def execute(...)` records call in `self.calls` list, returns `"stub: {name}"`
   - `make_registry` fixture: creates ToolRegistry with 2-3 StubTools (e.g., "tool_a", "tool_b")
   - Register `live` marker via `pytest_configure`
   - Set `asyncio_mode = "auto"` via pytest ini

3. **Create `tests/test_behaviors.py`**
   - Test `extract_tool_calls()` with various inputs against a known `valid_names` set
   - Test `match_direct_action()` with various user inputs
   - Validate structure of `DIRECT_ACTIONS` list and `CONTINUE_SCHEMA` dict

4. **Create `tests/test_config.py`**
   - Test `AgentConfig` model construction and field defaults
   - Test `is_tool_enabled()` logic paths
   - Test `get_system_prompt()` fallback behavior

## Edge Cases

- **FakeLLM exhaustion**: If `complete()` is called more times than responses provided, raise `IndexError` — this is intentional, tests should provide enough responses
- **extract_tool_calls with malformed JSON**: Should skip silently (existing behavior)
- **AgentConfig with both enabled_tools and disabled_tools**: disabled_tools should take precedence

## Files Affected

- `tests/test_example.py` — Delete
- `tests/conftest.py` — Create
- `tests/test_behaviors.py` — Create
- `tests/test_config.py` — Create

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing (32 passed in 0.11s)
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] Commit all changes together (code + artifacts)
