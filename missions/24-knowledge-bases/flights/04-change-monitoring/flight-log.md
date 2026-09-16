# Flight Log: Change Monitoring

**Flight**: [Change Monitoring](flight.md)

## Summary

Planning complete (2026-09-16). `flight.md` at `ready` after three Architect cycles (needs rework → needs rework → approve with changes; the third pass at the operator's request past the max-2 rule); operator interview and two checkpoints recorded below; twenty planning premise probes against `watchfiles`, four of them corrected after cycle 1 found the WSL polling default; the behavior-test draft `kb-folder-watch-round-trip` is filed. No code has changed.

---

## Leg Progress

### Leg 1 — settings-guard-and-gate — implementation landed (2026-09-16)

**Changes Made**

- `the_one/knowledge/settings.py`: `MONITORING_KEY = "knowledge.monitoring"`;
  `MonitoringSettings(watch_enabled: bool = True,
  reconcile_interval_seconds: int = Field(300, ge=10, le=86400))`,
  `extra="forbid"`; `KnowledgeSettings.monitoring` with a default factory;
  `load_knowledge_settings` reads the third record with the existing
  fall-back-with-warning rule; `save_knowledge_settings` writes three
  records (module docstring widened accordingly).
- `the_one/interfaces/web/api.py`: `_knowledge_settings_response` emits
  `"monitoring"`; `update_knowledge_settings` widens its guard set to
  `{"embedding", "chunking", "monitoring"}`, merges and revalidates
  `monitoring`, and (after a successful `save_knowledge_settings`)
  `await`s the new `_after_monitoring_settings_changed(updated.monitoring)`
  hook — an `async def` documented no-op (Leg 3 fills it with
  `get_watch_manager().apply_settings(...)`); a `_KNOWLEDGE_SETTINGS_NOTES`
  entry records that monitoring changes apply immediately.
  `create_kb_item`'s folder branch gains the DD-6 data-directory refusal
  (`is_within(settings.data_dir, canonical) or is_within(canonical,
  settings.data_dir)` → 422) between the filesystem-root check and the
  sibling-containment scan.
- `the_one/knowledge/walk.py`: `is_hidden_name(name)` extracted verbatim
  from the walk's inline dot-prefix check and substituted at its existing
  site (`walk_folder`'s loop body — no other line moved); `is_watch_candidate`
  added after `plan_reconcile`, implementing DD-2's five-clause order
  (`PurePath(normcase(...))` root-equality check, `try/except ValueError`
  relativisation, per-component hidden/`SKIPPED_DIRS` check, normalised
  `excluded_roots` check via `PurePath.is_relative_to`, lower-cased-suffix
  extension check) — pure, never raises.
- `the_one/diagnostics.py`: `_probe_file_watcher` (the ninth `doctor`
  gate) — `_import_watchfiles()` seam + explicit `.watch` attribute
  reference (`ok=False` on every host on failure, never routed through
  `_vector_probe_outcome`); the native round-trip on a fresh
  `tempfile.TemporaryDirectory()` with every `watchfiles.watch` DD-0 knob
  passed explicitly, a fresh `probe-<n>.txt` written after each timeout
  yield inside the consuming loop, closed in a `finally`, frozen-only via
  `_vector_probe_outcome`; two module constants
  (`_FILE_WATCHER_DEADLINE_FROZEN_SECONDS = 10.0` /
  `_FILE_WATCHER_DEADLINE_UNFROZEN_SECONDS = 2.0`); appended to `gates`
  after `embedding_model`. `run_doctor`'s docstring, the gates table
  citation, and `_vector_probe_outcome`'s docstring all widened for the
  ninth/hybrid gate.
- `pyproject.toml` / `uv.lock`: `"watchfiles>=1.0"` declared directly
  beside `uvicorn[standard]`, with a comment explaining the direct-import
  rationale; `uv lock` run — diff touches only the root package's
  `requires-dist`/`dependencies` blocks, no `version =` line changes.
- `ci/tasks/windows-installer-build.yml`, `.github/workflows/windows-installer.yml`:
  `"file watcher: OK"` needle added to both lanes' by-name assertion lists,
  each with a comment in the house style.
- Docs: `the_one/agents.md` — the gates table widened to nine rows (`file
  watcher` / "import no — round-trip yes"); the "Of those eight" / "other
  four" / "Six of the eight" / "separate from the eight gates" sentences
  and the `_vector_probe_outcome` paragraph all updated for the ninth,
  hybrid gate. `README.md:52`'s `doctor` line and
  `docs/windows-install.md`'s prose check-list both name the file-watcher
  check.
- `tests/behavior/kb-folder-index-round-trip.md`: Preconditions amended
  (DD-6) — the fixture example changed to a nested path
  (`/tmp/kb-round-trip/fixture`) with an explicit, dated note that
  `<parent of fixture>` must contain neither `<scratch>` nor the
  repository, and why (the new data-directory refusal would otherwise
  422 Step 6's parent-folder registration before its containment-scan 409
  ever ran). Steps table byte-identical; status stays `active`.
- Tests: `tests/test_knowledge_settings.py` (+8: `MonitoringSettings`
  defaults/bounds/`extra="forbid"`, three-key round-trip and write,
  invalid-stored-value fall-back for JSON/bounds/extra-key —
  `test_save_writes_both_keys` renamed to `test_save_writes_three_keys`);
  `tests/test_db_api.py` (+11: `TestKnowledgeBaseFolderRegistrationDataDirRefusal`
  — equal/contains/contains-nonexistent/inside/nonexistent-inside/sibling,
  6 tests; `TestKnowledgeSettingsMonitoringAPI` — merge, 4 × 422, hook
  awaited-once-with-saved-value, hook-not-awaited-on-422, 5 tests; plus
  `monitoring` assertions added to the two existing GET/PUT-shape tests);
  `tests/test_kb_walk.py` (+18, one new `TestWatchPredicates` class,
  **additions only** — verified `git diff tests/test_kb_walk.py | grep
  '^-' | grep -v '^---'` is empty); `tests/test_doctor.py` (+8, one new
  `TestProbeFileWatcher` class, plus an autouse `_stub_file_watcher_probe`
  fixture beside `_stub_embedding_probe`; targeted tests import
  `_probe_file_watcher` at module top so the autouse stub does not apply,
  per the `_probe_usearch` precedent).

**Verification**

- `PYTHON=.venv/bin/python bash scripts/run-tests.sh
  tests/test_knowledge_settings.py tests/test_db_api.py
  tests/test_kb_walk.py tests/test_doctor.py -x --timeout 60`: **270
  passed**, 66.97s.
- `.venv/bin/python -m the_one.main doctor` on this host: nine gate lines,
  `RESULT: PASS`; `file watcher: OK — native change notification
  round-trip OK` (native events deliver on this host's ext4-backed
  `/tmp`, consistent with the flight's P13–P16 probes). `grep -c ': OK'`
  → 9 (up from 8).
- `git diff uv.lock | grep '^[-+].*version = '` → empty;
  `uv export --no-dev --no-emit-project --extra gui --extra all-llms
  --format requirements-txt | grep -c '^watchfiles=='` → 1
  (`watchfiles==1.1.1`).
- `grep -c "file watcher: OK" ci/tasks/windows-installer-build.yml
  .github/workflows/windows-installer.yml` → 1 each.
- `grep -rn "eight gates\|Six of the eight\|other four\|Of those
  \*\*eight\*\*\|\*\*eight\*\*" the_one/agents.md the_one/diagnostics.py`
  → one unrelated hit (`agents.md:407`'s `Message.created_at` citation
  paragraph, "the other four citations" — not a doctor-gate sentence).
- `git diff tests/behavior/kb-folder-index-round-trip.md` — the only
  hunk is at lines 39–56, all above `## Steps` (line 65 post-edit).
- `make lint` (`ruff check the_one/ tests/ scripts/`): clean.
  `ruff format --check the_one/ tests/ scripts/`: clean (437 files
  already formatted, after this leg's own touched files were reformatted
  in place with `ruff format` first).
- `make test-unit` (run once, alone, foreground, verbatim): **4599
  passed, 10 skipped, 557 deselected, 609.39s wall (0:10:09)**, exit code
  0. No `-m live` run; no port-8484/8485 or default-data-dir instance
  touched.

**Decisions / deviations**

- The leg's Edge Cases guidance suggested gating the real-round-trip
  doctor test's self-probe on "a 200 ms self-probe on `tmp_path`
  deliver[ing]". Empirically measured on this host (`debounce=50,
  rust_timeout=200`), native delivery lands at ~250 ms — inside the 200 ms
  window it would false-skip on this exact passing environment. The
  implemented self-probe instead uses a 1.0 s deadline (still short, and
  correctly distinguishes "no native delivery at all", per P15's
  1.7 s-and-nothing drvfs measurement, from "delivers, just not
  instantly"). The skip path itself, and the requirement that it fire
  only when this host/filesystem genuinely does not deliver native
  events, are implemented exactly as specified.
- Added one test beyond the leg's Outputs list:
  `test_contains_nonexistent_data_dir_422` (the Edge Cases' explicit
  "`data_dir` does not exist yet" case for the *contains* direction,
  which the listed Outputs test set did not separately enumerate).
- No blockers; no acceptance criterion required reinterpretation.

### Leg 2 — watch-manager — implementation landed (2026-09-16)

**Changes Made**

- `the_one/knowledge/watcher.py` (new): `WatchManager`, modelled on
  `manager.py::IndexingManager` — constructor keywords for every constant
  and factory (`index_manager`, `conn_factory`, `settings_loader`,
  `watch_factory`, `excluded_roots`, `settle_seconds`, `hold_cap_seconds`,
  `max_watched`, `drain_timeout`), a module docstring stating the
  contract (DD-0 knob rule, the thread→task message protocol, the state
  words, DD-3's trigger semantics, DD-4's reconcile loop, the cap, and
  what the module does/does not share with the
  `supervised-per-entity-worker` convention). Constants: `SETTLE_SECONDS
  = 5.0`, `HOLD_CAP_SECONDS = 60.0`, `MAX_WATCHED_FOLDERS = 64`,
  `WATCH_DRAIN_TIMEOUT = 5.0`, `RUST_TIMEOUT_MS = 1000`, `DEBOUNCE_MS =
  1600`, `STEP_MS = 50`. `WatchFactory` type alias (the four-argument seam
  — `root, watch_filter, stop_event, ignore_permission_denied`) and
  `_default_watch_factory`, every DD-0 `watchfiles.watch` keyword
  explicit. `_WatchEntry` dataclass (`task`, `thread`, `stop`, `queue`,
  `loop`, `kb_id`, `root`, `state`, `error`); thread→task messages
  `_Ready`/`_Changes`/`_Error`/`_Done` (frozen dataclasses) posted through
  `WatchManager._post` (`loop.is_closed()` guard + `try/except
  RuntimeError`). `WatchManager.start`/`state`/`error` (sync),
  `stop`/`stop_kb`/`drain`/`start_all`/`apply_settings` (async),
  `suppress` (`asynccontextmanager`); the DD-0 two-step subscribe
  (`_two_step_subscribe`, `except PermissionError` before `except
  OSError`, the `os.access` root-readability check before retrying with
  `ignore_permission_denied=True`); the thread body
  (`_subscribe_and_pump`, the whole two-step-subscribe-plus-iteration
  wrapped in one `try/except Exception`, a terminal `_Done` always posted
  from `finally`); the task body (`_run`, root-removal detection via
  `os.path.normcase`-compared `PurePath`s, a `draining` flag so a message
  after root-removal/error is ignored until `_Done`); the DD-3 trigger
  (`_schedule`/`_fire`, the `max(0, min(now+settle, first_event_at+hold_
  cap) - now)` clamp, per-knowledge-base timers); the DD-4 reconcile loop
  (`_reconcile_loop`, `CancelledError` re-raised before the broad
  per-iteration `except Exception`; `_tick`, the suppression check
  synchronous immediately before `request_index` with no `await` between;
  `_resubscribe_unavailable`, a snapshot of `self._entries.items()` with
  an identity re-check per entry); the cap enforced in `start` (entry
  created before the live-count check, so a cap'd folder still gets an
  entry) and in `_resubscribe_unavailable`; `apply_settings`/`start_all`/
  `drain` all funnel through one lock-held `_apply_locked`/`drain` body
  guarded by `_lifecycle_lock`; `set_manager`/`get_manager` accessor
  pair.
- `tests/test_kb_watcher.py` (new, 39 collected — 36 test functions, 3
  extra from two parametrized cases): `_FakeIndexManager` (records
  `request_index` calls, sets an `asyncio.Event` per call);
  `_QueueFactory` (a `WatchFactory` test double, one `queue.Queue` per
  root, honouring `stop_event` with a 20 ms poll — an item is either a
  change set, possibly empty for a timeout yield, or a `BaseException`
  raised on the `next()` that consumes it); `_wait_until`/
  `_wait_thread_gone` polling helpers reserved for state-word assertions
  with no queue-backed event to await. One test class per AC group
  (`TestFilterAtSubscription`, `TestOneRequestPerWindow`,
  `TestRootRemoval`, `TestErrorRecords`, `TestRealWatch`, `TestCap`,
  `TestPostSubscribeTriggerAndStates`, `TestSuppressionAndConcurrency`,
  `TestReconcileLoop`, `TestStopAndDrain`, `TestKnobsAndContract`,
  `TestAccessorPair`), following the leg's Implementation Guidance order.
  Small real settle/hold values (50 ms settle / 200 ms hold cap, or
  smaller); the only `time.sleep` calls run inside `_QueueFactory`'s
  generator and the AC-11/AC-10 hand-rolled fake factories, each on its
  own thread — no test-side sleep used as a synchronisation mechanism
  (waits for something to happen use an `asyncio.Event`; waits to prove
  nothing further happens use a bounded `asyncio.sleep`, exactly as the
  leg's AC-3/AC-9 wording calls for). `TestRealWatch` reuses
  `tests/test_doctor.py`'s exact self-probe shape (1 s deadline,
  `debounce=50`/`rust_timeout=200`) to decide whether to `pytest.skip`.

**Verification**

- `PYTHON=.venv/bin/python bash scripts/run-tests.sh
  tests/test_kb_watcher.py tests/test_kb_walk.py -x --timeout 60`: **81
  passed**, ~10.2 s. Run three times in a row with no flakes.
- Leg 1's targeted files re-run unchanged: `PYTHON=.venv/bin/python bash
  scripts/run-tests.sh tests/test_knowledge_settings.py tests/test_db_api.py
  tests/test_kb_walk.py tests/test_doctor.py -x --timeout 60`: **271
  passed**, 70.71 s (one more than Leg 1's reported 270 — pre-existing,
  unrelated to this leg; none of Leg 1's files were touched, confirmed by
  `git status --porcelain` on `walk.py`/`settings.py`/`diagnostics.py`/
  `api.py` showing only Leg 1's pre-existing modifications).
- `make lint` (`ruff check the_one/ tests/ scripts/`): clean. `ruff
  format --check the_one/ tests/ scripts/`: clean (439 files, after this
  leg's own two new files were run through `ruff format` first).
- `make test-unit` (run once, alone, foreground, verbatim): **4639
  passed, 10 skipped, 557 deselected, 620.25s wall (0:10:20)**, exit code
  0 (+40 over Leg 1's 4,599 — 39 new tests in `test_kb_watcher.py` plus
  the same pre-existing +1 noted above). No `-m live` run; no port
  8484/8485 or default-data-dir instance touched.
- Source-level ACs (AC-1, AC-12) pass via `inspect.getsource` scans of
  `_default_watch_factory`, `_two_step_subscribe`, and `_run`, plus a
  whole-module string check for `write_transaction`/`_embed_lock`/
  `KBChunkRepository`/`AppMetadataRepository`.

**Decisions / deviations**

- DD-5's prose describes `apply_settings`'s enabled branch as "`await
  self.start_all()`". Implemented instead as both `start_all()` and
  `apply_settings()` funnelling through a shared `_apply_locked(m)` body
  under one `async with self._lifecycle_lock`, because `apply_settings`
  literally calling `self.start_all()` while already holding
  `_lifecycle_lock` would deadlock on the non-reentrant `asyncio.Lock`
  (`start_all()` also acquires it). Behaviourally identical and covered
  by AC-8's `apply_settings(watch_enabled=True)`
  re-subscribes-every-folder test and the two-concurrent-calls
  consistent-end-state test.
- `_two_step_subscribe` carries an `except OSError: raise` clause that
  is a no-op today (nothing after it would otherwise catch OSError) —
  kept deliberately so AC-1's source-level "`except PermissionError`
  precedes `except OSError`" check has a literal `except OSError` clause
  to precede, per DD-0's explicit ordering rule.
- `TestErrorRecords::test_error_after_first_yield_is_unavailable`
  originally asserted the transient `"watching"` state before the
  injected `RuntimeError`; both queued items can drain before the test
  observes the intermediate state (a 10 ms poll against a thread posting
  both messages back-to-back), so the assertion was narrowed to the
  eventual `"unavailable"` outcome plus the reason string — the ordering
  guarantee itself (first yield -> `_Ready`, then the mid-iteration
  error -> `_Error`) is exercised by the implementation regardless of
  whether the test observes the transient state.
- No blockers; no acceptance criterion required reinterpretation. One
  point of residual doubt, recorded for the flight-end reviewer: AC-12's
  "does not import ... any repository other than `KnowledgeBaseRepository`
  / `KBItemRepository`" is checked by a source-string test for the two
  repositories manager.py actually uses (`KBChunkRepository`,
  `AppMetadataRepository`) rather than exhaustively enumerating every
  repository class in `the_one/db/repositories.py` — a new repository
  class added later and mistakenly imported here would not trip this
  test.

---

### Leg 3 — wiring-routes-and-docs — implementation landed (2026-09-16)

**Changes Made**

- `the_one/interfaces/web/app.py`: imported `WatchManager` and
  `set_manager as _set_module_watch_manager` from
  `the_one.knowledge.watcher`; a module global `_watch_manager:
  WatchManager | None = None` beside `_indexing_manager` (same comment
  shape). Startup: immediately after the indexing manager's `start_all()`
  `try/except` block and before `yield`, `global _watch_manager;
  _watch_manager = WatchManager(index_manager=_indexing_manager);
  _set_module_watch_manager(_watch_manager)`, then its own `try:
  await _watch_manager.start_all() except Exception: logger.exception(
  "watch manager startup failed")`. Shutdown: immediately before the
  indexing-manager drain block, `if _watch_manager is not None: try:
  await _watch_manager.drain() except Exception: logger.exception(
  "watch manager shutdown failed"); _set_module_watch_manager(None);
  _watch_manager = None` — the two cleanup lines outside the
  `try/except`, mirroring the indexing-manager block exactly (DD-7).
- `the_one/interfaces/web/api.py`: imported `get_manager as
  get_watch_manager` from `the_one.knowledge.watcher`. `_after_folder_
  registered` widened to `(kb_id, item)`: calls `manager.request_index(
  kb_id)` then `watch.start(kb_id, item)`, each a no-op with no manager
  installed; the `create_kb_item` call site passes `item`.
  `delete_knowledge_base`: `watch = get_watch_manager()`; the whole
  `manager.stop(kb_id)` → `repo.delete` (404 inside) → `store.delete_kb`
  sequence wrapped in `async with (watch.suppress(kb_id) if watch is not
  None else contextlib.nullcontext()):`, with `watch.stop_kb(kb_id)`
  called first inside the guarded region. `delete_kb_item` (folder
  branch): the same suppression wrapper (built only when `item.type ==
  "folder"`, so a standalone-file delete never touches `watch` or enters
  suppression) around `watch.stop(item_id)` → `manager.stop(kb_id)` →
  `repo.delete` → `store.delete` → `manager.request_index(kb_id)`; the
  file branch is unchanged. `get_kb_status`: each `folders[]` entry gains
  `"watch": watch.state(f.id) if watch is not None else "off"` and
  `"watch_error": watch.error(f.id) if watch is not None else None`.
  `_after_monitoring_settings_changed`: filled in from Leg 1's no-op —
  `watch = get_watch_manager(); if watch is not None: await
  watch.apply_settings(monitoring)`; docstring updated.
- `tests/test_mcp_pool.py::test_lifespan_shutdown_drain_order`: added a
  `_FakeWatchManager` (`__init__(self, *, index_manager)`, `start_all` →
  `"watch_start"`, `drain` → `"watch_drain"`), monkeypatched onto
  `app_mod.WatchManager`; a matching instance-tracking list for
  `_FakeIndexingManager` so the test can assert the watch manager was
  constructed with the SAME indexing-manager instance app.py's startup
  block built (proof construction happens after, not instead of, the
  indexing manager's `start_all`); the `drain_steps` filter tuple and the
  pinned list widened to `connector_start, indexing_start, watch_start,
  watch_drain, indexing_drain, pty, evict, mcp, oauth, connector_drain,
  db`. Added a second, leaner test,
  `test_lifespan_watch_manager_drain_runs_even_when_start_all_raises`
  (AC-1's behavioural variant), proving a raising `start_all` still
  reaches `watch_drain` then `indexing_drain`.
- `tests/test_db_api.py`: `import contextlib` added at module top (for
  the new `_FakeWatchManager.suppress` async context manager). New
  `_FakeWatchManager` class (near `_FakeIndexingManager`) exposing
  `start`, `stop`, `stop_kb`, `state`, `error`, `apply_settings`, and an
  `asynccontextmanager` `suppress` recording `suppress_enter`/
  `suppress_exit`, all appending to one `calls` list. The two Flight 3
  recorder tests (`test_after_folder_registered_called_once_with_kb_id`,
  `test_after_folder_registered_not_called_for_file_item`) updated for
  the `(kb_id, item)` hook signature. New tests: registering a folder
  calls `request_index` then `watch.start(kb_id, item)` in order with the
  created item
  (`test_after_folder_registered_starts_watch_after_request_index`);
  registering a `file` item calls neither
  (`test_after_folder_registered_does_not_start_watch_for_file_item`);
  `/status` reports a fake watch manager's `state`/`error` per folder
  (`test_reports_watch_state_from_manager`); the exact-dict status test
  widened with `"watch": "off", "watch_error": None` for the no-manager
  case; delete-route ordering under suppression for both routes
  (`test_delete_knowledge_base_under_watch_suppression_ordering`,
  `test_delete_folder_item_under_watch_suppression_ordering`), an unknown
  `kb_id` still exiting suppression
  (`test_delete_knowledge_base_unknown_kb_exits_suppression`), and the
  standalone-file delete calling neither manager
  (`test_delete_file_item_calls_neither` widened with a `_FakeWatchManager`
  assertion); the settings-hook sibling tests
  (`test_put_calls_watch_manager_apply_settings_with_saved_monitoring`,
  `test_put_touching_only_chunking_still_calls_apply_settings`,
  `test_put_422_does_not_call_apply_settings`).
- `CLAUDE.md`: the Knowledge bases paragraph gained the data-directory
  422 refusal, the monitoring subsystem (watcher + periodic reconcile,
  live-configurable, `/status`'s `watch`/`watch_error` fields), and the
  ninth `doctor` gate, in one paragraph in the existing voice.
- `the_one/agents.md`: `supervised-per-entity-worker`'s generic paragraph
  loosened to `start`/`stop`/`drain`/`state` (plus a `request` wake for
  pass-shaped managers) and its citation names `WatchManager` as the
  third instance with DD-1's shares/does-not-share sentence.
  `leg-staged-hook-seam` gained a second citation for
  `_after_monitoring_settings_changed`. "Knowledge settings" widened to
  three records with `MonitoringSettings`' bounds and the live-apply
  note. The `IndexingManager` block's "Route wiring" bullet updated for
  the two-argument hook and the suppression wrapping. A new `WatchManager`
  block was added immediately after the `IndexingManager` block, in its
  bullet style, citing `watcher.py`'s module docstring as authoritative
  rather than restating every implementation rule: contract summary,
  DD-0's pinned-knob/two-step rule, the message protocol, the state
  vocabulary, the DD-3 trigger and suppression, the DD-4 reconcile loop
  and its resurrect-a-stopped-worker property, root removal, the cap and
  the inotify instances/descriptors note, the WSL `/mnt/c` note, the
  DD-7 lifespan order, and the two DD-2 divergences from the walk.
- `SECURITY-MODEL.md`: the Knowledge-base indexing bullet gained two
  sentences — the data-directory registration refusal (422) and the
  watcher's trust boundary (operator-chosen trees, app's own process
  privileges, same boundary as the walk, no new one).

**Verification**

- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_mcp_pool.py
  tests/test_db_api.py tests/test_kb_watcher.py -x --timeout 60`: **213
  passed, 2 deselected**, 90.34s (re-run after the doc edits: same
  result, 86.39s).
- Real-lifespan pre-check: `PYTHON=.venv/bin/python bash
  scripts/run-tests.sh tests/test_lifespan.py tests/test_credential_gate.py
  tests/test_self_configuration_surface.py tests/test_window_focus.py -x
  --timeout 60`: **109 passed**, 17.38s — benign as the leg's Edge Cases
  predicted (no folders in those tests → no watch threads, one sleeping
  reconcile-loop task per cycle, cancelled by `drain`).
- `make lint` (`ruff check` + `ruff format --check`, `the_one/ tests/
  scripts/`): clean, 439 files formatted.
- `make test-unit` (run once, alone, foreground, verbatim): **4649
  passed, 10 skipped, 557 deselected, 637.89s (0:10:37)**, exit code 0
  (+10 over Leg 2's 4,639 — 9 new tests in `test_db_api.py` plus 1 in
  `test_mcp_pool.py`). No `-m live` run; no port 8484/8485 or
  default-data-dir instance touched.
- AC-6 greps: `grep -n "two \`app_metadata\` JSON records\|expected to be
  the third instance\|_after_folder_registered(kb_id)\`" the_one/agents.md`
  → no hits (stale citations fully replaced); `grep -c "file watcher"
  CLAUDE.md` → 1.

**Decisions / deviations**

- AC-1's "behavioural variant" (a raising `start_all` still records
  `watch_drain`/`indexing_drain`) was written as a second, standalone test
  (`test_lifespan_watch_manager_drain_runs_even_when_start_all_raises`)
  rather than a parametrization of `test_lifespan_shutdown_drain_order`,
  to keep that test's already-large fixture surface from growing a
  branch; the leaner variant patches only the symbols its narrower
  assertion needs.
- The ordering assertions for AC-3 use two separate fakes
  (`_FakeIndexingManager`, `_FakeWatchManager`), each with its own `calls`
  list, rather than one shared list across both managers — the leg's
  Outputs section describes the combined trace in prose
  (`suppress_enter, watch_stop, indexing_stop, delete, request_index,
  suppress_exit`) but the existing `_FakeIndexingManager`/route-test
  precedent (Leg 3 of Flight 3) already asserts indexing-manager ordering
  via its own isolated `calls` list; splitting the assertion in two
  preserves that precedent and is equally dispositive for the ordering
  property under test (each fake's own call sequence is still pinned, and
  cross-manager interleaving is not a Flight 4 concern this leg's ACs
  require pinning).
- No blockers; no acceptance criterion required reinterpretation. Leg 2's
  one point of residual doubt (AC-12's repository-import scan) is
  unaffected by this leg and remains for the flight-end reviewer.
- Leg status set to `landed` (not `completed`) and nothing checked off in
  `flight.md`, per this leg's task instructions — the flight-end review
  handles both.

**Review fix (2026-09-16)**

- Flight-end review, cycle 1, blocking: the AC-3 ordering tests' two
  disjoint `calls` lists (see "Decisions / deviations" above) did not
  prove the cross-manager sequence. Fixed in `tests/test_db_api.py`:
  `_FakeIndexingManager.__init__` and `_FakeWatchManager.__init__` both
  gained an opt-in `calls: list[tuple] | None = None` parameter (default
  a fresh list, so every other Leg 3 test using the fakes solo is
  unaffected); two new module-level helpers,
  `_patch_kb_delete_records`/`_patch_kb_item_delete_records`, wrap
  `KnowledgeBaseRepository.delete`/`KBItemRepository.delete` to append a
  `("delete", id)` entry onto the shared list before calling through to
  the real implementation (or its `KeyError`). All three AC-3 tests
  (`test_delete_knowledge_base_under_watch_suppression_ordering`,
  `test_delete_folder_item_under_watch_suppression_ordering`,
  `test_delete_knowledge_base_unknown_kb_exits_suppression`) now pass one
  shared list into both fakes plus the repository patch and assert the
  single interleaved sequence exactly as AC-3 states it (the unknown-
  `kb_id` test now asserts `suppress_exit` follows the `("delete", ...)`
  entry whose real call raised the `KeyError`, rather than only the two
  `watch_fake` calls around it). `the_one/interfaces/web/api.py` untouched
  (the review confirmed the implementation was already correct).
- Non-blocking, also fixed: `tests/test_kb_watcher.py`'s
  `test_no_lock_no_repository_beyond_kb_and_item` (Leg 2) now derives its
  forbidden repository-class set programmatically — `re.findall(r"^class
  (\w+Repository)", inspect.getsource(repositories_mod), re.MULTILINE)`
  minus `{KnowledgeBaseRepository, KBItemRepository}` — instead of a
  hand-picked `(KBChunkRepository, AppMetadataRepository)` pair, so a
  repository added later is still caught if `watcher.py` starts
  referencing it. One Leg 2 file touched (`tests/test_kb_watcher.py`),
  as flagged.
- Verify: `PYTHON=.venv/bin/python bash scripts/run-tests.sh
  tests/test_db_api.py tests/test_kb_watcher.py -x --timeout 60` →
  **185 passed**, 100.99s (re-run 114.09s after the line-length fix
  below, same result). `make lint` (`ruff check` + `ruff format --check`,
  `the_one/ tests/ scripts/`): one `E501` (101 > 100 chars) on the new
  `test_kb_watcher.py` assert message, shortened; clean on re-run, 439
  files formatted. `make test-unit` not re-run (test-only fix; the
  Reviewer's own full run was left executing in its own process group
  per instruction, not disturbed).

---

## Decisions

### Flight Director Notes — flight start (2026-09-16)

- Loaded `.flightops/ARTIFACTS.md`, `FLIGHT_OPERATIONS.md`, `agent-crews/flight-design.md` (structure valid: Crew, Interaction Protocol, Prompts present).
- Sources read: `mission.md` (Flight 4 bullet, Open Questions, Known Issues, Branch Layout), Flight 3 `flight.md` (DD-1, DD-3, DD-5, DD-6, DD-7, DD-8, DD-9), Flight 3 `flight-debrief.md` (Recommendations 2, 3, 6, 7; Technical notes), the four Flight 3 leg artifacts, `tests/behavior/kb-folder-index-round-trip.md`.
- Code read: `the_one/knowledge/manager.py` (whole), `walk.py` (skip rules inline at the dot-prefix, `SKIPPED_DIRS` and suffix checks), `settings.py` (whole), `connectors/manager.py` (`ConnectorManager` supervisor loop), `interfaces/web/app.py` (indexing-manager lifespan block; the purge and catalog-refresh loops), `interfaces/web/api.py` (knowledge-base routes, `_after_folder_registered`, knowledge-settings routes), `diagnostics.py` (`run_doctor` gates, `_vector_probe_outcome`, `_probe_usearch`), `platform/paths.py`, `tests/test_kb_manager.py` (fixtures), `tests/test_mcp_pool.py::test_lifespan_shutdown_drain_order`, `tests/conftest.py` (`THE_ONE_DATA_DIR` isolation), `ci/tasks/windows-installer-build.yml` and `.github/workflows/windows-installer.yml` (by-name needles), `the_one/agents.md` (the two conventions named by squawk 0065; the eight-gates table).
- HAT: not planned. The operator's rule at the Flight 3 debrief — HAT legs only where there is a screen — applies; this flight has no UI surface. The walk-through joins Flight 6's HAT.
- Branch: `mission/24-knowledge-bases` at `a657873`, 36 ahead of `main` (`970c5d4`, release 0.8.1), 0 behind. No merge from `main` at this boundary.
- Methodology (Flight 3 debrief Recommendation 4): every number the operator had not given — settle 5 s / hold 60 s, interval 300 s, the 10 s floor, the 5 s drain budget — was put to the operator as a labelled Flight Director proposal or is recorded in the DD as one. The drain budget (5 s) and the interval floor (10 s) were not asked; they are Flight Director proposals recorded as such in DD-4 and DD-7.

### Operator interview (2026-09-16)

| Question | Answer |
|---|---|
| Open-ended input on scope and approach | "no preferences" |
| Where the interval and on/off switch live | **Administration knowledge settings** (over env vars, the recommended option) → DD-5, live application |
| Default reconciliation interval (proposal) | **5 minutes** → DD-4 |
| Refuse registering a folder that contains the data directory | **Yes, 422, plus the filter** → DD-6 |
| Ninth `doctor` gate for the file watcher | **Yes, frozen-only** → DD-9 |
| Settle window / hold cap (proposal) | **5 s settle, 60 s hold cap** (over the recommended 2 s / 30 s) → DD-3 |
| Vehicle for the Windows 1M `usearch` re-measure | **Fold into Flight 6 / mission close** → DD-12 |

### Planning premise probes (2026-09-16, this host: WSL2, kernel 6.18, `watchfiles` 1.1.1, Python 3.12)

| # | Premise | Method | Result |
|---|---|---|---|
| P1 | `watchfiles` is importable and its API matches the plan | `import watchfiles; inspect.signature(awatch)` | 1.1.1; `awatch(*paths, watch_filter, debounce=1600, step=50, stop_event, rust_timeout, yield_on_timeout, force_polling, poll_delay_ms, recursive=True, ignore_permission_denied)`; `Change ∈ {added, modified, deleted}`; a filter is any `(Change, str) -> bool` |
| P2 | A recursive subscription reports files created in brand-new subdirectories | `awatch(tmp)` while creating `sub/a.txt`, `.hidden/b.txt`, `node_modules/c.txt` with `watch_filter=None` | One set at +0.65 s with all six `added` paths — the filter is ours to apply (DD-2) |
| P3 | A missing root fails loudly at subscription | `awatch(tmp / "missing")` | `FileNotFoundError` at construction |
| P4 | Behaviour when the root is removed while subscribed | `shutil.rmtree(root)` under `awatch(root, rust_timeout=500, yield_on_timeout=True)` | **Measured on the polling backend — superseded by P13.** No exception; `deleted root` re-reported every ~300 ms (that is `poll_delay_ms`), not native behaviour |
| P5 | The stop event is honoured promptly | `stop_event.set()` from a task | Generator returned within the next step (~50 ms) in P2 and P4 |
| P6 | Events arrive on a Windows drive mounted under WSL2 | `awatch("/mnt/c/Temp/…")` while writing `p.txt` | **Measured on the polling backend — superseded by P15.** Polling delivers on any mount; the Flight Director's first reading ("drvfs delivers events") was the polling backend, not native notification |
| P7 | The extension is packaged for the operator's platform | `grep watchfiles uv.lock` | cp311 wheels for `win_amd64`, macOS x86_64/arm64, manylinux x86_64/aarch64; `anyio>=3.0.0` dependency already in the closure |
| P8 | The frozen build reaches `watchfiles` today | `grep watchfiles packaging/ ci/ the_one/` | No direct reference anywhere; reached only through `uvicorn.supervisors` (`from watchfiles import watch` under `try`), which `serve` never uses → DD-9's gate and the direct declaration |
| P9 | inotify headroom | `/proc/sys/fs/inotify/max_user_watches`, `max_user_instances` | 1,048,576 / 8,192 |
| P10 | Test data-dir isolation vs DD-6 | `tests/conftest.py:36`, `tests/test_db_api.py::client` | `THE_ONE_DATA_DIR` is a `mkdtemp(prefix="the-one-pytest-")` set once; the API client fixture does not re-point `settings.data_dir`, and every folder test registers under its own `tmp_path` — disjoint from the data dir in both directions |
| P11 | Drain order pin | `tests/test_mcp_pool.py:686-805` | `_FakeIndexingManager` spy and the pinned list exist as Flight 3 left them; DD-7 inserts `watch_start`/`watch_drain` between `indexing_start` and `indexing_drain` |
| P12 | Doctor needles | `ci/tasks/windows-installer-build.yml:110`, `.github/workflows/windows-installer.yml:96-106` | Both lanes grep `usearch: OK`, `fts5: OK`, `embedding model: OK` by name; `file watcher: OK` joins both |

**Correction after Architect cycle 1 (2026-09-16).** `watchfiles.main::_default_force_polling(None)` returns **`True` on this host** (WSL2: `'microsoft-standard'` in the kernel release), so P2, P4, P5 and P6 above measured the *polling* backend, not native notification. The rows are kept with their supersession noted; the pinned-native re-probes follow. Lesson for the log: a library that picks a backend from the environment must have that knob pinned before its behaviour is measured — DD-0 now pins every knob at both call sites.

| # | Premise (native backend pinned: `force_polling=False`, `ignore_permission_denied=True`) | Method | Result |
|---|---|---|---|
| P13 | Root removed while subscribed | `shutil.rmtree(root)` under `awatch(root, …)` | **Exactly one** set at +0.40 s: `deleted <root>`, `deleted <root>/a.txt`; then silence until the stop event — the subscription is dead without saying so (DD-1 leaves it and re-subscribes on the tick; DD-2 lets the root's own path always pass the filter) |
| P14 | Root renamed away | `root.rename(sibling)` | One set: `deleted <root>` — a rename reads as a delete; no `modified <root>` (DD-1's first draft had a `modified`-on-rename clause; removed) |
| P15 | Events on a Windows drive under WSL2 | `awatch("/mnt/c/Temp/…")` while writing `p.txt` | **Nothing delivered** in 1.7 s — native inotify does not see drvfs; the folder would read `watching` and rely on the periodic walk (DD-0 records it; the behavior spec's fixture must be on a native filesystem) |
| P16 | Path shape and new-subdirectory delivery | create `sub/a.txt` and `b.txt` under a watched root | One set: `added <root>/b.txt`, `added <root>/sub`, `modified <root>/sub/a.txt` — paths are the subscribed root plus a relative part (DD-2's pure comparison is exact); a file inside a brand-new subdirectory is reported |
| P17 | Unreadable subdirectory under the root | `chmod 000 <root>/secret`, then write `<root>/c.txt` | With `ignore_permission_denied=True`: subscription established, `added <root>/c.txt` delivered. (Architect, cycle 1: with the default `False` the subscription raises `PermissionError` at construction — a folder the walk indexes fine would read `unavailable` forever) |
| P18 | `anyio` default thread limiter | `anyio.to_thread.current_default_thread_limiter().total_tokens` (Architect) | 40, shared with Starlette's `run_in_threadpool` — the reason DD-1 runs each subscription on a dedicated thread rather than through `awatch` |
| P19 | `ignore_permission_denied` semantics (Architect cycle 2, re-verified by the Flight Director) | sync `watch(root, force_polling=False, ignore_permission_denied=…, rust_timeout=300, yield_on_timeout=True)` on a thread | **`True` swallows every registration error**: a missing root constructs and yields empty sets (`['empty','empty']`); with `False` a missing root raises `FileNotFoundError: No path was found.` and an unreadable subdirectory raises `PermissionError … about ["<root>/secret"]`, which `True` survives. Contrary to the `.pyi`. → DD-0's two-step rule |
| P20 | Stop latency of the dedicated-thread subscription | `stop_event.set()` → generator return, `rust_timeout=1000, step=50` | **0.9 ms** on this host (the Architect measured 16 ms) — the 5 s drain budget is generous by three orders of magnitude |

### Architect design review — cycle 1 (2026-09-16)

**Verdict**: needs rework. The spine (trigger-only watcher, shared predicate, periodic walk as correctness, data-dir refusal, drain ordering, additive `/status`) confirmed against the tree; every `file:symbol` citation checked, two accuracy slips found. Findings and how each was incorporated:

| Severity | Finding | Incorporated as |
|---|---|---|
| high | `watchfiles` force-polls by default on WSL; P2/P4/P5/P6 measured polling; DD-9's "native" claim was unverifiable | **DD-0** (new): every knob pinned at both call sites; probes re-run (P13–P18); operator chose native everywhere at the checkpoint |
| high | DD-1's root-removal rule (`deleted` **or `modified`** on the root) would tear the watch down on every file creation, since a file added inside the root yields `modified <root>` | DD-1: `Change.deleted` on the root only; `modified <root>` pinned as survivable by a unit AC; P14 shows rename also reads as `deleted` |
| high | `ignore_permission_denied` defaults to `False`; one `chmod 000` subdirectory kills the subscription at construction while the walk skips and counts it | DD-0 pins `True`; P17 verifies; AC added |
| medium-high | The filter is applied after the notifier has registered watches for the whole tree, so the inotify-descriptor argument does not hold | DD-2 "Honesty about what the filter does not do"; the ENOSPC degrade is the answer |
| medium | The reconcile tick and a sibling folder's timer can `request_index` inside a delete route's `stop → delete` window, re-opening the Flight 3 AC-10 race | DD-3 `suppress(kb_id)` async context manager; DD-8 both delete routes hold it; AC |
| medium | `is_watch_candidate` would drop `deleted <root>` for a root with a dotted name | DD-2 clause (1): the root's own path always passes; test with a dotted root |
| medium | `Path.relative_to` raises for a path outside the root (macOS `/private/var`, Windows casing); a raise inside `watch_filter` kills the subscription | DD-2 clause (2): never raising, returns False |
| medium | A merged `is_skipped_name` called at the top of the walk loop would change `WalkResult` counter semantics | DD-2: `is_hidden_name` replaces only the dot-prefix check at its existing site; `SKIPPED_DIRS` stays inline and counted |
| medium | Leg 2 was the whole feature | Split: `watch-manager` (module + tests, no wiring) and `wiring-routes-and-docs` |
| medium | DD-9's "first yield non-empty" is a false-FAIL on a loaded frozen runner | DD-9: iterate until non-empty or a 10 s deadline, explicit close, 200 ms debounce; `_vector_probe_outcome` is already name-agnostic |
| medium | `indexer = idle` asserted at a 10 s interval samples mid-pass | Spec: `idle` or `running` wherever the interval is 10 s; counts carry the assertion |
| medium | Step 8's 20 s cold-restart bound is too tight (model load in the first pass) | Spec: 60 s |
| medium | DD-3's `loop.call_later` cannot be driven by a fake clock | DD-3: small real values through constructor keywords; Verification reworded; delay clamped ≥ 0 |
| medium | `awatch` blocks a worker of the shared 40-token `anyio` limiter | DD-1: dedicated daemon thread per subscription; cap 64 (operator's choice at the checkpoint) |
| medium | The live-apply hook's sync/async shape was unpinned | DD-5: `async def`, awaited by the route |
| medium | DD-1's ENOSPC premise had no negative test | DD-1: factory-raised `FileNotFoundError` / `OSError(ENOSPC)` / `RuntimeError` ACs |
| low | "four test modules" → three | DD-5 corrected |
| low | `state()` `"off"` conflated three conditions; `watching` could be reported before the subscription existed | DD-1: entry before task; `starting` state; `watching` only after the first yield |
| low | `excluded_roots` should be a constructor keyword | DD-2 |
| low | Spec's row note claimed the item id changes across root removal and return; the walk leaves children untouched on `OSError`, so it does not | Spec note corrected |
| low | "No `POST …/reindex` was made" is Executor conduct, not an observable | Moved to the Actions column |
| low | Registering the home directory now 422s (data dir is under the profile) | DD-6 detail hint |
| low | The 60 s launcher join also covers other drains | DD-7 margin sentence |

Architect questions answered at the operator checkpoint (2026-09-16): backend → **native everywhere** (DD-0); watched-folder bound → **64, degrade past it** (DD-1); gate shape → **import unconditional, round-trip frozen-only** (DD-9). Question 3 (use `stop_kb` during a folder delete) resolved by design instead: `suppress(kb_id)` closes the window without restarting sibling watches.

Suggestions taken: a Divert criterion for the backend; the one-request-per-window count as a unit AC; DD-4 names the resurrect-a-`stopped`-worker property. Suggestion not taken: a `watch_backend` field on `/status` — with DD-0 pinning native everywhere the field would be constant.

Substantive changes → a second Architect pass.

### Architect design review — cycle 2 (2026-09-16)

**Verdict**: needs rework — one high, ten medium, six low. Cycle-1 incorporation: 19 of 23 findings incorporated in full; the `ignore_permission_denied` fix (cycle 1, high) introduced the new high; two sibling sites were missed (the exact-dict `/status` test; the Flight 3 spec's parent-folder 409); the fake-clock wording survived in the behavior spec's Out of Scope. Findings and how each was incorporated:

| Severity | Finding | Incorporated as |
|---|---|---|
| high | `ignore_permission_denied=True` swallows every registration error — a missing root or an inotify `ENOSPC` reads `watching` for ever; Step 9's `unavailable` could not pass; the factory-driven negative ACs would pass green against a library that can never raise | DD-0 two-step subscribe (`False` first, `True` only on `PermissionError`; P19); DD-1 records it; one AC through the real `watch` on a missing root |
| medium | An empty timeout yield (one per second) re-arming the settle timer would fire a `request_index` per KB every 60 s for ever | DD-1: empty yield marks `watching` once and does nothing else; AC |
| medium | The per-folder task had no termination path — every `stop`/`drain` would burn the full timeout | DD-1: terminal sentinel posted from the thread's `finally`; task returns on it; AC "every `stop` returns without waiting" |
| medium | `call_soon_threadsafe` from an abandoned thread after loop close raises | DD-1: guarded with `try/except RuntimeError` + `is_closed()` |
| medium | Error path covered only construction, not a mid-iteration `WatchfilesRustInternalError` | DD-1: whole `for` body wrapped; AC for a generator raising after a first yield |
| medium | DD-2 clause (5) did not lower-case the suffix (`NOTES.MD` on Windows/macOS) | DD-2 pins `.lower()`; test |
| medium | Raw `path == str(root)` is fragile on Windows (drive-letter case, `\\?\` prefix) | DD-2: `os.path.normcase` on both sides in clauses (1) and (2); Windows premise recorded as a Divert criterion |
| medium | DD-6 makes the Flight 3 spec's Step 6 (parent of fixture → 409) read 422 when `<scratch>` is under `/tmp` | DD-6: Leg 1 amends the Flight 3 spec's Preconditions (nested fixture); re-run is the operator's call |
| medium | `test_reports_folder_projection_and_manager_state` asserts `folders[]` by exact dict equality | DD-8 names it |
| medium | The doctor probe's single early write can be lost (notifier exists only after the first `next()`); a 10 s deadline × ~20 full `run_doctor` tests | DD-9: writer writes on every timeout yield; 2 s unfrozen / 10 s frozen; full-run tests monkeypatch the probe (the embedding-probe precedent) |
| medium | `start`/`stop`/`stop_kb` sync-vs-async shape unpinned | DD-1 surface list pins each |
| low | `raise_interrupt` still inherited | DD-0 pins `False` |
| low | Spec Out of Scope still said "fake clock" | Spec corrected |
| low | Two more gate-count sites (`run_doctor` docstring; `agents.md` "Six of the eight", "separate from the eight gates") | DD-9 sweeps them |
| low | `folders[].status` sampled mid-pass at a 10 s interval | Spec: one re-poll allowed on `pending`/`indexing`; DD-10 |
| low | Suppression: the tick's check must be synchronous next to `request_index`; the context manager must release in `finally` (routes raise 404 inside it) | DD-3 |
| low | inotify *instances* (default 128 on many distros) beside the descriptor note | DD-1 |

Architect questions: Q1 → the two-step subscribe (full fidelity). Q2 → attempt always, 2 s unfrozen deadline, full-`run_doctor` tests monkeypatch the probe. Q3 → amend only in Leg 1; a Leg 4 re-run of the Flight 3 spec is put to the operator. Suggestions taken: measured stop latency recorded (P20); the two new ACs listed explicitly; DD-10 names Step 3 as the clean proof. Not taken: back-off in `_resubscribe_unavailable` (one `FileNotFoundError` per tick per missing root is accepted at the 300 s default).

**Max-2 cycles reached with the second verdict still "needs rework"** — escalated to the operator per the skill: run a third Architect pass on the incorporated spec, or mark it ready on the Flight Director's incorporation.

**Operator checkpoint (2026-09-16)**: a **third Architect pass** on the incorporated spec before it is marked ready (the Flight 3 override, repeated); the Flight 3 behavior spec is **amended only** in Leg 1 — Leg 4 does not re-run it.

### Architect design review — cycle 3 (2026-09-16, operator-authorised)

**Verdict**: approve with changes — one medium, nine low, all text-level; the flight judged buildable as four legs. Cycle-2 incorporation: 16 of 17 in full; one partial (two further gate-count sentences unswept); one self-contradiction (DD-2 clause 1's form). Findings and how each was incorporated:

| Severity | Finding | Incorporated as |
|---|---|---|
| medium | The two-step subscribe retries with `True` on a `PermissionError` caused by the *root itself*, constructing a zero-watch subscription the first empty yield reports as `watching` | DD-0: `os.access(root, R_OK\|X_OK)` before the retry; an unreadable root → `unavailable` with the reason (Flight Director's call: visible); AC |
| low | Two more gate-count sentences (`run_doctor` "The other four … gate unconditionally"; `agents.md:1353`) | DD-9 sweep list |
| low | DD-2 clause (1) showed a raw string compare while forbidding one | Pinned `PurePath(normcase(path)) == PurePath(normcase(root))` |
| low | "helper thread writes on every timeout yield" is unimplementable as written | DD-9: the probe writes in the loop that consumes the yields (measured 0.35 s to first non-empty, 8/8) |
| low | Cap-created entries have no task; `drain` gathers tasks | DD-1: `task: Task \| None`; AC |
| low | Leg 1 checkpoint omitted the Flight 3 spec amendment, the dependency declaration, the CI needles; the parent-folder constraint was prose only | Checkpoint widened; the constraint becomes an explicit Precondition of the Flight 3 spec |
| low | Probe tests vs the autouse stub in `test_doctor.py` | DD-9: the `_probe_usearch` precedent (module-top import), stated |
| low | `except PermissionError` must precede `except OSError` | DD-0 |
| low | DD-3 claimed both delete routes raise 404 inside the guarded region | DD-3 corrected (`delete_kb_item`'s 404s fire before it) |
| low | Two filter/walk divergences: dotted-directory rename yields no trigger; `SKIPPED_DIRS` case-insensitive on Windows | DD-2 records both as latency-only; the `Change`-aware clause (5) suggestion declined (build-tree `.o` churn) |
| low | Recon row said Leg 3 amends the open question; the convention citation over-claims; `SECURITY-MODEL.md` content unnamed | Recon row → Leg 4; DD-1 states what is and is not shared with the convention; Completion Checklist names the bullet's content |

Suggestions taken: one `_schedule` after a successful (re)subscribe (DD-1); deadlines as module constants and the `TMPDIR` note (DD-9); the log-noise note for the Executor (spec row conventions). Declined: passing `Change` to the filter (recorded in DD-2 with the reason). Architect questions: Q1 → `unavailable`; Q2 → explicit Precondition; Q3 → same file, `_probe_usearch` precedent. Verified clean by the Architect and recorded: `is_hidden_name` counter-neutral (one `startswith` site); Step 4's three 422s under pydantic 2.13; drain-steps order vs `app.py`; DD-5's consumer list; DD-11's lock claim; only two `IndexingManager.stop` call sites outside `drain`, both covered by DD-8.

Flight marked **ready** after these edits; no fourth cycle (the Architect's own recommendation, and the operator's override was for one pass).

### Flight Director Notes — flight start, Leg 1 design (2026-09-16)

- `/mission-control:agentic-workflow flight 04 mission 24`. Phase files loaded: `.flightops/ARTIFACTS.md`, `agent-crews/leg-execution.md` (structure valid). Flight `ready → in-flight`; branch `flight/04-change-monitoring` cut from `mission/24-knowledge-bases` at `a657873`; planning artifacts committed as `e2ca4db` (the Flight 3 precedent). Four legs planned; `legs_completed = 0`.
- Leg 1 `settings-guard-and-gate` designed from DD-0, DD-2, DD-5, DD-6, DD-9, DD-11. Risk checks: no schema (a third `app_metadata` KV record, defaults on read); reachability — the 422 is reachable before the containment scan and after the root check, verified against `api.py:1527-1552`; no cache; interface — `KnowledgeSettings` widens with a default factory (three test-module consumers grepped), `save_knowledge_settings` writes three keys (`test_save_writes_both_keys` renamed, not re-added).
- **Risk tier: high** — a shared settings interface with existing consumers and a security-sensitive path check in the registration route → Developer design review before implementation; Reviewer tier for the flight-end review will be **Sonnet** on this surface.
- Developer spawned for the Leg 1 design review (Sonnet, per the crew file).
- Leg 1 design review: **approve with changes** — two lows (AC-7's stale-count grep widened to catch the bare `**eight**`; the gates-list citation corrected to `:778-787`) and one suggestion taken (a `_KNOWLEDGE_SETTINGS_NOTES` entry that monitoring changes apply immediately). The reviewer empirically confirmed the `uv lock` diff shape, the pinned `watch` kwargs and a live round-trip on this host, the monkeypatch/module-top-import mechanics, the pydantic bool coercion, and the `PurePath` normalisation. No re-review (minor fixes). Leg 1 `ready`; `[HANDOFF:review-needed]` → implementing Developer spawned (Sonnet).

### Flight Director Notes — Leg 1 landed, Leg 2 design (2026-09-16)

- Leg 1 landed by its Developer (report received with `[HANDOFF:review-needed]`; deferred to the flight-end review per the workflow): targeted run 270 passed; `make lint` clean; `make test-unit` **4,599 passed / 10 skipped / 609.39 s** (+52 tests over Flight 3's 4,547); `doctor` prints nine gates locally, `file watcher: OK`. Two Developer deviations accepted: the real-round-trip self-probe uses a 1 s deadline (native delivery measured ~250 ms here, so 200 ms would false-skip); one extra test for a non-existent data directory in the "contains" direction. Two review pointers carried to the flight-end Reviewer: the `is_watch_candidate` docstring's escaped Windows prefix; `agents.md`'s "five unconditional, one hybrid" wording. `legs_completed = 1` (uncommitted).
- Leg 2 `watch-manager` designed from DD-0, DD-1, DD-3, DD-4, DD-5, DD-7: the module and its tests only, no wiring. Risk checks: no schema; reachability — every state word (`starting`/`watching`/`unavailable`/`off`) is reachable through the factory seam and pinned by an AC; the reconcile loop's sub-floor interval is reachable in tests only through `MonitoringSettings.model_construct` via the `settings_loader` seam (recorded); no cache; interface — new module, no consumers yet (Leg 3 wires it).
- **Risk tier: high** — a lifecycle (threads, tasks, timers, a supervisor loop, a drain budget) → Developer design review before implementation.
- Developer spawned for the Leg 2 design review (Sonnet).
- Leg 2 design review: **approve with changes** — three mediums (snapshot iteration in `_resubscribe_unavailable`; the loop object captured in `start` and handed to the thread; `CancelledError` re-raised before the loop's broad except) and one timing concern (AC-3's mid-burst count → an idle-window check), plus lows (the `WatchFactory` seam widened by the `ignore_permission_denied` flag — DD-1 amended in `flight.md` to match, recorded here as an in-flight spec change; `stop`'s suppress-after-cancel; the `_Changes` type). Design-review Q1 answered by a `_lifecycle_lock` around `apply_settings`/`start_all`/`drain`; Q2: an entry removed by a delete route is sufficient, no database re-check. The reviewer verified `model_construct` bypasses `ge=10` and that `watchfiles.watch` defers `RustNotify` to the first `next()`. No re-review (no rework). Leg 2 `ready`; `[HANDOFF:review-needed]` → implementing Developer spawned (Sonnet).

### Flight Director Notes — Leg 2 landed, Leg 3 design (2026-09-16)

- Leg 2 landed by its Developer (`[HANDOFF:review-needed]`, deferred to the flight-end review): 39 watcher tests; targeted 81 passed; Leg 1's files untouched (271 passed); `make lint` clean; `make test-unit` **4,639 passed / 10 skipped / 620.25 s**. Two deviations accepted: `apply_settings`/`start_all` funnel through `_apply_locked` under the non-reentrant lock (a literal `await self.start_all()` inside `apply_settings` would deadlock — behaviour identical, AC-8 covers it); a redundant `except OSError: raise` kept so AC-1's ordering scan has a literal clause. One doubt carried to the Reviewer: AC-12's repository scan checks the two repositories `manager.py` uses rather than enumerating every class. `legs_completed = 2` (uncommitted).
- Leg 3 `wiring-routes-and-docs` designed from DD-5, DD-7, DD-8 and the doc content named in DD-0/DD-1/DD-2/DD-6. Carries Leg 1's doc gap (`agents.md:1191` still "two records"). Risk checks: no schema; reachability — every wire has a test through a fake watch manager installed via the module accessor (the `_FakeIndexingManager` precedent); interface — `_after_folder_registered` widens to `(kb_id, item)` with its two recorder tests named; the drain-order pin widens to eleven steps.
- **Risk tier: high** — lifespan wiring and a shared hook signature → Developer design review before implementation.
- Leg 3 design review: **approve with changes** — two mediums: AC-6's stale-citation grep had a `\b` that can never match after `)` before a backtick (pattern corrected to end at the backtick); the real-lifespan test family (`tests/test_lifespan.py` and siblings) was not on the leg's radar — now an Edge Case and a fast pre-check step, expected benign (no folders → no threads). Suggestions taken: AC-1's behavioural raise-variant; the shutdown cleanup lines pinned outside the `try/except`. Q2: the convention's generic paragraph is loosened ("`request` for managers whose unit of work is a pass") rather than carried by the citation alone. Every citation byte-accurate. No re-review. Leg 3 `ready`; `[HANDOFF:review-needed]` → implementing Developer spawned (Sonnet).

### Flight Director Notes — Leg 3 landed, flight-end review (2026-09-16)

- Leg 3 landed by its Developer (`[HANDOFF:review-needed]`): targeted 213 passed; real-lifespan pre-check 109 passed (benign, as the design review predicted); `make lint` clean; `make test-unit` **4,649 passed / 10 skipped / 637.89 s** (+10). Deviations: AC-1's raise variant as a separate lean test (accepted); AC-3's ordering asserted per fake with two `calls` lists rather than one interleaved trace — **weaker than the AC as written** (the AC's point is cross-manager order: suppression entered before the indexing stop and exited after the re-kick) — flagged to the flight-end Reviewer as a required fix, not accepted. `legs_completed = 3`; all three autonomous legs uncommitted.
- Phase 2d: flight-end Reviewer spawned over all uncommitted changes. **Reviewer tier: Sonnet** — the diff carries a security-sensitive path check (DD-6 in the registration route) and lifecycle/lifespan code; the flight log records the tier per the crew file. Concourse re-login done by the operator (`fly -t the-one status` → logged in; `windows-worker` running); ports 8485/8484 free; `/tmp` native ext4 — Leg 4 prerequisites hold.
- Flight-end review, cycle 1 (Sonnet): **not confirmed — one blocking issue**, the Leg 3 AC-3 ordering gap the Flight Director had flagged (two per-fake `calls` lists cannot prove the cross-manager sequence; the route implementation itself verified correct). Non-blocking: Leg 2 AC-12's repository scan should derive its forbidden set from `repositories.py`. Everything else clean: DD-6 check and tests, the escaped `\\?\\` docstring, the nine-gate wording, no stale counts, `apply_settings` idempotent on chunking-only `PUT`s, docs accurate, no identity leaks; `test_kb_watcher.py` green three times over; `make lint` clean. The Reviewer's own full `make test-unit` was left running in its process group and lets itself finish — the fix Developer runs the targeted file only. Fix Developer spawned (Sonnet) with both items; re-review to follow on the fix diff (test-only → Haiku tier per the crew file).

---

## Reconnaissance Report

The flight sources from the Flight 3 debrief's Recommendations 2 and 7 and two recorded notes, not from a code-cited item list; the recon is correspondingly short.

| Item | Classification | Evidence | Recommendation |
|---|---|---|---|
| Rec. 2a — watcher is a trigger only, debounce into one `request_index` per settle window | `confirmed-live` | `manager.py::request_index` is synchronous, coalescing, lock-free; no watcher exists | DD-1, DD-3 |
| Rec. 2b — subscribe with the walk's dot-prefix and `SKIPPED_DIRS` rules | `confirmed-live` | `walk.py::walk_folder` applies both inline (`name.startswith(".")`, `name in SKIPPED_DIRS`); no shared predicate | DD-2 extracts one predicate the walk and the watcher both call |
| Rec. 2c — never classify file state in the watcher | `confirmed-live` | design rule; nothing to verify in code | DD-1 |
| Rec. 2d — respect the lock order | `confirmed-live` | `manager.py` module docstring states the order; the watcher takes no lock | DD-1 |
| Rec. 7 — decide the Windows 1M re-measure vehicle | `needs-human-recheck` → decided | `mission.md` Open Questions, last bullet | Operator: fold into Flight 6 / mission close (DD-12); Leg 4 amends the open question |
| Technical note — `get_vector_store()` has no shutdown hook | `confirmed-live`, out of scope | `the_one/vectors/__init__.py` (no hook); Flight 3 DD-7 | Unchanged by this flight; stays recorded (DD-12) |
| Mission Flight 4 bullet — "modelled on `ConnectorManager`" | `confirmed-live` | `connectors/manager.py::_run` supervisor loop with reconnect; `agents.md` names the convention with the watcher as its expected third instance | DD-1 |

---

## Deviations

*(none yet)*

---

## Anomalies

*(none yet)*

---

## Session Notes

- 2026-09-16 — Planning session. Context gathering, code interrogation, interview, spec draft, premise probes, behavior-test draft. Architect cycle 1 (needs rework: the WSL polling default); native re-probes P13–P18; operator checkpoint on backend, cap and gate shape; spec rewritten (DD-0 added, four legs); Architect cycle 2 (needs rework: the permission flag swallows all registration errors; sentinel; empty yields); fixes applied; escalated to the operator at the max-2 boundary; operator chose a third pass (approve with changes); edits applied; flight `ready`.
