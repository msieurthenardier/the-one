# Squawk 0150: The connector line budget has no recorded counting rule

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-08
**Completed**: —

## Report
Mission 23 set a 3,000-line Python budget for connectors and closed at "2,970 / 3,000". Nothing records how that is counted: `the_one/connectors/*.py` alone is 2,553 lines, and the total only reconciles once the connector tools (417) are added. The next platform will face a live budget decision with no reproducible measurement. Found by routine maintenance 2026-10-08 (finding #26).

## Evidence
- `missions/23-connector-reset/mission-debrief.md` — "package 2,553 + tools 417"
- `the_one/connectors/README.md` — no budget or counting command

## Corrective Action
*(written at completion)* Expected: a short "Size budget" note in `the_one/connectors/README.md` naming the budget and the exact command (paths included, how blank lines and comments count).

## Verification
Running the documented command reproduces the current figure.

## Sign-Off
*(written at completion)*
