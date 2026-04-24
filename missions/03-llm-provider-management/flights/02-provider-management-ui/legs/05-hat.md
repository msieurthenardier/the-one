# Leg: hat

**Status**: planning
**Flight**: [Provider Management UI](../flight.md)

## Objective

Guided human acceptance testing session across all UI changes from this flight, with iterative fixes.

## Verification Steps

- [ ] Open Admin, navigate to LLM Providers: verify add, edit, delete for all 4 provider types (ollama, openai-compatible, openai, anthropic)
- [ ] Verify type-specific form fields show/hide correctly per provider type
- [ ] Test Connection button shows clear success/failure feedback
- [ ] Models auto-load after successful connection test; Refresh Models button re-fetches
- [ ] Delete a provider in use: verify warning about affected agents appears
- [ ] Navigate to System: verify Rotate Encryption Key button with double-click confirm
- [ ] After rotation, verify providers remain accessible
- [ ] Navigate to General settings: verify LLM Configuration section is gone
- [ ] Open Studio agent editor: verify provider dropdown and model dropdown
- [ ] Verify agents with no provider show "No provider -- configure in Admin" placeholder
- [ ] Select a provider: verify models populate in the model datalist
- [ ] Create/edit an agent: verify provider_config_id is sent correctly
- [ ] Verify CLI does not crash on startup
- [ ] Run full test suite: all tests pass with no regressions
