# Squawk 0056: `PUT /api/knowledge-settings` silently drops nested unknown keys

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-15
**Completed**: —

## Report

The route 422s an unknown top-level key, but an unknown key nested inside `embedding` or `chunking` (e.g. a typo of `overlap_chars`) is merged and then discarded by the Pydantic model, so the caller gets 200 and a silently unchanged setting. Fix: `model_config = ConfigDict(extra="forbid")` on `EmbeddingSettings` and `ChunkingSettings` (and `VectorStoreSettings` for consistency), with the resulting `ValidationError` surfacing as the route's existing 422 shape.

Logged from the Mission 24 Flight 2 debrief (2026-09-15).

## Evidence

- `the_one/knowledge/settings.py:48` (`EmbeddingSettings`), `:80` (`ChunkingSettings`) — no `model_config`, so Pydantic's default `extra="ignore"` applies.
- `the_one/interfaces/web/api.py:1614` `update_knowledge_settings` — merges the incoming dict then validates.
- Flight 2 flight log, "flight-end review, cycle 1": squawk candidate "nested unknown keys inside `embedding`/`chunking` are dropped rather than refused".

## Corrective Action
*(written at completion)*

## Verification
New parametrised test in `tests/test_db_api.py`: a nested unknown key under each section returns 422 and leaves the stored record unchanged; existing knowledge-settings tests green.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
