# Squawk 0414: Esc in a chart closes the GleepGlorp drawer too

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-24
**Completed**: —

## Report

When a chart's keyboard tooltip is showing inside the drawer, pressing Esc hides the tooltip and then also closes the whole drawer. The chart handler returns before `preventDefault`, so the drawer's Esc handler, which honours `defaultPrevented`, sees an unhandled Esc. Found by the 2026-11-24 routine maintenance (Accessibility Reviewer).

## Evidence
- `static/js/ui/chart.js` plot keydown (about line 350): `else if (key === 'Escape') { hide(); return; }`. The `ev.preventDefault()` below it is skipped.
- `static/js/ui/drawer.js` `onKeydown` (about line 152): `if (e.key !== 'Escape' || e.defaultPrevented || root.hidden) return;`.

## Corrective Action
*(written at completion)*

## Verification
A contract test: with a chart in the drawer, the tooltip open and focus on the plot, Esc hides the tooltip and the drawer stays open. A second Esc, with no tooltip showing, closes the drawer.
