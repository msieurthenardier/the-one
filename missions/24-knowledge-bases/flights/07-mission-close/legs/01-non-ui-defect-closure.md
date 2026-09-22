# Leg: non-ui-defect-closure

**Status**: completed
**Flight**: [Mission Close](../flight.md)

## Objective

Close the two server-side correctness holes the Flight 6 debrief recorded — the
vector store's missing shutdown flush and the stale `kb__` disable that survives
detach → rename → reattach — neither of which any operator surface can reveal.

## Context

These two defects are unrelated in subject and share one property that is the
reason they are in the same leg: **no product surface can observe either of
them.** No UI or route reports whether a vector write was flushed at shutdown,
and none renders a `kb__` toggle. Each is therefore pinned by a unit test or it
is not pinned at all, and a Reviewer reading this diff must judge it on test
evidence rather than on a demonstrable behaviour change.

Relevant flight decisions: **DD-3** (hook shape and placement), **DD-3a** (the
cancel-fallback torn-save hazard), **DD-13** (the reconcile's rule and seam).
All three were materially corrected by Architect cycle 1 — read them in the
flight artifact before starting; the decisions as *first drafted* were wrong in
ways this leg would otherwise inherit.

No prior legs. This is the flight's first leg and depends on nothing.

## Inputs

- `the_one/vectors/__init__.py` — `get_vector_store()` and the module-global
  `_store`; no non-building accessor exists
- `the_one/vectors/usearch_store.py` — `flush(kb_id)`, `close()`
- `the_one/knowledge/manager.py` — `IndexingManager.stop()` / `drain()`.
  **`stop()` is NOT shutdown-only**: it is also called at runtime from
  `api.py:1593` (`delete_knowledge_base`) and `api.py:1786`
  (`delete_kb_item` for a folder, which then **re-kicks the worker** at
  `api.py:1798-1799` via `manager.request_index(kb_id)`). All three paths share
  the process-wide singleton (`manager.py:545,554`). This is what makes AC-4a
  load-bearing.
- `tests/test_mcp_pool.py:616 — test_lifespan_shutdown_drain_order` — the
  existing drain-order spy that AC-7 extends
- `tests/test_factory_disable_enforcement.py` — `InMemoryStore` and the
  `AgentFactory` composition idiom. **Its `StubProviderWithKbTool` returns a
  FIXED tool name** and therefore cannot satisfy AC-16 on its own
- `tests/test_kb_tool_provider.py` — the
  `monkeypatch.setattr("the_one.db.connection.get_connection", ...)` seam
- `tests/test_kb_rename.py` — connection / agent-store fixtures
- `the_one/interfaces/web/app.py` — the lifespan shutdown block
- `the_one/agent/factory.py` — the `kb_tools` registration loop
- `the_one/knowledge/tool_provider.py` — `_HASH_LENGTHS`, `_discriminator`,
  `_NAME_PREFIX`, `_NAME_SUFFIX`
- Working tree: `flight/07-mission-close` at `595263c`, clean

## Outputs

- `close_vector_store()` in `the_one/vectors/__init__.py`, exported
- A cancel-fallback report on `IndexingManager`
- The hook wired into the lifespan between two named bounds
- A stale-name reconcile at the `kb_tools` registration loop
- Unit tests for every criterion below
- Flight log updated

## Acceptance Criteria

**Shutdown hook (DD-3, DD-3a)**

- [x] AC-1 — `close_vector_store()` exists in `the_one/vectors/__init__.py`,
      is listed in `__all__`, and is `async`.
- [x] AC-2 — When no store has been built (`_store is None`), it returns
      without building one. **It never calls `get_vector_store()`.**
- [x] AC-3 — When a store exists, it closes it and clears the module cache, so
      a subsequent `get_vector_store()` builds afresh.
- [x] AC-4 — `IndexingManager` exposes, per `kb_id`, whether that knowledge
      base's **most recent** `stop()` took the cancel fallback (the
      `cancelled = True` branch at `manager.py:240-243`).
