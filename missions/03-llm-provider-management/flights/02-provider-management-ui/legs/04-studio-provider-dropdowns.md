# Leg: studio-provider-dropdowns

**Status**: completed
**Flight**: [Provider Management UI](../flight.md)

## Objective

Fix the broken Studio LLM fields by replacing free-text provider/model/base_url with dynamic provider and model dropdowns, handling null provider_config_id with an actionable placeholder.

## Acceptance Criteria

- [x] `allProviders` state added, `fetchProviders()` called in `loadAll()`
- [x] Default agent object uses `provider_config_id: null` instead of `llm_provider`/`llm_base_url`
- [x] LLM Configuration section replaced: Provider `<select>` dropdown populated from GET /api/providers, Model `<input>` with `<datalist>` for type-ahead
- [x] `provider_config_id=null` handled with "No provider -- configure in Admin" disabled option (or "Select a provider..." when providers exist)
- [x] Models auto-fetched on provider change via `fetchModelsForProvider()`
- [x] `collectFormData()` sends `provider_config_id`, `llm_provider`/`llm_base_url` removed
- [x] Accessibility: for/id labels, aria-live on model loading indicator
