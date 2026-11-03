# Squawk 0318: A failed refetch blanks the Agent prompt waiting list

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-03
**Completed**: —

## Report
Squawk 0290 fixed the Routines item. When a refetch triggered by a window return fails, it now keeps the waiting list and shows an error. The Agent prompt item's `refetchRevisions` on the self-configuration tab still blanks its waiting list when the same refetch fails. Apply the same failed-refetch handling there.

## Evidence
- The 0290 Developer's report (turnaround 2026-11-02-2).
- `the_one/interfaces/web/static/js/areas/studio/self-configuration-tab.js` (`refetchRevisions`). Compare `self-config-routines.js` `refetchRoutines(passive)`.

## Corrective Action
*(written at completion)*

## Verification
- A browser test fails the revisions GET on a window return. It expects the list to stay and the error line to show.
- The test is falsified.
- The `agent-tabs` lane passes.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
