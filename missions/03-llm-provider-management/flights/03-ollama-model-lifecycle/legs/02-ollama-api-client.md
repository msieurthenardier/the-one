# Leg: ollama-api-client

**Status**: completed
**Flight**: [Ollama Model Lifecycle](../flight.md)

## Objective

Create a new `the_one/llm/ollama_api.py` module wrapping Ollama's native REST API for model lifecycle management (list, show, pull, delete, load, unload, running status).

## Context

- The existing `OllamaProvider` in `ollama_provider.py` uses the OpenAI-compatible `/v1/chat/completions` endpoint for chat. This new module uses Ollama's native API (no `/v1` prefix) for lifecycle operations.
- The native API endpoints: `/api/tags` (list models), `/api/ps` (running models + VRAM), `/api/show` (model details), `/api/pull` (download model, streaming), `/api/delete` (remove model), `/api/generate` with `keep_alive` (load/unload)
- All functions accept `base_url` parameter to support multiple Ollama instances
- The module is pure async using httpx — no SDK dependency
- Flight design decision: VRAM estimation uses parameter count from `/api/show`, falls back to file size, or "unknown"
- This module will replace the inline `/api/tags` call in `api.py` `list_provider_models` in leg 03 (lifecycle-endpoints)

## Inputs

- Ollama native API documentation (endpoints described in flight spec design decisions)
- Existing httpx patterns in `ollama_provider.py` and `api.py`
- Test patterns in `tests/test_provider_api.py` (uses `unittest.mock.patch` and `AsyncMock` for external HTTP)

## Outputs

- `the_one/llm/ollama_api.py` — async functions for all lifecycle operations
- `tests/test_ollama_api.py` — tests with mocked httpx responses

## Acceptance Criteria

- [ ] Module provides async functions: `list_models`, `list_running`, `show_model`, `pull_model` (async generator), `delete_model`, `load_model`, `unload_model`
- [ ] All functions accept `base_url: str` parameter
- [ ] `list_models` returns list of model info dicts (name, size, modified date)
- [ ] `list_running` returns running models with VRAM usage info from `/api/ps`
- [ ] `show_model` returns a dict with at minimum: `parameter_size` (int or None), `quantization_level` (str or None), `size` (file size in bytes), plus raw response fields
- [ ] `pull_model` is an async generator yielding progress dicts (status, completed, total) from `/api/pull` streaming response
- [ ] `delete_model` sends DELETE to `/api/delete`
- [ ] `load_model` sends POST to `/api/generate` with `keep_alive` parameter to load into VRAM
- [ ] `unload_model` sends POST to `/api/generate` with `keep_alive: 0` to unload from VRAM
- [ ] All functions handle connection errors gracefully (raise or re-raise with clear messages)
- [ ] Tests cover success paths and error paths for all functions
- [ ] Public `estimate_vram` function: takes show_model output, returns estimated VRAM bytes (int) or None if insufficient metadata
- [ ] Base URL normalization: strips trailing `/` and `/v1` suffix
- [ ] No ruff violations

## Verification Steps

- `cd /home/cprch/projects/the-one && python -m pytest tests/test_ollama_api.py -x --timeout=30`
- `cd /home/cprch/projects/the-one && python -m pytest tests/ -x --timeout=30`
- `cd /home/cprch/projects/the-one && ruff check the_one/llm/ollama_api.py`

## Implementation Guidance

1. **Create `the_one/llm/ollama_api.py`**
   - Define standalone async functions (not a class) — the module is stateless, each call gets `base_url`
   - Strip `/v1` suffix from base_url if present (users may pass the OpenAI-compatible URL)
   - Use `httpx.AsyncClient(timeout=30)` for metadata calls, longer timeout for pull/load
   - `pull_model` should use `httpx.AsyncClient.stream()` to handle the streaming JSON lines response — yield each parsed JSON line as a dict
   - `load_model`: POST to `/api/generate` with `{"model": name, "keep_alive": "24h"}` (or configurable). Ollama loads the model when it receives a generate request with keep_alive.
   - `unload_model`: POST to `/api/generate` with `{"model": name, "keep_alive": 0}` to immediately unload
   - VRAM estimation helper: extract parameter count from show_model response, estimate bytes (params * 2 for Q4_K_M, etc.), or fall back to model file size

2. **Create `tests/test_ollama_api.py`**
   - Use `unittest.mock.patch` on `httpx.AsyncClient` — patch target is `the_one.llm.ollama_api.httpx.AsyncClient` (NOT the api.py path)
   - Test each function's success path with realistic Ollama API response fixtures
   - Test error paths (connection refused, HTTP 404, malformed JSON, httpx.TimeoutException)
   - Test `pull_model` generator yields progress lines correctly
   - Test VRAM estimation with and without parameter metadata

## Edge Cases

- **Missing `/api/show` metadata**: Some models may not have parameter count — fall back to file size or return "unknown"
- **Empty model list**: `/api/tags` with no models pulled returns `{"models": []}`
- **Pull cancellation**: Generator may be abandoned mid-pull — httpx stream cleanup handles this
- **Base URL variants**: Handle `http://localhost:11434`, `http://localhost:11434/`, `http://localhost:11434/v1`

## Files Affected

- `the_one/llm/ollama_api.py` — new file
- `tests/test_ollama_api.py` — new file

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] Commit all changes together (code + artifacts)
