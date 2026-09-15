# Flight Log: Storage and Embedding Foundation

**Flight**: [Storage and Embedding Foundation](flight.md)

## Summary

In flight. Legs 1–5 landed (v40 schema + item lifecycle; chunk repository +
FTS5; embedding seam + knowledge settings + chunker; vector-store seam with
both backends; the store benchmark). Linux benchmark tables recorded;
Windows runs complete (sqlite-vec 1M measured; usearch 200k measured with
1M/3M extrapolated on time grounds; real corpus measured). Flight-end
review of Legs 1–5 confirmed on cycle 2; Legs 1–5 committed (`c315cf5`),
draft PR #197. **At the decision checkpoint**: the operator chooses the
store and dtype against the tables under `## Store Benchmark`; Leg 6
(closure) is designed after that entry exists.

---

## Leg Progress

### Leg 1 — v40-schema-and-item-lifecycle — implementation landed

**What landed** (DD-5/DD-13): schema `CURRENT_VERSION = 40` — `kb_items`
rebuilt via the v37-style same-name rewrite (guarded on `content_hash`
column absence) with a constrained lifecycle (`type IN ('file','url',
'folder')`, `status IN ('pending','indexing','indexed','failed')`, plus
`error`/`content_hash`/`size_bytes`/`mtime`/`updated_at`/`indexed_at`);
`kb_chunks` (`AUTOINCREMENT` ids, never recycled) and an external-content
`kb_chunks_fts` FTS5 index, both new; three indexes
(`idx_kb_items_kb_id`, `idx_kb_items_kb_status`, `idx_kb_chunks_kb_id`).
Added a defensive branch beyond the leg spec's literal guidance: when
`kb_items` is entirely absent (only reachable via a hand-built test
fixture that stamps `schema_version` above 0 without ever running
`SCHEMA_V1` — see "Deviations" below), the block creates the table fresh
in its v40 shape instead of assuming a v39 shape to rebuild from.

`the_one/db/_kb_types.py` (new): `KB_ITEM_TYPES`, `KB_ITEM_STATUSES`,
`KB_ITEM_TRANSITIONS` (keyed by target status), `KBItemTransitionError`.
`the_one/db/models.py`: `KBItem` gains the new fields as `Literal`s pinned
to `_kb_types.py` by two import-time asserts (the `PROVIDER_TYPES`
pattern). `the_one/db/_write_lock.py` (new): `write_transaction(conn)` —
one module-level `asyncio.Lock` + owning-task tracking, commit-on-clean-
exit / rollback-on-`BaseException`, same-task re-entry raises
`RuntimeError` before acquiring, `reset_for_test()`.

`the_one/db/repositories.py`: all **41** pre-existing `conn.commit()`
sites (the exact count the leg spec predicted) swept to
`async with write_transaction(self.conn): ...`, mechanically, file-wide,
in one pass; existence-check reads stayed outside the guarded block.
`KBItemRepository` gained `update_status` (one conditional `UPDATE`
keyed off `KB_ITEM_TRANSITIONS[target]`, `rowcount`-based
found/not-found/invalid-transition disambiguation, single shared
`now_iso()` stamp for `updated_at` + the `indexed_at` THEN-branch),
`set_content_identity`, `list_by_status`, `count_by_status`; `create` now
writes all thirteen columns.

`the_one/interfaces/web/api.py`: the rotation endpoint's write block (the
**+1** pre-existing multi-statement writer outside `the_one/db/`) moved
inside `write_transaction(conn)`, keeping `encryptor.install_key(new_key)`
as the first statement after the block with no intervening `await` (Q1
invariant — verified by the existing rotation tests, unchanged). Two new
routes (`GET .../items/{item_id}`, `POST .../items/{item_id}/retry` —
accepts `failed`/`indexing`, 409 otherwise incl. `indexed` which the
generic transition table would otherwise permit) plus two route fixes:
`create_kb_item` 404s on an unknown `kb_id` before validating the body;
`delete_kb_item` and the new item routes all scope-check
`item.kb_id == kb_id` and 404 (never leaking existence across KBs).

**Migration tests**: `TestSchemaV40` — 7 tests (fresh-DB shape/CHECK/AC-1,
CHECK constraints/AC-3, v39-upgrade-preserves-rows/AC-2 via the new
`_rewind_to_v39_kb_items` helper, idempotent-double-ensure, `>= 7`
rewind-rerun, stamp-only-rewind-short-circuits/AC-4,
AUTOINCREMENT-never-recycles/AC-5). `TestSchemaV39`'s fresh-db literal
assertion updated from `CURRENT_VERSION == 39` to `== 40` (a fresh DB now
runs the full chain through v40). Full `tests/test_db_migration.py`: 95
passed.

