# Flight Log: Agent Query

**Flight**: [Agent Query](flight.md)

## Summary

Planning (2026-09-17). `flight.md` drafted from the mission's Flight 5 bullet, the two mission open questions this flight settles, and the carry-forward items from the Flight 2, 3 and 4 debriefs. Operator interview recorded below; three planning premise probes run against the bundled embedding backend; the behavior-test draft `kb-agent-query-round-trip` is filed. No code has changed.

---

## Leg Progress

| Leg | Status | Notes |
|---|---|---|
| 01 `retrieval-and-fusion` | landed | Risk tier **high**. Design reviewed (Sonnet Developer): approve with changes, two medium + one low, all incorporated; no second cycle (one added AC plus a widened assertion, not substantive). Implemented: all 32 ACs met, 31 new tests in `tests/test_kb_retrieval.py` plus 3 in `tests/test_vector_store.py` and 4 in `tests/test_config.py`/`tests/test_factory_disable_enforcement.py`; `make lint` and the scoped suites all green. |
| 02 `kb-tools-gate-and-discovery` | landed | Risk tier **high**. Two design-review cycles pre-implementation (see "Design Review Cycles" below): cycle 1 found three highs and produced the DD-7 amendment dropping the `source_index` entry entirely; cycle 2 found the amendment had not been fully back-ported and fixed the last stale references. Implemented against the amended, `ready` leg spec: all 34 ACs met, 35 new tests in `tests/test_kb_tool_provider.py`, 5 new tests in `tests/test_factory.py::TestKBToolWiring`, 4 new tests in `tests/test_search_tools.py`; `make lint` and the scoped suites all green. |
| 03 `verify-integration` | not started | |

---

## Decisions

### Flight Director Notes — Leg 1 design (2026-09-17)

**Risk tier: high.** Three of the tier's triggers apply: it changes a shared
interface with existing consumers (`VectorStore`'s Protocol signature, plus
`AgentConfig.is_tool_enabled`), it alters a concurrency invariant (the
store's per-KB lock acquisition), and the mission's retrieval criterion rests
on its correctness. Design review run.

**Outcome: approve with changes.** The reviewer verified all eight Citation
Audit rows against the working tree rather than trusting them, and
independently recomputed DD-3 test 4's arithmetic — confirming the test fails
without the reserved slot (five both-list chunks score 0.0308–0.0328 against
a keyword-only rank-1 hit's 0.0164, so the exact-term hit sits at fused rank
6 and is excluded at `limit=5`) and passes with it. That matters: a pass-bar
test that passed either way would have left the criterion unprotected.

| # | Severity | Finding | Disposition |
|---|----------|---------|-------------|
| 1 | medium | **A third crash window none of the three flight-level cycles found.** `KBItemRepository.get` raises `KeyError` on an absent row, and DD-1's steps (5) and (6) are separate awaits on the one shared connection. An item deleted in that window raises an unhandled `KeyError` out of `search` — a crash where windows (a) and (b) degrade. | Fixed as **AC-6b**: tolerate and drop the hit, mirroring `get_many`'s own missing-id tolerance, with a test. Verified `get`'s `KeyError` and the `ON DELETE CASCADE` myself. |
| 2 | medium | AC-3's no-`wait_for` pin was scoped to the same statement as `store.query`, which misses a `wait_for` wrapped around the whole `gather` or around `search`'s body — equally cancelling, equally corrupting, and invisible to the narrow grep. | Fixed: the assertion is now that `wait_for` appears **nowhere** in `retrieval.py`. DD-1 gives the module no legitimate use for it, so absence is both cheaper and stronger. |
| 3 | low | AC-8 said "three guards" while DD-3's pseudocode has five clauses (the trigger being the fifth) — a Developer could implement the guards and omit the trigger. | Fixed: AC-8 enumerates all five and names the bundling. |
| S | suggestion | AC-21's test leans on the private `_entry(kb_id)`; no public seam exists. | Applied: the access pattern is spelled out in Verification, with the reason the private attribute is deliberate here (the invariant under test *is* that lock's state). |

The reviewer also confirmed no dependency leakage in either direction with
Leg 2, and that DD-6's Divert criterion does not fire: `is_tool_enabled` has
three call sites in `the_one/` and the only other `mcp__` literal outside
`agent/config.py` is `_search_tools.py`'s rendering prefix, which is Leg 2's
territory.

### Leg 1 implementation — Developer (Sonnet), 2026-09-17

All 32 acceptance criteria met; status `landed`. Files touched exactly per
the leg's scope (Creates: `the_one/knowledge/retrieval.py`,
`tests/test_kb_retrieval.py`; Modifies: `the_one/vectors/_store.py`,
`the_one/vectors/usearch_store.py`, `the_one/vectors/__init__.py`,
`the_one/embeddings/_backend.py`, `the_one/agent/config.py`,
`the_one/agents.md`, `tests/test_config.py`,
`tests/test_factory_disable_enforcement.py`, `tests/test_vector_store.py`) —
no Leg 2 file (`KBSearchTool`, `KBToolProvider`, `AgentFactory`,
`_search_tools.py`, `BASE_PROMPT`, `CLAUDE.md`, `SECURITY-MODEL.md`) touched.

**Chosen, not given: `SEMANTIC_QUERY_TIMEOUT = 2.0` seconds.** DD-1 pins the
reasoning (below the Flight 2 Windows flush duration of 10-12s at 1M chunks,
so a query concurrent with a flush degrades rather than waits) but leaves
the exact figure to Leg 1. 2.0s is comfortably below that flush duration —
long enough that an ordinary upsert (~1.8s at 1M) does not spuriously
degrade a query, short enough that the degrade fires well before the
flush's own duration would have made the wait pointless. Recorded here per
the Flight 3 debrief's "no number attributed to the operator that the
operator did not give" convention — this one is the Developer's, not the
operator's.

**Cycle-1-style self-review before handoff**: re-derived DD-3 test 4's
arithmetic independently (five both-list chunks score 0.0308-0.0328 vs. a
keyword-only rank-1 hit's 0.0152) and then verified the strict-bar test
actually depends on the reserved-slot rule by running it against a
monkeypatched `_fuse` with the reserved-slot block removed — it fails
(chunk 99 absent from the top 5) as DD-3 predicts, confirming the shipped
test is not vacuously green.

**Deviations from the leg spec**: none. The reserved-slot pseudocode, the
two named senses of "keyword-only"/`in_keyword_list`, the acquire-outside-
`try` lock discipline, and the four degrade causes were all implemented
literally as specified, per the coordinator's explicit instruction to treat
apparently over-specified ACs as encoding a measured review finding rather
than simplifying them.

**One AC exercised beyond its strict letter**: AC-27 says "if [the
factory-composition test] needs a `kb__` case, add one" (conditional). One
was added — `test_narrowed_builtin_whitelist_keeps_kb_tool` in
`tests/test_factory_disable_enforcement.py`, using a new
`StubProviderWithKbTool` — since DD-6's regression net is otherwise proven
only at the `AgentConfig.is_tool_enabled` unit level, not at the
factory-composition level the file's own module docstring says is its
territory.

