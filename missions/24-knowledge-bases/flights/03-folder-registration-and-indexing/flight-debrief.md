# Flight Debrief: Folder Registration and Indexing

**Date**: 2026-09-16
**Flight**: [Folder Registration and Indexing](flight.md)
**Status**: landed → completed at debrief
**Duration**: 2026-09-15 (planning, three Architect cycles, Legs 1–3) – 2026-09-16 (Leg 4 gates and behavior test, HAT waived, landed)
**Legs Completed**: 5 of 5 (Leg 5, the optional HAT, waived by the operator and folded into Flight 6)

Sources: the flight log in full; the five leg artifacts; the Developer
debrief interview (Sonnet, with an independent `make test-unit` run); the
Architect debrief design review (Sonnet); a three-question human interview;
the behavior-test run log; and the Flight Director's orchestration record.
PR #200 is ready for review against `mission/24-knowledge-bases`, not yet
merged.

## Outcome Assessment

### Objectives Achieved

The flight met its objective in full. A knowledge base is now usable from
the API: `POST …/items` with `type: folder` registers a folder with
existence, root and containment validation; a stat-only walk discovers
files under the DD-3 rules and a pure planner classifies them; the
extractor seam (Protocol + suffix-keyed in-tree registry + `TextExtractor`)
feeds `index_item`, which implements Flight 2's write ordering for the first
time (chunks + FTS commit, store delete of old ids, batched embed + upsert,
item `indexed` only after the flush that covers it); `IndexingManager`
runs one event-woken worker per knowledge base with cooperative stop,
manager-owned flush, pass-level stale rebuild and per-pass requeue, so a
restart resumes; and four routes (`status`, `reindex?scope=changed|all`,
`items/{id}/chunks`, `items/{id}/source`) expose it. All of it was proven
by a behavior test that passed 8/8 on its first run — including the
seeded restart-resume — a green unit gate at 4,547 tests, a clean
`pip-audit`, and a frozen Windows build that passed on the first attempt
with the installer up 0.07 %.

Beyond the plan: a real race found and fixed by the Leg 3 Developer
(`request_index` must clear the idle event synchronously before waking the
worker); the DD-12 measurement that priced the flush cadence at 9.09 %
save overhead at 1M vectors on Windows, under the 15 % divert line; and the
mission's `parent_id` and file-skipping open questions resolved.

### Mission Criteria Advanced

