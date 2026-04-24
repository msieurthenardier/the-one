# Leg: studio-provider-dropdowns

**Status**: completed
**Flight**: [Provider Management UI](../flight.md)

## Objective

Fix the broken Studio agent editor LLM fields: replace free-text provider/model/base_url inputs with a provider dropdown and model dropdown populated from the API, and handle agents with no configured provider.

## Context

- The Studio editor's default object (line 169-172 of `studio.js`) references `llm_provider`, `llm_base_url` which no longer exist on `AgentConfig` (removed in Flight 01)
- Lines 209-213 render free-text inputs for Provider, Model, and Base URL — these are stale
- `AgentConfig` now has `provider_config_id: str | None` and `llm_model: str`
- The `extra="ignore"` on `AgentConfig` silently drops the stale `llm_provider` and `llm_base_url` fields sent by the form
- Flight design: provider dropdown from `GET /api/providers`, model dropdown from `GET /api/providers/{id}/models`, remove Base URL field
- Default agent has `provider_config_id=None` — show actionable "No provider — configure in Admin" placeholder

## Inputs

- `studio.js` — current editor with stale LLM fields
- `styles.css` — existing studio styles
- API: `GET /api/providers` (list), `GET /api/providers/{id}/models` (models per provider)

## Outputs

- Provider dropdown populated from configured providers
- Model dropdown populated dynamically when provider changes
- Base URL field removed (it's part of the provider config now)
- Agents with `provider_config_id=null` show "No provider" placeholder
- Form submits `provider_config_id` and `llm_model` (not `llm_provider`/`llm_base_url`)

## Acceptance Criteria

- [x] LLM Configuration section shows a Provider dropdown (not free-text input)
- [x] Provider dropdown options come from `GET /api/providers` showing provider name and type
- [x] Provider dropdown includes a disabled "No provider — configure in Admin" option when `provider_config_id` is null
- [x] Selecting a provider auto-fetches models from `GET /api/providers/{id}/models`
- [x] Model dropdown populates with discovered models; current `llm_model` is pre-selected if it exists in the list
- [x] Model dropdown allows free-text entry as fallback (in case the model isn't discovered)
- [x] Base URL field is completely removed from the editor
- [x] Default object for new agents uses `provider_config_id: null, llm_model: 'qwen2.5:7b'` (not stale `llm_provider`/`llm_base_url`)
- [x] `collectFormData()` sends `provider_config_id` (not `llm_provider`/`llm_base_url`)
- [x] Editing an existing agent correctly pre-selects the current provider and model
- [x] Provider dropdown has `for`/`id` label association for accessibility
- [x] Model field has `for`/`id` label association for accessibility
- [x] `pytest tests/ -v --timeout=30` passes
- [x] `ruff check the_one/ tests/` passes clean

## Verification Steps

- Open Studio → select an agent → verify Provider dropdown shows configured providers
- Change provider → verify Model dropdown updates with that provider's models
- Create a new agent → verify default shows "No provider" placeholder
- Save an agent with a selected provider → verify `provider_config_id` is saved correctly
- Verify Base URL field is gone

## Implementation Guidance

1. **Fetch providers on load** (`studio.js`)
   - Add `var allProviders = [];` to the state variables
   - Add `fetchProviders()` that calls `GET /api/providers`
   - Include in `loadAll()` Promise.all

2. **Update default object** (`studio.js` `renderEditor`)
   - Replace `llm_provider: 'ollama', llm_base_url: null` with `provider_config_id: null`
   - Keep `llm_model: 'qwen2.5:7b'`

3. **Replace LLM fields** (`studio.js` `renderEditor`)
   - Remove the three free-text inputs (Provider, Model, Base URL)
   - Add Provider `<select>` dropdown:
     - Options: each provider as `<option value="{id}">{name} ({type})</option>`
     - If `provider_config_id` is null: add a disabled selected option "No provider — configure in Admin"
     - Pre-select the agent's `provider_config_id` if set
   - Add Model field:
     - Use `<input>` with a `<datalist>` for type-ahead suggestions from discovered models
     - This allows both selection from discovered models AND free-text entry
     - Pre-populate with `cfg.llm_model`
   - Add an inline model loading indicator

4. **Auto-fetch models on provider change** (`studio.js`)
   - When provider dropdown changes, call `GET /api/providers/{id}/models`
   - Populate the `<datalist>` with model IDs
   - Show a brief loading state during fetch

5. **Update `collectFormData()`** (`studio.js`)
   - Read `provider_config_id` from the select value (convert empty string to null)
   - Read `llm_model` from the input value
   - Remove `llm_provider` and `llm_base_url` collection
   - Remove the `if (data.llm_base_url === '') data.llm_base_url = null;` cleanup

6. **CSS updates** (`styles.css`)
   - Style the provider select dropdown (`.field-select` or similar)
   - Style the model loading indicator
   - Ensure consistent look with other studio form fields

## Edge Cases

- **No providers configured**: Dropdown shows only "No provider — configure in Admin" (disabled). User cannot select a provider until one is configured in Admin.
- **Provider deleted after agent was configured**: `provider_config_id` won't match any option. Show it as "Unknown provider" or similar, and let the user re-select.
- **Model not in discovered list**: The datalist/input approach allows free-text, so users can type a model name even if it isn't discovered. This handles edge cases where discovery fails.
- **Model fetch fails**: Show empty datalist, no crash. The input still accepts free-text.
- **Provider with no models**: Show empty datalist with a "No models discovered" hint.

## Files Affected

- `the_one/interfaces/web/static/js/areas/studio.js` — replace LLM fields, add provider/model dropdowns
- `the_one/interfaces/web/static/styles.css` — dropdown and loading indicator styles

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] Commit all changes together (code + artifacts)
