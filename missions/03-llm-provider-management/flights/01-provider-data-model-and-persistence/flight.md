# Flight: Provider Data Model & Persistence

**Status**: in-flight
**Mission**: [LLM Provider Management](../../mission.md)

## Contributing to Criteria

- [ ] Users can add, edit, and remove LLM provider configurations through the Administration interface, specifying connection details and credentials for each
- [ ] Multiple instances of the same provider type can coexist with distinct configurations
- [ ] API credentials are stored encrypted at rest, with the encryption key auto-generated on first start and stored on the filesystem outside the database; a rotate function re-encrypts all stored secrets with a new key
- [ ] The provider configuration interface discovers available models by querying provider APIs after credentials are verified
- [ ] Users can verify provider connectivity before saving a configuration

---

## Pre-Flight

### Objective

Establish the backend foundation for LLM provider management: a Pydantic data model for provider configurations, Fernet-based encryption for API credentials, a SQLite schema migration, a CRUD repository, and REST API endpoints including connection testing and model discovery. Remove the static LLM env vars from Settings and update AgentConfig to reference provider configs by ID. This flight delivers the complete backend — Flight 2 builds the UI on top.

### Open Questions

_(none — all resolved at mission level and during design review)_

### Design Decisions

**Provider config data model**: Each provider config has an `id` (12-char hex, consistent with KnowledgeBase/MCPSource/ChatSession), user-chosen `name`, `type` (one of: ollama, openai-compatible, openai, anthropic), `base_url`, encrypted `api_key`, and a JSON `config` field for type-specific settings.
- Rationale: The `type` field determines which `LLMProvider` class to instantiate and which API features are available (model lifecycle, model discovery). The `config` JSON field provides extensibility without schema changes.
- Trade-off: JSON config is less queryable than normalized columns, but provider-specific settings are rarely queried independently.

