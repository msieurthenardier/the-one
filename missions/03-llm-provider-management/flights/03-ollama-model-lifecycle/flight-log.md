# Flight Log: Ollama Model Lifecycle

**Flight**: [Ollama Model Lifecycle](flight.md)

## Summary

Flight 03 of Mission 03 (LLM Provider Management). Adding Ollama native API integration for model lifecycle management -- pull, delete, load, unload with VRAM monitoring. Enhanced Admin UI with progress bars and status indicators. Studio VRAM warnings. Auto-load on conversation start.

---

## Leg Progress

### Leg 01: backend-hardening (completed)
- **Started**: 2026-04-24
- Fixed key rotation atomicity: pre-fetch and decrypt all API keys before calling `rotate_key`, re-encrypt inside the sync callback (closure captures plaintext list, writes `(id, ciphertext)` tuples), DB writes happen after `rotate_key` returns with new key on disk
- Normalized error handling in `list_provider_models`: wrapped `ollama`, `openai`, and `anthropic` branches in try/except raising HTTPException(502), matching the existing `openai-compatible` pattern
- Verified `test_provider` error handling is already consistent (generic catch-all returns 200 with error status for all types) -- no changes needed
- Updated 3 existing failure tests (ollama, openai, anthropic model discovery) from expecting raw exceptions to asserting 502 responses
- Added 2 new rotation tests: empty table no-op and multi-provider re-encryption
- All 236 tests passing, no ruff violations

### Leg 02: ollama-api-client (completed)
- **Started**: 2026-04-24
- Created `the_one/llm/ollama_api.py` -- standalone async functions wrapping Ollama native REST API
- Functions: `list_models`, `list_running`, `show_model`, `pull_model` (async generator), `delete_model`, `load_model`, `unload_model`, `estimate_vram`
- All functions accept `base_url` parameter with `/v1` suffix stripping
- Uses `httpx.AsyncClient` with appropriate timeouts (30s metadata, 300s load, 600s pull)
- `pull_model` uses `client.stream()` for streaming JSON lines
- `estimate_vram` uses parameter count + quantization bits-per-param with 10% overhead, falls back to file size
- Connection and timeout errors wrapped in clear `ConnectionError` messages; 404s raise `ValueError`
- Created `tests/test_ollama_api.py` -- 40 tests covering all success/error paths
- All 276 tests passing, no ruff violations

### Leg 03: lifecycle-endpoints (completed)
- **Started**: 2026-04-24
- Added 5 new endpoints to `the_one/interfaces/web/api.py` under `/api/providers/{id}/models/`:
  - `POST .../pull` -- SSE streaming via `StreamingResponse` with `text/event-stream`, yields `data: {json}\n\n` format; errors mid-stream yield `data: {"error": "..."}\n\n`
  - `POST .../delete` -- calls `ollama_api.delete_model`, returns `{"status": "ok"}`
  - `POST .../load` -- calls `ollama_api.load_model`, returns `{"status": "ok"}`
  - `POST .../unload` -- calls `ollama_api.unload_model`, returns `{"status": "ok"}`
  - `GET .../status` -- calls `ollama_api.list_running`, returns running models list
- Created `_get_ollama_base_url` helper: validates provider exists (404), is ollama-type (400), strips `/v1` suffix
- All lifecycle endpoints validate empty model name (400) and wrap upstream errors as 502
- Refactored `list_provider_models` ollama branch to delegate to `ollama_api.list_models`
- Added 26 new tests in `tests/test_provider_api.py` covering success, not-found, wrong-type, upstream-failure, and empty-model for all endpoints
- All 302 tests passing, no ruff violations

### Leg 04: admin-model-lifecycle (completed)
- **Started**: 2026-04-24
- Added `renderOllamaModels(providerId, container)` function in admin.js -- replaces simple model list for ollama providers
- Fetches both `/models` and `/models/status` in parallel using `Promise.all`
- VRAM summary: text-based display showing total VRAM used by loaded models (accent-colored), "No models loaded", or "VRAM info unavailable"
- Model rows split into "Running" (green dot, unload button) and "Available" (gray dot, load + delete buttons) sections
- Pull UI: inline input with ReadableStream SSE reader for POST-based streaming progress
- SSE parser handles `data: {...}\n\n` format, progress bar with percentage, handles `{"status": "success"}` terminal event and `{"error": "..."}` events
- Delete confirmation uses same double-click pattern as provider deletion
- All action buttons show loading state, inline error on failure, full panel refresh on success
- Added `formatBytes` helper for human-readable sizes
- CSS: 30+ new rules using `admin-pf-` prefix for model rows, dots, pull progress, VRAM summary, action buttons
- Non-ollama providers continue using existing `fetchProviderModels` path unchanged
- All 302 tests passing, no ruff violations

