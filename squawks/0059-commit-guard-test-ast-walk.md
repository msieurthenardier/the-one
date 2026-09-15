# Squawk 0059: Write-lock commit-guard test is a substring scan

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-15
**Completed**: —

## Report

`tests/test_db_write_lock.py`'s source guard proves `.commit()`/`.rollback()` are confined to the two allowed files by searching file text for the substrings. A comment or docstring containing `.commit()` trips it (Leg 1 had to re-wrap a rotation comment to dodge it), and a call spelled differently (`getattr(conn, "commit")()`, an alias) slips past. Replace with an `ast` walk over `Call` nodes whose `func` is an `Attribute` named `commit`/`rollback`, keeping the same allowlist and failure message.

Logged from the Mission 24 Flight 2 debrief (2026-09-15).

## Evidence

- `tests/test_db_write_lock.py:173-177` — `text = path.read_text(...)`; `if ".commit()" in text or ".rollback()" in text:`.
- Flight 2 flight log, Leg 1 close: "a line-wrap in the rotation comment to dodge a guard-test regex".

## Corrective Action
*(written at completion)*

## Verification
The rewritten test still passes on the tree; a temporary `.commit()` inside a comment no longer trips it and a temporary real `conn.commit()` in a repository still does (state both in the corrective action).

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
