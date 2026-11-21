# Squawk 0394: One worked sequence of the GleepGlorp fill lifecycle in agents.md

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-21
**Completed**: 2026-11-21

## Report
`the_one/agents.md` describes fills leg by leg ("GleepGlorp fills, server (M36 F3 L5)" and
"GleepGlorp fills, browser (M36 F3 L6)"). It has no single worked sequence a Flight 4 reader can start
from. Add one short "Fill lifecycle" section that walks the sequence step by step:

1. `fill_form` records the fill.
2. The `fill_requested` frame reaches the screen.
3. Only the drawer that owns the turn (`ownsTurn`) queues it.
4. The drawer claims the fill (a token and a 120 s lease) and checks for Chats or a dialog.
5. It navigates, then `whenSettled`.
6. It writes unsaved edits only (the allowlist, all-or-nothing availability, operator-dirty fields
   kept, the model group last).
7. It reports the outcome.

The section also says why this differs from a proposal's single approve. Link the per-leg sections
rather than repeating them. Raised in the Flight 3 debrief.

## Evidence
- `the_one/agents.md`: the per-leg fill sections only.
- `the_one/gleepglorp/fill/`, `interfaces/web/gleepglorp_fills_api.py`,
  `static/js/gleepglorp-drawer/fill.js`, `areas/studio/agent-editor-fill.js`.

## Corrective Action
Added "### Fill lifecycle (M36 F3)" to `the_one/agents.md`, immediately before "GleepGlorp fills, server (M36 F3 L5)" and mirroring "Proposal lifecycle (M36 F2)": the seven steps, the statuses and who moves them (including `replaced`, lease expiry and Fill now), and why a fill differs from a proposal's Approve. It links both per-leg sections by exact heading. No difference from the squawk found; the removed "Show the form" button is not mentioned.

## Verification
The section exists and links the per-leg sections. Every name it cites exists in the code (grep).

Checked against code: `CLAIM_LEASE_SECONDS = 120` and `STATUSES` (fill/store.py), `NEEDS_PAGE` (fill/tool.py), the `not_applying` 409 (gleepglorp_fills_api.py), `ownsTurn` / `onFillRequested` (send.js, turn-frames.js, gleepglorp-drawer/chat.js), reason codes `in_chats`/`stay`/`target_gone`/`editor_unavailable` and `isDeciding` (gleepglorp-drawer/fill.js), `whenSettled` and `ALLOWED` (agent-editor-fill.js). Headings named all exist in agents.md.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet; the security tier, since the batch changed the shell-write hook and CLAUDE.md's safety rules), batch review of squawks 0368, 0379, 0384, 0385, 0391-0397
**Verdict**: confirmed
**Commit**: `squawk: turnaround 2026-11-21` on squawk/turnaround-2026-11-21
