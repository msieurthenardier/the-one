# Squawk 0268: the leg-execution crew file has no rule for outward dispatches

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-26
**Completed**: 2026-11-03

## Report
Twice in Mission 32 Flight 4, the Flight Director chained `gh workflow run` after a `git commit` that failed. Both times the dispatch still ran, on the old head. Run `40260891145` was cancelled at 24 s and still counted against the hosted Windows budget; run `40265725036` was cancelled before any platform job started. The rule adopted after the second slip ("a dispatch runs as its own command, after the push is verified") lives only in that flight's log.

## Evidence
- `missions/32-installers-everywhere/flights/04-windows-and-release/flight-log.md`: "A Flight Director error, recorded" (leg 3) and "The Flight Director's error, again" (leg 5).
- `.flightops/agent-crews/leg-execution.md` mentions neither dispatches nor outward steps.
- Flight 4 debrief, Recommendation 3 and methodology observation 5.

## Corrective Action
Added an "Outward steps" subsection with the three rules to the Interaction Protocol of
`.flightops/agent-crews/leg-execution.md` (noting that init-project resets would need it
re-applied). Original plan: Add a short project rule to `.flightops/agent-crews/leg-execution.md`, in its Interaction Protocol section, covering any outward step (a workflow dispatch, a tag push, a release):
- it runs as its own command, never chained after a commit or a push with `;` or `&&`;
- before it runs, the pushed head is checked to equal the intended commit (`git rev-parse HEAD origin/<branch>`);
- its run id and head SHA are recorded right after.

This is project configuration, not a plugin file, so it survives plugin updates. If `/mission-control:init-project` would reset it, note that in the edit.

## Verification
- Done (read-back). The crew file carries the rule, and the file still has `## Crew`, `## Interaction Protocol` and `## Prompts`, with fenced prompts (`/mission-control:preflight-check` reports no malformed crew file).

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches the shell-write hook, `App.safeUrl`, the encryption status count and the credential docs), batch review of the 2026-11-02-2 squawk turnaround, scoped to the diff. Its one blocking finding (0135's Dockerfile `uv venv` line) and the non-blocking items were fixed in a fix pass, which a Haiku Reviewer re-checked: `[HANDOFF:confirmed]`. An Accessibility Reviewer (Sonnet) confirmed the UI changes (0239, 0289, 0290, 0291, 0254). The final gate on the batch tree: `THE_ONE_TEST_NETNS=1 make test-unit` 8738 passed, 15 skipped (219 s, start load 0.48); browser `--parallel 3` `PARALLEL_RESULT rc=1 total=1774s lanes=17 failed=chats-transcript` (start load 0.72). The one failure is new squawk 0315, which passed 3 of 3 isolated runs.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02-2` commit on `squawk/turnaround-2026-11-02-2`.

## Disposition
- **Logged** at Mission 32 Flight 4's debrief (operator's choice of debrief follow-ups).