- [x] AC-4a — **The report is overwritten on every `stop()` call, never
      accumulated.** A clean stop for a `kb_id` must clear any prior cancelled
      verdict for that same `kb_id`. See Edge Cases — an append-only report is
      a silent data-loss bug, not a lesser version of this criterion.
- [x] AC-4b — A test proves the overwrite: force a cancel for a `kb_id`, then
      complete a clean `stop()` for the same `kb_id`, and assert it is no
      longer reported as cancelled. The write site must be symmetric — a second
      *cancel* for the same `kb_id` re-asserts cancelled just as a clean stop
      clears it. The report answers "how did the most recent stop end", with no
      special-casing of either direction.
- [x] AC-4c — **The report survives `drain()`.** `drain()` ends with
      `self._entries.clear()` (`manager.py:261`), so a flag stored on
      `_WorkerEntry` is wiped by the very call that precedes every production
      read of it. The report must live in a manager-level structure independent
      of `_entries`. A test must drive the **real** `IndexingManager.drain()`
      — with at least one `kb_id` forced down the cancel path first — and
      assert the report is still readable after `drain()` returns.
      *Without this criterion, storing the flag on `_WorkerEntry` (which
      already holds `state`, `stop_requested`, `awaiting_flush`) passes every
      other criterion in this leg and every existing test, while reporting an
      empty skip set at real shutdown — reintroducing DD-3a's hazard on the one
      path that matters.*
      *Falsification observed*: temporarily added `self._cancel_report.clear()`
      to `drain()` (simulating the entry-scoped-field bug) —
      `test_cancel_report_survives_the_real_drain` failed (`cancelled_kb_ids()`
      came back empty instead of `{"kb1"}`). Reverted; see flight log.
- [x] AC-5 — `close_vector_store()` **skips** those knowledge bases and logs
      each one at WARNING, naming the `kb_id` and saying the write was not
      flushed because a cancelled mutation may still be running.
- [x] AC-6 — The lifespan calls it **after** the indexing-manager drain block
      and **before** `await close_connection()` (`app.py:537`), wrapped in
      `try/except` with `logger.exception` on failure, matching every sibling
      drain in that block.
- [x] AC-6a — **The cancel-fallback report is captured into a local variable
      INSIDE the `if _indexing_manager is not None:` block, before
      `app.py:426-427` null it out.** Those two lines clear both the module
      singleton (`_set_module_indexing_manager(None)`) and the local
      (`_indexing_manager = None`), so any read taken "after the block" gets
      `None`. The captured local is then threaded into the
      `close_vector_store()` call.
- [x] AC-6b — The hook is called **unconditionally**, outside that `if`
      block — not moved inside it. A store can exist and be dirty with no
      indexing manager at all: `api.py:1793` reaches `_vector_store()` on the
      item-delete path. Gating the hook on `_indexing_manager is not None`
      would skip exactly the case it exists for. When there is no manager, the
      skip set is empty.
- [x] AC-7 — The drain-order spy test
      (`tests/test_mcp_pool.py::test_lifespan_shutdown_drain_order`, confirmed
      to exist at `:616`) gains an assertion for the hook's position between
      those two bounds.
- [x] AC-7a — **A test exercises the real `app.py` wiring, not just the
      ordering.** AC-7's spy asserts call order with `close_vector_store`
      replaced by a bare spy, and AC-8/9/10 test the hook in isolation with a
      hand-built skip set — so *neither* proves the report actually reaches the
      hook through `app.py`'s own code path. This criterion closes that gap:
      drive the real shutdown path with a manager whose drain records a cancel,
      and assert the hook received that `kb_id` in its skip set. Without this,
      an implementation that captures the wrong variable (or reads it after the
      null-out and always passes an empty set) passes every other criterion in
      this leg while DD-3a never fires in production.
      *Falsification observed*: temporarily moved the capture to after the
      null-out — `test_lifespan_shutdown_threads_real_cancel_report_into_vector_hook`
      failed (`close_vector_store` received `frozenset()` instead of the
      recorded kb_id). Reverted; see flight log.
