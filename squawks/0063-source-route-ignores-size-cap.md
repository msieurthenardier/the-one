# Squawk 0063: `GET …/items/{item_id}/source` reads the file whole with no size cap

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-16
**Completed**: —

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
*(written at completion)*

## Verification
Unit: `tests/test_db_api.py` — a `file` item whose path is an 11 MiB text fixture → `GET …/source` 413 with the cap in `detail`; a 1 KiB file still 200. Existing `/source` tests unchanged.

## Sign-Off
*(written at completion)*
