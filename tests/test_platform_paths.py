"""Direct tests for ``the_one.platform.paths``."""

from __future__ import annotations

from pathlib import Path

from the_one.platform.paths import canonicalize, is_within, safe_resolve


class TestCanonicalize:
    def test_expands_tilde(self) -> None:
        result = canonicalize("~")
        assert result == Path.home()
        assert result.is_absolute()

    def test_expands_tilde_with_subpath(self) -> None:
        result = canonicalize("~/foo/bar")
        assert result == Path.home() / "foo" / "bar"
        assert result.is_absolute()

    def test_resolves_relative_path(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = canonicalize("subdir/file.txt")
        assert result.is_absolute()
        # tmp_path may itself be a symlink target on some systems; compare
        # against its resolved form.
        assert result == tmp_path.resolve() / "subdir" / "file.txt"

    def test_accepts_path_input(self) -> None:
        # Both string and Path inputs should produce identical output.
        as_str = canonicalize("~/foo")
        as_path = canonicalize(Path("~/foo"))
        assert as_str == as_path

    def test_nonexistent_path_succeeds(self, tmp_path: Path) -> None:
        # Path.resolve(strict=False) is the default; non-existent paths
        # canonicalize without error.
        result = canonicalize(tmp_path / "does" / "not" / "exist")
        assert result.is_absolute()


class TestSafeResolve:
    def test_returns_absolute_path(self) -> None:
        result = safe_resolve("~/foo")
        assert result.is_absolute()

    def test_accepts_path_input(self) -> None:
        result = safe_resolve(Path("~"))
        assert result == Path.home()


class TestIsWithin:
    def test_path_equal_to_root(self, tmp_path: Path) -> None:
        assert is_within(tmp_path, tmp_path) is True

    def test_descendant(self, tmp_path: Path) -> None:
        child = tmp_path / "child" / "leaf.txt"
        assert is_within(child, tmp_path) is True

    def test_sibling_returns_false(self, tmp_path: Path) -> None:
        sibling = tmp_path.parent / "sibling-dir-xyz"
        assert is_within(sibling, tmp_path) is False

    def test_unrelated_returns_false(self) -> None:
        assert is_within("/etc/passwd", "/home/user") is False

    def test_accepts_string_inputs(self) -> None:
        # Verifies internal canonicalization: ~ should expand for both args.
        assert is_within("~/foo", "~") is True

    def test_path_input(self, tmp_path: Path) -> None:
        # Verifies Path inputs work identically to strings.
        child = tmp_path / "a"
        assert is_within(child, tmp_path) is True
        assert is_within(child, str(tmp_path)) is True
        assert is_within(str(child), tmp_path) is True
