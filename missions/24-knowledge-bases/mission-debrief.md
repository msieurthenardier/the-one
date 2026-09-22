# Mission Debrief: Knowledge Bases

**Date**: 2026-09-22
**Mission**: [Knowledge Bases](mission.md)
**Status**: completed
**Duration**: 2026-09-06 – 2026-09-22 (16 days)
**Flights Completed**: 7 of 7

## Outcome Assessment

### Success Criteria Results

| Criterion | Status | Notes |
|-----------|--------|-------|
| Register a folder as a source; see each item's index status including failures | **Met** | F3 `kb-folder-index-round-trip` 8/8 for the API half; F7 `kb-studio-round-trip` ckpt 3/5 for the operator surface — `corrupt.txt` rendered `failed` with "binary content" legible on the row, visibility confirmed three ways |
| Files index automatically; adds, edits and deletes reflected with no operator action or restart | **Met** | F4 `kb-folder-watch-round-trip` 9/9 — all three verbs in one filesystem-only pass, no `reindex`; F7 ckpt 8 re-confirmed on the operator surface |
| Large folder indexes in the background without blocking the UI, and resumes rather than restarts | **Partial — deliberately unticked** | The *resume* half is proven (F3 step 10's seeded-resume assertion). The *large-folder-without-blocking* half is evidenced by **no executed test**: the `large-folder settle` variant written for exactly this was authored in F7 and never run, and neither was `live-kill` |
| Inspect contents and metadata; retrieve source behind any indexed item | **Met** | F7 ckpt 6 — chunk order falsified by an intercept probe that re-served the chunks reversed; source byte-identical to disk, sha256 matching the stored `content_hash` |
| Embedding backend bundled, local, non-LLM; no account, network or external service; no contents leave the machine | **Met** | 63 MB model in-tree; frozen `the-one doctor` resolves it from inside the bundle (build 78, post-`anyio` bump). *Nuance kept*: "no contents leave the machine" is evidenced by construction, not by an egress test |
| Retrieval combines semantic and keyword matching | **Met** | F5 — RRF fusion with a reserved keyword-only slot; F7's fusion sweep confirmed the constants are load-bearing by evidence rather than tuned |
| **A different vector store** can be introduced without modifying the indexing pipeline | **Met** | Stronger than originally claimed — **three** independent test implementations satisfy `VectorStore` in full and drive `index_item`/`IndexingManager` end to end with `indexer.py` untouched. Known cost recorded: v41 froze `kb_vector_index`'s sidecar shape |
| **A new file-format handler** can be introduced without modifying the indexing pipeline | **Not met — falsified at mission close** | `index_item` applies an unconditional binary sniff (`indexer.py:155`) *before* calling the resolved extractor (`:159`). A `.docx` is a ZIP with null bytes at offset 4, so the deferred PDF/Office handlers would be rejected before `extract` ran. **I ticked this earlier the same day and was wrong**; the Architect falsified it with executed evidence |
| A knowledge base can be attached to and detached from any agent in Studio | **Met** | F7 `kb-studio-round-trip` 2026-09-22. Attach at ckpt 9 (presence in the tab's list *before* attaching is the load-bearing half); detach at ckpt 18 via DD-14. *Gap named*: detach is evidenced through delete-and-save, not a UI toggle-off |
| An attached agent can query its knowledge bases and cannot reach one it is not attached to | **Met** | F5 `kb-agent-query-round-trip` 8/8 — attached agent retrieved fixture prose from disk; unattached agent got `Unknown tool` with no KB content |
| Existing installs upgrade with no data loss; unit gate green; frozen Windows installer builds and runs | **Met** | `test_db_migration.py`; 4,809 unit passed / 10 skipped; 530 browser passed; frozen build `RESULT: PASS`, re-verified as build 78 after squawk 0083 |

**9 of 11 met** (the extensibility criterion was split at mission close). One partial, left unticked on purpose; one **falsified and corrected** — see the Architect's assessment.

All nine mission open questions are closed. Three were reconciled at mission close (2026-09-22) rather than at the point they were answered — including one that read "No longer an open bet" while still carrying an open checkbox.

### Overall Outcome

**The mission achieved its stated outcome.** An operator points the app at a folder; its documents are indexed, kept current with no further action, attached to whichever agents should have them, and reachable by those agents and no others — on a fresh install, with no account, no API key and no network.

The outcome was still the right goal at the end. The one scope amendment (DD-2, at Flight 2 planning) *narrowed* it in the right direction: an earlier draft let the operator choose between embedding backends and warned when a choice sent contents off-machine. Removing that choice made "no file contents leave the machine" an invariant instead of a setting.

## Flight Summary

| Flight | Status | Key Outcome |
|--------|--------|-------------|
| 01 dependency-and-packaging | completed | Proved the dependency closure packages and loads in a real Windows PyInstaller bundle, for both vector-store candidates, before any product code depended on it |
| 02 storage-and-embedding-foundation | completed | v40 schema with a real item lifecycle, the `VectorStore` Protocol seam, and the bundled local embedder. Every later flight builds on it |
| 03 folder-registration-and-indexing | completed | A knowledge base becomes usable from the API: registration with containment validation, stat-only walk, background worker that resumes rather than restarts |
| 04 change-monitoring | completed | The index follows the folder with no operator action — per-folder watcher with a reconciliation walk as the actual source of truth |
| 05 agent-query | completed | `kb__{slug}__search` per attachment; RRF fusion with a reserved keyword slot; attachment *is* authorization |
| 06 studio-surfaces | completed | The operator-facing surfaces, seen by the operator: Knowledge section, agent Knowledge tab, Administration panel |
| 07 mission-close | completed | Four obligations that had outlived their flights, two measurements the mission asked for and never took, every release gate run by hand with a named owner |

## Architect's Assessment

An Architect reviewed the mission's architectural evolution across all seven flights, with four claims verified by **execution** rather than reading — deliberately, because this mission's dominant defect class is an instrument that cannot detect what it claims. Its findings changed two entries in this debrief and one mission criterion. The full input is summarised here; the corrections have already been applied above.

**Verdict: architecture improved, with three narrow and named degradations.** Three well-shaped Protocol seams (`EmbeddingBackend`, `VectorStore`, `Extractor`), all structural-satisfaction with lazy-import dispatchers; a third instance of `supervised-per-entity-worker` that promoted the shape from precedent to documented convention; `db-writes-hold-the-write-lock` shipped lint-enforced and never needed widening across six legs; doctor gates 6 → 9. The degradations: a second threading model (one daemon thread per folder, capped at 64); `kb_vector_index`'s usearch-specific shape frozen into migration v41; and a request-protocol invariant living in the client (`studio.js:2420`), duplicated across a language boundary with **nothing binding the copies** — verified absent two ways.

**It corrected me on the extensibility criterion**, which I had ticked whole earlier the same day. Splitting it was right: the vector-store half is better evidenced than the mission originally claimed, and the file-format half is falsified for exactly the formats the mission defers. I verified the falsification independently before acting on it.

**Two defects it found that no flight caught**, both with a one-line fix and both now action items:

- **A residual window in the shutdown path.** `IndexingManager.stop` writes `_cancel_report[kb_id] = cancelled` at `manager.py:262` **before** the shutdown flush at `:268`. If that `wait_for` expires mid-`index.save`, the `TimeoutError` is merely logged, the lock releases, the save thread runs on — and the kb_id is **not** in `cancelled_kb_ids()`, so `close_vector_store` re-flushes it concurrently, writing the same fixed temp path. That is precisely the torn save DD-3a exists to prevent, reached through the other arm of the same `if/elif`. The Architect demonstrated the underlying asyncio property by execution: cancelling an `await asyncio.to_thread(...)` releases the lock but **does not stop the thread**, and a second flusher can acquire the lock while the first is still mutating. **The instrument gap has the same shape as the hole**: `shutdown_flush_timeout` appears in exactly one test, which asserts the *non*-timeout path.
- **`compute_tool_names`' docstring asserts set-independence unconditionally**, while the widening loop is exactly the exception — and under exhausted widening the returned colliding name becomes a **silent dict overwrite** in `ToolRegistry.register`, so an agent loses a knowledge base's tool with no error anywhere. Astronomically unlikely; trivially cheap to make loud. The residual was recorded in the F6 flight spec and absent from the docstring — *"on the record in the place nobody reads and absent from the place everybody reads."*

**On DD-13, it disagreed with the framing of the question I asked** — usefully. A server-side merge would **not** fix the 2026-09-22 symptom, because no merge rule fixes staleness: even a perfect preserve loses an out-of-band write when the client sends an explicit value derived from a stale read. And the problem is not `disabled_tools`-specific; `system_prompt`, `description` and `enabled_tools` are all last-writer-wins today. `disabled_tools` is merely where it surfaced, *because it is the one field with no UI*, which makes out-of-band writes the normal way to set it. It named an asymmetry worth recording: **an agent's self-revision is fail-closed against operator drift (`api.py:1334-1366` returns 409 with an `?override=true` escape); the operator's own Studio save is not** — and Studio already fetches the agent fresh on editor mount, so it *holds* the token and simply does not send it.

**The scaling finding that appears in no debrief.** `UsearchStore._ensure_loaded` uses `Index.restore`, a full in-RAM load, chosen deliberately but for an unrelated reason (the `os.replace` property on Windows); the RAM consequence is recorded nowhere. There is **no eviction path** — `self._kbs` is popped only in `delete_kb` — so every knowledge base whose index is touched stays fully resident for the process lifetime, and N knowledge bases sum. At the mission's own declared ceiling:

| Raw text | Chunks | Resident f16 vectors |
|---|---|---|
| 1 GB | 1.26 M | **1.20 GiB** |
| 2 GB | 2.53 M | **2.41 GiB** |
| 3 GB | 3.79 M | **3.61 GiB** |

Plus the HNSW graph and the ~250 MiB embedding-model footprint, in a frozen Windows desktop app, with no per-KB ceiling surfaced to the operator. The storage arithmetic was done for **disk** at Flight 1 and never for **RAM against the ceiling**. It pairs with F5's flagged `SEMANTIC_QUERY_TIMEOUT = 2.0`: at the ceiling a flush is ~24 s, during which every agent query degrades to keyword-only, repeatedly, with no operator dial. Same story from two directions — **what happens at the declared ceiling has not been measured at all**.

**On sequencing**, it confirmed two of three calls and reframed the third. Storage-before-registration "demonstrably paid" — F3's debrief records Flight 2's contracts were "consumed, not rediscovered," and F3 then did the same for F4. Change-monitoring as its own flight was right; its three planning cycles were spent in *planning*, not shipped-code rework. Studio-surfaces before mission-close was the wrong **load**, not the wrong **order** — the dependency direction was correct (F7 DD-13's reconcile requires F6 DD-17's unconditional discriminator), but the close should have been **two** flights: a non-UI lifecycle/measurement flight and a separate UI/spec/gates flight. That is F7's own leg-level verdict — *split on decidedness, not size* — applied one level up.

**Its process finding is the one I would carry hardest**, and it is not technical: *deferrals are recorded impeccably and forced by nothing.* Four items rolled across three to five flights each — the Windows 1M re-measure, the `get_vector_store()` shutdown hook (deferred once more **after** an F4 recommendation explicitly refused a third deferral), the ARTIFACTS.md mission-branch question (four debriefs, zero resolution), and squawk 0050 (fixed in code in F6, artifact still `open` across three flights).

## What Went Well

**Behaviour tests earned their cost.** Four specs (`kb-folder-index-round-trip`, `kb-folder-watch-round-trip`, `kb-agent-query-round-trip`, `kb-studio-round-trip`) each caught defects that unit tests structurally could not, because each needed a real save on one surface observed through a different one. The Studio spec alone surfaced fifteen numbered defects across its lifetime — and the majority were defects *in the spec's ability to catch a regression*, not in the product. That is the test doing its job at a level above the feature.

**Operator decision checkpoints were placed where they mattered.** The Flight 2 "bar set before the numbers exist" discipline — declare the acceptance band *before* measuring — is what made the vector-store choice a decision rather than a rationalisation. The same shape recurred in Flight 7's AC-7 band, declared before the 500k rung ran. The operator's stop-at-500k call rested on two independent anchors already agreeing, so the third rung would have confirmed rather than informed.

**Gate failures were recorded rather than skipped.** `pip-audit` was written into the Flight 7 checklist as *failing, with a named owner*, not quietly omitted — and that owner (squawk 0083) subsequently closed it, with the frozen Windows build re-run afterwards because `anyio` sits inside the PyInstaller closure. Test flakes were named, isolated and re-run (the unit flake passed alone in 0.21 s and with its whole file in 10.38 s) rather than waved through.

**The squawk qualification gate held under pressure.** Twelve squawks were logged mid-flight and deferred rather than folded into the flight in hand. When the 2026-09-22 run surfaced the last-writer-wins finding, it was refused as a squawk — it fails two of the four criteria — and raised as a flight candidate instead. The gate exists precisely to stop the squawk path becoming a bypass for real work, and it was used that way.

**The Witnessed pattern, run strictly, produced the mission's best evidence.** See Lessons Learned.

## What Could Be Improved

**One defect class produced nine recorded instances across the mission.** An instrument that cannot detect what it claims to detect, or an enumeration copied instead of counted:

1. A `grep 'simd\|simsimd\|numkong'` that **cannot match the identifier `usearch_acceleration`**, stated as a negative finding (DD-10 was false; the field had existed since Flight 2) — and praised by an Architect as "the sharpest finding of the review". Two reviewers looked at a grep and neither asked whether it could match.
2. A Citation Audit that said "six call sites" for `App.confirmDelete`; there are **13 across 8 files** — copied from the Flight 6 debrief and stamped `verified` without recounting. This changed the blast radius from one browser lane to four.
3. "Three list queries" per squawk 0087; there are **four** (`list`, `list_children`, `list_folders`, `list_by_status`) — squawk 0091.
4. A spec status line saying five structural defects where the run logs carry six.
5. "Four of four legs done" when there were five — **caught by the operator**, not by any process.
6. A behaviour-test run **voided entirely**: preconditions verified the data directory but not the *build*, so fresh JS served alongside stale Python produced locally-valid, globally-meaningless evidence across eight checkpoints.
7. Spec defect #15 (2026-09-22): a clause that could not distinguish the behaviour it claimed to test.
8. **Found at mission close by the Architect, caught by no debrief in seven flights**: `tests/test_kb_extractors.py:255-257` pins the extractor seam's "no pipeline change" claim while writing text content under the comment *"Content is irrelevant — StubExtractor always returns STUB_TEXT, ignoring what's on disk."* Content is not irrelevant: `index_item` sniffs the first 8 KiB before the extractor is consulted. Write ZIP or PDF header bytes and the test fails. **The criterion's own pinning test could not detect the thing it pinned** — and the over-claim it protects is restated verbatim in two further places (`the_one/agents.md:1211`, `extractors/text.py:5-8`).
9. And once more in my own hands, during this very debrief: a per-file `grep … *.js` that did not descend into `js/areas/`, disagreeing with a recursive count in the same breath. Caught only because the two numbers were printed side by side.

**The criteria-tracking mechanism was never maintained anywhere.** Every flight's "Contributing to Criteria" box is unticked, in all seven flights. Seven of ten mission criteria sat open despite the work having shipped; three open questions likewise. All were reconciled only at mission close, by re-deriving the evidence from scratch. A checklist nobody ticks is worse than no checklist: it silently reports "not done" for work that shipped weeks earlier, and it trains readers to ignore it.

**Spawning agents to wait on multi-hour Windows CI jobs was a structural mistake.** A Concourse build that takes 11–33 minutes does not need an agent holding context while it runs, and one such client was killed by a host OOM in Flight 2. The pattern that worked was a detached launch (`setsid nohup … & disown`) plus polling — arrived at by necessity rather than by design.

**Deferred commit caused citation drift inside a flight.** Flight 7 deferred review and commit to the end (Phase 2d). Four line-number citations in Leg 2b had already moved, because Leg 2a's uncommitted edits shifted them. The mitigation already exists in the methodology — prefer `file:symbol` over bare line numbers — but the deferred-commit design makes bare line numbers decay *within a single flight*, not just across flights.

## Lessons Learned

### 1. Naming a lesson in a debrief does not prevent its recurrence

This is the mission's central finding, and it is evidenced rather than asserted. The instrument-cannot-detect lesson was named in **four consecutive flight debriefs**:

- **F3**: *"What the behavior test did not call, it did not prove."* / *"Timing evidence from a small fixture is thin."*
- **F4**: *"An apparatus gap is not a system fail and not a pass either."* / *"Timing tolerances that never fire are unproven."*
- **F5**: *"Assertions made from memory of a read are **the dominant defect class in this mission**."* / *"Falsifiability is something to demonstrate, not assert."*
- **F6**: *"A negative result from an instrument that cannot express the thing is not a finding."*

It then recurred **twice in Flight 7** — DD-10 and spec defect #15 — with the Flight Director who wrote the F6 lesson personally committing the F7 instance. Four namings, zero prophylaxis.

**So what**: stop treating a debrief paragraph as a control. A lesson prevents recurrence only when it becomes a *mechanism* someone must pass through — a required field, a gate, a named move — not a sentence someone must remember.

### 2. What actually caught it was procedural independence, not analysis

Defect #15 was caught because an independent Validator **held its verdict and demanded a discriminating experiment** rather than ruling on the evidence in front of it. It could have called step 13 a clean FAIL — the observation supported that reading — and a real DD-13 regression would have been reported against correct code. It could equally have waved it through. It did neither.

Contrast the DD-10 failure: two reviewers, one of them an Architect who called it "the sharpest finding of the review", and neither asked the one question that mattered — *could this grep have matched?*

**So what**: the distinguishing move is cheap and teachable — *before accepting a result, state what would have produced the opposite result; if you cannot, the observation is not evidence.* Make "hold the verdict, demand a discriminating experiment" an explicit, named move in the behaviour-test methodology, available to any judge, rather than a thing a careful agent happens to do.

### 3. Independent re-derivation is worth its cost precisely when it finds nothing

Across the 2026-09-22 run, the Validator re-ran every `GET` itself, recomputed `MAX(indexed_at)` in Python rather than accepting the reported maximum, and built its own browser session rather than trusting the Executor's screenshots. Almost all of it confirmed what was reported. Two things did not: an unattributed second browser page adjacent to the run's most load-bearing evidence, and two byte-identical screenshots asserting a distinction that did not exist in the artifacts.

Both were found by the re-derivation, neither by the report. The value of the practice is not its hit rate.

### 4. A criterion that says "behavior-test-backed" needs a test that would catch a regression

Flight 7's first-named criterion was held unticked through a *passing* 18/18 run, because the independent Validator ruled the spec not yet `active`-worthy: *"four real defects found in one execution pass is not what a settled spec produces."* The product evidence was strong throughout; the spec's ability to catch a *future* regression was not. Distinguishing those two is the whole point of the phrase.

### 5. An operator decision and a deferred obligation are not the same thing

Flight 7's own debrief recorded the Architect's finding that it called itself "landed" while its first-named criterion was unticked and its PR was draft — *"not in the substance, but in the label."* That finding was correct, and it was closed by doing the work rather than by relabelling. "Recorded and owned" is a real improvement on Flight 6's *unowned and silently dropped*, but it is not the same as done, and status words should not imply that it is.

## Methodology Feedback

**1. Convert the falsifiability lesson into a required field, not a paragraph.**
Where an artifact records an absence, a negative result, or a count, require alongside it: *how this could have come out otherwise*. For a grep, the pattern and the identifier it must match. For a count, where it was counted (not where it was copied from). This is the single highest-value change this mission suggests, because it targets the one class that produced seven instances.

**2. Add "hold the verdict, demand a discriminating experiment" to the behaviour-test skill** as a named, legitimate move for the Validator, with the protocol used on 2026-09-22: the judge specifies the experiment, the orchestrator routes it to the executor **as a bare procedure with no indication of what any outcome would imply**, and the judge rules on the result. That last clause is what protects the Witnessed pattern from becoming a one-way channel.

**3. Either enforce the per-flight criteria boxes or delete them.** They were never ticked in any of seven flights. A checklist with a 0/7 maintenance rate is not a tracking mechanism; it is noise that makes the mission look less complete than it is. Recommendation: make "tick the criteria this leg advanced, with evidence" part of leg completion — or drop the per-flight box and keep only the mission list, reconciled at flight close.

**4. Stop spawning agents to wait on long CI jobs.** Make detached-launch-plus-poll the documented pattern for anything over a few minutes.

**5. Prefer `file:symbol` citations over line numbers — and say why it is stricter under deferred commit.** The existing guidance is right but under-motivated; deferred commit makes line numbers decay within a single flight.

**6. Autonomy: the operator's assessment is "not autonomous enough."** Taken with "mostly trusted" reported status, the read is that check-ins were spent on confirmations the Flight Director could have made itself, while the failures that mattered were ones *no* check-in would have caught — they were false claims, not open decisions. The correction is therefore **not** more human gates. It is fewer confirmation stops plus stronger self-verification (item 1), so that higher autonomy is safe rather than merely faster.

**7. Force deferrals, don't just record them.** This mission's deferral *recording* is exemplary and its deferral *discharge* is unmanaged: four items rolled across three to five flights each, one of them after a debrief explicitly refused a third deferral. A deferral should name an **owning flight at the moment it is made**, and a flight that does not discharge it must say so in **its own** checklist rather than leaving it to its successor. F6's own words — *"an unowned checklist item does not get an honest 'unticked, because…'; it gets forgotten"* — should become a standing instruction, the same upgrade item 1 proposes for the instrument class, for the same demonstrated reason.

## Action Items

- [ ] Author the **agent-PUT protocol flight** — the mission's largest carried debt, and live data loss today. The Architect reframed this away from a `disabled_tools` fix: **no merge rule fixes staleness**, and the problem is field-agnostic. Three parts in priority order: (1) optimistic concurrency on `PUT /api/agents/{name}`, reusing the fail-closed 409 + `?override=true` shape that already exists at `api.py:1334-1366` — Studio already holds a fresh `updated_at` and simply does not send it; (2) a scoped write (`disabled_tools_scope: ["builtin"]`) so the partition boundary lives in the request protocol, which is what F6 Rec. 5 asked for and F7 DD-12 declined; (3) one server-served prefix table, retiring the hand-typed `UNGATED_TOOL_PREFIXES` copy in `studio.js:2420` that nothing binds to the Python tuple. Refused as a squawk — fails two of the four criteria.
- [ ] Author the **build-identity flight**: `git_sha` / bundle hash on `/api/info`, carrying squawk **0085** (asset cache-busting keyed to app version). A build-identity signal is what would have made the voided run self-diagnosing instead of requiring forensics.
- [ ] **Close squawk 0050** — fixed in Flight 6, never written up or signed off. Checkpoint 11 of the 2026-09-22 run is its verification evidence: an unrelated General-tab save left `kb_ids` intact, with the mutation proven real.
- [ ] **Run the `large-folder settle` variant** to close the one partial criterion, and record whether the tolerance was actually exercised or passed vacuously on a warm cache — which the variant's own flake profile requires it to state.
- [ ] **Close the literal restart-resume gap**: a fixture that reliably catches `indexed > 0` before the stop, or a throttled indexing pass, so `content_hash` survival is asserted rather than inferred.
- [ ] **Enforce single-page discipline in the behaviour-test browser apparatus.** *"Exactly one page" is an invariant nobody enforces; it was discovered by accident.*
- [ ] **Add a step for detach-by-UI-toggle** to `kb-studio-round-trip`; detach is currently evidenced only through delete-and-save.
- [ ] **Fix the three weakly-falsifiable clauses** in `kb-studio-round-trip` (steps 3, 5 and 7), each with the reason it cannot currently fail.
- [ ] **Operator decision**: 95 tracked files under `missions/` contain an absolute home path. Forward-prevention (a pre-commit grep gate) or a scoped rewrite of the artifacts.
- [ ] **Squawk 0095 — shutdown-flush residual window**: set `_cancel_report[kb_id] = True` on the shutdown-flush timeout as well as the cancel fallback (`manager.py:262-272`), so `close_vector_store` skips a knowledge base whose save thread may still be running. Add a test that drives the timeout — the one existing test asserts the non-timeout path — and falsify it by removing the line.
- [ ] **Squawk 0096 — `compute_tool_names` docstring over-claims set-independence**: state the widening exception at the point of the claim (`tool_provider.py:124`).
- [ ] **Squawk 0097 — exhausted widening silently overwrites a registered tool**: make that path loud rather than letting `self._tools[tool.name] = tool` (`tools/base.py:189`) drop a knowledge base's tool in silence. *Filed separately from 0096 per the skill's one-squawk-one-item rule — different file, different fix.*
- [ ] **Squawk 0098 — the extractor seam's "zero pipeline change" claim is false for binary formats**, in three places including the test comment that asserts the opposite. Scoped to documentation; lifting the binary gate needs a design decision and belongs to the PDF/Office mission.
- [ ] **Squawk 0099 — `_build_store`'s docstring claims backend dispatch it does not do** (`vectors/__init__.py:70` vs `:76-78`).
- [ ] **Measure the declared ceiling before the next mission scopes around it**: resident vector RAM (1.2–3.6 GiB at 1–3 GB of raw text, no eviction path) together with `SEMANTIC_QUERY_TIMEOUT = 2.0` against a ~24 s flush. One piece of work; today neither is measured and neither is in Known Issues.
- [ ] **Widen the M7 extractor test to a binary fixture**, watch it fail, and let that failure be the pin — falsify-first, this mission's own discipline.
- [ ] **Burn down the squawk backlog**: 10 open, 3 deferred. Stale by the skill's own thresholds. Fold **squawk 0080** (`mcp_source_ids`, the missed fourth preserve case, live data loss, still deferred) into the protocol flight rather than filing it a third time in a third form.
