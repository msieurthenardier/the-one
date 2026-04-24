# Flight Debrief: Ollama Model Lifecycle

**Date**: 2026-04-24
**Flight**: [Ollama Model Lifecycle](flight.md)
**Status**: landed
**Duration**: 2026-04-24 (single session)
**Legs Completed**: 7 of 7

## Outcome Assessment

### Objectives Achieved

The flight fully achieved its objective. Ollama native API integration is complete with model pull, delete, load, and unload operations accessible from the Admin UI. VRAM usage and loaded model status are visible. Studio warns users about model sizes. Auto-load triggers on chat start with a visual loading indicator. Flight 02 debrief items (key rotation atomicity, error handling normalization) are resolved.

### Mission Criteria Advanced

- **Model lifecycle management**: Fully addressed. Pull/delete/load/unload with real-time status, VRAM monitoring, auto-load on conversation start.
- **Encrypted credential storage**: Strengthened. Key rotation atomicity bug fixed -- re-encryption now happens inside the callback before the new key is persisted.
- **Provider connectivity verification**: Improved. All provider types now return consistent 502s on upstream failure instead of unhandled 500s.

## What Went Well

1. **Core architecture held up.** The decision to create a separate `ollama_api.py` module (distinct from `OllamaProvider`) was the strongest design call. Clean separation of lifecycle management from chat, stateless functions accepting `base_url`, consistent error wrapping. No architectural regrets.

2. **Leg sequencing was logical and well-scoped.** Backend hardening first (prerequisite fixes), then API client, then endpoints, then UI layers, then integration, then HAT. Each leg built on the previous with clear boundaries. Test counts grew steadily: 236 -> 276 -> 302 -> 310.

3. **`_get_ollama_base_url` helper pattern.** Centralizes provider lookup, type validation, and URL normalization for all lifecycle endpoints. Good DRY pattern that prevented duplication across 5 endpoints.

4. **Non-blocking auto-load design.** Placing the check in the session layer (`app.py`) rather than `AgentFactory` kept the factory provider-agnostic. The try/except wrapping ensures a failed pre-load never crashes chat. Running on every message (not just session creation) was a pragmatic evolution -- models can be unloaded between messages.

5. **HAT caught real issues.** 8 fixes emerged from HAT that would have degraded user experience in production. The interactive testing format worked well for a UI-heavy flight.

## What Could Be Improved

### Process

- **HAT scope was larger than expected.** The HAT leg absorbed 8 significant fixes: library search endpoint, custom dropdown, pull cancel, Enter key prevention, httpx delete fix, OllamaProvider /v1 fix, unload verification, model selector rewrite. For UI-heavy flights, either budget a larger HAT or include intermediate manual smoke tests within UI legs.
- **External API quirks not anticipated in specs.** `httpx.AsyncClient.delete()` not supporting `json=` body and Ollama's async unload behavior (returns before VRAM is released) were both discoverable during leg design. Future specs for external API integrations should include a "known API quirks" section.
- **UI acceptance criteria were too functional.** Leg specs said things like "pull UI works" but didn't specify UX walkthrough steps. This led to datalist vs. dropdown issues only surfacing during HAT.

### Technical

- **`formatBytes` duplicated** in `admin.js` and `studio.js`. Should be extracted to a shared utility.
- **`/v1` URL normalization scattered** across `ollama_api._normalize_url`, `api._get_ollama_base_url`, and `OllamaProvider.__init__`. Three places doing the same stripping/appending. Should converge to a single utility.
- **`httpx.AsyncClient` created fresh per call** in `ollama_api.py`. No connection pooling. Fine at current scale but inefficient for the auto-load path (runs on every message).
- **`estimate_vram` function implemented but unused.** The Studio VRAM warning uses file size from the models list instead of the parameter-count estimation. Either the spec should have been simpler or the implementation should use the function. Minor dead code.
- **Ollama library search has no caching.** Every keystroke (debounced 300ms) fetches the full model list from `https://ollama.com/api/tags`. A short TTL cache would reduce upstream requests.
- **`unload_model` polling silently gives up.** Polls `/api/ps` up to 20 times, then returns without error if the model is still listed. Should at minimum log a warning.

### Documentation

