# Leg: store-benchmark

**Status**: completed
**Flight**: [Storage and Embedding Foundation](../flight.md)

## Objective

Produce the numbers the operator's store decision rests on: a committed,
parameterised benchmark script exercising every DD-4 cell through the Leg 4
seam, run on the Linux dev host and on `windows-worker`, with every figure
and the exact commands pasted into the flight log — and stop at the decision
checkpoint without removing anything.

## Context

- Flight DD-8 (act path, read path, corpora, the four cells, the measured
  quantities, the RAM fallback and its labelled extrapolation, run order:
  Windows 1M sqlite-vec cells first), DD-9 (decision inputs in order; the
  bar **p95 ≤ 250 ms** recorded at planning; `faiss-cpu` divert live if no
  cell clears it), DD-4 (the float32 cell stores upcast float16; recall
  floor 0.95 on the real corpus), DD-3 (`usearch` `flush` = `save`, and the
  `restore` cost prices the sidecar).
- Legs 1–4 landed: `SqliteVecStore` / `UsearchStore` with the shared
  Protocol (`open/upsert/delete/delete_kb/query/count/flush/close`),
  `quantize_int8`, `LocalStaticBackend`, `chunk_text`, `ChunkRecord`,
  `_peak_rss_bytes` in `diagnostics.py`.
- The real corpus is the repository's own markdown: `docs/`, `missions/`,
  `the_one/agents.md`, `README.md` — measured at planning: 1,151 files,
  25.7 MB, so roughly 25,000 chunks at DD-7's defaults. The static model
  embeds that in seconds; the exact float32 matrix (25k × 512 × 4 B ≈ 51 MB)
  fits in RAM for the recall ground truth.
- `windows-worker` RAM is recorded (flight prerequisite closed 2026-09-14):
  31.71 GB total, 14.22 GB free, 20 CPUs — the 3M cells run there directly.
  Free temp-disk space was not captured; the script prints it (and RAM,
  Windows via `ctypes` `GlobalMemoryStatusEx`; POSIX via `os.sysconf`) at
  start so the first Windows run records it, and the per-cell free-space
  guard uses it.
- The one-off Windows task YAML is **not committed** (Flight 1's peak-RSS
  reproduction precedent): its full text is pasted into the flight log
  with the run so the measurement is reproducible from the log alone.
- This leg is HIGH-tiered not for its blast radius (a script, one test, no
  shared interface) but because its output drives Leg 6's irreversible
  closure change: a wrong ground truth or a mis-scaled timer mis-decides the
  flight. The design review's job is to break the measurement, not the code.

## Inputs

- `the_one/vectors/` (Leg 4) — both stores and `quantize_int8`;
  `the_one/embeddings/local.py::LocalStaticBackend`,
  `the_one/knowledge/chunking.py::chunk_text`, `the_one/db/_kb_types.py::ChunkRecord`;
  `the_one/db/schema.py::ensure_schema`; `the_one/diagnostics.py::_peak_rss_bytes`.
- `scripts/refresh_embedding_model.py` — the generator-script precedent
  (`argparse` `main(argv)`, `verify()` helpers, non-zero exit on breach,
  `numpy`-only); `Makefile:199-200` (`refresh-embedding-model` target style).
- `ci/tasks/windows-installer-build.yml:1-46` — the `platform: windows`
  task shape (choco `python311`, `uv export … | pip install`, `pip install -e .
  --no-deps`), which the one-off YAML copies through step 2 and then runs
  the script instead of freezing.
- Flight 1's log, "Peak RSS fix — reproduced and corrected on windows-worker"
  — the one-off-task precedent (`fly -t the-one execute -c <task.yml> -i
  repo=.`, `PYTHONPATH` to the checkout, discarded after).
- `tests/_embedding_stub.py` (Leg 3) for the script's unit test.
- The mission's Known Issues: `usearch` is `simd=serial` on Windows; the
  Linux run is the contrast that makes that visible.

## Outputs

