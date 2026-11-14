# Leg: 02b-filesystem-check-helpers

**Status**: landed
**Flight**: [Filesystem Expansion & Constraints](../flight.md)

## Objective

Implement the module-level helpers `_filesystem_check`, `_filesystem_check_write_parent`, `_is_descendant`, `_check_read_size`, `_is_binary` in `the_one/tools/filesystem.py`. These are the runtime entry points that consume `FilesystemConfig` (L2a) and translate a path + config into either a canonical Path or a `ConstraintError`. No tool code is migrated in L2b — the helpers are tested in isolation; L3-L6 wire them into actual tool execute methods.

## Context

L2b is the final scaffolding leg of Flight 03 before tool migration starts in L3. After L2a, `FilesystemConfig` exists with cached `_canonical_allowlist` / `_canonical_denylist` `PrivateAttr` lists, but no code consumes them. L2b adds:

- `_filesystem_check(path, cfg)` — for READ paths and existing files. Canonicalizes, verifies allowlist + denylist, returns canonical Path. Symlinks are resolved by `canonicalize` (= `Path.resolve`), so a symlink pointing outside scope correctly fails the allowlist.
- `_filesystem_check_write_parent(path, cfg)` — for WRITE paths whose target may not exist yet. Checks that the parent directory exists and is in scope, then composes the leaf with the canonical parent. Tolerates non-existent leaves.
- `_is_descendant(path, root)` — pure helper used by both checks. Pre-canonicalized inputs.
- `_check_read_size(path, cfg)` — file-size cap enforcement. Raises `ConstraintError` on exceed.
- `_is_binary(path)` — null-byte sniff in first 8KB. Returns bool.

L3 then wires these into `ReadFileTool` / `WriteFileTool` / `ListDirTool`, and L4-L6 follow for the new tools.

**Relevant flight design decisions**:
- **Decision 10** — TOCTOU residual after canonicalize (accepted; documented). Read paths use `Path.resolve(strict=False)` (existing canonicalize); failure on non-existent surfaces as the I/O error from the tool, not the check. Write paths use the parent-canonicalize-then-compose pattern so symlinks in the path's *parent* are resolved while the leaf can still not-exist.
- **Decision 1.5** — `ConstraintError` (defined in L2a) is the exception type for ALL policy refusals. Helpers raise `ConstraintError`; tool wrappers in L3-L6 catch and format `[error] [constraint] {msg}`.
- **Decision 5** — `read_size_cap_bytes` enforced via `_check_read_size`. Read-side only.
- **Decision 2** — Binary detection via null-byte sniff in first 8KB of the file. Tools that consume `_is_binary` (read_file, edit_file, grep) refuse if `is_binary AND not cfg.allow_binary_files`.

**Helper boundaries** (what L2b does NOT do):
- L2b does NOT raise binary-refusal errors. `_is_binary` returns a bool. Each tool decides what to do (read_file refuses if `not cfg.allow_binary_files`; grep skips silently with a count). The "should we refuse this binary file?" policy lives in the tool, not the helper.
- L2b does NOT raise non-existence errors for read paths — the caller's I/O does. `_filesystem_check` does NOT call `path.exists()`.
- L2b does NOT raise non-existence errors for write paths' LEAF — only the PARENT must exist. A tool calling `_filesystem_check_write_parent` for a not-yet-created file gets back a canonical-parent + leaf-name composition.

## Inputs

Files that must exist (verified):
- `the_one/tools/filesystem.py` — has `FilesystemConfig`, `DEFAULT_PATH_DENYLIST`, `ConstraintError` (L2a, just landed)
- `the_one/platform/__init__.py` — re-exports `canonicalize` (F2)
- `the_one/platform/paths.py` — `canonicalize`, `is_within` (F2)

State that must be true:
- L2a landed (`FilesystemConfig` test suite green at 18 tests).
- Working tree includes uncommitted L1+L2a changes.
- Branch `flight/03-filesystem-expansion-and-constraints` checked out.

## Outputs

Files modified:
- `the_one/tools/filesystem.py` — adds 5 module-level helpers BETWEEN `FilesystemConfig` (end of class) and the existing `ReadFileTool` class. No imports beyond what L2a already added (`Path` is already imported; helpers re-use `canonicalize`, `ConstraintError`, `FilesystemConfig`).

