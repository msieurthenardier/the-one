# Leg: inventory-freshness

**Status**: completed
**Flight**: [Mission Close](../flight.md)

## Objective

Make a content-only change to an indexed file visible on the inventory — the
per-item freshness field and the invalidation signature that must widen with
it — and land the three smaller inventory corrections that share the same
files: stable list ordering, persisted walk skip counters, and the
shared-vocabulary note.

## Context

**DD-6 is the leg's spine and its two halves must land in one commit.** Flight 6
recorded that they *mask each other*: `knowledgeItemsSignature`
(`studio.js:480`) is counts-only, so a content-only edit triggers no `/items`
re-fetch — harmless today only because the item row renders nothing a
content-only change would alter. Shipping the freshness field alone converts an
invisible blind spot into a **visible staleness bug**.

Architect cycle 1 corrected DD-6's cost: this is **not** a render-only change.
`get_kb_status` (`api.py:1805-1841`) carries no per-item content signal at all,
so the signature — which is computed from `/status` — cannot be widened
client-side. A freshness aggregate on `get_kb_status` is required, so this leg
touches Python.

**DD-7** comes in because Flight 6 deferred it on a premise that is false: the
walk already counts skips (`walk.py:58-59`, nine increment sites) and
`manager.py:412` already logs them. The missing work is persistence and
projection. Per the operator's decision it persists in `app_metadata`, needing
no migration — at the price of explicit cleanup, since a kv key is outside
`kb_items`' cascade delete.

**DD-11 is comment-only** by operator re-decision after the Architect found the
vocabulary is 24 class names, not three. No class is renamed in this leg.

Leg 1 (`non-ui-defect-closure`) has landed but is **not committed** — this
flight defers commit to the flight-end review, so the working tree already
carries Leg 1's changes. Do not revert or re-stage them.

## Inputs

- `the_one/interfaces/web/api.py::get_kb_status` (`:1805-1841`) — the
  projection to widen; `delete_knowledge_base` (`:1577`) and `delete_kb_item`
  (`:1758`) — the two cleanup paths
- `the_one/interfaces/web/static/js/areas/studio.js:480` —
  `knowledgeItemsSignature`, read at `:589` (mount snapshot) and `:694` (poll
  comparison)
- `the_one/interfaces/web/static/js/areas/studio/knowledge-section.js:841` —
  `buildFileItemRow`; `:905` and `:1063` — `details.className =
  'mcp-tool-item'`, the two borrows DD-11's note documents
- `the_one/db/repositories.py:527,632,640` — the three untiebroken queries;
  `:1851-1876` — `AppMetadataRepository`, which has **only** `get`/`set` and
  needs a `delete` (AC-11a)
- `squawks/0087-kb-item-list-order-has-no-tiebreak.md` — its Corrective Action
  already specifies `ORDER BY created_at, path_or_url` **and** the browser
  assertion tightening (AC-13, AC-14a)
- `tests/browser/test_flow_studio_knowledge_inventory.py` — the set-comparison
  assertions AC-14a tightens, and the fixture precedent AC-6 follows
- `the_one/knowledge/walk.py:49-59` — `WalkResult`; `manager.py:405-420` — the
  walk-completion site that already logs both counters
- `the_one/interfaces/web/static/css/studio.css:173-188` — the `.mcp-tool-item`
  comment block
- `docs/ui-testid-registry.md` — every new `data-testid` must be registered
  (`tests/test_ui_guards.py` enforces both directions)

## Outputs

- A freshness field on each item row, and a `/status` aggregate that moves with it
- A widened `knowledgeItemsSignature`
- Persisted, projected and rendered walk skip counters, with cleanup
- Three `ORDER BY` tiebreaks
- A `consumers:` note at `studio.css`
- Browser + unit tests; flight log updated

## Acceptance Criteria

**Freshness + signature (DD-6) — one commit, never separately**