- `scripts/bench_vector_store.py` (new): CLI `--corpus {synthetic,real}`,
  `--n N` (synthetic size; default 1,000,000), `--queries Q` (default 200),
  `--cells` (comma list of `backend:dtype`, default all four), `--k`
  (default 10), `--seed` (default 2024), `--data-dir` (temp by default),
  `--out` (markdown file; stdout always). Prints host facts (platform,
  Python, SQLite version, `sqlite-vec` / `usearch` versions, CPU count,
  total/available RAM, `usearch`'s `numkong`/SIMD state from the Leg 1
  diagnostic), then one markdown table row per cell with: build wall time,
  inserted count, on-disk bytes (WAL-checkpointed DB delta for `sqlite-vec`,
  sidecar bytes for `usearch`), query p50 / p95 / max (ms, single query,
  `k` results), recall@`k` vs exact float32, peak RSS, and for `usearch`
  the `save` and `restore` wall times. Exit 0 always on completion; the
  numbers are the deliverable, not a gate.
- `Makefile`: `bench-vector-store` target running the script at a small
  smoke size (`--corpus synthetic --n 20000 --queries 50`), documented in
  `make help`.
- `tests/test_bench_vector_store.py` (new): the ground-truth and metric
  functions at tiny N; one synthetic end-to-end run (`--corpus synthetic
  --n 2000 --queries 10`, sqlite-vec float32 cell); and one real-corpus
  end-to-end run over a `tmp_path` of three small markdown files, driven
  by the suite-wide 8-dim stub backend (so `dim` follows `backend.dim`).
- Flight log: the "Store Benchmark" section — host facts for both
  platforms, the one-off task YAML verbatim, every table, the run order
  and timestamps, DD-8 extrapolation applied if needed (labelled), and a
  short "reading the table" note pointing at the p95 ≤ 250 ms bar. **No
  recommendation** — the decision is the operator's (DD-9).
- Leg ticked in `flight.md`; the flight-end review/commit pass for Legs
  1–5 follows this leg (Flight Director Notes, flight start).

## Acceptance Criteria

- [x] AC-1 The script runs end-to-end on this host with `--corpus synthetic
      --n 20000 --queries 50` for all four cells in under three minutes and
      prints one well-formed markdown table; `make bench-vector-store`
      invokes exactly that.
- [x] AC-2 Ground truth is exact: for a synthetic corpus the brute-force
      top-`k` for each query is computed by streamed float32 cosine
      (`argpartition` per 100k block, merged), and a unit test proves that
      the streamed merge equals a single-pass `argsort` top-`k` on a small
      corpus, that running the recall metric against the brute-force result
      itself yields 1.0, and that a deliberately half-replaced result yields
      0.5.
- [x] AC-3 Latency is measured per single query with `time.perf_counter_ns`
      around **only** the store's `query` call (no vector generation or
      normalisation inside the timed region), over `Q` queries, reporting
      p50/p95/max. For the int8 cells the store's **internal** quantisation
      of the query vector is inside the timed region — the landed API takes
      a float vector and quantises per call, there is no pre-quantised
      entry point, and inventing one here would be new seam surface; it is a
      genuine per-query cost of those cells and the table says so. A unit
      test asserts the timed region excludes the fixture work by timing a
      stub store that sleeps a known duration. For `usearch` the one query
      that triggers `restore` is issued **before** the timing loop and
      reported separately as the restore time — never folded into the
      p50/p95/max array.
- [x] AC-4 On-disk bytes for `sqlite-vec` are measured after `PRAGMA
      wal_checkpoint(TRUNCATE)` as the DB file's size delta from before the
      cell's inserts — the script's own connection sets `PRAGMA
      journal_mode=WAL` first (mirroring production; a fresh `aiosqlite`
      connection defaults to `delete` mode where the checkpoint is a silent
      no-op — design review verified); for `usearch` as the sidecar file's
      size after `flush`. `usearch` cells also report `save` and `restore`
      wall times at the run's `N`. **Each cell's DB file and sidecar are
      deleted as soon as its row is recorded**, so a multi-cell invocation
      at 3M needs the space of one cell (~6 GB worst case), not all four.
- [x] AC-5 Synthetic vectors are a seeded Gaussian mixture (64 centroids,
      σ = 0.3, unit-normalised, `float32`), generated and inserted in 100k
      batches so the process never holds the full set; queries are 200
      corpus members perturbed by σ = 0.05 and re-normalised (so recall is
      meaningful — each query has a true near neighbour). The same seed
      reproduces the same vectors on both platforms (asserted by a
      fingerprint printed with the table: the SHA-256 of the first batch).
