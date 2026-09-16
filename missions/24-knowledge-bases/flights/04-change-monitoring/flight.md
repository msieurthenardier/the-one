# Flight: Change Monitoring

**Status**: in-flight
**Mission**: [Knowledge Bases](../../mission.md)

## Contributing to Criteria

- [ ] Files in a registered folder index automatically, and additions, modifications, and deletions are reflected without operator action or an app restart *(this flight lands the event path and the periodic reconciliation walk; Flight 3 landed the walk itself, run only at registration, at startup, on re-index and on request; behavior-test-backed here for the event path, the periodic path, and recovery after a folder disappears and returns)*
- [ ] Operator can register a folder on disk as a knowledge base source, and see each discovered item's index status including failures *(extended: the per-KB status projection now reports whether each folder is being watched, and why not when it is not)*
- [ ] Existing installs upgrade with no data loss, the unit gate stays green, and the frozen Windows installer still builds and runs *(no schema change; one new `app_metadata` record with defaults applied on read; a ninth `doctor` gate proves the file-watcher native extension survives the freeze; one frozen run at flight close)*

---

## Pre-Flight

### Objective

Make a registered folder's index follow the folder without the operator
doing anything: a supervised per-folder filesystem watcher, backed by a
periodic reconciliation walk, both of which only ever ask the Flight 3
`IndexingManager` for a pass. The watcher is a latency optimisation and
never a source of truth — it subscribes with the walk's own skip rules,
coalesces bursts of events into one `request_index` per settle window,
classifies nothing, takes no lock, and degrades visibly to walk-only when a
folder cannot be watched. The periodic walk is what makes the mission
criterion true on every platform, including the ones where events can be
dropped. Both are operator-configurable from the existing knowledge
settings, applied live. No screen ships in this flight; acceptance is a
behavior test on a dedicated dev instance.

### Open Questions

