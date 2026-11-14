# Squawk 0325: Falsify the unproven self-configuration surface guards

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-03
**Completed**: 2026-11-14

## Report
Sortie 08 protects the self-configuration surface in two layers: it strips stored withholds on write and at startup, and it ignores them at build time. Either layer can make the other's tests pass, and several guards were never shown to fail without their fix (sortie 08 debrief, Recommendation 2). Falsify each one: remove the fix by edit, see the test fail, then restore it by edit. Strengthen any test that stays green. Optionally, add a guard test that fails on any new `(mcp_overrides or {}).get(source.name)` outside `override_for`. Tests only; no behaviour change.

## Evidence
- `override_for` call sites: `the_one/mcp/_tool_provider.py:281` and `the_one/agent/factory.py:170` (`_build_source_index`) were not falsified. Only `the_one/self_configuration/projection.py:155` was. Tests: `tests/test_self_configuration_agent_writes.py::TestBuildSitesIgnoreAStoredEntry` (e.g. `test_search_tools_index_lists_all_four_tools`, line ~408).
- `disabled_tools` strip on write (`the_one/interfaces/web/api.py::_normalize_surface_fields`): `TestDisabledToolsStrip::test_surface_names_are_stripped_and_others_kept` (~270). It must assert the **stored** `disabled_tools`, not only tool presence, because the factory's `is_platform_surface` exemption would mask a broken strip.
- Empty-entry drop: `TestOverrideRefusal::test_empty_entry_is_accepted_and_dropped` (~219).
- Falsification record: `sorties/08-self-configuration-off-tools-tab/flight-log.md`, Leg 01 "Falsification".

## Corrective Action
Tests only, in `tests/test_self_configuration_agent_writes.py`; no product change (`git diff` empty for every product file broken for falsification). Each guard was broken by edit, the result recorded, and the code restored by edit:
- `factory._build_source_index` (`override_for` -> direct `.get(source.name)`): `test_search_tools_index_lists_all_four_tools` FAILED. Already effective.
- `_tool_provider.get_tools_for_agent` Path B (line 377): NO existing test failed. Added `test_tool_provider_build_registers_all_four_tools` (both override shapes); FAILED with the break (2 failures).
- `_tool_provider.make_source_resolver` (line 272; the squawk's "281" has moved): no test covered it. Added `test_connection_resolver_ignores_a_stored_surface_entry` (a stored `headers` entry must not reach `source.secrets`); FAILED with the break. (My first draft asserted on `config` and stayed green, so it was corrected to `secrets`.)
- `_agent_cache.per_agent_tools` (line 58, a fifth reader the squawk did not name): added `test_per_agent_cache_ignores_a_stored_surface_credential`, which needs a STORED agent (an unstored one returns False regardless) and a positive control on an ordinary source; FAILED with the break.
- `disabled_tools` strip in `_normalize_surface_fields`: `test_surface_names_are_stripped_and_others_kept` FAILED with the strip disabled, and now also asserts the STORED `disabled_tools` through `env.store.load`.
- Empty-entry drop: `test_empty_entry_is_accepted_and_dropped` stayed GREEN with the drop removed, because the later `_drop_surface_override` pass masks it (the layering the squawk warned of). Added `test_normalize_drops_an_empty_entry_on_its_own`, which calls `_normalize_surface_fields` directly; FAILED with the drop removed.
- `manage.strip_surface_overrides`: both halves (overrides, `disabled_tools`) FAILED the existing `TestStripSurfaceOverrides` tests when disabled. Already effective.
- `projection.py:167` was falsified in sortie 08 and not repeated.
- Optional guard added: `TestNoDirectOverrideLookup` fails on any `<...overrides>.get(<...source>.name)` in `the_one/` outside `override_for`, with two allowed lines (the helper itself and the targeted credential write in `api.py`, which 422s a surface row just above it); it FAILED with a direct lookup put back in `factory.py`. Its pattern is also pinned by a positive test.

## Verification
Done: `scripts/run-tests.sh tests/test_self_configuration_agent_writes.py -x --timeout 60` is 44 passed, run twice; `ruff check` and `ruff format --check` clean. `make test-unit` was NOT run (batch rule: no whole-suite runs; the Flight Director runs it). Original criteria:
For each guard, show the named test failing with the fix removed and passing with it restored. Then run `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_self_configuration_agent_writes.py -x --timeout 60` and `THE_ONE_TEST_NETNS=1 make test-unit`.

Gate (Flight Director, full gate on the final tree, 2026-11-14): unit tier 10155 passed, 15 skipped (under `THE_ONE_TEST_NETNS=1`); browser `PARALLEL_RESULT rc=0 total=2253s lanes=20 failed=-`.

## Sign-Off
**Reviewer**: independent Reviewer (Sonnet tier, because the batch diff touches the MCP sandbox error path), who confirmed the batch diff with `[HANDOFF:confirmed]` on 2026-11-14 with no high or medium issues.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-14` commit on `squawk/turnaround-2026-11-14`