- [x] AC-6 The real corpus path chunks every `*.md` under `docs/`,
      `missions/`, plus `the_one/agents.md` and `README.md` with DD-7
      defaults, holds out 200 chunks as queries, embeds the rest with
      `LocalStaticBackend.load()` in batches of 1,000 (reporting the
      `truncated` total), and computes recall@10 against exact float32 over
      the embedded corpus. **The stores' `dim` is taken from
      `backend.dim`**, never hard-coded — which is also what lets the unit
      test run this path under the suite-wide `conftest.py` autouse stub
      (`dim=8`) with no injection flag. Chunk and file counts are printed.
- [x] AC-6b **Recall scope, reconciled with DD-8**: recall@10 is reported on
      **both** tables but means different things. On the synthetic table it
      is *index/quantisation recall* — how much of the exact top-10 an
      approximate index (usearch HNSW) or a lossy dtype (int8) returns; the
      sqlite-vec float32 cell is mechanically 1.0 (exact scan vs exact
      ground truth — design review verified) and serves as the AC-2 sanity
      check. On the real-corpus table it is the retrieval-relevant figure
      DD-4's 0.95 floor applies to. The "reading the table" note (AC-8e)
      says which bar applies to which column.
- [x] AC-7 Every cell is exercised **through the Leg 4 stores** (`open`,
      `upsert`, `flush`, `query`, `close`), never through raw `vec0` or
      `usearch` calls — a grep in the test asserts the script imports no
      `sqlite_vec`/`usearch` symbol except for version strings.
- [x] AC-8 The flight log's "Store Benchmark" section contains: (a) Linux
      host facts + the four-cell table at N = 1M and N = 3M + the real-corpus
      table; (b) `windows-worker` host facts (RAM is already recorded:
      31.71 GB; **free temp-disk space** is printed by the script and
      recorded here) + the 1M sqlite-vec cells run **first**, then the
      remaining cells at 1M, then all four at 3M (RAM allows; a cell is
      skipped with a printed reason only if the free-space guard trips);
      (c) the one-off task YAML verbatim; (d) the exact commands and UTC
      timestamps; (e) a one-paragraph "reading the table" note naming the
      p95 ≤ 250 ms bar for the latency columns and the 0.95 floor for the
      **real-corpus** recall column only, and stating that the latency
      columns are the **second, cache-warm pass** (steady-state interactive
      search, the production analogue) while cold-start cost is the
      separate `restore` column for `usearch` and effectively zero for
      `sqlite-vec` — without recommending.
      **(a), (d)-for-Linux, (e) landed by the Developer. (b) and (c) —
      the `windows-worker` half — are explicitly the Flight Director's
      scope per this leg's Verification Steps and are NOT yet done; this
      criterion is checked here only for the Developer's portion.**
- [x] AC-9 `ruff check the_one/ tests/ scripts/` and `ruff format --check`
      on the same three roots clean (CI's `lint.yml` covers only
      `the_one/ tests/` — the pre-commit hook covers `scripts/`; whether the
      CI gate should add `scripts/` is raised to the Flight Director, not
      changed here); `make test-unit` green; wall time within Leg 4's
      baseline plus test-count growth. The script must not be imported by
      the unit gate except in its own test (no `import scripts.…` from
      `the_one/`).

## Verification Steps

- AC-1: `time .venv/bin/python scripts/bench_vector_store.py --corpus
  synthetic --n 20000 --queries 50`; `make bench-vector-store`.
- AC-2–3, 7: `PYTHON=.venv/bin/python bash scripts/run-tests.sh
  tests/test_bench_vector_store.py -x --timeout 300`.
- AC-4–6: read the table columns from the AC-1 run and the real-corpus run
  (`--corpus real`).
- AC-8: read the flight log; `fly -t the-one execute -c <task.yml> -i repo=.`
  for the Windows runs (the Flight Director runs these; the Developer's
  scope ends at a working script and the Linux runs).
- AC-9: `ruff check the_one/ tests/ scripts/`; `make test-unit`.

## Implementation Guidance

1. **Script skeleton** in the generator-script style: module docstring
   stating purpose, `main(argv)`, `argparse`, pure helper functions
   (`make_synthetic_batches`, `make_queries`, `brute_force_topk`,
   `recall_at_k`, `time_queries`, `disk_bytes_sqlite`, `host_facts`,
   `render_table`). The script drives the stores through
   `asyncio.run(...)` with its own `aiosqlite` connection to a temp DB
   under `--data-dir` — `PRAGMA journal_mode=WAL` and `PRAGMA
   foreign_keys=ON` first, mirroring `the_one/db/connection.py`, then
   `ensure_schema` (the stores assume the schema; `kb_vector_index` is
   store-owned). Reset `the_one.vectors` and
   `the_one.db._write_lock` singletons between cells.