- [x] Where the reconciliation interval and the watcher on/off switch live → DD-5 (operator: Administration knowledge settings, 2026-09-16)
- [x] Default reconciliation interval → DD-4 (operator: 5 minutes; a Flight Director proposal accepted at the interview)
- [x] Settle window and hold cap for event coalescing → DD-3 (operator: 5 s settle, 60 s hold cap; a Flight Director proposal accepted at the interview)
- [x] Whether registration refuses a folder that contains the data directory → DD-6 (operator: yes, 422, plus the filter)
- [x] Whether the frozen build gets a file-watcher `doctor` gate → DD-9 (operator: yes, frozen-only)
- [x] The vehicle for the Windows 1M `usearch` re-measure (Flight 3 debrief Recommendation 7) → DD-12 (operator: fold into Flight 6 / mission close)
- [x] Whether this flight carries a HAT leg → no: no operator-visible surface (the rule set at the Flight 3 debrief); the behavior test is the acceptance gate and the walk-through folds into Flight 6's HAT
- [x] What happens to a watch when its root directory is removed → DD-1 (probed at planning with the native backend: exactly one `deleted <root>` and then silence; the watcher must recognise the root's own deletion, leave the subscription and re-subscribe on the reconcile tick)
- [x] Which `watchfiles` backend the app pins, given that the library silently polls on WSL → DD-0 (operator: native everywhere, 2026-09-16, at the design-review checkpoint)
- [x] Upper bound on watched folders, given one dedicated thread per subscription → DD-1 (operator: 64, degrade past it; a Flight Director proposal accepted at the design-review checkpoint)
- [x] Whether the file-watcher gate is frozen-only → DD-9 (operator, revised at the design-review checkpoint: import unconditional, native round-trip frozen-only)

### Design Decisions

**DD-0 — Every `watchfiles` knob is pinned explicitly at both call sites; no library or environment default is inherited**
- `watchfiles` chooses its backend at call time: `main.py::_default_force_polling` returns `True` on WSL (`'microsoft-standard'` in the kernel release) and whenever `WATCHFILES_FORCE_POLLING` is set, and `WATCHFILES_POLL_DELAY_MS`, `WATCHFILES_DEBUG` and `WATCHFILES_IGNORE_PERMISSION_DENIED` are likewise read from the environment. Found by the Architect at design review (cycle 1): the Flight Director's first four behaviour probes had measured the polling backend on this WSL host without knowing it. The general rule, stated once and applied at both sites — the subscription in `the_one/knowledge/watcher.py` and the gate in `the_one/diagnostics.py`: **`force_polling=False`, `raise_interrupt=False`, `debug=False`, `poll_delay_ms=300` (inert, pinned so an env var cannot reach it), `recursive=True`, explicit `debounce`, `step`, `rust_timeout`, `yield_on_timeout`, and `ignore_permission_denied` set per the two-step rule below.** **`ignore_permission_denied=True` swallows *every* registration error, not only `EACCES`** — verified at design review cycle 2 and re-verified by the Flight Director (flight log P19), contrary to the `.pyi` docstring: with it on, a subscription against a missing root constructs, yields empty timeout sets for ever, and never delivers even after the directory appears; with it off a missing root raises `FileNotFoundError` and an unreadable subdirectory raises `PermissionError` at construction. The rule is therefore **two-step**: subscribe with `ignore_permission_denied=False`; only if that raises `PermissionError` **and the root itself is readable** (one `os.access(root, R_OK | X_OK)` at subscribe time, never in the event path — a `PermissionError` on the root is the same exception type as one on a subtree, and retrying with `True` on an unreadable root would construct a subscription with zero watches that the first empty yield then reports as `watching`; Architect, cycle 3), subscribe again with `True`; an unreadable root goes `unavailable` with the permission reason (Flight Director's call at cycle 3: visible, not silently walk-carried). `except PermissionError` must precede any `except OSError` — it is a subclass, and an `OSError` clause written first would silently remove the retry. Every other registration error (a missing root, inotify's `ENOSPC`, a Rust-side `RuntimeError`) stays visible, which is what keeps the mission's visible degrade real. Verified at cycle 3: `deleted <root>` is still delivered under the `True` retry, and an unreadable subdirectory created after a successful subscribe never raises, so the retry is only ever needed at construction. Native notification everywhere is the operator's decision (2026-09-16): the shipped Windows build, Linux and macOS all use it, so dev and test must exercise the same event stream. Consequence on a WSL dev host, verified with the pinned value: a folder under `/mnt/c` (drvfs) receives **no events at all** while still reading `watching`; the periodic walk (DD-4) is what keeps it current there, and `agents.md` records it. Polling as a fallback is rejected for the app: it stats every file every 300 ms, which is the walk done badly.

**DD-1 — `WatchManager`: one supervised task per `folder` item, a third instance of the `supervised-per-entity-worker` shape in its dict-of-entries, `start`/`stop`/`drain`/`state`, accessor pair and deliberate drain placement, but **without** the wake/idle events and the `shield`+`wait_for` cooperative stop (a watch has no pass to finish — the stop event ends it within a step); Leg 3's `agents.md` citation states exactly what is shared and what is not; each subscription runs `watchfiles.watch` on its own dedicated thread; the task only ever calls the trigger; at most 64 subscriptions**
- `the_one/knowledge/watcher.py::WatchManager`, keyed by **folder item id**
  (not by knowledge base — folders are registered and deleted one at a
  time, and the Flight 3 route hooks already fire per folder). Entry:
  `_WatchEntry(task: asyncio.Task | None, stop: threading.Event, kb_id,
  root: Path, state, error: str | None)` — `task` is `None` for an entry
  the cap created without a thread, and `stop`/`drain`/`apply_settings`
  handle such entries without error (AC). Surface, following the `agents.md` convention, with each method's
  shape pinned: **sync** `start(kb_id, folder: KBItem)` (no-op if a live
  task exists; **always creates the entry before the task**; sync so the
  sync `_after_folder_registered` hook can call it) and `state(folder_id)
  -> "starting" | "watching" | "unavailable" | "off"`; **async** `stop(
  folder_id)`, `stop_kb(kb_id)`, `drain()`, `start_all()` and
  `apply_settings(MonitoringSettings)` (each awaits the tasks it ends);
  `suppress(kb_id)`, an async context manager (DD-3); and the module
  accessor pair `set_manager` / `get_manager`. `"off"` is what an
  unknown folder id reads (no entry: the watcher is disabled, or the
  manager is not installed); `"starting"` is an entry whose subscription
  has not yet reported its first yield; `"watching"` is reported **only
  after the first yield** (an empty timeout yield counts — it proves the
  subscription is established); `"unavailable"` means the entry exists but
  the subscription is down, with `error` saying why. Constructor keywords
  override the settle and hold-cap seconds, the subscription cap, the
  excluded roots (DD-2), and — the test seam — the **watch factory**
  (`Callable[[Path, filter, threading.Event, bool], Iterator[set[tuple[
  Change, str]]]]` — the fourth argument is `ignore_permission_denied`, so
  the two-step rule is observable through the seam; widened at Leg 2
  design — defaulting to `watchfiles.watch` with the DD-0 kwargs), so
  unit tests feed synthetic change sets through a generator reading a
  thread-safe `queue.Queue`, exercising the same thread hop as production,
  and one integration test runs the real `watch` against a `tmp_path`
  folder.
- **Dedicated thread, not `awatch`.** `awatch` blocks one worker of
  `anyio`'s *shared* default limiter (40 tokens on this host — the same
  pool Starlette's `run_in_threadpool` and the MCP stack draw from;
  Architect, cycle 1), so forty watched folders would deadlock the web
  layer's sync offload; `asyncio.to_thread` would instead pin workers of
  the default executor the indexer's embedding and walk calls share. Each
  entry therefore owns one `threading.Thread(daemon=True)` running the
  sync `watchfiles.watch(root, watch_filter=…, stop_event=entry.stop,
  rust_timeout=1000, yield_on_timeout=True, <DD-0 kwargs>)` and posting
  every yielded set to the loop with `loop.call_soon_threadsafe` into an
  `asyncio.Queue` the entry's task consumes. The thread subscribes
  under DD-0's two-step rule (`ignore_permission_denied=False`, retried
  with `True` only on `PermissionError`), so a construction error
  (`FileNotFoundError` for a missing root, an `OSError` such as inotify's
  `ENOSPC`, a `RuntimeError` from the Rust side) surfaces on the
  generator's first `next()`. **The whole `for changes in gen:` body is
  wrapped**, not only construction: `WatchfilesRustInternalError` (a
  `RuntimeError`) can be raised from any iteration, and an error record
  is posted for either case. **The thread posts a terminal sentinel from a
  `finally`**, and the entry's task returns on it — without that the task
  would sit in `queue.get()` for ever and every `stop`, `apply_settings(
  False)` and `drain` would burn its full timeout (Architect, cycle 2).
  Every post is `loop.call_soon_threadsafe` inside `try/except
  RuntimeError` with a `loop.is_closed()` check, because a thread
  abandoned at the drain timeout may post after the loop has closed.
  Measured stop latency from `entry.stop.set()` to thread exit with
  `rust_timeout=1000, step=50`: under 1 ms on this host (flight log P20;
  the Architect measured 16 ms) — the 5 s drain budget is generous by
  three orders of magnitude. Each subscription is one inotify *instance*
  as well as one descriptor per directory; `max_user_instances` is 8,192
  here but 128 by default on many distributions, so the 64-folder cap
  can take half of a default budget shared with every other program the
  operator runs — recorded in `agents.md` beside the descriptor note. **Cap: `MAX_WATCHED_FOLDERS = 64`** (operator's choice,
  2026-09-16, from a Flight Director proposal): the sixty-fifth `start`
  creates the entry as `unavailable` with reason `"watch limit reached
  (64)"` and no thread; registration is never refused for it; the
  reconcile tick's re-subscribe (below) promotes it once a slot frees.
  Flight 6's inventory renders the state.
