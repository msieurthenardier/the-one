# Leg: settings-guard-and-gate

**Status**: completed
**Flight**: [Change Monitoring](../flight.md)

## Objective

Land everything Flight 4 needs that does not require a running watcher: the
`MonitoringSettings` record on the knowledge-settings routes with its
live-apply hook as an awaited no-op (DD-5), the data-directory refusal at
folder registration (DD-6), the two shared filter predicates in `walk.py`
(DD-2), the direct `watchfiles` dependency (DD-11), the `file watcher`
doctor gate with every `watchfiles` knob pinned (DD-0, DD-9) together with
its CI needles and gate documentation, and the Flight 3 behavior spec's
Preconditions amendment (DD-6) — each with its tests.

## Context

- Flight DD-0 (pinned knobs; the two-step `ignore_permission_denied` rule —
  the gate's round-trip uses `False` only, on a fresh temporary directory),
  DD-2 (predicates: `is_hidden_name` at the walk's existing site, counters
  untouched; `is_watch_candidate` never raising, clause order), DD-5
  (settings record, routes, awaited async hook), DD-6 (refusal, order,
  detail hint, Flight 3 spec interaction), DD-9 (gate shape: import
  unconditional, round-trip frozen-only; write-in-loop; deadlines as
  constants; stub in `tests/test_doctor.py`, targeted tests via the
  module-top import), DD-11 (dependency declaration, no version change).
- Flight 3's rule set that this leg must not disturb: `walk_folder`'s
  `WalkResult` counter semantics (`tests/test_kb_walk.py` stays green
  **untouched**); the registration check order existence → root →
  containment, now existence → root → **data dir** → containment;
  `update_knowledge_settings`' merge-then-revalidate shape and its 422
  contracts (squawk 0056's `extra="forbid"`).
- No watcher module exists yet (Leg 2). Nothing in this leg imports
  `the_one.knowledge.watcher`; the hook is the `leg-staged-hook-seam`
  (`agents.md`), an `async def` no-op with a docstring naming Leg 3 as its
  filler.
- Security-sensitive surface: the data-directory check is path handling in
  the registration route → Reviewer tier **Sonnet** (recorded in the flight
  log at the flight-end review).

## Inputs

- Branch `flight/04-change-monitoring` at `e2ca4db` (planning artifacts),
  clean tree.
- `the_one/knowledge/settings.py`: `EmbeddingSettings`, `ChunkingSettings`,
  `VectorStoreSettings`, `KnowledgeSettings(embedding, chunking)`,
  `load_knowledge_settings` / `save_knowledge_settings` (two records),
  keys `EMBEDDING_KEY`, `CHUNKING_KEY`, `VECTOR_STORE_KEY`.
- `the_one/interfaces/web/api.py`: `create_kb_item` (`:1504`; the folder
  branch at `:1527-1552` — `canonicalize`, `is_dir` under `to_thread` →
  422, `is_filesystem_root` → 422, `list_folders` containment → 409);
  `get_knowledge_settings` / `update_knowledge_settings` (`:1842-1880`;
  guard `set(data) - {"embedding", "chunking"}`, per-key non-dict guard,
  merge-then-revalidate, `_knowledge_settings_response`); imports at
  `:26` (`from the_one.config import settings`) and `:78` (`is_within`)
  already cover the new check — nothing to add.
- `the_one/knowledge/walk.py:101 — "if name.startswith(\".\"):"` (the single
  dot-prefix site, before the dir/file split, bare `continue`, uncounted);
  `:130 — "if name in SKIPPED_DIRS:"` (directories only, counted);
  `:136 — "suffix = os.path.splitext(name)[1].lower()"`.
- `the_one/diagnostics.py`: `_vector_probe_outcome(name, reason)` (`:320`,
  docstring says "for the vector-store probe"), `_probe_usearch` (`:408`),
  `run_doctor` (`:710`; docstring enumerates the gates and says "Of those
  **eight**, four are frozen-only" and "The other four — child spawn,
  python interpreter, fts5, and embedding model — gate unconditionally";
  `gates = [...]` list ending with `embedding_model`).
- `tests/test_doctor.py`: `from the_one import diagnostics` (`:19`) and the
  module-top `from the_one.diagnostics import (… _probe_usearch, …)`
  (`:20-31`); the autouse `_stub_embedding_probe` fixture (`:48-59`) with
  its header comment explaining the 19-call-site cost;
  `TestEmbeddingProbeGating::test_does_not_use_the_frozen_only_helper`
  (`:685`, `inspect.getsource` scan — applies to the embedding probe only).
- `pyproject.toml:18 — "uvicorn[standard]>=0.30"`; no `watchfiles` line.
  `uv.lock` pins `watchfiles==1.1.1` transitively.
- `ci/tasks/windows-installer-build.yml:110` needle array;
  `.github/workflows/windows-installer.yml:96-106` `grep -q` needles.
- Docs: `the_one/agents.md:1340` ("The eight gates" table), `:1353` (the
  unconditional-gate sentence with the frozen-only list; "separate from
  the eight gates"), `:1355` ("Six of the eight wrap their body"), `:1357`
  (`_vector_probe_outcome` paragraph — "the vector-store probe … routes
  every failure through"); `README.md:52` (`doctor` line);
  `docs/windows-install.md:127-132` (the prose list of checks).
- `tests/behavior/kb-folder-index-round-trip.md` (status `active`):
  Preconditions name `<fixture>` "e.g. `/tmp/kb-round-trip-fixture`"; Step
  6 registers `<fixture>/notes` (409), `<parent of fixture>` (409),
  `<fixture>/does-not-exist` (422).
- Tests that pin today's contracts and must stay green: `tests/test_kb_walk.py`
  (untouched), `tests/test_knowledge_settings.py` (`:58
  test_save_writes_both_keys` updates to three keys), `tests/test_db_api.py::
  TestKnowledgeSettingsAPI` (`:1711-1780`) and the folder-registration
  tests (`:767-960`), `tests/test_doctor.py`.
- Host facts (flight log P1, P13, P19, P20): `watchfiles` 1.1.1 in `.venv`;
  native notification works under `/tmp` with `force_polling=False`;
  `ignore_permission_denied=True` swallows a missing root.

## Outputs

- `the_one/knowledge/settings.py`: `MONITORING_KEY = "knowledge.monitoring"`;
  `MonitoringSettings(watch_enabled: bool = True,
  reconcile_interval_seconds: int = Field(300, ge=10, le=86400))`,
  `extra="forbid"`; `KnowledgeSettings.monitoring` with a default factory;
  `load_knowledge_settings` reads the third record with the same
  fall-back-with-warning rule; `save_knowledge_settings` writes three
  records; `__all__`/module docstring updated (three records, DD-5).
- `the_one/interfaces/web/api.py`: `_knowledge_settings_response` emits
  `"monitoring"`; `update_knowledge_settings` accepts `monitoring` (guard
  set, non-dict guard, merge, revalidate) and, after `save_knowledge_
  settings`, `await _after_monitoring_settings_changed(updated.monitoring)`;
  `async def _after_monitoring_settings_changed(monitoring:
  MonitoringSettings) -> None` — a documented no-op ("Leg 3 fills this with
  the watch manager's `apply_settings`"); `create_kb_item` folder branch
  gains the data-directory check between the root check and the
  containment scan.
- `the_one/knowledge/walk.py`: `is_hidden_name(name: str) -> bool` and
  `is_watch_candidate(path: str, *, root: Path, extensions: frozenset[str],
  excluded_roots: tuple[Path, ...]) -> bool`, both pure, both in `__all__`
  if the module has one; `walk_folder:101` calls `is_hidden_name(name)`.
- `the_one/diagnostics.py`: `_probe_file_watcher() -> ProbeResult`, two
  module constants `_FILE_WATCHER_DEADLINE_FROZEN_SECONDS = 10.0` /
  `_FILE_WATCHER_DEADLINE_UNFROZEN_SECONDS = 2.0`, a module-level
  `_import_watchfiles()` seam the tests monkeypatch; `gates` gains the probe
  after `embedding_model`; `run_doctor` docstring and
  `_vector_probe_outcome` docstring updated.
- `pyproject.toml`: `"watchfiles>=1.0",` beside `uvicorn[standard]` with a
  one-line comment (Flight 4 imports it directly; the lock already pins
  1.1.1). `uv.lock`: only the root package's `requires-dist` metadata
  changes; no `version =` line changes.
- `ci/tasks/windows-installer-build.yml`, `.github/workflows/windows-installer.yml`:
  `file watcher: OK` needle with a comment in the house style.
- Docs: `the_one/agents.md` (nine-gate table with a "import no, round-trip
  yes" row; the four count-bearing sentences; the `_vector_probe_outcome`
  paragraph widened to "frozen-only gating"), `README.md:52`,
  `docs/windows-install.md:127-132`.
- `tests/behavior/kb-folder-index-round-trip.md`: Preconditions amended
  (nested fixture example `/tmp/kb-round-trip/fixture`; explicit constraint
  that `<parent of fixture>` contains neither `<scratch>` nor the
  repository, with the reason: registration now refuses a folder that
  overlaps the data directory); a dated amendment line under the header
  or Preconditions; status stays `active`; the Steps table untouched.
- Tests: `tests/test_knowledge_settings.py` (monitoring defaults, round-trip,
  three keys written, bounds, `extra="forbid"`, invalid stored record falls
  back), `tests/test_db_api.py` (settings routes: GET shows `monitoring`,
  PUT merge preserves the interval when only `watch_enabled` is sent, the
  three 422s — interval 5, `"maybe"`, unknown nested key — plus the
  existing guard still 422s a `vector_store` key; the hook is awaited once
  with the saved `MonitoringSettings`, via a monkeypatched recorder;
  DD-6: equal, above, inside → 422 with the detail naming the data
  directory, and check order: a non-existent path inside the data directory
  → 422 with the non-existence message), `tests/test_kb_walk.py` **gains**
  predicate tests in a new class (the existing tests byte-identical),
  `tests/test_doctor.py` (autouse stub for `_probe_file_watcher`; targeted
  tests via the module-top import: real round-trip on `tmp_path` → `ok`
  with the round-trip detail; `_import_watchfiles` raising `ImportError` →
  `ok=False` whether or not frozen; `watchfiles.watch` raising → `skipped —`
  unfrozen and `ok=False` frozen; the gates list contains nine names in
  order with `file watcher` last; the probe's source contains every DD-0
  knob name — a source-level guard like the embedding probe's).
- Flight log: Leg 1 progress entry (changes, verification, gate figures
  for the targeted runs and the leg-end `make test-unit`).

## Acceptance Criteria

- [x] **AC-1 — Settings record.** `MonitoringSettings` as specified; `KnowledgeSettings()` has `.monitoring == MonitoringSettings()`; `save_knowledge_settings` writes exactly three `app_metadata` keys (`EMBEDDING_KEY`, `CHUNKING_KEY`, `MONITORING_KEY`); `load_knowledge_settings` round-trips a non-default `monitoring` and falls back to the default with a logged warning naming `MONITORING_KEY` for invalid JSON, an out-of-bounds interval, and an extra key. `reconcile_interval_seconds` 9 and 86,401 raise `ValidationError`; 10 and 86,400 validate.
- [x] **AC-2 — Routes and hook.** `GET /api/knowledge-settings` returns `monitoring` with the defaults on a fresh database beside the existing keys. `PUT` with `{"monitoring": {"watch_enabled": false, "reconcile_interval_seconds": 10}}` → 200 echoing it and leaving `embedding`/`chunking`/`vector_store` unchanged; a following `PUT` with `{"monitoring": {"watch_enabled": true}}` → 200 with the interval still 10 (merge). 422 for: `{"monitoring": {"reconcile_interval_seconds": 5}}`, `{"monitoring": {"watch_enabled": "maybe"}}`, `{"monitoring": {"bogus": 1}}`, `{"monitoring": "off"}` (non-dict), and the pre-existing `{"vector_store": {...}}`. `_after_monitoring_settings_changed` is `async def`, is awaited exactly once per successful `PUT` with the saved `MonitoringSettings` (a test monkeypatches it with an async recorder), and is **not** awaited on a 422.
- [x] **AC-3 — Data-directory refusal.** With `settings.data_dir` monkeypatched to `tmp_path / "data"` (created): registering `tmp_path / "data"` (equal), `tmp_path` (contains it) and `tmp_path / "data" / "vectors"` (inside it, created) each → 422 with `detail` containing "data directory"; registering `tmp_path / "data" / "missing"` → 422 with the non-existence detail (order: existence first); registering `tmp_path / "docs"` (a sibling) → 201. Every existing folder-registration test passes unchanged.
- [x] **AC-4 — Predicates.** `is_hidden_name(".git")` true, `is_hidden_name("git")` false; `walk_folder` uses it at line 101 and `tests/test_kb_walk.py`'s existing tests pass **with no edit to their file except the new class**. `is_watch_candidate` (with `extensions={".md", ".txt"}`, `root=/r`, `excluded_roots=(/r/data,)`): `/r` → True (also `/r/` and, via `normcase`, a case-variant on a case-insensitive platform — assert the `PurePath` form is used); `/r/a.md` True; `/r/A.MD` True; `/r/a.png` False; `/r/README` True; `/r/sub` True; `/r/.git/x.md` False; `/r/x/node_modules/y.txt` False; `/r/.hidden` False; `/r/data/x.md` False; `/elsewhere/a.md` False; a malformed path (empty string) False, never raising. A root named `/r/notes.d` with `path == "/r/notes.d"` → True.
- [x] **AC-5 — Dependency.** `pyproject.toml` declares `watchfiles>=1.0`; after `uv lock`, `git diff uv.lock` touches only the root package's `requires-dist` block (no `version =` line changes); `uv export --no-dev --no-emit-project --extra gui --extra all-llms --format requirements-txt` still lists `watchfiles==1.1.1` exactly once.
- [x] **AC-6 — Doctor gate.** `_probe_file_watcher`: (1) `_import_watchfiles()` failing → `ProbeResult("file watcher", False, …)` on every host; (2) the round-trip — `tempfile.TemporaryDirectory()`, `watchfiles.watch(tmp, watch_filter=None, debounce=200, step=50, rust_timeout=250, yield_on_timeout=True, force_polling=False, ignore_permission_denied=False, raise_interrupt=False, debug=False, poll_delay_ms=300, recursive=True)`, a fresh file written **after each timeout yield inside the consuming loop**, success on the first non-empty set, failure at the deadline (frozen constant when `is_frozen()`, unfrozen otherwise), the generator closed in a `finally` — failure routed through `_vector_probe_outcome` (so `skipped —` unfrozen, `FAIL` frozen); (3) detail strings: success `"native change notification round-trip OK"`; a round-trip failure passes `f"import OK; round-trip: {reason}"` as the *reason* argument to `_vector_probe_outcome`, which prefixes `skipped — ` when unfrozen; (4) appended to `gates` last; `run_doctor` on this host prints nine gate lines with `file watcher: OK`. Tests as listed in Outputs, including a source-level guard that the probe's body names every knob in DD-0's list.
- [x] **AC-7 — Needles and docs.** Both CI lanes assert `file watcher: OK` by name (comment in the house style: a probe dropped from the gates list would still print `RESULT: PASS`). `the_one/agents.md`: the table lists nine gates with `file watcher` as "import no — round-trip yes"; the "Of those eight" / "other four" / "Six of the eight" / "separate from the eight gates" sentences and the `_vector_probe_outcome` paragraph are updated; `README.md:52` and `docs/windows-install.md` name the check. `grep -rn "eight gates\|Six of the eight\|other four\|Of those \*\*eight\*\*\|\*\*eight\*\*" the_one/agents.md the_one/diagnostics.py` → no stale hits.
- [x] **AC-8 — Flight 3 spec amendment.** `tests/behavior/kb-folder-index-round-trip.md` Preconditions carry the nested fixture example and the explicit constraint with its reason; the Steps table is byte-identical; status `active`; a dated amendment note.
- [x] **AC-9 — Gates.** `make lint` clean; the targeted files green with `-x --timeout 60`; `make test-unit` once at leg end, green (expected ≈ 4,547 + the new tests / 10 skipped), figures in the flight log.

## Verification Steps

- AC-1/AC-2/AC-3/AC-4/AC-6: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_knowledge_settings.py tests/test_db_api.py tests/test_kb_walk.py tests/test_doctor.py -x --timeout 60`.
- AC-4 (untouched): `git diff --stat tests/test_kb_walk.py` shows additions only, in one new class; `git diff tests/test_kb_walk.py | grep '^-' | grep -v '^---'` is empty.
- AC-5: `git diff uv.lock | grep '^[-+].*version = '` → empty; the `uv export` line count for `watchfiles==` is 1.
- AC-6: `.venv/bin/python -m the_one.main doctor | grep -c ': OK'` ≥ the previous count + 1; `… | grep 'file watcher'`.
- AC-7: the grep above; `grep -c "file watcher: OK" ci/tasks/windows-installer-build.yml .github/workflows/windows-installer.yml` → 1 each.
- AC-8: `git diff tests/behavior/kb-folder-index-round-trip.md` touches lines above `## Steps` only.
- AC-9: `make lint`; `make test-unit` (foreground, alone).

## Implementation Guidance

1. **Settings** (`settings.py`): add the model, key, field, load/save
   branches; mirror `ChunkingSettings`' docstring style; extend
   `tests/test_knowledge_settings.py` (a `TestMonitoringSettings*` class per
   the file's existing classes; `test_save_writes_both_keys` → three keys,
   renamed accordingly — rename over delete-and-re-add).
2. **Routes** (`api.py`): widen the guard set and the per-key loop to three
   keys; merge `monitoring`; construct `KnowledgeSettings(embedding=…,
   chunking=…, monitoring=MonitoringSettings.model_validate(merged))`; add
   `"monitoring"` to `_knowledge_settings_response`; add a `_KNOWLEDGE_SETTINGS_NOTES` entry (`api.py:1812-1815`) that monitoring changes apply immediately, beside the existing chunking note; define the async no-op
   hook next to `_after_folder_registered` with a docstring in that hook's
   style; `await` it after the save. Tests in `TestKnowledgeSettingsAPI`.
3. **Refusal** (`api.py::create_kb_item`): after the root check, before the
   containment loop:
   `if is_within(settings.data_dir, canonical) or is_within(canonical,
   settings.data_dir): raise HTTPException(422, detail=…)` with the DD-6
   detail. Both names are already imported. Tests in
   the folder-registration class, monkeypatching `settings.data_dir` via
   `monkeypatch.setattr(settings, "data_dir", tmp_path / "data")` the way
   `tests/conftest.py:326` does.
4. **Predicates** (`walk.py`): `is_hidden_name` above `walk_folder`; replace
   line 101's expression with a call, nothing else in the loop moves;
   `is_watch_candidate` after `plan_reconcile` with the DD-2 clause order
   in a docstring (root first; `normcase` + `PurePath`; relativise in `try
   … except ValueError: return False`; components; excluded roots via
   `PurePath.is_relative_to`; lower-cased suffix; no-suffix → True). Note in
   the docstring that the walk itself applies `SKIPPED_DIRS` to directories
   only and case-sensitively, and that the predicate is a trigger filter
   (DD-2's two recorded divergences).
5. **Dependency**: add the line; run `uv lock`; verify the diff shape.
6. **Doctor gate** (`diagnostics.py`): constants; `_import_watchfiles()`
   returning the module; `_probe_file_watcher` per AC-6 — use
   `time.monotonic()` for the deadline; write files named
   `probe-<n>.txt` with `n` incrementing per timeout yield; catch
   `Exception` around the whole round-trip and route through
   `_vector_probe_outcome("file watcher", f"import OK; round-trip:
   {reason}")`; the import failure returns `ProbeResult("file watcher",
   False, f"watchfiles import failed: {exc}")` directly. Append to `gates`;
   update both docstrings. Add the autouse stub in `tests/test_doctor.py`
   next to `_stub_embedding_probe` (same comment style — the round-trip
   costs up to 2 s per call and there are 19 call sites); targeted tests
   call the module-top-imported `_probe_file_watcher` (add it to the import
   list) so the stub does not apply — state that in a comment, per DD-9.
7. **Needles and docs**: the two lanes; the four `agents.md` sites; README;
   windows-install.
8. **Flight 3 spec**: Preconditions only.
9. **Flight log** entry; leg status `landed`. Do not commit.

## Edge Cases

- **`settings.data_dir` does not exist yet** (fresh install, first
  registration before anything wrote to it): `is_within` resolves with
  `strict=False`; the check still works. Test with a non-existent
  `tmp_path / "data"` for the "contains" case.
- **`data_dir` is a symlink**: both sides canonicalise; a symlinked data
  dir inside the folder is still refused.
- **Windows drive-letter case** in `is_watch_candidate`: `normcase`
  lower-cases on Windows; the tests run on POSIX, where it is the identity
  — assert the `PurePath` form via a POSIX-visible property (`"/r/"` and
  `"/r//sub/../"`? no — keep to what `PurePath` normalises on POSIX: a
  trailing slash and a doubled separator).
- **Round-trip probe on a host without native notification** (`TMPDIR` on
  a drvfs mount, a container without inotify): the probe reads `skipped —`
  unfrozen after the 2 s deadline; the targeted "real round-trip" test
  must therefore assert `ok is True` and accept either detail, with a
  comment — or skip itself when `_default_force_polling` would be true and
  `/tmp` is not native. Prefer: run the real round-trip test only when a
  200 ms self-probe on `tmp_path` delivers; otherwise `pytest.skip` with
  the reason.
- **`extra="forbid"` on `MonitoringSettings`**: an old stored record with an
  unknown key falls back to defaults with a warning (AC-1), never raises.
- **Hook awaited on the exception path?** No — the hook runs only after a
  successful save; a 422 returns before it (AC-2 asserts).

## Files Affected

- `the_one/knowledge/settings.py` — `MonitoringSettings`, key, load/save
- `the_one/knowledge/walk.py` — `is_hidden_name`, `is_watch_candidate`
- `the_one/interfaces/web/api.py` — settings routes, async hook, DD-6 check
- `the_one/diagnostics.py` — `_probe_file_watcher`, constants, docstrings
- `pyproject.toml`, `uv.lock` — direct dependency
- `ci/tasks/windows-installer-build.yml`, `.github/workflows/windows-installer.yml` — needle
- `the_one/agents.md`, `README.md`, `docs/windows-install.md` — gate docs
- `tests/test_knowledge_settings.py`, `tests/test_db_api.py`, `tests/test_kb_walk.py` (additions only), `tests/test_doctor.py`
- `tests/behavior/kb-folder-index-round-trip.md` — Preconditions
- `missions/24-knowledge-bases/flights/04-change-monitoring/flight-log.md`

## Citation Audit

Checked at `e2ca4db` on 2026-09-16: `walk.py:101` (`name.startswith(".")`),
`:130` (`name in SKIPPED_DIRS`), `:136` (lower-cased suffix); `api.py:1504`
(`create_kb_item`), `:1527-1552` (folder branch), `:1842-1880` (settings
routes); `diagnostics.py:320` (`_vector_probe_outcome`), `:710`
(`run_doctor`), gates list `:778-787`; `tests/test_doctor.py:19-31`
(imports), `:48-59` (autouse stub), `:685` (`getsource` guard);
`pyproject.toml:18`; `ci/tasks/windows-installer-build.yml:110`;
`.github/workflows/windows-installer.yml:96-106`; `agents.md:1340`,
`:1353`, `:1355`, `:1357`; `README.md:52`; `docs/windows-install.md:127-132`;
`tests/test_knowledge_settings.py:58`; `tests/conftest.py:326`. All present.

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
