# Flight Log: Proposals and approval

**Flight**: [Proposals and approval](flight.md)

## Summary
Planning. Branch `flight/02-proposals-and-approval` from `main` at `b3ee1b91`
(after the Flight 1 merge, #380).

### Flight Director Notes
- Planning, 2026-11-19. Operator decisions:
  - **Scope:** agents with their rules and routines in this flight; the other
    kinds come with form filling later.
  - **Approve** starts GleepGlorp's next turn.
  - **Eval method:** adopted as outlined (flight DD12).
  - **qwen3-4b** is measured only.
  - **Board choices:** card A, approval B, editor note A, states as drawn.
- Carried from the Flight 1 debrief:
  - The "grep tests for exact-dict pins" rule was added to the
    `leg-execution.md` Fix Review Issues prompt during planning.
  - The quiet-host gate re-measure is still owed (squawk 0389) and is taken at
    this flight's first full gate that starts on a quiet host.
  - Squawk 0385 is still open, outside this flight.
- **Design review, cycle 1** (Architect, Opus): approve with changes. Five
  high issues:
  - the compare and the save can't share a transaction;
  - no per-result taint marker is possible without the frozen `core.py`;
  - the view summaries are writable by agents;
  - Leg 2 was too coarse;
  - Leg 3 was too coarse.

  The medium issues covered the error surface, the PUT's omit traps, names to
  ids, the marked-message primitive and its seam, a busy 409, one open
  proposal per chat, the routine flag carried through, the secret guard
  helpers, and the editor event. All were folded in, and the legs grew from 7
  to 10.
- **Design review, cycle 2** (Architect, Opus): approve with changes. No high
  issues. The medium issues were:
  - Approve would add the approval message twice; the prompt now rides on
    `spawn_turn`;
  - the status transitions were inconsistent; Try again, double Approve and
    `failed` versus `applied` are now defined;
  - what `override` covers; untouched-field races are now re-merged and never
    shown as stale;
  - the evals' copy of the taint rule; there is now one predicate,
    `is_trusted_result`.

  The low items were:
  - a stale DD reference;
  - the rule repository's `on_commit`;
  - `session_joined` being synchronous;
  - purging a chat's messages;
  - the secret guard covering every string;
  - "pure" corrected to "shared".

  All were applied. That was the second and last review cycle, so the spec now
  goes to the operator.
