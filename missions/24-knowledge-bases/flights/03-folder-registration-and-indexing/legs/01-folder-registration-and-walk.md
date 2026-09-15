# Leg: folder-registration-and-walk

**Status**: completed
**Flight**: [Folder Registration and Indexing](../flight.md)

## Objective

Land the tested surfaces Legs 2 and 3 build on and nothing that runs on its
own: the `KBItemRepository` / `KBChunkRepository` widening (folder deletion
cleans descendants' FTS rows and returns every descendant chunk id; bulk
create; children and folder listing; bulk requeues; paged and ids-only chunk
reads; keyset iteration), a pure filesystem walk with the DD-3 filter rules
and a pure reconcile planner in `the_one/knowledge/walk.py`, folder
registration validation on the existing item route (DD-1) behind a no-op
hook Leg 3 fills, and the `SECURITY-MODEL.md` paragraph.

## Context

- Flight DD-1 (registration route and validation order: existence → root →
  containment; `file`/`url` contracts unchanged; the `ValidationError → 422`
  handler; a standalone file inside a registered folder is accepted as a
  second item), DD-2 (`parent_id` reuse; the widened `delete`; every new
  repository method unit-tested in this leg because its first production
  consumer is Leg 3; no index on `parent_id`, recorded), DD-3 (`os.scandir`
  walk, dot-entries / `SKIPPED_DIRS` / symlinks / unsupported extensions
  skipped, stat-only — the size cap and binary sniff belong to Leg 2's
  indexer; `plan_reconcile` classifies only, the worker applies with the
  status rule in Leg 3).
- The walk does not know the extension allowlist: the extractor registry
  that owns it is Leg 2's. `walk_folder` takes `extensions` as a parameter,
  which is also what keeps it pure and testable against any set.
