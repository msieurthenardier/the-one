# Leg: 01b-cross-config-dispatch-and-agent-name-plumbing

**Status**: landed
**Flight**: [Execution Expansion & Constraints](../flight.md)

## Objective

Land the architectural foundation for F4 cross-Config dispatch: widen `ToolProvider.get_tools` and `Tool.__init__` signatures to take `agent_name` and `cross_configs`, add `Requires` class attribute on `Tool`, freeze `FilesystemConfig`, and thread `agent_name` from `AgentFactory.create()` through `BuiltinToolProvider.get_tools()` into each tool instance.

## Context

- **F4 Decision 7**: cwd validation in execution tools must reuse `FilesystemConfig.path_allowlist`/`path_denylist` so an agent denied `read_file('/etc/passwd')` is also denied `cd /etc && cat passwd`. The mechanism: provider resolves all distinct Configs once and passes a `cross_configs: dict[type[BaseModel], BaseModel]` view to each tool.
- **F4 Decision 4**: PTY session ownership keys on `(agent_name, session_id)`. The `agent_name` must be plumbed through provider → tool init.
- **F4 Decision 7 (frozen Configs)**: `cross_configs` are shared across tool instances in one provider call; mutation by one tool would corrupt another's view. `model_config = ConfigDict(frozen=True)` makes Pydantic models hashable + immutable.
- **F4 Decision 8 (split rationale)**: L1a was the mechanical move; L1b is the architectural plumbing. Each gets its own review surface.
- **L1a landed** (uncommitted): `ConstraintError` lives in `the_one/tools/base.py` next to the `Tool` ABC; `filesystem.py` re-exports.
- **Protocol widening is non-breaking** for `runtime_checkable` Protocol (method-name checks only). Existing `isinstance(provider, ToolProvider)` continues to pass. This is verified by `tests/test_builtins.py::test_protocol_compliance`.

## Inputs

- `the_one/tools/base.py` — defines `Tool` ABC with `Config: type[BaseModel] = _EmptyConfig` and `__init__(self, config: BaseModel | None = None)`.
- `the_one/tools/provider.py` — defines `ToolProvider` Protocol with `get_tools(tool_configs=None, agent_overrides=None)`.
- `the_one/tools/builtins.py` — `_TOOL_CLASSES` (13 entries); `BuiltinToolProvider.get_tools` invokes `resolve(...)` per tool.
- `the_one/tools/resolver.py` — `resolve(schema, tool_config, agent_override) -> BaseModel` is the per-Config entrypoint.
- `the_one/tools/filesystem.py` — `FilesystemConfig(BaseModel)` exists without `frozen=True`.
- `the_one/agent/factory.py` — `AgentFactory.create(name)` calls `provider.get_tools(tool_configs_by_name, agent_overrides)` at line 117 with no `agent_name` argument.
- `tests/test_tool_base.py`, `tests/test_builtins.py`, `tests/test_factory.py` — existing test surfaces that exercise the current contracts.

## Outputs

- `the_one/tools/base.py`:
  - `Tool` ABC gains `Requires: tuple[type[BaseModel], ...] = ()` class-level default.
  - `Tool.__init__` widened to `(config=None, cross_configs=None, agent_name=None)`. Stores `self._cross_configs: dict[type[BaseModel], BaseModel]` and `self._agent_name: str | None`.
- `the_one/tools/provider.py`:
  - `ToolProvider.get_tools` Protocol widened to `(tool_configs=None, agent_overrides=None, agent_name=None)`.
