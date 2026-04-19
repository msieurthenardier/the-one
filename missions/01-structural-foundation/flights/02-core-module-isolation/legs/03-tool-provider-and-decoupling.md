# Leg: tool-provider-and-decoupling

**Status**: completed
**Flight**: [Core Module Isolation](../flight.md)

## Objective

Create the `ToolProvider` protocol and `BuiltinToolProvider`, decouple `memory.py` and `self_deploy.py` from direct settings access, remove `load_defaults()` from `ToolRegistry`, and update `tools/__init__.py` exports.

## Context

- Flight 1 blueprint: `plugin-protocol.md` defines `ToolProvider` and `BuiltinToolProvider`
- Flight 1 blueprint: `target-architecture.md` defines decoupling plan for `memory.py` and `self_deploy.py`
- `memory.py` has a genuine module-level binding: `MEMORY_DIR = settings.workspace_dir / ".memory"` at line 11
- `self_deploy.py` accesses settings inside `execute()` at call time (not module-level), but constructor injection is still needed for testability and per-agent configuration
- `load_defaults()` in `base.py` couples the registry to all tool implementations — replaced by `BuiltinToolProvider`

## Inputs

- `the_one/tools/base.py` — has `load_defaults()` to remove (lines 46-76)
- `the_one/tools/memory.py` — has module-level `MEMORY_DIR` (line 11)
- `the_one/tools/self_deploy.py` — accesses settings in `execute()` (lines 36-38)
- `the_one/tools/__init__.py` — current exports: `Tool`, `ToolRegistry`
- Design artifacts: `plugin-protocol.md`, `target-architecture.md`

## Outputs

- `the_one/tools/provider.py` — new file with `ToolProvider` protocol
- `the_one/tools/builtins.py` — new file with `BuiltinToolProvider`
- `the_one/tools/base.py` — `load_defaults()` removed
- `the_one/tools/memory.py` — constructor injection for `memory_dir`
- `the_one/tools/self_deploy.py` — constructor injection for `workspace_dir`, `concourse_target`, `concourse_pipeline`
- `the_one/tools/__init__.py` — updated exports

## Acceptance Criteria

- [x] `the_one/tools/provider.py` exists with `ToolProvider` as a `@runtime_checkable` Protocol with `name` property and `get_tools() -> list[Tool]` method
- [x] `the_one/tools/builtins.py` exists with `BuiltinToolProvider` that has `name` property returning `"builtin"` and `get_tools()` returning all 14 tools via lazy imports (same tools as current `load_defaults()`)
- [x] `the_one/tools/base.py` no longer has `load_defaults()` method on `ToolRegistry`
- [x] `the_one/tools/memory.py` — `MEMORY_DIR` module-level variable removed; `MemoryTool.__init__` accepts `memory_dir: Path | None = None` with default `settings.workspace_dir / ".memory"`; all internal methods use `self.memory_dir` instead of `MEMORY_DIR`
- [x] `the_one/tools/self_deploy.py` — `SelfDeployTool.__init__` accepts `workspace_dir: Path | None = None`, `concourse_target: str | None = None`, `concourse_pipeline: str | None = None` with defaults from settings; `execute()` uses `self.workspace_dir`, `self.concourse_target`, `self.concourse_pipeline` instead of accessing settings directly
- [x] `the_one/tools/__init__.py` exports `Tool`, `ToolRegistry`, `ToolProvider`
- [x] `the_one/interfaces/cli.py` `_make_agent()` uses `BuiltinToolProvider().get_tools()` instead of `tools.load_defaults()` (transitional — Leg 4 replaces `_make_agent()` entirely)
- [x] `the_one/interfaces/web/app.py` `_make_agent()` uses `BuiltinToolProvider().get_tools()` instead of `tools.load_defaults()` (transitional — Leg 4 replaces `_make_agent()` entirely)
- [x] `BuiltinToolProvider` satisfies `isinstance(BuiltinToolProvider(), ToolProvider)` check
- [x] `len(BuiltinToolProvider().get_tools()) == 14`
- [x] No circular imports — `python -c "from the_one.tools import ToolProvider"` and `python -c "from the_one.tools.builtins import BuiltinToolProvider"` succeed
- [x] `ruff check the_one/` is clean

## Verification Steps

- `python -c "from the_one.tools.provider import ToolProvider; print('ToolProvider OK')"`
- `python -c "from the_one.tools.builtins import BuiltinToolProvider; b = BuiltinToolProvider(); print(f'{len(b.get_tools())} tools'); from the_one.tools.provider import ToolProvider; print(f'satisfies protocol: {isinstance(b, ToolProvider)}')"`
- `python -c "from the_one.tools import Tool, ToolRegistry, ToolProvider; print('exports OK')"`
- `python -c "from the_one.tools.memory import MemoryTool; t = MemoryTool(); print(f'memory_dir: {t.memory_dir}')"`
- `python -c "from the_one.tools.self_deploy import SelfDeployTool; t = SelfDeployTool(); print(f'workspace: {t.workspace_dir}')"`
- `ruff check the_one/`

