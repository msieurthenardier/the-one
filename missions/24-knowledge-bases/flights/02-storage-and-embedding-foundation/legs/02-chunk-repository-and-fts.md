# Leg: chunk-repository-and-fts

**Status**: completed
**Flight**: [Storage and Embedding Foundation](../flight.md)

## Objective

Give `kb_chunks` and `kb_chunks_fts` their repository — one atomic
replace-per-item write with explicit FTS sync, the keyword-search primitive,
FTS rebuild and integrity helpers, and cascade cleanup on KB and item delete —
and add the `fts5` gate to `doctor` with both CI lanes asserting it.

## Context

- Flight DD-5 (external-content FTS5 synced by the repository, never by
  triggers; the recorded costs — a cascade is an unguarded back door, a missed
  sync surfaces as `database disk image is malformed`; hence `rebuild_fts`
  and `check_fts`), DD-12 (the keyword primitive returns `(chunk_id, score)`
  pairs; fusion is not this flight), DD-13 (every committer inside
  `write_transaction`; no nesting; the guard test), DD-11 (`_probe_fts5`
  unconditional; both lanes assert by name).
- Leg 1 landed (flight log, "Leg 1 — implementation landed"): v40 with
  `kb_chunks(id INTEGER PRIMARY KEY AUTOINCREMENT, item_id, kb_id, seq, text,
  char_start, char_end, created_at, UNIQUE(item_id, seq))` at
  `schema.py:2519-2530` and `kb_chunks_fts USING fts5(text,
  content='kb_chunks', content_rowid='id', tokenize='porter unicode61')` at
  `:2532-2534`; `write_transaction(conn)` in `the_one/db/_write_lock.py`
  (commit on exit, rollback on `BaseException`, same-task re-entry raises);
  the source guard in `tests/test_db_write_lock.py` (`commit()`/`rollback()`
  only in `_write_lock.py` and `schema.py`); `KnowledgeBaseRepository.delete`
  and `KBItemRepository.delete` are one-statement `DELETE`s inside the guard,
  relying on FK cascade — which reaches `kb_chunks` but **not** the FTS
  shadow tables.
- Nothing here embeds or stores vectors. The vector store's cleanup on KB and
  item delete is wired in Leg 4 at the call sites; this leg makes the SQL
  side complete and returns the deleted chunk ids so Leg 4 has what it needs.
- The chunker arrives in Leg 3. This leg defines the record type the chunker
  will produce, so the two legs agree on one shape without a dependency.

## Inputs

- `the_one/db/schema.py:2519-2541` — the landed `kb_chunks`, `kb_chunks_fts`
  and index DDL.
- `the_one/db/_write_lock.py` — `write_transaction`, `reset_for_test`.
- `the_one/db/_kb_types.py` — the tuples and `KBItemTransitionError`.
- `the_one/db/repositories.py` — `KnowledgeBaseRepository.delete`
  (`:401-405`), `KBItemRepository.delete` (`:474-479`) and
  `KBItemRepository._row_to_model`, then the `# ── MCP source repository ──`
  banner — the chunk repository goes between.
- `the_one/db/models.py` — `KBItem` (`:88+`); `KBChunk` is new.
- `the_one/diagnostics.py` — `ProbeResult` (`:46`), the unconditional probe
  shape (`_probe_embedding_model`, `:681+`: broad `except`, never routes
  through `_vector_probe_outcome`), the `gates = [` list in `run_doctor`
  (`:843`), the docstring at `:795-802` that enumerates "eight" gates.
- `.github/workflows/windows-installer.yml:72-86` (`grep -q "<name>: OK"`
  lines) and `ci/tasks/windows-installer-build.yml:59` (the PowerShell
  `foreach ($needle in @(…))` list) — the by-name assertion sites.
- `the_one/main.py:52-53`, `README.md:52`, `docs/windows-install.md:129` —
  the three doctor enumerations.
- `tests/test_doctor.py` — `TestProbeSqliteVec` (`:418`) for the
  swap-the-module-reference technique (`sqlite3.Connection` is an immutable
  C type), `TestEmbeddingProbeGating` (`:727`) for the source-inspection
  "does not use the frozen-only helper" test.
