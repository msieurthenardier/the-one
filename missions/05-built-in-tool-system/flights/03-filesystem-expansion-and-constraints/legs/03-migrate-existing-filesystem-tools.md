# Leg: 03-migrate-existing-filesystem-tools

**Status**: landed
**Flight**: [Filesystem Expansion & Constraints](../flight.md)

## Objective

Wire `Config = FilesystemConfig` on `ReadFileTool`, `WriteFileTool`, `ListDirTool`. Route every path through `_filesystem_check` (read paths, listing root) or `_filesystem_check_write_parent` (write parent). Add binary-file refusal on `ReadFileTool` (gated on `cfg.allow_binary_files`). Standardize error formatting: `ConstraintError` → `[error] [constraint] {msg}`; other exceptions → `[error] {e}`. Update the existing `tests/test_filesystem_tools.py` suite to construct tools with a permissive `FilesystemConfig` (allowlist scoped to `tmp_path` or HOME=tmp_path) and add new constraint-violation cases.

## Context

L3 is the first leg that actually changes tool behavior. After L3, every existing filesystem operation flows through the L2b helpers. L4-L6 follow the same pattern for the new tools (`edit_file`, `delete_file`, `move_file`, `mkdir`, `glob`, `grep`).

**Why the existing tests will break without updates**: today's `ReadFileTool().execute(path=str(tmp_path/"x.txt"))` works because the tool has `Config = _EmptyConfig` and no scope check. Post-L3, `ReadFileTool` defaults to `FilesystemConfig()` with `path_allowlist=["~"]`. `tmp_path` (typically `/tmp/pytest-...` on Linux) is OUTSIDE `~`, so the call returns `[error] [constraint] path '...' outside allowlist`. Tests must either:
1. Pass a tool-scoped `FilesystemConfig(path_allowlist=[str(tmp_path)])` via the constructor, OR
2. Set `monkeypatch.setenv("HOME", str(tmp_path))` so `~` resolves into the test dir.

L3 picks **option 1** for new tests (more explicit; isolates each test's scope) and **option 2** for the existing tilde-expansion tests (they're already setting HOME). The mixed approach matches the existing test file's idioms.

**Test for `/nonexistent/file.txt`**: `TestReadFileTool::test_missing_file_returns_error_string` passes `/nonexistent/file.txt` and asserts `result.startswith("[error]")`. Post-L3 with the default config, the error will be `[error] [constraint] path '...' outside allowlist` — still starts with `[error]`. The assertion still passes. But the *intent* of the test (file-not-found surfacing as `[error]`) is no longer what fires — the constraint check trips first. Update the test to pass an allowlist that includes `/nonexistent`'s parent (`/`) so the file-not-found path is what fires; OR keep the assertion but rename the test to reflect the new surface (`test_out_of_scope_path_returns_error_string`). L3 picks the second option (rename + reassert on the constraint message) because adding `/` to the allowlist defeats the test of *file-not-found* behavior.

**Relevant flight design decisions**:
- **Decision 2** — `FilesystemConfig` shared across all 9 filesystem tools. Per-tool field consumption: `read_file` reads all four constraints; `write_file` reads path-scope only (writes are bounded by content the agent provides; output cap is F4/F5 territory); `list_dir` reads path-scope only.
- **Decision 1.5** — `ConstraintError` formatted as `[error] [constraint] {msg}`. Non-ConstraintError exceptions formatted as `[error] {e}`.
- **Decision 5** — `read_size_cap_bytes` enforced for `ReadFileTool` BEFORE any read I/O (use `path.stat().st_size` via `_check_read_size`).
- **Bool semantic / Decision 2 sub-bullet** — `cfg.allow_binary_files = False` by default; `ReadFileTool` refuses binary files unless the agent narrowed the cfg to permit (impossible with `False` default — only operators can permit at the tool level, then agents inherit the permission).

**`offset/limit` interaction with size cap**: A 2MB file with cap=1MB returns `[error] [constraint] file size 2097152 bytes exceeds cap 1048576 bytes; use offset/limit to paginate`. The agent then retries with `offset=0, limit=N`. Today's `read_file` reads the WHOLE file then slices lines — that loses the cap. Two options:
- **Option A**: keep current shape; cap fires before any read; `offset/limit` cannot bypass the cap (caller still gets the constraint error).
- **Option B**: open the file streamed; advance to `offset` byte-by-byte; respect cap per chunk.

