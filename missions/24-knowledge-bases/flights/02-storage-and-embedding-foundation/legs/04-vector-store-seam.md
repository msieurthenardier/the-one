# Leg: vector-store-seam

**Status**: completed
**Flight**: [Storage and Embedding Foundation](../flight.md)

## Objective

Land the vector-store seam — a vectors-and-integer-ids-only Protocol with
`sqlite-vec` and `usearch` both behind it, the extension loaded inside the
`sqlite-vec` store with the probe's discipline, the sidecar registry and
staleness detection for `usearch`, a dispatcher that reads the
`knowledge.vector_store` record — plus the store cleanup wired into the KB and
item delete routes, one shared Protocol test suite run against every
backend × dtype cell, and the `SECURITY-MODEL.md` / `agents.md` contract text.

## Context

- Flight DD-3 (contract; `upsert` = delete-then-insert; write ordering:
  chunks + FTS commit first, vectors after, `indexed` only once vectors have
  landed; both stores acquire the write lock themselves — never nested;
  `SqliteVecStore` owns `kb_vectors` and checks the live DDL; `UsearchStore`
  is a per-KB sidecar with a store-owned registry table; `data_dir` resolved
  at `open()`; reset seam), DD-4 (dtype cells: sqlite-vec `float32`/`int8`,
  usearch `f16`/`i8`; the float32 cell stores upcast float16), DD-10
  (extension loaded in `open()`, enable → load → disable, `_loaded` flag,
  fail-loud from `open()`, `SECURITY-MODEL.md` paragraph), DD-13 (no
  re-entry; the store is a committer).
- Legs 1–3 landed. `KnowledgeBaseRepository.delete` and
  `KBItemRepository.delete` (returns the removed chunk ids) do the SQL-side
  cleanup; this leg adds the store-side cleanup at the **route** call sites,
  after the repository transaction, never inside it.
- The DD-3 "vectors landed" moment is made concrete here: `usearch` cannot
  save an HNSW index per `upsert` at scale (a save is O(N)), so the store
  exposes `flush(kb_id)`; "vectors landed" means **flushed**, and Flight 3's
  pipeline calls `flush` before it moves an item to `indexed`. `sqlite-vec`'s
  `flush` is a no-op (its writes commit on `upsert`).
- Empirical facts verified during planning on this host: `vec0` accepts
  `kb_id TEXT partition key` with `float[N]` and `int8[N]` (the latter bound
  via `vec_int8(?)`; a bare 4-byte-multiple blob is misread as float32);
  partition-keyed KNN with `AND kb_id = ? AND k = ?`; delete by rowid;
  `usearch.Index(ndim, metric="cos", dtype="f16"|"i8")`, `add` with numpy
  arrays only and explicit keys, `search(..., exact=True)` available,
  `save(path)`/`save() -> bytes`/`restore(path)`, `remove`, `contains`,
  `len`; `aiosqlite.Connection.enable_load_extension` / `load_extension` are
  coroutine methods; repeated `load_extension` is idempotent;
  `SQLITE_MAX_LENGTH` 1e9 (why BLOB persistence was rejected). Verified
  after drafting, on this host: `vec0(kb_id TEXT partition key, embedding
  int8[512] distance_metric=cosine)` is accepted and a `vec_int8()` KNN
  returns the planted rowid at distance ~0; `DELETE … WHERE rowid = ?`
  works on a partition-keyed table with no declared primary-key column;
  `DELETE … WHERE kb_id = ?` empties a partition; `usearch` `i8` and `f16`
  indexes return the planted key first for the same quantised vectors, a
  single-vector `search` returns `Matches` with `.keys`/`.distances`, and
  `remove` of an absent key returns without raising.

## Inputs

- `the_one/diagnostics.py:350-400` — `_probe_sqlite_vec`'s
  `hasattr(sqlite3.Connection, "enable_load_extension")` check, the
  `loadable_path()`-is-extensionless note, the enable → `sqlite_vec.load` →
  `finally: disable` discipline, the `serialize_float32` bind and the
  `MATCH ? AND k = ?` query; `_probe_usearch` (`:500+`) for the `ndim`,
  numpy-only and keys-not-vectors notes.
- `the_one/db/_write_lock.py` — `write_transaction`; `the_one/db/repositories.py`
  — `KnowledgeBaseRepository.delete` (`:445-463`), `KBItemRepository.delete`
  (`:533-548`, returns `list[int]`), `KBChunkRepository.list_for_item` /
  `get_many` (`:6xx`), `AppMetadataRepository`.
