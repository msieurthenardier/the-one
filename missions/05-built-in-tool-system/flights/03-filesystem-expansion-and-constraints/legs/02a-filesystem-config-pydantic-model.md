# Leg: 02a-filesystem-config-pydantic-model

**Status**: landed
**Flight**: [Filesystem Expansion & Constraints](../flight.md)

## Objective

Define the per-category `FilesystemConfig` Pydantic model, the `DEFAULT_PATH_DENYLIST` constant, and the `ConstraintError` exception type in `the_one/tools/filesystem.py`. Eagerly compute and cache canonical-path forms via `model_post_init` + `PrivateAttr`. No tool code is touched in L2a — `_filesystem_check` helpers (L2b) and the existing-tool migration (L3) are separate legs.

## Context

L2a is the second scaffolding leg of Flight 03. L1 added `NarrowPrefix` / `NarrowSuperset` markers to the resolver. L2a uses them to declare the four constraint fields on `FilesystemConfig`. L2b adds the runtime helpers (`_filesystem_check`, etc.) that consume the config; L3-L6 wire all 9 tools to it.

**Relevant flight design decisions**:
- **Decision 2** — Per-category `FilesystemConfig` shared by all 9 filesystem tools. Four annotated fields: `path_allowlist: NarrowPrefix`, `path_denylist: NarrowSuperset`, `read_size_cap_bytes: Narrow`, `allow_binary_files: Narrow`. Pre-canonicalization caching uses `model_post_init` + `PrivateAttr` (NOT `@computed_field @property`).
- **Decision 1.5** — `ConstraintError(Exception)` defined here. Tool wrappers (in L3-L6) catch this type and format `[error] [constraint] {msg}`; environmental errors keep formatting `[error] {e}`.
- **Decision 3** — Default path allowlist `["~"]` and curated denylist (system secrets, browser/app data, agent internals, `/etc`/`/proc`/`/sys`/`/dev`/`/boot`/`/var/log`).
- **Decision 5** — `read_size_cap_bytes` default `1_048_576` (1 MiB), bounds `ge=1024, le=104_857_600`. Read-side only; doesn't cap writes.
- **Decision 11** — `read_size_cap_bytes` carries `Field(json_schema_extra={"ui_hint": "dropdown", "ui_choices": [...]})` so F6's admin form generator renders a dropdown, not a free-form numeric input.
- **Bool semantic** (Decision 2 sub-bullet) — `allow_binary_files: bool = False` (positively-named permission) so the resolver's natural "True = permissive, False = denied" reading aligns; an agent setting `True` over a tool default of `False` correctly raises (widening permission).

**Caching invariant**: `model_post_init` runs once at construction. `_canonical_allowlist` / `_canonical_denylist` are stored on `PrivateAttr` instances and read O(1) afterwards. `@computed_field @property` was explicitly rejected — those re-execute on every attribute access and would defeat the N×M canonicalize-avoidance.

## Inputs

Files that must exist (verified):
- `the_one/tools/resolver.py` — `Narrow`, `NarrowPrefix`, `NarrowSuperset` (L1, just landed)
- `the_one/platform/__init__.py` — re-exports `canonicalize` (F2)
- `the_one/platform/paths.py` — `canonicalize`, `is_within` (F2)
- `the_one/tools/base.py` — `Tool.Config: type[BaseModel] = _EmptyConfig` default (F2)
- `the_one/tools/filesystem.py` — current 89-line module with `ReadFileTool`, `WriteFileTool`, `ListDirTool` (untouched in L2a)
- `tests/test_resolver.py` — passes 39 tests (post-L1)

State that must be true:
- L1 has landed (resolver markers exported, tests green).
- Working tree clean except for F3 artifacts.
- Branch `flight/03-filesystem-expansion-and-constraints` checked out.

## Outputs

Files modified:
- `the_one/tools/filesystem.py` — adds (at module top, before the existing tool classes):
  - imports for `Annotated`, `Path`, `Any`, `BaseModel`, `Field`, `PrivateAttr`, the resolver markers (`Narrow`, `NarrowPrefix`, `NarrowSuperset`)
  - `ConstraintError(Exception)` class
  - `DEFAULT_PATH_DENYLIST: tuple[str, ...]` (tuple, not list — immutable module constant; converted to a list per-instance via `default_factory=lambda: list(DEFAULT_PATH_DENYLIST)`)
  - `FilesystemConfig(BaseModel)` with the 4 annotated fields + `_canonical_allowlist`/`_canonical_denylist` `PrivateAttr` + `model_post_init`
  - the existing `ReadFileTool` / `WriteFileTool` / `ListDirTool` classes are NOT modified in L2a (L3 migrates them)

