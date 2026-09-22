# Squawk 0056: `PUT /api/knowledge-settings` silently drops nested unknown keys

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-15
**Completed**: 2026-09-15

## Report

The route 422s an unknown top-level key, but an unknown key nested inside `embedding` or `chunking` (e.g. a typo of `overlap_chars`) is merged and then discarded by the Pydantic model, so the caller gets 200 and a silently unchanged setting. Fix: `model_config = ConfigDict(extra="forbid")` on `EmbeddingSettings` and `ChunkingSettings` (and `VectorStoreSettings` for consistency), with the resulting `ValidationError` surfacing as the route's existing 422 shape.

Logged from the Mission 24 Flight 2 debrief (2026-09-15).

## Evidence

- `the_one/knowledge/settings.py:48` (`EmbeddingSettings`), `:80` (`ChunkingSettings`) — no `model_config`, so Pydantic's default `extra="ignore"` applies.
- `the_one/interfaces/web/api.py:1614` `update_knowledge_settings` — merges the incoming dict then validates.
- Flight 2 flight log, "flight-end review, cycle 1": squawk candidate "nested unknown keys inside `embedding`/`chunking` are dropped rather than refused".

## Corrective Action

Added `model_config = ConfigDict(extra="forbid")` to `EmbeddingSettings`,
`ChunkingSettings`, and (for consistency) `VectorStoreSettings` in
`the_one/knowledge/settings.py`. No change was needed in
`update_knowledge_settings` (`the_one/interfaces/web/api.py:1615`): it
already wraps the `KnowledgeSettings(...)` construction in
`try/except ValidationError` and returns `HTTPException(422, e.errors(...))`,
so the `extra_forbidden` error pydantic now raises for a nested unknown
key flows through that same existing path. `e.errors()`'s `loc` tuple
names the offending key (e.g. `("backend_typo",)`), so the 422 body
already identifies it — verified interactively and via the new
`test_put_nested_unknown_key_422s_and_names_the_key` test, which asserts
the key string appears in the response body.

**Read-path impact.** `load_knowledge_settings` catches
`(ValidationError, ValueError)` around each section's
`model_validate_json` and degrades to the section default with a
warning naming the storage key — this already covers the new
`extra_forbidden` failure mode with no code change; added a regression
test (`test_stored_record_with_extra_key_falls_back_to_default_with_warning`)
confirming an old stored record carrying an extra key still degrades to
defaults rather than raising.

`load_vector_store_settings` is unchanged in behavior by design (DD-3/DD-9):
an invalid stored `vector_store` record — extra key included, now — still
raises rather than falling back, because the wrong backend silently
reading the wrong on-disk data is the failure DD-3/DD-9 exists to
prevent. Confirmed this is safe to tighten: `vector_store` is
store-written only (`update_knowledge_settings`'s existing top-level-key
guard already refuses a `vector_store` key in the PUT body — see
`test_put_with_vector_store_key_rejected`), and its sole writer,
`save_vector_store_settings`, always calls
`VectorStoreSettings.model_dump_json()`, which can only emit exactly the
model's four declared fields — so no current writer (the v41 purge
included) can ever produce a stored record with an extra key. Checked
`tests/test_vectors_dispatch.py` and `tests/test_bench_vector_store.py`
for any construction of `VectorStoreSettings` with an out-of-schema key
— none exists, and both suites pass unchanged with `extra="forbid"`
applied.

## Verification

New parametrised test `TestKnowledgeSettingsAPI::test_put_nested_unknown_key_422s_and_names_the_key`
in `tests/test_db_api.py`: a nested unknown key under `embedding` and
under `chunking` returns 422 whose body contains the offending key name,
and a follow-up `GET` shows the stored record unchanged. New test
`TestInvalidStoredValue::test_stored_record_with_extra_key_falls_back_to_default_with_warning`
in `tests/test_knowledge_settings.py`: a stored `embedding`/`chunking`
record carrying an extra key still loads as defaults with a warning
naming the key, rather than raising. Both new tests were confirmed to
fail against the pre-fix code (via `git stash` of the settings.py change)
before the fix: the API test got 200 instead of 422, and the degrade
test's warning assertion failed because pre-fix, the extra key is
silently ignored and no warning is logged.

Full run: `PYTHON=.venv/bin/python bash scripts/run-tests.sh
tests/test_knowledge_settings.py tests/test_db_api.py
tests/test_vectors_dispatch.py tests/test_bench_vector_store.py -x
--timeout 60 -q` — 128 passed. `ruff check the_one/ tests/` — all checks
passed. `ruff format the_one/ tests/` — no changes needed beyond the
edited files (already formatted).

## Sign-Off
*(written at completion)*
**Reviewer**: Sonnet, batch review of squawk/turnaround-2026-09-15
**Verdict**: confirmed
**Commit**: ba46d62
