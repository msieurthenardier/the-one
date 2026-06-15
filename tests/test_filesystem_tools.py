"""Direct unit tests for filesystem tools after L3 migration to
``FilesystemConfig`` + the L2b helper set.

L3 wires every existing filesystem tool through ``_filesystem_check`` (or
``_filesystem_check_write_path`` for ``WriteFileTool``) and standardizes
error formatting: ``ConstraintError`` → ``[error] [constraint] {msg}``;
other exceptions → ``[error] {e}``. Tests below construct each tool with
an explicit, scoped ``FilesystemConfig`` so ``tmp_path`` is in scope.
Tilde-expansion tests retain ``monkeypatch.setenv("HOME", str(tmp_path))``
AND now also pass an explicit ``FilesystemConfig`` so ``~`` resolves into
the allowlisted scope.

Tilde-expansion tests use ``monkeypatch.setenv("HOME", str(tmp_path))``
rather than ``monkeypatch.setattr(Path, "home", ...)``. This is
deliberate: ``Path("~").expanduser()`` ultimately calls
``posixpath.expanduser``, which reads ``os.environ["HOME"]`` directly and
never calls ``Path.home()``. Patching ``Path.home`` is a silent no-op for
``expanduser`` and would leak the developer's real home into test paths
(false-pass mode).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from the_one.tools.filesystem import (
    DeleteFileTool,
    EditFileTool,
    FilesystemConfig,
    GlobTool,
    GrepTool,
    ListDirTool,
    MkdirTool,
    MoveFileTool,
    ReadFileTool,
    WriteFileTool,
)


class TestReadFileTool:
    async def test_happy_path(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        f = tmp_path / "x.txt"
        f.write_text("alpha\nbeta\ngamma")
        result = await ReadFileTool(cfg).execute(path=str(f))
        assert "alpha" in result and "beta" in result and "gamma" in result
        # 5-char right-aligned width line-number prefix
        assert "    1 | alpha" in result

    async def test_offset_limit(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        f = tmp_path / "x.txt"
        f.write_text("a\nb\nc\nd\ne")
        result = await ReadFileTool(cfg).execute(path=str(f), offset=1, limit=2)
        assert "    2 | b" in result and "    3 | c" in result
        # Line 1 must NOT be in the result; assert on the line-prefixed form
        # (substring "1 | a") rather than fragile split-based checks.
        assert "1 | a" not in result

    async def test_tilde_expansion(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # Path.expanduser reads os.environ["HOME"] via posixpath.expanduser;
        # patching Path.home does NOT affect Path("~").expanduser().
        monkeypatch.setenv("HOME", str(tmp_path))
        # On Windows, expanduser resolves USERPROFILE (not HOME) — patch it so
        # the write target lands inside the allowlisted tmp_path, not the real
        # home (C:\Users\runneradmin → outside allowlist → constraint error).
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        monkeypatch.setenv("HOMEDRIVE", tmp_path.drive if tmp_path.drive else "")
        monkeypatch.setenv("HOMEPATH", str(tmp_path))
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        (tmp_path / "y.txt").write_text("home content")
        result = await ReadFileTool(cfg).execute(path="~/y.txt")
        assert "home content" in result

    async def test_out_of_scope_path_returns_constraint_error(self) -> None:
        # Default config: allowlist is `~`, no denylist override. Out-of-scope
        # path surfaces as a constraint error before the I/O is attempted.
        result = await ReadFileTool().execute(path="/nonexistent/file.txt")
        assert result.startswith("[error] [constraint]")
        assert "outside allowlist" in result

    async def test_path_outside_allowlist_raises_constraint(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        result = await ReadFileTool(cfg).execute(path="/etc/hostname")
        assert result.startswith("[error] [constraint]")
        assert "outside allowlist" in result

    async def test_path_inside_denylist_raises_constraint(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(
            path_allowlist=[str(tmp_path)],
            path_denylist=[str(tmp_path / "secrets")],
        )
        target = tmp_path / "secrets" / "key.pem"
        target.parent.mkdir()
        target.write_text("x")
        result = await ReadFileTool(cfg).execute(path=str(target))
        assert result.startswith("[error] [constraint]")
        assert "inside denylist" in result

    async def test_size_cap_exceeded_returns_constraint(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(
            path_allowlist=[str(tmp_path)],
            path_denylist=[],
            read_size_cap_bytes=1024,
        )
        big = tmp_path / "big.txt"
        big.write_bytes(b"x" * 2048)
        result = await ReadFileTool(cfg).execute(path=str(big))
        assert result.startswith("[error] [constraint]")
        assert "exceeds cap" in result

    async def test_binary_refusal_default(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        # Default allow_binary_files is False
        binfile = tmp_path / "binary.dat"
        binfile.write_bytes(b"hello\x00world")
        result = await ReadFileTool(cfg).execute(path=str(binfile))
        assert result.startswith("[error] [constraint]")
        assert "binary" in result

    async def test_binary_allowed_when_cfg_permits(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(
            path_allowlist=[str(tmp_path)],
            path_denylist=[],
            allow_binary_files=True,
        )
        binfile = tmp_path / "ok-binary.dat"
        binfile.write_bytes(b"hello\x00world")
        result = await ReadFileTool(cfg).execute(path=str(binfile))
        assert not result.startswith("[error]")  # tool succeeded
        assert "hello" in result  # null replaced via errors="replace"


class TestWriteFileTool:
    async def test_happy_path(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        f = tmp_path / "out.txt"
        result = await WriteFileTool(cfg).execute(path=str(f), content="hi")
        # Locks the byte-count contract.
        assert "Wrote 2 bytes" in result
        # Canonicalized absolute path appears in the response.
        assert str(f) in result
        assert f.read_text() == "hi"

    async def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        f = tmp_path / "deep" / "nested" / "file.txt"
        result = await WriteFileTool(cfg).execute(path=str(f), content="x")
        assert result.startswith("Wrote")
        assert f.read_text() == "x"

    async def test_tilde_expansion(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # Path.expanduser reads os.environ["HOME"]; setenv is the correct
        # patch target — Path.home is never consulted by expanduser.
        monkeypatch.setenv("HOME", str(tmp_path))
        # On Windows, expanduser resolves USERPROFILE (not HOME).
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        monkeypatch.setenv("HOMEDRIVE", tmp_path.drive if tmp_path.drive else "")
        monkeypatch.setenv("HOMEPATH", str(tmp_path))
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        result = await WriteFileTool(cfg).execute(path="~/z.txt", content="home")
        assert result.startswith("Wrote")
        assert (tmp_path / "z.txt").read_text() == "home"

    async def test_parent_out_of_scope_raises_constraint(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        result = await WriteFileTool(cfg).execute(path="/etc/newfile.txt", content="x")
        assert result.startswith("[error] [constraint]")
        assert "outside allowlist" in result


class TestListDirTool:
    async def test_happy_path(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        (tmp_path / "c").mkdir()
        result = await ListDirTool(cfg).execute(path=str(tmp_path))
        lines = result.split("\n")
        # Sorted: a.txt, b.txt, c
        assert any("f a.txt" in line for line in lines)
        assert any("f b.txt" in line for line in lines)
        assert any("d c" in line for line in lines)

    async def test_recursive(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "nested.txt").write_text("n")
        result = await ListDirTool(cfg).execute(path=str(tmp_path), recursive=True)
        assert "nested.txt" in result

    async def test_500_entry_cap(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        # Use a fresh subdir so iterdir() count is exactly 550 — robust
        # against any future tmp_path prepopulation.
        target = tmp_path / "many"
        target.mkdir()
        for i in range(550):
            (target / f"f{i:03d}.txt").write_text("x")
        result = await ListDirTool(cfg).execute(path=str(target))
        assert "and 50 more" in result

    async def test_tilde_expansion(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # Path.expanduser reads os.environ["HOME"]; setenv is the correct
        # patch target — Path.home is never consulted by expanduser.
        monkeypatch.setenv("HOME", str(tmp_path))
        # On Windows, expanduser resolves USERPROFILE (not HOME).
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        monkeypatch.setenv("HOMEDRIVE", tmp_path.drive if tmp_path.drive else "")
        monkeypatch.setenv("HOMEPATH", str(tmp_path))
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        (tmp_path / "h.txt").write_text("home")
        result = await ListDirTool(cfg).execute(path="~")
        assert "h.txt" in result

    async def test_path_outside_allowlist_raises_constraint(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        result = await ListDirTool(cfg).execute(path="/etc")
        assert result.startswith("[error] [constraint]")
        assert "outside allowlist" in result


class TestEditFileTool:
    async def test_happy_single_match(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        target = tmp_path / "x.txt"
        target.write_text("alpha\nbeta\ngamma\n")
        result = await EditFileTool(cfg).execute(
            path=str(target),
            old_string="beta",
            new_string="BETA",
        )
        assert "Edited" in result
        assert "@@ around line 2 @@" in result
        assert "- " in result and "+ " in result
        assert target.read_text() == "alpha\nBETA\ngamma\n"

    async def test_multi_match_returns_constraint_error(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        target = tmp_path / "x.txt"
        target.write_text("a\na\na\n")
        result = await EditFileTool(cfg).execute(
            path=str(target),
            old_string="a",
            new_string="b",
        )
        assert result.startswith("[error] [constraint]")
        assert "matched 3 times" in result
        assert "add surrounding context" in result

    async def test_no_match_returns_constraint_error(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        target = tmp_path / "x.txt"
        target.write_text("hello world")
        result = await EditFileTool(cfg).execute(
            path=str(target),
            old_string="xyzzy",
            new_string="something",
        )
        assert result.startswith("[error] [constraint]")
        assert "not found" in result

    async def test_identical_strings_returns_constraint_error(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        target = tmp_path / "x.txt"
        target.write_text("hello")
        result = await EditFileTool(cfg).execute(
            path=str(target),
            old_string="hello",
            new_string="hello",
        )
        assert result.startswith("[error] [constraint]")
        assert "identical" in result and "no change" in result
        # File unchanged.
        assert target.read_text() == "hello"

    async def test_binary_refused_default(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        target = tmp_path / "binary.dat"
        target.write_bytes(b"hello\x00world")
        result = await EditFileTool(cfg).execute(
            path=str(target),
            old_string="hello",
            new_string="HELLO",
        )
        assert result.startswith("[error] [constraint]")
        assert "binary" in result

    async def test_size_cap_exceeded_returns_constraint(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(
            path_allowlist=[str(tmp_path)],
            path_denylist=[],
            read_size_cap_bytes=1024,
        )
        target = tmp_path / "big.txt"
        target.write_bytes(b"x" * 2048)
        result = await EditFileTool(cfg).execute(
            path=str(target),
            old_string="x",
            new_string="y",
        )
        assert result.startswith("[error] [constraint]")
        assert "exceeds cap" in result

    async def test_path_outside_allowlist_raises_constraint(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        result = await EditFileTool(cfg).execute(
            path="/etc/hostname",
            old_string="x",
            new_string="y",
        )
        assert result.startswith("[error] [constraint]")
        assert "outside allowlist" in result

    async def test_tilde_expansion(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        # On Windows, expanduser resolves USERPROFILE (not HOME).
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        monkeypatch.setenv("HOMEDRIVE", tmp_path.drive if tmp_path.drive else "")
        monkeypatch.setenv("HOMEPATH", str(tmp_path))
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        (tmp_path / "y.txt").write_text("foo bar\n")
        result = await EditFileTool(cfg).execute(
            path="~/y.txt",
            old_string="foo",
            new_string="FOO",
        )
        assert "Edited" in result
        assert (tmp_path / "y.txt").read_text() == "FOO bar\n"

    async def test_preview_contains_diff_markers(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        target = tmp_path / "x.txt"
        target.write_text("line1\nline2\nline3\nline4\nline5\n")
        result = await EditFileTool(cfg).execute(
            path=str(target),
            old_string="line3",
            new_string="LINE-3",
        )
        # Diff-style markers + line numbers visible.
        assert "- " in result and "    3 | line3" in result
        assert "+ " in result and "    3 | LINE-3" in result
        # Pre-context lines show line1, line2.
        assert "    1 | line1" in result
        assert "    2 | line2" in result
        # Post-context lines show line4, line5.
        assert "    4 | line4" in result
        assert "    5 | line5" in result

    async def test_old_string_spans_multiple_lines(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        target = tmp_path / "x.txt"
        target.write_text("alpha\nbeta\ngamma\ndelta\n")
        result = await EditFileTool(cfg).execute(
            path=str(target),
            old_string="beta\ngamma",
            new_string="BETA\nGAMMA\nEXTRA",
        )
        assert "Edited" in result
        # Two old lines marked with -, three new lines marked with +
        assert result.count("\n- ") == 2
        assert result.count("\n+ ") == 3
        assert target.read_text() == "alpha\nBETA\nGAMMA\nEXTRA\ndelta\n"

    async def test_old_string_ending_in_newline_no_overcount(self, tmp_path: Path) -> None:
        """Regression: span computation must use splitlines() length, not
        count('\\n') + 1. A trailing newline on old_string closes the last
        covered line; there is no partial line after it."""
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        target = tmp_path / "x.txt"
        target.write_text("a\nb\nc\nd\n")
        result = await EditFileTool(cfg).execute(
            path=str(target),
            old_string="b\nc\n",  # trailing \n
            new_string="X\n",  # trailing \n
        )
        assert "Edited" in result
        # 2 old lines deleted ("b", "c"), 1 new line inserted ("X").
        # If the algorithm overcounted, we would see 3 `-` and 2 `+` rows.
        assert result.count("\n- ") == 2
        assert result.count("\n+ ") == 1
        assert target.read_text() == "a\nX\nd\n"

    async def test_new_string_empty_deletion(self, tmp_path: Path) -> None:
        """Empty new_string deletes the matched region. Preview shows `-`
        rows for the old block and zero `+` rows."""
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        target = tmp_path / "x.txt"
        target.write_text("a\nb\nc\nd\n")
        result = await EditFileTool(cfg).execute(
            path=str(target),
            old_string="b\nc\n",
            new_string="",
        )
        assert "Edited" in result
        assert result.count("\n- ") == 2
        assert result.count("\n+ ") == 0
        assert target.read_text() == "a\nd\n"

    async def test_edit_at_first_line(self, tmp_path: Path) -> None:
        """Edit at line 1 emits no pre-context."""
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        target = tmp_path / "x.txt"
        target.write_text("first\nsecond\nthird\n")
        result = await EditFileTool(cfg).execute(
            path=str(target),
            old_string="first",
            new_string="FIRST",
        )
        assert "@@ around line 1 @@" in result
        # No pre-context lines (no leading `  N |` rows before the `-` block).
        # The line after the @@ header should be the `-` row.
        lines = result.split("\n")
        header_idx = next(i for i, line in enumerate(lines) if "@@" in line)
        assert lines[header_idx + 1].startswith("- "), lines[header_idx + 1]

    async def test_edit_at_last_line(self, tmp_path: Path) -> None:
        """Edit at last line emits no post-context."""
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        target = tmp_path / "x.txt"
        # No trailing newline on the last line.
        target.write_text("a\nb\nc")
        result = await EditFileTool(cfg).execute(
            path=str(target),
            old_string="c",
            new_string="C",
        )
        assert "Edited" in result
        # The last meaningful line in the result is the `+` row.
        # No `  N |` post-context rows after the `+` block.
        lines = [line for line in result.split("\n") if line]
        # Last line of the output should be a `+` row.
        assert lines[-1].startswith("+ "), lines[-1]


class TestDeleteFileTool:
    async def test_happy(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        target = tmp_path / "victim.txt"
        target.write_text("delete me")
        result = await DeleteFileTool(cfg).execute(path=str(target))
        assert result.startswith("Deleted")
        assert not target.exists()

    async def test_path_outside_allowlist_raises_constraint(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        result = await DeleteFileTool(cfg).execute(path="/etc/hostname")
        assert result.startswith("[error] [constraint]")
        assert "outside allowlist" in result

    async def test_path_inside_denylist_raises_constraint(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(
            path_allowlist=[str(tmp_path)],
            path_denylist=[str(tmp_path / "vault")],
        )
        target = tmp_path / "vault" / "secret.txt"
        target.parent.mkdir()
        target.write_text("x")
        result = await DeleteFileTool(cfg).execute(path=str(target))
        assert result.startswith("[error] [constraint]")
        assert "inside denylist" in result

    async def test_directory_refused(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        d = tmp_path / "subdir"
        d.mkdir()
        result = await DeleteFileTool(cfg).execute(path=str(d))
        assert result.startswith("[error] [constraint]")
        assert "is a directory" in result
        assert "delete_file operates on files only" in result

    async def test_file_does_not_exist_returns_environmental_error(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        # In-scope but no file there.
        result = await DeleteFileTool(cfg).execute(path=str(tmp_path / "missing.txt"))
        # Environmental error → starts with [error] but no [constraint] tag.
        assert result.startswith("[error]")
        assert "[constraint]" not in result

    async def test_tilde_expansion(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        # On Windows, expanduser resolves USERPROFILE (not HOME).
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        monkeypatch.setenv("HOMEDRIVE", tmp_path.drive if tmp_path.drive else "")
        monkeypatch.setenv("HOMEPATH", str(tmp_path))
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        (tmp_path / "h.txt").write_text("home")
        result = await DeleteFileTool(cfg).execute(path="~/h.txt")
        assert result.startswith("Deleted")
        assert not (tmp_path / "h.txt").exists()


class TestMoveFileTool:
    async def test_happy(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("hello")
        result = await MoveFileTool(cfg).execute(source=str(src), destination=str(dst))
        assert result.startswith("Moved")
        assert dst.read_text() == "hello"
        assert not src.exists()

    async def test_source_outside_allowlist_raises_constraint(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        result = await MoveFileTool(cfg).execute(
            source="/etc/hostname",
            destination=str(tmp_path / "stolen.txt"),
        )
        assert result.startswith("[error] [constraint]")
        assert "outside allowlist" in result

    async def test_destination_parent_outside_allowlist_raises_constraint(
        self, tmp_path: Path
    ) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        src = tmp_path / "src.txt"
        src.write_text("x")
        result = await MoveFileTool(cfg).execute(
            source=str(src), destination="/etc/exfiltrated.txt"
        )
        assert result.startswith("[error] [constraint]")

    async def test_destination_exists_default_refused(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("new")
        dst.write_text("old")
        result = await MoveFileTool(cfg).execute(source=str(src), destination=str(dst))
        assert result.startswith("[error] [constraint]")
        assert "exists" in result
        assert "overwrite=true" in result
        # Both files unchanged.
        assert src.read_text() == "new"
        assert dst.read_text() == "old"

    async def test_destination_exists_overwrite_permits(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("new")
        dst.write_text("old")
        result = await MoveFileTool(cfg).execute(
            source=str(src), destination=str(dst), overwrite=True
        )
        assert result.startswith("Moved")
        assert dst.read_text() == "new"
        assert not src.exists()

    async def test_source_does_not_exist_returns_environmental_error(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        result = await MoveFileTool(cfg).execute(
            source=str(tmp_path / "missing.txt"),
            destination=str(tmp_path / "anywhere.txt"),
        )
        assert result.startswith("[error]")
        assert "[constraint]" not in result

    async def test_destination_parent_missing_returns_environmental_error(
        self, tmp_path: Path
    ) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        src = tmp_path / "src.txt"
        src.write_text("x")
        # Destination's parent doesn't exist.
        result = await MoveFileTool(cfg).execute(
            source=str(src),
            destination=str(tmp_path / "nonexistent-dir" / "dst.txt"),
        )
        assert result.startswith("[error]")
        # _filesystem_check_write_parent raises FileNotFoundError, NOT ConstraintError.
        assert "[constraint]" not in result

    async def test_tilde_expansion(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        # On Windows, expanduser resolves USERPROFILE (not HOME).
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        monkeypatch.setenv("HOMEDRIVE", tmp_path.drive if tmp_path.drive else "")
        monkeypatch.setenv("HOMEPATH", str(tmp_path))
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        (tmp_path / "src.txt").write_text("home")
        result = await MoveFileTool(cfg).execute(source="~/src.txt", destination="~/dst.txt")
        assert result.startswith("Moved")
        assert (tmp_path / "dst.txt").read_text() == "home"


class TestMkdirTool:
    async def test_happy_creates_dir(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        target = tmp_path / "new_dir"
        result = await MkdirTool(cfg).execute(path=str(target))
        assert result.startswith("Created")
        assert target.is_dir()

    async def test_creates_intermediates(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        deep = tmp_path / "a" / "b" / "c" / "d"
        result = await MkdirTool(cfg).execute(path=str(deep))
        assert result.startswith("Created")
        assert deep.is_dir()
        assert (tmp_path / "a" / "b").is_dir()

    async def test_existing_dir_silent_success(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        # tmp_path already exists.
        result = await MkdirTool(cfg).execute(path=str(tmp_path))
        assert result.startswith("Created")
        assert tmp_path.is_dir()

    async def test_path_outside_allowlist_raises_constraint(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        result = await MkdirTool(cfg).execute(path="/etc/newdir")
        assert result.startswith("[error] [constraint]")
        assert "outside allowlist" in result

    async def test_tilde_expansion(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        # On Windows, expanduser resolves USERPROFILE (not HOME).
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        monkeypatch.setenv("HOMEDRIVE", tmp_path.drive if tmp_path.drive else "")
        monkeypatch.setenv("HOMEPATH", str(tmp_path))
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        result = await MkdirTool(cfg).execute(path="~/newdir")
        assert result.startswith("Created")
        assert (tmp_path / "newdir").is_dir()


class TestGlobTool:
    async def test_happy_finds_matching_files(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        (tmp_path / "a.py").write_text("x")
        (tmp_path / "b.py").write_text("y")
        (tmp_path / "c.txt").write_text("z")
        result = await GlobTool(cfg).execute(pattern="*.py", root=str(tmp_path))
        assert "a.py" in result and "b.py" in result
        assert "c.txt" not in result

    async def test_recursive_with_double_star(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        (tmp_path / "a.py").write_text("x")
        sub = tmp_path / "sub" / "sub2"
        sub.mkdir(parents=True)
        (sub / "b.py").write_text("y")
        result = await GlobTool(cfg).execute(pattern="**/*.py", root=str(tmp_path))
        assert "a.py" in result and "b.py" in result

    async def test_no_matches_returns_no_matches(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        result = await GlobTool(cfg).execute(pattern="*.nonexistent", root=str(tmp_path))
        assert result == "(no matches)"

    async def test_root_outside_allowlist_raises_constraint(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        result = await GlobTool(cfg).execute(pattern="*", root="/etc")
        assert result.startswith("[error] [constraint]")
        assert "outside allowlist" in result

    async def test_root_is_file_returns_constraint(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        f = tmp_path / "x.txt"
        f.write_text("x")
        result = await GlobTool(cfg).execute(pattern="*", root=str(f))
        assert result.startswith("[error] [constraint]")
        assert "not a directory" in result

    async def test_oos_match_skipped_silently_with_count(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        (tmp_path / "real.txt").write_text("x")
        (tmp_path / "escape").symlink_to("/etc")  # symlink to OOS dir
        result = await GlobTool(cfg).execute(pattern="*", root=str(tmp_path))
        # In-scope file present; symlink resolves to /etc which is OOS.
        assert "real.txt" in result
        assert "skipped" in result and "outside scope" in result

    async def test_500_match_cap(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        target = tmp_path / "many"
        target.mkdir()
        for i in range(550):
            (target / f"f{i:03d}.txt").write_text("x")
        result = await GlobTool(cfg).execute(pattern="*.txt", root=str(target))
        assert "and 50 more" in result

    async def test_root_default_is_cwd(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Default root="." is canonicalized via cwd; ensure scope rejection
        # path is exercised when cwd is not in the allowlist.
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        # Switch cwd to a different scratch dir outside the allowlist.
        other = tmp_path.parent / "other-cwd"
        other.mkdir(exist_ok=True)
        monkeypatch.chdir(other)
        result = await GlobTool(cfg).execute(pattern="*.txt")
        assert result.startswith("[error] [constraint]")


class TestGrepTool:
    async def test_happy_finds_matching_lines(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        (tmp_path / "a.py").write_text("def foo():\n    return foo\n")
        result = await GrepTool(cfg).execute(pattern="foo", path=str(tmp_path))
        assert "a.py:1:def foo():" in result
        assert "a.py:2:    return foo" in result

    async def test_fixed_string_mode(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        # `.` would match every char as regex; fixed_string=True only matches a literal `.`
        (tmp_path / "a.txt").write_text("hello world\nliteral.dot\n")
        result = await GrepTool(cfg).execute(pattern=".", path=str(tmp_path), fixed_string=True)
        # Only line 2 has a literal `.`
        assert "a.txt:2:" in result
        assert "a.txt:1:" not in result

    async def test_regex_default(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        (tmp_path / "a.py").write_text("def foo():\n    pass\ndef bar():\n    pass\n")
        result = await GrepTool(cfg).execute(pattern=r"def \w+", path=str(tmp_path))
        assert "def foo" in result and "def bar" in result

    async def test_no_match_returns_no_matches(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        (tmp_path / "a.txt").write_text("hello\n")
        result = await GrepTool(cfg).execute(pattern="xyzzy", path=str(tmp_path))
        assert result == "(no matches)"

    async def test_file_pattern_filter(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        (tmp_path / "a.py").write_text("foo\n")
        (tmp_path / "b.txt").write_text("foo\n")
        result = await GrepTool(cfg).execute(pattern="foo", path=str(tmp_path), file_pattern="*.py")
        assert "a.py:1:foo" in result
        assert "b.txt" not in result

    async def test_binary_skipped_silently_with_count(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        (tmp_path / "text.txt").write_text("foo\n")
        (tmp_path / "bin.dat").write_bytes(b"foo\x00\n")  # has null byte
        result = await GrepTool(cfg).execute(pattern="foo", path=str(tmp_path))
        assert "text.txt:1:foo" in result
        assert "bin.dat" not in result
        assert "skipped 1 binary file" in result

    async def test_oversized_skipped_silently_with_count(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(
            path_allowlist=[str(tmp_path)],
            path_denylist=[],
            read_size_cap_bytes=1024,
        )
        (tmp_path / "small.txt").write_text("foo\n")
        (tmp_path / "big.txt").write_bytes(b"foo\n" + b"x" * 2000)
        result = await GrepTool(cfg).execute(pattern="foo", path=str(tmp_path))
        assert "small.txt:1:foo" in result
        assert "big.txt" not in result
        assert "skipped 1 oversized file" in result

    async def test_root_outside_allowlist_raises_constraint(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        result = await GrepTool(cfg).execute(pattern="x", path="/etc")
        assert result.startswith("[error] [constraint]")
        assert "outside allowlist" in result

    async def test_500_global_cap(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        # Create one file with 600 lines containing the pattern.
        # But we have a 100-per-file cap, so we need multiple files.
        # 6 files x 100 matches each = 600 matches; global cap fires at 500.
        for i in range(6):
            (tmp_path / f"f{i}.txt").write_text("x\n" * 110)
        result = await GrepTool(cfg).execute(pattern="x", path=str(tmp_path))
        assert "global cap of 500 reached" in result

    async def test_per_file_cap_at_100(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        (tmp_path / "many.txt").write_text("x\n" * 150)
        result = await GrepTool(cfg).execute(pattern="x", path=str(tmp_path))
        # Only first 100 matches emitted from many.txt
        assert "many.txt:100:x" in result
        assert "many.txt:101:x" not in result
        assert "per-file cap reached for 1 file" in result

    async def test_invalid_regex_returns_environmental_error(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        (tmp_path / "a.txt").write_text("x\n")
        result = await GrepTool(cfg).execute(pattern="[invalid", path=str(tmp_path))
        assert result.startswith("[error]")
        # re.error is environmental, NOT a constraint refusal
        assert "[constraint]" not in result

    async def test_recursive_descent(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        (tmp_path / "a.py").write_text("foo\n")
        sub = tmp_path / "sub" / "deep"
        sub.mkdir(parents=True)
        (sub / "b.py").write_text("foo\n")
        result = await GrepTool(cfg).execute(pattern="foo", path=str(tmp_path))
        assert "a.py:1:foo" in result
        assert "b.py:1:foo" in result


class TestFilesystemToolInstantiation:
    def test_each_tool_has_filesystem_config(self) -> None:
        for cls in (
            ReadFileTool,
            WriteFileTool,
            EditFileTool,
            ListDirTool,
            DeleteFileTool,
            MoveFileTool,
            MkdirTool,
            GlobTool,
            GrepTool,
        ):
            t1 = cls()
            assert isinstance(t1._config, FilesystemConfig)
            t2 = cls(FilesystemConfig(path_allowlist=["/tmp"]))
            assert t2._config.path_allowlist == ["/tmp"]