Files created:
- `tests/test_filesystem_config.py` — new file, ~150 LoC. Covers default instantiation, resolver-level narrowing for each marker (happy + violation), the model_post_init caching invariant, and `Field.json_schema_extra` ui_hint round-trip via `model_json_schema()`.

State changes:
- No DB schema changes. No migrations. No runtime behavior change for any existing tool (L3 is the migration leg).

## Acceptance Criteria

- [ ] `the_one/tools/filesystem.py` exports `FilesystemConfig`, `DEFAULT_PATH_DENYLIST`, `ConstraintError` (in addition to the existing `ReadFileTool`/`WriteFileTool`/`ListDirTool`).
- [ ] `FilesystemConfig` has exactly four declared fields: `path_allowlist: Annotated[list[str], NarrowPrefix]` defaulting to `["~"]`; `path_denylist: Annotated[list[str], NarrowSuperset]` defaulting to a `list(DEFAULT_PATH_DENYLIST)`; `read_size_cap_bytes: Annotated[int, Narrow, Field(ge=1024, le=104_857_600, json_schema_extra={...})]` defaulting to `1_048_576`; `allow_binary_files: Annotated[bool, Narrow]` defaulting to `False`.
- [ ] `DEFAULT_PATH_DENYLIST` is a module-level `tuple[str, ...]` (immutable) containing every path listed in flight Decision 3 (16 entries: 8 credential / app paths, 4 browser/app data, 1 agent-internal, 6 system paths — note `~/.the-one/secrets` plus `/etc`, `/proc`, `/sys`, `/dev`, `/boot`, `/var/log`). Field default uses `default_factory=lambda: list(DEFAULT_PATH_DENYLIST)` so each Config instance owns its list.
- [ ] `model_post_init(__context)` runs after construction and populates `_canonical_allowlist: list[Path]` and `_canonical_denylist: list[Path]` `PrivateAttr` instances by mapping `canonicalize` over each input list.
- [ ] `_canonical_allowlist` / `_canonical_denylist` are `PrivateAttr(default_factory=list)` (NOT `@computed_field @property`); subsequent reads return the cached value without re-executing `canonicalize`.
- [ ] `ConstraintError` is an `Exception` subclass with a one-line docstring stating the formatted-error contract (`tool wrappers format as [error] [constraint] {msg}`).
- [ ] `read_size_cap_bytes`'s `Field(json_schema_extra={...})` carries the six dropdown choices listed in flight Decision 11 (`50KB`, `100KB`, `256KB`, `512KB`, `1MB`, `5MB` — bytes + label) under the `ui_hint: "dropdown"` key.
- [ ] `tests/test_filesystem_config.py::TestDefaultConstruction` covers: instantiates with no args; default `path_allowlist == ["~"]`; default `path_denylist` length matches `DEFAULT_PATH_DENYLIST`; default `read_size_cap_bytes == 1_048_576`; default `allow_binary_files is False`.
- [ ] `tests/test_filesystem_config.py::TestResolverIntegration` covers, using `the_one.tools.resolver.resolve`:
  - `path_allowlist` narrowing (agent path under tool root → pass; agent path outside → ValueError; non-list → NotImplementedError already covered by L1 generic resolver tests, no need to repeat for FilesystemConfig).
  - `path_denylist` narrowing (agent denylist ⊇ tool denylist → pass; agent drops a tool entry → ValueError).
  - `read_size_cap_bytes` narrowing (agent ≤ tool → pass; agent > tool → ValueError; outside `ge`/`le` bounds → Pydantic `ValidationError`).
  - `allow_binary_files` narrowing (agent True over tool False → ValueError; tool True / agent False → pass; both False → pass).
