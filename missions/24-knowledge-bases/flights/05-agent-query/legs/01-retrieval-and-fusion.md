# Leg 1: Retrieval and Fusion

**Status**: completed
**Flight**: [Agent Query](../flight.md)
**Risk tier**: high — the mission's retrieval criterion rests on this leg's
correctness, and it widens `the_one/vectors/`'s public seam.

## Objective

Build the retrieval engine with no agent in sight: a module that fuses the
vector store's semantic hits with FTS5's keyword hits by reciprocal rank,
degrades honestly on four distinct failure causes, and guarantees that a
query naming an exact term finds it. Bound the semantic side's *lock
acquisition* (never its work) by widening `UsearchStore.query`. Generalize
`AgentConfig.is_tool_enabled`'s hardcoded `mcp__` carve-out to a named prefix
set. No agent wiring, no tool, no registry — Leg 2 does that.

## Scope

**Creates**
- `the_one/knowledge/retrieval.py`
- `tests/test_kb_retrieval.py`

**Modifies**
- `the_one/vectors/_store.py` — `VectorStoreBusyError`; `timeout` on the
  `VectorStore` Protocol's `query` signature; the contract docstring
- `the_one/vectors/usearch_store.py` — keyword-only `timeout` on `query`
- `the_one/vectors/__init__.py` — re-export `VectorStoreBusyError`
- `the_one/embeddings/_backend.py` — the concurrency sentence on
  `EmbeddingBackend`
- `the_one/agent/config.py` — `UNGATED_TOOL_PREFIXES`
- `the_one/agents.md` — the per-KB-lock consequence beside the two crash
  windows
- `tests/test_config.py`, `tests/test_factory_disable_enforcement.py`,
  `tests/test_vector_store.py`

**Out of scope**: `KBSearchTool`, `KBToolProvider`, `AgentFactory`,
`_search_tools.py`, `BASE_PROMPT`, `CLAUDE.md`, `SECURITY-MODEL.md` — all Leg 2.

## Acceptance Criteria

### Retrieval module (DD-1)

- [x] **AC-1** `the_one/knowledge/retrieval.py` exposes frozen dataclasses
  `SearchHit(chunk_id, item_id, path, seq, char_start, char_end, text, score)`
  and `SearchResult(hits: list[SearchHit], degraded: str | None)`, and
  `async def search(kb_id, query, *, limit, chunk_repo, item_repo, store, backend) -> SearchResult`.
- [x] **AC-2** An empty or whitespace-only `query` returns an empty
  `SearchResult` **without touching the store, the database or the backend**.
  Verified by stubs that raise if called.
