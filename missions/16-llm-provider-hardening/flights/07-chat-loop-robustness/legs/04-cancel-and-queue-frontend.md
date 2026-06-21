# Leg: cancel-and-queue-frontend

**Status**: completed
**Flight**: [Chat-loop Robustness & Control](../flight.md)

## Objective
Give the Chat UI a stop control wired to the backend `cancel` action, and allow the
operator to queue one message while a turn is running.

## Context
- Flight DD3 (frontend half) + DD4. Depends on **leg 3** (the `cancel` WS action +
  `cancelled` event must exist). Today `send()` (chat.js:719) early-returns on
  `isCurrentBusy()` and disables `sendBtn`; the backend already serializes successive
  sends via the session lock (proven: 5 rapid WS sends → 5 ordered responses).
- Design-review LOW: this file has prior input-stuck-disabled history; reconcile
  state across `done`, error, `onclose`/reconnect, session-switch. Resolved
  sub-decision: **cancel discards any pending queued message** ("stop" = stop
  everything).

## Inputs
- `the_one/interfaces/web/static/js/areas/chat.js`: `send()` (~:719),
  `isCurrentBusy()` (~:34), `inFlightSessions`, `showThinking`/`removeThinking`
  (~:490-498), `ws.onmessage` (~:831), `ws.onclose` (~:821), the `done` handler
  (~:1145), session-switch (~:939).
- Backend `cancel` action + `cancelled` event (from leg 3).

## Outputs
- A stop/cancel control visible during a turn; one queued send-while-thinking shown
  as pending; correct busy-state reconciliation.

## Acceptance Criteria
- [ ] A stop control is shown while a turn is in flight; clicking it sends
      `{action:"cancel"}` and clears the thinking/busy state.
- [ ] The `cancelled` event resets UI state exactly like `done` (hide thinking, clear
      `inFlightSessions[currentSessionId]`, re-enable send unless a session banner is
      shown), and removes any pending queued message.
- [ ] `send()` accepts ONE message while a turn runs: it is shown immediately as
      pending and sent so the backend queues it (lock-serialized); it starts after the
      current turn ends.
- [ ] A second attempt to queue (while one is already pending) is ignored / indicated
      as full (queue depth = 1).
- [ ] State stays consistent across `done`, the `handleSystem` error path,
      `onclose`/reconnect (which wipes `inFlightSessions`), and session-switch — no
      stuck-disabled input.

## Verification Steps
- Browser/manual (also covered by the leg-5 behavior test): start a turn, see the
  stop control; click it → turn stops, input re-enabled, partial text retained.
- Send A; while running send B → B shows pending, runs after A. Attempt C while busy
  → ignored.
- If the project has JS unit/DOM tests, add coverage; otherwise rely on the behavior
  test (leg 5) + HAT (leg 6).

## Implementation Guidance
1. Add a stop button in the input area, shown when `isCurrentBusy()`; on click,
   `ws.send(JSON.stringify({action:"cancel"}))` and optimistically clear thinking.
2. Handle `data.type === "cancelled"` in `ws.onmessage` — mirror the `done` reset
   path; drop the pending queued message.
3. Modify `send()`: if busy and no pending queued message, accept this one — render a
   pending indicator and `ws.send({message})` (backend lock queues it); set a
   `pendingQueued` flag. If busy and already pending, ignore.
4. On `done`/`cancelled`/session-switch/`onclose`, clear `pendingQueued` and
   reconcile `sendBtn.disabled` / thinking consistently.

## Edge Cases
- **onclose mid-turn wipes `inFlightSessions`**: ensure the one-slot guard and
  pending indicator don't get stuck after reconnect.
- **cancel with a pending message**: pending is discarded (documented decision).
- **Rapid double-click stop**: cancel is idempotent (backend no-ops on already-done).

## Files Affected
- `the_one/interfaces/web/static/js/areas/chat.js` — stop control, `cancelled`
  handler, one-slot queue in `send()`, state reconciliation.
- (CSS for the stop control if needed.)

---

## Post-Completion Checklist
- [x] All acceptance criteria verified
- [x] Tests passing (JS/DOM if present) / behavior test deferred to leg 5
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed` (commit deferred to flight-wide review)

---

## Design-Review Corrections (binding)
- **`cancelled` must mirror the FULL `done` reset** (chat.js:1145-1155), not a subset:
  `hideThinking()`, `finalizeStreamingBubble()`, `currentStreamingVisibility = null`,
  `delete inFlightSessions[currentSessionId]`, re-enable send (banner-gated), and
  `refreshSessionList()`. Omitting `finalizeStreamingBubble()` leaves the partial
  bubble stuck in streaming state.
- **One-slot queue must be PER-SESSION** (key by session id, like `inFlightSessions`)
  — NOT a single global flag. The session-switch path (chat.js:932-945) must restore
  the pending indicator if a queued message exists for the joined session.
- **Queue only when busy-but-healthy**: if `sessionBannerEl` is set / `inputEl.disabled`
  (health gate at :760), keep blocking — a queued send must not bypass
  `setSessionHealth`.
- **Stop control is reactive**: show/hide derived from `isCurrentBusy()` so `onclose`
  (which wipes `inFlightSessions` at :826) auto-hides it.
- **Discard pending on cancel idempotently**: clear the pending queued message on BOTH
  the optimistic stop-click AND arrival of the `cancelled` event.
