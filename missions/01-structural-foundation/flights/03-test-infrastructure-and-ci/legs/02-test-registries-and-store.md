# Leg: test-registries-and-store

**Status**: completed
**Flight**: [Test Infrastructure & CI Hardening](../flight.md)

## Objective

Add unit tests for ToolRegistry, LLM registry, FilesystemConfigStore, and BuiltinToolProvider.

## Context

- Leg 1 complete — conftest.py with FakeLLM, StubTool, make_registry fixture available
- All target modules exist and are functional from Flight 2
- Tests should be pure-logic or filesystem-only (no LLM, no Docker, no network)

## Inputs

- `the_one/tools/base.py` — `Tool`, `ToolRegistry` (register, get, all_schemas, tool_names)
- `the_one/llm/registry.py` — `register_provider()`, `get_provider()`, `_try_load_builtin()`
- `the_one/agent/store.py` — `FilesystemConfigStore` (list_agents, load, save, delete, exists)
- `the_one/tools/builtins.py` — `BuiltinToolProvider` (get_tools, name)
- `the_one/tools/provider.py` — `ToolProvider` protocol
- `tests/conftest.py` — StubTool fixture available

## Outputs

- `tests/test_tool_registry.py` — ToolRegistry and Tool.to_schema() tests
- `tests/test_llm_registry.py` — LLM registry tests
- `tests/test_store.py` — FilesystemConfigStore tests
- `tests/test_builtins.py` — BuiltinToolProvider tests

## Acceptance Criteria

- [x] `test_tool_registry.py` tests: register, get, get unknown (KeyError), all_schemas output, tool_names list
- [x] `test_tool_registry.py` tests `Tool.to_schema()` output format (name, description, parameters keys)
- [x] `test_llm_registry.py` tests: register_provider, get_provider with registered provider
- [x] `test_llm_registry.py` tests: get_provider unknown (ValueError), lazy loading of ollama
- [x] `test_store.py` tests: save + load round-trip, list_agents, exists, delete, delete nonexistent (KeyError), load nonexistent (KeyError), invalid JSON handling
- [x] `test_store.py` uses `tmp_path` fixture for isolated filesystem
- [x] `test_builtins.py` tests: get_tools() returns 14 tools, name returns "builtin"
- [x] `test_builtins.py` tests: isinstance(BuiltinToolProvider(), ToolProvider) is True
- [x] `test_builtins.py` tests: all returned tools have name, description, parameters attributes
- [x] All new tests pass: `pytest tests/test_tool_registry.py tests/test_llm_registry.py tests/test_store.py tests/test_builtins.py -q`
- [x] `ruff check tests/` clean

## Verification Steps

- `python3 -m pytest tests/test_tool_registry.py tests/test_llm_registry.py tests/test_store.py tests/test_builtins.py --tb=short -q`
- `ruff check tests/`

## Implementation Guidance

1. **Create `tests/test_tool_registry.py`**
   - Use StubTool from conftest to populate registries
   - Test register + get round-trip, KeyError on unknown, all_schemas returns list of dicts, tool_names returns list of strings
   - Test `Tool.to_schema()` returns dict with "name", "description", "parameters" keys

2. **Create `tests/test_llm_registry.py`**
   - Import `register_provider`, `get_provider` from `the_one.llm.registry`
   - IMPORTANT: The registry uses a module-level `_providers` dict. Tests that register providers will pollute state across tests. Either:
     - Save and restore `_providers` around each test, OR
     - Use unique provider names per test to avoid collisions
   - Test registering a FakeLLM class and retrieving it
   - Test ValueError on unknown provider name
   - Test lazy loading: `get_provider("ollama")` should trigger import of `the_one.llm.ollama_provider`. Since ollama provider depends on httpx (which is installed), this should work. The provider will need `model` kwarg.

3. **Create `tests/test_store.py`**
   - Use `tmp_path` for all filesystem operations
   - `FilesystemConfigStore(tmp_path / "agents")` — the dir doesn't need to pre-exist (save creates it)
   - Test save then load returns equivalent AgentConfig
   - Test list_agents returns sorted names
   - Test exists returns True/False correctly
   - Test delete removes the file, delete nonexistent raises KeyError
   - Test load nonexistent raises KeyError
   - Test invalid JSON: write garbage to the file, load should raise (json.JSONDecodeError or ValidationError)

4. **Create `tests/test_builtins.py`**
   - `BuiltinToolProvider().get_tools()` — count should be 14
   - `BuiltinToolProvider().name` — should be "builtin"
   - `isinstance(BuiltinToolProvider(), ToolProvider)` — protocol compliance
   - Iterate tools, assert each has `name`, `description`, `parameters` attrs

## Edge Cases

- **LLM registry state pollution**: Tests must not leave registered providers that affect other test files
- **FilesystemConfigStore with nonexistent parent dir**: `save()` creates dirs with `mkdir(parents=True)`
- **Invalid JSON in store**: Could be malformed JSON or valid JSON that fails Pydantic validation

## Files Affected

- `tests/test_tool_registry.py` — Create
- `tests/test_llm_registry.py` — Create
- `tests/test_store.py` — Create
- `tests/test_builtins.py` — Create

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] Commit all changes together (code + artifacts)
