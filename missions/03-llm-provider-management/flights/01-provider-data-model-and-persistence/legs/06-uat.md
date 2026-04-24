# Leg: uat

**Status**: completed
**Flight**: [Provider Data Model & Persistence](../flight.md)

## Objective

End-to-end verification that the backend foundation for LLM provider management works correctly: provider CRUD, connection testing, model discovery, encryption key rotation, and agent-provider integration.

## Context

- Legs 01-05 completed: encryption, schema, repository, API endpoints, settings/agent migration
- All 212 tests pass
- This is the final leg of Flight 01 — interactive UAT

## Acceptance Criteria

- [x] Fresh database: app starts, schema creates `llm_providers` and updated `agents` table
- [x] Create a provider via `POST /api/providers` — returns 201 with masked API key
- [x] List providers via `GET /api/providers` — returns the created provider
- [x] Test connection via `POST /api/providers/{id}/test` — returns status ok (for reachable Ollama)
- [x] Discover models via `GET /api/providers/{id}/models` — returns model list
- [x] Update provider via `PUT /api/providers/{id}` — masked key preserved
- [x] Rotate encryption key via `POST /api/encryption/rotate` — provider still accessible after rotation
- [x] Delete provider via `DELETE /api/providers/{id}` — returns success
- [x] `/api/info` does not return `provider` or `model` fields
- [x] `/api/settings` does not return LLM fields
- [x] `AgentFactory.create()` raises clear error for agent without provider

## Verification Steps

1. Start the app with a fresh database
2. Create an Ollama provider config via API
3. Test connection to the provider
4. Discover models from the provider
5. Update the provider (with masked key)
6. Rotate encryption key, verify provider still works
7. Check /api/info and /api/settings responses
8. Verify AgentFactory error for unconfigured agent
9. Delete the provider
10. All tests still pass

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] If final leg of flight:
  - [x] Update flight.md status to `landed`
  - [x] Check off flight in mission.md
- [x] Commit all changes together (code + artifacts)
