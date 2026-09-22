# Squawk 0059: Write-lock commit-guard test is a substring scan

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-15
**Completed**: 2026-09-15

## Report

`tests/test_db_write_lock.py`'s source guard proves `.commit()`/`.rollback()` are confined to the two allowed files by searching file text for the substrings. A comment or docstring containing `.commit()` trips it (Leg 1 had to re-wrap a rotation comment to dodge it), and a call spelled differently (`getattr(conn, "commit")()`, an alias) slips past. Replace with an `ast` walk over `Call` nodes whose `func` is an `Attribute` named `commit`/`rollback`, keeping the same allowlist and failure message.

Logged from the Mission 24 Flight 2 debrief (2026-09-15).

## Evidence

- `tests/test_db_write_lock.py:173-177` — `text = path.read_text(...)`; `if ".commit()" in text or ".rollback()" in text:`.
- Flight 2 flight log, Leg 1 close: "a line-wrap in the rotation comment to dodge a guard-test regex".

## Corrective Action

Rewrote `test_commit_and_rollback_confined_to_write_lock_and_schema` (`tests/test_db_write_lock.py`) to parse each `the_one/**/*.py` file's source with `ast.parse` and `ast.walk` it, collecting `ast.Call` nodes whose `func` is an `ast.Attribute` with `attr in {"commit", "rollback"}`. Offenders are now recorded as `file:line` (via `node.lineno`) instead of just the bare file path, which gives a more precise failure message pointing straight at the call site. The allowlist (`the_one/db/_write_lock.py`, `the_one/db/schema.py`) and the `Path("the_one").rglob("*.py")` scope are unchanged. The docstring was updated to describe the AST walk and explicitly call out that it no longer trips on comments/docstrings and that it catches aliased receivers (matching on the `Attribute` node's shape, not the receiver's spelling).

Residual known limitation (out of scope for this squawk, matches the report's own framing): the guard matches syntactic `x.commit()` / `x.rollback()` attribute-call shapes only. Fully dynamic dispatch such as `getattr(conn, "commit")()` still slips past, exactly as the substring scan did — the AST walk closes the comment/docstring false-positive and the simple-alias false-negative named in the report, not every conceivable indirection.

Checked for the previously-reported line-wrap dodge near the rotation endpoint (`the_one/interfaces/web/api.py`, AC-9 comment block ~4830-4840, from the Flight 2 Leg 1 close note). The comment there was already reworded to avoid the literal substring, e.g. "...whose exit is / the commit), this function MUST issue only DML statements..." and "aiosqlite silently / COMMITs before any non-DML statement..." — prose forms of "commit" with no `.commit()`/`.rollback()` substring. A full-repo grep for `.commit()`/`.rollback()` (literal or split across a line-wrap) outside the two allowed files turned up none in any `.py` file — the only other tree-wide hits are in `the_one/agents.md` and two `.js` files under `interfaces/web/static/js/`, none of which the guard's `rglob("*.py")` scope even reaches. This wrap is now unnecessary (the AST walk doesn't look at comments at all) but harmless — left in place, not touched, per this squawk's file-only scope.

## Verification

Ran `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_db_write_lock.py -x --timeout 60 -q` before and after each proof edit below; final state: 7 passed.

Proved the rewrite both ways using a throwaway scratch module `the_one/db/_proof_scratch.py` (created, exercised, then deleted — confirmed absent via `git status --porcelain` showing no untracked files afterward):

1. **Comment no longer trips it**: a module containing only a comment with the literal text `.commit()` / `.rollback()` (no code) — guard test passed (0 offenders).
2. **Real direct call still caught**: added `class _ProofRepo: async def commits_directly(self, conn): await conn.commit()` — guard test failed with `AssertionError: ... ['the_one/db/_proof_scratch.py:12'] ...`, correct file and line.
3. **Aliased call still caught**: replaced with `c = conn; await c.rollback()` — guard test failed with `AssertionError: ... ['the_one/db/_proof_scratch.py:13'] ...`, correct file and line. (This case also happened to contain the literal `.rollback()` substring, so it wouldn't have distinguished the old scan from the new one on its own — but it does confirm the AST match is receiver-name-agnostic, matching on the `Attribute` node's `attr` field regardless of what the receiver expression is.)

Deleted `the_one/db/_proof_scratch.py` after case 3 and reran the full file: 7 passed.

`ruff check the_one/ tests/`: all checks passed. `ruff format the_one/ tests/`: 423 files left unchanged (no reformatting needed).

`git diff --stat` confirms scope: only `tests/test_db_write_lock.py` and this squawk artifact changed relative to this task's starting point; all other modified files (`squawks/0054`-`0058`, `0060`-`0062`, and the various `tests/`/`the_one/` files from prior squawks) are pre-existing uncommitted work, untouched.

## Sign-Off
*(written at completion)*
**Reviewer**: Sonnet, batch review of squawk/turnaround-2026-09-15
**Verdict**: confirmed
**Commit**: ba46d62
