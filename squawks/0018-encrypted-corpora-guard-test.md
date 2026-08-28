# Squawk 0018: No test keeps `_ENCRYPTED_CORPORA` and the rotation route's touched columns in sync

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-08-28
**Completed**: 2026-08-28

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

Added `tests/test_encrypted_corpora_guard.py` with two tests, both parsing
`inspect.getsource(rotate_encryption_key)`:

- `test_encrypted_corpora_matches_rotation_route_reads` extracts `{(table,
  column)}` from every `SELECT col[, col...] FROM table` in the route (via
  `_SELECT_RE`, filtering the leading lookup column — `id`/`name`/`identifier`
  — which identifies the row rather than naming a corpus) and asserts the
  result equals `set(_ENCRYPTED_CORPORA)`.
- `test_encrypted_corpora_matches_rotation_route_writes` does the same for
  `UPDATE table SET col = ?[, col = ?...]` (via `_UPDATE_RE`, splitting the
  SET clause on commas and taking the identifier left of each `=`).

Two independent extractions rather than one AST/regex pass covering both,
because the failure this squawk exists to catch isn't just "a corpus is
missing from `_ENCRYPTED_CORPORA` entirely" — it's also "a corpus is read in
the decrypt phase but its UPDATE loop was dropped" (or vice versa), which a
single combined set would mask by unioning reads and writes together. Keeping
the two checks separate means a column that's selected but never written back
(or written but never selected) fails on its own, pointing at exactly which
half of the route drifted.

Both regexes use `re.DOTALL` and collapse internal whitespace before parsing,
per the instruction to tolerate multi-line SQL — the route's own SELECT/UPDATE
strings are all single-line literals today, but the extractor doesn't assume
that stays true. A failure message names the missing/extra `(table, column)`
pairs and points at both `the_one/db/key_reconcile.py:_ENCRYPTED_CORPORA` and
`the_one/interfaces/web/api.py:rotate_encryption_key` so the next drift is
easy to locate and fix from the assertion alone. Each test also asserts its
extracted set is non-empty first, so a regex that silently stopped matching
(e.g. after an unrelated refactor of the route) fails loudly instead of making
the corpora-equality check vacuously true.

Test-only change — no production code touched (confirmed clean `git diff` on
`the_one/db/key_reconcile.py` and `the_one/interfaces/web/api.py` after the
verification below).

## Verification

- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_encrypted_corpora_guard.py -x --timeout 60`
  → `2 passed` against the current (in-sync) route and registry.
- `.venv/bin/ruff check . && .venv/bin/ruff format --check .` → both clean
  (ruff format reflowed two over-length assert lines in the new test file on
  first pass; re-ran clean after).
- Guard-bites check: temporarily removed `("agents", "mcp_overrides")` from
  `_ENCRYPTED_CORPORA` in `the_one/db/key_reconcile.py`, reran the same
  command — both new tests failed, each reporting
  `present in rotate_encryption_key {reads,writes} but absent from
  _ENCRYPTED_CORPORA: [('agents', 'mcp_overrides')]` and naming both file
  locations in the assertion body. Restored the removed line; `git diff --
  the_one/db/key_reconcile.py` and `git status --porcelain` confirmed the file
  is back to its original committed state (only the new test file and this
  squawk artifact remain changed). Reran the full command once more: `2
  passed`.

## Sign-Off
**Reviewer**: Reviewer agent (independent, diff-scoped batch review of turnaround 2026-08-28; Sonnet — batch touches the credential gate and key-material code)
**Verdict**: confirmed
**Commit**: `{sha}` on `squawk/turnaround-2026-08-28` — PR #{pr}

Full unit suite at close-out: 4580 passed / 10 skipped / 0 failed (513s); browser lane for 0022: 2 passed.
