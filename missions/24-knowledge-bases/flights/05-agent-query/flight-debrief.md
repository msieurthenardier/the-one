# Flight Debrief: Agent Query

**Flight**: [05-agent-query](flight.md)
**Mission**: [Knowledge Bases](../../mission.md)
**Status**: completed
**Debriefed**: 2026-09-17
**PR**: #204 (ready for review against `mission/24-knowledge-bases`, not yet merged)

---

## Outcome

The objective was met in full. An attached knowledge base is answerable by
its agents, proven against a live process rather than inferred from unit
tests.

**Mission criteria advanced:**

- *Retrieval combines semantic and keyword matching…* — **met**.
  `the_one/knowledge/retrieval.py` fuses the vector store and FTS5 by
  reciprocal rank, with one slot reserved for a keyword-only hit.
- *An attached agent can discover and query its knowledge bases… and cannot
  reach one it is not attached to* — **met**, behavior-test-backed.
- *A knowledge base can be attached to and detached from any agent* — the
  functional half landed; the Studio surface is Flight 6's.
- *Existing installs upgrade with no data loss…* — **held**. No schema
  change, no dependency change; frozen build `RESULT: PASS`.

**Checkpoints**: all three met. **Legs**: three, all `completed`, both
implementation legs with **zero deviations** from spec.

**Gates** (all by hand — no CI lane on mission-branch PRs): `make lint`
clean; `make test-unit` 4,732 passed / 10 skipped / exit 0; behavior test
8/8; frozen Windows `RESULT: PASS` with nine doctor gates; installer
+47,623 bytes (+0.035%), accounted to within ~300 bytes of the new modules'
source plus bytecode. `pip-audit` reported 6 advisories, verified as upstream
and escalated as squawks 0071/0072 rather than absorbed.

---

## Test Metrics

Debrief run (backgrounded): **4,732 passed, 10 skipped, 0 failed, 606.19 s,
exit 0.** No flakes, no retries.

| Point | Passed | Wall (s) | ms/test |
|---|---|---|---|
| Flight 1 debrief | 3,950 | 466.75 | 118 |
| Flight 2 close | 4,370 | 499.22 | 114 |
| Flight 3 debrief | 4,547 | 638.25 | 140 |
| Flight 4 Leg 4 gate | 4,649 | 653.19 | 141 |
| Flight 4 debrief | 4,649 | 636.62 | 137 |
| Flight 5 Leg 3 gate | 4,732 | 654.30 | 138 |
| **Flight 5 debrief** | **4,732** | **606.19** | **128** |

**+83 tests** at flat per-test cost. The debrief run landed at the low end of
the established 114–141 ms band — ~8 % faster than this flight's own closing
gate on an identical test count, which is host-load variance both the Flight 3
and Flight 4 debriefs already characterised as noise. No directional drift;
Flight 4's conclusion that the Flight 3 step was one-time continues to hold
across two more data points.

The count reconciles exactly against the flight log's own accounting: Leg 1's
in-flight 4,688 plus Leg 2's 35 + 5 + 4 = 44 lands on 4,732.

---

## What Worked

