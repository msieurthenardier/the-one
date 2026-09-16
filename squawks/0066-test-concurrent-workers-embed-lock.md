# Squawk 0066: no test drives two live `IndexingManager` workers through the shared `embed_lock`

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-16
**Completed**: 2026-09-16

## Report

`IndexingManager` serialises the embed + upsert pair across knowledge
bases with one manager-wide `asyncio.Lock` (`_embed_lock`, passed as
`IndexContext.embed_lock`). `tests/test_kb_manager.py` covers the pass,
reconcile, flush, stale recovery, cooperative stop and drain, but the
drain-concurrency test uses hand-built entries — no test runs two real
workers on two knowledge bases indexing at the same time and observes the
lock interleaving their batches (and that neither KB's items are lost or
double-processed). The debrief Developer named it as the one untested
concurrency path. Straightforward: two KBs with folders, a slow stub
backend that records which KB's batch holds the lock, `wait_until_idle`
on both, assert both fully `indexed` and that no two batches overlapped.

## Evidence

- `the_one/knowledge/manager.py:162` — `self._embed_lock = asyncio.Lock()`; `:357` — `embed_lock=self._embed_lock`
- `tests/test_kb_manager.py` — classes `TestManagerLifecycleBasics`, `TestPass`, `TestApplyReconcile`, `TestFlushAndFlip`, `TestStaleRecovery`, `TestCooperativeStopAndCancelFallback`, `TestDrain`, `TestStartAll`; none starts two workers concurrently
- Flight 3 debrief, "Technical — Minor"

## Corrective Action

Added `TestConcurrentWorkers::test_two_kbs_index_concurrently_through_the_shared_embed_lock`
to `tests/test_kb_manager.py`, plus two supporting test-only helper
classes defined just above it:

- `_TrackingLock` — a spy around a real `asyncio.Lock` (full mutual
  exclusion preserved, not faked) that also flags a shared
  `threading.Event` (`second_waiter`) the instant a SECOND coroutine's
  `__aenter__` finds the lock already held. Assigned via a test-only
  swap of `manager._embed_lock` (the same "private-attribute swap"
  pattern the file already uses for `_store_factory`/`_backend_factory`
  in `TestStaleRecovery`/`TestCooperativeStopAndCancelFallback`), so it
  is the exact object `IndexContext.embed_lock` resolves to for both
  workers' passes.
- `_ConcurrencyTrackingBackend` — wraps `StubEmbeddingBackend`. Every
  `embed()` call is labelled by which KB it belongs to (a marker
  substring each KB's fixture file content carries), recorded into
  `sequence` under a `threading.Lock`-guarded in-flight counter
  (`max_in_flight`) that must never exceed 1. A small per-call
  `time.sleep` means two calls WOULD overlap if nothing serialised them.
  The very first call additionally blocks — bounded (1s), never a bare
  sleep used *as* the synchronisation primitive — on `second_waiter`,
  giving the OTHER kb's worker a deterministic window to reach the lock
  before the first call's thread proceeds.

The test: registers two knowledge bases (`kb-a`, `kb-b`), each with a
folder of 2 small files under `tmp_path`, starts both workers at the
same time through one `IndexingManager` (`request_index` for both, then
`wait_until_idle` for both), and asserts:

1. both KBs end with every file item `indexed` and `store.count` equal
   to their chunk counts;
2. `backend.max_in_flight` never exceeded 1 (the lock's correctness);
3. both `"kb-a"` and `"kb-b"` appear in `backend.sequence` (both
   workers actually ran);
4. `second_waiter.is_set()` is `True` — proof kb-b's worker genuinely
   reached the lock while kb-a's batch was still inside it (not "the
   second worker never started"), established via the `_TrackingLock`
   hook rather than inferred from timing.

Runtime is ~0.9s in isolation, well under the ~2s budget.

## Verification

Command: `PYTHON=.venv/bin/python bash scripts/run-tests.sh
tests/test_kb_manager.py -x --timeout 60 -q`

- Full file: `24 passed in 11.55s` (all pre-existing tests plus the new
  one).
- New test in isolation
  (`tests/test_kb_manager.py::TestConcurrentWorkers`): `1 passed in
  0.91s`.
- Lock-removed proof: temporarily changed
  `manager._embed_lock = _TrackingLock(second_waiter)` to
  `manager._embed_lock = None` (production's real no-op path —
  `IndexContext.embed_lock=None` resolves to `contextlib.nullcontext()`
  in `the_one/knowledge/indexer.py`) and re-ran the isolated test:
  `1 failed in 1.83s`, failing exactly on
  `assert backend.max_in_flight <= 1` with `assert 2 <= 1` — confirms
  the test genuinely exercises the lock rather than passing vacuously.
  The change was reverted immediately after (`git diff` shows only the
  final `_TrackingLock(second_waiter)` line — no TEMP variant left in
  the file).
- `make lint`: `All checks passed!`
- `ruff format --check the_one/ tests/ scripts/`: `437 files already
  formatted`.

No production code was touched — scope stayed within
`tests/test_kb_manager.py` and this squawk file.

## Sign-Off
**Reviewer**: Sonnet (batch review, squawk turnaround 2026-09-16; Sonnet tier — 0063 touches the route reading operator-registered paths)
**Verdict**: confirmed
**Commit**: (recorded in the follow-up commit)
