# Squawk 0277: `POST /api/agents` with an unknown provider id returns 500 (a foreign-key error) instead of 422

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-28
**Completed**: —

## Report
Creating an agent whose `provider_config_id` names no provider returns HTTP **500**. The cause is an uncaught `sqlite3.IntegrityError: FOREIGN KEY constraint failed`, which comes from the repository save. The request should get a plain 422 on the field.

- **Where it surfaced:** the Mission 31 Flight 6 leg 09b behavior sweep (`list-and-detail`).
- **How:** the Executor's seed script had a bug and sent `provider_config_id: ""` (and an empty `kb_ids` entry) on 31 agent creates. Every one returned 500.
- **Impact:** no data was created. The web UI never sends an unknown provider id (the editor's select only offers real providers), so this is an API-boundary robustness gap, not a user-facing flow.

- **Hit again:** Mission 33 Flight 1, leg 10 behavior test (`tests/behavior/routine-connector-delivery/runs/2026-10-29-03-31-37.md`, step 1). The Executor sent `provider_config_id: ""`, and the 500 was logged in duplicate as squawk 0283. That makes three behavior-test runs across two missions. The M33 F1 debrief recommends completing it before Mission 33 Flight 2's behavior test.

## Evidence
- The dev instance log for that run (`$HOME/the-one-bt-m31f6/list-and-detail/cwd/serve.log`) shows `POST /api/agents` 500, ending in `the_one/interfaces/web/api.py::create_agent` → `await store.save(cfg)` (about `:1053`) → `the_one/db/repositories.py` `save` (about `:254`) → `sqlite3.IntegrityError: FOREIGN KEY constraint failed`.
- `create_agent` already maps `AgentConfig` validation errors to 422 (about `:1029-1033`). Referential integrity is only enforced by the database, and nothing catches that failure.
- An unknown `kb_ids` entry probably fails the same way, through the `agent_knowledge_bases` foreign key. This is unverified; check it in the same fix.

## Corrective Action
*(written at completion)*
Likely fix: before the save, check that `provider_config_id` (when set) and each `kb_ids` entry exist. On a miss, return 422 with a one-line `loc`/`msg` detail, following the API's existing 422 shape. Apply the same check to `update_agent` if it shares the gap.

## Verification
*(written at completion)*
- A unit test against the template database: `POST /api/agents` with an unknown `provider_config_id` returns 422, not 500, and nothing is created.
- The same holds for an unknown `kb_ids` entry, if confirmed.
- A valid create still returns 201.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
