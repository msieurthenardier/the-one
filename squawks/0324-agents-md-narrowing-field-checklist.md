# Squawk 0324: agents.md has no checklist for adding a narrowing tool-config field

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-03
**Completed**: 2026-11-14

## Report
After sortie 07, one override rule is spread across several places, and nothing mechanical ties them together except the property tests and the browser lanes. A new agent-narrowable tool-config field must be added in each of them. Add a short checklist to `the_one/agents.md` "Agent override validation and clipping (sortie 07)":
- the marker on the field;
- the strict-check rule (`resolve`) and the clip rule (`clip_override`), via the shared per-field helpers;
- the `x_marker` map and the client `allowed()` mirror;
- a row in the property-test generator;
- for host lists, that `NO_HOSTS` is reserved and never shown as a chip.

Never delete information; this squawk only adds the checklist.

## Evidence
- `the_one/agents.md` "Agent override validation and clipping (sortie 07)".
- `the_one/tools/resolver.py::clip_override`, `::resolve`, `::NO_HOSTS`.
- `the_one/interfaces/web/api.py` `x_marker` map.
- `the_one/interfaces/web/static/js/areas/shared/tool-config-fields.js` `allowed()`.
- `tests/test_resolver_clip.py` (property tests).
- `sorties/07-agent-tool-overrides/flight-debrief.md`, Documentation.

## Corrective Action
Added a five-step checklist bullet at the end of `the_one/agents.md` "Agent override validation and clipping (sortie 07)": the marker; the strict check and clip helpers (`check_field` -> `_check_*`, `clip_field` -> `_clip_*`); the `x_marker` map (`api.py::_enrich_schema_with_markers` `marker_map`) with the client `allowed()` mirror and `override_validation.agent_tab_renders` (pinned by `tests/test_agent_notices.py`); the property-test generator (`tests/test_resolver_clip.py` `_typed`, `_gen_row`, `_gen_override`, `_Ctx.list_pool`, the `parametrize` list); and `NO_HOSTS` being reserved and never shown as a chip (`tool-override-state.js`). Nothing was deleted.

## Verification
- The checklist is in agents.md, and every symbol it names exists.
- The doc-reading tests and `make test-unit` pass.

Done: every symbol named in the checklist was grepped in the source (`resolver.py`: `Narrow`..`Substitute`, `_MARKERS`, `check_field`, `clip_field`, `combine_field`, `NO_HOSTS`, the `_check_*` and `_clip_*` helpers; `api.py::_enrich_schema_with_markers`; `tool-config-fields.js::allowed`; `tool-override-state.js` `NO_HOSTS`; the test helpers). The full `make test-unit` was not run (left to the Flight Director).

Gate (Flight Director, full gate on the final tree, 2026-11-14): unit tier 10155 passed, 15 skipped (under `THE_ONE_TEST_NETNS=1`); browser `PARALLEL_RESULT rc=0 total=2253s lanes=20 failed=-`. This covers the full `make test-unit` the Developer left open.

## Sign-Off
**Reviewer**: independent Reviewer (Sonnet tier, because the batch diff touches the MCP sandbox error path), who confirmed the batch diff with `[HANDOFF:confirmed]` on 2026-11-14 with no high or medium issues.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-14` commit on `squawk/turnaround-2026-11-14`
