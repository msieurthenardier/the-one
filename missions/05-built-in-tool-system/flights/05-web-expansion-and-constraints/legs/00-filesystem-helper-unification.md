# Leg: 00-filesystem-helper-unification

**Status**: landed
**Flight**: [Web Expansion & Constraints](../flight.md)

## Objective

Unify the four filesystem-scope-check helpers — F3's `_filesystem_check`, `_filesystem_check_write_parent`, `_filesystem_check_write_path`, and F4's `_cwd_check` — into a single dispatched helper with a `CheckMode` enum. Existing names remain as thin shims so the 11 call sites in `the_one/tools/filesystem.py` and the call sites in `the_one/tools/execution.py` (and L4's upcoming `download_file`) compose cleanly. F3 + F4 test suites pass unchanged. The dispatch tail handles all four divergent post-canonicalize check shapes explicitly.

## Context

- **F4 Decision 8** deferred this unification to "post-F4 maintenance" because mixing filesystem cleanup with execution-tool design risked regressing F3.
- **F5 makes the case sharper**: `download_file` (L4) adds a 7th call site to the family. Now is the right time.
- **Architect feedback** flagged that the four call patterns have genuinely divergent post-checks:
  - `_filesystem_check`: scope only (READ).
  - `_filesystem_check_write_parent`: scope + assert parent exists (raises `FileNotFoundError`, NOT `ConstraintError`).
  - `_filesystem_check_write_path`: scope only on parent-canonicalize-then-compose.
  - `_cwd_check`: scope + `is_dir()` post-check.
  - The dispatch tail must encode all four explicitly so the unified helper's behavior is unambiguous.
- **Naming preserved**: existing function names (`_filesystem_check`, `_filesystem_check_write_parent`, `_filesystem_check_write_path`, `_cwd_check`) remain. The 2-arg call form (`_filesystem_check(path, cfg)`) continues to work — the new `mode` kwarg is optional with `CheckMode.READ` default. No call site touches change in this leg.

## Inputs

- `the_one/tools/filesystem.py` — `_filesystem_check`, `_filesystem_check_write_parent`, `_filesystem_check_write_path`, `_is_descendant`, `canonicalize` (from `the_one.platform`).
- `the_one/tools/execution.py:325` — `_cwd_check` (delegates to `_filesystem_check`).
- F3 test suite (`tests/test_filesystem_helpers.py`, `tests/test_filesystem_tools.py`) — regression net.
- F4 test suite (`tests/test_execution_helpers.py::TestCwdCheck`) — regression net.

## Outputs

- `the_one/tools/filesystem.py`:
  - Add `class CheckMode(str, Enum)` with four values: `READ`, `WRITE_NEW`, `WRITE_EXISTING_PARENT`, `DIRECTORY`. `str` mixin for ergonomic test asserts (`mode == "read"` works).
  - Rewrite `_filesystem_check(path, cfg, mode=CheckMode.READ) -> Path` as the dispatcher. The 2-arg call form (`mode=READ` default) preserves all existing call-site behavior.
  - `_filesystem_check_write_parent(path, cfg)` becomes a one-line shim: `return _filesystem_check(path, cfg, CheckMode.WRITE_EXISTING_PARENT)`.
  - `_filesystem_check_write_path(path, cfg)` becomes a one-line shim: `return _filesystem_check(path, cfg, CheckMode.WRITE_NEW)`.
  - **Existing F3 test imports** (`from the_one.tools.filesystem import _filesystem_check_write_parent, _filesystem_check_write_path`) continue to resolve via the shims.
- `the_one/tools/execution.py`:
  - `_cwd_check(cwd, fs_cfg)` becomes a one-line shim: `return _filesystem_check(cwd, fs_cfg, CheckMode.DIRECTORY)`.
  - Update the docstring to reflect the unified dispatch.
- `tests/test_filesystem_helpers.py`:
  - F3 tests pass unchanged (existing assertions cover READ, WRITE_NEW, WRITE_EXISTING_PARENT post-checks).
  - **New `TestCheckModeDispatch` class** with one parametrized test per mode that asserts (a) all four modes share the same canonicalize+allowlist+denylist core and (b) each mode's post-check fires correctly on the same in-scope path with different on-disk shapes:
    - READ: existence not required; out-of-scope refused; in-scope allowed.
    - WRITE_NEW: parent-canonicalize-then-compose; out-of-scope refused; in-scope-but-missing-parent allowed.
    - WRITE_EXISTING_PARENT: parent-canonicalize-then-compose; in-scope-but-missing-parent raises `FileNotFoundError`; in-scope-with-parent allowed.
    - DIRECTORY: scope check + `is_dir()` post-check; in-scope file (not dir) raises `ConstraintError` with `"does not exist or is not a directory"` wording; in-scope dir allowed.
- `tests/test_execution_helpers.py::TestCwdCheck`:
  - F4 tests pass unchanged. The `_cwd_check` shim's behavior (delegates to `CheckMode.DIRECTORY`) is identical to the pre-L0 implementation.

## Acceptance Criteria

- [x] `the_one/tools/filesystem.py` defines `class CheckMode(str, Enum)` with `READ`, `WRITE_NEW`, `WRITE_EXISTING_PARENT`, `DIRECTORY`.
- [x] `_filesystem_check(path, cfg, mode=CheckMode.READ)` is the dispatcher; the 2-arg call form preserves identical behavior to the pre-L0 helper.
- [x] `_filesystem_check_write_parent` is a one-line shim calling the dispatcher with `CheckMode.WRITE_EXISTING_PARENT`.
- [x] `_filesystem_check_write_path` is a one-line shim calling the dispatcher with `CheckMode.WRITE_NEW`.
- [x] `_cwd_check` (in `execution.py`) is a one-line shim calling the dispatcher with `CheckMode.DIRECTORY`.
- [x] All four modes share the same canonicalize+allowlist+denylist core (no duplicate logic).
- [x] **F3 test suite (`tests/test_filesystem_helpers.py`, `tests/test_filesystem_tools.py`) passes unchanged.**
- [x] **F4 test suite (`tests/test_execution_helpers.py::TestCwdCheck`) passes unchanged.**
- [x] New `TestCheckModeDispatch` class in `tests/test_filesystem_helpers.py` with parametrized tests covering all four modes against the same in-scope path with different on-disk shapes.
- [x] **DIRECTORY mode preserves the `"does not exist or is not a directory"` error message** (F4 wording — agents downstream depend on it).
- [x] **WRITE_EXISTING_PARENT raises `FileNotFoundError` (NOT `ConstraintError`)** when parent is in-scope but missing — F3's deliberate distinction between policy refusal and environmental error.
- [x] No call site in `the_one/tools/` outside this leg's scope is modified — the existing two-arg `_filesystem_check(path, cfg)` invocation form still works at all 7 sites.
- [x] `make test-unit` (full suite) green (modulo pre-existing CSS-token red).
- [x] `ruff check` clean on touched files.

## Verification Steps

```bash
# Module shape
docker exec the-one python -c "
from the_one.tools.filesystem import (
    CheckMode, _filesystem_check,
    _filesystem_check_write_parent, _filesystem_check_write_path,
)
from the_one.tools.execution import _cwd_check
assert hasattr(CheckMode, 'READ')
assert hasattr(CheckMode, 'WRITE_NEW')
assert hasattr(CheckMode, 'WRITE_EXISTING_PARENT')
assert hasattr(CheckMode, 'DIRECTORY')
print('OK exports')
"

# Two-arg call form unchanged
docker exec the-one python -c "
from pathlib import Path
from the_one.tools.filesystem import _filesystem_check, FilesystemConfig
cfg = FilesystemConfig()
canonical = _filesystem_check(str(Path.home()), cfg)
assert canonical == Path.home(), canonical
print('OK 2-arg READ form')
"

# WRITE_EXISTING_PARENT raises FileNotFoundError on missing parent
docker exec the-one python -c "
from pathlib import Path
from the_one.tools.filesystem import _filesystem_check, FilesystemConfig, CheckMode
cfg = FilesystemConfig()
try:
    _filesystem_check(str(Path.home() / 'nonexistent_dir' / 'file.txt'), cfg, CheckMode.WRITE_EXISTING_PARENT)
    raise SystemExit('FAIL: expected FileNotFoundError')
except FileNotFoundError as e:
    print(f'OK WRITE_EXISTING_PARENT raises FNF: {e}')
"

# DIRECTORY mode wording
docker exec the-one python -c "
from pathlib import Path
import tempfile
from the_one.tools.filesystem import _filesystem_check, ConstraintError, CheckMode
from the_one.tools.filesystem import FilesystemConfig
with tempfile.TemporaryDirectory() as td:
    f = Path(td) / 'file.txt'
    f.write_text('x')
    cfg = FilesystemConfig(path_allowlist=[td])
    try:
        _filesystem_check(str(f), cfg, CheckMode.DIRECTORY)
        raise SystemExit('FAIL: file should not pass DIRECTORY mode')
    except ConstraintError as e:
        assert 'does not exist or is not a directory' in str(e), e
        print(f'OK DIRECTORY wording: {e}')
"

# Full suite
docker exec the-one pytest tests/test_filesystem_helpers.py tests/test_filesystem_tools.py tests/test_execution_helpers.py -x -q
docker exec the-one pytest -x -q --deselect tests/test_token_definitions.py::test_every_var_reference_is_defined

# Lint
docker exec the-one ruff check the_one/tools/filesystem.py the_one/tools/execution.py tests/test_filesystem_helpers.py
```

## Implementation Guidance

1. **Define `CheckMode`** at the top of `the_one/tools/filesystem.py` (after the constants, before `FilesystemConfig`):

   ```python
   from enum import Enum

   class CheckMode(str, Enum):
       """Dispatch mode for `_filesystem_check`. F5 L0 unification of
       F3's read/write-parent/write-path helpers + F4's _cwd_check.

       The four modes have genuinely divergent post-canonicalize shapes
       — see the dispatcher implementation."""
       READ = "read"                              # scope only on canonicalize(path)
       WRITE_NEW = "write_new"                    # scope on canonicalize(parent)/leaf
       WRITE_EXISTING_PARENT = "write_existing_parent"  # WRITE_NEW + parent.exists()
       DIRECTORY = "directory"                    # READ + is_dir()
   ```

2. **Rewrite `_filesystem_check` as the dispatcher**:

   ```python
   def _filesystem_check(
       path: str | Path,
       cfg: FilesystemConfig,
       mode: CheckMode = CheckMode.READ,
   ) -> Path:
       """Canonicalize `path` against `cfg.path_allowlist`/`path_denylist`
       and run the mode's post-check. Returns the canonical Path on success.

       Modes:
         - READ: scope check on canonicalize(path). No existence check.
         - WRITE_NEW: scope check on canonicalize(parent)/leaf. Parent
           may not exist. Use for write_file/mkdir (caller mkdir's
           intermediates).
         - WRITE_EXISTING_PARENT: WRITE_NEW + assert parent exists.
           Raises FileNotFoundError (NOT ConstraintError) on missing
           parent — environmental error distinct from policy refusal.
           Use for move_file destination, edit_file write-back.
         - DIRECTORY: scope check on canonicalize(path) + assert
           canonical.is_dir(). Use for cwd validation in execution tools.

       Raises:
           ConstraintError: scope refusal (allowlist-fail or denylist-hit).
               Always checked FIRST so a hostile prompt cannot learn whether
               out-of-scope paths exist.
           FileNotFoundError: WRITE_EXISTING_PARENT mode only, when parent
               is in-scope but does not exist.
       """
       p = Path(path).expanduser()

       # Canonicalize per mode shape. For WRITE_* modes we canonicalize the
       # PARENT first (handles non-existent leafs lexically), compose with
       # the leaf, then re-canonicalize the composed path. The second
       # canonicalize is required to resolve a leaf that IS an existing
       # symlink (otherwise a symlink to an out-of-scope target slips
       # past the scope check). This matches F3's existing behavior at
       # `_filesystem_check_write_parent`/`_filesystem_check_write_path`,
       # which delegated to `_filesystem_check(composed, cfg)` and got
       # the second resolve for free.
       if mode in (CheckMode.WRITE_NEW, CheckMode.WRITE_EXISTING_PARENT):
           canonical_parent = canonicalize(p.parent)
           canonical = canonicalize(canonical_parent / p.name)
       else:  # READ, DIRECTORY
           canonical_parent = None
           canonical = canonicalize(p)

       # Scope check (allowlist + denylist) — same across all modes,
       # checked FIRST to avoid leaking layout for out-of-scope paths.
       in_allowlist = any(
           canonical == r or _is_descendant(canonical, r)
           for r in cfg._canonical_allowlist
       )
       if not in_allowlist:
           raise ConstraintError(f"path '{canonical}' outside allowlist")
       for deny in cfg._canonical_denylist:
           if canonical == deny or _is_descendant(canonical, deny):
               raise ConstraintError(f"path '{canonical}' inside denylist '{deny}'")

       # Mode-specific post-check.
       if mode == CheckMode.WRITE_EXISTING_PARENT:
           # canonical_parent is always set in this branch (set above when
           # mode is WRITE_EXISTING_PARENT or WRITE_NEW). Guard explicitly
           # rather than via `assert` so behavior is identical under
           # `python -O` (which strips asserts).
           if canonical_parent is None:
               raise RuntimeError("unreachable: canonical_parent unset in WRITE_EXISTING_PARENT")
           if not canonical_parent.exists():
               raise FileNotFoundError(
                   f"parent does not exist for path '{path}': {canonical_parent}"
               )
       elif mode == CheckMode.DIRECTORY:
           if not canonical.is_dir():
               raise ConstraintError(
                   f"cwd '{canonical}' does not exist or is not a directory"
               )
       # READ and WRITE_NEW have no post-check.

       return canonical
   ```

3. **Reduce the write-helpers to shims**:

   ```python
   def _filesystem_check_write_parent(path: str | Path, cfg: FilesystemConfig) -> Path:
       """Shim — calls `_filesystem_check(path, cfg, CheckMode.WRITE_EXISTING_PARENT)`.
       Preserved so external imports (tests, future tools) keep resolving."""
       return _filesystem_check(path, cfg, CheckMode.WRITE_EXISTING_PARENT)


   def _filesystem_check_write_path(path: str | Path, cfg: FilesystemConfig) -> Path:
       """Shim — calls `_filesystem_check(path, cfg, CheckMode.WRITE_NEW)`."""
       return _filesystem_check(path, cfg, CheckMode.WRITE_NEW)
   ```

4. **Reduce `_cwd_check` in `execution.py` to a shim**:

   ```python
   def _cwd_check(cwd: str | Path, fs_cfg: FilesystemConfig) -> Path:
       """Shim — calls `_filesystem_check(cwd, fs_cfg, CheckMode.DIRECTORY)`.
       Preserved as a name for execution-tool readability; the dispatch
       lives in `the_one/tools/filesystem.py` post-F5 L0."""
       from the_one.tools.filesystem import CheckMode  # local import to avoid cycle
       return _filesystem_check(cwd, fs_cfg, CheckMode.DIRECTORY)
   ```

   - **Note**: `_filesystem_check` is already imported at module top of `execution.py:35`. The local `CheckMode` import is just to keep the existing top-of-file import block clean — easy to fold up later if a refactor wants it.

5. **Add the new test class `TestCheckModeDispatch`** in `tests/test_filesystem_helpers.py`:

   ```python
   class TestCheckModeDispatch:
       """L0 unification: all four modes share the same canonicalize +
       allowlist + denylist core; mode-specific post-checks fire correctly."""

       def test_read_mode_no_existence_check(self, tmp_path):
           cfg = FilesystemConfig(path_allowlist=[str(tmp_path)])
           target = tmp_path / "missing.txt"  # path does not exist
           # READ mode does NOT require existence; should return canonical
           result = _filesystem_check(str(target), cfg, CheckMode.READ)
           assert result == target.resolve()

       def test_write_new_mode_allows_missing_parent(self, tmp_path):
           cfg = FilesystemConfig(path_allowlist=[str(tmp_path)])
           target = tmp_path / "missing_dir" / "file.txt"
           # WRITE_NEW does not require parent to exist
           result = _filesystem_check(str(target), cfg, CheckMode.WRITE_NEW)
           assert result == (tmp_path / "missing_dir" / "file.txt").resolve()

       def test_write_existing_parent_raises_fnf_for_missing_parent(self, tmp_path):
           cfg = FilesystemConfig(path_allowlist=[str(tmp_path)])
           target = tmp_path / "missing_dir" / "file.txt"
           with pytest.raises(FileNotFoundError):
               _filesystem_check(str(target), cfg, CheckMode.WRITE_EXISTING_PARENT)

       def test_write_existing_parent_succeeds_when_parent_exists(self, tmp_path):
           cfg = FilesystemConfig(path_allowlist=[str(tmp_path)])
           target = tmp_path / "newfile.txt"  # parent IS tmp_path
           result = _filesystem_check(str(target), cfg, CheckMode.WRITE_EXISTING_PARENT)
           assert result == target

       def test_directory_mode_raises_for_file(self, tmp_path):
           f = tmp_path / "file.txt"
           f.write_text("x")
           cfg = FilesystemConfig(path_allowlist=[str(tmp_path)])
           with pytest.raises(ConstraintError, match="does not exist or is not a directory"):
               _filesystem_check(str(f), cfg, CheckMode.DIRECTORY)

       def test_directory_mode_succeeds_for_dir(self, tmp_path):
           cfg = FilesystemConfig(path_allowlist=[str(tmp_path)])
           result = _filesystem_check(str(tmp_path), cfg, CheckMode.DIRECTORY)
           assert result == tmp_path

       def test_scope_check_fires_first_for_all_modes(self, tmp_path):
           # Out-of-scope path → ConstraintError regardless of mode.
           cfg = FilesystemConfig(path_allowlist=[str(tmp_path)])
           outside = tmp_path.parent / "outside_dir"
           for mode in CheckMode:
               with pytest.raises(ConstraintError, match="outside allowlist"):
                   _filesystem_check(str(outside / "anything"), cfg, mode)

       def test_write_modes_resolve_leaf_symlink_to_out_of_scope(self, tmp_path):
           # Regression net: WRITE_NEW and WRITE_EXISTING_PARENT must
           # canonicalize the COMPOSED path (parent + leaf), so a leaf
           # that's a symlink to an out-of-scope target is rejected.
           # Before L0 this was the contract of `_filesystem_check_write_*`,
           # which delegated to `_filesystem_check(composed, cfg)` for
           # the second canonicalize. The dispatcher must preserve this.
           outside = tmp_path.parent / "outside_target"
           outside.mkdir()
           leaf = tmp_path / "linkout"
           leaf.symlink_to(outside / "x")  # leaf -> out-of-scope path
           cfg = FilesystemConfig(path_allowlist=[str(tmp_path)])
           for mode in (CheckMode.WRITE_NEW, CheckMode.WRITE_EXISTING_PARENT):
               with pytest.raises(ConstraintError, match="outside allowlist"):
                   _filesystem_check(str(leaf), cfg, mode)
   ```

6. **Run the full suite** to confirm no regressions in F1-F4 surfaces.

## Edge Cases

- **WRITE_EXISTING_PARENT and WRITE_NEW canonicalize the parent only**: this is the F3 contract — scope check first (so out-of-scope paths can't probe filesystem layout), parent-existence check second (only for WRITE_EXISTING_PARENT). Preserved verbatim by the dispatcher.
- **READ and DIRECTORY canonicalize the full path**: this works for both because `canonicalize` (== `Path.expanduser().resolve(strict=False)`) is lexical for non-existent paths. DIRECTORY mode then checks `is_dir()` on the resolved path — `False` for missing OR non-dir paths, both producing the same error wording.
- **`canonical_parent is None` in WRITE_EXISTING_PARENT branch**: the `assert` is for type-narrowing only; the dispatcher's earlier `if mode in (WRITE_NEW, WRITE_EXISTING_PARENT)` branch always sets it. Defensive.
- **`CheckMode(str, Enum)`**: the `str` mixin allows test asserts like `mode == "read"`. Enum values are strings, not auto-numbers.
- **Local `CheckMode` import in `_cwd_check`** (in execution.py): avoids a top-of-file import cycle if anything in execution.py is later imported by filesystem.py. F4's existing `_filesystem_check` import already has the same cycle-avoidance shape.
- **Existing `_filesystem_check_write_parent`/`_filesystem_check_write_path` test imports**: the shims preserve them. No test file change required for L0 (the new test class is additive).

## Files Affected

- `the_one/tools/filesystem.py` — add `CheckMode` enum; rewrite `_filesystem_check` as dispatcher; reduce `_filesystem_check_write_parent` and `_filesystem_check_write_path` to one-line shims.
- `the_one/tools/execution.py` — reduce `_cwd_check` to a one-line shim.
- `tests/test_filesystem_helpers.py` — add `TestCheckModeDispatch` class (additive; existing tests untouched).

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] F3 + F4 test suites passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed` (in this file's header)
- [ ] (Flight Director will check off in flight.md — do NOT modify flight.md)
- [ ] (NOT final leg — do NOT update flight.md status, do NOT commit)
