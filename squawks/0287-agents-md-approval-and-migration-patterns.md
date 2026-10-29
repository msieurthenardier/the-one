# Squawk 0287: Name the approval and migration patterns in agents.md Project Conventions

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-29
**Completed**: 2026-10-29

## Report
Mission 33 Flight 3 introduced two reusable patterns. Both are described
only inside the routines sections of `the_one/agents.md`, not in its
"Project Conventions" list of named patterns:
- **Verbatim stored pair plus re-render at apply.** A proposal stores the
  normalized value with its exact instant (`schedule` plus `anchor_at`).
  Approval applies it verbatim, re-rendering only the display (`rezone`),
  and never re-normalizes against approval time.
- **Frozen migration converter with a guarded failure row.** A data
  migration carries its own converter, not the live normalizer. An
  unreadable row is turned off with one guarded history row instead of
  failing startup (v48).

## Evidence
- `missions/33-routines/flights/03-schedules-and-limits/flight-debrief.md`,
  Recommendation 5.
- `the_one/routines/service.py` (the approval pair and `rezone`) and the
  `the_one/db/schema.py` v48 block.
- `the_one/agents.md` "Project Conventions" has no entry for either.

## Corrective Action
Added two entries at the end of the `### Project-wide` run in `the_one/agents.md`
"Project Conventions" (just before "### Mission-specific (M16)"):
`verbatim-stored-pair-plus-rezone-at-apply` and
`frozen-migration-converter-with-guarded-failure-row`. Each states the rule, the
reason and a `file::symbol` citation checked against the code.

## Verification
`the_one/agents.md` "Project Conventions" has a named entry for each
pattern. Each entry gives one example citation and the reason for the
pattern.

Met: both entries exist under Project-wide; each has a rule, a reason and a
citation (`service.py::approve_proposal`/`_approval_pair`, `recurrence.py::rezone`;
`schema.py::_v48_convert`/`_v48_rewrite_routines`), all read in the code before writing.

## Sign-Off
**Reviewer**: Reviewer agent (Haiku), scoped to the diff of the 0286/0287
batch, `[HANDOFF:confirmed]`. Both entries sit at the end of the Project-wide
run in the neighbours' format; every cited symbol (`_agent_schedule`,
`_approval_pair`, `approve_proposal`, `recurrence.rezone`, `_v48_convert` and
its helpers, `_v48_rewrite_routines`, `_V48_UPGRADE_FAILED`) exists and the
described behaviour matches the code. No issues on 0287.
**Verdict**: confirmed
**Commit**: (this commit, `squawk: turnaround 2026-10-29`, on `squawk/turnaround-2026-10-29`)
