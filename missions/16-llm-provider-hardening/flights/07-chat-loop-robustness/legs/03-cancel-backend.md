# Leg: cancel-backend

**Status**: completed
**Flight**: [Chat-loop Robustness & Control](../flight.md)

## Objective
Let the operator interrupt an in-flight turn: a WS `cancel` action aborts the current
turn's task, preserves the partial assistant output (marked interrupted), and emits a
`cancelled` event — releasing the session lock.

## Context
- Flight DD3 (HIGH from design review). `_inflight_tasks` is an unkeyed set
  (app.py:414); cancel needs a per-session current-task map. `_spawn_message_processing`
  holds `session_locks[session.id]` (app.py:442) and `_process_and_broadcast`
  re-raises `CancelledError` (app.py:455-458) → cancelling the task releases the lock.
- **HIGH nuance**: streamed text lives only in `_stream_response`'s local
  `accumulated_text` (core.py:368); the assistant `Message` is appended to
  `agent.messages` only when the loop yields it (core.py:275). If cancel fires
  mid-`llm.stream` (core.py:370) the partial text is otherwise lost and
  `_save_session_to_db` (encodes `agent.messages`, app.py:1005) has nothing to save.

## Inputs
- `the_one/interfaces/web/app.py`: WS handler (~:1898), `_spawn_message_processing`
  (~:427), `_inflight_tasks` (~:414), `_process_and_broadcast` (~:1374) incl.
  `_broadcast_chunk` (~:1433), `_save_session_to_db` (~:1005), `_send_to_session`,
  the `done` event (~:1615).
- `the_one/agent/core.py` `Message.assistant(...)`.

## Outputs
- WS `{action:"cancel"}` aborts the active turn; an interrupted assistant Message is
  persisted; a `cancelled` event is broadcast; the lock is freed; the UI can resume.

## Acceptance Criteria
- [ ] A per-session current-task map is maintained (set on spawn at ~app.py:2067,
      cleared in the done-callback); coexists with `_inflight_tasks` (shutdown still
      cancels all).
- [ ] WS handler handles `{action:"cancel"}`: looks up the session's in-flight task
      and `.cancel()`s it; no-ops gracefully if none / already finished.
- [ ] Partial streamed text is captured (accumulate in the `_broadcast_chunk`
      closure) and, on cancel, an interrupted `Message.assistant(content=<partial>)`
      is appended to `session.agent.messages` and saved via `_save_session_to_db`
      BEFORE the `CancelledError` propagates.
- [ ] `_process_and_broadcast` gains an `except asyncio.CancelledError:` block that
      persists partial output, emits a `cancelled` event (flat `{"type":"cancelled"}`,
      optional `parent_message_id`), then **re-raises** (preserving lock release at
      app.py:455-458).
- [ ] After cancel the session lock is released (a subsequent message on the same
      session is accepted).
- [ ] Tests: cancel **mid-LLM-stream** and cancel **mid-tool-call**, both asserting
      (a) the interrupted Message is in history/persisted, (b) `cancelled` emitted,
      (c) lock released (next message runs).

## Verification Steps
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_*websocket* tests/test_*session* tests/test_process_and_broadcast* -x --timeout 30`
- Integration test: drive `_process_and_broadcast` with a slow/mocked stream, cancel
  the task mid-stream, assert partial Message persisted + `cancelled` event + lock freed.
- Mid-tool-call variant with a slow stub tool.

## Implementation Guidance
1. Add `_session_inflight: dict[str, asyncio.Task]` (or reuse a keyed structure). On
   message spawn, record `session.id -> task`; clear in the done-callback.
2. In the WS receive loop, add an `action == "cancel"` branch that finds the task for
   the bound session and cancels it (guard None / done).
3. In `_process_and_broadcast`, have `_broadcast_chunk` also append to a
   `partial_text` accumulator (nonlocal). Add `except asyncio.CancelledError:` that
   appends `Message.assistant(content=partial_text)` (mark interrupted, e.g. metadata
   or a content suffix) to `session.agent.messages`, `await _save_session_to_db`,
   `await _send_to_session(... {"type":"cancelled"})`, then `raise`.
4. Frontend wiring is leg 4 — only define the `cancelled` event shape here.

## Edge Cases
- **Cancel after natural completion**: task already discarded → no-op.
- **Cancel mid-tool-call**: `CancelledError` unwinds through `_execute_tool`'s
  `finally` (ContextVar reset); partial assistant text may be empty — persist an
  empty/short interrupted marker or skip if nothing streamed (decide + document).
- **Re-raise required**: do NOT swallow `CancelledError` (would strand the lock
  semantics and the task-done bookkeeping).

## Files Affected
- `the_one/interfaces/web/app.py` — per-session task map, `cancel` action, partial-output
  persistence + `cancelled` event in `_process_and_broadcast`.
- `tests/` — cancel mid-stream + mid-tool-call.

---

## Post-Completion Checklist
- [x] All acceptance criteria verified
- [x] Tests passing (14/14 in tests/test_cancel.py)
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed` (commit deferred to flight-wide review)

---

## Design-Review Corrections (binding) — leg was "needs rework"
- **[HIGH] `Message` has NO `metadata` field** (verified `llm/base.py:65-177`;
  `Message.assistant()` takes only `content, tool_calls, usage, visibility`). Do NOT
  invent a metadata field (would need codec + migration). **Mark interrupted via a
  content suffix**: append `"\n\n_[interrupted]_"` to the captured partial text.
- **[HIGH] The `except CancelledError` also fires on SHUTDOWN** (lifespan cancels all
  `_inflight_tasks` at app.py:235, and `_spawn_message_processing` re-raises at :455).
  So the persist + `cancelled`-emit must be **best-effort**: wrap the
  `_save_session_to_db` and `_send_to_session` in `contextlib.suppress(Exception)` so
  shutdown teardown (closing DB / sockets) can't turn a clean cancel into an error,
  then re-raise the `CancelledError`.
- **Handler placement**: add `except asyncio.CancelledError:` as a SIBLING of the
  existing `except Exception` at `app.py:1567` (CancelledError is `BaseException`, so
  it is NOT caught by `:1567`). It persists partial output, emits `cancelled`, then
  `raise`. (The re-raise at :455-458 is in the WRAPPER `_spawn_message_processing`,
  not `_process_and_broadcast` — the recon row said as much; the new handler is the
  one inside `_process_and_broadcast`.)
- **Persist only if non-empty**: if no assistant text streamed before cancel (e.g.
  cancel landed mid-tool-call with no preamble), skip the synthetic message and just
  emit `cancelled`.
- **Per-session task-map race**: with leg 4's queue-depth-1, two tasks can coexist on
  one session (running + queued-behind-the-lock). The map holds the RUNNING task; the
  done-callback clears the entry only if it still points at THIS task
  (`if _session_inflight.get(sid) is task: del ...`). Cancel snapshots the ref and
  guards: `t = _session_inflight.get(sid); if t and not t.done(): t.cancel()`.
- **`cancelled` event scope**: each WS connection is bound to one session and the
  frontend sends `cancel` for the current session, so `{"type":"cancelled"}` (no
  session_id, matching `done`) is sufficient; if you carry the persisted partial
  message id, leg 4 can reconcile the streaming bubble (nice-to-have).
- **Add a comment/test** asserting `except Exception` at :1567 does NOT catch
  `CancelledError` (a future refactor to `except BaseException` would silently break
  cancel's lock release).