- [ ] `tests/test_filesystem_config.py::TestCachingInvariant` covers the model_post_init caching: monkeypatch `the_one.tools.filesystem.canonicalize` to a counter; instantiate `FilesystemConfig(path_allowlist=[...3 paths], path_denylist=[...4 paths])`; read `_canonical_allowlist` and `_canonical_denylist` 100 times each; assert `counter == 7` exactly (3 + 4) — proves no per-access recomputation.
- [ ] `tests/test_filesystem_config.py::TestUiHint` covers `ui_hint`/`ui_choices` round-trip via `FilesystemConfig.model_json_schema()`: assert the `read_size_cap_bytes` property carries `ui_hint == "dropdown"` and `len(ui_choices) == 6`.
- [ ] `make test-unit` passes (target: post-L1 baseline of 536 passed + ~17 new tests = ~553 passed, modulo the same pre-existing CSS-token red).
- [ ] `ruff check` and `ruff format --check` clean on changed files.

## Verification Steps

Static (after edit, before test run):

```bash
cd /home/cprch/projects/the-one

# Symbols exported
rg -n "^class FilesystemConfig\b" the_one/tools/filesystem.py        # 1
rg -n "^class ConstraintError\b" the_one/tools/filesystem.py         # 1
rg -n "^DEFAULT_PATH_DENYLIST\s*=" the_one/tools/filesystem.py        # 1

# 4 annotated fields
rg -n "Annotated\[(list\[str\]|int|bool)," the_one/tools/filesystem.py
# Expected: 4 matches (path_allowlist NarrowPrefix; path_denylist NarrowSuperset; read_size_cap_bytes Narrow; allow_binary_files Narrow)

# PrivateAttr (not @computed_field)
rg -n "PrivateAttr|model_post_init" the_one/tools/filesystem.py      # ≥3 matches
rg -n "@computed_field" the_one/tools/filesystem.py                  # 0 matches

# Existing tool classes unchanged
rg -n "^class ReadFileTool\b|^class WriteFileTool\b|^class ListDirTool\b" the_one/tools/filesystem.py
# Expected: 3 (no rename, no removal)

# Test file exists
test -f tests/test_filesystem_config.py && echo OK
```

Dynamic:

```bash
docker exec the-one pytest tests/test_filesystem_config.py -v
# Expected: ~17 tests (6 default + 10 resolver-integration + 1 caching + 1 ui-hint), all pass

# Resolver still green (no regression from L1)
docker exec the-one pytest tests/test_resolver.py -v
# Expected: 39 pass

# Full unit suite (sanity)
make test-unit
# Expected: post-L1 baseline of 536 passed + ~17 new tests = ~553 passed; only pre-existing CSS-token red

# Quick FilesystemConfig narrowing smoke
docker exec the-one python -c "
from the_one.tools.filesystem import FilesystemConfig
from the_one.tools.resolver import resolve
r = resolve(
    FilesystemConfig,
    {'path_allowlist': ['~/projects']},
    {'path_allowlist': ['~/projects/foo']},
)
assert r.path_allowlist == ['~/projects/foo']
try:
    resolve(
        FilesystemConfig,
        {'path_allowlist': ['~/projects']},
        {'path_allowlist': ['/etc']},
    )
    assert False
except ValueError as e:
    assert 'widens' in str(e).lower() or 'not within' in str(e).lower()
print('OK')
"

# Caching smoke
docker exec the-one python -c "
from the_one.tools.filesystem import FilesystemConfig
cfg = FilesystemConfig(path_allowlist=['~', '/tmp'], path_denylist=['/etc'])
# PrivateAttrs populated
assert len(cfg._canonical_allowlist) == 2
assert len(cfg._canonical_denylist) == 1
print('OK')
"
```

Quality:

```bash
docker exec the-one ruff check the_one/tools/filesystem.py tests/test_filesystem_config.py
docker exec the-one ruff format --check the_one/tools/filesystem.py tests/test_filesystem_config.py
```

## Implementation Guidance

### Step 1: Update `the_one/tools/filesystem.py` imports

The current file imports only `pathlib.Path`, `typing.Any`, `the_one.platform.canonicalize`, and `the_one.tools.base.Tool`. Add the new imports above the existing ones, grouped per the repo's style (stdlib → third-party → first-party):

```python
from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, Field, PrivateAttr

from the_one.platform import canonicalize
from the_one.tools.base import Tool
from the_one.tools.resolver import Narrow, NarrowPrefix, NarrowSuperset
```

### Step 2: Add `ConstraintError` immediately after the imports

```python
class ConstraintError(Exception):
    """Policy-driven refusal raised by filesystem tools and the
    `_filesystem_check` family. Tool wrappers catch this type and format
    `[error] [constraint] {msg}`; environmental exceptions still format
    `[error] {e}` so agents can distinguish policy refusals from runtime
    failures (Flight 3 Decision 1.5)."""
```

