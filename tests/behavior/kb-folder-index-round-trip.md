# Behavior Test: Knowledge base folder registration indexes, reflects changes, and resumes

**Slug**: `kb-folder-index-round-trip`
**Status**: active
**Created**: 2026-09-15
**Last Run**: 2026-09-15-23-55-26 (pass, 8/8 — first run, Mission 24 Flight 3 Leg 4; see `kb-folder-index-round-trip/runs/2026-09-15-23-55-26.md`)

## Intent

Verify that an operator can register a folder on disk as a knowledge-base
source through the API, that the files in it are discovered, indexed in the
background and readable back with exact offsets, that additions, edits and
deletions in the folder are reflected by the next re-index, that an
unsupported-size file is reported as a failure rather than hidden, and that
an item stranded mid-index is requeued and finished after a restart. This
needs a behavior test rather than a unit test because the contract spans a
real process lifecycle (a background worker started by the app's lifespan,
a restart) and a real filesystem the app reads with its own privileges —
the unit suites prove each stage in isolation against fixtures; only a live
instance proves they are wired together. Mission 24 Flight 3, DD-9.

## Preconditions

- the-one is running host-native as a **dedicated dev instance** on
  `http://127.0.0.1:8485` with a **scratch data directory**, started as
  `THE_ONE_PORT=8485 THE_ONE_DATA_DIR=<scratch> <repo>/.venv/bin/the-one serve`, run detached from a scratch working directory and not the repo root (`<scratch>/cwd`; PID recorded; CLAUDE.md "SAFETY RULE") (record `<scratch>`;
  the resume step needs it). Verify with an active probe: `GET
  http://127.0.0.1:8485/api/live` returns 200. **Never 8484, never the
  operator's default data directory** (CLAUDE.md "SAFETY RULE").