- [x] AC-8 — A test proves a **dirty store belonging to a knowledge base with
      no worker** is flushed by the hook. This is the case no existing drain
      covers and the reason the hook exists.
- [x] AC-9 — A test proves a knowledge base whose worker took the cancel
      fallback is **not** flushed by the hook.
- [x] AC-10 — A test proves calling the hook twice is safe.

**Stale-name reconcile (DD-13)**

- [x] AC-11 — At the `kb_tools` registration loop (`factory.py:420-424`), a
      `kb__…__search` entry in `config.disabled_tools` whose **discriminator**
      derives from this tool's `kb_id` disables the tool **even when the entry's
      slug does not match the tool's current name**.
- [x] AC-12 — The match is attempted for **every** `L in _HASH_LENGTHS`
      (`(8, 12, 16)`), not a fixed width.
- [x] AC-13 — The match never splits on slug position: a knowledge base whose
      name normalizes to a slug containing `_` and `__` still reconciles
      correctly.
- [x] AC-14 — An entry carrying a discriminator for a **different** `kb_id`
      does not disable this tool.
- [x] AC-15 — Nothing is written to any agent row. `config.disabled_tools` is
      not mutated in place.
- [x] AC-16 — A test reproduces the full **detach → rename → reattach**
      sequence and asserts the disable survives it. This test must **fail
      without the reconcile** — state in the flight log that this was observed,
      not assumed. **The knowledge base's `name` must actually differ between
      the two `AgentFactory.create()` calls**; a fixed-name stub provider
      cannot falsify anything here. See Implementation Guidance step 9 for the
      seam.
      *Falsification observed*: temporarily reverted the loop to plain
      `config.is_tool_enabled(tool.name)` —
      `test_disabled_kb_tool_survives_detach_rename_reattach` failed (the
      renamed tool leaked into the rebuilt agent's registry). Reverted;
      see flight log.
- [x] AC-17 — `knowledge/kb_rename.py` is unchanged. Its exact-full-name
      rewrite remains the write-side converger; this leg adds the read-side
      backstop only.

**Gates**

- [x] AC-18 — `make test-unit` green; `ruff check` and `ruff format --check`
      clean.
- [x] AC-19 — Flight log updated with the leg entry, including the AC-16
      falsification observation and the Reviewer-relevant note that neither
      defect is observable through any product surface.

## Verification Steps

- AC-1/2/3, AC-8/9/10 — new tests in `tests/test_vector_store_shutdown.py` (or
  the nearest existing vectors test module). Run:
  `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_vector_store_shutdown.py -x --timeout 30`
- AC-2 specifically — assert via a spy/monkeypatch on `_build_store` that it is
  **never called** by the hook when `_store is None`.
- AC-4/4a/4b/4c/5 — `tests/test_kb_manager.py`, where the cancel-fallback and
  drain fixtures already live (`TestCooperativeStopAndCancelFallback`'s
  `stop_timeout=0.2` + `_BlockingBackend` idiom; `TestDrain`). Assert the
  report after a forced `stop_timeout` expiry; run a clean `stop()` for the
  same `kb_id` and assert the verdict is gone (AC-4b); and drive the **real**
  `drain()` and assert the report is still readable afterwards (AC-4c) — note
  `TestDrain::test_drain_stops_workers_concurrently` already asserts
  `manager._entries == {}` after `drain()`, which is the property AC-4c exists
  to survive. Assert the hook's skip via `caplog`.
- AC-6/6a/6b/7/7a — `tests/test_mcp_pool.py`. AC-7a is the one that matters:
  it must fail if the implementation reads the report after `app.py:426-427`
  rather than before. Write it so that reading the nulled reference produces an
  empty skip set and the assertion fails — do not settle for a test that passes
  either way.
- AC-11–AC-16 — tests in the existing agent-factory / KB-naming test module.
  AC-16 is the load-bearing one: build an agent with a disabled `kb__` tool,
  detach the knowledge base, rename it, reattach it, rebuild the agent, and
  assert the tool is still absent from the registry.
- AC-18 — `make test-unit` verbatim, alone, foreground.

## Implementation Guidance

1. **Read flight DD-3, DD-3a and DD-13 in full first.** Each was corrected at
   Architect review; the corrected text names the exact mechanism. In
   particular: `close()` already iterates `self._kbs` with a per-KB
   `try/except`, so do not re-implement that discipline.

2. **Surface the cancel fallback before writing the hook.** `stop()` already
   computes `cancelled`; record it in a **manager-level structure — NOT a
   `_WorkerEntry` field**. `_WorkerEntry` is the natural-looking home (it
   already holds `state`, `stop_requested`, `awaiting_flush`) and it is the
   wrong one: `drain()` clears `_entries` at `manager.py:261` immediately
   after gathering every `stop()`, so a flag stored there is gone before
   anything can read it (AC-4c). Do not change `stop()`'s or `drain()`'s
   signature or return type if a recorded attribute suffices — a lifecycle
   interface change is this leg's divert trigger (see the flight's Adaptation
   Criteria).