- `the_one/knowledge/settings.py` (Leg 3) — `EMBEDDING_KEY`, `CHUNKING_KEY`,
  the `load_/save_` shape; `the_one/interfaces/web/api.py:1557-1600` —
  `_knowledge_settings_response(current)` **already** returns `{"embedding",
  "chunking", "notes": list(_KNOWLEDGE_SETTINGS_NOTES)}`, and
  `update_knowledge_settings` **already** 422s any top-level key outside
  `{"embedding", "chunking"}` (generic message) — this leg extends the
  response with `"vector_store"` while preserving `notes`, and relies on
  the existing guard for AC-12 (no new message; the generic check fires
  first). `the_one/embeddings/__init__.py` — `get_embedding_backend()`'s
  double-checked locking, the shape the dispatcher and `open()` mirror;
  `the_one/embeddings/_backend.py` — `EmbedResult` (vectors are `float32`,
  unit-norm).
- `the_one/interfaces/web/api.py` — `delete_knowledge_base`, `delete_kb_item`
  (Leg 1's scoped version), the `_kb_repo`-style helpers.
- `the_one/platform/pty.py:130-163` (`create_pty_session` dispatch shape),
  `the_one/platform/sandbox/factory.py:52-72` (reset seam),
  `the_one/config.py:103-107` (`settings.data_dir / "…"` subdir precedent),
  `the_one/tools/sessions.py:168` (a runtime-created `data_dir` subdir).
- `tests/test_db_repositories.py:28-40` (the `conn` fixture);
  `tests/test_doctor.py::TestProbeSqliteVec` (`_SpyConnection` technique).
- `SECURITY-MODEL.md` — `## Tool Execution Boundary` (`:489`) is where the
  native-extension paragraph goes; `the_one/agents.md` `### Knowledge
  storage` (Leg 2/3).

## Outputs

- `the_one/vectors/_store.py` (new): `VectorStore` (`@runtime_checkable`
  Protocol, all methods `async`): `open()`, `upsert(kb_id, ids, vectors)`,
  `delete(kb_id, ids)`, `delete_kb(kb_id)`, `query(kb_id, vector, k) ->
  list[tuple[int, float]]`, `count(kb_id) -> int`, `flush(kb_id)`,
  `close()`, plus `backend: str`, `dtype: str`, `dim: int`;
  `VectorStoreError`, `VectorStoreMismatchError`, `VectorStoreStaleError`;
  `quantize_int8(vectors) -> np.ndarray[int8]` — **`np.clip(np.rint(v * 127),
  -127, 127).astype(np.int8)`**; the cast is load-bearing: without it the
  array stays float and `serialize_int8(q.tolist())` raises `struct.error`
  (design review verified) — shared by both int8 cells.
- `the_one/vectors/sqlite_vec_store.py` (new): `SqliteVecStore(conn, *,
  dtype: Literal["float32", "int8"], dim: int = 512)`.
- `the_one/vectors/usearch_store.py` (new): `UsearchStore(conn, *, dtype:
  Literal["f16", "i8"], dim: int = 512)`; `rebuild_from(kb_id,
  ids_and_vectors: Iterable[tuple[Sequence[int], np.ndarray]])`.
- `the_one/vectors/__init__.py` (new): re-exports; `_build_store(settings:
  VectorStoreSettings, conn) -> VectorStore` (the named seam AC-11's test
  monkeypatches); `async get_vector_store() -> VectorStore` (loads the
  record, double-checked under an `asyncio.Lock` like
  `get_embedding_backend()`, calls `_build_store`, `open()`s it, caches
  it); `_reset_for_test()`.
- `the_one/knowledge/settings.py`: `VectorStoreSettings(backend:
  Literal["sqlite-vec", "usearch"], dtype: str, dim: int = 512, model_id:
  str = "potion-retrieval-32M")` with a validator tying `dtype` to
  `backend` (`float32|int8` for sqlite-vec, `f16|i8` for usearch),
  `VECTOR_STORE_KEY = "knowledge.vector_store"`, `load_vector_store_settings`
  / `save_vector_store_settings`. Default during Legs 4–5: `sqlite-vec` /
  `float32`. **Not** exposed through `PUT /api/knowledge-settings` (DD-6:
  store-written — the existing top-level-key guard already 422s it); `GET`
  shows it read-only under `"vector_store"`, alongside the existing `notes`.
- `the_one/interfaces/web/api.py`: `delete_knowledge_base` calls
  `store.delete_kb(kb_id)` after `repo.delete`; `delete_kb_item` calls
  `store.delete(kb_id, ids)` after `repo.delete`; both log-and-continue on
  store failure (the DB is truth; a stale vector row for a never-recycled
  id is harmless).
- `SECURITY-MODEL.md`: a paragraph under `## Tool Execution Boundary`.
- `the_one/agents.md`: `### Knowledge storage` gains the seam, the write
  ordering, the flush rule, the no-nesting rule, the registry table and
  staleness rule, the dtype cells.
- Tests: `tests/test_vector_store.py` (new; the shared suite parametrised
  over four cells), `tests/test_vectors_dispatch.py` (new), `tests/test_db_api.py`
  additions (delete routes call the store), `tests/test_knowledge_settings.py`
  additions.
- Flight log entry; leg ticked in `flight.md`.

## Acceptance Criteria

- [x] AC-1 Both backends structurally satisfy `VectorStore`
      (`isinstance(..., VectorStore)` is `True`, no inheritance).
- [x] AC-2 Shared suite, for each of the four cells (sqlite-vec float32,
      sqlite-vec int8, usearch f16, usearch i8) with seeded unit-norm
      `np.float32` vectors of dim 512 built in the test file: after
      `upsert(kb, ids, vecs)` of 50 vectors, `query(kb, vecs[i], 1)` returns
      `ids[i]` first for every `i`; `query(kb, v, 10)` returns exactly 10
      results with non-decreasing distances; `count(kb) == 50`.
- [x] AC-3 `upsert` of an id that already exists replaces its vector (a
      query with the new vector returns that id first; `count` unchanged);
      `delete(kb, [id])` removes it (`count` drops, the id never appears in
      results); `delete_kb(kb)` leaves `count(kb) == 0` and `query(kb, v,
      10) == []`.
- [x] AC-4 KB isolation: identical vectors upserted under `kb_a` and `kb_b`
      never appear in each other's results.
- [x] AC-5 Reopen: a second store instance over the same connection (and the
      same `data_dir` for usearch) after `flush` + `close` answers the same
      queries; for usearch the sidecar file exists at
      `{data_dir}/vectors/{kb_id}.usearch` and the registry row's `count`
      equals `count(kb)`.
- [x] AC-6 `SqliteVecStore.open()` loads `vec0` on the app connection
      (`SELECT vec_version()` succeeds), leaves extension loading
      **disabled** afterwards (a subsequent `await conn.load_extension(...)`
      raises), is idempotent, and two concurrent `open()` calls load once.
      A `sqlite3` build without `enable_load_extension` (simulated by the
      `TestProbeSqliteVec` module-swap technique) raises
      `VectorStoreError` from `open()` naming `knowledge.vector_store`.
- [x] AC-7 Mismatch detection: a `kb_vectors` table created as `float[512]`
      and a store opened with `dtype="int8"` (or `dim=256`) raises
      `VectorStoreMismatchError` from `open()` naming the setting and both
      shapes; the live DDL is read from `sqlite_master`, not from the
      setting.
- [x] AC-8 usearch staleness: tampering the registry row's `count` (or
      deleting the sidecar) makes the next `query` raise
      `VectorStoreStaleError`; `rebuild_from(kb_id, …)` clears it and
      answers correctly afterwards; `flush` is what advances `generation`
      and `count` (an `upsert` without `flush` followed by a fresh store
      instance does not see the new vectors — documented behaviour).
