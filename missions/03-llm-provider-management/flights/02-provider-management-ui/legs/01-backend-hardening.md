# Leg: backend-hardening

**Status**: completed
**Flight**: [Provider Management UI](../flight.md)

## Objective

Harden the backend by adding tests for untested endpoints (connection test, model discovery), caching `get_encryptor()`, adding a `provider_config_id` index, fixing silent exception swallowing in `openai-compatible` model discovery, and fixing the CLI crash from removed settings fields.

## Context

- Flight 01 debrief recommended: test coverage for connection test and model discovery endpoints, `get_encryptor()` caching, `provider_config_id` index
- `cli.py:37` references `settings.llm_provider` and `settings.llm_model` which were removed from `Settings` in Flight 01 — this causes `AttributeError` on any CLI invocation
- `api.py:520-521` silently swallows all exceptions during `openai-compatible` model discovery, returning an empty list with no indication of failure
- `get_encryptor()` (`encryption.py:70-84`) re-reads the key file from disk and creates a new `Encryptor` on every call — should be cached as a module-level singleton

## Inputs

- `the_one/encryption.py` — current `get_encryptor()` with no caching
- `the_one/interfaces/cli.py` — references `settings.llm_provider` and `settings.llm_model`
- `the_one/interfaces/web/api.py` — `test_provider` and `list_provider_models` endpoints, `openai-compatible` silent `except Exception`
- `the_one/db/schema.py` — schema at v3, needs v4 for `provider_config_id` index
- `tests/test_provider_api.py` — existing CRUD tests, no tests for `/test` or `/models` endpoints

## Outputs

- `get_encryptor()` returns a cached singleton per `data_dir`, with `rotate_key()` mutations propagating correctly
- CLI banner no longer crashes — shows agent name/model or a generic banner instead of removed settings
- `openai-compatible` model discovery returns error info instead of silently returning `[]`
- Schema v4 migration adds `CREATE INDEX idx_agents_provider ON agents(provider_config_id)`
- Tests exist for connection test endpoint (all 4 provider types, success and failure)
- Tests exist for model discovery endpoint (all 4 provider types, success and failure)

## Acceptance Criteria

- [x] `get_encryptor()` caches by `data_dir` — calling it twice with the same path returns the same `Encryptor` instance
- [x] `rotate_key()` on the cached instance correctly updates the singleton in-place (existing behavior preserved)
- [x] CLI starts without `AttributeError` — banner shows useful info without referencing removed fields; gracefully handles `ValueError` from `factory.create()` when no provider is configured
- [x] `openai-compatible` model discovery raises `HTTPException` (or returns error detail) instead of silently returning `[]` on failure
- [x] Schema `CURRENT_VERSION` is 4; v4 migration creates `idx_agents_provider` index
- [x] Tests for `POST /api/providers/{id}/test` cover all 4 types with mocked success and mocked failure
- [x] Tests for `GET /api/providers/{id}/models` cover all 4 types with mocked responses
- [x] `pytest tests/ -v` passes with no failures
- [x] `ruff check the_one/ tests/` passes clean

## Verification Steps

- `python -c "from the_one.encryption import get_encryptor; from pathlib import Path; import tempfile; d = Path(tempfile.mkdtemp()); e1 = get_encryptor(d); e2 = get_encryptor(d); assert e1 is e2"`
- `python -c "from the_one.interfaces.cli import run"` — imports without error
- `pytest tests/test_provider_api.py -v` — all new tests pass
- `pytest tests/test_schema.py -v` — schema version is 4
- `ruff check the_one/ tests/`

## Implementation Guidance

1. **Cache `get_encryptor()`** (`the_one/encryption.py`)
   - Add a module-level `_cache: dict[str, Encryptor] = {}` keyed by `str(data_dir.resolve())`
   - On cache hit, return the existing instance; on miss, create, cache, and return
   - `rotate_key()` already mutates `self._fernet` and `self._key` in-place, so all holders of the cached reference see the new key — no additional changes needed

