# Leg: 04-migrate-filesystem-tools

**Status**: completed
**Flight**: [Cross-Platform Foundations & Policy Resolver](../flight.md)

## Objective

Route the three existing filesystem tools (`ReadFileTool`, `WriteFileTool`, `ListDirTool`) through `the_one/platform/paths.canonicalize` instead of inline `Path(p).expanduser().resolve()`. No new Config fields, no new constraint values — pure scaffolding migration with regression tests proving behavior is byte-for-byte unchanged.

## Context

This is the first of three tool-migration legs (L4 filesystem, L5 execution, L6 web). Per the flight Technical Approach, each tool routes through the platform layer and inherits the empty `Tool.Config = _EmptyConfig` from L3's ABC change. F3 will introduce real path-scope constraints on top of this seam.

**The L3 Tool ABC change (`__init__(config)` plus `Config: type[BaseModel] = _EmptyConfig`) is already inherited by all 7 tools as of L3.** L4 does NOT need to add per-tool Config classes — the empty default applies. The migration is mechanical: swap `Path(path).expanduser().resolve()` for `canonicalize(path)` at three sites in `the_one/tools/filesystem.py`.

### v8 baseline (verified at L4 design time, post-L3)

- `the_one/tools/filesystem.py:27` — `ReadFileTool.execute`: `p = Path(path).expanduser().resolve()`
- `the_one/tools/filesystem.py:52` — `WriteFileTool.execute`: `p = Path(path).expanduser().resolve()`
- `the_one/tools/filesystem.py:74` — `ListDirTool.execute`: `p = Path(path).expanduser().resolve()`
- `the_one/platform/paths.py:32` — `canonicalize(path)` returns `Path(path).expanduser().resolve()` (byte-for-byte equivalent today)
- `tests/test_builtins.py` — only checks the 3 tools have `name`/`description`/`parameters` attributes; no execute-path tests
- `tests/test_aiat.py` — exercises tools via real LLM (live test, run with `pytest -m live`)
- **No dedicated unit tests for `ReadFileTool.execute` / `WriteFileTool.execute` / `ListDirTool.execute` exist today.** L4 adds them as regression coverage for the migration.

## Inputs

What exists before this leg runs:

- L1, L2, L3 landed: platform package, schema v8, resolver + Tool ABC + per-agent instantiation
- All 7 existing tools inherit `Tool.Config = _EmptyConfig` and `__init__(config=None)`
- `the_one.platform.canonicalize` is available
- Branch: `flight/02-cross-platform-foundations` (continuing from L3)

## Outputs

What exists after this leg completes:

- `the_one/tools/filesystem.py` — three `Path(p).expanduser().resolve()` sites replaced with `canonicalize(p)`; one new import `from the_one.platform import canonicalize`
- `tests/test_filesystem_tools.py` (new) — direct execute-path tests for all three tools, covering the happy path and a representative set of edge cases (path with `~`, relative path, missing file, binary content via byte-range)
- All previously passing tests continue passing (regression invariant)
- Flight log + leg + flight artifact updated

## Acceptance Criteria