- [x] AC-9 Dispatcher: `get_vector_store()` returns `SqliteVecStore` when
      the record is absent (default) or says `sqlite-vec`, `UsearchStore`
      when it says `usearch`, the same instance on repeated calls,
      `_reset_for_test()` makes the next call build anew, and `data_dir` is
      read at `open()` — a `settings.data_dir` monkeypatch applied after
      `get_vector_store()` but before `open()` is honoured.
- [x] AC-10 Both stores acquire the write lock themselves; calling
      `store.upsert` from inside a caller's `write_transaction` raises
      `RuntimeError` (re-entry) rather than deadlocking; the Leg 1 source
      guard still passes (`commit()`/`rollback()` only in the two files).
- [x] AC-11 `DELETE /api/knowledge-bases/{kb_id}` and `DELETE …/items/{id}`
      call the store's `delete_kb` / `delete` with the right ids after the
      repository transaction (asserted with a recording stub store injected
      via `_reset_for_test()` + a monkeypatched builder); a store failure is
      logged and the route still returns 200.
- [x] AC-12 `GET /api/knowledge-settings` now includes `"vector_store"` **and
      still includes `"notes"`**; `PUT` with a `vector_store` key returns 422
      (the existing top-level-key guard — asserted, not re-implemented).
      `VectorStoreSettings` rejects `sqlite-vec`+`f16` and `usearch`+`float32`.