Files created:
- `tests/test_filesystem_helpers.py` — new file, ~250 LoC. Covers the full helper matrix per the flight's Decision 10:
  - `_filesystem_check`: happy, path outside allowlist, path inside denylist (top-level entry hit), path inside denylist (descendant hit), symlink to in-scope target, symlink to out-of-scope target, symlink to non-existent target, allowlist-equal path (root itself), edge case (empty allowlist → all-reject).
  - `_filesystem_check_write_parent`: happy (parent exists, in scope, leaf doesn't exist), happy (parent exists, leaf already exists), parent missing (FileNotFoundError), parent out of scope (ConstraintError), parent contains `..` (canonicalized correctly), parent contains symlink-to-out-of-scope (rejected after canonicalize).
  - `_check_read_size`: under cap, equal to cap, over cap (raises with formatted message), zero-byte file.
  - `_is_binary`: text file (False), binary file with null in first 8KB (True), text file with null at offset >8KB (False — the heuristic accepts this), empty file (False).
  - `_is_descendant`: descendant True, equal-to-root False (strict), unrelated False, parent False.

State changes:
- No DB schema changes. No migrations. No tool behavior changes (helpers are not yet called from any tool).

## Acceptance Criteria

- [ ] `the_one/tools/filesystem.py` defines 5 module-level helpers: `_filesystem_check`, `_filesystem_check_write_parent`, `_is_descendant`, `_check_read_size`, `_is_binary`.
- [ ] `_filesystem_check(path, cfg) -> Path`: canonicalizes input via `canonicalize`; raises `ConstraintError("path '{canonical}' outside allowlist")` if no entry in `cfg._canonical_allowlist` is the canonical or its ancestor; raises `ConstraintError("path '{canonical}' inside denylist '{deny}'")` if any `cfg._canonical_denylist` entry is the canonical or its ancestor; otherwise returns the canonical `Path`. Allowlist check uses `canonical == r OR _is_descendant(canonical, r)`. Denylist check uses the same semantics applied per denylist entry.
- [ ] `_filesystem_check_write_parent(path, cfg) -> Path`: takes the input path, expands user, canonicalizes the *parent* via `canonicalize` (always succeeds — `Path.resolve(strict=False)` is lexical for non-existent targets), composes the canonical parent with the original leaf name (`canonical_parent / p.name`), runs the composed path through `_filesystem_check` FIRST (scope check), and ONLY then checks `canonical_parent.exists()`. If scope fails → `ConstraintError`. If scope passes but parent missing → `FileNotFoundError(f"parent does not exist for path '{path}': {canonical_parent}")`. **Order matters**: scope-first prevents a hostile prompt from learning whether out-of-scope paths exist (e.g., `/etc/secrets-vault/foo` returns "outside allowlist", not "parent does not exist"). Returns the composed canonical Path on success.
- [ ] `_is_descendant(path: Path, root: Path) -> bool`: returns True iff `path` is *strictly* under `root` (NOT equal). Both arguments must be pre-canonicalized; the helper does not canonicalize. Implemented via `path.relative_to(root)` in a try/except — `relative_to` raises `ValueError` on unrelated paths (returns False) and succeeds on equal paths (returns False after the `path != root` guard). Used internally by `_filesystem_check` and tested directly.
- [ ] `_check_read_size(path: Path, cfg: FilesystemConfig) -> int`: stats the file; if `size > cfg.read_size_cap_bytes`, raises `ConstraintError` with substring `"file size N bytes exceeds cap M bytes; use offset/limit to paginate"`; otherwise returns the size as an int. (Callers may discard the return value; useful for tools that want to log/echo the size.)
- [ ] `_is_binary(path: Path) -> bool`: opens the file, reads up to 8192 bytes, returns `b"\x00" in chunk`. Returns False for files smaller than 8KB whose entire content has no null. The 8KB sniff window is documented as a heuristic boundary — null bytes after offset 8192 are not detected (acceptable per Decision 2).
- [ ] All policy refusals raise `ConstraintError` (not `ValueError`, not generic `Exception`). Non-existent-parent in the write-helper raises `FileNotFoundError` (environmental).
- [ ] `tests/test_filesystem_helpers.py` covers the full matrix from Decision 10 and the helper boundaries above.
- [ ] `make test-unit` passes (target: post-L2a baseline 554 + ~28 new tests = ~576 passed, modulo the same pre-existing CSS-token red).
- [ ] `ruff check` and `ruff format --check` clean on changed files.
- [ ] No tool migrations: `ReadFileTool`, `WriteFileTool`, `ListDirTool` continue passing their existing `tests/test_filesystem_tools.py` suite unchanged.

## Verification Steps

Static (after edit, before test run):

```bash
cd ~/projects/the-one

# 5 helpers defined
rg -n "^def _filesystem_check\b|^def _filesystem_check_write_parent\b|^def _is_descendant\b|^def _check_read_size\b|^def _is_binary\b" the_one/tools/filesystem.py
# Expected: 5 matches

# ConstraintError used as the policy-refusal type
rg -n "raise ConstraintError" the_one/tools/filesystem.py
# Expected: 3+ matches (at least allowlist-fail, denylist-fail, size-exceeded)

# No tool classes touched
rg -n "class (Read|Write|ListDir)FileTool|class ListDirTool" the_one/tools/filesystem.py
# Expected: 3 (unchanged class headers)

# Helpers do NOT call ConstraintError for non-existent parent
rg -n "FileNotFoundError" the_one/tools/filesystem.py
# Expected: 1 match (in _filesystem_check_write_parent)
```

Dynamic:

```bash
docker exec the-one pytest tests/test_filesystem_helpers.py -v
# Expected: ~28 tests, all pass

# L2a still green
docker exec the-one pytest tests/test_filesystem_config.py -v
# Expected: 18 pass

# Existing filesystem tools still green
docker exec the-one pytest tests/test_filesystem_tools.py -v
# Expected: 12 pass (unchanged)

# Resolver still green
docker exec the-one pytest tests/test_resolver.py -v
# Expected: 39 pass

# Full unit suite
make test-unit
# Expected: ~582 passed (554 + ~28); only the pre-existing CSS-token red

# Smoke: helper round-trip via Python
docker exec the-one python -c "
import os, tempfile
from pathlib import Path
from the_one.tools.filesystem import (
    FilesystemConfig, ConstraintError,
    _filesystem_check, _filesystem_check_write_parent, _is_descendant,
    _check_read_size, _is_binary,
)
with tempfile.TemporaryDirectory() as d:
    os.environ['HOME'] = d
    cfg = FilesystemConfig(path_allowlist=[d], path_denylist=[])
    ok = Path(d) / 'a.txt'
    ok.write_text('hello')
    assert _filesystem_check(str(ok), cfg) == ok.resolve()
    try:
        _filesystem_check('/etc/passwd', cfg)
        assert False
    except ConstraintError as e:
        assert 'outside allowlist' in str(e)
    print('OK')
"
```

Quality:

```bash
docker exec the-one ruff check the_one/tools/filesystem.py tests/test_filesystem_helpers.py
docker exec the-one ruff format --check the_one/tools/filesystem.py tests/test_filesystem_helpers.py
```

## Implementation Guidance

### Step 1: Insert helpers AFTER `FilesystemConfig` and BEFORE `ReadFileTool`

In `the_one/tools/filesystem.py`, locate the end of the `FilesystemConfig` class definition. Insert the five helper functions after the class block, separated by two blank lines per PEP 8. The existing `ReadFileTool` / `WriteFileTool` / `ListDirTool` classes remain after these helpers, untouched.

```python
def _is_descendant(path: Path, root: Path) -> bool:
    """True if ``path`` is strictly under ``root`` (NOT equal). Both
    arguments must be pre-canonicalized; this helper does not canonicalize.

    Implementation: ``Path.relative_to`` raises ``ValueError`` for unrelated
    paths and succeeds (returns ``Path('.')``) for equal paths. The
    ``path != root`` guard treats the equal case as "not strictly under"."""
    try:
        path.relative_to(root)
        return path != root
    except ValueError:
        return False


def _filesystem_check(path: str | Path, cfg: FilesystemConfig) -> Path:
    """Canonicalize ``path`` and verify it is within ``cfg.path_allowlist``
    and not within ``cfg.path_denylist``. Returns the canonical Path on
    success.

    Raises:
        ConstraintError: if the canonical path is outside every allowlist
            root, OR equal-to-or-descendant of any denylist root.

    Symlinks: ``canonicalize`` calls ``Path.resolve``, which follows
    symlinks. A symlink pointing outside the allowlist is therefore
    detected as out-of-scope (the symlink target's canonical form is
    used in the comparison)."""
    canonical = canonicalize(path)
    in_allowlist = any(
        canonical == r or _is_descendant(canonical, r)
        for r in cfg._canonical_allowlist
    )
    if not in_allowlist:
        raise ConstraintError(f"path '{canonical}' outside allowlist")
    for deny in cfg._canonical_denylist:
        if canonical == deny or _is_descendant(canonical, deny):
            raise ConstraintError(
                f"path '{canonical}' inside denylist '{deny}'"
            )
    return canonical


def _filesystem_check_write_parent(
    path: str | Path, cfg: FilesystemConfig
) -> Path:
    """For write operations whose target may not exist: canonicalize the
    PARENT and verify it is in scope; then compose the leaf with the
    canonical parent.

    Raises:
        ConstraintError: if the canonical-parent + leaf composition is
            outside scope (allowlist-fail or denylist-hit). **Checked
            first** — a hostile prompt cannot learn whether out-of-scope
            paths exist.
        FileNotFoundError: if the parent is in scope but does not exist
            (environmental error — distinct from ConstraintError so tool
            wrappers can format the two differently). Message includes
            the original path the agent passed AND the canonical parent.

    The leaf is intentionally NOT required to exist — `write_file`,
    `mkdir`, `move_file` (destination), and `edit_file`'s write-back
    pass through this helper.

    Order rationale: `canonicalize` with `Path.resolve(strict=False)` is
    lexical for non-existent targets, so it always succeeds. Running the
    composed path through `_filesystem_check` BEFORE the existence check
    prevents leaking filesystem-layout information for paths the
    operator never permitted."""
    p = Path(path).expanduser()
    canonical_parent = canonicalize(p.parent)
    composed = canonical_parent / p.name
    # Scope check FIRST — for out-of-scope paths the agent learns only
    # "outside allowlist" / "inside denylist", never whether the path
    # exists.
    result = _filesystem_check(composed, cfg)
    # Existence check SECOND — only fires for in-scope-but-missing
    # parents, which the operator already permitted access to.
    if not canonical_parent.exists():
        raise FileNotFoundError(
            f"parent does not exist for path '{path}': {canonical_parent}"
        )
    return result


def _check_read_size(path: Path, cfg: FilesystemConfig) -> int:
    """Return the file size in bytes if it is at-or-under
    ``cfg.read_size_cap_bytes``; otherwise raise ``ConstraintError`` with
    a paginate hint."""
    size = path.stat().st_size
    if size > cfg.read_size_cap_bytes:
        raise ConstraintError(
            f"file size {size} bytes exceeds cap "
            f"{cfg.read_size_cap_bytes} bytes; use offset/limit to paginate"
        )
    return size


def _is_binary(path: Path) -> bool:
    """Heuristic binary-file detection: read up to 8192 bytes and check
    for any null byte. Files smaller than 8KB are scanned in full;
    larger files are sniffed only at the head (acceptable per Decision 2
    — null bytes after offset 8192 are not detected)."""
    with path.open("rb") as f:
        chunk = f.read(8192)
    return b"\x00" in chunk
```

### Step 2: Verify imports are sufficient

L2a's import block already includes `Path`, `Annotated`, `Any`, `BaseModel`, `Field`, `PrivateAttr`, `canonicalize`, `Tool`, `Narrow`, `NarrowPrefix`, `NarrowSuperset`. The new helpers reference `Path`, `canonicalize`, `ConstraintError`, `FilesystemConfig` — all already in scope. No new imports needed.

### Step 3: Create tests/test_filesystem_helpers.py

```python
"""Tests for filesystem helpers (F3 L2b) — `_filesystem_check`,
`_filesystem_check_write_parent`, `_is_descendant`, `_check_read_size`,
`_is_binary`. Helpers are tested in isolation; L3 wires them into tools."""

from __future__ import annotations

from pathlib import Path

import pytest

from the_one.tools.filesystem import (
    ConstraintError,
    FilesystemConfig,
    _check_read_size,
    _filesystem_check,
    _filesystem_check_write_parent,
    _is_binary,
    _is_descendant,
)


# Convenience fixture: a FilesystemConfig pinned to a tmp_path scope.
@pytest.fixture
def scoped_cfg(tmp_path: Path) -> FilesystemConfig:
    return FilesystemConfig(
        path_allowlist=[str(tmp_path)],
        path_denylist=[],
    )


# ---------------------------------------------------------------------------
# _is_descendant
# ---------------------------------------------------------------------------


class TestIsDescendant:
    def test_descendant_returns_true(self, tmp_path: Path) -> None:
        child = tmp_path / "a" / "b"
        assert _is_descendant(child, tmp_path) is True

    def test_equal_returns_false(self, tmp_path: Path) -> None:
        assert _is_descendant(tmp_path, tmp_path) is False

    def test_unrelated_returns_false(self, tmp_path: Path) -> None:
        assert _is_descendant(Path("/etc"), tmp_path) is False

    def test_parent_returns_false(self, tmp_path: Path) -> None:
        # tmp_path is descendant of tmp_path.parent, not the reverse.
        assert _is_descendant(tmp_path.parent, tmp_path) is False


# ---------------------------------------------------------------------------
# _filesystem_check
# ---------------------------------------------------------------------------


class TestFilesystemCheck:
    def test_happy_path_within_allowlist(
        self, tmp_path: Path, scoped_cfg: FilesystemConfig
    ) -> None:
        target = tmp_path / "doc.txt"
        target.write_text("hi")
        assert _filesystem_check(str(target), scoped_cfg) == target.resolve()

    def test_path_outside_allowlist_raises(
        self, tmp_path: Path, scoped_cfg: FilesystemConfig
    ) -> None:
        with pytest.raises(ConstraintError) as exc:
            _filesystem_check("/etc/hostname", scoped_cfg)
        assert "outside allowlist" in str(exc.value)

    def test_path_inside_denylist_raises(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(
            path_allowlist=[str(tmp_path)],
            path_denylist=[str(tmp_path / "secrets")],
        )
        target = tmp_path / "secrets" / "key.pem"
        target.parent.mkdir()
        target.write_text("x")
        with pytest.raises(ConstraintError) as exc:
            _filesystem_check(str(target), cfg)
        assert "inside denylist" in str(exc.value)

    def test_denylist_root_itself_rejected(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(
            path_allowlist=[str(tmp_path)],
            path_denylist=[str(tmp_path / "blocked")],
        )
        blocked = tmp_path / "blocked"
        blocked.mkdir()
        with pytest.raises(ConstraintError):
            _filesystem_check(str(blocked), cfg)

    def test_allowlist_root_itself_passes(
        self, tmp_path: Path, scoped_cfg: FilesystemConfig
    ) -> None:
        # The allowlist root itself (equal-to) is in scope.
        assert _filesystem_check(str(tmp_path), scoped_cfg) == tmp_path.resolve()

    def test_symlink_to_in_scope_target_passes(
        self, tmp_path: Path, scoped_cfg: FilesystemConfig
    ) -> None:
        real = tmp_path / "real.txt"
        real.write_text("data")
        link = tmp_path / "link.txt"
        link.symlink_to(real)
        # Canonical of `link` resolves to `real` (still in scope).
        result = _filesystem_check(str(link), scoped_cfg)
        assert result == real.resolve()

    def test_symlink_to_out_of_scope_target_rejected(
        self, tmp_path: Path, scoped_cfg: FilesystemConfig
    ) -> None:
        link = tmp_path / "escape"
        link.symlink_to("/etc")
        with pytest.raises(ConstraintError) as exc:
            _filesystem_check(str(link), scoped_cfg)
        assert "outside allowlist" in str(exc.value)

    def test_symlink_to_nonexistent_target_resolves_lexically(
        self, tmp_path: Path, scoped_cfg: FilesystemConfig
    ) -> None:
        # Symlink pointing to a non-existent target inside scope: Path.resolve
        # with strict=False resolves to the target path even if it doesn't
        # exist; the allowlist check is applied to the resolved result.
        target_path = tmp_path / "ghost.txt"
        link = tmp_path / "ghost-link"
        link.symlink_to(target_path)
        # Resolves to tmp_path/ghost.txt, which is in-scope despite not existing
        result = _filesystem_check(str(link), scoped_cfg)
        assert result == target_path.resolve()

    def test_tilde_path_canonicalizes_via_expanduser(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`_filesystem_check` accepts paths containing `~` — `canonicalize`
        calls `expanduser()`. Setting HOME to tmp_path makes `~/foo` resolve
        into the allowlisted scope."""
        monkeypatch.setenv("HOME", str(tmp_path))
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        target = tmp_path / "tilde-doc.txt"
        target.write_text("ok")
        result = _filesystem_check("~/tilde-doc.txt", cfg)
        assert result == target.resolve()


# ---------------------------------------------------------------------------
# _filesystem_check_write_parent
# ---------------------------------------------------------------------------


class TestFilesystemCheckWriteParent:
    def test_happy_parent_exists_leaf_does_not(
        self, tmp_path: Path, scoped_cfg: FilesystemConfig
    ) -> None:
        target = tmp_path / "newfile.txt"
        # Leaf does not exist; parent (tmp_path) does.
        assert not target.exists()
        result = _filesystem_check_write_parent(str(target), scoped_cfg)
        assert result == (tmp_path.resolve() / "newfile.txt")

    def test_happy_parent_exists_leaf_already_exists(
        self, tmp_path: Path, scoped_cfg: FilesystemConfig
    ) -> None:
        target = tmp_path / "existing.txt"
        target.write_text("x")
        result = _filesystem_check_write_parent(str(target), scoped_cfg)
        assert result == target.resolve()

    def test_parent_missing_raises_file_not_found(
        self, tmp_path: Path, scoped_cfg: FilesystemConfig
    ) -> None:
        target = tmp_path / "missing-parent" / "file.txt"
        # Parent (`missing-parent`) doesn't exist.
        with pytest.raises(FileNotFoundError):
            _filesystem_check_write_parent(str(target), scoped_cfg)

    def test_parent_out_of_scope_raises_constraint(
        self, tmp_path: Path, scoped_cfg: FilesystemConfig
    ) -> None:
        # /etc exists but is outside the cfg's allowlist (which is tmp_path).
        with pytest.raises(ConstraintError):
            _filesystem_check_write_parent("/etc/newfile", scoped_cfg)

    def test_out_of_scope_missing_parent_prefers_constraint_over_filenotfound(
        self, tmp_path: Path, scoped_cfg: FilesystemConfig
    ) -> None:
        """Order rationale: scope check fires before existence check, so a
        path with an out-of-scope AND non-existent parent surfaces as
        ConstraintError, not FileNotFoundError. This prevents a hostile
        prompt from learning whether `/etc/missing-subdir/...` exists."""
        with pytest.raises(ConstraintError) as exc:
            _filesystem_check_write_parent(
                "/etc/missing-subdir/foo", scoped_cfg
            )
        assert "outside allowlist" in str(exc.value)

    def test_leaf_existing_symlink_to_out_of_scope_rejected(
        self, tmp_path: Path, scoped_cfg: FilesystemConfig
    ) -> None:
        """Leaf is itself an existing symlink that escapes scope. The
        parent is in scope; canonicalize on the composition resolves the
        leaf symlink → out-of-scope target → ConstraintError. Locks the
        behavior `write_file` and `move_file`'s destination will rely on."""
        leaf_link = tmp_path / "escape-leaf"
        leaf_link.symlink_to("/etc/passwd")
        with pytest.raises(ConstraintError):
            _filesystem_check_write_parent(str(leaf_link), scoped_cfg)

    def test_parent_with_dotdot_canonicalizes(
        self, tmp_path: Path, scoped_cfg: FilesystemConfig
    ) -> None:
        sub = tmp_path / "sub"
        sub.mkdir()
        # `sub/../newfile` canonicalizes to `tmp_path/newfile`, in scope.
        composed_path = sub / ".." / "newfile.txt"
        result = _filesystem_check_write_parent(str(composed_path), scoped_cfg)
        assert result == (tmp_path.resolve() / "newfile.txt")

    def test_parent_symlinked_to_out_of_scope_rejected(
        self, tmp_path: Path, scoped_cfg: FilesystemConfig
    ) -> None:
        # Parent is a symlink that resolves outside scope.
        escape = tmp_path / "escape-dir"
        escape.symlink_to("/etc")
        target = escape / "newfile"
        with pytest.raises(ConstraintError):
            _filesystem_check_write_parent(str(target), scoped_cfg)


# ---------------------------------------------------------------------------
# _check_read_size
# ---------------------------------------------------------------------------


class TestCheckReadSize:
    def test_under_cap_returns_size(self, tmp_path: Path) -> None:
        target = tmp_path / "small.txt"
        target.write_bytes(b"a" * 100)
        cfg = FilesystemConfig(read_size_cap_bytes=1024)
        assert _check_read_size(target, cfg) == 100

    def test_equal_to_cap_returns_size(self, tmp_path: Path) -> None:
        target = tmp_path / "exact.txt"
        target.write_bytes(b"a" * 1024)
        cfg = FilesystemConfig(read_size_cap_bytes=1024)
        assert _check_read_size(target, cfg) == 1024

    def test_over_cap_raises_constraint(self, tmp_path: Path) -> None:
        target = tmp_path / "big.txt"
        target.write_bytes(b"a" * 2048)
        cfg = FilesystemConfig(read_size_cap_bytes=1024)
        with pytest.raises(ConstraintError) as exc:
            _check_read_size(target, cfg)
        msg = str(exc.value)
        assert "2048" in msg and "1024" in msg
        assert "offset/limit to paginate" in msg

    def test_zero_byte_file_returns_zero(self, tmp_path: Path) -> None:
        target = tmp_path / "empty.txt"
        target.write_bytes(b"")
        cfg = FilesystemConfig(read_size_cap_bytes=1024)
        assert _check_read_size(target, cfg) == 0


# ---------------------------------------------------------------------------
# _is_binary
# ---------------------------------------------------------------------------


class TestIsBinary:
    def test_text_file_returns_false(self, tmp_path: Path) -> None:
        target = tmp_path / "text.txt"
        target.write_text("hello world\n" * 100)
        assert _is_binary(target) is False

    def test_binary_with_null_in_first_8kb_returns_true(
        self, tmp_path: Path
    ) -> None:
        target = tmp_path / "bin.dat"
        target.write_bytes(b"hello\x00world")
        assert _is_binary(target) is True

    def test_text_with_null_after_8kb_returns_false(self, tmp_path: Path) -> None:
        # Heuristic accepts this corner: nulls past offset 8192 are missed.
        target = tmp_path / "late-null.dat"
        target.write_bytes(b"a" * 9000 + b"\x00" + b"b" * 100)
        assert _is_binary(target) is False

    def test_empty_file_returns_false(self, tmp_path: Path) -> None:
        target = tmp_path / "empty.dat"
        target.write_bytes(b"")
        assert _is_binary(target) is False
```

### Step 4: Run tests; iterate until green

```bash
docker exec the-one ruff check the_one/tools/filesystem.py tests/test_filesystem_helpers.py
docker exec the-one ruff format the_one/tools/filesystem.py tests/test_filesystem_helpers.py
docker exec the-one pytest tests/test_filesystem_helpers.py -v
docker exec the-one pytest tests/test_filesystem_config.py -v
docker exec the-one pytest tests/test_filesystem_tools.py -v
make test-unit
```

### Step 5: Update flight log + leg status

- Append `### Leg 02b — _filesystem_check helpers` entry under "Leg Progress" in `flight-log.md`.
- Set leg `Status` to `landed`.
- Do NOT commit. Do NOT signal `[COMPLETE:leg]`. Signal `[HANDOFF:review-needed]`.

## Edge Cases

- **Symlink target follows for read paths**: `canonicalize` (= `Path.resolve(strict=False)`) resolves symlinks, so a symlink to an out-of-scope target is rejected as out-of-scope (not as a symlink-specific class). This is the desired behavior per Decision 10. Tests in `TestFilesystemCheck::test_symlink_to_*` lock this.
- **Symlink in the parent of a write path**: `_filesystem_check_write_parent` calls `canonicalize(p.parent)` which resolves any symlinks in the parent path. A parent that is itself a symlink to an out-of-scope dir is therefore rejected. `TestFilesystemCheckWriteParent::test_parent_symlinked_to_out_of_scope_rejected` covers this.
- **`tmp_path` and macOS `/private/var` symlink**: macOS makes `/var` a symlink to `/private/var`, so `tmp_path.resolve()` may differ from `tmp_path` directly. Tests use `target.resolve()` for assertions and `str(tmp_path)` for the allowlist input — `canonicalize` on both sides ensures consistent comparison. Linux/WSL (the F3 verification target) doesn't have this issue.
- **`Path.resolve(strict=False)` on non-existent leaf**: For a path like `tmp_path / "newfile"` where `tmp_path` exists and `newfile` does not, `resolve()` returns `tmp_path.resolve() / "newfile"` (lexical composition). `_filesystem_check_write_parent` does the parent resolve explicitly to avoid relying on this — but the helper's compose-parent-then-leaf shape produces an equivalent canonical for the in-scope case.
- **`PrivateAttr` access from helpers**: `_filesystem_check` reads `cfg._canonical_allowlist` and `cfg._canonical_denylist` — the underscore-prefixed names. Since the helper lives in the same module as `FilesystemConfig`, this is in-module access (not a violation of Pydantic's "private" intent). L2a's edge-case section pinned this as the intended consumer pattern.
- **`FileNotFoundError` vs `ConstraintError` distinction in write helper**: `_filesystem_check_write_parent` raises `FileNotFoundError` for missing parent (environmental — the operator's path config is fine; the agent just gave a path whose parent dir doesn't exist) and `ConstraintError` for out-of-scope parent (policy — the operator denied access). Tool wrappers in L3-L6 catch both: `ConstraintError → [error] [constraint] {msg}`, `FileNotFoundError` (and other exceptions) `→ [error] {e}`.
- **Empty allowlist**: An operator setting `path_allowlist = []` makes EVERY path fail the allowlist check (no entry can match). Acceptable degenerate config; not a bug. No test for this case (the bool semantic is too obvious).
- **Empty denylist**: With `path_denylist = []`, the denylist loop exits immediately without raising. Already covered implicitly by `scoped_cfg` fixture (denylist=[]).
- **Binary heuristic false negatives past 8KB**: A file with text in its first 8KB and binary content after will be misclassified as text. Decision 2 accepts this; tests pin the corner.
- **No `model_dump` exposure of `_canonical_*`**: PrivateAttrs are excluded from `model_dump()` and `model_json_schema()` automatically. This is desired — the canonical-paths cache is an implementation detail; serialization round-tripping a `FilesystemConfig` should round-trip the public `path_allowlist` strings.

## Files Affected

- `the_one/tools/filesystem.py` — additive only. 5 helpers, ~70 LoC of code + ~50 LoC of docstrings = ~120 added LoC. No existing-class modifications.
- `tests/test_filesystem_helpers.py` — new file, ~250 LoC.

Total: ~370 added LoC across 2 files.

**Out of scope for L2b**:

- Tool wiring (`Config = FilesystemConfig`, `_filesystem_check` calls inside `execute()`) → L3 (existing tools) and L4-L6 (new tools).
- Binary-file refusal at the tool layer → L3 (`ReadFileTool.execute`) and L4 (`EditFileTool.execute`) and L6 (`GrepTool` skip-with-count).
- Output / response-size caps for tool RESPONSES (different from read-size cap) → F4/F5.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`** (commit + leg-completion deferred to end-of-flight per agentic-workflow):

- [ ] All acceptance criteria verified
- [ ] Tests passing (`pytest tests/test_filesystem_helpers.py -v`; `pytest tests/test_filesystem_config.py -v`; `pytest tests/test_filesystem_tools.py -v`; `make test-unit` ≥ post-L2a baseline + ~28 new tests)
- [ ] `ruff check` and `ruff format --check` clean on changed files
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed`
- [ ] DO NOT check off this leg in `flight.md` (deferred to final commit)
- [ ] DO NOT commit; DO NOT signal `[COMPLETE:leg]`
- [ ] Signal `[HANDOFF:review-needed]`
