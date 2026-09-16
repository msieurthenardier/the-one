# Leg: wiring-routes-and-docs

**Status**: completed
**Flight**: [Change Monitoring](../flight.md)

## Objective

Wire Leg 2's `WatchManager` into the app: lifespan start and drain in the
DD-7 order with the drain-order test extended, the Flight 3 route hooks
starting and stopping watches under DD-3 suppression, the two `/status`
watch fields, the Leg 1 settings hook filled with `apply_settings`, and the
documentation the flight owes (`CLAUDE.md`, `the_one/agents.md`,
`SECURITY-MODEL.md`) — with tests for every wire.

## Context

- Flight DD-5 (the awaited async hook `_after_monitoring_settings_changed`
  → `apply_settings`), DD-7 (construct after the indexing manager's
  `start_all`, publish before the guarded `start_all`, drain before the
  indexing manager; the 5 s budget; the `_FakeWatchManager` shape and the
  pinned order), DD-8 (routes, `/status` fields, hooks under suppression,
  the exact-dict status test), DD-1/DD-2 (`agents.md` content: what the
  watcher shares with the convention, the post-hoc-filter honesty note,
  the inotify instances/descriptors note), DD-0 (the WSL `/mnt/c` note),
  DD-6 (`SECURITY-MODEL.md` content).
- Leg 1 landed: `_after_monitoring_settings_changed` is an `async def`
  no-op at `api.py:1913`, awaited by `update_knowledge_settings`; the
  DD-6 check is in `create_kb_item`. **Leg 1 gap carried here**:
  `the_one/agents.md:1191` "Knowledge settings" still says two records —
  this leg makes it three.
- Leg 2 landed: `the_one/knowledge/watcher.py::WatchManager(index_manager,
  *, …)` with sync `start(kb_id, folder: KBItem)` (a no-op while the
  watcher is disabled), `state(folder_id)`, `error(folder_id)`; async
  `stop`, `stop_kb`, `drain`, `start_all`, `apply_settings`; `suppress(kb_id)`
  async context manager; `set_manager`/`get_manager` (`:700`/`:706`).
  `apply_settings`, `start_all` and `drain` share `_lifecycle_lock`.
  `start_all` starts the reconcile loop and, when enabled, every folder of
  every knowledge base. The module docstring is the contract `agents.md`
  cites.
- `IndexingManager`'s lifespan block (`app.py:346-362`) and drain
  (`:386-397`) are the shape to mirror; the drain-order test
  (`tests/test_mcp_pool.py:686-805`) is the pin.
