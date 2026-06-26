# Leg: queued-message-render

**Status**: ready
**Flight**: [HAT — Provider Chat Sweep](../flight.md)

## Objective
Fix two send-while-thinking (F07 DD4 one-slot queue) UX defects: (F09-02) the queued
message never renders as a real bubble in the live transcript, and (F09-03) "Stop"
during a queued state cancels the queued message instead of the running turn.

## Context
- HAT findings F09-02 (frontend) + F09-03 (backend); full diagnosis in the flight-log.
- The queue is frontend-optimistic + backend lock-serialization: the queued message is
  sent to the backend immediately and waits on `session_locks[session.id]`; it runs as a
  normal turn once the lock frees.
- **No persistence change**: `_save_session_to_db` (`app.py:1011-1029`) persists
  `session.agent.messages` wholesale; the queued user message is already saved. Both bugs
  are live-session UX only.
- Operator decisions: investigate the cancel path now and fold the fix in (so this leg
  carries a backend change); batch the release (hold 0.2.11 — see flight DD2).

## Inputs
- `the_one/interfaces/web/static/js/areas/chat.js` — `send()` (`:761`), `showPendingQueued`
  /`clearPendingQueued` (`:50-67`), the WS `done` handler (`:1227-1245`) and `cancelled`
  handler (`:1246-1264`).
- `the_one/interfaces/web/app.py` — WS receive/spawn (`:2107-2155`), cancel action
  (`:2096-2105`), `_session_inflight` (`:428`), `_process_and_broadcast` user echo
  (`:1430`).

## Outputs
- `chat.js`: on turn `done` with a pending queued message, the message renders as a real
  user bubble in correct order and the session stays in-flight for the queued turn.
- `app.py`: `_session_inflight` tracks a **set** of tasks per session; `cancel` cancels all
  not-done tasks for the session (running + queued).

## Acceptance Criteria
- [ ] **F09-02**: queuing a message while a turn runs, then letting the turn finish,
      results in the queued message appearing as a normal user bubble — positioned AFTER
      the finishing turn's response and BEFORE the queued turn's response — and the
      thinking indicator/Send-disabled state carries into the queued turn.
- [ ] No double-render of the queued message for the sender (backend still excludes the
      sender from the user echo; the sender renders it client-side), and other subscribers
      still render it exactly once (from the backend broadcast).
- [ ] **F09-03**: clicking Stop while a message is queued cancels the **running** turn
      (and discards the queued message) — "stop = stop everything" (DD4). The running turn
      does not continue to completion.
- [ ] Normal (non-queued) send + normal Stop behavior is unchanged.
- [ ] `make test-browser` (Playwright) passes; any new browser test uses DOM/structure
      assertions, NOT committed visual snapshots.

## Verification Steps
- Browser test (Playwright): drive a slow turn, queue a message, assert (a) the queued
  bubble renders after turn-1 response on `done`; (b) Stop during the queued state cancels
  the in-flight turn.
- Manual (installed 0.2.11 once built): queue-while-thinking shows the bubble; Stop during
  a queued state halts the running turn.

## Implementation Guidance

1. **F09-02 — render the dequeued message (chat.js `done` handler ~`:1234-1240`).**
   - Capture the pending text BEFORE deleting it:
     `var dequeued = currentSessionId ? pendingQueuedMessages[currentSessionId] : null;`
   - `delete pendingQueuedMessages[sid]; clearPendingQueued();` (as now).
   - If `dequeued`: `addMsg('user', dequeued, 'You');` then KEEP the session in-flight
     (the queued turn is starting): `inFlightSessions[sid] = true; sendBtn.disabled = true;
     updateStopControl(); showThinking();` — do NOT run the idle reset in this case.
   - If not `dequeued`: existing idle reset (`delete inFlightSessions[sid]`, enable Send,
     `updateStopControl`).
   - Rationale: the backend excludes the sender from the user echo (`app.py:1430`), so the
     sender owns the optimistic render — same contract as a normal send, just deferred to
     dequeue time so ordering is correct.

2. **F09-03 — cancel all session tasks (app.py).**
   - Change `_session_inflight` (`:428`) to `dict[str, set[asyncio.Task]]`.
   - Spawn site (`:2148`): `_session_inflight.setdefault(session.id, set()).add(task)`.
   - Done-callback (`:2151-2153`): discard the task from the set; delete the key when the
     set is empty.
   - Cancel action (`:2100-2105`): iterate the session's set and `cancel()` every
     not-done task (running + queued). Keep the no-session / empty no-op behavior.

## Edge Cases
- **Queued turn then cancelled**: after F09-02 renders the queued bubble and re-arms
  in-flight, a subsequent Stop must cancel the queued turn (now the running one) — covered
  by the F09-03 set-cancel.
- **Multiple subscribers**: only the sender lacks the backend echo; others render from the
  broadcast. The client-side render must remain sender-only (it already is — it runs in the
  sender's own `done` handler).
- **`/reset` or session switch with a pending queued message**: ensure no orphaned pending
  state renders into the wrong session (preserve existing per-session keying).

## Files Affected
- `the_one/interfaces/web/static/js/areas/chat.js` — `done` handler.
- `the_one/interfaces/web/app.py` — `_session_inflight` set, spawn, done-callback, cancel.
- `tests/` (browser/Playwright) — new/updated send-while-thinking coverage.

---

## Post-Completion Checklist
- [ ] Acceptance criteria verified (browser tests)
- [ ] Update flight-log.md (F09-02 + F09-03 → resolved)
- [ ] Set this leg's status to `completed` (after live re-verify on 0.2.11)
- [ ] Check off / add this leg in flight.md
- [ ] Live re-verify on the installed 0.2.11 build
- [ ] Commit (batched into the 0.2.11 release)
