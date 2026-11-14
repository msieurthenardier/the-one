# Leg: 04-add-edit-file-tool

**Status**: landed
**Flight**: [Filesystem Expansion & Constraints](../flight.md)

## Objective

Add `EditFileTool` (`name="edit_file"`) to `the_one/tools/filesystem.py`. Implements old_string/new_string in-place replacement with strict uniqueness, size-cap enforcement, binary refusal, and a formatted line-numbered preview of the edit. Register in `BuiltinToolProvider._TOOL_CLASSES` and Studio's `TOOL_CATEGORIES`. Decision 8 from the flight spec defines the contract; L4 implements it.

## Context

L4 ships the first NEW filesystem tool. Existing read/write/list flow through `_filesystem_check` (L3) — `edit_file` is a read-then-write tool that goes through both `_filesystem_check` (read side) and the equivalent of `_filesystem_check_write_parent` (write side). Because the leaf MUST exist for `edit_file` to find `old_string`, the read-side check naturally requires existence; the write-back targets the same canonical path, so no separate parent check is needed.

**Relevant flight design decisions**:
- **Decision 8** — `edit_file(path, old_string, new_string)`. `old_string` must appear EXACTLY ONCE; multi-match error encourages adding context. Refuses binary. Subject to read-size cap. `old_string == new_string` is a no-op refusal.
- **Decision 1.5** — `ConstraintError` formatted as `[error] [constraint] {msg}`; other exceptions as `[error] {e}`.
- **Decision 5** — Read-size cap fires on the file size before the edit (the file must be read into memory to find/replace).
- **Decision 2** — Binary detection via `_is_binary` from L2b. Refused if `not cfg.allow_binary_files`.

**Edit semantics — line-numbered preview**:
The agent's mental model is "I made this edit; here's what the surrounding region looks like now". The preview should show:
- The edit's location (file path + line number where the change starts).
- A few context lines before and after the change.
- The changed lines marked clearly.

Format (proposal):

```
Edited /path/to/file.py
@@ around line 12 @@
   10 |     def helper():
   11 |         pass
-  12 |     return old_value
+  12 |     return new_value
   13 | 
   14 | def main():
```

