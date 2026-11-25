# Squawk 0411: A server-pushed proposal-card fold drops focus to the page

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-24
**Completed**: —

## Report

A server-pushed change of state rebuilds a proposal card's body with no focusable element, for example a replacement (squawk 0407) or a target that is gone. If keyboard focus was on that card's Approve or Dismiss button, it falls to `<body>` (WCAG 2.4.3). The case is reachable: during an agent turn the buttons are only `aria-disabled`, so they stay focusable. The gap predates squawk 0407, which made the replacement fold live and so more likely. Found by the Accessibility Reviewer of the 2026-11-24 squawk turnaround.

## Evidence
- `static/js/areas/chat/proposal-cards.js` `build(e)` (line 410): `e.body.replaceChildren.apply(e.body, kids)` (line 426) with no check of `document.activeElement`.
- The click paths already move focus with `App.focusAfter.restore(token, focusTarget(...))` (lines 653-687). The pushed path has no equivalent.

## Corrective Action
*(written at completion)*

## Verification
A browser test focuses the old card's Approve button. A replacement then arrives (the squawk 0407 test setup), and focus is on the composer input or the new card, not on `<body>`.
