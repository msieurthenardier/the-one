# Squawk 0401: A dirty provider editor can revert a type change that was approved meanwhile

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-21
**Completed**: 2026-11-23

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
Fixed in Mission 36 Flight 5 Leg 2 (flight DD4). The chosen fix: Save is refused, in the editor's
existing save-error line, until Cancel.
- `provider-editor-controller.js` gains `blockSave(text|null)` and `saveBlock()`.
- `provider-editor-follow.js`, in the dirty type-change branch, calls
  `ctl.blockSave("This provider's type changed; Cancel to see it")` beside the note. The
  same-type rebase branch calls `ctl.blockSave(null)` (a later approval that changes the type back
  to the mounted one lifts the block) and drops the stale Cancel hook.
- `provider-editor.js::performSave` shows the block text through `h.shell.setError` right after
  clearing the error and returns before `collectFormData`, so no PUT is sent, `saving` is
  untouched and the form stays dirty.
- Cancel re-mounts the editor on the new type (a new controller), so the block dies with the old
  one. No new placement: the message uses the existing error row.

Rejected: sending the new type with the dirty edits (merging dirty fields across a type change is
out of scope, as the note already says).

## Verification
A browser test runs these steps:
1. a provider editor is open and dirty;
2. a type change is approved;
3. the operator clicks Save.

Either the Save is refused with a message pointing to Cancel, or the editor stops the save until
Cancel. Choose the fix at completion, and record it here. The approved type survives in the stored
row.

Recorded: `tests/browser/test_flow_gleepglorp_follow_provider.py` has two new tests beside the
existing one.
- `test_save_is_refused_after_a_type_change_by_approval_until_cancel_squawk_0401`: Save shows the
  sentence in `.ui-editor-error-row`, sends no PUT, leaves the stored type (`ollama`) and the form
  dirty; Cancel re-mounts on the new type and a Save there succeeds.
- `test_a_later_approval_that_changes_the_type_back_lifts_the_save_block_squawk_0401`: the second
  approval rebases, the message goes, and Save sends one PUT.

## Sign-Off
- **Fixed in:** Mission 36 Flight 5, Leg 2.
- **Reviewed:** by the Flight 5 Batch A Reviewer (Sonnet): `[HANDOFF:confirmed]`, 2026-11-23.
  The Accessibility Reviewer confirmed the change too, and its one finding was fixed before the
  commit: the provider editor's error line now has `role="alert"`, so the refusal is announced.
- **Committed:** in the Flight 5 Batch A checkpoint commit (its ref is in the flight log).
