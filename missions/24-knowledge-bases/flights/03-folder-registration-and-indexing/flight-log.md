# Flight Log: Folder Registration and Indexing

**Flight**: [Folder Registration and Indexing](flight.md)

## Summary

In flight. Legs 1–4 completed and committed (PR #200); the optional HAT leg (`hat-and-alignment`) is the only leg outstanding — it needs the operator present. Reconnaissance, three Architect design-review cycles and the operator interview are recorded below; `flight.md` is at `ready`, the behavior-test draft `kb-folder-index-round-trip` is filed, no code has changed.

---

## Leg Progress

### Leg 1 — folder-registration-and-walk — implementation landed (2026-09-15)

**Changes Made**

- `the_one/db/repositories.py`: `KBItemRepository.delete` widened — the
  chunk select now covers `item_id = ? OR item_id IN (SELECT id FROM
  kb_items WHERE parent_id = ?)`, so a folder delete's FTS cleanup covers
  every descendant's chunks before the FK cascade removes the rows; the
  grep-count invariant (`VALUES ('delete'` appears exactly once in the
  file) holds. Added `create_many` (bulk `executemany` insert, one
  `write_transaction`), `list_children`, `list_folders`,
  `requeue_stranded(kb_id=None)`, `requeue_for_reindex(kb_id)`. Widened
  `list_by_status`/`count_by_status` with additive `limit=`/`type=`
  keywords (byte-for-byte the old behaviour when omitted — existing
  positional callers untouched). `KBChunkRepository.list_for_item` gained
  `limit=`/`offset=` keywords (`LIMIT -1 OFFSET ?` when only `offset` is
  given, since SQLite requires a `LIMIT` for `OFFSET`); added
  `ids_for_item` (id-only select, never touches `text`) and `iter_for_kb`
  (async-generator keyset pagination on `id`, no transaction held between
  pages).
- `the_one/knowledge/walk.py` (new): `SKIPPED_DIRS`, `DiscoveredFile`,
  `WalkResult`, `walk_folder`, `ReconcilePlan`, `plan_reconcile`,
  `content_hash`, `is_filesystem_root` — exactly as scoped in Outputs.
- `the_one/interfaces/web/api.py::create_kb_item`: wrapped
  `KBItem.model_validate` in `try/except ValidationError` → 422 (the
  `create_knowledge_base` shape); added the `type == "folder"` branch —
  canonicalise, existence/`is_dir` check under `asyncio.to_thread`,
  filesystem-root check, then a containment scan of `list_folders(kb_id)`
  in both directions (409 naming the conflicting item id) — in that exact
  order (existence → root → containment); stores the canonical absolute
  path; calls the new `_after_folder_registered(kb_id)` no-op hook after
  a successful folder create.
- `SECURITY-MODEL.md`: "Knowledge-base indexing (M24 F3)" bullet added to
  "Tool Execution Boundary", after the "No native SQLite extension"
  bullet, before "## Boxed Execution Mode".
- Tests: new `tests/test_kb_walk.py` (24 tests: filter rules, error
  surface/counters, the pure reconcile planner, `content_hash`,
  `is_filesystem_root`). Additions to `tests/test_db_repositories.py`
  (+14: the AC-1 folder-delete-cleans-descendants test plus a new
  `TestKBItemRepositoryBulkAndListings` class covering `create_many`
  (insert/no-op/rollback/single-transaction-spy), `list_children`,
  `list_folders`, the `list_by_status`/`count_by_status` keyword filters,
  and both requeue methods), `tests/test_kb_chunks.py` (+6: a new
  `TestChunkReadsPagingAndKeysetIteration` class covering
  `list_for_item` paging, `ids_for_item`, and `iter_for_kb` including its
  no-held-transaction-between-pages proof), `tests/test_db_api.py` (+15:
  a new `TestKnowledgeBaseFolderRegistration` class covering every AC-10
  registration-validation case — valid/relative/tilde/symlinked path
  canonicalisation, non-existent path, existing file path, filesystem
  root, same-KB overlap in all three directions with the conflicting id
  in `detail`, cross-KB same-path success, the existence-before-
  containment ordering case, `file`/`url` unchanged, the malformed-body
  422, and the `_after_folder_registered` hook call/no-call — plus one
  AC-11 test added to `TestKnowledgeBaseDeleteCallsVectorStore` for a
  folder delete's descendant chunk ids reaching the recording store).

**Notes**

- `SKIPPED_DIRS = frozenset({"node_modules", "__pycache__", "venv",
  "site-packages"})` — exactly the leg-spec value, no deviation.
- Counter semantics implemented as specified: `skipped_dirs` /
  `skipped_entries` count only *conditional* skips (symlinked directory
  or file, an unreadable subdirectory, a non-UTF-8 name, or a
  `SKIPPED_DIRS` match). Dot-prefixed names and unsupported extensions
  are by-design filters and are never counted — verified by dedicated
  tests (`test_dot_entries_not_counted`,
  `test_unsupported_suffix_not_counted`).
- Test-count delta per file (via `grep -cE "^\s*(async )?def test_"`
  against the pre-leg blob at each file's last commit):
  `tests/test_db_repositories.py` 173 → 187 (+14),
  `tests/test_kb_chunks.py` 20 → 26 (+6), `tests/test_db_api.py`
  77 → 92 (+15), new `tests/test_kb_walk.py` +24. Total new tests: 59.
- `make test-unit` (run once, alone, foreground): **4452 passed, 10
  skipped, 557 deselected, 523.20s wall (0:08:43)**, exit code 0. No
  `-m live` run; no port-8484 or default-data-dir instance touched;
  every DB test used a `tmp_path`-scoped connection.
- `make lint` (`ruff check the_one/ tests/ scripts/`): clean.
  `ruff format --check the_one/ tests/ scripts/`: clean (429 files
  already formatted after the leg's own files were reformatted in
  place).
- `grep -c "VALUES ('delete'" the_one/db/repositories.py` → `1` (AC-1's
  invariant, confirmed post-implementation).
- **Deviation from guidance, with reason**: the Implementation Guidance
  sketch for `create_kb_item`'s folder branch used a separate
  `item_repo_for_check` variable fetched independently of the later
  `repo = await _kb_item_repo()` used for `repo.create(item)`. Landed
  code fetches `_kb_item_repo()` once at the top of the folder branch and
  reuses the same `repo` for both the `list_folders` containment scan and
  the eventual `create` — behaviourally identical (each call opens its
  own connection-bound repository over the same shared `conn`), just one
  fewer redundant call. No functional change; noted since it is a
  cosmetic departure from the literal guidance text.
- No other deviations. All thirteen acceptance criteria (AC-1 through
  AC-13) implemented and verified via the leg's own Verification Steps
  before this entry was written.

### Leg 2 — extractor-seam-and-indexer — implementation landed (2026-09-15)

**Changes Made**

- `the_one/knowledge/extractors/__init__.py` (new): `Extractor`
  (`runtime_checkable` Protocol), `ExtractionError`, the suffix-keyed
  registry (`register`/`unregister`/`extractor_for`/
  `supported_extensions`/`clear_for_test`) — one dict entry per suffix in
  `extractor.extensions`, all-or-nothing conflict checking against a
  *different* extractor's name, same-name re-registration a no-op;
  `_register_builtins()` registers `TextExtractor` at import (and after
  `clear_for_test()` in a test's teardown).
- `the_one/knowledge/extractors/text.py` (new): `TextExtractor`
  (`utf-8-sig`, `errors="replace"`, `ExtractionError` chained from
  `OSError` on a missing file) and `TEXT_EXTENSIONS` — the DD-4 set
  verbatim, `.html`/`.htm`/`.log` absent.
- `the_one/knowledge/indexer.py` (new): constants (`MAX_FILE_BYTES`,
  `EMBED_BATCH`, `FLUSH_MIN_CHUNKS`, `FLUSH_MIN_SECONDS`,
  `FLUSH_SAVE_MULTIPLIER`), `is_binary_head`, `IndexContext`,
  `ItemOutcome`, the private `_Reject`/`_fail`, `index_item` (the eight
  DD-5 stages, the exact three-clause exception order from the
  Implementation Guidance, cooperative stop checked only after the first
  embed batch, `ctx.embed_lock` held per embed+upsert pair and released
  between batches), `FlushPolicy` (pure, clock-injected), `rebuild_kb`
  (DD-6's only stale recovery, no manager lock, no store call-back inside
  its generator).
- `the_one/vectors/_store.py`: `rebuild_from` added to the `VectorStore`
  Protocol, `AsyncIterable[tuple[Sequence[int], np.ndarray]]` input, the
  no-call-back invariant stated in its docstring.
- `the_one/vectors/usearch_store.py`: `rebuild_from` now iterates its
  input with `async for`; `entry.dirty = True` moved ahead of the
  `asyncio.to_thread` mutation in both `upsert` (before `_do_upsert`) and
  `delete` (after the `entry.index is None` early return, before
  `entry.index.remove`).
- Tests: `tests/_extractor_stub.py` (new, `StubExtractor` + `STUB_TEXT`),
  `tests/test_kb_extractors.py` (new, 17 tests — registry shape,
  `TextExtractor` decode rules and `TEXT_EXTENSIONS`, the M7
  stub-extractor end-to-end proof with `indexer.py` untouched),
  `tests/test_kb_indexer.py` (new, 25 tests / 26 collected — happy path,
  every AC-5 failure path including the three-clause exception order's
  propagate cases, zero-norm/`truncated`, cooperative stop and
  `embed_lock` release-between-batches, `FlushPolicy`'s fake-clock
  behaviour, `rebuild_kb`'s recovery + no-call-back proof).
  `tests/test_vector_store.py`: the five `rebuild_from` call sites
  wrapped in a new `_aiter()` helper; two new test classes —
  `TestRebuildFromAsyncIterable` (a generator that awaits between pages;
  the widened signature still satisfies `VectorStore` structurally) and
  `TestDirtyReorder` (a `to_thread` mutation that raises after partially
  mutating the index still leaves `entry.dirty` `True`, for both `upsert`
  and `delete`).
- `the_one/agents.md`: "**Knowledge indexing** (Flight 3, Leg 2)" block
  added to the Knowledge storage section, after "The chunker" and before
  "Web-session idle reaper" — the extractor registry, the eight
  `index_item` stages with transaction boundaries, the "stays `indexing`
  until the covering flush" rule, `FlushPolicy` and its three constants,
  zero-norm/`truncated` handling, `rebuild_kb` and the no-call-back
  invariant, the `entry.dirty` reorder, the corrected lock-ordering
  invariant, and the two crash-window consequences for Flight 5.

**AC-12 measurement** (this host: Linux, accelerated numpy/`usearch`; a
scratch script under the session scratchpad, not committed, against a
temp data dir — `UsearchStore` f16 dim 512, `StubEmbeddingBackend` dim
512, `ChunkingSettings()` defaults, `FlushPolicy()` defaults driven by a
manual loop calling `store.flush(kb_id)` when `should_flush()` is true,
plus one unconditional final flush):

| Measurement (10 files x ~852 KB generated text, 10,000 chunks) | Value |
|---|---|
| Total chunks indexed (sum of `ItemOutcome.chunks`) | 10,000 |
| `store.count(kb_id)` after the final flush | 10,000 |
| Total wall time (index + flush) | 2.005 s |
| `write_transaction` shim calls (instrumented at `the_one.vectors.usearch_store.write_transaction`, the name bound into that module's own namespace) | 41 |
| `write_transaction` shim total time | 6.422 ms |
| `write_transaction` shim avg time/call | 0.1566 ms |
| Flush count at 10k chunks | 1 (chunk/time gates never tripped mid-run on this host — only the unconditional end-of-pass flush ran; consistent with DD-5's note that the gates are built for much larger/slower builds) |
| `flush` (save) wall time | 7.467 ms |
| Flush time as % of this run's total wall time | 0.372 % |

**1M-vector extrapolation (Windows), the arithmetic DD-12 asks for**:
using Flight 2's Windows save curve (`save_ms` 244 at 20k, 1,908 at
200k — linear scaling gives 1,908 x (1,000,000/200,000) = 9,540 ms,
consistent with the flight's stated ~10-12 s range at 1M; taking the
midpoint **11 s** as the representative single-flush save time at that
scale):

- Required inter-flush wait per `FlushPolicy`: `max(FLUSH_MIN_SECONDS=15,
  FLUSH_SAVE_MULTIPLIER=10 x 11) = max(15, 110) = 110 s`.
- Steady-state cycle window: `save + wait = 11 + 110 = 121 s`.
- Overhead fraction: `11 / 121 = 9.09%` — exactly `1 / (1 + 10)`, the
  closed form DD-5/DD-12 cite, confirmed realistic at 1M scale (not just
  true "by construction") because the multiplier term (110 s) comfortably
  dominates `FLUSH_MIN_SECONDS` (15 s) at this save cost.
- **Divert threshold is 15% at 1M (flight spec). 9.09% < 15% — PASS**,
  ~39% relative margin below the threshold (`(15 - 9.09) / 15`).
- Cross-check against the ~7 ms/vector Windows insert rate: a full 1M
  build takes `1,000,000 x 7 ms = 7,000 s` (~116.7 min) of insert/embed
  time alone; the 121 s steady-state cycle covers roughly `121,000 ms /
  7 ms per vector ~= 17,285` vectors accumulated between flushes near the
  1M mark — comfortably above the 2,000-chunk gate, confirming the TIME
  gate (not the chunk gate) is what binds at that scale, exactly as DD-5
  states.

**Test figures**

- Per-file test-count deltas (defs via `grep -cE "^\s*(async )?def
  test_"`, collected counts via `pytest --collect-only -q` where
  parametrisation multiplies the def count):
  `tests/test_vector_store.py` 28 -> 32 defs (+4), 41 -> 45 collected
  (+4, none of the four new tests are parametrised); new
  `tests/test_kb_indexer.py` +25 defs / +26 collected (one
  `@pytest.mark.parametrize` case); new `tests/test_kb_extractors.py`
  +17 defs / +17 collected. Total new tests: 47.
- `make test-unit` (run once, alone, foreground): **4499 passed, 10
  skipped, 557 deselected, 517.29 s wall (0:08:37)**, exit code 0 — up
  from Leg 1's 4452 passed by exactly 47, matching the count above. No
  `-m live` run; no port-8484 or default-data-dir instance touched;
  every DB/vector-store test used a `tmp_path`-scoped connection and
  fixture-scoped `settings.data_dir` monkeypatch.
- `make lint` (`ruff check the_one/ tests/ scripts/`): clean.
  `ruff format --check the_one/ tests/ scripts/`: clean (435 files
  already formatted).
- `grep -rn "isinstance(.*VectorStore" tests/ the_one/`: two call sites,
  both in `tests/test_vector_store.py` (the pre-existing structural-
  Protocol-satisfaction test plus this leg's new async-signature check);
  no other `isinstance(..., VectorStore)` consumer exists anywhere in the
  tree.
- `grep -n "LocalStaticBackend.load(\|from_pretrained"
  tests/test_kb_extractors.py tests/test_kb_indexer.py
  tests/test_vector_store.py tests/_extractor_stub.py`: 0 matches — every
  seam-consumer test in this leg runs against `StubEmbeddingBackend`.

**Deviations from guidance, with reasons**

- The Implementation Guidance's stage-2 sketch does not show an explicit
  `except FileNotFoundError` around `path.stat()`; landed code adds one
  (`raise _Reject(f"file not found: {path}") from None`) because
  `asyncio.to_thread(path.stat)` raises `FileNotFoundError` for a missing
  file and AC-5 requires that specific case to fail with an error naming
  the path, not fall through to the generic `except Exception` handler's
  `f"{type(exc).__name__}: {exc}"` shape. Functionally required by AC-5,
  not a departure from intent.
- `ExtractionError` from `extractor.extract` is caught locally inside
  stage 2 and re-raised as `_Reject(str(exc)) from exc` (rather than
  letting it fall through to the generic `except Exception` clause)
  because AC-5 requires the stored error to be the extractor's message
  verbatim, not the `f"{type(exc).__name__}: {exc}"`-prefixed generic
  form. Same rationale as above — required by the acceptance criterion's
  exact wording, not a design deviation.
- After the `make test-unit` run recorded above, a flake surfaced under
  repeated runs of the leg's own three test files:
  `TestRebuildKb::test_rebuild_recovers_a_stale_kb`'s three fixture items
  originally shared identical paragraph text across files (`_make_text`
  keyed only on paragraph index, not on which file), so
  `StubEmbeddingBackend`'s deterministic hash-of-text embedding gave
  several chunks across different items the EXACT same vector — a tie a
  nearest-neighbour query cannot resolve by id, occasionally returning a
  different item's chunk id at distance 0 instead of the queried chunk's
  own id. Fixed by adding a `doc` disambiguator to `_make_text` and
  passing each file's index through it, so every fixture file's text (and
  therefore its embedded vectors) is unique within the test. Confirmed
  stable across 4 repeated runs of the three files afterward, then
  re-ran `make test-unit` once more in full to confirm the fix changed no
  pass/skip/deselect counts (identical 4,499 passed / 10 skipped / 557
  deselected, 526.25 s — the ~9 s wall-time difference from the figure
  recorded above is ordinary host-load variance, not a regression). Not
  a source-code deviation — the fixed file is a test fixture.
- No other deviations. All fourteen acceptance criteria (AC-1 through
  AC-14) implemented and verified via the leg's own Verification Steps
  before this entry was written.

### Leg 3 — indexing-manager-and-routes — implementation landed (2026-09-15)

**Changes Made**

- `the_one/knowledge/manager.py` (new): `IndexingManager` — constructor-
  injectable `conn_factory`/`store_factory`/`backend_factory`/`clock`,
  `embed_batch` and the three flush constants, `pending_page`,
  `stop_timeout`, `shutdown_flush_timeout`; `_WorkerEntry` (`task`,
  `wake`/`idle` events, `stop_requested`, `state`, `awaiting_flush`, a
  per-entry `FlushPolicy` created once at entry creation, `current_item_id`);
  `start`/`request_index`/`state`/`wait_until_idle` (sync/non-blocking
  except the test helper), `async stop`/`drain`/`start_all`; the worker
  loop (`_run`/`_resources`/`_pass`), the walk+reconcile pair
  (`_cycle_folder_to_pending`/`_walk_one_folder`/`_apply_reconcile`), the
  drain pair (`_drain_pending`'s bounded-fallback loop /
  `_drain_batch`), and the manager-owned `_flush`. Module-level
  `_manager`/`set_manager`/`get_manager` (the `connectors/manager.py`
  accessor shape).
- `the_one/interfaces/web/app.py`: imports `IndexingManager` and
  `set_manager as _set_module_indexing_manager`; startup constructs the
  manager and publishes it via the accessor BEFORE its own guarded
  `start_all()` (unlike the connector-manager block, which only publishes
  on success — needed so a route reaching `get_manager()` mid-startup
  sees a real instance); shutdown drains it (its own `try/except`) right
  after the in-flight/resume task gathers and before the web-session
  reaper drain, then clears the accessor. New module-level
  `_indexing_manager: IndexingManager | None` global, the
  `_connector_manager` shape.
- `the_one/interfaces/web/api.py`: `_kb_chunk_repo()` helper (the
  `_kb_item_repo`/`_vector_store` shape); `_after_folder_registered`
  filled to call `get_manager().request_index(kb_id)` when a manager is
  installed; `delete_knowledge_base` calls `manager.stop(kb_id)` before
  the repository delete; `delete_kb_item` of a `folder` item calls `stop`
  before the delete and `request_index` after (a `file` item delete calls
  neither); four new routes — `GET .../status`, `POST .../reindex?scope=`,
  `GET .../items/{id}/chunks`, `GET .../items/{id}/source`; `retry_kb_item`'s
  docstring updated to say startup and per-pass `requeue_stranded` now
  exist alongside the route (no longer "the only way out").
- `tests/test_kb_manager.py` (new, 23 tests): manager lifecycle basics;
  the pass (folder-fixture end-to-end, a dormant `url` + empty `folder` +
  a `KBItemTransitionError`-monkeypatched `file` item still reaching
  `idle`, the bounded-fallback drain with `pending_page=2` and three
  permanently-stuck items past two good ones); `_apply_reconcile` directly
  (new/removed/changed-different-per-source-status/changed-identical);
  flush cadence integration (small gates flush per item, large gates flush
  once at pass end); stale-sidecar recovery (a deleted sidecar + a fresh
  `UsearchStore` + `requeue_for_reindex` triggers `rebuild_kb`, ends every
  item `indexed` with `store.count` matching and a WARNING log; a store
  whose `rebuild_from` always raises fails the current item and stops,
  then a later `request_index` recovers); cooperative stop (a
  `_SlowBackend` mid-second-item, current item's chunks committed, prior
  item's flush landed, next pass finishes it) and the cancel fallback (a
  `_BlockingBackend` past `stop_timeout=0.2`, item stays `indexing`, no
  flush, next pass finishes it); `drain()` concurrency (three
  hand-constructed `_WorkerEntry`s each taking 0.3s complete well under
  0.9s) and the empty-manager no-op; `start_all` (cross-KB
  `requeue_stranded` + resume to `indexed`, the vector-store-settings
  write-once-if-absent byte-identity check, a KB with neither folders nor
  pending items getting no worker).
- `tests/test_db_api.py` (+25 tests): `_FakeIndexingManager` (records
  `request_index`/`stop` calls, scripted `state()`) installed via
  `monkeypatch.setattr(manager_mod, "_manager", fake)`; `/status` (404,
  counts+folders+chunks with no manager installed, folder projection +
  manager state, chunk count); `/reindex` (404, invalid-scope 422,
  `changed` default, `scope=all` requeue count + item ends `pending`, no
  manager installed still 202); `/chunks` (seq order + shape, `limit`
  below/above range 422, negative `offset` 422, other-KB 404); `/source`
  (extracted text + fresh-hash-not-stale, no-stored-hash-reads-stale,
  missing-file 404, folder/url 422, no-extractor 422, other-KB 404); the
  hook + both delete routes' `stop`/`request_index` call-order.
- `tests/test_mcp_pool.py`: `test_lifespan_shutdown_drain_order` extended
  with a `_FakeIndexingManager` (`start_all` -> `"indexing_start"`,
  `drain` -> `"indexing_drain"`) monkeypatched onto `app_mod.IndexingManager`;
  the asserted drain-order list is now `["connector_start",
  "indexing_start", "indexing_drain", "pty", "evict", "mcp", "oauth",
  "connector_drain", "db"]`.
- `CLAUDE.md`: a "Knowledge bases (M24)" paragraph in the Architecture
  section naming the item routes, the four new routes and their shapes,
  the operator-only/no-allowlist registration note, and the
  resume-not-restart behaviour.
- `the_one/agents.md`: the "Knowledge indexing" block's closing
  placeholder line replaced with the full `IndexingManager` contract —
  worker pass steps, `state` vocabulary, the no-`finally` idle bookkeeping
  rule (plus the `request_index`-clears-`idle`-synchronously fix, below),
  stale-sidecar recovery and the rebuild-failure path, cooperative stop +
  cancel fallback, the manager-owned `_flush` and its error handling,
  `drain()` concurrency and the 20s+20s budget under the desktop
  launcher's 60s join, `start_all`'s first-index settings record, the
  module accessor, and the route wiring.

**Test figures**

- Per-file test-count deltas: new `tests/test_kb_manager.py` +23 defs /
  +23 collected; `tests/test_db_api.py` +25 defs / +25 collected (`grep
  -cE "^\s*(async )?def test_"` before/after); `tests/test_mcp_pool.py`
  +0 defs (the drain-order test was extended in place, not duplicated).
  Total new tests: 48.
- The nine-file combined run this leg touches or depends on
  (`test_kb_manager.py test_kb_indexer.py test_kb_walk.py
  test_kb_extractors.py test_kb_chunks.py test_db_api.py
  test_db_repositories.py test_vector_store.py test_mcp_pool.py`, via
  `scripts/run-tests.sh ... -x --timeout 60 -q`): **513 passed, 2
  deselected, 171.73s**.
- `make test-unit` (run once, alone, foreground): **4547 passed, 10
  skipped, 557 deselected, 548.53s (0:09:08)**, exit code 0 — up from Leg
  2's 4499 passed by exactly 48, matching the count above (skipped and
  deselected counts unchanged — no browser/live/pixel tests added). No
  `-m live` run; no port-8484 or default-data-dir instance touched; every
  DB/vector-store/manager test used a `tmp_path`-scoped connection and
  fixture-scoped `settings.data_dir` monkeypatch.
- `make lint` (`ruff check the_one/ tests/ scripts/`): clean.
  `make format-check` (`ruff format --check the_one/ tests/ scripts/`):
  clean (437 files already formatted).
- Drain-order list as asserted (`test_lifespan_shutdown_drain_order`):
  `["connector_start", "indexing_start", "indexing_drain", "pty",
  "evict", "mcp", "oauth", "connector_drain", "db"]`.
- No test synchronises on a wall-clock sleep for its own pacing: the
  cooperative-stop/cancel-fallback/drain-concurrency tests use
  `manager.wait_until_idle`, `queue.Queue` signals consumed via
  `asyncio.to_thread`, and `asyncio.Event`s on hand-constructed
  `_WorkerEntry`s; a plain `time.sleep`/`asyncio.sleep` appears only
  inside the fake-slow test backends (`_SlowBackend`, `_BlockingBackend`)
  and one hand-rolled `_pretend_worker` coroutine standing in for a
  worker's own cooperative-stop delay in the `drain()` concurrency test.

**Deviations from guidance, with reasons**

- **Real bug found and fixed, not anticipated by the leg spec**:
  `request_index` now clears `entry.idle` SYNCHRONOUSLY (before
  `entry.wake.set()`), not left for the freshly-created or freshly-woken
  task to clear on its own next scheduling turn. Without this, a caller
  doing `request_index(); await wait_until_idle()` back-to-back — exactly
  the shape of nearly every test in this leg, and of the route wiring's
  own `_after_folder_registered` -> operator polls `/status` pattern —
  races a task that has not run yet: the entry's `idle` event is still
  set (from entry creation, or the prior pass's own normal completion),
  so `wait_until_idle` returns immediately instead of waiting for the
  pass just requested. Caught by this leg's own first `TestPass` test
  (`test_folder_fixture_indexes_every_file` failed with "Cannot operate
  on a closed database" — the test's `conn` fixture had torn down before
  the background task, which had not even started yet, tried to use it).
  Fixed in `request_index` itself; documented in `agents.md`'s idle-
  bookkeeping paragraph alongside the design-reviewed no-`finally` rule
  it sits next to.
- `_drain_pending`'s bounded fallback is implemented with an explicit
  `fallback_used` flag rather than the Implementation Guidance's more
  implicit "process its un-attempted ids, and exit only when that yields
  none" phrasing — after the ONE fallback read runs (empty or not), the
  loop returns to normal bounded-page reads rather than looping the
  fallback itself; a second occurrence of "page full, zero un-attempted"
  within the same pass falls straight to `return` because `fallback_used`
  is already `True`. Functionally equivalent for the bar the AC sets (one
  full read per pass, proven by the `pending_page=2` / three-stuck /
  two-good test) and clearer to reason about than a re-entrant fallback
  loop.
- `_flush(kb_id, entry)` resolves its own `store`/`item_repo` via the
  manager's factories on every call, rather than reusing whatever
  `IndexContext` the current pass built — required so the SAME method
  works correctly when called from `stop()` after the worker task (and
  its `ctx`) has already exited, per DD-7's "the manager, not the worker,
  performs the final flush" at shutdown. Recorded in the module docstring
  and `agents.md`.
- No other deviations. All twelve acceptance criteria (AC-1 through
  AC-12) implemented and verified via the leg's own Verification Steps
  before this entry was written.

---

### Leg 4 — verify-integration — completed (2026-09-15/16)

**Status**: completed
**Started**: 2026-09-15 (design at `e39da94`)
**Completed**: 2026-09-16T00:09Z

#### Changes Made
- No source change. `tests/behavior/kb-folder-index-round-trip.md`:
  `draft` → `active`, `Last Run` set; two apparatus notes added to
  Preconditions/Step 1 (mint the credential before the first `make up`
  on a fresh scratch dir; verify NUL bytes with Python, not `grep`).
  Run log `tests/behavior/kb-folder-index-round-trip/runs/
  2026-09-15-23-55-26.md` (committed; evidence ephemeral under
  `/tmp/behavior-tests/…`, 36 files, not committed).
- `missions/24-knowledge-bases/mission.md`: `parent_id` and skipped-files
  open questions resolved (DD-2, DD-3/4/5); the Windows 1M re-measure
  added as an open question.

#### Gates (all at `e39da94`)
| Gate | Result |
|---|---|
| AC-1 premise audit | every premise confirmed, zero spec edits (Developer, Sonnet) |
| AC-2 dev instance | 8485 + scratch data dir; `/api/live` 200; 8484 never listening |
| AC-3 behavior test | **pass, 8/8 checkpoints**, live two-agent mode, cold cache; every verdict evidence-backed; every wait point resolved on poll 1 |
| AC-4 lint / unit | `make lint` clean; `make test-unit` **4,547 passed / 10 skipped / 578.08 s** |
| AC-5 closure | `uv export` 1,697 lines, 0 `hf-xet`/`sqlite-vec`; `pip-audit --disable-pip` → No known vulnerabilities found |
| AC-6 frozen run | build **608700**, first attempt: `RESULT: PASS`, eight gates OK, `BUILD OK`; installer **134,886,157 bytes** (+95,865 / +0.07 % vs 134,790,292) |
| AC-7 mission artifact | done |
| AC-8 docs | CLAUDE.md / agents.md / SECURITY-MODEL.md verified; README and windows-install unchanged (no new gate or command) |

#### Notes
- Behavior-run observations worth carrying: this fixture indexes faster
  than the 2 s poll interval, so the run saw terminal states only — the
  live-kill variant is how to watch a transition; on this WSL2 host a
  stopped port reads as a curl timeout, not connection-refused; `make
  up`'s own boot-wait absorbs the restart latency; registering `/tmp`
  itself was refused 409 before any walk (the parent-containment rule
  protecting the host's own `/tmp`, evidence directory included).
- Candidate spec tightenings recorded in the run log's Operator Notes
  (realpath tiebreaker; "old chunk ids replaced" assertion) — not
  applied, each is a re-authored premise.
- Squawk candidate carried to the debrief: `CLAUDE.md` says `make up`
  writes `.the-one.pid`; the Makefile scopes it by port.

---

## Decisions

*(runtime decisions not in the original plan)*

### Flight Director Notes

**Planning — 2026-09-15.** Branch: to be cut from `mission/24-knowledge-bases`
as `flight/03-folder-registration-and-indexing` at flight start; PR back into
the mission branch per the mission's "Branch Layout" section. The mission
branch is level with `main` at planning (0 commits behind, 26 ahead), so no
rebase is due at this boundary. No CI lane runs on the flight PR — `make
lint`, `make test-unit`, `pip-audit` and the frozen `fly execute` are run by
hand and recorded here before merge.

**Planning premises measured — 2026-09-15** (this host: Linux, Python 3.12,
accelerated numpy and `usearch`; Windows figures in Flight 2's log are the
discount to apply). One scratch script against a temp data dir with the real
schema, the real `UsearchStore` (f16) and the real `LocalStaticBackend`:

| Premise | Measured |
|---|---|
| 1,000 empty `write_transaction` round-trips (the `UsearchStore.upsert` shim) | 52.5 ms total, 0.05 ms each |
| `KBItemRepository.create` × 500, one commit each | 483.6 ms |
| 500 item INSERTs in one transaction | 3.5 ms |
| `update_status` × 200 | 174.8 ms (0.9 ms each) |
| `replace_item_chunks`, 1,000 chunks of 1,000 chars | 118.4 ms |
| Model load (`LocalStaticBackend.load`) | 415 ms |
| `embed` batch 64 / 256 / 1,000 | 23.4 / 71.7 / 255.0 ms → 2,732 / 3,570 / 3,922 chunks/s |
| `upsert` 1,000 vectors in 256-batches | 143.4 ms |
| `flush` at 1,000 vectors | 2.9 ms |
| `os.walk` + `stat` over this checkout (2,079 files, dot-dirs pruned) | 24.2 ms |
| sha256 of 146 `.py` files (2.0 MB) | 39.4 ms |
| `chunk_text` on `agents.md` (255,532 chars → 326 chunks) | 6.4 ms |
| `chunk_text` on 10.2 MB (→ 13,040 chunks) | 273.1 ms |
| Symlinked directory under the root | neither `Path.rglob` nor `os.walk(followlinks=False)` descends into it on Python 3.12; `os.walk`'s rule is explicit and version-independent |

Read-outs that shaped the design decisions: the empty-transaction shim is
negligible at any batch size (DD-12 — recorded, confirmed in Leg 2 inside
the real pipeline); bulk item creation must be one transaction (DD-2's
`create_many`); chunking a large file belongs under `to_thread` (DD-5);
embedding is not the bottleneck on this host and, per Flight 2's Windows
numbers, the HNSW insert is the bottleneck on the operator's platform, which
is why the flush cadence is save-time-adaptive (DD-5).

**Interview (2026-09-15).** Operator had no approach preferences and confirmed
the two reconnaissance scope-downs (R6, M8). Structured answers: source
read-back routes land in this flight; a per-KB re-index route ships; a
behavior test **and** an optional HAT leg; the walk uses an extension
allowlist (unsupported formats are skipped, never failures).

**Design review, cycle 1 (2026-09-15).** Architect (Opus): **approve with
changes**. Load-bearing premises verified by the reviewer against code and
a scratch SQLite: the widened `KBItemRepository.delete` composes into its
existing single `write_transaction` with no nested guard; the recursive FK
cascade (folder → children → their `kb_chunks`) fires with
`PRAGMA foreign_keys=ON`, so select-FTS-then-delete is correctly ordered;
`rebuild_from` has consumers only in `tests/test_vector_store.py`; the
chunker's `text[char_start:char_end] == chunk.text` guarantee holds after
stripping; no existing test creates a `folder` item. Three high findings,
all incorporated: (1) the flush-cadence arithmetic inverted — both clauses
are lower bounds, so the re-work window *is* `10 × last save`, ~2 min at 1M
and ~4 min at 3M, and the first draft's "60 s bar" (which the Flight
Director had written without asking) could not coexist with the ~10 %
overhead cap → **operator asked, chose the overhead cap**; the window is now
recorded as a consequence, not a bar; (2) unconditional folder status
cycling would raise `KBItemTransitionError` on `pending → pending` after
either bulk requeue → the walk moves a folder to `pending` only from
`indexed`/`failed`; (3) the walk cannot fail an item (`failed` is reachable
only from `indexing`) → the size cap and binary sniff move into the indexer's
stage 2, and the walk is stat-only. Medium findings incorporated: the final
flush is performed by the manager from the lifespan's uncancelled task, not
inside the worker's `CancelledError` handler; the manager is constructed
before its guarded start so `drain` and the drain-order test always reach
it, with a `_FakeIndexingManager`; the pending loop skips `folder` as well
as `url`; the manager-lock → write-lock ordering is stated; `rebuild_from`'s
generator may not call back into the store; the inverse crash window
(saved sidecar holding vectors for deleted chunk ids) is recorded for
Flight 5. Low findings incorporated: `os.scandir` entries for symlink
checks and symlinked-directory pruning; `is_within` instead of the private
`_is_descendant`; ids-only `ids_for_item`; `parent_id` has no index
(recorded); `create_kb_item` gains the `ValidationError → 422` handler;
`/source` 422s an item with no extractor; two `app.py` line citations
corrected. Architect questions answered: `rebuilding` becomes a fourth
indexer state; status counts are file items only with a separate
`folders` list; **operator chose** `/reindex` = walk for changes by
default, `?scope=all` re-embeds. Behavior spec corrected: four items not
five; `alpha_indexed_at` recorded in Step 8; both containment directions
in Step 6; the live-kill variant's PID path is `.the-one.8485.pid`.

Squawk candidate surfaced by the review, not this flight's to fix:
`CLAUDE.md` says `make up` writes `.the-one.pid`, but `Makefile:37` scopes
the PID file by port (`.the-one.$(THE_ONE_PORT).pid`) — a one-line doc
drift; log at the debrief if not before.

Substantive changes → second Architect pass (cycle 2 of max 2).

**Design review, cycle 2 (2026-09-15).** Architect (Opus): **approve with
changes** — every cycle-1 fix present; four NEW high findings, all in the
sections rewritten for cycle 1 (the same signature Flight 1's debrief
recorded: a revision introducing a class of error the reviewer then
catches). All incorporated: (1) the pending drain could never terminate —
`folder`/`url` items skipped "without a status change" stay `pending`
forever → the drain now pages `type="file"` only (`list_by_status` gains a
`type=` keyword in Leg 1) and keeps a per-pass attempted-id set; a
checkpoint pins it; (2) the stale rebuild would re-enter the non-reentrant
manager lock (`VectorStoreStaleError` is raised inside stages 6–7) → the
catch is at pass level after the lock is released, the rebuild generator
takes no manager lock, and the full order is stated as manager lock → store
per-KB lock → write lock; (3) cancel-then-flush raced the `to_thread`
mutation inside `UsearchStore.upsert` → `stop()` is cooperative (flag +
wake + `wait_for` 60 s, cancel only as fallback, no flush on the fallback
path), and Leg 2 moves `entry.dirty = True` ahead of the `to_thread` call;
(4) the reconcile's changed-content branch repeated the cycle-1 folder bug
for files → requeue only from `indexed`/`failed`, `pending` left alone,
`indexing` impossible at walk time because every pass now begins with
`requeue_stranded(kb_id)`. Medium findings incorporated: per-pass
`requeue_stranded` (runtime resume, not boot-only); DD-1 validation order
pinned as existence → root → containment (so behavior Step 6's 422 holds);
`model_id` for the first-index record comes from `EMBEDDING_MODEL_DIRNAME`,
never a synchronous model load on the loop; `awaiting_flush` lives on the
worker entry; `FlushPolicy` is Leg 2's, its caller Leg 3's; the Divert
criterion now rests on Leg 2's extrapolation to 1M using Flight 2's Windows
save curve (a 10k Linux run can never exceed 10 % by construction); the
drain's flush catches and logs any error, leaving awaiting items `indexing`;
behavior Steps 4/8 record `alpha_indexed_at_initial` and request the chunks
they assert on, and Step 8 now also pins `scope=all` (requeued 3) and the
422 for an invalid scope. Low findings incorporated: the repository returns
chunk ids and the worker hands them to the store; a standalone file inside
a registered folder is accepted as a second item (recorded); `/status`
reads `idle` for a KB with no worker entry; checkpoint 5 split by leg;
Leg 3 route split expected rather than a deviation. Architect questions
answered in DD-7 (`running` covers the whole pass; cooperative stop
finishes the current item; the cancel fallback leaves it `indexing` for
the next pass's requeue).

**Max design-review cycles reached (2).** Per `/mission-control:flight`,
issues persisting after two rounds escalate to the human: the cycle-2
findings are all incorporated, but no third Architect pass has verified
the incorporation. Presented to the operator with that stated. **Operator's call: a third
Architect pass, scoped to the cycle-2 edits, before the flight is marked
`ready`** (override of the max-2 rule, recorded here as Flight 1's debrief
asked).

**Design review, cycle 3 — operator-requested verification pass
(2026-09-15).** Architect (Opus): **approve with changes**, scoped to the
cycle-2 edits. Verified as holding: the walk/reconcile rule against all
four child statuses and the claim that `indexing` is unreachable at walk
time; the cooperative stop and no-flush-on-cancel against
`usearch_store.py:262-283`; the `entry.dirty` reorder (lossless; in
`delete` it stays after the `index is None` early return); the DD-1
validation order against behavior Step 6; every DD-8 shape against Steps
3/4/7/8/10 including `requeued: 3`; the `EMBEDDING_MODEL_DIRNAME`
substitution. Two sentence-level highs of the same class the earlier passes
caught, both fixed: (1) "retries the item it was on" after a rebuild would
raise `KBItemTransitionError("indexing→indexing")` → the worker restarts
the pass instead (pass-start `requeue_stranded` returns the item to
`pending`); (2) the drain exit "until the page comes back empty" cannot
fire once a row is skipped by the attempted set → exit when a page contains
no un-attempted ids. Mediums fixed: `awaiting_flush` cleared at pass start
after `requeue_stranded` and the flip tolerates a per-item transition
error; the lock-order sentence corrected (`upsert`/`delete` acquire-and-
release the write lock before the per-KB lock; only `flush`/`rebuild_from`
nest); `ctx.should_stop` added to the indexer context so Leg 3 can
interrupt Leg 2's function between batches; shutdown budget resized to
20 s + 20 s with a concurrent per-KB drain so the total stays under the
desktop launcher's 60 s join. Low: `EMBEDDING_MODEL_DIRNAME` cited with its
module. These cycle-3 edits are the last unverified change; each leg's own
design review during execution covers them next.

**Flight status → `ready` (2026-09-15).**

### Flight Director Notes — flight start (2026-09-15)

- `/mission-control:agentic-workflow flight 03 mission 24` invoked. Phase
  file `.flightops/agent-crews/leg-execution.md` loaded and validated
  (Crew / Interaction Protocol / Prompts with fenced blocks present).
  Developer = Sonnet; Reviewer = Haiku unless the diff touches a
  security-sensitive surface, then Sonnet.
- Branch `flight/03-folder-registration-and-indexing` cut from
  `mission/24-knowledge-bases` at `0f79f9c`. Planning artifacts (flight
  spec, this log, the behavior-test draft) committed as the first flight
  commit. Flight status `ready` → `in-flight`.
- Five legs in the spec; four autonomous (`folder-registration-and-walk`,
  `extractor-seam-and-indexer`, `indexing-manager-and-routes`,
  `verify-integration`) then the optional HAT. Per the workflow, code
  review and commit are deferred to after the last autonomous leg, except
  that Leg 4's behavior test and frozen run need committed, reviewed code
  — so the flight-end review and commit run after Leg 3, and Leg 4 runs
  against that commit (the Flight 2 shape: Legs 1–5 reviewed and
  committed, Leg 6 against it).

### Flight Director Notes — Leg 1 design (2026-09-15)

- Leg artifact `legs/01-folder-registration-and-walk.md` written against
  the flight branch at `148f704`; thirteen acceptance criteria; Citation
  Audit appended.
- **Risk tier: HIGH.** A behavioural change to a shared repository method
  with a route consumer (`KBItemRepository.delete` now covers descendants),
  bulk status UPDATEs that bypass `update_status`'s per-row transition
  check (pinned to the transition table by call-time asserts), and the
  filesystem rules every later flight inherits. Design review runs
  (Developer, Sonnet, "Review Leg Design").
- Two things the leg deliberately leaves to Leg 2/3 and says so: the size
  cap and binary sniff (indexer), and the `request_index` call behind the
  `_after_folder_registered` no-op hook (manager). `walk_folder` takes the
  extension set as a parameter because the registry that owns it is
  Leg 2's.

- Leg 1 design review (Developer, Sonnet): **approve with changes** — one
  medium (the non-UTF-8 name guard must also cover directory names before
  they are pushed onto the walk stack) and two lows (a one-line citation
  drift; which counter a symlinked directory increments). All applied;
  counter semantics pinned (conditions are counted, by-design filters are
  not). The reviewer verified the widened `delete` SQL and cascade order
  against a scratch SQLite, `LIMIT -1 OFFSET ?` on SQLite 3.45.1, and that
  no existing test pins the old signatures. Changes were minor → no second
  review cycle. Leg 1 status → `ready`. `[HANDOFF:review-needed]`.

### Flight Director Notes — Leg 1 close, Leg 2 design (2026-09-15)

- Leg 1 landed (Developer, Sonnet): 59 new tests across four files,
  `make test-unit` 4,452 passed / 10 skipped / 523.20 s. Files touched match
  the leg's list exactly; one cosmetic deviation (a single `repo` variable
  in the folder branch) recorded in the leg entry. Per the workflow, no
  review or commit yet — the flight-end Reviewer covers Legs 1–3 together.
- Leg 2 artifact `legs/02-extractor-seam-and-indexer.md` written; fourteen
  acceptance criteria; Citation Audit against the working tree (Leg 1
  uncommitted).
- **Risk tier: HIGH.** A shared-interface change on the `VectorStore`
  Protocol (`rebuild_from` widened to an async iterable and added to the
  Protocol, five test call sites), a behaviour change inside
  `UsearchStore.upsert`/`delete` (`dirty` reorder), and the first
  implementation of Flight 2's write-ordering invariant. Design review runs
  (Developer, Sonnet).

- Leg 2 design review (Developer, Sonnet): **approve with changes** — two
  mediums (the DD-12 instrumentation must patch the name bound in
  `usearch_store`'s namespace, not `_write_lock`'s, or it records zero;
  the `_Reject` / stale / generic exception clause order was implied by
  AC-5 but not written) and four suggestions (zero-norm threshold alias,
  the redundant-but-deliberate `CancelledError` clause commented, the
  file-touch count pinned at two full reads plus a head sniff, the
  many-suffix registry shape spelled out). All applied. The reviewer
  verified every Leg 1 dependency signature, the `rebuild_from` consumers
  (tests only), and that the only `isinstance(…, VectorStore)` site is
  against the real store, so the Protocol widening breaks no stub. Minor
  → no second cycle. Leg 2 → `ready`. `[HANDOFF:review-needed]`.

### Flight Director Notes — Leg 2 close, Leg 3 design (2026-09-15)

- Leg 2 landed (Developer, Sonnet): 47 new tests (extractors 17, indexer
  26 collected, vector store +4), `make test-unit` 4,499 passed / 10
  skipped / 517.29 s. DD-12 measurement recorded in the leg entry: the
  empty-transaction shim costs 0.16 ms per call (41 calls for 10k chunks);
  save overhead extrapolated to 1M vectors on Windows is 9.09 % — under
  the 15 % Divert threshold with ~39 % margin; the time gate, not the
  chunk gate, binds at that scale, as DD-5 states.
- Leg 3 artifact `legs/03-indexing-manager-and-routes.md` written against
  the working tree (Legs 1–2 uncommitted); twelve acceptance criteria;
  Citation Audit appended. The leg keeps the routes in-leg (the flight
  anticipated a split; the manager's tests and the routes' tests are
  independent files, so the Developer's cost is width, not entanglement
  — revisit if the design review asks).
- **Risk tier: HIGH.** Lifecycle and state-machine work (the worker pass,
  cooperative stop, cancel fallback, stale restart), lifespan ordering
  (a new start/drain pair in `app.py` with the drain-order test extended),
  and four new operator-facing routes. Design review runs (Developer,
  Sonnet).

- Leg 3 design review (Developer, Sonnet): **approve with changes** — one
  high (a `finally` would set the idle event mid-stale-restart; now an
  explicit `else:` on the normal path only), two mediums
  (`current_item_id` missing from AC-1's field list; a cluster of ≥
  `pending_page` stuck rows could starve later rows within a pass — a
  bounded fallback to one unlimited read per pass added, with a test),
  two lows (`save_vector_store_settings` takes `conn`; the gathers
  citation was nine lines off). Suggestions applied: `stopped` state and
  the idle event set on the cancel-fallback path; accessor alias note;
  DD-7's publish-before-start rationale corrected in the flight spec (the
  drain reads the lifespan's local global, not the accessor). Minor → no
  second cycle. Leg 3 → `ready`. `[HANDOFF:review-needed]`.

### Flight Director Notes — Leg 3 close, flight-end review (2026-09-15)

- Leg 3 landed (Developer, Sonnet): 48 new tests (manager 23, routes 25,
  drain-order test extended in place), `make test-unit` 4,547 passed / 10
  skipped / 548.53 s. Two recorded deviations: a real race the Developer
  found (`request_index` now clears `entry.idle` synchronously before
  waking the worker, otherwise a `request_index(); await wait_until_idle()`
  pair could observe the previous pass's idle flag) and an explicit
  `fallback_used` flag for the bounded pending-page fallback.
- **Flight-end review (Phase 2d) over every uncommitted change since
  `148f704` — Legs 1, 2 and 3 together.** Reviewer tier: **Sonnet** — the
  diff adds operator-supplied filesystem paths read with the app's
  privileges (folder registration and its containment checks, the walk,
  the `/source` route that reads a file by stored path) and edits
  `SECURITY-MODEL.md`; that is a security-sensitive surface under the
  crew file's rule.

- Flight-end review (Reviewer, Sonnet): **`[HANDOFF:confirmed]`** on the
  first cycle — no blocking or non-blocking issues. Verified by the
  reviewer: every AC of Legs 1–3 against code and tests; the path-handling
  surface (canonicalise + both-direction containment, stat-only walk that
  never follows symlinks or yields outside the root, operator-only
  registration, `/source` uncapped by design); the lock order and the
  absence of any `write_transaction` in `the_one/knowledge/`; the
  FTS-delete-site invariant; that the mock-based regression tests would
  fail against the pre-fix code; no real model loads and no wall-clock
  synchronisation in the new tests; the combined nine-file suite 513
  passed / 174.21 s. Legs 1–3 → `completed`, checked off in `flight.md`,
  committed as one flight commit; draft PR opened against
  `mission/24-knowledge-bases` with Legs 4–5 unchecked.

- Flight commit `e39da94` (Legs 1–3, pre-commit ruff hook passed); branch
  pushed; draft PR **#200** opened against `mission/24-knowledge-bases`
  with Legs 4–5 unchecked. Leg 4 (`verify-integration`) runs against this
  commit: behavior-test premise audit and run, by-hand gates, frozen run.

### Flight Director Notes — Leg 4 design and gates (2026-09-15)

- Leg 4 artifact `legs/04-verify-integration.md` written at `e39da94`.
  **Risk tier: LOW** — no source change; a verification leg (behavior test,
  by-hand gates, frozen run) plus two artifact edits. No design review.
- Prerequisite probes: `sqlite3` 3.44.4, `uv` 0.10.0, `pip-audit` 2.10.0,
  port 8485 free, nothing on 8484, `fly` logged in, `windows-worker`
  running, no stale client.
- Launched in parallel: the frozen `fly execute` (run 1, detached, log
  `fly-f3-run1.log` in the session scratchpad, installer output outside
  the repo) and the release-closure audit — `uv export … --format
  requirements-txt` → 1,697 lines, 0 `hf-xet`/`sqlite-vec` lines;
  `pip-audit --disable-pip -r` → **No known vulnerabilities found**
  (AC-5 met). Behavior-spec premise audit spawned (Developer, Sonnet,
  AC-1). `make test-unit` is held until the audit Developer is done so
  the metric runs alone.

- Behavior-spec premise audit (Developer, Sonnet, Leg 4 AC-1): **every
  premise confirmed, zero edits** — route paths and codes, the file-only
  status counts and `folders` keys, both `reindex` scopes and the 422 for
  an invalid one, the chunk and source body keys and the `stale` rule,
  the validation order (existence before containment, so the missing
  nested path is 422), the walk's skips for the fixture's dot-entries /
  `.png` / symlink, the exact 10 MiB error text, the `requeued: 3`
  arithmetic, `parent_id` on children, the seeded-resume table and
  column, the credential and DB paths, the port-scoped PID file, and the
  registration kick reaching a lifespan-constructed manager. Ordering
  review: Steps 3, 8 and 10 have no race; the one external assumption is
  uvicorn serving no request before lifespan startup completes (standard
  uvicorn behaviour; noted, not verified from uvicorn source). Verdict:
  spec ready for first run. `make lint` clean (AC-4, lint half).

- **Unit gate (Leg 4 AC-4)**: `make test-unit` verbatim, alone, foreground
  at `e39da94`: **4,547 passed / 10 skipped / 557 deselected / 578.08 s**
  (pytest wall; 623.74 s including collection and teardown), exit 0 — the
  same count as Leg 3's close. Flight series: Flight 2 close 4,370 →
  squawk turnaround 4,431 → Leg 1 4,452 → Leg 2 4,499 → Leg 3 4,547
  (+116 tests for the flight, +154 over Flight 2's close).
- **Frozen run 1 (Leg 4 AC-6) — build 608700, succeeded on the first
  attempt**: `RESULT: PASS`; all eight doctor gates `OK` (`usearch: OK`
  with `numkong=no, simd=serial` as Flight 1 recorded; `fts5: OK`, SQLite
  3.45.1; `embedding model: OK`, peak RSS 247.2 MiB); `BUILD OK:
  the-one-setup-0.8.1.exe`; installer **134,886,157 bytes** against the
  Flight 2 baseline of 134,790,292 — **+95,865 bytes (+0.07 %)**,
  consistent with the flight adding only pure-Python modules under
  `the_one/knowledge/` and no dependency. The DD-11 iteration budget was
  not needed.
- Dev instance for the behavior test: first `make up` on 8485 with a
  scratch data dir failed its `verify-serving` step because no
  `api-credential` existed yet in the fresh data dir (the Makefile's own
  message prescribes `rotate-api-credential` first); brought down, the
  credential minted, brought up again. Recorded as an apparatus note for
  the spec's Preconditions (mint before the first `make up` on a fresh
  scratch dir), not a defect.

### Flight Director Notes — Leg 4 close, HAT pending (2026-09-16)

- Leg 4 completed and committed at `5a2fcec` (pushed; PR #200 checklist
  shows Legs 1–4). Every gate the mission's branch layout requires was run
  by hand and recorded in the Leg 4 entry.
- Leg 5 `hat-and-alignment` (optional, operator's call at planning)
  designed as a lightweight artifact at `ready`; **not started** — it is
  an operator-present leg, so the Flight Director stops here and hands
  over. The flight does not land until the HAT is completed or the
  operator waives it. The optional live-kill variant of the behavior
  test is also available if the operator wants to see a mid-flight
  transition rather than the seeded resume.

---

## Reconnaissance Report

Source artifacts walked against current code before leg design: the Flight 2
debrief (Recommendation 1, Recommendation 5, and the "Carry into Flight 3
planning" action item), the mission document's Flight 3 bullet, its success
criteria, and the three open questions that name this flight. Classification
per `/mission-control:flight` Phase 1b. The mission branch is at `0f79f9c`.

| Item | Source | Classification | Evidence | Recommendation |
|---|---|---|---|---|
| R1 — Two-transaction write ordering; `flush` is "landed"; the pipeline needs an explicit flush cadence, never per chunk | F2 debrief Rec. 1 | `confirmed-live` | `the_one/vectors/_store.py:17-30` states the contract and names "Flight 3's pipeline" as the caller; `UsearchStore.flush` (`usearch_store.py:341-367`) exists; no production caller of `flush` or `upsert` exists outside tests and the benchmark | Design input: the pipeline flushes per item batch, and an item flips to `indexed` only after the flush that covers it returns (DD in this flight) |
| R2 — `indexing → pending` requeue as the resume-not-restart primitive | F2 debrief Rec. 1 | `confirmed-live` | `the_one/db/_kb_types.py::KB_ITEM_TRANSITIONS` has `"pending": {"indexing", "failed", "indexed"}`; `retry_kb_item` (`api.py:1522-1557`) docstring: "until Flight 3's startup reconciliation exists this is the only way out for an item stranded by a kill" — no reconciliation exists | Design input: startup reconciliation requeues every `indexing` item, then resumes |
| R3 — `VectorStoreStaleError → rebuild_from` as the only stale recovery, an exceptional event | F2 debrief Rec. 1 | `confirmed-live` | `usearch_store.py:170-227` raises on missing/corrupt/count/dtype mismatch; `rebuild_from` at `:383-409`; `grep` finds zero references to either symbol outside `the_one/vectors/` and `agents.md` | Design input: one recovery path, triggered by the pipeline catching the error, re-embedding every chunk of the KB from `kb_chunks` |
| R4 — Write the `knowledge.vector_store` record on first index | F2 debrief Rec. 1 / Technical | `confirmed-live` | `save_vector_store_settings` (`the_one/knowledge/settings.py:224-230`) has callers only in `tests/test_knowledge_settings.py`; the v41 comment in `schema.py:2587` records the same fact | Pipeline writes the record before its first `upsert`, once per process (DD in this flight) |
| R5 — Measure the empty-`write_transaction` cost of `UsearchStore.upsert` under bulk load, in the first leg | F2 debrief Rec. 1 / Technical | `confirmed-live` | `usearch_store.py:266-267` and `:290-291` still open-and-close an empty `write_transaction` per call (acquire the app-wide lock, issue a real empty commit) | Measure in Leg 1 against the batch shape the pipeline actually uses; the design decision is on the batch size, which bounds the count of empty commits |
| R6 — Windows usearch build-time figures are extrapolated (~2 h per 1M f16 vectors, ~7 h at 3M) and unverified at the ceiling | F2 debrief Technical / Rec. 5 | `needs-human-recheck` | Flight 2 log, "Windows usearch at 1M and 3M — EXTRAPOLATED"; no code to check | Treat as an order of magnitude when choosing checkpoint granularity; the re-measure at 1M on Windows (Rec. 5) needs a real corpus of that size, which no leg in this flight produces — recommend recording it as a mission open question rather than a Flight 3 criterion |
| M1 — Folder item type, path containment on registration, the walk → filter → extract → chunk → embed → persist pipeline behind an extractor seam, as a resumable background job | mission Flight 3 bullet | `confirmed-live` (type value only) | v40 CHECK and `KBItem.type` Literal admit `folder`; `create_kb_item` (`api.py:1486-1504`) accepts any `path_or_url` with no existence, containment or canonicalisation check and kicks nothing; no `the_one/knowledge/` module walks, extracts or embeds; `grep -rn watchfiles the_one/` is empty | The flight's core scope |
| M2 — `parent_id` vs a new `folder_item_id` for the folder → file relationship | mission open question | `confirmed-live` | `parent_id` readers: only the repository's own INSERT/row-mapping (`repositories.py:513,519,635`); it survived v40 as `REFERENCES kb_items_new(id) ON DELETE CASCADE` with no index | Decide in this flight (DD); a new column is a v42 migration, reuse is not |
| M3 — Which files inside a registered folder are skipped, by what rule | mission open question | `confirmed-live` | `_is_binary` (`filesystem.py:274`, 8 KiB null-byte sniff) and `_check_read_size` (`:259`, takes a `FilesystemConfig`, so it cannot be reused as-is) exist; nothing in the tree handles dotfiles, VCS metadata or ignore files | Decide in this flight (DD) |
| M4 — Register a folder and see each discovered item's index status including failures | mission criterion | `partially-satisfied` | Status vocabulary, `error` column, transitions, `GET …/items`, `GET …/items/{id}`, `retry` route landed in Flight 2; registration, discovery and the pipeline that drives transitions do not exist | This flight lands the API half; the Studio half is Flight 6 |
| M5 — Large-folder indexing runs in the background without blocking the UI, and resumes rather than restarts after an interruption | mission criterion | `confirmed-live` | Nothing exists; the closest template is `ConnectorManager` (`the_one/connectors/manager.py:51-227`, one supervised task per entity, `start_all`/`stop`/`drain`, lifespan-wired at `app.py:320-329`) | Core scope; the supervisor shape is a DD |
| M6 — Inspect a knowledge base's contents and metadata, and retrieve the source material behind any indexed item | mission criterion | `partially-satisfied` | Repository reads exist (`KBItemRepository.list/get/count_by_status`, `KBChunkRepository.list_for_item/get_many`); no route returns chunks or source text; the chunker's docstring (`chunking.py:1-10`) promises exact offsets for exactly this | Unassigned between Flights 3 and 6 — operator's call in the interview |
| M7 — A new file-format handler can be introduced without modifying the indexing pipeline | mission criterion / constraint | `confirmed-live` | No extractor seam exists; the mission requires it to accept PDF/Office without the pipeline changing while shipping text only | Core scope (extractor Protocol, text/markdown/code implementation) |
| M8 — Whole-corpus re-index after a model change "is designed with the pipeline in Flight 3" | mission open question, partial answer at F2 | `partially-satisfied` | DD-2 left exactly one valid model; the settings route refuses any other, so no model change is reachable. The reachable re-index cases are: a content change on one item (per-item, this flight's normal path), a stale sidecar (R3), and an operator-initiated re-index of one item (`indexed → pending` exists in the transition table but no route uses it) | Recommend scoping the flight to per-item re-index plus the R3 rebuild; a "re-index this knowledge base" operator action is a question for the interview |

No item is `already-satisfied` or `drifted`. Retirement candidates: none. Items
R6 and M8 are scoped down as recommended above, pending the operator's
confirmation before Phase 2 proceeds to spec design.

---

## Deviations

*(none yet)*

---

## Anomalies

*(none yet)*

---

## Session Notes

- 2026-09-15 — Flight 3 planning opened; reconnaissance walked against `0f79f9c`.
- 2026-09-16 — Leg 4 completed: behavior test 8/8, unit gate 4,547, pip-audit clean, frozen build 608700 PASS.
- 2026-09-15 — Leg 1 (`folder-registration-and-walk`) implemented: repository widening, `the_one/knowledge/walk.py`, folder registration validation, `SECURITY-MODEL.md` bullet, 59 new tests across four files. `make test-unit` 4452 passed / 10 skipped / 523.20s; `make lint` and `ruff format --check` clean. `[HANDOFF:review-needed]`.
- 2026-09-15 — Leg 2 (`extractor-seam-and-indexer`) implemented: extractor seam + registry, `the_one/knowledge/indexer.py` (`index_item`, `FlushPolicy`, `rebuild_kb`), `rebuild_from` widened to an `AsyncIterable` on the `VectorStore` Protocol, the `entry.dirty` reorder, the DD-12 1M-Windows extrapolation (9.09% overhead, under the 15% Divert threshold), `agents.md`'s "Knowledge indexing" block, 47 new tests across three files. `make test-unit` 4499 passed / 10 skipped / 517.29s; `make lint` and `ruff format --check` clean. `[HANDOFF:review-needed]`.
- 2026-09-15 — Leg 3 (`indexing-manager-and-routes`) implemented: `the_one/knowledge/manager.py` (`IndexingManager` — worker pass, cooperative stop + cancel fallback, manager-owned flush, stale-sidecar rebuild + restart, bounded-fallback drain), lifespan `start_all`/`drain` wiring with the drain-order test extended, the four DD-8 routes, the `_after_folder_registered` hook filled, both delete routes' `stop`/`request_index` integration, `CLAUDE.md` and `agents.md` documentation, 48 new tests across two files (plus a real `request_index`-idle race found and fixed via this leg's own first test failure). `make test-unit` 4547 passed / 10 skipped / 557 deselected / 548.53s; `make lint` and `make format-check` clean. `[HANDOFF:review-needed]`.
