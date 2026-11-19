# Squawk 0388: Falsify the reserved-name tests from Mission 36 Flight 1 Leg 2

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-19
**Completed**: —

## Report
Leg 2 (`retire-default-agent`) added tests for the reserved agent names `default` and `GleepGlorp`. The flight log lists several of them as never falsified, so none has been shown to fail without the code it pins. The names guard a security-adjacent boundary: a stored agent must never take GleepGlorp's identity.

The unfalsified tests:
- the startup rename;
- the connector binding 422s;
- the inbound drop;
- `start_session`'s refusal;
- the routines guards;
- schema v53's idempotency and fresh-database cases.

Falsify each test: break its guard, see the test fail, revert, and record the result. Fix any test that passes vacuously.

## Evidence
- `missions/36-gleepglorp-assistant/flights/01-gleepglorp-exists-and-answers/flight-log.md`: Leg 2 entry, "not falsified" list.
- Code under test: `the_one/naming.py:check_agent_name`, `the_one/db/name_repair.py`, and the v53 step in `the_one/db/schema.py`.
- Debrief, "Technical": "Security-adjacent tests were not falsified".

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
