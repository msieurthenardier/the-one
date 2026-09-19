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