3. **The hook reads that report and skips.** The torn-save hazard is real and
   documented in the code itself at `manager.py:242-243`: cancelling a task
   mid-`to_thread` releases `entry.lock` while the worker thread keeps mutating
   the index, so saving right after would tear. Losing that write is the
   correct trade and must be logged, not silent.

4. **Place the call between the two bounds.** After the indexing-manager drain
   because that drain flushes workers' own knowledge bases; before
   `close_connection()` because `flush()` writes through `self.conn` via
   `_upsert_registry_row()`. Follow the comment style of the MCP-pool block at
   `app.py:451-454`, which states both of its bounds and why.

5. **For the reconcile, use what the loop already has.** `KBSearchTool` carries
   both `name` and `kb_id` (`tool_provider.py:252-259`), so the loop at
   `factory.py:420-424` already holds everything needed — no change to
   `KBToolProvider.get_tools_for_agent` and no new query.

6. **The matching rule** (DD-13): for each `L in _HASH_LENGTHS`, compute
   `_discriminator(tool.kb_id, L)`, then treat an entry as this tool's stale
   disable when it starts with `_NAME_PREFIX`, ends with `_NAME_SUFFIX`, and
   the portion before the suffix ends with `"_" + disc`. Never parse the slug.

7. **For `kb__` names, `is_tool_enabled(name)` reduces to
   `name not in disabled_tools`** — `kb__` is in `UNGATED_TOOL_PREFIXES`
   (`agent/config.py:15`), so the `enabled_tools` branch is skipped entirely
   (`config.py:182-188`). Replacing that call with a reconciled membership test
   **at this loop only** is therefore exactly equivalent plus the reconcile.
   Do not change `is_tool_enabled` itself — it is a shared interface with
   consumers outside this leg.

8. **Do not mutate `config.disabled_tools`.** The config object is not owned by
   this loop. Compute a local reconciled view.

9. **For AC-16, do not reach for the stub provider sitting next door.**
   `tests/test_factory_disable_enforcement.py::StubProviderWithKbTool` returns
   a fixed tool name — its own docstring says it "stands in" for the real
   provider — so a test built on it can never reproduce a rename and can never
   falsify the reconcile. The workable path combines three existing seams:
   monkeypatch the **global** `the_one.db.connection.get_connection` (the idiom
   in `tests/test_kb_tool_provider.py`; `KBToolProvider.get_tools_for_agent`
   calls it directly rather than taking an injected connection), back it with a
   repository whose `.get()` returns a knowledge base whose `.name` **differs
   between the two `AgentFactory.create()` calls**, and use `InMemoryStore`
   from `test_factory_disable_enforcement.py` for the agent config.
   `kb_rename.py` never needs to run: AC-16's case is precisely the one where
   the knowledge base was *detached* at rename time, so the write-side rewrite
   would not have fired anyway.

