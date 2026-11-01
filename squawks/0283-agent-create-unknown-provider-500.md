# Squawk 0283: Creating an agent with an empty or unknown provider id returns 500, not 422

**Status**: completed
**Duplicate of**: [0277](0277-create-agent-unknown-provider-500.md)
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-29
**Completed**: 2026-10-29

## Duplicate
Closed into squawk 0277 at the Mission 33 Flight 1 debrief (2026-10-29): same route, same root cause (`create_agent` never checks the provider exists before `store.save`). All tracking, the fix and the sign-off live on 0277; this file stays as the record of the third hit.

## Report
`POST /api/agents` with `"provider_config_id": ""` (and presumably any id with no `llm_providers` row) returns **500 Internal Server Error** instead of a 422 naming the field. Nothing is persisted. A client sending a stale or blank provider id should get a field error it can show, not a crash.

This was found during the Mission 33 Flight 1 leg 10 behavior test, `tests/behavior/routine-connector-delivery/runs/2026-10-29-03-31-37.md`, step 1 (the Executor's unintended first agent create). It is unrelated to routines and pre-existing.

Repro (dev instance, credential attached):

```
POST /api/agents {"name":"x","provider_config_id":"","llm_model":"mock-default"}
```

The response is 500. The server log shows `sqlite3.IntegrityError: FOREIGN KEY constraint failed`.

## Evidence
- In `the_one/interfaces/web/api.py::create_agent`, `AgentConfig.model_validate(data)` accepts the empty id. After that the route checks the self-configuration guards and the name conflict, then calls `store.save(cfg)`. Nothing checks that the provider exists, so the `agents` → `llm_providers` foreign key raises inside `save`. The 422 wrapping covers only the pydantic validation.
- `update_agent` (PUT) should be checked for the same gap when this is fixed.

## Deferral
**Reason**: found mid-flight (Mission 33 Flight 1), outside that flight's charter. It is not grounding, because nothing is created and the UI only ever sends a provider id from its picker.
**Revisit trigger**: closes with squawk 0277. When 0277 is completed, mark this one completed with the same commit reference (duplicate, no separate fix).

## Corrective Action
*(written at completion)*
Likely fix: before `store.save`, look up the provider by id and raise a 422 list on `loc ["provider_config_id"]` (the `_validation_detail` shape the forms map to fields) when it is missing or empty. Apply the same check in `update_agent` when the id changes.

## Verification
*(written at completion)*
A unit test POSTs an empty id and an unknown id, and asserts 422 with `loc ["provider_config_id"]` and no agent row. If the PUT is fixed, the same applies to it.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
