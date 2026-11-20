# Squawk 0392: A "Proposal lifecycle" overview in agents.md

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-19
**Completed**: —

## Report
`the_one/agents.md` describes GleepGlorp proposals leg by leg (M36 F2 L2 to L8),
but has no single overview a Flight 3 reader can start from. Add one short
"Proposal lifecycle" section: the states (`pending`, `applied`, `dismissed`,
`withdrawn`, `failed`) and their transitions, the one-open-per-chat rule
(`ProposalOpen`), a resolved proposal (`_AlreadyResolved`), the guard and the
continuation split, and the shared-service rule (the API route and
`apply_proposal` call the same write service, so validation cannot diverge).
Raised in the Flight 2 debrief.

## Evidence
- `the_one/agents.md` sections "GleepGlorp proposals (M36 F2 L2)" onward: per-leg only.
- `the_one/gleepglorp/proposals/store.py` (states, `ProposalOpen`),
  `apply.py` (`_AlreadyResolved`, `apply_proposal`), `the_one/agent/service.py`.

## Corrective Action
*(written at completion)*

## Verification
The section exists, links the per-leg sections rather than repeating them, and
every name it cites exists in the code (grep).

## Sign-Off
*(written at completion)*
