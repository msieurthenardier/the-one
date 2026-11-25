# Squawk 0426: `the_one/agents.md` does not describe the xdist isolation patterns

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-25
**Completed**: —

## Report

Mission 37 Flight 1 introduced three test-infrastructure patterns that are recorded only in its flight log:

1. **Per-worker data directories.** Each xdist worker gets its own data directory. A marker variable, `_THE_ONE_PYTEST_OWN_DATA_DIR`, separates a directory minted by conftest from an explicit override. The marker is inherited by child processes, which is harmless but undocumented.
2. **Opt-in, once-per-session fixtures for static data:** `fast_builtin_tool_names` and `parsed_scenarios_once`. The real function must still be asserted once.
3. **The window rule for tests that spawn MCP servers.** The silent window must exceed the interpreter's start-up time, about 1.2 s. Reserves are ceilings.

The next person to add a test-isolation resource, or to write a slow sweep, will not find these. Found by the Mission 37 Flight 1 debrief (Developer and Architect).

## Evidence
- `tests/conftest.py:39-50`: the marker logic.
- `tests/conftest.py` `fast_builtin_tool_names`, and `tests/test_evals_gleepglorp_harness.py` `parsed_scenarios_once`.
- `missions/37-maintenance/flights/01-unit-tier-runtime-iii/flight-log.md`: the Leg 1 and Leg 2 entries.

## Corrective Action
*(written at completion)*

## Verification
`the_one/agents.md` describes all three patterns. The likely home is "Test databases come from the session template", or a new subsection of the test-runner sections. A reader can find each pattern by searching for `PYTEST_XDIST_WORKER`, `fast_builtin_tool_names` and "spawn".

## Sign-Off
*(written at completion)*