- Security-sensitive? No new path handling (Leg 1's). Reviewer tier for
  the flight-end review stays Sonnet because Leg 1's surface is in the
  same diff.

## Inputs

- Working tree: Legs 1 and 2 uncommitted and landed.
- `the_one/interfaces/web/app.py:80-81` (indexing-manager imports),
  `:346-362` (construct → publish → guarded `start_all`), `:386-397`
  (drain block reading the local global, then `_set_module_indexing_
  manager(None)`).
- `the_one/interfaces/web/api.py:66` (`get_indexing_manager` import),
  `:1470-1498` (`delete_knowledge_base`: `manager.stop(kb_id)` at `:1477`
  before `repo.delete`), `:1506-1570` (`create_kb_item`; the hook call at
  `:1569`), `:1573-1578` (`_after_folder_registered(kb_id)`), `:1638-1672`
  (`delete_kb_item`: `manager.stop` at `:1656`, `request_index` at
  `:1669`), `:1675-1710` (`get_kb_status`; the `folders` comprehension),
  `:1913-1922` (`_after_monitoring_settings_changed` no-op).
- `tests/test_mcp_pool.py:686-709` (`_FakeConnectorManager`,
  `_FakeIndexingManager`, `monkeypatch.setattr(app_mod, "IndexingManager",
  …)`), `:778-805` (the `drain_steps` filter tuple and the pinned list).
- `tests/test_db_api.py:951-985` (the two `_after_folder_registered`
  recorder tests — single-argument `calls.append`), `:1355-1400`
  (`TestKnowledgeBaseStatusRoute`; `test_reports_folder_projection_and_
  manager_state` asserts `folders[]` by exact dict at `:1379`), `:1743`
  (`test_after_folder_registered_calls_request_index` — patches the
  manager, no change), `:1775` (`test_delete_folder_item_stops_before_and_
  requests_index_after` — the ordering test to extend), the
  `TestKnowledgeSettingsAPI` hook-recorder test from Leg 1 (grep
  `_after_monitoring_settings_changed`).
- Docs: `CLAUDE.md:79` ("Knowledge bases (M24)" paragraph);
  `the_one/agents.md:582-590` (`supervised-per-entity-worker` — "Flight
  4's filesystem watcher is expected to be the third instance"; and
  `leg-staged-hook-seam` citing `_after_folder_registered`), `:1191`
  (Knowledge settings, two records), `:1211-1222` (`IndexingManager`
  block; `:1222` route wiring cites `_after_folder_registered(kb_id)`);
  `SECURITY-MODEL.md:583-593` (Knowledge-base indexing bullet).

## Outputs

- `app.py`: imports `WatchManager` and `set_manager as
  _set_module_watch_manager` from `the_one.knowledge.watcher`; a module
  global `_watch_manager: WatchManager | None = None` beside
  `_indexing_manager`; startup — immediately after the indexing manager's
  `start_all` `try/except`: `global _watch_manager; _watch_manager =
  WatchManager(index_manager=_indexing_manager);
  _set_module_watch_manager(_watch_manager)`, then `try: await
  _watch_manager.start_all() except Exception: logger.exception("watch
  manager startup failed")`; shutdown — immediately **before** the
  indexing-manager drain block: `if _watch_manager is not None: try: await
  _watch_manager.drain() except Exception: logger.exception(…);
  _set_module_watch_manager(None); _watch_manager = None`. Comments in
  the block's existing style citing DD-7.
- `api.py`: `from the_one.knowledge.watcher import get_manager as
  get_watch_manager`; `_after_folder_registered(kb_id: str, item: KBItem)`
  — request the index as today, then `watch = get_watch_manager(); if
  watch is not None: watch.start(kb_id, item)`; the call site passes
  `item`; `delete_knowledge_base`: `watch = get_watch_manager()`; `async
  with (watch.suppress(kb_id) if watch is not None else
  contextlib.nullcontext()):` wrapping `stop_kb` → `manager.stop` →
  `repo.delete` (the 404 raise stays inside; the context manager releases
  in `finally`) → `store.delete_kb`; `delete_kb_item` (folder branch):
  the same wrapper around `await watch.stop(item_id)` → `manager.stop` →
  `repo.delete` → `store.delete` → `manager.request_index`; the
  standalone-file branch unchanged (no suppression needed — no stop);
  `get_kb_status`: each `folders[]` entry gains `"watch": watch.state(
  f.id) if watch is not None else "off"` and `"watch_error": watch.error(
  f.id) if watch is not None else None`; `_after_monitoring_settings_
  changed`: `watch = get_watch_manager(); if watch is not None: await
  watch.apply_settings(monitoring)`, docstring updated ("filled in Leg 3").
- `tests/test_mcp_pool.py::test_lifespan_shutdown_drain_order`:
  `_FakeWatchManager` with `__init__(self, *, index_manager)` recording
  the received manager (asserted to be the `_FakeIndexingManager`
  instance), `start_all` → `"watch_start"`, `drain` → `"watch_drain"`;
  `monkeypatch.setattr(app_mod, "WatchManager", _FakeWatchManager)`; the
  filter tuple and the pinned list become `connector_start,
  indexing_start, watch_start, watch_drain, indexing_drain, pty, evict,
  mcp, oauth, connector_drain, db`.
- `tests/test_db_api.py`: the two recorder tests take `(kb_id, item)` and
  assert the item is the created folder; a new test that
  `_after_folder_registered` calls `watch.start(kb_id, item)` on a
  `_FakeWatchManager` installed via `monkeypatch.setattr(watcher_mod,
  "_manager", fake)` (the `_FakeIndexingManager` pattern at `:1379`) and
  not for a `file` item; `test_reports_folder_projection_and_manager_state`
  widens its exact dict with `"watch": "off", "watch_error": None` (no
  watch manager installed) and a sibling test with a fake watch manager
  returning `("unavailable", "root removed")` for that folder id;
  `test_delete_folder_item_stops_before_and_requests_index_after` extends
  its ordering assertion to `["suppress_enter", "watch_stop",
  "indexing_stop", "delete", "request_index", "suppress_exit"]` with the
  fake watch manager's `suppress` recording enter/exit; a matching
  ordering test for `delete_knowledge_base` (`suppress_enter, stop_kb,
  indexing_stop, delete_kb, suppress_exit`) and one proving the 404 path
  exits suppression (`suppress_exit` recorded after a `KeyError` from the
  repository); the Leg 1 settings-hook test gains a sibling asserting a
  fake watch manager's `apply_settings` receives the saved
  `MonitoringSettings` once per successful `PUT`. Fakes live in the test
  file; a `_FakeWatchManager` exposing `start`, `stop`, `stop_kb`,
  `suppress`, `state`, `error`, `apply_settings` with a `calls` list.
- `CLAUDE.md:79`: the Knowledge bases paragraph gains (a) monitoring: a
  per-folder filesystem watcher (native notification, one dedicated thread
  per folder, at most 64) that only triggers passes, plus a periodic
  reconciliation walk every 5 minutes by default that is the source of
  truth; both under `monitoring` in `GET/PUT /api/knowledge-settings`,
  applied live; `/status`'s `folders[].watch` / `watch_error`; (b) the
  registration refusal of a folder overlapping the data directory (422);
  (c) the ninth `doctor` gate `file watcher`. Keep it to one paragraph in
  the existing voice.
- `the_one/agents.md`: (1) `:582-590` `supervised-per-entity-worker` — the
  generic paragraph's "`start` / `request` / `stop` / `drain` / `state`"
  becomes "`start` / `stop` / `drain` / `state` (plus a `request` wake for
  managers whose unit of work is a pass)", and the third citation states
  what `WatchManager` shares and what it does not (DD-1's sentence); `leg-staged-hook-seam` — a second citation:
  `_after_monitoring_settings_changed` (Leg 1 no-op → Leg 3
  `apply_settings`), noting it is `async def` because its filler awaits;
  (2) `:1191` Knowledge settings → three records, `MONITORING_KEY`,
  `MonitoringSettings` bounds, applied live via the awaited hook (unlike
  chunking); (3) a new **`WatchManager`** block after the `IndexingManager`
  block (`:1222`), in that block's bullet style: contract summary pointing
  at the module docstring; DD-0's pinned-knob rule and the two-step
  `ignore_permission_denied` rule with the verified reason; the message
  protocol and the sentinel; state vocabulary (`off`/`starting`/`watching`/
  `unavailable`) and what each means; the trigger (5 s settle, 60 s hold
  cap, one `request_index` per window, post-subscribe trigger, empty
  yields never trigger); suppression and the two delete routes; the
  reconcile loop (interval from settings per tick, wake on change,
  re-subscribe, the resurrect-a-`stopped`-worker property); the cap and
  the inotify instances/descriptors note (the filter is post-hoc — every
  directory under the root holds a descriptor); the WSL `/mnt/c` note
  (native delivery absent; walk carries it); lifespan order and the 5 s
  drain budget; route wiring (`_after_folder_registered(kb_id, item)`, the
  status fields); the DD-2 divergences (dotted-directory rename; Windows
  `SKIPPED_DIRS` case). (4) `:1222` route-wiring bullet updated for the
  two-argument hook.
- `SECURITY-MODEL.md:583-593`: the Knowledge-base indexing bullet gains
  two sentences: registration refuses a folder that equals, contains or
  lies inside the data directory (422), so the app's own database and
  index are never indexed and indexing writes never feed the watcher; the
  watcher registers operating-system change notifications on the
  operator-chosen trees and reads them with the app's own privileges — the
  same trust boundary as the walk, no new one.
- Flight log: Leg 3 progress entry.

## Acceptance Criteria

- [x] **AC-1 — Lifespan order.** `test_lifespan_shutdown_drain_order` passes with the eleven-step pinned list above; `_FakeWatchManager` received the `_FakeIndexingManager` instance as `index_manager`; a behavioural variant in which the fake's `start_all` raises still records `watch_drain` (and `indexing_drain` after it). The shutdown block's two cleanup lines (`_set_module_watch_manager(None)`; `_watch_manager = None`) sit **outside** the `try/except`, dedented, exactly as `app.py:391-397` does for the indexing manager, so the accessor is cleared even when `drain()` raises.
- [x] **AC-2 — Registration hook.** `_after_folder_registered(kb_id, item)`: with a fake indexing manager and a fake watch manager installed, registering a folder → `request_index(kb_id)` then `start(kb_id, item)` in that order with `item.id` equal to the created folder's id; registering a `file` item → neither; with no watch manager installed → `request_index` only, no error. The two Flight 3 recorder tests updated and green.
- [x] **AC-3 — Delete routes under suppression.** `delete_kb_item` on a folder → fake calls in order `suppress_enter(kb_id)`, `watch_stop(item_id)`, `indexing_stop(kb_id)`, repository delete, `request_index(kb_id)`, `suppress_exit(kb_id)`; a standalone-file delete → no watch calls at all; `delete_knowledge_base` → `suppress_enter`, `stop_kb(kb_id)`, `indexing_stop`, delete, `suppress_exit`; an unknown `kb_id` → 404 **and** `suppress_exit` recorded (released on the exception path); with no watch manager installed both routes behave exactly as before (existing tests green).
- [x] **AC-4 — Status fields.** `GET …/status` `folders[]` entries carry `watch` and `watch_error`: `"off"` / `null` with no watch manager; the fake's values otherwise; the exact-dict test updated; the Flight 3 behavior spec's named keys (`id`, `path`, `status`, `indexed_at`, `error`) unchanged.
- [x] **AC-5 — Settings hook.** A successful `PUT /api/knowledge-settings` with a `monitoring` change → the fake watch manager's `apply_settings` called once with the saved `MonitoringSettings`; a `PUT` touching only `chunking` → still called once (the hook is unconditional on success — record this: the manager's `apply_settings` is idempotent); a 422 → not called; no watch manager → no error.
- [x] **AC-6 — Docs.** `CLAUDE.md`, `the_one/agents.md` (all four sites plus the new block), `SECURITY-MODEL.md` updated as in Outputs; `grep -n "two \`app_metadata\` JSON records\|expected to be the third instance\|_after_folder_registered(kb_id)\`" the_one/agents.md` → no stale hits (the closing backtick, not `\b`, ends the third pattern — a word boundary never matches between `)` and a backtick); `grep -c "file watcher" CLAUDE.md` ≥ 1.
- [x] **AC-7 — Gates.** `make lint` clean; `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_mcp_pool.py tests/test_db_api.py tests/test_kb_watcher.py -x --timeout 60` green (the `requires_bwrap` tests in `test_mcp_pool.py` stay deselected by `addopts`); `make test-unit` once at leg end, green, figures in the flight log.

