# Flight Log: Agent Integration & Hardening

**Flight**: [Agent Integration & Hardening](flight.md)

## Summary

Consolidating outstanding hardening items from Flights 01-03 debriefs with remaining Flight 04 scope. Six autonomous legs plus HAT.

---

## Leg Progress

### Leg 01: shared-js-utilities — DONE

- **Scope**: Extract `escapeAttr`, `formatBytes`, `showFlash` into `App` namespace in `app.js`; remove inline copies from `admin.js` and `studio.js`; unify flash CSS under `.app-flash`
- **Changes**:
  - `app.js`: Added `escapeAttr`, `formatBytes` (admin iterative version), `showFlash` (with accessibility attrs); exported all four utilities
  - `admin.js`: Replaced `formatBytes` definition with `App.formatBytes` alias; replaced `showAdminFlash` body with `App.showFlash(contentEl, msg, isError)` delegation; replaced `escapeAttr` definition with `App.escapeAttr` alias
  - `studio.js`: Replaced `showFlash` definition with thin wrapper `App.showFlash(editorEl, msg)`; replaced `formatBytes` (logarithmic) with `App.formatBytes` alias; replaced `escapeAttr` definition with `App.escapeAttr` alias
  - `styles.css`: Added shared `.app-flash`, `.app-flash.visible`, `.app-flash.error` rules; removed `.admin-flash` and `.studio-flash` selectors
- **Deviations**: None — `showAdminFlash` kept as a thin wrapper function (not a raw alias) since it binds `contentEl` and preserves all existing call sites unchanged
- **Tests**: 304 passed, 0 failed

### Leg 02: url-normalization-and-backend-cleanup — DONE

- **Scope**: Consolidate scattered URL normalization into `strip_v1` and `ensure_v1` public functions in `ollama_api.py`; add warning log when `unload_model` polling exhausts
- **Changes**:
  - `ollama_api.py`: Renamed `_normalize_url` to `strip_v1` (public); added `ensure_v1(url)` function; added `import logging` and `logger = logging.getLogger(__name__)`; added `logger.warning(...)` after `unload_model` polling loop exhaustion; updated all internal callers
  - `api.py`: Replaced 3 inline `.rstrip("/").removesuffix("/v1")` calls (lines 407, 481, 522) with `ollama_api.strip_v1()`
  - `ollama_provider.py`: Added `from the_one.llm import ollama_api`; replaced inline ensure-`/v1` logic with `ollama_api.ensure_v1()`
  - `test_ollama_api.py`: Updated existing `TestNormalizeUrl` class to use `strip_v1` (renamed to `TestStripV1OllamaApi`)
  - `test_provider_api.py`: Added `TestStripV1` (5 tests) and `TestEnsureV1` (4 tests) covering trailing slash, `/v1` suffix, `/v1/` suffix, bare URL, already-correct URL
- **Deviations**: Also updated existing tests in `test_ollama_api.py` that referenced the old `_normalize_url` name
- **Tests**: 313 passed, 0 failed

### Leg 03: provider-deletion-protection — DONE

- **Scope**: Block provider deletion when agents reference the provider (409 Conflict), add dedicated `/api/providers/{id}/agents` endpoint, gracefully handle agent creation errors in WebSocket handler, update admin UI to hard-block deletion
- **Changes**:
  - `repositories.py`: Added `list_by_provider(provider_config_id)` method to `SQLiteAgentStore` — queries agents by provider FK, returns name list
  - `api.py`: Added `GET /api/providers/{id}/agents` endpoint returning `{"agents": [...]}` with 404 for unknown providers; modified `DELETE /api/providers/{id}` to check for referencing agents before deletion and return 409 with agent names if any exist
  - `app.py`: Wrapped all 4 `_create_session()` call sites (HTTP chat endpoint + 3 WebSocket actions: join, new_session, auto-join) in try/except for `ValueError`/`KeyError`, sending system error message via WebSocket or returning error dict for HTTP
  - `admin.js`: Updated `handleProviderDelete` to fetch `/api/providers/{id}/agents` on first click; if agents exist, shows "Used by: agent1, agent2" with disabled button (hard-block, no confirm flow); if no agents, shows normal confirm flow
  - `test_provider_api.py`: Added `TestProviderDeletionProtection` class with 5 tests: delete blocked by agents (409), delete allowed without agents (200), agents-by-provider listing, empty agent list, provider not found (404)
- **Deviations**: None
- **Tests**: 318 passed, 0 failed

### Leg 04: first-start-and-model-default — DONE