### Step 3: Add `DEFAULT_PATH_DENYLIST` constant

```python
DEFAULT_PATH_DENYLIST: tuple[str, ...] = (
    # System secrets / credentials (8)
    "~/.ssh",
    "~/.aws",
    "~/.gcloud",
    "~/.azure",
    "~/.config/gh",
    "~/.netrc",
    "~/.docker/config.json",
    "~/.kube",
    # Browser / app data (4)
    "~/.mozilla",
    "~/.config/google-chrome",
    "~/.config/Code",
    "~/.config/Slack",
    # Agent's own internals (1)
    "~/.the-one/secrets",
    # Outside ~ — system paths (6)
    "/etc",
    "/proc",
    "/sys",
    "/dev",
    "/boot",
    "/var/log",
)
```

Tuple chosen for immutability — operators / tests cannot accidentally mutate the module-level baseline. The Field default uses `default_factory=lambda: list(DEFAULT_PATH_DENYLIST)` so each instance owns its list (mutation by an agent's override doesn't poison the baseline).

### Step 4: Define `FilesystemConfig`

```python
class FilesystemConfig(BaseModel):
    """Per-category Config for all 9 filesystem tools (F3 Decision 2).

    Four constraint fields: path-scope allowlist (narrowing-by-prefix),
    path-scope denylist (narrowing-by-superset — agent ADDS restrictions),
    read-size cap (Narrow), allow-binary-files flag (Narrow with positive
    naming so resolver's natural True=permissive/False=denied reading aligns).

    Eagerly canonicalizes allowlist/denylist entries via `model_post_init`
    + `PrivateAttr`. NOT `@computed_field @property` — those re-execute on
    every access and would defeat the N×M canonicalize-avoidance.
    """

    path_allowlist: Annotated[list[str], NarrowPrefix] = ["~"]

    path_denylist: Annotated[list[str], NarrowSuperset] = Field(
        default_factory=lambda: list(DEFAULT_PATH_DENYLIST)
    )

    read_size_cap_bytes: Annotated[
        int,
        Narrow,
        Field(
            ge=1024,
            le=104_857_600,
            json_schema_extra={
                "ui_hint": "dropdown",
                "ui_choices": [
                    {"value": 51_200, "label": "50KB — very small models"},
                    {"value": 102_400, "label": "100KB — small/7B-class friendly"},
                    {"value": 262_144, "label": "256KB — most models comfortable"},
                    {"value": 524_288, "label": "512KB — middle"},
                    {"value": 1_048_576, "label": "1MB — default (Opus 200K headroom)"},
                    {"value": 5_242_880, "label": "5MB — Opus 1M only"},
                ],
            },
        ),
    ] = 1_048_576

    allow_binary_files: Annotated[bool, Narrow] = False

    # Eagerly-computed canonical paths cached as PrivateAttr.
    # NOT @computed_field @property — those re-execute on every access and
    # would defeat the N×M canonicalize avoidance. PrivateAttr stores the
    # value once at model_post_init; subsequent reads are O(1).
    _canonical_allowlist: list[Path] = PrivateAttr(default_factory=list)
    _canonical_denylist: list[Path] = PrivateAttr(default_factory=list)

    def model_post_init(self, __context: Any) -> None:
        # Runs after Pydantic finishes constructing the model. Compute the
        # canonical paths once and stash them on the private attrs.
        self._canonical_allowlist = [canonicalize(p) for p in self.path_allowlist]
        self._canonical_denylist = [canonicalize(p) for p in self.path_denylist]
```

### Step 5: Verify the existing tool classes remain unchanged

`ReadFileTool`, `WriteFileTool`, `ListDirTool` keep their L2a-baseline shape — no `Config` attribute changes, no `_filesystem_check` calls. L3 migrates them. The L2a diff is purely additive at the top of the file.

### Step 6: Create tests/test_filesystem_config.py