| Mission criterion | This flight's contribution |
|---|---|
| Register a folder; see each item's index status including failures | **API half landed**: validated registration, discovery, per-item status and error, the `/status` projection with file-only counts and per-folder walk status. Studio is Flight 6. |
| Additions, modifications, deletions reflected without operator action | **Reconcile walk landed** (proved by the behavior test's edit/add/delete step); the event-driven trigger is Flight 4, which only needs to call `request_index`. |
| Large-folder indexing in the background; resumes rather than restarts | **Landed**: per-KB worker, per-item status as the checkpoint, `indexing → pending` requeue at startup and per pass; behavior-test-backed (seeded strand). |
| Inspect contents; retrieve the source material behind an item | **API half landed**: chunk read-back with exact offsets (proved `text[char_start:char_end] == chunk.text` live) and source read-back with a freshness flag — with one defect, see Technical. |
| New format handler without touching the pipeline | **Landed and pinned by a test**: a `.stub` extractor indexes end to end with `indexer.py` untouched. |
| Upgrades with no data loss; unit gate green; frozen installer builds | **Advanced**: no schema change; gate green; build 608700 `RESULT: PASS`, 134,886,157 bytes. |

## What Went Well

- **Design review earned its cost, and the leg reviews then ran cheap.**
  Three Architect cycles at flight level caught seven high-severity
  state-machine defects before any code existed — the flush-cadence
  inversion, `pending → pending` on folders and then on files, the drain
  that could never terminate, the stale rebuild re-entering the manager
  lock, the cancel-then-flush race against a `to_thread` mutation, the
  `finally` that would set idle mid-restart, and the pending-page
  starvation. With those pinned, each leg's own design review closed in
  one cycle with mediums and lows only. The Architect's read: the
  cross-cutting concurrency rules were front-loaded into DD-5/6/7, and the
  legs paid nothing for them afterwards.
- **The operator's decisions came at the right moments with enough
  context** (human interview). Two design questions surfaced by review
  (the flush trade-off; what `/reindex` means) and the request for a
  third Architect pass were each put as a plain-language choice with a
  recommendation, and the operator confirmed that shape.
- **The behavior test passed first time, on a spec that had been
  premise-audited.** Every verdict rested on evidence files read by the
  Validator, not the Executor's prose; the three-timestamp chain in Steps
  8 and 10 was checked from raw JSON. The premise audit found zero spec
  defects — the flight-planning discipline of auditing act *and* observe
  paths, plus adding the `/status` projection specifically as the test's
  read path, is what made that possible.
- **Flight 2's four contracts were consumed, not rediscovered.** Two-
  transaction ordering with `flush` as "landed", `indexing → pending` as
  the resume primitive, `VectorStoreStaleError → rebuild_from` as the only
  recovery, and the first-index `knowledge.vector_store` record all landed
  as specified — Flight 2's Recommendation 1 worked as an input.
- **Test discipline held at scale.** +116 tests at flat per-test cost;
  one flight test in the fifteen slowest (a deliberate cancel-fallback
  timeout at 1.76 s); every mock-based regression test verified by both
  the flight-end Reviewer and the debrief Developer to fail against the
  pre-fix code; no wall-clock synchronisation in the manager tests.
- **The frozen run was budgeted as a diagnostic and needed no iteration.**
  Flight 2's lesson (per-build venv, `--no-deps`, exit-code checks) is what
  made a first-attempt pass unremarkable.

## What Could Be Improved

### Process

- **Important — an invented bar must be flagged before it is written into
  a DD.** The first flight draft stated a "60 s re-work window" as the
  operator's bar; the operator had never been asked. The Architect showed
  it was incompatible with the overhead cap, and a review cycle went to
  re-asking. Rule: when the Flight Director needs a number the operator
  has not given, ask for it (or label it "Flight Director's proposal") —
  never attribute it.
- **Important — the same defect class recurred across review cycles.**
  The `pending → pending` collision was fixed for folders in cycle 1 and
  reappeared for files in cycle 2; the drain exit condition was fixed in
  cycle 2 and broke again in the cycle-3 rewrite. Both times the fix was
  local when the rule was general. When a review finds a transition-table
  or loop-exit defect, state the general rule in the DD and grep the spec
  for every sibling site before the next pass.
- **Important — HAT legs only where there is a screen** (operator's call
  at the human interview). This flight's HAT was waived at Step 2 because
  nothing in it is visible in the UI. Methodology note for
  `/mission-control:flight`: plan a HAT for flights with an operator-
  visible surface; API-only flights rely on their behavior test and fold
  the walk into the next UI flight's HAT — which is what Flight 6 now
  carries.
- **Minor — "X's cap is the only cap" claims about a different code path
  need a negative test.** DD-8 said the indexer's size cap bounds the
  `/source` response; the route never enforces it (see Technical). A DD
  that relies on a cap enforced elsewhere should carry an AC with the
  negative case, not a cross-reference.
- **Minor — a fresh scratch data directory needs the credential minted
  before `make up`.** The first dev-instance start failed its verify step
  on this; now recorded in the behavior spec's Preconditions.

### Technical

- **Important — `/source` reads an uncapped file.** `get_kb_item_source`
  never checks `MAX_FILE_BYTES` (the constant is not imported in `api.py`),
  so a file the indexer refused at 10 MiB — or any large standalone `file`
  item — is read whole into memory on request. The docstring says the
  opposite. Found by the debrief Developer; missed by three Architect
  cycles, the flight-end Reviewer and the behavior test (which checked
  `big.txt`'s `failed` status but never called `/source` on it). One-line
  fix plus a negative test; squawk-sized; before Flight 5/6 consume the
  route.
- **Minor — `get_vector_store()` still has no shutdown hook.** The
  manager's `drain` is where dirty indexes get saved; a store touched by
  no worker (a KB with a backend but no worker) has no other path to a
  flush at shutdown. Recorded, not fixed; a design question for whoever
  next touches the dispatcher.
- **Minor — `/source` re-extracts the whole file on every call** with no
  caching. Fine for an API; Flight 6 should not call it on every item
  click.
- **Minor — walk skip counters are log-only.** `skipped_dirs` /
  `skipped_entries` would let an operator see why a folder undercounts
  without reading server logs; exposing them on `/status` adds a field
  (a feature, not a squawk) — Flight 6's call.
- **Minor — a standalone `file` item inside a registered folder is
  indexed twice** (recorded in DD-1 as accepted). Flight 6's inventory
  should make the duplication legible.
- **Minor — one concurrency path is untested**: two live workers embedding
  simultaneously against the shared `embed_lock` (the drain test uses
  hand-built entries). Straightforward code; a test would cost little.
- **Minor — the flush cadence is sized against extrapolated Windows
  figures** for the third flight running. The mission now carries the 1M
  re-measure as an open question; the Architect's view is that it should
  become a small maintenance flight once a corpus exists rather than roll
  forward indefinitely.

### Documentation

- Two patterns are now used twice and deserve names in `the_one/agents.md`
  (Recommendation 3): the *supervised-per-entity-worker* shape
  (`ConnectorManager`, `IndexingManager`; Flight 4's watcher will be the
  third) and the *leg-staged hook seam* (`_after_folder_registered`, a
  documented no-op filled by a later leg).
- `CLAUDE.md` says `make up` writes `.the-one.pid`; the Makefile scopes
  the PID file by port (`.the-one.$(THE_ONE_PORT).pid`). Carried in the
  flight log twice; a squawk now.
- The behavior spec's two candidate tightenings (a `realpath` tiebreaker
  for Step 2; an explicit "old chunk ids replaced, not appended" assertion
  after `scope=all`) are recorded in the run log's Operator Notes for the
  next re-author.

## Test Metrics

| Run | Command | Result |
|---|---|---|
| Leg 4 gate (alone, foreground) | `make test-unit` | **4,547 passed / 10 skipped / 578.08 s** |
| Debrief (Developer, alone, foreground) | `make test-unit` | 4,547 passed / 10 skipped / 638.25 s, 0 failures, no flakes |
| Debrief durations run | `run-tests.sh … --durations=15` | 4,547 / 10 / 609.21 s (durations only, not the metric) |

Series, all `make test-unit` alone and foreground: Flight 1 debrief 3,950 /
466.75 s → Flight 2 close 4,370 / 499.22 s → squawk turnaround 4,431 →
Leg 1 4,452 / 523.20 s → Leg 2 4,499 / 517.29 s → Leg 3 4,547 / 548.53 s →
Leg 4 4,547 / 578.08 s → debrief 4,547 / 638.25 s. Net for the flight:
**+116 tests**. The count has been flat at 4,547 since Leg 3, while wall
time on identical counts spread from 548 s to 638 s across four runs —
host-load variance of the kind Flight 2's debrief recorded, not a
regression, but the spread is wider than before: per-test cost has drifted
from ~118 ms (Flight 1) to 127–140 ms. The fifteen slowest are all
pre-existing (`test_mcp_pool.py::test_drain_timeout_handles_stuck_worker`
10.0 s remains the outlier); the only flight entry is the deliberate
cancel-fallback test at 1.76 s. Recommendation: the next debrief runs the
gate on a quiet host and records whether the drift is real.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| The 60 s re-work "bar" replaced by the operator's overhead-cap choice; window recorded as a consequence | The bar was Flight Director-invented; the Architect showed the two could not both hold at the ceiling | Yes — never attribute a number the operator did not give (Rec. 4) |
| `/reindex` defaults to a reconcile walk; `?scope=all` re-embeds | Operator's call at design review; the walk already detects changes | Yes — the route contract |
| Size cap and binary sniff moved from the walk into the indexer | `failed` is reachable only from `indexing`; the walk stays stat-only | Yes — recorded in DD-3/DD-5 and `agents.md` |
| Folder/file requeue only from `indexed`/`failed`; every pass starts with `requeue_stranded` | `pending → pending` raises; runtime resume, not boot-only | Yes — transition-table rule, asserted at call time |
| Manager-owned flush after a cooperative stop; no flush on cancel fallback; `entry.dirty` set before the `to_thread` | A cancelled `await` leaves the mutation thread running | Yes — part of the supervised-worker convention (Rec. 3) |
| Stale catch at pass level; pass restarts after a rebuild | The rebuild would re-enter the manager lock; a direct retry would hit `indexing → indexing` | Yes — `agents.md` Knowledge indexing |
| Drain exits on "no un-attempted ids", with one unlimited fallback read per pass | A stuck row at the head of the page window would spin or starve the drain | Yes |
| `request_index` clears the idle event synchronously (Developer-found) | `request_index(); await wait_until_idle()` raced a not-yet-scheduled task | Yes — the manager docstring records it |
| A third Architect pass past the max-2 rule | Operator's call; each pass had found highs in the previous pass's rewrites | Case by case — the escalation fired correctly; the operator chose verification over speed |
| HAT waived at Step 2 | No UI surface in this flight | Yes — HAT only where there is a screen (Rec. 5) |
| Routes kept in Leg 3 rather than split | Per-leg review closed in one cycle; the split was never needed | n/a |

## Key Learnings

1. **Front-load the cross-cutting state-machine rules at flight level;
   the legs then review cheaply.** Three flight-level cycles, then three
   one-cycle leg reviews — the cost moved to where the defects were.
2. **A local fix to a general rule comes back in the next rewrite.**
   Twice this flight. Write the rule, then sweep the spec.
3. **The behavior test's read path is a design decision.** `/status` was
   added for the test to observe through; the test then passed first time
   and never needed the database. Observability designed in beats a
   test-only seam added under pressure.
4. **What the behavior test did not call, it did not prove.** `big.txt`
   was checked for `failed` but never through `/source`, and that is where
   the flight's one real defect sits. A spec should exercise every route
   it names at least once, including on the failure fixture.
5. **Timing evidence from a small fixture is thin.** Every wait point
   resolved on the first poll, so the run observed terminal states only.
   The live-kill variant is the way to watch a transition; keep it as a
   variant, not the default.
6. **The supervised-per-entity worker is a house shape now.** Two
   instances with the same edge cases (cooperative stop, cancel fallback,
   idle race, concurrent drain within a budget); a third is coming.

## Recommendations

1. **Fix the `/source` cap before Flight 5 or 6 consume the route**
   (squawk): refuse a file over `MAX_FILE_BYTES` with a 413 naming the
   cap, and add the negative test the behavior spec lacks (call `/source`
   on the over-cap fixture). Correct the route docstring.
2. **Flight 4's watcher must be a trigger, not a second source of truth**:
   debounce filesystem events into one `request_index` per settle window;
   subscribe with the same dot-prefix and `SKIPPED_DIRS` rules as the walk;
   never classify file state itself; respect the lock order (never acquire
   the manager lock while holding the write lock). The walk remains
   correctness; the watcher is latency.
3. **Name two conventions in `the_one/agents.md`** (squawk):
   *supervised-per-entity-worker* (dict of entities → task + wake + idle +
   stop flag; `start`/`request`/`stop`/`drain`/`state`; module accessor
   pair; lifespan-wired; cooperative stop with cancel fallback; idle set
   only on normal completion; concurrent drain under a stated budget) and
   *leg-staged hook seam* (a documented no-op filled by a later leg, so an
   early leg never imports a later leg's module). Add the house rule that a
   DD relying on a cap enforced elsewhere carries a negative-test AC.
4. **Methodology: a Flight Director never attributes a number to the
   operator.** An unasked bar is labelled as a proposal and put as a
   question at the checkpoint, the way the flush trade-off eventually was.
5. **Methodology: plan HAT legs only for flights with an operator-visible
   surface** (operator's call). API-only flights are accepted by their
   behavior test; their walk is folded into the next UI flight's HAT.
6. **Flight 5's fusion design takes three inputs from this flight**: the
   two crash-window consequences (FTS ahead of vectors for an `indexing`
   item; a saved sidecar holding ids of replaced chunks until the next
   flush) as normal operating conditions, and filtering or flagging chunks
   of non-`indexed` items. Squawk 0054's bounds on `search_keyword` and the
   dim guard are already in.
7. **Decide the Windows 1M re-measure's vehicle** rather than rolling it
   forward a fourth time: a small maintenance flight once a real corpus
   exists, with the flush constants re-checked against the number.

## Action Items

- [ ] `/source`: enforce `MAX_FILE_BYTES` (413), fix the docstring, add the negative test — **squawk 0063** (defect, routine; before Flight 5).
- [ ] `CLAUDE.md`: `make up` writes `.the-one.$(THE_ONE_PORT).pid`, not `.the-one.pid` — **squawk 0064** (servicing, routine).
- [ ] `the_one/agents.md`: the two named conventions and the negative-test-for-remote-cap rule — **squawk 0065** (servicing, routine).
- [ ] Test: two live workers embedding concurrently through the shared `embed_lock` — **squawk 0066** (servicing, routine).
- [ ] Carry into Flight 4 planning: Recommendation 2.
- [ ] Carry into Flight 5 planning: Recommendation 6.
- [ ] Carry into Flight 6 planning: the waived HAT steps (already on the mission bullet); expose walk skip counters on `/status`; make standalone-inside-folder duplication legible; do not call `/source` per click.
- [ ] Mission: decide the vehicle for the Windows 1M re-measure (Recommendation 7).
- [ ] Merge PR #200 into `mission/24-knowledge-bases`.
- [ ] Still open from earlier debriefs: whether `.flightops/ARTIFACTS.md` documents the mission-branch layer.
