# Squawk 0324: agents.md has no checklist for adding a narrowing tool-config field

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-03
**Completed**: —

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
*(written at completion)*

## Verification
- The checklist is in agents.md, and every symbol it names exists.
- The doc-reading tests and `make test-unit` pass.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
