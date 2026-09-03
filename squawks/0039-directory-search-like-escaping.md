# Squawk 0039: Directory search LIKE query doesn't escape % and _

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-02
**Completed**: —

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
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
