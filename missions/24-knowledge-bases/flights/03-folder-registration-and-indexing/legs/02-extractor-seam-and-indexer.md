# Leg: extractor-seam-and-indexer

**Status**: completed
**Flight**: [Folder Registration and Indexing](../flight.md)

## Objective

Land the extractor seam (Protocol, in-tree registry, `TextExtractor`, a
test-only second extractor), the per-item indexer that implements Flight 2's
write ordering for the first time (`index_item`), the flush-cadence policy
object, the stale-sidecar rebuild (`rebuild_kb`) with `rebuild_from` widened
to an async iterable and added to the `VectorStore` Protocol, the
`entry.dirty` reorder in `UsearchStore`, the DD-12 in-pipeline measurement,
and the `agents.md` "Knowledge indexing" contract — with no worker, no
lifespan wiring and no route: nothing in this leg runs unless a test or Leg
3's manager calls it.

## Context

- Flight DD-4 (extractor seam), DD-5 (pipeline stages, `EMBED_BATCH = 256`,
  the flush cadence and the operator's overhead-cap bar, zero-norm rows,
  `truncated` logging, the lock-ordering invariant, `ctx.should_stop`),
  DD-6 (stale recovery: pass-level catch is Leg 3's; the rebuild generator
  takes no manager lock and never calls back into the store), DD-7 (the
  `entry.dirty` reorder; `awaiting_flush` is Leg 3's), DD-12 (measurement).
- Leg 1 landed (uncommitted, in the working tree): `KBChunkRepository.
  ids_for_item`, `iter_for_kb(kb_id, batch_size)`, `list_for_item(limit=,
  offset=)`; `KBItemRepository.update_status`, `set_content_identity`;
  `the_one/knowledge/walk.py::content_hash(path)`. This leg consumes them
  and adds nothing to the repositories.
- Flight 2 contracts this leg implements or must not break: chunks + FTS
  commit first (`replace_item_chunks`, one transaction), vectors after via
  the store, an item is `indexed` only after `flush` — **the flip to
  `indexed` is Leg 3's** (it happens after a flush the worker decides on);
  this leg leaves the item at `indexing`. The store acquires the write lock
  itself — a caller never wraps a store call in `write_transaction`.
  `EmbeddingBackend.embed` is sync and CPU-bound, run under
  `asyncio.to_thread`; `EmbedResult.vectors` float32 `(n, dim)` unit-norm
  within `NORM_TOLERANCE` (1e-3), zero-norm rows possible for texts that
  tokenise to nothing.
- Test conventions: every seam-consumer test runs against
  `tests/_embedding_stub.py::StubEmbeddingBackend` (dim 8 by default,
  `truncate_over_chars=` to exercise the truncated path); the real model
  loads stay in `tests/test_doctor_embedding_model.py`; a real
  `UsearchStore(conn, dtype="f16", dim=8)` on a `tmp_path` data dir (the
  `tests/test_vector_store.py` fixture shape at `:60-90`, `settings.
  data_dir` monkeypatched before `open()`).

## Inputs

- Working tree = flight branch `148f704` + Leg 1's uncommitted changes.
- `the_one/vectors/_store.py::VectorStore` Protocol (`:73-99`: `open`,
  `upsert`, `delete`, `delete_kb`, `query`, `count`, `flush`, `close`; no
  `rebuild_from`) and `::VectorStoreStaleError` (`:66`).
- `the_one/vectors/usearch_store.py`: `upsert` (`:255-283` — the empty
  `write_transaction` shim at `:266-267`, `entry.dirty = True` at `:283`
  *after* the `to_thread`), `delete` (`:285-299`, `dirty` at `:299`),
  `flush` (`:341-367`), `rebuild_from(kb_id, ids_and_vectors: Iterable[
  tuple[Sequence[int], np.ndarray]])` (`:383-409`, synchronous `for` inside
  `entry.lock`), `_check_dim` (`:242-253`).
- `tests/test_vector_store.py`: `rebuild_from` call sites at `:331`, `:357`,
  `:382`, `:596`, `:684` — all pass a plain list `[([1, 2, 3], vecs)]`.
- `the_one/embeddings/_backend.py`: `EmbeddingBackend`, `EmbedResult`,
  `NORM_TOLERANCE = 1e-3` (`:23`). `the_one/embeddings/local.py::
  MAX_TOKENS = 512` (`:44`), `EMBEDDING_MODEL_DIRNAME` (`:36`).
- `the_one/knowledge/chunking.py::chunk_text(text, *, size_chars=1000,
  overlap_chars=150) -> list[ChunkRecord]` (`:78`; empty text → `[]`).
- `the_one/knowledge/settings.py::ChunkingSettings` (`size_chars`,
  `overlap_chars`).
- `the_one/db/repositories.py`: `KBItemRepository.update_status(item_id,
  status, *, error=None)` (raises `KBItemTransitionError` / `KeyError`;
  stores `error` only into `failed`), `set_content_identity(item_id, *,
  content_hash, size_bytes, mtime)`; `KBChunkRepository.replace_item_chunks
  (item_id, kb_id, chunks) -> list[int]`, `ids_for_item(item_id)`,
  `iter_for_kb(kb_id, batch_size=1000)` (async generator of `list[KBChunk]`).
- `the_one/tools/filesystem.py::_is_binary` (`:274-281`): read 8192 bytes,
  `b"\x00" in chunk` — the rule to re-implement, not import.
- `the_one/tools/filesystem.py:383`: `read_text(errors="replace")` — the
  decode precedent.
- `the_one/connectors/registry.py`: module-level `_PLUGINS: dict`,
  `register`, `get_plugin`, `unregister`, `clear_for_test` — the in-tree
  registry shape.
- `the_one/agents.md` "Knowledge storage (Flight 2, Legs 1-4)" section
  (`:1140-1175`), whose last paragraph is "**The chunker**" (`:1175`)
  followed by `### Web-session idle reaper` (`:1177`).
- Flight 2 log, Windows benchmark tables (`missions/24-knowledge-bases/
  flights/02-storage-and-embedding-foundation/flight-log.md` `:1550-1700`):
  `save_ms` 244 at 20k, 1,908 at 200k (Windows usearch f16), the 1M/3M
  extrapolation table — the save curve DD-12's extrapolation uses.

## Outputs

- `the_one/knowledge/extractors/__init__.py` (new): `Extractor` Protocol,
  `ExtractionError`, `register`, `unregister`, `extractor_for`,
  `supported_extensions`, `clear_for_test`, built-in registration.
- `the_one/knowledge/extractors/text.py` (new): `TextExtractor`,
  `TEXT_EXTENSIONS`.
- `the_one/knowledge/indexer.py` (new): `MAX_FILE_BYTES`, `EMBED_BATCH`,
  `IndexContext`, `ItemOutcome`, `index_item`, `FlushPolicy`,
  `rebuild_kb`, `is_binary_head`.
- `the_one/vectors/_store.py`: `rebuild_from` on the Protocol, async-
  iterable input, the generator-must-not-call-back invariant in the
  docstring.
- `the_one/vectors/usearch_store.py`: `rebuild_from` iterates an
  `AsyncIterable`; `entry.dirty = True` moved ahead of the `to_thread` in
  `upsert` and `delete`.
- `tests/_extractor_stub.py` (new), `tests/test_kb_extractors.py` (new),
  `tests/test_kb_indexer.py` (new); `tests/test_vector_store.py` updated
  at the five `rebuild_from` sites (async-generator wrapper) plus a new
  test for the async input and the call-back invariant.
- `the_one/agents.md`: a "**Knowledge indexing** (Flight 3, Leg 2)"
  paragraph block after "The chunker".
- Flight log: leg entry with the DD-12 measurement table and the
  extrapolation.

## Acceptance Criteria

- [x] **AC-1 — Extractor seam.** `the_one/knowledge/extractors/__init__.py` defines a `runtime_checkable` `Extractor` Protocol (`name: str`, `extensions: frozenset[str]`, `extract(path: Path) -> str`), `ExtractionError(RuntimeError)`, and a module-level registry keyed by lower-cased dotted suffix with `register(extractor)` (raises `ValueError` if a suffix is already claimed by a *different* extractor name; re-registering the same name is a no-op), `unregister(name)`, `extractor_for(path) -> Extractor | None` (by `path.suffix.lower()`), `supported_extensions() -> frozenset[str]`, and `clear_for_test()` — the `the_one/connectors/registry.py` shape. Importing the package registers `TextExtractor`; `supported_extensions()` on import equals `TEXT_EXTENSIONS`. `TextExtractor` satisfies the Protocol structurally (`isinstance` true, no inheritance).
- [x] **AC-2 — Text extraction.** `TextExtractor.extract(path)` returns the file decoded as `utf-8-sig` with `errors="replace"` (a UTF-8 BOM is stripped; an invalid byte becomes U+FFFD, never an exception); a missing file raises `ExtractionError` chained from the `OSError`. `TEXT_EXTENSIONS` is the flight DD-4 set (`.txt .text .md .markdown .rst .adoc .py .pyi .js .mjs .cjs .ts .tsx .jsx .json .jsonl .yaml .yml .toml .ini .cfg .conf .csv .tsv .sh .bash .zsh .ps1 .bat .go .rs .java .kt .c .h .cc .cpp .hpp .cs .rb .php .swift .sql .xml`), lower-case with the dot, and contains neither `.html` nor `.htm` nor `.log`.
- [x] **AC-3 — The M7 test.** `tests/_extractor_stub.py::StubExtractor` (name `stub`, extensions `{".stub"}`, returns a fixed string) registered inside a test makes `index_item` index a `.stub` file end to end — chunks in `kb_chunks`, vectors in the store — with `indexer.py` unchanged (the test imports nothing private from it and patches nothing in it). `unregister`/`clear_for_test` + re-import of the built-ins restores the registry in the fixture's teardown so no other test sees `.stub`.
- [x] **AC-4 — `index_item` happy path.** `index_item(item, ctx) -> ItemOutcome` on a `pending` `file` item with a real text file: moves it `pending → indexing`; extracts under `asyncio.to_thread`; chunks with `ctx.chunking` under `to_thread`; reads old ids via `ids_for_item`; calls `replace_item_chunks` (one transaction); calls `ctx.store.delete(kb_id, old_ids)` **only when** `old_ids` is non-empty and **after** the chunk transaction; embeds in `EMBED_BATCH`-sized batches under `to_thread`; calls `ctx.store.upsert(kb_id, ids, vectors)` per batch; calls `set_content_identity` with the sha256 (`walk.content_hash`), size and mtime taken at extraction time; leaves the item at `indexing`; returns `ItemOutcome(status="awaiting_flush", chunks=n, vectors=n, truncated=0, error=None)`. Afterwards `store.count(kb_id)` equals the chunk count and `list_for_item` has `n` rows in `seq` order. A re-index of the same item deletes the old ids from the store (recording stub asserts the exact ids) and the new ids are disjoint from the old (`AUTOINCREMENT`).
- [x] **AC-5 — Failure paths land `failed` with the DD-5 messages**, each as its own test, each leaving zero chunks for the item and no store call: a missing file (`error` names the path); a file over `MAX_FILE_BYTES = 10 * 1024 * 1024` (`error == "file exceeds the 10 MiB indexing cap"`, checked from `stat` before any read); a file whose first 8192 bytes contain a null byte (`error == "binary content"`); an extractor raising `ExtractionError` (`error` is its message); a `file` item with no registered extractor (`error` names the suffix); a `folder` or `url` item (`error` says the type is not indexable — Leg 3 never sends these, but the function must not crash on them). Any other exception from stages 2–8 is caught, the item lands `failed` with `f"{type(exc).__name__}: {exc}"` truncated to 1,000 characters, and the exception is logged with traceback. `asyncio.CancelledError`, `VectorStoreStaleError`, `KBItemTransitionError` and `KeyError` from stage 1 are **not** caught — they propagate.
- [x] **AC-6 — Zero-norm and truncated rows.** With a stub backend returning one all-zero row among `n`: `n` chunks are stored in SQLite, `n-1` vectors are upserted (the zero row's id is absent from the `upsert` ids), `ItemOutcome.vectors == n-1`, `chunks == n`. With `StubEmbeddingBackend(truncate_over_chars=…)` making two inputs count as truncated: `ItemOutcome.truncated == 2` and one `INFO` log line names the item id and the count (caplog).
- [x] **AC-7 — Cooperative stop seam.** `ctx.should_stop` is consulted before each embed batch after the first; when it returns `True` mid-item the function returns `ItemOutcome(status="stopped", …)` with the item left at `indexing`, chunks committed, and no further `upsert` (recording stub proves the batch count). `ctx.embed_lock` (an `asyncio.Lock | None`) is held around each embed + upsert pair and released between batches (a test with a lock and a concurrent waiter observes the waiter acquiring it between batches).
- [x] **AC-8 — `FlushPolicy`.** `FlushPolicy(min_chunks=2000, min_seconds=15.0, save_multiplier=10.0, clock=time.monotonic)` with `record_chunks(n)`, `should_flush() -> bool` (true iff `chunks_since_flush >= min_chunks` **and** `clock() - last_flush_at >= max(min_seconds, save_multiplier * last_flush_seconds)`), and `record_flush(duration_seconds)` (resets `chunks_since_flush`, sets `last_flush_at = clock()`, `last_flush_seconds = duration`). Under a fake clock a test proves: no flush before `min_chunks`; no flush before `min_seconds`; after a 5 s flush no further flush until 50 s have elapsed even with 10× `min_chunks` recorded; the module constants `FLUSH_MIN_CHUNKS = 2000`, `FLUSH_MIN_SECONDS = 15.0`, `FLUSH_SAVE_MULTIPLIER = 10.0` are the defaults. `FlushPolicy` never calls the store — Leg 3 owns the flush call and the `awaiting_flush` list.
- [x] **AC-9 — `rebuild_from` widened.** `VectorStore` Protocol gains `async def rebuild_from(self, kb_id: str, ids_and_vectors: AsyncIterable[tuple[Sequence[int], np.ndarray]]) -> None` with a docstring stating: the store iterates the caller's generator while holding its per-KB lock, so the generator may only read `kb_chunks` and embed and must never call back into the store. `UsearchStore.rebuild_from` uses `async for`; the five existing test call sites wrap their lists in a small `_aiter(list)` helper; a new test proves a generator that awaits between pages works; `isinstance(UsearchStore(...), VectorStore)` stays true and no other `isinstance(…, VectorStore)` consumer exists (grep recorded in the log).
- [x] **AC-10 — `rebuild_kb(kb_id, ctx)`.** Streams `ctx.chunk_repo.iter_for_kb(kb_id, 1000)`, embeds each page under `to_thread` **without** `ctx.embed_lock` (DD-5's ordering note), skips zero-norm rows, yields `(ids, vectors)` into `ctx.store.rebuild_from`, and logs one `WARNING` naming the KB and the reason string it was given. Test: index three items, delete the sidecar file, build a fresh store on the same connection (stale on first touch), call `rebuild_kb` with a stale reason, assert `count(kb_id)` equals the vector-bearing chunk count and a `query` for a known chunk's own vector returns its id first. The generator is unit-tested to touch only `iter_for_kb` and `backend.embed` (a store stub that raises on any call other than `rebuild_from` passes).
- [x] **AC-11 — `entry.dirty` reorder.** In `UsearchStore.upsert` and `delete`, `entry.dirty = True` is set **before** the `asyncio.to_thread` mutation (in `delete`, after the `entry.index is None` early return). A test proves a `to_thread` that raises after mutating still leaves `dirty` true so the next `flush` saves. Existing `tests/test_vector_store.py` tests pass unchanged apart from the five wrapper edits.
- [x] **AC-12 — DD-12 measurement, recorded in the flight log.** A scratch script (under the session scratchpad, not committed) indexes a generated corpus of ~10,000 chunks (≈10 files × 1 MB of text) through `index_item` against the real `UsearchStore` f16 (dim 512, a temp data dir) with the stub backend at dim 512, then flushes on the `FlushPolicy` defaults with a manual driver loop, recording: total wall time; count and total time of the empty `write_transaction` shim (instrument by wrapping **`the_one.vectors.usearch_store.write_transaction`** — the name `usearch_store.py:50` binds into its own module namespace; patching `the_one.db._write_lock.write_transaction` would leave `upsert`/`delete`'s calls unaffected and record 0 — design review, medium); per-flush `save` time (`UsearchStore.flush` wall) and flush count at 10k; and an extrapolation of save overhead at 1M vectors on Windows using Flight 2's save curve (`save_ms` 244 at 20k, 1,908 at 200k, ~10–12 s extrapolated at 1M) against the ~7 ms/vector Windows insert rate — stated as a percentage with the arithmetic shown. The Divert threshold in the flight spec is 15 % at 1M.
- [x] **AC-13 — `agents.md`.** A "**Knowledge indexing** (Flight 3, Leg 2)" block after "The chunker" in the Knowledge storage section: the extractor registry (in-tree, keyed by suffix, `register` from the package `__init__`; a new format is one module and one `register` call; `.html` deliberately absent), the eight `index_item` stages in order with the write ordering and where each transaction boundary lies, the "item stays `indexing` until the flush that covers it" rule, `FlushPolicy` and its three constants with the operator's overhead-cap bar and the resulting re-work window figures, zero-norm and `truncated` handling, `rebuild_kb` as the only stale recovery with the no-call-back invariant, the `entry.dirty` reorder, the lock-ordering invariant as corrected at design review (manager lock → store per-KB lock → write lock; `upsert`/`delete` acquire-and-release the write lock *before* the per-KB lock; only `flush`/`rebuild_from` nest), and the two crash-window consequences for Flight 5. Leg 3 extends the block with the manager.
- [x] **AC-14 — Gates.** `ruff check` / `ruff format --check` clean; `make test-unit` green, figures and per-file test-count deltas in the flight log; real model loads still confined to `tests/test_doctor_embedding_model.py` (grep `LocalStaticBackend.load(` / `from_pretrained` in the new tests: 0).

## Verification Steps

- AC-1–AC-3: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_kb_extractors.py -x --timeout 60 -q`.
- AC-4–AC-8, AC-10: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_kb_indexer.py -x --timeout 60 -q`.
- AC-9, AC-11: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_vector_store.py -x --timeout 60 -q`; `grep -rn "isinstance(.*VectorStore" tests/ the_one/`.
- AC-12: the scratch script's output pasted into the flight log.
- AC-13: read the block; `grep -n "Knowledge indexing" the_one/agents.md`.
- AC-14: `make lint`; `make test-unit` once, alone, foreground.

## Implementation Guidance

1. **Extractors package.** `the_one/knowledge/extractors/__init__.py`:
   ```python
   @runtime_checkable
   class Extractor(Protocol):
       name: str
       extensions: frozenset[str]
       def extract(self, path: Path) -> str: ...
   class ExtractionError(RuntimeError): ...
   _BY_SUFFIX: dict[str, Extractor] = {}
   def register(extractor: Extractor) -> None: ...
   def unregister(name: str) -> None: ...
   def extractor_for(path: Path) -> Extractor | None: ...
   def supported_extensions() -> frozenset[str]: ...
   def clear_for_test() -> None: ...
   def _register_builtins() -> None:  # called at import; also what a test calls after clear_for_test
       from the_one.knowledge.extractors.text import TextExtractor
       register(TextExtractor())
   _register_builtins()
   ```
   `text.py`: `TEXT_EXTENSIONS: frozenset[str]` and `class TextExtractor:
   name = "text"; extensions = TEXT_EXTENSIONS; def extract(self, path):
   try: return path.read_bytes().decode("utf-8-sig", errors="replace")
   except OSError as exc: raise ExtractionError(f"cannot read {path}: {exc}") from exc`.
   Keep the import of `text.py` inside `_register_builtins` so the
   package import order is not circular. Unlike `connectors/registry.py`'s
   flat 1:1 dict, one extractor claims many suffixes: `register` inserts
   one dict entry per suffix in `extractor.extensions` (checking each for
   a conflicting *different* `name` before inserting any — all-or-nothing);
   `unregister(name)` scans the dict and removes every entry whose
   owner's `.name` matches.
2. **`indexer.py`.**
   - Constants: `MAX_FILE_BYTES = 10 * 1024 * 1024`, `EMBED_BATCH = 256`,
     `FLUSH_MIN_CHUNKS = 2000`, `FLUSH_MIN_SECONDS = 15.0`,
     `FLUSH_SAVE_MULTIPLIER = 10.0`, `_ERROR_MAX_CHARS = 1000`,
     `_BINARY_SNIFF_BYTES = 8192`.
   - `is_binary_head(path: Path) -> bool` — the four-line `_is_binary`
     rule.
   - `@dataclass class IndexContext: conn; item_repo: KBItemRepository;
     chunk_repo: KBChunkRepository; store: VectorStore; backend:
     EmbeddingBackend; chunking: ChunkingSettings; should_stop:
     Callable[[], bool] = lambda: False; embed_lock: asyncio.Lock | None =
     None; embed_batch: int = EMBED_BATCH`.
   - `@dataclass(frozen=True) class ItemOutcome: status: Literal[
     "awaiting_flush", "failed", "stopped"]; chunks: int; vectors: int;
     truncated: int; error: str | None`.
   - `async def index_item(item: KBItem, ctx: IndexContext) -> ItemOutcome`:
     stage 1 `await ctx.item_repo.update_status(item.id, "indexing")`
     (let its errors propagate); then a `try:` around stages 2–8 with
     **exactly this three-clause order** (design review, medium):
     ```python
     try:
         ...  # stages 2-8
     except (asyncio.CancelledError, VectorStoreStaleError):
         # CancelledError is a BaseException since 3.8 and would never
         # reach `except Exception` anyway; it is named here so a future
         # "simplification" does not drop the VectorStoreStaleError guard
         # that DOES need it (DD-6: the pass-level catch is Leg 3's).
         raise
     except _Reject as exc:
         return await _fail(ctx, item, str(exc))          # no traceback log
     except Exception as exc:
         logger.exception("indexing %s failed", item.id)
         return await _fail(ctx, item, f"{type(exc).__name__}: {exc}")
     ```
     where `_Reject(Exception)` is private to the module, `_fail` does
     `update_status(item.id, "failed", error=message[:_ERROR_MAX_CHARS])`
     and builds the `failed` outcome.
     Stage 2: `if item.type != "file": reject`; `path = Path(item.
     path_or_url)`; `extractor = extractor_for(path)`; `if extractor is
     None: reject(f"no extractor for suffix {path.suffix!r}")`; `st =
     await asyncio.to_thread(path.stat)` (`FileNotFoundError` → reject
     naming the path); `if st.st_size > MAX_FILE_BYTES: reject("file
     exceeds the 10 MiB indexing cap")`; `if await asyncio.to_thread(
     is_binary_head, path): reject("binary content")`; `text = await
     asyncio.to_thread(extractor.extract, path)`; `digest = await
     asyncio.to_thread(content_hash, path)`. **Two full reads and one head
     read, by design**: the 8 KiB sniff, then `extract` (one full read),
     then `content_hash` (a second streamed full read). Folding the hash
     into the extractor would put a hashing concern on every future
     extractor; the second read costs ~20 ms per MB (measured at
     planning) against ~250 ms of embedding per MB. Recorded, not
     optimised. Stage 3:
     `chunks = await asyncio.to_thread(chunk_text, text, size_chars=…,
     overlap_chars=…)`. Stage 4: `old_ids = await ctx.chunk_repo.
     ids_for_item(item.id)`; `ids = await ctx.chunk_repo.
     replace_item_chunks(item.id, item.kb_id, chunks)`. Stage 5: `if
     old_ids: await ctx.store.delete(item.kb_id, old_ids)`. Stages 6–7:
     iterate `range(0, len(ids), ctx.embed_batch)`; before each batch
     after the first, `if ctx.should_stop(): return stopped outcome`;
     acquire `ctx.embed_lock` if not `None` (`contextlib.nullcontext()`
     otherwise) around `result = await asyncio.to_thread(ctx.backend.
     embed, texts_batch)` + norm filter (`np.linalg.norm(vectors, axis=1)
     < _ZERO_NORM_THRESHOLD` → drop those rows and ids; count — where
     `_ZERO_NORM_THRESHOLD = NORM_TOLERANCE` with a comment that the
     reuse is deliberate: a genuine zero row has norm ≈ 0, a unit row
     ≈ 1, so any threshold in (1e-6, 0.9) classifies identically; the
     seam's own tolerance constant is reused rather than inventing one) + `await
     ctx.store.upsert(item.kb_id, kept_ids, kept_vectors)` (skip the call
     when nothing is kept). Sum `result.truncated`. Stage 8: `await
     ctx.item_repo.set_content_identity(item.id, content_hash=digest,
     size_bytes=st.st_size, mtime=st.st_mtime)`. Log at INFO when
     `truncated > 0`. Return `awaiting_flush`.
   - `class FlushPolicy` per AC-8; pure, clock-injected.
   - `async def rebuild_kb(kb_id: str, ctx: IndexContext, *, reason: str)
     -> None`: `logger.warning(...)`; define `async def _pages():` that
     `async for page in ctx.chunk_repo.iter_for_kb(kb_id, 1000)`: embeds
     `[c.text for c in page]` under `to_thread` (no lock), filters
     zero-norm, `yield (ids, vectors)`; then `await ctx.store.
     rebuild_from(kb_id, _pages())`.
3. **Store changes.** `_store.py`: add `rebuild_from` to the Protocol with
   the docstring invariant; import `AsyncIterable` from
   `collections.abc`. `usearch_store.py`: change the signature and the
   loop to `async for ids, vectors in ids_and_vectors:`; move `entry.dirty
   = True` above the `await asyncio.to_thread(_do_upsert, entry.index)`
   line in `upsert` and above the `to_thread(entry.index.remove, keys)`
   line in `delete` (after its `if entry.index is None: return`), with a
   one-line comment citing DD-7. `tests/test_vector_store.py`: add
   `async def _aiter(items): for item in items: yield item` near the top
   and wrap the five call sites.
4. **Tests.** `tests/test_kb_indexer.py` fixtures: `conn` (the
   `test_vector_store.py` shape), `store` (real `UsearchStore(conn,
   dtype="f16", dim=8)` with `settings.data_dir` monkeypatched to
   `tmp_path` and `open()` called), `backend` (`StubEmbeddingBackend(dim=
   8)`), `ctx` assembling `IndexContext` with `ChunkingSettings(size_chars
   =200, overlap_chars=20)` so small fixture files produce several chunks,
   and a `_make_kb_and_item(conn, path)` helper creating a KB and a
   `pending` `file` item pointing at a `tmp_path` file. A
   `RecordingStore` (structural `VectorStore` with lists of calls) for the
   assertions on delete/upsert ids and batch counts. Use
   `_reset_lock_state`-style autouse resets as `tests/test_kb_chunks.py:29`
   does.
5. **Measurement script** per AC-12, run from the scratchpad against a
   temp data dir; paste the table into the flight log's leg entry.
6. **`agents.md`** per AC-13. **Flight log** entry: Changes Made, the
   measurement table, per-file test-count deltas, `make test-unit` figures,
   the `isinstance` grep result, any deviation with reason.

## Edge Cases

- **Empty extraction** (a zero-byte or whitespace-only file): `chunk_text`
  returns `[]`; `replace_item_chunks` deletes any old rows and returns
  `[]`; no embed call is made; the outcome is `awaiting_flush` with
  `chunks=0` — a valid re-index result (Flight 2's contract), and Leg 3
  flips it to `indexed` at the next flush like any other.
- **File changes between stat and read**: the identity stored is the
  `stat` taken before the read; a later reconcile sees the newer mtime and
  requeues. Accepted (recorded).
- **Old ids present but the store never saw them** (a previous index was
  never flushed before a crash): `store.delete` of absent keys is a no-op
  in `usearch` (verified at Flight 2); harmless.
- **`embed` returning fewer rows than inputs** would be a backend defect:
  guard with `assert result.vectors.shape[0] == len(texts_batch)` so it
  fails loudly rather than misaligning ids.
- **A `VectorStoreStaleError` from `store.delete` in stage 5** propagates
  after the chunk transaction committed — the item is `indexing` with new
  chunks and no vectors; Leg 3's pass restart requeues it and the rebuild
  re-embeds from `kb_chunks`, which already holds the new chunks. Correct
  by construction; record it in the docstring.
- **`rebuild_kb` on an empty KB**: the generator yields nothing;
  `rebuild_from` builds an empty index, saves it, writes a registry row
  with `count = 0`, clears staleness.
- **`should_stop` before the first batch** is deliberately not checked —
  a stopped worker that has already committed chunks gains nothing by
  skipping the first batch; the between-batch check bounds the delay at
  one batch (~75 ms measured).

## Files Affected

- `the_one/knowledge/extractors/__init__.py`, `the_one/knowledge/extractors/text.py` — new
- `the_one/knowledge/indexer.py` — new
- `the_one/vectors/_store.py`, `the_one/vectors/usearch_store.py` — `rebuild_from` widening; `dirty` reorder
- `tests/_extractor_stub.py`, `tests/test_kb_extractors.py`, `tests/test_kb_indexer.py` — new
- `tests/test_vector_store.py` — five wrapper edits + two new tests
- `the_one/agents.md` — Knowledge indexing block
- `missions/24-knowledge-bases/flights/03-folder-registration-and-indexing/flight-log.md`

## Citation Audit

Checked against the working tree (flight branch `148f704` + Leg 1
uncommitted) on 2026-09-15: `_store.py` Protocol `:73-99`,
`VectorStoreStaleError` `:66`; `usearch_store.py` `upsert` `:255-283`
(shim `:266-267`, `dirty` `:283`), `delete` `:285-299`, `flush` `:341-367`,
`rebuild_from` `:383-409`; `test_vector_store.py` `rebuild_from` sites
`:331, :357, :382, :596, :684`, fixtures `:60-90`; `_backend.py`
`NORM_TOLERANCE` `:23`; `local.py` `MAX_TOKENS` `:44`,
`EMBEDDING_MODEL_DIRNAME` `:36`; `chunking.py::chunk_text` `:78`;
`filesystem.py::_is_binary` `:274`, `read_text(errors="replace")` `:383`;
`repositories.py` Leg 1 methods `ids_for_item` `:903`, `iter_for_kb` `:912`,
`list_for_item` `:884`, `update_status`, `set_content_identity`;
`walk.py::content_hash` `:210`; `agents.md` "The chunker" `:1175`, next
heading `:1177`. All present; no drift.

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
