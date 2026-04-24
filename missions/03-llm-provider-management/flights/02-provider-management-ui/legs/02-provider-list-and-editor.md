# Leg: provider-list-and-editor

**Status**: completed
**Flight**: [Provider Management UI](../flight.md)

## Objective

Build the "LLM Providers" category in Admin with a card/table layout for listing providers, an inline add/edit form with type-specific fields, CRUD wired to the API, a connection test button, and model auto-discovery with refresh.

## Context

- Flight design decision: provider list as card/table in content area (not sidebar), "LLM Providers" replaces the "Integrations" placeholder
- Type-specific form fields: `ollama` (base_url), `openai-compatible` (base_url + optional api_key), `openai` (api_key), `anthropic` (api_key)
- Auto-load models after connection test; refresh button to re-fetch
- Delete with agent-usage warning (query agents using this provider via the `provider_config_id` index added in leg 01)
- Existing admin patterns: `admin.js` uses `renderContent()` dispatch by `currentCategory`, `renderGeneralPanel()` for the General category
- Existing styles follow `.area-admin .admin-*` naming convention
- The app is vanilla JS, no frameworks — follow existing patterns (string-concatenated HTML, manual DOM wiring)

## Inputs

- `the_one/interfaces/web/static/js/areas/admin.js` — current admin area with General, Agents (placeholder), Integrations (placeholder), System (placeholder)
- `the_one/interfaces/web/static/styles.css` — existing admin styles
- API endpoints available: `GET/POST /api/providers`, `GET/PUT/DELETE /api/providers/{id}`, `POST /api/providers/{id}/test`, `GET /api/providers/{id}/models`, `GET /api/agents`

## Outputs

- Admin sidebar shows "LLM Providers" category (replacing "Integrations")
- Clicking "LLM Providers" shows a provider list with cards/rows showing name, type badge, and action buttons
- "Add Provider" button opens an inline form
- Form shows type-specific fields based on selected provider type
- "Test Connection" button calls the test endpoint and shows success/failure
- On successful test, models auto-load and display
- "Refresh Models" button re-fetches models
- Save creates/updates via API
- Delete button with agent-usage warning (shows count of agents using this provider)

## Acceptance Criteria

- [x] Admin sidebar shows "LLM Providers" as an active category (no "Soon" badge); "Integrations" is removed
- [x] Clicking "LLM Providers" renders a provider list view in the content area
- [x] Provider list shows each provider as a card/row with: name, type badge, action buttons (edit, delete)
- [x] "Add Provider" button opens an inline form in the content area
- [x] Provider type dropdown shows: ollama, openai-compatible, openai, anthropic
- [x] Selecting a type shows/hides fields dynamically:
  - `ollama`: base_url (default `http://localhost:11434/v1`)
  - `openai-compatible`: base_url + api_key (optional)
  - `openai`: api_key only (base_url defaults to `https://api.openai.com/v1`)
  - `anthropic`: api_key only (base_url defaults to `https://api.anthropic.com`)
- [x] "Test Connection" button (visible only after initial save, when provider has an `id`) calls `POST /api/providers/{id}/test` and shows success (green) or failure (red) feedback
- [x] On successful connection test, models auto-load from `GET /api/providers/{id}/models` and display as a list
- [x] "Refresh Models" button re-fetches the model list
- [x] Creating a provider calls `POST /api/providers` and updates the list
- [x] Editing a provider calls `PUT /api/providers/{id}` and updates the list
- [x] Deleting a provider shows an agent-usage warning (count of agents using it) and calls `DELETE /api/providers/{id}` on confirm
- [x] API key fields display as password inputs (masked) with a show/hide toggle
- [x] All provider operations show flash feedback (success/failure)
- [x] `ruff check the_one/ tests/` passes clean

## Verification Steps

- Open browser to Admin area, click "LLM Providers"
- Create a provider of each type, verify type-specific fields appear/hide
- Edit a provider, verify fields populate correctly
- Test connection on a real local Ollama instance (if available)
- Verify model list appears after successful test
- Delete a provider, verify agent-usage warning appears if agents reference it
- `ruff check the_one/ tests/`

