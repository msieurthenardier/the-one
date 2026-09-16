# Flight: Folder Registration and Indexing

**Status**: in-flight
**Mission**: [Knowledge Bases](../../mission.md)

## Contributing to Criteria

- [ ] Operator can register a folder on disk as a knowledge base source, and see each discovered item's index status including failures *(this flight lands the API half: registration with validation, discovery by walk, every item's status/error visible through the existing item routes plus a per-KB status projection; the Studio half is Flight 6)*
- [ ] Files in a registered folder index automatically, and additions, modifications, and deletions are reflected without operator action or an app restart *(partial — this flight's reconciliation walk detects all three on every pass and is what Flight 4's watcher triggers; this flight runs the walk at registration, at startup, on re-index and on request, not on a filesystem event; behavior-test-backed here for the walk, in Flight 4 for the event path)*
- [ ] Indexing a large folder runs in the background without blocking the UI, and resumes rather than restarts after an interruption *(landed here: a supervised per-KB worker, per-item status as the checkpoint, `indexing → pending` requeue at startup; behavior-test-backed)*
- [ ] Operator can inspect a knowledge base's contents and metadata, and retrieve the source material behind any indexed item *(the API half: chunk read-back with exact offsets and the extracted source text; Studio rendering is Flight 6)*
- [ ] A new file-format handler or a different vector store can be introduced without modifying the indexing pipeline *(the extractor half lands here — an in-tree registry keyed by extension, one text implementation; the vector-store half landed in Flight 2)*
- [ ] Existing installs upgrade with no data loss, the unit gate stays green, and the frozen Windows installer still builds and runs *(no schema change in this flight; one frozen run at flight close, budgeted as a diagnostic)*

Reconnaissance (flight log, "Reconnaissance Report"): thirteen source items, none
already satisfied, none drifted. Two scoped down with the operator's
confirmation: R6 (the extrapolated Windows build-time figures are an
order-of-magnitude input to checkpoint sizing; the re-measure at 1M vectors
becomes a mission open question because no leg here produces such a corpus)
and M8 (with one valid model there is no reachable model change; re-index means
per-item on content change, whole-KB on operator request, and the stale-sidecar
rebuild). Item M6 (source read-back) is assigned to this flight.

---

## Pre-Flight

### Objective

Make a knowledge base usable from the API: an operator registers a folder,
the app walks it, extracts text from every supported file, chunks, embeds and
persists it through the Flight 2 seams, and keeps the item lifecycle honest
while doing so — in a background worker that survives a restart by resuming
from per-item status rather than starting over. The flight lands the folder
registration surface with path validation, the walk-and-filter rule, the
extractor seam with its text implementation, the indexer with the flush
cadence Flight 2 left to it, the stale-sidecar rebuild path, a per-KB
supervised worker wired into the lifespan, the per-KB status, re-index and
read-back routes, and one behavior test that drives it all on a dev instance.
No filesystem watcher (Flight 4), no agent tool or search fusion (Flight 5), no
Studio surface (Flight 6).

### Open Questions

- [x] Is folder registration a new route or the existing item route? → DD-1
- [x] `parent_id` or a new column for folder → file? → DD-2
- [x] Which files are indexed, which skipped, which fail? → DD-3
- [x] Extractor seam shape and registry → DD-4
- [x] Pipeline stages, batch shape, and the flush cadence → DD-5
- [x] Stale-sidecar recovery, and how the pipeline streams into `rebuild_from` → DD-6
- [x] Supervisor shape: per-KB long-lived worker, lifespan wiring, shutdown → DD-7
- [x] Routes: status projection, re-index, chunk and source read-back → DD-8
- [x] Behavior-test apparatus, act and observe paths → DD-9
- [x] HAT leg → DD-10 (yes, optional final leg — operator's call)
- [x] Frozen run and the dependency closure → DD-11
- [x] What is measured, and which measurement leaves the flight → DD-12
- [x] Operator's bars, recorded before code exists → DD-5 (flush cadence: save overhead capped near 10 %, the crash re-work window is the consequence — asked and answered at design review, 2026-09-15, after the Architect showed the first draft's 60 s window and the overhead cap cannot both hold at the corpus ceiling), DD-8 (source read-back capped at the file size cap; `/reindex` walks for changes by default and re-embeds only on `scope=all`)

### Design Decisions