**New test files**: `tests/test_db_write_lock.py` (7 tests — AC-8 a–d
behavioural cases incl. the realistic concurrent-interleave case via
`asyncio.Event`-sequenced tasks, plus the AC-9 source guard) and
`tests/test_kb_types_consistency.py` (8 tests — tuple membership,
`Literal` pin, and behavioural fresh-DB CHECK accept/reject, deliberately
NOT a derived-SQL-string comparison per `_kb_types.py`'s docstring).
Additions to `tests/test_db_repositories.py` (`TestKBItemRepositoryLifecycle`
+ one `TestKBItemRepository` case) and `tests/test_db_api.py` (10 new
`TestKnowledgeBaseAPI` cases covering AC-10's route matrix).

**Unit-gate figures**: `make test-unit` — **3998 passed, 10 skipped**,
**584.35s (9:44)**. Compared to the Flight 1 baseline (3,950 / 10 /
455–470s): pass count is +48 (all net-new tests from this leg; skip count
unchanged, confirming no existing test was disturbed). Wall time is above
the 455–470s band, but this run was NOT clean — the scoped post-format
re-verification (`test_provider_api.py` … `test_db_api.py`, ~528 tests)
was still executing concurrently on the same host for part of this run's
duration, and the two invocations contended for CPU. A contention-free
re-run was judged unnecessary given every test passed and the delta is
fully explained by CPU contention plus 48 additional tests (48 tests at
this suite's ~0.12s/test average is on the order of 6s, not the ~120s
overage seen) — flagged here rather than silently accepted so a later
leg's own timing comparison isn't misled by this entry's figure. Ran the
gate exactly once per instruction.

**Ruff**: `ruff check the_one/ tests/` — all checks passed. `ruff format
--check the_one/ tests/` — required one `ruff format` pass (3 files:
`the_one/db/repositories.py`, `the_one/db/schema.py`,
`tests/test_db_migration.py`, mostly re-wrapping the additional
indentation level `write_transaction` introduced); clean after.

**Guard-test result**: `.commit()` / `.rollback()` occur in exactly two
files under `the_one/` — `the_one/db/_write_lock.py` and
`the_one/db/schema.py` — confirmed both by a direct `grep -rln` sweep and
by `tests/test_db_write_lock.py::test_commit_and_rollback_confined_to_write_lock_and_schema`
(passing).

**What a later leg should know**:

- The kb_items-table-absent defensive branch (see "What landed" above)
  was NOT anticipated by the leg spec and was needed to keep
  `tests/test_db_migration.py::TestMigrationV12::test_v12_real_v11_to_v12_upgrade`
  green — that test hand-builds a partial pre-v12 schema (stamping
  `schema_version` directly, never running `SCHEMA_V1`) and has no reason
  to know about KB tables. The same class of fixture could resurface for
  ANY future migration that unconditionally touches `kb_items`/`kb_chunks`
  without a presence guard — grep `tests/test_db_migration.py` for other
  hand-built partial-schema fixtures before assuming a table "always
  exists by version N."
- `tests/test_encrypted_corpora_guard.py`'s regex extractor is fragile to
  comment wording: a bare `SELECT` token appearing in a comment ahead of
  the real query, on the SAME physical line as a later `(PRAGMA, DDL,
  BEGIN)`-shaped parenthetical, can get its comma-split tokens
  mis-extracted as a bogus `(table, column)` pair once no `#`
  line-comment marker falls between them. Keep multi-clause parentheticals
  in that function's leading comment split across lines (mirroring the
  original layout) rather than collapsing them onto one line.
- The rotation endpoint's stale `aiosqlite silently COMMITs before any
  non-DML statement` comment (api.py, `:4642-4647` pre-leg) is now
  annotated but NOT corrected in substance — squawk 0051, explicitly out
  of this leg's scope per the leg spec.
- `KBItem.status`/`.type` `Literal`s are pinned to `_kb_types.py` tuples by
  import-time asserts, but the SQL CHECKs are FROZEN INLINE LITERALS in
  the v40 block — a future status/type addition needs a NEW migration
  block (the table-rebuild ceremony), never an edit to v40's CHECK text.
- Leg 2's `KBChunkRepository` can rely on: `write_transaction` already
  exists and is proven safe for FTS-adjacent tables; `kb_chunks`/
  `kb_chunks_fts` exist from this leg but nothing writes to either yet.

### Leg 2 — chunk-repository-and-fts — implementation landed

**What landed** (DD-5/DD-11/DD-12/DD-13): `the_one/db/_kb_types.py` gains
`ChunkRecord` (frozen dataclass: `seq`, `text`, `char_start`, `char_end` —
the shape crossing from Leg 3's chunker into the repository, validated by
nothing here since `UNIQUE(item_id, seq)`/`NOT NULL` enforce at insert
time). `the_one/db/models.py` gains `KBChunk` (plain read model, next to
`KBItem`). `the_one/db/repositories.py` gains the module-level
`_fts_delete_rows(conn, rows)` helper (the sole site issuing the
external-content `INSERT INTO kb_chunks_fts(kb_chunks_fts, rowid, text)
VALUES ('delete', ?, ?)` command) and `KBChunkRepository` with
`replace_item_chunks`, `delete_for_item`, `delete_for_kb`, `list_for_item`,
`get_many` (order-preserving, 500-batched `IN (…)`, `[]` short-circuit),
`count_for_kb`, `search_keyword`, `rebuild_fts`, `check_fts`.
`KnowledgeBaseRepository.delete` and `KBItemRepository.delete` each gained
a select-then-`_fts_delete_rows` step inside their existing
`write_transaction`, immediately before the row delete that FK-cascades
`kb_chunks` away; `KBItemRepository.delete` now returns `list[int]` (the
removed chunk ids) — its one caller (`api.py:1529`) already ignored the
return value, so no call site needed updating.

`the_one/diagnostics.py` gains `_probe_fts5` (in-memory `CREATE VIRTUAL
TABLE ... USING fts5(x, tokenize='porter unicode61')`, insert, `MATCH`,
assert rowid 1 — unconditional per DD-11, never routes through
`_vector_probe_outcome`, never consults `is_frozen()`), registered in
`run_doctor`'s `gates` list between `usearch` and `embedding model`; the
docstring's gate count and skip-behavior prose updated from eight/six to
nine/seven. Both CI lanes
(`.github/workflows/windows-installer.yml`,
`ci/tasks/windows-installer-build.yml`) assert `"fts5: OK"` by name
alongside the existing vector-store and embedding-model assertions. The
three doctor enumerations (`the_one/main.py`, `README.md`,
`docs/windows-install.md`) now mention FTS5/vector stores together.

**Deviations from the leg spec's literal guidance**: none. Every
Implementation Guidance step (1-11) landed as specified, including the
verified two-argument `check_fts` form, the unaliased `bm25(kb_chunks_fts)`
/ `MATCH` table name, the per-term quoting scheme, `cur.lastrowid` inside
`async with conn.execute(...) as cur`, and the 500-row `get_many` batch
size.

**Tests**: new `tests/test_kb_chunks.py` — **18 tests** across
`TestReplaceItemChunksInsert` (AC-1), `TestReplaceItemChunksReReplace`
(AC-2), `TestReplaceItemChunksAtomicitySingleTask` (AC-3, a duplicate-`seq`
mid-batch raising `sqlite3.IntegrityError`), `TestReplaceItemChunksAtomicityConcurrent`
(AC-4, `asyncio.gather` of a failing `replace_item_chunks` against a plain
`KnowledgeBaseRepository.create` — the failing task's duplicate `seq` is
placed last so it fails only after two successful inserts, and the
plain-writer task yields once before its own write so both genuinely
contend for the write-transaction lock), `TestSearchKeyword` (AC-5 — planted
token ranks first, cross-KB isolation, `bm25` ascending-is-best-first, `k`
honoured, every FTS5 operator character from the leg spec's Edge Cases
quoted and non-raising, empty/whitespace query short-circuits),
`TestCascadeDeleteFtsSync` (AC-6), `TestRebuildAndCheckFts` (AC-7 — empty
index, synced multi-row index, repository-driven delete, and the raw
`DELETE FROM kb_chunks` bypass-then-`rebuild_fts` recovery), plus
`TestGetManyAndCounts` for the two enumerated-but-not-lettered helpers.
`tests/test_doctor.py::TestProbeFts5` — **6 tests** (real round-trip detail
assertions, a module-swap failure path mirroring `TestProbeSqliteVec`'s
technique via a `_Fts5UnavailableConnection` wrapper, unconditional-failure
regardless of `is_frozen()`, the `inspect.getsource` regression guard for
both `_vector_probe_outcome` and `is_frozen` absence, the by-name output
line, and `RESULT: FAIL` promotion). `tests/test_db_repositories.py` gained
2 cascade-hook tests inside `TestKBItemRepository`
(`test_delete_returns_removed_chunk_ids_and_syncs_fts`,
`test_cascade_delete_via_kb_also_syncs_chunk_fts`) plus a `kb_chunk_repo`
fixture.

**Unit-gate figures**: `make test-unit` run alone, foreground, nothing else
on the host — **4,024 passed, 10 skipped, 472.22s (7:52)**. Delta from
this flight's Leg 1 entry (3,998 / 10) is exactly **+26** (18 +
6 + 2 — every net-net-new test from this leg, no existing test disturbed).
472.22s is 2.22s above the stated 455-470s reference band; fully explained
by the 26 additional tests (well under 0.1s/test at this suite's average)
rather than contention — this run was NOT concurrent with anything else.
Ran the gate exactly once per instruction; this leg's figure supersedes
Leg 1's contention-affected 584.35s as the flight's clean reference going
forward.

**Ruff**: `ruff check the_one/ tests/` — all checks passed (after fixing 3
`E501` line-too-long violations the first pass surfaced). `ruff format
--check the_one/ tests/` required one `ruff format` pass (4 files:
`the_one/db/repositories.py`, `the_one/diagnostics.py`,
`tests/test_db_repositories.py`, `tests/test_kb_chunks.py`); clean after.

**Guard-test result**: `.commit()`/`.rollback()` occur in exactly the same
two files as Leg 1 left them — `the_one/db/_write_lock.py` and
`the_one/db/schema.py` — confirmed by a direct `grep -rln` sweep of
`the_one/` and by
`tests/test_db_write_lock.py::test_commit_and_rollback_confined_to_write_lock_and_schema`
(passing). `KBChunkRepository.check_fts` takes the guard even though it
writes nothing, per the leg spec's explicit instruction (a read must not
run while another task's write is mid-flight on the FTS table).

**`.venv/bin/the-one doctor`'s `fts5` line** (this host, SQLite 3.45.1):
`fts5: OK — fts5 available (SQLite 3.45.1); porter+unicode61 MATCH
round-trip returned rowid 1`. Full run: `RESULT: PASS`, all nine gates OK.

**bm25 scoring note for Leg 4 / the fusion flight**: `bm25()` is
lower-is-better (more negative = more relevant); `search_keyword` returns
the raw score unchanged and orders `ASC` (best first). Any fusion or
benchmark code combining this with a vector-store distance/similarity
score (higher-is-better, per Leg 3/4's stores) MUST NOT assume a shared
sign convention — normalize or invert one side before combining.

**What a later leg should know**:

- `KBChunkRepository` is fully independent of `KnowledgeBaseRepository`/
  `KBItemRepository` at the write-transaction level — it never nests a
  `write_transaction` inside another; the two cascade hooks call the
  module-level `_fts_delete_rows` helper directly instead of going through
  `KBChunkRepository`'s methods, exactly per the leg spec's re-entry
  warning.
- Nothing here embeds text or calls the vector store — Leg 3 (chunker)
  produces `ChunkRecord`s that feed `replace_item_chunks` directly; Leg 4
  wires the vector-store cleanup into the same cascade call sites this leg
  established (`KnowledgeBaseRepository.delete` / `KBItemRepository.delete`
  now return/use the chunk ids Leg 4 needs), outside this leg's own
  `write_transaction` per the no-nesting rule (a vector store's own lock
  acquisition, like `KBChunkRepository`'s, must never be called from
  inside another component's `write_transaction` block).
- `search_keyword`'s `k` parameter is passed straight into `LIMIT ?` with
  no upper bound enforced by the repository — if Leg 4's benchmark or a
  future tool-facing caller needs a ceiling, that belongs at the caller,
  not silently added here (would have changed the leg spec's stated
  signature).

### Leg 3 — embedding-seam-and-settings — implementation landed

**What landed** (DD-1/DD-2/DD-6/DD-7/DD-11): the embedding seam —
`the_one/embeddings/_backend.py` (new: `EmbedResult` frozen dataclass,
`EmbeddingBackend` `@runtime_checkable` Protocol, `NORM_TOLERANCE = 1e-3`,
`EmbeddingModelMissingError`) and `the_one/embeddings/local.py` (new: the
five constants moved out of `diagnostics.py` with their leading
underscore dropped, `MAX_TOKENS = 512`, `force_hf_offline()`,
`resolve_model_dir()` carrying the two DD-5 offline-load guards, and
`LocalStaticBackend` — `load()` classmethod, `embed()` running
`use_multiprocessing=False, max_length=512, show_progress_bar=False`,
computing `truncated` from a second `tokenize(max_length=None)` pass
applied only to inputs longer than 512 characters). `the_one/embeddings/__init__.py`
rewritten: process-wide singleton (`get_embedding_backend()`,
double-checked under a `threading.Lock`), `async warm_up()`
(idempotent, `_warming`-guarded, swallows a loader failure into a log
line), `_reset_for_test()`.

`the_one/diagnostics.py`: `_probe_embedding_model` rewritten to
construct a **fresh** `LocalStaticBackend` (never the singleton) and
call `embed([...])` through it; the five underscored constants and
`_force_hf_offline` are removed (nothing outside `diagnostics.py` and
`tests/test_doctor_embedding_model.py` imported them); the probe now
imports the plain `EMBEDDING_DIM`/`EMBEDDING_WEIGHTS_FILENAME` names
from `the_one.embeddings.local`. New detail line shape (verified on
this host, see below): native dtype AND the float32 seam, the DD-1
truncation count, and a unit-norm check (`abs(norm - 1.0) >
NORM_TOLERANCE`) that subsumes the old separate all-zeros check.

`the_one/knowledge/__init__.py` + `settings.py` (new): `EmbeddingSettings`
(plain `str`/`int` fields with `field_validator`s — not `Literal`s, per
the leg spec's pydantic-2.13 finding that a `Literal` mismatch can't
carry the DD-2 amendment message into `.errors()`), `ChunkingSettings`
(`size_chars` 200–2000, `overlap_chars <= size_chars // 2`),
`KnowledgeSettings`, `EMBEDDING_KEY`/`CHUNKING_KEY`,
`load_knowledge_settings`/`save_knowledge_settings` against
`AppMetadataRepository`. `the_one/knowledge/chunking.py` (new):
`chunk_text(text, *, size_chars=1000, overlap_chars=150) ->
list[ChunkRecord]` — one combined sorted boundary-position set
(paragraph/line/sentence) drives both window-end selection and the next
window's overlap start; offsets are into the original text, CRLF
handled via `\r?\n` regexes rather than by normalizing the text.

`the_one/db/repositories.py`: `KnowledgeBaseRepository.count() -> int`
(one `SELECT count(*)`). `the_one/interfaces/web/api.py`: `# ──
Knowledge settings ──` banner, `GET`/`PUT /api/knowledge-settings`
(merge-then-revalidate on `PUT`, 422 on an unknown top-level key or a
failed validator); `create_knowledge_base` fires
`asyncio.create_task(warm_up())` after `repo.create(kb)`.
`the_one/interfaces/web/app.py`: a warm-up block after the
connector-manager start, gated on `KnowledgeBaseRepository(...).count()
> 0`, in its own `try/except` like its neighbours.
`packaging/windows/the-one.spec`: the `"the_one.embeddings"`
hiddenimports comment rewritten (the package IS now imported as a
module by `diagnostics.py`/`knowledge/settings.py`; the entry stays for
the packaged-data-by-name resolution).

**Test-isolation addition beyond the leg spec's literal file list**:
`tests/conftest.py` gained a suite-wide autouse fixture
(`_stub_embedding_backend_by_default`) patching `LocalStaticBackend.load`
to a `StubEmbeddingBackend` for every test module except
`tests.test_doctor_embedding_model` and `tests.test_embeddings` (checked
by `request.module.__name__`). This was necessary, not optional: once
`create_knowledge_base` fires `warm_up()` on every call, ANY existing
test that creates a knowledge base (e.g. `TestKnowledgeBaseAPI` from
Leg 1) would otherwise race a real ~250 MiB model load into the
background. Documented as a new "suite-wide variant" paragraph under the
`autouse-fixture + dedicated-real-load-file` convention in `agents.md`.

**Tests**: `tests/_embedding_stub.py` (new) — `StubEmbeddingBackend`
(hash-seeded deterministic unit vectors, `dim=8` default,
`truncate_over_chars` option). `tests/test_embeddings.py` (new) — **23
tests**: `TestProtocolSatisfaction` (AC-1 structural satisfaction for
both backends), `TestStubEmbeddingBackend` (AC-1 determinism/shape/dtype/
norm/truncation), `TestLocalStaticBackendEmbed` (AC-2 — shape/dtype/norm,
the three required `encode()` kwargs, the truncation count from the
long-subset-only `tokenize()` pass, the empty-input short-circuit, the
zero-token-text float32 dtype edge case), `TestResolveModelDir` /
`TestForceHfOffline` (AC-3 — both guards, including the new guard-#2
weights-missing test design review found untested anywhere in the tree),
`TestSingleton` (AC-4 — repeated-call identity, `_reset_for_test`,
concurrent-first-call exactly-once via a `threading.Event` start gate
plus a fake-loader sleep to widen the race window, `warm_up()`
idempotency and failure-swallowing). `tests/test_knowledge_settings.py`
(new) — **16 tests** (AC-8: defaults, round-trip, invalid-stored-value
fallback-with-warning for both keys, all three `EmbeddingSettings`
validators, both `ChunkingSettings` bounds inclusive/exclusive).
`tests/test_chunking.py` (new) — **212 tests** (AC-7: 200
seeded-corpus-generated texts — mixed paragraph lengths, long unbroken
lines, CRLF, unicode — each checked against every AC-7 invariant, plus
determinism and 11 hand-written edge-case tests). `tests/test_doctor_embedding_model.py`
— **+1 test** (`test_missing_weights_file_fails_rather_than_downloading`,
AC-3's guard-#2 case), plus DD-11's retargeting of the existing offline
tests' monkeypatch targets to `the_one.embeddings.local` and the
`_StubModel` kwargs/tokenize/encode shape update; still exactly **two**
real, unstubbed loads (`TestRealLoad.test_probe_loads_the_committed_weights`
and `test_reported_weights_size_matches_the_file_on_disk`) — verified via
`grep -c "real load\|from_pretrained"` and by inspection that neither
monkeypatches `StaticModel.from_pretrained`. `tests/test_lifespan.py` —
**+4 tests** (AC-5: zero-KB-skips-load, one-KB-loads-exactly-once-under-
`asyncio.to_thread`, loader-failure-logged-without-failing-startup, and a
source-inspection regression guard pinning the warm-up block after the
connector-manager start). `tests/test_db_api.py` — **+6 tests** (AC-5:
`TestKnowledgeBaseCreateWarmsUpEmbeddingBackend` — create kicks warm-up
exactly once, a second create does not kick it again; AC-9:
`TestKnowledgeSettingsAPI` — GET defaults, PUT chunking-only,
PUT-invalid-422-changes-nothing, PUT-non-local-backend-422-names-the-
amendment, PUT-unknown-top-level-key-422). `tests/test_db_repositories.py`
— **+1 test** (`TestKnowledgeBaseRepository.test_count`).

**Deviation from the leg spec's literal Implementation Guidance**
(recorded per the leg's Post-Completion Checklist, not a change to any
acceptance criterion): step 10's overlap-window description — "the next
window starts at the latest boundary at or before `end - overlap_chars`"
— does not itself bound overlap above by `overlap_chars` when worked
through with concrete numbers (a boundary chosen by searching *backward*
from the floor can land arbitrarily far below it, making overlap
*larger* than `overlap_chars`, not smaller). The implementation instead
searches for the EARLIEST boundary at or after `end - overlap_chars` —
the direction that actually produces the "at most `overlap_chars`, at
least 1 when full" guarantee AC-7 requires — falling back to the exact
character position when no boundary exists in range, unchanged from the
spec. Full reasoning in `the_one/knowledge/chunking.py`'s module
docstring ("Overlap direction note") and in `agents.md`'s new "Knowledge
storage" paragraph. AC-7 itself (the actual acceptance criterion, not
the guidance prose) is fully satisfied and verified by the 212-test
corpus sweep. A second, minor deviation: `chunk_text` uses one flat,
combined boundary-position set (paragraph ∪ line ∪ sentence) rather than
three separate hierarchical splitting passes — behaviorally equivalent
for the stated contract ("boundaries fall on paragraph/line/sentence
boundaries when one exists") and simpler to verify.

**Unit-gate figures**: `make test-unit` run alone, foreground, nothing
else on the host — **4,287 passed, 10 skipped, 496.64s (8:16)**. Delta
from Leg 2's clean reference (4,024 / 10 / 472.22s) is exactly **+263**
passed (23 + 16 + 212 + 1 + 4 + 6 + 1 — every net-new test this leg
added, across `test_embeddings.py`, `test_knowledge_settings.py`,
`test_chunking.py`, `test_doctor_embedding_model.py`, `test_lifespan.py`,
`test_db_api.py`, `test_db_repositories.py` respectively), skip count
unchanged (confirming no existing test was disturbed). Wall time is
+24.42s over the reference, consistent with ~0.093s/test at the added
count (the 212-case chunking sweep is cheap — no I/O, no model load)
rather than contention; this run was not concurrent with anything else.
Ran the gate exactly once per instruction.

**Ruff**: `ruff check the_one/ tests/` — all checks passed. `ruff format
--check the_one/ tests/` required two `ruff format` passes across the
leg's work (import-block reordering after `ruff check --fix` in
`tests/conftest.py`, `tests/test_embeddings.py`, `tests/test_lifespan.py`,
`tests/test_db_api.py`; then a formatting pass over
`tests/conftest.py`, `tests/test_db_api.py`, `tests/test_embeddings.py`,
`the_one/interfaces/web/api.py`); clean after both.

**`.venv/bin/the-one doctor`'s `embedding model` line** (this host,
verified against the real bundled weights, no stubbing):

```
embedding model: OK — 512-dim float16 model → float32 seam, norm 1.0000, truncated=0 (model.safetensors=64,605,272 bytes, peak RSS 262.6 MiB) from /home/cprch/projects/the-one/the_one/embeddings/data/potion-retrieval-32M
```

