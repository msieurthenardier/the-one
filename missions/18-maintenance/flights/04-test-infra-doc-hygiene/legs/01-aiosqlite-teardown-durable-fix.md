# Leg: aiosqlite-teardown-durable-fix

**Status**: completed
**Flight**: [Test-infra & doc hygiene](../flight.md)

## Objective
Durably fix the aiosqlite `Event loop is closed` teardown artifact — the oldest carried test-infra debt (since F05, F09-escalated) — so the worker thread's `close()` never fires across a torn-down event loop.

## Context
Maintenance report 2026-07-10 finding **T1**: the artifact surfaces as a `PytestUnhandledThreadExceptionWarning` (`RuntimeError('Event loop is closed')`) attributed to `tests/test_db_migration.py::TestSchemaV17`. `tests/conftest.py:62-99` (`_daemonize_aiosqlite_worker_threads`) daemonizes the worker so the interpreter can't wedge, but does NOT prevent the closed-loop `close()` raising. Presents as a cosmetic Pass across green runs, BUT F09 witnessed a **real intermittent hard failure** in `test_lifespan.py::test_lifespan_drains_session_registry` — load-order-dependent.

**Design review corrected the diagnosis** (AST-swept all 85 `aiosqlite.connect` sites): it is NOT a blanket "connections aren't closed" problem — 83/85 are closed 1:1 in-loop. The real causes:
- **One deterministic leak: `tests/test_db_migration.py:1798`** (`TestSchemaV16.test_v16_legacy_v15_row_decodes_with_null_external_key_columns`) opens a connection and **never closes it** (function ends ~1908 on a bare assert). This is the last test in `TestSchemaV16`, immediately followed by `class TestSchemaV17` (~1911) — which is why the async teardown warning gets *attributed* to `TestSchemaV17` (a timing artifact, not the origin). Fixing this leak should remove the warning.
- **A harmless duplicate close: `tests/test_db_migration.py:2088-2090`** (`TestSchemaV17.test_v17_legacy_v16_row_decodes_with_empty_connector_ids`) — idempotent per aiosqlite 0.22.1's `close()` guard, but dead code; clean it up.
- **Structural fragility (the F09-escalation root):** 84/85 closes are bare trailing statements with **no `try/finally`**, including the shared `setup` fixture (`tests/test_db_migration.py:20-37`, consumed by 4 tests) whose `await conn.close()` sits after `yield` unprotected — so *any* assertion failure in a consuming test skips the close and leaks a connection onto a to-be-torn-down loop. This is the load-order-dependent nondeterminism F09 saw. The durable fix must make the close **failure-safe**, not just present.

Disposition: **fix durably, don't accept a sixth time.**

## Inputs
- `tests/conftest.py` (the existing `_daemonize_aiosqlite_worker_threads`, ~line 62-99; pytest-asyncio config).
- `tests/test_db_migration.py` (`TestSchemaV17` and siblings — the raw `aiosqlite.connect` sites).
- `pyproject.toml` / `pytest.ini` / `conftest` — `asyncio_mode` + any loop-scope config.
- `the_one/db/connection.py` (how production closes the singleton deterministically in-loop — the pattern the tests should emulate).

## Acceptance Criteria
- [x] **Fix the deterministic leak at `tests/test_db_migration.py:1798`** — close that connection in-loop (prefer `async with aiosqlite.connect(...) as conn:` so the close is guaranteed even on assertion failure). The `Event loop is closed` / `PytestUnhandledThreadExceptionWarning` no longer appears in the warnings-summary of a normal `make test-unit` run.
- [x] **Make the close failure-safe, not just present** (design-review [2]): convert the raw connect/close pairs in the migration tests — at minimum the shared `setup` fixture (`:20-37`) and any bare trailing-close sites — to `async with` (or `try/finally`), so a mid-test assertion failure can't orphan a connection on a to-be-torn-down loop. `async with` is preferred (closes in-loop deterministically regardless of exceptions). Full conversion of all 85 sites is NOT required — target the deterministic leak + the shared/fragile sites; note which you converted and why.
- [x] **Remove the duplicate close at `:2088-2090`** (dead code).
- [x] **Order-dependence verification without new tooling** (design-review [3]: `pytest-randomly` is NOT installed, and running twice in the same order proves nothing): verify the warning is absent under an explicit **file-order permutation** that exercises the implicated adjacency — e.g. run `tests/test_lifespan.py tests/test_db_migration.py` and the reverse order, plus the normal full `make test-unit`. Do NOT add `pytest-randomly` (it would randomize the whole 3986-test suite and risk surfacing unrelated latent order-deps mid-maintenance — out of scope).
- [x] No test is skipped/xfail'd; migration tests still assert what they asserted before. No blanket `filterwarnings = ignore` (masks future real event-loop bugs).
- [x] Full unit suite green (`make test-unit`), same pass count (±0 modulo any new test), 0 failed.
- [x] `git diff` limited to `tests/test_db_migration.py` (and `tests/conftest.py` only if `_daemonize_aiosqlite_worker_threads` becomes redundant) + flight artifacts. **No `the_one/**` production change** (test-infra fix). No `pyproject.toml` change (no new dep).

## Verification Steps
- Run `make test-unit` twice (and once with a shuffled order if the runner supports it); grep the output for `Event loop is closed` / `PytestUnhandledThreadExceptionWarning` — must be absent.
- Confirm `test_lifespan.py::test_lifespan_drains_session_registry` passes in-suite (the F09-escalated case), not just in isolation.

## Implementation Guidance
1. **Fix `test_db_migration.py:1798`** — the confirmed deterministic leak. Convert its `aiosqlite.connect(...)` to `async with ... as conn:` so it closes in-loop unconditionally.
2. **Harden the fragile sites** — convert the shared `setup` fixture (`:20-37`, post-`yield` close consumed by 4 tests) and the other bare trailing-close pairs to `async with` (or `try/finally`). Prefer `async with`. This removes the failure-leak class (design-review [2]).
3. **Remove the duplicate close** at `:2088-2090`.
4. **Verify order-independence** via explicit file-order permutation (design-review [3]): `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_lifespan.py tests/test_db_migration.py` and the reverse, grepping for `Event loop is closed` — plus the full `make test-unit`. No `pytest-randomly`.
5. Keep `_daemonize_aiosqlite_worker_threads` as a backstop unless the durable fix makes it clearly redundant (if you remove it, prove the warning stays absent without it). Comment the converted sites with a pointer to this leg + report finding T1.

## Edge Cases
- Load-order dependence: a single green run does NOT prove the fix — run multiple / shuffled.
- Don't over-fix into a blanket `filterwarnings = ignore` — that masks future real event-loop bugs.

## Files Affected
- `tests/conftest.py`, `tests/test_db_migration.py` (and/or a shared DB-test fixture).

---

## Post-Completion Checklist
- [x] All acceptance criteria verified (multi-run, warning absent)
- [x] Tests passing
- [x] Update flight-log.md with a Leg Progress entry
- [x] Set this leg's status to `landed`
- [x] Check off this leg in flight.md
- [x] Changes stay uncommitted — batch commit after review