2. **Fix CLI crash** (`the_one/interfaces/cli.py`)
   - Line 37: `f"Provider: {settings.llm_provider} / {settings.llm_model}\n"` — both fields no longer exist on `Settings`
   - Additionally, `factory.create()` (line 29) raises `ValueError` when `provider_config_id is None` (which is the case for the default agent). The banner print is at line 34, so the crash happens *before* the banner
   - Fix approach: move the banner print *before* `factory.create()`, and wrap `factory.create()` in a try/except that catches `ValueError` and prints a user-friendly message like "No provider configured — set one up in Admin at http://host:port"
   - The banner itself should not reference `settings.llm_provider`/`settings.llm_model` — use generic info like version and tool count, or nothing
   - Example banner: `f"[bold]the-one[/bold] v0.1.0\nType [bold]/quit[/bold] to exit, [bold]/reset[/bold] to clear context."`

3. **Fix `openai-compatible` silent exception** (`the_one/interfaces/web/api.py`)
   - In `list_provider_models`, the `openai-compatible` branch (lines 510-521) catches all exceptions and returns `[]`
   - Change to re-raise as `HTTPException(502, detail=str(e))` so the UI can show the error
   - Alternatively, return `{"error": str(e)}` — but HTTP 502 is more standard for upstream failures

4. **Schema v4 migration** (`the_one/db/schema.py`)
   - Update `CURRENT_VERSION = 4`
   - Add `if version < 4:` block that runs `CREATE INDEX IF NOT EXISTS idx_agents_provider ON agents(provider_config_id)`
   - Insert version 4 into `schema_version`

5. **Add connection test endpoint tests** (`tests/test_provider_api.py`)
   - Use `unittest.mock.patch` to mock external calls (httpx, openai, anthropic)
   - Test each of the 4 provider types:
     - `ollama`: mock `httpx.AsyncClient.get` for `{base}/api/tags`
     - `openai-compatible`: mock `httpx.AsyncClient.get` for `{base_url}/models`
     - `openai`: mock `openai.AsyncOpenAI.models.list`
     - `anthropic`: mock `anthropic.AsyncAnthropic.models.list`
   - Test success (returns `{"status": "ok", ...}`) and failure (returns `{"status": "error", ...}`)

6. **Add model discovery endpoint tests** (`tests/test_provider_api.py`)
   - Similar mocking strategy as connection test
   - `ollama`: mock response with `{"models": [{"name": "qwen2.5:7b", "size": 123}]}`
   - `openai-compatible`: mock response with `{"data": [{"id": "model-1"}]}`
   - `openai`: mock `client.models.list()` returning model objects
   - `anthropic`: mock `client.models.list()` returning model objects
   - Test that the response format is normalized: `[{"id": ..., "name": ...}]`

## Edge Cases

- **Encryptor cache with different `data_dir` paths**: Two different directories must get separate `Encryptor` instances — key by resolved path
- **CLI with no agents**: `factory.create()` returns a default agent — the banner should handle `provider_config_id=None` gracefully
- **`openai-compatible` model discovery with auth failure vs network failure**: Both should surface the error, not silently return `[]`
- **Schema v4 on fresh DB**: `SCHEMA_V1` already creates the table without the index; v4 migration adds it. `CREATE INDEX IF NOT EXISTS` is safe for fresh DBs that run all migrations sequentially

## Files Affected

- `the_one/encryption.py` — add caching to `get_encryptor()`
- `the_one/interfaces/cli.py` — fix banner to not reference removed settings
- `the_one/interfaces/web/api.py` — fix `openai-compatible` silent exception
- `the_one/db/schema.py` — add v4 migration for `provider_config_id` index
- `tests/test_provider_api.py` — add connection test and model discovery tests
- `tests/test_encryption.py` — add test for `get_encryptor()` caching

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] Commit all changes together (code + artifacts)
