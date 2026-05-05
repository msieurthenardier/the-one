"""Tests for filesystem helpers (F3 L2b) — `_filesystem_check`,
`_filesystem_check_write_parent`, `_is_descendant`, `_check_read_size`,
`_is_binary`. Helpers are tested in isolation; L3 wires them into tools."""

from __future__ import annotations

from pathlib import Path

import pytest

from the_one.tools.filesystem import (
    CheckMode,
    ConstraintError,
    FilesystemConfig,
    _check_read_size,
    _filesystem_check,
    _filesystem_check_write_parent,
    _filesystem_check_write_path,
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
            _filesystem_check_write_parent("/etc/missing-subdir/foo", scoped_cfg)
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
# _filesystem_check_write_path
# ---------------------------------------------------------------------------


class TestFilesystemCheckWritePath:
    """Direct tests for ``_filesystem_check_write_path`` (added in L3
    alongside the existing-tool migration). Helper does scope-check on a
    lexically-composed canonical, with NO existence check on the parent —
    used by ``WriteFileTool`` (auto-creates parents) and L5's
    ``MkdirTool``."""

    def test_happy_parent_does_not_exist(
        self, tmp_path: Path, scoped_cfg: FilesystemConfig
    ) -> None:
        # Parent (`missing-parent`) does NOT exist. Helper must NOT raise.
        target = tmp_path / "missing-parent" / "child.txt"
        result = _filesystem_check_write_path(str(target), scoped_cfg)
        # Lexical composition; no existence check.
        assert result == (tmp_path.resolve() / "missing-parent" / "child.txt")

    def test_out_of_scope_raises_constraint(self, scoped_cfg: FilesystemConfig) -> None:
        with pytest.raises(ConstraintError):
            _filesystem_check_write_path("/etc/secrets/foo", scoped_cfg)

    def test_does_not_raise_filenotfound_on_missing_parent(
        self, tmp_path: Path, scoped_cfg: FilesystemConfig
    ) -> None:
        # Locks the contract: this helper does NOT do existence checks.
        # Use ``_filesystem_check_write_parent`` if existence is required.
        target = tmp_path / "deeply" / "nested" / "missing" / "file.txt"
        # Should NOT raise FileNotFoundError; should succeed with composed path.
        result = _filesystem_check_write_path(str(target), scoped_cfg)
        assert "deeply" in str(result)


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
        assert "exceeds cap" in msg

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

    def test_binary_with_null_in_first_8kb_returns_true(self, tmp_path: Path) -> None:
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


# ---------------------------------------------------------------------------
# CheckMode dispatch (F5 L0)
# ---------------------------------------------------------------------------


class TestCheckModeDispatch:
    """L0 unification: all four modes share the same canonicalize +
    allowlist + denylist core; mode-specific post-checks fire correctly."""

    def test_read_mode_no_existence_check(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)])
        target = tmp_path / "missing.txt"  # path does not exist
        # READ mode does NOT require existence; should return canonical.
        result = _filesystem_check(str(target), cfg, CheckMode.READ)
        assert result == target.resolve()

    def test_write_new_mode_allows_missing_parent(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)])
        target = tmp_path / "missing_dir" / "file.txt"
        # WRITE_NEW does not require parent to exist.
        result = _filesystem_check(str(target), cfg, CheckMode.WRITE_NEW)
        assert result == (tmp_path / "missing_dir" / "file.txt").resolve()

    def test_write_existing_parent_raises_fnf_for_missing_parent(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)])
        target = tmp_path / "missing_dir" / "file.txt"
        with pytest.raises(FileNotFoundError):
            _filesystem_check(str(target), cfg, CheckMode.WRITE_EXISTING_PARENT)

    def test_write_existing_parent_succeeds_when_parent_exists(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)])
        target = tmp_path / "newfile.txt"  # parent IS tmp_path
        result = _filesystem_check(str(target), cfg, CheckMode.WRITE_EXISTING_PARENT)
        assert result == target

    def test_directory_mode_raises_for_file(self, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("x")
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)])
        with pytest.raises(ConstraintError, match="does not exist or is not a directory"):
            _filesystem_check(str(f), cfg, CheckMode.DIRECTORY)

    def test_directory_mode_succeeds_for_dir(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)])
        result = _filesystem_check(str(tmp_path), cfg, CheckMode.DIRECTORY)
        assert result == tmp_path

    def test_scope_check_fires_first_for_all_modes(self, tmp_path: Path) -> None:
        # Out-of-scope path -> ConstraintError regardless of mode.
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)])
        outside = tmp_path.parent / "outside_dir"
        for mode in CheckMode:
            with pytest.raises(ConstraintError, match="outside allowlist"):
                _filesystem_check(str(outside / "anything"), cfg, mode)

    def test_write_modes_resolve_leaf_symlink_to_out_of_scope(self, tmp_path: Path) -> None:
        # Regression net: WRITE_NEW and WRITE_EXISTING_PARENT must
        # canonicalize the COMPOSED path (parent + leaf), so a leaf
        # that's a symlink to an out-of-scope target is rejected.
        # Before L0 this was the contract of `_filesystem_check_write_*`,
        # which delegated to `_filesystem_check(composed, cfg)` for the
        # second canonicalize. The dispatcher must preserve this.
        outside = tmp_path.parent / "outside_target"
        outside.mkdir()
        leaf = tmp_path / "linkout"
        leaf.symlink_to(outside / "x")  # leaf -> out-of-scope path
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)])
        for mode in (CheckMode.WRITE_NEW, CheckMode.WRITE_EXISTING_PARENT):
            with pytest.raises(ConstraintError, match="outside allowlist"):
                _filesystem_check(str(leaf), cfg, mode)