- Per-folder task, a supervisor loop: subscribe; on the first yield mark
  `watching` **and fire one `_schedule(kb_id)`** — the registration hook
  and the reconcile tick both request the index *before* the subscription
  exists, so without this one extra walk (24 ms per 2k files) every change
  landing in that window, including between the two attempts of the
  two-step subscribe, would wait a full interval (Architect, cycle 3); for each **non-empty** change set that survives the filter
  (DD-2) call `self._schedule(kb_id)` (DD-3) and nothing else. **An empty
  timeout yield — one arrives every second under `rust_timeout=1000,
  yield_on_timeout=True` — marks `watching` on the first occurrence and
  does nothing else, ever**: if it re-armed the settle timer the hold cap
  would fire a `request_index` per knowledge base every 60 s for the life
  of the process, invisibly (Architect, cycle 2); pinned by a unit AC
  ("a run of empty yields produces zero `request_index` calls"). **If the set contains a
  `Change.deleted` whose path equals the root itself, the task schedules
  one final trigger (so the next walk marks the folder `failed`, Flight 3
  DD-3), stops its thread, marks the entry `unavailable` with reason
  `"root removed"`, and is re-subscribed on every reconcile tick**
  (`_resubscribe_unavailable`, run by the DD-4 loop) — a drive that comes
  back is re-watched without operator action. Verified with the pinned
  native backend (flight log P13/P14): removing or renaming the root
  emits **exactly one** `deleted <root>` and the subscription is then
  silently dead (the kernel drops the watch; a directory recreated at the
  same path is a new inode), so this one event is the only chance to
  notice — which is why DD-2 guarantees the root's own path always passes
  the filter. A `modified <root>` change is an ordinary directory
  modification (a file created or removed inside it) and **must not**
  tear the watch down — pinned by a unit AC driving a synthetic
  `{(modified, root)}` set through the factory seam. Any error record from
  the thread takes the same path as root removal: log a warning once
  naming the folder and the reason, `unavailable`, retry on the tick;
  pinned by ACs driving factories that raise `FileNotFoundError`,
  `OSError(ENOSPC)` and `RuntimeError` at construction **and** one whose
  generator raises after a first successful yield (the `remote-cap-needs-
  a-negative-test` rule — the cap is enforced in the Rust extension, a
  different code path), plus **one AC through the real `watch`** for the
  missing-root case, since the factory seam alone would pass green
  against a library that swallowed the error (cycle 2's finding). A
  re-subscribe attempt against a still-missing root costs one
  `FileNotFoundError` per tick per such folder — accepted at a 300 s
  default interval; no backoff. The task never opens the database, never stats a file,
  never decides whether a path is a file, a directory or a symlink — the
  walk decides everything (Flight 3 debrief Recommendation 2: *the watcher
  is latency, the walk is correctness*).
- Lock order: the task holds no lock and calls only
  `IndexingManager.request_index`, which is synchronous and takes none, so
  the manager lock → store per-KB lock → write lock invariant
  (`manager.py` module docstring) is never in play.
- Rejected: `awatch` (the shared-limiter problem above); one subscription
  per knowledge base over all its folders (`watch` accepts several paths,
  but a folder added or removed would restart the whole subscription and
  drop events for the others mid-swap); classifying events in the watcher
  to skip the walk on a "modified" event — the reconcile's `(size, mtime)`
  then hash check is cheaper than getting that right, and it is the thing
  the mission says must be the source of truth.

**DD-2 — The filter is the walk's own rule, extracted once; the watcher drops what the walk would never index, plus anything under the data directory; it is a *trigger* filter, never a subscription filter**
- `walk.py` gains two pure functions. `is_hidden_name(name: str) -> bool`
  (dot-prefixed) replaces the inline `name.startswith(".")` check **at the
  same site** in `walk_folder`, so the uncounted-skip semantics of
  `WalkResult` are unchanged; the `name in SKIPPED_DIRS` check stays where
  it is (applied to directories only, after the dir/file split, and
  counted in `skipped_dirs`) — `tests/test_kb_walk.py` stays green
  untouched, and the Architect's cycle-1 finding that a merged predicate
  called at the top of the loop would silently change the counters is
  recorded here as the reason. `is_watch_candidate(path: str, *, root:
  Path, extensions: frozenset[str], excluded_roots: tuple[Path, ...]) ->
  bool` is the watcher-side composite, **never raising**, applied in this
  order: (1) `PurePath(os.path.normcase(path)) == PurePath(os.path.normcase(
  str(root)))` (a `PurePath` comparison after `normcase` on both sides —
  never a raw string compare, which a trailing or doubled separator
  would defeat, since a drive-letter case or `\\?\` prefix difference
  on Windows would make the root's own deletion invisible for ever) →
  **True, always** (the root's own deletion must reach the task even when
  the root's name carries a dotted suffix such as `notes.d` — Architect,
  cycle 1); (2) relativise with the same normalisation,
  `PurePath(normcase(path)).relative_to(normcase(root))`, inside `try` — a `ValueError`
  (macOS reporting `/private/var…` for `/var…`, a Windows drive-letter
  case difference, any future backend) returns **False** rather than
  propagating out of the generator and killing the subscription; (3) any
  relative component that `is_hidden_name` or is in `SKIPPED_DIRS` →
  False; (4) the path under any of `excluded_roots` (`PurePath.
  is_relative_to`) → False; (5) a final component **with** a suffix, **lower-cased** (the walk's
  own `os.path.splitext(name)[1].lower()` — `NOTES.MD` is an ordinary
  filename on Windows and macOS), outside `extensions` → False; a final component **without** a suffix →
  True (it may be a directory being created or removed, and the walk is
  the one that finds out). All string and `PurePath` work — no `stat`,
  no `resolve`: the root is canonical (registration canonicalised it,
  Flight 3 DD-1) and `watchfiles` reports paths as the subscribed root plus
  a relative part (verified, flight log P16). Tests: dot-prefix and
  `SKIPPED_DIRS` at any depth, unsupported suffix, an upper-cased
  supported suffix, no suffix, excluded root, the root itself with a
  dotted name and with a different case, a path outside the root. The
  Windows path-shape premise (what `watchfiles` reports as the root on
  Windows) is unverified at planning — recorded in the Adaptation
  Criteria; the normalisation is the defence.
- **Two recorded, latency-only divergences from the walk** (Architect,
  cycle 3): a directory rename or removal emits only directory-level
  events, so renaming or deleting a directory whose *name* carries an
  unsupported suffix (`build.d`) produces no trigger until the periodic
  tick — accepted, because the alternative (letting `added`/`deleted`
  events on any suffixed name through) would turn a build tree's `.o`
  churn into a walk per settle window, which is the noise the suffix
  clause exists to stop; and clause (3) tests `normcase`d components, so
  `SKIPPED_DIRS` matching is case-insensitive on Windows where the walk's
  is case-sensitive — a `Node_Modules` directory would not trigger there
  but would be walked. The walk remains correctness in both cases.
- **Honesty about what the filter does not do**: `watchfiles` applies
  `watch_filter` *after* the native notifier has registered watches for
  the whole tree (`main.py::_prep_changes`), so a recursive subscription
  consumes one inotify watch descriptor for every directory under the
  root, `.git`, `node_modules` and `venv` included — the mission's "one
  watch descriptor per directory against a per-user cap" concern is not
  reduced by filtering. The filter decides what *triggers* a pass; the
  ENOSPC degrade path (DD-1) is what happens when the cap is hit, and the
  walk is what keeps such a folder current. Recorded in `agents.md`.
- Symlinks are not filterable from an event path without a `stat`, so a
  symlink's change triggers a pass the walk then skips it in — harmless
  (a walk of 2,079 files costs 24 ms, Flight 3 measurement) and the only
  way to keep the watcher stat-free.
- `excluded_roots` defaults to `(canonicalize(settings.data_dir),)`,
  resolved when the `WatchManager` is constructed and overridable by
  constructor keyword (test fixtures re-point `settings.data_dir` after
  import; `usearch_store.py` resolves it lazily for the same reason). The
  indexer writes the database, its WAL and the vector sidecar under the
  data directory; without this exclusion a folder that contained it would
  feed every indexing write back into the watcher as a new pass forever.
  DD-6 makes that registration impossible from now on; the filter keeps an
  install that already has such a folder (registered under Flight 3) from
  looping.
- Extension set: `supported_extensions()` read once per subscription (a
  new extractor registered later needs a restart to be watched for — the
  same rule Flight 3's walk applies per pass; recorded, not special-cased).

**DD-3 — The trigger: one `request_index(kb_id)` per settle window, per knowledge base; 5 s settle, 60 s hold cap (operator's choice, 2026-09-16); suppressed while a delete route holds the knowledge base**
- `WatchManager._schedule(kb_id)`: if no timer is armed for `kb_id`,
  record `first_event_at = now` and arm `loop.call_later` for
  `SETTLE_SECONDS = 5`; if one is armed, cancel it and re-arm for
  `max(0, min(now + SETTLE_SECONDS, first_event_at + HOLD_CAP_SECONDS =
  60) - now)` (clamped — past the hold cap the raw value is negative;
  Architect, cycle 1). When it fires: `index_manager.request_index(kb_id)`
  unless the knowledge base is suppressed; forget the timer. A saved file
  is therefore indexed about five seconds after the last write to the
  folder; a folder that never stops changing (a long copy, a build) is
  still indexed at least once a minute. Unit tests use **small real
  values** through the constructor keywords (a 50 ms settle, a 200 ms hold
  cap) and await an event the fake index manager sets — no fake clock, no
  scheduler seam (the Verification bullet is worded accordingly); the AC
  that pins DD-3's whole point is "N events inside one window → exactly
  one `request_index`", and "events spanning past the hold cap → a second
  one".
- `request_index` is already coalescing (Flight 3 DD-7): a trigger landing
  mid-pass produces exactly one more pass after the current one, never a
  queue. A pass that indexes a file still being written picks up partial
  content; the write's final event triggers another pass whose reconcile
  sees the `(size, mtime)` change and re-indexes it — convergence, not a
  correctness gap; the item's `indexed_at` moving twice is the visible
  trace.
- **Suppression** (Architect, cycle 1: the reconcile tick or a sibling
  folder's timer could otherwise restart the worker between a delete
  route's `manager.stop` and its repository delete, re-opening the race
  Flight 3 AC-10 closed): `async with watch.suppress(kb_id):` cancels the
  knowledge base's armed timer, and for the duration makes `_schedule`,
  the timer callback and the reconcile tick skip that knowledge base.
  Both delete routes hold it across `stop → delete → request_index`
  (DD-8); a `None` manager is `contextlib.nullcontext()`. The context
  manager releases in a `finally` (`delete_knowledge_base`'s repository
  `KeyError → 404` fires inside the guarded region; `delete_kb_item`'s two
  404s fire before it), and the reconcile tick performs its
  suppression check **synchronously, with no `await` between the check
  and `request_index`** — the tick's repository listings are async, and
  a check taken before them would re-open the window mid-iteration
  (Architect, cycle 2). Timers are also
  cancelled by `stop_kb`, by `drain`, and by `apply_settings` turning the
  watcher off, so no `request_index` can land on an indexing manager that
  is draining (DD-7 ordering).
- The mission's rationale stands: Linux inotify is bounded per user and
  Windows drops events under buffer overflow, so a trigger that misses is
  repaired by DD-4, never by retrying the event.

**DD-4 — Periodic reconciliation: one loop in the `WatchManager`, `request_index` for every knowledge base that has a folder, every `reconcile_interval_seconds` (default 300, operator's choice); the loop also re-subscribes `unavailable` folders and, as a side effect, resurrects a `stopped` worker**
- `WatchManager._reconcile_loop()`: wait `interval` seconds (an
  `asyncio.Event` the settings hook sets cuts the wait short so a changed
  interval applies at once, not after one old interval), then for every
  knowledge base (`KnowledgeBaseRepository.list()`) with at least one
  folder (`KBItemRepository.list_folders`) and not suppressed (DD-3), call
  `request_index(kb_id)`; then `_resubscribe_unavailable()` (DD-1: root
  removed, an error record, the cap). The interval is read from the stored
  `MonitoringSettings` on every tick (`load_knowledge_settings`, the
  Flight 3 per-pass precedent for chunking). No startup catch-up: the
  `IndexingManager.start_all` walk at boot already is one. The loop runs
  whether or not the watcher is enabled — with the watcher off it is the
  only way changes are reflected, which is the mission's stated fallback.
  Exceptions inside a tick are logged and the loop continues (the purge
  and catalog-refresh loops' shape, `app.py`).
- Emergent benefit worth naming (Architect suggestion): a worker whose
  pass raised is left `stopped` by `IndexingManager._run`'s `except
  Exception`; the tick's `request_index` → `start()` → `task.done()` path
  restarts it, so an indexing failure is retried once per interval without
  operator action, where before this flight it waited for a route call.
- Cost: the tick is a walk per folder (stat-only, 24 ms per 2k files) and
  nothing else when nothing changed; the folder item cycles `indexed →
  pending → indexing → indexed` on each pass, so `folders[].indexed_at`
  advances every interval — the behavior test's observable for "a walk
  happened" — and `indexer` reads `running` for the duration of each
  pass, which the behavior spec accounts for.
- Bounds: `reconcile_interval_seconds` is validated `10 ≤ n ≤ 86_400`
  (`Field(ge=10, le=86400)`). The floor is a Flight Director proposal
  recorded as such: it exists for the behavior test and a curious operator,
  not for production; the default is 300.
- Rejected: a per-folder timer inside each watch task (a folder that is
  `unavailable` or a watcher that is off would then have no walk at all);
  a due-based daily loop like purge (the interval here is minutes and
  operator-set).

**DD-5 — `MonitoringSettings` is a third `app_metadata` record, `knowledge.monitoring`, on the existing knowledge-settings routes; a `PUT` applies live through an awaited async hook**
- `the_one/knowledge/settings.py`: `MonitoringSettings(watch_enabled: bool
  = True, reconcile_interval_seconds: int = Field(300, ge=10, le=86400))`,
  `extra="forbid"` (squawk 0056's rule); `MONITORING_KEY =
  "knowledge.monitoring"`; `KnowledgeSettings` gains `monitoring:
  MonitoringSettings = Field(default_factory=MonitoringSettings)`;
  `load_knowledge_settings` reads the third record with the same
  invalid-value-falls-back-with-a-warning rule, `save_knowledge_settings`
  writes three independent records. Every existing constructor call
  (`KnowledgeSettings(chunking=…)` in tests) keeps working through the
  default factory; `tests/test_knowledge_settings.py::test_save_writes_both_
  keys` becomes three keys. This is a shared-interface change with existing
  consumers (`api.py`, `manager.py::_resources`, and three test modules:
  `test_db_api.py`, `test_kb_manager.py`, `test_knowledge_settings.py` —
  grepped at planning and confirmed at design review); the leg is tiered
  high.
- `GET /api/knowledge-settings` returns `"monitoring": {…}` beside the
  existing keys; `PUT` widens its allowed top-level set to `{"embedding",
  "chunking", "monitoring"}` with the same non-dict guard and
  merge-then-revalidate shape (the `update_knowledge_base` precedent; 422
  on an unknown nested key via `extra="forbid"`, on `reconcile_interval_
  seconds` out of bounds, on a non-boolean `watch_enabled`).
- **Live application** — the operator chose settings over env vars
  precisely so the switch is a switch: after `save_knowledge_settings` the
  route **awaits** `_after_monitoring_settings_changed(updated.monitoring)`,
  an **`async def`** `leg-staged-hook-seam` landed as a documented no-op
  by Leg 1 and filled by Leg 3 with `await get_watch_manager()
  .apply_settings(...)` (`None` → no-op, the `_after_folder_registered`
  shape, but asynchronous because stopping subscriptions is awaited).
  Awaiting it is what makes the behavior spec's "within 5 s the folder
  reads `off`" deterministic. `apply_settings` is idempotent:
  `watch_enabled` false → every entry stopped and removed and every armed
  timer cancelled (folders read `off`); true → `start_all()` re-subscribes
  every folder of every knowledge base; any call wakes the reconcile loop
  so a new interval takes effect immediately. Unlike chunking (future
  indexing only, Flight 2 DD-7), a monitoring change is immediate —
  recorded in the route docstring and `agents.md`.
- Rejected: env vars read at call time (the purge-loop precedent) — the
  operator's call; a per-KB switch — the embedding backend is app-global
  and so is this, and Flight 6 gets one toggle to render.

**DD-6 — Registration refuses a folder that equals, contains, or lies inside the data directory (422), checked after the root check and before containment; the filter (DD-2) is the second line**
- `create_kb_item` (`api.py`, the Flight 3 DD-1 branch) gains, between the
  filesystem-root check and the `list_folders` containment scan: `if
  is_within(settings.data_dir, canonical) or is_within(canonical,
  settings.data_dir): 422`, detail `"folder overlaps the application data
  directory (<data_dir>); the app's own database and index live there —
  register a folder that does not contain it"`. The hint matters because
  the default data directory is `platformdirs.user_data_dir` under the
  user profile, so registering the home directory — a plausible operator
  action — is refused by this rule from now on. Both directions: a folder
  above the data directory would loop on every indexing write (DD-2), and
  a folder inside it (the vector sidecar directory, say) would index the
  app's own files. The order keeps Flight 3's rule that a non-existent
  path is 422 before anything else and that 409 is reserved for another
  registered folder. `the_one/platform/paths.py::is_within` canonicalises
  both sides (`resolve(strict=False)`, so a data directory that does not
  exist yet is handled), and a symlinked or relative setting cannot slip
  past it. Existing tests are unaffected: `tests/conftest.py` pins
  `THE_ONE_DATA_DIR` to its own `mkdtemp` directory, disjoint from every
  test's `tmp_path` in both directions, and the API client fixture does
  not re-point it (checked at planning, confirmed at design review). New
  tests cover equal, above, inside, and the check order (a missing path
  inside the data directory is still 422 for non-existence, with the
  non-existence message).
- The behavior test's fixture is outside both `<scratch>` and the
  repository, as Flight 3's already was; a step registers `<scratch>` and
  its parent to prove the refusal.
- **Interaction with the Flight 3 spec** (Architect, cycle 2): `tests/
  behavior/kb-folder-index-round-trip.md` Step 6 registers the *parent*
  of its fixture and expects 409; its 2026-09-15 run used `/tmp` as that
  parent, and `<scratch>` lived under `/tmp` too, so under this rule that
  row would now read 422 (data directory) before the containment scan
  ever ran. Leg 1 amends that spec's Preconditions (authoring, not
  drift): the fixture nests one level, e.g. `/tmp/kb-round-trip/fixture`,
  so its parent is `/tmp/kb-round-trip`, which contains neither
  `<scratch>` nor the repository, and Step 6's 409 stands. Operator's call (2026-09-16):
  amend only — Leg 4 does not re-run the Flight 3 spec; the new spec
  exercises the same registration route.

**DD-7 — Lifespan: the `WatchManager` is constructed after the `IndexingManager`'s `start_all`, drained before the `IndexingManager`; drain budget 5 s, so the knowledge-base shutdown stays at 45 s under the launcher's 60 s join**
- Startup (`app.py`, after the `_indexing_manager.start_all()` block):
  `global _watch_manager = WatchManager(index_manager=_indexing_manager)`,
  published via the accessor **before** its own guarded `start_all()` (the
  Flight 3 Leg 3 shape — the drain reads the local global, routes reach the
  accessor). `start_all()`: read `MonitoringSettings`; start the reconcile
  loop task; if `watch_enabled`, for every knowledge base and every
  `folder` item, `start(kb_id, folder)`. Its own `try/except` so a failure
  cannot kill startup. An operator with no folders pays one sleeping task.
- Shutdown: `await _watch_manager.drain()` immediately **before**
  `_indexing_manager.drain()`: cancel every armed trigger timer, cancel the
  reconcile loop, set every entry's `threading.Event` and `asyncio.wait_for(
  gather(*tasks), WATCH_DRAIN_TIMEOUT = 5 s)` (a Flight Director proposal,
  recorded as such), cancelling on timeout. The Rust side returns within
  one 50 ms step of the stop event; the timeout is for a filesystem that
  has hung, and the threads are daemon threads, so they cannot hold the
  process. Draining the watcher first means no `request_index` can land on
  the indexing manager while it is stopping workers. Budget: 5 s + Flight
  3's 20 s + 20 s = 45 s for the knowledge-base path; the same 60 s
  `interfaces/desktop/shell.py::_graceful_shutdown` join also covers the
  PTY, MCP, OAuth and connector drains, so the margin is thinner than
  "45 < 60" reads — the watcher's 5 s is deliberately small for that
  reason.
- `tests/test_mcp_pool.py::test_lifespan_shutdown_drain_order` gains a
  `_FakeWatchManager` (constructor takes `index_manager=`) recording
  `watch_start` / `watch_drain`; both the `drain_steps` filter tuple and
  the pinned list widen to `connector_start, indexing_start, watch_start,
  watch_drain, indexing_drain, pty, evict, mcp, oauth, connector_drain,
  db`.

**DD-8 — Routes: `/status` reports each folder's watch state; the Flight 3 hooks start and stop watches under suppression; nothing else changes shape**
- `GET /api/knowledge-bases/{kb_id}/status`: each `folders[]` entry gains
  `"watch": "starting" | "watching" | "unavailable" | "off"` and
  `"watch_error": str | null` (`off` / `null` when no manager is
  installed). Additive only: the Flight 3 behavior spec asserts named keys
  and the DD-8 contract there is untouched. This is the new behavior
  test's primary observable (DD-10).
- `create_kb_item` (folder): `_after_folder_registered(kb_id, item)` —
  the hook's signature widens to carry the item — kicks the index as
  today and then `get_watch_manager().start(kb_id, item)` (a `None`
  manager, or one whose settings say off, is a no-op; the manager reads
  its own enabled flag). The two Flight 3 hook tests
  (`tests/test_db_api.py::test_after_folder_registered_called_once_with_
  kb_id`, `…_not_called_for_file_item`) monkeypatch the hook with a
  single-argument recorder and update for the new argument;
  `test_after_folder_registered_calls_request_index` patches the manager
  and needs no change. "Additive" describes the API contract, not the
  tests: `TestKnowledgeBaseStatusRoute::test_reports_folder_projection_
  and_manager_state` asserts the `folders[]` entry by exact dict equality
  and updates for the two new keys (Architect, cycle 2 — the sweep-
  siblings lesson).
  `delete_kb_item` (folder): `async with watch.suppress(kb_id):` around
  `watch.stop(item_id)` → the existing `manager.stop(kb_id)` → repository
  delete → store delete → `manager.request_index(kb_id)`.
  `delete_knowledge_base`: `async with watch.suppress(kb_id):` around
  `watch.stop_kb(kb_id)` → `manager.stop(kb_id)` → repository delete →
  `store.delete_kb`. AC: a reconcile tick and a sibling folder's timer
  fired inside the suppression window produce no `request_index` (unit
  test against a fake index manager).
- `POST …/reindex` is unchanged: it is the operator's manual trigger and
  the watcher never needs it.

**DD-9 — A ninth `doctor` gate, `file watcher`: the import gates unconditionally, the native round-trip gates only when frozen (operator's choice, 2026-09-16); the frozen Windows run's needle list gains it**
- `diagnostics.py::_probe_file_watcher`: (1) `import watchfiles` and
  reference `watchfiles.watch` — a failure here is `ok=False` on **every**
  host, since from this flight the app imports the module at startup
  everywhere and a missing or unloadable `_rust_notify` extension is a
  defect wherever it happens; (2) create a temporary directory, open a
  real `watchfiles.watch(tmp, rust_timeout=1000, yield_on_timeout=True,
  <DD-0 kwargs, force_polling=False>)`, **write a fresh file after each timeout yield, in the loop that
  consumes them** (not once from a helper thread at +100 ms — the generator body, and so the notifier, does
  not exist until the first `next()`, and a single early write would be
  lost; Architect, cycle 2), and **iterate yields until a non-empty set
  arrives or an overall deadline passes** — 10 s when frozen, 2 s when
  not (the house rule "always attempt, downgrade only the failure" is
  kept, but this is the first probe whose attempt costs wall-clock) —
  then close the generator explicitly. Never "the first yield must be
  non-empty", which on a loaded frozen CI runner would fail the
  installer build for a scheduling hiccup (Architect, cycle 1; `watch`'s
  default `debounce` alone puts the first real yield up to 1.6 s after
  the write, so the probe pins a 200 ms `debounce` and `rust_timeout=
  250`). `tests/test_doctor.py` invokes the full `run_doctor` about
  twenty times; those tests monkeypatch `_probe_file_watcher` to a canned
  result exactly as they already do for the embedding-model probe (the
  file's own header explains why), and the probe's targeted tests live
  in the same file by the `_probe_usearch` precedent — they call the
  module-top-imported symbol directly, which `monkeypatch.setattr(
  diagnostics, …)` does not rebind, while `run_doctor` resolves the
  module global and gets the stub. The two deadlines are module
  constants. The probe's temporary directory honours `TMPDIR`; on a WSL
  host with `TMPDIR` under `/mnt/c` the round-trip legitimately reads
  `skipped`. A round-trip failure reports through
  `_vector_probe_outcome`, whose signature is already name-agnostic
  (`(name, reason)`); its docstring and the `agents.md` paragraph that
  calls it the vector probe's helper widen to "frozen-only gating". Detail
  strings: `"native change notification round-trip OK"` / `"import OK;
  round-trip: <reason>"`. Appended to `gates` after `embedding model`. Every
  gate-count site is swept, not only the table: `run_doctor`'s own
  docstring (the gate-name enumeration, "Of those **eight**, four are
  frozen-only", and "The other four … gate unconditionally" — five now,
  with this one a hybrid), `agents.md`'s "The eight gates" table (nine;
  frozen-only column: "import no, round-trip yes"), its "Six of the
  eight wrap their body", "separate from the eight gates" and the
  identical unconditional-gate sentence with the frozen-only list at
  `agents.md:1353`; `README.md`'s `doctor` line and
  `docs/windows-install.md` name it; `ci/tasks/windows-installer-build.yml`
  and the break-glass `.github/workflows/windows-installer.yml` add
  `"file watcher: OK"` to the by-name needles. `tests/test_doctor.py`
  gains the probe's host-side tests (pass path with a real temp dir;
  import-failure path by monkeypatching the import to raise → `ok=False`
  unfrozen; round-trip-failure path by monkeypatching `watchfiles.watch`
  to raise → `skipped` unfrozen, `ok=False` frozen).