- [x] **AC-3** The two backends are called concurrently under
  `asyncio.gather(..., return_exceptions=True)`, and the semantic call passes
  `timeout=SEMANTIC_QUERY_TIMEOUT` **into** `store.query`. **`asyncio.wait_for`
  must not appear anywhere in `retrieval.py`** — the test asserts the literal
  string is absent from the whole module, not merely adjacent to the
  `store.query` call. Widened at leg design review: an overall retrieval
  deadline wrapped around the `gather` (or around `search`'s whole body)
  cancels the in-flight `store.query` just as effectively and reproduces the
  measured hazard — caller and per-KB lock released at 0.302 s, escaped
  thread still reading the index at 1.502 s — without `wait_for` ever
  appearing near `store.query`. DD-1 gives `retrieval.py` no legitimate use
  for `wait_for`, so absence from the module is the cheaper and stronger pin.
- [x] **AC-4** `candidate_k = min(max(limit * 5, 25), 100)`, named constant.
- [x] **AC-5** Crash window (a): a chunk present only in the keyword list
  (its item still `indexing`, vectors not landed) is returned, ranked by RRF,
  unmarked. Crash window (b): a vector id with no `kb_chunks` row shortens
  the result instead of raising — `get_many` drops it.
- [x] **AC-6** A chunk whose item is not `indexed` is returned **unmarked**
  (no per-hit status field on `SearchHit`).
- [x] **AC-6b** **A third crash window, found at Leg 1 design review and not
  covered by DD-1's two.** `KBItemRepository.get` raises `KeyError` when the
  row is absent, and DD-1's steps (5) `get_many` and (6) per-item path
  resolution are two separate awaits on the one process-wide connection with
  an event-loop yield between them. An item deleted in that window (its
  chunks cascade away, but this query already holds their ids) would raise an
  unhandled `KeyError` out of `search` — crashing the whole query rather than
  degrading, which is inconsistent with how windows (a) and (b) are handled
  two bullets up. **Wrap the per-item lookup in `try/except KeyError` and
  drop the affected hit**, mirroring `get_many`'s own missing-id tolerance;
  log at DEBUG. A test deletes an item between the two calls (or stubs
  `item_repo.get` to raise) and asserts the result is shorter, not an
  exception.

### Fusion and the exact-term guarantee (DD-3)

- [x] **AC-7** `score = Σ 1/(RRF_K + rank)`, 1-based ranks, `RRF_K = 60` as a
  named module constant. Sort key `(-score, in_keyword_list desc, chunk_id asc)`.
- [x] **AC-8** The reserved-slot rule is implemented exactly as DD-3's
  pseudocode. That `if` has **five clauses**, not three: `limit >= 2`, the
  keyword list non-empty, the semantic list non-empty, the keyword-only set
  non-empty, **and the trigger itself** — no keyword-only hit already present
  in the top `limit`. DD-3 calls the first four "three guards" (bundling the
  two list checks) and discusses the trigger separately; do not read that as
  the complete condition. "Keyword-only" means present in the
  keyword list and **absent** from the semantic list — a both-list hit does
  **not** count as keyword representation for this rule.
- [x] **AC-9** When the rule fires, the reserved hit takes the displaced
  hit's position (last), and a DEBUG log names both chunk ids.
- [x] **AC-10** Five fusion tests pass, per DD-3:
  1. a keyword-only rare-identifier hit ranked outside the semantic window is
     in the fused result and absent from the semantic-only result;
  2. a both-list chunk outranks a one-list chunk at equal ranks (written at
     `limit >= 2`);
  3. `limit = 1`, keyword-only rank-1 tying semantic-only rank-1 → the
     keyword hit wins (tie-break, not the reserved slot, which is guarded off
     at `limit = 1`);
  4. **the strict bar**: `candidate_k = 25`, `limit = 5`, five both-list
     chunks ahead of a keyword-only exact-term hit → **the exact-term hit is
     within the returned five**. This test fails without the reserved slot;
  5. a sentence-shaped query containing the rare identifier records FTS5's
     implicit-AND behaviour (the keyword side returns nothing).
- [x] **AC-11** A test covers the `limit >= 2` guard directly: at `limit = 1`
  with a both-list winner and a keyword-only hit available, the both-list
  winner is **not** evicted.

### Degradation (DD-1, four causes)

- [x] **AC-12** `VectorStoreStaleError` → `degraded="semantic index rebuilding"`,
  keyword hits returned.
- [x] **AC-13** `VectorStoreBusyError` → `degraded="semantic index busy"`,
  keyword hits returned.
- [x] **AC-14** Any **other** semantic-slot exception (test with a
  `_check_dim`-style `ValueError`) → `degraded="semantic index unavailable"`,
  keyword hits returned, exception type logged. It must **never** reach
  fusion as a value.
- [x] **AC-15** A keyword-slot exception → `degraded="keyword index unavailable"`,
  **semantic** hits returned.
- [x] **AC-16** Both slots failing → the **semantic** slot's exception is
  raised (deterministic, not gather-order dependent).
- [x] **AC-17** There is **no** `count_for_kb` empty-knowledge-base
  short-circuit (cycle 2 removed it; a test asserting its absence is not
  required, but reintroducing it fails review).

### The store's bounded acquisition (DD-1)

- [x] **AC-18** `UsearchStore.query` gains `*, timeout: float | None = None`
  (**keyword-only** — existing positional calls `store.query("kb", vec, 1)`
  must still work; a test pins a positional call).
- [x] **AC-19** The bound wraps **only** `entry.lock.acquire()`. The acquire
  sits **outside** the `try`; the `finally: entry.lock.release()` runs only
  on a lock actually held. Nothing in-lock is ever cancelled.
- [x] **AC-20** Expiry raises `VectorStoreBusyError`, defined in
  `the_one/vectors/_store.py` as a subclass of **`VectorStoreError`**, never
  of `VectorStoreStaleError` (`manager.py` catches that one and responds with
  `rebuild_kb` — a full re-embed; inheriting would turn a transient busy
  query into a rebuild storm). Re-exported from `the_one/vectors/__init__.py`.
- [x] **AC-21** A test proves the invariant: with the per-KB lock held by
  another task, `query(..., timeout=<short>)` raises `VectorStoreBusyError`,
  **and** the lock is still held by the original holder afterwards (nothing
  was released out from under it).
- [x] **AC-22** Every existing exit path from `query` still releases the
  lock: the early `return []` when the index is `None` or empty, a
  `VectorStoreStaleError` from `_ensure_loaded`, an exception from the search
  thread, and normal completion. `_check_dim` stays **before** the lock.
- [x] **AC-23** `timeout` is added to the `VectorStore` Protocol's `query`
  signature and to `_store.py`'s contract docstring, which also records that
  **the bound covers the waiter, never the holder** — a cold-start
  `_ensure_loaded`/`Index.restore` runs in-lock and is unbounded.
- [x] **AC-24** The busy-path WARNING carries `kb_id` and the elapsed and
  `SEMANTIC_QUERY_TIMEOUT` values.

### The tool gate (DD-6)

- [x] **AC-25** `the_one/agent/config.py` defines module-level
  `UNGATED_TOOL_PREFIXES = ("mcp__", "kb__")` and `is_tool_enabled` uses
  `tool_name.startswith(UNGATED_TOOL_PREFIXES)`. `disabled_tools` stays a
  **universal** blacklist checked after.
- [x] **AC-26** Regression tests in `tests/test_config.py`: `enabled_tools=[]`
  keeps both a `kb__` name and an `mcp__` name; `enabled_tools=["web_search"]`
  keeps a `kb__` name; `disabled_tools=["kb__x__search"]` removes exactly
  that one.
- [x] **AC-27** `tests/test_factory_disable_enforcement.py` still passes; if
  its composition assertions need a `kb__` case, add one there rather than in
  a new file.
- [x] **AC-28** The docstring's "`enabled_tools == []` blocks all built-in
  tools but does NOT block MCP tools" sentence widens to name both prefixes.

### Documentation (all four, none optional)

- [x] **AC-29** `retrieval.py`'s module docstring records the no-lock rule,
  the **discounted** Linux measurement (p50 0.08 ms; platform-independent
  because the encode path reaches no BLAS/OMP kernel and mutates no model
  state), and `SEMANTIC_QUERY_TIMEOUT`'s reasoning against the Flight 2
  Windows flush figures.
- [x] **AC-30** `the_one/embeddings/_backend.py::EmbeddingBackend`'s docstring
  states that `embed` must be safe to call concurrently from multiple threads.
- [x] **AC-31** `the_one/vectors/usearch_store.py` / `_store.py` document the
  new `timeout`'s contract (waiter-only, never the holder).
- [x] **AC-32** `the_one/agents.md` gains the per-KB-lock consequence
  **beside the two existing crash windows** (same section, same audience):
  retrieval never takes the manager's embed lock, but `store.query` takes the
  store's per-KB lock, and a query concurrent with an upsert/flush/rebuild
  waits on it — bounded by the acquisition timeout. This is the durable
  record of this flight's highest-value review correction and is **not**
  optional.

## Verification

```bash
# Scoped iterations
PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_kb_retrieval.py -x --timeout 60
PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_config.py tests/test_factory_disable_enforcement.py tests/test_vector_store.py -x --timeout 60

# Leg-end
make test-unit
make lint
```

- AC-3's no-`wait_for` assertion: grep the module source for `wait_for` in
  the same statement as `store.query`.
- AC-21/AC-22 need a real `UsearchStore` against a tmp path, not a stub —
  the invariant is about the actual lock object. The access pattern, since
  there is no public seam for it: `await store._entry(kb_id).lock.acquire()`
  in one task, call `store.query(..., timeout=<short>)` from another, assert
  `VectorStoreBusyError`, then assert `entry.lock.locked()` is still `True`
  and that the original holder can still release cleanly. This is the one
  place the leg leans on a private attribute; it is deliberate, because the
  invariant under test is precisely that private lock's state.
- Pair every pytest run with `-x --timeout`; never `-m live`; the canonical
  gate is `make test-unit` verbatim, alone, foreground.

## Citation Audit

Verified against the working tree at `9fef908` + this flight's planning edits:

| Citation | Status |
|---|---|
| `usearch_store.py::query` — `async with entry.lock:` wrapping `_ensure_loaded` + `to_thread(entry.index.search, ...)`; `_check_dim` before the lock | verified |
| `_store.py` — `VectorStoreError`, `VectorStoreStaleError`, the `VectorStore` Protocol's `query` signature, the write-lock and no-call-back contract bullets | verified |
| `repositories.py::search_keyword` — bm25 lower-is-better, `ORDER BY score` ascending, whitespace split + per-term quoting (FTS5 implicit AND), empty-query short-circuit, `k` bounded by `MAX_SEARCH_K = 1000` | verified |
| `repositories.py::get_many` — preserves caller order, drops missing ids | verified |
| `agent/config.py::is_tool_enabled` — `is_mcp = tool_name.startswith("mcp__")`; whitelist applied only to non-MCP names; `disabled_tools` checked after | verified |
| `embeddings/_backend.py::EmbeddingBackend` — structural Protocol, `embed` synchronous and CPU-bound | verified |
| `manager.py` — catches `VectorStoreStaleError` and responds with `rebuild_kb` (why `VectorStoreBusyError` must not inherit from it) | verified at Architect cycle 3 |
| `store.query` has no production caller in `the_one/` today (only tests and `scripts/bench_vector_store.py`) | verified at Architect cycle 3 |

## Post-Completion Checklist

- [x] All acceptance criteria checked off
- [x] Leg status → `landed` (implementation complete; flight-end review still owes `completed`)
- [x] Leg checked off in `flight.md`
- [x] Flight log updated with outcomes, deviations and anomalies
