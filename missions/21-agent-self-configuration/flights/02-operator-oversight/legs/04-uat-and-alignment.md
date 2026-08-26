# Leg: uat-and-alignment (HAT)

**Status**: completed
**Flight**: [Operator Oversight](../flight.md)

## Objective

A guided human acceptance test of Flight 2's operator-oversight UX: the operator
drives the approval-mode toggle, the pending queue + count, approve (clean and
via the staleness re-confirm), dismiss, the revision history, and restore
(including the original value) against a real running instance — with the Flight
Director fixing any look-and-feel issues inline.

## Nature

Interactive HAT — **not** autonomously executed. The Flight Director stands up an
isolated scratch instance and guides the operator through each step one at a
time; the operator performs the action in their browser and reports what they
see. Fixes are applied inline (look-and-feel → inline; new behavior → promoted to
a scoped design review per the fix-vs-feature gate).

## Preconditions (operator-confirmed before starting)

- **Isolated instance only.** A scratch instance on **port 8485** (never 8484 —
  the operator's production instance) with a **scratch data dir** under
  `/tmp/the-one-hat/…` (never the operator's real data dir). Dev mode on so a
  **mock LLM provider** is available (no real API key needed).
- The Flight Director seeds the scratch data dir before launch: mock provider, a
  test agent (`hat-agent`) with a known original description/prompt, the
  self-configuration surface enabled, approval mode ON, and a populated queue +
  applied history (including an original value to restore to).
- The operator launches the scratch app themselves (so the credential-gate
  handoff authenticates the browser automatically) and reports readiness.

## Acceptance Criteria (verification steps)

Each is an operator-observed check; the Flight Director confirms before advancing.

- [x] AC1 — On the test agent's **Self-Configuration** tab, the approval-mode
      control shows ON; toggling it OFF then ON posts immediately and the status
      line reflects the change (no Studio Save needed).
- [x] AC2 — A **pending count** and a **queue** of pending revisions are shown,
      each card showing the field and its before→after values.
- [x] AC3 — **Approve (clean):** approving a pending revision whose field has not
      drifted applies it in one click; the card leaves the queue and the count
      decrements; the value is persisted (visible on reload / a fresh view).
- [x] AC4 — **Staleness + override:** for a pending revision whose field was
      changed after it was queued, Approve surfaces a **current-vs-proposed**
      panel (does not silently overwrite); an explicit **override/confirm**
      applies it.
- [x] AC5 — **Dismiss:** dismissing a pending revision removes it from the queue
      without changing the field; the count decrements.
- [x] AC6 — **History + restore:** the revision history lists past revisions
      (field, before→after, timestamp, source, status); a **Restore** control
      returns the field to an earlier value, and the **original** (pre-first-
      revision) value is restorable; the restore appears as a new history entry.
- [x] AC7 — **Approval OFF → direct:** with approval mode off, a revision applies
      directly (no queue) and still appears in the history as `applied`.
- [x] AC8 — **Accessibility spot-check:** the new controls are keyboard-operable
      and focus lands sensibly after each action (not bounced to page top).
- [x] AC9 — The operator is satisfied with the look-and-feel; any inline fixes
      made during the session are recorded in the flight log (and, if code
      changed, committed in a follow-up commit on the flight branch — no amend).

## Notes

- The "agent genuinely self-revises via chat into the queue" end-to-end path is
  covered by Flight 1's behavior test + Leg 2 unit tests; it can optionally be
  demonstrated live by scripting the mock provider, but the queue/history are
  seeded so the operator-facing flows are exercised deterministically.
- Teardown: stop the scratch instance and remove the scratch data dir at the end.

---

## Post-Completion Checklist

- [x] All AC steps walked and confirmed (or issues fixed inline + re-confirmed)
- [x] Flight log updated with the HAT session outcome and any inline fixes
- [ ] Scratch instance stopped, scratch data dir removed
- [ ] Set this leg's status to `completed`; check it off in flight.md
- [ ] If code changed during the HAT: a follow-up commit on the flight branch
