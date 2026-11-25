# Squawk 0412: "Replaced by the proposal below" shows before the new card does

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-24
**Completed**: 2026-11-25

## Report

Since squawk 0407, a replaced proposal's card folds live to "Withdrawn · <title>: replaced by the proposal below." The new card, though, is held until GleepGlorp's turn ends. So for the rest of the turn the line points at a card that is not there yet. It is brief and cosmetic, but the text is untrue while it shows (WCAG 1.3.1 and 3.3.2 flavour). The status announcement says only "Withdrawn: <title>." and gives no reason. Found by the Accessibility Reviewer of the 2026-11-24 squawk turnaround.

## Evidence
- `static/js/areas/chat/proposal-cards.js` `renderWithdrawn`: `reason = 'replaced by the proposal below.'` (line 283).
- The new card is held until the turn ends (`onChanged`, lines 568-584).

## Corrective Action
`renderWithdrawn` in `static/js/areas/chat/proposal-cards.js` now says "replaced by a newer proposal." (true whether or not the new card is shown yet). The two pins in `tests/browser/test_flow_chat_proposals.py` are updated. No other pin existed in `tests/`, `tests/behavior/` or `docs/`. The status announcement is unchanged.

## Verification
Done: the updated pinned strings pass in lane `gleepglorp-chat` (84 passed) and lane `chats` (178 passed). Planned check: either the wording holds true while the new card is held (for example "replaced by a newer proposal"), or the old card folds when the new card is shown. A test or a pinned string confirms the choice.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet), batch review of squawks 0411-0419; Accessibility Reviewer (Sonnet)
**Verdict**: confirmed
**Commit**: `squawk: turnaround 2026-11-25` on squawk/turnaround-2026-11-25
