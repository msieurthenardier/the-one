# Leg: backend-hardening

**Status**: completed
**Flight**: [Provider Management UI](../flight.md)

## Objective

Harden the backend by adding test coverage for untested endpoints, caching `get_encryptor()`, adding a `provider_config_id` index, fixing silent exception swallowing, and fixing the CLI crash.

## Acceptance Criteria

- [x] Mock tests for connection test endpoint (POST /api/providers/{id}/test) covering all 4 provider types with success and failure cases (8 new tests)
- [x] Mock tests for model discovery endpoint (GET /api/providers/{id}/models) covering all 4 provider types with success, failure, and not-found cases (9 new tests)
- [x] `get_encryptor()` cached as module-level singleton keyed by resolved data_dir path (3 new tests)
- [x] Schema v4 migration adds `CREATE INDEX IF NOT EXISTS idx_agents_provider ON agents(provider_config_id)`, CURRENT_VERSION updated to 4 (1 new test)
- [x] `openai-compatible` silent exception swallowing in `list_provider_models` fixed -- raises HTTPException(502)
- [x] CLI crash fixed: `settings.llm_provider`/`settings.llm_model` references removed, banner prints before factory.create(), factory.create() wrapped in try/except ValueError

## Implementation Notes

- Used `patch.dict(sys.modules, ...)` for mocking openai/anthropic since they use local imports inside function bodies
- Used `raise_app_exceptions=False` on ASGITransport to properly test 500 responses from unhandled exceptions
