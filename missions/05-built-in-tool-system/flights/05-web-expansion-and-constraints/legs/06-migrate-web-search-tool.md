# Leg: 06-migrate-web-search-tool

**Status**: landed
**Flight**: [Web Expansion & Constraints](../flight.md)

## Objective

Migrate `WebSearchTool` to consume the L5 `SearchBackend` protocol via cross_configs injection. Declare `Config = WebConfig`. `BuiltinToolProvider.get_tools` instantiates a single `DDGSearchBackend()` per call and passes it via `cross_configs[SearchBackend]`. Tool formats `list[SearchResult]` into the existing `- title\n  url\n  snippet` agent-facing shape. Closes the F1 known issue at the `WebSearchTool` surface.

## Context

- **L0–L5 landed** (uncommitted). `SearchBackend` Protocol + `DDGSearchBackend` ship in `the_one/tools/_search_backends.py`. The DDG backend uses the browser User-Agent that fixes F1.
- **F5 Decision 12** (L5 leg-design-time refinement): backends inject via `cross_configs[SearchBackend]` — same dispatch dict that F4 uses for `cross_configs[FilesystemConfig]`.
- **`cross_configs` type widening** (architect-flagged): the F4 L1b signature is `dict[type[BaseModel], BaseModel]`. `SearchBackend` is a Protocol, not a `BaseModel`. **Resolution**: widen to `dict[type, Any]` in `Tool.__init__` and `BuiltinToolProvider.get_tools`. The "frozen Pydantic" invariant from F4 still holds for Pydantic-keyed entries (`FilesystemConfig`, `ExecutionConfig`); Protocol-keyed entries (`SearchBackend`) are stateful but per-`get_tools()`-call-scoped, matching the session-bound freshness contract.
- **`Requires` declaration**: L1 didn't define `cross_configs[SearchBackend]` because L5 hadn't introduced `SearchBackend` yet. L6 declares `WebSearchTool.Requires = (SearchBackend,)` so the cross-Config dispatch surface remains declarative.
- **Agent-facing format unchanged**: today's `WebSearchTool.execute` returns either `"\n\n".join(["- title\n  url\n  snippet", ...])` or `"No results found."`. L6 preserves both.

## Inputs

- `the_one/tools/_search_backends.py` — `SearchResult`, `SearchBackend`, `DDGSearchBackend` (post-L5).
- `the_one/tools/_web_config.py` — `WebConfig` (post-L1).
- `the_one/tools/base.py::Tool.__init__` — `cross_configs: dict[type[BaseModel], BaseModel]` (F4 L1b shape).
- `the_one/tools/builtins.py::BuiltinToolProvider.get_tools` — current cross_configs construction.
- `the_one/tools/web.py::WebSearchTool` — current implementation (will be rewritten).
- `tests/test_web_tools.py::TestWebSearchTool` — existing tests to update.
- `tests/test_builtins.py` — cross_configs assertions to update.

## Outputs

- `the_one/tools/base.py`:
  - **Widen `cross_configs` type** in `Tool.__init__` from `dict[type[BaseModel], BaseModel] | None` to `dict[type, object] | None`. Update the docstring to note the F5 widening: Pydantic models for Config-style keys; Protocol-implementing instances for service-style keys (e.g., `SearchBackend`). The "frozen Pydantic" invariant continues to hold for the Pydantic-keyed entries.
  - `Requires` annotation widens correspondingly: `tuple[type, ...]` (was `tuple[type[BaseModel], ...]`).
- `the_one/tools/provider.py`:
  - Update the `ToolProvider.get_tools` Protocol signature's docstring to mention service-style cross_configs entries (no functional change to the Protocol — the type is already `runtime_checkable` and methods-only).
- `the_one/tools/builtins.py`:
  - Import `DDGSearchBackend`, `SearchBackend` from `_search_backends`.
  - In the factory path of `get_tools`, AFTER building the Pydantic-keyed `cross_configs` entries, append a service-keyed entry:
    ```python
    cross_configs[SearchBackend] = DDGSearchBackend()
    ```
    (F5 ships only one backend; F6 admin will let operators pick. The backend is constructed fresh per `get_tools` call — owns its own httpx client; closed via Python GC since each agent invocation gets a fresh provider call.)
