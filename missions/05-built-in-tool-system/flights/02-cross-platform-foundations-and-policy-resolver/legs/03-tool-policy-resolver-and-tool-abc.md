# Leg: 03-tool-policy-resolver-and-tool-abc

**Status**: completed
**Flight**: [Cross-Platform Foundations & Policy Resolver](../flight.md)

## Objective

Implement the policy resolver, the `Narrow` / `Substitute` markers, the `Tool.Config` ABC contract, the per-agent tool instantiation in `BuiltinToolProvider.get_tools(...)`, and the resolver invocation site in `AgentFactory.create()` — without populating any tool's Config with real fields (`Config = BaseModel` default for all 7 tools).

## Context

L3 ties together L1's platform package (no direct dependency, but live alongside) and L2's persistence surface (`tool_configs` table + `AgentConfig.tool_overrides` field). L3 introduces the resolution layer that **F3-F5 will populate with real constraint values**.

Per Decision 2: per-tool Pydantic `Config` schemas with `Annotated[type, Narrow]` / `Annotated[type, Substitute]` field metadata.

Per Decision 3: resolver invoked once at `AgentFactory.create()`; `BuiltinToolProvider.get_tools()` shifts from shared singletons to per-agent instantiation.

Per Decision 5: F2 uses `Tool.Config = BaseModel` empty default for all 7 tools — F3-F5 will introduce real constraint fields.

Per Decision 9: zero-arg `get_tools()` survives for introspection callers (`/api/tools`, `tests/test_builtins.py`) — when both args are `None`, each tool is instantiated with `Tool.Config()` (no resolver invocation).

Per Decision 10: the `ToolProvider` Protocol stays single-method; `BuiltinToolProvider.get_tools(...)` does its own internal name→Config-class mapping (no `tool_classes()` method on the Protocol). The factor of factor: **provider-drives-resolution** is the default (the resolver call lives inside `BuiltinToolProvider.get_tools`); fall back to factory-drives-resolution only if provider-drives complexity surfaces during implementation.

Per the Architect Q&A point 6 (resolver contract):
- **Unknown tool name** in overrides: silently ignored (mirrors `enabled_tools` strip behavior)
- **Unknown key inside a tool's overrides**: Pydantic `extra="ignore"` silently drops it
- **Type mismatch**: Pydantic raises `ValidationError`
- **Narrow violation** (override widens tool_config): resolver raises `ValueError("agent override widens %s.%s; only narrowing allowed")`

### Per-key narrowing semantics

Decision 2's `Annotated[type, Narrow]` is a marker, not a per-type comparison protocol. The resolver applies a sane default per Python type:

| Field type | Narrow means | Comparison |
|---|---|---|
| `bool` | True → False (revoke a permission) | `agent_val is False or agent_val == tool_val` |
| `int` / `float` (NOT bool) | lower cap → stricter | `agent_val <= tool_val` |
| `list[T]` / `tuple[T, ...]` | smaller subset → stricter | `all(item in tool_val for item in agent_val)` (works for unhashables) |
| `str` / other | no canonical narrowing | NOT IMPLEMENTED — `NotImplementedError("Narrow on <type> field <schema>.<key>; declare per-tool narrowing semantics or use Substitute")` |

**Convention for F3-F5**: `Narrow` on numeric types means upper-bound (cap). F3-F5 must enforce this when annotating fields. If a future field needs floor semantics (e.g., `min_throttle_delay`), introduce a companion marker `NarrowAtLeast` in `the_one/tools/resolver.py` (alongside `Narrow`/`Substitute`) rather than overloading `Narrow`. Documented here so downstream flights have an unambiguous contract.

**Bool ordering**: `bool` is `isinstance(int)` in Python, so the `bool` check must come BEFORE the int check in `_check_narrow`. The bool semantic ("True → False is more restrictive") is canonical for permission-style fields (`follow_redirects`, `allow_network`).

F2's tools have no `Narrow`-annotated fields (all Configs are empty); the fixture test exercises `bool`, `int`, and `list` cases. F3-F5 introduce `int` (timeouts, caps), `list[str]` (path allowlist), and `bool` (permission flags) fields — the resolver's per-type comparisons cover those without further code changes.

### v8 baseline (verified at L3 design time, post-L2)