- [x] AC-13 `make test-unit` green (foreground, alone, once); wall time within
      Leg 2's baseline plus test-count growth; ruff clean.

## Verification Steps

- AC-1–5, 7, 8, 10: `PYTHON=.venv/bin/python bash scripts/run-tests.sh
  tests/test_vector_store.py -x --timeout 120`.
- AC-6: same file; the extension-state assertions live there.
- AC-9: `… tests/test_vectors_dispatch.py -x --timeout 60`.
- AC-11–12: `… tests/test_db_api.py tests/test_knowledge_settings.py -x
  --timeout 120`.
- AC-13: `make test-unit`; `ruff check the_one/ tests/`; `ruff format --check
  the_one/ tests/`.

## Implementation Guidance

1. **`_store.py`.** Protocol + errors + `quantize_int8`. Docstring states the
   contract in full: integer ids are `kb_chunks.id` values (never
   recycled); no text or metadata ever crosses; the write ordering and the
   flush rule; both stores acquire the write lock — never call a store from
   inside `write_transaction`.

2. **`SqliteVecStore`.** `open()`: `if self._loaded: return`; `async with
   write_transaction(self.conn):` → **re-check `if self._loaded: return`
   inside the lock** (double-checked locking, the `get_embedding_backend()`
   shape — without the inner check two concurrent `open()`s both pass the
   outer check before either sets the flag and the second re-runs the whole
   body after the first releases; a counting monkeypatch then sees 2 loads
   and AC-6 fails — design review traced it) → `hasattr(sqlite3.Connection,
   "enable_load_extension")` else raise `VectorStoreError` (message names
   `knowledge.vector_store` and the build) → `await
   conn.enable_load_extension(True)`; `try: await conn.load_extension(str(
   sqlite_vec.loadable_path()))` `finally: await conn.enable_load_extension(
   False)` → `CREATE VIRTUAL TABLE IF NOT EXISTS kb_vectors USING vec0(kb_id
   TEXT partition key, embedding {col}[{dim}] distance_metric=cosine)` where
   `col` is `float` or `int8` → read `SELECT sql FROM sqlite_master WHERE
   name='kb_vectors'` and assert it contains `embedding {col}[{dim}]`, else
   `VectorStoreMismatchError` → `self._loaded = True`. Use
   `sqlite_vec.loadable_path()` via `load_extension` (aiosqlite proxies
   it), **not** `sqlite_vec.load(conn)` — on an `aiosqlite.Connection` that
   call does not raise; it creates never-awaited coroutines and loads
   nothing (design review verified) — which is why AC-6's
   `SELECT vec_version()` assertion is the proof that loading happened. `upsert`: `async with write_transaction`: `executemany(
   "DELETE FROM kb_vectors WHERE rowid = ?", …)` then `executemany(
   "INSERT INTO kb_vectors(rowid, kb_id, embedding) VALUES (?, ?, ?)"` with
   `serialize_float32(row.tolist())` for float32 or `"…VALUES (?, ?,
   vec_int8(?))"` with `serialize_int8(quantize_int8(row).tolist())` for
   int8. `query`: `SELECT rowid, distance FROM kb_vectors WHERE embedding
   MATCH ? AND kb_id = ? AND k = ?` (or `MATCH vec_int8(?)`), return
   `[(int(rowid), float(distance)), …]`. `count`, `delete`, `delete_kb` as
   named; `flush` and `close` are no-ops.

