# Squawk 0257: Agent tool overrides are stored without validation

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-25
**Completed**: 2026-10-31
**Related**: claimed by sortie 07 (agent tool overrides), planned on branch `sortie/07-agent-tool-overrides` and not yet in `sorties/`; complete it there ([maintenance 2026-10-30](../maintenance/2026-10-30.md)).

## Report
`PUT /api/agents/{name}` stores `tool_overrides` as sent. An override that widens the operator's value, or fails the tool's schema (a negative timeout, say), is saved without complaint and only fails when the agent is next built. At that point `resolver.resolve` raises.

Mission 31 Flight 4's HAT (ledger row 51) closed the client path: the agent Tools tab now blocks out-of-range values before Save. The API path is still open, and so is any value saved before that fix.

## Evidence
- `the_one/interfaces/web/api.py:update_agent`: the only `tool_overrides` handling is squawk 0223's preserve-on-omit (`if "tool_overrides" not in data`). There is no validation.
- `the_one/tools/resolver.py:resolve`: Narrow fields raise `ValueError` on a widening override (`_check_narrow`), and `schema.model_validate(merged)` raises on a value out of the schema's bounds. Both happen at build time.

**Expected:** the PUT (and create) run each override through the resolver against the current tool config, and return 422 with the field named, so a bad override never reaches the database.

## Corrective Action
Sortie 07 leg 2 (`save-and-notices`). `create_agent` and `update_agent` now call `the_one/tools/override_validation.py::validate_overrides` (in a worker thread) after the agent validates and the credential-override guard passes, and before the provider check and the name-conflict check. Only fields that are new or differ from the stored value (JSON-canonical comparison) are checked, each in order: marker present, `check_field` against the app-wide row (widening, type mismatch, unreadable path), then the field's own pydantic bounds and type through `TypeAdapter(Annotated[annotation, *metadata])`; a cross-field rule (default above maximum) is run over a candidate entry that passes the unchanged stored fields through `clip_override`, so a stale stored field never blocks an unrelated save. A failure is a 422 with `detail = [{"type": "tool_override", "loc": ["tool_overrides", tool, field], "msg": sentence}]`, one entry per failing field; an unknown tool is `loc ["tool_overrides", tool]`. A stored stale entry is instead clipped when the agent is built (leg 1) and surfaced as a derived `notices` entry on every agent response.

## Verification
`tests/test_api_agent_tool_override_validation.py` (28 tests) covers the 422 shape, every failure family with its exact sentence (including the negative timeout from this report) and the changed-fields-only rule. Falsified: with the `update_agent` call removed five tests fail; with every field checked instead of only changed ones seven fail. Left open for the flight commit.

## Sign-Off
**Reviewer**: the sortie 07 flight Reviewer (Sonnet tier, security-sensitive diff). It had no knowledge of the Developers' reasoning and read the save path in `api.py` (`_validate_tool_overrides`) and `override_validation.py`.
**Verdict**: `[HANDOFF:confirmed]` in all three review cycles. Closing gate: unit tier 8556 passed (the 3 baseline `test_desktop_host.py` failures only); `--parallel 3` with only squawk 0303's and 0304's known flakes, each passing on an isolated re-run.
**Commit**: the sortie 07 flight commit on `sortie/07-agent-tool-overrides` (`sortie/07: agent tool overrides`).
