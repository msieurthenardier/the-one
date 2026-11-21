# Squawk 0394: One worked sequence of the GleepGlorp fill lifecycle in agents.md

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-21
**Completed**: —

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
*(written at completion)*

## Verification
The section exists and links the per-leg sections. Every name it cites exists in the code (grep).
