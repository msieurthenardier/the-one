# Squawk 0066: no test drives two live `IndexingManager` workers through the shared `embed_lock`

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-16
**Completed**: —

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
*(written at completion)*

## Verification
The new test in `tests/test_kb_manager.py` passes and fails when the lock is removed from `IndexContext` (proves it exercises the lock).

## Sign-Off
*(written at completion)*