**DD-1 — Folder registration is `POST /api/knowledge-bases/{kb_id}/items` with `type: "folder"`, validated and canonicalised; `file` and `url` items keep today's contract**
- The route exists (`the_one/interfaces/web/api.py::create_kb_item`) and the
  v40 CHECK and `KBItem.type` Literal already admit `folder`; only validation
  and the kick are missing. For `type == "folder"` the route canonicalises
  `path_or_url` via `the_one.platform.paths.canonicalize` (expanduser +
  resolve, the filesystem tools' precedent), requires an existing directory
  (422 otherwise, detail naming the path), refuses a filesystem root
  (`path.parent == path`, 422 — a walk of `/` or `C:\` is never intended),
  and refuses a folder that equals, lies inside, or contains another `folder`
  item of the same knowledge base (409, **checked in exactly that order —
  existence, then root, then containment — so a non-existent path inside a
  registered folder is 422, not 409**; detail naming the conflicting item;
  `the_one/platform/paths.py::is_within` — public, canonicalising, "equals
  or descendant" — applied in both directions). The stored `path_or_url` is the canonical
  absolute string. On 201 the route calls
  `IndexingManager.request_index(kb_id)` (DD-7). While it is being edited,
  the route also gains the `ValidationError → 422` handler its sibling
  `create_knowledge_base` already has (today a malformed item body 500s —
  Architect, low).
- `type == "file"` items created directly through the route are unchanged
  (existing tests create them with paths that do not exist). The worker
  processes any `pending` `file` item, standalone or walked; a standalone
  file whose path does not exist lands `failed` with that error — visible,
  never silently skipped. Standalone files are never deleted by a walk (the
  walk reconciles only a folder's children, DD-3). A standalone `file`
  item whose path lies inside a registered folder is accepted and indexed
  as its own item alongside the walked child — two items, two chunk sets
  — because the `file` route's contract is deliberately unchanged;
  recorded, not refused (Architect cycle 2, low). `url` items are dormant
  (mission constraint): the worker skips them and they stay `pending`.
- Security posture: registration is operator-only (no agent-facing route
  creates items; Flight 5's tools are read-only search), the app reads the
  folder with its own privileges, and no allowlist applies — the operator
  is choosing what their agents may read. `SECURITY-MODEL.md` gains a
  "Knowledge-base indexing" paragraph saying exactly this, plus the fact
  that chunk text is stored in plaintext in the SQLite database under the
  existing single-user, local-only model.
- Rejected: a dedicated `POST …/folders` route — a second creation surface
  for the same table, with the same body, that Flight 6's inventory would
  have to special-case.

**DD-2 — `parent_id` is the folder → file link; folder deletion cleans descendants' chunks, FTS rows and vectors; no schema change**
- `kb_items.parent_id` survived v40 as `REFERENCES kb_items(id) ON DELETE
  CASCADE` with zero readers outside the repository's own INSERT and row
  mapping (`repositories.py:513,519,635`). The relationship is one level
  deep. Reusing it is free; a new indexed `folder_item_id` would be a v42
  rebuild of `kb_items` for no gain. A lookup by `(kb_id, path)` has no
  index and needs none: the walk reconciles in memory against one
  `SELECT` of the folder's children (DD-3), never per file.
- **The cascade hazard the Knowledge storage contract already names.**
  `KBItemRepository.delete` (`repositories.py`, the FTS select-then-delete
  shape) selects only `kb_chunks WHERE item_id = ?`. Deleting a folder item
  would FK-cascade its children and *their* chunks away with no FTS delete
  — the exact desync `agents.md` calls a defect by convention. So `delete`
  widens, same signature: the `(id, text)` select becomes `WHERE item_id = ?
  OR item_id IN (SELECT id FROM kb_items WHERE parent_id = ?)`, the FTS
  delete covers all of them inside the same `write_transaction`, the
  returned `list[int]` carries every chunk id so `delete_kb_item` passes
  them all to `store.delete`. A test proves a folder delete leaves zero
  orphan FTS rows (`check_fts()` true) and calls the store with the
  children's ids.
- Additive repository surface for the walk and the worker, all under the
  write lock per `db-writes-hold-the-write-lock`: `KBItemRepository.
  create_many(items)` (one transaction — measured at planning: 500 rows in
  3.5 ms versus 484 ms as 500 one-row commits), `list_children(folder_item_id)`,
  `list_folders(kb_id)`, `list_by_status(kb_id, status, *, limit=None, type=None)`
  (additive keywords — the worker drains `type="file"` only, DD-7), `requeue_stranded(kb_id=None) -> int` (one conditional
  `UPDATE … SET status='pending' WHERE status='indexing'` — the
  `indexing → pending` edge of `KB_ITEM_TRANSITIONS`, applied in bulk; the
  method asserts the edge against the table at call time so a future table
  change cannot silently bypass it), and `requeue_for_reindex(kb_id) -> int`
  (`indexed|failed → pending`, likewise). `KBChunkRepository.list_for_item`
  gains `limit`/`offset` keywords with defaults that keep existing callers
  unchanged; it gains `ids_for_item(item_id) -> list[int]` (ids only — a
  10 MB file has ~13k chunks and the indexer must not materialise their
  text just to delete their vectors) and `iter_for_kb(kb_id, batch_size)`
  — keyset pagination on `id` — for DD-6's rebuild stream.
  `count_by_status` gains an optional `type=` filter (DD-8 counts file
  items only). `requeue_for_reindex` touches `file` items only;
  `requeue_stranded` touches every type (a folder stranded at `indexing`
  goes back to `pending`, and the walk handles a `pending` folder — DD-3).
  Every one of these methods is unit-tested in Leg 1 itself, since their
  first production consumer is Leg 3 (Architect).
- Recorded, not migrated: `kb_items.parent_id` has no index
  (`schema.py:2537-2539` creates only `kb_id` and `(kb_id, status)`), so
  `list_children` and the widened `delete`'s subquery scan the KB's rows.
  Fine at this flight's scale; a v42 index is a later flight's call if
  Flight 6's inventory ever needs it.

**DD-3 — The walk: `os.walk` without following symlinks, dot-entries and a short directory denylist skipped, an extension allowlist, a size cap; reconcile by `(size, mtime)` then hash**
- `the_one/knowledge/walk.py::walk_folder(root) -> list[DiscoveredFile]`
  runs `os.walk(root, followlinks=False)` under `asyncio.to_thread`. Pruned
  in place from `dirs`: any name starting with `.` (covers `.git`, `.hg`,
  `.svn`, `.venv`, `.idea`, `.vscode`) and `SKIPPED_DIRS = {"node_modules",
  "__pycache__", "venv", "site-packages"}`. Skipped from `files`: any name
  starting with `.`, any symlink (`entry.is_symlink()` — a symlinked file
  is skipped even when its target lies inside the root; Flight 4's watcher
  inherits the same rule so the two never disagree), and any extension not
  in `SUPPORTED_EXTENSIONS` (DD-4's registry union). Everything skipped is
  not an item — the operator's call at planning: unsupported formats never
  show as failures. Verified at planning: `Path.rglob` and
  `os.walk(followlinks=False)` both ignore a symlinked directory on this
  host's Python 3.12, but `os.walk`'s behaviour is explicit in its
  signature and does not depend on the pathlib version (`recurse_symlinks`
  only arrived in 3.13), so `os.walk` it is.
- The walk uses `os.scandir` per directory (so `is_symlink()` /
  `is_dir(follow_symlinks=False)` come from the `DirEntry`, never a second
  `stat`; `os.walk` yields bare names — Architect, low), pruning symlinked
  directories out of the descent as well as skipping symlinked files. Per
  discovered file it records the canonical absolute path
  (`os.path.join(root, name)` — the root is already canonical, entries
  under it need no second `resolve()`; a test proves no discovered path
  escapes the root), `st_size` and `st_mtime`. **The walk is stat-based
  only**: it does not open files. The 10 MiB cap and the binary sniff are
  the indexer's (DD-5, stage 2), because `failed` is reachable only from
  `indexing` (`KB_ITEM_TRANSITIONS`) — a walk that tried to fail a
  freshly-created `pending` row would need two transitions and an extra
  8 KiB read per file per pass (Architect, high). Over-cap and binary
  files with a supported extension therefore become `pending` items that
  the indexer fails with a visible error on its first pass; unsupported
  extensions are never items.
- **Reconcile** (`walk.py::plan_reconcile(discovered, existing) ->
  ReconcilePlan`, pure and unit-tested against `KBItem` lists): `existing`
  is `list_children(folder)`; new paths → `create_many` as `pending`
  children; existing items whose path is gone → delete through
  `KBItemRepository.delete` (chunks and FTS rows go inside its
  transaction; the returned chunk ids are handed by the worker to
  `store.delete`, exactly as the delete route does); existing items whose
  `(size_bytes, mtime)` differ from the stat → candidates for a content
  check: the worker hashes the file (sha256 of the bytes, under
  `to_thread`; measured 2 MB in 39 ms) and only when the hash differs from
  `content_hash` requeues it — **and only from `indexed` or `failed`**: a
  changed child already at `pending` is left alone (it will be re-indexed
  by this pass anyway), and `indexing` cannot occur at walk time because
  every pass begins with `requeue_stranded(kb_id)` (DD-7) and one worker
  owns a knowledge base. `pending → pending` would raise
  `KBItemTransitionError` (Architect cycle 2, high — the folder-status
  bug of cycle 1, repeated for files; the reconcile application is
  unit-tested against all four child statuses). A touched-but-identical
  file has its identity columns updated via `set_content_identity` and is
  not re-indexed. Unchanged `(size, mtime)` → untouched. Measured cost of
  the walk itself: 2,079 files stat'd in 24 ms on this host.
- The folder item's own status is the walk's status: `pending → indexing`
  when a walk starts, `→ indexed` when the reconcile plan has been applied
  (`indexed_at` = last walk), `→ failed` with the OS error when the root is
  missing or unreadable — in which case the children are left exactly as
  they are (an unplugged drive must not delete an index; the next walk
  after it returns re-syncs). There is no `indexed → indexing` edge, so a
  re-walk first moves the folder `→ pending` **only from `indexed` or
  `failed`**; a folder already at `pending` (startup requeue, `scope=all`
  re-index, or a first walk) proceeds directly — `pending → pending` would
  raise `KBItemTransitionError` (Architect, high: the first draft cycled
  unconditionally and would have collided with both bulk requeues).
- No file-count cap: the corpus ceiling is text bytes, and the size cap and
  allowlist bound each file. The walk logs its counts (discovered, new,
  changed, removed, skipped) at info level per pass.
- Rejected: honouring `.gitignore` (a `pathspec` dependency against the
  budget stakeholder, and a rule that only means something inside a
  repository); indexing anything that passes the binary sniff (log files,
  data dumps and unknown formats as noise — the operator chose the
  allowlist).

**DD-4 — Extractor seam: a `runtime_checkable` Protocol, an in-tree registry keyed by extension, one text implementation**
- `the_one/knowledge/extractors/__init__.py`: `Extractor` Protocol with
  `name: str`, `extensions: frozenset[str]` (lower-case, with the dot) and
  `extract(path: Path) -> str` — synchronous, run by the indexer under
  `asyncio.to_thread`, raising `ExtractionError` (a `RuntimeError`
  subclass) for anything the extractor considers a failed extraction.
  Structural satisfaction, no base class (`structural-Protocol-satisfaction`).
  The registry is a module-level `dict[str, Extractor]` with `register(
  extractor)`, `extractor_for(path) -> Extractor | None` (by lower-cased
  suffix) and `supported_extensions() -> frozenset[str]` — the in-tree
  shape of `the_one/connectors/registry.py`, never entry points (mission
  context: no discovery machinery exists anywhere in the tree). The
  package `__init__` registers the built-in extractors at import.
- `extractors/text.py::TextExtractor`: `extensions` = the plain-text,
  markdown and code set — `.txt .text .md .markdown .rst .adoc .py .pyi .js
  .mjs .cjs .ts .tsx .jsx .json .jsonl .yaml .yml .toml .ini .cfg .conf .csv
  .tsv .sh .bash .zsh .ps1 .bat .go .rs .java .kt .c .h .cc .cpp .hpp .cs .rb
  .php .swift .sql .xml` (the Architect may prune or extend; the list is a
  constant in one place). `extract` reads bytes and decodes `utf-8-sig`
  with `errors="replace"` (the `ReadFileTool` precedent, `filesystem.py:
  383`), so a stray non-UTF-8 byte degrades to U+FFFD rather than failing
  the file. HTML is deliberately absent: raw tags are poor chunk text, and
  `readability-lxml` + `markdownify` are already in the closure for a
  later `HtmlExtractor` — one module and one `register` call, the pipeline
  untouched, which is the mission criterion this seam exists for. PDF and
  Office follow the same path in a later mission.
- Test: a `tests/_extractor_stub.py` registering a fake `.stub` extractor
  proves the pipeline indexes a new format with no pipeline change
  (mission criterion M7 pinned by a test, not a claim).

**DD-5 — Pipeline: per-item stages under Flight 2's write ordering; embed in batches of 256; flush on an adaptive cadence; an item is `indexed` only after the flush that covers it**
- `the_one/knowledge/indexer.py::index_item(item, ctx) -> ItemOutcome`, where
  `ctx` bundles the connection, the repositories, the vector store, the
  embedding backend, a `should_stop: Callable[[], bool]` the worker checks
  between embed batches (DD-7's cooperative stop needs a seam inside Leg
  2's function — Architect cycle 3; when it returns true mid-item the
  item is left `indexing` with no further stage run, and the pass-start
  requeue clears it) and the `ChunkingSettings` read once per worker pass
  (DD-7 of Flight 2: chunking changes apply to future indexing only).
  Stages, in order: (1) `update_status(pending → indexing)`; (2) resolve
  the extractor (a `folder` or `url` item never reaches here — DD-7's loop
  skips both), `stat` the file, reject over `MAX_FILE_BYTES = 10 MiB` with
  `error = "file exceeds the 10 MiB indexing cap"`, sniff the first 8 KiB
  for a null byte and reject with `error = "binary content"` (the
  `_is_binary` rule from `the_one/tools/filesystem.py:274`, re-implemented
  in the indexer — four lines, and the tool's helper is a tool-config
  concern), then `extract` under `to_thread` — a missing file, an
  `ExtractionError`, or either rejection ends the item `failed` with the
  error message (truncated to 1,000 characters) and no further stage runs; (3) `chunk_text` under `to_thread` (measured: 10 MB in 273 ms
  — too long for the loop); (4) old chunk ids via `ids_for_item`, then `replace_item_chunks` — chunks and FTS commit in one
  transaction (measured: 1,000 chunks in 118 ms); (5) `store.delete(kb_id,
  old_ids)` if any — a stale vector for a deleted, never-recycled id is
  harmless, so this runs after the commit, never inside it (the store
  takes the write lock itself, DD-13 of Flight 2); (6) embed the chunk
  texts in batches of `EMBED_BATCH = 256` under `to_thread` (measured on
  this host: 3,570 chunks/s at 256, 3,922 at 1,000 — the larger batch buys
  10 % for four times the peak array; 256 keeps a 10 MB file's 13k chunks
  to 51 calls); rows whose norm is below `NORM_TOLERANCE` (the seam's
  documented zero-token edge) are kept as chunks — FTS still finds them —
  and excluded from the vector `upsert`, counted in the outcome; `truncated`
  from each `EmbedResult` is summed and logged at info per item, never an
  error; (7) `store.upsert(kb_id, ids, vectors)` per batch; (8)
  `set_content_identity(hash, size, mtime)` from the bytes and stat taken
  at extraction time — the identity the next reconcile compares against.
  The item is now `indexing` with its chunks committed and its vectors
  in memory; it joins the worker's `awaiting_flush` list.
- **Flush cadence** (the contract Flight 2 left explicitly to this flight):
  after each item the worker flushes when `chunks_since_flush >=
  FLUSH_MIN_CHUNKS (2,000)` **and** `seconds_since_flush >=
  max(FLUSH_MIN_SECONDS (15), FLUSH_SAVE_MULTIPLIER (10) × last_flush_seconds)`,
  and unconditionally when no `pending` item remains. After a successful
  `store.flush(kb_id)`, every item in `awaiting_flush` moves `indexing →
  indexed` (`indexed_at` set; a per-item `KBItemTransitionError` is
  logged and skipped, never escapes the pass) and the list clears. A
  failed flush leaves the list populated and the items `indexing`; the
  list is cleared at the start of every pass, right after
  `requeue_stranded(kb_id)` has moved those items back to `pending`, so
  a later successful flush can never attempt `pending → indexed`
  (Architect cycle 3, medium). Both clauses are lower
  bounds, so the rule *delays* flushing: the save-multiplier term is what
  keeps the O(N) save from dominating a build, and it is also what sets
  the crash re-work window. **Operator's bar, asked and answered at design
  review (2026-09-15)**: cap save overhead near 10 % of build time; the
  re-work window after a crash is the consequence, not a second bar. At
  Flight 2's measured and extrapolated Windows figures (save ~0.24 s at
  20k, ~10–12 s at 1M, ~24 s at 3M; insert ~7 ms per vector at 1M) that
  window is ~15 s for small corpora, ~2 min at 1M and ~4 min at 3M —
  minutes of re-work against a multi-hour build, paid only after a crash.
  The alternative (a hard 60 s ceiling) was priced at ~17 % overhead at 1M
  and 30–40 % at 3M on *every* build and declined. The chunk gate never
  binds on Windows at scale (2,000 inserts ≈ 14 s, under the time gate);
  it exists so a burst of tiny files on a fast host does not flush per
  file. All three constants are module-level and constructor-overridable
  on the manager for tests (DD-7). Leg 2's measurement (DD-12) records
  per-flush save time and flush count at the pipeline's batch shape and
  **extrapolates save overhead to 1M vectors using Flight 2's Windows
  save curve** (the rule holds overhead near 1/(1+multiplier) by
  construction, so a 10k-chunk Linux run can never exceed 10 % on its
  own; only the extrapolation makes the Divert criterion checkable —
  Architect cycle 2).
- A crash at any point leaves every `awaiting_flush` item `indexing` with
  chunks committed and vectors unflushed. Startup requeues them (DD-7);
  their re-index replaces the chunks (new ids; the old ids were never in a
  saved sidecar, or were and are now stale-but-harmless) and re-embeds.
  **Two consequences recorded for Flight 5's fusion design**: (a)
  `search_keyword` can return chunks of an `indexing` item whose vectors
  have not landed; (b) the inverse — between `replace_item_chunks` and the
  next flush, the saved sidecar still holds vectors for the *deleted*
  chunk ids, so a vector query can return ids with no `kb_chunks` row and
  `get_many` silently returns fewer (Architect). Fusion must tolerate both;
  neither is a defect here.
- Concurrency across knowledge bases: the manager holds one `asyncio.Lock`
  around stages (6)–(7) so two KB workers interleave batches rather than
  race two CPU-bound threads against one model; the walk and extraction
  stages run unserialised. **Lock ordering invariant**: `UsearchStore.upsert`/`delete` acquire
  **and release** the shared write lock (the empty-transaction shim,
  `usearch_store.py:262-266`) *before* taking the store's per-KB lock,
  and touch no SQL inside it; only `flush` and `rebuild_from` genuinely
  nest per-KB lock → write lock (`:359-366`, `:396-406`). The rule, stated
  so Flight 4's watcher author cannot misread it: **manager lock → store
  per-KB lock → write lock** is the only permitted nesting order; no code
  may acquire the manager or per-KB lock while holding the write lock, or
  the manager lock while holding a per-KB lock (Architect cycle 3
  corrected the earlier wording that described `upsert` as nesting). `rebuild_from` holds the
  per-KB lock across the caller's generator, so the rebuild generator
  takes **no** manager lock (DD-6) — the one place embedding runs
  unserialised across knowledge bases, accepted because a rebuild is
  exceptional. Stated in the manager docstring and in `agents.md`
  (Architect, cycles 1 and 2).
- `knowledge.vector_store` is written on first index: `IndexingManager.
  start_all` (and `start`, for a KB created after boot) calls
  `save_vector_store_settings` **only if the record is absent**, with the
  live store's `backend`/`dtype`/`dim` and
  `the_one.embeddings.local.EMBEDDING_MODEL_DIRNAME` as `model_id` — never `get_embedding_backend().model_id`, which would load
  the model synchronously on the event loop (Architect cycle 2, medium)
  — before any `upsert`. `load_vector_store_settings` already
  raises on a drifted record, so a present record is never overwritten.

**DD-6 — `VectorStoreStaleError` has exactly one recovery: re-embed every chunk of the knowledge base from `kb_chunks` into `rebuild_from`, streamed; `rebuild_from` joins the Protocol with an async-iterable input**
- Today `UsearchStore.rebuild_from(kb_id, ids_and_vectors: Iterable[…])`
  takes a synchronous iterable and is not on the `VectorStore` Protocol.
  The pipeline cannot pre-embed a knowledge base into memory (3M × 512 ×
  4 B is 6 GB), so the signature widens to `AsyncIterable[tuple[Sequence[
  int], np.ndarray]]` (an `async for` inside the store; the existing
  synchronous test callers wrap their lists in a trivial async generator)
  and the method is added to the Protocol — a backend that needs no
  rebuild implements it as a no-op that clears staleness. **Pinned in the
  Protocol docstring**: the store iterates the caller's generator while
  holding its per-KB lock, so the generator may only read `kb_chunks` and
  embed — it must never call back into the store (`count`, `flush`, …),
  which would deadlock (Architect, medium). The indexer's `rebuild_kb`
  generator is unit-tested to touch only the chunk repository and the
  backend. This is a
  shared-interface change on `the_one/vectors/` with consumers only in
  `tests/test_vector_store.py`; those tests update in the same leg.
- Trigger: `VectorStoreStaleError` from any store call (`upsert`,
  `delete`, `flush`, `count`) propagates out of `index_item` and is caught
  **at the pass level, after the manager lock has been released** — never
  inside stages (6)–(7), where `rebuild_kb`'s embedding would re-enter the
  non-reentrant manager lock and hang with `/status` stuck at
  `rebuilding` (Architect cycle 2, high). The worker then runs
  `rebuild_kb(kb_id)`: logs a warning with the stale reason (this is
  exceptional — it re-embeds everything), streams
  `KBChunkRepository.iter_for_kb(kb_id, 1_000)`, embeds each page taking
  no manager lock (DD-5's ordering note), yields `(ids, vectors)` into
  `store.rebuild_from`, then **restarts the pass** rather than retrying
  the item in place: the item it was on (or, when the stale error came
  from a between-items cadence flush, every item in `awaiting_flush`) is
  at `indexing`, and `index_item`'s stage 1 is `pending → indexing`, so a
  direct retry would raise `KBItemTransitionError("indexing→indexing")`
  (Architect cycle 3, high). A restarted pass begins with
  `requeue_stranded(kb_id)` and a cleared `awaiting_flush` (DD-5), so
  those items return to `pending` and are re-indexed in order. The manager reports the worker as
  `rebuilding` for the duration (DD-8's status route — at 1M vectors this
  is hours, and `running` would misdescribe it; Architect Q2). Items are
  not touched: `kb_chunks` is the source of truth and every item's status
  stays what it was. If the rebuild itself raises, the current item lands
  `failed` with the error, the worker logs at error level and parks
  (returns to waiting for the next request); a later `request_index`
  tries again. No retry loop — a rebuild that fails twice is a defect to
  surface, not to hide.
- `delete_kb` and `rebuild_from` are the only store calls that do not
  raise on a stale KB (Flight 2), so `delete_knowledge_base` keeps its
  log-and-continue shape and never needs the rebuild.

**DD-7 — `IndexingManager`: one long-lived, event-woken worker task per knowledge base, started in the lifespan after the embedding warm-up, drained before the connector manager**
- `the_one/knowledge/manager.py::IndexingManager`, modelled on
  `ConnectorManager` (`the_one/connectors/manager.py:51-227`): a
  `dict[kb_id, _WorkerEntry(task, wake: asyncio.Event, stop_requested:
  bool, state, awaiting_flush: list[str])]` — `awaiting_flush` lives on
  the entry, not in the coroutine's locals, because the manager reads and
  clears it after the worker task is gone (Architect cycle 2); `start(kb_id)`
  creates the task if absent; `request_index(kb_id)` sets the event
  (starting the worker if needed); `stop(kb_id)` is **cooperative**: it
  sets `stop_requested`, wakes the event, and `asyncio.wait_for`s the task
  for `STOP_TIMEOUT = 20 s` — the worker checks the flag between items and
  between embed batches (via `ctx.should_stop`, DD-5) and returns from its
  pass — falling back to `task.cancel()` only on timeout. Cancellation is the fallback, not the
  mechanism, because `UsearchStore.upsert` mutates the in-memory index
  inside `asyncio.to_thread` (`usearch_store.py:275-283`): a cancelled
  await returns while that thread still runs, and a flush taken over the
  same index would race a live mutation (Architect cycle 2, high). In the
  cancel-fallback path the manager therefore does **not** flush; the
  in-flight item stays `indexing` and the next pass's `requeue_stranded`
  (below) or the next startup clears it. Leg 2 also moves `entry.dirty =
  True` ahead of the `to_thread` call in `UsearchStore.upsert`/`delete`
  so an interrupted mutation can never be skipped by `flush` as
  not-dirty (a dirty-but-unchanged index costs one save, nothing else).
  `drain()` stops all; `state(kb_id) -> "idle" | "running" | "rebuilding"
  | "stopped"` for the status route — `running` covers the whole pass,
  walk included; `stopped` means the worker died on an unexpected
  exception; a knowledge base with no worker entry at all reads `idle`
  (Architect cycle 2, low). Module-level accessor pair (`get_indexing_manager()` /
  `_set_module_indexing_manager()`) so routes reach the lifespan-owned
  instance the way connector routes reach theirs. Constructor keywords
  override `EMBED_BATCH`, the three flush constants and the walk's page
  size for tests.
- Worker loop: wait on the event, clear it, run one **pass**: (1)
  `requeue_stranded(kb_id)` — any item left at `indexing` by a
  cancel-fallback stop, a mid-item crash of a previous process, or a
  killed worker goes back to `pending`, so "resumes rather than restarts"
  holds at runtime and not only at boot (Architect cycle 2, medium); (2)
  for each folder item of the KB, walk + reconcile (DD-3, folder status
  cycling); (3) page `list_by_status(kb_id, "pending", limit=500,
  type="file")` and `index_item` each, keeping a per-pass set of item ids
  already attempted so a row that fails to leave `pending` (a caught
  `KBItemTransitionError`, a vanished row, a `should_stop` mid-item) is
  not retried within the pass, **and exiting the drain when a page
  contains no un-attempted ids** — not when it is empty, since a skipped
  row sits at the head of the `created_at`-ordered window forever
  (Architect cycle 3, high) — folders never enter the page
  (they are walked from `list_folders`, never extracted) and `url` items
  never enter it (dormant); without the type filter and the attempted set
  one dormant `url` item would spin the drain forever and `/status` would
  never reach `idle` (Architect cycle 2, high); (4) final flush; back to
  waiting. New items created mid-pass are picked up because the loop
  re-queries until empty.
- **Long-lived on purpose**: Flight 4's watcher and periodic reconciliation
  only need `request_index(kb_id)`; the loop shape does not change. No
  backoff supervisor loop (a connector reconnects to a remote; an indexer
  fails per item): an unexpected exception escaping the pass is logged
  with the traceback, the entry's state becomes `stopped`, and the next
  `request_index` restarts it.
- Lifespan: the manager is constructed (and assigned to the lifespan's
  `global _indexing_manager`, the `app.py:319-325` connector shape)
  **before** its guarded `start_all` block, so the shutdown drain — which
  reads that local global, not the module accessor — runs even when
  startup failed, and so the drain-order test, whose `MagicMock`
  connection makes any repository call raise, still reaches the drain
  step (Architect, medium; wording corrected at Leg 3 design review: the
  accessor publication is for the routes, the local global is what the
  drain reads). `start_all()` runs after the
  embedding warm-up scheduling (`app.py:328-341`): `requeue_stranded()` across all knowledge bases
  (one bulk UPDATE — the DD-5 of Flight 2 requeue edge, the resume-not-
  restart primitive), write the vector-store record if absent (DD-5),
  then for every knowledge base that has at least one `folder` item or any
  `pending` item, `start` + `request_index`. An operator with no knowledge
  bases pays nothing (the embedding warm-up gate already established that
  rule). Own `try/except` block so a failure cannot kill startup.
- Shutdown: `drain()` runs right after the in-flight task gathers
  (`app.py:345-365`) and before the reaper drain. **The manager, not the
  worker, performs the final flush**: `stop(kb_id)` stops the worker
  cooperatively (above), then — from the lifespan's own uncancelled task
  — runs `store.flush(kb_id)` under `asyncio.wait_for(…,
  SHUTDOWN_FLUSH_TIMEOUT = 20 s)` and flips that entry's `awaiting_flush`
  items `indexing → indexed` only if the flush completed. `drain()` runs
  every knowledge base's `stop` **concurrently** (`asyncio.gather`), not
  the `ConnectorManager.drain` serial `for`, so the whole drain is bounded
  by 20 s + 20 s = 40 s regardless of KB count — under the desktop
  launcher's 60 s `thread.join` (`interfaces/desktop/shell.py::
  _graceful_shutdown`), which would otherwise abandon the process mid-drain
  exactly when items await flush (Architect cycle 3, medium); any exception
  from that flush (a timeout, a `VectorStoreStaleError` — a rebuild is not
  an option at shutdown) is caught and logged, and the awaiting items are
  left `indexing` for the next startup's requeue (Architect cycle 2,
  medium). A flush inside
  the worker's `except CancelledError` would be aborted by any second
  cancellation (uvicorn's shutdown timeout, the desktop launcher's 60 s
  join in `interfaces/app.py::_graceful_shutdown`) and strand every
  awaiting item (Architect, medium). `_save_atomically` is crash-safe
  (tmp + `os.replace`), so a save cut off by process exit leaves the
  previous sidecar intact and a `.tmp` the next save overwrites. Nothing
  else closes the vector store at shutdown today (`get_vector_store()`
  has no shutdown hook — recorded, not fixed here); the manager's drain is
  where dirty indexes get saved. The lifespan drain-order test
  (`tests/test_mcp_pool.py:616` region) gains a `_FakeIndexingManager`
  alongside `_FakeConnectorManager` and asserts the new drain's position.
- Route integration: `create_kb_item` (folder) → `request_index`;
  `delete_knowledge_base` → `stop(kb_id)` **before** the repository delete
  (so no worker is mid-item on rows being cascaded), then the existing
  `delete_kb`; `delete_kb_item` for a `folder` → `stop`, delete,
  `request_index` (the remaining folders re-walk; a standalone `file` delete
  needs no stop — the worker's `KeyError`/`KBItemTransitionError` on a
  vanished row is caught per item). `POST …/reindex` (DD-8) →
  `request_index` (default) or `requeue_for_reindex` then `request_index`
  (`scope=all`).
- Test seam: every pipeline and manager test runs against
  `StubEmbeddingBackend` (Flight 2's convention — real loads stay in
  `tests/test_doctor_embedding_model.py`), a real `UsearchStore` on the
  `isolated_db` fixture's `tmp_path` data dir, and generated folders under
  `tmp_path`. The manager's tests use small flush constants and a
  `wait_until_idle(kb_id)` test helper (an event the worker sets at the
  end of a pass) so no test sleeps.

**DD-8 — Four routes: a per-KB status projection, whole-KB re-index, chunk read-back, source read-back**
- `GET /api/knowledge-bases/{kb_id}/status` → `{"items": {"pending": n,
  "indexing": n, "indexed": n, "failed": n}, "folders": [{"id", "path",
  "status", "indexed_at", "error"}], "chunks": n, "indexer": "idle" |
  "running" | "rebuilding" | "stopped"}`. The four counts are **file items
  only** (`count_by_status(kb_id, type="file")`) so Flight 6's inventory
  never renders the folder as a document; each folder's own walk status is
  listed separately (Architect Q3). `count_for_kb` supplies `chunks`,
  `manager.state` the indexer word (`idle` when the KB has no worker
  entry). This is the behavior test's primary
  observable (DD-9). 404 on an unknown KB.
- `POST /api/knowledge-bases/{kb_id}/reindex?scope=changed|all` (default
  `changed`; 422 for any other value) — operator's call at design review
  (2026-09-15). `changed` is a reconcile pass: `request_index` alone, so
  new, edited and deleted files are picked up by the DD-3 walk and
  unchanged content is not re-embedded. `all` is the recovery hammer:
  `requeue_for_reindex` (every `indexed|failed` **file** item → `pending`;
  folders and `indexing` items untouched) then `request_index`, so every
  file is re-extracted and re-embedded. Responds 202 `{"scope": …,
  "requeued": n}` (`n` = 0 for `changed`). Rebuilding a stale sidecar is
  *not* this — it is DD-6's automatic path — but `scope=all` re-upserts
  every vector, so it also heals a sidecar an operator suspects.
- `GET /api/knowledge-bases/{kb_id}/items/{item_id}/chunks?offset=0&limit=100`
  → `[{"id", "seq", "char_start", "char_end", "text"}]` in `seq` order;
  `limit` 1–1,000 (422 outside), the R8 scoping rule (an item of another
  KB reads as 404).
- `GET /api/knowledge-bases/{kb_id}/items/{item_id}/source` → `{"path",
  "size_bytes", "content_hash", "stale", "text"}` — the extracted text
  re-run through the item's extractor on demand (never stored: chunks are
  the stored form and offsets index into exactly this text), `stale` true
  when the fresh sha256 differs from the stored `content_hash` (the next
  walk will requeue it; the operator sees why offsets may not line up).
  404 if the item or the file is gone; 422 for a `url` or `folder` item or
  a `file` item with no registered extractor (a standalone `.png` item
  created directly); the DD-5 size cap bounds the response. **Operator's bar, set at
  planning**: no separate read-back cap — the file size cap is the cap.
- Contract recorded for the behavior spec and the HAT (DD-10): route
  paths above, the status body's four item keys, its `folders` list and
  four indexer states, the `scope` values,
  the chunk row's five keys, the source body's five keys, the 202/409/422
  codes named here. A HAT change to any of these is a spec re-author, not
  an inline fix.

**DD-9 — Behavior test `kb-folder-index-round-trip`: shell + http + filesystem apparatus against a dev instance on 8485 with a scratch data directory**
- Act path: `curl` with the long-lived credential (CLAUDE.md's
  behavior-test credential convention) against `POST /api/knowledge-bases`,
  `POST …/items` (folder), `POST …/reindex`; the filesystem apparatus
  generates the fixture folder under a scratch path and later adds, edits
  and deletes files in it. Read path: `GET …/status` polled as the wait
  point, `GET …/items` for per-item status and `error`, `GET
  …/items/{id}/chunks` and `…/source` for read-back — every assertion
  is a field in one of those bodies, all of which exist by Leg 3.
  **Both axes audited**: the apparatus can act (routes are operator-callable
  with a bearer credential, verified against `api.py`'s existing item
  routes) and can observe (the status projection is added specifically so
  the test never reads the database).
- The resume proof is seeded, not raced: with the instance stopped, the
  Executor sets one `indexed` item to `indexing` directly in the scratch
  database (`[mixed-frame]`, justified: there is no user-facing way to
  strand an item, and racing a kill against a seconds-long index is a
  flake by construction), restarts the instance, and observes through
  `…/status` that `indexing` returns to zero and the item is `indexed`
  again. A live-kill variant is listed as optional.
- Preconditions name the port, the scratch data directory, the start
  command and the active probe (`GET /api/live`). Never 8484, never the
  operator's default data directory.
- Spec drafted at planning (`tests/behavior/kb-folder-index-round-trip.md`,
  status `draft`); premise-audited by the Leg 4 Developer before its first
  run, per the authoring guide.

**DD-10 — HAT leg: optional, last, API-driven, sized to this flight**
- Operator's call at planning: behavior test **plus** a HAT leg. The HAT
  walks the operator through registering a folder of their own choosing
  on the dev instance, watching `…/status` move, reading a chunk and its
  source, editing and deleting a file and requesting a re-index, and
  reading a failure (an over-cap file). Look-and-feel here means response
  shapes and error messages; anything that adds behaviour routes through
  the fix-vs-feature gate. DD-8's contract is what a HAT change must
  re-author rather than patch. Another state the operator will not be
  looking at: the worker mid-pass while they call `DELETE` on the KB — the
  walk includes it.

**DD-11 — No closure change; one frozen run at flight close, budgeted as a diagnostic**
- The flight adds no dependency (`hashlib`, `os.walk`, `asyncio` are
  stdlib; `usearch`, `model2vec`, `numpy` are already in). New packages
  `the_one/knowledge/extractors/` are reached by ordinary imports, so no
  `hiddenimports` entry is needed (`the_one.embeddings` needed one because
  it is reached only through `importlib.resources`). `pip-audit` runs on
  the unchanged export anyway (the mission's by-hand gate list). One `fly
  execute` at flight close proves `RESULT: PASS` with the existing eight
  gates; the Flight 2 debrief's call stands — plan for an iteration if it
  fails, do not move the gate earlier.

**DD-12 — Measurements: the empty-transaction cost is recorded now and confirmed in Leg 2 at the pipeline's batch shape; the Windows 1M re-measure leaves the flight**
- Planning figures on this host (Linux, accelerated numpy, `usearch`
  SIMD): 1,000 empty `write_transaction` round-trips 52 ms (0.05 ms each);
  1,000 vectors upserted in 256-batches 143 ms; `flush` at 1,000 vectors
  3 ms; embedding 3,570 chunks/s at batch 256; `update_status` 0.9 ms; 500
  items in one transaction 3.5 ms. At one empty transaction per 256-chunk
  batch the shim costs ~0.2 ms per 256 chunks against ~72 ms of embedding
  — Flight 2's concern is answered at planning; Leg 2 records the same
  measurement inside the real pipeline (10k chunks through `index_item`)
  so the number lives next to the code that pays it.
- The Flight 2 debrief's Recommendation 5 (re-measure `usearch` build and
  incremental upsert on Windows at 1M once a real corpus exists) needs a
  corpus this flight does not create; it is recorded as a mission open
  question at flight start, with the R6 caveat that the ~2 h / 1M build
  figure is an extrapolation.

### Prerequisites

- [x] Flight 2 merged into `mission/24-knowledge-bases` (PR #197) and the
      squawk turnaround (PR #199) merged; the mission branch is level with
      `main` (0 behind, 26 ahead at planning)
- [x] `KB_ITEM_TRANSITIONS` carries `indexing → pending` and `indexed →
      pending`; `UsearchStore.flush`/`rebuild_from`/`VectorStoreStaleError`
      exist; `save_vector_store_settings` exists with no production caller;
      `count_by_status` and `list_for_item` exist — all verified against
      `0f79f9c`
- [x] Empirical premises verified on this host at planning: per-row commit
      vs batched insert cost, embedding throughput by batch size,
      `chunk_text` cost at 10 MB, `os.walk` symlink behaviour, sha256 cost,
      empty-transaction cost (DD-12)
- [ ] A dev instance for the behavior test and the HAT: `THE_ONE_PORT=8485
      THE_ONE_DATA_DIR=<scratch> make up` reachable, `GET /api/live` 200 —
      probed at Leg 4 start, not assumed
- [ ] Concourse at `localhost:8080`, team `the-one`, `fly` token valid, and
      `windows-worker` healthy — re-verified at flight close before the
      frozen run (the token expired mid-Flight 1)
- [ ] `sqlite3` CLI on the host for the behavior test's seeded-resume step
      (`[mixed-frame]`) — probed at Leg 4 start

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [ ] Prerequisites verified *(dev instance, `fly` token and `sqlite3` CLI are probed at the legs that need them; the code and empirical premises are done)*
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

Ordered so the one shared-interface change to an existing repository lands
first and alone with the pure, testable walk logic; the pipeline lands
against it with the store-Protocol widening it needs; the supervisor and
routes land last, wiring both into the app; and the flight closes on the
behavior test, the by-hand gates and the frozen run before the optional HAT.

**Leg 1 — `folder-registration-and-walk`.** `KBItemRepository` widening
(`delete` covering descendants; `create_many`, `list_children`,
`list_folders`, `list_by_status(limit=)`, `requeue_stranded`,
`requeue_for_reindex`), `KBChunkRepository.list_for_item(limit=, offset=)`
and `iter_for_kb`, `the_one/knowledge/walk.py` (walk, filters, constants,
`plan_reconcile`), the `create_kb_item` folder validation (DD-1, without the
`request_index` call, which needs Leg 3's manager — a named no-op hook
`_after_folder_registered(kb_id)` is left for Leg 3 to fill), the folder-
delete FTS/vector cleanup test, direct unit tests for every new repository
method (their first production consumer is Leg 3), and `SECURITY-MODEL.md`'s
paragraph. **HIGH
risk**: a behavioural change to a shared repository method with a route
consumer, plus the filesystem rules every later flight inherits.

**Leg 2 — `extractor-seam-and-indexer`.** `the_one/knowledge/extractors/`
(Protocol, registry, `TextExtractor`, the stub extractor in tests),
`the_one/knowledge/indexer.py` (`index_item`, the flush-cadence bookkeeping
as a small `FlushPolicy` object with its fake-clock test — Leg 2 owns the
object, Leg 3 owns its caller and the entry's `awaiting_flush` list —
`rebuild_kb`, and the `entry.dirty` reorder in `UsearchStore`), `rebuild_from` widened to an
async iterable and added to the `VectorStore` Protocol with
`tests/test_vector_store.py` updated, the DD-12 in-pipeline measurement
(including per-flush save time) recorded in the flight log, and the "Knowledge indexing" subsection of
`the_one/agents.md`'s Knowledge storage contract (stages, ordering, flush
rule, stale recovery, extractor registry). **HIGH risk**: a shared-interface
change on the vector-store Protocol; the write-ordering invariant is
implemented here for the first time.

**Leg 3 — `indexing-manager-and-routes`.** `the_one/knowledge/manager.py`
(`IndexingManager`, worker loop, cancel-flush, module accessors), lifespan
`start_all`/`drain` wiring with the drain-order test extended, the four DD-8
routes, the `create_kb_item` hook filled, the delete routes' `stop`
integration, `CLAUDE.md` (routes, the operator-only registration note) and
`the_one/agents.md` (manager contract). **HIGH risk**: lifecycle and
state-machine work, lifespan ordering. This is the widest leg; splitting
the four routes into their own leg at design time is expected, not a
deviation (Architect cycle 2).

**Leg 4 — `verify-integration`.** Probe the dev-instance prerequisites;
premise-audit `tests/behavior/kb-folder-index-round-trip.md` against the
landed code (correct the `draft` if the audit finds drift — authoring, not
drift) and run it via `/mission-control:behavior-test`; `make lint`,
`make test-unit` (recorded verbatim), `pip-audit` on the unchanged export;
the frozen `fly execute` run; mission open question recorded for the Windows
1M re-measure. Flight-end review and commit precede the frozen run per the
agentic workflow. A failing behavior test is an unmet criterion: the leg does
not land while it fails.

**Leg 5 — `hat-and-alignment`** *(optional)*. DD-10.

Files affected (planning estimate; legs cite exactly):
`the_one/db/repositories.py`, `the_one/interfaces/web/api.py`,
`the_one/interfaces/web/app.py`, `the_one/vectors/_store.py`,
`the_one/vectors/usearch_store.py`,
`the_one/knowledge/{walk,indexer,manager}.py`,
`the_one/knowledge/extractors/{__init__,text}.py`, `tests/_extractor_stub.py`,
new `tests/test_kb_walk.py`, `tests/test_kb_extractors.py`,
`tests/test_kb_indexer.py`, `tests/test_kb_manager.py`, updated
`tests/test_db_api.py`, `tests/test_db_repositories.py`,
`tests/test_kb_chunks.py`, `tests/test_vector_store.py`, the lifespan
drain-order test, `tests/behavior/kb-folder-index-round-trip.md`,
`CLAUDE.md`, `SECURITY-MODEL.md`, `the_one/agents.md`,
`missions/24-knowledge-bases/mission.md` (open question for the Windows
re-measure; Flight 3 checked off at landing).

### Checkpoints

- [ ] Registering a folder that does not exist, is a filesystem root, or overlaps an existing folder of the same KB is refused with the DD-1 codes; a valid registration stores the canonical path and returns 201
- [ ] Deleting a folder item leaves zero orphan FTS rows (`check_fts()` true) and hands every descendant chunk id to the vector store
- [ ] `walk_folder` on a fixture tree skips dot-entries, the denylisted directories, symlinked files and directories, and unsupported extensions, never yields a path outside the root and never opens a file; `plan_reconcile` classifies new / removed / changed / unchanged correctly (unit-tested, pure); a re-walk of an `indexed`, a `failed` and a `pending` folder all succeed
- [ ] A registered `.stub` extractor indexes a `.stub` file with no change to `indexer.py` (the M7 test)
- [ ] (Leg 2) `index_item` on a fixture file commits chunks + FTS in one transaction, upserts vectors and leaves the item `indexing`; an over-cap file, a binary file and a missing file each land `failed` with the DD-5 messages; a zero-norm chunk is kept in SQLite and absent from the store
- [ ] (Leg 3) an item lands `indexed` with `indexed_at` only after the flush that covers it; a pass with one dormant `url` item, one `folder` item and one file that cannot leave `pending` still terminates and `/status` reaches `idle`; a cooperative `stop` mid-pass finishes the current item and flushes; a cancel-fallback stop leaves the item `indexing` and the next pass requeues it
- [ ] The flush policy's three constants behave as DD-5 states under a fake clock (including: no flush before `10 × last_flush_seconds`); the DD-12 in-pipeline measurement, with per-flush save time, is in the flight log
- [ ] A KB whose sidecar is deleted between passes is rebuilt from `kb_chunks` on the next pass with a warning log, and `count(kb_id)` equals the vector-bearing chunk count afterwards; `rebuild_from` accepts an async iterable and is on the Protocol
- [ ] `IndexingManager.start_all` requeues every `indexing` item to `pending` on startup and finishes them; `stop`/`drain` flush a dirty index from the manager's own task within the timeout and flip the awaiting items; the pending loop skips `folder` and `url` items; the lifespan drain-order test covers the new drain with a fake manager
- [ ] `…/status` reports the four file-item counts, the folders list, the chunk count and the indexer state; `…/reindex` defaults to a walk pass and requeues `indexed|failed` file items only under `scope=all`; `…/chunks` pages in `seq` order with bounded `limit`; `…/source` returns the extracted text with `stale` computed from a fresh hash
- [ ] `knowledge.vector_store` exists after the first index and is not rewritten when present
- [ ] `tests/behavior/kb-folder-index-round-trip.md` passes on the dev instance, including the seeded resume step
- [ ] `make test-unit` green, wall time recorded; `make lint` clean; `pip-audit` clean; frozen `doctor` `RESULT: PASS`

### Adaptation Criteria

**Divert if**:
- The folder-delete cleanup cannot be expressed inside `KBItemRepository.
  delete`'s single `write_transaction` without nesting a guard — that is a
  transaction-model question for the operator, not a leg variation.
- Widening `rebuild_from` turns out to need a store-side change beyond the
  input type (for example, the HNSW build must be batched in a way the
  async iterable cannot express) — reopen DD-6 with the operator.
- Leg 2's extrapolation (DD-12) puts save overhead above ~15 % of build
  time at 1M vectors on Windows, or the re-work window far outside the
  ~2 min / 1M figure recorded in DD-5 — the constants are variations; a change to
  the *shape* of the rule (per-item flush, or flush off the worker) is a
  re-plan.
- The behavior test's seeded-resume step cannot observe the requeue through
  `…/status` (the projection is wrong for it) — fix the projection, not the
  test.
- `RESULT: FAIL` on the frozen run for a reason inside this flight's files —
  iterate as a diagnostic (DD-11); for a reason outside them, raise to the
  operator.

**Acceptable variations**:
- Module and constant names under `the_one/knowledge/`; the exact
  extension allowlist and directory denylist (recorded in the log)
- The three flush constants and `EMBED_BATCH`, within the DD-5 bar
- The status route's `indexer` vocabulary, as long as the behavior spec is
  re-authored with it before its first run
- `walk_folder` returning a generator instead of a list (Architect
  suggestion; the reconcile planner consumes either)
- Splitting Leg 3's routes into a separate leg if the manager's design
  review asks for it

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned
> and created one at a time as the flight progresses.

- [x] `folder-registration-and-walk` — repository widening (descendant
      cleanup in `delete`, bulk create, children/folders listing, bulk
      requeues, chunk paging and KB iteration), `walk.py` with the filter
      rules and pure reconcile planner, folder registration validation,
      `SECURITY-MODEL.md`. **HIGH risk** (shared repository method behaviour
      change; the filesystem rules).
- [x] `extractor-seam-and-indexer` — extractor Protocol + registry +
      `TextExtractor` + test stub, `index_item`, the flush policy,
      `rebuild_kb`, `rebuild_from` widened and on the Protocol, the DD-12
      measurement, `agents.md` indexing contract. **HIGH risk**
      (shared-interface change on the vector-store Protocol; first
      implementation of the write-ordering invariant).
- [x] `indexing-manager-and-routes` — `IndexingManager`, lifespan start/
      drain with the drain-order test, the four routes, delete-route
      integration, first-index settings record, `CLAUDE.md` and `agents.md`.
      **HIGH risk** (lifecycle; lifespan ordering).
- [x] `verify-integration` — dev-instance probes, behavior-test premise
      audit and run, by-hand gates, frozen run, mission open question.
- [ ] `hat-and-alignment` *(optional)* — guided API walk on the dev instance
      per DD-10.

---

## Post-Flight

### Completion Checklist

- [ ] All legs completed
- [ ] Code merged *(PR into `mission/24-knowledge-bases` — no CI lane runs on it; gates run by hand and recorded in the flight log)*
- [x] Tests passing
- [x] Documentation updated — `CLAUDE.md` (the four routes, folder registration is operator-only, the resume behaviour), `SECURITY-MODEL.md` (knowledge-base indexing paragraph), `the_one/agents.md` (Knowledge indexing contract: walk rules, extractor registry, pipeline stages and ordering, flush rule, stale recovery, manager lifecycle), `missions/24-knowledge-bases/mission.md` (Windows 1M re-measure open question; `parent_id` and file-skip open questions resolved)

### Verification

The flight succeeds when: `make test-unit` is green with the walk, extractor,
indexer, manager and route suites included and real model loads still
confined to `tests/test_doctor_embedding_model.py`; `make lint` and
`pip-audit` are clean; the behavior test
`kb-folder-index-round-trip` passes on a dev instance (register → indexed →
read back → edit/add/delete reflected by re-index → seeded resume →
failure visible), with its run log committed; and `the-one.exe doctor`
returns `RESULT: PASS` in a bundle frozen on `windows-worker`.

**Behavior test**: `tests/behavior/kb-folder-index-round-trip.md` (DD-9),
run in Leg 4 via `/mission-control:behavior-test kb-folder-index-round-trip`.

**Known lane conditions** carried from the Flight 2 debrief: `make
test-unit` ran 499 s at 4,370 tests at Flight 2 close and 4,431 after the
squawk turnaround; this flight adds five suites and must keep real model
loads to the existing file. Debrief metrics use `make test-unit` verbatim —
an explicit `-m` replaces `addopts` and lets the `requires_bwrap` tests run.
The Studio browser lane's standing flake (squawk 0035) is untouched — no
browser test changes. Squawk 0050 (Studio save clobbers `kb_ids`) is not in
this flight's path; it becomes load-bearing at Flight 5.
