# Squawk 0023: Crew file — Reviewer on Sonnet for security-touching reviews

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-08-28
**Completed**: 2026-08-28

## Report

`.flightops/agent-crews/leg-execution.md` sets the Reviewer's model to Haiku. The Flight
Director has deviated to Sonnet twice in a row (squawk turnaround 2026-08-27; Mission 22
Flight 1) because the diffs carried credential/key material and a gate exemption, disclosing
each time. Operator decision at the 2026-08-28 flight debrief: codify it. Update the Reviewer
entry to "Sonnet for reviews that touch security-sensitive surfaces (credentials, key
material, the credential gate, sandboxing); Haiku otherwise", with the Flight Director
recording which applied.

## Evidence

- `.flightops/agent-crews/leg-execution.md:18` — `**Model**: Haiku` (Reviewer)
- `missions/22-maintenance/flights/01-credential-lifecycle-integrity/flight-log.md` — Flight Director Notes, "Model deviation"
- `missions/22-maintenance/flights/01-credential-lifecycle-integrity/flight-debrief.md` — Deviations table

## Corrective Action

Updated the Reviewer entry's `**Model**` line in `.flightops/agent-crews/leg-execution.md`
(under `### Reviewer`, `## Crew`) from a flat `Haiku` to a conditional: Sonnet when the diff
touches a security-sensitive surface (credentials, key material, the credential gate or
middleware exemptions, sandboxing, self-configuration identity); Haiku otherwise. Added one
sentence that the Flight Director records which tier applied in the flight log (or squawk
sign-off). No other line in the Reviewer entry, and no other section of the file
(`## Interaction Protocol`, `## Prompts`, handoff signals), was touched.

Checked `.flightops/agent-crews/flight-debrief.md` — it defines only Developer and Architect
crew entries, no Reviewer, so nothing to change there. Searched `docs/` and `CLAUDE.md` in
this project for a restated "Reviewer runs on Haiku" sentence; found none — the only Haiku
mentions are unrelated behavior-test run logs (model-scope notes for a different feature),
not restatements of this crew-file policy.

## Verification

- `grep -n "Model" .flightops/agent-crews/leg-execution.md` shows the Reviewer's `**Model**`
  line now reads the conditional Sonnet/Haiku text with the flight-log recording sentence,
  while Developer and Accessibility Reviewer model lines (Sonnet, unconditional) are
  unchanged.
- `grep -c '^## '` on the file: 5 before and after the edit (unchanged) — `## Crew`,
  `## Separation Rules`, `## Interaction Protocol`, `## Template Variables`, `## Prompts` all
  still present.
- `grep -c '^```'` on the file: 12 before and after the edit (unchanged) — all fenced code
  blocks in `## Prompts` intact.
- `## Interaction Protocol`, `## Prompts`, and all handoff signal strings
  (`[HANDOFF:review-needed]`, `[HANDOFF:confirmed]`, `[BLOCKED:reason]`, `[COMPLETE:leg]`)
  confirmed byte-identical to the pre-edit version — only the `### Reviewer` `**Model**` bullet
  changed.

## Sign-Off
**Reviewer**: Reviewer agent (independent, diff-scoped batch review of turnaround 2026-08-28; Sonnet — batch touches the credential gate and key-material code)
**Verdict**: confirmed
**Commit**: artifact in `92c2563`; the crew-file change itself is versioned in `767e87d` (squawk 0024 un-ignored `.flightops/` in the same turnaround) on `squawk/turnaround-2026-08-28` — PR #180

Full unit suite at close-out: 4580 passed / 10 skipped / 0 failed (513s); browser lane for 0022: 2 passed.
