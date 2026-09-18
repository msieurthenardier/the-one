# Flight: Agent Query

**Status**: completed
**Mission**: [Knowledge Bases](../../mission.md)

## Contributing to Criteria

- [x] Retrieval combines semantic and keyword matching, so a query naming an exact term finds it even when the embedding model ranks that term poorly *(met in full here: one retrieval module fusing the vector store and FTS5 by reciprocal rank, with the exact-term guarantee pinned by targeted tests)*
- [x] An attached agent can discover and query its knowledge bases during a chat session, and cannot reach one it is not attached to *(met here; behavior-test-backed — `kb-agent-query-round-trip`)*
- [x] A knowledge base can be attached to and detached from any agent in Studio *(the functional half lands here — `AgentConfig.kb_ids` stops being inert and builds tools; the Studio surface is Flight 6)*
- [x] Existing installs upgrade with no data loss, the unit gate stays green, and the frozen Windows installer still builds and runs *(no schema change, no dependency change; one frozen run at flight close as a diagnostic)*

---

## Pre-Flight

### Objective

Make an attached knowledge base answerable by its agents. One retrieval
module fuses the vector store's semantic hits with FTS5's keyword hits by
reciprocal rank, tolerating the two crash windows Flight 3 recorded as
normal operating conditions. One `kb__{slug}__search` tool per attached
knowledge base is built by a per-agent provider, registered by
`AgentFactory` beside the MCP tools, discoverable through `search_tools`
under its own `kb:` group, and reachable only by agents the operator
attached it to. `AgentConfig.is_tool_enabled`'s hardcoded `mcp__` carve-out
generalizes so a narrowed built-in whitelist no longer silently strips every
knowledge-base tool. No schema change, no new dependency, no UI.

### Open Questions

- [x] How semantic and keyword results are combined, and whether the balance is operator-tunable → DD-3 (operator, 2026-09-17: reciprocal rank fusion with a fixed constant; no dial)
- [x] Whether `kb__` tools follow the built-in whitelist path or the MCP-override path → DD-6 (operator, 2026-09-17: generalize the prefix set; `disabled_tools` stays universal)
- [x] What retrieval does with chunks whose item is not `indexed` → DD-1 (operator, 2026-09-17: return them unmarked)
- [x] What evidence the exact-term criterion needs → DD-3 (operator, 2026-09-17: targeted tests, no recall benchmark this flight)
- [x] The behavior test's apparatus → DD-9 (operator, 2026-09-17: mock provider with scripted tool calls, shell-only)
- [x] Whether query embedding must take the indexing manager's embed lock → DD-2 (measured at planning: concurrent encode is bit-identical and costs 0.08 ms; it does not)
- [x] Whether this flight carries a HAT leg → no: no operator-visible surface (the standing rule from the Flight 3 debrief); the behavior test is the acceptance gate and the walk folds into Flight 6's HAT
- [x] Whether squawk 0050 (Studio agent save writes `kb_ids: []`) must be fixed before this flight makes attachment functional → operator's call, 2026-09-17: **no** — the gap between this flight and Flight 6 is accepted; recorded in DD-10

### Design Decisions

**DD-1 — Retrieval is its own module, not a method on the tool: `the_one/knowledge/retrieval.py`**
- `search(kb_id, query, *, limit, chunk_repo, item_repo, store, backend) ->
  SearchResult`, where `SearchResult` is a frozen dataclass
  `(hits: list[SearchHit], degraded: str | None)` and `SearchHit` is a frozen
  dataclass `(chunk_id, item_id, path, seq, char_start, char_end, text, score)`.
  **A result object, not a bare list** (Architect cycle 1): the degrade
  channel below has to travel with the hits, and both DD-8's rendering and
  Flight 6's inventory read it. A bare `list[SearchHit]` has nowhere to put
  `degraded` — the earlier draft said "on the result object" while typing the
  return as a list, which was a contradiction inside one decision.
  A module rather than a `KBSearchTool` method so Flight 6's inventory can
  render the same results the agent sees without going through a `Tool`,
  and so fusion is unit-testable with no agent, no registry and no LLM.
- Order of work: (1) an empty or whitespace-only `query` returns an empty
  `SearchResult` without touching the store or the database (`search_keyword` already
  short-circuits; the vector side must too, since embedding an empty string
  produces a near-zero vector whose neighbours are meaningless); (2) embed
  the query (DD-2); (3) run `store.query(kb_id, vec, candidate_k)` and
  `chunk_repo.search_keyword(kb_id, query, candidate_k)` concurrently under
  **`asyncio.gather(..., return_exceptions=True)`**, then inspect both slots.
  The semantic call passes its bound **into the store** —
  `store.query(kb_id, vec, candidate_k, timeout=SEMANTIC_QUERY_TIMEOUT)`,
  which raises `VectorStoreBusyError` (see the degrade rule below).
  **No `asyncio.wait_for` wraps the store call**, and none may be added: the
  store does its work inside its per-KB lock, so cancelling the await frees
  the lock while a pool thread is still reading the index — measured, and the
  reason cycle 1's version was replaced. The bound belongs on the lock
  acquisition, inside the store, never on the call; (4) fuse by
  reciprocal rank (DD-3) and take the top `limit`; (5) `chunk_repo.get_many`
  the surviving ids — it preserves the caller's order and silently drops ids
  with no row, which is exactly crash window (b); (6) resolve each chunk's
  item path in one pass (`item_repo.get` per distinct `item_id`, at most
  `limit` lookups, memoised within the call). **This numbered list is the
  authoritative ordering**; the bullets below constrain steps within it and
  add no step to it.
- **`return_exceptions=True` is load-bearing, not a style choice** (Architect
  cycle 1). A plain `asyncio.gather` propagates the first exception to the
  awaiter and leaves the sibling coroutine's result unretrieved — so an
  `except VectorStoreStaleError` handler would have **no keyword results to
  return**, and the orphaned task can surface as "Task exception was never
  retrieved". The degrade rule below is unreachable through a plain gather;
  the Leg 1 checkpoint that asserts it would fail against a spec-conformant
  implementation.
- **"Concurrently" is a bounded claim.** Both calls share the one
  process-wide aiosqlite connection, so the gather overlaps the store's
  `to_thread` search with the FTS query and nothing more. No deadlock — the
  two take no lock of each other's — but the parallelism is one thread hop,
  not two independent query paths.
- `candidate_k = min(max(limit * 5, 25), 100)` — deep enough that a hit
  ranked poorly by one side still reaches fusion, shallow enough that
  `get_many` and the item lookups stay trivial. Well inside
  `MAX_SEARCH_K` (1,000), so `search_keyword`'s `ValueError` guard
  (squawk 0054) is never tripped by this path.