Option A is simpler and matches Decision 5's framing ("cap exists to protect agent context"). The agent's `offset/limit` is for paging into already-allowed files, not for bypassing the cap. L3 picks Option A. The constraint message's "use offset/limit to paginate" hint is misleading in this respect — but the agent will discover empirically that offset/limit can't get past the cap on truly oversized files, and operators can raise the cap. **Sharpen the constraint message in L3** to: `f"file size {size} bytes exceeds cap {cap} bytes; truncate or have an operator raise the cap"`. (Decision: drop the "offset/limit" reference from the L2b error message in L3 to avoid misleading the agent.)

## Inputs

Files that must exist (verified):
- `the_one/tools/filesystem.py` — has `FilesystemConfig`, `ConstraintError`, `_filesystem_check`, `_filesystem_check_write_parent`, `_check_read_size`, `_is_binary` (L2a + L2b)
- `the_one/tools/builtins.py` — `_TOOL_CLASSES` dict + resolver-invoking factory path (F2 + L1 trio)
- `tests/test_filesystem_tools.py` — 12 passing tests against the F2 baseline behavior
- `tests/test_filesystem_helpers.py` — passes 29 tests post-L2b
- `tests/test_filesystem_config.py` — passes 18 tests post-L2a

State that must be true:
- L1 + L2a + L2b have all landed (uncommitted).
- Branch `flight/03-filesystem-expansion-and-constraints` checked out.

## Outputs

Files modified:
- `the_one/tools/filesystem.py` — adds `Config = FilesystemConfig` to all three existing tool classes; rewrites each `execute` to flow through helpers; standardizes error formatting. The `_check_read_size` error message tightened (drop "offset/limit" reference).
- `tests/test_filesystem_tools.py` — every existing test that uses a path outside `~` (i.e., `tmp_path`-based tests) constructs the tool with a `FilesystemConfig(path_allowlist=[str(tmp_path)])`. Tilde-expansion tests are unchanged (they already set HOME=tmp_path). One test (`test_missing_file_returns_error_string`) is renamed and its assertion updated to reflect that the constraint error now fires before the I/O. New constraint-violation tests added per tool (allowlist reject, denylist reject, size cap exceeded for `read_file`, binary refusal for `read_file`, write parent missing for `write_file`, write parent out-of-scope for `write_file`).
- `the_one/tools/filesystem.py` — also tightens the `_check_read_size` error message (drop "offset/limit"; replace with "truncate or have an operator raise the cap"). The L2b test in `tests/test_filesystem_helpers.py::TestCheckReadSize::test_over_cap_raises_constraint` needs its substring assertion updated correspondingly.

Files created: none.

