# Flight Log: Mission Close

**Flight**: [Mission Close](flight.md)

## Summary

Planning began 2026-09-19, immediately after Flight 6's debrief. Not yet in
flight.

---

## Reconnaissance Report

Per `/mission-control:flight` Phase 1b. Source artifacts: the Flight 6 debrief
(Recommendations + Action Items), Flight 6's `flight.md` DD-1 and Deferred
Scope, Flight 6's own reconnaissance rows R8/R12–R20, the mission's Open
Questions and Known Issues, and the open squawk log. Verified against the
working tree at **`7965246`** on 2026-09-19.

| Item | Source | Classification | Evidence | Recommendation |
|---|---|---|---|---|
| R12 — Windows 1M `usearch` re-measure | mission open Q; F4 DD-12; F6 DD-1 | `confirmed-live` | `scripts/bench_vector_store.py:837-861` already parameterises `--corpus`/`--cells`/`--seed` and forks a child per cell for clean `peak_rss_MB`. The apparatus exists; only the run does not. `ci/README.md:78` gives the ad-hoc worker pattern | In scope — Leg 3, as a staged ladder (DD-5) |
| R13 — "Large-folder settle" behavior-test variant | F4 debrief Rec. 3 | `confirmed-live`, **cheaper than the source states** | `tests/behavior/kb-folder-index-round-trip.md:99` already carries a `live-kill` variant that generates 2,000 × 50 KB files. The fixture generator is written; the settle variant reuses it rather than authoring one | In scope — Leg 4 |
| R14 — `get_vector_store()` has no shutdown hook | mission Known Issues; F4 debrief Rec. 5 | `confirmed-live` | `the_one/vectors/__init__.py:70` caches `_store` process-wide; `grep get_vector_store the_one/interfaces/web/app.py` → **0 hits**. `UsearchStore.close` (`:486`) and `.flush` (`:407`) both exist, so the hook has something to call | In scope — Leg 1 (DD-3) |
| R15 — shared `the_one/tools/naming.py` | F5 debrief #7; F6 DD-1 | `confirmed-live` | `_TOOL_NAME_MAX_LEN = 64` still duplicated at `mcp/_tool.py:39` and `knowledge/tool_provider.py:61`; `the_one/tools/naming.py` absent | **Out of scope — DD-2.** Its own stated trigger ("before a third prefixed namespace") has not fired. Deferred with that trigger recorded |
| R20 — recall/precision benchmark for `RRF_K`, `candidate_k`, DD-12 | F5 debrief #13 | `confirmed-live`, **with a gap the source item did not state** | `retrieval.py:93` `RRF_K = 60`, `:160 _candidate_k`, `:112 SEMANTIC_QUERY_TIMEOUT = 2.0`, reserved slot `:220-233`. The source asks for "recall/precision", which needs query→document judgments that **do not exist anywhere in the tree**. `bench_vector_store.py`'s `recall@k` is *vector* recall against brute-force neighbours — a different measurement entirely | In scope as a **sensitivity sweep**, not a relevance benchmark — DD-4 |
| R8 — walk skip counters on `/status` | F3 debrief action item; F6 Deferred Scope | `partially-satisfied` — **F6's deferral premise is false** | F6 deferred it saying "nothing in the pipeline accumulates them today, so the walk would have to count and persist per-pass skip totals." The walk **already counts**: `WalkResult.skipped_dirs`/`.skipped_entries` (`walk.py:58-59`), incremented at nine sites through `:106-152`; `manager.py:412` already logs both per pass. Missing work is persistence + projection only | In scope — Leg 2a (DD-7). Reclassified on evidence, not preference. Persists via `AppMetadataRepository`, no migration |
| F6 Rec. 2 — per-item freshness + signature widening | F6 debrief | `confirmed-live` | `studio.js:480 knowledgeItemsSignature` still `JSON.stringify(status.items) + '\|' + status.chunks`; read at `:589`, `:694`. `GET /items` already returns `indexed_at`/`content_hash`/`size_bytes`/`mtime`, discarded client-side | In scope — Leg 2a, both halves in one commit (DD-6). ⚠️ Architect correction: the signature half needs a `get_kb_status` aggregate — `/status` carries no per-item content signal, so it is **not** client-only |
| F6 Rec. 4 — DD-17's free reconcile for detach → rename → reattach | F6 debrief | `confirmed-live` | `tool_provider.py:117 compute_tool_names` — the discriminator is unconditional (verified in control flow). ⚠️ **This row's original evidence quoted the docstring's "independent of the composition of the set" claim, which the Architect falsified**: `_HASH_LENGTHS = (8, 12, 16)` (`:72`) and the widening loop at `:181-200` make the discriminator's *width* set-dependent. The decision survives; the matching rule changed | In scope — Leg 1 (DD-13) |
| F6 Rec. 5 — PUT/PATCH preserve-on-omit protocol | F6 debrief | `confirmed-live`, **out of scope** | `api.py::update_agent` carries three preserve-on-omit cases and no `mcp_source_ids` clause (squawk 0080, live data loss) | **Escalate — DD-12.** Every form in the app; fails flight sizing. Named with a vehicle rather than folded in |
| F6 Rec. 6 — component layer | F6 debrief; issue #207 | `confirmed-live` | — | Mission, not a leg. **Interim only** — ⚠️ but "the trio" is **24** class names across 6 source + 4 test files; DD-11 re-opened for the operator |
| squawk 0087 — no `ORDER BY` tiebreak | squawk log | `confirmed-live` | `repositories.py:527,632,640` bare `ORDER BY created_at`. **In-file precedent exists**: `:1569` (`, id DESC`) and `:2431` (`, identifier DESC`) already do it — the fix has a house style to match rather than invent | In scope — Leg 2a |
| squawk 0088 — armed-confirm invariant unpinned | squawk log | `confirmed-live` | Nothing pins the invariant the folder-delete confirm rests on | In scope — Leg 2b |
| squawk 0083 — `anyio` CVEs | squawk log | `confirmed-live` | `uv.lock:66-67` still `anyio-4.13.0`; two advisories fixed in 4.14.2 | **Prerequisite, squawk path** — DD-9. Blocks Leg 4's `pip-audit` and must precede the frozen build |
| squawk 0050 — `kb_ids` clobber | squawk log; F6 debrief action item | `already-satisfied in code`, **open as an artifact** | Fixed and regression-netted in Flight 6 (behavior test + HAT), but `squawks/0050-…md` has status `open` and an **empty Corrective Action section** | **Prerequisite, squawk path** — DD-9. Write-up + independent sign-off, no code change |
| F6 debrief Action — reconcile Completion Checklist to leg owners | F6 debrief Rec. 3 | `confirmed-live` | Two unowned items went unexecuted in Flight 6 | Applied: every Post-Flight checklist item in `flight.md` names a leg owner |
| F6 debrief Action — `revertMs` / confirm window | F6 debrief; HAT | `confirmed-live` | `confirm.js::App.confirmDelete`, `revertMs` default 3000, ~~six~~ ⚠️ **13 call sites across 8 files** — this row copied "six" from the F6 debrief; corrected after the Architect re-counted. Failed the squawk gate on "no design decisions" and "bounded blast radius" | In scope — Leg 2b as a **leg-level open question** (DD-8), not a pre-decided fix |
| squawks 0052, 0053, 0079 | squawk log | `confirmed-live`, unrelated surfaces | MCP argument coercion; Ollama provider UI; a methodology-artifact template | Out of scope — not Mission 24 work. Carried on the squawk log |
| squawks 0080, 0081, 0082, 0085 | squawk log | `deferred` / `open`, unrelated or escalated | 0080 escalates with DD-12; 0081/0082 deferred in Flight 6; 0085 is the asset cache-busting defect | Out of scope. 0085 in particular is a dev-ergonomics defect, not a mission obligation |

### Two reconnaissance corrections worth naming

Both are cases where a source artifact's stated reason did not survive being
checked, and both would have been carried forward unexamined if the recon pass
had trusted the prose:

1. **R8 was deferred on a false premise.** Flight 6 recorded that the walk does
   not count skips. It does, at nine sites, and has since Flight 3 — the
   counters are even already logged. The item was scoped as pipeline
   instrumentation when it is persistence and projection. It comes into this
   flight because the reason for excluding it is not true, not because the
   flight wanted more work.
2. **R20 asks for something that cannot be built as specified.** "Recall and
   precision" requires relevance judgments; the tree has none and the flight
   would have had to manufacture them. The existing `recall@k` in the bench
   script is a different measurement against a different ground truth, and is
   close enough in name to have been mistaken for the thing being asked for.
   DD-4 replaces the measurement with one that can actually be taken, and
   states in the decision itself what that measurement cannot conclude.

A third, smaller: **R13 is cheaper than its source implies** — the 2,000-file
fixture it needs is already written into the neighbouring spec's `live-kill`
variant.

**A fourth correction, found at design review rather than by this pass**: the
recon table above marked the `confirm.js` row `confirmed-live` on the strength
of the Flight 6 debrief's own figure and did not re-count. It was wrong by more
than 2×. Recorded here because the recon pass's whole purpose is to distrust
source-artifact prose, and on this one row it trusted it. See Design Review
below.

---

## Decisions

### Flight scoped as one closing flight over four risk domains
**Context**: Flight 6's DD-1 named a Flight 7 of R12/R13/R14/R15/R20. The
Flight 6 debrief then added the UI cluster, the spec re-author and the unowned
gates — and dropped R15's urgency by never triggering it.
**Decision**: one flight, four domains, R15 dropped with a recorded trigger
(DD-1, DD-2). Operator's call, 2026-09-19.
**Impact**: one review gate over four domains, mitigated by drawing leg
boundaries on the domain lines so the Reviewer reads four coherent diffs.

### The Windows re-measure runs as a ladder, not a single point
**Context**: the mission open question reads "re-measure at 1M," but the
underlying claim is that a Windows/Linux penalty ratio measured at 200k is
N-independent.
**Decision**: 200k → 500k → 1M with an early-stop checkpoint (DD-5).
**Impact**: the flight can falsify the assumption without a multi-hour hold on
a shared, uncontainerised worker that the installer lane also needs.

### Two squawks become prerequisites rather than legs
**Context**: squawk 0083 blocks `pip-audit`; squawk 0050 is fixed in code but
its artifact is empty and `open`.
**Decision**: both clear on the squawk path before the gates leg runs (DD-9).
**Impact**: a squawk's sign-off is what closes a squawk — routing them through
legs would produce worse records and a larger flight.

---

## Leg Progress

### `non-ui-defect-closure` (Leg 1)
**Status**: landed
**Started**: 2026-09-19
**Completed**: 2026-09-19

#### Changes Made

**Shutdown hook (DD-3/DD-3a)**:
- `the_one/vectors/__init__.py`: added `close_vector_store(*, skip_kb_ids=frozenset())`,
  exported in `__all__`. Never calls `get_vector_store()` — no-ops when
  `_store is None`. Shares a new `_clear_cache()` helper with
  `_reset_for_test()`. Logs each skipped `kb_id` at WARNING.
- `the_one/vectors/usearch_store.py` / `the_one/vectors/_store.py`:
  `UsearchStore.close()` (and the `VectorStore` Protocol) gained a
  keyword-only `skip_kb_ids` parameter, defaulted to `frozenset()` — every
  pre-existing caller is unaffected.
- `the_one/knowledge/manager.py`: `IndexingManager` gained a
  manager-level `self._cancel_report: dict[str, bool]`, written at one
  symmetric site inside `stop()` (`self._cancel_report[kb_id] = cancelled`
  unconditionally, every call — overwritten, never accumulated) and read
  through the new `cancelled_kb_ids() -> frozenset[str]` method. Lives
  outside `self._entries`, so it survives `drain()`'s
  `self._entries.clear()`. No change to `stop()`'s or `drain()`'s
  signature or return type.
- `the_one/interfaces/web/app.py`: the lifespan's shutdown branch captures
  `_indexing_manager.cancelled_kb_ids()` into a local INSIDE the
  `if _indexing_manager is not None:` block, immediately after `drain()`
  and BEFORE the block's own null-out of the module accessor and the
  local. `close_vector_store(skip_kb_ids=_cancel_report_kb_ids)` is then
  called unconditionally, between that block and `close_connection()`.

**Stale-name reconcile (DD-13)**:
- `the_one/agent/factory.py`: added `_kb_tool_is_disabled(tool,
  disabled_tools)`, called only at the `kb_tools` registration loop in
  place of `config.is_tool_enabled(tool.name)` — exact-name match, plus a
  discriminator-suffix match against `tool.kb_id` tried at every
  `_HASH_LENGTHS` width (8, 12, 16), never parsing the slug. Reads
  `config.disabled_tools`; never mutates it. `is_tool_enabled` itself is
  untouched.

#### Notes

**AC-7a falsification, observed**: temporarily changed the lifespan to
capture `cancelled_kb_ids()` AFTER the null-out (reading `None` instead).
`tests/test_mcp_pool.py::test_lifespan_shutdown_threads_real_cancel_report_into_vector_hook`
failed exactly as intended — `close_vector_store` received `frozenset()`
instead of the fake manager's recorded `{"kb-cancelled-during-drain"}`.
Reverted; test green again.

