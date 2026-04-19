# Leg: agent-store-and-factory

**Status**: completed
**Flight**: [Core Module Isolation](../flight.md)

## Objective

Create `AgentConfigStore` protocol and `FilesystemConfigStore`, create `AgentFactory`, replace `_make_agent()` in both interfaces with `AgentFactory().create()`, and update `agent/__init__.py` exports.

## Context

- Flight 1 blueprint: `multi-agent-model.md` defines AgentConfigStore, FilesystemConfigStore, and AgentFactory
- `AgentConfig` Pydantic model already exists (created in Leg 2)
- `ToolProvider` and `BuiltinToolProvider` already exist (created in Leg 3)
- `_make_agent()` in both `cli.py` and `web/app.py` currently uses the transitional `BuiltinToolProvider` pattern (from Leg 3) — this leg replaces the entire function with `AgentFactory`
- Design decision: factory always passes `base_url` to `get_provider()`, matching current `_make_agent()` behavior

## Inputs

- `the_one/agent/config.py` — `AgentConfig` model exists
- `the_one/tools/builtins.py` — `BuiltinToolProvider` exists
- `the_one/tools/provider.py` — `ToolProvider` protocol exists
- `the_one/config.py` — `settings.agents_dir` property exists
- `the_one/interfaces/cli.py` — has `_make_agent()` to replace
- `the_one/interfaces/web/app.py` — has `_make_agent()` to replace
- Design: `multi-agent-model.md` (corrected in Leg 1)

## Outputs

- `the_one/agent/store.py` — new file with `AgentConfigStore` protocol and `FilesystemConfigStore`
- `the_one/agent/factory.py` — new file with `AgentFactory`
- `the_one/interfaces/cli.py` — `_make_agent()` replaced with `AgentFactory().create()`
- `the_one/interfaces/web/app.py` — `_make_agent()` replaced with `AgentFactory().create()`
- `the_one/agent/__init__.py` — updated exports

## Acceptance Criteria

- [x] `the_one/agent/store.py` exists with:
  - `AgentConfigStore` as a `@runtime_checkable` Protocol with methods: `list_agents() -> list[str]`, `load(name) -> AgentConfig`, `save(config) -> None`, `delete(name) -> None`, `exists(name) -> bool`
  - `FilesystemConfigStore` implementation that reads/writes JSON from `agents_dir` path, uses `AgentConfig.model_validate(data)` for deserialization
- [x] `the_one/agent/factory.py` exists with `AgentFactory` class:
  - Constructor: `store: AgentConfigStore | None = None`, `tool_providers: list | None = None`
  - Defaults: `FilesystemConfigStore(settings.agents_dir)`, `[BuiltinToolProvider()]`
  - `create(name="default") -> Agent`: loads config, gets LLM provider (always passes `base_url`), builds filtered ToolRegistry, resolves system prompt
  - `list_agents() -> list[str]`: returns stored + "default"
  - `_default_config() -> AgentConfig`: synthesizes from settings including `llm_base_url=settings.llm_base_url`
- [x] `AgentFactory().create()` produces an Agent equivalent to old `_make_agent()`:
  - Same LLM provider with same model and base_url
  - Same 14 tools registered
  - Same system prompt (DEFAULT_SYSTEM_PROMPT)
- [x] `the_one/interfaces/cli.py` — `_make_agent()` function removed, replaced with `AgentFactory().create()` call. Unused imports removed (`get_provider`, `ToolRegistry`, `BuiltinToolProvider`).
- [x] `the_one/interfaces/web/app.py` — `_make_agent()` function removed, replaced with `_factory.create()` in `_get_session()` and `/api/selftest` endpoint (line 206). Unused imports removed (`get_provider`, `ToolRegistry`, `BuiltinToolProvider`).
- [x] `the_one/agent/__init__.py` exports `Agent`, `AgentConfig`, `AgentFactory`
- [x] No circular imports — `python -c "from the_one.agent import Agent, AgentConfig, AgentFactory"` succeeds
- [x] `ruff check the_one/` is clean

## Verification Steps

- `python -c "from the_one.agent.store import AgentConfigStore, FilesystemConfigStore; print('store OK')"`
- `python -c "from the_one.agent.factory import AgentFactory; a = AgentFactory(); agent = a.create(); print(f'tools: {agent.tools.tool_names}'); print(f'prompt starts: {agent.system_prompt[:20]}...')"`
- `python -c "from the_one.agent import Agent, AgentConfig, AgentFactory; print('exports OK')"`
- `ruff check the_one/`

