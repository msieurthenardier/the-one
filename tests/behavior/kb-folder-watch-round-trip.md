# Behavior Test: Knowledge base folder changes are reflected without operator action

**Slug**: `kb-folder-watch-round-trip`
**Status**: active
**Created**: 2026-09-16
**Last Run**: 2026-09-16-21-49-20 (pass, 9/9 judged checkpoints, Step 4 on an operator-authorised rerun — first run, Mission 24 Flight 4 Leg 4; see `kb-folder-watch-round-trip/runs/2026-09-16-21-49-20.md`)

## Intent

Verify that once a folder is registered as a knowledge-base source, changes
in it are reflected in the index with no API call and no restart: a file
added, edited or deleted is picked up by the filesystem watcher within a
settle window; with the watcher switched off the periodic reconciliation
walk still picks changes up within its interval; the monitoring settings
apply live through the existing knowledge-settings route; a restart
re-establishes the watch; a folder that disappears leaves its index intact,
reads `failed` and `unavailable`, and recovers when it returns; and the
application data directory cannot be registered. This needs a behavior
test rather than a unit test because the contract spans a real
filesystem-notification subsystem, a real background worker and a real
process restart — the unit suites drive the watcher with synthetic change
sets; only a live instance proves the operating-system events reach the
index. Mission 24 Flight 4, DD-10.

## Preconditions

- the-one is running host-native as a **dedicated dev instance** on
  `http://127.0.0.1:{PORT}` (a dedicated non-default port, 8486 or higher, assigned per run; never 8484 or 8485) with a **scratch data directory** `<scratch>` (under `$HOME`, e.g. `$HOME/the-one-behavior-test-scratch/kbw/data`, never `/tmp`),
  started as `THE_ONE_PORT={PORT} THE_ONE_DATA_DIR=<scratch> <repo>/.venv/bin/the-one serve`, run detached from a scratch working directory and not the repo root (`<scratch>/cwd`; PID recorded; CLAUDE.md "SAFETY RULE").
  Verify with an active probe: `GET http://127.0.0.1:{PORT}/api/live`
  returns 200. **Never 8484, never the operator's default data directory**
  (CLAUDE.md "SAFETY RULE"). A **fresh** scratch data directory has no
  `api-credential` file (`serve` does not create it): run
  `THE_ONE_DATA_DIR=<scratch> the-one rotate-api-credential` once before
  the first start.
- **Credential**: follow CLAUDE.md's "Behavior-test credential convention"
  — read `<scratch>/api-credential` verbatim and attach `Authorization:
  Bearer <credential>` to every `curl` call (shell-only apparatus; no
  handoff mint needed).
- A writable scratch folder for the fixture on a **native local
  filesystem** (on this WSL2 host that means under `/tmp`, never under
  `/mnt/c` — native change notification does not see drvfs mounts),
  outside the repository and outside `<scratch>`: `<fixture>` (e.g.
  `/tmp/kb-watch-fixture`; the fixture, not the instance's data directory or cwd, is the one
  place `/tmp` stays: it is the knowledge folder under test and needs a native filesystem). If it exists from a prior run, delete it
  before Step 1. `<scratch>` must not be inside `<fixture>` and `<fixture>`
  must not be inside `<scratch>` (Step 5 registers `<scratch>` on purpose
  to be refused).
- No knowledge base named `KBW-test` exists (`GET /api/knowledge-bases`);
  delete any leftover before Step 1.
