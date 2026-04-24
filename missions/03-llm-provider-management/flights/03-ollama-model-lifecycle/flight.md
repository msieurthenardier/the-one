# Flight: Ollama Model Lifecycle

**Status**: landed
**Mission**: [LLM Provider Management](../../mission.md)

## Contributing to Criteria

- [ ] The system manages model loading on Ollama instances at runtime — loading models on demand when agent conversations start, supporting concurrent models when VRAM allows, and warning users during model selection when a model's size risks exceeding available memory

---

## Pre-Flight

### Objective

Add Ollama native API integration for model lifecycle management. Users can pull, delete, load, and unload models from the Admin provider page with real-time progress. VRAM usage and loaded model status are visible. The Studio model selector warns when a model may not fit in available VRAM. When a conversation starts with an unloaded Ollama model, the system auto-loads it with a "Loading model..." indicator in chat. This flight also addresses critical action items from the Flight 02 debrief: key rotation atomicity and error handling normalization.

### Open Questions

_(none — all resolved during interview)_

### Design Decisions

**Ollama native API client module**: New `the_one/llm/ollama_api.py` module wrapping Ollama's native REST API (`/api/tags`, `/api/ps`, `/api/show`, `/api/pull`, `/api/delete`, `/api/generate` with `keep_alive`). Separate from `OllamaProvider` which uses the OpenAI-compatible `/v1/chat/completions` endpoint for chat. All functions accept `base_url` as a parameter to support multiple Ollama instances.
- Rationale: Clean separation — `OllamaProvider` handles LLM chat, `ollama_api` handles model lifecycle. The native API uses different base URL (no `/v1` suffix) and different response formats.
- Trade-off: Two modules touching the same Ollama instance, but at different API layers

**VRAM estimation from parameter count**: Use `GET /api/show` to get model parameter count/size metadata, estimate VRAM requirement from it (roughly: params * 2 bytes for Q4 quantization, more for higher quant levels). Cross-reference against `GET /api/ps` for actual loaded VRAM when available. When `/api/show` doesn't return usable parameter data, fall back to file size as a proxy (models are typically 40-60% of loaded VRAM size) or show "unknown" with no warning.
- Rationale: Ollama doesn't expose "how much VRAM will this model need" directly. Parameter count is the best available proxy before loading.
- Trade-off: Estimates will be approximate, but sufficient for warnings

**VRAM info in Admin provider page**: The Admin LLM Providers editor (for ollama-type providers) shows a "Models" section with: pulled models list, loaded/unloaded status per model, total VRAM usage bar, per-model VRAM usage, and pull/delete/load/unload action buttons. This replaces the simple model list currently shown after connection test.
- Rationale: Admin is where you manage provider infrastructure; model lifecycle is provider management
- Trade-off: The Admin provider form becomes more complex for ollama types, but other provider types are unaffected

**Model pull with SSE streaming progress**: `POST /api/pull` streams JSON lines with download progress. The backend proxies this as SSE via FastAPI's `StreamingResponse`. The UI shows a progress bar per pull operation with percentage and status. SSE is chosen over WebSocket because the Admin page has no existing WebSocket connection (only Chat does), and SSE is the natural fit for unidirectional server-to-client streaming from a REST endpoint.
- Rationale: Pulling models takes minutes; users need feedback. SSE is simpler than opening a WebSocket just for pull progress.
- Trade-off: Introduces SSE as a new transport pattern alongside the existing WebSocket (Chat). Both are appropriate for their use cases.

**Lifecycle endpoints use request body for model name**: Delete, load, and unload endpoints accept `{"model": "name"}` in the request body rather than model names in URL paths. Ollama model names contain colons (e.g., `qwen2.5:7b`) which can cause encoding issues in URL paths.
- New endpoints:
  - `POST /api/providers/{id}/models/pull` — streams pull progress (SSE), body: `{"model": "name"}`
  - `POST /api/providers/{id}/models/delete` — delete a pulled model, body: `{"model": "name"}`
  - `POST /api/providers/{id}/models/load` — load into VRAM, body: `{"model": "name"}`
  - `POST /api/providers/{id}/models/unload` — unload from VRAM, body: `{"model": "name"}`
  - `GET /api/providers/{id}/models/status` — loaded models with VRAM info (wraps `/api/ps`)
- Rationale: Proxy through the-one's API rather than having the browser hit Ollama directly (CORS, auth, URL abstraction). POST for all mutating operations avoids URL encoding issues.
- Trade-off: More API surface, but necessary for the proxy pattern

**VRAM warning in Studio model selector**: When the selected provider is ollama-type, after model selection, fetch VRAM status and model info. Show an inline warning (amber) if the model likely won't fit: "This model requires ~X GB VRAM, Y GB available — may cause performance issues". Allow selection regardless.
- Rationale: Strong warning, not a block — users may have system RAM fallback or know their setup better
- Trade-off: Extra API call on model selection, but only for ollama providers

**Auto-load in session layer, not AgentFactory**: When a conversation starts, the session creation logic in `app.py` checks if the agent's provider is ollama-type and whether the model is loaded (via `/api/ps`). If not loaded, it triggers a load via the `ollama_api` module and sends a `{"type": "system", "content": "Loading model..."}` WebSocket message while waiting. The `AgentFactory` remains provider-agnostic.
- Rationale: Keeps factory clean and provider-agnostic. Loading indicator logic is co-located with the WebSocket broadcast where it can send real-time feedback.
- Trade-off: Session layer gains provider-type awareness, but only for the auto-load check

