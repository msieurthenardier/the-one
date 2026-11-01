# Squawk 0257: Agent tool overrides are stored without validation

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-25
**Completed**: —
**Related**: claimed by sortie 07 (agent tool overrides), planned on branch `sortie/07-agent-tool-overrides` and not yet in `sorties/`; complete it there ([maintenance 2026-10-30](../maintenance/2026-10-30.md)).

## Report
`PUT /api/agents/{name}` stores `tool_overrides` as sent. An override that widens the operator's value, or fails the tool's schema (a negative timeout, say), is saved without complaint and only fails when the agent is next built. At that point `resolver.resolve` raises.

Mission 31 Flight 4's HAT (ledger row 51) closed the client path: the agent Tools tab now blocks out-of-range values before Save. The API path is still open, and so is any value saved before that fix.

## Evidence
- `the_one/interfaces/web/api.py:update_agent`: the only `tool_overrides` handling is squawk 0223's preserve-on-omit (`if "tool_overrides" not in data`). There is no validation.
- `the_one/tools/resolver.py:resolve`: Narrow fields raise `ValueError` on a widening override (`_check_narrow`), and `schema.model_validate(merged)` raises on a value out of the schema's bounds. Both happen at build time.

**Expected:** the PUT (and create) run each override through the resolver against the current tool config, and return 422 with the field named, so a bad override never reaches the database.

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
