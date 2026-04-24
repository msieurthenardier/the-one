# Leg: hat

**Status**: completed
**Flight**: [Provider Management UI](../flight.md)

## Objective

Guided human acceptance testing session across all UI changes from this flight, with iterative fixes.

## Verification Steps

- [x] Open Admin, navigate to LLM Providers: verify add, edit, delete for all 4 provider types (ollama, openai-compatible, openai, anthropic)
- [x] Verify type-specific form fields show/hide correctly per provider type
- [x] Test Connection button shows clear success/failure feedback
- [x] Models auto-load after successful connection test; Refresh Models button re-fetches
- [x] Delete a provider in use: verify warning about affected agents appears
- [x] Navigate to System: verify Rotate Encryption Key button with double-click confirm
- [x] After rotation, verify providers remain accessible
- [x] Navigate to General settings: verify LLM Configuration section is gone
- [x] Open Studio agent editor: verify provider dropdown and model dropdown
- [x] Verify agents with no provider show "No provider -- configure in Admin" placeholder
- [x] Select a provider: verify models populate in the model datalist
- [x] Create/edit an agent: verify provider_config_id is sent correctly
- [x] Verify CLI does not crash on startup
- [x] Run full test suite: all tests pass with no regressions

## Bugs Found and Fixed

1. **Models list disappeared when opening edit form** — The models list was not being fetched when opening the edit form for an existing provider. Fixed by adding auto-fetch of models when the edit form is opened, so the model list populates immediately.

2. **Studio provider dropdown not refreshing after Admin changes** — After adding or modifying providers in Admin, the Studio agent editor's provider dropdown still showed stale data. Fixed by adding a re-fetch of the providers list in the Studio's `activate()` function, so the dropdown refreshes every time the user navigates to Studio.
