# Flight Debrief: Provider Data Model & Persistence

**Date**: 2026-04-24
**Flight**: [Provider Data Model & Persistence](flight.md)
**Status**: landed
**Duration**: 2026-04-23 - 2026-04-24
**Legs Completed**: 6 of 6

## Outcome Assessment

### Objectives Achieved

The flight fully achieved its objective: a complete backend foundation for LLM provider management. The system now has:
- Fernet-based encryption with auto-generated key file and rotation
- `LLMProviderConfig` model with schema v3 migration
- `LLMProviderRepository` with transparent encrypt/decrypt
- REST API endpoints: full CRUD, connection testing, model discovery, key rotation
- `AgentConfig` and `AgentFactory` migrated from env-var-based to DB-based provider resolution
- All static LLM env vars removed from `Settings`

### Mission Criteria Advanced

| Criterion | Status | Notes |
|-----------|--------|-------|
| Users can add, edit, and remove LLM provider configurations | Backend complete | API endpoints ready, UI is Flight 02 |
| Multiple instances of same provider type can coexist | Backend complete | Each config has unique ID, no type restrictions |
| API credentials stored encrypted at rest with rotation | Fully met | Fernet encryption, file-based key, rotation endpoint |
| Provider configuration interface discovers available models | Backend complete | `/api/providers/{id}/models` endpoint ready |
| Users can verify provider connectivity | Backend complete | `/api/providers/{id}/test` endpoint ready |

## What Went Well

1. **Zero deviations from plan.** All 6 legs were implemented exactly as specified. No adaptation criteria were triggered. The flight log records no deviations, no anomalies, and no runtime decisions. This is exceptional and reflects thorough upfront design.

2. **Deliberate test regression management.** The decision to tolerate 24 known test failures in Legs 02-04 (from the schema migration removing columns that `SQLiteAgentStore` still referenced) and batch-fix them in Leg 05 was pragmatic. It avoided premature work on the store before the full migration picture was clear.

3. **Design review quality.** The design review cycle caught several critical issues before implementation:
   - FK CASCADE deletion of chat_sessions during agents table rebuild (Leg 02)
   - Async/sync mismatch in `rotate_key()` callback (Leg 04)
   - Masked API key overwrite on PUT (Leg 04)
   - Missing test files (`test_config.py`, `test_factory.py`) in Leg 05 scope
   - `FilesystemConfigStore` backward compatibility needing `extra="ignore"` (Leg 05)

4. **Consistent patterns.** `LLMProviderRepository` follows the exact same structure as existing repositories. The encryption concern is cleanly layered — repositories handle encrypt/decrypt transparently, API endpoints handle masking, and the factory handles type-to-registry mapping.

5. **Comprehensive test coverage.** 212 tests (up from ~65), with notable quality: provider repository tests verify raw DB values to confirm encryption actually occurred, schema migration tests use a separate legacy DDL to properly simulate pre-migration databases.

## What Could Be Improved

### Process

- **CLAUDE.md accuracy.** The CLAUDE.md update states `get_encryptor()` returns a "cached Encryptor instance" but the implementation does not cache. Documentation should reflect actual behavior.
- **Test count in CLAUDE.md** was updated to "~212" but this will drift with future flights. Consider removing the count or making it approximate ("200+").

### Technical

1. **Key rotation endpoint bypasses its own callback pattern.** The `POST /api/encryption/rotate` endpoint manually decrypts all keys, calls `rotate_key(lambda old, new: None)` with a no-op, then re-encrypts. This defeats the atomic callback design of `Encryptor.rotate_key()`. If re-encryption fails partway through, the key file holds the new key but some DB rows still have old-key ciphertext. Not crash-safe.

2. **Connection test and model discovery have zero test coverage.** These are the most complex endpoints (provider-specific HTTP/SDK calls with multiple code paths) but are entirely untested. Even mock-based tests would catch regressions.

3. **`openai-compatible` model discovery silently swallows all exceptions** (`except Exception: return []`), making it impossible to distinguish connectivity failures from "no models available."

4. **No `get_encryptor()` caching.** Each API request and `AgentFactory.create()` call reads the key file from disk. Functionally correct for single-user but wasteful.