- Why a gate at all: the Rust extension is reached in the app today only
  through `uvicorn`'s reload supervisor, which `the-one serve` never uses,
  so no frozen build to date has proven it loads. `pyproject.toml`
  declares `watchfiles>=1.0` directly (today it is only a transitive extra
  of `uvicorn[standard]`, which is not a contract) — the lock already pins
  1.1.1 with Windows and macOS wheels, so the closure does not change
  (DD-11).

**DD-10 — Behavior test `kb-folder-watch-round-trip`: shell + http + filesystem apparatus on 8485 with a scratch data directory; it proves the event path with no API call, the periodic path with the watcher off, the data-directory refusal, restart re-subscription, and root removal and return**
- Act path: `curl` with the long-lived credential against `POST
  /api/knowledge-bases`, `POST …/items` (folder), `PUT
  /api/knowledge-settings` (`monitoring`), `make down` / `make up`; the
  filesystem apparatus creates, edits, deletes files and removes and
  recreates the fixture root. Read path: `GET …/status` (`folders[].watch`,
  `folders[].watch_error`, `folders[].status`, `folders[].indexed_at`,
  `items` counts, `indexer`), `GET …/items`, `GET …/items/{id}/chunks`,
  `GET /api/knowledge-settings`. **Both axes audited at planning**: every
  action is an operator-callable route or a filesystem operation, and every
  assertion is a field in one of those bodies — the watch state is added to
  `/status` (DD-8) so the test never reads the database or the log. No
  `[mixed-frame]` row.
