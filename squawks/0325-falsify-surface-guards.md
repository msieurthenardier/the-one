# Squawk 0325: Falsify the unproven self-configuration surface guards

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-03
**Completed**: —

## Report
Sortie 08 protects the self-configuration surface in two layers: it strips stored withholds on write and at startup, and it ignores them at build time. Either layer can make the other's tests pass, and several guards were never shown to fail without their fix (sortie 08 debrief, Recommendation 2). Falsify each one: remove the fix by edit, see the test fail, then restore it by edit. Strengthen any test that stays green. Optionally, add a guard test that fails on any new `(mcp_overrides or {}).get(source.name)` outside `override_for`. Tests only; no behaviour change.

## Evidence
- `override_for` call sites: `the_one/mcp/_tool_provider.py:281` and `the_one/agent/factory.py:170` (`_build_source_index`) were not falsified. Only `the_one/self_configuration/projection.py:155` was. Tests: `tests/test_self_configuration_agent_writes.py::TestBuildSitesIgnoreAStoredEntry` (e.g. `test_search_tools_index_lists_all_four_tools`, line ~408).
- `disabled_tools` strip on write (`the_one/interfaces/web/api.py::_normalize_surface_fields`): `TestDisabledToolsStrip::test_surface_names_are_stripped_and_others_kept` (~270). It must assert the **stored** `disabled_tools`, not only tool presence, because the factory's `is_platform_surface` exemption would mask a broken strip.
- Empty-entry drop: `TestOverrideRefusal::test_empty_entry_is_accepted_and_dropped` (~219).
- Falsification record: `sorties/08-self-configuration-off-tools-tab/flight-log.md`, Leg 01 "Falsification".

## Corrective Action
*(written at completion)*

## Verification
For each guard, show the named test failing with the fix removed and passing with it restored. Then run `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_self_configuration_agent_writes.py -x --timeout 60` and `THE_ONE_TEST_NETNS=1 make test-unit`.

## Sign-Off
*(written at completion)*