**Anomalies**: none. Every scoped test file passed on first full run after
implementation (`tests/test_kb_retrieval.py`: 31/31;
`tests/test_vector_store.py`: 49/49; `tests/test_config.py` +
`tests/test_factory_disable_enforcement.py`: 40/40) — no flakiness, no
hangs, no test requiring a retry. `ruff check`/`ruff format --check` both
clean after one auto-fix pass (import sort + one line-length wrap in the
new test file).

Verification commands run (all green): `PYTHON=.venv/bin/python bash
scripts/run-tests.sh tests/test_kb_retrieval.py tests/test_config.py
tests/test_factory_disable_enforcement.py tests/test_vector_store.py -x
--timeout 60`; `make test-unit`; `make lint`.

### Leg 2 implementation — Developer (Sonnet), 2026-09-17

All 34 acceptance criteria met; status `landed`. Files touched exactly per
the leg's scope (Creates: `the_one/knowledge/tool.py`,
`the_one/knowledge/tool_provider.py`, `tests/test_kb_tool_provider.py`;
Modifies: `the_one/agent/factory.py`, `the_one/tools/_search_tools.py`
(the `kb__` branch in `_format_result` and the module docstring only —
`_search_tools.py`'s `source_index` shape untouched, per the DD-7
amendment), `the_one/agent/config.py` (`BASE_PROMPT` only — the gate
itself landed in Leg 1), `tests/test_factory.py`, `tests/test_search_tools.py`,
`CLAUDE.md`, `the_one/agents.md`, `SECURITY-MODEL.md`) — `retrieval.py` and
`the_one/vectors/` (Leg 1) not touched.

**No design question needed escalation.** The leg spec, as amended through
its own two design-review cycles, settled every naming, wiring, and
discovery decision before implementation started; nothing in the leg's
acceptance criteria was ambiguous enough to need a Flight-Director call.

**Deviations from the leg spec**: none. In particular, implemented exactly
as specified rather than simplified:
- The `kb__` naming algorithm (`the_one/knowledge/tool_provider.py::_compute_tool_names`):
  group-wide (not positional) collision discriminator, the fixed-length
  `sha256(kb_id)` hash (never a `kb_id` prefix) with its budget reserved
  BEFORE truncation, and the 8→12→16 widening pass asserting uniqueness
  across the agent's whole attached set rather than assuming it. AC-7
  explicitly warns to read AC-9 first, given the flight log's own record of
  two prior review passes catching the opposite ordering (a superseded
  rule read before its correction) — read in that order here.
- DD-7's amendment: no `source_index` entry for a knowledge base.
  `_format_result` gains only a prefix-parse branch; the "why absent"
  reasoning is recorded as a comment at that branch (AC-19) rather than
  left implicit, so a later reader does not "restore" the entry by
  MCP-symmetry.