- [x] AC-1 — Each file item row renders a freshness signal derived from data
      `GET /items` already returns (`indexed_at`, `content_hash`, `size_bytes`,
      `mtime`). The rendered form is the implementer's call against existing
      Studio patterns; it must change when a file's content changes and be
      stable when it does not.
- [x] AC-2 — `get_kb_status` gains a per-knowledge-base freshness aggregate
      that moves **iff** an item re-indexes. It is **additive** to the existing
      `items` counts and `chunks` — those still catch add/delete; the aggregate
      catches content-only change. No existing key is removed or renamed.
- [x] AC-3 — **`indexed_at` on a FILE item is the reliable signal; confirm the
      trace holds before building on it.** Design review traced it: a file
      item's `indexed_at` is stamped only by `update_status(..., "indexed")`
      from `_flush` (`manager.py:570`), which runs only for items actually
      re-queued and re-indexed — never on a no-op walk. A **folder** item's
      `indexed_at` is the opposite (`manager.py:441`, unconditional on every
      pass), which is why Implementation Guidance step 4 forbids it. Re-confirm
      the file-item path against the code, then build on it. Record in the
      flight log that AC-2 and AC-5 are satisfiable **together** for this exact
      reason — an aggregate over `type='file'` `indexed_at` moves iff something
      re-indexed and is stable on a quiet corpus.
- [x] AC-4 — `knowledgeItemsSignature` incorporates the new aggregate, so a
      content-only edit triggers the `/items` re-fetch at `studio.js:694`.
- [x] AC-5 — The re-fetch still does **not** fire on a quiet corpus: a poll
      tick with no indexing activity must produce an unchanged signature.
      *A signature that moves every tick would destroy an open chunks/source
      panel and scroll position on every poll — exactly what L1-D2 excluded
      polling `/items` to avoid.*
- [x] AC-6 — A browser test proves the round trip: edit a file's content in a
      registered folder, let it re-index, and assert the row's freshness signal
      changed **without a manual page reload**.
- [x] AC-7 — Both halves land in the same commit. State in the flight log that
      the freshness field was never green on its own.

**Walk skip counters (DD-7)**

- [x] AC-8 — The last completed walk's `skipped_dirs` / `skipped_entries` for
      each folder persist across a process restart, stored via
      `AppMetadataRepository` under a key derived from the folder item id. No
      schema migration.
- [x] AC-9 — `get_kb_status`'s `folders[]` entries carry the two counts,
      additive to the existing `id`/`path`/`status`/`indexed_at`/`error`/
      `watch`/`watch_error` keys.
- [x] AC-10 — The folder panel renders them.
- [x] AC-11 — **Cleanup on both delete paths**: deleting a folder
      (`delete_kb_item`, `api.py:1758`) and deleting a whole knowledge base
      (`delete_knowledge_base`, `api.py:1577`) both remove the corresponding
      keys. A kv key is outside `kb_items`' cascade, so without this the store
      grows forever.
- [x] AC-11a — **`AppMetadataRepository` gains a `delete(key)` method.** It has
      only `get` and `set` today (`repositories.py:1863-1876`); AC-11 cannot be
      satisfied without one. An earlier draft of this leg cited the class as
      existing surface and did not notice the gap.
- [x] AC-11b — **One shared key helper, used by all four call sites** — the
      write site (walk completion), the read site (`get_kb_status`), and both
      cleanup sites. Without it, a cleanup site whose key derivation drifts
      from the write site's deletes nothing while **AC-12's test still
      passes**, because `get()` on the wrong key also returns `None`. That
      false green would silently invalidate the whole no-migration trade.
- [x] AC-12 — A test proves a deleted folder leaves **no** `app_metadata` key
      behind. This is the whole price of avoiding the migration; it is paid
      here or the decision was wrong.

**Ordering (squawk 0087)**

- [x] AC-13 — The three queries at `repositories.py:527,632,640` gain
      **`, path_or_url` ASCENDING** — `ORDER BY created_at, path_or_url`.
      **Not `DESC`.** Squawk 0087's own Corrective Action already commits to
      this and gives the reason: ascending path order is the order the walk
      discovered the files in. The `:1569` / `:2431` precedents establish the
      *pattern* of adding a tiebreak column, **not its direction** — an earlier
      draft of this criterion cited them without that qualifier and would have
      sent a Developer the wrong way.
