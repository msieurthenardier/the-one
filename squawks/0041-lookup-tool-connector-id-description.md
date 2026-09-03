# Squawk 0041: find_platform_destination's connector_id description invites type-as-id confusion

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-02
**Completed**: —

## Report

The `directory-lookup-send` stub gate (run 2026-09-02-20-22-46) showed the floor
model repeatedly passing the connector TYPE (`"stub"`) as `connector_id` on first
attempts, recovering only via the no-match message. The parameter description says
"Optional further narrowing to one connector" without contrasting id vs type. Sharpen
it: "connector_id is an opaque id returned by a prior result — never the platform
type name; omit unless you have such an id." The carve-out seeds `to_schema()`, so
the schema-content pin tests may need the new text.

## Evidence

- `the_one/tools/connector_lookup.py:58-65` — the description
- `tests/behavior/directory-lookup-send/runs/2026-09-02-20-22-46.md` — the repeated pattern
- Flight 4 flight-log gate entry named this as a squawk candidate

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