- Timing (revised at design review): the event-path wait is 30 s (5 s
  settle + a walk + a short index); the periodic-path wait is 30 s at the
  10 s floor; the cold-restart wait is 60 s (lifespan startup, the ~250 MiB
  embedding-model load in the first pass, the store open, the walk — the
  same budget Step 2 has for less work); the root-return wait is 40 s (one
  tick to re-subscribe, one walk). At a 10 s interval `indexer` reads
  `running` during every tick's pass and the folder's own `status`
  cycles through `pending`/`indexing` for milliseconds, so the spec
  asserts `idle` **or** `running` wherever the interval is 10 s, allows
  one re-poll when a folder reads `pending` or `indexing`, and relies on
  the item counts, which are stable once indexed. Step 3 is the clean
  proof of the event path: at that point the interval is still the 300 s
  default, so nothing but the watcher can have caused the walk it
  observes — the single most valuable property of the spec. Every wait point polls `/status` every
  2 s.
- Premise verified at planning with the pinned native backend (flight log
  P13–P16): events are delivered on an ext4 `/tmp` path; a `/mnt/c` drvfs
  path delivers **nothing** natively (the polling backend the first probe
  had unknowingly used delivered there, which is why the flight log's P6
  row is corrected rather than deleted). The fixture must live on a native
  filesystem — `/tmp` on this host — and the spec's Preconditions say so.