- **Credential**: follow CLAUDE.md's "Behavior-test credential convention"
  — read `<scratch>/api-credential` verbatim and attach `Authorization:
  Bearer <credential>` to every `curl` call (shell-only apparatus; no
  handoff mint needed).
  A **fresh** scratch data directory has no credential file yet and
  `make up`'s verify step fails without one: run `THE_ONE_DATA_DIR=
  <scratch> the-one rotate-api-credential` once before the first `make up`
  (learned on the first run).
- The `sqlite3` CLI is on PATH (the seeded-resume step writes one row into
  `<scratch>/the-one.db` while the instance is stopped). Verify: `sqlite3
  --version` exits 0.
- A writable scratch folder for the fixture, outside the repository and
  outside `<scratch>`: `<fixture>`, nested one level under its own parent —
  e.g. `/tmp/kb-round-trip/fixture` (parent `/tmp/kb-round-trip`), **not**
  a bare `/tmp/kb-round-trip-fixture`. If it exists from a prior run,
  delete it before Step 1.
  **Amended 2026-09-16 (Flight 4 Leg 1, DD-6)**: registration now refuses
  (422) a folder that equals, contains, or lies inside the application
  data directory, so `<parent of fixture>` — the directory Step 6 registers
  to prove the existing sibling-containment 409 — **must contain neither
  `<scratch>` nor the repository**; a bare `/tmp` parent (this spec's
  original fixture) would now read 422 (data directory) before the
  containment scan Step 6 exercises ever ran, since `<scratch>` commonly
  lives directly under `/tmp` too. The nested-fixture layout above keeps
  `<parent of fixture>` (`/tmp/kb-round-trip`) disjoint from both, so
  Step 6's 409 still stands.
- No knowledge base named `KBRT-test` exists (`GET /api/knowledge-bases`);
  delete any leftover before Step 1.

## Observables Required

- http (response status and JSON bodies of `/api/knowledge-bases…` — measured via curl via Bash)
- filesystem (creating, editing and deleting fixture files; reading the scratch database in the resume step — measured via Bash)
- shell (the instance's `make up` / `make down` exit codes and the `/api/live` probe — measured via Bash)

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | (Setup, no judgment) Probe `GET /api/live` for 200. Create `<fixture>/` with: `notes/alpha.md` (three paragraphs of distinct prose containing the exact token `zebrafish-alpha`), `code/beta.py` (a 60-line Python file containing the identifier `gamma_delta_handler`), `.hidden/secret.txt` (any text), `.env` (any text), `data/big.txt` (11 MiB of text), `image.png` (200 bytes of binary containing at least one NUL byte — verify with a Python byte check, not `grep`, which misreports NULs), and a symlink `link.md` → `notes/alpha.md`. | (empty) |
| 2 | `POST /api/knowledge-bases` with `{"name": "KBRT-test"}`; record `kb_id`. `POST /api/knowledge-bases/{kb_id}/items` with `{"type": "folder", "path_or_url": "<fixture>"}`; record `folder_id`. | The KB create responds 201. The folder registration responds 201 and its body's `path_or_url` is the canonical absolute path of `<fixture>` and `type` is `folder`. |
| 3 | (Wait point, no actions) Poll `GET /api/knowledge-bases/{kb_id}/status` every 2 s. | Within 60 s the body shows `items.pending` = 0, `items.indexing` = 0, `indexer` = `idle`, `items.indexed` = 2 (`alpha.md`, `beta.py`), `items.failed` = 1 (`big.txt`), `chunks` ≥ 2, and `folders` is a one-element list whose entry has `id` = `folder_id`, `status` = `indexed` and a non-null `indexed_at`. (Item counts are file items only; the folder's own walk status lives in `folders`.) |
| 4 | `GET /api/knowledge-bases/{kb_id}/items`; record `alpha_id` (the `notes/alpha.md` item) and `alpha_indexed_at_initial` (its `indexed_at`). | Exactly four items: the folder (`indexed`), `notes/alpha.md` (`indexed`), `code/beta.py` (`indexed`), `data/big.txt` (`failed`, `error` mentions the 10 MiB cap) — and no item for `.hidden/secret.txt`, `.env`, `image.png` or `link.md`. Every `file` item's `parent_id` equals `folder_id`. |
| 5 | `GET /api/knowledge-bases/{kb_id}/items/{alpha_id}/chunks`, then `GET …/items/{alpha_id}/source`. | The chunks response is a non-empty list ordered by `seq` from 0, each row with `id`, `seq`, `char_start`, `char_end`, `text`; one chunk's `text` contains `zebrafish-alpha`. The source response has `stale` = false and a `text` such that, for the first chunk, `text[char_start:char_end]` equals that chunk's `text` exactly. |
| 6 | `POST …/items` with `{"type": "folder", "path_or_url": "<fixture>/notes"}`. Then `POST …/items` with `{"type": "folder", "path_or_url": "<parent of fixture>"}` (the directory that contains `<fixture>`). Then `POST …/items` with `{"type": "folder", "path_or_url": "<fixture>/does-not-exist"}`. | The nested folder is refused **409** (it lies inside a registered folder). The parent folder is refused **409** (it contains a registered folder). The missing folder is refused **422**. `GET …/status` still shows `items.indexed` = 2 and one entry in `folders`. |
| 7 | On the filesystem: append a new paragraph containing the exact token `zebrafish-omega` to `notes/alpha.md`; create `notes/new.txt` containing `hotel-november`; delete `code/beta.py`. Then `POST /api/knowledge-bases/{kb_id}/reindex` (no query string — the default `changed` scope, a reconcile walk). | The re-index responds **202** with a JSON body `{"scope": "changed", "requeued": 0}`. |
| 8 | Poll `GET …/status` every 2 s until idle, then `GET …/items`, `GET …/items/{alpha_id}/chunks` and `GET …/items/{alpha_id}`; record `alpha_indexed_at` from the last one's `indexed_at`. Then `POST …/reindex?scope=bogus`, then `POST …/reindex?scope=all`; poll `GET …/status` until idle again; `GET …/items/{alpha_id}` once more. | Within 60 s of Step 7: `items.pending` = 0, `items.indexing` = 0, `indexer` = `idle`. `GET …/items` now lists `notes/new.txt` as `indexed`, no longer lists `code/beta.py`, and still lists `data/big.txt` as `failed`. The chunks response includes a chunk whose `text` contains `zebrafish-omega`. `alpha_indexed_at` is later than `alpha_indexed_at_initial` (the edit was re-indexed). `scope=bogus` responds **422**. `scope=all` responds **202** with `{"scope": "all", "requeued": 3}` (`alpha.md`, `new.txt`, `big.txt` — every `indexed` or `failed` file item); within 60 s the status is idle again with `items.indexed` = 2 and `items.failed` = 1 unchanged, and `alpha.md`'s `indexed_at` is later than `alpha_indexed_at` (everything was re-embedded). Update `alpha_indexed_at` to this newest value. |
| 9 | (Setup, no judgment) Stop the instance (`make down` against the same env; confirm `GET /api/live` no longer answers). With `sqlite3 <scratch>/the-one.db`, run `UPDATE kb_items SET status='indexing' WHERE id='<alpha_id>';` and confirm `SELECT status FROM kb_items WHERE id='<alpha_id>';` prints `indexing`. | (empty) `[mixed-frame]` — there is no user-facing way to strand an item mid-index; the seeded row stands in for a process killed between chunk commit and flush. |
| 10 | Start the instance again with the same scratch-cwd `THE_ONE_PORT=8485 THE_ONE_DATA_DIR=<scratch> <repo>/.venv/bin/the-one serve`; probe `GET /api/live` until 200. Then poll `GET …/status` every 2 s. | Within 60 s of the probe answering: `items.indexing` = 0, `items.pending` = 0, `indexer` = `idle`, and `GET …/items/{alpha_id}` shows `status` = `indexed` with an `indexed_at` later than `alpha_indexed_at` recorded in Step 8 — the stranded item was requeued and finished without operator action. |
| 11 | (Teardown, no judgment) `DELETE /api/knowledge-bases/{kb_id}`; confirm it no longer appears in `GET /api/knowledge-bases`. Delete `<fixture>/`. | (empty) |

**Row conventions:** one row = one logical checkpoint. Steps 3, 8 and 10 are
wait points; Step 10 is the load-bearing resume assertion and Step 4 the
load-bearing filter assertion (what is *not* an item matters as much as what
is). **Cache discipline:** every read is a fresh `curl`; nothing here is
client-cached.

## Out of Scope

- Filesystem *events* (a change reflected without a re-index request) —
  Flight 4's watcher; this spec drives the reconciliation walk explicitly
  through `…/reindex`.
- Agent-facing search and the semantic/keyword fusion — Flight 5; no query
  route exists at this flight.
- Studio rendering of any of this — Flight 6.
- Live-kill timing (killing the process while a large folder is mid-index)
  — see Variants; the seeded Step 9 proves the same requeue primitive
  deterministically.

## Variants (optional)

- **live-kill**: replace Steps 9–10 with: generate 2,000 × 50 KB text files
  into `<fixture>/bulk/`, `POST …/reindex`, and within 3 s of the 202 send
  SIGKILL to the instance's PID (`<repo>/.the-one.8485.pid` — the
  Makefile scopes the PID file by port, so the dev instance never clobbers
  production's); restart; expect the
  same terminal state as Step 10 with `items.failed` unchanged. Higher
  fidelity, flake-prone by construction — run only when the seeded variant
  passes.
- **large-folder settle** (Mission 24 Flight 7 `regression-net-and-gates`
  leg, F4 debrief Rec. 3): reuses live-kill's own generator — the same
  2,000 × 50 KB text files into `<fixture>/bulk/`, no second generator
  authored — but does **not** kill anything. Register the bulk-laden
  `<fixture>` at Step 2 (instead of the small default fixture) and replace
  Step 3's single terminal poll with dense sub-2 s sampling from
  immediately after the `202` all the way to `indexer: idle`, recording
  `indexer` and `folders[0].watch` (and `folders[0].status`) on every
  sample rather than only at the end. The point is duration, not damage:
  the mandated small fixture (three good files) indexes in well under a
  second, so a single poll almost always lands on the terminal state and
  the transient states are never actually observed — this variant's whole
  job is to make the pass slow enough that the poll genuinely lands mid-pass
  on more than one sample. Expect `folders[0].watch` to read `starting` on
  the first one or two samples before settling to `watching` (per
  `kb-folder-watch-round-trip`'s own tolerance for that state), `indexer`
  to read `running` for the bulk of the pass and `idle` only once every
  item resolves, and the terminal counts to match Step 3/4's shape scaled
  up (`items.failed` = 1 for the deliberately oversized file, `items.indexed`
  = 2,002). **Flake profile, stated honestly, as live-kill's is**: this
  variant cannot flake on live-kill's axis — there is no SIGKILL race to
  win or lose — but it can still pass vacuously. On a fast disk or a warm
  embedding-model cache the pass may still resolve inside the first one or
  two poll intervals, in which case `starting`/`running` were not actually
  exercised and the run log must say so rather than claim the tolerance
  was proven; only a genuinely slow/cold pass forces the multi-sample
  transient window this variant exists to observe. Run only when the
  seeded variant (Steps 1–11) passes, and record the observed pass
  duration and sample count either way.
