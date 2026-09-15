# Flight Debrief: Storage and Embedding Foundation

**Date**: 2026-09-15
**Flight**: [Storage and Embedding Foundation](flight.md)
**Status**: landed → completed at debrief
**Duration**: 2026-09-14 (planning + Legs 1–5) – 2026-09-15 (decision checkpoint, Leg 6, four frozen runs)
**Legs Completed**: 6 of 6

Sources: the flight log in full; all six leg artifacts; the Developer
debrief interview (Sonnet, with an independent unit-suite run); the
Architect design review (Sonnet); a three-question human interview; and
the Flight Director's own orchestration record. PR #197 is ready for
review against `mission/24-knowledge-bases`, not yet merged.

## Outcome Assessment

### Objectives Achieved

The flight's objective was met in full. Every later flight in the mission
now builds on: a v40 schema with a real item lifecycle (`pending` /
`indexing` / `indexed` / `failed`, conditional-UPDATE transitions, a
`KBItemTransitionError`), chunk storage with `AUTOINCREMENT` ids that are
never recycled and an external-content FTS5 index kept in sync by the
repository; an embedding seam whose production backend is the bundled
`potion-retrieval-32M` model, with app-wide embedding and chunking
settings behind `/api/knowledge-settings`; a vector-store seam that
carried two backends through the benchmark and now has one; and the
closure change that removed the loser. The store decision was made by the
operator, on evidence, at a leg boundary, against a bar set before any
number existed: **`usearch`, dtype `f16`**. `sqlite-vec` cleared the
p95 ≤ 250 ms bar only below roughly 30k vectors on Windows and missed it
by 19–33× at 1M; `usearch` f16 sat two orders of magnitude under it and
cleared the 0.95 real-corpus recall floor with margin (0.98) where `i8`
sat on the floor.

Beyond the plan, the flight closed squawk 0049 (`hf-xet` out of the
closure, installer 141,827,664 → 134,790,292 bytes), hardened the
surviving store on three review-found conditions (atomic sidecar save,
corrupt sidecar reported as stale, `delete_kb` guard before mutation),
fixed a doctor output-encoding crash, and repaired the Windows CI
apparatus (per-build venv, `--no-deps` install, exit-code checks) after
the frozen-run gate exposed that the persistent worker had been masking a
silently failed install.

### Mission Criteria Advanced

| Mission criterion | This flight's contribution |
|---|---|
| Bundled, local, non-LLM embedding backend; no network | **Landed**: the seam and its production backend (`LocalStaticBackend`), offline guards, unconditional doctor gate. Fully met pending Flight 5's agent-facing use. |
| Retrieval combines semantic and keyword matching | **Both substrates landed** (usearch vectors, FTS5 `search_keyword`); fusion policy deferred by DD-12. |
| New handler or vector store without touching the pipeline | **Vector-store half landed**: the `VectorStore` Protocol survived a full build-and-delete of one implementation with no shape change. Extractor seam is Flight 3. |
| Register a folder, see each item's index status | **Lifecycle half landed**: status vocabulary, error column, transitions, routes. Folder type and pipeline are Flight 3. |
| Upgrades with no data loss; unit gate green; frozen installer builds | **Advanced and stressed**: v40 + v41 proven against rewind/rerun; gate green at 4,370; the frozen installer builds — after four runs that each fixed a real defect. |

## What Went Well

- **The decision process held its shape under pressure.** DD-9 put the
  choice with the operator, at a leg boundary, against a bar recorded
  before the benchmark ran. The Architect had warned the early Linux
  numbers might pre-decide the flight; the Windows numbers did decide it,
  and nothing in Leg 6 re-litigated the choice. The operator's own
  reading at the checkpoint was that the tables plus a plain-language
  brief were what made the call easy (human interview).
- **Design review caught the flight's most consequential defect before
  code existed.** DD-13's write lock was first scoped to multi-statement
  writers; the Architect modelled a single-statement `commit()` landing
  mid-transaction and the rule widened to every committer, enforced by a
  source-scan guard test that never needed widening from Leg 1 to Leg 6.
  Two other pre-code catches of the same quality: `AUTOINCREMENT` over a
  recyclable rowid (DD-5), and the one-argument FTS5 `integrity-check`
  that reports clean on a real desync (Leg 2).