- The instance's monitoring settings are at their defaults (`GET
  /api/knowledge-settings` → `monitoring.watch_enabled` = true,
  `monitoring.reconcile_interval_seconds` = 300); reset them with a `PUT`
  if a prior run left them changed.

## Observables Required

- http (response status and JSON bodies of `/api/knowledge-bases…` and `/api/knowledge-settings` — measured via curl via Bash)
- filesystem (creating, editing and deleting fixture files; removing and recreating the fixture root — measured via Bash)
- shell (the instance's start and stop-by-recorded-PID results and the `/api/live` probe — measured via Bash)

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | (Setup, no judgment) Probe `GET /api/live` for 200. Create `<fixture>/` with `notes/alpha.md` (three paragraphs of distinct prose containing the exact token `kilo-alpha`) and `code/beta.py` (a 40-line Python file containing the identifier `lima_mike_handler`). `GET /api/knowledge-settings`. | (empty) |
| 2 | `POST /api/knowledge-bases` with `{"name": "KBW-test"}`; record `kb_id`. `POST /api/knowledge-bases/{kb_id}/items` with `{"type": "folder", "path_or_url": "<fixture>"}`; record `folder_id`. Then poll `GET /api/knowledge-bases/{kb_id}/status` every 2 s. | Both creates respond 201. Within 60 s the status body shows `items.pending` = 0, `items.indexing` = 0, `items.indexed` = 2, `items.failed` = 0, `indexer` = `idle`, and `folders` is a one-element list whose entry has `id` = `folder_id`, `status` = `indexed`, a non-null `indexed_at`, **`watch` = `watching`** (it may read `starting` on the first polls) and **`watch_error`** null. Record that `indexed_at` as `walk_1`. `GET …/items` lists `notes/alpha.md` as `indexed`; record its id as `alpha_id`. |
| 3 | On the filesystem only — **make no API call other than the reads below, and never `POST …/reindex`**: append a paragraph containing the exact token `kilo-omega` to `notes/alpha.md`; create `notes/new.txt` containing `hotel-november`; delete `code/beta.py`. Then poll `GET …/status` every 2 s. | Within 30 s of the last filesystem action: `items.pending` = 0, `items.indexing` = 0, `indexer` = `idle`, `items.indexed` = 2, and `folders[0].indexed_at` is later than `walk_1` (record the new value as `walk_2`). `GET …/items` now lists `notes/new.txt` as `indexed` and no longer lists `code/beta.py`. `GET …/items/{alpha_id}/chunks` includes a chunk whose `text` contains `kilo-omega`. |
| 4 | `PUT /api/knowledge-settings` with `{"monitoring": {"watch_enabled": false, "reconcile_interval_seconds": 10}}`. Then `PUT /api/knowledge-settings` with `{"monitoring": {"reconcile_interval_seconds": 5}}`, then with `{"monitoring": {"watch_enabled": "maybe"}}`, then with `{"monitoring": {"bogus": 1}}`. Then poll `GET …/status` every 1 s. | The first `PUT` responds 200 and its body's `monitoring` is `{"watch_enabled": false, "reconcile_interval_seconds": 10}`; `embedding`, `chunking` and `vector_store` are unchanged from Step 1. The three following `PUT`s each respond **422** (interval below the 10 s floor; non-boolean flag; unknown key), and a `GET /api/knowledge-settings` afterwards still shows `watch_enabled` false and interval 10. Within 5 s of the first `PUT`, `folders[0].watch` = **`off`**. |
| 5 | `POST …/items` with `{"type": "folder", "path_or_url": "<scratch>"}`. Then `POST …/items` with `{"type": "folder", "path_or_url": "<parent of scratch>"}`. | Both respond **422** with a `detail` mentioning the data directory. `GET …/status` still shows exactly one entry in `folders`. |
| 6 | On the filesystem only — **no API call**, watcher off: create `notes/periodic.txt` containing `papa-quebec`. Poll `GET …/status` every 2 s. | Within 30 s: `items.indexed` = 3, `items.pending` = 0, `indexer` is `idle` or `running` (at a 10 s interval a poll can land mid-pass), `folders[0].indexed_at` later than `walk_2` (record as `walk_3`), `folders[0].watch` still `off`. `GET …/items` lists `notes/periodic.txt` as `indexed` — the periodic walk found it with no watcher and no re-index call. |
| 7 | `PUT /api/knowledge-settings` with `{"monitoring": {"watch_enabled": true}}`. Poll `GET …/status` every 1 s. | 200; body's `monitoring` is `{"watch_enabled": true, "reconcile_interval_seconds": 10}` (the interval set in Step 4 is preserved by the merge). Within 5 s `folders[0].watch` = `watching` and `watch_error` null. |
| 8 | Stop the instance (`kill` the recorded PID; confirm `GET /api/live` no longer answers). Start it again with the same scratch-cwd `THE_ONE_PORT={PORT} THE_ONE_DATA_DIR=<scratch> <repo>/.venv/bin/the-one serve`; probe `GET /api/live` until 200. Poll `GET …/status` every 2 s. | Within 60 s of the probe answering (a cold start loads the embedding model in its first pass): `folders[0].watch` = `watching`, `folders[0].status` = `indexed`, `items.indexed` = 3, `items.pending` = 0, `indexer` is `idle` or `running`. `GET /api/knowledge-settings` still shows `watch_enabled` true and interval 10 (settings survived the restart). |
| 9 | Remove the fixture root entirely (`rm -rf <fixture>`). Poll `GET …/status` every 2 s. | Within 30 s: `folders[0].status` = **`failed`** with a non-null `error` naming the path; `folders[0].watch` = **`unavailable`** with a non-null `watch_error`; `items.indexed` still = 3 and `GET …/items` still lists all three files (an unplugged drive must not delete an index); `indexer` is `idle` or `running`. |
| 10 | Recreate `<fixture>/notes/alpha.md` with new content containing the exact token `romeo-sierra` (nothing else in the folder). Poll `GET …/status` every 2 s. | Within 40 s: `folders[0].status` = `indexed`, `folders[0].watch` = `watching`, `watch_error` null; `items.indexed` = 1, `items.pending` = 0, `items.failed` = 0; `GET …/items` lists only the folder and `notes/alpha.md` (`new.txt` and `periodic.txt` are gone from disk and from the index). `GET …/items/{alpha_id}/chunks` includes a chunk whose `text` contains `romeo-sierra` and none containing `kilo-alpha` (the item is the same row: the walk left children untouched while the root was gone, and the return is a content change on `alpha_id`). |
| 11 | (Teardown, no judgment) `PUT /api/knowledge-settings` with `{"monitoring": {"watch_enabled": true, "reconcile_interval_seconds": 300}}`. `DELETE /api/knowledge-bases/{kb_id}`; confirm it no longer appears in `GET /api/knowledge-bases`. Delete `<fixture>/`. | (empty) |

**Row conventions:** one row = one logical checkpoint. Steps 3, 6, 9 and
10 are the load-bearing rows: 3 proves the event path, 6 the periodic path
with the watcher off, 9 the visible degrade, 10 the recovery through the
periodic re-subscribe. Every wait point polls `/status` every 2 s (1 s for
the settings toggles). Wherever the reconcile interval is 10 s (Steps 6
through 10) the `indexer` word is allowed to read `running` — a tick's pass
is in flight for part of every ten seconds — and the item counts carry the
assertion instead. For the same reason a folder's `status` may momentarily
read `pending` or `indexing` on one poll in Steps 8 through 10; allow one
re-poll before judging that field. While the root is absent (Step 9) the
instance log records one re-subscribe warning per tick for that folder;
that is the designed retry, not a failure.

**Measurement conventions (adopted after the first run):** any Expected
Result of the form "within N s of <an API call>" is measured by a single
shell script that issues the call and begins polling in the same process,
so the first sample lands within a second of the response — issuing them
as separate commands left Step 4's first attempt with no sample inside
its 5 s window. Every `curl` call captures its HTTP status into the
evidence (`-w`), not only the body. `alpha_id` is stable across Steps 9 and 10: a failed walk
leaves the folder's children exactly as they were.

## Out of Scope

- The walk's own discovery, filter and reconcile rules, chunk offsets,
  `/source`, `reindex?scope=all`, and the seeded resume — all covered by
  `kb-folder-index-round-trip` (Flight 3).
- Event coalescing counts (that exactly one pass runs per settle window) —
  unit-tested with small real settle values in `tests/test_kb_watcher.py`;
  not observable through the API.
- The inotify watch-cap and Windows buffer-overflow degrade paths — not
  reproducible on demand; the design (walk as correctness) covers them and
  the `unavailable` state is proven here through root removal instead.
- Behaviour on a network filesystem.
- The frozen Windows build's `file watcher` doctor gate — proven by the
  flight's frozen `fly execute` run, not here.
- Studio rendering of `watch` / `watch_error` — Flight 6.

## Variants (optional)

- **Large-folder settle**: with a fixture of several thousand files, copy
  a directory of 500 supported files in at once and assert that
  `folders[0].indexed_at` advances at most a few times (the 60 s hold cap)
  rather than once per file. Timing-sensitive; run when a real corpus is
  at hand.
