# Squawk 0063: `GET …/items/{item_id}/source` reads the file whole with no size cap

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-16
**Completed**: 2026-09-16

## Report

`get_kb_item_source` (`the_one/interfaces/web/api.py`) stats the file, then
calls `extractor.extract(path)` unconditionally and returns the whole text.
Its docstring — and Flight 3 DD-8 — say "no separate read-back cap — the
file size cap is the cap", but the route never checks `MAX_FILE_BYTES`
(the constant is not imported in `api.py`). A file the indexer refused at
10 MiB, or any larger standalone `file` item, is read into memory and
returned on request. Found at the Flight 3 debrief; the behavior test
checked the over-cap fixture's `failed` status but never called `/source`
on it.

Fix: before extracting, refuse `st.st_size > MAX_FILE_BYTES` with **413**
and a detail naming the cap; correct the docstring; add the negative test
(a `file` item pointing at an 11 MiB fixture → 413). Consider adding the
same call to the behavior spec's Step 5 at its next re-author.

## Evidence

- `the_one/interfaces/web/api.py::get_kb_item_source` (def at `:1753`) — docstring "the file size cap is the cap"; `st = await asyncio.to_thread(path.stat)` then `text = await asyncio.to_thread(extractor.extract, path)` with no size comparison between them
- `grep -c MAX_FILE_BYTES the_one/interfaces/web/api.py` → 0
- `the_one/knowledge/indexer.py:47` — `MAX_FILE_BYTES = 10 * 1024 * 1024`
- Flight 3 debrief, "Technical — Important"

## Corrective Action

`the_one/interfaces/web/api.py::get_kb_item_source` now imports
`MAX_FILE_BYTES` from `the_one.knowledge.indexer` and, immediately after
the existing `stat` call and before the extractor runs, refuses
`st.st_size > MAX_FILE_BYTES` with `HTTPException(413, detail=...)`
naming the cap and the file's actual size (e.g. "file exceeds the 10 MiB
read-back cap (10485761 bytes)"). This closes the gap directly: the route
now enforces the same cap the indexer does, independently, rather than
merely relying on (or claiming to rely on) the indexer having already
rejected an over-cap file. The docstring's inaccurate "no separate
read-back cap — the file size cap is the cap" claim is corrected to state
the route enforces `MAX_FILE_BYTES` itself with a 413. `the_one/agents.md`'s
DD-8 route-wiring paragraph gained one clause noting the same. (`CLAUDE.md`'s
`/source` description doesn't make any cap claim, so it needed no change.)

## Verification

Added `TestKnowledgeBaseSourceRoute::test_over_cap_file_413` (a sparse
file truncated to `MAX_FILE_BYTES + 1` via `f.truncate(...)` — avoids
actually writing 10 MiB since only `stat().st_size` is exercised before
extraction — asserts 413 with "10 MiB" and the byte count in `detail`)
and `test_small_file_under_cap_200` (a small file still returns 200 with
its extracted text) to `tests/test_db_api.py`. Existing `/source` tests
unchanged and still pass.

Ran:
```
PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_db_api.py -x --timeout 60 -q -k "source or KnowledgeBase"
```
Result: `78 passed, 45 deselected in 36.14s`.

Ran `make lint` (`ruff check the_one/ tests/ scripts/`) → `All checks
passed!`; also confirmed `ruff format --check the_one/ tests/ scripts/`
→ `437 files already formatted` (CI's full lint-gate shape).

## Sign-Off
**Reviewer**: Sonnet (batch review, squawk turnaround 2026-09-16; Sonnet tier — 0063 touches the route reading operator-registered paths)
**Verdict**: confirmed
**Commit**: `16222c4`