### Leg 05: studio-vram-warnings (completed)
- **Started**: 2026-04-24
- Added VRAM warning system to Studio model selector for ollama providers
- When model input changes (debounced 500ms), fetches `/models/status` and `/models` in parallel
- If selected model is already loaded (running): no warning shown
- If model is not loaded and found in available models list: shows amber warning with model size and current VRAM load
- Warning text: "This model requires ~X GB. Currently Y GB loaded across Z models."
- Warning clears on provider change, model change to a loaded model, or non-ollama provider
- Added `formatBytes` helper, `getSelectedProviderType`, `clearVramWarning`, `checkVramForModel`, `debouncedVramCheck` functions
- CSS: `.studio-vram-warning` with amber border-left, translucent amber background, hidden by default, `.visible` shows it
- Warning element uses `role="status"` and `aria-live="polite"` for accessibility
- All dynamic text passed through `escapeHtml`
- Network errors silently clear warning (non-blocking)
- All 302 tests passing, no ruff violations

### Leg 06: auto-load-on-chat (completed)
- **Started**: 2026-04-24
- Added `_ensure_ollama_model_loaded()` helper in `app.py` -- called at start of `_process_and_broadcast()` before `agent.step()`
- Uses Option B from leg spec: looks up agent config from `SQLiteAgentStore` using `session.agent_name`, then fetches `LLMProviderConfig` from `LLMProviderRepository`
- If provider type is "ollama": calls `ollama_api.list_running()` to check loaded models, handles `:latest` tag matching
- If model not loaded: sends `{"type": "system", "content": "Loading model..."}` to session subscribers, then awaits `ollama_api.load_model()`
- Non-ollama providers and default agents without DB records skip entirely
- Entire check wrapped in try/except -- errors logged but never crash the session
- Check runs on every message (ollama_api.list_running is fast, model may be unloaded between messages)
- AgentFactory remains unchanged (provider-agnostic)
- Added `get_encryptor` import to app.py (needed for `LLMProviderRepository` construction)
- Created `tests/test_auto_load.py` with 8 tests: load when not running, skip when loaded, skip non-ollama, skip default agent, connection error handling, load error handling, `:latest` tag matching, different model no-match
- All 310 tests passing, no ruff violations

### Leg 07: hat (completed)
- **Started**: 2026-04-24
- All 9 verification steps passed
- Fixes applied during HAT:
  - **Ollama library search endpoint**: Added `GET /api/ollama-library/search` proxying `https://ollama.com/api/tags` with query filtering; custom dropdown suggestions UI replacing unreliable HTML datalists
  - **Pull cancel support**: Added AbortController to pull fetch, cancel button in progress bar
  - **Enter key prevention**: Disabled Enter-to-pull on input, require explicit Pull button click
  - **Delete model fix**: `httpx.AsyncClient.delete()` doesn't support `json=` body; switched to `client.request("DELETE", ...)`
  - **OllamaProvider /v1 fix**: Auto-append `/v1` to base URL for OpenAI-compatible chat endpoint when missing
  - **Auto-load feedback**: Added "Model loaded." system message after load completes; chat UI shows spinning braille animation during load
  - **Unload verification**: `unload_model` now polls `/api/ps` until model is actually released before returning
  - **Studio model dropdown**: Replaced datalist with proper `<select>` dropdown for model selection, matching provider dropdown UX

---

## Decisions

_(no runtime decisions beyond HAT fixes above)_

---

## Deviations

- Pull model UX was originally a plain text input; evolved to custom dropdown with library search during HAT
- Studio model selector changed from datalist to select dropdown during HAT

---

## Anomalies

- `deepseek-v3.2` listed in Ollama library API without a default tag; pulling it fails with "file does not exist" -- Ollama registry issue, not actionable on our side

---

## Session Notes

### HAT Session -- 2026-04-24

**HAT feedback -- pull model UX**: User noted that the pull input requires typing the exact model name with no assistance. Addressed in-flight: added `/api/ollama-library/search` endpoint and custom dropdown suggestions UI with cancel support.

**HAT feedback -- VRAM warning: show available GPU memory**: User requested the Studio VRAM warning show total/available GPU VRAM, not just loaded model sizes. Ollama's API doesn't expose GPU info; `nvidia-smi` is available on the host but not accessible from the app container. Out of scope -- logged as a future enhancement. Could be solved by exposing a GPU info proxy endpoint on the host or Ollama container.
