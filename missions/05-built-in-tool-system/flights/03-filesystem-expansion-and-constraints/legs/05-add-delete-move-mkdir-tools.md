# Leg: 05-add-delete-move-mkdir-tools

**Status**: landed
**Flight**: [Filesystem Expansion & Constraints](../flight.md)

## Objective

Add three small file-level operations: `DeleteFileTool`, `MoveFileTool`, `MkdirTool`. Each routes through the existing `_filesystem_check` family from L2b/L3. `move_file` introduces the `overwrite: bool = False` parameter (Decision 10) — explicit override flag matching `mkdir`'s `parents=True, exist_ok=True` precedent. Register all three in `_TOOL_CLASSES` and Studio's `TOOL_CATEGORIES`.

## Context

L5 adds three single-purpose tools whose contract is small and uniform: each calls `_filesystem_check` (or `_filesystem_check_write_path` / `_filesystem_check_write_parent`) and performs a single OS-level operation. No streaming, no preview rendering, no multi-step state machines. The tests follow the same constraint-violation pattern established in L3-L4.

**Helper-mapping per tool** (from L3's three-helper set):

| Tool | Read check | Write check | Notes |
|------|------------|-------------|-------|
| `delete_file` | `_filesystem_check(path)` | (none — same path) | refuses directories; `unlink()` only works on files |
| `move_file` | `_filesystem_check(source)` | `_filesystem_check_write_parent(destination)` | source must exist (read check naturally requires this); destination's parent MUST exist (use parent variant); `overwrite=False` default |
| `mkdir` | (none — creating new) | `_filesystem_check_write_path(path)` | parents=True so intermediate dirs OK; uses the no-existence-check variant |

**Relevant flight design decisions**:
- **Decision 10** — `move_file` destination policy: explicit `overwrite: bool = False` parameter; refuses if destination exists and `overwrite=False`; permits when `overwrite=True`. Mirrors `mkdir`'s `exist_ok=True` precedent for explicit-override-flag-visible-in-tool-schema.
- **Decision 1.5** — All three tools format `ConstraintError` as `[error] [constraint] {e}`; other exceptions as `[error] {e}`.
- **Decision 2** — All three tools share `Config = FilesystemConfig`. `delete_file` / `move_file` / `mkdir` only use `path_allowlist` + `path_denylist` (no read I/O, no size checks, no binary detection).

**`delete_file` directory-refusal**: keep the contract minimal — `delete_file` operates on FILES. If the agent passes a directory path, refuse with a clear error: `"path '{canonical}' is a directory; delete_file operates on files only"`. Future leg may add a separate `delete_dir` if needed.

**`move_file` source/destination semantics**:
- Source must exist (the read-check requires it; if not, `_filesystem_check` returns the canonical but `Path.replace` fails with `FileNotFoundError` → `[error] {e}`, not constraint).
- Destination's parent must exist AND be in scope (use `_filesystem_check_write_parent`). Move operation does NOT auto-create parent dirs — the agent should `mkdir` first if needed.
- If destination exists and `overwrite=False` → `ConstraintError("destination '{canonical_dst}' exists; pass overwrite=True to replace it")`.
- If `overwrite=True` and destination exists → `Path.replace` (atomic move on POSIX; overwrites unconditionally).
- If `overwrite=True` and destination doesn't exist → `Path.replace` (still atomic; rename-only).

**`mkdir` semantics**:
- Uses `_filesystem_check_write_path` (no existence check on parent — `mkdir(parents=True)` creates intermediates).
- `parents=True, exist_ok=True` matches Python's stdlib idiom; the leaf-already-exists case is silent success.
- Returns `f"Created {canonical}"` even on `exist_ok=True` no-op (path was already there) — the agent gets a uniform success signal.

## Inputs

Files that must exist (verified):
- `the_one/tools/filesystem.py` — has `FilesystemConfig`, `ConstraintError`, `_filesystem_check`, `_filesystem_check_write_parent`, `_filesystem_check_write_path`, `_check_read_size`, `_is_binary`, the 4 tools post-L4 (`ReadFileTool`, `WriteFileTool`, `EditFileTool`, `ListDirTool`).
- `the_one/tools/builtins.py` — `_TOOL_CLASSES` dict (8 entries today).
- `the_one/interfaces/web/static/js/areas/studio.js` — `TOOL_CATEGORIES` (Filesystem currently has 4 entries).

State that must be true:
- L1 + L2a + L2b + L3 + L4 have all landed (uncommitted).
- `make test-unit` is at the post-L4 baseline of 607 passing.

## Outputs

Files modified:
- `the_one/tools/filesystem.py` — adds `DeleteFileTool`, `MoveFileTool`, `MkdirTool` classes (one after another, after `ListDirTool`).
- `the_one/tools/builtins.py` — adds three entries to `_TOOL_CLASSES`. Updates the import line.
- `the_one/interfaces/web/static/js/areas/studio.js` — adds `'delete_file'`, `'move_file'`, `'mkdir'` to the Filesystem category.
- `tests/test_filesystem_tools.py` — adds three new test classes (`TestDeleteFileTool`, `TestMoveFileTool`, `TestMkdirTool`); updates `TestFilesystemToolInstantiation::test_each_tool_has_filesystem_config` to include the three new classes.
- `tests/test_builtins.py` — updates the three hardcoded `8`s (post-L4) to `11`; adds the three new names to the expected names set.

Files created: none.

State changes:
- `BuiltinToolProvider.get_tools(...)` returns 11 tools instead of 8.
- `_TOOL_CLASSES` dict gains 3 entries; Studio sidebar adds 3 entries under Filesystem.
- No DB schema changes. No migrations. No new env vars. No new ports.

## Acceptance Criteria

### `DeleteFileTool`
- [ ] `name = "delete_file"`, description: `"Delete a file. Refuses directories — use a different approach for those."`. Parameters: required `path: string`. `Config = FilesystemConfig`.
- [ ] `execute(path)` flow:
  1. `cfg = self._config`.
  2. Two-clause try/except (`ConstraintError` → `[error] [constraint] {e}`; other → `[error] {e}`).
  3. `canonical = _filesystem_check(path, cfg)`.
  4. If `canonical.is_dir()` → `ConstraintError(f"path '{canonical}' is a directory; delete_file operates on files only")`.
  5. `canonical.unlink()`.
  6. Return `f"Deleted {canonical}"`.

### `MoveFileTool`
- [ ] `name = "move_file"`, description: `"Move or rename a file from source to destination. By default refuses to overwrite an existing destination — pass overwrite=true to permit."`. Parameters: required `source: string`, `destination: string`; optional `overwrite: bool = False`. `Config = FilesystemConfig`.
- [ ] `execute(source, destination, overwrite=False)` flow:
  1. `cfg = self._config`.
  2. Two-clause try/except.
  3. `canonical_src = _filesystem_check(source, cfg)`.
  4. `canonical_dst = _filesystem_check_write_parent(destination, cfg)`.
  5. If `canonical_dst.exists() and not overwrite` → `ConstraintError(f"destination '{canonical_dst}' exists; pass overwrite=true to replace it")`.
  6. `canonical_src.replace(canonical_dst)` (atomic on POSIX; overwrites if destination exists and `overwrite=True`).
  7. Return `f"Moved {canonical_src} → {canonical_dst}"`.

### `MkdirTool`
- [ ] `name = "mkdir"`, description: `"Create a directory and any missing parent directories. Idempotent — succeeds silently if the directory already exists."`. Parameters: required `path: string`. `Config = FilesystemConfig`.
- [ ] `execute(path)` flow:
  1. `cfg = self._config`.
  2. Two-clause try/except.
  3. `canonical = _filesystem_check_write_path(path, cfg)`.
  4. `canonical.mkdir(parents=True, exist_ok=True)`.
  5. Return `f"Created {canonical}"`.

### Registry + UI
- [ ] `_TOOL_CLASSES` insertion order: `delete_file`, `move_file`, `mkdir` slot together, AFTER `edit_file` and BEFORE `list_dir`. The full Filesystem grouping in `_TOOL_CLASSES` becomes: `read_file`, `write_file`, `edit_file`, `delete_file`, `move_file`, `mkdir`, `list_dir`.
- [ ] Studio `TOOL_CATEGORIES['Filesystem']` becomes: `['read_file', 'write_file', 'edit_file', 'delete_file', 'move_file', 'mkdir', 'list_dir']`.
- [ ] `tests/test_builtins.py`: hardcoded `8`s updated to `11`; expected names set adds `"delete_file"`, `"move_file"`, `"mkdir"`.

### Tests
- [ ] `TestDeleteFileTool`:
  - `test_happy` — file exists, in scope; deleted; result starts with `Deleted`; file no longer exists.
  - `test_path_outside_allowlist_raises_constraint` — `/etc/hostname`; constraint error.
  - `test_path_inside_denylist_raises_constraint` — denylisted path.
  - `test_directory_refused` — passes a dir path; constraint error mentioning "directory" and "delete_file operates on files only".
  - `test_file_does_not_exist_returns_environmental_error` — in-scope path with no file; result starts with `[error]` but does NOT contain `[constraint]` (the unlink raises `FileNotFoundError`, formatted as the second-clause `[error] {e}`).
  - `test_tilde_expansion` — `~/foo.txt` with HOME monkeypatch.
- [ ] `TestMoveFileTool`:
  - `test_happy` — source exists, in scope; destination's parent in scope; result starts with `Moved`.
  - `test_source_outside_allowlist_raises_constraint` — `/etc/hostname` source; constraint error.
  - `test_destination_parent_outside_allowlist_raises_constraint` — destination `/etc/foo`; constraint error.
  - `test_destination_exists_default_refused` — destination already exists; `overwrite=False` (default); constraint error mentions `overwrite=true`.
  - `test_destination_exists_overwrite_permits` — destination exists; `overwrite=True`; succeeds; old destination content replaced.
  - `test_source_does_not_exist_returns_environmental_error` — in-scope but no source file; `[error] {e}` (NOT constraint).
  - `test_destination_parent_missing_returns_environmental_error` — destination's parent doesn't exist (and is in scope); `_filesystem_check_write_parent` raises `FileNotFoundError`; `[error] {e}` (not constraint).
  - `test_tilde_expansion` — both source and destination via `~/`.
- [ ] `TestMkdirTool`:
  - `test_happy_creates_dir` — passes `tmp_path/new_dir`; result starts with `Created`; dir exists.
  - `test_creates_intermediates` — passes `tmp_path/a/b/c/d`; all intermediates created.
  - `test_existing_dir_silent_success` — passes `tmp_path` itself (already exists); succeeds (`exist_ok=True`).
  - `test_path_outside_allowlist_raises_constraint` — `/etc/newdir`.
  - `test_tilde_expansion` — `~/newdir` with HOME monkeypatch.

Total new tests: **18** (6 + 8 + 4 = 18, plus tilde-expansion redundancy makes 19).

- [ ] `make test-unit` passes (target: post-L4 baseline 607 + 19 new = ~626 passed, modulo pre-existing CSS-token red).
- [ ] `ruff check` and `ruff format --check` clean on changed files.

## Verification Steps

Static:

```bash
cd ~/projects/the-one

# Three new tool classes
rg -n "^class (DeleteFile|MoveFile|Mkdir)Tool\b" the_one/tools/filesystem.py
# Expected: 3

# Each calls a check helper
rg -n "_filesystem_check\b|_filesystem_check_write_parent\b|_filesystem_check_write_path\b" the_one/tools/filesystem.py
# Expected: 7+ matches (existing 4 + new 3)

# Registry has 11 entries
rg -n '": ' the_one/tools/builtins.py | wc -l
# Expected: ≥ 11

# Studio TOOL_CATEGORIES has all three
rg -n "'(delete_file|move_file|mkdir)'" the_one/interfaces/web/static/js/areas/studio.js
# Expected: 3 matches
```

Dynamic:

```bash
docker exec the-one pytest tests/test_filesystem_tools.py tests/test_filesystem_helpers.py tests/test_filesystem_config.py tests/test_resolver.py tests/test_builtins.py -v
# Expected: post-L4 + 19 new tests, all pass

make test-unit
# Expected: ~626 passed; only the pre-existing CSS-token red

# End-to-end smoke
docker exec the-one python -c "
import asyncio, tempfile
from pathlib import Path
from the_one.tools.filesystem import (
    DeleteFileTool, MoveFileTool, MkdirTool, FilesystemConfig
)
async def main():
    with tempfile.TemporaryDirectory() as d:
        cfg = FilesystemConfig(path_allowlist=[d], path_denylist=[])
        # mkdir
        new_dir = Path(d) / 'a' / 'b'
        out = await MkdirTool(cfg).execute(path=str(new_dir))
        assert out.startswith('Created')
        assert new_dir.is_dir()
        # write a file via WriteFileTool semantics for the move test
        src = new_dir / 'src.txt'
        src.write_text('hi')
        # move
        dst = Path(d) / 'dst.txt'
        out = await MoveFileTool(cfg).execute(
            source=str(src), destination=str(dst)
        )
        assert out.startswith('Moved')
        assert dst.read_text() == 'hi'
        assert not src.exists()
        # delete
        out = await DeleteFileTool(cfg).execute(path=str(dst))
        assert out.startswith('Deleted')
        assert not dst.exists()
        print('OK')
asyncio.run(main())
"
```

Quality:

```bash
docker exec the-one ruff check the_one/tools/filesystem.py the_one/tools/builtins.py tests/test_filesystem_tools.py tests/test_builtins.py
docker exec the-one ruff format --check ...
```

## Implementation Guidance

### Step 1: Add the three tool classes after `ListDirTool`

```python
class DeleteFileTool(Tool):
    name = "delete_file"
    description = (
        "Delete a file. Refuses directories — use a different approach "
        "for those."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to delete."},
        },
        "required": ["path"],
    }
    Config = FilesystemConfig

    async def execute(self, path: str, **kwargs: Any) -> str:
        cfg: FilesystemConfig = self._config
        try:
            canonical = _filesystem_check(path, cfg)
            if canonical.is_dir():
                raise ConstraintError(
                    f"path '{canonical}' is a directory; "
                    "delete_file operates on files only"
                )
            canonical.unlink()
            return f"Deleted {canonical}"
        except ConstraintError as e:
            return f"[error] [constraint] {e}"
        except Exception as e:
            return f"[error] {e}"


class MoveFileTool(Tool):
    name = "move_file"
    description = (
        "Move or rename a file from source to destination. By default "
        "refuses to overwrite an existing destination — pass "
        "overwrite=true to permit."
    )
    parameters = {
        "type": "object",
        "properties": {
            "source": {"type": "string", "description": "Source path."},
            "destination": {"type": "string", "description": "Destination path."},
            "overwrite": {
                "type": "boolean",
                "description": "Overwrite an existing destination.",
                "default": False,
            },
        },
        "required": ["source", "destination"],
    }
    Config = FilesystemConfig

    async def execute(
        self,
        source: str,
        destination: str,
        overwrite: bool = False,
        **kwargs: Any,
    ) -> str:
        cfg: FilesystemConfig = self._config
        try:
            canonical_src = _filesystem_check(source, cfg)
            canonical_dst = _filesystem_check_write_parent(destination, cfg)
            if canonical_dst.exists() and not overwrite:
                raise ConstraintError(
                    f"destination '{canonical_dst}' exists; "
                    "pass overwrite=true to replace it"
                )
            canonical_src.replace(canonical_dst)
            return f"Moved {canonical_src} → {canonical_dst}"
        except ConstraintError as e:
            return f"[error] [constraint] {e}"
        except Exception as e:
            return f"[error] {e}"


class MkdirTool(Tool):
    name = "mkdir"
    description = (
        "Create a directory and any missing parent directories. "
        "Idempotent — succeeds silently if the directory already exists."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory path to create."},
        },
        "required": ["path"],
    }
    Config = FilesystemConfig

    async def execute(self, path: str, **kwargs: Any) -> str:
        cfg: FilesystemConfig = self._config
        try:
            canonical = _filesystem_check_write_path(path, cfg)
            canonical.mkdir(parents=True, exist_ok=True)
            return f"Created {canonical}"
        except ConstraintError as e:
            return f"[error] [constraint] {e}"
        except Exception as e:
            return f"[error] {e}"
```

### Step 2: Register in `_TOOL_CLASSES`

Edit `the_one/tools/builtins.py`:

```python
from the_one.tools.filesystem import (
    DeleteFileTool,
    EditFileTool,
    ListDirTool,
    MkdirTool,
    MoveFileTool,
    ReadFileTool,
    WriteFileTool,
)

# ...

_TOOL_CLASSES: dict[str, type[Tool]] = {
    "shell": ShellTool,
    "read_file": ReadFileTool,
    "write_file": WriteFileTool,
    "edit_file": EditFileTool,
    "delete_file": DeleteFileTool,
    "move_file": MoveFileTool,
    "mkdir": MkdirTool,
    "list_dir": ListDirTool,
    "python_exec": PythonExecTool,
    "http_request": HttpRequestTool,
    "web_search": WebSearchTool,
}
```

(11 entries total. Filesystem grouping: read → write → edit → delete → move → mkdir → list. Logical order: data lifecycle.)

### Step 3: Update Studio's `TOOL_CATEGORIES`

```javascript
var TOOL_CATEGORIES = {
  'Filesystem': ['read_file', 'write_file', 'edit_file', 'delete_file', 'move_file', 'mkdir', 'list_dir'],
  'Execution': ['shell', 'python_exec'],
  'Web': ['http_request', 'web_search']
};
```

### Step 4: Add tests

In `tests/test_filesystem_tools.py`, extend the import:

```python
from the_one.tools.filesystem import (
    DeleteFileTool,
    EditFileTool,
    FilesystemConfig,
    ListDirTool,
    MkdirTool,
    MoveFileTool,
    ReadFileTool,
    WriteFileTool,
)
```

Add the three new test classes (after `TestEditFileTool`, before `TestFilesystemToolInstantiation`):

```python
class TestDeleteFileTool:
    async def test_happy(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        target = tmp_path / "victim.txt"
        target.write_text("delete me")
        result = await DeleteFileTool(cfg).execute(path=str(target))
        assert result.startswith("Deleted")
        assert not target.exists()

    async def test_path_outside_allowlist_raises_constraint(
        self, tmp_path: Path
    ) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        result = await DeleteFileTool(cfg).execute(path="/etc/hostname")
        assert result.startswith("[error] [constraint]")
        assert "outside allowlist" in result

    async def test_path_inside_denylist_raises_constraint(
        self, tmp_path: Path
    ) -> None:
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

    async def test_file_does_not_exist_returns_environmental_error(
        self, tmp_path: Path
    ) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        # In-scope but no file there.
        result = await DeleteFileTool(cfg).execute(
            path=str(tmp_path / "missing.txt")
        )
        # Environmental error → starts with [error] but no [constraint] tag.
        assert result.startswith("[error]")
        assert "[constraint]" not in result

    async def test_tilde_expansion(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
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
        result = await MoveFileTool(cfg).execute(
            source=str(src), destination=str(dst)
        )
        assert result.startswith("Moved")
        assert dst.read_text() == "hello"
        assert not src.exists()

    async def test_source_outside_allowlist_raises_constraint(
        self, tmp_path: Path
    ) -> None:
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

    async def test_destination_exists_default_refused(
        self, tmp_path: Path
    ) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        src.write_text("new")
        dst.write_text("old")
        result = await MoveFileTool(cfg).execute(
            source=str(src), destination=str(dst)
        )
        assert result.startswith("[error] [constraint]")
        assert "exists" in result
        assert "overwrite=true" in result
        # Both files unchanged.
        assert src.read_text() == "new"
        assert dst.read_text() == "old"

    async def test_destination_exists_overwrite_permits(
        self, tmp_path: Path
    ) -> None:
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

    async def test_source_does_not_exist_returns_environmental_error(
        self, tmp_path: Path
    ) -> None:
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

    async def test_tilde_expansion(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        (tmp_path / "src.txt").write_text("home")
        result = await MoveFileTool(cfg).execute(
            source="~/src.txt", destination="~/dst.txt"
        )
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

    async def test_path_outside_allowlist_raises_constraint(
        self, tmp_path: Path
    ) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        result = await MkdirTool(cfg).execute(path="/etc/newdir")
        assert result.startswith("[error] [constraint]")
        assert "outside allowlist" in result

    async def test_tilde_expansion(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        result = await MkdirTool(cfg).execute(path="~/newdir")
        assert result.startswith("Created")
        assert (tmp_path / "newdir").is_dir()
```

Update the instantiation test:

```python
class TestFilesystemToolInstantiation:
    def test_each_tool_has_filesystem_config(self) -> None:
        for cls in (
            ReadFileTool, WriteFileTool, EditFileTool, ListDirTool,
            DeleteFileTool, MoveFileTool, MkdirTool,
        ):
            t1 = cls()
            assert isinstance(t1._config, FilesystemConfig)
            t2 = cls(FilesystemConfig(path_allowlist=["/tmp"]))
            assert t2._config.path_allowlist == ["/tmp"]
```

### Step 5: Update `tests/test_builtins.py`

Replace the three hardcoded `8`s (post-L4) with `11`. Add `"delete_file"`, `"move_file"`, `"mkdir"` to the expected names set in the appropriate ordering (matching the `_TOOL_CLASSES` dict order).

### Step 6: Run lint + tests; iterate

```bash
docker exec the-one ruff check the_one/tools/filesystem.py the_one/tools/builtins.py tests/test_filesystem_tools.py tests/test_builtins.py
docker exec the-one ruff format --check ...
docker exec the-one pytest tests/test_filesystem_tools.py tests/test_filesystem_helpers.py tests/test_filesystem_config.py tests/test_resolver.py tests/test_builtins.py -v
make test-unit
```

### Step 7: Update flight log + leg status

- Append `### Leg 05 — Add delete_file, move_file, mkdir tools` entry under "Leg Progress" in `flight-log.md`.
- Set leg `Status` to `landed`.
- Do NOT commit. Do NOT signal `[COMPLETE:leg]`. Signal `[HANDOFF:review-needed]`.

## Edge Cases

- **`Path.replace` on POSIX is atomic for cross-name renames within the same filesystem**: `MoveFileTool` uses `replace` (not `rename`) to ensure the overwrite-existing-destination case works. On cross-filesystem moves, `replace` still works (Python falls back to copy-then-delete) but is no longer atomic. Tests don't exercise cross-filesystem; documented as known.
- **`MoveFileTool` source-and-destination identical**: `Path.replace(self)` is a no-op on POSIX. The tool returns `Moved {canonical_src} → {canonical_dst}` which would show identical paths. Acceptable; harmless.
- **`MoveFileTool` source is a directory**: `Path.replace` works for dirs too on POSIX. The tool's contract says "move or rename a file", but the implementation accepts dirs. This is technically broader than the description. Document as: "moving directories is supported but undocumented; tools description focuses on files for clarity". L4 design did not call this out. Acceptable.
- **`MkdirTool` on a path that exists as a FILE (not a dir)**: `Path.mkdir(parents=True, exist_ok=True)` raises `FileExistsError` if the path exists as a non-directory. The tool's two-clause catches this as a generic `[error] {e}`. The agent gets `[error] FileExistsError: ...`. Acceptable — environmental error.
- **`MkdirTool` racing**: another process creates the leaf between `_filesystem_check_write_path` and `mkdir`. `exist_ok=True` means we don't fail if it's a dir; we DO fail if it's a file (above). TOCTOU residual; documented in Decision 10.
- **`DeleteFileTool` on a symlink**: `unlink()` removes the symlink itself, not the target. Acceptable; tests don't explicitly cover but the L2b symlink-resolution semantics for `_filesystem_check` mean a symlink that ESCAPES scope is rejected at the canonical-resolution step, before unlink.
- **`MoveFileTool` source/destination both pointing through a symlink**: `_filesystem_check` resolves both. If either resolves outside scope, rejected. Acceptable.

## Files Affected

- `the_one/tools/filesystem.py` — adds 3 tool classes (~120 LoC). Net ~120 LoC.
- `the_one/tools/builtins.py` — extends import (4 new names), adds 3 dict entries. Net ~10 LoC.
- `the_one/interfaces/web/static/js/areas/studio.js` — 1-line change.
- `tests/test_filesystem_tools.py` — adds 3 test classes (~250 LoC), updates instantiation test.
- `tests/test_builtins.py` — updates 3 count assertions + names set.

Total: ~400 LoC across 5 files.

**Out of scope for L5**:

- `glob`, `grep` → L6.
- HAT walkthrough → L7.
- Documentation refresh → L8.

---

## Post-Completion Checklist

- [ ] All acceptance criteria verified
- [ ] Tests passing (target: ~626 passed; only pre-existing CSS-token red)
- [ ] `ruff check` and `ruff format --check` clean
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed`
- [ ] DO NOT check off this leg in `flight.md` (deferred to final commit)
- [ ] DO NOT commit; DO NOT signal `[COMPLETE:leg]`
- [ ] Signal `[HANDOFF:review-needed]`
