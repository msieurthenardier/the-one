# Squawk 0055: Embedding warm-up `create_task` handles are dropped

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-15
**Completed**: 2026-09-15

## Report

Two call sites fire the embedding-backend warm-up with `asyncio.create_task(...)` and discard the returned `Task`. The stdlib documents that an unreferenced task can be garbage-collected mid-flight. Every other background task in the codebase holds its handle (`_web_session_reaper_task`, `_chat_history_purge_task`, `_catalog_refresh_task`, the MCP pool reaper). Worst case today is a lost warm-up and a slower first embed; the fix is to keep the handle (a module-level set or attribute, with a done-callback that discards it), matching the existing pattern.

Logged from the Mission 24 Flight 2 debrief (2026-09-15).

## Evidence

- `the_one/interfaces/web/app.py:338` — `asyncio.create_task(_warm_up_embedding_backend())`, result unassigned.
- `the_one/interfaces/web/api.py:1425` — same call in `create_knowledge_base`.
- Contrast: `the_one/interfaces/web/app.py` lifespan holds `_web_session_reaper_task` etc.

## Corrective Action

Added a module-level `_tasks: set[asyncio.Task[None]]` holder and a
`schedule_warm_up()` helper in `the_one/embeddings/__init__.py`, next to
`warm_up()`. `schedule_warm_up()` creates the task, adds it to `_tasks`,
and registers `task.add_done_callback(_tasks.discard)` — mirroring the
`_inflight_tasks` pattern already used in
`the_one/interfaces/web/app.py`. `warm_up()`'s own `_warming`-guard
idempotency is untouched; `schedule_warm_up()` is purely a handle-holding
wrapper around it.

Both call sites now go through the shared helper instead of a bare
`asyncio.create_task(...)`:

- `the_one/interfaces/web/app.py` (lifespan, KB-count gate): imports
  `schedule_warm_up as _schedule_embedding_warm_up` and calls
  `_schedule_embedding_warm_up()`.
- `the_one/interfaces/web/api.py` (`create_knowledge_base`): same import
  rename and call, so a KB-create firing the warm-up more than once per
  process is still safe — each call adds its own task to the shared set.

A comment at the `_tasks` declaration cites the stdlib `create_task` note
on unreferenced tasks being eligible for GC and this squawk (0055).

## Verification

Added `TestSingleton.test_schedule_warm_up_holds_the_task_handle` in
`tests/test_embeddings.py`: calls `schedule_warm_up()`, asserts the
returned task is present in `embeddings._tasks` immediately, awaits it,
then asserts it has been discarded from the set (via the done-callback)
and that the loader ran exactly once.

`PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_embeddings.py tests/test_lifespan.py tests/test_db_api.py -x --timeout 60 -q`
→ 110 passed (the existing `test_lifespan.py` warm-up-at-startup tests
and `test_db_api.py` KB-create tests are unaffected by the call-site
rename). `ruff check the_one/ tests/` and `ruff format the_one/ tests/`
both clean.

## Sign-Off
*(written at completion)*
**Reviewer**: Sonnet, batch review of squawk/turnaround-2026-09-15
**Verdict**: confirmed
**Commit**: _(recorded in the follow-up commit)_
