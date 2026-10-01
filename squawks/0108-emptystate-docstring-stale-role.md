# Squawk 0108: `App.ui.emptyState` docstring still says listPane passes `role: 'status'`

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-01
**Completed**: —

## Report

The option comment for `App.ui.emptyState` in `ui/feedback.js` still says listPane passes
`'status'` as the role. That stopped being true in the Flight 1 review fix round. The
list pane's empty element no longer carries `role="status"`; announcements now come from
a persistent `.ui-list-pane-status` live region. The comment misleads anyone reading the
factory's API. Found by the Mission 25 Flight 1 debrief (Architect).

## Evidence

- `the_one/interfaces/web/static/js/ui/feedback.js:51` contains "role (set on the root
  when given; listPane passes 'status')".
- `the_one/interfaces/web/static/js/ui/list-pane.js` builds the empty state without a
  `role`, and a separate `.ui-list-pane-status` region does the announcing.

## Corrective Action

*(written at completion)*

## Verification

*(written at completion)*

Read-back of the comment, plus `tests/test_ui_library_source.py` and the ui-dir sink
guard. Comments in `ui/` are scanned, so the reworded comment must stay free of `testid:`
and of the sink tokens.

## Sign-Off

*(written at completion)*
