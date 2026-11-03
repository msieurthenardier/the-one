# Squawk 0281: Re-author the `agent-step-limit-notice` spec's follow-ups from its 2026-10-28 run

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-28
**Completed**: 2026-11-03
**Related**: 0256, 0282: behavior-spec follow-ups; complete together in one spec-edit pass ([maintenance 2026-10-30](../maintenance/2026-10-30.md)).

## Report
The HAT-close run of `tests/behavior/agent-step-limit-notice.md` passed 7/7. Its Validator and the Orchestrator listed six spec-quality follow-ups. They were deliberately not edited at the run, because steps are re-authored on purpose, never during a run. Apply them so the next run cannot pass vacuously or trip on seeding.

## Evidence
`tests/behavior/agent-step-limit-notice/runs/2026-10-28-14-36-06.md`, Orchestrator Notes ("Spec follow-ups"):
- Step 2: accept the `/general` suffix.
- Step 3: require an outbound baseline and a minimum number of polls after the first record.
- Step 1b: accept the DOM capture for "the old button gone", or ask for a mid-turn screenshot.
- Step 4: require the rendered conversation, so a count of 0 cannot pass vacuously.
- Preconditions: name the mock provider's `base_url`, the seeding order (provider before agent; squawk 0277), and the credential step (squawk 0278).
- Step 6: name the default `max_iterations` (20).

## Corrective Action
Edited `tests/behavior/agent-step-limit-notice.md`: step 2 accepts the `/general` suffix; step 3 records an outbound baseline first, polls at least 3 more times after the first new record and judges "exactly one new entry against the baseline"; step 1b accepts a DOM capture (first notice's Continue absent) or a mid-turn screenshot for "old button gone"; step 4 requires the rendered conversation (a `hello` user bubble present) so a count of 0 cannot pass on an empty log; Preconditions name the mock provider (`type: mock`, `base_url: ""`), the seeding order (provider, then agent with its id, then connector; squawk 0277) and the credential step (`the-one rotate-api-credential`; squawk 0278); step 6 names the default `max_iterations` (20). Also per 0213 the spec already used `$HOME`; no path change needed.

## Verification
No behavior test was run (not requested), so the Expected Results changes are untested by a re-run. Re-read the edited spec: the step table format is intact. Unit tier result under 0282.
Each of the six items is reflected in the spec, and the spec still validates against ARTIFACTS.md's format. A re-run is optional; record one if the steps' Expected Results changed.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches the shell-write hook, `App.safeUrl`, the encryption status count and the credential docs), batch review of the 2026-11-02-2 squawk turnaround, scoped to the diff. Its one blocking finding (0135's Dockerfile `uv venv` line) and the non-blocking items were fixed in a fix pass, which a Haiku Reviewer re-checked: `[HANDOFF:confirmed]`. An Accessibility Reviewer (Sonnet) confirmed the UI changes (0239, 0289, 0290, 0291, 0254). The final gate on the batch tree: `THE_ONE_TEST_NETNS=1 make test-unit` 8738 passed, 15 skipped (219 s, start load 0.48); browser `--parallel 3` `PARALLEL_RESULT rc=1 total=1774s lanes=17 failed=chats-transcript` (start load 0.72). The one failure is new squawk 0315, which passed 3 of 3 isolated runs.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02-2` commit on `squawk/turnaround-2026-11-02-2`.
