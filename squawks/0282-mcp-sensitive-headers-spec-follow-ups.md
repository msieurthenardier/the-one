# Squawk 0282: Re-author the `mcp-sensitive-headers-round-trip` spec's follow-ups from its 2026-10-28 run

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-28
**Completed**: —
**Related**: 0256, 0281: behavior-spec follow-ups; complete together in one spec-edit pass ([maintenance 2026-10-30](../maintenance/2026-10-30.md)).

## Report
The HAT-close run of `tests/behavior/mcp-sensitive-headers-round-trip.md` passed 8/8. The run listed four spec-quality follow-ups, deliberately not edited at the run. Apply them.

## Evidence
`tests/behavior/mcp-sensitive-headers-round-trip/runs/2026-10-28-14-36-06.md`, Orchestrator Notes ("Spec follow-ups"):
- Step 6: split the re-store precondition from the judged key change, or require evidence of the stored state first.
- Steps 5 and 7: add a note on the different storage of an empty value (in `config` when not sensitive, in `secrets` when sensitive).
- Step 8: name the before/after API diff as the evidence.
- Out of Scope: mention the automatic connection-status line.

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*
Each of the four items is reflected in the spec, and the spec still validates against ARTIFACTS.md's format.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