**AC-4c falsification, observed**: temporarily added
`self._cancel_report.clear()` to `drain()` (simulating the
entry-scoped-field bug the criterion guards against).
`tests/test_kb_manager.py::TestDrain::test_cancel_report_survives_the_real_drain`
failed exactly as intended — `cancelled_kb_ids()` came back empty after a
real `drain()` instead of `{"kb1"}`. Reverted; test green again.

**AC-16 falsification, observed**: temporarily reverted the `kb_tools`
loop to plain `config.is_tool_enabled(tool.name)` (no reconcile).
`tests/test_factory_disable_enforcement.py::TestKbToolStaleDisableReconcile::test_disabled_kb_tool_survives_detach_rename_reattach`
failed exactly as intended — the renamed knowledge base's new tool name
(`kb__Renamed_Knowledge_Base_ef7a30aa__search`) leaked into the rebuilt
agent's registry despite the stale `disabled_tools` entry. Reverted; test
green again. The test drives a real `KBToolProvider` against a real
SQLite connection (`_build_factory`'s existing patch idiom) with a
knowledge base whose `name` genuinely differs between the pre-rename and
post-rename `AgentFactory.create()` calls — not
`StubProviderWithKbTool`, whose fixed tool name cannot reproduce a
rename.

**Reviewer-relevant**: neither defect is observable through any product
surface — no UI or route reports a vector-store flush, and no Studio
surface renders a `kb__` toggle. Both are pinned entirely by the unit
tests above; a Reviewer must judge this leg on test evidence, not a
demonstrable behaviour change.

**Test files touched**: `tests/test_vector_store_shutdown.py` (new, 8
tests: AC-1/2/3/8/9/10), `tests/test_kb_manager.py` (2 new tests in
`TestCooperativeStopAndCancelFallback`/`TestDrain`: AC-4/4a/4b, AC-4c),
`tests/test_mcp_pool.py` (extended `test_lifespan_shutdown_drain_order`
for AC-7 and added
`test_lifespan_shutdown_threads_real_cancel_report_into_vector_hook` for
AC-7a), `tests/test_factory_disable_enforcement.py` (10 new tests across
`TestKbToolStaleDisableReconcile` and `TestKbToolIsDisabledHelper`:
AC-11–AC-17).

**Documentation**: `the_one/agents.md` gained "DD-13" and "Vector-store
shutdown hook" blocks (Knowledge indexing section) plus an addendum to
the `IndexingManager` module-accessor bullet; `CLAUDE.md` gained a short
M24 F7 L1 paragraph pointing to both.

**No divert trigger fired**: `IndexingManager.stop()`/`drain()` kept
their existing signatures and return types (`-> None` throughout) — only
a new constructor field and a new read-only accessor method were added.

**AC-18 gate**: `ruff check the_one/ tests/ scripts/` and `ruff format
--check the_one/ tests/ scripts/` both clean. `make test-unit` run twice:
first pass — 4789 passed, 10 skipped, 594 deselected, **1 failed**
(`TestSquawk0005ShutdownDrainUnderLoad::test_live_surface_connection_evicted_before_general_drain`,
`MCPConnectionError: MCP server did not respond within 30 seconds during
initialize` — a live-subprocess MCP connect starved by CPU contention
from the rest of the full suite running concurrently, in a file/test this
leg never touches). Re-ran that one test in isolation — passed in 1.02s.
Re-ran the full `make test-unit` a second time, alone — **4790 passed, 10
skipped, 594 deselected, 0 failed**, confirming the first failure was a
load-induced flake, not a regression from this leg's changes.

### `inventory-freshness` (Leg 2a)
**Status**: landed
**Started**: 2026-09-19
**Completed**: 2026-09-19

#### Changes Made

**Freshness + signature (DD-6) — one commit, both halves together (AC-1–AC-7)**:
- `the_one/db/repositories.py`: `KBItemRepository` gained
  `latest_indexed_at(kb_id, *, type=None)` — `MAX(indexed_at)`, one
  indexed query on `idx_kb_items_kb_id`.
- `the_one/interfaces/web/api.py::get_kb_status`: gained the top-level
  `"content_freshness"` key (`latest_indexed_at(kb_id, type="file")`) —
  additive; no existing key touched.
- `the_one/interfaces/web/static/js/areas/studio.js::knowledgeItemsSignature`:
  widened to `items | chunks | content_freshness`.
- `the_one/interfaces/web/static/js/areas/studio/knowledge-section.js::buildFileItemRow`:
  renders `Indexed: {indexed_at}` (`data-testid="kb-item-indexed-at"`,
  `content_hash` as the hover title), only when `indexed_at` is set.

**Walk skip counters (DD-7, AC-8–AC-12)**:
- `the_one/knowledge/settings.py`: added `walk_skip_counters_key(folder_item_id)`
  — the one shared key helper (AC-11b), `"knowledge.walk_skips.{id}"`.
- `the_one/db/repositories.py::AppMetadataRepository`: added `delete(key)`
  (AC-11a — did not exist before this leg).
- `the_one/knowledge/manager.py::_walk_one_folder`: persists
  `{"skipped_dirs", "skipped_entries"}` via `AppMetadataRepository` right
  after a walk completes, through the shared key helper.
- `the_one/interfaces/web/api.py::get_kb_status`: each `folders[]` entry
  gained `"skipped_dirs"`/`"skipped_entries"` (both `None` for a folder
  never walked — absence, not a fabricated zero).
- `the_one/interfaces/web/api.py::delete_kb_item`: a `folder`-type delete
  clears its own skip-counter key (no enumeration — folders cannot nest,
  and `KBItemRepository.delete`'s return is chunk ids only, never reused
  for this).
- `the_one/interfaces/web/api.py::delete_knowledge_base`: now instantiates
  `item_repo`, enumerates `list_folders(kb_id)` **before** `repo.delete`,
  and clears every enumerated folder's key after (log-and-continue, same
  shape as the existing vector-store cleanup).
- `the_one/interfaces/web/static/js/areas/studio/knowledge-section.js::updateFolderMeta`:
  renders `Skipped: N dirs, M entries` (`data-testid="kb-folder-skip-counts"`)
  only when both counts are non-null.

**Ordering (squawk 0087, AC-13/AC-14/AC-14a)**:
- `the_one/db/repositories.py`: `KBItemRepository.list`/`.list_children`/
  `.list_folders` all gained `, path_or_url` **ascending** (matching
  `walk_folder`'s own path sort — not the two in-file `DESC` precedents,
  which are a different "most recent first" case).
- `tests/browser/test_flow_studio_knowledge_inventory.py`: the
  nested-folder assertion tightened from a sorted-set comparison to an
  exact ordered sequence, inline comment updated to say order is now a
  contract.
- `squawks/0087-kb-item-list-order-has-no-tiebreak.md`: `Corrective
  Action`/`Verification` filled in, status set `completed`. Sign-Off left
  `(pending)` for the Flight Director per this leg's brief.

**Vocabulary note (DD-11, AC-16/AC-17)**:
- `the_one/interfaces/web/static/css/studio.css`: added a `consumers:`
  note above `.mcp-tool-item`, naming all six reader files and both
  `knowledge-section.js` borrow sites (`buildFolderPanel` `:905`,
  `buildOtherItemsPanel` `:1063`). No class renamed.

#### Notes

**AC-3, confirmed by reading the code, not assumed**: a FILE item's
`indexed_at` is stamped only by `KBItemRepository.update_status`'s
transition into `"indexed"` (`manager.py::_flush` is the only production
caller of that transition for a file item), which runs only for an item
actually re-queued and re-indexed. A FOLDER item's `indexed_at` is stamped
unconditionally on every completed walk (`_walk_one_folder`), changed or
not — confirmed by reading that method directly, and this is exactly why
Implementation Guidance forbade using it as the freshness source. AC-2 and
AC-5 are satisfiable **together** for this reason: `MAX(indexed_at)` over
`type='file'` items advances iff something re-indexed, and holds steady
on a quiet corpus. Verified with a unit test
(`TestKnowledgeBaseContentFreshness::test_folder_indexed_at_never_moves_the_aggregate`)
that drives a FOLDER item through the same `indexed` transition and
asserts `content_freshness` does not move.

**AC-7, stated explicitly**: the freshness-field render and the
`knowledgeItemsSignature` widening were never committed, tested, or
reported as done separately — both landed in this single leg pass. There
is no intermediate git state (and, since this flight defers commit to the
flight-end review, no intermediate commit either) where the render exists
without the signature change.

**AC-20 trade-offs, noted**:
- The walk-skip-counter kv record (DD-7) trades a v42 schema migration for
  an explicit-cleanup obligation on two delete paths. AC-11b's shared-key
  helper is the mitigation the design review specifically called out as
  necessary to avoid a false-green cleanup test; both cleanup sites and
  the read site import the same `walk_skip_counters_key` function — there
  is no second implementation of the key format anywhere.
- The freshness aggregate is honest about `plan_reconcile`'s own
  limitation (Edge Cases): a same-size, same-mtime content edit is not
  detected as changed by the walk pipeline at all, so `content_freshness`
  correctly does *not* move for that case — this is a pre-existing
  pipeline limitation, not something this leg's aggregate choice could or
  should paper over. AC-6's browser fixture deliberately edits the file to
  a different size so the round trip it proves is the one the pipeline
  actually supports.
- DD-11's comment-only resolution leaves 24 `mcp-tool-*` class names
  un-renamed; the `consumers:` note trades the rename's cost for
  visibility of the borrow, per the operator's re-decision recorded in the
  flight's DD-11.

**Test files touched**: `tests/test_db_repositories.py` (new
`TestKBItemRepositoryOrdering` — AC-13/AC-14; three new tests on
`TestAppMetadataRepository` — AC-11a), `tests/test_db_api.py` (new
`TestKnowledgeBaseContentFreshness` — AC-2/AC-3/AC-5; new
`TestKnowledgeBaseWalkSkipCounters` — AC-8/AC-9/AC-11/AC-12; two existing
`TestKnowledgeBaseStatusRoute` tests updated for the two new additive
`folders[]` keys), `tests/test_kb_manager.py` (`test_folder_fixture_indexes_every_file`
extended for AC-8's zero-skip case; new
`test_walk_skip_counters_persist_a_real_skip` for the non-zero case),
`tests/browser/test_flow_studio_knowledge_inventory.py` (AC-14a's
sequence tightening; new `test_content_only_edit_updates_item_freshness_with_no_reload`
for AC-6 — a real folder, a real on-disk edit, no reload, only the 5-second
poll).

**New testids**: `kb-item-indexed-at`, `kb-folder-skip-counts` — both
registered in `docs/ui-testid-registry.md`.

**Documentation**: `the_one/agents.md`'s "Route wiring" bullet (Knowledge
storage section) gained a "`get_kb_status` gains two ADDITIVE signals"
block covering `content_freshness`, the skip-counter kv contract and its
shared-key-helper discipline, and squawk 0087's fix.

**No divert trigger fired**: no schema migration was needed anywhere in
this leg — DD-7's whole premise (`app_metadata` kv, no v42 migration) held.

**Gate results**: `ruff check`/`ruff format --check` clean on every
touched file. `PYTHON=.venv/bin/python bash scripts/run-tests.sh
tests/test_db_repositories.py -x --timeout 30` — 212 passed.
`PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_db_api.py -x
--timeout 60` — 181 passed. `PYTHON=.venv/bin/python bash
scripts/run-tests.sh tests/test_kb_manager.py -x --timeout 120` — 27
passed. `PYTHON=.venv/bin/python bash scripts/run-tests.sh
tests/test_ui_guards.py -x --timeout 30` — 14 passed. Full `studio`
browser lane (`PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane
studio -x`) — **178 passed, 3 skipped**, 391s. `make test-unit` run at
leg-end, verbatim, alone, foreground — **4807 passed, 10 skipped, 595
deselected, 0 failed** in 622.93s (0:10:22).

---

## Deviations

*(none yet)*

---

## Anomalies

*(none yet)*

---

## Flight Director Notes

**Planning, 2026-09-19.** Phase 1b recon walked 19 source items across five
artifacts. Two classifications came back contradicting their source's stated
reason (R8, R20) and one came back cheaper than stated (R13); all three are
recorded above rather than silently acted on, because in each case the flight's
scope changed on the correction.

Four decisions were put to the operator rather than assumed, each because the
answer changed what gets built: the flight's scope shape, the Windows worker's
availability and run shape, R20's ground truth, and R8's inclusion. A fifth —
the confirm-window fix — was deliberately **not** decided at planning: the
operator's instruction was to investigate first, and DD-8 records that as a
leg-level open question rather than manufacturing a flight-level decision to
look complete. A flight spec that pre-decides a question it was told to
investigate has not resolved the question, only moved where it will be
rediscovered.

DD-12 is the flight saying no. Recommendation 5 is correct and squawk 0080 is
live data loss today, and neither fact makes it this flight's work — it is a
request-protocol change across every form in the app. The debrief's own
instruction was "do not let squawk 0080 be filed a third time in a third form,"
which is honoured by naming a vehicle, not by folding it into a closing flight
whose review gate is already carrying four domains.

## Design Review

### Architect cycle 1 — 2026-09-19

**Verdict**: approve with changes. All incorporated.

Re-checked 15 of the Citation Audit's 19 rows independently and found **one
outright failure, one verified-but-misleading row, and one drifted line
number**.

