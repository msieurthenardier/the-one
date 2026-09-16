# Squawk 0070: `supervised-per-entity-worker`: record when an instance takes a dedicated thread instead of the asyncio-native shape

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-16
**Completed**: —

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

*(written at completion)*

## Verification

*(written at completion)*

## Sign-Off

*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:

## Disposition

*(only for deferred or escalated squawks)*