- `the_one/tools/web.py`:
  - **`WebSearchTool` rewritten**:
    - `Config = WebConfig`.
    - `Requires = (SearchBackend,)` (new — L1's WebSearchTool had no Requires; L6 adds it).
    - `name = "web_search"`.
    - `description = "Search the web and return results (title, URL, snippet). The backend is operator-configurable (default DuckDuckGo); F6 admin will surface the picker. Useful for finding URLs to feed into fetch_url or read."`.
    - `parameters` unchanged (`query` required; `max_results` optional, default 5).
    - `execute(self, query, max_results=5, **kwargs) -> str`:
      1. `backend: SearchBackend = self._cross_configs[SearchBackend]` (typed cast).
      2. Three-clause envelope (no timeout-clause needed — DDGSearchBackend's owned-client timeout is the only deadline; if it fires, surfaces as `httpx.TimeoutException` from the generic `Exception` clause):
         - `try`:
           - `results = await backend.search(query, max_results)`.
           - If `not results`: return `"No results found."` (preserve F1 wording).
           - Format: `"\n\n".join(f"- {r.title}\n  {r.url}\n  {r.snippet}" for r in results)`.
         - `except ConstraintError as e: return f"[error] [constraint] {e}"` (defensive — backend may evolve to raise these).
         - `except Exception as e: return f"[error] {e}"`.
- `tests/test_web_tools.py::TestWebSearchTool`:
  - **Update existing 5 tests** to reflect the new architecture:
    - Construct `WebSearchTool(WebConfig(), cross_configs={SearchBackend: backend})` where `backend` is either a real `DDGSearchBackend` (with mocked transport) OR a stub `_StubBackend(SearchBackend)` for unit isolation.
    - Tests that today exercise httpx directly via `_install_mock_websearch` (preserved from L2) need rewriting to inject a stub backend instead. Cleaner separation: backend-level tests live in `tests/test_search_backends.py`; tool-level tests focus on backend-output formatting.
  - **New tests**:
    - `test_construction_shape`: builds with `cross_configs={SearchBackend: DDGSearchBackend()}`; `Config is WebConfig`; `Requires == (SearchBackend,)`.
    - `test_results_formatted_correctly`: stub backend returns 3 `SearchResult`s with known fields; tool returns the `"- title\n  url\n  snippet"` format with double-newline separation.
    - `test_no_results_message`: stub backend returns `[]`; tool returns `"No results found."`.
    - `test_max_results_passed_to_backend`: stub backend captures `max_results`; tool calls with `max_results=3`; backend received 3.
    - `test_backend_exception_caught`: stub raises `RuntimeError`; tool returns `[error] {msg}`.
- `tests/test_builtins.py`:
  - Update `test_cross_configs_contains_four_distinct_configs` (post-L2 rename): expand assertion set to include `SearchBackend`. Rename: `test_cross_configs_contains_four_configs_and_one_backend` (or similar) — five entries total. **Or** loosen the assertion to count the entries by category (Pydantic Configs vs service backends) rather than naming them all.
  - Decision: keep the simple set assertion. Rename to `test_cross_configs_contains_expected_keys` and assert: `{FilesystemConfig, ExecutionConfig, PythonExecConfig, WebConfig, SearchBackend}` ⊆ `cross_configs.keys()`. Five entries. Document the inclusion of `SearchBackend` (Protocol) alongside the Pydantic Configs.

## Acceptance Criteria

- [x] `Tool.__init__`'s `cross_configs` type widens to `dict[type, object] | None`. Docstring updated.
- [x] `Tool.Requires` type widens to `tuple[type, ...]`.
- [x] `BuiltinToolProvider.get_tools` injects `DDGSearchBackend()` into `cross_configs[SearchBackend]` on the factory path.
- [x] `WebSearchTool.Config is WebConfig` and `WebSearchTool.Requires == (SearchBackend,)`.
- [x] `WebSearchTool.execute` consumes `self._cross_configs[SearchBackend]`, calls `backend.search(query, max_results)`, formats `list[SearchResult]` as `"- title\n  url\n  snippet"` lines, double-newline separated.
- [x] Empty results → `"No results found."` (F1 wording preserved).
- [x] Three-clause envelope (`ConstraintError → Exception` plus an implicit `[error] ...` for backend-side failures).
- [x] All 5 existing `TestWebSearchTool` tests pass after migration.
- [x] All 5 new `WebSearchTool` tests pass.
- [x] `test_builtins.py::test_cross_configs_*` updated to assert `SearchBackend` is in the cross_configs dict.
- [x] `_TOOL_CLASSES` count unchanged at 19 (no new tools in L6).
- [x] Mission Open Question for F1 (DDG no results) is resolved by L6 + L5 — flight log records this.
- [x] Full unit suite green (modulo CSS-token red).
- [x] `ruff check` clean on touched files.

## Verification Steps

```bash
# Construction shape
docker exec the-one python -c "
from the_one.tools.web import WebSearchTool
from the_one.tools._web_config import WebConfig
from the_one.tools._search_backends import SearchBackend, DDGSearchBackend
t = WebSearchTool(WebConfig(), cross_configs={SearchBackend: DDGSearchBackend()})
assert t.Config is WebConfig
assert t.Requires == (SearchBackend,)
assert SearchBackend in t._cross_configs
print('OK construction')
"

# BuiltinToolProvider injects the backend
docker exec the-one python -c "
from the_one.tools.builtins import BuiltinToolProvider
from the_one.tools._search_backends import SearchBackend, DDGSearchBackend
tools = BuiltinToolProvider().get_tools({}, {})
ws = next(t for t in tools if t.name == 'web_search')
assert SearchBackend in ws._cross_configs
backend = ws._cross_configs[SearchBackend]
assert isinstance(backend, DDGSearchBackend)
print('OK provider injection')
"

# Tests
docker exec the-one pytest tests/test_web_tools.py tests/test_builtins.py tests/test_search_backends.py -x -q
docker exec the-one pytest -x -q --deselect tests/test_token_definitions.py::test_every_var_reference_is_defined

# Lint
docker exec the-one ruff check the_one/tools/base.py the_one/tools/builtins.py the_one/tools/web.py tests/test_web_tools.py tests/test_builtins.py
```

## Implementation Guidance

1. **Widen `Tool` ABC types** in `the_one/tools/base.py`:
   ```python
   class Tool(ABC):
       Config: type[BaseModel] = _EmptyConfig
       Requires: tuple[type, ...] = ()  # was tuple[type[BaseModel], ...]

       def __init__(
           self,
           config: BaseModel | None = None,
           cross_configs: dict[type, object] | None = None,  # was dict[type[BaseModel], BaseModel] | None
           agent_name: str | None = None,
       ) -> None:
           ...
   ```
   Update the docstring's "F4 L1b Decision 7 forced frozen Pydantic" note: still applies to Pydantic-keyed entries; Protocol-keyed service entries are stateful but per-`get_tools()` call-scoped.

2. **Update `BuiltinToolProvider.get_tools`** in `the_one/tools/builtins.py`:
   - Add import: `from the_one.tools._search_backends import DDGSearchBackend, SearchBackend`.
   - After the existing `cross_configs` construction loop, add:
     ```python
     # F5 L6: inject SearchBackend service alongside Pydantic Configs.
     # F5 ships only DDG; F6 admin will let operators pick. The backend
     # owns its own httpx client; per-`get_tools()` lifecycle matches
     # the session-bound freshness contract — agents with different
     # extra_allowed_hosts get different httpx clients via separate
     # `get_tools()` calls.
     cross_configs[SearchBackend] = DDGSearchBackend()
     ```
   - Update the docstring to mention the new entry type.

3. **Rewrite `WebSearchTool`** in `the_one/tools/web.py`:
   ```python
   class WebSearchTool(Tool):
       name = "web_search"
       description = (
           "Search the web and return results (title, URL, snippet). The "
           "backend is operator-configurable (default DuckDuckGo); F6 admin "
           "will surface the picker. Useful for finding URLs to feed into "
           "fetch_url or read."
       )
       parameters = {
           "type": "object",
           "properties": {
               "query": {"type": "string", "description": "Search query."},
               "max_results": {
                   "type": "integer",
                   "description": "Max results (default 5).",
                   "default": 5,
               },
           },
           "required": ["query"],
       }
       Config = WebConfig
       Requires = (SearchBackend,)

       async def execute(self, query: str, max_results: int = 5, **kwargs: Any) -> str:
           try:
               backend: SearchBackend = self._cross_configs[SearchBackend]  # type: ignore[assignment]
               results = await backend.search(query, max_results)
               if not results:
                   return "No results found."
               return "\n\n".join(
                   f"- {r.title}\n  {r.url}\n  {r.snippet}" for r in results
               )
           except ConstraintError as e:
               return f"[error] [constraint] {e}"
           except Exception as e:
               return f"[error] {e}"
   ```

4. **Update existing `TestWebSearchTool` tests** in `tests/test_web_tools.py`:
   - Replace the pre-F5 `_install_mock_websearch` factory with a stub-backend pattern. Define `_StubBackend` inside the test class:
     ```python
     class _StubBackend:
         name = "stub"
         def __init__(self, results=None, raise_exc=None, capture_max=None):
             self._results = results or []
             self._raise_exc = raise_exc
             self._capture_max = capture_max
         async def search(self, query, max_results):
             if self._capture_max is not None:
                 self._capture_max.append(max_results)
             if self._raise_exc is not None:
                 raise self._raise_exc
             return self._results
     ```
   - Each test constructs `WebSearchTool(WebConfig(), cross_configs={SearchBackend: stub_backend})` with the stub configured for that test.

5. **Update `test_builtins.py::test_cross_configs_contains_four_distinct_configs`**:
   - Rename to something like `test_cross_configs_contains_expected_entries` (5 entries: 4 Configs + 1 backend).
   - Update the assertion set: `{FilesystemConfig, ExecutionConfig, PythonExecConfig, WebConfig, SearchBackend} <= set(cross_configs.keys())`.
   - Update docstring to reflect the new shape (Pydantic Configs + Protocol-keyed service backends).

6. **Mission Open Question** for F1 (DDG no results) — flight log entry for L6 should record: "Closes F1 known issue. The fix landed in L5 (DDGSearchBackend uses browser User-Agent); L6 wires the backend into WebSearchTool. Mission Known Issue updated to `[x]` with reference to F5 L5 + L6."

## Edge Cases

- **`SearchBackend` Protocol type as dict key**: Python allows this; Protocol classes ARE valid types and hashable. `isinstance(backend, SearchBackend)` works because `SearchBackend` is `runtime_checkable`. `cross_configs[SearchBackend] = ddg_instance` is the natural shape.
- **Multiple backends in F6+**: when F6 admin lets operators pick, the provider chooses ONE backend per `get_tools` call based on tool config. The cross_configs dict still has one `SearchBackend` entry — just a different concrete implementation. No structural change.
- **Old test `_install_mock_websearch`** (preserved from L2 for WebSearchTool): can be deleted in L6 since the stub-backend pattern replaces it.
- **`Requires = (SearchBackend,)`** is documentation-only in F4 L1b's design (provider passes full `cross_configs` regardless). L6 keeps that — `Requires` is declarative metadata. The architect's L1b rationale ("documentation-only") stays valid.
- **Backend instance lifecycle**: `DDGSearchBackend()` creates a fresh instance per `get_tools` call. The owned-httpx-client is created lazily per `search()` call (per L5). When the agent invocation ends and the tool list is GC'd, the backend instance is too. No explicit close needed.
- **Concurrency**: if two agents share the same `BuiltinToolProvider` and call `get_tools()` simultaneously, each gets its OWN `DDGSearchBackend` instance — no shared state. Already covered by F4 L1b's per-call freshness.

## Files Affected

- `the_one/tools/base.py` — widen `cross_configs` and `Requires` types.
- `the_one/tools/builtins.py` — inject `DDGSearchBackend()` into `cross_configs[SearchBackend]` on factory path.
- `the_one/tools/web.py` — rewrite `WebSearchTool`.
- `tests/test_web_tools.py` — update 5 existing `TestWebSearchTool` tests to stub-backend pattern; add 5 new tests; delete `_install_mock_websearch`.
- `tests/test_builtins.py` — rename + update cross_configs assertion to include `SearchBackend`.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed` (in this file's header)
- [ ] (Flight Director will check off in flight.md — do NOT modify flight.md)
- [ ] (NOT final leg — do NOT update flight.md status, do NOT commit)