Full run: `RESULT: PASS`, all nine gates OK — both CI lanes' `embedding
model: OK` and `fts5: OK` greps are unaffected (the gate name and OK/FAIL
shape are unchanged; only the detail text after the em-dash changed).

**What Leg 4 / Leg 5 should know**:

- The embedding seam is fully independent of `the_one/vectors` (not
  created yet) — Leg 4 imports `the_one.embeddings.get_embedding_backend`
  (or, in tests, constructs a `StubEmbeddingBackend` directly) to produce
  vectors; nothing in this leg assumes a particular vector-store shape.
- `ChunkRecord` (Leg 2) is exactly what `chunk_text` returns — Leg 4/5's
  ingest pipeline can feed `chunk_text(...)`'s output straight into
  `KBChunkRepository.replace_item_chunks` and then `embed([c.text for c
  in chunks])` with no intermediate shape conversion.
- `get_embedding_backend()` raises `EmbeddingModelMissingError` (or
  whatever `LocalStaticBackend.load()` raises) to ITS caller if the
  loader fails — `warm_up()` only swallows the failure for the two
  fire-and-forget call sites (lifespan startup, `create_knowledge_base`).
  A later flight's real ingest pipeline calling `get_embedding_backend()`
  directly (not through `warm_up()`) will see that exception surface
  normally and must handle it.
- The suite-wide `_stub_embedding_backend_by_default` autouse fixture in
  `tests/conftest.py` means any FUTURE test file that needs to control
  `LocalStaticBackend.load` itself (mirroring `test_embeddings.py`) must
  add its own module name to `_EMBEDDING_REAL_LOAD_MODULES` there, or its
  own monkeypatching will simply be overridden by the autouse fixture's
  setup for every OTHER test in that file.
- `EmbeddingSettings`/`ChunkingSettings` validation is enforced only at
  the `PUT /api/knowledge-settings` route and at
  `load_knowledge_settings` (falls back to defaults with a logged
  warning on a stored value that no longer validates) — nothing in this
  leg touches `knowledge.vector_store` (DD-6's third settings record,
  owned by Leg 6).

### Leg 4 — vector-store-seam — implementation landed

**What landed** (DD-3/DD-4/DD-10/DD-13): the vector-store seam —
`the_one/vectors/_store.py` (new: `VectorStore` `@runtime_checkable`
Protocol — `open`/`upsert`/`delete`/`delete_kb`/`query`/`count`/`flush`/
`close` plus `backend`/`dtype`/`dim`; `VectorStoreError`,
`VectorStoreMismatchError`, `VectorStoreStaleError`; `quantize_int8`
with the load-bearing `.astype(np.int8)` cast), `the_one/vectors/sqlite_vec_store.py`
(new: `SqliteVecStore` — double-checked-locked `open()` loading `vec0`
via `enable_load_extension`/`load_extension`/`enable_load_extension`
against the connection, live-DDL mismatch check against
`sqlite_master`, delete-then-insert `upsert`, partition-scoped
`query`/`count`/`delete`/`delete_kb`, no-op `flush`/`close`),
`the_one/vectors/usearch_store.py` (new: `UsearchStore` — synchronous
`dict.setdefault` per-KB lock creation, registry-row staleness
detection (`VectorStoreStaleError` on a missing sidecar, a count
mismatch, or a dtype/dim mismatch) on every read/write except
`rebuild_from`/`delete_kb`, `flush()` as the only path that calls
`index.save()` and bumps `generation`/`count`), `the_one/vectors/__init__.py`
(new: the named `_build_store(settings, conn)` seam, async
`get_vector_store()` double-checked under `asyncio.Lock` mirroring
`get_embedding_backend()`'s shape, `_reset_for_test()`).
`the_one/knowledge/settings.py`: `VectorStoreSettings` (`backend`/
`dtype`/`dim`/`model_id`, a `model_validator` tying `dtype` to
`backend`), `VECTOR_STORE_KEY`, `load_vector_store_settings` (raises,
never falls back, on an invalid stored record — DD-3/DD-9: the wrong
backend must not silently read the wrong data),
`save_vector_store_settings`. `the_one/interfaces/web/api.py`:
`_vector_store()` helper; `delete_knowledge_base` and `delete_kb_item`
call `store.delete_kb`/`store.delete` after the repository transaction,
log-and-swallow on failure, still return 200;
`_knowledge_settings_response` made `async` and extended with
`"vector_store"` (read fresh every call) alongside the pre-existing
`notes` list — the pre-existing generic top-level-key 422 guard in
`update_knowledge_settings` was relied on as-is for AC-12 (no new
message added, per the design review's medium finding).

**Deviation from the leg spec's literal Implementation Guidance**
(recorded per the leg's Post-Completion Checklist; no acceptance
criterion changed): AC-10 requires that calling `store.upsert` from
inside a caller's `write_transaction` raises `RuntimeError` for BOTH
backends. `SqliteVecStore.upsert`/`.delete` satisfy this for free (their
whole body is one `write_transaction` block), but the guidance's literal
`UsearchStore.upsert`/`.delete` description never touches SQL at all —
they only mutate the in-memory index and mark it dirty; persistence is
`flush()`'s job. As written, that would NOT raise inside a caller's
transaction, failing AC-10 for the two usearch cells. Fix: both methods
now open-and-immediately-close an empty `async with write_transaction
(self.conn): pass` before doing their real work under the store's own
per-KB `asyncio.Lock` — this triggers the guard's re-entry `RuntimeError`
when nested, without holding the single process-wide write lock for the
duration of the (pure in-memory, `asyncio.to_thread`) mutation. Documented
at the call sites and in `agents.md`'s "Knowledge storage" update.

**Tests**: `tests/test_vector_store.py` (new, **50 tests**) — the shared
Protocol suite via a `store` fixture parametrised over the four cells
(sqlite-vec float32/int8, usearch f16/i8): `TestProtocolSatisfaction` (2,
AC-1), `TestSharedProtocolSuite` (3 × 4 cells = 12, AC-2 — self-first
query, k=10 non-decreasing distances, count), `TestUpsertReplaceAndDelete`
(3 × 4 = 12, AC-3), `TestKbIsolation` (1 × 4 = 4, AC-4, using disjoint id
ranges per the `vec0` table-wide-rowid edge case), `TestReopen` (1 × 4 =
4, AC-5), `TestSqliteVecOpenBehavior` (5, AC-6 — vec0 loads, extension
loading disabled after, idempotent, two concurrent opens load once via a
counting wrapper on `conn.enable_load_extension`, the
`TestProbeSqliteVec`-style module-swap for the missing-method build),
`TestMismatchDetection` (3, AC-7 — dtype mismatch, dim mismatch, and the
live-DDL text asserted present in the message), `TestUsearchStaleness`
(4, AC-8 — upsert-without-flush invisible to a fresh instance, tampered
registry count raises stale then `rebuild_from` recovers, missing sidecar
raises stale, `flush` is what advances `generation`/`count`),
`TestNoReentry` (1 × 4 = 4, AC-10). `tests/test_vectors_dispatch.py`
(new, **7 tests**, AC-9): defaults to sqlite-vec when the record is
absent, returns sqlite-vec/usearch per the record, same instance on
repeated calls, `_reset_for_test()` builds anew, concurrent first callers
build exactly once (a counting wrapper on `_build_store`), and
`data_dir` resolved at `open()` — a `settings.data_dir` monkeypatch
applied after `_build_store()` but before `.open()` is honoured (built
via `_build_store` directly so the two steps could be separated; the
full dispatcher always calls `open()` immediately, closing that window
in production). Every dispatcher test patches
`the_one.vectors.get_connection` to the test's isolated connection —
the module holds its own reference, independent of any patch on
`the_one.interfaces.web.api.get_connection`, and skipping this would
silently touch the operator's real data directory.
`tests/test_knowledge_settings.py` — **+11 tests**:
`TestVectorStoreSettingsValidation` (7 — default valid, both sqlite-vec
dtypes valid, both usearch dtypes valid, sqlite-vec+f16 rejected,
usearch+float32 rejected) and `TestVectorStoreSettingsPersistence` (4 —
default-on-absent, round-trip, key-is-written, invalid-stored-record
RAISES rather than falling back — the deliberate DD-3/DD-9 asymmetry
with `load_knowledge_settings`). `tests/test_db_api.py` — **+5 tests**:
AC-12 (`test_put_updates_chunking_and_still_returns_vector_store_and_notes`,
`test_put_with_vector_store_key_rejected`; the existing
`test_get_returns_defaults_on_fresh_db` was extended in place to assert
the new `"vector_store"` key, not counted as new) and AC-11 (a new
`TestKnowledgeBaseDeleteCallsVectorStore` class — `delete_knowledge_base`
calls `delete_kb` with the right id, `delete_kb_item` calls `delete`
with the exact chunk ids `KBChunkRepository.replace_item_chunks`
returned, and a store whose `delete_kb` raises is logged via
`logger.exception` while the route still returns 200 — all three via a
recording stub store injected through a monkeypatched `_build_store` +
`_reset_for_test()`, with the store's own `get_connection` rerouted to
the test client's connection the same way the dispatcher test file does).

**Guard test**: `tests/test_db_write_lock.py`'s source-scan test (rglobs
all of `the_one/`) passed unchanged — confirms `the_one/vectors/`
introduces no `commit()`/`rollback()` call outside
`the_one/db/_write_lock.py` and `the_one/db/schema.py`; manually
re-verified with `grep -rn "\.commit(\|\.rollback("` across the new
files with no hits.

**Empirical facts reconfirmed during implementation** (all of Context's
planning-time claims held under direct testing, none contradicted): `vec0`
rowids are unique table-wide (a same-id `UNIQUE constraint failed` was
observed when a disjoint-range test was deliberately broken during
development, confirming the edge case is real, not theoretical);
`usearch.Index.remove` of an absent key returns without raising, verified
both singly and as part of a mixed present/absent batch; `sqlite_vec.load
(conn)` on an `aiosqlite.Connection` was confirmed to silently load
nothing (a stray call during early drafting produced never-awaited-
coroutine warnings and a `vec_version()` failure) — the shipped code
uses `await conn.load_extension(str(sqlite_vec.loadable_path()))`
exclusively; `Index.restore` is a `staticmethod` returning a new `Index`.

**Empirical `usearch` `flush` (save) cost at this leg's test sizes**
(dim 512, f16, this host, single-KB, cold index) — Leg 5's benchmark
input: **n=50 → ~3.0 ms** (58.5 KB sidecar), **n=1,000 → ~7.5 ms**
(1.17 MB), **n=5,000 → ~5.8 ms** (5.87 MB) — sidecar bytes scale
linearly at ~1.17 KB/vector for f16/512-dim; save latency at these small
sizes is dominated by fixed overhead, not N, so Leg 5's benchmark at the
million-vector corpus ceiling is where the real cost curve will show.

**Unit-gate figures**: `make test-unit` run alone, foreground, nothing
else on the host — **4,360 passed, 10 skipped, 506.07s (8:26)**. Delta
from Leg 3's clean reference (4,287 / 10 / 496.64s) is exactly **+73**
passed (50 + 7 + 5 + 11 — every net-new test this leg added, across
`test_vector_store.py`, `test_vectors_dispatch.py`, `test_db_api.py`,
`test_knowledge_settings.py` respectively, matching the prediction
exactly), skip count unchanged (confirming no existing test was
disturbed). Wall time is +9.43s over the reference — consistent with
the added test count (several cells build real `usearch` HNSW indexes
and load the real `vec0` extension, so per-test cost here is higher than
Leg 3's cheap chunking sweep, but the total remains proportionate). Ran
the gate exactly once per instruction.

**Ruff**: `ruff check the_one/ tests/` — all checks passed (after fixing
one `E501` the auto-formatter didn't reach, in the `kb_vector_index`
INSERT's SQL string, split across two literals). `ruff format --check
the_one/ tests/` — clean after one `ruff format` pass over the four new/
changed vector-store files and the new/changed test files.

### Leg 5 — store-benchmark — implementation landed

**What landed**: `scripts/bench_vector_store.py` (new, ~700 lines) — a
parameterised benchmark script exercising all four DD-4 cells
(`sqlite-vec`/float32, `sqlite-vec`/int8, `usearch`/f16, `usearch`/i8)
**entirely through the Leg 4 `VectorStore` seam** (`open`/`upsert`/
`flush`/`query`/`close` — no raw `sqlite_vec`/`usearch` import anywhere in
the script; versions are read via `importlib.metadata.version(...)`,
never `import sqlite_vec`/`import usearch`). CLI: `--corpus
{synthetic,real}`, `--n`, `--queries`, `--cells` (comma `backend:dtype`
list, default all four), `--k`, `--seed`, `--data-dir`, `--out`, plus a
hidden `--real-corpus-root` (test-only injection point for the real-corpus
file walk). `Makefile`'s `bench-vector-store` target runs the AC-1 smoke
size. Full results, commands and timestamps are in the new top-level
"Store Benchmark" section below.

**Implementation notes**:
- Synthetic corpus: seeded 64-centroid Gaussian mixture (σ=0.3), 512-dim,
  generated/inserted in 100k batches via a fresh `np.random.default_rng(seed)`
  per call (so the same seed reproduces the same corpus across separate
  invocations and platforms — verified: the 1M and 3M runs printed the
  identical batch-0 SHA-256 fingerprint, since both start with the same
  first 100k-row batch). Queries are the first `--queries` corpus members
  (ids 1..Q, always present in the corpus by construction) perturbed by
  σ=0.05 on a `seed+1` substream and re-normalised.
- Ground truth: `brute_force_topk` streams `(ids, vectors)` batches through
  a per-block `argpartition` merged into a running top-k — never holds more
  than one 100k block plus the running result. Real-corpus ground truth
  reuses the same function over the embedded (non-held-out) corpus matrix.
- `recall_at_k` is a plain set-intersection over the returned vs. truth id
  sets, divided by k — order-independent by design (a shuffled correct
  result still scores 1.0; a half-replaced result scores exactly 0.5, both
  covered by unit tests).
- Latency: `time_queries` times only the `await store.query(...)` call
  with `perf_counter_ns`, runs the whole query loop twice and returns the
  second pass (cache-warm steady state) — proven by a unit test that times
  a stub store whose `query` sleeps a known duration, with unrelated large
  fixture work done outside the timed region. For `usearch`, one query is
  issued against a **freshly reopened** store (the first store closed,
  dropping its in-memory index) before the timing loop; that call's time is
  reported as `restore_ms` and excluded from the p50/p95/max array, per
  AC-3's reconciliation with the landed API (both stores quantise
  internally — there is no pre-quantised query entry point, so the int8
  cells' per-query quantisation cost is inside the timed region by design).
- Disk accounting: `sqlite-vec` cells checkpoint (`PRAGMA
  wal_checkpoint(TRUNCATE)`, issued outside any `write_transaction`) both
  before the cell's inserts (base size) and after `flush()`, reporting the
  delta; `usearch` cells report the sidecar file's size directly. Each
  cell gets a fresh `aiosqlite` connection and DB file; teardown order is
  `store.close()` → `conn.close()` → delete DB/`-wal`/`-shm`/sidecar,
  matching the Windows-safe ordering the leg spec calls out (unlinking a
  file SQLite still holds open raises WinError 32).
- Free-space guard: estimates `n × bytes_per_vector × 1.25` per cell before
  building it, printing `SKIPPED (need ~X GB, free Y GB)` as the row rather
  than crashing. **Deviation, per the leg spec's own flagged edge case**:
  the `usearch`/i8 base was raised from the spec's literal 512 B/vector to
  660 B/vector after the Linux 1M run measured ~660.6 B/vector there (a
  1.29x ratio against 512 — above the 1.25x margin, exactly the condition
  the leg spec said to watch for and correct before the Windows 3M run).
  `sqlite-vec`/int8 measured ~536 B/vector at 1M and 3M alike (ratio 1.05,
  unchanged). `sqlite-vec`/float32 measured ~2,077 B/vector at both 1M and
  3M, matching the leg's cited ~2,124.6 B/vector figure closely.
- Real corpus: walks `docs/`, `missions/`, `the_one/agents.md`,
  `README.md` (or, under `--real-corpus-root`, every `*.md` under one given
  directory — the unit test's injection point), chunks with the DD-7
  defaults (`ChunkingSettings()`), holds out every 125th chunk (capped at
  200) as queries, and embeds the rest via `LocalStaticBackend.load()` —
  **dim is taken from `backend.dim`, never hard-coded**, which is what let
  the real-corpus unit test run under the suite-wide 8-dim stub with no
  injection flag.

**Tests**: `tests/test_bench_vector_store.py` (new, **8 tests**) — AC-7's
source-scan (asserts no `ast.Import`/`ast.ImportFrom` of `sqlite_vec` or
`usearch`), AC-2's three ground-truth/recall tests (streamed-merge-equals-
single-pass-argsort on a small corpus; recall of a brute-force result
against itself is 1.0; a shuffled result is still 1.0; a half-replaced
result is exactly 0.5), AC-3's timed-region test (a sleeping stub store),
and two end-to-end runs: `--corpus synthetic --n 2000 --queries 10 --k 5
--cells sqlite-vec:float32` and `--corpus real --k 3 --cells
sqlite-vec:float32 --real-corpus-root <tmp_path of 3 small .md files>`
(the latter running under the autouse stub backend, dim=8, with no
injection flag — proving AC-6's `backend.dim` claim end-to-end).

**Unit-gate figures**: `make test-unit` run alone, foreground, nothing
else on the host — **4,368 passed, 10 skipped, 512.29s (8:32)**. Delta
from Leg 4's baseline (4,360 / 10 / 506.07s) is exactly **+8 passed**
(this leg's entire new test file), skip count unchanged, wall time +6.22s
— consistent with two extra tiny end-to-end runs (synthetic n=2,000 and a
3-file real corpus) added to the suite.

**Ruff**: `ruff check the_one/ tests/ scripts/` — all checks passed.
`ruff format --check the_one/ tests/ scripts/` — clean (one `ruff format`
pass was needed after the initial draft, to wrap several long `argparse`
`add_argument` lines and sort `tests/test_bench_vector_store.py`'s
imports).

**Linux run wall time** (this leg's scope; Windows runs are the Flight
Director's, see "Store Benchmark" below): AC-1 smoke ~8s, N=1M all four
cells ~15m41s, N=3M split across two invocations (~28m22s for the two
`sqlite-vec` cells, ~22m28s for the two `usearch` cells), real corpus
~29s. **Total ≈ 67 minutes** of benchmark wall time, plus the ~8.5-minute
unit gate. All runs completed with `status: OK` for every cell — no cell
was skipped by the free-space guard on this host (884 GB free at
`/tmp/the-one-bench`).

**What Leg 6 / the Flight Director should know**:
- The `usearch`/i8 free-space-guard base (`_BYTES_PER_VECTOR[("usearch",
  "i8")]`) is now 660 B/vector, not the leg spec's literal 512 — read this
  before trusting the guard on `windows-worker` at 3M without re-checking
  its own measured ratio there too (Windows RAM/allocator behaviour could
  differ from Linux's).
- Every 1M/3M invocation this leg ran individually exceeded the tooling's
  600-second foreground-command cap and was auto-relocated to a background
  slot by the harness (never `run_in_background` set explicitly) — the
  command itself was still launched in the foreground with the mandated
  600000ms timeout each time; this is a property of this session's tooling,
  not of the script, and does not apply to `fly execute`'s no-default-timeout
  behaviour on Concourse.
- `usearch`'s per-insert-batch cost visibly grows with graph size (each
  100k batch prints progress; the last few batches at both 1M and 3M took
  noticeably longer than the first) — expected HNSW behaviour, not a hang;
  Windows's `simd=serial` penalty (Known Issues) will make this more
  pronounced there.
- `sqlite-vec`'s query cost is dominated by I/O (`/proc/[pid]/io`'s `rchar`
  during the 3M float32 cell's query loop matched ~2.4 TB, consistent with
  400 full 6 GB-ish table scans) — this is the "exact scan" cost DD-4
  anticipated, not a bug.

### Flight-end review fixes (Legs 1–5)

Addressed the flight-end code review's two blocking findings and three
"fix now" non-blocking items. No commit made (Developer scope) — tree left
uncommitted for the Flight Director's re-review + commit.

**BLOCKING 1 — `bench_vector_store.py`'s `peak_rss_MB` was a
process-lifetime watermark, not per-cell.** `_peak_rss_bytes()` reads
`ru_maxrss`/`PeakWorkingSetSize`, both monotonic for the life of the
process; `run_synthetic`/`run_real` ran every cell of a multi-cell
invocation sequentially in ONE process, so only the first cell ever read a
clean number. **Fix — per-cell process isolation**: a multi-cell
invocation (`len(cells) > 1`, non-`--child`) now dispatches each cell to
its own child process (`sys.executable` re-invoking `bench_vector_store.py`
with `--cells <one cell>` plus a new hidden `--child` flag and the same
`--seed`/`--data-dir`/corpus arguments); a `--child` invocation regenerates
the corpus identically from the shared inputs, runs exactly that one cell,
and prints ONLY that cell's already-rendered markdown table row on stdout
(everything else — host facts, fingerprint, corpus/progress logging — goes
to stderr or is suppressed, via `contextlib.redirect_stdout` around the
child's internal run). The parent collects each child's row line verbatim
and assembles the final table (`_render_table_from_lines`) rather than
re-deriving it. A genuinely single-cell invocation still runs fully
in-process (no subprocess overhead). **Chosen design for the real-corpus
path**: children RE-EMBED the corpus themselves (no `.npy` caching between
children) — simplest, keeps each child fully self-contained, and the leg's
own review text flagged the ~30s/cell re-embed cost on Linux as acceptable.
Also extracted `render_row` (one row's markdown line) out of `render_table`
so both the in-process and per-cell-subprocess paths share the exact same
rendering logic instead of two independent implementations.

**BLOCKING 2 — `UsearchStore._path_for` built a filesystem path from an
unsanitised `kb_id`.** `KnowledgeBase.id` was a bare `str` and
`create_knowledge_base` accepted a client-supplied `id` verbatim, so
`"../../../evil"` could reach `{data_dir}/vectors/`. **Fix, both layers**:
(a) `KnowledgeBase` (`the_one/db/models.py`) gained an `id` field validator
restricting it to `^[A-Za-z0-9_-]{1,64}$` — every existing test id (`kb1`,
`kb-1`, `a`, `b`, ...) and every API-generated id (`uuid4().hex[:12]`)
already conform, so no test id needed changing; (b)
`UsearchStore._path_for` (`the_one/vectors/usearch_store.py`) now resolves
the candidate path and raises `VectorStoreError` if it would land outside
`self._data_dir` — defence in depth, so even a hypothetical validator
bypass can't escape the vectors directory. `create_knowledge_base`
(`the_one/interfaces/web/api.py`) now catches the resulting
`ValidationError` and 422s (it previously had no try/except around
`KnowledgeBase.model_validate`, so an invalid `id` would have surfaced as
an unhandled 500, not the 422 the fix requires).

**Fix now (non-blocking)**:
- `bench_vector_store.py::run_cell` — the per-cell pre-cleanup call
  (`_cleanup_cell_files`, deleting a leftover DB/sidecar from a prior
  interrupted run) moved INSIDE the per-cell `try` — previously a locked
  leftover file (e.g. a Windows sharing violation) would raise out of
  `run_cell` and abort every remaining cell instead of yielding this one
  cell a SKIPPED/ERROR row. The symmetric post-cell cleanup in `finally`
  also gained its own try/except (logs to stderr on failure) for the same
  reason, on the way out. `restore_ms`'s column note (docstring + a
  comment above `_TABLE_HEADERS`) now reads "restore + one k=10 query" —
  `usearch` loads its index lazily, so the timed post-restore call
  necessarily folds in that query's own cost; there is no pure-restore
  entry point to time separately.
- `tests/conftest.py`'s `_EMBEDDING_REAL_LOAD_MODULES` exemption comment
  corrected: only `tests.test_doctor_embedding_model` performs a real
  model load; `tests.test_embeddings` is exempted for a different reason
  (it stubs `model2vec.StaticModel` itself, one layer below
  `LocalStaticBackend.load`, so it needs this fixture to leave `load`
  alone rather than replacing it wholesale). Exemption set unchanged.
- `update_knowledge_settings` (`the_one/interfaces/web/api.py`) now
  type-checks that a present `embedding`/`chunking` value is a dict BEFORE
  merging it into the current settings — a non-dict value (string, list,
  int, `null`) previously reached `dict.update()` uncaught and surfaced as
  an unhandled 500; it now 422s.

**Files changed**: `scripts/bench_vector_store.py`,
`the_one/db/models.py`, `the_one/vectors/usearch_store.py`,
`the_one/interfaces/web/api.py`, `tests/conftest.py`.

**Tests added**: `tests/test_bench_vector_store.py` (+6: `--child` emits
exactly one stdout row; `--child` rejects anything but exactly one cell; a
real two-cell run produces two rows with real, non-`-`, `peak_rss_MB`
values; a mocked-dispatch test proving two DIFFERENT per-cell RSS values
from two isolated child processes both survive into the final table
unmodified — deterministic proof of the actual fix, since two real tiny
same-footprint subprocesses can legitimately report near-identical RSS,
which would make a real-value inequality assertion flaky; a pre-cleanup
`OSError` yields an ERROR row rather than crashing `run_cell`).
`tests/test_db_repositories.py` (+2: `KnowledgeBase.id` accepts the
existing conforming shapes, rejects path-traversal/oversized/space/dot
shapes via `ValidationError`). `tests/test_db_api.py` (+1:
`POST /api/knowledge-bases` with `id: "../x"` returns 422 and creates
nothing; +1 parametrised: `PUT /api/knowledge-settings` with a non-dict
`embedding`/`chunking` value 422s instead of 500). `tests/test_vector_store.py`
(+2: `UsearchStore._path_for("../../../evil")` raises `VectorStoreError`
even bypassing the model validator; a conforming `kb_id` still resolves
under the store's data dir).

**Verification**: `ruff check the_one/ tests/ scripts/` and
`ruff format --check the_one/ tests/ scripts/` both clean (one
`ruff format` pass needed after the initial draft). Scoped test runs (all
foreground, `scripts/run-tests.sh`, never `-m live`/port 8484): the five
touched/added test files plus their nearest neighbours —
`test_bench_vector_store.py`, `test_vector_store.py`,
`test_db_repositories.py`, `test_db_api.py`, `test_knowledge_settings.py`
(361 passed); `test_doctor.py`, `test_doctor_embedding_model.py`,
`test_db_migration.py`, `test_lifespan.py` (166 passed);
`test_embeddings.py`, `test_kb_chunks.py`, `test_kb_types_consistency.py`,
`test_vectors_dispatch.py`, `test_chunking.py`, `test_db_write_lock.py`
(275 passed). `make test-unit` intentionally NOT run here — the Flight
Director runs it after the re-review, per this leg's Developer-scope
instructions.

**IMPORTANT — read before trusting any `peak_rss_MB` figure recorded
BEFORE this fix**: every `peak_rss_MB` value in the "Store Benchmark"
tables below (the Linux 20k/1M/3M/real-corpus tables in this leg's own
run, and the Windows runs 0–1 in the Flight Director's notes) was produced
by the PRE-FIX single-process design — i.e. each is a **cumulative
process-lifetime watermark**, not a clean per-cell reading. Only the
FIRST cell's `peak_rss_MB` in each of those invocations is meaningful in
isolation; every subsequent cell's figure in the same table reflects
memory already held from the earlier cell(s) in that same run, which is
exactly why the flight-log tables show identical RSS for cell pairs
(1282.54/1282.54, 2927.72/2927.72, per the review's own citation). Any
Windows/large-N re-run performed AFTER this fix lands will produce
genuinely per-cell figures; the tables below are not retroactively
corrected and should be read with this caveat rather than re-trusted as
clean per-cell numbers.

---

## Store Benchmark

DD-8/DD-9 (Leg 5). Every table below was produced by
`scripts/bench_vector_store.py` through the Leg 4 `VectorStore` seam; every
number is pasted verbatim from the script's own stdout (`--out` also wrote
each run's host facts + table to a file under `/tmp/the-one-bench`, never
the repo or the operator's data directory). **No recommendation is made
here** — the store/dtype choice is the operator's (DD-9); see "reading the
table" below for the only interpretive note this section carries.

### Linux (dev host)

**Host** (identical across all Linux runs below): `Linux-6.18.33.2-microsoft-standard-WSL2-x86_64-with-glibc2.39`, Python
3.12.3, SQLite 3.45.1, `sqlite-vec` 0.1.9, `usearch` 2.26.2, 20 CPUs,
16.77 GB RAM total (~14.2 GB available), `usearch` acceleration
`numkong=yes, simd=haswell`, 884 GB free at `/tmp/the-one-bench`.

**AC-1 smoke** — `--corpus synthetic --n 20000 --queries 50`, well under
three minutes (actual: ~8s):

```
2026-09-14T23:26:24Z
$ .venv/bin/python scripts/bench_vector_store.py --corpus synthetic \
    --n 20000 --queries 50 --data-dir /tmp/the-one-bench/smoke \
    --out /tmp/the-one-bench/smoke.md