- AC-16's guard is `if self.kb_provider is not None` alone (no `and
  config.kb_ids` short-circuit) — matches the MCP block's structural shape
  even though `get_tools_for_agent` already no-ops cheaply for empty
  `kb_ids`.
- DD-8's four-way degrade rendering (`the_one/knowledge/tool.py::_render_result`):
  the one reversed cause (`"keyword index unavailable"` → semantic-only
  results) is handled by an explicit equality check against the other
  three, not a shared "is this a semantic-side cause" heuristic, so a
  fifth cause added later fails loud rather than silently defaulting to
  the wrong sentence.
- `KBSearchTool.execute`'s `limit` guard rejects `bool` explicitly (`bool`
  is an `int` subclass in Python — `limit=True` would otherwise silently
  pass the `1 <= limit <= 20` check as `1`).

**Self-review before handoff**: verified the naming algorithm's
reorder-independence is structural, not incidental — grouping is keyed by
`kb_id` and by slug *value*, never by list position, so
`test_collision_group_names_stable_under_reorder` and the AC-10b compound
test assert on that property directly rather than trusting a single
ordering. Also verified DD-7's "provably zero residual" claim holds for
this implementation specifically: `build_description` embeds `kb.name`/
`kb.description` verbatim (not paraphrased), so the per-tool haystack is a
strict superset of what a `source_index` entry's haystack would have been,
matching the flight log's cycle-2 proof.

**Anomalies**: none. Every scoped test file passed on first full run after
implementation (`tests/test_kb_tool_provider.py`: 35/35;
`tests/test_factory.py`: 35/35 incl. the new `TestKBToolWiring`;
`tests/test_search_tools.py`: 58/58 incl. the new `kb:` group tests) — no
flakiness, no hangs, no retries. Also ran the adjacent MCP/factory/
self-configuration/web-session test files that construct `AgentFactory`
without an explicit `kb_provider` (which now default-construct a real
`KBToolProvider`) to confirm the new default causes no regression:
`tests/test_cli_sandbox_parity.py`, `tests/test_connectors_inbound.py`,
`tests/test_factory_disable_enforcement.py`,
`tests/test_factory_openrouter.py`, `tests/test_mcp_tool_provider.py`,
`tests/test_self_configuration_surface.py`, `tests/test_web_session_reaper.py`
— all green. `ruff check`/`ruff format --check` both clean (one auto-fix:
an import-sort reorder in `factory.py`'s new `TYPE_CHECKING` import).

Verification commands run (all green): `PYTHON=.venv/bin/python bash
scripts/run-tests.sh tests/test_kb_tool_provider.py tests/test_factory.py
tests/test_search_tools.py -x --timeout 60`; `make test-unit`; `make lint`.

### Flight Director Notes — flight start (2026-09-17)

- Loaded `.flightops/ARTIFACTS.md`, `FLIGHT_OPERATIONS.md`, `agent-crews/flight-design.md` (structure valid; note this is the first flight whose design review runs against the prompt squawk 0068 widened, so the Architect is asked about environment-derived defaults and per-leg external-session checks by the prompt itself rather than by the spawn).
- Sources read: `mission.md` (Flight 5 bullet, the two open questions, Constraints, Known Issues, Branch Layout); the Flight 2, 3 and 4 debriefs (carry-forward items below); Flight 3 `flight.md` DD-5/DD-6 (the write ordering the crash windows come from); Flight 4 `flight.md` DD-8 (the `/status` shape Flight 6 renders).
- Code read: `the_one/agent/factory.py` (`create`'s registry build, the MCP block, `_build_source_index`), `the_one/agent/config.py` (`is_tool_enabled`, `kb_ids`), `the_one/tools/base.py` (`Tool`, `ToolRegistry`), `the_one/tools/provider.py` (the sync Protocol), `the_one/tools/_search_tools.py` (`_filter_candidates`, `_format_result`, `SearchTools`), `the_one/mcp/_tool.py` (`_normalize_source_name`, `MCPClientTool`, the 64-character ceiling), `the_one/mcp/_tool_provider.py` (`MCPToolProvider`, the sibling-class rationale), `the_one/db/repositories.py` (`search_keyword`, `get_many`, `count_for_kb`, `MAX_SEARCH_K`), `the_one/db/models.py` (`KBChunk`), `the_one/vectors/_store.py` and `usearch_store.py` (`query`'s distance return, `_check_dim`, the stale contract), `the_one/embeddings/_backend.py` and `local.py`, `the_one/knowledge/indexer.py` (the embed-lock scope), `the_one/interfaces/web/api.py` (agent, chat-session and knowledge-base routes), `the_one/interfaces/web/app.py` (`/ws`), `the_one/llm/mock.py` (scripted `tool_calls`), `scripts/bench_vector_store.py` (`recall_at_k`, the corpus generator).
- HAT: not planned. The operator's standing rule from the Flight 3 debrief — HAT legs only where there is a screen — applies; this flight has no UI surface. The walk folds into Flight 6's HAT.
- Branch: `mission/24-knowledge-bases` at `9fef908` (PR #203 merged), clean.
- Methodology (Flight 3 debrief Recommendation 4): no number in this spec is attributed to the operator that the operator did not give. `RRF_K = 60`, `candidate_k`, the 1–20 `limit` bound and the 5-result default are Flight Director proposals, recorded as such in their DDs; the four operator decisions are tagged with the date and the question they answered.

### Operator interview (2026-09-17)

| Question | Answer |
|---|---|
| Merge the squawk turnaround (PR #203) before planning continues | **Merge it now** — so this flight's design review inherits squawk 0068's two new checks |
| How semantic and keyword results are combined (mission open question) | **Reciprocal rank fusion with a fixed constant**, no operator dial → DD-3 |
| How `kb__` names pass the per-agent enable gate (mission open question) | **Generalize the prefix set**; `disabled_tools` stays universal → DD-6 |
| Behavior-test apparatus for the discover-and-query criterion | **Mock provider with scripted tool calls** (deterministic, offline) → DD-9 |
| Chunks whose item is not `indexed` | **Return them, unmarked** → DD-1 |
| Evidence for the exact-term criterion | **Targeted tests only**, no recall benchmark this flight → DD-3 |
| Squawk 0050's window between this flight and Flight 6 | **Accepted** ("the gap between the 2 flights is fine") → DD-10 |

### Planning premise probes (2026-09-17, this host, bundled `potion-retrieval-32M`, `HF_HUB_OFFLINE=1`)

| # | Premise | Method | Result |
|---|---|---|---|
| P1 | A query embedding is cheap enough that retrieval need not cache it | 20 sequential `embed([query])` calls on a warmed backend | **p50 0.08 ms, p95 0.17 ms, max 0.19 ms**; backend load 0.38 s, dim 512 → no caching, and the cost is irrelevant beside the store and FTS5 calls |
| P2 | The backend is safe to encode from several threads at once, so retrieval need not take the indexing manager's embed lock | 8 threads each calling `embed([query])`, compared against a serial baseline | **No errors; maximum absolute deviation 0.000e+00 — bit-identical.** → DD-2: the retrieval path takes no manager lock, so the lock-order invariant is never in play on it |
| P3 | What the manager's embed lock actually costs a would-be waiter | one 256-text `embed` (the indexer's batch shape) | **8.4 ms** for the embed half; the lock also spans the upsert. Recorded as the latency retrieval avoids by not queueing behind it, not as a bar |
| P4 | The mock provider can drive a tool call without a live model | `the_one/llm/mock.py` | `config["response"]["tool_calls"]` is read and turned into `ToolCall` objects; the module docstring records that a browser test already drives it this way → DD-9's act path |
| P5 | The behavior test can observe a tool call and its result through an existing surface | `api.py::get_chat_session` | `GET /api/chat/sessions/{id}` returns the persisted `messages` list alongside the summary → DD-9's read path; no test-only seam needed |
| P6 | Where a chat turn is driven from | `app.py:2446` | `@app.websocket("/ws")`, with an `action`-keyed JSON protocol (`join`, `message`); `websockets` is already a runtime dependency, so a shell-only Python driver adds nothing to the closure. **`ws.accept()` runs before any handler-level auth check — whether the bearer credential is accepted on the upgrade is flagged for the Leg 3 premise audit, not assumed** |
| P7 | `search_keyword`'s and `query`'s score directions and scales | `repositories.py::search_keyword`, `usearch_store.py::query` | bm25, negative, lower-is-better, `ORDER BY score` ascending → best-first; usearch **distances**, lower-is-better, scale varies with dtype → both lists best-first, scales incomparable → DD-3's rank-only fusion |
| P8 | `get_many` tolerates ids with no row | `repositories.py::get_many` | Preserves the caller's order and returns only ids found (`[by_id[i] for i in id_list if i in by_id]`) → crash window (b) needs no explicit check |
| P9 | The tool-name ceiling and normalisation rule | `mcp/_tool.py` | `_TOOL_NAME_MAX_LEN` enforced in `MCPClientTool.__init__` with a per-tool drop and a WARNING; `_normalize_source_name` maps `[^a-zA-Z0-9_-]` to `_` → DD-4 |
| P10 | `kb_ids` is persisted but inert | grep across `the_one/` | Readers: `db/repositories.py` (round-trip), `db/schema.py` (column), `agent/config.py:111` (field), `self_configuration/projection.py:55` (projection only). No runtime consumer → this flight is the first |

---

## Design Review Cycles

### Cycle 1 — Architect (Opus), 2026-09-17

First flight-design review run against the prompt squawk 0068 widened, so
items 7 (environment-derived defaults) and 8 (external-session prerequisites)
were asked by the crew file rather than by the spawn prompt. Verdict:
**approve with changes** — four high, ten medium, eight low. Every high and
every medium was fixed; the lows were applied except where noted. I verified
the four highs myself against the code before rewriting, rather than taking
the report at face value.

| # | Severity | Finding | Disposition |
|---|----------|---------|-------------|
| 1 | high | DD-2 claimed "agent query latency is never coupled to indexing". False: `UsearchStore.query` takes the same per-KB `entry.lock` that `upsert`, `flush` and `rebuild_from` hold — seconds during a flush at 1M, hours during a rebuild. The honest-degrade design was defeated in exactly the case it was written for, because a *healing* store does not raise `VectorStoreStaleError`, it waits. | Fixed. Verified `usearch_store.py::query` takes `entry.lock`. DD-2's second consequence rewritten to the narrower true claim; DD-1 gains `SEMANTIC_QUERY_TIMEOUT` around the semantic call with `TimeoutError` routed into the degrade channel. Recorded as a third consequence beside the two crash windows in Leg 1's doc update. |
| 2 | high | DD-1's `asyncio.gather` cannot produce the degraded result it specifies — a plain gather propagates the first exception and leaves the sibling's result unretrieved, so the handler has no keyword hits to return. The Leg 1 checkpoint was unreachable through the stated mechanism. | Fixed. DD-1 specifies `return_exceptions=True` with both slots inspected, and records *why* it is load-bearing so a Developer does not simplify it back. |
| 3 | high | DD-7 asserted three mechanisms the code does not have: `_format_result` renders from `source_index` (it never sees it — it parses the tool name), the index key is the group label (the key is `source.name`, the label is the normalized name segment), and `_build_synthetic_description` can take a KB description (no such parameter). The Acceptable-variations clause locked the broken shape in. | Fixed. Verified `_format_result(matches, query, *, total=None)` groups by prefix parse. DD-7 rewritten around selection-vs-rendering, a `kb__` branch in the prefix parse, `(group, name)` keying, and a directly-composed description. The acceptable-variation struck. |
| 4 | high | Behavior spec steps 7 and 9 assert the transcript contains no occurrence of the fixture identifier — unsatisfiable, since the scripted call's `arguments` carry it and `message_to_dict` persists them verbatim. Both isolation rows would fail for a reason unrelated to isolation. | Fixed. Both rows scoped to the `tool_result` matching the call (`is_error: true`, content carrying neither the identifier nor fixture text), with a spec-level note recording why, so a later editor does not "fix" it back. |
| 5 | medium | DD-4's collision suffix is order-dependent — "second and subsequent" is decided by operator-controlled `kb_ids` order, so a reorder swaps two tool names and silently re-targets a name-keyed `disabled_tools` entry. | Fixed. The suffix is now a property of the group: every member of a colliding slug gets `_{kb_id[:6]}`. |
| 6 | medium | DD-5's shadowing rationale is inverted — `ToolRegistry.register` is last-write-wins, so registering last means a KB tool *would* shadow, not could not. | Fixed, with the correction stated explicitly so a later reader does not build on the inverted version. |
| 7 | medium | DD-1's return type `list[SearchHit]` contradicts its own "on the result object" degrade wording. | Fixed: `SearchResult(hits, degraded)`. |
| 8 | medium | DD-3's exact-term guarantee is weaker than claimed — FTS5's implicit AND zeroes the keyword side for sentence-shaped queries, and at `candidate_k=25` any both-list chunk outranks a keyword-only rank-1 hit, with an exact tie at `limit=1` decided by `chunk_id`. | Fixed. Tie-break moves to keyword-first; the crowding arithmetic and the AND limit are recorded; five named tests replace two, including the `limit=1` tie and a sentence-shaped query. |
| 9 | medium | `EmbeddingBackend` makes no concurrency promise, so DD-2's rule is a property of one implementation. | Fixed: Leg 1 adds the guarantee to the seam's docstring. |
| 10 | medium | Review item 7 applied to my own probes — P1–P3 ran unpinned, and the mission's standing rule is to benchmark on Windows or discount Linux numbers explicitly. | Fixed. The numbers are now explicitly discounted and the conclusion rests on the code path (no BLAS/OMP kernel, no model mutation) rather than on the measurement. |
| 11 | medium | The mock provider repeats its scripted call every iteration; at the default `max_iterations=20` each turn dispatches the tool twenty times. | Fixed: both agents created with `max_iterations: 1`. Verified the budget is consumed at the *top* of the iteration body, so the single iteration still dispatches the tool and persists the result. |
| 12 | medium | `PUT /api/agents/{name}` is a full replace; the spec's "(leaving `kb_ids` unchanged)" would detach the KB and make step 8 look like a whitelist regression. | Fixed: steps 8 and 9 GET then PUT the complete body, re-sending `kb_ids`. |
| 13 | medium | DD-9's `/ws` premise is resolvable now. | Fixed. Verified `CredentialGateMiddleware._handle_websocket` falls back to `_resolve_header`. The premise is resolved, the protocol pinned in the spec, and the browser-apparatus Divert criterion struck. |
| 14 | medium | Leg 2 carries the flight's only shared-interface change on top of four packages; `is_tool_enabled` has no dependency on the KB tool existing. | Fixed: DD-6 moves to Leg 1. |
| 15 | medium | `BASE_PROMPT` tells the model its catalog is built-ins plus MCP, and names the two group labels — a third group makes the model's own instructions wrong. | Fixed: added to Leg 2's doc list. |
| L | low (eight) | `tests/test_agent_config.py` does not exist (tests live in `tests/test_config.py`); `agents.md:1209` → `1211`; the "zero runtime readers" prerequisite overstates (projection.py reads `kb_ids`); `KBSearchTool` must pass `agent_name`; `KBToolProvider` needs a lazy import and constructor injection; `get_embedding_backend()` is sync and takes a lock; over-long KB names drop the only tool; no per-item diversity. | All applied. The name-length one was upgraded rather than applied as written: **truncate-and-suffix instead of drop**, since the MCP precedent's "one tool of many" does not transfer when the drop costs the whole attachment. Per-item diversity recorded as DD-12 (accepted, deferred to the benchmark). |

**Operator questions answered by the Flight Director** (all four settled
without escalation; none changed the flight's shape): dropped-tool visibility
→ dissolved by truncate-and-suffix; `limit=1` tie → keyword side wins;
`degraded` channel → two distinct strings; `max_iterations=1` apparatus →
accepted, verified to still exercise the observable.

**Cycle 2**: the changes are substantive, so a second Architect pass runs
before the flight is marked `ready` (max 2 cycles).

### Cycle 2 — Architect (Opus), 2026-09-17

Scoped to verifying cycle 1's incorporation rather than re-deriving the
design. Verdict: **approve with changes** — one high, seven medium, seven
low. It confirmed fourteen of the fifteen cycle-1 dispositions landed
correctly against the code, and rejected the one I had flagged to it as least
certain.

| # | Severity | Finding | Disposition |
|---|----------|---------|-------------|
| 1 | high | Cycle 1's `asyncio.wait_for(store.query(...))` releases the caller **and the per-KB lock** while the pool thread is still executing against `entry.index`. The next holder — `upsert`, `flush` or `rebuild_from` — then mutates an index a live thread is reading. Failure mode is a corrupt sidecar or a segfault in the C extension, neither logged nor recoverable. | Fixed. **I verified it with a probe before changing anything**: caller released and lock free at 0.302 s, next holder acquired at 0.302 s, escaped thread still running until 1.502 s — exactly as reported. Escalated to the operator as a scope decision (it edits `the_one/vectors/`, which DD-11 declared untouched); operator chose the store-side fix. `UsearchStore.query` gains an optional `timeout` bounding **only** `entry.lock.acquire()`, raising `VectorStoreBusyError`. Nothing in-lock is ever cancelled. |
| 2 | medium | Verification still said "the 64-character drop", contradicting DD-4's truncate-and-suffix and the Leg 2 checkpoint. | Fixed — a leftover from the pre-fix draft. |
| 3 | medium | `_{kb_id[:6]}` is not unique: `POST /api/knowledge-bases` accepts a **client-supplied `id`**, so `kb-docs-1`/`kb-docs-2` both yield `kb-doc` and two colliding bases produce the same tool name — last-write-wins then drops one KB's only tool, the exact failure the group-wide rule was written to prevent. Truncation has the same hazard, and the over-length + collision composition was unspecified. | Fixed. Verified `api.py` only auto-generates an id when absent. The provider now computes the whole name set and widens the discriminator deterministically until unique, logging each widening; truncate-then-one-suffix-then-assert is specified. |
| 4 | medium | `SearchTools.__init__` does `source_index or {}` — an **empty dict is falsy**, so it binds a fresh dict. The factory populates the index only when MCP sources exist, which is false for this flight's common case, so KB entries added after registration would never reach the tool — and the behavior test would still pass, because step 6 matches the tool's own name. A silent defect with a green gate. | Fixed. Verified both the falsy bind and the MCP-only population guard. Entries are built in the factory **before** `registry.register(SearchTools(...))`, and DD-7's "or inside the provider" acceptable variation is struck. |
| 5 | medium | `(group, name)` tuple keying contradicts the declared `dict[str, ...]` types, and `_filter_candidates` uses the key as **match text** — a tuple would render as `"('kb', 'KBQ-test')"` into the haystack. | Fixed: namespaced **string** key, with the "the key participates in matching" constraint stated. |
| 6 | medium | `return_exceptions=True` turns *every* exception into a value, but DD-1 named only two types in one slot. An unexpected semantic exception (notably `_check_dim`'s `ValueError` on a dim mismatch after an upgrade) would reach fusion as if it were a result list and fail with an opaque `TypeError`; the keyword slot was unspecified entirely. | Fixed. Four causes now specified: stale, busy, any-other-semantic (`"semantic index unavailable"`), and a symmetric keyword-slot degrade (`"keyword index unavailable"`), with both-slots-failing raising honestly. |
| 7 | medium | DD-3's test 4 was the Divert trigger but had no falsifiable pass condition ("asserting whatever the chosen design actually guarantees"), so a Developer could write a test that passes by construction and the Divert would never fire. | Fixed, and the underlying design question escalated to the operator: the arithmetic says plain RRF **cannot** put the exact-term hit in the top `limit` at `candidate_k=25`, so the mission criterion would not hold. Operator chose to **reserve a keyword slot now** rather than let the Divert trip mid-flight. Test 4's bar is the strict one and is named in the Leg 1 checkpoint. |
| 8 | medium | The cycle-1 empty-KB short-circuit costs more than it saves — `count_for_kb` is an O(n) index scan on the hot path to avoid a 0.08 ms embed, and both backends already return `[]` cheaply. | Fixed by removal. A fix I added at cycle 1 that was worse than the absence of it. |
| L | low (seven) | Crossover claim imprecise (`candidate_k=100` is not safe either, merely less crowded); behavior spec step 3 omits the `tool_calls` `id` key that `MockProvider` requires; DD-4 didn't say the provider computes the name; a slug containing `__` mis-renders the group label; the "not imported across the MCP boundary" rationale ignores that `_build_source_index` already imports it; DD-1's numbered ordering omitted the short-circuit; Verification omitted `tests/test_factory_disable_enforcement.py`. | All applied. |

**Suggestions applied**: `SEMANTIC_QUERY_TIMEOUT`'s value reasoned against
the Flight 2 Windows flush figures (below flush duration, deliberately);
the cold-start `Index.restore` path recorded as the realistic route into a
long acquisition; DD-8's citation pinned to the chunk's own `item_id`
rather than a `parent_id`; Leg 1's four doc targets listed explicitly so the
`agents.md` note is not treated as optional.

**Operator questions answered by the Flight Director**: keyword-slot
exception → a symmetric third degrade string, since losing the keyword side
costs the exact-term guarantee and should be visible; collision discriminator
→ widens deterministically rather than constraining `KnowledgeBase.id`
uniqueness at six characters, which would be a schema-level constraint this
flight has no business adding.

**Cycle 3**: both standing cycles are used. Escalated to the operator per
their "keep max 2, ask each time" rule; operator chose to run a third pass
against the re-designed timeout and the reserved keyword slot before
implementation begins.

### Cycle 3 — Architect (Opus), 2026-09-17

Operator-authorised beyond the standing two-cycle limit, scoped to the two
changes cycle 2 produced: DD-1's bounded lock acquisition and DD-3's reserved
keyword slot. Verdict: **approve with changes** — two high, seven medium,
six low, with the Architect stating plainly that a cycle 4 is not warranted
because both highs are verifiable by re-reading two bullets. Both highs were
**text defects in my spec, not design failures**: the decisions were sound,
the prose would have made a literal Developer implement something else.

| # | Severity | Finding | Disposition |
|---|----------|---------|-------------|
| 1 | high | DD-1's numbered "authoritative ordering" **still specified the cancelled `asyncio.wait_for`** that cycle 2 removed, and my own cycle-2 addition ("this numbered list is the authoritative ordering") gave it precedence over the corrected bullet. A Developer following the spec literally would have reimplemented the memory-corruption hazard verbatim. | Fixed. Step (3) now passes `timeout=` into `store.query` and states that no `asyncio.wait_for` may wrap the store call, with the reason inline so a later simplifier does not tidy it back. A self-inflicted defect: the precedence clause I added to remove ambiguity is what made the stale text authoritative. |
| 2 | high | DD-3's reserved-slot **trigger said "keyword-side" while its displacer said "keyword-only"** — and in test 4 all five crowding chunks are both-list, hence keyword-side, so the trigger would see representation, no-op, and leave the exact-term hit at fused rank 6. The test the Leg 1 checkpoint names as the flight's pass bar would fail on day one. This is exactly the ambiguity I asked cycle 3 to check. | Fixed. Trigger restated over keyword-**only** hits with an explicit sentence that a both-list hit is not keyword representation for this rule, and the whole rule restated as **pseudocode** — the Architect's observation that both highs and two mediums this pass were prose-ambiguity failures in one paragraph, while the arithmetic was never ambiguous. |
| 3 | medium | The reserved slot had no defined behaviour when the keyword-only set is empty — `keyword_only[0]` raises `IndexError` on ordinary input (a query whose terms all land in semantically-similar chunks). | Fixed: added to the guard set. |
| 4 | medium | At `limit=1` the reserved slot would always evict a both-list winner — the strongest signal there is — inverting DD-3 test 2's property. | Fixed (operator question 1, Flight Director's call): guarded at `limit >= 2`, with the reason recorded — at `limit=1` a both-list winner *is* a keyword match, so the criterion is not at risk. Test 2 is written at `limit >= 2`. |
| 5 | medium | The Leg 1 checkpoint carried two cycle-1 leftovers contradicting DD-1: a degrade from "a semantic call that exceeds `SEMANTIC_QUERY_TIMEOUT`" (nothing bounds the call's work — only its acquisition) and "an empty knowledge base short-circuits before embedding" (cycle 2 deleted that short-circuit). Both would have had a Developer rebuild what cycle 2 removed. | Fixed: both deleted, and the two newest degrade causes added in their place. |
| 6 | medium | `VectorStoreBusyError`'s parent and home module were unspecified. `VectorStoreStaleError` as a parent would be actively harmful — `manager.py` catches it and responds with `rebuild_kb`, so a transient busy query would trigger a full re-embed. The Leg 1 file list named only `usearch_store.py`, so the class would have split the hierarchy across modules with no re-export. | Fixed: `VectorStoreBusyError(VectorStoreError)` in `_store.py`, re-exported from `__init__.py`, all three files named in DD-11 and Leg 1. Architect verified no existing `except` clause breaks — `store.query` has no production caller today. |
| 7 | medium | DD-5 and DD-7 specified **two orderings that cannot both be obeyed**: DD-7 needs the `source_index` entries built before `SearchTools` is registered, but their `tool_names_prefixed` need the final tool names, which only `KBToolProvider` can compute — and DD-5 put the provider call after registration. The two wrong resolutions are precisely what cycles 1 and 2 found. | Fixed: a four-step ordering stated explicitly in DD-5 (provider first, entries from its returned names, register `SearchTools`, then register the tools at DD-5's position). |
| 8 | medium | DD-8's degraded line named two of the four causes and said "these are keyword results" — backwards for `keyword index unavailable`, where they are semantic results. | Fixed: four causes, sentence depends on which side degraded. |
| 9 | medium | Two of the four degrade causes had no named test — the unexpected-semantic-exception cause (whose absence produces the opaque `TypeError` cycle 2 found) and the keyword-slot degrade. The newest, least-exercised branches in the flight. | Fixed: both named in the Leg 1 checkpoint and the Verification list, alongside both-slots-fail. |
| L | low (six) | The timed acquire must sit outside the `try` (inside, the `finally` raises `RuntimeError: Lock is not acquired` on every timeout, masking the real error); `timeout` should be keyword-only and belongs on the `VectorStore` Protocol; the bound covers the waiter, never the holder (a cold-start `Index.restore` is unbounded); the reserved hit's output position was unstated (it matters — the governor truncates from the head); nothing proved the `source_index` entry reachable; both-slots-fail didn't say which exception is raised. | All applied. The reachability one matters most: cycle 2's fix landed but its regression net did not, so `tests/test_search_tools.py` gains a test querying the knowledge base's *description* rather than the tool name — the only assertion that fails if the entry is missing. |

**Operator questions answered by the Flight Director**: `limit=1` eviction →
guard at `limit >= 2` (row 4); `timeout` on the Protocol → **yes**, the seam
exists to accept a second backend and a concrete-type reach-through would
defeat it, accepting one more file in the widening; DEBUG log when the
reserved slot fires → **yes**, since DD-3 ships no dial and DD-12 defers the
recall benchmark, a count of how often the guarantee costs a semantic hit is
what will tell that benchmark whether a dial was ever needed.

**Suggestions applied**: the busy-path WARNING carries `kb_id` and the
elapsed/timeout values (a genuine deadlock now degrades quietly and forever,
so that line is the only operator signal); the `kb:` match-token consequence
recorded; the `source_index` entry's two key names spelled as the existing
code reads them; DD-3's rule restated as pseudocode.

**No cycle 4.** The Architect's own assessment is that both highs are
mechanical text fixes verifiable by re-reading two bullets, and Leg 1 tiers
high — so it carries its own leg-level design review before any code is
written, which is the next gate either way.

**Flight marked `ready`.**

### Flight Director Notes — Leg 2 design, cycle 1 (2026-09-17)

**Risk tier: high** — factory wiring, a new per-agent tool surface, and an
edit to `_search_tools.py`, whose matching rules are already subtle.

**Outcome: needs rework** — three high findings, all real, all verified
against the tree. Two of them compounded, and chasing the second produced a
**design amendment to DD-7** rather than a patch.

| # | Severity | Finding | Disposition |
|---|----------|---------|-------------|
| 1 | high | AC-15's step 2 was not implementable: building the `source_index` entry needs `kb.description`, but the factory holds only the returned `list[Tool]`, and a tool's *name* is a normalized, possibly truncated, possibly suffixed slug from which neither `kb.name` nor `kb.description` can be recovered. The same class of defect cycle 3 found in DD-5/DD-7 — an ordering the code cannot execute — one level deeper. | Dissolved by the DD-7 amendment below: with no entry to build, there is no description to plumb. |
| 2 | high | **AC-22's reachability test was not selective.** DD-4 puts the knowledge base's description into the *tool's own* `description`, and `_filter_candidates` matches per-tool on `name + description` — so a query matching the description already matches without any `source_index` entry. Deleting the entry would not fail the test. The test meant to protect the ordering protected nothing, and would also have masked finding 1 (an empty `synthetic_description` is invisible when the tool's own description carries the same text). | **Escalated as a design question, not fixed as a test.** See the amendment below. |
| 3 | high | AC-9's "widen by taking more of `kb_id`" can produce a name over 64 characters: `KnowledgeBase._validate_id` allows a 64-character `kb_id`, so two knowledge bases sharing a name and a long id prefix would grow the discriminator past the budget AC-8 truncated against — and nothing re-truncates after widening. The stated test case (ids sharing six characters) is short and would not have tripped it, so the overflow could ship green. | Fixed: the discriminator is now a **fixed-length hash** (8 hex of `sha256(kb_id)`, stepping 8→12→16), whose length is known before truncation and can be reserved exactly. New **AC-10b** adds the compound case — a name long enough to need truncation *and* ids sharing a 6+ character prefix. |

**Design amendment — DD-7 loses its `source_index` entry** (operator's call,
2026-09-17). Finding 2 is a tell, not a test bug: the entry was never
load-bearing. `source_index` exists so a query naming an MCP *server* selects
all its tools en bloc; `_filter_candidates` unions those with the per-tool
matches. **A knowledge base has exactly one tool**, so that union adds
nothing the per-tool path does not already find by the same text — the only
residual effect is a ranking `max()`.

Three defects across two review passes were all downstream of keeping the
entry: cycle 3's DD-5/DD-7 ordering contradiction, cycle 2's
`source_index or {}` falsy-bind trap, and finding 1 above. Removing it
removes all three **by construction**, and reduces DD-7 to exactly what
cycle 2 first identified as "the real (and much simpler) change" — a `kb__`
branch in `_format_result`'s prefix parse. I had kept the entry as residue of
the original wrong design, and that residue was carrying the defects.

Options put to the operator were: drop the entry (chosen); keep it with a
terse tool description, which would make it load-bearing and the test
selective but keeps the ordering hazard and withholds the knowledge base's
description from the model at call time; or keep both and test against a
stub, which exercises a shape production never has.

**Also applied**: the `if self.kb_provider is not None` guard mirroring the
MCP idiom; an explicit note on AC-3 that `Agent._execute_tool` calls
`tool.execute(**args)` with no schema validation, so `limit` range-checking
is the tool's own job.

Leg 2 rewritten against the amendment (33 ACs, down from 34 with the
`source_index` cluster removed and the compound naming case added). Changes
are substantive → cycle 2 design review.

### Flight Director Notes — Leg 2 design, cycle 2 (2026-09-17)

**Outcome: approve with changes** — one high, two medium, both suggestions
applied. All mechanical text corrections; no design question remained.

The high is worth recording as a **pattern, not an incident**: AC-7 still
specified `_{kb_id[:6]}` as the collision discriminator, contradicting AC-9's
"always a fixed-length hash … never character-by-character growth of
`kb_id`". AC-7 is the criterion a Developer reads **first**, so a literal
implementation would have rebuilt the exact overflow defect AC-9 was written
to eliminate. This is the same failure mode as Architect cycle 3's high #1
(the numbered ordering still carrying the `wait_for` that a later bullet
removed): **I fix a rule in one place and leave the superseded version
upstream of it, where it is read first.** Twice now in one flight. The
mitigation that worked both times was a reviewer reading the artifact in
Developer order rather than in author order.

| # | Severity | Finding | Disposition |
|---|----------|---------|-------------|
| 1 | high | AC-7 contradicted AC-9 on the discriminator's form, and is read first. | Fixed: AC-7 now names AC-9's hash and says to read AC-9 before implementing. |
| 2 | medium | `flight.md`'s DD-4 still carried the superseded `_{kb_id[:6]}` rule and the "more of `kb_id`, else a short hash" widening order — never back-ported when the leg fixed it. | Fixed at the flight level too: DD-4 now specifies the fixed-length hash, with the 64-character `kb_id` reasoning inline. Also swept the Leg 2 checkpoint, which carried the same stale rule. |
| 3 | medium | `flight.md`'s legs list and Verification bullet still described `source_index` entries, pre-dating the DD-7 amendment in the same document. Harmless to a Developer working from the leg file, misleading to a Leg 3 verifier reading the flight's own checklist. | Fixed both. Zero `kb_id[:6]` references now remain in the flight spec. |

**The amendment was attacked and held.** I asked cycle 2 specifically whether
*any* query shape, ranking outcome or truncation behaviour would differ with
a `source_index` entry present, since the whole amendment rests on there
being none. It came back stronger than the claim: because DD-4 commits the
tool's own `description` to carrying the knowledge base's name and
description verbatim, the source-level haystack's content is a strict subset
of the per-tool haystack's, and `_match_score` is a substring test — so
`per_tool_score >= source_score` **always**, and the ranking `max()` is
always the per-tool score. The residual effect is provably **zero**, not
marginal. DD-7 now states it that way.

Naming arithmetic also verified at the flight level: the fixed `kb__` +
`__search` wrapper costs 12 of 64 characters, so reserving even a worst-case
16-hex discriminator leaves ~35 usable slug characters — never degenerate —
and the 8→12→16 stepping terminates well inside a 64-character digest.

Leg 2 → `ready`, 34 ACs. Implementation spawned.

### Flight Director Notes — flight-end code review (2026-09-17)

**Reviewer tier: Sonnet**, not Haiku. The crew rule calls for Sonnet when the
diff touches a security-sensitive surface. This diff carries no credentials,
key material, middleware or sandboxing — but it changes
`AgentConfig.is_tool_enabled`, the gate deciding which tools an agent can
reach, and the flight's stated security property is that an agent cannot
reach a knowledge base it was not attached to. That isolation claim should
not first be checked by the behavior test. Tier recorded per the crew file.

**Scope**: one deferred review over both implementation legs' uncommitted
changes — 15 modified files, 7 new — by a reviewer with no knowledge of
either Developer's reasoning.

**Outcome: `[HANDOFF:confirmed]`, no findings, blocking or non-blocking.**

What makes that verdict worth trusting is that it did not read the checked
boxes as evidence. It hand-recomputed the two arithmetic claims the flight
turns on:

- **Fusion**: the five crowding chunks score 2/(60+i) ≈ 0.0308–0.0328 against
  the keyword-only exact-term hit's 1/66 ≈ 0.01515, so that hit ranks 6th and
  is excluded at `limit=5` without the reserved slot. The pass-bar test is
  genuinely falsifiable, confirmed independently for the second time (the Leg
  2 design reviewer computed it too, from the spec rather than the code).
- **Name budget**: worst case `4 + 43 + 1 + 8 + 8 = 64` at an 8-hex
  discriminator and `4 + 35 + 1 + 16 + 8 = 64` at 16-hex — never over the
  limit. This is the arithmetic whose absence let the earlier prefix-widening
  scheme overflow undetected.

It also confirmed all four exit paths from `UsearchStore.query` release the
lock, that `manager.py` catches only `VectorStoreStaleError` and never the
new `VectorStoreBusyError` (so a transient busy query cannot trigger a
rebuild), and that `kb_id`/`kb_name` are constructor arguments absent from
`execute(query, limit)`'s signature — so the knowledge base an agent queries
is unforgeable by the model.

Scoped suites 248 passed; `ruff check` and `ruff format --check` clean.

## Reconnaissance Report

Flight 5 sources items from three prior debriefs and two mission open questions. Each was walked against current code before the legs were drafted.

| Item | Classification | Evidence | Recommendation |
|---|---|---|---|
| Mission open question — how semantic and keyword results are combined | `confirmed-live` | No fusion code exists anywhere in `the_one/`; `search_keyword` and `store.query` have no common caller | Settled by DD-3 (operator) |
| Mission open question — `kb__` tools and the enable gate | `confirmed-live` | `agent/config.py::is_tool_enabled` — `is_mcp = tool_name.startswith("mcp__")`, still the only prefix | Settled by DD-6 (operator); regression tests named in Leg 2 |
| Flight 2 debrief Rec. 2 — bound `search_keyword`'s `k`, guard the vector dimension, before Flight 5's agent-facing path | `already-satisfied` | `repositories.py:797` `MAX_SEARCH_K = 1000` with a reject-not-clamp guard; `usearch_store.py::_check_dim` called from `upsert`/`query`/`rebuild_from` (squawk 0054, completed 2026-09-15) | Retire — carried into the spec as a satisfied prerequisite; DD-1 notes `candidate_k` stays well inside the bound |
| Flight 3 debrief Rec. 6 — fusion takes the two crash windows as normal conditions | `confirmed-live` (as a design input, not a gap) | `the_one/agents.md:1211` documents both: FTS5 ahead of vectors for an `indexing` item; a saved sidecar holding ids the re-index deleted | DD-1 tolerates both by construction; `get_many`'s behaviour (P8) is what makes (b) free |
| Flight 3 debrief Rec. 6 — "filtering or flagging chunks of non-`indexed` items" | `confirmed-live`, needed an operator decision | No filter exists; `search_keyword` scopes by `kb_id` only | Operator chose return-unmarked → DD-1 |
| Flight 4 debrief Rec. 7 — the tool provider should treat `unavailable` as a distinguishable state if it surfaces watch health | `already-satisfied by scope` | The search tool surfaces retrieval results, not folder health; `/status` is the watch-health surface and Flight 6 renders it | Retire for this flight — recorded so Flight 6 picks it up |
| Flight 4 debrief Rec. 3 — schedule the "Large-folder settle" behavior-test variant before the mission closes | `confirmed-live`, out of this flight's scope | `tests/behavior/kb-folder-watch-round-trip.md` Variants section; never run | Stays a Flight 6 / mission-close input; this flight adds nothing to it |
| Squawk 0050 — Studio agent save writes `kb_ids: []` | `confirmed-live`, and this flight is what makes it bite | `studio.js:2038` reads `.chip-area[data-type="kb"] .chip`, which nothing renders; `api.py::update_agent` contains no `kb_ids` handling at all | Operator accepted the window → DD-10; squawk stays open for Flight 6 |
| Mission Known Issue — `get_vector_store()` has no shutdown hook | `confirmed-live`, out of scope | Unchanged; resolution point recorded at Flight 6 / mission close (Flight 4 debrief Rec. 5) | No action here; retrieval never writes to the store |
| Flight 3/4 test-metrics observations — the suite's wall time and the one 10 s outlier | `needs-human-recheck` at Leg 3 | Flight 4 debrief Test Metrics: 4,649 passed / 10 skipped / ~637 s; `test_mcp_pool.py::test_drain_timeout_handles_stuck_worker` 10.0 s, pre-existing | Leg 3 records the gate figures against that series; no action expected |

---

## Deviations

**Leg 1**: none from the leg spec. `SEMANTIC_QUERY_TIMEOUT`'s exact value
(2.0s) was left to Leg 1 by design (DD-1 pins only the reasoning, not the
number) and is recorded as a Developer decision, not a deviation, in the
Leg 1 implementation entry above.

---

## Anomalies

**Leg 1**: no test-level anomalies — all scoped suites passed, no flakiness
or hangs, and the completed `make test-unit` run was clean (4,688 passed, 10
skipped, exit 0, 623 s).

One process-level event the Flight Director observed that the Developer's
own report does not mention: the **first** `make test-unit` invocation was
terminated externally at 86% (`make: *** [Makefile:219: test-unit]
Terminated`), after ~630 s, with **4,046 tests passed and zero failures** up
to that point. It was not a test failure and not the `run-tests.sh`
`TEST_TIMEOUT` (1200 s default); the most likely cause is the agent's own
tool-call ceiling on a long foreground run. The Developer restarted the gate
and the second run completed cleanly. Recorded because a terminated gate run
is indistinguishable from a wedged one in a log read later, and because it is
the second flight in a row where a long foreground gate has bumped an agent's
budget — worth watching as a pattern rather than treating as noise.

**Flight Director correction**: I initially flagged the Developer's gate
invocation as a deviation from the canonical `make test-unit`, having seen
`run-tests.sh tests/ -m '...' -v --tb=short` in the process list. That was my
error — `Makefile:219` expands `test-unit` to exactly that command, so what
I saw was the target's own expansion. The Developer ran the canonical gate
verbatim. No deviation occurred and none is recorded.

---

## Session Notes

- 2026-09-17 — Planning session. Context gathering and code interrogation ran alongside the squawk turnaround (disjoint files); interview, premise probes P1–P10, reconnaissance, spec draft, behavior-test draft. Architect design review next.
