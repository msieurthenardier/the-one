# Squawk 0023: Crew file — Reviewer on Sonnet for security-touching reviews

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-08-28
**Completed**: —

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
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