```

synthetic fingerprint (batch0 sha256): `ade134776992a71906b9e6775f74cbfd1c7ac9ee3f1a828cae659934d76420a1`

| backend | dtype | n | build_s | disk_MB | p50_ms | p95_ms | max_ms | recall@k | peak_rss_MB | save_ms | restore_ms | status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| sqlite-vec | float32 | 20000 | 0.69 | 40.50 | 12.186 | 13.339 | 14.009 | 1.0000 | 231.90 | - | - | OK |
| sqlite-vec | int8 | 20000 | 0.68 | 10.43 | 12.888 | 13.661 | 13.999 | 0.9060 | 278.96 | - | - | OK |
| usearch | f16 | 20000 | 1.27 | 22.36 | 0.487 | 0.631 | 0.956 | 0.4300 | 279.39 | 16.637 | 26.430 | OK |
| usearch | i8 | 20000 | 0.72 | 12.60 | 0.289 | 0.448 | 0.590 | 0.4380 | 284.20 | 8.022 | 11.625 | OK |

`make bench-vector-store` (no explicit args — the target's own smoke
invocation) was run immediately after and confirmed to invoke the exact
same command shape, reproducing the identical fingerprint and the same
table shape (numbers within timing jitter of the run above).

**N = 1,000,000, all four cells** — one invocation:

```
2026-09-14T23:27:05Z (start) .. real 15m40.615s (end ≈ 23:42:46Z)
$ .venv/bin/python scripts/bench_vector_store.py --corpus synthetic \
    --n 1000000 --data-dir /tmp/the-one-bench/n1m \
    --out /tmp/the-one-bench/n1m.md