10. **The manager's cancel branch is tagged `DD-7` in its own comment**
    (`manager.py:242-244`), which refers to Flight 3's DD-7, not this flight's
    DD-3a or its DD-7 (skip counters). Do not grep for `DD-3a` in that file and
    conclude the branch is missing.

## Edge Cases

- **`_store` built but empty** — `IndexingManager.start_all()` calls the store
  factory on first launch even with zero knowledge bases, so a store with an
  empty `_kbs` is normal. The hook must handle it as a no-op close, not an
  error. *(This is why the flight's Checkpoint 1 asserts "the hook never builds
  a store" rather than "a fresh install builds none" — the latter is
  unreachable.)*
- **Flush fails inside `close()`** — already handled per-KB upstream; the hook
  must not convert a logged per-KB failure into a shutdown abort.
- **Second `close()` after a failed flush** — `flush()` early-returns on
  `not entry.dirty` (`usearch_store.py:424-426`), so a retry only happens when
  the first attempt failed, which is intended. AC-10 asserts safety, not
  no-op-ness.
- **An agent with `kb_ids` referencing a deleted knowledge base** — already
  warned and skipped (`tool_provider.py:242-248`); the reconcile never sees it.
- **Two attached knowledge bases whose slugs collide** — the widening loop
  gives them different discriminator widths. AC-12 exists for exactly this.
- **An entry that is a legitimate current-name disable** — must still disable.
  The reconcile widens the match; it must never narrow it.
- **A knowledge base that was cancel-stopped earlier and then indexed
  normally for hours** — this is the AC-4a case and the leg's sharpest hazard.
  A folder delete calls `stop()` and then immediately `request_index()`
  (`api.py:1786`, `:1798-1799`), so a `kb_id` can take the cancel fallback at
  10:00, re-index cleanly all day, and shut down at 18:00 with a genuinely
  dirty, genuinely safe-to-flush index. An **append-only** cancel report would
  skip it and lose that write — silently, and on a path that fires far more
  often than shutdown. DD-3a's protection would then cause more data loss than
  it prevents. The report must answer "did the *most recent* stop cancel?",
  never "has this kb_id *ever* cancelled?"
- **No indexing manager at all** — the hook still runs (AC-6b) with an empty
  skip set.

## Files Affected

- `the_one/vectors/__init__.py` — add `close_vector_store()`, extend `__all__`.
  Its cache-clear is the same two lines as `_reset_for_test()`; share one
  private helper rather than letting the two drift
- `the_one/knowledge/manager.py` — record cancel-fallback `kb_id`s
- `the_one/interfaces/web/app.py` — call the hook between the two bounds
- `the_one/agent/factory.py` — reconciled disable check at the `kb_tools` loop
- `tests/test_mcp_pool.py` — extend `test_lifespan_shutdown_drain_order`
  (AC-7) and add the real-wiring test (AC-7a)
- `tests/` — new and extended unit tests per the remaining criteria
- `missions/24-knowledge-bases/flights/07-mission-close/flight-log.md`

## Citation Audit

Verified against the working tree at **`595263c`** (2026-09-19). Design-review
cycle 1 added five rows and found no stale citation among the original twelve —
the gaps were things the first draft had not cited **at all**, which is the
failure mode a citation audit does not catch by construction.

