# Squawk 0256: fold the Validator's suggestions into the linux-package-install behavior test

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-24
**Completed**: —
**Related**: 0281, 0282: behavior-spec follow-ups; complete together in one spec-edit pass ([maintenance 2026-10-30](../maintenance/2026-10-30.md)).

## Report
The 44/44 run of `tests/behavior/linux-package-install.md` (Mission 32 Flight 2, leg 12) passed. Its Validator suggested five spec improvements, so the next run (Flight 4's release check) observes more and guesses less:
1. A window-geometry observable: the size remembered across relaunches. Position is X11 only (DD7).
2. Timed notification captures, so a banner is caught before it expires. Step 7 also asks for "not cut off", which the run judged loosely: the HAT found the tray notice truncated.
3. The apparatus facts in Preconditions: passwordless sudo in the guests, and no GDM autologin after a logout.
4. The AppImage runtime-parent rule: the app process runs under the AppImage runtime, not as Files' child.
5. "Hidden from the menu" wording for an AppImage entry that stays on disk but is hidden by `TryExec` after the file is deleted.

## Evidence
- The run log: `tests/behavior/linux-package-install/runs/2026-10-24-20-34-28.md`, the Validator's closing notes.
- The flight log: `fresh-vm-checks (part B)`, finding 6.

## Corrective Action
*(written at completion)*

## Verification
- The spec's Preconditions, Observables and Steps carry all five points. The step table still validates against `.flightops/ARTIFACTS.md`'s behavior-test format. No step depends on a committed baseline image.

## Sign-Off
*(written at completion)*

## Disposition
- **Logged** at Mission 32 Flight 2's debrief, on the operator's decision. Spec-only. Do it before the spec's next run.