- **Premise probes at planning.** Ten (P1–P10), of which two changed the
  design before a line was written (P7's incomparable score scales forced
  rank-only fusion; P8's `get_many` tolerance made crash window (b) free) and
  one — `/ws` auth — was deliberately flagged unresolved rather than assumed,
  then resolved during review. The payoff was measurable: Leg 3's premise
  audit was a re-verify with **zero** spec corrections.
- **Proving a pass bar falsifiable.** DD-3's crowding test was independently
  recomputed three times by three different agents, and the Leg 1 Developer
  removed the reserved-slot block to confirm the test actually fails without
  it. A pass bar that would pass either way protects nothing; this flight
  treated falsifiability as something to demonstrate, not assume.
- **Promoting a measurement to a contract.** DD-2 rested on a measured
  property of the one embedding backend. Leg 1 added "must be safe to call
  concurrently from multiple threads" to `EmbeddingBackend`'s Protocol
  docstring, converting a property of today's implementation into an
  obligation on the next one.
- **Escalating rather than absorbing.** The `pip-audit` findings and the
  `the_one/vectors/` scope widening both went to the operator as decisions
  rather than being folded in quietly.
- **Backgrounding the gate worked.** Leg 1's foreground `make test-unit` was
  externally terminated at 86 %; every subsequent run was backgrounded and
  none was. The mitigation is confirmed working.

---

## What Could Be Improved

### Critical — a recurring spec-authoring failure now in its third flight, with the fix already prescribed and never adopted

Twice this flight a rule was corrected in one place while the superseded
version was left **upstream of it**, where a Developer reads first:

- DD-1's numbered "authoritative ordering" still specified the cancelled
  `asyncio.wait_for` after a later bullet replaced it (Architect cycle 3).
- Leg 2's AC-7 still specified the `kb_id[:6]` discriminator after AC-9
  replaced it with a fixed-length hash (Leg 2 cycle 2).

Both were caught only by a reviewer reading in **Developer order** rather
than author order. The sharp detail on the first: the precedence clause that
elevated the stale text ("this numbered list is the authoritative ordering")
was added by the Flight Director *to remove ambiguity*. A precedence clause
is only safe when the authoritative block is the sole statement of the rule.

**This is not new.** The Flight 3 debrief recorded the same class and
prescribed the fix verbatim: *"Both times the fix was local when the rule was
general. When a review finds a transition-table or loop-exit defect, state the
general rule in the DD and grep the spec for every sibling site before the
next pass."* That recommendation stayed a recommendation. Flight 4 saw a
variant; Flight 5 saw two more. **A debrief recommendation that is not
converted into a standing instruction does not survive contact with the next
flight** — which is precisely what the squawk mechanism exists to prevent,
and the meta-lesson of this debrief.

Three structural fixes, in increasing cost, all from the Architect:

1. **One normative home per rule.** A rule that has already produced a review
   finding gets exactly one code-shaped authoritative statement; every other
   mention is a pointer, never a paraphrase. Prose invites restatement, and
   each restatement is a future stale copy. This is why restating DD-3 as
   pseudocode ended that ambiguity where three prose revisions had not.
2. **A supersession sweep.** Every correction names the superseded literal
   token, and the disposition is not complete until a grep for that token
   across all artifacts returns zero. Both instances this flight were
   single-token greps (`wait_for`, `kb_id[:6]`). Mechanisable.
3. **Read-in-Developer-order as a named review pass** in the crew file — read
   the numbered ACs and order-of-work top to bottom, implementing mentally,
   before reading the rationale prose.

### Critical — the flight spec has no Citation Audit, and every Class A defect lived there

Sorting the eight flight-level high findings by what it would have taken to
catch them:

- **Class A (5 of 8) — claims about code the spec asserted without
  re-reading.** DD-2's "latency is never coupled to indexing" (`query`
  visibly takes `entry.lock`); the plain-`gather` degrade; DD-7's three
  non-existent mechanisms; `kb_id[:6]` uniqueness (client-supplied ids, one
  read of `api.py`); `source_index or {}`'s falsy bind. Every one is a
  five-minute read away — and the planning notes list those files as read at
  flight start. **These were assertions made from memory of a read.**
- **Class B (1) — a genuine discovery.** The `wait_for` lock hazard needed a
  probe. This is the process at its best.
- **Class C (2) — defects introduced by the fixes themselves**, i.e. the
  stale-text pair above.

**Both leg specs carry a Citation Audit table; `flight.md` does not.** Leg 1
shipped with zero design-review highs; Leg 2 with zero deviations. The flight
spec, where all five Class A errors lived, has no such table. All five would
have been rows that failed it.

**Recommendation**: require a flight-level Citation Audit before the first
Architect cycle — one row per design decision that asserts a code mechanism
(signature, control flow, exception type, mutability, cardinality), each
carrying `file:symbol` and a verified mark. Highest-leverage single change
available from this flight.

### Important — a structure carried over from a sibling subsystem whose precondition was void

DD-7's `source_index` entry was **wrong from the start**, not superseded.
`source_index` exists so a query naming an MCP *server* selects all its tools
en bloc; its entire value comes from cardinality — one source, **many**
tools. DD-4's first line commits to **one tool per knowledge base**. At
cardinality 1 the union is provably empty of new members. Every fact needed
for that proof was in the flight's own DD-4 at planning time.

The tell, and the generalisable rule: **Leg 2's review found that the test
protecting the entry would pass with the entry deleted.** *If no test fails
when a structure is removed, the structure is not load-bearing — delete it
rather than writing another rule to protect it.* Three separate defects
(the DD-5/DD-7 ordering contradiction, the falsy-bind trap, the description
plumbing gap) were all downstream of keeping it, and all three vanished by
construction when it was dropped.