Trade-offs:
- Diff-style markers (`+`/`-`) are familiar to LLMs (matches Anthropic's Edit tool output).
- Line numbers help the agent verify the right region was edited.
- Context window: 2-3 lines before/after is typical; we'll go with **3** for predictability.

**Multi-match and no-match errors** must be actionable for small models:
- Multi-match: `"old_string matched N times; add surrounding context to make the match unique"`. The agent should know to read more lines around its target and rebuild the `old_string` with that context.
- No-match: `"old_string not found in file"`. The agent should re-read the file and check its `old_string` against current contents.
- No-op: `"old_string and new_string are identical; no change to apply"`.

## Inputs

Files that must exist (verified):
- `the_one/tools/filesystem.py` — has `FilesystemConfig`, `ConstraintError`, `_filesystem_check`, `_check_read_size`, `_is_binary`, the 3 existing tool classes (post-L3 with `Config = FilesystemConfig`).
- `the_one/tools/builtins.py` — `_TOOL_CLASSES` dict (7 entries today).
- `the_one/interfaces/web/static/js/areas/studio.js` — `TOOL_CATEGORIES` (lines 151-155).

State that must be true:
- L1 + L2a + L2b + L3 have all landed (uncommitted).
- `make test-unit` is at the post-L3 baseline of 593 passing.

## Outputs

Files modified:
- `the_one/tools/filesystem.py` — adds `EditFileTool` class after `ListDirTool`. Defines a private helper `_format_edit_preview(canonical, lines, edit_line_idx, old_lines_count, new_lines)` for the diff-style preview rendering. Net ~80 LoC.
- `the_one/tools/builtins.py` — adds `"edit_file": EditFileTool` to `_TOOL_CLASSES`. Updates the import line.
- `the_one/interfaces/web/static/js/areas/studio.js` — adds `'edit_file'` to the Filesystem category in `TOOL_CATEGORIES`. Single-line change.

Files created:
- New tests in `tests/test_filesystem_tools.py` under `class TestEditFileTool` — happy, multi-match-error, no-match-error, identical-strings-error, binary-refused, size-exceeded, write-out-of-scope (impossible because edit reads-and-writes the same path; cover via "read-side scope reject"), tilde expansion. ~10 tests. Updates the existing `TestFilesystemToolInstantiation::test_each_tool_has_filesystem_config` to also check `EditFileTool`.

State changes:
- `BuiltinToolProvider.get_tools(...)` returns 8 tools instead of 7. Update the existing `tests/test_builtins.py` count assertion if any.
- `_TOOL_CLASSES` dict gains an entry; Studio sidebar adds `edit_file` under Filesystem.
- No DB schema changes. No migrations. No new env vars. No new ports.

## Acceptance Criteria

- [ ] `EditFileTool(Tool)` declares `name = "edit_file"`, a clear `description` (`"Edit a file by replacing exactly-once-matching text. The old_string must be unique in the file; if multiple matches, add surrounding context."`), `parameters` JSON schema with required `path: string`, `old_string: string`, `new_string: string`, and `Config = FilesystemConfig`.
- [ ] `execute` flow:
  1. Resolve `cfg = self._config`.
  2. Wrap body in two-clause try/except (ConstraintError → `[error] [constraint] {e}`; other → `[error] {e}`).
  3. Validate `old_string != new_string` → `ConstraintError("old_string and new_string are identical; no change to apply")`.
  4. `canonical = _filesystem_check(path, cfg)`.
  5. `_check_read_size(canonical, cfg)`.
  6. If `_is_binary(canonical) and not cfg.allow_binary_files` → `ConstraintError("binary file refused (operator can permit via allow_binary_files)")`.
  7. `text = canonical.read_text(errors="replace")`.
  8. Count matches: `n = text.count(old_string)`.
     - `n == 0` → `ConstraintError(f"old_string not found in '{canonical}'")`.
     - `n > 1` → `ConstraintError(f"old_string matched {n} times in '{canonical}'; add surrounding context to make the match unique")`.
  9. Apply: `new_text = text.replace(old_string, new_string, 1)`.
  10. Write back: `canonical.write_text(new_text)`.
  11. Build the line-numbered preview via `_format_edit_preview` and return it.
- [ ] `_format_edit_preview(canonical: Path, old_text: str, old_string: str, new_string: str) -> str` — module-level function alongside the other helpers (consistent with `_filesystem_check`, `_check_read_size`, `_is_binary`). Behavior:
  - Splits both `old_text` and `new_text` (after replacement) via `splitlines()` (no `keepends`).
  - Locates the line index where `old_string` begins in `old_text` (use `old_text.index(old_string)` then count newlines before that index → 1-indexed start line).
  - Computes the lines spanned by `old_string` and `new_string` using **`splitlines()` length**, NOT `count("\n") + 1`. The latter overcounts when the string ends in `\n` (the trailing newline closes the last covered line; there is no partial line after it). Example: `"b\nc\n".count("\n") + 1 == 3` (wrong), but `"b\nc\n".splitlines() == ["b", "c"]` (length 2, correct). Add a sentinel: if `old_string == ""` (degenerate input), `splitlines()` returns `[]`; the tool's `count == 0 → not found` branch already handles this, but `_format_edit_preview` should never be called for an empty `old_string` because that would imply zero matches, which is a constraint error before the preview is built.
  - Renders the preview:
    - Header: `f"Edited {canonical}\n@@ around line {line_no} @@"`.
    - 3 lines of context BEFORE the change (from `old_text` lines).
    - The OLD lines marked with `- {line_no:>5} | {line}`.
    - The NEW lines marked with `+ {line_no:>5} | {line}` (line numbers re-counted from the NEW text — the new offset).
    - 3 lines of context AFTER the change (from `new_text` lines, since context after may shift if new_string adds/removes lines).
- [ ] `_TOOL_CLASSES` in `the_one/tools/builtins.py` has `"edit_file": EditFileTool` between `"write_file"` and `"list_dir"` (alphabetical ordering by tool name is NOT enforced; insertion order matches declaration). The import line `from the_one.tools.filesystem import ListDirTool, ReadFileTool, WriteFileTool` is extended to include `EditFileTool`.
- [ ] Studio's `TOOL_CATEGORIES` (in `the_one/interfaces/web/static/js/areas/studio.js`, line ~152) gains `'edit_file'` in the `'Filesystem'` array.
- [ ] `tests/test_filesystem_tools.py::TestEditFileTool` has at minimum:
  - `test_happy_single_match` — file contains `old_string` exactly once; edit succeeds; preview includes file path, line number, `-` and `+` markers; file content matches `new_text`.
  - `test_multi_match_returns_constraint_error` — file contains `old_string` 3 times; tool returns `[error] [constraint] ...matched 3 times...`.
  - `test_no_match_returns_constraint_error` — `old_string` not in file; tool returns `[error] [constraint] ...not found...`.
  - `test_identical_strings_returns_constraint_error` — `old_string == new_string`; returns `[error] [constraint] ...no change to apply`.
  - `test_binary_refused_default` — file with null byte; `allow_binary_files=False`; returns binary-refusal constraint.
  - `test_size_cap_exceeded_returns_constraint` — file > cap; returns size-exceeded constraint.
  - `test_path_outside_allowlist_raises_constraint` — out-of-scope path; returns outside-allowlist constraint.
  - `test_tilde_expansion` — `monkeypatch.setenv("HOME", str(tmp_path))` + cfg allowlist=tmp_path; edit via `~/foo.txt`.
  - `test_preview_contains_diff_markers` — happy edit; assert `-` and `+` markers in result; assert line numbers visible.
  - `test_old_string_spans_multiple_lines` — `old_string = "alpha\nbeta"` matches uniquely; edit replaces both lines; preview shows the multi-line region.
- [ ] `tests/test_filesystem_tools.py::TestFilesystemToolInstantiation::test_each_tool_has_filesystem_config` is updated to also check `EditFileTool`.
- [ ] `tests/test_builtins.py` test count assertions are updated to 8 tools (3 hardcoded `7` literals confirmed: at lines 49, 56, and 93; plus the expected names set at lines 58–66 must include `"edit_file"`).
- [ ] `make test-unit` passes (target: post-L3 baseline 593 + ~14 new tests = ~607 passed, modulo pre-existing CSS-token red). The 14 = 10 base + 4 edge-case regression tests (`test_old_string_ending_in_newline_no_overcount`, `test_new_string_empty_deletion`, `test_edit_at_first_line`, `test_edit_at_last_line`).
- [ ] `ruff check` and `ruff format --check` clean on changed files.

## Verification Steps

Static (after edit, before test run):

```bash
cd ~/projects/the-one

# EditFileTool defined
rg -n "^class EditFileTool\b" the_one/tools/filesystem.py
# Expected: 1

# _format_edit_preview helper defined
rg -n "^def _format_edit_preview\b" the_one/tools/filesystem.py
# Expected: 1

# Registered in _TOOL_CLASSES
rg -n '"edit_file":\s*EditFileTool' the_one/tools/builtins.py
# Expected: 1

# Imported in builtins
rg -n "EditFileTool" the_one/tools/builtins.py
# Expected: 2 (import + dict entry)

# Studio TOOL_CATEGORIES
rg -n "'edit_file'" the_one/interfaces/web/static/js/areas/studio.js
# Expected: 1

# Test class exists with full coverage
rg -n "class TestEditFileTool\b" tests/test_filesystem_tools.py
# Expected: 1
```

Dynamic:

```bash
docker exec the-one pytest tests/test_filesystem_tools.py -v
# Expected: ~30 tests (20 from L3 + ~10 new TestEditFileTool tests), all pass

docker exec the-one pytest tests/test_filesystem_helpers.py tests/test_filesystem_config.py tests/test_resolver.py -v
# Expected: 32 + 18 + 39 = 89 unchanged

docker exec the-one pytest tests/test_builtins.py -v
# Expected: pass (any tool-count assertion updated to 8)

make test-unit
# Expected: ~603 passed; only the pre-existing CSS-token red

# End-to-end smoke
docker exec the-one python -c "
import asyncio, tempfile, os
from pathlib import Path
from the_one.tools.filesystem import EditFileTool, FilesystemConfig
async def main():
    with tempfile.TemporaryDirectory() as d:
        target = Path(d) / 'doc.txt'
        target.write_text('alpha\nbeta\ngamma\n')
        cfg = FilesystemConfig(path_allowlist=[d], path_denylist=[])
        out = await EditFileTool(cfg).execute(
            path=str(target),
            old_string='beta',
            new_string='BETA',
        )
        assert 'Edited' in out
        assert 'beta' in out and 'BETA' in out
        assert target.read_text() == 'alpha\nBETA\ngamma\n'
        print('OK')
asyncio.run(main())
"
```

Quality:

```bash
docker exec the-one ruff check the_one/tools/filesystem.py the_one/tools/builtins.py tests/test_filesystem_tools.py
docker exec the-one ruff format --check the_one/tools/filesystem.py the_one/tools/builtins.py tests/test_filesystem_tools.py
```

## Implementation Guidance

### Step 1: Add `EditFileTool` after `ListDirTool` in `the_one/tools/filesystem.py`

```python
class EditFileTool(Tool):
    name = "edit_file"
    description = (
        "Edit a file by replacing exactly-once-matching text. The old_string "
        "must be unique in the file; if it matches multiple times, add "
        "surrounding context to make the match unique."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file."},
            "old_string": {
                "type": "string",
                "description": "Text to replace; must appear exactly once.",
            },
            "new_string": {
                "type": "string",
                "description": "Replacement text.",
            },
        },
        "required": ["path", "old_string", "new_string"],
    }
    Config = FilesystemConfig

    async def execute(
        self,
        path: str,
        old_string: str,
        new_string: str,
        **kwargs: Any,
    ) -> str:
        cfg: FilesystemConfig = self._config
        try:
            if old_string == new_string:
                raise ConstraintError(
                    "old_string and new_string are identical; no change to apply"
                )
            canonical = _filesystem_check(path, cfg)
            _check_read_size(canonical, cfg)
            if _is_binary(canonical) and not cfg.allow_binary_files:
                raise ConstraintError(
                    "binary file refused (operator can permit via allow_binary_files)"
                )
            text = canonical.read_text(errors="replace")
            n = text.count(old_string)
            if n == 0:
                raise ConstraintError(f"old_string not found in '{canonical}'")
            if n > 1:
                raise ConstraintError(
                    f"old_string matched {n} times in '{canonical}'; "
                    "add surrounding context to make the match unique"
                )
            new_text = text.replace(old_string, new_string, 1)
            canonical.write_text(new_text)
            return _format_edit_preview(canonical, text, old_string, new_string)
        except ConstraintError as e:
            return f"[error] [constraint] {e}"
        except Exception as e:
            return f"[error] {e}"
```

### Step 2: Add `_format_edit_preview` helper

Insert as a module-level function near the other filesystem helpers (after `_is_binary`, before `ReadFileTool`):

```python
def _format_edit_preview(
    canonical: Path, old_text: str, old_string: str, new_string: str
) -> str:
    """Render a diff-style preview of an edit.

    Format:
        Edited /path/to/file.py
        @@ around line N @@
           N-3 |   context line
           N-2 |   context line
           N-1 |   context line
        -    N |   old line
        +    N |   new line
           N+1 |   context line
           N+2 |   context line
           N+3 |   context line

    Multi-line edits emit one `-` line per old line and one `+` line per
    new line. Line numbers in the `-` rows count from `old_text`; line
    numbers in the `+` rows count from the new text (so post-edit line
    numbers show what the file now looks like)."""
    CONTEXT = 3

    # Find the start line of the edit (1-indexed).
    edit_offset = old_text.index(old_string)
    start_line = old_text[:edit_offset].count("\n") + 1

    old_lines = old_text.splitlines()
    new_text = old_text.replace(old_string, new_string, 1)
    new_lines = new_text.splitlines()

    # How many lines does old_string span? new_string?
    # Use splitlines() length, NOT count("\n") + 1. The latter overcounts
    # when the string ends in `\n` (the trailing newline closes the last
    # line; no partial line follows). `"b\nc\n".splitlines() == ["b","c"]`
    # (length 2 = the actual span) vs `count + 1 == 3` (wrong).
    # old_span is always >= 1 because empty old_string would have been
    # rejected by the count==0 check upstream.
    old_span = len(old_string.splitlines())
    # new_span CAN be 0 when new_string is empty (deletion case). That
    # produces `new_block = new_lines[start_line-1:start_line-1] = []`,
    # so zero `+` rows are emitted — exactly the deletion preview.
    new_span = len(new_string.splitlines())

    # Build the segments. start_line is 1-indexed; old_lines is 0-indexed.
    pre_start = max(0, start_line - 1 - CONTEXT)
    pre_end = start_line - 1
    pre_lines = old_lines[pre_start:pre_end]

    old_block = old_lines[start_line - 1 : start_line - 1 + old_span]
    new_block = new_lines[start_line - 1 : start_line - 1 + new_span]

    post_start_in_new = start_line - 1 + new_span
    post_lines = new_lines[post_start_in_new : post_start_in_new + CONTEXT]

    out = [f"Edited {canonical}", f"@@ around line {start_line} @@"]
    for i, line in enumerate(pre_lines):
        out.append(f"  {pre_start + i + 1:>5} | {line}")
    for i, line in enumerate(old_block):
        out.append(f"- {start_line + i:>5} | {line}")
    for i, line in enumerate(new_block):
        out.append(f"+ {start_line + i:>5} | {line}")
    for i, line in enumerate(post_lines):
        out.append(f"  {start_line + new_span + i:>5} | {line}")
    return "\n".join(out)
```

Notes:
- `splitlines()` (no `keepends=True`) drops the trailing `\n` on each line. The preview displays content without trailing newlines, which is the standard diff-tool convention.
- Edge: if the file ends without a trailing newline AND the edit is at the last line, `new_lines[start_line - 1 + new_span:]` returns an empty list (no post-context). Acceptable.
- Edge: if `start_line == 1`, no pre-context is shown. Acceptable.

### Step 3: Register in `_TOOL_CLASSES`

Edit `the_one/tools/builtins.py`:

```python
from the_one.tools.filesystem import (
    EditFileTool,
    ListDirTool,
    ReadFileTool,
    WriteFileTool,
)

# ...

_TOOL_CLASSES: dict[str, type[Tool]] = {
    "shell": ShellTool,
    "read_file": ReadFileTool,
    "write_file": WriteFileTool,
    "edit_file": EditFileTool,
    "list_dir": ListDirTool,
    "python_exec": PythonExecTool,
    "http_request": HttpRequestTool,
    "web_search": WebSearchTool,
}
```

(`edit_file` slotted between `write_file` and `list_dir` for natural read→write→edit→list grouping.)

### Step 4: Update Studio's `TOOL_CATEGORIES`

In `the_one/interfaces/web/static/js/areas/studio.js` line ~152:

```javascript
var TOOL_CATEGORIES = {
  'Filesystem': ['read_file', 'write_file', 'edit_file', 'list_dir'],
  'Execution': ['shell', 'python_exec'],
  'Web': ['http_request', 'web_search']
};
```

### Step 5: Add tests

In `tests/test_filesystem_tools.py`, extend the import:

```python
from the_one.tools.filesystem import (
    EditFileTool,
    FilesystemConfig,
    ListDirTool,
    ReadFileTool,
    WriteFileTool,
)
```

Add `class TestEditFileTool` (after the existing tool test classes, before `TestFilesystemToolInstantiation`):

```python
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

    async def test_multi_match_returns_constraint_error(
        self, tmp_path: Path
    ) -> None:
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

    async def test_no_match_returns_constraint_error(
        self, tmp_path: Path
    ) -> None:
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

    async def test_identical_strings_returns_constraint_error(
        self, tmp_path: Path
    ) -> None:
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

    async def test_size_cap_exceeded_returns_constraint(
        self, tmp_path: Path
    ) -> None:
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

    async def test_path_outside_allowlist_raises_constraint(
        self, tmp_path: Path
    ) -> None:
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        result = await EditFileTool(cfg).execute(
            path="/etc/hostname",
            old_string="x",
            new_string="y",
        )
        assert result.startswith("[error] [constraint]")
        assert "outside allowlist" in result

    async def test_tilde_expansion(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
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

    async def test_old_string_ending_in_newline_no_overcount(
        self, tmp_path: Path
    ) -> None:
        """Regression: span computation must use splitlines() length, not
        count('\\n') + 1. A trailing newline on old_string closes the last
        covered line; there is no partial line after it."""
        cfg = FilesystemConfig(path_allowlist=[str(tmp_path)], path_denylist=[])
        target = tmp_path / "x.txt"
        target.write_text("a\nb\nc\nd\n")
        result = await EditFileTool(cfg).execute(
            path=str(target),
            old_string="b\nc\n",   # trailing \n
            new_string="X\n",       # trailing \n
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
```

Update the instantiation test:

```python
class TestFilesystemToolInstantiation:
    def test_each_tool_has_filesystem_config(self) -> None:
        for cls in (ReadFileTool, WriteFileTool, EditFileTool, ListDirTool):
            t1 = cls()
            assert isinstance(t1._config, FilesystemConfig)
            t2 = cls(FilesystemConfig(path_allowlist=["/tmp"]))
            assert t2._config.path_allowlist == ["/tmp"]
```

### Step 6: Update `tests/test_builtins.py` for tool count

There are three hardcoded `7` literals (at lines 49, 56, and 93) plus an expected-names set (lines 58–66). Update all four to include `edit_file`:

```bash
rg -n "len\(.*tools\)" tests/test_builtins.py
# Expected: 3 matches; each must change to == 8
```

For the names set: add `"edit_file"` between `"write_file"` and `"list_dir"` (matching the `_TOOL_CLASSES` insertion order). The expected names set should be `{"shell", "read_file", "write_file", "edit_file", "list_dir", "python_exec", "http_request", "web_search"}`.

### Step 7: Run lint + tests; iterate

```bash
docker exec the-one ruff check the_one/tools/filesystem.py the_one/tools/builtins.py tests/test_filesystem_tools.py
docker exec the-one ruff format the_one/tools/filesystem.py the_one/tools/builtins.py tests/test_filesystem_tools.py
docker exec the-one pytest tests/test_filesystem_tools.py tests/test_filesystem_helpers.py tests/test_filesystem_config.py tests/test_resolver.py tests/test_builtins.py -v
make test-unit
```

### Step 8: Update flight log + leg status

- Append `### Leg 04 — Add edit_file tool` entry under "Leg Progress" in `flight-log.md`.
- Set leg `Status` to `landed`.
- Do NOT commit. Do NOT signal `[COMPLETE:leg]`. Signal `[HANDOFF:review-needed]`.

## Edge Cases

- **`old_string` at end of file without trailing newline**: `splitlines()` drops the absence of a trailing newline; the preview still works (no post-context shown). Tested implicitly by `test_old_string_spans_multiple_lines` (file ends with `\n`); for a file ending `delta` (no `\n`), the post-context is empty — acceptable.
- **`new_string` empty (deletion)**: `n = text.count(old_string)` still works; replacement returns the text minus `old_string`. Preview shows `-` rows for the old block and zero `+` rows because `new_span = 0`. Tested in `test_new_string_empty_deletion`.
- **Partial-line edits show whole containing lines in `-`/`+` rows**: when `old_string` starts or ends mid-line (e.g., `old_string="lo\nworld"` matching `"hello\nworld"`), the preview's `-` rows show the WHOLE first/last line (`hello`, not just `lo`), and the `+` rows likewise show whole new lines. This is intentional — the preview is for the agent's mental model of the surrounding region, not a precise byte-level diff. Documented as the L4 contract.
- **`old_string` at line boundary with newline**: `old_string = "alpha\n"` would match `"alpha\n"` cleanly; the multi-line span counter handles this. Not explicitly tested but covered by the multi-line test.
- **Very long lines (>10000 chars)**: the preview shows them as-is; no wrapping. Acceptable — agents render long lines fine.
- **File modification race**: if another process modifies the file between read and write, the agent's edit may be against stale content. TOCTOU residual; documented in Decision 10. Not in scope for L4.
- **Write-side scope check**: The write happens to the SAME canonical path that passed the read-side `_filesystem_check`, so no separate write-scope check is needed. (Edge case: if the agent's write would CREATE a parent dir, that's not happening here — edit is read-then-write of an existing file.)
- **`text.count(old_string)` on Unicode boundary**: `count` uses Python's str matching, which respects Unicode codepoint boundaries. An agent passing a partial codepoint would never match. Acceptable.
- **Preview line numbers and big files**: the `:>5` format pads to 5 digits; files with >99,999 lines show line numbers wider. The format still works; just less aligned. Acceptable for the foreseeable file-size range under the 1MB cap.
- **Pre-/post-context bleeding past file bounds**: `new_lines[start_line - 1 + new_span : start_line - 1 + new_span + CONTEXT]` returns whatever exists; out-of-range slicing returns an empty list (Python's slice semantic). Acceptable.

## Files Affected

- `the_one/tools/filesystem.py` — add `EditFileTool` class (~50 LoC), `_format_edit_preview` helper (~30 LoC). Net ~80 LoC.
- `the_one/tools/builtins.py` — extend import line, add 1 dict entry. Net ~3 changed LoC.
- `the_one/interfaces/web/static/js/areas/studio.js` — 1-line change to `TOOL_CATEGORIES`.
- `tests/test_filesystem_tools.py` — add `TestEditFileTool` class with ~10 tests (~150 LoC), update `test_each_tool_has_filesystem_config` to include `EditFileTool`. Update import line.
- `tests/test_builtins.py` — possibly update tool-count assertions if any exist.

Total: ~250 LoC across 5 files.

**Out of scope for L4**:

- `delete_file`, `move_file`, `mkdir` → L5.
- `glob`, `grep` → L6.
- HAT walkthrough → L7.
- Documentation refresh in agents.md / CLAUDE.md → L8.

---

## Post-Completion Checklist

- [ ] All acceptance criteria verified
- [ ] Tests passing (`pytest tests/test_filesystem_tools.py tests/test_filesystem_helpers.py tests/test_filesystem_config.py tests/test_resolver.py tests/test_builtins.py -v`; `make test-unit` ≥ post-L3 baseline + ~10 new tests)
- [ ] `ruff check` and `ruff format --check` clean on changed files
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed`
- [ ] DO NOT check off this leg in `flight.md` (deferred to final commit)
- [ ] DO NOT commit; DO NOT signal `[COMPLETE:leg]`
- [ ] Signal `[HANDOFF:review-needed]`
