# Squawk 0363: the Routines card re-announces its passive-refetch error on every window return

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-14
**Completed**: —

## Report
On the Self-configuration tab, the Routines card refetches its queue when the window is returned to. If that refetch fails, it shows "Unable to refresh waiting changes." on a `role=alert` line. While the failure lasts, every window return sets the same text again, so a screen reader announces it again each time. Squawk 0318 fixed the same problem for the Agent prompt card by announcing once per failure episode. The Routines card was not changed.

Expected: the line is set once per failure episode, and a later passive success clears only the passive message.

## Evidence
- `the_one/interfaces/web/static/js/areas/studio/self-config-routines.js`: `errorLine = App.ui.status({ state: 'danger', led: false, role: 'alert', ... })` (line ~84), `showError(text, passive)` (line ~220) and the passive failure branch `showError('Unable to refresh waiting changes.', true)` (line ~312). Nothing returns early when `passiveError` is already set.
- The fix to copy: `self-config-status.js` `refetchRevisions(passive)`, which returns early when `passiveRevisionsError` is set (line ~255).
- Found by the accessibility review of squawk 0318 (2026-11-14 turnaround).
