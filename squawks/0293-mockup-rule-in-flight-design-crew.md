# Squawk 0293: Flight design should require an operator-approved mockup of new user-facing surfaces

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-30
**Completed**: —

## Report
Mission 33 built routine targets, a chat chooser and connector delivery across Flights 1-3 from the data model outward; the operator first saw them at the mission-closing HAT and removed or reshaped them, which became six added legs. Mockups made at the HAT settled three surfaces in minutes. The operator: "Had we done some mock ups prior to the work, we may have avoided some of this rework." At the Flight 4 debrief the operator chose a project rule.

## Evidence
- `missions/33-routines/flights/04-hat-and-alignment/flight-debrief.md`, Methodology Observation 1 and Recommendation 1.
- `.flightops/agent-crews/flight-design.md`'s Architect prompt has no surface-review check.

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

`.flightops/agent-crews/flight-design.md`'s "Architect: Review Flight Design" prompt checks that every new or reshaped user-facing surface in the flight has an operator-approved mockup (or two layout options with the operator's choice) recorded in the flight artifact before legs are locked, and flags its absence as a high-severity issue; the interaction protocol says so too.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
