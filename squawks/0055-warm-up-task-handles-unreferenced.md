# Squawk 0055: Embedding warm-up `create_task` handles are dropped

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-15
**Completed**: —

## Report

Two call sites fire the embedding-backend warm-up with `asyncio.create_task(...)` and discard the returned `Task`. The stdlib documents that an unreferenced task can be garbage-collected mid-flight. Every other background task in the codebase holds its handle (`_web_session_reaper_task`, `_chat_history_purge_task`, `_catalog_refresh_task`, the MCP pool reaper). Worst case today is a lost warm-up and a slower first embed; the fix is to keep the handle (a module-level set or attribute, with a done-callback that discards it), matching the existing pattern.

Logged from the Mission 24 Flight 2 debrief (2026-09-15).

## Evidence

- `the_one/interfaces/web/app.py:338` — `asyncio.create_task(_warm_up_embedding_backend())`, result unassigned.
- `the_one/interfaces/web/api.py:1425` — same call in `create_knowledge_base`.
- Contrast: `the_one/interfaces/web/app.py` lifespan holds `_web_session_reaper_task` etc.

## Corrective Action
*(written at completion)*

## Verification
A test asserting the warm-up task is referenced (e.g. present in the holder) after the trigger; `tests/test_lifespan.py` and `tests/test_db_api.py` KB-create tests still green; `make test-unit` green.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