The broader rule: **when copying structure from a sibling subsystem, name the
invariant that makes it earn its keep and check it holds in the new context.**
Cardinality changes (N→1) void nearly all index/grouping/en-bloc machinery.
Notably the flight *did* apply this reasoning correctly elsewhere — DD-4
rejected the `MCPClientTool` drop-on-over-length precedent because "one tool
of many" does not transfer when the drop costs a knowledge base's only tool.
The capability is present; it needs applying systematically rather than where
it happens to occur to the author.

### Important — design review and behavior-test execution catch different defect classes

Five review cycles found zero of the behavior spec's own verification-
methodology gaps. One live run found a **false-pass hazard**: Step 9 cannot
distinguish a working blacklist from a silently detached knowledge base,
because both produce byte-identical output. Four further evidence
requirements the run depended on were unwritten; without them three of eight
verdicts would have been INCONCLUSIVE.

The general property, worth adding to behavior-test authoring conventions:
*a step whose expected result is an error, an absence, or a refusal has no
error budget left — any confounding cause produces the same observable, so
the assertion collapses to "something went wrong," which was already
guaranteed.* Three proposed rules:

- **Negative expectations require a positive state readback.** If two system
  states would yield byte-identical output, the step tests neither until it
  reads back which state obtained.
- **Full-replace mutations read back what they did not intend to change**,
  before driving the behaviour under test.
- **An absence cannot be proven from an excerpt.** Capture the complete
  observable and state the completeness criterion.

Note the spec showed exactly this scrutiny one row earlier for a *different*
confound — so this is unsystematic application, which is what a checklist buys.

### Minor — naming was under-budgeted

The flight design treated Leg 2 as "a third block that reads like the
second" and under-budgeted **naming**, which consumed five of Leg 2's ACs,
two design cycles and two of the flight's high findings. Tool names are
LLM-visible, name-keyed in `disabled_tools`, length-capped, derived from a
mutable operator-supplied field, and collision-prone by construction. Any
future flight minting LLM-visible tool names should budget naming as its own
risk area, reasoning about cardinality, mutability, collision and length
before the first review cycle.

### Minor — a fix added during review got lighter scrutiny than the original design

The empty-knowledge-base short-circuit was added at cycle 1 and deleted at
cycle 2 as costing more than it saved (an O(n) `COUNT(*)` on the agent hot
path to avoid a 0.08 ms embed). Generalise: *a fix proposed during review
gets the same citation and arithmetic scrutiny as the original design.*

---

## Technical Debt

**Introduced, deliberately and recorded:**

- **DD-12, no per-item diversity.** With 150-character chunk overlap the top
  `limit` can be adjacent windows of one file. Deferred to a recall benchmark
  that does not exist.
- **Un-measured constants.** `RRF_K = 60`, `candidate_k`, and
  `SEMANTIC_QUERY_TIMEOUT = 2.0` are validated only against constructed
  synthetic cases. This is "no measurement" debt accumulating in the one
  subsystem the mission criterion is about; it should be paid before mission
  close, not after.
- **`SEMANTIC_QUERY_TIMEOUT` at scale.** Defensible today. At the mission's
  upper corpus size a flush is ~24 s, so during a large re-index *every*
  agent query degrades to keyword-only for the flush's duration, repeatedly,
  with no operator dial and no correlation to indexer state.

**Found at debrief, not previously recorded:**

- **Tool-name machinery is duplicated across packages** (verified):
  `_TOOL_NAME_MAX_LEN = 64` in both `mcp/_tool.py:39` and
  `knowledge/tool_provider.py:61`; `_normalize_source_name` and
  `_normalize_kb_name` behaviourally identical in two packages; prefix
  knowledge spread across `_search_tools.py` (`_MCP_PREFIX`, `_KB_PREFIX`)
  and `agent/config.py` (`UNGATED_TOOL_PREFIXES`) with no single source of
  truth; and the `split("__", 2)[1]` label parse — with its known
  embedded-`__` flaw — now in two branches. Each instance was defended
  per-decision as package hygiene; in aggregate it is a pattern, and a third
  namespace triples it. **Recommend a shared `the_one/tools/naming.py`
  before a third prefixed namespace lands.**
