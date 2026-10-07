# Squawk 0132: The unit suite's skip count flaps between 10 and 12

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-07
**Completed**: —

## Report

Across Mission 25 Flight 6's gate runs, `make test-unit` reported 10 or 12 skipped tests on the same environment. No test changed between those runs that adds a skip. Some pair of tests is skipping conditionally, for example on a busy port, a missing binary, timing or platform. Identify them and record the reason, so a skip-count change at a gate means something.

## Evidence

The Flight 6 flight log's leg gates:

| Leg | Skipped |
|---|---|
| 1b | 12 |
| 2 | 10 |
| 4 | 10 |
| 4d | 10 |
| 4c | 12 |
| 6 | 12 |

In `git diff aaee705..1b6f540 -- tests`, no unit-tier skip marker was added.

## Corrective Action
*(written at completion)*

## Verification
Run `make test-unit` with `-rs` twice or more. Record the skipped test ids and their reasons in this squawk, and in `agents.md`'s testing notes if they are environment-conditional by design. A test that skips for an avoidable reason gets fixed.

## Sign-Off
*(written at completion)*