**The failure is the Flight Director's**, and is recorded rather than quietly
patched: the audit row for `App.confirmDelete` read "six call sites" and was
stamped `verified`. The real count is **13, across 8 files**. The figure was
copied from the Flight 6 debrief (`flight-debrief.md:281`) and marked verified
without being re-counted — which is precisely the defect class the Citation
Audit exists to catch. It changes the plan materially: the confirm fix crosses
four browser lanes rather than one, and it reaches
`areas/admin/system-page.js:81`, the API-credential rotation confirm, which is
the highest-consequence confirm in the app. Re-counted independently before
acting on the finding.

Six further substantive findings, all incorporated:

1. **DD-6's cost estimate was false.** It called the work "a render + signature
   change, not a data change." `get_kb_status` (`api.py:1805-1841`) carries no
   per-item content signal, so the signature — computed from `/status` — cannot
   be widened client-side to see a content-only edit. The *coupling* argument
   the decision rests on is correct and the Architect independently confirmed
   it; the cost was wrong. Resolved with a freshness aggregate on
   `get_kb_status`, so Leg 2a touches Python.
2. **DD-3 had one ordering bound where it needed two**, and a torn-save hazard
   it did not see. The hook must land after `_indexing_manager.drain()` **and
   before** `close_connection()`, because `flush()` writes through the
   connection. More seriously: `IndexingManager.stop()`'s cancel fallback
   releases `entry.lock` while a worker thread is still mutating the index
   (`manager.py:242-243` says so in its own comment), so a hook running
   straight afterwards would `index.save` concurrently with a live mutation.
   Closed as **DD-3a** — the manager surfaces which knowledge bases took the
   cancel fallback and the hook skips exactly those, logging each. The finding
   also produced a *better* rationale for the hook than the spec had: the drain
   leaves the store dirty on two paths, so the hook is load-bearing rather than
   defensive.
3. **DD-13's matching rule was falsified** (the Flight Director flagged this
   as the most likely falsification when spawning the review, and it landed).
   `_HASH_LENGTHS = (8, 12, 16)` with a real widening loop at `:181-200`, so the
   discriminator's *width* is set-composition-dependent — contradicting the
   docstring the audit row quoted as if it were control flow. The decision
   survives; the rule now iterates `_HASH_LENGTHS`. Separately, the reconcile's
   seam is `agent/factory.py:423`, not `KBToolProvider`, which never consults
   `disabled_tools` at all.
4. **DD-11's premise was wrong.** "The trio" is **24** `mcp-tool-*` class names
   across 6 source and 4 test files. A 3-of-24 rename is the one option DD-11's
   own rationale forbids. Re-opened for the operator rather than silently
   changed — the original was a real operator decision made against a number
   that turned out to be false.
5. **DD-5 tested the wrong claim.** Three Windows rungs test whether Windows
   cost is linear in N, not an N-independent Windows/Linux *ratio*. Narrowed
   the claim explicitly and recorded why the ratio does not matter: Flight 3's
   flush cadence rests on absolute Windows figures, and the ratio was only ever
   the means of producing them.
6. **DD-10 was looking one layer too high.** The bench records
   `usearch_version` but nothing about SIMD or numkong linkage — and Flight 1's
   log records that `usearch` *swallows its own numkong `ImportError`*, so a
   missing backend still imports and still prints a clean `OK`. A fresh
   per-run venv, DD-10's own remedy, is exactly where that could enter
   unnoticed. The bench task now emits the resolved backend.

Two structural findings also incorporated: **Leg 2 is not viable unsplit**, and
the seam the spec pre-authorised was wrong — it grouped DD-8 and DD-11 as
"shared-helper work" when they share only the adjective. Split into 2a
(decided, one lane) and 2b (undecided design, four lanes) as a **mandatory**
boundary. And the **Concourse worker prerequisite** needed a per-leg re-verify
rather than a planning-time confirmation, since the `fly` login expires and the
worker is shared.

Smaller corrections: `CURRENT_VERSION` is already **41**, so a new migration
would be v42 — and `AppMetadataRepository` (schema v31) makes DD-7's
persistence free of any migration at all, an option the Adaptation Criteria's
binary had omitted. Checkpoint 1's second clause was unreachable
(`IndexingManager.start_all` builds a store on first launch with zero knowledge
bases), reworded to the invariant actually wanted: *the hook never builds a
store*. DD-3's idempotency hazard was mis-stated (a second `close()` is a
no-op unless the first flush failed) — criterion kept, reason fixed. One divert
criterion was dead on arrival (`close()` is already on the `VectorStore`
Protocol) and was removed.

**No second Architect cycle was run for these**: every change is a correction
to a decision's stated evidence, scope figure, or placement, applied exactly as
the review specified. None introduced a new mechanism for a reviewer to
evaluate. The two genuinely open items (DD-11's re-scope, DD-7's storage home)
are operator questions, not design questions a second Architect pass would
settle.

---

### Execution begins — 2026-09-19

Flight marked `in-flight`. Crew file `.flightops/agent-crews/leg-execution.md`
loaded and validated (`## Crew`, `## Interaction Protocol`, `## Prompts` all
present, prompts fenced).

**Squawks 0083 and 0050 remain open at flight start.** Both are Leg 4
prerequisites (0083 blocks `pip-audit`; the frozen build must be verified after
the `anyio` bump). The operator elected to start the flight and clear them in
parallel rather than serialize. Recorded so Leg 4 does not discover the
dependency as a surprise.

**Leg 1 risk tier: HIGH.** Two independent triggers, either sufficient on its
own:
1. *State-machine / lifecycle change* — it adds a step to the application's
   shutdown sequence and constrains that step between two named bounds.
2. *Shared-interface change with existing consumers* — AC-4 asks
   `IndexingManager` to surface cancel-fallback state; the manager is consumed
   by the lifespan and by the knowledge pipeline.

