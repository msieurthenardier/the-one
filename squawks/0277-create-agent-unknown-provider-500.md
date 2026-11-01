# Squawk 0277: `POST /api/agents` with an unknown provider id returns 500 (a foreign-key error) instead of 422

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-28
**Completed**: 2026-10-29

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
Completed in Mission 33 Flight 2 leg 2 (flight DD14), limited to the provider; also closes duplicate squawk 0283. `create_agent` and `update_agent` in `the_one/interfaces/web/api.py` call a new `_check_agent_provider` after `AgentConfig` validation. `provider_config_id == ""`, or an id with no provider row (`LLMProviderRepository.get` raising `KeyError`), returns 422 `[{"type":"value_error","loc":["provider_config_id"],"msg":"That model provider doesn't exist."}]`; an absent or `null` id stays legal. On `update_agent` the check runs only when the incoming id differs from the stored one, so an agent whose provider was deleted later stays editable and fixable. `kb_ids` are deliberately not checked (dangling ids are designed, M24 DD-14). Original suggestion: before the save, check that `provider_config_id` (when set) and each `kb_ids` entry exist. On a miss, return 422 with a one-line `loc`/`msg` detail, following the API's existing 422 shape. Apply the same check to `update_agent` if it shares the gap.

## Verification
`tests/test_api_agent_provider_check.py` (5 tests, all pass): create with `""` and with an unknown id gives 422 and no row; update with an unknown id gives 422 and the row unchanged; update round-tripping a stored id whose provider was deleted gives 200 (a different unknown id is still 422); create with no provider (absent and `null`) and with a real provider give 201. `THE_ONE_TEST_NETNS=1 make test-unit`: 8173 passed, 15 skipped. Original plan:
- A unit test against the template database: `POST /api/agents` with an unknown `provider_config_id` returns 422, not 500, and nothing is created.
- The same holds for an unknown `kb_ids` entry, if confirmed.
- A valid create still returns 201.

## Sign-Off
*(written at completion)*
**Reviewer**: Mission 33 Flight 2 Batch A Reviewer (Sonnet), a separate agent from the implementing Developer
**Verdict**: `[HANDOFF:confirmed]`. Create checks the provider; update checks only a changed id; a null provider stays legal; an agent whose provider was deleted stays editable.
**Commit**: the Mission 33 Flight 2 Batch A checkpoint on `flight/02-agent-routines` (`flight/2: agent routines batch A`). Completed inside the flight (flight DD14, a recorded deviation from the squawk branch scheme).
