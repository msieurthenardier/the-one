# Leg: provider-api-endpoints

**Status**: completed
**Flight**: [Provider Data Model & Persistence](../flight.md)

## Objective

Add REST API endpoints for LLM provider management: full CRUD, connection testing, model discovery, and encryption key rotation. These endpoints power the UI built in Flight 02.

## Context

- Legs 01-03 completed: encryption module, schema v3 with `llm_providers` table, `LLMProviderRepository` with encrypted credentials
- Existing API pattern in `api.py`: helper functions return repository instances, endpoints use `APIRouter` with `/api` prefix
- The `LLMProviderRepository` requires an `Encryptor` — the helper function needs to create/cache one
- Connection testing and model discovery involve provider-specific HTTP calls:
  - **ollama**: native API at `{base_url without /v1}` — `/api/tags` for models, health check via `/api/tags`
  - **openai-compatible**: `/v1/models` for models (graceful degradation), health check via `/v1/models`
  - **openai**: OpenAI SDK `client.models.list()` for models and implicit connectivity check
  - **anthropic**: Anthropic SDK `client.models.list()` for models and implicit connectivity check
- The flight design decision specifies provider type → LLMProvider class mapping:
  - `ollama` and `openai-compatible` both use `OllamaProvider` (httpx-based, OpenAI-compatible `/v1/` endpoint)
  - `openai` uses `OpenAIProvider` (OpenAI SDK)
  - `anthropic` uses `AnthropicProvider` (Anthropic SDK)
- Connection test and model discovery do NOT use the LLMProvider classes — they make direct HTTP/SDK calls since they need provider-native APIs (not the chat completions endpoint)
- API key masking: GET endpoints should return masked API keys (e.g., `sk-...XYZ`) to avoid exposing secrets in the UI

## Inputs

- `the_one/interfaces/web/api.py` — existing REST API with router pattern
- `the_one/db/repositories.py` — `LLMProviderRepository` with CRUD + encryption
- `the_one/encryption.py` — `get_encryptor`, `Encryptor`
- `the_one/config.py` — `settings.data_dir` for encryption key path

## Outputs

- Provider CRUD endpoints added to `api.py`
- Connection test endpoint
- Model discovery endpoint
- Encryption key rotation endpoint
- `tests/test_provider_api.py` — endpoint tests

## Acceptance Criteria

- [x] `GET /api/providers` returns list of all provider configs (API keys masked)
- [x] `GET /api/providers/{id}` returns a single provider (API key masked)
- [x] `POST /api/providers` creates a new provider config (status 201), auto-generating a 12-char hex ID if not provided
- [x] `PUT /api/providers/{id}` updates an existing provider, returns 404 if not found
- [x] `DELETE /api/providers/{id}` deletes a provider, returns 404 if not found
- [x] `POST /api/providers/{id}/test` tests connectivity to the provider, returns `{"status": "ok", "detail": ...}` on success or `{"status": "error", "detail": ...}` on failure
- [x] `GET /api/providers/{id}/models` returns a list of models from the provider API, each with at least `id` and `name` fields; returns 404 if provider not found
- [x] `POST /api/encryption/rotate` rotates the encryption key and re-encrypts all stored API keys
- [x] API keys in GET responses are masked (show only last 4 chars with prefix like `***...XXXX`), or `null` if no key
- [x] Model discovery for `openai-compatible` gracefully returns an empty list if `/v1/models` is not available
- [x] `PUT /api/providers/{id}` detects masked API keys (matching `***...` pattern) and preserves the existing stored key instead of overwriting with the mask string
- [x] `ruff check the_one/interfaces/web/api.py tests/test_provider_api.py` passes
- [x] `pytest tests/test_provider_api.py -v` passes

## Verification Steps

- `ruff check the_one/interfaces/web/api.py tests/test_provider_api.py` — no lint errors
- `pytest tests/test_provider_api.py -v` — all tests pass

## Implementation Guidance

1. **Add helper for `LLMProviderRepository`** in `api.py`:
   ```python
   from the_one.encryption import get_encryptor
   from the_one.db.models import LLMProviderConfig
   from the_one.db.repositories import LLMProviderRepository

   async def _provider_repo() -> LLMProviderRepository:
       conn = await get_connection()
       encryptor = get_encryptor(settings.data_dir)
       return LLMProviderRepository(conn, encryptor)
   ```

2. **Add API key masking helper**:
   ```python
   def _mask_api_key(key: str | None) -> str | None:
       if not key:
           return key
       if len(key) <= 4:
           return "***"
       return f"***...{key[-4:]}"
   ```

3. **Add provider serialization helper** (masks API key for responses):
   ```python
   def _provider_response(provider: LLMProviderConfig) -> dict[str, Any]:
       data = provider.model_dump()
       data["api_key"] = _mask_api_key(provider.api_key)
       return data
   ```

4. **Add CRUD endpoints** following the existing pattern (agents, knowledge bases, etc.):
   - `GET /api/providers` — list all, mask keys
   - `GET /api/providers/{provider_id}` — get one, mask key, 404 if not found
   - `POST /api/providers` — create, auto-generate ID
   - `PUT /api/providers/{provider_id}` — update, 404 if not found
   - `DELETE /api/providers/{provider_id}` — delete, 404 if not found

