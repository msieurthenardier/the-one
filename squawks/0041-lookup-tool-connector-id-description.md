# Squawk 0041: find_platform_destination's connector_id description invites type-as-id confusion

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-02
**Completed**: 2026-09-03

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

Sharpened `find_platform_destination`'s `connector_id` parameter description
in `the_one/tools/connector_lookup.py` (lines 58-65) from "Optional further
narrowing to one connector. Omit unless you already have a connector_id from
a prior result of this tool." to explicitly name the failure mode: "An
opaque id returned by a prior result of this tool — never the platform type
name (e.g. never 'stub', 'telegram', 'discord'). Omit unless you already
have such an id."

Also aligned the tool's top-level `description` (same file, ~line 44), which
already carried omission guidance, to add the same "opaque id, never the
platform type name" framing so both descriptions state the same rule
consistently.

Checked `tests/test_connector_lookup_tool.py` and `tests/test_factory.py`
for pin tests on the exact description text. `TestSchemaAndDescription`
(`test_connector_lookup_tool.py:342-358`) pins only substring content of
the top-level `description` (`"send_to_platform_channel"`, `"connector_id"`,
`"omit"` present, case-insensitive) — all three still hold with the new
wording. No test pins the parameter-level `connector_id` description text
verbatim, and `test_factory.py` only imports the tool-name constant, so no
pin updates were needed. No behavior change — description text only.

## Verification

`PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_connector_lookup_tool.py tests/test_factory.py -x --timeout 30`
— 46 passed.

`.venv/bin/ruff check the_one/ tests/ && .venv/bin/ruff format --check the_one/ tests/`
— all checks passed, 401 files already formatted.

## Sign-Off
**Reviewer**: independent batch Reviewer (Sonnet — security tier for 0037), squawk/turnaround-2026-09-03
**Verdict**: confirmed
**Commit**: squawk/turnaround-2026-09-03 batch commit (PR follows)