- `the_one/tools/base.py:7-24` — `Tool` ABC with `name`, `description`, `parameters`, `execute(...)`; **no `__init__` and no `Config` today**
- `the_one/tools/builtins.py:6-28` — `BuiltinToolProvider.get_tools()` zero-arg, returns shared singletons
- `the_one/tools/provider.py:9-20` — `ToolProvider` Protocol: `name` + `get_tools()` (no-arg)
- `the_one/agent/factory.py:101-106` — registry-build loop iterates `provider.get_tools()` with no args
- `the_one/interfaces/web/api.py:79-84` — `/api/tools` endpoint calls `provider.get_tools()` zero-arg
- `tests/test_builtins.py:14,21` — 2 zero-arg `get_tools()` call sites
- `tests/test_factory.py:48-56` — `StubToolProvider.get_tools()` is zero-arg

## Inputs

What exists before this leg runs:

- L1 landed: `the_one/platform/` package present
- L2 landed: schema v8 with `tool_configs` table + `agents.tool_overrides` column; `ToolConfigRepository` exists; `AgentConfig.tool_overrides` field exists
- Branch: `flight/02-cross-platform-foundations` (continuing from L2)
- Pydantic v2 is in use (verified via L2's `dict[str, dict[str, Any]]` validation)

## Outputs

What exists after this leg completes:

- `the_one/tools/resolver.py` (new) — pure-function `resolve(schema, tool_config, agent_override) -> BaseModel`; `Narrow` and `Substitute` sentinel marker classes
- `the_one/tools/base.py` — `Tool` ABC gains `Config: type[BaseModel] = BaseModel` class attribute and `__init__(self, config: BaseModel | None = None)` 
- `the_one/tools/builtins.py` — `BuiltinToolProvider` has internal `_TOOL_CLASSES` dict; `get_tools(tool_configs=None, agent_overrides=None)` instantiates per-agent and invokes the resolver when at least one arg is supplied
- `the_one/agent/factory.py` — `AgentFactory.create()` reads `tool_configs.list_all()` and `config.tool_overrides`, passes both to `provider.get_tools(...)`
- `the_one/tools/provider.py` — `ToolProvider` Protocol's `get_tools` signature accepts the same two optional args (signature widens; existing callers keep working via defaults)
- Tests for resolver, Tool ABC, per-agent isolation, introspection-path preservation, all four Architect-Q&A-point-6 contracts
- All pre-existing tests pass without modification (zero-arg `get_tools()` calls survive)
- Flight log + leg + flight artifact updated

## Acceptance Criteria

- [ ] `the_one/tools/resolver.py` exists and exports:
  - `class Narrow: pass` (sentinel marker class — never instantiated)
  - `class Substitute: pass` (sentinel marker class — never instantiated)
  - `class _EmptyConfig(BaseModel): pass` (private singleton sentinel — Pydantic v2 forbids instantiating bare `BaseModel`, so we use a concrete subclass with no fields as the default for `Tool.Config`. Exposed as `Tool.Config`'s default value; direct import path remains `the_one.tools.resolver._EmptyConfig`. NOT added to `the_one/tools/__init__.py::__all__` — leading-underscore is intentional internal API. Tests that need the type import it explicitly from `the_one.tools.resolver`.)
  - `def resolve(schema: type[BaseModel], tool_config: dict | None, agent_override: dict | None) -> BaseModel`
- [ ] `resolve()` behavior, in order:
  1. **Empty-schema short-circuit**: if `schema.model_fields == {}`, return `schema()` immediately. (No marker dispatch needed; F2's seven tools all hit this path.)
  2. **NULL agent_override** (`agent_override is None`): merge `tool_config or {}` into `schema(...)` directly; return validated instance. The locked-down NULL semantic from Decision 1.
  3. **Per-key dispatch** for non-empty agent_override: iterate `schema.model_fields.items()`. For each `(key, field_info)`:
     - If `key` is NOT in `agent_override`: use `tool_config[key]` if present, else schema default (Pydantic handles via `model_validate({})`).
     - If `key` IS in `agent_override`: inspect `field_info.metadata`:
       - `Narrow in field_info.metadata` (class-identity check): apply per-type narrowing comparison (see Per-Key Narrowing Semantics in Context). On violation, raise `ValueError(f"agent override widens {schema.__name__}.{key}; only narrowing allowed")`. On comparison-not-implemented type, raise `NotImplementedError(f"Narrow on {type_name} field {schema.__name__}.{key}; declare per-tool narrowing semantics or use Substitute")`. On pass, the override value replaces tool_config's value in `merged`.
       - `Substitute in field_info.metadata`: override value replaces tool_config's value in `merged`, no comparison.
       - **Both `Narrow` AND `Substitute` markers**: design error; raise `ValueError(f"field {schema.__name__}.{key} has both Narrow and Substitute markers")`. F3-F5 must not annotate any field with both.
       - **Neither marker**: raise `ValueError(f"field {schema.__name__}.{key} has no Narrow/Substitute marker; cannot resolve")`. (F2's tools have empty Configs → never hit; F3-F5 must annotate every field they introduce.)
  4. Build the merged dict, then call `schema.model_validate(merged)` to get the validated instance. Pydantic's default `extra="ignore"` (or per-Config setting) drops unknown keys silently.
  5. **Unknown tool name** in `agent_override`: NOT this resolver's responsibility — `BuiltinToolProvider.get_tools()` only calls `resolve()` for tool names in `_TOOL_CLASSES`. Overrides for unknown tools are silently ignored at the provider level.
- [ ] `the_one/tools/base.py::Tool` gains:
  - `Config: type[BaseModel] = _EmptyConfig` class attribute (NOT bare `BaseModel` — Pydantic v2's `BaseModel()` raises `PydanticUserError`; `_EmptyConfig` is a concrete empty subclass imported from `the_one.tools.resolver`)
  - `def __init__(self, config: BaseModel | None = None) -> None: self._config = config or self.Config()`
  - Removing the `@abstractmethod` decorator on `execute` is NOT required (`ABC` + `abstractmethod` still works alongside `__init__`); leave the abstract contract in place
- [ ] `the_one/tools/builtins.py::BuiltinToolProvider` updates:
  - Add module-level eager-init `_TOOL_CLASSES: dict[str, type[Tool]]` mapping tool names to classes. Imports happen at module load time (no circular-import risk verified — leaf tool modules only import `the_one.tools.base`).
  - `get_tools(self, tool_configs: dict[str, dict] | None = None, agent_overrides: dict[str, dict] | None = None) -> list[Tool]`
    - Both `None` (introspection path): instantiate each tool with `cls()` (which calls `cls.__init__()` → `cls.Config()` → empty config). No resolver call.
    - At least one supplied (factory path): for each `(name, cls)` in `_TOOL_CLASSES.items()`, call `resolve(cls.Config, tool_configs.get(name), agent_overrides.get(name))` then `cls(resolved_config)`. Two simultaneous calls return distinct tool instance lists (per-agent isolation invariant — verified across BOTH the introspection AND factory paths in tests).
- [ ] `the_one/tools/provider.py::ToolProvider` Protocol's `get_tools` signature widens to `def get_tools(self, tool_configs: dict[str, dict] | None = None, agent_overrides: dict[str, dict] | None = None) -> list[Tool]: ...`. The Protocol stays single-method (no `tool_classes()` added).
- [ ] `the_one/agent/factory.py::AgentFactory.create()` updates the registry-build loop (lines 101-106 today) to:
  - Load tool-level configs: `tool_configs_repo = ToolConfigRepository(conn); tool_configs_by_name = await tool_configs_repo.list_all()`
  - Read agent-level overrides: `agent_overrides = config.tool_overrides or {}`
  - Pass both into `provider.get_tools(tool_configs_by_name, agent_overrides)`
  - Per-agent registry isolation: each `AgentFactory.create()` call constructs a fresh `ToolRegistry` (today already does this via `registry = ToolRegistry()`); the only change is that the tools registered are also fresh per-call.
- [ ] All 7 existing tools (`ShellTool`, `ReadFileTool`, `WriteFileTool`, `ListDirTool`, `PythonExecTool`, `HttpRequestTool`, `WebSearchTool`) inherit `Tool.Config = BaseModel` (no per-tool override needed for F2). They remain instantiable with no args (introspection path) AND with an empty `BaseModel()` config (factory path).
- [ ] `tests/test_resolver.py` (NEW):
  - Empty-schema short-circuit: `resolve(_EmptyConfig, None, None)` returns an `_EmptyConfig()` instance (NOT bare `BaseModel` — Pydantic v2 forbids that)
  - Empty-schema with `tool_config={"x": 1}`: still short-circuits (model_fields empty); the `x: 1` is silently ignored
  - Locked-down NULL: with a fixture Config having `cap: Annotated[int, Narrow] = 100`, `resolve(FixtureCfg, {"cap": 50}, None)` returns `cap=50`
  - Narrow happy path (int): `resolve(FixtureCfg, {"cap": 50}, {"cap": 30})` returns `cap=30`
  - Narrow happy path (int equal): `resolve(FixtureCfg, {"cap": 50}, {"cap": 50})` returns `cap=50`
  - Narrow violation (int widens): `resolve(FixtureCfg, {"cap": 50}, {"cap": 80})` raises `ValueError` with message containing `"widens"` AND `"cap"`
  - Narrow happy path (list): with `paths: Annotated[list[str], Narrow] = []`, `resolve(FixtureCfg, {"paths": ["/home", "/tmp"]}, {"paths": ["/home"]})` returns `paths=["/home"]`
  - Narrow happy path (list with unhashable elements): with `rules: Annotated[list[dict], Narrow] = []`, `resolve(FixtureCfg, {"rules": [{"a": 1}, {"b": 2}]}, {"rules": [{"a": 1}]})` succeeds — verifies the `all(item in tool_val for item in agent_val)` pattern works on unhashables
  - Narrow violation (list adds element): `resolve(FixtureCfg, {"paths": ["/home"]}, {"paths": ["/home", "/etc"]})` raises `ValueError`
  - Narrow happy path (bool): with `redirects: Annotated[bool, Narrow] = True`, `resolve(FixtureCfg, {"redirects": True}, {"redirects": False})` returns `redirects=False`
  - Narrow happy path (bool equal): `resolve(FixtureCfg, {"redirects": True}, {"redirects": True})` returns `redirects=True`
  - Narrow violation (bool widens False→True): `resolve(FixtureCfg, {"redirects": False}, {"redirects": True})` raises `ValueError`
  - Substitution path: with `token: Annotated[str, Substitute] = ""`, `resolve(FixtureCfg, {"token": "tool-tok"}, {"token": "agent-tok"})` returns `token="agent-tok"` (no comparison performed)
  - Field with no marker: with `weird: int = 0`, supplying an override raises `ValueError("...no Narrow/Substitute marker...")`
  - Field with both markers: with `bad: Annotated[int, Narrow, Substitute] = 0`, supplying an override raises `ValueError("...both Narrow and Substitute markers")`
  - Field with `Narrow` on str: raises `NotImplementedError`
  - Field with `Field(...)` metadata + marker: with `cap: Annotated[int, Field(description="x"), Narrow] = 100`, narrow happy path still works (verifies `m is Narrow` finds the marker alongside FieldInfo)
  - Type mismatch: with `cap: Annotated[int, Narrow] = 100`, override `{"cap": "fifty"}` raises Pydantic `ValidationError` (after the merged dict is fed to `model_validate`)
  - Unknown key in override (not in `model_fields`): silently dropped via Pydantic's default `extra="ignore"`
- [ ] `tests/test_builtins.py` updates:
  - **Existing tests at lines 14, 21** (`get_tools()` zero-arg form) MUST KEEP WORKING — they test the introspection path. No assertion changes needed; the new signature accepts zero args via defaults.
  - Add a new test: `BuiltinToolProvider().get_tools(tool_configs=None, agent_overrides=None)` is identical in shape to the zero-arg form
  - Add a new test: `BuiltinToolProvider().get_tools({}, {})` (empty dicts) goes through the factory path; tools are instantiated with `cls.Config()` empty configs; result still has 7 tools
  - Add a new test: per-agent isolation — `tools_a = provider.get_tools(...); tools_b = provider.get_tools(...)`; for each name, `tools_a[i] is not tools_b[i]` (no shared singletons)
  - Add a new test: unknown tool name in `agent_overrides` is silently ignored (passing `{"agent_overrides": {"nonexistent_tool": {"foo": "bar"}}}` does not raise; the 7 known tools are still instantiated)
- [ ] `tests/test_factory.py::StubToolProvider.get_tools` (line 55) signature widens to match the Protocol; a no-op test verifies the factory passes `tool_configs_by_name` (from a mocked `ToolConfigRepository.list_all()` returning `{}`) and `agent_overrides` (from `config.tool_overrides` which defaults to `None` → `{}`) into the provider
- [ ] **Live regression check**: `tests/test_factory.py` agent-creation tests pass unchanged in behavior. The factory fixture grows a new patch:
  ```python
  mock_tool_repo = AsyncMock()
  mock_tool_repo.list_all = AsyncMock(return_value={})
  ...
  patch("the_one.db.repositories.ToolConfigRepository", return_value=mock_tool_repo)
  ```
  The `list_all` AsyncMock setup is essential — without it, `await tool_configs_repo.list_all()` returns an `AsyncMock` (not a dict) and the provider invocation breaks.
- [ ] **Tool ABC contract test** (`tests/test_tool_base.py`, NEW or extend `tests/test_tool_registry.py`):
  - `Tool` subclass without overriding `Config` instantiates with no args (`MyTool()`); `MyTool()._config` is a `BaseModel` instance
  - `Tool` subclass with custom `Config` (e.g., `class MyConfig(BaseModel): timeout: int = 30`): `MyTool()._config.timeout == 30`; `MyTool(MyConfig(timeout=10))._config.timeout == 10`; `MyTool(MyConfig(timeout="bad"))` raises Pydantic `ValidationError`
- [ ] All 7 existing tool unit tests pass unchanged (the empty-Config inheritance + default `__init__` is fully backward-compatible). Verified by running `make test-unit` after L3 changes.
- [ ] `the_one/interfaces/web/api.py:79-84` (`/api/tools`) is unchanged — calls `provider.get_tools()` zero-arg, which still works via defaults
- [ ] No source code modified outside `the_one/tools/`, `the_one/agent/factory.py`, and `tests/`
- [ ] Pre-existing test suite still green (modulo pre-existing CSS-token red): `make test-unit` returns the L2-tip pass/fail set plus the new L3 tests

## Verification Steps

```bash
# Resolver smoke (in container after make rebuild)
docker exec the-one python -c "
from typing import Annotated
from pydantic import BaseModel
from the_one.tools.resolver import resolve, Narrow, Substitute, _EmptyConfig

class FakeCfg(BaseModel):
    cap: Annotated[int, Narrow] = 100
    paths: Annotated[list[str], Narrow] = []
    redirects: Annotated[bool, Narrow] = True
    token: Annotated[str, Substitute] = ''

# Narrow happy (int + list + bool + substitute)
r = resolve(FakeCfg,
    {'cap': 50, 'paths': ['/home', '/tmp'], 'redirects': True, 'token': 'tool'},
    {'cap': 30, 'paths': ['/home'], 'redirects': False, 'token': 'agent'})
assert r.cap == 30 and r.paths == ['/home'] and r.redirects is False and r.token == 'agent', r

# Locked-down NULL
r = resolve(FakeCfg, {'cap': 50}, None)
assert r.cap == 50, r

# Empty schema short-circuit (uses _EmptyConfig — bare BaseModel raises in Pydantic v2)
r = resolve(_EmptyConfig, {'anything': 1}, {'foo': 2})
assert r.model_dump() == {}, r

print('OK')
"

# Tool ABC contract
docker exec the-one python -c "
from pydantic import BaseModel
from the_one.tools.base import Tool
from the_one.tools.shell import ShellTool

# Empty Config inheritance
t = ShellTool()
assert isinstance(t._config, BaseModel), type(t._config)

# Custom Config
class MyCfg(BaseModel):
    timeout: int = 30
class MyTool(Tool):
    name = 'my'; description = 'x'; parameters = {}
    Config = MyCfg
    async def execute(self, **kw): return 'ok'

assert MyTool()._config.timeout == 30
assert MyTool(MyCfg(timeout=10))._config.timeout == 10
print('OK')
"

# Per-agent isolation invariant
docker exec the-one python -c "
import asyncio
from the_one.tools.builtins import BuiltinToolProvider

p = BuiltinToolProvider()
a = p.get_tools({}, {})
b = p.get_tools({}, {})
for ta, tb in zip(a, b):
    assert ta is not tb, f'singleton leaked for {ta.name}'
print('OK')
"

# Targeted tests
docker exec the-one pytest tests/test_resolver.py tests/test_builtins.py \
    tests/test_factory.py tests/test_tool_base.py -v

# Full suite (modulo pre-existing CSS red)
make test-unit
```

## Implementation Guidance

1. **Decide resolver location** — per L3 design, `the_one/tools/resolver.py` (resolver is a property of the tool config system; F3-F5's Configs live next door). If imports get tangled at implementation time, fall back to `the_one/agent/resolver.py`. Document the choice in a Decision entry in the flight log if the fallback is taken.

2. **Implement `the_one/tools/resolver.py`**

   ```python
   from __future__ import annotations
   from typing import Any
   from pydantic import BaseModel

   class Narrow:
       """Marker: agent-level override for this field must be <= tool-level value
       (per-type comparison). Numeric → cap; list → subset; bool → True→False only."""

   class Substitute:
       """Marker: agent-level override for this field replaces tool-level value."""

   class _EmptyConfig(BaseModel):
       """Sentinel empty Config. Pydantic v2 forbids instantiating bare BaseModel,
       so concrete subclass is the default for Tool.Config."""

   def _check_narrow(field_name: str, schema_name: str, tool_val: Any, agent_val: Any) -> None:
       """Raise ValueError if agent_val widens tool_val. Type-aware. Bool BEFORE
       int (bool is isinstance(int) in Python)."""
       if isinstance(agent_val, bool) and isinstance(tool_val, bool):
           # Narrow on bool: agent may revoke (True→False) or match.
           if agent_val is True and tool_val is False:
               raise ValueError(
                   f"agent override widens {schema_name}.{field_name}; "
                   "only narrowing allowed"
               )
           return
       if isinstance(agent_val, (int, float)) and isinstance(tool_val, (int, float)) \
               and not isinstance(agent_val, bool) and not isinstance(tool_val, bool):
           if agent_val > tool_val:
               raise ValueError(
                   f"agent override widens {schema_name}.{field_name}; "
                   "only narrowing allowed"
               )
           return
       if isinstance(agent_val, (list, tuple)) and isinstance(tool_val, (list, tuple)):
           # all-in-tool — works for unhashable elements (dicts, lists).
           if not all(item in tool_val for item in agent_val):
               raise ValueError(
                   f"agent override widens {schema_name}.{field_name}; "
                   "only narrowing allowed"
               )
           return
       raise NotImplementedError(
           f"Narrow on {type(agent_val).__name__} field {schema_name}.{field_name}; "
           "declare per-tool narrowing semantics or use Substitute"
       )

   def resolve(
       schema: type[BaseModel],
       tool_config: dict | None,
       agent_override: dict | None,
   ) -> BaseModel:
       """Compose tool-level + agent-level config per schema-declared semantics."""
       # 1. Empty schema → short-circuit (F2's tools all hit this).
       if not schema.model_fields:
           return schema()

       # 2. Locked-down NULL semantic.
       merged: dict[str, Any] = dict(tool_config or {})
       if agent_override is None:
           return schema.model_validate(merged)

       # 3. Per-key dispatch.
       for key, field_info in schema.model_fields.items():
           if key not in agent_override:
               continue
           markers = field_info.metadata
           has_narrow = any(m is Narrow for m in markers)
           has_substitute = any(m is Substitute for m in markers)
           if has_narrow and has_substitute:
               raise ValueError(
                   f"field {schema.__name__}.{key} has both Narrow and Substitute markers"
               )
           if not (has_narrow or has_substitute):
               raise ValueError(
                   f"field {schema.__name__}.{key} has no Narrow/Substitute marker; "
                   "cannot resolve"
               )
           if has_narrow:
               tool_val = merged.get(key, field_info.default)
               _check_narrow(key, schema.__name__, tool_val, agent_override[key])
           merged[key] = agent_override[key]

       # 4. Final validation (drops unknown keys via extra="ignore" default).
       return schema.model_validate(merged)
   ```

   Notes:
   - `m is Narrow` — Pydantic v2 stores the class itself in `field_info.metadata` for `Annotated[type, Narrow]`. Class-identity is sufficient; instance markers (`Narrow()`) are not used in this design.
   - The empty-schema short-circuit must come BEFORE the agent_override-None branch.
   - Bool ordering: bool check is BEFORE int because `bool` is `isinstance(int)`. The int branch defensively excludes bools to avoid double-handling.

3. **Update `the_one/tools/base.py`**

   ```python
   from pydantic import BaseModel
   from the_one.tools.resolver import _EmptyConfig

   class Tool(ABC):
       name: str
       description: str
       parameters: dict[str, Any]
       Config: type[BaseModel] = _EmptyConfig  # NEW: NOT bare BaseModel (uninstantiable in Pydantic v2)

       def __init__(self, config: BaseModel | None = None) -> None:
           # NEW: empty default lets existing zero-arg subclass instantiation work.
           # `or self.Config()` evaluates `self.Config()` only when config is None,
           # so subclasses with required-field Configs only fail when they should.
           self._config = config or self.Config()

       @abstractmethod
       async def execute(self, **kwargs: Any) -> str: ...

       def to_schema(self) -> dict[str, Any]:
           # unchanged
           ...
   ```

   Note: `ABC` + `abstractmethod` plus a concrete `__init__` works correctly. Tests verify direct instantiation of `Tool` subclasses still works. The `_EmptyConfig` import creates a one-way dependency `base.py → resolver.py`; the leaf tool modules (`shell.py`, etc.) only import from `base.py` so no cycle is introduced.

4. **Update `the_one/tools/builtins.py`**

   Replace the lazy-import body of `get_tools` with a module-level eager-init `_TOOL_CLASSES` dict and the new signature. Eager init at module-load time avoids the lazy-cache test-isolation footnote and the per-call `if is None` branch. No circular imports verified — leaf tool modules import only from `base.py`.

   ```python
   from __future__ import annotations
   from the_one.tools.base import Tool
   from the_one.tools.filesystem import ListDirTool, ReadFileTool, WriteFileTool
   from the_one.tools.python_exec import PythonExecTool
   from the_one.tools.resolver import resolve
   from the_one.tools.shell import ShellTool
   from the_one.tools.web import HttpRequestTool, WebSearchTool

   _TOOL_CLASSES: dict[str, type[Tool]] = {
       "shell": ShellTool,
       "read_file": ReadFileTool,
       "write_file": WriteFileTool,
       "list_dir": ListDirTool,
       "python_exec": PythonExecTool,
       "http_request": HttpRequestTool,
       "web_search": WebSearchTool,
   }

   class BuiltinToolProvider:
       @property
       def name(self) -> str:
           return "builtin"

       def get_tools(
           self,
           tool_configs: dict[str, dict] | None = None,
           agent_overrides: dict[str, dict] | None = None,
       ) -> list[Tool]:
           # Both None → introspection path (no resolver invocation).
           if tool_configs is None and agent_overrides is None:
               return [cls() for cls in _TOOL_CLASSES.values()]
           # Factory path → resolver invocation per tool.
           tool_configs = tool_configs or {}
           agent_overrides = agent_overrides or {}
           result: list[Tool] = []
           for name, cls in _TOOL_CLASSES.items():
               cfg = resolve(cls.Config, tool_configs.get(name), agent_overrides.get(name))
               result.append(cls(cfg))
           return result
   ```

   Note: `_TOOL_CLASSES` is module-level (one dict per Python process). The per-agent isolation guarantee is about the TOOL INSTANCES returned by `get_tools`, not the class dict. Tests that monkeypatch tool classes (none in F2; future flights) can patch `the_one.tools.builtins._TOOL_CLASSES` directly.

5. **Update `the_one/tools/provider.py`**

   Widen the Protocol's `get_tools` signature:

   ```python
   @runtime_checkable
   class ToolProvider(Protocol):
       @property
       def name(self) -> str: ...

       def get_tools(
           self,
           tool_configs: dict[str, dict] | None = None,
           agent_overrides: dict[str, dict] | None = None,
       ) -> list[Tool]: ...
   ```

   Existing callers (one-arg variants) remain compatible via defaults.

6. **Update `the_one/agent/factory.py::AgentFactory.create()`**

   Replace lines 101-106 (the existing registry-build loop) with:

   ```python
   from the_one.db.repositories import ToolConfigRepository

   # ... existing provider config resolution ...

   # NEW: load tool-level configs and agent overrides; pass both to providers.
   tool_configs_repo = ToolConfigRepository(conn)
   tool_configs_by_name = await tool_configs_repo.list_all()
   agent_overrides = config.tool_overrides or {}

   # 2. Build filtered tool registry (per-agent — fresh ToolRegistry every call).
   registry = ToolRegistry()
   for provider in self.tool_providers:
       for tool in provider.get_tools(tool_configs_by_name, agent_overrides):
           if config.is_tool_enabled(tool.name):
               registry.register(tool)
   ```

   The `conn` variable is the same one already in scope from the LLMProviderRepository call (factory.py line 75).

7. **Update `tests/test_factory.py::StubToolProvider`**

   Widen `get_tools` signature to match the Protocol:

   ```python
   def get_tools(
       self,
       tool_configs: dict[str, dict] | None = None,
       agent_overrides: dict[str, dict] | None = None,
   ) -> list[Tool]:
       return [StubTool("tool_a"), StubTool("tool_b"), StubTool("tool_c")]
   ```

   Existing test fixtures need a new patch: `patch("the_one.db.repositories.ToolConfigRepository", return_value=AsyncMock())` with `list_all = AsyncMock(return_value={})`. Add this alongside the existing `LLMProviderRepository` patch in the `factory` fixture.

8. **Write `tests/test_resolver.py`** — covers all 13 cases enumerated in AC

9. **Extend `tests/test_builtins.py`** — keep all 4 existing tests, add the 4 new tests enumerated in AC

10. **Write `tests/test_tool_base.py`** (or extend `tests/test_tool_registry.py`) — Tool ABC contract tests

11. **Update `the_one/agents.md`** documentation:
    - Section on `BuiltinToolProvider` (line 81): mention per-agent instantiation, `_TOOL_CLASSES` dict, the two-arg `get_tools` signature
    - Section on `ToolProvider` (line 162): document the widened signature; preserve the "single-method protocol" claim
    - Add a paragraph: "Resolver — `the_one/tools/resolver.py` composes tool-level + agent-level configs per `Narrow`/`Substitute` markers; invoked at agent build time, returns a per-agent Config instance per tool."

12. **Run targeted tests, then full suite**:
    ```bash
    make rebuild
    docker exec the-one pytest tests/test_resolver.py tests/test_builtins.py \
        tests/test_factory.py tests/test_tool_base.py -v
    make test-unit
    ```

## Edge Cases

- **Pydantic stores `Annotated` markers in `field_info.metadata`**: verified pattern. Both `Annotated[int, Narrow]` (class) and `Annotated[int, Narrow()]` (instance) end up in metadata; the resolver's `m is Narrow` identity check covers the class form, and the `==` check covers the instance form (rare but defensive).
- **A field with both `Narrow` and `Substitute`**: design error; resolver raises `ValueError`. Not exercised by F2's tools (all empty Configs); F3-F5 must not annotate a single field with both markers.
- **`tool_config` is `{}` and `agent_override` is `{}`**: short-circuit returns the schema's defaults via `model_validate({})`. Verified by the empty-empty test in `tests/test_resolver.py`.
- **`agent_override` references a key not in `schema.model_fields`**: Pydantic's default `extra="ignore"` drops it silently. Test asserts the drop.
- **`tool_config` references a key not in `schema.model_fields`**: same drop semantic. The merged dict gets dropped through Pydantic.
- **Eager imports**: `the_one.tools.builtins` imports all 7 tool modules at load time. This is a behavior change from today's lazy-imports-inside-`get_tools` pattern, but verified safe: leaf tool modules (`shell.py`, `filesystem.py`, `python_exec.py`, `web.py`) import only from `the_one.tools.base` and stdlib/third-party. No circular import risk.
- **Test isolation**: `_TOOL_CLASSES` is module-level. Tests that monkeypatch tool classes can patch `the_one.tools.builtins._TOOL_CLASSES` directly via `monkeypatch.setattr`. F2 doesn't introduce such tests.
- **Protocol structural compliance**: `tests/test_builtins.py:18` does `isinstance(BuiltinToolProvider(), ToolProvider)`. `runtime_checkable` Protocol checks method NAMES only, not signatures — the widened `get_tools(tool_configs, agent_overrides)` signature is non-breaking for the isinstance check.
- **Cache freshness contract** (per `/leg` skill section 6):
  - **Source of truth**: `tool_configs` SQLite table + `AgentConfig.tool_overrides` field
  - **Cache**: each agent's resolved `Tool.Config` instance, held by the tool instance, populated once at `AgentFactory.create()`
  - **Rebuild trigger**: per-agent rebuild on `AgentFactory.create()` (Decision 8 — session-bound)
  - **Maximum staleness**: until next `AgentFactory.create()`. F6's admin UI must communicate "applies to next session" — not L3's job to expose.
  - **User-action invalidation**: operator updates `tool_configs` via F6 admin UI → no in-flight invalidation; new sessions pick up the new value. Documented; not L3's job.
- **State-machine reachability** (per `/leg` skill section 5):
  - State: agent has `tool_overrides=None` → resolver receives `agent_override=None` → locked-down NULL path → returns tool_config-only Config. Reachable: yes (default agent state).
  - State: agent has `tool_overrides={}` → resolver receives `agent_override={}` → per-key dispatch loop is no-op → returns tool_config-only Config. Reachable: yes (operator clears overrides).
  - State: agent has `tool_overrides={"shell": {}}` → resolver receives `agent_override={}` (after `agent_overrides.get("shell")`) → no per-key dispatch → returns tool_config Config. Reachable: yes (operator deletes specific overrides).
  - No FK constraints, no CASCADE behaviors that could foreclose any of these.

## Files Affected

- `the_one/tools/resolver.py` — created
- `the_one/tools/base.py` — Tool ABC: add `Config` class attribute and `__init__`
- `the_one/tools/builtins.py` — replace get_tools signature; add `_TOOL_CLASSES`
- `the_one/tools/provider.py` — widen Protocol get_tools signature
- `the_one/agent/factory.py` — invoke resolver via `ToolConfigRepository.list_all()` + `provider.get_tools(...)`
- `tests/test_resolver.py` — created
- `tests/test_builtins.py` — extend with 4 new tests; existing 4 unchanged
- `tests/test_factory.py` — widen `StubToolProvider.get_tools`; patch `ToolConfigRepository`
- `tests/test_tool_base.py` — created (or extend `test_tool_registry.py`)
- `the_one/agents.md` — documentation updates
- `missions/.../flight-log.md` — append L3 progress entry
- `missions/.../flight.md` — check off L3
- `missions/.../legs/03-tool-policy-resolver-and-tool-abc.md` — set status `landed`

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`** (per agentic-workflow batched-review pattern, Developer does NOT commit; review and commit happen once at flight end):

- [ ] All acceptance criteria verified
- [ ] New resolver/Tool-ABC/per-agent-isolation tests passing
- [ ] All 7 existing tools' unit tests pass unchanged
- [ ] Pre-existing unit suite still green (modulo pre-existing CSS-token red)
- [ ] Update flight-log.md with L3 progress entry
- [ ] Set this leg's status to `landed`
- [ ] Check off L3 in flight.md
- [ ] Do NOT commit — final commit happens once after L7