```

synthetic fingerprint (batch0 sha256): `5c25c9f8e7b7e7b6f004f56fb052fdec8e171ca1216dfcabae2ae52460765e5b`

| backend | dtype | n | build_s | disk_MB | p50_ms | p95_ms | max_ms | recall@k | peak_rss_MB | save_ms | restore_ms | status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| sqlite-vec | float32 | 1000000 | 38.39 | 1980.08 | 553.942 | 563.516 | 569.178 | 1.0000 | 1282.54 | - | - | OK |
| sqlite-vec | int8 | 1000000 | 30.67 | 511.30 | 586.221 | 594.670 | 599.408 | 0.8630 | 1282.54 | - | - | OK |
| usearch | f16 | 1000000 | 216.49 | 1118.14 | 1.021 | 1.368 | 1.974 | 0.0710 | 2927.72 | 633.176 | 764.572 | OK |
| usearch | i8 | 1000000 | 133.91 | 629.86 | 0.888 | 1.219 | 2.122 | 0.0505 | 2927.72 | 374.338 | 484.519 | OK |

**N = 3,000,000, all four cells** — split into two invocations per the
leg spec (a single invocation would have exceeded this session's
per-command foreground cap):

```
2026-09-14T23:44:01Z (start) .. real 28m22.157s (end ≈ 00:12:23Z)
$ .venv/bin/python scripts/bench_vector_store.py --corpus synthetic \
    --n 3000000 --cells sqlite-vec:float32,sqlite-vec:int8 \
    --data-dir /tmp/the-one-bench/n3m --out /tmp/the-one-bench/n3m.md

2026-09-15T00:12:40Z (start) .. real 22m27.990s (end ≈ 00:35:08Z)
$ .venv/bin/python scripts/bench_vector_store.py --corpus synthetic \
    --n 3000000 --cells usearch:f16,usearch:i8 \
    --data-dir /tmp/the-one-bench/n3m --out /tmp/the-one-bench/n3m.md
```

synthetic fingerprint (batch0 sha256, both invocations):
`5c25c9f8e7b7e7b6f004f56fb052fdec8e171ca1216dfcabae2ae52460765e5b`
(identical to the N=1M run above — expected, since both corpora share the
same deterministic first 100k-row batch).

| backend | dtype | n | build_s | disk_MB | p50_ms | p95_ms | max_ms | recall@k | peak_rss_MB | save_ms | restore_ms | status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| sqlite-vec | float32 | 3000000 | 119.37 | 5939.38 | 1662.906 | 1686.712 | 1698.565 | 0.9995 | 1282.59 | - | - | OK |
| sqlite-vec | int8 | 3000000 | 91.38 | 1534.54 | 1760.608 | 1783.084 | 1792.661 | 0.8695 | 1282.59 | - | - | OK |
| usearch | f16 | 3000000 | 761.29 | 3354.55 | 1.450 | 2.072 | 2.286 | 0.0425 | 7646.50 | 2270.424 | 3498.863 | OK |
| usearch | i8 | 3000000 | 475.53 | 1889.70 | 1.080 | 1.365 | 1.616 | 0.0320 | 7646.50 | 1157.350 | 1542.323 | OK |

**Real corpus** — `docs/`, `missions/`, `the_one/agents.md`, `README.md`:
1,154 files, 31,838 chunks (200 held out as queries, 31,638 embedded;
2 truncated at the model's 512-token cap):

```
2026-09-15T00:35:32Z (start) .. real 0m28.722s (end ≈ 00:36:01Z)
$ .venv/bin/python scripts/bench_vector_store.py --corpus real \
    --data-dir /tmp/the-one-bench/real --out /tmp/the-one-bench/real.md
```

| backend | dtype | n | build_s | disk_MB | p50_ms | p95_ms | max_ms | recall@k | peak_rss_MB | save_ms | restore_ms | status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| sqlite-vec | float32 | 31638 | 1.14 | 62.79 | 18.380 | 19.689 | 21.618 | 0.9950 | 440.18 | - | - | OK |
| sqlite-vec | int8 | 31638 | 0.74 | 16.18 | 18.904 | 20.292 | 23.536 | 0.9645 | 440.18 | - | - | OK |
| usearch | f16 | 31638 | 0.88 | 35.39 | 0.306 | 0.444 | 1.143 | 0.9800 | 519.90 | 22.236 | 24.899 | OK |
| usearch | i8 | 31638 | 0.56 | 19.94 | 0.246 | 0.303 | 0.660 | 0.9465 | 520.06 | 13.403 | 13.862 | OK |

**Reading the table** (AC-8e): the operator's p95 ≤ 250 ms bar applies to
the latency columns (p50/p95/max), and those figures are the **second,
cache-warm pass** over each query loop — the steady-state interactive-
search cost; the separate cold-start cost is the `restore_ms` column for
`usearch` (`save_ms`/`restore_ms` are populated only for that backend) and
is effectively zero for `sqlite-vec` (no in-memory index to rebuild on
open). The `recall@k` column carries two different meanings across the
two kinds of table above (AC-6b): on the **synthetic** tables it is
*index/quantisation* recall — how much of the exact top-k an approximate
index (`usearch` HNSW) or a lossy dtype (int8) returns, and the
`sqlite-vec`/float32 row is ≈1.0 by construction (an exact scan measured
against an exact ground truth); on the **real-corpus** table it is the
retrieval-relevant figure the operator's DD-4 0.95 floor applies to.

### Windows (`windows-worker`)

Host facts (from the accidental run 0 below, identical for every run):
`windows-worker`, 20 logical CPUs, 31.71 GB RAM, **465.08 GB free** at the
data dir; Python 3.11 (choco); `usearch_acceleration: numkong=no,
simd=serial; numkong ext 7.8.2 loads fine [haswell,alder] — this usearch
binary was built without numkong` (the Flight 1 finding, reproduced).
Synthetic fingerprint (batch0 sha256) `ade1347769…420a1` — **identical to
the Linux run**, so the two platforms measured the same vectors.

One-off task YAML (not committed; `bench-task.yml` in the session
scratchpad), invoked as `fly -t the-one execute -c bench-task.yml -i repo=.
-v 'args=<ARGS>'`:

```yaml
platform: windows
params:
  ARGS: ((args))
inputs:
  - name: repo
run:
  path: powershell
  args: [-NoProfile, -ExecutionPolicy, Bypass, -Command, |
      $ErrorActionPreference = "Stop"
      choco install python311 -y --no-progress
      $py = "C:\Python311\python.exe"
      Set-Location repo
      & $py -m pip install --upgrade pip --quiet
      & $py -m pip install uv --quiet
      & $py -m uv export --no-dev --no-emit-project --format requirements-txt > release-requirements.txt
      & $py -m pip install -r release-requirements.txt --quiet
      & $py -m pip install -e . --no-deps --quiet
      $argv = $env:ARGS -split ' '
      New-Item -ItemType Directory -Force -Path "$env:TEMP\the-one-bench" | Out-Null
      & $py scripts\bench_vector_store.py @argv --data-dir "$env:TEMP\the-one-bench" --out "$env:TEMP\the-one-bench\table.md"
      Get-Content "$env:TEMP\the-one-bench\table.md"
      if ($LASTEXITCODE -ne 0) { throw "benchmark exited $LASTEXITCODE" }
  ]