- `the_one/tools/builtins.py`:
  - `BuiltinToolProvider.get_tools` accepts the new `agent_name` kwarg.
  - On the factory path, computes `cross_configs` once: iterate `_TOOL_CLASSES.values()`, collect distinct `cls.Config` types (skipping `_EmptyConfig`), resolve each once via `resolve(cfg_type, tool_configs.get(<reverse-lookup name>), None)` — but reverse lookup from `Config` type to tool name is fragile when multiple tools share a Config (they will in F4). **Resolve cross_configs from tool-level config only** (no agent overrides applied at the cross-Config layer — agent overrides only narrow the tool's own Config). Each tool's own Config still resolves with its own agent override; cross_configs are the operator-default views.
  - Pass `(cfg, cross_configs=cross_configs, agent_name=agent_name)` into each `cls(...)`.
  - On the introspection path (both args None), pass `cross_configs=None` and `agent_name=None`.
- `the_one/agent/factory.py`:
  - Line 117: pass `agent_name=name` to `provider.get_tools(...)`.
- `the_one/tools/filesystem.py`:
  - `FilesystemConfig` adds `model_config = ConfigDict(frozen=True)` (retroactive).
- `tests/test_tool_base.py`:
  - New test cases for `Requires` default, `cross_configs` storage, `agent_name` storage, and that omitting them still works (back-compat).
- `tests/test_builtins.py`:
  - New test: a fixture tool declaring `Requires = (FilesystemConfig,)` receives the resolved FilesystemConfig in `cross_configs`.
  - New test: `agent_name` threads through to the tool instance.
  - New test: `cross_configs` dict contains all distinct Config types referenced by `_TOOL_CLASSES` (currently just `FilesystemConfig` in addition to `_EmptyConfig`).
  - Existing tests pass unchanged (zero-arg form, explicit-None form, factory-path empty-dict form).
- `tests/test_factory.py`:
  - Update any test that asserts on `provider.get_tools(...)` call shape.
  - New test: `AgentFactory.create("foo")` results in tools whose `_agent_name == "foo"`.
- `tests/test_filesystem_config.py`:
  - New test: `FilesystemConfig` is frozen — attempting `cfg.read_size_cap_bytes = 999` raises `pydantic.ValidationError`.
  - New test: `model_post_init` still runs post-freeze (e.g., `_canonical_allowlist` is populated after construction).

## Acceptance Criteria

- [x] `Tool.__init__` signature is `(self, config=None, cross_configs=None, agent_name=None)`.
- [x] `Tool.Requires: tuple[type[BaseModel], ...] = ()` class-level default exists.
- [x] `Tool` instance exposes `self._cross_configs` (dict, defaults to `{}`) and `self._agent_name` (str|None, defaults to `None`).
- [x] `ToolProvider.get_tools` Protocol signature is `(tool_configs=None, agent_overrides=None, agent_name=None)`.
- [x] `BuiltinToolProvider.get_tools` accepts the `agent_name` kwarg (default `None`); threads it into every `cls(...)` call on the factory path.
- [x] On the factory path, `BuiltinToolProvider.get_tools` builds a `cross_configs: dict[type[BaseModel], BaseModel]` containing one resolved instance per distinct `cls.Config` type referenced by `_TOOL_CLASSES` (excluding `_EmptyConfig`), and passes it to each tool's `__init__`.
- [x] On the introspection path (`tool_configs is None and agent_overrides is None`), `cross_configs=None` and `agent_name=None` are passed (or the tool is constructed with `cls()` — back-compat preserves zero-arg).
- [x] `AgentFactory.create(name)` passes `agent_name=name` into `provider.get_tools(...)`.
- [x] `FilesystemConfig` carries `model_config = ConfigDict(frozen=True)` — mutating a field on an instance raises `pydantic.ValidationError`.
- [x] F3 test suite passes unchanged — existing tools have empty `Requires`; provider behavior is backward-compatible.
- [x] `tests/test_builtins.py::test_protocol_compliance` still passes — `runtime_checkable` Protocol widening is non-breaking.
- [x] New test: a fixture `Tool` subclass declaring `Requires = (FilesystemConfig,)` receives a `FilesystemConfig` instance in `cross_configs[FilesystemConfig]` from the provider.
- [x] New test: `AgentFactory.create("test-agent")` results in built tools where `tool._agent_name == "test-agent"`.
- [x] New test (in `tests/test_filesystem_config.py`): `FilesystemConfig(...)` is frozen — `pydantic.ValidationError` on attribute assignment.
- [x] New test (in `tests/test_filesystem_config.py`): `model_post_init` still runs post-freeze (e.g., `_canonical_allowlist` private attr populated after construction).
- [x] **All three mock providers** in `tests/test_factory.py` (`StubToolProvider` at module level + two `CapturingProvider` definitions inside `TestResolverWiring`) updated to accept the new `agent_name` kwarg.
- [x] `tests/conftest.py::StubTool` (if it overrides `Tool.__init__`) widened to accept `cross_configs` and `agent_name` kwargs.
- [x] `Tool.Requires` is a `tuple` (immutable class-level default), not a list.
- [x] `make test-unit` green (modulo pre-existing CSS-token red).

## Verification Steps

```bash
# Provider signature
docker exec the-one python -c "
import inspect
from the_one.tools.builtins import BuiltinToolProvider
sig = inspect.signature(BuiltinToolProvider.get_tools)
assert 'agent_name' in sig.parameters, sig
print('OK get_tools sig')
"

# Tool ABC widened
docker exec the-one python -c "
import inspect
from the_one.tools.base import Tool
sig = inspect.signature(Tool.__init__)
assert 'cross_configs' in sig.parameters
assert 'agent_name' in sig.parameters
assert hasattr(Tool, 'Requires')
assert Tool.Requires == ()
print('OK Tool ABC')
"

# Frozen FilesystemConfig
docker exec the-one python -c "
import pydantic
from the_one.tools.filesystem import FilesystemConfig
cfg = FilesystemConfig()
try:
    cfg.read_size_cap_bytes = 1
    raise SystemExit('FAIL: mutation succeeded')
except pydantic.ValidationError:
    print('OK frozen')
"

# cross_configs populated
docker exec the-one python -c "
from the_one.tools.builtins import BuiltinToolProvider
from the_one.tools.filesystem import FilesystemConfig
tools = BuiltinToolProvider().get_tools({}, {})
fs_tool = next(t for t in tools if t.name == 'read_file')
assert FilesystemConfig in fs_tool._cross_configs, list(fs_tool._cross_configs.keys())
print('OK cross_configs')
"

# Test suite
docker exec the-one pytest tests/test_tool_base.py tests/test_builtins.py tests/test_factory.py tests/test_filesystem_config.py tests/test_filesystem_helpers.py tests/test_filesystem_tools.py -x -q
docker exec the-one pytest -x -q
```

## Implementation Guidance

1. **Widen `Tool.__init__` and add `Requires` (in `the_one/tools/base.py`)**

   ```python
   class Tool(ABC):
       name: str
       description: str
       parameters: dict[str, Any]

       Config: type[BaseModel] = _EmptyConfig
       Requires: tuple[type[BaseModel], ...] = ()

       def __init__(
           self,
           config: BaseModel | None = None,
           cross_configs: dict[type[BaseModel], BaseModel] | None = None,
           agent_name: str | None = None,
       ) -> None:
           self._config = config or self.Config()
           self._cross_configs = cross_configs or {}
           self._agent_name = agent_name
   ```

   - All three new params default to safe values; F3 tools and tests that call `cls()` continue to work.

2. **Widen the `ToolProvider` Protocol (in `the_one/tools/provider.py`)**

   ```python
   def get_tools(
       self,
       tool_configs: dict[str, dict] | None = None,
       agent_overrides: dict[str, dict] | None = None,
       agent_name: str | None = None,
   ) -> list[Tool]:
       ...
   ```

   - Update the docstring to mention `agent_name` is per-agent state-isolation, NOT adversarial separation (per Decision 4).

3. **Update `BuiltinToolProvider.get_tools` (in `the_one/tools/builtins.py`)**

   - Add `agent_name: str | None = None` to the signature.
   - On the introspection path (both `tool_configs` and `agent_overrides` are `None`), preserve the existing `[cls() for cls in _TOOL_CLASSES.values()]`. This keeps `_cross_configs == {}` and `_agent_name == None` via `Tool.__init__` defaults.
   - On the factory path:
     - Build `cross_configs: dict[type[BaseModel], BaseModel] = {}` BEFORE the per-tool loop.
     - **Use the simpler-alternative dispatch**: iterate `_TOOL_CLASSES.items()` ONCE; for each `(name, cls)` where `cls.Config is not _EmptyConfig` AND `cls.Config not in cross_configs`, set `cross_configs[cls.Config] = resolve(cls.Config, tool_configs.get(name), None)`. Python 3.7+ guarantees `dict.items()` iterates in insertion order, so "first tool name with this Config" is deterministic and matches the order declared in `_TOOL_CLASSES`.
     - **Cross-Config layer ignores agent overrides** — pass `None` as the third arg to `resolve(...)`. Agent overrides only narrow each tool's own Config, never the cross-Config baseline view.
     - In the per-tool loop, pass `cls(cfg, cross_configs=cross_configs, agent_name=agent_name)`.
   - Import `_EmptyConfig` from `the_one.tools.resolver` for the "skip empty" check.

4. **Thread `agent_name` from factory (`the_one/agent/factory.py`)**

   - Line 117: change `for tool in provider.get_tools(tool_configs_by_name, agent_overrides):` to `for tool in provider.get_tools(tool_configs_by_name, agent_overrides, agent_name=name):`.

   - **Update mock providers in `tests/test_factory.py`** — three call sites:
     - Module-level `StubToolProvider` (~line 48): add `agent_name: str | None = None` to `get_tools` signature.
     - `TestResolverWiring`'s first `CapturingProvider` (~line 210): same widening.
     - `TestResolverWiring`'s second `CapturingProvider` (~line 272): same widening.
     - For tests that want to assert `agent_name` was threaded, capture it in a list/attr like `self.captured_agent_name = agent_name`.

   - **Update `tests/conftest.py::StubTool`** if it overrides `Tool.__init__`. If it inherits, no change needed; if it overrides, widen to `(self, config=None, cross_configs=None, agent_name=None)` and store all three (or call `super().__init__(...)` to delegate).

5. **Freeze `FilesystemConfig` (`the_one/tools/filesystem.py`)**

   - Import `ConfigDict` from `pydantic`: extend the existing `from pydantic import BaseModel, Field, PrivateAttr` line to include `ConfigDict`.
   - Add `model_config = ConfigDict(frozen=True)` as the first class-body line in `FilesystemConfig`.
   - **Risk check**: any code that currently mutates a `FilesystemConfig` instance after construction will now raise. Search `rg -n "fs_cfg\." the_one/ tests/` to find suspicious patterns. Construction-time mutation in `model_post_init` is fine — Pydantic's frozen check fires only on subsequent attribute *assignment*, AND `PrivateAttr` assignments inside `model_post_init` are exempt (they go through a different path).
   - **List-content mutation is NOT blocked by frozen=True.** The existing test `test_default_denylist_does_not_share_module_list` does `cfg1.path_denylist.append(...)` which still works post-freeze (frozen blocks attribute assignment, not mutation of the contained list). This is fine — that test still asserts the correct invariant (no module-level list sharing).

6. **Add tests**

   - `tests/test_tool_base.py`:
     - Construct `_NoConfigTool(cross_configs={...}, agent_name="x")` and assert the new attributes.
     - Construct with no args; assert `_cross_configs == {}` and `_agent_name is None`.
     - Assert `_NoConfigTool.Requires == ()`.
   - `tests/test_builtins.py`: Add a `_FixtureTool` subclass declaring `Config = ExecutionStub; Requires = (FilesystemConfig,)`. Monkeypatch `_TOOL_CLASSES` to include it. Call `BuiltinToolProvider().get_tools({}, {}, agent_name="alpha")`. Assert the fixture tool's `_cross_configs[FilesystemConfig]` is a `FilesystemConfig` instance and `_agent_name == "alpha"`. The simpler dispatch (item 3) handles this — no need to actually USE `Requires` in the provider yet; `Requires` is documentation/contract for now and tools opt-in by inspecting `self._cross_configs[FilesystemConfig]` themselves. (The provider already gives ALL tools the full `cross_configs` dict, so `Requires` is purely declarative for F4 readers + future static analyzers.)
   - `tests/test_factory.py`: With one of the existing capturing mock providers, assert that the captured `agent_name == "<name>"` after `factory.create("<name>")`. Add `captured_agent_name` field to the mock providers as part of the widening.
   - `tests/test_filesystem_config.py`: assert `pydantic.ValidationError` on `FilesystemConfig().read_size_cap_bytes = 1`. Also assert `FilesystemConfig()._canonical_allowlist` (or whichever PrivateAttr is populated by `model_post_init`) is non-empty after construction — proving `model_post_init` still runs post-freeze.
   - `tests/test_builtins.py`: add an assertion in the factory-path test that `tools[i]._cross_configs is tools[j]._cross_configs` (same dict instance shared across all tools in one call) AND that two separate `get_tools` calls return tools with different `cross_configs` instances (per-call freshness).

7. **Update existing tests**

   - `tests/test_builtins.py::TestBuiltinToolProviderL3`:
     - The `factory_path` tests already pass `({}, {})`. Verify that `_cross_configs[FilesystemConfig]` is populated for all 13 tools (or at minimum, that no exception is raised). This is the net new behavior — existing assertions on tool counts/names stay valid.

8. **Lint + tests**

   - `docker exec the-one ruff check the_one/`
   - `docker exec the-one pytest -x -q`

## Edge Cases

- **`cross_configs` passing semantics**: the dict is shared by reference across all tools in one `get_tools` call. Frozen Configs (FilesystemConfig now, ExecutionConfig in L2) prevent any tool from mutating a peer's view.
- **Reverse lookup for cross-Config tool_config source**: when multiple tools share a Config (all 9 filesystem tools share FilesystemConfig), the `tool_configs` dict may have entries for several names. The provider arbitrarily picks the first. **In practice**: operators set `tool_configs` row per *category*, not per tool — F2/F3 design assumes one logical config per category. If operators in F6 set per-tool overrides for the same category and they diverge, the cross-Config view will reflect only the first tool's row. Document as a known minor in this leg's flight log entry; revisit if F6 admin UI surfaces per-tool config writes.
- **`Requires` as documentation-only in L1b**: the provider currently passes the full `cross_configs` dict to every tool regardless of `Requires`. Future could optimize to pass only the declared subset, but YAGNI for F4 — leave the contract documented and the implementation simple.
- **Frozen Config + `model_post_init`**: Pydantic v2 calls `model_post_init` after `__init__` but the freeze fires only on subsequent attribute assignment. `FilesystemConfig.model_post_init` (canonicalization) works. Verify nothing else mutates fields post-construction (e.g., a `_setup` helper).
- **Test isolation**: tests that monkeypatch `_TOOL_CLASSES` should restore via `monkeypatch.setattr`. The `cross_configs` dict is per-call so test-to-test leakage is unlikely.
- **Backward-compat for `cls()` zero-arg construction**: many tests construct tools directly with `cls()` and pass an explicit Config later. The new params have defaults so this keeps working.
- **`AgentFactory` mock providers**: `tests/test_factory.py` may use mock providers whose `get_tools` doesn't accept the new `agent_name` kwarg. Update mocks to take `**kwargs` or to accept the new kwarg explicitly.

## Files Affected

- `the_one/tools/base.py` — widen `Tool.__init__`; add `Requires` default.
- `the_one/tools/provider.py` — widen `ToolProvider.get_tools` signature.
- `the_one/tools/builtins.py` — accept `agent_name`; build and pass `cross_configs`.
- `the_one/agent/factory.py` — pass `agent_name=name` to provider.
- `the_one/tools/filesystem.py` — add `ConfigDict(frozen=True)`.
- `tests/test_tool_base.py` — new tests for new params + `Requires`.
- `tests/test_builtins.py` — new tests for `cross_configs` dispatch + `agent_name` + intra-call sharing + inter-call freshness.
- `tests/test_factory.py` — update three mock provider definitions (`StubToolProvider` + 2× `CapturingProvider`); add `agent_name` capture/assertion test.
- `tests/conftest.py` — widen `StubTool.__init__` if it overrides `Tool.__init__`.
- `tests/test_filesystem_config.py` — new tests for frozen behavior + `model_post_init`-still-runs.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] (NOT final leg — do NOT update flight.md status, do NOT commit yet)
