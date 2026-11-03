# Squawk 0293: Flight design should require an operator-approved mockup of new user-facing surfaces

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-30
**Completed**: 2026-11-03

## Report
Mission 33 built routine targets, a chat chooser and connector delivery across Flights 1-3 from the data model outward; the operator first saw them at the mission-closing HAT and removed or reshaped them, which became six added legs. Mockups made at the HAT settled three surfaces in minutes. The operator: "Had we done some mock ups prior to the work, we may have avoided some of this rework." At the Flight 4 debrief the operator chose a project rule.

## Evidence
- `missions/33-routines/flights/04-hat-and-alignment/flight-debrief.md`, Methodology Observation 1 and Recommendation 1.
- `.flightops/agent-crews/flight-design.md`'s Architect prompt has no surface-review check.

## Corrective Action
Added check 10 (user-facing surfaces, high severity if no operator-approved mockup) to the
Architect "Review Flight Design" prompt and item 6 to the Interaction Protocol in
`.flightops/agent-crews/flight-design.md`.

## Verification
Read-back: both the prompt and the protocol carry the rule; the file's sections are intact.

`.flightops/agent-crews/flight-design.md`'s "Architect: Review Flight Design" prompt checks that every new or reshaped user-facing surface in the flight has an operator-approved mockup (or two layout options with the operator's choice) recorded in the flight artifact before legs are locked, and flags its absence as a high-severity issue; the interaction protocol says so too.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches the shell-write hook, `App.safeUrl`, the encryption status count and the credential docs), batch review of the 2026-11-02-2 squawk turnaround, scoped to the diff. Its one blocking finding (0135's Dockerfile `uv venv` line) and the non-blocking items were fixed in a fix pass, which a Haiku Reviewer re-checked: `[HANDOFF:confirmed]`. An Accessibility Reviewer (Sonnet) confirmed the UI changes (0239, 0289, 0290, 0291, 0254). The final gate on the batch tree: `THE_ONE_TEST_NETNS=1 make test-unit` 8738 passed, 15 skipped (219 s, start load 0.48); browser `--parallel 3` `PARALLEL_RESULT rc=1 total=1774s lanes=17 failed=chats-transcript` (start load 0.72). The one failure is new squawk 0315, which passed 3 of 3 isolated runs.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02-2` commit on `squawk/turnaround-2026-11-02-2`.