- `the_one/agents.md` — the `### Diagnostics` section (heading at `:1219`;
  "The eight gates" table at `:1228-1239`; the "Consumers of the exit code"
  paragraph at `:1226`, which lists the CI-grepped probe names; the
  probe-contract paragraph "Six of the eight…" at `:1243`); the
  `db-writes-hold-the-write-lock` convention entry Leg 1 added.
- Verified during planning on this host (SQLite 3.45.1): external-content
  FTS5 `INSERT INTO kb_chunks_fts(kb_chunks_fts, rowid, text) VALUES
  ('delete', ?, ?)`, `('rebuild')`, `('integrity-check')`, and `bm25()`
  ordering all behave as the flight states.

## Outputs

- `the_one/db/_kb_types.py`: `@dataclass(frozen=True) class ChunkRecord:
  seq: int; text: str; char_start: int; char_end: int` — the input shape for
  `replace_item_chunks` and the output shape of Leg 3's chunker.
- `the_one/db/models.py`: `KBChunk(id: int, item_id: str, kb_id: str, seq:
  int, text: str, char_start: int, char_end: int, created_at: str)`.
- `the_one/db/repositories.py`: `KBChunkRepository(conn)` with
  `replace_item_chunks(item_id, kb_id, chunks: Sequence[ChunkRecord]) ->
  list[int]`, `list_for_item(item_id) -> list[KBChunk]`, `get_many(ids) ->
  list[KBChunk]`, `count_for_kb(kb_id) -> int`, `delete_for_item(item_id)
  -> list[int]`, `delete_for_kb(kb_id) -> list[int]`, `search_keyword(kb_id,
  query, k) -> list[tuple[int, float]]`, `rebuild_fts() -> None`,
  `check_fts() -> bool`; a module-level `_fts_delete_rows(conn, rows)` helper
  shared with the two cascade hooks; `KnowledgeBaseRepository.delete` and
  `KBItemRepository.delete` issue the FTS delete commands for the chunks
  they are about to cascade away, inside their existing transaction;
  `KBItemRepository.delete` now returns `list[int]` (the chunk ids removed).
- `the_one/diagnostics.py`: `_probe_fts5()` registered in `gates` after
  `sqlite-vec`/`usearch` and before `embedding model`; `run_doctor`'s
  docstring says nine gates and names it.
- Both CI lanes assert `fts5: OK` by name; the three enumerations mention
  FTS5.
- `the_one/agents.md`: the Diagnostics gate table gains the `fts5` row (nine
  gates, unconditional), the "Consumers of the exit code" list of
  CI-grepped names gains `fts5`, and the probe-contract paragraph's "six of
  the eight" becomes "seven of the nine"; a new `### Knowledge storage`
  subsection under `## Subsystem contracts` records the FTS sync rule (the
  repository is the only writer of `kb_chunks_fts`; a raw `DELETE FROM
  kb_items`/`knowledge_bases` outside the repositories is a defect), the
  no-nesting composition rule, and the `ChunkRecord` shape. Leg 4 extends
  it with the seams.
- Tests: new `tests/test_kb_chunks.py`; `tests/test_doctor.py::TestProbeFts5`;
  additions to `tests/test_db_repositories.py` for the cascade hooks.
- Flight log entry; leg ticked in `flight.md`.

## Acceptance Criteria

- [x] AC-1 `replace_item_chunks(item_id, kb_id, chunks)` on an item with no
      chunks inserts them with `seq` and offsets preserved, returns the new
      ids in `seq` order, and every returned id is `MATCH`-able in
      `kb_chunks_fts` immediately after.
- [x] AC-2 Calling it again with different chunks removes the old rows **and
      their FTS entries** (a `MATCH` on a token unique to the old text
      returns nothing; `check_fts()` is `True`) and the new ids are all
      greater than every id previously issued (never recycled).
- [x] AC-3 Atomicity, single task: a chunk sequence whose Nth insert fails
      (a duplicate `seq` violating `UNIQUE(item_id, seq)`) leaves the
      previous chunks and their FTS rows exactly as they were and raises.
- [x] AC-4 Atomicity, concurrent: task A runs `replace_item_chunks` and is
      made to fail after its first insert (an `asyncio.Event`-sequenced
      failure inside a monkeypatched execute, or a duplicate `seq` placed
      last), while task B performs a plain single-statement repository
      write (`KnowledgeBaseRepository.create`) in A's gap. Afterwards A's
      item still has its previous chunks and FTS rows, and B's row exists.
