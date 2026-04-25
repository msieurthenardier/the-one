# Flight: Agent Integration & Hardening

**Status**: in-flight
**Mission**: [LLM Provider Management](../../mission.md)

## Contributing to Criteria

- [ ] The system degrades gracefully when a configured provider is unreachable or a requested model is unavailable, surfacing clear feedback to the user
- [ ] On first start with no provider configurations, the application guides the user to set up at least one provider before chat is functional

---

## Pre-Flight

### Objective

Consolidate outstanding hardening items from Flights 01-03 debriefs with remaining Flight 04 scope. Covers: first-start banner in Chat when no providers configured, provider deletion protection (block when agents reference), graceful error handling for null/deleted providers, shared JS utility extraction, URL normalization consolidation, Ollama library search caching, model default cleanup, and cross-area refresh convention.

### Open Questions

_(none — all resolved during planning)_

### Design Decisions

**First-start UX**: Non-blocking banner in Chat area. Fetch `/api/providers` on connect; if empty, show "No providers configured — set one up in Admin to start chatting." Dismisses when providers are later configured (check on activate()).

**Provider deletion**: Block with 409 Conflict when agents reference the provider. New `GET /api/providers/{id}/agents` endpoint returns affected agent names. Admin UI shows the list and hard-blocks deletion.

**Graceful agent errors**: Catch ValueError/KeyError in `app.py._create_session` and send a system message to the WebSocket instead of crashing: "Cannot start chat: Agent 'foo' has no provider configured."

**Shared JS utilities**: Attach to the `App` namespace in `app.js`. `escapeHtml` is already there; add `escapeAttr`, `formatBytes`, `showFlash`, `confirmTimer`. Replace all inline copies in admin.js and studio.js.

**URL normalization**: Two functions — `strip_v1(url)` (for native Ollama API) and `ensure_v1(url)` (for OpenAI-compatible). Place in `ollama_api.py` as public functions. Update all call sites.

**Library search cache**: Module-level dict with timestamp in `api.py`. 5-minute TTL. Cache the full model list; filter from cache on subsequent requests.

**Model default**: Change `AgentConfig.llm_model` default from `"qwen2.5:7b"` to `""`. Studio handles empty gracefully with "Choose a model" placeholder.

### Prerequisites

- [x] Flights 01-03 completed
- [x] Flight spec agreed

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

Six autonomous implementation legs covering JS utilities, backend cleanup, provider deletion protection, first-start flow, library caching, and refresh convention. One HAT leg for end-to-end verification.

### Checkpoints

- [x] Shared utilities extracted, no JS console errors
- [x] URL normalization consolidated, all call sites updated
- [x] Provider deletion blocked when agents reference it
- [x] First-start banner shows when no providers configured
- [x] Library search cache working with 5-min TTL
- [x] All activate() methods refresh data
- [ ] HAT passed

### Adaptation Criteria

**Divert if**:
- Provider deletion protection requires schema changes beyond scope

**Acceptable variations**:
- Minor adjustments to banner styling
- Cache TTL tuning

### Legs

- [x] `shared-js-utilities` — Extract shared JS utilities to App namespace
- [x] `url-normalization-and-backend-cleanup` — Consolidate URL normalization, add unload warning
- [x] `provider-deletion-protection` — Block deletion when agents reference, graceful error handling
- [x] `first-start-and-model-default` — Chat banner for no providers, empty model default
- [x] `library-cache-and-tests` — TTL cache for library search, endpoint tests
- [x] `activate-refresh-convention` — Audit and fix activate() data refresh
- [ ] `hat` — Interactive human acceptance test

---

## Post-Flight

### Completion Checklist

- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing
- [ ] Documentation updated

### Verification

- All existing tests pass (310+)
- New tests for: provider deletion protection (409), agents-by-provider endpoint, library search cache, URL normalization utility
- HAT walkthrough covers end-to-end flow
- No JS console errors after shared utility extraction