| Citation | Status |
|---|---|
| `the_one/vectors/__init__.py:70 — get_vector_store()` builds + opens + caches `_store`; `__all__` at `:43-50` omits any close function | verified |
| `the_one/vectors/usearch_store.py:486 — close()` iterates `self._kbs`, per-KB `try/except` | verified |
| `the_one/vectors/usearch_store.py:424-426 — flush()` early-returns on `entry is None or not entry.dirty` | verified |
| `the_one/knowledge/manager.py:240-243` — the `cancelled` branch, with the comment naming the still-running-mutation hazard | verified |
| `the_one/vectors/usearch_store.py:275-296 — upsert()` holds `entry.lock` across `await asyncio.to_thread(...)` | verified |
| `the_one/interfaces/web/app.py:421-427` — `_indexing_manager.drain()` block; `:537 — await close_connection()`; `:451-454` — the two-bound comment style to mirror | verified |
| `the_one/agent/factory.py:420-424` — `for tool in kb_tools: if tool.name not in disabled_names and config.is_tool_enabled(tool.name)` | verified |
| `the_one/knowledge/tool_provider.py:252-259` — `KBSearchTool(name=names[kb.id], kb_id=kb.id, ...)`, so the loop has both | verified |
| `the_one/knowledge/tool_provider.py:72 — _HASH_LENGTHS = (8, 12, 16)`; `:91 — _discriminator(kb_id, hash_len)`; `:63-64 — _NAME_PREFIX/_NAME_SUFFIX` | verified |
| `the_one/agent/config.py:15 — UNGATED_TOOL_PREFIXES = ("mcp__", "kb__")`; `:182-190 — is_tool_enabled` skips the `enabled_tools` branch for ungated names and then checks `tool_name in self.disabled_tools` | verified |
| `the_one/knowledge/manager.py:268-284 — start_all()` calls `self._store_factory()` when the vector-store key is absent (so a store exists on a fresh install with zero KBs) | verified |
| `the_one/knowledge/manager.py:256-261 — drain()` gathers every `stop()` then `self._entries.clear()`; `_WorkerEntry` (`:109-123`) holds `state`/`stop_requested`/`awaiting_flush`, making it the tempting and wrong home for the report (AC-4c) | verified — **added at design review cycle 2** |
| `the_one/knowledge/kb_rename.py::rename_kb_tool_references` — exact full-name replacement, never parses a discriminator | verified |
| `the_one/interfaces/web/app.py:426-427` — `_set_module_indexing_manager(None)` then `_indexing_manager = None`, both inside the `if` block (AC-6a) | verified — **added at design review**; the first draft's AC-6 cited `:421-427` as the "after" bound without noticing the null-out on its own last line |
| `the_one/interfaces/web/api.py:1593` and `:1786` — runtime `manager.stop(kb_id)` calls; `:1798-1799` re-kicks with `manager.request_index(kb_id)` (AC-4a) | verified — **added at design review** |
| `tests/test_mcp_pool.py:616 — test_lifespan_shutdown_drain_order` — the drain-order spy AC-7 extends; asserts an exact `drain_steps` list with every subsystem replaced by a call-order spy | verified — the first draft asserted this test existed on the strength of a code comment; it does |
| `tests/test_factory_disable_enforcement.py::StubProviderWithKbTool` — returns a FIXED tool name, so it cannot falsify AC-16 | verified — **added at design review** |

---

## Post-Completion Checklist

- [x] All acceptance criteria verified — AC-1 through AC-19, including
      AC-4a/4b/4c, AC-6a/6b, AC-7a
- [x] Tests passing — `make test-unit`: 4790 passed, 10 skipped, 594
      deselected, 0 failed (a single flaky failure on the first run,
      unrelated to this leg, did not reproduce in isolation or on rerun —
      see flight log)
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed` (the Flight Director sets `completed`
      at the flight-end review, per this flight's deferred-commit workflow)
- [x] Do **NOT** commit — the Flight Director commits after the flight-end
      review
- [x] Signal `[HANDOFF:review-needed]`