- **A third crash window of the same shape.** Leg 1's review found an
  item-deleted-between-awaits window matching the two Flight 3 recorded.
  Three ad hoc instances of "separate awaits over one shared connection are
  not a snapshot," each documented individually. Worth promoting to a named
  project convention so the fourth is designed for rather than found.

---

## Key Learnings

1. **A debrief recommendation that is not converted into a standing
   instruction does not survive the next flight.** Flight 3 prescribed the
   exact fix for the stale-rule class; Flights 4 and 5 hit it three more
   times. This is the meta-lesson, and it argues for converting debrief
   findings into squawks aggressively rather than trusting them to be
   remembered.
2. **Assertions made from memory of a read are the dominant defect class in
   spec authoring** — five of eight highs. A citation table converts that
   from a discipline problem into a mechanical one.
3. **Cardinality is the invariant to check when copying structure between
   subsystems.** N→1 voids indexing, grouping and en-bloc selection
   machinery wholesale.
4. **Falsifiability is something to demonstrate, not assert.** Removing the
   rule and watching the test fail is cheap and is the only thing that
   distinguishes a pass bar from decoration.
5. **Review and live execution catch disjoint defect classes.** Five review
   cycles found zero verification-methodology gaps; one run found four.

---

## Follow-Up Actions

| # | Item | Disposition |
|---|---|---|
| 1 | Behavior spec's unwritten evidence requirements + Step 9 false-pass + Step 6 ambiguity | **squawk 0073** |
| 2 | Recurring stale-rule class → standing methodology instruction (supersession sweep, one normative home, Developer-order review pass) | **squawk 0074** |
| 3 | Flight-level Citation Audit required before the first Architect cycle | **squawk 0075** |
| 4 | Name the waiter-bound/holder-unbounded lock-timeout shape in `agents.md` conventions | **squawk 0076** |
| 5 | Crowding arithmetic (`2/(60+r) > 1/61`) as an inline comment in `_fuse`'s docstring | **squawk 0077** |
| 6 | Name `multi-await-reads-are-not-snapshots` in `agents.md` Project Conventions | **squawk 0078** |
| 7 | Shared `the_one/tools/naming.py` before a third prefixed namespace | **Flight 6 or mission close** — needs design, not a squawk |
| 8 | **Knowledge-base rename dangles name-keyed `disabled_tools` entries** (verified: `update_knowledge_base` merges `name`; the tool name derives from it). DD-4 reasoned about reorder and attach/detach but never rename — and Flight 6 adds the rename affordance | **Flight 6 planning open question** |
| 9 | Squawk 0050 is now a live data-loss path, not latent — a Studio save wipes `kb_ids` | **Flight 6, before or with the Knowledge tab**; its behavior test must assert `kb_ids` survives an unrelated save |
| 10 | Name-length hint on the Studio knowledge-base name field (DD-4 carry-forward) | **Flight 6** |
| 11 | Flight 6's inventory should call `search()` directly and render `SearchResult.degraded` — the stated justifications for DD-1's module shape and result object | **Flight 6**; if neither happens, revisit both decisions |
| 12 | Correlate the degrade line with indexer state in `/status` | **Flight 6** — the mitigation for the `SEMANTIC_QUERY_TIMEOUT` concern |
| 13 | Recall/precision benchmark against a real corpus; evaluate `RRF_K`, `candidate_k` and DD-12 together | **mission close** |
| 14 | `pip-audit` advisories | **squawks 0071, 0072** (already logged) |

---

## Skill Effectiveness

**Mission skill** — adequate. The two open questions it carried (fusion
balance; prefix generalisation) were both settled at this flight's planning,
which is what they were for.

**Flight skill** — the gap this flight exposes is the missing **flight-level
Citation Audit**. The leg template has one; the flight template does not, and
the flight spec is where code-mechanism claims concentrate. Worth raising
upstream as a plugin-level suggestion, not just a project convention.

**Leg skill** — worked well. Both legs shipped zero deviations, and the
Citation Audit tables in both were checked rather than trusted by their
reviewers. The risk-tiering call (Legs 1–2 high, Leg 3 low with its review
skipped and the reasoning recorded) held up: Leg 3 needed no rework.

**Behavior-test skill** — the authoring conventions need the three negative-
assertion rules above. The execution protocol worked well; live two-agent
mode was materially better than re-spawn here because the Executor built the
WebSocket driver once and reused it across five turns.
