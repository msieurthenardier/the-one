# Squawk 0256: fold the Validator's suggestions into the linux-package-install behavior test

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-24
**Completed**: 2026-11-03
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
Edited `tests/behavior/linux-package-install.md` only. (1) New "window geometry" observable; step 7 records the outer size before closing and step 8/9 compare it after relaunch (position stays X11-only, not asserted). (2) Step 7 now takes timed screendumps (about 0.5 s, 2 s, 5 s after the click) and defines "not cut off" (whole title and every body line readable, no ellipsis, a truncated notice fails). (3) Preconditions state passwordless `sudo` in the guest and that GDM autologin applies at boot only, so step 11 logs back in by typing the password through QMP. (4) Step 2 and step 9 state that the AppImage app runs under the AppImage runtime, not as Files' child, and the process is identified by the AppImage path. (5) Step 11 words an AppImage `.desktop` entry that stays on disk but is hidden by `TryExec` as "hidden from the menu", judged on what the app grid shows. Intent and steps' subjects unchanged.

## Verification
Reviewed by re-reading the edited spec; the table keeps its three-column step format and no step references a committed baseline image. No behavior test was run (not requested). `THE_ONE_TEST_NETNS=1 make test-unit` result recorded under squawk 0282 below (one run for the whole batch); no test reads `tests/behavior/` specs.
- The spec's Preconditions, Observables and Steps carry all five points. The step table still validates against `.flightops/ARTIFACTS.md`'s behavior-test format. No step depends on a committed baseline image.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches the shell-write hook, `App.safeUrl`, the encryption status count and the credential docs), batch review of the 2026-11-02-2 squawk turnaround, scoped to the diff. Its one blocking finding (0135's Dockerfile `uv venv` line) and the non-blocking items were fixed in a fix pass, which a Haiku Reviewer re-checked: `[HANDOFF:confirmed]`. An Accessibility Reviewer (Sonnet) confirmed the UI changes (0239, 0289, 0290, 0291, 0254). The final gate on the batch tree: `THE_ONE_TEST_NETNS=1 make test-unit` 8738 passed, 15 skipped (219 s, start load 0.48); browser `--parallel 3` `PARALLEL_RESULT rc=1 total=1774s lanes=17 failed=chats-transcript` (start load 0.72). The one failure is new squawk 0315, which passed 3 of 3 isolated runs.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02-2` commit on `squawk/turnaround-2026-11-02-2`.

## Disposition
- **Logged** at Mission 32 Flight 2's debrief, on the operator's decision. Spec-only. Do it before the spec's next run.