```python
"""Tests for FilesystemConfig (F3 L2a) — Pydantic shape, defaults, resolver
integration, model_post_init caching invariant, and ui_hint metadata."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from the_one.tools.filesystem import (
    DEFAULT_PATH_DENYLIST,
    FilesystemConfig,
)
from the_one.tools.resolver import resolve


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


class TestDefaultConstruction:
    def test_zero_arg_construction_succeeds(self) -> None:
        cfg = FilesystemConfig()
        assert isinstance(cfg, FilesystemConfig)

    def test_default_path_allowlist_is_tilde(self) -> None:
        cfg = FilesystemConfig()
        assert cfg.path_allowlist == ["~"]

    def test_default_denylist_matches_module_constant(self) -> None:
        cfg = FilesystemConfig()
        assert cfg.path_denylist == list(DEFAULT_PATH_DENYLIST)

    def test_default_denylist_does_not_share_module_list(self) -> None:
        # Mutating one Config's denylist must not poison the module baseline.
        cfg1 = FilesystemConfig()
        cfg1.path_denylist.append("/should-not-leak")
        cfg2 = FilesystemConfig()
        assert "/should-not-leak" not in cfg2.path_denylist

    def test_default_read_size_cap_is_1mib(self) -> None:
        cfg = FilesystemConfig()
        assert cfg.read_size_cap_bytes == 1_048_576

    def test_default_allow_binary_files_false(self) -> None:
        cfg = FilesystemConfig()
        assert cfg.allow_binary_files is False


# ---------------------------------------------------------------------------
# Resolver integration — narrowing semantics on each marker
# ---------------------------------------------------------------------------


class TestResolverIntegration:
    """FilesystemConfig-specific shape: the four fields exist, are wired to
    the right markers, bounds fire, and the bool semantic is positively-named.

    NOTE: marker mechanics themselves (NarrowPrefix descendant rules,
    NarrowSuperset agent-⊇-tool rules, etc.) are covered generically by
    `tests/test_resolver.py` (L1). These FilesystemConfig tests duplicate
    a small slice of that coverage on purpose — to pin the per-field
    wiring (right marker on right field) end-to-end on this concrete
    schema. Tests use absolute paths instead of `~/projects` so they
    don't depend on the runtime HOME (matches L1's TestNarrowPrefix
    convention)."""

    def test_path_allowlist_narrow_descendant(self) -> None:
        r = resolve(
            FilesystemConfig,
            {"path_allowlist": ["/home/u/projects"]},
            {"path_allowlist": ["/home/u/projects/foo"]},
        )
        assert r.path_allowlist == ["/home/u/projects/foo"]

    def test_path_allowlist_widen_outside_root_raises(self) -> None:
        with pytest.raises(ValueError) as exc:
            resolve(
                FilesystemConfig,
                {"path_allowlist": ["/home/u/projects"]},
                {"path_allowlist": ["/etc"]},
            )
        assert "widens" in str(exc.value).lower() or "not within" in str(exc.value).lower()

    def test_path_denylist_agent_superset(self) -> None:
        r = resolve(
            FilesystemConfig,
            {"path_denylist": ["/etc"]},
            {"path_denylist": ["/etc", "/proc"]},
        )
        assert r.path_denylist == ["/etc", "/proc"]

    def test_path_denylist_drops_tool_entry_raises(self) -> None:
        with pytest.raises(ValueError) as exc:
            resolve(
                FilesystemConfig,
                {"path_denylist": ["/etc", "/proc"]},
                {"path_denylist": ["/etc"]},
            )
        assert "widens" in str(exc.value)

    def test_read_size_cap_narrow(self) -> None:
        r = resolve(
            FilesystemConfig,
            {"read_size_cap_bytes": 1_048_576},
            {"read_size_cap_bytes": 102_400},
        )
        assert r.read_size_cap_bytes == 102_400

    def test_read_size_cap_widen_raises(self) -> None:
        with pytest.raises(ValueError):
            resolve(
                FilesystemConfig,
                {"read_size_cap_bytes": 102_400},
                {"read_size_cap_bytes": 1_048_576},
            )

    # Bounds tests bypass `resolve()` and call FilesystemConfig() directly —
    # they verify Pydantic's `ge`/`le` schema validation independent of the
    # resolver path. (Through `resolve()`, the Narrow check passes first
    # because 512 <= tool_default; then `model_validate(merged)` raises
    # ValidationError. Both paths converge on rejection.)
    def test_read_size_cap_below_floor_raises_validation(self) -> None:
        with pytest.raises(ValidationError):
            FilesystemConfig(read_size_cap_bytes=512)  # under 1024 floor

    def test_read_size_cap_above_ceiling_raises_validation(self) -> None:
        with pytest.raises(ValidationError):
            FilesystemConfig(read_size_cap_bytes=200_000_000)  # over 100MB ceiling

    def test_allow_binary_widen_raises(self) -> None:
        with pytest.raises(ValueError):
            resolve(
                FilesystemConfig,
                {"allow_binary_files": False},
                {"allow_binary_files": True},
            )

    def test_allow_binary_revoke_passes(self) -> None:
        r = resolve(
            FilesystemConfig,
            {"allow_binary_files": True},
            {"allow_binary_files": False},
        )
        assert r.allow_binary_files is False


# ---------------------------------------------------------------------------
# Caching invariant — model_post_init runs once
# ---------------------------------------------------------------------------


class TestCachingInvariant:
    def test_canonicalize_called_exactly_n_plus_m_times(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from the_one.tools import filesystem as fs_module

        counter = {"n": 0}
        original = fs_module.canonicalize

        def counting_canonicalize(p: Any) -> Any:
            counter["n"] += 1
            return original(p)

        monkeypatch.setattr(fs_module, "canonicalize", counting_canonicalize)

        cfg = FilesystemConfig(
            path_allowlist=["~", "/tmp", "/var/data"],
            path_denylist=["/etc", "/proc", "/sys", "/dev"],
        )
        # 3 + 4 = 7 — counter resets the assertion baseline before reads.
        baseline = counter["n"]
        assert baseline == 7, f"expected 7 init calls, got {baseline}"

        # 100 reads of each PrivateAttr — canonicalize must NOT be re-called.
        for _ in range(100):
            _ = cfg._canonical_allowlist
            _ = cfg._canonical_denylist
        assert counter["n"] == 7, (
            f"canonicalize re-executed on read: counter went from {baseline} to {counter['n']}"
        )


# ---------------------------------------------------------------------------
# UI hint round-trip via model_json_schema
# ---------------------------------------------------------------------------


class TestUiHint:
    def test_read_size_cap_carries_dropdown_hint(self) -> None:
        schema = FilesystemConfig.model_json_schema()
        prop = schema["properties"]["read_size_cap_bytes"]
        assert prop.get("ui_hint") == "dropdown"
        assert "ui_choices" in prop
        assert len(prop["ui_choices"]) == 6
        # Sanity: 1MB choice present
        values = [c["value"] for c in prop["ui_choices"]]
        assert 1_048_576 in values
```

