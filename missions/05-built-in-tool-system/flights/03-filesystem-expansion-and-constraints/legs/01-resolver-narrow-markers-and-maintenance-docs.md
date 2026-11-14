# Leg: 01-resolver-narrow-markers-and-maintenance-docs

**Status**: landed
**Flight**: [Filesystem Expansion & Constraints](../flight.md)

## Objective

Extend `the_one/tools/resolver.py` with `NarrowPrefix` and `NarrowSuperset` sentinel markers (with mutual-exclusion enforcement across all four narrow/substitute markers), and land two F2-debrief maintenance fold-ins: `tests/CONVENTIONS.md` documenting the four established test patterns, and an `agents.md` paragraph documenting `_TOOL_CLASSES` and the `ui_hint` / `ui_choices` Pydantic-schema convention introduced in Decision 11.

## Context

This is the foundational scaffolding leg of Flight 03. Every downstream leg (L2a/L2b/L3-L6) depends on the new resolver markers because `FilesystemConfig` declares `path_allowlist: NarrowPrefix` and `path_denylist: NarrowSuperset`. No tool code is migrated in L1 — pure resolver + docs work. The leg also folds in two F2-debrief carryovers (Decision 7) so they ride alongside the resolver context-plumbing rather than spawning a separate maintenance leg.

**Relevant flight design decisions**:
- **Decision 1** — `NarrowPrefix` / `NarrowSuperset` sentinel markers (pivoted from `Substitute + model_validator` because Pydantic v2's `mode="after"` instance-method validators don't receive `info`).
- **Decision 1.5** — `ConstraintError(Exception)` lands here? No: defined in L2a alongside `FilesystemConfig`. L1 only ships resolver markers + docs.
- **Decision 7** — `tests/CONVENTIONS.md` + `_TOOL_CLASSES` doc note in `agents.md` fold into L1.
- **Decision 11** — `ui_hint` / `ui_choices` are the conventional Pydantic-schema metadata keys. L1 documents this convention so F4-F6 reuse the same keys for finite-set fields.

**Mutual-exclusion contract** (key reason this leg exists, not just "add two markers"): `resolve()`'s per-key dispatch must reject fields carrying more than one of `{Narrow, NarrowPrefix, NarrowSuperset, Substitute}`. F2 only checked `has_narrow and has_substitute`; the new markers expand the matrix.

## Inputs

Files that must exist (verified pre-flight):
- `the_one/tools/resolver.py` — ships `Narrow`, `Substitute`, `_EmptyConfig`, `_check_narrow`, `resolve` (F2)
- `the_one/platform/paths.py` — ships `canonicalize`, `safe_resolve`, `is_within` (F2)
- `the_one/agents.md` — exists; has `### the_one/tools/` table + Tool Policy Resolver section (F2)
- `tests/test_resolver.py` — exists with `TestNarrowInt`, `TestNarrowList`, `TestNarrowBool`, `TestSubstitute`, `TestMarkerErrors`, `TestPydanticInteraction` (F2)
- `tests/conftest.py` — exists with shared FakeLLM / StubTool / registry helpers (F1)
- `the_one/tools/builtins.py` — exports `_TOOL_CLASSES` dict (F1)
- `pyproject.toml` — `[tool.pytest.ini_options] asyncio_mode = "auto"` (F2)

State that must be true:
- Schema at v8 (verified)
- Branch `flight/03-filesystem-expansion-and-constraints` checked out from `main` at `83a34bb`
- All F2 resolver tests pass on `main` baseline

## Outputs

Files modified:
- `the_one/tools/resolver.py` — adds `NarrowPrefix`, `NarrowSuperset` classes; extends `_check_narrow` with per-marker dispatch (renames the function or splits into helpers); extends `resolve()`'s per-key dispatch to recognize all four markers and enforce mutual exclusion.
- `the_one/agents.md` — `### the_one/tools/` table row for `resolver.py` updated (mentions four markers); Tool Policy Resolver section extended with `NarrowPrefix` / `NarrowSuperset` semantics; new paragraph documenting `_TOOL_CLASSES` as the supported test seam AND `ui_hint`/`ui_choices` schema-metadata convention.

Files created:
- `tests/CONVENTIONS.md` — documents the four F2 patterns (asyncio_mode, monkeypatch.setenv HOME, httpx MockTransport `_install_mock` recursion-avoidance, kill+reap timeout-budget assertions).

