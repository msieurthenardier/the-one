# Leg: queued-message-render

**Status**: completed
**Flight**: [HAT — Provider Chat Sweep](../flight.md)

> **Completed (2026-06-27, shipping in 0.2.12).** Client-hold queue redesign:
> pinned cancellable chip (F09-04), render-on-dequeue (F09-02), Stop cancels the
> running turn (F09-03). Verified live on the dev instance (branch code) by the
> operator; 4 browser tests green. Ships in 0.2.12.

## Objective
Redesign the send-while-thinking (F07 DD4 one-slot queue) UX to a **client-hold** model
that fixes three HAT findings: (F09-02) the queued message never renders as a real bubble;
(F09-03) "Stop" during a queued state cancels the queued message instead of the running
turn; (F09-04) the queued message scrolls away with the chat and can't be cancelled.

**Client-hold model (chosen):** the frontend HOLDS the queued message locally and does NOT
send it to the backend until the in-flight turn's `done` arrives. It shows as a **pinned
chip** above the composer (outside the scroll region) with a **cancel (×)**. On `done` the
held message is sent via the normal send path (which renders the real bubble). This makes
cancel trivial/correct (nothing was sent), keeps the chip pinned, subsumes F09-02's render,
and means no queued backend task exists during the turn (so F09-03 can't arise — its
set-based cancel is retained as a robustness backstop).

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
- [ ] **F09-04 (pin)**: a queued message renders as a chip pinned above the composer
      (outside the scrolling message list) and does NOT scroll with the conversation.
- [ ] **F09-04 (cancel)**: the pinned chip has a cancel (×) control; activating it removes
      the chip and discards the held message — and because nothing was sent to the backend,
      no turn runs for it. Keyboard-accessible (focusable, Enter/Space).
- [ ] **F09-02 (render)**: when the in-flight turn finishes, the held message is sent and
      appears as a normal user bubble — positioned AFTER the finishing turn's response and
      BEFORE the queued turn's response — with the thinking/Send-disabled state carrying
      into the queued turn.
- [ ] **F09-03**: clicking Stop while a message is queued cancels the **running** turn; the
      held queued message is discarded (chip removed). The running turn does not continue to
      completion. (Backend `_session_inflight` set-cancel retained.)
- [ ] One user bubble per queued message (no double render); the held message is sent
      exactly once on dequeue via the normal send path.
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

> **Note:** this supersedes the earlier (committed, unreleased) F09-02 approach
> (done-handler manual render + immediate `ws.send` at queue time). Rework the frontend to
> client-hold as below; the F09-03 backend change (step 2) stays.

1. **F09-04 + F09-02 — client-hold + pinned cancellable chip (chat.js).**
   - In `send()` (`:761`) queued branch: do NOT `ws.send` (remove `:778`). Just store the
     held text per session (`pendingQueuedMessages[sid] = text`), clear the input, render the
     pinned chip. Keep the one-slot guard (ignore a second queue while one is held).
   - Rework `showPendingQueued`/`clearPendingQueued` (`:50-67`) so the chip renders in a
     pinned container ABOVE the composer, NOT appended to `messagesEl` (that is the
     scroll-away bug). Add minimal HTML/CSS for the pinned chip region; the chip shows the
     text + a cancel button. Cancel must be keyboard-accessible (focusable, Enter/Space).
   - Cancel handler: `delete pendingQueuedMessages[sid]; clearPendingQueued();` — purely
     local; nothing was sent. Also clear on session switch and `/reset`.
   - On turn `done` (`:1227`): if a held message exists, clear the chip and send it via the
     NORMAL send path (`addMsg('user', held, 'You')` + `ws.send({message: held})` +
     in-flight/showThinking/disable-Send; factor a helper if cleaner). Renders the bubble in
     correct order and starts the queued turn. If none held, normal idle reset.
   - Net: the held message reaches the backend only after the prior turn ends, via the same
     path as a normal send, so the sender's optimistic render + backend sender-exclusion
     (`app.py:1430`) already align; no backend echo change needed.

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
