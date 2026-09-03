# Squawk 0039: Directory search LIKE query doesn't escape % and _

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-02
**Completed**: 2026-09-03

## Report

`ConnectorDirectoryRepository.search` builds a `LIKE '%query%'` over display_name and
username without escaping SQL wildcards in the user-supplied substring — a query of
`%` or `_` matches everything/anything. Not a security issue (results stay inside the
already-authorized connector scope) but wrong results. Escape `%`, `_`, and the escape
char with an `ESCAPE` clause; one test each for a literal `%`/`_` query.

## Evidence

- `the_one/db/repositories.py:841` — the LIKE construction
- Flight 4 flight-end review, non-blocking note (2026-09-02)

## Corrective Action

`ConnectorDirectoryRepository.search` (`the_one/db/repositories.py`, `search`
method) now escapes the user-supplied substring before embedding it in the
`LIKE` pattern: `\` → `\\`, `%` → `\%`, `_` → `\_` (in that order, on the
already-lowercased query), then wraps it as `%...%`. Both `LIKE` clauses
(`display_name` and `username`) gained a matching `ESCAPE '\'` clause so
SQLite honors the escaping. Case-insensitivity (`LOWER(...)`) is unchanged.
Docstring updated to note the escaping behavior.

## Verification

Extended `tests/test_db_repositories.py` (`TestConnectorDirectoryRepository`)
with two new cases: a literal `%` query matches only directory entries whose
`display_name`/`username` contains a literal `%` (not every row), and a
literal `_` query matches only entries containing a literal `_` (not every
row). Existing substring/case-insensitivity behavior is unchanged and
covered by the pre-existing `test_search_case_insensitive_substring_over_display_name_and_username`.

Ran foreground, no timeouts hit:
- `tests/test_db_repositories.py` + `tests/test_connector_lookup_tool.py` —
  173 passed, no warnings (also fixed a pre-existing `SyntaxWarning:
  invalid escape sequence` introduced transiently while drafting the
  docstring, resolved before commit-worthy state).
- `.venv/bin/ruff check the_one/ tests/ && .venv/bin/ruff format --check
  the_one/ tests/` — all checks passed, 401 files already formatted.

## Sign-Off
**Reviewer**: independent batch Reviewer (Sonnet — security tier for 0037), squawk/turnaround-2026-09-03
**Verdict**: confirmed
**Commit**: squawk/turnaround-2026-09-03 batch commit (PR follows)