Tests added (in existing `tests/test_resolver.py`):
- `class TestNarrowPrefix` — happy (descendant), happy (equal-to-root), violation (path outside any tool entry), violation on non-list type (TypeError).
- `class TestNarrowSuperset` — happy (agent ⊇ tool), happy (equal lists), violation (tool entry missing from agent), violation on non-list type (TypeError).
- `class TestMutualExclusion::test_multi_marker_rejected` — locks the contract that no field may carry >1 of the four markers (covers `Narrow + NarrowPrefix`, `NarrowSuperset + Substitute`, `Narrow + NarrowSuperset`, `NarrowPrefix + Substitute`).

State changes:
- No DB schema changes. No migrations. No new env vars. No new ports.

## Acceptance Criteria

- [ ] `the_one/tools/resolver.py` exports two new sentinel marker classes: `NarrowPrefix` and `NarrowSuperset` with module-level docstrings explaining their semantics (prefix-containment and superset-membership respectively).
- [ ] `_check_narrow` (or its successor split) dispatches all four markers correctly: `Narrow` (existing semantics unchanged), `NarrowPrefix` (uses `the_one.platform.paths.is_within(agent_entry, tool_entry)` — agent value is narrow iff every agent entry is descendant-or-equal of at least one tool entry), `NarrowSuperset` (agent ⊇ tool — every tool entry must be present in agent value), `Substitute` (existing).
- [ ] `resolve()`'s per-key dispatch counts markers per field and raises `ValueError` if `marker_count > 1` (consistent with F2's `marker_count == 0` ValueError; both are "schema author wired markers wrong" → both are `ValueError`). Both messages updated to enumerate all four markers using a tuple-formatted list `(Narrow, NarrowPrefix, NarrowSuperset, Substitute)` (NOT a Python `{set}` literal — set rendering order is unstable). `marker_count == 0` message preserves the existing F2 substring `"no Narrow/Substitute marker"` (capitalized) so the existing F2 test `test_no_marker_raises` keeps passing without modification; new wording is appended (e.g., `"... — declare one of (Narrow, NarrowPrefix, NarrowSuperset, Substitute)"`). `marker_count > 1` message uses the substring `"multiple narrow/substitute markers"` plus the same tuple.
- [ ] `NarrowPrefix` / `NarrowSuperset` applied to non-list values raise `NotImplementedError` (NOT `TypeError`) — matches F2's precedent for `Narrow`-on-`str` at `resolver.py:116`. Keeps the marker-on-unsupported-type contract consistent across all four markers.
- [ ] All existing F2 resolver tests in `tests/test_resolver.py` continue to pass unchanged. `test_no_marker_raises` is preserved as-is (the old substring is kept). `test_both_markers_raises` is **updated only in its message-substring assertion** (from `"both Narrow and Substitute"` to `"multiple narrow/substitute markers"`); the `pytest.raises(ValueError)` shape is preserved (both errors are `ValueError`).
- [ ] `tests/test_resolver.py::TestNarrowPrefix` covers happy + violation + non-list-type-error (3+ tests).
- [ ] `tests/test_resolver.py::TestNarrowSuperset` covers happy + violation + non-list-type-error (3+ tests).
- [ ] `tests/test_resolver.py::TestMutualExclusion::test_multi_marker_rejected` parameterizes across the 5 net-new two-marker pairs introduced by L1 (`Narrow+NarrowPrefix`, `Narrow+NarrowSuperset`, `NarrowPrefix+NarrowSuperset`, `NarrowPrefix+Substitute`, `NarrowSuperset+Substitute`). The pre-existing `Narrow+Substitute` case is already covered by `test_both_markers_raises` (kept; substring updated).
- [ ] `tests/CONVENTIONS.md` exists with the four F2 patterns documented, each with a runnable code snippet (under 200 lines total).
- [ ] `the_one/agents.md` Tool Policy Resolver section mentions all four markers (search shows the four marker names in the section); the agent-architecture testing-conventions paragraph documents `_TOOL_CLASSES` as the supported test monkeypatch seam AND introduces `ui_hint`/`ui_choices` as the conventional Pydantic-schema metadata keys (with a one-line example from Decision 11's dropdown).
- [ ] `make test-unit` passes (target: existing unit count + 10+ new tests, modulo pre-existing CSS-token red).
- [ ] `ruff check` and `ruff format --check` clean on changed files.

## Verification Steps

Static (after edit, before commit):

```bash
cd ~/projects/the-one

# Markers exported
rg -n "^class NarrowPrefix" the_one/tools/resolver.py    # 1 match
rg -n "^class NarrowSuperset" the_one/tools/resolver.py  # 1 match

# Dispatch arms reference is_within for prefix
rg -n "is_within" the_one/tools/resolver.py              # 1+ match (within prefix dispatch)

# Mutual-exclusion check exists
rg -n "marker_count\b" the_one/tools/resolver.py         # 1+ match

# Tests exist
rg -n "class TestNarrowPrefix\b|class TestNarrowSuperset\b|test_multi_marker_rejected" tests/test_resolver.py
# Expected: 3 matches (TestNarrowPrefix, TestNarrowSuperset, TestMutualExclusion)

# CONVENTIONS.md exists
test -f tests/CONVENTIONS.md && echo OK

# agents.md mentions ui_hint convention
rg -n "ui_hint" the_one/agents.md                         # 1+ match
rg -n "_TOOL_CLASSES" the_one/agents.md                   # 1+ match (existing line 81 + new paragraph)
```

Dynamic:

```bash
# Resolver tests
docker exec the-one pytest tests/test_resolver.py -v
# Expected: existing F2 tests pass + ~14 new tests pass (5 prefix + 4 superset + 5 parametrized mutual-exclusion); 0 failures

# Full unit suite (sanity)
make test-unit
# Expected: target ≥ F2 baseline + ~14 new tests; pre-existing CSS-token red is acceptable

# Smoke from flight verification block — NarrowPrefix
docker exec the-one python -c "
from typing import Annotated
from pydantic import BaseModel
from the_one.tools.resolver import resolve, NarrowPrefix
class Cfg(BaseModel):
    paths: Annotated[list[str], NarrowPrefix] = []
r = resolve(Cfg, {'paths': ['/home/u']}, {'paths': ['/home/u/projects']})
assert r.paths == ['/home/u/projects']
try:
    resolve(Cfg, {'paths': ['/home/u']}, {'paths': ['/etc']})
    assert False
except ValueError as e:
    assert 'widens' in str(e)
print('OK')
"

# Smoke — NarrowSuperset
docker exec the-one python -c "
from typing import Annotated
from pydantic import BaseModel
from the_one.tools.resolver import resolve, NarrowSuperset
class Cfg(BaseModel):
    deny: Annotated[list[str], NarrowSuperset] = []
r = resolve(Cfg, {'deny': ['/etc']}, {'deny': ['/etc', '/proc']})
assert r.deny == ['/etc', '/proc']
try:
    resolve(Cfg, {'deny': ['/etc', '/proc']}, {'deny': ['/etc']})
    assert False
except ValueError as e:
    assert 'widens' in str(e) and '/proc' in str(e)
print('OK')
"
```

Quality:

```bash
ruff check the_one/tools/resolver.py the_one/agents.md tests/test_resolver.py tests/CONVENTIONS.md 2>&1 || true
ruff format --check the_one/tools/resolver.py tests/test_resolver.py
```

## Implementation Guidance

### Step 1: Add `NarrowPrefix` and `NarrowSuperset` marker classes

In `the_one/tools/resolver.py`, immediately after the existing `Substitute` class definition, add two new sentinel classes:

```python
class NarrowPrefix:
    """Marker: agent-level ``list[str]`` (paths) is narrowing iff every agent
    entry is a descendant of (or equal to) at least one tool entry, checked
    via ``the_one.platform.paths.is_within``.

    Used for path-allowlist style fields where the operator declares a set of
    permitted root paths and an agent may further restrict to subtrees within
    those roots.

    Raises ``NotImplementedError`` when applied to non-list values — this
    marker is list-only. Matches F2's ``Narrow``-on-``str`` precedent for
    "marker on unsupported type" so the contract is uniform across markers.
    """


class NarrowSuperset:
    """Marker: agent-level ``list[T]`` is narrowing iff every tool entry is
    also in the agent value (agent ⊇ tool — agent ADDS restrictions).

    Inverse of ``Narrow``'s list semantic (which is agent ⊆ tool, i.e. the
    agent removes options). Used for denylist-style fields where the
    operator declares a baseline of forbidden entries and the agent may add
    more forbidden entries but never remove the operator's baseline.

    Membership check is plain ``==`` equality on raw values — string-equal
    membership; canonicalization (e.g. resolving ``~``) is the consumer's
    responsibility (see ``FilesystemConfig.model_post_init`` in F3 L2a).

    Raises ``NotImplementedError`` when applied to non-list values.
    """
```

Both classes are sentinels — never instantiated. Identity comparison (`m is NarrowPrefix`) is the dispatch mechanism, matching F2's existing pattern for `Narrow` / `Substitute`.

### Step 2: Extend `_check_narrow` with per-marker dispatch

The simplest path is to refactor by extracting two helpers and calling them from `resolve()` directly (rather than overloading `_check_narrow`). This keeps the existing `_check_narrow` signature and behavior intact for `Narrow`-only callers and adds two siblings:

```python
def _check_narrow_prefix(
    field_name: str,
    schema_name: str,
    tool_val: Any,
    agent_val: Any,
) -> None:
    """Raise if ``agent_val`` widens ``tool_val`` under prefix-containment
    semantics. Both must be ``list[str]``; non-list values raise
    ``NotImplementedError`` (matches F2's ``Narrow``-on-``str`` precedent)."""
    if not (isinstance(tool_val, list) and isinstance(agent_val, list)):
        raise NotImplementedError(
            f"NarrowPrefix on non-list field {schema_name}.{field_name}; "
            "marker is list-only"
        )
    for ap in agent_val:
        if not any(is_within(ap, tp) for tp in tool_val):
            raise ValueError(
                f"agent override widens {schema_name}.{field_name}; "
                f"'{ap}' not within any tool entry"
            )


def _check_narrow_superset(
    field_name: str,
    schema_name: str,
    tool_val: Any,
    agent_val: Any,
) -> None:
    """Raise if ``agent_val`` widens ``tool_val`` under superset-membership
    semantics (agent must contain every tool entry). Membership uses ``==``
    on raw values — canonicalization is consumer-side."""
    if not (isinstance(tool_val, list) and isinstance(agent_val, list)):
        raise NotImplementedError(
            f"NarrowSuperset on non-list field {schema_name}.{field_name}; "
            "marker is list-only"
        )
    for tp in tool_val:
        if tp not in agent_val:
            raise ValueError(
                f"agent override widens {schema_name}.{field_name}; "
                f"tool entry '{tp}' missing from agent value"
            )
```

Notes:
- `is_within` is imported at module-top in `resolver.py` alongside the existing imports — no circular dependency exists between `the_one.tools.resolver` and `the_one.platform.paths`. Add `from the_one.platform.paths import is_within` to the existing import block.
- `is_within` already canonicalizes both arguments internally (verified in `the_one/platform/paths.py:55-71`), so the prefix check tolerates `~` / relative / non-canonical entries.

### Step 3: Extend `resolve()`'s per-key dispatch with mutual exclusion

In `resolve()`'s per-key loop, replace the existing two-marker check with a four-marker count + dispatch:

```python
    for key, field_info in schema.model_fields.items():
        if key not in agent_override:
            continue
        markers = field_info.metadata
        has_narrow = any(m is Narrow for m in markers)
        has_narrow_prefix = any(m is NarrowPrefix for m in markers)
        has_narrow_superset = any(m is NarrowSuperset for m in markers)
        has_substitute = any(m is Substitute for m in markers)
        marker_count = sum([has_narrow, has_narrow_prefix, has_narrow_superset, has_substitute])
        if marker_count > 1:
            raise ValueError(
                f"field {schema.__name__}.{key} has multiple narrow/substitute "
                "markers; declare exactly one of "
                "(Narrow, NarrowPrefix, NarrowSuperset, Substitute)"
            )
        if marker_count == 0:
            raise ValueError(
                f"field {schema.__name__}.{key} has no Narrow/Substitute marker; "
                "declare one of (Narrow, NarrowPrefix, NarrowSuperset, Substitute)"
            )
        tool_val = merged.get(key, field_info.default)
        if has_narrow:
            _check_narrow(key, schema.__name__, tool_val, agent_override[key])
        elif has_narrow_prefix:
            _check_narrow_prefix(key, schema.__name__, tool_val, agent_override[key])
        elif has_narrow_superset:
            _check_narrow_superset(key, schema.__name__, tool_val, agent_override[key])
        # Substitute path: no check; merge below performs replacement.
        merged[key] = agent_override[key]
```

**Compatibility notes**:

- **`marker_count == 0` message** preserves the F2 substring `"no Narrow/Substitute marker"` (capitalized) verbatim, with new tail text appended after the semicolon. The existing F2 test `TestMarkerErrors::test_no_marker_raises` (asserts substring `"no Narrow/Substitute marker"`) keeps passing without modification.
- **`marker_count > 1` message** uses the substring `"multiple narrow/substitute markers"`. F2's existing `test_both_markers_raises` (asserts `"both Narrow and Substitute"`) needs its substring updated to `"multiple narrow/substitute markers"`. The exception class stays `ValueError` (consistent with F2 — both are static schema design errors, both are `ValueError`; no exception-class promotion).
- **Tuple, not set**: the four-marker enumeration is rendered as a tuple literal `(Narrow, NarrowPrefix, NarrowSuperset, Substitute)` in both error messages. Python `{set}` literal rendering is order-unstable; tuples preserve order so error strings stay deterministic across runs.

### Step 4: Add fixture configs and tests

In `tests/test_resolver.py`, add fixture configs near the existing `IntCfg` / `ListCfg` block:

```python
class PrefixCfg(BaseModel):
    paths: Annotated[list[str], NarrowPrefix] = []


class SupersetCfg(BaseModel):
    deny: Annotated[list[str], NarrowSuperset] = []


class PrefixOnIntCfg(BaseModel):
    cap: Annotated[int, NarrowPrefix] = 100  # type-mismatch fixture


class SupersetOnIntCfg(BaseModel):
    cap: Annotated[int, NarrowSuperset] = 100


class NarrowPlusPrefixCfg(BaseModel):
    bad: Annotated[list[str], Narrow, NarrowPrefix] = []


class PrefixPlusSupersetCfg(BaseModel):
    bad: Annotated[list[str], NarrowPrefix, NarrowSuperset] = []


class PrefixPlusSubstituteCfg(BaseModel):
    bad: Annotated[list[str], NarrowPrefix, Substitute] = []


class SupersetPlusSubstituteCfg(BaseModel):
    bad: Annotated[list[str], NarrowSuperset, Substitute] = []


class NarrowPlusSupersetCfg(BaseModel):
    bad: Annotated[list[str], Narrow, NarrowSuperset] = []
```

And import at the top:

```python
from the_one.tools.resolver import (
    Narrow, NarrowPrefix, NarrowSuperset, Substitute, _EmptyConfig, resolve,
)
```

Test classes (at the bottom of the file, before any tail-end smoke tests):

```python
class TestNarrowPrefix:
    """`NarrowPrefix` non-list type-error uses NotImplementedError to match
    F2's Narrow-on-str precedent (resolver.py:116). Test for it accordingly."""

    def test_happy_descendant(self) -> None:
        result = resolve(
            PrefixCfg, {"paths": ["/home/u"]}, {"paths": ["/home/u/projects"]}
        )
        assert result.paths == ["/home/u/projects"]

    def test_happy_equal_to_root(self) -> None:
        result = resolve(
            PrefixCfg, {"paths": ["/home/u"]}, {"paths": ["/home/u"]}
        )
        assert result.paths == ["/home/u"]

    def test_happy_multi_root_match(self) -> None:
        # agent path /home/u/x is descendant of one of the two tool roots.
        result = resolve(
            PrefixCfg,
            {"paths": ["/home/u", "/var/data"]},
            {"paths": ["/home/u/x"]},
        )
        assert result.paths == ["/home/u/x"]

    def test_widen_outside_any_root_raises(self) -> None:
        with pytest.raises(ValueError) as exc:
            resolve(PrefixCfg, {"paths": ["/home/u"]}, {"paths": ["/etc"]})
        assert "widens" in str(exc.value)
        assert "not within" in str(exc.value)

    def test_non_list_raises_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError) as exc:
            resolve(PrefixOnIntCfg, {"cap": 100}, {"cap": 50})
        assert "non-list" in str(exc.value)


class TestNarrowSuperset:
    """`NarrowSuperset` membership uses raw == on values; canonicalization is
    consumer-side. Non-list type-error uses NotImplementedError, matching
    F2's Narrow-on-str precedent."""

    def test_happy_agent_superset(self) -> None:
        result = resolve(
            SupersetCfg, {"deny": ["/etc"]}, {"deny": ["/etc", "/proc"]}
        )
        assert result.deny == ["/etc", "/proc"]

    def test_happy_equal(self) -> None:
        result = resolve(SupersetCfg, {"deny": ["/etc"]}, {"deny": ["/etc"]})
        assert result.deny == ["/etc"]

    def test_widen_drops_tool_entry_raises(self) -> None:
        with pytest.raises(ValueError) as exc:
            resolve(
                SupersetCfg,
                {"deny": ["/etc", "/proc"]},
                {"deny": ["/etc"]},  # missing /proc — narrows the denylist
            )
        assert "widens" in str(exc.value)
        assert "/proc" in str(exc.value)

    def test_non_list_raises_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError) as exc:
            resolve(SupersetOnIntCfg, {"cap": 100}, {"cap": 50})
        assert "non-list" in str(exc.value)


class TestMutualExclusion:
    @pytest.mark.parametrize(
        "schema",
        [
            NarrowPlusPrefixCfg,
            NarrowPlusSupersetCfg,
            PrefixPlusSupersetCfg,
            PrefixPlusSubstituteCfg,
            SupersetPlusSubstituteCfg,
        ],
    )
    def test_multi_marker_rejected(self, schema: type[BaseModel]) -> None:
        with pytest.raises(ValueError) as exc:
            resolve(schema, {"bad": []}, {"bad": []})
        assert "multiple narrow/substitute" in str(exc.value)
```

Five net-new pairs are covered; the pre-existing `Narrow+Substitute` pair stays under `test_both_markers_raises` (substring updated; class unchanged).

**Update F2's `TestMarkerErrors::test_both_markers_raises`**: keep `pytest.raises(ValueError)`; change the asserted substring from `"both Narrow and Substitute"` to `"multiple narrow/substitute"`. Add an inline comment noting the L1 message rename.

**Leave F2's `TestMarkerErrors::test_no_marker_raises` unchanged**: the new error message preserves the `"no Narrow/Substitute marker"` substring; the existing assertion at `tests/test_resolver.py:196` continues to match.

### Step 5: Update agents.md

Two edits:

1. Update `### the_one/tools/` table row for `resolver.py` (line ~82) to mention all four markers:
   ```
   | `resolver.py` | `Narrow`, `NarrowPrefix`, `NarrowSuperset`, `Substitute`, `resolve` | Tool policy resolver — composes tool-level + agent-level configs per per-key marker semantics |
   ```

2. Extend the **Tool Policy Resolver** section (line ~167-174) with two new bullet items for the new markers, e.g.:
   - `Annotated[type, NarrowPrefix]` — agent override on a `list[str]` of paths is narrowing iff every agent entry is descendant-of (or equal to) at least one tool entry, checked via `the_one.platform.paths.is_within`. Used by `FilesystemConfig.path_allowlist`.
   - `Annotated[type, NarrowSuperset]` — agent override on a `list[T]` is narrowing iff every tool entry is also in the agent value (agent ⊇ tool — agent adds restrictions). Used by `FilesystemConfig.path_denylist`.

3. Add a NEW paragraph (best placed near the existing "Continue Signal" / end of Tool Policy Resolver block; before "## Browser test fixtures") titled `### Test conventions and schema metadata`:
   ```
   ### Test conventions and schema metadata

   Tests monkeypatch built-in tool registration via
   `the_one.tools.builtins._TOOL_CLASSES` (module-level dict) — this is the
   supported seam; do NOT reach into `BuiltinToolProvider` internals.
   See `tests/CONVENTIONS.md` for the four established test patterns
   (asyncio_mode auto, monkeypatch.setenv HOME for tilde-expansion tests,
   httpx MockTransport `_install_mock` recursion-avoidance, kill+reap
   timeout-budget assertions).

   Pydantic Config schemas may declare UI-presentation hints via
   `Field(json_schema_extra={"ui_hint": "...", "ui_choices": [...]})`
   so the F6 admin form generator renders finite-set fields (e.g.,
   read-size cap, redirect cap) as dropdowns rather than free-form
   numeric inputs. The convention introduced in F3 Decision 11:
   `ui_hint` is the rendering strategy ("dropdown", future: "slider",
   "toggle"); `ui_choices` is a list of `{"value": ..., "label": ...}`
   dicts. F4-F6 should reuse the same metadata keys for any
   finite-value configuration field.
   ```

### Step 6: Create tests/CONVENTIONS.md

Create the file at `tests/CONVENTIONS.md` with four sections (one per pattern). Use this skeleton:

```markdown
# Test conventions

Cross-cutting test patterns established during F2 (Cross-Platform Foundations).
New tests should reuse these patterns rather than reinvent them.

---

## 1. asyncio_mode = "auto"

`pyproject.toml` sets `[tool.pytest.ini_options] asyncio_mode = "auto"`. Async
tests are written as plain `async def test_x():` — no `@pytest.mark.asyncio`
decorator needed. pytest-asyncio applies the marker automatically.

```python
async def test_read_file_happy(tmp_path):
    f = tmp_path / "x.txt"
    f.write_text("hi")
    result = await ReadFileTool().execute(path=str(f))
    assert "hi" in result
```

---

## 2. monkeypatch.setenv("HOME", str(tmp_path))

Tests that rely on `~` expansion or `Path.home()` set HOME to a tmp_path so
the tilde resolves into an isolated test directory. Avoid `Path.home()`-stub
patterns; the env-var approach interacts correctly with `expanduser()` calls
deep inside platform helpers.

```python
async def test_read_under_tilde(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    target = tmp_path / "doc.txt"
    target.write_text("contents")
    result = await ReadFileTool().execute(path="~/doc.txt")
    assert "contents" in result
```

---

## 3. httpx MockTransport with _install_mock recursion-avoidance

Web tool tests inject controlled HTTP responses via `httpx.MockTransport`.
Capture `original = httpx.AsyncClient` BEFORE `monkeypatch.setattr` so the
factory's call to `original(...)` does not recurse through the patched symbol.

```python
def _install_mock(monkeypatch, handler):
    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient   # capture before patch

    def factory(*args, **kwargs):
        kwargs.pop("transport", None)
        return original(*args, transport=transport, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


async def test_http_get_200(monkeypatch):
    def handler(req):
        return httpx.Response(200, text="hello")
    _install_mock(monkeypatch, handler)
    result = await HttpRequestTool().execute(method="GET", url="https://x.test/")
    assert result.startswith("[200]") and "hello" in result
```

---

## 4. kill+reap timeout-budget assertions

Tests that exercise process timeout paths assert the kill+reap returns within
a small wall-clock budget — broken kill+reap blocks for the full underlying
sleep. Use `time.monotonic()` deltas, not framework timers.

```python
import time

async def test_shell_timeout_kills_fast(monkeypatch):
    start = time.monotonic()
    result = await ShellTool().execute(command="sleep 5", timeout_seconds=0.5)
    elapsed = time.monotonic() - start
    assert elapsed < 3.0, f"kill+reap blocked: {elapsed}s"
    assert "[error]" in result
```

The 3-second budget is intentionally generous (CI scheduler latency);
typical local runs see <1s. A regression in the kill+reap path manifests
as a 5s+ test — the assertion catches it before the runtime explodes.
```

### Step 7: Run lint + tests; iterate until green

```bash
docker exec the-one ruff check the_one/tools/resolver.py tests/test_resolver.py
docker exec the-one ruff format the_one/tools/resolver.py tests/test_resolver.py
docker exec the-one pytest tests/test_resolver.py -v
make test-unit
```

Iterate on failures until the resolver test class is green and the broader unit suite is at-or-above the F2 baseline (modulo pre-existing CSS-token red).

### Step 8: Update flight log

Append a `### Leg 01 — Resolver narrow markers + maintenance docs` entry to `flight-log.md` under "Leg Progress" with: status `landed`, started/completed timestamps, summary of changes, and any notes (e.g. the `test_both_markers_raises` substring update — class stays `ValueError`, message reworded from `"both Narrow and Substitute"` to `"multiple narrow/substitute markers"`).

### Step 9: Update leg + flight + post-completion checklist

- Set this leg's `Status` to `landed` (NOT `completed` — the leg-execution skill defers per-leg completion to the final commit step; agentic-workflow batches code review and commit at the end of all autonomous legs).
- Do NOT check off this leg in `flight.md` yet — that happens at the final commit.
- Do NOT commit. Do NOT signal `[COMPLETE:leg]`. Signal `[HANDOFF:review-needed]`.

## Edge Cases

- **F2 test substring update**: `tests/test_resolver.py::TestMarkerErrors::test_both_markers_raises` currently asserts `pytest.raises(ValueError)` with substring `"both Narrow and Substitute"`. L1 keeps the exception class as `ValueError` (no class promotion) and reworks the message to use substring `"multiple narrow/substitute markers"`. Update only the asserted substring in the same commit. `test_no_marker_raises` is preserved as-is (its substring `"no Narrow/Substitute marker"` is retained verbatim in the new message).
- **`is_within` canonicalization on non-existent paths**: `is_within` calls `canonicalize` (= `Path.expanduser().resolve(strict=False)`), which succeeds on non-existent paths. Prefix tests therefore work without touching the filesystem. Tests use literal POSIX strings (e.g. `"/home/u"`), no `tmp_path` setup needed for the prefix dispatch tests.
- **Non-list `NarrowPrefix` / `NarrowSuperset` raise `NotImplementedError`** (not `TypeError` or `ValueError`): matches F2's `Narrow`-on-`str` precedent at `resolver.py:116`. A schema author wiring `NarrowPrefix` onto a `bool` is the same logical error class as `Narrow` on `str` — both surface as `NotImplementedError` for contract uniformity. Tests pin this with `pytest.raises(NotImplementedError)`.
- **Marker count > 2**: a schema field annotated with three or four markers is exotic but possible — `marker_count > 1` covers all such cases uniformly. No need for separate `> 2` / `> 3` branches.
- **Empty `agent_override` dict for a field**: F2's existing behavior (skip the key entirely) is preserved — the marker-count checks only run when the key is in the override dict.
- **`is_within` import location**: module-top import in `the_one/tools/resolver.py`. There is no circular dependency between `tools/resolver.py` and `platform/paths.py` (resolver currently imports nothing from platform; paths imports nothing from tools). Module-top is one fewer surprise for readers.
- **`tests/CONVENTIONS.md` linting**: ensure the file passes any markdown-lint rules in CI. If CI doesn't lint markdown, no special handling needed; just keep it under 200 lines and use fenced code blocks with language tags (`python`, `bash`).
- **agents.md edits — search anchors**: when editing `agents.md`, prefer `Edit` with unique surrounding context (not `replace_all`). Anchor edits on full-sentence context strings (e.g., the literal `### Tool Policy Resolver` heading) rather than line numbers, which are volatile.

## Files Affected

- `the_one/tools/resolver.py` — add 2 marker classes (~30 LoC including docstrings), 2 dispatch helpers (~30 LoC), update `resolve()`'s per-key dispatch (~15 LoC), add module-top `from the_one.platform.paths import is_within` import. Net ~70-80 added LoC.
- `tests/test_resolver.py` — add ~9 fixture configs (~30 LoC), 3 test classes (~80 LoC), update 1 existing test substring (`test_both_markers_raises`). Net ~120 added LoC.
- `tests/CONVENTIONS.md` — new file, ~150 LoC.
- `the_one/agents.md` — update 1 table row, extend Tool Policy Resolver bullet list (+2 bullets), add a `### Test conventions and schema metadata` paragraph. Net ~30 added LoC.

Total: ~370 added LoC across 4 files; matches the flight estimate of "~100-130 LoC change + docs".

**Out of scope for L1 (deferred to other legs)**:

- **`CLAUDE.md` Tool Configuration Layer section** at `CLAUDE.md:103` references the old marker docs (single Narrow/Substitute pair). The flight schedules this update for L8 (integration verification, see flight.md L8 entry: "update `CLAUDE.md` Tool Configuration Layer section to document `NarrowPrefix` / `NarrowSuperset` semantics"). L1 deliberately preserves the F2 substring `"no Narrow/Substitute marker"` in the resolver error message so any code/docs referencing the old wording continue to match — minimizing the risk of a hidden break before L8 catches up. Anyone running the L1 reviewer should NOT flag CLAUDE.md as a gap; it's a known deferral.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`** (commit + leg-completion deferred to end-of-flight per agentic-workflow):

- [ ] All acceptance criteria verified
- [ ] Tests passing (`pytest tests/test_resolver.py -v`; `make test-unit` at-or-above F2 baseline)
- [ ] `ruff check` and `ruff format --check` clean on changed files
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] DO NOT check off this leg in `flight.md` (deferred to final commit)
- [ ] DO NOT commit; DO NOT signal `[COMPLETE:leg]`
- [ ] Signal `[HANDOFF:review-needed]`
