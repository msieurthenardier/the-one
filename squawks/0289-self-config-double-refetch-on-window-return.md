# Squawk 0289: Self-configuration refetches both queues twice on a window return

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-30
**Completed**: —

## Report
Returning to the window often fires both `visibilitychange` and `focus`; the Self-configuration tab (M33 F4 fix pass 3, F-E3-1) refetches both approval queues on each, so a return makes two requests per queue. A sequence guard keeps the result correct; only the duplicate fetch is wasted.

## Evidence
- `the_one/interfaces/web/static/js/areas/studio/self-configuration-tab.js` ~:178-179 (the two listeners).
- Mission 33 Flight 4 flight log, "Review of fix pass 3 and F-H1-1".

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

A test counts requests on a simulated return that fires both events and sees one refetch per queue.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
