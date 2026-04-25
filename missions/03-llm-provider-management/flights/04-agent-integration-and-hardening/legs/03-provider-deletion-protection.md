# Leg: provider-deletion-protection

**Status**: completed
**Flight**: [Agent Integration & Hardening](../flight.md)

## Objective

Block provider deletion when agents reference the provider (409 Conflict with agent list), add a dedicated endpoint to query affected agents, and gracefully handle agent creation when the provider is missing or deleted.

## Context

- The DELETE endpoint currently allows deleting providers even when agents reference them, leaving agents with orphaned `provider_config_id` values
- `factory.create()` raises `ValueError` when `provider_config_id is None` (line 39) and `KeyError` when the provider doesn't exist in DB (line 53) — both propagate unhandled to the WebSocket handler
- Admin.js already has a soft-confirm pattern that counts agents using `GET /api/agents`, but it doesn't hard-block deletion
- The design decision calls for a hard-block: 409 from the backend, UI shows affected agent names and prevents deletion

## Inputs

- `the_one/interfaces/web/api.py` — `delete_provider` endpoint (lines 461-468)
- `the_one/interfaces/web/app.py` — `_create_session` (lines 105-141), WebSocket handler with `new_session` action (line 547-561)
- `the_one/interfaces/web/static/js/areas/admin.js` — `handleProviderDelete` (lines 373-426)
- `the_one/db/repositories.py` — `SQLiteAgentStore` with agent CRUD
- `the_one/agent/factory.py` — `create()` raises ValueError/KeyError for missing providers

## Outputs

- New `GET /api/providers/{id}/agents` endpoint returning agent names
- `DELETE /api/providers/{id}` returns 409 when agents reference it
- `_create_session` catches ValueError/KeyError and sends system error message via WebSocket
- Admin UI hard-blocks deletion when agents reference the provider

## Acceptance Criteria

- [ ] `GET /api/providers/{id}/agents` returns `{"agents": ["agent1", "agent2"]}` listing agent names that reference the provider
- [ ] `GET /api/providers/{id}/agents` returns 404 if provider doesn't exist
- [ ] `DELETE /api/providers/{id}` returns 409 with `{"detail": "Provider is used by agents: agent1, agent2"}` when agents reference it
- [ ] `DELETE /api/providers/{id}` succeeds (200) when no agents reference it
- [ ] When `_create_session` fails due to ValueError or KeyError from the factory, the WebSocket sends `{"type": "system", "content": "Cannot start chat: <error message>"}` instead of crashing
- [ ] Admin UI: first click on Delete fetches `/api/providers/{id}/agents`; if agents exist, shows their names and disables the delete button (hard-block, not just confirm); if no agents, shows normal confirm flow
- [ ] New tests for: 409 on delete with agents, 200 on delete without agents, agents-by-provider endpoint
- [ ] All existing tests pass

## Verification Steps

- `python -m pytest tests/ --timeout=30 -x -q` passes
- Test: create provider, create agent referencing it, try DELETE provider → 409
- Test: create provider, no agents reference it, DELETE → 200
- Test: GET /api/providers/{id}/agents returns correct agent list

## Implementation Guidance

1. **Add `list_by_provider(provider_config_id)` method** to `SQLiteAgentStore` in `repositories.py`:
   - Query: `SELECT name FROM agents WHERE provider_config_id = ? ORDER BY name`
   - Return list of agent name strings

2. **Add `GET /api/providers/{id}/agents` endpoint** in `api.py`:
   - Use `SQLiteAgentStore.list_by_provider(provider_id)` to get agent names
   - Return `{"agents": [list of agent names]}`
   - Return 404 if provider doesn't exist

3. **Modify `DELETE /api/providers/{id}`** in `api.py`:
   - **IMPORTANT**: The DB schema uses `ON DELETE SET NULL` — `repo.delete()` will succeed and silently null the FK. The application-level check MUST happen before the delete call.
   - Before calling `repo.delete()`, query agents by provider_config_id using the new method
   - If any agents found, return `HTTPException(status_code=409, detail=f"Provider is used by agents: {', '.join(names)}")`
   - Otherwise proceed with deletion as before

4. **Catch errors in WebSocket handler** in `app.py`:
   - Wrap `_create_session()` calls (lines 457, 512, 552, 590) in try/except for ValueError and KeyError
   - On catch, send `{"type": "system", "content": f"Cannot start chat: {str(e)}"}` via the WebSocket
   - Don't create/join a session — leave session as None (or previous session)

5. **Update `handleProviderDelete` in admin.js**:
   - First click: fetch `/api/providers/{id}/agents`
   - If `agents.length > 0`: show agent names in button text ("Used by: agent1, agent2"), add a disabled/blocked style, do NOT set confirm class (no second click allowed)
   - If `agents.length === 0`: show normal confirm flow (existing pattern)
   - Reset timer still applies for the confirm case

6. **Add tests** in `test_provider_api.py`:
   - `TestProviderDeletionProtection` class:
     - `test_delete_blocked_by_agents` — create provider, create agent referencing it, DELETE → 409
     - `test_delete_allowed_without_agents` — create provider, DELETE → 200
     - `test_agents_by_provider` — create provider, create 2 agents referencing it, GET → returns both names
     - `test_agents_by_provider_empty` — create provider, no agents, GET → empty list
     - `test_agents_by_provider_not_found` — GET with fake ID → 404

## Edge Cases

- **Agent referencing deleted provider (pre-existing data)**: The graceful error handling in `_create_session` covers this — if an agent's provider was deleted before this protection was added, the error is caught and surfaced
- **Provider ID doesn't exist**: Both endpoints return 404
- **Concurrent deletion**: If agents are removed between the check and the delete, the deletion succeeds (acceptable race condition)

## Files Affected

- `the_one/interfaces/web/api.py` — New endpoint, modified delete
- `the_one/interfaces/web/app.py` — Error handling in WebSocket handler
- `the_one/interfaces/web/static/js/areas/admin.js` — Updated delete handler
- `the_one/db/repositories.py` — New `list_by_provider` method on SQLiteAgentStore
- `tests/test_provider_api.py` — New test class