- [x] AC-5 `search_keyword(kb_id, "rare-token", k)` returns the planted
      chunk id first; a chunk with the same token in **another** KB is not
      returned; results are ordered by `bm25` (best first); `k` is honoured;
      a query containing FTS5 operator characters (`"`, `*`, `(`, `-`, `OR`,
      `NEAR`) does not raise and is matched as plain terms; an empty or
      whitespace-only query returns `[]` without touching the DB.
- [x] AC-6 `KnowledgeBaseRepository.delete` on a KB with chunked items leaves
      zero `kb_chunks` rows, zero `kb_chunks_fts` rows for those ids (`SELECT
      count(*) FROM kb_chunks_fts WHERE rowid IN (…)` is 0 and a `MATCH` on
      their tokens returns nothing), and `check_fts()` is `True`.
      `KBItemRepository.delete` does the same for one item and returns the
      removed chunk ids.
- [x] AC-7 `rebuild_fts()` recovers a deliberately desynchronised index: after
      a raw `DELETE FROM kb_chunks` (bypassing the repository) `check_fts()`
      returns `False`; after `rebuild_fts()` it returns `True` and `MATCH` on
      the deleted text returns nothing. Also: `check_fts()` is `True` on an
      empty index, on a correctly synced multi-row index, and after a
      repository-driven delete. (Design review verified: only the
      two-argument `('integrity-check', 1)` command detects the desync; the
      one-argument form reports clean in every scenario, and
      `search_keyword`'s join silently filters orphans rather than raising.)
- [x] AC-8 `_probe_fts5` returns `ok=True` with a detail naming the SQLite
      version and the matched rowid; when `sqlite3` is swapped for a module
      whose `connect()` raises on `CREATE VIRTUAL TABLE` it returns
      `ok=False` (never raises) **regardless of `is_frozen()`**; a
      source-inspection test asserts it never calls `_vector_probe_outcome`;
      `run_doctor` prints `  fts5: OK — …` on this host and both CI lanes
      contain the literal `fts5: OK` assertion.
- [x] AC-9 The `tests/test_db_write_lock.py` source guard still passes (no new
      `commit()`/`rollback()` outside the two files); `make test-unit` green;
      ruff clean; wall time within the 455–470 s band when run alone (Leg 1's
      584 s was a concurrent-run artefact — this leg's figure is the clean
      baseline for the flight).

## Verification Steps

- AC-1–7: `PYTHON=.venv/bin/python bash scripts/run-tests.sh
  tests/test_kb_chunks.py tests/test_db_repositories.py -x --timeout 60`.
- AC-8: `… tests/test_doctor.py -x --timeout 60`; `.venv/bin/the-one doctor`
  on this host shows the `fts5: OK` line; `grep -n "fts5: OK"
  .github/workflows/windows-installer.yml ci/tasks/windows-installer-build.yml`
  shows one hit each.
- AC-9: `… tests/test_db_write_lock.py`; `make test-unit`; `ruff check
  the_one/ tests/`; `ruff format --check the_one/ tests/`.

## Implementation Guidance

1. **`ChunkRecord`** in `_kb_types.py` (frozen dataclass, no Pydantic — it is
   a plain value crossing from the chunker to the repository). Validate
   nothing here; `UNIQUE(item_id, seq)` and `NOT NULL` do the enforcing.

2. **`KBChunk`** model in `models.py` next to `KBItem`.

3. **`_fts_delete_rows(conn, rows)`** — module-level in `repositories.py`,
   takes `(rowid, text)` pairs and issues `INSERT INTO
   kb_chunks_fts(kb_chunks_fts, rowid, text) VALUES ('delete', ?, ?)` per
   row via `executemany`. External-content FTS5 needs the *original* text
   to delete, so callers must `SELECT id, text` **before** the `DELETE FROM
   kb_chunks`. This helper is the only FTS-delete site.

4. **`KBChunkRepository`** between the item repo and the MCP banner.
   - `replace_item_chunks`: one `write_transaction`: `SELECT id, text FROM
     kb_chunks WHERE item_id = ?` → `_fts_delete_rows` → `DELETE FROM
     kb_chunks WHERE item_id = ?` → for each `ChunkRecord` in `seq` order,
     `INSERT INTO kb_chunks (item_id, kb_id, seq, text, char_start,
     char_end) VALUES (…)` and collect `cur.lastrowid` (do **not** rely on
     `RETURNING`; the frozen CPython 3.11 bundle's SQLite version is not
     pinned by this project) → `executemany("INSERT INTO kb_chunks_fts(rowid,
     text) VALUES (?, ?)", zip(ids, texts))` → return `ids`. Any exception
     rolls the whole thing back via the guard; that is AC-3/AC-4.
   - `delete_for_item` / `delete_for_kb`: same select-then-FTS-delete-then-
     DELETE shape, each in its own transaction, returning the ids.
   - `search_keyword(kb_id, query, k)`: `bm25(kb_chunks_fts)` and `WHERE
     kb_chunks_fts MATCH ?` must name the **unaliased** table even though
     the rowid select aliases it `f` — `bm25(f)` / `f MATCH` raise `no such
     column: f` (verified). Build the FTS query by splitting on
     whitespace and quoting each term (`'"' + term.replace('"', '""') + '"'`),
     joined by spaces (FTS5 implicit AND); return `[]` for no terms. SQL:
     `SELECT f.rowid, bm25(kb_chunks_fts) AS score FROM kb_chunks_fts f JOIN
     kb_chunks c ON c.id = f.rowid WHERE kb_chunks_fts MATCH ? AND c.kb_id = ?
     ORDER BY score LIMIT ?` — `bm25()` is lower-is-better (negative);
     return it as-is and document that. The KB filter is a join because the
     FTS table carries no `kb_id` column (v40 is frozen).
   - `rebuild_fts`: `INSERT INTO kb_chunks_fts(kb_chunks_fts) VALUES
     ('rebuild')` inside `write_transaction`. `check_fts`: run **`INSERT INTO
     kb_chunks_fts(kb_chunks_fts, rank) VALUES ('integrity-check', 1)`** —
     the two-argument form, which for an external-content table also
     verifies the index against the content table (the one-argument form
     checks only the index's internal structure and reports clean on a
     desync — verified by the design review against three bypass
     scenarios); FTS5 raises `sqlite3.DatabaseError` on mismatch — catch
     that and return `False`; return `True` otherwise. No transaction needed for the
     check (it writes nothing) — but it must not be issued while another
     task's `write_transaction` is mid-flight on the FTS table, so take the
     guard anyway (a read inside the guard is allowed; the rule is about
     commits).
   - `list_for_item`, `get_many` (`WHERE id IN (…)` with the expanded
     placeholder list; preserve the caller's order in Python), `count_for_kb`.

5. **Cascade hooks.** In `KnowledgeBaseRepository.delete`, before the
   `DELETE FROM knowledge_bases` and inside its existing `write_transaction`:
   `SELECT id, text FROM kb_chunks WHERE kb_id = ?` → `_fts_delete_rows`.
   In `KBItemRepository.delete` likewise by `item_id`, and return the ids.
   The FK cascade then removes the chunk rows; the FTS side is already
   clean. Do not call `KBChunkRepository` methods from inside these (they
   open their own transaction → re-entry `RuntimeError`); use the module
   helper.

6. **`_probe_fts5`** in `diagnostics.py`, placed after `_probe_usearch`:
   `sqlite3.connect(":memory:")`, `CREATE VIRTUAL TABLE t USING fts5(x,
   tokenize='porter unicode61')`, insert one row with a known token, `SELECT
   rowid, bm25(t) FROM t WHERE t MATCH ?`, assert rowid 1 returns; detail
   `f"fts5 available (SQLite {sqlite3.sqlite_version}); porter+unicode61
   MATCH round-trip returned rowid 1"`. Broad `except Exception` → `ok=False`
   with the exception text. **Unconditional**: never `_vector_probe_outcome`,
   never `is_frozen()` — FTS5 is a mission constraint in every build
   (DD-11). Register it in `gates` between `usearch` and `embedding model`.
   Update the docstring count at `:795-802`.

7. **CI lanes.** `windows-installer.yml`: add `grep -q "fts5: OK"
   doctor.out` after the `usearch` line. `windows-installer-build.yml`: add
   `"fts5: OK"` to the `@(...)` needle list. Both are literal one-line edits;
   the flight-end frozen run is what proves them.

8. **Enumerations.** `main.py:52-53`, `README.md:52`,
   `docs/windows-install.md:129`: add "FTS5" where the vector stores are
   listed.

9. **Tests.** `tests/test_kb_chunks.py` uses the same `conn` fixture idiom
   as `tests/test_db_repositories.py` (`:55-80`) plus a module-local
   `autouse` fixture calling `the_one.db._write_lock.reset_for_test()`.
   For AC-4 reuse the `asyncio.Event` sequencing from
   `tests/test_db_write_lock.py`. For AC-7 desynchronise with a raw
   `DELETE FROM kb_chunks` **outside** any repository. `TestProbeFts5` in
   `test_doctor.py` follows `TestProbeSqliteVec`'s module-swap technique for
   the failure path and copies `TestEmbeddingProbeGating`'s
   `inspect.getsource` check for the "no frozen-only helper" assertion.
   Add `"fts5"` to whatever `TestRunDoctorHost` asserts about the printed
   gate names if it enumerates them.

10. **`agents.md`**: the gate table row, the "seven of the nine" edit, the
    new `### Knowledge storage` subsection (short — the seams land in Leg 4
    and extend it).

11. **Flight log entry** with test counts, `make test-unit` figures (run
    alone — see AC-9), ruff status, and the `search_keyword` scoring note
    (bm25 sign) for Leg 4's benchmark and the later fusion flight.

## Edge Cases

- **Empty `chunks`** in `replace_item_chunks`: deletes existing chunks and
  their FTS rows, inserts nothing, returns `[]` — a zero-length extraction
  is a valid re-index result.
- **FTS delete needs the original text**: select before delete, always;
  passing wrong text corrupts the index silently until the next `MATCH`
  (that is what `check_fts` is for).
- **`bm25()` is negative and lower is better**: tests order by ascending;
  Leg 4's benchmark and the future fusion must not assume higher-is-better.
- **Porter stemming**: `MATCH "foxes"` finds `fox` — tests use a token that
  stems to itself (e.g. `zq7xk`) for exact-planting assertions.
- **`get_many([])`**: return `[]` without a query (`IN ()` is a syntax error).
- **Very long `IN` lists**: `SQLITE_MAX_VARIABLE_NUMBER` varies by build
  (250,000 on this host; 32,766 is the SQLite default since 3.32); chunk
  `get_many` in batches of 500 regardless.
- **`check_fts` on an empty index**: `True`.
- **The FTS table is a virtual table**: `sqlite_master` membership tests in
  Leg 1 already tolerate shadow tables; nothing here changes them.
- **Windows**: nothing platform-specific; FTS5's presence in the frozen
  bundle is exactly what `_probe_fts5` exists to prove there.

## Files Affected

- `the_one/db/_kb_types.py` — `ChunkRecord`
- `the_one/db/models.py` — `KBChunk`
- `the_one/db/repositories.py` — `_fts_delete_rows`, `KBChunkRepository`, cascade hooks in the two `delete`s
- `the_one/diagnostics.py` — `_probe_fts5`, `gates`, docstring
- `.github/workflows/windows-installer.yml`, `ci/tasks/windows-installer-build.yml` — `fts5: OK`
- `the_one/main.py`, `README.md`, `docs/windows-install.md` — enumerations
- `the_one/agents.md` — gate table, probe-contract count, `### Knowledge storage`
- `tests/test_kb_chunks.py` — new
- `tests/test_doctor.py` — `TestProbeFts5`
- `tests/test_db_repositories.py` — cascade-hook tests
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

Design review (Developer, 2026-09-14) verified every cited location against
the tree with Leg 1 landed and ran empirical probes for the quoting scheme,
`lastrowid`, `executemany`, `bm25` aliasing, `LIMIT ?`, porter stemming,
`('rebuild')`, and the return-type change's callers. One high finding: the
one-argument `integrity-check` cannot detect an external-content desync —
corrected to the `rank=1` form and AC-7 rewritten. One drifted citation
(`agents.md` Diagnostics section, shifted by Leg 1's convention entry)
corrected; the repository `delete` citations rewritten as absolute lines.