State changes:
- ToolBehavior: every existing filesystem tool now refuses paths outside the resolved allowlist (default: `~` minus DEFAULT_PATH_DENYLIST). Existing operator/agent flows that read/write outside `~` will surface as constraint errors after L3 — operators should configure the tool-level `path_allowlist` if they need broader scope.
- No DB schema changes. No migrations. No new env vars. No `_TOOL_CLASSES` changes (the existing entries' `cls.Config` attribute changes; the dict shape is unchanged).
- Studio's `TOOL_CATEGORIES` is unchanged — `read_file`, `write_file`, `list_dir` were already in the Filesystem category.

## Acceptance Criteria

- [ ] `ReadFileTool`, `WriteFileTool`, `ListDirTool` each declare `Config = FilesystemConfig`.
- [ ] `ReadFileTool.execute(path, ...)`:
  - Calls `_filesystem_check(path, self._config)` first.
  - Calls `_check_read_size(canonical, self._config)` second.
  - Calls `_is_binary(canonical)` third; if True AND NOT `self._config.allow_binary_files`, raises `ConstraintError("binary file refused (operator can permit via allow_binary_files)")`. Note the operator-facing wording — the agent cannot self-grant permission, only narrow.
  - Then performs the actual `read_text(errors="replace")` + offset/limit slicing as today.
  - Wraps the whole body in `try/except ConstraintError as e` (returns `f"[error] [constraint] {e}"`) followed by `except Exception as e` (returns `f"[error] {e}"`).
- [ ] `WriteFileTool.execute(path, content, ...)`:
  - Calls `_filesystem_check_write_parent(path, self._config)` to get the canonical destination Path.
  - Performs `parent.mkdir(parents=True, exist_ok=True)` (preserves the existing "creates intermediate dirs" contract).
  - Performs `canonical.write_text(content)`.
  - Wraps in the same two-clause try/except. Returns `f"Wrote {len(content)} bytes to {canonical}"` on success.
- [ ] `ListDirTool.execute(path=".", recursive=False, ...)`:
  - Calls `_filesystem_check(path, self._config)` first.
  - Then performs the existing iterdir/rglob + 500-entry cap.
  - Wraps in the same two-clause try/except.
- [ ] `_check_read_size` error message in `the_one/tools/filesystem.py` tightened from `"file size N bytes exceeds cap M bytes; use offset/limit to paginate"` to `"file size N bytes exceeds cap M bytes"` — drop the hint string entirely. Rationale: today's `read_file` reads-then-slices so `offset/limit` cannot bypass the cap (Option A), but a future leg may stream-and-slice (Option B); the error message should not lock in either choice. The pure-numerics form is unambiguous and survives either future shape.
- [ ] `tests/test_filesystem_helpers.py::TestCheckReadSize::test_over_cap_raises_constraint`'s substring assertion is weakened to assert only on the size and cap numerics (`"2048" in msg and "1024" in msg and "exceeds cap" in msg`); drop the `"offset/limit to paginate"` substring assertion.
- [ ] `tests/test_filesystem_tools.py`:
  - Every existing test using `tmp_path` paths constructs the tool with `FilesystemConfig(path_allowlist=[str(tmp_path)])` (NOT `_EmptyConfig`). Tilde-expansion tests retain `monkeypatch.setenv("HOME", str(tmp_path))` AND now also pass an explicit `FilesystemConfig(path_allowlist=[str(tmp_path)])` so the tilde resolves into the allowlisted tmp_path scope.
  - `TestReadFileTool::test_missing_file_returns_error_string` is renamed to `test_out_of_scope_path_returns_constraint_error` and asserts `[error] [constraint] ... outside allowlist` substring.
  - `TestFilesystemToolInstantiation::test_each_tool_has_empty_config` is renamed to `test_each_tool_has_filesystem_config` and asserts `isinstance(t._config, FilesystemConfig)` — the empty-config era is over.
  - New constraint tests:
    - `TestReadFileTool::test_path_outside_allowlist_raises_constraint`
    - `TestReadFileTool::test_path_inside_denylist_raises_constraint`
    - `TestReadFileTool::test_size_cap_exceeded_returns_constraint`
    - `TestReadFileTool::test_binary_refusal_default`
    - `TestReadFileTool::test_binary_allowed_when_cfg_permits`
    - `TestWriteFileTool::test_parent_out_of_scope_raises_constraint`
    - `TestListDirTool::test_path_outside_allowlist_raises_constraint`
  - One direct test for the new helper added in `tests/test_filesystem_helpers.py::TestFilesystemCheckWritePath` (`_filesystem_check_write_path`) — happy (parent doesn't exist, scope check passes), out-of-scope (raises ConstraintError), no FileNotFoundError ever (the helper does NOT do existence checks). Locks the helper's contract independently of `WriteFileTool`.
- [ ] All new and updated tests pass; constraint-error responses start with `[error] [constraint]`; environmental errors (file-not-found, permission, etc.) start with `[error]` but do NOT include `[constraint]`.
- [ ] `make test-unit` passes (target: post-L2b baseline 583 + ~7 new tests in test_filesystem_tools.py + 3 in test_filesystem_helpers.py + renamed tests = ~593 passed (583 + 7 tool tests + 3 helper tests), modulo pre-existing CSS-token red).
- [ ] `ruff check` and `ruff format --check` clean on changed files.
- [ ] `tests/test_filesystem_config.py` and `tests/test_filesystem_helpers.py` continue passing unchanged (except for the `_check_read_size` substring update noted above).
- [ ] `tests/test_resolver.py` continues passing 39 tests unchanged.

## Verification Steps

Static (after edit, before test run):

```bash
cd ~/projects/the-one

# Three tools declare FilesystemConfig
rg -n "Config = FilesystemConfig" the_one/tools/filesystem.py
# Expected: 3 (ReadFileTool, WriteFileTool, ListDirTool)

# Each tool calls a check helper
rg -n "_filesystem_check\b|_filesystem_check_write_parent\b" the_one/tools/filesystem.py
# Expected: 3+ matches inside class bodies (one per tool minimum)

# Two-clause exception handler in each tool
rg -n "except ConstraintError" the_one/tools/filesystem.py
# Expected: 3+ matches (one per tool)

# Sharpened error message
rg -n "truncate or have an operator raise the cap" the_one/tools/filesystem.py
# Expected: 1 match (in _check_read_size)

# Old "offset/limit to paginate" wording removed
rg -n "offset/limit to paginate" the_one/tools/filesystem.py
# Expected: 0 matches
```

Dynamic:

```bash
docker exec the-one pytest tests/test_filesystem_tools.py -v
# Expected: 20 tests (13 baseline incl. instantiation + 7 new constraint cases), all pass

docker exec the-one pytest tests/test_filesystem_helpers.py -v
# Expected: 32 pass (29 baseline + 3 new TestFilesystemCheckWritePath tests); one substring update for over-cap

docker exec the-one pytest tests/test_filesystem_config.py -v
# Expected: 18 still pass

docker exec the-one pytest tests/test_resolver.py -v
# Expected: 39 still pass

make test-unit
# Expected: ~591 passed; only the pre-existing CSS-token red

# End-to-end smoke: a fresh ReadFileTool with default Config refuses out-of-scope path
docker exec the-one python -c "
import asyncio
from the_one.tools.filesystem import ReadFileTool
async def main():
    out = await ReadFileTool().execute(path='/etc/hostname')
    assert out.startswith('[error] [constraint]'), out
    assert 'outside allowlist' in out
    print('OK')
asyncio.run(main())
"

# End-to-end smoke: ReadFileTool with custom allowlist passes
docker exec the-one python -c "
import asyncio, tempfile, os
from pathlib import Path
from the_one.tools.filesystem import ReadFileTool, FilesystemConfig
async def main():
    with tempfile.TemporaryDirectory() as d:
        target = Path(d) / 'doc.txt'
        target.write_text('hello world')
        cfg = FilesystemConfig(path_allowlist=[d], path_denylist=[])
        out = await ReadFileTool(cfg).execute(path=str(target))
        assert 'hello world' in out, out
        print('OK')
asyncio.run(main())
"
```

Quality:

```bash
docker exec the-one ruff check the_one/tools/filesystem.py tests/test_filesystem_tools.py
docker exec the-one ruff format --check the_one/tools/filesystem.py tests/test_filesystem_tools.py
```

## Implementation Guidance

### Step 1: Tighten the `_check_read_size` error message

Edit the `_check_read_size` helper added in L2b. Drop the trailing hint entirely so the message reads `f"file size {size} bytes exceeds cap {cap} bytes"`. Rationale: the L2b hint "use offset/limit to paginate" is misleading because today's `read_file` reads-then-slices (Option A), so offset/limit cannot bypass the cap in practice; but a future leg may stream-and-slice (Option B), in which case "truncate or have an operator raise the cap" would be wrong. The pure-numerics form is unambiguous and survives either future shape.

```python
# the_one/tools/filesystem.py — _check_read_size body
def _check_read_size(path: Path, cfg: FilesystemConfig) -> int:
    size = path.stat().st_size
    if size > cfg.read_size_cap_bytes:
        raise ConstraintError(
            f"file size {size} bytes exceeds cap "
            f"{cfg.read_size_cap_bytes} bytes"
        )
    return size
```

Update the L2b test substring assertion to weaken to numerics-only (drop both the old "offset/limit to paginate" assertion and any new hint-string assertion):

```python
# tests/test_filesystem_helpers.py — TestCheckReadSize::test_over_cap_raises_constraint
# Replace:
assert "offset/limit to paginate" in msg
# With (numerics + the durable substring):
assert "2048" in msg and "1024" in msg
assert "exceeds cap" in msg
```

### Step 2: Wire `Config = FilesystemConfig` on the three existing tools

Insert `Config = FilesystemConfig` immediately after each `parameters = {...}` block. Update each `execute` method:

#### `ReadFileTool`

```python
class ReadFileTool(Tool):
    name = "read_file"
    description = "Read the contents of a file."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file."},
            "offset": {"type": "integer", "description": "Line number to start from (0-based)."},
            "limit": {"type": "integer", "description": "Max number of lines to read."},
        },
        "required": ["path"],
    }
    Config = FilesystemConfig

    async def execute(
        self,
        path: str,
        offset: int = 0,
        limit: int | None = None,
        **kwargs: Any,
    ) -> str:
        cfg: FilesystemConfig = self._config
        try:
            canonical = _filesystem_check(path, cfg)
            _check_read_size(canonical, cfg)
            if _is_binary(canonical) and not cfg.allow_binary_files:
                raise ConstraintError(
                    "binary file refused (operator can permit via allow_binary_files)"
                )
            text = canonical.read_text(errors="replace")
            lines = text.splitlines()
            if offset or limit:
                end = (offset + limit) if limit else None
                lines = lines[offset:end]
            return "\n".join(
                f"{i + offset + 1:>5} | {line}" for i, line in enumerate(lines)
            )
        except ConstraintError as e:
            return f"[error] [constraint] {e}"
        except Exception as e:
            return f"[error] {e}"
```

#### `WriteFileTool`

```python
class WriteFileTool(Tool):
    name = "write_file"
    description = "Write content to a file, creating directories as needed."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file."},
            "content": {"type": "string", "description": "Content to write."},
        },
        "required": ["path", "content"],
    }
    Config = FilesystemConfig

    async def execute(self, path: str, content: str, **kwargs: Any) -> str:
        cfg: FilesystemConfig = self._config
        try:
            canonical = _filesystem_check_write_parent(path, cfg)
            canonical.parent.mkdir(parents=True, exist_ok=True)
            canonical.write_text(content)
            return f"Wrote {len(content)} bytes to {canonical}"
        except ConstraintError as e:
            return f"[error] [constraint] {e}"
        except Exception as e:
            return f"[error] {e}"
```

Note: `_filesystem_check_write_parent` raises `FileNotFoundError` if the in-scope parent doesn't exist. But `mkdir(parents=True, exist_ok=True)` would create it. We have a subtle order problem: the helper rejects up front, so `write_file ~/projects/missing-dir/file.txt` returns `[error] parent does not exist...`. To preserve the existing "creates intermediate dirs" contract, `WriteFileTool` should pre-create the parent in scope BEFORE calling the helper. **Option**:

```python
    async def execute(self, path: str, content: str, **kwargs: Any) -> str:
        cfg: FilesystemConfig = self._config
        try:
            # Resolve the leaf's parent's scope first — but allow non-existent
            # parents because we'll create them. Use _filesystem_check on the
            # composed canonical (parent expanded lexically + leaf), then
            # mkdir(parents=True) the parent.
            p = Path(path).expanduser()
            # Lexical canonicalize of the parent — succeeds even for missing dirs
            from the_one.platform import canonicalize as _canon
            canonical_parent = _canon(p.parent)
            composed = canonical_parent / p.name
            canonical = _filesystem_check(composed, cfg)
            canonical.parent.mkdir(parents=True, exist_ok=True)
            canonical.write_text(content)
            return f"Wrote {len(content)} bytes to {canonical}"
        except ConstraintError as e:
            return f"[error] [constraint] {e}"
        except Exception as e:
            return f"[error] {e}"
```

The second option duplicates the lexical-canonicalize logic from `_filesystem_check_write_parent` minus the existence check. Trade-off:

- **Option A (use the helper as-is)**: `write_file` cannot create files in non-existent parent dirs — the agent must `mkdir` first. Breaks the `test_creates_parent_dirs` test (which today writes to `tmp_path/deep/nested/file.txt` and expects auto-creation). Loss of capability.
- **Option B (inline the lexical-canonicalize, skip the existence check)**: preserves the auto-create behavior. Duplicates ~3 lines from `_filesystem_check_write_parent`. **Pick Option B** to preserve the F2 contract; document the duplication as intentional.

A cleaner alternative is to add a third helper (`_filesystem_check_write_path`) that does the scope check on the lexical composition without the existence check. **Pick this**: extend L2b's helper set with `_filesystem_check_write_path` so `WriteFileTool` and L5's `MkdirTool`/`MoveFileTool` can share the same shape.

**L3 plan (final)**: add `_filesystem_check_write_path` to `the_one/tools/filesystem.py` (alongside the L2b helpers). It does scope-check on the composed canonical, no existence check. `WriteFileTool` calls it. `_filesystem_check_write_parent` keeps the existence-check variant (still useful for `move_file` destination semantics in L5 — destination's parent MUST exist, the agent has to mkdir first if needed). Document both in the helpers section.

#### Updated helper addition

```python
def _filesystem_check_write_path(
    path: str | Path, cfg: FilesystemConfig
) -> Path:
    """For write operations whose target may not exist AND whose parent
    may also not exist (the caller will `mkdir(parents=True)`): canonicalize
    the parent lexically (no existence check), compose with the leaf, and
    run the composition through ``_filesystem_check``.

    Raises:
        ConstraintError: if the composed path is outside scope.

    Use for `write_file` (auto-creates intermediates), `mkdir`. Use
    ``_filesystem_check_write_parent`` for `move_file` (destination's
    parent must already exist) or `edit_file`'s write-back."""
    p = Path(path).expanduser()
    canonical_parent = canonicalize(p.parent)
    composed = canonical_parent / p.name
    return _filesystem_check(composed, cfg)
```

**Update L3's `WriteFileTool` to use this new helper:**

```python
        canonical = _filesystem_check_write_path(path, cfg)
        canonical.parent.mkdir(parents=True, exist_ok=True)
        canonical.write_text(content)
```

#### `ListDirTool`

```python
class ListDirTool(Tool):
    name = "list_dir"
    description = "List files and directories at a given path."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory path (default: current dir)."},
            "recursive": {"type": "boolean", "description": "List recursively.", "default": False},
        },
        "required": [],
    }
    Config = FilesystemConfig

    async def execute(
        self, path: str = ".", recursive: bool = False, **kwargs: Any
    ) -> str:
        cfg: FilesystemConfig = self._config
        try:
            canonical = _filesystem_check(path, cfg)
            if recursive:
                entries = sorted(canonical.rglob("*"))
            else:
                entries = sorted(canonical.iterdir())
            lines = []
            for e in entries[:500]:
                prefix = "d " if e.is_dir() else "f "
                lines.append(f"{prefix}{e.relative_to(canonical)}")
            result = "\n".join(lines)
            if len(entries) > 500:
                result += f"\n... and {len(entries) - 500} more"
            return result or "(empty directory)"
        except ConstraintError as e:
            return f"[error] [constraint] {e}"
        except Exception as e:
            return f"[error] {e}"
```

### Step 3: Add new constraint-violation tests in `tests/test_filesystem_tools.py`

Add the import:

```python
from the_one.tools.filesystem import (
    FilesystemConfig,
    ListDirTool,
    ReadFileTool,
    WriteFileTool,
)
```

Drop the `_EmptyConfig` import (the empty-config era is over for filesystem tools).

Update existing tests to pass an allowlist that includes `tmp_path`. Pattern:

```python
async def test_happy_path(self, tmp_path: Path) -> None:
    cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
    f = tmp_path / "x.txt"
    f.write_text("alpha\nbeta\ngamma")
    result = await ReadFileTool(cfg).execute(path=str(f))
    ...
```

For the tilde tests, ALSO scope the allowlist to tmp_path (HOME=tmp_path so `~` expands into the allowlisted scope):

```python
async def test_tilde_expansion(
    self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
    (tmp_path / "y.txt").write_text("home content")
    result = await ReadFileTool(cfg).execute(path="~/y.txt")
    assert "home content" in result
```

Rename `test_missing_file_returns_error_string` and update its assertion:

```python
async def test_out_of_scope_path_returns_constraint_error(self) -> None:
    # Default config: allowlist is `~`, no denylist override. Out-of-scope
    # path surfaces as a constraint error before the I/O is attempted.
    result = await ReadFileTool().execute(path="/nonexistent/file.txt")
    assert result.startswith("[error] [constraint]")
    assert "outside allowlist" in result
```

Update the instantiation test:

```python
class TestFilesystemToolInstantiation:
    def test_each_tool_has_filesystem_config(self) -> None:
        for cls in (ReadFileTool, WriteFileTool, ListDirTool):
            t1 = cls()
            assert isinstance(t1._config, FilesystemConfig)
            t2 = cls(FilesystemConfig(path_allowlist=["/tmp"]))
            assert t2._config.path_allowlist == ["/tmp"]
```

Add the new constraint tests:

```python
class TestReadFileTool:
    # ... existing tests above ...

    async def test_path_outside_allowlist_raises_constraint(
        self, tmp_path: Path
    ) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        result = await ReadFileTool(cfg).execute(path="/etc/hostname")
        assert result.startswith("[error] [constraint]")
        assert "outside allowlist" in result

    async def test_path_inside_denylist_raises_constraint(
        self, tmp_path: Path
    ) -> None:
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

    async def test_size_cap_exceeded_returns_constraint(
        self, tmp_path: Path
    ) -> None:
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
    # ... existing tests above ...

    async def test_parent_out_of_scope_raises_constraint(
        self, tmp_path: Path
    ) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        result = await WriteFileTool(cfg).execute(
            path="/etc/newfile.txt", content="x"
        )
        assert result.startswith("[error] [constraint]")
        assert "outside allowlist" in result


class TestListDirTool:
    # ... existing tests above ...

    async def test_path_outside_allowlist_raises_constraint(
        self, tmp_path: Path
    ) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        result = await ListDirTool(cfg).execute(path="/etc")
        assert result.startswith("[error] [constraint]")
        assert "outside allowlist" in result
```

Note: `test_parent_missing_returns_filenotfound_error` is NOT included because we're using `_filesystem_check_write_path` (not `_filesystem_check_write_parent`) — `WriteFileTool` auto-creates parents and never sees a `FileNotFoundError`. The contract is: write operations through `WriteFileTool` create parents up to the in-scope tree boundary; the existence check only applies to `move_file` (L5) and `edit_file` (L4).

Add a direct test for the new helper at the end of `tests/test_filesystem_helpers.py`:

```python
class TestFilesystemCheckWritePath:
    """Direct tests for `_filesystem_check_write_path` (added in L3
    alongside the existing-tool migration). Helper does scope-check on
    a lexically-composed canonical, with NO existence check on the
    parent — used by `WriteFileTool` (auto-creates parents) and L5's
    `MkdirTool`."""

    def test_happy_parent_does_not_exist(
        self, tmp_path: Path, scoped_cfg: FilesystemConfig
    ) -> None:
        from the_one.tools.filesystem import _filesystem_check_write_path
        # Parent (`missing-parent`) does NOT exist. Helper must NOT raise.
        target = tmp_path / "missing-parent" / "child.txt"
        result = _filesystem_check_write_path(str(target), scoped_cfg)
        # Lexical composition; no existence check.
        assert result == (tmp_path.resolve() / "missing-parent" / "child.txt")

    def test_out_of_scope_raises_constraint(
        self, scoped_cfg: FilesystemConfig
    ) -> None:
        from the_one.tools.filesystem import _filesystem_check_write_path
        with pytest.raises(ConstraintError):
            _filesystem_check_write_path("/etc/secrets/foo", scoped_cfg)

    def test_does_not_raise_filenotfound_on_missing_parent(
        self, tmp_path: Path, scoped_cfg: FilesystemConfig
    ) -> None:
        from the_one.tools.filesystem import _filesystem_check_write_path
        # Locks the contract: this helper does NOT do existence checks.
        # Use `_filesystem_check_write_parent` if existence is required.
        target = tmp_path / "deeply" / "nested" / "missing" / "file.txt"
        # Should NOT raise FileNotFoundError; should succeed with composed path.
        result = _filesystem_check_write_path(str(target), scoped_cfg)
        assert "deeply" in str(result)
```

(Three tests in this class. Total new tests in `tests/test_filesystem_helpers.py` for L3 is 3, not 1 — but they belong to a single new `TestFilesystemCheckWritePath` class so the class header is what's listed in the AC.)

### Step 4: Run lint + tests; iterate until green

```bash
docker exec the-one ruff check the_one/tools/filesystem.py tests/test_filesystem_tools.py tests/test_filesystem_helpers.py
docker exec the-one ruff format the_one/tools/filesystem.py tests/test_filesystem_tools.py tests/test_filesystem_helpers.py
docker exec the-one pytest tests/test_filesystem_tools.py tests/test_filesystem_helpers.py tests/test_filesystem_config.py tests/test_resolver.py -v
make test-unit
```

Iterate on failures.

### Step 5: Update flight log + leg status

- Append `### Leg 03 — Migrate existing filesystem tools` entry under "Leg Progress" in `flight-log.md`.
- Set leg `Status` to `landed`.
- Do NOT commit. Do NOT signal `[COMPLETE:leg]`. Signal `[HANDOFF:review-needed]`.

## Edge Cases

- **`mkdir(parents=True, exist_ok=True)` on the canonical write path**: the canonical's parent (after `_filesystem_check_write_path`) may include intermediate dirs that don't yet exist. `mkdir` creates them; if any intermediate happens to be a symlink-to-elsewhere (created by an attacker between scope check and mkdir), TOCTOU applies — accepted per Decision 10. Tests don't cover this; documented as residual.
- **Binary refusal message wording**: `"binary file refused (operator can permit via allow_binary_files)"`. Avoid implying the agent can self-toggle the flag; only operators can. Small-model-friendly; flat sentence.
- **Default `path_denylist` and tests**: tests construct `FilesystemConfig` with `path_denylist=[]` to avoid the default 19-entry denylist interfering with `tmp_path`-based fixtures. Pattern: `FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])`.
- **`recursive=True` on `ListDirTool` with denylist**: today's `rglob("*")` returns descendants; if any descendant is itself in the denylist, it shows up in the listing. L3 does NOT filter the listing against the denylist (the listing is metadata, not access). Open question: should `list_dir` skip denylisted entries? Default: no — the listing reveals their existence but reading them via `read_file` is still blocked. Document as Decision: listing != access. Future leg may revisit if a use case emerges.
- **`_TOOL_CLASSES` unchanged**: the dict keys `"read_file"`, `"write_file"`, `"list_dir"` keep pointing at the same class objects; only `cls.Config` changes. The resolver (called from `BuiltinToolProvider.get_tools`) reads `cls.Config` per call, so a fresh `FilesystemConfig()` is built per agent invocation — no caching of stale empty configs.
- **Tool introspection path**: `BuiltinToolProvider.get_tools(None, None)` returns tools with `cls()` (default `FilesystemConfig()`). The `/api/tools` endpoint and zero-arg unit tests get a tool whose `_config.path_allowlist == ["~"]`. This is the intended default.
- **`canonicalize` import in WriteFileTool**: imported as `from the_one.platform import canonicalize` at module top (already there from L2a/L2b). The L3 implementation guidance's `from the_one.platform import canonicalize as _canon` is no longer needed since we factored to `_filesystem_check_write_path`. Drop the local-import note.
- **Default config in tests**: tests that exercise the default `~` allowlist end-to-end (smoke tests) need to set HOME=tmp_path AND construct the tool with `FilesystemConfig()` (no allowlist override). Otherwise `~` resolves to whatever HOME is in the test runner. Existing tilde-expansion tests are explicit about this.

## Files Affected

- `the_one/tools/filesystem.py` — adds `_filesystem_check_write_path` helper (~10 LoC), wires `Config = FilesystemConfig` on 3 tools, rewrites 3 `execute` methods (each ~10 LoC of changes), tightens `_check_read_size` message (1-line edit). Net ~50 added LoC.
- `tests/test_filesystem_tools.py` — updates ~12 existing tests to construct with `FilesystemConfig(...)`, renames 2 (`test_missing_file_...`, `test_each_tool_has_empty_config`), adds ~8 new constraint tests. Net ~150 added LoC.
- `tests/test_filesystem_helpers.py` — 1-line substring update in `test_over_cap_raises_constraint`.

Total: ~200 added/changed LoC across 3 files.

**Out of scope for L3 (deferred to other legs)**:

- New tools (`edit_file`, `delete_file`, `move_file`, `mkdir`, `glob`, `grep`) → L4-L6.
- Studio `TOOL_CATEGORIES` updates → L4-L6 (per new tool); L3 leaves the existing `Filesystem: read_file, write_file, list_dir` row unchanged.
- Browser tests for the Tools admin section → F6.
- AIAT live-smoke updates for the constraint behavior → optional in L8.
- `agents.md` / `CLAUDE.md` documentation refresh → L8.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`** (commit + leg-completion deferred to end-of-flight per agentic-workflow):

- [ ] All acceptance criteria verified
- [ ] Tests passing (`pytest tests/test_filesystem_tools.py tests/test_filesystem_helpers.py tests/test_filesystem_config.py tests/test_resolver.py -v`; `make test-unit` ≥ post-L2b baseline + ~7 new tests in test_filesystem_tools.py + 3 in test_filesystem_helpers.py)
- [ ] `ruff check` and `ruff format --check` clean on changed files
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed`
- [ ] DO NOT check off this leg in `flight.md` (deferred to final commit)
- [ ] DO NOT commit; DO NOT signal `[COMPLETE:leg]`
- [ ] Signal `[HANDOFF:review-needed]`
