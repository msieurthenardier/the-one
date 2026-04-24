# Flight Log: Provider Data Model & Persistence

**Flight**: [Provider Data Model & Persistence](flight.md)

## Summary

Flight 01 of Mission 03 (LLM Provider Management). Establishing the backend foundation for provider configuration management: encryption, data model, persistence, REST API, and settings migration.

---

## Leg Progress

### Leg 01: Encryption Module

**Status**: completed
**Date**: 2026-04-23

**Outcomes**:
- Created `the_one/encryption.py` with `Encryptor` class and `get_encryptor()` factory
- Public API: `encrypt`, `decrypt`, `encrypt_optional`, `decrypt_optional`, `rotate_key`
- Key file auto-generated at `{data_dir}/encryption.key` with mode 0600
- Added `cryptography>=43.0` to `pyproject.toml` core dependencies
- Created `tests/test_encryption.py` with 18 tests — all passing in 0.07s
- Lint (`ruff check`) and format (`ruff format`) clean

**Notes**:
- `pytest-timeout` not installed in dev deps; ran tests without `--timeout` flag (all completed in <1s)
- No deviations from leg spec

### Leg 02: Provider Model & Schema

**Status**: in-flight
**Date**: 2026-04-23

**Outcomes**:
- Added `LLMProviderConfig` Pydantic model to `the_one/db/models.py` with 8 fields (id, name, type, base_url, api_key, config, created_at, updated_at)
- Added v3 migration to `the_one/db/schema.py` (`CURRENT_VERSION = 3`)
- v3 migration creates `llm_providers` table with CHECK constraint on type, rebuilds `agents` table replacing `llm_provider`/`llm_base_url` with `provider_config_id` FK
- Migration wraps table rebuild in `PRAGMA foreign_keys=OFF/ON` to prevent cascade deletion of chat_sessions
- Created `tests/test_schema.py` with 13 tests — all passing in 0.13s
- Lint (`ruff check`) clean

**Known regression**:
- 24 existing tests in `test_db_api.py`, `test_db_repositories.py`, `test_db_migration.py` now fail with `sqlite3.OperationalError: table agents has no column named llm_provider`. This is expected: `SQLiteAgentStore.save()` still writes to `llm_provider`/`llm_base_url` columns removed by v3. The repository update is explicitly deferred to leg 05 per the flight design.

---

## Decisions

_(runtime decisions will be logged here)_

---

## Deviations

_(departures from planned approach will be logged here)_

---

## Anomalies

_(unexpected issues will be logged here)_

---

## Session Notes

### Flight Director Notes

**Phase file loaded**: `/home/cprch/projects/the-one/.flightops/agent-crews/leg-execution.md` (project-specific)
- Crew: Developer (Sonnet), Reviewer (Haiku), Accessibility Reviewer (Sonnet, optional)
- Git strategy: branch
- Working directory: `/home/cprch/projects/the-one`
