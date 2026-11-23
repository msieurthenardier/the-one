# Squawk 0401: A dirty provider editor can revert a type change that was approved meanwhile

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-21
**Completed**: —

## Report

When a provider's type is changed by an approved GleepGlorp proposal while the operator has the
editor for that provider open **with unsaved edits**:
- the editor shows a note ("This provider's type changed; Cancel to see it");
- it does not rebase, because merging dirty fields across a type change is out of scope.

If the operator then clicks Save instead of Cancel, the PUT sends the old type and reverts the
approved change.

Nothing is lost silently: the note is visible, the form is dirty, and no key moves. But the
approval is undone.

The Flight 4 Batch B Reviewer judged it acceptable for the flight and asked for a follow-up.

## Evidence
- `the_one/interfaces/web/static/js/areas/studio/provider-editor-follow.js`: the dirty path of a
  type change by approval only draws the note.
- `missions/36-gleepglorp-assistant/flights/04-mcp-servers-and-providers/legs/05b-provider-editor-fill.md`
  resolution 13 and the Leg 5b flight-log entry.

## Corrective Action
*(written at completion)*

## Verification
A browser test runs these steps:
1. a provider editor is open and dirty;
2. a type change is approved;
3. the operator clicks Save.

Either the Save is refused with a message pointing to Cancel, or the editor stops the save until
Cancel. Choose the fix at completion, and record it here. The approved type survives in the stored
row.