- **Every leg's acceptance criteria were mechanically verifiable** (exact
  DDL, exact test-count deltas, exact grep counts, exact transition
  tables). The Developer interview found none vague. Where a leg was
  wrong it was in Implementation Guidance prose — and each such error
  (the chunker overlap direction, Leg 5's pre-quantised timer, Leg 4's
  AC-10 for an in-memory store) was found and corrected before landing.
- **The frozen-run gate earned its cost four times over.** None of the
  four defects it exposed was visible from any Linux-side check, and one
  of them (the persistent Windows worker masking a failed install) had
  been latent since Flight 1, because Flight 1 only ever added packages.
- **Test discipline scaled.** About 350 tests were added across the
  flight at flat per-test cost: no new file appears among the fifteen
  slowest, because real model loads stay in one dedicated file and the
  stub backend covers the rest (the Flight 1 convention, reused as
  designed).
- **The Protocol seams and the dispatcher paid off exactly as promised.**
  Removing `sqlite-vec` was a `git rm` plus a one-branch dispatcher — no
  connection-factory edit, no migration edit (DD-10's rationale,
  vindicated). Store-owned-until-decided / migration-owned-after (DD-3's
  `kb_vector_index`) landed as v41 byte-for-byte.
- **Per-cell subprocess isolation in the benchmark** turned a review
  finding (peak RSS is a process-lifetime watermark) into a reusable
  measurement pattern, and the review verified the fix empirically.

## What Could Be Improved

### Process

- **Important — a leg-end checkpoint should lead with a plain-language
  brief.** The operator received the raw tables and a no-recommendation
  reading note, then asked for a simpler explanation before deciding.
  The interview answer: brief first, tables and reading note as backing
  detail. This is a methodology note for `/mission-control:flight`
  checkpoint design, not a criticism of DD-9's "no recommendation" rule,
  which stays.
