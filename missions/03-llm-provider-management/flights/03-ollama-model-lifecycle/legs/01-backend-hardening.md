# Leg: backend-hardening

**Status**: completed
**Flight**: [Ollama Model Lifecycle](../flight.md)

## Objective

Fix key rotation atomicity bug and normalize error handling across all provider endpoint branches.

## Context

- Flight 02 debrief flagged two critical items: key rotation has a data-loss window, and error handling is inconsistent across provider types
- The `rotate_encryption_key()` endpoint passes a no-op lambda to `rotate_key()`, meaning the new key is written to disk before the DB is re-encrypted. A crash between these steps leaves secrets unrecoverable.
- In `list_provider_models`, only the `openai-compatible` branch wraps exceptions in HTTPException(502). The `ollama`, `openai`, and `anthropic` branches let exceptions propagate as unhandled 500s.
- In `test_provider`, all exceptions fall through to a generic catch-all that returns 200 with `{"status": "error"}` — acceptable but should be consistent.

## Inputs

- `the_one/encryption.py` — `rotate_key()` method (lines 40-67)
- `the_one/interfaces/web/api.py` — `rotate_encryption_key` endpoint (lines 541-563), `test_provider` (lines 451-489), `list_provider_models` (lines 492-535)

## Outputs

- `the_one/interfaces/web/api.py` — fixed `rotate_encryption_key` that does re-encryption inside the callback; `list_provider_models` with consistent HTTPException(502) wrapping on all provider branches
- Updated or new tests covering the atomicity fix and error normalization

## Acceptance Criteria

- [ ] `rotate_encryption_key` performs re-encryption inside the `rotate_key` callback so that callback failure preserves the old key on disk. DB writes happen after `rotate_key` returns (new key on disk + re-encrypted values in memory = safe to commit)
- [ ] All provider type branches in `list_provider_models` wrap upstream failures in HTTPException(status_code=502)
- [ ] `test_provider` error handling is consistent across all provider types (currently acceptable — verify and normalize if needed)
- [ ] Existing tests pass, new tests cover the rotation atomicity and error wrapping
- [ ] No ruff violations

## Verification Steps

- `cd ~/projects/the-one && python -m pytest tests/ -x --timeout=30`
- `cd ~/projects/the-one && ruff check the_one/`
- Inspect `rotate_encryption_key` to verify the reencrypt callback writes to DB before the key file is updated

## Implementation Guidance

1. **Fix key rotation atomicity in `api.py`**
   - The `rotate_key` callback is sync (`Callable[[Encryptor, Encryptor], None]`) but DB ops are async. Use this approach:
     1. Pre-fetch all rows with API keys and decrypt them using the current encryptor (before calling `rotate_key`)
     2. Inside the sync callback, re-encrypt all plaintext values using `new_encryptor` and store results in a closure variable (e.g., a list of `(id, ciphertext)` tuples)
     3. After `rotate_key` returns (key file now written to disk), write re-encrypted values to DB and commit
   - Safety guarantee: if the callback raises (re-encryption fails), `rotate_key` preserves the old key file. If the DB write fails after, we have re-encrypted values in memory + new key on disk, so the write can be retried or an error returned for manual intervention
   - Use `new_encryptor.encrypt()` in the callback, not `encryptor.encrypt()` (which still has the old key at callback time)

2. **Normalize error handling in `list_provider_models`**
   - Wrap `ollama`, `openai`, and `anthropic` branches in try/except that raises HTTPException(status_code=502, detail=str(e))
   - Match the existing pattern from the `openai-compatible` branch

3. **Verify `test_provider` consistency**
   - The generic catch-all on line 486-487 handles all types equally — this is acceptable
   - If any branch needs tightening, do it, but don't over-engineer

4. **Tests**
   - Add/update test for `rotate_encryption_key` verifying that secrets are re-encrypted correctly
   - Add tests for `list_provider_models` error cases on ollama/openai/anthropic types returning 502

## Edge Cases

- **Callback failure during rotation**: Old key must be preserved — verify this is the case
- **Empty provider table**: Rotation with no secrets should succeed (no-op)
- **DB write failure after key rotation**: Key file reflects new key, but re-encrypted values are in memory. Error should be returned indicating the state; the write can be retried since re-encrypted values match the new key

## Files Affected

- `the_one/interfaces/web/api.py` — `rotate_encryption_key`, `list_provider_models`, possibly `test_provider`
- `tests/` — new or updated test file for rotation and error handling

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] Commit all changes together (code + artifacts)
