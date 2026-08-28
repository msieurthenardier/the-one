# Squawk 0018: No test keeps `_ENCRYPTED_CORPORA` and the rotation route's touched columns in sync

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-08-28
**Completed**: —

## Report

The set of encrypted columns is enumerated twice — as data in
`the_one/db/key_reconcile.py:_ENCRYPTED_CORPORA` (eight `(table, column)` pairs) and as
seven hand-written SELECT/UPDATE blocks in `the_one/interfaces/web/api.py:rotate_encryption_key`.
Nothing enforces that they agree. Mission 22 Flight 1 Decision D1 found two corpora that had
been missing from rotation for several missions; the next encrypted column can miss again.
Add a test that asserts every pair in `_ENCRYPTED_CORPORA` appears as a literal `(table, column)`
the route reads and writes (regex/AST scan of the route's source), and vice versa.

## Evidence

- `the_one/db/key_reconcile.py:20-29` — `_ENCRYPTED_CORPORA` tuple
- `the_one/interfaces/web/api.py:rotate_encryption_key` — `SELECT … FROM llm_providers|mcp_sources|connectors|agents|tool_configs|agent_external_credentials` and the matching `UPDATE` statements
- Flight log Decision D1, `missions/22-maintenance/flights/01-credential-lifecycle-integrity/flight-log.md`
- The full `EncryptedColumn` registry refactor is flight-sized (three decrypt shapes); this squawk is the cheap guard only

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
