# Mission: LLM Provider Management

**Status**: active

## Outcome

The-one provides a complete, self-service interface for managing LLM provider connections. Users configure providers (local and cloud) through the Administration area, with automatic model discovery, connection verification, and encrypted credential storage. Local providers like Ollama actively manage model loading at runtime — loading models on demand when agents need them, supporting concurrent models when VRAM allows, and warning users when selected models risk exceeding available memory. The Studio agent editor draws from configured providers and discovered models, replacing free-text entry with informed selection. The system moves from static env-var configuration to a dynamic, multi-provider runtime where provider setup is part of the first-start experience.

## Context

After Mission 02 (Multi-Agent Workspace), the-one supports multiple agents with per-agent LLM settings (provider name, model, base URL). However, these settings are essentially free-text — there's no way to register, validate, or manage provider connections through the UI. The Admin area's "General" page shows LLM config as read-only env vars. The "Agents", "Integrations", and "System" categories are placeholders.

The current architecture has useful building blocks:
- `OllamaProvider` works with any OpenAI-compatible server via `base_url`, but this conflates two distinct use cases: actual Ollama (with native API for model lifecycle) and generic OpenAI-compatible servers (LM Studio, vLLM, llama.cpp)
- The provider registry (`llm/registry.py`) lazy-loads by name but is hardcoded to three provider types
- `AgentConfig` carries `llm_provider`, `llm_model`, and `llm_base_url` fields as free text
- `AgentFactory` calls `get_provider()` directly with these fields
- SQLite persistence and the repository pattern are established
- LLM settings in `config.py` (`llm_provider`, `llm_model`, `llm_base_url`) are env-var based and will be removed in favor of DB-stored provider configurations

This mission introduces four distinct provider types:
- **ollama** — Ollama instances with native API access for model lifecycle management (load, unload, VRAM monitoring)
- **openai-compatible** — Generic OpenAI-compatible servers (LM Studio, vLLM, llama.cpp, text-generation-webui) with no model lifecycle
- **openai** — OpenAI cloud API with credential management and model discovery
- **anthropic** — Anthropic cloud API with credential management and model discovery

## Success Criteria

- [ ] Users can add, edit, and remove LLM provider configurations through the Administration interface, specifying connection details and credentials for each
- [ ] Multiple instances of the same provider type can coexist with distinct configurations (e.g., two Ollama instances at different URLs, or two OpenAI accounts with different API keys)
- [ ] API credentials are stored encrypted at rest, with the encryption key auto-generated on first start and stored on the filesystem outside the database; a rotate function re-encrypts all stored secrets with a new key
- [ ] The provider configuration interface discovers available models by querying provider APIs after credentials are verified (Ollama tags endpoint, OpenAI models list, Anthropic models list)
- [ ] Users can verify provider connectivity before saving a configuration
- [ ] The system manages model loading on Ollama instances at runtime — loading models on demand when agent conversations start, supporting concurrent models when VRAM allows, and warning users during model selection when a model's size risks exceeding available memory
- [ ] The Studio agent editor presents configured providers and their discovered models for selection, replacing free-text entry with dynamic dropdowns
- [ ] The system degrades gracefully when a configured provider is unreachable or a requested model is unavailable, surfacing clear feedback to the user
- [ ] On first start with no provider configurations, the application guides the user to set up at least one provider before chat is functional

## Stakeholders

- **Primary user**: Solo developer/operator who runs multiple local models (different sizes/specializations) and optionally uses cloud providers, and wants to manage all of this from the UI rather than editing env vars and restarting
- **Future self-modification**: The agent itself, which will eventually select its own provider/model based on task requirements

## Constraints

- **No frontend frameworks**: Vanilla JS, consistent with existing app-shell patterns
- **No ORMs**: Raw SQL via aiosqlite, following the repository pattern from Mission 02
- **Minimal new dependencies**: `cryptography` (Fernet) is approved for secret encryption. No other new dependencies beyond what's already installed (openai, anthropic, httpx)
- **Remove env-var LLM config**: The `llm_provider`, `llm_model`, and `llm_base_url` settings are removed from `config.py`. Provider configuration lives exclusively in the database. Development environments can seed the DB, but there is no env-var fallback for LLM settings
- **Preserve non-LLM functionality**: The CLI interface, self-deployment pipeline, and Concourse automation must continue working. Non-LLM env vars (host, port, data_dir, workspace_dir, concourse_*) are unchanged
- **Python 3.11+, async throughout**
- **Small-model friendly**: Provider config UI patterns should be simple enough for 7B-class models to work with when self-modifying

## Environment Requirements

- Local Python 3.11+ with editable install (`pip install -e ".[all-llms,dev]"`)
- Docker and docker-compose for container testing
- Ollama running locally with at least one model pulled (for model discovery and load/unload testing)
- ruff for linting and formatting
- A browser for UI development and testing

## Open Questions

_(all resolved)_

## Resolved Questions

- **Cloud model discovery**: Query provider APIs after credentials are saved and connectivity verified. Credentials are a prerequisite to model discovery — this is the expected workflow.
- **Env-var to DB transition**: Remove LLM env vars entirely. No auto-migration, no fallback. First start with an empty DB requires provider setup through the UI. Dev environments can seed the DB.
- **Ollama vs. generic OpenAI-compatible**: Split into separate provider types. `ollama` gets native API model lifecycle; `openai-compatible` is a generic type with no model management.
- **Concurrent model loading**: Support concurrent models on Ollama when VRAM allows. When configuring model selection, display VRAM warnings if a model is too large for available memory.
- **Encryption key management**: Auto-generate a Fernet key on first start, store it as a file in `data_dir` (e.g., `~/.the-one/encryption.key`). Provide a rotate function that generates a new key and re-encrypts all stored secrets. No env var required.

## Known Issues

_(none yet -- this is a new mission)_

## Flights

> **Note:** These are tentative suggestions, not commitments. Flights are planned and created one at a time as work progresses. This list will evolve based on discoveries during implementation.

- [x] Flight 1: **Provider Data Model & Persistence** -- Design the provider configuration data model (type, name, base URL, encrypted credentials, provider-specific metadata). Implement Fernet encryption with auto-generated key file and key rotation. Create the repository, schema migration, and REST API endpoints for provider CRUD. Remove LLM env vars from Settings.
- [x] Flight 2: **Provider Management UI** -- Build the provider configuration page in Admin under "Integrations" (replacing the placeholder). Provider list in sidebar, editor panel with type-specific forms (ollama, openai-compatible, openai, anthropic), connection test button, model discovery after credential verification.
- [x] Flight 3: **Model Lifecycle & VRAM Awareness** -- Implement Ollama native API integration for model loading/unloading. Query VRAM usage and model sizes. Support concurrent model loading when memory allows. Display warnings during model selection when a model risks exceeding available VRAM. Wire model loading into agent conversation startup.
- [ ] Flight 4: **Agent Integration & First-Start Flow** -- Update Studio agent editor with dynamic provider/model dropdowns. Update AgentFactory to resolve provider configs from DB. Build first-start experience that guides users to configure a provider before chat is available. Handle edge cases (referenced provider deleted, etc.).
- [ ] Flight 5: **Resilience & Verification** -- Graceful degradation for unreachable providers, clear error feedback in UI, encryption key rotation end-to-end, edge case handling (model unavailable, provider deleted mid-conversation). Full end-to-end verification across all flows.