- **Both crash windows are tolerated by construction, not by a check**
  (`the_one/agents.md`, "Two crash-window consequences recorded for Flight
  5's fusion design"): (a) FTS5 can return chunks of an `indexing` item
  whose vectors have not landed — those chunks appear with a keyword rank
  only, which RRF handles natively; (b) the saved sidecar can hold ids the
  last re-index deleted from `kb_chunks` — `get_many` returns fewer rows and
  the fused list is simply shorter. **A chunk whose item is not `indexed`
  is returned unmarked** (operator's call, 2026-09-17): the chunk text is
  committed and real, an item mid-reindex still answers questions, and a
  per-result status marker would put noise in front of the model on every
  hit. Recorded as a deliberate choice, not an oversight.
- **The semantic side degrades to keyword-only, loudly in the result, never
  silently — on three distinct causes, each with its own message.** All are
  caught in `search`, logged at warning, and returned as the keyword-side
  hits with `SearchResult.degraded` set; DD-8 renders it as one line above
  the hits.
  - `VectorStoreStaleError` out of `store.query` →
    `degraded="semantic index rebuilding"`.
  - `VectorStoreBusyError` out of `store.query` (the new bounded-acquisition
    path below) → `degraded="semantic index busy"`.
  - **Any other exception** in the semantic slot — notably
    `UsearchStore._check_dim`'s `ValueError`, which fires whenever the
    configured embedding dim and the stored index disagree, a realistic
    post-upgrade state — is logged with its type and degraded as
    `"semantic index unavailable"`. Specified because `return_exceptions=True`
    turns *every* exception into a value: an implementation that
    `isinstance`-checks only the named types would hand a third one to fusion
    as if it were a result list and fail with an opaque `TypeError`.
  **Distinct strings, not one** (Flight Director's call on the Architect's
  cycle-1 question 3): "rebuilding" heals itself and is expected after a
  stale sidecar; "busy" means a query landed during a long write and says
  nothing is wrong; "unavailable" means something is actually broken.
  Collapsing them would make the common case look like the exceptional one.
- **The keyword slot degrades symmetrically**: an exception there →
  `degraded="keyword index unavailable"` with the semantic-side hits
  returned. Losing the keyword side costs the mission's exact-term
  guarantee, so it is surfaced rather than swallowed — but semantic-only
  hits are still worth returning, which is the same judgement the semantic
  branch makes in reverse. Both slots failing → the **semantic** slot's exception is raised (named, so
  the message is deterministic rather than depending on gather ordering), and
  the tool surfaces an honest error (the `web_search` precedent).
- **The bound is on acquiring the lock, never on the work inside it**
  (Architect cycle 2, corrected; operator's call, 2026-09-17). Cycle 1
  specified `asyncio.wait_for(store.query(...), SEMANTIC_QUERY_TIMEOUT)`.
  **That was wrong, and I verified it wrong with a probe before changing
  it**: `UsearchStore.query` does its work as
  `async with entry.lock: await asyncio.to_thread(entry.index.search, ...)`,
  and cancelling that await releases the caller *and the lock* while the
  pool thread is still executing against `entry.index`. Measured: caller
  released and lock free at 0.302 s, next holder acquired at 0.302 s, escaped
  thread still running until 1.502 s. In production that next holder is
  `upsert` (`index.remove`/`index.add`), `flush` (`index.save`) or
  `rebuild_from` (which replaces `entry.index`) — so the timeout would
  silently convert the store's exclusive region into a racy one, with a
  corrupt sidecar or a segfault inside the C extension as the failure mode,
  neither logged nor recoverable in-process.
  **Instead**: `UsearchStore.query` gains a **keyword-only** `timeout`
  parameter (`*, timeout: float | None = None`, so existing positional calls
  like `store.query("kb", vec, 1)` keep working and no future caller can
  confuse it with `k`) that bounds **only** `entry.lock.acquire()`, raising
  `VectorStoreBusyError` when it expires. Nothing in-lock is ever cancelled,
  the exclusivity invariant is untouched, and the bound covers exactly the
  pathological case — a query queued behind an upsert, flush or rebuild.
  - **The acquire sits OUTSIDE the `try`**; the `finally: entry.lock.release()`
    therefore runs only on a lock actually held. An acquire placed inside the
    `try` raises `RuntimeError: Lock is not acquired` from the `finally` on
    every timeout, masking the `VectorStoreBusyError` — a trap worth one
    clause to close.
  - **`class VectorStoreBusyError(VectorStoreError)`** — never a subclass of
    `VectorStoreStaleError`. `manager.py` catches `VectorStoreStaleError` and
    responds with `rebuild_kb`, a full re-embed of the knowledge base;
    inheriting from it would turn a transient busy query into a rebuild
    storm.
  - **Home is `the_one/vectors/_store.py`**, beside `VectorStoreError` and
    `VectorStoreStaleError`, re-exported from `the_one/vectors/__init__.py`
    per the `canonical-import + convenience-re-export` convention — not
    defined in `usearch_store.py`, which would split the hierarchy across two
    modules.
  - **`timeout` joins the `VectorStore` Protocol signature and its contract
    docstring** in `_store.py` (Flight Director's call on the Architect's
    cycle-3 question 2). The seam exists to accept a second backend; leaving
    the parameter a `UsearchStore`-only extension would either break
    retrieval against that backend or force retrieval to reach through a
    concrete type, defeating the Protocol.
  - No existing `except` clause breaks: `VectorStoreBusyError` can only be
    raised when a caller passes `timeout`, and `store.query` has **no**
    production caller in `the_one/` today — only tests and the bench script.
  **This widens Leg 1 into `the_one/vectors/`** (`usearch_store.py`,
  `_store.py`, `__init__.py`), which DD-11 otherwise declares untouched; the
  operator accepted that scope widening in preference to leaving the work
  uncancellable-but-abandoned. `SEMANTIC_QUERY_TIMEOUT` is a named
  module-level constant.
  - **The bound covers the waiter, never the holder.** It does not bound the
    semantic call's duration: the first query after a restart acquires a free
    lock immediately and then blocks inside `_ensure_loaded`'s
    `to_thread(Index.restore, ...)` for as long as the sidecar takes,
    unbounded up to the 120 s tool ceiling. Stated here and in the new
    docstring, because a checkpoint that expects a degrade from a long
    *in-lock* operation would be testing something this design deliberately
    does not do.
  - The busy-path WARNING carries `kb_id` and the elapsed/`SEMANTIC_QUERY_TIMEOUT`
    values: a genuine deadlock (as opposed to a long flush) now degrades
    quietly and indefinitely, so that one line is the only signal an operator
    gets and it must be diagnosable on its own.
- **Why the bound exists at all.** Staleness is only observable in the window
  *before* the manager starts healing it — once `rebuild_from` is running,
  `store.query` does not raise `VectorStoreStaleError`, it waits on the
  per-KB lock for the rebuild's full duration (DD-2). Unbounded, the degrade
  path is defeated in precisely the scenario it was written for, and the only
  thing that ends the wait is the agent loop's 120 s tool-call ceiling
  (`the_one/agent/core.py`, `THE_ONE_TOOL_CALL_TIMEOUT_SECONDS`), which
  reaches the model as an opaque `timed out after 120s` instead of usable
  keyword results.
- **Choosing `SEMANTIC_QUERY_TIMEOUT`.** Against the Flight 2 Windows figures
  in DD-2 (~1.8 s per 256-vector upsert batch at 1M; 10–12 s per flush at 1M,
  ~24 s at 3M), any value below flush duration means a query concurrent with
  a flush degrades to keyword-only rather than waiting. **That is the
  intent** — a few seconds of agent latency is worse than keyword-only
  results, and the reserved keyword slot (DD-3) means the exact-term
  guarantee survives the degrade. Leg 1 picks the constant and records this
  reasoning beside it.
- **The cold-start path is the realistic way into a long acquisition.**
  `_ensure_loaded`'s `to_thread(Index.restore, ...)` also runs in-lock, and
  its duration scales with the corpus — so the *first* query after a restart
  on a large sidecar is the common case where a second query queues behind a
  long in-lock operation. Recorded next to DD-2's per-KB-lock correction.
  The indexing manager's worker is what heals the sidecar (Flight 3 DD-6) —
  retrieval never rebuilds.
- **No empty-knowledge-base short-circuit** (Architect cycle 2). Cycle 1
  added a `count_for_kb(kb_id) == 0` fast path; it costs more than it saves.
  `count_for_kb` is `SELECT COUNT(*) FROM kb_chunks WHERE kb_id = ?`, an
  index scan over every chunk row of the knowledge base — O(n) on the
  agent-facing hot path, and at the mission's low-single-digit-GB ceiling
  that is millions of rows. What it avoids is a 0.08 ms embed: both backends
  already return `[]` cheaply for an empty knowledge base (`search_keyword`
  short-circuits, and `store.query` returns immediately when
  `len(entry.index) == 0`). Dropped.
- Rejected: a single blended SQL query (the vector side is not in SQLite);
  querying the store first and filtering FTS to those ids (that is semantic
  search with keyword re-ranking, which cannot surface the exact-term hit
  the mission criterion names); caching query embeddings (0.08 ms, DD-2).

**DD-2 — Query embedding takes no lock and runs under `asyncio.to_thread`**
- Measured at planning on the bundled `potion-retrieval-32M` (flight log,
  "Planning premise probes" P1–P3): a single-query `embed` costs **p50
  0.08 ms / p95 0.17 ms**; eight concurrent `embed` calls from separate
  threads returned **bit-identical** vectors to the serial baseline with no
  error. The `IndexingManager`'s `_embed_lock` exists to serialise the
  embed-**plus-upsert** pair across per-KB workers, not because the model
  needs mutual exclusion for a read-only encode.
- Therefore the retrieval path **never acquires the manager lock**, and the
  lock-order invariant (`manager.py`: manager lock → store per-KB lock →
  write lock) is never in play on this path.
- **But retrieval is not decoupled from indexing, and an earlier draft of
  this decision claimed it was** (Architect cycle 1, corrected). The claim
  "agent query latency is never coupled to indexing" was false.
  `UsearchStore.query` acquires `entry.lock` — the *same* per-KB lock that
  `upsert` holds across its `to_thread` write, that `flush` holds across
  `_save_atomically` plus the registry write, and that `rebuild_from` holds
  across the caller's **entire generator**, i.e. across a full re-embed of
  the knowledge base. On Flight 2's Windows figures that is roughly 1.8 s for
  a 256-vector upsert batch at 1M, 10–12 s for a flush at 1M (~24 s at 3M),
  and hours for a rebuild. What is true is narrower and worth stating
  precisely: **the manager's embed lock is never taken; the store's per-KB
  lock is, and a query concurrent with an upsert, flush or rebuild waits on
  it — bounded by `SEMANTIC_QUERY_TIMEOUT` (DD-1), not by the agent loop's
  120 s tool ceiling.** This is the same class of fact as the two crash
  windows and is recorded as a third consequence beside them in
  `the_one/agents.md` (Leg 1's doc update).
- The encode still runs under `asyncio.to_thread`, matching the indexer, so
  a future backend that is not sub-millisecond cannot block the event loop.
  The measurement is recorded in the module docstring beside the rule, so a
  later reader can see why no lock is taken.
- **The numbers are Linux and are discounted; the conclusion rests on the
  code path, not on them** (review item 7, applied reflexively to my own
  probes). P1–P3 ran on this WSL host with `TOKENIZERS_PARALLELISM`, the
  rayon pool and `OMP_NUM_THREADS`/`OPENBLAS_NUM_THREADS` all unpinned, and
  the mission's standing rule since Flight 1 is to benchmark on Windows or
  discount Linux numbers explicitly. Discounted, then — the reason the result
  is platform-independent is structural: `LocalStaticBackend.embed` calls
  `StaticModel.encode(use_multiprocessing=False)`, whose path is
  tokenize → numpy fancy-index gather → mean → L2 normalise. It mutates no
  model state and reaches no BLAS/OMP kernel, so there is nothing for a
  thread-count environment variable to change. (Note that model2vec sets
  `TOKENIZERS_PARALLELISM=false` only in its multiprocessing branch, which
  this backend disables — so the tokenizer's pool is whatever the environment
  supplies, including on the frozen Windows app. It does not matter here for
  the same structural reason.)
- **The concurrency guarantee becomes a contract, not a measurement of the
  one implementation.** `EmbeddingBackend` is a seam that exists to accept a
  second backend, and a future ONNX/torch/remote one can easily be
  non-reentrant — at which point this DD's rule would be silently false.
  Leg 1 adds one sentence to `the_one/embeddings/_backend.py::EmbeddingBackend`'s
  docstring: `embed` must be safe to call concurrently from multiple threads.
  Then the no-lock rule holds by contract and a future backend author is
  told.

**DD-3 — Reciprocal rank fusion, fixed constant, ranks only**
- `score(chunk) = Σ over the lists it appears in of 1 / (RRF_K + rank)`,
  ranks 1-based, `RRF_K = 60` (the constant from the method's original
  publication; a module-level named constant, not a literal).
- **One result slot is reserved for the keyword-only side whenever both
  lists are non-empty** (operator's call, 2026-09-17; trigger corrected at
  Architect cycle 3). Plain RRF cannot satisfy the mission's exact-term
  criterion at the chosen candidate depth — the arithmetic below is
  unambiguous — so rather than let the flight's own Divert criterion trip
  mid-implementation and re-plan the fusion design then, the fix lands now.
- **The rule, as pseudocode** — prose ambiguity in this paragraph produced
  two high-severity review findings across cycles 2 and 3, so the
  authoritative statement is code-shaped:
  ```
  fused = sort_by(rrf_score desc, in_keyword_list desc, chunk_id asc)
  top   = fused[:limit]
  keyword_only = [h for h in fused if h.in_keyword and not h.in_semantic]
  if (limit >= 2
      and keyword_list is not empty
      and semantic_list is not empty
      and keyword_only is not empty
      and not any(h in keyword_only for h in top)):
      top[-1] = keyword_only[0]          # displaced hit's position, i.e. last
  return top
  ```
- **"Keyword-only" means exactly that: present in the keyword list and absent
  from the semantic list.** A chunk in **both** lists does **not** count as
  keyword representation for this rule. This is the distinction the whole
  guarantee turns on, and getting it wrong makes the rule a no-op in the one
  case it exists for: in DD-3 test 4 the five crowding chunks are all
  both-list, so a trigger phrased over "keyword-side" hits would see
  representation, do nothing, and leave the exact-term hit at fused rank 6 —
  failing the test the Leg 1 checkpoint names as the flight's pass bar. The
  mission criterion is about a term *the embedding model ranks poorly*, which
  is precisely a keyword-**only** hit.
  Note the phrase carries the *other* sense two bullets down, in the tie-break
  sort key, where `in_keyword_list` correctly counts a both-list hit. Two
  senses, one decision — they are named differently (`keyword_only` vs
  `in_keyword_list`) in the pseudocode above so they cannot drift together.
- **Three guards, each for a case that would otherwise be a defect**:
  `keyword_only` non-empty (a result where every keyword hit is also a
  semantic hit satisfies the trigger but has no displacer — a literal
  `keyword_only[0]` would raise `IndexError` on ordinary input); both lists
  non-empty (a one-sided result is already whatever its one side returned);
  and **`limit >= 2`** (Flight Director's call on the Architect's cycle-3
  question 1). At `limit = 1` the rule and the tie-break act on the same
  single slot, and the rule would evict a both-list winner — the strongest
  signal there is, matched by both retrievers — in favour of a keyword-only
  hit. The criterion is not at risk there: a both-list winner *is* a keyword
  match, so the model receives a chunk that matched the exact term. DD-3
  test 2 is therefore written at `limit >= 2`, and test 3 is unaffected (its
  keyword-only winner survives, so the trigger is false).
- **The reserved hit takes the displaced hit's position — last.** Stated
  because DD-8 renders hits best-first and the context governor truncates
  from the *head*, so on a small-context model the reserved hit is the first
  thing dropped. That is the correct trade (it is the lowest-scoring hit by
  construction), but it is a consequence worth knowing rather than
  discovering.
- **When the rule fires, log at DEBUG which hit was displaced and which
  replaced it** (Flight Director's call on the Architect's cycle-3
  question 3). DD-3 deliberately ships no dial and DD-12 defers the recall
  benchmark; a counter of how often the guarantee costs a semantic hit is
  what will let that benchmark say whether a dial was ever needed.
- **Ties break toward the keyword side first, then ascending `chunk_id`**
  (Flight Director's call on the Architect's question 2). The earlier draft
  broke ties on `chunk_id` alone, which decides the mission's exact-term
  criterion by coin flip at the boundary: at `limit = 1` a keyword-only
  rank-1 hit scores exactly `1/61`, the same as a semantic-only rank-1 hit,
  and the lower `chunk_id` wins for no reason connected to the criterion.
  Sorting by `(-score, not_in_keyword_list, chunk_id)` makes the criterion
  hold at every `limit` and costs one clause in the sort key. `chunk_id`
  remains the final tie-break, so the list stays deterministic for a given
  input.
- Rank-based because **the two score scales cannot be compared**: FTS5
  returns `bm25()`, which is negative and lower-is-better
  (`repositories.py::search_keyword` states this and deliberately returns
  the raw value); `UsearchStore.query` returns usearch **distances**, also
  lower-is-better but on an unrelated scale that varies with the dtype
  (`f16` today, `i8` a supported alternative). Both lists arrive best-first,
  so rank is read directly from list position — no normalisation, nothing to
  recalibrate if the store's dtype ever changes.
- **Not operator-tunable** (operator's call, 2026-09-17): `RRF_K` is not a
  dial an operator can evaluate without a recall benchmark, and this flight
  ships no benchmark. A future weighting knob would be a settings record and
  a measurement, not a constant someone guesses at.
- **Crowding is real at the chosen depth, and the tests must be able to trip
  it** (Architect cycle 1). The arithmetic: at `candidate_k = 25`, any chunk
  present in *both* lists scores at least `2/85 = 0.0235`, while a
  keyword-only rank-1 hit scores `1/61 = 0.0164`. So **any** both-list chunk
  outranks the exact-term hit, and with `limit = 5`, five both-list chunks
  crowd it out entirely. Precisely: `2/(60+r) > 1/61` for all `r <= 61`, so
  **every** both-list chunk ranked within ~61 on both sides outranks a
  keyword-only rank-1 hit. A larger `candidate_k` narrows the window but does
  not close it — `candidate_k = 100` is not a safe configuration either, it
  is merely a less crowded one. This is why the reserved slot above is a rule
  rather than a tuning exercise.
- **FTS5's implicit AND is a real limit on the guarantee, and it is recorded
  rather than discovered later** (Architect cycle 1). `search_keyword` quotes
  each whitespace-separated term and joins them, which FTS5 reads as AND. A
  sentence-shaped query that happens to contain the rare identifier therefore
  returns **zero** keyword hits — the keyword side contributes nothing in
  precisely the case where a model asks in natural language. Two responses,
  both in Leg 1: the tool `description` (DD-4/DD-8's contract) instructs
  terse, keyword-shaped queries; and a test pins the sentence-shaped case so
  the limit is a recorded property rather than a surprise in Flight 6.
- **The exact-term guarantee is pinned by targeted tests, not a benchmark**
  (operator's call). Five tests, named in Leg 1:
  1. A chunk containing a rare identifier the embedding model ranks outside
     the candidate window is present in the fused result and absent from the
     semantic-only result.
  2. A chunk appearing in both lists outranks one appearing in only one, at
     equal ranks.
  3. `limit = 1` with a keyword-only rank-1 hit tying a semantic-only rank-1
     hit: the keyword hit wins (the tie-break above).
  4. `candidate_k = 25` with five both-list chunks ahead of the exact-term
     hit, at `limit = 5`. **Pass condition: the exact-term hit appears within
     the returned `limit` results** — the mission criterion's own wording,
     and the strict bar. Plain RRF fails this by the arithmetic above; the
     reserved keyword slot is what makes it pass. This test is the one that
     would catch the reserved slot being dropped or mis-implemented, so it is
     named in the Leg 1 checkpoint.
  5. A sentence-shaped query containing the rare identifier: records the
     FTS5 implicit-AND behaviour.
- Rejected: weighted score after per-query normalisation (fragile on short
  corpora, and the normalisation has to be re-derived whenever the store's
  dtype changes); keyword as a fallback only when semantic recall looks thin
  (gives up the criterion — an exact term the model ranks poorly is exactly
  the case where semantic recall does *not* look thin).

**DD-4 — One `kb__{slug}__search` tool per attached knowledge base, built per agent**
- The mission's invariant: KB identity is baked into the tool instance, never
  an argument, because the registry gates on tool name and not on arguments.
- `slug = _normalize_kb_name(kb.name)` — the same rule as
  `the_one/mcp/_tool.py::_normalize_source_name` (every character outside
  `[a-zA-Z0-9_-]` becomes `_`), re-implemented in the knowledge package for
  package independence; a shared docstring note points at the sibling so the
  two never drift silently. (Stated honestly: the MCP boundary is *already*
  crossed here — `factory.py::_build_source_index` lazily imports
  `_normalize_source_name` today — so the duplication is a package-hygiene
  preference, not the avoidance of a crossing that does not otherwise exist.)
- **A slug can itself contain `__`, which mis-renders the group label.**
  `"My  Notes"` (two spaces) normalises to `My__Notes`, giving
  `kb__My__Notes__search`, whose `split("__", 2)[1]` is `My`. This is the
  same latent flaw the MCP path already has, so precedent covers leaving it —
  but DD-7's tests pin the normalized-segment behaviour, and this case is
  named among them so it is recorded rather than discovered.
- **Collisions are an ordinary state, not an edge case.**
  `knowledge_bases.name` is `TEXT NOT NULL` with no UNIQUE constraint and
  `create_knowledge_base` does no duplicate check, so two knowledge bases
  named `Docs` are a normal thing an operator can make.
- **The collision suffix is a property of the group, not of position**
  (Architect cycle 1, corrected). The earlier draft suffixed "the second and
  subsequent" colliding slug and claimed that made the name independent of
  iteration order. It does not: *which* knowledge base is "second" is decided
  by `config.kb_ids` order, which the operator controls and which is stored —
  reorder the list and the two tools swap names. That is not cosmetic,
  because `disabled_tools` is name-keyed: an operator's
  `disabled_tools: ["kb__docs__search"]` would silently re-target a
  *different* knowledge base after a reorder, and detaching the first would
  rename the second's tool back to the unsuffixed form and dangle the
  blacklist entry. **Rule: if a slug has more than one claimant among the
  agent's attached knowledge bases, every member of that group gets the group
  discriminator** — the fixed-length hash defined in the next bullet, **never
  a prefix of `kb_id`**. Deterministic under reorder; only attach/detach
  changes a name, which is a legible cause.
- **Uniqueness is asserted, not assumed** (Architect cycle 2; operator's
  call on its question 4; the discriminator's *form* corrected again at Leg 2
  design review). A `kb_id`-prefix discriminator is **not** guaranteed unique:
  `POST /api/knowledge-bases` accepts a **client-supplied `id`** (it only
  auto-generates `uuid4().hex[:12]` when absent), so two bases created as
  `kb-docs-1` and `kb-docs-2` both yield `kb-doc` — and two colliding `Docs`
  bases would then produce the *same* tool name, which
  `ToolRegistry.register`'s last-write-wins silently resolves by dropping one
  knowledge base's only tool. That is the exact failure the group-wide rule
  was written to prevent. **Rule** (corrected at Leg 2 design review): the
  discriminator is **always a fixed-length hash** — the first 8 hex
  characters of `sha256(kb_id)`, stepping to 12 then 16 only if a group still
  collides — **never a prefix of `kb_id`, and never character-by-character
  widening**. `KnowledgeBase._validate_id` permits a 64-character `kb_id`,
  the same as `_TOOL_NAME_MAX_LEN`, so prefix-widening can push a name past
  the very limit truncation already budgeted against, with nothing to
  re-truncate it. A fixed length is known *before* truncation and can be
  reserved exactly. The provider computes the whole agent's tool-name set and
  asserts uniqueness across it, logging at WARNING whenever it widens.
- **Over-length and colliding compose to one suffix, applied once**: truncate
  the slug to fit, then append a single discriminator, then run the
  uniqueness assertion above. Never two suffixes. Truncation discards exactly
  the distinguishing tail of a long name, so the assertion is what makes this
  safe rather than the truncation itself.
- **The provider computes the final name; the tool receives it.** Group
  collision detection needs the agent's whole attached set, which only
  `KBToolProvider` has — so naming is a provider responsibility, and
  `KBSearchTool` takes the finished name and sets it as an instance
  attribute before `super().__init__(agent_name=...)`.
- **Over-length names truncate and suffix; they are never dropped**
  (Flight Director's call on the Architect's question 1). The 64-character
  LLM ceiling is `the_one/mcp/_tool.py::_TOOL_NAME_MAX_LEN`, and the
  `MCPClientTool` precedent drops the offending tool with a WARNING. That
  precedent does not transfer: for an MCP source a drop costs one tool out of
  many, but here it costs **the knowledge base's only tool** — the whole
  attachment, invisibly, with nothing but a log line. `KnowledgeBase.name`
  has no length validation today, so a name over ~52 characters reaches this.
  Instead the slug is truncated to fit and the hash discriminator appended
  (its length reserved before truncation, per the rule above), keeping
  the name unique and the attachment alive; the truncation is logged at
  WARNING. A name-length hint on the Studio field is carried into Flight 6.
- `KBSearchTool(Tool)` sets `name` / `description` / `parameters` as
  **instance** attributes before `super().__init__()` — the `MCPClientTool`
  precedent, whose docstring records that the base `__init__` does not touch
  those three. It must also pass `agent_name` through to
  `super().__init__()`, as `MCPClientTool` does:
  `tests/test_factory.py::TestAgentNamePlumbing::test_agent_name_threads_to_tools`
  iterates **every** registered tool and asserts `tool._agent_name == name`,
  so a `KBSearchTool` that omits it fails an existing test. Parameters: `query` (string, required) and `limit` (integer,
  optional, default 5, 1–20; out-of-range is rejected with a message, not
  clamped, matching `search_keyword`'s convention). `description` names the
  knowledge base and, when set, its description, so `search_tools` matching
  has something to bite on.
- The tool holds `kb_id` and `kb_name`; `execute` resolves its own
  connection, repositories, store and backend at call time (the tool is
  built once per agent construction and may outlive any one of them) and
  calls DD-1's `search`. **`get_embedding_backend()` is resolved under
  `asyncio.to_thread`**, as `warm_up()` itself does: it is synchronous and
  takes a `threading.Lock`, so calling it on the event loop before warm-up
  has finished blocks the loop for the model load (0.38 s on this Linux host,
  unmeasured on Windows).

**DD-5 — `KBToolProvider`: async, per-knowledge-base keyed, the `MCPToolProvider` sibling shape**
- `the_one/knowledge/tool_provider.py::KBToolProvider.get_tools_for_agent(config, *, agent_name) -> list[Tool]`.
  **Not** a `the_one/tools/provider.py::ToolProvider` Protocol implementer,
  for the reason `MCPToolProvider`'s docstring already gives: that Protocol
  is synchronous and per-tool-name keyed, while this is async and per-entity
  keyed. Sibling class, same call shape, so `AgentFactory` gains a third
  block that reads like the second.
- Empty `config.kb_ids` → `[]` with no database call. A `kb_id` that no
  longer exists → WARNING naming the agent and the id, skip that one, keep
  the rest (the orphan-source precedent).
- **Wired in `AgentFactory.create` immediately after the MCP block**, behind
  the same filter: `if tool.name not in disabled_names and
  config.is_tool_enabled(tool.name)`, so the disabled/enabled composition
  stays in exactly one place. (Cycle 3 had to specify a four-step ordering to
  reconcile this with DD-7's `source_index` entries; DD-7's amendment removes
  the entries, and with them the constraint — the provider call has no
  ordering requirement relative to `SearchTools` at all.)
- **The earlier draft's rationale for registering last was backwards**
  (Architect cycle 1, corrected). It claimed "being last means a
  knowledge-base tool can never shadow a built-in or MCP name".
  `ToolRegistry.register` is `self._tools[tool.name] = tool` — **last write
  wins** — so registering last means a KB tool *would* shadow a same-named
  tool. It is harmless today only because the `kb__` prefix makes a collision
  impossible, and that, not ordering, is the actual reason. Stated correctly
  here so a later reader does not build on the inverted version.
- **Constructor-injected, like `mcp_provider`**, so `tests/test_factory.py`'s
  registration and isolation tests have a seam to substitute at. The import
  in `factory.py` must be **lazy** (inside the method), for the cycle
  `_build_source_index`'s docstring already records:
  `agent.__init__ → agent.factory → db.repositories → agent.config → agent.__init__`.

**DD-6 — `is_tool_enabled` generalizes its carve-out from one prefix to a named set**
- Today `the_one/agent/config.py::AgentConfig.is_tool_enabled` computes
  `is_mcp = tool_name.startswith("mcp__")` and applies the `enabled_tools`
  whitelist only to names that fail that test. A `kb__` name therefore counts
  as a built-in, so **any agent whose built-in list was narrowed in Studio
  would silently lose every knowledge-base tool** — no error, no UI signal.
  This flight is what makes that reachable, so the fix lands here.
- Change: a module-level `UNGATED_TOOL_PREFIXES = ("mcp__", "kb__")` and
  `is_ungated = tool_name.startswith(UNGATED_TOOL_PREFIXES)` (`str.startswith`
  accepts a tuple). `disabled_tools` stays a **universal** explicit blacklist,
  so an operator can still disable one knowledge-base tool by its prefixed
  name. Chosen over registering outside the gate (operator's call,
  2026-09-17) precisely to keep that blacklist working: skipping the call
  would require re-implementing `disabled_tools` at a second site.
- Shared-interface change on `AgentConfig`: the leg greps every caller of
  `is_tool_enabled` and every place that reasons about the `mcp__` prefix,
  and states in its design what it found. Regression tests, both named in the
  leg: an agent with `enabled_tools=[]` keeps its `kb__` tools and its
  `mcp__` tools; `disabled_tools=["kb__x__search"]` still removes exactly
  that one. The docstring's existing "`enabled_tools == []` blocks all
  built-in tools but does NOT block MCP tools" sentence widens to name both
  prefixes.

**DD-7 — `search_tools` grows a `kb:` group: one branch in the prefix parse, and no `source_index` entry**
> **Amended at Leg 2 design review (operator's call, 2026-09-17), after three
> Architect cycles.** The first draft asserted mechanisms the code does not
> have; cycle 2 rewrote it around selection-via-`source_index` and
> rendering-via-prefix-parse; cycle 3 fixed its keying and ordering. Leg 2's
> review then found the description plumbing could not reach the factory, and
> that the reachability test meant to protect the ordering **would pass with
> the index entry deleted**. That last finding is the tell: the entry was
> never load-bearing.
- **A knowledge base has exactly one tool, so source-level selection is
  degenerate.** `source_index` exists so a query naming an MCP *server* pulls
  in all of its tools en bloc — `_filter_candidates` collects
  `tool_names_prefixed` from a matching source and unions them with the
  per-tool matches. With one tool per knowledge base, that union adds nothing
  the per-tool path does not already find, because the tool's own
  `name + description` haystack carries the same text. The residual ranking
  effect is **provably zero**, not merely marginal (established at Leg 2
  review cycle 2): DD-4 commits the tool's own `description` to embedding the
  knowledge base's name and description verbatim, so the source-level
  haystack's content is a strict subset of the per-tool haystack's, and
  `_match_score` is a substring test — it can never find a token in the
  source haystack that is absent from the per-tool one. So
  `per_tool_score >= source_score` always, and the `max()` is always the
  per-tool score.
- **So knowledge bases get no `source_index` entry at all.** DD-7 reduces to
  what cycle 2 already identified as "the real (and much simpler) change": a
  `kb__` branch in `_format_result`'s prefix parse, beside the existing
  `_MCP_PREFIX` branch, rendering `kb:{slug}: …`. `_format_result` never sees
  `source_index` — it groups by parsing the tool name — so the label is
  unaffected by this amendment.
- **What this deletes, and why that is the point.** Three defects found
  across two review passes were all downstream of keeping the entry: the
  DD-5/DD-7 call-ordering contradiction (cycle 3), `SearchTools.__init__`'s
  `source_index or {}` falsy-bind trap (cycle 2), and the
  `synthetic_description`-needs-`kb.description` plumbing gap (Leg 2 review).
  None of them can occur now. The residue of the original wrong design was
  carrying the defects; removing it removes them by construction rather than
  by three more careful rules.
- **Matching therefore runs entirely through the tool's own description**,
  which names the knowledge base, carries its description when set, and
  instructs terse keyword-shaped queries (DD-4, DD-8). A test pins that a
  query matching the knowledge base's description returns its tool.
- Rejected: keeping the entry with a terse tool description (it would make
  the entry load-bearing and the test selective, but at the cost of the
  ordering constraint and its hazards, and it would withhold from the model —
  at call time — the description of what it is searching); keeping both and
  testing against a stub whose description omits the text (a test exercising
  a shape that never occurs in production).

**DD-8 — The tool's returned string: bounded, cited, and honest when degraded**
- One header line naming the knowledge base, the query and the hit count;
  then per hit, a citation line `[n] {path} #{seq} ({char_start}-{char_end})`
  followed by the chunk text. The path is the item's `path_or_url`, so the
  operator and the model see the same identifier the status and item routes
  use. **The citation resolves the chunk's own `item_id`, never a
  `parent_id`**: a registered folder and each walked file are both items, and
  the operator-meaningful path is the file's, not the folder's. (The
  behavior spec's step 5 asserts the child file's path, so this is a pinned
  contract, not a preference.)
- No hits → one sentence naming the knowledge base and the query, never an
  empty string.
- Degraded (DD-1) → one line above the hits carrying `SearchResult.degraded`
  verbatim. **Four causes, and the accompanying sentence depends on which
  side degraded** (Architect cycle 3): `semantic index rebuilding`,
  `semantic index busy` and `semantic index unavailable` are all keyword-only
  results; `keyword index unavailable` is the reverse — those are *semantic*
  results, and saying "these are keyword results" there would be exactly
  backwards.
- The tool `description` instructs **terse, keyword-shaped queries** rather
  than sentences — not a style preference but a consequence of FTS5's
  implicit AND (DD-3): a sentence-shaped query drops the keyword side to zero
  hits, which is exactly the half the mission's exact-term criterion rests
  on.
- No per-hit text cap and no total cap in the tool: chunk text is bounded by
  the chunking settings (1,000 characters by default) and `limit` is bounded
  at 20, so the worst case is ~20 KB, and the context-budget governor already
  bounds tool results with `truncation_direction = "head"` — which is the
  right end to keep, since hits are emitted best-first. Recorded so a later
  reader does not add a second cap that fights the governor. Note the
  governor **will** truncate on a small-context model: `_govern` bounds by a
  fraction of `max_context_tokens`, so "~20 KB" is a worst-case size, not a
  delivery guarantee.
- **Contract recorded for the behavior spec**: the tool-name shape
  `kb__{slug}__search`, the two parameter names, the `kb:` discovery group
  label, and the header/citation line shapes above. A change to any of these
  is a spec re-author, not an inline fix.

**DD-9 — Behavior test `kb-agent-query-round-trip`: mock provider with scripted tool calls, shell-only apparatus**
- Operator's call, 2026-09-17: the deterministic, offline apparatus over a
  live tool-capable model. It proves registration, dispatch, real fused
  results over a real indexed folder, the discovery group, the isolation
  case and the DD-6 whitelist regression; it does not prove that an
  unprompted model *chooses* the tool, which is recorded as out of scope.
- **Act path**: `curl` with the long-lived credential against the knowledge-base,
  agent, provider and chat-session routes, plus a small Python WebSocket
  driver against `/ws` (the `websockets` package is already a runtime
  dependency, so the apparatus adds nothing to the closure). The mock
  provider is admitted only under `THE_ONE_DEV_MODE=true` and its
  `config["response"]["tool_calls"]` is what makes the agent emit a call to a
  named tool — the same seam the browser tests already drive.
- **Read path**: `GET /api/chat/sessions/{session_id}` returns the persisted
  `messages` list, which carries the assistant's tool call and the tool
  result content — so every assertion reads a field of an existing response
  body, with no test-only seam and no database read.
- **The `/ws` premise is resolved, not carried** (Architect cycle 1, verified
  independently at planning). `CredentialGateMiddleware._handle_websocket`
  resolves the cookie first and then **falls back to `_resolve_header`**, so
  `Authorization: Bearer <long-lived credential>` authorizes the upgrade.
  `OriginAllowlistMiddleware` rejects a WS upgrade only when an `Origin`
  header is present and disallowed, and a Python `websockets` client sends
  none. **A shell-only Executor with the bearer credential drives `/ws`
  directly — no handoff, no cookie.** Leg 3's premise audit is therefore a
  re-verify against current code, not an open question, and the Divert
  criterion that contemplated a browser apparatus is struck.
- **The `/ws` protocol is pinned here** so two Executors do not write two
  drivers with two different completion conditions:
  `{"action":"join","session_id":…}` → `{"type":"session_joined",…}`;
  `{"action":"message","message":"…"}` — the key is **`message`**, not
  `content`; the turn ends on `{"type":"done"}`.
- **Both agents are created with `max_iterations: 1`.** `MockProvider.complete`
  returns the same scripted `response` on every call, so at the default
  `max_iterations=20` each turn would dispatch the knowledge-base tool twenty
  times before the budget ran out. The project already knows this — see
  `tests/browser/test_flow_chat_thinking_disclosure.py`'s note that the mock
  agent is seeded with `max_iterations=1` "so the static mock … does not
  loop". Verified at planning that this still exercises the observable: the
  loop consumes its budget at the *top* of the iteration body, so the single
  iteration completes the LLM call, dispatches the tool, and persists the
  result before the loop exits. The cost is that the test never exercises a
  second model turn after the tool result — accepted (Flight Director's call
  on the Architect's question 4), because every assertion reads the persisted
  transcript directly rather than a model's summary of it, and "the model
  writes a good answer from the hits" is already out of scope for a mock
  provider.
- Spec drafted at planning (`tests/behavior/kb-agent-query-round-trip.md`,
  status `draft`).

**DD-10 — Squawk 0050's window between this flight and Flight 6 is accepted**
- `studio.js` rebuilds `kb_ids` from `.chip-area[data-type="kb"] .chip`,
  which nothing renders, and `update_agent` has no server-side preservation
  for `kb_ids`, so every Studio agent save writes an empty list. This flight
  makes `kb_ids` functional, which turns a latent bug into real (silent)
  loss of an attachment for an operator who attaches through the API and
  then saves the agent in Studio for an unrelated reason.
- **Operator's call, 2026-09-17: accepted.** Squawk 0050 stays open and is
  fixed by Flight 6, which builds the Knowledge tab that populates those
  chips. This flight therefore does **not** touch `studio.js` or
  `update_agent`. Recorded here so the decision is visible to whoever hits it
  in between, and carried into the Flight 6 planning inputs.

**DD-11 — No schema change, no closure change; one frozen run at flight close as a diagnostic**
- Nothing here adds a table, a column or a migration: `agents.kb_ids` exists
  since before this mission and is already persisted and round-tripped by
  `AgentConfigRepository`. No dependency is added — `websockets` (the
  behavior-test driver) and everything the retrieval path touches are already
  in the closure — so `pip-audit` runs against an unchanged export, and the
  frozen Windows run is a diagnostic proving the nine existing gates still
  pass and the installer size has not moved. An iteration is budgeted if it
  fails inside this flight's files; a failure outside them is raised to the
  operator (the Flight 2/3/4 rule).
- **One scope widening, accepted deliberately** (operator's call,
  2026-09-17): DD-1's bounded lock acquisition edits three
  files in `the_one/vectors/` — `usearch_store.py` (the keyword-only
  `timeout` on `query`), `_store.py` (`VectorStoreBusyError` beside its
  siblings, plus the `VectorStore` Protocol signature and contract) and
  `__init__.py` (the re-export) — which this decision would otherwise leave
  untouched. It adds no dependency and no schema change, so the claims above
  hold; it is called out here so a reader does not treat the vectors package
  as out of bounds for Leg 1.

**DD-12 — No per-item diversity in the fused result; accepted and recorded**
- With a 150-character chunk overlap by default, the top `limit` hits can all
  be adjacent windows of one file — the model gets one passage rendered five
  times rather than five passages. Raised by the Architect at cycle 1 as
  worth a decision rather than necessarily a change.
- **Accepted for this flight, not fixed.** A one-hit-per-item rule with a
  fallback is a fusion-design change on top of the one this flight is already
  proving out, and it trades recall for spread in a way this flight has no
  benchmark to evaluate — the same reason DD-3 declines to make `RRF_K` a
  dial. Adjacent windows of the genuinely most relevant file is also a
  defensible answer to a query, not obviously a defect.
- Recorded for Flight 6 / mission close alongside the recall benchmark, so
  the two are evaluated together against real corpora rather than guessed at
  separately.

### Prerequisites

- [x] Flight 4 `completed` and merged to `mission/24-knowledge-bases` (PR #202, `152058b`); squawks 0067–0070 merged (PR #203, `9fef908`); working tree clean at planning
- [x] Flight 3's storage and indexing surface present and green: `KBChunkRepository.search_keyword` with its `MAX_SEARCH_K` bound and `get_many`'s order-preserving, missing-id-tolerant read; `UsearchStore.query` with its dimension guard; the `kb_chunks_fts` index
- [x] `AgentConfig.kb_ids` persisted and round-tripped (`db/repositories.py`, `db/schema.py`), with **no tool-building reader** today — verified at planning. (It is not unread: `self_configuration/projection.py` resolves knowledge-base names for `get_my_configuration`. Nothing builds a tool from it, which is what this flight changes.)
- [x] The embedding backend answers a single-text query in well under a millisecond and is safe to encode concurrently (planning probes P1–P3)
- [x] The mock provider emits scripted `tool_calls` (`the_one/llm/mock.py`) and is admitted under `THE_ONE_DEV_MODE=true`
- [x] `GET /api/chat/sessions/{id}` returns the persisted `messages` list; the WebSocket lives at `/ws`
- [x] Port 8485 free, nothing on 8484, no stale `fly execute` client; `pip-audit` 2.10.0; `uv` 0.10.0; `/tmp` native ext4
- [x] **Re-verified on the day of Leg 3** (2026-09-17): `fly -t the-one status` logged in, `windows-worker` `running`. Squawk 0068's rule earned its keep — the operator had to log in fresh before the leg. Noted at the same check: both Linux workers (`de5299cf212d`, `worker2`) are `stalled`; the Windows installer task runs on `windows-worker` so this flight was unaffected, but anything needing a Linux worker would fail

### Pre-Flight Checklist
- [x] All open questions resolved
- [x] Design decisions documented
- [x] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

Three legs. **Leg 1** is the engine with no agent in sight:
`the_one/knowledge/retrieval.py` — `SearchHit`, `search`, reciprocal rank
fusion, the concurrent semantic and keyword calls, the two crash-window
tolerances, the stale degrade, and the no-lock rule with its measurement
(DD-1, DD-2, DD-3). It is unit-testable against the existing `isolated_db`
and stub-backend fixtures, including the exact-term guarantee. **Leg 1 also
carries the `is_tool_enabled` prefix generalization (DD-6)**, moved out of
Leg 2 at Architect cycle 1: it has no dependency on the knowledge-base tool
existing — `cfg.is_tool_enabled("kb__x__search")` is unit-testable today
against `tests/test_config.py` — so landing the flight's only
shared-interface change separately de-risks it from the wiring, and leaves
Leg 2 carrying only the factory-level regression. **Leg 2**
makes retrieval reachable: `KBSearchTool`, `KBToolProvider`, the
`AgentFactory` wiring, the `kb:` discovery group, and the documentation
(DD-4, DD-5, DD-7, DD-8). **Leg 3** verifies against the real environment:
premise audit and run of `kb-agent-query-round-trip`, `make lint`,
`make test-unit` verbatim, the release-closure `pip-audit`, one frozen
Windows run, and the mission artifact updates. Legs 1 and 2 tier high — a
new fusion path whose correctness the mission criterion rests on, and a
shared-interface change to `AgentConfig` plus factory wiring — and get a
per-leg design review; the flight-end Reviewer covers all code.

### Checkpoints
- [x] Leg 1 landed: fusion returns a keyword-only hit the semantic side ranks outside its window; **at `candidate_k=25`, `limit=5`, with five both-list chunks ahead of it, the exact-term hit is still within the returned five** (DD-3 test 4 — the reserved slot's reason for existing); at `limit=1` a tied keyword hit wins; a query queued behind a held per-KB lock raises `VectorStoreBusyError` from the acquisition bound without cancelling in-lock work; a stale store degrades to keyword-only with `degraded` set; an unexpected exception in the semantic slot degrades as `semantic index unavailable` rather than reaching fusion as a value; an exception in the keyword slot degrades as `keyword index unavailable` with semantic-only hits; a vector id with no chunk row shortens the list instead of raising; an empty query touches neither backend; `enabled_tools=[]` keeps a `kb__` name and `disabled_tools=["kb__x__search"]` still removes exactly that one
- [x] Leg 2 landed: an attached agent's registry contains exactly one `kb__{slug}__search` per attached knowledge base; an unattached agent's contains none; two knowledge bases with the same name both get the hash discriminator regardless of `kb_ids` order, and a pair whose names collide *and* whose ids share a prefix still produce unique names no longer than 64 characters; an over-long name truncates rather than dropping the tool; `search_tools` matching the knowledge base's description returns its tool under a `kb:` group
- [x] Leg 3: behavior test passes every checkpoint (8/8); gates recorded; frozen run `RESULT: PASS` with nine gates

### Adaptation Criteria

**Divert if**:
- ~~Reciprocal rank fusion cannot satisfy the exact-term criterion at the chosen candidate depth.~~ **Resolved at planning, not left as a Divert** (Architect cycle 2): the arithmetic showed plain RRF *does* fail this at `candidate_k = 25`, so the reserved keyword slot was adopted in DD-3 rather than waiting for the criterion to trip mid-flight. Divert instead if the reserved slot itself proves insufficient — i.e. DD-3's test 4 still fails with the slot in place, which would mean the crowding is not the mechanism.
- `is_tool_enabled`'s carve-out turns out to have consumers outside the factory that reason about the `mcp__` prefix independently, so generalizing it is no longer a two-line change.

**Acceptable variations**:
- `RRF_K` and `candidate_k`'s exact formula, provided the constants are named and the exact-term test still passes.
- The citation line's punctuation and the header's wording, provided the behavior spec's contract (DD-8) is updated in the same commit.
- The wording of the knowledge-base tool's own `description`, provided it names the knowledge base, carries its description when set, and instructs terse keyword-shaped queries — since after DD-7's amendment that field is the **only** thing `search_tools` matches a knowledge base on.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `retrieval-and-fusion` - `the_one/knowledge/retrieval.py`: `SearchResult`/`SearchHit`, `search`, RRF with its named constants, the keyword-first tie-break and the **reserved keyword slot**, concurrent semantic + keyword under `return_exceptions=True` with all four degrade causes specified, crash-window tolerance. **`the_one/vectors/`** (`usearch_store.py`, `_store.py`, `__init__.py`): the keyword-only acquisition `timeout` on `query`, `VectorStoreBusyError(VectorStoreError)`, the Protocol signature + contract, and the re-export (DD-1's corrected bound; the one scope widening, DD-11). **`is_tool_enabled`'s prefix set with its regression tests (DD-6)** against `tests/test_config.py` and `tests/test_factory_disable_enforcement.py`. Unit tests: the five exact-term/fusion cases incl. test 4's strict bar and the `limit=1` tie. **Docs, all four and none optional**: `retrieval.py`'s docstring (the no-lock rule + the discounted Linux measurement), `the_one/embeddings/_backend.py::EmbeddingBackend` (the concurrency sentence), `the_one/vectors/usearch_store.py` (the new timeout's contract), and `the_one/agents.md` (the per-KB-lock consequence beside the two crash windows — the durable record of this review's highest-value correction). No agent wiring. *(high-risk: the mission criterion's correctness rests on this)*
- [x] `kb-tools-gate-and-discovery` - `KBSearchTool` + `KBToolProvider` (DD-4, DD-5); `AgentFactory` wiring with its factory-level gate regression; the `kb:` group as one branch in `_format_result`'s prefix parse, with **no** `source_index` entry (DD-7 as amended); the result format (DD-8); `BASE_PROMPT`, `CLAUDE.md`, `the_one/agents.md`, `SECURITY-MODEL.md`. *(high-risk: factory wiring, a new per-agent tool surface)*
- [x] `verify-integration` - premise audit + `/mission-control:behavior-test kb-agent-query-round-trip` on a dev instance; `make lint`; `make test-unit`; `pip-audit`; frozen `fly execute`; mission artifact updates. *(no HAT leg — no screen; the walk folds into Flight 6's HAT)*

---

## Post-Flight

### Completion Checklist
- [x] All legs completed
- [x] Code merged (PR into `mission/24-knowledge-bases`)
- [x] Tests passing (`make lint`, `make test-unit` verbatim, `pip-audit`, frozen run — by hand, recorded in the flight log)
- [x] Documentation updated (`the_one/agent/config.py::BASE_PROMPT` — it currently tells the model its catalog covers "BOTH built-in tools … AND tools from any MCP servers" and that results group as `built-in:` / `mcp:<server>:`, which a third group makes factually wrong about the model's own catalog; `CLAUDE.md`'s Knowledge bases paragraph gains the agent-facing half; `the_one/agents.md` gains a Knowledge retrieval section, the `kb__` prefix rule beside the existing tool-registry material, and the per-KB-lock consequence beside the two crash windows; `SECURITY-MODEL.md`'s Knowledge-base indexing bullet gains the attachment-is-authorization statement)

### Verification

- `/mission-control:behavior-test kb-agent-query-round-trip` passes every checkpoint on a dedicated dev instance (8485, scratch data directory, `THE_ONE_DEV_MODE=true`): an attached agent's turn produces a tool call whose result carries text from the indexed fixture; `search_tools` surfaces the tool under a `kb:` group; an unattached agent's identical scripted call fails without leaking knowledge-base content; an agent with a narrowed built-in whitelist keeps its knowledge-base tool.
- Unit: `tests/test_kb_retrieval.py` (fusion order, the exact-term guarantee incl. test 4's strict bar at `candidate_k=25`/`limit=5`, the reserved slot's three guards, crash windows (a) and (b), **all four degrade causes** — stale, busy, an unexpected semantic exception such as a `_check_dim`-style `ValueError`, and a keyword-slot exception — plus both-slots-fail raising the semantic exception, empty query, candidate depth, deterministic ties), `tests/test_kb_tool_provider.py` (tool naming, slug collision, the 64-character truncate-and-suffix, orphan `kb_id`, empty `kb_ids`), `tests/test_config.py` (the DD-6 regressions — the existing home of `is_tool_enabled`'s tests; no new file), `tests/test_factory_disable_enforcement.py` (the existing home of enabled/disabled-composition regressions, squarely in DD-6's blast radius), `tests/test_factory.py` (registration and isolation), `tests/test_search_tools.py` (the `kb:` group, **plus a description-matching test**: a query matching the knowledge base's *description* but not the tool's name still returns the tool, through the per-tool matching path — which after DD-7's amendment is the only path there is).
- Frozen: `^RESULT: PASS`, nine doctor gates `OK`, installer size recorded against 134,938,414 bytes (Flight 4 close, build 612549) — expected unchanged, since this flight adds no dependency and no package data.