### Step 7: Run lint + tests; iterate

```bash
docker exec the-one ruff check the_one/tools/filesystem.py tests/test_filesystem_config.py
docker exec the-one ruff format the_one/tools/filesystem.py tests/test_filesystem_config.py
docker exec the-one pytest tests/test_filesystem_config.py -v
docker exec the-one pytest tests/test_resolver.py -v   # confirm L1 still green
make test-unit
```

### Step 8: Update flight log + leg status

- Append `### Leg 02a — FilesystemConfig Pydantic model` entry under "Leg Progress" in `flight-log.md`.
- Set leg `Status` to `landed`.
- Do NOT commit. Do NOT signal `[COMPLETE:leg]`. Signal `[HANDOFF:review-needed]`.

## Edge Cases

- **`default_factory` for the denylist**: Pydantic v2 requires `default_factory` (NOT `default=list(...)`) to avoid sharing a single list reference across instances. This is the same trap as Python's mutable-default-arg gotcha for function defaults. The Field default uses `default_factory=lambda: list(DEFAULT_PATH_DENYLIST)`; instances mutating their `path_denylist` cannot poison sibling instances or the module constant.
- **Tilde in default `path_allowlist`**: `["~"]` is the literal string. `model_post_init` calls `canonicalize` which expands the tilde via `Path.expanduser()`. Tests do NOT rely on `os.environ["HOME"]` being set to a specific value for caching tests — they only count canonicalize invocations, not their results.
- **`PrivateAttr` Pydantic-v2 nuance**: `PrivateAttr` uses Python's underscore-prefix convention to skip Pydantic field machinery (no validation, no JSON schema entry, no inclusion in `model_dump`). Mutation IS allowed (unlike regular fields when `model_config["frozen"] = True`). `model_post_init` is the canonical hook — Pydantic v2 calls it after construction, exactly like `__init__` minus the validation phase.
- **No `Config` attribute change yet**: L2a only ADDS the `FilesystemConfig` class; it does NOT set `ReadFileTool.Config = FilesystemConfig`. That wiring lands in L3 alongside the actual `_filesystem_check` call sites. Tests for `ReadFileTool` / `WriteFileTool` / `ListDirTool` therefore continue passing untouched in L2a.
- **`ConstraintError` not raised yet**: L2a defines the type but no code raises it. L2b's `_filesystem_check` is the first raise site. Tests for `ConstraintError`-raising behavior are out of L2a scope.
- **`ui_hint`/`ui_choices` JSON-schema location**: Pydantic v2 puts `json_schema_extra` content directly into the generated schema's per-property dict (NOT nested under a `metadata` key). The test reads `schema["properties"]["read_size_cap_bytes"]["ui_hint"]` directly. If a future Pydantic version changes nesting, the test will catch it via the assertion failure.
- **Counting-monkeypatch caveat**: `monkeypatch.setattr(fs_module, "canonicalize", ...)` patches the symbol that `FilesystemConfig.model_post_init` reads via the module global. The `model_post_init` body calls `canonicalize(p)` (unqualified) — which Python resolves via the module's `__dict__`. Monkeypatching the module attribute therefore intercepts the call. If the implementation is ever refactored to `from the_one.platform.paths import canonicalize` directly (instead of via the platform package re-export), the patch target may need adjusting.
- **Mutual-exclusion with L1 markers**: `FilesystemConfig` uses `NarrowPrefix` on `path_allowlist`, `NarrowSuperset` on `path_denylist`, `Narrow` on `read_size_cap_bytes` and `allow_binary_files`. Each field has exactly one marker — the L1 `marker_count > 1` check stays silent. No need to test mutual exclusion here (covered in L1).
- **Empty denylist**: An operator can override the tool-level config to `{"path_denylist": []}` if they want a permissive baseline. `NarrowSuperset` then trivially passes any agent-level value (every entry of the empty set is in any list). Acceptable; the operator owns this decision.
- **Asymmetric `Field(...)` placement is intentional**: `path_denylist` puts `Field(default_factory=...)` on the RHS (`= Field(default_factory=lambda: list(DEFAULT_PATH_DENYLIST))`) because there are no other Field knobs to declare alongside the marker. `read_size_cap_bytes` puts `Field(...)` *inside* the `Annotated[]` metadata (alongside `Narrow`) because `ge`/`le`/`json_schema_extra` colocate naturally with the marker. Both shapes are valid Pydantic v2 with identical default semantics — the asymmetry follows readability, not a Pydantic constraint. Future readers should not "normalize" them.
- **Forward reference for L2b**: `_canonical_allowlist` / `_canonical_denylist` are `PrivateAttr` — accessed via the underscore-prefixed name. L2b's `_filesystem_check` is a module-private helper that lives in the same `the_one/tools/filesystem.py` module, so reaching into `cfg._canonical_allowlist` is in-module access (not consumer code). No public-property alias needed; if a future leg needs cross-module access, add a `canonical_allowlist` `@property` then.

