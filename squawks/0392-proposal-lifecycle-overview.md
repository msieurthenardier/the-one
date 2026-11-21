# Squawk 0392: A "Proposal lifecycle" overview in agents.md

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-19
**Completed**: 2026-11-21

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
Added a "### Proposal lifecycle (M36 F2)" section to `the_one/agents.md`,
immediately before "GleepGlorp proposals (M36 F2 L2)" (same `###` level under
"## GleepGlorp (M36)"). It covers states and transitions, `ProposalOpen`,
`_AlreadyResolved`, the staleness 409 and `override`, the continuation split and
the shared write services, and links the L2, L6 and L7 sections by heading.
Difference from the squawk: the write services are in `the_one/agent/service.py`,
`the_one/agent/rules_service.py` and `the_one/routines/service.py`, not only
`agent/service.py`. `withdrawn` is system-only (replaced or gone), never an
operator action.

## Verification
The section exists, links the per-leg sections rather than repeating them, and
every name it cites exists in the code (grep).

Checked: `STATUSES`, `OPEN_STATUSES`, `ProposalOpen`, `mark(from_statuses)` in
`proposals/store.py`; `_AlreadyResolved`, `apply_proposal`, `dismiss_proposal`
and the `withdrawn` "gone" mark in `apply.py`; the 409 answers in
`gleepglorp_proposals_api.py`; `on_approved`/`on_dismissed` in
`continuation.py`; `create_agent`/`change_agent`, `create_rule`/`change_rule`,
`create_routine`/`update_routine` called from `apply.py` and `api.py` /
`routines_api.py`; linked headings (L2, L6, L7) exist exactly.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet; the security tier, since the batch changed the shell-write hook and CLAUDE.md's safety rules), batch review of squawks 0368, 0379, 0384, 0385, 0391-0397
**Verdict**: confirmed
**Commit**: `squawk: turnaround 2026-11-21` on squawk/turnaround-2026-11-21
