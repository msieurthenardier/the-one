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

### Leg 03: test-factory-and-agent-loop — COMPLETE

- Created `tests/test_factory.py` — 7 tests covering AgentFactory: default agent creation with tools and system prompt, named agent from stored config, unknown agent KeyError, disabled_tools exclusion, enabled_tools whitelist, list_agents includes "default", list_agents includes stored agents. Uses patched `settings` and `get_provider` to isolate from real LLM/filesystem.
- Created `tests/test_agent.py` — 8 tests covering Agent.step() loop: normal text-only response, tool call execution with result yielded, direct action bypass ("restart yourself" without LLM), continue signal not yielded to caller but present in internal messages, max_iterations enforcement (stops after 2), tool exception yields is_error=True ToolResult, text-embedded JSON tool call extraction and execution, and reset() clearing messages to system prompt only.
- Used `StubToolProvider` implementing ToolProvider protocol for factory tests; `ErrorTool` subclass for error path testing
- All design review notes applied: patched `the_one.agent.factory.get_provider` and `the_one.agent.factory.settings`, fresh ToolRegistry per test, async `for msg in agent.step()` collection, exact FakeLLM response counts
- **17 new tests, 76 total passing**, ruff clean

### Leg 04: aiat-conversion — COMPLETE

- Deleted `tests/iaat.py` (standalone script using `requests` with custom test runner)
- Created `tests/test_aiat.py` — 8 AIAT tests converted to pytest with `@pytest.mark.live` decorator: health, basic_chat, tool_use_file_read, git_status, reset, run_tests, self_awareness, multi_step
- Uses `httpx` instead of `requests` (already a project dependency)
- Pytest fixtures for `base_url` (from `THE_ONE_TEST_URL` env var, default `http://localhost:8484`) and `session_id` (unique per test)
- Helper functions preserved as module-level: `chat()`, `reset()`, `assistant_text()`, `has_tool_call()`, `has_tool_result()`
- Added `addopts = "-m 'not live'"` to `pyproject.toml` `[tool.pytest.ini_options]` to exclude AIAT tests from default `pytest tests/` runs
- **76 unit tests still passing**, AIAT tests correctly excluded by default, ruff clean

---

## Decisions

---

## Deviations

---

## Anomalies

---

## Session Notes
