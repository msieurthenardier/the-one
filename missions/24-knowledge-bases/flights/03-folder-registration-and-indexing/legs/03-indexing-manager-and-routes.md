# Leg: indexing-manager-and-routes

**Status**: completed
**Flight**: [Folder Registration and Indexing](../flight.md)

## Objective

Make indexing run: `IndexingManager` (one long-lived, event-woken worker per
knowledge base with the DD-7 pass, cooperative stop, manager-owned flush,
pass-level stale recovery and the first-index settings record), its lifespan
start/drain wiring with the drain-order test extended, the four DD-8 routes
(`status`, `reindex`, `chunks`, `source`), the delete routes' `stop`
integration, the `_after_folder_registered` hook filled, and the `CLAUDE.md`
/ `agents.md` documentation — so that registering a folder on a running
instance indexes it in the background and a restart resumes.

## Context

- Flight DD-5 (flush cadence, `awaiting_flush` lifecycle, lock ordering,
  the first-index `knowledge.vector_store` record with
  `EMBEDDING_MODEL_DIRNAME`), DD-6 (pass-level stale catch, `rebuilding`
  state, pass restart after a rebuild), DD-7 (every sentence — the worker
  pass, cooperative `stop`, the cancel fallback with no flush, the
  manager-owned drain flush with error handling, concurrent `drain` within
  the 20 s + 20 s budget, lifespan placement, the `_FakeIndexingManager`,
  `state()` semantics), DD-8 (route shapes and codes), DD-3's folder-status
  and reconcile-application rules (requeue only from `indexed`/`failed`;
  `indexing` impossible at walk time because the pass starts with
  `requeue_stranded`).
- Leg 1 (uncommitted) supplies: `KBItemRepository.create_many`,
  `list_children`, `list_folders`, `list_by_status(limit=, type=)`,
  `count_by_status(type=)`, `requeue_stranded(kb_id=None)`,
  `requeue_for_reindex(kb_id)`, `update_status`, `set_content_identity`,
  `delete` (descendants); `KBChunkRepository.list_for_item(limit=, offset=)`,
  `ids_for_item`, `count_for_kb`; `walk.walk_folder(root, *, extensions)
  -> WalkResult(files, skipped_dirs, skipped_entries)`, `plan_reconcile`,
  `content_hash`; the `_after_folder_registered` no-op in `api.py`.
- Leg 2 (uncommitted) supplies: `indexer.IndexContext(conn, item_repo,
  chunk_repo, store, backend, chunking, should_stop, embed_lock,
  embed_batch)`, `index_item(item, ctx) -> ItemOutcome(status in
  {"awaiting_flush","failed","stopped"}, chunks, vectors, truncated,
  error)`, `FlushPolicy(min_chunks, min_seconds, save_multiplier, clock)`
  with `record_chunks` / `should_flush` / `record_flush`, `rebuild_kb(kb_id,
  ctx, *, reason)`, `extractors.supported_extensions()`; the store's
  `entry.dirty` reorder.
- Process-wide singletons the manager resolves lazily: `get_connection()`
  (`the_one/db/connection.py`), `get_vector_store()` (async,
  `the_one/vectors/__init__.py`), `get_embedding_backend()` (sync, loads the
  model — call it under `asyncio.to_thread`; the lifespan warm-up usually
  has loaded it already), `load_knowledge_settings(conn).chunking` (read
  once per pass — chunking changes apply to future indexing only).
- Precedents: `the_one/connectors/manager.py` (`ConnectorManager`, the
  `_listeners` dict, `start`/`stop`/`drain`, and the module accessor pair
  `set_manager`/`get_manager` at `:260-271`), the lifespan's own
  try/except-per-block style, and the connector routes' use of the
  accessor.

## Inputs

