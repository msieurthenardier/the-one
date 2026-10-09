# Squawk 0157: Self-configuration drain test timed out once under CI load

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-09
**Completed**: —

## Report
`test_live_surface_connection_evicted_before_general_drain` failed once in the Concourse `test` task during Mission 26 F01 leg 5 (a `fly execute` one-off build), with an MCP initialize timeout (30 s). The same file passed when run alone in the same container (11 passed), and the test has never failed locally (leg 4 gate, debrief gate, flight review `make test-unit`). The file was converted to the session template DB in Mission 26 F01 leg 1, so it is either a load-sensitive timing flake or a template-related ordering effect.

Reproduce: run the CI `test` task (`ci/tasks/test.yml`) under host load, or the unit lane alongside a heavy process. Watch the first post-merge pipeline builds.

## Evidence
- `tests/test_self_configuration_surface.py:602`: `TestSquawk0005ShutdownDrainUnderLoad::test_live_surface_connection_evicted_before_general_drain`.
- Flight log `missions/26-maintenance/flights/01-test-suite-runtime/flight-log.md`, Leg 5 Anomalies (unresolved).
- Scope gate: if diagnosis shows the drain itself, not the test's timing, is at fault, escalate rather than fix here.

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
