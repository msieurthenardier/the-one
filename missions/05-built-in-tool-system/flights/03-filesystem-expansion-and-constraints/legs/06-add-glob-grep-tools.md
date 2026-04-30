# Leg: 06-add-glob-grep-tools

**Status**: landed
**Flight**: [Filesystem Expansion & Constraints](../flight.md)

## Objective

Add `GlobTool` and `GrepTool` to `the_one/tools/filesystem.py`. Both are pattern-matching tools over the filesystem; both must enforce `_filesystem_check` per match (not just per root) so symlinks that escape scope are excluded. `GrepTool` also enforces `_check_read_size` and `_is_binary` per file (skipping silently with a count). Both cap output at 500 matches with `... and N more` truncation. Register in `_TOOL_CLASSES` and Studio's `TOOL_CATEGORIES`.

## Context

L6 ships the last two filesystem tools. `glob` and `grep` differ from L3-L5 tools in one important way: they walk multiple files. Per-match scope checks are required because a glob match could resolve to a symlink that escapes the configured scope. The leg's central challenge is per-match enforcement without making the tools too slow on large trees.

**Relevant flight design decisions**:
- **Decision 9** — `grep(pattern, path, fixed_string=False, file_pattern="*")`. Default Python `re` regex; `fixed_string=True` switches to `str.find`. 500-match global cap with truncation marker. Skips binary files silently when `cfg.allow_binary_files=False`. Skips files exceeding `read_size_cap_bytes` silently.
- **Decision 9 sub-bullet** — Per-file match cap: 100 matches per file before moving on, prevents a single huge-match-count file from monopolizing output.
- **Decision 4** — `glob` uses Python `pathlib.Path.glob`/`rglob` semantics (not shell-style). Documented in the flight's "Acceptable variations" section.
- **Decision 1.5** — `ConstraintError` formatted as `[error] [constraint] {e}`; other exceptions as `[error] {e}`.
- **Decision 2** — `glob` reads `path_allowlist` + `path_denylist` only (no read I/O, no size, no binary). `grep` reads all four constraints (it walks files and reads them).

**Per-match scope enforcement**:

For `glob`:
- The user passes a `root` path and a `pattern`.
- `_filesystem_check(root, cfg)` validates the root.
- `Path.rglob(pattern)` returns descendants. Each match could be a symlink resolving outside scope.
- For each match, call `_filesystem_check(match, cfg)`:
  - If it raises `ConstraintError`, skip silently (with a counter for the output footer).
  - If it returns the canonical, include in the result.

For `grep`:
- Same per-match scope check via `Path.rglob(file_pattern)`.
- For each in-scope match, call `_check_read_size` (skip silently with counter on cap-exceed) and `_is_binary` (skip silently with counter on binary refusal).
- For each remaining file, scan line-by-line for `pattern`; emit up to 100 matches per file; total cap 500.

**Output formats**:

`glob` output (one canonical path per line, 500-cap):
```
/tmp/scope/a.py
/tmp/scope/sub/b.py
/tmp/scope/sub/c.py
... and 47 more
(skipped 3 paths outside scope)
```

`grep` output (`path:line_num:matched_line`, 500-cap, +footer):
```
/tmp/scope/a.py:12:    return foo
/tmp/scope/sub/b.py:3:    foo = 1
... and 7 more
(skipped 2 binary files, 1 oversized file)
```

When `fixed_string=False` (the default), `pattern` is compiled via `re.compile(pattern)`. A bad regex raises `re.error`; the second-clause `except` catches it and returns `[error] re.error: ...`.

When `fixed_string=True`, scan via `if pattern in line` (each line is independent — no compilation).

## Inputs

Files that must exist (verified):
- `the_one/tools/filesystem.py` — has all 7 tools post-L5 + helpers.
- `the_one/tools/builtins.py` — `_TOOL_CLASSES` dict (11 entries today).
- `the_one/interfaces/web/static/js/areas/studio.js` — `TOOL_CATEGORIES` (Filesystem currently 7 entries).