3. **`UsearchStore`.** `open()`: `self._data_dir = settings.data_dir /
   "vectors"` resolved **here**, `mkdir(parents=True, exist_ok=True)`;
   `async with write_transaction`: `CREATE TABLE IF NOT EXISTS
   kb_vector_index (kb_id TEXT PRIMARY KEY, path TEXT NOT NULL, count
   INTEGER NOT NULL, generation INTEGER NOT NULL, dtype TEXT NOT NULL, dim
   INTEGER NOT NULL, updated_at TEXT NOT NULL)`. Per-KB state: an in-memory
   `dict[kb_id, _KbIndex(index | None, lock: asyncio.Lock, dirty: bool)]`.
   Get-or-create the **entry** (and its lock) synchronously —
   `self._kbs.setdefault(kb_id, _KbIndex(None, asyncio.Lock(), False))` with
   no `await` between check and insert — then `async with entry.lock:` load
   the index if `entry.index is None` (the lock cannot guard its own
   creation; the synchronous `setdefault` is what makes it safe).
   `_get(kb_id, create)`: under the KB lock, if not loaded: read the
   registry row; no row → new empty `Index(ndim=dim, metric="cos",
   dtype=dtype)` (only if `create`); row present → `await
   asyncio.to_thread(Index.restore, path)`; if the file is missing or
   `len(index) != row.count` or `row.dtype/dim` differ → mark stale and
   raise `VectorStoreStaleError` on any read/write except `rebuild_from`
   and `delete_kb`. `upsert`: under the KB lock, `to_thread`: `index.remove(
   existing keys)` for ids the index `contains`, then `index.add(keys,
   vectors)` (`np.asarray(ids, dtype=np.uint64)`; vectors `float32` — usearch
   casts to the index dtype internally; for `i8` pass `quantize_int8`
   output so both int8 cells quantise identically); `dirty = True`. `flush`:
   if dirty, `to_thread(index.save, path)` then `async with
   write_transaction`: upsert the registry row with `count = len(index)`,
   `generation += 1`, `updated_at`; `dirty = False`. `query`: `to_thread(
   index.search, vector, k)`; return `[(int(key), float(dist)), …]` from
   `matches.keys` / `matches.distances`. `delete`: `index.remove`, dirty.
   `delete_kb`: drop cache, delete the file if present, delete the
   registry row. `rebuild_from`: new index, add every batch, save, registry
   upsert, clear stale. `close`: flush every dirty KB.