- [x] AC-14 — A test pins it: insert rows with identical `created_at` and
      assert a stable order across repeated reads.
- [x] AC-14a — **Tighten the browser assertion squawk 0087 was filed against.**
      `tests/browser/test_flow_studio_knowledge_inventory.py`'s nested-folder
      assertions compare rendered relative paths as a **sorted set**, with the
      reason recorded inline, precisely because order was not a contract. Now
      that it is, the comparison becomes a **sequence** and the inline note is
      updated. The squawk's own Corrective Action commits to this; an earlier
      draft of this leg carried the query fix and silently dropped the test
      tightening that motivated filing it.
- [x] AC-15 — Squawk `0087` is updated to `completed` with its Corrective
      Action and Verification filled in. *(Sign-off is written by the Flight
      Director after the flight-end review, not by the implementer.)*

**Vocabulary note (DD-11)**

- [x] AC-16 — A `consumers:` note at the `.mcp-tool-item` comment block
      (`studio.css:173-188`) names every reader of the `mcp-tool-*` vocabulary.
      `knowledge-section.js` borrows it at **two** independent sites —
      `:905` (`buildFolderPanel`) and `:1063` (`buildOtherItemsPanel`) — so the
      note names the file as a consumer, not a single line.
- [x] AC-17 — **No class is renamed.** If the note cannot be written without a
      rename, stop and report — that is the signal the work belongs to the
      component-layer mission, not this leg.

**Gates**

- [x] AC-18 — Every new `data-testid` is registered in
      `docs/ui-testid-registry.md`; `tests/test_ui_guards.py` passes (it
      enforces registry sync in both directions, a dynamic-sink freeze, and
      banned CSS vocabulary).
- [x] AC-19 — `make test-unit` green; the `studio` browser lane green; `ruff
      check` and `ruff format --check` clean.
- [x] AC-20 — Flight log updated, including AC-3's finding and AC-7's
      statement.

## Verification Steps

- AC-1/4/5 — unit-level where possible plus the browser test in AC-6. For AC-5,
  assert the signature is byte-identical across two consecutive `/status`
  responses with no indexing in between.
- AC-2/3 — a unit test against `get_kb_status`; for AC-3, re-index a file whose
  content changed but whose size is identical (edit in place, same byte count)
  and assert the aggregate moves. A same-size edit is the case that falsifies a
  naive `size_bytes`-based aggregate.
- AC-6 — browser test in `tests/browser/test_flow_studio_knowledge_*.py` so it
  falls in the existing `studio` lane glob. Run:
  `PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane studio -x`
- AC-8/11/12 — unit tests against the repositories and the two delete routes.
- AC-13/14 — `tests/` covering `SQLiteKBItemRepository`.
- AC-18 — `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_ui_guards.py -x --timeout 30`
- AC-19 — `make test-unit` verbatim, alone, foreground.

## Implementation Guidance

1. **Land DD-6's two halves together.** Do not commit, push, or mark anything
   done with the freshness field rendered and the signature unwidened. There is
   no intermediate state that is better than the status quo.

2. **Check AC-3 first, before building the aggregate.** The entire decision
   rests on a claim nobody has verified: that a content-only re-index advances
   `indexed_at`. Read `manager.py`'s reconcile/apply path and
   `walk.py::plan_reconcile` (`:186-216`) — note its changed-detection is
   `item.content_hash is not None and (item.size_bytes != disc.size_bytes or
   item.mtime != disc.mtime)`, i.e. it keys on size and mtime, **not** content
   hash. A same-size, same-mtime edit is not detected as changed at all. Decide
   the aggregate against what the pipeline actually does.

3. **Keep the aggregate cheap.** `get_kb_status` is polled every 5 seconds per
   open detail view. One indexed query, not a scan.

