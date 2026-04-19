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

### Leg 02: test-registries-and-store — COMPLETE

- Created `tests/test_tool_registry.py` — 8 tests covering ToolRegistry (register, get, get unknown KeyError, all_schemas, tool_names, empty registry, duplicate overwrite) and Tool.to_schema() output format
- Created `tests/test_llm_registry.py` — 3 tests covering register_provider/get_provider round-trip, unknown provider ValueError, and ollama lazy loading; uses monkeypatch autouse fixture to isolate `_providers` state
- Created `tests/test_store.py` — 10 tests covering FilesystemConfigStore save/load round-trip, parent dir creation, overwrite, list_agents sorted, exists true/false, delete, delete nonexistent KeyError, load nonexistent KeyError, malformed JSON (JSONDecodeError), wrong-shape JSON (ValidationError)
- Created `tests/test_builtins.py` — 4 tests covering BuiltinToolProvider name, tool count (14), ToolProvider protocol compliance via isinstance, and required attribute presence on all tools
- **27 new tests, 59 total passing**, ruff clean

---

## Decisions

---

## Deviations

---

## Anomalies

---

## Session Notes