5. **No index on `agents.provider_config_id`.** Queries like "which agents use this provider?" require a full table scan. Not critical at current scale but worth adding.

### Documentation

- The flight spec's design decisions section is thorough and serves as good architectural documentation. No significant documentation gaps beyond the CLAUDE.md accuracy issue noted above.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| V1 DDL updated to final schema | Fresh installs get correct schema in one step instead of running through all migrations | Yes — V1 DDL should always represent the current canonical schema |
| `_LEGACY_SCHEMA_V1` in test_schema.py | Migration tests need the pre-migration DDL to properly simulate upgrades | Yes — keep legacy DDL constants in test files for migration testing |
| `model_config = {"extra": "ignore"}` on AgentConfig | Old JSON configs and DB rows may contain removed fields | Yes — defensive pattern for any model that may encounter data from older versions |

## Key Learnings

1. **Tolerating known test failures across legs works when explicitly planned.** The 24 test failures in Legs 02-04 were documented, expected, and batch-resolved in Leg 05. This was more efficient than partial fixes in each leg.

2. **Design review catches real bugs.** The FK cascade deletion issue (Leg 02) would have silently destroyed all chat sessions during migration. The masked key overwrite issue (Leg 04) would have corrupted stored credentials when users edited providers through the UI.

3. **Provider type-to-class mapping is a clean abstraction.** The `_PROVIDER_TYPE_MAP` dict in `factory.py` cleanly bridges the config-layer type system (`ollama`, `openai-compatible`, `openai`, `anthropic`) to the runtime LLM provider registry (`ollama`, `openai`, `anthropic`). This pattern should be reused.

4. **Inline key rotation is simpler but less safe than the callback pattern.** The callback design exists for atomicity, but async constraints made it impractical in the API endpoint. Future flights should either make the callback async-compatible or document the crash-safety trade-off explicitly.

## Recommendations

1. **Add mock-based tests for connection test and model discovery endpoints.** These are the primary UX touchpoints for Flight 02 (UI) and have zero coverage. Highest-impact testing gap.

2. **Fix key rotation to be crash-safe** — either make the `rotate_key()` callback async-compatible, or write the new key to a temp file and atomically rename after DB re-encryption commits.

3. **Cache `get_encryptor()` results** with a module-level singleton keyed by `data_dir` to avoid re-reading the key file on every request.

4. **Add an index on `agents.provider_config_id`** in the next schema migration. Needed for "which agents use this provider?" queries (relevant for provider deletion UX in Flight 02).

5. **Address the "default agent" gap before Flight 02.** `list_agents()` returns a "default" agent that always fails to create (no provider configured). Flight 02 or 04 should handle this — either hide non-functional agents from the list or show a clear "needs configuration" state.

## Skill Effectiveness

### Mission Skill
- The mission provided excellent context. Success criteria were clear and measurable. The resolved questions section captured all key design decisions that informed flight design.

### Flight Skill
- The flight structure was highly effective. Design decisions were thorough enough that zero deviations occurred. The leg breakdown was well-calibrated with clear boundaries between each leg.
- The deliberate test regression strategy (acknowledged in the flight spec) was a good process innovation.

### Leg Skill
- Leg specs were unusually precise. All acceptance criteria were binary and verifiable.
- The implementation guidance code snippets were accurate against the actual codebase.
- One gap: Leg 05 initially missed `test_config.py` and `test_factory.py` as affected files — caught by design review.

### Agentic Workflow
- The Developer/Reviewer cycle worked smoothly. The single blocking issue found by the Reviewer (unused import in Leg 05) was trivial and fixed quickly.
- Design reviews were high-value — they caught 5 substantive issues that would have caused bugs or test failures.

## Action Items

- [ ] Add mock-based tests for connection test and model discovery endpoints (can be done in Flight 02 or as a pre-flight for Flight 02)
- [ ] Fix CLAUDE.md: change "cached Encryptor instance" to "Encryptor instance" (no caching exists)
- [ ] Consider adding `get_encryptor()` caching and `provider_config_id` index in Flight 02's schema work
