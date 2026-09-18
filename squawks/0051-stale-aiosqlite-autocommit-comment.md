# Squawk 0051: `api.py` rotation comment repeats a false aiosqlite auto-commit claim

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-14
**Completed**: 2026-09-18

## Report

The encryption-rotation endpoint carries a comment stating that "aiosqlite
silently COMMITs before any non-DML statement (PRAGMA, DDL, BEGIN)", citing
the `schema.py` v8 docstring, and constrains the function's statement mix on
that basis. The claim is false on every Python this project supports: the
implicit commit before DDL was removed in Python 3.6. Measured during Mission
24 Flight 2 planning (Python 3.12.3 / SQLite 3.45.1): after uncommitted DML,
a `PRAGMA` or `CREATE TABLE` leaves `in_transaction == True` and a subsequent
`rollback()` discards the DML. The rotation code's actual behaviour is fine —
the comment's constraint is merely unnecessary — but the comment is the one a
developer designing a multi-statement write would lean on, and it would lead
them to the wrong mental model of what does and does not split a transaction.

Fix: rewrite the comment to state the real rule (a transaction is opened by
the first DML under `isolation_level=""` and ends only at `commit()` /
`rollback()`; **another coroutine's `commit()` on the shared connection is the
thing that splits it** — see Flight 2 DD-13 and the `db-writes-hold-the-
write-lock` convention once it lands). The `schema.py:319-327` twin is
corrected in Flight 2 Leg 1, which touches that file; this squawk is only the
`api.py` copy.

## Evidence

- `the_one/interfaces/web/api.py:4642-4647` — "Per the schema.py v8 docstring, aiosqlite silently COMMITs before any non-DML statement (PRAGMA, DDL, BEGIN), which would split the rotation into two separately-committed transactions"
- `the_one/db/schema.py:319-321` — the cited source: "aiosqlite's default isolation_level="" mode silently COMMITs before any non-DML statement (CREATE/ALTER/DROP)"
- Architect design review, Mission 24 Flight 2 cycle 1 (flight log, Flight Director Notes): measured `in_transaction` stays `True` across DDL/PRAGMA and `rollback()` discards prior DML
- Python 3.6 changelog: "sqlite3 no longer implicitly commits an open transaction before DDL statements"

## Corrective Action

Rewrote the comment at `the_one/interfaces/web/api.py` (immediately above
the encryption-rotation endpoint's first `SELECT`, inside
`rotate_encryption_key`) to drop the false "aiosqlite silently COMMITs
before any non-DML statement" claim. The replacement states the real rule
per DD-13 and the corrected `schema.py` v8 migration-block comment: under
aiosqlite's default `isolation_level=""` mode, a transaction is opened by
the first DML statement and stays open only until an explicit
`commit()`/`rollback()` — DDL and PRAGMA do NOT auto-commit (removed in
Python 3.6). What actually splits a transaction is *another coroutine's*
`commit()` on the shared connection landing mid-sequence; `write_transaction()`
(`the_one/db/_write_lock.py`) is what prevents that for the write later in
the same function, by holding the write lock across it. No logic changed —
this function still issues only `SELECT` statements before entering
`write_transaction()`; only the comment's stated rationale changed.

## Verification

- Comment-only change, confirmed by `git diff -- the_one/interfaces/web/api.py`: no non-comment line touched.
- `ruff check the_one/ tests/ scripts/` — `All checks passed!` (run as part of the combined `make lint` pass for this batch).
- The rotation function's statement sequence (SELECT-only reads, then `write_transaction()` around the writes) is unchanged; behaviour was not altered.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