Design review run accordingly. The tier would have been HIGH regardless on the
"when in doubt, tier high" rule: this leg's entire subject is a hazard
(DD-3a's torn save) that the flight only learned about at Architect review, one
layer below where the original decision was looking.

**Leg 1 bundles two unrelated defects deliberately.** The shutdown hook and the
name reconcile share no subject. They share the property that made both
survivable to this point: **no operator surface reveals either**. That is
recorded here because it changes what review means for this leg — a Reviewer
cannot confirm it by exercising the product, only by reading tests. The leg
states this in its own Context for the same reason.

---

### Leg 1 design review — two cycles, both `needs rework`

**Cycle 1** (Developer, Sonnet) returned three high-severity findings and one
medium. The serious one was not a citation slip but **a live data-loss bug the
leg design would have introduced**. DD-3a says to skip flushing knowledge bases
whose worker took the cancel fallback. The leg said "record it on the manager"
without establishing where else `stop()` is called — and it is called at
runtime from `api.py:1593` (`delete_knowledge_base`) and `api.py:1786`
(`delete_kb_item` for a folder), the latter **re-kicking the worker
immediately** at `api.py:1798-1799`. So a knowledge base can cancel-stop at
10:00, index cleanly all day, and shut down at 18:00 with a genuinely dirty,
genuinely safe index. An append-only report would skip flushing it and lose
that write — meaning DD-3a's protection would cause more data loss than it
prevents, on a path that fires far more often than shutdown. Closed with AC-4a
(overwrite, never accumulate), AC-4b, and a named Edge Case.

Cycle 1 also found that `app.py:426-427` nulls both the module singleton and
the local on the **last two lines of the very block** AC-6 said to read
"after" — so an implementation following the criteria in order would have read
`None`, passed an empty skip set, and shipped DD-3a inert with every specified
test green. Closed with AC-6a (capture inside the block) and AC-6b (call the
hook unconditionally outside it, because `api.py:1793` can dirty a store with
no manager at all). And that **no criterion tested the real `app.py` glue** —
the ordering spy replaces the hook with a bare spy, the isolation tests use a
hand-built skip set. Closed with AC-7a, written to demand a test that *fails*
when the report is read after the null-out.

**Cycle 2** confirmed all four cycle-1 findings closed, then found a fifth in
the same defect family: **`drain()` ends with `self._entries.clear()`**
(`manager.py:261`), so a flag stored on `_WorkerEntry` — the natural reading of
"record it on the manager", since that class already holds `state`,
`stop_requested` and `awaiting_flush` — is wiped by the very call that precedes
every production read. An implementation doing that passes every criterion and
every existing test while reporting an empty skip set at real shutdown. Closed
with AC-4c, which requires the report to live outside `_entries` and to be
proven readable after a **real** `drain()`.

**The pattern across both cycles is one defect class, found three times**: the
shutdown hook's skip set can be silently empty in production while every test
the leg specified still passes. Each cycle found a different mechanism for it —
the wrong read site, no real-wiring test, and storage wiped by `drain()`. The
Citation Audit could not have caught any of them: all three were things the
draft had not cited **at all**. An audit verifies the claims you made, not the
ones you did not think to make. That limitation is now recorded in the leg's
own audit header.

**Operator decision, 2026-09-19: proceed with implementation.** The reshape
option (drop the skip set entirely — flush unconditionally and accept the
torn-save risk, or wait rather than skip) was offered and not taken; DD-3a
stands as designed. Leg marked `ready`.

**Escalation.** Two cycles both returned `needs rework`, which is the
methodology's escalation trigger (`/mission-control:agentic-workflow`, "Design
review loops > 2 times → escalate to human"). Escalated to the operator rather
than silently running a third cycle. The cycle-2 finding was applied first, so
the escalation carries the leg in its best state rather than its worst; what is
escalated is the *decision* to proceed, not an unresolved disagreement — cycle
2's finding was precise, verified independently by the Flight Director
(`manager.py:261`, `_WorkerEntry` at `:109-123`), and uncontested.

---

### Flight Director note — Leg 1 widened the `VectorStore` Protocol, and the divert trigger for that had been deleted

Leg 1 landed with `the_one/vectors/_store.py` modified:

```
-    async def close(self) -> None: ...
+    async def close(self, *, skip_kb_ids: frozenset[str] | set[str] = frozenset()) -> None: ...
```

The leg's **Files Affected did not list `_store.py`**, and this is a
shared-interface change to the seam the mission's own constraint protects
("a different vector store can be introduced without modifying the indexing
pipeline").

**The flight spec had a divert trigger for exactly this and I removed it.**
The original Adaptation Criteria read: *"Divert if the shutdown hook turns out
to need a change to `VectorStore`'s protocol (`vectors/_store.py`) rather than
a new module-level function."* Architect cycle 1 called it "dead on arrival"
because `close()` is already on the Protocol, and I agreed and deleted it.

Both of us answered a narrower question than the trigger asked. The trigger
asked *does the hook force a Protocol change?* We checked *is `close()` on the
Protocol?* It was — and the hook still forced the Protocol to change, by
widening that method's signature. **This is the same error shape as the "six
call sites" Citation Audit failure earlier in this flight**: a claim verified
against a narrower proposition than the one being relied on. Twice in one
flight, by the Flight Director, is a pattern and is recorded as one.

**Disposition: accepted, not diverted.** The widening is keyword-only with a
default, so every existing implementation and call site still satisfies the
Protocol, and a future backend simply implements the wider signature — the
mission's seam constraint is intact. The full unit gate is green at 4,790.
Diverting a landed, tested, backward-compatible change into its own leg would
cost more than it protects.

**Two things the flight-end Reviewer must check rather than take on trust:**

1. **Latent stub trap.** Structural `VectorStore` implementations in the test
   suite still declare `async def close(self)` with no `skip_kb_ids` — e.g.
   `tests/test_kb_manager.py:577`, `tests/test_kb_indexer.py:172,209`,
   `tests/test_lifespan.py:46`. Nothing calls them with the new keyword today,
   so the suite is green; the next test that routes one of them through
   `close_vector_store()` gets a `TypeError`. The Developer's report says it
   "verified against the one pre-existing bare `store.close()` call site" —
   that checks callers, which is the opposite direction from the risk.
2. Whether pushing the skip set *into* `close()` was necessary at all, versus
   having `close_vector_store()` flush per knowledge base itself. The latter
   would need `UsearchStore._kbs`, which is private — so the chosen shape is
   defensible, but it is a design call made inside implementation and it
   deserves a second reader.

**Verified independently by the Flight Director** before accepting: the diff
above (`git diff the_one/vectors/_store.py`), the four stub sites, and the
existence of all three falsification tests the Developer named
(`test_lifespan_shutdown_threads_real_cancel_report_into_vector_hook`,
`test_cancel_report_survives_the_real_drain`,
`test_disabled_kb_tool_survives_detach_rename_reattach`) in the files claimed.

---

### Leg 2a risk tier and the remaining-flight sequencing

**Leg 2a `inventory-freshness` risk tier: HIGH.** Two triggers:
1. *Cache/freshness behaviour* — DD-6 is literally an invalidation-signature
   change. This is the named trigger verbatim.
2. *Projection change with a live consumer* — `get_kb_status` gains an
   aggregate, and `studio.js` polls it every 5 seconds.

Design review run accordingly, pointed hardest at **AC-3**, which may falsify
DD-6 outright: `walk.py::plan_reconcile` detects change on `size_bytes`/`mtime`
and **not** `content_hash`, so whether *any* field reliably moves on a
content-only re-index is unverified. The flight has assumed it since planning.
If nothing moves, DD-6 goes back to the operator rather than being papered over.

**Sequencing for the rest of the flight, recorded because "finish the flight"
is not fully autonomous:**

- **Leg 3 `measurement` is viable.** `fly` is installed and the `the-one`
  target holds a token valid to 2026-09-20 22:56 UTC (~24h). The leg's first
  step re-verifies the worker regardless — a planning-time check is not a
  run-time one. It carries an **operator decision point** by design (DD-5's
  early-stop at 500k), which the Flight Director escalates rather than decides.
- **Leg 4 `regression-net-and-gates` is BLOCKED on squawk 0083.** `pip-audit`
  cannot go green while `anyio` 4.13.0 is pinned, and the frozen Windows build
  must be verified *after* the bump. Squawk 0050 also remains `open`.
- **The squawks are deliberately NOT being cleared in parallel.** Both would
  edit the working tree while Legs 1-2 sit uncommitted on the flight branch,
  mixing squawk changes into a flight commit — precisely the mixed record the
  squawk convention exists to prevent, and the reason the Flight 7 planning
  artifacts were held off the squawk branch earlier in this session. They clear
  on their own branch after the flight's legs are committed, before Leg 4's
  gate run.

---

### Leg 2a design review — one cycle, `approve with changes`

**AC-3's premise holds; DD-6 is not falsified.** The review traced it rather
than asserting it: a **file** item's `indexed_at` is stamped only by `_flush`'s
`update_status(..., "indexed")` (`manager.py:570`), which runs only for items
actually re-queued and re-indexed — never on a no-op walk. A **folder** item's
is the opposite (`manager.py:441`, unconditional every pass), which is exactly
why the leg already forbade using it. So an aggregate over `type='file'`
`indexed_at` satisfies **AC-2 and AC-5 together** — moves iff something
re-indexed, stable on a quiet corpus. The conflict the Flight Director flagged
as possibly unbuildable does not exist.

The residual gap is a same-size **and** same-mtime edit, which
`plan_reconcile` cannot detect at all. That is a pre-existing pipeline
limitation orthogonal to the aggregate choice, recorded here so a future
reviewer does not re-litigate AC-3 as though the aggregate were at fault.

**Five corrections applied.** Two were substantive:

1. **AC-13 pointed the wrong way.** It told the Developer to match the in-file
   tiebreak precedents at `repositories.py:1569` / `:2431` — both **DESC**.
   Squawk 0087's own Corrective Action already commits to `ORDER BY created_at,
   path_or_url` **ascending**, for a stated reason (it is the order the walk
   discovered the files in). The precedents establish the *pattern*, not the
   *direction*, and the leg cited them without that qualifier.
2. **The leg carried the squawk's query fix and silently dropped the test
   tightening that motivated filing it.** Squawk 0087 exists because a browser
   assertion had to compare rendered paths as a **set** rather than a sequence,
   since order was not a contract. Making it a contract without tightening that
   assertion would close the squawk while leaving the weakened test that
   recorded the defect. Now AC-14a.

Three were citation defects: `AppMetadataRepository` has **only** `get`/`set`
and no `delete` (so AC-11 was unsatisfiable as written — now AC-11a);
`knowledge-section.js` borrows `mcp-tool-item` at **two** sites, not one; and
three line numbers had drifted (`delete_knowledge_base` 1585→1577,
`delete_kb_item` 1780→1758, `_appendIcon` 155→163 — the last carried over from
a pre-compaction note).

The review also pre-empted a silent-false-green the leg would have shipped:
without one shared key helper, a cleanup site whose key derivation drifts from
the write site deletes nothing **while AC-12's test still passes**, because
`get()` on the wrong key also returns `None`. Now AC-11b.

**No second review cycle.** Every change is a correction to a criterion's
direction, a citation, or a missing prerequisite — none introduces a mechanism
a reviewer has not already evaluated. Leg marked `ready`.

---


---

## Leg measurement (3) — pass 1: AC-7 tolerance band, declared BEFORE the 500k rung

**Written 2026-09-20, after both 200k calibration rungs and before 500k was
launched** — AC-7's ordering is (1) run 200k twice, (2) compute the observed
delta, (3) write the band down, (4) only then run 500k. This section is step 3.
Declared by the Flight Director as a threshold judgement recorded in an
artifact.

### The two 200k calibration rungs

Both on the Concourse Windows worker via `ci/tasks/windows-vector-bench.yml`,
launched detached. Build 74 (`200k-run1`) succeeded in 33m26s; build 75
(`200k-run2`) succeeded in ~33m. Backend recorded on **every row**:
`numkong=no, simd=serial; numkong ext will not load (ModuleNotFoundError: No
module named 'numkong')` — confirming Flight 1's finding that every published
`usearch` Windows wheel ships unlinked, now attached to the measurements
themselves rather than asserted alongside them.

| metric | run 1 | run 2 | run-to-run Δ | Flight 2 (200k) | r1 vs F2 | r2 vs F2 |
|---|---|---|---|---|---|---|
| f16 `build_s` | 1155.740 | 1161.530 | **+0.50%** | 1155.970 | −0.02% | +0.48% |
| i8 `build_s` | 496.110 | 486.200 | **−2.00%** | 497.120 | −0.20% | −2.20% |
| f16 `save_ms` | 2248.988 | 2116.229 | −5.90% | 1907.855 | +17.88% | +10.92% |
| i8 `save_ms` | 1196.527 | 1231.938 | +2.96% | 1028.898 | +16.29% | +19.73% |
| f16 `p95_ms` | 18.187 | 18.130 | −0.31% | 17.968 | +1.22% | +0.90% |
| i8 `p95_ms` | 9.072 | 8.391 | −7.51% | 8.458 | +7.26% | −0.79% |
| f16 `restore_ms` | 1128.912 | 1126.430 | −0.22% | 1008.386 | +11.95% | +11.71% |
| i8 `restore_ms` | 619.201 | 657.481 | +6.18% | 517.824 | +19.58% | **+26.97%** |

`disk_MB` reproduced **byte-identically** (223.67 / 126.01) in both runs and
against Flight 2.

### What the calibration actually shows

**`build_s` is near-deterministic.** Run-to-run spread is 0.5% (f16) and 2.0%
(i8), and f16 reproduces Flight 2's six-month-old figure to **−0.02%**. This is
the metric the linearity question rests on, and it is a clean instrument.

**`save_ms` and `restore_ms` carry real I/O noise AND a systematic offset.**
Run-to-run they move 3–6%, but *both* runs sit **+11% to +27% above Flight 2**
consistently. A consistent offset across two independent runs is not noise —
something about this worker's disk state differs from Flight 2's. Recorded as
an observation rather than explained away; it does not affect the linearity
claim, which rests on `build_s`.

### The band

Per-metric, derived from the observed deltas above rather than assumed:

| metric | band | basis |
|---|---|---|
| `build_s` | **±10%** | observed run-to-run ≤2.0%; a 5× margin keeps the linearity test sharp |
| `save_ms` | **±25%** | observed run-to-run ≤5.9%, plus the systematic offset above |
| `p95_ms` | **excluded from the linearity claim** — see below |

**`p95_ms` is deliberately NOT given a linear projection.** It is query
latency, and HNSW search cost grows roughly logarithmically in N, not linearly.
Projecting it linearly and then "testing" that projection would manufacture a
failure out of correct behaviour. It is recorded at every rung and compared
against the 200k value, but it is not part of the linearity claim. *(The leg's
AC-7 named it alongside `build_s` and `save_ms`; that was an error of framing
by the Flight Director — all three are reported, but only the two O(N) metrics
carry a linear expectation.)*

**Two runs bound a single observed delta, not a variance estimate.** With n=2
there is no distribution, only a spread. Stated because the multi-hour cost of
each rung makes a real variance estimate unaffordable, and a reader should not
mistake ±10% for a confidence interval.

### 500k linear projections the rung is tested against

| cell | projected `build_s` | ±10% band | projected `save_ms` | ±25% band |
|---|---|---|---|---|
| f16 | 2896.59 | 2606.9 – 3186.2 | 5456.52 | 4092.4 – 6820.7 |
| i8 | 1227.89 | 1105.1 – 1350.7 | 3035.58 | 2276.7 – 3794.5 |

(Mean of the two 200k rungs × 2.5.)

### AC-8 — the calibration gate: **PASS**

Every `build_s` figure is within 2.2% of Flight 2's, far inside ±10%.
`save_ms` sits +11–20%, inside ±25%. The apparatus reproduces Flight 2's
measurement, so the ladder is measuring what it claims to measure. Proceeding
to 500k.

*(`i8 restore_ms` at +26.97% vs Flight 2 is outside a ±25% band — but
`restore_ms` is not one of AC-8's gated metrics and is not part of the
linearity claim. Recorded here so the exceedance is visible rather than
filtered out by the choice of gated metrics.)*


### The 500k rung — build 76, succeeded in 1h17m49s

Backend on every row: `numkong=no, simd=serial` (unlinked wheel, as expected).

| cell | build_s | disk_MB | p50_ms | p95_ms | recall@k | peak_rss_MB | save_ms | restore_ms |
|---|---|---|---|---|---|---|---|---|
| f16 | 2954.80 | 559.17 | 12.235 | 16.587 | 0.0980 | 1537.97 | 4508.060 | 2236.272 |
| i8 | 1328.29 | 315.03 | 6.978 | 8.876 | 0.0580 | 1342.34 | 2856.788 | 1396.872 |

### AC-9 verdict against the band declared BEFORE this rung ran: **all four PASS**

| metric | linear projection (200k mean × 2.5) | measured | deviation | band | verdict |
|---|---|---|---|---|---|
| f16 `build_s` | 2896.59 | 2954.80 | **+2.01%** | ±10% | PASS |
| i8 `build_s` | 1227.89 | 1328.29 | **+8.18%** | ±10% | PASS |
| f16 `save_ms` | 5456.52 | 4508.06 | −17.38% | ±25% | PASS |
| i8 `save_ms` | 3035.58 | 2856.79 | −5.89% | ±25% | PASS |

**`disk_MB` is linear to within 0.001%** — projected 559.175 / 315.025 against
measured 559.17 / 315.03. Not a gated metric; recorded because a figure that
exact is a strong independent check that the two rungs measured the same thing.

**`p95_ms` moved the way a non-linear metric should**: f16 went **down** 8.7%
(18.159 → 16.587) and i8 up 1.7%, across a 2.5× corpus growth. Had it been left
in the linearity claim — as an earlier draft of AC-7 had it — f16 would have
"failed" a linear projection by 66% while behaving exactly as HNSW query
latency ought to. The correction earned itself here.

### What this answers

**Windows `usearch` build cost IS linear in N**, verified across a 2.5× range
with ≤8.2% deviation on the metric the question rests on. Flight 2's
extrapolation method — which Flight 3's flush cadence was sized against — is
**sound**, and that was the thing nobody had checked.

Note the deviation is one-sided on build (+2.0%, +8.2%) and one-sided the other
way on save (−17.4%, −5.9%). Two rungs cannot separate a mild super-linearity
from worker variance; the 200k pair's own run-to-run spread was ≤2.0% on build,
so the +8.2% on i8 is larger than noise and is recorded as such rather than
waved through.

### 1M projections, from two independent anchors

| cell | from 200k × 5 | from 500k × 2 |
|---|---|---|
| f16 `build_s` | 5793.2s (96.6 min) | 5909.6s (98.5 min) |
| i8 `build_s` | 2455.8s (40.9 min) | 2656.6s (44.3 min) |

The two anchors agree within 2% on f16 and 8% on i8. A 1M rung would cost
roughly **2.5 hours** of the shared worker (≈137 min of build plus
provisioning, save and restore).


### Operator decision, 2026-09-20: **stop at 500k. The 1M rung is not run.**

**This overrides DD-5's letter.** DD-5's early-stop checkpoint reads: *"if the
measured per-vector build cost is within tolerance of the extrapolation, the 1M
run proceeds; if the curve has already diverged, the leg stops."* The curve did
**not** diverge, so by that rule the 1M rung proceeds. The operator stopped it
anyway, and the reasoning is recorded here rather than the decision being made
to look like DD-5's.

**Why the case for 1M weakened between planning and now**: DD-5 was written
when the linearity assumption was *unverified*, and a 1M rung was the only way
to test it. It is now verified across a 2.5× range on the metric the question
rests on, and both anchors (200k×5 and 500k×2) project 1M within 2% of each
other on f16. The remaining ~2.5 hours of shared worker would buy precision on
a number that can now be derived with justified confidence — which is the same
argument DD-5 itself makes for stopping early, applied to a case DD-5 did not
anticipate: *the extrapolation confirmed rather than falsified*.

**What is consequently NOT known**, stated plainly so nobody later reads this
as a 1M measurement:
- There is **no measured 1M figure**. The mission's open question closes on a
  *verified extrapolation*, not a direct measurement. Anyone who needs a real
  1M number must run the rung; `ci/tasks/windows-vector-bench.yml` is committed
  and takes `-v bench_n=1000000`.
- The **i8 build drift (+8.18%)** is larger than the 200k pair's run-to-run
  spread (≤2.0%) and is therefore not explained as noise. Two rungs cannot
  separate mild super-linearity from worker variance, and a third would have
  helped. Carried as a residual, not resolved.
- `peak_rss_MB` grew sub-linearly (f16 1271 → 1538, +21% for a 2.5× corpus),
  consistent with model/import weight dominating, but this is two points and no
  claim is made about its shape at 1M.

**Leg 3 therefore has no pass 2.** AC-9a's "self-contained handoff so a fresh
Developer can resume at 1M" is moot and is closed as not-required; the leg
completes in one pass with AC-10 (the 1M rung) recorded as **deliberately not
run**, per this decision — never as passed.

### AC-12/AC-13 — Flight 3's flush cadence re-checked against the measured curve: **re-confirmed**

Flight 3's DD-12 sized `FlushPolicy` (`the_one/knowledge/indexer.py:49-51`,
`FLUSH_MIN_CHUNKS=2000`, `FLUSH_MIN_SECONDS=15.0`, `FLUSH_SAVE_MULTIPLIER=10.0`,
consumed as `max(FLUSH_MIN_SECONDS, FLUSH_SAVE_MULTIPLIER × last_flush_seconds)`)
against a **15% steady-state-overhead divert threshold at 1M**
(`flights/03-folder-registration-and-indexing/flight-log.md:194-201`), using a
single extrapolated 11s save figure. This leg has real measured `save_ms` at
two rungs instead, so the arithmetic is re-derived here rather than accepted.

**Independent re-derivation of the closed form.** Overhead = `save_s / (save_s
+ wait_s)`, where `wait_s = max(15.0, 10 × save_s)`. The two terms cross at
`save_s = 15.0 / 10.0 = 1.5s`. Above that crossover the multiplier term
dominates and overhead collapses to a constant regardless of `save_s`:
`save_s / (save_s + 10·save_s) = 1/11 = 9.0909…%` — this reproduces Flight 3's
9.09% closed form independently rather than taking it on faith. **Below** the
crossover, `FLUSH_MIN_SECONDS=15` binds instead and overhead is
`save_s / (save_s + 15)`, which is *lower* than 9.09% and depends on the exact
`save_s`.

Applying this to every measured `save_ms` in this leg:

| cell | `save_ms` | `save_s` | which term binds | overhead |
|---|---|---|---|---|
| 200k f16 run1 | 2248.988 | 2.249 | multiplier (≥1.5s) | 9.091% |
| 200k f16 run2 | 2116.229 | 2.116 | multiplier (≥1.5s) | 9.091% |
| 200k i8 run1 | 1196.527 | 1.197 | **`FLUSH_MIN_SECONDS` (<1.5s)** | **7.388%** |
| 200k i8 run2 | 1231.938 | 1.232 | **`FLUSH_MIN_SECONDS` (<1.5s)** | **7.590%** |
| 500k f16 | 4508.060 | 4.508 | multiplier (≥1.5s) | 9.091% |
| 500k i8 | 2856.788 | 2.857 | multiplier (≥1.5s) | 9.091% |

**The i8-at-200k case the Flight Director flagged is real and checked
explicitly, not assumed away**: at 200k, i8's `save_s` (≈1.20–1.23s) sits
*below* the 1.5s crossover, so `FLUSH_MIN_SECONDS` binds rather than the
multiplier term, and overhead is lower than the invariant (7.39–7.59% vs
9.09%). By 500k, i8's `save_s` (2.857s) has crossed above 1.5s and the
invariant applies again. This is consistent, not contradictory: as corpus
size (and therefore `save_s`) grows, overhead can only rise toward 9.09% and
plateau there — it never exceeds it for either dtype in the measured range.

**Verdict: re-confirmed.** Every measured overhead (7.39%–9.09%) sits
comfortably under the 15% divert threshold Flight 3 sized the cadence against,
with margin ranging from 36% relative (i8 200k) to 39% relative (the
multiplier-dominated cases, matching Flight 3's own 9.09%-vs-15% margin
exactly). Because overhead is invariant at 9.09% once `save_s ≥ 1.5s` and only
falls below that for *smaller*, faster saves, and because build cost (and
therefore save cost) was independently confirmed linear in N by AC-9 above,
the 500k-and-below re-confirmation extends to 1M by the same closed-form
argument Flight 3 already made — the multiplier term will dominate even more
comfortably at 1M's larger save times, not less. No number here forces a
change (AC-13's divert trigger does not fire); `the_one/knowledge/indexer.py`
is untouched by this leg.

**What this data cannot tell you (state plainly, per the leg's own
instruction):** the bench ladder measures raw vector build/save/restore cost
through `UsearchStore` directly — it does not run the indexing pipeline, so it
produces no `chunks/second` figure. Whether `FLUSH_MIN_CHUNKS=2000` ever binds
*before* the time gate at any corpus size — i.e., whether the chunk-count gate
is even reachable, or is permanently shadowed by the time-based `max(...)` —
is **out of this data's reach**. Flight 3's own Leg 2 measurement (F3 log
`:187`) found only the unconditional end-of-pass flush ran on its test host,
never either gate mid-run; this leg adds no new evidence on that question and
does not claim to.

### The fusion sweep (AC-14–AC-17)

`scripts/sweep_fusion_constants.py` drove `retrieval.search()` end-to-end
(real `UsearchStore` + `KBChunkRepository` + `IndexingManager`, per
Implementation Guidance 6b — not the bench's raw-vector path, not the stub
vector-store fixture) over the repository's own `docs/` and `missions/`
folders: **33,281 chunks indexed**, 60 queries sampled from the corpus itself
(stride 40), against the shipped constants `RRF_K=60`, `candidate_k(limit=10)=50`.

Swept `RRF_K` ∈ {10, 30, 60, 100, 200} × `candidate_k` ∈ {10, 25, 50, 100,
200} (25 cells including the shipped point), monkeypatching `_candidate_k`
directly per Implementation Guidance 6a:

| RRF_K | candidate_k | fire_rate | mean_overlap_vs_shipped | exact_match_rate_vs_shipped |
|---|---|---|---|---|
| 60 (shipped) | 50 (shipped) | 0.000 | 1.000 | 1.000 |
| 10 / 30 / 60 / 100 | every swept value except (100,200) | 0.000 | 1.000 | 1.000 |
| 100 | 200 | 0.000 | 0.998 | 0.983 |
| 200 | 10 / 25 / 50 / 100 | 0.000 | 1.000 | 1.000 |
| 200 | 200 | 0.000 | 0.998 | 0.983 |

(Full 25-row grid preserved in the run log; collapsed here because 23 of 25
cells are identical to the shipped point.)

**AC-14 — reserved-slot fire rate: 0.000 across the whole grid**, all 60
queries, every `(RRF_K, candidate_k)` combination. **AC-17 applies, not
AC-15's counterfactual**: the result set barely moves across a 5×5 grid
spanning a 20× range on `RRF_K` and a 20× range on `candidate_k` — the two
weakest points (`RRF_K∈{100,200}, candidate_k=200`) still hold 0.998 mean
overlap and 0.983 exact-match against the shipped constants. **Verdict: the
constants are not load-bearing at this corpus size (~33k chunks)** — moving
them within a generously wide grid does not materially change what a query
gets back.

**AC-15's boundary, held**: no relevance judgment was manufactured and no
value is recommended. The mission's fusion open question closes as *"fixed,
and here is the evidence the fixing is not arbitrary"* — never as "tuned."

**AC-16's caveat, stated plainly**: the sweep's embeddings run through a
deterministic hash-seeded stub (dim=8, mirroring
`tests/_embedding_stub.py::StubEmbeddingBackend`), reimplemented in-script
because `scripts/` must not depend on `tests/`. A hash-based stub has **no
correlation to real semantic meaning** — it exercises fusion *arithmetic*
(how RRF combines two independently-produced rank lists), never a real
model's actual recall/precision behavior. This sweep would not catch a
genuine relevance regression (the right chunks silently ranking worse under a
real embedding model); it answers sensitivity to the constants, not quality.
A future mission wanting a real relevance benchmark needs ground-truth
judgments this tree does not have, and building the stub was not a step
toward that — it is a deliberately different, narrower measurement.

**Corpus-size caveat (Edge Cases)**: at ~33k chunks the reserved slot never
fired, so its fire rate is a finding about this corpus (real repository docs,
short/paragraph-length queries drawn from the same corpus, high keyword-
semantic agreement) rather than proof the slot can never fire on a corpus
shaped to stress it deliberately.

### AC-18 — `make test-unit`, verbatim, alone, foreground

Run alone, in the foreground, with no rung concurrently live (the 1M rung was
never launched — see the stop-at-500k decision above — so there is no
Edge Cases conflict to observe). `ruff check the_one/ tests/ scripts/` and
`ruff format --check the_one/ tests/ scripts/` both ran clean first (all
checks passed; 452 files already formatted).

`make test-unit` result: **4,809 passed, 10 skipped, 616 deselected, 1
failed** in 674.88s. Series so far: F1 3,950 → F2 4,370 → F3 4,547 → F4 4,649
→ F5 4,732 → F6 4,769 → F7 Leg 2a 4,807 → **F7 Leg 3: 4,810 collected** (4,809
passed + 1 failed), +3 over Leg 2a.

**The one failure, checked for isolation rather than accepted as a
regression, per this leg's own host-memory-pressure caveat**:
`tests/test_kb_watcher.py::TestStopAndDrain::test_drain_three_live_entries_under_a_second`
— asserts `WatchManager.drain()` completes in under 1.0s and that no
`the-one-watch-f{0,1,2}` threads remain in `threading.enumerate()`
afterward. Re-run alone (`pytest
tests/test_kb_watcher.py::TestStopAndDrain::test_drain_three_live_entries_under_a_second`):
**PASSED in 0.21s**. Re-run as its whole file (`pytest
tests/test_kb_watcher.py`, 39 tests including this one): **all 39 PASSED** in
10.38s, no reorder needed. The test asserts a real-clock timing bound and
real OS thread teardown; under the full ~11-minute, ~4,800-test run on a host
already flagged as under intermittent memory pressure from unrelated
processes, thread-cleanup latency crossing 1.0s is the kind of scheduling
noise that timing assertion is exposed to, not a defect this leg's changes
introduced — no file this leg touches (`scripts/bench_vector_store.py`,
`scripts/sweep_fusion_constants.py`, `mission.md`, the two flight-log/leg
files) has any relationship to `WatchManager` or `test_kb_watcher.py`, and
the same test is not among the fixes any of Legs 1/2a/2b made. **Recorded as
a flake, not a regression** — passes standalone and in its own file both
times it was checked.

**Gate verdict: PASS**, with the one isolated-and-confirmed flake noted above
rather than silently ignored.

### AC-19/AC-20 — Leg 3 complete

AC-19 is satisfied by the sections above plus the earlier "pass 1" sections
in this same `## Leg measurement (3)` block: AC-7's pre-declared tolerance
(the band table), every rung's raw figures with the recorded backend (both
200k calibration runs and the 500k rung, each with `numkong=no, simd=serial`
on every row), AC-11's linearity interpretation, AC-12's flush-constant
conclusion (re-confirmed, immediately above), and the fusion sweep's results
with AC-15/AC-16's boundaries held.

AC-20 closes both mission open questions directly in `mission.md`: the fusion
balance as "fixed, and here is the evidence the fixing is not arbitrary" (DD-4,
never "tuned," `RRF_K`/`candidate_k` sweep evidence and the AC-16 stub-
embedding caveat both carried into the mission doc), and the Windows 1M
re-measure as a verified extrapolation (not a direct measurement, the i8
+8.18% residual drift named, `ci/tasks/windows-vector-bench.yml -v
bench_n=1000000` pointed at for anyone who needs the real number). The
Known Issues entry for `usearch` running unaccelerated on Windows was also
updated to cite this leg's live per-row confirmation.

**Leg 3 (`measurement`) is complete in one pass.** No product code changed —
neither the flush constants (AC-13 did not fire) nor the fusion constants
(AC-15 forbids it without a load-bearing finding, and none was found). The
only tree changes are `ci/tasks/windows-vector-bench.yml` (new),
`scripts/bench_vector_store.py`'s per-cell backend column,
`scripts/sweep_fusion_constants.py` (new), `mission.md`'s two open questions
and the Known Issues entry, and this flight log.

## Leg confirm-lapse (2b) — implementation

**2026-09-19.** Landed uncommitted, carried alongside Legs 1 and 2a per the
flight's deferred-commit convention.

### AC-1 — finding: all 13 `App.confirmDelete` call sites

Re-enumerated per the leg's own warning (line numbers drift under a
deferred-commit flight): `grep -rn "confirmDelete(" the_one/interfaces/web/static/js/`
returned the same 13 sites the leg named, at the line numbers already
current in the working tree.