**Only ollama-type providers get lifecycle features**: `openai-compatible`, `openai`, and `anthropic` providers are unaffected. The enhanced model section in Admin only renders for `type === "ollama"`. Studio VRAM warnings only trigger for ollama providers.
- Rationale: Model lifecycle is an Ollama-specific concept; other providers manage their own models
- Trade-off: None — clean type-based branching

**Key rotation atomicity fix (debrief item)**: Move re-encryption inside the `rotate_key()` callback so the old key is preserved on disk until all secrets are successfully re-encrypted. Only after the callback completes does the new key get written. This eliminates the data-loss window where the key file is updated but secrets still have old encryption.
- Rationale: Flight 02 debrief flagged this as critical
- Trade-off: None — strictly safer than current approach

**Normalize error handling across provider endpoints (debrief item)**: All provider type branches in `test_provider` and `list_provider_models` wrap exceptions in HTTPException with appropriate status codes (502 for upstream failures). Currently only `openai-compatible` does this; other types let exceptions propagate as unhandled 500s.
- Rationale: Flight 02 debrief flagged this as important. Adding more endpoints in this flight makes normalization urgent.
- Trade-off: None — consistent error handling

### Prerequisites

- [x] Flight 02 completed — Admin provider UI, Studio dropdowns, connection test, model discovery
- [x] Ollama running locally with at least one model pulled
- [x] `GET /api/tags` already used for model discovery (api.py) — will continue alongside new lifecycle endpoints
- [ ] Verify Ollama native API endpoints available: `/api/ps`, `/api/show`, `/api/pull`, `/api/delete`

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

1. **Backend hardening** — Fix key rotation atomicity, normalize error handling across provider endpoints
2. **Ollama native API client** — New module wrapping lifecycle endpoints with async httpx
3. **Backend lifecycle endpoints** — Pull (SSE streaming), delete, load, unload, status endpoints proxied through the-one's API
4. **Admin model lifecycle UI** — Enhanced model section for ollama providers: status indicators, VRAM bar, pull with progress, load/unload/delete actions
5. **Studio VRAM warnings** — Inline warnings on model selection for ollama providers
6. **Auto-load on chat** — Session layer triggers model load if unloaded, WebSocket shows loading indicator
7. **HAT** — Interactive human acceptance testing

### Checkpoints

- [x] Key rotation atomicity fixed, error handling normalized
- [x] Ollama native API client module works with local Ollama instance
- [x] Backend lifecycle endpoints functional (pull, delete, load, unload, status)
- [x] Admin shows model lifecycle UI with VRAM info for ollama providers
- [x] Studio shows VRAM warnings for large models on ollama providers
- [x] Auto-load on conversation start works with loading indicator
- [ ] HAT passed

### Adaptation Criteria

**Divert if**:
- Ollama API doesn't expose sufficient VRAM metadata — fall back to simpler loaded/unloaded indicators without size estimates
- SSE streaming proves unreliable through the proxy — switch to polling-based pull progress

**Acceptable variations**:
- VRAM estimates may be rough (within 2x) — this is expected given quantization variability
- Pull progress granularity may vary by model source
- Load times vary significantly by model size and hardware

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `backend-hardening` — Fix key rotation atomicity (re-encrypt inside callback before new key is persisted). Normalize error handling: wrap all provider type branches in `test_provider` and `list_provider_models` with HTTPException 502 on upstream failure.
- [x] `ollama-api-client` — New `the_one/llm/ollama_api.py` module: async functions for ps (loaded models + VRAM), show (model details + parameter count), pull (async generator yielding progress), delete, load (via generate with keep_alive), unload. All accept base_url parameter. Tests with mocked httpx responses. Fallback handling when /api/show metadata is insufficient.
- [x] `lifecycle-endpoints` — New API endpoints: pull (SSE via StreamingResponse), delete, load, unload, status. All validate provider is ollama-type. Model name in request body (not URL path). Proxies to native API via the client module. Tests for all endpoints.
- [x] `admin-model-lifecycle` — Enhanced Admin provider form for ollama: replace simple model list with lifecycle panel showing loaded/available status, VRAM usage bar, per-model size, pull with progress bar (SSE reader), load/unload/delete buttons. Pull dialog for entering model name. Non-ollama providers keep existing simple model list.
- [x] `studio-vram-warnings` — Studio model selector fetches VRAM status for ollama providers on model selection, shows inline amber warning when estimated model size exceeds available VRAM. No warnings for non-ollama providers.
- [x] `auto-load-on-chat` — Session creation in app.py checks if agent's provider is ollama-type and model is loaded. If not, triggers load via ollama_api and sends "Loading model..." system message over WebSocket. AgentFactory unchanged.
- [x] `hat` — Guided HAT session with iterative fixes

---

## Post-Flight

### Completion Checklist

- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing
- [ ] Documentation updated

### Verification

- Key rotation: rotate key, verify all providers still accessible (no data loss)
- Provider error handling: trigger failures on all 4 provider types, verify consistent 502 responses
- Open Admin → LLM Providers → edit an Ollama provider: see model lifecycle panel with VRAM info
- Pull a new model: progress bar shows download percentage, model appears in list when complete
- Load/unload models: status updates, VRAM bar reflects changes
- Delete a model: removed from list with confirmation
- Studio → select an Ollama provider → pick a large model: VRAM warning appears
- Start a chat with an unloaded Ollama model: "Loading model..." appears, then chat works
- Non-ollama providers: no lifecycle UI, no VRAM warnings (unchanged behavior)
