# Squawk 0123: Wording fixes for `windows-window-chrome` from its Flight 5 close-gate run

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-06
**Completed**: —

## Report

The close-gate run of `windows-window-chrome` passed 11 of 11 checkpoints. Its Executor
and Validator flagged wording that one of them had to work out, or that a stricter
reading could misjudge. These are clarifications only:
- **Step 7, the flush poll.**
  - The step clicks Dark and waits for the profile's leveldb log to move. But step 6
    ends on Dark, so the click writes nothing and the poll can never move.
  - Click Light, then Dark, and poll after the last change.
  - Say what to judge when the outcome (the preference survives a hard stop) is
    observed but the flush is not.
- **Steps 1 and 7, the splash bounds.** "Every channel above 220" and "below 60" fail
  literally on rounded-corner pixels and on the splash's own content. Judge the frame
  mean (or a body patch), and say that `no-window` and `covered_by_tree` frames are not
  judged.
- **Step 5.** State the "close to" tolerance (±8 per channel).
- **Step 4.** Anchor the border sample on the helper's `frame_bounds`.
- **Steps 3 and 9.** Require at least one saved capture while the palette is open.
- **Step 9:**
  - judge minimize on the outer rect (the helper's `visible` flag stays True);
  - re-show own window A as setup before any `front` more than about 8 minutes after
    step 1, or show it with a longer `--seconds`;
  - give the x, minimize and caption coordinates as frame-bound formulas only.
- **Step 1:**
  - "Create no `window-chrome.json`" means the run creates none (the app writes one at
    launch);
  - the 200-frame series left 35 frames of margin; consider 300.

## Evidence

The Orchestrator Notes and Closing Summaries in
`tests/behavior/windows-window-chrome/runs/2026-10-06-20-06-24.md`.

## Corrective Action

*(written at completion)*

Edit only the named steps and Preconditions text in `tests/behavior/windows-window-chrome.md`,
and add a Revised line. Do not change any expectation's meaning.

## Verification

Re-read each edited step against the run log: every expectation the run judged still
reads the same.

## Sign-Off

*(written at completion)*
