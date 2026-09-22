# Flight: Storage and Embedding Foundation

**Status**: completed
**Mission**: [Knowledge Bases](../../mission.md)

## Contributing to Criteria

- [ ] The embedding backend is bundled, local and non-LLM; works on a fresh install with no account, no network, no external service; no file contents leave the machine *(this flight lands the seam and its production backend; Flight 1 already proved the model packages and loads offline)*
- [ ] Retrieval combines semantic and keyword matching *(partial — this flight lands both substrates, the vector store and the FTS5 index over chunk text, and their two query primitives; the fusion policy is a later flight's design decision)*
- [ ] A new file-format handler or a different vector store can be introduced without modifying the indexing pipeline *(partial — the vector-store seam; the extractor seam is Flight 3)*
- [ ] Operator can register a folder … and see each discovered item's index status including failures *(partial — the item lifecycle: status vocabulary, error column, transitions, routes; the folder type and the pipeline that drives transitions are Flight 3)*
- [ ] Existing installs upgrade with no data loss, the unit gate stays green, and the frozen Windows installer still builds and runs *(the v40 migration, proven against rewind/rerun; one frozen run at flight close)*

Reconnaissance-retired or re-scoped source items (see the flight log's
Reconnaissance Report for evidence): R2 mission citation corrected in
`mission.md`; R11 DD-6 rewrite scoped to the embedding probe only; R16 `kb__`
tool gating and R17 Studio `kb_ids` clobber (squawk 0050) are outside this
flight.

---

## Pre-Flight

### Objective

Give the knowledge-base scaffold a working storage and embedding foundation
that every later flight builds on and none has to redesign: a v40 migration
that turns `kb_items` into a real item lifecycle and adds chunk storage with an
FTS5 index; an embedding seam whose production implementation is the bundled
`potion-retrieval-32M` model landed in Flight 1; a vector-store seam with
`sqlite-vec` and `usearch` both behind it under the mission's vectors-and-ids-
only contract; a benchmark that measures the two stores on Windows at the
corpus ceiling so the operator can choose one on evidence; and the closure
change that removes the loser. App-wide embedding and chunking settings ship
with defaults and an API, no UI. No agent tool, no Studio surface, no
indexing pipeline: those are Flights 3–6.

### Open Questions

- [x] Embedding seam shape and who owns the DD-5 offline guards → DD-1
- [x] Whether a second production embedding backend ships → DD-2 (no; mission amended)
- [x] Vector-store seam contract, `upsert` semantics, write ordering, where each backend persists → DD-3
- [x] Vector dtype at rest → DD-4 (measured, then chosen)
- [x] v40 schema: item lifecycle, chunk table, FTS5 sync mechanism, id stability → DD-5
- [x] Where the app-wide embedding and chunking settings live → DD-6
- [x] Chunking policy and defaults → DD-7
- [x] Benchmark apparatus: act path, read path, platform, RAM fallback → DD-8
- [x] How the store choice is made and what the closure removes → DD-9
- [x] Loading the `vec0` extension: where and when → DD-10
- [x] Which probes join the `doctor` gate, and what the rewritten probe changes → DD-11
- [x] Whether search fusion is in scope → DD-12 (no)
- [x] How writes stay atomic on one shared connection → DD-13
- [x] **Latency bar, set by the operator at planning (2026-09-14), before any number exists**: **p95 ≤ 250 ms** for one k = 10 query on Windows at the largest measured N (3M, one KB at the corpus ceiling). DD-9 input #1 is judged against this figure. (Architect S2: the numbers may pre-decide the flight, so the bar had to exist first.)
- [ ] **Deferred to the decision checkpoint between Leg 5 and Leg 6**: which store, which dtype — answered by the benchmark, recorded by the operator in the flight log before Leg 6 is designed

### Design Decisions

**DD-1 — Embedding seam: a `runtime_checkable` Protocol in `the_one/embeddings/`, one production backend, one test-only backend, loaded once per process**
- Shape: `EmbeddingBackend` Protocol with `model_id: str`, `dim: int`, and
  `embed(texts: Sequence[str]) -> EmbedResult` where `EmbedResult` carries
  `vectors: np.ndarray` (`float32`, shape `(len(texts), dim)`, unit-norm) and
  `truncated: int` — the count of inputs the tokenizer cut at `max_length`
  (Architect S7: model2vec pre-truncates silently by characters and then by
  tokens, so a long chunk is stored and keyword-indexed whole but embedded
  only up to its first 512 tokens; the seam makes that visible so Flight 3
  can log it). **How it is computed and what it costs**: `encode()` returns
  vectors only, so the backend runs `model.tokenize(texts, max_length=None)`
  and counts lengths above 512 — a second tokenisation pass the Architect
  measured at ~27 % of embed wall time. The backend applies it only to
  inputs longer than 512 characters (a text of ≤ 512 characters cannot
  exceed 512 tokens), so at DD-7's defaults the cost is near zero and the
  27 % is the worst case at the 2,000-char ceiling. `truncated` counts the
  *token* cut; model2vec's character pre-slice (`max_length × median token
  length`, 3,584 characters for this model) is inert below that bound and
  never reached at DD-7's ceiling. Sync and CPU-bound; callers run it under `asyncio.to_thread`.
  Thread safety verified by the Architect against the installed source:
  `StaticModel.tokenize` never mutates tokenizer state and `encode_batch_fast`
  is the Rust thread-safe path. Structural satisfaction per
  `structural-Protocol-satisfaction`; no base class.
- Production backend `LocalStaticBackend` (`the_one/embeddings/local.py`)
  wraps exactly the load path Flight 1's probe already proved
  (`the_one/diagnostics.py:_probe_embedding_model`, `:702-753`): resolve the
  packaged directory via `importlib.resources.files("the_one.embeddings")`,
  assert the directory and `model.safetensors` exist **before** any loader
  call, force offline via the two-part `_force_hf_offline` (env var **and**
  the already-bound `huggingface_hub.constants.HF_HUB_OFFLINE`), then
  `StaticModel.from_pretrained(path)`. The DD-5 guards move **into the backend**
  so they protect production, not only the probe; the probe then constructs a
  **fresh** backend instance (never the singleton — DD-11) and calls it.
- `encode()` is called with `use_multiprocessing=False` and an explicit
  `max_length=512` (R20). model2vec's default spawns a process pool above
  10,000 texts; a fork pool inside a uvicorn worker or a PyInstaller bundle is
  a hazard, and 10k-text batches are exactly what Flight 3 will send. The
  model's float16 output (its `config.json` says `"embedding_dtype":
  "float16", "normalize": true`) is upcast to float32 at the seam boundary;
  the backend does **not** re-normalise — the model already does, and a norm
  outside tolerance is a defect to report, not to hide. The tolerance is
  **1e-3**: float16 output upcast to float32 measures max |1 − ‖v‖| = 1.83e-4
  on the bundled model (Architect), so "unit-norm" in the Protocol docstring
  means unit-norm within float16 tolerance, never exact. The store decides
  what it keeps (DD-4).
- Lifecycle: `get_embedding_backend()` returns a process-wide singleton built
  from the `knowledge.embedding` setting (DD-6); first call loads the model
  (~250 MiB whole-process, Flight 1's figure). Warm-up: a `lifespan` task
  next to the existing `create_task` loops (`the_one/interfaces/web/app.py:
  249-260`), registered **after** `ConnectorManager.start_all`, running the
  load under `asyncio.to_thread`, and **only when at least one knowledge base
  exists** (one `SELECT count(*)`) — an operator who never creates a KB never
  pays 250 MiB (Architect Q4). The same warm-up is kicked, once, by
  `create_knowledge_base` (`api.py:1387`), so the operator creating their
  *first* KB after a cold start does not pay the load inside their first
  indexing request either — the case the gate would otherwise miss. Tests reset the singleton via
  `_reset_for_test()`, mirroring `the_one/platform/sandbox/factory.py:62`'s
  `_reset_selection_log_state`.
- Test-only second implementation `StubEmbeddingBackend` in
  `tests/_embedding_stub.py` (deterministic, hash-seeded unit vectors of a
  chosen `dim`), following the `FakeLLM` / `StubTool` precedent in
  `tests/conftest.py`. Every seam consumer's unit test runs against the stub.
  Real loads stay confined to `tests/test_doctor_embedding_model.py`, which
  already performs two today (the real-load test and the offline-capture
  test); Leg 3 adds none elsewhere. This is what keeps the seam from taking
  the shape of its only production backend.
- Trade-off: a Protocol plus a stub is lighter than a second production
  backend and proves less. Accepted — the mission was amended at this
  flight's planning to make non-LLM local embeddings the product.

**DD-2 — No provider-delegating backend; the mission is amended, not this flight worked around**
- The operator settled on non-LLM local embeddings as the product. The
  mission's two-production-backends rule, its "available but never silent"
  constraint, the backend-choice success criterion and the Ollama environment
  requirement were amended on 2026-09-14 to record that. A remote backend
  remains possible behind DD-1's seam as a future mission.
- Consequence for this flight: the `knowledge.embedding` setting (DD-6) has
  exactly one valid `backend` value, `"local"`, and exactly one valid
  `model_id`, the bundled one; validation rejects anything else with 422 and
  a message naming the amendment (Architect Q1 — with one model there is no
  reachable "change the model while chunks exist" case, so the 409 re-index
  gate is documented as the shape a second bundled model would need, not
  built as unreachable code).

**DD-3 — Vector-store seam: vectors and stable integer ids only, `upsert` is delete-then-insert, one write ordering both backends must satisfy**
- Contract (`the_one/vectors/`): `VectorStore` Protocol with
  `open()`, `upsert(kb_id, ids: Sequence[int], vectors: np.ndarray)`,
  `delete(kb_id, ids)`, `delete_kb(kb_id)`, `query(kb_id, vector, k) ->
  list[tuple[int, float]]` (id, cosine distance), `count(kb_id)`, `close()`.
  Ids are `kb_chunks.id` values (DD-5: `AUTOINCREMENT`, never recycled) —
  `usearch` keys are `uint64` and `vec0` rows are rowids, so neither backend
  needs an id mapping table, **and** a stale entry in either index can only
  ever point at a deleted id, never at different text. No text, no metadata,
  ever crosses the seam (mission constraint).
- **`upsert` means: remove any of `ids` already present, then insert.**
  Neither backend has a native upsert — `INSERT OR REPLACE` into `vec0` fails
  its primary-key constraint and `usearch.Index.add` raises on a duplicate key
  (Architect, verified). The shared Protocol test suite includes "upsert an id
  that already exists" so the two implementations cannot diverge where Flight
  3's re-index path hits them.
- **Write ordering invariant (Architect S4)**, stated here because nothing in
  this flight writes a vector in production and Flight 3 would otherwise
  invent it under pressure: chunks and their FTS rows commit first; vectors
  are written after; an item's status flips to `indexed` only once vectors
  have landed. A crash between the two leaves an item `indexing` (requeued by
  DD-5's transition table), never an `indexed` item with no vectors.
  Both stores acquire DD-13's write lock internally for their own writes;
  a caller never wraps a store call in its own transaction (the guard would
  raise on re-entry). Chunks + FTS and vectors are therefore always two
  transactions, which is what the ordering invariant assumes.
- `SqliteVecStore`: one shared virtual table in the main database,
  `kb_vectors USING vec0(kb_id TEXT partition key, embedding <dtype>[512]
  distance_metric=cosine)`, created by the store's `open()` with
  `CREATE VIRTUAL TABLE IF NOT EXISTS` — **not** by the v40 migration, because
  the column dtype is DD-4's measured choice and the table only exists when
  this backend is the configured one. `open()` loads the extension (DD-10)
  and then compares the live DDL (`SELECT sql FROM sqlite_master WHERE
  name='kb_vectors'`) against the `knowledge.vector_store` record — the
  record is the thing that drifts, and `IF NOT EXISTS` would silently keep an
  old-dtype table (Architect S6). Partition-keyed queries, delete-by-rowid
  and whole-partition delete verified on this host against `sqlite-vec` 0.1.9.
- `UsearchStore`: one HNSW index per knowledge base, persisted as a sidecar
  file `{data_dir}/vectors/{kb_id}.usearch`, with a store-owned registry table
  `kb_vector_index(kb_id TEXT PRIMARY KEY, path TEXT, count INTEGER,
  generation INTEGER, updated_at TEXT)` created by `open()`. Store-owned
  rather than v40-owned on purpose (Architect Q3): if `usearch` loses, a v40
  table for it would be a dead table in a frozen migration forever; if it
  wins, Leg 6 moves the DDL into a v41 block so the fresh-DB shape tests see
  it. A BLOB-in-SQLite layout was considered and rejected on a measured limit:
  this build's `SQLITE_MAX_LENGTH` is 1,000,000,000 bytes, and one KB at the
  corpus ceiling (~3M chunks × 512 dims × 2 bytes) is ~3 GB before the graph.
  Crash consistency: `kb_chunks` is the source of truth and the sidecar is a
  cache; `generation` is bumped after every successful `save()`, and a
  mismatch (or a missing file) on `open()` marks the KB for rebuild. The
  rebuild itself (re-embed every chunk) is Flight 3's pipeline — this flight
  ships the detection and a `rebuild_from(ids_and_vectors_iter)` method, and
  the benchmark records `save()`/`restore()` time at scale so Leg 6's decision
  prices it.
- Selection: `get_vector_store()` reads the `knowledge.vector_store` setting
  (DD-6) and dispatches like `create_pty_session` (`the_one/platform/pty.py:
  130-163`), lazy-importing each backend. It resolves `data_dir` **at
  `open()`**, not at construction, and exposes `_reset_for_test()` — a
  singleton captured before a test's `data_dir` monkeypatch would otherwise
  write sidecars into the operator's real data directory (Architect S5).
  Until Leg 6 the setting's default is whichever backend the benchmark is
  exercising; after Leg 6 there is one backend and the dispatcher keeps its
  shape for the future.

**DD-4 — Vector dtype at rest is measured, not assumed; the float32 cell is understood to store upcast float16**
- The arithmetic the choice rests on, at 512 dims: float32 2,048 B/vector,
  float16 1,024 B, int8 512 B. At the corpus ceiling (~3 GB raw text, ~1,000
  char chunks → ~3M chunks) that is ~6 GB / ~3 GB / ~1.5 GB of vectors. This
  is the figure Flight 1's debrief said to compute directly rather than read
  off the 247.1 MiB whole-process peak RSS. The Architect measured 2.08 KB
  per float32 vector on this host, confirming the arithmetic.
- `vec0` has no float16 column type: `sqlite-vec` offers `float[N]` (float32)
  and `int8[N]` (bound via `vec_int8(?)`, verified on this host — a bare blob
  bind is misread as float32). Because the model emits float16, **sqlite-vec's
  float32 cell costs twice the bytes for zero fidelity gain** (Architect S3);
  the real quantisation question is float16 versus int8, and sqlite-vec's
  lack of an f16 column is a substantive cost in its column of the table, not
  a formatting detail. `usearch` offers `f16` and `i8` natively. The benchmark
  (DD-8) measures four cells — sqlite-vec f32 and i8, usearch f16 and i8 —
  with recall@10 against exact float32 brute force as the quality floor. A
  cell below recall 0.95 on the real corpus is disqualified.
- Early signal, recorded so nobody is surprised: the Architect's 200k-vector
  probe on the accelerated Linux build put sqlite-vec f32 and i8 at ~121 ms
  and ~125 ms p50 for k = 10 in one partition — int8 buys 4× disk and no
  latency, and linear extrapolation to 3M is ~1.8 s before the Windows
  `simd=serial` penalty. The bar in the open question above exists so this
  number is judged, not merely observed.
- The chosen `(backend, dtype, dim, model_id)` is written to the
  `knowledge.vector_store` setting so a later mismatch is detectable at
  `open()` (DD-3) rather than as silent garbage.

**DD-5 — v40: `kb_items` rebuild with a lifecycle, `kb_chunks` with `AUTOINCREMENT` ids and an external-content FTS5 index kept in sync by the repository, not by triggers**
- `kb_items` is rebuilt via the v37 template (`schema.py:2141-2212`): same-name
  rewrite through `kb_items_new`, guarded on column absence
  (`"content_hash" not in PRAGMA table_info(kb_items)`) — the v37 guard shape;
  v39 (`:2308-2312`) guards on table presence and rewrites unconditionally,
  which also works but re-runs the copy on every rewind. New shape: `type TEXT
  NOT NULL CHECK (type IN ('file','url','folder'))`, `status TEXT NOT NULL
  DEFAULT 'pending' CHECK (status IN ('pending','indexing','indexed',
  'failed'))`, plus `error TEXT`, `content_hash TEXT`, `size_bytes INTEGER`,
  `mtime REAL`, `updated_at TEXT NOT NULL DEFAULT (datetime('now'))`,
  `indexed_at TEXT`. `parent_id` is carried through unchanged — its fate is
  Flight 3's open question (R3). Existing rows migrate with `status = CASE
  WHEN status IN (…) THEN status ELSE 'pending' END`: the old column was
  unconstrained, so a non-vocabulary value is mapped rather than left to fail
  the CHECK. **Both CHECKs are frozen inline literals in the v40 block**, never
  derived from a Python tuple — `schema.py:22-28` records that derivation was
  retired for CHECKs because history is append-only (Architect). The model's
  `Literal` and a `_kb_types.py` tuple may share a source with an import-time
  assert (the `models.py:71-76` pattern), pinned by a fresh-DB "CHECK rejects a
  bogus value" test, never by a derived-SQL test. `PRAGMA foreign_keys=ON` is
  re-issued after the script (the v37 comment at `:2181-2184` is load-bearing:
  forgetting it leaves the singleton connection with FKs off for the process).
  A one-line comment notes that `executescript` must start with no open
  transaction that touched the FTS table (per-block `commit()` guarantees it
  today).
- **Transition table** (enforced in `KBItemRepository.update_status`, raises
  on anything else): `pending→indexing`, `indexing→indexed`,
  `indexing→failed`, `indexing→pending` (**requeue** — a process killed
  mid-index must not strand an item forever; Flight 3's "resumes rather than
  restarts" needs a startup reconciliation that uses exactly this edge;
  Architect), `failed→pending` (retry), `indexed→pending` (re-index). The
  retry route accepts both `failed` and `indexing` — the same operator
  intent, and until Flight 3's startup reconciliation exists it is the only
  way out for an item stranded by a kill (Architect, low).
- `kb_chunks(id INTEGER PRIMARY KEY AUTOINCREMENT, item_id TEXT NOT NULL
  REFERENCES kb_items(id) ON DELETE CASCADE, kb_id TEXT NOT NULL REFERENCES
  knowledge_bases(id) ON DELETE CASCADE, seq INTEGER NOT NULL, text TEXT NOT
  NULL, char_start INTEGER NOT NULL, char_end INTEGER NOT NULL, created_at
  TEXT NOT NULL DEFAULT (datetime('now')), UNIQUE (item_id, seq))` plus
  `idx_kb_chunks_kb_id`. **`AUTOINCREMENT` is load-bearing** (Architect, high):
  a plain `INTEGER PRIMARY KEY` recycles the highest deleted rowid, and
  `replace_item_chunks` deletes-and-reinserts on every re-index, so a sidecar
  one generation behind or a missed `vec0` delete would map a recycled id to
  different text — a silent wrong answer DD-3's generation check cannot see.
  With `AUTOINCREMENT` a stale id can only ever be a deleted one. Cost: one
  `sqlite_sequence` row. Integer ids on purpose: FTS5 external-content tables
  key on an integer rowid, and both vector backends key on integers. The v36
  new-table template (`schema.py:2100`) applies.
- `kb_chunks_fts USING fts5(text, content='kb_chunks', content_rowid='id',
  tokenize='porter unicode61')`, `CREATE VIRTUAL TABLE IF NOT EXISTS`
  (verified idempotent). External-content, so chunk text is stored once.
  **Sync is explicit in the repository**, inside the same transaction as the
  `kb_chunks` write: insert FTS rows after inserting chunks; issue the
  `('delete', rowid, text)` command before deleting chunks (verified). No
  triggers — and the hazard is worse than the migration report stated
  (Architect S1, verified): a dangling FTS trigger makes `ALTER TABLE … RENAME`
  fail on **any unrelated table**, so one orphaned trigger would break every
  future migration's rebuild ceremony, not only a rebuild of `kb_chunks`.
  Two facts recorded next to that decision: (a) an FK cascade from
  `knowledge_bases` or `kb_items` **would** fire an `AFTER DELETE` trigger,
  so choosing repository sync makes the repository the only thing between a
  cascade and orphan FTS rows — `KnowledgeBaseRepository.delete` and
  `KBItemRepository.delete` therefore call the chunk repository's FTS cleanup
  and the vector store's `delete`/`delete_kb` explicitly, and a raw
  `DELETE FROM kb_items` anywhere else is a defect by convention; (b) the
  symptom of a miss is not stale results but `DatabaseError: database disk
  image is malformed` on the next MATCH **that selects the FTS `text`
  column**, which reads to an operator like corruption — `search_keyword`'s
  own query selects only rowid and score and joins `kb_chunks`, so it
  silently filters an orphaned index row instead (Leg 2 design review); the
  desync is therefore invisible until `check_fts()` (the two-argument
  `integrity-check`) is run. So the repository also ships `rebuild_fts()` (`INSERT INTO
  kb_chunks_fts(kb_chunks_fts) VALUES('rebuild')`, verified to recover) and
  `check_fts()` (`'integrity-check'`), and a test proves a KB delete leaves
  zero orphan FTS rows and zero vector rows.
- Indexes `idx_kb_items_kb_id (kb_id)`, `idx_kb_items_kb_status (kb_id,
  status)`, `idx_kb_chunks_kb_id` are created after the script. (The
  `column-aware-index-create-for-rewind-paths` convention is scoped to
  indexes whose columns evolved across prior migrations; v40's are new on a
  stable column set, so it does not bite — creating them outside the script
  is harmless and keeps the v21 shape available if a later migration renames
  a column.)
- Ordering inside the v40 block: the `kb_items` rebuild script first, then
  `kb_chunks`, then the FTS table, then indexes, then the stamp last.
  Migration tests follow the `TestSchemaV39` shapes at
  `tests/test_db_migration.py:4439-4519`: fresh-DB post-shape, idempotent on
  double ensure, tolerant of the `>= 7` rewind-rerun, both CHECKs accept the
  new values and reject a bogus one, `PRAGMA foreign_keys == 1` after, an
  existing pre-v40 row with `status = NULL` and one with a junk status both
  land as `pending`, `AUTOINCREMENT` proven by delete-then-insert yielding a
  fresh id, and `sqlite_master` membership assertions (house style;
  FTS5 shadow tables now exist). `tests/test_schema.py`'s frozen V1 DDL copy
  is untouched. `CURRENT_VERSION = 40` and the literal assertion at
  `tests/test_db_migration.py:4389` are updated.
- No vec0 DDL in the migration (DD-3). The Architect verified that a database
  carrying a `vec0` table opens, migrates, `VACUUM`s and runs the full
  rebuild ceremony without the extension loaded — only queries against the
  `vec0` table itself fail — so keeping the table store-owned costs nothing
  and keeps `tests/test_db_migration.py` and external tooling clear of it.

**DD-6 — App-wide settings: two `app_metadata` JSON records with defaults applied on read; API only, no UI; route prefix `/api/knowledge-settings`**
- Keys and defaults, owned by a new `the_one/knowledge/settings.py`:
  `knowledge.embedding` → `{"backend": "local", "model_id":
  "potion-retrieval-32M", "dim": 512}`; `knowledge.chunking` →
  `{"size_chars": 1000, "overlap_chars": 150}`; `knowledge.vector_store` →
  `{"backend": <chosen in Leg 6>, "dtype": <chosen>, "dim": 512, "model_id":
  "potion-retrieval-32M"}`. Two operator-facing records (embedding, chunking)
  per the operator's call to keep them separately changeable; the third is
  written by the store and read for DD-3's mismatch check. Stored through
  `AppMetadataRepository` (`repositories.py:1237-1264`, the v31 key/value
  table) as JSON strings; plaintext is correct because nothing here is a
  credential (DD-2 removed the only case that would have been, and
  `key_reconcile.py:19-30`'s hand-maintained corpus list is a trap not worth
  entering for nothing).
- Routes: `GET /api/knowledge-settings` returns both operator records with
  defaults filled; `PUT /api/knowledge-settings` accepts either or both and
  validates via Pydantic models with bounds — `size_chars` 200–2000,
  `overlap_chars` 0–50 % of size, `backend == "local"`, `model_id ==` the
  bundled id, `dim == 512` (422 otherwise, DD-2). Chunking changes apply to
  future indexing only, stated in the response. The prefix is new: the tree
  has no `/settings` namespace, `/api/config` (`api.py:350`) is read-only
  client config, and `/api/knowledge-bases/settings` would collide with the
  `{kb_id}` path parameter — `/api/knowledge-settings` mirrors the hyphenated
  resource style and collides with nothing. The Administration panel that
  edits these is a later flight.
- Rejected: a Pydantic `Settings` env var (not operator-configurable from the
  UI the mission requires later); a new table with encrypted columns (nothing
  to encrypt after DD-2).

**DD-7 — Chunking: a pure, deterministic, paragraph-aware chunker with app-wide defaults; no per-KB configuration**
- `the_one/knowledge/chunking.py::chunk_text(text, *, size_chars=1000,
  overlap_chars=150) -> list[Chunk]` where `Chunk(seq, text, char_start,
  char_end)`. Split on blank-line paragraphs, then on line/sentence boundaries
  when a paragraph exceeds `size_chars`, pack greedily up to `size_chars`,
  carry an `overlap_chars` tail into the next chunk. Offsets are into the
  original text so Flight 3's "retrieve the source material behind an item"
  criterion has exact spans. Deterministic: the same text and settings always
  yield the same chunks (a property test pins it).
- Why 1,000 / 150: at ~4 chars per token for English the chunk sits near 250
  tokens, well inside the model's 512-token `max_length` (DD-1), so nothing is
  silently truncated at the cap; it is the middle of DD-4's storage range
  (~3M chunks at the ceiling); and static mean-pooled embeddings lose
  specificity as spans grow, so smaller-than-LLM chunks are the right default
  for this model class. The upper bound of 2,000 is validated at the settings
  API because 2,000 chars can exceed 512 tokens for dense code — and when it
  does, DD-1's `truncated` count is what reports it.
- Resolved mission open question: chunking is app-wide, not per-KB (operator's
  call at planning). Tuning is Flight 3's concern once real corpora exist.

**DD-8 — Benchmark apparatus: a committed, parameterised script, run on `windows-worker` through a one-off `fly execute` task and on the Linux dev host, with a stated RAM fallback**
- Act path: `scripts/bench_vector_store.py` (generator-script precedent —
  `scripts/refresh_embedding_model.py`), taking `--n`, `--queries`, `--cells`
  and `--corpus {synthetic,real}` as CLI arguments so the 3M cell is its own
  invocation (Architect S2). Two corpora: (a) synthetic clustered vectors
  (Gaussian mixture, 512 dims, unit-normalised) at N = 1,000,000 and
  N = 3,000,000, generated and inserted in 100k batches so the process never
  holds the full float32 set; (b) a real corpus — the repository's own
  markdown (`docs/`, `missions/`, `the_one/agents.md`, `README.md`) chunked by
  DD-7 and embedded by DD-1's backend, on the order of 10–20k chunks — with
  200 held-out query chunks. For each of DD-4's four cells it records build
  wall time, on-disk bytes (the DB delta or the sidecar size), query latency
  p50/p95 at k = 10 over 200 single queries, recall@10 against exact float32
  brute force (numpy, streamed in 100k blocks), and peak RSS via
  `the_one.diagnostics._peak_rss_bytes`. For `usearch` it also records
  `save()` + `restore()` time at the largest N, the DD-3 rebuild cost. Output
  is one markdown table on stdout.
- Read path: stdout, pasted verbatim into the flight log. The Windows run uses
  a one-off task YAML (not committed, same shape as Flight 1's peak-RSS
  reproduction: `platform: windows`, the worker's `C:\Python311`, `PYTHONPATH`
  to the checkout, `-i repo=.`) — an unfrozen run, because the question is the
  store's behaviour on Windows CPython 3.11 with the published wheels, not the
  freeze. The Linux run is the contrast that makes the SIMD gap visible.
- **RAM fallback (Architect Q6)**: if `windows-worker` cannot hold the 3M
  `usearch` f16 cell (~3–4 GB resident), the recorded set is Windows 1M,
  Linux 1M and Linux 3M, and the Windows 3M figure is **extrapolated** as
  Linux 3M × (Windows 1M / Linux 1M), labelled as an extrapolation in the
  table. The extrapolation assumes the platform penalty is N-independent,
  which holds for a per-distance SIMD-versus-serial kernel cost (the thing
  Flight 1 found) and would not hold for a memory-bound effect — the label
  says so (Architect S8). Flight 1's inheritance — measure on Windows or
  discount Linux explicitly — is satisfied either way and cannot be lost
  silently.
- **Run order (Architect S9)**: the Windows 1M sqlite-vec cells run first as
  a cheap early read against the bar. If they miss it there, the 3M cells
  for that store are skipped as wasted worker time and the `faiss-cpu`
  question is raised days earlier; the CLI arguments make this free.
- Observability premise checked: everything asserted is a number the script
  computes and prints; no state under test lives anywhere the script cannot
  read. Feasibility premise checked on this host for the small case.
- Trade-off: a synthetic corpus at 3M measures latency and *index recall*
  (how much of the exact top-10 an approximate index or a lossy dtype
  returns), not retrieval quality; retrieval-relevant recall — the figure
  DD-4's 0.95 floor applies to — is measured only on the ~25k real corpus.
  *(Clarified at Leg 5 design review: both tables carry a recall column,
  with different meanings; the earlier wording said synthetic recall was
  not measured at all.)* Accepted; the alternative is embedding gigabytes
  of text nobody has.

**DD-9 — The store choice is the operator's, made at a leg boundary against a bar set in advance; Leg 6 removes the loser and closes squawk 0049**
- Decision inputs, in priority order: (1) p95 single-query latency at the
  largest measured N on Windows, judged against the bar the operator records
  **before** the table lands (open question above); (2) recall@10 ≥ 0.95 at
  the cell's dtype; (3) on-disk bytes at that N; (4) the single-file property
  versus DD-3's sidecar rebuild cost, priced by the measured `restore()`
  time. The operator records the choice and the chosen dtype in the flight
  log's Flight Director Notes; Leg 6 is designed only after that entry
  exists. If **no** cell clears the bar, the `faiss-cpu` divert (Flight 1's
  shelf) is live and is a flight re-plan, not a Leg 6 variation — on the
  Architect's early Linux numbers this is a realistic outcome, not a
  formality.
- Leg 6 removes the losing package from `pyproject.toml` (and `numkong` if
  `usearch` loses — it is unreachable on Windows in any case, Known Issues),
  regenerates `uv.lock`, drops the loser's `doctor` probe and its by-name CI
  assertions in both lanes, removes its `upx_exclude` entries and any
  `binaries` collection from the spec, deletes its store backend module and
  tests, and adds the `[tool.uv] override-dependencies` that drops `hf-xet`
  (squawk 0049 completed against this leg's commit, verified by the same
  frozen run). If `usearch` wins, the `kb_vector_index` DDL moves into a v41
  block (DD-3). One `fly execute` at the end proves `RESULT: PASS` with the
  surviving probes and `fts5: OK`; `pip-audit` runs on the final closure.

**DD-10 — `vec0` is loaded inside `SqliteVecStore.open()`, not in the connection factory**
- The extension is a backend-specific concern and lives with the backend.
  `open()` runs `await conn.enable_load_extension(True)`, `await
  conn.load_extension(sqlite_vec.loadable_path())`, then
  `enable_load_extension(False)` in a `finally` — the probe's discipline
  (`diagnostics.py:355-380`). `aiosqlite.Connection` exposes both as real
  coroutine methods dispatched onto the connection's worker thread (Architect,
  verified). Repeated `load_extension` on one connection is idempotent
  (verified), and a store-level `_loaded` flag under the write lock makes
  the enable → load → disable sequence run once, so two concurrent `open()`
  calls cannot interleave inside the window. Extension loading is off for
  the rest of the process. The window now opens on **first vector-store
  use**, not at boot — `SECURITY-MODEL.md` says so.
- Why not `the_one/db/connection.py::get_connection` (the earlier draft): the
  rationale — "a database written with a `vec0` table cannot be silently
  opened by a build that cannot read it" — is false (Architect, verified:
  everything but the `vec0` queries themselves works without the extension).
  Loading in the store keeps the factory backend-agnostic, makes Leg 6's
  removal a module deletion rather than a connection-factory edit, and means
  no test that never touches vectors pays the load. Fail-loud stays: a
  `sqlite3` build without `enable_load_extension` raises from `open()` with a
  message naming the `knowledge.vector_store` setting — that is where the
  operator's misconfiguration actually is.
- `SECURITY-MODEL.md` gains a paragraph noting the native extension load and
  the disabled state. Test: `tests/test_vector_store.py` asserts
  `SELECT vec_version()` succeeds on the app connection after `open()` and
  that a subsequent `load_extension` call **fails**.

**DD-11 — Two more permanent `doctor` gates; the rewritten embedding probe changes its detail line and its tests deliberately**
- `_probe_fts5`: in-memory `CREATE VIRTUAL TABLE … USING fts5`, insert, `bm25`
  MATCH, assert the rowid comes back. Unconditional like the embedding probe
  (Flight 1 DD-7: FTS5 is a base capability in every checkout, and the frozen
  Windows CPython 3.11 build has never been observed with it — R9). Both CI
  lanes assert `fts5: OK` by name. `run_doctor`'s docstring
  (`diagnostics.py:795-802`) enumerates "eight" gates by name and is updated,
  as are `the_one/main.py`, `README.md` and `docs/windows-install.md`.
- `_probe_embedding_model` is rewritten to construct a **fresh
  `LocalStaticBackend`** (never `get_embedding_backend()` — the offline test
  that monkeypatches `_EMBEDDING_MODEL_DIRNAME` would otherwise race the
  singleton and pass or fail on test order). The detail line changes shape
  and the tests change with it (Architect, medium — the earlier draft's "same
  detail line, same tests" was wrong): it now reports the model's native
  dtype and the seam's (`512-dim float16 model → float32 seam`), the norm
  (asserted within 1e-3 of 1.0 per DD-1's measured float16 tolerance, as a
  model-normalisation check rather than an all-zeros guard), `truncated=0` for the probe text, the weights byte size,
  peak RSS and the resolved path. In `tests/test_doctor_embedding_model.py`
  the `"float16 vector"` assertion, the `_StubModel.encode` signature (must
  accept kwargs and return 2-D) and the `len(vector)` read are updated; both
  CI lanes' `grep -q "embedding model: OK"` are unaffected.
- The existing `_probe_sqlite_vec` / `_probe_usearch` stay as capability gates
  and are unchanged (R11) until Leg 6 removes one.

**DD-12 — Search fusion is not this flight**
- The flight ships the two primitives — `VectorStore.query` (semantic) and
  `KBChunkRepository.search_keyword(kb_id, query, k)` (FTS5 `bm25`) — each
  returning `(chunk_id, score)` pairs, with tests. How they combine
  (reciprocal rank fusion, weighting, fallback) is a mission open question
  that needs a real corpus and an agent-facing tool to evaluate against;
  designing it now would be designing blind.

**DD-13 — Every write that commits on the shared connection runs inside one `write_transaction()` guard; no explicit `BEGIN`; the rule is stated, tested and lint-enforced**
- The earlier draft's "explicit `BEGIN`/`COMMIT` on the singleton" is not
  achievable (Architect, high, verified): `aiosqlite` serialises statements,
  not transactions, so another coroutine's `commit()` commits a partial write
  and a subsequent `rollback()` cannot undo it; an explicit `BEGIN` raises
  `cannot start a transaction within a transaction` whenever any other
  uncommitted DML is open — exactly under the concurrency that motivates it;
  and it is unnecessary, because with `isolation_level=""` the first DML
  already opens a transaction. The two in-tree comments a developer would
  lean on (`schema.py:319-327`, `api.py:4642-4647`, "aiosqlite silently
  COMMITs before any non-DML statement") are stale — DDL and PRAGMA have not
  auto-committed since Python 3.6 — and Leg 1 corrects them where it touches
  `schema.py` and logs the `api.py` one as a squawk.
- Rule: **every path that calls `commit()` on the shared connection holds
  the lock** — not only multi-statement writers. The cycle-1 draft scoped the
  lock to multi-statement writes and left single-statement self-committing
  methods alone; the Architect modelled that verbatim and the previous
  chunks were destroyed, because the hazard was never two multi-statement
  writers colliding — it is *anyone else's* `commit()` landing inside a
  partial transaction, and a single-statement repository method is exactly
  such a committer. With every committer holding the lock the model
  survives. Mechanism: `the_one/db/_write_lock.py` exposes
  `write_transaction(conn)`, an async context manager that acquires a
  module-level `asyncio.Lock` (precedents: `the_one/sessions/_locks.py:20`,
  `the_one/mcp/_pool.py:103`, `the_one/interfaces/web/app.py:566`), yields,
  and on exit commits — or rolls back if the body raised. Every repository
  write, in every existing repository, is wrapped in it (a mechanical,
  uncontended change; each acquisition is one statement long for the
  existing methods). `SqliteVecStore`'s SQLite writes use it too. The
  convention is named `db-writes-hold-the-write-lock` in `the_one/agents.md`.
- **Nesting is forbidden and detected.** The lock is not re-entrant;
  `write_transaction` records the owning task and raises `RuntimeError`
  immediately if the same task re-enters, so a deadlock becomes a test
  failure rather than a hang. Consequently the vector store **acquires the
  lock itself** and callers never wrap a store call inside their own
  transaction — DD-3's write ordering (chunks + FTS commit, then vectors)
  is two transactions by design, never one (Architect Q3).
- `update_status` is a single conditional statement, not a read-then-write:
  `UPDATE kb_items SET status = ?, … WHERE id = ? AND status IN (<allowed
  predecessors>)`; `rowcount == 0` is an invalid transition or a missing
  item, distinguished by one follow-up `SELECT`. A check-and-set in SQL has
  no TOCTOU window for Flight 3's pipeline and Flight 4's watcher to fall
  into (Architect Q2).
- **Enforcement**: a repo-source guard test in the genre of
  `tests/test_token_definitions.py` / `tests/test_ui_guards.py` asserts that
  every `conn.commit()` under `the_one/db/` and `the_one/vectors/` is
  lexically inside a `write_transaction` block (the helper is the only place
  that may call `commit()` directly). The rule is the kind that decays
  silently; the guard is what keeps it true after Flight 4 (Architect S10).
- Test: the atomicity checkpoint keeps its single-task failing-insert case
  **and** adds a concurrent-interleave case — two tasks, one raising
  mid-write, the other a **plain single-statement repository write** that
  commits in between — proving the previous chunks and FTS rows survive.
  That is the realistic interleaving; a test whose second task is another
  lock-holder would prove only atomicity against lock-holders.
- Rejected: a second write connection. The Architect tried it: under WAL a
  second connection on the same file gets `database is locked` while the
  first holds an open write transaction, so every existing repository would
  need a `busy_timeout` and a retry story.

### Prerequisites

- [ ] Concourse at `localhost:8080`, team `the-one`, `fly` token valid (it
      expired mid-Flight 1; re-verify at flight start, not at Leg 5)
- [x] `windows-worker` registered and healthy, **and its available RAM
      recorded** — measured 2026-09-14 by a one-off task: 31.71 GB total,
      14.22 GB free, 20 CPUs. The 3M cells run there directly; DD-8's
      extrapolation is not needed
- [x] **Operator's latency bar recorded**: p95 ≤ 250 ms (set at planning,
      2026-09-14; DD-9 input #1)
- [ ] `uv` on PATH for Leg 6's lock regeneration (uv 0.10.0 at Flight 1)
- [x] `sqlite-vec` 0.1.9 partition keys, `vec_int8` binding, delete-by-rowid;
      `usearch` 2.26.2 `save()`/`restore()` to path and buffer; FTS5 external-
      content with delete; `aiosqlite` extension coroutines; `SQLITE_MAX_LENGTH`
      1e9; `vec0` DB opens and migrates without the extension; rowid
      recycling without `AUTOINCREMENT`; no native upsert in either store;
      model2vec thread safety — all verified on this host during planning
- [x] Mission amended for DD-2 (2026-09-14); squawk 0050 logged for R17; R2
      citation corrected

### Pre-Flight Checklist

- [x] All open questions resolved *(one deliberately deferred: the store choice at the Leg 5/6 checkpoint, judged against the p95 ≤ 250 ms bar)*
- [x] Design decisions documented
- [ ] Prerequisites verified *(Concourse/`fly` token, `windows-worker` RAM and `uv` re-verified at flight start; the empirical premises and the latency bar are done)*
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

Ordered so the schema — the one hard-to-reverse step — lands first and alone,
the chunk repository lands against it with the write-lock rule it introduces,
the seams land with a stub backend so their tests never wait on a model load
or a native extension, the measurement runs on a proven apparatus, and the
irreversible closure change comes last, after a human decision.

**Leg 1** rewrites the storage shape: the v40 block in `ensure_schema`
(`the_one/db/schema.py`, appended after the v39 block at `:2269`,
`CURRENT_VERSION = 40`, `tests/test_db_migration.py:4389` updated), the
`KBItem` model's status and type vocabularies as `Literal`s sharing a
`_kb_types.py` tuple with an import-time assert, `KBItemRepository` gaining
`update_status` with DD-5's transition table, `set_content_identity`,
`list_by_status`, `count_by_status`; `the_one/db/_write_lock.py` with
`write_transaction`, **every existing repository write wrapped in it**, the
commit-guard test (DD-13), and the stale-comment correction at
`schema.py:319-327`. Routes: `GET
…/items/{item_id}` (the repo method that has no caller today), `POST
…/items/{item_id}/retry` (`failed|indexing→pending`, 409 otherwise), `create_kb_item`
checks the KB exists and returns 404 instead of leaking an `IntegrityError` as
a 500, `delete_kb_item` scopes by `kb_id` (R8). Migration, repository and
route tests.

**Leg 2** lands `KBChunkRepository`: `replace_item_chunks` under the write
lock with explicit FTS sync, `search_keyword`, `rebuild_fts`, `check_fts`,
the cascade-cleanup hooks in `KnowledgeBaseRepository.delete` and
`KBItemRepository.delete` (DD-5), the single-task and concurrent-interleave
atomicity tests (DD-13), the orphan-FTS-rows test, and `_probe_fts5` with
both CI lanes' by-name assertions plus the four doctor enumerations (DD-11).
The `db-writes-hold-the-write-lock` convention is written
into `the_one/agents.md` here, where its first consumer lives.

**Leg 3** lands the embedding seam and the settings: `the_one/embeddings/`
gains the Protocol, `EmbedResult`, `LocalStaticBackend`, the singleton, its
reset seam and the KB-gated warm-up; `the_one/embeddings/__init__.py`'s
"no seam lives here" docstring and `packaging/windows/the-one.spec:245-254`'s
"NOTHING imports `the_one.embeddings`" comment are both rewritten (they are
contradicted the moment the seam exists); the probe is rewritten per DD-11
with its tests; `tests/_embedding_stub.py` provides the stub;
`the_one/knowledge/` is created with `settings.py` and `chunking.py`; the two
`/api/knowledge-settings` routes join `api.py` under a `# ── Knowledge
settings ──` banner; the `agents.md` Diagnostics section (squawk 0047) is
updated for the rewritten probe.

**Leg 4** lands the vector-store seam: `the_one/vectors/` with the Protocol,
`SqliteVecStore` (DD-10 loading inside `open()`, live-DDL mismatch check),
`UsearchStore` (sidecar, registry table, generation check, `rebuild_from`),
`get_vector_store()` with `data_dir` resolved at `open()` and a reset seam,
the shared Protocol test suite run against both backends (including
upsert-existing-id, reopen-and-query, delete-kb-leaves-zero) — driven by
deterministic seeded `np.ndarray`s built in the test file, **not** by the
embedding stub, so Leg 4 genuinely depends only on Leg 1 — DD-3's write
ordering written into `the_one/agents.md`'s new "Knowledge storage" contract,
and the `SECURITY-MODEL.md` paragraph.

**Leg 5** is the measurement: `scripts/bench_vector_store.py`, the Linux
runs, the `windows-worker` runs (or DD-8's extrapolation), every number in
the flight log. It **stops** at the decision checkpoint and removes nothing.

**Leg 6** is designed after the operator's decision entry exists. It removes
the loser and `hf-xet`, moves `kb_vector_index` into v41 if `usearch` won,
updates docs (`CLAUDE.md` gains the settings routes, the write-lock rule and
the `fts5` gate; `README.md`, `docs/windows-install.md` and `the_one/main.py`
doctor enumerations lose the removed probe), runs the unit gate, `pip-audit`
and one frozen `fly execute`.

Files affected (planning estimate; legs cite exactly): `the_one/db/schema.py`,
`the_one/db/models.py`, `the_one/db/_kb_types.py`, `the_one/db/_write_lock.py`,
`the_one/db/repositories.py`, `the_one/interfaces/web/api.py`,
`the_one/interfaces/web/app.py`, `the_one/diagnostics.py`, `the_one/main.py`,
`the_one/embeddings/{__init__,_backend,local}.py`,
`the_one/knowledge/{__init__,settings,chunking}.py`,
`the_one/vectors/{__init__,_store,sqlite_vec_store,usearch_store}.py`,
`scripts/bench_vector_store.py`, `pyproject.toml`, `uv.lock`,
`packaging/windows/the-one.spec`, `.github/workflows/windows-installer.yml`,
`ci/tasks/windows-installer-build.yml`, `tests/test_db_migration.py`,
`tests/test_db_repositories.py`, `tests/test_db_api.py`, `tests/test_doctor.py`,
`tests/test_doctor_embedding_model.py`, `tests/_embedding_stub.py`, new
`tests/test_kb_chunks.py`, `tests/test_embeddings.py`,
`tests/test_knowledge_settings.py`, `tests/test_chunking.py`,
`tests/test_vector_store.py`, `CLAUDE.md`, `SECURITY-MODEL.md`, `README.md`,
`docs/windows-install.md`, `the_one/agents.md`, `squawks/0049-*.md`.

### Checkpoints

- [ ] v40 applies on a fresh DB, on a v39 DB with existing `kb_items` rows (a `status = NULL` row and a junk-status row both land as `pending`), survives the `>= 7` rewind-rerun, `CURRENT_VERSION == 40`, and `kb_chunks` proves `AUTOINCREMENT` by delete-then-insert
- [ ] `fts5: OK` appears in the frozen Windows `doctor` output (proves R9)
- [ ] `KBItemRepository.update_status` enforces the transition table as one conditional `UPDATE`, including `indexing→pending`; the retry route moves `failed` and `indexing` items to `pending` and refuses others with 409
- [ ] `replace_item_chunks` is atomic in both the single-task failing-insert case and the concurrent-interleave case against a plain single-statement writer (DD-13); the commit-inside-`write_transaction` guard test passes across `the_one/db/` and `the_one/vectors/`
- [ ] `search_keyword` returns the planted chunk for an exact rare token; a KB delete leaves zero orphan FTS rows and zero vector rows; `rebuild_fts` recovers a deliberately orphaned index
- [ ] `LocalStaticBackend.embed` returns `(n, 512)` float32 unit vectors with a `truncated` count, never enables multiprocessing, and the rewritten probe's detail line and tests match DD-11
- [ ] Every seam consumer test passes against `StubEmbeddingBackend`; real loads stay confined to `tests/test_doctor_embedding_model.py`; `make test-unit` wall time stays within the 455–470 s band (3,950 tests at Flight 1 close)
- [ ] `GET/PUT /api/knowledge-settings` round-trips; a non-bundled `model_id` or non-`local` backend is refused 422
- [ ] Both vector backends pass the same Protocol test suite (upsert / upsert-existing / query / delete / delete_kb / count / reopen-and-query) against seeded numpy vectors; `SELECT vec_version()` works after `SqliteVecStore.open()` and loading is disabled afterwards; the live-DDL dtype mismatch is detected
- [x] Operator's latency bar recorded **before** Leg 5 runs — p95 ≤ 250 ms, at planning
- [ ] Benchmark table for all four DD-4 cells at N = 1M and N = 3M (Windows measured or DD-8-extrapolated, labelled), plus recall@10 on the real corpus, from both platforms, in the flight log
- [ ] Operator's store + dtype decision recorded in Flight Director Notes before Leg 6 is designed
- [ ] Loser removed, `hf-xet` overridden, `uv.lock` regenerated with no conflict, `pip-audit` clean, installer size recorded against 141,827,664 bytes, frozen `doctor` `RESULT: PASS`
- [ ] Squawk 0049 completed against Leg 6's commit

### Adaptation Criteria

**Divert if**:
- `fts5: FAIL` in the frozen Windows bundle. FTS5 is a mission constraint
  (hybrid retrieval with no second engine); the divert is a CPython build
  question, not a Flight 2 design question.
- `enable_load_extension` fails on the frozen bundle's `aiosqlite` path
  despite Flight 1's bare-`sqlite3` success — eliminates `sqlite-vec` by fact;
  the decision checkpoint collapses to `usearch` and Leg 6 proceeds.
- **No** cell clears the operator's latency bar at the largest measured N on
  Windows. Next on the shelf per Flight 1: `faiss-cpu` (19.5 MB, Windows
  wheels). This is a re-plan of DD-3/DD-9, not a Leg 6 variation.
- Every int8 cell falls below recall 0.95 **and** the surviving float cell's
  on-disk bytes at the ceiling exceed what the operator accepts — reopens
  DD-7's chunk-size default rather than the store choice.
- The v40 rebuild cannot be made rewind-tolerant without touching a frozen
  block — escalate; the append-only rule is not this flight's to bend.
- The write-lock rule (DD-13) turns out to need a lock across a path outside
  this flight's files (an existing repository's multi-statement write) —
  that is a shared-interface change to raise, not to fold in.

**Acceptable variations**:
- Package and module names under `the_one/embeddings`, `the_one/knowledge`,
  `the_one/vectors`
- The benchmark's N values if `windows-worker` RAM forces the DD-8 fallback
  (recorded and labelled)
- Whether the warm-up task is gated on "any KB exists" or on a setting
- Chunker splitting heuristics, as long as determinism and offsets hold
- Leg 3 and Leg 4 may be implemented in either order; both depend only on
  Leg 1

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned
> and created one at a time as the flight progresses.

- [x] `v40-schema-and-item-lifecycle` — the migration, `CURRENT_VERSION = 40`,
      `_kb_types.py`, item status vocabulary and conditional-UPDATE
      transitions, `_write_lock.py` + every repository write wrapped + the
      commit-guard test, the stale-comment fix, the item routes and two route
      fixes, migration and repository tests. **HIGH risk** (schema; a
      mechanical change across every repository's write path).
- [x] `chunk-repository-and-fts` — `KBChunkRepository` with locked
      transactional FTS sync, keyword search, `rebuild_fts`/`check_fts`,
      cascade-cleanup hooks, atomicity and orphan tests, `_probe_fts5` with
      both lanes' assertions and the doctor enumerations, the write-lock
      convention in `agents.md`. **HIGH risk** (shared-interface change to
      `run_doctor`'s gate list read by four consumers; transaction semantics on
      the singleton).
- [x] `embedding-seam-and-settings` — `EmbeddingBackend`, `EmbedResult`,
      `LocalStaticBackend` carrying the DD-5 guards, singleton + reset + KB-
      gated warm-up, probe rewrite with its test changes, stub backend,
      `knowledge/settings.py` + `chunking.py`, the two settings routes, the
      `__init__` docstring and spec comment rewrites, `agents.md` Diagnostics
      update. Risk tier at leg design; the probe rewrite touches a gate four
      consumers read.
- [x] `vector-store-seam` — `VectorStore` Protocol, both backends, DD-10
      loading in `open()`, live-DDL mismatch check, sidecar registry and
      generation check, the shared Protocol test suite, the "Knowledge
      storage" contract in `agents.md`, the `SECURITY-MODEL.md` paragraph.
      **HIGH risk** (native extension on the app connection).
- [x] `store-benchmark` — the script, the latency-bar prerequisite checked,
      Linux runs, `windows-worker` runs or the labelled extrapolation, numbers
      in the log. **Ends at the operator's decision checkpoint.** Linux runs
      (AC-1 smoke, N=1M, N=3M all four cells, real corpus) landed by the
      Developer; `windows-worker` runs are the Flight Director's, not yet
      run.
- [x] `store-decision-and-closure` — designed only after the decision entry
      exists. Remove the loser and its probe/spec/CI lines, v41 for
      `kb_vector_index` if `usearch` won, `hf-xet` override (squawk 0049),
      lock regeneration, docs, `pip-audit`, one frozen run. **HIGH risk**
      (dependency closure, both CI lanes).

No HAT leg: the flight has no operator-visible surface (operator's call at
planning).

---

## Post-Flight

### Completion Checklist

- [x] All legs completed
- [ ] Code merged *(PR into `mission/24-knowledge-bases` — no CI lane runs on it; gates run by hand and recorded in the flight log)*
- [x] Tests passing
- [x] Documentation updated — `CLAUDE.md` (settings routes, write-lock rule, `fts5` gate), `SECURITY-MODEL.md` (DD-10), `README.md` / `docs/windows-install.md` / `the_one/main.py` doctor enumerations, `the_one/agents.md` Diagnostics section, the new `db-writes-hold-the-write-lock` convention, and a new "Knowledge storage" subsystem contract (seams, settings keys, the FTS sync rule, the write ordering, the no-vec0-in-migrations rule)
- [x] Squawk 0049 completed; squawk 0051 (stale aiosqlite comment at `api.py:4642-4647`) logged at planning; mission open questions on chunking and on backend switching annotated *(done at planning)*

### Verification

The flight succeeds when: `make test-unit` is green with the v40 migration
suite included; the benchmark table for both stores on both platforms is in
the flight log and the operator's decision entry cites it against the bar
recorded before the run; the losing store is gone from the closure;
`pip-audit` is clean; and `the-one.exe doctor` returns `RESULT: PASS` in a
PyInstaller bundle frozen on `windows-worker` with `fts5: OK` and the
surviving store's probe present and gating.

**No behavior test.** Nothing in this flight is observable by an operator or an
agent except two JSON settings routes, whose acceptance is fully stated by
unit tests against `TestClient`. Two live agents would witness nothing the
assertions do not already state.

**Known lane conditions** carried from the Flight 1 debrief: `make test-unit`
runs 455–470 s at 3,950 tests; the flight adds a migration suite, five seam
and repository suites and the chunker's property test, and must stay in that
band by keeping real model loads to the two that already exist. The Studio
browser lane's standing timing flake (squawk 0035) is untouched — no browser
test changes.