4. **The signature must stay stable on a quiet corpus (AC-5).** This is why
   `status.folders[].indexed_at` was rejected as the signal at flight design:
   Flight 6 measured that it advances on every reconcile walk whether or not
   anything changed. Do not reintroduce it as the freshness source.

5. **For skip counters, write at the walk-completion site** that already logs
   them (`manager.py:405-420`) — the values are in hand there.

6. **Cleanup (AC-11) is not optional, and the two paths differ.**
   - `delete_knowledge_base` (`api.py:1577`): enumerate with
     `item_repo.list_folders(kb_id)` **before** `repo.delete(kb_id)` — after it
     there is nothing to enumerate. Note `item_repo` is not currently
     instantiated in that route; it needs to be.
   - `delete_kb_item` (`api.py:1758`): **no enumeration needed.** Folders
     cannot nest — registration rejects a folder overlapping an existing one
     with 409, and only `file` items ever carry a `parent_id` — so the route's
     own `item_id` param is the only key to clear.
   - **Do not reuse the `ids` variable already in scope** at the
     `delete_kb_item` call site. `KBItemRepository.delete(item_id)` returns
     **chunk ids only**, never descendant item or folder ids; it exists there
     for vector-store cleanup. Keying skip-counter cleanup off it would clear
     nothing.
   - Add `AppMetadataRepository.delete(key)` first (AC-11a) — it does not
     exist.

7. **Register every new testid** as you add it, not at the end.
   `tests/test_ui_guards.py` fails in both directions.

8. **`buildFileItemRow` uses `_el(...)` and `textContent`, never HTML strings.**
   The dynamic-sink freeze in `test_ui_guards.py` will fail the build on an
   `innerHTML` sink. If an icon is needed, the sanctioned path is `_appendIcon`
   (`knowledge-section.js:155`), which routes through `DOMParser`.

9. **For DD-11's note, state the direction of the borrow.**
   `knowledge-section.js` sets `details.className = 'mcp-tool-item'` at
   `:905` (`buildFolderPanel`) and again at `:1063` (`buildOtherItemsPanel`) —
   a knowledge-base surface reusing the MCP source-editor's tile vocabulary,
   twice. That is the concrete fact the note exists to make visible; Flight 6
   paid three post-landing passes to defects of exactly that shape.

10. **`_appendIcon` is at `knowledge-section.js:163`**, not `:155` — an earlier
    draft of this leg carried the drifted number.

## Edge Cases

- **Same-size, same-mtime content edit** — per `plan_reconcile`, not detected
  as changed, so nothing re-indexes and no freshness signal should move. The
  UI must not claim freshness the pipeline did not produce. If AC-6's browser
  test edits a file to the same byte length, it will not re-index at all —
  make the fixture edit change the size, or drive the re-index explicitly.
- **An item that has never indexed** (`indexed_at` null) — render something
  honest, not a fabricated timestamp.
- **A folder whose walk has never completed** — no persisted counters yet.
  Render absence, not zero: "not yet walked" and "walked, skipped nothing" are
  different facts.
- **Two re-indexes within one timestamp tick** — if the aggregate is
  timestamp-based, the second may not move it. Note the limitation rather than
  engineering around it.
- **Deleting a knowledge base with many folders** — AC-11's enumeration happens
  before the delete; ensure a failure there cannot abort the delete itself
  (the route's existing shape is log-and-continue after the repository
  transaction).
- **Rows sharing `created_at`** — the AC-13 tiebreak's whole reason; SQLite
  returns them in arbitrary order without it.

## Files Affected

- `the_one/interfaces/web/api.py` — `get_kb_status` aggregate + `folders[]`
  counts; cleanup in both delete routes
- `the_one/knowledge/manager.py` — persist skip counters at walk completion
- `the_one/db/repositories.py` — three `ORDER BY` tiebreaks; new
  `AppMetadataRepository.delete(key)` (AC-11a)