4. **Dispatcher.** `get_vector_store()` is **async** (it reads a DB record
   — a documented departure from `create_pty_session`'s sync shape): fast
   path `if _store is not None: return _store`; else `async with _lock:`
   re-check; `settings = await load_vector_store_settings(conn)`; `store =
   _build_store(settings, conn)` (lazy-imports the backend module — the
   seam AC-11 patches); `await store.open()`; cache; return. Two concurrent
   first callers build once.

5. **Settings.** `VectorStoreSettings` as in Outputs; `load_` returns the
   default `sqlite-vec`/`float32` when the record is absent, and raises
   (not defaults) when a stored record is invalid — a corrupt store record
   is the one setting that must not silently fall back, because the wrong
   backend reads the wrong data. `GET` includes it; `PUT` refuses it (422:
   "vector_store is written by the application, not the operator").

6. **Routes.** A `_vector_store()` helper (`await get_vector_store()`).
   After `await repo.delete(kb_id)`: `try: await store.delete_kb(kb_id)
   except Exception: logger.exception(...)`. Item route: `ids = await
   repo.delete(item_id)` then `store.delete(kb_id, ids)` if `ids`.

7. **Tests.** `tests/test_vector_store.py`: a `cell` fixture parametrised
   `[("sqlite-vec","float32"), ("sqlite-vec","int8"), ("usearch","f16"),
   ("usearch","i8")]` building the store over the `conn` fixture and a
   `tmp_path` data dir (monkeypatch `settings.data_dir`), with a
   module-local autouse fixture calling `the_one.db._write_lock.reset_for_test()`
   and `the_one.vectors._reset_for_test()`. Vectors: `rng =
   np.random.default_rng(2024)`, normalised rows. For the int8 cells the
   "returns itself first" assertion holds because quantisation is
   deterministic and cosine is scale-invariant. AC-6's "load once" test:
   `asyncio.gather(store.open(), store.open())` with a counting
   monkeypatch on `load_extension`. AC-11 uses a recording stub satisfying
   the Protocol structurally.

8. **`SECURITY-MODEL.md`** paragraph: the app loads one native SQLite
   extension (`sqlite-vec`'s `vec0`, shipped in the wheel and collected by
   the spec) on first vector-store use, with extension loading enabled for
   the three awaits it takes and disabled again in a `finally`; no other
   extension is ever loaded; the loaded code stays for the process
   lifetime like any imported C extension.

9. **`agents.md`** and the **flight log entry** (test counts per cell, unit
   gate figures, the empirical answers to the two open probes in Context,
   and — for Leg 5 — the observed per-upsert cost of usearch `save` at the
   sizes the tests used).

## Edge Cases

- **`upsert` with empty `ids`** → no-op, no transaction.
- **`vec0` rowids are unique table-wide, not per partition** (design review
  verified: `rowid=1` under `kb_a` then `rowid=1` under `kb_b` raises
  `UNIQUE constraint failed`). Production is safe because every id comes
  from one global `kb_chunks.id` sequence; the **shared test suite must use
  disjoint id ranges per KB** (e.g. `kb_a` 1–50, `kb_b` 101–150) or the
  sqlite-vec cells of AC-4 fail while the usearch cells pass. The store
  docstring states the invariant.
- **Duplicate ids within one `upsert` call** → the last wins for usearch
  (remove-then-add per key) and raises for vec0 (UNIQUE) — the seam
  documents "ids within a call are distinct" and the chunk repository
  guarantees it; not validated.
- **Re-indexed items leave dangling vector rows**: `replace_item_chunks`
  retires old chunk ids, and nothing in this leg deletes their vectors
  (only KB/item deletes reach the store). Harmless — ids are never recycled
  and `get_many` filters unknown ids — but Flight 3's pipeline owns
  deleting the old ids' vectors after a re-index; recorded as a Flight 3
  input, not fixed here.
- **`query` on a KB with no vectors** → `[]` (sqlite-vec returns no rows;
  usearch: no index → `[]` without creating one).
- **`k` larger than `count`** → fewer results; never an error.
- **usearch `remove` of an absent key** → returns without raising
  (verified), so `upsert` may call `remove(keys)` unconditionally; keep the
  `contains` check only if a count of actually-removed keys is needed.
- **usearch `search` result shape** for a single vector is `Matches` with
  `.keys`/`.distances`; a 2-D input returns `BatchMatches` — always pass a
  1-D `float32` array.
- **Two `SqliteVecStore` instances over one connection** (tests) → the
  second `open()` re-runs the DDL `IF NOT EXISTS` and the DDL check; the
  extension is already loaded — `load_extension` again is idempotent.
- **`data_dir` changes after `open()`** → not honoured (documented; the
  reset seam exists for tests).
- **int8 quantisation of a non-unit vector** → clipped to ±127; the seam's
  contract says unit-norm input; document, do not re-normalise.
- **Windows path separators** in the registry `path` column → store the
  absolute `str(Path)`; the OS writes what it reads.
- **`vec0` and `VACUUM`/backups** → nothing here; the Architect verified a
  `vec0` DB opens and migrates without the extension loaded.

## Files Affected

- `the_one/vectors/__init__.py`, `_store.py`, `sqlite_vec_store.py`, `usearch_store.py` — new
- `the_one/knowledge/settings.py` — `VectorStoreSettings`, key, load/save
- `the_one/interfaces/web/api.py` — delete routes call the store; `GET` shows `vector_store`; `PUT` refuses it
- `SECURITY-MODEL.md`, `the_one/agents.md` — contract text
- `tests/test_vector_store.py`, `tests/test_vectors_dispatch.py` — new
- `tests/test_db_api.py`, `tests/test_knowledge_settings.py` — additions
- `missions/24-knowledge-bases/flights/02-storage-and-embedding-foundation/flight-log.md`, `flight.md`

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed` (the Flight Director sets `completed` after the flight-end review)
- [x] Check off this leg in flight.md
- [x] Do NOT commit — review and commit are deferred to the flight-end review

## Citation Audit

Design review (Developer, 2026-09-14) verified every citation against the
tree with Legs 1–3 landed and probed sqlite-vec / usearch / aiosqlite
mechanics directly. Two highs fixed (int8 cast; double-checked locking in
`open()`); two mediums fixed (existing `notes` field and top-level-key guard
in the settings routes cited and relied on; table-wide `vec0` rowid
uniqueness recorded with the disjoint-id-range test rule); `repositories.py`
citations corrected (+9 lines). Verified holding: explicit-rowid inserts,
`vec_int8(?)` inside `executemany`, `Index.add` on `i8`/`f16` with float32
input, `restore`, `len`, empty-index `search`, the re-entry `RuntimeError`.
