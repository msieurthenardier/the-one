# Flight Log: Folder Registration and Indexing

**Flight**: [Folder Registration and Indexing](flight.md)

## Summary

In flight. Reconnaissance, three Architect design-review cycles and the operator interview are recorded below; `flight.md` is at `ready`, the behavior-test draft `kb-folder-index-round-trip` is filed, no code has changed.

---

## Leg Progress

*(none yet)*

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