5. **Add connection test endpoint** `POST /api/providers/{provider_id}/test`:
   ```python
   @router.post("/providers/{provider_id}/test")
   async def test_provider(provider_id: str) -> dict[str, Any]:
       repo = await _provider_repo()
       try:
           provider = await repo.get(provider_id)
       except KeyError:
           raise HTTPException(status_code=404, detail=f"Provider not found: {provider_id}")

       try:
           if provider.type == "ollama":
               # Ollama native API — strip /v1 suffix if present
               base = provider.base_url.rstrip("/").removesuffix("/v1")
               async with httpx.AsyncClient(timeout=10) as client:
                   resp = await client.get(f"{base}/api/tags")
                   resp.raise_for_status()
               return {"status": "ok", "detail": "Connected to Ollama"}
           elif provider.type == "openai-compatible":
               async with httpx.AsyncClient(timeout=10) as client:
                   resp = await client.get(
                       f"{provider.base_url.rstrip('/')}/models",
                       headers=_auth_headers(provider.api_key),
                   )
                   resp.raise_for_status()
               return {"status": "ok", "detail": "Connected"}
           elif provider.type == "openai":
               import openai
               client = openai.AsyncOpenAI(api_key=provider.api_key)
               await client.models.list()
               return {"status": "ok", "detail": "Connected to OpenAI"}
           elif provider.type == "anthropic":
               import anthropic
               client = anthropic.AsyncAnthropic(api_key=provider.api_key)
               await client.models.list()
               return {"status": "ok", "detail": "Connected to Anthropic"}
       except Exception as e:
           return {"status": "error", "detail": str(e)}
   ```

6. **Add model discovery endpoint** `GET /api/providers/{provider_id}/models`:
   - **ollama**: `GET {base}/api/tags` → response has `models` array with `name`, `size`, `parameter_size`, etc. Normalize to `[{"id": name, "name": name, "size": size}, ...]`
   - **openai-compatible**: `GET {base_url}/models` → response has `data` array with `id` field. Gracefully return `[]` if request fails
   - **openai**: `client.models.list()` → returns model objects with `id`. Filter to chat models if possible
   - **anthropic**: `client.models.list()` → returns model objects with `id` and `display_name`
   - Return common shape: `[{"id": str, "name": str, ...extra fields per type}]`

7. **Add encryption key rotation endpoint** `POST /api/encryption/rotate`:

   **Important**: `Encryptor.rotate_key()` uses a synchronous callback which can't contain `await` calls. Use the inline approach instead — decrypt all keys first, rotate with a no-op callback, then re-encrypt:

   ```python
   @router.post("/encryption/rotate")
   async def rotate_encryption_key() -> dict[str, str]:
       encryptor = get_encryptor(settings.data_dir)
       conn = await get_connection()

       # 1. Read and decrypt all stored API keys
       async with conn.execute(
           "SELECT id, api_key FROM llm_providers WHERE api_key IS NOT NULL AND api_key != ''"
       ) as cur:
           rows = await cur.fetchall()
       decrypted = [(row["id"], encryptor.decrypt(row["api_key"])) for row in rows]

       # 2. Rotate key (no-op callback — re-encryption handled below)
       encryptor.rotate_key(lambda old, new: None)

       # 3. Re-encrypt with the now-rotated encryptor
       for provider_id, plaintext in decrypted:
           await conn.execute(
               "UPDATE llm_providers SET api_key = ? WHERE id = ?",
               (encryptor.encrypt(plaintext), provider_id),
           )
       await conn.commit()
       return {"status": "ok"}
   ```

8. **Add `_auth_headers` helper** for OpenAI-compatible providers:
   ```python
   def _auth_headers(api_key: str | None) -> dict[str, str]:
       if api_key:
           return {"Authorization": f"Bearer {api_key}"}
       return {}
   ```

9. **Create `tests/test_provider_api.py`**
   - Use the existing test pattern from `tests/test_db_api.py` — it patches `get_connection` and uses `httpx.AsyncClient` with the FastAPI app
   - **Must also patch `get_encryptor`**: the `_provider_repo()` helper calls `get_encryptor(settings.data_dir)`. Patch it to return a test `Encryptor` backed by a temp key file:
     ```python
     from the_one.encryption import Encryptor
     from cryptography.fernet import Fernet

     # In fixture:
     test_key = Fernet.generate_key()
     key_path = tmp_path / "test.key"
     key_path.write_bytes(test_key)
     test_encryptor = Encryptor(test_key, key_path=key_path)
     # Patch "the_one.interfaces.web.api.get_encryptor" to return test_encryptor
     ```
   - Since connection test and model discovery hit external services, mock them or test only CRUD endpoints
   - Test CRUD: create (201 status), list, get (verify key masked), update, delete, 404 cases
   - Test masked key preservation on update (send back masked key, verify original key preserved)
   - Test key masking logic directly
   - Test rotation endpoint with a provider that has an API key — verify the key is still decryptable after rotation

## Edge Cases

- **Async/sync mismatch in rotate_key**: The `Encryptor.rotate_key` callback is synchronous. The endpoint is async. Handle this carefully — either restructure rotation to work without the callback or use sync DB operations inside the callback.
- **Ollama base_url may or may not have `/v1` suffix**: Strip it for native API calls. Users might enter `http://localhost:11434` or `http://localhost:11434/v1` — handle both.
- **OpenAI/Anthropic SDK not installed**: These are optional dependencies. Connection test and model discovery should catch `ImportError` and return a clear error message.
- **Large model lists**: OpenAI returns hundreds of models. Consider returning all and letting the UI filter.

## Files Affected

- `the_one/interfaces/web/api.py` — add provider endpoints, helpers, rotation endpoint
- `tests/test_provider_api.py` — new file (endpoint tests)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] Commit all changes together (code + artifacts)