State that must be true:
- L1 + L2a + L2b + L3 + L4 + L5 have all landed.
- `make test-unit` is at the post-L5 baseline of 626 passing.

## Outputs

Files modified:
- `the_one/tools/filesystem.py` — adds `GlobTool` and `GrepTool` classes (after `MkdirTool`, before `ListDirTool` is OK; insertion order in `_TOOL_CLASSES` is what matters for the registry, not source-file order). Net ~150 LoC.
- `the_one/tools/builtins.py` — adds two entries to `_TOOL_CLASSES`. Updates the import line.
- `the_one/interfaces/web/static/js/areas/studio.js` — adds `'glob'` and `'grep'` to the Filesystem category.
- `tests/test_filesystem_tools.py` — adds two new test classes (`TestGlobTool`, `TestGrepTool`); updates `TestFilesystemToolInstantiation::test_each_tool_has_filesystem_config`.
- `tests/test_builtins.py` — updates the three hardcoded `11`s (post-L5) to `13`; adds the two new names to the expected names set.

Files created: none.

State changes:
- `BuiltinToolProvider.get_tools(...)` returns 13 tools.
- Studio sidebar's Filesystem category has 9 entries.
- No DB schema changes. No migrations. No new env vars. No new ports.

## Acceptance Criteria

### `GlobTool`
- [ ] `name = "glob"`, description: `"Find files matching a pattern (Python pathlib glob syntax — '**' for recursive, '*' for any chars in a name). Returns canonical paths, one per line."`. Parameters: required `pattern: string`; optional `root: string = "."`. `Config = FilesystemConfig`.
- [ ] `execute(pattern, root=".")` flow:
  1. `cfg = self._config`.
  2. Two-clause try/except.
  3. `canonical_root = _filesystem_check(root, cfg)`.
  4. If `canonical_root.is_dir()` is False → `ConstraintError(f"glob root '{canonical_root}' is not a directory")` (avoids mysterious empty results when the agent passes a file).
  5. Walk: if pattern contains `**`, use `canonical_root.rglob(pattern)`; else use `canonical_root.glob(pattern)`. (Actually — `Path.glob` accepts `**` natively; just always use `glob(pattern)` and document the recursion semantics.)

   **Simpler**: always use `canonical_root.glob(pattern)`. `Path.glob` interprets `**` as recursive. Drop the `rglob` branch.
  6. For each match, call `_filesystem_check(match, cfg)`:
     - On `ConstraintError`, increment `skipped_oos` counter, continue.
     - On success, append canonical to `included`.
  7. Sort `included`, cap at 500.
  8. Build output:
     - One canonical path per line.
     - If `len(included_uncapped) > 500`: append `... and {N} more` line.
     - If `skipped_oos > 0`: append `(skipped {N} paths outside scope)` line.
  9. Return the assembled output, or `(no matches)` if both `included` and `skipped_oos` are zero.

