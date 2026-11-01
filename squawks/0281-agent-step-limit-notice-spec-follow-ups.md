# Squawk 0281: Re-author the `agent-step-limit-notice` spec's follow-ups from its 2026-10-28 run

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-28
**Completed**: —
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
*(written at completion)*

## Verification
*(written at completion)*
Each of the six items is reflected in the spec, and the spec still validates against ARTIFACTS.md's format. A re-run is optional; record one if the steps' Expected Results changed.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