## Files Affected

- `the_one/tools/filesystem.py` — additive only. Imports (~5 added lines), `ConstraintError` (~5), `DEFAULT_PATH_DENYLIST` (~22), `FilesystemConfig` (~50). Net ~80 added LoC. Existing tool classes unchanged.
- `tests/test_filesystem_config.py` — new file, ~150 LoC.

Total: ~230 LoC across 2 files.

**Out of scope for L2a (deferred to subsequent legs)**:

- `_filesystem_check`, `_filesystem_check_write_parent`, `_is_descendant`, `_check_read_size`, `_is_binary` runtime helpers → L2b.
- Wiring `Config = FilesystemConfig` on existing tools and integrating `_filesystem_check` into their `execute` methods → L3.
- Adding new tools (`edit_file`, `delete_file`, `move_file`, `mkdir`, `glob`, `grep`) → L4-L6.
- `BuiltinToolProvider._TOOL_CLASSES` / Studio `TOOL_CATEGORIES` updates → L4-L6 (per new tool).
- CLAUDE.md / agents.md broader documentation refresh → L8.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`** (commit + leg-completion deferred to end-of-flight per agentic-workflow):

- [ ] All acceptance criteria verified
- [ ] Tests passing (`pytest tests/test_filesystem_config.py -v`; `pytest tests/test_resolver.py -v`; `make test-unit` at-or-above L1 baseline)
- [ ] `ruff check` and `ruff format --check` clean on changed files
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] DO NOT check off this leg in `flight.md` (deferred to final commit)
- [ ] DO NOT commit; DO NOT signal `[COMPLETE:leg]`
- [ ] Signal `[HANDOFF:review-needed]`
