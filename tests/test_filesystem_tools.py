"""Direct unit tests for filesystem tools after L4 migration to platform.canonicalize.

These tests cover the regression invariant for L4: routing through
`the_one.platform.canonicalize` preserves the previous behavior of
`Path(path).expanduser().resolve()` byte-for-byte at the three call sites
in `the_one/tools/filesystem.py`.

Tilde-expansion tests use `monkeypatch.setenv("HOME", str(tmp_path))` rather
than `monkeypatch.setattr(Path, "home", ...)`. This is deliberate:
`Path("~").expanduser()` ultimately calls `posixpath.expanduser`, which reads
`os.environ["HOME"]` directly and never calls `Path.home()`. Patching
`Path.home` is a silent no-op for `expanduser` and would leak the developer's
real home into test paths (false-pass mode).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from the_one.tools.filesystem import ListDirTool, ReadFileTool, WriteFileTool
from the_one.tools.resolver import _EmptyConfig


class TestReadFileTool:
    async def test_happy_path(self, tmp_path: Path) -> None:
        f = tmp_path / "x.txt"
        f.write_text("alpha\nbeta\ngamma")
        result = await ReadFileTool().execute(path=str(f))
        assert "alpha" in result and "beta" in result and "gamma" in result
        # 5-char right-aligned width line-number prefix
        assert "    1 | alpha" in result

    async def test_offset_limit(self, tmp_path: Path) -> None:
        f = tmp_path / "x.txt"
        f.write_text("a\nb\nc\nd\ne")
        result = await ReadFileTool().execute(
            path=str(f), offset=1, limit=2
        )
        assert "    2 | b" in result and "    3 | c" in result
        # Line 1 must NOT be in the result; assert on the line-prefixed form
        # (substring "1 | a") rather than fragile split-based checks.
        assert "1 | a" not in result

    async def test_tilde_expansion(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Path.expanduser reads os.environ["HOME"] via posixpath.expanduser;
        # patching Path.home does NOT affect Path("~").expanduser().
        monkeypatch.setenv("HOME", str(tmp_path))
        (tmp_path / "y.txt").write_text("home content")
        result = await ReadFileTool().execute(path="~/y.txt")
        assert "home content" in result

    async def test_missing_file_returns_error_string(self) -> None:
        result = await ReadFileTool().execute(path="/nonexistent/file.txt")
        assert result.startswith("[error]")


class TestWriteFileTool:
    async def test_happy_path(self, tmp_path: Path) -> None:
        f = tmp_path / "out.txt"
        result = await WriteFileTool().execute(path=str(f), content="hi")
        # Locks the byte-count contract.
        assert "Wrote 2 bytes" in result
        # Canonicalized absolute path appears in the response.
        assert str(f) in result
        assert f.read_text() == "hi"

    async def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        f = tmp_path / "deep" / "nested" / "file.txt"
        result = await WriteFileTool().execute(path=str(f), content="x")
        assert result.startswith("Wrote")
        assert f.read_text() == "x"

    async def test_tilde_expansion(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Path.expanduser reads os.environ["HOME"]; setenv is the correct
        # patch target — Path.home is never consulted by expanduser.
        monkeypatch.setenv("HOME", str(tmp_path))
        result = await WriteFileTool().execute(path="~/z.txt", content="home")
        assert result.startswith("Wrote")
        assert (tmp_path / "z.txt").read_text() == "home"


class TestListDirTool:
    async def test_happy_path(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        (tmp_path / "c").mkdir()
        result = await ListDirTool().execute(path=str(tmp_path))
        lines = result.split("\n")
        # Sorted: a.txt, b.txt, c
        assert any("f a.txt" in line for line in lines)
        assert any("f b.txt" in line for line in lines)
        assert any("d c" in line for line in lines)

    async def test_recursive(self, tmp_path: Path) -> None:
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "nested.txt").write_text("n")
        result = await ListDirTool().execute(
            path=str(tmp_path), recursive=True
        )
        assert "nested.txt" in result

    async def test_500_entry_cap(self, tmp_path: Path) -> None:
        # Use a fresh subdir so iterdir() count is exactly 550 — robust
        # against any future tmp_path prepopulation.
        target = tmp_path / "many"
        target.mkdir()
        for i in range(550):
            (target / f"f{i:03d}.txt").write_text("x")
        result = await ListDirTool().execute(path=str(target))
        assert "and 50 more" in result

    async def test_tilde_expansion(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Path.expanduser reads os.environ["HOME"]; setenv is the correct
        # patch target — Path.home is never consulted by expanduser.
        monkeypatch.setenv("HOME", str(tmp_path))
        (tmp_path / "h.txt").write_text("home")
        result = await ListDirTool().execute(path="~")
        assert "h.txt" in result


class TestFilesystemToolInstantiation:
    def test_each_tool_has_empty_config(self) -> None:
        for cls in (ReadFileTool, WriteFileTool, ListDirTool):
            t1 = cls()
            t2 = cls(_EmptyConfig())
            assert isinstance(t1._config, _EmptyConfig)
            assert isinstance(t2._config, _EmptyConfig)
