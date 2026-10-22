# Squawk 0220: Arming a two-step confirm is not announced to screen readers

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-15
**Completed**: 2026-10-21

## Report
`App.ui.confirm` (formerly `App.confirmDelete`) arms a control by swapping its label to, for example, "Confirm delete?" and starting a 3-second lapse timer. It sends no live-region announcement.
- A screen-reader user who presses Enter may hear nothing, and may not realise the control is now armed.
- The 3-second auto-revert leaves little time for an assistive-technology user to find and confirm it (WCAG 2.2.1).

The behaviour predates Mission 31: the `confirm.js` header records it as deliberate. It applies app-wide, to all 14 call sites, so it is out of scope for the Flight 1 pilot.

A fix would add one shared polite announcement in `App.ui.confirm`, as `self-configuration-tab.js` already does for its own case. It could also lengthen or pause the lapse while focus is on the armed control.

## Evidence
- `the_one/interfaces/web/static/js/ui/confirm.js` (arm path, no live region).
- `the_one/interfaces/web/static/js/ui/editor.js` `dangerZone` (consumer).
- Mission 31 Flight 1 Accessibility Reviewer, non-blocking item 3 (flight log, Phase 2d).

## Corrective Action
Mission 31 Flight 2 leg 05. `App.ui.confirm` now announces through one shared polite live region (`div.visually-hidden[role=status][aria-live=polite]`, `data-testid=ui-confirm-live`), appended to `document.body` lazily on the first arm, cached with an `isConnected` check, and written through a single pending-timeout handle (clear, then set on the next tick, so a repeat arm re-announces and a lapse cannot race a following arm).
- Arm: "Press {subject} again to {confirmLabel lower-cased, no '?'}."; lapse: "{subject}: not confirmed"; commit clears the region.
- The subject is `opts.announceName`, else the control's `aria-label`, else the original title text.
- The two local workarounds (`rules-notes-tab.js` arm message, `self-configuration-tab.js` revoke announcement) were removed; their error and limit regions stay.
- Visual behaviour is unchanged. The lapse timing was not lengthened (the announcement is the fix).

## Verification
A contract case in `tests/browser/test_ui_confirm_contract.py` (both engines) asserts that arming produces a polite status announcement and that lapse and commit clear it.

## Sign-Off
**Reviewer**: pending (flight review)
**Verdict**: pending
**Commit**: pending (flight commit)
