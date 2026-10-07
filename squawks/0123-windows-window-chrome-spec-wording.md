# Squawk 0123: Wording fixes for `windows-window-chrome` from its Flight 5 close-gate run

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-06
**Completed**: 2026-10-06

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

Wording only, in `tests/behavior/windows-window-chrome.md`, with a `Revised` line and no
expectation changed:
- **Step 7:** clicks Light, then Dark, and polls after the last click (step 6 ends on Dark);
  when the outcome (dark survives the hard stop) is observed but the flush is not, the step is
  judged on the outcome and the report says so (INCONCLUSIVE only when the outcome is not
  dark either); its splash bound is the frame mean or a body patch; the x button's
  coordinates are formulas only.
- **Steps 1 and 7:** `no-window` and `covered_by_tree` frames are not judged; step 1's
  "creates none" is "the run creates none" (the app writes `window-chrome.json` at launch);
  both series are 300 frames.
- **Step 5:** "close to" is stated as within +-8 per channel.
- **Step 4:** the border sample is anchored on the left edge of `frame_bounds`.
- **Step 3:** at least one `capture --window` while the palette is open is required.
- **Step 9:** minimize is judged on the outer rect (the `visible` flag stays True); own
  window A is re-shown as setup before a `front` more than about 8 minutes after step 1 (or
  shown with a longer `--seconds`); step 10's x button also uses the formula.
No item was skipped.

Commit: pending the Flight 6 legs 1-3 commit.

## Verification

- Every edited step re-read against `runs/2026-10-06-20-06-24.md`: every expectation the run
  judged still reads the same (step 7's intent, the dark preference surviving a hard stop and
  a relaunch with no light frame, is unchanged).

## Sign-Off

**Reviewer**: Developer agent, Mission 25 Flight 6 leg 3 (the flight-end review confirms)
**Verdict**: confirmed
**Commit**: pending the Flight 6 legs 1-3 commit
