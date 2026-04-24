# Flight: Provider Management UI

**Status**: landed
**Mission**: [LLM Provider Management](../../mission.md)

## Contributing to Criteria

- [ ] Users can add, edit, and remove LLM provider configurations through the Administration interface, specifying connection details and credentials for each
- [ ] Multiple instances of the same provider type can coexist with distinct configurations
- [ ] Users can verify provider connectivity before saving a configuration
- [ ] The provider configuration interface discovers available models by querying provider APIs after credentials are verified
- [ ] The Studio agent editor presents configured providers and their discovered models for selection, replacing free-text entry with dynamic dropdowns

---

## Pre-Flight

### Objective

Build the provider management UI in the Administration area and update the Studio agent editor to use dynamic provider/model selection. This flight also addresses backend gaps from the Flight 01 debrief: missing test coverage for connection test and model discovery endpoints, `get_encryptor()` caching, `provider_config_id` index, and General settings cleanup.

### Open Questions

_(all resolved)_

### Design Decisions

**Provider list as card/table layout in content area**: Cards in the content panel rather than sidebar items — the sidebar already has category navigation (General, LLM Providers, System). Each card shows provider name, type badge, connection status indicator, and action buttons.
- Rationale: Avoids overloading the sidebar which already serves as category navigation
- Trade-off: Less screen real estate for the editor — solved by using an inline expandable editor or a slide-out panel within the content area

**New "LLM Providers" category in Admin sidebar**: Dedicated category replacing the "Integrations" placeholder. "Agents" placeholder also removed (agent management lives in Studio).
- Rationale: LLM providers are the primary integration point; a dedicated category makes them immediately discoverable
- Trade-off: None — replaces an empty placeholder

**Type-specific form fields**: Provider type dropdown dynamically shows/hides fields:
- `ollama` — base_url only (default `http://localhost:11434/v1`)
- `openai-compatible` — base_url + optional api_key
- `openai` — api_key only (base_url defaults to `https://api.openai.com/v1`)
- `anthropic` — api_key only (base_url defaults to `https://api.anthropic.com`)
- Rationale: Reduces confusion — users only see fields relevant to their provider type
- Trade-off: Slightly more complex form logic

**Auto-load models after connection test**: When "Test Connection" succeeds, models are automatically fetched and displayed. A refresh button allows re-fetching models after provider configuration changes.
- Rationale: Reduces click count and immediately confirms the provider is working
- Trade-off: Slightly slower connection test UX (must wait for model fetch too)

**Key rotation under System**: The encryption key rotation button lives under the "System" admin category, not per-provider. It's a global operation affecting all encrypted credentials.
- Rationale: Rotation is a security/maintenance operation, not a per-provider concern
- Trade-off: Users might expect rotation controls near the credentials they're protecting

