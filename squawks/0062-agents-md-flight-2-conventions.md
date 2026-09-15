# Squawk 0062: Name four Flight 2 conventions in `the_one/agents.md`

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-15
**Completed**: —

## Report

Four patterns the flight instantiated live only in code comments and the flight log. Add them to `the_one/agents.md` "Project Conventions": *empty-transaction re-entry guard* (an in-memory-until-flush store opens and closes an empty `write_transaction` so DD-13's no-nesting rule holds uniformly — cite `UsearchStore.upsert`); *atomic sidecar save* (write `<path>.tmp` in the same directory, `os.replace`, then the registry row; a crash between the two reads as stale and is recoverable, never silent — cite `_save_atomically`); *migration tests replay the real chain* (fixtures must not stamp `schema_version` past tables they never created; until they comply, a block touching an always-present table carries a presence guard — cite v40 `kb_items` and v41 `app_metadata`); *store-owned-until-decided* (a schema element whose owner is an open planning question is created by the owner until the decision, then moved into a migration — cite `kb_vector_index`). Also add one sentence to "Knowledge storage": synthetic-corpus recall is index recall on a clustered generator; DD-4's 0.95 floor applies to real-corpus recall only.

Logged from the Mission 24 Flight 2 debrief (2026-09-15).

## Evidence

- `the_one/agents.md:82` `## Project Conventions`; the Knowledge storage section (~line 1128).
- `the_one/vectors/usearch_store.py` module docstring and `_save_atomically` docstring; `the_one/db/schema.py` v40/v41 guard comments.
- Flight 2 debrief, Recommendation 3.

## Corrective Action
*(written at completion)*

## Verification
Doc-only; `tests/test_token_definitions.py`-style checks unaffected; a reviewer confirms each convention cites a real symbol.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