- **Important — the frozen run stays a flight-end gate, budgeted as a
  diagnostic** (operator's call at interview). Four runs at ~8 minutes
  each was the right price for four real defects; the lesson is to plan
  for iterations, not to move the gate earlier.
- **Important — the same review shape found the same defect class twice.**
  A raising mock that never inspects its call arguments proved nothing
  (`TestAtomicSave`, fixed to assert the `.usearch.tmp` path); the
  Developer interview found the sibling shape in the benchmark's
  per-cell-RSS regression test, whose canned rows would pass against the
  original bug's mechanism. Reviewers should ask of every mock-based
  regression test: "would this pass against the code before the fix?"
- **Minor — hand-built migration fixtures bit twice**, exactly as Leg 1
  predicted: v40 needed a `kb_items`-absent branch and v41 an
  `app_metadata`-absent guard, both forced by fixtures that stamp
  `schema_version` past tables they never created. This is a convention
  gap (see Documentation), not a code gap.
- **Minor — an orchestration slip at Leg 4** (artifact edit failed after
  the Developer was already spawned) was recovered in a minute and the
  lesson recorded: edit and verify in one round, spawn in the next. It
  did not recur.
- **Minor — long-running one-off builds must never run under a
  harness-managed command.** Windows run 1 died with its client when the
  host ran low on memory during a unit gate. The `setsid nohup … &
  disown` pattern held for all four Leg 6 runs.

### Technical

- **Important — the empty `write_transaction` in `UsearchStore.upsert`/
  `delete`** (the acquire-and-release shim that satisfies DD-13's
  re-entry rule for an in-memory store) takes the app-wide write lock
  and issues a real empty commit on every batch. Flight 3's bulk
  indexing is exactly the workload that will call it per chunk batch;
  measure early, and consider a re-entry-only check that skips the
  transaction round-trip.
- **Important — before any agent-facing query path (Flight 5)**:
  `search_keyword`'s `k` flows unbounded into `LIMIT ?`
  (`repositories.py:808`), and `VectorStore.upsert`/`query` have no
  `shape[-1] == dim` guard. Both are one-line fixes, both named in the
  flight-end review, both resource-exhaustion or silent-garbage vectors
  once a tool argument reaches them.
- **Minor — two fire-and-forget warm-up tasks are unreferenced**
  (`app.py:338`, `api.py:1425`, `asyncio.create_task(...)` with the
  handle dropped). Every other background task in the codebase holds its
  handle; worst case today is a GC'd warm-up and a slower first call.
- **Minor — `save_vector_store_settings` has no production caller.**
  The record that makes DD-3's mismatch detection real is written only
  by tests and the benchmark; Flight 3's pipeline must write it on first
  index.
- **Minor — dormant paths.** `i8`/`quantize_int8` is implemented, tested
  and benchmarked with no default user (deliberate; revisit only if a
  Studio setting ever exposes dtype). The inert `kb_vectors` vec0 table
  in any dev database that opened the old store is permanent — a vec0
  table cannot be dropped without the module — and the v41 comment is
  the only thing stopping a future "clean-up" from crashing the rewind
  path.
- **Minor — thin spots the Developer interview named**: `TestSchemaV41`
  lacks the double-`ensure_schema` idempotency and full rewind tests its
  v40 sibling has, and its `app_metadata` guard is covered only
  incidentally by a v32 fixture; `_ensure_loaded`'s dtype/dim-mismatch
  branch has no test; `query()`'s distances are asserted sorted, never
  against an independently computed cosine value; `delete_kb` unlinks
  without `missing_ok=True` while its sibling does.
- **Minor — DD-8's extrapolation is provisional at the true ceiling.**
  The Windows 1M/3M usearch figures are 200k measurements scaled by a
  Windows/Linux ratio assumed N-independent; never checked at 1M/3M on
  Windows. Flight 3's checkpoint granularity should treat the ~2 h / 1M
  build figure as an order of magnitude, and re-measure incremental
  upsert cost once a real large corpus exists.

### Documentation

- `the_one/agents.md` Project Conventions should name four patterns this
  flight instantiated (see Recommendation 3): the empty-transaction
  re-entry guard, the atomic sidecar save, the migration-fixture rule,
  and store-owned-until-decided.
- The synthetic-vs-real recall distinction (index recall on a clustered
  synthetic corpus vs. the retrieval recall DD-4's floor governs) lives
  only in the flight log's "Reading the tables". One sentence in
  `agents.md`'s Knowledge storage section would stop a later flight
  quoting 0.04 as a quality figure.
- `squawk 0051` (stale aiosqlite autocommit comment in `api.py`) is still
  open; Leg 1 fixed only the `schema.py` twin.
- Flight 1's debrief action items: squawks 0047, 0048, 0049 are all
  completed; the `.flightops/ARTIFACTS.md` mission-branch question is
  still undecided and PR #197 was correctly opened against the mission
  branch this time.

## Test Metrics

Two figures, not directly comparable, both recorded honestly:

| Run | Command | Result |
|---|---|---|
| Flight closure (Leg 6 commit, alone, foreground) | `make test-unit` | **4,370 passed / 10 skipped / 499.22 s** |
| Debrief (Developer interview) | `run-tests.sh tests/ -m 'not browser and not live and not pixel' --durations=15` | 4,411 passed / 13 skipped / 28 warnings / **547.11 s**, 0 failures, no flakes |

The debrief run's explicit `-m` replaced `pyproject.toml`'s `addopts`
marker expression, so the 12 `requires_bwrap` integration tests ran (bwrap
is present on this host) — that, not new code, explains most of the +41 /
+3 delta — and unrelated pytest processes from another project were
running concurrently, so the wall time is contention-inflated. **Lesson:
the debrief metrics command must be `make test-unit` verbatim**, then a
second invocation for durations if wanted; never a hand-written `-m`.

Clean in-flight series, all alone and foreground: Flight 1 debrief 3,950
/ 466.75 s → Leg 2 4,024 / 472.22 s (flight baseline) → Leg 3 4,287 /
496.64 s → Leg 4 4,360 / 506.07 s → Leg 5 4,368 / 512.29 s → post-review
4,394 / 511.46 s → Leg 6 4,370 / 499.22 s (−25: the removed sqlite-vec
parametrisation and probe tests outweighed the new hardening tests). Net
for the flight: **+346 tests at +27 s** — proportional, no slow cluster.
The fifteen slowest tests are all pre-existing sandbox/PTY/timeout tests
(`test_mcp_pool.py::test_drain_timeout_handles_stuck_worker` 10.0 s is
the outlier); the only flight-added entry is the benchmark's real
two-subprocess test at 1.22 s, by design.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| DD-13 widened from multi-statement writers to every committer, lint-enforced | Architect modelled a single-statement `commit()` landing mid-transaction | Yes — already the `db-writes-hold-the-write-lock` convention |
| `UsearchStore.upsert`/`delete` open an empty `write_transaction` to trip the re-entry guard | The store's writes are in-memory until `flush`; AC-10 required uniform re-entry behaviour | Yes, as a named pattern — with Flight 3 measuring its cost |
| "Vectors landed" means `flush`, not `upsert` (DD-3 refinement) | HNSW save is O(N); cannot save per upsert | Yes — Flight 3's pipeline contract |
| DD-8 RAM fallback replaced by a time-based one (Windows 1M/3M usearch extrapolated from 200k) | Worker had RAM; a 1M Windows build is ~2 h, 3M ~7 h | Case-by-case; label every extrapolation |
| Synthetic recall reinterpreted as index recall; the 0.95 floor applies to the real corpus only | Two tables carried a recall column with different meanings | Yes — state both meanings wherever the numbers are quoted |
| Chunker overlap rule inverted from the leg's prose | Spec wording error; 212-case sweep proved the corrected rule | n/a — corrected in code and log |
| Defensive table/record-presence guards in v40 and v41 | Hand-built migration fixtures stamp `schema_version` past tables they never created | Yes — convention for migration tests (Rec. 3) |
| Three usearch hardening fixes added in Leg 6 | Found only at flight-end review from usearch's real crash and exception behaviour | Yes — atomic save as a named pattern |
| Doctor `emit` made encode-safe; `→` replaced by `->` | cp1252-piped stdout on the Windows worker crashed the doctor | Yes — probe details are ASCII; the emitter cannot die on its own output |
| Concourse Windows task builds in a per-build venv, installs with `--no-deps`, checks every native exit code | Persistent worker site-packages masked a silently failed install; pip hash mode walks transitive requirements; PowerShell ignores native exit codes | Yes — both lanes now do this |
| `i8` dtype kept as a valid non-default | Working, tested, benchmarked; deleting it buys nothing | Yes, until a UI setting forces the question |
| Leg 6 carried four fix passes and four frozen runs instead of one | Each run exposed an independent defect | Budget the flight-end frozen run as a diagnostic with iterations (operator's call) |

## Key Learnings

1. **A bar set before the numbers exist is what makes an operator decision
   fast and defensible.** The p95 ≤ 250 ms bar separated the candidates
   by two orders of magnitude. Its blind spot was build time, which turned
   out to be the binding cost at the ceiling and had to be reasoned about
   ad hoc — the next benchmark-driven decision should set a build/rebuild
   bar alongside the latency bar.
2. **Removing a dependency is the first real test of a frozen pipeline.**
   Adding packages never exposes a persistent build environment; removing
   one did, and revealed that the install step had been failing silently
   with the environment papering over it. A frozen lane must build in a
   throwaway environment and fail on every native exit code, or it proves
   nothing about the closure.
3. **Non-ASCII in diagnostic output is a Windows CI defect waiting to
   happen.** Interactive consoles hide it (UTF-8 console I/O); every CI
   lane pipes. Probe detail strings stay ASCII and the emitter degrades
   instead of raising.
4. **A raising mock is only a test if it inspects what it was called
   with.** Ask of every regression test: would it pass against the code
   before the fix? Two instances in one flight.
5. **The hand-built migration fixture is a recurring hazard, now twice
   confirmed.** Migration blocks that touch an unconditionally-present
   table need a presence guard until the fixtures replay the real chain.
6. **Extrapolation labels travel.** The DD-8 label discipline ("Windows 3M
   figures are extrapolated; N-independence assumed") is what let the
   decision entry state its own uncertainty honestly. Keep it.
7. **Store-owned-until-decided / migration-owned-after** is a clean shape
   for any schema element whose owner is an open question at planning.

## Recommendations

1. **Flight 3 planning must take four contracts from this flight as
   inputs, not rediscover them**: two-transaction write ordering with
   `flush` as "landed" and an explicit flush cadence (not per chunk);
   `indexing → pending` requeue via the transition table as the
   resume-not-restart primitive; `VectorStoreStaleError → rebuild_from`
   as the only stale recovery, treated as an exceptional event because it
   re-embeds everything; and writing the `knowledge.vector_store` record
   on first index. Add: measure the empty-transaction cost of
   `UsearchStore.upsert` under bulk load in Flight 3's first leg.
2. **Close the seam's input bounds before Flight 5's agent-facing query
   path**: bound `search_keyword`'s `k` and add a `shape[-1] == dim` guard
   on `upsert`/`query`. Squawk-sized; see Action Items.
3. **Name four conventions in `the_one/agents.md`**: *empty-transaction
   re-entry guard* for in-memory-until-flush stores; *atomic sidecar
   save* (tmp in the same directory, `os.replace`, then the registry row;
   a crash between the two is stale-and-recoverable, never silent);
   *migration tests replay the real chain* (fixtures must not stamp
   `schema_version` past tables they never created; until they comply,
   blocks touching an always-present table carry a presence guard); and
   *store-owned-until-decided*. Add the synthetic-vs-real recall sentence
   to Knowledge storage.
4. **Methodology: checkpoints lead with a plain-language brief** (options,
   costs, what the bar says), tables and reading note behind it; the
   no-recommendation rule stays. And: the flight-end frozen run is
   planned as a diagnostic with iterations, never a formality.
5. **Set a build/rebuild-time bar alongside any latency bar** in the next
   benchmark-driven decision, and re-measure usearch build and
   incremental-upsert cost on Windows at 1M once Flight 3 has a real
   corpus — DD-8's N-independence assumption is unverified at the ceiling.

## Action Items

- [ ] Bound `search_keyword`'s `k` and add the `shape[-1] == dim` guard on `VectorStore.upsert`/`query` — **squawk 0054** (defect, routine; required before Flight 5).
- [ ] Hold the two warm-up `create_task` handles (`app.py:338`, `api.py:1425`) like every other background task — **squawk 0055** (defect, routine).
- [ ] `PUT /api/knowledge-settings`: refuse nested unknown keys inside `embedding`/`chunking` (`extra="forbid"`) instead of dropping them — **squawk 0056** (defect, routine).
- [ ] Encryption-rotation endpoint: catch `BaseException` to match the write-lock guard — **squawk 0057** (credential surface: Sonnet-tier review at completion) (defect, routine).
- [ ] Tests: `TestSchemaV41` idempotency + full rewind + a dedicated `app_metadata`-absent guard test; `UsearchStore` dtype/dim-mismatch staleness test; a cosine-distance value test for `query()`; `delete_kb` `missing_ok=True` — **squawk 0058** (servicing, routine).
- [ ] Commit-guard test: AST walk instead of a substring scan; benchmark tests assert on the numeric cells, not only `| OK |` — **squawks 0059, 0060** (servicing, routine).
- [ ] CI `lint.yml` / `ci/tasks/lint.yml` do not cover `scripts/` (parked at Leg 5 design review) — **squawk 0061** (servicing, routine).
- [ ] `the_one/agents.md`: the four named conventions and the recall sentence (Recommendation 3) — **squawk 0062** (servicing, routine).
- [ ] Carry into Flight 3 planning: Recommendation 1's four contracts, the empty-transaction cost measurement, and the provisional Windows build-time figures.
- [ ] Decide the `.flightops/ARTIFACTS.md` mission-branch question (still open from Flight 1's debrief).
- [ ] Merge PR #197 into `mission/24-knowledge-bases`.
