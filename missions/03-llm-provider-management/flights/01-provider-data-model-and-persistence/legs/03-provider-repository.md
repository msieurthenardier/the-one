# Leg: provider-repository

**Status**: completed
**Flight**: [Provider Data Model & Persistence](../flight.md)

## Objective

Add `LLMProviderRepository` to `the_one/db/repositories.py` with full CRUD operations and transparent encrypt-on-write / decrypt-on-read handling for the `api_key` field.

## Context

- Leg 01 completed: `the_one/encryption.py` provides `Encryptor` with `encrypt_optional`/`decrypt_optional`
- Leg 02 completed: `llm_providers` table exists in schema v3, `LLMProviderConfig` model in `db/models.py`
- Existing repositories follow a consistent pattern: `__init__(conn)`, list/get/create/update/delete methods, static `_row_to_model`, `_now_iso()` helper
- The repository needs an `Encryptor` instance to handle API key encryption — passed at construction
- 24 existing tests are failing (SQLiteAgentStore writes to removed columns) — this is expected and deferred to leg 05. The new repository tests must work independently.

## Inputs

- `the_one/db/models.py` — `LLMProviderConfig` model
- `the_one/db/repositories.py` — existing repository pattern (KnowledgeBaseRepository, MCPSourceRepository, etc.)
- `the_one/encryption.py` — `Encryptor` class
- `the_one/db/schema.py` — schema v3 with `llm_providers` table

## Outputs

- `LLMProviderRepository` class added to `the_one/db/repositories.py`
- `tests/test_provider_repository.py` — unit tests

## Acceptance Criteria

- [x] `LLMProviderRepository` exists in `repositories.py` with constructor `__init__(self, conn, encryptor)`
- [x] `list()` returns all providers ordered by name
- [x] `get(provider_id)` returns a single provider, raises `KeyError` if not found
- [x] `create(provider)` inserts a new provider, encrypting `api_key` if present
- [x] `update(provider)` updates an existing provider, encrypting `api_key` if present, raises `KeyError` if not found
- [x] `delete(provider_id)` deletes a provider, raises `KeyError` if not found
- [x] API keys are encrypted before INSERT/UPDATE and decrypted after SELECT
- [x] None/empty API keys pass through without encryption (via `encrypt_optional`/`decrypt_optional`)
- [x] The `config` field is stored as JSON and restored as a dict
- [x] `ruff check the_one/db/repositories.py tests/test_provider_repository.py` passes
- [x] `pytest tests/test_provider_repository.py -v` passes

## Verification Steps

- `ruff check the_one/db/repositories.py tests/test_provider_repository.py` — no lint errors
- `pytest tests/test_provider_repository.py -v` — all tests pass

## Implementation Guidance

1. **Add `LLMProviderRepository` to `repositories.py`** following the existing pattern. Add the import for `LLMProviderConfig` to the imports at the top.

   ```python
   class LLMProviderRepository:
       """Async CRUD for LLM provider configurations."""

       def __init__(self, conn: aiosqlite.Connection, encryptor: Encryptor) -> None:
           self.conn = conn
           self.encryptor = encryptor

       async def list(self) -> list[LLMProviderConfig]:
           async with self.conn.execute(
               "SELECT * FROM llm_providers ORDER BY name"
           ) as cur:
               return [self._row_to_model(r) for r in await cur.fetchall()]

       async def get(self, provider_id: str) -> LLMProviderConfig:
           async with self.conn.execute(
               "SELECT * FROM llm_providers WHERE id = ?", (provider_id,)
           ) as cur:
               row = await cur.fetchone()
           if row is None:
               raise KeyError(f"Provider not found: {provider_id}")
           return self._row_to_model(row)

       async def create(self, provider: LLMProviderConfig) -> None:
           await self.conn.execute(
               "INSERT INTO llm_providers (id, name, type, base_url, api_key, config,"
               " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
               self._to_row(provider),
           )
           await self.conn.commit()

       async def update(self, provider: LLMProviderConfig) -> None:
           if not await self._exists(provider.id):
               raise KeyError(f"Provider not found: {provider.id}")
           await self.conn.execute(
               "UPDATE llm_providers SET name=?, type=?, base_url=?, api_key=?,"
               " config=?, updated_at=? WHERE id=?",
               (
                   provider.name,
                   provider.type,
                   provider.base_url,
                   self.encryptor.encrypt_optional(provider.api_key),
                   json.dumps(provider.config),
                   _now_iso(),
                   provider.id,
               ),
           )
           await self.conn.commit()

       async def delete(self, provider_id: str) -> None:
           if not await self._exists(provider_id):
               raise KeyError(f"Provider not found: {provider_id}")
           await self.conn.execute(
               "DELETE FROM llm_providers WHERE id = ?", (provider_id,)
           )
           await self.conn.commit()

       async def _exists(self, provider_id: str) -> bool:
           async with self.conn.execute(
               "SELECT 1 FROM llm_providers WHERE id = ?", (provider_id,)
           ) as cur:
               return await cur.fetchone() is not None

       def _to_row(self, provider: LLMProviderConfig) -> tuple:
           return (
               provider.id,
               provider.name,
               provider.type,
               provider.base_url,
               self.encryptor.encrypt_optional(provider.api_key),
               json.dumps(provider.config),
               provider.created_at,
               provider.updated_at,
           )

       def _row_to_model(self, row: aiosqlite.Row) -> LLMProviderConfig:
           return LLMProviderConfig(
               id=row["id"],
               name=row["name"],
               type=row["type"],
               base_url=row["base_url"],
               api_key=self.encryptor.decrypt_optional(row["api_key"]),
               config=json.loads(row["config"] or "{}"),
               created_at=row["created_at"],
               updated_at=row["updated_at"],
           )
   ```

2. **Add import** for `Encryptor` at top of repositories.py:
   ```python
   from the_one.encryption import Encryptor
   ```

3. **Create `tests/test_provider_repository.py`**
   - Create a fixture that sets up an in-memory DB with schema, an Encryptor (using `tmp_path`), and returns a `LLMProviderRepository`
   - Test list (empty, then after create)
   - Test create + get round-trip
   - Test create with API key — verify the raw DB value is encrypted (query DB directly), verify get returns decrypted value
   - Test create with None API key — verify None is preserved
   - Test update — verify fields change, updated_at changes
   - Test update with API key change — verify re-encrypted
   - Test delete
   - Test get non-existent — raises KeyError
   - Test delete non-existent — raises KeyError
   - Test config dict stored as JSON and restored

## Edge Cases

- **Encrypted API key format**: Fernet tokens are URL-safe base64. They will contain characters like `=`, `-`, `_`. The TEXT column in SQLite handles these fine.
- **Config dict with nested structures**: `json.dumps`/`json.loads` handles nested dicts and lists. No special handling needed.

## Files Affected

- `the_one/db/repositories.py` — add `LLMProviderRepository` class and `Encryptor` import
- `tests/test_provider_repository.py` — new file (unit tests)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] Commit all changes together (code + artifacts)