- Working tree = flight branch `148f704` + Legs 1–2 uncommitted.
- `the_one/interfaces/web/app.py`: imports `ConnectorManager` (`:47`) and
  `set_manager as _set_module_connector_manager` (`:48`); startup —
  connector manager construction and `start_all` (`:319-327`), the
  embedding warm-up block (`:328-343`), `yield` (`:344`); shutdown — the
  in-flight and resume task gathers (`:354-366`), then the reaper drain
  (from `:370`), …, the connector drain with `_set_module_connector_manager
  (None)` (`:437-443`).
- `tests/test_mcp_pool.py::test_lifespan_shutdown_drain_order` (`:616-783`):
  startup mocks with `_fake_conn = MagicMock()` (`:669`), the
  `_FakeConnectorManager` spy (`:689-696`) monkeypatched onto
  `app_mod.ConnectorManager`, the shutdown spies, and the assertion list
  `["connector_start", "pty", "evict", "mcp", "oauth", "connector_drain",
  "db"]` (`:769-783`).
- `the_one/interfaces/web/api.py`: `_kb_repo`/`_kb_item_repo`/
  `_vector_store` helpers (`:258-271`), `delete_knowledge_base`
  (`:1458-1477`), the KB item routes block (`:1481-1620`), the hook
  (`:1542-1545`), `delete_kb_item` (`:1600-1620`), the R8 scoping shape
  (`get_kb_item` `:1548-1560`), `retry_kb_item`'s 409 shape.
- `the_one/knowledge/settings.py`: `VECTOR_STORE_KEY`, `VectorStoreSettings`,
  `save_vector_store_settings`, `load_knowledge_settings`;
  `the_one/db/repositories.py::AppMetadataRepository.get`.
- `the_one/embeddings/local.py::EMBEDDING_MODEL_DIRNAME` (`:36`).
- `tests/test_db_api.py` `client` fixture (`:20-48`: a bare `FastAPI()` with
  the router, `get_connection`/`get_encryptor` patched, no lifespan) and
  Leg 1's folder-registration tests (they monkeypatch
  `_after_folder_registered` by name — keep the name).
- `tests/test_kb_indexer.py` fixtures (`:37-104`): the `conn`/`store`/
  `backend`/`chunking` shapes the manager tests reuse.
- `CLAUDE.md` "Architecture (orientation)" watch-outs and the
  "Configuration" section — where the KB routes and the operator-only
  registration note go; `the_one/agents.md` "Knowledge indexing (Flight 3,
  Leg 2)" block (after "The chunker", before "### Web-session idle
  reaper").

## Outputs

- `the_one/knowledge/manager.py` (new): `IndexingManager`, `_WorkerEntry`,
  `STOP_TIMEOUT`, `SHUTDOWN_FLUSH_TIMEOUT`, `PENDING_PAGE`, `set_manager`,
  `get_manager`.
- `the_one/interfaces/web/app.py`: manager construction, `start_all`,
  `drain`, accessor set/clear.
- `the_one/interfaces/web/api.py`: four routes; hook filled; `stop`
  integration in both delete routes.
- `tests/test_kb_manager.py` (new); `tests/test_db_api.py` (route tests
  with a fake manager); `tests/test_mcp_pool.py` (drain-order test
  extended).
- `CLAUDE.md`, `the_one/agents.md`.
- Flight log entry.

## Acceptance Criteria