```

**Run 0 (accidental, 2026-09-15 00:50–00:53 UTC)** — the first invocation
used `-v ARGS=` against a static `params:` value, so the task ran its
default `--corpus synthetic --n 20000 --queries 50`, all four cells. Kept
as a valid Windows 20k data point (3 min wall including provisioning):

| backend | dtype | n | build_s | disk_MB | p50_ms | p95_ms | max_ms | recall@k | peak_rss_MB | save_ms | restore_ms | status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| sqlite-vec | float32 | 20000 | 5.40 | 40.50 | 135.747 | 154.516 | 159.537 | 1.0000 | 221.50 | - | - | OK |
| sqlite-vec | int8 | 20000 | 3.35 | 10.43 | 77.221 | 99.379 | 101.107 | 0.9060 | 226.74 | - | - | OK |
| usearch | f16 | 20000 | 82.80 | 22.36 | 10.753 | 13.179 | 15.122 | 0.4320 | 226.74 | 244.374 | 110.920 | OK |
| usearch | i8 | 20000 | 35.15 | 12.60 | 5.158 | 6.152 | 6.365 | 0.3980 | 226.74 | 113.389 | 76.905 | OK |

Windows / Linux ratios at 20k (same vectors): sqlite-vec float32 p95
**11.6×** slower (154.5 vs 13.3 ms); usearch f16 p95 **20.9×** slower (13.2
vs 0.63 ms) and build **65×** slower (82.8 vs 1.27 s). Disk bytes and
recall identical to the byte, as they must be.

**Reading the synthetic recall column — a caveat the Flight Director adds
before the operator reads any table.** `usearch`'s synthetic recall@10 is
0.43 at 20k, 0.07 at 1M and 0.04 at 3M on Linux, yet **0.98 on the real
corpus**. The synthetic corpus is 64 tight Gaussian clusters (σ = 0.3):
at 3M each cluster holds ~47k near-equidistant members, and an HNSW graph's
top-10 among those is close to a random draw from the cluster — the known
HNSW failure on heavily clustered / near-duplicate data. sqlite-vec's
exhaustive scan is immune by construction (1.0 / 0.9995). So the synthetic
recall column is an index-recall figure for a pathological distribution,
**not** a retrieval-quality figure; DD-4's 0.95 floor applies to the
real-corpus column only, exactly as AC-6b states. The synthetic tables'
decision-grade columns are latency, build time, disk and RSS.

**Run 1 — build 60 (2026-09-15 01:48–03:19 UTC, 1 h 31 min wall, detached
client), fixed script (per-cell subprocess), `--corpus synthetic --n
1000000 --queries 200 --cells sqlite-vec:float32,sqlite-vec:int8`.** Free
disk at data dir 462.97 GB. Fingerprint `5c25c9f8…65e5b` — identical to
the Linux 1M fingerprint (same vectors). Build 59, the first attempt, was
aborted at 44 min when the host-side client was killed (see Flight
Director Notes); no rows had printed.

| backend | dtype | n | build_s | disk_MB | p50_ms | p95_ms | max_ms | recall@k | peak_rss_MB | save_ms | restore_ms | status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| sqlite-vec | float32 | 1000000 | 267.30 | 1980.08 | 7590.033 | 8332.508 | 9094.250 | 1.0000 | 1271.95 | - | - | OK |
| sqlite-vec | int8 | 1000000 | 177.72 | 511.30 | 4787.222 | 4867.738 | 5244.406 | 0.8630 | 1272.18 | - | - | OK |

Windows / Linux at 1M: float32 p95 **14.8×** (8,333 vs 564 ms), int8 p95
**8.2×** (4,868 vs 595 ms), build 7.0× / 5.8×. Disk and recall identical.
`peak_rss_MB` here is per-cell (fixed script) — both cells ~1.27 GB.

**Early-read verdict by the leg's rule**: both sqlite-vec cells miss the
p95 ≤ 250 ms bar at 1M by 19× (int8) and 33× (float32) on the operator's
platform, so the **3M sqlite-vec cells are skipped on Windows** as wasted
worker time. Labelled extrapolation for the record, applying the Linux
3M/1M ratio (float32 2.99×, int8 3.00× — an exhaustive scan is linear in
N): **~24.9 s (float32) and ~14.6 s (int8) p95 at 3M on Windows**. The
extrapolation assumes the per-distance cost is N-independent, which it is
for a linear scan.

**Run 2 — build 61 (2026-09-15 03:20–03:49 UTC, 29 min wall), `--corpus
synthetic --n 200000 --queries 200 --cells usearch:f16,usearch:i8`.** Free
disk 459.53 GB. Fingerprint `5c25c9f8…65e5b` (same vectors as Linux). A
matching **Linux 200k** run was made by the Flight Director on the dev host
for the ratio (`--data-dir /tmp/the-one-bench-fd`, fixed script):

| platform | backend | dtype | n | build_s | disk_MB | p50_ms | p95_ms | max_ms | recall@k | peak_rss_MB | save_ms | restore_ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Windows | usearch | f16 | 200000 | 1155.97 | 223.67 | 13.604 | 17.968 | 22.608 | 0.1500 | 1271.04 | 1907.855 | 1008.386 |
| Windows | usearch | i8 | 200000 | 497.12 | 126.01 | 6.627 | 8.458 | 10.369 | 0.1155 | 1271.71 | 1028.898 | 517.824 |
| Linux | usearch | f16 | 200000 | 34.01 | 223.64 | 0.712 | 0.909 | 1.111 | 0.1425 | 1281.09 | 130.338 | 146.979 |
| Linux | usearch | i8 | 200000 | 20.69 | 125.98 | 0.569 | 0.692 | 0.806 | 0.1390 | 1281.11 | 81.372 | 103.084 |

Windows / Linux at 200k: f16 p95 **19.8×**, build **34.0×**, restore
6.9×; i8 p95 **12.2×**, build 24.0×, restore 5.0×. Disk within 0.03 MB;
recall within noise (the synthetic-recall caveat above applies).

**Windows usearch at 1M and 3M — EXTRAPOLATED, not measured** (time was
the binding constraint: a measured 1M f16 build on this worker is ~2 h and
3M ~7 h; DD-8's fallback rule applied with the 200k ratios, which assume
the platform penalty — serial-SIMD distance kernels — is N-independent):

| cell | N | p95 (extrap.) | build (extrap.) | restore (extrap.) |
|---|---|---|---|---|
| usearch f16 | 1M | ~27 ms (Linux 1.37 × 19.8) | ~2.0 h (216 s × 34) | ~5.3 s (0.76 s × 6.9) |
| usearch f16 | 3M | ~41 ms (Linux 2.07 × 19.8) | ~7.2 h (761 s × 34) | ~24 s (3.5 s × 6.9) |
| usearch i8 | 1M | ~15 ms (Linux 1.22 × 12.2) | ~54 min (134 s × 24) | ~2.4 s |
| usearch i8 | 3M | ~17 ms (Linux 1.37 × 12.2) | ~3.2 h (476 s × 24) | ~7.7 s |

The p95 extrapolations sit two orders of magnitude under the 250 ms bar
even if the ratio were off by several times; the build-time
extrapolations are the material figure — they price DD-3's
rebuild-from-SQLite story on the operator's platform.

**Run 3 — build 62 (2026-09-15 03:49–03:58 UTC, 8 min wall), `--corpus
real`, all four cells.** Free disk 459.42 GB. 31,679 chunks embedded (Linux
embedded 31,638 — the `missions/` tree gained flight-log text between the
two runs; the 200 held-out queries are drawn by the same rule, so the
corpora are near-identical, not byte-identical).

| backend | dtype | n | build_s | disk_MB | p50_ms | p95_ms | max_ms | recall@k | peak_rss_MB | save_ms | restore_ms | status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| sqlite-vec | float32 | 31679 | 10.20 | 62.79 | 217.349 | 246.389 | 257.747 | 0.9950 | 430.97 | - | - | OK |
| sqlite-vec | int8 | 31679 | 2.37 | 16.18 | 139.571 | 158.329 | 171.220 | 0.9645 | 422.99 | - | - | OK |
| usearch | f16 | 31679 | 41.62 | 35.42 | 3.426 | 5.874 | 9.406 | 0.9800 | 456.62 | 336.636 | 144.314 | OK |
| usearch | i8 | 31679 | 17.71 | 19.95 | 1.770 | 4.463 | 8.643 | 0.9530 | 438.00 | 124.153 | 108.663 | OK |

Windows / Linux on the real corpus: sqlite-vec float32 p95 12.5× (246 vs
19.7 ms), usearch f16 p95 13.2× (5.9 vs 0.44 ms). Recall on the two
platforms: usearch i8 **0.9530 here vs 0.9465 on Linux** — the two runs
straddle DD-4's 0.95 floor on near-identical corpora, so that cell's
recall is *at* the floor within noise, not clearly above it.

### Reading the tables (Flight Director; no recommendation)

- **Bar**: p95 ≤ 250 ms for one k = 10 query on Windows at the largest
  measured N (DD-9 #1, set at planning). Latency columns are the second,
  cache-warm pass — steady-state interactive search; cold start is the
  `restore_ms` column (usearch) and ~0 for sqlite-vec.
- **sqlite-vec, both dtypes**: at today's real corpus (32k chunks) float32
  sits *on* the bar (246 ms) and int8 under it (158 ms); at 1M vectors on
  Windows they are 8.3 s and 4.9 s — 33× and 19× over — and ~25 s / ~15 s
  at the 3M ceiling (extrapolated, linear scan). The exhaustive scan is
  exact (recall 1.0 / 0.9995 synthetic; 0.995 / 0.9645 real) and keeps the
  single-file property. It clears the bar only below roughly 30k vectors
  on this platform.
- **usearch, both dtypes**: p95 5.9 / 4.5 ms real, ~27 / ~15 ms at 1M and
  ~41 / ~17 ms at 3M (extrapolated) — two orders of magnitude under the
  bar. Real-corpus recall f16 **0.98** (clears the 0.95 floor), i8 0.9465–
  0.953 (at the floor within noise). Costs: a per-KB sidecar outside the
  SQLite file; **build time on Windows** is the material figure — ~34×
  Linux, i.e. ~2 h for 1M and ~7 h for 3M f16 vectors (extrapolated),
  which is what a full rebuild-from-SQLite would cost at the ceiling;
  `restore` ~24 s at 3M (extrapolated). Disk: f16 1,024 B/vector (3.35 GB
  at 3M measured on Linux), i8 512 B/vector.
- **The synthetic recall column** for usearch (0.15 at 200k, 0.04 at 3M) is
  index recall on a pathologically clustered corpus and is not a
  retrieval-quality figure — see the caveat above; the real-corpus column
  is the one DD-4's floor applies to.
- **faiss-cpu divert**: not triggered — two cells clear the bar.
- **Conditions recorded for a usearch decision** (flight-end review
  findings): sidecar `save` is not atomic; a corrupt sidecar raises the
  library's raw error; `delete_kb` mutates before the re-entry guard. Leg 6
  would carry all three.


Not run by this leg (Developer scope ends at the Linux runs and a working
script) — the Flight Director runs the Windows one-off `fly execute` task
per the leg spec's Implementation Guidance §9 and DD-8's run order
(sqlite-vec 1M cells first), and records the task YAML, host facts,
tables, and any DD-8 RAM-fallback extrapolation here.

---

## Decisions

*(runtime decisions not in the original plan)*

### Flight Director Notes

**Planning — 2026-09-14.** Branch: to be cut from `mission/24-knowledge-bases`
as `flight/02-storage-and-embedding-foundation` at flight start; PR back into
the mission branch per the mission's "Branch Layout" section. No CI lane runs
on that PR — `make lint`, `make test-unit`, `pip-audit` and the frozen
`fly execute` are run by hand and recorded here before merge.

---

## Reconnaissance Report

Source artifacts walked against current code before leg design: the mission
document's code citations and the Flight 2 bullet in its Flights list, Flight
1's flight spec (DD-6) and flight debrief (Recommendations 1–3, Action Items),
and the open squawk list. Classification per `/mission-control:flight` Phase 1b.

| # | Source item | Class | Evidence | Recommendation |
|---|---|---|---|---|
| R1 | Mission: KB endpoints at `api.py:1370-1466` | confirmed-live (drifted range) | `the_one/interfaces/web/api.py:1370-1462` — eight routes, all `Request`-based hand-validation; no item update/status/search/reindex route | Keep; range is 1370–1462. Route gaps are Flight 2 scope |
| R2 | Mission: `mcp__` carve-out at `config.py:166-172` | drifted (wrong file) | Lives at `the_one/agent/config.py:146-172` (`AgentConfig.is_tool_enabled`), not `the_one/config.py` (that range is the legacy-data-dir rename). Content as described: `is_mcp = tool_name.startswith("mcp__")` | Correct the citation in `mission.md`. The decision itself belongs to the tool-registration flight, not Flight 2 |
| R3 | Mission: `parent_id` has zero readers | confirmed | Written at `repositories.py:443,448`, round-tripped at `:469`; DDL `schema.py:75`; no filter/join/traversal anywhere | Decision stays open for Flight 3 (folder→file); Flight 2 must not build a chunk hierarchy that competes with it |
| R4 | Mission F2 bullet: "widen the item-type CHECK via the v37 rebuild template" | confirmed-live (name drift) | Column is `kb_items.type` (`schema.py:76`: `CHECK (type IN ('file','url'))`), Pydantic `KBItem.type: Literal["file","url"]` (`models.py:94`); `item_type` has zero hits in the tree | Widen `type`; do not rename. v37 template at `schema.py:2141-2212`; v39's same-name rewrite note at `:2288-2299` argues for the simpler unconditional rewrite |
| R5 | Mission F2 bullet: "add app-level embedding config" | confirmed-live | No embedding settings anywhere (`the_one/config.py:52-78` Settings has none). Precedent: `app_metadata` key/value table, v31 (`schema.py:1936-1949`), `AppMetadataRepository` (`repositories.py:1237-1264`), plaintext, no encryptor | Design decision needed: where a backend choice that may carry a credential lives (see DD) |
| R6 | Mission F2 bullet: "add item status/error/hash/timestamp" | confirmed-live | `kb_items` has `status TEXT DEFAULT 'pending'` only — no CHECK, no error, no hash, no `updated_at`; no `UPDATE kb_items` statement exists in the tree; `KBItemRepository` (`repositories.py:422-477`) has no `update` | Flight 2 scope |
| R7 | Mission F2 bullet: "chunk and vector tables plus the FTS5 index over chunk text" | confirmed-live | No chunk table, no `vec0` table, no FTS anywhere (`grep fts5` → only the vec0 MATCH in diagnostics). FTS5 compiled into the dev venv's SQLite 3.45.1 (verified `CREATE VIRTUAL TABLE … USING fts5`) | Flight 2 scope. FTS5 in the **frozen** Windows bundle is unverified — see R13 |
| R8 | Mission F2 bullet: "repository and route gaps that leave no way to move an item out of `pending`" | confirmed-live | As R6; plus two pre-existing rough edges in the same routes: `create_kb_item` never checks the KB exists (FK `IntegrityError` → 500, `api.py:1443-1452`) and `delete_kb_item` ignores its `kb_id` path segment (`:1455-1462`) | Fold both edges into the route-gap leg; they are inside the surface Flight 2 already rewrites |
| R9 | Mission Constraint: FTS5 "compiled into the interpreter the app ships and entirely unused today" | partially-verified | Dev venv: yes. Frozen CPython 3.11 on Windows: not yet observed | Add an FTS5 line to the existing `doctor` gate set (unconditional, like the embedding probe) so the frozen run proves it — cheap, same shape as Flight 1's probes |
| R10 | Mission Constraint: `enable_load_extension` "genuinely varies across Python builds" | confirmed | Dev venv has it (`sqlite3.Connection.enable_load_extension` present, SQLite 3.45.1); frozen Windows proved it in Flight 1 (`sqlite-vec: OK` on `windows-worker`). App connection (`connection.py:45-58`) never calls it; the probe records this as Flight 2's work (`diagnostics.py:345-347`) | Flight 2 wires the load into the singleton connection with the probe's enable→load→disable discipline |
| R11 | F1 DD-6: "probe internals will need a light rewrite in Flight 2 to call through the seam" | partially-satisfied | Embedding probe's load path (`diagnostics.py:702-753`, `_force_hf_offline` `:665-679`) is exactly what the seam needs internally → mechanical swap. Store probes build throwaway tables and were never meant to integrate → no change needed | Scope the rewrite to the embedding probe only |
| R12 | F1 debrief Rec 1: benchmark stores on Windows or discount Linux | confirmed-live | usearch Windows wheels are `simd=serial` (F1 log, binary analysis); no benchmarking harness exists in the tree (no `bench*`, no `pytest-benchmark`); the only measurement surface is `doctor`'s detail line + `fly execute` | Apparatus DD needed (see DD) |
| R13 | F1 debrief Rec 2 / pyproject comment: remove the losing store in the same flight; pick up `hf-xet` (squawk 0049) | confirmed-live | `pyproject.toml:85-96` carries both stores with the comment "The loser is removed from the closure in Flight 2"; `hf-xet` is a hard dep of `huggingface-hub` on x86_64/arm64 (`uv.lock`), needs an override to drop; squawk 0049 open | Both land in the closure leg, verified by one frozen run |
| R14 | F1 debrief Rec 3: 247.1 MiB peak RSS is whole-process, not model-marginal | confirmed | F1 log "Frozen Windows Verification — Leg 2 (second run)" | Compute the float16-vs-int8 storage decision from DD-1 arithmetic, not from this figure |
| R15 | Mission: `models.py` is 360 lines, connector inference config removed | confirmed | `wc -l the_one/db/models.py` → 360 | Informational only |
| R16 | Mission Open Q: `kb__` tools vs whitelist gate | out-of-scope (F2) | `agent/config.py:166-172`; `factory.py` never reads `kb_ids` (`agent/config.py:110`: "reference IDs only — no functional behavior yet") | Belongs to the tool-registration flight. Flight 2 ships no agent tool |
| R17 | Discovered: Studio save path writes `kb_ids: []` on every agent save | new — out-of-scope (F2) | `studio.js:2035-2044` collects chips from a selector nothing renders; any API-set `kb_ids` is clobbered on UI save | Squawk candidate or fold into the Studio KB flight; flag to operator |
| R18 | Discovered: `KBItemRepository.get` has no caller and no route | confirmed-live | `repositories.py:434`; no `GET …/items/{item_id}` route | Route-gap leg adds the route |
| R19 | Discovered: no index on `kb_items(kb_id)` | confirmed-live | schema.py has no `idx_kb_items_*` | Add in v40, `CREATE INDEX` outside the `executescript` per `column-aware-index-create-for-rewind-paths` |
| R20 | Discovered: model2vec `encode()` defaults `use_multiprocessing=True` above 10,000 texts and `max_length=512` tokens | confirmed (venv probe) | `StaticModel.encode(sentences, max_length=512, batch_size=1024, use_multiprocessing=True, multiprocessing_threshold=10000)` | Seam must pin `use_multiprocessing=False` — a fork pool inside a uvicorn worker or a frozen bundle is a hazard — and own the 512-token truncation explicitly |
| R21 | Discovered: usearch `save()` returns bytes when given no path; `restore(buffer)` accepts bytes | confirmed (venv probe) | `Index.save(path_or_buffer=None) -> bytes`, `Index.restore(path_or_buffer, view=False)`; `sqlite_vec.serialize_int8` also exists | Widens the store design space: a usearch index could be persisted as a BLOB inside SQLite rather than a sidecar file — see DD |

**Items flagged for operator decision** (not auto-retired): R2 (citation fix in
`mission.md` — trivial, proposed to do during this planning pass), R17 (defect
outside Flight 2's surface), R9 (add an FTS5 doctor probe — proposed yes).

### Flight Director Notes — planning, design review

- **Crew interview (2026-09-14)** settled: recon follow-ups (citation fix,
  FTS5 probe, squawk 0050 for the Studio `kb_ids` clobber); settings live in
  `app_metadata` as two separate records with defaults, API only, UI later;
  seam with both stores, benchmark, human chooses, loser removed; benchmark
  as a committed script run on `windows-worker` via a one-off `fly execute`;
  full chunking policy now, app-wide, never per-KB; four-state item status
  with CHECK; **no provider-delegating backend** — the operator settled on
  non-LLM local embeddings as the product, and the mission was amended in
  five places to record it (outcome, Context, success criterion, Constraints,
  Environment Requirements) rather than worked around; no HAT leg.
- **Empirical premises verified on this host before the spec was written**:
  `vec0` partition keys + `vec_int8` binding + delete-by-rowid; `usearch`
  `save()`/`restore()` to bytes and path; FTS5 external-content delete;
  `aiosqlite` extension coroutines; `SQLITE_MAX_LENGTH` 1e9 (rules out
  usearch-as-BLOB at the ceiling); model2vec `encode` defaults
  (`use_multiprocessing=True` above 10k texts, `max_length=512`).
- **Design review cycle 1 (Architect, Opus) — `approve with changes`.** Two
  high-severity findings, both verified empirically by the reviewer and both
  accepted: (1) explicit `BEGIN`/`COMMIT` on the shared `aiosqlite` connection
  cannot deliver atomicity — another coroutine's `commit()` commits a partial
  write, and `BEGIN` raises under exactly the concurrency that motivates it;
  replaced by a write lock (DD-13). (2) plain `INTEGER PRIMARY KEY` recycles
  rowids, so a re-index could map a stale vector id to different text — a
  silent wrong answer; replaced by `AUTOINCREMENT` (DD-5). Six medium findings
  fixed: upsert semantics defined; the probe rewrite's test impact stated
  honestly; CHECKs as frozen inline literals; `indexing→pending` requeue;
  extension loading moved from the connection factory into the store (the
  factory rationale was shown false — a `vec0` DB opens and migrates without
  the extension); Leg 1 split (six legs now). Seven suggestions adopted,
  including setting the operator's latency bar **before** the benchmark runs
  — the reviewer's 200k-vector probe suggests sqlite-vec may miss any
  reasonable bar at 3M, so the `faiss-cpu` divert is live rather than
  theoretical. Changes are substantive → cycle 2.
- **Design review cycle 2 (same Architect) — `approve with changes`.** All
  cycle-1 fixes verified landed except one: the write lock was scoped to
  multi-statement writers, and the reviewer modelled a plain single-statement
  repository write committing mid-transaction — the previous chunks were
  destroyed with the lock in place. Fixed by widening the rule to **every
  committer** (`write_transaction()` guard wrapping every existing repository
  write, non-reentrant with re-entry detection, lint-enforced by a repo-source
  guard test; convention renamed `db-writes-hold-the-write-lock`). The
  reviewer also showed the second-connection alternative fails under WAL
  (`database is locked`), which turns DD-13's rejection from a preference
  into a measured fact. Two mediums fixed: `truncated` now has a stated
  computation (a `tokenize` pass on inputs over 512 chars, ~27 % worst-case)
  and the vector suite no longer depends on Leg 3's stub. Three lows fixed
  (retry route accepts `indexing`; DD-10's window is first-use, `_loaded`
  flag; norm tolerance 1e-3 against a measured 1.83e-4). S8–S10 and Q1–Q3
  adopted. **Two cycles used — the workflow's maximum.** Escalating the
  proceed decision to the operator at the spec walkthrough, per the Flight 1
  Leg 2 precedent: every finding arrived with a verified fix and none
  persisted across cycles, so the remaining risk is implementation-level and
  is covered by each leg's own design review and the flight-end Reviewer.
- **Spec walkthrough and operator decisions (2026-09-14)**: proceed past the
  two-cycle review maximum (same rationale as Flight 1 Leg 2 — every finding
  fixed and verified, none persisted; per-leg design reviews and the
  flight-end Reviewer cover the implementation-level residue); **latency bar
  set at p95 ≤ 250 ms** for one k = 10 query on Windows at the largest
  measured N, recorded here before any benchmark number exists; squawk 0051
  logged for the stale `api.py:4642-4647` aiosqlite comment (Leg 1 fixes the
  `schema.py:319-327` twin in-leg). Flight moved `planning` → `ready`.

### Flight Director Notes — flight start (2026-09-14)

- Phase file `.flightops/agent-crews/leg-execution.md` loaded and validated
  (`## Crew`, `## Interaction Protocol`, `## Prompts`; six prompt sections,
  each fenced). Developer: Sonnet. Reviewer: Sonnet on security-sensitive
  diffs, Haiku otherwise — tier recorded per review.
