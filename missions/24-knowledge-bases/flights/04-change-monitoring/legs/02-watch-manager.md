# Leg: watch-manager

**Status**: completed
**Flight**: [Change Monitoring](../flight.md)

## Objective

Land `the_one/knowledge/watcher.py` complete and unit-tested with no app
wiring: `WatchManager` with one dedicated-thread `watchfiles` subscription
per folder under DD-0's pinned knobs and two-step rule, the DD-2 filter
applied at subscription, the DD-3 settle trigger with hold cap and
suppression, the DD-4 reconcile loop with re-subscribe, the DD-5
`apply_settings`, `start_all` / `drain` / `state`, the 64-subscription cap,
and the module accessor pair — driven in tests through a watch-factory seam
plus one real-`watch` integration test.

## Context

- Flight DD-0 (every knob explicit; two-step `ignore_permission_denied`
  with the root-readability check; `except PermissionError` before
  `except OSError`), DD-1 (entry shape, method shapes, dedicated thread,
  sentinel, closed-loop guard, empty-yield rule, root-removed rule, error
  records, cap, post-subscribe trigger, no-lock rule), DD-2 (the filter is
  Leg 1's `is_watch_candidate`; `excluded_roots` default), DD-3 (timer,
  clamp, suppression), DD-4 (loop, settings read per tick, wake on change,
  resurrect-`stopped` benefit), DD-5 (`apply_settings` semantics), DD-7
  (drain budget and the sentinel's role — wiring itself is Leg 3).
- Leg 1 landed (uncommitted, flight log "Leg 1 — settings-guard-and-gate"):
  `walk.py::is_hidden_name`, `walk.py::is_watch_candidate(path, *, root,
  extensions, excluded_roots)` (pure, never raises, DD-2 clause order);
  `settings.py::MonitoringSettings(watch_enabled, reconcile_interval_
  seconds)` with `MONITORING_KEY`; `load_knowledge_settings(conn).monitoring`;
  `pyproject.toml` declares `watchfiles`; the doctor probe in
  `diagnostics.py::_probe_file_watcher` is the reference for the pinned
  `watch(...)` call. Leg 1's deviation: native delivery on this host takes
  ~250 ms with a 50 ms debounce — a real-`watch` test must not assume
  sub-200 ms delivery.
- `IndexingManager` (`the_one/knowledge/manager.py`) is the model:
  constructor keywords for every constant and factory, `_WorkerEntry`
  dataclass, `set_manager`/`get_manager`, the module docstring stating the
  contract. The watcher takes **no lock** and calls only
  `request_index(kb_id)` (sync, coalescing).
- Host facts (flight log P13–P20): one `deleted <root>` on removal or
  rename, then silence; `ignore_permission_denied=True` swallows a missing
  root; stop latency < 1 ms; paths are root + relative part.
- No route, lifespan or doc change in this leg (Leg 3). `agents.md` gets
  its Knowledge-monitoring section in Leg 3 too; this leg's module
  docstring is the contract statement Leg 3 will cite.

## Inputs

- Working tree: Leg 1's uncommitted changes (do not touch them beyond what
  this leg needs; nothing in Leg 1's files should change here).
- `the_one/knowledge/manager.py:1-45` (module docstring), `:109-127`
  (`_WorkerEntry`), `:131-165` (constructor keywords), `:166-215`
  (`start`, `request_index`, `state`, `wait_until_idle`), `:548-556`
  (`set_manager` / `get_manager`).
- `the_one/knowledge/walk.py::is_watch_candidate` (`:220`),
  `is_hidden_name` (`:62`), `SKIPPED_DIRS`.
- `the_one/knowledge/extractors::supported_extensions`.
- `the_one/knowledge/settings.py::MonitoringSettings` (`:159`),
  `load_knowledge_settings`.
- `the_one/db/repositories.py::KnowledgeBaseRepository.list` (`:408`),
  `KBItemRepository.list_folders` (`:608`).
- `the_one/db/models.py::KBItem` (`id`, `kb_id`, `path_or_url`, `type`).
- `the_one/platform/paths.py::canonicalize`; `the_one/config.py::settings.data_dir`.
- `the_one/diagnostics.py::_probe_file_watcher` — the pinned `watch(...)`
  keyword list to mirror (`rust_timeout` differs: 1000 here, per DD-1).
- `tests/test_kb_manager.py:53-145` — the fixtures and helpers to mirror
  (`_reset_module_state`, `conn`, `kb_repo`, `item_repo`, `_make_kb`,
  `_make_conn_factory`), and its rule: no wall-clock sleeps for test-side
  synchronisation — events only.
- Installed `watchfiles` 1.1.1: `watch(*paths, watch_filter, debounce,
  step, stop_event, rust_timeout, yield_on_timeout, debug, raise_interrupt,
  force_polling, poll_delay_ms, recursive, ignore_permission_denied)`;
  `Change` enum; a `threading.Event` is a valid `stop_event`; construction
  errors surface on the generator's first `next()`;
  `WatchfilesRustInternalError(RuntimeError)` can be raised from any
  iteration.

## Outputs

- `the_one/knowledge/watcher.py` (new), with a module docstring that states
  the contract (the `manager.py` style): purpose; the DD-0 knob rule; the
  message protocol between thread and task; the state words; the trigger
  semantics; suppression; the reconcile loop; the cap; what it shares with
  `supervised-per-entity-worker` and what it does not (DD-1). Contents:
  - Constants (constructor-overridable): `SETTLE_SECONDS = 5.0`,
    `HOLD_CAP_SECONDS = 60.0`, `MAX_WATCHED_FOLDERS = 64`,
    `WATCH_DRAIN_TIMEOUT = 5.0`, `RUST_TIMEOUT_MS = 1000`, `DEBOUNCE_MS =
    1600`, `STEP_MS = 50`.
  - `WatchFactory` type alias: `Callable[[Path, Callable[[Change, str],
    bool], threading.Event, bool], Iterator[set[tuple[Change, str]]]]` —
    `(root, watch_filter, stop_event, ignore_permission_denied)`. **This
    widens DD-1's three-argument seam by one positional flag** so the
    two-step rule is observable through the seam (AC-5); DD-1 is amended
    to match (flight-log note). The default factory is a plain function
    returning `watchfiles.watch(...)` — a generator whose `RustNotify`
    construction runs on the first `next()`, inside the thread body; the
    default `_default_watch_factory` calls `watchfiles.watch` with **every**
    DD-0 keyword explicit (`force_polling=False`, `raise_interrupt=False`,
    `debug=False`, `poll_delay_ms=300`, `recursive=True`, `debounce=
    DEBOUNCE_MS`, `step=STEP_MS`, `rust_timeout=RUST_TIMEOUT_MS`,
    `yield_on_timeout=True`, `ignore_permission_denied=<arg>`,
    `watch_filter=<arg>`, `stop_event=<arg>`).
  - Thread→task messages (small frozen dataclasses or a tagged tuple):
    `_Ready`, `_Changes(changes: frozenset[tuple[Change, str]])`,
    `_Error(reason: str)`, `_Done` (the sentinel, posted from `finally`).
    Every post is `loop.call_soon_threadsafe(queue.put_nowait, msg)` inside
    `try/except RuntimeError` after a `loop.is_closed()` check.
  - `_WatchEntry(task: asyncio.Task | None, thread: threading.Thread |
    None, stop: threading.Event, queue: asyncio.Queue, loop:
    asyncio.AbstractEventLoop, kb_id: str, root: Path, state: str, error:
    str | None)` — `loop` is captured with `asyncio.get_running_loop()` in
    `start()` and handed to the thread body, which has no loop of its own
    (`asyncio.get_event_loop()` on a bare thread raises).
  - `class WatchManager`: constructor `(index_manager, *, conn_factory=
    get_connection, settings_loader=None, watch_factory=
    _default_watch_factory, excluded_roots=None, settle_seconds=…,
    hold_cap_seconds=…, max_watched=…, drain_timeout=…)`; `index_manager`
    is duck-typed (anything with a sync `request_index(kb_id)`);
    `settings_loader` is an optional `Callable[[], Awaitable[
    MonitoringSettings]]` (default: `load_knowledge_settings(await
    conn_factory()).monitoring`) — the seam tests use to drive a sub-floor
    interval via `MonitoringSettings.model_construct(...)`;
    `excluded_roots` defaults to `(canonicalize(settings.data_dir),)`
    resolved at construction.
  - Methods with the DD-1 shapes: sync `start(kb_id, folder: KBItem)`,
    sync `state(folder_id) -> str`, sync `error(folder_id) -> str | None`;
    async `stop(folder_id)`, `stop_kb(kb_id)`, `drain()`, `start_all()`,
    `apply_settings(MonitoringSettings)`; `suppress(kb_id)` as an
    `asynccontextmanager` releasing in `finally`.
  - Thread body `_subscribe_and_pump(entry, filt, factory, loop)`: two-step
    subscribe (first `next()` under `False`; on `PermissionError` — caught
    **before** `OSError` — check `os.access(root, R_OK | X_OK)`; readable →
    re-create with `True`; unreadable → `_Error("root not readable: …")`);
    on the first yield post `_Ready` once; every non-empty set → `_Changes`;
    empty set → nothing; any exception from construction or iteration →
    `_Error(f"{type}: {exc}")`; `finally`: close the generator, post `_Done`.
  - Task body `_run(folder_id, entry)`: consume the queue until `_Done`:
    `_Ready` → `state = "watching"`, `error = None`, `_schedule(kb_id)`
    (DD-1's post-subscribe trigger); `_Changes` → if any `(Change.deleted,
    p)` with `PurePath(normcase(p)) == PurePath(normcase(str(root)))`:
    `_schedule(kb_id)`, set `entry.stop`, `state = "unavailable"`, `error =
    "root removed"`, then keep consuming until `_Done` (never leave the
    thread's `_Done` unread); otherwise `_schedule(kb_id)`; `_Error(reason)`
    → `logger.warning` once naming the folder, `state = "unavailable"`,
    `error = reason`; `_Done` → return. The task never touches the
    database, never `stat`s, never takes a lock.
  - `_schedule(kb_id)`: skip if suppressed; arm/re-arm per DD-3 with the
    `max(0, …)` clamp; the callback `_fire(kb_id)` pops the timer, re-checks
    suppression, and calls `index_manager.request_index(kb_id)`.
  - `suppress(kb_id)`: cancel the KB's timer, add to `_suppressed`, yield,
    `finally` discard.
  - `_reconcile_loop()`: `except asyncio.CancelledError: raise` **before**
    the broad per-iteration `except Exception` (the `manager.py::_run`
    precedent, `:329-335`) so `drain()`'s cancel is clean; then `while
    True`: `m = await self._load_settings()`;
    wait `m.reconcile_interval_seconds` on `self._settings_changed` via
    `asyncio.wait_for`; on the event → clear it and `continue` (re-read);
    on timeout → `await self._tick()`. `_tick()`: list KBs, for each with
    a folder and **not suppressed (checked synchronously right before the
    call)** → `request_index(kb_id)`; then `await
    self._resubscribe_unavailable()`; every exception inside a tick is
    logged and swallowed.
  - `_resubscribe_unavailable()`: iterate a **snapshot**
    (`list(self._entries.values())` — a concurrent route `stop` pops
    entries, and the loop body awaits; the `IndexingManager.drain`
    precedent) and skip any entry no longer in `self._entries` at the
    moment it is reached; an entry removed by a delete route is sufficient
    protection — no database re-check. For every remaining entry at
    `unavailable` while the watcher is enabled: if a slot is free under the cap, reset the
    entry (`state = "starting"`, new stop event and queue) and start its
    thread and task; otherwise leave it (`"watch limit reached (64)"`).
  - `start(kb_id, folder)`: no-op if an entry with a live task exists; if
    the watcher is disabled → no entry (reads `off`); create the entry
    **before** any task; if live subscriptions ≥ `max_watched` → `state =
    "unavailable"`, `error = "watch limit reached (N)"`, no thread, no
    task; else start the daemon thread and the task.
  - `stop(folder_id)`: set the stop event; if a task exists,
    `wait_for(task, drain_timeout)`; on timeout `task.cancel()` then
    `with contextlib.suppress(asyncio.CancelledError, Exception): await
    task` (the `IndexingManager.stop` shape); pop the entry;
    no error for a missing entry or a task-less entry. `stop_kb(kb_id)`:
    cancel the timer, `stop` every entry of that KB concurrently.
  - `apply_settings(m)`, `start_all()` and `drain()` run under one
    `asyncio.Lock` (`_lifecycle_lock`) so two concurrent settings `PUT`s
    cannot interleave a disable with an enable (Developer design review
    Q1); `start` itself is synchronous with no await between its liveness
    check and entry creation, so it is idempotent by construction and
    `start_all` twice is a no-op the second time. `apply_settings(m)`:
    record `enabled`; disabled → cancel every timer, stop every entry
    concurrently; enabled → `await self.start_all()`; always set
    `_settings_changed`. `start_all()`: load settings, start the
    reconcile-loop task if absent or done; if enabled, `start` every
    folder of every KB. `drain()`: cancel timers, cancel the loop task,
    stop every entry concurrently under `drain_timeout`, clear.
  - `set_manager` / `get_manager` module accessors.
- `tests/test_kb_watcher.py` (new), mirroring `test_kb_manager.py`'s
  fixtures; a `_FakeIndexManager` recording `request_index` calls and
  setting an `asyncio.Event` per call; a `_QueueFactory` whose generator
  reads a thread-safe `queue.Queue` of items (`set(...)` for changes,
  `set()` for a timeout yield, an exception instance to raise, honouring
  the stop event with a short poll) so every test drives the same thread
  hop as production; small real settle/hold values (50 ms / 200 ms) with
  no fake clock; tests as in the Acceptance Criteria.
- Flight log: Leg 2 progress entry.

## Acceptance Criteria

- [x] **AC-1 — Contract and knobs.** `watcher.py` has the module docstring above; `_default_watch_factory`'s source names every DD-0 keyword (a source-level test scans for each of `force_polling=False`, `raise_interrupt=False`, `debug=False`, `poll_delay_ms=`, `recursive=True`, `debounce=`, `step=`, `rust_timeout=`, `yield_on_timeout=True`, `ignore_permission_denied=`); the two-step subscribe's `except PermissionError` precedes `except OSError` (source-level test).
- [x] **AC-2 — Filter at subscription.** The factory receives a `watch_filter` that, for a root `R` with `excluded_roots=(R/data,)`, returns True for `R/a.md`, `R/sub`, and `R` itself, and False for `R/.git/x.md`, `R/node_modules/y.txt`, `R/data/z.md`, `R/a.png` (asserted by capturing the filter passed to a recording factory and calling it).
- [x] **AC-3 — One request per window.** With settle 50 ms / hold 200 ms: five `_Changes` sets fed back-to-back with no delay → wait for the first `request_index(kb_id)` (beyond the one post-subscribe trigger of AC-8, which the test consumes first), then wait a further 4× settle: still exactly one (an idle-window check, not a mid-burst count — thread-hop jitter on a loaded host must not fail it); sets fed every 40 ms for 400 ms → at least two and at most four calls (the hold cap fires); after silence, no further calls. A run of ten empty timeout yields → zero calls.
- [x] **AC-4 — Root removal.** A `_Changes` set containing `(Change.deleted, str(root))` → exactly one `request_index`, then `state(folder_id) == "unavailable"`, `error(folder_id) == "root removed"`, the thread stopped (joined within 1 s), the task finished; a set `{(Change.modified, str(root))}` → one `request_index` and the state stays `watching`. A root with a dotted name (`tmp_path / "notes.d"`) behaves identically.
- [x] **AC-5 — Error records.** A factory raising `FileNotFoundError` at construction, one raising `OSError(errno.ENOSPC, …)`, one raising `RuntimeError`, and one raising `RuntimeError` after a first successful yield → each ends `unavailable` with the reason containing the exception type name, the task finished, exactly one warning logged (caplog). A factory raising `PermissionError` at construction with a readable root → a second factory call with `ignore_permission_denied=True` (the recording factory asserts the flag sequence `[False, True]`) and the entry reaches `watching`; the same with an unreadable root (`chmod 000`, skipped on Windows or as root) → `unavailable`, reason contains "not readable", no second call.
- [x] **AC-6 — Real `watch`.** Against a `tmp_path` folder with the default factory: writing `a.md` after `watching` → a `request_index` within 5 s; `rmtree(root)` → `unavailable` / `"root removed"` within 5 s; the test `pytest.skip`s when a 1 s self-probe on `tmp_path` delivers nothing (the Leg 1 pattern). Also with the default factory: `start` on a missing root → `unavailable` (never `watching`) with the reason containing `FileNotFoundError`.
- [x] **AC-7 — Cap.** `max_watched=2`: three `start`s → the third is `unavailable` with `"watch limit reached (2)"`, `task is None`; `stop` of one live entry then `_resubscribe_unavailable()` → the third reaches `watching`; `stop`/`drain` on a cap-created entry return without error.
- [x] **AC-8 — Post-subscribe trigger and states.** `start` twice for the same folder → one thread, one task, one post-subscribe trigger; `start_all` twice → no change; two concurrent `apply_settings` calls (disable and enable, gathered) → a consistent end state (every folder either all `watching`/`starting` or all `off`, matching whichever call ran last), no exception. Immediately after `start`, `state == "starting"`; after the first (empty) yield → `"watching"` and exactly one `request_index`; an unknown folder id → `"off"`; with `apply_settings(watch_enabled=False)` → every entry gone, `state == "off"`, no thread alive (`threading.enumerate()` check by name), timers cancelled (no late `request_index`); `apply_settings(watch_enabled=True)` → `start_all` re-subscribes every folder of every KB in the database (uses the `conn` fixture with two KBs, three folders).
- [x] **AC-9 — Suppression and concurrency.** A `stop_kb` gathered with a `_tick()` whose `_resubscribe_unavailable` is running → no `RuntimeError` (dictionary size), the entries gone afterwards. Inside `async with manager.suppress(kb)`: `_schedule(kb)` and a fed `_Changes` set produce no `request_index`; a timer armed before entering is cancelled; a `_tick()` skips that KB but serves another; after exit, a new `_Changes` set triggers normally; the context manager releases when the body raises.
- [x] **AC-10 — Reconcile loop.** With a `settings_loader` returning `MonitoringSettings.model_construct(watch_enabled=True, reconcile_interval_seconds=0.05)` and two KBs (one with a folder, one without): within 1 s the folder KB has ≥ 2 `request_index` calls and the folder-less KB has none; changing the loader's interval to 10 s and calling `apply_settings` wakes the loop (no tick lands in the next 300 ms); an entry made `unavailable` by an error factory is re-subscribed on the next tick once the factory succeeds (the test's factory fails once, then yields).
- [x] **AC-11 — Stop and drain.** `stop(folder_id)` returns in well under `drain_timeout` (assert < 1 s) because of the sentinel; `drain()` with three live entries returns < 1 s, leaves no thread alive, no timer armed, the loop task done; a factory whose generator ignores the stop event (blocks 3 s) → `stop` returns at `drain_timeout` (set to 0.3 s in the test) with the task cancelled and no exception.
- [x] **AC-12 — No lock, no DB in the task.** A source-level test asserts `watcher.py` does not import `write_transaction`, `_embed_lock`, or any repository other than `KnowledgeBaseRepository` / `KBItemRepository` (used only by `start_all` and `_tick`), and that `_run`'s source contains no `await ` of a repository or store method.
- [x] **AC-13 — Gates.** `make lint` clean; `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_kb_watcher.py tests/test_kb_walk.py -x --timeout 60` green; Leg 1's targeted files still green; `make test-unit` once at leg end, green, figures in the flight log.

## Verification Steps

- AC-1/AC-12: the source-level tests in `tests/test_kb_watcher.py`.
- AC-2–AC-11: the targeted run above (every test event-synchronised; the only sleeps are inside fake factories running on their own thread, like `test_kb_manager.py`'s fake-slow backends).
- AC-13: `make lint`; `make test-unit` (foreground, alone, ≥ 900 s budget).

## Implementation Guidance

1. Module skeleton and docstring; constants; the factory and message
   types; `_WatchEntry`.
2. Thread body and task body; `start` / `stop` / `stop_kb` / `state` /
   `error`. Test AC-2, AC-4, AC-5, AC-8 (states), AC-11 (stop) first with
   the queue factory.
3. Trigger: `_schedule` / `_fire` / `suppress`. Test AC-3, AC-9.
4. Loop: `_load_settings`, `_reconcile_loop` (CancelledError re-raised
   first), `_tick`, `_resubscribe_unavailable` (snapshot), `start_all`,
   `apply_settings`, `drain` (all three under `_lifecycle_lock`). Test
   AC-7's re-subscribe half, AC-8 (settings and concurrency), AC-9's
   concurrency clause, AC-10, AC-11 (drain). (AC-7's cap-at-`start` half
   belongs to step 2.)
5. Real-`watch` test (AC-6) last; accessors; source-level tests (AC-1,
   AC-12).
6. Flight log entry; leg `landed`. Do not commit.

## Edge Cases

- **`start` called before a loop is running** (a sync caller outside the
  loop): not supported — document that `start` requires a running loop
  (`asyncio.get_running_loop()`), like `IndexingManager.start`.
- **Two `_Ready`s**: the thread posts `_Ready` once (a flag), so a
  re-subscribe after `False → True` does not double-trigger.
- **Root removed while the KB is suppressed**: the final trigger is
  dropped by suppression; the next tick's walk marks the folder `failed`
  anyway (the walk is correctness).
- **`_Changes` after `entry.stop` was set by root removal**: ignored (the
  task is draining to `_Done`).
- **`apply_settings(False)` while a thread is mid-yield**: the stop event
  ends it within a step; `stop` awaits the sentinel.
- **A `KBItem` whose `path_or_url` is not a directory at `start`**: the
  thread's first `next()` raises `FileNotFoundError` (or `NotADirectory
  Error`, an `OSError`) → `unavailable`; the reconcile tick retries.
- **Thread naming**: `the-one-watch-<folder_id>` so AC-8/AC-11 can assert
  on `threading.enumerate()`.
- **Loop task exceptions**: `_reconcile_loop` catches everything but
  `CancelledError` per iteration and continues; a failing
  `settings_loader` falls back to `MonitoringSettings()` with a warning.
- **`settings.data_dir` re-pointed after construction** (tests): pass
  `excluded_roots` explicitly; the default is resolved once.

## Files Affected

- `the_one/knowledge/watcher.py` — new
- `tests/test_kb_watcher.py` — new
- `missions/24-knowledge-bases/flights/04-change-monitoring/flight-log.md`

## Citation Audit

Checked at the Leg 1 working tree on 2026-09-16: `manager.py` docstring
`:1-45`, `_WorkerEntry` `:109`, constructor `:131`, `start` `:166`,
`request_index` `:192`, `state` `:210`, accessors `:548`/`:554`; `walk.py:62`
(`is_hidden_name`), `:220` (`is_watch_candidate`); `settings.py:159`
(`MonitoringSettings`); `repositories.py:408`, `:608`;
`tests/test_kb_manager.py:53-145`. All present.

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