**Studio provider/model dropdowns**: Replace free-text Provider, Model, and Base URL fields with:
- Provider dropdown populated from `GET /api/providers` (shows provider name, type as subtitle)
- Model dropdown populated from `GET /api/providers/{id}/models` (auto-fetched when provider changes)
- Base URL field removed entirely (it's part of the provider config now)
- Rationale: Constrains selection to configured providers, eliminates invalid combinations
- Trade-off: Agents can only use configured providers (this is the intended design)

**Schema v4 migration for provider_config_id index**: Add `CREATE INDEX idx_agents_provider ON agents(provider_config_id)` to support "which agents use this provider?" queries efficiently. Needed for deletion UX (warn when deleting a provider that agents reference).
- Rationale: Flight 01 debrief recommendation
- Trade-off: Minimal — adding an index is low-risk

**Encryptor caching**: `get_encryptor()` becomes a module-level singleton cached by `data_dir`. The cached instance is the same mutable object that `rotate_key()` updates in-place, so rotation correctly propagates to all callers holding a reference.
- Rationale: Avoids re-reading the key file from disk on every API request
- Trade-off: None — the mutation semantics of `rotate_key()` are preserved

**CLI fix**: `cli.py` references `settings.llm_provider` and `settings.llm_model` which were removed in Flight 01. The CLI banner must be updated to remove these references or show provider info from the DB.
- Rationale: Latent runtime crash — `AttributeError` on any CLI invocation
- Trade-off: None — straightforward fix

**Studio broken state acknowledgment**: The Studio editor's default object and form fields reference `llm_provider`, `llm_base_url`, and `llm_model` — the first two no longer exist in `AgentConfig`. The Studio editor is currently partially broken (create mode sends stale fields, silently dropped by `extra="ignore"`). The `studio-provider-dropdowns` leg is a **fix** of broken functionality, not just an enhancement.

**Default agent handling**: `list_agents()` returns a "default" agent with `provider_config_id=None`. Rather than hiding it, the Studio dropdown should show a "No provider — configure in Admin" placeholder when `provider_config_id` is null. This makes the broken state visible and actionable.
- Rationale: Users need to know why the default agent doesn't work
- Trade-off: None — better UX than a silent failure

### Prerequisites

- [x] Flight 01 completed — backend API endpoints ready
- [x] Provider CRUD endpoints: GET/POST/PUT/DELETE `/api/providers`
- [x] Connection test: `POST /api/providers/{id}/test`
- [x] Model discovery: `GET /api/providers/{id}/models`
- [x] Encryption rotation: `POST /api/encryption/rotate`
- [x] `AgentConfig` has `provider_config_id` field
- [x] `AgentFactory` resolves providers from DB

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

1. **Backend hardening** — Add tests for untested endpoints, cache `get_encryptor()`, add `provider_config_id` index, fix `openai-compatible` error swallowing, fix CLI crash
2. **Admin LLM Providers** — New category with card/table layout, inline editor with type-specific forms, connection test button, model auto-discovery with refresh, delete with agent-usage warning
3. **Admin System & General cleanup** — System category with key rotation, remove stale categories/settings sections, update stale docs
4. **Studio provider/model dropdowns** — Fix broken LLM fields, constrain to configured providers, handle unconfigured agents
5. **HAT** — Interactive human acceptance testing across all UI changes

### Checkpoints

- [x] Backend hardening complete — all endpoints tested, encryptor cached, index added, CLI fixed
- [x] Provider CRUD + test + model discovery UI working in Admin
- [x] System category with key rotation functional, General settings cleaned up
- [x] Studio agent editor uses provider/model dropdowns with null-provider handling
- [ ] HAT passed

### Adaptation Criteria

**Divert if**:
- Provider card layout proves unusable — switch to full sidebar-list pattern like Studio
- Model discovery UX is too slow for inline display — switch to a separate "Models" tab/section

**Acceptable variations**:
- Minor layout adjustments to card sizing and form placement
- Simplifying model display to just names (omitting size/metadata) if response formats vary
- Adjusting default base URLs if provider conventions differ

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `backend-hardening` — Add mock tests for connection test/model discovery endpoints, cache `get_encryptor()`, schema v4 (provider_config_id index), fix openai-compatible silent exceptions, fix CLI crash (`settings.llm_provider`/`settings.llm_model` references)
- [x] `provider-list-and-editor` — Admin "LLM Providers" category with card/table layout, add/edit form with type-specific fields, CRUD wired to API, connection test + model auto-discovery + refresh
- [x] `system-and-settings-cleanup` — Admin "System" category with encryption key rotation, remove stale categories ("Agents", "Integrations"), update General settings (remove LLM section), update stale docs (`agents.md`)
- [x] `studio-provider-dropdowns` — Fix broken Studio LLM fields: replace free-text provider/model/base_url with provider dropdown + model dropdown, handle null provider_config_id with actionable placeholder
- [ ] `hat` — Guided HAT session with iterative fixes across all UI changes

---

## Post-Flight

### Completion Checklist

- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing
- [ ] Documentation updated

### Verification

- Open Admin → LLM Providers: can add, edit, delete providers of all 4 types
- Connection test shows clear success/failure feedback
- Models auto-load after successful connection test; refresh button re-fetches
- Deleting a provider in use shows warning about affected agents
- System → Rotate Key works and providers remain accessible
- Studio agent editor shows provider dropdown and model dropdown
- Agents with no provider show actionable "configure in Admin" placeholder
- General settings page no longer shows LLM fields
- CLI does not crash on startup
- All existing tests pass, new endpoint tests pass