## Implementation Guidance

1. **Create `the_one/agent/store.py`**
   - `AgentConfigStore` Protocol per `multi-agent-model.md`:
     - `@runtime_checkable`
     - Methods: `list_agents`, `load`, `save`, `delete`, `exists`
     - `load()` raises `KeyError` if not found
   - `FilesystemConfigStore`:
     - Constructor takes `agents_dir: Path`
     - `load()` reads JSON, uses `AgentConfig.model_validate(data)`
     - `save()` serializes with `model_dump()`, writes JSON
     - `list_agents()` globs `*.json` and returns sorted stems
     - `exists()` checks path existence
     - `delete()` raises `KeyError` if not found, then unlinks

2. **Create `the_one/agent/factory.py`**
   - `AgentFactory` per `multi-agent-model.md`:
     - Constructor: `store` defaults to `FilesystemConfigStore(settings.agents_dir)`, `tool_providers` defaults to `[BuiltinToolProvider()]`
     - `create(name="default")`:
       1. Load config (from store or `_default_config()` for "default")
       2. Get LLM provider — **always pass `base_url` unconditionally**: `get_provider(config.llm_provider, model=config.llm_model, base_url=config.llm_base_url)`. Do NOT use the conditional pattern from the blueprint (`if config.llm_base_url`); always pass `base_url` as a keyword argument to match current `_make_agent()` behavior.
       3. Build ToolRegistry filtered by `config.is_tool_enabled()`
       4. Resolve system prompt via `config.get_system_prompt()`
       5. Return `Agent(llm=llm, tools=registry, system_prompt=system_prompt, max_iterations=config.max_iterations)`
     - `_default_config()`:
       ```python
       return AgentConfig(
           name="default",
           description="General-purpose agent with full tool access",
           llm_provider=settings.llm_provider,
           llm_model=settings.llm_model,
           llm_base_url=settings.llm_base_url,
       )
       ```
     - `_load_config(name)`: try store, fall back to `_default_config()` for "default", raise `KeyError` for unknown
     - `list_agents()`: merge store names with "default"
   - Call `settings.ensure_dirs()` in `create()` to match current `_make_agent()` behavior

3. **Replace `_make_agent()` in `the_one/interfaces/cli.py`**
   - Remove `_make_agent()` function entirely
   - Remove now-unused imports: `get_provider`, `ToolRegistry`, `BuiltinToolProvider`
   - Add import: `from the_one.agent.factory import AgentFactory`
   - In `_run_cli()`, replace `agent = _make_agent()` with:
     ```python
     factory = AgentFactory()
     agent = factory.create()
     ```

4. **Replace `_make_agent()` in `the_one/interfaces/web/app.py`**
   - Remove `_make_agent()` function entirely
   - Remove now-unused imports: `get_provider`, `ToolRegistry`, `BuiltinToolProvider`
   - Add import: `from the_one.agent.factory import AgentFactory`
   - Create module-level factory: `_factory = AgentFactory()`
   - In `_get_session()`, replace `agent=_make_agent()` with `agent=_factory.create()`
   - In `selftest()` endpoint (line 206), replace `agent = _make_agent()` with `agent = _factory.create()`

5. **Update `the_one/agent/__init__.py`**
   - Add imports of `AgentConfig` from `config` and `AgentFactory` from `factory`
   - Update `__all__` to `["Agent", "AgentConfig", "AgentFactory"]`

## Edge Cases

- **`_default_config()` `llm_base_url`**: Current `_make_agent()` always passes `base_url=settings.llm_base_url`. The factory's `_default_config()` must include `llm_base_url=settings.llm_base_url` to match. Without this, Ollama would fall back to its constructor default URL.
- **`base_url` always passed**: The factory always passes `base_url` to `get_provider()` even when it's None. Providers that don't use it accept it via `**kwargs`. This matches current behavior.
- **`settings.ensure_dirs()`**: Current `_make_agent()` calls this. The factory should call it in `create()` to preserve the behavior.
- **`FilesystemConfigStore.save()` serialization**: Use `model_dump()` for Pydantic models, not manual field enumeration. Simpler and automatically handles all fields.

## Files Affected

- `the_one/agent/store.py` — Create
- `the_one/agent/factory.py` — Create
- `the_one/agent/__init__.py` — Update exports
- `the_one/interfaces/cli.py` — Replace `_make_agent()`
- `the_one/interfaces/web/app.py` — Replace `_make_agent()`

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