- [x] **AC-1 — Manager shape.** `IndexingManager(*, embed_batch=EMBED_BATCH, flush_min_chunks=FLUSH_MIN_CHUNKS, flush_min_seconds=FLUSH_MIN_SECONDS, flush_save_multiplier=FLUSH_SAVE_MULTIPLIER, pending_page=PENDING_PAGE (500), stop_timeout=STOP_TIMEOUT (20.0), shutdown_flush_timeout=SHUTDOWN_FLUSH_TIMEOUT (20.0), conn_factory=get_connection, store_factory=get_vector_store, backend_factory=get_embedding_backend, clock=time.monotonic)` — every dependency injectable for tests, defaults the production singletons. Methods: `start(kb_id)` (creates the worker task if absent or done), `request_index(kb_id)` (sets the entry's wake event, starting the worker if needed), `async stop(kb_id)`, `async drain()`, `state(kb_id) -> "idle" | "running" | "rebuilding" | "stopped"` (`idle` for a KB with no entry), `async start_all()`, and the test helper `async wait_until_idle(kb_id, timeout)`. A module-level `_manager` with `set_manager`/`get_manager`, the `connectors/manager.py:260-271` shape. `_WorkerEntry` holds `task`, `wake: asyncio.Event`, `idle: asyncio.Event`, `stop_requested: bool`, `state: str`, `awaiting_flush: list[str]`, `policy: FlushPolicy`, `current_item_id: str | None` (the item a pass is on, for the rebuild-failure path). One manager-wide `asyncio.Lock` (`_embed_lock`) is passed as `ctx.embed_lock`. The module docstring states the lock order (manager lock → store per-KB lock → write lock; `upsert`/`delete` acquire-and-release the write lock before the per-KB lock; only `flush`/`rebuild_from` nest).
- [x] **AC-2 — The pass.** A worker pass, in order: state `running`; `requeue_stranded(kb_id)` and `entry.awaiting_flush.clear()`; for each folder from `list_folders(kb_id)`: move it `→ pending` only if it is `indexed` or `failed`, then `pending → indexing`, `walk_folder` under `to_thread` with `extensions=supported_extensions()` (an `OSError` → folder `→ failed` with the error, children untouched, continue), `plan_reconcile(result.files, list_children(folder.id))`, apply: `new` → `create_many` of `pending` `file` children (`id = uuid4().hex[:12]`, `parent_id = folder.id`, `path_or_url = f.path`, `size_bytes`/`mtime` **left `None`** so the first index sets the identity); `removed` → `item_repo.delete(item.id)` then `store.delete(kb_id, ids)` if any; `changed` → `content_hash` under `to_thread`, and if it differs from `item.content_hash` and the item is `indexed` or `failed` → `update_status(item.id, "pending")`, if it is the same → `set_content_identity` with the fresh stat, if the item is `pending` → nothing; then folder `→ indexed`; the walk's counts logged at INFO. Then drain: page `list_by_status(kb_id, "pending", limit=pending_page, type="file")`, skipping ids in a per-pass `attempted` set, calling `index_item` for each un-attempted item with `ctx.should_stop = lambda: entry.stop_requested`; exit the drain when a page contains no un-attempted ids — **unless** that page is full (`len(page) == pending_page`), in which case fall back to one unlimited `list_by_status(kb_id, "pending", type="file")` read for this pass, process its un-attempted ids, and exit only when that yields none (design review: a cluster of ≥ `pending_page` rows stuck at `pending` would otherwise occupy the oldest window forever and starve later rows within the pass; the fallback bounds it to one full read per pass — a test with `pending_page=2`, three stuck items and two good ones proves both good ones index in a single pass); after each `awaiting_flush` outcome append the id and `policy.record_chunks(outcome.chunks)`, and flush when `policy.should_flush()`; on a `stopped` outcome leave the drain; on `KBItemTransitionError`/`KeyError` from `index_item` log and continue. Then a final flush if `awaiting_flush` is non-empty; state `idle`; `entry.idle.set()`. Tests: a pass over a folder fixture indexes every file to `indexed`; a pass with one dormant `url` item, one `folder` item and one `file` item whose `update_status` raises terminates and reaches `idle`; the folder-status rule holds from `indexed`, `failed` and `pending`; reconcile application covers new / removed (store `delete` called with the ids) / changed-and-different (requeued only from `indexed` and `failed`, never from `pending`) / changed-but-identical (identity updated, status untouched).
- [x] **AC-3 — Flush and flip.** `_flush(entry)` times `store.flush(kb_id)`, calls `policy.record_flush(seconds)`, then moves every id in `awaiting_flush` `indexing → indexed` (a per-item `KBItemTransitionError`/`KeyError` is logged and skipped) and clears the list. An item is never `indexed` before the flush that covers it (a test with `flush_min_chunks=1, flush_min_seconds=0, flush_save_multiplier=0` flushes per item and observes the order; a test with large gates observes items at `indexing` until the pass's final flush).
- [x] **AC-4 — Stale recovery.** `VectorStoreStaleError` propagating out of `index_item` (or a flush) is caught at the pass level with the manager lock not held: state `rebuilding`, `rebuild_kb(kb_id, ctx, reason=str(exc))`, then the pass restarts from step one (so `requeue_stranded` returns the interrupted item to `pending` and the cleared `awaiting_flush` cannot flip a `pending` row). Test: index a KB, delete its sidecar file, reset the store singleton (fresh `UsearchStore`), `request_index` → the KB ends with every item `indexed`, `store.count` equal to the vector-bearing chunk count, one WARNING log naming the reason, and `state()` back to `idle`. If `rebuild_kb` raises: the item being processed (if any) lands `failed` with the error, an ERROR log, state `stopped`, and the worker returns; a later `request_index` restarts it (test).
- [x] **AC-5 — Cooperative stop and the cancel fallback.** `stop(kb_id)`: sets `stop_requested`, sets `wake`, `await asyncio.wait_for(task, stop_timeout)`; on timeout `task.cancel()` and await it (suppressing `CancelledError`). After a cooperative stop the manager runs `_flush(entry)` under `asyncio.wait_for(…, shutdown_flush_timeout)` from its own task, catching and logging any exception (including `VectorStoreStaleError` and `TimeoutError`) and leaving the awaiting items `indexing` in that case; after a cancel fallback it does **not** flush and sets `entry.state = "stopped"` (nothing else would update a stale `running`/`rebuilding` word until the next `request_index`). In every case `stop` ends by setting `entry.idle` so a `wait_until_idle` caller never hangs on a stopped worker. `stop` on an unknown KB is a no-op. Tests: a stop mid-pass (a slow stub backend) returns within the budget, the current item's chunks are committed, the flushed items are `indexed`; a worker that ignores the flag (test hook: a backend that blocks past `stop_timeout=0.2`) is cancelled, no flush runs, the item stays `indexing`, and the next `request_index` pass requeues and finishes it.
- [x] **AC-6 — Drain.** `drain()` stops every entry **concurrently** (`asyncio.gather`), then clears the dict; with three fake-slow workers each taking 0.3 s to stop, `drain` completes in well under 0.9 s (test). `drain()` on an empty manager is a no-op.
- [x] **AC-7 — `start_all`.** Calls `requeue_stranded()` (all KBs); writes `knowledge.vector_store` via `save_vector_store_settings(conn, VectorStoreSettings(backend=store.backend, dtype=store.dtype, dim=store.dim, model_id=EMBEDDING_MODEL_DIRNAME))` **only if** `AppMetadataRepository.get(VECTOR_STORE_KEY)` is `None` (never overwrites — a test seeds a record and asserts it is byte-identical after); then for every KB from `KnowledgeBaseRepository.list()` that has at least one folder or at least one `pending` `file` item, `start` + `request_index`. A KB with neither gets no worker (`state == "idle"`). The stranded requeue plus the workers finishing is the resume proof: seed two items at `indexing` with chunks, `start_all`, `wait_until_idle` → both `indexed`.
- [x] **AC-8 — Lifespan.** In `app.py`: import `IndexingManager` and `set_manager as _set_module_indexing_manager`; after the embedding warm-up block, construct `IndexingManager()`, publish it with `_set_module_indexing_manager`, then `await manager.start_all()` inside its own `try/except Exception` (logged, never fatal); at shutdown, right after the in-flight resume gathers and before the reaper drain, `await manager.drain()` inside `try/except`, then `_set_module_indexing_manager(None)`. `test_lifespan_shutdown_drain_order` gains a `_FakeIndexingManager` (`start_all` appends `"indexing_start"`, `drain` appends `"indexing_drain"`) monkeypatched onto `app_mod.IndexingManager`, and the asserted order becomes `["connector_start", "indexing_start", "indexing_drain", "pty", "evict", "mcp", "oauth", "connector_drain", "db"]`.
- [x] **AC-9 — Routes.** `GET /api/knowledge-bases/{kb_id}/status` → `{"items": count_by_status(kb_id, type="file"), "folders": [{"id","path","status","indexed_at","error"} …] (from list_folders; "path" = path_or_url), "chunks": count_for_kb(kb_id), "indexer": manager.state(kb_id) or "idle" when no manager is installed}`; 404 for an unknown KB. `POST /api/knowledge-bases/{kb_id}/reindex?scope=changed|all` (default `changed`; any other value 422; unknown KB 404) → `changed`: `request_index`, `{"scope": "changed", "requeued": 0}`; `all`: `n = requeue_for_reindex(kb_id)`, `request_index`, `{"scope": "all", "requeued": n}`; status 202. `GET …/items/{item_id}/chunks?offset=0&limit=100` → list of `{"id","seq","char_start","char_end","text"}` in `seq` order via `list_for_item(limit=, offset=)`; `limit` outside 1–1000 or `offset < 0` → 422; R8 scoping (other KB → 404). `GET …/items/{item_id}/source` → `{"path","size_bytes","content_hash","stale","text"}` for a `file` item with a registered extractor: `text` = `extractor.extract(path)` under `to_thread`, `content_hash` = the stored value, `stale` = `content_hash(path) != stored` (a stored `None` reads as stale `True`); 404 if the item or the file is missing; 422 for `folder`/`url` or a `file` with no extractor. Route tests use a `_FakeIndexingManager` installed via `monkeypatch.setattr(manager_mod, "_manager", fake)` that records `request_index`/`stop` calls and returns a scripted `state`.
- [x] **AC-10 — Route integration.** `_after_folder_registered(kb_id)` calls `get_manager().request_index(kb_id)` when a manager is installed (no-op otherwise; Leg 1's test that monkeypatches the hook by name still passes). `delete_knowledge_base` calls `await manager.stop(kb_id)` **before** `repo.delete` (when installed). `delete_kb_item` of a `folder` item calls `stop` before the delete and `request_index` after; a `file` item delete calls neither. Tests assert the fake's call order.
- [x] **AC-11 — Docs.** `CLAUDE.md`: a short "Knowledge bases (M24)" paragraph in the Architecture section naming the item routes, the four new routes with their codes, that folder registration is operator-only and reads the folder with the app's privileges, that indexing runs in a background worker started by the lifespan and resumes after a restart via `indexing → pending`, and that `POST …/reindex` walks for changes by default and re-embeds only with `scope=all`. `the_one/agents.md`: extend the "Knowledge indexing" block with the manager contract — worker pass steps, `state` vocabulary, cooperative stop and the cancel fallback, manager-owned flush and its error handling, `drain` concurrency and the 20 s + 20 s budget under the desktop launcher's 60 s join, the first-index settings record, the module accessor, and the route wiring. Both documents' existing line about `retry_kb_item` being "the only way out" for a stranded item (if present in either) is updated or the `retry_kb_item` docstring in `api.py` is updated to say startup and per-pass requeue now exist.
- [x] **AC-12 — Gates.** `ruff check` / `ruff format --check` clean; `make test-unit` green with figures and per-file deltas in the flight log; no test sleeps on wall-clock for synchronisation (`wait_until_idle` and events only; `asyncio.sleep` allowed only inside fake-slow test backends).

## Verification Steps

- AC-1–AC-7: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_kb_manager.py -x --timeout 60 -q`.
- AC-8: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_mcp_pool.py -x --timeout 60 -q -k drain_order`.
- AC-9–AC-10: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_db_api.py -x --timeout 60 -q -k "KnowledgeBase"`.
- AC-11: read both documents; `grep -n "reindex" CLAUDE.md the_one/agents.md`.
- AC-12: `make lint`; `make test-unit` once, alone, foreground.

## Implementation Guidance

1. **`manager.py`.** Module docstring per AC-1. `_WorkerEntry` as a
   `@dataclass`. `start(kb_id)`: `entry = self._entries.get(kb_id)`; if
   `entry is None` create it with a fresh `FlushPolicy(self._flush_min_
   chunks, …, clock=self._clock)`; if `entry.task is None or entry.task.
   done()`: `entry.stop_requested = False`, `entry.task = asyncio.create_
   task(self._run(kb_id, entry))`. `request_index`: `self.start(kb_id)`
   then `entry.wake.set()`. `_run`: `while True: await entry.wake.wait();
   entry.wake.clear(); if entry.stop_requested: return; entry.idle.clear();
   try: await self._pass(kb_id, entry) except VectorStoreStaleError as exc:
   … rebuild then `entry.wake.set()` to restart … except asyncio.
   CancelledError: raise except Exception: logger.exception(...); entry.
   state = "stopped"; entry.idle.set(); return; else: entry.state = "idle";
   entry.idle.set()`. **No `finally`**: the `idle` event and the `idle`
   state are set on the normal-completion path only (the `else:` of the
   try — after the drain and the final flush), never on the stale
   restart's `continue` nor on the `CancelledError` re-raise; a `finally`
   would flip `idle` true for an instant mid-restart and race
   `wait_until_idle` callers into a false idle (design review, high).
   Structure the restart as: on stale, set
   `entry.state = "rebuilding"`, run `rebuild_kb`, then `entry.wake.set()`
   and `continue` — the next loop iteration is the restarted pass. On a
   rebuild failure: mark the current item `failed` if the pass recorded
   one in `entry.current_item_id` (add that field), log, `entry.state =
   "stopped"`, `entry.idle.set()`, `return`.
   - `_resources(kb_id)`: `conn = await self._conn_factory()`, repos,
     `store = await self._store_factory()`, `backend = await asyncio.
     to_thread(self._backend_factory)`, `chunking = (await
     load_knowledge_settings(conn)).chunking`; build `IndexContext(...,
     should_stop=lambda: entry.stop_requested, embed_lock=self._embed_lock,
     embed_batch=self._embed_batch)`.
   - `_pass` per AC-2; `_apply_reconcile` as its own method for
     testability; `_drain_pending` per AC-2 with the attempted set and the
     "no un-attempted ids in the page" exit; `_flush` per AC-3; the
     folder-status helper `_cycle_folder_to_pending(item)`.
   - `stop` per AC-5: `entry.stop_requested = True; entry.wake.set(); try:
     await asyncio.wait_for(asyncio.shield(entry.task), self._stop_timeout)
     … except TimeoutError: entry.task.cancel(); with suppress(...): await
     entry.task; cancelled = True`. Then `if not cancelled and entry.
     awaiting_flush: try: await asyncio.wait_for(self._flush(entry),
     self._shutdown_flush_timeout) except Exception: logger.exception`.
     Use `asyncio.shield` so the `wait_for` timeout does not itself cancel
     the task before the fallback decides to. `drain`: `await asyncio.
     gather(*(self.stop(k) for k in list(self._entries)), return_exceptions
     =True)`; then `self._entries.clear()`.
   - `start_all` per AC-7; `wait_until_idle(kb_id, timeout=10.0)`: `await
     asyncio.wait_for(entry.idle.wait(), timeout)` (create the entry's
     `idle` event set initially so a never-started KB is "idle").
2. **`app.py`.** Follow the connector-manager block shape exactly
   (`global _indexing_manager`, constructed and published before the
   guarded `start_all`; the shutdown block mirrors `:437-443` with its own
   `try/except` and the accessor cleared).
3. **`api.py`.** A `_indexing_manager()` helper returning the knowledge
   manager's `get_manager()` (may be `None`) — import it under an alias
   such as `get_indexing_manager`, since `api.py:29` already imports the
   connector accessor as `get_connector_manager`; there is no collision,
   just keep the two distinguishable. Routes next to the existing KB routes under the item
   block; `scope` as a `Query` parameter validated by a `Literal`-typed
   dependency or an explicit check → 422. For `/source`, resolve the
   extractor via `extractor_for(Path(item.path_or_url))`.
4. **Tests.** `tests/test_kb_manager.py` builds the manager with injected
   factories over the `test_kb_indexer.py` fixture shapes (`conn`, a real
   `UsearchStore` on `tmp_path`, `StubEmbeddingBackend(dim=8)`), fixture
   folders under `tmp_path`, and a `_SlowBackend`/`_BlockingBackend` for
   the stop tests. Reset the write-lock and vectors module state per test
   (the autouse fixture at `test_kb_indexer.py:37`). For the stale test,
   delete `{tmp_path}/vectors/{kb_id}.usearch` and inject a store factory
   that returns a **new** `UsearchStore` instance on the next pass (or
   reset the dispatcher singleton).
5. **Docs** per AC-11. **Flight log** entry: Changes Made, test-count
   deltas, `make test-unit` figures, the drain-order list as asserted, any
   deviation with reason.

## Edge Cases

- **`request_index` during a pass** sets the event; the loop runs another
  pass immediately after — coalesced, never lost.
- **KB deleted mid-pass** (only possible if a route skipped `stop`):
  repository calls raise `KeyError`; per-item catches log and continue,
  `list_folders` returns `[]`; the pass ends `idle`. Harmless.
- **Model missing** (`get_embedding_backend` raises
  `EmbeddingModelMissingError`): the pass's resource resolution raises →
  logged, `stopped`; the doctor gate is the operator's diagnostic.
- **Two KBs indexing concurrently**: only the embed+upsert pair is
  serialised by `_embed_lock`; walks and extraction interleave freely.
- **`stop` racing `request_index`**: `stop_requested` is checked at loop
  top and between items; a `request_index` after `stop` returns calls
  `start`, which sees `task.done()` and creates a fresh task with
  `stop_requested = False`.
- **`/status` for a KB whose worker died** reads `stopped` until the next
  `request_index`; the folder list still reports each folder's last
  status.
- **`/source` on a file over the cap**: the extractor still reads it (the
  cap is the indexer's), so a 10 MiB+ body is possible; accepted per
  DD-8's operator bar (the cap is the cap); the item is `failed` anyway.

## Files Affected

- `the_one/knowledge/manager.py` — new
- `the_one/interfaces/web/app.py` — lifespan start/drain wiring
- `the_one/interfaces/web/api.py` — four routes, hook filled, delete-route `stop` integration, `retry_kb_item` docstring
- `tests/test_kb_manager.py` — new
- `tests/test_db_api.py` — route tests (additions)
- `tests/test_mcp_pool.py` — drain-order test extended
- `CLAUDE.md`, `the_one/agents.md`
- `missions/24-knowledge-bases/flights/03-folder-registration-and-indexing/flight-log.md`

## Citation Audit

Checked against the working tree (flight branch `148f704` + Legs 1–2
uncommitted) on 2026-09-15: `app.py` connector block `:319-327`, warm-up
`:328-343`, `yield` `:344`, in-flight/resume gathers `:354-366` (corrected at design review), reaper drain from `:370`, connector drain `:437-443`;
`tests/test_mcp_pool.py` drain-order test `:616-783` (fake manager
`:689-696`, assertion `:769-783`); `api.py` helpers `:258-271`,
`delete_knowledge_base` `:1458-1477`, hook `:1542-1545`, `delete_kb_item`
`:1600-1620`; `connectors/manager.py` accessor `:260-271`; `indexer.py`
`IndexContext` `:89-101`, `ItemOutcome` `:105-112`, `FlushPolicy` `:248-283`,
`rebuild_kb` `:285`; `local.py::EMBEDDING_MODEL_DIRNAME` `:36`;
`test_kb_indexer.py` fixtures `:37-104`; `test_db_api.py` client `:20-48`.
All present; no drift.

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