## Implementation Guidance

1. **Create `the_one/tools/provider.py`**
   - Define `ToolProvider` Protocol per `plugin-protocol.md`
   - Import `Tool` from `the_one.tools.base`
   - Use `@runtime_checkable` decorator
   - Two members: `name` property (`str`) and `get_tools()` method (`list[Tool]`)

2. **Create `the_one/tools/builtins.py`**
   - Define `BuiltinToolProvider` per `plugin-protocol.md`
   - `name` property returns `"builtin"`
   - `get_tools()` has lazy imports of all 14 tool classes (same order as current `load_defaults()`)
   - Returns list of instantiated tools — `MemoryTool()` and `SelfDeployTool()` use default constructors (which pull from settings)

3. **Remove `load_defaults()` from `the_one/tools/base.py`**
   - Delete lines 46-76 (the entire `load_defaults` method)
   - No other changes to `base.py`

4. **Decouple `the_one/tools/memory.py`**
   - Remove `MEMORY_DIR = settings.workspace_dir / ".memory"` (line 11)
   - Add `__init__` to `MemoryTool`:
     ```python
     def __init__(self, memory_dir: Path | None = None) -> None:
         self.memory_dir = memory_dir or (settings.workspace_dir / ".memory")
     ```
   - Replace all references to `MEMORY_DIR` with `self.memory_dir` in methods:
     - `execute()` line 56: `MEMORY_DIR.mkdir(...)` → `self.memory_dir.mkdir(...)`
     - `_save()` line 80: `MEMORY_DIR / f"{slug}.md"` → `self.memory_dir / f"{slug}.md"`
     - `_read()` line 91: `MEMORY_DIR / f"{slug}.md"` → `self.memory_dir / f"{slug}.md"`
     - `_read()` line 94: `MEMORY_DIR.glob(...)` → `self.memory_dir.glob(...)`
     - `_list()` line 102: `MEMORY_DIR.glob(...)` → `self.memory_dir.glob(...)`
     - `_search()` line 117: `MEMORY_DIR.glob(...)` → `self.memory_dir.glob(...)`
     - `_delete()` line 133: `MEMORY_DIR / f"{slug}.md"` → `self.memory_dir / f"{slug}.md"`

5. **Decouple `the_one/tools/self_deploy.py`**
   - Add `__init__` to `SelfDeployTool`:
     ```python
     def __init__(
         self,
         workspace_dir: Path | None = None,
         concourse_target: str | None = None,
         concourse_pipeline: str | None = None,
     ) -> None:
         self.workspace_dir = workspace_dir or settings.workspace_dir
         self.concourse_target = concourse_target or settings.concourse_target
         self.concourse_pipeline = concourse_pipeline or settings.concourse_pipeline
     ```
   - Add `from pathlib import Path` to imports
   - In `execute()`, replace:
     - `workspace = settings.workspace_dir` → `workspace = self.workspace_dir`
     - `concourse = settings.concourse_target` → `concourse = self.concourse_target`
     - `pipeline = settings.concourse_pipeline` → `pipeline = self.concourse_pipeline`

6. **Update `the_one/tools/__init__.py`**
   - Add `ToolProvider` import from `the_one.tools.provider`
   - Update `__all__` to include `ToolProvider`

7. **Update `_make_agent()` callers (transitional)**
   - In `the_one/interfaces/cli.py`, replace `tools.load_defaults()` (line 26) with:
     ```python
     from the_one.tools.builtins import BuiltinToolProvider
     # ... in _make_agent():
     tools = ToolRegistry()
     for tool in BuiltinToolProvider().get_tools():
         tools.register(tool)
     ```
   - In `the_one/interfaces/web/app.py`, same replacement (line 64)
   - This keeps the codebase functional between Legs 3 and 4

## Edge Cases

- **`memory.py` still imports `settings`**: The import stays because the constructor default uses `settings.workspace_dir`. This is fine — it's evaluated at construction time, not module level.
- **`self_deploy.py` still imports `settings`**: Same pattern — used as constructor defaults.
- **Protocol isinstance check**: `BuiltinToolProvider` doesn't inherit from `ToolProvider` — it satisfies it structurally. The `@runtime_checkable` decorator enables `isinstance()` checks.
- **Callers of `load_defaults()`**: Both `cli.py` and `web/app.py` call `tools.load_defaults()`. They must be updated in this leg to use `BuiltinToolProvider` to keep the codebase functional. Leg 4 replaces `_make_agent()` entirely with `AgentFactory`.

## Files Affected

- `the_one/tools/provider.py` — Create
- `the_one/tools/builtins.py` — Create
- `the_one/tools/base.py` — Remove `load_defaults()`
- `the_one/tools/memory.py` — Constructor injection
- `the_one/tools/self_deploy.py` — Constructor injection
- `the_one/tools/__init__.py` — Add `ToolProvider` export
- `the_one/interfaces/cli.py` — Transitional: replace `load_defaults()` with `BuiltinToolProvider`
- `the_one/interfaces/web/app.py` — Transitional: replace `load_defaults()` with `BuiltinToolProvider`

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