**Provider type to LLMProvider class mapping**: The four config types map to runtime provider classes as follows:
- `ollama` → `OllamaProvider` (uses Ollama's `/v1/` for completions, native `/api/` for model lifecycle and discovery)
- `openai-compatible` → `OllamaProvider` (reuses the same OpenAI-compatible implementation, no model lifecycle; model discovery attempts `/v1/models` with graceful degradation)
- `openai` → `OpenAIProvider` (uses OpenAI SDK, model discovery via models API)
- `anthropic` → `AnthropicProvider` (uses Anthropic SDK, model discovery via models API)
- Rationale: `OllamaProvider` already works with any OpenAI-compatible server. No new provider class is needed for `openai-compatible` — the distinction exists at the config/lifecycle layer, not the completions layer.

**Agent-to-provider reference**: Replace `llm_provider` + `llm_base_url` on agents with `provider_config_id` (FK to `llm_providers`, ON DELETE SET NULL). Keep `llm_model` on agents since model selection is per-agent, not per-provider.
- Rationale: A single FK cleanly references a specific provider instance. ON DELETE SET NULL means deleting a provider doesn't cascade-delete agents — they just become unusable until reassigned. The model remains agent-level because multiple agents may use the same provider with different models.
- Trade-off: Existing agents in the DB will have NULL `provider_config_id` after migration and won't be usable until updated. This is acceptable since the mission requires provider setup before chat is functional.

**Default agent behavior after Settings removal**: The `AgentFactory._default_config()` method currently synthesizes a default agent from Settings env vars. After removing those vars, the default agent path changes: if no "default" agent exists in the DB, the factory raises an error. The first-start flow (Flight 4) will handle guiding users to create a provider and agent before chat is available.
- Rationale: A non-functional default is worse than a clear error. The system should not pretend to work without a configured provider.

**Encryption approach**: Fernet symmetric encryption from the `cryptography` package (added as a core dependency). Key is auto-generated on first access and stored at `{data_dir}/encryption.key` (file mode 0600). Rotation generates a new key, re-encrypts all stored secrets, and replaces the key file. Empty/None API keys are not encrypted (Ollama configs typically have no key).
- Rationale: Fernet is authenticated encryption (AES-CBC + HMAC), widely trusted, and the `cryptography` package is the standard Python choice. File-based key storage keeps the key outside the DB without requiring env-var provisioning. `cryptography` is a core dependency because encryption is fundamental to provider management.
- Trade-off: Single key file is simpler but less secure than HSM/KMS. Acceptable for a single-user local agent.

**Encryption module placement**: `the_one/encryption.py` (top-level module), not under `db/`.
- Rationale: Encryption is a security/infrastructure concern, not a database concern. The key file lives on the filesystem, and the module may be used by non-DB components in the future.

**Provider types as an enum, not a plugin system**: The four types (ollama, openai-compatible, openai, anthropic) are hardcoded in a Literal type. No dynamic plugin loading.
- Rationale: The existing `LLMProvider` registry already handles the runtime side. Adding a plugin system for four known types is over-engineering.

**Schema migration uses table-rebuild pattern**: SQLite ALTER TABLE DROP COLUMN is only available in 3.35.0+. The v3 migration uses the same table-rebuild pattern proven in the v2 migration (create new table, copy data, drop old, rename). The `llm_providers` table must be created before rebuilding `agents` since the FK references it.

### Prerequisites

- [ ] Mission 03 approved and active
- [ ] `cryptography` package available (will be added to dependencies)

### Pre-Flight Checklist

- [ ] All open questions resolved
- [ ] Design decisions documented
- [ ] Prerequisites verified
- [ ] Validation approach defined
- [ ] Legs defined

---

## In-Flight

### Technical Approach

1. Add `cryptography` to `pyproject.toml` core dependencies
2. Create an encryption module (`the_one/encryption.py`) with Fernet key management, encrypt/decrypt functions, and key rotation
3. Add `LLMProviderConfig` Pydantic model to `the_one/db/models.py`
4. Add schema migration v3 to `the_one/db/schema.py`: create `llm_providers` table first, then rebuild `agents` table (add `provider_config_id` FK with ON DELETE SET NULL, drop `llm_provider`/`llm_base_url` columns). Use table-rebuild pattern.
5. Add `LLMProviderRepository` to `the_one/db/repositories.py` with encrypt-on-write / decrypt-on-read for the `api_key` field (skip encryption for None/empty keys)
6. Add REST API endpoints to `the_one/interfaces/web/api.py`: full CRUD, connection test, model discovery, encryption key rotation
7. Update `the_one/config.py`: remove `llm_provider`, `llm_model`, `llm_base_url` from Settings
8. Update `the_one/agent/config.py`: replace `llm_provider` + `llm_base_url` with `provider_config_id` (nullable str)
9. Update `the_one/agent/factory.py`: resolve provider config from DB via repository instead of `get_provider()` with settings. Default agent errors clearly if no provider is configured.
10. Update `the_one/interfaces/web/app.py`: fix `/api/info` endpoint (remove provider/model fields that came from Settings)
11. Update `the_one/interfaces/web/api.py`: note that `/api/settings` response shape changes (LLM fields removed)
12. Update existing tests, add new tests for encryption and provider repository

### Checkpoints

- [x] Encryption module works: key auto-generation, encrypt/decrypt round-trip, key rotation
- [x] Schema migration runs cleanly on existing v2 databases
- [x] Provider CRUD via REST API works end-to-end (create, read, update, delete)
- [x] API keys are encrypted in DB and decrypted on read
- [x] Connection test endpoint successfully reaches a running Ollama instance
- [x] Model discovery endpoint returns models from a running Ollama instance
- [ ] AgentFactory resolves providers from DB
- [ ] Existing tests pass (updated for schema changes)

### Adaptation Criteria

**Divert if**:
- Fernet encryption introduces async compatibility issues (unlikely — encryption is CPU-bound and fast)
- The agents table migration breaks chat session FK cascades in unexpected ways

**Acceptable variations**:
- Model discovery response format may vary per provider type — normalize to a common shape (id, name, size where available)
- Connection test may return different detail levels per provider type
- If `cryptography` install is problematic in the Docker build, fall back to a simpler encryption approach
- `openai-compatible` model discovery may fail for servers that don't implement `/v1/models` — return empty list with a note, not an error

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `encryption-module` — Create `the_one/encryption.py` with Fernet key management (auto-generate key file at `{data_dir}/encryption.key` with mode 0600, load, rotate), encrypt/decrypt helpers that skip None/empty values, and unit tests
- [x] `provider-model-and-schema` — Add `LLMProviderConfig` Pydantic model to `db/models.py` with id (12-char hex), name, type (Literal), base_url, api_key, config (dict). Schema migration v3: create `llm_providers` table, rebuild `agents` table (add `provider_config_id` FK ON DELETE SET NULL, drop `llm_provider`/`llm_base_url`). Note: `cryptography` dependency already added in leg 01
- [x] `provider-repository` — Add `LLMProviderRepository` to `db/repositories.py` with CRUD operations, encrypt-on-write / decrypt-on-read for api_key, and unit tests
- [x] `provider-api-endpoints` — Add REST endpoints: CRUD (`/api/providers`), connection test (`POST /api/providers/{id}/test`), model discovery (`GET /api/providers/{id}/models`), encryption key rotation (`POST /api/encryption/rotate`). Connection test and model discovery include provider-specific logic: Ollama native API (`/api/tags`), OpenAI-compatible (`/v1/models` with graceful degradation), OpenAI (SDK models list), Anthropic (SDK models list)
- [ ] `settings-and-agent-migration` — Remove `llm_provider`, `llm_model`, `llm_base_url` from Settings. Update AgentConfig: replace `llm_provider` + `llm_base_url` with `provider_config_id`. Update AgentFactory to resolve from DB. Update SQLiteAgentStore for new schema. Fix `/api/info` in app.py. Note `/api/settings` response shape change. Update all affected tests
- [ ] `uat` — End-to-end verification: create provider via API, test connection, discover models, create agent referencing provider, verify factory creates working agent, rotate encryption key, verify secrets still accessible

---

## Post-Flight

### Completion Checklist

- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing
- [ ] CLAUDE.md updated if architecture section changes

### Verification

1. Start the app with a fresh (empty) database — schema migration creates `llm_providers` table
2. Create an Ollama provider config via `POST /api/providers` — verify api_key encrypted in DB (if provided)
3. Test connection via `POST /api/providers/{id}/test` — returns success for reachable Ollama
4. Discover models via `GET /api/providers/{id}/models` — returns list from Ollama
5. Create an agent referencing the provider — verify `AgentFactory.create()` produces a working agent
6. Rotate encryption key via `POST /api/encryption/rotate` — verify all secrets re-encrypted and still decryptable
7. All existing tests pass (updated for schema changes)
8. `/api/info` and `/api/settings` return valid responses without removed LLM fields
