# Squawk 0290: A failed focus refetch blanks the Self-configuration waiting list

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-30
**Completed**: —
**Related**: 0289: same self-configuration tab refetch path; complete together ([maintenance 2026-10-30](../maintenance/2026-10-30.md)).

## Report
A refetch triggered only by window focus or visibility (M33 F4 fix pass 3) that fails (offline, a transient error) takes the `renderRoutineQueue([])` / `setUnavailable` branch, so the operator's waiting list disappears on a mere window return. A passive refetch should keep the shown list and only surface the error.

## Evidence
- `the_one/interfaces/web/static/js/areas/studio/self-config-routines.js` (the queue's error branch).
- Mission 33 Flight 4 flight log, "Review of fix pass 3 and F-H1-1".

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

A browser test fails a focus refetch and the previously shown waiting items stay visible with an error line.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
