# Squawk 0411: A server-pushed proposal-card fold drops focus to the page

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-24
**Completed**: 2026-11-25

## Report

A server-pushed change of state rebuilds a proposal card's body with no focusable element, for example a replacement (squawk 0407) or a target that is gone. If keyboard focus was on that card's Approve or Dismiss button, it falls to `<body>` (WCAG 2.4.3). The case is reachable: during an agent turn the buttons are only `aria-disabled`, so they stay focusable. The gap predates squawk 0407, which made the replacement fold live and so more likely. Found by the Accessibility Reviewer of the 2026-11-24 squawk turnaround.

## Evidence
- `static/js/areas/chat/proposal-cards.js` `build(e)` (line 410): `e.body.replaceChildren.apply(e.body, kids)` (line 426) with no check of `document.activeElement`.
- The click paths already move focus with `App.focusAfter.restore(token, focusTarget(...))` (lines 653-687). The pushed path has no equivalent.

## Corrective Action
In `static/js/areas/chat/proposal-cards.js` `build(e)`: before `replaceChildren`, record whether `document.activeElement` is inside `e.body`. After the rebuild, if it was and the new body has no focusable element (button, link, input, select, textarea, `[tabindex]`), focus `ctx.composer.input`. The click paths still move focus afterwards through `App.focusAfter.restore`, which overrides this. New test `test_a_pushed_fold_of_the_focused_card_moves_focus_off_the_body` in `tests/browser/test_flow_chat_proposals.py`.

## Verification
Done: the new test was falsified (fix removed: it failed with `activeElement` BODY; fix restored: passes). Lane `gleepglorp-chat` 84 passed, lane `chats` 178 passed, static guards 396 passed, ruff check and format clean on the test file. Planned check: a browser test focuses the old card's Approve button. A replacement then arrives (the squawk 0407 test setup), and focus is on the composer input or the new card, not on `<body>`.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet; the batch touched connector-token and CI token surfaces), batch review of squawks 0411-0419; Accessibility Reviewer (Sonnet) for 0411, 0412, 0413, 0414 and 0419
**Verdict**: confirmed. The case where the new body still has a button, and the `[tabindex]` selector breadth, are logged as squawk 0421.
**Commit**: `squawk: turnaround 2026-11-25` on squawk/turnaround-2026-11-25