| # | Site | Armed element | `[data-confirm-title]` target | Consequence of committing | Lapse distinguishable from commit, BEFORE this leg |
|---|---|---|---|---|---|
| 1 | `system-page.js:81` | `rotateBtn` (button) | static label "Rotate Encryption Key" | `POST /api/encryption/rotate` — rotates the Fernet key protecting **every** stored secret in the app; irreversible, no undo, no row disappears | **No** |
| 2 | `knowledge-section.js:979` | `<summary>` (folder panel) | the folder-path span (**operator's own filesystem path**, not a label) | `DELETE` the folder + cascade-delete its file items and chunks; irreversible | **No** |
| 3 | `knowledge-section.js:1443` | `deleteBtn` (Danger Zone) | static label "Delete Knowledge Base" | `DELETE` the whole knowledge base; irreversible | **No** |
| 4 | `connector-editor.js:599` | `deleteBtn` (Danger Zone) | static label "Delete Connector" | `DELETE` the connector config; irreversible | **No** |
| 5 | `mcp-server-editor.js:1270` | `deleteBtn` (Danger Zone) | static label "Delete MCP Server" | `DELETE` the MCP source; irreversible | **No** |
| 6 | `mcp-server-editor.js:1321` | `resetBtn` | static label "Reset connection" | `DELETE .../connection` — clears OAuth tokens/DCR/tools cache; recoverable via re-auth | **No** |
| 7 | `self-configuration-tab.js:1294` | `revokeBtn` | static label "Revoke" | revokes an external-access credential; irreversible (token invalidated) | **No** (and the ARM transition is announced via `role=status` for WCAG 4.1.2 — the LAPSE transition was not) |
| 8 | `studio.js:2080` | `deleteBtn` (agent editor) | static label "Delete Agent" | `DELETE` the agent config; irreversible | **No** |
| 9 | `studio.js:2116` | `purgeBtn` (agent editor) | static label "Purge now" | `DELETE` the agent's chat sessions; irreversible, agent itself survives | **No** — though see the pre-existing quirk below |
| 10 | `provider-editor.js:509` | `resetBtn` (plan sign-in) | static label "Reset connection" | clears stored OAuth tokens **locally only**; recoverable via re-sign-in | **No** |
| 11 | `provider-editor.js:946` | `deleteBtn` (no-agent-usage path) | static label "Delete Provider" | `DELETE` the provider; irreversible; gated by an agent-usage pre-check that found none | **No** |
| 12 | `provider-editor.js:951` | `deleteBtn` (network-failure fail-open path) | static label "Delete Provider" | same as #11, but the agent-usage pre-check **itself failed** — arms without knowing whether an agent is using the provider | **No** |
| 13 | `chat.js:1140` | `<li class="list-item">` (session row) | the session-title span (**operator's own/auto-generated conversation title**, not a label) | WS `delete_session` — deletes the chat session and its message history; irreversible | **No** |

**Reconciliation behaviour per site (guidance 4a).** Grepped every candidate
file for `setInterval`: only `studio.js`'s knowledge-detail poll
(`startKnowledgePoll`, 5s) touches an armed control's ancestry — site #2's
folder `<summary>`, which is exactly what squawk 0088 is about. Sites
3-12 sit inside editor panels with **no background poll or reconciliation
at all** touching them; nothing rebuilds them out from under an armed
click short of the operator's own navigation. Site #13 (`chat.js`) is
structurally different from all twelve others: `App.chat.renderSessionList`
does `sessionListEl.innerHTML = ''` and rebuilds the **entire list from
scratch** on every `session_list` WebSocket message — no keyed
reconciliation, no signature gate. A session_list broadcast fires only on
an actual list-changing event (create/delete/rename, from any tab), so the
exposure window is narrower than "every N seconds", but it is
**unconditional** where site #2's rebuild risk is conditional on a
changed items-signature. Fixing `renderSessionList`'s rendering strategy is
a `chat.js` change unrelated to `confirm.js` and outside this leg's
"no call-site special-casing, only the shared helper" boundary (DD-8) — it
is recorded here as a known, narrow, pre-existing limitation of the fix at
this one site, not something this leg closes.

### AC-2 — uniform defect, one narrow site-specific exposure

The **defect** is uniform across all 13: none of them had any way to
distinguish a lapsed arm from a commit before this leg, and the fix
(a `.confirm-lapsed` class, cleared unconditionally on the control's next
`confirmDelete` call) lands identically at all 13 through the shared
helper — no call site is special-cased (AC-5).

What is **not** uniform is what happens to the visual cue after it is
applied, and that follows directly from the reconciliation survey above:

- 11 of 13 sites have zero competing background re-render — the cue is
  reliable by construction.
- 1 of 13 (site #2, the folder summary) sits under a periodic poll whose
  survival is exactly squawk 0088's invariant, pinned by this leg's other
  deliverable.
- 1 of 13 (site #13, chat sessions) rebuilds wholesale on any list-changing
  WS event — a narrower-than-the-folder-case but unconditional-when-it-
  fires exposure, out of scope to close here.

Consequence severity also spans a wide range — from fully local/recoverable
(provider-editor's plan reset, site #10) to the single highest-consequence
control in the app (site #1, credential rotation, which rotates the key
protecting every other stored secret with no undo). AC-6 addresses that
site specifically below.

Two sites (#2, #13) swap the **operator's own data** (a filesystem path, a
conversation title) as the `[data-confirm-title]` target rather than a
static button label — raising the stakes of AC-7's capture discipline at
exactly those two sites (a regression there corrupts the operator's own
displayed data, not just a button's resting label). Verified unchanged:
capture still happens only in the first-click branch.

### AC-3 — escalation gate: feedback-only, not an interaction change

The chosen design — a `.confirm-lapsed` class, set only by the timer's own
`lapse()` callback and cleared unconditionally at the very top of every
`confirmDelete()` call, before the arm/commit branch is decided — was
checked against all three conditions mechanically, not by feel:

1. **Click count to commit: unchanged.** Still exactly two clicks (arm,
   then commit); the lapse cue never introduces a third required click.
2. **The arm/commit decision still depends only on `.confirm-delete`.**
   The lapse-clearing line runs unconditionally before
   `itemEl.classList.contains('confirm-delete')` is even evaluated — the
   branch itself never inspects `.confirm-lapsed`. A click's effect is
   exactly as governed by the one binary class as it was before this leg.
3. **`revertMs`'s role is unchanged.** The first click still starts the
   timer (`setTimeout(lapse, revertMs)`); the commit branch still clears it
   via the same `clearTimeout` call inside `revert()`. Nothing about what
   starts or stops the timer changed.

All three hold, so this is a **feedback** change under AC-3's test, not an
interaction change — DD-8's escalation trigger did not fire, and AC-3a is
therefore inapplicable (the leg did not need to freeze whole or report an
escalation; squawk 0088's independent work landed alongside the fix in the
same pass, not as a fallback).

The leg guidance's own warning — "a lapsed indicator that lingers until the
next interaction... would have been reasonable to call 'just visual' while
actually changing click semantics" — was taken seriously: the design
avoided that trap specifically by making "next interaction" mean "the next
call to `confirmDelete` for this `itemEl`" (arm OR commit alike), the only
kind of interaction the helper itself has any visibility into, rather than
some broader DOM-wide activity heuristic that would require the click
handler to consult new state.

### AC-4/AC-5 — the fix

`confirm.js` gained: a `lapse()` function (marks `.confirm-lapsed`, then
calls the existing `revert()`), the timer now calls `lapse` instead of
`revert` directly, and every `confirmDelete()` call clears
`.confirm-lapsed` unconditionally up front. `components.css` gained one
generic rule, `.confirm-lapsed { outline: 2px solid var(--status-warning);
outline-offset: 2px; }` — element-shape-agnostic (works identically on the
11 `<button>` sites, the one `<summary>`, and the one `<li>`), so the fix
reaches all 13 sites through the shared helper with zero call-site changes.

**No aria-live announcement for the lapse cue** (guidance 4c) — a
deliberate decision, recorded rather than an omission.
`self-configuration-tab.js` already announces the ARM transition via its
own `role=status` region (added for WCAG 4.1.2, since a persistent
`aria-label` overrides the swapped title text as the accessible name at
that one site). Extending that to LAPSE for every site would mean either a
per-call-site opt-in (which AC-5 forbids) or the helper owning a generic
live-region contract of its own — a materially larger surface than "add a
CSS class", and not something the leg's investigation was scoped to design.
The cue is visual-only; screen-reader parity for the lapse transition is
left as a named gap, not silently dropped.

### AC-6/AC-6a — the credential-rotation site

`system-page.js:81` was evaluated on its own terms, not folded into the
general 13-site pass, because it is the one confirm whose commit has no
undo and no visible row to disappear afterward. The fix does not add a
click, does not change what any click does, and does not touch what
triggers the rotate `POST` — it only changes what is **shown** after a
lapse. If anything this reduces accidental-double-fire risk: an operator
who is unsure whether their first click registered now has a visible
answer ("outlined amber, label still reads 'Rotate Encryption Key'" means
nothing happened) instead of a resting-identical state that gives no
signal either way.

**AC-6a's specific hazard — verified closed.** `revert()` has three
callers: the timer's own expiry (a true lapse, now routed through `lapse()`
instead), a transport-failure `.catch` and, per `system-page.js:87-91`, the
credential rotation's own **SUCCESS** path — `revertFn()` is called after a
successful rotation, with a comment saying so, conveying success through a
separate flash. Because `lapse()` marks `.confirm-lapsed` and only THEN
calls the shared `revert()` — while `revertFn` handed to callers is `revert`
itself, never `lapse` — a successful rotation can never end up wearing the
lapse cue. Pinned directly by
`test_rotate_success_never_carries_the_lapse_cue`
(`tests/browser/test_flow_admin_rotate_flash.py`): commits a (mocked)
successful rotation and asserts neither `.confirm-delete` nor
`.confirm-lapsed` is present afterward.

### AC-9/AC-9a — test coverage

One lapse-distinguishability test landed per call site (14 call sites' worth
of assertions across 13 sites — provider-editor's two arming PATHS to the
same button, #11/#12, each got a dedicated test, in
`test_flow_provider_editor.py`), plus the credential-rotation success-path
regression guard (AC-6a) and squawk 0088's invariant test:

- `studio` (8 sites): `test_flow_studio_knowledge_inventory.py` (folder +
  KB delete, plus the squawk 0088 invariant test), `test_studio_connector_editor.py`,
  `test_flow_studio_mcp_editor.py` (delete + reset), `test_studio_self_configuration_external.py`,
  `test_flow_agent_crud.py`, `test_flow_studio_purge_now_button.py`
- `system` (4 sites): `test_flow_admin_rotate_flash.py` (lapse +
  success-never-lapses), `test_flow_provider_plan_signin.py`,
  `test_flow_provider_editor.py` (both arming paths)
- `chat` (1 site): `test_flow_new_chat.py`
- `shared` (contract test, AC-9a): new `tests/browser/test_confirm_contract.py`
  — matches none of the chat/studio/system basename globs in
  `scripts/run-tests.sh`, so it lands in the complement lane by
  construction. Exercises `App.confirmDelete` directly via `page.evaluate`
  against a synthetic element tied to no call site: arm→commit, capture
  discipline, lapse visibility + next-interaction clearing, the
  `revertFn`-success-never-lapses contract (independent of any one call
  site), idempotent `revert()`, and the missing-`titleEl` edge case.

Lane results: `studio`, `system`, `chat`, `shared` all green (recorded
below under Verification).

### AC-10/AC-10a — squawk 0088's third invariant, pinned and falsified

Added `test_armed_folder_confirm_survives_items_signature_tick` to
`test_flow_studio_knowledge_inventory.py`. AC-10a's hazard is real: a naive
version (arm, then wait on the real walk→hash→chunk→embed→5s-poll
pipeline) would let the confirm's own 3-second `revertMs` fire before a
naturally-timed tick ever arrived. The landed test avoids the race by (1)
driving the signature-changing edit directly — `httpx` against
`POST .../reindex?scope=changed`, then a tight polling loop against
`GET .../status` for `content_freshness` to move, using Leg 2a's new
aggregate rather than sleeping on the pipeline — and (2) phase-locking the
arm click to the app's own 5-second poll (observed live via
`page.expect_response`) so the next natural tick lands well inside the
3-second window instead of racing an arbitrary point in the cycle.

**Falsification observed, not assumed.** Temporarily changed
`renderAllItems` (`knowledge-section.js`) to replace each folder's
`<summary>` with a freshly-built element on every call (simulating a
future regression), ran the new test alone:

```
PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser \
  tests/browser/test_flow_studio_knowledge_inventory.py -x --timeout 120 \
  -k test_armed_folder_confirm_survives_items_signature_tick
...
FAILED ...::test_armed_folder_confirm_survives_items_signature_tick
AssertionError: Locator expected to have class 're.compile('\\bconfirm-delete\\b')'
Actual value: mcp-tool-summary kb-folder-summary
1 failed, 18 deselected in 22.23s
```

The actual failure was sharper than "the class didn't survive": the delete
button's click handler closes over the **original** `summary` variable
from `buildFolderPanel`'s scope, so once `renderAllItems` swapped in a new
`<summary>` node, the click armed the stale, now-detached node while the
visibly-displayed summary showed no feedback at all — a live instance of
exactly the failure mode squawk 0088's Report describes ("a tick that did
would either destroy the armed node..."). Reverted the temporary change and
re-ran:

```
tests/browser/test_flow_studio_knowledge_inventory.py .
1 passed, 18 deselected in 17.63s
```

The test pins the *invariant* (the summary node's identity and armed state
survive an items-signature tick), not today's call graph — a future
refactor that keeps summaries intact via a different route still passes.
Squawk 0088 updated to `status: completed` with Corrective Action and
Verification filled in; Sign-Off left for the Flight Director per the leg's
own instruction.

### Edge cases (leg's own list)

- **Two confirms armed simultaneously** (e.g. two folder rows): each
  `confirmDelete` call closes over its own `itemEl`/`titleEl`/timer with no
  shared module-level state — independently armable, independently lapse,
  no interaction between them.
- **A confirm armed on a node the page then removes**: the timer's closure
  holds a reference to the (possibly now-detached) `itemEl`; `classList`
  operations on a detached node are harmless no-ops in every browser. No
  new risk from the lapse marker — same shape of non-issue the pre-existing
  title-restore already had.
- **`titleEl` missing**: the lapse cue lives entirely on `itemEl`'s
  classList, never on `titleEl` — it degrades identically to (in fact more
  simply than) the title-restore path, which already guards `if (titleEl)`.
  Pinned by `test_missing_title_element_does_not_throw`
  (`test_confirm_contract.py`).
- **Lapse while the tab is backgrounded**: unchanged by this leg —
  `setTimeout` throttling can make the real revert land later than
  `revertMs` nominally promises; when it does fire, the operator now sees
  the lapse cue instead of a silently-already-reverted control, which is
  strictly better information than before, not a new hazard.
- **Commit path calls `revertFn` on transport failure**: `revertFn` is
  `revert`, never `lapse` — a transport failure's rollback is visually
  identical to today's resting state, never mistaken for a lapse. Pinned
  by `test_capture_discipline_only_first_click_captures_original_title`
  and `test_revertfn_success_path_never_marks_lapse`.

### Verification

```
ruff check the_one/ tests/ scripts/          # All checks passed!
ruff format --check the_one/ tests/ scripts/ # 451 files already formatted
make test-unit                               # 4807 passed, 10 skipped
```

Browser lanes (`PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane <lane>`):

- `chat` — **41 passed**, clean single run.
- `shared` — **180 passed, 3 skipped**, clean run (after a real bug in the
  new contract test itself: `test_lapse_is_visually_distinct_and_clears_on_next_interaction`
  called `probe.click()` to simulate "the next interaction", but the
  synthetic fixture has no click LISTENER wired — unlike every real call
  site, nothing was listening, so the click did nothing. Fixed to invoke
  `App.confirmDelete` again directly via `page.evaluate`, matching what the
  helper itself defines as "the next interaction". Not a bug in `confirm.js`).
- `system` — **124 tests in the lane** (verified by
  `pytest --collect-only -q -m browser tests/browser/test_flow_admin_*.py
  tests/browser/test_flow_provider_*.py` → "124 tests collected"), all
  passing. ⚠️ **Corrected by the Flight Director**: this entry originally read
  "**187 passed** across component runs", which summed passes across several
  partial re-runs and therefore counted tests more than once. 187 would imply
  +68 tests against Flight 6's `system` baseline of 119; the real delta is
  **+5**, which is what this leg added. Left visible rather than silently
  edited, because the debrief compares these figures as a series and an
  inflated count corrupts the comparison rather than merely being wrong once.
  (29/29 on `test_flow_provider_editor.py` alone, including both new lapse
  tests);
  one full-lane run hit 3 unrelated pre-existing tests
  (`test_flow_admin_navigation.py`, `test_flow_provider_dirty_confirm.py`,
  `test_flow_provider_editor.py::test_api_key_eye_toggle`) with the
  `net::ERR_NETWORK_CHANGED`/element-not-found signature described below —
  all three pass individually.
- `studio` — **187 passed, 3 skipped**, clean on the final run. Getting
  there took several attempts: four consecutive full-lane runs each hit
  between 1 and 3 DIFFERENT failures, always in files this leg never
  touched (`test_flow_studio_mcp_navigation.py`,
  `test_flow_studio_navigation.py`, `test_flow_studio_knowledge_attach.py`,
  `test_flow_studio_tools_overrides.py`,
  `test_studio_self_configuration_queue.py`,
  `test_mcp_test_connection_button.py`, `test_studio_mcps_tab.py`), always
  with the same signature (`expect(...).to_be_visible/to_have_attribute`
  timing out waiting for a studio-mount element under full-lane load), and
  every one of them passed cleanly re-run alone or in a small group. This
  matches `conftest.py`'s documented "Standing pattern — full-lane timing
  flakes (squawk 0035)" verbatim ("an occasional test fails only under a
  FULL-lane run... the observed cases so far are all `studio`") — a
  pre-existing, environment-load-driven flake this leg did not introduce,
  not a regression. One genuine bug WAS found and fixed along the way:
  `test_reset_mcp_connection_confirm_lapse_is_visually_distinct` asserted
  `access_token` was still present in the GET response after a lapse, but
  `api.py`'s `OAUTH_MANAGED_SECRET_KEYS` visibility filter strips that key
  from every response regardless of state — fixed to assert `oauth_active`
  instead, the correct observable.

`docs/ui-testid-registry.md` / `tests/test_ui_guards.py`: no new
`data-testid`s were introduced by this leg (the lapse cue is a CSS class,
`.confirm-lapsed`, not a testid) — `test_ui_guards.py` passes unchanged.


---

## Leg regression-net-and-gates (5) — implementation

**2026-09-20.** Landed uncommitted, carried alongside Legs 1, 2a, 2b and 3
(`measurement`) per the flight's deferred-commit convention. This is the
flight's final leg, and the named owner of every release gate below.

### Part 1 — `kb-studio-round-trip` re-authored to `Status: active` (AC-1–AC-7)

Read both run logs before touching the spec, per the leg's own Implementation
Guidance — the status line named five defects; the sixth (AC-1a) was in the
2026-09-18-13-14-52 run log's Orchestrator Notes only (`:735-742`), never in
the status line.

- **AC-1**: resolved with the mandated **local swap**, not a reword or a move
  to the end. Row 9 is now the attach step (the original step 10); Row 10 is
  now the restart-resume step (the original step 9). A prose note directly
  above the Steps table states the swap and its rationale so it reads as a
  deliberate authoring decision, not a silent reorder. **No coverage loss**:
  nothing in steps 11-18 needs continuous-session state, and the restart
  (now Row 10) threatens nothing once it runs after the attach it used to
  precede.
- **AC-1a** (the sixth, run-log-only defect): Preconditions gained a
  **second, disposable fixture folder** (`<fixture-restart>`), sized (at
  authoring time, per the leg's explicit instruction — never grown mid-run)
  to make a full index pass take several seconds to low tens of seconds.
  Row 10 now polls `GET .../status` until at least one item genuinely reports
  `indexing` before issuing the stop — the fix for "stop it mid-pass" being
  unwinnable against a 3-4 file fixture that indexes in under a second. It
  runs on its own disposable knowledge base, created and deleted entirely
  inside Row 10, so it cannot perturb steps 3/5/8's counts on the main
  fixture.
- **AC-2**: added a `[continuous-session]` Preconditions definition — a
  falsifiable apparatus contract (the Executor states which process/page
  continuity it achieved; the Validator records the marked clause
  UNEXERCISED, never PASS, on a fresh mount inside the marked span) — and
  applied it to steps 5 (documented as a deliberate best-effort exception,
  per FINDING 3's own disposition), 8 and 9.
- **AC-3**: Preconditions now mandate a fourth fixture file (≥3 KB, multi-
  chunk); step 6 now opens that specific file, so the ordering clause has
  something to fail against instead of being vacuously true on a single-chunk
  fixture.
- **AC-4**: step 2's cleanup deletion moved out of the Expected Results
  column into Actions; Expected Results now states a falsifiable
  post-condition (the inventory shows only the first knowledge base after
  the deletion action) rather than an imperative instruction sitting where a
  judgment belongs.
- **AC-5**: step 8's "the edited file re-indexes" clause rewritten against
  Leg 2a's real observables — the per-item `data-testid="kb-item-indexed-at"`
  timestamp and `GET /status`'s `content_freshness` — and explicitly states
  that a **folder-level** `indexed_at` advancing is NOT evidence for the
  clause (per the 2026-09-18-reverify run log's own correction), so a future
  run cannot cite the wrong timestamp and pass vacuously again.
- **AC-6**: `Status` → `active`. `Last Run` left untouched, as instructed —
  the Flight Director's run skill owns that field. Validated against
  `.flightops/ARTIFACTS.md`'s required sections: Intent, Preconditions,
  Observables Required, Steps, Out of Scope all present; Variants present
  and optional.
- **AC-7**: Preconditions still name a non-default port and scratch data
  directory, and still reference CLAUDE.md's safety rule by name rather than
  restating credential mechanics.

No assertion was weakened to make it pass — every changed clause became
*more* falsifiable (a real fixture to order, a real observable to read, a
real in-flight item to interrupt), never a happy-path softening. File:
`tests/behavior/kb-studio-round-trip.md`.

### Part 2 — `large-folder settle` variant (AC-8/AC-9)

Added to `tests/behavior/kb-folder-index-round-trip.md`'s Variants section,
reusing `live-kill`'s existing 2,000 × 50 KB generator rather than authoring
a second one (AC-8) — registered at initial Step 2 instead of Steps 9-10, with
dense sub-2s sampling through Step 3's window instead of a single terminal
read, so the `starting`→`watching` and `running`/`idle` transients (F4
debrief Rec. 3) are actually observed rather than raced past. States its own
flake profile honestly, as `live-kill` does (AC-9): no SIGKILL race to lose,
but it can still pass vacuously on a fast disk / warm embedding cache, in
which case the run log must say the tolerance was not exercised rather than
claim it was proven.

### Part 3 — the gates (AC-10–AC-15)

#### AC-10 — `make lint`: **PASS**

```
ruff check the_one/ tests/ scripts/          # All checks passed!
ruff format --check the_one/ tests/ scripts/ # 452 files already formatted
```

#### AC-11 — `make test-unit`: **PASS, cited rather than re-run**

This leg's changes are markdown-only (confirmed via `git status`: every file
this leg touched is a `.md`/spec file — no `the_one/`, `tests/*.py` or
`scripts/*.py` edits), so per the leg's own instruction the Leg 3
(`measurement`) run alone-and-foreground is cited rather than burning another
~11 minutes:

**4,809 passed, 10 skipped, 616 deselected, 1 failed** in 674.88s. The one
failure, `tests/test_kb_watcher.py::TestStopAndDrain::test_drain_three_live_entries_under_a_second`,
was isolated by Leg 3 (passed alone in 0.21s; passed with its whole 39-test
file in 10.38s) and recorded as a real-clock timing flake under host
memory pressure, not a regression — no file this leg or Leg 3 touched has any
relationship to `WatchManager`. Series: F1 3,950 → F2 4,370 → F3 4,547 →
F4 4,649 → F5 4,732 → F6 4,769 → F7 Leg 2a 4,807 → **F7 Leg 3: 4,810
collected (4,809 passed + 1 failed)**, +3 over Leg 2a. This leg adds no
Python tests, so no further delta — the F7 series closes at Leg 3's number.

#### AC-12 — full `TEST_TIMEOUT=3600 make test-browser`, all four lanes: **PASS**

**2 failed, 530 passed, 6 skipped, 12 deselected in 940.50s (15m40s).**

Both failures match the documented squawk-0035 full-lane-only timing-flake
pattern (`conftest.py`'s "Standing pattern — full-lane timing flakes") —
named, isolated, and re-run rather than waved through, per the leg's own
Edge Cases:

1. `tests/browser/test_flow_admin_tools_editor.py::test_test_button_input_pre_filled`
   — a file this flight never touched (`git status` confirms), so treated as
   the ordinary case of the known pattern.
2. `tests/browser/test_flow_provider_editor.py::test_save_and_cancel_disabled_when_clean`
   — this file **was** modified by Leg 2b (`confirm-lapse`, which added lapse
   tests to it), so it got the **stronger** check rather than being assumed
   benign on the flake pattern alone: both failures isolated together passed
   **2 passed in 4.36s**, and the whole file re-run passed **29 passed in
   58.15s**. Recorded explicitly that this one was scrutinised *because* the
   flight touched that file, not waved through.

Neither failure also fails in isolation, so per the leg's Edge Cases neither
is a regression and the leg is not blocked from landing.

Browser lane totals for this run: **530 passed / 6 skipped** across all four
lanes (one combined full-suite run, not a per-lane breakdown — the full run
covers every lane's tests in one pass, satisfying AC-12's "all four lanes,
not a selection"), against Flight 6's recorded baseline of **469 passed / 6
skipped**. *(Note for anyone comparing lane figures across this flight's
log: Leg 2a's `system`-lane figure was corrected earlier in this log from an
inflated 187 to the real 124 collected — that correction stands; it is not
reintroduced or contradicted by this leg's combined total.)*

#### AC-13 — `pip-audit` against the release closure: **NOT GREEN, as expected — recorded against squawk 0083**

Per `ci/README.md`'s "Pre-merge lint + audit gate" recipe:

```
uv export --no-dev --no-emit-project --extra gui --extra all-llms --format requirements-txt \
  | pip-audit --disable-pip -r -
```

Result:

```
Found 2 known vulnerabilities in 1 package
Name  Version ID             Fix Versions
----- ------- -------------- ------------
anyio 4.13.0  CVE-2026-63374 4.14.2
anyio 4.13.0  CVE-2026-64847 4.14.2
```

Exactly the finding squawk 0083 (`open`) already records. Recorded here as
this gate's observed, honest outcome: **not green, and cannot be until
squawk 0083 lands.** The dependency is **not** bumped by this leg.

#### AC-14 — frozen Windows build: **PASS**

Sequenced against Leg 3's ladder first: `fly -t the-one builds` showed the
500k rung (build 76) already `succeeded` at 13:58:47 with nothing running
since, so the worker was free. Launched detached per the build-59 lesson:

```
setsid nohup fly -t the-one execute -c ci/tasks/windows-installer-build.yml \
  -i repo=. -o installer=/tmp/windows-installer-out > /tmp/windows-installer-build.log 2>&1 & disown
```

Build 630446 (`http://localhost:8080/builds/630446`) **succeeded**. Frozen
`the-one.exe doctor` gates all reported `OK`: `child spawn`, `python
interpreter`, `desktop shell`, `llm providers`, `model catalog`, `usearch`,
`fts5`, `embedding model`, `file watcher` — `RESULT: PASS`. Installer
`the-one-setup-0.8.1.exe` (135,040,950 bytes) produced and staged. `make
test-browser` (AC-12) was launched only after this build finished, per the
leg's instruction not to run the two concurrently.

**Discrepancy worth recording so it does not mislead a future reader**: the
frozen build's `usearch` doctor line reads

```
usearch: OK — numkong=no, simd=serial; numkong ext 7.8.2 loads fine [haswell,alder] — this usearch binary was built without numkong
```

while Leg 3's benchmark rows recorded

```
numkong=no, simd=serial; numkong ext will not load (ModuleNotFoundError: No module named 'numkong')
```

Both end at the same `simd=serial` backend, so **no measurement from Leg 3's
ladder is invalidated** — the shipped numbers remain representative. But the
*reasons* differ and must not be conflated: the shipped frozen bundle **has**
`numkong` bundled and it loads fine — `usearch` itself simply was not linked
against it — whereas Leg 3's bench venv had `numkong` **absent entirely**
(`ModuleNotFoundError`). Leg 3's own Edge Cases asked the field to
"distinguish unlinked from missing from linked"; the `doctor` probe (run
against the actual frozen artifact) makes exactly that distinction, and the
bench script's string does not. Two different configurations arriving at the
same `simd=serial` outcome for two different reasons — recorded here so a
future reader comparing the two strings side by side does not conclude they
describe the same environment.

#### AC-15 — documentation reconciled

Added to `CLAUDE.md`: two new paragraphs (confirm-lapse cue; Windows
vector-store measurement / the new `windows-vector-bench.yml` CI task).
Added to `the_one/agents.md`: two corresponding detail blocks (the
confirm-lapse cue's full contract, including squawk 0088's third invariant;
the `windows-vector-bench.yml` task's contract, including the stop-at-500k
decision and `scripts/sweep_fusion_constants.py`). Legs 1 and 2a's own
CLAUDE.md paragraphs (shutdown hook; `get_kb_status`'s additive keys) were
already present from those legs and needed no change — this pass confirmed
they agree with the shipped surface rather than rewriting them.

### AC-16/AC-17 — metrics and recording, as observed

| Gate | Outcome | Notes |
|---|---|---|
| Spec re-author (AC-1–AC-7) | done | `kb-studio-round-trip.md` → `active` |
| Large-folder settle variant (AC-8/AC-9) | done | `kb-folder-index-round-trip.md` |
| `make lint` (AC-10) | **PASS** | ruff check + format --check both clean |
| `make test-unit` (AC-11) | **PASS** (cited) | 4,809 / 10 skipped / 1 flake, isolated; no delta this leg |
| `make test-browser`, full, 4 lanes (AC-12) | **PASS** | 530 passed / 6 skipped / 2 flakes (squawk 0035 pattern, both isolated+rerun clean) |
| `pip-audit`, release closure (AC-13) | **NOT GREEN (expected)** | anyio 4.13.0 × 2 CVEs, squawk 0083, not bumped |
| Frozen Windows build (AC-14) | **PASS** | build 630446, installer produced, all doctor gates OK |
| Doc reconciliation (AC-15) | done | CLAUDE.md + agents.md |

No gate went **not-run**. Every outcome above is recorded as observed,
including the one gate (`pip-audit`) that is honestly not green — per AC-17,
that is the correct record, not a thing to fix by bumping a dependency on
this branch.

### Verification

```
make lint                                    # PASS — see AC-10 above
make test-unit                               # cited from Leg 3 — see AC-11 above
TEST_TIMEOUT=3600 make test-browser          # 2 failed, 530 passed, 6 skipped, 12 deselected, 940.50s
pip-audit (release closure, ci/README.md)    # anyio 4.13.0 × 2 CVEs — squawk 0083, not green
fly -t the-one execute -c ci/tasks/windows-installer-build.yml -i repo=. -o installer=./out
                                              # build 630446 succeeded — installer produced, doctor RESULT: PASS
```

---

### Operator decision, 2026-09-20: commit before running `kb-studio-round-trip`

The flight's Completion Checklist requires that spec **`active` and passing**.
It is `active` (Leg 05, AC-6). The 18-step walk is **not yet run**, and the
flight commits without it.

**Why this is not the Flight 6 failure repeating.** Flight 6 left two checklist
items unowned and unexecuted, which is why Leg 05 exists and why AC-17 says a
gate that did not run is recorded as not-run, never as passed. That rule is
applied here to the flight's own checklist: the item is marked `[~]` with the
run explicitly outstanding and an owner named, and the **mission criterion it
backs stays unticked**. The difference from Flight 6 is not that something was
deferred — it is that the deferral is written down, owned, and blocks the
criterion rather than quietly passing it.

**What the flight actually owed, and delivered**: the re-author. Six structural
defects (five from the spec's status line, a sixth found only in the run logs)
are fixed, and the spec validates against `.flightops/ARTIFACTS.md`'s format.
Proving the full walk green is mission-close work: it needs a dedicated dev
instance, two live agents, and the newly-mandated second fixture folder sized
so the restart-resume step is winnable rather than vacuous.

**Scheduled**: before the flight's PR merges into `mission/24-knowledge-bases`.

## Behaviour test — `kb-studio-round-trip` clean run (2026-09-22)

The run the flight's last unticked acceptance item was waiting on. Spec was
`draft` since 2026-09-21, reverted after its previous 18/18 run surfaced four
further structural defects plus one under-scoped clause.

**Result: 17 pass / 1 inconclusive / 0 fail** across all 18 checkpoints.
Run log: `tests/behavior/kb-studio-round-trip/runs/2026-09-22-01-05-35.md`.

**Two process corrections from the previous run's Validator were adopted in full.**
Checkpoints were run **strictly one at a time** — 18 separate Executor→Validator
round-trips — rather than batched; the previous run batched 5-7 and 11-13, and its
Validator's assessment was that the clean result *"doesn't retroactively justify the
batching, it just means we got lucky that nothing broke inside a batch."* And
Validator reasoning was never relayed to the Executor: the run's one cross-agent
procedure (step 13-bis) was issued as a bare sequence of actions with no indication
of what any outcome would imply.

**What this run proved that no previous run did.** Step 5's `[continuous-session]`
clause and step 9's full step-2-to-9 continuity span were **exercised for the first
time** rather than recorded UNEXERCISED. Step 9's span was verified by two
independent outside readers — the Flight Director and the Validator, separately,
via read-only CDP `evaluate` calls neither agent could have coordinated to fake.
Step 8's rewritten `content_freshness` clause reproduced the exact phenomenon that
forced its rewrite — the aggregate equalled the *new* file's timestamp, not the
*edited* file's, diverging ~1.09 ms (prior run: 1.868 ms) — and **passed**, where
the old equality clause would have failed correct behaviour. The Validator
recomputed the maximum itself rather than accepting the reported one, and judged
that the rewrite *"is doing its intended job, not just being lenient."*

**Step 5's routing was overridden deliberately.** Crew protocol sends wait-point
rows straight to the Validator, which observes independently — but that is a fresh
mount, which by the spec's own partial-exception rule would have recorded the
`[continuous-session]` clause UNEXERCISED before it could be tried. Routed to the
Executor's continuous page instead. Following the generic protocol would have
silently lost a clause that was in fact exercisable.

### New spec defect #15 — found, fixed, and the fix verified in-run

Step 13 came back with `disabled_tools` erased after an unrelated save. Rather
than record a DD-13 regression, the confound was surfaced **as fact, not
conclusion**: step 12 sets the entry via an out-of-band API `PUT` — the only path
that exists, since there is deliberately no UI for it — while step 9 mandates one
unbroken page, so by step 13 the client's in-memory config necessarily predates the
`PUT`. **The Validator held its verdict** and specified a discriminating experiment
rather than ruling either way on the available evidence.

Step 13-bis: re-add via `PUT`, force a full reload (the continuity marker going
`kb-studio-rt-…` → `null` is falsifiable proof of a genuine remount, not a
hash-only no-op), confirm the entry present server-side **before** saving, then an
unrelated save from the fresh page — **the entry survived**. DD-13's client-side
union works correctly when the client has current knowledge of the field.

Verdict: **inconclusive — the test failed, not the system.** Two
individually-correct requirements collided. Fixed in the spec by inserting an
explicit fresh-load beat between steps 12 and 13; **the corrected sequence was
itself executed during this run as 13-bis and passed**, so the fix ships verified
rather than merely reasoned.

### Findings carried out of the run

- **Product finding, recommended as a flight rather than a squawk** — Studio's
  agent-editor save is last-writer-wins with no staleness detection. An
  out-of-band config change made while a tab is open is silently discarded by that
  tab's next unrelated save: no version check, no conflict warning, no signal to
  the operator. Plausible real operator sequence, because an operator may set
  `disabled_tools` by script *precisely because no UI exists for it*. Inconsistent
  with staleness patterns this codebase already applies elsewhere (`if_version`
  gating; the self-configuration restore path's fail-closed-against-staleness
  behaviour). **It fails the squawk gate** on two of four criteria — the fix needs
  a design decision (detect how? block, warn, or refetch?) and touches a shared
  interface — so it is raised as a flight candidate rather than logged as a squawk.
- **Literal restart-resume remains unproven.** Step 10 won the race on the first
  attempt (+0.0424 s, with the transition bracketed 9.6 ms on the other side) but
  caught the snapshot at `indexed: 0` — the spec's own named evidence ceiling.
  Aggregate resume is well-evidenced; the `content_hash`-survival mechanism the
  spec describes was never exercised. Closing it needs a larger/slower fixture or a
  throttled pass. The Executor reported the ceiling plainly rather than silently
  retrying for a better number.
- **Apparatus: untracked pages spawn during error recovery.** A second, unattributed
  page sat in the shared CDP context adjacent to the run's most load-bearing
  evidence, found by the Flight Director's independent verification. It was debris
  from an aborted script. *"Exactly one page" is an invariant nobody enforces; it
  was discovered by accident.* Closed at checkpoint 11; must be enforced before this
  apparatus runs unattended.
- **Evidence-capture defect.** Two step-6 screenshots asserting a pre-/post-probe
  distinction were **byte-identical** (`md5` verified independently by the Flight
  Director, not taken on the Validator's word) and framed only the top of the panel,
  so neither depicted the ordering they were captured to prove. The verdict survived
  only because the Validator generated its own artifact. Same *instrument cannot
  detect what it claims to* family this mission keeps producing — and the fourth
  distinct instance in Mission 24.
- **Three weakly-falsifiable clauses named** by the Validator for a future revision:
  step 3's "no error shown" (nothing adversarial forces it), step 5's timing clause
  (registration completes the pass in ~80 ms, so the reconcile walk is never
  exercised by that wait), and step 7's degrade branch (only the `degraded: null`
  branch is reachable in this scenario; the named branch has never been falsified by
  any run of this spec).

### Unrequested rigour worth recording

At step 6 the Executor intercepted the chunks response and re-served the same 15
objects in **reversed** `seq` order; the UI still rendered ascending, proving
client-side re-sorting empirically rather than by reading the JS — then separately
curled the endpoint to confirm the API's own order was ascending too, closing the
gap that the client sort would otherwise hide. At step 18 it went **looking** for a
log-level error rather than stopping at "no visible error," surfaced two
`WARNING` lines verbatim, and declined to characterise them — leaving the
interpretive call to the Validator, which made it explicitly.

### Note on the flight artifact

`### Checkpoints` (flight.md:612) is largely unticked even though most of its items
were demonstrably delivered — it appears never to have been tick-maintained during
the flight, unlike `### Completion Checklist`, which was reconciled before landing.
Only the two items this run and squawk 0083 actually closed were ticked there; the
rest were left alone rather than swept, since ticking items without verifying them
is the exact habit this mission's debriefs keep flagging.

## Session Notes

**2026-09-19** — Flight planned, Architect-reviewed, and marked `ready`. Two
questions the review re-opened were returned to the operator and settled the
same day: DD-11 becomes comment-only (the rename is the component mission's),
and DD-7's skip counters live in `app_metadata` with the leg owning explicit
cleanup on both delete paths, since a kv key is outside `kb_items`' cascade.

**Artifacts are uncommitted, deliberately.** They were authored while the
working tree sat on `squawk/turnaround-2026-09-19`, whose PR #208 is still
open. Committing them there would put flight-planning work inside a squawk PR,
which is exactly the kind of mixed record the squawk convention exists to
prevent. They carry across the branch switch cleanly (one untracked directory
plus a modified `mission.md`) and belong on the flight branch, cut from
`mission/24-knowledge-bases` after #208 merges.

Prerequisites outstanding: PR #208 unmerged; squawks 0083 and 0050 open;
Concourse worker re-verify deferred into Leg 3's first step.