- Lifecycle endpoints in `api.py` lack docstrings (the search endpoint has one, but the 5 lifecycle endpoints don't).
- SSE streaming format (`data: {json}\n\n`) for the pull endpoint is only documented in the flight log, not in code comments.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| VRAM bar replaced with text summary | Ollama API doesn't expose total GPU VRAM, making a progress bar misleading | Yes -- text-based VRAM display is more honest |
| Model pull input evolved to library search dropdown | HAT revealed users can't guess exact model names | Yes -- searchable inputs for external resources |
| Studio model datalist replaced with select dropdown | HTML datalists unreliable across browsers | Yes -- always use proper select elements |
| Unload verification polling added | Ollama returns from unload before VRAM is released | Yes -- verify async operations complete |
| OllamaProvider auto-appends /v1 | Provider stores base URL without /v1 but chat endpoint needs it | Yes -- defensive URL normalization |

## Key Learnings

1. **HTML datalists are unreliable.** Both the model pull input and Studio model selector had to be rewritten from datalist to custom dropdown/select. Default to proper dropdowns for any data-driven selection.

2. **HAT is essential for UI flights.** Automated tests validate logic but not UX. The 8 fixes from HAT would all have been user-facing bugs. Budget proportionally for UI-heavy flights.

3. **External API proxying needs caching decisions upfront.** The library search endpoint was added reactively during HAT with no caching. Future flight specs that introduce external API proxying should include caching as a design decision.

4. **Bidirectional URL normalization is a code smell.** The Ollama base URL is stored one way, stripped for native API, and re-appended for OpenAI-compatible API. This caused a real bug (chat 404). A single canonical form with documented normalization points would prevent this class of issue.

## Skill Effectiveness

### Mission Skill
- Mission context was clear and well-structured. Success criteria are specific and measurable. The flight list was accurate -- 3 of 5 flights complete, with Flight 03 advancing the model lifecycle criterion significantly.

### Flight Skill
- Flight design was strong. Design decisions were thorough and mostly held up. The 7-leg breakdown was appropriate. One gap: the VRAM estimation design decision specified using `estimate_vram` but the implementation used file size instead -- spec and implementation diverged without explicit acknowledgment.

### Leg Skill
- Leg specs provided sufficient implementation guidance. Acceptance criteria were verifiable. Main weakness: UI legs lacked UX-level acceptance criteria, leading to HAT discovering interaction issues that could have been caught earlier.

## Recommendations

1. **Add "UX walkthrough" acceptance criteria to UI legs.** Instead of just "pull UI works," specify: "user types 2+ chars -> dropdown appears with suggestions -> click selects model -> Pull button starts download -> progress bar shows percentage -> cancel button aborts." This front-loads UX validation before HAT.

2. **Consolidate URL normalization.** Create a single `normalize_ollama_url(base_url, for_native=True)` utility used by `ollama_api.py`, `api.py`, and `OllamaProvider`. Eliminates 3 separate normalization implementations and prevents the /v1 mismatch bug class.

3. **Extract shared JS utilities.** `formatBytes` (and potentially `escapeHtml`, `escapeAttr`) should live in a shared module rather than being duplicated across area files. This is now the second flight where JS duplication has appeared.

4. **Add caching for external API proxies.** The Ollama library search should cache the tag list with a 5-minute TTL. Generalize this: any flight spec that proxies an external API should include a caching design decision.

5. **Wire `estimate_vram` or remove it.** The function exists but is unused. Either the Studio VRAM warning should use it for more accurate estimates, or it should be removed to avoid dead code. Recommend wiring it in -- parameter-count estimation is more accurate than file size.

## Action Items

- [ ] Extract `formatBytes` to shared JS utility (Flight 04 or maintenance)
- [ ] Consolidate `/v1` URL normalization into single utility (Flight 04)
- [ ] Add TTL cache for `/api/ollama-library/search` (Flight 04 or maintenance)
- [ ] Add tests for `search_ollama_library` endpoint (Flight 04 or maintenance)
- [ ] Log warning when `unload_model` polling gives up without confirmation
- [ ] Decide: wire `estimate_vram` into Studio VRAM warning, or remove dead code
- [ ] Future enhancement: GPU VRAM visibility via proxy endpoint on host/Ollama container
