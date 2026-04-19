# Flight Log: Test Infrastructure & CI Hardening

**Flight**: [Test Infrastructure & CI Hardening](flight.md)

## Summary

_(In progress)_

---

## Leg Progress

### Leg 01: test-fixtures-and-behaviors — COMPLETE

- Created `tests/conftest.py` with `FakeLLM(LLMProvider)`, `StubTool(Tool)`, and `make_registry` fixture
- Created `tests/test_behaviors.py` — 20 tests covering `extract_tool_calls()`, `match_direct_action()`, `DIRECT_ACTIONS`, and `CONTINUE_SCHEMA`
- Created `tests/test_config.py` — 12 tests covering `AgentConfig` construction, `is_tool_enabled()`, `get_system_prompt()`, and `DEFAULT_SYSTEM_PROMPT`
- Deleted `tests/test_example.py` (placeholder)
- Added `[tool.pytest.ini_options]` to `pyproject.toml` with `asyncio_mode = "auto"` and `live` marker registration
- **32 tests passing**, ruff clean
- **Key finding**: `extract_tool_calls()` regex cannot match dict arguments at all (even flat `{"x": 1}`), not just nested ones — the `[^}]+` in the pattern consumes up to the first `}` which is the inner closing brace, producing invalid JSON. Only string arguments work. Tests document this limitation.

---

## Decisions

---

## Deviations

---

## Anomalies

---

## Session Notes