- [ ] `the_one/tools/filesystem.py` imports `canonicalize` from `the_one.platform` (single import line at the top of the file alongside the existing `from pathlib import Path` import — `Path` may still be needed for the `read_text`/`write_text`/`mkdir` calls)
- [ ] `ReadFileTool.execute` (line 27): replace `p = Path(path).expanduser().resolve()` with `p = canonicalize(path)`. Keep all other behavior (offset/limit slicing, `errors="replace"` decode, formatted line-numbered output) unchanged.
- [ ] `WriteFileTool.execute` (line 52): replace `p = Path(path).expanduser().resolve()` with `p = canonicalize(path)`. Keep `p.parent.mkdir(parents=True, exist_ok=True)` and `p.write_text(content)` calls unchanged.
- [ ] `ListDirTool.execute` (line 74): replace `p = Path(path).expanduser().resolve()` with `p = canonicalize(path)`. Keep recursive vs non-recursive behavior, the 500-entry cap, and the prefix formatting unchanged.
- [ ] No other changes to `the_one/tools/filesystem.py` — verify by running the full file through a diff and confirming the only deltas are the 3 line replacements + 1 import line.
- [ ] **Test: `tests/test_filesystem_tools.py` (NEW)** — direct unit tests for all three tools, mirroring the test discipline established for the platform layer in L1:
  - `TestReadFileTool`:
    - Happy path: `ReadFileTool().execute(path=str(tmp_path / "f.txt"))` returns line-numbered content (5-char right-aligned width: `"    1 | content"`) for a small file written with known content
    - `~` expansion: write a file under `tmp_path`, **`monkeypatch.setenv("HOME", str(tmp_path))`** (NOT `monkeypatch.setattr(Path, "home", ...)` — `Path.expanduser` reads `os.environ["HOME"]` directly via `posixpath.expanduser`, never calls `Path.home`), read with path `"~/f.txt"` — verifies `canonicalize` does the expanduser
    - `offset`/`limit` slicing: write a 5-line file (`"a\nb\nc\nd\ne"`), read with `offset=1, limit=2` — returns lines 2-3 with line-number prefixes `"    2 | b"` and `"    3 | c"` (positive assertion); negate with `assert "1 | a" not in result` (NOT `assert " a" not in result.split("\n")[0]` which is fragile — tests the wrong substring)
    - Missing file: `execute(path="/nonexistent/file")` returns a string starting with `[error]` (not an exception)
  - `TestWriteFileTool`:
    - Happy path: writes file content, returns `"Wrote N bytes to /resolved/path"`; assert `"Wrote 2 bytes"` for `content="hi"` AND `f.read_text() == "hi"`
    - Creates parent directories: `execute(path=str(tmp_path / "new" / "deep" / "file.txt"), content="x")` succeeds; the intermediate dirs exist after
    - `~` expansion: `monkeypatch.setenv("HOME", str(tmp_path))` — verifies path is canonicalized before write
  - `TestListDirTool`:
    - Happy path: `execute(path=str(tmp_path))` for a dir with files `a.txt`, `b.txt` and subdir `c/`: returns lines starting with `f a.txt`, `f b.txt`, `d c` (sorted)
    - Recursive flag: with `recursive=True`, includes nested files
    - 500-entry cap: create a **fresh subdir of tmp_path** (`many = tmp_path / "many"; many.mkdir(); ...`) with 550 files; output ends with `"... and 50 more"`. The fresh subdir guarantees the 550 count is exact and isolates the test from any `tmp_path` evolution.
    - `~` expansion: `monkeypatch.setenv("HOME", str(tmp_path))`; verifies canonicalization
- [ ] **Tool ABC instantiation regression test** (extend `tests/test_builtins.py` or add to `test_filesystem_tools.py`): each filesystem tool can be instantiated with `cls()` (no args) AND `cls(_EmptyConfig())`; both work and produce a tool whose `_config` is an `_EmptyConfig` instance.
- [ ] All 7 existing tools' tests pass unchanged (no regressions). Notably:
  - `tests/test_builtins.py` — all 9 tests still pass (4 original + 5 added in L3)
  - `tests/test_factory.py` — unchanged behavior (filesystem tools still appear in the per-agent registry)
- [ ] Pre-existing test suite still green (modulo pre-existing CSS-token red): `make test-unit` returns the L3-tip pass/fail set plus the new L4 tests
- [ ] No source code modified outside `the_one/tools/filesystem.py` and `tests/`
- [ ] **AIAT live smoke remains green**: `pytest -m live tests/test_aiat.py` exercises `read_file`/`write_file`/`list_dir` through a real agent. Run as a final check before signaling [HANDOFF:review-needed]. (If AIAT requires API keys / Ollama running and is not available locally, document the skip and run only the unit suite.)