- **Scope**: Show non-blocking banner in Chat when no providers configured; remove hardcoded `qwen2.5:7b` model default throughout the stack
- **Changes**:
  - `chat.js`: Added `bannerEl` module variable and `checkProviders()` function that fetches `/api/providers` and shows/hides a `.chat-no-providers` banner above messages; called in `onopen` and `activate()`; stored as `_checkProviders` reference
  - `styles.css`: Added `.area-chat .chat-no-providers` rule — centered, muted color, surface background, border-bottom separator
  - `config.py`: Changed `AgentConfig.llm_model` default from `"qwen2.5:7b"` to `""`
  - `schema.py`: Changed both CREATE TABLE `llm_model` defaults from `'qwen2.5:7b'` to `''` (SCHEMA_V1 line 30, migration v3 line 141)
  - `repositories.py`: Changed `_row_to_config` fallback from `or "qwen2.5:7b"` to `or ""`
  - `test_config.py`: Updated assertion from `"qwen2.5:7b"` to `""`
- **Deviations**: None
- **Tests**: 318 passed, 0 failed

### Leg 05: library-cache-and-tests — DONE

- **Scope**: Add in-memory TTL cache to Ollama library search endpoint; add comprehensive test class
- **Changes**:
  - `api.py`: Added `import time`; added module-level `_library_cache` dict and `_LIBRARY_CACHE_TTL = 300`; refactored `search_ollama_library` to check cache freshness before fetching, update cache on success, and fall back to stale cache on fetch failure
  - `test_provider_api.py`: Added `TestOllamaLibrarySearch` class with 7 tests: basic search, empty query, short query, results capped at 30, cache hit (verifies single HTTP call for two searches), HTTP error with no cache returns empty, HTTP error with stale cache falls back to cached data; uses `autouse` fixture to reset `_library_cache` between tests
- **Deviations**: None
- **Tests**: 325 passed, 0 failed

### Leg 06: activate-refresh-convention — DONE

- **Scope**: Audit activate() methods across all three areas; document the convention in app.js
- **Changes**:
  - `app.js`: Added convention comment above `activate()` call in `switchTo()` documenting that activate() must refresh data
- **Audit results**: All three areas already implement the convention correctly:
  - Chat: reconnects WS if needed, fetches agents, checks providers
  - Admin: refreshes settings or provider list based on current category (skips when in form mode)
  - Studio: calls loadAll() to refresh agents, providers, KBs, MCP sources
- **Deviations**: No functional gaps found — convention was already followed, just needed documentation
- **Tests**: No test changes needed

### Leg 07: HAT — DONE

- **Scope**: Interactive human acceptance test covering all changes
- **Results**:
  - First-start banner: PASS — shows appropriate message for no-providers, no-agents, and both-missing states
  - Add provider: PASS — Ollama provider saves, connection test passes
  - Banner dismissal: PASS — banner updates to "No agents" after provider added, disappears after agent created
  - Create agent: PASS — model dropdown shows "Choose a model" placeholder, populates after provider selection
  - Provider deletion protection: not explicitly re-tested (covered by automated tests)
  - Shared JS utilities: PASS — no console errors across all areas
  - Library search cache: not explicitly re-tested (covered by automated tests)
  - Test suite: PASS — 325 passed, 0 failed
- **HAT fixes applied**:
  - `chat.js`: Enhanced `checkProviders` to also check agents, showing contextual banner messages for each state
  - `chat.js`: Made `checkProviders` return its promise, chained before `fetchAgents`/`list_sessions` to avoid race
  - `chat.js`: Skip auto-create session and `+ new` button when banner is showing
  - `chat.js`: Reset `busy`/`sendBtn` state when system error arrives (prevents stuck disabled button)
- **Known issue (deferred)**: First auto-joined session on connect may show "default agent has no provider" error if old sessions exist in DB — user will address separately

---

## Decisions

_(runtime decisions added as needed)_

---

## Deviations

_(departures from plan added as needed)_

---

## Anomalies

_(unexpected issues added as needed)_

---

## Session Notes

### Flight Director Notes

**2026-04-25 — Flight Setup**
- Phase file loaded: project crew from `/home/cprch/projects/the-one/.flightops/agent-crews/leg-execution.md`
- Crew: Developer (Sonnet), Reviewer (Haiku), optional Accessibility Reviewer (Sonnet)
- Git strategy: branch (from flight/03-ollama-model-lifecycle)
- Working directory: `/home/cprch/projects/the-one`
- 7 legs total (6 autonomous + 1 HAT), using fast workflow (deferred review/commit)