- `the_one/interfaces/web/static/js/areas/studio.js` — widen the signature
- `the_one/interfaces/web/static/js/areas/studio/knowledge-section.js` — item
  freshness render; folder-panel skip counts
- `the_one/interfaces/web/static/css/studio.css` — the `consumers:` note
- `docs/ui-testid-registry.md` — new testids
- `squawks/0087-kb-item-list-order-has-no-tiebreak.md` — status + corrective
  action
- `tests/browser/test_flow_studio_knowledge_inventory.py` — AC-14a's
  set-to-sequence tightening, plus AC-6's freshness round trip
- `tests/` — remaining unit tests
- `missions/24-knowledge-bases/flights/07-mission-close/flight-log.md`

## Citation Audit

Verified against the working tree on `flight/07-mission-close` (2026-09-19),
which carries Leg 1's uncommitted changes. **Design review re-checked every row
and found three drifted line numbers and two substantively wrong rows**; all
five are corrected and marked below. Rows the review confirmed pixel-exact:
`studio.js:480`, `get_kb_status:1805-1841`, and all three
`repositories.py` tiebreak lines.

| Citation | Status |
|---|---|
| `api.py:1805-1841 — get_kb_status` returns `items` (status counts), `folders[]` (`id`/`path`/`status`/`indexed_at`/`error`/`watch`/`watch_error`), `chunks`, `indexer` — no per-item content signal | verified |
| `studio.js:480 — knowledgeItemsSignature(status)` = `JSON.stringify((status && status.items) \|\| {}) + '\|' + (status && status.chunks)`; read at `:589` and `:694` | verified |
| `studio.js:688-694` — the re-fetch is gated on the signature changing, with a comment naming L1-D2's reason for not polling `/items` | verified |
| `knowledge-section.js:841 — buildFileItemRow(item, opts)` renders path, status, optional error, optional standalone badge, item menu — no freshness field | verified |
| `knowledge-section.js:905` **and `:1063`** — `details.className = 'mcp-tool-item'`, the cross-page vocabulary borrow, at TWO sites | verified — **corrected at design review**; the first draft named only `:905` |
| `studio.css:173-188` — the `.mcp-tool-item` comment block and rule | verified |
| `repositories.py:527,632,640` — bare `ORDER BY created_at`; `:1569` and `:2431` carry tiebreaks as house style | verified |
| `repositories.py:1851-1876 — AppMetadataRepository` — `get` and `set` **only**; no `delete` exists (AC-11a) | verified — **corrected**; the first draft cited it as sufficient existing surface |
| `squawks/0087-…md` Corrective Action — `ORDER BY created_at, path_or_url` (ascending) **and** tightening the browser assertion from a set to a sequence (AC-13, AC-14a) | verified — **corrected**; the first draft cited two `DESC` precedents and dropped the test tightening entirely |
| `manager.py:570` — a FILE item's `indexed_at` is stamped by `_flush`'s `update_status(..., "indexed")`, only for re-indexed items; `manager.py:441` — a FOLDER item's is stamped unconditionally every pass (AC-3, guidance 4) | verified |
| `KBItemRepository.delete(item_id)` returns **chunk ids only** — not descendant item ids (guidance 6) | verified |
| `walk.py:49-59 — WalkResult.skipped_dirs/.skipped_entries`; `manager.py:405-420` logs both at walk completion | verified |
| `walk.py:186-216 — plan_reconcile` changed-detection keys on `size_bytes` / `mtime`, **not** `content_hash` — so a same-size same-mtime edit is not detected (AC-3, Edge Cases) | verified |
| `api.py:1577 — delete_knowledge_base` and `:1758 — delete_kb_item` — the two cleanup paths (AC-11) | verified — **line numbers corrected** from `:1585-1600` / `:1780-1802` |
| `knowledge-section.js:163 — _appendIcon` — the sanctioned DOMParser icon path | verified — **line corrected** from `:155` |

---

## Post-Completion Checklist

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed`
- [x] Do **NOT** commit — the Flight Director commits after the flight-end review
- [x] Signal `[HANDOFF:review-needed]`
