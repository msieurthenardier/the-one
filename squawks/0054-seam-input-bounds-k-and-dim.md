# Squawk 0054: Bound `search_keyword`'s `k` and guard vector dimension at the store seam

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-15
**Completed**: —

## Report

`KBChunkRepository.search_keyword` passes its `k` argument straight into `LIMIT ?` with no ceiling, and `VectorStore.upsert`/`query` accept any array shape — a wrong-width vector reaches usearch unguarded. Neither matters today (no caller is agent-controlled), but Flight 5 exposes both paths to a tool argument, where an unbounded `k` is a resource-exhaustion vector and a wrong dimension is silent garbage rather than a clear error. Fix: clamp or reject `k` above a stated ceiling at the repository (the leg's own note said the bound belongs there or at the caller — pick the repository so every caller inherits it), and raise `ValueError` naming the expected `dim` when `vectors.shape[-1] != self.dim` in `UsearchStore.upsert` / `query`. Required before Flight 5's agent-facing query path is designed.

Logged from the Mission 24 Flight 2 debrief (2026-09-15).

## Evidence

- `the_one/db/repositories.py:804-810` — `"ORDER BY score LIMIT ?", (match_query, kb_id, k)`; no bound on `k`.
- `the_one/vectors/usearch_store.py:242` (`upsert`) and `:306` (`query`) — `_maybe_quantize(np.asarray(vectors))` with no shape check.
- Flight 2 flight log, "flight-end review, cycle 1": squawk candidate "no `shape[-1] == dim` guard on `upsert`/`query`".

## Corrective Action
*(written at completion)*

## Verification
New tests in `tests/test_kb_chunks.py` (over-large `k` is clamped/rejected) and `tests/test_vector_store.py` (wrong-width vector raises `ValueError` naming the dim for both `upsert` and `query`); `make test-unit` green.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