## Verification Steps

- AC-1: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_mcp_pool.py -x --timeout 60 -k drain_order`.
- AC-2–AC-5: `… tests/test_db_api.py -x --timeout 60`.
- AC-6: the greps above; read the three files' diffs.
- AC-7: `make lint`; `make test-unit`.
- Real-lifespan tests (a fast pre-check before the full suite): `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_lifespan.py tests/test_credential_gate.py tests/test_self_configuration_surface.py tests/test_window_focus.py -x --timeout 60` — these drive the real `lifespan(app)` without monkeypatching the managers and will now construct a real `WatchManager` (no folders → no threads, one reconcile-loop task per cycle, cancelled by `drain`).

## Implementation Guidance

1. `app.py` startup and shutdown blocks; the drain-order test (AC-1).
2. `api.py`: hook signature and call site; `get_kb_status`; the two delete
   routes with `contextlib.nullcontext()` for a `None` manager (`import
   contextlib` if absent); the settings hook. Tests (AC-2–AC-5) with one
   `_FakeWatchManager` class near `_FakeIndexingManager`.
3. Docs (AC-6). Keep `agents.md`'s new block in the `IndexingManager`
   block's bullet style and cite `watcher.py`'s module docstring as the
   authoritative contract rather than restating every rule.
4. `make lint`; targeted runs; `make test-unit`; flight-log entry; leg
   `landed`. Do not commit.

## Edge Cases

- **Tests that run the real lifespan** (`tests/test_lifespan.py`,
  `test_credential_gate.py`, `test_self_configuration_surface.py`,
  `test_window_focus.py`, `test_index_asset_cache_busting.py`, the
  connector plugin tests): each cycle now constructs a real
  `WatchManager`, runs its `start_all` (no folder items in those tests →
  no threads; one reconcile-loop task that sleeps 300 s) and drains it.
  Expected benign — the same shape the real `IndexingManager` already
  runs there — recorded so the Developer runs them early rather than at
  the tail of the full suite.

- **`delete_kb_item` 404s** fire before the suppression block (Flight 4
  DD-3's corrected sentence) — no `suppress_exit` expected there; the AC-3
  exception-path assertion is for `delete_knowledge_base` only.
- **`watch.start` for a folder while the watcher is disabled**: a no-op
  inside the manager; the route does not check the setting.
- **`_after_folder_registered` when the folder registration 201s but
  `start` raises** (cannot today — `start` only creates an entry — but
  wrap nothing: a raise here is a defect to surface, matching the
  indexing kick).
- **Lifespan startup when `_indexing_manager.start_all()` failed**: the
  watch manager is still constructed with the (constructed) indexing
  manager and started — it only ever calls `request_index`, which
  restarts a dead worker (DD-4's property).
- **The drain-order test's `_FakeIndexingManager` has no
  `request_index`**: the fake watch manager never calls it — fine.

## Files Affected

- `the_one/interfaces/web/app.py` — lifespan start/drain
- `the_one/interfaces/web/api.py` — hooks, delete routes, status fields
- `tests/test_mcp_pool.py`, `tests/test_db_api.py`
- `CLAUDE.md`, `the_one/agents.md`, `SECURITY-MODEL.md`
- `missions/24-knowledge-bases/flights/04-change-monitoring/flight-log.md`

## Citation Audit

Checked at the Leg 2 working tree on 2026-09-16: `app.py:80-81`,
`:346-362`, `:386-397`; `api.py:66`, `:1470-1498`, `:1477`, `:1506-1570`,
`:1569`, `:1573-1578`, `:1638-1672`, `:1656`, `:1669`, `:1675-1710`,
`:1913-1922`; `watcher.py:319` (`start`), `:365`/`:371`
(`state`/`error`), `:377`/`:397`/`:538`/`:656`/`:666`/`:678`, `:700`/`:706`
(accessors); `tests/test_mcp_pool.py:686-709`, `:778-805`;
`tests/test_db_api.py:951`, `:969`, `:1355`, `:1379`, `:1743`, `:1775`;
`CLAUDE.md:79`; `agents.md:582-590`, `:1191`, `:1211-1222`;
`SECURITY-MODEL.md:583-593`. All present.

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
