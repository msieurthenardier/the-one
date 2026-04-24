# Leg: system-and-settings-cleanup

**Status**: completed
**Flight**: [Provider Management UI](../flight.md)

## Objective

Add the Admin "System" category with encryption key rotation, remove stale categories and settings sections, and update stale documentation.

## Acceptance Criteria

- [x] "Agents" placeholder removed from admin categories
- [x] "System" category activated with `renderSystemPanel()`
- [x] System panel has "Rotate Encryption Key" button with double-click confirm, warning text, calling POST /api/encryption/rotate with flash feedback
- [x] "LLM Configuration" section removed from General settings (settingSections and fieldLabels)
- [x] agents.md updated: stale llm_provider/llm_model references removed, provider_config_id and provider resolution documented

## Implementation Notes

- Implemented alongside Leg 2 in a single admin.js rewrite due to tight coupling