2. **Cells**: build a store per cell directly (`SqliteVecStore(conn,
   dtype=…, dim=dim)`, `UsearchStore(conn, dtype=…, dim=dim)` with
   `settings.data_dir` monkeypatched to `--data-dir`) — do not go through
   the dispatcher, which reads the app setting. Fresh DB file **and fresh
   `aiosqlite` connection** per cell so on-disk deltas are clean; at the end
   of each cell `await store.close()`, then **`await conn.close()`**, then
   delete that cell's DB file, `-wal`, `-shm` and sidecar directory before
   opening the next cell's connection — on Windows, unlinking a file SQLite
   still holds open raises `PermissionError` (WinError 32) and would crash
   the multi-cell run on exactly the platform that matters (design review,
   cycle 2). Peak disk use is one cell. Before each cell, a free-space guard: estimate
   `N × bytes_per_vector(dtype) × 1.25` (2,048 / 512 / 1,024 / 512 B for
   f32 / i8 / f16 / i8) and if `shutil.disk_usage(data_dir).free` is below
   it, **skip the cell** and print `SKIPPED (need ≈X GB, free Y GB)` as its
   row — print-and-skip, never crash mid-run (Architect Q3 resolved:
   gate, with the reason in the table).

3. **Synthetic corpus**: `rng = np.random.default_rng(seed)`; centroids
   `(64, 512)` normalised; batch of 100k: pick centroid ids, add
   `rng.standard_normal((100k, 512)) * 0.3`, normalise, `float32`. Ids are
   `1..N`. Queries: 200 corpus rows chosen by fixed indices, perturbed,
   normalised — stored in RAM. Ground truth: for each batch compute
   `sims = Q @ batch.T` (`(200, 100k)`), `argpartition` top-`k`, merge with
   the running top-`k` (keep `(id, sim)` pairs). Print the SHA-256 of
   `batch0.tobytes()`.

4. **Timing**: `for q in queries: t0 = perf_counter_ns(); await
   store.query(kb, q, k); t1 …` — the query vectors are generated and
   normalised before the loop; the store's internal int8 quantisation is
   inside the timed region by design (AC-3). For `usearch`, issue one
   untimed warm query first (it triggers `restore` on a fresh instance —
   that call is the restore-time measurement, step 6) so the loop measures
   steady state. Run the `Q`-query loop **twice** and report the second
   pass (Concourse worker noise; the first pass warms caches). Report
   `np.percentile([...], [50, 95])` and `max` in ms.

5. **Recall**: `len(set(returned ids) & set(truth ids)) / k`, averaged.

6. **Disk**: `sqlite-vec` — `await conn.execute("PRAGMA
   wal_checkpoint(TRUNCATE)")` then `os.path.getsize(db)` minus the size
   before the cell's first insert. `usearch` — sidecar size after `flush`.
   `save`/`restore` timing: `flush` is the save; time it; then `close`,
   construct a new store, time its first `query` (which restores) — report
   both.

7. **Real corpus**: walk the four roots, read `*.md` as UTF-8 (errors
   `replace`), `chunk_text` each, keep `(file, seq, text)`; hold out every
   ~125th chunk (≈200) as queries; embed the rest and the queries with
   `LocalStaticBackend.load()` (one load) in batches of 1,000; exact ground
   truth over the in-RAM corpus matrix; then the same four cells. The stub
   backend is used only in the unit test (`--embedding stub` hidden flag or
   a module-level injection point).

8. **Host facts**: `platform.platform()`, `sys.version`, `sqlite3.
   sqlite_version`, package versions, `os.cpu_count()`, **free disk at
   `--data-dir` via `shutil.disk_usage` (cross-platform, no ctypes)**, RAM
   (Windows:
   `ctypes.windll.kernel32.GlobalMemoryStatusEx` with declared `argtypes`
   — the Flight 1 HANDLE lesson; POSIX: `os.sysconf("SC_PHYS_PAGES") *
   os.sysconf("SC_PAGE_SIZE")` and `/proc/meminfo` `MemAvailable`),
   `usearch` acceleration via the Leg 1 diagnostic helper.

