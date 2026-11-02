# Squawk 0297: Document the per-knowledge-base vector ceiling and log a flush slower than the query timeout

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-30
**Completed**: 2026-11-01

## Report
Resident vector RAM was carried as unmeasured since Mission 24. The 2026-10-30 maintenance cycle measured it: about 1.2 KB resident per vector (512-dim f16, fully loaded), about 1.2 GB at 1M vectors. The binding limit is the flush, not the RAM: `flush()` holds the per-KB lock for the whole atomic save, and a query waits at most `SEMANTIC_QUERY_TIMEOUT` (2.0 s) before degrading to keyword-only, which a save reaches somewhere around 1.5-2M vectors. Neither threshold is written down, and a slow flush is silent. From maintenance report 2026-10-30, finding #14.

## Evidence
- `the_one/vectors/usearch_store.py:407` `flush` holds the KB lock across `_save_atomically` (0.10 s for 100k vectors, a 117 MB file on a warm cache).
- `the_one/knowledge/retrieval.py`: `SEMANTIC_QUERY_TIMEOUT` = 2.0 s.
- `the_one/embeddings/local.py:39` `EMBEDDING_DIM = 512`; `the_one/knowledge/settings.py:164` dtype `f16`.

## Corrective Action
`the_one/agents.md` (vector-store section, after the lock-wait paragraph) now states the measured RAM per vector, the ~1M per-knowledge-base ceiling and the flush as the binding limit, citing `maintenance/2026-10-30.md` finding #14. `UsearchStore.flush` times `_save_atomically` and logs one WARNING (knowledge base and duration) when it exceeds `SLOW_FLUSH_WARN_SECONDS` (2.0), a pinned copy of `SEMANTIC_QUERY_TIMEOUT` because the vectors layer sits below knowledge. Locking and flush behaviour are unchanged.

## Verification

`agents.md`'s vector-store section states the measured per-vector RAM and the comfortable ceiling (~1M vectors per knowledge base). A unit test with an injected slow save shows `flush` logs one WARNING naming the knowledge base and the duration when the save outlasts `SEMANTIC_QUERY_TIMEOUT`.

`tests/test_vector_store.py::TestSlowFlushWarning` (slow save: one WARNING; fast save: none; constant equals `SEMANTIC_QUERY_TIMEOUT`). Falsified by disabling the warning: the slow-save test failed, then passed once restored.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet; the batch states security-model residual risks, 0298 and 0299), batch review of the 2026-11-01 squawk turnaround, scoped to the diff, `[HANDOFF:confirmed]`. Falsified: yes. Process note: the Developer appended `TestSlowFlushWarning` to `tests/test_vector_store.py` with a shell heredoc (squawk 0286 rule); the Flight Director confirmed the diff is a pure 53-line addition at the end of the file.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-01` commit on `squawk/turnaround-2026-11-01`. Unit tier under `THE_ONE_TEST_NETNS=1`: 8560 passed, 23 skipped, 3 failed (the known `tests/test_desktop_host.py` baseline, unchanged from main).
