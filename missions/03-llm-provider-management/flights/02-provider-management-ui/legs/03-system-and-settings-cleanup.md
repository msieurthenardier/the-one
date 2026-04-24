# Leg: system-and-settings-cleanup

**Status**: completed
**Flight**: [Provider Management UI](../flight.md)

## Objective

Add the "System" admin category with encryption key rotation, remove stale admin categories and settings sections, and update stale documentation.

## Context

- Flight design: System category with key rotation button; remove "Agents" placeholder; clean up General settings
- `admin.js` currently has `{ id: 'agents', label: 'Agents', active: false }` (placeholder) and `{ id: 'system', label: 'System', active: false }` (placeholder)
- General settings `settingSections` still includes "LLM Configuration" with `llm_provider`, `llm_model`, `llm_base_url` — these fields no longer exist on `Settings`
- `agents.md` references stale config properties (`llm_provider`, `llm_model`) and describes the default agent as "synthesized from env vars"
- Key rotation endpoint: `POST /api/encryption/rotate` (already exists, tested in leg 01)

## Inputs

- `admin.js` — current categories array, `settingSections`, `renderContent()` dispatch
- `styles.css` — existing admin styles
- `agents.md` — stale architecture docs
- `the_one/config.py` — current Settings fields (no LLM fields)

## Outputs

- "System" category active with key rotation UI
- "Agents" category removed from sidebar
- General settings no longer shows "LLM Configuration" section
- `agents.md` updated to reflect provider_config_id architecture

## Acceptance Criteria

- [x] Admin sidebar no longer shows "Agents" category
- [x] "System" category is active (no "Soon" badge) and renders a System panel
- [x] System panel has a "Rotate Encryption Key" button that calls `POST /api/encryption/rotate`
- [x] Rotation button shows success/failure flash feedback
- [x] Rotation button has a confirmation step (double-click pattern) with clear warning text
- [x] General settings no longer shows "LLM Configuration" section (the `settingSections` array and `fieldLabels` are cleaned up)
- [x] `agents.md` no longer references `llm_provider`, `llm_model`, `llm_base_url` as config properties; instead documents `provider_config_id` and the new provider resolution flow
- [x] `ruff check the_one/ tests/` passes clean

## Verification Steps

- Open Admin → verify sidebar shows: General, LLM Providers, System (no Agents)
- Click General → verify no "LLM Configuration" section; only Paths, Server, Concourse CI
- Click System → verify "Rotate Encryption Key" button with warning text
- Click rotate → first click shows confirmation, second click calls API
- Read `agents.md` → verify no stale `llm_provider`/`llm_model` references

## Implementation Guidance

1. **Remove "Agents" category** (`admin.js`)
   - Remove `{ id: 'agents', label: 'Agents', active: false }` from the `categories` array

2. **Activate "System" category** (`admin.js`)
   - Change `{ id: 'system', label: 'System', active: false }` to `active: true`
   - In `renderContent()`, add `else if (currentCategory === 'system') { renderSystemPanel(); }`

3. **Build `renderSystemPanel()`** (`admin.js`)
   - Header: "System"
   - Section: "Encryption" with explanatory text about key rotation
   - Warning text: "Rotating the encryption key re-encrypts all stored API credentials with a new key. This is irreversible."
   - "Rotate Encryption Key" button with double-click confirm pattern
   - On confirm: call `POST /api/encryption/rotate`, show flash feedback
   - Use `.admin-system-*` CSS classes

4. **Clean up General settings** (`admin.js`)
   - Remove the "LLM Configuration" entry from `settingSections`:
     ```js
     { title: 'LLM Configuration', fields: ['llm_provider', 'llm_model', 'llm_base_url'] }
     ```
   - Remove `llm_provider`, `llm_model`, `llm_base_url` from `fieldLabels`

5. **Update `agents.md`** (`the_one/agents.md`)
   - In the config.py section: remove `llm_provider`, `llm_model` from key properties
   - In the AgentConfig section: document `provider_config_id` field
   - In Key Patterns > Multi-Agent: update "default agent synthesized from env vars" to reflect that the default agent has `provider_config_id=None` and must be configured through the UI
   - Add brief mention of `encryption.py` and `db/repositories.py` for LLMProviderRepository
   - Keep changes minimal — only fix stale references, don't rewrite the whole doc

6. **Add CSS** (`styles.css`)
   - `.admin-system-section` — section container
   - `.admin-system-warning` — warning text with orange/amber styling
   - `.admin-system-btn` — button styling
   - `.admin-system-btn-confirm` — red confirm state

## Edge Cases

- **Key rotation while no providers exist**: The endpoint handles this gracefully (no rows to re-encrypt). The UI should still work.
- **Key rotation failure**: The endpoint is transactional — if re-encryption fails, the old key is preserved. Show error flash.
- **Settings API still returns LLM fields**: The `GET /api/settings` endpoint returns all `Settings` fields. Since `llm_provider` etc. were removed from `Settings`, they won't appear. No API changes needed.

## Files Affected

- `the_one/interfaces/web/static/js/areas/admin.js` — remove Agents, activate System, clean up General
- `the_one/interfaces/web/static/styles.css` — system panel styles
- `the_one/agents.md` — update stale references

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] Commit all changes together (code + artifacts)
