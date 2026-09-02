# Squawk 0035: Document the studio lane's full-run timing flake as a standing pattern

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-02
**Completed**: —

## Report

Three occurrences across two flights of the same shape: a studio browser-lane test
fails on a FULL-lane run with an element-wait timeout, then passes clean in isolation
within seconds (Flight 3 leg 2: `test_last_updated_renders_relative_time_format`;
leg 3: `test_studio_section_nav_renders_four_buttons`; Flight 3 debrief run:
`test_studio_connector_enabled_checkbox_unchecked_persists_disabled`, isolated rerun
2.5s clean). Each was re-diagnosed from scratch. Add a standing note in the studio
lane's conftest or lane header: full-run timing flakes are a known characteristic;
isolated-rerun-before-treating-as-regression is the standing disposition.

## Evidence

- Flight 3 flight-log entries (legs 2, 3) and flight-debrief Test Metrics (2026-09-02)
- Raised by the Flight 3 debrief, Developer interview recommendation 3

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