- Prerequisites at flight start: `fly -t the-one status` → logged in;
  `windows-worker` `platform: windows` `running` (the two Linux workers are
  `stalled` — not needed by this flight); `uv` 0.10.0 on PATH.
  **`windows-worker` RAM still unrecorded** — Leg 5's design records it
  before the benchmark runs and applies DD-8's fallback if needed.
- Branch `flight/02-storage-and-embedding-foundation` cut from
  `mission/24-knowledge-bases` at `88972cb`. Flight `ready` → `in-flight`.
- Six legs planned; review and commit deferred to after the last autonomous
  leg per the workflow — except that Leg 5 ends at a human decision
  checkpoint, so the flight-end review/commit runs **twice**: once after
  Leg 5 (legs 1–5 reviewed and committed so the benchmark numbers and the
  code that produced them are on record before the operator decides), and
  once after Leg 6.

### Flight Director Notes — Leg 1 design

- Leg `01-v40-schema-and-item-lifecycle` written from the code as it stands:
  41 `commit()` sites in `repositories.py` plus one in `api.py`'s rotation
  endpoint (`:4850`) are the full set the DD-13 sweep must cover; the 40 in
  `schema.py` are migration stamps and are exempt by stated rule.
- **Risk tier: HIGH.** Three triggers, any one sufficient: a schema migration
  with a table rebuild; a shared-interface change to every repository's
  write path (the `write_transaction` sweep) plus the rotation endpoint,
  which is a credential surface; a lifecycle/state-machine (the item status
  transition table). Design review by a Developer follows.
- **Leg 1 design review, cycle 1 — `approve with changes`.** Nine empirical
  probes by the reviewer, all holding: the v40 rebuild preserves the three
  seed rows (including a self-referential `parent_id`) and maps NULL/junk
  status to `pending`; `AUTOINCREMENT` does not recycle; the external-content
  FTS5 commands work; the conditional `UPDATE` + `rowcount` shape already
  exists at `repositories.py:265-270`; wrapping the rotation endpoint in
  `write_transaction` preserves the commit → `install_key` no-await
  invariant (an `asyncio.Lock` release does not yield); no repository method
  commits in a loop or nests another committer, so the 41-site sweep is
  safe; the rotation failure test's class-level `commit` patch still fires
  through the guard. One medium (a `TestSchemaV39` citation off by ~100
  lines) and two lows (explicit vocabulary guard in `update_status`; one
  `now` for both stamps) fixed in the artifact. Cosmetic only — no second
  cycle. Leg marked `ready`. Proceeding to implementation.

### Flight Director Notes — Leg 1 close, Leg 2 design

- Leg 1 landed by the Developer with three recorded deviations, all
  accepted: a defensive fresh-create branch in v40 for a hand-built
  partial-schema fixture that never runs `SCHEMA_V1`; the retry route
  restricting to `failed`/`indexing` explicitly (the generic transition table
  also admits `indexed→pending`, which AC-10 said must 409 via retry); a
  line-wrap in the rotation comment to dodge a guard-test regex. The 584 s
  unit-gate figure is a concurrent-run artefact (the Developer's scoped
  re-verification overlapped it); Leg 2's clean run sets the flight's
  baseline. Orchestration note: the Developer paused three times waiting on
  background test runs; resumed each time with a foreground-only instruction.
  Later spawn prompts say "foreground, 600000 ms timeout" up front.
- Leg `02-chunk-repository-and-fts` written from the landed code. **Risk
  tier: HIGH.** Triggers: a shared-interface change to `run_doctor`'s gate
  list (four consumers: `main.py`, `tests/test_doctor.py`, both CI lanes);
  transaction semantics on the singleton (the first multi-statement writer
  built on `write_transaction`); and a return-type change to
  `KBItemRepository.delete`. Design review by a Developer follows.
- **Leg 2 design review, cycle 1 — `approve with changes`.** One high: the
  leg's `check_fts()` used the one-argument `('integrity-check')`, which the
  reviewer showed reports clean on all three desync scenarios; the
  two-argument `('integrity-check', 1)` form detects all three and stays
  clean on empty, synced and correctly-deleted states. Corrected in the leg
  and AC-7 rewritten; DD-5's "malformed on the next MATCH" claim narrowed in
  `flight.md` (only a MATCH that selects FTS `text` raises; `search_keyword`'s
  join filters orphans silently). One medium: `agents.md` citations shifted
  by Leg 1's edits, plus the "Consumers of the exit code" name list must gain
  `fts5` — both fixed. Everything else verified holding (quoting scheme,
  `lastrowid`, `executemany`, unaliased `bm25`, stemming, return-type
  callers). No re-review: the one substantive change is a SQL form the
  reviewer itself verified. Leg marked `ready`. Proceeding to implementation.

### Flight Director Notes — Leg 2 close, Leg 3 design

- Leg 2 landed with no spec deviations. Clean unit gate, run alone:
  **4,024 passed / 10 skipped / 472.22 s** — this is the flight's baseline.
  The Developer flagged 2.2 s over the 455–470 s band the flight
  checkpoint names; accepted: +26 tests on a ~470 s suite is inside
  run-to-run noise (Flight 1's own readings spanned 453–469 s at a fixed
  count). The checkpoint's band is re-read as "no growth beyond test-count
  growth" and the flight-end entry says so. `doctor` on this host now prints
  nine gates, `fts5: OK` among them.
- Leg `03-embedding-seam-and-settings` was drafted while Leg 2 implemented
  (its inputs were Leg 1's landed code plus Leg 2's `ChunkRecord` shape,
  now confirmed landed as specified). **Risk tier: HIGH.** Triggers: the
  `embedding model` probe's detail line is read by name in both CI lanes
  and by `tests/test_doctor_embedding_model.py` (a shared interface with
  consumers); a lifespan startup change (the warm-up task); a new route
  namespace; the constants and offline helper move packages
  (canonical-import change with the probe as consumer). Design review by a
  Developer follows.
- **Leg 3 design review, cycle 1 — `approve with changes`.** Two highs, both
  verified by the reviewer: a `Literal` field cannot carry the custom 422
  message AC-9 requires (pydantic 2.13 — `Field(description=…)` never
  reaches `errors()`; a `field_validator` raising `ValueError` does) → the
  settings models use `str` + validators; and `TestEmbeddingProbeGating`'s
  citation had drifted into Leg 2's `TestProbeFts5` → corrected (`:816`).
  Mediums: the constant re-binding alias served no consumer → dropped;
  guard #2 (weights file missing) has no test anywhere → AC-3 adds one;
  `diagnostics.py` citations shifted +47 → corrected. Suggestions adopted:
  zero-token inputs yield a zero vector and flip the batch to float64
  (reviewer found it) → seam pins float32, docstring states the caveat;
  "full" chunk defined as a hard cap hit; character-level overlap fallback
  stated; both warm-up call sites fire-and-forget. Cosmetic-to-moderate,
  each with a verified fix — no second cycle. Leg marked `ready`.
- **Drafting ahead.** While Leg 3 implements, Legs 4 (`vector-store-seam`)
  and 5 (`store-benchmark`) were drafted from the landed Leg 1–2 code, the
  ready Leg 3 spec and verified probes (int8 + cosine on `vec0`, rowid
  delete on a partition-keyed table, `usearch` i8/f16 top-1, `remove` of an
  absent key does not raise). Their design reviews wait for a stable tree
  after each preceding leg lands. The one-off Windows benchmark task YAML
  is prepared in the session scratchpad (never committed; pasted into this
  log with each run). Real corpus measured: 1,151 markdown files, 25.7 MB,
  ~25k chunks at DD-7 defaults.

### Flight Director Notes — Leg 3 close, Leg 4 design

