# Leg: provider-list-and-editor

**Status**: completed
**Flight**: [Provider Management UI](../flight.md)

## Objective

Build the Admin "LLM Providers" category with a card/table layout, inline add/edit form with type-specific fields, CRUD wired to API, connection test with model auto-discovery, and delete with agent-usage warning.

## Acceptance Criteria

- [x] "Integrations" and "Agents" placeholders replaced with `{ id: 'providers', label: 'LLM Providers', active: true }`
- [x] `renderProvidersPanel()` displays provider cards with name, color-coded type badge, edit/delete buttons
- [x] Inline add/edit form with type-specific fields (ollama: base_url, openai-compatible: base_url + api_key, openai: api_key with default base_url, anthropic: api_key with default base_url)
- [x] API key rendered as password input with show/hide toggle
- [x] "Test Connection" button calls POST /api/providers/{id}/test, auto-fetches models on success
- [x] "Refresh Models" button re-fetches models
- [x] Delete shows agent-usage warning (fetches GET /api/agents, counts matching provider_config_id)
- [x] Flash feedback on all operations
- [x] Accessibility: for/id label association, aria-live on flash/test results, focus-visible on buttons, role="list"/role="listitem" on cards

## Implementation Notes

- Combined with Leg 3 in a single admin.js rewrite since both legs modify the same file and are tightly coupled