9. **Windows one-off task YAML** (Flight Director; pasted into the log):
   `platform: windows`, `inputs: [repo]`, run: choco `python311`, `uv
   export --no-dev --no-emit-project` (no extras — `sqlite-vec`, `usearch`
   and `model2vec` are base dependencies) `| pip install`, `pip install -e .
   --no-deps`, then
   `& $py scripts\bench_vector_store.py --corpus synthetic --n 1000000
   --cells sqlite-vec:float32,sqlite-vec:int8` **first** (the early read
   against the bar), then the `usearch` cells at 1M, then — if the printed
   available RAM is ≥ 8 GB — all four at 3M, then `--corpus real`. Each
   invocation is its own `fly execute` so a crash loses one table, not all.

10. **Flight log section** written by the Flight Director from the
    captured stdout; the Developer's log entry covers the script, its test,
    and the Linux runs.

## Edge Cases

- **`argpartition` on fewer than `k` candidates** (tiny N in tests) → clamp
  `k` to the batch size.
- **Duplicate query members** (a query's source row is in the corpus) → by
  design: the perturbed source is the expected top-1; recall measures
  whether the store finds it and its neighbours.
- **`sqlite-vec` at 3M on Windows** may take tens of minutes per cell — the
  script prints progress per 100k batch so a long run is distinguishable
  from a hang; `fly execute` has no timeout by default.
- **WAL checkpoint under an open transaction** → issue it after `flush`
  and outside any `write_transaction`.
- **`usearch` `restore` timing must load from disk** → `close()` the first
  store (dropping its cache) before constructing the second.
- **Real corpus on Windows** → the checkout is uploaded by `-i repo=.`;
  `missions/` is included, so the corpus is identical on both platforms
  (assert by printing chunk count on both).
- **Memory**: never hold the synthetic corpus; the exact ground truth holds
  only 200 queries and a `(200, k)` running result.
- **int8 per-vector overhead is unmeasured before the Linux 1M run**: the
  1.25× guard margin is validated for float32 (2,124.6 B/vector measured)
  and usearch f16 (~1,198 B/vector, Leg 4's log); if the Linux 1M int8 rows
  show a ratio above 1.25×, raise the guard's multiplier before the Windows
  3M run rather than trust it blindly (failure mode is a skip, not a crash).

## Files Affected

- `scripts/bench_vector_store.py` — new
- `Makefile` — `bench-vector-store` target
- `tests/test_bench_vector_store.py` — new
- `missions/24-knowledge-bases/flights/02-storage-and-embedding-foundation/flight-log.md`, `flight.md`

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified (AC-8's Windows half is the Flight Director's)
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed` (the Flight Director sets `completed` after the flight-end review)
- [x] Check off this leg in flight.md
- [x] Do NOT commit — the flight-end review and commit for Legs 1–5 follow this leg (not committed)

## Citation Audit

Design review cycle 1 (Developer, 2026-09-14) — `needs rework` — verified
the landed store API against every call the leg makes and found: AC-3's
"quantise before the timer" impossible against the API (both stores
quantise internally; no pre-quantised entry point) → AC-3 rewritten; the
synthetic recall column contradicted DD-8's trade-off → AC-6b reconciles
both tables' recall meanings; the promised free-disk-space print was absent
→ host facts and a per-cell free-space guard added, plus per-cell cleanup;
`dim` must come from `backend.dim` (the suite-wide stub is 8-dim) → stated;
`PRAGMA journal_mode=WAL` needed for the checkpoint to mean anything →
stated; restore-triggering query excluded from the latency array → stated.
Empirically confirmed by the reviewer: the synthetic distribution is
non-trivial (13.3 % same-centroid in the exact top-10 vs 1.6 % random; the
perturbed source is top-1 100 %); sqlite-vec float32 synthetic recall is
1.0 by construction; ~2,124.6 B/vector on disk for float32 `vec0` rows.

Cycle 2 (same reviewer) — `approve with changes`: all round-1 fixes verified
landed (the 1.25× disk margin checked against Leg 4's measured sidecar
bytes and the reviewer's own 2,124.6 B/vector float32 figure); one new
medium introduced by the cleanup fix — the aiosqlite connection must be
closed before the cell's files are deleted, or Windows raises WinError 32 —
fixed; two lows (test-bullet wording; "second pass = steady state" stated in
the reading-the-table note) fixed. Credited: AC-2's "half-replaced → 0.5"
case is the first that exercises the recall metric's set semantics (a
shuffled correct result cannot change a set intersection).