- Leg 3 landed. Unit gate alone: **4,287 passed / 10 skipped / 496.64 s**
  (+263 tests, +24 s over Leg 2's 472 s — proportional). Three deviations,
  all accepted: (1) the leg's overlap rule ("latest boundary at or before
  `end − overlap`") bounds overlap from *below*, the opposite of AC-7 — the
  Developer implemented "earliest boundary at or after `end − overlap`" and
  proved it over a 212-case seeded sweep; a spec wording error, corrected
  in the code, recorded here; (2) one flat sorted boundary set instead of
  three tiers — equivalent, simpler; (3) a suite-wide `conftest.py` autouse
  fixture stubbing the embedding backend, needed because
  `create_knowledge_base` now kicks `warm_up()` and every pre-existing KB
  test would otherwise race a real load — the real-load file opts out. The
  probe's new line on this host: `embedding model: OK — 512-dim float16
  model → float32 seam, norm 1.0000, truncated=0 (…, peak RSS 262.6 MiB)`.
  The Developer backgrounded the unit gate once more despite the
  instruction; the process watch + nudge pattern recovered it in one step.
- Leg `04-vector-store-seam` (drafted ahead) goes to design review now that
  the tree is stable. **Risk tier: HIGH** — a native extension loaded on the
  app connection (security-sensitive surface per the crew file's Reviewer
  tiering), two new committers under the write-lock rule, a store-owned
  DDL, and the delete routes gaining a second side effect.
- **Leg 4 design review, cycle 1 — `approve with changes`.** Two highs, both
  verified by the reviewer and fixed in the artifact: `quantize_int8`'s
  formula lacked the `.astype(np.int8)` cast (`serialize_int8` raises
  `struct.error` on the float result); `open()`'s `_loaded` check needed
  double-checked locking or two concurrent opens load twice (the
  `get_embedding_backend()` precedent). Mediums: the knowledge-settings
  routes already carry `notes` and a generic top-level-key 422 guard —
  Leg 4 extends rather than replaces and drops its proposed custom message;
  `vec0` rowids are unique table-wide, not per partition — the shared suite
  uses disjoint id ranges per KB and the docstring states the invariant.
  Suggestions adopted: named `_build_store` seam; synchronous `setdefault`
  for per-KB lock creation; `sqlite_vec.load(conn)` on aiosqlite silently
  loads nothing (recorded); dangling vectors after re-index noted as a
  Flight 3 input. Citation drift (+9 lines in `repositories.py`) corrected.
  No second cycle. Leg marked `ready`; implementation follows.
- **Orchestration slip, recovered.** The Leg 4 review-fix edit aborted on a
  mismatched replacement target *after* the implementing Developer had been
  spawned in the same tool round, so the Developer briefly held an
  artifact without the fixes. The edit was re-applied within a minute and
  the Developer was messaged the eight corrections by name with an
  instruction to re-read the artifact before writing further code. Lesson
  for the remaining legs: apply artifact edits and verify the status line
  in one step, spawn in the next — never both in one round.

### Flight Director Notes — Leg 4 close, Leg 5 design

- Leg 4 landed. Unit gate alone: **4,360 passed / 10 skipped / 506.07 s**
  (+73 tests, +9 s). One deviation, accepted with a note: AC-10 requires
  every store write to raise on re-entry, but `UsearchStore.upsert`/`delete`
  touch no SQL until `flush`, so the Developer added an empty
  `write_transaction` block at the top of each to trip the guard before the
  in-memory mutation. It satisfies the contract ("never call a store from
  inside a transaction") uniformly across backends; the flight-end Reviewer
  should confirm the empty block commits nothing and holds the global lock
  only for the check. Observed `usearch` `flush` cost at 512 dims, f16:
  ~3–8 ms and ~1.17 KB per vector on disk at 50–5,000 vectors — Leg 5's
  3M-cell save will be seconds to tens of seconds, which is the DD-3
  rebuild-cost input.
- Leg `05-store-benchmark` (drafted ahead) goes to design review. **Risk
  tier: HIGH** — not blast radius (a script and one test) but consequence:
  its numbers drive Leg 6's irreversible closure change, so the review's
  job is to break the measurement (ground truth, timer scope, disk
  accounting, the RAM fallback) rather than the code.
- **`windows-worker` RAM recorded** (one-off `fly execute` task, PowerShell
  `Win32_ComputerSystem`/`Win32_OperatingSystem`, 2026-09-14): **31.71 GB
  total, 14.22 GB free, 20 logical CPUs.** Flight prerequisite closed. The
  3M benchmark cells (usearch f16 ~3–4 GB resident; sqlite-vec float32 ~6 GB
  DB file) fit; DD-8's labelled extrapolation will not be needed. Temp-disk
  free space was not captured by the task (the drive query errored after
  the RAM lines); Leg 5's script prints it alongside RAM so the first
  Windows run records it.
- **Leg 5 design review, cycle 1 — `needs rework`.** Three highs, all
  measurement-integrity findings, all resolved in the artifact: (1) AC-3
  asked the int8 cells to quantise the query before the timer, but the
  landed stores quantise internally with no pre-quantised entry point —
  rewritten: internal quantisation is a genuine per-query cost inside the
  timed region, no new seam invented; (2) the synthetic recall column
  contradicted DD-8's "recall only on the real corpus" — reconciled as two
  recall meanings (index recall on synthetic, retrieval recall on real,
  the 0.95 floor applying to the latter only); DD-8's wording clarified in
  `flight.md`; (3) the free-disk-space print promised in this log was
  missing — added to host facts, plus a per-cell free-space guard
  (print-and-skip) and per-cell cleanup so a 3M multi-cell run needs one
  cell's space. Mediums: `dim` from `backend.dim` (the suite-wide stub is
  8-dim); `journal_mode=WAL` on the script's connection so the checkpoint
  step is real. Lows: restore query excluded from the latency array; two
  timing passes, report the second; `uv export` without extras. Raised to
  the Flight Director and parked: CI's `lint.yml` does not cover
  `scripts/` — a squawk candidate after the flight. Substantive changes →
  cycle 2.
- **Leg 5 design review, cycle 2 — `approve with changes`.** All round-1
  fixes verified. One new medium the cleanup fix introduced: closing only
  the store leaves the `aiosqlite` connection holding the DB file, and on
  Windows `os.remove` of an open SQLite file raises WinError 32 — the
  multi-cell Windows run would crash on the platform the decision rests on.
  Fixed: close the store, close the connection, then delete, then open the
  next cell. Two lows fixed. Two cycles used; nothing persisted across
  cycles. Leg marked `ready`; implementation follows.

### Flight Director Notes — Leg 5 close, Windows runs

- Leg 5 landed. Unit gate alone: **4,368 passed / 10 skipped / 512.29 s**
  (+8 tests). Linux tables in `## Store Benchmark`. One in-leg correction:
  the usearch i8 free-space estimate raised from 512 to 660 B/vector after
  the Linux 1M run measured a 1.29× ratio (the leg's own edge case fired).
- Windows run order per DD-8: (1) sqlite-vec float32 + int8 at 1M — the
  early read against the p95 ≤ 250 ms bar; on Linux those cells are already
  at 563 / 595 ms, so if they miss on Windows the 3M sqlite-vec cells are
  skipped as wasted worker time per the leg; (2) usearch f16 + i8 at 1M;
  (3) usearch at 3M; (4) real corpus. Each is its own `fly execute` from a
  clean tree state (the uncommitted Legs 1–5 are uploaded by `-i repo=.`).
  Run 1 started 2026-09-15T00:50:11Z.

### Flight Director Notes — flight-end review, cycle 1 (Legs 1–5)

- **Reviewer tier: Sonnet** — the diff touches the encryption-rotation
  endpoint (credential surface) and loads a native extension on the app
  connection. The review ran in parallel with Windows run 1: the numbers
  are log data, not code.
- **Verdict: not confirmed — two blocking**, both reproduced by the reviewer
  from the committed artifacts and both accepted: (1) `peak_rss_MB` in the
  benchmark is a process-lifetime watermark, so every cell after the first
  in an invocation is contaminated (the Linux tables show identical RSS
  for cell pairs) — fix: per-cell subprocess isolation, and every RSS
  value recorded before the fix is annotated as cumulative; (2)
  `UsearchStore._path_for` builds a sidecar path from an unsanitised,
  client-suppliable `KnowledgeBase.id` — fix: an id charset validator on
  the model plus a containment assert in the store. Fix Developer spawned.
- **Non-blocking dispositions**: fixed in the same pass — benchmark
  pre-cleanup inside the per-cell `try`, `restore_ms` labelled, the
  `conftest.py` exemption comment, non-dict settings values 422 not 500;
  artifact items fixed by the Flight Director — Leg 4's checklist ticked,
  this log's Summary refreshed. **Conditions on a usearch decision in Leg 6**
  (recorded for the operator's checkpoint): sidecar `save` is not atomic
  (no tmp + replace — a kill mid-save destroys the last good generation);
  a corrupt sidecar raises the library's raw error rather than
  `VectorStoreStaleError`; `delete_kb` mutates before the re-entry guard.
  **Squawk candidates after the flight**: rotation's `except Exception`
  narrower than the guard's `BaseException`; the commit-guard test is a
  substring scan; nested unknown keys inside `embedding`/`chunking` are
  dropped rather than refused (`extra="forbid"`); the benchmark tests
  assert only `| OK |`; the live-DDL check is a substring match on vec0's
  DDL text; no `shape[-1] == dim` guard on `upsert`/`query`.
- **Flight-end review, cycle 2 — confirmed.** Both blocking fixes verified
  empirically by the reviewer (a live two-cell run produced distinct RSS
  values 90.05 / 93.15 MB; `_path_for("../../../evil")` raises with the
  model layer bypassed); the fix-now items and artifacts verified; 700
  scoped tests green, ruff clean, no regression. The one residual — Leg 4's
  final checklist box — ticked by the Flight Director. `[HANDOFF:confirmed]`
  is taken as given on the unit gate passing (running now, post-fix).

### Flight Director Notes — Legs 1–5 committed; Windows run 1 relaunched

- Post-fix unit gate, foreground, alone: **4,394 passed / 10 skipped /
  511.46 s** (+26 tests from the fix pass; wall time flat). Review cycle 2
  confirmed. Legs 1–5 set `completed`; single commit for the five legs
  follows (the flight's second commit will carry the Windows tables and the
  operator's decision entry; Leg 6 is its own commit after review).
- **Windows run 1 (build 59) was aborted at 01:39 UTC after 44 min** — not
  by the worker: the host ran low on memory during the post-fix unit gate
  and the harness killed the background `fly execute` client, and a one-off
  build dies with its client. No rows had printed (rows print at cell end).
  Relaunched as **build 60** with the fixed (per-cell subprocess) script,
  detached via `setsid nohup … & disown` so a client-side kill cannot abort
  it again; output retrievable with `fly watch -b 60` regardless of the
  client. Lesson recorded: never run a multi-hour one-off build from a
  harness-managed foreground/background command.
- Committed as `c315cf5`; draft PR **#197** → `mission/24-knowledge-bases`.
- **Windows plan revised on time, not RAM.** At 20k the Windows/Linux
  ratios were 11.6× (sqlite-vec p95) and 65× (usearch build). Scaled, a
  usearch 1M build on `windows-worker` is ~4 h and 3M ~14 h — not a
  flight-time apparatus. So: build 60 (sqlite-vec 1M) runs to completion as
  the definitive early read; usearch runs on Windows at **200k** (build ~15
  min) and on the **real corpus** (31k chunks), and the 1M/3M usearch
  Windows figures are **extrapolated** from the measured Windows/Linux
  ratios at 200k, labelled, per DD-8's fallback rule with "time" substituted
  for "RAM" as the binding constraint and stated as such.

### Flight Director Notes — DD-9 decision checkpoint (2026-09-15)

- **Operator decision: `usearch`, dtype `f16`.** Recorded here per DD-9
  before Leg 6 is designed. The operator's reasoning, restated from the
  checkpoint conversation: the bar was p95 ≤ 250 ms per k = 10 query on
  Windows at the largest measured N; only the two `usearch` cells clear it
  (f16 ~27 ms at 1M, ~41 ms at 3M, extrapolated; 5.9 ms on the real
  corpus), whereas `sqlite-vec` clears it only below roughly 30k vectors on
  this platform and would cap knowledge bases at about today's corpus size.
  Between the `usearch` dtypes, f16 is chosen for accuracy margin: real-
  corpus recall@10 0.98 against DD-4's 0.95 floor, where i8 sits at the
  floor within noise (0.9465–0.953). The i8 disk saving (512 vs 1,024
  B/vector) is not worth the recall risk at this stage.
- **Accepted costs**: the per-KB sidecar outside the SQLite file (DD-3's
  rebuild-from-SQLite path, ~2 h for 1M f16 vectors on `windows-worker`,
  extrapolated); `restore` ~24 s at 3M (extrapolated); f16 on-disk 1,024
  B/vector (3.35 GB at 3M, measured on Linux).
- **Consequences for Leg 6** (`store-decision-and-closure`), per DD-9:
  `sqlite-vec` is the loser — remove the package from `pyproject.toml`,
  regenerate `uv.lock`, drop its `doctor` probe and by-name CI assertions in
  both lanes, its `upx_exclude` / `binaries` spec entries, its store backend
  module and tests; move the `kb_vector_index` DDL into a v41 block (DD-3);
  `numkong` stays (usearch won); add the `[tool.uv] override-dependencies`
  that drops `hf-xet` (squawk 0049 completed against Leg 6's commit); one
  `fly execute` frozen run proves `RESULT: PASS`. Leg 6 also carries the
  three conditions recorded at the flight-end review for a `usearch`
  decision: sidecar `save` must become atomic (tmp + replace), a corrupt
  sidecar must surface as `VectorStoreStaleError` rather than the library's
  raw error, and `delete_kb` must guard re-entry before mutating.
- `faiss-cpu` divert: not triggered; Flight 1's shelf stays shelved.