### `GrepTool`
- [ ] `name = "grep"`, description: `"Search file contents for a pattern (regex by default, or literal-string with fixed_string=true). Returns matches as 'path:line_num:matched_line'. Skips binary and oversized files silently."`. Parameters: required `pattern: string`, `path: string`; optional `fixed_string: bool = False`, `file_pattern: string = "*"`. `Config = FilesystemConfig`.
- [ ] `execute(pattern, path, fixed_string=False, file_pattern="*")` flow:
  1. `cfg = self._config`.
  2. Two-clause try/except.
  3. `canonical_root = _filesystem_check(path, cfg)`.
  4. If `canonical_root.is_dir()` is False → `ConstraintError(f"grep root '{canonical_root}' is not a directory")`.
  5. If not `fixed_string`: compile `regex = re.compile(pattern)`. (`re.error` from a bad pattern falls through as `[error] {e}`.)
  6. Initialize counters: `matches: list[str] = []`, `skipped_binary = 0`, `skipped_oversized = 0`, `total_match_count = 0`, `truncated_files: list[Path] = []`.
  7. Walk `canonical_root.rglob(file_pattern)` (always recursive — `grep` is dir-tree-wide by default).
  8. For each candidate path:
     - If not `path.is_file()`: continue.
     - Try `_filesystem_check(path, cfg)`:
       - On `ConstraintError`: continue silently (we don't surface OOS skip count for grep — too noisy).
     - Try `_check_read_size(path, cfg)`:
       - On `ConstraintError`: increment `skipped_oversized`, continue.
     - If `_is_binary(path) and not cfg.allow_binary_files`: increment `skipped_binary`, continue.
     - Read text: `text = path.read_text(errors="replace")`.
     - Scan lines:
       - `per_file_count = 0`.
       - For each `(idx, line)` enumerated 1-indexed:
         - Match: `match_found = (pattern in line)` if `fixed_string` else `regex.search(line) is not None`.
         - If matched:
           - If `total_match_count >= 500`: break out of all loops (global cap).
           - If `per_file_count >= 100`: track in `truncated_files`, break inner loop (per-file cap).
           - Append `f"{path}:{idx}:{line}"` to `matches`.
           - `per_file_count += 1`.
           - `total_match_count += 1`.
  9. Build output:
     - Join `matches` lines.
     - If `total_match_count >= 500`: append `... and more matches (global cap of 500 reached)`.
     - If `truncated_files`: append `(per-file cap reached for {N} file(s); first 100 matches per file shown)`.
     - If `skipped_binary > 0`: append `(skipped {N} binary file(s))`.
     - If `skipped_oversized > 0`: append `(skipped {N} oversized file(s))`.
  10. Return the assembled output, or `(no matches)` if `matches` is empty.

### Registry + UI
- [ ] `_TOOL_CLASSES` insertion order: `glob`, `grep` slot together, AFTER `mkdir` and BEFORE `list_dir`. Final Filesystem grouping: `read_file, write_file, edit_file, delete_file, move_file, mkdir, glob, grep, list_dir` (9 entries).
- [ ] Studio `TOOL_CATEGORIES['Filesystem']` mirrors that order.
- [ ] `tests/test_builtins.py`: hardcoded `11`s updated to `13`; expected names set adds `"glob"`, `"grep"`.

### Tests
- [ ] `TestGlobTool`:
  - `test_happy_finds_matching_files` — create `a.py`, `b.py`, `c.txt` in `tmp_path`; `pattern="*.py"`; result has both `.py` paths, no `.txt`.
  - `test_recursive_with_double_star` — create files under `tmp_path/sub/sub2/`; `pattern="**/*.py"`; recursive descent works.
  - `test_no_matches_returns_no_matches` — `pattern="*.nonexistent"`; result is `(no matches)`.
  - `test_root_outside_allowlist_raises_constraint` — `root="/etc"`.
  - `test_root_is_file_returns_constraint` — pass a file path as root; constraint error mentioning "not a directory".
  - `test_oos_match_skipped_silently_with_count` — create a symlink under tmp_path pointing to `/etc/hostname`; glob it via `*`; the symlink resolves OOS; output includes `(skipped 1 paths outside scope)`.
  - `test_500_match_cap` — create 550 files matching; output ends with `... and 50 more`.
  - `test_root_default_is_cwd` — `pattern="*.txt"`, no `root` arg; ensure default `"."` is canonicalized via cwd. (May be skipped if tmp_path-only sandbox can't ensure cwd; test the constraint-rejection path instead.)
- [ ] `TestGrepTool`:
  - `test_happy_finds_matching_lines` — file `a.py` with `def foo():\n    return foo`; `pattern="foo"`; result has both lines.
  - `test_fixed_string_mode` — `pattern="."`, `fixed_string=True`; matches only literal `.` (not "any char").
  - `test_regex_default` — `pattern=r"def \w+"`; matches function definitions.
  - `test_no_match_returns_no_matches` — `pattern="xyzzy"`.
  - `test_file_pattern_filter` — multiple files; `file_pattern="*.py"`; only `.py` files searched.
  - `test_binary_skipped_silently_with_count` — 1 text + 1 binary; output includes `(skipped 1 binary file(s))` and only text-file matches.
  - `test_oversized_skipped_silently_with_count` — 1 small + 1 big (>cap); output includes `(skipped 1 oversized file(s))`.
  - `test_root_outside_allowlist_raises_constraint` — `path="/etc"`.
  - `test_500_global_cap` — file with 600 matches of `pattern="x"`; output ends with `... and more matches (global cap of 500 reached)`.
  - `test_per_file_cap_at_100` — file with 150 matches; only first 100 emitted; output footer mentions per-file cap.
  - `test_invalid_regex_returns_environmental_error` — `pattern="[invalid"`; result starts with `[error]` but no `[constraint]`.
  - `test_recursive_descent` — `pattern="x"`; files in nested subdirs; all matches found.

Total new tests: **8 + 12 = 20**.

- [ ] `make test-unit` passes (target: post-L5 baseline 626 + 20 new = ~646 passed, modulo pre-existing CSS-token red).
- [ ] `ruff check` and `ruff format --check` clean on changed files.

## Verification Steps

Static:

```bash
cd /home/cprch/projects/the-one

rg -n "^class (Glob|Grep)Tool\b" the_one/tools/filesystem.py
# Expected: 2

# Re module imported (for grep's regex path)
rg -n "^import re\b|^from re\b" the_one/tools/filesystem.py
# Expected: 1

# Per-match _filesystem_check loop in glob/grep
rg -n "for .* in .*\.glob\(|for .* in .*\.rglob\(" the_one/tools/filesystem.py
# Expected: 2+ (one per tool)

# Registry has 13
rg -n '": ' the_one/tools/builtins.py | wc -l
# Expected: ≥ 13
```

Dynamic:

```bash
docker exec the-one pytest tests/test_filesystem_tools.py tests/test_filesystem_helpers.py tests/test_filesystem_config.py tests/test_resolver.py tests/test_builtins.py -v
# Expected: post-L5 + 20 new

make test-unit
# Expected: ~646 passed; only pre-existing CSS-token red

# End-to-end smoke
docker exec the-one python -c "
import asyncio, tempfile
from pathlib import Path
from the_one.tools.filesystem import GlobTool, GrepTool, FilesystemConfig
async def main():
    with tempfile.TemporaryDirectory() as d:
        cfg = FilesystemConfig(path_allowlist=[d], path_denylist=[])
        Path(d, 'a.py').write_text('def foo():\n    return 1\n')
        Path(d, 'b.txt').write_text('foo bar\n')
        Path(d, 'sub').mkdir()
        Path(d, 'sub', 'c.py').write_text('def baz():\n    pass\n')
        # glob
        out = await GlobTool(cfg).execute(pattern='**/*.py', root=d)
        assert 'a.py' in out and 'c.py' in out
        # grep
        out = await GrepTool(cfg).execute(pattern='foo', path=d)
        assert 'foo' in out
        print('OK')
asyncio.run(main())
"
```

## Implementation Guidance

### Step 1: Add `import re` at the top of `the_one/tools/filesystem.py`

If not already present (it likely isn't), add `import re` to the stdlib import block.

### Step 2: Add `GlobTool` and `GrepTool` after `MkdirTool`

```python
class GlobTool(Tool):
    name = "glob"
    description = (
        "Find files matching a pattern (Python pathlib glob syntax — "
        "'**' for recursive, '*' for any chars in a name). Returns "
        "canonical paths, one per line. Capped at 500 matches."
    )
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Glob pattern (e.g. '*.py', '**/*.txt').",
            },
            "root": {
                "type": "string",
                "description": "Directory to search from (default: '.').",
                "default": ".",
            },
        },
        "required": ["pattern"],
    }
    Config = FilesystemConfig

    async def execute(
        self, pattern: str, root: str = ".", **kwargs: Any
    ) -> str:
        cfg: FilesystemConfig = self._config
        try:
            canonical_root = _filesystem_check(root, cfg)
            if not canonical_root.is_dir():
                raise ConstraintError(
                    f"glob root '{canonical_root}' is not a directory"
                )
            included: list[Path] = []
            skipped_oos = 0
            for match in canonical_root.glob(pattern):
                try:
                    canonical_match = _filesystem_check(match, cfg)
                except ConstraintError:
                    skipped_oos += 1
                    continue
                included.append(canonical_match)
            included.sort()
            capped = included[:500]
            lines = [str(p) for p in capped]
            if len(included) > 500:
                lines.append(f"... and {len(included) - 500} more")
            if skipped_oos > 0:
                lines.append(f"(skipped {skipped_oos} paths outside scope)")
            return "\n".join(lines) if lines else "(no matches)"
        except ConstraintError as e:
            return f"[error] [constraint] {e}"
        except Exception as e:
            return f"[error] {e}"


class GrepTool(Tool):
    name = "grep"
    description = (
        "Search file contents for a pattern (regex by default, or "
        "literal-string with fixed_string=true). Returns matches as "
        "'path:line_num:matched_line'. Skips binary and oversized files "
        "silently. Capped at 500 total matches and 100 per file."
    )
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Search pattern (regex by default).",
            },
            "path": {
                "type": "string",
                "description": "Directory to search.",
            },
            "fixed_string": {
                "type": "boolean",
                "description": "If true, treat pattern as literal text.",
                "default": False,
            },
            "file_pattern": {
                "type": "string",
                "description": "Glob filter for files to search (default '*').",
                "default": "*",
            },
        },
        "required": ["pattern", "path"],
    }
    Config = FilesystemConfig

    async def execute(
        self,
        pattern: str,
        path: str,
        fixed_string: bool = False,
        file_pattern: str = "*",
        **kwargs: Any,
    ) -> str:
        cfg: FilesystemConfig = self._config
        try:
            canonical_root = _filesystem_check(path, cfg)
            if not canonical_root.is_dir():
                raise ConstraintError(
                    f"grep root '{canonical_root}' is not a directory"
                )
            regex: re.Pattern | None = None
            if not fixed_string:
                regex = re.compile(pattern)
            matches: list[str] = []
            skipped_binary = 0
            skipped_oversized = 0
            truncated_files = 0
            global_cap_hit = False

            for candidate in canonical_root.rglob(file_pattern):
                if global_cap_hit:
                    break
                if not candidate.is_file():
                    continue
                try:
                    canonical_candidate = _filesystem_check(candidate, cfg)
                except ConstraintError:
                    continue
                try:
                    _check_read_size(canonical_candidate, cfg)
                except ConstraintError:
                    skipped_oversized += 1
                    continue
                if _is_binary(canonical_candidate) and not cfg.allow_binary_files:
                    skipped_binary += 1
                    continue
                text = canonical_candidate.read_text(errors="replace")
                per_file_count = 0
                for line_idx, line in enumerate(text.splitlines(), start=1):
                    if fixed_string:
                        matched = pattern in line
                    else:
                        matched = regex.search(line) is not None
                    if not matched:
                        continue
                    if len(matches) >= 500:
                        global_cap_hit = True
                        break
                    if per_file_count >= 100:
                        truncated_files += 1
                        break
                    matches.append(f"{canonical_candidate}:{line_idx}:{line}")
                    per_file_count += 1

            lines: list[str] = list(matches)
            if global_cap_hit:
                lines.append("... and more matches (global cap of 500 reached)")
            if truncated_files > 0:
                lines.append(
                    f"(per-file cap reached for {truncated_files} file(s); "
                    "first 100 matches per file shown)"
                )
            if skipped_binary > 0:
                lines.append(f"(skipped {skipped_binary} binary file(s))")
            if skipped_oversized > 0:
                lines.append(
                    f"(skipped {skipped_oversized} oversized file(s))"
                )
            return "\n".join(lines) if lines else "(no matches)"
        except ConstraintError as e:
            return f"[error] [constraint] {e}"
        except Exception as e:
            return f"[error] {e}"
```

Note: the per-file truncation increments `truncated_files` only AFTER the inner loop hits the per-file cap. The 101st match is the trigger; matches 1-100 are emitted.

### Step 3: Register in `_TOOL_CLASSES`

```python
from the_one.tools.filesystem import (
    DeleteFileTool,
    EditFileTool,
    GlobTool,
    GrepTool,
    ListDirTool,
    MkdirTool,
    MoveFileTool,
    ReadFileTool,
    WriteFileTool,
)

_TOOL_CLASSES: dict[str, type[Tool]] = {
    "shell": ShellTool,
    "read_file": ReadFileTool,
    "write_file": WriteFileTool,
    "edit_file": EditFileTool,
    "delete_file": DeleteFileTool,
    "move_file": MoveFileTool,
    "mkdir": MkdirTool,
    "glob": GlobTool,
    "grep": GrepTool,
    "list_dir": ListDirTool,
    "python_exec": PythonExecTool,
    "http_request": HttpRequestTool,
    "web_search": WebSearchTool,
}
```

(13 entries.)

### Step 4: Update Studio's `TOOL_CATEGORIES`

```javascript
var TOOL_CATEGORIES = {
  'Filesystem': ['read_file', 'write_file', 'edit_file', 'delete_file', 'move_file', 'mkdir', 'glob', 'grep', 'list_dir'],
  'Execution': ['shell', 'python_exec'],
  'Web': ['http_request', 'web_search']
};
```

### Step 5: Add tests

In `tests/test_filesystem_tools.py`, extend the import:

```python
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
```

Add `TestGlobTool` and `TestGrepTool` classes (after `TestMkdirTool`, before `TestFilesystemToolInstantiation`).

```python
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
        result = await GlobTool(cfg).execute(
            pattern="**/*.py", root=str(tmp_path)
        )
        assert "a.py" in result and "b.py" in result

    async def test_no_matches_returns_no_matches(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        result = await GlobTool(cfg).execute(
            pattern="*.nonexistent", root=str(tmp_path)
        )
        assert result == "(no matches)"

    async def test_root_outside_allowlist_raises_constraint(
        self, tmp_path: Path
    ) -> None:
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

    async def test_oos_match_skipped_silently_with_count(
        self, tmp_path: Path
    ) -> None:
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
        result = await GrepTool(cfg).execute(
            pattern=".", path=str(tmp_path), fixed_string=True
        )
        # Only line 2 has a literal `.`
        assert "a.txt:2:" in result
        assert "a.txt:1:" not in result

    async def test_regex_default(self, tmp_path: Path) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        (tmp_path / "a.py").write_text(
            "def foo():\n    pass\ndef bar():\n    pass\n"
        )
        result = await GrepTool(cfg).execute(
            pattern=r"def \w+", path=str(tmp_path)
        )
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
        result = await GrepTool(cfg).execute(
            pattern="foo", path=str(tmp_path), file_pattern="*.py"
        )
        assert "a.py:1:foo" in result
        assert "b.txt" not in result

    async def test_binary_skipped_silently_with_count(
        self, tmp_path: Path
    ) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        (tmp_path / "text.txt").write_text("foo\n")
        (tmp_path / "bin.dat").write_bytes(b"foo\x00\n")  # has null byte
        result = await GrepTool(cfg).execute(pattern="foo", path=str(tmp_path))
        assert "text.txt:1:foo" in result
        assert "bin.dat" not in result
        assert "skipped 1 binary file" in result

    async def test_oversized_skipped_silently_with_count(
        self, tmp_path: Path
    ) -> None:
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

    async def test_root_outside_allowlist_raises_constraint(
        self, tmp_path: Path
    ) -> None:
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

    async def test_invalid_regex_returns_environmental_error(
        self, tmp_path: Path
    ) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        (tmp_path / "a.txt").write_text("x\n")
        result = await GrepTool(cfg).execute(
            pattern="[invalid", path=str(tmp_path)
        )
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
```

Update the instantiation test:

```python
class TestFilesystemToolInstantiation:
    def test_each_tool_has_filesystem_config(self) -> None:
        for cls in (
            ReadFileTool, WriteFileTool, EditFileTool, ListDirTool,
            DeleteFileTool, MoveFileTool, MkdirTool,
            GlobTool, GrepTool,
        ):
            t1 = cls()
            assert isinstance(t1._config, FilesystemConfig)
            t2 = cls(FilesystemConfig(path_allowlist=["/tmp"]))
            assert t2._config.path_allowlist == ["/tmp"]
```

### Step 6: Update `tests/test_builtins.py`

Three `11`s → `13`. Names set: add `"glob"` and `"grep"` after `"mkdir"`.

### Step 7: Run lint + tests; iterate

```bash
docker exec the-one ruff check the_one/tools/filesystem.py the_one/tools/builtins.py tests/test_filesystem_tools.py tests/test_builtins.py
docker exec the-one ruff format --check ...
docker exec the-one pytest tests/test_filesystem_tools.py tests/test_filesystem_helpers.py tests/test_filesystem_config.py tests/test_resolver.py tests/test_builtins.py -v
make test-unit
```

### Step 8: Update flight log + leg status

- Append `### Leg 06 — Add glob, grep tools` entry under "Leg Progress" in `flight-log.md`.
- Set leg `Status` to `landed`.
- Do NOT commit. Signal `[HANDOFF:review-needed]`.

## Edge Cases

- **`Path.glob` with `**`**: Python's `pathlib.Path.glob` interprets `**` as recursive, BUT only when surrounded by path separators (`/**/`). At the bare root (e.g., `pattern="**"`), behavior is platform-dependent. Tests use `pattern="**/*.py"` which works portably.
- **Glob against a file (not directory)**: `is_dir()` check upfront rejects this with a clear constraint message — agent gets a useful error rather than silent empty output.
- **`Path.rglob` on a symlinked directory**: rglob does NOT follow symlinks by default in Python 3.11+. Tests' OOS-symlink case relies on this — the symlink itself is what's matched, and `_filesystem_check` resolves it to OOS.
- **Empty file in grep**: `read_text` returns `""`, `splitlines() == []`, no matches emitted — silently skipped. No special handling needed.
- **`fixed_string=True` with empty pattern**: `"" in line` is always True (every line "contains" the empty string). Output would be every line of every file, capped at 500. Defensible but spammy. Not specifically tested; accept.
- **Regex compilation per call**: `re.compile(pattern)` runs once per `execute`, then `regex.search` runs per line. Acceptable performance under the 1MB cap.
- **`grep` with binary files when `cfg.allow_binary_files=True`**: the binary check is gated on the cfg flag; if operator permits, binaries are scanned via `read_text(errors="replace")`. Result lines may have replacement chars but won't crash. Not specifically tested; documented.
- **Symlinked directory in glob root**: if `root` itself is a symlink that resolves OOS, `_filesystem_check(root, cfg)` fails at the constraint check before any rglob. Covered by `test_root_outside_allowlist_raises_constraint`.
- **Per-file cap counter accuracy**: increments only when the inner loop actually hits the 101st match (line 8.6 in the spec). If a file has exactly 100 matches, no `truncated_files` increment. Correct.

## Files Affected

- `the_one/tools/filesystem.py` — add `import re`, add 2 tool classes (~150 LoC total).
- `the_one/tools/builtins.py` — extend import, add 2 dict entries (~5 LoC).
- `the_one/interfaces/web/static/js/areas/studio.js` — 1-line change (extend Filesystem array).
- `tests/test_filesystem_tools.py` — add 2 test classes (~250 LoC), update instantiation test.
- `tests/test_builtins.py` — update 3 count assertions + names set.

Total: ~410 LoC across 5 files.

**Out of scope for L6**:

- HAT walkthrough → L7.
- Documentation refresh → L8.
- Per-tool tests for the existing 4 helpers (already covered in L2b/L3-L5).

---

## Post-Completion Checklist

- [ ] All acceptance criteria verified
- [ ] Tests passing (target: ~646 passed; only pre-existing CSS-token red)
- [ ] `ruff check` and `ruff format --check` clean
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed`
- [ ] DO NOT check off this leg in `flight.md` (deferred to final commit)
- [ ] DO NOT commit; DO NOT signal `[COMPLETE:leg]`
- [ ] Signal `[HANDOFF:review-needed]`