- Spec drafted at planning (`tests/behavior/kb-folder-watch-round-trip.md`,
  status `draft`); premise-audited by the Leg 4 Developer before its first
  run.

**DD-11 — No closure change; `pip-audit` on the unchanged export; one frozen run at flight close with the new needle, budgeted as a diagnostic**
- `watchfiles` 1.1.1 and `anyio` are already in `uv.lock` (via
  `uvicorn[standard]` and `starlette`); declaring `watchfiles` directly
  changes no resolved version. PyInstaller already collects the extension
  through `uvicorn.supervisors`' module-level `try` import, and
  `_rust_notify` is an ordinary importable extension of the same class
  `packaging/windows/the-one.spec:151-170` documents as needing no entry
  (`tokenizers`, `safetensors`, `usearch.compiled`); the gate (DD-9) is
  what proves it. If the frozen run fails on `file watcher`, the fix is a
  `hiddenimports` entry for `watchfiles._rust_notify` — iterated as a
  diagnostic inside the flight (the Flight 2/3 rule), not moved earlier.

**DD-12 — The Windows 1M `usearch` re-measure folds into Flight 6 / mission close (operator's call, 2026-09-16); `get_vector_store()`'s missing shutdown hook stays recorded**
- `mission.md`'s open question is amended in Leg 4: a synthetic 1M-chunk
  corpus generated at mission close, measured on the Windows worker, with
  Flight 3's flush constants re-checked against the number; the Flight 6
  bullet carries it. This flight adds nothing to that measurement.
- The Flight 3 debrief's note that a knowledge base with a store but no
  worker has no flush path at shutdown is unchanged by this flight (the
  watcher never touches the store) and stays a recorded design question
  for whoever next touches the dispatcher.

### Prerequisites

- [x] Flight 3 `completed` and merged to `mission/24-knowledge-bases` (PR #200, `e030437`); squawks 0063–0066 merged (PR #201, `a657873`); `git status` clean at planning
- [x] `mission/24-knowledge-bases` is 36 commits ahead of `main` and 0 behind — no merge from `main` needed at this boundary (mission Branch Layout)
- [x] `watchfiles` 1.1.1 importable from `.venv`; `uv.lock` pins it with cp311 wheels for Windows, macOS (x86_64, arm64) and Linux; `anyio` present
- [x] Host inotify limits: `max_user_watches` 1,048,576, `max_user_instances` 8,192 (this WSL2 host, kernel 6.18) — ample for planning probes and the behavior test
- [x] `watchfiles` behaviour probed on this host with the native backend pinned (flight log, "Planning premise probes", P13–P16, superseding the polling-backend rows P2/P4/P6): recursive delivery into new subdirectories, one `deleted <root>` on removal or rename then silence, permission-denied subdirectory survivable, root-plus-relative path shape, no native delivery on `/mnt/c`
- [x] Port 8485 free and nothing listening on 8484 at planning; `sqlite3` on PATH is **not** needed by this flight's spec (no seeded step)
- [x] `fly -t the-one status` logged in and `windows-worker` running at planning
- [ ] Leg 3 re-verifies the dev-instance and Concourse prerequisites on the day

### Pre-Flight Checklist
- [x] All open questions resolved
- [x] Design decisions documented
- [x] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

Four legs. **Leg 1** lays the foundations that need no running watcher:
the `MonitoringSettings` record and its routes with the live-apply async
hook as a no-op (DD-5), the data-directory refusal (DD-6), `is_hidden_name`
and `is_watch_candidate` in `walk.py` (DD-2), the direct `watchfiles`
dependency, and the `file watcher` doctor gate with its CI needles and gate
docs (DD-0, DD-9). **Leg 2** is the watcher module alone: `WatchManager`
with its dedicated-thread subscriptions, filter application, settle
trigger, suppression, reconcile loop and `apply_settings` (DD-0, DD-1,
DD-3, DD-4), fully unit-tested through the watch-factory seam plus one
real-`watch` integration test — no app wiring. **Leg 3** wires it: lifespan
start/drain and the drain-order test (DD-7), the route hooks with
suppression and the `/status` fields (DD-8), the settings hook filled
(DD-5), and the `CLAUDE.md` / `agents.md` / `SECURITY-MODEL.md` updates.
**Leg 4** verifies against the real environment: premise audit and run of
`kb-folder-watch-round-trip`, `make lint`, `make test-unit` verbatim, the
release-closure `pip-audit`, one frozen Windows run with the ninth needle,
and the mission artifact updates (DD-12). Legs 1–3 tier high (a shared
interface with consumers and a security-sensitive path check; a lifecycle;
lifespan wiring) and get a per-leg design review, with a Sonnet Reviewer
on the path-handling surface; the flight-end Reviewer covers all code.

### Checkpoints
- [ ] Leg 1 landed: settings round-trip with three records, `PUT` refusals, data-dir 422 in all three shapes, predicate tests including a dotted root and an out-of-root path, `doctor` prints nine gates locally with `file watcher` OK-or-skipped-round-trip, `watchfiles` declared in `pyproject.toml` with `uv.lock` unchanged, both CI needle files carry `file watcher: OK`, the Flight 3 spec's Preconditions amended with the nested fixture and the explicit constraint that `<parent of fixture>` contains neither `<scratch>` nor the repository
- [ ] Leg 2 landed: N synthetic events inside one window → exactly one `request_index`; `{(modified, root)}` survives; a run of empty yields → zero `request_index`; `{(deleted, root)}` → one trigger then `unavailable`; factory raising `FileNotFoundError` / `OSError(ENOSPC)` / `RuntimeError` at construction, and one raising after a first yield → `unavailable` and retry on tick; the real `watch` against a missing root → `unavailable`, never `watching`; a root the process cannot read → `unavailable`, never `watching`; a successful (re)subscribe fires one `request_index`; every `stop` returns without waiting for the timeout (sentinel); `stop`/`drain` on a cap-created entry with no task return without error; the 65th folder → `unavailable` (cap); `suppress` silences the timer and the tick; `apply_settings` on/off/interval; `drain` under budget; the real-`watch` integration test on `tmp_path`
- [ ] Leg 3 landed: drain order pinned; `/status` carries the watch fields; delete routes hold suppression; hook tests updated; docs
- [ ] Leg 4: behavior test passes every step; gates recorded; frozen run `RESULT: PASS` with `file watcher: OK`

### Adaptation Criteria

**Divert if**:
- The pinned `force_polling=False` cannot be used on the operator's platform (the frozen Windows build's gate fails on the round-trip with the extension present) — the event path's semantics (root removal, `modified <root>`) were derived for native notification and must be re-derived before Leg 2 proceeds.
- The frozen build cannot load `watchfiles`' extension even with a `hiddenimports` entry.
- A subscription thread cannot be stopped within the 5 s drain budget on this host in a way the daemon-thread fallback does not cover.
- `is_hidden_name` cannot replace the inline check without changing `walk_folder`'s observable behaviour (`tests/test_kb_walk.py` must stay green untouched).
- On Windows, `watchfiles` reports the root's own deletion under a path that `os.path.normcase` cannot reconcile with the subscribed root (a premise unverified at planning — only Linux was probed): root removal would then be invisible and DD-1's degrade path needs a Windows-specific rule before Leg 2 lands there.

**Acceptable variations**:
- `debounce`/`step`/`rust_timeout` values inside the subscription if the settle proves jittery, as long as DD-3's numbers hold from the operator's point of view and DD-0's rule (every knob explicit) is kept.
- The `unavailable` reason strings; the exact `watch_error` wording; the exact 422 detail wording in DD-6.
- The reconcile loop's tick doing its listing under `asyncio.to_thread` if it turns out to matter (it should not).
- Additional `/status` fields Flight 6 asks for, provided the Flight 3 and Flight 4 behavior specs' named keys are untouched.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [ ] `settings-guard-and-gate` - `MonitoringSettings` record + routes + async no-op live-apply hook (DD-5); data-directory refusal (DD-6); `is_hidden_name` / `is_watch_candidate` in `walk.py` (DD-2); `watchfiles` declared; `file watcher` doctor gate with pinned knobs, CI needles, gate docs (DD-0, DD-9); the Flight 3 behavior spec's Preconditions amended for the nested fixture (DD-6). Tests for all of it. *(high-risk: shared settings interface with consumers; security-sensitive path check → Sonnet Reviewer)*
- [ ] `watch-manager` - `the_one/knowledge/watcher.py` complete: dedicated-thread subscriptions with pinned knobs, filter application, root-removed and error-record handling, the cap, settle trigger with clamp and suppression, reconcile loop with re-subscribe, `apply_settings`, `start_all` / `drain`, accessor pair; `tests/test_kb_watcher.py` through the factory seam plus one real-`watch` test. No app wiring. *(high-risk: lifecycle)*
- [ ] `wiring-routes-and-docs` - lifespan start/drain + drain-order test (DD-7); route hooks under suppression, `/status` fields, hook tests (DD-8); settings hook filled (DD-5); docs (`CLAUDE.md`, `agents.md` Knowledge indexing + the convention's third citation + the nine gates + the WSL note, `SECURITY-MODEL.md`). *(high-risk: lifespan wiring)*
- [ ] `verify-integration` - premise audit + `/mission-control:behavior-test kb-folder-watch-round-trip` on 8485; `make lint`; `make test-unit`; `pip-audit`; frozen `fly execute` with the new needle; `mission.md` open-question amendment (DD-12) and Flight 6 bullet. *(no HAT leg — no screen; the walk folds into Flight 6's HAT)*

---

## Post-Flight

### Completion Checklist
- [ ] All legs completed
- [ ] Code merged (PR into `mission/24-knowledge-bases`)
- [ ] Tests passing (`make lint`, `make test-unit` verbatim, `pip-audit`, frozen run — by hand, recorded in the flight log)
- [ ] Documentation updated (`CLAUDE.md` Knowledge bases paragraph; `the_one/agents.md` Knowledge indexing, the nine gates, the convention citation; `SECURITY-MODEL.md`'s Knowledge-base indexing bullet gains: the data-directory refusal, and that operating-system watches are registered on operator-chosen trees and read with the app's own privileges, the same trust boundary as the walk; `README.md` doctor line; `docs/windows-install.md`)

### Verification

- `/mission-control:behavior-test kb-folder-watch-round-trip` passes every step on a dedicated dev instance (8485, scratch data directory, fixture on a native filesystem): a file change is reflected with no API call within 30 s; with the watcher off and the interval at 10 s a change is reflected within 30 s; registering the data directory or its parent is 422; after a restart the folder reads `watching` again within 60 s; removing the fixture root leaves the items intact, the folder `failed` and the watch `unavailable`; recreating it brings both back within 40 s.
- Unit: `tests/test_kb_watcher.py` (synthetic change sets through the watch factory with small real settle/hold values, no fake clock: filter application, one `request_index` per window and a second past the hold cap, `{(modified, root)}` survives, empty yields never trigger, `{(deleted, root)}` → one trigger then `unavailable`, factory errors at construction and mid-iteration → `unavailable` and retry on tick, a real `watch` on a missing root → `unavailable`, the cap, `suppress`, `apply_settings` on/off/interval, `stop`/`stop_kb`/`drain` under budget, one real-`watch` integration test on `tmp_path`), `tests/test_kb_walk.py` (predicates, counters untouched), `tests/test_knowledge_settings.py` (third record), `tests/test_db_api.py` (routes, hooks under suppression, `/status` fields, DD-6), `tests/test_doctor.py` (gate: import unconditional, round-trip frozen-only), `tests/test_mcp_pool.py` (drain order).
- Frozen: `^RESULT: PASS`, nine gates `OK`, `file watcher: OK` present, installer size recorded against 134,886,157 bytes (Flight 3 close, build 608700).