## Implementation Guidance

1. **Update admin categories** (`admin.js`)
   - Replace `{ id: 'integrations', label: 'Integrations', active: false }` with `{ id: 'providers', label: 'LLM Providers', active: true }`
   - In `renderContent()`, add `else if (currentCategory === 'providers') { renderProvidersPanel(); }`

2. **Build `renderProvidersPanel()`** (`admin.js`)
   - Fetch `GET /api/providers` to get the list
   - Render a header with "LLM Providers" title and "Add Provider" button
   - Render provider cards in a list/table:
     ```
     [Type Badge] Provider Name            [Edit] [Delete]
     ```
   - Type badge should be color-coded: ollama=green, openai-compatible=yellow, openai=blue, anthropic=purple

3. **Build provider form** (`admin.js`)
   - Shown inline in the content area (replaces the card list when adding/editing)
   - Fields: Name (text), Type (select dropdown), Base URL (text, conditional), API Key (password, conditional)
   - Type change handler: show/hide fields and set default base_url values
   - Default base URLs per type:
     - ollama: `http://localhost:11434/v1`
     - openai-compatible: (empty, user must provide)
     - openai: `https://api.openai.com/v1`
     - anthropic: `https://api.anthropic.com`
   - API key field: `<input type="password">` with a small eye icon toggle to show/hide
   - When `base_url` field is hidden (openai, anthropic), the form must still populate the default `base_url` value in the submitted payload — `base_url` is required on `LLMProviderConfig`
   - "Cancel" button returns to list view
   - "Save" button: POST for create, PUT for edit

4. **Connection test** (`admin.js`)
   - "Test Connection" button visible only after provider is saved (has an id)
   - Calls `POST /api/providers/{id}/test`
   - Shows inline status: green checkmark + "Connected" or red X + error message
   - On success, auto-call `GET /api/providers/{id}/models` and render model list

5. **Model list** (`admin.js`)
   - Rendered below the form after successful connection test
   - Simple list of model names (id)
   - "Refresh Models" button to re-fetch
   - Show loading spinner during fetch

6. **Delete with agent-usage warning** (`admin.js`)
   - Before deleting, fetch `GET /api/agents` and count agents where `provider_config_id === providerId`
   - If count > 0: show warning "This provider is used by N agent(s). Deleting it will leave them without a provider."
   - Double-click/confirm pattern (like Studio's delete)

7. **Flash feedback** (`admin.js`)
   - Replicate the flash pattern from Studio: create a `div.admin-flash`, append to content, fade in via `.visible` class, remove after 2s. Use `.area-admin .admin-flash` CSS scoped to admin area (same visual treatment as `.area-studio .studio-flash`)
   - Show on create, update, delete, test success/failure

8. **CSS styles** (`styles.css`)
   - Add styles for provider cards, form fields, type badges, connection test status, model list
   - Follow existing `.area-admin .admin-*` naming: `.admin-provider-card`, `.admin-provider-badge`, `.admin-provider-form`, etc.
   - Keep the dark theme consistent with existing design

## Edge Cases

- **Empty provider list**: Show "No providers configured. Add one to get started." placeholder
- **API key masking on edit**: PUT endpoint handles masked keys (preserves original) — the form should send the masked value as-is if unchanged, or the new value if the user clears and re-enters
- **Type change during edit**: If user changes type, update visible fields and defaults but don't lose entered values unnecessarily
- **Connection test on unsaved provider**: Button should be disabled/hidden until the provider is saved
- **Model discovery failure**: Show error message, don't crash — user can retry with "Refresh Models"
- **Long model lists**: Scroll within a bounded container, don't let it push the form out of view

## Files Affected

- `the_one/interfaces/web/static/js/areas/admin.js` — provider list, form, CRUD, test, model discovery
- `the_one/interfaces/web/static/styles.css` — provider card, form, badge, test status, model list styles

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] Commit all changes together (code + artifacts)
