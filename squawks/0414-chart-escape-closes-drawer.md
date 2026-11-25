# Squawk 0414: Esc in a chart closes the GleepGlorp drawer too

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-24
**Completed**: 2026-11-25

## Report

When a chart's keyboard tooltip is showing inside the drawer, pressing Esc hides the tooltip and then also closes the whole drawer. The chart handler returns before `preventDefault`, so the drawer's Esc handler, which honours `defaultPrevented`, sees an unhandled Esc. Found by the 2026-11-24 routine maintenance (Accessibility Reviewer).

## Evidence
- `static/js/ui/chart.js` plot keydown (about line 350): `else if (key === 'Escape') { hide(); return; }`. The `ev.preventDefault()` below it is skipped.
- `static/js/ui/drawer.js` `onKeydown` (about line 152): `if (e.key !== 'Escape' || e.defaultPrevented || root.hidden) return;`.

## Corrective Action
`static/js/ui/chart.js` plot keydown: on Esc, if no tooltip is showing (`active < 0`) the handler returns untouched so the key reaches an enclosing handler (the drawer); if one is showing it hides it and falls through to the existing `ev.preventDefault()`, so the drawer's `defaultPrevented` check leaves the drawer open. No `stopPropagation` (the drawer's own check is the project pattern). New contract test `test_escape_claims_the_key_only_while_the_tooltip_shows` in `tests/browser/test_ui_chart_contract.py` uses a container Esc listener standing in for the drawer.

## Verification
A contract test: with a chart in the drawer, the tooltip open and focus on the plot, Esc hides the tooltip and the drawer stays open. A second Esc, with no tooltip showing, closes the drawer.

Result: the new test passes on chromium and webkit with the fix and fails (`[False] == [True]`) with the fix removed (falsified, fix restored). `run-tests.sh --lane contracts-chat -x` (THE_ONE_REQUIRE_WEBKIT=1, netns): 358 passed. `gleepglorp-chat` lane: 84 passed. `tests/test_ui_guards.py`, `test_token_definitions.py`, `test_design_tokens_a11y.py`: 396 passed. ruff check and format clean on the test file.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet), batch review of squawks 0411-0419; Accessibility Reviewer (Sonnet): no keyboard trap; a focused chart now needs two Esc presses to close the drawer, which is acceptable
**Verdict**: confirmed
**Commit**: `squawk: turnaround 2026-11-25` on squawk/turnaround-2026-11-25
