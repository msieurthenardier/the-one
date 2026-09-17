# Squawk 0070: `supervised-per-entity-worker`: record when an instance takes a dedicated thread instead of the asyncio-native shape

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-16
**Completed**: 2026-09-17

## Report

`WatchManager` is the convention's third instance and the first to run its
unit of work on a dedicated daemon thread rather than an asyncio task
(justified: `awatch` blocks a worker of the shared 40-token `anyio`
limiter; `asyncio.to_thread` would pin the default executor the indexer
uses). The reason is in `watcher.py`'s docstring and the `agents.md`
`WatchManager` block, but the convention paragraph itself does not say when
a future instance should choose a thread — a fourth instance would decide by
nearest precedent. Add the criterion to the convention.

## Evidence

- `the_one/agents.md:582` — `### \`supervised-per-entity-worker\`` (the generic paragraph and three citations; no thread-vs-task criterion)
- `the_one/knowledge/watcher.py` module docstring, "Dedicated thread, not `awatch`"
- Flight 4 debrief, Technical "a second threading model"; Recommendation 4

## Corrective Action

Added a decision-criterion paragraph to the `supervised-per-entity-worker`
convention section in `the_one/agents.md`, inserted between the existing
generic descriptive paragraph and the (unchanged) `Citations:` line:

> Asyncio-native is the default shape for the worker's unit of work. A
> dedicated daemon thread is warranted only when that unit of work is a
> blocking call that would otherwise occupy a *shared* pool for its whole
> lifetime — a subscription or stream that blocks indefinitely, not a
> bounded piece of CPU work — naming which pool it would have pinned:
> `anyio`'s default thread limiter (which Starlette's `run_in_threadpool`
> and the MCP stack draw from) or `asyncio.to_thread`'s default executor
> (which the indexer's embedding and walk calls use). An instance that
> takes a thread on this basis must also state a cap on concurrent
> entities and a visible degrade past it.

No other section of `agents.md` was touched (in particular, the
`WatchManager` block further down the file, which already carries the
per-instance rationale, is untouched) and `watcher.py` was not edited.

## Verification

This is a markdown-only documentation change — no test run applies; ruff
(`make lint`) does not cover `.md` files, so it was not run.

**Citations unchanged**: `git diff the_one/agents.md` shows exactly two
new lines (the added paragraph plus its trailing blank line) inserted
before the `Citations:` line; the `Citations:` line itself (naming
`ConnectorManager`, `IndexingManager`, and `WatchManager` as the section's
three existing instances) is byte-for-byte unchanged in the diff.

**Claims checked against the cited code/docs, not asserted from memory**:

- "`anyio`'s default thread limiter ... which Starlette's
  `run_in_threadpool` and the MCP stack draw from" — matches
  `the_one/knowledge/watcher.py`'s module docstring verbatim ("Dedicated
  thread, not `awatch`" paragraph: "`awatch` blocks one worker of
  `anyio`'s shared default limiter ... the same pool Starlette's
  `run_in_threadpool` and the MCP stack draw from") and the flight spec
  (`missions/24-knowledge-bases/flights/04-change-monitoring/flight.md`
  lines 82-84, identical wording). The flight log's probe P18
  (`missions/24-knowledge-bases/flights/04-change-monitoring/flight-log.md:559`)
  measured `anyio.to_thread.current_default_thread_limiter().total_tokens`
  directly at 40 on the probe host, "shared with Starlette's
  `run_in_threadpool`" — I did not assert the 40-token figure myself in
  the added text (it already appears in the cited `WatchManager` citation
  and flight docs), only that the pool is shared and named.
- "`asyncio.to_thread`'s default executor ... which the indexer's
  embedding and walk calls use" — confirmed directly in
  `the_one/knowledge/manager.py`: `backend = await
  asyncio.to_thread(self._backend_factory)` (embedding backend
  construction, line 347), `result = await asyncio.to_thread(walk_folder,
  ...)` (walk, line 398), and `digest = await
  asyncio.to_thread(content_hash, ...)` (content hashing, line 446) — all
  three are `asyncio.to_thread` calls inside `IndexingManager`, i.e. the
  indexer's embedding and walk calls.
- "a cap on concurrent entities and a visible degrade past it" — matches
  `WatchManager`'s own instance: `the_one/knowledge/watcher.py` names
  `MAX_WATCHED_FOLDERS = 64` (DD-1's cap) and a documented degrade for a
  folder past the cap (an entry created without a task/thread), so the
  criterion's requirement is exactly what the one existing thread-based
  instance already does — nothing new is being demanded that the
  precedent doesn't already satisfy.

## Sign-Off

**Reviewer**: batch Reviewer agent (Haiku tier — the diff is documentation, crew prompts and a test comment; no security-sensitive surface, per `.flightops/agent-crews/leg-execution.md`)
**Verdict**: confirmed
**Commit**: (recorded in the follow-up commit on `squawk/turnaround-2026-09-17`)

## Disposition

*(only for deferred or escalated squawks)*
