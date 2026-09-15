# Squawk 0054: Bound `search_keyword`'s `k` and guard vector dimension at the store seam

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-15
**Completed**: 2026-09-15

## Report

`KBChunkRepository.search_keyword` passes its `k` argument straight into `LIMIT ?` with no ceiling, and `VectorStore.upsert`/`query` accept any array shape — a wrong-width vector reaches usearch unguarded. Neither matters today (no caller is agent-controlled), but Flight 5 exposes both paths to a tool argument, where an unbounded `k` is a resource-exhaustion vector and a wrong dimension is silent garbage rather than a clear error. Fix: clamp or reject `k` above a stated ceiling at the repository (the leg's own note said the bound belongs there or at the caller — pick the repository so every caller inherits it), and raise `ValueError` naming the expected `dim` when `vectors.shape[-1] != self.dim` in `UsearchStore.upsert` / `query`. Required before Flight 5's agent-facing query path is designed.

Logged from the Mission 24 Flight 2 debrief (2026-09-15).

## Evidence

- `the_one/db/repositories.py:804-810` — `"ORDER BY score LIMIT ?", (match_query, kb_id, k)`; no bound on `k`.
- `the_one/vectors/usearch_store.py:242` (`upsert`) and `:306` (`query`) — `_maybe_quantize(np.asarray(vectors))` with no shape check.
- Flight 2 flight log, "flight-end review, cycle 1": squawk candidate "no `shape[-1] == dim` guard on `upsert`/`query`".

## Corrective Action

1. **`KBChunkRepository.search_keyword` (`the_one/db/repositories.py`)**: added a module constant `MAX_SEARCH_K = 1000` (next to the existing `_GET_MANY_BATCH_SIZE` batching constant) and a guard `if k < 1 or k > MAX_SEARCH_K: raise ValueError(...)` at the top of the method, naming the bound and the offending `k`. Chose **reject, not clamp**, for both ends of the range: the repository already has an established convention of raising `ValueError` for invalid input (the illegal-field guard in the agent-config update path, the unknown-KB-item-status guard) and no existing precedent for silently clamping a caller-supplied numeric range — clamping an over-large `k` would let a resource-exhaustion-shaped call succeed silently instead of surfacing the mistake to the (eventual, Flight 5) agent caller. Docstring updated to state the bound and the reject-not-clamp rationale.

2. **`UsearchStore.upsert` / `.query` / `.rebuild_from` (`the_one/vectors/usearch_store.py`)**: added a `_check_dim(vectors, kb_id)` helper — a `.shape[-1]` read (no copy, no `np.asarray` conversion) compared against `self.dim` — and called it at the top of all three methods, before `_maybe_quantize`/`index.add`/`index.search`. Raises `ValueError` naming the expected dim, the actual width, and the `kb_id`. `rebuild_from` calls it inside its per-batch loop (once per `(ids, vectors)` tuple), matching the squawk's note that it "feeds the same `add`". Placed in `query` before the per-KB lock/`_ensure_loaded` so a wrong-width query vector is rejected even against an empty/never-created index, rather than being masked by the empty-index `return []` short-circuit.

3. **Docs**: added a one-line "Dimension guard (squawk 0054)" bullet to the `VectorStore` Protocol docstring in `the_one/vectors/_store.py`'s contract list, and a matching one-sentence bullet to `the_one/agents.md`'s "Knowledge storage" section (after the `delete_kb`-guard-first bullet), since that section documents `UsearchStore`'s raised-error behaviour (`VectorStoreStaleError`, the path-traversal `VectorStoreError`) elsewhere in the same run of bullets.

## Verification

Commands run (all green):
```
PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_kb_chunks.py tests/test_vector_store.py tests/test_db_api.py -x --timeout 60 -q
# 136 passed
ruff check the_one/ tests/          # All checks passed!
ruff format the_one/ tests/         # 423 files already formatted (1 reformatted on first pass, then clean)
```

New tests, and why each fails without its guard:

- `tests/test_kb_chunks.py::TestSearchKeyword::test_k_below_one_raises` — `k=0`/`k=-1` passed straight to SQLite's `LIMIT ?` today produces `LIMIT 0` (silently empty) or `LIMIT -1` (SQLite treats negative as unbounded), neither of which raises — without the added `if k < 1 ...` guard this test's `pytest.raises(ValueError)` would not fire.
- `tests/test_kb_chunks.py::TestSearchKeyword::test_k_above_ceiling_raises` — same reasoning for `k = MAX_SEARCH_K + 1`: today it reaches SQLite unbounded and returns successfully; fails without the `k > MAX_SEARCH_K` guard.
- `tests/test_vector_store.py::TestDimensionGuard::test_upsert_wrong_width_raises_naming_both_dims` / `test_query_wrong_width_raises_naming_both_dims` / `test_rebuild_from_wrong_width_raises_naming_both_dims` — each passes a `dim=8` vector array against the `store` fixture's `dim=512` (parametrised over both usearch dtype cells, f16/i8). Before this fix, `upsert`/`rebuild_from` would pass the mismatched array straight to `usearch.Index.add`, and `query` straight to `Index.search`/quantisation, with no shape check in this codebase's own code — any resulting failure would come from inside the `usearch` C extension (an unpredictable/opaque exception, not a `ValueError` naming `512`/`8`/`"kb"`), so `pytest.raises(ValueError, match=str(DIM))` would not reliably fire without the added `_check_dim` calls.

`make test-unit` was not run as a separate step; the targeted `run-tests.sh` invocation above covers the changed files' full test modules plus `test_db_api.py` per the assignment (repository/vector-store/db-API seam), all passing.

## Sign-Off
*(written at completion)*
**Reviewer**: Sonnet, batch review of squawk/turnaround-2026-09-15
**Verdict**: confirmed
**Commit**: _(recorded in the follow-up commit)_
