"""Tests for ``the_one/knowledge/walk.py`` (Flight 3 Leg 1, AC-6 through
AC-9): the filter rules, the walk's error surface and skip counters, the
pure reconcile planner, ``content_hash`` and ``is_filesystem_root``.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from the_one.db.models import KBItem
from the_one.knowledge.walk import (
    SKIPPED_DIRS,
    DiscoveredFile,
    ReconcilePlan,
    WalkResult,
    content_hash,
    is_filesystem_root,
    plan_reconcile,
    walk_folder,
)


def _symlink(target: Path, link: Path) -> None:
    """``os.symlink`` with a portable skip — not needed on this Linux host,
    but keeps the file honest about the platform dependency (Implementation
    Guidance point 6)."""
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError) as e:
        pytest.skip(f"os.symlink not supported on this platform: {e}")


def _build_fixture_tree(root: Path) -> None:
    root.mkdir()
    (root / "a.txt").write_text("a")
    (root / "b.md").write_text("b")
    (root / ".hidden.txt").write_text("hidden")
    hidden_dir = root / ".hiddendir"
    hidden_dir.mkdir()
    (hidden_dir / "inner.txt").write_text("inner")
    node_modules = root / "node_modules"
    node_modules.mkdir()
    (node_modules / "pkg.txt").write_text("pkg")
    sub = root / "sub"
    sub.mkdir()
    (sub / "c.py").write_text("c")
    (sub / "unsupported.bin").write_text("bin")
    _symlink(root / "a.txt", root / "symlinked_file.txt")
    _symlink(sub, root / "symlinked_dir")


class TestSkippedDirsConstant:
    def test_exact_value(self) -> None:
        assert SKIPPED_DIRS == frozenset({"node_modules", "__pycache__", "venv", "site-packages"})


# ── AC-6: filter rules ─────────────────────────────────────────────────


class TestWalkFolderFilterRules:
    def test_filters_and_yields_expected_files(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        _build_fixture_tree(root)
        extensions = frozenset({".txt", ".md", ".py"})

        result = walk_folder(root, extensions=extensions)

        names = {os.path.relpath(f.path, root) for f in result.files}
        assert names == {"a.txt", "b.md", os.path.join("sub", "c.py")}
        # node_modules + symlinked_dir.
        assert result.skipped_dirs == 2
        # symlinked_file.txt only — dot-entries and the unsupported suffix
        # are by-design filters, never counted.
        assert result.skipped_entries == 1

        for f in result.files:
            assert os.path.isabs(f.path)
            assert os.path.commonpath([f.path, str(root)]) == str(root)
            assert isinstance(f.size_bytes, int)
            assert isinstance(f.mtime, float)

    def test_case_insensitive_suffix_match(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        root.mkdir()
        (root / "A.TXT").write_text("upper")
        result = walk_folder(root, extensions=frozenset({".txt"}))
        assert len(result.files) == 1

    def test_dot_entries_not_counted(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        root.mkdir()
        (root / ".env").write_text("secret")
        hidden_dir = root / ".git"
        hidden_dir.mkdir()
        (hidden_dir / "config.txt").write_text("x")
        result = walk_folder(root, extensions=frozenset({".txt", ".env"}))
        assert result.files == []
        assert result.skipped_dirs == 0
        assert result.skipped_entries == 0

    def test_unsupported_suffix_not_counted(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        root.mkdir()
        (root / "image.png").write_text("binary-ish")
        result = walk_folder(root, extensions=frozenset({".txt"}))
        assert result.files == []
        assert result.skipped_dirs == 0
        assert result.skipped_entries == 0

    def test_iterative_walk_handles_deep_nesting_without_recursion_error(
        self, tmp_path: Path
    ) -> None:
        root = tmp_path / "root"
        root.mkdir()
        current = root
        for i in range(200):
            current = current / f"d{i}"
            current.mkdir()
        (current / "leaf.txt").write_text("leaf")

        result = walk_folder(root, extensions=frozenset({".txt"}))

        assert len(result.files) == 1
        assert result.files[0].path.endswith("leaf.txt")

    def test_opens_no_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = tmp_path / "root"
        root.mkdir()
        (root / "a.txt").write_text("hello")

        def _raise(*args, **kwargs):
            raise AssertionError("walk_folder must not open files")

        monkeypatch.setattr("builtins.open", _raise)
        monkeypatch.setattr("io.open", _raise)

        result = walk_folder(root, extensions=frozenset({".txt"}))
        assert len(result.files) == 1

    def test_non_utf8_filename_in_directory_skipped_and_counted(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        root.mkdir()
        bad_name = b"\xff\xfebad.txt"
        bad_path = os.path.join(os.fsencode(str(root)), bad_name)
        with open(bad_path, "wb") as f:
            f.write(b"data")

        result = walk_folder(root, extensions=frozenset({".txt"}))

        assert result.files == []
        assert result.skipped_entries == 1
        assert result.skipped_dirs == 0

    def test_non_utf8_directory_name_skipped_counted_and_never_descended(
        self, tmp_path: Path
    ) -> None:
        root = tmp_path / "root"
        root.mkdir()
        bad_dir_name = b"\xff\xfebaddir"
        bad_dir_path = os.path.join(os.fsencode(str(root)), bad_dir_name)
        os.mkdir(bad_dir_path)
        inner_file = os.path.join(bad_dir_path, b"inner.txt")
        with open(inner_file, "wb") as f:
            f.write(b"data")

        result = walk_folder(root, extensions=frozenset({".txt"}))

        assert result.files == []
        assert result.skipped_dirs == 1
        assert result.skipped_entries == 0


# ── AC-7: error surface and counters ──────────────────────────────────


class TestWalkFolderErrorSurface:
    def test_missing_root_raises(self, tmp_path: Path) -> None:
        missing = tmp_path / "nope"
        with pytest.raises((NotADirectoryError, FileNotFoundError)):
            walk_folder(missing, extensions=frozenset({".txt"}))

    def test_root_is_a_file_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("x")
        with pytest.raises((NotADirectoryError, FileNotFoundError)):
            walk_folder(f, extensions=frozenset({".txt"}))

    @pytest.mark.skipif(
        hasattr(os, "geteuid") and os.geteuid() == 0,
        reason="root bypasses directory permission bits",
    )
    def test_unreadable_subdirectory_skipped_and_counted_not_raised(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        root.mkdir()
        locked = root / "locked"
        locked.mkdir()
        (locked / "x.txt").write_text("x")
        locked.chmod(0o000)
        try:
            result = walk_folder(root, extensions=frozenset({".txt"}))
        finally:
            locked.chmod(0o755)

        assert result.files == []
        assert result.skipped_dirs == 1

    def test_file_vanishing_between_scandir_and_stat_is_skipped_and_counted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = tmp_path / "root"
        root.mkdir()

        class _VanishedEntry:
            name = "vanished.txt"
            path = str(root / "vanished.txt")

            def is_symlink(self) -> bool:
                return False

            def is_dir(self, follow_symlinks: bool = True) -> bool:
                return False

            def is_file(self, follow_symlinks: bool = True) -> bool:
                return True

            def stat(self, follow_symlinks: bool = True):
                raise OSError("vanished between scandir and stat")

        monkeypatch.setattr(os, "scandir", lambda path: iter([_VanishedEntry()]))

        result = walk_folder(root, extensions=frozenset({".txt"}))

        assert result.files == []
        assert result.skipped_entries == 1

    def test_walk_result_shape(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        root.mkdir()
        result = walk_folder(root, extensions=frozenset({".txt"}))
        assert isinstance(result, WalkResult)
        assert result.files == []
        assert result.skipped_dirs == 0
        assert result.skipped_entries == 0


# ── AC-8: pure reconcile planner ──────────────────────────────────────


def _item(path: str, *, content_hash: str | None = None, size_bytes=None, mtime=None) -> KBItem:
    return KBItem(
        id=f"item-{path}",
        kb_id="kb1",
        type="file",
        path_or_url=path,
        content_hash=content_hash,
        size_bytes=size_bytes,
        mtime=mtime,
    )


class TestPlanReconcile:
    def test_new_file_with_no_existing_item(self) -> None:
        disc = DiscoveredFile(path="/a", size_bytes=10, mtime=1.0)
        plan = plan_reconcile([disc], [])
        assert isinstance(plan, ReconcilePlan)
        assert plan.new == [disc]
        assert plan.removed == []
        assert plan.changed == []
        assert plan.unchanged == 0

    def test_removed_item_not_discovered(self) -> None:
        item = _item("/a", content_hash="h", size_bytes=10, mtime=1.0)
        plan = plan_reconcile([], [item])
        assert plan.removed == [item]
        assert plan.new == []
        assert plan.changed == []
        assert plan.unchanged == 0

    def test_changed_when_identity_present_and_size_differs(self) -> None:
        item = _item("/a", content_hash="h", size_bytes=10, mtime=1.0)
        disc = DiscoveredFile(path="/a", size_bytes=20, mtime=1.0)
        plan = plan_reconcile([disc], [item])
        assert plan.changed == [(item, disc)]
        assert plan.new == []
        assert plan.removed == []
        assert plan.unchanged == 0

    def test_changed_when_identity_present_and_mtime_differs(self) -> None:
        item = _item("/b", content_hash="h", size_bytes=10, mtime=1.0)
        disc = DiscoveredFile(path="/b", size_bytes=10, mtime=2.0)
        plan = plan_reconcile([disc], [item])
        assert plan.changed == [(item, disc)]

    def test_unchanged_when_identity_present_and_stat_matches(self) -> None:
        item = _item("/a", content_hash="h", size_bytes=10, mtime=1.0)
        disc = DiscoveredFile(path="/a", size_bytes=10, mtime=1.0)
        plan = plan_reconcile([disc], [item])
        assert plan.unchanged == 1
        assert plan.new == []
        assert plan.removed == []
        assert plan.changed == []

    def test_no_identity_yet_counts_as_unchanged_even_if_stat_differs(self) -> None:
        item = _item("/a", content_hash=None, size_bytes=None, mtime=None)
        disc = DiscoveredFile(path="/a", size_bytes=99, mtime=99.0)
        plan = plan_reconcile([disc], [item])
        assert plan.unchanged == 1
        assert plan.changed == []
        assert plan.new == []
        assert plan.removed == []

    def test_pure_no_filesystem_or_database_access(self) -> None:
        # No tmp_path/conn fixture used anywhere in this test — plan_reconcile
        # operates purely on the in-memory sequences passed to it.
        item = _item("/a", content_hash="h", size_bytes=10, mtime=1.0)
        disc = DiscoveredFile(path="/a", size_bytes=10, mtime=1.0)
        assert plan_reconcile([disc], [item]).unchanged == 1
        assert plan_reconcile([], []) == ReconcilePlan(new=[], removed=[], changed=[], unchanged=0)


# ── AC-9: content_hash / is_filesystem_root ───────────────────────────


class TestContentHashAndIsFilesystemRoot:
    def test_content_hash_matches_read_bytes_hash_for_a_multi_mib_file(
        self, tmp_path: Path
    ) -> None:
        p = tmp_path / "big.bin"
        data = os.urandom(3 * 1024 * 1024)
        p.write_bytes(data)
        expected = hashlib.sha256(data).hexdigest()
        assert content_hash(p) == expected

    def test_is_filesystem_root_true_for_slash(self) -> None:
        assert is_filesystem_root(Path("/")) is True

    def test_is_filesystem_root_false_for_a_non_root_path(self, tmp_path: Path) -> None:
        assert is_filesystem_root(tmp_path) is False