## Verification Steps

```bash
# Diff inspection: confirm only 3 line replacements + 1 import (host)
git diff -- the_one/tools/filesystem.py
# Expected: import line added at top, three lines changed inline

# Build container with new files
make rebuild

# Targeted tests
docker exec the-one pytest tests/test_filesystem_tools.py -v
docker exec the-one pytest tests/test_builtins.py tests/test_factory.py -v

# Full unit suite (pre-existing CSS red expected)
make test-unit

# Smoke: each tool instantiable both ways
docker exec the-one python -c "
from the_one.tools.filesystem import ReadFileTool, WriteFileTool, ListDirTool
from the_one.tools.resolver import _EmptyConfig

for cls in (ReadFileTool, WriteFileTool, ListDirTool):
    t1 = cls()
    t2 = cls(_EmptyConfig())
    assert isinstance(t1._config, _EmptyConfig)
    assert isinstance(t2._config, _EmptyConfig)
print('OK')
"

# Smoke: read+write roundtrip via canonicalize
docker exec the-one python -c "
import asyncio, tempfile, pathlib
from the_one.tools.filesystem import ReadFileTool, WriteFileTool

async def main():
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / 'sub' / 'file.txt'
        wr = await WriteFileTool().execute(path=str(p), content='hello\nworld')
        assert 'Wrote' in wr, wr
        rd = await ReadFileTool().execute(path=str(p))
        assert 'hello' in rd and 'world' in rd, rd
        rd2 = await ReadFileTool().execute(path=str(p), offset=1, limit=1)
        assert 'world' in rd2 and 'hello' not in rd2, rd2

asyncio.run(main())
print('OK')
"

# Live smoke (skip if no LLM available)
docker exec the-one pytest -m live tests/test_aiat.py -v || echo "AIAT skipped"
```

## Implementation Guidance

1. **Update `the_one/tools/filesystem.py`**

   At the top of the file, add the canonicalize import. Keep the `Path` import (still used for `read_text`/`write_text`/`iterdir`/`rglob`/`mkdir`/`is_dir`/`relative_to`):

   ```python
   from __future__ import annotations

   from pathlib import Path
   from typing import Any

   from the_one.platform import canonicalize
   from the_one.tools.base import Tool
   ```

2. **Replace the three call sites** — the only logic change. Each is a single-line swap:

   - `ReadFileTool.execute` line 27:
     ```python
     # before:
     p = Path(path).expanduser().resolve()
     # after:
     p = canonicalize(path)
     ```
   - `WriteFileTool.execute` line 52: same pattern.
   - `ListDirTool.execute` line 74: same pattern.

   No other behavior changes. The `read_text(errors="replace")`, `write_text(content)`, `mkdir(parents=True, exist_ok=True)`, `iterdir()`, `rglob("*")`, the 500-entry cap, the line-number formatting — all preserved exactly.

3. **Write `tests/test_filesystem_tools.py`**

   Use pytest-asyncio's `asyncio_mode = "auto"` (already configured per L1's anomaly fix) — write tests as `async def` rather than `asyncio.run(...)`. Use `tmp_path` (the standard pytest fixture) for filesystem-touching tests. **Use `monkeypatch.setenv("HOME", str(tmp_path))` for `~` expansion tests** — `Path.expanduser` reads `os.environ["HOME"]` directly (via `posixpath.expanduser`); patching `Path.home` does NOT affect `Path("~").expanduser()` and would silently leak the developer's real home into test paths.

   Skeleton:

   ```python
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
           assert "    1 | alpha" in result  # line-numbered

       async def test_offset_limit(self, tmp_path: Path) -> None:
           f = tmp_path / "x.txt"
           f.write_text("a\nb\nc\nd\ne")
           result = await ReadFileTool().execute(
               path=str(f), offset=1, limit=2
           )
           assert "    2 | b" in result and "    3 | c" in result
           assert "1 | a" not in result  # line 1 NOT included

       async def test_tilde_expansion(self, tmp_path: Path, monkeypatch) -> None:
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
           assert "Wrote 2 bytes" in result  # locks the byte-count contract
           assert str(f) in result  # canonicalized absolute path appears
           assert f.read_text() == "hi"

       async def test_creates_parent_dirs(self, tmp_path: Path) -> None:
           f = tmp_path / "deep" / "nested" / "file.txt"
           result = await WriteFileTool().execute(path=str(f), content="x")
           assert result.startswith("Wrote")
           assert f.read_text() == "x"

       async def test_tilde_expansion(self, tmp_path: Path, monkeypatch) -> None:
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

       async def test_tilde_expansion(self, tmp_path: Path, monkeypatch) -> None:
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
   ```