- Flight 2's contracts this leg must not break: `db-writes-hold-the-write-
  lock` (every commit inside one `write_transaction`, never nested);
  `_fts_delete_rows` is the only FTS delete site and needs `(id, text)`
  selected **before** the row delete; `KB_ITEM_TRANSITIONS` (`_kb_types.py`)
  is the only source of allowed status edges — a bulk `UPDATE` may apply an
  edge in bulk but must assert the edge exists in the table at call time.
- Nothing observable changes for an operator in this leg: registration of a
  folder succeeds and is validated, but no indexing runs until Leg 3 fills
  the hook.

## Inputs

- `mission/24-knowledge-bases` at `0f79f9c` merged into the flight branch;
  flight branch `flight/03-folder-registration-and-indexing` at `148f704`
  (planning artifacts only).
- `the_one/db/repositories.py::KBItemRepository` (`list`, `get`, `create`,
  `delete`, `update_status`, `set_content_identity`, `list_by_status`,
  `count_by_status`), `::KBChunkRepository` (`replace_item_chunks`,
  `delete_for_item`, `delete_for_kb`, `list_for_item`, `get_many`,
  `count_for_kb`, `search_keyword`, `rebuild_fts`, `check_fts`), and the
  module-level `_fts_delete_rows(conn, rows)` at `repositories.py:375`.
- `the_one/db/_kb_types.py::KB_ITEM_TRANSITIONS` —
  `{"indexing": {"pending"}, "indexed": {"indexing"}, "failed": {"indexing"},
  "pending": {"indexing", "failed", "indexed"}}`.
- `the_one/interfaces/web/api.py::create_kb_item` (`:1487-1501`): KB
  existence check → `request.json()` → `KBItem.model_validate(data)` with no
  `ValidationError` handler → `repo.create(item)` → `item.model_dump()`.
- `the_one/platform/paths.py::canonicalize` (`:29`, `expanduser().resolve()`,
  succeeds for a non-existent path) and `::is_within` (`:54`, equals-or-
  descendant, canonicalises both inputs).
- `the_one/tools/filesystem.py::_is_binary` (`:274`) — the rule Leg 2
  re-implements; **not** used by this leg.
- Test fixtures: `tests/test_db_repositories.py` `conn` (`:28`, per-test
  `aiosqlite` DB with `ensure_schema`), `kb_repo` (`:69`), `kb_item_repo`
  (`:74`), `kb_chunk_repo`; `tests/test_kb_chunks.py` `conn`/`kb_repo`/
  `kb_item_repo`/`chunk_repo` (`:39-67`); `tests/test_db_api.py` `client`
  (`:20`, `AsyncClient` with the credential attached) and the
  `TestKnowledgeBaseAPI` class (`:542`) whose item tests (`:600-760`) are the
  shape to follow; `TestKnowledgeBaseDeleteCallsVectorStore` (`:800`) with
  its recording-stub store for the delete-route test.
- `SECURITY-MODEL.md` "Tool Execution Boundary" (`:489`), a bullet list whose
  last entry is the M24 F2 L06 "No native SQLite extension" paragraph
  (`:573-582`).

## Outputs

- `the_one/db/repositories.py`: `KBItemRepository.delete` widened;
  `create_many`, `list_children`, `list_folders`, `requeue_stranded`,
  `requeue_for_reindex` added; `list_by_status` and `count_by_status` gain
  keyword filters. `KBChunkRepository.list_for_item` gains `limit`/`offset`;
  `ids_for_item` and `iter_for_kb` added.
- `the_one/knowledge/walk.py` (new): `SKIPPED_DIRS`, `DiscoveredFile`,
  `walk_folder`, `ReconcilePlan`, `plan_reconcile`, `content_hash`,
  `is_filesystem_root`.
- `the_one/interfaces/web/api.py`: `create_kb_item` folder validation and
  the `_after_folder_registered(kb_id)` no-op hook; `ValidationError → 422`.
- `SECURITY-MODEL.md`: "Knowledge-base indexing (M24 F3)" bullet.
- Tests: new `tests/test_kb_walk.py`; additions to
  `tests/test_db_repositories.py`, `tests/test_kb_chunks.py`,
  `tests/test_db_api.py`.
- Flight log: leg entry with the test-count delta and `make test-unit`
  figures.

## Acceptance Criteria

- [x] **AC-1 — Folder delete cleans descendants.** `KBItemRepository.delete(folder_id)` where the folder has two child `file` items (`parent_id = folder_id`) each with chunks: returns every chunk id of both children (and the folder's own, if any), leaves zero `kb_chunks` rows for the three items, zero `kb_chunks_fts` rows for their text (a `MATCH` on a planted rare token returns 0), and `check_fts()` is `True`. All inside the method's single existing `write_transaction`; `_fts_delete_rows` remains the only FTS delete site (grep count of `VALUES ('delete'` in `repositories.py` is unchanged: 1). Deleting a child `file` directly is unchanged in behaviour (existing tests pass untouched).
- [x] **AC-2 — Bulk create.** `KBItemRepository.create_many(items)` inserts N items in one `write_transaction` (`executemany`, all 13 columns as `create` does); an empty sequence is a no-op; a duplicate id inside the batch raises `sqlite3.IntegrityError` and inserts none of the batch (rolled back by the guard). A test proves the single-transaction property by counting commits via a `write_transaction`-level spy or by asserting the partial-batch rollback.
- [x] **AC-3 — Listings.** `list_children(folder_item_id)` returns the items whose `parent_id` equals it, oldest first, and `[]` for an unknown id; `list_folders(kb_id)` returns the KB's `folder` items oldest first. `list_by_status(kb_id, status, *, limit=None, type=None)` and `count_by_status(kb_id, *, type=None)` filter by `type` when given and are byte-for-byte the old behaviour when not (existing tests untouched); `limit` caps the page.
- [x] **AC-4 — Bulk requeues.** `requeue_stranded(kb_id=None) -> int` moves every `indexing` item of every type to `pending` (scoped to one KB when `kb_id` is given), clears `error`, stamps `updated_at`, returns the row count, and asserts at call time that `"indexing" in KB_ITEM_TRANSITIONS["pending"]`. `requeue_for_reindex(kb_id) -> int` moves `indexed` and `failed` **`file`** items of that KB to `pending`, leaves `indexing` items, `folder` items and other KBs untouched, clears `error`, returns the count, and asserts both edges. Both are one conditional `UPDATE` inside one `write_transaction`.
- [x] **AC-5 — Chunk reads.** `list_for_item(item_id, *, limit=None, offset=0)` pages in `seq` order and is unchanged when called positionally; `ids_for_item(item_id) -> list[int]` returns the ids in `seq` order and never selects `text` (the SQL is `SELECT id FROM kb_chunks …`); `iter_for_kb(kb_id, batch_size=1000)` is an async iterator yielding `list[KBChunk]` pages in ascending `id` order by keyset (`WHERE kb_id = ? AND id > ? ORDER BY id LIMIT ?`), covering chunks of several items, yielding nothing for an empty KB, and never holding a transaction between pages.
- [x] **AC-6 — Walk filter rules.** `walk_folder(root, *, extensions)` on a fixture tree yields exactly the regular files whose lower-cased suffix is in `extensions`, and none of: files or directories whose name starts with `.`; anything under a directory named in `SKIPPED_DIRS` (`node_modules`, `__pycache__`, `venv`, `site-packages`); symlinked files; anything under a symlinked directory (not descended); files with an unsupported suffix; names that cannot be encoded as UTF-8. Every yielded `DiscoveredFile.path` is an absolute string under `root` (`os.path.commonpath` check in the test) carrying `size_bytes` and `mtime` from `entry.stat(follow_symlinks=False)`. The walk is iterative (a 200-deep nested fixture walks without recursion error) and opens no file (a test patches `builtins.open` / `io.open` to raise and the walk still succeeds).
- [x] **AC-7 — Walk error surface.** A root that does not exist or is not a directory raises `NotADirectoryError`/`FileNotFoundError` from `walk_folder`; an unreadable *sub*directory (`PermissionError` from `scandir`) is skipped and counted, not raised; a file that vanishes between `scandir` and `stat` is skipped. The walk returns its counts alongside the files — `WalkResult(files, skipped_dirs, skipped_entries)` — so Leg 3 can log them. **Counter semantics**: `skipped_dirs` counts directories pruned for a *condition* (symlinked, unreadable, non-UTF-8 name, or in `SKIPPED_DIRS`); `skipped_entries` counts files skipped for a condition (symlinked, non-UTF-8 name, vanished or unstat-able). Dot-prefixed names and unsupported suffixes are by-design filters and are **not** counted.
- [x] **AC-8 — Reconcile planner.** `plan_reconcile(discovered, existing) -> ReconcilePlan` is pure: `new` = discovered paths with no existing item; `removed` = existing items whose path is not discovered; `changed` = pairs where the item has a non-`None` `content_hash` and either `size_bytes` or `mtime` differs from the stat; everything else counted in `unchanged` (including items with no identity yet — they are `pending` and will be indexed anyway). Keyed on the exact path string. Tested against all four combinations plus the no-identity case; it never touches the database and never reads a file.
- [x] **AC-9 — `content_hash(path) -> str`** returns the lower-case hex sha256 of the file's bytes, streamed in 1 MiB blocks (a 3 MiB fixture hashes to the same value `hashlib.sha256(path.read_bytes()).hexdigest()` gives). **`is_filesystem_root(path) -> bool`** is true for `/` (and would be for `C:\`: `path.parent == path`).
- [x] **AC-10 — Folder registration.** `POST /api/knowledge-bases/{kb_id}/items` with `type: "folder"`: an existing directory → 201, the stored and returned `path_or_url` is the canonical absolute path (a `~`-prefixed or relative or symlinked input is resolved); a non-existent path → 422; an existing *file* path → 422; a filesystem root → 422; a path equal to, inside, or containing an existing `folder` item **of the same KB** → 409 with the conflicting item id in `detail`; the same folder registered in a *different* KB → 201. The checks run in that order (existence, root, containment) so a non-existent path under a registered folder is 422. The existence/`is_dir` check runs under `asyncio.to_thread`. `type: "file"` and `type: "url"` bodies behave exactly as before (existing tests untouched). Any body that fails `KBItem.model_validate` → 422 with `e.errors(include_context=False)` (was an unhandled 500). After a successful folder create the route calls `_after_folder_registered(kb_id)`, a module-level no-op whose docstring says Leg 3 replaces its body with `IndexingManager.request_index`; a test asserts it is called once with the KB id (monkeypatch).
- [x] **AC-11 — Folder delete route.** `DELETE …/items/{folder_id}` hands every descendant chunk id to `store.delete(kb_id, ids)` (extend the recording-stub pattern of `test_delete_kb_item_calls_delete_with_the_chunk_ids`).
- [x] **AC-12 — Security model.** `SECURITY-MODEL.md` "Tool Execution Boundary" gains a "Knowledge-base indexing (M24 F3)" bullet after the "No native SQLite extension" one: registration is operator-only through the API (no agent-facing route creates items; Flight 5's tools are read-only search), the app reads registered folders with its own privileges and no allowlist applies, dot-entries and the `SKIPPED_DIRS` set are skipped by construction, and extracted chunk text is stored in plaintext in the SQLite database under the existing single-user local-only model.
- [x] **AC-13 — Gates.** `ruff check the_one/ tests/ scripts/` and `ruff format --check the_one/ tests/ scripts/` clean; `make test-unit` green with the test-count delta recorded in the flight log; no test file outside this leg's list changes.

## Verification Steps

- AC-1–AC-5: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_db_repositories.py tests/test_kb_chunks.py -x --timeout 60 -q`; `grep -c "VALUES ('delete'" the_one/db/repositories.py` → `1`.
- AC-6–AC-9: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_kb_walk.py -x --timeout 60 -q`.
- AC-10–AC-11: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_db_api.py -x --timeout 60 -q -k "KnowledgeBase"`.
- AC-12: read the bullet; `grep -n "Knowledge-base indexing (M24 F3)" SECURITY-MODEL.md`.
- AC-13: `make lint`; `make test-unit` (run once, alone, foreground; record passed/skipped/wall time).

## Implementation Guidance

1. **Repository widening first** (`the_one/db/repositories.py`).
   - `delete`: change the select to
     `SELECT id, text FROM kb_chunks WHERE item_id = ? OR item_id IN (SELECT id FROM kb_items WHERE parent_id = ?)`
     with `(item_id, item_id)`; the rest of the method is unchanged — the
     FK cascade (`kb_items.parent_id … ON DELETE CASCADE`, then `kb_chunks.
     item_id … ON DELETE CASCADE`) removes children and their chunks after
     the FTS rows are already gone. Update the docstring to say so.
   - `create_many`: `executemany` with the same 13-column statement as
     `create`, inside one `write_transaction`; return `None`.
   - `list_children`, `list_folders`: plain selects, `ORDER BY created_at`.
   - `list_by_status(kb_id, status, *, limit=None, type=None)`: build the
     SQL from the base statement, append `AND type = ?` when `type` is
     given and `LIMIT ?` when `limit` is given. `count_by_status(kb_id, *,
     type=None)` likewise. Keep positional compatibility.
   - `requeue_stranded(kb_id=None)`: `assert "indexing" in
     KB_ITEM_TRANSITIONS["pending"]` (a real `assert` is fine here — the
     table is import-time data; a comment says it pins the bulk UPDATE to
     the table); `UPDATE kb_items SET status = 'pending', error = NULL,
     updated_at = ? WHERE status = 'indexing'` plus `AND kb_id = ?` when
     scoped; return `cur.rowcount`. `requeue_for_reindex(kb_id)`: assert
     both `"indexed"` and `"failed"` are in `KB_ITEM_TRANSITIONS["pending"]`;
     `… WHERE kb_id = ? AND type = 'file' AND status IN ('indexed', 'failed')`.
   - `KBChunkRepository`: `list_for_item(item_id, *, limit=None, offset=0)`
     — `LIMIT ? OFFSET ?` only when `limit` is given (SQLite needs a LIMIT
     for OFFSET; use `LIMIT -1 OFFSET ?` when only `offset` is given);
     `ids_for_item`; `iter_for_kb` as an `async def … -> AsyncIterator[
     list[KBChunk]]` generator: `last_id = 0`, loop `SELECT * … WHERE kb_id
     = ? AND id > ? ORDER BY id LIMIT ?`, yield the page, break when it is
     shorter than `batch_size`.
2. **`the_one/knowledge/walk.py`.**
   - `SKIPPED_DIRS: frozenset[str] = frozenset({"node_modules",
     "__pycache__", "venv", "site-packages"})`.
   - `@dataclass(frozen=True) class DiscoveredFile: path: str; size_bytes:
     int; mtime: float`. `@dataclass class WalkResult: files:
     list[DiscoveredFile]; skipped_dirs: int; skipped_entries: int`.
   - `walk_folder(root: Path, *, extensions: frozenset[str]) -> WalkResult`:
     synchronous (Leg 3 calls it under `asyncio.to_thread`). `root` is
     expected canonical; raise if `not root.is_dir()`. Iterative: a stack of
     directory paths starting at `root`; for each, `os.scandir(dirpath)`
     inside `try/except PermissionError, FileNotFoundError` (count and
     continue); for each entry: `name = entry.name`; skip if
     `name.startswith(".")` (not counted — a by-design filter); then
     `try: name.encode("utf-8") except UnicodeEncodeError` → skip and count
     (**before** the dir/file split, so a non-UTF-8 *directory* name is
     never pushed onto the stack — otherwise every path joined under it
     would be unencodable; design review, medium); if `entry.is_symlink()`
     → skip and count (a symlinked directory counts in `skipped_dirs`, a
     symlinked file in `skipped_entries`); if `entry.is_dir(follow_symlinks=
     False)` → push unless `name in SKIPPED_DIRS` (count in `skipped_dirs`);
     elif `entry.is_file(follow_symlinks=False)` → suffix check
     `os.path.splitext(name)[1].lower() in extensions` (an unsupported
     suffix is not counted — by design, not an item), then
     `st = entry.stat(follow_symlinks=False)` inside `try/except OSError:
     skip and count`, append `DiscoveredFile(os.path.join(dirpath, name),
     st.st_size, st.st_mtime)`. Sort `files` by path for determinism.
   - `plan_reconcile(discovered: Sequence[DiscoveredFile], existing:
     Sequence[KBItem]) -> ReconcilePlan` with `new: list[DiscoveredFile]`,
     `removed: list[KBItem]`, `changed: list[tuple[KBItem, DiscoveredFile]]`,
     `unchanged: int`. Build `by_path = {item.path_or_url: item}`; iterate
     discovered; then the leftover existing are `removed`.
   - `content_hash(path: Path) -> str`: `hashlib.sha256`, read in
     `1024 * 1024` blocks.
   - `is_filesystem_root(path: Path) -> bool`: `path.parent == path`.
   - Module docstring: cites flight DD-3, states the walk is stat-only and
     that the size cap and binary sniff are the indexer's (Leg 2).
3. **Route** (`the_one/interfaces/web/api.py::create_kb_item`).
   - Wrap `KBItem.model_validate(data)` in `try/except ValidationError`
     → `HTTPException(422, e.errors(include_context=False))`, the
     `create_knowledge_base` shape at `:1414-1420`.
   - If `item.type == "folder"`: `canonical = canonicalize(item.path_or_url)`
     (import from `the_one.platform.paths` — check whether `api.py` already
     imports from `the_one.platform`; add the import if not); `if not await
     asyncio.to_thread(canonical.is_dir)` → 422 `f"folder does not exist or
     is not a directory: {item.path_or_url}"`; `if is_filesystem_root(
     canonical)` → 422; for each `existing in await repo.list_folders(kb_id)`:
     `if is_within(canonical, existing.path_or_url) or is_within(existing.
     path_or_url, canonical)` → 409 `f"folder overlaps registered folder
     {existing.id}: {existing.path_or_url}"`. Then `item = item.model_copy(
     update={"path_or_url": str(canonical)})`.
   - After `await repo.create(item)`: `if item.type == "folder":
     _after_folder_registered(kb_id)`. Define `def
     _after_folder_registered(kb_id: str) -> None:` near `_kb_item_repo`
     with a docstring: "Leg 1 no-op seam; Leg 3 replaces the body with
     `get_indexing_manager().request_index(kb_id)`."
4. **AC-11 needs no route change**: `delete_kb_item` (`api.py:1559-1578`)
   already forwards whatever `repo.delete(item_id)` returns to
   `store.delete`; the widened repository method is the whole fix and the
   test is the only addition (design review).
5. **`SECURITY-MODEL.md`** bullet per AC-12, after the sqlite-extension
   bullet, before `## Boxed Execution Mode`.
6. **Tests**, in the order above; keep every existing test untouched.
   `tests/test_kb_walk.py` builds its fixture tree under `tmp_path` with
   `os.symlink` (skip the symlink cases with `pytest.mark.skipif` only on a
   platform where `os.symlink` raises — not needed on this Linux host, but
   write the guard so the file is portable). For the "opens no file" test,
   `monkeypatch.setattr("builtins.open", _raise)` and
   `monkeypatch.setattr("io.open", _raise)`.
7. **Flight log** entry under "Leg Progress" and a line in "Session Notes";
   `make test-unit` figures; the exact `SKIPPED_DIRS` value and the walk's
   count fields recorded (the flight's Acceptable Variations require it).

## Edge Cases

- **Non-UTF-8 filenames** (`os.scandir` returns surrogate-escaped `str`):
  storing one in a `TEXT` column raises `UnicodeEncodeError` inside
  `sqlite3`. The walk skips and counts them (AC-6) rather than letting the
  bulk insert fail the whole batch.
- **Symlinked root**: `canonicalize` resolves it at registration, so the
  stored path is the target; the walk never sees a symlink at the root.
- **Case-insensitive filesystems** (Windows, macOS default): two
  registrations differing only in case canonicalise to the same `resolve()`
  result on Windows (drive letter and existing components are normalised);
  on macOS `resolve()` does not fold case. Accepted: containment is
  string-equality on canonical paths; recorded, not solved.
- **Duplicate paths inside one walk**: impossible from one `scandir` tree
  without symlinks; `plan_reconcile` still keys on the string, so a
  duplicate would collapse to one.
- **A `folder` item deleted while a child is `indexing`**: not this leg's
  concern (no worker exists); Leg 3 stops the worker first.
- **`requeue_for_reindex` on a KB with zero items** returns 0 and commits an
  empty transaction — harmless.
- **`iter_for_kb` while chunks are being replaced**: pages are separate
  reads with no transaction between them; a chunk inserted mid-iteration
  with a higher id is seen, one deleted is not — Leg 2's rebuild tolerates
  both (`kb_chunks` is truth; the rebuild is exceptional).
- **`list_for_item(limit=None, offset=5)`**: use `LIMIT -1 OFFSET ?`.

## Files Affected

- `the_one/db/repositories.py` — `KBItemRepository.delete` widened;
  `create_many`, `list_children`, `list_folders`, `requeue_stranded`,
  `requeue_for_reindex`; `list_by_status`/`count_by_status` keyword filters;
  `KBChunkRepository.list_for_item` paging, `ids_for_item`, `iter_for_kb`
- `the_one/knowledge/walk.py` — new
- `the_one/interfaces/web/api.py` — `create_kb_item` validation and hook
- `SECURITY-MODEL.md` — one bullet
- `tests/test_kb_walk.py` — new
- `tests/test_db_repositories.py`, `tests/test_kb_chunks.py`,
  `tests/test_db_api.py` — additions only
- `missions/24-knowledge-bases/flights/03-folder-registration-and-indexing/flight-log.md`

## Citation Audit

Checked against the flight branch at `148f704` on 2026-09-15:
`repositories.py::_fts_delete_rows` at `:375`; `KBItemRepository` at
`:484`, `delete` at `:531-552`, `list_by_status` at `:607`, `count_by_status`
at `:616`; `KBChunkRepository.list_for_item` at `:749`, `count_for_kb` at
`:778`; `api.py::create_kb_item` at `:1487-1501` (corrected at design review) and
the `create_knowledge_base` 422 handler at `:1414-1420`; `paths.py::canonicalize` `:29`,
`is_within` `:54`; `_kb_types.KB_ITEM_TRANSITIONS`; test fixtures at the
lines cited in Inputs. All present; no drift.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [ ] If final leg of flight:
  - [ ] Update flight.md status to `landed`
  - [ ] Check off flight in mission.md
- [x] Commit all changes together (code + artifacts)
