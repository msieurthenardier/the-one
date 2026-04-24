# Leg: lifecycle-endpoints

**Status**: completed
**Flight**: [Ollama Model Lifecycle](../flight.md)

## Objective

Add backend API endpoints for Ollama model lifecycle operations: pull (SSE streaming), delete, load, unload, and status. All endpoints validate the provider is ollama-type and proxy to the `ollama_api` module.

## Context

- Leg 02 created `the_one/llm/ollama_api.py` with all the underlying async functions
- The flight spec defines these endpoints:
  - `POST /api/providers/{id}/models/pull` — streams pull progress (SSE)
  - `POST /api/providers/{id}/models/delete` — delete a pulled model
  - `POST /api/providers/{id}/models/load` — load into VRAM
  - `POST /api/providers/{id}/models/unload` — unload from VRAM
  - `GET /api/providers/{id}/models/status` — loaded models with VRAM info
- Model name goes in request body (not URL path) because Ollama model names contain colons
- SSE for pull progress is chosen because the Admin page has no WebSocket connection
- The existing `list_provider_models` ollama branch can be refactored to use `ollama_api.list_models`

## Inputs

- `the_one/llm/ollama_api.py` — async functions for all lifecycle operations
- `the_one/interfaces/web/api.py` — existing provider endpoints and patterns
- `the_one/db/repositories.py` — `LLMProviderRepository` for provider lookup

## Outputs

- `the_one/interfaces/web/api.py` — 5 new endpoints + refactored ollama branch in `list_provider_models`
- `tests/test_provider_api.py` — tests for all new endpoints

## Acceptance Criteria

- [ ] `POST /api/providers/{id}/models/pull` accepts `{"model": "name"}`, validates provider is ollama-type, returns SSE stream (`text/event-stream`) with progress events from `ollama_api.pull_model`
- [ ] `POST /api/providers/{id}/models/delete` accepts `{"model": "name"}`, validates ollama-type, calls `ollama_api.delete_model`, returns 200 on success
- [ ] `POST /api/providers/{id}/models/load` accepts `{"model": "name"}`, validates ollama-type, calls `ollama_api.load_model`, returns 200 on success
- [ ] `POST /api/providers/{id}/models/unload` accepts `{"model": "name"}`, validates ollama-type, calls `ollama_api.unload_model`, returns 200 on success
- [ ] `GET /api/providers/{id}/models/status` validates ollama-type, calls `ollama_api.list_running`, returns running models with VRAM info
- [ ] All lifecycle endpoints return 400 if provider is not ollama-type
- [ ] All lifecycle endpoints return 404 if provider not found
- [ ] All lifecycle endpoints return 502 on upstream Ollama failure
- [ ] Existing `list_provider_models` ollama branch refactored to use `ollama_api.list_models`
- [ ] Tests cover success, wrong provider type, provider not found, and upstream failure for each endpoint
- [ ] All existing tests still pass
- [ ] No ruff violations

## Verification Steps

- `cd /home/cprch/projects/the-one && python -m pytest tests/ -x --timeout=30`
- `cd /home/cprch/projects/the-one && ruff check the_one/`

## Implementation Guidance

1. **Add request model for lifecycle endpoints**
   - Simple Pydantic model or just use `Request` body parsing: `{"model": "name"}`
   - Keep it lightweight — a dict from `request.json()` or a small Pydantic `BaseModel` with a `model` field

2. **Helper to get ollama provider base_url**
   - Create a helper that loads provider by ID, validates it's ollama-type, and returns the base_url (stripped of `/v1`)
   - Returns 404 if not found, 400 if not ollama-type
   - Reuse across all 5 lifecycle endpoints

3. **Implement the 5 endpoints in `api.py`**
   - Import: `from the_one.llm import ollama_api` and `from fastapi.responses import StreamingResponse`
   - `pull`: Use `StreamingResponse` with `media_type="text/event-stream"`. Wrap `ollama_api.pull_model` async generator — yield each progress dict as `data: {json}\n\n` SSE format. On error mid-stream, yield `data: {"error": "message"}\n\n` so the frontend knows.
   - `delete`, `load`, `unload`: Simple POST handlers that call the corresponding `ollama_api` function and return `{"status": "ok"}`. Wrap exceptions in HTTPException(502).
   - `status`: GET handler calling `ollama_api.list_running`, returns the list directly. Wrap exceptions in HTTPException(502).

4. **Refactor `list_provider_models` ollama branch**
   - The ollama branch currently has a try/except from leg 01's error normalization. Replace the entire try block contents (inline httpx call) with `ollama_api.list_models(provider.base_url)`. Keep the except wrapper.
   - `ollama_api.list_models` returns raw Ollama dicts with `name` and `size` keys. Map to `[{"id": m["name"], "name": m["name"], "size": m.get("size")}]` format to match existing contract.

5. **Tests in `test_provider_api.py`**
   - Import in api.py: `from the_one.llm import ollama_api` — then patch at `the_one.interfaces.web.api.ollama_api.{function_name}`
   - Test each endpoint: success, provider not found (404), wrong type (400), upstream failure (502)
   - Test the SSE pull endpoint yields correctly formatted events

## Edge Cases

- **SSE client disconnect during pull**: `StreamingResponse` handles this — the generator is abandoned and httpx cleans up
- **Empty model name**: Return 400 with clear message
- **Provider deleted mid-operation**: The helper validates at call time — race conditions are acceptable

## Files Affected

- `the_one/interfaces/web/api.py` — 5 new endpoints, refactored ollama branch, helper function
- `tests/test_provider_api.py` — new tests for lifecycle endpoints

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] Commit all changes together (code + artifacts)