4. **Run targeted tests, then full suite**:
   ```bash
   make rebuild
   docker exec the-one pytest tests/test_filesystem_tools.py tests/test_builtins.py tests/test_factory.py -v
   make test-unit
   ```

5. **Run the AIAT smoke** (if local LLM is available — Ollama or mock provider):
   ```bash
   docker exec the-one pytest -m live tests/test_aiat.py -v
   ```
   If AIAT is unavailable in the dev environment, document this in the flight log and rely on the unit suite for L4 verification.

## Edge Cases

- **`~` expansion uses `os.environ["HOME"]`**: `Path("~").expanduser()` calls `posixpath.expanduser` which reads `os.environ["HOME"]` directly — it does NOT call `Path.home()`. Use `monkeypatch.setenv("HOME", str(tmp_path))` to drive the expansion in tests. Patching `Path.home` is a no-op for `expanduser` and silently leaks the developer's real home into test paths (false-pass mode). Document in test docstrings.
- **`canonicalize` of a non-existent path** (forward-reference from L1): succeeds without raising; the read_text / iterdir then fails with FileNotFoundError, which the existing `except Exception` clauses catch and return as `[error] {e}`. Behavior preserved.
- **Cache freshness contract** (per `/leg` skill section 6): no caches in filesystem tools. Each `execute()` call canonicalizes the path fresh from input. No staleness concern.
- **State-machine reachability** (per `/leg` skill section 5): no states added or modified by L4. The migration is internal; tool inputs/outputs are unchanged.
- **Test isolation**: `tmp_path` is per-test (pytest fixture). The 500-entry-cap test creates 550 files in tmp; pytest cleans up automatically. Test runtime should stay <2s on the 550-file case.
- **`test_500_entry_cap` boundary**: cap is exactly 500. With 550 files, output is 500 entries + `... and 50 more`. The assertion `"and 50 more" in result` exercises the boundary.
- **L3 test inheritance**: `tests/test_tool_base.py` (created in L3) verified Tool ABC instantiation generically. L4's `TestFilesystemToolInstantiation` adds tool-specific verification — small overlap, but documents intent for the migration.

## Files Affected

- `the_one/tools/filesystem.py` — 3 line replacements + 1 import line
- `tests/test_filesystem_tools.py` — created
- `missions/.../flight-log.md` — append L4 progress entry
- `missions/.../flight.md` — check off L4 in Legs section + check off "Filesystem tools migrated" checkpoint
- `missions/.../legs/04-migrate-filesystem-tools.md` — set status `landed`

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`** (per agentic-workflow batched-review pattern, Developer does NOT commit; review and commit happen once at flight end):

- [ ] All acceptance criteria verified
- [ ] New `test_filesystem_tools.py` tests passing
- [ ] Pre-existing unit suite still green (modulo pre-existing CSS-token red)
- [ ] AIAT smoke green (or skip-with-explanation in flight log if local LLM unavailable)
- [ ] Update flight-log.md with L4 progress entry
- [ ] Set this leg's status to `landed`
- [ ] Check off L4 in flight.md (legs section AND "Filesystem tools migrated" checkpoint)
- [ ] Do NOT commit — final commit happens once after L7
